"""The fixation point's two looks, in the engine (the pop-out revision's design §2; its plan's
Task 5; decisions.md TSK-79).

The PI, 2026-11-16, for every task: "we should have a fix color that indicates that the monkey
should be looking at fixation, eg, a gray fix dot. then when the monkey should "act" (or in the
case of a catch, maintain fix), the fix dot changes in some way, eg, changes color or shape or
hollows out." So the fixation point has a *hold* look and an *act* look, each a setting, and stays
on when the stimuli appear.

Two things in the engine follow. **A setting's start may be one of its choices** (`Param.start`;
XC-517, the other half of XC-420): a look setting starts at a look, and a run, the record (REC-27's
form), the pre-flight and the card take that start as they take a choice set live. **A task that
hides its fixation point at its go is warned at load** (`fixation-hidden-at-go`, the builder's call
the design §2 leaves him), accepted in every kind: the lab's rule is that its look changes instead.

Engine test material, run only in the simulator: no number here is a timing claim about the rig.
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest

import _sessions
from _rig import DIRECT
from wl_xcon import preflight
from wl_xcon.actor import Box
from wl_xcon.check import FIXATION_HIDDEN_AT_GO, check_task
from wl_xcon.cli import _load_allocation, _load_task
from wl_xcon.dio import Simulated as Card
from wl_xcon.findings import SESSION_KINDS
from wl_xcon.link import ParamRow, Revert, Simulated
from wl_xcon.photometry import SRGB, Gray
from wl_xcon.record import _written
from wl_xcon.run import Scripted
from wl_xcon.task import (
    REMEMBERED, SPENT, After, Annulus, Array, Choice, Counting, Disc, Entered, Exited, Hide, Hold,
    Mark, ObjectWindows, On, Outcome, P, Param, ReactionTime, Reward, SaccadeOnset, SaccadeTo,
    Show, Square, State, Stimulus, Task, Trial, Update, Window,
)
from wl_xcon.taskd import Session, SessionSpec
from wl_xcon.welfare import Deployment, Simulated as Pump

WALL_NOW = 1_700_000_000.0
ALLOCATION = _load_allocation(Path("tasks/allocation.py"))
#: The reference tasks, by file: none hides its fixation point at its go (read 2026-11-16).
REFERENCE = ("adaptive_detection", "calibration", "fixation_detection", "visual_search",
             "visual_search_training")
JAKE = Box("jake")

#: Two looks of one fixation point, its hold look and its act look ("Hollows out": a filled gray
#: dot becomes a gray ring of the same size), and a third it does not offer.
HOLD_LOOK = Disc(size=0.3, color=Gray(40.0))
ACT_LOOK = Annulus(inner=0.15, outer=0.3, color=Gray(40.0))
NOT_OFFERED = Square(size=0.3, color=Gray(40.0))


# --- A setting's start may be one of its choices ----------------------------------------------


def test_a_choice_setting_starts_at_one_of_its_choices_and_nothing_else():
    """`Param.start` takes a number, as before, or a value equal to one of the setting's choices
    -- the very choice, or one equal to it -- and is refused as the setting is built otherwise:
    a look it does not offer, a number on a setting of looks, a number its numeric choices do not
    hold, and a look on a setting with no choices, each with a sentence naming the setting."""
    looks = (HOLD_LOOK, ACT_LOOK)
    assert Param("fix_look", unit="appearance", choices=looks, start=HOLD_LOOK).start is HOLD_LOOK
    equal = Param("fix_look", unit="appearance", choices=looks,
                  start=Annulus(inner=0.15, outer=0.3, color=Gray(40.0)))
    assert equal.start == ACT_LOOK
    assert Param("fix_look", unit="appearance", choices=looks).start is None
    assert Param("gap", unit="s", choices=(0.5, 1.0), start=1.0).start == 1.0

    for start in (NOT_OFFERED, 0.3):
        with pytest.raises(ValueError, match=(
                r"'fix_look': a task's starting value is a number, or one of its choices; "
                r".* is not one of the 2 choices it offers")):
            Param("fix_look", unit="appearance", choices=looks, start=start)
    with pytest.raises(ValueError, match=r"'gap'.*0\.7 is not one of the 2 choices it offers"):
        Param("gap", unit="s", choices=(0.5, 1.0), start=0.7)
    with pytest.raises(ValueError, match=r"'fix_hold'.*starting value is a number"):
        Param("fix_hold", unit="s", low=0.05, high=2.0, start=HOLD_LOOK)


# --- A run, the record, the pre-flight and the card take a look's start -------------------------

#: `fixation_detection`'s target appearance, given a start: its disc, the first of its choices.
STARTED = ('            choices=(\n'
           '                Disc(size=1.0, color=Gray(P("target_luminance"))),\n'
           '                Square(size=1.0, color=Gray(P("target_luminance"))),\n'
           '            ),\n')


def _started_task(folder: Path) -> Path:
    """`fixation_detection` with `target_appearance` starting at its disc, as `NAME.py`."""
    text = Path("tasks/fixation_detection.py").read_text()
    assert STARTED in text, "fixation_detection's target appearance moved; update STARTED"
    text = text.replace(STARTED, STARTED + '            start=Disc(size=1.0, color=Gray('
                                           'P("target_luminance"))),\n', 1)
    path = Path(folder) / "started.py"
    path.write_text(text)
    return path


class _Drained(Simulated):
    """A link that runs `script[n]` as the `n`th drain begins -- each a command queued, or a
    callable given the session, a value set live through `Session.set` as every path sets one --
    and keeps each running drain's cards. A command drained before trial `n` applies from trial
    `n + 1`. Past `BUDGET` drains the session is one that never ends, and fails here by name."""

    BUDGET = 60

    def __init__(self, script):
        super().__init__()
        self.script, self.drains, self.cards = dict(script), 0, {}
        self.session = None

    def drain(self) -> list:
        self.drains += 1
        assert self.drains <= self.BUDGET, (
            f"the session drained {self.drains} times, past the budget of {self.BUDGET}")
        if self.session is not None and self.session.phase == "running":
            self.cards[self.drains] = {row[0]: ParamRow.of(*row)
                                       for row in self.session.parameters}
        for step in self.script.get(self.drains, ()):
            if callable(step):
                step(self.session)
            else:
                self.queue(step)
        return super().drain()


def _nobody(trial, values, index) -> Scripted:
    """No gaze: each trial ends as a missed acquisition."""
    return Scripted({})


def _session(tmp_path, path: Path, link, values: dict, trials: int) -> Session:
    spec = SessionSpec(
        task=str(path), allocation="tasks/allocation.py", root=tmp_path,
        session_id="2027-01-14_01", subject="A", trials=trials, frame_period=1 / 240, seed=3,
        values=values, bounds=_sessions.bounds(), already_delivered_today=0.0,
        deployment=Deployment.RIG_FIXED, geometry=DIRECT, session_kind="training",
        calibration=SRGB)
    session = Session(spec, card=Card(), pump=Pump(), link=link)
    session.wall_clock = lambda: WALL_NOW + session.now()
    session.left_cage(at=WALL_NOW)
    session.head_fixed(at=session.wall_now())
    session.world = _nobody
    link.session = session
    return session


def _rows(session, name: str) -> list[dict]:
    path = session.directory / name
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def test_a_looks_start_runs_records_and_reverts_as_a_choice_set_live(tmp_path):
    """A look setting started at its disc: the pre-flight passes it and starts the run with it;
    each trial line records it in REC-27's form, as it records the square a person sets live
    through `Session.set` before trial 2; the card says it in the rig's words, from the task, as
    it says the square from a person; and a revert to the run's start, drained before trial 4 and
    so from trial 5, hands the setting back to the task, its disc again, recorded as a revert row
    of moment 0 whose `was` is the square and whose `now` is null, as a number handed back is."""
    path = _started_task(tmp_path)
    task = _load_task(path)
    (declared,) = [p for p in task.params if p.name == "target_appearance"]
    disc, square = declared.choices
    assert declared.start == disc

    assert preflight.values(task, {}).result == "pass"
    assert preflight.starting(task, {})["target_appearance"] == disc
    assert not [f for f in check_task(task, ALLOCATION) if f.blocking]

    link = _Drained({2: [lambda session: session.set("target_appearance", square, JAKE)],
                     4: [Revert(change=0, by=JAKE)]})
    session = _session(tmp_path, path, link, values={}, trials=6)

    session.run()

    assert session.refusals == []
    lines = _rows(session, "trials.jsonl")
    assert [line["params"]["target_appearance"] for line in lines] == (
        [_written(disc)] + [_written(square)] * 3 + [_written(disc)] * 2)
    changes = _rows(session, "parameter_changes.jsonl")
    assert [(row["kind"], row["name"], row["trial_number"]) for row in changes] == [
        ("set", "target_appearance", 2), ("revert", "target_appearance", 5)]
    assert (changes[0]["was"], changes[0]["now"]) == (_written(disc), _written(square))
    assert (changes[1]["was"], changes[1]["now"], changes[1]["moment"]) == (
        _written(square), None, 0)

    started, held, reverted = (link.cards[n]["target_appearance"] for n in (2, 3, 6))
    assert (started.source, started.changed, started.value) == ("task", False, None)
    assert started.words is not None and started.words.startswith("Disc")
    assert (held.source, held.changed) == ("person", True)
    assert held.words is not None and held.words.startswith("Square")
    assert (reverted.source, reverted.changed, reverted.words) == ("task", False, started.words)


# --- A task hiding its fixation point at its go is warned ---------------------------------------

#: The pop-out search's shape at wl-xtasks `64929fe` (2026-11-08), copied as a fixture: the
#: fixation point held in `hold_fix`, and at the go, on the edge into `go`, its reaction-time
#: state, the discs shown and the point hidden. Its numbers are this fixture's.
FIX = Stimulus("fix", at=(0.0, 0.0), looks=P("fix_look"))
ARRAY = Stimulus("search", at=(0.0, 0.0), looks=Array(
    n=P("set_size"), radius=8.0, target=0, looks=Disc(size=1.0, color=Gray(40.0)),
    among=Disc(size=1.0, color=Gray(10.0)), phase=P("array_rotation")))


def _timeout(state: str, outcome: Outcome) -> State:
    return State(state, go=[On(After(P("timeout")), outcome)])


def _popout(go: list) -> Task:
    """The pop-out's shape at `64929fe`, its go doing `go` beside showing the discs."""
    search = Trial(
        start="between",
        view="direct",
        counting=Counting(after_stimulus=SPENT, appears="go"),
        windows=[
            Window("fix", at=(0.0, 0.0), radius=P("fix_window"), on="fix"),
            Window("center", at=(0.0, 0.0), radius=P("fix_window"), on=REMEMBERED),
            ObjectWindows(of="search", radius=P("object_window")),
        ],
        params=[
            Param("inter_trial", unit="s", low=0.0, high=10.0, start=1.0),
            Param("fix_acquisition", unit="s", low=0.5, high=10.0, start=2.0),
            Param("fix_hold", unit="s", low=0.05, high=2.0, start=0.5),
            Param("response_deadline", unit="s", low=0.1, high=3.0, start=1.0),
            Param("target_hold", unit="s", low=0.05, high=1.0, start=0.3),
            Param("timeout", unit="s", low=0.0, high=10.0, start=2.0),
            Param("fix_window", unit="deg", low=0.5, high=5.0, start=2.0),
            Param("object_window", unit="deg", low=0.5, high=2.0, start=1.5),
            Param("set_size", unit="objects", low=1, high=12, start=4,
                  why="a stand-in: a ring of 12 at most"),
            Param("array_rotation", unit="deg", low=0.0, high=360.0, start=0.0),
            Param("fix_look", unit="appearance", choices=(HOLD_LOOK, ACT_LOOK), start=HOLD_LOOK),
            Param("fix_act_look", unit="appearance", choices=(HOLD_LOOK, ACT_LOOK),
                  start=ACT_LOOK),
        ],
        states=[
            State("between", go=[On(After(P("inter_trial")), "await_fix")]),
            State("await_fix", enter=[Show(FIX), Mark(4096)], go=[
                On(Entered("fix"), "hold_fix"),
                On(After(P("fix_acquisition")), Outcome.NO_FIXATION, do=[Mark(4100)]),
            ]),
            State("hold_fix", go=[
                On(Hold("fix", P("fix_hold")), "go", do=[*go, Show(ARRAY), Mark(4103)]),
                On(Exited("fix"), "early", do=[Hide("fix"), Mark(4101)]),
                On(After(10.0), Outcome.NO_FIXATION),
            ]),
            State("go", go=[
                On(Exited("center"), "flight", do=[Mark(4098)]),
                On(After(P("response_deadline")), Outcome.NO_RESPONSE),
            ]),
            State("flight", go=[
                On(SaccadeTo("search.target"), "on_target", do=[Mark(4099)]),
                On(SaccadeTo("search.distractor"), "wrong", do=[Hide("search"), Mark(4104)]),
                On(SaccadeOnset(), "astray", do=[Hide("search")]),
                On(After(0.3), "astray", do=[Hide("search")]),
            ]),
            State("on_target", go=[
                On(Hold("search.target", P("target_hold")), Outcome.CORRECT,
                   do=[Mark(4110), Mark(4102), Reward("reward_correct")]),
                On(Exited("search.target"), "broke", do=[Hide("search")]),
                On(After(3.0), Outcome.NO_RESPONSE),
            ]),
            _timeout("early", Outcome.FIXATION_BREAK),
            _timeout("wrong", Outcome.WRONG_TARGET),
            _timeout("astray", Outcome.ABORT),
            _timeout("broke", Outcome.TARGET_BREAK),
        ],
    )
    from wl_xcon.task import NEITHER, NOT_DIFFICULTY, STIMULUS, Meaning

    return Task(
        structures={"search": search},
        default="search",
        reaction_time=ReactionTime(state="go", to=("flight",), note=(
            "from the go to the eye leaving the fixation window")),
        choice=Choice(objects=("search.target", "search.distractor"), by="saccade"),
        meanings={
            "inter_trial": Meaning(NOT_DIFFICULTY, NEITHER, note="the time between trials"),
            "timeout": Meaning(NOT_DIFFICULTY, NEITHER, note="the blank after an error"),
            "fix_look": Meaning(NOT_DIFFICULTY, STIMULUS, note="the hold look"),
            "fix_act_look": Meaning(NOT_DIFFICULTY, STIMULUS, note="the act look"),
        },
    )


