"""Start at a chosen stage, with starting values, and resume a stage (the pop-out search build's
Task 6; its design, `docs/superpowers/specs/2026-11-07-popout-search-design.md` §3.5 and §3.6,
approved by the PI on 2026-11-07).

The PI's decisions: "The trainer picks" where the animal starts each day -- the stage, the
staircase's level and the pairings, at the run's start, "with yesterday's end shown" -- and
"nothing carries the stage across sessions on its own" (that is the paused build C7's). The plan's
Review Focus 4: **a session resumed after a crash mid-stage** (`wlx taskd`'s stranded resume) comes
back with its stage, its staircase's level, its pool and any suggestion pending as they were.

wl-preproc accepted the record's one new field on 2026-11-07
(`docs/pending-wl-preproc-amendments.md`): the run's start row gains `start_block`, the name of the
block the run started at, "absent or null means the first".

**The console's start carries a start block through `Service._start`**, welfare-listed: the PI
approved its passing the block to the start's pre-flight and to the run on 2026-11-07, asked in
the UI (the build's welfare item); until then a start naming one was refused with a sentence.

Engine test material, run only in the simulator: the reference search task with a pool of three
pairings of its own looks (as `test_pairing_pool.py` builds it) and a plan of two stages, `Alone`
(one object) and `Crowd` (a staircase on its set size), whose moves a person confirms. Windows are
short so a run is a few trials; the task's own are 50.
"""

from __future__ import annotations

import html
import json
import shutil
import time
from pathlib import Path

import pytest

import _sessions
from _frames import view
from _rig import DIRECT, PATH as RIG_FILE, RIG
from _sessions import OPEN_ACCEPTED, typed
from wl_xcon import stranded
from wl_xcon.actor import Box
from wl_xcon.cli import _load_allocation, _load_task, main
from wl_xcon.dio import Simulated as Card
from wl_xcon.link import (
    BackBlock, CheckRun, Decline, EndSession, HandBack, NextBlock, OpenSession, PoolRow,
    Preflight, PreflightItem, ResumeSession, SetParameter, Simulated, StageRow, StartRun, Stop,
    _decode_command, _encode_command, decode, encode,
)
from wl_xcon.photometry import SRGB
from wl_xcon.preflight import FAIL, task as task_checks
from wl_xcon.run import Scripted
from wl_xcon.service import Service
from wl_xcon.task import SaccadeTo
from wl_xcon.taskd import Session, SessionSpec
from wl_xcon.web import fragments
from wl_xcon.welfare import Deployment, Simulated as Pump

WALL_NOW = 1_700_000_000.0
SEED = 7
JAKE = Box("jake")
FRAMES = 240
SEARCH = "tasks/visual_search.py"
ALLOCATION = "tasks/allocation.py"
#: The confirmed progression's order, with short windows: back under 50% of the last 4 first
#: answers, each move a person's to confirm.
CONFIRMED = "ByCriterion(fall_back=(0.5, 4), confirm=True)"
#: The pool's three pairings, after `visual_search`'s own source, as `test_pairing_pool.py` has it.
POOL = (
    "Pool('pairings', ((RED_DISC, GREEN_DISC), (GREEN_DISC, RED_DISC), (GREEN_SQUARE, RED_DISC)),"
    " odd='target_appearance', distractor='distractor_appearance')")
#: Crowd's staircase: 4, 6, 8 and 10 objects, easiest first, three right a step harder, one wrong a
#: step easier.
STAIRS = "Staircase('set_size', (4, 6, 8, 10))"
#: `visual_search`'s starting values, six objects -- where Crowd's staircase starts, nearest -- and
#: one pairing pooled.
VALUES = {**_sessions.SEARCH_VALUES, "pairings": 1}
UNKNOWN = ("warnings", "pump calibration", "eye tracker")


def _source(stages: list[str], order: str = CONFIRMED, plans: str = "") -> str:
    """`visual_search`'s source with a pool over its two looks, its pool setting `pairings`
    declared from 1 to 7 starting at 1, its set size allowed down to one object (its target index
    then always 0), and one plan, `train`, of `stages` in `order`, and `plans`, more of them as
    source. Engine test material."""
    text = Path(SEARCH).read_text()
    for old, new in (('Param("set_size", unit="objects", low=2, high=12)',
                      'Param("set_size", unit="objects", low=1, high=12)'),
                     ('Param("target_index", unit="index", low=0, high=1)',
                      'Param("target_index", unit="index", low=0, high=0)')):
        assert text.count(old) == 1, old
        text = text.replace(old, new)
    return text + (
        "\n\nimport dataclasses as _dataclasses\n"
        "from wl_xcon.scheduler import EVERY_TRIAL\n"
        "from wl_xcon.task import (Balanced, Block, ByCriterion, Condition, Plan, Pool, "
        "Staircase, NEITHER, NOT_DIFFICULTY)\n"
        "RED_DISC, GREEN_DISC = Disc(size=1.0, color=RED), Disc(size=1.0, color=GREEN)\n"
        "GREEN_SQUARE = Square(size=1.0, color=GREEN)\n"
        "search = _dataclasses.replace(search, params=[*search.params, "
        "Param('pairings', unit='pairings', low=1, high=7, start=1)])\n"
        "TASK = _dataclasses.replace(\n"
        "    TASK, structures={'search': search},\n"
        "    meanings={**TASK.meanings, 'pairings': Meaning(NOT_DIFFICULTY, NEITHER, "
        "note='which pairings are drawn')},\n"
        f"    pool={POOL},\n"
        f"    plans={{'train': Plan([{', '.join(stages)}], order={order}){plans}}})\n")


