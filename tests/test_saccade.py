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

from wl_xcon.saccade import (
    DEFAULT_LAMBDA,
    DEFAULT_MIN_DURATION_SAMPLES,
    VERSION,
    Detector,
    Params,
    detect,
    median_scale,
    thresholds,
    velocity,
)

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
    online detector measures them in its own buffer (XC-414), and the batch form's `_amplitude`
    over the same samples of the trace gives the same number, bit for bit."""
    from wl_xcon.saccade import _amplitude

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
_BUFFERS = ("_x", "_y", "_t", "_present", "_vx", "_vy", "_sorting")


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
    lose two samples, cross an 0.2 s hole in time, and confirm saccades on both sides of it."""
    gaze, at = _trace([(200, 10, 8.0, 0.0), (450, 12, -7.0, 3.0), (800, 15, 5.0, 5.0)], n=n)
    gaze[:120] = [(0.0, 0.0)] * 120
    gaze[300] = gaze[700] = None
    at = [t + (0.2 if i >= 600 else 0.0) for i, t in enumerate(at)]
    return gaze, at


def test_a_sample_builds_nothing_whatever_it_does():
    """**On the trial loop's path**, a sample a frame (`gaze.Tracked.display`), so accepting one
    builds nothing (XC-414), on every sample of `_demanding`'s trace, with a history short enough
    that its buffers wrap and its thresholds refreshed every seventh velocity: no list, slice,
    generator or tuple, where until 2026-10-29 every sample appended to three growing lists, sliced
    two, walked them with generators, and every refresh copied its velocities into a list."""
    from _builds import built_on

    gaze, at = _demanding()
    detector = Detector(history=60, refresh_every=7)
    built, confirmed = set(), []
    for t, g in zip(at, gaze):
        built.update(built_on(detector.accept, t, g))
        if detector.onset is not None:
            confirmed.append(detector.onset)

    assert [s.start for s in confirmed if s.start > 600] and len(confirmed) >= 3
    assert sorted(built) == []


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
# Contract: wl-preproc's pinned fixtures
# ---------------------------------------------------------------------------
#
# **Vendored and versioned, not imported.** This section used to import wl-preproc's
# live `engbert_kliegl` and `velocity`, which meant the moment wl-preproc moved its
# detector to true visual angle (XC-398) this repository's main would have gone red
# for a change that is theirs to make, and ours to follow in our own commit. So
# wl-preproc publishes fixtures -- inputs and their detector's outputs -- by version,
# and a published version is never edited: v1 pins today's per-axis behavior
# (wl-preproc `10ea913`, `docs/fixtures/saccade/v1.json`). v2, the true-angle one, is
# pinned in the commit that moves `saccade.py` to true angle (XC-398), beside v1 until
# nothing here needs v1 any more. The copy is byte-identical and its SHA-256 is
# asserted, so a copy that drifts fails rather than quietly redefining "theirs".
# Nothing here needs wl-preproc importable.

_FIXTURE = Path(__file__).parent / "fixtures" / "wl-preproc" / "saccade-v1.json"
_FIXTURE_SHA256 = "f94ea3a32521e7c5bdfb80040f10fe82303f76550296145b21fbeb94d9667666"

_V1 = json.loads(_FIXTURE.read_bytes())
_TRACES = {t["name"]: t for t in _V1["traces"]}


def _ours_on(trace):
    """Our detector's input from a fixture trace. Ours takes no mask: a sample the
    tracker did not deliver is `None` in the gaze, which `velocity` and `detect`
    treat as unknown. Their `available` is `None` where a detector may label and the
    mask's name where it may not, so the mapping is exact: masked -> `None`."""
    gaze = [
        None if mask is not None else (float(x), float(y))
        for (x, y), mask in zip(trace["gaze_deg"], trace["available"] or [None] * len(trace["gaze_deg"]))
    ]
    at = [i / _V1["fs_hz"] for i in range(len(gaze))]
    return gaze, at


def test_the_vendored_fixture_is_the_one_wl_preproc_published():
    assert hashlib.sha256(_FIXTURE.read_bytes()).hexdigest() == _FIXTURE_SHA256
    assert (_V1["version"], _V1["geometry"], _V1["fs_hz"]) == (1, "per-axis", 500.0)
    assert len(_V1["traces"]) == 8 and len(_V1["median_scale"]) == 6


