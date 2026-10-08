import json
import os
from pathlib import Path

import pytest

from wl_xcon.actor import Box
from wl_xcon.link import TEXT_LIMIT, _quoted
from wl_xcon.resume import PREDATES, PREDATES_KINDS, Unresumable, read
from wl_xcon.task import Outcome

DEPARTURE = 1_700_000_000.0
TASK = "tasks/fixation_detection.py"
NAMES = ("trial_number", "trial_in_task", "trial_in_run", "trial_in_block",
         "block_in_session", "block_in_task", "block_in_run",
         "run_in_session", "run_in_task", "task_in_session")


def _pos(*numbers, run, task=TASK):
    return {"run": run, "task": task, **dict(zip(NAMES, numbers))}


def _start(run, bounded, task=TASK, numbers=None):
    """A run's start row with the numbers `Session.run` records in it: `numbers` is its
    `(run_in_session, run_in_task, task_in_session)`, by default the run of one task whose
    record index is `run`."""
    run_in_session, run_in_task, task_in_session = numbers or (run + 1, run + 1, 1)
    return {"event": "start", "run": run, "at": DEPARTURE + 60 * run, "task": task,
            "bounded": bounded, "run_in_session": run_in_session, "run_in_task": run_in_task,
            "task_in_session": task_in_session}


def _end(run, stopped_because="every block is finished", stop_kind="completed"):
    return {"event": "end", "run": run, "at": DEPARTURE + 60 * run + 50,
            "stopped_because": stopped_because, "stop_kind": stop_kind}


def _line(number, outcome, fluid_ml, last_reward_at, run):
    return {"index": number - 1, "run": run, "trial_number": number, "outcome": outcome,
            "fluid_ml": fluid_ml, "last_reward_at": last_reward_at}


def _reward(ml, at):
    # The real row (`record.control`) also carries `at_local`, `trial_index` and `run`.
    return {"kind": "reward", "by": {"kind": "box", "name": "jake"}, "at": at, "ml": ml, "entry": "reward_correct",
            "trial_index": 0, "run": None}


def _change(sequence, name, was, now, run):
    return {"sequence": sequence, "name": name, "was": was, "now": now, "by": {"kind": "box", "name": "jake"}, "run": run}


def _config(**over):
    config = {
        "session_id": "2027-01-14_01", "subject": "REFERENCE", "service": True,
        "deployment": "rig_chaired",
        "session_kind": "training",
        "bounds": {"ceilings": {"reward_correct": {"value": 0.05, "maximum": 10.0, "unit": "mL"}},
                   "minima": {"daily_fluid": {"value": 20.0, "unit": "mL"}}},
        "versions": {"bounds": "b.py", "rig": "r.py", "subject_settings": ""},
        "setup": {"view": "direct"},
        "already_delivered_today": 40.0,
    }
    config.update(over)
    return config


def _jsonl(path: Path, rows) -> None:
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))


def _folder(tmp_path, *, runs=(), starts=(), lines=(), controls=(), changes=(), config=None):
    directory = tmp_path / "2027-01-14_01" / "xcon"
    directory.mkdir(parents=True)
    (directory / "config.json").write_text(json.dumps(config or _config()))
    for name, rows in (("runs.jsonl", runs), ("trial_starts.jsonl", starts),
                       ("trials.jsonl", lines), ("controls.jsonl", controls),
                       ("parameter_changes.jsonl", changes)):
        if rows:
            _jsonl(directory / name, rows)
    return directory


def _two_runs(tmp_path, changes=()):
    """Two runs of one task. The second was cut by a crash mid-trial: trial 5 started,
    with no line. A hand reward fell between the runs."""
    return _folder(
        tmp_path,
        runs=[_start(0, {"reward_correct": 0.2}), _end(0), _start(1, {"reward_correct": 0.25})],
        starts=[_pos(1, 1, 1, 1, 1, 1, 1, 1, 1, 1, run=0), _pos(2, 2, 2, 2, 1, 1, 1, 1, 1, 1, run=0),
                _pos(3, 3, 1, 1, 2, 2, 1, 2, 2, 1, run=1), _pos(4, 4, 2, 2, 2, 2, 1, 2, 2, 1, run=1),
                _pos(5, 5, 3, 3, 2, 2, 1, 2, 2, 1, run=1)],
        lines=[_line(1, "correct", 0.2, DEPARTURE + 100, run=0),
               _line(2, "no_fixation", 0.0, None, run=0),
               _line(3, "correct", 0.25, DEPARTURE + 300, run=1),
               _line(4, "correct", 0.25, DEPARTURE + 400, run=1)],
        controls=[_reward(0.25, at=DEPARTURE + 200)],
        changes=changes,
    )


