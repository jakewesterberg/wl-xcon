"""Saccade detection: ours against theirs, and online against batch.

Three layers, and the ordering is the argument. `velocity` and `median_scale` are
`wl-preproc`'s, so they are checked against its pinned, versioned fixtures. `detect` must agree with
their detector interval for interval, because S5 §5 chose this algorithm *specifically*
so that online-versus-offline disagreement measures staleness and latency rather than
two different methods -- a claim that is worth nothing unless the two really are the
same method. `Detector` is then checked against `detect`, never against a fresh
expectation, so the online path is only ever compared with the shared algorithm.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
from pathlib import Path

import pytest

from wl_xcon.calibration import EyeMap, Mapping, Model
from wl_xcon.eye import Replay, Tracker
from wl_xcon.gaze import Tracked
from wl_xcon.run import Recorded, run_trial
from wl_xcon.saccade import (
    DEFAULT_LAMBDA,
    DEFAULT_MIN_DURATION_SAMPLES,
    HALF_WINDOW,
    VERSION,
    Detector,
    Params,
    _amplitude,
    _outside,
    detect,
    median_scale,
    thresholds,
    velocity,
)
from wl_xcon.task import (REMEMBERED, After, On, Outcome, SaccadeOnset, SaccadeTo, State, Trial,
                          Window)

FS = 500.0
DT = 1.0 / FS


def _trace(saccades, n=600, noise=0.02, seed=3):
    """A fixation trace with saccades stepped into it.

    `saccades` is `(onset_sample, duration_samples, dx_deg, dy_deg)`. Position moves
    linearly across the saccade, which is what makes velocity supra-threshold there
    and nowhere else.
    """
    rng = random.Random(seed)
    x, y = 0.0, 0.0
    gaze, at = [], []
    steps = {}
    for onset, duration, dx, dy in saccades:
        for k in range(duration):
            steps[onset + k] = (dx / duration, dy / duration)
    for i in range(n):
        step = steps.get(i, (0.0, 0.0))
        x += step[0]
        y += step[1]
        gaze.append((x + rng.gauss(0, noise), y + rng.gauss(0, noise)))
        at.append(i * DT)
    return gaze, at


# ---------------------------------------------------------------------------
# Ours, on its own terms
# ---------------------------------------------------------------------------


def test_a_clean_saccade_is_found_at_about_the_right_place():
    gaze, at = _trace([(200, 10, 8.0, 0.0)])
    found = detect(gaze, at)
    assert len(found) == 1
    assert abs(found[0].start - 200) <= 4
    assert found[0].amplitude_deg == pytest.approx(8.0, abs=0.5)
    assert not found[0].flagged


def test_pure_fixation_produces_nothing():
    """The threshold is estimated from the trace's own noise, so a trace that is all
    noise must not find events in it -- otherwise every fixation trial reports
    saccades and the guard is worthless."""
    gaze, at = _trace([])
    assert detect(gaze, at) == []


def test_two_saccades_are_two_events():
    gaze, at = _trace([(150, 10, 6.0, 0.0), (400, 10, -6.0, 2.0)], n=700)
    found = detect(gaze, at)
    assert len(found) == 2
    assert found[0].start < found[1].start


def test_a_run_shorter_than_the_minimum_duration_is_not_a_saccade():
    """Engbert-Kliegl's minimum duration is what separates a saccade from a noise
    excursion above threshold, and dropping it would make the detector fire on the
    tail of its own distribution."""
    brief = Params(min_duration_samples=40)
    gaze, at = _trace([(200, 10, 8.0, 0.0)])
    assert detect(gaze, at, brief) == []


def test_median_scale_is_not_a_standard_deviation():
    """The property the whole threshold rests on: adding large excursions must not
    inflate the scale much, or the detector desensitises exactly as a session
    accumulates the events it is looking for."""
    quiet = [0.1, -0.1, 0.2, -0.2] * 25
    with_saccades = quiet + [400.0, -380.0, 420.0] * 5

    quiet_scale = median_scale(quiet)
    loud_scale = median_scale(with_saccades)
    assert loud_scale < quiet_scale * 2.0

    ordinary_sd = _sd(with_saccades)
    assert ordinary_sd > quiet_scale * 20


def _sd(values):
    mean = sum(values) / len(values)
    return math.sqrt(sum((v - mean) ** 2 for v in values) / len(values))


def test_a_near_tie_cannot_produce_nan():
    """`median(v²) - median(v)²` is non-negative in exact arithmetic and can round
    negative in float64; `sqrt` of that is `nan`, silently. wl-preproc measured
    -1.78e-15 on a four-sample array."""
    assert median_scale([1.0, 1.0, 1.0, 1.0]) == 0.0
    assert not math.isnan(median_scale([0.1, 0.1, 0.1000000000000001, 0.1]))


# ---------------------------------------------------------------------------
# The stall rule (S5 §5)
# ---------------------------------------------------------------------------


def test_velocity_is_not_computed_across_a_gap():
    """Two samples 80 ms apart differenced as though 2 ms apart is an enormous fake
    velocity -- it fires the detector AND inflates the threshold meant to catch it."""
    gaze, at = _trace([])
    at = [t + (0.2 if i >= 300 else 0.0) for i, t in enumerate(at)]  # an 80 ms hole
    velocities = velocity(gaze, at, Params())
    assert all(v is None for v in velocities[298:301]), "the window spanning the hole"
    assert velocities[290] is not None and velocities[310] is not None


def test_a_missing_sample_produces_no_velocity():
    gaze, at = _trace([])
    gaze[300] = None
    velocities = velocity(gaze, at, Params())
    assert all(v is None for v in velocities[298:303])


def test_a_saccade_whose_window_touched_a_gap_is_flagged_not_dropped():
    """S5 §5, exactly: flagged, not silently reported, and not dropped either.
    Dropping hides a real saccade; reporting it unmarked launders an artifact."""
    gaze, at = _trace([(200, 10, 8.0, 0.0)])
    gaze[203] = None
    found = detect(gaze, at)
    assert found, "a dropped sample must not delete the saccade"
    assert any(s.flagged for s in found)


def test_the_gap_ceiling_matches_the_trackers_staleness_by_default():
    """Two answers to 'is this still about the same stretch of time' would drift."""
    from wl_xcon.eye import Tracker

    assert Params().max_gap_s == Tracker.staleness


# ---------------------------------------------------------------------------
# Online against batch
# ---------------------------------------------------------------------------


def _online(gaze, at, params=Params()):
    detector = Detector(params=params)
    return [s for t, g in zip(at, gaze) if (s := detector.accept(t, g)) is not None]


def test_the_online_detector_finds_what_the_batch_form_finds():
    """Not compared against a fresh expectation: the online path is checked against
    the shared algorithm, so a change to the algorithm cannot be silently satisfied
    by adjusting a number here."""
    gaze, at = _trace([(200, 10, 8.0, 0.0), (450, 12, -7.0, 3.0)], n=700)
    batch = detect(gaze, at)
    online = _online(gaze, at)

    assert len(online) == len(batch)
    for got, want in zip(online, batch):
        assert abs(got.start - want.start) <= 2


def test_the_online_detector_reports_on_the_sample_that_confirms():
    """Confirmation is not onset. A run becomes a saccade once
    `min_duration_samples` of it exist, and `start` is where it actually began -- so
    the record keeps the onset while the trial loop learns of it later."""
    gaze, at = _trace([(200, 12, 8.0, 0.0)])
    detector = Detector()
    confirmed_at = None
    for i, (t, g) in enumerate(zip(at, gaze)):
        if detector.accept(t, g) is not None:
            confirmed_at = i
            break
    assert confirmed_at is not None
    saccade = detector.onset
    assert confirmed_at > saccade.start, "confirmation must trail onset"
    assert confirmed_at - saccade.start >= DEFAULT_MIN_DURATION_SAMPLES


def test_the_online_amplitude_is_measured_as_the_batch_form_measures_it():
    """Start point to end point over the samples a confirmation has, `start` to `stop - 1`: the
    online detector measures them from the run's first sample, kept as the run starts, to the last
    in its own buffer (XC-414; version 2), and the batch form's `_amplitude` over the same samples
    of the trace gives the same number, bit for bit."""
    gaze, at = _trace([(200, 10, 8.0, 0.0), (450, 12, -7.0, 3.0)], n=700)
    found = _online(gaze, at)

    assert len(found) == 2
    for saccade in found:
        assert saccade.amplitude_deg > 1.0
        assert saccade.amplitude_deg == _amplitude(gaze, saccade.start, saccade.stop)


def test_nothing_fires_before_the_threshold_has_enough_samples():
    """A scale estimated from a handful of samples is a scale estimated from noise.
    The same refusal `Tracker.state` makes before its first sample."""
    gaze, at = _trace([(10, 10, 8.0, 0.0)])
    detector = Detector(params=Params(warmup_samples=200))
    assert _online_with(detector, gaze[:150], at[:150]) == []
    assert not detector.ready


def _online_with(detector, gaze, at):
    return [s for t, g in zip(at, gaze) if (s := detector.accept(t, g)) is not None]


def test_reset_forgets_the_previous_trials_threshold():
    """The threshold is per trial (S5 §5). Carried across, a quiet first trial would
    decide a noisy second trial's sensitivity."""
    gaze, at = _trace([(200, 10, 8.0, 0.0)])
    detector = Detector()
    _online_with(detector, gaze, at)
    assert detector.ready

    detector.reset()
    assert not detector.ready
    assert detector.onset is None


