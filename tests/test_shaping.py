"""The training switch, on · frozen · full task (the console settings design's §8; the PI,
2026-11-16: "both, a freeze training option and a full task option"; frozen trials "They don't
count"): `link.Shaping` moves it, staged to the next trial, recorded as a `shaping` change row and
revertible; frozen holds the stage, every staircase's level and the pool's pairings, with no move,
no suggestion and no step, its trials counted toward no bar; full task plays the plan's finished
version, `Plan.full`, as a block of its own, its staircase at its hardest level and its values over
its conditions, each line naming them `drawn: "full"`; on again reopens the stage left at its
staircase's level ("Pick up where it left"), its count, its windows and its time left as it left
them (the PI, 2026-11-18, "Pick up where it was"). Frozen time is not the stage's: its time limit
counts none of it (the PI, 2026-11-18, "Stop the clock").

Engine test material, run only in the simulator: the reference search task with a pool of three
pairings of its own looks and a confirmed progression of two stages, Fade-in, whose staircase
steps the fixation point's luminance, and Crowd, whose staircase steps the set size, with a full
task of Crowd and every pairing. Windows are short (5 answers), so a run is a few trials; no number
here is a timing claim about the rig.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import _sessions
from _rig import DIRECT
from wl_xcon.actor import Box
from wl_xcon.check import check_task
from wl_xcon.cli import _load_task
from wl_xcon.dio import Simulated as Card
from wl_xcon.link import (
    NextBlock, Revert, SetParameter, Shaping, Simulated, Staged, Stop, decode, encode,
)
from wl_xcon.photometry import SRGB
from wl_xcon.run import Scripted
from wl_xcon.task import SHAPING, Block, Condition, FullTask, Plan, SaccadeTo
from wl_xcon.taskd import Session, SessionSpec
from wl_xcon.welfare import Deployment, Simulated as Pump

WALL_NOW = 1_700_000_000.0
SEED = 7
JAKE = Box("jake")
FRAMES = 240
SEARCH = "tasks/visual_search.py"
CONFIRMED = "ByCriterion(fall_back=(0.5, 4), confirm=True)"
POOL = (
    "Pool('pairings', ((RED_DISC, GREEN_DISC), (GREEN_DISC, RED_DISC), (GREEN_SQUARE, RED_DISC)),"
    " odd='target_appearance', distractor='distractor_appearance')")
#: Fade-in's staircase, on the fixation point's luminance, and Crowd's, on the set size: three
#: right a level harder, one wrong a level easier, each from its first level.
FADE = "Staircase('fix_luminance', (20.0, 30.0, 40.0), start=0)"
CROWD = "Staircase('set_size', (4, 6, 8), start=0)"
#: The full task: Crowd, every pairing (1 + 2 + 4), at its staircase's hardest level, 8.
FULL = "FullTask('Crowd', {'pairings': 7})"


def _source(full: str | None = FULL, order: str = CONFIRMED, fade: str = FADE) -> str:
    """`visual_search` with a pool over its two looks, its setting `pairings` declared from 1 to 7,
    and one plan, `train`: Fade-in, then Crowd, each one condition every trial paying it, its bar
    to move up 4 of the last 5, and `full` its full task. Engine test material."""
    stages = ", ".join(
        f'Block("{name}", [Condition("c", {{}}, target=1)], counting=EVERY_TRIAL, '
        f'criterion=(0.8, 5), staircase={staircase})'
        for name, staircase in (("Fade-in", fade), ("Crowd", CROWD)))
    declared = "" if full is None else f", full={full}"
    return Path(SEARCH).read_text() + (
        "\n\nimport dataclasses as _dataclasses\n"
        "from wl_xcon.scheduler import EVERY_TRIAL\n"
        "from wl_xcon.task import (Block, ByCriterion, Condition, FullTask, Plan, Pool, Staircase, "
        "NEITHER, NOT_DIFFICULTY)\n"
        "RED_DISC, GREEN_DISC = Disc(size=1.0, color=RED), Disc(size=1.0, color=GREEN)\n"
        "GREEN_SQUARE = Square(size=1.0, color=GREEN)\n"
        "search = _dataclasses.replace(search, params=[*search.params, "
        "Param('pairings', unit='pairings', low=1, high=7, start=1)])\n"
        "TASK = _dataclasses.replace(\n"
        "    TASK, structures={'search': search},\n"
        "    meanings={**TASK.meanings, 'pairings': Meaning(NOT_DIFFICULTY, NEITHER, "
        "note='which pairings are drawn')},\n"
        f"    pool={POOL},\n"
        f"    plans={{'train': Plan([{stages}], order={order}{declared})}})\n")


def _trial(kind: str, values: dict) -> Scripted:
    """One trial the animal plays: `right` (`CORRECT`) or `wrong` (`WRONG_TARGET`)."""
    held = round(values["fix_hold"] * FRAMES) + 20
    looks = {frame: "fix" for frame in range(1, held + 1)}
    if kind == "right":
        target = f"search.{values['target_index']}"
        return Scripted({SaccadeTo("search.target"): held + 10},
                        inside={**looks, **{f: target for f in range(held + 1, held + 400)}})
    assert kind == "wrong", kind
    return Scripted({SaccadeTo("search.distractor"): held + 10}, inside=looks)


class _Drained(Simulated):
    """A link that queues `script[n]` as the `n`th drain begins: the loop drains once before each
    trial, so drain `n` comes before the trial numbered `n - 1` from 0, and a switch it queues is
    staged there and applies at the next boundary, before trial `n`; a move applies at once. A run
    of more drains than `BUDGET` fails, saying so."""

    BUDGET = 200

    def __init__(self, script):
        super().__init__()
        self.script, self.drains = dict(script), 0

    def drain(self) -> list:
        self.drains += 1
        assert self.drains <= self.BUDGET, "the session is not ending"
        for command in self.script.get(self.drains, ()):
            self.queue(command)
        return super().drain()


def _session(folder: Path, script: list[str], commands=None, *, full: str | None = FULL,
             pairings: int = 7, source: str | None = None) -> Session:
    """A run of plan `train` on the simulators, its animal playing `script`, stopped by a person
    once the script is played; the pool holds `pairings` (every pairing by default, so the rig never
    suggests widening it)."""
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "search.py"
    path.write_text(_source(full) if source is None else source)
    values = {**_sessions.SEARCH_VALUES, "pairings": pairings}
    spec = SessionSpec(
        task=str(path), allocation="tasks/allocation.py", root=folder,
        session_id="2027-01-14_01", subject="A", trials=len(script), frame_period=1 / FRAMES,
        seed=SEED, values=dict(values), bounds=_sessions.bounds(), already_delivered_today=0.0,
        deployment=Deployment.RIG_FIXED, geometry=DIRECT, session_kind="training",
        calibration=SRGB, plan="train",
    )
    session = Session(spec, card=Card(), pump=Pump(), link=_Drained(commands or {}))
    session.wall_clock = lambda: WALL_NOW + session.now()
    session.left_cage(at=WALL_NOW)
    session.head_fixed(at=session.wall_now())

    def built(trial, values, index):
        if index == len(script) - 1:
            session.link.queue(Stop(by=JAKE))
        return _trial(script[index], values)

    session.world = built
    return session


def _frames(session: Session) -> dict:
    """The last running frame of each boundary, by the trial about to run."""
    return {f.trial_index: f for f in session.link.published if f.phase == "running"}


def _lines(session: Session) -> list[dict]:
    return [json.loads(line) for line in (session.directory / "trials.jsonl").read_text()
            .splitlines()]


def _changes(session: Session) -> list[dict]:
    path = session.directory / "parameter_changes.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def _ends(session: Session) -> list[dict]:
    rows = [json.loads(line) for line in (session.directory / "runs.jsonl").read_text()
            .splitlines()]
    return next(row for row in rows if row["event"] == "end")["block_ends"]


# --- frozen ----------------------------------------------------------------------------------


def test_frozen_makes_no_move_no_suggestion_and_no_step(tmp_path):
    """**Frozen holds the stage, its staircase's level and the pool** (§8: "the stage, the staircase
    levels and the pairings stay exactly as they are. There are no moves, no suggestions and no
    staircase steps until it is on again"): 100 right answers frozen in Fade-in leave it in Fade-in,
    its staircase at its first level, the rig suggesting nothing -- no `suggested` row, no prompt on
    any frame -- each line saying `frozen`. The fixation point's card says what it is frozen at."""
    session = _session(tmp_path, ["right"] * 101, {1: [Shaping("frozen", JAKE)]})

    session.run()

    assert session.refusals == []
    lines = _lines(session)
    assert [line["shaping"] for line in lines] == ["on"] + ["frozen"] * 100
    assert {line["block"] for line in lines} == {"Fade-in"}
    assert {line["params"]["fix_luminance"] for line in lines} == {20.0}
    assert [row for row in _changes(session) if row["kind"] == "suggested"] == []
    frames = _frames(session)
    assert all(frames[at].suggestion is None and frames[at].widen is None for at in frames)
    assert session.blocks_run == ["Fade-in"]
    card = next(row for row in frames[50].params if row.name == "fix_luminance")
    assert (card.source, card.value) == ("frozen", 20.0)
    assert (frames[0].shaping, frames[50].shaping) == ("on", "frozen")


