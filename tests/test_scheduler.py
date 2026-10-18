"""The trial scheduler: which condition next, when a block ends, what is owed.

S8 §1-2. Between-trial code, outside the frame budget -- so it may hold state and do
arbitrary arithmetic, and an error here is observable and recoverable rather than a
dropped frame.
"""

from __future__ import annotations

import pytest

from wl_xcon.scheduler import (
    CORRECT_ONLY,
    EVERY_TRIAL,
    PRESENTED,
    Block,
    Condition,
    Constrained,
    Scheduler,
    WithReplacement,
)
from wl_xcon.task import COUNTED, OWED, SPENT, UNPAID, Counting, Outcome


def _block(**kwargs) -> Block:
    return Block(
        name="main",
        conditions=[
            Condition("near", values={"target_eccentricity": 5.0}, target=10),
            Condition("far", values={"target_eccentricity": 15.0}, target=10),
        ],
        **kwargs,
    )


def test_counters_distinguish_attempted_completed_and_correct():
    """Collapsing them makes a balanced design unverifiable: an animal that aborts
    only the hard condition looks, on an attempted count, like it ran both."""
    # One condition, so the shuffle cannot decide which one is being counted.
    scheduler = Scheduler(
        [Block(name="main", conditions=[Condition("near", {}, target=10)])], seed=1
    )

    scheduler.record(scheduler.next_trial().name, Outcome.CORRECT)
    scheduler.record(scheduler.next_trial().name, Outcome.FIXATION_BREAK)

    counts = scheduler.counts("near")
    assert (counts.attempted, counts.completed, counts.correct) == (2, 1, 1)


def test_owed_is_target_minus_completed_not_minus_attempted():
    """The question at a rig is never how many have run but how many more are
    needed, and an aborted trial produced no datum."""
    scheduler = Scheduler([_block()], seed=1)

    for _ in range(3):
        trial = scheduler.next_trial()
        scheduler.record(trial.name, Outcome.FIXATION_BREAK)

    assert scheduler.owed("near") == 10
    assert scheduler.owed("far") == 10


def test_a_fixation_break_is_requeued_at_the_end_of_the_block():
    """The default ruled 2026-08-31. A broken fixation is a failure to engage and
    the condition still owes a datum; end of block rather than immediately, so an
    animal cannot make an easy condition repeat by breaking on the hard one."""
    scheduler = Scheduler([_block()], seed=1)

    first = scheduler.next_trial()
    scheduler.record(first.name, Outcome.FIXATION_BREAK)

    assert first.name in scheduler.requeued
    assert scheduler.upcoming()[-1] == first.name


def test_a_wrong_choice_is_not_requeued():
    """A wrong choice *is* the datum."""
    scheduler = Scheduler([_block()], seed=1)

    first = scheduler.next_trial()
    scheduler.record(first.name, Outcome.WRONG_TARGET)

    assert scheduler.requeued == []


def test_a_block_with_a_fixed_length_ends_when_every_condition_is_owed_nothing():
    """**Bounded, and the bound is an assertion rather than a `while` that trusts
    the code under test.** This ran `while not scheduler.finished:` until 2026-09-19,
    so a `record` that stopped advancing the counts made this test spin forever --
    and a mutation sweep reported `caught record  timed out after 300s`, which is the
    harness noticing a hang rather than a test noticing a defect. Every trial of this
    block pays its debt, so twenty draws is the whole of it; forty is slack for the
    requeue path and still finite."""
    scheduler = Scheduler([_block()], seed=1)

    for _ in range(40):
        if scheduler.finished:
            break
        trial = scheduler.next_trial()
        scheduler.record(trial.name, Outcome.CORRECT)
    else:
        raise AssertionError(
            "the block never finished in 40 correct trials, though its two "
            "conditions owe 10 each and a correct trial pays"
        )

    assert scheduler.counts("near").completed == 10
    assert scheduler.counts("far").completed == 10


