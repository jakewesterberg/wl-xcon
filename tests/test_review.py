"""The review artifact.

ADR-0006 rests on this: a task Claude wrote is approved from a rendered diagram, a
code table and a simulation report, **without reading the source**. If that is not
possible, the design failed rather than the reviewer -- so the artifact is a
deliverable, not a convenience.
"""

from __future__ import annotations

import dataclasses

import pytest

from wl_xcon.declarations import COMMON, content_hash
from wl_xcon.review import render, render_task
from wl_xcon.task import (
    After,
    BACKGROUND,
    CLEAR_CUT,
    Choice,
    Counting,
    EASIER,
    EXPECTED,
    HARDER,
    Mark,
    Hold,
    Exited,
    Meaning,
    NO_CHOICE,
    NO_LIMIT,
    On,
    P,
    Param,
    Outcome,
    ReactionTime,
    Reward,
    SaccadeTo,
    SPENT,
    Block,
    Balanced,
    ByCriterion,
    Condition,
    Constrained,
    Cyclic,
    Fixed,
    Plan,
    Random,
    STIMULUS,
    State,
    Task,
    Trial,
    Window,
    WithReplacement,
)

TRIAL = Trial(
    start="hold",
    windows=[Window("fix", at=(0.0, 0.0), radius=2.0)],
    states=[
        State(
            "hold",
            enter=[Mark(4096)],
            go=[
                On(Exited("fix"), Outcome.FIXATION_BREAK),
                On(After(0.3), Outcome.CORRECT),
            ],
        ),
    ],
)


def test_the_diagram_shows_every_transition_with_its_guard():
    """A diagram that omits a transition is worse than none: it is a picture a
    reviewer trusts, showing a task that is not the one that will run."""
    artifact = render(TRIAL)

    assert "stateDiagram-v2" in artifact
    assert "[*] --> hold" in artifact
    assert "hold --> FIXATION_BREAK: Exited(fix)" in artifact
    assert "hold --> CORRECT: After(0.3s)" in artifact


def test_the_code_table_names_what_each_code_means():
    """A recorded code carries timing without meaning. The reviewer has to be able
    to see which state emits what, or the event stream is unreviewable."""
    artifact = render(TRIAL, allocation_names={4096: "FIX_ON"})

    assert "4096" in artifact
    assert "FIX_ON" in artifact
    assert "hold" in artifact


def test_a_parameter_reference_renders_as_its_name():
    """The artifact exists to be read. `After(fix_acquisitions)` -- a unit suffix glued
    to a parameter name -- and a raw `P(name='fix_hold')` are both noise in the one
    place noise costs the most, because a reviewer who stops trusting the diagram
    goes back to reading source, which is the thing this replaces."""
    trial = Trial(
        start="hold",
        windows=[Window("fix", at=(0.0, 0.0), radius=2.0)],
        params=[Param("fix_hold", unit="s", low=0.05, high=2.0)],
        states=[
            State(
                "hold",
                go=[
                    On(Hold("fix", P("fix_hold")), Outcome.CORRECT),
                    On(After(P("fix_hold")), Outcome.NO_RESPONSE),
                ],
            ),
        ],
    )

    artifact = render(trial)

    assert "Hold(fix, fix_hold)" in artifact
    assert "After(fix_hold)" in artifact
    assert "P(name=" not in artifact
    assert "fix_holds" not in artifact


# --- The task object's report (engine spec §18.1; engine build C1) -----------------------

HOLDING = Trial(
    start="hold",
    windows=[Window("fix", at=(0.0, 0.0), radius=2.0)],
    params=[
        Param("fix_hold", unit="s", low=0.05, high=2.0),
        Param("contrast", unit="fraction", low=0.02, high=1.0),
        Param("target_appearance", unit="appearance", choices=("disc", "square")),
    ],
    states=[
        State("hold", enter=[Mark(4096)],
              go=[On(SaccadeTo("fix"), "held"), On(After(P("fix_hold")), Outcome.NO_RESPONSE)]),
        State("held", go=[On(After(0.1), Outcome.CORRECT, do=[Reward("reward_correct")])]),
    ],
)
OTHER = Trial(start="hold", states=[State("hold", go=[On(After(0.3), Outcome.CORRECT)])])
LOOKS = Meaning(EXPECTED, STIMULUS, raising=HARDER, note="the feature | that pops out",
                overrides="search pops out on it")


