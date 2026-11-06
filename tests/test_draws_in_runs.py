"""A run plays its draws and its generated conditions (engine build C3's spec §2, §4, §6 and §10;
closes XC-362).

Between trials, never in a frame, each trial draws each setting a draw gives it: the task's, which
a block type may replace, or its condition's own range (the PI, 2026-10-30: Q1a, "Task default,
block may replace"; Q1b, "Yes"), each value keyed by the run's seed, the trial's number in the run
and the setting, apart from the scheduler's generators. A repeat, ordinary or a drum's, takes each
setting's `same` or `fresh` (Q3, "Per drawn setting, required"; "Follow same/fresh"). A person's
value replaces a draw. A block's factors make ordinary conditions. Each trial's line says what it
drew and from where (`drawn`) and what a person held (`live`), a drawn direction written from 0 to
360; each run's start row records the task's draws, every field, and the conditions each
factorial made.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

import pytest

import _sessions
from _rig import DIRECT
from wl_xcon import variation
from wl_xcon.actor import Box
from wl_xcon.cli import _load_task
from wl_xcon.declarations import canonical
from wl_xcon.dio import Simulated as Card
from wl_xcon.geometry import shown_direction
from wl_xcon.link import SetParameter, Simulated
from wl_xcon.photometry import SRGB
from wl_xcon.run import Scripted
from wl_xcon.task import FRESH, SAME, SaccadeTo, TruncatedNormal, Uniform
from wl_xcon.taskd import Session, SessionSpec
from wl_xcon.welfare import Deployment, Simulated as Pump

ROOT = Path(__file__).resolve().parents[1]
#: The wall every session here reads from, plus its frames' seconds (`_session`).
WALL_NOW = 1_700_000_000.0
SEED = 7
#: A trial the animal breaks: it looks away from the fixation point at its sixth frame, before
#: any hold here is done, a fixation break, owed.
BREAK = Scripted({}, inside={frame: "fix" for frame in range(1, 6)})
#: The reference task's two target appearances, as Python source.
APPEARANCES = ('(Disc(size=1.0, color=Gray(P("target_luminance"))), '
               'Square(size=1.0, color=Gray(P("target_luminance"))))')


def _right(values: dict) -> Scripted:
    """A trial the animal gets right, whatever its fixation hold: it holds the fixation point 20
    frames past the hold, then looks at the target and stays on it."""
    held = round(values["fix_hold"] * 240) + 20
    return Scripted({SaccadeTo("target"): held + 10},
                    inside={frame: "fix" if frame <= held else "target"
                            for frame in range(1, held + 200)})


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


def _session(spec, link=None, world=None) -> Session:
    """On the simulators, its wall following its frames from `WALL_NOW`, the animal out of its
    cage and its head fixed then; against `world` where one is given, else the simulated
    animal."""
    session = Session(spec, card=Card(), pump=Pump(),
                      link=link if link is not None else Simulated())
    session.wall_clock = lambda: WALL_NOW + session.now()
    session.left_cage(at=WALL_NOW)
    session.head_fixed(at=session.wall_now())
    if world is not None:
        session.world = world
    return session


class _Drained(Simulated):
    """A link that queues `script[n]` as the `n`th drain begins: the loop drains once before each
    trial and once each time the plan moves to another block, and a command drained applies from
    the next trial."""

    def __init__(self, script):
        super().__init__()
        self.script, self.drains = dict(script), 0

    def drain(self) -> list:
        self.drains += 1
        for command in self.script.get(self.drains, ()):
            self.queue(command)
        return super().drain()


def _rows(session: Session, name: str) -> list[dict]:
    return [json.loads(line) for line in (session.directory / name).read_text().splitlines()]


def _lines(session: Session) -> list[dict]:
    return _rows(session, "trials.jsonl")


def _start(session: Session) -> dict:
    return next(row for row in _rows(session, "runs.jsonl") if row["event"] == "start")


def _declared(task, name: str):
    return next(param for param in task.params if param.name == name)


#: The task draws the fixation hold; block `own` replaces its draw, and block `ranged`'s
#: condition draws it from its own range, the block saying its conditions give it.
WHERE = dict(
    draws='{"fix_hold": Uniform(0.2, 0.4, repeat=FRESH)}',
    plans=('{"p": Plan([Block("plain", [Condition("c", {}, target=3)]), '
           'Block("own", [Condition("o", {}, target=3)], '
           'draws={"fix_hold": Uniform(0.5, 0.6, repeat=FRESH)}), '
           'Block("ranged", [Condition("r", {"fix_hold": Uniform(0.8, 0.9, repeat=FRESH)}, '
           'target=3)], draws={"fix_hold": BY_CONDITIONS})])}'),
)


def test_a_tasks_draw_a_blocks_and_a_conditions_own_range_each_draw_and_say_where_from(tmp_path):
    """The PI, 2026-10-30, Q1a ("Task default, block may replace": "one default for the task ...
    a block type may replace it (narrow or widen)") and Q1b ("a condition may draw its own setting
    from its own range; the trial counts toward the condition and records the value it got"). Each
    trial runs on the value drawn for it, its line records that value in `params` and where its
    draw came from in `drawn`, and the value is the keyed draw (engine build C3's calls 4 and 7):
    the run's seed, the trial's number in the run, the setting."""
    path = _sessions.varied_task(tmp_path, **WHERE)
    task = _load_task(path)
    blocks = {block.name: block for block in task.plans["p"].blocks}
    draws = {
        "plain": (task.draws["fix_hold"], ("task", "fix_hold")),
        "own": (blocks["own"].draws["fix_hold"], ("block", "own", "fix_hold")),
        "ranged": (blocks["ranged"].conditions[0].values["fix_hold"],
                   ("condition", "r", "fix_hold")),
    }
    ran = {}

    def world(trial, values, index):
        ran[index] = values["fix_hold"]
        return _right(values)

    session = _session(_spec(tmp_path, path, plan="p"), world=world)

    session.run()

    lines = _lines(session)
    assert [line["block"] for line in lines] == ["plain"] * 3 + ["own"] * 3 + ["ranged"] * 3
    for line in lines:
        drawn, key = draws[line["block"]]
        assert line["drawn"] == {"fix_hold": key[0]}
        assert line["params"]["fix_hold"] == ran[line["index"]] == variation.draw(
            drawn, SEED, line["index"], key, declared=_declared(task, "fix_hold"))
        assert drawn.low <= line["params"]["fix_hold"] <= drawn.high
    assert len({line["params"]["fix_hold"] for line in lines}) == 9


#: Every kind of draw, and a condition's own range in a block that replaces one of the task's.
REPLAYED = dict(
    draws=('{"target_x": Uniform(-10.0, 10.0, repeat=SAME), '
           '"target_y": TruncatedNormal(0.0, 8.0, repeat=FRESH), '
           '"fix_hold": NonAging(0.2, 0.3, 0.5, repeat=FRESH), '
           '"target_appearance": Listed(' + APPEARANCES + ', repeat=FRESH)}'),
    plans=('{"p": Plan([Block("a", [Condition("near", {}, target=3), '
           'Condition("far", {}, target=3)]), '
           'Block("b", [Condition("ranged", {"fix_luminance": Weighted((20.0, 40.0, 60.0), '
           '(1, 2, 1), repeat=SAME)}, target=4)], '
           'draws={"target_y": Uniform(-3.0, 3.0, repeat=SAME)})])}'),
)
DRAWN = ("target_x", "target_y", "fix_hold", "target_appearance", "fix_luminance")
#: Run in another process: `_replayed` of the folder it is given, as JSON.
REPLAY = (
    "import json, sys\n"
    "from pathlib import Path\n"
    "sys.path[:0] = [sys.argv[1], str(Path(sys.argv[1]) / 'tests')]\n"
    "import test_draws_in_runs as here\n"
    "print(json.dumps(here._replayed(Path(sys.argv[2]))))\n"
)


def _replayed(folder: Path, seed: int = SEED) -> list:
    """A run of `REPLAYED` against a world scripted by trial number -- every fourth trial from the
    second broken, owed, and shown again -- and what each line says it was and drew."""
    path = _sessions.varied_task(folder, **REPLAYED)

    def world(trial, values, index):
        return BREAK if index % 4 == 1 else _right(values)

    session = _session(_spec(folder, path, plan="p", seed=seed), world=world)
    session.run()
    return [[line["index"], line["condition"], line["repeat_of"], line["drawn"],
             {name: line["params"][name] for name in DRAWN}] for line in _lines(session)]


def test_one_seed_replays_the_same_draws_in_another_process(tmp_path):
    """TSK-06 ("a fresh seed per run, recorded; any run replayed exactly from its seed") and the
    C3 spec §2 ("a run replays from its seed and change log"): two processes run one task with
    one seed and draw alike -- a uniform, a truncated normal, the non-aging wait, a prepared list,
    a block's own draw and a condition's weighted range, on fresh trials and repeats. The draws are
    keyed hashes, holding no process's state. Both processes run with one `PYTHONHASHSEED`, and
    the world is scripted by trial number, so what is tested is the draws, not the simulated
    animal (the engine C3 plan's call 40; its review, I-8)."""

    def elsewhere(folder: Path) -> list:
        done = subprocess.run(
            [sys.executable, "-c", REPLAY, str(ROOT), str(folder)], cwd=ROOT,
            env={**os.environ, "PYTHONHASHSEED": "0"}, capture_output=True, text=True,
            timeout=300,
        )
        assert done.returncode == 0, done.stderr
        return json.loads(done.stdout.splitlines()[-1])

    first, second = elsewhere(tmp_path / "first"), elsewhere(tmp_path / "second")

    assert first == second
    assert any(repeat_of is not None for _, _, repeat_of, _, _ in first), "a trial shown again"
    task = _load_task(_sessions.varied_task(tmp_path / "here", **REPLAYED))
    wait, listed = task.draws["fix_hold"], task.draws["target_appearance"]
    assert [params["fix_hold"] for index, _, _, _, params in first] == [
        variation.draw(wait, SEED, index, ("task", "fix_hold")) for index, *_ in first]
    normal = [(index, params["target_y"]) for index, _, _, drawn, params in first
              if drawn["target_y"] == "task"]
    assert normal and all(value == variation.draw(
        task.draws["target_y"], SEED, index, ("task", "target_y"),
        declared=_declared(task, "target_y")) for index, value in normal), "cut to -16 to 16"
    assert [params["target_appearance"] for *_, params in first] == [
        canonical(variation.draw(listed, SEED, 0, ("task", "target_appearance"), ordinal=place),
                  every_field=True) for place in range(len(first))], "the list's passes, in turn"
    other = _replayed(tmp_path / "other", seed=SEED + 1)
    assert [params for *_, params in other] != [params for *_, params in first]


def test_adding_a_draw_moves_no_condition_or_repeat(tmp_path):
    """The C3 spec §2: each draw comes from a generator keyed by run seed, trial and setting,
    "apart from the scheduler's, so adding a draw moves no condition or repeat". The same task
    and seed against the simulated animal, without a draw and with one of a setting no state
    reads (the fixation point's luminance; a drawn wait would legitimately change the animal's
    ticks: the engine C3 plan's call 40), play the same conditions, break the same trials and
    show the same ones again."""
    plans = ('{"p": Plan([Block("b", [Condition("near", {"target_x": 5.0}, target=6), '
             'Condition("far", {"target_x": 12.0}, target=6)])])}')

    def played(folder: Path, draws: str) -> tuple[Session, list]:
        path = _sessions.varied_task(folder, draws=draws, plans=plans)
        session = _session(_spec(folder, path, plan="p"))
        session.run()
        return session, [(line["condition"], line["repeat_of"], line["at_once"], line["outcome"])
                         for line in _lines(session)]

    _, without = played(tmp_path / "without", "{}")
    session, drawing = played(tmp_path / "with",
                              '{"fix_luminance": Uniform(20.0, 60.0, repeat=FRESH)}')

    assert drawing == without
    assert any(repeat_of is not None for _, repeat_of, _, _ in without), "a trial shown again"
    lines = _lines(session)
    assert all(line["drawn"] == {"fix_luminance": "task"} for line in lines)
    assert len({line["params"]["fix_luminance"] for line in lines}) == len(lines)


#: One setting a repeat takes the same, one it draws fresh; a block that drums.
SAME_FRESH = dict(
    draws=('{"target_x": Uniform(-10.0, 10.0, repeat=SAME), '
           '"fix_luminance": Uniform(20.0, 60.0, repeat=FRESH)}'),
    plans=('{"p": Plan([Block("ordinary", [Condition("a", {}, target=3), '
           'Condition("b", {}, target=3)]), '
           'Block("drummed", [Condition("d", {}, target=2)], drum=True)])}'),
)


def test_a_same_setting_repeats_its_value_and_source_a_fresh_one_draws_anew_drummed_or_not(
        tmp_path):
    """The PI, 2026-10-30, Q3 ("each drawn setting declares same or fresh on a repeat") and the
    drummed repeat ("Follow same/fresh": "each drawn setting follows its own same or fresh, as
    ordinary repeats do"; XC-362's "keeps all its values" revised). Every first try of `a` breaks
    and is shown again later; every trial of `d`, in a block that drums, breaks twice and is right
    on its third try. A `same` setting's repeat carries the value and the source of the trial it
    shows again, kept, never drawn again (engine build C3's call 13): so when the draws' ranges
    change while a drum is going on (as a person's live range would, the engine C3 plan's Task 13,
    set here straight into the ranges in force with a change id, 9), the drum's tries keep the
    first try's value and source, and the next trial is drawn from the new range, naming it. A
    `fresh` setting is drawn on each try's own number, from the range in force."""
    path = _sessions.varied_task(tmp_path, **SAME_FRESH)
    task = _load_task(path)
    moved = {"target_x": Uniform(12.0, 14.0, repeat=SAME),
             "fix_luminance": Uniform(70.0, 80.0, repeat=FRESH)}
    changed: list[int] = []
    tries = [0]

    def world(trial, values, index):
        draw = session._scheduler.drawn
        if draw.condition.name == "d" and not changed:
            # After this trial's draws, before the next one's, where a live range lands.
            for name, drawn in moved.items():
                session._ranges[("task", name)] = (drawn, 9)
            changed.append(index)
        if draw.condition.name == "a" and draw.repeat_of is None:
            return BREAK
        if draw.condition.name == "d" and tries[0] < 2:
            tries[0] += 1
            return BREAK
        tries[0] = 0
        return _right(values)

    session = _session(_spec(tmp_path, path, plan="p"), world=world)

    session.run()

    lines = _lines(session)
    by_index = {line["index"]: line for line in lines}
    repeats = [line for line in lines if line["repeat_of"] is not None]
    assert sorted((line["condition"], line["drummed"]) for line in repeats) == (
        [("a", False)] * 3 + [("d", True)] * 4), "ordinary repeats, and two tries of each d"
    assert [line["drawn"]["target_x"] for line in lines if line["condition"] == "d"] == (
        ["task"] * 3 + [9] * 3), "a drum's tries keep the source their first try drew from"
    for line in repeats:
        shown = by_index[line["repeat_of"]]
        assert line["params"]["target_x"] == shown["params"]["target_x"]
        assert line["drawn"]["target_x"] == shown["drawn"]["target_x"]
        assert line["params"]["fix_luminance"] != shown["params"]["fix_luminance"]
    for line in lines:
        first = line
        while first["repeat_of"] is not None:
            first = by_index[first["repeat_of"]]
        if first["index"] > changed[0]:
            x_draw, x_from = moved["target_x"], 9
        else:
            x_draw, x_from = task.draws["target_x"], "task"
        if line["index"] > changed[0]:
            lum_draw, lum_from = moved["fix_luminance"], 9
        else:
            lum_draw, lum_from = task.draws["fix_luminance"], "task"
        assert line["drawn"] == {"target_x": x_from, "fix_luminance": lum_from}
        assert line["params"]["target_x"] == variation.draw(
            x_draw, SEED, first["index"], ("task", "target_x"))
        assert line["params"]["fix_luminance"] == variation.draw(
            lum_draw, SEED, line["index"], ("task", "fix_luminance"))
    assert session._kept == {}, "nothing kept once no repeat waits"


def test_a_persons_value_replaces_a_draw_live_and_overridden_where_the_condition_drew(tmp_path):
    """The C3 spec §6 (TSK-19, extended to draws): "a person's value replaces a draw (the task's,
    a block's, or a condition's own range). The trial is then not `drawn` for that setting, and is
    `overridden` where the draw was a condition's." Each line lists what a person held, `live`
    (engine build C3's spec §10)."""
    path = _sessions.varied_task(
        tmp_path,
        draws=('{"target_x": Uniform(-10.0, 10.0, repeat=FRESH), '
               '"fix_hold": Uniform(0.2, 0.4, repeat=FRESH)}'),
        plans=('{"p": Plan([Block("b", [Condition("ranged", '
               '{"fix_hold": Uniform(0.25, 0.35, repeat=FRESH)}, target=6)], '
               'draws={"fix_hold": BY_CONDITIONS})])}'),
    )
    link = _Drained({2: [SetParameter(name="target_x", value=12.0, by=Box("jake"))],
                     4: [SetParameter(name="fix_hold", value=0.5, by=Box("jake"))]})
    session = _session(_spec(tmp_path, path, plan="p"), link,
                       world=lambda trial, values, index: _right(values))

    session.run()

    lines = _lines(session)
    assert [(line["drawn"], line["live"], line["overridden"]) for line in lines] == (
        [({"target_x": "task", "fix_hold": "condition"}, [], [])] * 2
        + [({"fix_hold": "condition"}, ["target_x"], [])] * 2
        + [({}, ["fix_hold", "target_x"], ["fix_hold"])] * 2)
    assert [line["params"]["target_x"] for line in lines[2:]] == [12.0] * 4
    assert [line["params"]["fix_hold"] for line in lines[4:]] == [0.5] * 2
    assert all(0.25 <= line["params"]["fix_hold"] <= 0.35 for line in lines[:4])


#: A block of one hand-listed condition and those its factors make, a range of its own among the
#: levels, one combination excluded and one given its own number.
FACTORIAL = ('{"f": Plan([Block("grid", [Condition("hand", {"target_x": 0.0}, target=1)], '
             'factorial=Factorial({"target_x": (-5.0, 5.0), '
             '"fix_hold": (0.2, TruncatedNormal(0.35, 0.05, repeat=FRESH))}, '
             'exclude=({"target_x": -5.0, "fix_hold": 0.2},), target=2, '
             'targets={"target_x=5.0, fix_hold=0.2": 3}))])}')
LEFT_RANGED = "target_x=-5.0, fix_hold=normal of mean 0.35 and sd 0.05, cut to the setting's range"
RIGHT_FIXED = "target_x=5.0, fix_hold=0.2"
RIGHT_RANGED = "target_x=5.0, fix_hold=normal of mean 0.35 and sd 0.05, cut to the setting's range"


def test_generated_conditions_play_and_each_cell_owes_its_target(tmp_path):
    """TSK-22 ("the framework makes the combinations minus declared exclusions, each named from its
    levels; hand-listed conditions remain possible") and the PI, 2026-10-30, Q4 ("each remaining
    combination owes the same number, a hand-written number per combination allowed"): the block
    plays its hand-listed condition and each combination its exclusion leaves, each named from its
    levels, each its trials; a combination whose level is a range of its own draws from it."""
    path = _sessions.varied_task(tmp_path, plans=FACTORIAL)
    task = _load_task(path)
    made = {condition.name: condition
            for condition in variation.generated(task.plans["f"].blocks[0])}
    session = _session(_spec(tmp_path, path, plan="f"),
                       world=lambda trial, values, index: _right(values))

    session.run()

    lines = _lines(session)
    assert session.stop_kind == "completed"
    assert Counter(line["condition"] for line in lines) == {
        "hand": 1, LEFT_RANGED: 2, RIGHT_FIXED: 3, RIGHT_RANGED: 2}
    for line in lines:
        if line["condition"] == "hand":
            assert (line["drawn"], line["params"]["target_x"]) == ({}, 0.0)
            continue
        values = made[line["condition"]].values
        assert line["params"]["target_x"] == values["target_x"]
        if isinstance(values["fix_hold"], TruncatedNormal):
            assert line["drawn"] == {"fix_hold": "condition"}
            assert line["params"]["fix_hold"] == variation.draw(
                values["fix_hold"], SEED, line["index"],
                ("condition", line["condition"], "fix_hold"),
                declared=_declared(task, "fix_hold"))
        else:
            assert (line["drawn"], line["params"]["fix_hold"]) == ({}, 0.2)


def test_the_start_row_records_the_draws_with_every_field_and_the_generated_conditions(tmp_path):
    """The C3 spec §10 and §4 ("each run's start row lists them too, so the record needs no task
    file"; pitfall P20), with the engine C3 plan's call 12 (the controller's ruling 2): the task's
    draws as declared, every field, a normal's cut filled from its setting's range, and what each
    block's factors made, with their values, targets and the exclusions; `plan_form` stays the
    plan as declared. A run of a task drawing nothing records no draws and nothing made."""
    path = _sessions.varied_task(
        tmp_path, draws='{"target_y": TruncatedNormal(0.0, 4.0, repeat=SAME)}', plans=FACTORIAL)
    task = _load_task(path)
    session = _session(_spec(tmp_path, path, plan="f"),
                       world=lambda trial, values, index: _right(values))

    session.run()

    start = _start(session)
    assert start["draws"] == {"target_y": {"class": "TruncatedNormal", "fields": {
        "mean": 0.0, "sd": 4.0, "low": -16.0, "high": 16.0, "repeat": "same"}}}
    ranged = {"class": "TruncatedNormal", "fields": {
        "mean": 0.35, "sd": 0.05, "low": 0.05, "high": 2.0, "repeat": "fresh"}}
    assert start["generated"] == [{
        "block": "grid",
        "conditions": [
            {"name": LEFT_RANGED, "values": {"target_x": -5.0, "fix_hold": ranged}, "target": 2},
            {"name": RIGHT_FIXED, "values": {"target_x": 5.0, "fix_hold": 0.2}, "target": 3},
            {"name": RIGHT_RANGED, "values": {"target_x": 5.0, "fix_hold": ranged}, "target": 2},
        ],
        "excluded": [{"target_x": -5.0, "fix_hold": 0.2}],
    }]
    assert start["plan_form"] == canonical(task.plans["f"])
    (block,) = start["plan_form"]["fields"]["blocks"]
    assert [c["fields"]["name"] for c in block["fields"]["conditions"]] == ["hand"]

    plain = _sessions.varied_task(tmp_path / "plain")
    session = _session(_spec(tmp_path / "plain", plain, trials=2),
                       world=lambda trial, values, index: _right(values))
    session.run()
    start = _start(session)
    assert (start["draws"], start["generated"], start["directions"]) == (None, [], [])
    assert all(line["drawn"] == {} and line["live"] == [] for line in _lines(session))


def _directed(folder: Path, draws: str, plans: str = "{}") -> Path:
    """`varied_task` with its target placed by eccentricity and direction, `target_ecc` (8°) and
    `target_dir`, declared from -180 to 180 and starting at 0: the reference task's target and
    its window at `Polar(P("target_ecc"), P("target_dir"))`. Engine test material."""
    path = _sessions.varied_task(folder, draws=draws, plans=plans, name="directed")
    text = path.read_text()
    for old, new in (
        ('"target", at=(P("target_x"), P("target_y")), looks=P("target_appearance")',
         '"target", at=Polar(P("target_ecc"), P("target_dir")), looks=P("target_appearance")'),
        ('            at=(P("target_x"), P("target_y")),\n            radius=P("target_window"),',
         '            at=Polar(P("target_ecc"), P("target_dir")),\n'
         '            radius=P("target_window"),'),
        ('        Param("target_x", unit="deg", low=-16.0, high=16.0, start=10.0),',
         '        Param("target_ecc", unit="deg", low=0.0, high=16.0, start=8.0),\n'
         '        Param("target_dir", unit="deg", low=-180.0, high=180.0, start=0.0),\n'
         '        Param("target_x", unit="deg", low=-16.0, high=16.0, start=10.0),'),
    ):
        assert text.count(old) == 1, old
        text = text.replace(old, new)
    text = text.replace("from wl_xcon.task import (", "from wl_xcon.task import (\n    Polar,", 1)
    text += (
        "from wl_xcon.task import NOT_DIFFICULTY, STIMULUS, Meaning\n"
        "TASK = _dataclasses.replace(TASK, meanings={\n"
        "    **TASK.meanings,\n"
        "    'target_ecc': Meaning(NOT_DIFFICULTY, STIMULUS, note='how far out the target is'),\n"
        "    'target_dir': Meaning(NOT_DIFFICULTY, STIMULUS, note='which way the target is'),\n"
        "})\n"
    )
    path.write_text(text)
    return path


def test_a_drawn_direction_is_written_from_0_to_360_and_a_given_one_as_given(tmp_path):
    """The PI, 2026-10-30 ("0 to 360 in both repos"; and "Warn at load": a setting's number is
    shown and recorded as the number it holds), as the controller ruled on the engine C3 plan's
    outline review (I-6): a direction the rig draws is drawn in the task's own terms, -45 to 45,
    and the trial runs on it there, but its line writes it from 0 to 360, since the rig chose the
    number; a direction the task gives (a condition's -90) or a person gives (a live -30) is
    written as given. The start row writes the draw's range from 0 to 360, crossing rightward,
    315 to 45."""
    path = _directed(
        tmp_path, '{"target_dir": Uniform(-45.0, 45.0, repeat=FRESH)}',
        plans=('{"p": Plan([Block("given", [Condition("left", {"target_dir": -90.0}, target=2)], '
               'draws={"target_dir": BY_CONDITIONS}), '
               'Block("drawn", [Condition("c", {}, target=6)])])}'))
    task = _load_task(path)
    # The 7th drain: one before each of the first five trials and one as the plan moves on.
    link = _Drained({7: [SetParameter(name="target_dir", value=-30.0, by=Box("jake"))]})
    ran = {}

    def world(trial, values, index):
        ran[index] = values["target_dir"]
        return _right(values)

    session = _session(_spec(tmp_path, path, plan="p"), link, world=world)

    session.run()

    lines = _lines(session)
    assert [line["block"] for line in lines] == ["given"] * 2 + ["drawn"] * 6
    drawn = [variation.draw(task.draws["target_dir"], SEED, line["index"],
                            ("task", "target_dir")) for line in lines[2:6]]
    assert any(value < 0 for value in drawn), "a direction drawn below 0"
    assert [ran[line["index"]] for line in lines[2:6]] == drawn, "run in the task's own terms"
    assert [line["params"]["target_dir"] for line in lines[2:6]] == [
        shown_direction(value) for value in drawn]
    assert all(0 <= line["params"]["target_dir"] < 360 for line in lines[2:6])
    assert [(line["params"]["target_dir"], line["drawn"], line["live"]) for line in lines] == (
        [(-90.0, {}, [])] * 2
        + [(line["params"]["target_dir"], {"target_dir": "task"}, []) for line in lines[2:6]]
        + [(-30.0, {}, ["target_dir"])] * 2)
    assert _start(session)["draws"] == {"target_dir": {"class": "Uniform", "fields": {
        "low": 315.0, "high": 45.0, "repeat": "fresh"}}}
    # Named as a direction, for circular statistics (the plan's science review, M-4).
    assert _start(session)["directions"] == ["target_dir"]


def test_a_non_aging_wait_is_between_its_shortest_and_longest_every_trial(tmp_path):
    """The PI, 2026-10-30, Q2 ("Draw again": "every wait falls between the shortest and the
    longest"): over a run, every fixation hold drawn from a non-aging wait of 0.2 to 0.6 s is
    inside it, is what the trial ran on, and is the keyed draw."""
    path = _sessions.varied_task(tmp_path, draws='{"fix_hold": NonAging(0.2, 0.3, 0.6, '
                                                 'repeat=FRESH)}')
    task = _load_task(path)
    ran = {}

    def world(trial, values, index):
        ran[index] = values["fix_hold"]
        return _right(values)

    session = _session(_spec(tmp_path, path, trials=60), world=world)

    session.run()

    lines = _lines(session)
    waits = [line["params"]["fix_hold"] for line in lines]
    assert len(waits) == 60 and len(set(waits)) == 60
    assert all(0.2 <= wait <= 0.6 for wait in waits)
    assert waits == [ran[line["index"]] for line in lines]
    assert waits == [variation.draw(task.draws["fix_hold"], SEED, line["index"],
                                    ("task", "fix_hold")) for line in lines]


@pytest.mark.parametrize("draws, plans, said", [
    ('{"target_appearance": Weighted(' + APPEARANCES + ', (1, 1), repeat=FRESH)}', "{}",
     re.escape("value 2 of the task's draw of 'target_appearance'")),
    ("{}", ('{"p": Plan([Block("b", [Condition("c", {}, target=3)], '
            'draws={"target_appearance": Listed(' + APPEARANCES + ', repeat=FRESH)})])}'),
     re.escape("value 2 of block 'b''s draw of 'target_appearance'")),
    ("{}", ('{"p": Plan([Block("b", [Condition("c", {"target_appearance": Weighted('
            + APPEARANCES + ', (1, 1), repeat=SAME)}, target=3)])])}'),
     re.escape("value 2 of condition 'c''s own range for 'target_appearance'")),
    ("{}", ('{"p": Plan([Block("b", [], factorial=Factorial({"target_appearance": '
            + APPEARANCES + '}, target=2))])}'),
     r"the value condition \"target_appearance=Square\(.*\)\" of block 'b' sets for "
     r"'target_appearance'"),
], ids=["task", "block", "condition", "factorial"])
def test_a_drawn_item_the_record_cannot_write_stops_the_run_before_it_starts(
        tmp_path, monkeypatch, draws, plans, said):
    """REC-27; the appearance-record review's M2, for drawn values (engine build C3's call 35): a
    value a draw can give is written on its trial's line like a condition's, after the trial ran
    and rewarded. So each value a weighted set or a prepared list can give -- the task's, a
    block's, a condition's own range -- and each value a factorial's levels give its conditions is
    tried in the record's writer as the run starts, and one it refuses stops the run before it is
    numbered, strobed or written, the sentence naming the draw. Here the record refuses the
    reference task's square, as `tests/test_taskd.py` has it refuse one; `check` lets nothing in
    today that the record refuses, so this is the backstop."""
    import wl_xcon.record as record

    written = record._written
    square = _declared(_load_task(_sessions.varied_task(tmp_path / "shapes")),
                       "target_appearance").choices[1]

    def refusing(value):
        if value == square:
            raise TypeError("the record writes no Square value")
        return written(value)

    monkeypatch.setattr(record, "_written", refusing)
    path = _sessions.varied_task(tmp_path, draws=draws, plans=plans)
    spec = _spec(tmp_path, path, plan=None if plans == "{}" else "p", trials=3)
    session = _session(spec)
    before = list(session.card.codes)

    with pytest.raises(TypeError, match=f"the record cannot write {said}"):
        session.run()

    assert session.run_index is None
    assert session.welfare.commanded == 0.0
    assert session.card.codes == before
    assert not (session.directory / "runs.jsonl").exists()
    assert not (session.directory / "trials.jsonl").exists()
