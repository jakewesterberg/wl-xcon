"""The change log and resume (engine build C3's spec §8; XC-288 §3.4; closes XC-363).

`parameter_changes.jsonl` grows into one log of every change to what the animal experiences, one
row for each setting an act moves (`record.SessionRecord.change`): the act's `change` id, from 1;
its `kind`; what it moved (`name`, never empty) from what to what, each value written as given;
when it applied and the first trial it applies to, numbered as that trial's line; its run; the
setting's meaning with the way it went and its step; who; `offered`, `odds` and `event_code`;
and `sequence` on the kinds that strobe `PARAM_CHANGED` alone. A person's value is a `set` row
with a change id of its own, assigned where it applies (`taskd.Session._apply_staged`), never in
`Session.set`. A clear and the two switches are written to `controls.jsonl` exactly as engine
build C2a writes them, and to the change log beside them. Resume, through which the
welfare-listed `stranded.find` reads every stranded folder, reads every kind and still fails
closed on a damaged row.
"""

from __future__ import annotations

import dataclasses
import json
import os
import shutil
from pathlib import Path

import pytest

from wl_xcon import record, resume, stranded
from wl_xcon.actor import Box
from wl_xcon.bounds import Bounds, Ceiling, Floor
from wl_xcon.cli import _load_task
from wl_xcon.dio import Simulated as Card
from wl_xcon.link import ClearOwed, Drum, SetParameter, Simulated, Training
from wl_xcon.photometry import SRGB
from wl_xcon.record import SessionRecord, _local
from wl_xcon.scheduler import EVERY_TRIAL, Block, Condition
from wl_xcon.task import CLEAR_CUT, EASIER, FRESH, STIMULUS, Meaning, Param, Uniform
from wl_xcon.taskd import RunSpec, Session, SessionSpec
from wl_xcon.welfare import Deployment, Simulated as Pump
from _rig import DIRECT

#: The wall every session here reads from, plus its frames' seconds (`_session`).
WALL_NOW = 1_700_000_000.0
JAKE = {"kind": "box", "name": "jake"}
TASK = "tasks/fixation_detection.py"
#: The reference detection task's values, as `tests/test_taskd.py` runs it.
VALUES = {
    "fix_acquisition": 4.0, "fix_hold": 0.3, "response_deadline": 0.6, "target_hold": 0.2,
    "fix_window": 2.0, "target_window": 3.0, "target_x": 10.0, "target_y": 0.0,
    "target_appearance": None, "fix_luminance": 40.0, "target_luminance": 40.0,
}
#: Its own starting values (`Param.start`).
STARTS = {name: value for name, value in VALUES.items() if value is not None}
#: Every key of a change row, `sequence` included, for a kind that strobes `PARAM_CHANGED`.
KEYS = {"change", "kind", "name", "was", "now", "by", "at", "at_local", "trial_number", "run",
        "meaning", "offered", "odds", "event_code", "sequence"}


def _spec(tmp_path, **over) -> SessionSpec:
    spec = SessionSpec(
        task=TASK, allocation="tasks/allocation.py", root=tmp_path, session_id="2027-01-14_01",
        subject="A", trials=3, frame_period=1 / 240, seed=1, values=dict(VALUES),
        bounds=Bounds(
            subject="A",
            ceilings={"reward_correct": Ceiling(value=0.15, maximum=0.40, unit="mL"),
                      "out_of_cage": Ceiling(value=800.0, maximum=100_000.0, unit="s")},
            minima={"daily_fluid": Floor(value=250.0, unit="mL")},
        ),
        already_delivered_today=0.0, deployment=Deployment.RIG_FIXED, geometry=DIRECT,
        session_kind="training", calibration=SRGB,
    )
    for name, value in over.items():
        setattr(spec, name, value)
    return spec


