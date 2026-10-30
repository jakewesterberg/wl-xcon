"""Pre-flight (P4d-2b spec §6.2) under S9a §10's one rule (PI, 2026-09-19): fail blocks,
unknown proceeds only on a named acknowledgement written into the record, pass proceeds."""

from __future__ import annotations

import dataclasses
import shutil
from pathlib import Path

import pytest

from _rig import DIRECT, STEREOSCOPE
import _sessions
from _sessions import WALL, session
from wl_xcon import preflight
from wl_xcon.actor import Box
from wl_xcon.check import parameters_used
from wl_xcon.cli import _load_allocation, _load_task
from wl_xcon.findings import NOT_RECORDING, SESSION_KINDS
from wl_xcon.link import NOTE_LIMIT, Preflight, PreflightItem
from wl_xcon.photometry import SRGB
from wl_xcon.task import Block, Condition, P, Param, Plan, Task
from wl_xcon.warnlist import Entry
from wl_xcon.welfare import Absent, Deployment, Simulated

ALLOCATION = _load_allocation(Path("tasks/allocation.py"))
TASK = Path("tasks/fixation_detection.py")


def _trial():
    """The reference task's one trial structure (engine build C1)."""
    return _load_task(TASK).trial


def _as_task(trial) -> Task:
    """`trial` as a task's one structure, which is what `preflight.values` reads."""
    return Task({"detection": trial}, default="detection")


def test_a_task_that_passes_its_checks_in_the_sessions_setup_passes():
    item, trial, _ = preflight.task(TASK, ALLOCATION, DIRECT, SRGB)

    assert (item.name, item.result) == ("task checks", "pass")
    assert "direct view" in item.said and trial is not None


def test_a_task_written_for_the_other_setup_fails_on_its_field_and_warns_of_its_setup():
    """XC-352's A12: the setups' mismatch is a warning; the reference task's ±16° beyond the
    stereoscope's mask still fails (A15, kept)."""
    item, _, findings = preflight.task(TASK, ALLOCATION, STEREOSCOPE, SRGB)

    assert item.result == "fail" and "stimulus-off-screen" in item.said
    assert "wrong-setup" not in item.said
    assert [f.code for f in findings if f.is_warning and f.code == "wrong-setup"] == ["wrong-setup"]


@pytest.mark.parametrize(
    ("text", "said"),
    [("x = 1\n", "defines 0 task objects"), ("raise ValueError('broken on purpose')\n", "did not load")],
)
def test_a_task_file_that_does_not_load_fails_rather_than_raising(tmp_path, text, said):
    bad = tmp_path / "bad.py"
    bad.write_text(text)

    item, trial, _ = preflight.task(bad, ALLOCATION, DIRECT, SRGB)

    assert item.result == "fail" and said in item.said and trial is None


def _checks_that_raise(monkeypatch) -> None:
    """`check_task` raising `TypeError` on a shape it does not expect, as it did on a window placed
    by a whole-point setting until XC-156 was fixed (its `_closest_approach`, since removed,
    unpacked the place as a pair): no task of the repo's makes the checks raise now, so the fault is put there."""
    def unpack(*_args, **_kwargs):
        raise TypeError("cannot unpack non-iterable P object")

    monkeypatch.setattr(preflight, "check_task", unpack)


def test_a_task_whose_checks_raise_on_it_fails_rather_than_raising(monkeypatch):
    """Fix round 1 of Task 8: a task file is code, and `check()` is run on it -- and can
    raise on a shape it does not expect (it did, XC-156; the fault is put there now by a
    stand-in). Its fault is this item's, as a failed load is, and never the caller's: the
    service reached this on every check and start, and nothing above it contained the
    exception."""
    _checks_that_raise(monkeypatch)

    item, trial, _ = preflight.task(TASK, ALLOCATION, DIRECT, SRGB)

    assert (item.name, item.result) == ("task checks", "fail")
    assert item.said.startswith(
        f"{TASK.name}'s load-time checks did not finish: TypeError: cannot unpack non-iterable")
    assert trial is not None, "it loaded; its checks did not finish"


def test_a_task_with_a_window_placed_by_a_whole_point_setting_is_checked_and_warned_of(tmp_path):
    """XC-156: the task the checks used to raise on loads, is checked to the end, and is warned of
    where its target's choices can overlap its fixation window's (a warning, never the item's
    fail), saying which choice."""
    item, trial, findings = preflight.task(
        _sessions.whole_point_task(tmp_path), ALLOCATION, DIRECT, SRGB)

    assert item.result == "pass" and trial is not None
    (found,) = [f for f in findings if f.code == "overlapping-windows"]
    assert "by setting 'target_point'" in found.detail


