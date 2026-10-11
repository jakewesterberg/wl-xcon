"""The task object (engine spec §3.5; engine build C1): a task file's one `Task` -- its trial
structures by name, the default one its runs play until plans exist (build C2), and what XC-288 §4
has a task declare about itself: what each setting means, what it offers to choose, and how its
reaction time is defined."""

from __future__ import annotations

import pytest

from wl_xcon.check import check, check_task
from wl_xcon.findings import Finding
from wl_xcon.task import (
    BACKGROUND,
    CHOSEN_BY,
    CLEAR_CUT,
    CRITERION,
    EASIER,
    EXPECTED,
    HARDER,
    NEITHER,
    NO_CHOICE,
    NOT_DIFFICULTY,
    STIMULUS,
    After,
    Choice,
    Disc,
    Meaning,
    On,
    Outcome,
    P,
    Param,
    ReactionTime,
    Reward,
    SaccadeTo,
    Show,
    State,
    Stimulus,
    Task,
    Trial,
    Window,
)

HOLD = Param("fix_hold", unit="s", low=0.05, high=2.0, start=0.3)
LONGER_HOLD = Param("fix_hold", unit="s", low=0.05, high=5.0, start=0.3)
WINDOW = Param("fix_window", unit="deg", low=0.5, high=5.0, start=2.0)
CONTRAST = Param("contrast", unit="fraction", low=0.02, high=1.0, start=0.5)


def _trial(*params: Param, view: str = "either", hold: Param = HOLD,
           rewarded: str = "reward_correct") -> Trial:
    """One target, chosen from `wait` by a saccade landing on it, or a `NO_RESPONSE` after
    `fix_hold`; `chose` pays through `rewarded`. Declares `hold` and `params`."""
    return Trial(
        start="wait",
        view=view,
        params=[hold, *params],
        windows=[Window("target", at=(5.0, 0.0), radius=2.0, on="target")],
        states=[
            State(
                "wait",
                enter=[Show(Stimulus("target", at=(5.0, 0.0), looks=Disc(size=1.0)))],
                go=[On(SaccadeTo("target"), "chose"), On(After(P("fix_hold")), Outcome.NO_RESPONSE)],
            ),
            State("chose", go=[On(After(0.1), Outcome.CORRECT, do=[Reward(rewarded)])]),
        ],
    )


def test_a_meaning_is_one_of_three_kinds():
    """TRN-03: clear-cut, expected, or not a difficulty setting; nothing else."""
    with pytest.raises(ValueError, match="a setting's meaning is"):
        Meaning("hard", CRITERION)


def test_a_meaning_says_whether_its_setting_is_a_criterion_or_a_stimulus():
    """The PI, 2026-10-11: each setting says whether it is a criterion (what counts as success) or
    a stimulus (what the animal sees); the bounded settings are neither. Required, as the kind is."""
    with pytest.raises(TypeError, match="role"):
        Meaning(CLEAR_CUT, raising=EASIER)
    with pytest.raises(ValueError, match="a setting's role is"):
        Meaning(CLEAR_CUT, "success", raising=EASIER)

    assert [Meaning(CLEAR_CUT, role, raising=EASIER).role for role in (
        CRITERION, STIMULUS, NEITHER)] == ["criterion", "stimulus", "neither"]


def test_a_clear_cut_or_expected_meaning_says_which_way_raising_it_moves_the_task():
    with pytest.raises(ValueError, match="says which way raising it moves the task"):
        Meaning(CLEAR_CUT, CRITERION)
    with pytest.raises(ValueError, match="says which way raising it moves the task"):
        Meaning(EXPECTED, STIMULUS, raising="up", note="why")

    assert Meaning(CLEAR_CUT, CRITERION, raising=EASIER).raising == EASIER
    assert Meaning(EXPECTED, STIMULUS, raising=HARDER, note="some animals").note == "some animals"


def test_an_expected_direction_comes_with_its_note():
    """XC-288 §4.1: "with the direction expected and a short context note"."""
    for note in ("", "   "):
        with pytest.raises(ValueError, match="comes with a note"):
            Meaning(EXPECTED, STIMULUS, raising=HARDER, note=note)


def test_a_setting_that_is_not_a_difficulty_setting_takes_no_direction():
    with pytest.raises(ValueError, match="takes no direction"):
        Meaning(NOT_DIFFICULTY, STIMULUS, raising=EASIER)
    with pytest.raises(ValueError, match="takes no direction"):
        Meaning(NOT_DIFFICULTY, STIMULUS, relative_to=0)

    assert Meaning(NOT_DIFFICULTY, STIMULUS, note="turns the ring").note == "turns the ring"


