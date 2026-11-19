"""Executing a declarative trial.

The framework runs the task; the task never owns the frame loop (ADR-0006). These
tests are about that loop -- and they are the same loop the rig runs, with a
simulated world substituted for hardware.
"""

from __future__ import annotations

import pytest

from wl_xcon.run import (
    LONGEST_TRIAL_S, Quiet, Recorded, Scripted, longest_trial_frames, run_trial,
)
from wl_xcon.task import (
    After,
    Disc,
    Entered,
    Mark,
    Exited,
    Hold,
    On,
    Outcome,
    P,
    Param,
    Reward,
    SaccadeTo,
    Score,
    Show,
    State,
    Stimulus,
    Tolerances,
    Trial,
    Update,
    Window,
)


def test_the_longest_trial_is_five_minutes_at_the_sessions_rate():
    """Engine spec §6.8: "the loop's frame cap derived from 300 s at the session's rate" (XC-287).
    It was 100,000 frames whatever the rate, about 417 s at 240 Hz."""
    assert LONGEST_TRIAL_S == 300.0
    assert longest_trial_frames(1 / 240) == 72_000
    assert longest_trial_frames(1 / 120) == 36_000
    assert longest_trial_frames(0.7) == 429, "to the nearest frame: 428.57"


@pytest.mark.parametrize("frame_period", [1.0, 0.5])
def test_a_trial_that_reaches_the_longest_trial_ends_there_with_no_outcome(frame_period):
    """A wait the five minutes cut short: the trial ends at the cap, a hang, whatever its own
    bound. (Slow frames keep the test to a few hundred.)"""
    trial = Trial(start="wait", states=[State("wait", go=[On(After(400.0), Outcome.CORRECT)])])

    result = run_trial(trial, world=Quiet(), frame_period=frame_period)

    assert result.outcome is None
    assert result.frames == round(300 / frame_period)


def test_a_time_guard_fires_on_the_first_frame_at_or_past_its_deadline():
    """The frame quantum is real and the task cannot see it. A 100 ms wait on a
    10 ms frame resolves on frame 10, not at 100 ms -- which is why S1 forbids a
    task assuming a frame period and why V1 measures the real one."""
    trial = Trial(
        start="wait",
        states=[State("wait", go=[On(After(0.1), Outcome.CORRECT)])],
    )

    result = run_trial(trial, world=Quiet(), frame_period=0.01)

    assert result.outcome is Outcome.CORRECT
    assert result.frames == 10


def test_the_clock_restarts_on_state_entry():
    """A hold is 50 ms *after acquisition*, not 50 ms after the trial began. If
    elapsed time were measured from the trial rather than the state, every hold
    would shorten by however long the animal took to look -- an error that gets
    worse the slower the animal is, which is exactly backwards."""
    trial = Trial(
        start="await_fix",
        windows=[Window("fix", at=(0.0, 0.0), radius=2.0)],
        states=[
            State(
                "await_fix",
                go=[
                    On(Entered("fix"), "hold_fix"),
                    On(After(1.0), Outcome.NO_FIXATION),
                ],
            ),
            State("hold_fix", go=[On(After(0.05), Outcome.CORRECT)]),
        ],
    )

    result = run_trial(
        trial,
        world=Scripted({}, inside={frame: "fix" for frame in range(3, 40)}),
        frame_period=0.01,
    )

    assert result.outcome is Outcome.CORRECT
    assert result.frames == 8  # enters on 3, holds 50 ms across frames 4-8


def test_a_world_where_nothing_happens_falls_through_to_the_time_bound():
    trial = Trial(
        start="await_fix",
        windows=[Window("fix", at=(0.0, 0.0), radius=2.0)],
        states=[
            State(
                "await_fix",
                go=[
                    On(Entered("fix"), "hold_fix"),
                    On(After(0.04), Outcome.NO_FIXATION),
                ],
            ),
            State("hold_fix", go=[On(After(0.05), Outcome.CORRECT)]),
        ],
    )

    result = run_trial(trial, world=Quiet(), frame_period=0.01)

    assert result.outcome is Outcome.NO_FIXATION


def test_a_parameter_reference_is_resolved_from_the_trials_bound_values():
    """S8 §3.4: a trial runs against a *resolved* parameter set, snapshotted per
    trial. Found by simulating the first real task, whose guards are all parameter
    references -- the loop compared a float to a `P` and raised."""
    trial = Trial(
        start="wait",
        params=[Param("timeout", unit="s", low=0.01, high=1.0)],
        states=[State("wait", go=[On(After(P("timeout")), Outcome.NO_RESPONSE)])],
    )

    result = run_trial(trial, Quiet(), frame_period=0.01, values={"timeout": 0.05})

    assert result.outcome is Outcome.NO_RESPONSE
    assert result.frames == 5


