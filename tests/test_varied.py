"""What varied, and the designed plan, in the record (engine build C3's spec §5 and §10; XC-344).

Each `block_ends` entry on a run's end row says what varied in its block and how (`varied`): its
conditions giving a setting different values or ranges of their own, a draw -- from where, as its
trials' lines name it (`drawn`), and the draw itself, every field -- or a person holding it, read
from what the block declared and did, never from the values its trials happened to get. A
designed block's entry also gives its plan (`planned`): a sequence-balanced block's condition
names in the order planned, played or not, or a priming block's runs as far as it played them.
Each trial line names its place in a designed block's plan (`planned`), which a drum's try and a
trial played again at once share with the trial they show again. Each entry also counts, for
each condition, its trial lines in the block, those a person's value overrode and those kept out
of moving up (`counts`; the engine C3 plan's science review, M-4). XC-344's premise
("uncertainty about where a target appears raises thresholds") is cited to [@cohn1985effect] and
[@pelli1985uncertainty] in REC-28.
"""

from __future__ import annotations

import dataclasses
import json
import random

import _sessions
from _rig import DIRECT
from wl_xcon import taskd
from wl_xcon.actor import Box
from wl_xcon.dio import Simulated as Card
from wl_xcon.link import BackBlock, Drum, HandBack, NextBlock, SetParameter, SetRange, Simulated
from wl_xcon.photometry import SRGB
from wl_xcon.run import Scripted
from wl_xcon.task import Outcome, SaccadeTo
from wl_xcon.taskd import RunSpec, Session, SessionSpec
from wl_xcon.variation import balanced_sequence
from wl_xcon.welfare import Deployment, Simulated as Pump

#: The wall every session here reads from, plus its frames' seconds (`_session`).
WALL_NOW = 1_700_000_000.0
SEED = 7
JAKE = Box("jake")
#: A trial the animal breaks: it looks away from the fixation point at its sixth frame, before
#: any hold here is done, a fixation break before the target appears.
BREAK = Scripted({}, inside={frame: "fix" for frame in range(1, 6)})


def _right(values: dict) -> Scripted:
    """A trial the animal gets right, whatever its holds: it holds the fixation point 20 frames
    past its hold, then looks at the target and stays on it."""
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


def _session(spec, link=None, world=_always_right, *, service=False) -> Session:
    """On the simulators, its wall following its frames from `WALL_NOW`, the animal out of its
    cage and its head fixed then, and `world` giving each trial; a `wlx taskd` one opened."""
    session = Session(spec, card=Card(), pump=Pump(),
                      link=link if link is not None else Simulated(), service=service)
    session.wall_clock = lambda: WALL_NOW + session.now()
    session.left_cage(at=WALL_NOW)
    session.head_fixed(at=session.wall_now())
    session.world = world
    if service:
        session.open(how="wlx taskd")
    return session


class _Drained(Simulated):
    """A link that queues `script[n]` as the `n`th drain begins. The loop drains once before each
    trial and once each time the plan moves to another block; a value drained before trial `n`
    applies from trial `n + 1`."""

    def __init__(self, script):
        super().__init__()
        self.script, self.drains = dict(script), 0

    def drain(self) -> list:
        self.drains += 1
        for command in self.script.get(self.drains, ()):
            self.queue(command)
        return super().drain()


def _scripted(monkeypatch, outcomes: list) -> None:
    """Every trial ends with the next of `outcomes` and lasts 240 frames, so a block's time reads
    exactly: one second and the 0.5 s ITI a trial."""
    real, calls = taskd.run_trial, []

    def scripted(*args, **kwargs):
        calls.append(None)
        return dataclasses.replace(real(*args, **kwargs), outcome=outcomes[len(calls) - 1],
                                   frames=240)

    monkeypatch.setattr(taskd, "run_trial", scripted)


def _rows(session: Session, name: str) -> list[dict]:
    return [json.loads(line) for line in (session.directory / name).read_text().splitlines()]


def _lines(session: Session) -> list[dict]:
    return _rows(session, "trials.jsonl")


def _end(session: Session) -> dict:
    return next(row for row in _rows(session, "runs.jsonl") if row["event"] == "end")


