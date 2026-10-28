"""The display is state the trial loop owns.

Every check in the system inspects the transition graph. Nothing modelled what was
*on the screen*, so the residual defect class was "correct graph, wrong experiment"
-- and the reference task carried one: it shows a fixation point in `await_fix` and
holds it in `hold_fix`, which is only correct if a `Show` persists. Found by review
2026-08-31.
"""

import dataclasses

import pytest

from wl_xcon.run import Quiet, Scripted, run_trial
from wl_xcon.task import (
    After,
    Disc,
    Entered,
    Hide,
    Hold,
    On,
    Outcome,
    Polar,
    Show,
    State,
    Stimulus,
    Trial,
    Update,
    Window,
    UNCHANGED,
)

FIX = Stimulus("fix", at=(0.0, 0.0), looks=Disc(size=0.3))


def test_a_shown_stimulus_persists_into_the_next_state():
    """The bug, stated as a test.

    Under state-scoped `Show` the fixation point vanishes at the exact frame the
    animal is asked to hold it -- a task that reads correctly, passes every load-time
    check, and runs the wrong experiment.
    """
    trial = Trial(
        start="await_fix",
        windows=[Window("fix", at=(0.0, 0.0), radius=2.0, on="fix")],
        states=[
            State("await_fix", enter=[Show(FIX)], go=[On(Entered("fix"), "hold_fix")]),
            State(
                "hold_fix",
                go=[
                    On(Hold("fix", 0.02), Outcome.CORRECT),
                    On(After(1.0), Outcome.NO_FIXATION),
                ],
            ),
        ],
    )
    world = Scripted(at_frame={}, inside=dict.fromkeys(range(1, 20), "fix"))
    result = run_trial(trial, world, frame_period=0.01)

    assert result.outcome is Outcome.CORRECT
    # It went up on frame 1 and was never taken down.
    assert result.shown == (("fix", 1, None),)


def test_hide_takes_a_stimulus_down():
    trial = Trial(
        start="on",
        windows=[],
        states=[
            State("on", enter=[Show(FIX)], go=[On(After(0.02), "off")]),
            State("off", enter=[Hide("fix")], go=[On(After(0.02), Outcome.CORRECT)]),
        ],
    )
    result = run_trial(trial, Quiet(), frame_period=0.01)

    assert result.outcome is Outcome.CORRECT
    # Up on frame 1; the Hide is decided while processing frame 2, so frame 3 is
    # the first frame without it. Half-open, so the duration is 3 - 1 = 2 frames,
    # which is exactly how long the state lasted.
    assert result.shown == (("fix", 1, 3),)


def test_update_changes_a_stimulus_without_taking_it_down():
    """Change detection needs one uninterrupted stimulus.

    `Hide` then `Show` inserts an offset transient and a blank frame, which is a
    different experiment -- and the transient is precisely the confound the paradigm
    exists to avoid.
    """
    trial = Trial(
        start="on",
        windows=[],
        states=[
            State("on", enter=[Show(FIX)], go=[On(After(0.02), "changed")]),
            State(
                "changed",
                enter=[Update("fix", looks=Disc(size=1.5))],
                go=[On(After(0.02), Outcome.CORRECT)],
            ),
        ],
    )
    result = run_trial(trial, Quiet(), frame_period=0.01)

    # One continuous presentation, not two.
    assert result.shown == (("fix", 1, None),)
    # Decided while processing frame 2, different from frame 3 -- the same
    # one-frame rule the whole display follows.
    assert result.changed == (("fix", 3),)


def test_each_show_and_update_says_what_was_drawn_from_which_frame():
    """XC-399: a trial's row says where each stimulus it showed was, so the loop keeps each
    stimulus as a `Show` put it up and as an `Update` left it, with the first frame it was so --
    every `Show` and every `Update`, in the order they took effect, a stimulus shown again after a
    `Hide` once more. Nothing is resolved in a frame: the record turns them into positions after
    the trial."""
    moved = Update("fix", at=Polar(8.0, 45.0))
    trial = Trial(
        start="on",
        windows=[],
        states=[
            State("on", enter=[Show(FIX)], go=[On(After(0.02), "moved")]),
            State("moved", enter=[moved], go=[On(After(0.02), "off")]),
            State("off", enter=[Hide("fix")], go=[On(After(0.02), "again")]),
            State("again", enter=[Show(FIX)], go=[On(After(0.02), Outcome.CORRECT)]),
        ],
    )
    result = run_trial(trial, Quiet(), frame_period=0.01)

    assert result.placed == (
        (FIX, 1), (dataclasses.replace(FIX, at=Polar(8.0, 45.0)), 3), (FIX, 7))
    assert [(p.stimulus.name, p.frame) for p in result.placed] == [
        ("fix", 1), ("fix", 3), ("fix", 7)]


def test_the_world_is_told_what_is_on_the_display():
    """A world that cannot see the display cannot draw it, and a simulated subject
    that cannot see it is responding to a screen nobody rendered."""
    seen: list[tuple[int, tuple[str, ...]]] = []

    class Watching(Quiet):
        def display(self, visible, frame):
            seen.append((frame, tuple(sorted(visible))))

    trial = Trial(
        start="on",
        windows=[],
        states=[
            State("on", enter=[Show(FIX)], go=[On(After(0.02), "off")]),
            State("off", enter=[Hide("fix")], go=[On(After(0.02), Outcome.CORRECT)]),
        ],
    )
    run_trial(trial, Watching(), frame_period=0.01)

    assert (1, ("fix",)) in seen
    assert (3, ()) in seen


def test_showing_a_stimulus_that_is_already_up_is_refused():
    """Two live stimuli under one name would make `Hide` and `Update` ambiguous."""
    trial = Trial(
        start="on",
        windows=[],
        states=[
            State("on", enter=[Show(FIX)], go=[On(After(0.02), "again")]),
            State("again", enter=[Show(FIX)], go=[On(After(0.02), Outcome.CORRECT)]),
        ],
    )
    with pytest.raises(ValueError, match="already on the display"):
        run_trial(trial, Quiet(), frame_period=0.01)


def test_updating_a_stimulus_that_is_not_up_is_refused():
    trial = Trial(
        start="on",
        windows=[],
        states=[
            State(
                "on",
                enter=[Update("fix", at=(1.0, 0.0))],
                go=[On(After(0.02), Outcome.CORRECT)],
            ),
        ],
    )
    with pytest.raises(ValueError, match="not on the display"):
        run_trial(trial, Quiet(), frame_period=0.01)


def test_the_unchanged_sentinel_identifies_itself():
    """`UNCHANGED` is a sentinel, and a sentinel's whole job in a traceback, a diff or
    a debugger is to be recognisable. Degraded to the default
    `<Unchanged object at 0x...>` it becomes noise in exactly the situation it exists
    to clarify -- which field of an `Update` was deliberately left alone.

    A thin test, and named honestly as one. It was written because the mutation gate
    reported `Unchanged.__repr__` uncovered once the harness's pattern was fixed
    enough to reach it. The alternative was to teach the harness to honour
    `# pragma: no cover`, and that was rejected: five of this tool's five failures
    have been it being too permissive, and an escape hatch anyone can open with a
    comment is the sixth waiting to happen.
    """
    assert repr(UNCHANGED) == "UNCHANGED"
