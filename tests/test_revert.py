"""Revert (engine build C3's spec §8 and §14 items 1 and 3).

The PI, 2026-10-07, TSK-43, "Yes, with revert": "any earlier state restored in one action, itself
recorded"; and 2026-10-30, "Approve all four", the C3 spec's welfare items for the design. Item
1: a third branch beside the pause in the welfare-listed `Session._command` hands `link.Revert` to
`Session._revert`, off the list, which never raises. Item 3: revert is on the welfare summary --
it restores task settings and drawn ranges only, never a bounded setting such as a reward size;
each value goes through `Session.set` unchanged, and the revert is refused whole if any value is.
A revert goes back to a moment of the run in progress (`Session._moments`: the run's start, then
one kept after each act) and applies at the next boundary as one act: one change id for all its
rows, kind `revert`, each naming the moment it goes back to.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import _sessions
from _rig import DIRECT
from wl_xcon import taskd, variation
from wl_xcon.actor import Box
from wl_xcon.cli import _load_task
from wl_xcon.dio import Simulated as Card
from wl_xcon.findings import SESSION_KINDS, Finding
from wl_xcon.link import (
    CONTROL_HISTORY, ClearOwed, Drum, HandBack, Pause, Resume, Revert, SetParameter, SetRange,
    Simulated, Stop, Training,
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
ANA = Box("ana")
#: Jake and Ana as a change row writes them.
BY = {"kind": "box", "name": "jake"}
ANA_BY = {"kind": "box", "name": "ana"}
#: `PARAM_CHANGED`'s code in the reference allocation: what each change row here strobes.
PARAM_CHANGED = 4130
#: The reference task's fixation hold's meaning, and its fixation point's luminance's, as a
#: change row writes them.
FIX_HOLD = {"kind": "clear-cut", "role": "criterion", "raising": "harder", "relative_to": None}
FIX_LUMINANCE = {"kind": "expected", "role": "stimulus", "raising": "easier",
                 "relative_to": "background"}
#: The task's draw of the fixation hold, every trial afresh.
DRAWN = '{"fix_hold": Uniform(0.2, 0.4, repeat=FRESH)}'
#: `visual_search`'s values: its target red among green, a ring of six objects 8° out.
SEARCH = _load_task(Path("tasks/visual_search.py"))
((RED, GREEN, _),) = [p.choices for p in SEARCH.params if p.name == "target_appearance"]
SEARCHED = {"fix_acquisition": 4.0, "fix_hold": 0.3, "response_deadline": 0.6,
            "target_hold": 0.2, "fix_window": 2.0, "object_window": 0.5,
            "array_eccentricity": 8.0, "set_size": 6, "target_index": 0,
            "array_rotation": 0.0, "fix_luminance": 40.0,
            "target_appearance": RED, "distractor_appearance": GREEN}


def _near(target: int) -> Block:
    """One block of one condition placing the target 5° out, owing `target` trials."""
    return Block("b", [Condition("near", {"target_x": 5.0}, target=target)])


def _right(values: dict) -> Scripted:
    """A trial the animal gets right, whatever its holds: it holds the fixation point 20 frames
    past its hold, then looks at the target and stays on it 400 frames, past any target hold."""
    held = round(values["fix_hold"] * 240) + 20
    return Scripted({SaccadeTo("target"): held + 10},
                    inside={frame: "fix" if frame <= held else "target"
                            for frame in range(1, held + 400)})


#: A trial the animal breaks: it looks at the fixation point five frames and looks away.
BREAK = Scripted({}, inside={frame: "fix" for frame in range(1, 6)})


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
    cage and its head fixed then; the animal right on every trial unless `world` says otherwise,
    the simulated animal where it is `None`; a `wlx taskd` session, opened, where `service`."""
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
    trial, once each time the plan moves to another block, and once each pass while paused; a
    command drained before trial `n` applies from trial `n + 1`."""

    def __init__(self, script):
        super().__init__()
        self.script, self.drains = dict(script), 0

    def drain(self) -> list:
        self.drains += 1
        for command in self.script.get(self.drains, ()):
            self.queue(command)
        return super().drain()


def _rows(session: Session, name: str) -> list[dict]:
    """The rows of one of the session's files, none where it was never written."""
    path = session.directory / name
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def _lines(session: Session) -> list[dict]:
    return _rows(session, "trials.jsonl")


def _changes(session: Session) -> list[dict]:
    return _rows(session, "parameter_changes.jsonl")


def _reverted(session: Session) -> list[dict]:
    return [row for row in _changes(session) if row["kind"] == "revert"]


def _without_instants(row: dict) -> dict:
    return {key: value for key, value in row.items() if key not in ("at", "at_local")}


def _fed(session: Session, *kinds: str) -> list[tuple]:
    """The changes feed's lines of `kinds`, as `(kind, by, said)`."""
    return [(kind, by, said) for kind, by, _, said in session.controls if kind in kinds]


def _edited(path: Path, *edits: tuple[str, str], tail: str = "") -> Path:
    """`path` with each `(old, new)` made, each `old` found once, and `tail` appended."""
    text = path.read_text()
    for old, new in edits:
        assert text.count(old) == 1, old
        text = text.replace(old, new)
    path.write_text(text + tail)
    return path


def _ceiling(folder: Path) -> Path:
    """`varied_task` declaring a setting named as the reward ceiling is, `reward_correct`, which
    nothing reads, with a meaning, as a task may (as `tests/test_hand_back_and_ranges.py`'s does).
    Engine test material."""
    return _edited(
        _sessions.varied_task(folder, name="ceiling"),
        ('        Param("target_hold", unit="s", low=0.05, high=1.0, start=0.2),',
         '        Param("reward_correct", unit="mL", low=0.0, high=1.0),\n'
         '        Param("target_hold", unit="s", low=0.05, high=1.0, start=0.2),'),
        tail=("from wl_xcon.task import NEITHER, NOT_DIFFICULTY, Meaning\n"
              "TASK = _dataclasses.replace(TASK, meanings={'reward_correct': Meaning(\n"
              "    NOT_DIFFICULTY, NEITHER, note='named as a ceiling is, read by nothing')})\n"))


