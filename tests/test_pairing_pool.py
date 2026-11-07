"""The pairing pool (the pop-out search build's Task 5; its design,
`docs/superpowers/specs/2026-11-07-popout-search-design.md` §3.2 and §3.4, approved by the PI on
2026-11-07).

The PI's answers of 2026-11-07: "A pool of four" -- on each trial one color is the odd one and
another fills the distractors, so the animal learns the odd one, not the blue one; twelve ordered
pairings; "Start with fewer, add more"; the trainer picks the first pairings ("The trainer
picks"), and the rig suggests adding more by the same rule as a stage ("Same rule: rig
suggests"); at the prompt "Trainer picks at the prompt". The design's calls (§3.4): the bar is
judged over all the current pairings pooled; in Alone a pairing is only the odd one's color; when
one window of trials meets both bars, one prompt offers both, the stage first; a widening leaves
the staircase where it is; the pool carries into the next stage.

**The pool's value is a whole number** (`task.Pool`): the sum of its pairings' numbers, 1, 2, 4,
8 ... in the order the pool declares them. The console's `set` and the wire carry a setting's
value as a number or as one of its declared choices (`link._setting` and `Session.set`, both
welfare-listed and unchanged), and a pool of twelve pairings has 4,095 non-empty values, too many
to declare as choices that every frame would carry; a whole number rides every existing path --
a live `set`, a run's start, `wlx run --set`, the frame and the record -- unchanged.

wl-preproc accepted the record's shapes on 2026-11-07 (`docs/pending-wl-preproc-amendments.md`):
the pairing is two settings in `params`, each marked `drawn: "pool"`, and a `suggested` row's
`move` may be `"widen"`. The plan's Review Focus 5: an empty pool is refused with a sentence before
the next trial; Alone with any pool runs (only the odd one's color shows).

Engine test material, run only in the simulator: the reference search task with a pool of three
pairings of its own looks -- a red disc among green, a green disc among red, a green square among
red -- over its `target_appearance` and `distractor_appearance`, its set size allowed down to one
for an Alone stage. Windows are short (5 answers) so a run is a few trials; the task's own are 50.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest

import _sessions
from _frames import frame, view
from _rig import DIRECT, PATH as RIG_FILE
from wl_xcon import stranded
from wl_xcon.actor import Box
from wl_xcon.check import check_task
from wl_xcon.cli import _load_allocation, _load_task, main
from wl_xcon.dio import Simulated as Card
from wl_xcon.link import (
    Decline, HandBack, NextBlock, SetParameter, Simulated, Stop, Suggestion, decode, encode,
)
from wl_xcon.photometry import SRGB
from wl_xcon.preflight import FAIL, values as starting_values
from wl_xcon.review import render_task
from wl_xcon.run import Scripted
from wl_xcon.task import Pool, SaccadeTo
from wl_xcon.taskd import RunSpec, Session, SessionSpec
from wl_xcon.web import fragments
from wl_xcon.welfare import Deployment, Simulated as Pump

WALL_NOW = 1_700_000_000.0
SEED = 7
JAKE = Box("jake")
#: Jake as a row writes him.
BY = {"kind": "box", "name": "jake"}
FRAMES = 240
SEARCH = "tasks/visual_search.py"
#: The confirmed progression's order, with short windows: up at 80% of the last 5 answers, back
#: under 50% of the last 4 first answers, each move a person's to confirm.
CONFIRMED = "ByCriterion(fall_back=(0.5, 4), confirm=True)"
#: The pool's three pairings, odd one first, as `_look` names each look a line writes.
P1, P2, P3 = ("red disc", "green disc"), ("green disc", "red disc"), ("green square", "red disc")
#: The pool's declaration, after `visual_search`'s own source.
POOL = (
    "Pool('pairings', ((RED_DISC, GREEN_DISC), (GREEN_DISC, RED_DISC), (GREEN_SQUARE, RED_DISC)),"
    " odd='target_appearance', distractor='distractor_appearance')")


def _source(stages: list[str], order: str, *, pool: str = POOL, low: str = "1",
            start: str | None = "1",
            meaning: str = "Meaning(NOT_DIFFICULTY, NEITHER, note='which pairings are drawn')",
            extra: str = "") -> str:
    """`visual_search`'s source with a pool over its two looks, its pool setting `pairings`
    declared from 1 to 7 starting at `start`, its set size allowed down to one object (its target
    index then always 0), and one plan, `train`, of `stages` in `order`; `extra`, more source
    after it. Engine test material."""
    text = Path(SEARCH).read_text()
    for old, new in (('Param("set_size", unit="objects", low=2, high=12)',
                      'Param("set_size", unit="objects", low=1, high=12)'),
                     ('Param("target_index", unit="index", low=0, high=1)',
                      'Param("target_index", unit="index", low=0, high=0)')):
        assert text.count(old) == 1, old
        text = text.replace(old, new)
    started = "" if start is None else f", start={start}"
    return text + (
        "\n\nimport dataclasses as _dataclasses\n"
        "from wl_xcon.scheduler import EVERY_TRIAL\n"
        "from wl_xcon.task import (Block, ByCriterion, Condition, Plan, Pool, Staircase, "
        "Uniform, Weighted, CLEAR_CUT, HARDER, NEITHER, NOT_DIFFICULTY)\n"
        "RED_DISC, GREEN_DISC = Disc(size=1.0, color=RED), Disc(size=1.0, color=GREEN)\n"
        "GREEN_SQUARE = Square(size=1.0, color=GREEN)\n"
        "search = _dataclasses.replace(search, params=[*search.params, "
        f"Param('pairings', unit='pairings', low={low}, high=7{started})])\n"
        "TASK = _dataclasses.replace(\n"
        "    TASK, structures={'search': search},\n"
        f"    meanings={{**TASK.meanings, 'pairings': {meaning}}},\n"
        f"    pool={pool},\n"
        f"    plans={{'train': Plan([{', '.join(stages)}], order={order})}})\n"
        + extra)


def _stage(name: str, criterion=(0.8, 5), *, set_size: int | None = None,
           staircase: str | None = None, extra: str = "") -> str:
    """A stage's source: one condition, every trial paying it (`EVERY_TRIAL`), giving the set size
    where `set_size` says, its `criterion` the up bar, the staircase given, and `extra`, more of
    its fields as source."""
    values = "{}" if set_size is None else f"{{'set_size': {set_size}}}"
    stepped = "" if staircase is None else f", staircase={staircase}"
    rule = "" if criterion is None else f", criterion={criterion}"
    return (f'Block("{name}", [Condition("c", {values}, target=1)], counting=EVERY_TRIAL'
            f'{rule}{stepped}{extra})')


def _task(folder: Path, stages: list[str], order: str = CONFIRMED, **source) -> Path:
    """`_source`'s task written into `folder` as `search.py`."""
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "search.py"
    path.write_text(_source(stages, order, **source))
    return path


