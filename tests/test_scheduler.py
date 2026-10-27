"""The trial scheduler: which condition next, when a block ends, what is owed.

S8 §1-2. Between-trial code, outside the frame budget -- so it may hold state and do
arbitrary arithmetic, and an error here is observable and recoverable rather than a
dropped frame.
"""

from __future__ import annotations

import random

import pytest

from wl_xcon.scheduler import (
    BACK,
    CAP,
    CLEARED,
    CORRECT_ONLY,
    DRUM_WARNING,
    EVERY_TRIAL,
    FALL_BACK,
    NEXT,
    PRESENTED,
    RIG,
    RULE,
    RUN_TIME,
    TIME,
    TRAINING,
    Block,
    BlockEnd,
    Condition,
    ConditionReport,
    Constrained,
    Scheduler,
    Shortfall,
    Shuffled,
    WithReplacement,
)
from wl_xcon.task import (
    COUNTED, NO_LIMIT, OWED, SPENT, UNPAID, Balanced, ByCriterion, Counting, Cyclic, Fixed, Outcome,
    Random,
)


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


def test_a_repeat_still_waiting_when_its_block_is_left_stays_with_that_block():
    """A block left while a repeat waits -- `advance` asks nothing of the block it leaves -- starts
    the next with none of its repeats, as it starts with none of its counts. Since the PI's decision
    of 2026-10-18 (a criterion block's targets are a minimum) no end rule leaves one so; this
    guards `advance`."""
    first = Block(name="first", conditions=[Condition("a", {}, target=100),
                                            Condition("b", {}, target=100)], criterion=(1.0, 1))
    second = Block(name="second", conditions=[Condition("c", {}, target=1)])
    scheduler = Scheduler([first, second], seed=1)
    broke = scheduler.next_trial().name
    scheduler.record(broke, Outcome.FIXATION_BREAK)
    scheduler.record(scheduler.next_trial().name, Outcome.CORRECT)
    assert scheduler._due and not scheduler.finished

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


def test_a_rule_judges_answers_only():
    """The PI, 2026-10-18: a rule judges answers only -- right, or wrong, a miss among them where
    the task makes no response an answer -- and "a trial with no answer neither adds to nor breaks a
    streak or a percentage": a fixation break, and no response where the structure does not
    withhold, are no answers, so the two right answers around them are in a row. Where it
    withholds, no response is a miss, judged."""
    def window(withholding: bool) -> list:
        block = Block(name="b", conditions=[Condition("a", {}, target=100)], criterion=(1.0, 2))
        scheduler = Scheduler([block], seed=1,
                              counting=Counting(after_stimulus=SPENT, withholding=withholding))
        for outcome in (Outcome.CORRECT, Outcome.FIXATION_BREAK, Outcome.NO_RESPONSE,
                        Outcome.CORRECT):
            scheduler.record(scheduler.next_trial().name, outcome)
        return list(scheduler._window)

    assert window(withholding=False) == [1, 1]
    assert window(withholding=True) == [0, 1]


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
    block = Block(name="b", conditions=[Condition("a", {}, target=2)], criterion=(0.5, 2))
    scheduler = Scheduler([block], seed=1, counting=Counting(after_stimulus=SPENT))

    for outcome in (Outcome.CORRECT, Outcome.TARGET_BREAK):
        scheduler.record(scheduler.next_trial().name, outcome)

    assert scheduler.owed("a") == 0
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
    block = Block(name="b", conditions=[Condition("catch", {}, target=2)], criterion=(1.0, 2))
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
        seed=1, counting=Counting(after_stimulus=OWED), clearing=True)
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


def _mixed(**block) -> Scheduler:
    """A block of two conditions, `detect` naming the `detection` structure -- breaks after its
    stimulus used up, no response a miss, no repeat -- and `search` naming none, so playing the
    default's: breaks shown again, no response no answer, no limit (engine build C2b)."""
    detection = Counting(after_stimulus=SPENT, withholding=True, cap=0)
    search = Counting(after_stimulus=OWED)
    mixed = Block(name="mixed", conditions=[
        Condition("detect", {}, target=5, structure="detection"),
        Condition("search", {}, target=5),
    ], **block)
    return Scheduler([mixed], seed=1, counting=search, countings={"detection": detection})


def test_each_condition_counts_by_the_table_of_the_structure_it_plays():
    """Engine build C2b (the PI, 2026-10-07: "a task declares several trial structures; each
    condition names its own; interleaving them in a block is ordinary"): a condition naming a
    structure counts by that structure's table -- what a break after its stimulus does, whether no
    response is an answer, its repeat limit -- and one naming none by the default's."""
    scheduler = _mixed()

    assert scheduler.record("detect", Outcome.TARGET_BREAK) == SPENT
    assert scheduler.record("search", Outcome.TARGET_BREAK) == OWED
    assert scheduler.record("detect", Outcome.NO_RESPONSE) == COUNTED
    assert scheduler.record("search", Outcome.NO_RESPONSE) == OWED
    # `detect`'s structure moves a condition past at its first failure in a row; `search`'s has
    # no limit, so its failures were placed as repeats.
    assert scheduler.record("detect", Outcome.FIXATION_BREAK) == OWED
    assert [(s.condition, s.because) for s in scheduler.shortfalls] == [("detect", CAP)]
    assert scheduler.counts("search").repeats == 2
    # And judged by it: `detect`'s miss is a wrong answer, `search`'s no response no answer.
    assert (scheduler.counts("detect").wrong, scheduler.counts("search").wrong) == (1, 0)


def test_a_blocks_own_table_replaces_each_structures_and_each_structure_says_what_is_an_answer():
    """A block counting by its own table counts every condition by it, whatever structure each
    plays; whether no response is an answer stays each structure's (the controller's ruling M8 on
    the engine C2a plan's revision): a miss under `detect`, used up as no answer under `search`."""
    scheduler = _mixed(counting=PRESENTED)

    assert scheduler.record("detect", Outcome.TARGET_BREAK) == SPENT
    assert scheduler.record("search", Outcome.TARGET_BREAK) == SPENT
    assert scheduler.record("detect", Outcome.NO_RESPONSE) == COUNTED
    assert scheduler.record("search", Outcome.NO_RESPONSE) == SPENT


def test_a_block_offers_clear_when_any_structure_its_conditions_play_can_owe():
    """`clearable` (the engine C2a plan's Minor 3) asks every structure the open block's conditions
    play: a block of conditions all playing a structure that owes nothing offers no *clear*; one
    more condition playing a structure that owes, and it does."""
    def offered(*structures) -> bool:
        block = Block(name="b", conditions=[
            Condition(f"c{n}", {}, target=1, structure=name) for n, name in enumerate(structures)])
        return Scheduler([block], seed=1, counting=Counting(after_stimulus=OWED),
                         countings={"flat": EVERY_TRIAL}).clearable

    assert offered("flat", "flat") is False
    assert offered("flat", None) is True


def test_a_blocks_no_limit_removes_its_tasks_repeat_limit():
    """XC-380 (engine build C2b): a block's own table says "no limit" with `NO_LIMIT`, where `None`
    keeps the task's -- so a hold-training block can repeat a trial until it is done though its
    task moves a condition past at its second failure in a row. In a structure's own table the two
    say the same."""
    def moved_past(block_cap, structure_cap=1) -> list:
        table = Counting(after_stimulus=OWED, cap=block_cap)
        block = Block(name="b", conditions=[Condition("a", {}, target=3)], counting=table)
        scheduler = Scheduler([block], seed=1,
                              counting=Counting(after_stimulus=OWED, cap=structure_cap))
        for _ in range(6):
            if scheduler.finished:
                break
            scheduler.record(scheduler.next_trial().name, Outcome.FIXATION_BREAK)
        return [short.after_trial for short in scheduler.shortfalls]

    assert moved_past(None) == [1]
    assert moved_past(NO_LIMIT) == []
    assert moved_past(None, structure_cap=NO_LIMIT) == []


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
    scheduler = Scheduler([block], seed=1, clearing=True)
    broke = scheduler.next_trial().name
    scheduler.record(broke, Outcome.FIXATION_BREAK)

    assert scheduler.clear(broke, by="jake") is None

    assert scheduler.owed(broke) == 1
    assert scheduler.shortfalls == [Shortfall("b", broke, 1, CLEARED, 0, "jake")]
    assert not scheduler.shortfalls[0].possible_avoidance
    draws = []
    for _ in range(10):
        if scheduler.finished:
            break
        scheduler.next_trial()
        draws.append(scheduler.drawn)
        scheduler.record(scheduler.drawn.condition.name, Outcome.CORRECT)
    else:
        raise AssertionError("the block never finished within 10 trials")
    assert all(draw.repeat_of is None for draw in draws) and len(draws) == 3
    assert scheduler.clear("c") == "block 'b' has no condition 'c', so nothing is cleared"
    assert scheduler.clear(broke) == f"'{broke}' owes nothing in block 'b', so nothing is cleared"


