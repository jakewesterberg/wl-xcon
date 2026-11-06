"""Eased trials kept out of moving up (engine build C3's spec §7).

The PI: with the C2b merge, Q8, "Merge; fix eased trials in C3" -- a trial a person's change made
easier does not count toward moving up (a training stage's pass rule, or the criterion that ends a
block) and does count toward moving back (a plan's fall-back rule); and in C3's brainstorm, on a
change to an expected setting, "No, after any change". Between trials, before each trial runs,
`Session._eased` reads each setting a live change reaches on it -- one a person holds, one drawn
from a range changed live -- by its declared meaning (TRN-03), against what the trial would
otherwise have had: its condition's value, the run's own, or for a drawn setting the value the
seed draws for that trial from the range as written. The loop names the settings on the trial's
line (`eased`) and hands the verdict to `Scheduler.record`, which leaves the trial out of its
block's rule and, in a training progression, out of its stage's number of trials and targets (the
engine C3 plan's review, I-7, and its Appendix B, item 10).
"""

from __future__ import annotations

import json
from pathlib import Path

import _sessions
from _rig import DIRECT
from wl_xcon import variation
from wl_xcon.actor import Box
from wl_xcon.cli import _load_task
from wl_xcon.dio import Simulated as Card
from wl_xcon.link import (
    Drum, HandBack, NextBlock, Revert, SetParameter, SetRange, Simulated, Stop,
)
from wl_xcon.photometry import SRGB
from wl_xcon.run import Scripted
from wl_xcon.task import FRESH, SAME, Block, Condition, Listed, SaccadeTo, Uniform
from wl_xcon.taskd import RunSpec, Session, SessionSpec
from wl_xcon.welfare import Deployment, Simulated as Pump

#: The wall every session here reads from, plus its frames' seconds (`_session`).
WALL_NOW = 1_700_000_000.0
SEED = 7
JAKE = Box("jake")
TASK = Path("tasks/fixation_detection.py")
#: A trial the animal breaks: it looks away from the fixation point at its sixth frame, before
#: any hold here is done, a fixation break.
BREAK = Scripted({}, inside={frame: "fix" for frame in range(1, 6)})


def _right(values: dict) -> Scripted:
    """A trial the animal gets right, whatever its holds: it holds the fixation point 20 frames
    past its hold, then looks at the target and stays on it."""
    held = round(values["fix_hold"] * 240) + 20
    return Scripted({SaccadeTo("target"): held + 10},
                    inside={frame: "fix" if frame <= held else "target"
                            for frame in range(1, held + 400)})


def _missed(values: dict) -> Scripted:
    """A trial the animal misses: it holds the fixation point past its hold and stays there, never
    looking at the target, until the response deadline ends the trial -- no response, a miss,
    which the reference task counts as an answer."""
    held = round(values["fix_hold"] * 240) + 20
    return Scripted({}, inside={frame: "fix" for frame in range(1, held + 400)})


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


def _session(spec, link=None, world=_always_right) -> Session:
    """On the simulators, its wall following its frames from `WALL_NOW`, the animal out of its
    cage and its head fixed then, and `world` giving each trial."""
    session = Session(spec, card=Card(), pump=Pump(),
                      link=link if link is not None else Simulated())
    session.wall_clock = lambda: WALL_NOW + session.now()
    session.left_cage(at=WALL_NOW)
    session.head_fixed(at=session.wall_now())
    session.world = world
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


def _rows(session: Session, name: str) -> list[dict]:
    return [json.loads(line) for line in (session.directory / name).read_text().splitlines()]


def _lines(session: Session) -> list[dict]:
    return _rows(session, "trials.jsonl")


def _end(session: Session) -> dict:
    return next(row for row in _rows(session, "runs.jsonl") if row["event"] == "end")


def _told(session: Session) -> list[str]:
    """The changes feed's warnings that a live change keeps a trial out of moving up."""
    return [said for kind, _, _, said in session.controls
            if kind == "warning" and "kept out of moving up" in said]


def _first_eased(lines: list[dict]) -> list[int]:
    """The index of each block's first eased trial, block by block as the run played them."""
    firsts, open_block, found = [], None, False
    for line in lines:
        if line["block"] != open_block:
            open_block, found = line["block"], False
        if line["eased"] and not found:
            firsts.append(line["index"])
            found = True
    return firsts


def _meant(folder: Path, *, meanings: str = "", edits: tuple = (), draws: str = "{}") -> Path:
    """`varied_task` drawing `draws`, with each `(old, new)` of `edits` made in its text and
    `meanings` (Python source for the entries of a dict) declared as its own meanings. Engine test
    material, run only in the simulator."""
    path = _sessions.varied_task(folder, name="eased", draws=draws)
    text = path.read_text()
    for old, new in edits:
        assert text.count(old) == 1, old
        text = text.replace(old, new)
    if meanings:
        text += ("from wl_xcon.task import (\n"
                 "    BACKGROUND, CLEAR_CUT, CRITERION, EASIER, EXPECTED, STIMULUS, Meaning,\n"
                 ")\n"
                 f"TASK = _dataclasses.replace(TASK, meanings={{{meanings}}})\n")
    path.write_text(text)
    return path


