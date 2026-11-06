"""What varies, in the review report (engine build C3; its spec §3-§5): the task's draws and each
block's, a condition's own range, the conditions a block makes from factors with the exclusions
applied and each level's share, a designed order in words, and each non-aging wait's hazard against
the flat rate with its declared and realized averages. A task is approved from this report, not
from its source (ADR-0006), and nobody writes a generated condition, so nobody reads one unless it
is shown (pitfall P20)."""

from __future__ import annotations

import math

import pytest

from wl_xcon import review, variation
from wl_xcon.review import render_task
from wl_xcon.task import (
    BY_CONDITIONS,
    FRESH,
    SAME,
    After,
    Block,
    Condition,
    Factorial,
    NonAging,
    On,
    Outcome,
    P,
    Param,
    Plan,
    Polar,
    Priming,
    SaccadeTo,
    SequenceBalanced,
    State,
    Task,
    Trial,
    Uniform,
    Weighted,
    Window,
)

LOOK = Trial(
    start="wait",
    params=[
        Param("wait", unit="s", low=0.5, high=3.0, start=1.0),
        Param("contrast", unit="fraction", low=0.0, high=1.0, start=0.5),
        Param("side", unit="side", choices=("left", "right")),
        Param("ecc", unit="deg", low=0.0, high=20.0, start=8.0),
        Param("dir", unit="deg", low=0.0, high=360.0, start=45.0),
    ],
    windows=[Window("target", at=Polar(P("ecc"), P("dir")), radius=2.0)],
    states=[
        State("wait", go=[On(After(P("wait")), "look")]),
        State("look", go=[On(SaccadeTo("target"), Outcome.CORRECT),
                          On(After(0.5), Outcome.NO_RESPONSE)]),
    ],
)

#: What `_wait` says of a wait its numbers give no hazard for.
CANNOT = ("**Its hazard cannot be computed**: a non-aging wait's mean must be past its shortest "
          "and at most its longest, each a finite number, which the load-time check refuses "
          "otherwise.")


def _task(**fields) -> Task:
    """One structure, `look`: a wait, a contrast, a side, and a target placed by eccentricity and
    direction, so `dir` is a direction setting (`variation.directions`)."""
    return Task({"look": LOOK}, default="look", **fields)


