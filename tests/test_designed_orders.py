"""Engine build C3's designed orders and eased trials, as the scheduler plays them (the PI,
2026-10-30: Q5a, "Block picks; pairs default"; Q5b, "'Again at once' as an option"; Q6, "Both of
the last two"; Q8, "Merge; fix eased trials in C3"; the C3 spec §5 and §7).

A sequence-balanced block plays a de Bruijn cycle of its conditions, drawn as it opens; a priming
block repeats its feature's value or switches it, by a chance or in runs of drawn length; a break
in either is not shown again unless it comes back at once, under the repeat limit; and a trial a
live change eased never counts toward moving up and always toward moving back. The trial loop and
the record that carry these are tested where they are built.
"""

from __future__ import annotations

import random
from collections import Counter

import pytest

from wl_xcon.scheduler import (
    BACK,
    CAP,
    CLEARED,
    CORRECT_ONLY,
    DESIGNED,
    FALL_BACK,
    RIG,
    RULE,
    RUN_TIME,
    TIME,
    Block,
    BlockEnd,
    Condition,
    Scheduler,
    Shortfall,
    WithReplacement,
)
from wl_xcon.task import (
    FRESH,
    OWED,
    ByCriterion,
    Counting,
    Listed,
    NonAging,
    Outcome,
    Priming,
    SequenceBalanced,
)
from wl_xcon.variation import balanced_sequence

#: Breaks after the stimulus owed, and a trial moved past after two failed tries in a row.
LIMITED = Counting(after_stimulus=OWED, cap=2)


def _sequence(names: str = "abcd", depth: int = 2, cycles: int = 1, again: bool = False,
              **block) -> Block:
    """A sequence-balanced block of one-letter conditions, each owed what its cycles plan."""
    count = len(names)
    return Block(
        name="seq",
        conditions=[Condition(name, {}, target=cycles * count ** (depth - 1)) for name in names],
        order=SequenceBalanced(depth=depth, cycles=cycles, again_at_once=again),
        **block,
    )


def _priming(chance: float | None = None, runs: tuple | None = None, again: bool = False,
             trials: int = 200, **block) -> Block:
    """A priming block on the target's color: four conditions, two red and two green."""
    return Block(
        name="prime",
        conditions=[Condition(f"{color}-{side}", {"target_color": color, "side": side}, target=0)
                    for color in ("red", "green") for side in ("left", "right")],
        order=Priming("target_color", chance=chance, runs=runs, again_at_once=again),
        trials=trials,
        **block,
    )


def _play(scheduler: Scheduler, outcomes, shown: bool = True, eased: bool = False) -> list:
    """Draw and record one trial per outcome; their draws."""
    draws = []
    for outcome in outcomes:
        scheduler.next_trial()
        draws.append(scheduler.drawn)
        scheduler.record(draws[-1].condition.name, outcome, shown=shown, eased=eased)
    return draws


def _finish(scheduler: Scheduler, limit: int) -> list:
    """Play right answers until the open block's rule is met, at most `limit` trials; their
    draws."""
    draws = []
    while not scheduler.finished:
        assert len(draws) < limit, "the block's rule is never met"
        draws += _play(scheduler, [Outcome.CORRECT])
    return draws


def _color(draw) -> str:
    return draw.condition.values["target_color"]