def test_a_clear_cut_setting_made_easier_keeps_a_trial_out_of_its_blocks_rule_and_harder_does_not(
        tmp_path):
    """A fixation window wider than the trial would otherwise have had eases it (`fix_window`,
    clear-cut, raising easier): its trials are left out of the window the block's criterion
    reads, so three right in a row takes three right trials no one eased; a window narrower does
    not ease it, and its trial counts. Each line names what kept it out (`eased`), and every trial
    still counts toward its condition (TSK-19)."""
    link = _Drained({2: [SetParameter(name="fix_window", value=3.0, by=JAKE)],
                     5: [SetParameter(name="fix_window", value=1.0, by=JAKE)]})
    session = _session(_spec(tmp_path, TASK, blocks=[
        Block("b", [Condition("c", {}, target=1)], criterion=(1.0, 3))]), link)

    session.run()

    assert session.refusals == []
    assert [(line["params"]["fix_window"], line["eased"]) for line in _lines(session)] == [
        (2.0, []), (2.0, []), (3.0, ["fix_window"]), (3.0, ["fix_window"]),
        (3.0, ["fix_window"]), (1.0, [])]
    end = _end(session)
    assert [(ended["block"], ended["ended"], ended["after_trial"])
            for ended in end["block_ends"]] == [("b", "rule", 5)]
    (report,) = end["conditions"]
    assert (report["trials"], report["right"]) == (6, 6)


def test_an_expected_setting_held_anywhere_but_the_trials_own_value_keeps_it_out(tmp_path):
    """The PI, "No, after any change": an expected setting a person holds at any value but the one
    the trial would otherwise have had keeps it out, either way. Here the task reads its target
    window as expected easier (as the search tasks' `object_window` is), and its condition gives
    it 4°: held at 3°, narrower, which a clear-cut reading would call harder, the trial is kept
    out; held at the condition's own 4°, it is not, though a person still holds it (`live`); held
    at 5°, it is again. Where no condition gives the setting, the trial's own value is the run's:
    the fixation point held at the run's 40 cd/m² keeps nothing out, at 50 it does."""
    path = _meant(tmp_path, meanings=(
        "'target_window': Meaning(EXPECTED, CRITERION, raising=EASIER, "
        "note='a wider window accepts a less accurate landing', "
        "overrides='read as the search tasks read their object window')"))
    link = _Drained({2: [SetParameter(name="target_window", value=3.0, by=JAKE)],
                     4: [SetParameter(name="target_window", value=4.0, by=JAKE)],
                     6: [SetParameter(name="target_window", value=5.0, by=JAKE),
                         SetParameter(name="fix_luminance", value=40.0, by=JAKE)],
                     8: [SetParameter(name="fix_luminance", value=50.0, by=JAKE)]})
    session = _session(_spec(tmp_path, path, blocks=[
        Block("b", [Condition("c", {"target_window": 4.0}, target=10)])]), link)

    session.run()

    assert session.refusals == []
    window, both = ["target_window"], ["fix_luminance", "target_window"]
    assert [(line["live"], line["eased"]) for line in _lines(session)] == (
        [([], [])] * 2 + [(window, window)] * 2 + [(window, [])] * 2 + [(both, window)] * 2
        + [(both, both)] * 2)


def test_a_setting_that_is_no_difficulty_never_keeps_a_trial_out(tmp_path):
    """A setting declared not a difficulty setting never keeps a trial out, whatever a person sets
    it to (the C3 spec §7): the target's place and its appearance (TRN-10). Held beside a fixation
    window widened, only the window is named; once the window is handed back, the trial with
    the other two still held counts toward the block's rule as any other, the third right in a
    row it reads."""
    square = next(p for p in _load_task(TASK).params if p.name == "target_appearance").choices[1]
    link = _Drained({2: [SetParameter(name="target_x", value=-12.0, by=JAKE),
                         SetParameter(name="target_appearance", value=square, by=JAKE),
                         SetParameter(name="fix_window", value=3.0, by=JAKE)],
                     4: [HandBack(name="fix_window", by=JAKE)]})
    session = _session(_spec(tmp_path, TASK, blocks=[
        Block("b", [Condition("c", {}, target=1)], criterion=(1.0, 3))]), link)

    session.run()

    assert session.refusals == []
    held = ["target_appearance", "target_x"]
    assert [(line["live"], line["eased"]) for line in _lines(session)] == [
        ([], []), ([], []), (["fix_window", *held], ["fix_window"]),
        (["fix_window", *held], ["fix_window"]), (held, [])]
    assert [(ended["ended"], ended["after_trial"]) for ended in _end(session)["block_ends"]] == [
        ("rule", 4)]


def test_a_changed_choice_is_read_by_its_raising(tmp_path):
    """A setting whose values are its choices has no order (TRN-11: a task's own meaning for one
    "reads on changing it"), so a change to it is read by its `raising` alone, whichever way the
    numbers moved (the engine C3 plan's review, M-19; `variation.easier`'s `choices`). The
    fixation window's choices raise easier: the person's 1°, narrower than the trial's 2°, still
    eases it. The fixation hold's raise harder: the person's 0.2 s, shorter than the trial's
    0.3 s, does not."""
    path = _meant(tmp_path, edits=(
        ('        Param("fix_hold", unit="s", low=0.05, high=2.0, start=0.3),',
         '        Param("fix_hold", unit="s", choices=(0.2, 0.3, 0.4), start=0.3),'),
        ('        Param("fix_window", unit="deg", low=0.5, high=5.0, start=2.0),',
         '        Param("fix_window", unit="deg", choices=(1.0, 2.0, 3.0), start=2.0),')))
    link = _Drained({2: [SetParameter(name="fix_window", value=1.0, by=JAKE)],
                     4: [HandBack(name="fix_window", by=JAKE),
                         SetParameter(name="fix_hold", value=0.2, by=JAKE)]})
    session = _session(_spec(tmp_path, path, trials=6), link)

    session.run()

    assert session.refusals == []
    assert [(line["live"], line["eased"]) for line in _lines(session)] == (
        [([], [])] * 2 + [(["fix_window"], ["fix_window"])] * 2 + [(["fix_hold"], [])] * 2)