def test_a_meanings_words_are_text_and_its_reference_a_number_a_name_or_the_background():
    """A direction reads relative to a reference (the engine C1 plan's call 4): none, a number,
    another setting's name, or the trial's background."""
    with pytest.raises(ValueError, match="note is text"):
        Meaning(CLEAR_CUT, CRITERION, raising=EASIER, note=3)
    with pytest.raises(ValueError, match="overrides the shared one is text"):
        Meaning(CLEAR_CUT, CRITERION, raising=EASIER, overrides=None)
    for wrong in (True, "", float("nan"), [0], (0.0, 0.0)):
        with pytest.raises(ValueError, match="relative_to is None"):
            Meaning(EXPECTED, STIMULUS, raising=HARDER, note="n", relative_to=wrong)

    for reference in (None, 0, -2.5, "green_luminance", BACKGROUND):
        assert Meaning(EXPECTED, STIMULUS, raising=HARDER, note="n",
                       relative_to=reference).relative_to == reference


def test_a_reaction_time_names_its_state_where_it_ends_and_what_it_measures():
    timed = ReactionTime("stim_on", ("verify", Outcome.WRONG_TARGET), "onset to landing")

    assert (timed.state, timed.to) == ("stim_on", ("verify", Outcome.WRONG_TARGET))
    for state, to, note in [
        ("", ("verify",), "x"),
        ("stim_on", (), "x"),
        ("stim_on", ["verify"], "x"),
        ("stim_on", (3,), "x"),
        ("stim_on", ("verify",), " "),
    ]:
        with pytest.raises(ValueError):
            ReactionTime(state, to, note)


def test_a_choice_names_its_items_and_the_act_that_chooses_one():
    assert tuple(CHOSEN_BY) == ("saccade", "gaze", "touch", "lever")
    assert Choice(("search.target", "search.distractor"), "saccade").by == "saccade"
    with pytest.raises(ValueError, match="is made by saccade, gaze, touch, lever"):
        Choice(("target",), "wink")
    for items in [(), ("",), ["target"], (3,)]:
        with pytest.raises(ValueError):
            Choice(items, "gaze")


def test_a_task_holds_its_structures_by_name_and_plays_the_default():
    a, b = _trial(view="direct"), _trial(CONTRAST, view="direct")

    task = Task({"a": a, "b": b}, default="b")

    assert task.trial is b and task.view == "direct"
    assert Task({"a": a}, default="a", choice=NO_CHOICE).choice is NO_CHOICE


def test_a_task_refuses_a_shape_it_cannot_be():
    a = _trial()
    for structures, default, said in [
        ({}, "a", "a dict, at least one"),
        ([a], "a", "a dict, at least one"),
        ({"": a}, "", "named by text"),
        ({"a": "a trial"}, "a", "is a Trial"),
        ({"a": a}, "b", "is not one of its structures"),
    ]:
        with pytest.raises(ValueError, match=said):
            Task(structures, default=default)
    for wrong in [
        {"reaction_time": ("stim_on", "verify")},
        {"choice": ("target",)},
        {"meanings": [("contrast", Meaning(CLEAR_CUT, STIMULUS, raising=EASIER))]},
        {"meanings": {"contrast": "clear-cut"}},
    ]:
        with pytest.raises(ValueError):
            Task({"a": a}, default="a", **wrong)


def test_a_tasks_settings_are_its_structures_union_the_defaults_first():
    """Engine spec §3.5: "the union of their declared parameters, which `Session.set` validates
    against". Each name once; the default structure's declaration first."""
    a, b = _trial(WINDOW), _trial(CONTRAST, hold=LONGER_HOLD)

    assert Task({"a": a, "b": b}, default="b").params == [LONGER_HOLD, CONTRAST, WINDOW]
    assert Task({"a": a, "b": b}, default="a").params == [HOLD, WINDOW, CONTRAST]


#: The findings `check_task` adds to a structure's own (engine build C1).
TASK_CODES = frozenset({
    "parameter-mismatch", "view-mismatch", "undeclared-meaning", "override-without-why",
    "bad-meaning", "meaning-for-nothing", "no-reaction-time", "bad-reaction-time",
    "undeclared-choice", "bad-choice", "unhashable-task",
})
TIMED = ReactionTime("wait", ("chose",), "from entering wait to a saccade landing on the target")


