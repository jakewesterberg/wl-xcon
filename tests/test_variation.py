"""The arithmetic of variation (engine build C3; its spec §2-§7 and §10): keyed draws and what each
can give, the non-aging wait's redrawn tail and its hazard, a prepared list's passes, where a
block's draws come from, factorial conditions and their names, de Bruijn sequences, the live
numbers, a draw as the record writes it and the rig says it, the settings that are directions,
and whether a value is easier. Pure functions: nothing here runs a session."""

from __future__ import annotations

import collections
import dataclasses
import json
import math
import os
import random
import statistics
import subprocess
import sys
from pathlib import Path

import pytest

from wl_xcon import variation
from wl_xcon.cli import _load_task
from wl_xcon.declarations import COMMON
from wl_xcon.task import (
    BY_CONDITIONS,
    CLEAR_CUT,
    CRITERION,
    EASIER,
    EXPECTED,
    FRESH,
    HARDER,
    OWED,
    SAME,
    STIMULUS,
    After,
    Block,
    Condition,
    Counting,
    Disc,
    Distribution,
    Factorial,
    Listed,
    Meaning,
    NonAging,
    On,
    Outcome,
    P,
    Param,
    Polar,
    Show,
    State,
    Stimulus,
    Task,
    Trial,
    TruncatedNormal,
    Uniform,
    Update,
    Weighted,
    Window,
)
from wl_xcon.variation import (
    LIVE_NUMBERS,
    balanced_sequence,
    bounds_of,
    directions,
    draw,
    easier,
    expanded,
    generated,
    hazard_ratio,
    in_force,
    level_name,
    numbers,
    own_ranges,
    realized_mean,
    recorded,
    run_length,
    switch_chances,
    unit,
    values_of,
    with_numbers,
    words,
)

ROOT = Path(__file__).resolve().parents[1]
#: Keys drawn per distribution: enough that a share is within a hundredth of its chance.
KEYS = 10_000
HOLD = Param("fix_hold", unit="s", low=0.05, high=2.0, start=0.3)
WAIT = Param("wait", unit="s", low=0.5, high=1.5, start=1.0)
CONTRAST = Param("contrast", unit="fraction", low=0.02, high=1.0, start=0.5)

#: A script that loads this file in another process and prints what `_sample` gives there.
_ELSEWHERE = (
    "import importlib.util, sys\n"
    "spec = importlib.util.spec_from_file_location('drawn_elsewhere', sys.argv[1])\n"
    "module = importlib.util.module_from_spec(spec)\n"
    "spec.loader.exec_module(module)\n"
    "print(repr(module._sample()))\n"
)


def _sample() -> list:
    """What seed 7 gives: a unit, a draw of each kind on trial 3, a list's sixth fresh draw and a
    designed sequence."""
    return [
        unit(7, 0, "wait", 0),
        draw(Uniform(0.2, 0.4, repeat=FRESH), 7, 3, ("task", "wait")),
        draw(Weighted(("a", "b", "c"), (1, 2, 3), repeat=FRESH), 7, 3, ("block", "b", "side")),
        draw(TruncatedNormal(1.0, 0.1, repeat=FRESH), 7, 3, ("task", "fix_hold"), declared=HOLD),
        draw(Listed((2, 4, 6, 8), repeat=FRESH), 7, 3, ("task", "set_size"), ordinal=5),
        draw(NonAging(0.75, 1.0, 1.25, repeat=FRESH), 7, 3, ("task", "wait")),
        balanced_sequence(["a", "b", "c"], 2, 1, random.Random("design:7:0")),
    ]


def _task(**fields) -> Task:
    """One structure declaring a hold, a wait and a contrast; its draws and plans as given."""
    trial = Trial(
        start="wait",
        params=[HOLD, WAIT, CONTRAST],
        states=[State("wait", go=[On(After(P("wait")), Outcome.CORRECT)])],
        counting=Counting(after_stimulus=OWED, appears="wait"),
    )
    return Task({"wait": trial}, default="wait", **fields)


def test_one_key_gives_one_value_in_another_process():
    """Engine build C3's call 4 [@salmon2011parallel]: a draw is a function of its key alone, so
    two processes, each with its own fixed `PYTHONHASHSEED` (call 40), agree with this one; and
    the key's first unit is pinned, so the value one key gives cannot move between versions, nor
    a designed sequence one seed gives, without this failing."""

    def elsewhere(seed: str) -> str:
        done = subprocess.run(
            [sys.executable, "-c", _ELSEWHERE, __file__], cwd=ROOT,
            env={**os.environ, "PYTHONHASHSEED": seed, "PYTHONPATH": str(ROOT)},
            capture_output=True, text=True, timeout=120,
        )
        assert done.returncode == 0, done.stderr
        return done.stdout.strip()

    here = _sample()

    assert elsewhere("1") == elsewhere("999") == repr(here)
    assert here[0] == 0.26757503367803215
    assert here[-1] == ("a", "b", "c", "c", "a", "c", "b", "b", "a", "a")