def test_running_without_a_value_for_a_declared_parameter_is_refused():
    """Not defaulted to zero. A missing timeout that silently becomes 0.0 turns
    every trial into an immediate abort, which looks like an animal that will not
    work rather than like a bug. **Refused by name, in its own words** (`run._unbound`, which
    builds the message as it raises, never on a frame that resolves; XC-414), not as the bare
    lookup's `KeyError`."""
    trial = Trial(
        start="wait",
        params=[Param("timeout", unit="s", low=0.01, high=1.0)],
        states=[State("wait", go=[On(After(P("timeout")), Outcome.NO_RESPONSE)])],
    )

    with pytest.raises(KeyError, match="no value bound for parameter 'timeout'"):
        run_trial(trial, Quiet(), frame_period=0.01, values={})


def test_a_trial_records_every_scored_response_and_still_ends_once():
    """S1a §8. A trial emits scored events as it goes; the terminal outcome
    summarises. Free viewing is then a trial with many scored responses and a
    mundane ending, rather than a shape the model cannot express."""
    trial = Trial(
        start="first",
        windows=[
            Window("a", at=(-10.0, 0.0), radius=2.0),
            Window("b", at=(10.0, 0.0), radius=2.0),
        ],
        states=[
            State(
                "first",
                go=[
                    On(
                        SaccadeTo("a"),
                        "second",
                        do=[Score("a", Outcome.CORRECT)],
                    ),
                    On(After(1.0), Outcome.NO_RESPONSE),
                ],
            ),
            State(
                "second",
                go=[
                    On(
                        SaccadeTo("b"),
                        Outcome.CORRECT,
                        do=[Score("b", Outcome.WRONG_TARGET)],
                    ),
                    On(After(1.0), Outcome.NO_RESPONSE),
                ],
            ),
        ],
    )

    result = run_trial(
        trial,
        Scripted({SaccadeTo("a"): 3, SaccadeTo("b"): 7}),
        frame_period=0.01,
    )

    assert result.outcome is Outcome.CORRECT
    assert [(s.window, s.scored_as, s.frame) for s in result.scored] == [
        ("a", Outcome.CORRECT, 3),
        ("b", Outcome.WRONG_TARGET, 7),
    ]


class _Membership:
    """A world that reports only where gaze is, frame by frame."""

    def __init__(self, inside: dict[int, str]) -> None:
        self.inside = inside

    def in_window(self, window: str, frame: int, eye: str = "both") -> bool:
        return self.inside.get(frame) == window

    def happened(self, guard, state: str, frame: int) -> bool:
        return False

    def began(self, state: str, frame: int) -> None:
        pass

    def signal(self, frame: int) -> str:
        """Always available: these tests are not about signal loss."""
        return "ok"

    def display(self, visible, frame: int) -> None:
        """Blind on purpose: these tests are about how membership becomes entering,
        leaving and holding, which does not depend on what is drawn."""


def test_entered_exited_and_hold_are_derived_from_membership_not_asked_of_the_world():
    """The property that makes worlds interchangeable.

    A world reports *where gaze is*. The loop derives entering, leaving and holding
    from that, so those semantics -- including the staleness policy S5 §4.1
    requires -- exist once. If each world implemented them, the simulator and a
    mouse would disagree about what a hold is, and a person validating a task in
    demo mode would be validating different behaviour from the one an animal gets.
    """
    trial = Trial(
        start="await_fix",
        windows=[Window("fix", at=(0.0, 0.0), radius=2.0)],
        states=[
            State(
                "await_fix",
                go=[
                    On(Entered("fix"), "hold_fix"),
                    On(After(1.0), Outcome.NO_FIXATION),
                ],
            ),
            State(
                "hold_fix",
                go=[
                    On(Hold("fix", 0.03), Outcome.CORRECT),
                    On(Exited("fix"), Outcome.FIXATION_BREAK),
                ],
            ),
        ],
    )
    # inside from frame 2; a hold of 30 ms at 10 ms frames completes on frame 5
    world = _Membership({frame: "fix" for frame in range(2, 40)})

    result = run_trial(trial, world, frame_period=0.01)

    assert result.outcome is Outcome.CORRECT
    # Frame 2 is consumed entering `hold_fix`; the hold there runs 3, 4, 5. A hold
    # cannot count the frame that triggered entry into its own state.
    assert result.frames == 5


