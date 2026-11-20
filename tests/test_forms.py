"""A timing setting switched to drawn on its console card: a person's draw, its *form* (the console
settings design's §3; the PI, 2026-11-16: every timing setting "fixed or drawn", staged until the
next trial like any change).

`link.SetForm` offers a shape and its numbers for a setting in seconds; `Session._form` judges it
beside `_range` and never raises, refusing with a sentence and nothing staged; what it accepts waits
in `Session._pending` and applies at the next boundary (`_apply_staged`) as a `form` change row with
its `PARAM_CHANGED` strobe and `sequence`. From then on each trial draws the setting from it -- over
the block's conditions, its draw and its staircase, as a held value is -- fresh on a repeat (the PI,
"Follow same/fresh"), naming the form row's id; a typed value or a hand-back ends it, and a revert
takes it back with the rest. Engine test material, run only in the simulator: no number here is a
timing claim about the rig.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

import _sessions
from _rig import DIRECT
from wl_xcon import variation
from wl_xcon.actor import Box
from wl_xcon.dio import Simulated as Card
from wl_xcon.link import (
    Drum, HandBack, Revert, SetForm, SetParameter, SetRange, Simulated, Staged, Stop, Telemetry,
)
from wl_xcon.photometry import SRGB
from wl_xcon.run import Scripted
from wl_xcon.task import (
    FRESH, SAME, Block, Condition, Listed, NonAging, SaccadeTo, Staircase, TruncatedNormal, Uniform,
    Weighted,
)
from wl_xcon.taskd import Session, SessionSpec
from wl_xcon.welfare import Deployment, Simulated as Pump

WALL_NOW = 1_700_000_000.0
SEED = 7
JAKE = Box("jake")
BY = {"kind": "box", "name": "jake"}
#: `PARAM_CHANGED`'s code in the reference allocation.
PARAM_CHANGED = 4130
#: The reference task's fixation hold's meaning, as a change row writes it.
FIX_HOLD = {"kind": "clear-cut", "role": "criterion", "raising": "harder", "relative_to": None}
#: The PI's foreperiod as a person's draw: non-aging from 0.75 to 1.25 s, its decay derived.
NONAGING = {"shortest": 0.75, "longest": 1.25}
WAIT = NonAging.between(0.75, 1.25, repeat=FRESH)
#: Where a person's draw of `fix_hold` is keyed (`variation.draw`'s key).
PERSON = ("person", "fix_hold")
BREAK = Scripted({}, inside={frame: "fix" for frame in range(1, 6)})


def _form(shape: str = "non_aging", numbers=None, name: str = "fix_hold", **lists) -> SetForm:
    return SetForm(name=name, shape=shape, numbers=NONAGING if numbers is None else numbers,
                   by=JAKE, **lists)


def _right(values: dict) -> Scripted:
    """A trial the animal gets right whatever its holds, as `test_hand_back_and_ranges`'s."""
    held = round(values["fix_hold"] * 240) + 20
    return Scripted({SaccadeTo("target"): held + 10},
                    inside={frame: "fix" if frame <= held else "target"
                            for frame in range(1, held + 400)})


def _always_right(trial, values, index) -> Scripted:
    return _right(values)


def _spec(tmp_path, task, **over) -> SessionSpec:
    spec = SessionSpec(
        task=str(task), allocation="tasks/allocation.py", root=tmp_path,
        session_id="2027-01-14_01", subject="A", trials=400, frame_period=1 / 240, seed=SEED,
        values={"target_appearance": None}, bounds=_sessions.bounds(),
        already_delivered_today=0.0, deployment=Deployment.RIG_FIXED, geometry=DIRECT,
        session_kind="training", calibration=SRGB,
    )
    for name, value in over.items():
        setattr(spec, name, value)
    return spec


def _session(spec, link, world=_always_right) -> Session:
    session = Session(spec, card=Card(), pump=Pump(), link=link)
    session.wall_clock = lambda: WALL_NOW + session.now()
    session.left_cage(at=WALL_NOW)
    session.head_fixed(at=session.wall_now())
    session.world = world
    link.session = session
    return session