def test_a_session_read_back_gives_its_departure_fluid_and_numbers(tmp_path):
    got = read(_two_runs(tmp_path), DEPARTURE)

    assert got.departure == DEPARTURE
    assert got.already_today == 40.0
    assert got.commanded == pytest.approx(0.2 + 0.25 + 0.25 + 0.25)
    assert got.last_reward_at == DEPARTURE + 400
    assert got.run_index == 1
    levels = got.levels
    assert (levels.trials, levels.blocks, levels.runs) == (5, 2, 2)
    assert levels.order == {"fixation_detection": 1}
    assert levels.task_runs == {"fixation_detection": 2}
    assert levels.task_trials == {"fixation_detection": 5}
    assert levels.task_blocks == {"fixation_detection": 2}
    assert levels.session_tally.outcomes == {Outcome.CORRECT: 3, Outcome.NO_FIXATION: 1}
    assert levels.task_tallies["fixation_detection"].outcomes[Outcome.CORRECT] == 3


def test_a_started_trial_with_no_line_keeps_its_number_and_adds_no_fluid(tmp_path):
    """Review Focus 4: trial 5 started, so the next trial is 6, and its fluid is not counted."""
    levels = read(_two_runs(tmp_path), DEPARTURE).levels
    levels.start_run(TASK)
    position, opened = levels.start_trial()
    assert (position.trial_number, position.block_in_session, position.run_in_session) == (6, 3, 3)
    assert opened


def test_a_hand_reward_between_runs_is_counted_and_can_be_the_last_reward(tmp_path):
    """Review Focus 3."""
    directory = _two_runs(tmp_path)
    _jsonl(directory / "controls.jsonl", [_reward(0.25, at=DEPARTURE + 900)])
    got = read(directory, DEPARTURE)
    assert got.commanded == pytest.approx(0.2 + 0.25 + 0.25 + 0.25)
    assert got.last_reward_at == DEPARTURE + 900


def test_the_reward_size_is_the_last_runs_then_its_own_changes(tmp_path):
    """A change made in run 0 is already in run 1's start row; one made in run 1 is not."""
    earlier = read(_two_runs(tmp_path / "a", changes=[_change(1, "reward_correct", 0.2, 0.25, run=0)]),
                   DEPARTURE)
    assert earlier.bounded == {"reward_correct": 0.25} and earlier.sequence == 1
    later = read(_two_runs(tmp_path / "b", changes=[_change(1, "reward_correct", 0.2, 0.25, run=0),
                                                    _change(2, "reward_correct", 0.25, 0.3, run=1),
                                                    _change(3, "fix_window", 2.0, 3.0, run=1)]),
                 DEPARTURE)
    assert later.bounded == {"reward_correct": 0.3} and later.sequence == 3
    # The last start row is authoritative for what came before it: a run-0 change is not
    # replayed over it (it would be the same value in a consistent record, so only a
    # differing one proves the run filter is there).
    stale = read(_two_runs(tmp_path / "c", changes=[_change(1, "reward_correct", 0.2, 0.9, run=0)]),
                 DEPARTURE)
    assert stale.bounded == {"reward_correct": 0.25}


def test_an_out_of_cage_limit_changed_in_any_run_is_carried_the_latest_last(tmp_path):
    """The final review's I2: no start row's `bounded` holds `out_of_cage`, so a change
    to it made in any run is carried, never reverted to the file's on resume; of two,
    the later by sequence."""
    once = read(_two_runs(tmp_path / "a", changes=[_change(1, "out_of_cage", 28800.0, 3600.0, run=0)]),
                DEPARTURE)
    assert once.bounded == {"reward_correct": 0.25, "out_of_cage": 3600.0}
    twice = read(_two_runs(tmp_path / "b", changes=[_change(1, "out_of_cage", 28800.0, 7200.0, run=0),
                                                    _change(2, "out_of_cage", 7200.0, 3600.0, run=1)]),
                 DEPARTURE)
    assert twice.bounded == {"reward_correct": 0.25, "out_of_cage": 3600.0}


