"""What a task declares beyond its trials (XC-288 §4; engine build C1): the shared list of the common
settings' meanings, which a task inherits and overrides only with a note saying why (the PI,
2026-10-11); the bounded settings' table, outside `bounds.py` (XC-288 §4.1); and each setting's
meaning as resolved."""

from __future__ import annotations

import dataclasses
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from wl_xcon import photometry
from wl_xcon import task as vocabulary
from wl_xcon.cli import _load_bounds
from wl_xcon.declarations import (
    BOUNDED, COMMON, FORMAT, OVERRIDE, OWN, SHARED, canonical, content, content_hash, resolved,
)
from wl_xcon.task import (
    BACKGROUND,
    CLEAR_CUT,
    CRITERION,
    EASIER,
    EXPECTED,
    HARDER,
    NEITHER,
    NO_LIMIT,
    NOT_DIFFICULTY,
    OWED,
    SPENT,
    STIMULUS,
    UNCHANGED,
    After,
    Balanced,
    Block,
    ByCriterion,
    Condition,
    Counting,
    Cyclic,
    Meaning,
    On,
    Outcome,
    Param,
    Plan,
    Reward,
    State,
    Task,
    Trial,
    WithReplacement,
)

HOLD = Param("fix_hold", unit="s", low=0.05, high=2.0, start=0.3)
CONTRAST = Param("contrast", unit="fraction", low=0.02, high=1.0, start=0.5)


def _task(*params: Param, **meanings: Meaning) -> Task:
    """A one-structure task declaring `params`, with `meanings` as its own."""
    trial = Trial(start="wait", params=list(params),
                  states=[State("wait", go=[On(After(1.0), Outcome.CORRECT)])])
    return Task({"wait": trial}, default="wait", meanings=meanings)


def test_a_setting_on_the_shared_list_inherits_its_meaning():
    assert resolved(_task(HOLD)) == {"fix_hold": (COMMON["fix_hold"], SHARED)}


def test_a_setting_only_one_task_has_takes_that_tasks_meaning():
    own = Meaning(CLEAR_CUT, STIMULUS, raising=EASIER)

    assert resolved(_task(CONTRAST, contrast=own)) == {"contrast": (own, OWN)}


def test_a_task_may_override_a_shared_meaning_and_it_is_marked_an_override():
    """The PI, 2026-10-11: "override allowed with a note"; the override is recorded as one."""
    override = Meaning(EXPECTED, CRITERION, raising=HARDER, note="a long hold breaks some animals",
                       overrides="this task trains holding")

    assert resolved(_task(HOLD, fix_hold=override)) == {"fix_hold": (override, OVERRIDE)}


def test_a_setting_with_no_meaning_is_left_out_for_the_check_to_refuse():
    assert resolved(_task(HOLD, CONTRAST)) == {"fix_hold": (COMMON["fix_hold"], SHARED)}


def test_the_shared_list_holds_every_setting_two_reference_task_files_use_alike():
    """The ten settings three or more reference task files use, `target_x` and `target_y` among
    them now that the detection tasks' target position bears calibration's names, and the seven
    two task files share, `array_eccentricity` among them (the engine C1 plan's call 5; the PI's
    confirmation of its Appendix B and his `target_y`, 2026-10-11): seventeen."""
    assert set(COMMON) == {
        "fix_acquisition", "fix_hold", "fix_luminance", "fix_window", "response_deadline",
        "target_hold", "target_appearance", "target_luminance", "target_x", "target_y",
        "target_window", "object_window", "set_size", "target_index",
        "array_rotation", "array_eccentricity", "distractor_appearance",
    }
    assert len(COMMON) == 17


def test_every_shared_meaning_says_whether_its_setting_is_a_criterion_or_a_stimulus():
    """The PI, 2026-10-11: windows, holds and the times allowed are criteria; what the animal
    sees is a stimulus. Neither is the bounded settings' alone."""
    assert {name for name, meaning in COMMON.items() if meaning.role == CRITERION} == {
        "fix_acquisition", "fix_hold", "fix_window", "response_deadline", "target_hold",
        "target_window", "object_window",
    }
    assert all(meaning.role == STIMULUS for name, meaning in COMMON.items()
               if meaning.role != CRITERION)
    assert {meaning.role for meaning in BOUNDED.values()} == {NEITHER}


