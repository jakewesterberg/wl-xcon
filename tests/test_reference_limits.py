"""The reference tasks keep a bound only where a value cannot be, or the PI decided it, each with
its reason (the console settings design's §4; the PI, 2026-11-16, "Hard limits only where
impossible"). A builder's guessed range is gone: the layout judges the values set instead
(`check.laid_out`). Engine test material, run only in the simulator: no number here is a timing
claim about the rig."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from _calibrations import SPECTRA  # noqa: F401  (the measured stand-in's home)
from _rig import DIRECT
from wl_xcon.check import PAST_LIMIT, UNEXPLAINED_LIMIT, beyond_range, check_task, laid_out
from wl_xcon.cli import _load_task
from wl_xcon.task import limit_reason

TASKS = Path(__file__).resolve().parents[1] / "tasks"
NAMES = ("fixation_detection", "adaptive_detection", "visual_search", "visual_search_training",
         "calibration")
COL_29 = "white on the default calibration, the published sRGB 80 cd/m² (COL-29)"


def _allocation():
    sys.path.insert(0, str(TASKS))
    spec = importlib.util.spec_from_file_location("allocation", TASKS / "allocation.py")
    module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module.ALLOCATION


def _bounds(task):
    """Every (structure, setting, side) the task declares a bound on."""
    return [(name, p, side) for name, s in task.structures.items() for p in s.params
            for side, bound in (("low", p.low), ("high", p.high)) if bound is not None]


@pytest.mark.parametrize("name", NAMES)
def test_every_reference_tasks_bound_is_impossible_or_decided_with_its_reason(name):
    task = _load_task(TASKS / f"{name}.py")
    found = check_task(task, _allocation(), geometry=DIRECT)

    assert [f.detail for f in found if f.code == UNEXPLAINED_LIMIT] == []
    for structure, param, side in _bounds(task):
        assert limit_reason(param, side), (name, structure, param.name, side)


def test_a_builders_guess_is_gone_and_a_decided_or_physical_bound_stays():
    """What stays, by its reason: luminance's 80 (the PI's, COL-29), the two primaries' own full
    drive, a hold's highest (its state ends at 10 s, or 3 s, so a longer one cannot finish), a set
    size's highest (a run builds every object first) and the standard lowest of 0 and highest of 1.
    No size, window, place, ring or wait has a guessed range."""
    kept = {}
    for name in NAMES:
        for _structure, param, side in _bounds(_load_task(TASKS / f"{name}.py")):
            bound = param.low if side == "low" else param.high
            if not (side == "low" and bound == 0):
                kept.setdefault(name, set()).add((param.name, side, bound))
    holds = {("fix_hold", "high", 10.0), ("target_hold", "high", 3.0)}
    assert kept["fixation_detection"] == holds | {("fix_luminance", "high", 80.0),
                                                  ("target_luminance", "high", 80.0)}
    assert kept["adaptive_detection"] == holds | {("fix_luminance", "high", 80.0),
                                                  ("target_luminance", "high", 80.0),
                                                  ("target_contrast", "high", 1.0)}
    assert kept["calibration"] == {("cal_hold", "high", 10.0), ("target_luminance", "high", 80.0)}
    for name in ("visual_search", "visual_search_training"):
        assert {n for n, _s, _b in kept[name]} >= {"set_size", "fix_luminance"}
    assert ("red_luminance", "high", 17.0) in kept["visual_search_training"]
    assert ("green_luminance", "high", 57.0) in kept["visual_search_training"]
    assert not {n for k in kept.values() for n, _s, _b in k} & {
        "fix_window", "target_window", "object_window", "cal_window", "target_x", "target_y",
        "array_eccentricity", "array_rotation", "target_eccentricity", "fix_acquisition",
        "response_deadline"}


def test_the_luminance_bound_cites_what_the_pi_decided():
    task = _load_task(TASKS / "fixation_detection.py")
    (param,) = [p for p in task.trial.params if p.name == "target_luminance"]

    assert limit_reason(param, "high") == COL_29
    (finding, *_) = beyond_range(task, {"target_luminance": 90.0}, geometry=DIRECT)
    assert (finding.code, finding.blocking) == (PAST_LIMIT, True)
    assert COL_29 in finding.detail


def test_visual_search_twelve_on_a_five_degree_ring_warns_crowding_at_those_values():
    """TSK-39's old guard held the object window to 1.0° so twelve on a 5° ring could not overlap.
    The window is free now, and 1.6° there, 2.59° apart, overlaps: a warning naming the settings
    and their values, never a refusal; at 1.0° it says nothing."""
    task = _load_task(TASKS / "visual_search.py")
    (window,) = [p for p in task.trial.params if p.name == "object_window"]
    assert (window.low, window.high) == (None, None)
    values = {"set_size": 12, "array_eccentricity": 5.0}

    crowded = [f for f in laid_out(task, {**values, "object_window": 1.6}, geometry=DIRECT)
               if f.code == "crowded-array"]
    clear = [f for f in laid_out(task, {**values, "object_window": 1.0}, geometry=DIRECT)
             if f.code == "crowded-array"]

    assert len(crowded) == 1 and not crowded[0].blocking
    for word in ("12 objects ('set_size')", "5° ring ('array_eccentricity')",
                 "windows of 1.6° radius ('object_window')"):
        assert word in crowded[0].detail, crowded[0].detail
    assert clear == []