def test_every_draw_falls_inside_what_its_distribution_can_give(monkeypatch):
    """Each of the PI's five (TSK-24), 10,000 keys each: inside its bounds (`bounds_of`) or among
    its values (`values_of`), spread as its distribution says. A normal is cut to its setting's
    declared range unless it declares its own, end by end. **A cut far in a tail, and a unit of
    0 or just under 1, give a value inside, never an exception** (call 5; review I-2): the
    normal's probability is held inside (0, 1), where `NormalDist.inv_cdf` answers."""
    narrow = Param("fix_hold", unit="s", low=0.95, high=1.3)
    cases = [
        (Uniform(0.2, 0.4, repeat=FRESH), None, (0.2, 0.4)),
        (Weighted((0.9, 0.1, 0.5, 0.7), (0, 3, 1, 0), repeat=FRESH), None, None),
        (TruncatedNormal(1.0, 0.1, repeat=FRESH), narrow, (0.95, 1.3)),
        (TruncatedNormal(1.0, 0.1, low=0.9, high=1.1, repeat=FRESH), narrow, (0.9, 1.1)),
        (TruncatedNormal(1.0, 0.1, low=0.9, repeat=FRESH), narrow, (0.9, 1.3)),
        (Listed((2, 4, 6), repeat=FRESH), None, None),
        (NonAging(0.75, 1.0, 1.25, repeat=FRESH), None, (0.75, 1.25)),
    ]
    drawn = []
    for distribution, declared, bounds in cases:
        assert bounds_of(distribution, declared) == bounds
        values = [draw(distribution, 5, trial, ("task", "x"), declared=declared, ordinal=trial)
                  for trial in range(KEYS)]
        if bounds is None:
            assert set(values) <= set(values_of(distribution))
        else:
            assert all(bounds[0] <= value <= bounds[1] for value in values)
        drawn.append(values)

    uniform, weighted, normal_cut, _, _, listed, _ = drawn
    assert min(uniform) < 0.201 and max(uniform) > 0.399
    assert statistics.fmean(uniform) == pytest.approx(0.3, abs=0.002)
    assert {0.9, 0.7}.isdisjoint(weighted)
    assert weighted.count(0.1) / KEYS == pytest.approx(0.75, abs=0.015)
    normal = statistics.NormalDist(1.0, 0.1)
    cut = normal.cdf(1.3) - normal.cdf(0.95)
    expected = 1.0 + 0.1 * (normal.pdf(0.95) - normal.pdf(1.3)) * 0.1 / cut
    assert statistics.fmean(normal_cut) == pytest.approx(expected, abs=0.003)
    assert sorted(collections.Counter(listed).values()) == [3333, 3333, 3334]
    assert (bounds_of(TruncatedNormal(1.0, 0.1)), values_of(Uniform(0.2, 0.4))) == (
        (-math.inf, math.inf), ())
    assert values_of(Weighted((0.9, 0.1, 0.5, 0.7), (0, 3, 1, 0))) == (0.9, 0.1, 0.5, 0.7)

    for far in (TruncatedNormal(0.0, 1.0, low=40.0, high=41.0, repeat=FRESH),
                TruncatedNormal(0.0, 1.0, low=-41.0, high=-40.0, repeat=FRESH)):
        assert all(far.low <= draw(far, 5, trial, ("task", "x")) <= far.high
                   for trial in range(100))
    for share in (0.0, math.nextafter(1.0, 0.0)):
        monkeypatch.setattr(variation, "unit", lambda *key, share=share: share)
        for distribution, declared, bounds in cases:
            value = draw(distribution, 5, 0, ("task", "x"), declared=declared)
            if bounds is None:
                assert value in values_of(distribution)
            else:
                assert bounds[0] <= value <= bounds[1]
        assert draw(Weighted((0.9, 0.1, 0.5, 0.7), (0, 3, 1, 0)), 5, 0, ("task", "x")) == (
            0.1 if share == 0.0 else 0.5)
        assert draw(Uniform(0.2, 0.4), 5, 0, ("task", "x")) == pytest.approx(
            0.2 if share == 0.0 else 0.4)


