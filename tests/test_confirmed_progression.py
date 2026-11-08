"""A progression that suggests, and a person who confirms (the pop-out search build's Task 4;
its design, `docs/superpowers/specs/2026-11-07-popout-search-design.md` §3.4, approved by the PI
on 2026-11-07).

The PI's answers of 2026-11-07: between stages "Rig suggests, trainer confirms"; the bar, "80%
correct, last 50 trials", judged at the stage's hardest step ("Hardest step reached, 80% there");
back down the same way, "Below 50% of the last 50". The last 50 are answers only (the design's
§3.4, its call, after TSK-33): a trial the staircase's verdict classes as a success or a failure,
never one that moves nothing (no fixation, an early saccade). "At the hardest step": the bar to
move up counts the last answers given with the block's staircase at its last level, an answer at
an easier level neither counting nor breaking the window; a block with no staircase is always at
its hardest (the builder's reading of "80% there", confirmed by the PI on 2026-11-07, asked in the
UI: "Yes: count tries at the top"; a failure at the top steps a one-up staircase down, so a window
every answer had to share would ask for an unbroken run of right answers there). After a hold the
count starts again ("After 50 new tries", the same day).

wl-preproc accepted the record's shapes on 2026-11-07 (`docs/pending-wl-preproc-amendments.md`):
a `suggested` and a `declined` change row, and a confirmation the existing `next_block` or
`back_block` row with the suggested row's id as its `suggestion`. The plan's Review Focus 2: a
suggestion whose bar drops before the trainer answers withdraws itself, and an answer arriving
after is refused with a sentence.

Engine test material, run only in the simulator: the reference search task with a plan of two
stages, the second with a staircase on its set size, as the pop-out search's Crowd has one. Windows
are short (3 to 5 answers) so a run is a few trials; the task's own are 50.
"""

from __future__ import annotations

import json
import os
from dataclasses import replace
from pathlib import Path

import pytest

import _sessions
from _frames import frame
from _preproc import problems_beyond_xc461
from _rig import DIRECT
from wl_xcon import link as wire
from wl_xcon import resume
from wl_xcon.actor import Box
from wl_xcon.cli import _load_task
from wl_xcon.dio import Simulated as Card
from wl_xcon.link import (
    SCHEMA, BackBlock, CommandRefused, Decline, HandBack, NextBlock, SchemaMismatch, SetParameter,
    Simulated, Stop, Suggestion, Training, _command_from, _decode_command, _encode_command, decode,
    encode,
)
from wl_xcon.photometry import SRGB
from wl_xcon.record import KINDS, STROBED
from wl_xcon.review import render_task
from wl_xcon.run import Scripted
from wl_xcon.serve import BadCommand, parse_command
from wl_xcon.task import SaccadeTo
from wl_xcon.taskd import RunSpec, Session, SessionSpec
from wl_xcon.welfare import Deployment, Simulated as Pump

WALL_NOW = 1_700_000_000.0
SEED = 7
JAKE = Box("jake")
#: Jake as a row writes him.
BY = {"kind": "box", "name": "jake"}
FRAMES = 240
SEARCH = "tasks/visual_search.py"
((RED, GREEN, _),) = [p.choices for p in _load_task(Path(SEARCH)).params
                      if p.name == "target_appearance"]
#: `visual_search`'s starting values, its target red among green, six objects where no staircase
#: gives the set size.
VALUES = {**_sessions.SEARCH_VALUES, "target_appearance": RED, "distractor_appearance": GREEN}
#: The pop-out search's order, with short windows: up at 80% of the last 5 answers, back under 50%
#: of the last 4 first answers, each move a person's to confirm.
CONFIRMED = "ByCriterion(fall_back=(0.5, 4), confirm=True)"


def _stage(name: str, criterion=(0.8, 5), staircase: str | None = None, extra: str = "") -> str:
    """A stage's source: one condition, every trial paying it (`EVERY_TRIAL`), its `criterion` the
    up bar, the staircase given, and `extra`, more of its fields as source."""
    stepped = "" if staircase is None else f", staircase={staircase}"
    rule = "" if criterion is None else f", criterion={criterion}"
    return (f'Block("{name}", [Condition("c", {{}}, target=1)], counting=EVERY_TRIAL'
            f'{rule}{stepped}{extra})')


