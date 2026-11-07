"""The simulated eye through `gaze.Tracked` (XC-456; the pop-out search plan's Task 8).

Until this, a simulated session's animal was `simulate.Subject`, which fires a guard by a hazard rate
per guard type and has no gaze: a saccade "to the target" was a coin weighted by rates, wherever the
task drew the target, and the saccade rules the rig scores by (EYE-19) were never asked. The XC-410
review's probe L showed it: a state entered as gaze leaves the fixation window, asking for a saccade
to the target, scored where the eye lands on the rig, 24 of 24, and 115 CORRECT / 85 WRONG_TARGET by
the simulator's rates (`docs/research/2026-11-06-saccade-rules-probes/pL_exited_then_saccade.py`).

`simeye.Eye` is a gaze source that looks at what the display draws, and `gaze.Tracked` scores it,
so a simulated session of a task with gaze guards is scored by the rig's own eye rules, sample by
sample. The task here is that probe's shape in a whole trial, the pop-out search's (its design
§3.1): fixate, hold, the dot goes off as the items come on (the go), and the next saccade from
fixation is the answer, a state the eye leaving the fixation window enters asking where it lands.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest

from _builds import built_on, builds_of
from _rig import DIRECT
from wl_xcon import simeye, simulate
from wl_xcon.bounds import Bounds, Ceiling, Floor
from wl_xcon.cli import _load_task
from wl_xcon.dio import Simulated as Card
from wl_xcon.eye import Tracker
from wl_xcon.gaze import Tracked
from wl_xcon.geometry import separation_deg
from wl_xcon.photometry import SRGB
from wl_xcon.run import Recorded, run_trial
from wl_xcon.saccade import Detector, detect
from wl_xcon.task import (After, Entered, Exited, On, Outcome, Pressed, SaccadeTo, State, Trial,
                          Window)
from wl_xcon.taskd import Session, SessionSpec
from wl_xcon.welfare import Deployment, Simulated as Pump

#: The rig's frame period in a simulated session (`wlx run`'s, `wlx taskd`'s).
FRAME = 1 / 240

#: The pop-out search's trial (its design §3.1), as a task file: fixate within 2 s, hold 0.5 s, the
#: dot off and the four items on in one frame, the go; the eye leaving the fixation window (a
#: remembered one, the dot being gone) enters `flight`, which scores the saccade where it lands: on
#: the odd one, then held 0.3 s; on another item, an error; on empty space, an abort.
_TASK = '''
from wl_xcon.photometry import Gray
from wl_xcon.task import (
    OWED, REMEMBERED, After, Array, Choice, Counting, Disc, Entered, Exited, Hide, Hold,
    ObjectWindows, On, Outcome, P, Param, ReactionTime, Reward, SaccadeTo, Show, Square, State,
    Stimulus, Task, Trial, Window,
)

FIX = Stimulus("fix", at=(0.0, 0.0), looks=Disc(size=0.3, color=Gray(40.0)))
ITEMS = Stimulus("search", at=(0.0, 0.0), looks=Array(
    n=4, radius=8.0, target=P("target_index"), looks=Disc(size=1.0, color=Gray(40.0)),
    among=Square(size=1.0, color=Gray(40.0))))

search = Trial(
    start="await_fix",
    counting=Counting(after_stimulus=OWED, appears="go"),
    windows=[Window("fix", at=(0.0, 0.0), radius=2.0, on="fix"),
             Window("center", at=(0.0, 0.0), radius=2.0, on=REMEMBERED),
             ObjectWindows(of="search", radius=1.5)],
    params=[Param("target_index", unit="index", low=0, high=3, start=1)],
    states=[
        State("await_fix", enter=[Show(FIX)],
              go=[On(Entered("fix"), "hold_fix"), On(After(2.0), Outcome.NO_FIXATION)]),
        State("hold_fix",
              go=[On(Hold("fix", 0.5), "go", do=[Hide("fix"), Show(ITEMS)]),
                  On(Exited("fix"), Outcome.FIXATION_BREAK),
                  On(After(10.0), Outcome.NO_FIXATION)]),
        State("go", go=[On(Exited("center"), "flight"), On(After(1.0), Outcome.NO_RESPONSE)]),
        State("flight", go=[On(SaccadeTo("search.target"), "hold_target"),
                            On(SaccadeTo("search.distractor"), Outcome.WRONG_TARGET),
                            On(After(0.3), Outcome.ABORT)]),
        State("hold_target",
              go=[On(Hold("search.target", 0.3), Outcome.CORRECT, do=[Reward("reward_correct")]),
                  On(Exited("search.target"), Outcome.TARGET_BREAK),
                  On(After(3.0), Outcome.NO_RESPONSE)]),
    ],
)

TASK = Task(
    {"search": search},
    default="search",
    reaction_time=ReactionTime("go", ("flight",), "from the go to the eye leaving the fixation window"),
    choice=Choice(objects=("search.target", "search.distractor"), by="saccade"),
    needs_fixed_head=True,
)
'''


@pytest.fixture(scope="module")
def search(tmp_path_factory) -> Trial:
    path = tmp_path_factory.mktemp("simeye") / "relay_search.py"
    path.write_text(_TASK)
    return _load_task(path).trial


class _Kept:
    """A gaze source that keeps each sample it hands over: the eye's, as `gaze.Tracked` read it."""

    def __init__(self, source, kept: list) -> None:
        self.source = source
        self.kept = kept

    def poll(self, at: float):
        sample = self.source.poll(at)
        self.kept.append(sample)
        return sample


