"""What the trainer's panel reads from the frame (the pop-out search build's Task 7; its design,
`docs/superpowers/specs/2026-11-07-popout-search-design.md` §3.5, approved by the PI on
2026-11-07, who accepted the sketch of the trainer's screen with short stage names).

During the session the trainer sees "the stage by name, the staircase's level and its lock, the
last 50 trials' percent correct and errors by kind, the pairings on, and, when the bar is met, a
prompt naming why". The stage's name, the suggestions and the parameter cards were in the frame
already (schema 17, 19 and 20); what the panel needed beside them, each added within schema 20
(the build's one bump), read between trials from the object the record is written from, never
per frame and never recomputed by a console:

- **the open block's staircase** (`Telemetry.staircase`): its setting, levels, the level it is at
  -- before the block's first trial, the one it will start at -- whether a person holds the setting
  (the lock, TSK-32), and its rule;
- **the stage's last answers as the bars judge them** (`Telemetry.bars`), under a confirmed
  progression: toward moving back each trial's first answer, the wrong ones by outcome, and the
  trials left out of them beside it (the design's §3.4: no fixation and early saccades "left out of
  the 50 and shown beside it, so the trainer sees them"); toward moving up the answers at the
  stage's hardest step; each bar's proportion;
- **the pool's pairings in its declared order, with its value** (`Telemetry.pool`): a console
  draws the widening's picker from them and sends the value now plus the numbers of the pairings
  ticked (`task.Pool`, Task 5's whole number).

Engine test material, run only in the simulator: the reference search task with a pool of three
pairings of its own looks and a plan of two stages, as in `test_pairing_pool.py`. Windows are short
(4 to 6 answers) so a run is a few trials; the task's own are 50.
"""

from __future__ import annotations

import json
from pathlib import Path

import msgpack
import pytest

import _sessions
from _frames import frame
from _rig import DIRECT
from wl_xcon.actor import Box
from wl_xcon.dio import Simulated as Card
from wl_xcon.link import (
    Bars, Decline, FrameError, HandBack, NextBlock, Pooled, SetParameter, Simulated, StaircaseRow,
    Stop, decode, encode,
)
from wl_xcon.photometry import SRGB
from wl_xcon.run import Scripted
from wl_xcon.task import SaccadeTo
from wl_xcon.taskd import RunSpec, Session, SessionSpec
from wl_xcon.welfare import Deployment, Simulated as Pump

WALL_NOW = 1_700_000_000.0
SEED = 7
JAKE = Box("jake")
FRAMES = 240
SEARCH = "tasks/visual_search.py"
#: The confirmed progression's order, with short windows: back under 50% of the last 4 first
#: answers, each move a person's to confirm.
CONFIRMED = "ByCriterion(fall_back=(0.5, 4), confirm=True)"
POOL = (
    "Pool('pairings', ((RED_DISC, GREEN_DISC), (GREEN_DISC, RED_DISC), (GREEN_SQUARE, RED_DISC)),"
    " odd='target_appearance', distractor='distractor_appearance')")
#: A staircase on the set size, three right a level harder and one wrong a level easier.
STEPS = "Staircase('set_size', (4, 6, 8){start})"


def _source(stages: list[str], order: str) -> str:
    """`visual_search`'s source with a pool over its two looks, its pool setting `pairings`
    declared from 1 to 7, and one plan, `train`, of `stages` in `order`. Engine test material."""
    return Path(SEARCH).read_text() + (
        "\n\nimport dataclasses as _dataclasses\n"
        "from wl_xcon.scheduler import EVERY_TRIAL\n"
        "from wl_xcon.task import (Block, ByCriterion, Condition, Plan, Pool, Staircase, "
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
        f"    plans={{'train': Plan([{', '.join(stages)}], order={order})}})\n")


def _stage(name: str, criterion=(0.8, 5), staircase: str | None = None) -> str:
    """A stage's source: one condition, every trial paying it, its `criterion` the up bar, and the
    staircase given."""
    stepped = "" if staircase is None else f", staircase={staircase}"
    rule = "" if criterion is None else f", criterion={criterion}"
    return (f'Block("{name}", [Condition("c", {{}}, target=1)], counting=EVERY_TRIAL'
            f'{rule}{stepped})')