def _session(spec, link=None, *, service=False) -> Session:
    """On the simulators, its wall following its frames from `WALL_NOW`, the animal out of its
    cage and its head fixed then, as `tests/test_taskd.py`'s sessions are; a `wlx taskd` one
    opened."""
    session = Session(spec, card=Card(), pump=Pump(),
                      link=link if link is not None else Simulated(), service=service)
    session.wall_clock = lambda: WALL_NOW + session.now()
    session.left_cage(at=WALL_NOW)
    session.head_fixed(at=session.wall_now())
    if service:
        session.open(how="wlx taskd")
    return session


class _Drained(Simulated):
    """A link that queues `script[n]` as the `n`th drain begins: the commands reach the loop at
    the boundary before trial `n`.

    It also bounds the session: a test here that passes drains at most 416 times (the drum's
    chain of failed tries, which the clear tests count in), so a session that goes past `BUDGET`
    drains, five times that and more, is one that never ends (a mutant of `taskd._ends` runs it
    toward the eight-hour limit), and fails here by name at once rather than hanging."""

    BUDGET = 2000

    def __init__(self, script):
        super().__init__()
        self.script, self.drains = dict(script), 0

    def drain(self) -> list:
        self.drains += 1
        assert self.drains <= self.BUDGET, (
            f"the session drained {self.drains} times, past the budget of {self.BUDGET} (the "
            "longest passing test here counts 416): it is not ending")
        for command in self.script.get(self.drains, ()):
            self.queue(command)
        return super().drain()


def _rows(session: Session, name: str) -> list[dict]:
    return [json.loads(line) for line in (session.directory / name).read_text().splitlines()]


def _without_instants(row: dict) -> dict:
    return {key: value for key, value in row.items() if key not in ("at", "at_local")}


def test_a_persons_value_writes_a_set_row_with_every_key_and_its_first_trial(tmp_path):
    """XC-288 §3.4: the row's `change` id, from 1; when it applied, at the instant its line on
    the changes feed names; the first trial it applies to, numbered as that trial's line; the
    setting's meaning, with the way it went and its step; `offered` empty and `odds` null; and
    the `sequence` its strobe joins it by."""
    link = _Drained({1: [SetParameter(name="fix_hold", value=0.5, by=Box("jake"))]})
    session = _session(_spec(tmp_path), link)

    session.run()

    (row,) = _rows(session, "parameter_changes.jsonl")
    assert set(row) == KEYS
    assert _without_instants(row) == {
        "change": 1, "kind": "set", "name": "fix_hold", "was": 0.3, "now": 0.5, "by": JAKE,
        "trial_number": 2, "run": 0,
        "meaning": {"kind": "clear-cut", "role": "criterion", "raising": "harder",
                    "relative_to": None, "went": "harder", "step": pytest.approx(0.2)},
        "offered": [], "odds": None, "event_code": 4130, "sequence": 1,
    }
    lines = _rows(session, "trials.jsonl")
    assert [(line["trial_number"], line["params"]["fix_hold"]) for line in lines] == [
        (1, 0.3), (2, 0.5), (3, 0.5)], "its first trial is the line its trial_number names"
    (fed,) = [at for kind, _, at, _ in session.controls if kind == "set"]
    assert (row["at"], row["at_local"]) == (fed, _local(fed))


def _near_far() -> Block:
    return Block(name="b", conditions=[Condition("near", {"target_x": 5.0}, target=4),
                                       Condition("far", {"target_x": 12.0}, target=4)])


def _switched(tmp_path) -> Session:
    """A run in which, before its first trial, a trainer switches the training aid *clear* on,
    clears one trial of `near` and switches drumming on for the run; and in which a person sets
    `fix_hold` before its second, applied from its third."""
    link = _Drained({1: [Training(setting="clear", on=True, by=Box("jake")),
                         ClearOwed(condition="near", by=Box("jake")),
                         Drum(scope="run", by=Box("jake"))],
                     2: [SetParameter(name="fix_hold", value=0.5, by=Box("jake"))]})
    session = _session(_spec(tmp_path, trials=400, blocks=[_near_far()]), link)
    session.run()
    return session


