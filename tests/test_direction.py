"""Every direction shown or written from 0° to 360°, and none at the center (the PI, 2026-10-30).

Asked "Today a task that writes 270 degrees sees 270 on the console but -90 in the record", the PI
answered "0 to 360 everywhere": "As tasks write it, e.g. 270. One form in the task, the console and
the record"; and asked what the center has, "Empty at center": "The record writes no direction at
eccentricity 0, and the console shows only '0°'. Matches wl-preproc." wl-preproc normalizes as the
rig does (its spec, amendment 1, 2026-10-30): the angle in degrees, mod 360, then 0 where that
gives 360.0. Every expectation here is written out, never computed by `wl_xcon.geometry`; the
directions the record writes are read against `_angles`, the PI's formulas.
"""

from __future__ import annotations

import json
import math
import random

import pytest

import _angles
from _rig import DIRECT
from wl_xcon.check import check
from wl_xcon.levels import Position
from wl_xcon.photometry import Gray
from wl_xcon.record import SessionRecord
from wl_xcon.task import (
    After, Array, Disc, Hold, On, Outcome, P, Param, Polar, Show, State, Stimulus, Trial, Window,
)


def _turned(direction: float, want: float) -> bool:
    """`direction` is in [0, 360) and is `want` to a billionth of a degree, read round the circle,
    so 359.9999999999 and 0 are one direction."""
    apart = abs(direction - want) % 360.0
    return 0.0 <= direction < 360.0 and min(apart, 360.0 - apart) < 1e-9


# --- The one helper ----------------------------------------------------------------------------


def test_the_shown_form_is_the_angle_mod_360_then_0_where_that_gives_360_and_none_at_the_center():
    """`geometry.shown_direction`, which every edge calls, and `geometry.shown_polar`, a per-axis
    position's eccentricity and shown direction. A tiny negative angle is 360.0 mod 360 in float64,
    which is why the second step exists, pinned here as wl-preproc pins it. The center is decided
    as the math does, with no tolerance: a position 1e-300° off it has a direction."""
    from wl_xcon import geometry

    shown, polar = geometry.shown_direction, geometry.shown_polar
    assert -1e-15 % 360.0 == 360.0
    assert shown(-1e-15) == 0.0 and math.copysign(1.0, shown(-1e-15)) == 1.0
    assert shown(-90.0) == 270.0 and shown(270.0) == 270.0
    assert shown(-90) == 270 and isinstance(shown(-90), int)
    assert shown(180.0) == 180.0 and shown(-180.0) == 180.0
    assert shown(360.0) == 0.0 and shown(720.0) == 0.0 and shown(-360.0) == 0.0
    assert math.copysign(1.0, shown(-0.0)) == 1.0
    assert polar(0.0, 0.0) == (0.0, None) and polar(-0.0, -0.0) == (0.0, None)
    assert polar(0.0, -8.0) == (8.0, 270.0) and polar(-8.0, 0.0) == (8.0, 180.0)
    assert polar(8.0, -1e-15) == (8.0, 0.0)
    assert polar(1e-300, 0.0)[1] == 0.0 and polar(0.0, -1e-300)[1] == 270.0
    draw = random.Random(20261030)
    for _ in range(2000):
        direction = draw.uniform(-1080.0, 1080.0)
        turned = shown(direction)
        assert 0.0 <= turned < 360.0
        assert (turned - direction) / 360.0 == pytest.approx(round((turned - direction) / 360.0),
                                                             abs=1e-12)


# --- The record ---------------------------------------------------------------------------------


def _shown(stimulus, frame: int = 1, presentation: int = 0):
    from wl_xcon.run import Placed

    return Placed(stimulus, frame, "show", (), presentation, None)


def _line(tmp_path, placed=(), params=None) -> dict:
    """The one line a record writes for a trial that drew `placed` with `params`."""
    record = SessionRecord.open(tmp_path, session_id="2027-01-14_01", subject="A")
    record.trial(index=1, outcome="correct", params=params or {}, run=0,
                 position=Position.lone(1), fluid_ml=0.0, last_reward_at=None, placed=placed)
    return json.loads((record.directory / "trials.jsonl").read_text())