def _task(folder: Path, stages: list[str], order: str = CONFIRMED) -> Path:
    """The reference search task with one plan, `train`, of `stages` in `order`, written into
    `folder` as `search.py`. Engine test material."""
    path = folder / "search.py"
    path.write_text(Path(SEARCH).read_text() + (
        "\n\nimport dataclasses as _dataclasses\n"
        "from wl_xcon.scheduler import EVERY_TRIAL\n"
        "from wl_xcon.task import Block, ByCriterion, Condition, Plan, Staircase\n"
        f"TASK = _dataclasses.replace(TASK, plans={{'train': Plan([{', '.join(stages)}], "
        f"order={order})}})\n"))
    return path


def _trial(kind: str, values: dict) -> Scripted:
    """One `visual_search` trial the animal plays as `kind` says: `right` (`CORRECT`), `wrong`, a
    look at a distractor (`WRONG_TARGET`), `break`, leaving the target before its hold
    (`TARGET_BREAK`), `early`, leaving the fixation point before the array, the go
    (`FIXATION_BREAK`), and `away`, never looking at the fixation point (`NO_FIXATION`)."""
    held = round(values["fix_hold"] * FRAMES) + 20
    target = f"search.{values['target_index']}"
    looks = {frame: "fix" for frame in range(1, held + 1)}
    if kind == "right":
        return Scripted({SaccadeTo("search.target"): held + 10},
                        inside={**looks, **{f: target for f in range(held + 1, held + 400)}})
    if kind == "break":
        return Scripted({SaccadeTo("search.target"): held + 10},
                        inside={**looks, **{f: target for f in range(held + 1, held + 20)}})
    if kind == "wrong":
        return Scripted({SaccadeTo("search.distractor"): held + 10}, inside=looks)
    if kind == "early":
        return Scripted({}, inside={frame: "fix" for frame in range(1, 6)})
    assert kind == "away", kind
    return Scripted({}, inside={})


class _Drained(Simulated):
    """A link that queues `script[n]` as the `n`th drain begins: the loop drains once before each
    trial, so drain `n` comes before the trial numbered `n - 1` from 0, while no block moves on of
    itself (a move on a stage's own rule takes a pass of the loop, which drains again)."""

    def __init__(self, script):
        super().__init__()
        self.script, self.drains = dict(script), 0

    def drain(self) -> list:
        self.drains += 1
        assert self.drains <= 100, "the session is not ending"
        for command in self.script.get(self.drains, ()):
            self.queue(command)
        return super().drain()


def _session(tmp_path, stages: list[str], script: list[str], commands=None, *,
             order: str = CONFIRMED, service: bool = False) -> Session:
    """A run of plan `train` of `stages` on the simulators, its animal playing `script`, the run
    stopped by a person once the script is played, its wall following its frames from
    `WALL_NOW`, the animal out of its cage and its head fixed; with `service`, a `wlx taskd`
    session, opened, whose run `run_plan` starts."""
    path = _task(tmp_path, stages, order)
    spec = SessionSpec(
        task="" if service else str(path), allocation="tasks/allocation.py", root=tmp_path,
        session_id="2027-01-14_01", subject="A", trials=len(script), frame_period=1 / FRAMES,
        seed=SEED, values=dict(VALUES), bounds=_sessions.bounds(), already_delivered_today=0.0,
        deployment=Deployment.RIG_FIXED, geometry=DIRECT, session_kind="training",
        calibration=SRGB, plan=None if service else "train",
    )
    session = Session(spec, card=Card(), pump=Pump(), link=_Drained(commands or {}),
                      service=service)
    session.wall_clock = lambda: WALL_NOW + session.now()
    session.left_cage(at=WALL_NOW)
    session.head_fixed(at=session.wall_now())
    if service:
        session.open(how="wlx taskd")
        session.run_plan = lambda: session.run(RunSpec(
            task=str(path), trials=len(script), seed=SEED, values=dict(VALUES), plan="train"))

    def world(trial, values, index):
        if index == len(script) - 1:
            # The script's last trial: a person's stop, drained at the boundary after it.
            session.link.queue(Stop(by=JAKE))
        return _trial(script[index], values)

    session.world = world
    return session


def _rows(session: Session, name: str) -> list[dict]:
    path = session.directory / name
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def _blocks(session: Session) -> list[str]:
    return [line["block"] for line in _rows(session, "trials.jsonl")]


def _changes(session: Session) -> list[dict]:
    return _rows(session, "parameter_changes.jsonl")


def _suggested(row: dict) -> tuple:
    """A change row as the fields a suggestion and a hold write."""
    return (row["change"], row["kind"], row["name"], row["was"], row["now"], row["by"],
            row["trial_number"], row.get("move"), row.get("block"), row.get("bar"),
            row.get("at_hardest"), row.get("suggestion"), row["event_code"], row["meaning"],
            "sequence" in row)