def _breaks(monkeypatch, refused: tuple[str, float], warned: tuple[str, float] | None = None):
    """**This file's stand-in for a value whose widened checks break the run**, installed from
    the moment it is called: `check.beyond_range`, as `Session._beyond_range` meets it, refuses
    values holding `refused`'s setting at its value with a finding that blocks, and gives values
    holding `warned`'s, where given, a warning of its own, a sentence never accepted before. A
    revert restores what the run held at an earlier moment, which every check passed when it was
    set, so a check of the task refuses one only through something that changed since, as a trial
    waiting to be shown again keeps a value (`test_a_revert_the_waiting_trial_cannot_meet_...`);
    this stand-in is for a value whose widened checks answer otherwise now."""
    real = taskd.beyond_range

    def standing_in(task, values, *args, **kwargs):
        found = real(task, values, *args, **kwargs)
        name, value = refused
        if values.get(name) == value:
            return [*found, Finding("stand-in", f"{name!r} at {value:g} breaks the run here")]
        if warned is not None and values.get(warned[0]) == warned[1]:
            return [*found, Finding("stand-in-warning", f"{warned[0]!r} at {warned[1]:g} is warned",
                                    blocking=False, accepted_in=SESSION_KINDS)]
        return found

    monkeypatch.setattr(taskd, "beyond_range", standing_in)


def test_a_revert_restores_each_value_held_or_handed_back_and_each_range_as_then(tmp_path):
    """The C3 spec §8 ("each task setting to its value then, held or handed back as it was then,
    and each drawn range as it was"). A person holds the target's place over its condition's and
    its height, and narrows the task's draw of the fixation hold (changes 1 to 3); then hands the
    place back, moves the height, narrows the draw again and holds the fixation point's luminance
    (4 to 7). The revert to change 3 puts back each value held then through `set` -- the place,
    held over its condition's again, and the height -- hands back the luminance, held since, and
    puts the draw back as it was then: from the next trial on, as after change 3, the hold drawn
    from that range and naming the revert's change."""
    path = _sessions.varied_task(tmp_path, draws=DRAWN)
    key = ("task", "fix_hold")
    then, since = Uniform(0.2, 0.3, repeat=FRESH), Uniform(0.25, 0.3, repeat=FRESH)
    link = _Drained({2: [SetParameter(name="target_x", value=12.0, by=JAKE),
                         SetParameter(name="target_y", value=2.0, by=JAKE),
                         SetRange(name="fix_hold", numbers={"high": 0.3}, by=JAKE)],
                     4: [HandBack(name="target_x", by=JAKE),
                         SetParameter(name="target_y", value=3.0, by=JAKE),
                         SetRange(name="fix_hold", numbers={"low": 0.25}, by=JAKE),
                         SetParameter(name="fix_luminance", value=50.0, by=JAKE)],
                     6: [Revert(change=3, by=JAKE)]})
    session = _session(_spec(tmp_path, path, blocks=[_near(8)]), link)

    session.run()

    assert session.refusals == []
    lines = _lines(session)
    assert [(line["params"]["target_x"], line["params"]["target_y"],
             line["params"]["fix_luminance"], line["live"], line["overridden"], line["drawn"])
            for line in lines] == (
        [(5.0, 0.0, 40.0, [], [], {"fix_hold": "task"})] * 2
        + [(12.0, 2.0, 40.0, ["target_x", "target_y"], ["target_x"], {"fix_hold": 3})] * 2
        + [(5.0, 3.0, 50.0, ["fix_luminance", "target_y"], [], {"fix_hold": 6})] * 2
        + [(12.0, 2.0, 40.0, ["target_x", "target_y"], ["target_x"], {"fix_hold": 8})] * 2)
    assert [line["params"]["fix_hold"] for line in lines[6:]] == [
        variation.draw(then, SEED, 6, key), variation.draw(then, SEED, 7, key)]
    # A value over a setting its conditions give writes no `was` (`Session._block_gives`).
    assert [(row["change"], row["sequence"], row["name"], row["was"], row["now"], row["moment"])
            for row in _reverted(session)] == [
        (8, 8, "fix_luminance", 50.0, None, 3),
        (8, 9, "fix_hold", variation.recorded(since), variation.recorded(then), 3),
        (8, 10, "target_x", None, 12.0, 3),
        (8, 11, "target_y", 3.0, 2.0, 3)]
    assert (session._ranges, session._edited) == (
        {key: (then, 8)}, frozenset({"target_x", "target_y"}))
    assert (session.spec.values["target_x"], session.spec.values["fix_luminance"]) == (12.0, 40.0)