class _Arrived:
    """Samples already made, one a poll: a trial's samples handed to `gaze.Tracked` again."""

    def __init__(self, samples: list) -> None:
        self.samples = samples
        self.polled = 0

    def poll(self, at: float):
        if self.polled >= len(self.samples):
            return None
        sample = self.samples[self.polled]
        self.polled += 1
        return sample


def _played(trial: Trial, eye, trials: int, values: dict) -> Counter:
    """`trials` trials of `trial` through the eye's own world, their outcomes counted."""
    outcomes = Counter()
    for _ in range(trials):
        world = eye.world(trial, values, FRAME)
        outcomes[run_trial(trial, world, FRAME, values=values, effects=Recorded()).outcome] += 1
    return outcomes


def _bounds() -> Bounds:
    return Bounds(
        subject="A",
        ceilings={
            "reward_correct": Ceiling(value=0.15, maximum=0.40, unit="mL"),
            "out_of_cage": Ceiling(value=28_800.0, maximum=100_000.0, unit="s"),
        },
        minima={"daily_fluid": Floor(value=250.0, unit="mL")},
    )


def test_a_simulated_session_scores_as_gaze_tracked_does(tmp_path, monkeypatch):
    """**The XC-456 probe's case, a whole session**: a simulated session of a task with gaze guards,
    its world left to the session (`Session.world` unset), plays every trial through the eye, and
    each trial's recorded outcome is what `gaze.Tracked` makes of the samples the eye gave it,
    handed to a plain `Tracked` again: 200 trials, where the hazard simulator scored the same
    state 115 CORRECT / 85 WRONG_TARGET whatever its gaze did, having none. Its answers land on
    the odd one and on the others, as its accuracy has them."""
    path = tmp_path / "relay_search.py"
    path.write_text(_TASK)
    played = []
    made = simeye.Eye.world

    def world(eye, trial, values, frame_period):
        seen = made(eye, trial, values, frame_period)
        kept: list = []
        played.append((trial, dict(values), kept))
        seen.source = _Kept(seen.source, kept)
        return seen

    monkeypatch.setattr(simeye.Eye, "world", world)
    spec = SessionSpec(
        task=str(path), allocation="tasks/allocation.py", root=tmp_path,
        session_id="2027-01-14_01", subject="A", trials=200, frame_period=FRAME, seed=4,
        values={}, bounds=_bounds(), already_delivered_today=0.0,
        deployment=Deployment.RIG_FIXED, geometry=DIRECT, session_kind="training",
        calibration=SRGB,
    )
    session = Session(spec, card=Card(), pump=Pump())
    session.wall_clock = lambda: 1_700_000_000.0 + session.now()
    session.left_cage(at=session.wall_now())
    session.head_fixed(at=session.wall_now())

    session.run()

    rows = [json.loads(line)
            for line in (session.directory / "trials.jsonl").read_text().splitlines()]
    assert len(rows) >= 200
    assert len(played) == len(rows), "a trial of the session was not played through the eye"
    scored = [
        run_trial(trial, Tracked(Tracker(), simeye.MAPPING, trial, FRAME, values,
                                 source=_Arrived(kept)),
                  FRAME, values=values, effects=Recorded()).outcome.value
        for trial, values, kept in played
    ]
    assert [row["outcome"] for row in rows] == scored
    counted = Counter(scored)
    assert counted["correct"] >= 100 and counted["wrong_target"] >= 5, counted


