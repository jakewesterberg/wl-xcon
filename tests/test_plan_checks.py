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
from wl_xcon.scheduler import EVERY_TRIAL
from wl_xcon.task import (
    OWED,
    Balanced,
    Block,
    ByCriterion,
    Condition,
    Constrained,
    Counting,
    Cyclic,
    Plan,
    Random,
    WithReplacement,
)

BASE = _load_task(Path("tasks/fixation_detection.py"))
#: The codes this file's checks give; the reference task gives none of them.
PLAN_CODES = {"bad-plan", "endless-plan", "unbalanced-plan", "late-condition", "empty-block",
              "block-table-unread", "no-run-limit", "weightless-condition", "fall-back-unjudged",
              "fall-back-bounce"}

NEAR = Condition("near", {"target_x": 5.0}, target=4)
FAR = Condition("far", {"target_x": 12.0}, target=4, structure="detection")


def _findings(**plans) -> list:
    task = dataclasses.replace(BASE, plans=plans)
    return [f for f in check_task(task) if f.code in PLAN_CODES]


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
         "sets 'target_x' to 'far', and it takes a number (deg)"),
        (Plan([Block("b", [Condition("c", {"target_appearance": "disc"}, target=1)])]),
         "sets 'target_appearance' to 'disc', and it is one of"),
        (Plan([Block("b", [dataclasses.replace(NEAR, target=-1)])]), "has target -1"),
        (Plan([Block("b", [NEAR], criterion=(0.8, 0))]), "criterion is (0.8, 0)"),
        (Plan([Block("b", [NEAR], criterion=(1.5, 10))]), "criterion is (1.5, 10)"),
        (Plan([Block("b", [NEAR])], order=ByCriterion(fall_back=(0.5, 0)), time_limit_s=60.0),
         "its fall-back rule is (0.5, 0)"),
        (Plan([Block("b", [NEAR], trials=0)]), "number of trials is 0"),
        (Plan([Block("b", [NEAR], time_limit_s=0.0)]), "time limit is 0.0, a number of seconds"),
        (Plan([Block("b", [NEAR])], time_limit_s=-5.0), "its time limit is -5.0"),
        (Plan([Block("b", [NEAR])], order=Cyclic(cycles=0)), "its order's count is 0"),
        (Plan([Block("b", [NEAR], order=WithReplacement(weights={"near": -1.0}))]),
         "weights are {'near': -1.0}"),
        (Plan([Block("b", [NEAR], order=WithReplacement(weights={"near": 0.0}))]),
         "at least one condition's above 0"),
    ],
)
def test_a_plan_that_cannot_run_is_refused_saying_which_and_why(plan, said):
    """Unrunnable, or unreadable in the record: refused in every kind of session, as an authoring
    rule, never a warning (the PI's rule of 2026-10-11 keeps refusals for these)."""
    found = _findings(p=plan)

    assert [f.code for f in found] == ["bad-plan"], found
    assert found[0].detail.startswith("plan 'p': ") and said in found[0].detail
    assert all(found[0].refuses(kind) for kind in SESSION_KINDS)


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
         "never meets the rule of stage 'b', which has no time limit"),
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