def test_the_onset_edge_survives_exactly_one_question():
    """The trial loop asks once per frame. An edge that persisted would fire the
    guard on every subsequent frame; one that vanished before being asked would be
    missed entirely."""
    gaze, at = _trace([(200, 12, 8.0, 0.0)])
    detector = Detector()
    for t, g in zip(at, gaze):
        if detector.accept(t, g) is not None:
            break
    assert detector.onset is not None
    detector.accept(at[-1] + DT, gaze[-1])
    assert detector.onset is None


#: Every buffer `Detector` keeps (XC-414).
_BUFFERS = ("_x", "_y", "_t", "_present", "_ux", "_uy", "_uz", "_local", "_vx", "_vy", "_sorting")


def test_the_buffer_stays_bounded_over_a_long_trial():
    """Hot-path discipline: no unbounded work or memory per frame. A trial loop that
    grew a list for its whole duration would allocate through the trial it must not
    allocate in. **Each buffer is built with the detector** (XC-414), its size fixed by its
    parameters, and a long trial, saccades and all, neither rebuilds nor resizes one."""
    detector = Detector(history=100)
    built = {name: (getattr(detector, name), len(getattr(detector, name))) for name in _BUFFERS}
    gaze, at = _trace([(500, 10, 8.0, 0.0), (1500, 12, -7.0, 3.0)], n=3000)
    _online_with(detector, gaze, at)

    assert {name: (getattr(detector, name), len(getattr(detector, name))) for name in _BUFFERS} \
        == built
    assert all(getattr(detector, name) is buffer for name, (buffer, _) in built.items())
    assert max(size for _, size in built.values()) == 100


def _demanding(n: int = 1000):
    """A trace that makes the online detector do everything it does: hold perfectly still for its
    first 120 samples (so its thresholds are zero and re-estimated every sample), warm up, refresh,
    lose two samples far from any saccade, cross an 0.2 s hole in time, confirm saccades on both
    sides of it, and follow two that each lost a sample near their start: one confirmed once six of
    its velocities are measured, and one, a short saccade whose lost sample leaves it five, followed
    to the velocity that ends it and never confirmed (version 3; version 2 confirmed it there)."""
    gaze, at = _trace([(200, 10, 8.0, 0.0), (450, 12, -7.0, 3.0), (800, 15, 5.0, 5.0),
                       (900, 4, 4.0, 0.0)], n=n)
    gaze[:120] = [(0.0, 0.0)] * 120
    gaze[300] = gaze[700] = None
    gaze[203] = gaze[905] = None
    at = [t + (0.2 if i >= 600 else 0.0) for i, t in enumerate(at)]
    return gaze, at


def test_a_sample_builds_nothing_whatever_it_does():
    """**On the trial loop's path**, a sample a frame (`gaze.Tracked.display`), so accepting one
    builds nothing (XC-414), on every sample of `_demanding`'s trace, with a history short enough
    that its buffers wrap and its thresholds refreshed every seventh velocity: no list, slice,
    generator or tuple, where until 2026-10-29 every sample appended to three growing lists, sliced
    two, walked them with generators, and every refresh copied its velocities into a list. Both
    ways a run that lost a sample goes (version 3) are among them: confirmed in flight once six of
    its velocities are measured, and followed to its end with five, never confirmed."""
    from _builds import built_on

    gaze, at = _demanding()
    detector = Detector(history=60, refresh_every=7)
    built, confirmed = set(), []
    for t, g in zip(at, gaze):
        built.update(built_on(detector.accept, t, g))
        if detector.onset is not None:
            confirmed.append((detector.onset, detector.in_flight))

    assert [s.start for s, _ in confirmed if s.start > 600] and len(confirmed) >= 3
    assert {flying for s, flying in confirmed if s.flagged} == {True}
    assert not [s for s, _ in confirmed if 890 <= s.start <= 910], \
        "the short saccade that lost a sample is followed, and never confirmed"
    assert sorted(built) == []


def test_a_gaze_sample_that_is_no_number_makes_every_velocity_reading_it_no_number():
    """**A non-finite position propagates** (version 6), as wl-preproc's `local_velocity` says
    of its own ("a non-finite position makes every window that reads it NaN") and as the per-axis
    difference did until version 4: a NaN in sample 650's gaze makes the five velocities whose
    windows hold it NaN on both axes, batch and online alike, and no others. Version 4's local
    frame read a direction it could not normalize as the origin, so those velocities were
    numbers, near zero, and the thresholds were taken over them as if measured."""
    gaze, at = _trace([(200, 10, 8.0, 0.0), (450, 12, -7.0, 3.0)], n=700)
    gaze[650] = (math.nan, gaze[650][1])

    velocities = velocity(gaze, at, Params())

    assert [n for n, v in enumerate(velocities)
            if v is not None and (v[0] != v[0] or v[1] != v[1])] == list(range(648, 653))
    assert all(v[0] != v[0] and v[1] != v[1] for v in velocities[648:653])


@pytest.mark.parametrize("history,nan", [(60, False), (1000, False), (1000, True)],
                         ids=["wrapped", "filling", "filling, a NaN among them"])