def _uniform(low: float, high: float, repeat: str = "fresh") -> dict:
    """A uniform draw as the record writes it: its class and every field, its `repeat` among
    them (the engine C3 plan's call 12)."""
    return {"class": "Uniform", "fields": {"low": low, "high": high, "repeat": repeat}}


def _drew(source, low: float, high: float, repeat: str = "fresh") -> dict:
    """One way a setting varied: drawn from `source`, as its trials' lines name it."""
    return {"by": "draw", "from": source, "distribution": _uniform(low, high, repeat)}


CONDITION, PERSON = {"by": "condition"}, {"by": "person"}


def test_each_block_end_says_what_varied_by_condition_draw_and_person(tmp_path):
    """XC-344: each block's end says what varied in it and how, read from what the block declared
    and did. The task draws its fixation hold in every block. The first block draws its target
    window from a normal of its own, which the record writes with the cut it is drawn to, the
    window's declared range; its two conditions give the target two luminances, and one of them a
    vertical place the other leaves to the run; both give the fixation point one luminance, which
    therefore did not vary; and a person holds the target's horizontal place on its third and
    fourth trials. In the second block, whose one condition gives nothing, a person holds the
    fixation hold on its first trial and hands it back, and the draw gives it on its second: the
    draw is listed first, then the person, whatever came first. No block plays a designed order,
    so no line or end has a plan."""
    path = _sessions.varied_task(
        tmp_path, draws='{"fix_hold": Uniform(0.25, 0.35, repeat=FRESH)}', plans=(
            '{"p": Plan([Block("mixed", ['
            'Condition("a", {"target_luminance": 30.0, "fix_luminance": 40.0, '
            '"target_y": 2.0}, target=2), '
            'Condition("b", {"target_luminance": 60.0, "fix_luminance": 40.0}, target=2)], '
            'draws={"target_window": TruncatedNormal(3.0, 0.25, repeat=FRESH)}), '
            'Block("still", [Condition("c", {}, target=2)])])}'))
    link = _Drained({2: [SetParameter(name="target_x", value=-10.0, by=JAKE)],
                     4: [HandBack(name="target_x", by=JAKE),
                         SetParameter(name="fix_hold", value=0.3, by=JAKE)],
                     6: [HandBack(name="fix_hold", by=JAKE)]})
    session = _session(_spec(tmp_path, path, plan="p"), link)

    session.run()

    assert session.refusals == []
    lines = _lines(session)
    both = {"fix_hold": "task", "target_window": "block"}
    assert [(line["block"], line["live"], line["drawn"]) for line in lines] == [
        ("mixed", [], both), ("mixed", [], both), ("mixed", ["target_x"], both),
        ("mixed", ["target_x"], both), ("still", ["fix_hold"], {}),
        ("still", [], {"fix_hold": "task"})]
    assert [line["planned"] for line in lines] == [None] * 6
    hold = _drew("task", 0.25, 0.35)
    window = {"by": "draw", "from": "block", "distribution": {
        "class": "TruncatedNormal",
        "fields": {"mean": 3.0, "sd": 0.25, "low": 0.5, "high": 6.0, "repeat": "fresh"}}}
    assert [(end["block"], end["varied"], end["planned"])
            for end in _end(session)["block_ends"]] == [
        ("mixed", {"fix_hold": [hold], "target_luminance": [CONDITION],
                   "target_window": [window], "target_x": [PERSON],
                   "target_y": [CONDITION]}, None),
        ("still", {"fix_hold": [hold, PERSON]}, None)]


def test_a_live_range_adds_its_change_to_what_varied(tmp_path):
    """A draw a person changed live is a draw of its own (the PI, 2026-10-30, Q7b: "the record says
    which range each trial was drawn from"): the block's end lists the declared draw its first
    trials named, then each range a person put in force, named by the change that put it there as
    the trials' lines name it, every field."""
    path = _sessions.varied_task(
        tmp_path, draws='{"fix_window": Uniform(1.5, 2.5, repeat=FRESH)}')
    link = _Drained({2: [SetRange(name="fix_window", numbers={"low": 1.0, "high": 3.0},
                                  by=JAKE)],
                     4: [SetRange(name="fix_window", numbers={"low": 0.5, "high": 1.0},
                                  by=JAKE)]})
    session = _session(_spec(tmp_path, path, trials=6), link)

    session.run()

    assert session.refusals == []
    assert [line["drawn"] for line in _lines(session)] == (
        [{"fix_window": "task"}] * 2 + [{"fix_window": 1}] * 2 + [{"fix_window": 2}] * 2)
    (end,) = _end(session)["block_ends"]
    assert end["varied"] == {"fix_window": [
        _drew("task", 1.5, 2.5), _drew(1, 1.0, 3.0), _drew(2, 0.5, 1.0)]}


