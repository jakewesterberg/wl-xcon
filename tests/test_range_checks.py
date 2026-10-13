"""Checks that reason over the values a console can dial in, not the ones set today.

Every parameter here is live-editable between trials, which means a task is not one
configuration but a *space* of them. A check against current values proves the task
happens not to be broken right now; a check against declared ranges proves an
experimenter cannot break it from the console.
"""

import inspect
from dataclasses import replace

from wl_xcon.check import BREAKS_A_RUN, beyond_range, check, widened
from wl_xcon.findings import SESSION_KINDS
from wl_xcon.photometry import SRGB, Gray
from wl_xcon.run import run_trial
from wl_xcon.task import (
    Task,
    After,
    Disc,
    Hold,
    On,
    Outcome,
    P,
    Param,
    Show,
    Square,
    State,
    Stimulus,
    Trial,
    Window,
)

FIX = Stimulus("fix", at=(0.0, 0.0), looks=Disc(size=0.3))


def codes(trial) -> set[str]:
    return {f.code for f in check(trial)}


def found(trial, code):
    """The one finding of `code` that `check` gives `trial`."""
    (one,) = [f for f in check(trial) if f.code == code]
    return one


def two_windows(a_at, a_r, b_at, b_r, params=()) -> Trial:
    return Trial(
        start="wait",
        params=list(params),
        windows=[
            Window("a", at=a_at, radius=a_r, on="fix"),
            Window("b", at=b_at, radius=b_r, on="fix"),
        ],
        states=[
            State(
                "wait",
                enter=[Show(FIX)],
                go=[
                    On(Hold("a", 0.1), Outcome.CORRECT),
                    On(Hold("b", 0.1), Outcome.WRONG_TARGET),
                    On(After(1.0), Outcome.NO_RESPONSE),
                ],
            ),
        ],
    )


def test_windows_that_overlap_are_a_warning_saying_a_look_at_one_can_count_as_the_other():
    """A gaze position inside both scores whichever transition is listed first.

    Which is decided by editing order (M0 §4), and it can relabel errors as correct trials
    or the reverse -- in a task where nothing looks wrong. **A warning, not a refusal**
    (XC-352's A8; the PI, 2026-10-11: "the experimenter needs free control most of the
    time"), accepted in every session kind, saying so.
    """
    warning = found(two_windows((0.0, 0.0), 3.0, (4.0, 0.0), 3.0), "overlapping-windows")

    assert (warning.blocking, warning.accepted_in) == (False, SESSION_KINDS)
    assert "a look at one can count as the other" in warning.detail


def test_windows_that_cannot_overlap_are_accepted():
    assert "overlapping-windows" not in codes(
        two_windows((0.0, 0.0), 2.0, (8.0, 0.0), 2.0)
    )


def test_windows_that_overlap_only_at_an_extreme_of_a_range_are_found():
    """Separated today, overlapping at a setting the console allows."""
    trial = two_windows(
        (0.0, 0.0),
        P("fix_window"),
        (6.0, 0.0),
        2.0,
        params=[Param("fix_window", unit="deg", low=0.5, high=5.0)],
    )
    assert "overlapping-windows" in codes(trial)


def test_a_later_after_that_can_never_fire_first_is_a_review_note():
    """Two time bounds where one always wins.

    The second is dead code that reads as a safety net, so the state it was meant
    to protect against is unprotected and nobody notices, because the line is there.
    """
    trial = Trial(
        start="wait",
        params=[],
        windows=[],
        states=[
            State(
                "wait",
                go=[
                    On(After(0.5), Outcome.NO_RESPONSE),
                    On(After(2.0), Outcome.ABORT),
                ],
            ),
        ],
    )
    findings = [f for f in check(trial) if f.code == "unreachable-timeout"]
    assert findings
    # The message must name *which* timeout is dead. A finding that says a state has
    # an unreachable timeout, without saying which, sends the reader back to the
    # source -- which is the thing these findings exist to replace.
    assert "ABORT" in findings[0].detail
    # A review note, never a refusal (XC-352's A7).
    assert (findings[0].blocking, findings[0].accepted_in) == (False, ())
    assert findings[0].detail.endswith("which is probably a mistake")


