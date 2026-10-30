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

import dataclasses
import json
import math
import random

import pytest

import _angles
from _rig import DIRECT
from wl_xcon.check import check
from wl_xcon.findings import SESSION_KINDS
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


def test_the_record_writes_a_zero_eccentricity_and_its_x_y_as_0_never_minus_0(tmp_path):
    """Review 1's M2: the PI's "the console shows only '0°'" reads a center written `Polar(-0.0,
    45)` as 0 too, never -0, in a setting's value and in a stimulus's entry, each number with
    its sign."""
    line = _line(tmp_path, (_shown(Stimulus("fix", at=Polar(-0.0, 45.0), looks=Disc())),),
                 {"center": Polar(-0.0, 45.0)})
    for written in (line["params"]["center"], line["stimuli"][0]):
        numbers = [written[k] for k in ("eccentricity", "x", "y")]
        assert numbers == [0.0] * 3 and written["direction"] is None
        assert [math.copysign(1.0, n) for n in numbers] == [1.0] * 3, written


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

    pairs = ((0.0, -8.0), (-8.0, 0.0), (8.0, -0.0004), (8.0, -1e-6), (0.0, 0.0), (0.0003, 0.0))
    assert [position_words(pair, pairs) for pair in pairs] == [
        "8° at 270° · (x, y) (0, -8)",
        "8° at 180° · (x, y) (-8, 0)",
        "8° at 359.997° · (x, y) (8, -0.0004)",
        "8° at 0° · (x, y) (8, -1e-06)",
        "0° · (x, y) (0, 0)",
        "0° · (x, y) (0.0003, 0)",
    ]
    assert position_words(Polar(8.0, -90.0)) == "8° at 270° · (x, y) (0, -8)"
    assert position_words(Polar(8, -90)) == "8° at 270° · (x, y) (0, -8)"
    assert position_words(Polar(8.0, -180.0)) == "8° at 180° · (x, y) (-8, 0)"
    assert position_words(Polar(8.0, -1e-9)) == "8° at 0° · (x, y) (8, 0)"
    assert position_words(Polar(0.0, 45.0)) == "0° · (x, y) (0, 0)"
    # Review 1's M2: the center is "0°", never "-0°", and keeps the (x, y) it knows, (0, 0)
    # whatever direction a setting would give it.
    assert position_words(Polar(-0.0, 45.0)) == "0° · (x, y) (0, 0)"
    assert position_words(Polar(0.0, P("dir"))) == "0° · (x, y) (0, 0)"
    assert position_words(Polar(-0.0, P("dir"))) == "0° · (x, y) (0, 0)"
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
    # Review 1's M1: a direction just under 360 that prints as 360 reads 0.
    assert "shows a stimulus at (eccentricity 80, direction 0)" in said(_shows(Polar(80.0, -1e-9)))
    assert "shows a stimulus at (eccentricity ecc, direction 270)" in said(_shows(
        Polar(P("ecc"), -90.0), Param("ecc", unit="deg", low=2.0, high=80.0)))
    ring = Array(n=4, radius=50.0, looks=Disc(), among=Disc())
    assert "shows a stimulus at (eccentricity 0) " in said(_shows(Polar(0.0, 45.0), looks=ring))
    assert "shows a stimulus at (eccentricity 0) " in said(_shows(Polar(-0.0, 45.0), looks=ring))
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


# --- Load warnings: one position written two ways (the PI, 2026-10-30) -------------------------