def _reviewed(**over) -> Task:
    """Two structures, `OTHER` written first and `HOLDING` the default."""
    fields = dict(
        structures={"other": OTHER, "holding": HOLDING},
        default="holding",
        reaction_time=ReactionTime("hold", ("held",), "from the hold's start to a saccade"),
        choice=Choice(("fix",), "saccade"),
        meanings={"contrast": Meaning(CLEAR_CUT, STIMULUS, raising=EASIER), "target_appearance": LOOKS},
    )
    fields.update(over)
    return Task(**fields)


def test_a_task_report_says_what_each_setting_means_and_where_that_comes_from():
    """XC-288 §4: "the person reviewing the task confirms it, in the review report"; an override
    shows why, and each setting whether it is a criterion or a stimulus (the PI, 2026-10-11)."""
    out = render_task(_reviewed())
    shared = COMMON["fix_hold"]

    assert "## What a reviewer confirms" in out and "### What each setting means" in out
    assert "| Setting | Unit | Role | Meaning | Direction | Note | From |" in out
    assert (f"| fix_hold | s | {shared.role} | {shared.kind} | raising it: {shared.raising} "
            f"|  | shared list |" in out)
    assert "| contrast | fraction | stimulus | clear-cut | raising it: easier |  | this task |" in out
    assert ("| target_appearance | appearance | stimulus | expected | changing it: harder "
            "| the feature \\| that pops out | overrides the shared list: search pops out on it |"
            in out)


def test_a_direction_read_from_a_reference_says_from_what():
    """Call 4: a direction reads on raising the value, or on moving it away from a number, another
    setting, or the trial's background."""
    for relative, said in [(0, "farther from 0"), (2.5, "farther from 2.5"),
                           ("fix_hold", "farther from `fix_hold`"),
                           (BACKGROUND, "farther from the background")]:
        contrast = Meaning(EXPECTED, STIMULUS, raising=EASIER, note="n", relative_to=relative)
        out = render_task(_reviewed(meanings={"contrast": contrast, "target_appearance": LOOKS}))

        assert f"| contrast | fraction | stimulus | expected | {said}: easier | n | this task |" in out


def test_a_setting_with_no_meaning_is_shown_undeclared_not_hidden():
    """`wlx review` checks nothing first, so the report says what is missing."""
    out = render_task(_reviewed(meanings={"target_appearance": LOOKS}))

    assert "| contrast | fraction | **UNDECLARED** | | | | |" in out


def test_the_report_says_how_reaction_time_is_defined_what_it_offers_and_its_head():
    out = render_task(_reviewed())

    assert "From entering `hold` to leaving it for `held`: from the hold's start to a saccade." in out
    assert "`fix`, chosen by a saccade." in out
    assert "Runs with the head fixed or free" in out
    head = "Needs a fixed head: a warning, not a refusal, in any session not declared head-fixed"
    assert head in render_task(_reviewed(needs_fixed_head=True))
    assert "None: the task offers no choice." in render_task(_reviewed(choice=NO_CHOICE))
    bare = render_task(_reviewed(reaction_time=None, choice=None))
    assert bare.count("**Not declared.**") == 2


def test_the_report_names_the_task_by_its_content_and_its_bounded_settings():
    out = render_task(_reviewed())

    assert f"Content: `{content_hash(_reviewed())}`" in out
    assert "### Bounded settings it rewards through" in out
    assert "| reward_correct | neither | not a difficulty setting |" in out


def test_the_report_shows_what_each_trial_does_to_its_conditions_count():
    """Engine build C2a (its plan's engineering review, Minor 8): the counting table changes what a
    run's count means, so a reviewer confirms it -- every outcome's class once the stimulus has
    appeared and before, the hang's, whether withholding is an answer, the repeat limit -- and a
    structure without one says so, as the load-time check refuses it."""
    table = Counting(after_stimulus=SPENT, appears="hold", withholding=True, cap=3)
    holding = dataclasses.replace(HOLDING, counting=table)
    out = render_task(_reviewed(structures={"other": OTHER, "holding": holding}))

    assert "### What each trial does to its condition's count" in out
    assert "| Outcome | After the stimulus appears | Before it |" in out
    assert "| target_break | used up | shown again |" in out
    assert "| no_response | counted | counted |" in out
    assert "| fixation_break | shown again | shown again |" in out
    assert "| hang (the five-minute cap) | shown again | shown again |" in out
    assert "Structure `holding`: its stimulus appears in `hold`; withholding is an answer" in out
    assert "a repeat limit of 3 failed repeats in a row" in out
    assert "Structure `other`: **no counting table**" in out
    assert out.index("### What each trial does") < out.index("## Structure `holding`")