def test_two_after_bounds_whose_ranges_cross_are_allowed():
    """Either can win depending on the setting, so neither is dead."""
    trial = Trial(
        start="wait",
        params=[
            Param("short", unit="s", low=0.1, high=3.0),
            Param("long", unit="s", low=0.2, high=1.0),
        ],
        windows=[],
        states=[
            State(
                "wait",
                go=[
                    On(After(P("short")), Outcome.NO_RESPONSE),
                    On(After(P("long")), Outcome.ABORT),
                ],
            ),
        ],
    )
    assert "unreachable-timeout" not in codes(trial)


def test_array_objects_that_can_crowd_into_each_other_are_a_warning():
    """Set size and eccentricity are both live, so crowding is a console setting.

    Twelve objects on a small ring with generous windows overlap, and then a saccade
    to one distractor is scored against another -- or against the target. The
    windows are generated, so no author ever looks at them.
    """
    from wl_xcon.task import Array, ObjectWindows, SaccadeTo

    trial = Trial(
        start="search",
        params=[
            Param("set_size", unit="objects", low=2, high=12),
            Param("array_eccentricity", unit="deg", low=3.0, high=12.0),
            Param("object_window", unit="deg", low=0.5, high=4.0),
        ],
        windows=[ObjectWindows(of="search", radius=P("object_window"))],
        states=[
            State(
                "search",
                enter=[
                    Show(
                        Stimulus(
                            "search",
                            at=(0.0, 0.0),
                            looks=Array(
                                n=P("set_size"),
                                radius=P("array_eccentricity"),
                                target=0,
                            ),
                        )
                    )
                ],
                go=[
                    On(SaccadeTo("search.target"), Outcome.CORRECT),
                    On(After(1.0), Outcome.NO_RESPONSE),
                ],
            ),
        ],
    )
    warning = found(trial, "crowded-array")
    # A warning, not a refusal (XC-352's A9; the PI, 2026-10-11).
    assert (warning.blocking, warning.accepted_in) == (False, SESSION_KINDS)
    assert "a saccade to one would be scored against another" in warning.detail


def test_an_array_that_cannot_crowd_is_accepted():
    from wl_xcon.task import Array, ObjectWindows, SaccadeTo

    trial = Trial(
        start="search",
        params=[
            Param("set_size", unit="objects", low=2, high=6),
            Param("array_eccentricity", unit="deg", low=8.0, high=12.0),
            Param("object_window", unit="deg", low=0.5, high=2.0),
        ],
        windows=[ObjectWindows(of="search", radius=P("object_window"))],
        states=[
            State(
                "search",
                enter=[
                    Show(
                        Stimulus(
                            "search",
                            at=(0.0, 0.0),
                            looks=Array(
                                n=P("set_size"),
                                radius=P("array_eccentricity"),
                                target=0,
                            ),
                        )
                    )
                ],
                go=[
                    On(SaccadeTo("search.target"), Outcome.CORRECT),
                    On(After(1.0), Outcome.NO_RESPONSE),
                ],
            ),
        ],
    )
    assert "crowded-array" not in codes(trial)


# --- A value outside its declared range (the PI, 2026-10-11, XC-352's D2) -------------------


def _windows_task(high: float) -> Task:
    """`two_windows` as a task: `fix_window`'s radius over [0.5, `high`], 6° from a 2° window."""
    trial = two_windows((0.0, 0.0), P("fix_window"), (6.0, 0.0), 2.0,
                        params=[Param("fix_window", unit="deg", low=0.5, high=high, start=1.0)])
    return Task({"windows": trial}, default="windows")


def test_a_value_inside_its_range_is_checked_as_declared_and_adds_nothing():
    assert beyond_range(_windows_task(3.0), {"fix_window": 3.0}) == []
    assert widened(_windows_task(3.0), {"fix_window": 2.0}).params == _windows_task(3.0).params


def test_a_range_is_widened_to_a_value_outside_it_and_nowhere_else():
    task = widened(_windows_task(3.0), {"fix_window": 0.2, "other": 9.0, "fix_hold": "words"})

    (param,) = task.params
    assert (param.low, param.high) == (0.2, 3.0)


def test_a_value_outside_its_range_that_breaks_nothing_is_a_warning_the_task_was_not_designed_for_it():
    """D2: "accept with a warning that the task was not designed for it if nothing breaks"."""
    (warning,) = beyond_range(_windows_task(3.0), {"fix_window": 0.2})

    assert (warning.code, warning.blocking, warning.accepted_in) == (
        "outside-range", False, SESSION_KINDS)
    assert warning.detail.startswith(
        "'fix_window' is 0.2 deg, outside the [0.5, 3.0] the task declares, so the task was not "
        "designed for it")


