"""Hard limits only where a value cannot be, and warnings from the layout actually set (the console
settings design's §4; the PI, 2026-11-16, "Hard limits only where impossible").

**Every declared bound is a hard limit**: a value past one is refused, `past-limit`, saying the
limit's one-line reason (`task.limit_reason`: a standard reason, or the task's `Param.why`), and a
bound with neither is warned at load, `unexplained-limit`. **The layout is judged at the values
set**: the load reads an open side of a range at the setting's start (`check._at_start`), a run's
pre-flight at the run's values (`preflight.laid_out`), and every change -- a value, a range, a
person's draw, a hand-back and a revert -- at what the run will hold after it, each block,
condition and draw's two ends (`Session._laid_out`): off the field refuses, and each new warning
is accepted by who made the change and said on the feed.

The fixture is a ring of discs with object windows in degrees, its ranges open: `visual_search`
with its builder's ranges taken away (each setting given a start and a lowest of 0, or 1 for its
count), its discs `disc_size` across, and a `catch_share` fraction beside them. Engine test
material, run only in the simulator: no number here is a timing claim about the rig.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

import _sessions
from _rig import DIRECT
from wl_xcon import preflight
from wl_xcon.actor import Box
from wl_xcon.check import (
    LAYOUT, PAST_LIMIT, UNEXPLAINED_LIMIT, at_values, beyond_range, check_task, laid_out,
)
from wl_xcon.cli import _load_allocation, _load_task
from wl_xcon.dio import Simulated as Card
from wl_xcon.link import (
    HandBack, ParamRow, Revert, SetForm, SetParameter, SetRange, Simulated,
)
from wl_xcon.photometry import SRGB
from wl_xcon.run import Scripted
from wl_xcon.scheduler import EVERY_TRIAL
from wl_xcon.task import (
    BELOW_ONE, BELOW_ZERO, COUNT_UNITS, FRACTION_TOP, FRESH, REASON_LIMIT, Block, Condition,
    Param, Uniform, limit_reason,
)
from wl_xcon.taskd import Session, SessionSpec
from wl_xcon.web import _range
from wl_xcon.welfare import Deployment, Simulated as Pump

WALL_NOW = 1_700_000_000.0
ROOT = Path(__file__).resolve().parents[1]
XTASKS = next((c for c in (ROOT / "wl-xtasks", ROOT.parent / "wl-xtasks")
               if (c / "tasks" / "popout_search.py").is_file()), None)
if XTASKS is None and os.environ.get("WLX_REQUIRE_XTASKS") == "1":  # pragma: no cover - CI's
    raise AssertionError("WLX_REQUIRE_XTASKS=1 but no wl-xtasks checkout holding "
                         "tasks/popout_search.py was found beside or inside this repository")
JAKE = Box("jake")
ALLOCATION = _load_allocation(Path("tasks/allocation.py"))

#: The ring's settings, each open above but its set size, a start where the run begins:
#: visual_search's with its builder's ranges taken away (its TSK-39 bound among them), every limit
#: a value cannot pass. A set size declares its highest still (`unbounded-set-size`, the PI's
#: "Refuse at load" of 2026-10-14; §4's "a set size past the array's places").
OPEN = '''{
    "fix_acquisition": Param("fix_acquisition", unit="s", low=0.0, start=0.5),
    "fix_hold": Param("fix_hold", unit="s", low=0.0, start=0.3),
    "response_deadline": Param("response_deadline", unit="s", low=0.0, start=0.6),
    "target_hold": Param("target_hold", unit="s", low=0.0, start=0.2),
    "fix_window": Param("fix_window", unit="deg", low=0.0, start=2.0),
    "object_window": Param("object_window", unit="deg", low=0.0, start=1.6),
    "array_eccentricity": Param("array_eccentricity", unit="deg", low=0.0, start=6.0),
    "set_size": Param("set_size", unit="objects", low=1, high=12, start=4,
                      why="a stand-in for the array's places, which a set size must declare"),
    "target_index": Param("target_index", unit="index", low=0, start=0),
    "array_rotation": Param("array_rotation", unit="deg", low=0.0, start=0.0),
    "fix_luminance": Param("fix_luminance", unit="cd/m2", low=0.0, high=80.0, start=40.0,
                           why="white on the default calibration, the sRGB standard's (COL-29)"),
}'''
#: The settings the fixture adds: its discs' size, a fraction, and a place for the fixation point
#: in seconds -- contrived, so a timing setting's draw can move a stimulus (the form's path).
ADDED = '''[
    Param("disc_size", unit="deg", low=0.0, start=1.0),
    Param("catch_share", unit="fraction", low=0.0, high=1.0, start=0.1),
    Param("fix_drift", unit="s", low=0.0, start=0.0),
]'''
MEANINGS = '''{
    "disc_size": Meaning(NOT_DIFFICULTY, STIMULUS, note="the ring's discs, across"),
    "catch_share": Meaning(NOT_DIFFICULTY, NEITHER, note="a fraction no trial reads"),
    "fix_drift": Meaning(NOT_DIFFICULTY, STIMULUS, note="the fixation point's place, contrived"),
}'''


def _ring_task(folder: Path, *, name: str = "ring", over: str = "") -> Path:
    """The fixture, written into `folder` as `NAME.py`; `over` is Python run last, free to replace
    `_OPEN`'s entries before the task is made."""
    text = Path("tasks/visual_search.py").read_text()
    for old, new in (("size=1.0,", 'size=P("disc_size"),'),
                     ('FIX = Stimulus("fix", at=(0.0, 0.0),', 'FIX = Stimulus("fix", at=(P("fix_drift"), 0.0),')):
        assert old in text, old
        text = text.replace(old, new)
    text += (
        "\n\nimport dataclasses as _dataclasses\n"
        "from wl_xcon.task import NEITHER, NOT_DIFFICULTY, STIMULUS, Meaning\n"
        f"_OPEN = {OPEN}\n{over}\n"
        "search = _dataclasses.replace(search, params=[\n"
        f"    _OPEN.get(p.name, p) for p in search.params] + {ADDED})\n"
        "TASK = _dataclasses.replace(TASK, structures={'search': search},\n"
        f"                            meanings={{**TASK.meanings, **{MEANINGS}}})\n"
    )
    path = Path(folder) / f"{name}.py"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