def _offered(session: Session) -> dict[int, Suggestion | None]:
    """The suggestion each running frame carried, by the trial about to run, the last frame of
    each boundary's."""
    return {f.trial_index: f.suggestion for f in session.link.published if f.phase == "running"}


def _fed(session: Session, kind: str) -> list[str]:
    return [said for fed, _, _, said in session.controls if fed == kind]


def _two_stages(tmp_path, script, commands=None, *, order=CONFIRMED, up=(0.8, 5)) -> Session:
    return _session(tmp_path, [_stage("Alone", up), _stage("Crowd", up)], script, commands,
                    order=order)


def test_a_met_bar_suggests_and_does_not_move(tmp_path):
    """"Rig suggests, trainer confirms": five right of the last five answers meet Alone's bar, and
    the rig suggests moving up to Crowd -- one `suggested` row, from no one, naming the move, the
    stage it was judged in, the bar's numbers and that every trial was at the stage's hardest step
    (Alone has no staircase), strobing nothing -- and does not move: the run stays in Alone however
    long the bar stays met, suggesting once. Each frame from the next boundary carries it, with
    the row's id for the console to answer by, and the changes feed says it."""
    script = ["right"] * 8
    session = _two_stages(tmp_path, script)

    session.run()

    assert _blocks(session) == ["Alone"] * 8
    assert session.blocks_run == ["Alone"]
    assert [_suggested(row) for row in _changes(session)] == [
        (1, "suggested", "block", "Alone", "Crowd", None, 6, "up", "Alone",
         {"correct": 5, "of": 5}, True, None, None, None, False)]
    offered = _offered(session)
    assert [offered[index] for index in range(5)] == [None] * 5
    assert [offered[index] for index in (5, 6, 7)] == [
        Suggestion(change=1, move="up", block="Alone", to="Crowd", correct=5, of=5,
                   at_hardest=True)] * 3
    assert _fed(session, "suggestion") == [
        "the rig suggests moving up from Alone to Crowd: 5 of the last 5 answers at its hardest "
        "step right; confirm with next block, or hold"]


def test_between_runs_no_suggestion_is_offered(tmp_path):
    """A `wlx taskd` session's run stopped with a suggestion standing: between runs no block is
    open to move, so neither the session nor its frame offers it (schema 20's `suggestion`)."""
    session = _session(tmp_path, [_stage("Alone"), _stage("Crowd")], ["right"] * 6,
                       service=True)

    session.run_plan()

    assert [row["kind"] for row in _changes(session)] == ["suggested"]
    assert session.phase == "between_runs" and session.suggestion is None
    session._publish()
    assert session.link.published[-1].phase == "between_runs"
    assert session.link.published[-1].suggestion is None


def test_next_block_after_a_suggestion_moves_and_both_rows_are_logged(tmp_path):
    """A person confirms with the existing next block, naming the suggestion it answers: the run
    moves up as a person's move does, the `suggested` row in the change log and the `next_block`
    row in `controls.jsonl` with who moved it and the suggestion it answered, as wl-preproc
    accepted; the suggestion is gone from the next frame."""
    script = ["right"] * 8
    session = _two_stages(tmp_path, script, {7: [NextBlock(by=JAKE, suggestion=1)]})

    session.run()

    assert session.refusals == []
    assert _blocks(session) == ["Alone"] * 6 + ["Crowd"] * 2
    assert session.blocks_run == ["Alone", "Crowd"]
    assert [(row["kind"], row["change"]) for row in _changes(session)] == [("suggested", 1)]
    (moved,) = [row for row in _rows(session, "controls.jsonl") if row["kind"] == "next_block"]
    assert (moved["by"], moved["block"], moved["to"], moved["suggestion"], moved["event_code"],
            moved["trial_index"]) == (BY, "Alone", "Crowd", 1, None, 6)
    assert _offered(session)[6] is None
    assert _fed(session, "next_block") == [
        "next block: from block Alone to block Crowd, confirming the rig's suggestion 1"]