def test_the_report_shows_each_plan_in_tables():
    """Engine spec §18.1, "the plan in tables" (engine build C2b): each plan's order and run time
    limit; each block's end rules, how it draws its conditions, what it counts by and whether it
    drums; each condition's structure, target and values. A task with none says so."""
    plans = {
        "train": Plan(
            [Block("easy", [Condition("near", {"contrast": 0.9}, target=10)],
                   criterion=(0.8, 20), time_limit_s=300.0, drum=True),
             Block("hard", [Condition("far", {"contrast": 0.2}, target=10, structure="other")],
                   criterion=(1.0, 5), trials=40, counting=Counting(after_stimulus=SPENT),
                   order=Constrained(max_run=2))],
            order=ByCriterion(fall_back=(0.5, 20)), time_limit_s=1800.0),
        "loop": Plan([Block("easy", [Condition("near", {}, target=4)])], order=Cyclic(cycles=3)),
    }
    out = render_task(_reviewed(plans=plans))

    assert "### Plans" in out and "#### Plan `train`" in out and "#### Plan `loop`" in out
    assert ("A training progression, stage by stage from the first: up one when a stage's rule is "
            "met or its time runs out; back one, started fresh, under 50% right over the last 20 "
            "first answers; the top stage keeps working until a time limit, a stop or the "
            "session's end. "
            "The run ends at the first pause between trials after 30 minutes of trials.") in out
    assert ("| easy | every target used up; 80% right over the last 20 answers; or its time runs "
            "out at 5 minutes | shuffled passes | each condition's structure's table | yes |"
            in out)
    assert ("| hard | every target used up; 5 right in a row; 40 trials run | drawn with "
            "replacement, runs of at most 2 | its own table | no |") in out
    assert "| train | " not in out
    assert "| easy | near | holding | 10 | contrast = 0.9 |" in out
    assert "| hard | far | other | 10 | contrast = 0.2 |" in out
    assert "In order, over and over: 3 passes. No run time limit." in out
    assert out.index("### Plans") < out.index("## Structure `holding`")
    assert "None: the plain run only" in render_task(_reviewed())


def test_a_conditions_position_is_shown_eccentricity_and_direction_first():
    """The PI, 2026-10-19, "Polar first, x-y allowed": a value a condition sets that is a position
    -- a whole-point setting's `Polar` or pair -- is shown in the plan's table as every position in
    the report is, eccentricity and direction first and its (x, y) beside them; a number as
    written. A pair is a position only for a setting declared as one, its choices each a `Polar`
    or a pair (XC-401's fix round, M2): a pair another setting holds is shown as written."""
    from dataclasses import replace

    from wl_xcon.task import Polar

    holding = replace(HOLDING, params=[
        *HOLDING.params, Param("pos", unit="deg", choices=(Polar(8.0, 45.0), (5.0, 0.0))),
        Param("span", unit="deg", low=0.0, high=1.0)])
    plans = {"places": Plan([Block("b", [
        Condition("oblique", {"pos": Polar(8.0, 45.0), "contrast": 0.5}, target=2),
        Condition("right", {"pos": (5.0, 0.0)}, target=2),
        Condition("plain", {"span": (0.3, 0.6)}, target=2)])])}
    out = render_task(_reviewed(plans=plans, structures={"other": OTHER, "holding": holding}))

    assert ("| b | oblique | holding | 2 | pos = 8° at 45° · (x, y) (5.675, 5.675), "
            "contrast = 0.5 |") in out
    assert "| b | right | holding | 2 | pos = 5° at 0° · (x, y) (5, 0) |" in out
    assert "| b | plain | holding | 2 | span = (0.3, 0.6) |" in out