def test_the_online_thresholds_are_the_batch_form_s_over_the_last_history_velocities(history,
                                                                                       nan):
    """Re-estimated in buffers built with the detector (XC-414), the thresholds are still
    `thresholds` over the last `history` usable velocities, oldest first, bit for bit: once the
    velocity buffer has wrapped, while it is still filling, and with a NaN among the velocities
    then, where the order `sorted` met them in decides each median."""
    gaze, at = _trace([(200, 10, 8.0, 0.0), (450, 12, -7.0, 3.0)], n=700)
    if nan:
        gaze[650] = (math.nan, gaze[650][1])
    detector = Detector(history=history, refresh_every=1)
    for t, g in zip(at, gaze):
        detector.accept(t, g)
    last = [v for v in velocity(gaze, at, Params()) if v is not None][-history:]

    assert repr((detector._eta_x, detector._eta_y)) == repr(thresholds(last, Params()))


def test_indices_stay_absolute_once_the_buffer_has_been_trimmed():
    """The buffers are rings, written over from their first slot once full (XC-414; until then
    trimmed), so a stored buffer index goes stale the moment it is. A saccade late in a long
    trial must still report where it actually began."""
    detector = Detector(history=60)
    gaze, at = _trace([(900, 12, 9.0, 0.0)], n=1100)
    found = _online_with(detector, gaze, at)
    assert found, "a saccade after many trims is still a saccade"
    assert abs(found[0].start - 900) <= 6, f"start drifted to {found[0].start}"


# ---------------------------------------------------------------------------
# A sample lost near a saccade's start: counted, marked (version 2), by its measured velocities
# (version 3)
# ---------------------------------------------------------------------------
#
# One missing gaze sample leaves unknown the five velocities whose windows hold it. Until version 2
# the online detector confirmed a run only on the sample at which it was exactly
# `min_duration_samples` long, so a run whose confirming velocity was one of those five was never
# reported at all, while `detect` reported it flagged (found by the XC-414 work, 2026-10-29). The
# PI, asked 2026-10-30, "Count it, marked (Recommended)": "Its landing is measured, so live and
# offline agree. Some trials now scored 'no response' would become correct or wrong-target."
#
# Version 2 counted the unknown velocities toward a run's length, as `detect` did, so one noise
# velocity outside the threshold beside a lost sample made a saccade of six (the saccade-gap-onset
# review's I1). The PI, asked 2026-11-04, "Require measured samples (Recommended)": "A saccade
# counts only if its minimum duration is met by measured, not filled-in, moving samples; the
# offline detection applies the same rule."


def _lost(gaze, *samples):
    """The trace with each of `samples` missing, as a sample the tracker never delivered is."""
    gaze = list(gaze)
    for k in samples:
        gaze[k] = None
    return gaze


def _confirmations(gaze, at, params=Params()):
    """Each saccade the online detector reports, with the sample that confirmed it and whether its
    run was still open then."""
    detector = Detector(params=params)
    found = []
    for k, (t, g) in enumerate(zip(at, gaze)):
        saccade = detector.accept(t, g)
        if saccade is not None:
            found.append((k, saccade, detector.in_flight))
    return found


#: A 12-sample saccade at sample 200, whose run starts at 198 and is confirmed on the velocity at
#: 203, the sixth, which sample 205 completes.
_TWELVE = [(200, 12, 8.0, 0.0)]


@pytest.mark.parametrize("into", range(3, 8))
def test_a_saccade_that_lost_a_sample_where_it_is_confirmed_is_reported_marked(into):
    """A sample `into` samples after its run's start, 3 to 7: each leaves the sixth velocity unknown
    and one before it known, so version 1 never reported the run. It is confirmed on the velocity
    that gives it six measured ones (version 3), five samples after a whole trace confirms it, the
    five the lost sample left unknown all in the run before then, at the batch form's start and
    flagged as the batch form flags it, its size start point to end point as the batch form
    measures it. Version 2 confirmed it on its first later velocity outside the threshold, the
    unknown ones counted, one to five samples after."""
    gaze, at = _trace(_TWELVE)
    [(whole_at, whole, _)] = _confirmations(gaze, at)
    lost = _lost(gaze, whole.start + into)

    found = _confirmations(lost, at)
    batch = detect(lost, at)

    assert [s.start for _, s, _ in found] == [s.start for s in batch] == [whole.start]
    assert [s.flagged for _, s, _ in found] == [s.flagged for s in batch] == [True]
    [(confirmed_at, saccade, flying)] = found
    assert confirmed_at - whole_at == 5 and flying
    assert saccade.amplitude_deg == _amplitude(lost, saccade.start, saccade.stop)


def test_a_short_saccade_a_lost_sample_leaves_five_measured_velocities_is_not_a_saccade():
    """**What "Require measured samples" costs** (version 3; the PI, 2026-11-04). A 4-sample
    saccade whose run is 7 velocities long, whole, and a sample lost 7 into it: five velocities
    outside the threshold, five unknown, then one inside it. Five are measured, short of six, so it
    is no saccade, online or in the batch form. Version 2 counted the run 10 long and confirmed it
    on the velocity that ends it, flagged; version 1 reported nothing."""
    gaze, at = _trace([(200, 4, 4.0, 0.0)])
    [(_, whole, _)] = _confirmations(gaze, at)
    assert [(s.start, s.stop - s.start) for s in detect(gaze, at)] == [(whole.start, 7)], \
        "whole, it is a saccade of seven measured velocities"
    lost = _lost(gaze, whole.start + 7)

    assert _confirmations(lost, at) == []
    assert detect(lost, at) == []


@pytest.mark.parametrize("before", range(-2, 4))
def test_a_saccade_whose_first_velocity_follows_a_lost_sample_is_marked(before):
    """A sample lost from three samples before the run's start to two into it: the run starts
    late or not at all, but its first velocity's window, or one of the two before it, held the
    lost sample, so the batch form flags it (`_saccade`'s window). It was reported online unflagged:
    an artifact the gap may have made, reported as though nothing were missing."""
    gaze, at = _trace(_TWELVE)
    [(_, whole, _)] = _confirmations(gaze, at)
    lost = _lost(gaze, whole.start - 1 + before)

    found = _confirmations(lost, at)
    batch = detect(lost, at)

    assert [(s.start, s.flagged) for _, s, _ in found] == [(s.start, s.flagged) for s in batch]
    assert [s.flagged for _, s, _ in found] == [True]


@pytest.mark.parametrize("shortest,reported", [(5, True), (6, False), (10, False)],
                         ids=["met by its measured velocities", "one measured short",
                              "met only with the unknown ones"])
def test_a_run_is_long_enough_only_by_its_measured_velocities(shortest, reported):
    """**The boundary** (version 3): the 4-sample saccade with a sample lost 7 into its run has
    five measured velocities outside the threshold, then five unknown, then one inside it. With
    `min_duration_samples` 5 it is a saccade, confirmed in flight on its fifth, at the batch form's
    start -- unflagged, the gap still ahead of it, which the batch form's flag sees -- and with 6 it
    is not, online or in the batch form, nor with 10, which version 2 met by counting the unknown
    ones, confirming it on the velocity that ends it, flagged."""
    gaze, at = _trace([(200, 4, 4.0, 0.0)])
    [(_, whole, _)] = _confirmations(gaze, at)
    lost = _lost(gaze, whole.start + 7)
    params = Params(min_duration_samples=shortest)

    found = _confirmations(lost, at, params)
    batch = detect(lost, at, params)

    assert [(s.start, s.flagged, flying) for _, s, flying in found] \
        == ([(whole.start, False, True)] if reported else [])
    assert [(s.start, s.flagged) for s in batch] == ([(whole.start, True)] if reported else [])