def test_a_session_opened_with_no_run_reads_back_with_run_one_next(tmp_path):
    """Review Focus 2."""
    got = read(_folder(tmp_path), DEPARTURE)
    assert (got.commanded, got.last_reward_at, got.run_index, got.sequence) == (0.0, None, None, 0)
    assert got.bounded == {}
    got.levels.start_run(TASK)
    assert got.levels.start_trial()[0].run_in_session == 1


# The final review's I3: a run that raises after `Levels.start_run` and before its start
# row (`Session.run` contains it, and the session goes on) took its numbers and wrote
# none. Counting start rows would issue them again; the start rows' own numbers do not.


def _next_run(directory, task=TASK) -> tuple:
    levels = read(directory, DEPARTURE).levels
    levels.start_run(task)
    position = levels.start_trial()[0]
    return position.run_in_session, position.run_in_task, position.task_in_session


def test_the_next_run_is_numbered_past_every_run_recorded_not_by_the_rows(tmp_path):
    """Run 2 raised before its start row: the next is run 4, and the task's run 4."""
    directory = _folder(tmp_path, runs=[_start(0, {}), _end(0), _start(2, {}), _end(2)])

    assert _next_run(directory) == (4, 4, 1)


def test_a_task_new_since_a_gap_is_numbered_past_every_task_recorded(tmp_path):
    """Detection, the session's second task, raised before its start row; calibration
    then took task 3. Detection's next run is the session's fourth task, never the third."""
    directory = _folder(tmp_path, runs=[
        _start(0, {}), _end(0),
        _start(2, {}, task="tasks/calibration.py", numbers=(3, 1, 3)), _end(2),
    ])

    assert _next_run(directory, "tasks/detection.py") == (4, 1, 4)
    assert _next_run(directory, "tasks/calibration.py") == (4, 2, 3)


def test_a_start_row_without_its_run_and_task_numbers_cannot_be_resumed(tmp_path):
    row = _start(0, {})
    del row["task_in_session"]
    directory = _folder(tmp_path, runs=[row])

    with pytest.raises(Unresumable, match="run and task numbers"):
        read(directory, DEPARTURE)


def test_a_session_whose_runs_were_ended_reads_back_as_ended(tmp_path):
    """The final review's I1: End session's `end` row (`Session.end_runs`) is read back,
    so the session comes back waiting for its return (the PI, 2026-10-01)."""
    directory = _two_runs(tmp_path)
    assert read(directory, DEPARTURE).ended is False

    with (directory / "controls.jsonl").open("a") as handle:
        handle.write(json.dumps({"kind": "end", "by": {"kind": "box", "name": "jake"}, "at": DEPARTURE + 950,
                                 "trial_index": 0, "run": 1}) + "\n")

    assert read(directory, DEPARTURE).ended is True


def _ended_by(by):
    return {"kind": "end", "by": by, "at": DEPARTURE + 950, "trial_index": 0, "run": None}


def test_how_the_last_run_ended_is_read_back_and_never_before_any_run(tmp_path):
    """The final review's M1: how the session's last run ended, for the frames between
    runs and the summary -- its end row's reason, or, with no end row, that it stopped
    with its process -- and "before any run" only of a session that ran none."""
    killed = read(_two_runs(tmp_path / "a"), DEPARTURE)
    assert (killed.stopped_because, killed.stop_kind) == (
        "run 2 stopped with its process; its record holds no end for it", "fault",
    )
    directory = _two_runs(tmp_path / "b")
    with (directory / "runs.jsonl").open("a") as handle:
        handle.write(json.dumps(_end(1, "stopped by jake", "operator")) + "\n")
    stopped = read(directory, DEPARTURE)
    assert (stopped.stopped_because, stopped.stop_kind) == ("stopped by jake", "operator")
    none = read(_folder(tmp_path / "c"), DEPARTURE)
    assert (none.stopped_because, none.stop_kind) == ("", None)
    ended = read(
        _folder(tmp_path / "d", controls=[_ended_by({"kind": "box", "name": "jake"})]), DEPARTURE
    )
    assert (ended.stopped_because, ended.stop_kind) == (
        "session ended by jake (box, unverified), before any run", "operator",
    )