def test_a_non_aging_wait_redraws_its_tail_and_its_hazard_rises_as_the_spec_says():
    """The PI, 2026-10-30, Q2, "Draw again": every wait falls between the shortest and the
    longest. Spec §3's numbers, arithmetic of the declared 750-1000-1250 ms wait (call 6): the
    chance per moment 1.16, 1.58, 3.03 and 10.51 times the flat rate at 750, 1000, 1150 and 1225
    ms (the spec rounds the last to 10), and a realized mean of 922 ms. The draws are the
    distribution drawing a long wait again gives: their mean is that realized mean, as is a wait
    drawn again by hand from a plain exponential, and their share up to 1000 ms is the cut
    exponential's."""
    wait = NonAging(750, 1000, 1250, repeat=FRESH)

    assert [round(hazard_ratio(wait, at), 2) for at in (750, 1000, 1150, 1225)] == [
        1.16, 1.58, 3.03, 10.51]
    assert round(realized_mean(wait)) == 922
    assert (hazard_ratio(wait, 700), hazard_ratio(wait, 1250)) == (0.0, math.inf)
    assert realized_mean(NonAging(0.0, 1.0, 60.0)) == pytest.approx(1.0, abs=1e-9)

    drawn = [draw(wait, 11, trial, ("task", "wait")) for trial in range(KEYS)]
    assert all(750 <= value <= 1250 for value in drawn)
    assert statistics.fmean(drawn) == pytest.approx(realized_mean(wait), abs=5)
    share = sum(value <= 1000 for value in drawn) / KEYS
    assert share == pytest.approx((1 - math.exp(-1)) / (1 - math.exp(-2)), abs=0.015)
    by_hand, rng = [], random.Random(3)
    while len(by_hand) < KEYS:
        waited = rng.expovariate(1 / 250)
        if waited <= 500:
            by_hand.append(750 + waited)
    assert statistics.fmean(by_hand) == pytest.approx(realized_mean(wait), abs=5)


def test_a_wait_whose_longest_is_far_past_its_mean_is_computed_never_raising():
    """A wait the load accepts whose longest lies more than about 709 of its time constants past
    its shortest, where e to that power is past a float's range: its tail all but never reaches
    the longest, so it realizes its declared mean, and its hazard is the flat rate until near the
    longest. Computed, never raised (`realized_mean` raised `OverflowError` there; found drafting
    the review report, which shows each wait's averages)."""
    far = NonAging(0.0, 0.001, 1.0, repeat=FRESH)

    assert realized_mean(far) == pytest.approx(0.001)
    assert [realized_mean(NonAging(0.0, 1.0, longest)) for longest in (700.0, 800.0, 1e6)] == (
        pytest.approx([1.0, 1.0, 1.0]))
    assert (hazard_ratio(far, 0.5), hazard_ratio(far, 1.0)) == (pytest.approx(1.0), math.inf)
    drawn = [draw(far, 13, trial, ("task", "wait")) for trial in range(1000)]
    assert all(0.0 <= value <= 1.0 for value in drawn)
    assert statistics.fmean(drawn) == pytest.approx(0.001, abs=0.0002)


def test_a_prepared_list_plays_each_item_once_per_shuffled_pass_or_in_order():
    """Engine build C3's call 7: a list plays in shuffled passes, each item once before any
    again, in a new order each pass, the place its draw's fresh draws have reached (`ordinal`)
    choosing the item, not the trial; with `in_order`, as listed, over and over. Two draws of
    one setting -- the task's and a block's -- hold their own passes, and another seed others."""
    listed = Listed((2, 4, 6, 8), repeat=FRESH)
    key = ("task", "set_size")
    played = [draw(listed, 3, 0, key, ordinal=place) for place in range(40)]
    passes = [tuple(played[at:at + 4]) for at in range(0, 40, 4)]

    assert all(sorted(each) == [2, 4, 6, 8] for each in passes)
    assert len(set(passes)) > 1
    assert [draw(listed, 3, trial, key, ordinal=5) for trial in range(5)] == [played[5]] * 5
    blocks = [draw(listed, 3, 0, ("block", "easy", "set_size"), ordinal=place)
              for place in range(40)]
    assert blocks != played and all(sorted(blocks[at:at + 4]) == [2, 4, 6, 8]
                                     for at in range(0, 40, 4))
    assert [draw(listed, 4, 0, key, ordinal=place) for place in range(40)] != played
    in_order = Listed((2, 4, 6, 8), in_order=True, repeat=SAME)
    assert [draw(in_order, 3, place, key, ordinal=place) for place in range(10)] == [
        2, 4, 6, 8, 2, 4, 6, 8, 2, 4]