def _flagged_as_the_batch_form_would(velocities, start, centre):
    """`_saccade`'s flag over what a confirmation on the velocity at `centre` can know: whether
    the batch form leaves a velocity unknown from two samples before the run to the one before."""
    return any(velocities[k] is None for k in range(max(0, start - HALF_WINDOW), centre))


def test_each_flag_is_the_batch_form_s_window_where_a_lost_sample_neighbours_a_saccade():
    """**The flag's window, both edges, swept** (seeded): 100 saccades of random size, length and
    direction, each with one sample lost from eight before its onset to four into it. Every
    confirmation is flagged exactly when the batch form leaves a velocity unknown from two samples
    before its run to the velocity that confirms it. The sweep holds runs whose nearest unknown
    velocity before them is two samples back, which the window takes, and three, which it does
    not, so a window one narrower or one wider fails here."""
    rng = random.Random(20261030)
    nearest = set()
    for _ in range(100):
        onset = rng.randint(150, 300)
        gaze, at = _trace([(onset, rng.randint(6, 16), rng.uniform(1.0, 9.0), rng.uniform(-3.0, 3.0))],
                          n=480, seed=rng.randint(0, 10**6))
        lost = _lost(gaze, onset + rng.randint(-8, 4))
        velocities = velocity(lost, at, Params())
        for k, saccade, _ in _confirmations(lost, at):
            centre = k - HALF_WINDOW
            assert saccade.flagged == _flagged_as_the_batch_form_would(
                velocities, saccade.start, centre), (onset, saccade)
            back = [d for d in (1, 2, 3) if velocities[saccade.start - d] is None]
            if back:
                nearest.add(back[0])

    assert {2, 3} <= nearest


def test_reset_forgets_where_the_last_trial_lost_a_sample():
    """`reset` starts the last unknown velocity over. Carried from a trial that lost a sample near
    its end, its index, past every sample of the next trial, would flag every run in it, so the
    next trial's clean saccade would be reported as touching a gap it never had."""
    gaze, at = _trace(_TWELVE)
    [(_, whole, _)] = _confirmations(gaze, at)
    detector = Detector()
    _online_with(detector, _lost(gaze, len(gaze) - 3), at)

    detector.reset()

    assert [(s.start, s.flagged) for s in _online_with(detector, gaze, at)] == [(whole.start, False)]


@pytest.mark.parametrize("moving_from,start,flagged", [(0, 3, True), (4, 4, False)],
                         ids=["from the first sample", "from the fifth"])
def test_a_run_at_a_trial_s_first_velocities_is_flagged_as_the_batch_form_flags_it(
        moving_from, start, flagged):
    """`velocity` gives the first two samples no velocity, for want of a window, and the batch
    form's flag counts them unknown, as the detector's starting last unknown velocity does. With a
    two-velocity warmup the detector is ready on its second velocity, the trace's fourth: an eye
    moving from the first sample is outside the threshold there, so its run starts at 3, sample 1's
    unknown velocity two back, and is flagged; with the eye moving later the first run starts at 4,
    three back, unflagged."""
    rng = random.Random(11)
    gaze = [(0.5 * max(0, i - moving_from) + rng.gauss(0, 0.02), rng.gauss(0, 0.02))
            for i in range(40)]
    at = [i * DT for i in range(40)]
    params = Params(warmup_samples=2)

    k, saccade, _ = _confirmations(gaze, at, params)[0]

    assert (saccade.start, saccade.flagged) == (start, flagged)
    assert saccade.flagged == _flagged_as_the_batch_form_would(
        velocity(gaze, at, params), saccade.start, k - HALF_WINDOW)


def _fixating(n: int = 600, noise: float = 0.02, seed: int = 1):
    """Fixation, Gaussian noise `noise` degrees on each axis and nothing else, sampled at `FS`."""
    rng = random.Random(seed)
    return [(rng.gauss(0, noise), rng.gauss(0, noise)) for _ in range(n)], [i * DT for i in range(n)]


def _stepped(gaze, at: int = 300, step: float = 0.12):
    """`gaze` with the eye stepped `step` degrees to the right from sample `at`: one velocity
    outside the threshold, and no saccade."""
    return [(x + (step if i >= at else 0.0), y) for i, (x, y) in enumerate(gaze)]


@pytest.mark.parametrize("lost", [302, 303])
def test_a_lost_sample_beside_one_noise_velocity_is_no_saccade(lost):
    """**The question the PI answered on 2026-11-04** (the saccade-gap-onset review's I1, its
    probe 3(a)): fixation, a 0.12° step of the eye at sample 300 and no saccade, and sample `lost`
    lost. A velocity or two outside the threshold, then the five the lost sample leaves unknown,
    then one inside it: version 2 counted that a run of six or more, a saccade, flagged, online and
    in the batch form, where version 1 and wl-preproc report nothing. "Require measured samples
    (Recommended)": it is no saccade, live or batch."""
    gaze, at = _fixating()
    stepped = _stepped(gaze)
    assert _confirmations(stepped, at) == [] and detect(stepped, at) == [], \
        "whole, the step is no saccade"
    trace = _lost(stepped, lost)
    velocities = velocity(trace, at, Params())
    eta = thresholds(velocities, Params())
    outside = [k for k in range(290, 312)
               if velocities[k] is not None and _outside(velocities[k], *eta)]
    unknown = [k for k in range(290, 312) if velocities[k] is None]
    assert 1 <= len(outside) < DEFAULT_MIN_DURATION_SAMPLES \
        and len(outside) + len(unknown) >= DEFAULT_MIN_DURATION_SAMPLES \
        and outside[-1] + 1 == unknown[0], "the unknown velocities must be what made it six"

    assert _confirmations(trace, at) == []
    assert detect(trace, at) == []


#: A 30-sample saccade at sample 200, whose run starts at 198 and has six measured velocities (198
#: to 203) before sample 206.
_THIRTY = [(200, 30, 12.0, 0.0)]


@pytest.mark.parametrize("lost, stop", [(24, 232), (25, 231), (200, 231)],
                         ids=["50 ms from the last measured sample to the next",
                              "52 ms", "400 ms"])
def test_a_run_is_carried_across_a_short_loss_and_ended_by_a_long_one(lost, stop):
    """**A lost stretch is bounded** (version 5; the PI, in wl-preproc's session of 2026-11-06,
    "Agree: bridge lost data": a saccade is carried across a short loss of data, counted and
    flagged). `lost` samples go missing from 206, inside `_THIRTY`'s run, after its sixth measured
    velocity. A stretch from the last measured sample, 205, to the next of `max_gap_s` or less
    carries the run, flagged, to where the eye is seen at rest: 25 samples on, 50 ms as this trace's
    clock writes it (`i / 500` s, which here rounds to 0.04999999999999999 s). A longer one ends it
    on the first sample past the bound, 231, 52 ms on, keeping the run so far since six of its
    velocities are measured; until then a stretch of any length carried it while the missing
    samples kept arriving, so 400 ms of nothing was one run. **Online it ends on the same sample**:
    the detector is in flight until the sample that completes the velocity at the batch form's
    stop, `stop + HALF_WINDOW`, and not after."""
    gaze, at = _trace(_THIRTY)
    trace = _lost(gaze, *range(206, 206 + lost))

    assert [(s.start, s.stop, s.flagged) for s in detect(trace, at)] == [(198, stop, True)]
    detector, flying = Detector(), []
    for t, g in zip(at, trace):
        detector.accept(t, g)
        flying.append(detector.in_flight)
    assert flying[stop + HALF_WINDOW - 1] and not flying[stop + HALF_WINDOW], \
        "online the run must end as the batch form ends it"
    assert not any(flying[stop + HALF_WINDOW:])


