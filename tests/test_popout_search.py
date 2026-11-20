"""The pop-out search, the lab's first real training task (the pop-out search build's Task 9; its
design, `docs/superpowers/specs/2026-11-07-popout-search-design.md` §3, every number in it the
PI's), as the task library wl-xtasks holds it, run through this engine.

**Read by path from a wl-xtasks checkout, never copied**: its `tasks/popout_search.py`, which reads
its colors from `stimuli/isohue.json` beside it. The checkout is the git-ignored link `wl-xtasks`
at this repository's root (a worktree's, as `wl-preproc` is, and where CI checks wl-xtasks's main
out), else one beside this repository. **A checkout without the task skips these tests locally,
and fails them under `WLX_REQUIRE_XTASKS=1`**, as the wl-preproc tests fail under
`WLX_REQUIRE_PREPROC=1`. CI checks wl-xtasks's main out but does not set it yet: the task reaches
wl-xtasks's main only when the PI merges it there.

What is held here: it loads with only the warnings expected of it; it declares the PI's values;
the go is the frame the discs come on and the fixation point goes off; the next saccade from
fixation answers, and a look to empty space, a wrong disc, an early saccade and leaving the odd one
before its hold are each an error with the blank timeout and no reward; a simulated session moves
up a stage only when a person confirms the rig's suggestion; its record reads back whole through
wl-preproc's own code; the twelve pairings and the four colors are equal in macaque luminance on
the test calibration; and a simulated session plays it end to end through the simulated eye, scored
by the rig's own eye rules (`gaze.Tracked`).

The trials here are played by a scripted eye through `gaze.Tracked` (`_Eye`): its saccades are the
simulated eye's minimum-jerk profile with its noise (`simeye`), each launched a set number of frames
after a state begins, so a test names the eye's movements and the rig's own rules score them.
Engine test material: no timing claim rests on the frames counted here, which are the simulated
frame clock's.
"""

from __future__ import annotations

import json
import os
import random
from collections import Counter
from dataclasses import replace
from pathlib import Path

import pytest

from _calibrations import PRIMARIES, measured
from _rig import DIRECT
from wl_xcon import cones, photometry, simeye
from wl_xcon.actor import Box
from wl_xcon.bounds import Bounds, Ceiling, Floor
from wl_xcon.check import check_task
from wl_xcon.cli import _load_allocation, _load_task
from wl_xcon.dio import Simulated as Card
from wl_xcon.eye import EyeReading, Sample, Tracker
from wl_xcon.findings import SESSION_KINDS
from wl_xcon.gaze import Tracked
from wl_xcon.geometry import on_circle_deg, separation_deg
from wl_xcon.link import BackBlock, Decline, NextBlock, SetParameter, Simulated, Stop
from wl_xcon.photometry import D65, SRGB, ColorSetLight, xyY
from wl_xcon.run import Recorded, run_trial
from wl_xcon.task import (
    EXPECTED,
    HARDER,
    NOT_DIFFICULTY,
    SPENT,
    Array,
    ByCriterion,
    Counting,
    Disc,
    ObjectWindows,
    Outcome,
    P,
    Reward,
    Show,
    Steps,
    Window,
    actions_of,
    staircase_verdict,
)
from wl_xcon.taskd import Session, SessionSpec, _appeared
from wl_xcon.welfare import Deployment, Simulated as Pump

ROOT = Path(__file__).resolve().parents[1]
#: Where a wl-xtasks checkout is looked for: the link at this repository's root, then beside it.
#: The first holding the task is read.
CANDIDATES = (ROOT / "wl-xtasks", ROOT.parent / "wl-xtasks")
XTASKS = next((c for c in CANDIDATES if (c / "tasks" / "popout_search.py").is_file()), None)
if XTASKS is None and os.environ.get("WLX_REQUIRE_XTASKS") == "1":  # pragma: no cover - CI's
    raise AssertionError(
        f"WLX_REQUIRE_XTASKS=1 but no wl-xtasks checkout holding tasks/popout_search.py was found "
        f"at {' or '.join(str(c) for c in CANDIDATES)}. The lab's first real task is tested only "
        f"here; skipping it would report a task nobody ran"
    )

pytestmark = pytest.mark.skipif(
    XTASKS is None,
    reason="no wl-xtasks checkout holding tasks/popout_search.py at the repository's root or "
    "beside it; the pop-out search is read from there",
)

TASK_FILE = None if XTASKS is None else XTASKS / "tasks" / "popout_search.py"
STIMULI = None if XTASKS is None else XTASKS / "stimuli" / "isohue.json"
#: The colors as this repository's tests derived them (the pop-out search build's Task 2).
FIXTURE = Path(__file__).parent / "fixtures" / "isohue.json"
ALLOCATION = "tasks/allocation.py"
#: `TIMEOUT_ON` in the reference allocation: the error's blank screen begins.
TIMEOUT_ON = 4138
#: The trial's other codes the tests below read: the odd one held, the reward commanded; and each
#: error's reason, strobed before the trial's end marker.
OUTCOME_CORRECT, REWARD_COMMANDED = 4110, 4102
REASON = {Outcome.WRONG_TARGET: 4113, Outcome.ABORT: 4118, Outcome.FIXATION_BREAK: 4119,
          Outcome.TARGET_BREAK: 4120}

#: The simulated frame clock: 240 Hz, as a simulated session runs.
FRAME = 1 / 240
HZ = 240
COLORS = ("blue", "purple", "red", "green")
JAKE = Box("jake")


@pytest.fixture(scope="module")
def task():
    return _load_task(TASK_FILE)


def _bounds() -> Bounds:
    return Bounds(
        subject="A",
        ceilings={
            "reward_correct": Ceiling(value=0.15, maximum=0.40, unit="mL"),
            "out_of_cage": Ceiling(value=28_800.0, maximum=100_000.0, unit="s"),
        },
        minima={"daily_fluid": Floor(value=250.0, unit="mL")},
    )


def _look(look) -> tuple[str, object]:
    """A pool look's color name and the fraction of the set's luminance it is drawn at."""
    return look.color.color, look.color.fraction


def _pairing(task, odd: str, among: str) -> tuple:
    """The pool's pairing of the odd one `odd` among distractors `among`."""
    (found,) = [pairing for pairing in task.pool.choices
                if _look(pairing[0])[0] == odd and _look(pairing[1])[0] == among]
    return found


def _values(task, *, odd: str = "blue", among: str = "red", set_size: int = 4,
            rotation: float = 0.0) -> dict:
    """A trial's values: the task's own starts, the pairing of `odd` among `among`, `set_size`
    discs and the ring turned to `rotation`, the odd one at that direction."""
    values = {param.name: param.start for param in task.params if param.start is not None}
    looks = _pairing(task, odd, among)
    values.update(odd_color=looks[0], distractor_color=looks[1], set_size=set_size,
                  array_rotation=rotation)
    return values


class _Eye:
    """**A scripted eye, the sample source `gaze.Tracked` reads**: it starts away from every window
    and makes `moves` in turn, each `(state, frames, to)` launched `frames` after `state` first
    began, to `to` in degrees, with the simulated eye's minimum-jerk profile, duration and noise
    (`simeye`), so the rig's detector finds each saccade. `begun` holds each state's first frame."""

    def __init__(self, moves, start=(6.0, 6.0), seed: int = 1) -> None:
        self.moves = list(moves)
        self.x, self.y = start
        self.begun: dict[str, int] = {}
        self.flight = None
        self.noise = random.Random(seed)
        self.samples = 0

    def step(self, frame: int) -> None:
        if self.flight is not None:
            launched, (x0, y0), (x1, y1), duration = self.flight
            tau = (frame - launched) * FRAME / duration
            if tau >= 1.0:
                self.x, self.y, self.flight = x1, y1, None
            else:
                share = tau ** 3 * (10.0 - 15.0 * tau + 6.0 * tau * tau)
                self.x, self.y = x0 + (x1 - x0) * share, y0 + (y1 - y0) * share
            return
        if self.moves:
            state, frames, to = self.moves[0]
            if state in self.begun and frame >= self.begun[state] + frames:
                self.moves.pop(0)
                duration = (simeye.DURATION_S
                            + simeye.DURATION_PER_DEG_S * separation_deg(self.x, self.y, *to))
                self.flight = (frame, (self.x, self.y), to, duration)

    def poll(self, at: float) -> Sample:
        self.samples += 1
        noise = self.noise
        reading = EyeReading(self.samples, (0.0, 0.0), 1.0,
                             (self.x + noise.gauss(0.0, simeye.NOISE_DEG),
                              self.y + noise.gauss(0.0, simeye.NOISE_DEG)), (0.0, 0.0))
        return Sample(at, reading, reading)


class _Seen(Tracked):
    """`gaze.Tracked`, the rig's gaze world, its tracker the scripted eye: told each state's first
    frame and each frame's display before `Tracked` is, as `simeye.Seeing` tells its eye."""

    def __init__(self, eye: _Eye, trial, values: dict) -> None:
        Tracked.__init__(self, Tracker(), simeye.MAPPING, trial, FRAME, values, source=eye)
        self.eye = eye

    def began(self, state: str, frame: int) -> None:
        self.eye.begun.setdefault(state, frame)
        Tracked.began(self, state, frame)

    def display(self, visible, frame: int) -> None:
        self.eye.step(frame)
        Tracked.display(self, visible, frame)


def _play(task, moves, *, eye_at=(6.0, 6.0), **values):
    """One trial of the task, its eye making `moves` from `eye_at`: the result, the eye, and its
    marks and rewards in order."""
    bound = _values(task, **values)
    eye = _Eye(moves, start=eye_at)
    effects = Recorded()
    result = run_trial(task.trial, _Seen(eye, task.trial, bound), FRAME, values=dict(bound),
                       effects=effects)
    return result, eye, effects.log


def _shown(result) -> dict:
    """Each stimulus's (on, off) frames, by name; one presentation each here."""
    shown = {}
    for presentation in result.shown:
        assert presentation.name not in shown, result.shown
        shown[presentation.name] = (presentation.on, presentation.off)
    return shown


#: Where the scripted eye looks, with the ring turned to 0° and four discs: the odd one at 0°, a
#: distractor at 90°, and empty space on the ring at 45°, 6.1° from either.
FIXATION = (0.0, 0.0)
ODD_ONE = on_circle_deg(0.0, 0.0, 8.0, 0.0)
OTHER = on_circle_deg(0.0, 0.0, 8.0, 90.0)
EMPTY = on_circle_deg(0.0, 0.0, 8.0, 45.0)
#: The eye takes the fixation point 50 frames after it comes on, and answers 48 frames (0.2 s)
#: after the go.
LOOK = ("await_fix", 50, FIXATION)


def _timed_out(task, result, eye, log, state: str, outcome: Outcome) -> None:
    """The trial ended `outcome` after `timeout` seconds of blank screen from the frame it entered
    `state`, the array (or the fixation point) off that frame, no reward, its timeout strobed then
    and its reason last."""
    assert result.outcome is outcome, (result.outcome, result.visited)
    assert result.visited[-1] == state
    timeout = round(_start(task, "timeout") * HZ)
    began = eye.begun[state]
    assert result.frames == began + timeout - 1, "the blank lasted the timeout, then the trial ended"
    offs = [off for _, off in _shown(result).values()]
    assert None not in offs and max(offs) == began, "the screen blank from the error's frame"
    assert not [entry for entry in log if entry[0] == "reward"], log
    assert log[-2:] == [("mark", TIMEOUT_ON), ("mark", REASON[outcome])], log


def _start(task, name: str):
    (param,) = [param for param in task.params if param.name == name]
    return param.start


# --- It loads, with the PI's values -------------------------------------------------------------


def test_popout_loads_clean_but_the_expected_warnings(task):
    """Against this repository's allocation, in direct view, head-fixed: nothing refused in any
    session kind. On the default calibration, its colors and lights are nominal (`color-on-default`,
    `contrast-on-default`). In both, its plan has no end of its own (`endless-plan`): the trainer
    ends a run; and the suggestions' margin, up to 20 answers, can reach a bar's count on the
    smallest windows (`margin-reaches-bar`; the re-review 2, M-7), the training plan's settings
    being read over their ranges; and the set size read at its top, the PI's 36 (2026-11-19), which
    crowds the ring's windows (`crowded-array`). **Since the pop-out's revision** its go no longer
    hides the fixation point (no `fixation-hidden-at-go`; TSK-79: the point stays on and takes its
    act look), and the fixation point's saturation is judged at its start at load, 0, the set's
    gray, so nothing is paler (`test_popout_revision.py`). **Since the console settings plan's Task 11
    nothing else**: its
    caps gone and its open sides judged at their starts (the controller's ruling 5), the layout
    warns of nothing there (`test_the_popout_loads_with_no_layout_warning_at_its_starts`) -- the
    windows that could overlap over the old ranges (`crowded-array`), the fixation window reaching
    the discs' (`answer-window-reaches-objects`), windows inside their discs
    (`window-inside-object`) and discs touching (`objects-touch`) are each said where a value set
    makes it so -- every limit has its reason (`unexplained-limit`), and the colors, judged at
    their start, 15 cd/m², are shown as written on the sRGB standard (`color-set-desaturated`, said
    over the old range above about 26 cd/m², is judged at a value set live since the whole-build
    review's I2: `test_brightening_the_colors_past_what_the_panel_shows_warns_live`)."""
    allocation = _load_allocation(Path(ALLOCATION))

    on_default = check_task(task, allocation, geometry=DIRECT, calibration=SRGB,
                            deployment=Deployment.RIG_FIXED, source=TASK_FILE)
    on_measured = check_task(task, allocation, geometry=DIRECT, calibration=measured(),
                             deployment=Deployment.RIG_FIXED, source=TASK_FILE)

    for found in (on_default, on_measured):
        assert [f for f in found if any(f.refuses(kind) for kind in SESSION_KINDS)] == []
        assert all(f.is_warning for f in found), found
    assert {f.code for f in on_default} == {"color-on-default", "contrast-on-default",
                                             "margin-reaches-bar", "endless-plan",
                                             "crowded-array"}
    # Each said once, naming the structures it is in (XC-545).
    for code in ("color-on-default", "contrast-on-default"):
        (one,) = [f for f in on_default if f.code == code]
        assert one.detail.startswith(f"in structures {', '.join(map(repr, task.structures))}: ")
    assert {f.code for f in on_measured} == {"margin-reaches-bar", "endless-plan",
                                              "crowded-array"}
    # The set size's range is closed (a highest is kept for `unbounded-set-size`), so the load
    # reads it at its top: the PI's 36 (2026-11-19) on the 8° ring crowds the 1.5° windows.
    for found in (on_default, on_measured):
        crowded = [f.detail for f in found if f.code == "crowded-array"]
        assert len(crowded) == 1 and "36 objects ('set_size')" in crowded[0], crowded