def test_frozen_trials_count_toward_no_bar(tmp_path):
    """**"They don't count"** (the PI, 2026-11-16): five right answers frozen enter neither the
    stage's bars nor its staircase's run. The stage's last answers hold the one given before the
    freeze until training is on again, then count on from it; its staircase steps only after three
    right answers given on -- trial 0's, then trials 6 and 7 -- so trial 8 is the first a level
    harder; and no answer was at its hardest step, so the bar to move up has none and the rig
    suggests nothing."""
    script = ["right"] * 11
    session = _session(tmp_path, script, {1: [Shaping("frozen", JAKE)],
                                          6: [Shaping("on", JAKE)]})

    session.run()

    assert session.refusals == []
    lines = _lines(session)
    assert [line["shaping"] for line in lines] == ["on"] + ["frozen"] * 5 + ["on"] * 5
    assert [line["params"]["fix_luminance"] for line in lines] == [20.0] * 8 + [30.0] * 3
    frames = _frames(session)
    assert [frames[at].bars.of for at in range(1, 11)] == [1] * 6 + [2, 3, 4, 4]
    assert {frames[at].bars.up_of for at in range(1, 11)} == {0}
    assert [row for row in _changes(session) if row["kind"] == "suggested"] == []


def test_a_standing_suggestion_is_withdrawn_on_freezing(tmp_path):
    """**A suggestion standing is withdrawn as the switch freezes training**, as a lapse withdraws
    one: the prompt to move up that five right answers at Fade-in's hardest step made (its staircase
    started there) is gone from the frame after the switch applies, and the
    trainer's later confirmation of it is refused with the sentence saying why, nothing moved."""
    script = ["right"] * 9
    hardest = _source(fade=FADE.replace("start=0", "start=2"))
    session = _session(tmp_path, script, {6: [Shaping("frozen", JAKE)],
                                          8: [NextBlock(suggestion=1, by=JAKE)]}, source=hardest)

    session.run()

    frames = _frames(session)
    assert frames[5].suggestion is not None and frames[5].suggestion.change == 1
    assert frames[6].suggestion is None
    assert [refusal[0] for refusal in session.refusals] == ["next_block"]
    assert "withdrawn as training was frozen" in session.refusals[0][2]
    assert session.blocks_run == ["Fade-in"]