def test_a_lost_stretch_exactly_max_gap_s_long_carries_the_run():
    """**The bound is inclusive**, as the gap between two samples is: with `max_gap_s` the
    24-sample loss's own stretch as the clock writes it, from the last measured sample, 205, to the
    next, 230, the run is carried, batch and online, as with the default bound. On a clock of
    `i / 500` s no 25-sample stretch is exactly 0.05 s, so the default cannot show the boundary."""
    gaze, at = _trace(_THIRTY)
    trace = _lost(gaze, *range(206, 230))
    params = Params(max_gap_s=at[230] - at[205])

    assert [(s.start, s.stop, s.flagged) for s in detect(trace, at, params)] == [(198, 232, True)]
    detector, flying = Detector(params=params), []
    for t, g in zip(at, trace):
        detector.accept(t, g)
        flying.append(detector.in_flight)
    assert flying[232 + HALF_WINDOW - 1] and not flying[232 + HALF_WINDOW]


@pytest.mark.parametrize("ends", ["a break in time", "the trace's end"])
def test_a_run_a_gap_or_the_trace_ends_is_long_enough_only_by_its_measured_velocities(ends):
    """**The batch form's two other ways a run ends apply the rule too** (the review of
    2026-11-06, its I2): the noise velocity beside a lost sample (`_stepped`, sample 302 lost) whose
    run is ended by a 0.1 s hole in time at sample 306, or by the trace ending there, rather than
    by a velocity inside the threshold. One measured velocity, the rest unknown: no saccade, where
    version 2's rule, the run's length with its unknown velocities, made it (299, 306)."""
    gaze, at = _fixating()
    trace = _lost(_stepped(gaze), 302)
    if ends == "a break in time":
        at = [t + (0.1 if i >= 306 else 0.0) for i, t in enumerate(at)]
    else:
        trace, at = trace[:306], at[:306]
    velocities = velocity(trace, at, Params())
    eta = thresholds(velocities, Params())
    assert [k for k in range(290, 306) if velocities[k] is not None and _outside(velocities[k], *eta)] \
        == [299] and all(velocities[k] is None for k in range(300, 306)), \
        "one velocity outside the threshold, then unknown ones to where the run ends"

    assert detect(trace, at) == []


class _Pinned(Detector):
    """**The online detector with its thresholds held**, at `eta`: the batch form's, so the two
    forms' rule is compared apart from the online threshold, which is the trial's so far and
    differs from the whole trace's by design (S5 §5: per trial and adaptive)."""

    def __init__(self, eta: "tuple[float, float]") -> None:
        super().__init__()
        self.eta = eta

    def _refresh(self) -> None:
        self._eta_x, self._eta_y = self.eta


@pytest.mark.parametrize("seed", [20261104, 5, 9, 23, 28])
def test_every_run_is_confirmed_while_it_is_open(seed):
    """**Version 3 confirms a run only while it is open** (seeded): 200 saccades of 2 to 16
    samples, of random size and direction, each losing one to three samples from six before its
    onset to twelve into it. A run's measured velocities are counted as they come, so the one that
    makes six is outside the threshold and the run still open: every confirmation is made in
    flight. Version 2 confirmed some on the velocity that ends the run.

    **And online and batch apply one rule**: with the online thresholds held at the batch form's
    (`_Pinned`), the online detector reports exactly the saccades the batch form does, at the same
    starts. Left adaptive, the online threshold is the trial's so far, and a run near it can have
    six measured velocities outside one threshold and five outside the other: compared so, with
    starts within two samples, this held on the first seed and failed on four of these (the review
    of 2026-11-06, its M4; 53 of 12,200 traces over 61 seeds, against none held)."""
    rng = random.Random(seed)
    confirmed = 0
    for _ in range(200):
        onset = rng.randint(150, 300)
        gaze, at = _trace([(onset, rng.randint(2, 16), rng.uniform(1.0, 9.0), rng.uniform(-3.0, 3.0))],
                          n=480, seed=rng.randint(0, 10**6))
        lost = _lost(gaze, *{onset + rng.randint(-6, 12) for _ in range(rng.randint(1, 3))})
        found = _confirmations(lost, at)
        confirmed += len(found)
        assert all(flying for _, _, flying in found), (onset, found)
        held = _Pinned(thresholds(velocity(lost, at, Params()), Params()))
        assert [s.start for t, g in zip(at, lost) if (s := held.accept(t, g)) is not None] \
            == [s.start for s in detect(lost, at)], onset

    assert confirmed > 100


def test_the_detector_whose_no_number_gaze_reads_as_no_number_is_version_6():
    """`VERSION` is bumped whenever a session would detect something else: version 2 reports what
    version 1 never did, version 3 no longer reports a run whose minimum duration only unknown
    velocities met, version 4 detects and sizes in true visual angle (XC-398), version 5 ends a
    run at a lost stretch longer than `max_gap_s`, and version 6 makes a gaze sample that is no
    number NaN in every velocity reading it, as before version 4. **Not wl-preproc's fixture set
    "v2"**, which version 4 is pinned to: that is their file's version, and this constant is
    ours."""
    assert VERSION == 6


# ---------------------------------------------------------------------------
# Contract: wl-preproc's pinned fixtures
# ---------------------------------------------------------------------------
#
# **Vendored and versioned, not imported.** This section used to import wl-preproc's
# live `engbert_kliegl` and `velocity`, which meant the moment wl-preproc moved its
# detector to true visual angle (XC-398) this repository's main would have gone red
# for a change that is theirs to make, and ours to follow in our own commit. So
# wl-preproc publishes fixtures -- inputs and their detector's outputs -- by version,
# and a published version is never edited. Each copy is byte-identical and its SHA-256
# is asserted, so a copy that drifts fails rather than quietly redefining "theirs".
# Nothing here needs wl-preproc importable.
#
# **v2, the true-angle one, is the contract since version 4** (wl-preproc `82380d2`,
# `docs/fixtures/saccade/v2.json`, sent with its merge on 2026-11-06): v1's eight traces
# and its companion's two near-threshold ones, read from those files so the inputs are
# identical, and a 60-sample trace that tells the complete-window scale from v1's.
# **v1 is kept for its median-scale cases alone** (`docs/fixtures/saccade/v1.json`,
# `10ea913`), which v2 does not carry and which do not depend on geometry: its traces
# are per axis, which nothing here detects in any more. **Its thresholds companion
# (`v1-thresholds.json`, `065da53`) is retired** with version 4: it pinned per-axis
# thresholds and runs only, and v2 names its digest among the files it was derived from.

_FIXTURE = Path(__file__).parent / "fixtures" / "wl-preproc" / "saccade-v1.json"
_FIXTURE_SHA256 = "f94ea3a32521e7c5bdfb80040f10fe82303f76550296145b21fbeb94d9667666"
#: The thresholds companion's digest, vendored beside v1 until version 4.
_COMPANION_SHA256 = "f6da9801eb3f196b50ba546710b27816879acc46011ac117ff7ddbdeaad56e8e"