def test_a_direction_drawn_varied_from_its_range_written_from_0_to_360(tmp_path):
    """A drawn direction's range is written as the rig draws it, from 0 to 360 (the PI,
    2026-10-30, "0 to 360 in both repos"; the engine C3 plan's call 11), in a block's `varied` as
    in the start row's `draws`: the task declares its target's direction drawn from -45 to 45, so
    the block's end writes the range 315 to 45, crossing rightward."""
    path = _sessions.varied_task(
        tmp_path, draws='{"target_dir": Uniform(-45.0, 45.0, repeat=FRESH)}', name="directed")
    # The target and its window placed by `target_ecc` (8°) and `target_dir`, declared from -180
    # to 180, as the engine C3 plan's Task 10 places them; `Polar` imported by the task's own
    # first import, ahead of the target.
    text = path.read_text().replace(
        "from wl_xcon.task import (", "from wl_xcon.task import (\n    Polar,", 1)
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
    path.write_text(text + (
        "from wl_xcon.task import NOT_DIFFICULTY, STIMULUS, Meaning\n"
        "TASK = _dataclasses.replace(TASK, meanings={\n"
        "    **TASK.meanings,\n"
        "    'target_ecc': Meaning(NOT_DIFFICULTY, STIMULUS, note='how far out the target is'),\n"
        "    'target_dir': Meaning(NOT_DIFFICULTY, STIMULUS, note='which way the target is'),\n"
        "})\n"))
    session = _session(_spec(tmp_path, path, trials=2))

    session.run()

    assert session.refusals == []
    (end,) = _end(session)["block_ends"]
    assert end["varied"] == {"target_dir": [_drew("task", 315.0, 45.0)]}


def test_a_value_a_repeat_keeps_adds_nothing_to_what_varied(tmp_path):
    """A `SAME` setting's repeat shows the value the trial it repeats drew, with that trial's
    source (the engine C3 plan's call 13), so it adds no way of its own: that trial, in the same
    block, named its draw already. The second trial breaks under drumming, and a person widens the
    fixation window's draw before its drum's try, which keeps the window drawn from the range as
    declared: the block's end lists the declared draw and the widened range once each, and never
    the widened range under the declared draw's name."""
    path = _sessions.varied_task(
        tmp_path, draws='{"fix_window": Uniform(1.5, 2.5, repeat=SAME)}')

    def world(trial, values, index):
        return BREAK if index == 1 else _right(values)

    link = _Drained({1: [Drum(scope="run", by=JAKE)],
                     2: [SetRange(name="fix_window", numbers={"low": 1.0, "high": 3.0},
                                  by=JAKE)]})
    session = _session(_spec(tmp_path, path, trials=3), link, world=world)

    session.run()

    assert session.refusals == []
    # The drum switch took change 1 (a `drum` row), so the range is change 2.
    assert [(line["drummed"], line["repeat_of"], line["drawn"]) for line in _lines(session)] == [
        (False, None, {"fix_window": "task"}), (False, None, {"fix_window": "task"}),
        (True, 1, {"fix_window": "task"}), (False, None, {"fix_window": 2})]
    (end,) = _end(session)["block_ends"]
    assert end["varied"] == {"fix_window": [
        _drew("task", 1.5, 2.5, "same"), _drew(2, 1.0, 3.0, "same")]}