def test_a_clear_a_drum_switch_and_a_training_switch_are_written_to_both_files(tmp_path):
    """XC-363, and the C3 ask (`docs/pending-wl-preproc-amendments.md`): each is a control row in
    `controls.jsonl` exactly as engine build C2a writes it, and a change row of its own kind
    beside it, at the same instant, its `name` what it moved, no meaning and no `sequence`: it
    strobes nothing. A person's value after them takes the next change id, and the first
    `sequence`."""
    session = _switched(tmp_path)

    controls = [row for row in _rows(session, "controls.jsonl")
                if row["kind"] in ("training", "clear", "drum")]
    first = {"by": JAKE, "trial_index": 0, "event_code": None, "run": 0}
    assert [_without_instants(row) for row in controls] == [
        {**first, "kind": "training", "setting": "clear", "was": False, "now": True},
        {**first, "kind": "clear", "condition": "near", "block": "b", "rest": False,
         "cleared": 1, "owed": 3},
        {**first, "kind": "drum", "scope": "run", "block": "b", "was": None, "now": "run"},
    ], "the control rows exactly as engine build C2a writes them"
    changes = _rows(session, "parameter_changes.jsonl")
    common = {"by": JAKE, "trial_number": 1, "run": 0, "meaning": None, "offered": [],
              "odds": None, "event_code": None}
    assert [_without_instants(row) for row in changes[:3]] == [
        {**common, "change": 1, "kind": "training", "name": "clear", "was": False, "now": True,
         "setting": "clear"},
        {**common, "change": 2, "kind": "clear", "name": "owed", "was": 4, "now": 3,
         "condition": "near", "block": "b", "rest": False, "cleared": 1},
        {**common, "change": 3, "kind": "drum", "name": "drumming", "was": None, "now": "run",
         "scope": "run", "block": "b"},
    ]
    assert [(row["at"], row["at_local"]) for row in changes[:3]] == [
        (row["at"], row["at_local"]) for row in controls]
    (person,) = changes[3:]
    first_at = next(line["trial_number"] for line in _rows(session, "trials.jsonl")
                    if line["params"]["fix_hold"] == 0.5)
    assert (person["kind"], person["change"], person["sequence"], person["trial_number"]) == (
        "set", 4, 1, first_at)


def _their_reader():
    """wl-preproc's reader of these rows (`wl_preproc/events/rigrecords.py`), or a skip where its
    checkout is absent -- a failure under `WLX_REQUIRE_PREPROC=1`, which CI sets, as
    `tests/test_taskd.py` guards its assembler."""
    try:
        from wl_preproc.events.rigrecords import read_rig_records
    except ImportError as exc:  # pragma: no cover - exercised by the CI job
        if os.environ.get("WLX_REQUIRE_PREPROC") == "1":
            raise AssertionError(
                f"WLX_REQUIRE_PREPROC=1 but wl-preproc is not importable ({exc})") from exc
        pytest.skip("wl-preproc checkout not beside this repo")
    return read_rig_records


def test_wl_preprocs_reader_takes_every_change_row_and_its_strobed_ones_sequence(tmp_path):
    """The path, not the piece (the C3 ask: "Every row names something in `name`", since
    wl-preproc's reader leaves out a row that does not): its reader takes the clear's, the
    switches' and the person's rows with no problem, `sequence` on the one that strobed alone."""
    read_rig_records = _their_reader()
    session = _switched(tmp_path)

    records = read_rig_records(session.directory.parent)

    assert records.problems == ()
    assert [(change.name, change.sequence) for change in records.changes] == [
        ("clear", None), ("owed", None), ("drumming", None), ("fix_hold", 1)]