def test_accuracy_one_scores_correct_every_answer(search):
    """An eye that always answers right, never early, scores CORRECT on every trial, wherever the
    display draws the odd one (each target index, so each a different place on the ring); one that
    never answers right lands on another item every time, WRONG_TARGET. The answer is where the
    eye goes, read from the display, and `gaze.Tracked` says where it landed."""
    for target in range(4):
        eye = simeye.Eye(accuracy=1.0, rt_median_s=0.2, early_rate=0.0, seed=target)
        assert _played(search, eye, 30, {"target_index": target}) == Counter(
            {Outcome.CORRECT: 30}), target

    wrong = simeye.Eye(accuracy=0.0, rt_median_s=0.2, early_rate=0.0, seed=9)
    assert _played(search, wrong, 30, {"target_index": 2}) == Counter({Outcome.WRONG_TARGET: 30})


def test_an_answer_with_no_distractor_drawn_lands_on_empty_space():
    """**Empty space** (the PI, 2026-11-07: "anything other than looking at the target with the
    next saccade from fix to the target is an error"; the pop-out search design §3.1): with nothing
    but the target drawn -- the reference detection task, one target
    10° out -- an answer that is not the target's lands at the target's eccentricity, in a
    direction away from every window by the margin, and the task scores no response; never in a
    window, and never anywhere but where a saccade of the answer's size goes."""
    trial = _load_task(Path("tasks/fixation_detection.py")).trial
    values = {param.name: param.start for param in trial.params}
    eye = simeye.Eye(accuracy=0.0, rt_median_s=0.2, early_rate=0.0, seed=4)
    directions = set()
    for _ in range(30):
        world = eye.world(trial, values, FRAME)
        result = run_trial(trial, world, FRAME, values=values, effects=Recorded())
        assert result.outcome is Outcome.NO_RESPONSE
        assert result.visited == ("await_fix", "hold_fix", "stim_on")
        assert separation_deg(0.0, 0.0, eye._x, eye._y) == pytest.approx(10.0)
        assert separation_deg(10.0, 0.0, eye._x, eye._y) > 3.0 + simeye.MARGIN_DEG
        assert separation_deg(0.0, 0.0, eye._x, eye._y) > 2.0 + simeye.MARGIN_DEG
        directions.add(round(eye._x, 6))
    assert len(directions) == 30, "each wrong answer a direction of its own"