def _trial(kind: str, values: dict) -> Scripted:
    """One trial the animal plays as `kind` says: `right` (`CORRECT`), `wrong`, a look at a
    distractor (`WRONG_TARGET`), `early`, leaving the fixation point before the array, the go
    (`FIXATION_BREAK`), and `away`, never looking at the fixation point (`NO_FIXATION`)."""
    held = round(values["fix_hold"] * FRAMES) + 20
    target = f"search.{values['target_index']}"
    looks = {frame: "fix" for frame in range(1, held + 1)}
    if kind == "right":
        return Scripted({SaccadeTo("search.target"): held + 10},
                        inside={**looks, **{f: target for f in range(held + 1, held + 400)}})
    if kind == "wrong":
        return Scripted({SaccadeTo("search.distractor"): held + 10}, inside=looks)
    if kind == "early":
        return Scripted({}, inside={frame: "fix" for frame in range(1, 6)})
    assert kind == "away", kind
    return Scripted({}, inside={})


class _Drained(Simulated):
    """A link that queues `script[n]` as the `n`th drain begins: the loop drains once before each
    trial, so drain `n` comes before the trial numbered `n - 1` from 0. A value it queues is staged
    at that drain and applies at the next boundary, the trial after; a move applies at once."""

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
             order: str = CONFIRMED, pairings: int = 7, plan: str | None = "train",
             service: bool = False) -> Session:
    """A run of plan `train` of `stages` (or, with `plan` `None`, the task's plain run) on the
    simulators, its animal playing `script`, the run stopped by a person once the script is played;
    the pool holds `pairings` (every pairing, by default, so the rig never suggests widening it).
    With `service`, a `wlx taskd` session, opened, whose run `run_plan` starts."""
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "search.py"
    path.write_text(_source(stages, order))
    values = {**_sessions.SEARCH_VALUES, "pairings": pairings}
    spec = SessionSpec(
        task="" if service else str(path), allocation="tasks/allocation.py", root=folder,
        session_id="2027-01-14_01", subject="A", trials=len(script), frame_period=1 / FRAMES,
        seed=SEED, values=dict(values), bounds=_sessions.bounds(), already_delivered_today=0.0,
        deployment=Deployment.RIG_FIXED, geometry=DIRECT, session_kind="training",
        calibration=SRGB, plan=None if service else plan,
    )
    session = Session(spec, card=Card(), pump=Pump(), link=_Drained(commands or {}),
                      service=service)
    session.wall_clock = lambda: WALL_NOW + session.now()
    session.left_cage(at=WALL_NOW)
    session.head_fixed(at=session.wall_now())
    if service:
        session.open(how="wlx taskd")
        session.run_plan = lambda: session.run(RunSpec(
            task=str(path), trials=len(script), seed=SEED, values=dict(values), plan=plan))

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
    path = session.directory / "trials.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines()]


def _ladder(level: int, held: bool = False) -> StaircaseRow:
    return StaircaseRow("set_size", (4, 6, 8), level, held, 3, 1)


# --- the staircase ---------------------------------------------------------------------------


def test_the_frame_carries_the_staircase_its_level_and_whether_a_person_holds_it(tmp_path):
    """"The staircase's level and its lock" (§3.5): each boundary's frame carries the open block's
    staircase at the level the next trial will take -- three right in a row step it from 4 to 6
    objects -- and, once a person's value holds the setting (TSK-32's lock), says it is held, at
    the level the staircase stopped at, which held trials do not step; a hand-back resumes it at the
    level nearest the value held (Review Focus 1), and the frame says so before the trial that
    takes it."""
    session = _session(tmp_path, [_stage("Crowd", staircase=STEPS.format(start=", start=0"))],
                       ["right"] * 8, {5: [SetParameter("set_size", 4, JAKE)],
                                       7: [HandBack("set_size", JAKE)]})

    session.run()

    assert session.refusals == []
    frames = _frames(session)
    assert [frames[index].staircase for index in range(8)] == [
        _ladder(0), _ladder(0), _ladder(0), _ladder(1), _ladder(1), _ladder(1, held=True),
        _ladder(1, held=True), _ladder(0)]
    # What the frames said is what the trials took.
    assert [line["params"]["set_size"] for line in _lines(session)] == [4, 4, 4, 6, 6, 4, 4, 4]