def test_two_changes_in_one_drain_each_take_an_id_and_strobe_once_in_order(tmp_path):
    """Engine build C3's spec §8 ("a `change` id ... one per revert"; a person's value is an act
    of its own): two values drained in one pass apply at one boundary, each its own change id and
    `sequence` in the order offered, each strobing `PARAM_CHANGED` once, back to back; a
    ceiling's row names no task setting, so it writes no meaning."""
    link = _Drained({1: [SetParameter(name="fix_hold", value=0.5, by=Box("jake")),
                         SetParameter(name="reward_correct", value=0.2, by=Box("sam"))]})
    session = _session(_spec(tmp_path), link)

    session.run()

    changes = _rows(session, "parameter_changes.jsonl")
    assert [(row["change"], row["sequence"], row["name"], row["trial_number"], row["by"]["name"])
            for row in changes] == [(1, 1, "fix_hold", 2, "jake"),
                                    (2, 2, "reward_correct", 2, "sam")]
    assert changes[1]["meaning"] is None
    codes = session.card.codes
    first = codes.index(4130)
    assert codes.count(4130) == 2 and codes[first + 1] == 4130


def test_a_rows_meaning_says_which_way_it_went_and_its_step(tmp_path):
    """XC-288 §3.4 and §4.1 (TRN-03): the setting's declared meaning, `relative_to` as written,
    the way the change went by it and its step. A choice has no order (TRN-11), so a change goes
    the way its `raising` says, whichever way it moved; a meaning relative to another setting
    reads that setting's value; the background cannot be read here, nor anything for a setting
    that is not a difficulty setting; a ceiling's name is no task setting."""
    task = _load_task(Path(TASK))
    detection = task.structures["detection"]
    extra = [Param("cue_size", unit="deg", choices=(1.0, 2.0)),
             Param("guide_x", unit="deg", low=-16.0, high=16.0, start=0.0)]
    task = dataclasses.replace(
        task,
        structures={"detection": dataclasses.replace(detection,
                                                     params=[*detection.params, *extra])},
        meanings={"cue_size": Meaning(CLEAR_CUT, STIMULUS, raising=EASIER),
                  "guide_x": Meaning(CLEAR_CUT, STIMULUS, raising=EASIER, relative_to="target_x")},
    )
    session = _session(_spec(tmp_path))
    session._take(task)
    meaning = session._meaning
    disc, square = next(p for p in task.params if p.name == "target_appearance").choices

    assert meaning("fix_hold", 0.3, 0.5) == {
        "kind": "clear-cut", "role": "criterion", "raising": "harder", "relative_to": None,
        "went": "harder", "step": pytest.approx(0.2)}
    assert [meaning("fix_hold", 0.5, 0.3)["went"], meaning("fix_window", 2.0, 3.0)["went"],
            meaning("fix_window", 2.0, 2.0)["went"]] == ["easier", "easier", None]
    assert (meaning("fix_hold", None, 0.5)["went"], meaning("fix_hold", None, 0.5)["step"]) == (
        None, None)
    luminance = meaning("target_luminance", 40.0, 60.0)
    assert (luminance["kind"], luminance["relative_to"], luminance["went"], luminance["step"]) == (
        "expected", "background", None, 20.0)
    assert meaning("target_x", 10.0, -10.0) == {
        "kind": "not a difficulty setting", "role": "stimulus", "raising": None,
        "relative_to": None, "went": None, "step": -20.0}
    assert (meaning("target_appearance", disc, square)["went"],
            meaning("target_appearance", disc, square)["step"]) == (None, None)
    assert [meaning("cue_size", 2.0, 1.0)["went"], meaning("cue_size", 1.0, 2.0)["went"]] == [
        "easier", "easier"]
    assert meaning("guide_x", 8.0, 4.0)["relative_to"] == "target_x"
    assert [meaning("guide_x", 8.0, 4.0)["went"], meaning("guide_x", 4.0, 8.0)["went"],
            meaning("guide_x", 8.0, 12.0)["went"]] == ["easier", "harder", None]
    assert meaning("reward_correct", 0.15, 0.2) is None