def test_decline_logs_and_keeps_the_stage(tmp_path):
    """A person holds (`Decline`, the console's Hold): a `declined` row, by them, naming the
    suggestion it answers, and the run stays in Alone. The rig suggests the move again only once
    a fresh window of answers meets the bar (an engineering call: a hold is not asked again on
    the same answers): five more right, a second `suggested` row."""
    script = ["right"] * 12
    session = _two_stages(tmp_path, script, {7: [Decline(suggestion=1, by=JAKE)]})

    session.run()

    assert session.refusals == []
    assert _blocks(session) == ["Alone"] * 12
    assert [_suggested(row) for row in _changes(session)] == [
        (1, "suggested", "block", "Alone", "Crowd", None, 6, "up", "Alone",
         {"correct": 5, "of": 5}, True, None, None, None, False),
        (2, "declined", "block", "Alone", "Alone", BY, 7, None, None, None, None, 1, None, None,
         False),
        (3, "suggested", "block", "Alone", "Crowd", None, 12, "up", "Alone",
         {"correct": 5, "of": 5}, True, None, None, None, False)]
    offered = _offered(session)
    assert [offered[index] is None for index in range(6, 11)] == [True] * 5
    assert offered[11].change == 3
    assert _fed(session, "decline") == [
        "held in block Alone: the rig's suggestion 1, to move up to Crowd, declined; it is "
        "suggested again once a fresh window of answers meets its bar"]


def test_a_suggestion_withdraws_when_the_bar_drops(tmp_path):
    """The plan's Review Focus 2: the bar is met, the suggestion shows, then the next answers drop
    below it before the trainer answers -- four of five right still meets 80%, three of five does
    not -- and the suggestion withdraws itself: gone from the next frame, said on the changes
    feed with the numbers, and the run stays where it is. A withdrawal writes no change row
    (wl-preproc was told of no such kind); the trial lines hold what withdrew it."""
    script = ["right"] * 5 + ["wrong", "wrong", "right"]
    session = _two_stages(tmp_path, script)

    session.run()

    assert _blocks(session) == ["Alone"] * 8
    assert [row["kind"] for row in _changes(session)] == ["suggested"]
    offered = _offered(session)
    assert [offered[index] is not None for index in (5, 6, 7)] == [True, True, False]
    assert offered[6].correct == 4 and offered[6].of == 5
    assert _fed(session, "suggestion")[1:] == [
        "the rig's suggestion 1, to move up from Alone to Crowd, is withdrawn: 3 of the last 5 "
        "answers at its hardest step right, under its 80%"]


def test_a_confirmation_after_withdrawal_is_refused_with_a_sentence(tmp_path):
    """The plan's Review Focus 2: a confirmation or a hold that reaches the rig after its
    suggestion withdrew is refused with a sentence, and nothing moves; a person's next block by
    hand, naming no suggestion, still moves the run, as it always did, its row naming none."""
    script = ["right"] * 5 + ["wrong", "wrong", "right", "right", "right"]
    session = _two_stages(tmp_path, script, {9: [NextBlock(by=JAKE, suggestion=1),
                                                 Decline(suggestion=1, by=JAKE)],
                                             10: [NextBlock(by=JAKE)]})

    session.run()

    withdrawn = ("the rig's suggestion 1, to move up from Alone to Crowd, was withdrawn when its "
                 "bar no longer held, missed by more than its margin, before this answer arrived; ")
    assert session.refusals == [
        ("next_block", JAKE, withdrawn + "nothing moved, and the run stays in block Alone"),
        ("decline", JAKE, withdrawn + "there is nothing to hold")]
    assert _blocks(session) == ["Alone"] * 9 + ["Crowd"]
    assert [row["kind"] for row in _changes(session)] == ["suggested"]
    (moved,) = [row for row in _rows(session, "controls.jsonl") if row["kind"] == "next_block"]
    assert "suggestion" not in moved


def test_an_answer_naming_no_suggestion_of_the_run_or_the_other_way_is_refused(tmp_path):
    """An answer is refused, with a sentence, nothing moved, where it names a suggestion the rig
    never made in this run, one already answered, or the other move (back one for a suggestion
    to move up), and a suggestion that is no whole number, as the wire refuses it, where the
    command reached the session another way."""
    script = ["right"] * 9
    session = _two_stages(tmp_path, script, {7: [Decline(suggestion=4, by=JAKE),
                                                 Decline(suggestion="1", by=JAKE),
                                                 BackBlock(by=JAKE, suggestion=1),
                                                 Decline(suggestion=1, by=JAKE),
                                                 NextBlock(by=JAKE, suggestion=1)]})

    session.run()

    assert session.refusals == [
        ("decline", JAKE, "the rig made no suggestion 4 in this run; there is nothing to hold"),
        ("decline", JAKE, "a 'decline' command names the rig's suggestion by its id, a whole "
                          "number from 1, and '1' is not one; there is nothing to hold"),
        ("back_block", JAKE, "the rig's suggestion 1 is to move up from Alone to Crowd, not back; "
                             "nothing moved, and the run stays in block Alone"),
        ("next_block", JAKE, "the rig's suggestion 1, to move up from Alone to Crowd, was already "
                             "declined; nothing moved, and the run stays in block Alone")]
    assert _blocks(session) == ["Alone"] * 9
    assert [row["kind"] for row in _changes(session)] == ["suggested", "declined"]