#: `visual_search`'s starting values: its looks as the pool's first pairing, which the pool's
#: draw replaces on every trial, six objects where no stage gives the set size, and one pairing
#: pooled.
VALUES = {**_sessions.SEARCH_VALUES, "pairings": 1}


def _trial(kind: str, values: dict) -> Scripted:
    """One trial the animal plays as `kind` says: `right` (`CORRECT`), `wrong`, a look at a
    distractor (`WRONG_TARGET`), and `early`, leaving the fixation point before the array, the go
    (`FIXATION_BREAK`)."""
    held = round(values["fix_hold"] * FRAMES) + 20
    target = f"search.{values['target_index']}"
    looks = {frame: "fix" for frame in range(1, held + 1)}
    if kind == "right":
        return Scripted({SaccadeTo("search.target"): held + 10},
                        inside={**looks, **{f: target for f in range(held + 1, held + 400)}})
    if kind == "wrong":
        return Scripted({SaccadeTo("search.distractor"): held + 10}, inside=looks)
    assert kind == "early", kind
    return Scripted({}, inside={frame: "fix" for frame in range(1, 6)})


class _Drained(Simulated):
    """A link that queues `script[n]` as the `n`th drain begins: the loop drains once before each
    trial, so drain `n` comes before the trial numbered `n - 1` from 0, while no block moves on of
    itself. A value it queues is staged at that drain and applies at the next boundary, the trial
    after."""

    def __init__(self, script):
        super().__init__()
        self.script, self.drains = dict(script), 0

    def drain(self) -> list:
        self.drains += 1
        assert self.drains <= 100, "the session is not ending"
        for command in self.script.get(self.drains, ()):
            self.queue(command)
        return super().drain()


def _session(folder: Path, stages: list[str], script: list[str], commands=None, *,
             order: str = CONFIRMED, values: dict | None = None, world=None,
             start_block: str | None = None, **source) -> Session:
    """A run of plan `train` of `stages` on the simulators, its animal playing `script`, the run
    stopped by a person once the script is played, its wall following its frames from
    `WALL_NOW`, the animal out of its cage and its head fixed, at `start_block` where one is
    given. `world`, called with the session and the trial's index before each trial is built,
    may reach into it."""
    path = _task(folder, stages, order, **source)
    spec = SessionSpec(
        task=str(path), allocation="tasks/allocation.py", root=folder,
        session_id="2027-01-14_01", subject="A", trials=len(script), frame_period=1 / FRAMES,
        seed=SEED, values={**VALUES, **(values or {})}, bounds=_sessions.bounds(),
        already_delivered_today=0.0, deployment=Deployment.RIG_FIXED, geometry=DIRECT,
        session_kind="training", calibration=SRGB, plan="train", start_block=start_block,
    )
    session = Session(spec, card=Card(), pump=Pump(), link=_Drained(commands or {}))
    session.wall_clock = lambda: WALL_NOW + session.now()
    session.left_cage(at=WALL_NOW)
    session.head_fixed(at=session.wall_now())

    def built(trial, values, index):
        if world is not None:
            world(session, index)
        if index == len(script) - 1:
            # The script's last trial: a person's stop, drained at the boundary after it.
            session.link.queue(Stop(by=JAKE))
        return _trial(script[index], values)

    session.world = built
    return session


def _rows(session: Session, name: str) -> list[dict]:
    path = session.directory / name
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def _lines(session: Session) -> list[dict]:
    return _rows(session, "trials.jsonl")


def _changes(session: Session) -> list[dict]:
    return _rows(session, "parameter_changes.jsonl")


def _look(written: dict) -> str:
    """A look as a trial's line writes it (`record._written`), in words: its color, by the sign of
    its L-M contrast (`visual_search`'s red is +0.603, its green -0.143), and its shape."""
    color = "red" if written["fields"]["color"]["fields"]["l_m"] > 0 else "green"
    return f"{color} {written['class'].lower()}"


def _pairing(line: dict) -> tuple[str, str]:
    """The pairing a trial's line shows: its target's look, then its distractors'."""
    return (_look(line["params"]["target_appearance"]),
            _look(line["params"]["distractor_appearance"]))