def test_the_record_writes_each_stimulus_s_direction_from_0_to_360_and_none_at_the_center(tmp_path):
    """REC-26's `stimuli`: a task's `Polar(8, -90)` is written 270, a position straight down (x, y)
    (0, -8) is 270, never -90, leftward 180, and one a hair below rightward, whose direction mod
    360 rounds to 360.0, is 0. At the center the direction is null, the eccentricity 0 and (x, y)
    (0, 0) beside it. Each eye's own position and each object of an array likewise: the object an
    array puts straight down is at 270."""
    lit = Disc(size=0.5, color=Gray(40.0))
    entries = _line(tmp_path, tuple(_shown(s, 1, i) for i, s in enumerate((
        Stimulus("down", at=Polar(8.0, -90.0), looks=lit),
        Stimulus("below", at=(0.0, -8.0), looks=lit),
        Stimulus("left", at=(-8.0, 0.0), looks=lit),
        Stimulus("hair", at=(8.0, -1e-15), looks=lit),
        Stimulus("fix", at=(0.0, 0.0), looks=lit),
        Stimulus("pair", at=(0.0, 0.0), at_left=Polar(3.0, -30.0), at_right=(0.0, 0.0), looks=lit),
        Stimulus("ring", at=(0.0, 0.0), looks=Array(n=4, radius=5.0, phase=0.0, looks=lit,
                                                    among=lit)),
    ))))["stimuli"]
    down, below, left, hair, fix, pair, ring = entries

    for entry, want in ((down, 270.0), (below, 270.0), (left, 180.0)):
        assert _turned(entry["direction"], want), (entry["name"], entry["direction"])
        assert entry["eccentricity"] == pytest.approx(8.0, abs=1e-9)
    assert hair["direction"] == 0.0 and math.copysign(1.0, hair["direction"]) == 1.0
    for center in (fix, pair["right"], ring):
        assert (center["eccentricity"], center["direction"], center["x"], center["y"]) == (
            0.0, None, 0.0, 0.0)
    assert _turned(pair["left"]["direction"], 330.0)
    assert [_turned(o["direction"], want) for o, want in zip(ring["objects"], (0, 90, 180, 270))] \
        == [True] * 4


def test_a_setting_s_polar_value_is_recorded_from_0_to_360_and_with_none_at_the_center(tmp_path):
    """REC-25's form, wherever a value is written: the task's own `Polar(8, -90)` is recorded 270,
    an integer as an integer, its (x, y) beside it unchanged; `Polar(8, -1e-15)` 0; and
    `Polar(0, 45)`, the center, with no direction."""
    params = _line(tmp_path, params={
        "down": Polar(8.0, -90.0), "whole": Polar(8, -90), "kept": Polar(8.0, 270.0),
        "hair": Polar(8.0, -1e-15), "center": Polar(0.0, 45.0)})["params"]

    assert params["down"]["direction"] == 270.0 and params["kept"]["direction"] == 270.0
    assert params["whole"]["direction"] == 270 and isinstance(params["whole"]["direction"], int)
    assert params["down"]["y"] == pytest.approx(-8.0, abs=1e-12)
    assert params["hair"]["direction"] == 0.0
    assert params["center"] == {"eccentricity": 0.0, "direction": None, "x": 0.0, "y": 0.0}


# --- The review report, the console, the page and `wlx console` -------------------------------


