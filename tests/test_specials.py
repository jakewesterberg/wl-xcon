"""Special trials (the pop-out revision's Task 3; its design,
`docs/superpowers/specs/2026-11-16-popout-revision-design.md` §4, approved by the PI on 2026-11-16,
"Approve both").

The PI's answers: four kinds of special trial, three catches and a probe, "A percentage per kind";
counted in the stage's bars like any other trial ("An error, counted"); "Only normal trials move
it" -- a special trial never steps the stage's staircase, so the staircase keeps tracking about 79%
right on search itself [@levitt1971transformed]. The controller's calls (the plan's Task 3): a
repeat of a special trial is the same kind; shares past 100 are drawn in proportion, warned at
load; only a trial of the task's default structure can be special; a special trial at the
staircase's last level counts toward moving up, as any trial there does.

A task declares each kind (`task.Special`: its name, the setting giving its percentage, the
structure it plays) in `Task.specials`. The run draws each trial's kind between trials from its
seed (`taskd.Session._special`), plays the kind's structure with the stage's values, its
staircase's value and its pairing, records it in the stage's bars and its condition's count, and
steps no staircase. Each line says its kind (`trial_kind`, as wl-preproc renamed it on
2026-11-19, XC-543) and whether it stepped (`stepped`); the start row names each kind
(`specials`).

Engine test material, run only in the simulator: the reference search task with a pool of three
pairings (as `test_pairing_pool.py` builds it), a staircase on its set size, and two special kinds,
`target_absent` and `odd_one_alone`, each playing a copy of the search under a name of its own
(Task 4 gives the catch its own array), their percentages `absent_percent` and `alone_percent`.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import _sessions
from _rig import DIRECT
from wl_xcon import resume, variation
from wl_xcon.actor import Box
from wl_xcon.check import check_task
from wl_xcon.cli import _load_task
from wl_xcon.dio import Simulated as Card
from wl_xcon.link import NextBlock, SetParameter, Simulated, Stop
from wl_xcon.photometry import SRGB
from wl_xcon.review import render_task
from wl_xcon.run import Scripted
from wl_xcon.scheduler import Draw
from wl_xcon.task import NORMAL, SPECIAL_UNIT, Condition, P, Param, SaccadeTo, Special, Task
from wl_xcon.taskd import RunSpec, Session, SessionSpec, went_on
from wl_xcon.welfare import Deployment, Simulated as Pump

WALL_NOW = 1_700_000_000.0
SEED = 7
JAKE = Box("jake")
FRAMES = 240
SEARCH = "tasks/visual_search.py"
#: A confirmed progression with a window of ten first answers shown on the panel, so a short run's
#: every answer is in it.
CONFIRMED = "ByCriterion(fall_back=(0.5, 10), confirm=True)"
POOL = (
    "Pool('pairings', ((RED_DISC, GREEN_DISC), (GREEN_DISC, RED_DISC), (GREEN_SQUARE, RED_DISC)),"
    " odd='target_appearance', distractor='distractor_appearance')")
#: The two kinds, in their declared order.
SPECIALS = ("(Special('target_absent', P('absent_percent'), 'absent'), "
            "Special('odd_one_alone', P('alone_percent'), 'alone'))")
#: The staircase on the set size: 4, 6, 8 and 10 objects, three right a level harder, one wrong a
#: level easier; the run's six objects put it at 6 to start.
STAIRS = "Staircase('set_size', (4, 6, 8, 10))"
VALUES = {**_sessions.SEARCH_VALUES, "pairings": 1, "absent_percent": 0, "alone_percent": 0}
ABSENT, ALONE = "target_absent", "odd_one_alone"


def _source(stages: list[str], order: str = CONFIRMED, *, specials: str = SPECIALS,
            structures: str = "{'search': search, 'absent': search, 'alone': search}",
            share: str = "unit='percent', low=0, high=100", absent_start: str = "0",
            alone_start: str = "0", extra: str = "") -> str:
    """`visual_search`'s source with a pool over its two looks, two percentages of special trials
    declared as `share` says, starting at `absent_start` and `alone_start`, `structures` (each
    special kind playing a copy of the search under its own name), `specials`, and one plan,
    `train`, of `stages` in `order`; `extra`, more source after it. Engine test material."""
    text = Path(SEARCH).read_text()
    return text + (
        "\n\nimport dataclasses as _dataclasses\n"
        "from wl_xcon.scheduler import EVERY_TRIAL\n"
        "from wl_xcon.task import (Block, ByCriterion, Condition, Plan, Pool, Special, Staircase, "
        "NEITHER, NOT_DIFFICULTY)\n"
        "RED_DISC, GREEN_DISC = Disc(size=1.0, color=RED), Disc(size=1.0, color=GREEN)\n"
        "GREEN_SQUARE = Square(size=1.0, color=GREEN)\n"
        "WHY = 'a percentage of trials is at most 100'\n"
        "search = _dataclasses.replace(search, params=[*search.params, "
        "Param('pairings', unit='pairings', low=1, high=7, start=1), "
        f"Param('absent_percent', {share}, start={absent_start}, whole=True, why=WHY), "
        f"Param('alone_percent', {share}, start={alone_start}, whole=True, why=WHY)])\n"
        "SHARE = Meaning(NOT_DIFFICULTY, NEITHER, note='how many trials are special')\n"
        "TASK = _dataclasses.replace(\n"
        f"    TASK, structures={structures},\n"
        "    meanings={**TASK.meanings, 'pairings': Meaning(NOT_DIFFICULTY, NEITHER, "
        "note='which pairings are drawn'), 'absent_percent': SHARE, 'alone_percent': SHARE},\n"
        f"    pool={POOL}, specials={specials},\n"
        f"    plans={{'train': Plan([{', '.join(stages)}], order={order})}})\n"
        + extra)


def _stage(name: str, *, staircase: str | None = STAIRS, extra: str = "",
           structure: str | None = None) -> str:
    """A stage's source: one condition, naming `structure` where given, every trial paying it
    (`EVERY_TRIAL`), its set size stepped by `staircase`, and `extra`, more of its fields."""
    stepped = "" if staircase is None else f", staircase={staircase}"
    named = "" if structure is None else f", structure={structure!r}"
    return (f'Block("{name}", [Condition("c", {{}}, target=1{named})], counting=EVERY_TRIAL'
            f'{stepped}{extra})')


def _trial(kind: str, values: dict) -> Scripted:
    """One trial the animal plays as `kind` says: `right` (`CORRECT`), `wrong` (`WRONG_TARGET`)
    and `early`, leaving the fixation point before the array (`FIXATION_BREAK`)."""
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
    """A link that queues `script[n]` as the `n`th drain begins: a value queued at drain `n`
    applies from the trial numbered `n` from 0."""

    def __init__(self, script):
        super().__init__()
        self.script, self.drains = dict(script), 0

    def drain(self) -> list:
        self.drains += 1
        assert self.drains <= 200, "the session is not ending"
        for command in self.script.get(self.drains, ()):
            self.queue(command)
        return super().drain()


def _session(folder: Path, stages: list[str], script: list[str], commands=None, *,
             values: dict | None = None, seed: int = SEED, **source) -> Session:
    """A run of plan `train` of `stages` on the simulators, its animal playing `script`, the run
    stopped by a person once the script is played."""
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "search.py"
    path.write_text(_source(stages, **source))
    spec = SessionSpec(
        task=str(path), allocation="tasks/allocation.py", root=folder,
        session_id="2027-01-14_01", subject="A", trials=len(script), frame_period=1 / FRAMES,
        seed=seed, values={**VALUES, **(values or {})}, bounds=_sessions.bounds(),
        already_delivered_today=0.0, deployment=Deployment.RIG_FIXED, geometry=DIRECT,
        session_kind="training", calibration=SRGB, plan="train",
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


def _rows(session: Session, name: str) -> list[dict]:
    path = session.directory / name
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def _lines(session: Session) -> list[dict]:
    return _rows(session, "trials.jsonl")


def _kinds(session: Session) -> list:
    return [line["trial_kind"] for line in _lines(session)]


def _share(name: str, value: int) -> list:
    return [SetParameter(name, value, JAKE)]


def _task(tmp_path: Path, **source) -> Task:
    path = tmp_path / "search.py"
    path.write_text(_source([_stage("Crowd")], **source))
    return _load_task(path)


def _found(task: Task, code: str) -> list[str]:
    return [finding.detail for finding in check_task(task) if finding.code == code]


# --- Declared -------------------------------------------------------------------------------------


def test_a_special_declared_wrong_is_refused_as_built_or_at_load(tmp_path):
    """As built (`task.Special`, `Task.specials`): a kind that is no printable text of 1 to 40
    characters, or is `normal` itself; a share that names no setting by `P`; an empty structure;
    anything but `Special`s in a task's specials, or two of one kind or one structure. At load
    (`bad-special`): a structure the task lacks, or its default; a share naming no setting the task
    declares, or one not in percent from 0 to 100."""
    assert (NORMAL, SPECIAL_UNIT) == ("normal", "percent")
    for kind in ("", "x" * 41, "two\nlines", NORMAL, 3):
        with pytest.raises(ValueError):
            Special(kind, P("absent_percent"), "absent")
    Special("x" * 40, P("absent_percent"), "absent")
    for share in ("absent_percent", 10, None):
        with pytest.raises(ValueError, match="share"):
            Special(ABSENT, share, "absent")
    for structure in ("", None, 3):
        with pytest.raises(ValueError, match="structure"):
            Special(ABSENT, P("absent_percent"), structure)

    task = _task(tmp_path)
    one, other = task.specials
    for specials, said in (
        ([one], "tuple"), ((one, "alone"), "tuple"),
        ((one, Special(ABSENT, P("alone_percent"), "alone")), "kind"),
        ((one, Special(ALONE, P("alone_percent"), "absent")), "structure"),
    ):
        with pytest.raises(ValueError, match=said):
            Task(structures=task.structures, default=task.default, specials=specials)
    assert _found(task, "bad-special") == []

    def special(**fields) -> str:
        made = {"kind": f"'{ABSENT}'", "share": "P('absent_percent')", "structure": "'absent'",
                **fields}
        return f"(Special({made['kind']}, {made['share']}, {made['structure']}),)"

    for case, said in (
        ({"structure": "'ghost'"},
         "special kind 'target_absent' plays structure 'ghost', which the task does not have"),
        ({"structure": "'search'"},
         "special kind 'target_absent' plays structure 'search', the task's default: a special "
         "trial plays a structure of its own, in place of the default"),
        ({"share": "P('ghost')"},
         "special kind 'target_absent' takes its percentage from 'ghost', which the task does "
         "not declare"),
        ({"share": "P('fix_hold')"},
         "special kind 'target_absent' takes its percentage from 'fix_hold', which is in s "
         "from 0 to 10: a percentage of trials is a setting in percent from 0 to 100"),
    ):
        folder = tmp_path / str(len(said))
        folder.mkdir()
        assert _found(_task(folder, specials=special(**case)), "bad-special") == [said], case
    for share in ("unit='percent', low=0, high=50", "unit='percent', low=1, high=100",
                  "unit='fraction', low=0, high=100"):
        folder = tmp_path / share.replace("'", "").replace(", ", "_")
        folder.mkdir()
        found = _found(_task(folder, share=share, absent_start="1", alone_start="1"),
                       "bad-special")
        assert len(found) == 2 and all("from 0 to 100" in said for said in found), share
    # Blocking, every kind.
    folder = tmp_path / "blocking"
    folder.mkdir()
    (finding,) = [f for f in check_task(_task(folder, specials=special(structure="'ghost'")))
                  if f.code == "bad-special"]
    assert finding.blocking


def test_shares_past_100_are_drawn_in_proportion_and_warned_at_load(tmp_path):
    """"The percentages add to at most 100. More is a load warning naming the sum" (§4), accepted
    in every kind; each kind is then drawn in proportion to its percentage, and no trial is normal
    (the controller's call). Over 2,000 draws at 90 and 60, about three in five are
    `target_absent` and two in five `odd_one_alone`, none normal; at 100 in all, none warned."""
    task = _task(tmp_path, absent_start="60", alone_start="50")
    (finding,) = [f for f in check_task(task) if f.code == "specials-over-100"]
    assert (finding.blocking, finding.accepted_in) == (False, ("training", "piloting",
                                                               "recording"))
    assert finding.detail == (
        "the special trials' percentages add to 110 at the task's starts (target_absent 60 "
        "from 'absent_percent', odd_one_alone 50 from 'alone_percent'), past 100: each kind is "
        "then drawn in proportion to its percentage, and no trial is normal")
    folder = tmp_path / "hundred"
    folder.mkdir()
    assert _found(_task(folder, absent_start="60", alone_start="40"), "specials-over-100") == []

    drawn = _draws(tmp_path / "run", {"absent_percent": 90, "alone_percent": 60})
    assert drawn.count(None) == 0
    assert abs(drawn.count(ABSENT) / len(drawn) - 0.6) < 0.03
    assert abs(drawn.count(ALONE) / len(drawn) - 0.4) < 0.03


# --- Drawn ----------------------------------------------------------------------------------------


def _draws(folder: Path, shares: dict, n: int = 2000, **source) -> list:
    """`n` fresh trials' kinds, as `Session._special` draws them for a run of seed `SEED` at
    `shares`, each a trial of the default structure: the kind's name, or `None` for a normal
    trial."""
    session = _session(folder, [_stage("Crowd")], ["right"], values=shares, **source)
    task = _load_task(Path(session.spec.task))
    session._run = RunSpec.of(session.spec)
    condition = Condition("c", {}, target=1)
    return [None if special is None else special.kind
            for special in (session._special(task, Draw(condition, number))
                            for number in range(n))]


def test_the_shares_draw_each_kind_near_its_percentage(tmp_path):
    """"Each kind has its own percentage of trials" (§4): at 10% and 20%, over 2,000 trials, each
    kind is drawn within 3 points of its percentage, the rest normal; at 0, none is."""
    drawn = _draws(tmp_path / "some", {"absent_percent": 10, "alone_percent": 20})
    assert abs(drawn.count(ABSENT) / len(drawn) - 0.10) < 0.03
    assert abs(drawn.count(ALONE) / len(drawn) - 0.20) < 0.03
    assert abs(drawn.count(None) / len(drawn) - 0.70) < 0.03
    assert set(_draws(tmp_path / "none", {"absent_percent": 0, "alone_percent": 0})) == {None}


def test_the_draw_is_the_runs_seeds_and_the_same_seed_draws_the_same_kinds(tmp_path):
    """"Which trials are special is drawn per trial from the percentages, between trials, keyed by
    the run's seed" (§4): each trial's kind is the one its run's seed and its number give
    (`variation.unit(seed, trial, "special trial", 0)` against the shares cumulated in their
    declared order, divided by 100), so two runs of one seed draw the same kinds and another seed
    others."""
    shares = {"absent_percent": 30, "alone_percent": 30}
    script = ["right"] * 12
    runs = [_session(tmp_path / str(n), [_stage("Crowd")], script, values=shares, seed=seed)
            for n, seed in enumerate((SEED, SEED, SEED + 1))]
    for session in runs:
        session.run()
    one, again, other = (_kinds(session) for session in runs)

    def expected(seed: int, number: int) -> str:
        share = variation.unit(seed, number, "special trial", 0)
        return ABSENT if share < 0.3 else ALONE if share < 0.6 else NORMAL

    assert one == again == [expected(SEED, number) for number in range(12)]
    assert other == [expected(SEED + 1, number) for number in range(12)]
    assert one != other and {ABSENT, ALONE, NORMAL} <= set(one)


# --- Played ---------------------------------------------------------------------------------------


def test_a_special_trial_takes_the_stage_the_staircases_value_and_a_pairing(tmp_path):
    """"A special trial otherwise follows the open stage" (§4): it plays its kind's structure, in
    the stage's block, at the set size the stage's staircase gives (`drawn` `"staircase"`), with a
    pairing drawn from the pool (`drawn` `"pool"`), counted toward its condition as any trial
    is."""
    session = _session(tmp_path, [_stage("Crowd")], ["right"] * 3,
                       values={"absent_percent": 100, "pairings": 7})

    session.run()

    assert session.refusals == []
    lines = _lines(session)
    assert [(line["trial_kind"], line["structure"], line["block"], line["params"]["set_size"],
             line["drawn"]["set_size"], line["drawn"]["target_appearance"],
             line["drawn"]["distractor_appearance"], line["counting"])
            for line in lines] == [
        (ABSENT, "absent", "Crowd", 6, "staircase", "pool", "pool", "counted")] * 3
    # The stimuli are the special structure's, drawn as any trial's.
    assert all(any(entry["name"] == "search" for entry in line["stimuli"]) for line in lines)


def test_a_special_trial_steps_no_staircase_and_counts_in_the_bars(tmp_path):
    """"Only normal trials move it" (the PI, 2026-11-16) and "An error, counted": three right
    normal trials step the staircase a level harder, the catches between them -- one right, one
    wrong -- neither adding to the run of successes nor breaking it, so the level steps after the
    third normal success, and only then; and the stage's bars count every one of the six, the
    catches' right and wrong among them."""
    script = ["right", "right", "right", "wrong", "right", "right"]
    session = _session(tmp_path, [_stage("Crowd")], script,
                       {1: _share("absent_percent", 100), 2: _share("absent_percent", 0),
                        3: _share("absent_percent", 100), 4: _share("absent_percent", 0)})

    session.run()

    assert session.refusals == []
    lines = _lines(session)
    assert [line["trial_kind"] for line in lines] == [
        NORMAL, ABSENT, NORMAL, ABSENT, NORMAL, NORMAL]
    assert [line["params"]["set_size"] for line in lines] == [6, 6, 6, 6, 6, 8]
    assert [line["counting"] for line in lines] == ["counted"] * 6
    bars = [frame.bars for frame in session.link.published
            if frame.phase == "running" and frame.bars is not None][-1]
    assert (bars.correct, bars.of, bars.wrong) == (5, 6, {"wrong_target": 1})


def test_each_line_says_its_kind_and_whether_it_stepped(tmp_path):
    """Each line's `trial_kind` and `stepped`, as wl-preproc accepted (XC-543): a normal trial
    whose outcome counted on the staircase stepped it; a special trial did not, nor an early
    saccade, which is neither a success nor a failure, nor a trial whose set size a person held;
    a stage with no staircase writes `stepped` null; a task declaring no special trial writes
    `trial_kind` null."""
    stepped = _session(tmp_path / "stairs", [_stage("Crowd")], ["right", "right", "early", "right"],
                       {1: _share("absent_percent", 100), 2: _share("absent_percent", 0),
                        3: [SetParameter("set_size", 8, JAKE)]},
                       values={"absent_percent": 0})
    plain = _session(tmp_path / "plain", [_stage("Plain", staircase=None)], ["right"] * 2)
    none = _session(tmp_path / "none", [_stage("Crowd")], ["right"] * 2, specials="()",
                    structures="{'search': search}")
    for session in (stepped, plain, none):
        session.run()
        assert session.refusals == []

    assert [(line["trial_kind"], line["outcome"], line["stepped"]) for line in _lines(stepped)] == [
        (NORMAL, "correct", True), (ABSENT, "correct", False), (NORMAL, "fixation_break", False),
        (NORMAL, "correct", False)]
    assert _lines(stepped)[3]["drawn"].get("set_size") is None
    assert [(line["trial_kind"], line["stepped"]) for line in _lines(plain)] == [
        (NORMAL, None)] * 2
    assert [(line["trial_kind"], line["stepped"]) for line in _lines(none)] == [
        (None, True)] * 2


def test_a_repeat_and_a_drum_keep_the_special_kind(tmp_path):
    """The plan's Review Focus 2: "a repeat of a special trial is the same kind" (the controller's
    call). An early saccade on a target-absent catch is owed, and its repeat is a target-absent
    catch; a wrong answer on one under drumming brings it back as one, twice -- **even after its
    percentage is set to 0 while the repeat waits**; the next fresh trial follows the new
    percentage, normal."""
    owed = _session(tmp_path / "owed", [_stage("Crowd").replace(", counting=EVERY_TRIAL", "")],
                    ["early", "right", "right"], {1: _share("absent_percent", 0)},
                    values={"absent_percent": 100})
    drummed = _session(tmp_path / "drum", [_stage("Crowd", extra=", drum=True")],
                       ["wrong", "wrong", "right", "right"], {1: _share("absent_percent", 0)},
                       values={"absent_percent": 100})
    for session in (owed, drummed):
        session.run()
        assert session.refusals == []

    assert [(line["trial_kind"], line["repeat_of"]) for line in _lines(owed)] == [
        (ABSENT, None), (ABSENT, 0), (NORMAL, None)]
    assert [(line["trial_kind"], line["drummed"], line["params"]["absent_percent"])
            for line in _lines(drummed)] == [
        (ABSENT, False, 100), (ABSENT, True, 0), (ABSENT, True, 0), (NORMAL, False, 0)]


def test_a_condition_naming_another_structure_is_never_special(tmp_path):
    """"Only a trial of the task's default structure can be special" (the controller's call): a
    condition naming another structure plays it as named, at any percentage, normal on its line;
    one naming the default can be special."""
    other = _session(tmp_path / "other", [_stage("Other", structure="other")], ["right"] * 3,
                     values={"absent_percent": 100},
                     structures="{'search': search, 'absent': search, 'alone': search, "
                                "'other': search}")
    named = _session(tmp_path / "named", [_stage("Named", structure="search")], ["right"] * 3,
                     values={"absent_percent": 100})
    for session in (other, named):
        session.run()
        assert session.refusals == []

    assert [(line["trial_kind"], line["structure"]) for line in _lines(other)] == [
        (NORMAL, "other")] * 3
    assert [(line["trial_kind"], line["structure"]) for line in _lines(named)] == [
        (ABSENT, "absent")] * 3


# --- Gone on from, recorded, reviewed -------------------------------------------------------------


def test_a_stopped_run_with_specials_goes_on_at_its_staircases_level(tmp_path):
    """The plan's Review Focus 1: a run with catches stops, and the next goes on from it
    (`taskd.went_on`, the record read back by the run's own rules). Its staircase is at the level
    the stopped run had reached, with its count, the special lines having stepped nothing -- two
    right normal trials, then a right catch and a wrong one, then a third right normal, step it
    once, to 8, its count started again -- and its bars hold every line, the catches' among
    them."""
    script = ["right", "right", "right", "wrong", "right"]
    session = _session(tmp_path, [_stage("Crowd")], script,
                       {2: _share("absent_percent", 100), 4: _share("absent_percent", 0)})

    session.run()

    assert [line["trial_kind"] for line in _lines(session)] == [
        NORMAL, NORMAL, ABSENT, ABSENT, NORMAL]
    assert [line["params"]["set_size"] for line in _lines(session)] == [6, 6, 6, 6, 6]
    task = _load_task(Path(session.spec.task))
    went = went_on(task, resume.read(session.directory, departure=WALL_NOW).last_run)
    assert (went.stage, went.climb.value, went.climb.right, went.climb.wrong) == ("Crowd", 8, 0, 0)
    assert (session._climb.value, session._climb.right) == (went.climb.value, went.climb.right)
    trials = [entry for entry in went.bars if entry[0] == "trial"]
    assert [entry[1].value for entry in trials] == [
        "correct", "correct", "correct", "wrong_target", "correct"]


def test_the_start_row_names_each_special(tmp_path):
    """The start row's `specials`, as wl-preproc accepted (XC-543): each kind, with the setting its
    percentage is read from and the structure it plays; null for a task declaring none. (Its keys
    are written sorted, as every row's are, so the declared order the draw cumulates in is the
    task's, named by its content hash; each line names its own kind.)"""
    some = _session(tmp_path / "some", [_stage("Crowd")], ["right"])
    none = _session(tmp_path / "none", [_stage("Crowd")], ["right"], specials="()",
                    structures="{'search': search}")
    for session in (some, none):
        session.run()

    (start,) = [row for row in _rows(some, "runs.jsonl") if row["event"] == "start"]
    assert start["specials"] == {
        ABSENT: {"share": "absent_percent", "structure": "absent"},
        ALONE: {"share": "alone_percent", "structure": "alone"}}
    (start,) = [row for row in _rows(none, "runs.jsonl") if row["event"] == "start"]
    assert start["specials"] is None


def test_the_review_lists_each_special_kind(tmp_path):
    """The review report lists each special kind: the setting its percentage is read from, what
    that starts at, and the structure it plays; nothing for a task declaring none."""
    report = render_task(_task(tmp_path, absent_start="5"))
    assert "### Special trials" in report
    assert "| target_absent | `absent_percent` | 5% | `absent` |" in report
    assert "| odd_one_alone | `alone_percent` | 0% | `alone` |" in report
    folder = tmp_path / "none"
    folder.mkdir()
    assert "### Special trials" not in render_task(
        _task(folder, specials="()", structures="{'search': search}"))


def test_no_draw_or_record_of_a_special_runs_in_a_frame(tmp_path, monkeypatch):
    """Hot path (the plan's Global Constraints): a trial's kind is drawn between trials, never in a
    frame. `_special` and the line's write are counted while a trial's frames run, and neither
    runs there; each ran once a trial between them."""
    import wl_xcon.record as record_module
    import wl_xcon.taskd as taskd_module

    inside = {"now": False}
    calls = {"between": 0, "in a frame": 0, "lines in a frame": 0}
    run_trial, special = taskd_module.run_trial, Session._special
    write = record_module.SessionRecord.trial

    def framed(*args, **kwargs):
        inside["now"] = True
        try:
            return run_trial(*args, **kwargs)
        finally:
            inside["now"] = False

    def counted(self, task, draw):
        calls["in a frame" if inside["now"] else "between"] += 1
        return special(self, task, draw)

    def written(self, *args, **kwargs):
        calls["lines in a frame"] += inside["now"]
        return write(self, *args, **kwargs)

    monkeypatch.setattr(taskd_module, "run_trial", framed)
    monkeypatch.setattr(Session, "_special", counted)
    monkeypatch.setattr(record_module.SessionRecord, "trial", written)
    session = _session(tmp_path, [_stage("Crowd")], ["right"] * 4,
                       values={"absent_percent": 50, "alone_percent": 50})

    session.run()

    assert set(_kinds(session)) <= {ABSENT, ALONE} and len(_kinds(session)) == 4
    assert calls == {"between": 4, "in a frame": 0, "lines in a frame": 0}