def test_a_live_range_that_reaches_anything_easier_keeps_every_trial_out_until_put_back(tmp_path):
    """The PI, 2026-10-31, on the engine C3 plan's Appendix B, item 18, "Judge the range as a whole
    (Recommended)": a range changed live is judged as a whole against the range the task writes,
    never trial by trial; if it reaches any value easier than the written range allows -- for a
    uniform, either end moved the easier way, a mixed change counted so -- none of its trials count
    toward moving up until it is put back, by its written numbers sent again or by a revert. The
    task draws the fixation window, wider easier, from 1.5° to 2.5°. Widened to 1° to 3°, both
    ways, every trial is kept out, though some draw narrower windows than the written range would
    have; lowered to 0.5° to 1°, harder at both ends, none is; sent back as 1.5° to 2.5°, none;
    narrowed to 2° to 2.5°, toward the easy end, every trial again; reverted to the run's start,
    drawn as declared, none. Each range's row says which way it went."""
    path = _sessions.varied_task(
        tmp_path, draws='{"fix_window": Uniform(1.5, 2.5, repeat=FRESH)}')
    declared, key = _load_task(path).draws["fix_window"], ("task", "fix_window")
    wider = Uniform(1.0, 3.0, repeat=FRESH)
    link = _Drained({
        2: [SetRange(name="fix_window", numbers={"low": 1.0, "high": 3.0}, by=JAKE)],
        5: [SetRange(name="fix_window", numbers={"low": 0.5, "high": 1.0}, by=JAKE)],
        8: [SetRange(name="fix_window", numbers={"low": 1.5, "high": 2.5}, by=JAKE)],
        11: [SetRange(name="fix_window", numbers={"low": 2.0, "high": 2.5}, by=JAKE)],
        14: [Revert(change=0, by=JAKE)]})
    session = _session(_spec(tmp_path, path, trials=17), link)

    session.run()

    assert session.refusals == []
    lines = _lines(session)
    assert [line["drawn"] for line in lines] == (
        [{"fix_window": "task"}] * 2 + [{"fix_window": change} for change in (1, 2, 3, 4)
                                        for _ in range(3)] + [{"fix_window": "task"}] * 3)
    narrower = [number for number in range(2, 5) if variation.draw(wider, SEED, number, key)
                < variation.draw(declared, SEED, number, key)]
    assert narrower, "a trial the widened range drew narrower than the written one would have"
    out = ["fix_window"]
    assert [line["eased"] for line in lines] == (
        [[]] * 2 + [out] * 3 + [[]] * 3 + [[]] * 3 + [out] * 3 + [[]] * 3)
    ranges = [row for row in _rows(session, "parameter_changes.jsonl")
              if row["kind"] in ("range", "revert")]
    assert [(row["change"], row["kind"], row["meaning"]["went"]) for row in ranges] == [
        (1, "range", "easier"), (2, "range", "harder"), (3, "range", None),
        (4, "range", "easier"), (5, "revert", None)]


def test_a_live_range_of_an_expected_setting_or_one_whose_way_cannot_be_read_keeps_its_trials_out(
        tmp_path):
    """The PI's answer of 2026-10-31 (Appendix B, item 18) with his rules before it: a range
    changed live of an expected setting keeps its trials out whichever way it moved ("No, after
    any change"); one whose way cannot be read keeps them out on doubt (Appendix B item 2). The
    target window, read here as expected easier, is drawn from 3.5° to 4.5° and lowered to 3° to
    4.5°, which a clear-cut reading would call harder; the fixation point's luminance, read
    relative to the background, is drawn from 30 to 50 cd/m² and raised to 31 to 50."""
    path = _meant(tmp_path, meanings=(
        "'target_window': Meaning(EXPECTED, CRITERION, raising=EASIER, "
        "note='a wider window accepts a less accurate landing', "
        "overrides='read as the search tasks read their object window'), "
        "'fix_luminance': Meaning(CLEAR_CUT, STIMULUS, raising=EASIER, relative_to=BACKGROUND, "
        "note='a point farther from the background is easier to find', "
        "overrides='read as clear-cut here')"),
        draws=('{"target_window": Uniform(3.5, 4.5, repeat=FRESH), '
               '"fix_luminance": Uniform(30.0, 50.0, repeat=FRESH)}'))
    link = _Drained({2: [SetRange(name="target_window", numbers={"low": 3.0}, by=JAKE)],
                     4: [SetRange(name="fix_luminance", numbers={"low": 31.0}, by=JAKE)]})
    session = _session(_spec(tmp_path, path, trials=6), link)

    session.run()

    assert session.refusals == []
    assert [line["eased"] for line in _lines(session)] == (
        [[]] * 2 + [["target_window"]] * 2 + [["fix_luminance", "target_window"]] * 2)


def test_a_value_held_over_a_range_changed_live_is_judged_against_the_range_as_written(tmp_path):
    """A person's value over a draw is judged against what the seed draws for that trial from the
    range as written (the C3 spec §7), never from a range changed live. The fixation window is
    drawn from 1.5° to 2.5° and lowered live to 1° to 1.4°, harder, so its trials count; a person
    then holds 1.45°, wider than any the lowered range draws and narrower than any the written one
    does: harder than the trial would otherwise have had, so its trials count too; then 2.6°, wider
    than any the written range draws, which keeps them out."""
    path = _sessions.varied_task(
        tmp_path, draws='{"fix_window": Uniform(1.5, 2.5, repeat=FRESH)}')
    link = _Drained({2: [SetRange(name="fix_window", numbers={"low": 1.0, "high": 1.4}, by=JAKE)],
                     4: [SetParameter(name="fix_window", value=1.45, by=JAKE)],
                     6: [SetParameter(name="fix_window", value=2.6, by=JAKE)]})
    session = _session(_spec(tmp_path, path, trials=8), link)

    session.run()

    assert session.refusals == []
    assert [(line["drawn"], line["live"], line["eased"]) for line in _lines(session)] == (
        [({"fix_window": "task"}, [], [])] * 2 + [({"fix_window": 1}, [], [])] * 2
        + [({}, ["fix_window"], [])] * 2 + [({}, ["fix_window"], ["fix_window"])] * 2)