def _direction_task(folder: Path) -> Path:
    """The reference detection task with its target 8° out at a direction, `target_dir`, declared
    from -180 to 180 (`task.Polar`), written into `folder` as `direction.py`. Engine test material,
    run only in the simulator: no reference task places a target by a direction setting."""
    text = Path(TASK).read_text()
    for old, new in (
        ('"target", at=(P("target_x"), P("target_y")), looks=P("target_appearance")',
         '"target", at=Polar(8.0, P("target_dir")), looks=P("target_appearance")'),
        ('            at=(P("target_x"), P("target_y")),\n            radius=P("target_window"),',
         '            at=Polar(8.0, P("target_dir")),\n            radius=P("target_window"),'),
        ('        Param("target_x", unit="deg", low=-16.0, high=16.0, start=10.0),',
         '        Param("target_dir", unit="deg", low=-180.0, high=180.0, start=90.0),\n'
         '        Param("target_x", unit="deg", low=-16.0, high=16.0, start=10.0),'),
        ("from wl_xcon.task import (", "from wl_xcon.task import (\n    Polar,"),
    ):
        assert text.count(old) == 1, old
        text = text.replace(old, new)
    text += (
        "\n\nimport dataclasses as _direction_dataclasses\n"
        "from wl_xcon.task import NOT_DIFFICULTY, STIMULUS, Meaning\n"
        "TASK = _direction_dataclasses.replace(TASK, meanings={\n"
        "    'target_dir': Meaning(NOT_DIFFICULTY, STIMULUS, note='where the target is'),\n"
        "})\n"
    )
    path = Path(folder) / "direction.py"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def test_a_persons_direction_is_written_as_given_in_its_change_row(tmp_path):
    """The PI, 2026-10-30, "Warn at load": a setting's number is shown and recorded as the number
    it holds, and only a value the rig draws is normalized when written (the C3 ask). A person's
    -90 for a direction setting is -90 in its change row's `now`, as in the trials' `params`."""
    task = _direction_task(tmp_path / "tasks")
    link = _Drained({1: [SetParameter(name="target_dir", value=-90.0, by=Box("jake"))]})
    session = _session(_spec(tmp_path, task=str(task), values={**VALUES, "target_dir": 90.0}),
                       link)

    session.run()

    (row,) = _rows(session, "parameter_changes.jsonl")
    assert (row["was"], row["now"], row["meaning"]["step"]) == (90.0, -90.0, -180.0)
    assert [line["params"]["target_dir"] for line in _rows(session, "trials.jsonl")] == [
        90.0, -90.0, -90.0]


def test_a_change_row_its_readers_would_refuse_is_never_written(tmp_path):
    """The record's side of resume's refusal: a kind the rig does not write, a `sequence` where
    the kind strobes nothing or none where it strobes `PARAM_CHANGED`, a row naming nothing
    (wl-preproc leaves one out), and a change id that is not a whole number from 1 are each
    refused before the file is opened."""
    assert record.KINDS == ("set", "hand_back", "range", "revert", "clear", "drum", "training",
                            "suggested", "declined")
    assert record.STROBED == ("set", "hand_back", "range", "revert")
    log = SessionRecord.open(tmp_path, "2027-01-14_01", "A")
    good = dict(change=1, kind="set", name="fix_hold", was=0.3, now=0.5, by=Box("jake"),
                at=WALL_NOW, trial_number=1, run=0, meaning=None, event_code=4130, sequence=1)
    for over, said in (({"kind": "preset"}, "kind is one of"),
                       ({"sequence": None}, "carries a sequence exactly when"),
                       ({"kind": "clear", "event_code": None}, "carries a sequence exactly when"),
                       ({"name": ""}, "names nothing"),
                       ({"change": 0}, "whole number from 1"),
                       ({"change": True}, "whole number from 1")):
        with pytest.raises(ValueError, match=said):
            log.change(**{**good, **over})
    assert not (log.directory / "parameter_changes.jsonl").exists()
    log.change(**good)
    log.change(**{**good, "change": 2, "kind": "drum", "name": "drumming", "was": None,
                  "now": "run", "by": None, "event_code": None, "sequence": None,
                  "scope": "run", "block": "b"})
    rows = [json.loads(line) for line in
            (log.directory / "parameter_changes.jsonl").read_text().splitlines()]
    assert set(rows[0]) == KEYS
    assert set(rows[1]) == KEYS - {"sequence"} | {"scope", "block"}
    assert (rows[1]["by"], rows[1]["at_local"]) == (None, _local(WALL_NOW))


