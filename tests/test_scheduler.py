"""The trial scheduler: which condition next, when a block ends, what is owed.

S8 §1-2. Between-trial code, outside the frame budget -- so it may hold state and do
arbitrary arithmetic, and an error here is observable and recoverable rather than a
dropped frame.
"""

from __future__ import annotations

import random

import pytest

from wl_xcon.scheduler import (
    CAP,
    CLEARED,
    CORRECT_ONLY,
    DRUM_WARNING,
    EVERY_TRIAL,
    PRESENTED,
    RIG,
    Block,
    Condition,
    Constrained,
    Scheduler,
    Shortfall,
    Shuffled,
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


def _breaking(order, seed: int = 1, every: int = 3) -> list:
    """The engine C2a plan's probe: three conditions owing five trials each, every `every`-th trial
    a fixation break, run to the block's end. Each trial's `Draw`, in order."""
    block = Block(
        name="main", conditions=[Condition(name, {}, target=5) for name in "abc"], order=order)
    scheduler = Scheduler([block], seed=seed)
    draws = []
    for _ in range(200):
        if scheduler.finished:
            return draws
        scheduler.next_trial()
        draws.append(scheduler.drawn)
        broke = scheduler.drawn.number % every == 0
        scheduler.record(scheduler.drawn.condition.name,
                         Outcome.FIXATION_BREAK if broke else Outcome.CORRECT)
    raise AssertionError("the block never ended in 200 trials")


@pytest.mark.parametrize("order", [Shuffled(), WithReplacement(), Constrained(max_run=2)],
                         ids=["shuffled", "with-replacement", "constrained"])
@pytest.mark.parametrize("seed", [1, 2, 3])
def test_a_repeat_comes_back_within_the_next_k_trials_and_never_the_very_next(order, seed):
    """§16.3, superseding 2026-08-31's "end of the block"; the PI, 2026-10-11 and 2026-10-12: a
    random slot within the next k trials, k the block's number of conditions and at least 3, never
    the very next, in every block -- unless it is the only condition still owed, then at once, and
    its draw says so. Appended to the queue, a repeat was the very next trial 8 times in 8 under
    `WithReplacement` and `Constrained` and 3 in 8 under `Shuffled` (seed 1, every third trial a
    break: the plan's third defect)."""
    draws = _breaking(order, seed=seed)

    repeats = [draw for draw in draws if draw.repeat_of is not None]
    assert len(repeats) >= 5
    assert {draw.condition.name for draw in draws} == {"a", "b", "c"}
    for draw in repeats:
        assert draws[draw.repeat_of].condition == draw.condition
        gap = draw.number - draw.repeat_of
        assert (gap == 1) == draw.at_once
        assert 1 <= gap <= 3
    assert not any(d.at_once for d in repeats[:3]), "early on, other conditions are still owed"


def test_in_a_block_of_two_conditions_a_repeat_comes_two_or_three_trials_later():
    """The PI, 2026-10-12, "At least 3": "A repeat lands 2 or 3 trials later even in a two-condition
    block, so its position is not fixed." With k at least 2 the trial after a break was the other
    condition and the one after that the repeat, 200 seeds in 200 (the science review's D3)."""
    gaps = set()
    for seed in range(20):
        block = Block(name="b", conditions=[Condition(n, {}, target=6) for n in "ab"])
        scheduler = Scheduler([block], seed=seed)
        for _ in range(200):
            if scheduler.finished:
                break
            scheduler.next_trial()
            draw = scheduler.drawn
            if draw.repeat_of is not None and not draw.at_once:
                gaps.add(draw.number - draw.repeat_of)
            broke = draw.number % 3 == 0
            scheduler.record(draw.condition.name,
                             Outcome.FIXATION_BREAK if broke else Outcome.CORRECT)
        else:
            raise AssertionError(f"seed {seed}: the block never ended in 200 trials")

    assert gaps == {2, 3}


def test_no_repeat_waits_past_its_k_when_breaks_come_often():
    """Each repeat takes a slot no other waiting repeat holds, so two never fall due together and
    none waits past its window (the engineering review's Minor 2: 1.17% of repeats came later than
    k with six conditions breaking half the time, when slots could be shared). The bound of k is
    exact, drums aside: slot number + k is always free (see `Scheduler._repeat`); a seeded probe of
    464,202 repeats found none late."""
    for seed in range(10):
        breaks = random.Random(seed)
        block = Block(name="b", conditions=[Condition(f"c{i}", {}, target=10) for i in range(6)])
        scheduler = Scheduler([block], seed=seed)
        for _ in range(2000):
            if scheduler.finished:
                break
            scheduler.next_trial()
            draw = scheduler.drawn
            if draw.repeat_of is not None:
                assert 2 <= draw.number - draw.repeat_of <= 6 or draw.at_once, (seed, draw)
            broke = breaks.random() < 0.5
            scheduler.record(draw.condition.name,
                             Outcome.FIXATION_BREAK if broke else Outcome.CORRECT)
        else:
            raise AssertionError(f"seed {seed}: the block never ended in 2000 trials")


def test_a_repeat_never_comes_straight_after_its_break_while_another_condition_is_owed():
    """§16.3 and the PI's rule: at once only for the last condition owed. When every owed
    condition is waiting and the earliest repeat is the one the last trial placed, the next
    waiting one goes (the review's Important 1: seeds 1, 3, 14 and 19 put it straight back, `a`
    after `a`, while `b` still owed)."""
    for seed in range(20):
        block = Block(name="b", conditions=[Condition("a", {}, target=1),
                                            Condition("b", {}, target=1),
                                            Condition("c", {}, target=0),
                                            Condition("d", {}, target=0)])
        scheduler = Scheduler([block], seed=seed)
        for _ in range(50):
            if scheduler.finished:
                break
            scheduler.next_trial()
            draw = scheduler.drawn
            if draw.at_once:
                assert scheduler.owed(draw.condition.name) > 0
                assert [n for n in "ab" if n != draw.condition.name and scheduler.owed(n) > 0
                        ] == [], (seed, draw)
            scheduler.record(draw.condition.name,
                             Outcome.FIXATION_BREAK if draw.number < 2 else Outcome.CORRECT)
        else:
            raise AssertionError(f"seed {seed}: the block never ended in 50 trials")


def test_the_only_condition_still_owed_repeats_at_once_and_its_draw_says_so():
    """§16.3: "unless it is the only condition still owed, when it repeats at once, recorded"."""
    block = Block(name="b", conditions=[Condition("a", {}, target=1), Condition("b", {}, target=1)])
    scheduler = Scheduler([block], seed=1)
    first = scheduler.next_trial()
    scheduler.record(first.name, Outcome.CORRECT)
    second = scheduler.next_trial()
    scheduler.record(second.name, Outcome.FIXATION_BREAK)

    again = scheduler.next_trial()

    assert again == second
    assert (scheduler.drawn.condition, scheduler.drawn.number, scheduler.drawn.repeat_of,
            scheduler.drawn.at_once) == (second, 2, 1, True)


def test_a_waiting_repeat_holds_its_conditions_draws_and_comes_early_when_nothing_else_can():
    """A condition whose repeat is waiting is not drawn otherwise: the repeat is its next trial.
    When every condition still owed is waiting, the earliest repeat comes now, before its slot,
    though not at once. (Seed 4 gives the first repeat slot 3, so trial 2 has nothing it could
    draw but a waiting repeat.)"""
    block = Block(name="b", conditions=[Condition("a", {}, target=1), Condition("b", {}, target=1),
                                        Condition("c", {}, target=0)])
    scheduler = Scheduler([block], seed=4)
    names = []
    for _ in range(2):
        names.append(scheduler.next_trial().name)
        scheduler.record(names[-1], Outcome.FIXATION_BREAK)
    assert min(scheduler._due)[0] == 3, "the seed's precondition: the first repeat's slot"

    third = scheduler.next_trial()

    assert sorted(names) == ["a", "b"], "each breaks once, neither drawn while its repeat waits"
    assert (third.name, scheduler.drawn.repeat_of, scheduler.drawn.at_once) == (names[0], 0, False)


def test_a_repeat_still_waiting_when_its_block_ends_stays_with_that_block():
    """A criterion can end a block while a repeat waits; the next block starts with none of the
    last one's repeats, as it starts with none of its counts."""
    first = Block(name="first", conditions=[Condition("a", {}, target=100),
                                            Condition("b", {}, target=100)], criterion=(1.0, 1))
    second = Block(name="second", conditions=[Condition("c", {}, target=1)])
    scheduler = Scheduler([first, second], seed=1)
    broke = scheduler.next_trial().name
    scheduler.record(broke, Outcome.FIXATION_BREAK)
    scheduler.record(scheduler.next_trial().name, Outcome.CORRECT)
    assert scheduler.finished

    scheduler.advance()

    assert [scheduler.next_trial().name for _ in range(2)] == ["c", "c"]


def test_a_constrained_block_keeps_its_runs_short_while_two_conditions_are_owed():
    """`Constrained(max_run=2)`: a repeat never makes a run of three while another condition can
    be drawn instead, and across seeds a repeat's slot takes more than one position in its
    window (k = 3: two or three trials on), as the PI's "random slot" has it."""
    gaps = set()
    for seed in (3, 4, 5, 6, 7):
        block = Block(name="b", conditions=[Condition(n, {}, target=20) for n in "ab"],
                      order=Constrained(max_run=2))
        scheduler = Scheduler([block], seed=seed)
        runs, last = [], None
        for _ in range(200):
            if scheduler.finished:
                break
            owing = sum(scheduler.owed(name) > 0 for name in "ab")
            name = scheduler.next_trial().name
            draw = scheduler.drawn
            if draw.repeat_of is not None and not draw.at_once:
                gaps.add(draw.number - draw.repeat_of)
            runs.append((runs[-1][0] + 1 if name == last else 1, owing))
            last = name
            scheduler.record(name, Outcome.FIXATION_BREAK if draw.number % 2 == 0
                             else Outcome.CORRECT)

        assert max(length for length, owing in runs if owing == 2) <= 2
    assert len(gaps) > 1, gaps


def test_a_waiting_repeat_comes_early_rather_than_let_a_constrained_run_grow():
    """`Constrained(max_run=1)`, `a` waiting for its slot and `b` the only other condition owed: a
    second `b` in a row would break the block's limit, so `a`'s repeat comes first. (Seed 8 gives
    `a`'s repeat slot 3.)"""
    block = Block(name="b", conditions=[Condition("a", {}, target=5), Condition("b", {}, target=5),
                                        Condition("c", {}, target=0)], order=Constrained(max_run=1))
    scheduler = Scheduler([block], seed=8)
    drawn = []
    for outcome in (Outcome.FIXATION_BREAK, Outcome.CORRECT, Outcome.CORRECT):
        drawn.append(scheduler.next_trial().name)
        scheduler.record(drawn[-1], outcome)
        if len(drawn) == 1:
            assert scheduler._due[0][0] == 3, "the seed's precondition: the repeat's slot"

    assert drawn == ["a", "b", "a"]
    assert scheduler.drawn.repeat_of == 0


def test_each_draw_names_the_condition_before_it_in_its_block():
    """§16.4: "the realized sequence is recorded either way: each trial's actual predecessor,
    aborted ones included". A block's first trial has none."""
    scheduler = Scheduler(blocks=_two_blocks(), seed=1)
    seen = []
    for outcome in (Outcome.FIXATION_BREAK, Outcome.CORRECT, Outcome.CORRECT):
        seen.append((scheduler.next_trial().name, scheduler.drawn.previous))
        scheduler.record(seen[-1][0], outcome)
    scheduler.advance()
    scheduler.next_trial()

    assert seen == [("a", None), ("a", "a"), ("a", "a")]
    assert (scheduler.drawn.previous, scheduler.drawn.number) == (None, 3)


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


# --- the repeat cap (engine spec §16.6) ----------------------------------------------


def _breaking_on(cap, breaks: int, outcomes=(Outcome.FIXATION_BREAK,),
                 target: int = 3) -> Scheduler:
    """One condition owing `target` trials, its table's limit `cap`, its trials ending as
    `outcomes` say in turn, `breaks` of them."""
    scheduler = Scheduler([Block(name="b", conditions=[Condition("a", {}, target=target)])],
                          seed=1, counting=Counting(after_stimulus=OWED, cap=cap))
    for n in range(breaks):
        scheduler.record(scheduler.next_trial().name, outcomes[n % len(outcomes)])
    return scheduler


def test_past_its_cap_a_conditions_debt_is_forgiven_and_flagged_as_possible_avoidance():
    """§16.6: "past N repeats in a block, the condition's remaining debt is forgiven, its shortfall
    recorded, shown and flagged as possible avoidance". Two repeats allowed: the third break in a
    row forgives the three trials still owed, and the block can end."""
    scheduler = _breaking_on(cap=2, breaks=3)

    assert scheduler.requeued == ["a", "a"] and scheduler.counts("a").repeats == 2
    assert scheduler.shortfalls == [Shortfall("b", "a", 3, CAP, 2)]
    assert scheduler.shortfalls[0].possible_avoidance
    assert scheduler.owed("a") == 0 and scheduler.finished


def test_with_no_cap_a_condition_is_repeated_until_done():
    """The PI, 2026-10-11: with no cap set, "no limit (repeat until done)"; the console's clear
    moves past one by hand."""
    scheduler = _breaking_on(cap=None, breaks=50)

    assert scheduler.counts("a").repeats == 50 and scheduler.shortfalls == []
    assert scheduler.owed("a") == 3 and not scheduler.finished


def test_a_cap_of_zero_forgives_at_the_first_owed_trial():
    """A cap of 0: no repeat at all; the first owed trial forgives the debt."""
    scheduler = _breaking_on(cap=0, breaks=1)

    assert scheduler.requeued == [] and [s.trials for s in scheduler.shortfalls] == [3]


def test_the_repeat_limit_counts_failed_repeats_in_a_row_and_resets_when_the_condition_pays():
    """The PI, 2026-10-12: "Tries in a row of one trial" -- "The condition is moved past after 3
    failed repeats in a row, and the count resets once it is done." Counted over the block instead,
    the limit flagged conditions an animal merely broke on now and then (the science review's O1);
    here two breaks, a correct trial, two breaks and a correct trial are four repeats and no
    shortfall, and only a third failure in a row forgives."""
    run = (Outcome.FIXATION_BREAK, Outcome.FIXATION_BREAK, Outcome.CORRECT)
    paid = _breaking_on(cap=2, breaks=6, outcomes=run, target=5)
    moved_past = _breaking_on(cap=2, breaks=6, outcomes=run + run[:2] + run[:1], target=5)

    assert (paid.counts("a").repeats, paid.shortfalls, paid.owed("a")) == (4, [], 3)
    assert moved_past.shortfalls == [Shortfall("b", "a", 4, CAP, 5)]


def test_a_shortfall_the_rig_made_is_named_for_the_rig_and_not_flagged_as_avoidance():
    """The controller's ruling on the engineering review's M4: only the animal's outcomes are
    flagged as possible avoidance. A limit reached with tries a lost tracker or a fault ended is
    named for the rig, and a camera that keeps dropping a condition is not called the animal's."""
    rig = _breaking_on(cap=1, breaks=2, outcomes=(Outcome.TRACKER_LOST,))
    mixed = _breaking_on(cap=1, breaks=2, outcomes=(Outcome.FIXATION_BREAK, Outcome.FAULT))
    animal = _breaking_on(cap=1, breaks=2, outcomes=(Outcome.FIXATION_BREAK, Outcome.NO_FIXATION))

    assert [(s.because, s.possible_avoidance) for s in rig.shortfalls] == [(RIG, False)]
    assert [(s.because, s.possible_avoidance) for s in mixed.shortfalls] == [(RIG, False)]
    assert [(s.because, s.possible_avoidance) for s in animal.shortfalls] == [(CAP, True)]


def test_a_wrong_answer_left_unpaid_never_feeds_the_repeat_limit():
    """The controller's ruling on the engineering review's I3: under "until N correct" a wrong
    answer is not placed as a repeat, so a condition the animal keeps getting wrong is neither
    forgiven nor flagged as avoidance."""
    table = Counting(after_stimulus=OWED, outcomes={"wrong_target": UNPAID}, cap=0)
    scheduler = Scheduler([Block(name="b", conditions=[Condition("a", {}, target=2)])], seed=1,
                          counting=table)
    for _ in range(5):
        scheduler.record(scheduler.next_trial().name, Outcome.WRONG_TARGET)

    assert (scheduler.shortfalls, scheduler.requeued, scheduler.owed("a")) == ([], [], 2)


def test_a_forgiven_conditions_waiting_repeat_is_not_drawn_and_none_is_placed_again():
    """The placement guard (`record`: a repeat only while the condition owes anything) and
    `_forgive`'s dropping of a waiting repeat have their consumer in a person's clear: `a` breaks
    and its repeat waits; the rest of `a` is cleared, which takes the waiting repeat with it; the
    draws that follow are `b`'s alone, and a late result for `a` places nothing. (Task 7's review,
    minor 6: this test first recorded `a` three times with no draw between, which no run does.)"""
    scheduler = Scheduler(
        [Block(name="b", conditions=[Condition("a", {}, target=3), Condition("b", {}, target=40)])],
        seed=1, counting=Counting(after_stimulus=OWED))
    for _ in range(5):
        name = scheduler.next_trial().name
        if name == "a":
            break
        scheduler.record(name, Outcome.CORRECT)
    else:
        raise AssertionError("the seed draws a within five trials")
    scheduler.record("a", Outcome.FIXATION_BREAK)
    assert [due[2] for due in scheduler._due] == ["a"], "the break's repeat waits"

    assert scheduler.clear("a", rest=True) is None
    drawn = []
    for _ in range(12):
        name = scheduler.next_trial().name
        drawn.append(name)
        scheduler.record(name, Outcome.CORRECT)
    scheduler.record("a", Outcome.FIXATION_BREAK)

    assert scheduler._due == [] and scheduler.requeued == ["a"]
    assert set(drawn) == {"b"} and scheduler.owed("a") == 0
    assert [(s.condition, s.trials, s.because) for s in scheduler.shortfalls] == [("a", 3, CLEARED)]


def test_any_answer_ends_a_trial_so_its_conditions_next_trial_counts_its_failures_from_0():
    """The PI, 2026-10-18, "1: an answer ends the trial": the repeat limit counts failed tries of
    one trial, and any answer, right or wrong, starts it over. Under "until N correct" a wrong
    answer pays nothing, and the count went on through it: a break, a wrong answer and a break at a
    limit of 1 forgave the whole debt as possible avoidance (Task 7's review, Important 1)."""
    table = Counting(after_stimulus=OWED, outcomes={"wrong_target": UNPAID}, cap=1)
    scheduler = Scheduler([Block(name="b", conditions=[Condition("a", {}, target=3)])], seed=1,
                          counting=table)
    for outcome in (Outcome.FIXATION_BREAK, Outcome.WRONG_TARGET, Outcome.FIXATION_BREAK):
        scheduler.record(scheduler.next_trial().name, outcome)

    assert (scheduler.shortfalls, scheduler.counts("a").in_a_row) == ([], 1)
    scheduler.record(scheduler.next_trial().name, Outcome.FIXATION_BREAK)
    assert [(s.because, s.trials) for s in scheduler.shortfalls] == [(CAP, 3)]


def test_a_drummed_answer_ends_the_trial_too_so_the_next_break_is_a_new_trials_first_failure():
    """The controller's ruling I3 on the revision's review: the reset sits above `record`'s drum
    branch, which returns early, so the PI's "1: an answer ends the trial" holds for a drummed
    answer as well. At a limit of 1, `x` breaks (failure 1, a repeat waits); drumming is switched
    on and the repeat is answered wrong and drummed; drumming is switched off, which drops the
    drum; `x`'s next trial breaks once -- the first failure of a new trial, so a repeat is placed
    and nothing is forgiven."""
    scheduler = Scheduler(
        [Block(name="b", conditions=[Condition("x", {}, target=3), Condition("y", {}, target=40)])],
        seed=1, counting=Counting(after_stimulus=OWED, cap=1))

    def draw_x() -> None:
        for _ in range(20):
            name = scheduler.next_trial().name
            if name == "x":
                return
            scheduler.record(name, Outcome.CORRECT)
        raise AssertionError("x is drawn within twenty trials")

    draw_x()
    scheduler.record("x", Outcome.FIXATION_BREAK)
    assert scheduler.counts("x").in_a_row == 1
    scheduler.drum("block")
    draw_x()
    assert scheduler.record("x", Outcome.WRONG_TARGET) == OWED
    assert scheduler.drawn is not None
    scheduler.drum("off")
    draw_x()
    scheduler.record("x", Outcome.FIXATION_BREAK)

    assert scheduler.shortfalls == []
    assert scheduler.counts("x").in_a_row == 1


def test_the_tasks_repeat_limit_holds_in_a_block_counted_by_its_own_table_unless_it_sets_one():
    """The PI, 2026-10-18, "No: the task's limit applies unless the block sets its own": a block
    counting by a named table, which sets no limit, keeps the structure's limit of 1; a block whose
    own table sets 2 is moved past at its third failure in a row instead. A named table removed the
    structure's limit."""
    def moved_past(table) -> list:
        block = Block(name="b", conditions=[Condition("a", {}, target=3)], counting=table)
        scheduler = Scheduler([block], seed=1, counting=Counting(after_stimulus=OWED, cap=1))
        for _ in range(5):
            if scheduler.finished:
                break
            scheduler.record(scheduler.next_trial().name, Outcome.FIXATION_BREAK)
        return [short.after_trial for short in scheduler.shortfalls]

    assert moved_past(CORRECT_ONLY) == [1]
    assert moved_past(Counting(after_stimulus=OWED, cap=2)) == [2]


def test_a_rig_failure_anywhere_in_the_row_names_it_for_the_rig_and_an_ended_trial_forgets_it():
    """Task 7's review, Important 2: a shortfall is flagged as possible avoidance only when every
    failed try in the row was the animal's, so a lost tracker on the row's first try names it for
    the rig as surely as one on its last; and an answer, ending the trial, clears the rig's
    failures with the rest of its count, so the animal's own failures after it are flagged."""
    first = _breaking_on(cap=1, breaks=2, outcomes=(Outcome.TRACKER_LOST, Outcome.FIXATION_BREAK))
    ended = _breaking_on(cap=1, breaks=4, target=5, outcomes=(
        Outcome.TRACKER_LOST, Outcome.CORRECT, Outcome.FIXATION_BREAK, Outcome.FIXATION_BREAK))

    assert [(s.because, s.possible_avoidance) for s in first.shortfalls] == [(RIG, False)]
    assert [(s.because, s.possible_avoidance) for s in ended.shortfalls] == [(CAP, True)]


def test_a_cleared_trial_forgives_one_of_the_debt_and_drops_its_waiting_repeat():
    """The PI, 2026-10-11: "manually advance beyond or clear a specific trial in the count".
    Clearing the trial a repeat is waiting for forgives one trial, records who did it, and the
    repeat never comes; a clear of nothing owed, or of no condition of the block, is refused with a
    sentence."""
    block = Block(name="b", conditions=[Condition("a", {}, target=2), Condition("b", {}, target=2)])
    scheduler = Scheduler([block], seed=1)
    broke = scheduler.next_trial().name
    scheduler.record(broke, Outcome.FIXATION_BREAK)

    assert scheduler.clear(broke, by="jake") is None

    assert scheduler.owed(broke) == 1
    assert scheduler.shortfalls == [Shortfall("b", broke, 1, CLEARED, 0, "jake")]
    assert not scheduler.shortfalls[0].possible_avoidance
    draws = []
    while not scheduler.finished:
        scheduler.next_trial()
        draws.append(scheduler.drawn)
        scheduler.record(scheduler.drawn.condition.name, Outcome.CORRECT)
    assert all(draw.repeat_of is None for draw in draws) and len(draws) == 3
    assert scheduler.clear("c") == "block 'b' has no condition 'c', so nothing is cleared"
    assert scheduler.clear(broke) == f"'{broke}' owes nothing in block 'b', so nothing is cleared"


def test_clearing_a_drummed_trial_moves_past_it():
    """"Advance beyond": the drum's trial waiting to come back is dropped with the trial cleared."""
    scheduler = Scheduler([Block(name="b", conditions=[Condition("a", {}, target=2)], drum=True)],
                          seed=1)
    scheduler.record(scheduler.next_trial().name, Outcome.WRONG_TARGET)

    scheduler.clear("a")
    scheduler.next_trial()

    assert not scheduler.drawn.drummed and scheduler.owed("a") == 1


def test_clearing_the_rest_of_a_condition_forgives_all_it_still_owes():
    """The science review's D5: a condition the animal refuses, owing many, is moved past at
    once."""
    block = Block(name="b", conditions=[Condition("a", {}, target=20),
                                        Condition("b", {}, target=1)])
    scheduler = Scheduler([block], seed=1)

    assert scheduler.clear("a", by="jake", rest=True) is None

    assert scheduler.owed("a") == 0
    assert scheduler.shortfalls == [Shortfall("b", "a", 20, CLEARED, None, "jake")]


def test_clearing_a_condition_that_is_queued_keeps_it_from_the_next_draw():
    """A condition the shuffle has queued and a person then clears the rest of is not drawn: the
    queue's entry went stale, and `_peek` drops it (the controller's ruling from Task 4's review)."""
    block = Block(name="b", conditions=[Condition(name, {}, target=2) for name in "abc"],
                  order=Shuffled())
    scheduler = Scheduler([block], seed=1)
    scheduler.next_trial()
    scheduler.record(scheduler.drawn.condition.name, Outcome.CORRECT)
    queued = scheduler.upcoming()[0]

    assert scheduler.clear(queued, rest=True) is None
    scheduler.next_trial()

    assert scheduler.drawn.condition.name != queued


# --- drumming (the PI, 2026-10-11) -----------------------------------------------


def _drummed(**block) -> Scheduler:
    """Three conditions owing two trials each, by a table that spends breaks after the stimulus."""
    return Scheduler(
        [Block(name="b", conditions=[Condition(n, {}, target=2) for n in "abc"], **block)],
        seed=1, counting=Counting(after_stimulus=SPENT),
    )


def test_a_drummed_trial_comes_back_at_once_until_it_is_correct():
    """"A training tool ... where a trial is repeated until correct": a wrong answer, which counts
    elsewhere, and a break, which this table spends, both pay nothing and bring the same condition
    straight back; the correct one pays. Each repeat's draw says it was drummed."""
    scheduler = _drummed(drum=True)
    first = scheduler.next_trial()
    draws = []
    for outcome in (Outcome.WRONG_TARGET, Outcome.TARGET_BREAK, Outcome.CORRECT):
        assert scheduler.record(scheduler.drawn.condition.name, outcome) == (
            COUNTED if outcome is Outcome.CORRECT else OWED)
        if outcome is not Outcome.CORRECT:
            scheduler.next_trial()
            draws.append(scheduler.drawn)

    assert [d.condition for d in draws] == [first, first]
    assert [(d.repeat_of, d.at_once, d.drummed, d.drumming) for d in draws] == [
        (0, True, True, "block"), (1, True, True, "block")]
    assert scheduler.owed(first.name) == 1 and scheduler.counts(first.name).spent == 0
    assert scheduler.requeued == [first.name, first.name], "each failed try is logged as owed"


def test_only_a_trials_first_try_is_judged_for_the_criterion_under_drumming():
    """The PI, 2026-10-12, "Leave drummed repeats out": "Only each trial's first try is judged for
    the criterion. The repeats are still recorded as what they were." Judging the repeats let an
    animal that always picks one side meet 60% over 30 at 50% true accuracy (the science review's
    D2): lose-shift solves a correction trial."""
    scheduler = Scheduler(
        [Block(name="b", conditions=[Condition("a", {}, target=100)], criterion=(0.5, 2),
               drum=True)], seed=1)
    for outcome in (Outcome.WRONG_TARGET, Outcome.CORRECT):
        scheduler.record(scheduler.next_trial().name, outcome)

    assert scheduler.drawn.drummed and not scheduler.finished, "one first try, not two"
    scheduler.record(scheduler.next_trial().name, Outcome.CORRECT)
    assert scheduler.finished, "two first tries, half of them right"


def _chain(*outcomes) -> list:
    """The criterion window after one drummed trial's tries, each of `outcomes` in turn."""
    scheduler = Scheduler(
        [Block(name="b", conditions=[Condition("a", {}, target=100)], criterion=(0.9, 5),
               drum=True)], seed=1)
    for outcome in outcomes:
        scheduler.record(scheduler.next_trial().name, outcome)
    return list(scheduler._window)


def test_a_drummed_trials_first_answer_is_judged_when_its_first_try_ended_before_one():
    """The PI, 2026-10-18, "Judge its first answer": "If the first try ends before any answer, the
    first try that does answer is judged. Repeats after a wrong answer stay out." Leaving it out
    left the harder trials of an animal that breaks when unsure out of its criterion."""
    assert _chain(Outcome.FIXATION_BREAK, Outcome.CORRECT) == [1]
    assert _chain(Outcome.FIXATION_BREAK, Outcome.WRONG_TARGET, Outcome.CORRECT) == [0]
    assert _chain(Outcome.WRONG_TARGET, Outcome.CORRECT) == [0]
    assert _chain(Outcome.CORRECT, Outcome.FIXATION_BREAK, Outcome.CORRECT) == [1, 1], "two trials"


def test_a_drummed_block_that_ends_on_a_wrong_first_try_opens_the_next_with_its_own_condition():
    """A criterion met on a wrong first try leaves a drum waiting; the next block must not draw it
    (its condition is not the next block's: `next_trial` raised `StopIteration`)."""
    blocks = [Block(name="A", conditions=[Condition("a", {}, target=100)], criterion=(0.5, 2),
                    drum=True),
              Block(name="B", conditions=[Condition("b", {}, target=2)])]
    scheduler = Scheduler(blocks, seed=1)
    for outcome in (Outcome.CORRECT, Outcome.WRONG_TARGET):
        scheduler.record(scheduler.next_trial().name, outcome)
    assert scheduler.finished and scheduler.drum_tries == 1, "a drum is waiting"

    scheduler.advance()

    assert scheduler.next_trial().name == "b" and not scheduler.drawn.drummed


def test_a_drummed_catch_condition_finishes_on_correct_rejections():
    """The controller's ruling on the engineering review's I1: a drum ends on a right answer, and a
    catch trial's right answer is a correct rejection; drummed, the condition owed 2 after 50 of
    them and its block never ended."""
    block = Block(name="b", conditions=[Condition("catch", {}, target=2)], drum=True)
    scheduler = Scheduler([block], seed=1,
                          counting=Counting(after_stimulus=OWED, withholding=True))
    for _ in range(2):
        assert scheduler.record(scheduler.next_trial().name, Outcome.CORRECT_REJECT) == COUNTED

    assert scheduler.finished and not scheduler.drawn.drummed


def test_a_drummed_trials_failed_tries_in_a_row_are_counted_for_the_consoles_warning():
    """The PI, 2026-10-12, "After 10 in a row": the first try and each drum's repeat that fails are
    tries in a row of one trial; a right answer ends the run of them."""
    scheduler = Scheduler([Block(name="b", conditions=[Condition("a", {}, target=2)], drum=True)],
                          seed=1)
    tries = []
    for _ in range(DRUM_WARNING):
        scheduler.record(scheduler.next_trial().name, Outcome.WRONG_TARGET)
        tries.append(scheduler.drum_tries)
    scheduler.record(scheduler.next_trial().name, Outcome.CORRECT)

    assert tries == list(range(1, DRUM_WARNING + 1)) and DRUM_WARNING == 10
    assert scheduler.drum_tries == 0


def test_a_trainer_switches_drumming_for_a_block_or_a_run_or_off():
    """The PI, 2026-10-11: "switched on per block or run by the trainer". On for the block ends with
    it; on for the run carries on; off holds to the block's end, over a block that declares it, and
    drops a drum waiting to come back."""
    blocks = [Block(name=n, conditions=[Condition(n.lower(), {}, target=1)], drum=declared)
              for n, declared in (("A", False), ("B", False), ("C", True), ("D", False))]
    scheduler = Scheduler(blocks, seed=1)
    seen = [scheduler.drumming]
    scheduler.drum("block")
    seen.append(scheduler.drumming)
    scheduler.advance()
    seen.append(scheduler.drumming)
    scheduler.advance()
    seen.append(scheduler.drumming)
    scheduler.record(scheduler.next_trial().name, Outcome.WRONG_TARGET)
    scheduler.drum("off")
    seen.append(scheduler.drumming)
    seen.append(scheduler.next_trial().name == "c" and scheduler.drawn.drummed)
    scheduler.drum("run")
    scheduler.record("c", Outcome.CORRECT)
    scheduler.advance()
    seen.append(scheduler.drumming)

    assert seen == [None, "block", None, "block", None, False, "run"]
    with pytest.raises(ValueError, match="drumming is switched block, run, off"):
        scheduler.drum("on")


def test_a_switch_made_as_a_block_finishes_is_for_the_next_block():
    """The loop drains a trainer's commands before it advances, so a switch that arrives as a block
    finishes is for the next block, and says which (the engineering review's Minor 10: it was
    lost, its control row naming the block that had ended)."""
    blocks = [Block(name=n, conditions=[Condition(n.lower(), {}, target=1)]) for n in "ABC"]
    scheduler = Scheduler(blocks, seed=1)
    scheduler.record(scheduler.next_trial().name, Outcome.CORRECT)
    assert scheduler.finished

    said = scheduler.drum("block")
    scheduler.advance()

    assert (said, scheduler.block.name, scheduler.drumming) == ("B", "B", "block")
    scheduler.record(scheduler.next_trial().name, Outcome.CORRECT)
    scheduler.advance()
    assert (scheduler.block.name, scheduler.drumming) == ("C", None), "the switch was B's alone"
    scheduler.record(scheduler.next_trial().name, Outcome.CORRECT)
    assert scheduler.done
    assert scheduler.drum("off") == "C", "the last block has no next: the switch is its own"


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


@pytest.mark.parametrize("withholds, expected", [
    (True, {"EVERY_TRIAL": COUNTED, "PRESENTED": COUNTED, "CORRECT_ONLY": UNPAID}),
    (False, {"EVERY_TRIAL": SPENT, "PRESENTED": SPENT, "CORRECT_ONLY": OWED}),
])
@pytest.mark.parametrize("name", ["EVERY_TRIAL", "PRESENTED", "CORRECT_ONLY"])
def test_no_response_is_the_structures_answer_under_a_blocks_table_too(name, withholds, expected):
    """The PI's decision 6: where the structure withholds, no response is a miss -- an answer, as a
    false alarm is -- whatever the block's table declares for it. Under "until N correct" it pays
    nothing and is not shown again; where the structure does not withhold, the table's own class
    stands."""
    table = {"EVERY_TRIAL": EVERY_TRIAL, "PRESENTED": PRESENTED, "CORRECT_ONLY": CORRECT_ONLY}[name]
    block = Block(name="b", conditions=[Condition("a", {}, target=3)], counting=table)
    scheduler = Scheduler([block], seed=1,
                          counting=Counting(after_stimulus=OWED, withholding=withholds))

    assert scheduler.record(scheduler.next_trial().name, Outcome.NO_RESPONSE) == expected[name]
    assert scheduler.requeued == (["a"] if expected[name] == OWED else [])


def test_a_condition_already_paid_is_not_placed_again_when_a_trial_of_it_is_owed():
    """`record` places a repeat only for a condition that still owes: two breaks owe it again, a
    correct trial pays it, and a late trial of it that breaks leaves `requeued` as it was. Called
    directly: `next_trial` never draws a condition that owes nothing (`_drawable`), so the guard
    is reached only once a console clear or a repeat limit can end a debt while a repeat of it
    waits (`Scheduler.clear`, `_forgive`; engine build C2a's Tasks 7 and 8)."""
    block = Block(name="b", conditions=[Condition("a", {}, target=1)])
    scheduler = Scheduler([block], seed=1, counting=Counting(after_stimulus=OWED))
    for outcome in (Outcome.FIXATION_BREAK, Outcome.FIXATION_BREAK, Outcome.CORRECT):
        scheduler.record(scheduler.next_trial().name, outcome)
    assert scheduler.requeued == ["a", "a"] and scheduler.owed("a") == 0

    assert scheduler.record("a", Outcome.FIXATION_BREAK) == OWED

    assert scheduler.requeued == ["a", "a"]