def test_the_task_item_returns_its_findings_checked_against_the_calibration():
    item, trial, findings = preflight.task(TASK, ALLOCATION, DIRECT, SRGB)

    assert item.result == "pass" and trial is not None
    assert [f.code for f in findings] == ["contrast-on-default"]



def test_the_task_item_warns_of_a_position_its_file_computes_from_cos_and_sin(tmp_path):
    """The path a `wlx taskd` session takes (the PI, 2026-10-19): the pre-flight's task item reads
    the task file it loaded, so a position built from `cos` and `sin` is a warning it returns, to
    be accepted with the others, and never this item's fail."""
    source = TASK.read_text(encoding="utf-8").replace(
        'FIX = Stimulus("fix", at=(0.0, 0.0),', 'FIX = Stimulus("fix", at=(math.cos(0.0) - 1.0, 0.0),')
    path = tmp_path / "computed.py"
    path.write_text("import math\n" + source, encoding="utf-8")

    item, _, findings = preflight.task(path, ALLOCATION, DIRECT, SRGB)

    assert item.result == "pass"
    assert "computed-position" in [f.code for f in findings]

A = Entry("a", "one", NOT_RECORDING)
B = Entry("b", "two", SESSION_KINDS)


def test_the_warnings_item_fails_on_one_the_kind_does_not_accept():
    item, owed = preflight.warnings([A, B], "recording", frozenset())

    assert (item.name, item.result, owed) == ("warnings", "fail", [])
    assert item.said == "a recording session does not accept a: one"


def test_the_warnings_item_is_an_unknown_listing_each_not_yet_accepted():
    item, owed = preflight.warnings([A, B], "training", {A.key})

    assert (item.result, owed) == ("unknown", [B])
    assert "b: two" in item.said and "a: one" not in item.said


def test_the_warnings_item_passes_when_each_was_accepted_or_there_are_none():
    assert preflight.warnings([A, B], "training", {A.key, B.key})[0].result == "pass"
    assert preflight.warnings([], "recording", frozenset())[0] == PreflightItem("warnings", "pass", "none")


def test_an_unknown_says_each_warning_it_asks_to_accept_whole():
    """XC-353 (the PI, 2026-10-11: warnings "with an explanation of why it may not be a good
    idea"): one acknowledgement of this item accepts every warning it lists, so it says each
    whole -- its code and every word of its sentence -- however long. What the start accepts is
    the warnings themselves, and each keeps every word for `warnings.jsonl`."""
    long = Entry("long", "x" * 2_000 + " the end", SESSION_KINDS)

    item, owed = preflight.warnings([long], "training", frozenset())

    assert item.result == "unknown"
    assert item.said == "1 not yet accepted this session (long): long: " + "x" * 2_000 + " the end"
    assert owed == [long]


def test_an_unknown_names_every_warning_however_long_their_names_and_never_fails_for_it():
    """XC-352's B1 (the PI, 2026-10-11, approving the audit): a display limit is no reason to
    refuse a run. Twenty codes whose names together run past `link.NOTE_LIMIT` failed the item
    before; each is named now, and the item asks to accept them."""
    many = [Entry(f"code-{i:02d}-" + "c" * 40, "x", SESSION_KINDS) for i in range(20)]

    item, owed = preflight.warnings(many, "training", frozenset())

    assert (item.result, owed) == ("unknown", many)
    head = item.said.split("): ")[0]
    assert len(head) > NOTE_LIMIT and all(entry.code in head for entry in many)


def test_a_fail_accepts_nothing_and_is_cut_as_the_refusal_quoting_it_is():
    """A warning the session's kind does not accept fails the item, which accepts nothing, so
    its sentence is cut to `link.NOTE_LIMIT` characters and "…": the gate's refusal quotes it."""
    refused = Entry("refused", "y" * 2_000, ())

    item, owed = preflight.warnings([refused], "training", frozenset())

    assert (item.result, len(item.said), owed) == ("fail", NOTE_LIMIT + 1, [])
    assert item.said.startswith("a training session does not accept refused: yyy")


