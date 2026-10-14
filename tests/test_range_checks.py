"""Checks that reason over the values a console can dial in, not the ones set today.

Every parameter here is live-editable between trials, which means a task is not one
configuration but a *space* of them. A check against current values proves the task
happens not to be broken right now; a check against declared ranges proves an
experimenter cannot break it from the console.
"""

import inspect
from dataclasses import replace
from pathlib import Path

import wl_xcon.check as checking
from _rig import DIRECT
from tasks.allocation import ALLOCATION
from wl_xcon import service
from wl_xcon.check import BREAKS_A_RUN, beyond_range, check, check_task, widened
from wl_xcon.cli import _load_task
from wl_xcon.findings import SESSION_KINDS, Finding
from wl_xcon.photometry import SRGB, Gray, Michelson, Weber
from wl_xcon.run import run_trial
from wl_xcon.task import (
    RDS,
    Task,
    After,
    Array,
    Disc,
    Grating,
    Hold,
    ObjectWindows,
    On,
    Outcome,
    P,
    Param,
    Polygon,
    SaccadeTo,
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


def test_a_bound_whose_setting_has_one_bound_is_never_called_dead_by_reading_it_as_0():
    """Task 10's review, fix round 2: `_widest` read a setting with one bound as 0 to 0, so an
    `After` of 2 s racing one up to 3 s was "never reached" -- the 3 s one read as always firing
    at 0. Read over what it can reach (`_span`), from 0 up to 3 s, either can win."""
    trial = Trial(
        start="wait",
        params=[Param("short", unit="s", high=3.0)],
        windows=[],
        states=[State("wait", go=[On(After(P("short")), Outcome.NO_RESPONSE),
                                  On(After(2.0), Outcome.ABORT)])],
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


def test_an_array_whose_size_has_no_highest_or_is_chosen_is_checked_at_its_largest():
    """Task 10's review, I2, for arrays: a set size declared with no highest, or by choices, was
    left out of the ranges and read as 0 objects, which never crowd. With no highest it can be
    any number, and crowds; by choices it is its largest choice; a ring with no lowest can be
    0° (`_span`)."""
    def sized(declared: Param) -> Trial:
        trial = _array_task(6).structures["search"]
        return replace(trial, params=[declared if p.name == declared.name else p
                                      for p in trial.params])

    unbounded = found(sized(Param("set_size", unit="objects", low=2)), "crowded-array")
    ringless = found(sized(Param("array_eccentricity", unit="deg", high=12.0)), "crowded-array")
    any_size = found(sized(Param("object_window", unit="deg", low=0.5)), "crowded-array")

    assert "can put any number of objects on a 8° ring" in unbounded.detail
    assert "can put 6 objects on a 0° ring, 0.00° apart" in ringless.detail
    assert "with windows of any radius" in any_size.detail
    assert "crowded-array" in codes(sized(Param("set_size", unit="objects", choices=(2, 16))))
    assert "crowded-array" not in codes(sized(Param("set_size", unit="objects", choices=(2, 6))))


def test_an_arrays_set_size_is_read_as_the_run_reads_it_a_whole_number():
    """Task 10's re-review, minor: `_crowded_arrays` read a set size's highest as declared, so one
    declared up to 12.5 was checked as 12.5 objects where the run draws twelve (`Array.positions`
    reads `int`), as `_array_faults` and `_declared_window_names` read it (`_whole`): twelve
    objects on an 8° ring are 4.14° apart, clear of two 2° windows, where 12.5 would be
    3.98°."""
    trial = _array_task(6).structures["search"]
    sized = replace(trial, params=[
        Param("set_size", unit="objects", low=2, high=12.5) if p.name == "set_size" else p
        for p in trial.params])

    assert "crowded-array" not in codes(sized)


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


def _target_task() -> Task:
    """A fixation window at the centre, 1° in radius, and a target window 2° in radius anywhere
    over x 4-16° and y ±8°, both scored in one state: within their ranges never nearer than 4°,
    beyond the 3° their radii sum to."""
    trial = Trial(
        start="wait",
        params=[Param("target_x", unit="deg", low=4.0, high=16.0, start=8.0),
                Param("target_y", unit="deg", low=-8.0, high=8.0, start=0.0)],
        windows=[Window("fix", at=(0.0, 0.0), radius=1.0, on="fix"),
                 Window("target", at=(P("target_x"), P("target_y")), radius=2.0, on="fix")],
        states=[State("wait", enter=[Show(FIX)], go=[
            On(Hold("target", 0.1), Outcome.CORRECT),
            On(Hold("fix", 0.1), Outcome.WRONG_TARGET),
            On(After(1.0), Outcome.NO_RESPONSE),
        ])],
    )
    return Task({"w": trial}, default="w")


def test_a_value_that_brings_a_window_onto_another_between_the_corners_of_its_ranges_is_refused():
    """Task 10's review, I2: the least distance between two windows was taken over the corners of
    their position ranges, so a target widened to x 0-16° and y ±8° was never nearer the fixation
    window than its corners, 8°, though at (0, 0) it sits on it. Per axis, the distance between
    the two ranges, 0 where they overlap (`_closest_approach`): refused, naming the value and the
    windows; a value that keeps them apart is only outside its range."""
    found = beyond_range(_target_task(), {"target_x": 0.0})

    assert "overlapping-windows" not in {f.code for f in check_task(_target_task())}
    (refusal,) = [f for f in found if f.blocking]
    assert refusal.code == "overlapping-windows"
    assert refusal.detail.startswith(
        "with 'target_x' at 0, outside its declared range: state 'wait' scores 'target' and "
        "'fix', which can come within 0.00°")
    assert [(f.code, f.blocking) for f in beyond_range(_target_task(), {"target_x": 3.5})] == [
        ("outside-range", False)]


def _chosen_target(xs: tuple) -> Task:
    """A fixation window at the centre and a target window at x one of `xs` (choices), y 0, both
    scored in one state, each radius declared over [0.5, 2]."""
    trial = Trial(
        start="wait",
        params=[Param("target_x", unit="deg", choices=xs),
                Param("fix_window", unit="deg", low=0.5, high=2.0, start=1.0),
                Param("target_window", unit="deg", low=0.5, high=2.0, start=1.0)],
        windows=[Window("fix", at=(0.0, 0.0), radius=P("fix_window"), on="fix"),
                 Window("target", at=(P("target_x"), 0.0), radius=P("target_window"), on="fix")],
        states=[State("wait", enter=[Show(FIX)], go=[
            On(Hold("target", 0.1), Outcome.CORRECT),
            On(Hold("fix", 0.1), Outcome.WRONG_TARGET),
            On(After(1.0), Outcome.NO_RESPONSE),
        ])],
    )
    return Task({"w": trial}, default="w")


def test_a_window_placed_by_choices_is_at_each_choice_never_between_them():
    """The final review's I2: a coordinate given by choices was read as the interval between its
    least and greatest choice, so a target window at x -10° or 10° was said at load to come
    within 0.00° of a fixation window at the centre (`overlapping-windows`), though it is always
    10° from it and their radii sum to at most 4°; and `fix_window` sent at 9°, where the two
    truly collide, was then the same pair only larger, a warning. **Each choice is a point**
    (`_closest_approach`): nothing at load, and 9° refused, as it is with the target at -10° or
    -8°."""
    assert "overlapping-windows" not in {f.code for f in check_task(_chosen_target((-10.0, 10.0)))}
    for xs, gap in (((-10.0, 10.0), "10.00"), ((-10.0, -8.0), "8.00")):
        found = beyond_range(_chosen_target(xs), {"fix_window": 9.0})

        (refusal,) = [f for f in found if f.blocking]
        assert refusal.code == "overlapping-windows"
        assert refusal.detail.startswith(
            f"with 'fix_window' at 9, outside its declared range: state 'wait' scores 'target' "
            f"and 'fix', which can come within {gap}° while their radii sum to 11.00°")


def test_a_radius_declared_only_up_to_a_bound_is_refused_past_it_when_the_windows_then_collide():
    """Task 10's review, I2: a setting with one bound was left out of the ranges and read as
    (0, 0), so a radius declared up to 3° alone, sent at 9° with a window 6° away, was only a
    warning. A radius' missing lowest is 0, and the value widens the bound it lies beyond, so the
    radius is checked over [0, 9]: refused. Its `outside-range` warning names the one bound
    declared, never `None` (the review's M2)."""
    trial = two_windows((0.0, 0.0), P("fix_window"), (6.0, 0.0), 2.0,
                        params=[Param("fix_window", unit="deg", high=3.0, start=1.0)])
    task = Task({"windows": trial}, default="windows")

    found = beyond_range(task, {"fix_window": 9.0})

    assert "overlapping-windows" not in {f.code for f in check_task(task)}
    (refusal,) = [f for f in found if f.blocking]
    assert refusal.code == "overlapping-windows"
    assert refusal.detail.startswith(
        "with 'fix_window' at 9, outside its declared range: state 'wait' scores 'a' and 'b'")
    assert found[0].detail.startswith(
        "'fix_window' is 9 deg, above its declared 3.0, so the task was not designed for it")
    assert "None" not in found[0].detail


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
    # Its 240 Hz is the rate `wlx taskd` runs at (Task 10's review, M4).
    assert service.FRAME_PERIOD == 1 / 240 and round(100_000 * service.FRAME_PERIOD) == 417


def test_a_literal_wait_counts_toward_the_tasks_longest():
    """A literal `After` of 30 s makes the task's longest wait 30 s, so `fix_acquisition` may go
    to 20 s with a warning."""
    trial = _waiting_task().structures["waiting"]
    state = trial.states[0]
    longer = replace(trial, states=[replace(state, go=[*state.go, On(After(30.0), Outcome.ABORT)])])

    found = beyond_range(Task({"waiting": longer}, default="waiting"), {"fix_acquisition": 20.0})

    assert [(f.code, f.blocking) for f in found] == [("outside-range", False)]


def _timing_out(timeout: Param) -> Task:
    """`_waiting_task` with a third wait, `After(P("timeout"))`, its setting declared as
    `timeout`."""
    trial = _waiting_task().structures["waiting"]
    state = trial.states[0]
    return Task({"waiting": replace(
        trial, params=[*trial.params, timeout],
        states=[replace(state, go=[*state.go, On(After(P("timeout")), Outcome.ABORT)])],
    )}, default="waiting")


def test_a_wait_with_no_highest_makes_no_wait_longer_than_any_the_task_declares():
    """Task 10's review, M1: a wait setting with no highest was left out of the task's longest
    wait, so one sent below its lowest was "a wait longer than any the task declares (its
    longest, 0 s)". With no highest a wait can be any length, so no value of any wait is longer
    than one the task declares. Its `outside-range` warning names the one bound declared (M2)."""
    task = _timing_out(Param("timeout", unit="s", low=1.0, start=2.0))

    below = beyond_range(task, {"timeout": 0.5})

    assert [f.code for f in beyond_range(task, {"fix_acquisition": 600.0})] == ["outside-range"]
    assert [(f.code, f.blocking) for f in below] == [("outside-range", False)]
    assert below[0].detail.startswith(
        "'timeout' is 0.5 s, below its declared 1.0, so the task was not designed for it")
    assert "None" not in below[0].detail


def test_a_wait_declared_by_choices_counts_its_longest_choice():
    """Task 10's review, M1: a wait setting declared by choices was left out of the task's
    longest wait; it counts by its largest choice that is a number."""
    task = _timing_out(Param("timeout", unit="s", choices=(1.0, 30.0)))

    within = beyond_range(task, {"fix_acquisition": 20.0})
    longer = beyond_range(task, {"fix_acquisition": 60.0})

    assert [f.code for f in within] == ["outside-range"]
    assert [f.code for f in longer] == ["outside-range", "longer-than-declared"]
    assert "a wait longer than any the task declares (its longest, 30 s)" in longer[1].detail


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


def _search(object_window: float = 1.0, targets: tuple = (), distractors: tuple = ()) -> Task:
    """`tasks/visual_search.py`, its 1° objects on a ring 5-14° out, with its object windows
    declared up to `object_window`° (1° as written; at 3° it loads with `crowded-array` among
    its warnings) and `targets` and `distractors` added to the choices of each."""
    task = _load_task(Path(__file__).resolve().parents[1] / "tasks" / "visual_search.py")
    trial = task.structures["search"]

    def declared(param: Param) -> Param:
        if param.name == "object_window":
            return replace(param, high=object_window)
        if param.name == "target_appearance":
            return replace(param, choices=(*param.choices, *targets))
        if param.name == "distractor_appearance":
            return replace(param, choices=(*param.choices, *distractors))
        return param

    return replace(task, structures={
        "search": replace(trial, params=[declared(p) for p in trial.params])})


def _windowless(most: int, looks=Disc(), among=None) -> Task:
    """Two to `most` objects, a target that looks like `looks` among distractors like `among` (1°
    discs, and `looks`, unless said), on a ring 8-12° out, with no object windows."""
    trial = Trial(
        start="search",
        params=[Param("set_size", unit="objects", low=2, high=most),
                Param("array_eccentricity", unit="deg", low=8.0, high=12.0)],
        states=[State("search", enter=[Show(Stimulus("search", at=(0.0, 0.0), looks=Array(
            n=P("set_size"), radius=P("array_eccentricity"), target=0, looks=looks,
            among=looks if among is None else among)))], go=[
            On(After(1.0), Outcome.NO_RESPONSE),
        ])],
    )
    return Task({"search": trial}, default="search")


def _on_the_rig(task: Task, values: dict) -> list[Finding]:
    """`beyond_range` as a session in direct view on the default calibration checks it, with the
    reference allocation."""
    return beyond_range(task, values, ALLOCATION, geometry=DIRECT, calibration=SRGB)


def test_a_set_size_past_its_range_that_draws_its_objects_on_one_another_is_refused():
    """The final review's I1: a set size sent past its range was judged only by what the
    widened checks find, so an array already crowded at load (`crowded-array`, a warning since
    A9), or one with no object windows, took 1000 or 1e9 objects with warnings alone -- and the
    run then stalls building every object and its window before a trial's first frame, a stop,
    a pause and the out-of-cage limit unheard: what D2 refuses. **Refused**, whatever the task
    was accepted with, once adjacent objects on the tightest ring would sit closer than the
    smallest object is across, saying so: `visual_search` with its object windows declared up to
    3° (the review's probe), the crowded array of the I5 test, and an array with no windows."""
    for task, ring in ((_search(object_window=3.0), 5), (_array_task(16), 8), (_windowless(6), 8)):
        for n in (1000, 1e9):
            found = _on_the_rig(task, {"set_size": n})

            (refusal,) = [f for f in found if f.blocking]
            assert refusal.code == "overlapping-objects"
            assert refusal.detail.startswith(
                f"with 'set_size' at {n:g}, outside its declared range: array 'search' at {n:g} "
                f"objects would put adjacent objects ")
            assert (f"apart on its {ring}° ring, closer than its smallest object is across (1°), "
                    f"so they would be drawn on one another") in refusal.detail
            assert "a stop, a pause and the out-of-cage limit unheard" in refusal.detail


def test_a_set_size_past_its_range_whose_objects_stay_apart_on_the_tightest_ring_is_a_warning():
    """I1's refusal reads the ring at its least and the objects at their smallest, never their
    windows: on `visual_search`'s 5° ring, with its windows declared up to 3° (crowded at load,
    so a larger array is a warning), 13 of its 1° objects and 31, 1.01° apart, are warnings,
    and 32, 0.98° apart, refused; with a 3° target and a 3° distractor among its choices,
    twenty objects 1.56° apart, the smallest still clear of each other, are a warning, as twenty
    3° targets among 1° distractors are on an 8° ring, 2.50° apart; an array with no windows
    takes thirteen with `outside-range` alone; and a 1° triangle, whose size is the circle
    through its corners, is read by the 0.5° circle inside its sides: sixty on an 8° ring, 0.84°
    apart, a warning, and a thousand refused."""
    crowded = _search(object_window=3.0)
    for n in (13, 31):
        assert [(f.code, f.blocking) for f in _on_the_rig(crowded, {"set_size": n})] == [
            ("outside-range", False), ("crowded-array", False)]
    assert [(f.code, f.blocking) for f in _on_the_rig(crowded, {"set_size": 32})] == [
        ("outside-range", False), ("crowded-array", False), ("overlapping-objects", True)]
    (refusal,) = [f for f in _on_the_rig(crowded, {"set_size": 32}) if f.blocking]
    assert "0.98° apart on its 5° ring" in refusal.detail
    three = (Disc(size=3.0, color=Gray(16.0)),)
    larger = _search(object_window=3.0, targets=three, distractors=three)
    assert [(f.code, f.blocking) for f in _on_the_rig(larger, {"set_size": 20})] == [
        ("outside-range", False), ("crowded-array", False)]
    assert [(f.code, f.blocking) for f in beyond_range(
        _windowless(6, looks=Disc(size=3.0), among=Disc(size=1.0)), {"set_size": 20})] == [
        ("outside-range", False)]
    assert [(f.code, f.blocking) for f in beyond_range(_windowless(6), {"set_size": 13})] == [
        ("outside-range", False)]
    triangles = _windowless(6, looks=Polygon(sides=3, size=1.0))
    assert [(f.code, f.blocking) for f in beyond_range(triangles, {"set_size": 60})] == [
        ("outside-range", False)]
    (refusal,) = [f for f in beyond_range(triangles, {"set_size": 1000}) if f.blocking]
    assert "closer than its smallest object is across (0.5°)" in refusal.detail


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
    # What a clip is about names the color as the task wrote it (Task 10's review, I1).
    assert refusal.detail.endswith(
        "(new with this value: Square asking for Gray(cd_m2=P(name='square')))")


def _two_discs() -> Task:
    """Two plain discs: one lit by `disc_a`, over 10-100 cd/m², which the sRGB default's
    80 cd/m² white clips at load, and one by `disc_b`, over 10-50, which it never clips."""
    trial = Trial(
        start="on",
        params=[Param("disc_a", unit="cd/m2", low=10.0, high=100.0, start=20.0),
                Param("disc_b", unit="cd/m2", low=10.0, high=50.0, start=20.0)],
        states=[State("on", enter=[
            Show(Stimulus("a", at=(-2.0, 0.0), looks=Disc(size=1.0, color=Gray(P("disc_a"))))),
            Show(Stimulus("b", at=(2.0, 0.0), looks=Disc(size=1.0, color=Gray(P("disc_b"))))),
        ], go=[On(After(1.0), Outcome.CORRECT)])],
    )
    return Task({"lights": trial}, default="lights")


def test_a_value_that_newly_clips_a_second_appearance_of_one_type_is_refused_naming_it():
    """Task 10's review, I1: a clip was about its appearance's type, so a disc a value newly
    clipped was "about" the other disc's clip, which the task was accepted with, and only a
    warning. A clip is about what asks for its light and the color as the task wrote it
    (`Finding.subjects`): `disc_b` newly clipped is refused, naming it -- at 150, and at 100,
    where its light is the very light `disc_a` already asks for -- while `disc_a` clipped
    further is a warning."""
    newly = beyond_range(_two_discs(), {"disc_b": 150.0}, calibration=SRGB)
    same_light = beyond_range(_two_discs(), {"disc_b": 100.0}, calibration=SRGB)
    further = beyond_range(_two_discs(), {"disc_a": 150.0}, calibration=SRGB)

    for found, value in ((newly, "150"), (same_light, "100")):
        (refusal,) = [f for f in found if f.blocking]
        assert refusal.code == "unrealizable-color"
        assert refusal.detail.startswith(f"with 'disc_b' at {value}, outside its declared range: ")
        assert refusal.detail.endswith(
            "(new with this value: Disc asking for Gray(cd_m2=P(name='disc_b')))")
    # The light both ask for at 100 is said once, naming the disc once (`_clips`).
    (refusal,) = [f for f in same_light if f.blocking]
    assert refusal.detail.count("Disc asks for xyY(x=0.3127, y=0.329, Y=100.0)") == 1
    assert "Disc and Disc" not in refusal.detail
    assert [(f.code, f.blocking) for f in further] == [
        ("outside-range", False), ("unrealizable-color", False)]


def _two_contrasts(make) -> Task:
    """Two stimuli `make` makes on a 60 cd/m² background: one at contrast `strong`, over 0-0.5,
    whose brightest light, 90 cd/m², the sRGB default's 80 cd/m² white clips at load, and one at
    `weak`, over 0-0.2, whose 72 cd/m² it never clips."""
    trial = Trial(
        start="on",
        background=Gray(60.0),
        params=[Param("strong", unit="contrast", low=0.0, high=0.5, start=0.1),
                Param("weak", unit="contrast", low=0.0, high=0.2, start=0.1)],
        states=[State("on", enter=[
            Show(Stimulus("s", at=(-3.0, 0.0), looks=make(P("strong")))),
            Show(Stimulus("w", at=(3.0, 0.0), looks=make(P("weak")))),
        ], go=[On(After(1.0), Outcome.CORRECT)])],
    )
    return Task({"contrasts": trial}, default="contrasts")


def test_a_value_that_newly_clips_a_second_contrast_of_one_type_is_refused_naming_it():
    """Task 10's review, I1, for the lights a contrast makes (`_modulation_faults`): such a clip is
    about what asks for it with its contrast and mean as the task wrote them, so `weak` at 0.5,
    whose light is the very light `strong` already makes, is refused, naming it -- a disc's Weber
    contrast and a grating's Michelson alike."""
    for make, written in (
        (lambda c: Disc(size=1.0, contrast=Weber(c)), "Disc asking for Weber(value=P(name='weak'))"),
        (lambda c: Grating(contrast=Michelson(c)),
         "Grating asking for Michelson(value=P(name='weak')) about its background"),
    ):
        found = beyond_range(_two_contrasts(make), {"weak": 0.5}, calibration=SRGB)

        (refusal,) = [f for f in found if f.blocking]
        assert refusal.code == "unrealizable-color"
        assert refusal.detail.endswith(f"(new with this value: {written})"), written


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


def test_a_finding_that_breaks_a_run_and_names_nothing_it_is_about_is_refused(monkeypatch):
    """`beyond_range` fails closed (Task 10's review, M4): a finding of `BREAKS_A_RUN` the widening
    adds that names nothing it is about cannot be shown to be about something the task was
    accepted with, so it is refused. No check gives one today; one that forgot its subjects must
    not pass as a warning."""
    declared = _windows_task(3.0)
    collide = Finding("overlapping-windows", "two windows collide", blocking=False,
                      accepted_in=SESSION_KINDS)
    monkeypatch.setattr(checking, "check_task",
                        lambda task, *a, **k: [] if task is declared else [collide])

    found = beyond_range(declared, {"fix_window": 5.0})

    assert [(f.code, f.blocking) for f in found] == [
        ("outside-range", False), ("overlapping-windows", True)]
    assert found[1].detail == "with 'fix_window' at 5, outside its declared range: two windows collide"


# --- A setting with one bound, in the checks that refuse (Task 10's review, fix round 2) ------


def _stereogram(correlation: Param) -> Task:
    """A random-dot stereogram whose correlation is `correlation`, on the stereoscope."""
    trial = Trial(
        start="on",
        view="stereoscope",
        params=[correlation],
        states=[State("on", enter=[
            Show(Stimulus("rds", at=(0.0, 0.0), looks=RDS(correlation=P(correlation.name)))),
        ], go=[On(After(1.0), Outcome.CORRECT)])],
    )
    return Task({"stereogram": trial}, default="stereogram")


def test_a_correlation_with_one_bound_is_refused_at_load_and_widened_past_one_refused_again():
    """The fix round's concern 1: `_widest` read a setting with one bound as 0 to 0, so a
    correlation declared up to 1 alone passed at load -- though a console can send it any value
    below, unchecked -- and sent at 2 passed the widened check too: an impossible stereogram
    accepted, the run failing mid-trial, what D2 refuses. Read over what it can reach (`_span`),
    its undeclared lowest is without end: refused at load, saying so, and at 2 refused again,
    naming the value. A correlation declared over [-0.5, 0.5] passes at load, and sent at 0.9,
    a correlation still, is only outside its range. **The refusal names the setting and the fix**
    (Task 10's re-review, minor; the PI kept the refusal on 2026-10-14, I4)."""
    one_bound = _stereogram(Param("c", unit="r", high=1.0, start=0.5))
    control = _stereogram(Param("c", unit="r", low=-0.5, high=0.5, start=0.2))

    (declared,) = [f for f in check_task(one_bound) if f.code == "impossible-correlation"]
    (refusal,) = [f for f in beyond_range(one_bound, {"c": 2.0}) if f.blocking]

    assert declared.blocking and "whose correlation has no declared lowest;" in declared.detail
    assert declared.detail.endswith("; 'c' declares no lowest; declare both limits")
    assert refusal.code == "impossible-correlation"
    assert refusal.detail.startswith(
        "with 'c' at 2, outside its declared range: state 'on' shows a stereogram whose "
        "correlation reaches 2 and has no declared lowest;")
    assert "impossible-correlation" not in {f.code for f in check_task(control)}
    assert [(f.code, f.blocking) for f in beyond_range(control, {"c": 0.9})] == [
        ("outside-range", False)]


def _targeted(target: Param) -> Task:
    """Four objects on a ring 8° out, the target the one `target` indexes."""
    trial = Trial(
        start="search",
        params=[target],
        windows=[ObjectWindows(of="search", radius=1.0)],
        states=[State("search", enter=[Show(Stimulus("search", at=(0.0, 0.0), looks=Array(
            n=4, radius=8.0, target=P(target.name))))], go=[
            On(SaccadeTo("search.target"), Outcome.CORRECT),
            On(After(1.0), Outcome.NO_RESPONSE),
        ])],
    )
    return Task({"search": trial}, default="search")


def test_a_target_index_with_one_bound_is_refused_at_load_and_widened_past_the_array_again():
    """The fix round's concern 1, for an array: a target index declared up to 1 alone was read as
    0 to 0, so it passed at load -- though a console can send it below 0, unchecked, where the
    target window is none of the objects -- and sent at 6, past four objects, passed the widened
    check too, the run then failing as the trial expands its windows. Refused at load, saying
    its lowest is undeclared, and at 6 refused again, naming the value; one declared over [0, 1]
    passes at load, and sent at 3, still one of the four, is only outside its range. The refusal
    names the setting and the fix, as a set size with no lowest does (Task 10's re-review, minor;
    the PI kept the refusal on 2026-10-14, I4)."""
    one_bound = _targeted(Param("ti", unit="index", high=1, start=0))
    control = _targeted(Param("ti", unit="index", low=0, high=1, start=0))

    (declared,) = [f for f in check_task(one_bound) if f.code == "target-outside-array"]
    (refusal,) = [f for f in beyond_range(one_bound, {"ti": 6}) if f.blocking]

    assert declared.blocking and (
        "with a target index reaching 1 that can be below 0, its lowest undeclared;"
        in declared.detail)
    assert declared.detail.endswith("; 'ti' declares no lowest; declare both limits")
    assert refusal.code == "target-outside-array"
    assert refusal.detail.startswith(
        "with 'ti' at 6, outside its declared range: state 'search' shows an array of as few "
        "as 4 objects with a target index reaching 6 that can be below 0")
    assert "target-outside-array" not in {f.code for f in check_task(control)}
    assert [(f.code, f.blocking) for f in beyond_range(control, {"ti": 3})] == [
        ("outside-range", False)]
    sized = replace(control.structures["search"], params=[
        *control.params, Param("n", unit="objects", high=6, start=4)])
    sized = replace(sized, states=[replace(sized.states[0], enter=[Show(Stimulus(
        "search", at=(0.0, 0.0), looks=Array(n=P("n"), radius=8.0, target=P("ti"))))])])
    (fewest,) = [f for f in check(sized) if f.code == "target-outside-array"]
    assert fewest.detail.startswith("state 'search' shows an array of as few as 0 objects")
    assert fewest.detail.endswith("; 'n' declares no lowest; declare both limits")