def test_early_rate_produces_early_saccade_errors(search):
    """**Early, before the go** (the PI, 2026-11-07: "if a saccade starts during a cue, before the
    go period, that would be an early saccade error"): an eye early on every trial leaves the
    fixation window during the hold, FIXATION_BREAK, every trial; one never early never does; and
    one early on 30% of trials breaks on about that share, answering right on the rest."""
    values = {"target_index": 1}
    always = simeye.Eye(accuracy=1.0, rt_median_s=0.2, early_rate=1.0, seed=5)
    assert _played(search, always, 40, values) == Counter({Outcome.FIXATION_BREAK: 40})

    never = simeye.Eye(accuracy=1.0, rt_median_s=0.2, early_rate=0.0, seed=5)
    assert _played(search, never, 40, values) == Counter({Outcome.CORRECT: 40})

    some = _played(search, simeye.Eye(accuracy=1.0, rt_median_s=0.2, early_rate=0.3, seed=5),
                   400, values)
    assert set(some) == {Outcome.FIXATION_BREAK, Outcome.CORRECT}
    assert 0.24 <= some[Outcome.FIXATION_BREAK] / 400 <= 0.36, some


def test_the_detector_finds_its_saccades(search, monkeypatch):
    """**Its saccades are ones the rig's detector finds** (`saccade.Detector`, the online form
    `gaze.Tracked` feeds once a frame, and `saccade.detect`, the batch form it is checked against),
    at the 240 Hz a simulated session runs at: every saccade the eye makes in a trial and lands
    within it, once the detector has its warmup, is confirmed once, its onset within two samples of
    the eye's take-off, and the detector confirms none it did not make; the batch form measures
    each to within a quarter degree of the eye's own size; and so for a saccade of each size from
    1° to 12°, ten each. (One the eye makes during the warmup, its first sixty samples here, the
    detector may miss, or confirm from where it became ready, as it would a real eye's.)"""
    launched: list = []
    go = simeye.Eye._go

    def recorded(eye, frame, x, y):
        launched[-1].append((frame, separation_deg(eye._x, eye._y, x, y)))
        go(eye, frame, x, y)

    monkeypatch.setattr(simeye.Eye, "_go", recorded)
    eye = simeye.Eye(accuracy=0.7, rt_median_s=0.2, early_rate=0.2, seed=8)
    found = made = 0
    for trial_index in range(60):
        launched.append([])
        kept: list = []
        world = eye.world(search, {"target_index": trial_index % 4}, FRAME)
        world.source = _Kept(world.source, kept)
        run_trial(search, world, FRAME, values={"target_index": trial_index % 4},
                  effects=Recorded())
        gaze = [(sample.left.dpi_x(), sample.left.dpi_y()) for sample in kept]
        detector = Detector()
        onsets = []
        for index, position in enumerate(gaze):
            confirmed = detector.accept(index * FRAME, position)
            if confirmed is not None:
                onsets.append(confirmed.start)
        # The eye's frame `f` is sample `f - 1`; it is still at its start there, and moves from
        # the next. The warmup: no velocity threshold before 50 of them (`saccade.Params`).
        starts = [(frame - 1, size) for frame, size in launched[-1]]
        # A saccade the trial's end cuts off (an early one, ending it as it leaves the window) has
        # no landing in the trace to measure.
        late = [(start, size) for start, size in starts
                if start >= 60 and start + _samples_of(size) + 3 < len(gaze)]
        for start, _ in late:
            assert sum(1 for onset in onsets if abs(onset - start) <= 2) == 1, (trial_index,
                                                                               late, onsets)
        assert all(any(abs(onset - start) <= 2 for start, _ in starts)
                   for onset in onsets if onset >= 60), (trial_index, starts, onsets)
        runs = detect(gaze, [index * FRAME for index in range(len(gaze))])
        for start, size in late:
            measured = [run.amplitude_deg for run in runs if abs(run.start - start) <= 2]
            assert len(measured) == 1 and abs(measured[0] - size) <= 0.25, (start, size, runs)
        found += len(late)
        made += len(starts)
    assert found >= 40, (found, made)

    monkeypatch.setattr(simeye.Eye, "_go", go)
    for size in (1.0, 2.0, 4.0, 8.0, 12.0):
        for seed in range(10):
            still = simeye.Eye(accuracy=1.0, rt_median_s=0.2, early_rate=0.0, seed=seed)
            gaze = []
            for frame in range(1, 200):
                if frame == 100:
                    still._go(frame, size, 0.0)
                if still._flying:
                    still._fly(frame)
                sample = still.poll(frame * FRAME)
                gaze.append((sample.left.dpi_x(), sample.left.dpi_y()))
            detector = Detector()
            onsets = [confirmed.start for index, position in enumerate(gaze)
                      if (confirmed := detector.accept(index * FRAME, position)) is not None]
            assert len(onsets) == 1 and abs(onsets[0] - 99) <= 2, (size, seed, onsets)
            runs = detect(gaze, [index * FRAME for index in range(len(gaze))])
            assert len(runs) == 1 and abs(runs[0].amplitude_deg - size) <= 0.25, (size, runs)