def test_the_report_and_the_console_show_every_direction_from_0_to_360_and_none_at_the_center():
    """The rig's words for a position (`review.position_words`), which the review report, the
    console's parameter card, a staged change, the changes feed and `wlx console` all show: a
    task's `Polar(8, -90)` reads 270, a pair straight down 270, leftward 180, a direction a
    thousandth of a degree under 360 as shown reads 0, never 360, and the center "0°" with no
    direction, a `Polar(0, 45)` as a pair (0, 0) is."""
    from wl_xcon.cli import _shown
    from wl_xcon.link import ParamRow
    from wl_xcon.review import position_words

    pairs = ((0.0, -8.0), (-8.0, 0.0), (8.0, -0.0004), (8.0, -1e-6), (0.0, 0.0))
    assert [position_words(pair, pairs) for pair in pairs] == [
        "8° at 270° · (x, y) (0, -8)",
        "8° at 180° · (x, y) (-8, 0)",
        "8° at 359.997° · (x, y) (8, -0.0004)",
        "8° at 0° · (x, y) (8, -1e-06)",
        "0° · (x, y) (0, 0)",
    ]
    assert position_words(Polar(8.0, -90.0)) == "8° at 270° · (x, y) (0, -8)"
    assert position_words(Polar(8, -90)) == "8° at 270° · (x, y) (0, -8)"
    assert position_words(Polar(8.0, -180.0)) == "8° at 180° · (x, y) (-8, 0)"
    assert position_words(Polar(8.0, -1e-9)) == "8° at 0° · (x, y) (8, 0)"
    assert position_words(Polar(0.0, 45.0)) == "0° · (x, y) (0, 0)"
    assert position_words(Polar(0.0, P("dir"))) == "0°"
    assert position_words(Polar(P("ecc"), -90.0)) == "ecc at 270°"
    assert position_words(Polar(math.inf, -90.0)) == "not a position: inf° at 270°"
    row = ParamRow.of("pos", "deg", None, None, Polar(8.0, -90.0), False)
    assert (row.value, row.position) == (None, "8° at 270° · (x, y) (0, -8)")
    assert _shown(Polar(0.0, 45.0)) == "0° · (x, y) (0, 0)"


def test_the_review_report_places_each_stimulus_and_window_from_0_to_360():
    """The report's tables: a window and a stimulus a task places at `Polar(8, -90)` read 270,
    and the fixation point at the center has no direction."""
    from wl_xcon.review import render

    trial = Trial(
        start="on",
        windows=[Window("a", at=Polar(8.0, -90.0), radius=1.0, on="a")],
        states=[State("on", enter=[Show(Stimulus("a", at=Polar(8.0, -90.0), looks=Disc())),
                                   Show(Stimulus("f", at=(0.0, 0.0), looks=Disc()))],
                      go=[On(After(1.0), Outcome.NO_RESPONSE)])],
    )

    artifact = render(trial)

    assert "| `a` | 8° at 270° · (x, y) (0, -8) |" in artifact
    assert "| `on` | `a` | 8° at 270° · (x, y) (0, -8) |" in artifact
    assert "| `on` | `f` | 0° · (x, y) (0, 0) |" in artifact
    assert "-90" not in artifact


# --- The checker's sentences ------------------------------------------------------------------


def _shows(at, *params, looks=None) -> Trial:
    return Trial(
        start="on",
        params=list(params),
        windows=[Window("w", at=(0.0, 0.0), radius=2.0, on="s")],
        states=[State("on", enter=[Show(Stimulus("s", at=at, looks=looks or Disc()))],
                      go=[On(After(1.0), Outcome.ABORT)])],
    )


def test_a_stimulus_placed_off_the_screen_is_named_by_its_direction_from_0_to_360():
    """Check 8's sentence names where a state shows a stimulus as the task placed it: `Polar(80,
    -90)` reads direction 270, a setting's name as its name, and an array about the center,
    whose ring runs off the field, eccentricity 0 and no direction, a direction a setting holds
    included."""
    def said(trial: Trial) -> str:
        (found,) = [f for f in check(trial, geometry=DIRECT) if f.code == "stimulus-off-screen"]
        return found.detail

    assert "shows a stimulus at (eccentricity 80, direction 270)" in said(
        _shows(Polar(80.0, -90.0)))
    assert "shows a stimulus at (eccentricity ecc, direction 270)" in said(_shows(
        Polar(P("ecc"), -90.0), Param("ecc", unit="deg", low=2.0, high=80.0)))
    ring = Array(n=4, radius=50.0, looks=Disc(), among=Disc())
    assert "shows a stimulus at (eccentricity 0) " in said(_shows(Polar(0.0, 45.0), looks=ring))
    assert "shows a stimulus at (eccentricity 0) " in said(_shows(
        Polar(0.0, P("dir")), Param("dir", unit="deg", choices=(0.0, 90.0)), looks=ring))


