"""Telemetry schema 19: where each value comes from (engine build C3's spec §6).

The PI's decisions it carries: engine spec §14.7 (TSK-19, 2026-10-07: a live edit to a value a
condition sets wins, and "the console shows which conditions an edit overrides"); and of
2026-10-30, Q7a, "Yes, a 'hand back' button", Q7b, "Yes, range changes live", and revert (TSK-43).
The C3 spec §6: "each setting's card says where its value comes from (task, run, conditions, a draw
and its range, or a person) and which conditions set or draw it. A staged change names the
conditions it will override **before** it applies; today only the applied line on the feed does."
So each `ParamRow` carries its `source`, `conditions`, `draw` and `numbers`; each `Staged` row its
`kind` and `overrides`, a hand-back, a live range and a revert's changes among the rows; and each
frame the run's `moments` a revert can go back to, capped, the run's start always kept. A reader of
18 refuses 19 and 19 refuses 18, by name.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import msgpack
import pytest

import _sessions
from _frames import frame, idle
from _rig import DIRECT
from wl_xcon import link as wire
from wl_xcon.actor import Box
from wl_xcon.dio import Simulated as Card
from wl_xcon.link import (
    CONTROL_HISTORY, SCHEMA, HandBack, ParamRow, Revert, SchemaMismatch, SetParameter, SetRange,
    Simulated, Staged, Stop, decode, encode,
)
from wl_xcon.photometry import SRGB
from wl_xcon.run import Scripted
from wl_xcon.task import FRESH, SAME, Block, Condition, SaccadeTo, Uniform
from wl_xcon.taskd import RunSpec, Session, SessionSpec
from wl_xcon.welfare import Deployment, Simulated as Pump

#: The wall every session here reads from, plus its frames' seconds (`_session`).
WALL_NOW = 1_700_000_000.0
SEED = 7
JAKE = Box("jake")


def _right(values: dict) -> Scripted:
    """A trial the animal gets right, whatever its holds: it holds the fixation point 20 frames
    past its hold, then looks at the target and stays on it 400 frames, past any target hold."""
    held = round(values["fix_hold"] * 240) + 20
    return Scripted({SaccadeTo("target"): held + 10},
                    inside={step: "fix" if step <= held else "target"
                            for step in range(1, held + 400)})


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


def _session(spec, link=None, *, service=False) -> Session:
    """On the simulators, its wall following its frames from `WALL_NOW`, the animal out of its
    cage, its head fixed, and right on every trial; a `wlx taskd` session, opened, where
    `service`."""
    session = Session(spec, card=Card(), pump=Pump(),
                      link=link if link is not None else Simulated(), service=service)
    session.wall_clock = lambda: WALL_NOW + session.now()
    session.left_cage(at=WALL_NOW)
    session.head_fixed(at=session.wall_now())
    session.world = _always_right
    if service:
        session.open(how="wlx taskd")
    return session


class _Watched(Simulated):
    """A link that queues `script[n]` as the `n`th drain begins, and keeps the first frame
    published after it (`seen[n]`). The loop drains once before each trial, and once more as the
    plan moves to another block, and publishes right after: within a block, a command drained in
    the `n`th pass is staged in `seen[n]`, and applied in `seen[n + 1]`, from trial `n`, counting
    from 0."""

    def __init__(self, script):
        super().__init__()
        self.script, self.drains, self.seen = dict(script), 0, {}

    def drain(self) -> list:
        self.drains += 1
        for command in self.script.get(self.drains, ()):
            self.queue(command)
        return super().drain()

    def publish(self, telemetry) -> None:
        super().publish(telemetry)
        self.seen.setdefault(self.drains, telemetry)


def _edited(path: Path, *edits: tuple[str, str], tail: str = "") -> Path:
    """`path` with each `(old, new)` made, each `old` found once, and `tail` appended."""
    text = path.read_text()
    for old, new in edits:
        assert text.count(old) == 1, old
        text = text.replace(old, new)
    path.write_text(text + tail)
    return path


def _sourced(folder: Path) -> Path:
    """`varied_task` with a setting from each source a card can name. The task draws the fixation
    hold, the target window -- declared not live-editable -- its eccentricity from a weighted set,
    and its direction, -45° to 45° in the task's terms; the target is placed by those two
    (`Polar`). Block `b` replaces the fixation hold's draw with its own; its condition `near` sets
    the target's luminance, and `far` draws it from its own range. Block `c`'s condition, also
    named `near`, sets it too. `spare` is a setting nothing reads and nothing gives a value. Engine
    test material, run only in the simulator."""
    return _edited(
        _sessions.varied_task(
            folder, name="sourced",
            draws=('{"fix_hold": Uniform(0.2, 0.4, repeat=FRESH), '
                   '"target_window": Uniform(2.5, 3.5, repeat=FRESH), '
                   '"target_ecc": Weighted((6.0, 8.0), (1, 1), repeat=FRESH), '
                   '"target_dir": Uniform(-45.0, 45.0, repeat=FRESH)}'),
            plans=('{"p": Plan([Block("b", [Condition("near", {"target_luminance": 30.0}, '
                   'target=3), Condition("far", {"target_luminance": Uniform(50.0, 60.0, '
                   'repeat=SAME)}, target=3)], draws={"fix_hold": Uniform(0.5, 0.6, '
                   'repeat=FRESH)}), Block("c", [Condition("near", {"target_luminance": 20.0}, '
                   'target=2)])])}')),
        ("from wl_xcon.photometry import Gray\nfrom wl_xcon.task import (",
         "from wl_xcon.photometry import Gray\nfrom wl_xcon.task import (\n    Polar,"),
        ('"target", at=(P("target_x"), P("target_y")), looks=P("target_appearance")',
         '"target", at=Polar(P("target_ecc"), P("target_dir")), looks=P("target_appearance")'),
        ('            at=(P("target_x"), P("target_y")),\n            radius=P("target_window"),',
         '            at=Polar(P("target_ecc"), P("target_dir")),\n'
         '            radius=P("target_window"),'),
        ('        Param("target_window", unit="deg", low=0.5, high=6.0, start=3.0),',
         '        Param("target_window", unit="deg", low=0.5, high=6.0, start=3.0, live=False),'),
        ('        Param("target_x", unit="deg", low=-16.0, high=16.0, start=10.0),',
         '        Param("target_ecc", unit="deg", low=0.0, high=16.0, start=8.0),\n'
         '        Param("target_dir", unit="deg", low=-180.0, high=180.0, start=0.0),\n'
         '        Param("spare", unit="deg", low=0.0, high=1.0),\n'
         '        Param("target_x", unit="deg", low=-16.0, high=16.0, start=10.0),'),
        tail=("from wl_xcon.task import NEITHER, NOT_DIFFICULTY, STIMULUS, Meaning\n"
              "TASK = _dataclasses.replace(TASK, meanings={\n"
              "    **TASK.meanings,\n"
              "    'target_ecc': Meaning(NOT_DIFFICULTY, STIMULUS, note='how far out'),\n"
              "    'target_dir': Meaning(NOT_DIFFICULTY, STIMULUS, note='which way'),\n"
              "    'spare': Meaning(NOT_DIFFICULTY, NEITHER, note='read by nothing'),\n"
              "})\n"))


def _where(row: ParamRow) -> tuple:
    """Where a card says its value comes from: its four fields of schema 19."""
    return (row.source, row.conditions, row.draw, row.numbers)


def test_each_card_says_where_its_value_comes_from_and_which_conditions_set_or_draw_it(tmp_path):
    """The C3 spec §6: each card's `source` says where its value comes from in the open block --
    `task` (its start), `run` (a value the run was given), `conditions`, `draw` or `person`,
    nothing where nothing gives it -- `conditions` every condition of the run's plan that sets or
    draws it, each once, `draw` the open block's draw of it in the rig's words (its own, else the
    task's; a direction's from 0 to 360) and `numbers` the numbers a person may change live,
    none for a setting declared not live, a direction (XC-445) or a weighted set (XC-443). A
    person's value is the card's source from the trial it applies to, over a draw or the
    conditions, which the card still names; a ceiling's card says nothing of where it comes
    from."""
    link = _Watched({2: [SetParameter(name="fix_window", value=2.5, by=JAKE),
                         SetParameter(name="fix_hold", value=0.55, by=JAKE),
                         SetParameter(name="target_luminance", value=45.0, by=JAKE)]})
    session = _session(_spec(tmp_path, _sourced(tmp_path), plan="p",
                             values={"target_appearance": None, "target_y": 1.5}), link)

    session.run()

    assert session.refusals == []
    before = {row.name: _where(row) for row in link.seen[1].params}
    after = {row.name: _where(row) for row in link.seen[3].params}
    block_draw = ("uniform from 0.5 s to 0.6 s", {"low": 0.5, "high": 0.6})
    assert before == {
        "fix_acquisition": ("task", (), None, None),
        "fix_hold": ("draw", (), *block_draw),
        "response_deadline": ("task", (), None, None),
        "target_hold": ("task", (), None, None),
        "fix_window": ("task", (), None, None),
        "target_window": ("draw", (), "uniform from 2.5 deg to 3.5 deg", None),
        "target_ecc": ("draw", (), "one of 6.0 deg, 8.0 deg, weighted 1:1", None),
        "target_dir": ("draw", (), "uniform from 315.0 deg to 45.0 deg", None),
        "spare": (None, (), None, None),
        "target_x": ("task", (), None, None),
        "target_y": ("run", (), None, None),
        "target_appearance": ("run", (), None, None),
        "fix_luminance": ("task", (), None, None),
        "target_luminance": ("conditions", ("near", "far"), None, None),
        "reward_correct": (None, (), None, None),
    }
    assert {name: where for name, where in after.items() if where != before[name]} == {
        "fix_window": ("person", (), None, None),
        "fix_hold": ("person", (), *block_draw),
        "target_luminance": ("person", ("near", "far"), None, None),
    }


def test_between_runs_no_card_says_where_its_value_comes_from_and_no_moment_is_listed(tmp_path):
    """Between a `wlx taskd` session's runs no block is open, no plan is played and no revert
    reaches back: every card says nothing of where its value comes from, and the frame lists no
    moment, as the open run's fields read none between runs (the engine C2b plan's final review,
    M1). While the run went, the cards said it and the moments were listed."""
    link = _Watched({2: [SetParameter(name="target_x", value=12.0, by=JAKE)]})
    session = _session(_spec(tmp_path, "", trials=0, values={}), link, service=True)
    run = RunSpec(task="tasks/fixation_detection.py", trials=4, seed=SEED,
                  values={"target_appearance": None},
                  blocks=[Block("b", [Condition("near", {"target_x": 5.0}, target=4)])])

    session.run(run)
    session.publish()

    during, between = link.seen[3], link.published[-1]
    assert {row.name: _where(row) for row in during.params}["target_x"] == (
        "person", ("near",), None, None)
    assert [moment.change for moment in during.moments] == [1, 0]
    assert between.phase == "between_runs"
    assert {_where(row) for row in between.params} == {(None, (), None, None)}
    assert (between.moments, between.staged, between.eased) == ((), (), ())


def _ceiling_named(folder: Path) -> Path:
    """`varied_task` declaring a setting named as the reward ceiling is, `reward_correct`, which
    nothing reads, with a meaning, as a task may (`tests/test_live_refusal.py`'s does). Engine
    test material."""
    return _edited(
        _sessions.varied_task(folder, name="ceiling"),
        ('        Param("target_hold", unit="s", low=0.05, high=1.0, start=0.2),',
         '        Param("reward_correct", unit="mL", low=0.0, high=1.0),\n'
         '        Param("target_hold", unit="s", low=0.05, high=1.0, start=0.2),'),
        tail=("from wl_xcon.task import NEITHER, NOT_DIFFICULTY, Meaning\n"
              "TASK = _dataclasses.replace(TASK, meanings={'reward_correct': Meaning(\n"
              "    NOT_DIFFICULTY, NEITHER, note='named as a ceiling is, read by nothing')})\n"))


def test_a_staged_change_names_its_kind_and_the_conditions_it_will_override_before_it_applies(
        tmp_path):
    """The C3 spec §6: "A staged change names the conditions it will override **before** it
    applies". A person's value of a setting the plan's conditions set names them as it is staged,
    kind `set`; one no condition sets names none; and a reward size names none, a ceiling, though
    the task declares a setting of its name that a condition sets. At the next boundary they
    apply, leave the staged rows, and the card names the conditions instead, as the changes
    feed's line does."""
    link = _Watched({2: [SetParameter(name="target_x", value=12.0, by=JAKE),
                         SetParameter(name="fix_hold", value=0.4, by=JAKE),
                         SetParameter(name="reward_correct", value=0.2, by=JAKE)]})
    session = _session(_spec(tmp_path, _ceiling_named(tmp_path), blocks=[
        Block("b", [Condition("near", {"target_x": 5.0, "reward_correct": 0.5}, target=3),
                    Condition("far", {"target_x": 9.0}, target=3)])]), link)

    session.run()

    assert session.refusals == []
    assert link.seen[2].staged == (
        Staged("target_x", 10.0, 12.0, JAKE, False, "set", ("near", "far")),
        Staged("fix_hold", 0.3, 0.4, JAKE, False, "set", ()),
        Staged("reward_correct", 0.15, 0.2, JAKE, True, "set", ()),
    )
    assert link.seen[3].staged == ()
    card = {row.name: row for row in link.seen[3].params}["target_x"]
    assert (card.value, card.source, card.conditions) == (12.0, "person", ("near", "far"))
    assert [said for kind, _, _, said in session.controls if kind == "set"] == [
        "target_x 10.00 → 12.00, from trial 2; until handed back it overrides what conditions "
        "near, far set or draw",
        "fix_hold 0.30 → 0.40, from trial 2",
        "reward_correct 0.15 → 0.20, from trial 2",
    ]


def test_a_staged_hand_back_and_range_are_shown_staged_in_words(tmp_path):
    """The outline review's M-15: a hand-back and a live range wait to apply as a value does, so
    the console shows them staged, in the order offered. A hand-back's `was` is the person's value
    and its `now` the run's own where the run takes the setting back, else `None` (the open block's
    conditions give it again); a range's `was` and `now` are the draw before and after it in the
    rig's words, a second range on the same draw starting where the first ends. Neither overrides
    a condition; a range names the blocks it reaches. Applied, the card says the range in force,
    changed live, and its numbers."""
    path = _sessions.varied_task(tmp_path, draws='{"fix_hold": Uniform(0.2, 0.4, repeat=FRESH)}')
    link = _Watched({2: [SetParameter(name="target_x", value=12.0, by=JAKE),
                         SetParameter(name="target_y", value=2.0, by=JAKE)],
                     4: [HandBack(name="target_x", by=JAKE), HandBack(name="target_y", by=JAKE),
                         SetRange(name="fix_hold", numbers={"low": 0.25}, by=JAKE),
                         SetRange(name="fix_hold", numbers={"high": 0.35}, by=JAKE)]})
    session = _session(_spec(tmp_path, path, blocks=[
        Block("b", [Condition("near", {"target_x": 5.0}, target=6)])]), link)

    session.run()

    assert session.refusals == []
    assert link.seen[4].staged == (
        Staged("target_x", 12.0, None, JAKE, False, "hand_back", (), True),
        Staged("target_y", 2.0, 0.0, JAKE, False, "hand_back", (), True),
        Staged("fix_hold", "uniform from 0.2 s to 0.4 s", "uniform from 0.25 s to 0.4 s", JAKE,
               False, "range", ("b",)),
        Staged("fix_hold", "uniform from 0.25 s to 0.4 s", "uniform from 0.25 s to 0.35 s", JAKE,
               False, "range", ("b",)),
    )
    assert decode(encode(link.seen[4])) == link.seen[4]
    applied = {row.name: _where(row) for row in link.seen[5].params}
    assert link.seen[5].staged == ()
    assert (applied["target_x"], applied["target_y"], applied["fix_hold"]) == (
        ("conditions", ("near",), None, None), ("task", (), None, None),
        ("range", (), "uniform from 0.25 s to 0.35 s", {"low": 0.25, "high": 0.35}))


def test_a_reverts_staged_changes_are_shown_as_one_revert(tmp_path):
    """A revert offers its hand-backs and ranges ahead of its values (Task 14's call): each is a
    staged row of kind `revert`, the range in the rig's words from the one in force to the one
    declared, the value naming the conditions it will override, as a person's value does."""
    path = _sessions.varied_task(tmp_path, draws='{"fix_hold": Uniform(0.2, 0.4, repeat=FRESH)}')
    link = _Watched({2: [SetParameter(name="target_x", value=12.0, by=JAKE)],
                     3: [SetRange(name="fix_hold", numbers={"high": 0.3}, by=JAKE)],
                     4: [HandBack(name="target_x", by=JAKE)],
                     5: [SetParameter(name="target_y", value=2.0, by=JAKE)],
                     6: [Revert(change=1, by=JAKE)]})
    session = _session(_spec(tmp_path, path, blocks=[
        Block("b", [Condition("near", {"target_x": 5.0}, target=8)])]), link)

    session.run()

    assert session.refusals == []
    assert link.seen[6].staged == (
        Staged("target_y", 2.0, 0.0, JAKE, False, "revert", (), True),
        Staged("fix_hold", "uniform from 0.2 s to 0.3 s", "uniform from 0.2 s to 0.4 s", JAKE,
               False, "revert", ()),
        Staged("target_x", 10.0, 12.0, JAKE, False, "revert", ("near",)),
    )


def test_moments_list_the_runs_changes_newest_first_and_keep_its_start_when_capped(tmp_path):
    """The outline review's M-15: the frame lists the run's moments a revert can go back to,
    newest first, at most `CONTROL_HISTORY`, a frame being re-encoded at every boundary, and
    **always the run's start, last**, so a revert to it is offered however many acts came after:
    55 values set in one drain are 55 moments past the start, of which the newest 49 are listed,
    then the start. Each says its act in the changes feed's words, at the instant it was kept."""
    held = [SetParameter(name="fix_hold", value=round(0.3 + step / 100, 2), by=JAKE)
            for step in range(1, 56)]
    link = _Watched({2: held})
    session = _session(_spec(tmp_path, "tasks/fixation_detection.py", blocks=[
        Block("b", [Condition("near", {"target_x": 5.0}, target=4)])]), link)

    session.run()

    start = wire.MomentRow(0, WALL_NOW, "the run's start", ("fix_hold handed back",))
    assert link.seen[2].moments == (start,)
    listed = link.seen[3].moments
    assert len(listed) == CONTROL_HISTORY == 50
    assert [moment.change for moment in listed] == [*range(55, 6, -1), 0]
    assert (listed[0].said, listed[0].changes) == ("fix_hold 0.30 → 0.85", ())
    assert listed[1].changes == ("fix_hold → 0.84",)
    assert listed[-1] == start
    assert [moment.change for moment in session._moments] == list(range(56))
    assert [(moment.change, moment.at, moment.said) for moment in listed[:-1]] == [
        (moment.change, moment.at, moment.said) for moment in session._moments[:6:-1]]


def test_a_reader_of_18_refuses_19_and_19_refuses_18_by_name(monkeypatch):
    """§3's schema rule: a frame of another schema is refused by name, before any other field is
    read (`SchemaMismatch`), both ways round: a reader of 19 refuses an 18 frame, and a console
    still built for 18 refuses a 19 frame rather than show a staged hand-back's `None` as a
    value."""
    sent = frame()

    assert SCHEMA == sent.schema == 19
    with pytest.raises(SchemaMismatch, match="carried schema 18 and this console reads schema 19"):
        decode(encode(replace(sent, schema=18)))
    monkeypatch.setattr(wire, "SCHEMA", 18)
    with pytest.raises(SchemaMismatch, match="carried schema 19 and this console reads schema 18"):
        decode(encode(sent))


def test_a_frame_with_every_new_field_round_trips():
    """ADR-0003's golden round-trip, for each field schema 19 adds: a card's source, conditions,
    draw, numbers and the conditions past those it names, `None` and empty among them; a staged
    row's kind and overrides, a hand-back's `now` of `None` and a range's words; the moments, each
    a `MomentRow` with what a revert to it changes; and the settings keeping trials out of moving
    up -- on a frame, and on an idle frame's closed summary. A tuple stays a tuple and `None` stays
    `None`."""
    sent = frame(
        params=(
            ParamRow("fix_hold", "s", 0.05, 2.0, 0.55, False, None, "person", ("near", "far"),
                     "uniform from 0.5 s to 0.6 s", {"low": 0.5, "high": 0.6}, 3),
            ParamRow("target_dir", "deg", -180.0, 180.0, 0.0, False, None, "range", (),
                     "uniform from 315.0 deg to 45.0 deg", None),
            ParamRow("reward_correct", "mL", 0.0, 0.4, 0.15, True),
        ),
        staged=(
            Staged("target_x", 12.0, None, JAKE, False, "hand_back", (), True),
            Staged("fix_hold", "uniform from 0.2 s to 0.4 s", "uniform from 0.25 s to 0.4 s",
                   JAKE, False, "range", ()),
            Staged("target_y", 0.0, 2.0, JAKE, False, "revert", ("near", "far")),
            Staged("target_y", 2.0, 0.0, JAKE, False, "revert", (), True),
        ),
        moments=(
            wire.MomentRow(3, 1_700_000_030.0, "target_x 12.00 handed back to its conditions"),
            wire.MomentRow(0, 1_700_000_000.0, "the run's start",
                           ("target_y handed back", "fix_hold → 0.30")),
        ),
        eased=("fix_window", "target_luminance"),
    )

    restored = decode(encode(sent))
    closed = decode(encode(idle(closed=sent)))

    assert restored == sent and closed.closed == sent
    held, turned, ceiling = restored.params
    assert (held.conditions, held.numbers, held.more, turned.numbers, turned.more) == (
        ("near", "far"), {"low": 0.5, "high": 0.6}, 3, None, 0)
    assert (ceiling.source, ceiling.conditions, ceiling.draw) == (None, (), None)
    assert [type(row) for row in restored.moments] == [wire.MomentRow, wire.MomentRow]
    assert restored.staged[0].now is None and restored.staged[2].overrides == ("near", "far")
    assert [row.hands_back for row in restored.staged] == [True, False, False, True]
    assert restored.moments[1].changes == ("target_y handed back", "fix_hold → 0.30")
    assert restored.eased == ("fix_window", "target_luminance")


def test_the_applied_feed_line_still_names_the_conditions_it_overrides(tmp_path):
    """TSK-19's revision (the C3 spec §6): the changes feed's line naming the conditions an edit
    overrides stays, now saying it overrides them until handed back (Q7a), a condition that draws
    the setting from its own range among them; a value no condition gives names none."""
    path = _sessions.varied_task(tmp_path)
    link = _Watched({2: [SetParameter(name="target_luminance", value=45.0, by=JAKE),
                         SetParameter(name="fix_hold", value=0.4, by=JAKE)]})
    session = _session(_spec(tmp_path, path, blocks=[
        Block("b", [Condition("far", {"target_luminance": Uniform(50.0, 60.0, repeat=SAME)},
                              target=3)])]), link)

    session.run()

    assert session.refusals == []
    assert [said for kind, _, _, said in session.controls if kind == "set"] == [
        "target_luminance 40.00 → 45.00, from trial 2; until handed back it overrides what "
        "condition far sets or draws",
        "fix_hold 0.30 → 0.40, from trial 2",
    ]


def test_the_frame_says_which_settings_keep_trials_out_of_moving_up_while_they_do(tmp_path):
    """The C3 plan's engineering review, I-2, and its science review, I-4: while a person's change
    keeps trials out of moving up, the frame says which settings do (`eased`), from the trial it
    first keeps out until a hand-back ends it, and again once it is changed again: the console's
    standing line, beside the changes feed's warning said once a block. Between runs, and as the
    next run starts, it says nothing; nor in a run whose block has no rule that moves the animal
    on, as the feed does not, though its trials' lines say `eased`."""
    link = _Watched({2: [SetParameter(name="fix_window", value=3.0, by=JAKE)],
                     5: [HandBack(name="fix_window", by=JAKE)],
                     7: [SetParameter(name="fix_window", value=3.0, by=JAKE)],
                     12: [SetParameter(name="fix_window", value=3.0, by=JAKE)]})
    session = _session(_spec(tmp_path, "", trials=0, values={}), link, service=True)
    values = {"target_appearance": None}
    session.run(RunSpec(task="tasks/fixation_detection.py", trials=9, seed=SEED, values=values,
                        blocks=[Block("b", [Condition("c", {}, target=9)],
                                      criterion=(1.0, 3))]))
    session.publish()
    between = len(link.published)
    session.run(RunSpec(task="tasks/fixation_detection.py", trials=4, seed=SEED, values=values))

    assert session.refusals == []
    assert [link.seen[at].eased for at in range(1, 10)] == (
        [()] * 3 + [("fix_window",)] * 3 + [()] * 2 + [("fix_window",)])
    assert link.published[between - 1].eased == ()
    lines = [json.loads(line)
             for line in (session.directory / "trials.jsonl").read_text().splitlines()]
    assert [line["eased"] for line in lines if line["run"] == 1] == [
        [], [], ["fix_window"], ["fix_window"]]
    assert {frame.eased for frame in link.published[between:]} == {()}


def test_a_range_changed_live_is_marked_on_its_card_and_names_the_blocks_it_reaches(tmp_path):
    """The C3 plan's science review, M-2 and I-4: a range on the task's draw reaches every block of
    the run's plan that uses it, for the rest of the run, a later test block among them; staged, it
    names them, as a value names the conditions it will override. A block with a draw of its own
    is not reached. Applied, the card says its draw is a range a person changed live (`range`),
    where it said `draw`."""
    path = _sessions.varied_task(
        tmp_path, draws='{"fix_hold": Uniform(0.2, 0.4, repeat=FRESH)}', plans=(
            '{"p": Plan([Block("train", [Condition("a", {}, target=4)]), '
            'Block("own", [Condition("b", {}, target=2)], draws={"fix_hold": Uniform(0.5, 0.6, '
            'repeat=FRESH)}), Block("test", [Condition("c", {}, target=2)])])}'))
    link = _Watched({2: [SetRange(name="fix_hold", numbers={"high": 0.3}, by=JAKE)]})
    session = _session(_spec(tmp_path, path, plan="p"), link)

    session.run()

    assert session.refusals == []
    (staged,) = link.seen[2].staged
    assert (staged.kind, staged.overrides) == ("range", ("train", "test"))
    assert [{row.name: row.source for row in link.seen[at].params}["fix_hold"]
            for at in (2, 3)] == ["draw", "range"]


def test_a_card_names_at_most_twenty_conditions_and_counts_the_rest(tmp_path):
    """The C3 plan's engineering review, M-5: a card names every condition of the run's plan that
    sets or draws its setting, and a factorial can make thousands, which a frame re-encoded at
    every boundary would carry each time. A card names the first `CONDITIONS_SHOWN`, 20, an
    engineering default, in the plan's order, and counts the rest (`more`); the wire carries
    both."""
    conditions = [Condition(f"c{at}", {"target_x": float(at % 10)}, target=1)
                  for at in range(25)]
    link = _Watched({2: [Stop(by=JAKE)]})
    session = _session(_spec(tmp_path, "tasks/fixation_detection.py",
                             blocks=[Block("b", conditions)]), link)

    session.run()

    cards = {row.name: row for row in link.seen[1].params}
    assert wire.CONDITIONS_SHOWN == 20
    assert (cards["target_x"].conditions, cards["target_x"].more) == (
        tuple(f"c{at}" for at in range(20)), 5)
    assert (cards["fix_hold"].conditions, cards["fix_hold"].more) == ((), 0)
    assert decode(encode(link.seen[1])) == link.seen[1]
    named = tuple(f"c{at}" for at in range(21))
    assert [ParamRow.of("x", "deg", 0.0, 1.0, 0.5, False, (), "conditions", named[:size]).more
            for size in (20, 21)] == [0, 1]


def test_each_moment_says_what_a_revert_to_it_would_change(tmp_path):
    """The C3 plan's science review, M-1: one mis-tap on the moment list restores many settings
    at once, so each moment the frame lists says what a revert to it would change, from what the
    run will hold once all offered applies, as the revert reads it: each setting a person holds
    now and not then handed back, each draw changed since put back, then each value held then set
    back, in the changes feed's words. Sent, the revert stages exactly those, in that order, and
    once it is offered the moment it goes back to changes nothing more; nor does the latest
    moment, the revert's own, with nothing offered since."""
    path = _sessions.varied_task(tmp_path, draws='{"fix_hold": Uniform(0.2, 0.4, repeat=FRESH)}')
    link = _Watched({2: [SetParameter(name="target_x", value=12.0, by=JAKE)],
                     3: [SetRange(name="fix_hold", numbers={"high": 0.3}, by=JAKE)],
                     4: [HandBack(name="target_x", by=JAKE)],
                     5: [SetParameter(name="target_y", value=2.0, by=JAKE)],
                     6: [Revert(change=1, by=JAKE)]})
    session = _session(_spec(tmp_path, path, blocks=[
        Block("b", [Condition("near", {"target_x": 5.0}, target=8)])]), link)

    session.run()

    assert session.refusals == []
    assert [(moment.change, moment.changes) for moment in link.seen[5].moments] == [
        (3, ("target_y handed back",)),
        (2, ("target_y handed back", "target_x → 12.00")),
        (1, ("target_y handed back", "the task's draw of 'fix_hold' → as declared",
             "target_x → 12.00")),
        (0, ("target_y handed back", "the task's draw of 'fix_hold' → as declared")),
    ]
    assert {moment.change: moment.changes for moment in link.seen[6].moments}[1] == ()
    assert (link.seen[7].moments[0].change, link.seen[7].moments[0].changes) == (5, ())
    assert [row.name for row in link.seen[6].staged] == ["target_y", "fix_hold", "target_x"]


def test_a_staged_row_says_whether_it_hands_a_setting_back_and_a_malformed_one_is_refused():
    """A revert's hand-back to the run's own value and a revert's value look the same by `kind` and
    `now` (`Staged("target_y", 2.0, 0.0, ..., "revert")` for both), yet one ends the person's hold
    and the other keeps it, so each staged row carries `hands_back` (schema 19, fix round 1 of the
    C3 plan's Task 17): it is carried by name, a bool, and a frame without it, or with something
    else, is a `FrameError`, as every field's absence is."""
    sent = frame(staged=(Staged("target_y", 2.0, 0.0, JAKE, False, "revert", (), True),
                         Staged("target_y", 2.0, 0.0, JAKE, False, "revert", ())))

    assert [row.hands_back for row in decode(encode(sent)).staged] == [True, False]
    for broken in ("gone", "yes", 1):
        bad = msgpack.unpackb(encode(sent), raw=False)
        if broken == "gone":
            del bad["staged"][0]["hands_back"]
        else:
            bad["staged"][0]["hands_back"] = broken
        with pytest.raises(wire.FrameError):
            decode(msgpack.packb(bad))


def test_a_conditions_own_range_beats_the_tasks_draw_on_the_card_as_in_the_trial_loop(tmp_path):
    """Fix round 1, minor 2: for blocks given in code, a condition drawing a setting from its own
    range over a setting the task draws wins in the trial loop (`_draw`: the trials' lines say
    `drawn: condition`), so the card says `conditions`, with no draw of the task's and no numbers
    to change (a range sent from it would change a draw no trial takes), and a hand-back is to its
    conditions, not its draw."""
    path = _sessions.varied_task(tmp_path, draws='{"fix_hold": Uniform(0.2, 0.4, repeat=FRESH)}')
    link = _Watched({2: [SetParameter(name="fix_hold", value=0.55, by=JAKE)],
                     4: [HandBack(name="fix_hold", by=JAKE)]})
    session = _session(_spec(tmp_path, path, blocks=[
        Block("b", [Condition("far", {"fix_hold": Uniform(0.5, 0.6, repeat=FRESH)}, target=6)])]),
        link)

    session.run()

    assert session.refusals == []
    lines = [json.loads(line)
             for line in (session.directory / "trials.jsonl").read_text().splitlines()]
    assert [line["drawn"] for line in lines[:2]] == [{"fix_hold": "condition"}] * 2
    card = {row.name: row for row in link.seen[1].params}["fix_hold"]
    assert (card.source, card.conditions, card.draw, card.numbers) == (
        "conditions", ("far",), None, None)
    assert [said for kind, _, _, said in session.controls if kind == "hand_back"] == [
        "fix_hold 0.55 handed back to its conditions, from trial 4"]
