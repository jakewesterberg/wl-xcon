"""A position written as its eccentricity and direction (the PI, 2026-10-19).

"A task can say 'at eccentricity e, direction θ' and the rig converts it exactly; the load check
warns where a task computes a position as e·cosθ itself", and "Polar first, x-y allowed": tasks
write positions as eccentricity and direction by default, and (x, y) stays for axis-aligned
designs. Positions are per screen axis, so (e·cos θ, e·sin θ) is less than e out off the axes:
7.975° for 8° at 45°. Every expectation here is computed from directions, `D · tan` per axis,
with numpy's dot products, never with `geometry`'s own arithmetic.
"""

from __future__ import annotations

import math
import textwrap
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from _rig import DIRECT
from wl_xcon import screen
from wl_xcon.check import check, check_task
from wl_xcon.cli import _load_task
from wl_xcon.findings import SESSION_KINDS
from wl_xcon.photometry import Gray
from wl_xcon.review import render
from wl_xcon.task import (
    After,
    Array,
    Disc,
    Hold,
    ObjectWindows,
    On,
    Outcome,
    P,
    Param,
    SaccadeTo,
    Show,
    State,
    Stimulus,
    Trial,
    Window,
    expand_windows,
)

TASKS = Path(__file__).resolve().parents[1] / "tasks"


def _unit(x: float, y: float) -> np.ndarray:
    t = np.array([math.tan(math.radians(x)), math.tan(math.radians(y)), 1.0])
    return t / np.linalg.norm(t)


def _apart(p, q) -> float:
    return math.degrees(math.acos(float(np.clip(_unit(*p) @ _unit(*q), -1.0, 1.0))))


def _expected(e: float, theta: float) -> tuple[float, float]:
    """`(atan(tan e cos θ), atan(tan e sin θ))`, written out here rather than read from
    `geometry`."""
    t = math.tan(math.radians(e))
    return (math.degrees(math.atan(t * math.cos(math.radians(theta)))),
            math.degrees(math.atan(t * math.sin(math.radians(theta)))))


def _polar(*args):
    from wl_xcon.task import Polar

    return Polar(*args)


def test_a_stimulus_its_window_and_an_array_take_a_polar_position_drawn_and_scored_as_x_y():
    """Accepted wherever a position is: a stimulus's, a window's center, an array's. `screen`
    draws each at its exact per-axis degrees, every object of a polar array sits on its true
    circle about that position, and each object window is where its object is drawn."""
    lit = Disc(size=0.5, color=Gray(40.0))
    target = Stimulus("target", at=_polar(P("ecc"), P("dir")), looks=lit)
    ring = Stimulus("ring", at=_polar(10.0, 30.0), looks=Array(n=6, radius=3.0, target=0,
                                                              looks=lit, among=lit))
    trial = Trial(
        start="on",
        params=[Param("ecc", unit="deg", low=2.0, high=16.0),
                Param("dir", unit="deg", low=-180.0, high=180.0)],
        windows=[Window("target", at=_polar(P("ecc"), P("dir")), radius=1.0, on="target"),
                 ObjectWindows(of="ring", radius=0.5)],
        states=[State("on", enter=[Show(target), Show(ring)], go=[
            On(Hold("target", 0.1), Outcome.CORRECT), On(After(1.0), Outcome.NO_RESPONSE)])],
    )
    values = {"ecc": 8.0, "dir": 45.0}

    drawn = screen.resolve({"target": target, "ring": ring}, values, trial, DIRECT,
                           frame_period=1 / 240)
    windows = {w.name: w.at for w in expand_windows(trial, values)[0]}

    at = {item.name: item.at_left for item in drawn.items}
    assert at["target"] == pytest.approx(_expected(8.0, 45.0), abs=1e-9)
    assert _apart((0.0, 0.0), at["target"]) == pytest.approx(8.0, abs=1e-9)
    center = _expected(10.0, 30.0)
    for i in range(6):
        assert _apart(center, at[f"ring.{i}"]) == pytest.approx(3.0, abs=1e-9)
        assert windows[f"ring.{i}"] == pytest.approx(at[f"ring.{i}"], abs=1e-12)
    assert "computed-position" not in {f.code for f in check(trial)}


