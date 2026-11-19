"""The reference allocation's codes: the pop-out revision's seven are allocated by name.

They are told to wl-preproc before any record shape is written
(docs/pending-wl-preproc-amendments.md, the pop-out revision's section). The codes are
wl-xtasks' to own, held in `tasks/allocation.py` until it publishes its own (ADR-0007).
"""

from __future__ import annotations

from tasks.allocation import ALLOCATION

#: Every code the allocation held before the revision, 4096-4138, which no allocation
#: may renumber: a recording made under them would be relabeled silently.
BEFORE = {
    4096: "FIX_ON",
    4097: "TARGET_ON",
    4098: "SACCADE_ONSET",
    4099: "TARGET_ACQUIRED",
    4100: "ABORT_NO_FIXATION",
    4101: "ABORT_FIXATION_BREAK",
    4102: "REWARD_COMMANDED",
    4103: "ARRAY_ON",
    4104: "DISTRACTOR_ACQUIRED",
    4105: "CALIBRATION_TARGET_ON",
    4106: "CALIBRATION_TARGET_HELD",
    4107: "CALIBRATION_START",
    4108: "CALIBRATION_END",
    4110: "OUTCOME_CORRECT",
    4111: "OUTCOME_EARLY_RESPONSE",
    4112: "OUTCOME_LATE_RESPONSE",
    4113: "OUTCOME_WRONG_TARGET",
    4114: "OUTCOME_EARLY_ERROR",
    4115: "OUTCOME_LATE_ERROR",
    4116: "OUTCOME_NO_FIXATION",
    4117: "OUTCOME_NO_RESPONSE",
    4118: "OUTCOME_ABORT",
    4119: "OUTCOME_FIXATION_BREAK",
    4120: "OUTCOME_TARGET_BREAK",
    4121: "OUTCOME_CATCH_BREAK",
    4122: "OUTCOME_MOTION_BREAK",
    4123: "OUTCOME_CORRECT_REJECT",
    4124: "OUTCOME_FALSE_ALARM",
    4125: "OUTCOME_BLINK_BREAK",
    4126: "OUTCOME_TRACKER_LOST",
    4127: "OUTCOME_FAULT",
    4128: "HEAD_FIXED",
    4129: "HEAD_RELEASED",
    4130: "PARAM_CHANGED",
    4131: "PAUSE",
    4132: "RESUME",
    4133: "OPERATOR_MARK",
    4134: "MANUAL_REWARD",
    4135: "RUN_START",
    4136: "RUN_END",
    4137: "SESSION_RESUMED",
    4138: "TIMEOUT_ON",
}

REVISION = {
    4139: "GO_CUE", 4140: "CATCH_FIXATION_HELD", 4141: "CATCH_FIXATION_BREAK",
    4142: "SPECIAL_TARGET_ABSENT", 4143: "SPECIAL_ODD_PLACE_EMPTY",
    4144: "SPECIAL_DISTRACTOR_ALONE", 4145: "SPECIAL_ODD_ONE_ALONE",
}


def test_the_revisions_seven_codes_are_allocated_by_name_and_new():
    held = ALLOCATION.task_events
    for code, name in REVISION.items():
        assert held.get(code) == name, (
            "code " + str(code) + " should be " + name + ", the allocation has "
            + str(held.get(code)))
        assert 4096 <= code <= 32767
    for code, name in BEFORE.items():
        assert held.get(code) == name, (
            "the earlier code " + str(code) + " " + name + " moved or went: "
            + str(held.get(code)))
    assert len(set(held.values())) == len(held), "two codes share a name"