def test_it_holds_the_pis_values(task):
    """§3, every number the PI's: the trial's times and sizes as each setting's start, the stages
    and their bars, the colors, black, one reward, a fixed head; and every setting of numbers starts
    somewhere (the two looks the pool gives each trial are appearances, which take none). **Every
    number is a setting** (the PI, 2026-11-07: "everything should be adjustable in the console,
    no?"): the sizes, the colors' brightness, the bars and their windows, the staircases' counts and
    steps, each starting at the PI's value, and none of them a difficulty but the sizes and the
    brightness. **Since the pop-out's revision** (its design, §2 to §6) the task has its four special
    kinds' structures beside the search, the array appears with its delay, the fixation point is
    drawn in its hold look and scored by its own window throughout, and the engine's waits are
    settings too (`test_popout_revision.py` holds the rest)."""
    trial = task.trial
    assert list(task.structures) == ["search", "target_absent", "odd_place_empty",
                                     "distractor_alone", "odd_one_alone"]
    assert task.default == "search"
    starts = {param.name: param.start for param in task.params}
    assert {name: starts.get(name) for name in (
        "inter_trial", "fix_acquisition", "fix_hold", "response_deadline", "target_hold",
        "timeout", "fix_window", "object_window")} == {
        "inter_trial": 1.0, "fix_acquisition": 2.0, "fix_hold": 0.5, "response_deadline": 1.0,
        "target_hold": 0.3, "timeout": 2.0, "fix_window": 2.0, "object_window": 3.0}
    assert {name: starts.get(name) for name in (
        "disc_size", "ring_radius", "fix_size", "color_luminance", "move_up_bar",
        "move_up_window", "move_back_bar", "move_back_window", "staircase_down", "staircase_up",
        "fade_in_step", "crowd_step", "fade_in_floor", "crowd_floor", "suggestion_margin")} == {
        "disc_size": 1.0, "ring_radius": 8.0, "fix_size": 0.3, "color_luminance": 15.0,
        "move_up_bar": 0.8, "move_up_window": 50, "move_back_bar": 0.5, "move_back_window": 50,
        "staircase_down": 3, "staircase_up": 1, "fade_in_step": 0.1, "crowd_step": 1,
        "fade_in_floor": 0.1, "crowd_floor": 4, "suggestion_margin": 3}
    for name in ("move_up_bar", "move_up_window", "move_back_bar", "move_back_window",
                 "staircase_down", "staircase_up", "fade_in_step", "crowd_step", "ring_radius",
                 "fade_in_floor", "crowd_floor", "suggestion_margin"):
        assert task.meanings[name].kind == NOT_DIFFICULTY, name
    assert [param.name for param in task.params if param.start is None] == [
        "odd_color", "distractor_color"]
    assert all(param.choices for param in task.params if param.start is None)
    assert trial.background is None, "black, the default bottom layer"
    # The array appears with its delay, before the go, so a trial that reaches it and ends
    # unanswered is a failure: "a wrong item and no response count as failures" (§3.4; the build's
    # review, I1).
    assert trial.counting == Counting(after_stimulus=SPENT, appears="delay")

    shows = {action.stimulus.name: action.stimulus
             for _, action in actions_of(trial) if isinstance(action, Show)}
    assert set(shows) == {"fix", "search"}
    assert shows["fix"].looks == P("fix_look")
    (hold,) = [param for param in task.params if param.name == "fix_look"]
    assert isinstance(hold.start, Disc) and hold.start.size == P("fix_size")
    ring = shows["search"].looks
    assert isinstance(ring, Array) and ring.radius == P("ring_radius") and ring.n == P("set_size")
    assert (ring.looks, ring.among) == (P("odd_color"), P("distractor_color"))
    # The discs' windows a multiple of each disc's radius since the console settings plan's Task
    # 11: 3.0, the PI's 1.5° about a 1° disc
    # (`test_the_popouts_object_window_is_three_times_a_discs_radius`).
    windows = {window.name if isinstance(window, Window) else window.of: (
        window.radius if isinstance(window, Window) else window.scale)
        for window in trial.windows}
    assert windows == {"fix": P("fix_window"), "search": P("object_window")}
    assert any(isinstance(window, ObjectWindows) for window in trial.windows)
    rewards = [action for _, action in actions_of(trial) if isinstance(action, Reward)]
    assert rewards == [Reward("reward_correct")]
    assert task.needs_fixed_head is True

    (plan,) = task.plans.values()
    assert list(task.plans) == ["training"]
    assert plan.order == ByCriterion(fall_back=(P("move_back_bar"), P("move_back_window")),
                                     confirm=True, margin=P("suggestion_margin"))
    assert [block.name for block in plan.blocks] == ["Alone", "Fade-in", "Crowd"]
    assert all(block.criterion == (P("move_up_bar"), P("move_up_window")) for block in plan.blocks)
    alone, fade_in, crowd = plan.blocks
    assert [c.values for c in alone.conditions] == [{"set_size": 1}] and alone.staircase is None
    assert [c.values for c in fade_in.conditions] == [{"set_size": 4}]
    assert [c.values for c in crowd.conditions] == [{"distractor_fraction": 1.0}]
    counts = (P("staircase_down"), P("staircase_up"))
    assert (fade_in.staircase.levels, (fade_in.staircase.down, fade_in.staircase.up)) == (
        Steps(P("fade_in_floor"), 1.0, P("fade_in_step")), counts)
    assert (crowd.staircase.levels, (crowd.staircase.down, crowd.staircase.up)) == (
        Steps(P("crowd_floor"), 12, P("crowd_step")), counts)
    faint = fade_in.staircase.at(starts)
    assert (faint.setting, faint.down, faint.up, faint.start) == ("distractor_fraction", 3, 1, None)
    assert faint.levels == (0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0)
    assert faint.nearest(starts["distractor_fraction"]) == 0, "Fade-in starts faint"
    more = crowd.staircase.at(starts, whole=True)
    assert (more.setting, more.levels, more.down, more.up, more.start) == (
        "set_size", (4, 5, 6, 7, 8, 9, 10, 11, 12), 3, 1, None)
    assert more.nearest(starts["set_size"]) == 0, "Crowd starts at 4"
    for name in ("set_size", "distractor_fraction"):
        assert (task.meanings[name].kind, task.meanings[name].raising) == (EXPECTED, HARDER), name
    assert task.meanings["pairings"].kind == NOT_DIFFICULTY

    pool = task.pool
    assert (pool.setting, pool.odd, pool.distractor) == ("pairings", "odd_color",
                                                           "distractor_color")
    assert sorted((_look(odd)[0], _look(among)[0]) for odd, among in pool.choices) == sorted(
        (odd, among) for odd in COLORS for among in COLORS if odd != among)
    for odd, among in pool.choices:
        assert isinstance(odd, Disc) and isinstance(among, Disc)
        assert (odd.size, among.size) == (P("disc_size"), P("disc_size"))
        assert _look(odd)[1] == 1.0 and _look(among)[1] == P("distractor_fraction")
        assert odd.color.luminance == among.color.luminance == P("color_luminance")
    assert pool.unpooled(starts["pairings"]) is None


def test_its_pairings_are_named_by_their_colors_for_the_trainer_and_the_reviewer(task):
    """Task 9's report: the trainer saw "pairing 1" to "pairing 12" and the review report mapped
    them to long disc reprs. Each pairing is named by its colors, the odd one's first -- "blue among
    purple" -- in the pool's order, the n-th worth 2 ** n: on the start form and the trainer's panel
    (`taskd.start_rows`, the rig's own rows), in the sentence a pool's value is refused with, and
    in `wlx review`'s table of the pool and where it starts."""
    from wl_xcon.review import render_task as render_review
    from wl_xcon.taskd import start_rows

    names = tuple(f"{odd} among {among}" for odd in COLORS for among in COLORS if among != odd)
    _, row = start_rows(task, "training", {})
    report = render_review(task, _load_allocation(Path(ALLOCATION)).task_events)

    assert row.pairings == names and row.start == 66
    assert "1, blue among purple; 2, blue among red; 4, blue among green" in task.pool.unpooled(0)
    assert "| 1 | blue among purple | Disc(" in report and "| 2048 | green among red | Disc(" in report
    assert "It starts at 66: blue among red, red among blue." in report
    assert "pairing 1" not in report


# --- The trial ----------------------------------------------------------------------------------


def test_the_go_is_the_frame_the_array_appears(task):
    """§3.1, "no delay between array presentation and fixation dimming/go cue", as revised (the
    pop-out revision's §3, `go_delay` 0 to start): the discs come on and the fixation point takes
    its act look on one frame, the frame the trial enters `go`, after the second of blank screen
    between trials and the fixation held 0.5 s; **the point stays on** (§2). Held 0.3 s, the odd
    one pays one reward and the trial ends, with no timeout."""
    result, eye, log = _play(task, [LOOK, ("go", 48, ODD_ONE)])

    shown = _shown(result)
    assert result.outcome is Outcome.CORRECT, result.visited
    go = eye.begun["go"]
    assert eye.begun["await_fix"] == 1 + HZ, "a second of blank screen between trials"
    assert shown["fix"] == (eye.begun["await_fix"], None)
    assert [(changed.name, changed.frame) for changed in result.changed] == [("fix", go)]
    assert shown["search"] == (go, None)
    assert go == eye.begun["hold_fix"] + round(0.5 * HZ)
    assert result.frames == eye.begun["on_target"] + round(0.3 * HZ) - 1
    assert [entry for entry in log if entry[0] == "reward"] == [("reward", "reward_correct")]
    assert log[-3:] == [("mark", OUTCOME_CORRECT), ("mark", REWARD_COMMANDED),
                        ("reward", "reward_correct")]


@pytest.mark.parametrize("then", ["stays", "looks again"])
def test_a_saccade_to_empty_space_is_an_error_with_the_timeout(task, then):
    """§3.1, "anything other than looking at the target with the next saccade from fix to the
    target is an error": a saccade landing on empty space is an abort, the screen blank for the
    timeout, no reward -- whether the eye stays there or looks on to the odd one."""
    moves = [LOOK, ("go", 48, EMPTY)]
    if then == "looks again":
        moves.append(("flight", 36, ODD_ONE))

    result, eye, log = _play(task, moves)

    _timed_out(task, result, eye, log, "astray", Outcome.ABORT)
    assert "on_target" not in result.visited


@pytest.mark.parametrize(("where", "state", "outcome"), [
    (("go", 48, OTHER), "wrong", Outcome.WRONG_TARGET),
    (("hold_fix", 60, ODD_ONE), "early", Outcome.FIXATION_BREAK),
])
def test_a_wrong_disc_and_an_early_saccade_are_errors_with_the_timeout(task, where, state,
                                                                       outcome):
    """§3.1: a saccade landing on another disc is a wrong target; leaving the fixation point before
    the go is an early saccade. Each blanks the screen for the timeout, no reward, and keeps its
    own outcome. The early one never shows the discs."""
    result, eye, log = _play(task, [LOOK, where])

    _timed_out(task, result, eye, log, state, outcome)
    if outcome is Outcome.FIXATION_BREAK:
        assert "search" not in _shown(result) and "go" not in eye.begun


def test_a_target_break_is_an_error(task):
    """§3.1: leaving the odd one before its 0.3 s is an error with the timeout and no reward, and a
    staircase counts it a failure (TSK-33 as built); leaving it after 0.3 s is a correct trial."""
    early, eye, log = _play(task, [LOOK, ("go", 48, ODD_ONE), ("on_target", 30, EMPTY)])
    late, _, late_log = _play(task, [LOOK, ("go", 48, ODD_ONE), ("on_target", 80, EMPTY)])

    _timed_out(task, early, eye, log, "broke", Outcome.TARGET_BREAK)
    assert staircase_verdict(Outcome.TARGET_BREAK, shown=True) is False
    assert late.outcome is Outcome.CORRECT
    assert [entry for entry in late_log if entry[0] == "reward"] == [("reward", "reward_correct")]


def test_no_response_after_the_go_is_a_failure_with_no_timeout_and_no_reward(task):
    """§3.1 and §3.4 (the build's review, I1): an eye that holds the fixation point through the go
    and makes no saccade ends the trial `NO_RESPONSE` once the response deadline passes; the array
    had appeared, so the staircase counts it a failure ("a wrong item and no response count as
    failures"), and it is no error of §3.1's: no timeout, no reward. The task's counting table
    (`appears="go"`) is what makes it shown."""
    result, eye, log = _play(task, [LOOK])

    assert result.outcome is Outcome.NO_RESPONSE, result.visited
    assert result.visited[-1] == "go" and "flight" not in result.visited
    shown = _appeared(task.trial, result)
    assert shown is True
    assert staircase_verdict(result.outcome, shown) is False
    assert result.frames == eye.begun["go"] + round(_start(task, "response_deadline") * HZ) - 1
    assert ("mark", TIMEOUT_ON) not in log
    assert not [entry for entry in log if entry[0] == "reward"], log


def test_an_eye_already_at_the_center_as_the_fixation_point_comes_on_has_entered_it(task):
    """**The PI's try-out of demo mode, 2026-11-16**: "if i already have the "gaze" near the center
    when the fixation dot appears, i have to leave the window and reenter to start the trial. If I
    am already at the center, i shouldn't have to leave and reenter". An eye resting at the center
    through `between`, the blank before the fixation point, has entered `fix` on `await_fix`'s
    first frame, the one the point is first drawn on, and the trial goes on to `hold_fix` the next
    frame without the eye moving. **The hold counts from `hold_fix`'s first frame**, never from
    before the point came on, so the go comes `fix_hold` after it, not sooner. Until then `Entered`
    fired only on an edge against the frame before, and membership is judged in every state, so the
    eye was already inside as `await_fix` began and the trial ended `NO_FIXATION` (decisions.md
    EYE-30)."""
    result, eye, log = _play(task, [("go", 48, ODD_ONE)], eye_at=FIXATION)

    assert result.outcome is Outcome.CORRECT, result.visited
    assert result.visited[:5] == ("between", "await_fix", "hold_fix", "delay", "go")
    shown = _shown(result)
    assert eye.begun["await_fix"] == 1 + HZ, "a second of blank screen between trials"
    assert shown["fix"][0] == eye.begun["await_fix"]
    assert eye.begun["hold_fix"] == eye.begun["await_fix"] + 1, "entered on await_fix's first frame"
    assert eye.begun["go"] == eye.begun["hold_fix"] + round(_start(task, "fix_hold") * HZ), (
        "the hold counts from hold_fix's first frame, not from before the point came on")
    assert [entry for entry in log if entry[0] == "reward"] == [("reward", "reward_correct")]


# --- Sessions -----------------------------------------------------------------------------------


def _spec(root: Path, *, seed: int, start_block: str | None = None) -> SessionSpec:
    return SessionSpec(
        task=str(TASK_FILE), allocation=ALLOCATION, root=root, session_id="2027-01-14_01",
        subject="A", trials=1, frame_period=FRAME, seed=seed, values={}, bounds=_bounds(),
        already_delivered_today=0.0, deployment=Deployment.RIG_FIXED, geometry=DIRECT,
        session_kind="training", calibration=SRGB, plan="training", start_block=start_block,
    )


def _opened(spec: SessionSpec, link) -> Session:
    """A session on the simulators, its world left to it (the simulated eye), out of its cage and
    its head fixed, its wall following its frames."""
    session = Session(spec, card=Card(), pump=Pump(), link=link)
    session.wall_clock = lambda: 1_700_000_000.0 + session.now()
    session.left_cage(at=session.wall_now())
    session.head_fixed(at=session.wall_now())
    return session


def _rows(session: Session, name: str) -> list[dict]:
    path = session.directory / name
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


class _Trainer(Simulated):
    """**The trainer at the console**, between trials, as the panel's *Hold* and *Move up* send:
    the rig's first suggestion to move up is held after it has stood `HELD` trials; a later one is
    confirmed once it has stood `STANDS`; the run is stopped `AFTER` trials into the next stage. A
    run still going at `BUDGET` drains is stopped there, `ran_out`, rather than run to the
    out-of-cage limit."""

    HELD, STANDS, AFTER, BUDGET = 5, 20, 30, 600

    def __init__(self) -> None:
        super().__init__()
        self.session: Session | None = None
        self.drains = 0
        #: Each suggestion to move up, by its id: the drain it was first seen standing.
        self.first: dict[int, int] = {}
        self.held = self.confirmed = None
        self.ran_out = False

    def drain(self) -> list:
        self.drains += 1
        if self.drains == self.BUDGET:
            self.ran_out = True
            self.queue(Stop(by=JAKE))
        offered = self.session.suggestion
        if offered is not None and offered[1] == "up":
            change = offered[0]
            stood = self.drains - self.first.setdefault(change, self.drains)
            if self.held is None and stood >= self.HELD:
                self.held = (self.drains, change)
                self.queue(Decline(suggestion=change, by=JAKE))
            elif (self.held is not None and self.confirmed is None and change != self.held[1]
                  and stood >= self.STANDS):
                self.confirmed = (self.drains, change)
                self.queue(NextBlock(by=JAKE, suggestion=change))
        if self.confirmed is not None and self.drains == self.confirmed[0] + self.AFTER:
            self.queue(Stop(by=JAKE))
        return super().drain()


@pytest.fixture(scope="module")
def confirmed(tmp_path_factory):
    """A simulated session of the plan from Alone, its animal the simulated eye, right on 95% of its
    answers so the bar stays met: the trainer holds the rig's first suggestion to move up, confirms
    a later one, and stops the run thirty trials into Fade-in."""
    trainer = _Trainer()
    spec = replace(_spec(tmp_path_factory.mktemp("confirmed"), seed=3), accuracy=0.95)
    session = _opened(spec, trainer)
    trainer.session = session
    session.run()
    return session, trainer