class _Drained(Simulated):
    """A link that queues `script[n]` as the `n`th drain begins (one drain before each trial, so a
    command drained before trial `n` applies from trial `n + 1`), and keeps what the session's
    cards and staircase say at each drain (`seen`). Past `BUDGET` drains the session is one that
    never ends, and fails here by name."""

    BUDGET = 100

    def __init__(self, script):
        super().__init__()
        self.script, self.drains, self.seen, self.session = dict(script), 0, {}, None

    def drain(self) -> list:
        self.drains += 1
        assert self.drains <= self.BUDGET, (
            f"the session drained {self.drains} times, past the budget of {self.BUDGET}")
        if self.session is not None and self.session.phase == "running":
            self.seen[self.drains] = ({row[0]: row for row in self.session.parameters},
                                      self.session.staircase, self.session.staged)
        for command in self.script.get(self.drains, ()):
            self.queue(command)
        return super().drain()


def _rows(session: Session, name: str) -> list[dict]:
    path = session.directory / name
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def _lines(session: Session) -> list[dict]:
    return _rows(session, "trials.jsonl")


def _changes(session: Session) -> list[dict]:
    return _rows(session, "parameter_changes.jsonl")


def _without_instants(row: dict) -> dict:
    return {key: value for key, value in row.items() if key not in ("at", "at_local")}


def _fed(session: Session, *kinds: str) -> list[tuple]:
    return [(kind, by, said) for kind, by, _, said in session.controls if kind in kinds]


def _held(line: dict) -> float:
    return line["params"]["fix_hold"]


def _plain(tmp_path, **over) -> Session:
    """The reference detection task, its fixation hold the task's start, 0.3 s."""
    return _spec(tmp_path, "tasks/fixation_detection.py", **over)


# --- The decay's live numbers ---------------------------------------------------------------


def test_a_nonagings_live_numbers_are_its_shortest_and_longest(tmp_path):
    """A non-aging wait's mean is derived from its two ends (TSK-15's revision), so a range naming
    it is refused, naming the two a person may move; moving the longest derives the decay again,
    the row writing the mean it derived."""
    path = _sessions.varied_task(
        tmp_path, draws='{"fix_hold": NonAging(0.2, 0.3, 0.5, repeat=FRESH)}')
    link = _Drained({2: [SetRange(name="fix_hold", numbers={"mean": 0.35}, by=JAKE),
                         SetRange(name="fix_hold", numbers={"maximum": 0.8}, by=JAKE)]})
    session = _session(_spec(tmp_path, path, trials=4), link)

    session.run()

    assert session.refusals == [("fix_hold", JAKE, (
        "the range of 'fix_hold' is not changed: 'mean' is no number of a NonAging changed live; "
        "its live numbers are minimum, maximum"))]
    (row,) = _changes(session)
    assert row["now"] == variation.recorded(NonAging(0.2, 0.2 + 0.6 / 3, 0.8, repeat=FRESH))


# --- Drawn from the next trial --------------------------------------------------------------


ROOT = Path(__file__).resolve().parents[1]
XTASKS = next((c for c in (ROOT / "wl-xtasks", ROOT.parent / "wl-xtasks")
               if (c / "tasks" / "popout_search.py").is_file()), None)
if XTASKS is None and os.environ.get("WLX_REQUIRE_XTASKS") == "1":  # pragma: no cover - CI's
    raise AssertionError("WLX_REQUIRE_XTASKS=1 but no wl-xtasks checkout holding "
                         "tasks/popout_search.py was found beside or inside this repository")


