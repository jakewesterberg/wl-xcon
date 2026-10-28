"""The display is state the trial loop owns.

Every check in the system inspects the transition graph. Nothing modelled what was
*on the screen*, so the residual defect class was "correct graph, wrong experiment"
-- and the reference task carried one: it shows a fixation point in `await_fix` and
holds it in `hold_fix`, which is only correct if a `Show` persists. Found by review
2026-08-31.
"""

import dataclasses

import pytest

from wl_xcon.run import Placed, Quiet, Scripted, run_trial
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
    `Hide` once more -- and, so the row reads as a timeline (the review's I3), which it was, the
    fields an `Update` set, its presentation in `shown`, and the first frame that presentation was
    off the display (null when it was on through the trial's last frame). Nothing is resolved in a
    frame: the record turns them into positions after the trial."""
    moved = Update("fix", at=Polar(8.0, 45.0), opacity=0.5)
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

    # Shown on 1, moved on 3, hidden on 5, shown again on 7; the trial's last frame is 8.
    assert result.frames == 8
    assert result.placed == (
        Placed(FIX, 1, "show", (), 0, 5),
        Placed(dataclasses.replace(FIX, at=Polar(8.0, 45.0), opacity=0.5), 3, "update",
               ("at", "opacity"), 0, 5),
        Placed(FIX, 7, "show", (), 1, None),
    )


def test_what_a_trial_puts_up_on_its_way_out_was_never_drawn_and_is_not_placed():
    """The review's I2: a `Show` or `Update` on an edge to an outcome takes effect on the frame
    after the trial's last, so it was never on the screen, and the row must not say where it was.
    A `Hide` on that edge leaves the stimulus on through the last frame: its presentation never
    went off within the trial."""
    late = Stimulus("late", at=(3.0, 0.0), looks=Disc(size=0.3))
    trial = Trial(
        start="on",
        windows=[],
        states=[State("on", enter=[Show(FIX)], go=[On(After(0.02), Outcome.CORRECT, do=[
            Show(late), Update("fix", at=(1.0, 1.0)), Hide("fix")])])],
    )
    result = run_trial(trial, Quiet(), frame_period=0.01)

    assert result.frames == 2
    assert result.placed == (Placed(FIX, 1, "show", (), 0, None),)


def test_a_stimulus_up_for_no_frame_is_not_placed_and_one_changed_as_it_appears_is_two_entries():
    """The re-review of XC-399, its minor 2: a `Show` and a `Hide` on one transition -- or an
    `Update` and a `Hide` -- take effect on one frame, so what they describe was on the screen for
    no frame and has no entry; the presentation's `Show` keeps its own, `off` the frame it went.
    A `Show` and an `Update` on one frame stay two entries at that frame, the `Show`'s describing
    for no frame what the `Update` then changed, as the ask says such pairs can occur."""
    flash = Stimulus("flash", at=(3.0, 0.0), looks=Disc(size=0.3))
    trial = Trial(
        start="on",
        windows=[],
        states=[
            State("on", enter=[Show(FIX)], go=[On(After(0.02), "next", do=[
                Show(flash), Hide("flash"), Update("fix", at=(1.0, 1.0)), Hide("fix")])]),
            State("next", go=[On(After(0.02), Outcome.CORRECT)]),
        ],
    )
    result = run_trial(trial, Quiet(), frame_period=0.01)

    assert result.placed == (Placed(FIX, 1, "show", (), 0, 3),)

    dimmed = Trial(start="on", windows=[], states=[State(
        "on", enter=[Show(FIX), Update("fix", opacity=0.5)],
        go=[On(After(0.02), Outcome.CORRECT)])])
    result = run_trial(dimmed, Quiet(), frame_period=0.01)

    assert result.placed == (
        Placed(FIX, 1, "show", (), 0, None),
        Placed(dataclasses.replace(FIX, opacity=0.5), 1, "update", ("opacity",), 0, None),
    )


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
