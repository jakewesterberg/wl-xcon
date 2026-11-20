"""**The pop-out search by a scripted pointer, over the real ZMQ link** (demo mode §9; its plan's
Task 6): a demo service in process on a `ZmqLink` with its four endpoints, paced on the wall clock,
the pop-out read from wl-xtasks; a scripted pointer reporting through the gaze endpoint and reading
each `Drawn` for where the discs are (`tests/_demo.py`); and the trainer's panel on the console's
SUB and REQ. Each outcome a person can give is played and recorded, scored by the rig's own eye
rules; a suggestion to move up a stage is answered from the panel and moves the run; and the
demo's record reads back through wl-preproc's own code.

**The pop-out's timings, shortened by its settings** (as `wlx demo --set` gives them, demo mode
§5): a quarter second between trials, a 0.1 s hold on the odd disc, no blank after an error, and
in the suggestion's run a bar read over the last 5 answers, so a trial takes little more than its
fixation hold. **The fixation hold is the task's draw**, non-aging from 0.75 to 1.25 s since the
pop-out's revision (its design's §6), which a run's starting value does not replace (a person's
value or draw on its card does), so every hold here is at least 0.75 s. **The time between trials stays past the saccade
detector's warm-up**: each trial's detector is fresh and reports nothing before
`saccade.Params.warmup_samples` velocities, one a frame (50, 0.21 s at 240 Hz), so a scripted
hand's answer sooner after a trial's start is never a saccade, and the `flight` state's bound
scores it a look elsewhere (XC-505). Where a scripted hand must leave inside a hold (a target
break), that hold is lengthened instead, and the fixation hold's 0.75 s at least leaves an early
saccade's and tracker loss by B's two reports inside it, so a slow computer never turns the trial
into another outcome; where a trial waits on nothing (no response, no
fixation), its wait is shortened. Each is a setting the task declares, inside its range; the
task's own numbers are not changed (demo mode §3.3). Engine test material: no timing claim rests
on the frames counted here (CLAUDE.md).
"""

from __future__ import annotations

import json
import os

import pytest

from _demo import (
    BY, FIX, REST, Demo, Person, distractor, empty_space, shown_names, target, toward_target,
)
from wl_xcon import pointer
from wl_xcon.link import NextBlock, Stop, Telemetry
from wl_xcon.saccade import HALF_WINDOW, Params
from wl_xcon.task import Outcome

#: The shortened timings every run here takes (the module docstring).
SHORT = {"inter_trial": 0.25, "target_hold": 0.1, "timeout": 0.0}
#: `tasks/eight_hour_bounds.py`'s `reward_correct`, mL, which REFERENCE's demo pays.
REWARD_ML = 0.05
#: The codes read here, `tasks/allocation.py`'s as the pop-out strobes them: the odd one held, the
#: reward commanded, the error's blank begun, the answer's saccade begun.
OUTCOME_CORRECT, REWARD_COMMANDED, TIMEOUT_ON, SACCADE_ONSET = 4110, 4102, 4138, 4098
#: The session's frames a second (`service.FRAME_PERIOD`), and the pop-out's bound on landing, the
#: `flight` state's `After(0.3)`, in them.
HZ = 240
LANDING_FRAMES = round(0.3 * HZ)
#: When a trial's saccade detector first reports, from its first frame: its warm-up's velocities,
#: and the two samples ahead of each the five-point window reads (`saccade.HALF_WINDOW`).
WARM_S = (Params().warmup_samples + HALF_WINDOW) / HZ


# --- Who plays each outcome ------------------------------------------------------------------


class Correct(Person):
    """Fixates, and at the go looks to the odd disc and stays."""

    def go(self, drawn):
        return (*target(drawn), False)


class Early(Person):
    """Fixates, and leaves the fixation point before the go: two reports on it, then away."""

    def holding(self):
        return (*(FIX if self.since_fix <= 2 else REST), False)


class WrongDisc(Person):
    """At the go, looks to a distractor."""

    def go(self, drawn):
        return (*distractor(drawn), False)


class EmptySpace(Person):
    """At the go, looks to a place no disc is, and stays."""

    def go(self, drawn):
        return (*empty_space(drawn), False)