def _suggested(row: dict) -> tuple:
    """A change row as the fields a suggestion and a hold write."""
    return (row["change"], row["kind"], row["name"], row["was"], row["now"], row["by"],
            row["trial_number"], row.get("move"), row.get("block"), row.get("bar"),
            row.get("at_hardest"), row.get("suggestion"))


def _offered(session: Session) -> dict[int, tuple]:
    """The stage's suggestion and the widening each running frame carried, by the trial about to
    run, the last frame of each boundary's."""
    return {f.trial_index: (f.suggestion, f.widen) for f in session.link.published
            if f.phase == "running"}


def _fed(session: Session, kind: str) -> list[str]:
    return [said for fed, _, _, said in session.controls if fed == kind]


def _widen(change: int, block: str, correct: int = 5, of: int = 5) -> Suggestion:
    """A frame's widening, as `link.Suggestion` carries it: no stage to go to."""
    return Suggestion(change=change, move="widen", block=block, to=None, correct=correct, of=of,
                      at_hardest=True)


def test_each_trial_draws_a_pairing_from_the_current_pool(tmp_path):
    """"A pool of four": each trial draws one pairing of the pool its setting holds now into the
    two settings, the odd one's look and the distractors' -- here pairings 1 and 3, the setting at
    5 -- each marked `drawn: "pool"` on its line, as wl-preproc accepted, with the pool's own value
    beside them in `params`. A person's `set` of the pool, a change-log row with who, applies at
    the next boundary, as every value does: from that trial on, only the pairing it holds."""
    script = ["right"] * 14
    session = _session(tmp_path, [_stage("Crowd")], script,
                       {9: [SetParameter("pairings", 2, JAKE)]}, values={"pairings": 5})

    session.run()

    assert session.refusals == []
    (row,) = [row for row in _changes(session) if row["kind"] == "set"]
    assert (row["name"], row["was"], row["now"], row["by"], row["trial_number"]) == (
        "pairings", 5, 2, BY, 10)
    lines = _lines(session)
    assert len(lines) == 14
    before = [_pairing(line) for line in lines if line["trial_number"] < 10]
    after = [_pairing(line) for line in lines if line["trial_number"] >= 10]
    assert set(before) == {P1, P3} and set(after) == {P2}
    assert {(line["drawn"].get("target_appearance"), line["drawn"].get("distractor_appearance"))
            for line in lines} == {("pool", "pool")}
    assert [line["params"]["pairings"] for line in lines] == [5] * 9 + [2] * 5


def test_a_person_holding_one_look_takes_it_over_the_pool(tmp_path):
    """A person's value on one of the two settings holds it (engine build C3's held setting), as
    over any draw: its trials show the person's look, the line no longer marking it drawn by the
    pool, and the pool still gives the other. Its `set` row writes no `was` -- no single value was
    held before it, the pool giving each trial its own, whatever the run's value -- and a
    hand-back gives it back to the draw (`to` `"draw"`, the word wl-preproc was told), the pool
    giving it again from the next trial."""
    script = ["right"] * 7
    ((red, _, square),) = [param.choices for param in _load_task(Path(SEARCH)).params
                           if param.name == "target_appearance"]
    session = _session(tmp_path, [_stage("Crowd", criterion=None)], script,
                       {3: [SetParameter("target_appearance", square, JAKE)],
                        5: [HandBack("target_appearance", JAKE)]},
                       values={"pairings": 2, "target_appearance": red})

    session.run()

    assert session.refusals == []
    lines = _lines(session)
    assert [_pairing(line) for line in lines] == (
        [P2] * 3 + [("green square", "red disc")] * 2 + [P2] * 2)
    assert [line["drawn"].get("target_appearance") for line in lines] == (
        ["pool"] * 3 + [None] * 2 + ["pool"] * 2)
    assert [line["drawn"].get("distractor_appearance") for line in lines] == ["pool"] * 7
    held, handed = _changes(session)
    assert (held["kind"], held["name"], held["was"], held["trial_number"]) == (
        "set", "target_appearance", None, 4)
    assert (handed["kind"], handed["name"], handed["to"], handed["trial_number"]) == (
        "hand_back", "target_appearance", "draw", 6)


def test_a_look_held_over_the_pool_is_judged_against_the_trials_pairing(tmp_path):
    """A value a person holds over a look the pool gives is judged against the look the trial's
    pairing would have given (engine build C3's eased trials; the PI, Q8): with the odd one's look
    declared an expected setting, held at the look the pool draws it is no change, and at another
    each trial is kept out of moving up, its line naming it."""
    ((_, green, square),) = [param.choices for param in _load_task(Path(SEARCH)).params
                             if param.name == "target_appearance"]
    expected = ("TASK = _dataclasses.replace(TASK, meanings={**TASK.meanings, "
                "'target_appearance': Meaning(EXPECTED, STIMULUS, raising=HARDER, "
                "note='engine test material', overrides='engine test material')})\n")
    session = _session(tmp_path, [_stage("Crowd", criterion=None)], ["right"] * 6,
                       {2: [SetParameter("target_appearance", green, JAKE)],
                        4: [SetParameter("target_appearance", square, JAKE)]},
                       values={"pairings": 2}, extra=expected)

    session.run()

    assert session.refusals == []
    lines = _lines(session)
    assert [_pairing(line)[0] for line in lines] == ["green disc"] * 4 + ["green square"] * 2
    assert [line["eased"] for line in lines] == [[]] * 4 + [["target_appearance"]] * 2