def test_a_session_ended_before_b2b_names_who_ended_it_as_written(tmp_path):
    """Review Focus 1 (b2b spec §6): a record written before 2026-10-02 holds its `by`
    as a string, and a record is never rewritten, so a resume reads it back as written."""
    directory = _folder(tmp_path, controls=[_ended_by({"kind": "box", "name": "jake"})])
    (row,) = [json.loads(line) for line in (directory / "controls.jsonl").read_text().splitlines()]
    row["by"] = "jake (box, unverified)"
    _jsonl(directory / "controls.jsonl", [row])

    ended = read(directory, DEPARTURE)

    assert ended.stopped_because == "session ended by jake (box, unverified), before any run"


def test_a_restored_tally_counts_hangs(tmp_path):
    directory = _two_runs(tmp_path)
    _jsonl(directory / "trials.jsonl", [_line(1, "hang", 0.0, None, run=0)])
    assert read(directory, DEPARTURE).levels.session_tally.hangs == 1


@pytest.mark.parametrize("damage", ["config", "line"])
def test_a_record_from_before_xc026_cannot_be_resumed(tmp_path, damage):
    """Review Focus 5: no `already_delivered_today`, or a line with no `fluid_ml`."""
    config = _config()
    if damage == "config":
        del config["already_delivered_today"]
    line = (
        {"trial_number": 1, "run": 0, "outcome": "correct"}
        if damage == "line"
        else _line(1, "correct", 0.2, DEPARTURE + 1, run=0)
    )
    directory = _folder(tmp_path, config=config, runs=[_start(0, {})],
                        starts=[_pos(1, 1, 1, 1, 1, 1, 1, 1, 1, 1, run=0)], lines=[line])
    with pytest.raises(Unresumable, match="written before"):
        read(directory, DEPARTURE)
    assert "fluid so far cannot be known" in PREDATES


def test_a_record_with_lines_and_no_starts_cannot_be_resumed(tmp_path):
    """Lines with no `trial_starts.jsonl` were written before XC-026."""
    directory = _folder(tmp_path, runs=[_start(0, {})],
                        lines=[_line(1, "correct", 0.2, DEPARTURE + 1, run=0)])
    with pytest.raises(Unresumable, match="written before"):
        read(directory, DEPARTURE)


@pytest.mark.parametrize("name", ["config.json", "trials.jsonl", "trial_starts.jsonl",
                                  "runs.jsonl", "controls.jsonl", "parameter_changes.jsonl"])
def test_an_unreadable_record_cannot_be_resumed(tmp_path, name):
    directory = _two_runs(tmp_path, changes=[_change(1, "reward_correct", 0.2, 0.25, run=0)])
    with (directory / name).open("a") as handle:
        handle.write('{"torn": ')
    with pytest.raises(Unresumable, match=name.replace(".", r"\.")):
        read(directory, DEPARTURE)


def test_a_record_whose_config_names_another_session_cannot_be_resumed(tmp_path):
    """The final review's M5: a folder copied under another name is not that session."""
    directory = _folder(tmp_path, config=_config(session_id="2027-01-13_01"))

    with pytest.raises(Unresumable, match="config.json names session '2027-01-13_01'"):
        read(directory, DEPARTURE)


def test_a_line_with_no_start_cannot_be_resumed(tmp_path):
    directory = _two_runs(tmp_path)
    with (directory / "trials.jsonl").open("a") as handle:
        handle.write(json.dumps(_line(9, "correct", 0.25, DEPARTURE + 500, run=1)) + "\n")
    with pytest.raises(Unresumable, match="trial 9"):
        read(directory, DEPARTURE)


def test_a_start_row_missing_its_number_cannot_be_resumed(tmp_path):
    directory = _two_runs(tmp_path)
    with (directory / "trial_starts.jsonl").open("a") as handle:
        handle.write(json.dumps({"run": 1, "task": TASK}) + "\n")
    with pytest.raises(Unresumable, match="trial_number"):
        read(directory, DEPARTURE)


def test_the_last_write_is_the_newest_record_file(tmp_path):
    directory = _two_runs(tmp_path)
    for path in directory.iterdir():
        os.utime(path, (DEPARTURE + 5, DEPARTURE + 5))
    os.utime(directory / "trials.jsonl", (DEPARTURE + 777, DEPARTURE + 777))
    assert read(directory, DEPARTURE).last_written_at == DEPARTURE + 777