@pytest.mark.parametrize("path", ["tasks/reference_bounds.py", "tasks/eight_hour_bounds.py"])
def test_every_ceiling_a_bounded_config_carries_has_its_meaning_in_the_table(path):
    """XC-288 §4.1: the bounded settings that change live take their meanings from a table in
    wl-xcon, outside `bounds.py`; and the table names nothing that is not one."""
    ceilings = set(_load_bounds(Path(path)).ceilings)

    assert ceilings <= set(BOUNDED)
    assert set(BOUNDED) == {"reward_correct", "out_of_cage"}


ROOT = Path(__file__).resolve().parents[1]

#: A task file of one structure: a setting of its own with its meaning, a reward, a reaction time.
TASK_FILE = '''from wl_xcon.task import (
    CLEAR_CUT, EASIER, NO_CHOICE, STIMULUS, After, Meaning, On, Outcome, P, Param, ReactionTime,
    Reward, State, Task, Trial,
)

trial = Trial(
    start="wait",
    params=[Param("contrast", unit="fraction", low=0.02, high=1.0, start=0.5)],
    states=[State("wait", go=[On(After(P("contrast")), Outcome.CORRECT, do=[Reward("reward_correct")])])],
)
TASK = Task(
    {"wait": trial},
    default="wait",
    reaction_time=ReactionTime("wait", (Outcome.CORRECT,), "the wait"),
    choice=NO_CHOICE,
    meanings={"contrast": Meaning(CLEAR_CUT, STIMULUS, raising=EASIER)},
)
'''

#: `TASK_FILE` with a plan (engine build C2b): blocks drawn with replacement by weight, conditions
#: naming their structure, a time limit and a balanced order -- each a declaration the hash writes.
PLANNED_FILE = TASK_FILE.replace(
    "    Reward, State, Task, Trial,\n)",
    "    Reward, State, Task, Trial, Balanced, Block, Condition, Plan, WithReplacement,\n)",
) + '''
PLANNED = Task(
    TASK.structures, default=TASK.default, reaction_time=TASK.reaction_time, choice=TASK.choice,
    meanings=TASK.meanings,
    plans={"mixed": Plan(
        blocks=[
            Block("catch", [Condition("signal", {"contrast": 0.5}, target=8, structure="wait"),
                            Condition("blank", {"contrast": 0.02}, target=2)],
                  order=WithReplacement(weights={"signal": 0.8, "blank": 0.2}), trials=10),
            Block("easy", [Condition("easy", {"contrast": 0.9}, target=5)], time_limit_s=300.0),
        ],
        order=Balanced(blocks=4), time_limit_s=1800.0,
    )},
)
del TASK
'''

#: Loads a task file by path and prints its hash: what another process makes of it.
HASH_IT = (
    "import importlib.util, sys\n"
    "from wl_xcon.declarations import content_hash\n"
    "spec = importlib.util.spec_from_file_location('hashed', sys.argv[1])\n"
    "module = importlib.util.module_from_spec(spec)\n"
    "spec.loader.exec_module(module)\n"
    "print(content_hash(module.TASK))\n"
)

#: What `DEFAULTS` writes for a field with no default.
REQUIRED = "<required>"