def test_clearing_one_trial_starts_its_conditions_failed_tries_over():
    """The PI, 2026-10-18, "End that waiting trial; count starts over": *clear one* moves past the
    trial whose repeat waits, and the condition's next trial counts its failures from 0, so a limit
    of 1 does not forgive the rest of its debt at the condition's next failure."""
    block = Block(name="b", conditions=[Condition("a", {}, target=3)])
    scheduler = Scheduler([block], seed=1, counting=Counting(after_stimulus=OWED, cap=1),
                          clearing=True)
    scheduler.record(scheduler.next_trial().name, Outcome.FIXATION_BREAK)

    assert scheduler.clear("a") is None
    scheduler.record(scheduler.next_trial().name, Outcome.FIXATION_BREAK)

    assert [s.because for s in scheduler.shortfalls] == [CLEARED]
    assert (scheduler.owed("a"), scheduler.counts("a").in_a_row) == (2, 1)


def test_clearing_one_trial_forgets_the_rigs_failures_in_its_row_too():
    """Task 8's review, Important 1: decision 9 starts the trial's count over, the rig's failures
    in the row with the animal's, so the animal's own failures after a clear are flagged."""
    block = Block(name="b", conditions=[Condition("a", {}, target=3)])
    scheduler = Scheduler([block], seed=1, counting=Counting(after_stimulus=OWED, cap=1),
                          clearing=True)
    scheduler.record(scheduler.next_trial().name, Outcome.TRACKER_LOST)

    assert scheduler.clear("a") is None
    for _ in range(2):
        if scheduler.finished:
            break
        scheduler.record(scheduler.next_trial().name, Outcome.FIXATION_BREAK)

    assert [(s.because, s.possible_avoidance) for s in scheduler.shortfalls] == [
        ("cleared", False), ("cap", True)]


def test_a_switch_made_as_a_block_ends_reads_against_the_next_block():
    """Task 8's review, Important 2: `drumming_switched` is what `drumming` reads for the block a
    switch made now is for, had none been made -- the next block's own `drum`, or a run's switch,
    once this block's end rule is met; this block's reading before that."""
    blocks = [Block(name="A", conditions=[Condition("a", {}, target=1)], counting=EVERY_TRIAL,
                    drum=True),
              Block(name="B", conditions=[Condition("b", {}, target=1)]),
              Block(name="C", conditions=[Condition("c", {}, target=1)], drum=True)]
    scheduler = Scheduler(blocks, seed=1)
    assert scheduler.drumming_switched == "block"
    scheduler.record(scheduler.next_trial().name, Outcome.CORRECT)
    assert scheduler.finished and scheduler.drumming_switched is None
    scheduler.drum("run")
    assert scheduler.drumming_switched == "run"
    scheduler.advance()
    assert (scheduler.drumming, scheduler.drumming_switched) == ("run", "run")
    scheduler.record(scheduler.next_trial().name, Outcome.CORRECT)
    assert scheduler.drumming_switched == "run"
    scheduler.drum("off")
    # The off is pending for block C now, which declares drum: it reads what the switch makes it.
    assert scheduler.drumming_switched is None


@pytest.mark.parametrize("next_drums", [False, True])
@pytest.mark.parametrize(("first", "second", "second_was"),
                         [("block", "off", "block"), ("off", "block", None)])
def test_a_second_switch_in_one_drain_reads_the_first_one_pending(
        next_drums, first, second, second_was):
    """Task 8's re-review, minor: a switch already carried to the next block (`_carried`) is what
    the next switch's `drumming_switched` reads, not the next block's own `drum`."""
    blocks = [Block(name="A", conditions=[Condition("a", {}, target=1)], counting=EVERY_TRIAL),
              Block(name="B", conditions=[Condition("b", {}, target=1)], drum=next_drums)]
    scheduler = Scheduler(blocks, seed=1)
    scheduler.record(scheduler.next_trial().name, Outcome.CORRECT)
    assert scheduler.finished

    assert scheduler.drumming_switched == ("block" if next_drums else None)
    assert scheduler.drum(first) == "B"
    assert scheduler.drumming_switched == second_was
    scheduler.drum(second)
    scheduler.advance()
    assert scheduler.drumming == (None if second == "off" else "block")


def test_clearing_a_drummed_trial_moves_past_it():
    """"Advance beyond": the drum's trial waiting to come back is dropped with the trial cleared."""
    scheduler = Scheduler([Block(name="b", conditions=[Condition("a", {}, target=2)], drum=True)],
                          seed=1, clearing=True)
    scheduler.record(scheduler.next_trial().name, Outcome.WRONG_TARGET)

    scheduler.clear("a")
    scheduler.next_trial()

    assert not scheduler.drawn.drummed and scheduler.owed("a") == 1


def test_clearing_the_rest_of_a_condition_forgives_all_it_still_owes():
    """The science review's D5: a condition the animal refuses, owing many, is moved past at
    once."""
    block = Block(name="b", conditions=[Condition("a", {}, target=20),
                                        Condition("b", {}, target=1)])
    scheduler = Scheduler([block], seed=1, clearing=True)

    assert scheduler.clear("a", by="jake", rest=True) is None

    assert scheduler.owed("a") == 0
    assert scheduler.shortfalls == [Shortfall("b", "a", 20, CLEARED, None, "jake")]


def test_clearing_a_condition_that_is_queued_keeps_it_from_the_next_draw():
    """A condition the shuffle has queued and a person then clears the rest of is not drawn: the
    queue's entry went stale, and `_peek` drops it (the controller's ruling from Task 4's
    review)."""
    block = Block(name="b", conditions=[Condition(name, {}, target=2) for name in "abc"],
                  order=Shuffled())
    scheduler = Scheduler([block], seed=1, clearing=True)
    scheduler.next_trial()
    scheduler.record(scheduler.drawn.condition.name, Outcome.CORRECT)
    queued = scheduler.upcoming()[0]

    assert scheduler.clear(queued, rest=True) is None
    scheduler.next_trial()

    assert scheduler.drawn.condition.name != queued


def test_clear_is_a_training_aid_off_until_a_trainer_switches_it_on():
    """The PI, 2026-10-18, "Drumming and 'clear'": clearing trials from the count is a training
    aid, off by default; a clear while it is off is refused with a sentence and changes nothing --
    a control not switched on, not a refusal of a task. The trainer switches it on, and off, for the
    rest of the run, and the percentage setting beside it; nothing else is switched so."""
    scheduler = Scheduler([Block(name="b", conditions=[Condition("a", {}, target=3)])], seed=1)
    off = ("clear is a training aid, and it is off in this run; a trainer switches it on to clear "
           "a trial from the count")

    assert scheduler.clear("a") == off and scheduler.shortfalls == []
    scheduler.train("clear", True)
    assert scheduler.clear("a") is None and scheduler.owed("a") == 2
    scheduler.train("clear", False)
    scheduler.train("first_answers", True)
    assert scheduler.clear("a") == off and scheduler.first_answers
    assert TRAINING == ("clear", "first_answers")
    with pytest.raises(ValueError, match="a training setting is clear or first_answers"):
        scheduler.train("drum", True)


def test_each_draw_names_the_training_aids_on_as_it_was_drawn():
    """The PI, 2026-10-18: while a training aid is on "the record marks it on every trial" --
    drumming, by a block's declaration or a trainer's switch, and *clear*. The percentage setting is
    no aid; its switch is in the control rows."""
    scheduler = Scheduler([Block(name="b", conditions=[Condition("a", {}, target=5)])], seed=1)
    seen = []
    for switch in (None, ("clear", True), ("drum", "run"), ("first_answers", True)):
        if switch is not None and switch[0] == "drum":
            scheduler.drum(switch[1])
        elif switch is not None:
            scheduler.train(*switch)
        seen.append(scheduler.next_trial() and scheduler.drawn.aids)
        scheduler.record("a", Outcome.CORRECT)

    assert seen == [(), ("clear",), ("drumming", "clear"), ("drumming", "clear")]


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