def test_each_run_keeps_its_own_values_and_starts_with_no_live_range(tmp_path):
    """The run's own values are the task's starts under what the run was given, before any live
    edit; a draw changed live is the run's alone (engine build C3's spec §6); the change ids go on
    across runs, as `sequence` does."""
    session = _session(_spec(tmp_path, task="", trials=0, values={}), service=True)
    session.link.queue(SetParameter(name="fix_hold", value=0.5, by=Box("jake")))

    session.run(RunSpec(task=TASK, trials=3, seed=2, values={"fix_window": 3.0}))

    assert session._run_values == {**STARTS, "fix_window": 3.0}
    assert session.spec.values["fix_hold"] == 0.5
    # As a live range would leave it (`Session._range`, the C3 plan's Task 13).
    session._ranges[("task", "fix_hold")] = (Uniform(0.2, 0.4, repeat=FRESH), 1)
    session.link.queue(SetParameter(name="fix_hold", value=0.6, by=Box("jake")))
    session.run(RunSpec(task=TASK, trials=3, seed=2, values={}))

    assert (session._run_values, session._ranges) == (STARTS, {})
    assert [(row["change"], row["sequence"], row["run"])
            for row in _rows(session, "parameter_changes.jsonl")] == [(1, 1, 0), (2, 2, 1)]


#: A change row as the rig writes one, whole: what each damage below starts from.
_WHOLE = {"change": 10, "kind": "set", "name": "fix_hold", "was": 0.4, "now": 0.5, "by": JAKE,
          "at": WALL_NOW + 600.0, "at_local": "", "trial_number": 12, "run": 0, "meaning": None,
          "offered": [], "odds": None, "event_code": 4130, "sequence": 8}
_UNSEQUENCED = {k: v for k, v in _WHOLE.items() if k != "sequence"}
_NO_SEQUENCE = "strobed PARAM_CHANGED and holds no whole-number sequence"
#: One damaged row each, and what `stranded.find` says of it.
_DAMAGED = {
    "unknown kind": ({**_WHOLE, "kind": "preset"}, "is of the kind 'preset'"),
    "set without sequence": (_UNSEQUENCED, _NO_SEQUENCE),
    "range without sequence": ({**_UNSEQUENCED, "kind": "range"}, _NO_SEQUENCE),
    "no kind, no sequence": ({k: v for k, v in _UNSEQUENCED.items() if k != "kind"},
                             _NO_SEQUENCE),
    "change as text": ({**_WHOLE, "change": "10"}, "holds no change id"),
    "change 0": ({**_WHOLE, "change": 0}, "holds no change id"),
}


