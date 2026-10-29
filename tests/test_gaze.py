"""Replayed OpenIrisDPI samples reaching a `Window` test in degrees.

This is P6's exit condition, and the reason it is one test file rather than three:
`eye` parsing correctly, `calibration` fitting correctly and `run` looping correctly
were each already true separately, and none of that proves an animal's gaze reaches a
criterion. The path has four joints and every one of them is somewhere a sign, a unit
or a clock can be wrong without any single module being wrong.
"""

from __future__ import annotations

import json
import math
import os
import random
from dataclasses import replace

import pytest

from _rig import DIRECT
from wl_xcon.calibration import (
    Collector,
    conditions,
    EyeMap,
    Fixation,
    Mapping,
    MappingLog,
    Model,
    constellation,
    fit_eye,
)
from wl_xcon.bounds import Bounds, Ceiling, Floor
from wl_xcon.dio import Simulated as Card
from wl_xcon.eye import Replay, Tracker, parse
from wl_xcon.findings import NOT_RECORDING, Finding
from wl_xcon.gaze import Calibrating, Tracked
from wl_xcon.geometry import Geometry
from wl_xcon.photometry import SRGB
from wl_xcon.run import Recorded, run_trial
from wl_xcon.scheduler import Block, Scheduler
from wl_xcon.taskd import Session, SessionSpec
from wl_xcon.welfare import Deployment, Simulated as Pump
from wl_xcon.task import Outcome, SaccadeOnset, SaccadeTo
from tasks.calibration import calibration
from wl_xcon import screen
from wl_xcon.photometry import Gray
from wl_xcon.task import (After, Array, Blank, Disc, Entered, Exited, Hide, Hold, ObjectWindows,
                          On, P, Polar, Show, State, Stimulus, Trial, Update)

GEOMETRY = Geometry.stereoscope(
    panel_width_cm=58.997, panel_height_cm=33.293, screen_distance_cm=50.0, half_ipd_cm=1.6
)


def _targets() -> tuple[tuple[float, float], ...]:
    """The calibration constellation, computed when a test asks rather than at import.

    It was a module constant, `TARGETS = constellation(GEOMETRY)`. That ran at
    collection, so a broken `geometry` property aborted the whole suite with a
    collection error and no test ran -- and the mutation harness read that exit as a
    catch (`docs/CHECKPOINT.md`, 2026-09-20 sweep). Called here, the same breakage fails
    the tests that use it, and `tests/test_geometry.py` asserts each property itself.
    """
    return constellation(GEOMETRY)

#: Their reader, or a refusal. **`importorskip` is wrong here**: a contract test that is
#: allowed not to run is not a contract test, and the whole point of writing this file is
#: that *they* accept it. So a missing checkout skips locally and **fails** under
#: `WLX_REQUIRE_PREPROC=1`, which is what CI sets. Same guard as `test_calibration.py`.
_REQUIRED = os.environ.get("WLX_REQUIRE_PREPROC") == "1"
try:
    from wl_preproc.eye.xcon import read_xcon_map as _read_their_map
except ImportError as exc:  # pragma: no cover - exercised by the CI job
    if _REQUIRED:
        raise AssertionError(
            f"WLX_REQUIRE_PREPROC=1 but wl-preproc is not importable ({exc}). The "
            f"session's calibration file is only useful if their reader accepts it, "
            f"and skipping that check reports a compatibility nobody verified"
        ) from exc
    _read_their_map = None

_contract = pytest.mark.skipif(
    _read_their_map is None,
    reason="wl-preproc checkout not beside this repo; the contract cannot run",
)

#: A camera whose raw vector is a plain affine function of gaze, so a test can state
#: where the animal is looking in degrees and know what the tracker would report.
#: Deliberately affine and not the design tool's optics: this exercises the join, not
#: the physics, and a second copy of the physics here would drift from that one.
_SCALE_X, _SCALE_Y = 4.0, -3.5
_ORIGIN_X, _ORIGIN_Y = 300.0, 230.0


def _raw_for(x_deg: float, y_deg: float) -> tuple[float, float]:
    return (_ORIGIN_X + _SCALE_X * x_deg, _ORIGIN_Y + _SCALE_Y * y_deg)


def _payload(x_deg: float, y_deg: float, frame: int = 1) -> str:
    """What OpenIrisDPI would emit for an animal looking there.

    P1 carries the signal and P4 sits at a fixed offset, so `dpi()` -- their
    difference -- is `_raw_for` exactly. Building the payload rather than the
    `Sample` keeps the parser in the path: a unit or an index error in `eye.parse`
    is precisely the sort of thing this test exists to catch.
    """
    p1x, p1y = _raw_for(x_deg, y_deg)
    p4x, p4y = 0.0, 0.0
    eye = {
        "FrameNumber": frame,
        "Pupil": {"Center": {"X": p1x, "Y": p1y}, "Size": {"Width": 30.0, "Height": 28.0}},
        "CRs": [
            {"X": p1x, "Y": p1y},
            {"X": 0.0, "Y": 0.0},
            {"X": 0.0, "Y": 0.0},
            {"X": p4x, "Y": p4y},
        ],
    }
    return json.dumps({"Left": eye, "Right": dict(eye)})


def _fitted_mapping(version: int = 1) -> Mapping:
    """A map fit from the reference constellation, through the real fit."""
    fixations = tuple(
        Fixation(raw=_raw_for(x, y), target=(x, y)) for x, y in _targets()
    )
    eye_map, findings = fit_eye(fixations)
    assert eye_map is not None and not [f for f in findings if f.blocking]
    return Mapping(version=version, targets=_targets(), left=eye_map, right=eye_map)


def _tracker_at(x_deg: float, y_deg: float, at: float = 0.0) -> Tracker:
    tracker = Tracker()
    tracker.accept(parse(_payload(x_deg, y_deg), at=at))
    return tracker


# ---------------------------------------------------------------------------
# The path, joint by joint
# ---------------------------------------------------------------------------


def test_a_replayed_payload_becomes_degrees():
    """Parser, `dpi()`, fit and map, in one line. An affine camera is recoverable
    exactly, so anything but an exact answer is a defect rather than noise."""
    mapping = _fitted_mapping()
    world = Tracked(_tracker_at(6.0, -4.0), mapping, calibration, frame_period=0.008)

    assert world.gaze("left", frame=0) == pytest.approx((6.0, -4.0), abs=1e-6)
    assert world.gaze("right", frame=0) == pytest.approx((6.0, -4.0), abs=1e-6)


def test_gaze_in_degrees_decides_a_window():
    values = {"target_x": 6.0, "target_y": -4.0, "cal_window": 2.0,
              "fix_acquisition": 3.0, "cal_hold": 0.2}
    mapping = _fitted_mapping()

    inside = Tracked(_tracker_at(6.0, -4.0), mapping, calibration, 0.008, values)
    assert inside.in_window("cal", frame=0)

    # Just outside the 2 deg radius, on the diagonal: 2.5 deg away.
    outside = Tracked(_tracker_at(7.77, -5.77), mapping, calibration, 0.008, values)
    assert not outside.in_window("cal", frame=0)


# ---------------------------------------------------------------------------
# A window is measured in true visual angle at its own location
# ---------------------------------------------------------------------------
#
# The PI, 2026-10-19: "Measure each window as the true angle between where the eye points
# and the window's center, at its own location." Each gaze point below is built from a
# direction, never from per-axis degrees: per-axis arithmetic is what is under test, and a
# point placed with it would agree with it by construction.


def _direction(x_deg: float, y_deg: float) -> tuple[float, float, float]:
    """A position's direction from the eye, `D · tan` per axis (`viewport.center`), unit."""
    t = (math.tan(math.radians(x_deg)), math.tan(math.radians(y_deg)), 1.0)
    norm = math.sqrt(sum(c * c for c in t))
    return (t[0] / norm, t[1] / norm, t[2] / norm)


def _away(center, angle_deg: float, toward, turn_deg: float = 0.0) -> tuple[float, float]:
    """The position `angle_deg` of true visual angle from `center`: along the great circle
    toward the position `toward`, turned `turn_deg` about the center's own direction."""
    c, w = _direction(*center), _direction(*toward)
    dot = sum(a * b for a, b in zip(c, w))
    t0 = [b - dot * a for a, b in zip(c, w)]
    norm = math.sqrt(sum(v * v for v in t0))
    t0 = [v / norm for v in t0]
    t90 = (c[1] * t0[2] - c[2] * t0[1], c[2] * t0[0] - c[0] * t0[2], c[0] * t0[1] - c[1] * t0[0])
    turn, angle = math.radians(turn_deg), math.radians(angle_deg)
    t = [math.cos(turn) * a + math.sin(turn) * b for a, b in zip(t0, t90)]
    d = [math.cos(angle) * a + math.sin(angle) * b for a, b in zip(c, t)]
    return (math.degrees(math.atan2(d[0], d[2])), math.degrees(math.atan2(d[1], d[2])))


def _window_world(gaze, center, radius: float = 2.0, mapping: Mapping | None = None) -> Tracked:
    """The calibration task's `cal` window at `center`, the animal looking at `gaze`."""
    values = {"target_x": center[0], "target_y": center[1], "cal_window": radius,
              "fix_acquisition": 3.0, "cal_hold": 0.2}
    return Tracked(_tracker_at(*gaze), mapping or _fitted_mapping(), calibration, 0.008, values)