@pytest.fixture
def ring(tmp_path):
    return _load_task(_ring_task(tmp_path))


def _looks(task) -> dict:
    """The run's two looks: the first choice of each, a red disc among green."""
    return {p.name: p.choices[0] for p in task.params
            if p.name in ("target_appearance", "distractor_appearance")}


class _Drained(Simulated):
    """A link that queues `script[n]` as the `n`th drain begins (a command drained before trial `n`
    applies from trial `n + 1`). Past `BUDGET` drains the session is one that never ends, and fails
    here by name."""

    BUDGET = 60

    def __init__(self, script):
        super().__init__()
        self.script, self.drains = dict(script), 0

    def drain(self) -> list:
        self.drains += 1
        assert self.drains <= self.BUDGET, (
            f"the session drained {self.drains} times, past the budget of {self.BUDGET}")
        for command in self.script.get(self.drains, ()):
            self.queue(command)
        return super().drain()


def _nobody(trial, values, index) -> Scripted:
    """No gaze: each trial ends as a missed acquisition, at the fixture's 0.5 s."""
    return Scripted({})


def _session(tmp_path, link, *, values=None, blocks=None, trials=8) -> Session:
    path = _ring_task(tmp_path)
    task = _load_task(path)
    spec = SessionSpec(
        task=str(path), allocation="tasks/allocation.py", root=tmp_path,
        session_id="2027-01-14_01", subject="A", trials=trials, frame_period=1 / 240, seed=3,
        values={**_looks(task), **(values or {})}, bounds=_sessions.bounds(),
        already_delivered_today=0.0, deployment=Deployment.RIG_FIXED, geometry=DIRECT,
        session_kind="training", calibration=SRGB,
        **({} if blocks is None else {"blocks": blocks}))
    session = Session(spec, card=Card(), pump=Pump(), link=link)
    session.wall_clock = lambda: WALL_NOW + session.now()
    session.left_cage(at=WALL_NOW)
    session.head_fixed(at=session.wall_now())
    session.world = _nobody
    link.session = session
    return session