def test_leaving_a_window_restarts_a_hold_rather_than_pausing_it():
    """A hold is continuous. Accumulating across a gap would score an animal that
    looked away and back as having held throughout, which is the opposite of what
    the criterion is for."""
    trial = Trial(
        start="hold_fix",
        windows=[Window("fix", at=(0.0, 0.0), radius=2.0)],
        states=[
            State(
                "hold_fix",
                go=[
                    On(Hold("fix", 0.03), Outcome.CORRECT),
                    On(After(0.2), Outcome.NO_RESPONSE),
                ],
            ),
        ],
    )
    # in for two frames, out for one, then in continuously
    inside = {1: "fix", 2: "fix", 4: "fix", 5: "fix", 6: "fix", 7: "fix"}

    result = run_trial(trial, _Membership(inside), frame_period=0.01)

    assert result.outcome is Outcome.CORRECT
    assert result.frames == 6, "the hold restarted at frame 4, completing on 6"


def test_a_hold_is_measured_from_state_entry_not_from_when_gaze_arrived():
    """Found by review, 2026-08-31, and it made correctly-authored tasks wrong.

    `holding_since` was trial-scoped, so a `Hold` in a later state was already
    satisfied by presence that began before that state was entered. A memory-guided
    structure -- hold 0.3 s, then a declared 0.3 s delay with fixation enforced --
    ran the delay for **one frame** and scored CORRECT. Every working-memory delay
    in the v1 inventory is written this way.

    A hold in a state means held continuously *since that state began*.
    """
    trial = Trial(
        start="hold_fix",
        windows=[Window("fix", at=(0.0, 0.0), radius=2.0)],
        states=[
            State(
                "hold_fix",
                go=[
                    On(Hold("fix", 0.3), "delay"),
                    On(After(5.0), Outcome.NO_FIXATION),
                ],
            ),
            State(
                "delay",
                go=[
                    On(Hold("fix", 0.3), Outcome.CORRECT),
                    On(Exited("fix"), Outcome.FIXATION_BREAK),
                    On(After(5.0), Outcome.NO_RESPONSE),
                ],
            ),
        ],
    )
    always_inside = Scripted({}, inside={f: "fix" for f in range(1, 5000)})

    result = run_trial(trial, always_inside, frame_period=0.01)

    assert result.outcome is Outcome.CORRECT
    # 0.3 s to satisfy the first hold, then a further 0.3 s inside `delay`.
    assert result.frames == 60, f"the delay ran {(result.frames - 30) / 100:.2f} s"


# --- An eye already inside a window as its state begins has entered it (the PI, during demo
# mode's try-out, 2026-11-16: "If I am already at the center, i shouldn't have to leave and
# reenter"; decisions.md EYE-30). `Entered` fires on a state's first judged frame on being inside,
# as on gaze coming in from outside on any later frame; `Exited` and holds are unchanged. Until
# then both were edges against the frame before, and membership is judged in every state.


class _Lost(_Membership):
    """`_Membership`, with the tracker lost on the frames `lost`."""

    def __init__(self, inside: dict[int, str], lost: set[int]) -> None:
        super().__init__(inside)
        self.lost = lost

    def signal(self, frame: int) -> str:
        return "lost" if frame in self.lost else "ok"


def _then(asked: list) -> Trial:
    """`blank` for 30 ms (frames 1 to 3, left on frame 3), then `asked`'s edges from frame 4, at
    the default graces (tracker loss forgiven for 50 ms, five 10 ms frames)."""
    return Trial(
        start="blank",
        windows=[Window("fix", at=(0.0, 0.0), radius=2.0)],
        states=[State("blank", go=[On(After(0.03), "asked")]), State("asked", go=asked)],
    )