def _placed_by(at, *params, where="stimulus", looks=None, view="either") -> Trial:
    """A trial placing a stimulus, a window or an update (`where`) at `at`, with `params`; or, where
    `"eyes"`, a stimulus at (0, 0) with `at` its two per-eye positions."""
    from wl_xcon.task import Update

    lit = looks or Disc(size=0.5, color=Gray(40.0))
    if where == "eyes":
        shown = Stimulus("s", at=(0.0, 0.0), at_left=at[0], at_right=at[1], looks=lit)
    else:
        shown = Stimulus("s", at=(0.0, 0.0) if where != "stimulus" else at, looks=lit)
    enter = [Show(shown)] + ([Update("s", at=at)] if where == "update" else [])
    windows = [Window("w", at=at if where == "window" else (0.0, 0.0), radius=1.0, on="s")]
    return Trial(start="on", params=list(params), windows=windows, view=view,
                 states=[State("on", enter=enter, go=[On(Hold("w", 0.1), Outcome.CORRECT),
                                                      On(After(1.0), Outcome.NO_RESPONSE)])])


def _warned(trial: Trial, code: str) -> list:
    found = [f for f in check(trial) if f.code == code]
    assert all(not f.blocking and f.accepted_in == SESSION_KINDS for f in found), found
    return found


def _said_of(trial: Trial, code: str) -> str:
    """The one warning `code` `trial` gives, its sentence."""
    (found,) = _warned(trial, code)
    return found.detail


DIRECTION = "direction-outside-0-360"
ECCENTRICITY = "negative-eccentricity"
STIMULUS_REASON = "a stimulus's entry records"


def _dir(**declared) -> Param:
    return Param("dir", unit="deg", **declared)


def test_a_setting_used_as_a_direction_that_can_be_outside_0_to_360_is_warned_at_load():
    """Review 1's I1, the PI, 2026-10-30, "Warn at load": "A setting used as a direction that offers
    a value outside 0-360 gets a load warning, never a refusal, so the task author writes 270. The
    docs say a setting's number is shown as written." A setting placing a `Polar`'s direction -- a
    stimulus's, a window's, an update's -- is shown on the console and recorded in `params` as the
    number it holds: a choice or a start outside [0, 360) is warned once, in every kind, saying
    what to write. 0 to 360 as a range, choices inside it, a coordinate's setting, a `Polar`'s own
    literal direction and a whole position's choices (each shown from 0 to 360) are not."""
    down = _dir(choices=(-90.0, 90.0))
    said = _said_of(_placed_by(Polar(8.0, P("dir")), down), DIRECTION)
    assert ("setting 'dir' places the direction of state 'on' shows stimulus 's' and can be -90, "
            "outside 0 to 360") in said
    assert "write 270 for -90" in said
    (found,) = _warned(_placed_by(Polar(8.0, P("dir")), down), DIRECTION)
    assert found.subjects == ("setting 'dir'",)
    said = _said_of(_placed_by(Polar(8.0, P("dir")), _dir(choices=(0.0, 360.0)), where="update"),
                    DIRECTION)
    assert "updates stimulus 's'" in said and "write 0 for 360" in said
    said = _said_of(_placed_by(Polar(8.0, P("dir")), _dir(low=0.0, high=360.0, start=360.0)),
                    DIRECTION)
    assert "its start 360" in said and "write 0 for 360" in said
    # Re-review 2's S3: a start and a range both outside are each told what to write.
    said = _said_of(_placed_by(Polar(8.0, P("dir")), _dir(low=-180.0, high=180.0, start=-90.0)),
                    DIRECTION)
    assert "write 270 for -90" in said and "write 0 to 360" in said
    twice = dataclasses.replace(_placed_by(Polar(8.0, P("dir")), down, where="window"),
                                states=_placed_by(Polar(8.0, P("dir")), down).states)
    assert len(_warned(twice, DIRECTION)) == 1
    for quiet in (
            _placed_by(Polar(8.0, P("dir")), _dir(low=0.0, high=360.0)),
            _placed_by(Polar(8.0, P("dir")), _dir(choices=(0.0, 90.0, 270.0))),
            _placed_by((P("dir"), 0.0), _dir(choices=(-5.0, 5.0))),
            _placed_by(Polar(8.0, -90.0)),
            _placed_by(P("pos"), Param("pos", unit="deg", choices=(Polar(8.0, -90.0),))),
    ):
        assert _warned(quiet, DIRECTION) == []