@pytest.mark.skipif(XTASKS is None, reason="no wl-xtasks checkout holding the pop-out search")
def test_a_timing_setting_switched_to_drawn_is_drawn_from_the_next_trial(tmp_path):
    """The design's §3 on the PI's own task: in a simulated pop-out run, the trainer switches
    `inter_trial` to drawn, non-aging 0.75 to 1.25 s, before trial 1. Trial 1 runs as it was, at the
    task's 1.0 s; from trial 2 every trial draws it fresh from the form, inside its range and not
    all alike, its line naming the form row's id; the row is a `form` row, its `was` the run's
    value, since only the run gave the setting. **The gap between trials, not the fixation hold**,
    since the pop-out revision (its design's §6) draws `fix_hold` itself, non-aging from 0.75 to
    1.25 s, so a person's switch of it no longer starts from a fixed value."""
    link = _Drained({2: [_form(name="inter_trial")], 9: [Stop(by=JAKE)]})
    spec = SessionSpec(
        task=str(XTASKS / "tasks" / "popout_search.py"), allocation="tasks/allocation.py",
        root=tmp_path, session_id="2027-01-14_01", subject="A", trials=1, frame_period=1 / 240,
        seed=SEED, values={}, bounds=_sessions.bounds(), already_delivered_today=0.0,
        deployment=Deployment.RIG_FIXED, geometry=DIRECT, session_kind="training",
        calibration=SRGB, plan="training")
    session = Session(spec, card=Card(), pump=Pump(), link=link)
    session.wall_clock = lambda: WALL_NOW + session.now()
    session.left_cage(at=WALL_NOW)
    session.head_fixed(at=session.wall_now())

    session.run()

    assert session.refusals == []
    lines = _lines(session)
    assert len(lines) >= 6

    def gap(line: dict) -> float:
        return line["params"]["inter_trial"]

    assert [gap(line) for line in lines[:2]] == [1.0, 1.0]
    assert all("inter_trial" not in line["drawn"] for line in lines[:2])
    later = lines[2:]
    assert all(0.75 <= gap(line) <= 1.25 for line in later)
    assert len({gap(line) for line in later}) > 1
    assert [gap(line) for line in later] == [
        variation.draw(WAIT, SEED, line["index"], ("person", "inter_trial")) for line in later]
    (row,) = [row for row in _changes(session) if row["kind"] == "form"]
    assert all(line["drawn"]["inter_trial"] == row["change"] for line in later)
    assert (row["was"], row["now"], row["shape"]) == (1.0, variation.recorded(WAIT), "non_aging")


#: What gives `fix_hold` in the block: its conditions, its own draw, or its staircase.
OVER = {
    "conditions": 'Block("b", [Condition("c", {"fix_hold": 0.4}, target=8)])',
    "draw": ('Block("b", [Condition("c", {}, target=8)], '
             'draws={"fix_hold": Uniform(0.2, 0.4, repeat=FRESH)})'),
    "staircase": ('Block("b", [Condition("c", {}, target=8)], '
                  'staircase=Staircase("fix_hold", (0.2, 0.3, 0.4), start=0))'),
}


@pytest.mark.parametrize("given", sorted(OVER))
def test_a_switch_replaces_the_blocks_conditions_draw_or_staircase_until_handed_back(
        tmp_path, given):
    """Review Focus 1: the trainer switches `fix_hold` to drawn in a block whose conditions set it,
    whose own draw draws it, or whose staircase steps it, then hands it back. From the next trial
    the form wins over each; the card names what it overrides -- the conditions, the block's draw
    in the rig's words, or the staircase held -- and from the trial after the hand-back the block's
    own gives it again, its trials no longer naming the form."""
    path = _sessions.varied_task(tmp_path, plans=f'{{"p": Plan([{OVER[given]}])}}',
                                 name=f"over_{given}")
    path.write_text(path.read_text().replace(
        "from wl_xcon.task import (\n    BY_CONDITIONS,",
        "from wl_xcon.task import (\n    Staircase,\n    BY_CONDITIONS,", 1))
    link = _Drained({2: [_form()], 5: [HandBack(name="fix_hold", by=JAKE)]})
    session = _session(_spec(tmp_path, path, plan="p", trials=8), link)

    session.run()

    assert session.refusals == []
    lines = _lines(session)
    (form, handed) = _changes(session)
    assert (form["kind"], handed["kind"], handed["was"]) == (
        "form", "hand_back", variation.recorded(WAIT))
    assert [line["drawn"].get("fix_hold") for line in lines[2:5]] == [form["change"]] * 3
    assert [_held(line) for line in lines[2:5]] == [
        variation.draw(WAIT, SEED, line["index"], PERSON) for line in lines[2:5]]
    assert all("fix_hold" in line["overridden"] for line in lines[2:5]) == (given == "conditions")
    card, stair, _ = link.seen[4]
    row = card["fix_hold"]
    assert (row[7], row[12]["by"], row[12]["shape"]) == ("form", "person", "non_aging")
    after = lines[5:]
    if given == "conditions":
        assert row[8] == ("c",)
        assert [(_held(line), line["drawn"].get("fix_hold")) for line in after] == [
            (0.4, None)] * len(after)
    elif given == "draw":
        assert row[9] == "uniform from 0.2 s to 0.4 s"
        assert {line["drawn"]["fix_hold"] for line in after} == {"block"}
    else:
        assert stair[0] == "fix_hold" and stair[3] is True, "the staircase is held by the form"
        assert {line["drawn"]["fix_hold"] for line in after} == {"staircase"}
        assert _held(after[0]) in (0.2, 0.3, 0.4)
    assert session._forms == {}