def test_a_blocks_draws_in_force_are_its_own_and_the_tasks_it_does_not_replace():
    """The PI, 2026-10-30, Q1a, "Task default, block may replace": a block draws its own draws
    and the task's it does not name, each with its key (call 7); a setting it names
    `BY_CONDITIONS` is its conditions', drawn by neither. A condition's own range (Q1b) is its
    own, keyed by the condition."""
    wait, hold = Uniform(0.8, 1.2, repeat=FRESH), Uniform(0.2, 0.4, repeat=SAME)
    task = _task(draws={"wait": wait, "fix_hold": hold})
    plain = Block("session", [Condition("session", {}, target=10)])
    narrow = NonAging(0.75, 1.0, 1.25, repeat=FRESH)
    dim = Uniform(0.1, 0.5, repeat=FRESH)
    own = Block("own", [], draws={"wait": narrow, "contrast": dim, "fix_hold": BY_CONDITIONS})
    wide = Condition("wide", {"fix_hold": Uniform(0.5, 0.9, repeat=SAME), "contrast": 0.5}, 4)

    assert in_force(task, plain) == {"wait": (wait, ("task", "wait")),
                                     "fix_hold": (hold, ("task", "fix_hold"))}
    assert in_force(task, own) == {"wait": (narrow, ("block", "own", "wait")),
                                   "contrast": (dim, ("block", "own", "contrast"))}
    assert in_force(_task(), own) == {"wait": (narrow, ("block", "own", "wait")),
                                      "contrast": (dim, ("block", "own", "contrast"))}
    assert own_ranges(wide) == {
        "fix_hold": (Uniform(0.5, 0.9, repeat=SAME), ("condition", "wide", "fix_hold"))}
    assert own_ranges(Condition("plain", {"contrast": 0.5}, 4)) == {}
    assert in_force(task, Block("odd", [], draws=[("wait", narrow)])) == in_force(task, plain)


def test_a_factorial_expands_minus_its_exclusions_named_from_its_levels_in_order():
    """TSK-22 ("the framework makes the combinations minus declared exclusions, each named from
    its levels; hand-listed conditions remain possible") and Q4 ("each cell equal", "a
    hand-written number per combination allowed"): every combination, the first factor slowest,
    but those an exclusion holds all the levels of -- so one naming fewer factors excludes a
    slice, and one naming nothing real, or nothing, excludes nothing -- each named in the
    factors' order, after the block's hand-listed conditions, owed `target` or its own number,
    playing the factorial's structure. The declaration itself is untouched."""
    factorial = Factorial(
        {"contrast": (0.1, 0.5), "side": ("left", "right")},
        exclude=({"contrast": 0.1, "side": "left"},),
        target=4,
        targets={"contrast=0.5, side=right": 8},
        structure="probe",
    )
    catch = Condition("catch", {"contrast": 0.0}, target=2)
    block = Block("mixed", [catch], criterion=(0.8, 20), factorial=factorial)
    made = generated(block)

    assert [(c.name, c.values, c.target, c.structure) for c in made] == [
        ("contrast=0.1, side=right", {"contrast": 0.1, "side": "right"}, 4, "probe"),
        ("contrast=0.5, side=left", {"contrast": 0.5, "side": "left"}, 4, "probe"),
        ("contrast=0.5, side=right", {"contrast": 0.5, "side": "right"}, 8, "probe"),
    ]
    whole = expanded(block)
    assert whole.conditions == [catch, *made] and whole.factorial is None
    assert dataclasses.replace(whole, conditions=[catch], factorial=factorial) == block
    assert block.conditions == [catch] and block.factorial is factorial

    def names(**fields) -> list[str]:
        two = {"contrast": (0.1, 0.5), "side": ("left", "right")}
        return [c.name for c in generated(Block("b", [], factorial=Factorial(two, **fields)))]

    assert names(exclude=({"side": "left"},)) == [
        "contrast=0.1, side=right", "contrast=0.5, side=right"]
    assert names(exclude=({"size": 3},)) == names(exclude=({},)) == names() == [
        "contrast=0.1, side=left", "contrast=0.1, side=right",
        "contrast=0.5, side=left", "contrast=0.5, side=right"]
    three = Factorial({"a": (1, 2), "b": ("x",), "c": (True, False)})
    assert [c.name for c in generated(Block("b", [], factorial=three))] == [
        "a=1, b=x, c=True", "a=1, b=x, c=False", "a=2, b=x, c=True", "a=2, b=x, c=False"]
    ranged = Factorial({"fix_hold": (0.3, Uniform(0.5, 0.9, repeat=SAME))})
    assert [(c.name, c.values) for c in generated(Block("b", [], factorial=ranged))] == [
        ("fix_hold=0.3", {"fix_hold": 0.3}),
        ("fix_hold=uniform from 0.5 to 0.9", {"fix_hold": Uniform(0.5, 0.9, repeat=SAME)}),
    ]
    plain = Block("plain", [catch])
    assert expanded(plain) is plain and generated(plain) == []
    assert generated(Block("b", [], factorial=Factorial({}))) == []