@pytest.mark.parametrize("directions, shown", [((-30.0, 30.0), True), ((0.0, 120.0), False)])
def test_check_8_holds_a_polar_position_to_the_field_at_every_direction_its_range_allows(
        directions, shown):
    """20° out, over a range of directions, in direct view's ±30.5° × ±18.4° field: from 0° to
    120° both ends are inside, at (20°, 0°) and (-10.3°, 17.5°), but 90°, between them, is 20°
    up, past the top. Check 8 refuses it exactly when some direction in the range puts it past
    the edge, by every direction at a tenth of a degree."""
    trial = Trial(
        start="on",
        params=[Param("dir", unit="deg", low=directions[0], high=directions[1])],
        states=[State("on", enter=[Show(Stimulus("t", at=_polar(20.0, P("dir")), looks=Disc(
            size=0.5, color=Gray(40.0))))], go=[On(After(1.0), Outcome.NO_RESPONSE)])],
    )
    swept = [_expected(20.0, t) for t in np.arange(directions[0], directions[1] + 0.05, 0.1)]

    refused = "stimulus-off-screen" in {f.code for f in check(trial, geometry=DIRECT)}

    assert all(DIRECT.can_show(*p) for p in swept) is shown
    assert refused is not shown


@pytest.mark.parametrize("radius, overlap", [(5.9, False), (6.1, True)])
def test_windows_with_polar_centers_overlap_exactly_when_their_positions_can_meet(radius, overlap):
    """A fixation window at the center, 2° in radius, and a target window 8° out in any
    direction (a range of -180° to 180°): every direction is 8° from the center, so they overlap
    exactly when the target's radius passes 6°; the per-axis box of that circle holds the center
    and would read them 0° apart."""
    trial = Trial(
        start="wait",
        params=[Param("dir", unit="deg", low=-180.0, high=180.0)],
        windows=[Window("fix", at=(0.0, 0.0), radius=2.0, on="fix"),
                 Window("target", at=_polar(8.0, P("dir")), radius=radius, on="fix")],
        states=[State("wait", enter=[Show(Stimulus("fix", at=(0.0, 0.0), looks=Disc(size=0.3)))],
                      go=[On(Hold("fix", 0.1), Outcome.CORRECT),
                          On(Hold("target", 0.1), Outcome.WRONG_TARGET),
                          On(After(1.0), Outcome.NO_RESPONSE)])],
    )

    found = [f for f in check(trial) if f.code == "overlapping-windows"]

    assert bool(found) is overlap
    if found:
        assert "which can come within 8.00°" in found[0].detail


def test_the_review_report_shows_eccentricity_and_direction_first_and_x_y_beside_them():
    """The PI, 2026-10-19 ("Polar first, x-y allowed"): every position is shown as its
    eccentricity and direction, with its per-axis (x, y) beside it, a position written as (x, y)
    converted exactly; one a setting holds is shown as written."""
    trial = Trial(
        start="on",
        params=[Param("ecc", unit="deg", low=2.0, high=16.0),
                Param("x", unit="deg", low=-5.0, high=5.0)],
        windows=[Window("a", at=_polar(8.0, 45.0), radius=1.0, on="a"),
                 Window("b", at=(5.0, 0.0), radius=1.0, on="b")],
        states=[State("on", enter=[
            Show(Stimulus("a", at=_polar(8.0, 45.0), looks=Disc())),
            Show(Stimulus("b", at=(5.0, 0.0), looks=Disc())),
            Show(Stimulus("c", at=_polar(P("ecc"), 90.0), looks=Disc())),
            Show(Stimulus("d", at=(P("x"), 0.0), looks=Disc())),
            Show(Stimulus("e", at=(0.0, 0.0), looks=Disc())),
        ], go=[On(After(1.0), Outcome.NO_RESPONSE)])],
    )

    artifact = render(trial)

    assert "| `a` | 8° at 45° · (x, y) (5.675, 5.675) |" in artifact
    assert "| `b` | 5° at 0° · (x, y) (5, 0) |" in artifact
    assert "| `on` | `a` | 8° at 45° · (x, y) (5.675, 5.675) |" in artifact
    assert "| `on` | `c` | ecc at 90° |" in artifact
    assert "| `on` | `d` | (x, y) (x, 0) |" in artifact
    assert "| `on` | `e` | 0° · (x, y) (0, 0) |" in artifact