def test_a_typed_value_on_a_drawn_card_holds_it_fixed_and_ends_the_form(tmp_path):
    """The planner's call: a value typed on the card is the switch's *fixed* side, `Session.set`'s
    as ever. Typed over a form, it holds the setting at that value from the next trial and ends
    the form; its row writes `was` null, since a draw gave the setting before it."""
    link = _Drained({2: [_form()], 4: [SetParameter(name="fix_hold", value=0.6, by=JAKE)]})
    session = _session(_plain(tmp_path, trials=6), link)

    session.run()

    assert session.refusals == []
    lines = _lines(session)
    assert [line["drawn"].get("fix_hold") for line in lines] == [None, None, 1, 1, None, None]
    assert [(_held(line), line["live"]) for line in lines[4:]] == [(0.6, ["fix_hold"])] * 2
    form, typed = _changes(session)
    assert (typed["kind"], typed["was"], typed["now"]) == ("set", None, 0.6)
    assert session._forms == {} and session._edited == {"fix_hold"}


def test_a_repeat_draws_a_switched_setting_fresh(tmp_path):
    """The controller's call on the PI's "Follow same/fresh": a person's draw is fresh, so a
    repeat of a trial broken under it draws its own wait, on its own number, even where the task
    declares the setting `same`."""
    path = _sessions.varied_task(
        tmp_path, draws='{"fix_hold": Uniform(0.2, 0.4, repeat=SAME)}')

    def world(trial, values, index):
        return BREAK if index in (2, 4) else _right(values)

    link = _Drained({2: [_form(), Drum(scope="block", by=JAKE)]})
    session = _session(_spec(tmp_path, path, trials=8), link, world=world)

    session.run()

    lines = _lines(session)
    by_index = {line["index"]: line for line in lines}
    repeats = [line for line in lines if line["repeat_of"] is not None and line["index"] > 2]
    assert repeats, "a broken trial was shown again"
    for line in lines[2:]:
        assert _held(line) == variation.draw(WAIT, SEED, line["index"], PERSON)
    assert all(_held(line) != _held(by_index[line["repeat_of"]]) for line in repeats)


# --- Refused, with a sentence ---------------------------------------------------------------


DEGENERATE = [
    (_form(numbers={"shortest": 1.0, "longest": 1.0}),
     "its shortest, 1.0, is not below its longest, 1.0"),
    (_form(numbers={"shortest": 1.25, "longest": 0.75}),
     "its shortest, 1.25, is not below its longest, 0.75"),
    (_form("normal", {"mean": 0.5, "sd": 0.0, "low": 0.3, "high": 0.7}), "sd 0.0, is not above 0"),
    (_form("normal", {"mean": 0.5, "sd": -0.1, "low": 0.3, "high": 0.7}),
     "sd -0.1, is not above 0"),
    (_form("list", {}, values=()), "it has no values"),
    (_form("weights", {}, values=(0.3, 0.5), weights=(1.0,)), "2 value(s) and 1 weight(s)"),
    (_form("weights", {}, values=(0.3, 0.5), weights=(0.0, 0.0)), "its weights are all 0"),
    (_form("weights", {}, values=(0.3, 0.5), weights=(1.0, -1.0)),
     "each is a finite number of 0 or more"),
    (_form("uniform", {"low": 0.5, "high": 0.5}), "gives one value only"),
    (_form(numbers={"low": 0.75, "high": 1.25}),
     "a non_aging draw takes shortest and longest, and was sent high, low"),
    (_form("list", {"low": 0.75}, values=(0.5,)), "a list draw takes no numbers"),
    (_form("uniform", {"low": 0.2, "high": 0.4}, values=(0.3,)), "a uniform draw takes no values"),
    (_form("scaled", {"factor": 0.3}), "a scaling by eccentricity is a size's"),
    (_form("spiky", {}), "'spiky' is not a shape"),
    (_form(name="fix_holdd"), "it is not a setting this task declares"),
    (_form(name="reward_correct"), "it is a welfare ceiling, which is never drawn"),
]