def test_a_repeated_code_is_named_once_with_its_count_in_the_order_codes_first_appear():
    """Fix round 2 of Task 12: a task gives one `luminance-step` per pattern whose mean differs
    from the background. Named once each, thirty of them would push the head past the limit
    and fail every run; named once with their count, every distinct warning is named in a
    short head, and the item asks to accept them all. A code's later repeats do not move it."""
    default = Entry("default calibration", "the default", SESSION_KINDS)
    steps = [Entry("luminance-step", f"pattern {i}'s mean differs", SESSION_KINDS) for i in range(30)]
    free = Entry("head free", "the head is free", SESSION_KINDS)

    item, owed = preflight.warnings([default, steps[0], free, *steps[1:]], "training", frozenset())

    assert (item.result, owed) == ("unknown", [default, steps[0], free, *steps[1:]])
    assert item.said.startswith(
        "32 not yet accepted this session (default calibration, luminance-step ×30, head free): "
        "default calibration: the default; luminance-step: pattern 0's mean differs; head free:"
    )


@pytest.mark.parametrize(
    ("given", "result", "said"),
    [
        ({"fix_hold": 0.3}, "pass", "each declared and in range"),
        # Outside its range: a warning, never this item's fail (XC-352's D2; `preflight.beyond`).
        ({"fix_hold": 99.0}, "pass", "1 outside its declared range ('fix_hold')"),
        ({"no_such": 1.0}, "fail", "not a parameter this task declares"),
        ({"fix_hold": "long"}, "fail", "takes a number"),
        ({"fix_hold": float("nan")}, "fail", "not a real number"),
        ({"fix_hold": float("inf")}, "fail", "not a real number"),
        ({"fix_hold": float("-inf")}, "fail", "not a real number"),
    ],
)
def test_starting_values_are_checked_against_the_tasks_declarations(given, result, said):
    item = preflight.values(_as_task(_trial()), given)

    assert (item.name, item.result) == ("starting values", result) and said in item.said


def _declaring(declared: Param):
    """The reference task with `fix_hold` declared as `declared` instead."""
    trial = _trial()
    return _as_task(dataclasses.replace(
        trial, params=[declared if p.name == "fix_hold" else p for p in trial.params]
    ))


@pytest.mark.parametrize(
    "declared",
    [
        Param("fix_hold", unit="s", low="0.05", high=2.0),
        Param("fix_hold", unit="s", choices=3),
    ],
    ids=["a bound typed as text", "choices that are not a collection"],
)
def test_a_value_whose_declaration_cannot_be_compared_fails_rather_than_raising(declared):
    """The b3a-1 final review, Important 1: `Param` checks none of its fields, so a bound
    typed as text passes `check()` and then raised `TypeError` here -- out of the
    service's pre-flight, ending `wlx taskd` with the animal out. It fails that value,
    naming it, and every other value is still checked."""
    item = preflight.values(_declaring(declared), {"fix_hold": 0.3, "fix_acquisition": 99.0})

    assert (item.name, item.result) == ("starting values", "fail")
    assert "'fix_hold' could not be checked against its declaration: TypeError: " in item.said
    # Outside its range, a warning (XC-352's D2): never among this item's fails.
    assert "'fix_acquisition'" not in item.said


def test_declarations_that_cannot_be_read_fail_every_value_rather_than_raising():
    item = preflight.values(_as_task(dataclasses.replace(_trial(), params=None)), {"fix_hold": 0.3})

    assert (item.name, item.result) == ("starting values", "fail")
    assert item.said.startswith("the task's parameter declarations could not be read: TypeError: ")


def test_a_bare_exit_from_a_task_or_bounds_file_still_says_something(tmp_path):
    bad = tmp_path / "bad.py"
    bad.write_text("import sys\nsys.exit()\n")

    item, _, _ = preflight.task(bad, ALLOCATION, DIRECT, SRGB)
    kept = preflight.files(bad, "A", None)[0]

    assert item.result == kept.result == "fail"
    assert item.said.strip() and kept.said.strip() and "bad.py" in item.said


def test_the_animals_files_pass_when_they_load_and_name_it(tmp_path):
    folder = tmp_path / "REFERENCE"
    folder.mkdir()
    shutil.copy("tasks/reference_bounds.py", folder / "bounds.py")
    shutil.copy("tasks/reference_subject.py", folder / "settings.py")

    items = preflight.files(folder / "bounds.py", "REFERENCE", folder / "settings.py")

    assert [(i.name, i.result) for i in items] == [
        ("bounded config", "pass"), ("subject settings", "pass"),
    ]


