"""The task object (engine spec §3.5; engine build C1): a task file's one `Task` -- its trial
structures by name, the default one its runs play until plans exist (build C2), and what XC-288 §4
has a task declare about itself: what each setting means, what it offers to choose, and how its
reaction time is defined."""

from __future__ import annotations

import pytest

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