#: **Every field's default, at the content's format 1** (`declarations.FORMAT`; the engine C1
#: plan's call 11): each class a task's content can hold (`_vocabulary`), and each of its fields'
#: defaults as `canonical` writes them, or `REQUIRED`. `canonical` leaves a field at its default
#: out of a task's content, so a default that changes would change what a task does and leave its
#: hash as it was; it raises `FORMAT` instead, which every content carries. *Format 1 was rewritten
#: in place on 2026-10-11, before it shipped (build C1 unmerged, no hash recorded): `ItemWindows`
#: became `ObjectWindows` and `Choice.items` `Choice.objects`, the PI's "object", not "item".*
DEFAULTS_AT_FORMAT = 1
DEFAULTS = {
    "Action": {},
    "After": {"seconds": REQUIRED, "since": None},
    "Annulus": {"inner": 1.0, "outer": 2.0, "contrast": None, "color": None},
    "Appearance": {},
    "Array": {
        "n": 4,
        "radius": 8.0,
        "target": 0,
        "looks": {"class": "Disc", "fields": {}},
        "among": {"class": "Disc", "fields": {}},
        "phase": 0.0,
    },
    "Background": {},
    "Balanced": {"blocks": None},
    "Bar": {"length": 4.0, "width": 0.5, "orientation": 0.0, "contrast": None, "color": None},
    "Blank": {},
    "Block": {
        "name": REQUIRED,
        "conditions": REQUIRED,
        "criterion": None,
        "counting": None,
        "order": {"class": "Shuffled", "fields": {}},
        "drum": False,
        "trials": None,
        "time_limit_s": None,
    },
    "BlockOrder": {},
    "Bounded": {"name": REQUIRED},
    "ByCriterion": {"fall_back": None},
    "ChairStill": {},
    "Checkerboard": {"check_size": 1.0, "contrast": None, "aperture": 10.0, "color": None},
    "Choice": {"objects": REQUIRED, "by": REQUIRED},
    "Color": {},
    "Condition": {"name": REQUIRED, "values": REQUIRED, "target": REQUIRED, "structure": None},
    "ConeContrast": {"L": 0.0, "M": 0.0, "S": 0.0},
    "Constrained": {"max_run": 2, "weights": {}},
    "Contrast": {"value": REQUIRED},
    "Corrugation": {"sf": 0.5, "amplitude": 0.1, "orientation": 0.0, "phase": 0.0},
    "Counting": {
        "after_stimulus": REQUIRED, "appears": None, "withholding": False, "outcomes": {},
        "cap": None,
    },
    "Cross": {"size": 0.5, "thickness": 0.1, "contrast": None, "color": None},
    "Custom": {"name": REQUIRED},
    "Cyclic": {"cycles": None},
    "DKL": {"lum": 0.0, "l_m": 0.0, "s_lm": 0.0},
    "Disc": {"size": 1.0, "contrast": None, "color": None},
    "Dots": {
        "coherence": 0.5,
        "direction": 0.0,
        "speed": 5.0,
        "density": 1.0,
        "aperture": 5.0,
        "seed": 0,
        "color": None,
    },
    "Entered": {"window": REQUIRED},
    "Exited": {"window": REQUIRED},
    "FeatureAbove": {"source": REQUIRED, "threshold": REQUIRED},
    "Fixed": {},
    "Form": {},
    "Gabor": {
        "sf": 2.0,
        "orientation": 0.0,
        "phase": 0.0,
        "contrast": None,
        "sigma": 1.0,
        "color": None,
    },
    "Grating": {
        "sf": 2.0,
        "orientation": 0.0,
        "phase": 0.0,
        "contrast": None,
        "aperture": 5.0,
        "color": None,
    },
    "Gray": {"cd_m2": REQUIRED},
    "Guard": {},
    "Hide": {"stimulus": REQUIRED},
    "Hold": {"window": REQUIRED, "seconds": REQUIRED},
    "ObjectWindows": {"of": REQUIRED, "radius": REQUIRED, "eye": "both"},
    "Mark": {"code": REQUIRED},
    "Meaning": {
        "kind": REQUIRED,
        "role": REQUIRED,
        "raising": None,
        "note": "",
        "relative_to": None,
        "overrides": "",
    },
    "Michelson": {"value": REQUIRED},
    "Movie": {"asset": "", "size": 10.0, "loop": False},
    "NoChoice": {},
    "Noise": {
        "exponent": 1.0,
        "contrast": None,
        "aperture": 5.0,
        "refresh_hz": 0.0,
        "seed": 0,
        "color": None,
    },
    "On": {"guard": REQUIRED, "to": REQUIRED, "do": []},
    "Onscreen": {"patch": "task"},
    "Order": {},
    "P": {"name": REQUIRED},
    "Param": {
        "name": REQUIRED,
        "unit": REQUIRED,
        "low": None,
        "high": None,
        "choices": [],
        "live": True,
        "start": None,
    },
    "Picture": {"asset": "", "size": 10.0},
    "Plan": {"blocks": REQUIRED, "order": {"class": "Fixed", "fields": {}}, "time_limit_s": None},
    "Plaid": {
        "sf": 2.0,
        "orientation": 0.0,
        "angle": 90.0,
        "contrast": None,
        "aperture": 5.0,
        "color": None,
    },
    "Polar": {"eccentricity": REQUIRED, "direction": REQUIRED},
    "Polygon": {"sides": 3, "size": 1.0, "orientation": 0.0, "contrast": None, "color": None},
    "Pressed": {"device": REQUIRED},
    "RDS": {
        "correlation": 1.0,
        "form": None,
        "density": 1.0,
        "dot_size": 0.1,
        "aperture": 5.0,
        "contrast": None,
        "seed": 0,
        "color": None,
    },
    "RMS": {"value": REQUIRED},
    "Random": {"blocks": None},
    "ReactionTime": {"state": REQUIRED, "to": REQUIRED, "note": REQUIRED},
    "Released": {"device": REQUIRED},
    "Remembered": {},
    "Response": {"device": REQUIRED},
    "Reward": {},
    "SaccadeOnset": {},
    "SaccadeTo": {"window": REQUIRED},
    "Score": {"window": REQUIRED, "scored_as": REQUIRED},
    "Show": {"stimulus": REQUIRED},
    "Shuffled": {},
    "Slant": {"gradient": 0.05, "orientation": 0.0},
    "Square": {"size": 1.0, "contrast": None, "color": None},
    "State": {"name": REQUIRED, "enter": [], "go": [], "unbounded": False},
    "Stimulus": {
        "name": REQUIRED,
        "at": REQUIRED,
        "looks": {"class": "Disc", "fields": {}},
        "disparity": 0.0,
        "eye": "both",
        "layer": 0,
        "combine": "cover",
        "opacity": 1.0,
        "at_left": None,
        "at_right": None,
    },
    "Task": {
        "structures": REQUIRED,
        "default": REQUIRED,
        "reaction_time": None,
        "choice": None,
        "meanings": {},
        "needs_fixed_head": False,
        "plans": {},
    },
    "Tolerances": {"blink": 0.0, "tracker_lost": 0.05},
    "Touched": {"window": REQUIRED},
    "Trial": {
        "start": REQUIRED,
        "states": REQUIRED,
        "params": [],
        "windows": [],
        "tolerances": {"class": "Tolerances", "fields": {}},
        "view": "either",
        "background": None,
        "background_left": None,
        "background_right": None,
        "periphery": "true_angle",
        "counting": None,
    },
    "Update": {
        "stimulus": REQUIRED,
        "at": {"class": "Unchanged", "fields": {}},
        "looks": {"class": "Unchanged", "fields": {}},
        "disparity": {"class": "Unchanged", "fields": {}},
        "eye": {"class": "Unchanged", "fields": {}},
        "layer": {"class": "Unchanged", "fields": {}},
        "opacity": {"class": "Unchanged", "fields": {}},
        "at_left": {"class": "Unchanged", "fields": {}},
        "at_right": {"class": "Unchanged", "fields": {}},
    },
    "Weber": {"value": REQUIRED},
    "WithReplacement": {"weights": {}},
    "Window": {"name": REQUIRED, "at": REQUIRED, "radius": REQUIRED, "on": None, "eye": "both"},
    "xyY": {"x": REQUIRED, "y": REQUIRED, "Y": REQUIRED},
}