def test_only_a_trials_first_answer_is_judged_for_a_percentage_under_the_first_answers_setting():
    """The PI, 2026-10-12, "Leave drummed repeats out": "Only each trial's first try is judged for
    the criterion. The repeats are still recorded as what they were." Since 2026-10-18 the training
    setting "first answers only", for a percentage rule. Judging the repeats let an animal that
    always picks one side meet 60% over 30 at 50% true accuracy (the science review's D2):
    lose-shift solves a correction trial."""
    scheduler = Scheduler(
        [Block(name="b", conditions=[Condition("a", {}, target=100)], criterion=(0.5, 2),
               drum=True)], seed=1, first_answers=True)
    for outcome in (Outcome.WRONG_TARGET, Outcome.CORRECT):
        scheduler.record(scheduler.next_trial().name, outcome)

    assert scheduler.drawn.drummed and list(scheduler._window) == [0], "one first answer, not two"
    scheduler.record(scheduler.next_trial().name, Outcome.CORRECT)
    assert list(scheduler._window) == [0, 1], "two first answers, half of them right"


def _chain(*outcomes) -> list:
    """The criterion window after one drummed trial's tries, each of `outcomes` in turn, under the
    training setting "first answers only"."""
    scheduler = Scheduler(
        [Block(name="b", conditions=[Condition("a", {}, target=100)], criterion=(0.9, 5),
               drum=True)], seed=1, first_answers=True)
    for outcome in outcomes:
        scheduler.record(scheduler.next_trial().name, outcome)
    return list(scheduler._window)


def test_a_drummed_trials_first_answer_is_judged_when_its_first_try_ended_before_one():
    """The PI, 2026-10-18, "Judge its first answer": "If the first try ends before any answer, the
    first try that does answer is judged. Repeats after a wrong answer stay out." Leaving it out
    left the harder trials of an animal that breaks when unsure out of its criterion. It holds under
    the training setting "first answers only" (the PI, 2026-10-18), as does a repeat's break after
    the wrong answer: still out."""
    assert _chain(Outcome.FIXATION_BREAK, Outcome.CORRECT) == [1]
    assert _chain(Outcome.FIXATION_BREAK, Outcome.WRONG_TARGET, Outcome.CORRECT) == [0]
    assert _chain(Outcome.WRONG_TARGET, Outcome.CORRECT) == [0]
    assert _chain(Outcome.WRONG_TARGET, Outcome.FIXATION_BREAK, Outcome.CORRECT) == [0]
    assert _chain(Outcome.CORRECT, Outcome.FIXATION_BREAK, Outcome.CORRECT) == [1, 1], "two trials"


def test_every_answer_is_judged_under_until_n_correct_too():
    """The PI, 2026-10-18, "Yes, every answer counts in the 20" (settling XC-367): a wrong answer
    under "until N correct" pays nothing, and is judged, so a percentage is not met by any run of
    right answers."""
    block = Block(name="b", conditions=[Condition("a", {}, target=100)], criterion=(0.8, 5),
                  counting=CORRECT_ONLY)
    scheduler = Scheduler([block], seed=1)
    for outcome in (Outcome.WRONG_TARGET, Outcome.WRONG_TARGET, Outcome.CORRECT, Outcome.CORRECT,
                    Outcome.CORRECT):
        scheduler.record(scheduler.next_trial().name, outcome)

    assert list(scheduler._window) == [0, 0, 1, 1, 1]


@pytest.mark.parametrize("first_answers", [False, True])
def test_a_streak_under_drumming_judges_every_answer_in_order(first_answers):
    """The PI, 2026-10-18, "Every answer counts in order": "the wrong answer breaks the streak (back
    to 0), and the drummed correct starts it again at 1. A streak can only be built from correct
    answers in a row, whichever try they came on." A streak is a rule of proportion 1.0, "N correct
    in a row", whatever the training setting says of a percentage."""
    block = Block(name="b", conditions=[Condition("a", {}, target=100)], criterion=(1.0, 3),
                  drum=True)
    scheduler = Scheduler([block], seed=1, first_answers=first_answers)
    for outcome in (Outcome.CORRECT, Outcome.WRONG_TARGET, Outcome.CORRECT, Outcome.CORRECT):
        scheduler.record(scheduler.next_trial().name, outcome)

    assert list(scheduler._window) == [0, 1, 1]
    assert scheduler.streak


@pytest.mark.parametrize(("first_answers", "judged"), [(False, [0, 1, 0, 1]), (True, [0, 0])])
def test_a_percentage_under_drumming_judges_every_answer_unless_set_to_first_answers(
        first_answers, judged):
    """The PI, 2026-10-18: by default a percentage rule counts every answer in order, drummed tries
    included ("Every answer"); the training setting "first answers only" judges each trial's first
    answer, and a trial whose first try had no answer is judged by its first answer ("Judge its
    first answer")."""
    block = Block(name="b", conditions=[Condition("a", {}, target=100)], criterion=(0.5, 10),
                  drum=True)
    scheduler = Scheduler([block], seed=1, first_answers=first_answers)
    for outcome in (Outcome.WRONG_TARGET, Outcome.CORRECT, Outcome.FIXATION_BREAK,
                    Outcome.WRONG_TARGET, Outcome.CORRECT):
        scheduler.record(scheduler.next_trial().name, outcome)

    assert list(scheduler._window) == judged
    assert not scheduler.streak


def test_a_hold_training_block_judges_a_broken_hold_it_scores_as_a_miss():
    """The PI, 2026-10-18, "Yes, where the block says so": "Only where a block itself declares a
    broken hold as a scored trial (a hold-training block) does it count as a miss toward the
    percentage. Everywhere else, breaks stay out, as you decided." Judged on answers alone, "80%
    held over the last 10" was met by any 10 holds with the animal breaking 9 times in 10 (the
    revision's engineering review, I2). The same breaks under the structure's table stay out, even
    where the structure's own table would score them (the block's table is the one read), and a
    rig failure never counts against the animal, whatever the block's table pays it (decision 19:
    "Lost tracking and rig faults never count against the animal")."""
    def drill(block_table) -> Scheduler:
        block = Block(name="hold", conditions=[Condition("a", {}, target=1000)],
                      criterion=(0.8, 10), counting=block_table)
        return Scheduler([block], seed=1,
                         counting=Counting(after_stimulus=OWED,
                                           outcomes={"fixation_break": COUNTED}))

    scored = drill(Counting(after_stimulus=OWED, outcomes={
        "fixation_break": COUNTED, "fault": COUNTED, "tracker_lost": COUNTED}))
    plain = drill(None)
    for n in range(100):
        outcome = Outcome.CORRECT if n % 10 == 0 else Outcome.FIXATION_BREAK
        for scheduler in (scored, plain):
            scheduler.record(scheduler.next_trial().name, outcome)

    assert list(scored._window) == [1] + [0] * 9 and not scored.finished
    assert list(plain._window) == [1] * 10
    # A scored break is a miss in the condition's own counts too, not only in the window.
    assert [(r.right, r.wrong) for r in scored.block_report] == [(10, 90)]
    assert [(r.right, r.wrong) for r in plain.block_report] == [(10, 0)]

    for outcome in (Outcome.FAULT, Outcome.TRACKER_LOST):
        before = list(scored._window)
        scored.record(scored.next_trial().name, outcome)
        assert list(scored._window) == before


def test_an_ordinary_repeat_is_a_trial_of_its_own_in_the_conditions_counts():
    """Appendix B 19: "an ordinary repeat -- a break shown again a few trials later -- is a trial of
    its own", counted with the trials and not with the one it repeats: a break, then its repeat
    right, are two trials of which one was right first time."""
    scheduler = Scheduler([Block(name="b", conditions=[Condition("a", {}, target=1)])], seed=1)
    scheduler.record(scheduler.next_trial().name, Outcome.FIXATION_BREAK)
    scheduler.record(scheduler.next_trial().name, Outcome.CORRECT)

    (report,) = scheduler.block_report
    assert scheduler.drawn.repeat_of is not None
    assert (report.trials, report.right_first) == (2, 1)