def test_a_value_held_over_a_draw_is_judged_against_what_the_draw_gives_that_trial(tmp_path):
    """Where a draw gives the setting -- here its condition's own range, 1.5° to 2.5° (the PI,
    Q1b) -- the trial would otherwise have had the value the seed draws for it from that range
    (the C3 spec §7: "the keyed generator makes it computable"), not the run's 2°: a person holding
    the fixation window at 2° eases exactly the trials whose own draw would have been narrower."""
    path = _sessions.varied_task(tmp_path)
    own, key = Uniform(1.5, 2.5, repeat=FRESH), ("condition", "c", "fix_window")
    link = _Drained({2: [SetParameter(name="fix_window", value=2.0, by=JAKE)]})
    session = _session(_spec(tmp_path, path, blocks=[
        Block("b", [Condition("c", {"fix_window": own}, target=12)])]), link)

    session.run()

    assert session.refusals == []
    lines = _lines(session)
    held = [["fix_window"] if 2.0 > variation.draw(own, SEED, number, key) else []
            for number in range(2, 12)]
    assert [] in held and ["fix_window"] in held, "some draws narrower, some wider"
    assert [line["eased"] for line in lines] == [[]] * 2 + held
    assert [(line["live"], line["overridden"]) for line in lines[2:]] == [
        (["fix_window"], ["fix_window"])] * 10


def test_a_same_repeat_is_judged_by_the_range_that_drew_the_value_it_keeps(tmp_path):
    """The engine C3 plan's call 13 and the PI's answer of 2026-10-31 (Appendix B, item 18): a
    `SAME` setting's repeat takes the value, and the source, of the trial it shows again, so it is
    judged by the range that drew that value, named by its change, never by the range in force
    when it is shown again. A trial drawn from a widened range breaks under drumming; the range is
    then sent back as written, and the drum's try, keeping the widened range's window, is still
    kept out, while the next fresh trial, drawn from the range sent back, counts."""
    path = _sessions.varied_task(
        tmp_path, draws='{"fix_window": Uniform(1.5, 2.5, repeat=SAME)}')

    def world(trial, values, index):
        return BREAK if index == 3 else _right(values)

    link = _Drained({1: [Drum(scope="run", by=JAKE)],
                     2: [SetRange(name="fix_window", numbers={"low": 1.0, "high": 3.0},
                                  by=JAKE)],
                     4: [SetRange(name="fix_window", numbers={"low": 1.5, "high": 2.5},
                                  by=JAKE)]})
    session = _session(_spec(tmp_path, path, trials=6), link, world=world)

    session.run()

    assert session.refusals == []
    lines = _lines(session)
    # The drum switch took change 1 (a `drum` row), so the ranges are changes 2 and 3.
    out = ["fix_window"]
    assert [(line["drawn"], line["repeat_of"], line["eased"]) for line in lines] == [
        ({"fix_window": "task"}, None, []), ({"fix_window": "task"}, None, []),
        ({"fix_window": 2}, None, out), ({"fix_window": 2}, None, out),
        ({"fix_window": 2}, 3, out), ({"fix_window": 3}, None, []), ({"fix_window": 3}, None, [])]
    assert lines[4]["drummed"] and lines[4]["params"] == lines[3]["params"]


def test_a_value_held_on_a_same_repeat_is_judged_against_the_value_the_trial_it_repeats_drew(
        tmp_path):
    """A person's value over a `SAME` setting on a repeat: had no one held it, the repeat would
    have taken the value the trial it shows again drew (the engine C3 plan's call 13), so that is
    what the hold is judged against, never the draw on the repeat's own number. The fourth trial
    breaks under drumming, and from its drum's try a person holds the fixation window halfway
    between its draw and the one the try's own number would draw."""
    path = _sessions.varied_task(
        tmp_path, draws='{"fix_window": Uniform(1.5, 2.5, repeat=SAME)}')
    declared, key = _load_task(path).draws["fix_window"], ("task", "fix_window")
    drew, own = variation.draw(declared, SEED, 3, key), variation.draw(declared, SEED, 4, key)
    held = (drew + own) / 2

    def world(trial, values, index):
        return BREAK if index == 3 else _right(values)

    link = _Drained({1: [Drum(scope="run", by=JAKE)],
                     4: [SetParameter(name="fix_window", value=held, by=JAKE)]})
    session = _session(_spec(tmp_path, path, trials=5), link, world=world)

    session.run()

    assert session.refusals == []
    again = _lines(session)[4]
    assert (again["drummed"], again["repeat_of"], again["live"]) == (True, 3, ["fix_window"])
    assert again["eased"] == (["fix_window"] if held > drew else [])
    assert (held > drew) != (held > own), "the try's own draw would say otherwise"