def _warned(session) -> list[dict]:
    path = session.directory / "warnings.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def _changes(session) -> list[dict]:
    path = session.directory / "parameter_changes.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def _fed(session) -> list[str]:
    return [said for kind, _, _, said in session.controls if kind == "warning"]


# --- Hard limits, each with its reason --------------------------------------------------------


def test_a_value_past_a_bound_is_refused_with_its_reason(tmp_path, ring):
    """§4: a time below 0 and a fraction above 1 cannot be. Each is refused first, blocking, with
    its reason -- by `check.beyond_range`, which the pre-flight and `Session.set` ask by their
    existing paths -- and live the value is refused, the previous one standing, nothing staged
    and no warning written."""
    (below, *_) = beyond_range(ring, {"fix_hold": -0.1})
    (above, *_) = beyond_range(ring, {"catch_share": 1.2})

    assert (below.code, below.blocking, below.detail) == (
        PAST_LIMIT, True, "'fix_hold' at -0.1 s is below its 0: below 0 cannot be")
    assert (above.code, above.blocking, above.detail) == (
        PAST_LIMIT, True, "'catch_share' at 1.2 fraction is above its 1: a fraction is at most 1")
    starting = preflight.values(ring, {"catch_share": 1.2},
                                [f for f in preflight.beyond(ring, {"catch_share": 1.2},
                                                             ALLOCATION, DIRECT, SRGB, None)
                                 if f.blocking])
    assert starting.result == "fail" and "past-limit: 'catch_share' at 1.2" in starting.said

    link = _Drained({2: [SetParameter(name="fix_hold", value=-0.1, by=JAKE),
                         SetParameter(name="catch_share", value=1.2, by=JAKE)]})
    session = _session(tmp_path, link, trials=3)
    session.run()

    assert session.refusals == [
        ("fix_hold", JAKE, "'fix_hold' at -0.1 is refused, and the previous value stands: "
                           "past-limit: 'fix_hold' at -0.1 s is below its 0: below 0 cannot be"),
        ("catch_share", JAKE, "'catch_share' at 1.2 is refused, and the previous value stands: "
                              "past-limit: 'catch_share' at 1.2 fraction is above its 1: a "
                              "fraction is at most 1")]
    assert (session.spec.values["fix_hold"], session.spec.values["catch_share"]) == (0.3, 0.1)
    assert [row["code"] for row in _warned(session)] == []


def test_standard_bounds_need_no_reason_and_others_are_warned_unexplained(tmp_path, ring):
    """The three standard reasons need no line of the task's own: a lowest of 0, a count's lowest
    of 1 and a fraction's highest of 1. A bound neither they nor its `why` explain is warned at
    load, `unexplained-limit`, accepted in every kind, naming the setting and its bound; the
    fixture's one other bound, COL-29's 80 cd/m², gives its reason."""
    assert UNEXPLAINED_LIMIT not in {f.code for f in check_task(ring, ALLOCATION)}
    declared = {p.name: p for p in ring.params}
    assert limit_reason(declared["fix_hold"], "low") == BELOW_ZERO
    assert limit_reason(declared["set_size"], "low") == BELOW_ONE
    assert limit_reason(declared["catch_share"], "high") == FRACTION_TOP
    assert limit_reason(declared["fix_luminance"], "high") == (
        "white on the default calibration, the sRGB standard's (COL-29)")
    assert limit_reason(declared["fix_hold"], "high") is None
    assert "objects" in COUNT_UNITS and limit_reason(
        Param("n", unit="deg", low=1.0), "low") is None

    capped = _load_task(_ring_task(tmp_path, name="capped", over=(
        '_OPEN["fix_acquisition"] = Param("fix_acquisition", unit="s", low=0.5, high=10.0, '
        'start=0.5)')))
    (unexplained,) = [f for f in check_task(capped, ALLOCATION) if f.code == UNEXPLAINED_LIMIT]

    assert (unexplained.blocking, unexplained.is_warning, unexplained.subjects) == (
        False, True, ("setting 'fix_acquisition'",))
    assert unexplained.detail.startswith(
        "'fix_acquisition' declares its lowest, 0.5 and its highest, 10 s, with no reason")