def test_a_block_that_trains_acquiring_fixation_judges_a_failure_to_acquire_it_scores_as_a_miss():
    """The PI, 2026-10-18, decision 19, "Yes, where the block says so": a block training looking at
    the fixation point at all counts a failure to acquire it as a miss, a trial that timed out
    waiting at the longest trial included (`task.HANG_COUNTS_AS`, which counts as no fixation).
    A default table leaves both out."""
    def drill(block_table) -> Scheduler:
        block = Block(name="look", conditions=[Condition("a", {}, target=1000)],
                      criterion=(0.8, 10), counting=block_table)
        return Scheduler([block], seed=1)

    scored = drill(Counting(after_stimulus=OWED, outcomes={"no_fixation": COUNTED}))
    plain = drill(None)
    for scheduler in (scored, plain):
        scheduler.record(scheduler.next_trial().name, Outcome.NO_FIXATION)
        scheduler.record(scheduler.next_trial().name, None)

    assert list(scored._window) == [0, 0]
    assert list(plain._window) == []


def test_a_blocks_own_table_cannot_make_no_response_an_answer():
    """The controller's ruling M8 on the plan's revision review: what is an answer is the
    structure's, as `_answer` reads it. A block's table saying it withholds, over a structure that
    does not, made no response a miss, counted; it is classed as that table classes any other
    break after the stimulus, and no rule judges it."""
    block = Block(name="b", conditions=[Condition("a", {}, target=3)], criterion=(1.0, 2),
                  counting=Counting(after_stimulus=SPENT, withholding=True))
    scheduler = Scheduler([block], seed=1, counting=Counting(after_stimulus=OWED))

    assert scheduler.record(scheduler.next_trial().name, Outcome.NO_RESPONSE) == SPENT
    assert list(scheduler._window) == []


def test_a_block_left_with_a_drum_waiting_opens_the_next_with_its_own_condition():
    """A drum waiting when its block is left -- `advance` asks nothing of the block it leaves -- is
    not the next block's: its condition is not the next block's, and `next_trial` raised
    `StopIteration`. Since the PI's "Finish the drum first" (2026-10-18) no end rule leaves a block
    so -- a criterion met on a wrong answer waits for its drum -- so this leaves one on purpose,
    and guards `advance`."""
    blocks = [Block(name="A", conditions=[Condition("a", {}, target=1)], criterion=(0.5, 2),
                    drum=True),
              Block(name="B", conditions=[Condition("b", {}, target=2)])]
    scheduler = Scheduler(blocks, seed=1)
    for outcome in (Outcome.CORRECT, Outcome.WRONG_TARGET):
        scheduler.record(scheduler.next_trial().name, outcome)
    assert not scheduler.finished and scheduler.drum_tries == 1, "the drum holds the block open"

    scheduler.advance()

    assert scheduler.next_trial().name == "b" and not scheduler.drawn.drummed


def test_a_criterion_block_ends_only_once_its_criterion_is_met_and_every_target_is_used_up():
    """The PI, 2026-10-18, "Both: criterion and every target": "The block ends only once the
    criterion is met and every target is used up". Two right answers meet 100% over two, and the
    block, owing four trials, goes on until it owes none; its criterion alone ended it."""
    block = Block(name="b", conditions=[Condition("a", {}, target=3), Condition("b", {}, target=1)],
                  criterion=(1.0, 2))
    scheduler = Scheduler([block], seed=1)
    for _ in range(2):
        scheduler.record(scheduler.next_trial().name, Outcome.CORRECT)

    assert list(scheduler._window) == [1, 1] and not scheduler.finished
    for _ in range(2):
        scheduler.record(scheduler.next_trial().name, Outcome.CORRECT)
    assert scheduler.finished and [scheduler.owed(n) for n in "ab"] == [0, 0]


def test_past_its_targets_a_criterion_block_draws_every_condition_until_the_criterion_is_met():
    """The PI, 2026-10-18 (settling XC-364): "conditions keep coming until both hold". Every target
    used up with the criterion unmet, the block draws all its conditions again, by its order, each
    answer counted as ever and nothing owed -- where it had nothing left to draw and the run
    faulted. A block without a criterion still draws nothing once its targets are used up."""
    block = Block(name="b", conditions=[Condition(n, {}, target=1) for n in "ab"],
                  criterion=(1.0, 3))
    scheduler = Scheduler([block], seed=1)
    kinds, drawn = [], []
    for outcome in (Outcome.CORRECT, Outcome.CORRECT, Outcome.WRONG_TARGET, Outcome.CORRECT,
                    Outcome.CORRECT, Outcome.CORRECT):
        assert not scheduler.finished
        drawn.append(scheduler.next_trial().name)
        kinds.append(scheduler.record(drawn[-1], outcome))

    assert scheduler.finished and set(drawn[2:]) == {"a", "b"}
    assert kinds == [COUNTED] * 6 and [scheduler.owed(n) for n in "ab"] == [0, 0]
    fixed = Scheduler([Block(name="b", conditions=[Condition(n, {}, target=1) for n in "ab"])],
                      seed=1)
    for _ in range(2):
        fixed.record(fixed.next_trial().name, Outcome.CORRECT)
    with pytest.raises(IndexError, match="no condition left to draw"):
        fixed.next_trial()


def test_a_drummed_criterion_block_goes_on_drumming_past_its_targets():
    """Drumming acted only while a condition owed, so past its targets a training block -- a streak,
    drummed -- stopped drumming: a wrong answer there comes back at once until it is right, as it
    did before the target was used up."""
    block = Block(name="b", conditions=[Condition("a", {}, target=1)], criterion=(1.0, 2),
                  drum=True)
    scheduler = Scheduler([block], seed=1)
    drummed = []
    for outcome in (Outcome.CORRECT, Outcome.WRONG_TARGET, Outcome.CORRECT, Outcome.CORRECT):
        scheduler.record(scheduler.next_trial().name, outcome)
        drummed.append(scheduler.drawn.drummed)

    assert drummed == [False, False, True, False] and scheduler.finished


@pytest.mark.parametrize(("drummed", "finished"), [
    ((Outcome.CORRECT,), True),
    ((Outcome.WRONG_TARGET, Outcome.CORRECT), False),
])
def test_a_drummed_block_met_on_a_wrong_answer_finishes_its_drum_first(drummed, finished):
    """The PI, 2026-10-18, "Finish the drum first": "The block ends only after the drummed trial is
    answered right. If the extra tries drop the percentage below the bar, the block carries on.
    Training ends on a success." Four right answers then a wrong one make 80% of the last 5, and
    the block waits for its drum: right at once, it ends there; wrong again, the percentage falls
    below the bar, and the block carries on once the drum is right."""
    block = Block(name="b", conditions=[Condition("a", {}, target=1)], criterion=(0.8, 5),
                  drum=True)
    scheduler = Scheduler([block], seed=1)
    for outcome in (Outcome.CORRECT,) * 4 + (Outcome.WRONG_TARGET,):
        scheduler.record(scheduler.next_trial().name, outcome)
    assert list(scheduler._window) == [1, 1, 1, 1, 0] and scheduler.drum_tries == 1
    assert not scheduler.finished, "met, but a drum is waiting"

    for outcome in drummed:
        scheduler.record(scheduler.next_trial().name, outcome)

    assert scheduler.drum_tries == 0 and scheduler.finished is finished


def test_stopping_a_drum_that_holds_a_met_block_open_is_this_blocks_switch():
    """*Stop drumming* while a drum holds open a block whose criterion is met ends the drum, and the
    block with it; the switch is this block's, so the next block's own drumming is not switched
    off. Asked after *off* had dropped the drum, the carry called it the next block's (reachable
    since the PI's "Finish the drum first", 2026-10-18)."""
    blocks = [Block(name="A", conditions=[Condition("a", {}, target=1)], criterion=(0.5, 2),
                    drum=True),
              Block(name="B", conditions=[Condition("b", {}, target=2)], drum=True)]
    scheduler = Scheduler(blocks, seed=1)
    for outcome in (Outcome.CORRECT, Outcome.WRONG_TARGET):
        scheduler.record(scheduler.next_trial().name, outcome)
    assert not scheduler.finished and scheduler.drum_tries == 1
    assert scheduler.drumming_switched == "block"

    assert scheduler.drum("off") == "A" and scheduler.finished
    scheduler.advance()
    assert (scheduler.block.name, scheduler.drumming) == ("B", "block")