def test_settings_that_name_another_animal_or_an_undrawn_half_ipd_pass_saying_so(tmp_path):
    """XC-352's C7 and C8 (the PI, 2026-10-11): warnings, listed with the run's (the session's
    `setup_warnings`), so the re-read passes, saying whose settings they are; only a file that no
    longer loads fails."""
    folder = tmp_path / "A"
    folder.mkdir()
    shutil.copy("tasks/reference_bounds.py", folder / "bounds.py")
    (folder / "settings.py").write_text(
        "from wl_xcon.geometry import SubjectSettings\n"
        "SETTINGS = SubjectSettings(subject='B', half_ipd_cm=2.4)\n")

    _, settings = preflight.files(folder / "bounds.py", "REFERENCE", folder / "settings.py")

    assert settings.result == "pass"
    assert "gives 'B''s half-IPD of 2.4 cm" in settings.said


def test_the_animals_files_fail_when_they_name_another_or_do_not_load(tmp_path):
    folder = tmp_path / "B"
    folder.mkdir()
    shutil.copy("tasks/reference_bounds.py", folder / "bounds.py")
    (folder / "settings.py").write_text("SETTINGS = None\n")

    items = preflight.files(folder / "bounds.py", "B", folder / "settings.py")

    assert [i.result for i in items] == ["fail", "fail"]
    assert "'REFERENCE'" in items[0].said and "must define SETTINGS" in items[1].said


def test_the_out_of_cage_item_passes_while_the_mark_is_in_and_the_limit_is_not_reached(tmp_path):
    made = session(tmp_path)
    made.left_cage(at=WALL - 60)

    item = preflight.out_of_cage(made)

    assert (item.name, item.result) == ("out of cage", "pass")


def test_the_out_of_cage_item_fails_with_no_departure_or_past_the_limit(tmp_path):
    """Spec §6.1: "reached between runs, it refuses a new run"."""
    unmarked = session(tmp_path / "a")
    past = session(tmp_path / "b", out_of_cage=600.0)
    past.left_cage(at=WALL - 300)
    past.wall_clock = lambda: WALL + 400

    item = preflight.out_of_cage(unmarked)
    assert item.result == "fail" and "not recorded as out of its cage" in item.said
    item = preflight.out_of_cage(past)
    assert item.result == "fail" and "ceiling" in item.said and "End session" in item.said


def test_the_out_of_cage_item_fails_for_a_head_fixed_session_never_fixed(tmp_path):
    made = session(tmp_path, deployment=Deployment.RIG_FIXED)
    made.left_cage(at=WALL - 60)

    item = preflight.out_of_cage(made)

    assert item.result == "fail" and "not recorded as head-fixed" in item.said


def test_the_out_of_cage_item_fails_once_the_animal_is_recorded_home(tmp_path):
    made = session(tmp_path)
    made.left_cage(at=WALL - 300)
    made.returned_to_cage(at=WALL - 100)

    item = preflight.out_of_cage(made)

    assert item.result == "fail" and "already recorded as back" in item.said


def test_a_cage_side_session_passes_and_does_not_claim_a_departure(tmp_path, monkeypatch):
    real = _sessions.bounds

    def no_ceiling(**kwargs):
        made = real(**kwargs)
        kept = {k: v for k, v in made.ceilings.items() if k != "out_of_cage"}
        return dataclasses.replace(made, ceilings=kept)

    monkeypatch.setattr(_sessions, "bounds", no_ceiling)
    made = session(tmp_path, deployment=Deployment.CAGE_SIDE)

    item = preflight.out_of_cage(made)

    assert item.result == "pass" and "no out-of-cage interval" in item.said
    assert "marked" not in item.said


def test_inside_the_warning_band_the_item_passes_with_the_warning_as_its_sentence(tmp_path):
    made = session(tmp_path, out_of_cage=600.0)
    made.left_cage(at=WALL - 300)

    item = preflight.out_of_cage(made)

    assert item.result == "pass" and item.said == made.welfare.approaching_limit(WALL)
    assert "300 s left" in item.said


def test_exactly_at_the_limit_the_item_says_so_and_passes_as_must_stop_does_not_fire(tmp_path):
    made = session(tmp_path, out_of_cage=600.0)
    made.left_cage(at=WALL - 300)
    made.wall_clock = lambda: WALL + 300
    assert made.welfare.must_stop(WALL + 300) is None

    item = preflight.out_of_cage(made)

    assert item.result == "pass" and "at its 600 s out-of-cage limit" in item.said
    assert "not reached" not in item.said


def test_what_nothing_measures_is_unknown_and_says_what_it_waits_for():
    """S9a §10: an absent pump calibration is acknowledgeable only while no real pump
    driver exists -- a dated claim, named so it can be found (V10)."""
    for pump in (Simulated(), Absent()):
        items = preflight.unmeasured(pump)

        assert [(i.name, i.result) for i in items] == [
            ("pump calibration", "unknown"), ("eye tracker", "unknown"),
        ]
        assert "V10" in items[0].said and "driver" in items[0].said
        assert "V3" in items[1].said