def test_a_simulated_session_moves_up_only_on_confirmation(confirmed):
    """§3.4, "Rig suggests, trainer confirms": the bar met in Alone (80% of the last 50 answers),
    the rig suggests Fade-in and the run stays in Alone, through a hold and for the twenty trials a
    second suggestion stands unanswered; it moves to Fade-in at the trial after the trainer
    confirms, and only then. Fade-in's distractors start faint, given by its staircase."""
    session, trainer = confirmed
    lines = _rows(session, "trials.jsonl")
    changes = _rows(session, "parameter_changes.jsonl")
    controls = _rows(session, "controls.jsonl")
    assert trainer.held is not None and trainer.confirmed is not None, "no suggestion to answer"
    assert session.stop_kind == "operator" and not trainer.ran_out

    ups = [row for row in changes if row["kind"] == "suggested" and row["move"] == "up"]
    assert len(ups) >= 2
    assert {(row["block"], row["was"], row["now"], row["at_hardest"]) for row in ups} == {
        ("Alone", "Alone", "Fade-in", True)}
    assert all(row["bar"]["of"] == 50 and row["bar"]["correct"] >= 40 for row in ups)
    assert (ups[0]["change"], ups[-1]["change"]) == (trainer.held[1], trainer.confirmed[1])
    declined = [row for row in changes if row["kind"] == "declined"]
    assert trainer.held[1] in {row["suggestion"] for row in declined}
    assert all(row["by"] == {"kind": "box", "name": "jake"} for row in declined)
    (move,) = [row for row in controls if row["kind"] == "next_block"]
    assert move["suggestion"] == trainer.confirmed[1]

    blocks = [line["block"] for line in lines]
    switch = blocks.index("Fade-in")
    assert set(blocks[:switch]) == {"Alone"} and set(blocks[switch:]) == {"Fade-in"}
    assert lines[switch]["index"] == move["trial_index"], "it moved where the confirmation reached"
    standing = [line for line in lines[:switch] if line["trial_number"] > ups[-1]["trial_number"]]
    assert len(standing) >= _Trainer.STANDS - 1, "the bar met, the run stayed until confirmed"
    after = lines[switch:]
    assert after[0]["params"]["distractor_fraction"] == 0.1
    assert all(line["drawn"]["distractor_fraction"] == "staircase" for line in after)
    assert all(line["params"]["set_size"] == 4 for line in after)


def test_the_record_reads_back_whole_through_wl_preproc(confirmed):
    """The path, not the piece: the confirmed session's record, read by wl-preproc's own code --
    its trial lines, runs, session and training records with no problem, the suggestions, the hold
    and the move read as the rig wrote them -- and its strobed stream decoded and assembled into
    one trial per trial line, each ending on its outcome's marker, every error's timeout strobed."""
    try:
        from wl_preproc.contracts import events as their_events
        from wl_preproc.events.assemble import assemble
        from wl_preproc.events.rigrecords import change_fields, read_rig_records
        from wl_preproc.events.rigruns import read_rig_runs
        from wl_preproc.events.rigsession import read_rig_session
        from wl_preproc.events.rigtrials import read_rig_trials
    except ImportError as exc:  # pragma: no cover - exercised by the CI job
        if os.environ.get("WLX_REQUIRE_PREPROC") == "1":
            raise AssertionError(
                f"WLX_REQUIRE_PREPROC=1 but wl-preproc is not importable ({exc})") from exc
        pytest.skip("wl-preproc checkout not beside this repo")
    session, trainer = confirmed
    folder = session.directory.parent
    lines = _rows(session, "trials.jsonl")

    trials = read_rig_trials(folder, "A")
    runs = read_rig_runs(folder, "A")
    rig = read_rig_session(folder, "A")
    records = read_rig_records(folder)
    changes = _rows(session, "parameter_changes.jsonl")
    fields, problems = change_fields([json.dumps(row) for row in changes])

    assert (trials.problems, runs.problems, rig.problems, records.problems,
            problems) == ((), (), (), (), [])
    assert [(t.number, t.block, t.outcome, t.shown) for t in trials.trials] == [
        (line["trial_number"], line["block"], line["outcome"], line["shown"]) for line in lines]
    assert all(t.drawn["odd_color"] == "pool" for t in trials.trials)
    (run,) = runs.runs
    assert (run.plan, run.stop_kind, run.presentations) == ("training", "operator", len(lines))
    assert [(f.kind, f.change) for f in fields] == [(row["kind"], row["change"]) for row in changes]
    assert {"suggested", "declined"} <= {f.kind for f in fields}
    assert [c.kind for c in records.controls].count("next_block") == 1

    events = their_events.decode_stream([(i * 0.001, w) for i, w in enumerate(session.card.codes)])
    assembly = assemble(events)
    assert assembly.errors == []
    assert [t.trial_id for t in assembly.trials] == [line["trial_number"] for line in lines]
    for trial, line in zip(assembly.trials, lines):
        marker = their_events.Marker(session.allocation.outcomes[Outcome(line["outcome"])])
        assert trial.outcome == marker.name.removeprefix("TRIAL_").lower(), line
    codes = [e.code for e in events if isinstance(e, their_events.SimpleEvent)]
    errors = sum(line["outcome"] in ("abort", "wrong_target", "target_break", "fixation_break")
                 for line in lines)
    assert errors > 0 and codes.count(TIMEOUT_ON) == errors


def test_each_line_names_its_colors_and_each_run_defines_the_set_once(task, tmp_path):
    """**The record's weight** (the build's final fixes, 1): written whole, each look's color set
    -- four colors, an apex, a held luminance and a sentence of its source -- rode every trial line
    twice, 1.6 KB of a 3.9 KB line, whose `params` were 2.3 KB. A line names each look's color by
    its set's name and the color's (`"colorset": "isohue"`, `"color": "blue"`), its fraction as the
    line's other values are; the set's definition is in the record once, in the run's start row
    (`color_sets`): as its file reads, and as this rig's calibration drew it -- each color as shown,
    the chroma given up together, each color's output levels, **at each luminance the run's values
    draw it at** (the fix round: `color_luminance` a setting), a list. So each line's whole
    parameter set of a Fade-in session is under 2.75 KB -- under 1 KB before the fix round made
    twelve more of its numbers settings, each a key of every line, and each look's luminance a
    reference to one, 0.15 KB in all; under 1.25 KB before the pop-out's revision added 22
    settings, the bounds, graces, shares and the fixation point's two looks among them, 1.4 KB, the
    looks and their hues 0.86 KB of it, each written as a reference to its settings, never a color
    set -- (the line's other keys, each stimulus's place among them, are as they were), no line
    realizes the set again (`color_realized` null), and the record still reads back: the run's
    stage and pool, as wl-xcon's own resume finds them."""
    from wl_xcon import resume
    from wl_xcon.taskd import went_on

    session = _opened(_spec(tmp_path, seed=5, start_block="Fade-in"), _Stops(40))

    session.run()

    lines = _rows(session, "trials.jsonl")
    assert len(lines) >= 30
    # Each line's `params` as the record writes it: keys sorted, `json`'s separators.
    weights = [len(json.dumps(line["params"], sort_keys=True).encode()) for line in lines]
    assert max(weights) < 2816, sorted(weights)[-3:]
    assert all(line["color_realized"] is None for line in lines)
    by_reference = {"class": "P", "fields": {"name": "distractor_fraction"}}
    brightness = {"class": "P", "fields": {"name": "color_luminance"}}
    for line in lines:
        odd, among = (line["params"][name]["fields"]["color"]
                      for name in ("odd_color", "distractor_color"))
        assert (odd["class"], odd["fields"]["colorset"], odd["fields"]["fraction"]) == (
            "ColorSetLight", "isohue", 1.0)
        assert (among["class"], among["fields"]["colorset"], among["fields"]["fraction"]) == (
            "ColorSetLight", "isohue", by_reference)
        assert odd["fields"]["luminance"] == among["fields"]["luminance"] == brightness
        assert line["params"]["color_luminance"] == 15.0
        # The pool the run starts with: blue among red and red among blue.
        assert {odd["fields"]["color"], among["fields"]["color"]} == {"blue", "red"}

    theirs = photometry.ColorSet.load(STIMULI)
    source = json.dumps(theirs.source)[1:-1]
    written = {path.name: path.read_text() for path in session.directory.iterdir()}
    assert {name: text.count(source) for name, text in written.items() if source in text} == {
        "runs.jsonl": 1}, "the set's definition is in the record once"
    (start,) = [row for row in _rows(session, "runs.jsonl") if row["event"] == "start"]

    def realized(luminance: float) -> dict:
        shown = photometry.realize(theirs, SRGB, luminance)
        return {"luminance_cd_m2": luminance, "desaturation": shown.desaturation,
                "xy": {color: list(xy) for color, xy in shown.xy.items()},
                "xyz": {color: list(xyz) for color, xyz in shown.xyz.items()},
                "drive": {color: list(levels) for color, levels in shown.drive.items()},
                "macaque_row": list(photometry.macaque_row(SRGB))}

    assert start["calibration"] == SRGB.id
    # At each luminance the run's values draw it at: the colors' 15, and since the pop-out's
    # revision the fixation point's 40, its two looks color-set lights, in the order first met.
    assert start["color_sets"] == {"isohue": {
        "name": "isohue", "colors": {color: list(xy) for color, xy in theirs.colors.items()},
        "apex": list(theirs.apex), "luminance_cd_m2": 15.0, "held": "macaque_2deg_LM1",
        "source": theirs.source, "design": theirs.design,
        "realized": [realized(40.0), realized(15.0)],
    }}

    restored = resume.read(session.directory, departure=1_700_000_000.0)
    went = went_on(task, restored.last_run)
    assert (went.stage, went.pool) == ("Fade-in", 66)


def test_the_twelve_pairings_and_the_four_colors_are_equal_in_macaque_luminance(task):
    """§3.2: the task's colors are `stimuli/isohue.json`'s, the numbers this repository's tests
    derived; on the test calibration, through its primaries' own spectra, each of the four colors
    the pool draws -- the odd one's, and a distractor's at full, Crowd's -- realizes at the macaque
    luminance (L + M at L:M 1, CIE 2006 2°) of a D65 light at 15 cd/m², to 0.1%, at its own
    chromaticity, so every one of the twelve pairings is equal in it and differs by color alone."""
    theirs, ours = photometry.ColorSet.load(STIMULI), photometry.ColorSet.load(FIXTURE)
    assert (theirs.colors, theirs.apex, theirs.luminance_cd_m2, theirs.held) == (
        ours.colors, ours.apex, 15.0, "macaque_2deg_LM1")
    assert "02-color/isohue_spectrum" in theirs.source and "isohue_levels.csv" in theirs.source
    panel = measured()
    held = _macaque(panel.weights(xyY(*D65, 15.0)), panel)

    def realized(look) -> tuple:
        light = look.color
        assert isinstance(light, ColorSetLight) and light.colorset == theirs
        X, Y, Z = photometry.colorset_xyz(replace(light, fraction=1.0, luminance=15.0), panel)
        return panel.weights_of((X, Y, Z)), (X / (X + Y + Z), Y / (X + Y + Z))

    seen = set()
    for odd, among in task.pool.choices:
        for look in (odd, among):
            weights, xy = realized(look)
            assert _macaque(weights, panel) == pytest.approx(held, rel=1e-3), look
            assert xy == pytest.approx(theirs.colors[_look(look)[0]], abs=1e-9), look
            seen.add(_look(look)[0])
        assert _look(odd)[0] != _look(among)[0]
    assert seen == set(COLORS)


def _macaque(weights, panel) -> float:
    """The macaque luminance (`cones.macaque_luminance`) of the spectrum the panel shows at these
    primary weights, through its measured spectra."""
    spectra = panel.spectra
    spectrum = tuple(sum(w * v for w, v in zip(weights, at))
                     for at in zip(spectra.red, spectra.green, spectra.blue))
    return cones.macaque_luminance((spectra.nm, spectrum))


class _Kept:
    """A gaze source that keeps each sample it hands over (as `tests/test_simeye.py`'s)."""

    def __init__(self, source, kept: list) -> None:
        self.source, self.kept = source, kept

    def poll(self, at: float):
        sample = self.source.poll(at)
        self.kept.append(sample)
        return sample


class _Arrived:
    """Samples already made, one a poll (as `tests/test_simeye.py`'s)."""

    def __init__(self, samples: list) -> None:
        self.samples, self.polled = samples, 0

    def poll(self, at: float):
        if self.polled >= len(self.samples):
            return None
        self.polled += 1
        return self.samples[self.polled - 1]


class _Stops(Simulated):
    """A person's stop, drained before trial `after`."""

    def __init__(self, after: int) -> None:
        super().__init__()
        self.after, self.drains = after, 0

    def drain(self) -> list:
        self.drains += 1
        if self.drains == self.after:
            self.queue(Stop(by=JAKE))
        return super().drain()


def test_a_simulated_session_runs_end_to_end_through_the_simulated_eye(tmp_path, monkeypatch):
    """§2's "through the rig's own eye rules in simulation": a `wlx run` session of the plan
    started at Fade-in, its world left to the session, plays every trial through the simulated eye,
    and each trial's recorded outcome is what a plain `gaze.Tracked` makes of the samples the eye
    gave it. It answers right, on a distractor and early; Fade-in's staircase moves the
    distractors' luminance; and on every trial that reached the go, the discs came on the frame the
    fixation point took its act look (the pop-out revision's §3, `go_delay` 0), the point staying
    on."""
    played = []
    made = simeye.Eye.world

    def world(eye, trial, values, frame_period):
        seen = made(eye, trial, values, frame_period)
        kept: list = []
        played.append((trial, dict(values), kept))
        seen.source = _Kept(seen.source, kept)
        return seen

    monkeypatch.setattr(simeye.Eye, "world", world)
    session = _opened(_spec(tmp_path, seed=5, start_block="Fade-in"), _Stops(150))

    session.run()

    lines = _rows(session, "trials.jsonl")
    assert session.stop_kind == "operator" and len(lines) >= 140
    assert len(played) == len(lines), "a trial of the session was not played through the eye"
    scored = [
        run_trial(trial, Tracked(Tracker(), simeye.MAPPING, trial, FRAME, values,
                                 source=_Arrived(kept)),
                  FRAME, values=values, effects=Recorded()).outcome.value
        for trial, values, kept in played
    ]
    assert [line["outcome"] for line in lines] == scored
    counted = Counter(scored)
    assert counted["correct"] >= 50 and counted["wrong_target"] >= 5, counted
    assert counted["fixation_break"] >= 1, counted
    assert {line["block"] for line in lines} == {"Fade-in"}
    assert len({line["params"]["distractor_fraction"] for line in lines}) >= 3
    went = [line for line in lines if line["shown"]]
    assert went
    for line in went:
        stimuli = {(entry["name"], entry["kind"]): entry for entry in line["stimuli"]}
        assert stimuli["fix", "update"]["frame"] == stimuli["search", "show"]["frame"], (
            line["stimuli"])
        assert stimuli["fix", "update"]["changed"] == ["looks"]


class _Locks(Simulated):
    """**A trainer who locks a setting** (a person's `set`, the console's lock; TSK-32): `setting`
    at `value`, sent at the first drain, so it holds from the run's second trial; the run stopped
    `AFTER` drains once the rig first suggests moving up, or at `BUDGET` -- or at `stop_at`. Sent at
    drain `send_at` instead, where one is given."""

    AFTER, BUDGET = 3, 240

    def __init__(self, setting: str, value: float, *, stop_at: int | None = None,
                 send_at: int = 1, more: tuple = ()) -> None:
        super().__init__()
        self.setting, self.value, self.stop_at, self.send_at = setting, value, stop_at, send_at
        #: More `(setting, value)` sent at the same drain, before it.
        self.more = more
        self.session: Session | None = None
        self.drains = 0
        self.seen: int | None = None
        self.ran_out = False

    def drain(self) -> list:
        self.drains += 1
        if self.drains == self.send_at:
            for setting, value in self.more:
                self.queue(SetParameter(setting, value, JAKE))
            self.queue(SetParameter(self.setting, self.value, JAKE))
        offered = self.session.suggestion
        if self.seen is None and offered is not None and offered[1] == "up":
            self.seen = self.drains
        if self.drains == self.BUDGET:
            self.ran_out = True
        if (self.drains in (self.BUDGET, self.stop_at)
                or (self.seen is not None and self.drains == self.seen + self.AFTER)):
            self.queue(Stop(by=JAKE))
        return super().drain()