class SecondLook(Person):
    """At the go, looks short of the odd disc, 4° out on the line to it, outside the fixation
    window and the disc's, stops there, then looks on to the odd disc: a second look, which counts
    wherever it goes. **Its stop is timed, not left to the schedule** (the build's re-review, N7):
    the look short is sent 50 ms after the go's first report and the look on 200 ms after it
    (`next_in`), so the move short, eased over its 50 ms gap and `pointer.EASE_SLACK_S`, lands 75
    ms on and **the pointer stops there 125 ms**: at least 75 ms with either report 50 ms late, well
    clear of the 50 ms or less that can merge two moves into one saccade, and the second look begins
    about 220 ms into the flight, inside the pop-out's 0.3 s landing bound. On the schedule, the
    stop was 75 ms less twice a late report's lateness, and three reports short (300 ms) reach that
    bound before the second look is seen (probed in process, 2026-11-16: 44 of 216 runs across
    0-50 ms of lateness, against 0 of 216 so)."""

    def go(self, drawn):
        if self.since_go == 1:
            return (*FIX, False)
        return (*(toward_target(drawn, 4.0) if self.since_go == 2 else target(drawn)), False)

    def next_in(self):
        return {1: 0.05, 2: 0.2}.get(self.since_go)


class TargetBreak(Person):
    """At the go, looks to the odd disc, and leaves it after two reports there."""

    def go(self, drawn):
        return (*(target(drawn) if self.since_go <= 2 else REST), False)


class NoResponse(Person):
    """Fixates, and stays where the fixation point was after the go."""

    def go(self, drawn):
        return (*FIX, False)


class NoFixation(Person):
    """Never looks to the fixation point."""

    def aim(self):
        return (*REST, False)


class TrackerLoss(Person):
    """Fixates, then holds B, which the source reads as tracker loss (demo mode §3.3)."""

    def holding(self):
        return (*FIX, self.since_fix > 2)

    def go(self, drawn):
        return (*FIX, True)


#: The states each trial passes through, as far as the answer (`_demo.ANSWERED_STATES`).
FIXATED = ("between", "await_fix", "hold_fix")
ANSWERED = (*FIXATED, "delay", "go", "flight")

#: **Each outcome**: who plays it, the values its run takes over `SHORT`, the states its trial
#: passes through, and the trial line's outcome. The long hold (1.0 s, inside `target_hold`'s
#: 0.05-1.0) and the drawn fixation hold leave a scripted hand's leaving inside them; the short
#: waits (`response_deadline` at 0.2 of 0.1-3.0, `fix_acquisition` at its lowest, 0.5) end a trial
#: that waits on nothing.
CASES = {
    "correct": (Correct, {}, (*ANSWERED, "on_target"), Outcome.CORRECT),
    "early saccade": (Early, {}, (*FIXATED, "early"), Outcome.FIXATION_BREAK),
    "wrong disc": (WrongDisc, {}, (*ANSWERED, "wrong"), Outcome.WRONG_TARGET),
    "empty space": (EmptySpace, {}, (*ANSWERED, "astray"), Outcome.ABORT),
    "second look": (SecondLook, {}, (*ANSWERED, "astray"), Outcome.ABORT),
    "target break": (TargetBreak, {"target_hold": 1.0}, (*ANSWERED, "on_target", "broke"),
                     Outcome.TARGET_BREAK),
    "no response": (NoResponse, {"response_deadline": 0.2}, (*FIXATED, "delay", "go"),
                    Outcome.NO_RESPONSE),
    "no fixation": (NoFixation, {"fix_acquisition": 0.5}, ("between", "await_fix"),
                    Outcome.NO_FIXATION),
    "tracker loss by B": (TrackerLoss, {}, FIXATED, Outcome.TRACKER_LOST),
}
#: The outcomes that end on the error's blank (`TIMEOUT_ON`), each the pop-out's error.
TIMED_OUT = {Outcome.FIXATION_BREAK, Outcome.WRONG_TARGET, Outcome.ABORT, Outcome.TARGET_BREAK}


@pytest.fixture
def began(monkeypatch) -> list:
    """**Each state the rig's world was told began**, `(trial, state, frame)`, as the trial loop
    tells it (`run.World.began`), read on the service's thread: what the rig made of the pointer,
    seen without changing it."""
    told: list = []
    real = pointer.Pointing.began

    def spy(world, state, frame):
        told.append((world.index, state, frame))
        return real(world, state, frame)

    monkeypatch.setattr(pointer.Pointing, "began", spy)
    return told