def _hidden(task: Task) -> list:
    return [finding for finding in check_task(task, ALLOCATION)
            if finding.code == FIXATION_HIDDEN_AT_GO]


def test_hiding_the_fixation_point_at_the_go_is_warned():
    """The pop-out at `64929fe` hid its fixation point on the edge into its reaction-time state,
    the point a window held the eye on in the state before: a warning at load, accepted in every
    kind, naming the state, the edge's source and the stimulus, and giving the lab's rule since
    2026-11-16. The early saccade's `Hide`, on an edge into no reaction-time state, is not
    warned, nor is the search's `Hide` on a wrong look. Nothing else the task says blocks."""
    task = _popout([Hide("fix")])

    (warned,) = _hidden(task)

    assert not warned.blocking and warned.is_warning
    assert set(warned.accepted_in) == set(SESSION_KINDS)
    assert warned.subjects == ("state 'hold_fix'", "stimulus 'fix'")
    assert warned.detail == (
        "the edge from state 'hold_fix' into 'go', the task's reaction-time state, hides "
        "stimulus 'fix', which window 'fix' held the eye on in 'hold_fix': the lab's rule since "
        "2026-11-16 (TSK-79) is that the fixation point stays on, and its look changes at the go "
        "(an Update of its looks, to its act look), so the go is the point's change, never its "
        "going off")
    assert not [finding for finding in check_task(task, ALLOCATION) if finding.blocking]


def test_a_fixation_point_that_changes_its_look_at_the_go_is_not_warned():
    """The same shape with its point changed to its act look at the go (`Update`) is not warned,
    nor is any reference task, none of which hides one (read 2026-11-16)."""
    assert _hidden(_popout([Update("fix", looks=P("fix_act_look"))])) == []
    assert _hidden(_popout([])) == []
    for name in REFERENCE:
        assert _hidden(_load_task(Path("tasks") / f"{name}.py")) == [], name


def test_a_hide_in_the_reaction_time_states_entry_is_the_go_too():
    """A task that hides its point in the reaction-time state's own entry, rather than on the
    edge into it, hides it at the go all the same: warned, naming the state the eye held it in."""
    task = _popout([])
    search = task.structures["search"]
    states = [dataclasses.replace(state, enter=[Hide("fix")]) if state.name == "go" else state
              for state in search.states]
    task = dataclasses.replace(task, structures={"search": dataclasses.replace(
        search, states=states)})

    (warned,) = _hidden(task)

    assert warned.subjects == ("state 'hold_fix'", "stimulus 'fix'")
