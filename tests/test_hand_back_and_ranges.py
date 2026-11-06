"""Hand back, and a drawn range changed live (engine build C3's spec §6 and §14 item 1).

The PI, 2026-10-30: Q7a, "Yes, a 'hand back' button" ("from the next trial the conditions'
values apply again, trials no longer marked; recorded as a change"); Q7b, "Yes, range changes
live" ("recorded as a change; trials stay drawn, not overridden; the record says which range
each trial was drawn from"); and on a condition's own range changed live, "Not in C3". Two
branches beside the pause in the welfare-listed `Session._command` hand `link.HandBack` and
`link.SetRange` to `Session._hand_back` and `_range`, off the list (the C3 spec's welfare item 1,
approved for the design, "Approve all four"), which never raise: each refuses with its sentence,
a check that raises among them. What each accepts waits in `Session._pending` and applies at the
next boundary with the values staged, in the order offered (`_apply_staged`), each its own change
id, `PARAM_CHANGED` strobe and change row (`hand_back`, `range`); a change offered after it is
judged over it. Neither passes through `Session.set`, and neither reaches a reward size.
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
from wl_xcon.link import Drum, HandBack, Pause, Resume, SetParameter, SetRange, Simulated, Stop
from wl_xcon.photometry import SRGB
from wl_xcon.run import Scripted
from wl_xcon.task import FRESH, SAME, Block, Condition, Polar, SaccadeTo, Uniform
from wl_xcon.taskd import RunSpec, Session, SessionSpec
from wl_xcon.welfare import Deployment, Simulated as Pump

#: The wall every session here reads from, plus its frames' seconds (`_session`).
WALL_NOW = 1_700_000_000.0
SEED = 7
JAKE = Box("jake")
#: Jake as a change row writes him.
BY = {"kind": "box", "name": "jake"}
#: `PARAM_CHANGED`'s code in the reference allocation: what each change here strobes.
PARAM_CHANGED = 4130
#: A trial the animal breaks: it looks away from the fixation point at its sixth frame, before
#: any hold here is done, a fixation break, owed.
BREAK = Scripted({}, inside={frame: "fix" for frame in range(1, 6)})
#: The reference task's fixation hold's meaning, as a change row writes it.
FIX_HOLD = {"kind": "clear-cut", "role": "criterion", "raising": "harder", "relative_to": None}
#: `visual_search`'s values: its target red among green, a ring of six objects 8° out.
SEARCH = _load_task(Path("tasks/visual_search.py"))
((RED, GREEN, _),) = [p.choices for p in SEARCH.params if p.name == "target_appearance"]
SEARCHED = {"fix_acquisition": 4.0, "fix_hold": 0.3, "response_deadline": 0.6,
            "target_hold": 0.2, "fix_window": 2.0, "object_window": 0.5,
            "array_eccentricity": 8.0, "set_size": 6, "target_index": 0,
            "array_rotation": 0.0, "fix_luminance": 40.0,
            "target_appearance": RED, "distractor_appearance": GREEN}


def _right(values: dict) -> Scripted:
    """A trial the animal gets right, whatever its holds: it holds the fixation point 20 frames
    past its hold, then looks at the target and stays on it 400 frames, past any target hold
    drawn here."""
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


def _deadline(folder: Path, draws: str, plans: str = "{}") -> Path:
    """`varied_task` drawing `draws` with `plans`, its target hold bounded by the deadline: the
    timeout in `verify`, which the reference task writes as 3 s, reads `response_deadline`, so a
    trial whose target hold is longer than its deadline leaves no time to answer (XC-343's first
    combination). Engine test material, run only in the simulator."""
    return _edited(
        _sessions.varied_task(folder, draws=draws, plans=plans, name="deadline"),
        ("                On(After(3.0), Outcome.NO_RESPONSE),",
         '                On(After(P("response_deadline")), Outcome.NO_RESPONSE),'))


def _directed(folder: Path, draws: str, plans: str) -> Path:
    """`varied_task` drawing `draws` with `plans`, its target placed by eccentricity and direction,
    `target_ecc` and `target_dir` (-180° to 180°, as `tests/test_draws_in_runs.py`'s), and its
    target window's radius declared not live-editable. Engine test material."""
    return _edited(
        _sessions.varied_task(folder, draws=draws, plans=plans, name="directed"),
        ("from wl_xcon.photometry import Gray\nfrom wl_xcon.task import (",
         "from wl_xcon.photometry import Gray\nfrom wl_xcon.task import (\n    Polar,"),
        ('"target", at=(P("target_x"), P("target_y")), looks=P("target_appearance")',
         '"target", at=Polar(P("target_ecc"), P("target_dir")), looks=P("target_appearance")'),
        ('            at=(P("target_x"), P("target_y")),\n            radius=P("target_window"),',
         '            at=Polar(P("target_ecc"), P("target_dir")),\n'
         '            radius=P("target_window"),'),
        ('        Param("target_window", unit="deg", low=0.5, high=6.0, start=3.0),',
         '        Param("target_window", unit="deg", low=0.5, high=6.0, start=3.0, live=False),'),
        ('        Param("target_x", unit="deg", low=-16.0, high=16.0, start=10.0),',
         '        Param("target_ecc", unit="deg", low=0.0, high=16.0, start=8.0),\n'
         '        Param("target_dir", unit="deg", low=-180.0, high=180.0, start=0.0),\n'
         '        Param("target_x", unit="deg", low=-16.0, high=16.0, start=10.0),'),
        tail=("from wl_xcon.task import NOT_DIFFICULTY, STIMULUS, Meaning\n"
              "TASK = _dataclasses.replace(TASK, meanings={\n"
              "    **TASK.meanings,\n"
              "    'target_ecc': Meaning(NOT_DIFFICULTY, STIMULUS, note='how far out'),\n"
              "    'target_dir': Meaning(NOT_DIFFICULTY, STIMULUS, note='which way'),\n"
              "})\n"))


def _ceiling(folder: Path) -> Path:
    """`varied_task` declaring a setting named as the reward ceiling is, `reward_correct`, which
    nothing reads, with a meaning, as a task may (as `tests/test_live_refusal.py`'s does). Engine
    test material."""
    return _edited(
        _sessions.varied_task(folder, name="ceiling"),
        ('        Param("target_hold", unit="s", low=0.05, high=1.0, start=0.2),',
         '        Param("reward_correct", unit="mL", low=0.0, high=1.0),\n'
         '        Param("target_hold", unit="s", low=0.05, high=1.0, start=0.2),'),
        tail=("from wl_xcon.task import NEITHER, NOT_DIFFICULTY, Meaning\n"
              "TASK = _dataclasses.replace(TASK, meanings={'reward_correct': Meaning(\n"
              "    NOT_DIFFICULTY, NEITHER, note='named as a ceiling is, read by nothing')})\n"))


def test_a_hand_back_returns_a_setting_to_its_conditions_from_the_next_trial(tmp_path):
    """Q7a: a person's value over the condition's (TSK-19), then *hand back*: from the next trial
    the condition's value applies again, its trials no longer `live` or `overridden`. The
    hand-back is a change of its own (XC-288 §3.4): a change id, one `PARAM_CHANGED` strobe with
    its `sequence`, the person's value as `was` and `now` null, since the conditions take the
    setting back in the open block (`to`), the first trial it applies to and the setting's
    meaning; the setting holds the run's own value again (the C3 plan's call 23), and the feed
    says so. A setting no person holds, and one the task does not declare, are not handed back."""
    link = _Drained({2: [SetParameter(name="target_x", value=12.0, by=JAKE)],
                     4: [HandBack(name="target_x", by=JAKE), HandBack(name="fix_hold", by=JAKE),
                         HandBack(name="fix_holdd", by=JAKE)]})
    session = _session(_spec(tmp_path, "tasks/fixation_detection.py", blocks=[
        Block("b", [Condition("near", {"target_x": 5.0}, target=6)])]), link)

    session.run()

    assert session.refusals == [
        ("fix_hold", JAKE, "'fix_hold' is not handed back: no person holds it in this run, so "
                           "there is nothing to hand back"),
        ("fix_holdd", JAKE, "'fix_holdd' is not handed back: it is not a setting this task "
                            "declares"),
    ]
    assert [(line["params"]["target_x"], line["live"], line["overridden"])
            for line in _lines(session)] == (
        [(5.0, [], [])] * 2 + [(12.0, ["target_x"], ["target_x"])] * 2 + [(5.0, [], [])] * 2)
    offered, handed = _changes(session)
    assert (offered["kind"], offered["change"], offered["sequence"]) == ("set", 1, 1)
    assert _without_instants(handed) == {
        "change": 2, "kind": "hand_back", "name": "target_x", "was": 12.0, "now": None,
        "to": "conditions", "by": BY, "trial_number": 5, "run": 0,
        "meaning": {"kind": "not a difficulty setting", "role": "stimulus", "raising": None,
                    "relative_to": None, "went": None, "step": None},
        "offered": [], "odds": None, "event_code": PARAM_CHANGED, "sequence": 2,
    }
    assert session.card.codes.count(PARAM_CHANGED) == 2
    assert (session.spec.values["target_x"], session._edited) == (10.0, frozenset())
    assert _fed(session, "hand_back") == [
        ("hand_back", JAKE, "target_x 12.00 handed back to its conditions, from trial 4")]


def test_a_hand_back_of_a_drawn_setting_draws_it_again_and_of_a_run_setting_restores_the_runs_value(
        tmp_path):
    """Where the open block draws the setting, the hand-back gives it back to the draw (`to`
    `"draw"`): the trials after it draw it again, keyed as ever, naming the draw. Where only the
    run gives it, it goes back to the run's own value, the run's given one over the task's start
    (the C3 plan's call 23: `to` `"run"`, `now` that value, its step from the person's)."""
    path = _sessions.varied_task(tmp_path, draws='{"fix_hold": Uniform(0.2, 0.4, repeat=FRESH)}')
    drawn, key = _load_task(path).draws["fix_hold"], ("task", "fix_hold")
    link = _Drained({2: [SetParameter(name="fix_hold", value=0.5, by=JAKE),
                         SetParameter(name="target_y", value=3.0, by=JAKE)],
                     4: [HandBack(name="fix_hold", by=JAKE), HandBack(name="target_y", by=JAKE)]})
    session = _session(_spec(tmp_path, path, trials=6,
                             values={"target_appearance": None, "target_y": 1.5}), link)

    session.run()

    assert session.refusals == []
    lines = _lines(session)
    assert [(line["drawn"], line["live"], line["params"]["target_y"]) for line in lines] == (
        [({"fix_hold": "task"}, [], 1.5)] * 2 + [({}, ["fix_hold", "target_y"], 3.0)] * 2
        + [({"fix_hold": "task"}, [], 1.5)] * 2)
    assert [line["params"]["fix_hold"] for line in lines] == [
        variation.draw(drawn, SEED, 0, key), variation.draw(drawn, SEED, 1, key), 0.5, 0.5,
        variation.draw(drawn, SEED, 4, key), variation.draw(drawn, SEED, 5, key)]
    rows = _changes(session)
    assert [(row["change"], row["kind"], row["name"], row["was"], row["now"], row.get("to"))
            for row in rows] == [
        (1, "set", "fix_hold", 0.3, 0.5, None), (2, "set", "target_y", 1.5, 3.0, None),
        (3, "hand_back", "fix_hold", 0.5, None, "draw"),
        (4, "hand_back", "target_y", 3.0, 1.5, "run")]
    assert (rows[2]["meaning"]["step"], rows[3]["meaning"]["step"]) == (None, -1.5)
    assert (session.spec.values["fix_hold"], session.spec.values["target_y"]) == (0.3, 1.5)
    assert _fed(session, "hand_back") == [
        ("hand_back", JAKE, "fix_hold 0.50 handed back to its draw, from trial 4"),
        ("hand_back", JAKE, "target_y 3.00 handed back to the run's 1.50, from trial 4")]


def test_a_hand_back_of_a_setting_the_run_gives_no_value_leaves_it_without_one(tmp_path):
    """The C3 plan's call 23: the run's own value is the task's start under the run's, "absent if
    neither". `spare` declares no start, the run gives none and nothing reads it (a setting that
    places a stimulus and holds no value is refused before the run starts, XC-415); a person sets
    it, then hands it back, and from the next trial the setting holds no value again, as the run
    began: absent from the trial's values and the line's `params`."""
    path = _edited(
        _sessions.varied_task(tmp_path),
        ('        Param("target_x", unit="deg", low=-16.0, high=16.0, start=10.0),',
         '        Param("spare", unit="deg", low=0.0, high=1.0),\n'
         '        Param("target_x", unit="deg", low=-16.0, high=16.0, start=10.0),'),
        tail=("from wl_xcon.task import NEITHER, NOT_DIFFICULTY, Meaning\n"
              "TASK = _dataclasses.replace(TASK, meanings={\n"
              "    **TASK.meanings,\n"
              "    'spare': Meaning(NOT_DIFFICULTY, NEITHER, note='read by nothing')})\n"))
    link = _Drained({2: [SetParameter(name="spare", value=0.5, by=JAKE)],
                     4: [HandBack(name="spare", by=JAKE)]})
    session = _session(_spec(tmp_path, path, trials=6), link)

    session.run()

    assert session.refusals == []
    assert ["spare" in line["params"] for line in _lines(session)] == [
        False, False, True, True, False, False]
    (_, handed) = _changes(session)
    assert (handed["kind"], handed["now"], handed["to"]) == ("hand_back", None, "run")
    assert "spare" not in session.spec.values
    ((_, _, said),) = _fed(session, "hand_back")
    assert said.endswith(" handed back to the run, which gives it no value, from trial 4")


def test_typing_the_old_value_back_does_not_hand_it_back(tmp_path):
    """TSK-19 and the C2b plan's Appendix B item 1, as Q7a revises it: typing the condition's own
    value back still holds the setting (its trials stay `live` and `overridden`); the *hand back*
    button gives it back."""
    link = _Drained({2: [SetParameter(name="target_x", value=12.0, by=JAKE)],
                     4: [SetParameter(name="target_x", value=5.0, by=JAKE)],
                     6: [HandBack(name="target_x", by=JAKE)]})
    session = _session(_spec(tmp_path, "tasks/fixation_detection.py", blocks=[
        Block("b", [Condition("near", {"target_x": 5.0}, target=8)])]), link)

    session.run()

    assert [(line["params"]["target_x"], line["live"], line["overridden"])
            for line in _lines(session)] == (
        [(5.0, [], [])] * 2 + [(12.0, ["target_x"], ["target_x"])] * 2
        + [(5.0, ["target_x"], ["target_x"])] * 2 + [(5.0, [], [])] * 2)
    assert [(row["kind"], row["was"], row["now"]) for row in _changes(session)] == [
        ("set", 10.0, 12.0), ("set", 12.0, 5.0), ("hand_back", 5.0, None)]


#: The task draws the fixation hold, and block `own` replaces its draw; the task draws the target
#: window too, up to 6.5°, past the 6° it declares (as a run's pre-flight would warn).
OWN = dict(
    draws=('{"fix_hold": Uniform(0.2, 0.4, repeat=FRESH), '
           '"target_window": Uniform(5.5, 6.5, repeat=FRESH)}'),
    plans=('{"p": Plan([Block("plain", [Condition("c", {}, target=3)]), '
           'Block("own", [Condition("o", {}, target=3)], '
           'draws={"fix_hold": Uniform(0.5, 0.6, repeat=FRESH)}), '
           'Block("again", [Condition("a", {}, target=3)])])}'),
)


def test_a_live_range_draws_every_trial_inside_it_naming_its_change(tmp_path):
    """Q7b and the C3 plan's call 22: a range changed live changes the draw the open block uses,
    its own or the task's, for the rest of the run wherever that draw applies. In block `plain`
    the task's draw narrows to 0.25 to 0.3 s, so `plain`'s and `again`'s later trials draw from
    it; in block `own` its own draw takes a new highest, its lowest kept, so only `own`'s do. Every
    trial is drawn, never `live` or `overridden`, from the range in force, keyed as ever, and
    names its change (`drawn`). Each range is a change row: its draws before and after with every
    field, whose draw it changed (`from`, `block`), and the setting's meaning, `went` the way the
    new range went judged as a whole against the range the task writes (the PI, 2026-10-31,
    Appendix B item 18): narrowed to 0.25 to 0.3 s, its lowest raised and its highest lowered,
    the hold harder as it rises, a mixed change, counted easier; `own`'s highest raised to 0.7 s
    is harder, its lowest kept. A range inside its setting's
    declared range is checked no further (`_beyond_range` is for an extreme outside it), so no
    warning the target window's draw would give elsewhere is accepted in its name."""
    path = _sessions.varied_task(tmp_path, **OWN)
    task = _load_task(path)
    declared, own = task.draws["fix_hold"], task.plans["p"].blocks[1].draws["fix_hold"]
    narrowed, widened = Uniform(0.25, 0.3, repeat=FRESH), Uniform(0.5, 0.7, repeat=FRESH)
    task_key, own_key = ("task", "fix_hold"), ("block", "own", "fix_hold")
    # One drain before each trial and one as the plan moves on: the 2nd is before plain's second
    # trial, the 6th before own's second.
    link = _Drained({2: [SetRange(name="fix_hold", numbers={"low": 0.25, "high": 0.3}, by=JAKE)],
                     6: [SetRange(name="fix_hold", numbers={"high": 0.7}, by=JAKE)]})
    session = _session(_spec(tmp_path, path, plan="p"), link)

    session.run()

    assert session.refusals == []
    expected = ([("plain", declared, task_key, "task")] * 2 + [("plain", narrowed, task_key, 1)]
                + [("own", own, own_key, "block")] * 2 + [("own", widened, own_key, 2)]
                + [("again", narrowed, task_key, 1)] * 3)
    lines = _lines(session)
    assert [(line["block"], line["drawn"], line["live"], line["overridden"])
            for line in lines] == [(block, {"fix_hold": source, "target_window": "task"}, [], [])
                                   for block, _, _, source in expected]
    assert [line["params"]["fix_hold"] for line in lines] == [
        variation.draw(drawn, SEED, line["index"], key)
        for line, (_, drawn, key, _) in zip(lines, expected)]
    easier, harder = ({**FIX_HOLD, "went": went, "step": None} for went in ("easier", "harder"))
    assert [_without_instants(row) for row in _changes(session)] == [
        {"change": 1, "kind": "range", "name": "fix_hold", "was": variation.recorded(declared),
         "now": variation.recorded(narrowed), "from": "task", "block": None, "by": BY,
         "trial_number": 3, "run": 0, "meaning": easier, "offered": [], "odds": None,
         "event_code": PARAM_CHANGED, "sequence": 1},
        {"change": 2, "kind": "range", "name": "fix_hold", "was": variation.recorded(own),
         "now": variation.recorded(widened), "from": "block", "block": "own", "by": BY,
         "trial_number": 6, "run": 0, "meaning": harder, "offered": [], "odds": None,
         "event_code": PARAM_CHANGED, "sequence": 2},
    ]
    assert session._ranges == {task_key: (narrowed, 1), own_key: (widened, 2)}
    assert _rows(session, "warnings.jsonl") == []
    assert _fed(session, "range") == [
        ("range", JAKE,
         "the task's draw of 'fix_hold' → uniform from 0.25 s to 0.3 s, from trial 2"),
        ("range", JAKE,
         "block 'own''s draw of 'fix_hold' → uniform from 0.5 s to 0.7 s, from trial 5")]


def test_a_range_is_judged_as_a_whole_against_the_range_the_task_writes():
    """The PI, 2026-10-31, on the engine C3 plan's Appendix B, item 18, "Judge the range as a whole
    (Recommended)": a range changed live counts as easier than the range written where it reaches
    any value easier than that allows -- for a uniform, either end moved the easier way, a mixed
    change among them -- and where which way cannot be read, doubt counted as easier
    (`variation.easier_range`, `True` or `None`); where each number that moved moved the harder
    way, or none moved, it does not (`False`). A normal's mean and cut, and a wait's shortest,
    average and longest, are read as a uniform's ends are, a normal's cut filled from its
    setting's range; a normal's spread changed moves its values both ways, mixed; a setting that
    is no difficulty setting never counts. Read the other way round, `True` says it moved the
    harder way somewhere, as its change row says (`Session._range_went`)."""
    from wl_xcon.task import (BACKGROUND, CLEAR_CUT, CRITERION, EASIER, HARDER, NEITHER,
                              NOT_DIFFICULTY, STIMULUS, Meaning, NonAging, Param,
                              TruncatedNormal)
    wider = Meaning(CLEAR_CUT, CRITERION, raising=EASIER)
    written = Uniform(1.5, 2.5, repeat=FRESH)

    def judged(low, high, meaning=wider):
        return variation.easier_range(meaning, Uniform(low, high, repeat=FRESH), written)

    assert [judged(1.5, 3.0), judged(2.0, 2.5), judged(1.0, 3.0), judged(2.0, 2.2)] == [True] * 4
    assert [judged(1.0, 2.5), judged(0.5, 1.0), judged(1.5, 2.5)] == [False] * 3
    assert judged(1.0, 2.0, Meaning(CLEAR_CUT, CRITERION, raising=HARDER)) is True
    assert judged(1.0, 2.0, Meaning(CLEAR_CUT, STIMULUS, raising=EASIER,
                                     relative_to=BACKGROUND)) is None
    assert judged(1.5, 3.0, Meaning(NOT_DIFFICULTY, NEITHER)) is False

    window = Param("w", unit="deg", low=0.5, high=1.5)
    normal = TruncatedNormal(1.0, 0.1, repeat=FRESH)
    assert variation.easier_range(
        wider, TruncatedNormal(1.0, 0.1, low=0.5, repeat=FRESH), normal, window) is False
    assert variation.easier_range(
        wider, TruncatedNormal(1.0, 0.2, repeat=FRESH), normal, window) is True
    assert variation.easier_range(
        wider, TruncatedNormal(0.9, 0.1, repeat=FRESH), normal, window) is False
    assert variation.easier_range(
        wider, normal, TruncatedNormal(0.9, 0.1, repeat=FRESH), window) is True
    longer = Meaning(CLEAR_CUT, CRITERION, raising=HARDER)
    wait = NonAging(0.75, 1.0, 1.25, repeat=FRESH)
    assert variation.easier_range(longer, NonAging(0.75, 1.0, 1.5, repeat=FRESH), wait) is False
    assert variation.easier_range(longer, wait, NonAging(0.75, 1.0, 1.5, repeat=FRESH)) is True


def test_a_conditions_own_range_a_weighted_set_a_list_a_direction_and_a_setting_not_live_are_not_changed_live(
        tmp_path):
    """The PI, 2026-10-30, "Not in C3" (a condition's own range: "set one value over it (marked)
    or hand it back"); the C3 plan's call 22 (review M-4, M-15): a weighted set or a list (XC-443),
    a direction's range (XC-445) and a setting declared not live-editable are not changed live;
    nor a setting the open block does not draw, a number its kind does not change live, numbers
    that cannot be drawn, or a name the task does not declare. Each is refused with its sentence,
    and nothing changes: no row, no range in force, every trial drawn as declared."""
    path = _directed(tmp_path, (
        '{"target_dir": Uniform(-45.0, 45.0, repeat=FRESH), '
        '"target_x": Weighted((-5.0, 5.0), (1, 1), repeat=FRESH), '
        '"target_y": Listed((0.0, 2.0), repeat=FRESH), '
        '"target_window": Uniform(2.5, 3.5, repeat=FRESH), '
        '"fix_luminance": Uniform(30.0, 50.0, repeat=FRESH)}'),
        ('{"p": Plan([Block("b", [Condition("r", '
         '{"fix_hold": Uniform(0.25, 0.35, repeat=FRESH)}, target=4)])])}'))
    offered = [("fix_hold", {"low": 0.3}), ("target_x", {"low": -6.0}),
               ("target_y", {"low": 1.0}), ("target_dir", {"low": -30.0}),
               ("target_window", {"low": 2.0}), ("fix_acquisition", {"low": 3.0}),
               ("fix_luminance", {"mean": 40.0}), ("fix_luminance", {"low": 60.0}),
               ("fix_holdd", {"low": 0.3})]
    link = _Drained({2: [SetRange(name=name, numbers=numbers, by=JAKE)
                         for name, numbers in offered]})
    session = _session(_spec(tmp_path, path, plan="p"), link)

    session.run()

    assert session.refusals == [(name, JAKE, f"the range of {name!r} is not changed: {why}")
                                for name, why in [
        ("fix_hold", "in block 'b' it is drawn from condition 'r''s own range, and a condition's "
                     "own range is not changed live in engine build C3 (the PI, 2026-10-30, \"Not "
                     "in C3\"): set one value over it, or hand it back; editing it is a condition "
                     "edit, the rig-edit build's"),
        ("target_x", "it is drawn from a Weighted, which is not changed live in engine build C3 "
                     "(XC-443): only a Uniform's, a TruncatedNormal's and a NonAging's numbers "
                     "are"),
        ("target_y", "it is drawn from a Listed, which is not changed live in engine build C3 "
                     "(XC-443): only a Uniform's, a TruncatedNormal's and a NonAging's numbers "
                     "are"),
        ("target_dir", "it places a direction, whose range is not changed live in engine build C3 "
                       "(XC-445): the task declares it in its own terms, and the console shows it "
                       "from 0 to 360"),
        ("target_window", "it is declared not live-editable by this task"),
        ("fix_acquisition", "block 'b' does not draw it, by its own draw or the task's"),
        ("fix_luminance", "'mean' is no number of a Uniform changed live; its live numbers are "
                          "low, high"),
        ("fix_luminance", "uniform from 60.0 cd/m2 to 50.0 cd/m2 cannot be drawn: its lowest, "
                          "60.0, is above its highest, 50.0; write the lowest first"),
        ("fix_holdd", "it is not a setting this task declares"),
    ]]
    assert (_changes(session), session._ranges, session._pending) == ([], {}, [])
    assert {tuple(sorted(line["drawn"].items())) for line in _lines(session)} == {(
        ("fix_hold", "condition"), ("fix_luminance", "task"), ("target_dir", "task"),
        ("target_window", "task"), ("target_x", "task"), ("target_y", "task"))}


def test_a_live_range_past_its_declared_range_is_warned_or_refused_as_a_value_is(tmp_path):
    """TSK-51 and the C3 spec §6 ("numbers outside the declared range are re-checked widened, as a
    value is"): each extreme of a new range outside its setting's declared range is checked as a
    typed value outside it is (`Session._beyond_range`). `visual_search`'s ring drawn from 3°,
    below its 5°, crowds its 12 objects: refused, saying why, and nothing of it written. A
    fixation hold drawn up to 2.5 s, past its 2 s, breaks nothing: the range applies, its warning
    accepted by who sent it and said on the feed."""
    blocks = [Block("drawn", [Condition("any", {}, target=4)],
                    draws={"array_eccentricity": Uniform(6.0, 9.0, repeat=FRESH),
                           "fix_hold": Uniform(0.2, 0.4, repeat=FRESH)})]
    link = _Drained({2: [SetRange(name="array_eccentricity", numbers={"low": 3.0}, by=JAKE),
                         SetRange(name="fix_hold", numbers={"high": 2.5}, by=JAKE)]})
    session = _session(_spec(tmp_path, "tasks/visual_search.py", blocks=blocks,
                             values={**SEARCHED, "set_size": 12}), link, world=None)

    session.run()

    assert session.refusals == [("array_eccentricity", JAKE, (
        "the range of 'array_eccentricity' is not changed: 'array_eccentricity' at 3 is outside "
        "its declared range, and with the range widened to it the load-time checks refuse it: "
        "crowded-array: with 'array_eccentricity' at 3, outside its declared range: array "
        "'search' can put 12 objects on a 3° ring, 1.55° apart, with windows of 1° radius; "
        "adjacent objects would overlap and a saccade to one would be scored against another; the "
        "previous value stands"))]
    warned = ("'fix_hold' is 2.5 s, outside the [0.05, 2.0] the task declares, so the task was "
              "not designed for it: its load-time checks were proved only over its declared "
              "range, and were run again with the range widened to 2.5")
    assert [(row["code"], row["by"], row["detail"]) for row in
            _rows(session, "warnings.jsonl")] == [("outside-range", BY, warned)]
    assert _fed(session, "warning") == [("warning", JAKE, f"outside-range: {warned}")]
    (row,) = _changes(session)
    assert (row["kind"], row["block"], row["now"]) == (
        "range", "drawn", variation.recorded(Uniform(0.2, 2.5, repeat=FRESH)))
    lines = _lines(session)
    assert len(lines) > 2 and all(
        line["drawn"] == {"array_eccentricity": "block", "fix_hold": 1}
        and 0.2 <= line["params"]["fix_hold"] <= 2.5 for line in lines[2:])


def test_an_impossible_hand_back_or_range_is_refused_and_leaves_no_warning_written(tmp_path):
    """The C3 spec §9 ("each change as offered (a value, range, hand-back or revert) against every
    condition of the run's blocks and the draws in force"): with a response deadline of 0.5 s, a
    target hold drawn up to 1.5 s leaves no time to answer on some trials, so the range is refused
    -- judged before its extreme past the declared 1 s, so no warning is written (the outline
    review's I-1). Later a person holds the deadline at 2 s and a target hold of 0.8 s; handing
    the deadline back to the run's 0.5 s would leave no time to answer, and is refused, while
    handing the target hold back to its draw is not."""
    path = _deadline(tmp_path, '{"target_hold": Uniform(0.1, 0.3, repeat=FRESH)}')
    link = _Drained({2: [SetRange(name="target_hold", numbers={"high": 1.5}, by=JAKE),
                         SetParameter(name="response_deadline", value=2.0, by=JAKE),
                         SetParameter(name="target_hold", value=0.8, by=JAKE)],
                     4: [HandBack(name="response_deadline", by=JAKE),
                         HandBack(name="target_hold", by=JAKE)]})
    session = _session(_spec(tmp_path, path, trials=6, values={
        "target_appearance": None, "response_deadline": 0.5}), link)

    session.run()

    unpaid = ("state 'verify' ends the trial NO_RESPONSE after `response_deadline`, 0.5 s, while "
              "its 'target' hold takes `target_hold`, {held}: the hold starts only when the gaze "
              "arrives, so it never finishes and no answer can be paid (XC-343); give the timeout "
              "more than {more}, or hold in a state of its own bounded longer, as the reference "
              "tasks hold their target")
    assert session.refusals == [
        ("target_hold", JAKE, "the range of 'target_hold' is not changed: it would leave trials "
                              "no animal can get right, in session: session (impossible-trial): "
                              "block 'session', condition 'session': "
                              + unpaid.format(held="up to 1.5 s", more="1.5 s")),
        ("response_deadline", JAKE, "'response_deadline' is not handed back: it would leave "
                                    "trials no animal can get right, in session: session "
                                    "(impossible-trial): block 'session', condition 'session': "
                                    + unpaid.format(held="0.8 s", more="0.8 s")),
    ]
    assert _rows(session, "warnings.jsonl") == []
    assert [(row["kind"], row["name"], row.get("to")) for row in _changes(session)] == [
        ("set", "response_deadline", None), ("set", "target_hold", None),
        ("hand_back", "target_hold", "draw")]
    assert session._edited == frozenset({"response_deadline"})


@pytest.mark.parametrize("act, broken", [
    ("hand_back", "impossible"), ("range", "impossible"), ("hand_back", "possible"),
    ("range", "possible"), ("range", "undrawable")])
def test_a_check_that_raises_inside_a_hand_back_or_a_range_refuses_it_and_the_session_runs_on(
        tmp_path, monkeypatch, act, broken):
    """Review Focus 5, the acts' half (the outline review's I-1; the C3 plan's call 20): the two
    acts run beside the pause, outside `_command`'s listed `try`, so each refuses its own faults.
    A check that raises -- `check.impossible`, as `_possible` meets it and says it could not run;
    `_possible` itself; `check.undrawable` -- refuses the hand-back or the range, saying so, and
    the session runs to its end with nothing changed. The stand-ins are this file's own: each
    raises from the trial after a person's value was checked, so that value is held first, and a
    hand-back holds no name for Task 12's stand-in to raise on."""
    path = _sessions.varied_task(tmp_path, draws='{"fix_hold": Uniform(0.2, 0.4, repeat=FRESH)}')
    offered = (HandBack(name="target_x", by=JAKE) if act == "hand_back"
               else SetRange(name="fix_hold", numbers={"high": 0.5}, by=JAKE))
    link = _Drained({2: [SetParameter(name="target_x", value=12.0, by=JAKE)], 3: [offered]})

    def raising(*args, **kwargs):
        raise ZeroDivisionError("division by zero")

    def world(trial, values, index):
        if index == 1:
            # After the person's value was offered (the 2nd drain), before the act is (the 3rd).
            if broken == "possible":
                monkeypatch.setattr(session, "_possible", raising)
            else:
                monkeypatch.setattr(taskd, broken, raising)
        return _right(values)

    session = _session(_spec(tmp_path, path, trials=5), link, world=world)

    session.run()

    name = offered.name
    what = (f"{name!r} is not handed back" if act == "hand_back"
            else f"the range of {name!r} is not changed")
    whole = "the hand-back" if act == "hand_back" else "the range"
    assert session.stop_kind == "completed"
    assert session.refusals == [(name, JAKE, (
        f"{what}: the check for trials no animal can get right could not be run "
        f"(ZeroDivisionError: division by zero)" if broken == "impossible"
        else f"{whole} of {name!r} could not be checked (ZeroDivisionError: division by zero), "
             f"so it is refused and the session runs on"))]
    assert [row["kind"] for row in _changes(session)] == ["set"]
    assert (session._edited, session._ranges, session._pending) == (
        frozenset({"target_x"}), {}, [])
    assert {line["drawn"]["fix_hold"] for line in _lines(session)} == {"task"}


def test_both_sent_while_paused_apply_after_the_resume(tmp_path):
    """The P4d-2b spec §5.1 ("trials run again from the next pass of the loop, with any setting
    staged while paused applied first"), for the two new acts: `_hold` drains through `_command`,
    so a hand-back and a range sent while paused are offered then, wait (`_pending`), and apply as
    the session resumes, before its next trial, each its own change, in the order sent."""
    path = _sessions.varied_task(tmp_path, draws='{"fix_hold": Uniform(0.2, 0.4, repeat=FRESH)}')
    waiting = []

    class Watched(_Drained):
        def drain(self) -> list:
            if self.drains == 4:
                # As the 5th drain, the resume's, begins: what waited while paused.
                waiting.append((list(session._pending), session._edited, dict(session._ranges)))
            return super().drain()

    link = Watched({1: [SetParameter(name="target_x", value=12.0, by=JAKE)],
                    3: [Pause(by=JAKE)],
                    4: [HandBack(name="target_x", by=JAKE),
                        SetRange(name="fix_hold", numbers={"low": 0.3}, by=JAKE)],
                    5: [Resume(by=JAKE)]})
    session = _session(_spec(tmp_path, path, trials=4), link)

    session.run()

    assert session.refusals == []
    ((pending, edited, ranges),) = waiting
    assert [(act.kind, act.name) for act in pending] == [
        ("hand_back", "target_x"), ("range", "fix_hold")]
    assert (edited, ranges) == (frozenset({"target_x"}), {})
    kinds = [kind for kind, _, _, _ in session.controls]
    assert kinds.index("pause") < kinds.index("resume") < kinds.index("hand_back") < kinds.index(
        "range")
    assert [(line["params"]["target_x"], line["live"], line["drawn"])
            for line in _lines(session)] == [
        (10.0, [], {"fix_hold": "task"}), (12.0, ["target_x"], {"fix_hold": "task"}),
        (10.0, [], {"fix_hold": 3}), (10.0, [], {"fix_hold": 3})]
    assert [(row["change"], row["kind"], row["trial_number"]) for row in _changes(session)] == [
        (1, "set", 2), (2, "hand_back", 3), (3, "range", 3)]


def test_a_hand_back_or_range_drained_with_a_stop_is_dropped_and_said(tmp_path):
    """The b3a-1 plan's decision 2, for the two new acts (the outline review's M-5): between a
    `wlx taskd` session's runs nothing applies what was offered, so a hand-back and a range
    drained with the stop that ends a run are dropped, each said on the feed in the order offered,
    and neither is written."""
    path = _sessions.varied_task(tmp_path, draws='{"fix_hold": Uniform(0.2, 0.4, repeat=FRESH)}')
    link = _Drained({1: [SetParameter(name="target_x", value=12.0, by=JAKE)],
                     2: [HandBack(name="target_x", by=JAKE),
                         SetRange(name="fix_hold", numbers={"high": 0.5}, by=JAKE),
                         Stop(by=JAKE)]})
    session = _session(_spec(tmp_path, "", trials=0, values={}), link, service=True)

    session.run(RunSpec(task=str(path), trials=5, seed=SEED, values={"target_appearance": None}))

    assert (session.phase, session._pending, session._ranges) == ("between_runs", [], {})
    assert _fed(session, "hand_back", "range") == [
        ("hand_back", JAKE,
         "target_x 12.00 handed back to the run's 10.00 was not applied: run 1 ended first"),
        ("range", JAKE, "the task's draw of 'fix_hold' → uniform from 0.2 s to 0.5 s was not "
                        "applied: run 1 ended first")]
    assert [(row["kind"], row["name"]) for row in _changes(session)] == [("set", "target_x")]


#: One setting a repeat takes the same, one it draws fresh (as `tests/test_draws_in_runs.py`'s).
SAME_FRESH = ('{"target_x": Uniform(-10.0, 10.0, repeat=SAME), '
              '"fix_luminance": Uniform(20.0, 60.0, repeat=FRESH)}')


def test_a_same_value_survives_a_long_drum_and_a_range_changed_meanwhile(tmp_path):
    """Review Focus 1 (the PI, 2026-10-30: Q3, "Per drawn setting, required"; "Follow same/fresh";
    Q7b): the run's first trial breaks and waits to be shown again; a trainer switches drumming on,
    and the next trial breaks on twelve tries in a row, its drum holding that waiting repeat past
    its window, while both draws' ranges change live between its tries. Every try of the drummed
    trial, and the late repeat, carry the `same` value and source of the trial they show again
    (`_kept`, never drawn again); every trial draws its `fresh` value on its own number from the
    range in force, naming its change once it changed; and `_kept` never drops an entry a
    waiting repeat names."""
    path = _sessions.varied_task(tmp_path, draws=SAME_FRESH)
    task = _load_task(path)
    moved = {"target_x": Uniform(12.0, 14.0, repeat=SAME),
             "fix_luminance": Uniform(70.0, 80.0, repeat=FRESH)}
    tries = [0]
    kept = []

    def world(trial, values, index):
        draw = session._scheduler.drawn
        kept.append(session._scheduler.waiting <= set(session._kept))
        if index == 0:
            return BREAK
        if index == 1 or (draw.drummed and tries[0] < 12):
            tries[0] += 1
            return BREAK
        return _right(values)

    # The 2nd drain is before the second trial; the 6th before the sixth, a drummed try.
    link = _Drained({2: [Drum(scope="block", by=JAKE)],
                     6: [SetRange(name="target_x", numbers={"low": 12.0, "high": 14.0}, by=JAKE),
                         SetRange(name="fix_luminance", numbers={"low": 70.0, "high": 80.0},
                                  by=JAKE)]})
    session = _session(_spec(tmp_path, path, blocks=[
        Block("b", [Condition("a", {}, target=2), Condition("d", {}, target=2)])]), link,
        world=world)

    session.run()

    assert session.refusals == [] and all(kept)
    lines = _lines(session)
    by_index = {line["index"]: line for line in lines}
    assert [line["index"] for line in lines if line["drummed"]] == list(range(2, 14))
    (late,) = [line for line in lines if line["repeat_of"] == 0]
    assert late["index"] > 13 and not late["drummed"], "held past its window by the drum"
    for line in lines:
        first = line
        while first["repeat_of"] is not None:
            first = by_index[first["repeat_of"]]
        x_draw, x_from = ((moved["target_x"], 2) if first["index"] > 5
                          else (task.draws["target_x"], "task"))
        lum_draw, lum_from = ((moved["fix_luminance"], 3) if line["index"] > 5
                              else (task.draws["fix_luminance"], "task"))
        assert line["drawn"] == {"target_x": x_from, "fix_luminance": lum_from}
        assert line["params"]["target_x"] == variation.draw(
            x_draw, SEED, first["index"], ("task", "target_x"))
        assert line["params"]["fix_luminance"] == variation.draw(
            lum_draw, SEED, line["index"], ("task", "fix_luminance"))
    assert session._kept == {}, "nothing kept once no repeat waits"


def test_a_change_offered_after_a_pending_hand_back_or_range_is_judged_over_it(tmp_path):
    """The C3 spec §9 ("each change as offered ... against every condition of the run's blocks and
    the draws in force"), across one drain: a change offered after a hand-back or a range that has
    not applied yet is judged over it (`Session._ahead`), as one offered after a staged value is.
    Target holds drawn up to 0.9 s leave time to answer while a person holds the deadline at 2 s,
    so that range is offered; then handing the deadline back to its 0.6 s start, or setting it to
    0.5 s, would leave no time on them, and both are refused. Later the range goes back to 0.1 to
    0.3 s and the deadline is handed back, and a target hold of 0.8 s offered after them is
    refused: the deadline it would meet is the run's again, not the person's."""
    path = _deadline(tmp_path, '{"target_hold": Uniform(0.1, 0.3, repeat=FRESH)}')
    task_key = ("task", "target_hold")
    link = _Drained({2: [SetParameter(name="response_deadline", value=2.0, by=JAKE)],
                     3: [SetRange(name="target_hold", numbers={"high": 0.9}, by=JAKE),
                         HandBack(name="response_deadline", by=JAKE),
                         SetParameter(name="response_deadline", value=0.5, by=JAKE)],
                     5: [SetRange(name="target_hold", numbers={"high": 0.3}, by=JAKE),
                         HandBack(name="response_deadline", by=JAKE),
                         SetParameter(name="target_hold", value=0.8, by=JAKE)]})
    session = _session(_spec(tmp_path, path, trials=7), link)

    session.run()

    assert [(name, why.split(": it would leave trials no animal can get right, in ")[0])
            for name, _, why in session.refusals] == [
        ("response_deadline", "'response_deadline' is not handed back"),
        ("response_deadline", "'response_deadline' at 0.5 is refused, and the previous value "
                              "stands"),
        ("target_hold", "'target_hold' at 0.8 is refused, and the previous value stands")]
    rows = _changes(session)
    assert [(row["kind"], row["name"], row["was"], row["now"]) for row in rows] == [
        ("set", "response_deadline", 0.6, 2.0),
        ("range", "target_hold", variation.recorded(Uniform(0.1, 0.3, repeat=FRESH)),
         variation.recorded(Uniform(0.1, 0.9, repeat=FRESH))),
        ("range", "target_hold", variation.recorded(Uniform(0.1, 0.9, repeat=FRESH)),
         variation.recorded(Uniform(0.1, 0.3, repeat=FRESH))),
        ("hand_back", "response_deadline", 2.0, 0.6)]
    assert [(line["params"]["response_deadline"], line["drawn"]) for line in _lines(session)] == [
        (0.6, {"target_hold": "task"})] * 2 + [(2.0, {"target_hold": "task"})] + [
        (2.0, {"target_hold": 2})] * 2 + [(0.6, {"target_hold": 3})] * 2
    assert session._ranges == {task_key: (Uniform(0.1, 0.3, repeat=FRESH), 3)}


def test_a_value_outside_its_range_offered_after_a_pending_range_is_checked_with_its_extremes(
        tmp_path):
    """The C3 spec §11 ("Live, `Session._beyond_range` learns conditions and draws"), across one
    drain: a range offered and not yet applied is in force for a value offered after it. Block
    `drawn` draws `visual_search`'s ring from 6° to 9°; a person widens it to 4°, below its
    declared 5° (warned: six objects fit there), then asks for 13 objects, past the 12 the task
    declares. 13 fit on the 8° ring and on the 6° to 9° declared, not on the 4° the range just
    offered reaches, so they are refused, naming the range's extreme."""
    blocks = [Block("drawn", [Condition("any", {}, target=4)],
                    draws={"array_eccentricity": Uniform(6.0, 9.0, repeat=FRESH)})]
    link = _Drained({2: [SetRange(name="array_eccentricity", numbers={"low": 4.0}, by=JAKE),
                         SetParameter(name="set_size", value=13, by=JAKE)]})
    session = _session(_spec(tmp_path, "tasks/visual_search.py", blocks=blocks,
                             values=dict(SEARCHED)), link, world=None)

    session.run()

    (refusal,) = session.refusals
    assert refusal[:2] == ("set_size", JAKE)
    assert refusal[2].startswith("'set_size' at 13 is outside its declared range, and with the "
                                 "range widened to it the load-time checks refuse it: "
                                 "crowded-array: ")
    assert refusal[2].endswith(" (on the trials of block 'drawn', condition 'any', block "
                               "'drawn''s draw of 'array_eccentricity' at 4); the previous value "
                               "stands")
    assert [row["code"] for row in _rows(session, "warnings.jsonl")] == ["outside-range"]
    assert [(row["kind"], row["name"]) for row in _changes(session)] == [
        ("range", "array_eccentricity")]
    assert session.spec.values["set_size"] == 6


def test_neither_a_hand_back_nor_a_range_touches_a_reward_size(tmp_path):
    """The engine C3 plan's Appendix A, item 5: neither act passes through `Session.set`, and
    neither can touch a reward. A reward size is never held as a task setting -- a person's value
    for one is a ceiling's, staged and applied by `set`'s and `bounds`' own branch -- and is never
    drawn, so a hand-back or a range naming one is refused first, by its name, even where the task
    declares a setting of that name; the reward size the person set stands, and only its own row
    is written."""
    link = _Drained({2: [SetParameter(name="reward_correct", value=0.2, by=JAKE)],
                     3: [HandBack(name="reward_correct", by=JAKE),
                         SetRange(name="reward_correct", numbers={"low": 0.1}, by=JAKE)]})
    session = _session(_spec(tmp_path, _ceiling(tmp_path), trials=5), link)

    session.run()

    assert session.refusals == [
        ("reward_correct", JAKE, "'reward_correct' is not handed back: it is a welfare ceiling, "
                                 "never a task setting a person holds"),
        ("reward_correct", JAKE, "the range of 'reward_correct' is not changed: it is a welfare "
                                 "ceiling, which is never drawn"),
    ]
    assert session.spec.bounds.value("reward_correct") == 0.2
    assert [(row["kind"], row["name"], row["meaning"]) for row in _changes(session)] == [
        ("set", "reward_correct", None)]
    assert (session._edited, session._ranges, session._pending) == (frozenset(), {}, [])


def test_staged_values_and_pending_acts_apply_in_the_order_offered_each_its_own_change(tmp_path):
    """The C3 plan's call 19, the applier's second step: `_apply_staged` applies the values staged
    and the hand-backs and ranges pending in the order they were offered, each its own change id,
    `PARAM_CHANGED` strobe and `sequence`. A hand-back offered after a value in the same drain
    hands that value back, and a second one then finds nothing to hand back. A range whose draw is
    `None`, as a revert to a run's start will offer one (the C3 plan's Task 14), puts the declared
    draw back in force, its trials naming it again."""
    path = _sessions.varied_task(tmp_path, draws='{"fix_hold": Uniform(0.2, 0.4, repeat=FRESH)}')
    declared = _load_task(path).draws["fix_hold"]
    narrowed = Uniform(0.2, 0.3, repeat=FRESH)

    def world(trial, values, index):
        if index == 3:
            session._pending.append(taskd.Pending(
                "range", "fix_hold", was=variation.recorded(narrowed),
                now=variation.recorded(declared), by=JAKE, after=0, key=("task", "fix_hold"),
                draw=None))
        return _right(values)

    link = _Drained({2: [SetParameter(name="target_x", value=12.0, by=JAKE),
                         SetRange(name="fix_hold", numbers={"high": 0.3}, by=JAKE),
                         SetParameter(name="target_y", value=2.0, by=JAKE),
                         HandBack(name="target_x", by=JAKE), HandBack(name="target_x", by=JAKE)]})
    session = _session(_spec(tmp_path, path, trials=6), link, world=world)

    session.run()

    assert session.refusals == [("target_x", JAKE, "'target_x' is not handed back: no person "
                                                   "holds it in this run, so there is nothing to "
                                                   "hand back")]
    rows = _changes(session)
    assert [(row["change"], row["sequence"], row["kind"], row["name"], row["was"], row["now"])
            for row in rows] == [
        (1, 1, "set", "target_x", 10.0, 12.0),
        (2, 2, "range", "fix_hold", variation.recorded(declared), variation.recorded(narrowed)),
        (3, 3, "set", "target_y", 0.0, 2.0),
        (4, 4, "hand_back", "target_x", 12.0, 10.0),
        (5, 5, "range", "fix_hold", variation.recorded(narrowed), variation.recorded(declared))]
    assert [row["trial_number"] for row in rows] == [3, 3, 3, 3, 5]
    assert session.card.codes.count(PARAM_CHANGED) == 5
    assert [(line["params"]["target_x"], line["live"], line["drawn"])
            for line in _lines(session)] == (
        [(10.0, [], {"fix_hold": "task"})] * 2 + [(10.0, ["target_y"], {"fix_hold": 2})] * 2
        + [(10.0, ["target_y"], {"fix_hold": "task"})] * 2)
    assert session._ranges == {}
    assert [said for _, _, said in _fed(session, "range")][-1] == (
        "the task's draw of 'fix_hold' → as declared, from trial 4")


#: A drummed block of one condition: a trial not right comes straight back, keeping its `same`
#: values.
DRUMMED = '{"p": Plan([Block("b", [Condition("c", {}, target=3)], drum=True)])}'
#: The refusal of a 0.7 s target hold that a deadline of `deadline` would leave no time for.
HELD_TOO_LONG = (
    "'target_hold' at 0.7 is refused, and the previous value stands: it would leave trials no "
    "animal can get right, in b: c (impossible-trial): block 'b', condition 'c': state 'verify' "
    "ends the trial NO_RESPONSE after `response_deadline`, {deadline}, while its 'target' hold "
    "takes `target_hold`, 0.7 s: the hold starts only when the gaze arrives, so it never "
    "finishes and no answer can be paid (XC-343); give the timeout more than 0.7 s, or hold in "
    "a state of its own bounded longer, as the reference tasks hold their target; a trial "
    "waiting to be shown again, or the next one drawn before the change applies, keeps the value "
    "it drew for a setting declared same: clear the waiting trial, switch drumming off or pause, "
    "then make the change")


def _kept_session(tmp_path, repeat: str, script: dict, *, broken: int = 1) -> Session:
    """The deadline task drawing its response deadline from 0.5 to 1 s, `repeat` as given, in a
    drummed block, its target hold 0.2 s: the first trial draws a deadline under 0.7 s (the
    seed's); the first `broken` trials break, and every later one is right where it can be. A
    stop at the 40th drain caps a session whose trial no animal can get right, which the drum
    would otherwise bring back until the out-of-cage limit."""
    path = _deadline(tmp_path, f'{{"response_deadline": Uniform(0.5, 1.0, repeat={repeat})}}',
                     DRUMMED)
    link = _Drained({**script, 40: [Stop(by=JAKE)]})

    def world(trial, values, index):
        return BREAK if index < broken else _right(values)

    return _session(_spec(tmp_path, path, plan="p"), link, world=world)


def _windows(folder: Path) -> Path:
    """`varied_task` drawing the target window from 1° to 3°, whose declared ranges cannot overlap
    its two windows -- the fixation window up to 3°, the target's up to 3°, the target 8° to 16°
    out and within 1° of the horizontal -- and whose `stim_on` also scores leaving the fixation
    window, so both are scored there (the plan's engineering review, I-3, its probe 7). Engine test
    material, run only in the simulator."""
    folder.mkdir()
    return _edited(
        _sessions.varied_task(folder, draws='{"target_window": Uniform(1.0, 3.0, repeat=FRESH)}'),
        ('        Param("fix_window", unit="deg", low=0.5, high=5.0, start=2.0),',
         '        Param("fix_window", unit="deg", low=0.5, high=3.0, start=2.0),'),
        ('        Param("target_window", unit="deg", low=0.5, high=6.0, start=3.0),',
         '        Param("target_window", unit="deg", low=0.5, high=3.0, start=3.0),'),
        ('        Param("target_x", unit="deg", low=-16.0, high=16.0, start=10.0),',
         '        Param("target_x", unit="deg", low=8.0, high=16.0, start=10.0),'),
        ('        Param("target_y", unit="deg", low=-16.0, high=16.0, start=0.0),',
         '        Param("target_y", unit="deg", low=-1.0, high=1.0, start=0.0),'),
        ('                On(SaccadeTo("target"), "verify", do=[Mark(4098)]),',
         '                On(SaccadeTo("target"), "verify", do=[Mark(4098)]),\n'
         '                On(Exited("fix"), Outcome.FIXATION_BREAK),'))


def test_a_hand_back_to_a_run_value_outside_its_range_is_checked_with_the_ranges_widened_since(
        tmp_path):
    """The plan's engineering review, I-3: a run given `fix_window` 4°, outside its declared 3° --
    widened alone it overlaps nothing, so it is only warned -- is held at 1° by a person, who then
    widens the target window's draw to 4.9° (checked widened with the held 1°, it breaks nothing)
    and hands `fix_window` back. The run's 4° beside a 4.9° window overlaps, which the widened
    load checks refuse for a typed value: so the hand-back is checked as one is (`_beyond_range`),
    refused at once, and 1° stands. With no range widened, the same hand-back applies."""
    def run(name: str, script: dict) -> Session:
        where = tmp_path / name
        path = _windows(where)
        session = _session(_spec(where, path, trials=6), _Drained(script))
        session.run(RunSpec(task=str(path), trials=6, seed=SEED,
                            values={"target_appearance": None, "fix_window": 4.0}))
        return session

    widened = run("widened", {1: [SetParameter("fix_window", 1.0, JAKE)],
                              2: [SetRange("target_window", {"high": 4.9}, JAKE)],
                              3: [HandBack("fix_window", JAKE)]})
    (why,) = [why for name, _, why in widened.refusals if name == "fix_window"]
    assert why.startswith(
        "'fix_window' is not handed back: 'fix_window' at 4 is outside its declared range, and "
        "with the range widened to it the load-time checks refuse it: overlapping-windows"), why
    assert [row["kind"] for row in _changes(widened)] == ["set", "range"]
    assert [line["params"]["fix_window"] for line in _lines(widened)] == [4.0] + [1.0] * 5
    plain = run("plain", {1: [SetParameter("fix_window", 1.0, JAKE)],
                          3: [HandBack("fix_window", JAKE)]})
    assert plain.refusals == []
    assert [line["params"]["fix_window"] for line in _lines(plain)] == [4.0, 1.0, 1.0, 4.0, 4.0,
                                                                         4.0]


def test_a_hand_back_applied_as_the_plan_moves_on_says_what_takes_the_setting_there(tmp_path):
    """The plan's engineering review, M-1: a hand-back offered as block A's rule is met applies in
    block B, whose condition gives `target_hold` 0.6 s. Its row and its feed line say what takes
    the setting back where it applies -- B's conditions, `now` null -- never A's run value, 0.2 s,
    which no trial of B held (the plan's call 41)."""
    plans = ("{'p': Plan(blocks=[Block('A', conditions=[Condition('a', {}, target=3)]), "
             "Block('B', conditions=[Condition('b', {'target_hold': 0.6}, target=3)])])}")
    path = _sessions.varied_task(tmp_path, plans=plans)
    link = _Drained({1: [SetParameter("target_hold", 0.4, JAKE)],
                     4: [HandBack("target_hold", JAKE)]})
    session = _session(_spec(tmp_path, path, trials=6, plan="p"), link)

    session.run()

    (row,) = [row for row in _changes(session) if row["kind"] == "hand_back"]
    assert (row["was"], row["now"], row["to"], row["trial_number"]) == (0.4, None, "conditions", 4)
    assert [(line["block"], line["params"]["target_hold"]) for line in _lines(session)] == [
        ("A", 0.2), ("A", 0.4), ("A", 0.4), ("B", 0.6), ("B", 0.6), ("B", 0.6)]
    assert [said for _, _, said in _fed(session, "hand_back")] == [
        "target_hold 0.40 handed back to its conditions, from trial 3"]


@pytest.mark.parametrize("repeat", ["SAME", "FRESH"])
def test_a_change_the_next_trials_repeat_would_meet_with_a_same_value_drawn_before_it_is_refused(
        tmp_path, repeat):
    """The controller's ruling of 2026-10-30 on the engine C3 plan's fuzz (seed 810), under the
    PI's Q10, "Refuse in file and live": in one drain a person narrows the deadline's draw to 0.75
    s and up, then asks for a target hold of 0.7 s. Over the narrowed range that leaves time to
    answer -- but the next trial is drawn before the two apply, from 0.5 s up, and where the
    deadline is `same` a repeat of it keeps that deadline under the new hold: the trial breaks,
    and the drum would bring it back with no answer ever paid. So the hold is refused at once,
    naming the condition. Where the deadline is `fresh`, the repeat draws it again from the
    narrowed range, and the hold is accepted. No trial runs that no animal can get right."""
    session = _kept_session(tmp_path, repeat, {1: [
        SetRange(name="response_deadline", numbers={"low": 0.75}, by=JAKE),
        SetParameter(name="target_hold", value=0.7, by=JAKE)]})

    session.run()

    lines = _lines(session)
    assert lines[0]["params"]["response_deadline"] < 0.7, "the premise: the first deadline"
    assert session.refusals == ([("target_hold", JAKE, HELD_TOO_LONG.format(
        deadline="as soon as 0.5 s"))] if repeat == "SAME" else [])
    assert (session.stop_kind, len(lines)) == ("completed", 4)
    assert all(line["params"]["response_deadline"] > line["params"]["target_hold"]
               for line in lines)


@pytest.mark.parametrize("repeat", ["SAME", "FRESH"])
def test_a_change_that_would_leave_a_waiting_trials_kept_same_value_impossible_is_refused(
        tmp_path, repeat):
    """The same ruling, its second path: the deadline's draw narrowed to 0.75 s and up applies;
    the first trial, drawn before it from 0.5 s up, breaks, and its drum waits to show it again.
    Then a person narrows it from above too and asks for a target hold of 0.7 s, and the drum's
    first try breaks as well, so its next try would run under the new hold. Every draw leaves
    time to answer -- but the waiting trial keeps its `same` deadline, so the hold is refused at
    once, naming its condition once, though both the draw applied now and the one offered are
    judged. Where the deadline is `fresh`, the waiting trial draws it again, and the hold is
    accepted. No trial runs that no animal can get right."""
    session = _kept_session(tmp_path, repeat, {
        1: [SetRange(name="response_deadline", numbers={"low": 0.75}, by=JAKE)],
        2: [SetRange(name="response_deadline", numbers={"high": 0.95}, by=JAKE),
            SetParameter(name="target_hold", value=0.7, by=JAKE)]}, broken=2)

    session.run()

    lines = _lines(session)
    assert lines[0]["params"]["response_deadline"] < 0.7, "the premise: the first deadline"
    assert session.refusals == ([("target_hold", JAKE, HELD_TOO_LONG.format(
        deadline="0.675507 s"))] if repeat == "SAME" else [])
    assert (session.stop_kind, len(lines)) == ("completed", 5)
    assert all(line["params"]["response_deadline"] > line["params"]["target_hold"]
               for line in lines)


def test_while_paused_a_change_is_judged_against_the_ranges_its_next_trial_will_draw_from(
        tmp_path):
    """Paused, no trial is drawn before what is offered applies: the session resumes, applies it,
    then draws. So narrowing the deadline's `same` draw to 0.75 s and up and then asking for a
    0.7 s target hold, while paused before the first trial, is accepted, and every trial leaves
    time to answer: the ranges applied now are judged only for a trial drawn before the change
    applies."""
    session = _kept_session(tmp_path, "SAME", {
        1: [Pause(by=JAKE)],
        2: [SetRange(name="response_deadline", numbers={"low": 0.75}, by=JAKE),
            SetParameter(name="target_hold", value=0.7, by=JAKE)],
        3: [Resume(by=JAKE)]}, broken=0)

    session.run()

    lines = _lines(session)
    assert session.refusals == []
    assert (session.stop_kind, len(lines)) == ("completed", 3)
    assert all(line["params"]["target_hold"] == 0.7 <= 0.75 <= line["params"]["response_deadline"]
               for line in lines)


def test_a_hand_back_or_range_naming_a_ceiling_is_refused_into_the_session_record_too(tmp_path):
    """The PI, 2026-09-19 (`record.SessionRecord.refusal`): a refusal of a ceiling-bounded name
    also goes into the session record, since telemetry is lossy. `_command`'s setting path writes
    it; the two acts, which run beside it, write the same row: the numbers asked for a range,
    nothing for a hand-back, who asked, the sentence the console was told and where in the run."""
    link = _Drained({3: [HandBack(name="reward_correct", by=JAKE),
                         HandBack(name="target_hold", by=JAKE),
                         SetRange(name="reward_correct", numbers={"low": 0.1}, by=JAKE)]})
    session = _session(_spec(tmp_path, _ceiling(tmp_path), trials=5), link)

    session.run()

    assert [name for name, _, _ in session.refusals] == [
        "reward_correct", "target_hold", "reward_correct"], "a mistyped or unheld name is no row"
    rows = _rows(session, "refusals.jsonl")
    assert [(row["name"], row["asked"], row["why"]) for row in rows] == [
        ("reward_correct", None, session.refusals[0][2]),
        ("reward_correct", {"low": 0.1}, session.refusals[2][2])]
    assert [session.refusals[i][2].split(":")[0] for i in (0, 2)] == [
        "'reward_correct' is not handed back", "the range of 'reward_correct' is not changed"]
    assert all(row["by"] == BY and row["trial_index"] == 2 for row in rows)