def test_degenerate_shapes_are_refused_with_a_sentence(tmp_path):
    """Review Focus 2: a shortest at or past the longest, an SD at or below 0, an empty list,
    weights of another length, all zero or negative, a draw of one value, numbers its shape does
    not take, a scaling of a timing setting (a size's alone, `tests/test_scaling.py`), a shape there is no
    such, a name the task does not declare and a reward size: each refused with its sentence,
    nothing staged and no row written, the session running on to its last trial. A word among the
    numbers and a list past `link.LISTED_LIMIT` never decode (`tests/test_link.py`)."""
    link = _Drained({2: [command for command, _ in DEGENERATE]})
    session = _session(_plain(tmp_path, trials=4), link)

    session.run()

    assert len(session.refusals) == len(DEGENERATE)
    for (name, by, why), (command, said) in zip(session.refusals, DEGENERATE):
        assert (name, by) == (command.name, JAKE)
        # A scaling is refused as one (the console settings plan's Task 6: a size's alone).
        how = "scaled" if command.shape == "scaled" else "drawn"
        assert why.startswith(f"{command.name!r} is not {how} as asked: "), why
        assert said in why, (said, why)
    assert _changes(session) == [] and session._forms == {}
    assert len(_lines(session)) == 4


def test_a_form_is_judged_at_its_extremes(tmp_path):
    """The design's §3: the load checks judge a drawn timing setting at its extremes, as they judge
    a range. The deadline task's target hold is bounded by its response deadline, 0.6 s, so a
    target hold drawn to 0.9 s leaves trials no time to answer at its longest: refused,
    `impossible-trial`, nothing staged. One whose longest is inside it is accepted."""
    path = _sessions.varied_task(tmp_path, name="deadline")
    path.write_text(path.read_text().replace(
        "                On(After(3.0), Outcome.NO_RESPONSE),",
        '                On(After(P("response_deadline")), Outcome.NO_RESPONSE),', 1))
    link = _Drained({2: [_form("uniform", {"low": 0.1, "high": 0.9}, name="target_hold"),
                         _form("uniform", {"low": 0.1, "high": 0.3}, name="target_hold")]})
    session = _session(_spec(tmp_path, path, trials=4), link)

    session.run()

    ((name, _, why),) = session.refusals
    assert name == "target_hold" and "impossible-trial" in why
    (row,) = _changes(session)
    assert row["now"] == variation.recorded(Uniform(0.1, 0.3, repeat=FRESH))


def test_the_drawn_switch_is_a_timing_settings_alone(tmp_path):
    """Every timing setting gets the switch (the PI, 2026-11-16), and only a timing setting: a
    setting in degrees is refused a drawn form, and its card offers no switch (`switch` None)."""
    link = _Drained({2: [_form("uniform", {"low": 2.0, "high": 4.0}, name="target_window")]})
    session = _session(_plain(tmp_path, trials=3), link)

    session.run()

    ((name, _, why),) = session.refusals
    assert name == "target_window"
    assert "it is in deg, and only a timing setting, in s, is drawn from its card" in why
    card = link.seen[2][0]
    assert (card["fix_hold"][11], card["target_window"][11]) == ("drawn", None)
    assert (card["fix_hold"][12], card["target_window"][12]) == (None, None)


# --- The record ---------------------------------------------------------------------------------