def test_a_trial_locked_at_the_hardest_step_counts_toward_moving_up(tmp_path):
    """The PI, 2026-11-07, on the build's review (I2): "Any trial played at the hardest step
    counts, whoever set it there." The trainer locks `distractor_fraction` at full in Fade-in, its
    staircase's hardest step, from the run's second trial: every trial plays at full and leaves
    the staircase where it was, and each one answered counts toward moving up -- none is eased by
    the lock, the panel's bar counts them, and with 80% of the last 50 right the rig suggests
    moving up to Crowd, every answer of its window at the hardest step."""
    trainer = _Locks("distractor_fraction", 1.0)
    session = _opened(replace(_spec(tmp_path, seed=5, start_block="Fade-in"), accuracy=0.95),
                      trainer)
    trainer.session = session

    session.run()

    assert trainer.seen is not None and not trainer.ran_out, "no suggestion to move up was made"
    lines = _rows(session, "trials.jsonl")
    assert lines[0]["params"]["distractor_fraction"] == 0.1
    assert all(line["params"]["distractor_fraction"] == 1.0 for line in lines[1:])
    assert all("distractor_fraction" in line["live"] for line in lines[1:])
    assert not [line for line in lines if "distractor_fraction" in (line.get("eased") or ())]
    (up, *_) = [row for row in _rows(session, "parameter_changes.jsonl")
                if row["kind"] == "suggested" and row["move"] == "up"]
    assert (up["block"], up["now"], up["at_hardest"]) == ("Fade-in", "Crowd", True)
    assert up["bar"]["of"] == 50 and up["bar"]["correct"] >= 40
    # The panel's count: the frame the suggestion first stood on carries the bar it was made on.
    (first, *_) = [frame for frame in session.link.published
                   if frame.suggestion is not None and frame.suggestion.change == up["change"]]
    assert (first.bars.up_correct, first.bars.up_of, first.bars.up_window) == (
        up["bar"]["correct"], 50, 50)
    assert (first.suggestion.correct, first.suggestion.of) == (up["bar"]["correct"], 50)


@pytest.mark.parametrize("more, value", [((), 0.951), ((("fade_in_step", 0.5),), 0.81)])
def test_a_trial_held_merely_near_the_hardest_step_stays_eased(tmp_path, more, value):
    """The controller's ruling of 2026-11-08 on the re-review, I-1: a held value counts as at the
    hardest step only at the top level or beyond it in the harder direction -- the PI said "at the
    hardest step" -- so one merely nearest it stays eased, "as now": distractors locked at 0.951 of
    full, or at 0.81 with Fade-in's step at 0.5 (levels 0.1, 0.6 and 1.0), are dimmer than the odd
    one, every trial of theirs is eased by the lock and none goes toward moving up, so no move up
    is suggested however right the animal is."""
    trainer = _Locks("distractor_fraction", value, stop_at=80, more=more)
    session = _opened(replace(_spec(tmp_path, seed=5, start_block="Fade-in"), accuracy=0.95),
                      trainer)
    trainer.session = session

    session.run()

    lines = _rows(session, "trials.jsonl")
    assert len(lines) >= 70 and trainer.seen is None
    assert all(line["params"]["distractor_fraction"] == value for line in lines[1:])
    assert all("distractor_fraction" in line["eased"] for line in lines[1:])
    assert not [row for row in _rows(session, "parameter_changes.jsonl")
                if row["kind"] == "suggested" and row["move"] == "up"]
    last = session.link.published[-1]
    assert last.bars is None or last.bars.up_of == 0


@pytest.mark.parametrize(("start", "locked", "stepped_at"), [
    (0.9, 30, {0.9, 1.0}),
    (0.1, 3, {0.1}),
])
def test_went_on_replays_only_answers_at_the_hardest_step_as_at_it(task, tmp_path, start, locked,
                                                                   stepped_at):
    """The build's review, M1 (H10): a run that stops with its process is gone on from by
    replaying its record (`taskd.went_on`), and each line goes toward the stage's bar to move up
    only where it was at the stage's hardest step -- the staircase at its top level, or a value a
    person held there (I2) -- never an answer at an easier level. A Fade-in run started one level
    below full, so its staircase moves to full and back, and the trainer locks the distractors at
    full for its last trials; **and one started faint, locked at full from its third trial while
    its staircase waits at the bottom** (the re-review, M-2: a held line is judged by its value,
    not the staircase's level): each line replays as at the hardest step exactly where its
    distractors were at full."""
    from wl_xcon import resume
    from wl_xcon.taskd import went_on

    spec = replace(_spec(tmp_path, seed=5, start_block="Fade-in"),
                   values={"distractor_fraction": start})

    class _Late(_Locks):
        """The lock sent at drain `locked`, not the first; the run stopped at the 45th."""

        def drain(self) -> list:
            self.drains += 1
            if self.drains == locked:
                self.queue(SetParameter(self.setting, self.value, JAKE))
            if self.drains == 45:
                self.queue(Stop(by=JAKE))
            return Simulated.drain(self)

    late = _Late("distractor_fraction", 1.0)
    session = _opened(spec, late)
    late.session = session

    session.run()

    lines = _rows(session, "trials.jsonl")
    restored = resume.read(session.directory, departure=1_700_000_000.0)
    went = went_on(task, restored.last_run)
    replayed = [event[5] for event in went.bars if event[0] == "trial"]
    at_full = [line["params"]["distractor_fraction"] == 1.0 for line in lines]
    assert replayed == at_full
    assert any(at_full) and not all(at_full)
    held = [line for line in lines if "distractor_fraction" in line["live"]]
    assert held and all(line["params"]["distractor_fraction"] == 1.0 for line in held)
    stepped = [line for line in lines if "distractor_fraction" not in line["live"]]
    assert {line["params"]["distractor_fraction"] for line in stepped} >= stepped_at


@pytest.mark.parametrize(("stage", "setting", "value", "own"), [
    ("Alone", "set_size", 3, 1),
    ("Fade-in", "set_size", 6, 4),
    ("Crowd", "distractor_fraction", 0.5, 1.0),
])
def test_a_trainer_overrides_a_stages_own_value_live(tmp_path, stage, setting, value, own):
    """Each stage's own fixed value -- Alone's one disc, Fade-in's four, Crowd's distractors at full
    -- is a condition's value, and a person's live value wins over it (engine spec §14.7; TSK-32's
    lock, the brief's fix 1): from the trial after the trainer's `set`, every trial of the stage
    plays at the person's value, its line saying a person holds it, and the stage is the same."""
    trainer = _Locks(setting, float(value), stop_at=8)
    session = _opened(_spec(tmp_path, seed=5, start_block=stage), trainer)
    trainer.session = session

    session.run()

    lines = _rows(session, "trials.jsonl")
    assert len(lines) >= 6 and {line["block"] for line in lines} == {stage}
    assert lines[0]["params"][setting] == own and setting not in lines[0]["live"]
    assert all(line["params"][setting] == value and setting in line["live"]
               for line in lines[1:])


# --- Every number a setting (the fix round; the PI, 2026-11-07) ---------------------------------


def test_the_bar_to_move_up_reads_its_window_live(tmp_path):
    """The PI, 2026-11-07: "everything should be adjustable in the console, no?" The trainer sets
    `move_up_window` to 20 before Alone's second trial; the bar reads it at its next judgment and
    restarts nothing (the window rolls): the rig suggests moving up on 80% of the last 20 answers,
    long before 50 are in, the panel's bar a window of 20, and the change is the setting's own
    `set` row."""
    trainer = _Locks("move_up_window", 20.0)
    session = _opened(replace(_spec(tmp_path, seed=5), accuracy=0.95), trainer)
    trainer.session = session

    session.run()

    assert trainer.seen is not None and not trainer.ran_out
    changes = _rows(session, "parameter_changes.jsonl")
    assert [(row["kind"], row["name"], row["now"]) for row in changes][:1] == [
        ("set", "move_up_window", 20.0)]
    (up, *_) = [row for row in changes if row["kind"] == "suggested" and row["move"] == "up"]
    assert (up["block"], up["bar"]["of"]) == ("Alone", 20) and up["bar"]["correct"] >= 16
    lines = _rows(session, "trials.jsonl")
    assert len(lines) < 50 and {line["block"] for line in lines} == {"Alone"}
    (first, *_) = [frame for frame in session.link.published
                   if frame.suggestion is not None and frame.suggestion.change == up["change"]]
    assert (first.bars.up_of, first.bars.up_window, first.bars.up_at) == (20, 20, 0.8)


def test_a_staircase_step_changed_live_re_derives_its_levels(tmp_path):
    """The trainer sets Fade-in's step, `fade_in_step`, from a tenth to 0.3 at its tenth trial:
    from the next trial the staircase's levels are 0.1, 0.4, 0.7 and 1.0, it goes on at the level
    nearest the value it was at, and the panel shows the new levels. The change is the setting's
    own `set` row, nothing else (no new row kind)."""
    trainer = _Locks("fade_in_step", 0.3, send_at=10, stop_at=40)
    session = _opened(replace(_spec(tmp_path, seed=5, start_block="Fade-in"), accuracy=0.95),
                      trainer)
    trainer.session = session

    session.run()

    lines = _rows(session, "trials.jsonl")
    changes = _rows(session, "parameter_changes.jsonl")
    assert [(row["kind"], row["name"], row["now"]) for row in changes
            if row["kind"] not in ("suggested",)] == [("set", "fade_in_step", 0.3)]
    applied = changes[0]["trial_number"]
    before = [line for line in lines if line["trial_number"] < applied]
    after = [line for line in lines if line["trial_number"] >= applied]
    assert before and after
    assert {line["params"]["distractor_fraction"] for line in before} <= {
        0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0}
    assert {line["params"]["distractor_fraction"] for line in after} <= {0.1, 0.4, 0.7, 1.0}
    assert all(line["params"]["fade_in_step"] == 0.3 for line in after)
    # It goes on at the level nearest the value it was at.
    last = before[-1]["params"]["distractor_fraction"]
    first = after[0]["params"]["distractor_fraction"]
    assert abs(first - last) <= 0.15 + 1e-9, (last, first)
    shown = [frame.staircase for frame in session.link.published
             if frame.staircase is not None and frame.trial_index == after[-1]["index"]]
    assert shown and tuple(shown[-1].levels) == (0.1, 0.4, 0.7, 1.0)


def test_the_colors_brightness_changed_live_is_realized_once_and_written_once(tmp_path):
    """The trainer dims the colors from 15 to 12 cd/m² of macaque luminance (`color_luminance`) at
    the run's fifth trial. The run's start row realizes the set at 15 -- and at 40, the fixation
    point's brightness, its two looks color-set lights since the pop-out's revision; the first line
    drawn at 12
    carries the set realized at 12 -- each color's chromaticity as shown, the chroma given up
    together and its output levels -- and no other line does, so a reader knows each trial's drawn
    light from its line's `color_luminance` and the record alone, without the rig: the realization
    at that luminance, times the look's fraction."""
    trainer = _Locks("color_luminance", 12.0, send_at=5, stop_at=14)
    session = _opened(_spec(tmp_path, seed=5, start_block="Fade-in"), trainer)
    trainer.session = session

    session.run()

    lines = _rows(session, "trials.jsonl")
    (start,) = [row for row in _rows(session, "runs.jsonl") if row["event"] == "start"]
    theirs = photometry.ColorSet.load(STIMULI)
    at = {luminance: photometry.realize(theirs, SRGB, luminance) for luminance in (15.0, 12.0)}
    assert sorted(entry["luminance_cd_m2"]
                  for entry in start["color_sets"]["isohue"]["realized"]) == [15.0, 40.0]
    written = [(line["index"], line["color_realized"]) for line in lines
               if line["color_realized"] is not None]
    assert len(written) == 1
    index, realized = written[0]
    assert lines[index]["params"]["color_luminance"] == 12.0
    assert all(line["params"]["color_luminance"] == 15.0 for line in lines[:index])
    assert all(line["params"]["color_luminance"] == 12.0 for line in lines[index:])
    assert realized == {"isohue": [{
        "luminance_cd_m2": 12.0, "desaturation": at[12.0].desaturation,
        "xy": {color: list(xy) for color, xy in at[12.0].xy.items()},
        "xyz": {color: list(xyz) for color, xyz in at[12.0].xyz.items()},
        "drive": {color: list(levels) for color, levels in at[12.0].drive.items()},
        "macaque_row": list(photometry.macaque_row(SRGB))}]}
    # Each line's light, from the record alone: its luminance's realization times its fraction.
    found = {entry["luminance_cd_m2"]: entry
             for entry in [*start["color_sets"]["isohue"]["realized"], *realized["isohue"]]}
    for line in lines:
        assert line["params"]["color_luminance"] in found



class _Sets(Simulated):
    """**A trainer who sets `setting` to each of `values` in turn**, one every `EVERY` drains from
    the first, and stops the run `EVERY` drains after the last."""

    EVERY = 2

    def __init__(self, setting: str, values: tuple) -> None:
        super().__init__()
        self.setting, self.values, self.drains = setting, values, 0

    def drain(self) -> list:
        self.drains += 1
        sent, due = divmod(self.drains - 1, self.EVERY)
        if due == 0 and sent < len(self.values):
            self.queue(SetParameter(self.setting, self.values[sent], JAKE))
        if self.drains == self.EVERY * (len(self.values) + 1):
            self.queue(Stop(by=JAKE))
        return super().drain()


def test_brightening_the_colors_past_what_the_panel_shows_warns_live(tmp_path):
    """The whole-build review of the console settings build, I2 (XC-518): the load judges an open
    `color_luminance` at its start, 15 cd/m², where the sRGB standard shows the set as written; a
    trainer raising it to 28 cd/m² live is told, `color-set-desaturated`, the share of chroma every
    color gives up there, a warning he accepts by making the change (`warnings.jsonl`, `how`
    `set`) and said on the changes feed. Lowering it to 27, the same set still paler than asked,
    and then back to 15, adds nothing new. The value applies: a warning, never a refusal. **Said
    once, naming each structure that draws the colors** (XC-545; until 2026-11-19 once for each of
    the pop-out's five)."""
    trainer = _Sets("color_luminance", (28.0, 27.0, 15.0))
    session = _opened(_spec(tmp_path, seed=5, start_block="Fade-in"), trainer)

    session.run()

    assert session.refusals == []
    every = [row for row in _rows(session, "warnings.jsonl")
             if row["code"] == "color-set-desaturated"]
    structures = ", ".join(map(repr, _load_task(TASK_FILE).structures))
    warned = [row for row in every if row["detail"].startswith(f"in structures {structures}: ")]
    assert warned == every
    assert [(row["how"], row["by"]) for row in warned] == [("set", {"kind": "box",
                                                                    "name": "jake"})]
    assert ("calibration srgb-standard cannot show color set 'isohue' as written at 28 cd/m² of "
            "macaque luminance") in warned[0]["detail"]
    fed = [said for kind, _, _, said in session.controls
           if kind == "warning" and said.startswith("color-set")]
    assert f"color-set-desaturated: {warned[0]['detail']}" in fed
    assert len(fed) == len(every)
    lines = _rows(session, "trials.jsonl")
    assert {line["params"]["color_luminance"] for line in lines} == {15.0, 28.0, 27.0}


def test_raising_the_fixation_points_saturation_live_warns_once(tmp_path):
    """The whole-build review of the pop-out revision, the controller's ruling: **a saturation
    setting is judged at its start at load** -- the fixation point's 0, the set's gray, raises no
    `color-set-desaturated` -- **and at the value set live**: a trainer raising `fix_saturation`
    to the full color (1) at the point's 40 cd/m² is told, once, naming the structures (XC-545),
    the share of chroma the sRGB standard cannot show there; a warning he accepts by making the
    change, said on the changes feed, and the value applies."""
    from wl_xcon.check import check_task as loaded

    task = _load_task(TASK_FILE)
    at_load = loaded(task, _load_allocation(Path(ALLOCATION)), geometry=DIRECT, calibration=SRGB,
                     deployment=Deployment.RIG_FIXED, source=TASK_FILE)
    assert "color-set-desaturated" not in {f.code for f in at_load}

    trainer = _Sets("fix_saturation", (1.0,))
    session = _opened(_spec(tmp_path, seed=5, start_block="Fade-in"), trainer)
    session.run()

    assert session.refusals == []
    every = [row for row in _rows(session, "warnings.jsonl")
             if row["code"] == "color-set-desaturated"]
    assert len(every) == 1, every
    assert every[0]["how"] == "set" and "fix_" in every[0]["detail"], every[0]
    assert every[0]["detail"].startswith("in structures 'search', ")
    fed = [said for kind, _, _, said in session.controls
           if kind == "warning" and said.startswith("color-set-desaturated")]
    assert fed == [f"color-set-desaturated: {every[0]['detail']}"]
    lines = _rows(session, "trials.jsonl")
    assert 1.0 in {line["params"]["fix_saturation"] for line in lines}

