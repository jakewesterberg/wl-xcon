"""The review artifact.

ADR-0006 rests on this: a task Claude wrote is approved from a rendered diagram, a
code table and a simulation report, **without reading the source**. If that is not
possible, the design failed rather than the reviewer -- so the artifact is a
deliverable, not a convenience.
"""

from __future__ import annotations

from wl_xcon.declarations import COMMON, content_hash
from wl_xcon.review import render, render_task
from wl_xcon.task import (
    After,
    BACKGROUND,
    CLEAR_CUT,
    Choice,
    EASIER,
    EXPECTED,
    HARDER,
    Mark,
    Hold,
    Exited,
    Meaning,
    NO_CHOICE,
    On,
    P,
    Param,
    Outcome,
    ReactionTime,
    Reward,
    SaccadeTo,
    STIMULUS,
    State,
    Task,
    Trial,
    Window,
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
    assert "Needs a fixed head: refused in any session whose head is not fixed" in render_task(
        _reviewed(needs_fixed_head=True))
    assert "None: the task offers no choice." in render_task(_reviewed(choice=NO_CHOICE))
    bare = render_task(_reviewed(reaction_time=None, choice=None))
    assert bare.count("**Not declared.**") == 2


def test_the_report_names_the_task_by_its_content_and_its_bounded_settings():
    out = render_task(_reviewed())

    assert f"Content: `{content_hash(_reviewed())}`" in out
    assert "### Bounded settings it rewards through" in out
    assert "| reward_correct | neither | not a difficulty setting |" in out


def test_each_structure_is_drawn_under_its_own_heading_the_default_first():
    """Engine spec §13.3: several structures, each drawn as `render` draws one, a level down."""
    out = render_task(_reviewed())

    default = out.index("## Structure `holding`, the default")
    assert default < out.index("## Structure `other`")
    assert render(OTHER).replace("## ", "### ") in out
    assert "\n## Trial structure" not in out and "### Trial structure" in out