@pytest.mark.parametrize(("inside", "outcome", "frames"), [
    # Outside all along: an eye outside a window as its state begins has left nothing.
    ({}, Outcome.NO_RESPONSE, 8),
    # Inside through `blank`, out on `asked`'s first frame: it left, as before.
    ({1: "fix", 2: "fix", 3: "fix"}, Outcome.FIXATION_BREAK, 4),
])
def test_exited_at_a_states_start_is_still_an_edge_against_the_frame_before(inside, outcome,
                                                                            frames):
    """**`Exited` is unchanged** (EYE-30, the controller's ruling): an eye outside a window as its
    state begins fires no `Exited`, and one leaving on the state's first judged frame, inside on
    the frame before, still does. So the rule that makes `Entered` fire on a state's first frame is
    not one that forgets the frame before at a transition, which would lose this exit."""
    trial = _then([On(Exited("fix"), Outcome.FIXATION_BREAK), On(After(0.05), Outcome.NO_RESPONSE)])

    result = run_trial(trial, _Membership(inside), frame_period=0.01)

    assert (result.outcome, result.frames) == (outcome, frames)


def test_entered_on_a_frozen_first_frame_fires_on_the_states_first_judged_frame():
    """**A state's first judged frame, not its first frame** (EYE-30, the controller's ruling):
    `asked` begins on frame 4 with the tracker lost on frames 4 and 5, inside the 50 ms grace, so
    the trial's view of gaze is frozen there and no edge is derived (EYE-18). Gaze inside the window
    since frame 1 has entered it on frame 6, the first judged frame, though it was inside on the
    frame before too."""
    trial = _then([On(Entered("fix"), Outcome.CORRECT), On(After(0.2), Outcome.NO_FIXATION)])
    world = _Lost({frame: "fix" for frame in range(1, 40)}, lost={4, 5})

    result = run_trial(trial, world, frame_period=0.01)

    assert (result.outcome, result.frames) == (Outcome.CORRECT, 6)


def test_a_hold_after_an_entered_taken_on_a_states_first_frame_counts_from_its_own_first_frame():
    """**Holds are unchanged** (EYE-30): gaze inside the window from frame 1 has entered it on
    `asked`'s first frame, 4, and the hold that follows counts from `held`'s first frame, 5, never
    from before (entering a state clears every hold, the rule of 2026-08-31): 50 ms of it is frames
    5 to 9."""
    trial = Trial(
        start="blank",
        windows=[Window("fix", at=(0.0, 0.0), radius=2.0)],
        states=[
            State("blank", go=[On(After(0.03), "asked")]),
            State("asked", go=[On(Entered("fix"), "held"), On(After(0.2), Outcome.NO_FIXATION)]),
            State("held", go=[On(Hold("fix", 0.05), Outcome.CORRECT),
                              On(Exited("fix"), Outcome.FIXATION_BREAK),
                              On(After(1.0), Outcome.NO_RESPONSE)]),
        ],
    )

    result = run_trial(trial, _Membership({frame: "fix" for frame in range(1, 200)}),
                       frame_period=0.01)

    assert result.visited == ("blank", "asked", "held")
    assert (result.outcome, result.frames) == (Outcome.CORRECT, 9)


# --- the I/O layer: marks and rewards leaving the loop -----------------------
#
# Until 2026-09-06 `_apply` executed the display actions and silently dropped the
# rest, its comment saying `Mark` and `Reward` "belong to the I/O layer, which has
# no simulator yet". `dio.Simulated` had existed for five days. So the M1 gate ran a
# thousand trials, scored them correct, strobed **no event codes at all** and
# delivered **no reward** -- a session that cannot be aligned to any recording and an
# animal that worked for nothing, both reported clean.


def _rewarding_trial() -> Trial:
    """One frame, one mark, one reward. Small on purpose: these tests are about
    whether an action leaves the loop, not about how a trial reaches its outcome."""
    return Trial(
        start="go",
        states=[
            State(
                "go",
                go=[
                    On(
                        After(0.0),
                        Outcome.CORRECT,
                        do=[Mark(4102), Reward("reward_correct")],
                    )
                ],
            )
        ],
    )


def test_a_mark_reaches_the_effects_port_with_its_code():
    effects = Recorded()

    run_trial(_rewarding_trial(), Quiet(), frame_period=0.01, effects=effects)

    assert ("mark", 4102) in effects.log


def test_a_reward_reaches_the_effects_port_by_name():
    """By name, never by magnitude. The task said which bounded entry; what that
    entry is worth is the bounded config's to say and the task's never."""
    effects = Recorded()

    run_trial(_rewarding_trial(), Quiet(), frame_period=0.01, effects=effects)

    assert ("reward", "reward_correct") in effects.log


def test_the_code_is_strobed_before_the_valve_opens():
    """Declared order, and it is the order that matters: `REWARD_COMMANDED` says a
    reward was commanded, so a stream where it trails the delivery describes a
    different sequence of events from the one that happened."""
    effects = Recorded()

    run_trial(_rewarding_trial(), Quiet(), frame_period=0.01, effects=effects)

    assert effects.log == [("mark", 4102), ("reward", "reward_correct")]


