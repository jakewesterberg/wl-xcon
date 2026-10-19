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