def test_the_review_lists_the_tasks_draws_and_each_blocks():
    """The PI, 2026-10-30, Q1a ("Task default, block may replace") and Q1b ("a condition may draw
    its own setting from its own range"): the report lists the task's draws, the plain run's, in
    the rig's words with what a repeat takes (Q3), a direction from 0 to 360 as the rig writes it
    (engine build C3's call 11); then each block's -- its own, the task's it does not replace, a
    setting it leaves to its conditions -- and a condition's own range among its values. A value a
    condition gives is shown as given. A task drawing nothing says so, and a plan whose blocks draw
    nothing has no table of draws."""
    task = _task(
        draws={"wait": NonAging(0.75, 1.0, 1.25, repeat=FRESH),
               "dir": Uniform(-45, 45, repeat=SAME)},
        plans={"p": Plan([
            Block("plain", [Condition("near", {"contrast": 0.9}, target=4)]),
            Block("long", [Condition("far", {"side": "right"}, target=4)],
                  draws={"wait": NonAging(1.0, 1.5, 3.0, repeat=SAME),
                         "contrast": Weighted((0.1, 0.5), (3, 1), repeat=FRESH)}),
            Block("given", [Condition("left", {"dir": 180.0}, target=4),
                            Condition("spread", {"dir": Uniform(-10, 10, repeat=FRESH)},
                                      target=4)],
                  draws={"dir": BY_CONDITIONS}),
        ])},
    )
    out = render_task(task)

    assert "| Setting | Drawn from | On a repeat |" in out
    assert (out.index("### What each trial does to its condition's count") < out.index("### Draws")
            < out.index("### Plans"))
    assert "| wait | non-aging from 0.75 s to 1.25 s, mean 1.0 s | fresh |" in out
    assert "| dir | uniform from 315 deg to 45 deg | same |" in out
    assert "| Block | Setting | Drawn from | Whose | On a repeat |" in out
    assert ("| plain | wait | non-aging from 0.75 s to 1.25 s, mean 1.0 s | the task's | fresh |"
            in out)
    assert "| plain | dir | uniform from 315 deg to 45 deg | the task's | same |" in out
    assert ("| long | wait | non-aging from 1.0 s to 3.0 s, mean 1.5 s | the block's own | same |"
            in out)
    assert ("| long | contrast | one of 0.1 fraction, 0.5 fraction, weighted 3:1 | the block's own "
            "| fresh |") in out
    assert "| long | dir | uniform from 315 deg to 45 deg | the task's | same |" in out
    assert ("| given | wait | non-aging from 0.75 s to 1.25 s, mean 1.0 s | the task's | fresh |"
            in out)
    assert ("| given | dir | each condition's value or own range (above) | by its conditions | |"
            in out)
    assert out.count("| given | dir |") == 1
    assert "| given | left | look | 4 | dir = 180.0 |" in out
    assert ("| given | spread | look | 4 | dir = uniform from 350 deg to 10 deg (fresh on a "
            "repeat) |") in out
    assert "`wait`, the task's draw: non-aging from 0.75 s to 1.25 s, mean 1.0 s." in out
    assert "`wait` in block `long`, its own draw: non-aging from 1.0 s to 3.0 s, mean 1.5 s." in out
    assert "| 2.9 s | 5.52 times |" in out
    assert "Its waits average 1.46 s, below the declared mean of 1.5 s" in out

    plain = render_task(_task(plans={"q": Plan([Block("b", [Condition("c", {}, target=1)])])}))
    assert ("### Draws\n\nNone of the task's own: the plain run draws nothing. A block type's own "
            "draws are in its plan's tables.") in plain
    assert "| Block | Setting |" not in plain


def test_a_factorials_generated_conditions_exclusions_and_level_shares_are_listed():
    """The C3 spec §4 ("Listed for review": "nobody writes generated conditions, so nobody reads
    them unless shown"), TSK-22 and the PI's Q4 ("Yes, each cell equal": "the review report shows
    each level's overall share"): each generated condition in the plan's table after the block's
    hand-listed ones, with its values and target; the factors and levels, the target and each
    hand-written number, the exclusions applied; and each level's share of the trials the
    generated conditions owe, which exclusions and hand-written numbers make unequal. A level may
    be a range of its own (Q1b), its hazard shown once for every condition sharing it; conditions
    that owe nothing, as a priming block's, say so."""
    mixed = Factorial({"contrast": (0.1, 0.5), "side": ("left", "right")},
                      exclude=({"contrast": 0.1, "side": "left"},), target=4,
                      targets={"contrast=0.5, side=right": 8})
    ranges = Factorial({"wait": (NonAging(0.5, 0.75, 1.0, repeat=FRESH),),
                        "side": ("left", "right")}, target=0)
    plans = {"p": Plan([
        Block("mixed", [Condition("catch", {"contrast": 0.0}, target=2)], factorial=mixed),
        Block("ranges", [], factorial=ranges, order=Priming("side", chance=0.5), trials=40),
    ])}
    out = render_task(_task(plans=plans))

    assert ("| mixed | catch | look | 2 | contrast = 0.0 |\n"
            "| mixed | contrast=0.1, side=right | look | 4 | contrast = 0.1, side = right |\n"
            "| mixed | contrast=0.5, side=left | look | 4 | contrast = 0.5, side = left |\n"
            "| mixed | contrast=0.5, side=right | look | 8 | contrast = 0.5, side = right |"
            ) in out
    assert ("Block `mixed` makes 3 conditions from its factors, its last 3 rows in the table of "
            "conditions above: contrast (0.1, 0.5); side (left, right). Each is owed 4 trials, but "
            "`contrast=0.5, side=right` 8. Excluded: `contrast=0.1, side=left`.") in out
    assert ("| Factor | Level | Conditions | Trials owed | Share of trials owed |\n"
            "|---|---|---|---|---|\n"
            "| contrast | 0.1 | 1 | 4 | 25.0% |\n"
            "| contrast | 0.5 | 2 | 12 | 75.0% |\n"
            "| side | left | 1 | 4 | 25.0% |\n"
            "| side | right | 2 | 12 | 75.0% |") in out

    level = "wait=non-aging from 0.5 to 1.0, mean 0.75"
    assert (f"| ranges | {level}, side=left | look | 0 | wait = non-aging from 0.5 s to 1.0 s, "
            f"mean 0.75 s (fresh on a repeat), side = left |") in out
    assert ("Block `ranges` makes 2 conditions from its factors, its last 2 rows in the table of "
            f"conditions above: wait ({level[5:]}); side (left, right). Each is owed 0 trials. "
            "Excluded: none.") in out
    assert f"| wait | {level[5:]} | 2 | 0 | none owed |" in out
    assert (f"`wait` in block `ranges`, the own range of `{level}, side=left`, "
            f"`{level}, side=right`: non-aging from 0.5 s to 1.0 s, mean 0.75 s.") in out
    assert out.count("| 0.5 s, the shortest |") == 1