_V1 = json.loads(_FIXTURE.read_bytes())

_V2_FIXTURE = Path(__file__).parent / "fixtures" / "wl-preproc" / "saccade-v2.json"
_V2_SHA256 = "501e630945402b8064ea4a32708b8a20adba6d7ae90a3afd7209d96359c281c4"

_V2 = json.loads(_V2_FIXTURE.read_bytes())
_TRACES = {t["name"]: t for t in _V2["traces"]}
#: The traces whose inputs are v1's, each a single movement or two far from any other: the online
#: detector, its threshold the trial's so far, is held to their runs too. The near-threshold
#: movements and the short trace are the batch form's to hold, on the whole trace's threshold.
_FROM_V1 = [name for name, trace in _TRACES.items() if trace["inputs_from"] == "v1.json"]


def _ours_on(trace):
    """Our detector's input from a fixture trace. Ours takes no mask: a sample the
    tracker did not deliver is `None` in the gaze, which `velocity` and `detect`
    treat as unknown. Their `available` is `None` where a detector may label and the
    mask's name where it may not, so the mapping is exact: masked -> `None`."""
    gaze = [
        None if mask is not None else (float(x), float(y))
        for (x, y), mask in zip(trace["gaze_deg"], trace["available"] or [None] * len(trace["gaze_deg"]))
    ]
    at = [i / _V2["fs_hz"] for i in range(len(gaze))]
    return gaze, at


def _held(got: float, want: float) -> bool:
    """**v2's tolerance**, as its `about` states it: `|got - want| <= 1e-9 + 1e-12 * |want|`, in
    the number's own unit. Under true angle every number but an interval passes through `sin`,
    `cos` and `atan2`, which round differently in the last places across C libraries and forms of
    the direction, and a velocity component near zero is a cancelling difference."""
    return abs(got - want) <= 1e-9 + 1e-12 * abs(want)


def test_the_vendored_fixture_is_the_one_wl_preproc_published():
    assert hashlib.sha256(_FIXTURE.read_bytes()).hexdigest() == _FIXTURE_SHA256
    assert (_V1["version"], _V1["geometry"], _V1["fs_hz"]) == (1, "per-axis", 500.0)
    assert len(_V1["traces"]) == 8 and len(_V1["median_scale"]) == 6


def test_the_vendored_v2_is_the_one_wl_preproc_published():
    """Its digest, as wl-preproc sent it with the merge (2026-11-06), and the two files it was
    derived from, the v1 vendored here and the companion vendored here until version 4."""
    assert hashlib.sha256(_V2_FIXTURE.read_bytes()).hexdigest() == _V2_SHA256
    assert (_V2["version"], _V2["geometry"], _V2["fs_hz"]) == (2, "true-angle", 500.0)
    assert _V2["derived_from"] == {"v1.json": _FIXTURE_SHA256, "v1-thresholds.json": _COMPANION_SHA256}
    assert len(_TRACES) == 11 and len(_FROM_V1) == 8


def test_our_defaults_are_their_defaults():
    assert DEFAULT_LAMBDA == _V2["defaults"]["lambda"]
    assert DEFAULT_MIN_DURATION_SAMPLES == _V2["defaults"]["min_duration_samples"]
    assert Params().lambda_ == _V2["defaults"]["lambda"]
    assert Params().min_duration_samples == _V2["defaults"]["min_duration_samples"]


@pytest.mark.parametrize("case", _V1["median_scale"], ids=lambda c: c["name"])
def test_our_median_scale_is_theirs(case):
    assert median_scale(list(case["values"])) == pytest.approx(case["scale"], abs=1e-12)


@pytest.mark.parametrize("name", list(_TRACES))
def test_our_velocity_is_their_velocity_in_true_angle(name):
    """**In the local frame at each sample** (v2; version 4): the five samples' directions read
    about the centre sample's own, azimuthal-equidistant, then the five-point difference, so off
    centre it is the eye's angular velocity and per axis it was not. Ours derives `fs` from the
    window's own timestamps because the protocol is poll-based; on an evenly sampled trace that
    reduces to their fixed rate.

    Ours is `None` where the five-sample window is not fully present -- the two edge samples at
    each end, and any window touching a masked sample -- where theirs is 0.0 at the edges and,
    beside a mask, a number read across the gaze the mask threw. So: held to v2's tolerance
    wherever ours has an answer, `None` only where it should be, and their edges 0."""
    trace = _TRACES[name]
    gaze, at = _ours_on(trace)
    theirs_v = trace["velocity_deg_s"]
    mine = velocity(gaze, at, Params())
    n = len(gaze)
    assert len(theirs_v) == n
    answered = 0
    for i in range(n):
        window_present = 2 <= i < n - 2 and all(gaze[j] is not None for j in range(i - 2, i + 3))
        assert (mine[i] is not None) == window_present, f"sample {i}"
        if mine[i] is None:
            if i < 2 or i >= n - 2:
                assert theirs_v[i] == [0.0, 0.0], f"edge sample {i}"
            continue
        answered += 1
        assert _held(mine[i][0], theirs_v[i][0]) and _held(mine[i][1], theirs_v[i][1]), \
            (i, mine[i], theirs_v[i])
    assert answered > n // 2


@pytest.mark.parametrize("name", list(_TRACES))
def test_our_thresholds_are_theirs_in_true_angle(name):
    """**Over complete windows only**, on both sides since v2 (its spec §6.1): `thresholds` over
    our velocities, which are `None` wherever a window is incomplete, against their `eta_deg_s`,
    held to v2's tolerance. Per axis theirs took every unmasked sample, zero-filled edges
    included, and ours stood 0.04-2.4% from it; the short trace's two differ from v1's rule by 9%
    and 21%."""
    gaze, at = _ours_on(_TRACES[name])
    mine = thresholds(velocity(gaze, at, Params()), Params())
    eta = _TRACES[name]["eta_deg_s"]

    assert _held(mine[0], eta[0]) and _held(mine[1], eta[1]), (mine, eta)


@pytest.mark.parametrize("name", list(_TRACES))
def test_our_detector_finds_the_intervals_theirs_finds_in_true_angle(name):
    """The claim S5 §5 rests on, exactly: intervals are held exactly in v2. The blink trace is run
    with its masked samples as `None` gaze (see `_ours_on`); the detector must still find both
    saccades on either side of the blink and none inside it. The near-threshold traces' runs are
    the ones lambda +/-5% or the ellipse's limit at 1.1 moves, and not every movement in them is
    detected; the short trace has none."""
    trace = _TRACES[name]
    gaze, at = _ours_on(trace)

    assert [(s.start, s.stop) for s in detect(gaze, at)] \
        == [(r["start"], r["stop"]) for r in trace["runs"]]


@pytest.mark.parametrize("name", [n for n in _TRACES if _TRACES[n]["runs"]])
def test_our_size_is_theirs_in_true_angle(name):
    """**Size is the true angle between the run's first and last samples' directions** (v2),
    `geometry.separation_deg`, held to v2's tolerance: 2° up from (20°, 0°) is 1.86° here, where
    per axis it was the 2° step's `hypot`."""
    trace = _TRACES[name]
    gaze, at = _ours_on(trace)
    found = detect(gaze, at)

    assert len(found) == len(trace["runs"])
    for saccade, run in zip(found, trace["runs"]):
        assert _held(saccade.amplitude_deg, run["amplitude_deg"]), (saccade, run)