def test_a_real_pump_makes_the_calibration_a_fail_not_an_acknowledgeable_unknown():
    class ValvePump:
        def deliver(self, ml):
            pass

    items = preflight.unmeasured(ValvePump())

    assert (items[0].name, items[0].result) == ("pump calibration", "fail")
    assert "V10" in items[0].said and "driver" in items[0].said
    assert items[1].result == "unknown"


def _checked(*results: str, mark: bool = True) -> Preflight:
    items = [PreflightItem(f"item {i}", r, f"said {i}") for i, r in enumerate(results)]
    if mark:
        items.append(PreflightItem("out of cage", "pass", "marked"))
    return Preflight("t.py", tuple(items))


def test_the_gate_lets_every_pass_through():
    assert preflight.gate(_checked("pass", "pass"), ()) is None


def test_the_gate_blocks_any_fail_even_when_every_unknown_is_acknowledged():
    why = preflight.gate(_checked("pass", "fail", "unknown"), ("item 2",))

    assert why.startswith("pre-flight failed") and "item 1: said 1" in why


def test_naming_a_failed_item_never_unblocks_it():
    why = preflight.gate(_checked("fail", "unknown"), ("item 0", "item 1"))

    assert why.startswith("pre-flight failed") and "item 0: said 0" in why


def test_the_gate_lets_an_unknown_through_only_when_it_is_acknowledged_by_name():
    assert "item 1" in preflight.gate(_checked("unknown", "unknown"), ("item 0",))
    assert preflight.gate(_checked("unknown", "unknown"), ("item 0", "item 1")) is None


def test_a_bare_string_is_not_an_acknowledgement_it_is_a_substring_trap():
    said = "I did not check item 0 or item 1"

    why = preflight.gate(_checked("unknown", "unknown"), said)

    assert why is not None and "names" in why


def test_the_gate_fails_closed_on_a_result_it_does_not_know():
    assert preflight.gate(_checked("pass", "maybe"), ()).startswith("pre-flight failed")


def test_a_preflight_without_the_out_of_cage_item_does_not_open_the_gate():
    for empty in (Preflight("t.py", ()), _checked("pass", mark=False)):
        why = preflight.gate(empty, ())

        assert why.startswith("pre-flight failed") and "out of cage" in why


def test_the_record_says_who_acknowledged_each_unknown_and_no_one_else():
    rows = preflight.rows(
        _checked("pass", "unknown", "unknown"), Box("jake"), ("item 2",)
    )

    assert [(r["name"], r["result"], r["acknowledged_by"]) for r in rows] == [
        ("item 0", "pass", None),
        ("item 1", "unknown", None),
        ("item 2", "unknown", {"kind": "box", "name": "jake"}),
        ("out of cage", "pass", None),
    ]


@pytest.mark.parametrize("by", [Box(""), Box("   "), None, "jake"])
def test_the_record_refuses_an_acknowledgement_nobody_signed(by):
    with pytest.raises(ValueError, match="who acknowledged"):
        preflight.rows(_checked("unknown"), by, ("item 0",))


def test_a_blank_name_is_fine_when_nothing_was_acknowledged():
    rows = preflight.rows(_checked("pass", "unknown"), None, ())

    assert all(r["acknowledged_by"] is None for r in rows)


def test_a_carried_acknowledgement_is_recorded_under_who_gave_it_and_marked_carried():
    rows = preflight.rows(_checked("unknown", "unknown"), Box("ann"), ("item 1",),
                          carried={"item 0": Box("jake")})

    assert [(r["name"], r["acknowledged_by"], r["carried"]) for r in rows[:2]] == [
        ("item 0", {"kind": "box", "name": "jake"}, True),
        ("item 1", {"kind": "box", "name": "ann"}, False)]


def test_only_an_unknown_nobody_named_here_is_recorded_as_carried():
    """A name acknowledged here is this start's, whoever accepted it before; and a carried
    name on an item that is not unknown carries nothing, as a pass needs no acknowledgement."""
    rows = preflight.rows(_checked("unknown", "pass"), Box("ann"), ("item 0",),
                          carried={"item 0": Box("jake"), "item 1": Box("jake")})

    assert [(r["name"], r["acknowledged_by"], r["carried"]) for r in rows[:2]] == [
        ("item 0", {"kind": "box", "name": "ann"}, False),
        ("item 1", None, False)]