def _module(path: Path):
    """A task file, imported by path as the loader does."""
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _loaded(path: Path):
    """The `TASK` a task file defines."""
    return _module(path).TASK


def _vocabulary() -> dict[str, type]:
    """Every class a task's content can hold, by name: each dataclass `wl_xcon.task` defines -- its
    vocabulary, the declarations and the task object -- and `wl_xcon.photometry`'s colors and
    contrasts."""
    found = {
        name: value for name, value in vars(vocabulary).items()
        if isinstance(value, type) and dataclasses.is_dataclass(value)
        and value.__module__ == vocabulary.__name__
    }
    found.update({
        name: value for name, value in vars(photometry).items()
        if isinstance(value, type) and issubclass(value, (photometry.Color, photometry.Contrast))
    })
    return found


def _defaults() -> dict[str, dict[str, object]]:
    """`DEFAULTS` as the code reads now."""
    now: dict[str, dict[str, object]] = {}
    for name, cls in sorted(_vocabulary().items()):
        now[name] = {}
        for spec in dataclasses.fields(cls):
            if spec.default is not dataclasses.MISSING:
                now[name][spec.name] = canonical(spec.default)
            elif spec.default_factory is not dataclasses.MISSING:
                now[name][spec.name] = canonical(spec.default_factory())
            else:
                now[name][spec.name] = REQUIRED
    return now