def test_a_repeat_shows_the_pairing_of_the_trial_it_repeats(tmp_path):
    """A drummed repeat is the trial again, "so the drum teaches the problem" (the PI's "Follow
    same/fresh"): it shows the pairing the trial it repeats drew, never a new draw, while a new
    trial draws afresh."""
    script = ["wrong", "wrong", "right"] * 4
    session = _session(tmp_path, [_stage("Crowd", extra=", drum=True")], script,
                       values={"pairings": 7})

    session.run()

    lines = _lines(session)
    assert [line["drummed"] for line in lines] == [False, True, True] * 4
    shown = [_pairing(line) for line in lines]
    assert all(shown[at] == shown[at + 1] == shown[at + 2] for at in range(0, 12, 3))
    assert len({shown[at] for at in range(0, 12, 3)}) > 1


def test_the_bar_on_the_pooled_pairings_suggests_widen(tmp_path):
    """"Start with fewer, add more" and "Same rule: rig suggests": five right of the last five
    answers, judged over every pairing pooled, meet the stage's bar, and the rig suggests both
    moving up and widening the pool -- one window meeting both bars, one prompt offering both,
    **the stage first** (the design's §3.4). The widening is a `suggested` row of `move`
    `"widen"`, naming the pool's setting, its value then as `was` and no `now` -- it names no
    pairings: the trainer picks them ("Trainer picks at the prompt") -- from no one, strobing
    nothing. Each frame from the next boundary carries both, the widening with no stage to go
    to; the changes feed says each."""
    session = _session(tmp_path, [_stage("Alone", set_size=1), _stage("Crowd")], ["right"] * 8)

    session.run()

    assert [line["block"] for line in _lines(session)] == ["Alone"] * 8
    assert [_suggested(row) for row in _changes(session)] == [
        (1, "suggested", "block", "Alone", "Crowd", None, 6, "up", "Alone",
         {"correct": 5, "of": 5}, True, None),
        (2, "suggested", "pairings", 1, None, None, 6, "widen", "Alone",
         {"correct": 5, "of": 5}, True, None)]
    assert all(row["event_code"] is None and "sequence" not in row for row in _changes(session))
    offered = _offered(session)
    assert [offered[index] for index in range(5)] == [(None, None)] * 5
    up = Suggestion(change=1, move="up", block="Alone", to="Crowd", correct=5, of=5,
                    at_hardest=True)
    assert [offered[index] for index in (5, 6, 7)] == [(up, _widen(2, "Alone"))] * 3
    assert _fed(session, "suggestion") == [
        "the rig suggests moving up from Alone to Crowd: 5 of the last 5 answers at its hardest "
        "step right; confirm with next block, or hold",
        "the rig suggests widening the pool in Alone: 5 of the last 5 answers at its hardest step "
        "right, over the 1 pairing of 3 it holds; widen it with a value of pairings holding more, "
        "or hold"]


def test_the_top_stage_suggests_widening_alone_and_a_full_pool_never(tmp_path):
    """At the top stage there is no stage to move up to, so the bar met suggests widening alone;
    a pool holding every pairing has none to add, so the rig never suggests widening it."""
    narrow = _session(tmp_path / "narrow", [_stage("Crowd")], ["right"] * 6)
    full = _session(tmp_path / "full", [_stage("Crowd")], ["right"] * 6, values={"pairings": 7})

    narrow.run()
    full.run()

    assert [_suggested(row) for row in _changes(narrow)] == [
        (1, "suggested", "pairings", 1, None, None, 6, "widen", "Crowd",
         {"correct": 5, "of": 5}, True, None)]
    assert _offered(narrow)[5] == (None, _widen(1, "Crowd"))
    assert _changes(full) == []
    assert _offered(full)[5] == (None, None)


def test_widening_the_pool_answers_the_prompt_and_the_bars_start_afresh(tmp_path):
    """The trainer answers the widening with a `set` of the pool holding more pairings (the
    change log's `set` row says who). As it applies, the widening is confirmed and the move up
    offered beside it is withdrawn -- one prompt, answered -- and both bars start afresh, judged
    over the pairings pooled now: a confirmation of the move up arriving after is refused with a
    sentence, nothing moved, and the rig suggests again only once five new answers meet the bar
    ("After 50 new tries", the PI, of a hold)."""
    script = ["right"] * 13
    session = _session(tmp_path, [_stage("Alone", set_size=1), _stage("Crowd")], script,
                       {7: [SetParameter("pairings", 3, JAKE)],
                        9: [NextBlock(by=JAKE, suggestion=1)]})

    session.run()

    assert session.refusals == [
        ("next_block", JAKE, "the rig's suggestion 1, to move up from Alone to Crowd, was "
         "withdrawn when its bar stopped being met, before this answer arrived; nothing moved, "
         "and the run stays in block Alone")]
    assert [line["block"] for line in _lines(session)] == ["Alone"] * 13
    assert [(row["change"], row["kind"], row["name"], row.get("move"), row["trial_number"])
            for row in _changes(session)] == [
        (1, "suggested", "block", "up", 6), (2, "suggested", "pairings", "widen", 6),
        (3, "set", "pairings", None, 8),
        (4, "suggested", "block", "up", 13), (5, "suggested", "pairings", "widen", 13)]
    assert _changes(session)[2]["by"] == BY
    offered = _offered(session)
    assert [offered[index] for index in range(7, 12)] == [(None, None)] * 5
    assert _fed(session, "suggestion")[2] == (
        "the pool changed in Alone, so the bars start afresh on the pairings pooled now; the "
        "rig's suggestion 2, to widen the pool, is confirmed; the rig's suggestion 1, to move up "
        "from Alone to Crowd, is withdrawn")
    assert {_pairing(line) for line in _lines(session)[7:]} == {P1, P2}