def test_a_criterion_block_ends_on_performance_not_on_a_count():
    """"80% over the last 20 completed" -- and it consumes the same running
    statistics the console plots use, computed once."""
    scheduler = Scheduler(
        [_block(criterion=(0.8, 20))], seed=1
    )

    for _ in range(20):
        trial = scheduler.next_trial()
        scheduler.record(trial.name, Outcome.CORRECT)

    assert scheduler.finished, "20 correct in a row meets 80% over 20"


def test_aborted_trials_do_not_count_toward_a_criterion_window():
    """An abort says nothing about performance. Letting one into the window makes
    the criterion track engagement rather than what the animal can do -- the same
    reasoning that keeps aborts out of the staircase."""
    scheduler = Scheduler([_block(criterion=(0.8, 4))], seed=1)

    for outcome in (Outcome.CORRECT, Outcome.NO_FIXATION, Outcome.NO_FIXATION):
        trial = scheduler.next_trial()
        scheduler.record(trial.name, outcome)

    assert not scheduler.finished, "one completed trial is not a window of four"


# --- what counts, declared per block -------------------------------------------

def test_a_block_can_count_only_correct_trials():
    """"Run until 10 correct" -- the animal owes the condition a correct trial and
    an error leaves the debt standing."""
    block = Block(
        name="main",
        conditions=[Condition("near", {}, target=3)],
        counting=CORRECT_ONLY,
    )
    scheduler = Scheduler([block], seed=1)

    for outcome in (Outcome.CORRECT, Outcome.WRONG_TARGET, Outcome.CORRECT):
        scheduler.record(scheduler.next_trial().name, outcome)

    assert scheduler.owed("near") == 1, "the error did not pay the debt"


def test_a_block_can_count_every_presentation_regardless_of_accuracy():
    """"Show the array 100 times" -- accuracy is the measurement, not the quota, so
    a wrong answer and a no-response both count."""
    block = Block(
        name="main",
        conditions=[Condition("near", {}, target=3)],
        counting=PRESENTED,
    )
    scheduler = Scheduler([block], seed=1)

    for outcome in (Outcome.CORRECT, Outcome.WRONG_TARGET, Outcome.NO_RESPONSE):
        scheduler.record(scheduler.next_trial().name, outcome)

    assert scheduler.owed("near") == 0


def test_a_trial_that_never_reached_the_stimulus_is_not_a_presentation():
    """The distinction PRESENTED exists to draw: the animal never fixated, so the
    array was never shown, so nothing was presented to count."""
    block = Block(
        name="main",
        conditions=[Condition("near", {}, target=3)],
        counting=PRESENTED,
    )
    scheduler = Scheduler([block], seed=1)

    scheduler.record(scheduler.next_trial().name, Outcome.NO_FIXATION)

    assert scheduler.owed("near") == 3


def test_the_criterion_window_can_use_a_different_rule_from_the_counter():
    """They are different questions. A block may count every presentation toward
    its quota while judging performance only on completed choices."""
    block = Block(
        name="main",
        conditions=[Condition("near", {}, target=100)],
        counting=PRESENTED,
        criterion=(0.8, 2),
        criterion_over=frozenset({Outcome.CORRECT, Outcome.WRONG_TARGET}),
    )
    scheduler = Scheduler([block], seed=1)

    for outcome in (Outcome.CORRECT, Outcome.NO_RESPONSE, Outcome.CORRECT):
        scheduler.record(scheduler.next_trial().name, outcome)

    assert scheduler.finished, "two correct choices; the no-response was not judged"


# --- order, declared per block --------------------------------------------------