def test_a_persons_move_still_applies_while_frozen(tmp_path):
    """**"The experimenter needs free control"**: frozen, a person's move by hand still moves the
    run up to Crowd, whose staircase then holds its first level too, and a person's value still
    applies; nothing is suggested."""
    script = ["right"] * 8
    session = _session(tmp_path, script, {3: [NextBlock(by=JAKE)],
                                          6: [SetParameter("fix_hold", 0.25, JAKE)]})
    session.link.script[1] = [Shaping("frozen", JAKE)]

    session.run()

    assert session.refusals == []
    lines = _lines(session)
    assert [line["block"] for line in lines] == ["Fade-in"] * 2 + ["Crowd"] * 6
    assert {line["params"]["set_size"] for line in lines[2:]} == {4}
    assert [line["params"]["fix_hold"] for line in lines] == [0.3] * 6 + [0.25] * 2
    assert [row for row in _changes(session) if row["kind"] == "suggested"] == []


# --- the full task ---------------------------------------------------------------------------


def test_full_task_plays_its_block_at_its_hardest_with_its_values(tmp_path):
    """**Full task plays `Plan.full`** (§8): from the trial after the switch, the run is in Crowd as
    a block of its own, Fade-in ending `shaping`; Crowd's staircase held at its hardest level, 8,
    and every pairing pooled, each value's line naming it `drawn: "full"`; six right answers move
    nothing and suggest nothing. A person's value still wins over the full task's."""
    script = ["right"] * 9
    session = _session(tmp_path, script, {1: [Shaping("full", JAKE)],
                                          7: [SetParameter("set_size", 6, JAKE)]}, pairings=1)

    session.run()

    assert session.refusals == []
    lines = _lines(session)
    assert [line["block"] for line in lines] == ["Fade-in"] + ["Crowd"] * 8
    assert [line["params"]["set_size"] for line in lines] == [6] + [8] * 6 + [6] * 2
    assert [line["drawn"].get("set_size") for line in lines] == [None] + ["full"] * 6 + [None] * 2
    assert {line["params"]["pairings"] for line in lines[1:]} == {7}
    assert {line["drawn"]["pairings"] for line in lines[1:]} == {"full"}
    assert lines[0]["params"]["pairings"] == 1 and "pairings" not in lines[0]["drawn"]
    assert [row for row in _changes(session) if row["kind"] == "suggested"] == []
    assert [(end["block"], end["ended"]) for end in _ends(session)] == [
        ("Fade-in", "shaping"), ("Crowd", "run")]
    frames = _frames(session)
    assert frames[3].staircase.level == 2 and frames[3].full_task is True
    card = next(row for row in frames[3].params if row.name == "set_size")
    assert (card.source, card.value) == ("full", 8)