def test_a_revert_to_the_runs_start_hands_everything_back_and_restores_the_declared_ranges(
        tmp_path):
    """The C3 spec §8, a revert to change 0, the run's start: every setting a person holds is
    handed back to what gives it in the open block -- the target's place to its condition, its
    height to the run -- and every draw changed live, the block's own and the task's, is put back
    as declared. Its rows say so: a setting handed back now null, its `to` left out; a draw as
    declared, with every field and whose draw it was (`from`, `block`); each naming the moment, 0.
    The trials after it draw from the declared draws again, naming them as declared. A revert
    then to change 4 brings all of it back, each range from the one declared, naming its change."""
    path = _sessions.varied_task(tmp_path, draws=(
        '{"fix_hold": Uniform(0.2, 0.4, repeat=FRESH), '
        '"fix_luminance": Uniform(30.0, 50.0, repeat=FRESH)}'))
    declared = _load_task(path).draws["fix_luminance"]
    own = Uniform(0.5, 0.6, repeat=FRESH)
    own_key, task_key = ("block", "own", "fix_hold"), ("task", "fix_luminance")
    blocks = [Block("own", [Condition("near", {"target_x": 5.0}, target=8)],
                    draws={"fix_hold": own})]
    link = _Drained({2: [SetParameter(name="target_x", value=12.0, by=JAKE),
                         SetParameter(name="target_y", value=2.0, by=JAKE),
                         SetRange(name="fix_hold", numbers={"high": 0.7}, by=JAKE),
                         SetRange(name="fix_luminance", numbers={"low": 35.0}, by=JAKE)],
                     4: [Revert(change=0, by=JAKE)],
                     6: [Revert(change=4, by=JAKE)]})
    session = _session(_spec(tmp_path, path, blocks=blocks), link)

    session.run()

    assert session.refusals == []
    lines = _lines(session)
    assert [(line["params"]["target_x"], line["params"]["target_y"], line["live"],
             line["drawn"]) for line in lines] == (
        [(5.0, 0.0, [], {"fix_hold": "block", "fix_luminance": "task"})] * 2
        + [(12.0, 2.0, ["target_x", "target_y"], {"fix_hold": 3, "fix_luminance": 4})] * 2
        + [(5.0, 0.0, [], {"fix_hold": "block", "fix_luminance": "task"})] * 2
        + [(12.0, 2.0, ["target_x", "target_y"], {"fix_hold": 6, "fix_luminance": 6})] * 2)
    assert [(line["params"]["fix_hold"], line["params"]["fix_luminance"])
            for line in lines[4:6]] == [
        (variation.draw(own, SEED, index, own_key), variation.draw(declared, SEED, index, task_key))
        for index in (4, 5)]
    widened, raised = Uniform(0.5, 0.7, repeat=FRESH), Uniform(35.0, 50.0, repeat=FRESH)
    reverted = _reverted(session)
    # A value over a setting its conditions give writes no `was` (`Session._block_gives`).
    assert [(row["change"], row["name"], row["was"], row["now"], row.get("from"),
             row.get("block"), row["moment"]) for row in reverted] == [
        (5, "target_x", 12.0, None, None, None, 0),
        (5, "target_y", 2.0, None, None, None, 0),
        (5, "fix_hold", variation.recorded(widened), variation.recorded(own), "block", "own", 0),
        (5, "fix_luminance", variation.recorded(raised), variation.recorded(declared), "task",
         None, 0),
        (6, "fix_hold", variation.recorded(own), variation.recorded(widened), "block", "own", 4),
        (6, "fix_luminance", variation.recorded(declared), variation.recorded(raised), "task",
         None, 4),
        (6, "target_x", None, 12.0, None, None, 4),
        (6, "target_y", 0.0, 2.0, None, None, 4)]
    assert _without_instants(reverted[3]) == {
        "change": 5, "kind": "revert", "name": "fix_luminance",
        "was": variation.recorded(raised), "now": variation.recorded(declared),
        "from": "task", "block": None, "moment": 0,
        "by": BY, "trial_number": 5, "run": 0,
        "meaning": {**FIX_LUMINANCE, "went": None, "step": None},
        "offered": [], "odds": None, "event_code": PARAM_CHANGED, "sequence": 8,
    }
    assert "to" not in reverted[0] and "to" not in reverted[1]
    assert (session._ranges, session._edited) == (
        {own_key: (widened, 6), task_key: (raised, 6)}, frozenset({"target_x", "target_y"}))
    assert _fed(session, "revert")[:4] == [
        ("revert", JAKE, "target_x 12.00 handed back to its conditions, reverting to the run's "
                         "start, from trial 4"),
        ("revert", JAKE, "target_y 2.00 handed back to the run's 0.00, reverting to the run's "
                         "start, from trial 4"),
        ("revert", JAKE, "block 'own''s draw of 'fix_hold' → as declared, reverting to the run's "
                         "start, from trial 4"),
        ("revert", JAKE, "the task's draw of 'fix_luminance' → as declared, reverting to the "
                         "run's start, from trial 4")]