@pytest.mark.parametrize("name", [n for n in _TRACES if _TRACES[n]["runs"]])
def test_our_size_splits_their_runs_at_their_microsaccade_cut(name):
    """**The 1° microsaccade cut, read in true angle.** Labelling is offline analysis, which ours
    does not do -- no task guard needs it, and `Saccade` has no label -- but the cut reads the
    size, so ours must put each of their runs on the side of `microsaccade_max_deg` their label
    does, at or above it a saccade. 1.12° up from (30°, 0°) is 0.98° of true angle, a
    microsaccade, which per axis read 1.12°, a saccade."""
    trace = _TRACES[name]
    gaze, at = _ours_on(trace)
    cut = _V2["defaults"]["microsaccade_max_deg"]

    assert ["saccade" if s.amplitude_deg >= cut else "microsaccade" for s in detect(gaze, at)] \
        == [r["label"] for r in trace["runs"]]


@pytest.mark.parametrize("name", _FROM_V1)
def test_online_each_of_their_runs_is_confirmed_on_its_sixth_velocity_and_nothing_else(name):
    """**What version 2 leaves alone, sample for sample.** On each trace of v1's inputs, nothing
    missing near a run, the online detector reports exactly their runs, each at their start,
    unflagged, on the sample that completes its sixth velocity, `start + min_duration_samples +
    HALF_WINDOW - 1`, as version 1 did: confirming a run once it is long enough rather than
    exactly so moves nothing where no velocity in it is unknown. In true angle since version 4."""
    gaze, at = _ours_on(_TRACES[name])
    runs = _TRACES[name]["runs"]

    assert [(k, s.start, s.stop, s.flagged) for k, s, _ in _confirmations(gaze, at)] == [
        (r["start"] + DEFAULT_MIN_DURATION_SAMPLES + HALF_WINDOW - 1, r["start"],
         r["start"] + DEFAULT_MIN_DURATION_SAMPLES, False) for r in runs]


_LOST_IN_A_RUN = [(name, index, into) for name in _FROM_V1
                  for index in range(len(_TRACES[name]["runs"])) for into in range(3, 8)]


@pytest.mark.parametrize("name,index,into", _LOST_IN_A_RUN,
                         ids=[f"{n}-run{i}-lost+{k}" for n, i, k in _LOST_IN_A_RUN])
def test_online_a_run_that_lost_a_sample_near_its_start_is_found_where_theirs_is_marked(
        name, index, into):
    """**Live and offline agree** (the PI, 2026-10-30 and 2026-11-04). Their run, on the trace the
    eye PC recorded, against ours on the same trace with one sample the rig's stream lost, 3 to 7
    samples into the run: each hides the velocity a whole trace confirms it on, and version 1
    reported nothing there. Every one of their runs that keeps six measured velocities with the
    sample lost is found at their start, the one that lost a sample flagged and the rest not, and
    the batch form finds the same. **One that keeps fewer is found by neither** (version 3,
    "Require measured samples"): the off-centre traces' runs, 10 velocities, and the
    microsaccade's, 9, keep five or four, the lost sample leaving five unknown inside them, where
    version 2 found each, flagged.

    The offline side is their run on the whole trace because the eye PC's file keeps the frame the
    rig's stream lost (S5 §3, the XC-288 spec §3.3). A frame missing from that file too is masked
    there with its neighbours, and their detector ends a run at a masked sample where ours carries
    it across: with their default validity mask, `_TWELVE`'s saccade with a sample lost 3 to 12
    into its run is not found offline at all (measured 2026-10-30). Their rule against ours, older
    than this change."""
    trace = _TRACES[name]
    gaze, at = _ours_on(trace)
    runs = trace["runs"]
    lost = _lost(gaze, runs[index]["start"] + into)
    velocities = velocity(lost, at, Params())
    kept = [i for i, r in enumerate(runs) if i != index or sum(
        v is not None for v in velocities[r["start"]:r["stop"]]) >= DEFAULT_MIN_DURATION_SAMPLES]

    found = _confirmations(lost, at)

    assert [s.start for _, s, _ in found] == [runs[i]["start"] for i in kept] \
        == [s.start for s in detect(lost, at)]
    assert [s.flagged for _, s, _ in found] == [i == index for i in kept]


def test_in_flight_tracks_the_open_run_not_the_confirmation():
    """`gaze.Tracked` uses this to decide when the eye has landed, so it has to mean
    'a supra-threshold run is open', not 'a saccade was recently confirmed'. A
    saccade is confirmed part-way through its own flight, and asking the wrong
    question would let `SaccadeTo` report a landing while the eye was still moving."""
    gaze, at = _trace([(200, 20, 9.0, 0.0)], n=500)
    detector = Detector()

    during, after = [], []
    for i, (t, g) in enumerate(zip(at, gaze)):
        detector.accept(t, g)
        if 210 <= i <= 218:
            during.append(detector.in_flight)
        if 260 <= i <= 280:
            after.append(detector.in_flight)

    assert any(during), "in_flight must be true while the eye is moving"
    assert not any(after), "in_flight must be false once the eye has landed"


def test_in_flight_is_false_on_a_still_eye():
    gaze, at = _trace([], n=400)
    detector = Detector()
    for t, g in zip(at, gaze):
        detector.accept(t, g)
    assert not detector.in_flight


# ---------------------------------------------------------------------------
# In a trial: a guard waiting for a saccade takes one that lost a sample
# ---------------------------------------------------------------------------
#
# Through the trial loop, a replayed tracker, the map and `gaze.Tracked`, which feeds the detector
# one sample a frame. **The tracker's staleness ceiling is half a frame here**, so a datagram that
# never arrived is a frame with no gaze, which the detector is given as a lost sample; under the
# default 50 ms ceiling the tracker keeps the last sample over one lost datagram, and the detector
# is given that sample again instead. One frame without gaze is inside the trial's 50 ms
# tracker-loss grace, which only freezes the frame.

_FRAME = 0.002

#: An eye whose map is the identity: P1 at the gaze in degrees and P4 at the origin, so a payload
#: states where the animal looks.
_IDENTITY = EyeMap(model=Model.AFFINE, x=(0.0, 1.0, 0.0), y=(0.0, 0.0, 1.0), conditioning=1.0,
                   rms_residual_deg=0.0, n_points=3)

_RESPOND = Trial(
    start="respond",
    windows=[Window("target", at=(8.0, 0.0), radius=2.0, on=REMEMBERED),
             Window("other", at=(-8.0, 0.0), radius=2.0, on=REMEMBERED)],
    states=[State("respond", go=[On(SaccadeTo("target"), Outcome.CORRECT),
                                 On(SaccadeTo("other"), Outcome.WRONG_TARGET),
                                 On(After(1.0), Outcome.NO_RESPONSE)])],
)


def _datagram(x: float, y: float, frame: int) -> str:
    """What OpenIrisDPI sends for both eyes looking at `(x, y)` under `_IDENTITY`."""
    eye = {"FrameNumber": frame,
           "Pupil": {"Center": {"X": x, "Y": y}, "Size": {"Width": 30.0, "Height": 28.0}},
           "CRs": [{"X": x, "Y": y}, {"X": 0.0, "Y": 0.0}, {"X": 0.0, "Y": 0.0}, {"X": 0.0, "Y": 0.0}]}
    return json.dumps({"Left": eye, "Right": eye})


