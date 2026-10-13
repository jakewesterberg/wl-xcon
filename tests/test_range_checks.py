"""Checks that reason over the values a console can dial in, not the ones set today.

Every parameter here is live-editable between trials, which means a task is not one
configuration but a *space* of them. A check against current values proves the task
happens not to be broken right now; a check against declared ranges proves an
experimenter cannot break it from the console.
"""

from wl_xcon.check import check
from wl_xcon.findings import SESSION_KINDS
from wl_xcon.task import (
    After,
    Disc,
    Hold,
    On,
    Outcome,
    P,
    Param,
    Show,
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