def test_a_value_outside_its_range_that_makes_windows_collide_is_refused_saying_what():
    """D2: "refuse only what would break the run (off screen, windows colliding, colors
    unmakeable), saying what". Windows that can overlap within the declared ranges are a warning
    at load (A8); widened past them to a value that makes them collide, refused."""
    found = beyond_range(_windows_task(3.0), {"fix_window": 5.0})

    (refusal,) = [f for f in found if f.blocking]
    assert refusal.code == "overlapping-windows" and refusal.code in BREAKS_A_RUN
    assert refusal.detail.startswith(
        "with 'fix_window' at 5, outside its declared range: state 'wait' scores")
    assert [f.code for f in found if not f.blocking] == ["outside-range"]
    assert set(BREAKS_A_RUN) == {"overlapping-windows", "crowded-array", "unrealizable-color"}


def _waiting_task() -> Task:
    """One state waiting on `fix_acquisition` (0.5-10 s) for a fixation, or `fix_hold` (0.05-2 s)
    inside its window; the task's longest declared wait is 10 s."""
    trial = Trial(
        start="wait",
        params=[Param("fix_acquisition", unit="s", low=0.5, high=10.0, start=4.0),
                Param("fix_hold", unit="s", low=0.05, high=2.0, start=0.3)],
        windows=[Window("fix", at=(0.0, 0.0), radius=2.0, on="fix")],
        states=[State("wait", enter=[Show(FIX)], go=[
            On(Hold("fix", P("fix_hold")), Outcome.CORRECT),
            On(After(P("fix_acquisition")), Outcome.NO_FIXATION),
        ])],
    )
    return Task({"waiting": trial}, default="waiting")


def test_a_wait_outside_its_range_but_within_the_tasks_longest_is_a_warning():
    """`fix_hold` at 8 s is outside its 0.05-2 s and within the 10 s the task already waits."""
    assert [(f.code, f.blocking) for f in beyond_range(_waiting_task(), {"fix_hold": 8.0})] == [
        ("outside-range", False)]


def test_a_wait_longer_than_any_the_task_declares_is_a_warning_that_stop_and_the_limit_go_unheard():
    """The plan's call 4, answered by the PI on 2026-10-12: "Allow, with a warning". Stop, pause
    and the out-of-cage limit are heard between trials, never inside one, until they are checked
    about once a second inside a trial (XC-373), so the warning, one per wait, says they go
    unheard until that trial ends, and names the trial cap that ends it at the latest."""
    found = beyond_range(_waiting_task(), {"fix_acquisition": 60.0})

    assert [(f.code, f.blocking, f.accepted_in) for f in found] == [
        ("outside-range", False, SESSION_KINDS), ("longer-than-declared", False, SESSION_KINDS)]
    assert found[1].detail.startswith(
        "'fix_acquisition' at 60 s is a wait longer than any the task declares (its longest, 10 s)")
    assert "they go unheard until that trial ends" in found[1].detail
    # The cap it names is the loop's; build C2a's five-minute cap changes both (engine spec §6.8).
    assert inspect.signature(run_trial).parameters["max_frames"].default == 100_000
    assert "the trial cap, 100,000 frames (about 417 s at 240 Hz)" in found[1].detail


def test_a_literal_wait_counts_toward_the_tasks_longest():
    """A literal `After` of 30 s makes the task's longest wait 30 s, so `fix_acquisition` may go
    to 20 s with a warning."""
    trial = _waiting_task().structures["waiting"]
    state = trial.states[0]
    longer = replace(trial, states=[replace(state, go=[*state.go, On(After(30.0), Outcome.ABORT)])])

    found = beyond_range(Task({"waiting": longer}, default="waiting"), {"fix_acquisition": 20.0})

    assert [(f.code, f.blocking) for f in found] == [("outside-range", False)]


def test_a_finding_the_declared_ranges_already_give_is_not_refused_again():
    """What the declared task's checks already find was accepted with it; only what the
    widening adds is judged."""
    found = beyond_range(_windows_task(5.0), {"fix_window": 0.2})

    assert [f.code for f in found] == ["outside-range"]