def test_parameters_used_names_every_parameter_the_task_references():
    """From the task down -- states, windows and the stimuli they name -- as
    `run._resolve` meets them in a trial."""
    assert parameters_used(_trial()) == frozenset({
        "fix_hold", "fix_acquisition", "fix_window", "response_deadline", "target_hold",
        "target_appearance", "target_x", "target_y", "target_window",
        "fix_luminance", "target_luminance",
    })


def test_a_run_given_nothing_starts_from_the_tasks_own_values():
    """What the page sends (P4d-2b spec §6.2): no values, and the task's own pass."""
    item = preflight.values(_as_task(_trial()), {})

    assert (item.result, item.said) == ("pass", "10 starting value(s), each declared and in range")


def _starting(**starts):
    """The reference task with the named parameters' own `start` replaced."""
    trial = _trial()
    return _as_task(dataclasses.replace(
        trial,
        params=[
            dataclasses.replace(param, start=starts[param.name]) if param.name in starts else param
            for param in trial.params
        ],
    ))


def test_a_number_the_task_uses_that_nothing_gives_a_value_fails_naming_it():
    """Review Focus 2 (the b3a-2 plan, decision 2). A run with a parameter its trials
    resolve and no value for it faulted at its first trial -- `run._resolve`: "no value
    bound for parameter" -- after `RUN_START`. The pre-flight now fails it, naming each,
    so the start is refused first. An appearance, which nothing resolves before S4's
    display exists, is not refused unset."""
    trial = _starting(fix_hold=None, fix_window=None)

    item = preflight.values(trial, {})

    assert (item.name, item.result) == ("starting values", "fail")
    assert "'fix_hold' is used by the task and has no starting value" in item.said
    assert "'fix_window' is used by the task and has no starting value" in item.said
    assert "target_appearance" not in item.said
    assert preflight.values(trial, {"fix_hold": 0.3, "fix_window": 2.0}).result == "pass"


def _unchecked(trial, name: str, start: float):
    """`trial` with `name`'s start set past `Param`'s own refusal (the b3a-2 final review,
    m2), which a task file cannot do: what the pre-flight's second line is for."""
    params = []
    for param in trial.params:
        if param.name == name:
            param = dataclasses.replace(param, start=None)
            object.__setattr__(param, "start", start)
        params.append(param)
    return dataclasses.replace(trial, params=params)


def test_a_tasks_own_start_outside_its_range_is_held_as_a_sent_value_is():
    """`Param` refuses such a start as the task is built (m2), so a task file cannot
    declare one; the pre-flight still holds every merged value to its range, which outside it
    is a warning since XC-352's D2 (the PI, 2026-10-11)."""
    with pytest.raises(ValueError, match="'fix_hold'.*99.0 is above"):
        _starting(fix_hold=99.0)
    item = preflight.values(_as_task(_unchecked(_trial(), "fix_hold", 99.0)), {})

    assert item.result == "pass" and "1 outside its declared range ('fix_hold')" in item.said
    assert preflight.values(
        _as_task(_unchecked(_trial(), "fix_hold", 99.0)), {"fix_hold": 0.3}
    ).said == "10 starting value(s), each declared and in range", (
        "what was sent is what the run starts with"
    )


def test_a_starting_value_outside_its_range_is_checked_widened_and_what_breaks_fails_the_item():
    """XC-352's D2 (the PI, 2026-10-11): the load-time checks run again with the range widened to
    the value (`preflight.beyond`); what breaks the run -- here the target off direct view's
    screen -- fails the starting values item, saying which value, and the rest are warnings."""
    task = _load_task(TASK)

    off = preflight.beyond(task, {"target_x": 40.0}, ALLOCATION, DIRECT, SRGB, None)
    wide = preflight.beyond(task, {"fix_window": 7.0}, ALLOCATION, DIRECT, SRGB, None)
    item = preflight.values(task, {"target_x": 40.0}, [f for f in off if f.blocking])

    assert [(f.code, f.blocking) for f in wide] == [("outside-range", False)]
    assert {f.code for f in off if f.blocking} == {"stimulus-off-screen"}
    assert item.result == "fail"
    assert "stimulus-off-screen: with 'target_x' at 40, outside its declared range: " in item.said