@pytest.mark.parametrize("center, toward, turn", [
    ((20.0, 0.0), (20.0, 10.0), 0.0),
    ((30.0, 0.0), (30.0, 10.0), 0.0),
    ((20.0, 20.0), (40.0, 40.0), 0.0),
    ((20.0, 20.0), (40.0, 40.0), 90.0),
], ids=["straight up at 20", "straight up at 30", "out along the diagonal", "across the diagonal"])
def test_a_window_holds_gaze_by_true_visual_angle_at_its_own_location(center, toward, turn):
    """A 2° window holds gaze 1.99° from its center and not gaze 2.01° away, in every
    direction and wherever it is. The per-axis test, `hypot(x - cx, y - cy)`, made a 2° window
    at (20°, 0°) 1.879° tall, at (30°, 0°) 1.732° tall, and at (20°, 20°) 1.778° deep along the
    diagonal and 2.013° wide across it: smaller than declared in most directions off center, and
    larger in one."""
    inside = _away(center, 1.99, toward, turn)
    outside = _away(center, 2.01, toward, turn)

    assert _window_world(inside, center).in_window("cal", frame=0)
    assert not _window_world(outside, center).in_window("cal", frame=0)


@pytest.mark.parametrize("bearing", range(0, 360, 45))
def test_a_window_straight_ahead_is_as_it_was(bearing):
    """The control, which passes under the per-axis test too: straight ahead a per-axis degree
    is a degree of visual angle to within 0.0004° at 2°, so a window at (0°, 0°) is unchanged."""
    toward = (10.0 * math.cos(math.radians(bearing)), 10.0 * math.sin(math.radians(bearing)))

    assert _window_world(_away((0.0, 0.0), 1.99, toward), (0.0, 0.0)).in_window("cal", frame=0)
    assert not _window_world(_away((0.0, 0.0), 2.01, toward), (0.0, 0.0)).in_window(
        "cal", frame=0)


def test_every_window_in_the_field_holds_gaze_by_true_visual_angle():
    """Seeded, over direct view's whole field: a window anywhere in it, 0.5-8° in radius, holds
    gaze 0.5% inside its radius in any direction and not gaze 0.5% outside it."""
    rng = random.Random(20261019)
    mapping = _fitted_mapping()
    wrong = []
    for _ in range(200):
        center = (rng.uniform(-DIRECT.half_field_h_deg, DIRECT.half_field_h_deg),
                  rng.uniform(-DIRECT.half_field_v_deg, DIRECT.half_field_v_deg))
        radius, turn = rng.uniform(0.5, 8.0), rng.uniform(0.0, 360.0)
        toward = (center[0], center[1] + 10.0)
        inside = _away(center, 0.995 * radius, toward, turn)
        outside = _away(center, 1.005 * radius, toward, turn)
        if not _window_world(inside, center, radius, mapping).in_window("cal", frame=0):
            wrong.append(("missed", center, radius, turn))
        if _window_world(outside, center, radius, mapping).in_window("cal", frame=0):
            wrong.append(("held", center, radius, turn))

    assert wrong == []


def test_a_window_is_missed_when_the_map_is_the_wrong_one():
    """The failure this whole path exists to make visible. Uncalibrated gaze lands
    somewhere plausible and the trial scores as behaviour, not as a rig fault."""
    values = {"target_x": 6.0, "target_y": -4.0, "cal_window": 2.0,
              "fix_acquisition": 3.0, "cal_hold": 0.2}
    wrong = Mapping(
        version=1,
        targets=_targets(),
        left=EyeMap(Model.AFFINE, (0.0, 1.0, 0.0), (0.0, 0.0, 1.0), 1.0, 0.0, 13),
        right=EyeMap(Model.AFFINE, (0.0, 1.0, 0.0), (0.0, 0.0, 1.0), 1.0, 0.0, 13),
    )
    world = Tracked(_tracker_at(6.0, -4.0), wrong, calibration, 0.008, values)
    assert not world.in_window("cal", frame=0)


def test_before_the_first_sample_gaze_is_unavailable_not_centred():
    """`Tracker.state` refuses to report (0, 0) at startup; this asserts the refusal
    survives the join. A world reporting the origin would put gaze exactly on a
    centre target and score a hold against an empty chair."""
    world = Tracked(Tracker(), _fitted_mapping(), calibration, 0.008,
                    {"target_x": 0.0, "target_y": 0.0, "cal_window": 3.0,
                     "fix_acquisition": 3.0, "cal_hold": 0.2})
    assert world.gaze("left", frame=0) is None
    assert world.signal(frame=0) == "lost"
    assert not world.in_window("cal", frame=0)


def test_a_stale_sample_is_not_a_position():
    """The staleness ceiling belongs to `Tracker` and is not re-derived here. At
    8 ms a frame, the 50 ms default expires part-way through frame 7."""
    world = Tracked(_tracker_at(0.0, 0.0, at=0.0), _fitted_mapping(), calibration, 0.008,
                    {"target_x": 0.0, "target_y": 0.0, "cal_window": 3.0,
                     "fix_acquisition": 3.0, "cal_hold": 0.2})
    assert world.in_window("cal", frame=6)
    assert world.signal(frame=6) == "ok"
    assert not world.in_window("cal", frame=7)
    assert world.signal(frame=7) == "lost"


def test_an_eye_without_a_map_reports_no_gaze():
    mapping = Mapping(version=1, targets=_targets(), left=_fitted_mapping().left, right=None)
    world = Tracked(_tracker_at(3.0, 3.0), mapping, calibration, 0.008)
    assert world.gaze("left", frame=0) is not None
    assert world.gaze("right", frame=0) is None


def test_version_zero_maps_nothing():
    """A session before its calibration block. Asked for degrees it answers `None`,
    which is what stops an uncalibrated session silently scoring windows."""
    log = MappingLog(_targets())
    world = Tracked(_tracker_at(0.0, 0.0), log.current, calibration, 0.008,
                    {"target_x": 0.0, "target_y": 0.0, "cal_window": 3.0,
                     "fix_acquisition": 3.0, "cal_hold": 0.2})
    assert world.mapping_version == 0
    assert world.gaze("left", frame=0) is None
    assert not world.in_window("cal", frame=0)


def _saccade_source(dwell: int, steps: int, to: tuple[float, float], tail: int = 200,
                    noise: float = 0.02, seed: int = 5):
    """Payloads that fixate at the origin, saccade linearly to `to`, then hold.

    **With fixational noise, and that is not decoration.** Engbert-Kliegl's threshold
    is estimated from the trace's own velocity distribution, so a perfectly still eye
    gives a scale of exactly zero and the detector refuses to fire at all -- which is
    what `wl-preproc`'s does too (`if eta_x <= 0 or eta_y <= 0: return []`). A
    noiseless trace tests a case no eye produces.
    """
    rng = random.Random(seed)
    frames = [(0.0, 0.0)] * dwell
    frames += [((to[0] * k) / steps, (to[1] * k) / steps) for k in range(1, steps + 1)]
    frames += [to] * tail
    return Replay(payloads=[
        (0.0, _payload(x + rng.gauss(0, noise), y + rng.gauss(0, noise), frame=n))
        for n, (x, y) in enumerate(frames)
    ])


def _drive(world, frames: int, frame_period: float = 0.002):
    """Pump the world's own per-frame hook, which is where gaze is polled."""
    for frame in range(frames):
        world.display({}, frame)
        yield frame


def test_a_saccade_onset_is_reported_once_and_only_once():
    """One saccade is one response. A guard that stayed true would turn a single
    saccade into a stream of them for as long as the state lasted."""
    world = Tracked(
        Tracker(), _fitted_mapping(), calibration, 0.002,
        source=_saccade_source(dwell=120, steps=10, to=(8.0, 0.0)),
    )
    fired = [f for f in _drive(world, 320) if world.happened(SaccadeOnset(), "s", f)]
    assert len(fired) == 1, f"fired on frames {fired}"


def test_saccade_to_waits_for_the_eye_to_land():
    """At confirmation the eye is still in flight and has landed nowhere. Firing
    `SaccadeTo` then would report a saccade heading somewhere as having arrived."""
    values = {"target_x": 8.0, "target_y": 0.0, "cal_window": 2.0,
              "fix_acquisition": 3.0, "cal_hold": 0.2}
    world = Tracked(
        Tracker(), _fitted_mapping(), calibration, 0.002, values,
        source=_saccade_source(dwell=120, steps=10, to=(8.0, 0.0)),
    )
    onset_frame = landed_frame = None
    for frame in _drive(world, 320):
        if onset_frame is None and world.detector.onset is not None:
            onset_frame = frame
        if world.happened(SaccadeTo("cal"), "s", frame):
            landed_frame = frame
            break
    assert onset_frame is not None, "no saccade was detected at all"
    assert landed_frame is not None, "the saccade never landed in the window"
    assert landed_frame > onset_frame
    # The load-bearing part: the eye is not still moving when the landing is
    # reported. `landed > onset` alone is satisfied by firing one frame later.
    assert not world.detector.in_flight
    assert world.gaze_cyclopean(landed_frame) == pytest.approx((8.0, 0.0), abs=0.5)


def test_saccade_to_does_not_fire_when_the_saccade_lands_elsewhere():
    """The distinction between `SaccadeTo` and 'a saccade happened'. A saccade away
    from the target must not satisfy a guard naming the target."""
    values = {"target_x": 8.0, "target_y": 0.0, "cal_window": 2.0,
              "fix_acquisition": 3.0, "cal_hold": 0.2}
    world = Tracked(
        Tracker(), _fitted_mapping(), calibration, 0.002, values,
        source=_saccade_source(dwell=120, steps=10, to=(-9.0, 4.0)),
    )
    fired = [f for f in _drive(world, 320) if world.happened(SaccadeTo("cal"), "s", f)]
    assert fired == []