def test_a_luminance_new_to_its_run_is_the_lines_color_realized_and_wl_preproc_reads_it(tmp_path):
    """XC-491, wl-preproc's answer of 2026-11-14, accepted with one rename: **the trial line's key
    is `color_realized`** -- "A bare `realized` beside a trial's other fields reads as if the trial
    itself were realized" -- its shape as before: null but on the run's first line drawn at a
    luminance the run has not yet realized, then each set's realization there, by set name, `{set
    name: [entry]}`. No line carries a bare `realized`, and the start row's
    `color_sets[name].realized` keeps its name. Read back by wl-xcon's own resume, each line holds
    it as written; read by wl-preproc's reader as on our local export, the record has no problem but
    XC-461's note (`tests/_preproc.py`), one trial for each line."""
    from wl_xcon import resume

    trainer = _Locks("color_luminance", 12.0, send_at=5, stop_at=14)
    session = _opened(_spec(tmp_path, seed=5, start_block="Fade-in"), trainer)
    trainer.session = session

    session.run()

    lines = _rows(session, "trials.jsonl")
    assert all("color_realized" in line and "realized" not in line for line in lines)
    written = [line["color_realized"] for line in lines if line["color_realized"] is not None]
    assert [list(each) for each in written] == [["isohue"]]
    (entry,) = written[0]["isohue"]
    assert (sorted(entry), entry["luminance_cd_m2"]) == (
        ["desaturation", "drive", "luminance_cd_m2", "macaque_row", "xy", "xyz"], 12.0)
    (start,) = [row for row in _rows(session, "runs.jsonl") if row["event"] == "start"]
    defined = start["color_sets"]["isohue"]
    assert "color_realized" not in defined
    # The colors' 15, and the fixation point's 40 since the pop-out's revision.
    assert sorted(each["luminance_cd_m2"] for each in defined["realized"]) == [15.0, 40.0]
    restored = resume.read(session.directory, departure=1_700_000_000.0)
    assert [line["color_realized"] for line in restored.last_run.lines] == [
        line["color_realized"] for line in lines]

    try:
        from wl_preproc.events.rigrecords import change_fields, read_rig_records
        from wl_preproc.events.rigruns import read_rig_runs
        from wl_preproc.events.rigsession import read_rig_session
        from wl_preproc.events.rigtrials import read_rig_trials
    except ImportError as exc:  # pragma: no cover - exercised by the CI job
        if os.environ.get("WLX_REQUIRE_PREPROC") == "1":
            raise AssertionError(
                f"WLX_REQUIRE_PREPROC=1 but wl-preproc is not importable ({exc})") from exc
        pytest.skip("wl-preproc checkout not beside this repo")
    folder = session.directory.parent
    trials, runs = read_rig_trials(folder, "A"), read_rig_runs(folder, "A")
    rig, records = read_rig_session(folder, "A"), read_rig_records(folder)
    _, problems = change_fields(
        (session.directory / "parameter_changes.jsonl").read_text().splitlines())
    assert (trials.problems, runs.problems, rig.problems, records.problems,
            problems) == ((), (), (), (), [])
    assert [t.number for t in trials.trials] == [line["trial_number"] for line in lines]


def test_the_prompt_names_the_hardest_step_in_plain_words_and_a_pool_stays_whole(tmp_path):
    """The build's review, M7 and M8. **The prompt to move up says the stage's hardest step in the
    trainer's words**, the PI's sketch (§3.5): "the distractors are at full brightness and 41 of
    the last 50 were correct" -- Fade-in's staircase declares its words, which the panel's prompt
    says with the bar's numbers. **And a pool's value stays a whole number after a `set`**: the wire
    carries every number as a float, and the trainer's 67 is applied, recorded and drawn from as
    67, never 67.0."""
    from wl_xcon.web import fragments
    from _frames import view

    trainer = _Locks("distractor_fraction", 1.0)
    session = _opened(replace(_spec(tmp_path / "up", seed=5, start_block="Fade-in"),
                              accuracy=0.95), trainer)
    trainer.session = session
    session.run()
    (shown, *_) = [frame for frame in session.link.published
                   if frame.suggestion is not None and frame.suggestion.move == "up"]
    prompt = fragments(shown, view(can_write=True))["rt-train"]
    assert shown.staircase.hardest == "the distractors are at full brightness"
    assert (f"The distractors are at full brightness and {shown.suggestion.correct} of the last "
            f"50 were correct") in prompt

    widened = _Locks("pairings", 67.0, stop_at=6)
    pooled = _opened(_spec(tmp_path / "pool", seed=5, start_block="Fade-in"), widened)
    widened.session = pooled
    pooled.run()
    lines = _rows(pooled, "trials.jsonl")
    assert [line["params"]["pairings"] for line in lines[1:]] == [67] * (len(lines) - 1)
    assert all(type(line["params"]["pairings"]) is int for line in lines)
    (row,) = [row for row in _rows(pooled, "parameter_changes.jsonl") if row["kind"] == "set"]
    assert row["now"] == 67 and type(row["now"]) is int


class _StopAt(Simulated):
    """**A trainer who only stops the run**, at drain `at`."""

    def __init__(self, at: int) -> None:
        super().__init__()
        self.at, self.drains = at, 0

    def drain(self) -> list:
        self.drains += 1
        if self.drains == self.at:
            self.queue(Stop(by=JAKE))
        return super().drain()


#: **A panel a tenth as bright as the test one** (XC-494): white about 20 cd/m², so it shows the
#: four colors only up to about 18.85 cd/m² of macaque luminance, below what `color_luminance`
#: may be set to (computed 2026-11-08 with `check.reachable_top`).
DIM = measured(**{name: xyY(x, y, Y * 0.1) for name, (x, y, Y) in PRIMARIES.items()},
               id="dim@2027-01-20")


#: **The fixation point brought within `DIM`'s reach for a run**, both looks at 15 cd/m²: given as
#: the run's starting values, never as a copy of the task (the pop-out revision's whole-build
#: review, the controller's ruling on Task 7's concern 3).
WITHIN_DIM = {"fix_luminance": 15.0, "fix_act_luminance": 15.0}


def test_a_panel_too_dim_for_the_colors_range_top_warns_and_starts_at_its_top(tmp_path):
    """XC-494, by the PI's "warnings over refusals" (2026-10-11) and his answer of 2026-11-20 from
    his try-out ("Start at the brightest it can, warn"): on a panel that cannot show the colors at
    all above about 18.9 cd/m², not even the set's apex, **the task loads**, its start, 15, being
    shown -- since the console settings plan's Task 11 `color_luminance`'s lowest is open, so the
    load judges it at its start, and no reachable top is warned of there
    (`color-set-unreachable`), as it was over the old range of 1 to 30 -- **a trainer's live value
    above that top is refused**, the previous value standing, with a sentence naming it, while one
    below it is taken. **The fixation point's looks**, color-set lights at 40 cd/m² since the
    pop-out's revision, which this panel cannot show either (`check._reachable_starts`), load with
    `color-set-unreachable` naming the point's brightness and the top, and **the pop-out as written
    now starts** (until 2026-11-20 its run was refused): its point at the panel's reachable top,
    18.85 cd/m², with a warning naming each setting, the value asked, the value used and why
    (`check.in_reach`, `start-at-reachable-top`); the run's record shows the value used as its
    start. A run given the colors at 25, above their top, starts them at it too."""
    from wl_xcon.check import START_AT_REACHABLE_TOP, in_reach
    from wl_xcon.preflight import PASS, values as starting_values

    task = _load_task(TASK_FILE)
    found = check_task(task, _load_allocation(Path(ALLOCATION)),
                       geometry=DIRECT, calibration=DIM, deployment=Deployment.RIG_FIXED,
                       source=TASK_FILE)
    assert not [f for f in found if f.blocking], [f.detail for f in found if f.blocking]
    unreached = [f.detail for f in found if f.code == "color-set-unreachable"]
    assert len(unreached) == 2 and all("40 cd/m²" in said and "about 18.9 cd/m²" in said
                                       for said in unreached), unreached
    assert all("a run starting above that starts at it, with a warning" in said
               for said in unreached), unreached
    assert {said.split("setting ")[1].split(",")[0] for said in unreached} == {
        "'fix_luminance'", "'fix_act_luminance'"}
    assert not [said for said in unreached if "'color_luminance'" in said]
    assert "color-set-desaturated" in {f.code for f in found}, "at 15, as written it is not shown"

    starts = {param.name: param.start for param in task.params if param.start is not None}
    used, warned, refused = in_reach(task, starts, DIM)
    assert used == {"fix_luminance": 18.85, "fix_act_luminance": 18.85} and refused == [], used
    assert [(f.code, f.blocking, f.accepted_in) for f in warned] == [
        (START_AT_REACHABLE_TOP, False, SESSION_KINDS)] * 2
    for finding, setting in zip(warned, ("fix_luminance", "fix_act_luminance")):
        assert finding.detail.startswith(
            f"setting {setting!r} starts at 18.85 cd/m², not the 40 cd/m² asked: calibration "
            f"dim@2027-01-20 cannot show color set 'isohue' at 40 cd/m²"), finding.detail
        assert "the brightest it can show it at, its reachable top" in finding.detail
    point = starting_values(task, {}, (), "training", calibration=DIM)
    assert point.result == PASS, point.said

    as_written = _opened(replace(_spec(tmp_path / "written", seed=5, start_block="Fade-in"),
                                 calibration=DIM), _StopAt(4))
    as_written.run()
    lines = _rows(as_written, "trials.jsonl")
    assert lines and all(line["params"]["fix_luminance"] == 18.85
                         and line["params"]["fix_act_luminance"] == 18.85 for line in lines)
    (start,) = [row for row in _rows(as_written, "runs.jsonl") if row["event"] == "start"]
    assert start["resolved"]["fix_luminance"] == start["resolved"]["fix_act_luminance"] == 18.85
    assert start["layers"]["run"]["fix_luminance"] == 18.85
    assert start["layers"]["task"]["fix_luminance"] == 40.0, "the task's own start, as declared"

    refused = _Locks("color_luminance", 25.0, stop_at=5)
    session = _opened(replace(_spec(tmp_path / "live", seed=5, start_block="Fade-in"),
                              calibration=DIM, values=dict(WITHIN_DIM)), refused)
    refused.session = session
    session.run()
    assert session.refusals == [("color_luminance", JAKE, (
        "'color_luminance' at 25 is refused, and the previous value stands: calibration "
        "dim@2027-01-20 cannot show color set 'isohue' at 25 cd/m² of macaque luminance, not even "
        "its apex: this panel shows it up to about 18.9 cd/m² of macaque luminance, its reachable "
        "top"))]
    assert {line["params"]["color_luminance"] for line in _rows(session, "trials.jsonl")} == {15.0}

    taken = _Locks("color_luminance", 18.0, stop_at=5)
    within = _opened(replace(_spec(tmp_path / "within", seed=5, start_block="Fade-in"),
                             calibration=DIM, values=dict(WITHIN_DIM)), taken)
    taken.session = within
    within.run()
    assert within.refusals == []
    assert [line["params"]["color_luminance"] for line in _rows(within, "trials.jsonl")][1:] == (
        [18.0] * (len(_rows(within, "trials.jsonl")) - 1))

    bright = {**WITHIN_DIM, "color_luminance": 25.0}
    item = starting_values(task, bright, (), "training", calibration=DIM)
    assert item.result == PASS, item.said
    assert in_reach(task, {**starts, **bright}, DIM)[0] == {"color_luminance": 18.85}
    started = _opened(replace(_spec(tmp_path / "start", seed=5, start_block="Fade-in"),
                              calibration=DIM, values=dict(bright)),
                      _StopAt(4))
    started.run()
    assert {line["params"]["color_luminance"] for line in _rows(started, "trials.jsonl")} == {
        18.85}


#: A panel a twenty-fifth as bright as `DIM`: the four colors' reachable top on it, about 0.75
#: cd/m², is below `color_luminance`'s start, 15 (computed 2026-11-19 with `check.reachable_top`).
DARK = measured(**{name: xyY(x, y, Y * 0.004) for name, (x, y, Y) in PRIMARIES.items()},
                id="dark@2027-01-20")
#: A panel a two-hundredth as bright as `DARK`: it cannot show the set's apex even at 0.05 cd/m²,
#: the least a luminance setting is read from (`check.DESATURATED_STEP`).
BLACK = measured(**{name: xyY(x, y, Y * 0.00002) for name, (x, y, Y) in PRIMARIES.items()},
                 id="black@2027-01-20")


class _StopsTheRun(Simulated):
    """**The page's link to `wlx taskd`**, its trainer stopping the service's run at its `at`-th
    drain while one runs."""

    def __init__(self, at: int) -> None:
        super().__init__()
        self.at, self.running, self.service = at, 0, None

    def drain(self) -> list:
        session = None if self.service is None else self.service.session
        if session is not None and session.phase == "running":
            self.running += 1
            if self.running == self.at:
                self.queue(Stop(by=JAKE))
        return super().drain()


def test_the_page_starts_the_popout_on_a_too_dim_panel_its_point_at_the_top(tmp_path):
    """The PI's answer of 2026-11-20 ("Start at the brightest it can, warn"), **on the path the
    page's Start takes** (`wlx taskd`'s service: `CheckRun`, then `StartRun` with the items
    acknowledged by name, as the page's start form sends them; `Service._start` welfare-listed and
    unchanged): on `DIM`, the pop-out as written, the fixation point at 40 cd/m², checks with its
    starting values passing and its warnings item asking, among them one for each of the point's
    brightnesses, `start-at-reachable-top`, naming the setting, the 40 asked and the 18.85 used;
    the start runs, each trial at 18.85, and the warning is written as accepted at the start, by
    whom. Until 2026-11-20 Start was refused, and the page could not set the point's starting
    brightness."""
    import shutil

    from _rig import PATH as RIG_FILE, RIG
    from _sessions import typed
    from wl_xcon.check import START_AT_REACHABLE_TOP
    from wl_xcon.link import CheckRun, OpenSession, StartRun
    from wl_xcon.preflight import PASS, STARTING_VALUES, UNKNOWN, WARNINGS
    from wl_xcon.service import Service

    subjects, root = tmp_path / "subjects", tmp_path / "sessions"
    (subjects / "REFERENCE").mkdir(parents=True)
    shutil.copy("tasks/eight_hour_bounds.py", subjects / "REFERENCE" / "bounds.py")
    shutil.copy("tasks/reference_subject.py", subjects / "REFERENCE" / "settings.py")
    root.mkdir()
    link = _StopsTheRun(4)
    service = Service(rig=RIG, rig_path=RIG_FILE, subjects=subjects, tasks=TASK_FILE.parent,
                      allocation=_load_allocation(Path(ALLOCATION)), allocation_path=ALLOCATION,
                      root=root, link=link, seed=lambda: 5)
    link.service = service
    service.calibration = DIM  # the rig's panel, as its calibration record would load it

    def step(command):
        link.queue(command)
        service.step()
        return link.published[-1]

    step(OpenSession(
        by=JAKE, session_id="2027-01-14_01", animal="REFERENCE", deployment="rig_fixed",
        view="direct", session_kind="training", departure=typed(60), delivered_today=0.0,
        answer=None, amend_to=None, amend_reason="",
        accepted=tuple(entry.key for entry in service.open_warnings(Deployment.RIG_FIXED))))
    assert service.session is not None and service.session.spec.calibration == DIM
    run = dict(task=TASK_FILE.name, values={}, plan="training", start_block="Fade-in")
    checked = step(CheckRun(by=JAKE, **run)).preflight
    items = {item.name: item for item in checked.items}
    assert items[STARTING_VALUES].result == PASS, items[STARTING_VALUES].said
    assert items[WARNINGS].result == UNKNOWN and START_AT_REACHABLE_TOP in items[WARNINGS].said
    for setting in ("fix_luminance", "fix_act_luminance"):
        assert (f"setting {setting!r} starts at 18.85 cd/m², not the 40 cd/m² asked"
                in items[WARNINGS].said), items[WARNINGS].said
    unknown = tuple(item.name for item in checked.items if item.result == UNKNOWN)
    step(StartRun(by=JAKE, trials=1, acknowledged=unknown, **run))

    folder = root / "2027-01-14_01" / "xcon"
    lines = [json.loads(line) for line in (folder / "trials.jsonl").read_text().splitlines()]
    assert lines and {(line["params"]["fix_luminance"], line["params"]["fix_act_luminance"])
                      for line in lines} == {(18.85, 18.85)}
    accepted = [json.loads(line) for line in (folder / "warnings.jsonl").read_text().splitlines()]
    started = [row for row in accepted if row["code"] == START_AT_REACHABLE_TOP]
    assert [(row["how"], row["by"]["name"]) for row in started] == [("start", "jake")] * 2, started