def _classes(value: object, found: set[str]) -> set[str]:
    """Every class `canonical`'s plain data names, at any depth, added to `found`."""
    if isinstance(value, dict):
        if "class" in value:
            found.add(value["class"])
        for item in value.values():
            _classes(item, found)
    elif isinstance(value, list):
        for item in value:
            _classes(item, found)
    return found


def test_a_declaration_is_written_by_its_class_and_the_fields_it_sets():
    """Call 11: a class by its name and only the fields away from their defaults, so a field a later
    build adds leaves every task's hash as it was."""
    assert canonical(Meaning(CLEAR_CUT, STIMULUS, raising=EASIER)) == {
        "class": "Meaning", "fields": {"kind": "clear-cut", "role": "stimulus", "raising": "easier"}}
    assert canonical(Meaning(EXPECTED, STIMULUS, raising=HARDER, note="n",
                             relative_to=BACKGROUND))["fields"]["relative_to"] == {
        "class": "Background", "fields": {}}
    assert canonical(Outcome.CORRECT) == {"enum": "Outcome", "value": "correct"}
    assert canonical(UNCHANGED) == {"class": "Unchanged", "fields": {}}
    assert canonical((1, 2.5, "a", None, True)) == [1, 2.5, "a", None, True]


def test_a_reward_is_written_with_the_entry_it_names():
    """Call 19: `Reward` reads as a dataclass with no fields, and every `Reward` equals every other;
    the entry it pays through is part of the task all the same. `canonical` reads its one slot,
    `ref`, by name, so a slot added to `Reward` would be in no hash (the plan's engineering review,
    M7)."""
    assert Reward.__slots__ == ("ref",), "canonical reads Reward's ref alone; read the new slot too"
    assert canonical(Reward("reward_correct")) == {"class": "Reward", "fields": {
        "ref": {"class": "Bounded", "fields": {"name": "reward_correct"}}}}
    assert canonical(Reward("reward_correct")) != canonical(Reward("reward_streak"))


def test_what_it_cannot_read_is_refused_never_written_by_its_address():
    with pytest.raises(TypeError, match="is not a declaration"):
        canonical(object())
    with pytest.raises(TypeError, match="keys are text"):
        canonical({1: "a"})


def test_the_hash_is_sha256_of_the_content_as_sorted_json(tmp_path):
    path = tmp_path / "hashed_task.py"
    path.write_text(TASK_FILE)
    task = _loaded(path)
    text = json.dumps(content(task), sort_keys=True, separators=(",", ":"), ensure_ascii=True)

    assert content_hash(task) == "sha256:" + hashlib.sha256(text.encode("ascii")).hexdigest()
    assert re.fullmatch(r"sha256:[0-9a-f]{64}", content_hash(task))
    assert content(task)["format"] == FORMAT
    assert content(task)["meanings"] == {
        "contrast": canonical(Meaning(CLEAR_CUT, STIMULUS, raising=EASIER))}
    assert content(task)["bounded"] == {"reward_correct": canonical(BOUNDED["reward_correct"])}