def test_on_after_full_reopens_the_stage_left_at_its_level(tmp_path):
    """**On again, the stage left reopens at its staircase's level** ("Pick up where it left"):
    three right answers step Fade-in to 30 cd/m2; the full task plays three trials of Crowd; on
    again, Fade-in reopens as a block of its own at 30, its count and windows as it left them
    (`test_a_return_from_the_full_task_picks_the_stage_up_where_it_was`)."""
    script = ["right"] * 10
    session = _session(tmp_path, script, {5: [Shaping("full", JAKE)], 8: [Shaping("on", JAKE)]})

    session.run()

    assert session.refusals == []
    lines = _lines(session)
    assert [line["block"] for line in lines] == ["Fade-in"] * 5 + ["Crowd"] * 3 + ["Fade-in"] * 2
    assert [line["params"]["fix_luminance"] for line in lines[:5]] == [20.0] * 3 + [30.0] * 2
    assert [line["params"]["fix_luminance"] for line in lines[8:]] == [30.0, 30.0]
    assert session.blocks_run == ["Fade-in", "Crowd", "Fade-in"]
    assert [end["ended"] for end in _ends(session)] == ["shaping", "shaping", "run"]


def test_full_is_refused_for_a_plan_declaring_none(tmp_path):
    """**No full task to play** where the plan declares none (`Plan.full` `None`): refused with the
    sentence, nothing staged, the run running on in training; the page's switch grays it
    (`Telemetry.full_task`)."""
    session = _session(tmp_path, ["right"] * 3, {1: [Shaping("full", JAKE)]}, full=None)

    session.run()

    assert [(name, "declares no full task" in why) for name, _, why in session.refusals] == [
        ("shaping", True)]
    assert {line["shaping"] for line in _lines(session)} == {"on"}
    assert [row for row in _changes(session) if row["kind"] == "shaping"] == []
    assert _frames(session)[1].full_task is False


def test_a_full_task_whose_layout_refuses_it_is_refused(tmp_path):
    """**The full task is judged as it would play** (`_possible`, `_laid_out` over its block, its
    values over its conditions): one whose array would sit 40 degrees out, off the field, is refused
    with the layout's sentence as it is offered, nothing staged, the run training on."""
    session = _session(tmp_path, ["right"] * 3, {1: [Shaping("full", JAKE)]},
                       full="FullTask('Crowd', {'pairings': 7, 'array_eccentricity': 40.0})")

    session.run()

    assert [(name, "the layout it leaves refuses it" in why) for name, _, why in
            session.refusals] == [("shaping", True)]
    assert {line["shaping"] for line in _lines(session)} == {"on"}


def test_a_switch_is_refused_with_its_sentence(tmp_path):
    """Refused, nothing staged: a position the switch has not; the one already set, and the one
    already staged; and any position in a run with no training progression, no staircase and no
    pool, which has nothing to switch."""
    session = _session(tmp_path, ["right"] * 3, {1: [
        Shaping("off", JAKE), Shaping("on", JAKE), Shaping("frozen", JAKE),
        Shaping("frozen", JAKE)]})

    session.run()

    said = [why for _, _, why in session.refusals]
    assert len(said) == 3
    assert "is none of them" in said[0]
    assert "already on" in said[1]
    assert "already frozen once what is staged applies" in said[2]
    assert [row["now"] for row in _changes(session) if row["kind"] == "shaping"] == ["frozen"]
    plain = _sessions.session(tmp_path / "plain")
    plain.link = _Drained({1: [Shaping("frozen", JAKE)]})
    plain.left_cage(at=_sessions.WALL)
    plain.run()
    assert [(name, "no training to switch" in why) for name, _, why in plain.refusals] == [
        ("shaping", True)]