def test_a_level_is_named_exactly_a_position_eccentricity_and_direction_first():
    """Engine build C3's call 14: a number by its shortest exact form, text as written, a position
    eccentricity first with its direction from 0 to 360 and none at eccentricity 0 (the PI,
    2026-10-30, "0 to 360 in both repos", "Empty at center"), an (x, y) pair as one, a range of
    its own in the rig's words, anything else by its `repr`, which the load refuses where it
    holds an address. Names are what wl-preproc groups trials by."""
    assert [level_name(level) for level in (0.1, 3, 1e-05, 0.30000000000000004, "left")] == [
        "0.1", "3", "1e-05", "0.30000000000000004", "left"]
    assert level_name(Polar(8, -90)) == "8° at 270°"
    assert level_name(Polar(8.0, 45.0)) == "8.0° at 45.0°"
    assert level_name(Polar(12.5, 360)) == "12.5° at 0°"
    assert level_name(Polar(0, 45)) == "0°"
    assert level_name((1.5, -2)) == level_name([1.5, -2]) == "(1.5, -2)"
    assert level_name(Uniform(0.5, 0.9, repeat=SAME)) == "uniform from 0.5 to 0.9"
    assert level_name(Disc(size=1.0)) == repr(Disc(size=1.0))
    assert level_name(Polar(P("ecc"), 45)) == repr(Polar(P("ecc"), 45))
    assert level_name(True) == "True"
    assert " at 0x" in level_name(object())
    block = Block("b", [], factorial=Factorial(
        {"target_pos": (Polar(8, -90), (1.5, -2)), "contrast": (0.1,)}))
    assert [c.name for c in generated(block)] == [
        "target_pos=8° at 270°, contrast=0.1", "target_pos=(1.5, -2), contrast=0.1"]


def test_a_linear_de_bruijn_sequence_holds_every_tuple_once_a_cycle_and_replays_from_its_seed():
    """TSK-23 [@aguirre2011de; @brooks2012counterbalancing], Q5a ("Block picks; pairs default")
    and the PI's answer of 2026-10-31 on the engine C3 plan's Appendix B, item 1 ("Add one closing
    trial (Recommended)"): each cycle is the linear de Bruijn sequence, `n**depth + depth - 1`
    trials, in which each run of `depth` conditions, a condition after itself included, follows
    exactly once -- every pair of 4 conditions in 17 trials, every triple in 66. It is a de Bruijn
    cycle, each condition `n**(depth - 1)` times, with its first `depth - 1` conditions played again
    at its end, so those first trials are a lead-in that only precedes what follows. Played
    `cycles` times over, each cycle holds every pair once. One seed, one sequence: a block that
    opens again draws a new one from its own occurrence."""
    for depth, sizes in ((2, (2, 3, 4, 5)), (3, (2, 3, 4))):
        for count in sizes:
            names = [f"c{index}" for index in range(count)]
            for occurrence in range(25):
                played = balanced_sequence(names, depth, 1,
                                           random.Random(f"design:7:{occurrence}"))
                assert len(played) == count ** depth + depth - 1
                assert played[count ** depth:] == played[:depth - 1]
                cycle = played[:count ** depth]
                assert collections.Counter(cycle) == {n: count ** (depth - 1) for n in names}
                runs = collections.Counter(played[at:at + depth] for at in range(count ** depth))
                assert len(runs) == count ** depth and set(runs.values()) == {1}

    names = ["a", "b", "c", "d"]
    once = balanced_sequence(names, 2, 1, random.Random("design:7:0"))
    twice = balanced_sequence(names, 2, 2, random.Random("design:7:0"))
    assert len(once) == 17 and twice == once * 2
    for cycle in (twice[:17], twice[17:]):
        pairs = collections.Counter(zip(cycle, cycle[1:]))
        assert len(pairs) == 16 and set(pairs.values()) == {1}
    assert len(balanced_sequence(names, 3, 1, random.Random("design:7:0"))) == 66
    assert balanced_sequence(names, 2, 1, random.Random("design:7:0")) == once
    assert len({balanced_sequence(names, 2, 1, random.Random(f"design:7:{n}"))
                for n in range(10)}) > 1
    assert sorted(balanced_sequence(names, 1, 1, random.Random("design:7:0"))) == names
    assert [balanced_sequence(given, depth, cycles, random.Random(0)) for given, depth, cycles in
            ((names, 0, 1), (names, 2, 0), ([], 2, 1))] == [(), (), ()]