def _stage(name: str, criterion=None, *, set_size: int | None = None,
           staircase: str | None = None, target: int = 1, extra: str = "") -> str:
    """A stage's source: one condition of `target` trials, every trial paying it (`EVERY_TRIAL`),
    giving the set size where `set_size` says, its `criterion` the bar to move up, the staircase
    given, and `extra`, more of its fields as source."""
    values = "{}" if set_size is None else f"{{'set_size': {set_size}}}"
    stepped = "" if staircase is None else f", staircase={staircase}"
    rule = "" if criterion is None else f", criterion={criterion}"
    return (f'Block("{name}", [Condition("c", {values}, target={target})], counting=EVERY_TRIAL'
            f'{rule}{stepped}{extra})')


#: The two stages most tests play: `Alone`, one object, and `Crowd`, its set size stepped by
#: `STAIRS`, each with a bar to move up of 80% of the last 2 answers at its hardest step.
ALONE, CROWD = _stage("Alone", (0.8, 2), set_size=1), _stage("Crowd", (0.8, 2), staircase=STAIRS)


def _trial(kind: str, values: dict) -> Scripted:
    """One trial the animal plays as `kind` says: `right` (`CORRECT`) or `wrong`, a look at a
    distractor (`WRONG_TARGET`)."""
    held = round(values["fix_hold"] * FRAMES) + 20
    target = f"search.{values['target_index']}"
    looks = {frame: "fix" for frame in range(1, held + 1)}
    if kind == "right":
        return Scripted({SaccadeTo("search.target"): held + 10},
                        inside={**looks, **{f: target for f in range(held + 1, held + 400)}})
    assert kind == "wrong", kind
    return Scripted({SaccadeTo("search.distractor"): held + 10}, inside=looks)


def _jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


# --- a session of its own (`wlx run`'s, and the backstop) ---------------------------------------


def _session(folder: Path, stages: list[str], script: list[str], *, start_block=None,
             order: str = CONFIRMED) -> Session:
    """A run of plan `train` of `stages` on the simulators, starting at `start_block`, its animal
    playing `script`, the run stopped by a person once the script is played."""
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "search.py"
    path.write_text(_source(stages, order))
    spec = SessionSpec(
        task=str(path), allocation=ALLOCATION, root=folder, session_id="2027-01-14_01",
        subject="A", trials=len(script), frame_period=1 / FRAMES, seed=SEED, values=dict(VALUES),
        bounds=_sessions.bounds(), already_delivered_today=0.0,
        deployment=Deployment.RIG_FIXED, geometry=DIRECT, session_kind="training",
        calibration=SRGB, plan="train", start_block=start_block,
    )
    session = Session(spec, card=Card(), pump=Pump(), link=Simulated())
    session.wall_clock = lambda: WALL_NOW + session.now()
    session.left_cage(at=WALL_NOW)
    session.head_fixed(at=session.wall_now())

    def built(trial, values, index):
        if index == 1:
            session.link.queue(BackBlock(by=JAKE))
        if index == len(script) - 1:
            session.link.queue(Stop(by=JAKE))
        return _trial(script[index], values)

    session.world = built
    return session