def test_param_why_is_one_printable_line_of_120_at_most():
    """A limit's reason is one line on a card: printable text of `REASON_LIMIT` (120) characters
    at most, refused otherwise as the setting is built, as a staircase's hardest step in words."""
    assert REASON_LIMIT == 120
    Param("x", unit="deg", low=0.0, high=10.0, why="w" * 120)
    for wrong in ("w" * 121, "two\nlines", "a\ttab", 3):
        with pytest.raises(ValueError, match="one printable line of 120 characters at most"):
            Param("x", unit="deg", low=0.0, high=10.0, why=wrong)


# --- The layout at the values set --------------------------------------------------------------


def test_at_values_pins_a_number_or_a_span():
    """`check.at_values` holds a number at itself, `low = high = start`, and a draw's two ends as
    a span, its start the least; a setting with choices and a word are left as declared."""
    task = _load_task(Path("tasks/visual_search.py"))
    pinned = at_values(task, {"set_size": 6, "array_eccentricity": (9.0, 7.0),
                              "target_appearance": "a word", "fix_hold": "a word"})
    declared = {p.name: p for p in pinned.params}

    assert (declared["set_size"].low, declared["set_size"].high, declared["set_size"].start) == (
        6, 6, 6)
    ring = declared["array_eccentricity"]
    assert (ring.low, ring.high, ring.start) == (7.0, 9.0, 7.0)
    assert declared["fix_hold"] == {p.name: p for p in task.params}["fix_hold"]
    assert LAYOUT == ("stimulus-off-screen", "overlapping-windows", "crowded-array",
                      "answer-window-reaches-objects", "window-inside-object", "objects-touch",
                      "scaled-small", "color-set-desaturated", "color-set-unreachable",
                      "specials-over-100")


def test_the_layout_is_judged_at_the_values_on_every_change(tmp_path):
    """Review Focus 3. The trainer raises `set_size` to 12, and the 1.6° windows on the 6° ring
    crowd: a warning naming the pair and both values, accepted by him and said on the feed.
    Lowering it to 4 again adds nothing. Then the ring is drawn, Uniform from 5° to 7°, and he
    moves its least to 3°: at its least end, eight objects crowd; judged at both its ends, so the
    warning names 3°, and its most end, on the field, refuses nothing."""
    blocks = [Block("b", [Condition("c", {}, target=12)], counting=EVERY_TRIAL,
                    draws={"array_eccentricity": Uniform(5.0, 7.0, repeat=FRESH)})]
    link = _Drained({
        2: [SetParameter(name="set_size", value=12, by=JAKE)],
        4: [SetParameter(name="set_size", value=4, by=JAKE)],
        6: [SetParameter(name="set_size", value=8, by=JAKE)],
        8: [SetRange(name="array_eccentricity", numbers={"low": 3.0}, by=JAKE)],
    })
    plain = _session(tmp_path / "plain", _Drained({
        2: [SetParameter(name="set_size", value=12, by=JAKE)],
        4: [SetParameter(name="set_size", value=4, by=JAKE)]}), trials=6)
    plain.run()

    assert plain.refusals == []
    (crowded,) = _warned(plain)
    assert (crowded["code"], crowded["how"], crowded["by"]) == (
        "crowded-array", "set", {"kind": "box", "name": "jake"})
    assert crowded["detail"].startswith(
        "array 'search' can put 12 objects ('set_size') on a 6° ring ('array_eccentricity'), "
        "3.10° apart, with windows of 1.6° radius ('object_window')")
    assert _fed(plain) == [f"crowded-array: {crowded['detail']}"]

    drawn = _session(tmp_path / "drawn", link, blocks=blocks, trials=12)
    drawn.run()

    assert drawn.refusals == []
    details = [row["detail"] for row in _warned(drawn) if row["code"] == "crowded-array"]
    assert len(details) == 2, details
    assert "12 objects ('set_size') on a 5° ring" in details[0]
    assert details[1].startswith(
        "array 'search' can put 8 objects ('set_size') on a 3° ring ('array_eccentricity')")
    assert details[1].endswith("(on the trials of block 'b', condition 'c')")