def test_a_runs_priming_block_shows_its_switch_chance_after_each_trial_of_a_run():
    """The C3 plan's science review, I-8: runs of lengths drawn evenly from 3 to 7 make a switch
    ever more expected along a run -- 0, 0, then 0.2, 0.25, 0.33, 0.5 and certain at 7 -- which a
    non-aging draw of lengths avoids, near 0.4 until its cut; the report shows each, and says a
    distribution of lengths in the rig's words. A block primed by a chance shows none."""
    two = [Condition("l", {"side": "left"}, target=0), Condition("r", {"side": "right"}, target=0)]
    waited = NonAging(3.0, 5.0, 12.0, repeat=FRESH)
    plans = {"p": Plan([
        Block("even", two, order=Priming("side", runs=(3, 7)), trials=200),
        Block("waited", two, order=Priming("side", runs=waited), trials=200),
        Block("chance", two, order=Priming("side", chance=0.7), trials=200),
    ])}
    out = render_task(_task(plans=plans))
    even = out[out.index("Block `even`: the chance its run switches"):]
    assert ("| Shown trials in the run | Chance it switches next |\n|---|---|\n| 1 | 0.00 |\n"
            "| 2 | 0.00 |\n| 3 | 0.20 |\n| 4 | 0.25 |\n| 5 | 0.33 |\n| 6 | 0.50 |\n"
            "| 7 | 1.00 |\n") in even
    flat = out[out.index("Block `waited`: the chance its run switches"):]
    assert "| 3 | 0.40 |\n| 4 | 0.40 |\n| 5 | 0.41 |\n" in flat and "| 11 | 1.00 |" in flat
    assert ("priming on `side`: runs of one value, each its length drawn "
            f"{variation.words(waited, 'shown trials')}, rounded down, then another value at "
            "random") in out
    assert "Block `chance`: the chance its run switches" not in out