def test_past_targets_agrees_with_what_each_condition_owes_through_a_run_of_mixed_outcomes():
    """`past_targets` is read from the counts directly, not by asking `owed` of each condition; it
    must say what `all(owed == 0)` says after every outcome, forgiving a trial included."""
    block = Block(name="b", conditions=[Condition("a", {}, target=1), Condition("b", {}, target=2),
                                        Condition("c", {}, target=0)], criterion=(1.0, 50))
    scheduler = Scheduler([block], seed=1, clearing=True)
    assert scheduler.clear("b", rest=True) is None
    seen = {scheduler.past_targets}
    outcomes = (Outcome.CORRECT, Outcome.WRONG_TARGET, Outcome.FIXATION_BREAK, Outcome.CORRECT)
    for step in range(12):
        name = scheduler.next_trial().name
        scheduler.record(name, outcomes[step % len(outcomes)])
        past = scheduler.past_targets
        seen.add(past)
        assert past == all(scheduler.owed(c.name) == 0 for c in block.conditions)
    assert seen == {True, False}


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


def test_a_conditions_report_counts_a_drummed_trial_once_and_every_try_as_a_presentation():
    """The PI, 2026-10-18: "A trial and its drummed repeats are one" trial, and per condition the
    console shows "trials and presentations; right, wrong, % right (first time); owed, repeats,
    moved past ...; drummed tries (and the current failed run)". Three trials, two of them drummed
    to the right answer, are five presentations; one was right first time."""
    scheduler = Scheduler([Block(name="b", conditions=[Condition("a", {}, target=3)], drum=True)],
                          seed=1)
    scheduler.record(scheduler.next_trial().name, Outcome.WRONG_TARGET)
    failing = scheduler.block_report[0].failing
    for outcome in (Outcome.CORRECT, Outcome.FIXATION_BREAK, Outcome.CORRECT, Outcome.CORRECT):
        scheduler.record(scheduler.next_trial().name, outcome)

    assert failing == 1 and scheduler.trials == 3
    assert scheduler.block_report == (
        ConditionReport("b", "a", trials=3, presentations=5, right=3, wrong=1, right_first=1,
                        owed=0, repeats=0, moved_past=0, possible_avoidance=False, drummed=2,
                        failing=0),)


def test_the_report_keeps_every_blocks_counts_and_flags_a_condition_its_limit_moved_past():
    """The PI, 2026-10-18: each condition's counts are "written into the run's end record as well",
    every block's -- the scheduler kept a block's counts only until it advanced -- with the
    possible-avoidance flag where a repeat limit moved the condition past."""
    blocks = [Block(name="A", conditions=[Condition("a", {}, target=2)],
                    counting=Counting(after_stimulus=OWED, cap=0)),
              Block(name="B", conditions=[Condition("b", {}, target=1)])]
    scheduler = Scheduler(blocks, seed=1)
    scheduler.record(scheduler.next_trial().name, Outcome.FIXATION_BREAK)
    assert scheduler.finished

    scheduler.advance()
    scheduler.record(scheduler.next_trial().name, Outcome.CORRECT)

    assert [(r.block, r.condition, r.trials, r.moved_past, r.possible_avoidance, r.right)
            for r in scheduler.report] == [("A", "a", 1, 2, True, 0), ("B", "b", 1, 0, False, 1)]


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


# --- Plans: how blocks follow one another, and how each ends (engine build C2b) ---------------


def _one(name: str, target: int = 1, **block) -> Block:
    return Block(name=name, conditions=[Condition(name.lower(), {}, target=target)], **block)


def _run_out(scheduler: Scheduler, limit: int = 60) -> list[str]:
    """The block names a scheduler visits, every trial correct, until its plan is done."""
    seen = [scheduler.block.name]
    for _ in range(limit):
        if scheduler.done:
            return seen
        if scheduler.ends is not None:
            seen.append(scheduler.advance(scheduler.ends).name)
            continue
        scheduler.record(scheduler.next_trial().name, Outcome.CORRECT)
    raise AssertionError(f"not done after {limit} steps: {seen}")


def test_a_cyclic_plan_repeats_its_blocks_in_order_its_cycles_times():
    """The PI, 2026-10-07: "repeating (Bt1, Bt2, Bt1, Bt2...)". A cyclic plan of no count is never
    done by its blocks; a time limit, a stop or the out-of-cage limit ends its run."""
    blocks = [_one("A"), _one("B")]

    assert _run_out(Scheduler(blocks, seed=1, order=Cyclic(cycles=2))) == ["A", "B", "A", "B"]
    endless = Scheduler(blocks, seed=1, order=Cyclic())
    for _ in range(9):
        endless.record(endless.next_trial().name, Outcome.CORRECT)
        assert not endless.done
        endless.advance(endless.ends)
    assert endless.block.name == "B"


def test_a_balanced_plan_shows_every_block_type_once_a_round_in_an_order_drawn_from_the_seed():
    """The PI, 2026-10-19, "Shuffled rounds": each round shows every block type once, in a seeded
    random order; a count that is not whole rounds leaves the last round partial, the seed choosing
    its types; the same seed replays the same order, and another seed can draw another."""
    blocks = [_one("A"), _one("B"), _one("C")]

    def order(seed: int, count: int = 7) -> list[str]:
        return _run_out(Scheduler(blocks, seed=seed, order=Balanced(blocks=count)))

    first = order(1)
    assert len(first) == 7
    assert sorted(first[0:3]) == sorted(first[3:6]) == ["A", "B", "C"]
    assert first == order(1)
    assert len({tuple(order(seed)) for seed in range(8)}) > 1


def test_a_random_plan_draws_each_block_type_from_the_seed_and_may_repeat_one():
    """The PI, 2026-10-19, "Both, as two choices": "random can repeat a type and leave another out
    by chance, recorded with its seed": each block's type drawn on its own, replayed by the seed."""
    blocks = [_one("A"), _one("B")]
    orders = [tuple(_run_out(Scheduler(blocks, seed=seed, order=Random(blocks=6))))
              for seed in range(12)]

    assert all(len(order) == 6 for order in orders)
    assert any(order[i] == order[i + 1] for order in orders for i in range(5))
    assert orders[3] == tuple(_run_out(Scheduler(blocks, seed=3, order=Random(blocks=6))))


def test_a_random_block_order_leaves_every_conditions_draw_as_the_seed_gives_it():
    """A random block order draws from a generator of its own (`seed` again, apart), so the
    conditions a block draws are the ones a fixed plan's same block draws from the same seed."""
    block = Block(name="A", conditions=[Condition(c, {}, target=3) for c in "xyz"])

    def draws(**order) -> list[str]:
        scheduler = Scheduler([block], seed=5, **order)
        names = []
        for _ in range(9):
            names.append(scheduler.next_trial().name)
            scheduler.record(names[-1], Outcome.CORRECT)
        return names

    assert draws() == draws(order=Random(blocks=1))


def _stages(fall_back=(0.5, 4)) -> Scheduler:
    """A training progression of three stages, each "3 right in a row" over one condition."""
    blocks = [_one(name, target=1, criterion=(1.0, 3)) for name in ("S1", "S2", "S3")]
    return Scheduler(blocks, seed=1, order=ByCriterion(fall_back=fall_back))


def _answer(scheduler: Scheduler, *outcomes: Outcome) -> None:
    for outcome in outcomes:
        scheduler.record(scheduler.next_trial().name, outcome)


def test_a_training_progression_moves_up_on_a_stages_rule_and_back_one_on_its_fall_back():
    """The PI, 2026-10-19, "Same, but top keeps going": move up when the stage's own rule is met;
    move back one stage, started fresh, when the plan's second rule is met -- "under 50% over the
    last 20" -- judged once that many answers are in, answers only."""
    scheduler = _stages()
    _answer(scheduler, Outcome.CORRECT, Outcome.CORRECT, Outcome.CORRECT)
    assert scheduler.ends == RULE
    assert scheduler.advance(scheduler.ends).name == "S2"

    _answer(scheduler, Outcome.WRONG_TARGET, Outcome.FIXATION_BREAK, Outcome.WRONG_TARGET,
            Outcome.CORRECT)
    assert scheduler.ends is None, "three answers are not yet the window's four"
    _answer(scheduler, Outcome.WRONG_TARGET)
    assert scheduler.ends == FALL_BACK
    assert scheduler.advance(scheduler.ends).name == "S1"
    assert scheduler.counts("s1").trials == 0, "started fresh"
    assert scheduler.fell_back == 1, "counted, for the console's plan row"
    assert [(end.block, end.ended) for end in scheduler.ended] == [("S1", RULE), ("S2", FALL_BACK)]