def test_a_value_held_on_a_repeat_of_a_trial_a_live_range_drew_is_judged_against_the_range_written(
        tmp_path):
    """A person's value over a `SAME` setting on a repeat whose original drew it from a range
    changed live: had no one held it, the repeat would have kept a value the written range never
    gave, so the hold is judged, as every held value over a draw is, against the value the seed
    draws from the range as written, for the trial the repeat shows again (`_kept`'s `original`),
    never for the repeat's own number (the engine C3 plan's calls 13 and 18; revision round 2). The
    fourth trial, drawn from a range widened live, breaks under drumming, and from its drum's try
    a person holds the fixation window halfway between the written range's draws for the two
    numbers."""
    path = _sessions.varied_task(
        tmp_path, draws='{"fix_window": Uniform(1.5, 2.5, repeat=SAME)}')
    declared, key = _load_task(path).draws["fix_window"], ("task", "fix_window")
    drew, own = variation.draw(declared, SEED, 3, key), variation.draw(declared, SEED, 4, key)
    held = (drew + own) / 2

    def world(trial, values, index):
        return BREAK if index == 3 else _right(values)

    link = _Drained({1: [Drum(scope="run", by=JAKE)],
                     2: [SetRange(name="fix_window", numbers={"low": 1.0, "high": 3.0},
                                  by=JAKE)],
                     4: [SetParameter(name="fix_window", value=held, by=JAKE)]})
    session = _session(_spec(tmp_path, path, trials=5), link, world=world)

    session.run()

    assert session.refusals == []
    first, again = _lines(session)[3:5]
    assert first["drawn"] == {"fix_window": 2}
    assert (again["drummed"], again["repeat_of"], again["live"]) == (True, 3, ["fix_window"])
    assert again["eased"] == (["fix_window"] if held > drew else [])
    assert (held > drew) != (held > own), "the try's own number would say otherwise"


def test_a_prepared_list_held_is_judged_against_the_item_the_trial_would_have_taken(tmp_path):
    """A prepared list a person holds does not move on (a held setting is not drawn; the engine
    C3 plan's call 7), so the trial would otherwise have had, on a `SAME` repeat, the item the
    trial it shows again drew, and else the item the list's next fresh draw takes -- which the
    trial after the hand-back then draws. The fixation window is drawn from four widths in
    shuffled passes, the seed's first pass 3°, 4°, 1°; the second trial (4°) breaks under
    drumming, and a person holds 2.5° from its drum's try for two trials: narrower than the 4° the
    try would have repeated, not eased; wider than the 1° the next fresh draw takes, eased."""
    path = _sessions.varied_task(
        tmp_path, draws='{"fix_window": Listed((1.0, 2.0, 3.0, 4.0), repeat=SAME)}')
    declared, key = _load_task(path).draws["fix_window"], ("task", "fix_window")
    order = [variation.draw(declared, SEED, 0, key, ordinal=place) for place in range(3)]
    assert order == [3.0, 4.0, 1.0], "the seed's first pass, as this test reads it"

    def world(trial, values, index):
        return BREAK if index == 1 else _right(values)

    link = _Drained({1: [Drum(scope="run", by=JAKE)],
                     2: [SetParameter(name="fix_window", value=2.5, by=JAKE)],
                     4: [HandBack(name="fix_window", by=JAKE)]})
    session = _session(_spec(tmp_path, path, trials=4), link, world=world)

    session.run()

    assert session.refusals == []
    lines = _lines(session)
    assert [(line["params"]["fix_window"], line["repeat_of"], line["eased"])
            for line in lines] == [
        (3.0, None, []), (4.0, None, []), (2.5, 1, []), (2.5, None, ["fix_window"]),
        (1.0, None, [])]


def test_a_value_staged_under_another_task_keeps_nothing_out(tmp_path):
    """Values a person staged before the run, under the task the session names, apply at the
    run's first boundary and are held (`live`) whatever task the run plays. The search task's
    object window is no setting of the detection task the run plays, and nothing of its trials
    reads it: it keeps nothing out, and judging it never ends the run. The fixation window both
    declare, widened, keeps every trial out."""
    session = _session(_spec(tmp_path, "tasks/visual_search.py"))
    session.set("object_window", 0.8, by=JAKE)
    session.set("fix_window", 3.0, by=JAKE)

    session.run(RunSpec(task=str(TASK), trials=3, seed=SEED,
                        values={"target_appearance": None}))

    assert [(line["live"], line["eased"]) for line in _lines(session)] == [
        (["fix_window", "object_window"], ["fix_window"])] * 3


def test_easing_relative_to_another_setting_and_to_the_background(tmp_path):
    """A meaning relative to another setting reads that setting as the trial has it (TRN-11): the
    task reads its target's luminance as easier the farther from the fixation point's, 40 cd/m²,
    and the run gives it 60. Held at 50, nearer, the trial is not eased; at 75, farther, it is; at
    20, as far, it is not. A meaning relative to the trial's background cannot be read here, so a
    live change keeps the trial out on doubt (the engine C3 plan's Appendix B, item 2): the fixation
    point's luminance, read clear-cut by this task, held at 30 cd/m², which raising-easier would
    call harder. The target's 20 is then judged against the fixation point's 30 as that trial has
    it: nearer than the run's 60, not eased."""
    path = _meant(tmp_path, meanings=(
        "'target_luminance': Meaning(CLEAR_CUT, STIMULUS, raising=EASIER, "
        "relative_to='fix_luminance', note='a target farther from the fixation point in "
        "luminance stands out', overrides='read against the fixation point here'), "
        "'fix_luminance': Meaning(CLEAR_CUT, STIMULUS, raising=EASIER, relative_to=BACKGROUND, "
        "note='a point farther from the background is easier to find', "
        "overrides='read as clear-cut here')"))
    link = _Drained({2: [SetParameter(name="target_luminance", value=50.0, by=JAKE)],
                     3: [SetParameter(name="target_luminance", value=75.0, by=JAKE)],
                     4: [SetParameter(name="target_luminance", value=20.0, by=JAKE)],
                     5: [SetParameter(name="fix_luminance", value=30.0, by=JAKE)]})
    session = _session(_spec(tmp_path, path, trials=6,
                             values={"target_appearance": None, "target_luminance": 60.0}), link)

    session.run()

    assert session.refusals == []
    assert [line["eased"] for line in _lines(session)] == [
        [], [], [], ["target_luminance"], [], ["fix_luminance"]]