def test_a_saccade_is_consumed_by_whichever_guard_takes_it():
    """Otherwise one saccade satisfies `SaccadeTo` on every later frame gaze stays in
    the window, which is indistinguishable from saccading there over and over."""
    values = {"target_x": 8.0, "target_y": 0.0, "cal_window": 2.0,
              "fix_acquisition": 3.0, "cal_hold": 0.2}
    world = Tracked(
        Tracker(), _fitted_mapping(), calibration, 0.002, values,
        source=_saccade_source(dwell=120, steps=10, to=(8.0, 0.0)),
    )
    fired = [f for f in _drive(world, 400) if world.happened(SaccadeTo("cal"), "s", f)]
    assert len(fired) == 1, f"fired on frames {fired}"


def test_a_still_eye_produces_no_saccade():
    world = Tracked(
        Tracker(), _fitted_mapping(), calibration, 0.002,
        source=Replay(payloads=[(0.0, _payload(1.0, 1.0, frame=n)) for n in range(400)]),
    )
    assert [f for f in _drive(world, 350) if world.happened(SaccadeOnset(), "s", f)] == []


# ---------------------------------------------------------------------------
# End to end: a calibration trial, scored from replayed gaze
# ---------------------------------------------------------------------------


def test_a_calibration_trial_is_scored_from_replayed_gaze():
    """P6's exit condition. Payloads in, `CORRECT` out, through the parser, the
    tracker, a fitted map, the window geometry and the trial loop."""
    values = {"target_x": 6.0, "target_y": -4.0, "cal_window": 2.0,
              "fix_acquisition": 2.0, "cal_hold": 0.1}
    frame_period = 0.008
    world = Tracked(
        Tracker(),
        _fitted_mapping(),
        calibration,
        frame_period,
        values,
        source=Replay(payloads=[(0.0, _payload(6.0, -4.0, frame=n)) for n in range(400)]),
    )

    result = run_trial(calibration, world, frame_period, values=values,
                       effects=Recorded())
    assert result.outcome is Outcome.CORRECT


def test_a_calibration_trial_aborts_when_the_animal_looks_elsewhere():
    """The same path, with the animal looking well away from the target.
    `NO_FIXATION` rather than `CORRECT` is what says the window test is actually
    being applied rather than passing everything."""
    values = {"target_x": 6.0, "target_y": -4.0, "cal_window": 2.0,
              "fix_acquisition": 0.5, "cal_hold": 0.1}
    frame_period = 0.008
    world = Tracked(
        Tracker(),
        _fitted_mapping(),
        calibration,
        frame_period,
        values,
        source=Replay(payloads=[(0.0, _payload(-6.0, 6.0, frame=n)) for n in range(400)]),
    )

    result = run_trial(calibration, world, frame_period, values=values,
                       effects=Recorded())
    assert result.outcome is Outcome.NO_FIXATION


def test_a_tracker_that_stops_delivering_is_equipment_not_behaviour():
    """The source runs dry part-way through the hold. That has to reach the loop as
    `TRACKER_LOST`, not as a fixation break: scoring a dropped camera as the animal
    looking away inflates a session's break rate with equipment failure, invisibly."""
    values = {"target_x": 6.0, "target_y": -4.0, "cal_window": 2.0,
              "fix_acquisition": 3.0, "cal_hold": 2.0}
    frame_period = 0.008
    world = Tracked(
        Tracker(),
        _fitted_mapping(),
        calibration,
        frame_period,
        values,
        source=Replay(payloads=[(0.0, _payload(6.0, -4.0, frame=n)) for n in range(20)]),
    )

    result = run_trial(calibration, world, frame_period, values=values,
                       effects=Recorded())
    assert result.outcome is Outcome.TRACKER_LOST


# ---------------------------------------------------------------------------
# The collector, and the versioned map
# ---------------------------------------------------------------------------


def test_the_collector_fits_both_eyes_from_held_fixations():
    collector = Collector()
    for x, y in _targets():
        assert collector.accept((x, y), [parse(_payload(x, y), at=0.0)])

    left, right, findings = collector.fit()
    assert left is not None and right is not None
    assert left.model is Model.SECOND_ORDER
    assert [f for f in findings if f.blocking] == []
    assert left.n_points == 13


def test_the_collector_tags_each_finding_by_eye_and_keeps_every_other_field(monkeypatch):
    """The engine B final review: the tag rebuilt each finding from its code, detail and
    blocking, so a warning came out accepted in no session kind."""
    said = "a warning fit_eye gives"
    warned = Finding("a-stand-in", said, blocking=False, accepted_in=NOT_RECORDING)
    monkeypatch.setattr("wl_xcon.calibration.fit_eye", lambda fixations, **_: (None, [warned]))

    _, _, findings = Collector().fit()

    assert findings == [
        Finding("a-stand-in:left", said, blocking=False, accepted_in=NOT_RECORDING),
        Finding("a-stand-in:right", said, blocking=False, accepted_in=NOT_RECORDING),
    ]


def test_a_target_worked_twice_still_counts_once():
    """`fit_eye` weights by target, so a target the scheduler happened to present
    twice would otherwise pull the fit toward wherever the animal was asked twice."""
    collector = Collector()
    for x, y in _targets():
        collector.accept((x, y), [parse(_payload(x, y), at=0.0)])
    collector.accept(_targets()[0], [parse(_payload(*_targets()[0]), at=0.0)])

    assert len(collector.fixations("left")) == 13


def test_a_target_with_too_few_samples_is_declined():
    collector = Collector(minimum_samples=3)
    assert not collector.accept((0.0, 0.0), [parse(_payload(0.0, 0.0), at=0.0)])
    assert collector.fixations("left") == ()


def test_the_collector_averages_the_samples_it_is_given():
    collector = Collector()
    collector.accept(
        (2.0, 2.0),
        [parse(_payload(1.0, 1.0), at=0.0), parse(_payload(3.0, 3.0), at=0.0)],
    )
    (fixation,) = collector.fixations("left")
    assert fixation.raw == pytest.approx(_raw_for(2.0, 2.0))


def test_the_map_is_versioned_and_every_change_is_logged():
    log = MappingLog(_targets())
    assert log.version == 0

    fitted = _fitted_mapping().left
    log.install(at=100.0, targets=_targets(), left=fitted, right=fitted, why="block 1")
    assert log.version == 1

    log.recenter(at=250.0, left=(0.5, -0.25), right=(0.5, -0.25), why="chair shifted")
    assert log.version == 2
    assert [c.why for c in log.changes] == ["block 1", "chair shifted"]
    assert [c.at for c in log.changes] == [100.0, 250.0]

    # Reconstructible after the fact, which is the point of keeping versions.
    assert log.at_version(1).offsets == ((0.0, 0.0), (0.0, 0.0))
    assert log.at_version(2).offsets == ((0.5, -0.25), (0.5, -0.25))


def test_recentering_shifts_gaze_without_refitting():
    fitted = _fitted_mapping().left
    log = MappingLog(_targets())
    log.install(at=0.0, targets=_targets(), left=fitted, right=fitted)
    before = Tracked(_tracker_at(3.0, 3.0), log.current, calibration, 0.008)
    assert before.gaze("left", 0) == pytest.approx((3.0, 3.0), abs=1e-6)

    log.recenter(at=1.0, left=(0.5, -0.25), right=(0.5, -0.25))
    after = Tracked(_tracker_at(3.0, 3.0), log.current, calibration, 0.008)
    assert after.gaze("left", 0) == pytest.approx((3.5, 2.75), abs=1e-6)
    # The coefficients themselves are untouched, so the correction is reversible.
    assert log.current.left.x == fitted.x


def test_recentering_replaces_rather_than_accumulates():
    """Two recenterings are two statements about where the animal is now. The
    second was measured against gaze the first had already corrected, so adding
    them applies the first twice."""
    fitted = _fitted_mapping().left
    log = MappingLog(_targets())
    log.install(at=0.0, targets=_targets(), left=fitted, right=fitted)
    log.recenter(at=1.0, left=(0.5, 0.0), right=(0.5, 0.0))
    log.recenter(at=2.0, left=(0.2, 0.0), right=(0.2, 0.0))

    world = Tracked(_tracker_at(3.0, 3.0), log.current, calibration, 0.008)
    assert world.gaze("left", 0) == pytest.approx((3.2, 3.0), abs=1e-6)


def test_a_refit_drops_the_offset():
    """A recentering describes a chair position under the map it was measured
    against. Carrying it across a refit applies a correction the new fit already
    contains."""
    fitted = _fitted_mapping().left
    log = MappingLog(_targets())
    log.install(at=0.0, targets=_targets(), left=fitted, right=fitted)
    log.recenter(at=1.0, left=(3.0, 3.0), right=(3.0, 3.0))
    log.install(at=2.0, targets=_targets(), left=fitted, right=fitted, why="block 2")

    assert log.current.offsets == ((0.0, 0.0), (0.0, 0.0))


def test_recentering_without_a_map_is_refused():
    with pytest.raises(ValueError, match="no map to recenter"):
        MappingLog(_targets()).recenter(at=1.0, left=(1.0, 0.0))


def test_the_offset_is_folded_into_the_file_because_their_schema_has_no_room():
    """Their model forbids fields it does not declare, so a recentered map has to
    reach the file as coefficients. Folding into the constant is exact for an
    additive offset; what is lost is that a recentering happened, and that survives
    in the change log."""
    fitted = _fitted_mapping().left
    log = MappingLog(_targets())
    log.install(at=0.0, targets=_targets(), left=fitted, right=fitted)
    log.recenter(at=1.0, left=(0.5, -0.25), right=(0.0, 0.0))

    written = log.current.as_calibration()
    assert written.left.x[0] == pytest.approx(fitted.x[0] + 0.5)
    assert written.left.y[0] == pytest.approx(fitted.y[0] - 0.25)
    assert written.left.x[1:] == fitted.x[1:]
    assert written.right.x[0] == pytest.approx(fitted.x[0])
    assert written.mapping_version == 2