def test_a_check_that_cannot_run_widened_fails_closed(tmp_path, monkeypatch):
    """Nothing a task's declarations hold raises out of the pre-flight: a widened check that
    raises refuses the values, saying what is known -- the checks could not run, and why -- and
    never that a value is outside its range, which none may be (Task 10's review, M3)."""
    monkeypatch.setattr(preflight, "beyond_range", lambda *a, **k: 1 / 0)

    (refusal,) = preflight.beyond(_load_task(TASK), {"fix_window": 7.0}, ALLOCATION, DIRECT, SRGB, None)

    assert refusal.blocking and refusal.code == "outside-range"
    assert refusal.detail.startswith(
        "the load-time checks could not be run again with each range widened to its starting "
        "value (ZeroDivisionError: division by zero), so what the starting values would break is "
        "unknown")


def test_a_bound_that_cannot_be_compared_refuses_the_values_without_saying_one_is_outside():
    """Task 10's review, M3: a bound typed as text cannot be compared with a value, so the widened
    checks cannot run; the refusal says so, and why, and not that a value is outside its range --
    0.3 s is inside the 0.05-2 s meant."""
    task = _declaring(Param("fix_hold", unit="s", low="0.05", high=2.0))

    (refusal,) = preflight.beyond(task, {"fix_hold": 0.3}, ALLOCATION, DIRECT, SRGB, None)

    assert refusal.blocking and refusal.code == "outside-range"
    assert "could not be run again with each range widened to its starting value (TypeError: " in (
        refusal.detail)
    assert "is outside its declared range" not in refusal.detail


def test_a_parameter_used_but_never_declared_fails_naming_it():
    """`check()`'s undeclared-parameter finding walks the states only; a window's radius
    naming nothing declared passed both and faulted after `RUN_START`."""
    trial = _trial()
    windows = [dataclasses.replace(trial.windows[0], radius=P("fix_windw"))] + list(trial.windows[1:])
    item = preflight.values(_as_task(dataclasses.replace(trial, windows=windows)), {})

    assert item.result == "fail"
    assert "'fix_windw' is used by the task and is not declared" in item.said


def test_a_task_file_from_before_the_task_object_fails_its_preflight_saying_why(tmp_path):
    """Review Focus 1: a file with a trial and no task object is refused by its loader, which says
    how to wrap it; the item fails and nothing raises."""
    bare = tmp_path / "bare.py"
    bare.write_text("from wl_xcon.task import After, On, Outcome, State, Trial\n"
                    "t = Trial(start='a', states=[State('a', go=[On(After(1.0), Outcome.CORRECT)])])\n")

    item, task, _ = preflight.task(bare, ALLOCATION, DIRECT, SRGB)

    assert (item.result, task) == ("fail", None)
    assert "defines 0 task objects" in item.said and "wraps its trials in one Task" in item.said


def test_a_task_whose_setting_says_nothing_of_what_it_means_fails_its_preflight(tmp_path):
    text = TASK.read_text()
    was = '        Param("fix_hold", unit="s", low=0.05, high=2.0, start=0.3),\n'
    assert text.count(was) == 1
    unexplained = tmp_path / "unexplained.py"
    unexplained.write_text(text.replace(
        was, was + '        Param("cue_delay", unit="s", low=0.0, high=1.0, start=0.2),\n'))

    item, task, _ = preflight.task(unexplained, ALLOCATION, DIRECT, SRGB)

    assert item.result == "fail" and "undeclared-meaning" in item.said and task is not None


def test_a_run_needs_a_value_for_every_number_any_of_its_structures_uses():
    """The engine C1 plan's call 15: a plain run's starting values cover every trial structure its
    task can play, failing closed; a run of a plan, the structures its conditions play (engine
    build C2b, below)."""
    trial = _trial()
    cued = dataclasses.replace(
        trial,
        params=[*trial.params, Param("cue_delay", unit="s", low=0.0, high=1.0)],
        windows=[dataclasses.replace(trial.windows[0], radius=P("cue_delay")), *trial.windows[1:]],
    )
    task = Task({"detection": trial, "cued": cued}, default="detection")

    item = preflight.values(task, {})

    assert item.result == "fail"
    assert "'cue_delay' is used by the task and has no starting value" in item.said
    assert preflight.values(task, {"cue_delay": 0.2}).result == "pass"