def test_a_widening_leaves_the_staircase_where_it_is(tmp_path):
    """"A widening leaves the staircase where it is" (the design's §3.4): Crowd's staircase on its
    set size, at its hardest step, meets the bar and the widening is offered; a failure steps it a
    level easier; the trainer widens the pool; the next trials run at the level it had stepped
    to, counting on from there, never back to where the block started it."""
    script = ["right"] * 5 + ["wrong"] + ["right"] * 4
    session = _session(tmp_path, [_stage("Crowd", staircase="Staircase('set_size', (4, 6, 8), "
                                                            "start=2)")],
                       script, {7: [SetParameter("pairings", 3, JAKE)]})

    session.run()

    assert session.refusals == []
    assert [(row["kind"], row.get("move"), row["trial_number"]) for row in _changes(session)] == [
        ("suggested", "widen", 6), ("set", None, 8)]
    assert [line["params"]["set_size"] for line in _lines(session)] == [8] * 6 + [6] * 3 + [8]


def test_one_hold_holds_the_whole_prompt_and_the_count_starts_again(tmp_path):
    """The trainer holds (`Decline`, the console's Hold) naming either suggestion of the prompt:
    the move up and the widening stand on one window, so one hold holds both, a `declined` row
    each, by the trainer, the stage's first, naming the suggestion it answers -- the stage's
    `name` the block, the widening's the pool's setting at its value. The count starts again
    ("After 50 new tries", the PI): five new answers, and both are suggested again."""
    script = ["right"] * 12
    session = _session(tmp_path, [_stage("Alone", set_size=1), _stage("Crowd")], script,
                       {7: [Decline(suggestion=2, by=JAKE)]})

    session.run()

    assert session.refusals == []
    assert [_suggested(row) for row in _changes(session)] == [
        (1, "suggested", "block", "Alone", "Crowd", None, 6, "up", "Alone",
         {"correct": 5, "of": 5}, True, None),
        (2, "suggested", "pairings", 1, None, None, 6, "widen", "Alone",
         {"correct": 5, "of": 5}, True, None),
        (3, "declined", "block", "Alone", "Alone", BY, 7, None, None, None, None, 1),
        (4, "declined", "pairings", 1, 1, BY, 7, None, None, None, None, 2),
        (5, "suggested", "block", "Alone", "Crowd", None, 12, "up", "Alone",
         {"correct": 5, "of": 5}, True, None),
        (6, "suggested", "pairings", 1, None, None, 12, "widen", "Alone",
         {"correct": 5, "of": 5}, True, None)]
    offered = _offered(session)
    assert [offered[index] for index in range(6, 11)] == [(None, None)] * 5
    assert _fed(session, "decline") == [
        "held in block Alone: the rig's suggestion 1, to move up to Crowd, declined; it is "
        "suggested again once a fresh window of answers meets its bar",
        "held in block Alone: the rig's suggestion 2, to widen the pool, declined; it is "
        "suggested again once a fresh window of answers meets its bar"]


def test_a_hold_of_a_move_back_leaves_the_widening_standing(tmp_path):
    """The build's review, M1 (H3): one hold holds the whole prompt only where the prompt is a move
    up and a widening on one window. **A move back stands on another window** (the first answers,
    toward the fall-back), so at the top stage, where a widening and a move back can stand
    together, a hold of the move back declines it alone: one `declined` row, naming it, and the
    widening still stands, offered on every frame after. Crowd's staircase at its hardest step
    meets the bar to widen on five right; four failures step it down and meet the fall-back."""
    script = ["right"] * 5 + ["wrong"] * 4 + ["right"] * 2
    session = _session(tmp_path, [_stage("Alone", set_size=1),
                                  _stage("Crowd", staircase="Staircase('set_size', (4, 6, 8), "
                                                            "start=2)")],
                       script, {9: [Decline(suggestion=2, by=JAKE)]}, start_block="Crowd")

    session.run()

    assert session.refusals == []
    assert [line["block"] for line in _lines(session)] == ["Crowd"] * 11
    assert [(row["change"], row["kind"], row["name"], row.get("move"), row.get("suggestion"))
            for row in _changes(session)] == [
        (1, "suggested", "pairings", "widen", None), (2, "suggested", "block", "back", None),
        (3, "declined", "block", None, 2)]
    offered = _offered(session)
    assert [offered[index] for index in (8, 9, 10)] == [(None, _widen(1, "Crowd", 4, 5))] * 3
    assert _fed(session, "decline") == [
        "held in block Crowd: the rig's suggestion 2, to move back to Alone, declined; it is "
        "suggested again once a fresh window of answers meets its bar"]


def test_a_move_up_confirmed_lapses_the_widening_and_the_pool_carries_into_the_next_stage(
        tmp_path):
    """"The pool carries into the next stage" (the design's §3.4): the trainer widens the pool in
    Alone and later confirms the move up; Crowd's trials draw from the pool as it was widened, its
    setting's value carried over, and the widening the rig offered beside the move lapses with
    it: a hold naming it is refused with a sentence. Crowd's own bar, judged afresh, later
    suggests widening the pool it carried, its value 5."""
    script = ["right"] * 14
    session = _session(tmp_path, [_stage("Alone", set_size=1), _stage("Crowd")], script,
                       {2: [SetParameter("pairings", 5, JAKE)],
                        9: [NextBlock(by=JAKE, suggestion=2)],
                        10: [Decline(suggestion=3, by=JAKE)]})

    session.run()

    assert session.refusals == [
        ("decline", JAKE, "the rig's suggestion 3, to widen the pool in Alone, lapsed when the "
         "run left block Alone; there is nothing to hold")]
    lines = _lines(session)
    assert [line["block"] for line in lines] == ["Alone"] * 8 + ["Crowd"] * 6
    assert [line["params"]["pairings"] for line in lines] == [1, 1] + [5] * 12
    assert {_pairing(line) for line in lines[8:]} == {P1, P3}
    assert [(row["change"], row["kind"], row.get("move"), row["was"])
            for row in _changes(session)] == [
        (1, "set", None, 1), (2, "suggested", "up", "Alone"), (3, "suggested", "widen", 5),
        (4, "suggested", "widen", 5)]