def _responded(to_x: float, lose=()):
    """`_RESPOND` through the loop, the eye fixating the origin for 200 frames and then making
    `_TWELVE`'s saccade to `(to_x, 0)`, each sample in `lose` a datagram that never arrived: the
    result, and every saccade the detector confirmed."""
    result, confirmed, _ = _responded_with(to_x, {k: "" for k in lose})
    return result, confirmed


def _responded_with(to_x: float, sent: dict):
    """`_responded`, each datagram `k` in `sent` replaced by `sent[k]`: the result, every saccade
    the detector confirmed, and the tracker, which counts what it received and dropped."""
    gaze, _ = _trace([(200, 12, to_x, 0.0)], n=800)
    payloads = [(0.0, sent[k] if k in sent else _datagram(x, y, k)) for k, (x, y) in enumerate(gaze)]
    detector, confirmed = Detector(), []
    accept = detector.accept

    def keeping(at, gaze_deg):
        saccade = accept(at, gaze_deg)
        if saccade is not None:
            confirmed.append(saccade)
        return saccade

    detector.accept = keeping
    tracker = Tracker(staleness=_FRAME / 2)
    world = Tracked(tracker, Mapping(version=1, targets=(), left=_IDENTITY, right=_IDENTITY),
                    _RESPOND, _FRAME, {}, source=Replay(payloads=payloads), detector=detector)
    return run_trial(_RESPOND, world, _FRAME, values={}, effects=Recorded()), confirmed, tracker


def _left_eye_at(x: float, y: float, frame: int, p1_x: float) -> str:
    """`_datagram`, the left eye's first Purkinje image read at `p1_x` across: what the tracker
    would send with one eye's position no number, as `json.dumps` writes a float that is none,
    a bare `Infinity`, `-Infinity` or `NaN`, which Python's `json.loads` accepts."""
    datagram = json.loads(_datagram(x, y, frame))
    datagram["Left"]["CRs"][0]["X"] = p1_x
    return json.dumps(datagram)


@pytest.mark.parametrize("value", [math.inf, -math.inf, math.nan],
                         ids=["Infinity", "-Infinity", "NaN"])
def test_a_datagram_whose_gaze_is_no_finite_number_is_a_lost_sample(value):
    """**A gaze value that is not finite is a lost sample** (the controller's ruling of 2026-11-06,
    on the definitions the PI agreed that day in wl-preproc's session: "Lost: no measurement, or
    none to trust ... a value that is not a number"). The left eye's first Purkinje image reads
    `value` in the datagram five samples into `_TWELVE`'s saccade to the target: the trial runs on,
    the tracker counts the datagram dropped, and the trial ends, and its saccade is confirmed and
    flagged, exactly as with that datagram missing. Until then `Infinity` raised in the true-angle
    arithmetic mid-session, and `NaN` was taken as a sample."""
    _, kept = _responded(8.0)
    bad = kept[0].start + 5
    gaze, _ = _trace([(200, 12, 8.0, 0.0)], n=800)
    missing, missed, lost = _responded_with(8.0, {bad: ""})
    assert missing.outcome is Outcome.CORRECT and lost.dropped == 1

    result, confirmed, tracker = _responded_with(
        8.0, {bad: _left_eye_at(gaze[bad][0], gaze[bad][1], bad, value)})

    assert (result.outcome, result.frames) == (missing.outcome, missing.frames)
    assert [(s.start, s.stop, s.flagged) for s in confirmed] \
        == [(s.start, s.stop, s.flagged) for s in missed]
    assert (tracker.received, tracker.dropped) == (lost.received, lost.dropped)


@pytest.mark.parametrize("to_x,outcome", [(8.0, Outcome.CORRECT), (-8.0, Outcome.WRONG_TARGET)],
                         ids=["to the target", "to the other window"])
def test_a_trial_waiting_for_a_saccade_takes_one_that_lost_a_sample_near_its_start(to_x, outcome):
    """The PI, 2026-10-30: "It counts for a task's saccade guard like any saccade." A saccade whose
    fifth sample never arrived ended its trial `NO_RESPONSE` under version 1, the detector never
    reporting it; now the trial ends as the whole saccade ends it, by where it landed, and the
    saccade the guard took is the one the detector confirmed, flagged. The trial record holds no
    saccade yet (build T, XC-400), so that flag is the mark it carries."""
    whole, kept = _responded(to_x)
    assert whole.outcome is outcome and [s.flagged for s in kept] == [False]

    result, confirmed = _responded(to_x, lose={kept[0].start + 5})

    assert result.outcome is outcome
    assert [(s.start, s.flagged) for s in confirmed] == [(kept[0].start, True)]


def test_a_reading_whose_degrees_overflow_is_no_position_for_that_eye():
    """**A finite datagram whose conversion is not finite** does not raise either: the left eye's
    Purkinje images read 1e308 and -1e308 across five samples into the saccade, finite, so `parse`
    keeps the datagram, but their difference overflows to infinity. That eye has no position on
    that frame (`gaze.Tracked.gaze`, as for an eye with no map), the right eye stands for gaze, and
    the trial runs on and ends as it does whole, the datagram received. Until then the infinity
    reached the true-angle arithmetic and raised."""
    whole, kept = _responded(8.0)
    bad = kept[0].start + 5
    gaze, _ = _trace([(200, 12, 8.0, 0.0)], n=800)
    datagram = json.loads(_datagram(gaze[bad][0], gaze[bad][1], bad))
    datagram["Left"]["CRs"][0]["X"] = 1e308
    datagram["Left"]["CRs"][3]["X"] = -1e308

    result, confirmed, tracker = _responded_with(8.0, {bad: json.dumps(datagram)})

    assert (result.outcome, result.frames) == (whole.outcome, whole.frames)
    assert [(s.start, s.flagged) for s in confirmed] == [(s.start, s.flagged) for s in kept]
    assert tracker.dropped == 0


#: **A catch trial**: any saccade in its second is an early response, and none a correct reject.
_CATCH = Trial(start="hold", windows=[], states=[
    State("hold", go=[On(SaccadeOnset(), Outcome.EARLY_RESPONSE),
                      On(After(1.0), Outcome.CORRECT_REJECT)]),
])


@pytest.mark.parametrize("lose", [(), (302,)], ids=["whole", "sample 302 lost"])
def test_a_catch_trial_is_not_ended_early_by_a_lost_sample_beside_a_noise_velocity(lose):
    """**The review's probe 10, through the trial loop**: the eye never makes a saccade --
    fixation noise and a 0.12° step at sample 300 -- and datagram 302 never arrives. Version 2
    counted the unknown velocities the lost sample left, so the catch trial ended `EARLY_RESPONSE`
    at frame 308 though no saccade was made; version 3 counts only measured ones (the PI,
    2026-11-04), and it is a correct reject, as it is whole."""
    gaze, _ = _fixating()
    payloads = [(0.0, "" if k in lose else _datagram(x, y, k))
                for k, (x, y) in enumerate(_stepped(gaze))]
    world = Tracked(Tracker(staleness=_FRAME / 2),
                    Mapping(version=1, targets=(), left=_IDENTITY, right=_IDENTITY), _CATCH,
                    _FRAME, {}, source=Replay(payloads=payloads))

    result = run_trial(_CATCH, world, _FRAME, values={}, effects=Recorded())

    assert (result.outcome, result.frames) == (Outcome.CORRECT_REJECT, 500)