def test_the_plan_tables_say_a_time_in_whole_minutes_and_a_balanced_order_never_back_to_back():
    """The engineering review, Minor 4 ("1 minutes", "3.33333 minutes"), and the PI's "Never
    back-to-back" (2026-10-19), as the report says them."""
    plans = {"mixed": Plan([Block("a", [Condition("near", {}, target=4)], time_limit_s=200.0),
                            Block("b", [Condition("far", {}, target=4)])],
                           order=Balanced(blocks=4), time_limit_s=60.0)}
    out = render_task(_reviewed(plans=plans))

    assert ("In shuffled rounds within the run, each block type once a round, drawn from the run's "
            "seed, never one type twice in a row: 4 blocks. The run ends at the first pause "
            "between trials after 1 minute of trials.") in out
    assert "or its time runs out at 3 minutes 20 s" in out


NEAR = Condition("near", {"contrast": 0.9}, target=4)


@pytest.mark.parametrize(
    ("plan", "said"),
    [
        (Plan([Block("b", [NEAR])], order=Random(blocks=3)),
         "Each block a type drawn at random from the run's seed: 3 blocks. No run time limit."),
        (Plan([Block("b", [NEAR])], order=Random()),
         "Each block a type drawn at random from the run's seed: until a time limit, a stop or the "
         "out-of-cage limit."),
        (Plan([Block("b", [NEAR])], order=Fixed()), "Each block once, in order. No run time limit."),
        (Plan([Block("b", [NEAR])], order=Cyclic()),
         "In order, over and over: until a time limit, a stop or the out-of-cage limit."),
        (Plan([Block("b", [NEAR])], order=Balanced()),
         "never one type twice in a row: round after round until a time limit, a stop or the "
         "out-of-cage limit."),
        (Plan([Block("b", [NEAR], criterion=(0.8, 10))], order=ByCriterion()),
         "up one when a stage's rule is met or its time runs out; no fall-back; the top stage"),
        (Plan([Block("b", [NEAR], order=WithReplacement())]),
         "| b | every target used up | drawn with replacement | each condition's structure's "
         "table | no |"),
        (Plan([Block("b", [NEAR], order=WithReplacement(weights={"near": 2.0}))]),
         "| b | every target used up | drawn with replacement, weighted {'near': 2.0} |"),
        (Plan([Block("b", [NEAR], order=Constrained(max_run=1, weights={"near": 2.0}))]),
         "| drawn with replacement, runs of at most 1, weighted {'near': 2.0} |"),
        (Plan([Block("b", [Condition("bare", {}, target=4)])]), "| b | bare | holding | 4 | none |"),
        # A bar in a block's, a condition's or a structure's name is escaped, never a new column.
        (Plan([Block("a|b", [Condition("c|d", {}, target=1, structure="x|y")])]),
         "| a\\|b | c\\|d | x\\|y | 1 | none |"),
        (Plan([Block("a|b", [NEAR])]),
         "| a\\|b | every target used up | shuffled passes |"),
    ],
)
def test_the_plan_tables_say_each_order_draw_and_value_as_declared(plan, said):
    """The final review of engine build C2b, T11: the plan tables' branches the other tests leave
    unread -- a random and a fixed order, a count of none for each order that takes one, no
    fall-back, a draw with replacement, weights, a condition setting nothing -- and a name with a
    bar in it, which `_cell` escapes as it escapes every other cell."""
    structures = {"other": OTHER, "holding": HOLDING, "x|y": OTHER}

    assert said in render_task(_reviewed(structures=structures, plans={"p": plan}))


def test_a_tables_no_limit_is_shown_as_no_limit():
    """XC-380 (engine build C2b): `NO_LIMIT` reads as no repeat limit, never as a number."""
    table = Counting(after_stimulus=SPENT, appears="hold", cap=NO_LIMIT)
    holding = dataclasses.replace(HOLDING, counting=table)
    out = render_task(_reviewed(structures={"holding": holding}))

    assert "no repeat limit: a condition is repeated until done" in out
    assert "a repeat limit of no limit" not in out


def test_each_structure_is_drawn_under_its_own_heading_the_default_first():
    """Engine spec §13.3: several structures, each drawn as `render` draws one, a level down."""
    out = render_task(_reviewed())

    default = out.index("## Structure `holding`, the default")
    assert default < out.index("## Structure `other`")
    assert render(OTHER).replace("## ", "### ") in out
    assert "\n## Trial structure" not in out and "### Trial structure" in out