# ---------------------------------------------------------------------------
# A whole calibration block, from scheduled targets to an installed map
# ---------------------------------------------------------------------------


def test_a_whole_calibration_block_produces_an_installed_map():
    """Every piece of P6 at once: the scheduler walks the constellation, the task
    scores each target from replayed gaze, the collector averages what was held, the
    fit runs, and the result is installed as a new mapping version.

    This is the shape the `taskd` driver has to take, written as a test because
    `taskd` is still a spine and wiring a calibration block into a real session is
    P4b's. Until then this is what says the pieces compose -- each was tested alone,
    and alone none of them proves an animal's gaze becomes a map.
    """
    frame_period = 0.008
    block = Block(
        name="calibration",
        conditions=conditions(
            GEOMETRY, window_deg=3.0, hold_s=0.1, acquisition_s=1.0,
            luminance_cd_m2=40.0, repeats=2
        ),
    )
    scheduler = Scheduler(blocks=[block], seed=11)
    collector = Collector()
    log = MappingLog(_targets())

    # Version 0 maps nothing, so the block cannot be scored through the map it is
    # about to produce. A calibration window is sized for that: wide enough to admit
    # gaze that is wrong by the amount calibration is about to correct.
    bootstrap = _fitted_mapping()

    trials = 0
    while not scheduler.finished and trials < 200:
        condition = scheduler.next_trial()
        trials += 1
        target = (condition.values["target_x"], condition.values["target_y"])
        world = Tracked(
            Tracker(),
            bootstrap,
            calibration,
            frame_period,
            condition.values,
            source=Replay(payloads=[(0.0, _payload(*target, frame=n)) for n in range(400)]),
        )
        result = run_trial(calibration, world, frame_period, values=condition.values,
                           effects=Recorded())
        scheduler.record(condition.name, result.outcome)

        # Only trials the task paid for contribute. A fixation the task would not
        # reward is not one to calibrate against.
        if result.outcome is Outcome.CORRECT:
            collector.accept(target, [parse(_payload(*target), at=0.0)])

    assert scheduler.finished
    assert trials == 26, "thirteen targets, twice each"

    left, right, findings = collector.fit(tested_eccentricity_deg=16.0)
    assert left is not None and right is not None
    assert [f for f in findings if f.blocking] == []
    assert left.model is Model.SECOND_ORDER
    assert left.n_points == 13, "a target worked twice contributes one pairing"

    installed = log.install(at=42.0, targets=_targets(), left=left, right=right,
                            why="calibration block")
    assert installed.version == 1
    assert log.changes[0].why == "calibration block"

    # And the installed map is the one a later trial would be scored through.
    scored = Tracked(_tracker_at(6.0, -4.0), log.current, calibration, frame_period)
    assert scored.mapping_version == 1
    assert scored.gaze("left", 0) == pytest.approx((6.0, -4.0), abs=1e-6)


# ---------------------------------------------------------------------------
# A whole session, not a composition test
# ---------------------------------------------------------------------------
#
# The test above composes every piece by hand and its docstring says it is "the
# shape the `taskd` driver has to take". That was true and it is not a driver: a
# session never ran a calibration block, and nothing wrote the map at close, so the
# artifact `wl-preproc` reads existed only as bytes a test could produce.


def _calibration_bounds() -> Bounds:
    return Bounds(
        subject="REFERENCE",
        ceilings={
            "reward_correct": Ceiling(value=0.05, maximum=0.20, unit="mL"),
            # The session's one duration ceiling (PI, 2026-09-19). A calibration
            # block is twenty-six trials of at most a second and a half, so this
            # admits them several times over -- and still bounds a scheduler whose
            # counters stop advancing, which since `max_trials` went is the only
            # backstop a criterion-free block has besides its own quota. It is read
            # on the wall since P4d-2a (spec §10), so these sessions are given a
            # wall that follows their frames (`_marked`); against this host's own
            # clock it would bound nothing for ten real minutes.
            "out_of_cage": Ceiling(value=600.0, maximum=600.0, unit="s"),
        },
        minima={"daily_fluid": Floor(value=20.0, unit="mL")},
    )


#: The wall instant these sessions start at, in POSIX seconds. Only differences
#: from it matter.
WALL_NOW = 1_700_000_000.0


def _marked(session: Session) -> Session:
    """The marks a `RIG_FIXED` session needs, on a wall that follows its frames.

    Every welfare duration is read on the wall since P4d-2a (spec §10), and both
    marks are wall instants. The wall is `WALL_NOW` plus the session's frame clock,
    so the out-of-cage ceiling above still ends a runaway block on simulated seconds
    -- the same arrangement `tests/test_taskd.py`'s `_session` makes.
    """
    session.wall_clock = lambda: WALL_NOW + session.now()
    session.left_cage(at=session.wall_now())
    session.head_fixed(at=session.wall_now())
    return session


def _calibration_session(tmp_path, repeats: int = 2):
    frame_period = 0.008
    block = Block(
        name="calibration",
        conditions=conditions(
            GEOMETRY, window_deg=3.0, hold_s=0.1, acquisition_s=1.0,
            luminance_cd_m2=40.0, repeats=repeats
        ),
    )
    driver = Calibrating(
        bootstrap=_fitted_mapping(),
        log=MappingLog(_targets()),
        frame_period=frame_period,
        replay=lambda target: [
            (0.0, _payload(*target, frame=n)) for n in range(400)
        ],
    )
    spec = SessionSpec(
        task="tasks/calibration.py",
        allocation="tasks/allocation.py",
        root=tmp_path,
        session_id="2027-01-14_01",
        subject="REFERENCE",
        trials=0,
        frame_period=frame_period,
        seed=11,
        values={"cal_window": 3.0, "fix_acquisition": 1.0, "cal_hold": 0.1},
        bounds=_calibration_bounds(),
        already_delivered_today=0.0,
        deployment=Deployment.RIG_FIXED,
        geometry=DIRECT,
        session_kind="training",
        calibration=SRGB,
        blocks=[block],
    )
    session = Session(
        spec,
        card=Card(),
        pump=Pump(),
        world=driver.world,
        observe=driver.observe,
    )
    return _marked(session), driver


def test_a_session_runs_the_calibration_block_and_installs_the_map(tmp_path):
    """The exit condition P6 left open. A session -- with its ceilings, its record
    and its event stream -- walks the constellation and ends with a map installed."""
    session, driver = _calibration_session(tmp_path)

    session.run()
    mapping, findings = driver.install(at=42.0, tested_eccentricity_deg=16.0)

    assert session.stopped_because == "every block is finished"
    assert [f for f in findings if f.blocking] == []
    assert mapping.version == 1
    assert mapping.left is not None and mapping.left.n_points == 13


@_contract
def test_a_calibration_session_writes_the_file_wl_preprocs_reader_accepts(tmp_path):
    """`GazeCalibration.to_yaml` already produced the right bytes; nothing put them
    on disk under a session. Round-tripped through their real reader below, because a
    file we believe is readable is not the claim worth making."""
    session, driver = _calibration_session(tmp_path)
    session.run()
    driver.install(at=42.0, tested_eccentricity_deg=16.0)

    written = driver.write(session.directory)

    assert written == tmp_path / "2027-01-14_01" / "xcon" / "eye_calibration.yaml"
    assert _read_their_map(written) is not None


def test_only_trials_the_task_paid_for_reach_the_fit(tmp_path):
    """A fixation the task would not reward is not one to calibrate against, and the
    session is now what enforces that rather than a test doing it by hand."""
    session, driver = _calibration_session(tmp_path)

    census = session.run()

    assert driver.collected == census.outcomes[Outcome.CORRECT]
    assert driver.collected > 0


def test_a_calibration_session_is_paid_and_counted_like_any_other(tmp_path):
    """Calibration is a block, not an exception. The animal works and is paid, and
    the day's total counts it -- so calibration work counts toward the day's floor
    rather than being unpaid setup."""
    session, _ = _calibration_session(tmp_path)

    census = session.run()

    assert session.welfare.deliveries == census.outcomes[Outcome.CORRECT]
    assert session.welfare.total_today() > 0.0


def test_the_fit_uses_the_hold_and_not_the_whole_trial(tmp_path):
    """A calibration trial *begins* with the animal looking somewhere else -- that is
    what `Entered("cal")` waits for. Averaging every sample the trial saw would drag
    each target toward wherever gaze happened to start, by an amount that depends on
    how long acquisition took, and the resulting map would be wrong in a way no
    conditioning or extent check can see."""
    frame_period = 0.008
    hold_s = 0.1

    def replay(target):
        """Fifty frames looking 8.5 deg off this target, then at it.

        Relative to the target rather than at a fixed point, because a fixed one
        lands inside *some* target's 3 deg window and that trial's hold would then
        be satisfied by gaze that never moved -- which would make this test pass for
        a reason that has nothing to do with the slice under test.
        """
        away = (target[0] + 6.0, target[1] + 6.0)
        payloads = [(0.0, _payload(*away, frame=n)) for n in range(50)]
        payloads += [(0.0, _payload(*target, frame=n)) for n in range(50, 400)]
        return payloads

    driver = Calibrating(
        bootstrap=_fitted_mapping(),
        log=MappingLog(_targets()),
        frame_period=frame_period,
        replay=replay,
    )
    spec = SessionSpec(
        task="tasks/calibration.py",
        allocation="tasks/allocation.py",
        root=tmp_path,
        session_id="2027-01-14_01",
        subject="REFERENCE",
        trials=0,
        frame_period=frame_period,
        seed=11,
        values={"cal_window": 3.0, "fix_acquisition": 1.0, "cal_hold": hold_s},
        bounds=_calibration_bounds(),
        already_delivered_today=0.0,
        deployment=Deployment.RIG_FIXED,
        geometry=DIRECT,
        session_kind="training",
        calibration=SRGB,
        blocks=[
            Block(
                name="calibration",
                conditions=conditions(
                    GEOMETRY, window_deg=3.0, hold_s=hold_s, acquisition_s=1.0,
                    luminance_cd_m2=40.0, repeats=1
                ),
            )
        ],
    )
    session = _marked(
        Session(spec, card=Card(), pump=Pump(), world=driver.world,
                observe=driver.observe)
    )

    session.run()
    mapping, findings = driver.install(at=1.0, tested_eccentricity_deg=16.0)

    assert [f for f in findings if f.blocking] == []
    # The camera is affine, so a map fit from the held samples alone recovers gaze
    # exactly. Samples from before acquisition would show up here as error.
    world = Tracked(_tracker_at(6.0, -4.0), mapping, calibration, frame_period)
    assert world.gaze("left", 0) == pytest.approx((6.0, -4.0), abs=1e-6)