def test_a_reward_with_no_effects_port_refuses_rather_than_being_dropped():
    """`dio.Absent`'s argument, and the reason this whole section exists. A loop that
    silently discards a `Reward` is indistinguishable, from every test and every
    record, from one that delivered it."""
    with pytest.raises(RuntimeError, match="no I/O"):
        run_trial(_rewarding_trial(), Quiet(), frame_period=0.01)


def test_an_entry_action_can_mark_too():
    """Entry actions are where `FIX_ON` and `ARRAY_ON` live, so a loop that only
    walked transitions would emit half the stream."""
    effects = Recorded()
    trial = Trial(
        start="go",
        states=[
            State("go", enter=[Mark(4096)], go=[On(After(0.0), Outcome.CORRECT)])
        ],
    )

    run_trial(trial, Quiet(), frame_period=0.01, effects=effects)

    assert effects.log == [("mark", 4096)]


def test_a_task_that_commands_nothing_needs_no_io_port():
    """Most tests in this file run tasks with no actions at all, and a loop that
    demanded a port regardless would be enforcing a rule about the wrong thing."""
    trial = Trial(start="go", states=[State("go", go=[On(After(0.0), Outcome.CORRECT)])])

    assert run_trial(trial, Quiet(), frame_period=0.01).outcome is Outcome.CORRECT


# --- P4d-2b b2a: the one per-frame hook ------------------------------------------


class _Watched(Quiet):
    """`Quiet`, with every display call logged beside the hook's."""

    def __init__(self, log: list) -> None:
        object.__setattr__(self, "log", log)

    def display(self, visible, frame: int) -> None:
        self.log.append(("display", frame))


def test_each_frame_is_called_once_per_frame_before_anything_else_on_it():
    """P4d-2b spec §5.1: a mark is stamped in the frame it reaches the rig, so the
    session's check runs once per frame, first, before the frame is drawn or any
    guard is read -- the frame it names is the frame it happened in."""
    trial = Trial(
        start="wait",
        states=[State("wait", go=[On(After(0.1), Outcome.CORRECT)])],
    )
    log: list = []

    result = run_trial(
        trial,
        world=_Watched(log),
        frame_period=0.01,
        each_frame=lambda frame: log.append(("each", frame)),
    )

    assert result.frames == 10
    assert log == [
        entry for frame in range(1, 11) for entry in (("each", frame), ("display", frame))
    ]


class _Blinking(Quiet):
    def signal(self, frame: int) -> str:
        return "blink"


def test_each_frame_runs_on_a_frame_the_gaze_signal_was_lost_too():
    """An interrupted frame skips the guards (`continue`), and must not skip the mark
    check: an operator's mark during a blink is still a mark."""
    trial = Trial(
        start="wait",
        states=[State("wait", go=[On(After(10.0), Outcome.CORRECT)])],
        tolerances=Tolerances(blink=None, tracker_lost=None),
    )
    frames: list = []

    run_trial(
        trial, world=_Blinking(), frame_period=0.01, max_frames=20,
        each_frame=frames.append,
    )

    assert frames == list(range(1, 21))


# --- XC-410: the world is told each state's first frame (a `SaccadeTo` counts a saccade whose eye
# stops in its state, a `SaccadeOnset` one that begins in it) ------------------------------------


class _Told(Quiet):
    """`Quiet`, with every state the loop says began logged, with its first frame."""

    def __init__(self, log: list) -> None:
        object.__setattr__(self, "log", log)

    def began(self, state: str, frame: int) -> None:
        self.log.append((state, frame))


def test_the_world_is_told_the_first_frame_of_every_state_the_trial_enters():
    """A `SaccadeOnset` counts a saccade that began in its state (the PI, 2026-10-30) and a
    `SaccadeTo` one whose eye stops in its state, wherever its onset fell (the PI, 2026-11-07), so
    a world that remembers saccades (`gaze.Tracked`) has to know each state's first frame: the
    frame its guards are first asked on and its entry actions first drawn. The start state's is
    frame 1; every other's is the frame after the transition that enters it, **a state entered
    again included**, whose earlier saccades are no more its own than another state's. The edge
    that entered it is not told (it had been, as `by`, until nothing read it): this test asserted
    that guard, and now asserts the state and its first frame alone."""
    trial = Trial(
        start="a",
        states=[
            State("a", go=[On(After(0.03), "b")]),
            State("b", go=[On(After(0.02), "b2")]),
            State("b2", go=[On(After(0.02), "b2")]),
        ],
    )
    log: list = []

    result = run_trial(trial, world=_Told(log), frame_period=0.01, max_frames=12)

    assert result.outcome is None and result.frames == 12
    assert log == [("a", 1), ("b", 4), ("b2", 6), ("b2", 8), ("b2", 10), ("b2", 12)]