def test_in_alone_any_pool_runs(tmp_path):
    """The plan's Review Focus 5: in Alone, where no distractor shows, a pairing is only the odd
    one's color (the design's §3.4), and any pool runs -- one pairing, or all three: each trial
    shows one object, the target, in the odd look its pairing gives."""
    for pooled, shown in ((2, {"green disc"}), (7, {"red disc", "green disc", "green square"})):
        session = _session(tmp_path / str(pooled), [_stage("Alone", set_size=1)],
                           ["right"] * 9, values={"pairings": pooled})

        session.run()

        assert session.refusals == [] and session.stop_kind == "operator"
        lines = _lines(session)
        assert [line["outcome"] for line in lines] == ["correct"] * 9
        assert {_pairing(line)[0] for line in lines} == shown
        arrays = [stimulus for line in lines for stimulus in line["stimuli"]
                  if stimulus["name"] == "search"]
        assert len(arrays) == 9 and all(len(array["objects"]) == 1 for array in arrays)


def test_an_empty_pool_is_refused_with_a_sentence(tmp_path):
    """The plan's Review Focus 5: a trainer who empties the pool is refused at once, with a
    sentence, before the next trial; the pool stands as it was, nothing is staged or recorded, and
    the trials draw on from it. So is a value naming no pool: no whole number, or a pairing the
    pool does not declare."""
    script = ["right"] * 5
    session = _session(tmp_path, [_stage("Crowd", criterion=None)], script,
                       {3: [SetParameter("pairings", 0, JAKE), SetParameter("pairings", 2.5, JAKE),
                            SetParameter("pairings", 8, JAKE)]}, values={"pairings": 2})

    session.run()

    guide = ("a pool is the sum of the numbers of the pairings it holds: 1, pairing 1; 2, pairing "
             "2; 4, pairing 3")
    assert session.refusals == [
        ("pairings", JAKE, "'pairings' at 0 is refused, and the previous pool stands: it holds no "
         f"pairing, so no trial could be drawn; {guide}"),
        ("pairings", JAKE, "'pairings' at 2.5 is refused, and the previous pool stands: it is no "
         f"whole number; {guide}"),
        ("pairings", JAKE, "'pairings' at 8 is refused, and the previous pool stands: it holds a "
         f"pairing beyond the 3 the pool declares; {guide}")]
    assert _changes(session) == []
    assert [_pairing(line) for line in _lines(session)] == [P2] * 5


def test_a_run_started_with_an_empty_pool_is_refused_before_it_starts(tmp_path):
    """An empty pool given at a run's start is refused before anything of the run is numbered or
    written: by `Session.run`'s backstop, by `wlx taskd`'s pre-flight, which the console's start
    asks first, and by `wlx run` before its session opens and its departure is marked."""
    session = _session(tmp_path / "run", [_stage("Crowd")], ["right"], values={"pairings": 0})
    with pytest.raises(SystemExit, match=(
            "task refused, run not started: the pool 'pairings' at 0: it holds no pairing, so no "
            "trial could be drawn; a pool is the sum")):
        session.run()
    assert _lines(session) == []

    task = _load_task(_task(tmp_path / "preflight", [_stage("Crowd")]))
    item = starting_values(task, {**VALUES, "pairings": 0}, plan="train")
    assert item.result == FAIL and "the pool 'pairings' at 0: it holds no pairing" in item.said
    assert starting_values(task, VALUES, plan="train").result != FAIL

    path = _task(tmp_path / "cli", [_stage("Crowd")])
    sets = {**{name: str(value) for name, value in _sessions.SEARCH_VALUES.items()},
            "pairings": "0"}
    with pytest.raises(SystemExit) as refused:
        main(["run", str(path), "--plan", "train", "--rig", RIG_FILE, "--view", "direct",
              "--kind", "training", "--accept-warnings", "--allocation", "tasks/allocation.py",
              "--bounds", "tasks/reference_bounds.py", "--root", str(tmp_path / "root"),
              "--session-id", "2027-01-14_01", "--subject", "REFERENCE",
              "--out-of-cage-at", time.strftime("%H:%M"), "--delivered-today", "0",
              "--trials", "2",
              *[arg for name, value in sets.items() for arg in ("--set", f"{name}={value}")]])
    assert str(refused.value).startswith(
        "task refused, session not started, nothing recorded: the pool 'pairings' at 0: it holds "
        "no pairing")
    assert not (tmp_path / "root").exists() or list((tmp_path / "root").iterdir()) == []
    assert stranded.find(tmp_path / "root") == []