def test_a_window_whose_center_is_a_polar_position_holds_gaze_by_true_visual_angle():
    """A window written as its eccentricity and direction (the PI, 2026-10-19), here 20° out at
    120° by its settings, is scored where that position is: gaze 1.99° from it in true visual
    angle is inside its 2° radius and 2.01° is outside, in any direction."""
    from wl_xcon.task import After, Disc, Hold, On, Outcome, P, Polar, Show, State, Stimulus
    from wl_xcon.task import Trial, Window

    trial = Trial(
        start="on",
        windows=[Window("w", at=Polar(P("ecc"), P("dir")), radius=2.0, on="s")],
        states=[State("on", enter=[Show(Stimulus("s", at=Polar(P("ecc"), P("dir"))))],
                      go=[On(Hold("w", 0.1), Outcome.CORRECT), On(After(1.0), Outcome.ABORT)])],
    )
    values = {"ecc": 20.0, "dir": 120.0}
    t = math.tan(math.radians(20.0))
    center = (math.degrees(math.atan(t * math.cos(math.radians(120.0)))),
              math.degrees(math.atan(t * math.sin(math.radians(120.0)))))
    mapping = _fitted_mapping()
    for turn in (0.0, 45.0, 90.0, 200.0):
        toward = (center[0], center[1] + 10.0)
        inside = Tracked(_tracker_at(*_away(center, 1.99, toward, turn)), mapping, trial, 0.008,
                         values)
        outside = Tracked(_tracker_at(*_away(center, 2.01, toward, turn)), mapping, trial, 0.008,
                          values)
        assert inside.in_window("w", frame=0) and not outside.in_window("w", frame=0)


# ---------------------------------------------------------------------------
# An array's object windows follow an `Update` that moves it (XC-402)
# ---------------------------------------------------------------------------
#
# Each object's window is where the object is drawn (STE-28), so an `Update` that moves an array
# -- its position, as a pair, as eccentricity and direction or as a setting; its ring's radius;
# its rotation; its set size; which object is its target -- moves the windows with it, from the
# frame the display first carries the change. Until 2026-10-27 they stayed where the array's
# `Show` had put it for the whole trial, and the animal was scored where the objects had been.
# Gaze is placed where `screen` draws each object, never where the windows are built: the windows
# are what is under test.

#: Four 0.5° discs on a 3° ring, object 1 the target. With 1° windows, neighbors' windows are
#: 4.24° apart and never touch.
_DISC = Disc(size=0.5, color=Gray(40.0))
_RING = Array(n=4, radius=3.0, target=1, looks=_DISC, among=_DISC)
_FRAME = 0.008
_HOLD = 0.05


def _drawn(stimulus: Stimulus, values: dict, trial: Trial) -> dict:
    """Where `screen` draws each of an array stimulus's objects, by name, in direct view."""
    shown = screen.resolve({stimulus.name: stimulus}, values, trial, DIRECT, frame_period=_FRAME)
    return {item.name: item.at_left for item in shown.items}


def _moved(shown: Stimulus, update: Update) -> Stimulus:
    """The stimulus as the display carries it after `update`, made as `run._apply` makes it."""
    return replace(shown, **update.changes())


def _apart(p, q) -> float:
    """The angle at the eye between two positions, from their directions."""
    a, b = _direction(*p), _direction(*q)
    return math.degrees(math.acos(max(-1.0, min(1.0, sum(x * y for x, y in zip(a, b))))))


def _then_moved(shown: Stimulus, update: Update, held: str = "search.1", before=None,
                scored_as: Outcome = Outcome.CORRECT, windows=None, waits: float = 0.5) -> Trial:
    """`shown`, moved by `update` once `before` fires (0.04 s by default) within `waits`, or else
    `NO_FIXATION`; then 0.5 s for a `_HOLD` on `held`, scored `scored_as`, or else
    `NO_RESPONSE`."""
    return Trial(
        start="shown",
        windows=windows or [ObjectWindows(of="search", radius=1.0)],
        states=[
            State("shown", enter=[Show(shown)],
                  go=[On(before or After(0.04), "moved"), On(After(waits), Outcome.NO_FIXATION)]),
            State("moved", enter=[update],
                  go=[On(Hold(held, _HOLD), scored_as), On(After(0.5), Outcome.NO_RESPONSE)]),
        ],
    )


def _run(trial: Trial, values: dict, gaze: list, eyes: "list | None" = None):
    """The trial through the loop, gaze held at `gaze[k]` on frame k + 1 (and the right eye at
    `eyes[k]` when given), through the parser, the tracker, a fitted map and `Tracked`."""
    payloads = []
    for n, at in enumerate(gaze):
        payload = json.loads(_payload(*at, frame=n))
        if eyes is not None:
            payload["Right"] = json.loads(_payload(*eyes[n], frame=n))["Right"]
        payloads.append((0.0, json.dumps(payload)))
    world = Tracked(Tracker(), _fitted_mapping(), trial, _FRAME, values,
                    source=Replay(payloads=payloads))
    return run_trial(trial, world, _FRAME, values=values, effects=Recorded())


#: Each way an `Update` moves an array without changing its objects: the array shown, the update,
#: and the settings the trial runs with.
_MOVES = {
    "to another x-y position": (
        Stimulus("search", at=(0.0, 0.0), looks=_RING), Update("search", at=(10.0, 5.0)), {}),
    "to another eccentricity and direction, by its settings": (
        Stimulus("search", at=Polar(5.0, 30.0), looks=_RING),
        Update("search", at=Polar(P("ecc"), P("dir"))), {"ecc": 12.0, "dir": 200.0}),
    "to a position one setting holds whole": (
        Stimulus("search", at=(0.0, 0.0), looks=_RING), Update("search", at=P("where")),
        {"where": Polar(8.0, 135.0)}),
    "its ring grown": (
        Stimulus("search", at=(4.0, -2.0), looks=_RING),
        Update("search", looks=replace(_RING, radius=7.0)), {}),
    "rotated": (
        Stimulus("search", at=(4.0, -2.0), looks=_RING),
        Update("search", looks=replace(_RING, phase=90.0)), {}),
    "to an array a setting holds": (
        Stimulus("search", at=(4.0, -2.0), looks=_RING), Update("search", looks=P("ring")),
        {"ring": replace(_RING, radius=6.0, phase=45.0)}),
}


def _object_1(move: str):
    """A move's trial, its settings, and where object 1 is drawn before and after it."""
    shown, update, values = _MOVES[move]
    trial = _then_moved(shown, update)
    old = _drawn(shown, values, trial)["search.1"]
    new = _drawn(_moved(shown, update), values, trial)["search.1"]
    assert _apart(old, new) > 2.0, "the move must take the window off where it was"
    return trial, values, old, new


@pytest.mark.parametrize("move", list(_MOVES))
def test_an_array_s_object_windows_follow_an_update_that_moves_it(move):
    """After the update, gaze where object 1 is now drawn holds its window. Until 2026-10-27 it
    held nothing there (XC-402)."""
    trial, values, _, new = _object_1(move)

    assert _run(trial, values, [new] * 200).outcome is Outcome.CORRECT


@pytest.mark.parametrize("move", list(_MOVES))
def test_after_the_update_an_object_s_old_place_holds_nothing(move):
    """After the update, gaze where object 1 was drawn holds no window: until 2026-10-27 the
    animal was scored there, looking at where the object had been (XC-402)."""
    trial, values, old, _ = _object_1(move)

    assert _run(trial, values, [old] * 200).outcome is Outcome.NO_RESPONSE


def test_before_the_update_the_windows_are_where_the_array_was_shown():
    """The in-between: gaze held where object 1 is shown completes the first hold, and the update
    follows; held then where the update draws it, the second completes too. Gaze stays where the
    object was shown for as long as the first hold is waited for (0.07 s), too short a time after
    the update for a second hold there."""
    shown, update, values = _MOVES["to another x-y position"]
    trial = _then_moved(shown, update, before=Hold("search.1", _HOLD), waits=0.07)
    old = _drawn(shown, values, trial)["search.1"]
    new = _drawn(_moved(shown, update), values, trial)["search.1"]

    result = _run(trial, values, [old] * math.ceil(0.07 / _FRAME) + [new] * 200)

    assert result.visited == ("shown", "moved")
    assert result.outcome is Outcome.CORRECT


def test_the_windows_move_on_the_frame_the_display_first_carries_the_update():
    """Not a frame before, while the objects are still drawn where they were, and not a frame
    after: with gaze already where object 1 is going, `Entered` on it fires on the frame the loop
    records the update as first shown (`Result.changed`)."""
    shown, update, values = _MOVES["to another x-y position"]
    trial = Trial(
        start="shown",
        windows=[ObjectWindows(of="search", radius=1.0)],
        states=[
            State("shown", enter=[Show(shown)], go=[On(After(0.04), "moved")]),
            State("moved", enter=[update], go=[On(Entered("search.1"), Outcome.CORRECT),
                                               On(After(0.5), Outcome.NO_RESPONSE)]),
        ],
    )
    new = _drawn(_moved(shown, update), values, trial)["search.1"]

    result = _run(trial, values, [new] * 200)

    assert result.outcome is Outcome.CORRECT
    assert result.frames == result.changed[0].frame