def test_the_first_stage_has_no_stage_to_fall_back_to():
    scheduler = _stages()
    _answer(scheduler, *[Outcome.WRONG_TARGET] * 6)

    assert scheduler.ends is None


def test_at_the_top_stage_the_animal_keeps_working_once_its_rule_is_met():
    """The PI, 2026-10-19: "at the top stage the animal keeps working there until a time limit, a
    stop or the end of the session": its rule met, it does not end, and its conditions keep coming;
    its own time limit ends the run, with nowhere to move on to."""
    scheduler = _stages(fall_back=None)
    for _ in range(2):
        _answer(scheduler, Outcome.CORRECT, Outcome.CORRECT, Outcome.CORRECT)
        scheduler.advance(scheduler.ends)
    _answer(scheduler, *[Outcome.CORRECT] * 5)

    assert scheduler.block.name == "S3" and scheduler.finished
    assert scheduler.ends is None and not scheduler.done and scheduler.past_targets
    scheduler.expire()
    assert scheduler.ends == TIME and scheduler.done


def test_a_met_rule_counts_before_a_fall_back_at_the_top_stage_too():
    """A met rule counts before a fall-back met at the same answer ("training ends on a success";
    Appendix B) -- and at the top stage, which works on once its rule is met, it holds the
    fall-back off for as long as the rule holds, falling back once it does not."""
    blocks = [_one("S1", target=1), _one("S2", target=1, criterion=(1.0, 2))]
    scheduler = Scheduler(blocks, seed=1, order=ByCriterion(fall_back=(0.6, 4)))
    _answer(scheduler, Outcome.CORRECT)
    scheduler.advance(scheduler.ends)
    _answer(scheduler, Outcome.WRONG_TARGET, Outcome.WRONG_TARGET, Outcome.CORRECT,
            Outcome.CORRECT)

    assert scheduler.finished and list(scheduler._back) == [0, 0, 1, 1]
    assert scheduler.ends is None, "two right in a row hold off two of four first answers"
    _answer(scheduler, Outcome.WRONG_TARGET)
    assert scheduler.ends == FALL_BACK


def test_a_stage_whose_time_runs_out_moves_up_whether_or_not_it_passed():
    """The PI, 2026-10-19, "Move on anyway": "Time-boxed stages: go to the next stage whether or not
    the animal passed." What it still owed is recorded as not run, "time ran out"."""
    scheduler = _stages()
    _answer(scheduler, Outcome.FIXATION_BREAK)
    scheduler.expire()

    assert scheduler.ends == TIME
    assert scheduler.advance(scheduler.ends).name == "S2"
    assert scheduler.shortfalls == [Shortfall("S1", "s1", 1, TIME, 0)]
    assert scheduler.ended == [BlockEnd("S1", TIME, None, 0)]


def test_a_blocks_time_waits_for_a_drummed_trial_to_be_right():
    """The PI, 2026-10-19, "Finish the drum first": time running out while a drummed trial is coming
    back ends the block only once that trial is right."""
    scheduler = Scheduler([_one("A", target=5, drum=True), _one("B")], seed=1)
    _answer(scheduler, Outcome.WRONG_TARGET)
    scheduler.expire()

    assert scheduler.ends is None
    _answer(scheduler, Outcome.WRONG_TARGET)
    assert scheduler.ends is None
    _answer(scheduler, Outcome.CORRECT)
    assert scheduler.ends == TIME and not scheduler.done


def test_a_block_with_a_number_of_trials_ends_once_it_has_run_them_drummed_repeats_inside():
    """Engine spec §13.5's "a number of trials" (the PI, 2026-10-07), counted as the PI counts
    trials (2026-10-18: "200 trials; drummed repeats inside them"): a trial and its drummed repeats
    one, an ordinary repeat a trial of its own; the targets are a minimum, and past them every
    condition is drawn by its order."""
    block = Block(name="A", conditions=[Condition("x", {}, target=1), Condition("y", {}, target=1)],
                  trials=4, drum=True)
    scheduler = Scheduler([block], seed=1)
    _answer(scheduler, Outcome.CORRECT, Outcome.WRONG_TARGET, Outcome.CORRECT)

    assert scheduler.block_trials == 2 and scheduler.past_targets and not scheduler.finished
    _answer(scheduler, Outcome.CORRECT)
    assert scheduler.block_trials == 3 and not scheduler.finished
    _answer(scheduler, Outcome.CORRECT)
    assert scheduler.finished and scheduler.ends == RULE and scheduler.done


def test_a_person_moves_a_run_on_a_block_or_back_one_and_it_is_recorded_with_who():
    """The PI, 2026-10-19, "'Next' and 'back one'": both directions by hand, each recorded with
    who; back one starts that block fresh; past the plan's last block, or before its first, nothing
    moves and the sentence says why."""
    scheduler = _stages()
    assert scheduler.move(BACK, by="kim") == (
        "block 'S1' is the first of the run's blocks, so there is no block before it")
    _answer(scheduler, Outcome.CORRECT)

    assert scheduler.move(NEXT, by="kim") is None and scheduler.block.name == "S2"
    assert scheduler.move(NEXT, by="kim") is None and scheduler.block.name == "S3"
    assert scheduler.move(NEXT, by="kim") == (
        "block 'S3' is the last its plan gives, so there is no next block; stop ends the run")
    assert scheduler.move(BACK, by="kim") is None and scheduler.block.name == "S2"
    assert [(end.block, end.ended, end.by) for end in scheduler.ended] == [
        ("S1", NEXT, "kim"), ("S2", NEXT, "kim"), ("S3", BACK, "kim")]


def test_a_drumming_switch_as_a_cyclic_plans_last_block_ends_is_for_the_block_that_follows():
    """`drum`'s carry reads the block the plan's order gives next (`following`), not the next in
    the list: at a cyclic plan's last block that is its first again."""
    scheduler = Scheduler([_one("A", drum=True), _one("B")], seed=1, order=Cyclic())
    scheduler.advance(RULE)
    _answer(scheduler, Outcome.CORRECT)

    assert scheduler.drumming_switched == "block", "A, which follows, drums by its declaration"
    assert scheduler.drum("off") == "A"


def test_a_plan_that_has_opened_every_block_type_since_its_last_trial_has_stalled():
    """The per-advance progress check (engine spec §13.5): a cyclic plan whose every block is over
    before it draws a trial would advance forever; it has stalled once it has opened each type
    since its last trial. A plan with one such type among others that draw has not."""
    empty = [_one("A", target=0), _one("B", target=0)]
    scheduler = Scheduler(empty, seed=1, order=Cyclic())
    assert scheduler.ends == RULE and not scheduler.stalled
    scheduler.advance(scheduler.ends)
    assert scheduler.ends == RULE and scheduler.stalled

    mixed = Scheduler([_one("A", target=0), _one("B")], seed=2, order=Random())
    for _ in range(12):
        if mixed.ends is None:
            break
        assert not mixed.stalled
        mixed.advance(mixed.ends)
    assert mixed.block.name == "B" and mixed.drawable


def test_a_persons_move_starts_the_progress_check_afresh():
    """The engine C2b plan's engineering review, I1 (its fuzz's seed 167): a fixed plan whose first
    block owes nothing and whose second owes three; a person moves back one before the second's
    first trial, and the first ends on its rule again. The plan has opened both types since its
    last trial, but a move is not the plan spinning: it has not stalled, and the second block
    draws."""
    scheduler = Scheduler([_one("A", target=0), _one("B", target=3)], seed=1)
    assert scheduler.ends == RULE and not scheduler.stalled
    scheduler.advance(scheduler.ends)
    assert scheduler.move(BACK, by="kim") is None and scheduler.block.name == "A"

    assert scheduler.ends == RULE and not scheduler.stalled
    assert scheduler.advance(scheduler.ends).name == "B" and scheduler.drawable