def _whole(**over) -> Task:
    """A task declaring everything: a shared setting and its own, its reaction time, its choice."""
    fields = dict(
        structures={"main": _trial(CONTRAST)},
        default="main",
        reaction_time=TIMED,
        choice=Choice(("target",), "saccade"),
        meanings={"contrast": Meaning(CLEAR_CUT, STIMULUS, raising=EASIER)},
    )
    fields.update(over)
    return Task(**fields)


def _task_findings(task: Task, **kwargs) -> list[Finding]:
    """What `check_task` found about the task itself, a structure's own findings left out."""
    return [f for f in check_task(task, **kwargs) if f.code in TASK_CODES]


def _codes(task: Task, **kwargs) -> set[str]:
    return {f.code for f in _task_findings(task, **kwargs)}


def test_a_task_that_declares_everything_adds_no_finding_of_its_own():
    assert _task_findings(_whole()) == []
    assert all(f.blocking for f in _task_findings(_whole(reaction_time=None, choice=None)))


def test_each_structures_findings_name_it_when_the_task_has_several():
    """A one-structure task's findings read as `check`'s always have (call 13)."""
    orphaned = Trial(start="a", states=[State("a", go=[On(After(1.0), Outcome.CORRECT)]),
                                        State("orphan", go=[On(After(1.0), Outcome.CORRECT)])])
    (own,) = [f for f in check(orphaned) if f.code == "unreachable-state"]

    alone = check_task(Task({"only": orphaned}, default="only"))
    both = check_task(Task({"one": orphaned, "two": orphaned}, default="one"))

    assert [f.detail for f in alone if f.code == "unreachable-state"] == [own.detail]
    assert [f.detail for f in both if f.code == "unreachable-state"] == [
        f"in structure 'one': {own.detail}", f"in structure 'two': {own.detail}"]


def test_a_setting_two_structures_declare_differently_is_refused():
    """Engine spec §3.5: one set of settings, which `Session.set` validates against."""
    same = _whole(structures={"a": _trial(CONTRAST), "b": _trial(CONTRAST)}, default="a")
    differ = _whole(structures={"a": _trial(CONTRAST), "b": _trial(CONTRAST, hold=LONGER_HOLD)},
                    default="a")

    assert _codes(same) == set()
    (found,) = _task_findings(differ)
    assert found.code == "parameter-mismatch" and "'fix_hold'" in found.detail
    assert "'a'" in found.detail and "'b'" in found.detail


def test_structures_written_for_different_setups_are_refused():
    task = _whole(structures={"a": _trial(CONTRAST, view="direct"),
                              "b": _trial(CONTRAST, view="stereoscope")}, default="a")

    assert _codes(task) == {"view-mismatch"}


def test_a_setting_with_no_meaning_is_refused_naming_it():
    """XC-288 §4.1: "Required ... a missing declaration cannot be told from a forgotten one"."""
    (found,) = _task_findings(_whole(meanings={}))

    assert found.code == "undeclared-meaning" and "'contrast'" in found.detail


def test_overriding_a_shared_meaning_needs_a_note_saying_why():
    """Review Focus 2; the PI, 2026-10-11: a task overrides a shared meaning "only with a note
    saying why"."""
    own = {"contrast": Meaning(CLEAR_CUT, STIMULUS, raising=EASIER)}
    silent = _whole(meanings={**own, "fix_hold": Meaning(CLEAR_CUT, CRITERION, raising=EASIER)})
    said = _whole(meanings={**own, "fix_hold": Meaning(CLEAR_CUT, CRITERION, raising=EASIER,
                                                       overrides="this task's hold is a reward")})

    (found,) = _task_findings(silent)
    assert found.code == "override-without-why" and "'fix_hold'" in found.detail
    assert _codes(said) == set()


def test_an_override_of_nothing_and_a_meaning_for_no_setting_are_refused():
    """Review Focus 2: a meaning kept for a setting the task no longer declares is refused, and so
    is an override of a name the shared list does not have."""
    stale = _whole(meanings={"contrast": Meaning(CLEAR_CUT, STIMULUS, raising=EASIER),
                             "speed": Meaning(CLEAR_CUT, STIMULUS, raising=HARDER)})
    overriding = _whole(meanings={"contrast": Meaning(CLEAR_CUT, STIMULUS, raising=EASIER,
                                                      overrides="nothing to override")})

    (found,) = _task_findings(stale)
    assert found.code == "meaning-for-nothing" and "'speed'" in found.detail
    (found,) = _task_findings(overriding)
    assert found.code == "bad-meaning" and "'contrast'" in found.detail