def test_a_shaping_switch_is_staged_recorded_and_reverted(tmp_path):
    """**Staged to the next trial, recorded as a change row, and revertible** (§8): the switch shows
    staged on the boundary it was sent at, still on there; from the next trial it is frozen, its
    `shaping` row naming the first trial it applies to, who switched it, no meaning, no strobe and
    no `sequence` (XC-513's group 4). A revert to the run's start takes it back, written as a
    `shaping` row of the revert's change id naming its moment, previewed as "training → on"."""
    session = _session(tmp_path, ["right"] * 7, {2: [Shaping("frozen", JAKE)],
                                                 5: [Revert(0, JAKE)]})

    session.run()

    assert session.refusals == []
    frames = _frames(session)
    assert frames[1].staged == (Staged("shaping", "on", "frozen", JAKE, False, "shaping"),)
    assert frames[1].shaping == "on" and frames[2].shaping == "frozen"
    start = next(moment for moment in frames[3].moments if moment.change == 0)
    assert start.changes == ("training → on",)
    lines = _lines(session)
    assert [line["shaping"] for line in lines] == ["on"] * 2 + ["frozen"] * 3 + ["on"] * 2
    rows = [row for row in _changes(session) if row["kind"] == "shaping"]
    assert [(row["name"], row["was"], row["now"], row["meaning"], row["event_code"],
             "sequence" in row, row["trial_number"], row["by"]["name"]) for row in rows] == [
        ("shaping", "on", "frozen", None, None, False, lines[2]["trial_number"], "jake"),
        ("shaping", "frozen", "on", None, None, False, lines[5]["trial_number"], "jake")]
    assert rows[1]["moment"] == 0 and "moment" not in rows[0]


def test_each_trial_line_says_its_shaping(tmp_path):
    """**Each trial line gains `shaping`**, the switch's state for that trial (XC-513's group 4),
    on, frozen and full in turn; a run starts on."""
    script = ["right"] * 7
    session = _session(tmp_path, script, {1: [Shaping("frozen", JAKE)],
                                          3: [Shaping("full", JAKE)], 5: [Shaping("on", JAKE)]})

    session.run()

    assert session.refusals == []
    assert [line["shaping"] for line in _lines(session)] == (
        ["on"] + ["frozen"] * 2 + ["full"] * 2 + ["on"] * 2)
    assert set(SHAPING) == {"on", "frozen", "full"}


# --- the declaration ------------------------------------------------------------------------


@pytest.mark.parametrize("full, said", [
    ("FullTask('Solo', {})", "plays block 'Solo', which the plan does not have"),
    ("FullTask('Crowd', {'loudness': 3})", "'loudness', which is no setting the task declares"),
    ("FullTask('Crowd', {'set_size': 20})", "'set_size' 20, outside its limits"),
    ("FullTask('Crowd', {'pairings': 2.5})", "no whole number"),
    ("FullTask('Crowd', {'reward_correct': 0.2})", "a bounded setting"),
])
def test_a_bad_full_task_is_refused_at_load(tmp_path, full, said):
    """**Checked at load** (`bad-full-task`): a block the plan has, settings the task declares and
    no bounded one, values inside their limits, a pool's value naming a pool. And its shape is
    refused as it is built."""
    path = tmp_path / "search.py"
    path.write_text(_source(full))

    found = [f for f in check_task(_load_task(path)) if f.code == "bad-full-task"]

    assert len(found) == 1 and said in found[0].detail and found[0].blocking
    assert [f.code for f in check_task(_load_task(_write(tmp_path / "good.py", _source())))
            if f.code == "bad-full-task"] == []
    with pytest.raises(ValueError, match="names its block by text"):
        FullTask(3)
    with pytest.raises(ValueError, match="is a FullTask"):
        Plan([Block("b", [Condition("c", {}, target=1)])], full="Crowd")


def _write(path: Path, source: str) -> Path:
    path.write_text(source)
    return path