@pytest.mark.parametrize("low, high, write, choices", [
    (-90.0, -10.0, "write 270 to 350", False),
    (370.0, 400.0, "write 10 to 40", False),
    (-90.0, 0.0, "write 270 to 360", False),
    (-180.0, 180.0, "write 0 to 360", False),
    (-10.0, 360.0, "write 0 to 360", False),
    (-30.0, 30.0, "offer choices", True),
])
def test_a_direction_range_is_told_its_spelling_from_0_to_360(low, high, write, choices):
    """Re-review 1's R1: a range outside 0 to 360 is told the same range from 0 to 360 -- -90 to -10
    is 270 to 350, 370 to 400 is 10 to 40, one ending on a whole turn ends at 360, and one spanning
    a whole turn or more is every direction, 0 to 360 -- and only one truly across 0, which has no
    one spelling, to offer choices, which would make a continuous direction a discrete one."""
    said = _said_of(_placed_by(Polar(8.0, P("dir")), _dir(low=low, high=high)), DIRECTION)
    assert f"its range from {low:g} to {high:g}" in said and write in said
    assert ("offer choices" in said) is choices


@pytest.mark.parametrize("declared, reach, write", [
    ({}, "any number, its range declaring no bounds", "declare its range within 0 to 360"),
    ({"low": 0.0}, "its range from 0, with no highest", "declare its range within 0 to 360"),
    ({"high": 90.0}, "its range up to 90, with no lowest", "declare its range within 0 to 360"),
])
def test_a_direction_setting_open_on_a_side_is_warned(declared, reach, write):
    """Re-review 1's R5: a side a setting leaves undeclared reaches without end (`check._span`), so
    a direction setting with no highest, or no lowest, can be sent -90 or 400 from the console,
    and is warned as one whose range reaches past 0 to 360 is."""
    said = _said_of(_placed_by(Polar(8.0, P("dir")), _dir(**declared)), DIRECTION)
    assert f"can be {reach}, outside 0 to 360" in said and write in said


def test_each_warning_s_reason_is_where_its_position_is_used():
    """Re-review 1's R2: the reason a warning gives is where the position is used. A stimulus's
    entry records a position a `Show` or an `Update` places; a window is judged where it is placed
    and nothing records its direction; a literal `Polar` is on no console and in no `params`, only
    in the review report and the checker's sentences."""
    down = _dir(choices=(-90.0, 90.0))
    said = _said_of(_placed_by(Polar(8.0, P("dir")), down), DIRECTION)
    assert ("the console shows the setting's number and `params` records it as it holds it (-90), "
            "while a stimulus's entry records the direction from 0° to 360° (270)") in said
    said = _said_of(_placed_by(Polar(8.0, P("dir")), down, where="window"), DIRECTION)
    assert ("(-90), while the window is placed at the direction 270°") in said
    assert "nothing records a window's direction" in said and STIMULUS_REASON not in said
    said = _said_of(_placed_by(Polar(-8.0, 90.0)), ECCENTRICITY)
    assert ("that is the position 8° out at 270°, which a stimulus's entry records, while the "
            "review report and the checker's sentences say it as written") in said
    assert "console" not in said and "params" not in said
    said = _said_of(_placed_by(Polar(-8.0, 90.0), where="window"), ECCENTRICITY)
    assert "that is the position 8° out at 270°, where the window is placed" in said
    assert STIMULUS_REASON not in said and "console" not in said
    said = _said_of(_placed_by(P("pos"), Param("pos", unit="deg", choices=(
        Polar(-8.0, 90.0),)), where="window"), ECCENTRICITY)
    # Re-review 2's S1: the review report shows a setting by its name, never its choices.
    assert ("where the window is placed, while the console and `params` say it as written"
            ) in said and STIMULUS_REASON not in said and "review report" not in said
    said = _said_of(_placed_by(Polar(P("ecc"), 45.0), Param("ecc", unit="deg", low=-2.0, high=10.0),
                               where="window"), ECCENTRICITY)
    assert "while the window is placed at a positive eccentricity" in said
    assert STIMULUS_REASON not in said
    said = _said_of(_placed_by(Polar(P("ecc"), 45.0),
                               Param("ecc", unit="deg", low=-2.0, high=10.0)), ECCENTRICITY)
    assert "while a stimulus's entry records the position at a positive eccentricity" in said