def test_a_form_row_strobes_and_says_what_it_replaced(tmp_path):
    """Task 1's ask (`docs/pending-wl-preproc-amendments.md`, the console settings section): a
    `form` row strobes `PARAM_CHANGED` and carries a `sequence`; `now` is the form as the record
    writes a draw, `repeat` `"fresh"`; `detail` its `shape`; and `was` the rule every row's
    follows: the run's value where only the run gave it, the person's value where one was held,
    the earlier form where one stood. A typed value between them writes `was` null over the form.
    The block's end says the form varied the setting, by the row's id."""
    second = Uniform(0.4, 0.6, repeat=FRESH)
    third = Listed((0.5, 0.7, 0.9), repeat=FRESH)
    link = _Drained({2: [_form()],
                     4: [SetParameter(name="fix_hold", value=0.5, by=JAKE)],
                     6: [_form("uniform", {"low": 0.4, "high": 0.6})],
                     8: [_form("list", {}, values=(0.5, 0.7, 0.9))]})
    session = _session(_plain(tmp_path, trials=10), link)

    session.run()

    assert session.refusals == []
    rows = _changes(session)
    meaning = {**FIX_HOLD, "went": None, "step": None}
    common = {"name": "fix_hold", "by": BY, "run": 0, "offered": [], "odds": None,
              "event_code": PARAM_CHANGED}
    assert [_without_instants(row) for row in rows if row["kind"] == "form"] == [
        {**common, "change": 1, "kind": "form", "was": 0.3, "now": variation.recorded(WAIT),
         "shape": "non_aging", "trial_number": 3, "meaning": meaning, "sequence": 1},
        {**common, "change": 3, "kind": "form", "was": 0.5, "now": variation.recorded(second),
         "shape": "uniform", "trial_number": 7, "meaning": meaning, "sequence": 3},
        {**common, "change": 4, "kind": "form", "was": variation.recorded(second),
         "now": variation.recorded(third), "shape": "list", "trial_number": 9, "meaning": meaning,
         "sequence": 4},
    ]
    assert rows[1]["was"] is None and rows[1]["kind"] == "set"
    assert session.card.codes.count(PARAM_CHANGED) == 4
    assert [line["drawn"].get("fix_hold") for line in _lines(session)] == [
        None, None, 1, 1, None, None, 3, 3, 4, 4]
    assert sorted(_held(line) for line in _lines(session)[8:]) in (
        [0.5, 0.7], [0.5, 0.9], [0.7, 0.9])
    assert _fed(session, "form")[0] == (
        "form", JAKE, "fix_hold 0.30 → drawn: non-aging from 0.75 s to 1.25 s (τ 0.1667 s, 1 in "
                      "20 drawn again, mean 0.8905 s), from trial 2")
    (end,) = next(row for row in _rows(session, "runs.jsonl")
                  if row["event"] == "end")["block_ends"]
    assert [way for way in end["varied"]["fix_hold"] if way["by"] == "draw"] == [
        {"by": "draw", "from": 1, "distribution": variation.recorded(WAIT)},
        {"by": "draw", "from": 3, "distribution": variation.recorded(second)},
        {"by": "draw", "from": 4, "distribution": variation.recorded(third)}]


def test_a_pending_form_is_listed_as_staged_and_its_card_says_it_is_drawn(tmp_path):
    """Through the frames a console reads (`Telemetry`): a form offered and not yet applied is a
    staged row of kind `form`, its draw in the rig's words and the conditions it will override
    named before it applies; once applied, the card's source is `form`, its switch `drawn` and
    its shape the person's, by name; and the moment kept holds it, for a revert."""
    link = _Drained({2: [_form()]})
    session = _session(_spec(tmp_path, "tasks/fixation_detection.py", trials=4, blocks=[
        Block("b", [Condition("c", {"fix_hold": 0.4}, target=4)])]), link)

    session.run()

    frames = [frame for frame in link.published if isinstance(frame, Telemetry)]
    staged = [row for frame in frames for row in frame.staged]
    assert staged and set(staged) == {Staged(
        name="fix_hold", was=None, now=variation.words(WAIT, "s"), by=JAKE, bounded=False,
        kind="form", overrides=("c",))}
    cards = [row for frame in frames for row in frame.params
             if row.name == "fix_hold" and row.source == "form"]
    assert cards and cards[-1].switch == "drawn" and cards[-1].shape == {
        "shape": "non_aging", "numbers": NONAGING, "values": [], "weights": [], "by": "person"}
    assert session._moments[-1].forms == {"fix_hold": WAIT}


