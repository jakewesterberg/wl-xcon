"""Each trial structure's counting table (engine spec §16.1-16.2; engine build C2a).

What every outcome does to its condition's count: counted, an answer; spent, used up and marked an
abort; owed, shown again; unpaid, neither paid nor shown again. Declared by the structure, never
decided by the scheduler, because "run until ten correct" and "show the array a hundred times"
are both ordinary designs (TSK-26).
"""

from __future__ import annotations

import pytest

from wl_xcon.codes import _standing_outcomes
from wl_xcon.task import (
    AFTER_STIMULUS,
    ANSWERS,
    COUNTED,
    HANG_COUNTS_AS,
    OWED,
    REPEATED,
    RIGHT,
    SPENT,
    UNPAID,
    Counting,
    Outcome,
)


def test_every_outcome_falls_under_exactly_one_rule():
    """Total and disjoint, as `_FAMILY` is: an outcome added to the vocabulary without a rule here
    would be classed by nothing anyone decided."""
    rules = [ANSWERS, REPEATED, AFTER_STIMULUS, frozenset({Outcome.NO_RESPONSE})]

    assert frozenset().union(*rules) == frozenset(Outcome)
    assert sum(len(rule) for rule in rules) == len(Outcome)


def test_the_right_answers_are_the_two_the_codes_mark_correct():
    """`codes.py`: "A correct rejection *is* a correct trial". Drumming ends, a criterion judges and
    a condition's correct count counts on this one set (the engine C2a plan's call 7)."""
    marked = _standing_outcomes()

    assert RIGHT == {o for o in Outcome if marked[o] == marked[Outcome.CORRECT]}
    assert RIGHT == {Outcome.CORRECT, Outcome.CORRECT_REJECT} and RIGHT <= ANSWERS


def test_every_answer_counts_a_correct_rejection_and_a_false_alarm_among_them():
    """§16.1; TSK-27: where withholding is an answer, a correct rejection and a false alarm are
    answers. `scheduler.RESPONDED` left both out, so a block of catch trials never met its
    target (the engine C2a plan's first defect)."""
    for after in (SPENT, OWED):
        table = Counting(after_stimulus=after)
        assert {table.of(outcome) for outcome in ANSWERS} == {COUNTED}
    assert {Outcome.CORRECT_REJECT, Outcome.FALSE_ALARM} <= ANSWERS


def test_the_four_that_end_before_the_decision_are_owed_whatever_the_structure_says_of_breaks():
    """§16.2; TSK-29: a fixation break, no fixation, a lost tracker and a fault are repeated by
    default, so the condition still gets its datum."""
    assert REPEATED == {Outcome.FIXATION_BREAK, Outcome.NO_FIXATION, Outcome.TRACKER_LOST,
                        Outcome.FAULT}
    for after in (SPENT, OWED):
        table = Counting(after_stimulus=after)
        assert {table.of(outcome) for outcome in REPEATED} == {OWED}


@pytest.mark.parametrize("after", [SPENT, OWED])
def test_a_target_break_and_a_blink_break_follow_what_the_structure_declares(after):
    """§16.2's "other breaks"; the PI, 2026-10-11: no default, each task declares. `REQUEUED`
    repeated a target break and a blink break whatever a task said (the plan's second defect)."""
    table = Counting(after_stimulus=after)

    assert {table.of(outcome) for outcome in AFTER_STIMULUS} == {after}
    assert {Outcome.TARGET_BREAK, Outcome.BLINK_BREAK} <= AFTER_STIMULUS


def test_a_break_before_the_stimulus_appeared_is_owed_whatever_the_structure_says_of_breaks():
    """A long blink during the fixation hold ends the trial as a blink break before anything was
    presented: owed, as a fixation break is, never "counted as presented" (§16.1: "Not counted:
    trials that end before the decision"). An answer stays an answer, and a line of the table's
    own for the outcome still decides it."""
    table = Counting(after_stimulus=SPENT)
    declared = Counting(after_stimulus=SPENT, outcomes={"blink_break": SPENT})

    assert table.of(Outcome.BLINK_BREAK, shown=False) == OWED
    assert table.of(Outcome.BLINK_BREAK, shown=True) == SPENT
    assert table.of(Outcome.CORRECT, shown=False) == COUNTED
    assert declared.of(Outcome.BLINK_BREAK, shown=False) == SPENT