def test_a_direction_reads_from_another_declared_setting_and_never_on_a_list_of_choices():
    """Call 4: a direction read relative to a setting reads from another one the task declares;
    a list of choices has no distance from anything, so reads on changing it alone."""
    cue = Param("cue", unit="appearance", choices=("disc", "square"))

    def relative(contrast_to: object, cue_to: object = None) -> Task:
        return _whole(structures={"main": _trial(CONTRAST, cue)}, meanings={
            "contrast": Meaning(EXPECTED, STIMULUS, raising=EASIER, note="n",
                                relative_to=contrast_to),
            "cue": Meaning(EXPECTED, STIMULUS, raising=HARDER, note="n", relative_to=cue_to)})

    for fine in (None, 0, BACKGROUND, "fix_hold"):
        assert _codes(relative(fine)) == set()
    for wrong, named in [("contrast", "'contrast'"), ("speed", "'speed'")]:
        (found,) = _task_findings(relative(wrong))
        assert found.code == "bad-meaning" and named in found.detail
    (found,) = _task_findings(relative(None, cue_to=0))
    assert found.code == "bad-meaning" and "'cue'" in found.detail


def test_a_bounded_setting_the_task_rewards_through_needs_its_meaning_in_the_table():
    """XC-288 §4.1: its meaning comes from `declarations.BOUNDED`, outside `bounds.py`."""
    streak = _whole(structures={"main": _trial(CONTRAST, rewarded="reward_streak")})

    (found,) = _task_findings(streak)
    assert found.code == "undeclared-meaning" and "'reward_streak'" in found.detail


def test_a_task_must_say_how_its_reaction_time_is_defined():
    """XC-288 §4.3: "Every task declares how its reaction time is defined"."""
    assert _codes(_whole(reaction_time=None)) == {"no-reaction-time"}


def test_a_reaction_time_from_a_state_no_structure_has_or_to_where_it_never_goes_is_refused():
    nowhere = _whole(reaction_time=ReactionTime("stim_on", ("chose",), "x"))
    wrong_end = _whole(reaction_time=ReactionTime("wait", ("chose", Outcome.WRONG_TARGET), "x"))
    both_ends = _whole(reaction_time=ReactionTime("wait", ("chose", Outcome.NO_RESPONSE), "x"))

    (found,) = _task_findings(nowhere)
    assert found.code == "bad-reaction-time" and "'stim_on'" in found.detail
    (found,) = _task_findings(wrong_end)
    assert found.code == "bad-reaction-time" and "WRONG_TARGET" in found.detail
    assert _codes(both_ends) == set()


def test_a_task_must_say_what_it_offers_to_choose_even_when_it_is_nothing():
    """The plan's engineering review, I2: an unset choice cannot be told from a forgotten one
    (XC-288 §4.1's reason, for §4.3), so a task offering none says `NO_CHOICE`."""
    (found,) = _task_findings(_whole(choice=None))

    assert found.code == "undeclared-choice" and "NO_CHOICE" in found.detail
    assert _codes(_whole(choice=NO_CHOICE)) == set()


def test_a_choice_names_windows_chosen_by_the_act_it_names():
    """XC-288 §4.3: "which of its items count as choices and what choosing one is"."""
    touched = _whole(choice=Choice(("target",), "touch"))
    elsewhere = _whole(choice=Choice(("target", "elsewhere"), "saccade"))

    (found,) = _task_findings(touched)
    assert found.code == "bad-choice" and "'target'" in found.detail and "touch" in found.detail
    (found,) = _task_findings(elsewhere)
    assert found.code == "bad-choice" and "'elsewhere'" in found.detail


def test_a_task_whose_content_cannot_be_hashed_is_refused():
    """XC-288 §4.4: a run records which version of its task it ran, so a task that cannot be named
    by its content is refused before any run."""
    odd = Param("odd", unit="label", choices=(object(),))
    task = _whole(structures={"main": _trial(CONTRAST, odd)},
                  meanings={"contrast": Meaning(CLEAR_CUT, STIMULUS, raising=EASIER),
                            "odd": Meaning(NOT_DIFFICULTY, STIMULUS)})

    assert "unhashable-task" in _codes(task)