def test_a_suggestion_lapses_when_a_person_moves_by_hand(tmp_path):
    """A person's move by hand, naming no suggestion, while one stands: the run moves as a move by
    hand always did, its row naming none, and the suggestion lapses -- never said withdrawn -- so an
    answer naming it after is refused, saying so."""
    script = ["right"] * 8
    session = _two_stages(tmp_path, script, {7: [NextBlock(by=JAKE)],
                                             8: [Decline(suggestion=1, by=JAKE)]})

    session.run()

    assert session.refusals == [
        ("decline", JAKE, "the rig's suggestion 1, to move up from Alone to Crowd, lapsed when the "
                          "run left block Alone; there is nothing to hold")]
    assert _blocks(session) == ["Alone"] * 6 + ["Crowd"] * 2
    assert len(_fed(session, "suggestion")) == 1
    assert [row["kind"] for row in _changes(session)] == ["suggested"]


def test_a_stages_time_still_moves_it_up_and_a_suggestion_standing_lapses(tmp_path):
    """Under `confirm` a stage's time running out still moves it up (an engineering call: a time
    limit is the task author's declaration, no judgment of the animal); a suggestion standing then
    lapses, never said withdrawn, and an answer naming it after is refused, saying so. Each right
    trial here is 1.125 s on the simulated trial clock (its frames at the frame period, and the
    ITI), so Alone's 6.5 s run out after six trials, its bar met after five."""
    script = ["right"] * 8
    stages = [_stage("Alone", extra=", time_limit_s=6.5"), _stage("Crowd")]
    session = _session(tmp_path, stages, script, {9: [Decline(suggestion=1, by=JAKE)]})

    session.run()

    assert _blocks(session) == ["Alone"] * 6 + ["Crowd"] * 2
    assert _fed(session, "block") == ["Alone → Crowd: its time ran out"]
    assert len(_fed(session, "suggestion")) == 1
    assert session.refusals == [
        ("decline", JAKE, "the rig's suggestion 1, to move up from Alone to Crowd, lapsed when the "
                          "run left block Alone; there is nothing to hold")]


def test_below_the_back_bar_suggests_the_previous_stage(tmp_path):
    """"Below 50% of the last 50" ("Rig suggests, trainer confirms", back down the same way): in
    Crowd, fewer than half of the last four first answers right suggests Alone, the row saying
    whether those trials were at Crowd's hardest step (its staircase at its easiest: no), and the
    trainer's back one, naming it, moves the run back. The first stage, with none below it, never
    suggests moving back, however it goes."""
    script = ["wrong"] * 4 + ["right"] * 3 + ["wrong"] * 5 + ["right"]
    stages = [_stage("Alone", (0.8, 3)),
              _stage("Crowd", (0.8, 3), 'Staircase("set_size", (4, 6), start=0)')]
    session = _session(tmp_path, stages, script, {8: [NextBlock(by=JAKE, suggestion=1)],
                                                  13: [BackBlock(by=JAKE, suggestion=2)]})

    session.run()

    assert session.refusals == []
    assert _blocks(session) == ["Alone"] * 7 + ["Crowd"] * 5 + ["Alone"]
    assert [_suggested(row) for row in _changes(session)] == [
        (1, "suggested", "block", "Alone", "Crowd", None, 8, "up", "Alone",
         {"correct": 3, "of": 3}, True, None, None, None, False),
        (2, "suggested", "block", "Crowd", "Alone", None, 12, "back", "Crowd",
         {"correct": 0, "of": 4}, False, None, None, None, False)]
    moved = [(row["kind"], row["block"], row["to"], row["suggestion"])
             for row in _rows(session, "controls.jsonl")
             if row["kind"] in ("next_block", "back_block")]
    assert moved == [("next_block", "Alone", "Crowd", 1), ("back_block", "Crowd", "Alone", 2)]
    assert _offered(session)[11] == Suggestion(change=2, move="back", block="Crowd", to="Alone",
                                               correct=0, of=4, at_hardest=False)