def _cli(tmp_path, *extra: str) -> list:
    """`wlx run` of `tmp_path`'s `search.py`, its plan `fixed`: `Alone` then `Crowd`, two trials
    each, in order."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    path = tmp_path / "search.py"
    path.write_text(_source([ALONE, CROWD], plans=(
        ", 'fixed': Plan([" + _stage("Alone", set_size=1, target=2) + ", "
        + _stage("Crowd", staircase=STAIRS, target=2) + "])"
        ", 'mixed': Plan([" + _stage("Alone", set_size=1, target=2) + ", "
        + _stage("Crowd", staircase=STAIRS, target=2) + "], order=Balanced(blocks=2))")))
    sets = {**{name: str(value) for name, value in _sessions.SEARCH_VALUES.items()},
            "pairings": "1"}
    return ["run", str(path), "--rig", RIG_FILE, "--view", "direct", "--kind", "training",
            "--accept-warnings", "--allocation", ALLOCATION,
            "--bounds", "tasks/eight_hour_bounds.py", "--root", str(tmp_path / "root"),
            "--session-id", "2027-01-14_01", "--subject", "REFERENCE",
            "--out-of-cage-at", time.strftime("%H:%M"), "--delivered-today", "0",
            "--trials", "2",
            *[arg for name, value in sets.items() for arg in ("--set", f"{name}={value}")],
            *extra]


def test_a_run_starts_at_the_named_block_and_its_start_row_says_so(tmp_path):
    """A run of a plan starts at the block it names (the PI, "The trainer picks"), the plan's
    earlier stages still there to move back to, and its start row says where, as wl-preproc
    accepted (`start_block`); one naming none starts at the first, its start row saying `null`.
    `wlx run --start-block` starts there too."""
    named = _session(tmp_path / "named", [ALONE, CROWD], ["right"] * 3, start_block="Crowd")
    first = _session(tmp_path / "first", [ALONE, CROWD], ["right"] * 3)

    named.run()
    first.run()

    lines = _jsonl(named.directory / "trials.jsonl")
    assert [(line["block"], line["params"]["set_size"]) for line in lines] == [
        ("Crowd", 6), ("Crowd", 6), ("Alone", 1)]
    start = _jsonl(named.directory / "runs.jsonl")[0]
    assert (start["plan"], start["start_block"], start["blocks"]) == (
        "train", "Crowd", ["Alone", "Crowd"])
    assert [line["block"] for line in _jsonl(first.directory / "trials.jsonl")] == [
        "Alone", "Alone", "Alone"]
    assert _jsonl(first.directory / "runs.jsonl")[0]["start_block"] is None

    assert main(_cli(tmp_path / "cli", "--plan", "fixed", "--start-block", "Crowd")) == 0
    xcon = tmp_path / "cli" / "root" / "2027-01-14_01" / "xcon"
    assert [line["block"] for line in _jsonl(xcon / "trials.jsonl")] == ["Crowd", "Crowd"]
    assert _jsonl(xcon / "runs.jsonl")[0]["start_block"] == "Crowd"


@pytest.mark.parametrize("plan, start_block, said", [
    ("fixed", "Nope", "plan 'fixed' has no block 'Nope'; its blocks are 'Alone', 'Crowd'"),
    (None, "Crowd", "block 'Crowd' names a block of a plan to start at, and this run plays no "
                    "plan"),
    ("mixed", "Crowd", "plan 'mixed' plays its blocks in a random order, so no run starts at "
                       "one of them by its name"),
])
def test_an_unknown_block_is_refused_before_the_run_opens(tmp_path, plan, start_block, said):
    """A start block the run cannot start at is refused with a sentence before anything of the run
    is recorded: by `wlx run` before its session opens and its departure is marked, by the
    pre-flight `wlx taskd` takes at a check and a start (its task checks fail), and by
    `Session.run`'s backstop."""
    argv = _cli(tmp_path / "cli", "--start-block", start_block,
                *(() if plan is None else ("--plan", plan)))
    with pytest.raises(SystemExit) as refused:
        main(argv)
    assert str(refused.value) == f"task refused, session not started, nothing recorded: {said}"
    assert not (tmp_path / "cli" / "root").exists() or list(
        (tmp_path / "cli" / "root").iterdir()) == []
    assert stranded.find(tmp_path / "cli" / "root") == []

    item, _, _ = task_checks(tmp_path / "cli" / "search.py", _load_allocation(Path(ALLOCATION)),
                             DIRECT, SRGB, plan=plan, start_block=start_block)
    assert (item.result, item.said) == (FAIL, said)

    if plan == "fixed":
        session = _session(tmp_path / "run", [ALONE, CROWD], ["right"], start_block=start_block)
        with pytest.raises(SystemExit, match="^task refused, session not started: plan 'train' "
                                             "has no block 'Nope'"):
            session.run()
        assert _jsonl(session.directory / "runs.jsonl") == []


# --- `wlx taskd`: the service, its pre-flight, and a resume -------------------------------------


class _Wall:
    def __init__(self) -> None:
        self.at = _sessions.WALL

    def __call__(self) -> float:
        return self.at


def _folders(tmp_path, stages: list[str]) -> tuple:
    """`--subjects`, `--tasks` and `--root` for a service: the reference animal with its bounds and
    settings, and `search.py` of `stages`."""
    subjects, tasks, root = tmp_path / "subjects", tmp_path / "tasks", tmp_path / "sessions"
    (subjects / "REFERENCE").mkdir(parents=True)
    shutil.copy("tasks/eight_hour_bounds.py", subjects / "REFERENCE" / "bounds.py")
    shutil.copy("tasks/reference_subject.py", subjects / "REFERENCE" / "settings.py")
    tasks.mkdir()
    (tasks / "search.py").write_text(_source(stages, plans=(
        ", 'other': Plan([" + ", ".join(stages) + f"], order={CONFIRMED})")))
    root.mkdir()
    return subjects, tasks, root


def _service(folders) -> Service:
    subjects, tasks, root = folders
    return Service(
        rig=RIG, rig_path=RIG_FILE, subjects=subjects, tasks=tasks,
        allocation=_load_allocation(Path(ALLOCATION)), allocation_path=ALLOCATION, root=root,
        link=Simulated(), seed=lambda: SEED, wall_clock=_Wall(),
    )


def _step(service, *commands):
    for command in commands:
        service.link.queue(command)
    service.step()
    return service.link.published[-1]


def _open(session_id: str = "2027-01-14_01") -> OpenSession:
    return OpenSession(
        by=JAKE, session_id=session_id, animal="REFERENCE", deployment="rig_fixed",
        view="direct", session_kind="training", departure=typed(60), delivered_today=0.0,
        answer=None, amend_to=None, amend_reason="", accepted=OPEN_ACCEPTED,
    )


def _start(**over) -> StartRun:
    fields = dict(by=JAKE, task="search.py", values=dict(VALUES), trials=1, acknowledged=UNKNOWN,
                  plan="train")
    fields.update(over)
    return StartRun(**fields)


