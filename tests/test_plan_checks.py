"""The load-time checks of a task's plans (engine spec §13; engine build C2b).

Under the PI's rule of 2026-10-11, warnings over refusals: a plan is refused only for what cannot
run or would leave its record unreadable, each sentence saying which plan and block and what to
write, and warned, saying why, for what runs but may not do what was meant. Every caller that holds
a task to its checks -- `wlx check`, `wlx run`, the pre-flight, `Session.run`'s backstop -- sees
these through `check.check_task`.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from wl_xcon.check import check_task
from wl_xcon.cli import _load_task
from wl_xcon.findings import SESSION_KINDS
from wl_xcon.scheduler import CORRECT_ONLY, EVERY_TRIAL
from wl_xcon.task import (
    OWED,
    Balanced,
    Block,
    ByCriterion,
    Condition,
    Constrained,
    Counting,
    Cyclic,
    Order,
    Plan,
    Random,
    WithReplacement,
)

BASE = _load_task(Path("tasks/fixation_detection.py"))
#: The codes this file's checks give; the reference task gives none of them.
PLAN_CODES = {"bad-plan", "endless-plan", "unbalanced-plan", "late-condition", "empty-block",
              "block-table-unread", "no-run-limit", "weightless-condition", "fall-back-unjudged",
              "fall-back-bounce", "unknown-weight"}

NEAR = Condition("near", {"target_x": 5.0}, target=4)
FAR = Condition("far", {"target_x": 12.0}, target=4, structure="detection")


def _findings(**plans) -> list:
    task = dataclasses.replace(BASE, plans=plans)
    return [f for f in check_task(task) if f.code in PLAN_CODES]


def test_a_condition_s_position_and_its_setting_s_choices_are_named_in_the_rig_s_words(tmp_path):
    """Review 1's I2 (the PI, 2026-10-30, "0 to 360 everywhere"; STE-29): a condition setting a
    whole position to no choice of its setting names the value and the choices as the review report
    does, eccentricity and direction first, each direction from 0° to 360° and none at the center,
    never as Python writes a `Polar`."""
    import _sessions
    from wl_xcon.task import Polar

    path = _sessions.polar_task(tmp_path)
    text = path.read_text()
    old = "choices=(Polar(8.0, 0.0), Polar(8.0, 45.0))"
    assert text.count(old) == 1
    path.write_text(text.replace(old, "choices=(Polar(8.0, -90.0), Polar(0.0, 45.0))"))
    task = dataclasses.replace(_load_task(path), plans={"p": Plan([Block("b", [
        Condition("c", {"target_pos": Polar(8.0, -45.0)}, target=1)])])})

    (said,) = [f.detail for f in check_task(task) if f.code == "bad-plan"]

    assert ("sets 'target_pos' to 8° at 315° · (x, y) (5.675, -5.675), and it is one of "
            "8° at 270° · (x, y) (0, -8), 0° · (x, y) (0, 0)") in said
    assert "Polar(" not in said and "-90" not in said


def test_a_plan_the_rig_can_run_adds_no_finding():
    """A balanced plan of whole rounds and a run time limit; a training progression with a fall-back
    rule and a run time limit; conditions naming the task's structure and setting its settings
    within their ranges."""
    blocks = [Block("near-far", [NEAR, FAR], criterion=(0.8, 10)),
              Block("far", [FAR], trials=20, time_limit_s=300.0,
                    order=WithReplacement(weights={"far": 2.0}))]
    stages = [Block("easy", [NEAR], criterion=(0.8, 10)),
              Block("hard", [FAR], criterion=(0.8, 10), time_limit_s=600.0)]

    assert _findings(
        balanced=Plan(blocks, order=Balanced(blocks=4), time_limit_s=1800.0),
        training=Plan(stages, order=ByCriterion(fall_back=(0.5, 10)), time_limit_s=3600.0),
        fixed=Plan(blocks),
    ) == []


@pytest.mark.parametrize(
    ("plan", "said"),
    [
        (Plan([]), "it has no blocks"),
        (Plan([Block("b", (NEAR,))]), "a block's conditions are a list of Conditions"),
        (Plan([Block("b", [NEAR]), Block("b", [FAR])]), "two of its block types are named 'b'"),
        # XC-388: two conditions of one block with one name.
        (Plan([Block("b", [NEAR, dataclasses.replace(FAR, name="near")])]),
         "block 'b' has two conditions named 'near'"),
        # XC-381: a block that can never end.
        (Plan([Block("b", [], criterion=(0.8, 10))]), "has no conditions and ends on a criterion"),
        (Plan([Block("b", [], trials=10)]), "has no conditions and ends on a number of trials"),
        (Plan([Block("b", [dataclasses.replace(NEAR, structure="search")])]),
         "plays structure 'search', which the task does not have"),
        (Plan([Block("b", [Condition("c", {"reward_correct": 0.2}, target=1)])]),
         "sets 'reward_correct', which is no setting the task declares"),
        (Plan([Block("b", [Condition("c", {"target_x": "far"}, target=1)])]),
         "sets 'target_x' to 'far', and it takes a finite number (deg)"),
        (Plan([Block("b", [Condition("c", {"target_x": 10**400}, target=1)])]),
         "sets 'target_x' to 1.00000e+400, and it takes a finite number (deg)"),
        (Plan([Block("b", [Condition("c", {"target_appearance": "disc"}, target=1)])]),
         "sets 'target_appearance' to 'disc', and it is one of"),
        (Plan([Block("b", [dataclasses.replace(NEAR, target=-1)])]), "has target -1"),
        (Plan([Block("b", [NEAR], criterion=(0.8, 0))]), "criterion is (0.8, 0)"),
        (Plan([Block("b", [NEAR], criterion=(1.5, 10))]), "criterion is (1.5, 10)"),
        (Plan([Block("b", [NEAR])], order=ByCriterion(fall_back=(0.5, 0)), time_limit_s=60.0),
         "its fall-back rule is (0.5, 0)"),
        (Plan([Block("b", [NEAR], trials=0)]), "number of trials is 0"),
        (Plan([Block("b", [NEAR], time_limit_s=0.0)]),
         "time limit is 0.0; a time limit is a number of seconds"),
        (Plan([Block("b", [NEAR])], time_limit_s=-5.0), "its time limit is -5.0"),
        (Plan([Block("b", [NEAR])], order=Cyclic(cycles=0)), "its order's count is 0"),
        (Plan([Block("b", [NEAR], order=WithReplacement(weights={"near": -1.0}))]),
         "weights are {'near': -1.0}"),
        # The review's I1: slips the scheduler cannot start a run on.
        (Plan([Block("b", [NEAR, FAR], order=Constrained(max_run=None))]),
         "longest run is None, and it is a whole number of trials, 1 or more"),
        (Plan([Block("b", [NEAR, FAR], order=Constrained(max_run=2.5))]),
         "longest run is 2.5, and it is a whole number"),
        (Plan([Block("b", [NEAR, FAR], order=Constrained(max_run=True))]),
         "longest run is True, and it is a whole number"),
        (Plan([Block("b", [NEAR, FAR], order=Random())]),
         "order is Random(blocks=None), and a block's order is how its conditions follow"),
        # The review's I2: refused, not a traceback.
        (Plan([Block("b", [NEAR, FAR], order=WithReplacement(weights=None))]),
         "weights are None, and weights are a dict"),
        (Plan([Block("easy", [NEAR]), Block("mid", (NEAR,)), Block("hard", [FAR])],
              order=ByCriterion(fall_back=(0.5, 10)), time_limit_s=600.0),
         "and a block's conditions are a list of Conditions"),
        (Plan([Block("b", [NEAR], order=WithReplacement(weights={"near": 0.0}))]),
         "at least one condition's above 0"),
        # The final review's T6, N1: a middle stage of text, where `most_answers` reads each
        # condition's structure, refused rather than raising.
        (Plan([Block("easy", [NEAR]), Block("mid", ["near"]), Block("hard", [FAR])],
              order=ByCriterion(fall_back=(0.5, 10)), time_limit_s=600.0),
         "block 'mid''s conditions are ['near'], and a block's conditions are a list of "
         "Conditions"),
        # The final review's I1: an order the scheduler cannot draw from faulted the first draw.
        (Plan([Block("b", [NEAR, FAR], order=Order())]),
         "order is Order(), and a block's order is how its conditions follow"),
        # The final review's I2: a block's own table that is no table raised in the check.
        (Plan([Block("b", [NEAR], counting="spent")]),
         "block 'b''s own counting table is 'spent', and a block counts by a Counting"),
        (Plan([Block("easy", [NEAR]), Block("mid", [NEAR], counting="spent"), Block("hard", [FAR])],
              order=ByCriterion(fall_back=(0.5, 10)), time_limit_s=600.0),
         "block 'mid''s own counting table is 'spent'"),
        # The final review's I3: values that are no dict faulted the first trial; a value keyed by
        # anything but text, and a block or condition named by anything but text, which each
        # trial's row names it by -- an int written as a number in trials.jsonl's `condition`.
        (Plan([Block("b", [Condition("c", [("target_x", 5.0)], target=1)])]),
         "block 'b''s condition 'c' sets [('target_x', 5.0)], and a condition's values are a "
         "dict of setting name to value"),
        (Plan([Block("b", [Condition("c", {1: 5.0}, target=1)])]),
         "block 'b''s condition 'c' sets a value keyed 1, and a condition names each setting it "
         "sets by text"),
        (Plan([Block("b", [Condition(1, {"target_x": 5.0}, target=1)])]),
         "block 'b' has a condition named 1, which is not text, and each trial's row names its "
         "condition by its name; name it by text, such as 'near'"),
        (Plan([Block("b", [Condition(["x"], {"target_x": 5.0}, target=1)])]),
         "block 'b' has a condition named ['x'], which is not text"),
        (Plan([Block(2, [NEAR])]),
         "a block type is named 2, which is not text, and each trial's row names its block's type "
         "by its name; name it by text, such as 'easy'"),
        (Plan([Block("b", [dataclasses.replace(NEAR, structure=["x"])])]),
         "plays structure ['x'], which the task does not have"),
        (Plan([Block("easy", [NEAR]), Block("mid", [dataclasses.replace(NEAR, structure=["x"])]),
               Block("hard", [FAR])], order=ByCriterion(fall_back=(0.5, 10)), time_limit_s=600.0),
         "block 'mid''s condition 'near' plays structure ['x']"),
    ],
)
def test_a_plan_that_cannot_run_is_refused_saying_which_and_why(plan, said):
    """Unrunnable, or unreadable in the record: refused in every kind of session, as an authoring
    rule, never a warning (the PI's rule of 2026-10-11 keeps refusals for these)."""
    found = _findings(p=plan)

    assert [f.code for f in found] == ["bad-plan"], found
    assert found[0].detail.startswith("plan 'p': ") and said in found[0].detail
    assert all(found[0].refuses(kind) for kind in SESSION_KINDS)


def test_a_plan_named_past_what_a_start_can_carry_is_refused_saying_so():
    """The wire takes a plan's name as 1 to 200 characters (`link._command_from`), so a longer one
    could be offered on the page and never started: refused at load, in every kind of session."""
    ok = Plan([Block("b", [NEAR])])

    assert _findings(**{"x" * 200: ok}) == []
    found = _findings(**{"x" * 201: ok})

    assert [f.code for f in found] == ["bad-plan"], found
    assert "its name is 201 characters, and a plan's name is 1 to 200" in found[0].detail
    assert all(found[0].refuses(kind) for kind in SESSION_KINDS)


def test_a_refusal_quotes_an_over_long_plan_name_cut_short():
    """The final review's T8: the refusal lands in the page's pre-flight line, so a name of
    thousands of characters is quoted by its first characters only, and the sentence after it
    still says what is wrong."""
    (found,) = _findings(**{"x" * 5000: Plan([Block("b", [NEAR])])})

    assert found.detail.startswith(f"plan {'x' * 40 + '…'!r}: its name is 5000 characters")
    assert len(found.detail) < 250


@pytest.mark.parametrize(
    ("plan", "code", "said"),
    [
        # XC-386: a target-0 condition beside nonzero targets in a criterion block.
        (Plan([Block("b", [NEAR, dataclasses.replace(FAR, target=0)], criterion=(0.8, 10))]),
         "late-condition", "condition(s) 'far' have target 0"),
        (Plan([Block("b", [NEAR])], order=Cyclic()), "endless-plan",
         "count of none repeats its blocks"),
        (Plan([Block("b", [NEAR])], order=Random()), "endless-plan", "no time limit"),
        (Plan([Block("b", [NEAR], criterion=(0.8, 10))], order=ByCriterion()), "endless-plan",
         "stage 'b' is the top stage and has no time limit, so an animal that meets its rule "
         "works on there"),
        (Plan([Block("a", [NEAR], criterion=(0.8, 10)),
               Block("b", [FAR], criterion=(0.8, 10), time_limit_s=60.0)], order=ByCriterion()),
         "endless-plan", "an animal that never meets the rule of stage 'a', which has no time "
         "limit"),
        # The final review's T6, N4: each order's own count named.
        (Plan([Block("b", [NEAR])], order=Cyclic()), "endless-plan",
         "give the order a count -- cycles= -- and it ends after that many"),
        (Plan([Block("b", [NEAR])], order=Balanced()), "endless-plan",
         "give the order a count -- blocks= -- and it ends after that many"),
        (Plan([Block("b", [NEAR])], order=Random()), "endless-plan",
         "give the order a count -- blocks= -- and it ends after that many"),
        # The review's M4: a number of trials holds a target-0 condition back as a criterion does.
        (Plan([Block("b", [NEAR, dataclasses.replace(FAR, target=0)], trials=12)]),
         "late-condition", "ends on a criterion or a number of trials"),
        # The review's M7: a weight naming no condition of the block.
        (Plan([Block("b", [NEAR, FAR], order=WithReplacement(weights={"nera": 0.0}))]),
         "unknown-weight", "weights name 'nera', which no condition of the block is called"),
        (Plan([Block("a", [NEAR]), Block("b", [FAR])], order=Balanced(blocks=5)),
         "unbalanced-plan", "5 blocks of 2 block types are not whole rounds"),
        (Plan([Block("b", [dataclasses.replace(NEAR, target=0)]), Block("c", [FAR])]),
         "empty-block", "block 'b' owes no trial -- every target 0"),
        (Plan([Block("b", [NEAR], counting=Counting(after_stimulus=OWED, appears="stim_on"))]),
         "block-table-unread", "its stimulus appears in 'stim_on'"),
        (Plan([Block("b", [NEAR], counting=dataclasses.replace(EVERY_TRIAL, withholding=True))]),
         "block-table-unread", "withholding is an answer"),
        (Plan([Block("b", [NEAR], order=Constrained(max_run=0))]), "no-run-limit",
         "longest run is 0"),
        # The engineering review, I2: a condition of weight 0 owed trials is never drawn.
        (Plan([Block("b", [NEAR, FAR], order=WithReplacement(weights={"near": 0.0}))]),
         "weightless-condition", "condition(s) 'near' weigh 0"),
        # Minor 3: a fall-back rule never judged -- one stage, or a stage over before its window.
        (Plan([Block("b", [NEAR], criterion=(0.8, 10))], order=ByCriterion(fall_back=(0.5, 10)),
              time_limit_s=600.0),
         "fall-back-unjudged", "it has one stage and a fall-back rule"),
        (Plan([Block("easy", [NEAR], criterion=(0.8, 10)), Block("mid", [NEAR]),
               Block("hard", [FAR], criterion=(0.8, 10))],
              order=ByCriterion(fall_back=(0.5, 10)), time_limit_s=600.0),
         "fall-back-unjudged", "stage 'mid' has no criterion and every answer pays its condition, "
         "so it ends on its rule after 4 first answers at most"),
        # The science review, M2: a progression prone to move up and back.
        (Plan([Block("a", [NEAR], criterion=(0.6, 10)), Block("b", [FAR], criterion=(0.8, 10))],
              order=ByCriterion(fall_back=(0.7, 10)), time_limit_s=600.0),
         "fall-back-bounce", "under 70% of the last 10 first answers right, is at or above stage "
         "'a''s bar of 60%"),
        (Plan([Block("a", [NEAR], criterion=(0.8, 10)), Block("b", [FAR], criterion=(0.8, 5)),
               Block("c", [NEAR], criterion=(0.8, 10))],
              order=ByCriterion(fall_back=(0.5, 10)), time_limit_s=600.0),
         "fall-back-bounce", "stage 'b' judges its last 5 answers and the fall-back rule the last "
         "10 first answers"),
    ],
)
def test_a_plan_that_runs_but_may_not_do_what_was_meant_is_a_warning_saying_why(plan, code, said):
    """The PI, 2026-10-11: "warnings are more appropriate most of the time with an explanation of
    why it may not be a good idea": each accepted in every kind of session, refusing none."""
    found = _findings(p=plan)

    assert [f.code for f in found] == [code], found
    assert said in found[0].detail
    assert not found[0].blocking and set(found[0].accepted_in) == set(SESSION_KINDS)


def test_names_of_text_and_of_numbers_together_are_refused_and_never_raise():
    """The final review's I3: two block types named by one number beside two named by one text
    raised sorting the names; each number is refused, and the text named twice is."""
    found = _findings(p=Plan([Block(1, [NEAR]), Block(1, [FAR]), Block("a", [NEAR]),
                              Block("a", [FAR])]))

    assert [f.code for f in found] == ["bad-plan"] * 3
    assert "two of its block types are named 'a'" in found[0].detail
    assert all("a block type is named 1, which is not text" in f.detail for f in found[1:])


def test_a_weight_on_a_block_of_no_conditions_says_the_block_has_none():
    """The final review's T6, N4: `unknown-weight` on a block with no conditions ended "check
    the spelling against " with nothing after it."""
    found = _findings(p=Plan([Block("b", [], order=WithReplacement(weights={"x": 1.0}))]))

    (weight,) = [f for f in found if f.code == "unknown-weight"]
    assert weight.detail.endswith(
        "block 'b''s weights name 'x', which no condition of the block is called, so they weigh "
        "nothing; the block has no conditions")


def test_a_training_progression_ends_of_itself_only_with_every_stage_timed_and_no_fall_back():
    """The science review, C3: a training progression is warned as endless unless the plan has a
    run time limit, or it has no fall-back rule and every stage has a time limit -- an animal that
    never meets an untimed stage's rule works on there, the top stage's included, and a fall-back
    can move a run of timed stages up and back forever."""
    stages = [Block("easy", [NEAR], criterion=(0.8, 10)), Block("hard", [FAR], criterion=(0.8, 10))]
    top_timed = [stages[0], dataclasses.replace(stages[1], time_limit_s=600.0)]
    all_timed = [dataclasses.replace(stage, time_limit_s=600.0) for stage in stages]

    def codes(blocks, **plan) -> list:
        return [f.code for f in _findings(p=Plan(blocks, **plan))]

    assert codes(stages, order=ByCriterion()) == ["endless-plan"]
    assert codes(top_timed, order=ByCriterion()) == ["endless-plan"]
    assert codes(all_timed, order=ByCriterion(fall_back=(0.5, 10))) == ["endless-plan"]
    assert "forever" in _findings(
        p=Plan(all_timed, order=ByCriterion(fall_back=(0.5, 10))))[0].detail
    assert codes(all_timed, order=ByCriterion()) == []
    assert codes(stages, order=ByCriterion(fall_back=(0.5, 10)), time_limit_s=1800.0) == []


def test_a_middle_stage_that_cannot_end_before_the_fall_back_window_is_not_warned():
    """The review's M3: `most_answers` warns only where every answer pays and the stage ends within
    the window. A stage counting by `CORRECT_ONLY` leaves a wrong answer unpaid, so it can run on;
    one that withholds with a miss left unpaid the same; one with `trials=` at or above the window
    is judged by it; one whose targets reach the window the same."""
    unpaid_miss = dataclasses.replace(BASE.structures["detection"].counting, outcomes={
        "no_response": "unpaid"})
    detection = dataclasses.replace(BASE.structures["detection"], counting=unpaid_miss)
    task = dataclasses.replace(BASE, structures={"detection": detection})

    def codes(mid: Block, base=BASE) -> list:
        plan = Plan([Block("easy", [NEAR]), mid, Block("hard", [FAR])],
                    order=ByCriterion(fall_back=(0.5, 10)), time_limit_s=600.0)
        return [f.code for f in check_task(dataclasses.replace(base, plans={"p": plan}))
                if f.code in PLAN_CODES]

    small = dataclasses.replace(NEAR, target=2)
    assert codes(Block("mid", [small])) == ["fall-back-unjudged"]
    assert codes(Block("mid", [small], counting=CORRECT_ONLY)) == []
    assert codes(Block("mid", [small]), task) == []
    assert codes(Block("mid", [small], trials=10)) == []
    assert codes(Block("mid", [dataclasses.replace(NEAR, target=10)])) == []