def test_a_designed_order_is_said_in_words():
    """The C3 spec §5 and the PI's Q5a ("Block picks; pairs default"), Q5b ("'Again at once' as an
    option") and Q6 ("Both of the last two"): a sequence-balanced block's reach, cycles and break
    rule, and that it ends once its sequence is played out, `(n**depth + depth - 1) * cycles`
    trials, each cycle the linear sequence opening on a lead-in (the PI, 2026-10-31), or its own
    number of trials first (engine build C3's call 15); a priming block's feature, its chance or
    its runs and its break rule, ending on its trials or its time (call 16). Each said apart from
    "shuffled passes", which is what it read before."""
    four = [Condition(name, {"contrast": c}, target=1)
            for name, c in (("a", 0.2), ("b", 0.4), ("c", 0.6), ("d", 0.8))]
    two = [Condition("l", {"side": "left"}, target=0), Condition("r", {"side": "right"}, target=0)]
    plans = {"p": Plan([
        Block("pairs", four, order=SequenceBalanced()),
        Block("triples", [Condition("x", {"contrast": 0.2}, target=8),
                          Condition("y", {"contrast": 0.8}, target=8)],
              order=SequenceBalanced(depth=3, cycles=2, again_at_once=True), trials=12),
        Block("chance", two, order=Priming("side", chance=0.7), trials=200),
        Block("runs", two, order=Priming("side", runs=(3, 7), again_at_once=True),
              time_limit_s=300.0),
    ])}
    out = render_task(_task(plans=plans))
    tail = "| each condition's structure's table | no |"

    assert ("| pairs | its sequence is played out, 17 trials | sequence-balanced from the run's "
            "seed: each cycle a linear de Bruijn sequence, each ordered pair of conditions, a "
            "condition after itself included, once a cycle, its first trial a lead-in that only "
            "precedes what follows; 1 cycle; a broken trial is not repeated, its place a designed "
            "shortfall " + tail) in out
    assert ("| triples | its sequence is played out, 20 trials; or 12 trials run | "
            "sequence-balanced from the run's seed: each cycle a linear de Bruijn sequence, each "
            "ordered triple of conditions, a condition after itself included, once a cycle, its "
            "first 2 trials a lead-in that only precedes what follows; 2 cycles; a broken trial "
            "comes back at once, under the repeat limit " + tail) in out
    assert ("| chance | 200 trials run | priming on `side`: the next trial repeats the last shown "
            "trial's value with a chance of 0.7, else another value at random; within a value, "
            "its conditions in shuffled passes; a broken trial is not repeated " + tail) in out
    assert ("| runs | its time runs out at 5 minutes | priming on `side`: runs of one value, each "
            "3 to 7 shown trials long, drawn, then another value at random; within a value, its "
            "conditions in shuffled passes; a broken trial comes back at once, under the repeat "
            "limit " + tail) in out
    assert "each ordered run of 4 conditions" in review._block_order(SequenceBalanced(depth=4))
    assert "shuffled passes |" not in out


def test_a_non_aging_wait_shows_its_hazard_rise_and_both_averages():
    """The PI, 2026-10-30, Q2 ("Draw again": "the review report shows how much the target's chance
    rises near the longest") and engine build C3's call 6: the chance of the wait ending at each
    moment, against the flat rate, at the shortest, the mean and two points nearing the longest,
    and both averages, the declared mean being the wait's own before its tail is drawn again. The
    spec's example, 750 to 1250 ms with a mean of 1000, **pinned in the report's own format**: two
    decimal places, so 1.16, 1.58, 3.03 and 10.51 times, which the spec's §3 rounds to 1.2, 1.6,
    3 and 10 (review M-20: its "10" rounds 10.51 down); the realized average to three significant
    figures, 922 ms. Arithmetic of the declared distribution, said so: no timing claim."""
    assert review._wait(NonAging(750, 1000, 1250, repeat=FRESH), "ms") == [
        "| At | Chance per moment, against the flat rate |",
        "|---|---|",
        "| 750 ms, the shortest | 1.16 times |",
        "| 1000 ms, the mean | 1.58 times |",
        "| 1150 ms | 3.03 times |",
        "| 1225 ms | 10.51 times |",
        "",
        "A wait drawn past the longest, 1250 ms, is drawn again, so the chance rises toward it. "
        "Its waits average 922 ms, below the declared mean of 1000 ms, which is the wait's own "
        "before its tail is drawn again. These describe the declared distribution, not the rig.",
        "",
    ]
    out = render_task(_task(draws={"wait": NonAging(0.75, 1.0, 1.25, repeat=FRESH)}))
    assert ("| 0.75 s, the shortest | 1.16 times |\n| 1 s, the mean | 1.58 times |\n"
            "| 1.15 s | 3.03 times |\n| 1.225 s | 10.51 times |") in out
    assert "Its waits average 0.922 s, below the declared mean of 1 s" in out
    assert review._wait(NonAging(750, 1000, 1250, repeat=FRESH), "")[2] == (
        "| 750, the shortest | 1.16 times |")

    # A mean past four fifths of the way is listed in its place; a mean at the longest, where
    # every wait not ended before ends, says so.
    assert review._wait(NonAging(0.0, 0.9, 1.0, repeat=SAME), "s")[2:6] == [
        "| 0 s, the shortest | 1.49 times |", "| 0.8 s | 5.02 times |",
        "| 0.9 s, the mean | 9.51 times |", "| 0.95 s | 18.50 times |"]
    assert "| 1 s, the mean | every wait not ended before ends here |" in review._wait(
        NonAging(0.5, 1.0, 1.0, repeat=SAME), "s")