def _samples_of(size: float) -> int:
    """How many samples a saccade of `size` degrees lasts, at this frame period."""
    return int((simeye.DURATION_S + simeye.DURATION_PER_DEG_S * size) / FRAME) + 1


#: **What a frame of a trial through `gaze.Tracked` builds** (XC-414; `tests/test_gaze.py`'s
#: `_ONCE_A_FRAME`): each eye's gaze through its map, and the two eyes' mean the detector is fed.
_TRACKED_FRAME = {("Mapping.degrees_of", "tuple"), ("Tracked.gaze_cyclopean", "tuple")}
#: **And what the eye's sample needs**: its Purkinje image, the pair `(x, y)` the map reads, the
#: one thing the eye builds each frame (the sample and its reading are calls, not seen here).
_THE_SAMPLE = {("Eye.poll", "tuple")}
#: What a frame that takes an edge builds besides (`tests/test_gaze.py`'s `_A_TRANSITION`): the
#: trial's record of it, and the effects the simulator's port logs.
_A_TRANSITION = {
    ("Shown.__new__", "tuple"), ("Placed.__new__", "tuple"), ("Changed.__new__", "tuple"),
    ("_apply", "tuple"), ("_apply", "dict"), ("_apply", "arguments"),
    ("Recorded.mark", "tuple"), ("Recorded.reward", "tuple"),
}


def test_a_frame_of_a_simulated_trial_builds_only_the_rig_s_and_the_eye_s_sample(search,
                                                                                 monkeypatch):
    """**Hot-path discipline** (CLAUDE.md): every frame `run_trial` runs of a trial through the
    eye -- fixating, holding, the go, the answer's flight and landing, the target held -- builds
    only what `gaze.Tracked` builds on a rig's frame and the eye's sample; the eye's decisions, a
    saccade's launch among them, build nothing. Measured on the whole frame, `run._Loop.frame` as
    `run_trial` calls it (`tests/test_gaze.py`'s measure, XC-414)."""
    from wl_xcon import run
    from wl_xcon.run import Changed, Confirmed, Placed, Shown

    records = {record.__new__.__code__: f"{record.__name__}.__new__"
               for record in (Shown, Placed, Changed, Confirmed)}
    eye = simeye.Eye(accuracy=1.0, rt_median_s=0.2, early_rate=0.0, seed=2)
    eye._x, eye._y = 8.0, 3.0  # away from the dot, so the trial begins with a saccade to it
    world = eye.world(search, {"target_index": 3}, FRAME)
    frame_of = run._Loop.frame
    measured, steady, took = [], set(), set()

    def measured_frame(loop, frame: int) -> bool:
        ended, states = [], len(loop.visited)

        def step() -> None:
            ended.append(frame_of(loop, frame))

        built = set(built_on(step, named=records))
        measured.append(frame)
        (took if ended[0] or len(loop.visited) != states else steady).update(built)
        return ended[0]

    monkeypatch.setattr(run._Loop, "frame", measured_frame)
    result = run_trial(search, world, FRAME, values={"target_index": 3}, effects=Recorded())

    assert result.outcome is Outcome.CORRECT
    assert result.visited == ("await_fix", "hold_fix", "go", "flight", "hold_target")
    assert measured == list(range(1, result.frames + 1))
    assert sorted(steady - _TRACKED_FRAME - _THE_SAMPLE) == []
    assert sorted(took - _TRACKED_FRAME - _THE_SAMPLE - _A_TRANSITION) == []
    assert builds_of(simeye.Seeing.display) == builds_of(simeye.Seeing.began) == []
    # And every path the eye can take on a frame, read whole, those this trial did not take too:
    # an answer to a distractor or to empty space, a look away, an early break.
    on_a_frame = (simeye.Eye.began, simeye.Eye.see, simeye.Eye._decide, simeye.Eye._plan,
                  simeye.Eye._launch, simeye.Eye._go, simeye.Eye._fly, simeye.Eye._aimed,
                  simeye.Eye._where, simeye.Eye._drawn, simeye.Eye._distractor,
                  simeye.Eye._empty, simeye.Eye._toward, simeye.Eye._clear)
    assert [built for method in on_a_frame for built in builds_of(method)] == []
    assert builds_of(simeye.Eye.poll) == [("Eye.poll", "tuple")]