def test_a_stage_opened_shows_its_own_staircase_where_it_will_start(tmp_path):
    """A stage the trainer moves the run up to shows, at the boundary it opens, its own staircase
    at the level its first trial will take -- never the stage before's, left at its hardest step.
    A stage with none shows none."""
    easy = _stage("Easy", (0.8, 3), STEPS.format(start=", start=2"))
    hard = _stage("Hard", staircase=STEPS.format(start=", start=0"))
    session = _session(tmp_path, [easy, hard], ["right"] * 5,
                       {4: [NextBlock(suggestion=1, by=JAKE)]})

    session.run()

    assert session.refusals == []
    frames = _frames(session)
    assert [(frames[i].block, frames[i].staircase) for i in range(5)] == [
        ("Easy", _ladder(2)), ("Easy", _ladder(2)), ("Easy", _ladder(2)), ("Hard", _ladder(0)),
        ("Hard", _ladder(0))]
    assert [line["params"]["set_size"] for line in _lines(session)] == [8, 8, 8, 4, 4]


# --- the last answers ------------------------------------------------------------------------


def test_the_frame_carries_the_last_answers_their_errors_by_kind_and_the_trials_left_out(tmp_path):
    """"The last 50 trials' percent correct and errors by kind" (§3.5), the last 50 being answers
    only, "no-fixation trials and early saccades ... left out of the 50 and shown beside it" (§3.4):
    each frame carries the stage's last answers toward moving back (here the last 4), right and
    wrong by outcome, the trials left out of them since the answer before the first of them, and,
    toward moving up, the answers at the stage's hardest step (here 6, no staircase: every answer),
    with each bar's proportion. An early saccade and a trial never fixated wait beside the window
    until an answer comes; they leave it with the answer after them."""
    script = ["right", "wrong", "early", "away", "right", "wrong", "right", "right", "right"]
    session = _session(tmp_path, [_stage("Easy", (0.8, 6)), _stage("Hard")], script)

    session.run()

    assert session.refusals == []
    frames = _frames(session)
    aside = {"fixation_break": 1, "no_fixation": 1}
    assert frames[0].bars == Bars(0, 0, 4, {}, {}, 0, 0, 6, 0.8, 0.5)
    assert frames[4].bars == Bars(1, 2, 4, {"wrong_target": 1}, aside, 1, 2, 6, 0.8, 0.5)
    assert frames[7].bars == Bars(2, 4, 4, {"wrong_target": 2}, aside, 3, 5, 6, 0.8, 0.5)
    assert frames[8].bars == Bars(3, 4, 4, {"wrong_target": 1}, aside, 4, 6, 6, 0.8, 0.5)
    assert frames[9].bars == Bars(3, 4, 4, {"wrong_target": 1}, {}, 4, 6, 6, 0.8, 0.5)


def test_the_trials_left_out_start_afresh_with_their_window(tmp_path):
    """The trials left out beside the window go with it whenever it starts afresh: as the trainer
    moves the run up a stage (two waiting in Easy are not Hard's), as the pool changes (the bars
    judge the pairings pooled now), and as the trainer holds a move back ("After 50 new tries")."""
    script = ["right", "right", "right", "early", "away", "early", "early",
              "wrong", "wrong", "wrong", "wrong", "early", "right"]
    session = _session(tmp_path, [_stage("Easy", (0.8, 3)), _stage("Hard")], script, {
        6: [NextBlock(suggestion=1, by=JAKE)], 7: [SetParameter("pairings", 3, JAKE)],
        13: [Decline(suggestion=3, by=JAKE)]})

    session.run()

    assert session.refusals == []
    frames = _frames(session)
    assert frames[4].bars.left_out == {"fixation_break": 1}
    assert frames[5].bars == Bars(0, 0, 4, {}, {}, 0, 0, 5, 0.8, 0.5)
    assert frames[6].bars == Bars(0, 0, 4, {}, {"fixation_break": 1}, 0, 0, 5, 0.8, 0.5)
    assert frames[7].bars == Bars(0, 0, 4, {}, {}, 0, 0, 5, 0.8, 0.5)
    assert frames[11].bars == Bars(0, 4, 4, {"wrong_target": 4}, {}, 0, 4, 5, 0.8, 0.5)
    assert (frames[11].suggestion.change, frames[11].suggestion.move) == (3, "back")
    assert frames[12].bars == Bars(0, 0, 4, {}, {}, 0, 4, 5, 0.8, 0.5)