def test_a_revert_is_one_change_its_rows_naming_the_moment(tmp_path):
    """XC-288 §3.4 and the C3 spec §8 ("one `change` id for the whole revert"): every row of one
    revert shares one change id, kind `revert`, each with the moment it goes back to, each its own
    `PARAM_CHANGED` strobe and `sequence`. Each row's `was` is what the setting held just before
    it: here the fixation hold another person set in the same drain, applied ahead of the revert
    with its own change id, not the value before that drain (`set`'s `was`). A setting handed back
    reads `now` null. A value set after the revert applied is an act, and a change, of its own."""
    link = _Drained({2: [SetParameter(name="fix_hold", value=0.5, by=JAKE)],
                     4: [SetParameter(name="fix_hold", value=0.7, by=JAKE),
                         SetParameter(name="target_y", value=2.0, by=JAKE)],
                     6: [SetParameter(name="fix_hold", value=0.9, by=ANA),
                         Revert(change=1, by=JAKE)],
                     8: [SetParameter(name="target_x", value=12.0, by=JAKE)]})
    session = _session(_spec(tmp_path, "tasks/fixation_detection.py", blocks=[_near(10)]), link)

    session.run()

    assert session.refusals == []
    rows = _changes(session)
    # A value over a setting its conditions give writes no `was` (`Session._block_gives`).
    assert [(row["change"], row["sequence"], row["kind"], row["name"], row["was"], row["now"],
             row["by"], row.get("moment")) for row in rows] == [
        (1, 1, "set", "fix_hold", 0.3, 0.5, BY, None),
        (2, 2, "set", "fix_hold", 0.5, 0.7, BY, None),
        (3, 3, "set", "target_y", 0.0, 2.0, BY, None),
        (4, 4, "set", "fix_hold", 0.7, 0.9, ANA_BY, None),
        (5, 5, "revert", "target_y", 2.0, None, BY, 1),
        (5, 6, "revert", "fix_hold", 0.9, 0.5, BY, 1),
        (6, 7, "set", "target_x", None, 12.0, BY, None)]
    assert rows[5]["meaning"] == {**FIX_HOLD, "went": "easier", "step": -0.4}
    assert session.card.codes.count(PARAM_CHANGED) == 7
    assert [(line["params"]["fix_hold"], line["params"]["target_y"], line["live"])
            for line in _lines(session)[5:]] == [
        (0.7, 2.0, ["fix_hold", "target_y"])] + [(0.5, 0.0, ["fix_hold"])] * 2 + [
        (0.5, 0.0, ["fix_hold", "target_x"])] * 2
    assert _fed(session, "revert") == [
        ("revert", JAKE, "target_y 2.00 handed back to the run's 0.00, reverting to change 1, "
                         "from trial 6"),
        ("revert", JAKE, "fix_hold 0.90 → 0.50, reverting to change 1, from trial 6")]
    assert (session._acts, session._act_moments) == ({}, {})


def test_a_moment_is_kept_after_each_act_the_first_the_runs_start(tmp_path):
    """The engine C3 plan's call 24 ("rebuilt from `Session._moments`, a snapshot after each act"):
    the run's start first, change 0, holding nothing; then, after each act as it applies, its
    change id and instant, the act in the feed's words, and what the live layer holds -- each
    setting a person holds with its value, and each draw changed live -- a revert's among them.
    The revert to change 2 puts back the target's place; the range it finds as it was then."""
    path = _sessions.varied_task(tmp_path, draws=DRAWN)
    key, narrowed = ("task", "fix_hold"), Uniform(0.2, 0.3, repeat=FRESH)
    link = _Drained({2: [SetParameter(name="target_x", value=12.0, by=JAKE),
                         SetRange(name="fix_hold", numbers={"high": 0.3}, by=JAKE)],
                     4: [HandBack(name="target_x", by=JAKE)],
                     6: [Revert(change=2, by=JAKE)]})
    session = _session(_spec(tmp_path, path, blocks=[_near(8)]), link)

    session.run()

    at, moment = {row["change"]: row["at"] for row in _changes(session)}, taskd.Moment
    assert session._moments == [
        moment(0, WALL_NOW, "the run's start", {}, {}),
        moment(1, at[1], "target_x 10.00 → 12.00", {"target_x": 12.0}, {}),
        moment(2, at[2], "the task's draw of 'fix_hold' → uniform from 0.2 s to 0.3 s",
               {"target_x": 12.0}, {key: narrowed}),
        moment(3, at[3], "target_x 12.00 handed back to its conditions", {}, {key: narrowed}),
        moment(4, at[4], "reverted to change 2", {"target_x": 12.0}, {key: narrowed}),
    ]
    # A value over a setting its conditions give writes no `was` (`Session._block_gives`).
    assert [(row["kind"], row["name"], row["was"], row["now"]) for row in _reverted(session)] == [
        ("revert", "target_x", None, 12.0)]


def test_every_moment_of_the_run_is_kept_past_the_consoles_cap_its_start_first(tmp_path):
    """The outline review's M-15: the console's list of moments is capped, keeping the run's start
    (`link.CONTROL_HISTORY`; telemetry schema 19). The session keeps
    every moment of the run, its start first, so a revert reaches any change of it, the first
    among them, however many came after: 55 values set in one drain, then a revert to change 1."""
    held = [SetParameter(name="fix_hold", value=round(0.3 + step / 100, 2), by=JAKE)
            for step in range(1, 56)]
    link = _Drained({2: held, 4: [Revert(change=1, by=JAKE)]})
    session = _session(_spec(tmp_path, "tasks/fixation_detection.py", blocks=[_near(6)]), link)

    session.run()

    assert session.refusals == []
    assert len(session._moments) == 57 > CONTROL_HISTORY
    assert (session._moments[0].change, session._moments[0].said) == (0, "the run's start")
    (row,) = _reverted(session)
    assert (row["change"], row["name"], row["was"], row["now"], row["moment"]) == (
        56, "fix_hold", 0.85, 0.31, 1)
    assert [line["params"]["fix_hold"] for line in _lines(session)[2:]] == [0.85] * 2 + [0.31] * 2