def test_the_report_computes_a_far_tail_and_says_what_the_load_refuses_never_raising():
    """`wlx review` checks nothing first, and a report that raises shows nothing at all. A wait
    whose longest is far past its mean -- e to the power (longest - shortest) / (mean - shortest)
    past a float's range -- is a wait the load accepts, and its realized mean is computed (Task
    3's `variation.realized_mean`, written so it cannot overflow). What the load refuses is said: a
    wait whose numbers give no hazard; a draw not saying what a repeat takes; a draw of, or a
    condition's value for, a setting nothing declares; a block's draw that is no draw, or draws
    that are not a dict; a priming block with both a chance and runs and no end; a factorial
    whose factors, levels, exclusions or own numbers are not of their shape, or whose target is
    not a whole number."""
    assert variation.realized_mean(NonAging(0.0, 0.001, 1.0)) == pytest.approx(0.001)
    far = review._wait(NonAging(0.0, 0.001, 1.0, repeat=FRESH), "s")
    assert "Its waits average 0.001 s, below the declared mean of 0.001 s" in far[-2]
    for wait in (NonAging(1.0, 1.0, 2.0), NonAging(1.0, 3.0, 2.0), NonAging(1.0, math.inf, 2.0),
                 NonAging(1.0, "1.5", 2.0), NonAging(True, 1.5, 2.0)):
        assert review._wait(wait, "s") == [CANNOT, ""]

    task = _task(
        draws={"wait": NonAging(1.0, 1.0, 2.0), "speed": Uniform(1, 2, repeat=SAME)},
        plans={"p": Plan([
            Block("odd", [Condition("l", {"side": "left", "speed": 2}, target=0)],
                  order=Priming("side", chance=0.5, runs=(2, 4)),
                  draws={"contrast": "by condition"}),
            Block("bare", [], draws=("wait",), factorial=Factorial(
                [("contrast", (0.1,))], exclude=("contrast",), targets=[("contrast=0.1", 2)])),
            Block("flat", [], factorial=Factorial({"contrast": (0.1, 0.5), "side": "left"})),
            Block("whole", [], factorial=Factorial({"contrast": (0.1,)}, target=True)),
        ])},
    )
    out = render_task(task)

    assert "| wait | non-aging from 1.0 s to 2.0 s, mean 1.0 s | **not declared** |" in out
    assert "| speed **UNDECLARED** | uniform from 1 to 2 | same |" in out
    assert CANNOT in out
    assert ("| odd | **nothing declared**, which the load-time check refuses | priming on `side`: "
            "**a chance or runs, exactly one**, which the load-time check refuses otherwise;"
            ) in out
    assert "| odd | l | look | 0 | side = left, speed = 2 |" in out
    assert "| odd | contrast | **not a draw**: 'by condition' | | |" in out
    assert "| bare | wait | non-aging from 1.0 s to 2.0 s, mean 1.0 s | the task's |" in out
    assert ("Block `bare` makes 0 conditions from its factors, its last 0 rows in the table of "
            "conditions above: **no factors**. Each is owed 1 trials. Excluded: none.") in out
    assert ("Block `flat` makes 0 conditions from its factors, its last 0 rows in the table of "
            "conditions above: contrast (0.1, 0.5); side (). Each is owed 1 trials.") in out
    assert "| contrast | 0.5 | 0 | 0 | none owed |" in out
    assert "| whole | contrast=0.1 | look | True | contrast = 0.1 |" in out
    assert "| contrast | 0.1 | 1 | 0 | none owed |" in out