def test_no_bars_outside_a_confirmed_progression_and_nothing_between_runs(tmp_path):
    """The bars are a confirmed progression's (`ByCriterion(confirm=True)`): a plan that moves on
    its own carries none, nor a plain run of a task with no staircase, which carries its pool; and
    between a `wlx taskd` session's runs, when no block is open, no frame carries any of the
    three."""
    stages = [_stage("Easy", (0.8, 6)), _stage("Hard")]
    own = _session(tmp_path / "own", stages, ["right"] * 2,
                   order="ByCriterion(fall_back=(0.5, 4))")
    plain = _session(tmp_path / "plain", stages, ["right"] * 2, plan=None)
    taskd = _session(tmp_path / "taskd", [_stage("Easy", (0.8, 6), STEPS.format(start="")),
                                          _stage("Hard")], ["right"] * 2, service=True)

    own.run()
    plain.run()
    taskd.run_plan()

    shown = [(f.staircase, f.bars) for f in _frames(own).values()]
    assert shown and set(shown) == {(None, None)}
    assert {(f.staircase, f.bars) for f in _frames(plain).values()} == {(None, None)}
    assert {f.pool for f in _frames(plain).values()} == {
        Pooled("pairings", ("pairing 1", "pairing 2", "pairing 3"), 7)}
    assert {(f.staircase is not None, f.bars is not None, f.pool is not None)
            for f in _frames(taskd).values()} == {(True, True, True)}
    assert taskd.phase == "between_runs"
    taskd._publish()
    last = taskd.link.published[-1]
    assert last.phase == "between_runs" and (last.staircase, last.bars, last.pool) == (
        None, None, None)


# --- the pool --------------------------------------------------------------------------------


def test_the_frame_carries_the_pools_pairings_in_their_order_and_its_value(tmp_path):
    """"The pairings on" (§3.5), and what a console needs to widen the pool: each frame carries
    the pool's pairings in words in the order the pool declares them -- the n-th worth 2 ** n --
    and its setting's value now, which a person's `set` changes from the boundary it applies at."""
    session = _session(tmp_path, [_stage("Easy", (0.8, 6)), _stage("Hard")], ["right"] * 5,
                       {3: [SetParameter("pairings", 5, JAKE)]}, pairings=1)

    session.run()

    assert session.refusals == []
    frames = _frames(session)
    words = ("pairing 1", "pairing 2", "pairing 3")
    assert [frames[index].pool for index in range(5)] == [
        Pooled("pairings", words, 1)] * 3 + [Pooled("pairings", words, 5)] * 2


# --- the wire --------------------------------------------------------------------------------

SHOWN = dict(
    staircase=StaircaseRow("distractor_luminance", (0.25, 0.5, 1.0), 1, True, 3, 1),
    bars=Bars(39, 50, 50, {"wrong_target": 7, "no_response": 4}, {"fixation_break": 4, "hang": 1},
              41, 50, 50, 0.8, 0.5),
    pool=Pooled("pairings", ("blue>red", "red>blue", "purple>red"), 5),
)


def test_the_three_survive_the_wire_and_none_stays_none():
    """Each of the three travels on the frame as it was read, and a frame with none of them
    decodes with none, never an empty row a console would draw."""
    sent = frame(**SHOWN)

    assert decode(encode(sent)) == sent
    restored = decode(encode(frame()))
    assert (restored.staircase, restored.bars, restored.pool) == (None, None, None)


@pytest.mark.parametrize("broken", [
    ("staircase", None, "gone"), ("staircase", "held", "gone"), ("staircase", "held", 1),
    ("staircase", "levels", "gone"), ("staircase", "level", "gone"),
    ("bars", None, "gone"), ("bars", "wrong", "gone"), ("bars", "wrong", ["wrong_target", 7]),
    ("bars", "left_out", 4), ("bars", "up_at", "gone"),
    ("pool", None, "gone"), ("pool", "pairings", "gone"), ("pool", "value", "gone"),
], ids=lambda broken: "-".join(map(str, broken)))
def test_a_frame_missing_or_misshaping_one_is_refused_as_a_frame(broken):
    """The frame's decoder checks each field it reads (`FrameError`, which a console catches and
    shows nothing of): a field gone, a row's field gone, a lock that is no true or false, a count by
    outcome that is no mapping."""
    name, part, value = broken
    bad = msgpack.unpackb(encode(frame(**SHOWN)), raw=False)
    if part is None:
        del bad[name]
    elif value == "gone":
        del bad[name][part]
    else:
        bad[name][part] = value

    with pytest.raises(FrameError):
        decode(msgpack.packb(bad))