def test_a_revert_to_a_clears_change_restores_the_moment_in_force_then(tmp_path):
    """The engine C3 plan's call 24 (its review, M-15): a clear, a drumming switch and a training
    switch each take a change id and keep no moment, since they move no setting and no range; a
    revert to one goes back to what was in force then, the latest moment at or before it, and its
    rows name the id it was given. Counts and training aids are not reverted (the C3 spec §8): the
    trial cleared stays cleared, drumming and *clear* stay on, and their control rows stand."""
    link = _Drained({2: [SetParameter(name="target_x", value=12.0, by=JAKE)],
                     3: [Training(setting="clear", on=True, by=JAKE),
                         ClearOwed(condition="near", by=JAKE),
                         SetParameter(name="target_y", value=2.0, by=JAKE)],
                     4: [Drum(scope="block", by=JAKE)],
                     5: [SetParameter(name="fix_luminance", value=50.0, by=JAKE)],
                     7: [Revert(change=3, by=JAKE)],
                     9: [Revert(change=5, by=JAKE)]})
    session = _session(_spec(tmp_path, "tasks/fixation_detection.py", blocks=[_near(12)]), link)

    session.run()

    assert session.refusals == []
    assert [(row["change"], row["kind"], row["name"]) for row in _changes(session)][:6] == [
        (1, "set", "target_x"), (2, "training", "clear"), (3, "clear", "owed"),
        (4, "set", "target_y"), (5, "drum", "drumming"), (6, "set", "fix_luminance")]
    assert [(row["change"], row["name"], row["was"], row["now"], row["moment"])
            for row in _reverted(session)] == [
        (7, "fix_luminance", 50.0, None, 3), (7, "target_y", 2.0, None, 3),
        (8, "target_y", 0.0, 2.0, 5)]
    assert [m.change for m in session._moments] == [0, 1, 4, 6, 7, 8]
    assert [(line["params"]["target_y"], line["params"]["fix_luminance"])
            for line in _lines(session)] == (
        [(0.0, 40.0)] * 3 + [(2.0, 40.0)] * 2 + [(2.0, 50.0)] * 2 + [(0.0, 40.0)] * 2
        + [(2.0, 40.0)] * 2)
    scheduler = session._scheduler
    assert (scheduler.drumming, scheduler.clearing) == ("block", True)
    assert [(s.condition, s.trials, s.because) for s in scheduler.shortfalls] == [
        ("near", 1, "cleared")]
    assert [row["kind"] for row in _rows(session, "controls.jsonl")
            if row["kind"] in ("clear", "drum", "training")] == ["training", "clear", "drum"]


def test_a_revert_is_refused_whole_when_one_value_is_and_writes_no_change_row(
        tmp_path, monkeypatch):
    """The C3 spec's welfare item 3 ("each value goes through `Session.set` unchanged, and the
    revert is refused whole if any value is"), with this file's stand-in for a value whose widened
    checks break the run. The revert to change 2 puts back two values outside their declared
    ranges, each through `set`: the fixation hold first, accepted with a warning the stand-in
    gives it, then the response deadline, refused. The whole revert is refused with `set`'s
    sentence: no change row is written and nothing applies -- what it staged and offered is cut
    back, and the trials after run as before. The warning `set` accepted for the earlier value
    stays accepted, by `_beyond_range`'s rule (the outline review's M-16)."""
    link = _Drained({2: [SetParameter(name="fix_hold", value=2.5, by=JAKE),
                         SetParameter(name="response_deadline", value=3.5, by=JAKE)],
                     4: [HandBack(name="fix_hold", by=JAKE),
                         HandBack(name="response_deadline", by=JAKE)],
                     6: [Revert(change=2, by=JAKE)]})

    def world(trial, values, index):
        if index == 4:
            # After the two hand-backs were offered (the 4th drain), before the revert is.
            _breaks(monkeypatch, ("response_deadline", 3.5), warned=("fix_hold", 2.5))
        return _right(values)

    session = _session(_spec(tmp_path, "tasks/fixation_detection.py", blocks=[_near(8)]), link,
                       world=world)

    session.run()

    assert session.refusals == [("revert", JAKE, (
        "the revert to change 2 is refused, and none of it applies: 'response_deadline' at 3.5 "
        "is outside its declared range, and with the range widened to it the load-time checks "
        "refuse it: stand-in: 'response_deadline' at 3.5 breaks the run here; the previous value "
        "stands"))]
    assert [(row["change"], row["kind"], row["name"]) for row in _changes(session)] == [
        (1, "set", "fix_hold"), (2, "set", "response_deadline"),
        (3, "hand_back", "fix_hold"), (4, "hand_back", "response_deadline")]
    (*_, kept) = _rows(session, "warnings.jsonl")
    assert (kept["code"], kept["detail"], kept["by"]) == (
        "stand-in-warning", "'fix_hold' at 2.5 is warned", BY)
    assert (session._staged, session._pending, session._acts, session._act_moments) == (
        [], [], {}, {})
    assert [(line["params"]["fix_hold"], line["params"]["response_deadline"], line["live"])
            for line in _lines(session)[4:]] == [(0.3, 0.6, [])] * 4