def test_constrained_order_refuses_a_run_longer_than_declared():
    """What most search and attention designs actually use, because an animal
    exploits runs -- three of the same target position in a row and it stops
    searching and starts predicting."""
    block = Block(
        name="main",
        conditions=[Condition("a", {}, target=40), Condition("b", {}, target=40)],
        order=Constrained(max_run=2),
    )
    scheduler = Scheduler([block], seed=3)

    drawn = [scheduler.next_trial().name for _ in range(60)]

    runs = []
    for name in drawn:
        if runs and runs[-1][0] == name:
            runs[-1][1] += 1
        else:
            runs.append([name, 1])
    assert max(length for _, length in runs) <= 2


def test_with_replacement_respects_weights():
    """For conditions you want rarely: catch trials, probes."""
    block = Block(
        name="main",
        conditions=[Condition("common", {}, target=900), Condition("rare", {}, target=100)],
        order=WithReplacement(weights={"common": 9.0, "rare": 1.0}),
    )
    scheduler = Scheduler([block], seed=5)

    drawn = [scheduler.next_trial().name for _ in range(2000)]

    assert 0.05 < drawn.count("rare") / len(drawn) < 0.15


def test_a_trial_lost_to_equipment_still_owes_its_datum():
    """The rig failing is not the animal declining.

    `TRACKER_LOST`, `BLINK_BREAK` and `FAULT` were added to the outcome vocabulary on
    2026-09-01 and were not in the requeue set, so a condition that lost a trial to a
    dropped camera would have been silently one datum short -- and the shortfall
    appears nowhere, because the block ends when every condition is owed nothing. A
    blink break is the structure's to declare since engine build C2a (`task.Counting`); a
    lost tracker and a fault are owed by every structure, with no table at all.
    """
    block = Block(
        name="b",
        conditions=[Condition(name="a", values={}, target=2)],
    )
    scheduler = Scheduler(blocks=[block], seed=1)

    scheduler.record(scheduler.next_trial().name, Outcome.TRACKER_LOST)
    assert scheduler.requeued == ["a"]

    scheduler.record(scheduler.next_trial().name, Outcome.FAULT)
    assert scheduler.requeued == ["a", "a"]


def test_requeue_policy_is_declared_per_block():
    """Which aborts owe a datum is a task's judgement, not the framework's.

    A block training an animal to hold fixation may treat a fixation break as a real
    error that pays its debt; a block measuring a psychometric function must not. The
    block's table replaces its structure's (TSK-26).
    """
    strict = Block(
        name="strict",
        conditions=[Condition(name="a", values={}, target=1)],
        counting=Counting(after_stimulus=OWED, outcomes={"fixation_break": COUNTED}),
    )
    scheduler = Scheduler(blocks=[strict], seed=1, counting=Counting(after_stimulus=OWED))
    scheduler.record(scheduler.next_trial().name, Outcome.FIXATION_BREAK)

    assert scheduler.requeued == []
    assert scheduler.owed("a") == 0


# --- the counting table (engine spec §16.1-16.2; engine build C2a) ---------------------


def _catch(**table) -> Scheduler:
    """One condition owing three trials, counted by a structure's table built from `table`."""
    block = Block(name="catch", conditions=[Condition("catch", {}, target=3)])
    return Scheduler([block], seed=1, counting=Counting(**table))


def test_a_catch_condition_meets_its_target_on_correct_rejections():
    """§16.1; TSK-27. `Counting.RESPONDED` left out correct rejections and false alarms, so ten
    correct rejections left a catch condition owing 3, never repeated, and its block never ended
    (the engine C2a plan's first defect)."""
    scheduler = _catch(after_stimulus=OWED, withholding=True)

    for outcome in (Outcome.CORRECT_REJECT, Outcome.FALSE_ALARM, Outcome.CORRECT_REJECT):
        assert scheduler.record(scheduler.next_trial().name, outcome) == COUNTED

    assert scheduler.finished
    assert scheduler.requeued == []