def test_conditions_drawing_from_ranges_of_their_own_vary_by_condition_and_by_each_range(
        tmp_path):
    """A condition's own range (the PI, 2026-10-30, Q1b) is a draw its trials' lines name
    `"condition"`. Where a block's conditions draw one setting from different ranges of their own,
    the setting varied by condition, and the block's end lists each range as a draw, once, in the
    order its trials first drew from it: two conditions sharing a range give one."""
    path = _sessions.varied_task(tmp_path, plans=(
        '{"p": Plan([Block("own", ['
        'Condition("narrow", {"fix_window": Uniform(1.5, 2.5, repeat=FRESH)}, target=2), '
        'Condition("also", {"fix_window": Uniform(1.5, 2.5, repeat=FRESH)}, target=2), '
        'Condition("wide", {"fix_window": Uniform(1.0, 3.0, repeat=FRESH)}, target=2)])])}'))
    session = _session(_spec(tmp_path, path, plan="p"))

    session.run()

    assert session.refusals == []
    lines = _lines(session)
    assert {line["condition"] for line in lines} == {"narrow", "also", "wide"}
    assert [line["drawn"] for line in lines] == [{"fix_window": "condition"}] * 6
    ranges = {"narrow": _drew("condition", 1.5, 2.5), "also": _drew("condition", 1.5, 2.5),
              "wide": _drew("condition", 1.0, 3.0)}
    first = []
    for line in lines:
        if ranges[line["condition"]] not in first:
            first.append(ranges[line["condition"]])
    assert len(first) == 2
    (end,) = _end(session)["block_ends"]
    assert end["varied"] == {"fix_window": [CONDITION, *first]}


def test_a_block_that_ran_no_trial_varied_nothing(tmp_path):
    """A block a person moved past before its first trial ran none, and nothing varied in it,
    whatever it declared: its conditions give the target two luminances and the task draws the
    fixation hold, yet its end says `{}`. The next block's end says what its trials drew."""
    path = _sessions.varied_task(
        tmp_path, draws='{"fix_hold": Uniform(0.25, 0.35, repeat=FRESH)}', plans=(
            '{"p": Plan([Block("skipped", ['
            'Condition("a", {"target_luminance": 30.0}, target=1), '
            'Condition("b", {"target_luminance": 60.0}, target=1)]), '
            'Block("played", [Condition("c", {}, target=2)])])}'))
    link = _Drained({1: [NextBlock(by=JAKE)]})
    session = _session(_spec(tmp_path, path, plan="p"), link)

    session.run()

    assert session.refusals == []
    assert [(end["block"], end["ended"], end["block_in_session"], end["varied"], end["counts"])
            for end in _end(session)["block_ends"]] == [
        ("skipped", "next", None, {}, {}),
        ("played", "rule", 1, {"fix_hold": [_drew("task", 0.25, 0.35)]},
         {"c": {"trials": 2, "overridden": 0, "eased": 0}})]


def test_each_run_says_only_what_varied_in_its_own_blocks(tmp_path):
    """A `wlx taskd` session plays several runs, and each run's end row says what varied in its own
    blocks alone: the first run's conditions give the target two luminances; the second, a plain
    run of the same task, varied nothing, its one block the first of its own run as the first
    run's was."""
    path = _sessions.varied_task(tmp_path, plans=(
        '{"p": Plan([Block("mixed", ['
        'Condition("a", {"target_luminance": 30.0}, target=1), '
        'Condition("b", {"target_luminance": 60.0}, target=1)])])}'))
    session = _session(_spec(tmp_path, "", trials=0, values={}), service=True)
    values = {"target_appearance": None}

    session.run(RunSpec(task=str(path), trials=0, seed=SEED, values=values, plan="p"))
    session.run(RunSpec(task=str(path), trials=2, seed=SEED, values=values))

    assert session.refusals == []
    ends = [row for row in _rows(session, "runs.jsonl") if row["event"] == "end"]
    assert [[(block["block"], block["varied"]) for block in end["block_ends"]]
            for end in ends] == [[("mixed", {"target_luminance": [CONDITION]})], [("session", {})]]
    once = {"trials": 1, "overridden": 0, "eased": 0}
    assert [[block["counts"] for block in end["block_ends"]] for end in ends] == [
        [{"a": once, "b": once}], [{"session": {"trials": 2, "overridden": 0, "eased": 0}}]]