def test_a_window_meeting_both_bars_suggests_moving_up(tmp_path):
    """Where the last answers meet both bars at once -- the last three right, and under half of
    the last eight first answers -- the rig suggests moving up, as a stage's met rule counts
    before its fall-back (`Scheduler.ends`)."""
    script = ["right"] * 3 + ["wrong"] * 5 + ["right"] * 3
    stages = [_stage("Alone", (0.8, 3)), _stage("Crowd", (0.8, 3)), _stage("Top", (0.8, 3))]
    session = _session(tmp_path, stages, script, {4: [NextBlock(by=JAKE, suggestion=1)]},
                       order="ByCriterion(fall_back=(0.5, 8), confirm=True)")

    session.run()

    assert [(row["change"], row["move"], row["now"], row["bar"]) for row in _changes(session)] == [
        (1, "up", "Crowd", {"correct": 3, "of": 3}), (2, "up", "Top", {"correct": 3, "of": 3})]


def test_the_bar_counts_answers_only(tmp_path):
    """The last 50 count answers only (the design's §3.4): an early saccade and no fixation are
    left out of the window, and leaving the target before its hold -- an error after the go, though
    the engine counts it as no answer -- is in it, a failure, as the staircase classes it
    (`task.staircase_verdict`): after seven trials, four of the last five answers right."""
    script = ["right", "early", "right", "away", "right", "break", "right", "right"]
    session = _two_stages(tmp_path, script)

    session.run()

    assert [line["outcome"] for line in _rows(session, "trials.jsonl")] == [
        "correct", "fixation_break", "correct", "no_fixation", "correct", "target_break",
        "correct", "correct"]
    (row,) = _changes(session)
    assert (row["trial_number"], row["bar"]) == (8, {"correct": 4, "of": 5})
    assert _offered(session)[6] is None and _offered(session)[7].of == 5


def test_under_drumming_the_bar_to_move_back_judges_each_trials_first_answer(tmp_path):
    """"First answer only" (the PI, 2026-10-19; TSK-57), for the suggestion as for a fall-back:
    under drumming a trial that is not right comes back until it is, and only each trial's first
    answer counts toward moving back, so one stubborn trial cannot suggest demoting a stage. Four
    trials in Crowd, each wrong first and right on its drummed try: none of four first answers
    right."""
    script = ["right"] * 3 + ["wrong", "right"] * 4
    stages = [_stage("Alone", (0.8, 3)), _stage("Crowd", (0.8, 3), extra=", drum=True")]
    session = _session(tmp_path, stages, script, {4: [NextBlock(by=JAKE, suggestion=1)]})

    session.run()

    assert session.refusals == []
    assert [line["drummed"] for line in _rows(session, "trials.jsonl")][3:] == [False, True] * 4
    back = [row for row in _changes(session) if row.get("move") == "back"]
    assert [(row["trial_number"], row["bar"]) for row in back] == [(11, {"correct": 0, "of": 4})]


def test_with_first_answers_on_the_bar_to_move_up_judges_each_trials_first_answer(tmp_path):
    """The training setting "first answers only" (the PI, 2026-10-18), for the suggestion as for a
    stage's own percentage rule: under drumming with it on, only each trial's first answer counts
    toward moving up, so the right drummed try of a trial first answered wrong is not one of the
    three right."""
    script = ["wrong"] + ["right"] * 5
    stages = [_stage("Alone", (0.8, 3), extra=", drum=True"), _stage("Crowd", (0.8, 3))]
    session = _session(tmp_path, stages, script,
                       {1: [Training(setting="first_answers", on=True, by=JAKE)]})

    session.run()

    assert [(row["kind"], row["change"], row["trial_number"]) for row in _changes(session)] == [
        ("training", 1, 1), ("suggested", 2, 6)]


def test_the_bar_to_move_up_counts_the_answers_at_the_hardest_step(tmp_path):
    """"Hardest step reached, 80% there": the bar to move up counts the last answers given at the
    stage's hardest step, its staircase at its last level, and leaves out those at an easier
    level, which neither count nor break the window. A failure at the top steps the staircase
    down one (its one-up rule), so a window every answer had to share would ask for an unbroken run
    of right answers there, not 80%: here four of the last five answers at six objects are right,
    with the three at four objects between them left out. Not before the staircase reached its
    top: the first answers, at its easiest, never count."""
    script = ["right", "right", "wrong", "right", "right", "right", "right", "right"]
    stages = [_stage("Fade-in", (0.8, 5), 'Staircase("set_size", (4, 6), start=1)'),
              _stage("Crowd", (0.8, 5))]
    session = _session(tmp_path, stages, script)

    session.run()

    assert [line["params"]["set_size"] for line in _rows(session, "trials.jsonl")] == (
        [6] * 3 + [4] * 3 + [6] * 2)
    (row,) = _changes(session)
    assert (row["trial_number"], row["bar"], row["at_hardest"]) == (
        9, {"correct": 4, "of": 5}, True)
    assert _offered(session)[7] is None
    assert (_offered(session)[8].correct, _offered(session)[8].of) == (4, 5)