@pytest.mark.parametrize("after", [SPENT, OWED])
def test_a_target_break_is_spent_or_owed_as_the_structure_declares(after):
    """§16.2; the PI, 2026-10-11. `REQUEUED` repeated a target break and a blink break whatever a
    task said (the plan's second defect). Spent pays the debt and is marked an abort; owed pays
    nothing and comes back."""
    scheduler = _catch(after_stimulus=after)

    for outcome in (Outcome.TARGET_BREAK, Outcome.BLINK_BREAK):
        assert scheduler.record(scheduler.next_trial().name, outcome) == after

    counts = scheduler.counts("catch")
    if after == SPENT:
        assert (counts.spent, counts.completed, scheduler.owed("catch")) == (2, 0, 1)
        assert scheduler.requeued == []
    else:
        assert (counts.spent, scheduler.owed("catch")) == (0, 3)
        assert scheduler.requeued == ["catch", "catch"]


def test_a_break_before_the_stimulus_appeared_is_owed_even_where_breaks_are_spent():
    """§16.1: "Not counted: trials that end before the decision". A long blink in the fixation hold
    presented nothing (`shown` False: `taskd._appeared`)."""
    scheduler = _catch(after_stimulus=SPENT)

    assert scheduler.record(scheduler.next_trial().name, Outcome.BLINK_BREAK, shown=False) == OWED
    assert scheduler.owed("catch") == 3 and scheduler.requeued == ["catch"]


def test_a_spent_trial_pays_its_debt_and_is_no_answer_for_the_criterion():
    """§16.2: spent is "counted as presented and marked an abort", so a criterion judged on the
    answers does not see it."""
    block = Block(name="b", conditions=[Condition("a", {}, target=100)], criterion=(0.5, 2))
    scheduler = Scheduler([block], seed=1, counting=Counting(after_stimulus=SPENT))

    for outcome in (Outcome.CORRECT, Outcome.TARGET_BREAK):
        scheduler.record(scheduler.next_trial().name, outcome)

    assert scheduler.owed("a") == 98
    assert not scheduler.finished, "one answer is not a window of two"
    scheduler.record(scheduler.next_trial().name, Outcome.CORRECT)
    assert scheduler.finished, "two correct answers are"


def test_a_trial_at_the_longest_trial_is_owed_and_in_a_flat_run_pays():
    """XC-287; the PI, 2026-10-11: a trial that reaches the cap is a missed acquisition, repeated
    like a fault. `None` neither counted nor was requeued, so a flat run ran N trials plus its hangs
    (the plan's fourth defect); in a flat run every trial pays, this one too."""
    owed = _catch(after_stimulus=SPENT)
    flat = Scheduler(
        [Block(name="session", conditions=[Condition("session", {}, target=2)],
               counting=EVERY_TRIAL)],
        seed=1,
    )

    assert owed.record(owed.next_trial().name, None) == OWED
    assert owed.requeued == ["catch"] and owed.owed("catch") == 3
    assert flat.record(flat.next_trial().name, None) == SPENT
    assert flat.owed("session") == 1


def test_an_outcome_each_structure_declares_is_refused_with_no_table_to_read():
    """The PI, 2026-10-11: no default stands in for a declaration. What every structure shares
    still answers without one."""
    scheduler = Scheduler([_block()], seed=1)

    assert scheduler.record(scheduler.next_trial().name, Outcome.FIXATION_BREAK) == OWED
    assert scheduler.record(scheduler.next_trial().name, Outcome.CORRECT) == COUNTED
    assert scheduler.record(scheduler.next_trial().name, Outcome.CORRECT, shown=False) == COUNTED
    assert scheduler.record(scheduler.next_trial().name, None) == OWED
    with pytest.raises(ValueError, match="target_break ended a trial of block 'main'"):
        scheduler.record(scheduler.next_trial().name, Outcome.TARGET_BREAK)