# --- TSK-78: a zero wait lasts no frame (the pop-out revision's §3 item 5) -----------------------
#
# The PI's "on one frame": with `go_delay` 0 the array and the go are drawn together. An edge that
# enters a state whose plain `After` resolves to 0 or less takes that `After`'s edge on the same
# frame, its actions applied at the same `frame + 1`; the state lasted no frame, so no other edge of
# it is judged. At most one such pass a frame: the state a pass enters is judged from the next.


def _go_delay_trial(delay_go: "list[On] | None" = None) -> Trial:
    """A dot on from the start; after 30 ms the array is shown on entering `delay`, and the dot
    changes on leaving it after `go_delay`; the go state ends the trial 50 ms on, or on the eye
    leaving the fixation window, the answer."""
    dot = Stimulus("dot", at=(0.0, 0.0), looks=Disc(size=0.3))
    array = Stimulus("array", at=(8.0, 0.0), looks=Disc(size=1.0))
    go = Update("dot", opacity=0.5)
    return Trial(
        start="hold",
        params=[Param("go_delay", unit="s", low=0.0, high=1.0)],
        windows=[Window("fix", at=(0.0, 0.0), radius=2.0)],
        states=[
            State("hold", enter=[Show(dot)], go=[On(After(0.03), "delay")]),
            State("delay", enter=[Show(array)],
                  go=delay_go or [On(After(P("go_delay")), "go", do=[go])]),
            State("go", go=[On(Exited("fix"), Outcome.CORRECT),
                            On(After(0.05), Outcome.NO_RESPONSE)]),
        ],
    )


def test_a_zero_wait_is_passed_on_the_frame_its_state_is_entered():
    """`go_delay` 0: the array shown on entering `delay` and the dot's change on leaving it are
    one frame's, and `delay` is still among the states the trial visited. Until TSK-78 the loop
    took one edge a frame, so a zero state lasted one frame and the change trailed the array."""
    result = run_trial(_go_delay_trial(), Quiet(), frame_period=0.01, values={"go_delay": 0.0})

    placed = {(entry.stimulus.name, entry.kind): entry.frame for entry in result.placed}
    assert placed[("array", "show")] == placed[("dot", "update")] == 4
    assert result.visited == ("hold", "delay", "go")
    # The go state was entered on frame 3 with `delay`, so its 50 ms run out on frame 8.
    assert (result.outcome, result.frames) == (Outcome.NO_RESPONSE, 8)


def test_a_wait_above_zero_counts_from_the_next_frame_as_before():
    """`go_delay` 0.05 at 240 Hz: `delay` is entered on frame 8 (30 ms) and left on frame 20, 12
    frames on, as every wait above zero is counted, the dot changing on frame 21."""
    log: list = []
    result = run_trial(_go_delay_trial(), _Told(log), frame_period=1 / 240,
                       values={"go_delay": 0.05})

    placed = {(entry.stimulus.name, entry.kind): entry.frame for entry in result.placed}
    assert log[:3] == [("hold", 1), ("delay", 9), ("go", 21)]
    assert (placed[("array", "show")], placed[("dot", "update")]) == (9, 21)


def test_a_zero_wait_listed_after_a_gaze_edge_still_passes():
    """The pass is the state's first plain `After` that resolves to 0, wherever it is listed: an
    `Exited` before it is not judged, the state having lasted no frame. The eye leaves the fixation
    window on the frame after the array: in the go state, the answer, not an early break."""
    trial = _go_delay_trial([On(Exited("fix"), Outcome.EARLY_RESPONSE),
                             On(After(P("go_delay")), "go", do=[Update("dot", opacity=0.5)])])
    world = Scripted({}, inside={frame: "fix" for frame in range(1, 4)})

    result = run_trial(trial, world, frame_period=0.01, values={"go_delay": 0.0})

    assert (result.outcome, result.frames) == (Outcome.CORRECT, 4)
    assert result.visited == ("hold", "delay", "go")