def test_each_block_end_counts_each_conditions_trials_those_overridden_and_those_eased(tmp_path):
    """The C3 plan's science review, M-4: a condition's trials count toward it whatever a person
    did, so a factorial cell can be met by trials that never showed its level. Each block's end
    says, for each condition that ran a trial, its trial lines in the block, those on which a
    person's value overrode what its condition set (`overridden`), and those kept out of moving up
    (`eased`). A person widens the fixation window from the third trial, which eases every trial
    after it, and holds the target's luminance, which both conditions set, from the fifth."""
    path = _sessions.varied_task(tmp_path, plans=(
        '{"p": Plan([Block("mixed", ['
        'Condition("a", {"target_luminance": 30.0}, target=3), '
        'Condition("b", {"target_luminance": 60.0}, target=3)])])}'))
    link = _Drained({2: [SetParameter(name="fix_window", value=3.0, by=JAKE)],
                     4: [SetParameter(name="target_luminance", value=45.0, by=JAKE)]})
    session = _session(_spec(tmp_path, path, plan="p"), link)

    session.run()

    assert session.refusals == []
    lines = _lines(session)
    assert [(bool(line["overridden"]), bool(line["eased"])) for line in lines] == (
        [(False, False)] * 2 + [(False, True)] * 2 + [(True, True)] * 2)
    (end,) = _end(session)["block_ends"]
    assert end["counts"] == {
        condition: {"trials": sum(1 for line in mine),
                    "overridden": sum(1 for line in mine if line["overridden"]),
                    "eased": sum(1 for line in mine if line["eased"])}
        for condition in ("a", "b")
        for mine in [[line for line in lines if line["condition"] == condition]]}
    assert [end["counts"][name]["trials"] for name in ("a", "b")] == [3, 3]


def test_a_designed_blocks_lines_carry_their_planned_place_and_its_end_its_plan(tmp_path):
    """Each trial of a designed block names its place in the block's plan (`planned`), and the
    block's end its plan. A sequence-balanced block's plan is its condition names in the order
    planned, the sequence the run's seed draws for the block's opening (the engine C3 plan's call
    15), each line its cycle and position. A priming block's is its runs as it played them,
    `{value, length}` each (the controller's ruling on the plan's Task 6), each line its run,
    whether it is the run's first, and the value planned, which its condition gives it; each run
    as long as drawn, but the last, which the block's trials cut, and each switch a new value."""
    path = _sessions.varied_task(tmp_path, plans=(
        '{"p": Plan([Block("seq", ['
        'Condition("a", {"target_luminance": 30.0}, target=2), '
        'Condition("b", {"target_luminance": 60.0}, target=2)], order=SequenceBalanced()), '
        'Block("prime", ['
        'Condition("dim", {"target_luminance": 30.0}, target=0), '
        'Condition("bright", {"target_luminance": 60.0}, target=0)], '
        'order=Priming("target_luminance", runs=(2, 3)), trials=7)])}'))
    session = _session(_spec(tmp_path, path, plan="p"))

    session.run()

    assert session.refusals == []
    lines = _lines(session)
    ends = _end(session)["block_ends"]
    assert [(end["block"], end["ended"]) for end in ends] == [("seq", "rule"), ("prime", "rule")]
    sequence = [line for line in lines if line["block"] == "seq"]
    assert ends[0]["planned"] == list(
        balanced_sequence(["a", "b"], 2, 1, random.Random(f"design:{SEED}:0")))
    assert [(line["condition"], line["planned"]) for line in sequence] == [
        (name, {"cycle": 0, "position": place, "lead_in": place == 0})
        for place, name in enumerate(ends[0]["planned"])]

    primed = [line for line in lines if line["block"] == "prime"]
    plan = ends[1]["planned"]
    runs = [[line for line in primed if line["planned"]["run"] == run] for run in range(len(plan))]
    assert [len(run) for run in runs[:-1]] == [planned["length"] for planned in plan[:-1]]
    assert 1 <= len(runs[-1]) <= plan[-1]["length"] and sum(map(len, runs)) == len(primed) == 7
    assert all(2 <= planned["length"] <= 3 for planned in plan)
    assert all(before["value"] != after["value"] for before, after in zip(plan, plan[1:]))
    assert [(line["planned"]["switch"], line["planned"]["value"]) for line in primed] == [
        (place == 0, planned["value"]) for planned, run in zip(plan, runs)
        for place in range(len(run))]
    assert all(line["params"]["target_luminance"] == line["planned"]["value"] for line in primed)
    assert {planned["value"] for planned in plan} == {30.0, 60.0}
    assert [end["varied"] for end in ends] == [{"target_luminance": [CONDITION]}] * 2