def test_our_defaults_are_their_defaults():
    assert DEFAULT_LAMBDA == _V1["defaults"]["lambda"]
    assert DEFAULT_MIN_DURATION_SAMPLES == _V1["defaults"]["min_duration_samples"]
    assert Params().lambda_ == _V1["defaults"]["lambda"]
    assert Params().min_duration_samples == _V1["defaults"]["min_duration_samples"]


@pytest.mark.parametrize("case", _V1["median_scale"], ids=lambda c: c["name"])
def test_our_median_scale_is_theirs(case):
    assert median_scale(list(case["values"])) == pytest.approx(case["scale"], abs=1e-12)


@pytest.mark.parametrize("name", list(_TRACES))
def test_our_velocity_is_their_velocity(name):
    """Ours derives `fs` from the window's own timestamps because the protocol is
    poll-based; on an evenly sampled trace that must reduce to their fixed-rate
    estimator, or the two detectors are differentiating differently and every
    comparison between them is partly about smoothing.

    Ours is `None` where the five-sample window is not fully present -- the two edge
    samples at each end, and any window touching a masked sample -- where theirs is
    0.0 at the edges (an array has to hold something). So: equal to rel 1e-9 wherever
    ours has an answer, `None` only where it should be, and their edge values are 0."""
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
        assert mine[i][0] == pytest.approx(theirs_v[i][0], rel=1e-9)
        assert mine[i][1] == pytest.approx(theirs_v[i][1], rel=1e-9)
    assert answered > n // 2


@pytest.mark.parametrize("name", list(_TRACES))
def test_our_detector_finds_the_intervals_theirs_finds(name):
    """The claim S5 §5 rests on. Their detector labels by amplitude and ours does not
    -- labelling is offline analysis, not something a task guard needs -- so the
    contract is over the intervals, which is the detection itself. Their `label` is
    not compared for that reason.

    The blink trace is run with its masked samples as `None` gaze (see `_ours_on`);
    the detector must still find both saccades on either side of the blink and none
    inside it."""
    trace = _TRACES[name]
    gaze, at = _ours_on(trace)
    mine = detect(gaze, at)
    expected = [(r["start"], r["stop"]) for r in trace["runs"]]
    assert expected, "a fixture trace with no run would prove nothing"
    assert [(s.start, s.stop) for s in mine] == expected


@pytest.mark.parametrize("name", list(_TRACES))
def test_our_amplitude_is_their_amplitude(name):
    """Per-axis today, so these are the same start-to-end distance. **Not bit-exact:**
    on two traces ours is 1 ulp from theirs (`math.hypot` against `np.hypot`), so this
    allows 4 ulp and no more -- far below anything a threshold or a label can see."""
    trace = _TRACES[name]
    gaze, at = _ours_on(trace)
    mine = detect(gaze, at)
    for found, run in zip(mine, trace["runs"]):
        assert abs(found.amplitude_deg - run["amplitude_deg"]) <= 4 * math.ulp(run["amplitude_deg"])


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
# Contract: the thresholds companion
# ---------------------------------------------------------------------------
#
# wl-preproc `065da53`, `docs/fixtures/saccade/v1-thresholds.json`, frozen beside v1 and
# vendored the same way (byte-identical, SHA-256 pinned, and pinned to the v1 file it
# accompanies). **What it pins that v1's traces do not:** v1's runs are far enough from
# the ellipse that lambda and the ellipse's limit can drift a little without changing
# one. The companion gives each v1 trace's thresholds (`eta_deg_s`), and two
# near-threshold traces whose movements sit 0.95-1.6x the ellipse-crossing speed, on
# which lambda off by 5% either way, or the limit at 1.1 or 1.5, changes the runs.
#
# **The two definitions of eta differ, and this is deliberate here.** Theirs is
# lambda * median_scale over the velocity at every sample the mask leaves usable,
# including the two zero-filled samples at each edge and any window touching a masked
# sample. Ours drops incomplete windows (they are `None`), so ours moves by about
# 0.1-0.2% on the 1200-sample traces (up to 2.4% on v1's 400-sample ones) and changes no run. Hence two checks: ours against `eta_deg_s` at rel 3e-3,
# and theirs recomputed from the fixture's own velocities, with `median_scale`, to 1e-12.
# Which one is meant is for the XC-398 spec to settle; until then this pins the runs
# exactly and the thresholds both ways.

_COMPANION = Path(__file__).parent / "fixtures" / "wl-preproc" / "saccade-v1-thresholds.json"
_COMPANION_SHA256 = "f6da9801eb3f196b50ba546710b27816879acc46011ac117ff7ddbdeaad56e8e"

