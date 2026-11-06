"""The variation vocabulary in the task object (engine build C3; its spec §2-§5): the five
distributions a setting is drawn from, each saying what a repeat of its trial takes; where a task
and a block type declare their draws; the conditions a block makes from factors; and the two
designed orders of a block's conditions. Declarations only: what they declare is judged at load
(`check.check_task`) and played between trials, never here."""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from wl_xcon.cli import _load_task
from wl_xcon.declarations import canonical, content_hash
from wl_xcon.task import (
    BY_CONDITIONS,
    FOUND_BY,
    FRESH,
    OWED,
    REPEATS,
    SAME,
    After,
    Array,
    Block,
    BlockOrder,
    Condition,
    Counting,
    Distribution,
    Factorial,
    Listed,
    NonAging,
    On,
    Order,
    Outcome,
    P,
    Param,
    Plan,
    Priming,
    SequenceBalanced,
    Shuffled,
    State,
    Task,
    Trial,
    TruncatedNormal,
    Uniform,
    Weighted,
)

ROOT = Path(__file__).resolve().parents[1]
HOLD = Param("fix_hold", unit="s", low=0.05, high=2.0, start=0.3)
WAIT = Param("wait", unit="s", low=0.5, high=1.5, start=1.0)
CONTRAST = Param("contrast", unit="fraction", low=0.02, high=1.0, start=0.5)


def _task(**fields) -> Task:
    """One structure declaring a hold, a wait and a contrast; its draws and plans as given."""
    trial = Trial(
        start="wait",
        params=[HOLD, WAIT, CONTRAST],
        states=[State("wait", go=[On(After(P("wait")), Outcome.CORRECT)])],
        counting=Counting(after_stimulus=OWED, appears="wait"),
    )
    return Task({"wait": trial}, default="wait", **fields)


def test_the_five_distributions_carry_their_numbers_and_what_a_repeat_takes():
    """The PI's five (TSK-24), frozen, each closing with `repeat`: `SAME` or `FRESH` on a repeat of
    its trial (the PI, 2026-10-30, Q3, "Per drawn setting, required"), `None` until the author
    says, which the load refuses. **Not refused as built** (call 2): a draw that cannot be drawn
    is a finding at load with a sentence, never a task file that will not import."""
    drawn = {
        Uniform: (Uniform(0.2, 0.4), ("low", "high", "repeat")),
        Weighted: (Weighted((0.1, 0.5), (3, 1)), ("values", "weights", "repeat")),
        TruncatedNormal: (TruncatedNormal(1.0, 0.1), ("mean", "sd", "low", "high", "repeat")),
        Listed: (Listed((2, 4, 6)), ("values", "in_order", "repeat")),
        NonAging: (NonAging(0.75, 1.0, 1.25), ("minimum", "mean", "maximum", "repeat")),
    }

    assert dataclasses.fields(Distribution) == ()
    for kind, (distribution, names) in drawn.items():
        assert type(distribution) is kind and isinstance(distribution, Distribution)
        assert tuple(spec.name for spec in dataclasses.fields(kind)) == names
        assert distribution.repeat is None
        with pytest.raises(dataclasses.FrozenInstanceError):
            distribution.repeat = SAME
    assert (SAME, FRESH, REPEATS) == ("same", "fresh", ("same", "fresh"))
    assert (TruncatedNormal(1.0, 0.1).low, TruncatedNormal(1.0, 0.1).high) == (None, None)
    assert Listed((2, 4, 6)).in_order is False
    assert Uniform(0.2, 0.4, repeat=FRESH).repeat == FRESH
    assert NonAging(minimum=0.75, mean=1.0, maximum=1.25, repeat=SAME) == NonAging(
        0.75, 1.0, 1.25, SAME)
    assert Uniform(0.4, 0.2).low == 0.4 and Weighted((0.1,), (0, 0)).weights == (0, 0)