def test_the_switch_round_trips_on_the_wire():
    """`shaping` on the wire: a position the switch has, sent by a person; any other refused at the
    wire, as the session refuses it too."""
    assert decode is not None and encode is not None
    from wl_xcon.link import CommandRefused, _decode_command, _encode_command

    assert _decode_command(_encode_command(Shaping("full", JAKE))) == Shaping("full", JAKE)
    with pytest.raises(CommandRefused, match="none of them"):
        _decode_command(_encode_command(Shaping("off", JAKE)))


# --- the stage's clock and its return (the PI, 2026-11-18) -----------------------------------

#: Fade-in with a time limit of 6 s of trials: each scripted right answer here takes 1.125 s (270
#: frames at 240 Hz, its ITI included), so an unfrozen Fade-in ends on its time after 6 trials.
TIMED = "criterion=(0.8, 5), time_limit_s=6.0, staircase=Staircase('fix_luminance'"


def _timed() -> str:
    source = _source()
    assert source.count("criterion=(0.8, 5), staircase=Staircase('fix_luminance'") == 1
    return source.replace("criterion=(0.8, 5), staircase=Staircase('fix_luminance'", TIMED)


def _fade_ins(session: Session) -> list[str]:
    """Each line's training switch, for the lines Fade-in played."""
    return [line["shaping"] for line in _lines(session) if line["block"] == "Fade-in"]


def test_frozen_stops_the_stages_clock_and_on_picks_up_its_time_left(tmp_path):
    """**"Stop the clock"** (the PI, 2026-11-18: "frozen time doesn't count toward the stage's time
    limit. Switching back on picks up with the time the stage had left"): Fade-in, 6 s, three trials
    in (2.625 s left), is frozen for nine trials, 10.125 s, far past its limit; its time left stands
    at 2.625 s on every frozen boundary, it does not move the moment training is on, and it ends on
    its time after exactly the three trials that 2.625 s takes -- the six on trials an unfrozen
    Fade-in runs."""
    plain = _session(tmp_path / "plain", ["right"] * 10, source=_timed())
    plain.run()
    assert _fade_ins(plain) == ["on"] * 6

    session = _session(tmp_path / "frozen", ["right"] * 20, {
        3: [Shaping("frozen", JAKE)], 12: [Shaping("on", JAKE)]}, source=_timed())

    session.run()

    assert session.refusals == []
    frames = _frames(session)
    assert [frames[at].block_left_s for at in range(3, 13)] == [2.625] * 10
    assert _fade_ins(session) == ["on"] * 3 + ["frozen"] * 9 + ["on"] * 3
    assert _lines(session)[12]["block"] == "Fade-in"
    assert [(end["block"], end["ended"], end["after_trial"]) for end in _ends(session)][0] == (
        "Fade-in", "time", 14)


def test_two_freezes_both_leave_the_stages_clock_still(tmp_path):
    """**Several freezes add up**: Fade-in frozen for four trials, on for two, frozen for five, then
    on runs exactly the six on trials its 6 s take, whatever the frozen time between them."""
    session = _session(tmp_path, ["right"] * 24, {
        2: [Shaping("frozen", JAKE)], 6: [Shaping("on", JAKE)],
        8: [Shaping("frozen", JAKE)], 13: [Shaping("on", JAKE)]}, source=_timed())

    session.run()

    assert session.refusals == []
    assert _fade_ins(session) == (
        ["on"] * 2 + ["frozen"] * 4 + ["on"] * 2 + ["frozen"] * 5 + ["on"] * 2)
    assert _ends(session)[0]["ended"] == "time"


def test_the_full_tasks_time_is_not_the_stages(tmp_path):
    """**With a return from the full task, the stage's time left is as it was**: Fade-in, two trials
    in (3.75 s left), plays the full task for eight trials, 9 s, past its limit; back on, it reopens
    with 3.75 s left and runs exactly the four trials an unfrozen Fade-in has left."""
    session = _session(tmp_path, ["right"] * 20, {
        2: [Shaping("full", JAKE)], 10: [Shaping("on", JAKE)]}, source=_timed())

    session.run()

    assert session.refusals == []
    frames = _frames(session)
    assert (frames[1].block_left_s, frames[2].block_left_s) == (4.875, None)
    assert frames[10].block_left_s == 3.75
    assert [line["block"] for line in _lines(session)][:16] == (
        ["Fade-in"] * 2 + ["Crowd"] * 8 + ["Fade-in"] * 4 + ["Crowd"] * 2)
    assert [end["ended"] for end in _ends(session)][:3] == ["shaping", "shaping", "time"]