@pytest.mark.parametrize("case", list(CASES))
def test_the_popout_by_a_scripted_pointer_records_each_outcome(case, tmp_path, zmq_cleanup,
                                                               began):
    """§9: a plain run of one trial of the pop-out, four discs to start, played by a scripted
    pointer over the gaze endpoint, reading the rig's `Drawn` for where the discs are; the trial
    line records its outcome, scored by the rig's own eye rules (`gaze.Tracked`, under
    `pointer.Pointing`), through the states the person's play should take it. Only the correct one
    is paid, on the simulated pump; each error ends on its blank; a look to empty space ends on the
    landing bound and a second look before it, which is what tells the two aborts apart; and the
    record and every frame say demo."""
    assert SHORT["inter_trial"] > WARM_S, "the answer would come before a saccade can be seen"
    who, values, states, outcome = CASES[case]
    person = who()
    with Demo(tmp_path, person, zmq_cleanup) as demo:
        demo.open()
        demo.start({**SHORT, **values})
        ended = demo.ended_run()
        session = demo.service.session
        demo.end()

    (line,) = demo.rows("trials.jsonl")
    assert line["outcome"] == outcome.value, (case, line)
    assert tuple(state for _, state, _ in began) == states
    entered = {state: frame for _, state, frame in began}
    assert person.drawn, "the pointer read no screen"
    assert ended.demo is True
    assert {f.demo for f in demo.frames if isinstance(f, Telemetry)} == {True}
    assert json.loads((demo.record / "config.json").read_text())["demo"]["gaze"] == "mouse"
    codes = session.card.codes
    paid = [REWARD_ML] if outcome is Outcome.CORRECT else []
    assert session.pump.delivered == paid and line["fluid_ml"] == sum(paid)
    assert (OUTCOME_CORRECT in codes, REWARD_COMMANDED in codes) == (bool(paid), bool(paid))
    assert codes.count(TIMEOUT_ON) == (outcome in TIMED_OUT)
    if case == "empty space":
        assert entered["astray"] - entered["flight"] >= LANDING_FRAMES, "on the landing bound"
    if case == "second look":
        assert SACCADE_ONSET in codes
        assert entered["astray"] - entered["flight"] < LANDING_FRAMES, (
            "on the second look's onset, before the landing bound")


class Centered(Person):
    """**At the center from its first report**, where the fixation point will come on, through the
    blank between trials and as the point comes on, never moving before the go; then to the odd
    disc, and stays. `before_go` counts its reports before the go."""

    def __init__(self) -> None:
        super().__init__()
        self.before_go = 0

    def aim(self):
        if self.go_drawn is None and not self.ended:
            self.before_go += 1
            return (*FIX, False)
        return super().aim()

    def go(self, drawn):
        return (*target(drawn), False)


def test_a_pointer_already_at_the_center_as_the_fixation_point_comes_on_has_entered_it(
        tmp_path, zmq_cleanup, began):
    """**The PI's try-out, 2026-11-16**, through the path he found it on: "if i already have the
    "gaze" near the center when the fixation dot appears, i have to leave the window and reenter to
    start the trial. If I am already at the center, i shouldn't have to leave and reenter". A
    pointer resting at the center from before the trial began, across the boundary from `between`
    to `await_fix`, has entered the fixation window on `await_fix`'s first frame, and the trial goes
    on to the discs without the pointer moving. Until then it ended `NO_FIXATION` (decisions.md
    EYE-30)."""
    person = Centered()
    with Demo(tmp_path, person, zmq_cleanup) as demo:
        demo.open()
        demo.start({**SHORT, "fix_acquisition": 0.5})
        demo.ended_run()
        demo.end()

    (line,) = demo.rows("trials.jsonl")
    assert line["outcome"] == Outcome.CORRECT.value, line
    assert tuple(state for _, state, _ in began) == (*ANSWERED, "on_target")
    entered = {state: frame for _, state, frame in began}
    assert entered["hold_fix"] == entered["await_fix"] + 1, "entered on await_fix's first frame"
    assert person.before_go > 0 and person.go_drawn is not None


# --- A catch, by the pointer (the pop-out revision's §4) ---------------------------------------

#: A catch's codes, `tasks/allocation.py`'s: its hold kept, and its outcome's reason.
CATCH_FIXATION_HELD, OUTCOME_CORRECT_REJECT = 4140, 4123