_TH = json.loads(_COMPANION.read_bytes())
_NEAR = {t["name"]: t for t in _TH["near_threshold_traces"]}
_ETA_CASES = [(n, _TRACES[n], e["eta_deg_s"]) for n, e in ((e["name"], e) for e in _TH["v1_traces"])]
_ETA_CASES += [(n, t, t["eta_deg_s"]) for n, t in _NEAR.items()]


def test_the_vendored_companion_is_the_one_wl_preproc_published():
    assert hashlib.sha256(_COMPANION.read_bytes()).hexdigest() == _COMPANION_SHA256
    assert _TH["companion_to"]["sha256"] == _FIXTURE_SHA256
    assert (_TH["version"], _TH["geometry"]) == (1, "per-axis")
    assert _TH["companion_to"]["file"] == "v1.json"
    assert [e["name"] for e in _TH["v1_traces"]] == list(_TRACES)
    assert list(_NEAR) == ["near-threshold-horizontal", "near-threshold-oblique"]
    for t in _NEAR.values():
        assert len(t["gaze_deg"]) == 1200 and len(t["runs"]) == 3


@pytest.mark.parametrize("name", list(_NEAR))
def test_near_threshold_velocity_is_their_velocity(name):
    trace = _NEAR[name]
    gaze, at = _ours_on(trace)
    mine = velocity(gaze, at, Params())
    n = len(gaze)
    answered = 0
    for i in range(n):
        window_present = 2 <= i < n - 2 and all(gaze[j] is not None for j in range(i - 2, i + 3))
        assert (mine[i] is not None) == window_present, f"sample {i}"
        if mine[i] is None:
            continue
        answered += 1
        assert mine[i][0] == pytest.approx(trace["velocity_deg_s"][i][0], rel=1e-9)
        assert mine[i][1] == pytest.approx(trace["velocity_deg_s"][i][1], rel=1e-9)
    assert answered > n // 2


@pytest.mark.parametrize("name", list(_NEAR))
def test_our_detector_finds_the_near_threshold_intervals_exactly(name):
    """Exactly, not approximately: these runs are the ones lambda +/-5% or the ellipse's
    limit at 1.1 moves, so an exact match is what makes a drifted constant fail."""
    trace = _NEAR[name]
    gaze, at = _ours_on(trace)
    expected = [(r["start"], r["stop"]) for r in trace["runs"]]
    assert [(s.start, s.stop) for s in detect(gaze, at)] == expected


@pytest.mark.parametrize("name,trace,eta", _ETA_CASES, ids=[c[0] for c in _ETA_CASES])
def test_our_thresholds_are_theirs_within_the_window_rule(name, trace, eta):
    """Ours (`thresholds` over our velocities, incomplete windows excluded) against their
    `eta_deg_s`. The difference is the dropped edge and masked windows, so it scales with
    their share of the trace: measured 0.04-0.2% on the 1200-sample near-threshold traces
    (bound rel 3e-3, as wl-preproc suggested) but up to 2.4% on v1's 400-sample traces,
    where the four zero-filled edge samples are 1% of the usable set and move the median.
    Bound rel 3e-2 there. Still far inside the 5% that moves a run."""
    gaze, at = _ours_on(trace)
    mine = thresholds(velocity(gaze, at, Params()), Params())
    rel = 3e-3 if len(gaze) >= 1200 else 3e-2
    assert mine[0] == pytest.approx(eta[0], rel=rel)
    assert mine[1] == pytest.approx(eta[1], rel=rel)


@pytest.mark.parametrize("name,trace,eta", _ETA_CASES, ids=[c[0] for c in _ETA_CASES])
def test_their_thresholds_follow_their_stated_rule(name, trace, eta):
    """Their rule, built here from the fixture's own velocities and mask: lambda times
    `median_scale` over every unmasked sample, zero-filled edges included. Our
    `median_scale` and `DEFAULT_LAMBDA` must reproduce their `eta_deg_s` to 1e-12."""
    available = trace["available"] or [None] * len(trace["velocity_deg_s"])
    usable = [v for v, mask in zip(trace["velocity_deg_s"], available) if mask is None]
    for axis in (0, 1):
        rebuilt = DEFAULT_LAMBDA * median_scale([float(v[axis]) for v in usable])
        assert rebuilt == pytest.approx(eta[axis], rel=1e-12)