def test_a_stimulus_set_off_the_field_is_refused_whichever_setting_moved_it(tmp_path):
    """Review Focus 3: a stimulus off direct view's ±18.4° field is refused whichever setting moves
    it there -- the ring's eccentricity typed past the field, the fixation point moved by its own
    setting, or the ring's draw given a most past the field -- each refused as it is offered,
    naming the field, the previous value or range standing; the ring at 17.5°, inside, accepted."""
    blocks = [Block("b", [Condition("c", {}, target=6)], counting=EVERY_TRIAL,
                    draws={"array_rotation": Uniform(0.0, 90.0, repeat=FRESH)})]
    link = _Drained({
        2: [SetParameter(name="array_eccentricity", value=17.5, by=JAKE)],
        3: [SetParameter(name="array_eccentricity", value=19.0, by=JAKE),
            SetParameter(name="fix_drift", value=35.0, by=JAKE)],
    })
    session = _session(tmp_path, link, blocks=blocks, trials=4)

    session.run()

    assert [refusal[0] for refusal in session.refusals] == ["array_eccentricity", "fix_drift"]
    for name, value, why in session.refusals:
        assert why.startswith(f"{name!r} at "), why
        assert "the layout it leaves refuses it: stimulus-off-screen: " in why
        assert "outside the \u00b130.5\u00b0 \u00d7 \u00b118.4\u00b0 direct field" in why
    assert (session.spec.values["array_eccentricity"], session.spec.values["fix_drift"]) == (
        17.5, 0.0)

    drawn = [Block("b", [Condition("c", {}, target=6)], counting=EVERY_TRIAL,
                   draws={"array_eccentricity": Uniform(5.0, 7.0, repeat=FRESH)})]
    ranged = _session(tmp_path / "ranged", _Drained({2: [SetRange(
        name="array_eccentricity", numbers={"high": 19.0}, by=JAKE)]}), blocks=drawn, trials=3)
    ranged.run()

    ((name, _, why),) = ranged.refusals
    assert name == "array_eccentricity"
    assert why.startswith("the range of 'array_eccentricity' is not changed: the layout it leaves "
                          "refuses it: stimulus-off-screen: ")


def test_a_window_smaller_than_its_disc_is_warned(ring):
    """§4: an object window of 0.4° about a 1° disc leaves its edge outside: `window-inside-object`,
    a warning in every kind, at the values set; at the fixture's 1.6° none."""
    (found,) = [f for f in laid_out(ring, {"object_window": 0.4}, geometry=DIRECT)
                if f.code == "window-inside-object"]

    assert (found.blocking, found.is_warning) == (False, True)
    assert found.detail.startswith(
        "array 'search''s object windows can be 0.4° in radius ('object_window'), smaller than "
        "its objects, up to 1° across ('disc_size'), 0.5° in radius")
    assert "window-inside-object" not in {f.code for f in laid_out(ring, {}, geometry=DIRECT)}


def test_touching_discs_are_warned(ring):
    """§4: twelve 2° discs on a 3° ring are 1.55° apart center to center, closer than their sizes'
    mean: `objects-touch`, a warning in every kind; four of them on the 6° ring are not."""
    found = [f for f in laid_out(ring, {"set_size": 12, "array_eccentricity": 3.0,
                                        "disc_size": 2.0, "object_window": 0.5}, geometry=DIRECT)
             if f.code == "objects-touch"]

    assert [(f.blocking, f.is_warning) for f in found] == [(False, True)]
    assert found[0].detail == (
        "array 'search' can put 12 objects ('set_size') on a 3° ring ('array_eccentricity'), "
        "1.55° apart center to center, closer than their sizes' mean (2° ('disc_size')), so "
        "neighbors touch or overlap on the screen")
    assert "objects-touch" not in {f.code for f in laid_out(ring, {"disc_size": 2.0},
                                                             geometry=DIRECT)}