def test_a_condition_of_weight_0_is_never_drawn_and_leaves_nothing_to_draw_once_the_rest_are_paid():
    """The engine C2b plan's engineering review, I2: a weighted draw never gives a condition of
    weight 0, and once every other condition is paid there is nothing to draw -- `drawable` says
    so, for the loop to end the run with its sentence (the PI, 2026-10-19, "End run with a
    sentence") -- where `random.choices` raised. The draws before are the ones the seed gives
    with the condition left out."""
    def block(weights) -> Block:
        return Block(name="A", conditions=[Condition(c, {}, target=t) for c, t in
                                           (("a", 2), ("b", 3), ("c", 3))][:len(weights)],
                     order=WithReplacement(weights=weights))

    zero = Scheduler([block({"a": 0.0, "b": 1.0, "c": 2.0})], seed=4)
    drawn = []
    while zero.drawable:
        drawn.append(zero.next_trial().name)
        zero.record(drawn[-1], Outcome.CORRECT)

    assert sorted(drawn) == ["b"] * 3 + ["c"] * 3
    assert zero.owed("a") == 2 and zero.ends is None and not zero.drawable


def _second_stage(drum: bool = True, **stage) -> Scheduler:
    """A training progression at its second stage, drumming unless told not to, under a fall-back
    rule of under half of the last four answers right; the first stage passed on one right
    answer."""
    blocks = [_one("S1", target=1),
              Block(name="S2", conditions=[Condition("s2", {}, target=50)], drum=drum, **stage)]
    scheduler = Scheduler(blocks, seed=1, order=ByCriterion(fall_back=(0.5, 4)))
    _answer(scheduler, Outcome.CORRECT)
    scheduler.advance(scheduler.ends)
    return scheduler


@pytest.mark.parametrize("criterion", [(1.0, 3), (0.8, 5), None])
@pytest.mark.parametrize("first_answers", [False, True])
def test_moving_back_judges_each_trials_first_answer_only_whatever_the_stage_counts(
        criterion, first_answers):
    """The PI, 2026-10-19, "First answer only": "Only each trial's first answer counts toward moving
    back, so one stubborn trial can't demote a stage the animal is otherwise doing well in" --
    under a streak, a percentage or no rule, with the training setting "first answers only" on or
    off (the science review, C1: the window sat in the stage rule's branch). Right first time
    twice, then one trial right only at its fourth try, then one at its second: four first answers,
    half right, not under half; one more wrong first answer and the stage falls back, once its
    drummed trial is right."""
    scheduler = _second_stage(criterion=criterion)
    scheduler.first_answers = first_answers
    _answer(scheduler, Outcome.CORRECT, Outcome.CORRECT)
    _answer(scheduler, Outcome.WRONG_TARGET, Outcome.WRONG_TARGET, Outcome.WRONG_TARGET,
            Outcome.CORRECT)
    assert scheduler.ends is None, "three first answers, two right: not judged yet"
    _answer(scheduler, Outcome.WRONG_TARGET, Outcome.CORRECT)
    assert scheduler.ends is None, "four first answers, half right: not under half"

    _answer(scheduler, Outcome.WRONG_TARGET)
    assert scheduler.ends is None, "its drummed trial comes back first"
    _answer(scheduler, Outcome.CORRECT)
    assert scheduler.ends == FALL_BACK
    assert scheduler.because(FALL_BACK) == (
        "fell back: 1 of its last 4 first answers right, under 50%")


def test_a_broken_hold_a_stage_scores_counts_toward_moving_back_as_toward_moving_up():
    """The PI, 2026-10-19, "Yes, the same": "A hold-training stage judges holds both ways: broken
    holds count toward moving up and toward moving back." A break the stage's own table does not
    score counts toward neither."""
    scored = _second_stage(drum=False, counting=Counting(
        after_stimulus=OWED, outcomes={"fixation_break": COUNTED}))
    plain = _second_stage(drum=False)
    for scheduler in (scored, plain):
        _answer(scheduler, Outcome.CORRECT, *[Outcome.FIXATION_BREAK] * 3)

    assert list(scored._back) == [1, 0, 0, 0] and scored.ends == FALL_BACK
    assert list(plain._back) == [1] and plain.ends is None


def test_a_balanced_plans_rounds_never_put_one_block_type_back_to_back():
    """The PI, 2026-10-19, "Never back-to-back": "Each new round starts with a different type than
    the last one played, so every block boundary is a real switch; still balanced in counts." Over
    many seeds and two to five types, no two blocks in a row share a type, and each whole round
    still shows every type once."""
    for n in range(2, 6):
        blocks = [_one(f"T{i}") for i in range(n)]
        for seed in range(40):
            order = _run_out(Scheduler(blocks, seed=seed, order=Balanced(blocks=4 * n + 1)),
                             limit=400)
            assert all(a != b for a, b in zip(order, order[1:])), (n, seed, order)
            rounds = [sorted(order[i:i + n]) for i in range(0, 4 * n, n)]
            assert rounds == [sorted(b.name for b in blocks)] * 4, (n, seed)


def test_each_block_end_records_its_place_its_number_in_the_stream_and_when_a_top_stage_passed():
    """The engineering review, I4: each `BlockEnd` names its place in the run's sequence and the
    number the loop gave it as its first trial opened it in the stream, `None` for a block that
    ran no trial. The science review, I1: a top stage's end says after which trial its rule was
    first met, its animal working on past it."""
    scheduler = _stages(fall_back=None)
    scheduler.in_session = 7
    _answer(scheduler, Outcome.CORRECT, Outcome.CORRECT, Outcome.CORRECT)
    scheduler.advance(scheduler.ends)
    assert scheduler.move(NEXT, by="kim") is None
    scheduler.in_session = 9
    _answer(scheduler, Outcome.CORRECT, Outcome.WRONG_TARGET, *[Outcome.CORRECT] * 3)
    assert scheduler.passed_at is None, "not yet asked at a boundary"
    assert scheduler.ends is None and scheduler.passed_at == 7
    _answer(scheduler, Outcome.CORRECT, Outcome.WRONG_TARGET)
    scheduler.expire()
    assert scheduler.ends == TIME and scheduler.passed_at == 7
    scheduler.close(scheduler.ends)

    assert scheduler.ended == [BlockEnd("S1", RULE, None, 2, 0, 7, None),
                               BlockEnd("S2", NEXT, "kim", 2, 1, None, None),
                               BlockEnd("S3", TIME, None, 9, 2, 9, 7)]


def test_the_runs_time_closes_its_open_block_as_the_runs_recording_what_it_owed_so():
    """The science review, I3: the run's own time limit ending the run with a block open is
    recorded apart from the block's own time -- `RUN_TIME` -- and what the block still owed is
    recorded as not run for it, forgiving nothing."""
    scheduler = Scheduler([_one("A", target=3)], seed=1)
    _answer(scheduler, Outcome.CORRECT)
    scheduler.close(RUN_TIME)

    assert scheduler.shortfalls == [Shortfall("A", "a", 2, RUN_TIME, 0)]
    assert scheduler.ended == [BlockEnd("A", RUN_TIME, None, 0)]
    assert scheduler.owed("a") == 2


def test_each_block_end_is_said_with_its_numbers():
    """The science review, I2: one line on the changes feed per block end, with its reason and
    numbers -- "S2 -> S1: 8 of last 20 right"."""
    streak = _stages()
    _answer(streak, Outcome.CORRECT, Outcome.CORRECT, Outcome.CORRECT)
    percentage = Scheduler([_one("A", target=1, criterion=(0.8, 5), trials=6)], seed=1)
    _answer(percentage, Outcome.CORRECT, Outcome.WRONG_TARGET, *[Outcome.CORRECT] * 4)
    timed = Scheduler([_one("A", target=4)], seed=1)
    timed.expire()

    assert streak.because(RULE) == "its rule met: 3 right in a row, every target used up"
    assert percentage.because(RULE) == (
        "its rule met: 4 of its last 5 answers right, 6 trials run, every target used up")
    assert timed.because(TIME) == "its time ran out, its rule not met"
    assert timed.because(RUN_TIME) == "the run's time ran out"