def test_the_hash_is_the_same_in_another_process(tmp_path):
    """Review Focus 4: nothing in it is an address or a seeded hash, so two processes, each with its
    own `PYTHONHASHSEED`, agree with this one."""
    path = tmp_path / "hashed_task.py"
    path.write_text(TASK_FILE)

    def elsewhere(seed: str) -> str:
        done = subprocess.run(
            [sys.executable, "-c", HASH_IT, str(path)], cwd=ROOT,
            env={**os.environ, "PYTHONHASHSEED": seed}, capture_output=True, text=True, timeout=120,
        )
        assert done.returncode == 0, done.stderr
        return done.stdout.strip()

    assert elsewhere("1") == elsewhere("999") == content_hash(_loaded(path))


def test_a_plan_hashes_the_same_in_another_process(tmp_path):
    """Engine build C2b: a plan's blocks, weights and orders are declarations the hash writes field
    by field, none of them a set or an address, so a task with plans hashes alike in every
    process."""
    path = tmp_path / "planned_task.py"
    path.write_text(PLANNED_FILE)

    def elsewhere(seed: str) -> str:
        done = subprocess.run(
            [sys.executable, "-c", HASH_IT.replace("module.TASK", "module.PLANNED"), str(path)],
            cwd=ROOT, env={**os.environ, "PYTHONHASHSEED": seed}, capture_output=True, text=True,
            timeout=120,
        )
        assert done.returncode == 0, done.stderr
        return done.stdout.strip()

    assert elsewhere("1") == elsewhere("999") == content_hash(_module(path).PLANNED)


def test_a_comment_or_a_default_written_out_leaves_the_hash_and_a_start_value_moves_it(tmp_path):
    """Review Focus 4 (XC-288 §4.4: "a hash of its content, never its file path"). One file name
    each: two files of one name, size and second can share a bytecode cache entry."""
    plain, annotated, moved = (tmp_path / f"{name}_task.py" for name in ("plain", "annotated", "moved"))
    plain.write_text(TASK_FILE)
    annotated.write_text("# The same task, with a comment and its default view written out.\n"
                         + TASK_FILE.replace('start="wait",\n    params', 'start="wait",\n    view="either",\n    params'))
    moved.write_text(TASK_FILE.replace("start=0.5", "start=0.6"))
    assert 'view="either"' in annotated.read_text() and "start=0.6" in moved.read_text()

    assert content_hash(_loaded(plain)) == content_hash(_loaded(annotated))
    assert content_hash(_loaded(moved)) != content_hash(_loaded(plain))


def test_a_shared_meaning_is_part_of_every_task_that_inherits_it(monkeypatch):
    """A change to the shared list is a change to each task using the setting (call 11)."""
    task = _task(HOLD)
    before = content_hash(task)

    monkeypatch.setitem(COMMON, "fix_hold", Meaning(NOT_DIFFICULTY, CRITERION))

    assert content_hash(task) != before


def test_a_bounded_settings_meaning_is_part_of_every_task_rewarding_through_it(tmp_path, monkeypatch):
    """The review report shows it beside the hash, so the hash covers it (the plan's engineering
    review, M4)."""
    path = tmp_path / "hashed_task.py"
    path.write_text(TASK_FILE)
    task = _loaded(path)
    before = content_hash(task)

    monkeypatch.setitem(BOUNDED, "reward_correct", Meaning(NOT_DIFFICULTY, NEITHER, note="other"))

    assert content_hash(task) != before


def test_the_contents_format_is_part_of_every_hash(monkeypatch):
    task = _task(HOLD)
    before = content_hash(task)

    monkeypatch.setattr("wl_xcon.declarations.FORMAT", FORMAT + 1)

    assert content_hash(task) != before