def test_a_session_whose_log_holds_every_kind_is_found_resumable_and_goes_on_numbering(tmp_path):
    """Review Focus 4 (engine build C3's spec §8; `stranded.find` is welfare-listed and reads
    every stranded folder through `resume.read`). A session's log holds a clear, a drum switch and
    a training switch, a person's values, a hand-back, a range change and a two-row revert,
    written through `record.change` before its process stopped: it is found resumable, its next
    `sequence` and its next `change` exceed every one in the log, and its reward size is restored
    from the last `set` row of it alone, never from another kind's row naming it (which the rig
    never writes). With one damaged row added -- an unknown kind, a strobed or kindless row without
    a whole-number `sequence`, a `change` that is text or 0 -- it is found not resumable, saying
    which row, failing closed."""
    root = tmp_path / "first"
    link = _Drained({1: [Training(setting="clear", on=True, by=Box("jake")),
                         ClearOwed(condition="x", by=Box("jake")),
                         Drum(scope="block", by=Box("jake")),
                         SetParameter(name="reward_correct", value=0.2, by=Box("jake"))]})
    first = _session(_spec(root, task="", trials=0, values={}), link, service=True)
    block = Block(name="X", conditions=[Condition("x", {}, target=3)], counting=EVERY_TRIAL)
    first.run(RunSpec(task=TASK, trials=50, seed=2, values=dict(VALUES), blocks=[block]))
    log = SessionRecord.open(root, "2027-01-14_01", "A")
    later = {"by": Box("jake"), "at": WALL_NOW + 500.0, "trial_number": 9, "run": 0,
             "meaning": None, "event_code": 4130}
    uniform = {"class": "Uniform", "fields": {"low": 0.2, "high": 0.4, "repeat": "fresh"}}
    log.change(change=5, kind="hand_back", name="fix_hold", was=0.5, now=0.3, sequence=2,
               to="run", **later)
    log.change(change=6, kind="range", name="fix_hold", was=uniform,
               now={**uniform, "fields": {**uniform["fields"], "high": 0.5}}, sequence=3,
               block=None, **{"from": "task"}, **later)
    log.change(change=7, kind="revert", name="fix_hold", was=0.3, now=0.4, sequence=4,
               moment=4, **later)
    log.change(change=7, kind="revert", name="fix_window", was=2.0, now=2.5, sequence=5,
               moment=4, **later)
    log.change(change=8, kind="set", name="reward_correct", was=0.2, now=0.25, sequence=6,
               **later)
    log.change(change=9, kind="revert", name="reward_correct", was=0.25, now=0.35,
               sequence=7, moment=4, **later)
    kinds = [row["kind"] for row in _rows(first, "parameter_changes.jsonl")]
    assert kinds == ["training", "clear", "drum", "set", "hand_back", "range", "revert",
                     "revert", "set", "revert"]
    for label, (row, _) in _DAMAGED.items():
        copy = tmp_path / label.replace(" ", "_")
        shutil.copytree(root, copy)
        with (copy / "2027-01-14_01" / "xcon" / "parameter_changes.jsonl").open("a") as handle:
            handle.write(json.dumps(row) + "\n")

    (found,) = stranded.find(root)
    assert (found.resumable, found.why) == (True, "")
    restoration = resume.read(first.directory, first.welfare.left_cage_wall_at)
    assert (restoration.sequence, restoration.change) == (7, 9)
    assert restoration.bounded["reward_correct"] == 0.25
    again = Session(_spec(root, task="", trials=0, values={}), card=Card(), pump=Pump(),
                    link=Simulated(), service=True)
    later_still = first.now() + 60.0
    again.wall_clock = lambda: WALL_NOW + later_still + again.now()
    again.resume(restoration, by=Box("jake"), how="test")
    assert (again._sequence, again._change) == (7, 9)
    assert again.spec.bounds.value("reward_correct") == 0.25
    again.link.queue(SetParameter(name="fix_hold", value=0.4, by=Box("jake")))
    again.run(RunSpec(task=TASK, trials=50, seed=2, values=dict(VALUES), blocks=[block]))
    last = _rows(again, "parameter_changes.jsonl")[-1]
    assert (last["kind"], last["change"], last["sequence"], last["run"]) == ("set", 10, 8, 1)

    for label, (_, said) in _DAMAGED.items():
        (found,) = stranded.find(tmp_path / label.replace(" ", "_"))
        assert not found.resumable, label
        assert found.why.startswith(f"its parameter_changes.jsonl row 11 {said}"), found.why