def test_two_zero_waits_in_a_row_take_one_frame_between_them():
    """At most one pass a frame: the first zero state is passed on the frame it is entered, and
    the second, entered by the pass, is judged from the next frame, where its zero wait fires."""
    trial = Trial(
        start="a",
        params=[Param("second", unit="s", low=0.0, high=1.0)],
        states=[
            State("a", go=[On(After(0.03), "z1")]),
            State("z1", enter=[Show(Stimulus("first", at=(0.0, 0.0)))],
                  go=[On(After(0.0), "z2")]),
            State("z2", go=[On(After(P("second")), "after")]),
            State("after", enter=[Show(Stimulus("then", at=(1.0, 0.0)))],
                  go=[On(After(0.05), Outcome.CORRECT)]),
        ],
    )
    log: list = []

    result = run_trial(trial, _Told(log), frame_period=0.01, values={"second": 0.0})

    assert log == [("a", 1), ("z1", 4), ("z2", 4), ("after", 5)]
    assert [(entry.stimulus.name, entry.frame) for entry in result.placed] == [
        ("first", 4), ("then", 5)]
    assert result.visited == ("a", "z1", "z2", "after")


def test_a_cycle_of_zero_waits_ends_on_the_longest_trial():
    """Two zero states that enter each other: one pass a frame, so each frame takes one edge and
    one pass, and the trial reaches its longest with no outcome, a hang, never looping in a frame."""
    trial = Trial(
        start="a",
        states=[
            State("a", go=[On(After(0.01), "z1")]),
            State("z1", go=[On(After(0.0), "z2")]),
            State("z2", go=[On(After(0.0), "z1")]),
        ],
    )

    result = run_trial(trial, Quiet(), frame_period=0.01, max_frames=20)

    assert (result.outcome, result.frames) == (None, 20)
    assert result.visited == ("a",) + ("z1", "z2") * 20


def test_a_zero_timeout_ends_the_trial_on_the_frame_of_its_error():
    """An error's timeout state at 0 s ends the trial on the frame the error was taken, its
    outcome's actions strobed with the error's. It ended one frame later until TSK-78."""
    trial = Trial(
        start="await",
        params=[Param("timeout", unit="s", low=0.0, high=5.0)],
        windows=[Window("fix", at=(0.0, 0.0), radius=2.0)],
        states=[
            State("await", go=[On(Exited("fix"), "timeout", do=[Mark(4110)]),
                               On(After(1.0), Outcome.CORRECT)]),
            State("timeout", go=[On(After(P("timeout")), Outcome.FIXATION_BREAK,
                                    do=[Mark(4111)])]),
        ],
    )
    effects = Recorded()
    world = Scripted({}, inside={frame: "fix" for frame in range(1, 6)})

    result = run_trial(trial, world, frame_period=0.01, values={"timeout": 0.0},
                       effects=effects)

    assert (result.outcome, result.frames) == (Outcome.FIXATION_BREAK, 6)
    assert result.visited == ("await", "timeout")
    assert effects.log == [("mark", 4110), ("mark", 4111)]


#: What a frame that takes an edge builds (`tests/test_gaze.py`'s `_A_TRANSITION`, XC-414): the
#: trial's record of the transition and the effects it hands the port; nothing else, pass or none.
_A_TRANSITION = {
    ("Shown.__new__", "tuple"), ("Placed.__new__", "tuple"), ("Changed.__new__", "tuple"),
    ("_apply", "tuple"), ("_apply", "dict"), ("_apply", "arguments"),
    ("Recorded.mark", "tuple"), ("Recorded.reward", "tuple"),
}