def test_wlx_run_starts_the_popout_on_a_too_dim_panel_its_point_at_the_top(tmp_path, capsys):
    """The PI's answer of 2026-11-20, by `wlx run`: on a rig whose calibration record is `DIM`'s,
    the pop-out as written starts (until 2026-11-20 it was refused before the session opened), its
    point at 18.85 cd/m², the warning for each of its brightnesses printed as accepted by
    `--accept-warnings` and written as accepted; each trial is drawn at 18.85."""
    import time

    from _calibrations import BACKGROUND, LINEAR, OBSERVER, SPECTRA
    from _rig import naming
    from wl_xcon.check import START_AT_REACHABLE_TOP
    from wl_xcon.cli import main

    folder = tmp_path / "rig"
    folder.mkdir()
    (folder / "cal.json").write_text(json.dumps({
        "id": DIM.id, "measured_on": DIM.measured_on, "observer": OBSERVER,
        "primaries": {name: [x, y, Y * 0.1] for name, (x, y, Y) in PRIMARIES.items()},
        "background": BACKGROUND,
        "transfer": {c: [list(p) for p in zip(LINEAR.levels, LINEAR.fractions)]
                     for c in ("red", "green", "blue")},
        "spectra": {name: list(getattr(SPECTRA, name)) for name in ("nm", "red", "green", "blue")},
    }))
    rig = naming(folder, str(folder / "cal.json"))
    root = tmp_path / "root"
    main(["run", str(TASK_FILE), "--rig", str(rig), "--view", "direct", "--kind", "training",
          "--accept-warnings", "--allocation", ALLOCATION, "--bounds",
          "tasks/reference_bounds.py", "--root", str(root), "--session-id", "2027-01-14_01",
          "--subject", "REFERENCE", "--out-of-cage-at", time.strftime("%H:%M"),
          "--delivered-today", "0", "--trials", "2"])
    printed = capsys.readouterr().out
    for setting in ("fix_luminance", "fix_act_luminance"):
        assert (f"warning accepted: {START_AT_REACHABLE_TOP}: setting {setting!r} starts at 18.85 "
                f"cd/m², not the 40 cd/m² asked") in printed, printed
    folder = root / "2027-01-14_01" / "xcon"
    lines = [json.loads(line) for line in (folder / "trials.jsonl").read_text().splitlines()]
    assert len(lines) == 2 and {line["params"]["fix_luminance"] for line in lines} == {18.85}
    accepted = [json.loads(line)["code"]
                for line in (folder / "warnings.jsonl").read_text().splitlines()]
    assert accepted.count(START_AT_REACHABLE_TOP) == 2, accepted


def test_a_panel_that_cannot_show_the_colors_at_their_start_warns_and_starts_at_its_top(tmp_path):
    """XC-494's rule at a start (the pop-out revision's whole-build review, the controller's ruling
    on Task 7's concern 3, `check._reachable_starts`; the PI, 2026-11-20, "Start at the brightest it
    can, warn"): where a panel cannot show the four colors at `color_luminance`'s start, 15 cd/m²,
    not even the set's apex, but can at a lower value the setting allows, **the task loads with
    `color-set-unreachable`**, naming the start and the panel's reachable top, about 0.75 cd/m²,
    and is checked there; **a run starting at the start starts at that top**, with a warning
    (`start-at-reachable-top`), by the pre-flight's values and `Session.run` alike. Until 2026-11-19
    the task was refused at load (`unrealizable-color`), and until 2026-11-20 its run at Start."""
    from wl_xcon.check import in_reach
    from wl_xcon.preflight import PASS, values as starting_values

    task = _load_task(TASK_FILE)
    found = check_task(task, _load_allocation(Path(ALLOCATION)), geometry=DIRECT,
                       calibration=DARK, deployment=Deployment.RIG_FIXED, source=TASK_FILE)
    assert not [f for f in found if f.blocking], [f.detail for f in found if f.blocking]
    (colors,) = [f.detail for f in found if f.code == "color-set-unreachable"
                 and "'color_luminance'" in f.detail]
    assert "15 cd/m²" in colors and "about 0.75 cd/m²" in colors, colors

    starts = {param.name: param.start for param in task.params if param.start is not None}
    used, warned, refused = in_reach(task, starts, DARK)
    assert refused == [] and used["color_luminance"] == pytest.approx(0.75, abs=0.05), used
    (said,) = [f.detail for f in warned if "'color_luminance'" in f.detail]
    assert f"starts at {used['color_luminance']:g} cd/m², not the 15 cd/m² asked" in said, said
    item = starting_values(task, {}, (), "training", calibration=DARK)
    assert item.result == PASS, item.said
    started = _opened(replace(_spec(tmp_path, seed=5, start_block="Fade-in"), calibration=DARK),
                      _StopAt(4))
    started.run()
    assert {line["params"]["color_luminance"] for line in _rows(started, "trials.jsonl")} == {
        used["color_luminance"]}


def test_a_panel_that_cannot_show_the_colors_at_any_value_their_setting_allows_refuses_the_task(
        tmp_path):
    """XC-494's other side: where a panel cannot show the four colors at any luminance their
    setting allows, not even the set's apex at 0.05 cd/m², no trial could be drawn, so **the task
    is refused at load**, as a fixed luminance it cannot show is (`unrealizable-color`): every color
    the task can draw, at the start -- since the console settings plan's Task 11 its lowest is
    open, so the load judges it there -- the lights handed on as given (`check._within_reach`; CI's
    sweep of run 42496196528, where it survived neutering, nothing else refusing them). **And a
    run is refused** (the PI's answer of 2026-11-20 starts a run at the panel's reachable top only
    where one exists): its starting values no value the settings allow brings within reach
    (`check.in_reach`), the pre-flight's starting values item failing on each, and `Session.run`
    refusing the task."""
    from wl_xcon.check import in_reach
    from wl_xcon.preflight import FAIL, values as starting_values

    found = check_task(_load_task(TASK_FILE), _load_allocation(Path(ALLOCATION)), geometry=DIRECT,
                       calibration=BLACK, deployment=Deployment.RIG_FIXED, source=TASK_FILE)
    # The color set's own, the fixation point's lights at their 40 cd/m² among them since the
    # pop-out's revision made its looks color-set lights.
    unshown = [f for f in found if f.code == "unrealizable-color" and "'isohue'" in f.detail]

    assert unshown and all(f.blocking for f in unshown)
    assert "color-set-unreachable" not in {f.code for f in found}
    for color in ("blue", "purple", "red", "green"):
        for end in ("luminance=15.0",):
            assert any(f"'isohue', '{color}'" in f.detail and end in f.detail for f in unshown), (
                color, end)

    task = _load_task(TASK_FILE)
    starts = {param.name: param.start for param in task.params if param.start is not None}
    used, warned, refused = in_reach(task, starts, BLACK)
    assert (used, warned) == ({}, [])
    assert {name for name, _ in refused} == {"color_luminance", "fix_luminance",
                                             "fix_act_luminance"}, refused
    assert all("so no trial could be drawn" in said for _, said in refused), refused
    item = starting_values(task, {}, (), "training", calibration=BLACK)
    assert item.result == FAIL and "'color_luminance': calibration black@2027-01-20" in item.said
    session = _opened(replace(_spec(tmp_path, seed=5, start_block="Fade-in"), calibration=BLACK),
                      _StopAt(4))
    with pytest.raises(SystemExit, match="(?s)task refused, session not started:.*unrealizable-color"):
        session.run()
    assert _rows(session, "trials.jsonl") == []

# --- The console settings plan's Task 11: its sections, its limits, its window as a ratio ----------

#: **The companion design's sections** (`docs/superpowers/specs/2026-11-16-popout-revision-design.md`
#: §5, the console settings plan's Task 11, the training ones split): each setting's section as
#: `task.section_of` gives it, the six times by their unit, so naming none.
SECTIONS = {
    **dict.fromkeys(("inter_trial", "fix_acquisition", "fix_hold", "go_delay",
                     "response_deadline", "target_hold", "timeout", "blink_grace",
                     "tracker_lost_grace"), "Timing"),
    # The bounds on the engine's own waits, settings since the pop-out's revision (its §3).
    **dict.fromkeys(("fix_hold_limit", "landing_limit", "target_hold_limit", "catch_hold_limit"),
                    "Timing/bounds"),
    # Its special trials (the revision's §4 and §5), right after Timing.
    **dict.fromkeys(("target_absent_percent", "odd_place_empty_percent",
                     "distractor_alone_percent", "odd_one_alone_percent", "catch_hold"),
                    "Special trials"),
    **dict.fromkeys(("fix_window", "object_window"), "Gaze windows"),
    # The fixation point's two looks (the revision's §2).
    **dict.fromkeys(("fix_look", "fix_act_look", "fix_size", "fix_act_size", "fix_hole",
                     "fix_act_hole", "fix_color", "fix_act_color", "fix_saturation",
                     "fix_act_saturation", "fix_luminance", "fix_act_luminance"),
                    "Stimuli/fixation point"),
    **dict.fromkeys(("disc_size", "ring_radius", "set_size", "array_rotation"), "Stimuli/array"),
    # The pairings with the colors they pair (the console interface rework's Task 9).
    **dict.fromkeys(("odd_color", "distractor_color", "color_luminance", "distractor_fraction",
                     "pairings"), "Colors"),
    **dict.fromkeys(("move_up_bar", "move_up_window", "move_back_bar", "move_back_window"),
                    "Training/bars"),
    **dict.fromkeys(("staircase_down", "staircase_up", "fade_in_step", "crowd_step",
                     "fade_in_floor", "crowd_floor"), "Training/staircases"),
    "suggestion_margin": "Training/suggestions",
}


def test_the_popout_declares_the_companion_designs_sections(task):
    """§7 of the console settings design ("The task file names it") and the companion design's §5:
    Timing, its bounds a subsection since the pop-out's revision; Special trials; Gaze windows;
    Stimuli, as fixation point and array; Colors, the pairings among them since the console
    interface rework's Task 9; and the Training tab's bars, staircases and suggestions. **Every
    setting has its section**, none falling to Other; the times name none and go to Timing by
    their unit; the training ones sit under `TRAINING_SECTION`, which the Training tab gathers
    (Task 10)."""
    from wl_xcon.task import OTHER, TRAINING_SECTION, section_of

    assert {param.name: section_of(param) for param in task.params} == SECTIONS
    assert OTHER not in {section_of(param) for param in task.params}
    times = {name for name, section in SECTIONS.items() if section == "Timing"}
    assert list(dict.fromkeys(SECTIONS.values()))[:4] == [
        "Timing", "Timing/bounds", "Special trials", "Gaze windows"]
    assert {param.name: (param.unit, param.section) for param in task.params
            if param.name in times} == dict.fromkeys(times, ("s", ""))
    assert {param.name for param in task.params
            if param.section.split("/")[0] == TRAINING_SECTION} == {
        name for name, section in SECTIONS.items() if section.startswith("Training/")}


#: **Each limit the pop-out keeps** (the console settings design's §4; the PI, 2026-11-16, "Hard
#: limits only where impossible"): (lowest, highest), `None` for an open side. A time, a distance,
#: a hole, a margin and a share below 0, a count below 1, a fraction above 1 and a share above 100
#: cannot be; a size's lowest stays open (the controller's ruling: a size of 0 is refused at the
#: value), and so does a color-set light's luminance -- the colors', and the fixation point's since
#: the pop-out's revision -- which at 0 gives a color no chromaticity, refused at the value too; each
#: keeps COL-29's highest. **The training
#: plan's settings keep both ends** (`PLANNED_WHY`): this engine's load checks refuse a staircase's
#: or a bar's setting with an open side (`bad-staircase`, `bad-plan`), as `unbounded-set-size`
#: refuses a set size with no highest, so each side no standard reason covers keeps its number.
BOUNDS = {
    **dict.fromkeys(("inter_trial", "fix_acquisition", "fix_hold", "response_deadline",
                     "target_hold", "timeout", "go_delay", "blink_grace", "tracker_lost_grace",
                     "fix_hold_limit", "landing_limit", "target_hold_limit", "catch_hold_limit",
                     "catch_hold"), (0.0, None)),
    **dict.fromkeys(("fix_window", "disc_size", "fix_size", "fix_act_size"), (None, None)),
    **dict.fromkeys(("fix_hole", "fix_act_hole"), (0.0, None)),
    **dict.fromkeys(("fix_saturation", "fix_act_saturation"), (0.0, 1.0)),
    **dict.fromkeys(("target_absent_percent", "odd_place_empty_percent",
                     "distractor_alone_percent", "odd_one_alone_percent"), (0, 100)),
    "object_window": (0.0, None),
    "ring_radius": (0.0, None),
    # A color-set light since the pop-out's revision, whose lowest is open as the colors' is.
    **dict.fromkeys(("fix_luminance", "fix_act_luminance"), (None, 80.0)),
    "color_luminance": (None, 80.0),
    "set_size": (1, 36),
    "array_rotation": (0.0, 360.0),
    "distractor_fraction": (0.0, 1.0),
    "pairings": (1, None),
    "move_up_bar": (0.5, 1.0),
    "move_back_bar": (0.05, 1.0),
    **dict.fromkeys(("move_up_window", "move_back_window"), (1, 200)),
    "suggestion_margin": (0, 20),
    **dict.fromkeys(("staircase_down", "staircase_up"), (1, 10)),
    "fade_in_step": (0.05, 1.0),
    "crowd_step": (1, 8),
    "fade_in_floor": (0.0, 1.0),
    "crowd_floor": (1, 11),
}
#: Why the training plan's settings keep both ends, as the task file says it.
PLANNED_WHY = ("the training plan's load checks read its whole range, so it keeps both ends; "
               "the builder's")
#: The settings that say it.
PLANNED = ("move_up_bar", "move_up_window", "move_back_bar", "move_back_window",
           "suggestion_margin", "staircase_down", "staircase_up", "fade_in_step", "crowd_step",
           "crowd_floor")


def test_the_popouts_bounds_are_impossible_ones_with_reasons(task):
    """The console settings plan's Task 11: **each bound stands only where a value cannot be, or
    where this engine's checks need one**, every one with its reason (`task.limit_reason`), so the
    load warns of none (`unexplained-limit`): the standard ones need no line; the ring's direction
    is written from 0 to 360 (the PI, 2026-10-30); the fixation point's and the colors' 80 cd/m²
    are COL-29's; a set size keeps its highest, since a run builds every disc before its first
    frame (`unbounded-set-size` refuses one without); the training plan's settings keep both ends
    (`PLANNED_WHY`), and one with an open side is refused at load; and the pool, with no highest of
    its own, refuses a value past its twelve pairings itself (`check.unpooled`). **An open lowest
    is no hole**: a disc of 0°, or colors at 0 cd/m², is refused where it is set
    (`check.laid_out`)."""
    from wl_xcon.check import UNEXPLAINED_LIMIT, unpooled
    from wl_xcon.task import BELOW_ONE, BELOW_ZERO, FRACTION_TOP, limit_reason

    numbers = {param.name: param for param in task.params if not param.choices}
    assert {name: (param.low, param.high) for name, param in numbers.items()} == BOUNDS
    for name, param in numbers.items():
        for side, bound in (("low", param.low), ("high", param.high)):
            assert (limit_reason(param, side) is None) == (bound is None), (name, side)
    whys = {name: param.why for name, param in numbers.items() if param.why}
    assert whys == {
        "array_rotation": "a direction, written from 0 to 360 (the PI, 2026-10-30)",
        **dict.fromkeys(("fix_luminance", "fix_act_luminance", "color_luminance"),
                        "white on the default calibration, the published sRGB 80 cd/m² (COL-29)"),
        **dict.fromkeys(("target_absent_percent", "odd_place_empty_percent",
                         "distractor_alone_percent", "odd_one_alone_percent"),
                        "a share of trials is at most 100"),
        "set_size": "a run builds every disc before its first frame, so a set size needs a "
                    "highest: 36, the PI's (2026-11-19)",
        **dict.fromkeys(PLANNED, PLANNED_WHY),
    }
    assert limit_reason(numbers["ring_radius"], "low") == BELOW_ZERO
    assert limit_reason(numbers["pairings"], "low") == BELOW_ONE
    assert limit_reason(numbers["distractor_fraction"], "high") == FRACTION_TOP
    assert UNEXPLAINED_LIMIT not in {
        f.code for f in check_task(task, _load_allocation(Path(ALLOCATION)), geometry=DIRECT,
                                   calibration=measured(), deployment=Deployment.RIG_FIXED,
                                   source=TASK_FILE)}
    from wl_xcon.check import laid_out

    allocation = _load_allocation(Path(ALLOCATION))
    for name in ("disc_size", "color_luminance"):
        assert [f for f in laid_out(task, {name: 0.0}, allocation=allocation, geometry=DIRECT,
                                    calibration=measured(), deployment=Deployment.RIG_FIXED)
                if f.blocking], name
    ((_, past),) = unpooled(task, {"pairings": 4096})
    assert "it holds a pairing beyond the 12 the pool declares" in past
    assert unpooled(task, {"pairings": 4095}) == []
    for name, code in (("staircase_down", "bad-staircase"), ("move_up_window", "bad-plan")):
        opened = replace(task, structures={"search": replace(task.trial, params=[
            replace(param, high=None) if param.name == name else param
            for param in task.trial.params])})
        assert code in {f.code for f in check_task(opened, _load_allocation(Path(ALLOCATION)),
                                                   geometry=DIRECT, calibration=measured(),
                                                   deployment=Deployment.RIG_FIXED)
                        if f.blocking}, name