def test_a_value_that_only_enlarges_an_overlap_the_task_was_accepted_with_is_a_warning():
    """The warnings-over-refusals review's I5: windows that already overlap at the declared
    extreme were accepted with the task at load (A8); a value past it that only brings them
    closer is about nothing new (`Finding.subjects`: the same state and pair of windows), and is
    a warning saying the value, never a refusal."""
    found = beyond_range(_windows_task(5.0), {"fix_window": 5.2})

    assert [(f.code, f.blocking) for f in found] == [
        ("outside-range", False), ("overlapping-windows", False)]
    assert found[1].detail.startswith(
        "with 'fix_window' at 5.2, outside its declared range: state 'wait' scores")


def _array_task(most: int) -> Task:
    """Two to `most` objects on a ring 8-12° out, each window up to 2° in radius: they crowd past
    twelve objects."""
    from wl_xcon.task import Array, ObjectWindows, SaccadeTo

    trial = Trial(
        start="search",
        params=[Param("set_size", unit="objects", low=2, high=most),
                Param("array_eccentricity", unit="deg", low=8.0, high=12.0),
                Param("object_window", unit="deg", low=0.5, high=2.0)],
        windows=[ObjectWindows(of="search", radius=P("object_window"))],
        states=[State("search", enter=[Show(Stimulus("search", at=(0.0, 0.0), looks=Array(
            n=P("set_size"), radius=P("array_eccentricity"), target=0)))], go=[
            On(SaccadeTo("search.target"), Outcome.CORRECT),
            On(After(1.0), Outcome.NO_RESPONSE),
        ])],
    )
    return Task({"search": trial}, default="search")


def test_an_array_crowded_further_is_a_warning_and_one_newly_crowded_is_refused():
    """The review's I5, for an array: one that crowds at sixteen objects was accepted with the
    task (A9), so twenty is a warning; one that never crowded, at most six, is refused at
    twenty."""
    worse = beyond_range(_array_task(16), {"set_size": 20})
    newly = beyond_range(_array_task(6), {"set_size": 20})

    assert [(f.code, f.blocking) for f in worse] == [
        ("outside-range", False), ("crowded-array", False)]
    assert [(f.code, f.blocking) for f in newly] == [
        ("outside-range", False), ("crowded-array", True)]


def _two_lights(brightest: float) -> Task:
    """A disc lit by `disc`, over 10 to `brightest` cd/m², and a square by `square`, over 10 to
    50: the sRGB default's white is 80 cd/m²."""
    trial = Trial(
        start="on",
        params=[Param("disc", unit="cd/m2", low=10.0, high=brightest, start=20.0),
                Param("square", unit="cd/m2", low=10.0, high=50.0, start=20.0)],
        states=[State("on", enter=[
            Show(Stimulus("d", at=(-2.0, 0.0), looks=Disc(size=1.0, color=Gray(P("disc"))))),
            Show(Stimulus("s", at=(2.0, 0.0), looks=Square(size=1.0, color=Gray(P("square"))))),
        ], go=[On(After(1.0), Outcome.CORRECT)])],
    )
    return Task({"lights": trial}, default="lights")


def test_a_light_clipped_further_is_a_warning_and_one_newly_clipped_is_refused_naming_it():
    """The review's I5, for colors: the disc, which the panel clips at the top of its declared
    range, was accepted with the task (A20), so a value that only clips it further is a warning;
    one that makes the square too bright for the panel, which made it, is refused, naming it."""
    further = beyond_range(_two_lights(100.0), {"disc": 150.0}, calibration=SRGB)
    newly = beyond_range(_two_lights(100.0), {"square": 150.0}, calibration=SRGB)

    assert [f.blocking for f in further if f.code == "unrealizable-color"] == [False]
    (refusal,) = [f for f in newly if f.blocking]
    assert refusal.code == "unrealizable-color"
    assert refusal.detail.endswith("(new with this value: Square)")


def test_an_overlap_new_in_one_structure_is_refused_though_another_has_one_of_the_same_names():
    """What a finding is about is named by its structure in a task of several (`check_task`): two
    structures whose windows share their names, one overlapping at the declared extreme and one
    not, widened until the second overlaps too -- that overlap is new, and refused."""
    def windows(far: float) -> Trial:
        return two_windows((0.0, 0.0), P("fix_window"), (far, 0.0), 2.0,
                           params=[Param("fix_window", unit="deg", low=0.5, high=5.0, start=1.0)])
    task = Task({"near": windows(6.0), "far": windows(10.0)}, default="near")

    found = beyond_range(task, {"fix_window": 9.0})

    (refusal,) = [f for f in found if f.blocking]
    assert refusal.code == "overlapping-windows" and "in structure 'far'" in refusal.detail