def test_a_revert_takes_a_form_back_with_the_rest(tmp_path):
    """TSK-43 (the PI, 2026-10-07, "Yes, with revert"): a form is part of a moment. A revert to the
    first form's change puts it back over the later one, as a `revert` row naming the moment, its
    `now` the form and its `shape`; a revert to the run's start hands it back, its `now` null, and
    the run's value plays again."""
    second = Uniform(0.4, 0.6, repeat=FRESH)
    link = _Drained({2: [_form()], 4: [_form("uniform", {"low": 0.4, "high": 0.6})],
                     6: [Revert(change=1, by=JAKE)], 8: [Revert(change=0, by=JAKE)]})
    session = _session(_plain(tmp_path, trials=10), link)

    session.run()

    assert session.refusals == []
    rows = [_without_instants(row) for row in _changes(session)]
    assert [(row["change"], row["kind"]) for row in rows] == [
        (1, "form"), (2, "form"), (3, "revert"), (4, "revert")]
    assert (rows[2]["was"], rows[2]["now"], rows[2]["shape"], rows[2]["moment"]) == (
        variation.recorded(second), variation.recorded(WAIT), "non_aging", 1)
    assert (rows[3]["was"], rows[3]["now"], rows[3]["moment"]) == (variation.recorded(WAIT), None,
                                                                    0)
    lines = _lines(session)
    assert [line["drawn"].get("fix_hold") for line in lines] == [
        None, None, 1, 1, 2, 2, 3, 3, None, None]
    assert [_held(line) for line in lines[8:]] == [0.3, 0.3]
    assert session._forms == {}


def test_each_shape_draws_inside_what_it_can_give(tmp_path):
    """Each of the five shapes a card offers is drawn as its distribution is (`variation.draw`),
    keyed by the person: a uniform and a normal from one unit, a list in its shuffled passes, a
    weighted set by its weights."""
    shapes = [(_form("uniform", {"low": 0.4, "high": 0.6}), Uniform(0.4, 0.6, repeat=FRESH)),
              (_form("normal", {"mean": 0.5, "sd": 0.1, "low": 0.3, "high": 0.7}),
               TruncatedNormal(0.5, 0.1, 0.3, 0.7, repeat=FRESH)),
              (_form("weights", {}, values=(0.3, 0.6), weights=(3.0, 1.0)),
               Weighted((0.3, 0.6), (3.0, 1.0), repeat=FRESH))]
    link = _Drained({2: [shapes[0][0]], 4: [shapes[1][0]], 6: [shapes[2][0]]})
    session = _session(_plain(tmp_path, trials=8), link)

    session.run()

    assert session.refusals == []
    lines = _lines(session)
    for (_, drawn), pair in zip(shapes, (lines[2:4], lines[4:6], lines[6:8])):
        assert [_held(line) for line in pair] == [
            variation.draw(drawn, SEED, line["index"], PERSON) for line in pair]


def test_a_resume_reads_a_form_row_back(tmp_path):
    """A session whose change log holds `form` rows is read back by a resume (`resume._changes`
    knows every kind in the commit that writes it), its next change and `sequence` numbered after
    them: `form` strobes, so its row's `sequence` is counted."""
    from wl_xcon import resume

    link = _Drained({2: [_form()], 4: [_form("uniform", {"low": 0.4, "high": 0.6})]})
    session = _session(_plain(tmp_path, trials=6), link)
    session.run()

    restoration = resume.read(session.directory, session.welfare.left_cage_wall_at)

    assert (restoration.change, restoration.sequence) == (2, 2)


# --- Kept out of moving up ----------------------------------------------------------------------