def test_easier_reads_a_meaning_both_ways_and_says_when_it_cannot():
    """Engine build C3's call 18, from each setting's declared meaning (TRN-03, TRN-11): raising
    a number, or moving it from a number or another setting, moves the task as `raising` says,
    for a clear-cut and an expected setting alike; a changed choice by `raising` alone; a setting
    no difficulty setting is never easier. **Where the direction cannot be read -- against the
    background, a choice against a reference, no value to compare, a reference that is no
    number -- it says so (`None`)**, and the animal is never moved up on doubt. A setting whose
    values are its choices is read as a choice, numbers or not, as the review report reads it."""
    window, hold = COMMON["fix_window"], COMMON["fix_hold"]
    away = Meaning(CLEAR_CUT, STIMULUS, raising=HARDER, relative_to=0.0)
    beside = Meaning(CLEAR_CUT, STIMULUS, raising=EASIER, relative_to="distractor_contrast")
    choice = Meaning(CLEAR_CUT, STIMULUS, raising=EASIER)
    hard_choice = Meaning(CLEAR_CUT, STIMULUS, raising=HARDER)
    expected = Meaning(EXPECTED, CRITERION, raising=EASIER, note="a wider window may also land")

    assert [easier(window, 3.0, 2.0), easier(window, 1.0, 2.0), easier(window, 2.0, 2)] == [
        True, False, False]
    assert [easier(hold, 0.2, 0.3), easier(hold, 0.4, 0.3)] == [True, False]
    assert [easier(expected, 3.0, 2.0), easier(expected, 1.0, 2.0)] == [True, False]
    assert [easier(away, 2.0, 4.0), easier(away, -6.0, 4.0), easier(away, -4.0, 4.0)] == [
        True, False, False]
    assert [easier(beside, 0.9, 0.6, 0.5), easier(beside, 0.1, 0.6, 0.5),
            easier(beside, 0.6, 0.4, 0.5)] == [True, True, False]
    assert [easier(beside, 0.9, 0.6), easier(beside, 0.9, 0.6, "dim")] == [None, None]
    assert easier(COMMON["fix_luminance"], 40.0, 20.0, 0.0) is None
    assert [easier(choice, "red", "green"), easier(hard_choice, "red", "green"),
            easier(hard_choice, "green", "red"), easier(choice, "red", "red")] == [
        True, False, False, False]
    assert [easier(choice, 4, 8, choices=True), easier(hard_choice, 8, 4, choices=True),
            easier(choice, 4, 8)] == [True, False, False]
    assert [easier(away, "red", "green"), easier(away, 4, 8, choices=True)] == [None, None]
    assert [easier(window, 3.0, None), easier(window, None, 2.0)] == [None, None]
    assert [easier(window, math.nan, 2.0), easier(window, math.inf, 2.0)] == [None, None]
    assert [easier(COMMON["target_x"], 4.0, 0.0), easier(COMMON["set_size"], 8, 4)] == [
        False, False]


def test_the_settings_a_polar_reads_as_its_direction_are_found():
    """Engine build C3's call 11: a drawn direction is written from 0 to 360, so the rig must
    know which settings place one -- each a `Polar`'s direction anywhere in any structure: a
    stimulus, an eye of one, an `Update`, a window. An eccentricity is none, nor a direction
    written as a number. No reference task places a position by a setting's direction."""
    look = Trial(
        start="on",
        params=[Param("ecc", unit="deg", low=0.0, high=20.0, start=8.0),
                Param("dir", unit="deg", low=0.0, high=360.0, start=45.0),
                Param("turn", unit="deg", low=0.0, high=360.0, start=90.0)],
        windows=[Window("w", at=Polar(P("ecc"), P("dir")), radius=2.0, on="s")],
        states=[State("on", enter=[Show(Stimulus("s", at=Polar(P("ecc"), P("dir"))))],
                      go=[On(After(0.5), "moved")]),
                State("moved", enter=[Update("s", at=Polar(8.0, P("turn")))],
                      go=[On(After(1.0), Outcome.CORRECT)])],
    )
    probe = Trial(
        start="on",
        params=[Param("left_dir", unit="deg", low=0.0, high=360.0, start=10.0)],
        states=[State("on", enter=[Show(Stimulus("p", at=Polar(P("ecc"), 30.0),
                                                 at_left=Polar(4.0, P("left_dir"))))],
                      go=[On(After(1.0), Outcome.CORRECT)])],
    )

    assert directions(Task({"look": look, "probe": probe}, default="look")) == frozenset(
        {"dir", "turn", "left_dir"})
    assert directions(Task({"probe": probe}, default="probe")) == frozenset({"left_dir"})
    for name in ("fixation_detection", "adaptive_detection", "visual_search",
                 "visual_search_training", "calibration"):
        assert directions(_load_task(ROOT / "tasks" / f"{name}.py")) == frozenset()