def test_a_bad_placement_sentence_names_a_position_by_its_direction_from_0_to_360():
    """`bad-placement`: a coordinate placed by a setting one of whose choices is a whole position
    names that choice in the rig's words, its direction 270 where the task wrote -90."""
    trial = _shows((P("x"), 0.0), Param("x", unit="deg", choices=(1.0, Polar(8.0, -90.0))))

    (found,) = [f for f in check(trial) if f.code == "bad-placement"]

    assert "which can be 8° at 270° · (x, y) (0, -8). That is a whole position" in found.detail


# --- Internal math keeps its own convention -----------------------------------------------------


def _units(positions):
    """Each per-axis position's direction, `(tan x, tan y, 1)` made unit, as rows."""
    import numpy as np

    v = np.array([[math.tan(math.radians(x)), math.tan(math.radians(y)), 1.0]
                  for x, y in positions])
    return v / np.linalg.norm(v, axis=1, keepdims=True)


def test_the_shown_form_changes_no_window_overlap_or_interval_result():
    """The rule is at the edges alone (the PI's decision is about what is shown and written):
    `geometry`'s direction intervals, `check`'s and every window's are read as given, a whole turn
    either way. A window at `Polar(8, -90)` and one at `Polar(8, 270)` are one window; intervals
    written across 0 (-30° to 30°) give what the same written a turn on (330° to 390°) does, and
    what a brute-force minimum over the positions gives; and `polar_of_deg`, the math's own
    inverse, still reads straight down as -90."""
    import numpy as np

    from wl_xcon.geometry import least_separation_deg, polar_box_deg, polar_deg, polar_of_deg

    assert polar_of_deg(0.0, -8.0) == (8.0, -90.0)
    for a, b in (((-30.0, 30.0), (330.0, 390.0)), ((-90.0, -90.0), (270.0, 270.0)),
                 ((-200.0, -150.0), (160.0, 210.0))):
        boxes = [sum(polar_box_deg((8.0, 8.0), side), ()) for side in (a, b)]
        assert boxes[0] == pytest.approx(boxes[1], abs=1e-9)
        for other in (((10.0, 12.0), (170.0, 200.0)), ((6.0, 6.0), (-100.0, -80.0)),
                      ((6.0, 6.0), (10.0, 10.0))):
            written = least_separation_deg([(5.0, 9.0)], [a], [other[0]], [other[1]],
                                           polar_a=True, polar_b=True)
            turned = least_separation_deg([(5.0, 9.0)], [b], [other[0]], [other[1]],
                                          polar_a=True, polar_b=True)
            assert written == pytest.approx(turned, abs=1e-9)
            near = _units([polar_deg(e, t) for e in np.linspace(5.0, 9.0, 41)
                           for t in np.linspace(a[0], a[1], 121)])
            far = _units([polar_deg(e, t) for e in np.linspace(*other[0], 21)
                          for t in np.linspace(*other[1], 61)])
            brute = math.degrees(math.acos(min(1.0, float((near @ far.T).max()))))
            assert written <= brute + 1e-9 and written == pytest.approx(brute, abs=0.05)
    gaps = []
    for down in (Polar(8.0, -90.0), Polar(8.0, 270.0)):
        trial = Trial(start="w", windows=[Window("a", at=down, radius=1.0, on="s"),
                                          Window("b", at=Polar(8.5, -88.0), radius=1.0, on="s")],
                      states=[State("w", enter=[Show(Stimulus("s", at=(0.0, 0.0), looks=Disc()))],
                                    go=[On(Hold("a", 0.1), Outcome.CORRECT),
                                        On(Hold("b", 0.1), Outcome.WRONG_TARGET),
                                        On(After(1.0), Outcome.NO_RESPONSE)])])
        gaps.append([f.detail for f in check(trial) if f.code == "overlapping-windows"])
    assert gaps[0] and gaps[0] == gaps[1]