def test_eased_trials_count_toward_the_fall_back_and_their_conditions_counts(tmp_path):
    """The PI, Q8: eased trials "do count toward moving back". A training progression's second
    stage gives its condition a fixation window of 1°, which a person holds at 3° from the run's
    second trial (the first stage's own 3°, so its trials are not eased): the second stage's four
    misses are eased, and the plan's fall-back judges each first answer, so the run moves back to
    the first stage. The end row counts every eased trial toward its condition (`conditions`),
    the record of what the animal did, while its stage's target stays owed (the engine C3 plan's
    review, I-7)."""
    path = _sessions.varied_task(tmp_path, plans=(
        '{"p": Plan([Block("S1", [Condition("a", {"fix_window": 3.0}, target=1)], '
        'criterion=(1.0, 2)), Block("S2", [Condition("b", {"fix_window": 1.0}, target=1)], '
        'criterion=(1.0, 2))], order=ByCriterion(fall_back=(0.5, 4)))}'))
    stages = []

    def world(trial, values, index):
        stages.append(session._scheduler.block.name)
        if stages[-1] == "S2":
            return _missed(values)
        if "S2" in stages:
            link.queue(Stop(by=JAKE))
        return _right(values)

    link = _Drained({1: [SetParameter(name="fix_window", value=3.0, by=JAKE)]})
    session = _session(_spec(tmp_path, path, plan="p"), link, world=world)

    session.run()

    assert session.refusals == []
    lines = _lines(session)
    assert [(line["block"], line["outcome"], line["eased"]) for line in lines] == (
        [("S1", "correct", [])] * 2 + [("S2", "no_response", ["fix_window"])] * 4
        + [("S1", "correct", [])])
    end = _end(session)
    assert [(ended["block"], ended["ended"]) for ended in end["block_ends"]] == [
        ("S1", "rule"), ("S2", "fall_back"), ("S1", "run")]
    second = next(report for report in end["conditions"] if report["block"] == "S2")
    assert (second["trials"], second["wrong"], second["owed"]) == (4, 4, 1)


def test_a_training_stage_is_not_passed_on_eased_trials_by_its_trials_or_targets(tmp_path):
    """The engine C3 plan's review, I-7, and its Appendix B, item 10, through the run: a training
    progression's first stage ends when its three trials are run and its target of two met. Its
    fixation window widened from the run's second trial, its eased trials count toward neither,
    so the stage runs on; the person's hand-back makes the trials after it count, and the stage
    ends on the second after it, its trials then three. Its condition's counts keep every trial."""
    path = _sessions.varied_task(tmp_path, plans=(
        '{"p": Plan([Block("S1", [Condition("a", {}, target=2)], trials=3), '
        'Block("S2", [Condition("b", {}, target=1)])], order=ByCriterion())}'))

    def world(trial, values, index):
        if session._scheduler.block.name == "S2":
            link.queue(Stop(by=JAKE))
        return _right(values)

    link = _Drained({1: [SetParameter(name="fix_window", value=3.0, by=JAKE)],
                     5: [HandBack(name="fix_window", by=JAKE)]})
    session = _session(_spec(tmp_path, path, plan="p"), link, world=world)

    session.run()

    assert session.refusals == []
    lines = _lines(session)
    assert [(line["block"], line["eased"]) for line in lines] == (
        [("S1", [])] + [("S1", ["fix_window"])] * 4 + [("S1", [])] * 2 + [("S2", [])])
    end = _end(session)
    assert [(ended["block"], ended["ended"], ended["after_trial"])
            for ended in end["block_ends"]] == [("S1", "rule", 6), ("S2", "run", 7)]
    first = next(report for report in end["conditions"] if report["block"] == "S1")
    assert (first["trials"], first["right"], first["owed"]) == (7, 7, 0)


def test_a_drummed_trial_whose_paying_try_was_eased_does_not_count_toward_a_stages_trials(
        tmp_path):
    """The controller's ruling on Task 15 (2026-10-30): a trial counts as eased toward a stage's
    number of trials when the try that paid it was eased, not only when its first try was, since
    the answer that paid it was made easier and must not move the animal up. A training
    progression's first stage owes no trials (its target 0) and ends when two trials are run.
    Under drumming its first trial breaks, uneased; a person widens the fixation window, and the
    drum's try that pays it is eased. Handed back, the stage takes two more trials no one eased to
    end, the drummed one not among its two."""
    path = _sessions.varied_task(tmp_path, plans=(
        '{"p": Plan([Block("S1", [Condition("a", {}, target=0)], trials=2), '
        'Block("S2", [Condition("b", {}, target=1)])], order=ByCriterion())}'))

    def world(trial, values, index):
        if session._scheduler.block.name == "S2":
            link.queue(Stop(by=JAKE))
        return BREAK if index == 0 else _right(values)

    link = _Drained({1: [Drum(scope="run", by=JAKE),
                         SetParameter(name="fix_window", value=3.0, by=JAKE)],
                     2: [HandBack(name="fix_window", by=JAKE)]})
    session = _session(_spec(tmp_path, path, plan="p"), link, world=world)

    session.run()

    assert session.refusals == []
    lines = _lines(session)
    assert [(line["block"], line["drummed"], line["outcome"], line["eased"])
            for line in lines] == [
        ("S1", False, "fixation_break", []), ("S1", True, "correct", ["fix_window"]),
        ("S1", False, "correct", []), ("S1", False, "correct", []), ("S2", False, "correct", [])]
    end = _end(session)
    assert [(ended["block"], ended["ended"], ended["after_trial"])
            for ended in end["block_ends"]] == [("S1", "rule", 3), ("S2", "run", 4)]
    first = next(report for report in end["conditions"] if report["block"] == "S1")
    assert (first["trials"], first["presentations"]) == (3, 4)