def test_gaze_left_where_an_object_was_has_exited_it_on_the_frame_it_moves():
    """The other edge of the same frame: gaze that stays where object 1 was shown is inside its
    window until the update and has left it, an `Exited`, on the frame the update is first shown,
    though the eye never moved (EYE-29)."""
    shown, update, values = _MOVES["to another x-y position"]
    trial = Trial(
        start="shown",
        windows=[ObjectWindows(of="search", radius=1.0)],
        states=[
            State("shown", enter=[Show(shown)], go=[On(After(0.04), "moved")]),
            State("moved", enter=[update], go=[On(Exited("search.1"), Outcome.FIXATION_BREAK),
                                               On(After(0.5), Outcome.NO_RESPONSE)]),
        ],
    )
    old = _drawn(shown, values, trial)["search.1"]

    result = _run(trial, values, [old] * 200)

    assert result.outcome is Outcome.FIXATION_BREAK
    assert result.frames == result.changed[0].frame


@pytest.mark.parametrize("before, after, at, outcome", [
    (4, 8, "after", Outcome.WRONG_TARGET),
    (8, 4, "before", Outcome.NO_RESPONSE),
], ids=["an object only the larger set has", "an object the smaller set no longer has"])
def test_an_update_of_set_size_moves_the_objects_and_who_the_distractors_are(
        before, after, at, outcome):
    """Object 5 exists in an eight-object array and not in a four-object one: gaze where an
    update to eight draws it holds `search.distractor`, and gaze where an update to four took it
    from holds nothing."""
    shown = Stimulus("search", at=(0.0, 0.0), looks=replace(_RING, n=before))
    update = Update("search", looks=replace(_RING, n=after))
    trial = _then_moved(shown, update, held="search.distractor",
                        scored_as=Outcome.WRONG_TARGET)
    drawn = _drawn(shown if at == "before" else _moved(shown, update), {}, trial)["search.5"]

    assert _run(trial, {}, [drawn] * 200).outcome is outcome


def test_an_object_a_smaller_set_no_longer_has_holds_nothing_where_it_was():
    """Object 5 of eight, named directly rather than through an alias: after an update to four
    objects it has no window, and gaze where it was drawn holds nothing (the review's R1). Kept
    from the eight-object placement, it would still hold gaze there."""
    shown = Stimulus("search", at=(0.0, 0.0), looks=replace(_RING, n=8))
    update = Update("search", looks=_RING)
    trial = _then_moved(shown, update, held="search.5")

    assert _run(trial, {}, [_drawn(shown, {}, trial)["search.5"]] * 200).outcome is \
        Outcome.NO_RESPONSE


def test_two_updates_in_turn_place_the_windows_where_both_put_the_objects():
    """Moved by one update and its ring grown by a later one: the windows are where both put
    the objects, an update's position paired with another update's appearance (the review's R4),
    not where the move alone did."""
    shown = Stimulus("search", at=(0.0, 0.0), looks=_RING)
    move, grow = Update("search", at=(10.0, 5.0)), Update("search", looks=replace(_RING, radius=7.0))
    trial = Trial(
        start="shown",
        windows=[ObjectWindows(of="search", radius=1.0)],
        states=[
            State("shown", enter=[Show(shown)], go=[On(After(0.024), "moved")]),
            State("moved", enter=[move], go=[On(After(0.024), "grown")]),
            State("grown", enter=[grow], go=[On(Hold("search.1", _HOLD), Outcome.CORRECT),
                                             On(After(0.5), Outcome.NO_RESPONSE)]),
        ],
    )
    both = _drawn(_moved(_moved(shown, move), grow), {}, trial)["search.1"]

    result = _run(trial, {}, [both] * 200)

    assert result.visited == ("shown", "moved", "grown")
    assert result.outcome is Outcome.CORRECT


@pytest.mark.parametrize("on, outcome", [
    ("search.3", Outcome.CORRECT), ("search.1", Outcome.NO_RESPONSE),
], ids=["the new target", "the old target"])
def test_an_update_that_changes_the_target_moves_what_holds_the_target(on, outcome):
    """The objects stay where they are and object 3 becomes the target: a hold on
    `search.target` is then a hold on object 3, and no longer on object 1."""
    shown = Stimulus("search", at=(0.0, 0.0), looks=_RING)
    update = Update("search", looks=replace(_RING, target=3))
    trial = _then_moved(shown, update, held="search.target")

    assert _run(trial, {}, [_drawn(shown, {}, trial)[on]] * 200).outcome is outcome


def test_a_saccade_to_the_target_is_scored_where_an_update_made_it_the_target():
    """`SaccadeTo` asks the world about the target by its alias's own name, so the world's own
    reading of `search.target` must follow the update, not only the loop's membership."""
    ring = replace(_RING, radius=8.0)
    shown = Stimulus("search", at=(0.0, 0.0), looks=ring)
    update = Update("search", looks=replace(ring, target=3))
    trial = Trial(
        start="shown",
        windows=[ObjectWindows(of="search", radius=2.0)],
        states=[
            State("shown", enter=[Show(shown)], go=[On(After(0.02), "moved")]),
            State("moved", enter=[update], go=[On(SaccadeTo("search.target"), Outcome.CORRECT),
                                               On(After(0.6), Outcome.NO_RESPONSE)]),
        ],
    )
    to = _drawn(_moved(shown, update), {}, trial)["search.3"]
    world = Tracked(Tracker(), _fitted_mapping(), trial, 0.002, {},
                    source=_saccade_source(dwell=120, steps=10, to=to))

    result = run_trial(trial, world, 0.002, values={}, effects=Recorded())

    assert result.outcome is Outcome.CORRECT


def test_an_object_window_an_update_adds_scores_the_eye_its_family_declares():
    """A family scoring the left eye scores it in an object only the update draws: the left eye
    on object 5 holds it while the right looks 6° away, where their mean would not."""
    shown = Stimulus("search", at=(0.0, 0.0), looks=_RING)
    update = Update("search", looks=replace(_RING, n=8))
    trial = _then_moved(shown, update, held="search.5",
                        windows=[ObjectWindows(of="search", radius=1.0, eye="left")])
    left = _drawn(_moved(shown, update), {}, trial)["search.5"]
    right = (left[0] + 6.0, left[1])

    assert _run(trial, {}, [left] * 200, eyes=[right] * 200).outcome is Outcome.CORRECT


def test_an_array_shown_twice_is_scored_where_each_show_draws_it():
    """Hidden and shown again elsewhere: each presentation's windows are where it is drawn. Built
    once from the `Show`, they were where the last `Show` in the task put it, for every one. Gaze
    stays where object 1 is first shown for as long as the first presentation waits for it."""
    first = Stimulus("search", at=(0.0, 0.0), looks=_RING)
    second = replace(first, at=(10.0, 5.0))
    trial = Trial(
        start="first",
        windows=[ObjectWindows(of="search", radius=1.0)],
        states=[
            State("first", enter=[Show(first)], go=[On(Hold("search.1", _HOLD), "gone"),
                                                    On(After(0.1), Outcome.NO_FIXATION)]),
            State("gone", enter=[Hide("search")], go=[On(After(0.016), "second")]),
            State("second", enter=[Show(second)], go=[On(Hold("search.1", _HOLD), Outcome.CORRECT),
                                                      On(After(0.5), Outcome.NO_RESPONSE)]),
        ],
    )
    at_first = _drawn(first, {}, trial)["search.1"]
    at_second = _drawn(second, {}, trial)["search.1"]

    result = _run(trial, {}, [at_first] * math.ceil(0.1 / _FRAME) + [at_second] * 200)

    assert result.visited == ("first", "gone", "second")
    assert result.outcome is Outcome.CORRECT


def test_an_update_that_draws_no_array_leaves_the_windows_where_the_objects_were_drawn():
    """An appearance that is not an array -- here `Blank` -- draws no objects, so their windows
    have nowhere new to go: they stay where the objects were last drawn, as they do when the
    array is hidden, and not where the array was first shown."""
    shown, moving, values = _MOVES["to another x-y position"]
    trial = Trial(
        start="shown",
        windows=[ObjectWindows(of="search", radius=1.0)],
        states=[
            State("shown", enter=[Show(shown)], go=[On(After(0.024), "moved")]),
            State("moved", enter=[moving], go=[On(After(0.024), "blanked")]),
            State("blanked", enter=[Update("search", looks=Blank())],
                  go=[On(Hold("search.1", _HOLD), Outcome.CORRECT),
                      On(After(0.5), Outcome.NO_RESPONSE)]),
        ],
    )
    new = _drawn(_moved(shown, moving), values, trial)["search.1"]

    result = _run(trial, values, [new] * 200)

    assert result.visited == ("shown", "moved", "blanked")
    assert result.outcome is Outcome.CORRECT


# ---------------------------------------------------------------------------
# A saccade to an array's distractor is one to any distractor, wherever it is
# ---------------------------------------------------------------------------
#
# `SaccadeTo` reaches the world directly (`World.happened`), so `Tracked` itself must judge an
# alias by the objects it names, each with its own eye. Until 2026-10-27 it judged
# `<of>.distractor` by a stand-in window at the target, so on a rig `WRONG_TARGET` was
# unreachable in the reference search task, a saccade to a distractor and then a corrective one to
# the target was rewarded, and a task listing the distractor edge first punished a saccade to the
# target. The simulated animal has no geometry, so no census could see it. The reference search
# task is run here whole, its settings below; its objects are drawn in grays, since where they are
# does not depend on their color.