def test_a_sequence_balanced_block_plays_each_cycle_as_the_linear_sequence_every_pair_once():
    """The PI, Q5a, "Block picks; pairs default"; the C3 spec §5; and his answer of 2026-10-31 on
    the engine C3 plan's Appendix B, item 1, "Add one closing trial (Recommended)": at pairs each
    condition follows each, itself included, once a cycle, each cycle the linear de Bruijn
    sequence the block's own generator draws as it opens, n squared and one trials (four
    conditions, 17), so all 16 pairs show. Its first trial is a lead-in that only precedes what
    follows, and its place says so (`lead_in`). The block owes each place of its plan, the
    lead-in's among them (Appendix B item 11, as built). At triples each cycle opens on a lead-in
    of two, and every cycle holds every triple once."""
    scheduler = Scheduler([_sequence()], seed=11, counting=LIMITED)
    plan = scheduler.planned
    assert plan == balanced_sequence(list("abcd"), 2, 1, random.Random("design:11:0"))
    assert len(plan) == 17
    assert [scheduler.owed(name) for name in "abcd"] == [plan.count(name) for name in "abcd"]
    draws = []
    for _ in range(17):
        assert scheduler.ends is None and scheduler.drawable
        draws += _play(scheduler, [Outcome.CORRECT])
        assert sum(scheduler.owed(name) for name in "abcd") == 17 - len(draws)

    assert scheduler.finished
    names = tuple(draw.condition.name for draw in draws)
    assert names == plan
    assert [draw.planned for draw in draws] == [
        {"cycle": 0, "position": p, "lead_in": p == 0} for p in range(17)]
    pairs = Counter(zip(names, names[1:]))
    assert len(pairs) == 16 and set(pairs.values()) == {1}
    assert Counter(names[1:]) == {name: 4 for name in "abcd"}
    assert scheduler.ends == RULE and not scheduler.drawable
    assert scheduler.because(RULE) == "its rule met: its planned sequence played out"
    scheduler.close(RULE)
    assert scheduler.ended == [BlockEnd("seq", RULE, None, 16, 0, None, None, plan)]
    assert scheduler.shortfalls == []

    triples = Scheduler([_sequence("ab", depth=3, cycles=2)], seed=3, counting=LIMITED)
    played = _play(triples, [Outcome.CORRECT] * 20)
    assert triples.finished
    assert [draw.planned for draw in played] == [
        {"cycle": i // 10, "position": i % 10, "lead_in": i % 10 < 2} for i in range(20)]
    names = tuple(draw.condition.name for draw in played)
    for cycle in (names[:10], names[10:]):
        seen = Counter(zip(cycle, cycle[1:], cycle[2:]))
        assert len(seen) == 8 and set(seen.values()) == {1}


def test_a_sequence_balanced_block_ends_on_its_number_of_trials_owing_nothing():
    """The engine C3 plan's review, I-3: a sequence-balanced block ends at whichever comes first,
    its plan played out or its number of trials run, and owes nothing then; so does one a time
    limit cuts, its own or the run's. The places it did not play stay in its plan, which its end
    records, and in no shortfall."""
    scheduler = Scheduler([_sequence(trials=5)], seed=11, counting=LIMITED)
    plan = scheduler.planned
    _play(scheduler, [Outcome.CORRECT] * 4)
    assert scheduler.ends is None and sum(scheduler.owed(name) for name in "abcd") == 13
    _play(scheduler, [Outcome.CORRECT])
    assert scheduler.finished and scheduler.ends == RULE
    assert [scheduler.owed(name) for name in "abcd"] == [0, 0, 0, 0]
    assert scheduler.because(RULE) == "its rule met: 5 trials run"
    scheduler.close(RULE)
    assert scheduler.ended[-1].planned == plan and len(plan) == 17
    assert scheduler.shortfalls == []

    timed = Scheduler([_sequence()], seed=11, counting=LIMITED)
    _play(timed, [Outcome.CORRECT] * 3)
    timed.expire()
    assert timed.ends == TIME
    assert [timed.owed(name) for name in "abcd"] == [0, 0, 0, 0]
    timed.close(TIME)
    assert timed.shortfalls == [] and timed.ended[-1].planned == timed.planned

    run_timed = Scheduler([_sequence()], seed=11, counting=LIMITED)
    _play(run_timed, [Outcome.CORRECT] * 3)
    run_timed.close(RUN_TIME)
    assert run_timed.shortfalls == []
    assert [run_timed.owed(name) for name in "abcd"] == [0, 0, 0, 0]


def test_a_break_in_a_sequence_balanced_block_is_not_repeated_and_is_a_designed_shortfall():
    """TSK-31: designed blocks "default to no repeats". The broken trial's place is lost, one
    trial of its condition forgiven as `designed`, never flagged; a wrong answer is no break; and
    the sequence goes on."""
    scheduler = Scheduler([_sequence()], seed=11, counting=LIMITED)
    plan = scheduler.planned
    _play(scheduler, [Outcome.CORRECT, Outcome.WRONG_TARGET, Outcome.FIXATION_BREAK])

    assert scheduler.waiting == frozenset()
    assert scheduler.shortfalls == [Shortfall("seq", plan[2], 1, DESIGNED, 2)]
    assert not scheduler.shortfalls[0].possible_avoidance
    assert scheduler.counts(plan[2]).forgiven == 1 and scheduler.counts(plan[2]).repeats == 0
    following = _play(scheduler, [Outcome.CORRECT])[0]
    assert (following.condition.name, following.repeat_of) == (plan[3], None)
    assert following.planned == {"cycle": 0, "position": 3, "lead_in": False}
    rest = _finish(scheduler, 20)
    assert len(rest) == 13 and tuple(d.condition.name for d in rest) == plan[4:]


def test_a_break_in_a_priming_block_writes_no_shortfall():
    """The engine C3 plan's review, M-9; its Appendix B, item 6: a run counts only trials whose
    stimulus appeared, so a break before the stimulus loses no place -- the next trial takes it --
    and one after it is a shown trial of its run. Neither is shown again, and neither is a
    shortfall."""
    scheduler = Scheduler([_priming(runs=(3, 3))], seed=4, counting=LIMITED)
    first = _play(scheduler, [Outcome.CORRECT])[0]
    color = _color(first)
    assert first.planned == {"run": 0, "switch": True, "value": color}
    early = _play(scheduler, [Outcome.FIXATION_BREAK], shown=False)[0]
    assert early.planned == {"run": 0, "switch": False, "value": color}
    taken = _play(scheduler, [Outcome.CORRECT])[0]
    assert taken.planned == early.planned and taken.repeat_of is None
    late = _play(scheduler, [Outcome.FIXATION_BREAK])[0]
    assert late.planned == {"run": 0, "switch": False, "value": color}
    switched = _play(scheduler, [Outcome.CORRECT])[0]

    assert switched.planned == {"run": 1, "switch": True, "value": _color(switched)}
    assert _color(switched) != color
    assert [_color(draw) for draw in (first, early, taken, late)] == [color] * 4
    assert scheduler.shortfalls == [] and scheduler.waiting == frozenset()
    assert scheduler.planned == ((color, 3), (_color(switched), 3))
    assert not scheduler.past_targets and scheduler.owed(first.condition.name) == 0


def test_again_at_once_brings_the_broken_trial_straight_back_with_its_planned_place():
    """The PI, Q5b, "'Again at once' as an option"; the C3 spec §5: the broken trial comes straight
    back, so every planned transition still happens. It is a repeat of the trial that broke, at
    once, with its place, and the plan waits for it: a break at its last place holds the block open
    until it comes back."""
    scheduler = Scheduler([_sequence(again=True)], seed=11, counting=LIMITED)
    plan = scheduler.planned
    _play(scheduler, [Outcome.CORRECT, Outcome.CORRECT, Outcome.FIXATION_BREAK])
    assert scheduler.waiting == frozenset({2})
    assert scheduler.owed(plan[2]) == plan[3:].count(plan[2]) + 1
    back = _play(scheduler, [Outcome.CORRECT])[0]

    assert (back.condition.name, back.repeat_of, back.at_once) == (plan[2], 2, True)
    assert back.planned == {"cycle": 0, "position": 2, "lead_in": False}
    assert scheduler.waiting == frozenset() and scheduler.shortfalls == []
    assert scheduler.counts(plan[2]).repeats == 1
    following = _play(scheduler, [Outcome.CORRECT])[0]
    assert (following.condition.name, following.planned) == (
        plan[3], {"cycle": 0, "position": 3, "lead_in": False})
    _play(scheduler, [Outcome.CORRECT] * 12)
    last = _play(scheduler, [Outcome.FIXATION_BREAK])[0]
    assert last.planned == {"cycle": 0, "position": 16, "lead_in": False}
    assert not scheduler.finished and scheduler.ends is None and scheduler.drawable
    final = _play(scheduler, [Outcome.CORRECT])[0]
    assert (final.repeat_of, final.planned) == (last.number, last.planned)
    assert scheduler.finished

    priming = Scheduler([_priming(runs=(2, 2), again=True)], seed=4, counting=LIMITED)
    broken = _play(priming, [Outcome.FIXATION_BREAK], shown=False)[0]
    again = _play(priming, [Outcome.CORRECT])[0]
    assert (again.condition, again.repeat_of, again.at_once) == (broken.condition, 0, True)
    assert again.planned == broken.planned == {"run": 0, "switch": True, "value": _color(broken)}
    assert _play(priming, [Outcome.CORRECT])[0].planned == {
        "run": 0, "switch": False, "value": _color(broken)}


def test_again_at_once_moves_past_a_trial_after_the_repeat_limit_flagging_avoidance():
    """The engine C3 plan's review, I-4, and its Appendix B, item 9: a trial brought back at once
    is moved past after the task's repeat limit, as any repeat is (§16.6; the PI, 2026-10-12:
    "moved past after 3 failed repeats in a row"), flagged as possible avoidance unless the rig
    lost a try, and the sequence goes on; its count then starts over."""
    scheduler = Scheduler([_sequence(again=True)], seed=11, counting=LIMITED)
    plan = scheduler.planned
    tries = _play(scheduler, [Outcome.FIXATION_BREAK] * 3)

    assert [(t.condition.name, t.repeat_of) for t in tries] == [
        (plan[0], None), (plan[0], 0), (plan[0], 1)]
    assert scheduler.shortfalls == [Shortfall("seq", plan[0], 1, CAP, 2)]
    assert scheduler.shortfalls[0].possible_avoidance and scheduler.counts(plan[0]).flagged
    assert scheduler.waiting == frozenset()
    assert _play(scheduler, [Outcome.CORRECT])[0].planned == {
        "cycle": 0, "position": 1, "lead_in": False}
    later = plan.index(plan[0], 1)
    _play(scheduler, [Outcome.CORRECT] * (later - 2))
    again = _play(scheduler, [Outcome.FIXATION_BREAK])[0]
    assert again.planned == {"cycle": 0, "position": later, "lead_in": False}
    assert scheduler.waiting == frozenset({again.number})

    rig = Scheduler([_sequence(again=True)], seed=11, counting=LIMITED)
    _play(rig, [Outcome.FIXATION_BREAK, Outcome.TRACKER_LOST, Outcome.FIXATION_BREAK])
    assert [(s.because, s.possible_avoidance) for s in rig.shortfalls] == [(RIG, False)]

    priming = Scheduler([_priming(chance=0.5, again=True)], seed=4, counting=LIMITED)
    _play(priming, [Outcome.FIXATION_BREAK] * 3)
    assert [(s.trials, s.because) for s in priming.shortfalls] == [(1, CAP)]


def test_priming_by_chance_repeats_at_its_rate_and_every_switch_changes_the_value():
    """The PI, Q6, "Both of the last two": within one block, a set chance that the next trial
    repeats the last one's feature, interleaved. At 0.7, seeded: the repeats are pinned, and near
    the chance; every switch picks the other value; within a value its conditions play in shuffled
    passes; and the runs it records are as played."""
    scheduler = Scheduler([_priming(chance=0.7, trials=400)], seed=21, counting=LIMITED)
    draws = _finish(scheduler, 500)
    colors = [_color(draw) for draw in draws]

    assert len(draws) == 400
    assert all(draw.planned["value"] == color for draw, color in zip(draws, colors))
    repeats = sum(a == b for a, b in zip(colors, colors[1:]))
    assert repeats == 273 and 0.62 < repeats / 399 < 0.78
    assert [draw.planned["switch"] for draw in draws] == [
        i == 0 or colors[i] != colors[i - 1] for i in range(400)]
    runs = scheduler.planned
    assert len(runs) == 400 - repeats and sum(length for _, length in runs) == 400
    assert all(a[0] != b[0] for a, b in zip(runs, runs[1:]))
    for color in ("red", "green"):
        names = [draw.condition.name for draw in draws if _color(draw) == color]
        passes = [tuple(names[i:i + 2]) for i in range(0, len(names) - 1, 2)]
        assert {tuple(sorted(each)) for each in passes} == {(f"{color}-left", f"{color}-right")}
        assert len(set(passes)) == 2


def test_priming_by_runs_draws_lengths_in_range_counting_shown_trials():
    """The PI, Q6, "Both of the last two": runs of one feature whose lengths are drawn (3 to 7
    here), then a switch. A run counts only the trials whose stimulus appeared (the engine C3
    plan's Appendix B, item 6), so each run but the last shows exactly its drawn length however
    many of its trials broke before the stimulus, and its first place is a switch until a trial of
    it is shown."""
    scheduler = Scheduler([_priming(runs=(3, 7), trials=300)], seed=8, counting=LIMITED)
    chance = random.Random(8)
    draws, shown = [], []
    for _ in range(500):
        if scheduler.finished:
            break
        appeared = chance.random() < 0.8
        draws += _play(scheduler, [Outcome.CORRECT if appeared else Outcome.FIXATION_BREAK],
                       shown=appeared)
        shown.append(appeared)
    runs = scheduler.planned

    assert len(draws) == 300

    assert all(3 <= length <= 7 for _, length in runs)
    assert len({length for _, length in runs}) == 5
    assert all(a[0] != b[0] for a, b in zip(runs, runs[1:]))
    assert shown.count(False) > 0 and scheduler.shortfalls == []
    for number, (value, length) in enumerate(runs):
        mine = [(draw, appeared) for draw, appeared in zip(draws, shown)
                if draw.planned["run"] == number]
        assert all(draw.planned["value"] == value == _color(draw) for draw, _ in mine)
        assert sum(appeared for _, appeared in mine) == length or number == len(runs) - 1
        before = [any(appeared for _, appeared in mine[:i]) for i in range(len(mine))]
        assert [draw.planned["switch"] for draw, _ in mine] == [not b for b in before]


def test_priming_runs_drawn_from_a_distribution_play_their_drawn_lengths():
    """The C3 plan's science review, I-8: a priming block's run lengths may be drawn by any of the
    five distributions, each its draw rounded down. A non-aging draw from 2 to 6 trials, mean 3,
    gives lengths of 2 to 5, the shortest most often, and the seed replays them; a prepared
    list plays its lengths in passes, in order where it says so."""
    def lengths(runs, seed: int = 8, trials: int = 300) -> list[int]:
        scheduler = Scheduler([_priming(runs=runs, trials=trials)], seed=seed, counting=LIMITED)
        _finish(scheduler, trials + 1)
        return [length for _, length in scheduler.planned]

    waited = lengths(NonAging(2.0, 3.0, 6.0, repeat=FRESH))
    assert set(waited[:-1]) <= {2, 3, 4, 5} and len(set(waited[:-1])) >= 3
    counted = Counter(waited[:-1])
    assert counted[2] == max(counted.values())
    assert lengths(NonAging(2.0, 3.0, 6.0, repeat=FRESH)) == waited
    assert lengths(NonAging(2.0, 3.0, 6.0, repeat=FRESH), seed=9) != waited
    assert lengths(Listed((2, 4), in_order=True, repeat=FRESH), trials=24) == [2, 4] * 4
    passes = lengths(Listed((2, 3, 4), repeat=FRESH), trials=27)
    assert all(sorted(passes[at:at + 3]) == [2, 3, 4] for at in (0, 3, 6))
    assert passes != [2, 3, 4] * 3


def test_an_eased_trial_never_counts_toward_a_rule_and_always_toward_the_fall_back():
    """The PI, Q8, "Merge; fix eased trials in C3": eased trials do not count toward moving up,
    and do count toward moving back (the C3 spec §7). Left out of the window a block's criterion
    reads, judged by the fall-back as any answer is, and counted toward its condition outside a
    training progression."""
    block = Block(name="A", conditions=[Condition("x", {}, target=1)], criterion=(1.0, 3))
    scheduler = Scheduler([block], seed=1)
    for eased in (False, True, False):
        scheduler.record(scheduler.next_trial().name, Outcome.CORRECT, eased=eased)
    assert not scheduler.finished and scheduler.ends is None
    assert (scheduler.counts("x").completed, scheduler.counts("x").eased) == (3, 0)
    assert scheduler.block_report[0].trials == 3
    scheduler.record(scheduler.next_trial().name, Outcome.CORRECT)
    assert scheduler.finished
    assert scheduler.because(RULE) == (
        "its rule met: 3 right in a row, every target used up")

    stages = [Block(name=name, conditions=[Condition("x", {}, target=1)], criterion=(1.0, 3))
              for name in ("S1", "S2")]
    progression = Scheduler(stages, seed=1, order=ByCriterion(fall_back=(0.5, 4)))
    _play(progression, [Outcome.CORRECT] * 3)
    progression.advance(progression.ends)
    _play(progression, [Outcome.WRONG_TARGET] * 4, eased=True)
    assert progression.ends == FALL_BACK
    assert progression.because(FALL_BACK) == (
        "fell back: 0 of its last 4 first answers right, under 50%")


def test_in_a_progression_an_eased_trial_counts_toward_neither_a_stages_trials_nor_targets():
    """The engine C3 plan's review, I-7, and its Appendix B, item 10: a stage with no criterion
    ends when its trials are run and its targets met, so an eased trial counts toward neither --
    an answer that paid nothing leaves its condition owing as before -- and its condition is drawn
    on. Its condition's own counts keep it. Outside a progression the same trials count."""
    stages = [Block(name="S1", conditions=[Condition("x", {}, target=2)], trials=3),
              Block(name="S2", conditions=[Condition("x", {}, target=1)])]
    scheduler = Scheduler(stages, seed=1, counting=CORRECT_ONLY, order=ByCriterion())
    _play(scheduler, [Outcome.WRONG_TARGET], eased=True)
    assert (scheduler.block_trials, scheduler.owed("x")) == (0, 2)
    _play(scheduler, [Outcome.CORRECT] * 3, eased=True)
    counts = scheduler.counts("x")
    assert (counts.eased, counts.eased_paid, counts.completed) == (4, 3, 3)
    assert (scheduler.block_trials, scheduler.owed("x"), scheduler.finished) == (0, 2, False)
    assert not scheduler.past_targets
    report = scheduler.block_report[0]
    assert (report.trials, report.right, report.wrong, report.owed) == (4, 3, 1, 2)
    _play(scheduler, [Outcome.CORRECT] * 2)
    assert (scheduler.block_trials, scheduler.owed("x"), scheduler.finished) == (2, 0, False)
    assert scheduler.past_targets
    _play(scheduler, [Outcome.WRONG_TARGET])
    assert scheduler.finished and scheduler.ends == RULE
    assert scheduler.because(RULE) == "its rule met: 3 trials run, every target used up"

    fixed = Scheduler([stages[0]], seed=1, counting=CORRECT_ONLY)
    _play(fixed, [Outcome.CORRECT] * 3, eased=True)
    assert fixed.finished and fixed.counts("x").eased == 0


def test_waiting_names_every_trial_a_repeat_a_drum_or_again_at_once_will_show():
    """What the trial loop keeps a trial's drawn values for (the engine C3 plan's call 13): each
    trial a waiting repeat, a drum or a trial again at once will show again, by its number, until
    it is shown."""
    block = Block(name="A", conditions=[Condition(name, {}, target=2) for name in "xyz"])
    ordinary = Scheduler([block], seed=1, counting=LIMITED)
    _play(ordinary, [Outcome.FIXATION_BREAK] * 2)
    assert ordinary.waiting == frozenset({0, 1})
    shown_again = [draw.repeat_of for draw in _play(ordinary, [Outcome.CORRECT] * 6)
                   if draw.repeat_of is not None]
    assert sorted(shown_again) == [0, 1] and ordinary.waiting == frozenset()

    drummed = Scheduler([Block(name="A", conditions=block.conditions, drum=True)], seed=1,
                        counting=LIMITED)
    _play(drummed, [Outcome.WRONG_TARGET])
    assert drummed.waiting == frozenset({0})
    _play(drummed, [Outcome.FIXATION_BREAK])
    assert drummed.waiting == frozenset({1})
    _play(drummed, [Outcome.CORRECT])
    assert drummed.waiting == frozenset()

    again = Scheduler([_sequence(again=True)], seed=11, counting=LIMITED)
    _play(again, [Outcome.CORRECT, Outcome.FIXATION_BREAK])
    assert again.waiting == frozenset({1})
    _play(again, [Outcome.CORRECT])
    assert again.waiting == frozenset()


def test_a_person_clears_only_a_trial_waiting_to_come_back_in_a_designed_block():
    """A designed block's plan gives its trials, so the training aid *clear* moves past only a
    trial waiting to come back -- one again at once, or a drum's -- as it moves past any ("End that
    waiting trial; count starts over"), and the plan goes on; anything else is refused, saying
    why."""
    scheduler = Scheduler([_sequence(again=True)], seed=11, counting=LIMITED)
    scheduler.train("clear", True)
    plan = scheduler.planned
    assert scheduler.clear(plan[0], by="kim") == (
        f"block 'seq' plays a designed order, so only a trial waiting to come back is cleared, "
        f"and no trial of {plan[0]!r} waits")
    _play(scheduler, [Outcome.FIXATION_BREAK])
    assert scheduler.clear(plan[0], by="kim") is None
    assert scheduler.shortfalls == [Shortfall("seq", plan[0], 1, CLEARED, 0, "kim")]
    assert scheduler.waiting == frozenset()
    following = _play(scheduler, [Outcome.CORRECT])[0]
    assert (following.repeat_of, following.planned) == (
        None, {"cycle": 0, "position": 1, "lead_in": False})

    priming = Scheduler([_priming(runs=(2, 2), drum=True)], seed=4, counting=LIMITED)
    priming.train("clear", True)
    first = _play(priming, [Outcome.WRONG_TARGET])[0]
    assert priming.waiting == frozenset({0})
    assert priming.clear(first.condition.name) is None
    following = _play(priming, [Outcome.CORRECT])[0]
    assert following.repeat_of is None
    assert following.planned == {"run": 0, "switch": False, "value": _color(first)}


def test_a_sequence_balanced_block_survives_a_drum_a_move_back_and_its_time():
    """Review Focus 2, the engine C3 plan's: a trainer switches drumming on mid-sequence, presses
    *back one* into a sequence-balanced block, and lets its time cut its second cycle. Drummed
    tries never move the plan; the reopened block plays a new sequence from its own occurrence
    (its Appendix B, item 7); the cut leaves the places never reached in its plan, and the
    only shortfall is the one trial that broke."""
    blocks = [_sequence("abc", cycles=2), Block(name="after", conditions=[Condition("z", {}, 1)])]
    scheduler = Scheduler(blocks, seed=6, counting=LIMITED)
    first = scheduler.planned
    assert first == balanced_sequence(list("abc"), 2, 2, random.Random("design:6:0"))
    assert len(_finish(scheduler, 20)) == 20
    scheduler.advance(scheduler.ends)
    assert scheduler.move(BACK, "kim") is None and scheduler.block.name == "seq"
    reopened = scheduler.planned
    assert reopened == balanced_sequence(list("abc"), 2, 2, random.Random("design:6:2"))
    assert reopened != first

    _play(scheduler, [Outcome.CORRECT] * 3)
    scheduler.drum("block")
    tries = _play(scheduler, [Outcome.WRONG_TARGET, Outcome.FIXATION_BREAK, Outcome.CORRECT])
    third = {"cycle": 0, "position": 3, "lead_in": False}
    assert [(t.planned, t.drummed) for t in tries] == [(third, False), (third, True), (third, True)]
    assert {t.condition.name for t in tries} == {reopened[3]}
    scheduler.drum("off")
    broken = _play(scheduler, [Outcome.FIXATION_BREAK])[0]
    assert broken.planned == {"cycle": 0, "position": 4, "lead_in": False}
    assert _play(scheduler, [Outcome.CORRECT] * 6)[-1].planned == {
        "cycle": 1, "position": 0, "lead_in": True}
    scheduler.expire()
    assert scheduler.ends == TIME
    assert [scheduler.owed(name) for name in "abc"] == [0, 0, 0]
    scheduler.advance(TIME)

    assert [(end.block, end.ended, end.planned) for end in scheduler.ended] == [
        ("seq", RULE, first), ("after", BACK, None), ("seq", TIME, reopened)]
    assert scheduler.shortfalls == [Shortfall("seq", reopened[4], 1, DESIGNED, broken.number)]
    assert scheduler.block.name == "after"


def _designed(rng: random.Random) -> Block:
    """A random designed block: sequence-balanced over two to four conditions, at depth 2 (or 3
    over two), once or twice over, perhaps cut by a number of trials; or priming over two or three
    values, by a chance or by runs of one to six; either perhaps again at once, perhaps drummed."""
    again, drum = rng.random() < 0.4, rng.random() < 0.2
    if rng.random() < 0.5:
        names = "abcd"[:rng.randint(2, 4)]
        depth = rng.choice([2, 3]) if len(names) == 2 else 2
        return _sequence(names, depth=depth, cycles=rng.randint(1, 2), again=again, drum=drum,
                         trials=rng.choice([None, rng.randint(1, 20)]))
    low = rng.randint(1, 3)
    order = (Priming("target_color", runs=(low, low + rng.randint(0, 3)), again_at_once=again)
             if rng.random() < 0.5
             else Priming("target_color", chance=rng.random(), again_at_once=again))
    values = ("red", "green", "blue")[:rng.randint(2, 3)]
    return Block(
        name="prime",
        conditions=[Condition(f"{value}-{i}", {"target_color": value}, target=0)
                    for value in values for i in range(rng.randint(1, 2))],
        order=order, trials=rng.randint(5, 60), drum=drum,
    )


@pytest.mark.parametrize("seed", range(0, 300, 30))
def test_a_fuzz_of_300_designed_blocks_keeps_every_invariant(seed):
    """Engine build C3's designed blocks fuzzed, thirty a case, each followed by an ordinary block,
    with random outcomes, stimuli shown or not, eased trials, drumming switched and time run out.
    A fresh trial of a sequence-balanced block plays its plan's next place, each once and in
    order; a drum's try and a trial again at once show the trial just before them again, with its
    place; a priming trial's value is its condition's, its first place a switch, every switch a
    new value, and a run shows its drawn length (under a chance, the length it records); only a
    sequence-balanced block writes a `designed` shortfall, one trial, never flagged; no block ends
    on its rule while a trial waits to come back; `waiting` names each such trial; an eased try
    never reaches the rule's window; and every designed block ends within 600 tries. Each case
    meets every kind of event it checks."""
    met = Counter()
    for case in range(seed, seed + 30):
        rng = random.Random(case)
        block = _designed(rng)
        tail = Block(name="tail", conditions=[Condition("z", {}, target=1)])
        scheduler = Scheduler([block, tail], seed=case, counting=LIMITED)
        order, plan = block.order, scheduler.planned
        fresh, last, shown_runs, chain = 0, None, Counter(), (None, False)
        for _ in range(600):
            if scheduler.block is tail:
                break
            ending = scheduler.ends
            if ending is not None:
                assert ending != RULE or (scheduler._again, scheduler._drum) == (None, None), case
                met[ending] += 1
                scheduler.advance(ending)
                planned = scheduler.ended[-1].planned
                if isinstance(order, SequenceBalanced):
                    assert planned == plan, case
                    cycle = len(block.conditions) ** order.depth + order.depth - 1
                    assert len(plan) == cycle * order.cycles, case
                    continue
                shown_runs[chain[0]] += chain[1]
                assert all(a[0] != b[0] for a, b in zip(planned, planned[1:])), case
                lengths = [length for _, length in planned]
                if order.runs is None:
                    assert lengths == [shown_runs[i] for i in range(len(planned))], case
                else:
                    assert all(order.runs[0] <= n <= order.runs[1] for n in lengths), case
                    assert [shown_runs[i] for i in range(len(planned) - 1)] == lengths[:-1], case
                    assert shown_runs[len(planned) - 1] <= lengths[-1], case
                continue
            assert scheduler.drawable, case
            waiting = scheduler.waiting
            scheduler.next_trial()
            draw = scheduler.drawn
            met["drummed" if draw.drummed else "fresh" if draw.repeat_of is None else "again"] += 1
            if draw.drummed or draw.repeat_of is not None:
                assert draw.repeat_of == last.number and draw.repeat_of in waiting, case
                assert draw.planned == last.planned, case
            elif isinstance(order, SequenceBalanced):
                cycle = len(block.conditions) ** order.depth + order.depth - 1
                place = draw.planned["cycle"] * cycle + draw.planned["position"]
                assert draw.planned["lead_in"] == (draw.planned["position"] < order.depth - 1), case
                assert place == fresh and draw.condition.name == plan[place], case
                fresh += 1
            else:
                shown_runs[chain[0]] += chain[1]
                run = draw.planned["run"]
                assert draw.planned["switch"] == (shown_runs[run] == 0), case
                assert draw.planned["value"] == _color(draw), case
                chain = (run, False)
            shown = rng.random() < 0.8
            outcome = rng.choice([Outcome.CORRECT, Outcome.CORRECT, Outcome.WRONG_TARGET,
                                  Outcome.FIXATION_BREAK, Outcome.TRACKER_LOST])
            eased = rng.random() < 0.2
            window, written = len(scheduler._window), len(scheduler.shortfalls)
            kind = scheduler.record(draw.condition.name, outcome, shown=shown, eased=eased)
            chain = (chain[0], chain[1] or shown)
            if eased:
                assert len(scheduler._window) == window, case
            new = scheduler.shortfalls[written:]
            met.update(short.because for short in new)
            for short in new:
                assert (short.trials, short.after_trial) == (1, draw.number), case
                if short.because == DESIGNED:
                    assert isinstance(order, SequenceBalanced) and kind == OWED, case
                    assert not short.possible_avoidance and not order.again_at_once, case
                else:
                    assert short.because in (CAP, RIG) and order.again_at_once, case
            if scheduler.drumming and outcome is not Outcome.CORRECT:
                assert scheduler.waiting == {draw.number} and not new, case
            elif kind == OWED and order.again_at_once:
                assert scheduler.waiting == ({draw.number} if not new else frozenset()), case
            else:
                assert scheduler.waiting == frozenset(), case
            last = draw
            if rng.random() < 0.05:
                scheduler.drum(rng.choice(["block", "off"]))
            if rng.random() < 0.01:
                scheduler.expire()
        else:
            raise AssertionError(f"case {case} did not leave its designed block")
    assert all(met[event] for event in ("fresh", "drummed", "again", DESIGNED, RULE, TIME)), met
    assert met[CAP] + met[RIG] > 0, met


def test_an_ordinary_blocks_draws_are_as_the_seed_gave_them():
    """A designed block draws from a generator of its own (`random.Random(f"design:{seed}:...")`),
    never the one an ordinary block's draws and repeats share. So an ordinary block's draws and
    repeats are the ones the seed gave it before engine build C3, pinned here as they were drawn
    then, and the same with a designed block played before it."""
    shuffled = Block(name="A", conditions=[Condition(name, {}, target=3) for name in "xyz"])
    weighted = Block(name="B", conditions=[Condition(name, {}, target=4) for name in "xyz"],
                     order=WithReplacement(weights={"x": 2.0}))

    def draws(blocks: list, seed: int, count: int) -> list:
        scheduler = Scheduler(blocks, seed=seed, counting=LIMITED)
        for _ in range(20):
            if scheduler.block is blocks[-1]:
                break
            if scheduler.ends is not None:
                scheduler.advance(scheduler.ends)
            else:
                _play(scheduler, [Outcome.CORRECT])
        start, played = scheduler._number, []
        for i in range(count):
            draw = _play(scheduler, [Outcome.FIXATION_BREAK if i % 4 == 1 else Outcome.CORRECT])[0]
            played.append((draw.condition.name,
                           None if draw.repeat_of is None else draw.repeat_of - start))
        return played

    pinned_a = [("x", None), ("y", None), ("z", None), ("z", None), ("y", 1), ("x", None),
                ("z", None), ("y", None), ("x", 5), ("y", None), ("x", None)]
    pinned_b = [("x", None), ("x", None), ("y", None), ("x", 1), ("z", None), ("x", None),
                ("z", None), ("y", None), ("x", 5), ("z", None), ("y", None), ("z", 9)]
    assert draws([shuffled], 5, 11) == pinned_a
    assert draws([weighted], 9, 12) == pinned_b
    assert draws([_sequence("pq", again=True), shuffled], 5, 11) == pinned_a
    assert draws([_priming(runs=(1, 2), trials=6), weighted], 9, 12) == pinned_b


def test_a_time_limit_does_not_wait_for_a_trial_due_again_at_once():
    """Appendix B item 13, which the PI confirmed on 2026-10-31: only a drum holds a time limit
    ("Finish the drum first"). A trial due again at once is dropped by the cut, as a waiting
    repeat is: the block ends on its time, owes nothing, and writes no shortfall for it."""
    sequence = Scheduler([_sequence(again=True)], seed=11, counting=LIMITED)
    _play(sequence, [Outcome.CORRECT, Outcome.FIXATION_BREAK])
    assert sequence.waiting == frozenset({1})
    sequence.expire()
    assert sequence.ends == TIME
    assert [sequence.owed(name) for name in "abcd"] == [0] * 4
    sequence.close(TIME)
    assert sequence.shortfalls == []

    priming = Scheduler([_priming(runs=(2, 2), again=True)], seed=4, counting=LIMITED)
    _play(priming, [Outcome.FIXATION_BREAK], shown=False)
    assert priming.waiting == frozenset({0})
    priming.expire()
    assert priming.ends == TIME
    assert [priming.owed(c.name) for c in priming.block.conditions] == [0] * 4
    priming.close(TIME)
    assert priming.shortfalls == []


def test_reading_drawable_between_trials_does_not_move_a_priming_blocks_plan():
    """`drawable` is a property any reader may use; a priming block's seeded plan must not depend
    on when it is read, so a plan replays from its seed whoever looks."""
    def played(extra_reads: bool) -> list:
        scheduler = Scheduler([_priming(chance=0.5, trials=200)], seed=3, counting=LIMITED)
        names = []
        for _ in range(40):
            scheduler.next_trial()
            draw = scheduler.drawn
            if extra_reads:
                assert scheduler.drawable
            scheduler.record(draw.condition.name, Outcome.CORRECT)
            if extra_reads:
                assert scheduler.drawable
            names.append((draw.condition.name, draw.planned["run"]))
        return names

    assert played(True) == played(False)


def test_a_trial_due_again_at_once_is_still_owed_after_the_blocks_trials_are_run():
    """A sequence-balanced block whose last allowed trial breaks, again at once, owes that one
    trial of its condition and nothing else, and is not finished until it comes back."""
    scheduler = Scheduler([_sequence(trials=5, again=True)], seed=11, counting=LIMITED)
    plan = scheduler.planned
    _play(scheduler, [Outcome.CORRECT] * 4 + [Outcome.FIXATION_BREAK])
    assert scheduler.block_trials >= 5 and not scheduler.finished
    assert [scheduler.owed(name) for name in "abcd"] == [int(name == plan[4]) for name in "abcd"]
    _play(scheduler, [Outcome.CORRECT])
    assert scheduler.finished and [scheduler.owed(name) for name in "abcd"] == [0] * 4