def test_answers_below_the_hardest_step_never_count_toward_moving_up(tmp_path):
    """Three right of the last three meet the bar only once all three were given at the stage's
    hardest step: not the first three, played at its easiest, but the three after the staircase
    stepped up."""
    script = ["right"] * 7
    stages = [_stage("Fade-in", (0.8, 3), 'Staircase("set_size", (4, 6), start=0)'),
              _stage("Crowd", (0.8, 3))]
    session = _session(tmp_path, stages, script)

    session.run()

    assert [line["params"]["set_size"] for line in _rows(session, "trials.jsonl")] == (
        [4] * 3 + [6] * 4)
    (row,) = _changes(session)
    assert (row["trial_number"], row["bar"], row["at_hardest"]) == (
        7, {"correct": 3, "of": 3}, True)
    assert _offered(session)[5] is None and _offered(session)[6].at_hardest


def test_an_eased_trial_is_left_out_of_the_bar_to_move_up(tmp_path):
    """Engine build C3's eased trials (the PI, Q8: a trial a person's change made easier does not
    count toward moving up): trials played at a fixation hold a person made shorter than the run's
    are left out of the window, so three right of the last three counts only the trials either
    side of the hold."""
    script = ["right"] * 7
    session = _two_stages(tmp_path, script, {2: [SetParameter(name="fix_hold", value=0.1, by=JAKE)],
                                             5: [HandBack(name="fix_hold", by=JAKE)]},
                          up=(0.8, 3))

    session.run()

    assert session.refusals == []
    assert [line["eased"] for line in _rows(session, "trials.jsonl")] == (
        [[]] * 2 + [["fix_hold"]] * 3 + [[]] * 2)
    suggested = [row for row in _changes(session) if row["kind"] == "suggested"]
    assert [(row["change"], row["trial_number"]) for row in suggested] == [(3, 7)]


def test_without_confirm_bycriterion_moves_as_before(tmp_path):
    """C2b's training progression, unchanged without `confirm`: a stage whose rule is met moves up
    on its own, the feed saying why; nothing is suggested, and no frame carries a suggestion."""
    script = ["right"] * 8
    session = _two_stages(tmp_path, script, order="ByCriterion(fall_back=(0.5, 4))")

    session.run()

    assert _blocks(session) == ["Alone"] * 5 + ["Crowd"] * 3
    assert _changes(session) == []
    assert set(_offered(session).values()) == {None}
    assert _fed(session, "block") == [
        "Alone → Crowd: its rule met: 5 of its last 5 answers right, every target used up"]


def test_a_stage_with_no_bar_keeps_working_until_a_person_moves_it(tmp_path):
    """Under `confirm` no stage moves of itself: one with no criterion, its target used up, keeps
    drawing its conditions, as a top stage does, until a person moves the run, and the rig
    suggests nothing for it."""
    script = ["right"] * 4
    session = _session(tmp_path, [_stage("Alone", None), _stage("Crowd")], script)

    session.run()

    assert _blocks(session) == ["Alone"] * 4
    assert session.stopped_because == "stopped by jake (box, unverified)"
    assert _changes(session) == []


def test_the_review_report_says_a_person_confirms_each_move(tmp_path):
    """The review report (`wlx review`; engine spec §18.1) says a confirmed progression's moves are
    a person's, suggested by the rig, so a reviewer reads what the plan does: tasks are written by
    a model and read by people."""
    path = _task(tmp_path, [_stage("Alone"), _stage("Crowd")])

    report = render_task(_load_task(path))

    assert ("A training progression, stage by stage from the first, each move suggested by the rig "
            "and made only when a person confirms it: up when a stage's rule is met on its "
            "answers at its hardest step; back one, its counts started fresh (its staircase where "
            "the run left it), under 50% right over the last 4 "
            "first answers; a stage whose time runs out moves up on its own; the top stage keeps "
            "working until a time limit, a stop or the session's end.") in report