def test_each_eye_s_own_position_is_read_for_both_warnings():
    """Re-review 1's R4: a stereoscope stimulus's per-eye positions are positions too: a left eye's
    `Polar(-3, 0)` is a negative eccentricity, and a right eye's direction setting outside 0 to 360
    is warned."""
    trial = _placed_by((Polar(-3.0, 0.0), Polar(3.0, P("dir"))), _dir(choices=(-90.0, 90.0)),
                       where="eyes", view="stereoscope")
    assert "its left-eye position is -3° at 0°" in _said_of(trial, ECCENTRICITY)
    assert "setting 'dir' places the direction of state 'on' shows stimulus 's'" in _said_of(
        trial, DIRECTION)


def test_a_grating_s_drift_setting_outside_0_to_360_is_warned_with_its_own_reason():
    """Re-review 1's R6: a grating's drift direction held by a setting is "a setting used as a
    direction" too. Its reason is its own: the console and `params` show the setting's number while
    the drift sentences say a drift direction from 0° to 360°; no stimulus's entry records a
    drift."""
    from wl_xcon import look
    from wl_xcon.photometry import Michelson

    grating = look.Look(shape=look.Circle(size=4.0), orientation=0.0, fill=look.SineGrating(
        tf=2.0, direction=P("drift"), contrast=Michelson(0.5)))
    said = _said_of(_placed_by((0.0, 0.0), Param("drift", unit="deg", choices=(-90.0, 90.0)),
                               looks=grating), DIRECTION)
    assert "setting 'drift' places the direction of a grating's drift and can be -90" in said
    assert ("(-90), while the drift sentences, the checker's and the drawer's, say a drift "
            "direction from 0° to 360° (270)") in said and STIMULUS_REASON not in said
    assert "write 270 for -90" in said
    assert _warned(_placed_by((0.0, 0.0), Param("drift", unit="deg", choices=(90.0, 270.0)),
                              looks=grating), DIRECTION) == []


def test_a_plan_condition_giving_a_direction_or_an_eccentricity_outside_is_warned():
    """The C3 plan's outline (the controller, 2026-10-30): a plan condition gives a setting a value
    the task holds as surely as a choice does, so one giving a direction setting a value outside 0
    to 360, or an eccentricity setting one below 0, is warned once per setting and condition, its
    reason where the setting is used."""
    from wl_xcon.check import check_task
    from wl_xcon.task import Block, Condition, Plan, Task

    trial = _placed_by(Polar(P("ecc"), P("dir")), _dir(low=0.0, high=360.0),
                       Param("ecc", unit="deg", low=0.0, high=10.0))
    task = Task({"t": trial}, default="t", plans={"p": Plan([Block("b", [
        Condition("down", {"dir": -90.0, "ecc": -4.0}, target=1),
        Condition("up", {"dir": 90.0, "ecc": 4.0}, target=1)])])})

    found = [f for f in check_task(task) if f.code in (DIRECTION, ECCENTRICITY)]

    assert [f.code for f in found] == [DIRECTION, ECCENTRICITY]
    assert all(not f.blocking and f.accepted_in == SESSION_KINDS for f in found)
    direction, eccentricity = (f.detail for f in found)
    assert direction.startswith("plan 'p': block 'b''s condition 'down' sets 'dir' to -90, outside "
                                "0 to 360, and 'dir' places the direction of state 'on' shows "
                                "stimulus 's'")
    assert STIMULUS_REASON in direction and "write 270 for -90" in direction
    assert eccentricity.startswith("plan 'p': block 'b''s condition 'down' sets 'ecc' to -4, below "
                                   "0, and 'ecc' places the eccentricity of")
    assert found[0].subjects == ("plan 'p': block 'b': condition 'down': setting 'dir'",)
    # Re-review 2's S2: a direction past 360, and a whole position below 0, which the review
    # report shows as a condition's value.
    far = dataclasses.replace(task, plans={"p": Plan([Block("b", [
        Condition("far", {"dir": 400.0}, target=1)])])})
    (said,) = [f.detail for f in check_task(far) if f.code == DIRECTION]
    assert "condition 'far' sets 'dir' to 400, outside 0 to 360" in said
    assert said.endswith("write 40 for 400")
    whole = Task({"t": _placed_by(P("pos"), Param("pos", unit="deg", choices=(
        Polar(8.0, 0.0), Polar(-8.0, 90.0))))}, default="t", plans={"p": Plan([Block("b", [
            Condition("neg", {"pos": Polar(-8.0, 90.0)}, target=1)])])})
    (said,) = [f.detail for f in check_task(whole)
               if f.code == ECCENTRICITY and f.subjects[0].startswith("plan")]
    assert said.startswith("plan 'p': block 'b''s condition 'neg' sets 'pos', placing state 'on' "
                           "shows stimulus 's', to -8° at 90° · (x, y) (0, -8)")
    assert ("which a stimulus's entry records, while the console, `params` and the review report "
            "say it as written") in said and said.endswith("Polar(8, 270)")