# --- fail closed (the controller's ruling on Task 4, 2026-10-01) -------------------
#
# A record the service cannot read must never stop `wlx taskd` starting, since
# `stranded.find` reads every stranded folder through `read` as it starts: whatever a
# record makes raise is `Unresumable`, naming it.


def test_an_infinite_number_in_a_record_cannot_be_resumed(tmp_path):
    """`int(Infinity)` raises `OverflowError`, which no narrower handler named."""
    directory = _two_runs(tmp_path)
    with (directory / "trial_starts.jsonl").open("a") as handle:
        handle.write(json.dumps(_pos(float("inf"), 6, 4, 4, 2, 2, 1, 2, 2, 1, run=1)) + "\n")
    assert "Infinity" in (directory / "trial_starts.jsonl").read_text()

    with pytest.raises(Unresumable, match="OverflowError"):
        read(directory, DEPARTURE)


def test_a_record_nested_past_the_parsers_depth_cannot_be_resumed(tmp_path):
    directory = _two_runs(tmp_path)
    (directory / "controls.jsonl").write_text("[" * 100_000 + "]" * 100_000 + "\n")

    with pytest.raises(Unresumable, match="RecursionError"):
        read(directory, DEPARTURE)


@pytest.mark.parametrize(
    "bounds",
    [
        {"ceilings": {"reward_correct": {"value": 0.05, "maximum": 10.0, "unit": "mL"}}},
        [],
        {"ceilings": [], "minima": {}},
        {"ceilings": {}, "minima": "daily_fluid"},
        None,
    ],
    ids=["no minima", "a list", "ceilings a list", "minima a string", "none"],
)
def test_a_config_whose_bounds_are_not_ceilings_and_minima_cannot_be_resumed(tmp_path, bounds):
    """What a resume compares the animal's bounds with (plan ruling 3) must be there to
    compare, so a `config.json` without it is refused, naming the file."""
    directory = _folder(tmp_path, config=_config(bounds=bounds))

    with pytest.raises(Unresumable, match=r"config\.json"):
        read(directory, DEPARTURE)


def test_a_record_that_does_not_say_what_its_session_was_for_cannot_be_resumed(tmp_path):
    config = _config()
    del config["session_kind"]

    with pytest.raises(Unresumable) as refused:
        read(_folder(tmp_path, config=config), DEPARTURE)

    assert str(refused.value) == PREDATES_KINDS


def test_a_record_whose_session_was_for_something_else_cannot_be_resumed(tmp_path):
    with pytest.raises(Unresumable, match="'demo', which is not training, piloting or recording"):
        read(_folder(tmp_path, config=_config(session_kind="demo")), DEPARTURE)


def test_a_restoration_says_what_its_session_is_for(tmp_path):
    assert read(_folder(tmp_path, config=_config(session_kind="piloting")), DEPARTURE).session_kind == "piloting"


def test_a_restoration_carries_what_the_session_accepted(tmp_path):
    directory = _folder(tmp_path)
    _jsonl(directory / "warnings.jsonl", [{
        "code": "head free", "detail": "the head is free",
        "accepted_in": ["training", "piloting", "recording"], "session_kind": "training",
        "by": {"kind": "box", "name": "jake"}, "at": DEPARTURE + 5.0, "at_local": "",
        "how": "open", "run": None,
    }])

    assert read(directory, DEPARTURE).accepted == (
        ("head free", "the head is free", ("training", "piloting", "recording"), Box("jake"),
         DEPARTURE + 5.0),
    )


def test_a_damaged_accepted_warning_row_makes_a_record_unresumable(tmp_path):
    directory = _folder(tmp_path)
    _jsonl(directory / "warnings.jsonl", [{"code": "head free"}])

    with pytest.raises(Unresumable, match="KeyError"):
        read(directory, DEPARTURE)


def _accepted_row(**over) -> dict:
    """One `warnings.jsonl` row as `SessionRecord.warning` writes it; each field given
    replaces its own."""
    row = {
        "code": "head free", "detail": "the head is free",
        "accepted_in": ["training", "piloting", "recording"], "session_kind": "training",
        "by": {"kind": "box", "name": "jake"}, "at": DEPARTURE + 5.0, "at_local": "",
        "how": "open", "run": None,
    }
    row.update(over)
    return row