def test_a_default_that_changes_raises_the_contents_format():
    """The plan's engineering review, I1: `canonical` leaves a field at its default out, so a
    changed default would change what a task does and leave its hash as it was. A default that
    changes, or a field that goes, raises `declarations.FORMAT`; a new class or field joins
    `DEFAULTS` with no raise, being at its default in every task written before it."""
    now = _defaults()
    changed = sorted(
        f"{name}.{field}" for name, fields in DEFAULTS.items()
        for field, default in fields.items() if now.get(name, {}).get(field, "<gone>") != default
    )
    assert (FORMAT, changed) == (DEFAULTS_AT_FORMAT, []), (
        f"defaults changed or gone: {changed}; raise declarations.FORMAT (now {FORMAT}), then "
        f"write DEFAULTS and DEFAULTS_AT_FORMAT as they are at it"
    )
    added = sorted(set(now) - set(DEFAULTS)) + sorted(
        f"{name}.{field}" for name in set(now) & set(DEFAULTS)
        for field in now[name] if field not in DEFAULTS[name]
    )
    assert added == [], f"new in the vocabulary: {added}; add them to DEFAULTS, raising nothing"


def test_every_class_a_reference_task_declares_has_its_defaults_held():
    """`DEFAULTS` reaches every class a real task's content holds."""
    found: set[str] = set()
    for name in ("fixation_detection", "adaptive_detection", "visual_search",
                 "visual_search_training", "calibration"):
        for value in vars(_module(ROOT / "tasks" / f"{name}.py")).values():
            if isinstance(value, (Trial, Task)):
                _classes(canonical(value), found)

    assert {"Trial", "Array", "DKL", "xyY"} <= found <= set(DEFAULTS)


def test_needing_a_fixed_head_is_part_of_the_task_and_not_needing_one_changes_nothing():
    plain = _task(HOLD)
    fixed = Task(plain.structures, default=plain.default, needs_fixed_head=True)
    unfixed = Task(plain.structures, default=plain.default, needs_fixed_head=False)

    assert content_hash(fixed) != content_hash(plain) == content_hash(unfixed)


def test_a_structures_counting_table_is_part_of_the_tasks_content():
    """Engine build C2a: what a break after the stimulus does changes what a run's count means, so
    it moves the hash; a structure that declares none hashes as before the field existed."""
    plain = _task(HOLD)
    trial = plain.structures[plain.default]
    spent = dataclasses.replace(trial, counting=Counting(after_stimulus=SPENT))
    owed = dataclasses.replace(trial, counting=Counting(after_stimulus=OWED))

    def of(structure):
        return content_hash(Task({plain.default: structure}, default=plain.default))

    assert len({of(trial), of(spent), of(owed)}) == 3
    assert of(trial) == content_hash(plain)


def test_a_tasks_plans_are_part_of_its_content():
    """Engine build C2b: which blocks a run can play, how they follow, what each condition sets and
    plays, and when a block or a run is over change what a run of the task is, so each moves the
    hash; a task with no plans hashes as before the field existed."""
    plain = _task(HOLD)
    near = Condition("near", {"fix_hold": 0.3}, target=10)
    block = Block("hold", [near])

    def of(**plans):
        return content_hash(Task(plain.structures, default=plain.default, plans=plans))

    variants = {
        of(),
        of(one=Plan([block])),
        of(two=Plan([block])),
        of(one=Plan([block], order=Cyclic())),
        of(one=Plan([block], order=Cyclic(cycles=3))),
        of(one=Plan([block], order=ByCriterion(fall_back=(0.5, 20)))),
        of(one=Plan([block], time_limit_s=600.0)),
        of(one=Plan([dataclasses.replace(block, time_limit_s=60.0)])),
        of(one=Plan([dataclasses.replace(block, trials=40)])),
        of(one=Plan([Block("hold", [dataclasses.replace(near, structure="wait")])])),
        of(one=Plan([dataclasses.replace(
            block, counting=Counting(after_stimulus=OWED, cap=NO_LIMIT))])),
    }
    assert len(variants) == 11
    assert of() == content_hash(plain)