_SEARCH_FRAME = 0.002
_SEARCH = {
    "fix_acquisition": 1.0, "fix_hold": 0.1, "response_deadline": 0.8, "target_hold": 0.1,
    "fix_window": 2.0, "object_window": 1.0, "array_eccentricity": 8.0, "set_size": 4,
    "target_index": 1, "array_rotation": 0.0, "fix_luminance": 40.0,
    "target_appearance": Disc(size=1.0, color=Gray(30.0)),
    "distractor_appearance": Disc(size=1.0, color=Gray(20.0)),
}


def _saccades(*to, dwell: int = 200, steps: int = 10, stay: int = 100, seed: int = 5,
              right: "tuple[float, float]" = (0.0, 0.0)) -> Replay:
    """Payloads that fixate the origin for `dwell` frames, then saccade to each point of `to` in
    turn, `steps` frames each, staying `stay` frames at each but the last, where they stay; the
    right eye `right` degrees from the left throughout."""
    rng = random.Random(seed)
    path, at = [(0.0, 0.0)] * dwell, (0.0, 0.0)
    for k, point in enumerate(to):
        path += [(at[0] + (point[0] - at[0]) * j / steps, at[1] + (point[1] - at[1]) * j / steps)
                 for j in range(1, steps + 1)]
        path += [point] * (stay if k < len(to) - 1 else 600)
        at = point
    payloads = []
    for n, (x, y) in enumerate(path):
        x, y = x + rng.gauss(0, 0.02), y + rng.gauss(0, 0.02)
        payload = json.loads(_payload(x, y, frame=n))
        payload["Right"] = json.loads(_payload(x + right[0], y + right[1], frame=n))["Right"]
        payloads.append((0.0, json.dumps(payload)))
    return Replay(payloads=payloads)


def _searched(*to, distractor_first: bool = False):
    """`tasks/visual_search`'s trial through the loop, gaze saccading to each of `to` in turn."""
    from tasks.visual_search import search

    if distractor_first:
        states = [replace(s, go=[s.go[1], s.go[0], *s.go[2:]]) if s.name == "array_on" else s
                  for s in search.states]
        search = replace(search, states=states)
    world = Tracked(Tracker(), _fitted_mapping(), search, _SEARCH_FRAME, _SEARCH,
                    source=_saccades(*to))
    effects = Recorded()
    return run_trial(search, world, _SEARCH_FRAME, values=_SEARCH, effects=effects), effects


def _search_drawn() -> dict:
    from tasks.visual_search import ARRAY, search

    return _drawn(ARRAY, _SEARCH, search)


@pytest.mark.parametrize("distractor", ["search.0", "search.2", "search.3"])
def test_a_saccade_to_any_distractor_is_wrong_target(distractor):
    """Each of the three distractors, not only one, and with its marks."""
    result, effects = _searched(_search_drawn()[distractor])

    assert result.outcome is Outcome.WRONG_TARGET
    assert ("mark", 4104) in effects.log and ("reward", "reward_correct") not in effects.log


@pytest.mark.parametrize("distractor_first", [False, True],
                         ids=["the target edge first", "the distractor edge first"])
def test_a_saccade_to_the_target_is_correct_whichever_edge_is_listed_first(distractor_first):
    """With the distractor edge listed first, the stand-in at the target took the saccade, and a
    task punished the right answer as `WRONG_TARGET`."""
    result, effects = _searched(_search_drawn()["search.1"], distractor_first=distractor_first)

    assert result.outcome is Outcome.CORRECT
    assert ("reward", "reward_correct") in effects.log


def test_a_distractor_saccade_corrected_to_the_target_is_scored_by_the_first():
    """The first saccade is the response the task's edges score: a saccade to a distractor and a
    corrective one to the target is `WRONG_TARGET`, unrewarded. It was rewarded as `CORRECT`."""
    drawn = _search_drawn()

    result, effects = _searched(drawn["search.0"], drawn["search.1"])

    assert result.outcome is Outcome.WRONG_TARGET
    assert ("reward", "reward_correct") not in effects.log


def test_a_saccade_to_a_distractor_of_a_moved_array_is_wrong_target():
    """After an `Update` moved the array, a saccade to one of its distractors where it is now drawn
    is `WRONG_TARGET`, and one to where that distractor was is no response at all."""
    ring = replace(_RING, radius=8.0)
    shown = Stimulus("search", at=(0.0, 0.0), looks=ring)
    update = Update("search", at=(3.0, -2.0))
    trial = Trial(
        start="shown",
        windows=[ObjectWindows(of="search", radius=1.5)],
        states=[
            State("shown", enter=[Show(shown)], go=[On(After(0.02), "moved")]),
            State("moved", enter=[update],
                  go=[On(SaccadeTo("search.target"), Outcome.CORRECT),
                      On(SaccadeTo("search.distractor"), Outcome.WRONG_TARGET),
                      On(After(0.6), Outcome.NO_RESPONSE)]),
        ],
    )

    def to(where):
        world = Tracked(Tracker(), _fitted_mapping(), trial, 0.002, {}, source=_saccades(where))
        return run_trial(trial, world, 0.002, values={}, effects=Recorded()).outcome

    assert to(_drawn(_moved(shown, update), {}, trial)["search.2"]) is Outcome.WRONG_TARGET
    assert to(_drawn(shown, {}, trial)["search.2"]) is Outcome.NO_RESPONSE


def test_a_saccade_to_a_distractor_is_judged_for_the_eye_its_family_scores():
    """Each distractor's window is judged for its own eye: a family scoring the left eye takes a
    saccade landing the left eye on a distractor while the right eye looks 6° away, where the two
    eyes' mean would be 3° off it."""
    ring = replace(_RING, radius=8.0)
    shown = Stimulus("search", at=(0.0, 0.0), looks=ring)
    trial = Trial(
        start="shown",
        windows=[ObjectWindows(of="search", radius=1.5, eye="left")],
        states=[State("shown", enter=[Show(shown)],
                      go=[On(SaccadeTo("search.target"), Outcome.CORRECT),
                          On(SaccadeTo("search.distractor"), Outcome.WRONG_TARGET),
                          On(After(0.8), Outcome.NO_RESPONSE)])],
    )
    to = _drawn(shown, {}, trial)["search.2"]
    world = Tracked(Tracker(), _fitted_mapping(), trial, 0.002, {},
                    source=_saccades(to, right=(6.0, 0.0)))

    assert run_trial(trial, world, 0.002, values={}, effects=Recorded()).outcome is \
        Outcome.WRONG_TARGET


def test_judging_a_saccade_builds_nothing_in_its_frame():
    """`happened` runs on every frame an unclaimed saccade is pending (XC-410), so judging where
    it landed builds no tuple, list, dict or set: the bytecode of the two functions on that path
    has no `BUILD_` instruction (the round-1 re-review). `in_window`, which both reach, builds
    nothing either (XC-413; `test_judging_a_window_builds_nothing_in_its_frame`)."""
    import dis

    built = sorted({(function.__name__, instruction.opname)
                    for function in (Tracked.happened, Tracked._landed)
                    for instruction in dis.get_instructions(function)
                    if instruction.opname.startswith("BUILD_")})

    assert built == []


# ---------------------------------------------------------------------------
# Judging a window builds nothing in its frame (XC-413)
# ---------------------------------------------------------------------------
#
# `in_window` runs on every frame for every window a guard asks about (`run.run_trial`'s
# membership), so CLAUDE.md's hot-path discipline holds it: nothing allocated per frame. Until
# 2026-10-28 every call built a list of the eyes' positions, a one-eye tuple, two generators for
# their mean, the window's center again from however the task wrote it, and each eye's gaze again
# from the tracker's sample, window after window.

#: The instructions that build an object, by what they build, the first prefix an instruction's name
#: has deciding: a container and what fills one, a string, a slice, a function or its cell, a
#: generator, an iterator, a call's packed arguments, and anything else built. Named by what is
#: built, not by instruction, so Python 3.11 to 3.13 read alike: one string is `FORMAT_VALUE` in
#: 3.12 and `FORMAT_SIMPLE` in 3.13. **A float is not counted**: CPython boxes every float an
#: arithmetic step makes, and no pure-Python path avoids it.
_BUILDING = (
    ("BUILD_TUPLE", "tuple"), ("LIST_TO_TUPLE", "tuple"),
    ("BUILD_LIST", "list"), ("LIST_", "list"),
    ("BUILD_MAP", "dict"), ("BUILD_CONST_KEY_MAP", "dict"), ("DICT_", "dict"), ("MAP_ADD", "dict"),
    ("BUILD_SET", "set"), ("SET_ADD", "set"), ("SET_UPDATE", "set"),
    ("BUILD_STRING", "string"), ("FORMAT_", "string"), ("CONVERT_VALUE", "string"),
    ("BUILD_SLICE", "slice"), ("BINARY_SLICE", "slice"),
    ("MAKE_", "function"), ("SET_FUNCTION_ATTRIBUTE", "function"),
    ("RETURN_GENERATOR", "generator"), ("GET_ITER", "iterator"),
    ("CALL_FUNCTION_EX", "arguments"), ("CALL_INTRINSIC", "object"), ("BUILD_", "object"),
)


def _what_builds(opname: str) -> "str | None":
    return next((what for prefix, what in _BUILDING if opname.startswith(prefix)), None)