def _clear_after_a_failed_try(tmp_path, monkeypatch, block: Block,
                              outcome=None) -> tuple[dict, dict]:
    """A run whose every try fails, in `block` with drumming on from the start: *clear* is switched
    on before the first trial and the condition it drew cleared before the second, with the
    failed trial's drum waiting. The clear's control row and its change row."""
    from wl_xcon import taskd
    from wl_xcon.task import Outcome

    outcome = outcome or Outcome.WRONG_TARGET
    real = taskd.run_trial

    def wrong(*args, **kwargs):
        return dataclasses.replace(real(*args, **kwargs), outcome=outcome)

    monkeypatch.setattr(taskd, "run_trial", wrong)
    holder = []

    class Clearing(_Drained):
        """Names, as the second drain begins, the condition the failed trial drew."""

        def drain(self) -> list:
            if self.drains == 1:
                drawn = holder[0]._scheduler.drawn.condition.name
                self.script[2] = [ClearOwed(condition=drawn, by=Box("jake"))]
            return super().drain()

    link = Clearing({1: [Training(setting="clear", on=True, by=Box("jake"))]})
    session = _session(_spec(tmp_path, trials=3, blocks=[block]), link)
    holder.append(session)
    session.run()
    (control,) = [row for row in _rows(session, "controls.jsonl") if row["kind"] == "clear"]
    (change,) = [row for row in _rows(session, "parameter_changes.jsonl")
                 if row["kind"] == "clear"]
    return control, change


def test_a_clear_of_a_drums_waiting_trial_in_a_designed_block_was_owed_what_it_owes(
        tmp_path, monkeypatch):
    """Engine build C3's spec §8 and the C3 ask ("what the condition owed before and after"): in
    a priming block, which owes nothing, a drum's waiting trial is no debt, so clearing it moves
    what the condition owes not at all, and the change row says so (`was` equals `now`), as the
    control row's `owed` does; a sequence-balanced block's is the next test."""
    from wl_xcon.scheduler import Priming

    priming = Block(name="p", conditions=[Condition("x", {"target_x": 5.0}, target=0),
                                          Condition("y", {"target_x": 12.0}, target=0)],
                    order=Priming("target_x", chance=0.5), trials=50, drum=True)
    control, change = _clear_after_a_failed_try(tmp_path / "priming", monkeypatch, priming)
    assert (control["cleared"], control["owed"]) == (1, 0)
    assert (change["was"], change["now"], change["cleared"]) == (0, 0, 1)


def test_a_clear_of_a_drums_waiting_trial_in_a_sequence_balanced_block_was_owed_what_it_owes(
        tmp_path, monkeypatch):
    """The sequence-balanced half of the case above: the block owes its plan's places, and a
    drum's waiting trial is not among them, so the row's `was` equals its `now`."""
    from wl_xcon.scheduler import SequenceBalanced

    balanced = Block(name="s", conditions=[Condition("x", {"target_x": 5.0}, target=2),
                                           Condition("y", {"target_x": 12.0}, target=2)],
                     order=SequenceBalanced(depth=2), drum=True)
    control, change = _clear_after_a_failed_try(tmp_path, monkeypatch, balanced)
    assert (control["cleared"], control["owed"]) == (1, change["now"])
    assert change["was"] == change["now"] > 0


def test_a_clear_of_a_trial_shown_again_at_once_was_owed_one_more(tmp_path, monkeypatch):
    """The other designed case: a sequence-balanced block that shows a failed trial again at
    once owes that trial among its places, so clearing it takes one off what the condition owes
    (`was` one more than `now`)."""
    from wl_xcon.scheduler import SequenceBalanced
    from wl_xcon.task import Outcome

    block = Block(name="s", conditions=[Condition("x", {"target_x": 5.0}, target=2),
                                        Condition("y", {"target_x": 12.0}, target=2)],
                  order=SequenceBalanced(depth=2, again_at_once=True))
    control, change = _clear_after_a_failed_try(tmp_path, monkeypatch, block,
                                                Outcome.FIXATION_BREAK)
    assert control["cleared"] == 1
    assert (change["was"], change["now"]) == (control["owed"] + 1, control["owed"])