@pytest.mark.parametrize(("path", "setting"), [
    ("tasks/fixation_detection.py", "fix_window"),
    ("tasks/fixation_detection.py", "target_window"),
    ("tasks/visual_search.py", "object_window"),
    ("tasks/calibration.py", "cal_window"),
])
@pytest.mark.parametrize("value", [0.0, -2.0])
def test_a_reference_tasks_window_of_no_size_is_refused_at_the_values_set(path, setting, value):
    """The whole-build review's I1 (§4: "a size below zero" cannot be, nor 0): a reference task's
    gaze window, each leaving its lowest open, set to 0 or below is refused at the values set
    (`bad-window-radius`, blocking, naming the window and the setting) -- live and at a run's start
    alike, both reading `check.laid_out` -- and at 1° it is not. A window's radius, a gaze
    window's or an array's object windows' in degrees, is the same rule."""
    task = _load_task(Path(path))

    found = [f for f in laid_out(task, {setting: value}, allocation=ALLOCATION, geometry=DIRECT)
             if f.code == "bad-window-radius"]

    assert found and all(f.blocking for f in found), found
    assert all(f"({setting!r})" in f.detail and f"{value:g}°" in f.detail for f in found)
    assert not [f for f in laid_out(task, {setting: 1.0}, allocation=ALLOCATION, geometry=DIRECT)
                if f.code == "bad-window-radius"]


def test_a_declared_range_reaching_no_size_is_refused_at_load(tmp_path, ring):
    """I1 at load: a window's range declared at both ends is read over them, every value in it one
    a console can send, so a range reaching 0 is refused there, as a look's size reaching 0 is
    (`bad-block`); one leaving its lowest open is read at its start, and loads (the fixture's)."""
    assert "bad-window-radius" not in {f.code for f in check_task(ring, ALLOCATION,
                                                                   geometry=DIRECT)}
    closed = _load_task(_ring_task(tmp_path, name="closed", over=(
        '_OPEN["fix_window"] = Param("fix_window", unit="deg", low=0.0, high=5.0, start=2.0, '
        'why="a test\'s")')))

    (found,) = [f for f in check_task(closed, ALLOCATION, geometry=DIRECT)
                if f.code == "bad-window-radius" and f.subjects == ("window 'fix'",)]
    assert found.blocking
    assert found.detail.startswith("window 'fix': its radius can be 0° ('fix_window')")

@pytest.mark.skipif(XTASKS is None, reason="no wl-xtasks checkout holding the pop-out search")
def test_the_fixation_window_reaching_the_discs_is_still_warned():
    """§4, already a warning, on the PI's pop-out: its window about the center, whose exit starts
    the answer, at 5° reaches the 1.5° object windows on a 6° ring, so a correct look landing on a
    disc inside it never leaves it; at the values set, as at load, and not at its starts. **In each
    structure that scores the discs**: the search and the probe that shows the odd one alone (the
    pop-out revision), the fixation point's own window `fix` the one whose exit starts the answer,
    since the point stays on. **Said once, naming both** (XC-545), about each one's window."""
    popout = _load_task(XTASKS / "tasks" / "popout_search.py")
    starts = {p.name: p.start for p in popout.params if p.start is not None}
    found = [f for f in laid_out(popout, {**starts, "fix_window": 5.0, "ring_radius": 6.0},
                                 geometry=DIRECT)
             if f.code == "answer-window-reaches-objects"]

    assert [(f.is_warning, f.subjects) for f in found] == [
        (True, ("search: window 'fix'", "odd_one_alone: window 'fix'"))]
    assert found[0].detail.startswith("in structures 'search', 'odd_one_alone': ")
    assert "its radius up to 5° and theirs up to 1.5°" in found[0].detail
    assert not [f for f in laid_out(popout, starts, geometry=DIRECT)
                if f.code == "answer-window-reaches-objects"]