def test_a_run_of_a_plan_needs_values_for_the_structures_its_conditions_play_only():
    """Engine build C2b: a plan's run plays the structures its conditions name, so a number only
    another structure uses needs no starting value; and a number every condition playing its
    structure sets is given by the plan."""
    trial = _trial()
    cued = dataclasses.replace(
        trial,
        params=[*trial.params, Param("cue_delay", unit="s", low=0.0, high=1.0)],
        windows=[dataclasses.replace(trial.windows[0], radius=P("cue_delay")), *trial.windows[1:]],
    )
    plain = Plan([Block("b", [Condition("c", {}, target=1)])])
    cueing = Plan([Block("b", [Condition("c", {"cue_delay": 0.2}, target=1, structure="cued"),
                               Condition("d", {}, target=1)])])
    half = Plan([Block("b", [Condition("c", {"cue_delay": 0.2}, target=1, structure="cued"),
                             Condition("d", {}, target=1, structure="cued")])])
    task = Task({"detection": trial, "cued": cued}, default="detection",
                plans={"plain": plain, "cueing": cueing, "half": half})

    assert preflight.values(task, {}, plan="plain").result == "pass"
    assert preflight.values(task, {}, plan="cueing").result == "pass"
    item = preflight.values(task, {}, plan="half")
    assert item.result == "fail" and "'cue_delay' is used by the task" in item.said


def test_a_place_with_no_value_fails_the_starting_values_and_an_appearance_does_not(tmp_path):
    """XC-415 (the PI, 2026-10-30: "Refuse to start"): a setting with choices that places a
    stimulus -- here a whole position, which no starting value and nothing over the wire can give --
    left without a value fails the starting values, naming it and where it places, so `gate`
    refuses the start; one left to the run is otherwise not refused only where it places nothing (an
    appearance, the reference task's `target_appearance`). A plan whose every condition playing the
    structure sets it gives it; one that leaves it unset in a condition fails, naming that
    condition."""
    from wl_xcon.task import Polar

    task = _load_task(_sessions.cue_task(tmp_path))
    item = preflight.values(task, {})

    assert item.result == "fail"
    assert item.said == (
        "setting 'cue_pos' places the position of stimulus 'cue' as state 'await_fix' shows it and "
        "has no value: neither the task nor the run gives it one, and a stimulus placed by no "
        "value cannot be drawn, so the run does not start")
    planned = dataclasses.replace(task, plans={
        "set": Plan([Block("b", [Condition("c", {"cue_pos": Polar(8.0, 0.0)}, target=1)])]),
        "unset": Plan([Block("b", [Condition("c", {"cue_pos": Polar(8.0, 0.0)}, target=1),
                                   Condition("d", {}, target=1)])])})
    assert preflight.values(planned, {}, plan="set").result == "pass"
    unset = preflight.values(planned, {}, plan="unset")
    assert unset.result == "fail"
    assert "'cue_pos' places the position of stimulus 'cue'" in unset.said
    assert "has no value in condition 'd' of block 'b'" in unset.said
    assert preflight.values(_load_task(TASK), {}).result == "pass"


def test_a_plan_its_task_does_not_declare_fails_the_task_checks(tmp_path):
    """Engine build C2b: so `gate` refuses a start naming one, `Service._start` unchanged in
    that."""
    path = _sessions.planned_task(tmp_path, '{"short": Plan([Block("b", [Condition("c", {}, '
                                            'target=1)])])}')

    named, _, _ = preflight.task(path, ALLOCATION, DIRECT, SRGB, plan="short")
    missing, _, _ = preflight.task(path, ALLOCATION, DIRECT, SRGB, plan="long")

    assert named.result == "pass"
    assert missing.result == "fail"
    assert missing.said == "the task declares no plan 'long'; its plans are 'short'"


def test_each_conditions_values_are_held_to_their_ranges_as_starting_values_are(tmp_path):
    """Engine build C2b, under the PI's rule of 2026-10-11 (XC-352's D2): a value a condition sets
    outside its range is a warning naming the condition, and one that would break the run -- a
    target off the screen -- fails the starting values, naming it too."""
    path = _sessions.planned_task(tmp_path, (
        '{"wide": Plan([Block("b", [Condition("near", {"target_x": 5.0}, target=1), '
        'Condition("past", {"target_x": 17.0}, target=1)])]), '
        '"off": Plan([Block("b", [Condition("away", {"target_x": 16.0, "target_y": 40.0}, '
        'target=1)])])}'))
    task = _load_task(path)

    wide = preflight.beyond(task, {}, ALLOCATION, DIRECT, SRGB, None, plan="wide")
    off = preflight.beyond(task, {}, ALLOCATION, DIRECT, SRGB, None, plan="off")

    assert [f.code for f in wide] == ["outside-range"]
    assert wide[0].detail.startswith("in plan 'wide', block 'b', condition 'past': 'target_x'")
    assert not wide[0].blocking
    refused = [f for f in off if f.blocking]
    assert refused and all("condition 'away'" in f.detail for f in refused)
    assert preflight.values(task, {}, refused, plan="off").result == "fail"
    assert preflight.beyond(task, {}, ALLOCATION, DIRECT, SRGB, None) == []