class Holds(Person):
    """Fixates, and from the go keeps looking at the fixation point: on a catch, the right answer.
    **A catch's go is the frame its discs are first drawn**, read from the screen's items, since a
    catch scores no disc and so has no disc windows for `Person` to read (`_demo.discs`).
    `discs_seen` keeps each go screen's drawn discs and their windows flagged the target."""

    def __init__(self) -> None:
        super().__init__()
        self.discs_seen: list = []

    def seen(self, drawn) -> None:
        super().seen(drawn)
        if self.go_drawn is None and not self.ended and any(
                name.startswith("search.") for name in shown_names(drawn)):
            self.go_drawn = drawn

    def go(self, drawn):
        if self.since_go == 1:
            items = sorted(name for name in shown_names(drawn) if name.startswith("search."))
            self.discs_seen.append((items, [w.name for w in drawn.windows if w.target]))
        return (*FIX, False)


def test_a_catch_played_with_the_mouse_is_held_for_its_reward(tmp_path, zmq_cleanup, began):
    """The pop-out revision's §4, through the path the PI plays it on: **a run of target-absent
    catches only**, its share at 100, a scripted pointer over the gaze endpoint that fixates and
    keeps looking at the fixation point after the go. The discs it reads are all distractors, none
    flagged the target; the trial passes the delay and the go, and holding `catch_hold` is a correct
    reject, paid the task's own reward once on the simulated pump, its hold, its reason and the
    reward's command strobed; its line names its kind and says it stepped nothing."""
    person = Holds()
    with Demo(tmp_path, person, zmq_cleanup) as demo:
        demo.open()
        demo.start({**SHORT, "target_absent_percent": 100})
        demo.ended_run()
        session = demo.service.session
        demo.end()

    (line,) = demo.rows("trials.jsonl")
    assert (line["trial_kind"], line["outcome"]) == ("target_absent",
                                                     Outcome.CORRECT_REJECT.value), line
    assert line["stepped"] in (None, False)
    assert tuple(state for _, state, _ in began) == (*FIXATED, "delay", "go")
    assert person.discs_seen, "the pointer read no go screen"
    items, flagged = person.discs_seen[0]
    assert len(items) == line["params"]["set_size"] and flagged == [], person.discs_seen[0]
    assert session.pump.delivered == [REWARD_ML] and line["fluid_ml"] == REWARD_ML
    codes = session.card.codes
    at = codes.index(CATCH_FIXATION_HELD)
    assert codes[at:at + 3] == [CATCH_FIXATION_HELD, OUTCOME_CORRECT_REJECT, REWARD_COMMANDED]
    assert TIMEOUT_ON not in codes


# --- A suggestion answered from the trainer's panel ------------------------------------------


class _Contexts:
    """`zmq_cleanup`'s release for a module's fixture: each socket's context, destroyed when the
    module's tests are done, pass or fail."""

    def __init__(self) -> None:
        self.contexts: list = []

    def __call__(self, made):
        self.contexts.append(made._ctx)
        return made

    def release(self) -> None:
        for context in self.contexts:
            context.destroy(linger=0)


#: How long the trainer waits for the rig's suggestion, and then for the run to reach Fade-in: five
#: times the handful of trials either takes (five answers to the bar, a trial or two to the move),
#: so a slow computer is waited for. A run that gives neither in time is stopped there, and the
#: tests below say what is missing.
SUGGESTION_WITHIN_S = 20.0


@pytest.fixture(scope="module")
def answered(tmp_path_factory):
    """**A run of the plan `training` from Alone, the bar read over its last 5 answers**, a scripted
    person right on every trial: the trainer's panel confirms the rig's first suggestion to move up
    as it stands on a frame, by its id over REP (`next_block`, as the panel's *Move up* sends it),
    and stops the run once a frame says the run is in Fade-in, or once either is waited for past
    `SUGGESTION_WITHIN_S`. The demo, its session (for the simulated card's codes), and the
    suggestion answered or `None`: what is missing is the tests' to say, not this fixture's."""
    register = _Contexts()
    try:
        with Demo(tmp_path_factory.mktemp("answered"), Correct(), register) as demo:
            demo.open()
            demo.start({**SHORT, "move_up_window": 5}, plan="training", start_block="Alone")
            suggested = demo.first(
                lambda f: isinstance(f, Telemetry) and f.suggestion is not None
                and f.suggestion.move == "up", SUGGESTION_WITHIN_S)
            if suggested is not None:
                demo.send(NextBlock(by=BY, suggestion=suggested.suggestion.change))
                demo.first(lambda f: isinstance(f, Telemetry) and f.block == "Fade-in",
                           SUGGESTION_WITHIN_S)
            demo.send(Stop(by=BY))
            demo.ended_run()
            session = demo.service.session
            demo.end()
        yield demo, session, None if suggested is None else suggested.suggestion
    finally:
        register.release()