def _plays(service, script: list[str], commands: dict | None = None, *,
           dies_at: int | None = None) -> None:
    """The open session's animal plays `script`, each command of `commands[n]` sent as trial `n`
    is built -- drained at the boundary after it; a function there gives them, called with the
    session then -- and the run stopped by a person once the script is played, or, at trial
    `dies_at`, its process stopped there, by Ctrl-C at `wlx taskd`'s terminal: before that trial
    takes a number."""
    session = service.session

    def built(trial, values, index):
        sent = (commands or {}).get(index, ())
        for command in (sent(session) if callable(sent) else sent):
            service.link.queue(command)
        if index == dies_at:
            raise KeyboardInterrupt
        if dies_at is None and index == len(script) - 1:
            service.link.queue(Stop(by=JAKE))
        return _trial(script[index], values)

    session.world = built


def _xcon(folders, session_id: str = "2027-01-14_01") -> Path:
    return folders[2] / session_id / "xcon"


def _stranded_in(tmp_path, stages, script, commands, *, killed: bool):
    """A session opened and run until its process stopped at the trial after `script`, by Ctrl-C;
    `killed`, as a kill leaves it, with no end row for its run. Then a second service over the same
    root, which finds it stranded, and resumes it."""
    folders = _folders(tmp_path, stages)
    first = _service(folders)
    _step(first, _open())
    _plays(first, script, commands, dies_at=len(script))
    with pytest.raises(KeyboardInterrupt):
        _step(first, _start())
    xcon = _xcon(folders)
    rows = _jsonl(xcon / "runs.jsonl")
    assert (rows[-1]["event"], rows[-1]["stopped_because"]) == (
        "end", "interrupted at the terminal")
    if killed:
        (xcon / "runs.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows[:-1]))
    second = _service(folders)
    assert [s.session_id for s in _step(second).stranded] == ["2027-01-14_01"]
    frame = _step(second, ResumeSession(by=JAKE, session_id="2027-01-14_01"))
    assert frame.phase == "between_runs"
    return folders, second


def _run_lines(folders, run: int) -> list[dict]:
    return [line for line in _jsonl(_xcon(folders) / "trials.jsonl") if line["run"] == run]


def _changes(folders, kind: str) -> list[dict]:
    return [row for row in _jsonl(_xcon(folders) / "parameter_changes.jsonl")
            if row.get("kind") == kind]


def _running(service, run: int) -> list:
    return [frame for frame in service.link.published
            if getattr(frame, "phase", None) == "running" and frame.run_index == run]


@pytest.mark.parametrize("killed", [False, True], ids=["interrupted", "killed"])
def test_a_stranded_session_resumes_its_stage_level_pool_and_suggestion(tmp_path, killed):
    """The plan's Review Focus 4. Run 1 moves to Crowd by hand, widens its pool to two pairings,
    steps Crowd's staircase down to 4 objects on four wrong answers, which suggest moving back,
    and answers once right, the suggestion still standing (1 of the last 4 right, under 50%), when
    its process stops -- by Ctrl-C at `wlx taskd`, or killed, its record holding no end for it.
    Resumed, the session's next run of the same task and plan **goes on from there**: it starts in
    Crowd, at 4 objects, with two pairings, the suggestion standing under its own id from its first
    frame, and confirming it moves the run back, the move's row naming it."""
    script = ["right", "right", "wrong", "wrong", "wrong", "wrong", "right"]
    folders, second = _stranded_in(
        tmp_path, [ALONE, CROWD], script,
        {0: [NextBlock(by=JAKE), SetParameter(name="pairings", value=3, by=JAKE)]},
        killed=killed)
    (suggested,) = _changes(folders, "suggested")
    assert (suggested["move"], suggested["block"], suggested["now"], suggested["run"]) == (
        "back", "Crowd", "Alone", 0)
    checked = _step(second, CheckRun(by=JAKE, task="search.py", values=dict(VALUES),
                                     plan="train"))
    _plays(second, ["wrong", "right"],
           {0: [BackBlock(by=JAKE, suggestion=suggested["change"])]})

    _step(second, _start())

    first = _running(second, 1)[0]
    assert (first.block, first.suggestion.change, first.suggestion.move,
            first.suggestion.correct, first.suggestion.of) == (
        "Crowd", suggested["change"], "back", 1, 4)
    lines = _run_lines(folders, 1)
    assert [(line["block"], line["params"]["set_size"], line["params"]["pairings"])
            for line in lines] == [("Crowd", 4, 3), ("Alone", 1, 3)]
    start = [row for row in _jsonl(_xcon(folders) / "runs.jsonl")
             if row["event"] == "start" and row["run"] == 1][0]
    assert (start["start_block"], start["resolved"]["pairings"]) == ("Crowd", 3)
    (moved,) = [row for row in _jsonl(_xcon(folders) / "controls.jsonl")
                if row["kind"] == "back_block" and row["run"] == 1]
    assert (moved["block"], moved["to"], moved["suggestion"]) == (
        "Crowd", "Alone", suggested["change"])
    said = [control.said for control in _running(second, 1)[-1].controls
            if control.kind == "resumed"]
    went = (f"in Crowd; set_size at 4, by its staircase, 1 right toward a step harder; pairings "
            f"3 (pairing 1, pairing 2); the rig's suggestion {suggested['change']}, to move back "
            f"from Crowd to Alone, standing")
    assert said == [f"this run goes on from run 1, which stopped with its process: {went}"]
    # Its pre-flight said so before the start, in the pickers' place.
    assert checked.preflight.continues == (
        f"it goes on from run 1, which stopped with its process: {went}")
    pane = fragments(checked, view())["preflight"]
    assert 'id="continues"' in pane and 'id="start-block"' not in pane


def test_a_resumed_run_keeps_its_staircases_count_toward_a_step(tmp_path):
    """The staircase comes back with its count: two right in a row at 6 objects before the stop,
    so the next run's first right is the third, and steps it harder, to 8 -- never counted afresh,
    which would take three more. And its failures toward a step easier: on a staircase two wrong
    step easier, one wrong before the stop and one after step it to 4, and its feed says so."""
    folders, second = _stranded_in(tmp_path / "right", [ALONE, CROWD], ["right"] * 3,
                                   {0: [NextBlock(by=JAKE)]}, killed=True)
    _plays(second, ["right", "right"])

    _step(second, _start())

    assert [line["params"]["set_size"] for line in _run_lines(folders, 1)] == [6, 8]
    # Only the resumed session's first run goes on: the next starts at its plan's first stage.
    _plays(second, ["right"])
    _step(second, _start())
    assert [line["block"] for line in _run_lines(folders, 2)] == ["Alone"]

    crowd = _stage("Crowd", (0.8, 2), staircase="Staircase('set_size', (4, 6, 8, 10), up=2)")
    folders, second = _stranded_in(tmp_path / "wrong", [ALONE, crowd], ["right", "wrong"],
                                   {0: [NextBlock(by=JAKE)]}, killed=True)
    _plays(second, ["wrong", "right"])

    _step(second, _start())

    assert [line["params"]["set_size"] for line in _run_lines(folders, 1)] == [6, 4]
    assert [control.said for control in _running(second, 1)[-1].controls
            if control.kind == "resumed"] == [
        "this run goes on from run 1, which stopped with its process: in Crowd; set_size at 6, "
        "by its staircase, 1 wrong toward a step easier; pairings 1 (pairing 1)"]


def test_a_run_that_went_on_and_stopped_again_goes_on_again(tmp_path):
    """A run that went on from one its process stopped in, and stopped with its process too, goes
    on again from where it reached: its staircase is read from the levels its own lines played at,
    the level it came back with among them, never started afresh where the plan's would start."""
    folders, second = _stranded_in(tmp_path, [ALONE, CROWD], ["right"] * 4,
                                   {0: [NextBlock(by=JAKE)]}, killed=True)
    _plays(second, ["right"], dies_at=1)
    with pytest.raises(KeyboardInterrupt):
        _step(second, _start())
    third = _service(folders)
    _step(third)
    _step(third, ResumeSession(by=JAKE, session_id="2027-01-14_01"))
    _plays(third, ["right", "right", "right"])

    _step(third, _start())

    assert [line["params"]["set_size"] for line in _run_lines(folders, 1)] == [8]
    assert [line["params"]["set_size"] for line in _run_lines(folders, 2)] == [8, 8, 10]


@pytest.mark.parametrize("how", ["moved by hand", "its time"])
def test_a_stage_left_after_the_last_trial_is_where_the_run_goes_on(tmp_path, how):
    """The run goes on in the stage it was in as its process stopped, even one it reached after its
    last trial: a person's move, read from `controls.jsonl` though the run was killed with no end
    row; or the stage's time running out, which no row but the run's end row records (Ctrl-C)."""
    if how == "moved by hand":
        folders, second = _stranded_in(tmp_path, [ALONE, CROWD], ["right"],
                                       {0: [NextBlock(by=JAKE)]}, killed=True)
    else:
        alone = _stage("Alone", (0.8, 2), set_size=1, extra=", time_limit_s=0.001")
        folders, second = _stranded_in(tmp_path, [alone, CROWD], ["right"], {}, killed=False)
    assert [line["block"] for line in _run_lines(folders, 0)] == ["Alone"]
    _plays(second, ["right"])

    _step(second, _start())

    assert [(line["block"], line["params"]["set_size"]) for line in _run_lines(folders, 1)] == [
        ("Crowd", 6)]


def test_a_hold_and_its_hand_back_before_the_stop_come_back_as_they_left_the_staircase(tmp_path):
    """A person's value holds the staircase (TSK-32): its trials step nothing, so a run stopped
    while it held comes back where the staircase stopped -- two right at 6, then three right at 6
    held, and the next run's first right is the third, stepping it to 8. A person's value is a
    live edit of that run, not carried: the next run's staircase gives the setting again. And a
    hand-back resumes the staircase at the level nearest the value held, its count started again
    (the plan's Review Focus 1): two right at 6, one held, handed back, and three more right are
    needed after the stop, never one."""
    hold = SetParameter(name="set_size", value=6, by=JAKE)
    folders, second = _stranded_in(tmp_path / "held", [ALONE, CROWD], ["right"] * 6,
                                   {0: [NextBlock(by=JAKE)], 1: [hold]}, killed=True)
    assert [(line["params"]["set_size"], line["drawn"].get("set_size"))
            for line in _run_lines(folders, 0)][1:] == [
        (6, "staircase"), (6, "staircase"), (6, None), (6, None), (6, None)]
    _plays(second, ["right"] * 2)

    _step(second, _start())

    assert [(line["params"]["set_size"], line["drawn"].get("set_size"))
            for line in _run_lines(folders, 1)] == [(6, "staircase"), (8, "staircase")]
    assert [control.said for control in _running(second, 1)[-1].controls
            if control.kind == "resumed"] == [
        "this run goes on from run 1, which stopped with its process: in Crowd; set_size at 6, "
        "by its staircase, 2 right toward a step harder; pairings 1 (pairing 1); set_size held by "
        "a person at its last trial, not carried: hold it again to keep it"]

    folders, second = _stranded_in(
        tmp_path / "handed", [ALONE, CROWD], ["right"] * 5,
        {0: [NextBlock(by=JAKE)], 1: [hold], 3: [HandBack(name="set_size", by=JAKE)]},
        killed=True)
    assert [(line["params"]["set_size"], line["drawn"].get("set_size"))
            for line in _run_lines(folders, 0)][1:] == [
        (6, "staircase"), (6, "staircase"), (6, None), (6, None)]
    assert [row["name"] for row in _changes(folders, "hand_back")] == ["set_size"]
    _plays(second, ["right"] * 4)

    _step(second, _start())

    assert [line["params"]["set_size"] for line in _run_lines(folders, 1)] == [6, 6, 6, 8]


def test_a_suggestion_held_before_the_stop_stays_held_and_its_window_starts_again(tmp_path):
    """A suggestion a person held before the stop is not offered again by the resumed run, and its
    window goes on from the hold (the PI, "After 50 new tries"): two wrong answers after the hold,
    then two more in the next run make four, and only then is moving back suggested again."""
    script = ["right"] + ["wrong"] * 7
    folders, second = _stranded_in(
        tmp_path, [ALONE, CROWD], script,
        {0: [NextBlock(by=JAKE)],
         5: lambda session: [Decline(suggestion=session.suggestion[0], by=JAKE)]},
        killed=True)
    (held,) = _changes(folders, "suggested")
    (declined,) = _changes(folders, "declined")
    assert (declined["suggestion"], declined["trial_number"]) == (
        held["change"], _run_lines(folders, 0)[6]["trial_number"])
    _plays(second, ["wrong", "wrong", "wrong"])

    _step(second, _start())

    assert _running(second, 1)[0].suggestion is None
    suggested = [row for row in _changes(folders, "suggested") if row["run"] == 1]
    lines = _run_lines(folders, 1)
    assert [row["trial_number"] for row in suggested] == [lines[1]["trial_number"] + 1]


def test_a_suggestion_withdrawn_before_the_stop_is_not_offered_again(tmp_path):
    """A suggestion whose bar stopped being met before the stop had withdrawn itself (the plan's
    Review Focus 2), which no row records: the resumed run judges its bar again, and offers
    neither a move back the animal's answers no longer call for -- four wrong, then two right,
    50% of the last 4 -- nor a widening its last answer at the hardest step undid."""
    folders, second = _stranded_in(
        tmp_path / "back", [ALONE, CROWD], ["right", "wrong", "wrong", "wrong", "wrong", "right",
                                            "right"],
        {0: [NextBlock(by=JAKE)]}, killed=True)
    (back,) = _changes(folders, "suggested")
    _plays(second, ["right"])

    _step(second, _start())

    assert back["move"] == "back" and _running(second, 1)[0].suggestion is None

    crowd = _stage("Crowd", (0.8, 3), staircase="Staircase('set_size', (4, 6))")
    folders, second = _stranded_in(tmp_path / "widen", [ALONE, crowd],
                                   ["right", "right", "right", "right", "wrong"],
                                   {0: [NextBlock(by=JAKE)]}, killed=True)
    (widen,) = _changes(folders, "suggested")
    _plays(second, ["right"])

    _step(second, _start())

    assert widen["move"] == "widen" and _running(second, 1)[0].widen is None


def test_a_widening_standing_at_the_stop_stands_again_and_a_pool_change_starts_its_bar_afresh(
        tmp_path):
    """The rig's suggestion to widen the pool comes back as it was (the build's Task 5): in Crowd,
    its staircase at its hardest from the first, three right at the hardest step meet the bar
    (80% of the last 3) and the rig suggests widening; after the stop it stands under its own id,
    and a hold answers it. And a pool changed before the stop starts the bar afresh, as it did
    live: two right, the pool widened, one right, the stop, and the bar is met only on the second
    right of the next run."""
    crowd = _stage("Crowd", (0.8, 3), staircase="Staircase('set_size', (4, 6))")
    folders, second = _stranded_in(tmp_path / "standing", [ALONE, crowd], ["right"] * 4,
                                   {0: [NextBlock(by=JAKE)]}, killed=True)
    (widen,) = _changes(folders, "suggested")
    assert (widen["move"], widen["name"]) == ("widen", "pairings")
    _plays(second, ["right"], {0: [Decline(suggestion=widen["change"], by=JAKE)]})

    _step(second, _start())

    assert _running(second, 1)[0].widen.change == widen["change"]
    (declined,) = _changes(folders, "declined")
    assert (declined["suggestion"], declined["run"]) == (widen["change"], 1)

    folders, second = _stranded_in(
        tmp_path / "afresh", [ALONE, crowd], ["right"] * 4,
        {0: [NextBlock(by=JAKE)], 1: [SetParameter(name="pairings", value=3, by=JAKE)]},
        killed=True)
    assert _changes(folders, "suggested") == []
    _plays(second, ["right"] * 3)

    _step(second, _start())

    lines = _run_lines(folders, 1)
    assert [row["trial_number"] for row in _changes(folders, "suggested")] == [
        lines[1]["trial_number"] + 1]


@pytest.mark.parametrize("how", ["stopped", "another plan", "task edited"])
def test_a_resumed_run_starts_afresh_after_a_run_a_person_ended_or_on_another_plan(tmp_path, how):
    """Only a run that stopped with its process goes on: one a person stopped had ended, as in a
    session never stranded, and the next run starts at its plan's first stage; a run of another
    plan starts at its own first; and so does one of a task file changed since, whose stages and
    staircases may no longer be the ones the record names."""
    folders = _folders(tmp_path, [ALONE, CROWD])
    first = _service(folders)
    _step(first, _open())
    if how == "stopped":
        _plays(first, ["right", "wrong"], {0: [NextBlock(by=JAKE)]})
        _step(first, _start())
    else:
        _plays(first, ["right", "wrong", "wrong"], {0: [NextBlock(by=JAKE)]}, dies_at=2)
        with pytest.raises(KeyboardInterrupt):
            _step(first, _start())
    if how == "task edited":
        path = folders[1] / "search.py"
        path.write_text(path.read_text().replace(STAIRS, "Staircase('set_size', (4, 6, 8, 12))"))
    second = _service(folders)
    _step(second)
    _step(second, ResumeSession(by=JAKE, session_id="2027-01-14_01"))
    _plays(second, ["right"])

    _step(second, _start(plan="other" if how == "another plan" else "train"))

    assert [(line["block"], line["params"]["set_size"]) for line in _run_lines(folders, 1)] == [
        ("Alone", 1)]
    assert [control.kind for control in _running(second, 1)[-1].controls].count("resumed") == 0


def test_a_console_start_at_a_named_block_starts_there(tmp_path):
    """The PI approved `Service._start` carrying the start's block (2026-11-07, asked in the UI;
    the build's welfare item): a console's start naming `Crowd` starts the run there, its start row
    saying so. One naming a block the plan lacks fails the pre-flight `_start` takes again for that
    block -- its task checks, as a check naming it says first -- so the gate refuses it and nothing
    starts, before `Session.run`'s backstop is reached."""
    folders = _folders(tmp_path, [ALONE, CROWD])
    service = _service(folders)
    _step(service, _open())
    checked = _step(service, CheckRun(by=JAKE, task="search.py", values=dict(VALUES),
                                      plan="train", start_block="Nope"))
    _plays(service, ["right"])
    refused = _step(service, _start(start_block="Nope"))
    _plays(service, ["right"])

    _step(service, _start(start_block="Crowd"))

    said = "plan 'train' has no block 'Nope'; its blocks are 'Alone', 'Crowd'"
    assert (checked.preflight.start_block, checked.preflight.items[0].result,
            checked.preflight.items[0].said) == ("Nope", FAIL, said)
    assert [(r.name, r.why) for r in refused.refusals][-1] == (
        "start", f"pre-flight failed, so the run does not start: task checks: {said}")
    (start,) = [row for row in _jsonl(_xcon(folders) / "runs.jsonl") if row["event"] == "start"]
    assert (start["plan"], start["start_block"]) == ("train", "Crowd")
    assert [(line["block"], line["params"]["set_size"]) for line in _run_lines(folders, 0)] == [
        ("Crowd", 6)]


def test_the_start_form_shows_yesterdays_end(tmp_path):
    """The PI's sketch of the trainer's screen (the design's §3.5): at the day's start, the stage,
    the staircase's starting level and the pairings to pick, "with yesterday's end shown". The
    pre-flight of a session's run says where the animal's previous session of that plan ended --
    read from its record, the staircase's level as its last step left it -- and offers the plan's
    stages, each staircase's levels and where it would start, and the pool's pairings; the page's
    Setup tab draws them. Nothing is carried on its own: the run starts where its start says."""
    folders = _folders(tmp_path, [ALONE, CROWD])
    first = _service(folders)
    _step(first, _open("2027-01-13_01"))
    _plays(first, ["right"] * 5,
           {0: [NextBlock(by=JAKE), SetParameter(name="pairings", value=5, by=JAKE)]})
    _step(first, _start())
    # Its last run is of another plan, which the start of a run of `train` does not show.
    _plays(first, ["right"])
    _step(first, _start(plan="other"))
    _step(first, EndSession(by=JAKE, session_id=None, returned="now", confirm=False))
    second = _service(folders)
    _step(second, _open())

    frame = _step(second, CheckRun(by=JAKE, task="search.py", values=dict(VALUES), plan="train"))

    preflight = frame.preflight
    said = ("session 2027-01-13_01's last run of plan train ended in Crowd; set_size at 8, by its "
            "staircase; pairings 5 (pairing 1, pairing 3)")
    assert preflight.previous == said
    assert preflight.stages == (
        StageRow("Alone"), StageRow("Crowd", "set_size", (4, 6, 8, 10), 1, False))
    assert preflight.pool == PoolRow("pairings", ("pairing 1", "pairing 2", "pairing 3"), 1)
    assert preflight.continues is None
    pane = fragments(frame, view())["preflight"]
    assert html.escape(said) in pane
    assert '<select id="start-block"' in pane and '<option value="Crowd"' in pane
    assert 'data-start-setting="set_size"' in pane and 'data-stage="Crowd"' in pane
    assert pane.count('data-pairing="') == 3
    _plays(second, ["right"])
    _step(second, _start())
    assert [line["block"] for line in _jsonl(_xcon(folders) / "trials.jsonl")] == ["Alone"]


def test_a_start_and_a_check_carry_their_start_block_and_a_preflight_its_start_on_the_wire():
    """The wire: `start` and `check` carry `start_block`, a word or null; the pre-flight on a frame
    carries where the run would start, its stages, its pool, the previous end and what a resumed
    run goes on from."""
    for command in (StartRun(by=JAKE, task="search.py", values={}, trials=1, acknowledged=(),
                             plan="train", start_block="Crowd"),
                    CheckRun(by=JAKE, task="search.py", values={}, plan="train",
                             start_block="Crowd"),
                    CheckRun(by=JAKE, task="search.py", values={}, plan="train")):
        assert _decode_command(_encode_command(command)) == command
    preflight = Preflight(
        "search.py", (PreflightItem("task checks", "pass", "it passes"),), plan="train",
        plans=("train",), start_block="Crowd",
        stages=(StageRow("Alone"), StageRow("Crowd", "set_size", (4, 6, 8, 10), 1, False)),
        pool=PoolRow("pairings", ("pairing 1", "pairing 2"), 1), previous="it ended in Crowd",
        continues="it goes on")
    from _frames import frame
    sent = frame(preflight=preflight)
    assert decode(encode(sent)).preflight == preflight


def test_a_record_the_resumed_run_cannot_read_back_starts_it_at_its_first_block(tmp_path):
    """The run that stopped is read back from its record, and a line it cannot read -- one torn of
    its place in the run -- is no refusal and no fault: the run starts at its plan's first block,
    as any run does, and its pre-flight says nothing goes on."""
    folders, second = _stranded_in(tmp_path, [ALONE, CROWD], ["right"] * 3,
                                   {0: [NextBlock(by=JAKE)]}, killed=True)
    path = _xcon(folders) / "trials.jsonl"
    lines = _jsonl(path)
    del lines[-1]["index"]
    path.write_text("".join(json.dumps(line) + "\n" for line in lines))
    # Its process stops again before any run, and a third resumes it from the torn record.
    third = _service(folders)
    _step(third)
    _step(third, ResumeSession(by=JAKE, session_id="2027-01-14_01"))
    checked = _step(third, CheckRun(by=JAKE, task="search.py", values=dict(VALUES),
                                    plan="train"))
    _plays(third, ["right"])

    _step(third, _start())

    assert checked.preflight.continues is None
    assert [(line["block"], line["params"]["set_size"]) for line in _run_lines(folders, 1)] == [
        ("Alone", 1)]


def test_the_pre_flight_says_what_the_resumed_run_comes_back_with_not_the_stopped_runs_values(
        tmp_path, monkeypatch):
    """The re-review, M-1: a stopped run's person-set values are not carried (XC-467), so the
    pre-flight's "goes on from" (`Session.continues`) judges the stage's bars on the values the run
    would start with -- the task's starts under the start's -- as the run does, never on the stopped
    run's. Alone's window, a setting `win` (4 to start), set to 2 live, met at 2 of 2, and the
    process stopped: the resumed run's bar reads 4 again, so neither the pre-flight nor the run's
    first frame says a suggestion stands."""
    import sys

    module = sys.modules[__name__]
    plain = module._source

    def windowed(stages, order=CONFIRMED, plans=""):
        text = plain(stages, order, plans)
        old = "Param('pairings', unit='pairings', low=1, high=7, start=1)"
        assert text.count(old) == 1
        text = text.replace(old, old + ", Param('win', unit='answers', low=1, high=10, start=4)")
        text = text.replace(
            "'pairings': Meaning(NOT_DIFFICULTY, NEITHER, note='which pairings are drawn')",
            "'pairings': Meaning(NOT_DIFFICULTY, NEITHER, note='which pairings are drawn'), "
            "'win': Meaning(NOT_DIFFICULTY, NEITHER, note='the bar\\'s window')")
        return "from wl_xcon.task import P\n" + text

    monkeypatch.setattr(module, "_source", windowed)
    alone = _stage("Alone", "(0.8, P('win'))", set_size=1)
    crowd = _stage("Crowd", (0.8, 2), staircase=STAIRS)
    folders, second = _stranded_in(tmp_path, [alone, crowd], ["right", "right", "right"],
                                   {0: [SetParameter(name="win", value=2, by=JAKE)]}, killed=True)
    assert [row["move"] for row in _changes(folders, "suggested")][:1] == ["up"]

    checked = _step(second, CheckRun(by=JAKE, task="search.py", values=dict(VALUES), plan="train"))
    continues = checked.preflight.continues
    assert continues is not None and "standing" not in continues, continues
    _plays(second, ["right"])
    _step(second, _start())
    first = _running(second, 1)[0]
    assert (first.block, first.suggestion) == ("Alone", None)