def test_an_open_range_is_judged_at_its_start_at_load(tmp_path, ring):
    """The load reads each open side at the setting's start: the fixture's open ring and windows
    load in direct view with no blocking finding. A ring whose start is past the field is refused
    there; one with no start is left to the run's start, no `stimulus-off-screen` at load. A set
    size reads its declared highest, which it must declare: with none it is refused at load, as
    the PI ruled on 2026-10-14, held at its start or not."""
    assert not [f for f in check_task(ring, ALLOCATION, geometry=DIRECT, calibration=SRGB)
                if f.blocking]
    far = _load_task(_ring_task(tmp_path, name="far", over=(
        '_OPEN["array_eccentricity"] = Param("array_eccentricity", unit="deg", low=0.0, '
        'start=19.0)')))
    unstarted = _load_task(_ring_task(tmp_path, name="unstarted", over=(
        '_OPEN["array_eccentricity"] = Param("array_eccentricity", unit="deg", low=0.0)')))

    assert "stimulus-off-screen" in {f.code for f in check_task(far, ALLOCATION, geometry=DIRECT)
                                     if f.blocking}
    assert "stimulus-off-screen" not in {
        f.code for f in check_task(unstarted, ALLOCATION, geometry=DIRECT)}
    endless = _load_task(_ring_task(tmp_path, name="endless", over=(
        '_OPEN["set_size"] = Param("set_size", unit="objects", low=1, start=4)')))
    assert [f.code for f in check_task(endless, ALLOCATION, geometry=DIRECT, calibration=SRGB)
            if f.blocking] == [
        "unbounded-set-size"]


def test_the_preflight_judges_the_layout_at_the_runs_values(ring):
    """A run's start is judged at its values (`preflight.laid_out`): a ring sent past the field
    blocks, failing the starting values item; twelve objects crowd, a warning offered at the start
    naming the plain run; and a plan's block drawing the ring from 3° to 7° is judged at both ends,
    its crowding at 3° named by plan, block and condition."""
    off = preflight.laid_out(ring, {"array_eccentricity": 19.0}, None, ALLOCATION, DIRECT, SRGB,
                             None)
    crowded = preflight.laid_out(ring, {"set_size": 12}, None, ALLOCATION, DIRECT, SRGB, None)
    plan = dataclass_plan(ring, Block("near", [Condition("c", {"set_size": 8}, target=2)],
                                      draws={"array_eccentricity": Uniform(3.0, 7.0,
                                                                           repeat=FRESH)}))
    drawn = preflight.laid_out(plan, {}, "p", ALLOCATION, DIRECT, SRGB, None)

    assert [(f.code, f.blocking) for f in off] == [("stimulus-off-screen", True)]
    assert off[0].detail.startswith("in the plain run: ")
    item = preflight.values(ring, {"array_eccentricity": 19.0}, [f for f in off if f.blocking])
    assert item.result == "fail" and "stimulus-off-screen: in the plain run" in item.said
    assert [(f.code, f.is_warning) for f in crowded] == [("crowded-array", True)]
    assert crowded[0].detail.startswith("in the plain run: array 'search' can put 12 objects")
    (near,) = [f for f in drawn if f.code == "crowded-array"]
    assert near.detail.startswith(
        "in plan 'p', block 'near', condition 'c': array 'search' can put 8 objects ('set_size') "
        "on a 3° ring")



def test_a_layout_the_preflight_cannot_judge_is_refused_under_its_own_code(ring, monkeypatch):
    """The whole-build review's m2: a layout check that raises at a run's start is a blocking
    finding saying so, under a code of its own, `layout-unjudged` -- not `stimulus-off-screen`,
    which would name a cause nobody found in the pre-flight item and the warnings record -- and it
    fails the starting values item."""
    def broken(*args, **kwargs):
        raise ZeroDivisionError("division by zero")

    monkeypatch.setattr(preflight, "check_laid_out", broken)
    (found,) = preflight.laid_out(ring, {}, None, ALLOCATION, DIRECT, SRGB, None)

    assert (found.code, found.blocking) == ("layout-unjudged", True)
    assert found.detail == ("the layout at the run's values could not be judged "
                            "(ZeroDivisionError: division by zero), so whether a stimulus leaves "
                            "the field is unknown")
    item = preflight.values(ring, {}, [found])
    assert item.result == "fail" and "layout-unjudged: " in item.said

def dataclass_plan(task, block):
    """`task` with one plan, `p`, of `block`."""
    import dataclasses

    from wl_xcon.task import Plan
    return dataclasses.replace(task, plans={"p": Plan([block])})