def test_a_suggestion_answered_from_the_trainers_panel_moves_the_stage(answered):
    """§9, "a suggestion answered from the trainer's panel": the rig suggests Fade-in once 4 of
    the last 5 answers in Alone are right, and the panel's confirmation, naming the suggestion,
    moves the run there at the boundary it reaches: the `suggested` row the rig wrote, the
    `next_block` control naming it, by the person who sent it, and the trial lines' stage
    switching there, Fade-in's four discs from its first trial."""
    demo, session, suggestion = answered
    assert suggestion is not None, "the rig suggested no move up"
    lines = demo.rows("trials.jsonl")
    changes = demo.rows("parameter_changes.jsonl")
    controls = demo.rows("controls.jsonl")

    (row,) = [r for r in changes if r["kind"] == "suggested" and r["change"] == suggestion.change]
    assert (row["move"], row["block"], row["was"], row["now"]) == (
        "up", "Alone", "Alone", "Fade-in")
    assert row["bar"]["of"] == 5 and row["bar"]["correct"] >= 4
    assert (suggestion.block, suggestion.to, suggestion.of) == ("Alone", "Fade-in", 5)
    (move,) = [c for c in controls if c["kind"] == "next_block"]
    assert move["suggestion"] == suggestion.change
    assert move["by"] == {"kind": "box", "name": "jake"}

    blocks = [line["block"] for line in lines]
    switch = blocks.index("Fade-in")
    assert set(blocks[:switch]) == {"Alone"} and set(blocks[switch:]) == {"Fade-in"}
    assert lines[switch]["index"] == move["trial_index"], "it moved where the confirmation reached"
    assert all(line["outcome"] == "correct" for line in lines), [line["outcome"] for line in lines]
    assert all(line["params"]["set_size"] == 1 for line in lines[:switch])
    assert all(line["params"]["set_size"] == 4 for line in lines[switch:])
    assert session.pump.delivered == [REWARD_ML] * len(lines)


def test_a_demo_record_reads_back_through_wl_preproc(answered):
    """The path, not the piece: the demo's record, read by wl-preproc's own code -- its trial lines,
    runs, session and change rows -- with no problem at all, its `config.json`'s `demo` key among
    what it reads without complaint (Task 1's ask, accepted as named on 2026-11-14); and the
    simulated card's strobed stream decoded and assembled into
    one trial per trial line, each ending on its outcome's marker."""
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
    demo, session, _ = answered
    folder = demo.record.parent
    lines = demo.rows("trials.jsonl")
    changes = demo.rows("parameter_changes.jsonl")

    trials = read_rig_trials(folder, "REFERENCE")
    runs = read_rig_runs(folder, "REFERENCE")
    rig = read_rig_session(folder, "REFERENCE")
    records = read_rig_records(folder)
    fields, problems = change_fields([json.dumps(row) for row in changes])

    assert (trials.problems, runs.problems, rig.problems, records.problems,
            problems) == ((), (), (), (), [])
    assert rig.of_this_session and rig.kind == "training"
    assert [(t.number, t.block, t.outcome) for t in trials.trials] == [
        (line["trial_number"], line["block"], line["outcome"]) for line in lines]
    (run,) = runs.runs
    assert (run.plan, run.stop_kind, run.presentations) == ("training", "operator", len(lines))
    assert [c.kind for c in records.controls].count("next_block") == 1

    events = their_events.decode_stream([(i * 0.001, w) for i, w in enumerate(session.card.codes)])
    assembly = assemble(events)
    assert assembly.errors == []
    assert [t.trial_id for t in assembly.trials] == [line["trial_number"] for line in lines]
    for trial, line in zip(assembly.trials, lines):
        marker = their_events.Marker(session.allocation.outcomes[Outcome(line["outcome"])])
        assert trial.outcome == marker.name.removeprefix("TRIAL_").lower(), line