def test_a_hand_back_ends_the_easing_from_the_next_trial(tmp_path):
    """A hand-back ends a person's hold, and with it the easing, from the next trial (the C3 spec
    §7). The task draws the fixation window from 1.5° to 2.5°, and a person holds it at 3°, wider
    than any it draws: those two trials are eased, left out of the block's rule. Handed back to
    its draw, it is drawn as declared again, no live change, and the trial after the hand-back
    is the third right in a row the rule counts."""
    path = _sessions.varied_task(
        tmp_path, draws='{"fix_window": Uniform(1.5, 2.5, repeat=FRESH)}')
    link = _Drained({2: [SetParameter(name="fix_window", value=3.0, by=JAKE)],
                     4: [HandBack(name="fix_window", by=JAKE)]})
    session = _session(_spec(tmp_path, path, blocks=[
        Block("b", [Condition("c", {}, target=1)], criterion=(1.0, 3))]), link)

    session.run()

    assert session.refusals == []
    assert [(line["drawn"], line["eased"]) for line in _lines(session)] == (
        [({"fix_window": "task"}, [])] * 2 + [({}, ["fix_window"])] * 2
        + [({"fix_window": "task"}, [])])
    assert [(ended["ended"], ended["after_trial"]) for ended in _end(session)["block_ends"]] == [
        ("rule", 4)]


def test_the_changes_feed_says_once_a_block_which_live_change_keeps_its_trials_out_of_moving_up(
        tmp_path):
    """The C3 plan's engineering review, I-2, and its science review, I-4: a trainer who widens
    the fixation window in a block that ends on a criterion sees a perfect streak and a block that
    will not end. The changes feed says why, a warning, the first time in a block a trial is kept
    out for a setting: the trial, the setting and the way back, *hand back* for a value a person
    holds -- and not again in that block however many trials follow. The next block, eased again,
    is told again. A run with no rule that moves the animal on is told nothing: its trials' lines
    still say `eased`."""
    path = _sessions.varied_task(tmp_path, plans=(
        '{"p": Plan([Block("crit", [Condition("c", {}, target=1)], criterion=(1.0, 3)), '
        'Block("next", [Condition("n", {}, target=1)], criterion=(1.0, 3))])}'))
    link = _Drained({2: [SetParameter(name="fix_window", value=3.0, by=JAKE)],
                     6: [NextBlock(by=JAKE)], 10: [Stop(by=JAKE)]})
    session = _session(_spec(tmp_path, path, plan="p"), link)

    session.run()

    assert session.refusals == []
    lines = _lines(session)
    for block in ("crit", "next"):
        assert sum(1 for line in lines if line["block"] == block and line["eased"]) >= 2, block
    assert _first_eased(lines) == [2, 5]
    assert _told(session) == [
        f"trial {index} is kept out of moving up: a live change eased fix_window; hand "
        f"fix_window back, to count trials toward moving up again" for index in (2, 5)]

    plain = _session(_spec(tmp_path / "plain", TASK, trials=6), _Drained(
        {2: [SetParameter(name="fix_window", value=3.0, by=JAKE)]}))
    plain.run()
    assert [line["eased"] for line in _lines(plain)][2:] == [["fix_window"]] * 4
    assert _told(plain) == []


def test_a_range_changed_live_is_told_its_way_back_and_a_training_stage_is_told_too(tmp_path):
    """The C3 plan's engineering review, I-2: a training progression's stage ends on its trials
    and targets, which leave eased trials out, so a stage is told as a block with a criterion is.
    A drawn setting whose range a person changed live is told the way back from a range: send the
    range as the task writes it, or revert the change."""
    path = _sessions.varied_task(
        tmp_path, draws='{"fix_window": Uniform(1.5, 2.5, repeat=FRESH)}', plans=(
            '{"p": Plan([Block("S1", [Condition("a", {}, target=2)], trials=3), '
            'Block("S2", [Condition("b", {}, target=1)])], order=ByCriterion())}'))
    link = _Drained({2: [SetRange(name="fix_window", numbers={"low": 1.0, "high": 3.0}, by=JAKE)],
                     14: [Stop(by=JAKE)]})
    session = _session(_spec(tmp_path, path, plan="p"), link)

    session.run()

    assert session.refusals == []
    # The widened range reaches a wider window than written: every trial drawn from it is kept
    # out, so the stage, ending on its trials, runs on until the stop (the PI, 2026-10-31).
    assert _first_eased(_lines(session)) == [2]
    assert _told(session) == [
        "trial 2 is kept out of moving up: a live change eased fix_window; send fix_window's range "
        "as the task writes it or revert that change, to count trials toward moving up again"]


def test_a_value_held_on_a_fresh_repeat_is_judged_against_the_repeats_own_draw(tmp_path):
    """Task 15 fix round 1 (the review's Important 1; the PI's rule, never move an animal up on
    eased trials): a `FRESH` setting a person holds on a repeat would, had no one held it, have
    been drawn on the repeat's own number, not taken from the trial it shows again, so that is
    what the hold is judged against. The fourth trial breaks under drumming, and from its drum's
    try a person holds the fixation window halfway between the written range's draws for the two
    numbers."""
    path = _sessions.varied_task(
        tmp_path, draws='{"fix_window": Uniform(1.5, 2.5, repeat=FRESH)}')
    declared, key = _load_task(path).draws["fix_window"], ("task", "fix_window")
    # A trial whose draw is wider than its drum's try's own, so a hold between them is wider than
    # the try's own draw (eased) and narrower than the original's (which would not call it so).
    broke = next(number for number in range(2, 12)
                 if variation.draw(declared, SEED, number, key)
                 > variation.draw(declared, SEED, number + 1, key))
    drew = variation.draw(declared, SEED, broke, key)
    own = variation.draw(declared, SEED, broke + 1, key)
    held = (drew + own) / 2

    def world(trial, values, index):
        return BREAK if index == broke else _right(values)

    link = _Drained({1: [Drum(scope="run", by=JAKE)],
                     broke + 1: [SetParameter(name="fix_window", value=held, by=JAKE)]})
    session = _session(_spec(tmp_path, path, trials=broke + 2), link, world=world)

    session.run()

    assert session.refusals == []
    again = _lines(session)[broke + 1]
    assert (again["drummed"], again["repeat_of"], again["live"]) == (
        True, broke, ["fix_window"])
    assert again["eased"] == ["fix_window"]