def test_a_draw_is_recorded_with_every_field_a_normal_with_its_cut_a_direction_normalized():
    """Engine build C3's calls 11 and 12 (controller rulings 1 and 2): a draw is written with
    every field, its defaults included, so the record is read without this build's defaults; a
    normal's cut filled end by end from its setting's declared range where it gives none; a
    direction's places from 0 to 360, so a range declared -45 to 45 is written 315 to 45,
    crossing rightward. Plain data, as JSON writes it."""
    assert recorded(Uniform(-45, 45, repeat=FRESH), direction=True) == {
        "class": "Uniform", "fields": {"low": 315, "high": 45, "repeat": "fresh"}}
    assert recorded(Uniform(-45, 45, repeat=FRESH)) == {
        "class": "Uniform", "fields": {"low": -45, "high": 45, "repeat": "fresh"}}
    assert recorded(TruncatedNormal(1.0, 0.1, repeat=SAME), HOLD) == {
        "class": "TruncatedNormal",
        "fields": {"mean": 1.0, "sd": 0.1, "low": 0.05, "high": 2.0, "repeat": "same"}}
    assert recorded(TruncatedNormal(1.0, 0.1, low=0.9, repeat=SAME), HOLD)["fields"] == {
        "mean": 1.0, "sd": 0.1, "low": 0.9, "high": 2.0, "repeat": "same"}
    assert recorded(TruncatedNormal(1.0, 0.1))["fields"] == {
        "mean": 1.0, "sd": 0.1, "low": None, "high": None, "repeat": None}
    turned = Param("dir", unit="deg", low=-90.0, high=90.0)
    assert recorded(TruncatedNormal(-30, 10, repeat=SAME), turned, direction=True)["fields"] == {
        "mean": 330, "sd": 10, "low": 270.0, "high": 90.0, "repeat": "same"}
    assert recorded(Listed((-90, 0, 90), repeat=FRESH), direction=True) == {
        "class": "Listed", "fields": {"values": [270, 0, 90], "in_order": False,
                                      "repeat": "fresh"}}
    assert recorded(Weighted((0.1, 0.5), (3, 1))) == {
        "class": "Weighted", "fields": {"values": [0.1, 0.5], "weights": [3, 1], "repeat": None}}
    wait = recorded(NonAging(-10, 0, 10, repeat=FRESH), direction=True)
    assert wait["fields"] == {"minimum": 350, "mean": 0, "maximum": 10, "repeat": "fresh"}
    assert json.loads(json.dumps(wait)) == wait


def test_a_draw_is_said_in_the_rigs_words():
    """What the console's card and a staged change say of a draw, and a range level's name: each
    number with its unit, a direction's places from 0 to 360, a normal without a cut of its own
    cut to its setting's range, a list's passes said."""
    assert words(Uniform(0.2, 0.4, repeat=FRESH), "s") == "uniform from 0.2 s to 0.4 s"
    assert words(Uniform(-45, 45), "deg", direction=True) == "uniform from 315 deg to 45 deg"
    assert words(Uniform(-45, 45), "deg") == "uniform from -45 deg to 45 deg"
    assert words(Weighted((0.1, 0.5), (3, 1)), "s") == "one of 0.1 s, 0.5 s, weighted 3:1"
    assert words(Weighted((Polar(8, -90), (1.5, -2)), (1, 1)), "position") == (
        "one of 8° at 270°, (1.5, -2), weighted 1:1")
    normal = "normal of mean 1.0 s and sd 0.1 s, "
    assert words(TruncatedNormal(1.0, 0.1, low=0.9, high=1.1), "s") == (
        normal + "cut from 0.9 s to 1.1 s")
    assert words(TruncatedNormal(1.0, 0.1), "s") == normal + "cut to the setting's range"
    assert words(TruncatedNormal(1.0, 0.1, high=1.1), "s") == (
        normal + "cut from the setting's lowest to 1.1 s")
    assert words(TruncatedNormal(1.0, 0.1, low=0.9), "s") == (
        normal + "cut from 0.9 s to the setting's highest")
    assert words(TruncatedNormal(-30, 10, low=-90, high=0), "deg", direction=True) == (
        "normal of mean 330 deg and sd 10 deg, cut from 270 deg to 0 deg")
    assert words(Listed((2, 4, 6), repeat=FRESH), "objects") == (
        "each of 2 objects, 4 objects, 6 objects once a pass, shuffled")
    assert words(Listed((2, 4, 6), in_order=True), "") == "in order: 2, 4, 6, over and over"
    assert words(Listed(("red", "green")), "appearance") == (
        "each of red, green once a pass, shuffled")
    assert words(NonAging(0.75, 1.0, 1.25), "s") == "non-aging from 0.75 s to 1.25 s, mean 1.0 s"
    assert words(Distribution(), "s") == "Distribution()"