#: Fade-in at its hardest step from its first trial, so each right answer enters its bar to move
#: up as well as its bar to move back.
HARDEST = FADE.replace("start=0", "start=2")


def test_a_return_from_the_full_task_picks_the_stage_up_where_it_was(tmp_path):
    """**"Pick up where it was"** (the PI, 2026-11-18: "the stage resumes with its trial count and
    its last-N-trials window as you left them; the full-task trials in between are skipped
    over"): four right answers into Fade-in (its bars 4 of 5), three full-task trials of Crowd,
    then on: Fade-in reopens with both bars as they were, and one more right answer completes the
    window, the rig suggesting the move up at that boundary with the bars a Fade-in run with no
    full task suggests it on after its fifth."""
    plain = _session(tmp_path / "plain", ["right"] * 6, source=_source(fade=HARDEST))
    plain.run()
    alone = _frames(plain)
    assert alone[4].suggestion is None and alone[5].suggestion is not None

    session = _session(tmp_path / "full", ["right"] * 9, {
        4: [Shaping("full", JAKE)], 7: [Shaping("on", JAKE)]}, source=_source(fade=HARDEST))

    session.run()

    assert session.refusals == []
    assert [line["block"] for line in _lines(session)] == (
        ["Fade-in"] * 4 + ["Crowd"] * 3 + ["Fade-in"] * 2)
    frames = _frames(session)
    assert (frames[3].bars.of, frames[3].bars.up_of) == (3, 3)
    assert frames[7].bars == alone[4].bars
    assert (frames[7].bars.of, frames[7].bars.up_of) == (4, 4)
    assert frames[7].suggestion is None
    assert frames[8].suggestion is not None and frames[8].bars == alone[5].bars
    assert frames[8].suggestion.move == alone[5].suggestion.move


def test_a_stage_back_from_the_full_task_ends_on_its_carried_count(tmp_path):
    """**Its trial count carried**: a Fade-in of six trials, moving up of itself, four trials in,
    then three of the full task, then on: two more trials end it on its rule, as six would end it
    with no full task, and the full task's trials are in its count nowhere. **Each block reports its
    own trials** in the run's end row: four, three, two -- no trial counted twice."""
    counted = _source(order="ByCriterion(fall_back=(0.5, 4))").replace(
        "criterion=(0.8, 5), staircase=Staircase('fix_luminance'",
        "trials=6, staircase=Staircase('fix_luminance'")
    assert "trials=6" in counted
    session = _session(tmp_path, ["right"] * 12, {
        4: [Shaping("full", JAKE)], 7: [Shaping("on", JAKE)]}, source=counted)

    session.run()

    assert session.refusals == []
    assert [line["block"] for line in _lines(session)][:10] == (
        ["Fade-in"] * 4 + ["Crowd"] * 3 + ["Fade-in"] * 2 + ["Crowd"])
    assert [end["ended"] for end in _ends(session)][:3] == ["shaping", "shaping", "rule"]
    rows = [json.loads(line) for line in (session.directory / "runs.jsonl").read_text()
            .splitlines()]
    end = next(row for row in rows if row["event"] == "end")
    assert [(each["block"], each["trials"]) for each in end["conditions"]][:3] == [
        ("Fade-in", 4), ("Crowd", 3), ("Fade-in", 2)]


def test_a_stage_back_from_the_full_task_meets_its_rule_on_its_carried_window(tmp_path):
    """**Its criterion window carried**, in a progression that moves of itself: four right answers
    into Fade-in (its rule, 80% of its last 5 answers right), three of the full task, then on:
    the first right answer back fills its window of five, and Fade-in ends on its rule at that
    boundary, as its fifth would end it with no full task."""
    session = _session(tmp_path, ["right"] * 11, {
        4: [Shaping("full", JAKE)], 7: [Shaping("on", JAKE)]},
        source=_source(order="ByCriterion(fall_back=(0.5, 4))"))

    session.run()

    assert session.refusals == []
    assert [line["block"] for line in _lines(session)][:9] == (
        ["Fade-in"] * 4 + ["Crowd"] * 3 + ["Fade-in"] + ["Crowd"])
    assert [end["ended"] for end in _ends(session)][:3] == ["shaping", "shaping", "rule"]