def test_a_negative_eccentricity_is_warned_at_load_saying_what_to_write():
    """Review 1's M3, the PI, 2026-10-30, "Warn at load": "Says to write it as a positive
    eccentricity at the opposite direction. Never refused." `Polar(-8, 90)` is the position 8° out
    at 270°. A literal `Polar`, a whole position's choice and a setting placing an eccentricity
    whose choices, start or range go below 0, or that has no lowest (re-review 1's R5), are each
    warned, in every kind; -0 and 0 or more are not."""
    said = _said_of(_placed_by(Polar(-8.0, 90.0)), ECCENTRICITY)
    assert "is -8° at 90° · (x, y) (0, -8)" in said and "Polar(8, 270)" in said
    said = _said_of(_placed_by(Polar(-8, -135), where="window"), ECCENTRICITY)
    assert "window 'w'" in said and "Polar(8, 45)" in said
    (found,) = _warned(_placed_by(P("pos"), Param("pos", unit="deg", choices=(
        Polar(8.0, 0.0), Polar(-8.0, 90.0)))), ECCENTRICITY)
    assert found.subjects == ("setting 'pos'",) and "Polar(8, 270)" in found.detail
    said = _said_of(_placed_by(Polar(P("ecc"), 45.0), Param(
        "ecc", unit="deg", low=-2.0, high=10.0), where="update"), ECCENTRICITY)
    assert ("setting 'ecc' places the eccentricity of state 'on' updates stimulus 's' and can be "
            "its range from -2 to 10") in said
    assert "opposite direction" in said
    said = _said_of(_placed_by(Polar(P("ecc"), 45.0), Param(
        "ecc", unit="deg", choices=(-8.0, 8.0))), ECCENTRICITY)
    assert "can be -8" in said
    said = _said_of(_placed_by(Polar(P("ecc"), 45.0), Param("ecc", unit="deg", high=10.0)),
                    ECCENTRICITY)
    assert "can be its range up to 10, with no lowest" in said and "declare its lowest" in said
    said = _said_of(_placed_by(Polar(-8.0, P("d")), Param("d", unit="deg", choices=(90.0,))),
                    ECCENTRICITY)
    assert said.endswith("8° with 'd''s directions turned by 180°")
    for quiet in (_placed_by(Polar(-0.0, 45.0)), _placed_by(Polar(8.0, 90.0)),
                  _placed_by(Polar(P("ecc"), 45.0), Param("ecc", unit="deg", low=0.0, high=10.0))):
        assert _warned(quiet, ECCENTRICITY) == []
