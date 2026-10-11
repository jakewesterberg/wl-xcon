"""What a task declares beyond its trials (XC-288 §4; engine build C1): the shared list of the common
settings' meanings, which a task inherits and overrides only with a note saying why (the PI,
2026-10-11); the bounded settings' table, outside `bounds.py` (XC-288 §4.1); and each setting's
meaning as resolved."""

from __future__ import annotations

from pathlib import Path

import pytest

from wl_xcon.cli import _load_bounds
from wl_xcon.declarations import BOUNDED, COMMON, OVERRIDE, OWN, SHARED, resolved
from wl_xcon.task import (
    CLEAR_CUT,
    CRITERION,
    EASIER,
    EXPECTED,
    HARDER,
    NEITHER,
    STIMULUS,
    After,
    Meaning,
    On,
    Outcome,
    Param,
    State,
    Task,
    Trial,
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
    """The nine settings three or more reference task files use, but `eccentricity`, which means a different thing in
    each task using it, and the seven two task files share (the engine C1 plan's call 5)."""
    assert set(COMMON) == {
        "fix_timeout", "fix_hold", "fix_luminance", "fix_window", "response_window",
        "target_hold", "target_looks", "target_luminance",
        "target_window", "target_position", "item_window", "set_size", "target_index",
        "array_phase", "distractors",
    }


def test_every_shared_meaning_says_whether_its_setting_is_a_criterion_or_a_stimulus():
    """The PI, 2026-10-11: windows, holds and the times allowed are criteria; what the animal
    sees is a stimulus. Neither is the bounded settings' alone."""
    assert {name for name, meaning in COMMON.items() if meaning.role == CRITERION} == {
        "fix_timeout", "fix_hold", "fix_window", "response_window", "target_hold",
        "target_window", "item_window",
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