def test_the_popouts_object_window_is_three_times_a_discs_radius(task):
    """§5 of the console settings design ("Grows in proportion"): **the discs' windows are a
    multiple of each disc's own radius**, `object_window` 3.0 to start -- the 1.5° window about a
    1° disc it was, as before -- the window following its disc: a 2° disc gets a 3° window, and a
    window set below its disc's radius is warned (`window-inside-object`). The setting's lowest is
    0, a multiple below 0 cannot be."""
    from wl_xcon.check import laid_out

    (objects,) = [window for window in task.trial.windows if isinstance(window, ObjectWindows)]
    assert (objects.of, objects.radius, objects.scale) == ("search", None, P("object_window"))
    (param,) = [param for param in task.params if param.name == "object_window"]
    assert (param.unit, param.low, param.high, param.start, param.section) == (
        "× disc radius", 0.0, None, 3.0, "Gaze windows")
    ring = [action.stimulus for _, action in actions_of(task.trial) if isinstance(action, Show)
            and action.stimulus.name == "search"][0].looks
    for size, radius in ((1.0, 1.5), (2.0, 3.0)):
        values = {**_values(task, set_size=12), "disc_size": size}
        windows = objects.expand(ring, values)
        assert {round(w.radius, 12) for w in windows if w.name.split(".")[1].isdigit()} == {
            radius}, size
    inside = laid_out(task, {"object_window": 0.8}, allocation=_load_allocation(Path(ALLOCATION)),
                      geometry=DIRECT, calibration=measured(), deployment=Deployment.RIG_FIXED)
    assert "window-inside-object" in {f.code for f in inside}


def test_the_popout_loads_with_no_layout_warning_at_its_starts(task):
    """The console settings plan's Task 11 (the controller's ruling 5): with its caps gone and its
    open sides judged at their starts, **the pop-out loads with no layout warning** (`check.LAYOUT`)
    on either calibration but the set size's top -- read at the PI's 36 (2026-11-19), whose 1.5°
    windows crowd on the 8° ring -- and none at its starts set (`check.laid_out`; twelve 1° discs
    on the 8° ring, 4.13° apart, their windows and the 2° fixation window clear of each other),
    nor any limit without its reason. **And the fixation point's saturation judged at its start**
    (the pop-out revision's whole-build review, the controller's ruling): at 0 the point is the
    set's gray, which every panel shows, so no `color-set-desaturated` at load on either
    calibration; raised live it is warned of
    (`test_raising_the_fixation_points_saturation_live_warns_once`)."""
    from wl_xcon.check import LAYOUT, UNEXPLAINED_LIMIT, laid_out

    allocation = _load_allocation(Path(ALLOCATION))
    starts = {param.name: param.start for param in task.params if param.start is not None}
    for calibration in (SRGB, measured()):
        found = check_task(task, allocation, geometry=DIRECT, calibration=calibration,
                           deployment=Deployment.RIG_FIXED, source=TASK_FILE)
        said = [f.detail for f in found if f.code in {*LAYOUT, UNEXPLAINED_LIMIT}]
        # Only the set size's top (a closed range is read at its ends): the PI's 36, 2026-11-19.
        assert len(said) == 1 and "36 objects ('set_size')" in said[0], said
        at_starts = laid_out(task, {**starts, "set_size": 12}, allocation=allocation,
                             geometry=DIRECT, calibration=calibration,
                             deployment=Deployment.RIG_FIXED)
        assert [f.detail for f in at_starts if f.code in LAYOUT] == []



# --- A gaze window of no size (the whole-build review's I1) -------------------------------------


#: A gaze window's radius, or the object windows' ratio, that cannot be: 0, and below.
NO_SIZE = [("fix_window", 0.0), ("fix_window", -1.0), ("object_window", 0.0)]


@pytest.mark.parametrize(("setting", "value"), NO_SIZE)
def test_a_window_of_no_size_is_refused_live_with_nothing_staged(tmp_path, setting, value):
    """The whole-build review of the console settings build, I1; the design's §4, "a size below
    zero" is what cannot be, and 0 too: **a gaze window's radius, or an object window's ratio, at
    or below 0 is refused where a trainer sets it** (`bad-window-radius`, a structure check that
    `check.laid_out`'s new-refusal rule refuses), its sentence naming the setting and the value,
    the previous value standing and nothing staged. The pop-out leaves both windows' lowest open,
    so no range refuses either; on main their floor was 0.5°, and a trainer's 0 or -2 for 2 was
    taken silently, every trial after it no fixation."""
    trainer = _Locks(setting, value, stop_at=4)
    session = _opened(_spec(tmp_path, seed=5), trainer)
    trainer.session = session

    session.run()

    ((name, by, why),) = session.refusals
    assert (name, by) == (setting, JAKE)
    assert why.startswith(f"{setting!r} at {value:g} is refused, and the previous value stands: "
                          f"the layout it leaves refuses it: bad-window-radius: "), why
    assert f"{setting!r}" in why.partition("bad-window-radius: ")[2]
    start = {param.name: param.start for param in session._task.params}[setting]
    assert session.spec.values[setting] == start and setting not in session._edited
    assert not [row for row in _rows(session, "parameter_changes.jsonl")
                if row.get("name") == setting]
    lines = _rows(session, "trials.jsonl")
    assert len(lines) >= 2 and all(line["params"][setting] == start for line in lines)


@pytest.mark.parametrize(("setting", "value"), NO_SIZE)
def test_a_window_of_no_size_is_refused_in_the_preflight(task, setting, value):
    """I1, at a run's start: the pre-flight judges the layout at the run's values
    (`preflight.laid_out`), and a window of no size is a blocking finding there, failing the
    starting values item; at the pop-out's own starts, none."""
    from wl_xcon import preflight

    allocation = _load_allocation(Path(ALLOCATION))
    found = preflight.laid_out(task, {setting: value}, "training", allocation, DIRECT, SRGB,
                               Deployment.RIG_FIXED)
    refused = [f for f in found if f.blocking]

    assert {f.code for f in refused} == {"bad-window-radius"}, [f.detail for f in found]
    assert all(f"{setting!r}" in f.detail for f in refused)
    item = preflight.values(task, {setting: value}, refused, plan="training", calibration=SRGB)
    assert item.result == "fail" and "bad-window-radius: " in item.said
    assert not [f for f in preflight.laid_out(task, {}, "training", allocation, DIRECT, SRGB,
                                              Deployment.RIG_FIXED) if f.blocking]

def test_isohue_carries_its_design_frame(task):
    """§6 of the console settings design: **wl-xtasks' isohue says how its hues were made**, the
    frame the hue-angle method defines a new color in (Task 8): CAM16-UCS, about a gray of
    lightness J' 65 -- wl-style's generator's reference gray, `isohue.py`'s `J_REF` and its
    METHODS.md -- at chroma 29.49, its source sentence's own; the source says where both came
    from, and the task reads the set as the file gives it."""
    theirs = photometry.ColorSet.load(STIMULI)
    frame = {"space": "CAM16-UCS", "gray_lightness": 65.0, "chroma": 29.49}
    assert theirs.design == frame
    assert json.loads(STIMULI.read_text())["design"] == frame
    assert "chroma 29.49" in theirs.source and "J' 65" in theirs.source
    (light,) = {look.color.colorset for pairing in task.pool.choices for look in pairing}
    assert light.design == frame


def _scheduler(task, values: dict, start: int = 0):
    """The pop-out plan's scheduler, as a run makes it, reading `values` live."""
    from wl_xcon import variation
    from wl_xcon.scheduler import Scheduler

    plan = task.plans["training"]
    return Scheduler(
        blocks=[variation.expanded(block) for block in plan.blocks], seed=0,
        counting=task.trial.counting,
        countings={name: structure.counting for name, structure in task.structures.items()},
        order=plan.order, start=start, values=lambda: values,
        params={param.name: param for param in task.params})


def test_the_bars_read_the_last_window_of_more_answers_kept(task):
    """The re-review, I-4: each bar keeps as many answers as its window setting can be (200), and
    reads **the last `move_up_window`, or `move_back_window`, of them** -- "80% correct, last 50
    trials". Sixty wrong then fifty right: the move up is suggested on 50 of the last 50; fifty
    right then fifty wrong, a stage above the first: the move back on 0 of the last 50. The panel's
    numbers are the same last 50."""
    from wl_xcon.scheduler import MOVE_BACK, MOVE_UP

    values = {param.name: param.start for param in task.params if param.start is not None}
    up = _scheduler(task, values)
    for outcome in [Outcome.WRONG_TARGET] * 60 + [Outcome.CORRECT] * 50:
        up.judged(outcome, True, True, False, True)
    assert up.bar(MOVE_UP) == (50, 50, True)
    assert (up.suggestion.move, up.suggestion.correct, up.suggestion.of) == ("up", 50, 50)
    assert (up.answers.correct, up.answers.of, up.answers.up_correct, up.answers.up_of) == (
        50, 50, 50, 50)

    back = _scheduler(task, values, start=1)
    for outcome in [Outcome.CORRECT] * 50 + [Outcome.WRONG_TARGET] * 50:
        back.judged(outcome, True, True, False, True)
    assert back.bar(MOVE_BACK) == (0, 50, True)
    assert (back.suggestion.move, back.suggestion.correct, back.suggestion.of) == ("back", 0, 50)


def test_a_window_set_above_its_highest_is_kept_that_long(task):
    """The re-review, M-3 (`Scheduler._fit`): a window a person sets above its declared highest
    (`move_up_window` 300, above 200), as a live value outside its range may be, is kept that long
    from then on, so its bar is judged on 300 answers once that many are in, never on the 200 the
    window was first kept as."""
    from wl_xcon.scheduler import MOVE_UP

    values = {param.name: param.start for param in task.params if param.start is not None}
    up = _scheduler(task, values)
    values["move_up_window"] = 300
    for _ in range(299):
        up.judged(Outcome.CORRECT, True, True, False, True)
    assert up.suggestion is None
    up.judged(Outcome.CORRECT, True, True, False, True)
    assert up.bar(MOVE_UP) == (300, 300, True) and up.suggestion.of == 300


def test_the_window_whose_exit_starts_the_answer_reaching_the_discs_is_warned(task, tmp_path):
    """The re-review, I-2 (the controller's ruling of 2026-11-08: a warning, by the PI's "warnings
    over refusals"): the answer begins as the eye leaves the fixation window, `fix` since the
    pop-out's revision (the point stays on); where that
    window reaches a disc's window -- a ring of 4° and a fixation window of 4.5°, both inside their
    ranges -- a look straight to the odd one, held, never leaves it, and ends as no response, a
    staircase's failure, with no reward. So **a value set live that makes it reach is warned on the
    changes feed** as it applies; at the starts nothing reaches, so the load warns of nothing
    (`answer-window-reaches-objects`): since the console settings plan's Task 11 the pop-out
    declares no range for the ring or the windows that could reach, so the load judges them at
    their starts, where it warned over the old ranges about their smallest ring."""
    from wl_xcon.check import answer_reaches

    right = [LOOK, ("go", 48, on_circle_deg(0.0, 0.0, 4.0, 0.0))]
    fine = _play_at(task, right, ring_radius=4.0, fix_window=3.0)
    assert fine.outcome is Outcome.CORRECT
    reached = _play_at(task, right, ring_radius=4.0, fix_window=4.5)
    assert reached.outcome is Outcome.NO_RESPONSE and reached.visited[-1] == "go"
    assert staircase_verdict(reached.outcome, _appeared(task.trial, reached)) is False

    found = [f for f in check_task(task, _load_allocation(Path(ALLOCATION)), geometry=DIRECT,
                                   calibration=SRGB, deployment=Deployment.RIG_FIXED,
                                   source=TASK_FILE)
             if f.code == "answer-window-reaches-objects"]
    assert found == []
    starts = {param.name: param for param in task.params}
    assert answer_reaches(task.trial, {
        name: (param if param.choices or param.start is None
               else replace(param, low=param.start, high=param.start))
        for name, param in starts.items()}) == []

    trainer = _Locks("ring_radius", 4.0, stop_at=6, more=(("fix_window", 4.5),))
    session = _opened(_spec(tmp_path, seed=5, start_block="Fade-in"), trainer)
    trainer.session = session
    session.run()
    warned = [said for kind, _, _, said in session.controls if kind == "warning"
              and said.startswith("answer-window-reaches-objects")]
    # Once, naming each structure scoring the discs: the search, and the probe of the odd one
    # alone (XC-545).
    assert [said.split(": ")[1] for said in warned] == [
        "in structures 'search', 'odd_one_alone'"], warned
    assert all("on a ring as small as 4° about it" in said for said in warned)
    assert all("its radius up to 4.5° and theirs up to 1.5°" in said for said in warned)


def _play_at(task, moves, **values):
    """One trial of the task at its starts but `values`, its eye making `moves`: the result."""
    bound = {**_values(task), **values}
    eye = _Eye(moves)
    return run_trial(task.trial, _Seen(eye, task.trial, bound), FRAME, values=dict(bound),
                     effects=Recorded())


def test_a_stages_floor_is_a_setting_and_a_step_that_makes_no_levels_is_warned(task, tmp_path):
    """The controller's rulings of 2026-11-08 on the re-review: **each staircase's easiest end is a
    setting** (M-6: `fade_in_floor`, `crowd_floor`, the PI's 0.1 and 4 to start), so a trainer who
    raises Fade-in's floor to 0.4 has it start there and never step below it; and **a step set far
    below its range, which makes no levels, is warned as it is set** (M-4,
    `staircase-steps-unmade`: the staircase keeps the levels it had, while the lines record the
    step set). Nothing is warned inside the declared ranges."""
    from wl_xcon.check import beyond_range

    trainer = _Locks("fade_in_floor", 0.4, stop_at=30)
    session = _opened(_spec(tmp_path, seed=5, start_block="Fade-in"), trainer)
    trainer.session = session
    session.run()
    lines = _rows(session, "trials.jsonl")
    assert lines[0]["params"]["distractor_fraction"] == 0.1
    assert lines[1]["params"]["distractor_fraction"] == 0.4
    assert {line["params"]["distractor_fraction"] for line in lines[1:]} <= {
        0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0}
    assert all(line["drawn"]["distractor_fraction"] == "staircase" for line in lines)

    allocation = _load_allocation(Path(ALLOCATION))
    assert "staircase-steps-unmade" not in {
        f.code for f in check_task(task, allocation, geometry=DIRECT, calibration=SRGB,
                                   deployment=Deployment.RIG_FIXED)}
    found = [f for f in beyond_range(task, {"fade_in_step": 0.0005}, allocation, geometry=DIRECT,
                                     calibration=SRGB, deployment=Deployment.RIG_FIXED)
             if f.code == "staircase-steps-unmade"]
    assert len(found) == 1 and found[0].is_warning
    assert ("block 'Fade-in''s staircase on 'distractor_fraction' makes no levels at a step of "
            "0.0005 ('fade_in_step')") in found[0].detail
    assert "the staircase keeps the levels it had" in found[0].detail