def test_a_revert_refused_whole_leaves_another_persons_staged_change_alone(
        tmp_path, monkeypatch):
    """Review Focus 3 (the C3 spec §8; `_hold` drains through `_command`): while the session is
    paused, Ana sets the fixation point's luminance, then Jake sends two reverts in the same
    drain. The first, to change 1, would put back a response deadline whose widened checks this
    file's stand-in breaks: it is refused whole, and Ana's value stays staged. The second, to
    change 3, is accepted: it hands back what is held since, Ana's luminance among the rest, since
    a revert goes back to its moment whatever changed since. At the resume Ana's change applies
    first with its own change id, and the revert after it as one act."""
    waiting = []

    class Watched(_Drained):
        def drain(self) -> list:
            if self.drains == 7:
                # As the 8th drain, the resume's, begins: what the paused drain left offered.
                waiting.append((list(session._staged),
                                [(act.kind, act.name, act.act) for act in session._pending],
                                dict(session._act_moments)))
            return super().drain()

    link = Watched({2: [SetParameter(name="response_deadline", value=3.5, by=JAKE)],
                    3: [HandBack(name="response_deadline", by=JAKE),
                        SetParameter(name="fix_hold", value=0.5, by=JAKE)],
                    5: [SetParameter(name="target_x", value=12.0, by=JAKE)],
                    6: [Pause(by=JAKE)],
                    7: [SetParameter(name="fix_luminance", value=50.0, by=ANA),
                        Revert(change=1, by=JAKE), Revert(change=3, by=JAKE)],
                    8: [Resume(by=JAKE)]})

    def world(trial, values, index):
        if index == 3:
            # After the response deadline was handed back, before anything is reverted.
            _breaks(monkeypatch, ("response_deadline", 3.5))
        return _right(values)

    session = _session(_spec(tmp_path, "tasks/fixation_detection.py", blocks=[_near(8)]), link,
                       world=world)

    session.run()

    assert session.refusals == [("revert", JAKE, (
        "the revert to change 1 is refused, and none of it applies: 'response_deadline' at 3.5 "
        "is outside its declared range, and with the range widened to it the load-time checks "
        "refuse it: stand-in: 'response_deadline' at 3.5 breaks the run here; the previous value "
        "stands"))]
    ((staged, pending, moments),) = waiting
    (act,) = moments
    assert (staged, pending, moments) == (
        [("fix_luminance", 40.0, 50.0, ANA, False)],
        [("hand_back", "fix_luminance", act), ("hand_back", "target_x", act)], {act: 3})
    rows = _changes(session)
    assert [(row["change"], row["kind"], row["name"], row["was"], row["now"], row["by"])
            for row in rows[4:]] == [
        (5, "set", "fix_luminance", 40.0, 50.0, ANA_BY),
        (6, "revert", "fix_luminance", 50.0, None, BY),
        (6, "revert", "target_x", 12.0, None, BY)]
    kinds = [kind for kind, _, _, _ in session.controls]
    assert kinds.index("pause") < kinds.index("resume") < kinds.index("set", kinds.index(
        "resume")) < kinds.index("revert")
    assert [(line["params"]["fix_luminance"], line["params"]["target_x"], line["live"])
            for line in _lines(session)[5:]] == [(40.0, 5.0, ["fix_hold"])] * 3


@pytest.mark.parametrize("broken", ["impossible", "possible", "beyond_range", "set"])
def test_a_check_that_raises_inside_a_revert_refuses_it_and_the_session_runs_on(
        tmp_path, monkeypatch, broken):
    """Review Focus 5, the revert's part (the outline review's I-1; the C3 plan's call 20): a
    revert runs beside the pause, outside `_command`'s listed `try`, so it refuses its own faults.
    A check that raises -- `check.impossible`, as `_possible` meets it and says it could not run;
    `_possible` itself; `check.beyond_range`, as `set`'s `_beyond_range` meets it and refuses the
    value; `set` itself, on the second of the two values the revert puts back -- refuses the
    revert whole, saying so, and the session runs to its end with nothing of the revert applied:
    the hand-back it offered and the value it staged ahead of the fault are cut back too. The
    stand-ins are this file's own: each raises from the trial after the values the revert puts
    back were set and handed back, so that they were checked first."""
    link = _Drained({2: [SetParameter(name="fix_hold", value=2.5, by=JAKE),
                         SetParameter(name="target_x", value=12.0, by=JAKE)],
                     3: [HandBack(name="fix_hold", by=JAKE), HandBack(name="target_x", by=JAKE),
                         SetParameter(name="target_y", value=2.0, by=JAKE)],
                     5: [Revert(change=2, by=JAKE)]})

    def raising(*args, **kwargs):
        raise ZeroDivisionError("division by zero")

    def world(trial, values, index):
        if index == 3:
            # After the hand-backs were applied (the 4th trial), before the revert is offered.
            if broken == "possible":
                monkeypatch.setattr(session, "_possible", raising)
            elif broken == "set":
                real = session.set
                monkeypatch.setattr(session, "set", lambda name, value, by: (
                    raising() if name == "target_x" else real(name, value, by=by)))
            else:
                monkeypatch.setattr(taskd, broken, raising)
        return _right(values)

    session = _session(_spec(tmp_path, "tasks/fixation_detection.py", blocks=[_near(7)]), link,
                       world=world)

    session.run()

    assert session.stop_kind == "completed"
    assert session.refusals == [("revert", JAKE, {
        "impossible": "the revert to change 2 is refused, and none of it applies: the check for "
                      "trials no animal can get right could not be run (ZeroDivisionError: "
                      "division by zero)",
        "beyond_range": "the revert to change 2 is refused, and none of it applies: 'fix_hold' "
                        "at 2.5 is outside its declared range, and the load-time checks could "
                        "not be run again with the range widened (ZeroDivisionError: division by "
                        "zero), so it is refused and the previous value stands",
    }.get(broken, "the revert to change 2 could not be checked (ZeroDivisionError: division by "
                  "zero), so it is refused, none of it applies, and the session runs on"))]
    assert [row["kind"] for row in _changes(session)] == [
        "set", "set", "hand_back", "hand_back", "set"]
    assert (session._staged, session._pending, session._edited) == (
        [], [], frozenset({"target_y"}))
    assert {(line["params"]["fix_hold"], line["params"]["target_x"])
            for line in _lines(session)[4:]} == {(0.3, 5.0)}


def test_a_revert_never_moves_a_reward_size(tmp_path):
    """The C3 spec's welfare item 3 ("never a bounded setting such as a reward size"; engine spec
    §17.6): a reward size a person sets is a ceiling's, staged and applied by `set`'s and
    `bounds`' own branch, never held as a task setting, even where the task declares a setting of
    its name. So its act keeps no moment, no moment holds it, and a revert -- even to its own
    change id, which goes back to the moment in force then -- hands back the task's own setting
    and leaves the reward size where the person last set it."""
    link = _Drained({2: [SetParameter(name="reward_correct", value=0.2, by=JAKE),
                         SetParameter(name="fix_hold", value=0.5, by=JAKE)],
                     4: [SetParameter(name="reward_correct", value=0.25, by=JAKE)],
                     6: [Revert(change=1, by=JAKE)]})
    session = _session(_spec(tmp_path, _ceiling(tmp_path), trials=8), link)

    session.run()

    assert session.refusals == []
    assert session.spec.bounds.value("reward_correct") == 0.25
    assert [(row["change"], row["kind"], row["name"], row["now"]) for row in
            _changes(session)] == [
        (1, "set", "reward_correct", 0.2), (2, "set", "fix_hold", 0.5),
        (3, "set", "reward_correct", 0.25), (4, "revert", "fix_hold", None)]
    assert [moment.change for moment in session._moments] == [0, 2, 4]
    assert all("reward_correct" not in moment.held for moment in session._moments)