def test_a_task_and_a_block_declare_draws_and_a_block_a_factorial():
    """Where a draw is written (the PI, 2026-10-30, Q1a, "Task default, block may replace"): the
    task's `draws`, the plain run included, which a block type's own `draws` replaces or, for a
    setting its conditions give, marks `BY_CONDITIONS`; a condition may draw its own setting from
    its own range (Q1b). A block may make conditions from factors (TSK-22), a level a value of its
    setting or its own range. Every new field closes its class, at a default."""
    wait = NonAging(0.75, 1.0, 1.25, repeat=FRESH)
    own = Condition("wide", {"fix_hold": Uniform(0.5, 0.9, repeat=SAME)}, target=5)
    factorial = Factorial(
        {"contrast": (0.1, 0.5), "fix_hold": (0.3, TruncatedNormal(0.6, 0.1, repeat=SAME))},
        exclude=({"contrast": 0.1, "fix_hold": 0.3},),
        target=4,
        targets={"contrast=0.5, fix_hold=0.3": 8},
        structure="wait",
    )
    block = Block("mixed", [own], draws={"wait": wait, "fix_hold": BY_CONDITIONS},
                  factorial=factorial)
    task = _task(draws={"wait": Uniform(0.8, 1.2, repeat=FRESH)}, plans={"one": Plan([block])})

    assert task.draws == {"wait": Uniform(0.8, 1.2, repeat=FRESH)}
    assert task.plans["one"].blocks[0].draws == {"wait": wait, "fix_hold": BY_CONDITIONS}
    assert task.plans["one"].blocks[0].factorial is factorial
    assert own.values["fix_hold"] == Uniform(0.5, 0.9, repeat=SAME)
    assert BY_CONDITIONS == "by conditions"
    assert [spec.name for spec in dataclasses.fields(Factorial)] == [
        "factors", "exclude", "target", "targets", "structure"]
    assert Factorial({"contrast": (0.1, 0.5)}) == Factorial(
        {"contrast": (0.1, 0.5)}, (), 1, {}, None)
    assert [spec.name for spec in dataclasses.fields(Block)][-4:] == [
        "trials", "time_limit_s", "draws", "factorial"]
    assert [spec.name for spec in dataclasses.fields(Task)][-2:] == ["plans", "draws"]
    plain = Block("plain", [own])
    assert (plain.draws, plain.factorial, _task().draws) == ({}, None, {})
    assert plain.draws is not Block("other", []).draws


def test_the_designed_orders_are_a_blocks_condition_orders():
    """Sequence-balanced (TSK-23; the PI, 2026-10-30, Q5a, "Block picks; pairs default") and
    priming (Q6, "Both of the last two") order a block's conditions, beside `Shuffled`, so a plan
    cannot take either as its order of blocks; named apart from the plan orders `Balanced` and
    `Random`. No repeat on a break by default (TSK-31); "again at once" is the block's to choose
    (Q5b)."""
    balanced = SequenceBalanced()
    priming = Priming("contrast", chance=0.7)

    assert isinstance(balanced, Order) and isinstance(priming, Order)
    assert not isinstance(balanced, BlockOrder) and not isinstance(priming, BlockOrder)
    assert [spec.name for spec in dataclasses.fields(SequenceBalanced)] == [
        "depth", "cycles", "again_at_once"]
    assert (balanced.depth, balanced.cycles, balanced.again_at_once) == (2, 1, False)
    assert [spec.name for spec in dataclasses.fields(Priming)] == [
        "feature", "chance", "runs", "again_at_once"]
    assert (priming.feature, priming.chance, priming.runs, priming.again_at_once) == (
        "contrast", 0.7, None, False)
    block = Block("primed", [Condition("dim", {"contrast": 0.1}, target=0)],
                  order=Priming("contrast", runs=(3, 7), again_at_once=True), trials=200)
    assert block.order == Priming("contrast", None, (3, 7), True)
    assert Block("pairs", [], order=SequenceBalanced(depth=3, cycles=2)).order.cycles == 2
    assert Block("plain", []).order == Shuffled()
    with pytest.raises(ValueError, match="a plan's order is a BlockOrder"):
        Plan([], order=SequenceBalanced())


def test_an_array_says_what_names_its_target_its_look_by_default():
    """The PI, 2026-10-31, on the engine C3 plan's Appendix B, item 17, "Refuse only odd-one-out
    tasks (Recommended)": an array says what tells the animal which of its objects is the target
    (`found_by`, one of `FOUND_BY`). **Its look, by default** (`"look"`): the target is the odd
    one out, as in a pop-out search, which the load's two look checks hold it to. **A cue**
    (`"cue"`): something else the trial shows names it -- a cue, a remembered sample, a place --
    as in a cued two-choice design, whose target may look like its distractors. At its default it
    is left out of what the hash reads, so every task that shows an array hashes as before; a cued
    array's hash moves."""
    assert FOUND_BY == ("look", "cue")
    assert [spec.name for spec in dataclasses.fields(Array)][-1] == "found_by"
    assert Array().found_by == "look"
    cued = Array(n=2, found_by="cue")
    assert (cued.n, cued.found_by) == (2, "cue")
    with pytest.raises(dataclasses.FrozenInstanceError):
        cued.found_by = "look"
    assert "found_by" not in canonical(Array(n=2))["fields"]
    assert canonical(cued)["fields"]["found_by"] == "cue"
    assert canonical(cued) != canonical(Array(n=2))
    for name in ("visual_search", "visual_search_training"):
        assert "found_by" not in str(canonical(_load_task(ROOT / "tasks" / f"{name}.py")))