def test_no_response_is_a_miss_where_withholding_is_an_answer_and_a_break_where_it_is_not():
    """§16.1; the PI, 2026-10-11: "No response" in both detection tasks is a miss, counted."""
    assert Counting(after_stimulus=OWED, withholding=True).of(Outcome.NO_RESPONSE) == COUNTED
    assert Counting(after_stimulus=OWED).of(Outcome.NO_RESPONSE) == OWED
    assert Counting(after_stimulus=SPENT).of(Outcome.NO_RESPONSE) == SPENT


def test_a_trial_at_the_longest_trial_counts_as_a_missed_acquisition():
    """The PI, 2026-10-11 (XC-287): "it isn't a fixation break, it is a missed acquisition" --
    repeated like a fault, by `NO_FIXATION`'s class, whatever the structure says of it."""
    assert HANG_COUNTS_AS is Outcome.NO_FIXATION
    assert Counting(after_stimulus=SPENT).of(None) == OWED
    spent = Counting(after_stimulus=OWED, outcomes={"no_fixation": SPENT})
    assert spent.of(None) == spent.of(Outcome.NO_FIXATION) == SPENT


def test_a_class_the_structure_declares_for_an_outcome_overrides_the_rules():
    """TSK-26: a block training fixation may count a fixation break as an error; "run until ten
    correct" leaves a wrong answer unpaid, neither paid nor shown again (§16.2: "Not repeated:
    wrong targets")."""
    table = Counting(after_stimulus=OWED,
                     outcomes={"fixation_break": COUNTED, "wrong_target": UNPAID})

    assert table.of(Outcome.FIXATION_BREAK) == COUNTED
    assert table.of(Outcome.WRONG_TARGET) == UNPAID
    assert table.of(Outcome.CORRECT) == COUNTED


@pytest.mark.parametrize(
    ("fields", "said"),
    [
        ({"after_stimulus": "repeated"}, "a break after the stimulus is spent"),
        ({"after_stimulus": UNPAID}, "a break after the stimulus is spent"),
        ({"after_stimulus": OWED, "appears": ""}, "names the state its stimulus appears in"),
        ({"after_stimulus": OWED, "appears": 3}, "names the state its stimulus appears in"),
        ({"after_stimulus": OWED, "withholding": "yes"}, "withholding is True or False"),
        ({"after_stimulus": OWED, "outcomes": [("correct", COUNTED)]}, "a dict of outcome names"),
        ({"after_stimulus": OWED, "outcomes": {"hang": OWED}}, "'hang' is not an outcome"),
        ({"after_stimulus": OWED, "outcomes": {"correct": "paid"}}, "'correct' is given 'paid'"),
        ({"after_stimulus": OWED, "cap": -1}, "a repeat cap is a whole number"),
        ({"after_stimulus": OWED, "cap": True}, "a repeat cap is a whole number"),
        ({"after_stimulus": OWED, "cap": 2.5}, "a repeat cap is a whole number"),
    ],
)
def test_a_malformed_counting_table_is_refused_as_it_is_built(fields, said):
    """Its shape is refused as it is built, as a `Task`'s is; what a task declares with it is
    checked at load (`check.check_task`)."""
    with pytest.raises(ValueError, match=said):
        Counting(**fields)


def test_a_counting_table_says_what_breaks_after_the_stimulus_do_or_cannot_be_built():
    """The PI, 2026-10-11: "no default; each task declares"."""
    with pytest.raises(TypeError, match="after_stimulus"):
        Counting()
    assert Counting(after_stimulus=SPENT, cap=0).cap == 0


def test_a_counting_table_names_the_state_its_stimulus_appears_in():
    """The PI, 2026-10-13, "Task names it, required": "Each task's counting table names the step
    where its stimulus appears ... A cued task names the cue step." A table a block counts by
    (`scheduler.CORRECT_ONLY`) names none: where the stimulus appears is the structure's, and
    `check.check_task` refuses a structure whose table names none."""
    assert Counting(after_stimulus=OWED, appears="cue").appears == "cue"
    assert Counting(after_stimulus=OWED).appears is None