def test_a_polar_position_is_part_of_the_task_s_content():
    """`canonical` writes it as every declaration, so it is hashed; a task that writes none
    hashes as it did before it existed."""
    from wl_xcon.declarations import canonical

    assert canonical(_polar(8.0, P("dir"))) == {"class": "Polar", "fields": {
        "eccentricity": 8.0, "direction": {"class": "P", "fields": {"name": "dir"}}}}


def _task_file(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "computed.py"
    path.write_text(textwrap.dedent('''\
        import math
        import numpy as np
        from math import cos as c, sin
        from wl_xcon.task import (After, Disc, On, Outcome, P, Param, Show, State, Stimulus, Task,
                                  Trial, Window, NO_CHOICE, ReactionTime, OWED, Counting)
        ''') + textwrap.dedent(body) + textwrap.dedent('''\

        TASK = Task(structures={"t": TRIAL}, default="t", choice=NO_CHOICE,
                    reaction_time=ReactionTime(state="on", to=(Outcome.NO_RESPONSE,), note="n"))
        '''), encoding="utf-8")
    return path


def _computed(path: Path) -> list:
    return [f for f in check_task(_load_task(path), source=path) if f.code == "computed-position"]


def test_a_position_built_from_cos_and_sin_in_the_task_file_is_a_warning_naming_the_line(tmp_path):
    """The PI, 2026-10-19: "the load check warns where a task computes a position as e·cosθ
    itself". The file is read with the parser: a call of `math`'s or numpy's `cos` or `sin`, by
    any name it is imported as, inside a position -- a stimulus's, a window's center, an update's
    or a per-eye one, written there, through a name the file assigns, or among the choices of a
    setting a position names. A warning in every session kind, never a refusal, naming the line
    and saying to write the position as `Polar`."""
    path = _task_file(tmp_path, '''\
        A = math.radians(45.0)
        CORNER = (8 * c(A), 8 * sin(A))
        TRIAL = Trial(
            start="on",
            params=[Param("pos", unit="deg", choices=tuple(
                (8 * np.cos(math.radians(t)), 8 * np.sin(math.radians(t))) for t in (0, 90)))],
            windows=[Window("w", (8 * math.cos(A), 8 * math.sin(A)), 1.0, on="s")],
            states=[State("on", enter=[
                Show(Stimulus("s", at=(8 * math.cos(A), 0.0), looks=Disc())),
                Show(Stimulus("k", at=CORNER, looks=Disc())),
                Show(Stimulus("q", at=P("pos"), looks=Disc())),
            ], go=[On(After(1.0), Outcome.NO_RESPONSE)])],
        )
        ''')

    found = _computed(path)

    assert [(f.blocking, f.accepted_in) for f in found] == [(False, SESSION_KINDS)] * 4
    lines = [f.detail.split(":")[0] for f in found]
    assert lines == ["line 12", "line 14", "line 15", "line 16"]
    assert all("write it as Polar(eccentricity, direction)" in f.detail for f in found)
    assert "7.975° for 8° at 45°" in found[0].detail


def test_cos_and_sin_outside_a_position_and_the_reference_tasks_draw_no_warning(tmp_path):
    """A contrast or a duration computed with `cos` is no position; and no reference task builds
    one from `cos` or `sin`."""
    path = _task_file(tmp_path, '''\
        TRIAL = Trial(
            start="on",
            states=[State("on", enter=[
                Show(Stimulus("s", at=(8.0, 0.0), looks=Disc(size=1.0 + math.cos(0.3)))),
            ], go=[On(After(0.5 + 0.1 * math.sin(1.0)), Outcome.NO_RESPONSE)])],
        )
        ''')

    assert _computed(path) == []
    for name in ("adaptive_detection", "calibration", "fixation_detection", "visual_search",
                 "visual_search_training"):
        assert _computed(TASKS / f"{name}.py") == [], name


def test_an_update_s_position_in_its_place_and_trigonometry_inside_a_polar(tmp_path):
    """The review of commits 2-5, items 2 and 3: an `Update` takes its position in its second
    place too, as `Stimulus` and `Window` do, and `cos` there is found; and a `Polar` whose own
    fields are computed with `cos` or `sin` is an eccentricity and a direction however computed,
    so nothing inside one is warned of."""
    path = _task_file(tmp_path, '''\
        from wl_xcon.task import Polar, Update
        ECC = math.degrees(math.acos(math.cos(0.2) * math.cos(0.1)))
        TRIAL = Trial(
            start="on",
            states=[State("on", enter=[
                Show(Stimulus("p", at=Polar(ECC, 30.0), looks=Disc())),
                Show(Stimulus("r", at=Polar(math.degrees(math.acos(c(0.3))), 0.0), looks=Disc())),
                Update("p", (8 * math.cos(0.5), 0.0)),
            ], go=[On(After(1.0), Outcome.NO_RESPONSE)])],
        )
        ''')

    found = _computed(path)

    assert [f.detail.split(":")[0] for f in found] == ["line 13"]
    assert "an update's position" in found[0].detail


@pytest.mark.parametrize("farthest, shown", [(16.0, True), (25.0, False)])
def test_a_whole_point_setting_of_polar_choices_is_measured_at_each(farthest, shown):
    """The review's item 4: a whole-point setting whose choices are `Polar` values was refused by
    check 8 as a position it could not bound. Each choice is converted and measured like any
    other: 8° right and `farthest` up, in direct view's 18.4° vertical field."""
    trial = Trial(
        start="on",
        params=[Param("pos", unit="deg", choices=(_polar(8.0, 0.0), _polar(farthest, 90.0)))],
        states=[State("on", enter=[Show(Stimulus("t", at=P("pos"), looks=Disc(
            size=0.5, color=Gray(40.0))))], go=[On(After(1.0), Outcome.NO_RESPONSE)])],
    )

    found = [f for f in check(trial, geometry=DIRECT) if f.code == "stimulus-off-screen"]

    assert bool(found) is not shown
    if found:
        assert "which can reach 0.0, 25.0" in found[0].detail


@pytest.mark.parametrize("highest", [90.0, None])
def test_windows_whose_centers_reach_the_side_are_found_to_overlap(highest):
    """The review of the fix commit, item 1: a window 48.44° out or more, to 90° or without end, at
    -159.7° to -124.46°, and one over 76.23°-82.08° across and -90° to -49.04° up, each 19° in
    radius, can come 34.46° apart, under the 38° their radii sum to; read through per-axis
    degrees at the side, where (±90°, ±90°) stands for every direction 90° out, they were said
    45° apart and passed."""
    trial = Trial(
        start="w",
        params=[Param("ecc", unit="deg", low=48.44, high=highest),
                Param("dir", unit="deg", low=-159.7, high=-124.46),
                Param("dx", unit="deg", low=76.23, high=82.08),
                Param("dy", unit="deg", low=-90.0, high=-49.04)],
        windows=[Window("t", at=_polar(P("ecc"), P("dir")), radius=19.0, on="s"),
                 Window("d", at=(P("dx"), P("dy")), radius=19.0, on="s")],
        states=[State("w", enter=[Show(Stimulus("s", at=(0.0, 0.0), looks=Disc()))],
                      go=[On(Hold("t", 0.1), Outcome.CORRECT),
                          On(Hold("d", 0.1), Outcome.WRONG_TARGET),
                          On(After(1.0), Outcome.NO_RESPONSE)])],
    )

    assert "overlapping-windows" in {f.code for f in check(trial)}


def _fixation_and_target(lowest: float, highest, directions) -> Trial:
    """A fixation window anywhere over ±1° on each axis and a target window `lowest`° out or more,
    to `highest` (or without end), over `directions`, each 1° in radius, scored in one state."""
    return Trial(
        start="w",
        params=[Param("ecc", unit="deg", low=lowest, high=highest),
                Param("dir", unit="deg", low=directions[0], high=directions[1]),
                Param("fx", unit="deg", low=-1.0, high=1.0),
                Param("fy", unit="deg", low=-1.0, high=1.0)],
        windows=[Window("t", at=_polar(P("ecc"), P("dir")), radius=1.0, on="s"),
                 Window("f", at=(P("fx"), P("fy")), radius=1.0, on="s")],
        states=[State("w", enter=[Show(Stimulus("s", at=(0.0, 0.0), looks=Disc()))],
                      go=[On(Hold("t", 0.1), Outcome.CORRECT),
                          On(Hold("f", 0.1), Outcome.WRONG_TARGET),
                          On(After(1.0), Outcome.NO_RESPONSE)])],
    )


@pytest.mark.parametrize("highest", [90.0, None])
@pytest.mark.parametrize("directions", [(-180.0, 180.0), (0.0, 90.0)])
def test_a_window_reaching_the_side_is_read_by_its_eccentricity_from_one_at_the_center(
        highest, directions):
    """The check of the side-of-field commit: a target window 5° out or more, reaching 90° or
    without end, and a fixation window over ±1°, each 1° in radius, are at least 5° less the
    fixation window's farthest corner, 1.414° out, apart: 3.586°, beyond the 2° their radii sum
    to. The boxes that hold a region reaching 90° held the center too, and read them 0° apart;
    the eccentricities' gap, which no pair is nearer than, reads them as they are."""
    assert "overlapping-windows" not in {
        f.code for f in check(_fixation_and_target(5.0, highest, directions))}


def test_a_window_reaching_the_side_that_does_come_within_reach_is_still_found():
    """2.5° out or more instead: the gap is 1.086°, under the 2° the radii sum to, and a target at
    2.5° and 45° meets the fixation window's corner direction there."""
    (found,) = [f for f in check(_fixation_and_target(2.5, None, (-180.0, 180.0)))
                if f.code == "overlapping-windows"]

    assert "which can come within 1.09°" in found.detail

def _two_windows(first_at, second_at, *params) -> Trial:
    """Two windows 1° in radius, `a` and `b`, scored in one state, placed at `first_at` and
    `second_at` (a position, or a setting among `params`)."""
    return Trial(
        start="w",
        params=list(params),
        windows=[Window("a", at=first_at, radius=1.0, on="s"),
                 Window("b", at=second_at, radius=1.0, on="s")],
        states=[State("w", enter=[Show(Stimulus("s", at=(0.0, 0.0), looks=Disc()))],
                      go=[On(Hold("a", 0.1), Outcome.CORRECT),
                          On(Hold("b", 0.1), Outcome.WRONG_TARGET),
                          On(After(1.0), Outcome.NO_RESPONSE)])],
    )


def _overlaps(trial: Trial) -> list:
    return [f for f in check(trial) if f.code == "overlapping-windows"]


def test_two_windows_each_placed_by_a_whole_point_setting_are_checked_over_every_pair_of_choices():
    """XC-156: the overlap check (`_closest_approach`, since removed) unpacked a window's place as a pair and raised `TypeError` for
    `Window.at = P(...)`, a legal form. Read as a window with coordinate settings is, over every
    value its choices allow: 8° at 0° and 8° at 5° are 0.70° apart, under the 2° the radii sum to,
    and the sentence names those choices in the review report's words (eccentricity and direction
    first), not Python's repr."""
    trial = _two_windows(
        P("pa"), P("pb"),
        Param("pa", unit="deg", choices=(_polar(8.0, 0.0), _polar(8.0, 90.0))),
        Param("pb", unit="deg", choices=(_polar(20.0, 180.0), _polar(8.0, 5.0))))

    (found,) = _overlaps(trial)

    assert "which can come within 0.70° while their radii sum to 2.00°" in found.detail
    assert ("(1 of 4 combinations overlaps, by settings 'pa' and 'pb': 'a' at 8° at 0° · (x, y) "
            "(8, 0) with 'b' at 8° at 5° · (x, y) (7.97, 0.702))") in found.detail
    assert "Polar(" not in found.detail
    assert not found.blocking and found.accepted_in == SESSION_KINDS


def test_the_overlap_finding_names_each_choice_by_its_direction_from_0_to_360():
    """The PI, 2026-10-30, "0 to 360 everywhere": the choice the overlap finding names, written
    `Polar(8, -90)` by the task, reads 270 there as everywhere else."""
    trial = _two_windows(P("pa"), _polar(8.0, 272.0), Param("pa", unit="deg", choices=(
        _polar(8.0, -90.0), _polar(8.0, 90.0))))

    (found,) = _overlaps(trial)

    assert "(1 of 2 choices overlaps, by setting 'pa': 'a' at 8° at 270° · (x, y) (0, -8))" \
        in found.detail
    assert "-90" not in found.detail


def test_a_window_placed_by_a_whole_point_setting_and_one_placed_by_a_literal_are_checked():
    """XC-156: one window at a setting's choice (10°, 0°) or (-10°, 0°), the other literally at
    (10.5°, 0°): they overlap at the first choice only, which is the one named; only the window
    placed by a setting is described by its setting."""
    trial = _two_windows(
        P("pa"), (10.5, 0.0), Param("pa", unit="deg", choices=((10.0, 0.0), (-10.0, 0.0))))

    (found,) = _overlaps(trial)

    assert "which can come within 0.50° while their radii sum to 2.00°" in found.detail
    assert "(1 of 2 choices overlaps, by setting 'pa': 'a' at 10° at 0° · (x, y) (10, 0))" in found.detail
    assert "at 180°" not in found.detail and "'b' at" not in found.detail

    swapped = _two_windows((10.5, 0.0), P("pb"), Param("pb", unit="deg",
                                                       choices=((-10.0, 0.0), (10.0, 0.0))))
    (found,) = _overlaps(swapped)
    assert "(1 of 2 choices overlaps, by setting 'pb': 'b' at 10° at 0° · (x, y) (10, 0))" in found.detail


def test_choices_that_overlap_only_in_some_combinations_are_found_and_the_combination_named():
    """XC-156: of the four pairings of two settings' two choices, only (0°, 10°) with (0°, 10.5°)
    come within the radii: `pa`'s second choice with `pb`'s first, off the diagonal, so a check
    that pairs choice i with choice i (a plan's conditions do set two settings together) passes
    it. The finding is the same as a pair that does overlap, naming that one."""
    trial = _two_windows(
        P("pa"), P("pb"),
        Param("pa", unit="deg", choices=((10.0, 0.0), (0.0, 10.0))),
        Param("pb", unit="deg", choices=((0.0, 10.5), (-10.0, 0.0))))

    (found,) = _overlaps(trial)

    assert "which can come within 0.50° while their radii sum to 2.00°" in found.detail
    assert ("by settings 'pa' and 'pb': 'a' at 10° at 90° · (x, y) (0, 10) with "
            "'b' at 10.5° at 90° · (x, y) (0, 10.5))") in found.detail


def test_choices_that_never_overlap_are_not_crossed_into_positions_nobody_offered():
    """XC-156: a window at (10°, 5°) or (-10°, -5°) is never near (10°, -5°) (10° away). Read as
    two coordinate settings crossed, x in {10, -10} and y in {5, -5}, it would have a position
    nobody offered, (10°, -5°), exactly on the other window: a whole point is one choice or the
    other."""
    trial = _two_windows(
        P("pa"), (10.0, -5.0), Param("pa", unit="deg", choices=((10.0, 5.0), (-10.0, -5.0))))

    assert _overlaps(trial) == []


@pytest.mark.parametrize("choices", [
    (None,), ("left", "right"), (3.0, 4.0), ((1.0, 2.0, 3.0),), (float("inf"), float("nan")),
    ((float("inf"), 0.0),), (10**400,), ((10**400, 0.0),), (True, False), ((), ()),
    (_polar("x", 0.0),), (),
])
def test_choices_that_are_no_position_do_not_raise_out_of_the_overlap_check(choices):
    """XC-156: a whole-point setting whose choices are no positions (the other refusal,
    `bad-placement`, speaks) or that has none (a free value, refused at load by XC-422) is skipped
    by the overlap check, which never raises."""
    trial = _two_windows(P("pa"), (0.0, 0.0), Param("pa", unit="deg", choices=choices))

    assert _overlaps(trial) == []
    assert {f.code for f in check(trial)} >= {"bad-placement"} or choices == (None,)


def test_a_setting_never_declared_or_a_mix_of_good_and_bad_choices_is_checked_without_raising():
    """XC-156: an undeclared setting is skipped (its own finding says so); of a setting's choices
    only those that are positions are compared."""
    undeclared = _two_windows(P("nowhere"), (0.0, 0.0))
    assert _overlaps(undeclared) == []

    mixed = _two_windows(P("pa"), (0.0, 10.5), Param("pa", unit="deg",
                                                    choices=("left", (0.0, 10.0), None)))
    (found,) = _overlaps(mixed)
    assert "(1 choice overlaps, by setting 'pa': 'a' at 10° at 90° · (x, y) (0, 10))" in found.detail


def test_a_window_whose_position_is_of_no_shape_the_check_reads_does_not_raise_either():
    """XC-156: `_centers` unpacked any literal as a pair, and a three-tuple or a string raised;
    `_position_kind_faults` refuses it, and the overlap check skips it."""
    for at in ((1.0, 2.0, 3.0), "here", 5.0, None):
        trial = _two_windows(at, (0.0, 0.0))
        assert _overlaps(trial) == []
        assert "bad-placement" in {f.code for f in check(trial)}


def test_every_choice_that_overlaps_is_named_up_to_three_then_counted():
    """XC-156 fix round 1 (I1): a target at any of eight places 1.5° out overlaps a window at the
    center; the finding names the nearest three combinations, then counts the rest, and the closest
    separation stays in the sentence."""
    trial = _two_windows(P("pt"), (0.0, 0.0), Param(
        "pt", unit="deg", choices=tuple(_polar(1.5, 45.0 * k) for k in range(8))))

    (found,) = _overlaps(trial)

    assert ("which can come within 1.50° while their radii sum to 2.00° (8 of 8 choices overlap, "
            "by setting 'pt': ") in found.detail
    assert found.detail.count("'a' at 1.5° at ") == 3 and ", and 5 more)" in found.detail


def test_two_overlapping_choices_are_both_named_and_the_one_that_does_not_is_not():
    """XC-156 fix round 1 (I1): the repo's own fixture shape, a target at (10°, 0°) or (-10°, 0°)
    against a window at the center with a radius of 9.5°, and a third choice far off."""
    trial = Trial(
        start="w",
        params=[Param("pa", unit="deg", choices=((10.0, 0.0), (-10.0, 0.0), (0.0, 30.0)))],
        windows=[Window("a", at=P("pa"), radius=1.0, on="s"),
                 Window("b", at=(0.0, 0.0), radius=9.5, on="s")],
        states=[State("w", enter=[Show(Stimulus("s", at=(0.0, 0.0), looks=Disc()))],
                      go=[On(Hold("a", 0.1), Outcome.CORRECT),
                          On(Hold("b", 0.1), Outcome.WRONG_TARGET),
                          On(After(1.0), Outcome.NO_RESPONSE)])],
    )

    (found,) = _overlaps(trial)

    assert "(2 of 3 choices overlap, by setting 'pa': " in found.detail
    assert "'a' at 10° at 0°" in found.detail and "'a' at 10° at 180°" in found.detail
    assert "30° at 90°" not in found.detail


@pytest.mark.parametrize("at", [
    ("a", 1), (None, 1), ([1.0], 2.0), (10**400, 0), (float("nan"), 0.0), (P("x"), "b"),
    _polar("x", 0.0), _polar(10**400, 0.0), _polar(P("x"), None),
])
def test_a_literal_position_holding_a_non_number_is_refused_and_the_overlap_check_does_not_raise(at):
    """XC-156 fix round 1 (m1): `check()` raised on these literals (ValueError, TypeError,
    OverflowError) before `bad-placement` could refuse them; it refuses them now."""
    trial = _two_windows(at, (0.0, 0.0), Param("x", unit="deg", low=-1.0, high=1.0))

    found = check(trial)

    assert "bad-placement" in {f.code for f in found}
    assert [f for f in found if f.code == "overlapping-windows"] == []


@pytest.mark.parametrize("radius", ["big", None, 10**400, float("nan"), float("inf")])
def test_a_literal_radius_that_is_no_number_is_refused_and_the_overlap_check_does_not_raise(radius):
    """XC-156 fix round 1 (m1): a window radius written as text, None or a value no float holds
    raised out of `check()`; it is refused (`bad-placement`) and the pair is not compared."""
    trial = _two_windows((0.0, 0.0), (0.0, 1.0))
    trial = replace(trial, windows=[replace(trial.windows[0], radius=radius), trial.windows[1]])

    found = check(trial)

    (refusal,) = [f for f in found if f.code == "bad-placement"]
    assert "window 'a': its radius is " in refusal.detail and "not a finite number" in refusal.detail
    assert [f for f in found if f.code == "overlapping-windows"] == []


def test_the_three_named_are_the_nearest_and_the_farthest_is_counted_not_named():
    """XC-156 fix round 2 (n1): five places at distinct distances, 0.5° to 2.5° out, from a window
    3° in radius with the target 1° in radius: all five overlap; the three nearest are named, in
    order, and the farthest two are counted."""
    trial = _two_windows(P("pt"), (0.0, 0.0), Param(
        "pt", unit="deg", choices=tuple(_polar(e, 0.0) for e in (2.5, 0.5, 2.0, 1.0, 1.5))))
    trial = replace(trial, windows=[trial.windows[0], replace(trial.windows[1], radius=3.0)])

    (found,) = _overlaps(trial)

    assert ("(5 of 5 choices overlap, by setting 'pt': 'a' at 0.5° at 0° · (x, y) (0.5, 0); "
            "'a' at 1° at 0° · (x, y) (1, 0); 'a' at 1.5° at 0° · (x, y) (1.5, 0), and 2 more)"
            ) in found.detail
    assert "2.5°" not in found.detail.split("while")[1].split("a gaze")[0]


def test_two_windows_on_one_setting_take_its_choice_together_and_are_counted_so():
    """XC-156 fix round 2 (n3): windows `a` and `b` both at `P("pt")`, as per-eye windows can be,
    hold one choice between them at a time: two combinations, not four, where the choices are far
    apart (a choice of one beside another choice of the other never happens), and both overlap."""
    trial = _two_windows(P("pt"), P("pt"), Param("pt", unit="deg", choices=((0.0, 0.0), (20.0, 0.0))))

    (found,) = _overlaps(trial)

    assert "(2 of 2 combinations overlap, by setting 'pt': " in found.detail
    assert "'a' at 0° · (x, y) (0, 0) with 'b' at 0° · (x, y) (0, 0)" in found.detail
    assert ("'a' at 20° at 0° · (x, y) (20, 0) with 'b' at 20° at 0° · (x, y) (20, 0)"
            in found.detail)
    assert "0.00°" in found.detail


def test_a_count_of_one_agrees_with_its_verb_and_noun():
    """XC-156 fix round 2 (n3): "1 choice overlaps" where one place is compared, "1 of 3 choices
    overlaps" where one of several does; never "1 of 1 combinations overlap"."""
    one = _two_windows(P("pa"), (10.5, 0.0), Param("pa", unit="deg", choices=((10.0, 0.0),)))
    several = _two_windows(P("pa"), (10.5, 0.0), Param(
        "pa", unit="deg", choices=((10.0, 0.0), (-10.0, 0.0), (0.0, 10.0))))

    assert "(1 choice overlaps, by setting 'pa': " in _overlaps(one)[0].detail
    assert "(1 of 3 choices overlaps, by setting 'pa': " in _overlaps(several)[0].detail


def test_a_finding_with_both_windows_set_names_two_then_counts_each_position_in_full():
    """XC-156 fix round 3: eight choices each, every pairing on a ring 0.7° apart or less
    overlapping: two combinations named, the rest counted, each position in the review report's
    words in full (STE-29: eccentricity and direction first, (x, y) beside them)."""
    trial = _two_windows(
        P("pa"), P("pb"),
        Param("pa", unit="deg", choices=tuple(_polar(8.0, 45.0 * k) for k in range(8))),
        Param("pb", unit="deg", choices=tuple(_polar(8.0, 45.0 * k + 5.0) for k in range(8))))

    (found,) = _overlaps(trial)

    clause = found.detail.split("radii sum to 2.00° ", 1)[1].split("; a gaze", 1)[0]
    assert clause.startswith("(8 of 64 combinations overlap, by settings 'pa' and 'pb': ")
    assert clause.endswith(", and 6 more)") and clause.count(" with ") == 2
    assert clause.count("(x, y)") == 4