def test_only_a_uniform_a_normal_and_a_waits_numbers_change_live():
    """The PI, 2026-10-30, Q7b ("Yes, range changes live"; the spec's §6: "a uniform's ends; a
    wait's shortest, average and longest") and engine build C3's call 22: a uniform's ends, a
    normal's numbers and cut, a wait's three; the kind and what a repeat takes never; a weighted
    set's and a list's not in this build. A name that is not one of a kind's live numbers is
    refused, saying which are."""
    assert LIVE_NUMBERS == {Uniform: ("low", "high"),
                            TruncatedNormal: ("mean", "sd", "low", "high"),
                            NonAging: ("minimum", "mean", "maximum")}
    assert numbers(Uniform(0.2, 0.4, repeat=FRESH)) == {"low": 0.2, "high": 0.4}
    assert numbers(TruncatedNormal(1.0, 0.1)) == {"mean": 1.0, "sd": 0.1}
    assert numbers(TruncatedNormal(1.0, 0.1, low=0.9, high=1.1)) == {
        "mean": 1.0, "sd": 0.1, "low": 0.9, "high": 1.1}
    assert numbers(NonAging(0.75, 1.0, 1.25)) == {"minimum": 0.75, "mean": 1.0, "maximum": 1.25}
    assert [numbers(Weighted((1, 2), (1, 1))), numbers(Listed((1, 2)))] == [None, None]

    assert with_numbers(Uniform(0.2, 0.4, repeat=FRESH), {"high": 0.6}) == Uniform(
        0.2, 0.6, repeat=FRESH)
    assert with_numbers(TruncatedNormal(1.0, 0.1, repeat=SAME), {"low": 0.9, "sd": 0.2}) == (
        TruncatedNormal(1.0, 0.2, low=0.9, repeat=SAME))
    assert with_numbers(NonAging(0.75, 1.0, 1.25), {}) == NonAging(0.75, 1.0, 1.25)
    with pytest.raises(ValueError, match=r"'mean' is not a number of a Uniform changed live; "
                                         r"its live numbers are low, high"):
        with_numbers(Uniform(0.2, 0.4), {"mean": 0.3})
    with pytest.raises(ValueError, match="'repeat' is not a number of a NonAging"):
        with_numbers(NonAging(0.75, 1.0, 1.25, repeat=SAME), {"repeat": FRESH})
    with pytest.raises(ValueError, match="a Weighted's numbers are not changed live"):
        with_numbers(Weighted((1, 2), (1, 1)), {"values": (1, 3)})
    with pytest.raises(ValueError, match="a Listed's numbers are not changed live"):
        with_numbers(Listed((1, 2)), {})


def test_a_weighted_set_whose_weights_overflow_or_hold_a_subnormal_draws_one_of_its_values():
    """The C3 plan's engineering review, M-2: weights summing past a float (1e308 twice) or one too
    small to add (5e-324) once made the place found run past the values, faulting the session at
    its first draw. The load refuses both (`check.undrawable`); the draw is held to its last
    value of weight above 0, so it never raises between trials."""
    huge = Weighted((0.2, 0.3), (1e308, 1e308), repeat=FRESH)
    tiny = Weighted((0.2,), (5e-324,), repeat=FRESH)
    assert {draw(huge, 7, trial, ("task", "fix_hold")) for trial in range(200)} <= {0.2, 0.3}
    assert {draw(tiny, 7, trial, ("task", "fix_hold")) for trial in range(200)} == {0.2}


def test_a_priming_runs_length_is_its_draw_rounded_down_and_at_least_one():
    """The C3 plan's science review, I-8: a priming block's runs may be drawn by any of the five
    distributions, each length its draw rounded down, at least 1."""
    assert [run_length(Uniform(3.0, 8.0), share) for share in (0.0, 0.5, 0.999)] == [3, 5, 7]
    assert [run_length(Weighted((2, 5), (1, 1)), share) for share in (0.25, 0.75)] == [2, 5]
    assert run_length(NonAging(0.5, 1.0, 4.0), 0.0) == 1
    assert run_length(TruncatedNormal(5.0, 1.0, low=3.0, high=8.0), 0.5) == 5


def test_a_runs_switch_chance_at_each_position_rises_when_even_and_holds_when_non_aging():
    """The C3 plan's science review, I-8: with lengths drawn evenly from 3 to 7, a run that has
    shown k trials switches next with chance 0, 0, 1/5, 1/4, 1/3, 1/2 and 1 -- a switch ever more
    expected along the run, which is the variable priming studies; non-aging lengths (the
    truncated exponential, rounded down) keep it near 1 - e^(-1/τ) until the cut."""
    even = switch_chances((3, 7))
    assert [length for length, _ in even] == [1, 2, 3, 4, 5, 6, 7]
    assert [chance for _, chance in even] == pytest.approx([0, 0, 1 / 5, 1 / 4, 1 / 3, 1 / 2, 1])
    assert switch_chances(Weighted((2, 4), (3, 1))) == ((1, 0.0), (2, 0.75), (3, 0.0), (4, 1.0))
    flat = switch_chances(NonAging(3.0, 5.0, 12.0))

    def expected(length: int) -> float:
        start = (length - 3) / 2
        return ((math.exp(-start) - math.exp(-start - 0.5))
                / (math.exp(-start) - math.exp(-4.5)))

    assert [length for length, _ in flat] == list(range(1, 12))
    assert [chance for _, chance in flat[:2]] == [0.0, 0.0]
    assert [chance for _, chance in flat[2:10]] == pytest.approx(
        [expected(length) for length in range(3, 11)])
    assert flat[-1] == (11, 1.0)
    assert all(0.39 < chance < 0.42 for _, chance in flat[2:6])