def _fuzzed(seed: int) -> Scheduler:
    """A random plan: one to four block types of one to three conditions, targets 0 to 3, each
    perhaps a criterion, a number of trials, drumming and a condition order; and a random block
    order of each kind, the counted ones counted."""
    rng = random.Random(seed)
    blocks = []
    for b in range(rng.randint(1, 4)):
        order = rng.choice([Shuffled(), WithReplacement(weights={"c0": 2.0}),
                            Constrained(max_run=rng.randint(1, 2))])
        blocks.append(Block(
            name=f"B{b}",
            conditions=[Condition(f"c{c}", {}, target=rng.randint(0, 3))
                        for c in range(rng.randint(1, 3))],
            criterion=rng.choice([None, (rng.choice([0.5, 0.8, 1.0]), rng.randint(1, 4))]),
            trials=rng.choice([None, rng.randint(1, 6)]),
            drum=rng.random() < 0.3,
            order=order,
        ))
    order = rng.choice([Cyclic(cycles=rng.randint(1, 3)), Balanced(blocks=rng.randint(1, 6)),
                        Random(blocks=rng.randint(1, 6)),
                        ByCriterion(fall_back=rng.choice([None, (0.5, rng.randint(1, 4))]))])
    return Scheduler(blocks, seed=seed, counting=Counting(after_stimulus=OWED, cap=2),
                     order=order)


@pytest.mark.parametrize("seed", range(0, 400, 40))
def test_no_random_plan_draws_from_nowhere_ends_a_block_on_a_drum_or_moves_a_stage_by_two(seed):
    """Engine build C2b's plans fuzzed, forty plans a case: whatever a plan's orders and end rules,
    a block that does not end can always draw (its targets, a repeat, a drum, or past its targets
    every condition); no block ends while a drum waits ("Finish the drum first"); a training
    progression moves one stage at a time; and every plan is done, stalls, or -- a progression's
    top stage working on -- runs until it is stopped."""
    for case in range(seed, seed + 40):
        scheduler = _fuzzed(case)
        rng = random.Random(case)
        for _ in range(800):
            if scheduler.done:
                break
            ending = scheduler.ends
            if ending is not None:
                assert scheduler._drum is None, case
                if scheduler.stalled:
                    assert all(
                        b.criterion is None and b.trials is None
                        and all(c.target == 0 for c in b.conditions) for b in scheduler.blocks
                    ), f"a false stall, case {case}"
                    break
                was = scheduler._position
                scheduler.advance(ending)
                if isinstance(scheduler.order, ByCriterion):
                    assert abs(scheduler._position - was) == 1, case
                continue
            assert scheduler.drawable, case
            if isinstance(scheduler.order, Balanced) and len(scheduler.blocks) > 1:
                sequence = scheduler._sequence
                assert all(a != b for a, b in zip(sequence, sequence[1:])), case
            name = scheduler.next_trial().name
            assert name in {c.name for c in scheduler.block.conditions}, case
            scheduler.record(name, rng.choice([Outcome.CORRECT, Outcome.CORRECT,
                                               Outcome.WRONG_TARGET, Outcome.FIXATION_BREAK]))
            if rng.random() < 0.02:
                scheduler.expire()
        else:
            assert isinstance(scheduler.order, ByCriterion), case


def test_a_timed_stages_fall_back_met_as_its_time_runs_out_moves_back():
    """A fall-back is judged before a stage's time: S2 with four wrong first answers, its time
    run out, falls back to S1 rather than moving on."""
    scheduler = _stages()
    _answer(scheduler, Outcome.CORRECT, Outcome.CORRECT, Outcome.CORRECT)
    scheduler.advance(scheduler.ends)
    _answer(scheduler, *[Outcome.WRONG_TARGET] * 4)
    scheduler.expire()

    assert scheduler.ends == FALL_BACK
    assert scheduler.advance(scheduler.ends).name == "S1"


def test_a_stage_moved_on_by_its_time_starts_its_own_clock():
    scheduler = _stages()
    _answer(scheduler, Outcome.FIXATION_BREAK)
    scheduler.expire()
    assert scheduler.expired
    scheduler.advance(scheduler.ends)

    assert scheduler.ends is None and not scheduler.expired


def test_a_plan_whose_block_drew_since_it_opened_every_type_has_not_stalled():
    scheduler = Scheduler([_one("A", target=0), _one("B")], seed=1, order=Cyclic())
    scheduler.advance(scheduler.ends)
    _answer(scheduler, Outcome.CORRECT)
    assert scheduler.ends == RULE and not scheduler.stalled
    scheduler.advance(scheduler.ends)

    assert scheduler.ends == RULE and not scheduler.stalled


def test_a_balanced_order_leaves_every_conditions_draw_as_the_seed_gives_it():
    blocks = [Block(name=n, conditions=[Condition(c, {}, target=3) for c in "xyz"]) for n in "AB"]

    def draws(**order) -> list[str]:
        scheduler = Scheduler(blocks, seed=5, **order)
        names = []
        for _ in range(9):
            names.append(scheduler.next_trial().name)
            scheduler.record(names[-1], Outcome.CORRECT)
        return names

    assert draws() == draws(order=Balanced(blocks=1))


def test_a_stage_below_the_top_records_no_pass_after_a_fall_back_from_it():
    blocks = [_one("S1"), _one("S2", criterion=(1.0, 2))]
    scheduler = Scheduler(blocks, seed=1, order=ByCriterion(fall_back=(0.6, 4)))
    _answer(scheduler, Outcome.CORRECT)
    scheduler.advance(scheduler.ends)
    _answer(scheduler, Outcome.WRONG_TARGET, Outcome.WRONG_TARGET, Outcome.CORRECT,
            Outcome.CORRECT)
    assert scheduler.ends is None and scheduler.passed_at is not None
    _answer(scheduler, Outcome.WRONG_TARGET)
    scheduler.advance(scheduler.ends)

    assert scheduler.passed_at is None


def test_next_block_names_the_block_the_plan_goes_on_to_and_none_at_its_end():
    scheduler = _stages()
    assert scheduler.next_block.name == "S2"
    _answer(scheduler, Outcome.CORRECT, Outcome.CORRECT, Outcome.CORRECT)
    scheduler.advance(scheduler.ends)
    scheduler.advance(RULE)
    assert scheduler.block.name == "S3" and scheduler.next_block is None
    cyclic = Scheduler([_one("A"), _one("B")], seed=1, order=Cyclic(cycles=1))
    assert cyclic.next_block.name == "B"
    cyclic.advance(RULE)
    assert cyclic.next_block is None


def test_expired_is_false_until_expire_and_false_again_after_the_block_moves_on():
    scheduler = Scheduler([_one("A"), _one("B")], seed=1)
    assert scheduler.expired is False
    scheduler.expire()
    assert scheduler.expired is True
    scheduler.advance(TIME)
    assert scheduler.expired is False


def test_drum_waiting_names_the_condition_whose_drummed_trial_waits_until_it_is_right():
    scheduler = Scheduler([_one("A", target=3, drum=True)], seed=1)
    assert scheduler.drum_waiting is None
    _answer(scheduler, Outcome.WRONG_TARGET)
    assert scheduler.drum_waiting == "a"
    _answer(scheduler, Outcome.CORRECT)
    assert scheduler.drum_waiting is None


def test_a_block_end_is_recorded_once_whoever_closes_it_again():
    scheduler = Scheduler([_one("A", target=3)], seed=1)
    scheduler.close(TIME)
    scheduler.close(RUN_TIME)

    assert scheduler.ended == [BlockEnd("A", TIME, None, None)]
    assert [s.because for s in scheduler.shortfalls] == [TIME]


def test_a_persons_clear_starts_the_progress_check_afresh():
    """A Cyclic plan, A owing nothing and B owing two: B cleared to nothing before its first trial
    ends on its rule, but that is a person's doing, not the plan spinning, so it has not stalled."""
    scheduler = Scheduler([_one("A", target=0), _one("B", target=2)], seed=1, order=Cyclic())
    scheduler.clearing = True
    scheduler.advance(scheduler.ends)
    assert scheduler.clear("b", by="kim", rest=True) is None

    assert scheduler.ends == RULE and not scheduler.stalled
    # And the move on from it: A owes nothing and ends at once, but the plan can still draw (B).
    scheduler.advance(scheduler.ends)
    assert scheduler.ends == RULE and not scheduler.stalled


@pytest.mark.parametrize("order", [Fixed(), Cyclic(), Balanced(), Random(), ByCriterion()])
def test_a_plan_with_no_blocks_is_refused_plainly_whatever_its_order(order):
    with pytest.raises(IndexError, match="no block to start"):
        Scheduler([], seed=1, order=order)