@pytest.mark.parametrize("damage, named", [
    ({"code": 5}, "has a code that is not text"),
    ({"detail": None}, "has a detail that is not text"),
    ({"accepted_in": ["training", "demo"]}, "has an accepted_in that is not a list"),
    ({"accepted_in": "training"}, "has an accepted_in that is not a list"),
    ({"accepted_in": [1]}, "has an accepted_in that is not a list"),
    ({"accepted_in": {"training": 1}}, "has an accepted_in that is not a list"),
    ({"session_kind": "recording"},
     "has a session_kind of 'recording', and its config.json says the session is for 'training'"),
    ({"at": True}, "has an at that is not a finite number"),
    ({"at": "1700000005.0"}, "has an at that is not a finite number"),
    ({"at": float("inf")}, "has an at that is not a finite number"),
    ({"at": float("nan")}, "has an at that is not a finite number"),
    ({"by": "jake"}, "has a by that is not an actor's map or null"),
    ({"by": {"kind": "box", "name": "jake", "extra": 1}},
     "has a by that is not an actor's map or null"),
    # What `Entry` refuses (the engine B final review): `Session.resume` would raise on it.
    ({"code": "luminance-step ×2"},
     "is not a warning as the rig lists one (a warning's code never holds '×'"),
    ({"code": "a, b"}, "is not a warning as the rig lists one (a warning's code never holds ','"),
    ({"code": ""}, "is not a warning as the rig lists one (a warning's code is text, and this one is empty)"),
    ({"accepted_in": ["training", "training"]},
     "is not a warning as the rig lists one (a warning's accepted_in names 'training' twice)"),
], ids=["code", "detail", "unknown-kind", "kinds-as-text", "kind-not-text", "kinds-as-object",
         "session-kind", "at-bool", "at-text", "at-infinite", "at-nan", "by-text",
         "by-extra-field", "code-with-a-count", "code-with-a-comma", "code-empty", "kind-twice"])
def test_a_damaged_accepted_warning_row_is_refused_naming_its_field_never_coerced(
    tmp_path, damage, named
):
    """The engine B plan, call 12: a `warnings.jsonl` row that is not what
    `SessionRecord.warning` writes makes the record unresumable through `read`, so
    `stranded.find` marks it so, rather than a resume `Session.resume` would then refuse or a
    value coerced into something nobody accepted. The second row, after one that is whole."""
    directory = _folder(tmp_path)
    _jsonl(directory / "warnings.jsonl",
           [_accepted_row(), _accepted_row(**{"code": "other", **damage})])

    with pytest.raises(Unresumable) as refused:
        read(directory, DEPARTURE)

    assert str(refused.value).startswith(f"its warnings.jsonl row 2 {named}")
    assert str(refused.value).endswith("; end it instead")


@pytest.mark.parametrize("where", ["config-kind", "row-kind", "config-session-id"])
def test_a_value_of_ten_thousand_characters_is_quoted_cut(tmp_path, where):
    """The engine B final review: why a session cannot be resumed is `Stranded.why`, shown on
    every idle frame and the page's banner, so a session kind or a session id the record holds
    is quoted cut, as `link._quoted` cuts a value."""
    value = "k" * 10_000
    if where == "config-kind":
        directory = _folder(tmp_path, config=_config(session_kind=value))
    elif where == "row-kind":
        directory = _folder(tmp_path)
        _jsonl(directory / "warnings.jsonl", [_accepted_row(session_kind=value)])
    else:
        directory = _folder(tmp_path, config=_config(session_id=value))

    with pytest.raises(Unresumable) as refused:
        read(directory, DEPARTURE)

    said = str(refused.value)
    assert _quoted(value) in said and "k" * (TEXT_LIMIT + 1) not in said
    assert said.endswith("; end it instead") and len(said) < 2 * TEXT_LIMIT + 200


def test_a_warning_accepted_by_nobody_at_a_whole_second_reads_back_as_written(tmp_path):
    directory = _folder(tmp_path)
    _jsonl(directory / "warnings.jsonl", [_accepted_row(by=None, at=1_700_000_005)])

    ((*_, by, at),) = read(directory, DEPARTURE).accepted
    assert by is None and at == 1_700_000_005.0 and isinstance(at, float)