def test_a_revert_to_an_earlier_runs_change_or_an_unknown_one_is_refused(tmp_path):
    """The engine C3 plan's call 24 and its Appendix B item 5 ("Revert reaches back within the
    current run"): in a `wlx taskd` session's second run, a revert to a change of the first run,
    to one not made yet, or to the run's start while nothing has changed since, is refused with
    its sentence; one whose change is no whole number from 0 is refused by the wire's own rule,
    since a command can reach the session another way. The second run's moments begin with its
    own start; a revert to its own change goes back to it."""
    path = _sessions.varied_task(tmp_path)
    link = _Drained({1: [SetParameter(name="fix_hold", value=0.5, by=JAKE)],
                     3: [Stop(by=JAKE)],
                     4: [Revert(change=0, by=JAKE), Revert(change=1, by=JAKE),
                         Revert(change=9, by=JAKE), Revert(change=-1, by=JAKE),
                         Revert(change=True, by=JAKE), Revert(change="2", by=JAKE)],
                     5: [SetParameter(name="target_x", value=12.0, by=JAKE)],
                     6: [HandBack(name="target_x", by=JAKE)],
                     8: [Revert(change=2, by=JAKE)]})
    session = _session(_spec(tmp_path, "", trials=0, values={}), link, service=True)
    run = RunSpec(task=str(path), trials=10, seed=SEED, values={"target_appearance": None})

    session.run(run)
    session.run(run)

    wire = ("a 'revert' command's change is a whole number from 0, and {} is not one, so it is "
            "refused")
    assert session.refusals == [
        ("revert", JAKE, "the revert to the run's start is refused, and none of it applies: the "
                         "run holds now what it held then, so there is nothing to revert"),
        ("revert", JAKE, "the revert to change 1 is refused, and none of it applies: change 1 was "
                         "made before run 2 started, and a revert goes back within the run in "
                         "progress, to one of its changes or to its start (0)"),
        ("revert", JAKE, "the revert to change 9 is refused, and none of it applies: no change 9 "
                         "has been made yet"),
        ("revert", JAKE, wire.format("-1")), ("revert", JAKE, wire.format("True")),
        ("revert", JAKE, wire.format("'2'")),
    ]
    assert [(row["change"], row["kind"], row["name"], row["run"]) for row in
            _changes(session)] == [
        (1, "set", "fix_hold", 0), (2, "set", "target_x", 1), (3, "hand_back", "target_x", 1),
        (4, "revert", "target_x", 1)]
    assert [moment.change for moment in session._moments] == [0, 2, 3, 4]
    assert session._moments[0].said == "the run's start"


def test_a_revert_drained_with_a_stop_is_dropped_and_said(tmp_path):
    """The b3a-1 plan's decision 2, for a revert (the outline review's M-5): between a `wlx taskd`
    session's runs nothing applies what was offered, so a revert drained with the stop that ends a
    run -- here a value put back and a setting handed back -- is dropped, said once on the feed,
    as the one act it is, and not written; and what it staged is forgotten with it, so the next
    run's first value is a change of its own, no revert's."""
    path = _sessions.varied_task(tmp_path)
    link = _Drained({1: [SetParameter(name="fix_hold", value=0.5, by=JAKE)],
                     2: [SetParameter(name="fix_hold", value=0.7, by=JAKE),
                         SetParameter(name="target_x", value=12.0, by=JAKE)],
                     3: [Revert(change=1, by=JAKE), Stop(by=JAKE)],
                     4: [SetParameter(name="target_x", value=12.0, by=JAKE)]})
    session = _session(_spec(tmp_path, "", trials=0, values={}), link, service=True)
    run = RunSpec(task=str(path), trials=4, seed=SEED, values={"target_appearance": None})

    session.run(run)

    assert _fed(session, "revert") == [
        ("revert", JAKE, "the revert to change 1 was not applied: run 1 ended first")]
    assert (session._staged, session._acts, session._act_moments) == ([], {}, {})

    session.run(run)

    assert [(row["change"], row["kind"], row["name"], row["run"]) for row in _changes(session)] == [
        (1, "set", "fix_hold", 0), (2, "set", "fix_hold", 0), (3, "set", "target_x", 0),
        (4, "set", "target_x", 1)]


def test_a_revert_judges_each_value_over_what_it_hands_back_and_restores(tmp_path):
    """An engineering call of the engine C3 plan's Task 14: a revert offers its hand-backs and
    ranges ahead of its values, so `set` judges each value over the moment the revert goes back
    to, not over what it is about to undo. 13 objects fit on `visual_search`'s 8° ring (change 1);
    then the set size is handed back and the ring drawn in to 4°, past its declared 5° (warned:
    six fit there). The revert to change 1 hands the ring back to 8° and puts 13 objects back:
    judged on the 8° ring, they are accepted; judged on the 4° one, they would crowd it."""
    blocks = [Block("ring", [Condition("any", {}, target=8)])]
    link = _Drained({2: [SetParameter(name="set_size", value=13, by=JAKE)],
                     3: [HandBack(name="set_size", by=JAKE),
                         SetParameter(name="array_eccentricity", value=4.0, by=JAKE)],
                     5: [Revert(change=1, by=JAKE)]})
    session = _session(_spec(tmp_path, "tasks/visual_search.py", blocks=blocks,
                             values=dict(SEARCHED)), link, world=None)

    session.run()

    assert session.refusals == []
    assert [(row["change"], row["kind"], row["name"], row["was"], row["now"])
            for row in _changes(session)] == [
        (1, "set", "set_size", 6, 13), (2, "hand_back", "set_size", 13, 6),
        (3, "set", "array_eccentricity", 8.0, 4.0),
        (4, "revert", "array_eccentricity", 4.0, None), (4, "revert", "set_size", 6, 13)]
    lines = _lines(session)
    assert len(lines) > 6 and all(
        (line["params"]["set_size"], line["params"]["array_eccentricity"]) == (13, 8.0)
        for line in lines[5:])


