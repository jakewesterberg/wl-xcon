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

from _calibrations import measured
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
from wl_xcon.link import Decline, NextBlock, Simulated, Stop
from wl_xcon.photometry import D65, SRGB, ColorSetLight, xyY
from wl_xcon.run import Recorded, run_trial
from wl_xcon.task import (
    EXPECTED,
    HARDER,
    NOT_DIFFICULTY,
    Array,
    ByCriterion,
    Disc,
    ObjectWindows,
    Outcome,
    P,
    Reward,
    Show,
    Window,
    actions_of,
    staircase_verdict,
)
from wl_xcon.taskd import Session, SessionSpec
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


def _play(task, moves, **values):
    """One trial of the task, its eye making `moves`: the result, the eye, and its marks and
    rewards in order."""
    bound = _values(task, **values)
    eye = _Eye(moves)
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
    `contrast-on-default`); on the measured test calibration, which carries its primaries' spectra,
    they are not. In both, its plan has no end of its own (`endless-plan`): the trainer ends a run."""
    allocation = _load_allocation(Path(ALLOCATION))

    on_default = check_task(task, allocation, geometry=DIRECT, calibration=SRGB,
                            deployment=Deployment.RIG_FIXED, source=TASK_FILE)
    on_measured = check_task(task, allocation, geometry=DIRECT, calibration=measured(),
                             deployment=Deployment.RIG_FIXED, source=TASK_FILE)

    for found in (on_default, on_measured):
        assert [f for f in found if any(f.refuses(kind) for kind in SESSION_KINDS)] == []
        assert all(f.is_warning for f in found), found
    assert {f.code for f in on_default} == {"color-on-default", "contrast-on-default",
                                             "endless-plan"}
    assert {f.code for f in on_measured} == {"endless-plan"}


def test_it_holds_the_pis_values(task):
    """§3, every number the PI's: the trial's times and sizes as each setting's start, the stages
    and their bars, the colors, black, one reward, a fixed head; and every setting of numbers starts
    somewhere (the two looks the pool gives each trial are appearances, which take none)."""
    trial = task.trial
    assert list(task.structures) == ["search"] and task.default == "search"
    starts = {param.name: param.start for param in task.params}
    assert {name: starts.get(name) for name in (
        "inter_trial", "fix_acquisition", "fix_hold", "response_deadline", "target_hold",
        "timeout", "fix_window", "object_window")} == {
        "inter_trial": 1.0, "fix_acquisition": 2.0, "fix_hold": 0.5, "response_deadline": 1.0,
        "target_hold": 0.3, "timeout": 2.0, "fix_window": 2.0, "object_window": 1.5}
    assert [param.name for param in task.params if param.start is None] == [
        "odd_color", "distractor_color"]
    assert all(param.choices for param in task.params if param.start is None)
    assert trial.background is None, "black, the default bottom layer"

    shows = {action.stimulus.name: action.stimulus
             for _, action in actions_of(trial) if isinstance(action, Show)}
    assert set(shows) == {"fix", "search"}
    assert isinstance(shows["fix"].looks, Disc) and shows["fix"].looks.size == 0.3
    ring = shows["search"].looks
    assert isinstance(ring, Array) and ring.radius == 8.0 and ring.n == P("set_size")
    assert (ring.looks, ring.among) == (P("odd_color"), P("distractor_color"))
    windows = {window.name if isinstance(window, Window) else window.of: window.radius
               for window in trial.windows}
    assert windows == {"fix": P("fix_window"), "center": P("fix_window"),
                       "search": P("object_window")}
    assert any(isinstance(window, ObjectWindows) for window in trial.windows)
    rewards = [action for _, action in actions_of(trial) if isinstance(action, Reward)]
    assert rewards == [Reward("reward_correct")]
    assert task.needs_fixed_head is True

    (plan,) = task.plans.values()
    assert list(task.plans) == ["training"]
    assert plan.order == ByCriterion(fall_back=(0.5, 50), confirm=True)
    assert [block.name for block in plan.blocks] == ["Alone", "Fade-in", "Crowd"]
    assert all(block.criterion == (0.8, 50) for block in plan.blocks)
    alone, fade_in, crowd = plan.blocks
    assert [c.values for c in alone.conditions] == [{"set_size": 1}] and alone.staircase is None
    assert [c.values for c in fade_in.conditions] == [{"set_size": 4}]
    assert [c.values for c in crowd.conditions] == [{"distractor_fraction": 1.0}]
    faint = fade_in.staircase
    assert (faint.setting, faint.down, faint.up, faint.start) == ("distractor_fraction", 3, 1, None)
    assert faint.levels[-1] == 1.0 and 0.0 < faint.levels[0] < 1.0
    assert list(faint.levels) == sorted(set(faint.levels)), "faint to full, easiest first"
    assert faint.nearest(starts["distractor_fraction"]) == 0, "Fade-in starts faint"
    more = crowd.staircase
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
        assert (odd.size, among.size) == (1.0, 1.0)
        assert _look(odd)[1] == 1.0 and _look(among)[1] == P("distractor_fraction")
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
    """§3.1, "no delay between array presentation and fixation dimming/go cue": the discs come on
    and the fixation point goes off on one frame, the frame the trial enters `go`, after the second
    of blank screen between trials and the fixation held 0.5 s. Held 0.3 s, the odd one pays one
    reward and the trial ends, with no timeout."""
    result, eye, log = _play(task, [LOOK, ("go", 48, ODD_ONE)])

    shown = _shown(result)
    assert result.outcome is Outcome.CORRECT, result.visited
    go = eye.begun["go"]
    assert eye.begun["await_fix"] == 1 + HZ, "a second of blank screen between trials"
    assert shown["fix"] == (eye.begun["await_fix"], go)
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

    assert (trials.problems, runs.problems, rig.problems, records.problems, problems) == (
        (), (), (), (), [])
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
    the chroma given up together, each color's output levels. So each line's whole parameter set
    of a Fade-in session is under 1 KB (the line's other keys, each stimulus's place among them,
    are as they were), and the record still reads back: the run's stage and pool, as wl-xcon's own
    resume finds them."""
    from wl_xcon import resume
    from wl_xcon.taskd import went_on

    session = _opened(_spec(tmp_path, seed=5, start_block="Fade-in"), _Stops(40))

    session.run()

    lines = _rows(session, "trials.jsonl")
    assert len(lines) >= 30
    # Each line's `params` as the record writes it: keys sorted, `json`'s separators.
    weights = [len(json.dumps(line["params"], sort_keys=True).encode()) for line in lines]
    assert max(weights) < 1024, sorted(weights)[-3:]
    by_reference = {"class": "P", "fields": {"name": "distractor_fraction"}}
    for line in lines:
        odd, among = (line["params"][name]["fields"]["color"]
                      for name in ("odd_color", "distractor_color"))
        assert (odd["class"], odd["fields"]["colorset"], odd["fields"]["fraction"]) == (
            "ColorSetLight", "isohue", 1.0)
        assert (among["class"], among["fields"]["colorset"], among["fields"]["fraction"]) == (
            "ColorSetLight", "isohue", by_reference)
        # The pool the run starts with: blue among red and red among blue.
        assert {odd["fields"]["color"], among["fields"]["color"]} == {"blue", "red"}

    theirs = photometry.ColorSet.load(STIMULI)
    source = json.dumps(theirs.source)[1:-1]
    written = {path.name: path.read_text() for path in session.directory.iterdir()}
    assert {name: text.count(source) for name, text in written.items() if source in text} == {
        "runs.jsonl": 1}, "the set's definition is in the record once"
    (start,) = [row for row in _rows(session, "runs.jsonl") if row["event"] == "start"]
    shown = photometry.realize(theirs, SRGB)
    assert start["calibration"] == SRGB.id
    assert start["color_sets"] == {"isohue": {
        "name": "isohue", "colors": {color: list(xy) for color, xy in theirs.colors.items()},
        "apex": list(theirs.apex), "luminance_cd_m2": 15.0, "held": "macaque_2deg_LM1",
        "source": theirs.source,
        "realized": {"desaturation": shown.desaturation,
                     "xy": {color: list(xy) for color, xy in shown.xy.items()},
                     "drive": {color: list(levels) for color, levels in shown.drive.items()}},
    }}

    restored = resume.read(session.directory, departure=1_700_000_000.0)
    went = went_on(task, restored.last_run)
    assert (went.stage, went.pool) == ("Fade-in", 66)


def test_the_twelve_pairings_and_the_four_colors_are_equal_in_macaque_luminance(task):
    """§3.2: the task's colors are `stimuli/isohue.json`'s, the numbers this repository's tests
    derived; on the test calibration, through its primaries' own spectra, each of the four colors
    the pool draws -- the odd one's, and a distractor's at full, Crowd's -- realizes at the macaque
    luminance (L + M at L:M 1, Stockman-Sharpe 2°) of a D65 light at 15 cd/m², to 0.1%, at its own
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
        X, Y, Z = photometry.colorset_xyz(replace(light, fraction=1.0), panel)
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
    fixation point went off."""
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
        stimuli = {entry["name"]: entry for entry in line["stimuli"]}
        assert stimuli["fix"]["off"] == stimuli["search"]["frame"], line["stimuli"]