def test_a_session_plays_a_gaze_task_through_the_eye_and_any_other_through_hazards(search):
    """**Which world a simulated session's trial gets** (`simulate.agent`, the session's default,
    `taskd.Session._agent`): a trial with gaze guards the rig's gaze world answers, the eye through
    `gaze.Tracked`; a trial with none, or with a guard no gaze world answers (a lever here), the
    hazard `Subject`, as before, since the rig's gaze world would never answer it."""
    subject = simulate.Subject(seed=1)
    make = simulate.agent(subject, simeye.Eye(accuracy=0.8, rt_median_s=0.2, early_rate=0.05,
                                              seed=1), FRAME)
    assert isinstance(make(search, {"target_index": 0}, 0), simeye.Seeing)

    timed = Trial(start="s", states=[State("s", go=[On(After(0.1), Outcome.CORRECT)])])
    assert make(timed, {}, 1) is subject

    lever = Trial(start="s", windows=[Window("fix", at=(0.0, 0.0), radius=2.0, on="fix")],
                  states=[State("s", go=[On(Entered("fix"), Outcome.CORRECT),
                                         On(Pressed("lever"), Outcome.FALSE_ALARM),
                                         On(After(1.0), Outcome.NO_FIXATION)])])
    assert make(lever, {}, 2) is subject


def test_a_timer_from_a_window_edge_never_ends_its_state_through_the_eye_as_on_a_rig(search):
    """**XC-454, narrowed**: a timer counted from the eye leaving a window,
    `After(t, since=Exited(...))`, never starts through the rig's gaze world, which answers no
    window edge; the trial ends on another edge. Through the eye it never starts either, so a
    simulated session of such a task scores as the rig would; the hazard `Subject` fires it by its
    rate, so its census does not."""
    from dataclasses import replace

    states = [
        state if state.name != "go" else replace(state, go=[
            On(After(0.05, since=Exited("center")), Outcome.EARLY_RESPONSE),
            On(SaccadeTo("search.target"), "hold_target"),
            On(SaccadeTo("search.distractor"), Outcome.WRONG_TARGET),
            On(After(1.0), Outcome.NO_RESPONSE)])
        for state in search.states
    ]
    timed = replace(search, states=states)
    eye = simeye.Eye(accuracy=1.0, rt_median_s=0.2, early_rate=0.0, seed=6)
    assert _played(timed, eye, 30, {"target_index": 0}) == Counter({Outcome.CORRECT: 30})

    hazards = simulate.Subject(seed=6, engagement=1.0, hazards={
        Entered: 20.0, Exited: 1.0, SaccadeTo: 2.0})
    census = simulate.simulate(timed, hazards, 200, FRAME, {"target_index": 0},
                               effects=Recorded())
    assert census.outcomes[Outcome.EARLY_RESPONSE] > 0