def _built_on(call, *args) -> "list[tuple[str, str]]":
    """What each Python function `call(*args)` runs can build, by the function's qualified name,
    `call` itself included (`_BUILDING`). **The functions are found by running it**
    (`sys.setprofile`), so the measure follows whatever the path calls, which a list of functions
    written into a test does not; **each is read whole** (`dis`), so a branch this call did not take
    is read too. The collector is off meanwhile, so no finalizer runs inside.

    **It cannot see a call that allocates.** It reads instructions, and a call is one instruction
    whatever it does: `str(frame)`, `list(x)` or `dict(x)` in `in_window` would pass it (the
    gaze-followups review's K3), as would anything a function written in C allocates inside. Such
    calls are kept off the path by reading it, not by this."""
    import dis
    import gc
    import sys

    codes = set()

    def entered(frame, event, arg):
        if event == "call":
            codes.add(frame.f_code)

    collecting = gc.isenabled()
    gc.disable()
    sys.setprofile(entered)
    try:
        call(*args)
    finally:
        sys.setprofile(None)
        if collecting:
            gc.enable()
    return sorted({(code.co_qualname, what)
                   for code in codes for instruction in dis.get_instructions(code)
                   if (what := _what_builds(instruction.opname)) is not None})


#: The settings `_judged_world`'s trial runs with.
_JUDGED = {"ecc": 12.0, "dir": 200.0, "r": 2.0}


def _judged_world():
    """A world over a window centered by eccentricity and direction, each a setting, and an array
    moved by an `Update`, its family scoring the left eye; with its tracker, its trial, and the
    array as shown and as moved."""
    from wl_xcon.task import Window

    shown = Stimulus("search", at=(0.0, 0.0), looks=_RING)
    move = Update("search", at=Polar(P("ecc"), P("dir")))
    trial = Trial(
        start="shown",
        windows=[Window("w", at=Polar(P("ecc"), P("dir")), radius=P("r"), on="s"),
                 ObjectWindows(of="search", radius=1.0, eye="left")],
        states=[
            State("shown", enter=[Show(Stimulus("s", at=Polar(P("ecc"), P("dir")))), Show(shown)],
                  go=[On(After(0.04), "moved")]),
            State("moved", enter=[move], go=[On(Hold("search.1", _HOLD), Outcome.CORRECT),
                                             On(After(0.5), Outcome.NO_RESPONSE)]),
        ],
    )
    tracker = Tracker()
    world = Tracked(tracker, _fitted_mapping(), trial, _FRAME, _JUDGED)
    return world, tracker, trial, shown, _moved(shown, move)


def test_judging_a_window_builds_nothing_in_its_frame():
    """Once the frame's display has run, as the trial loop runs it before asking: a window centered
    by settings, an array's object windows before and after an `Update` moves them, an object only
    a larger set would have, a window the task does not have, each for both eyes and for each eye
    alone, with gaze fresh and with it stale."""
    world, tracker, _, shown, moved = _judged_world()

    built = set()
    for frame, array, at in ((1, shown, (3.0, 0.0)), (2, moved, (-11.0, -4.0)), (100, moved, None)):
        if at is not None:
            tracker.accept(parse(_payload(*at), at=world.when(frame)))
        world.display({"s": Stimulus("s", at=(0.0, 0.0)), "search": array}, frame)
        for name in ("w", "search.1", "search.target", "search.distractor", "search.5", "nowhere"):
            for eye in ("both", "left", "right"):
                built.update(_built_on(world.in_window, name, frame, eye))

    assert sorted(built) == []


def test_a_window_center_resolved_before_the_trial_follows_an_update_that_moves_the_array():
    """Resolved between trials, each placement's centers are swapped in on the frame the display
    first carries the `Update`: gaze where object 1 is drawn after it, by eccentricity and direction
    from settings, is inside its window, and gaze where object 1 was is no longer. Before it, the
    windows are where the `Show` drew the array."""
    world, tracker, trial, shown, moved = _judged_world()
    old = _drawn(shown, _JUDGED, trial)["search.1"]
    new = _drawn(moved, _JUDGED, trial)["search.1"]
    assert _apart(old, new) > 2.0

    def at(frame: int, gaze, array) -> bool:
        tracker.accept(parse(_payload(*gaze), at=world.when(frame)))
        world.display({"s": Stimulus("s", at=(0.0, 0.0)), "search": array}, frame)
        return world.in_window("search.1", frame, "left")

    assert at(1, old, shown) and not at(2, new, shown)
    assert at(3, new, moved) and not at(4, old, moved)


#: **What still builds in a frame, once a frame however many windows are asked**: each eye's gaze
#: from the tracker's sample, its dual-Purkinje vector (`eye.EyeReading.dpi`) through its map
#: (`calibration.Mapping.degrees`, `_for` and `EyeMap.degrees`, its polynomial's terms among them),
#: and the two eyes' mean the saccade detector is fed (`gaze.Tracked.gaze_cyclopean`). `_for`'s
#: string is its refusal's message, built only for a name that is no eye.
_ONCE_A_FRAME = {
    ("EyeReading.dpi", "tuple"),
    ("Mapping._for", "tuple"),
    ("Mapping._for", "string"),
    ("Mapping.degrees", "tuple"),
    ("EyeMap.degrees", "tuple"),
    ("Tracked.gaze_cyclopean", "tuple"),
}


def test_each_eye_s_gaze_is_converted_once_a_frame_and_builds_only_the_map_s_tuples():
    """Where the frame's gaze is first read, for the detector, as the display reads it: each eye's
    sample through its map builds the tuples the map's interface returns, and nothing else does."""
    world, tracker, _, _, _ = _judged_world()
    tracker.accept(parse(_payload(3.0, 0.0), at=world.when(1)))

    assert set(_built_on(world.gaze_cyclopean, 1)) <= _ONCE_A_FRAME


def test_a_second_sample_within_a_frame_is_judged_not_the_frame_s_first():
    """Each eye's gaze is converted once a frame, and again when the tracker accepts a sample
    since: after a second sample in the frame, a window is judged by it, and the detector's mean
    is taken from it, whichever is asked first. Keyed by the frame alone, either would read the
    frame's first sample."""
    from wl_xcon.task import position_of

    on_w = position_of(Polar(_JUDGED["ecc"], _JUDGED["dir"]), {})

    def second_sample():
        world, tracker, _, _, _ = _judged_world()
        tracker.accept(parse(_payload(*on_w), at=world.when(1)))
        world.display({}, 1)
        assert world.in_window("w", 1)
        tracker.accept(parse(_payload(-20.0, 10.0), at=world.when(1)))
        return world

    window_first = second_sample()
    assert not window_first.in_window("w", 1)
    assert window_first.gaze_cyclopean(1) == pytest.approx((-20.0, 10.0), abs=1e-6)

    mean_first = second_sample()
    assert mean_first.gaze_cyclopean(1) == pytest.approx((-20.0, 10.0), abs=1e-6)
    assert not mean_first.in_window("w", 1)


#: A task whose one window is centered by a whole-point setting with a choice that holds no value
#: (the gaze-followups review's first, I1): it loads with no finding (XC-415, narrowed to this case;
#: a choice that is a value and no position is refused at load), and the window is
#: judged only by `SaccadeTo`, so a trial with no saccade never asks about it.
_NEVER_ASKED_TASK = """
from wl_xcon.photometry import Gray
from wl_xcon.task import (
    CRITERION, NO_CHOICE, NOT_DIFFICULTY, OWED, After, Counting, Disc, Meaning, On, Outcome, P,
    Param, Polar, ReactionTime, SaccadeTo, Show, State, Stimulus, Task, Trial, Window,
)

trial = Trial(
    start="only",
    params=[Param("where", unit="deg", choices=(Polar(8.0, 0.0), None))],
    windows=[Window("w", at=P("where"), radius=1.0, on="t")],
    states=[State("only",
                  enter=[Show(Stimulus("t", at=(0.0, 0.0), looks=Disc(size=0.5, color=Gray(40.0))))],
                  go=[On(SaccadeTo("w"), Outcome.CORRECT), On(After(0.05), Outcome.NO_RESPONSE)])],
    counting=Counting(after_stimulus=OWED, appears="only"),
)
TASK = Task(
    {"only": trial},
    default="only",
    reaction_time=ReactionTime("only", (Outcome.CORRECT,), "the one state's length"),
    choice=NO_CHOICE,
    meanings={"where": Meaning(NOT_DIFFICULTY, CRITERION, note="where the window is")},
)
"""


def test_a_window_no_trial_asks_about_raises_only_when_asked(tmp_path):
    """**A window that cannot be placed with a trial's values raises where it is asked about, never
    when the world is built** (the gaze-followups review, I1): a session whose trials never ask
    about it runs to its end, as it did before XC-413 resolved each window between trials, and
    the window still raises when asked. Raised at the build, it stopped the session on its first
    trial."""
    path = tmp_path / "never_asked.py"
    path.write_text(_NEVER_ASKED_TASK)
    built = []

    def world(trial, values, index):
        built.append(Tracked(Tracker(), _fitted_mapping(), trial, 0.008, values,
                             source=Replay(payloads=[(0.0, _payload(0.0, 0.0, frame=n))
                                                     for n in range(100)])))
        return built[-1]

    spec = SessionSpec(
        task=str(path), allocation="tasks/allocation.py", root=tmp_path,
        session_id="2027-01-14_01", subject="REFERENCE", trials=2, frame_period=0.008, seed=11,
        values={"where": None}, bounds=_calibration_bounds(), already_delivered_today=0.0,
        deployment=Deployment.RIG_FIXED, geometry=DIRECT, session_kind="training",
        calibration=SRGB,
    )
    session = _marked(Session(spec, card=Card(), pump=Pump(), world=world))

    session.run()

    assert session.stopped_because == "every block is finished"
    assert len(built) == 2
    with pytest.raises(TypeError):
        built[-1].in_window("w", 1)