def test_the_pis_margin_holds_a_suggestion_until_37_of_50_and_back_until_27(task):
    """The PI, 2026-11-08: "Stay up until 3 below" -- "With the 80% bar, it appears at 40 of 50 and
    goes only below 37. The 3 is itself a console setting." The pop-out's `suggestion_margin`, 3
    to start, read live (`Scheduler.holds`): the move up met at 40 of 50 holds at 37 and not at
    36; at a margin of 0 it holds only where met. In mirror, the move back met under 25 of 50 holds
    while fewer than 28 are right -- missed by no more than 3 answers -- and goes at 28."""
    from wl_xcon.scheduler import MOVE_BACK, MOVE_UP

    values = {param.name: param.start for param in task.params if param.start is not None}
    up = _scheduler(task, values)
    for outcome in [Outcome.CORRECT] * 40 + [Outcome.WRONG_TARGET] * 10:
        up.judged(outcome, True, True, False, True)
    assert up.bar(MOVE_UP)[:2] == (40, 50) and up.suggestion.move == "up"
    for right in (39, 38, 37):
        up.judged(Outcome.WRONG_TARGET, True, True, False, True)
        assert up.bar(MOVE_UP)[0] == right and up.holds(MOVE_UP) and up.suggestion is None
    values["suggestion_margin"] = 0
    assert not up.holds(MOVE_UP)
    values["suggestion_margin"] = 3
    up.judged(Outcome.WRONG_TARGET, True, True, False, True)
    assert up.bar(MOVE_UP)[0] == 36 and not up.holds(MOVE_UP)

    back = _scheduler(task, values, start=1)
    for outcome in [Outcome.WRONG_TARGET] * 26 + [Outcome.CORRECT] * 24:
        back.judged(outcome, True, True, False, True)
    assert back.bar(MOVE_BACK)[:2] == (24, 50) and back.suggestion.move == "back"
    for _ in range(3):
        back.judged(Outcome.CORRECT, True, True, False, True)
    assert back.bar(MOVE_BACK)[0] == 27 and back.holds(MOVE_BACK)
    back.judged(Outcome.CORRECT, True, True, False, True)
    assert back.bar(MOVE_BACK)[0] == 28 and not back.holds(MOVE_BACK)


class _Moves(Simulated):
    """**A trainer who moves the run by hand**: `moves[n]` sent at drain `n`, noting the open stage
    and its staircase's value as it is left (`left`); the run stopped at drain `stop_at`."""

    def __init__(self, moves: dict, stop_at: int) -> None:
        super().__init__()
        self.moves, self.stop_at, self.drains = moves, stop_at, 0
        self.session: Session | None = None
        self.left: list = []

    def drain(self) -> list:
        self.drains += 1
        if self.drains in self.moves:
            climb = self.session._climb
            self.left.append((self.session._scheduler.block.name,
                              None if climb is None else climb.value))
            self.queue(self.moves[self.drains])
        if self.drains == self.stop_at:
            self.queue(Stop(by=JAKE))
        return super().drain()


def test_a_stage_the_animal_returns_to_picks_up_where_it_left(task, tmp_path):
    """The PI, 2026-11-08, asked in the UI: "Pick up where it left" -- "Fade-in resumes at the step
    the animal reached before moving up; if it struggles there, the staircase eases" -- and "Pick
    up there too": "Any stage the animal returns to resumes where it left". A run in Fade-in is
    moved up to Crowd, back to Fade-in, and up to Crowd again: **each return resumes at the level
    its staircase was at when the run left that stage**, never at its floor or nearest the run's
    value, as a stage first visited starts (TSK-57 as amended), and its line says the staircase
    gave it."""
    trainer = _Moves({26: NextBlock(by=JAKE), 46: BackBlock(by=JAKE), 58: NextBlock(by=JAKE)},
                     stop_at=64)
    session = _opened(replace(_spec(tmp_path, seed=5, start_block="Fade-in"), accuracy=0.95),
                      trainer)
    trainer.session = session

    session.run()

    lines = _rows(session, "trials.jsonl")
    visits: list = []
    for line in lines:
        if not visits or visits[-1][0] != line["block"]:
            visits.append((line["block"], []))
        visits[-1][1].append(line)
    assert [block for block, _ in visits] == ["Fade-in", "Crowd", "Fade-in", "Crowd"]
    (_, fade_left), (_, crowd_left), _ = trainer.left
    assert fade_left > 0.1 and crowd_left > 4, "the stages left above where they start"
    back = visits[2][1][0]
    assert back["params"]["distractor_fraction"] == fade_left
    assert back["drawn"]["distractor_fraction"] == "staircase"
    up = visits[3][1][0]
    assert up["params"]["set_size"] == crowd_left and up["drawn"]["set_size"] == "staircase"
    # A stage first visited starts as it always has: Crowd at 4.
    assert visits[1][1][0]["params"]["set_size"] == 4


def test_a_margin_that_can_reach_a_bars_count_is_warned_at_load_and_live(task, tmp_path):
    """The re-review 2, M-7 (the controller's ruling: a warning, never a refusal): a margin as large
    as a bar's count makes a suggestion its bar can never withdraw -- up at 4 of 5 with a margin of
    5 holds with none right. **At load**, over the ranges, the pop-out's margin of up to 20 can
    reach every stage's bar on a 1-answer window, its lowest since the console settings plan's
    Task 11 (`margin-reaches-bar`); **live**, the changes feed
    warns once as values set make it reach -- a 5-answer window with a margin of 5 -- and nothing at
    the starts."""
    from wl_xcon.check import margin_reaches

    found = [f for f in check_task(task, _load_allocation(Path(ALLOCATION)), geometry=DIRECT,
                                   calibration=SRGB, deployment=Deployment.RIG_FIXED,
                                   source=TASK_FILE)
             if f.code == "margin-reaches-bar"]
    assert len(found) == 2 and all(f.is_warning for f in found)
    assert ("can reach stages 'Alone', 'Fade-in' and 'Crowd''s bars to move up, as few as 0.5 "
            "right answers") in found[0].detail
    starts = {name: (param if param.choices or param.start is None
                     else replace(param, low=param.start, high=param.start))
              for name, param in {p.name: p for p in task.params}.items()}
    assert margin_reaches(task.plans["training"], starts) == []

    trainer = _Locks("suggestion_margin", 5.0, stop_at=6, more=(("move_up_window", 5.0),))
    session = _opened(_spec(tmp_path, seed=5, start_block="Fade-in"), trainer)
    trainer.session = session
    session.run()
    warned = [said for kind, _, _, said in session.controls if kind == "warning"
              and said.startswith("margin-reaches-bar")]
    assert len(warned) == 1 and "as few as 4 right answers" in warned[0]



# --- The console interface rework's Task 9: plain names, one sentence, whole numbers, groups ---

#: **The pop-out's counts** (the console interface design's goal 6; the PI, 2026-11-19, of a set
#: size: "there should not be a decimal option for entry"): every setting that can only be a whole
#: number -- the set size, the pool's value, the bars' windows, the margin, the staircases' counts,
#: Crowd's step and floor -- and nothing legitimately fractional.
WHOLE = ("set_size", "pairings", "move_up_window", "move_back_window", "suggestion_margin",
         "staircase_down", "staircase_up", "crowd_step", "crowd_floor", "target_absent_percent",
         "odd_place_empty_percent", "distractor_alone_percent", "odd_one_alone_percent")
#: The units that count, each held whole: a special kind's share of trials among them since the
#: pop-out's revision (its plan's Amendments, item 4: "each share `whole=True`").
COUNTS = ("objects", "answers", "pairings", "percent")
#: **The training rules as the trainer reads them** (the design's goal 8; its own example, "Move up
#: when at least [80]% of the last [50] answers are right"): each group's title, its settings in
#: its box's order, and its sentence. The PI reviews the words on the wl-xtasks branch.
GROUPS = (
    # The special trials' (the pop-out revision's plan, Amendments, item 4), right after Timing.
    ("Special trials", ("target_absent_percent", "odd_place_empty_percent",
                        "distractor_alone_percent", "odd_one_alone_percent", "catch_hold"),
     "Of every 100 trials: {target_absent_percent} target absent, {odd_place_empty_percent} odd "
     "place empty, {distractor_alone_percent} a distractor alone, {odd_one_alone_percent} the odd "
     "one alone; a catch is held {catch_hold}"),
    ("Move up", ("move_up_bar", "move_up_window"),
     "Move up when at least {move_up_bar} of the last {move_up_window} answers at the hardest "
     "step are right"),
    ("Move back", ("move_back_bar", "move_back_window"),
     "Move back when fewer than {move_back_bar} of the last {move_back_window} answers are right"),
    ("Staircase", ("staircase_down", "staircase_up"),
     "One level harder after {staircase_down} right in a row, one level easier after "
     "{staircase_up} wrong in a row"),
)


def test_every_popout_setting_has_a_label_and_help(task):
    """The design's goal 5 (the PI, 2026-11-19: "descriptions are too long ... what are
    pairings?"): **every setting has a plain name and one sentence saying what it is**. The name is
    the trainer's words, `LABEL_LIMIT` at most, no code name's underscore, none two alike (the
    load's `bad-label` refuses that); the code name stays as it is, the record's and the task's. The
    sentence is one, `REASON_LIMIT` at most, ending in its one full stop, and names no number: its
    value, limits and their reasons are the box's and its *more*'s, not the sentence's. **The
    pairings' sentence says what a pairing is**: an odd disc's color with the distractors'."""
    import re

    from wl_xcon.check import BAD_LABEL
    from wl_xcon.task import LABEL_LIMIT, REASON_LIMIT

    for param in task.params:
        assert param.label and len(param.label) <= LABEL_LIMIT, param.name
        assert "_" not in param.label and param.label != param.name, param.name
        assert param.help and len(param.help) <= REASON_LIMIT, param.name
        assert param.help.endswith(".") and param.help.count(".") == 1, param.name
        assert not re.search(r"[0-9]", param.help), param.name
    labels = [" ".join(param.label.split()).casefold() for param in task.params]
    assert len(set(labels)) == len(labels)
    assert BAD_LABEL not in {f.code for f in check_task(
        task, _load_allocation(Path(ALLOCATION)), geometry=DIRECT, calibration=measured(),
        deployment=Deployment.RIG_FIXED, source=TASK_FILE)}
    (pairings,) = [param for param in task.params if param.name == "pairings"]
    assert "odd" in pairings.help and "distractor" in pairings.help and "pair" in pairings.help


def test_the_popouts_counts_are_whole(task):
    """The design's goal 6: **each count is declared whole** -- `WHOLE`, every setting in a unit
    that counts and none other -- so its box steps by 1 with no decimals, the load finds no
    `bad-whole`, and **a fraction given one is refused** before a run starts (`preflight.values`)
    with the sentence that says it is a whole number."""
    from wl_xcon import preflight
    from wl_xcon.check import BAD_WHOLE
    from wl_xcon.task import step_of

    assert {param.name for param in task.params if param.whole} == set(WHOLE)
    assert {param.name for param in task.params if param.unit in COUNTS} == set(WHOLE)
    assert {param.name: step_of(param) for param in task.params if param.whole} == dict.fromkeys(
        WHOLE, 1)
    assert BAD_WHOLE not in {f.code for f in check_task(
        task, _load_allocation(Path(ALLOCATION)), geometry=DIRECT, calibration=measured(),
        deployment=Deployment.RIG_FIXED, source=TASK_FILE)}
    starts = _values(task)
    assert preflight.values(task, starts).result == preflight.PASS
    for param in task.params:
        if param.whole:
            item = preflight.values(task, {**starts, param.name: param.start + 0.5})
            assert item.result == preflight.FAIL, param.name
            assert (f"'{param.name}' is a whole number of {param.unit}, and "
                    f"{param.start + 0.5:g} is not one") in item.said, (param.name, item.said)


def test_the_popouts_training_rules_read_as_sentences(task, tmp_path):
    """The design's goal 8 (the PI, 2026-11-19, "One box after Timing"): **the bars and the
    staircases read as three rules, each one box with one Apply** -- *Move up*, *Move back* and
    *Staircase* (`GROUPS`), their settings sharing a section, none a reward size (the load's
    `bad-group`), after the special trials' one box (the pop-out's revision, its plan's Amendments,
    item 4); **the two bars are percents**, with the distractors' brightness and Fade-in's
    step and floor (the PI, 2026-11-19), and the fixation point's saturations, and no other
    setting is; at the starts the rules
    read "Move up when at least 80% of the last 50 answers at the hardest step are right". **The
    path to the page**: a session on the task sends each group and each setting's plain name, help,
    wholeness and percent, and the Training tab draws each rule as one box whose sentence holds its
    fields, its settings drawing no box of their own."""
    import re

    from _frames import frame, view
    from wl_xcon import web
    from wl_xcon.link import GroupRow, ParamRow

    assert [(group.name, group.settings, group.sentence) for group in task.groups] == list(GROUPS)
    # The PI, 2026-11-19 (asked in the UI): the distractors' brightness and Fade-in's step and
    # floor, fractions of full, read as percents too.
    assert {param.name for param in task.params if param.percent} == {
        "move_up_bar", "move_back_bar", "distractor_fraction", "fade_in_step", "fade_in_floor",
        # The fixation point's saturations, fractions of full chroma (the pop-out's revision).
        "fix_saturation", "fix_act_saturation"}
    assert "bad-group" not in {f.code for f in check_task(
        task, _load_allocation(Path(ALLOCATION)), geometry=DIRECT, calibration=measured(),
        deployment=Deployment.RIG_FIXED, source=TASK_FILE)}
    starts = {param.name: (f"{param.start * 100:g}%" if param.percent else f"{param.start:g}")
              for param in task.params if isinstance(param.start, (int, float))}
    assert [group.sentence.format(**starts) for group in task.groups] == [
        "Of every 100 trials: 0 target absent, 0 odd place empty, 0 a distractor alone, 0 the odd "
        "one alone; a catch is held 0.5",
        "Move up when at least 80% of the last 50 answers at the hardest step are right",
        "Move back when fewer than 50% of the last 50 answers are right",
        "One level harder after 3 right in a row, one level easier after 1 wrong in a row"]

    session = Session(_spec(tmp_path, seed=1), card=Card(), pump=Pump())
    groups = tuple(GroupRow(*group) for group in session.groups)
    assert [(group.name, group.settings, group.section) for group in groups] == [
        ("Special trials", ("target_absent_percent", "odd_place_empty_percent",
                            "distractor_alone_percent", "odd_one_alone_percent", "catch_hold"),
         "Special trials"),
        ("Move up", ("move_up_bar", "move_up_window"), "Training/bars"),
        ("Move back", ("move_back_bar", "move_back_window"), "Training/bars"),
        ("Staircase", ("staircase_down", "staircase_up"), "Training/staircases")]
    rows = tuple(ParamRow.of(*row) for row in session.parameters)
    by_name = {row.name: row for row in rows}
    declared = {param.name: param for param in task.params}
    for name, row in by_name.items():
        if name in declared:
            param = declared[name]
            assert (row.label, row.help, row.whole, row.percent) == (
                param.label, param.help, param.whole, param.percent), name
    training = web.fragments(frame(params=rows, groups=groups), view())["training-params"]
    cards = re.findall(r'data-card="([^"]+)"', training)
    assert {"Move up", "Move back", "Staircase"} <= set(cards)
    assert not {"move_up_bar", "move_up_window", "move_back_bar", "move_back_window",
                "staircase_down", "staircase_up"} & set(cards)
    sentence = re.search(r'data-card="Move up".*?<div class="sentence">(.*?)</div>',
                         training).group(1)
    words = re.findall(r'<span class="gs">(.*?)</span>', sentence)
    assert words == ["Move up when at least ", " of the last ",
                     " answers at the hardest step are right"]
    assert 'data-param="move_up_bar"' in sentence and 'data-percent="1"' in sentence
    assert 'data-param="move_up_window"' in sentence and 'data-whole="1"' in sentence


def test_pairings_sit_with_the_colors(task, tmp_path):
    """The design (Task 9): **the pairings sit in Colors, with the colors they pair**, not in a
    section of their own; on the page their grid is a box of the Colors section."""
    import re

    from _frames import frame, view
    from wl_xcon import web
    from wl_xcon.link import GroupRow, ParamRow
    from wl_xcon.task import section_of

    sections = {param.name: section_of(param) for param in task.params}
    assert sections["pairings"] == "Colors"
    assert "Pairings" not in set(sections.values())
    assert [name for name, section in sections.items() if section == "Colors"] == [
        "odd_color", "distractor_color", "color_luminance", "distractor_fraction", "pairings"]
    session = Session(_spec(tmp_path, seed=1), card=Card(), pump=Pump())
    rows = tuple(ParamRow.of(*row) for row in session.parameters)
    params = web.fragments(frame(params=rows, groups=tuple(GroupRow(*group)
                                                           for group in session.groups)),
                           view())["params"]
    # The summary's sections (the summary and editor design of 2026-11-19), each line opening
    # its box (a section's *New color…* line opens no box).
    summary = params.partition('<div class="legend">')[0]
    sections = re.findall(
        r'<div class="ssec" data-section="([^"]+)">(.*?)(?=<div class="ssec" |$)', summary, re.S)
    boxed = {section: re.findall(
                 r'<button type="button" class="line(?! newcolor)[^"]*" data-open="([^"]+)"', body)
             for section, body in sections}
    assert boxed["Colors"] == ["odd_color", "distractor_color", "color_luminance",
                               "distractor_fraction", "pairings"], boxed
    assert "Pairings" not in boxed