def test_a_draw_reaching_anything_easier_keeps_its_trials_out_of_the_blocks_rule(tmp_path):
    """**A person's draw is judged as a whole, at its extremes** (`Session._form_eases`), against
    what the trial would otherwise have had, here the run's fixation hold, 0.3 s, a longer hold
    harder: uniform from 0.1 to 0.4 s reaches shorter holds, so its every trial is kept out, and
    non-aging from 0.75 to 1.25 s, longer at both ends, keeps none out. Each line names what kept it out (`eased`), and the block's "three right
    in a row" reads only the trials no draw eased: trial 0's, then trials 4 and 5, so it ends after
    trial 5, not trial 2."""
    easier = _form("uniform", {"low": 0.1, "high": 0.4})
    link = _Drained({1: [easier], 4: [_form()]})
    session = _session(_plain(tmp_path, blocks=[
        Block("b", [Condition("c", {}, target=1)], criterion=(1.0, 3))]), link)

    session.run()

    assert session.refusals == []
    lines = _lines(session)
    assert [(line["drawn"].get("fix_hold"), line["eased"]) for line in lines] == [
        (None, []), (1, ["fix_hold"]), (1, ["fix_hold"]), (1, ["fix_hold"]), (2, []), (2, [])]
    (ended,) = [row for row in _rows(session, "runs.jsonl") if row["event"] == "end"]
    assert [(end["block"], end["ended"], end["after_trial"])
            for end in ended["block_ends"]] == [("b", "rule", 5)]


def test_a_draw_over_the_blocks_draw_is_judged_against_the_draw_written(tmp_path):
    """**Where the block draws the setting, a person's draw is judged against that draw as the
    task writes it** (`variation.easier_range`): over the fixation hold drawn uniform from 0.2 to
    0.4 s, uniform from 0.3 to 0.5 s, longer at both ends, keeps nothing out; non-aging, a draw of
    another kind, cannot be read either way, so its trials are kept out on doubt; and uniform from
    0.1 to 0.4 s, its shortest shorter, keeps them out."""
    block = ('Block("b", [Condition("c", {}, target=11)], '
             'draws={"fix_hold": Uniform(0.2, 0.4, repeat=FRESH)})')
    path = _sessions.varied_task(tmp_path, plans=f'{{"p": Plan([{block}])}}', name="over_draw")
    link = _Drained({2: [_form("uniform", {"low": 0.3, "high": 0.5})], 5: [_form()],
                     8: [_form("uniform", {"low": 0.1, "high": 0.4})]})
    session = _session(_spec(tmp_path, path, plan="p", trials=11), link)

    session.run()

    assert session.refusals == []
    out = ["fix_hold"]
    assert [(line["drawn"].get("fix_hold"), line["eased"]) for line in _lines(session)] == (
        [("block", [])] * 2 + [(1, [])] * 3 + [(2, out)] * 3 + [(3, out)] * 3)


@pytest.mark.parametrize("meaning, eased", [
    ("Meaning(EXPECTED, CRITERION, raising=HARDER, note='held as the task expects it', "
     "overrides='read as expected here')", ["fix_hold"]),
    ("Meaning(NOT_DIFFICULTY, CRITERION, note='no harder or easier here', "
     "overrides='read as no difficulty here')", []),
])
def test_a_draw_of_an_expected_setting_keeps_its_trials_out_and_of_no_difficulty_none(
        tmp_path, meaning, eased):
    """**An expected setting's draw keeps its trials out whatever it draws** (the PI, "No, after
    any change"), here non-aging from 0.75 to 1.25 s, which a clear-cut reading of the fixation
    hold would call harder; **a setting that is no difficulty setting keeps none out**, here uniform
    from 0.1 to 0.4 s, which a clear-cut reading would call easier."""
    path = _sessions.varied_task(tmp_path, name="meant")
    path.write_text(path.read_text() + (
        "from wl_xcon.task import CRITERION, EXPECTED, HARDER, NOT_DIFFICULTY, Meaning\n"
        f"TASK = _dataclasses.replace(TASK, meanings={{'fix_hold': {meaning}}})\n"))
    drawn = _form() if eased else _form("uniform", {"low": 0.1, "high": 0.4})
    link = _Drained({2: [drawn]})
    session = _session(_spec(tmp_path, path, trials=4), link)

    session.run()

    assert session.refusals == []
    assert [(line["drawn"].get("fix_hold"), line["eased"]) for line in _lines(session)] == [
        (None, []), (None, []), (1, eased), (1, eased)]