def test_a_pool_no_check_let_through_ends_the_run_with_a_sentence(tmp_path):
    """The backstop: a pool that names no pairing at a boundary, however it got there, ends the
    run there with a sentence saying why, as a block that cannot draw does, never a fault."""

    def emptied(session, index):
        if index == 2:
            session.spec.values["pairings"] = 0

    session = _session(tmp_path, [_stage("Crowd")], ["right"] * 6, world=emptied)

    session.run()

    assert session.stop_kind == "completed"
    assert session.stopped_because == (
        "the pool 'pairings' at 0: it holds no pairing, so no trial could be drawn; a pool is the "
        "sum of the numbers of the pairings it holds: 1, pairing 1; 2, pairing 2; 4, pairing 3; "
        "so the run ends here")
    assert len(_lines(session)) == 3


#: A setting of choices, `chosen`, which one case puts the pool on.
_CHOSEN = ("search = _dataclasses.replace(search, params=[*search.params, Param('chosen', "
           "unit='pairings', choices=(1, 3))])\n"
           "TASK = _dataclasses.replace(TASK, structures={'search': search}, meanings={"
           "**TASK.meanings, 'chosen': Meaning(NOT_DIFFICULTY, NEITHER)}, pool="
           + POOL.replace("'pairings'", "'chosen'") + ")\n")


def _given(name: str, value: str) -> str:
    """Plan `train` again, its one stage's condition giving `name` the source `value`."""
    return (f"TASK = _dataclasses.replace(TASK, plans={{'train': Plan([Block('Crowd', "
            f"[Condition('c', {{'{name}': {value}}}, target=1)], counting=EVERY_TRIAL)])}})\n")


#: The pool declarations the load refuses (`bad-pool`), each as `_source`'s keywords and the
#: words its finding says.
_REFUSED = {
    "undeclared": (
        {"pool": POOL.replace("'pairings'", "'pairs'")},
        "the pool's setting 'pairs' is no setting the task declares"),
    "a ceiling": (
        {"pool": POOL.replace("'pairings'", "'reward_correct'")},
        "the pool's setting 'reward_correct' is a bounded setting"),
    "of choices": (
        {"extra": _CHOSEN},
        "the pool's setting 'chosen' is a setting of choices"),
    "no start": (
        {"start": None},
        "the pool's setting 'pairings' declares no start"),
    "a start naming no pool": (
        {"low": "0", "start": "0"},
        "the pool 'pairings' at 0: it holds no pairing"),
    "a difficulty setting": (
        {"meaning": "Meaning(CLEAR_CUT, STIMULUS, raising=HARDER)"},
        "the pool's setting 'pairings' is declared a difficulty setting"),
    "a look no choice": (
        {"pool": POOL.replace("(GREEN_SQUARE, RED_DISC)", "(RED_DISC, GREEN_SQUARE)")},
        "pairing 3's distractor look is no choice of 'distractor_appearance'"),
    "a setting of numbers": (
        {"pool": POOL.replace("distractor='distractor_appearance'", "distractor='set_size'")},
        "the pool's distractor setting 'set_size' is no setting of choices"),
    "a look drawn too": (
        {"extra": "TASK = _dataclasses.replace(TASK, draws={'target_appearance': Weighted("
                  "(RED_DISC, GREEN_DISC), (1, 1), repeat='same')})\n"},
        "'target_appearance' is given by the pool and drawn by the task"),
    "a look given by conditions too": (
        {"extra": _given("distractor_appearance", "GREEN_DISC")},
        "'distractor_appearance' is given by the pool and by the conditions of block 'Crowd'"),
    "the pool's setting given by conditions": (
        {"extra": _given("pairings", "3")},
        "the pool's setting 'pairings' is given by the conditions of block 'Crowd'"),
}


@pytest.mark.parametrize("case", sorted(_REFUSED))
def test_a_pool_the_rig_cannot_draw_is_refused_at_load(tmp_path, case):
    """`check.check_task`'s `bad-pool`, under the PI's rule of warnings over refusals: only what
    the rig cannot draw or the record could not be read by -- a pool on a setting the task does
    not declare, a reward size (welfare), a setting of choices, with no start or one naming no
    pool, or one declared a difficulty setting (a pool's number has no order a change could be
    judged easier by); a pairing whose look is no choice of its setting, a pool over a setting of
    numbers; and either look given by the pool and also drawn or given by conditions, never
    both. The task as `_source` writes it loads with no `bad-pool`."""
    source, said = _REFUSED[case]
    path = tmp_path / "search.py"
    path.write_text(_source([_stage("Crowd")], CONFIRMED, **source))
    allocation = _load_allocation(Path("tasks/allocation.py"))
    found = [finding for finding in check_task(_load_task(path), allocation, geometry=DIRECT,
                                               calibration=SRGB,
                                               deployment=Deployment.RIG_FIXED)
             if finding.code == "bad-pool"]
    assert len(found) == 1 and said in found[0].detail and found[0].blocking, found
    plain = tmp_path / "plain.py"
    plain.write_text(_source([_stage("Crowd")], CONFIRMED))
    assert [finding for finding in check_task(_load_task(plain), allocation, geometry=DIRECT,
                                              calibration=SRGB, deployment=Deployment.RIG_FIXED)
            if finding.code == "bad-pool"] == []