def test_a_sequence_balanced_block_cut_by_its_trials_lists_the_places_it_did_not_play(tmp_path):
    """The engine C3 plan's review, I-3: a sequence-balanced block ends at whichever comes first,
    its plan played out or its number of trials run, and owes nothing then. Its five trials play
    the first five of its ten places, its cycle the linear sequence (the PI, 2026-10-31); its end
    lists all ten, the five never played named by no line, and the run writes no shortfall (the
    controller's ruling on the plan's Task 3)."""
    path = _sessions.varied_task(tmp_path, plans=(
        '{"p": Plan([Block("seq", [Condition("a", {}, target=3), Condition("b", {}, target=3), '
        'Condition("c", {}, target=3)], order=SequenceBalanced(), trials=5)])}'))
    session = _session(_spec(tmp_path, path, plan="p"))

    session.run()

    assert session.refusals == []
    end = _end(session)
    (block,) = end["block_ends"]
    assert (block["ended"], block["after_trial"]) == ("rule", 4)
    assert block["planned"] == list(
        balanced_sequence(["a", "b", "c"], 2, 1, random.Random(f"design:{SEED}:0")))
    assert [(line["condition"], line["planned"]) for line in _lines(session)] == [
        (name, {"cycle": 0, "position": place, "lead_in": place == 0})
        for place, name in enumerate(block["planned"][:5])]
    assert end["shortfalls"] == []


def test_a_sequence_balanced_block_the_runs_time_cuts_owes_nothing_and_lists_its_plan(
        tmp_path, monkeypatch):
    """The run's own time limit cuts a sequence-balanced block as its number of trials does
    (the engine C3 plan's call 15): its end lists every place, played or not, and the run writes
    no shortfall, `run_time` included, for the places it never reached (the controller's ruling
    on the plan's Task 3). Each trial lasts a second and its 0.5 s ITI, so the plan's 4 s are up
    after the third trial."""
    _scripted(monkeypatch, [Outcome.CORRECT] * 10)
    path = _sessions.varied_task(tmp_path, plans=(
        '{"p": Plan([Block("seq", [Condition("a", {}, target=2), Condition("b", {}, target=2)], '
        'order=SequenceBalanced())], time_limit_s=4.0)}'))
    session = _session(_spec(tmp_path, path, plan="p"))

    session.run()

    assert session.refusals == []
    end = _end(session)
    (block,) = end["block_ends"]
    assert (block["ended"], end["end_reason"]) == ("run_time", "plan_time")
    assert block["planned"] == list(
        balanced_sequence(["a", "b"], 2, 1, random.Random(f"design:{SEED}:0")))
    assert [line["planned"] for line in _lines(session)] == [
        {"cycle": 0, "position": place, "lead_in": place == 0} for place in range(3)]
    assert end["shortfalls"] == []


def test_a_designed_shortfall_is_on_the_end_row(tmp_path):
    """A break in a sequence-balanced block is not played again by default (the PI, 2026-10-30,
    Q5b; the engine C3 plan's call 17): its place is lost, and the end row's `shortfalls` say so,
    `because` `"designed"`, one trial, never flagged, after the trial that broke, whose line names
    the place lost. A block that plays its broken trial again at once loses none: the trial comes
    straight back with the same planned place, and writes no shortfall."""
    path = _sessions.varied_task(tmp_path, plans=(
        '{"p": Plan([Block("seq", [Condition("a", {}, target=2), Condition("b", {}, target=2)], '
        'order=SequenceBalanced()), '
        'Block("again", [Condition("c", {}, target=2), Condition("d", {}, target=2)], '
        'order=SequenceBalanced(again_at_once=True))])}'))

    def world(trial, values, index):
        return BREAK if index in (1, 6) else _right(values)

    session = _session(_spec(tmp_path, path, plan="p"), world=world)

    session.run()

    assert session.refusals == []
    place = [{"cycle": 0, "position": position, "lead_in": position == 0}
             for position in range(5)]
    assert [(line["block"], line["outcome"], line["repeat_of"], line["at_once"], line["planned"])
            for line in _lines(session)] == [
        ("seq", "correct", None, False, place[0]),
        ("seq", "fixation_break", None, False, place[1]),
        ("seq", "correct", None, False, place[2]),
        ("seq", "correct", None, False, place[3]),
        ("seq", "correct", None, False, place[4]),
        ("again", "correct", None, False, place[0]),
        ("again", "fixation_break", None, False, place[1]),
        ("again", "correct", 6, True, place[1]),
        ("again", "correct", None, False, place[2]),
        ("again", "correct", None, False, place[3]),
        ("again", "correct", None, False, place[4])]
    end = _end(session)
    assert end["shortfalls"] == [{
        "block": "seq", "condition": end["block_ends"][0]["planned"][1], "trials": 1,
        "because": "designed", "possible_avoidance": False, "after_trial": 1, "by": None}]