def test_every_change_path_asks_the_layout(tmp_path):
    """Each way a run's values change is judged by the layout at what it leaves, refused for a
    result off the field, nothing staged: a value typed, a range changed, a person's draw, a
    hand-back and a revert. The run starts with its ring 19° out, past the field, as only a run
    started in code without its pre-flight can (`preflight.laid_out` refuses it there), and the
    trainer brings it in to 6°. Then each path that would put a stimulus past the field is refused,
    saying so: typing the ring to 19° again, the drawn fixation point's range given a most of 40°
    (contrived: a place in seconds, so a timing setting's draw can move it), a person's draw of it
    up to 40°, handing the ring back to the run's 19°, and reverting to the run's start."""
    blocks = [Block("b", [Condition("c", {}, target=10)], counting=EVERY_TRIAL,
                    draws={"fix_drift": Uniform(0.0, 1.0, repeat=FRESH)})]
    link = _Drained({
        2: [SetParameter(name="array_eccentricity", value=6.0, by=JAKE)],
        4: [SetParameter(name="array_eccentricity", value=19.0, by=JAKE)],
        5: [SetRange(name="fix_drift", numbers={"high": 40.0}, by=JAKE)],
        6: [SetForm(name="fix_drift", shape="uniform", numbers={"low": 0.0, "high": 40.0},
                    by=JAKE)],
        7: [HandBack(name="array_eccentricity", by=JAKE)],
        8: [Revert(change=0, by=JAKE)],
    })
    session = _session(tmp_path, link, blocks=blocks, trials=10,
                       values={"array_eccentricity": 19.0})

    session.run()

    refused = [(name, why) for name, _, why in session.refusals]
    assert [name for name, _ in refused] == [
        "array_eccentricity", "fix_drift", "fix_drift", "array_eccentricity", "revert"], refused
    for name, why in refused:
        assert "the layout it leaves refuses it: stimulus-off-screen: " in why, (name, why)
    assert refused[0][1].startswith("'array_eccentricity' at 19 is refused, and the previous "
                                    "value stands: ")
    assert refused[1][1].startswith("the range of 'fix_drift' is not changed: ")
    assert refused[2][1].startswith("'fix_drift' is not drawn as asked: ")
    assert refused[3][1].startswith("'array_eccentricity' is not handed back: ")
    assert refused[4][1].startswith("the revert to the run's start is refused, and none of it "
                                    "applies: ")
    assert session.spec.values["array_eccentricity"] == 6.0
    assert session._forms == {} and session._edited == {"array_eccentricity"}
    assert not any(row["kind"] in ("range", "form", "hand_back", "revert")
                   for row in _changes(session))


def test_the_card_says_each_limits_reason(tmp_path):
    """§4: "each card says why for any limit that stays, in one line". A session's rows carry each
    limit's reason (`ParamRow.why`), and the card says it beside the range: a fraction's
    "0 to 1 fraction · a fraction is at most 1", a count's lowest, the task's own line; a setting
    with no bound says *no limit*, and one with a bound and no reason says the range alone."""
    session = _session(tmp_path, _Drained({}), trials=1)
    rows = {row[0]: ParamRow.of(*row) for row in session.parameters}

    assert rows["catch_share"].why == {"low": BELOW_ZERO, "high": FRACTION_TOP}
    assert _range(rows["catch_share"]) == "0.00 to 1.00 fraction · a fraction is at most 1"
    assert _range(rows["set_size"]) == (
        "1.00 to 12.00 objects · fewer than 1 cannot be: one is needed; a stand-in for the "
        "array&#x27;s places, which a set size must declare")
    assert _range(rows["fix_hold"]) == "0.00 to open s · below 0 cannot be"
    # At its step's decimals (`ParamRow.step`: cd/m2 steps by 1, `task.UNIT_STEPS`; the console
    # interface rework's Task 5), a step of 0.01 two.
    assert _range(rows["fix_luminance"]) == (
        "0 to 80 cd/m2 · white on the default calibration, the sRGB standard&#x27;s (COL-29)")
    assert rows["target_appearance"].why is None
    assert _range(ParamRow("free", "deg", None, None, 1.0, False)) == "no limit"
    assert _range(ParamRow("capped", "deg", 0.0, 10.0, 1.0, False,
                           why={"low": BELOW_ZERO, "high": None})) == (
        "0.00 to 10.00 deg · below 0 cannot be")