def test_a_wrong_answer_under_until_n_correct_pays_nothing_and_is_not_shown_again():
    """The PI, 2026-08-31: "wrong choice not" re-queued; §16.2: "Not repeated: wrong targets". A
    wrong answer under "run until ten correct" leaves the debt standing, and its condition comes
    back when the block's order draws it, never placed as a repeat."""
    block = Block(name="main", conditions=[Condition(n, {}, target=2) for n in "ab"],
                  counting=CORRECT_ONLY)
    scheduler = Scheduler([block], seed=1)
    wrong = scheduler.next_trial().name

    assert scheduler.record(wrong, Outcome.WRONG_TARGET) == UNPAID
    assert scheduler.record(scheduler.next_trial().name, Outcome.CORRECT_REJECT) == COUNTED
    assert scheduler.requeued == [] and scheduler.owed(wrong) == 2


def test_a_correct_rejection_is_right_for_the_criterion_and_the_correct_count():
    """`codes.py`: "A correct rejection *is* a correct trial", and the PI's rollup of 2026-09-26
    counts both: a criterion over a block of catch trials is met on correct rejections."""
    block = Block(name="b", conditions=[Condition("catch", {}, target=100)], criterion=(1.0, 2))
    scheduler = Scheduler([block], seed=1, counting=Counting(after_stimulus=OWED, withholding=True))

    for _ in range(2):
        scheduler.record(scheduler.next_trial().name, Outcome.CORRECT_REJECT)

    assert scheduler.finished and scheduler.counts("catch").correct == 2


# --- block progression ------------------------------------------------------
#
# `finished` has always been about the current block. Nothing advanced `_index`, so
# a `Scheduler` built with two blocks ran the first one forever -- which nothing
# noticed, because `taskd` never imported this module at all.


def _two_blocks() -> list[Block]:
    return [
        Block(name="first", conditions=[Condition("a", {}, target=2)]),
        Block(name="second", conditions=[Condition("b", {}, target=3)]),
    ]


def test_a_scheduler_is_not_done_while_a_later_block_is_owed_trials():
    scheduler = Scheduler(blocks=_two_blocks(), seed=1)
    for _ in range(2):
        scheduler.record(scheduler.next_trial().name, Outcome.CORRECT)

    assert scheduler.finished, "the first block is"
    assert not scheduler.done, "the session is not"


def test_advancing_moves_to_the_next_block_and_its_own_conditions():
    scheduler = Scheduler(blocks=_two_blocks(), seed=1)
    for _ in range(2):
        scheduler.record(scheduler.next_trial().name, Outcome.CORRECT)

    scheduler.advance()

    assert scheduler.block.name == "second"
    assert scheduler.next_trial().name == "b"


def test_a_new_block_starts_its_counters_and_its_criterion_window_empty():
    """Otherwise a block inherits the previous block's performance, and a criterion
    can be met before its own block has run a trial."""
    blocks = [
        Block(name="first", conditions=[Condition("a", {}, target=2)]),
        Block(
            name="second",
            conditions=[Condition("b", {}, target=100)],
            criterion=(0.9, 2),
        ),
    ]
    scheduler = Scheduler(blocks=blocks, seed=1)
    for _ in range(2):
        scheduler.record(scheduler.next_trial().name, Outcome.CORRECT)

    scheduler.advance()

    assert not scheduler.finished, "two correct trials belonged to the block before"
    assert scheduler.counts("b").attempted == 0


def test_advancing_past_the_last_block_is_refused():
    """A session that ran off the end of its plan would draw from a block that does
    not exist, and the failure would surface as an index error mid-trial."""
    scheduler = Scheduler(blocks=_two_blocks(), seed=1)
    scheduler.advance()

    with pytest.raises(IndexError, match="last block"):
        scheduler.advance()


def test_a_single_block_scheduler_is_done_when_that_block_is():
    scheduler = Scheduler(
        blocks=[Block(name="only", conditions=[Condition("a", {}, target=1)])], seed=1
    )

    assert not scheduler.done
    scheduler.record(scheduler.next_trial().name, Outcome.CORRECT)

    assert scheduler.done