def test_decline_and_a_confirmation_travel_the_wire_with_the_suggestion_they_answer():
    """The trainer's Hold is its own command, `decline`, naming the suggestion it answers; next
    block and back one may name one too, and with none are a move by hand, as before. Each is
    built by the wire's own rules from a page's body, and a suggestion that is not a whole number
    from 1 is refused before any session sees it."""
    for command in (Decline(suggestion=3, by=JAKE), NextBlock(by=JAKE, suggestion=3),
                    BackBlock(by=JAKE, suggestion=2), NextBlock(by=JAKE), BackBlock(by=JAKE)):
        restored = _decode_command(_encode_command(command))
        assert restored == command and type(restored) is type(command)
    assert Decline.KIND == "decline"
    assert parse_command({"kind": "decline", "suggestion": 3, "by": "jake"}) == Decline(
        suggestion=3, by=JAKE)
    assert parse_command({"kind": "next_block", "suggestion": 3, "by": "jake"}) == NextBlock(
        by=JAKE, suggestion=3)
    assert parse_command({"kind": "back_block", "by": "jake"}) == BackBlock(by=JAKE)
    for body in ({"kind": "decline", "by": "jake"},
                 {"kind": "decline", "suggestion": 0, "by": "jake"},
                 {"kind": "decline", "suggestion": True, "by": "jake"},
                 {"kind": "next_block", "suggestion": "3", "by": "jake"},
                 {"kind": "back_block", "suggestion": 2.0, "by": "jake"}):
        with pytest.raises(BadCommand, match="names the rig's suggestion by its id, a whole number "
                                             "from 1"):
            parse_command(body)
    with pytest.raises(CommandRefused):
        _command_from({"kind": "decline", "suggestion": -1, "by": {"kind": "box", "name": "j"}})


def test_a_reader_of_19_refuses_20_and_20_refuses_19_by_name(monkeypatch):
    """Telemetry schema 20 carries the rig's suggestion: §3's schema rule, both ways round, so a
    console built for 19 refuses a frame whose suggestion it would not show."""
    sent = frame()

    assert SCHEMA == sent.schema == 20
    with pytest.raises(SchemaMismatch, match="carried schema 19 and this console reads schema 20"):
        decode(encode(replace(sent, schema=19)))
    monkeypatch.setattr(wire, "SCHEMA", 19)
    with pytest.raises(SchemaMismatch, match="carried schema 20 and this console reads schema 19"):
        decode(encode(sent))


def test_a_frame_with_a_suggestion_round_trips():
    """ADR-0003's golden round-trip for schema 20's field: a frame's suggestion, and none."""
    offered = Suggestion(change=3, move="back", block="Crowd", to="Alone", correct=1, of=50,
                         at_hardest=False)
    for sent in (frame(suggestion=offered), frame(suggestion=None)):
        assert decode(encode(sent)) == sent


def test_wl_preprocs_reader_takes_the_suggested_and_declined_rows(tmp_path):
    """The path, not the piece: wl-preproc's reader of the rig's records takes a run's suggestion
    and hold rows with no problem, `sequence` on neither, and its field reader reads their kinds,
    the stage each names and the detail it was told of."""
    try:
        from wl_preproc.events.rigrecords import change_fields, read_rig_records
    except ImportError as exc:  # pragma: no cover - exercised by the CI job
        if os.environ.get("WLX_REQUIRE_PREPROC") == "1":
            raise AssertionError(
                f"WLX_REQUIRE_PREPROC=1 but wl-preproc is not importable ({exc})") from exc
        pytest.skip("wl-preproc checkout not beside this repo")
    session = _two_stages(tmp_path, ["right"] * 7, {7: [Decline(suggestion=1, by=JAKE)]})
    session.run()

    records = read_rig_records(session.directory.parent)
    log = session.directory / "parameter_changes.jsonl"
    texts = log.read_text().splitlines() if log.exists() else []
    fields, problems = change_fields(texts)

    assert records.problems == ()
    assert [(change.name, change.sequence) for change in records.changes] == [
        ("block", None), ("block", None)]
    assert problems_beyond_xc461(problems) == []
    read = [(field.kind, field.change, field.block, json.loads(field.detail)) for field in fields]
    assert read == [
        ("suggested", 1, "Alone", {"move": "up", "block": "Alone", "bar": {"correct": 5, "of": 5},
                                   "at_hardest": True}),
        ("declined", 2, None, {"suggestion": 1})]


def test_the_two_kinds_are_appended_and_a_resume_reads_them(tmp_path):
    """`record.KINDS` grows only after `training` (`STROBED = KINDS[:4]` is positional), and
    neither new kind strobes; a session whose log holds a suggestion and a hold is read back by a
    resume, its next change numbered after them."""
    assert KINDS[7:] == ("suggested", "declined") and STROBED == KINDS[:4]
    session = _two_stages(tmp_path, ["right"] * 7, {7: [Decline(suggestion=1, by=JAKE)]})
    session.run()

    restoration = resume.read(session.directory, session.welfare.left_cage_wall_at)

    assert restoration.change == 2