def test_a_hand_backs_moment_says_what_took_the_setting_where_it_applied(tmp_path):
    """The review of Task 14, Important 1 (the plan's engineering review, M-1, for the moment): a
    hand-back offered as block A's rule is met applies in block B, whose conditions leave the
    target's place to the run. Its row, its feed line and the moment it keeps say what takes it
    back where it applies, the run's 10.00, never A's conditions, which no trial of B held."""
    plans = ("{'p': Plan(blocks=[Block('A', conditions=[Condition('a', {'target_x': 5.0}, "
             "target=3)]), Block('B', conditions=[Condition('b', {}, target=3)])])}")
    path = _sessions.varied_task(tmp_path, plans=plans)
    link = _Drained({1: [SetParameter(name="target_x", value=12.0, by=JAKE)],
                     4: [HandBack(name="target_x", by=JAKE)]})
    session = _session(_spec(tmp_path, path, trials=6, plan="p"), link)

    session.run()

    said = "target_x 12.00 handed back to the run's 10.00"
    assert [said_ for _, _, said_ in _fed(session, "hand_back")] == [f"{said}, from trial 3"]
    assert [(m.change, m.said) for m in session._moments] == [
        (0, "the run's start"), (1, "target_x 10.00 → 12.00"), (2, said)]


def test_two_identical_reverts_in_one_drain_apply_once_and_the_second_changes_nothing(tmp_path):
    """The review of Task 14, Minor 4 (Appendix B item 15's backstop in the session): a double
    click sends the same revert twice. The second is judged over what the first offers, finds the
    run already holding that moment, and is refused as changing nothing; the first applies as one
    act."""
    link = _Drained({2: [SetParameter(name="fix_hold", value=0.5, by=JAKE)],
                     4: [Revert(change=0, by=JAKE), Revert(change=0, by=JAKE)]})
    session = _session(_spec(tmp_path, "tasks/fixation_detection.py", blocks=[_near(8)]), link)

    session.run()

    assert session.refusals == [("revert", JAKE, (
        "the revert to the run's start is refused, and none of it applies: the run holds now "
        "what it held then, so there is nothing to revert"))]
    assert [(row["change"], row["name"], row["moment"]) for row in _reverted(session)] == [
        (2, "fix_hold", 0)]
    assert [m.change for m in session._moments] == [0, 1, 2]


def test_a_revert_the_waiting_trial_cannot_meet_is_refused_whole_by_the_tasks_own_check(tmp_path):
    """The review of Task 14, Minor 2 (probe P2), the real path of welfare item 3's refusal, no
    stand-in: the fixation hold times out after `fix_acquisition`, and is drawn `same`. A person
    sets the acquisition time to 1 s (change 1), hands it back and widens the hold's draw to 1.8 s
    (changes 2 and 3) in a drummed block. A try breaks and waits, keeping a hold of more than 1 s
    -- then a revert to change 1 would put back the 1 s timeout under it. `_possible` refuses the
    whole, naming the condition, both values and the way on; nothing is staged, offered or
    written."""
    path = _edited(
        _sessions.varied_task(
            tmp_path, draws='{"fix_hold": Uniform(0.2, 0.4, repeat=SAME)}',
            plans='{"p": Plan([Block("b", [Condition("c", {}, target=9)], drum=True)])}'),
        ("                On(After(10.0), Outcome.NO_FIXATION),",
         '                On(After(P("fix_acquisition")), Outcome.NO_FIXATION),'))

    def world(trial, values, index):
        return BREAK if index >= 7 else _right(values)

    link = _Drained({2: [SetParameter(name="fix_acquisition", value=1.0, by=JAKE)],
                     3: [HandBack(name="fix_acquisition", by=JAKE),
                         SetRange(name="fix_hold", numbers={"high": 1.8}, by=JAKE)],
                     10: [Revert(change=1, by=JAKE)], 14: [Stop(by=JAKE)]})
    session = _session(_spec(tmp_path, path, plan="p"), link, world=world)

    session.run()

    ((kind, by, said),) = session.refusals
    assert (kind, by) == ("revert", JAKE)
    assert said.startswith(
        "the revert to change 1 is refused, and none of it applies: it would leave trials no "
        "animal can get right, in b: c (impossible-trial): block 'b', condition 'c': state "
        "'hold_fix' ends the trial NO_FIXATION after `fix_acquisition`, 1 s, while its 'fix' hold "
        "takes `fix_hold`, 1.56628 s: ")
    assert said.endswith("a trial waiting to be shown again, or the next one drawn before the "
                         "change applies, keeps the value it drew for a setting declared same: "
                         "clear the waiting trial, switch drumming off or pause, then make the "
                         "change")
    assert [row["kind"] for row in _changes(session)] == ["set", "hand_back", "range"]
    assert (session._staged, session._pending, session._acts, session._act_moments) == (
        [], [], {}, {})
    assert len({line["params"]["fix_hold"] for line in _lines(session)[7:]}) == 1