def test_a_frame_that_passes_a_zero_wait_allocates_nothing(monkeypatch):
    """CLAUDE.md: "Inside trial loops: no allocation". Measured as `tests/test_gaze.py` measures a
    frame (`built_on`, `_Loop.frame` wrapped on the class): the frame that takes an edge into a zero
    state and passes it builds the two transitions' records and nothing else, the pass read from
    the table `_Loop` built between trials."""
    from _builds import built_on
    from wl_xcon import run

    records = {record.__new__.__code__: f"{record.__name__}.__new__"
               for record in (run.Shown, run.Placed, run.Changed, run.Confirmed)}
    trial = Trial(
        start="a",
        params=[Param("go_delay", unit="s", low=0.0, high=1.0)],
        states=[
            State("a", go=[On(After(0.03), "delay", do=[Mark(4100)])]),
            State("delay", enter=[Show(Stimulus("array", at=(8.0, 0.0)))],
                  go=[On(After(P("go_delay")), "go", do=[Mark(4101)])]),
            State("go", go=[On(After(0.05), Outcome.CORRECT)]),
        ],
    )
    frame_of = run._Loop.frame
    passed: dict = {}

    def measured_frame(loop, frame: int) -> bool:
        ended, states = [], len(loop.visited)
        built = built_on(lambda: ended.append(frame_of(loop, frame)), named=records)
        if len(loop.visited) == states + 2:
            passed[frame] = set(built)
        return ended[0]

    monkeypatch.setattr(run._Loop, "frame", measured_frame)
    effects = Recorded()
    result = run_trial(trial, Quiet(), frame_period=0.01, values={"go_delay": 0.0},
                       effects=effects)

    assert result.visited == ("a", "delay", "go")
    assert list(passed) == [3], "no frame took an edge into `delay` and passed it"
    assert sorted(passed[3] - _A_TRANSITION) == []
    assert effects.log == [("mark", 4100), ("mark", 4101)]


#: **Each reference task's outcomes at its starts, as the engine counted them before TSK-78**, at
#: the branch's base (`91b22f7f`, 2026-11-19): the hazard `Subject` below at two seeds, 600 trials
#: each at 240 Hz, every setting at its start and each with none at the values the tests above
#: and `tests/test_reference_tasks.py` time them with. No reference task waits 0 s at its starts,
#: so a zero wait's pass must leave every count where it was.
_AT_BASE = {
    "fixation_detection": {
        3: {"correct": 341, "fixation_break": 88, "no_fixation": 93, "no_response": 31,
            "target_break": 47},
        11: {"correct": 347, "fixation_break": 86, "no_fixation": 93, "no_response": 30,
             "target_break": 44}},
    "adaptive_detection": {
        3: {"correct": 341, "fixation_break": 88, "no_fixation": 93, "no_response": 31,
            "target_break": 47},
        11: {"correct": 347, "fixation_break": 86, "no_fixation": 93, "no_response": 30,
             "target_break": 44}},
    "visual_search": {
        3: {"correct": 174, "fixation_break": 88, "no_fixation": 100, "no_response": 7,
            "target_break": 28, "wrong_target": 203},
        11: {"correct": 171, "fixation_break": 78, "no_fixation": 111, "no_response": 13,
             "target_break": 25, "wrong_target": 202}},
    "visual_search_training": {
        3: {"correct": 174, "fixation_break": 88, "no_fixation": 100, "no_response": 7,
            "target_break": 28, "wrong_target": 203},
        11: {"correct": 171, "fixation_break": 78, "no_fixation": 111, "no_response": 13,
             "target_break": 25, "wrong_target": 202}},
    "calibration": {
        3: {"correct": 396, "fixation_break": 96, "no_fixation": 108},
        11: {"correct": 421, "fixation_break": 86, "no_fixation": 93}},
}

#: A value for each setting a reference task gives no start, the timings `tests/test_reference_tasks.py`
#: runs them at and windows of the sizes the tasks start theirs at.
_UNSTARTED = {"fix_acquisition": 4.0, "fix_hold": 0.3, "response_deadline": 0.6,
              "target_hold": 0.2, "fix_window": 2.0, "target_window": 3.0, "target_x": 10.0,
              "target_y": 0.0, "cal_window": 2.0, "cal_hold": 0.3}


@pytest.mark.parametrize("name", sorted(_AT_BASE))
def test_every_reference_tasks_outcomes_are_unchanged_at_their_starts(name):
    from pathlib import Path

    from wl_xcon.cli import _load_task
    from wl_xcon.simulate import Subject, simulate

    task = _load_task(Path(__file__).resolve().parents[1] / "tasks" / f"{name}.py")
    declared = {param.name for param in task.params}
    values = {**{setting: value for setting, value in _UNSTARTED.items() if setting in declared},
              **{param.name: param.start for param in task.params if param.start is not None}}

    counted = {}
    for seed in (3, 11):
        census = simulate(
            task,
            Subject(seed=seed, engagement=0.85, lapse=0.15,
                    hazards={Entered: 4.0, Exited: 0.5, SaccadeTo: 5.0}),
            trials=600, frame_period=1 / 240, values=values, effects=Recorded())
        assert census.hangs == 0
        counted[seed] = {outcome.value: n for outcome, n in census.outcomes.items()}

    assert counted == _AT_BASE[name]