def test_a_sequence_balanced_block_a_trainer_disturbs_records_each_plan_its_drum_and_its_cut(
        tmp_path, monkeypatch):
    """Review Focus 2's record (the engine C3 plan's; its Task 6 pins the scheduler's part). A
    trainer presses *back one* into a sequence-balanced block that played out, holds the target's
    horizontal place, switches drumming on in the reopened block and off again, and lets its time
    limit cut its second cycle. Each opening's end records its own plan, the reopened one drawn
    anew from its occurrence (the plan's Appendix B, item 7), and what varied in that opening
    alone; drummed tries carry the place they show again and never move the plan; the place a
    break lost is the one shortfall, `designed`; the places the time cut are on the block's
    `planned` and in no shortfall, `time` included (the controller's ruling on the plan's Task 3).
    Each trial lasts a second and its 0.5 s ITI, so the block's 31 s let the first opening's 20
    trials, two cycles of ten, play out and cut the second, slowed by four drummed tries, after 21
    lines."""
    _scripted(monkeypatch, [Outcome.CORRECT] * 24 + [Outcome.WRONG_TARGET] * 4
              + [Outcome.CORRECT, Outcome.FIXATION_BREAK] + [Outcome.CORRECT] * 20)
    path = _sessions.varied_task(tmp_path, plans=(
        '{"p": Plan([Block("seq", [Condition("a", {}, target=6), Condition("b", {}, target=6), '
        'Condition("c", {}, target=6)], order=SequenceBalanced(cycles=2), time_limit_s=31.0), '
        'Block("after", [Condition("z", {}, target=1)])])}'))
    link = Simulated()

    def world(trial, values, index):
        if index == 20:
            link.queue(BackBlock(by=JAKE))
            link.queue(SetParameter(name="target_x", value=-10.0, by=JAKE))
        if index == 23:
            link.queue(Drum(scope="block", by=JAKE))
        if index == 28:
            link.queue(Drum(scope="off", by=JAKE))
        return _right(values)

    session = _session(_spec(tmp_path, path, plan="p"), link, world=world)

    session.run()

    assert session.refusals == []
    first = list(balanced_sequence(["a", "b", "c"], 2, 2, random.Random(f"design:{SEED}:0")))
    reopened = list(balanced_sequence(["a", "b", "c"], 2, 2, random.Random(f"design:{SEED}:2")))
    assert reopened != first
    end = _end(session)
    assert [(block["block"], block["ended"], block["planned"], block["varied"])
            for block in end["block_ends"]] == [
        ("seq", "rule", first, {}), ("after", "back", None, {}),
        ("seq", "time", reopened, {"target_x": [PERSON]}),
        ("after", "rule", None, {"target_x": [PERSON]})]
    lines = _lines(session)
    def place_of(place: int) -> dict:
        return {"cycle": place // 10, "position": place % 10, "lead_in": place % 10 == 0}

    assert [(line["condition"], line["planned"]) for line in lines[:20]] == [
        (name, place_of(place)) for place, name in enumerate(first)]
    places = [0, 1, 2, 3, 3, 3, 3, 3, 4, *range(5, 17)]
    assert [(line["condition"], line["planned"], line["drummed"]) for line in lines[21:42]] == [
        (reopened[place], place_of(place), 25 <= index <= 28)
        for index, place in enumerate(places, start=21)]
    assert end["shortfalls"] == [{
        "block": "seq", "condition": reopened[4], "trials": 1, "because": "designed",
        "possible_avoidance": False, "after_trial": 29, "by": None}]
    assert len(lines) == 43