@pytest.mark.parametrize("fields, said", [
    ({"setting": "", "choices": (("a", "b"),)}, "a pool names its setting"),
    ({"setting": "pool", "choices": [("a", "b")]}, "a pool's pairings are a tuple"),
    ({"setting": "pool", "choices": ()}, "a pool has at least one pairing"),
    ({"setting": "pool", "choices": (("a", "b", "c"),)}, "two looks, the odd one's first"),
    ({"setting": "pool", "choices": (("a", "a"),)}, "the same look twice"),
    ({"setting": "pool", "choices": (("a", "b"), ("a", "b"))}, "listed twice"),
    ({"setting": "pool", "choices": (("a", "b"),), "odd": "pool"}, "three different settings"),
    ({"setting": "pool", "choices": tuple((f"c{n}", "d") for n in range(53))}, "at most 52"),
])
def test_a_pool_is_refused_as_it_is_built(fields, said):
    """A pool's own shape is refused as it is built, as a staircase's is: a setting by name, a
    tuple of at least one pairing, each two different looks, none listed twice, the pool's
    setting and its two looks' three different settings, and no more pairings than a pool's
    number holds exactly in the float a setting's value travels as."""
    with pytest.raises(ValueError, match=said):
        Pool(**fields)


def test_a_pools_number_names_its_pairings():
    """A pool's value is the sum of its pairings' numbers, 1, 2, 4 ... in the order it declares
    them; any other value names no pool, and says why."""
    pool = Pool("pool", (("blue", "red"), ("red", "blue"), ("green", "blue")))
    assert pool.pairings(5) == (("blue", "red"), ("green", "blue"))
    assert pool.pairings(5.0) == pool.pairings(5)
    assert pool.pairings(1) == (("blue", "red"),)
    assert pool.pairings(6) == (("red", "blue"), ("green", "blue"))
    assert pool.number((("green", "blue"), ("red", "blue"))) == 6
    assert [pool.unpooled(value) is None for value in (1, 7, 6.0)] == [True] * 3
    guide = ("a pool is the sum of the numbers of the pairings it holds: 1, blue>red; 2, red>blue; "
             "4, green>blue")
    assert [pool.unpooled(value) for value in (0, -1, 8, 1.5, None, True, "1")] == [
        f"it holds no pairing, so no trial could be drawn; {guide}",
        f"it holds no pairing, so no trial could be drawn; {guide}",
        f"it holds a pairing beyond the 3 the pool declares; {guide}",
        f"it is no whole number; {guide}",
        f"it has no value; {guide}", f"it is no number; {guide}", f"it is no number; {guide}"]


def test_the_cards_say_the_pool_gives_the_two_looks(tmp_path):
    """Each look's card says where its value comes from (telemetry schema 19's `source`): drawn
    each trial from its pool, in the value's place, with a field to hold a value over it; the
    pool's own card shows its number."""
    session = _session(tmp_path, [_stage("Crowd")], ["right"] * 2)

    session.run()

    running = [f for f in session.link.published if f.phase == "running"][-1]
    rows = {row.name: row for row in running.params}
    assert (rows["target_appearance"].source, rows["distractor_appearance"].source,
            rows["pairings"].source) == ("pool", "pool", "run")
    cards = fragments(running, view())["params"].split('<div class="param')
    looks = [card for card in cards if "<span>target_appearance</span>" in card
             or "<span>distractor_appearance</span>" in card]
    assert len(looks) == 2 and all(
        '<span class="pv">drawn each trial from its pool</span>' in card
        and 'placeholder="a value over its pool"' in card for card in looks)


def test_a_frame_with_a_widening_round_trips():
    """ADR-0003's golden round-trip for schema 20's `widen`: a frame's widening, and none."""
    for sent in (frame(widen=_widen(4, "Crowd", 41, 50)), frame(widen=None)):
        assert decode(encode(sent)) == sent


def test_wl_preprocs_reader_takes_the_widening_and_its_hold(tmp_path):
    """The path, not the piece: wl-preproc's reader of the rig's records takes a run's widening
    and its hold with no problem, `sequence` on neither, and its field reader reads the move it
    was told of, `"widen"`."""
    try:
        from wl_preproc.events.rigrecords import change_fields, read_rig_records
    except ImportError as exc:  # pragma: no cover - exercised by the CI job
        if os.environ.get("WLX_REQUIRE_PREPROC") == "1":
            raise AssertionError(
                f"WLX_REQUIRE_PREPROC=1 but wl-preproc is not importable ({exc})") from exc
        pytest.skip("wl-preproc checkout not beside this repo")
    session = _session(tmp_path, [_stage("Crowd")], ["right"] * 7,
                       {7: [Decline(suggestion=1, by=JAKE)]})
    session.run()

    records = read_rig_records(session.directory.parent)
    log = session.directory / "parameter_changes.jsonl"
    fields, problems = change_fields(log.read_text().splitlines())

    assert records.problems == ()
    assert [(change.name, change.sequence) for change in records.changes] == [
        ("pairings", None), ("pairings", None)]
    assert problems == []
    assert [(field.kind, field.change, json.loads(field.detail)) for field in fields] == [
        ("suggested", 1, {"move": "widen", "block": "Crowd", "bar": {"correct": 5, "of": 5},
                          "at_hardest": True}),
        ("declined", 2, {"suggestion": 1})]


def test_the_review_report_names_each_pairings_number(tmp_path):
    """The review report says what a pool's number means, so a reader of a record's `pairings: 5`
    or a reviewer of the task file knows which pairings it holds: each pairing's number in the
    pool's order, its two settings, where it starts, and that each trial draws one pairing
    uniformly."""
    report = render_task(_load_task(_task(tmp_path, [_stage("Crowd")])))

    assert "### The pool of pairings" in report
    assert ("| 1 | pairing 1 | Disc(size=1.0" in report
            and "| 4 | pairing 3 | Square(size=1.0" in report)
    assert ("Each trial draws one pairing of those `pairings` holds, each as likely, into "
            "`target_appearance` and `distractor_appearance`") in report
    assert "It starts at 1: pairing 1." in report