@pytest.mark.parametrize(
    ("draws", "said"),
    [
        ([("wait", Uniform(0.8, 1.2, repeat=FRESH))], "a dict of setting names to Distributions"),
        ({"": Uniform(0.8, 1.2, repeat=FRESH)}, "names its setting by text, not ''"),
        ({3: Uniform(0.8, 1.2, repeat=FRESH)}, "names its setting by text, not 3"),
        ({"wait": (0.8, 1.2)}, r"draw 'wait' is a Distribution \(.*\), not tuple"),
        ({"wait": BY_CONDITIONS}, r"draw 'wait' is a Distribution \(.*\), not str"),
        ({"wait": Shuffled()}, r"draw 'wait' is a Distribution \(.*\), not Shuffled"),
    ],
)
def test_a_tasks_draws_are_refused_as_built_unless_settings_to_distributions(draws, said):
    """Call 2: a task's draws are a dict of settings, by name, to `Distribution`s, refused as built
    otherwise, as its meanings and plans are. `BY_CONDITIONS` is a block's word, never the task's.
    What a draw declares is the load's to judge (`check.check_task`)."""
    with pytest.raises(ValueError, match=said):
        _task(draws=draws)


def test_a_task_that_draws_hashes_apart_and_one_that_does_not_keeps_its_hash():
    """Each new declaration changes what a run of the task is, so each moves the content hash. At
    its default each is left out (`declarations.canonical`), so a task that draws nothing and a
    block declaring neither draws nor factors hash as before the fields existed -- every reference
    task among them -- and `declarations.FORMAT` stays 1."""
    near = Condition("near", {"contrast": 0.5}, target=4)

    def of(**fields) -> str:
        return content_hash(_task(**fields))

    def block(**fields) -> str:
        return of(plans={"one": Plan([Block("b", [near], **fields)])})

    two = {"fix_hold": (0.3, 0.6)}
    variants = [
        of(),
        of(draws={"wait": Uniform(0.8, 1.2, repeat=FRESH)}),
        of(draws={"wait": Uniform(0.8, 1.2, repeat=SAME)}),
        of(draws={"wait": Uniform(0.8, 1.3, repeat=SAME)}),
        of(draws={"fix_hold": Uniform(0.8, 1.2, repeat=SAME)}),
        of(draws={"wait": Weighted((0.8, 1.2), (1, 1), repeat=SAME)}),
        of(draws={"wait": Weighted((0.8, 1.2), (1, 3), repeat=SAME)}),
        of(draws={"wait": TruncatedNormal(1.0, 0.1, repeat=SAME)}),
        of(draws={"wait": TruncatedNormal(1.0, 0.1, low=0.9, repeat=SAME)}),
        of(draws={"wait": TruncatedNormal(1.0, 0.1, high=1.1, repeat=SAME)}),
        of(draws={"wait": Listed((0.8, 1.2), repeat=SAME)}),
        of(draws={"wait": Listed((0.8, 1.2), in_order=True, repeat=SAME)}),
        of(draws={"wait": NonAging(0.75, 1.0, 1.25, repeat=SAME)}),
        block(),
        block(draws={"wait": NonAging(0.75, 1.0, 1.25, repeat=FRESH)}),
        block(draws={"contrast": BY_CONDITIONS}),
        block(factorial=Factorial(two)),
        block(factorial=Factorial(two, exclude=({"fix_hold": 0.3},))),
        block(factorial=Factorial(two, target=2)),
        block(factorial=Factorial(two, targets={"fix_hold=0.6": 3})),
        block(factorial=Factorial(two, structure="wait")),
        block(factorial=Factorial({"fix_hold": (0.3, Uniform(0.5, 0.7, repeat=SAME))})),
        block(order=SequenceBalanced()),
        block(order=SequenceBalanced(depth=3)),
        block(order=SequenceBalanced(cycles=2)),
        block(order=SequenceBalanced(again_at_once=True)),
        block(order=Priming("contrast", chance=0.7)),
        block(order=Priming("contrast", chance=0.6)),
        block(order=Priming("contrast", runs=(3, 7))),
        block(order=Priming("contrast", runs=(3, 7), again_at_once=True)),
        of(plans={"one": Plan([Block("b", [dataclasses.replace(
            near, values={"contrast": Uniform(0.1, 0.9, repeat=SAME)})])])}),
    ]

    assert len(set(variants)) == len(variants) == 31
    assert of(draws={}) == of() == content_hash(_task())
    assert block(draws={}, factorial=None) == block()
    written = canonical(_task(plans={"one": Plan([Block("b", [near])])}))
    assert "draws" not in written["fields"]
    assert set(written["fields"]["plans"]["one"]["fields"]["blocks"][0]["fields"]) == {
        "name", "conditions"}
    for name in ("fixation_detection", "adaptive_detection", "visual_search",
                 "visual_search_training", "calibration"):
        assert "draws" not in canonical(_load_task(ROOT / "tasks" / f"{name}.py"))["fields"]