def test_a_range_lowered_live_and_put_back_still_counts_a_same_repeat_of_its_trial(tmp_path):
    """Task 15 fix round 1 (the review's Minor 2): a trial drawn from a range lowered live (harder
    at both ends) counts toward moving up, and so does its drum's try after the range is sent back
    as written, since that try is judged by the range that drew the value it keeps, found through
    the moment of its change (`_moments`), where a lookup that failed would read as doubt and keep
    it out."""
    path = _sessions.varied_task(
        tmp_path, draws='{"fix_window": Uniform(1.5, 2.5, repeat=SAME)}')

    def world(trial, values, index):
        return BREAK if index == 3 else _right(values)

    link = _Drained({1: [Drum(scope="run", by=JAKE)],
                     2: [SetRange(name="fix_window", numbers={"low": 1.0, "high": 1.4},
                                  by=JAKE)],
                     4: [SetRange(name="fix_window", numbers={"low": 1.5, "high": 2.5},
                                  by=JAKE)]})
    session = _session(_spec(tmp_path, path, trials=6), link, world=world)

    session.run()

    assert session.refusals == []
    lines = _lines(session)
    assert [(line["drawn"], line["repeat_of"], line["eased"]) for line in lines] == [
        ({"fix_window": "task"}, None, []), ({"fix_window": "task"}, None, []),
        ({"fix_window": 2}, None, []), ({"fix_window": 2}, None, []),
        ({"fix_window": 2}, 3, []), ({"fix_window": 3}, None, []),
        ({"fix_window": 3}, None, [])]


def test_an_expected_range_typed_back_to_its_written_numbers_counts_as_put_back(tmp_path):
    """Task 15 fix round 1 (the review's Minor 1 and 3; the PI's item 18 names typing the written
    numbers again as a way to put a range back): an expected setting's range is compared by the
    numbers that place its draws, as the change row's `went` is, not as objects. The target window,
    read as expected, is drawn as a normal about 4° with no written cut (its setting's own
    stands in); its cut is lowered live, which keeps its trials out ("No, after any change"), and
    sent back as the setting's own cut, which counts them again, its row saying `went: null`."""
    path = _meant(tmp_path, meanings=(
        "'target_window': Meaning(EXPECTED, CRITERION, raising=EASIER, "
        "note='a wider window accepts a less accurate landing', "
        "overrides='read as the search tasks read their object window')"),
        draws='{"target_window": TruncatedNormal(4.0, 0.5, repeat=FRESH)}')
    declared = next(p for p in _load_task(path).params if p.name == "target_window")
    link = _Drained({2: [SetRange(name="target_window", numbers={"low": 3.0}, by=JAKE)],
                     4: [SetRange(name="target_window", numbers={"low": declared.low}, by=JAKE)]})
    session = _session(_spec(tmp_path, path, trials=6), link)

    session.run()

    assert session.refusals == []
    assert [line["eased"] for line in _lines(session)] == (
        [[]] * 2 + [["target_window"]] * 2 + [[]] * 2)
    ranges = [row for row in _rows(session, "parameter_changes.jsonl") if row["kind"] == "range"]
    assert [row["meaning"]["went"] for row in ranges][-1] is None


def test_a_sequence_stage_that_moves_up_on_its_sequence_is_told_so_not_that_its_trials_are_out(
        tmp_path):
    """Task 15 fix round 1 (the review's Important 2; the PI, 2026-10-31, item 10, "Only warn at
    load"): a sequence-balanced stage below a training progression's top moves up when its sequence
    is played out, eased trials or not, so the changes feed tells a trainer what is true -- the
    trial and the setting, that the stage moves up when its sequence is played out, eased trials
    or not, and how to take the change off -- and never that the trials are kept out of moving
    up, which a stage with a criterion is told."""
    for name, stage, said in (
        ("sequence", 'Block("S1", [Condition("a", {}, target=2), Condition("b", {}, target=2)], '
                     'order=SequenceBalanced(depth=2))',
         "trial 1 was eased by a live change to fix_window; this stage moves up when its "
         "sequence is played out, eased trials or not; hand fix_window back, to take the "
         "change off"),
        ("criterion", 'Block("S1", [Condition("a", {}, target=1)], criterion=(1.0, 3))',
         "trial 1 is kept out of moving up: a live change eased fix_window; hand fix_window "
         "back, to count trials toward moving up again")):
        path = _sessions.varied_task(tmp_path / name, plans=(
            '{"p": Plan([' + stage + ', Block("S2", [Condition("c", {}, target=1)])], '
            'order=ByCriterion())}'))
        link = _Drained({1: [SetParameter(name="fix_window", value=3.0, by=JAKE)],
                         3: [Stop(by=JAKE)]})
        session = _session(_spec(tmp_path / name, path, plan="p"), link)

        session.run()

        assert session.refusals == []
        assert _first_eased(_lines(session))[:1] == [1], name
        assert [said_ for kind, _, _, said_ in session.controls if kind == "warning"
                and "eased" in said_ and "fix_window" in said_][:1] == [said], name
