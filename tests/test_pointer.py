"""Demo mode's eye, the mouse, in process (demo mode design §3.3-§3.5, §9; its plan's Task 2).

`pointer.Source` turns the page's pointer reports into one `eye.Sample` a frame, and
`pointer.Pointing`, `gaze.Tracked` built as `simeye.Seeing` is, scores them by the rig's own eye
rules and answers the guards no gaze world answers from the keys, the button and the display. What
is held here: the newest report wins, in sequence order; a report is current for `LIVE_S`, a stall
within it held and counted toward a hold, past it tracker loss; off the drawing is gaze away, B is
tracker loss and never a blink; a still pointer makes no saccade, a move across frames one landing
where it stopped, and a one-report flick one too; keys on their edges, a press and release between
two frames seen once, the counts rebased at a trial's first frame; touch, `Onscreen`,
`FeatureAbove` and `ChairStill`; the keys' numbering and its bound; the drain's bound and a
malformed report; the pacing; the noise's seed; the mouse and the simulated eye agreeing on the
pop-out search; and a frame building only its sample.

**Every test runs against an injected clock and never sleeps**: `_Clock` is the wall clock
`pointer.Pace` waits on, its sleep moving it on, and `_Page` holds the reports the page sent, each
read once the clock has reached the moment it was sent. Engine test material: no timing claim rests
on any number here (CLAUDE.md).
"""

from __future__ import annotations

import json
import math
import os
import random
from collections import Counter, deque
from dataclasses import replace
from pathlib import Path

import pytest

from _builds import built_on, builds_of
from _rig import DIRECT, RIG
from wl_xcon import pointer, run, saccade, simeye, viewport
from wl_xcon.bounds import Bounds, Ceiling, Floor
from wl_xcon.dio import Simulated as Card
from wl_xcon.geometry import polar_of_deg
from wl_xcon.link import Drawn, Simulated, Stop, decode, encode
from wl_xcon.photometry import SRGB, Gray
from wl_xcon.actor import Box
from wl_xcon.run import Changed, Confirmed, Placed, Recorded, Shown, run_trial
from wl_xcon.task import (
    REMEMBERED,
    After,
    Array,
    ChairStill,
    Disc,
    Entered,
    Exited,
    FeatureAbove,
    Hide,
    Hold,
    Noise,
    On,
    Onscreen,
    Outcome,
    P,
    Picture,
    Pressed,
    Released,
    Response,
    SaccadeOnset,
    SaccadeTo,
    Show,
    State,
    Stimulus,
    Tolerances,
    Touched,
    Trial,
    Window,
    actions_of,
)
from wl_xcon.taskd import Session, SessionSpec
from wl_xcon.welfare import Deployment, Simulated as Pump

#: The session's frame period, `service.FRAME_PERIOD`'s: 240 Hz.
FRAME = 1 / 240
#: Where the injected clock starts: anywhere but zero, so a pace that never reads it is caught.
T0 = 100.0
#: No key pressed yet.
NONE = (0,) * pointer.KEYS
#: A slice for each length a report can be written at, so the page's `receive` writes one into the
#: buffer without building a slice on the frame (the measure of `test_a_frame_...` reads it whole).
_SLOTS = tuple(slice(0, size) for size in range(pointer.MESSAGE.size + 1))

DOT = Stimulus("dot", at=(0.0, 0.0), looks=Disc(size=0.3, color=Gray(40.0)))
TARGET = Stimulus("goal", at=(8.0, 0.0), looks=Disc(size=1.0, color=Gray(40.0)))

#: **A fixation trial**: the dot shown, gaze into its window, held 0.3 s; leaving it is a break.
#: A second, wide window, 30° across, shows that the pointer off the drawing is outside every one.
FIX = Trial(
    start="await_fix",
    windows=[Window("fix", at=(0.0, 0.0), radius=2.0, on="dot"),
             Window("wide", at=(0.0, 0.0), radius=30.0, on=REMEMBERED)],
    states=[
        State("await_fix", enter=[Show(DOT)],
              go=[On(Entered("fix"), "hold"), On(After(1.0), Outcome.NO_FIXATION)]),
        State("hold", go=[On(Hold("fix", 0.3), Outcome.CORRECT),
                          On(Exited("fix"), Outcome.FIXATION_BREAK),
                          On(After(3.0), Outcome.NO_FIXATION)]),
    ],
)


def report(seq: int, x: float, y: float, *, over: bool = True, b: bool = False,
           button: bool = False, held: int = 0, presses=NONE) -> bytes:
    return pointer.pack(seq, x, y, over=over, b=b, button=button, held=held, presses=presses)


class _Clock:
    """**The wall clock, injected**: what `pointer.Pace` reads, its sleep moving it on, so nothing
    sleeps."""

    def __init__(self, t: float = T0) -> None:
        self.t = t
        self.slept: list = []

    def __call__(self) -> float:
        return self.t

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.t += seconds


class _Page:
    """**The gaze socket, as a page fills it**: each report sent at a moment on the clock, read by
    `receive` once the clock has reached it, one a call, as `recv_into` reads one message into the
    buffer; -1 with none waiting. Its calls counted."""

    def __init__(self, clock: _Clock) -> None:
        self.clock = clock
        self.waiting: deque = deque()
        self.calls = 0
        self.seq = 0

    def send(self, at: float, message: bytes) -> None:
        self.waiting.append((at, message))

    def pointer(self, at: float, x: float, y: float, **flags) -> None:
        """A report of the pointer at `(x, y)` sent at `at`, numbered next."""
        self.seq += 1
        self.send(at, report(self.seq, x, y, **flags))

    def receive(self, buffer: bytearray) -> int:
        self.calls += 1
        waiting = self.waiting
        if not waiting or waiting[0][0] > self.clock.t + 1e-9:
            return -1
        message = waiting.popleft()[1]
        size = len(message)
        buffer[_SLOTS[size]] = message
        return size


def frame_at(start: float, frame: int) -> float:
    """Frame `frame`'s moment on the clock, its trial's first frame at `start`."""
    return start + (frame - 1) * FRAME


def _rig(*, seed: int = 1, noise_deg: float = simeye.NOISE_DEG):
    """A clock, a page, a source on it and a pace on the clock."""
    clock = _Clock()
    page = _Page(clock)
    source = pointer.Source(page.receive, seed=seed, noise_deg=noise_deg)
    pace = pointer.Pace(FRAME, clock=clock, sleep=clock.sleep)
    return clock, page, source, pace


def _world(trial: Trial, source, pace, values=None) -> pointer.Pointing:
    """One trial's world, as `pointer.worlds` makes it."""
    return pointer.worlds(source, pace=pace)(trial, values or {}, 0)


def _play(trial: Trial, source, pace, values=None):
    world = _world(trial, source, pace, values)
    return world, run_trial(trial, world, FRAME, values=values or {}, effects=Recorded())


def _drive(world, frames: int, state: str = "s", visible=None, guards=()) -> list:
    """Frames 1 to `frames` of `world` by hand, as the loop calls it -- the display, then each of
    `guards` asked -- with what each answered."""
    world.began(state, 1)
    answers = []
    for frame in range(1, frames + 1):
        world.display(visible if visible is not None else {}, frame)
        answers.append(tuple(world.happened(guard, state, frame) for guard in guards))
    return answers


def _count_saccades(monkeypatch) -> list:
    """Every saccade a detector confirms from now on, as `gaze.Tracked` feeds it."""
    confirmed: list = []
    accept = saccade.Detector.accept

    def counted(detector, at, gaze):
        found = accept(detector, at, gaze)
        if found is not None:
            confirmed.append(found)
        return found

    monkeypatch.setattr(saccade.Detector, "accept", counted)
    return confirmed


# --- Reports --------------------------------------------------------------------------------


def test_a_report_is_41_bytes_as_the_page_packs_it():
    """The wire (§3.8): 41 bytes, little-endian; the flags' bits; the keys held, bit `k - 1` for key
    `k`; each key's press count modulo 65536."""
    assert pointer.MESSAGE.size == 41
    message = pointer.pack(7, 1.5, -2.0, over=True, b=False, button=True, held=0b101,
                           presses=(65537, 2, 0, 0, 0, 0, 0, 0, 9))
    assert pointer.MESSAGE.unpack(message) == (7, 1.5, -2.0, pointer.OVER | pointer.BUTTON, 0b101,
                                               1, 2, 0, 0, 0, 0, 0, 0, 9)
    assert (pointer.OVER, pointer.B_HELD, pointer.BUTTON) == (1, 2, 4)
    with pytest.raises(ValueError, match="9 keys"):
        pointer.pack(1, 0.0, 0.0, over=True, b=False, button=False, held=0, presses=(0,) * 8)
    assert pointer.MAPPING.why == "the mouse, in degrees"
    assert replace(pointer.MAPPING, why=simeye.MAPPING.why) == simeye.MAPPING


def test_the_newest_report_wins_in_sequence_order():
    """Three reports in one drain, numbered 3, 1, 2: 3's position, the other two stale; and one
    older than the report in hand while it is current is stale too."""
    clock, page, source, _ = _rig(noise_deg=0.0)
    for seq, x in ((3, 3.0), (1, 1.0), (2, 2.0)):
        page.send(T0, report(seq, x, 0.5))
    sample = source.poll(0.0)
    assert (sample.left.dpi_x(), sample.left.dpi_y()) == (3.0, 0.5)
    assert source.stale == 2
    page.send(T0, report(2, 2.0, 0.5))
    sample = source.poll(FRAME)
    assert sample.left.dpi_x() == 3.0 and source.stale == 3


def test_a_report_is_current_for_live_s_then_tracker_loss():
    """A report is current for `LIVE_S` (§3.3): a sample just inside it, `None` at it; and through
    `Pointing`, the signal "lost" once the tracker's last sample is older than its staleness, never
    "blink"."""
    clock, page, source, pace = _rig()
    page.send(T0, report(1, 0.0, 0.0))
    assert source.poll(0.0) is not None
    assert source.poll(pointer.LIVE_S - 1e-6) is not None
    assert source.poll(pointer.LIVE_S) is None

    clock, page, source, pace = _rig()
    page.send(T0, report(1, 0.0, 0.0))
    world = _world(Trial(start="s", states=[State("s", unbounded=True)]), source, pace)
    world.began("s", 1)
    sampled, signals = [], []
    for frame in range(1, 200):
        world.display({}, frame)
        sampled.append(world.tracker.latest is not None
                       and world.tracker.latest.at == world.when(frame))
        signals.append(world.signal(frame))
    last = max(frame for frame, fresh in enumerate(sampled, 1) if fresh)
    assert all(sampled[:last]) and not any(sampled[last:])
    assert (last - 1) * FRAME < pointer.LIVE_S + 1e-9 and last * FRAME >= pointer.LIVE_S - 1e-9
    staleness = world.tracker.staleness
    for frame, signal in enumerate(signals, 1):
        held = world.when(frame) - world.when(last) < staleness
        assert signal == ("ok" if held else "lost"), (frame, signal)
    assert signals[-1] == "lost" and "blink" not in signals


def test_a_stall_within_live_s_holds_the_position_and_counts_toward_a_hold():
    """A page's stall within `LIVE_S` (Review Focus 3): the last position held, the signal "ok", and
    a 0.3 s hold completing across 0.2 s and more with no report."""
    clock, page, source, pace = _rig()
    for frame in range(1, 26, 4):
        page.pointer(frame_at(T0, frame), 0.5, 0.0)
    last = frame_at(T0, 25)
    world, result = _play(FIX, source, pace)
    assert result.outcome is Outcome.CORRECT, result
    assert result.visited == ("await_fix", "hold")
    assert clock.t - last >= 0.2 - 1e-9


def test_off_the_drawing_is_gaze_away_not_tracker_loss():
    """Off the drawing is gaze off the screen (Review Focus 3): the signal "ok", every window
    outside, gaze at `AWAY_DEG`, and a fixation held on the dot breaks by `Exited`."""
    clock, page, source, pace = _rig()
    for frame in range(1, 41, 4):
        page.pointer(frame_at(T0, frame), 0.5, 0.0)
    for frame in range(41, 120, 4):
        page.pointer(frame_at(T0, frame), 0.5, 0.0, over=False)
    world, result = _play(FIX, source, pace)
    assert result.outcome is Outcome.FIXATION_BREAK, result
    assert result.visited == ("await_fix", "hold")
    assert result.frames == 41
    assert world.signal(41) == "ok"
    assert not world.in_window("fix", 41) and not world.in_window("wide", 41)
    x, y = world.gaze_cyclopean(41)
    assert math.hypot(x - pointer.AWAY_DEG[0], y - pointer.AWAY_DEG[1]) < 0.2


def test_b_held_is_tracker_loss_never_blink():
    """B held is tracker loss (Review Focus 3): the source gives no sample, the tracker goes stale,
    and the trial ends under the task's `tracker_lost`, never as a blink, though the task forgives a
    blink of a second."""
    trial = replace(FIX, tolerances=Tolerances(blink=1.0, tracker_lost=0.05))
    clock, page, source, pace = _rig()
    for frame in range(1, 40, 4):
        page.pointer(frame_at(T0, frame), 0.5, 0.0)
    for frame in range(40, 200, 4):
        page.pointer(frame_at(T0, frame), 0.5, 0.0, b=True)
    world = _world(trial, source, pace)
    signals = []
    signal = world.signal
    world.signal = lambda frame: signals.append(signal(frame)) or signals[-1]
    result = run_trial(trial, world, FRAME, effects=Recorded())
    assert result.outcome is Outcome.TRACKER_LOST, result
    assert "lost" in signals and "blink" not in signals
    assert result.frames < 40 + round((0.05 + 0.05) / FRAME) + 3


# --- Saccades -------------------------------------------------------------------------------

#: A trial asking for a saccade to a window, with another window on the way there.
_LOOK = Trial(
    start="s",
    windows=[Window("target", at=(12.0, 0.0), radius=1.5, on=REMEMBERED),
             Window("flick", at=(8.0, 0.0), radius=1.5, on=REMEMBERED),
             Window("passed", at=(4.0, 0.0), radius=1.5, on=REMEMBERED)],
    states=[State("s", go=[On(SaccadeTo("target"), Outcome.CORRECT),
                           On(SaccadeTo("flick"), Outcome.CORRECT),
                           On(SaccadeTo("passed"), Outcome.WRONG_TARGET),
                           On(After(2.0), Outcome.NO_RESPONSE)])],
)


def _still(page, x: float, y: float, frames: range) -> None:
    """The pointer still at `(x, y)`, a report every 4 frames over `frames` of a trial at `T0`."""
    for frame in frames[::4]:
        page.pointer(frame_at(T0, frame), x, y)


def test_a_still_pointer_makes_no_saccade(monkeypatch):
    """A still pointer, reported every 100 ms for 2 s, the page's slowest: every sample within its
    noise of where the pointer is, and no saccade confirmed."""
    confirmed = _count_saccades(monkeypatch)
    trial = Trial(start="s", states=[State("s", go=[On(SaccadeOnset(), Outcome.ABORT),
                                                    On(After(2.0), Outcome.CORRECT)])])
    clock, page, source, pace = _rig()
    for frame in range(1, 490, 24):
        page.pointer(frame_at(T0, frame), 3.0, -2.0)
    world = _world(trial, source, pace)
    kept: list = []
    world.source = _Kept(source, kept)
    result = run_trial(trial, world, FRAME, effects=Recorded())
    assert result.outcome is Outcome.CORRECT
    assert result.frames == min(frame for frame in range(1, 1000) if frame * FRAME >= 2.0)
    assert len(kept) == result.frames
    assert max(math.hypot(sample.left.dpi_x() - 3.0, sample.left.dpi_y() + 2.0)
               for sample in kept) < 8 * simeye.NOISE_DEG
    assert confirmed == []


def test_a_move_across_frames_that_stops_makes_one_saccade_landing_where_it_stopped(monkeypatch):
    """A move reported across frames (§9): still, then 12° rightward over 200 ms, a report every
    4 frames, then still: one saccade confirmed, and `SaccadeTo` fires on the window where it
    stopped, not on those it passed over."""
    confirmed = _count_saccades(monkeypatch)
    clock, page, source, pace = _rig()
    _still(page, 0.0, 0.0, range(1, 121))
    for step in range(1, 13):
        page.pointer(frame_at(T0, 120 + 4 * step), 12.0 * step / 12, 0.0)
    for frame in range(192, 480, 24):
        page.pointer(frame_at(T0, frame), 12.0, 0.0)
    world, result = _play(_LOOK, source, pace)
    assert result.outcome is Outcome.CORRECT, result
    assert len(confirmed) == 1, confirmed
    assert world.in_window("target", result.frames)


def test_a_one_report_flick_is_still_a_saccade(monkeypatch):
    """§14 item 9: still, then no report for 100 ms, then one report 8° away: eased over the frames
    it took, it is one saccade the detector confirms, landing in the window there."""
    confirmed = _count_saccades(monkeypatch)
    clock, page, source, pace = _rig()
    _still(page, 0.0, 0.0, range(1, 121))
    page.pointer(frame_at(T0, 144), 8.0, 0.0)
    for frame in range(168, 480, 24):
        page.pointer(frame_at(T0, frame), 8.0, 0.0)
    world, result = _play(_LOOK, source, pace)
    assert result.outcome is Outcome.CORRECT, result
    assert len(confirmed) == 1, confirmed
    assert world.in_window("flick", result.frames)


def test_a_still_pointers_report_during_its_flick_leaves_the_flick_one_saccade(monkeypatch):
    """The whole-build review's I2, with `pointer.EASE_SLACK_S`: a flick's report after 100 ms
    of none is eased over 125 ms, so the still pointer's next report, here 50 ms later, as a page
    on a busy computer sends it, comes before the flick has landed. **A report where the pointer
    already goes leaves the move in flight as it was**: restarted from rest it would stop and start
    again, a second saccade (23 of 40 seeds, probed), and in the pop-out a second look, an abort
    (`tests/test_demo_popout.py`'s look to empty space, once, under the suite's load)."""
    confirmed = _count_saccades(monkeypatch)
    trial = Trial(start="s", states=[State("s", go=[On(After(3.0), Outcome.CORRECT)])])
    for seed in range(10):
        confirmed.clear()
        clock, page, source, pace = _rig(seed=seed)
        for frame in range(1, 300, 24):
            page.pointer(frame_at(T0, frame), 0.0, 0.0)
        for frame in (300, *range(312, 720, 24)):
            page.pointer(frame_at(T0, frame), 6.0, 6.0)
        _play(trial, source, pace)
        flicks = [found for found in confirmed if found.amplitude_deg > 1.0]
        assert len(flicks) == 1 and confirmed[-1] is flicks[0], (seed, confirmed)


def test_a_flick_reported_the_frame_after_a_still_pointers_report_is_still_a_saccade(monkeypatch):
    """**A flick a frame behind a still pointer's report** (2026-11-19): the page reports a still
    pointer every 100 ms, and a hand moves when it moves, so a flick's report can reach the rig the
    frame after a still one's, or after two that came a frame apart (`tests/test_page_browser.py`'s
    pop-out played with the mouse, an abort in about one suite run in several; pitfall P29). Taken
    in that one frame, as a report in a stream of one a frame is, the flick was a jump the detector
    never confirms -- under its six samples outside the threshold -- so the look landed nowhere,
    and the pop-out ended it astray on its landing bound with the eye in the target's window.
    **Only a report continuing a stream of one a frame is taken exactly**; this one is eased over
    its gap and `pointer.EASE_SLACK_S`: one saccade, landing in the window there."""
    confirmed = _count_saccades(monkeypatch)
    for bunched in (1, 2):
        for seed in range(10):
            confirmed.clear()
            clock, page, source, pace = _rig(seed=seed)
            _still(page, 0.0, 0.0, range(1, 121))
            for frame in range(141 - bunched, 141):
                page.pointer(frame_at(T0, frame), 0.0, 0.0)
            page.pointer(frame_at(T0, 141), 8.0, 0.0)
            for frame in range(165, 480, 24):
                page.pointer(frame_at(T0, frame), 8.0, 0.0)
            world, result = _play(_LOOK, source, pace)
            flicks = [found for found in confirmed if found.amplitude_deg > 1.0]
            assert result.outcome is Outcome.CORRECT, (bunched, seed, result)
            assert len(flicks) == 1 and confirmed[-1] is flicks[0], (bunched, seed, confirmed)
            assert world.in_window("flick", result.frames)


# --- Keys, touch and the light sensor ---------------------------------------------------------


def test_keys_fire_on_their_edges():
    """§3.4: `Pressed` on the key going down, once however long it is held; `Released` on it coming
    up; `Response` on its key going down."""
    trial = Trial(start="a", states=[
        State("a", go=[On(Pressed("lever"), "b"), On(After(1.0), Outcome.NO_RESPONSE)]),
        State("b", go=[On(Pressed("lever"), Outcome.ABORT), On(Released("lever"), "c"),
                       On(After(1.0), Outcome.NO_RESPONSE)]),
        State("c", go=[On(Response("bar"), Outcome.CORRECT), On(After(1.0), Outcome.NO_RESPONSE)]),
    ])
    assert [item.label for item in pointer.inputs(trial)] == ["lever", "bar"]
    clock, page, source, pace = _rig()
    for frame in range(1, 200, 4):
        lever = 1 if frame >= 21 else 0
        held = (1 if 21 <= frame < 41 else 0) | (2 if frame >= 61 else 0)
        page.pointer(frame_at(T0, frame), 0.0, 0.0, held=held,
                     presses=(lever, 1 if frame >= 61 else 0) + NONE[2:])
    world = _world(trial, source, pace)
    began = []
    told = world.began
    world.began = lambda state, frame: began.append((state, frame)) or told(state, frame)
    result = run_trial(trial, world, FRAME, effects=Recorded())
    assert result.outcome is Outcome.CORRECT, result
    assert began == [("a", 1), ("b", 22), ("c", 42)]
    assert result.frames == 61


def test_a_press_and_release_between_two_frames_is_seen_once():
    """Presses are counted, not sampled (§3.4, Review Focus 2): a press and release between two
    frames is a down edge and an up edge on the next frame, and neither on the frames after."""
    clock, page, source, pace = _rig()
    page.send(T0, report(1, 0.0, 0.0))
    source.poll(0.0)
    page.send(T0, report(2, 0.0, 0.0, presses=(1,) + NONE[1:]))
    source.poll(FRAME)
    assert source.went_down(1) and source.went_up(1) and not source.held(1)
    page.send(T0, report(3, 0.0, 0.0, presses=(1,) + NONE[1:]))
    source.poll(2 * FRAME)
    assert not source.went_down(1) and not source.went_up(1)
    source.poll(3 * FRAME)
    assert not source.went_down(1) and not source.went_up(1)

    trial = Trial(start="a", states=[
        State("a", go=[On(Pressed("lever"), "b"), On(After(1.0), Outcome.NO_RESPONSE)]),
        State("b", go=[On(Pressed("lever"), Outcome.ABORT),
                       On(Released("lever"), Outcome.ABORT),
                       On(After(0.2), Outcome.CORRECT)]),
    ])
    clock, page, source, pace = _rig()
    for frame in range(1, 200, 4):
        page.pointer(frame_at(T0, frame), 0.0, 0.0,
                     presses=(1 if frame >= 21 else 0,) + NONE[1:])
    world, result = _play(trial, source, pace)
    assert result.outcome is Outcome.CORRECT and result.visited == ("a", "b"), result


def test_press_counts_rebase_at_a_trials_first_frame():
    """Review Focus 2: a press in the gap between two trials never fires the next trial's
    `Pressed`, since the counts rebase at its first frame; what waits then but the newest report is
    discarded; and a press within the trial still fires."""
    trial = Trial(start="s", states=[State("s", go=[On(Pressed("lever"), Outcome.FALSE_ALARM),
                                                    On(After(0.1), Outcome.CORRECT)])])
    clock, page, source, pace = _rig()
    make = pointer.worlds(source, pace=pace)

    def played(presses, start, pressed_at=None):
        for frame in range(1, 40, 4):
            count = presses + (1 if pressed_at is not None and frame >= pressed_at else 0)
            page.pointer(frame_at(start, frame), 1.0, 1.0, presses=(count,) + NONE[1:])
        world = make(trial, {}, 0)
        result = run_trial(trial, world, FRAME, effects=Recorded())
        page.waiting.clear()
        return result.outcome

    assert played(0, T0) is Outcome.CORRECT
    # The gap: pressed, released, and still, three reports waiting at the next trial's start.
    gap = clock.t + 0.01
    clock.t = gap
    page.pointer(gap, 1.0, 1.0, held=1, presses=(1,) + NONE[1:])
    page.pointer(gap, 1.0, 1.0, presses=(1,) + NONE[1:])
    page.pointer(gap, 4.0, 4.0, presses=(1,) + NONE[1:])
    stale = source.stale
    world = make(trial, {}, 1)
    assert source.stale == stale + 2
    # Sixteen frames: the move to the newest report is eased over the gap since the last report
    # and `EASE_SLACK_S`, landed well inside them.
    assert _drive(world, 16, guards=(Pressed("lever"), Released("lever"))) == [(False, False)] * 16
    assert world.gaze_cyclopean(16) == pytest.approx((4.0, 4.0), abs=0.1)
    page.waiting.clear()
    assert played(1, clock.t) is Outcome.CORRECT
    assert played(1, clock.t, pressed_at=9) is Outcome.FALSE_ALARM


def test_touch_holds_while_the_button_is_down_inside_the_window():
    """`Touched(window)` holds while the mouse button is down with the pointer inside the window
    (§3.4): not over it without the button, not with the button elsewhere, and on every frame of a
    press inside it."""
    trial = Trial(start="s", windows=[Window("pad", at=(5.0, 0.0), radius=2.0, on=REMEMBERED)],
                  states=[State("s", go=[On(Touched("pad"), Outcome.CORRECT),
                                         On(After(1.0), Outcome.NO_RESPONSE)])])
    clock, page, source, pace = _rig()
    script = ([(5.0, False)] * 10 + [(0.0, True)] * 10 + [(5.0, True)] * 10
              + [(5.0, False)] * 10)
    for frame, (x, button) in enumerate(script, 1):
        page.pointer(frame_at(T0, frame), x, 0.0, button=button)
    world = _world(trial, source, pace)
    answers = [touched for (touched,) in _drive(world, 40, guards=(Touched("pad"),))]
    assert answers == [False] * 20 + [True] * 10 + [False] * 10


def test_onscreen_fires_on_the_first_frame_after_the_display_changed():
    """`Onscreen` fires on the first frame after the display changed, as a light sensor sees it
    (§3.4): the frame a stimulus is first drawn, the frame an `Update` redraws it and the frame it
    is hidden, and on no frame the display stays as it was."""
    trial = Trial(start="a", windows=[], states=[
        State("a", enter=[Show(DOT)], go=[On(Onscreen(), "b"), On(After(0.5), Outcome.ABORT)]),
        State("b", go=[On(Onscreen(), Outcome.ABORT),
                       On(After(0.1), "c", do=[Hide("dot")])]),
        State("c", go=[On(Onscreen(), Outcome.CORRECT), On(After(0.5), Outcome.NO_RESPONSE)]),
    ])
    clock, page, source, pace = _rig()
    _still(page, 0.0, 0.0, range(1, 100))
    world, result = _play(trial, source, pace)
    assert result.outcome is Outcome.CORRECT and result.visited == ("a", "b", "c"), result
    hidden = min(frame for frame in range(2, 100) if (frame - 1) * FRAME >= 0.1)
    assert result.frames == hidden + 1

    clock, page, source, pace = _rig()
    _still(page, 0.0, 0.0, range(1, 20))
    world = _world(trial, source, pace)
    moved = replace(DOT, at=(1.0, 1.0))
    shown = [{}, {"dot": DOT}, {"dot": DOT}, {"dot": moved}, {"dot": moved}, {}, {}]
    world.began("a", 1)
    fired = []
    for frame, visible in enumerate(shown, 1):
        world.display(visible, frame)
        fired.append(world.happened(Onscreen(), "a", frame))
    assert fired == [False, True, False, True, False, True, False]


def test_feature_above_holds_while_held_and_chair_still_while_not():
    """`FeatureAbove(source)` holds while its key is held, `ChairStill` while its key is not
    (§3.4)."""
    trial = Trial(start="s", states=[State("s", go=[
        On(FeatureAbove("rate", 2.0), Outcome.CORRECT), On(ChairStill(), Outcome.ABORT),
        On(After(1.0), Outcome.NO_RESPONSE)])])
    assert [(item.key, item.label) for item in pointer.inputs(trial)] == [
        (1, "feature rate"), (2, "the chair")]
    clock, page, source, pace = _rig()
    for frame, held in enumerate((0b00, 0b01, 0b11, 0b10, 0b00), 1):
        page.pointer(frame_at(T0, frame), 0.0, 0.0, held=held)
    world = _world(trial, source, pace)
    answers = _drive(world, 5, guards=(FeatureAbove("rate", 2.0), ChairStill()))
    assert answers == [(False, True), (True, True), (True, False), (False, False), (False, True)]


def test_keys_are_numbered_in_the_order_the_states_first_name_them():
    """§3.4: one key a device whatever guard names it, one a feature source whatever its
    threshold, one the chair, numbered from 1 in the order the states first name them, a clock's
    `since` included; and a world given keys that miss one is refused."""
    trial = Trial(start="one", states=[
        State("one", go=[On(ChairStill(), "two"), On(Pressed("lever"), "two"),
                         On(After(1.0), Outcome.ABORT)]),
        State("two", go=[On(After(0.1, since=Response("bar")), "three"),
                         On(FeatureAbove("rate", 3.0), "three"), On(Released("lever"), "three"),
                         On(After(1.0), Outcome.ABORT)]),
        State("three", go=[On(FeatureAbove("rate", 9.0), Outcome.CORRECT),
                           On(Response("bar"), Outcome.CORRECT), On(After(1.0), Outcome.ABORT)]),
    ])
    numbered = pointer.inputs(trial)
    assert numbered == (pointer.Input(1, ChairStill()), pointer.Input(2, Pressed("lever")),
                        pointer.Input(3, Response("bar")),
                        pointer.Input(4, FeatureAbove("rate", 3.0)))
    clock, page, source, pace = _rig()
    with pytest.raises(ValueError, match="feature rate"):
        pointer.Pointing(source, trial, FRAME, {}, pace=pace, keys=numbered[:3])


def test_more_than_nine_inputs_are_refused_naming_them():
    """A task naming more than nine inputs cannot be played by hand (§3.4): refused, naming those
    past the ninth, as a `ValueError`; and a demo's worlds refuse it."""
    names = [f"lever_{letter}" for letter in "abcdefghijk"]
    trial = Trial(start="s", states=[State(
        "s", go=[On(Pressed(name), Outcome.CORRECT) for name in names]
        + [On(After(1.0), Outcome.NO_RESPONSE)])])
    with pytest.raises(pointer.TooManyInputs) as refused:
        pointer.inputs(trial)
    assert isinstance(refused.value, ValueError)
    message = str(refused.value)
    assert "lever_j, lever_k would have none" in message and "lever_i" not in message
    assert "names 11" in message
    assert [item.label for item in refused.value.inputs] == names
    clock, page, source, pace = _rig()
    with pytest.raises(pointer.TooManyInputs):
        pointer.worlds(source, pace=pace)(trial, {}, 0)
    assert len(pointer.inputs(replace(trial, states=[replace(
        trial.states[0], go=trial.states[0].go[:9] + trial.states[0].go[11:])]))) == 9


# --- Bounded work, a malformed report, the pace, the noise ------------------------------------


def test_the_drain_takes_at_most_64_messages_a_frame():
    """§3.8: bounded work, whatever arrives: 100 waiting, a frame reads 64 and keeps the newest of
    them, the next the other 36."""
    clock, page, source, _ = _rig(noise_deg=0.0)
    for seq in range(1, 101):
        page.send(T0, report(seq, seq / 10, 0.0))
    first = source.poll(0.0)
    assert page.calls == pointer.DRAIN == 64 and len(page.waiting) == 36
    assert first.left.dpi_x() == 6.4
    second = source.poll(FRAME)
    assert page.calls == 64 + 37 and len(page.waiting) == 0
    assert second.left.dpi_x() == 10.0
    assert source.stale == 63 + 35


def test_a_malformed_message_is_counted_and_dropped():
    """One the wrong size, one with a NaN x, one with an infinite y: each counted and dropped, as a
    malformed mark is (§3.8), and the frame goes on with the good one."""
    clock, page, source, _ = _rig(noise_deg=0.0)
    page.send(T0, report(1, 2.0, 1.0))
    page.send(T0, report(5, 9.0, 9.0)[:40])
    page.send(T0, report(6, math.nan, 9.0))
    page.send(T0, report(7, 9.0, math.inf))
    sample = source.poll(0.0)
    assert source.malformed == 3 and source.stale == 0
    assert (sample.left.dpi_x(), sample.left.dpi_y()) == (2.0, 1.0)
    page.send(T0, report(2, 3.0, 1.0))
    assert source.poll(FRAME).left.dpi_x() == 3.0


def test_pacing_waits_for_each_frames_moment():
    """§3.5: from a trial's first frame, each frame waits until its moment, a frame period apart,
    on the injected clock."""
    clock = _Clock()
    pace = pointer.Pace(FRAME, clock=clock, sleep=clock.sleep)
    pace.start()
    for frame in range(2, 7):
        clock.t += 0.001
        pace.wait(frame)
        assert clock.t == pytest.approx(T0 + (frame - 1) * FRAME, abs=1e-12)
    assert clock.slept == pytest.approx([FRAME - 0.001] * 5, abs=1e-12)


def test_a_late_frame_runs_at_once_and_moves_the_schedule_on():
    """§3.5: a frame already late runs at once, and the schedule moves on from it: the next frame
    waits a whole frame from then, never a catch-up burst."""
    clock = _Clock()
    pace = pointer.Pace(FRAME, clock=clock, sleep=clock.sleep)
    pace.start()
    pace.wait(2)
    clock.t += 3.5 * FRAME
    late = clock.t
    pace.wait(3)
    assert clock.t == late and len(clock.slept) == 1
    pace.wait(4)
    assert clock.t == pytest.approx(late + FRAME, abs=1e-12)
    pace.wait(5)
    assert clock.t == pytest.approx(late + 2 * FRAME, abs=1e-12)
    assert clock.slept[1:] == pytest.approx([FRAME, FRAME], abs=1e-12)
    # A new trial's first frame starts a schedule of its own.
    clock.t += 10.0
    pace.start()
    start = clock.t
    pace.wait(2)
    assert clock.t == pytest.approx(start + FRAME, abs=1e-12)


def test_the_noise_is_drawn_from_the_runs_seed():
    """§3.3, §14 item 16: the noise is `simeye.NOISE_DEG` per axis, drawn from a generator of the
    run's seed, so the same run's seed draws the same noise and another seed other noise."""
    def noise(seed: int, **given) -> list:
        clock, page, source, _ = _rig(seed=seed, **given)
        page.send(T0, report(1, 1.0, 2.0))
        drawn = []
        for frame in range(5):
            sample = source.poll(frame * FRAME)
            drawn += [sample.left.dpi_x() - 1.0, sample.left.dpi_y() - 2.0]
            assert sample.left is sample.right
        return drawn

    clock, page, source, _ = _rig(seed=7)
    assert source.noise_deg == simeye.NOISE_DEG == pointer.Source(
        page.receive, seed=7).noise_deg
    expected = random.Random("7: the mouse's noise")
    assert noise(7) == pytest.approx([expected.gauss(0.0, simeye.NOISE_DEG) for _ in range(10)],
                                     abs=1e-12)
    assert noise(7) == noise(7) and noise(8) != noise(7)
    assert noise(7, noise_deg=0.0) == [0.0] * 10


# --- The screen, to the page (§3.9) ------------------------------------------------------------


def _drawing(**over) -> pointer.Drawing:
    """A demo's drawing on this rig's direct view, its housings the stand-ins, on the default
    calibration."""
    return pointer.Drawing(RIG, DIRECT, SRGB, session_id=over.pop("session_id", "demo-1"),
                           stand_in=over.pop("stand_in", True))


def test_a_drawing_and_a_publisher_go_together():
    """`pointer._paired`: a drawing with no publisher would be resolved for nobody, and a publisher
    with no drawing would never be called, the page left blank with nothing raising; so either
    alone is refused, by `worlds` and by `Pointing`. Neither is an in-process world's, which
    publishes nothing, at its end too."""
    clock, page, source, pace = _rig()
    for given in (dict(publish=print), dict(drawing=_drawing())):
        with pytest.raises(ValueError, match="give a `Drawing` and a publisher together"):
            pointer.worlds(source, pace=pace, **given)
        with pytest.raises(ValueError, match="give a `Drawing` and a publisher together"):
            pointer.Pointing(source, FIX, FRAME, {}, pace=pace, keys=(), **given)
    world = _world(FIX, source, pace)
    assert world.drawing is None and world.publish is None
    world.ended()


def test_a_trial_waits_while_no_page_steers_showing_the_field():
    """Demo mode's Task 10: before a run's first screen a page has nothing to point at, so
    `Worlds.waiting` says the first trial waits while no report has arrived -- a malformed one is
    none -- publishing the field each time it is asked: blank, frame 0, the trial's index, no
    windows and no keys, the setup's viewports and housings. Once a report is heard it waits no
    longer, and the report is kept for the trial's first frame (`Source.steered`). **And so does
    every later trial** (the whole-build review's I3): once the reports stop and a trial outlives
    the last by `LIVE_S`, the next waits, until a report arrives; one still current at the
    boundary waits not at all. Without a drawing nothing is published."""
    clock, page, source, pace = _rig()
    link = Simulated()
    drawing = _drawing(session_id="demo-2026-11-14_1012")
    made = pointer.worlds(source, pace=pace, drawing=drawing, publish=link.publish)
    assert made.waiting(0) is True and made.waiting(0) is True
    page.send(clock.t, b"short")
    assert made.waiting(0) is True and source.malformed == 1, "a malformed report is none"
    fields = [d for d in link.published if isinstance(d, Drawn)]
    assert len(fields) == 3, "the field, each time it is asked"
    field = fields[0]
    assert (field.session_id, field.trial, field.frame, field.screen) == (
        "demo-2026-11-14_1012", 0, 0, None)
    assert (field.windows, field.outlines, field.keys) == ((), (), ())
    assert field.viewports == drawing.viewports and field.housings == tuple(DIRECT.housings)
    assert field.stand_in is True and decode(encode(field)) == field
    assert drawing.field(3).trial == 3

    page.pointer(clock.t, 2.0, 1.0)
    assert made.waiting(0) is False and made.waiting(0) is False
    assert len([d for d in link.published if isinstance(d, Drawn)]) == 3, "nothing more drawn"
    world = made(FIX, {}, 0)
    world.display({}, 1)
    assert world.gaze_cyclopean(1) == pytest.approx((2.0, 1.0), abs=0.2), "the report, kept"

    # The page lets go (Escape): the trial outlives the last report, and the next trial waits.
    _drive(world, round(pointer.LIVE_S / FRAME) + 2)
    assert made.waiting(1) is True and made.waiting(1) is True, "nobody steers: it waits"
    fields = [d for d in link.published if isinstance(d, Drawn) and d.frame == 0]
    assert [(d.trial, d.screen, d.keys) for d in fields[3:]] == [(1, None, ())] * 2
    page.pointer(clock.t, -1.0, 0.5)
    assert made.waiting(1) is False, "a page points again"
    later = made(FIX, {}, 1)
    _drive(later, 4)
    assert later.gaze_cyclopean(4) == pytest.approx((-1.0, 0.5), abs=0.2), "the report, kept"
    assert made.waiting(2) is False, "a report still current at the boundary: no wait"
    _, _, alone, paced = _rig()
    assert pointer.worlds(alone, pace=paced).waiting(0) is True, "without a drawing too"


def test_a_source_is_steered_while_a_report_is_kept_or_current_in_hand():
    """`Source.steered`: false with nothing waiting, or only a malformed report; true once a report
    is kept for the next trial's first frame, and while the one in hand is current; **false again
    once a trial has outlived it by `LIVE_S`** (the whole-build review's I3), true again with the
    next. The source's clock stands still between trials, so a report current at a trial's last
    frame is current at its boundary."""
    clock, page, source, pace = _rig()
    assert source.steered() is False
    page.send(clock.t, report(1, float("nan"), 0.0))
    assert source.steered() is False and source.malformed == 1
    page.pointer(clock.t, 0.0, 0.0)
    assert source.steered() is True
    world = _world(FIX, source, pace)
    _drive(world, round(pointer.LIVE_S / FRAME) - 2)
    assert source.steered() is True, "a report in hand, still current"
    _drive(world, round(pointer.LIVE_S / FRAME) + 2)
    assert source.steered() is False, "the trial outlived it"
    assert source.steered() is False, "between trials the source's clock stands still"
    page.pointer(clock.t, 1.0, 0.0)
    assert source.steered() is True


#: **A trial whose screen changes once**: the dot from its first frame; a transition that changes
#: nothing shown; the goal shown beside the dot; a key waited on, never pressed.
_SHOWING = Trial(
    start="a",
    windows=[Window("fix", at=(0.0, 0.0), radius=2.0, on="dot"),
             Window("goal", at=(8.0, 0.0), radius=2.0, on="goal")],
    states=[
        State("a", enter=[Show(DOT)], go=[On(After(1.2), "b")]),
        State("b", go=[On(After(1.3), "c", do=[Show(TARGET)])]),
        State("c", go=[On(After(1.2), Outcome.CORRECT), On(Pressed("lever"), Outcome.ABORT)]),
    ],
)


def test_pointing_publishes_at_start_on_a_change_each_second_and_a_blank_at_the_end():
    """§3.9: a demo's world publishes its screen whole on the trial's first frame, on the first
    frame its screen changed (never for a transition that changed nothing shown), at least every
    `REDRAWN_EVERY_S` of the trial's clock, and, once the trial has ended (`ended`, which the
    session calls), blank: no screen and no windows, as the animal's is until the next trial. Each
    carries the trial and frame, the setup's viewports, housings and field edge, the stand-in flag
    and the keys, each stimulus's first frame (its onset, from which a drift is timed), and crosses
    the wire whole. A trial's first frame is published though it shows nothing."""
    clock, page, source, pace = _rig()
    _still(page, 0.0, 0.0, range(1, 1000))
    link = Simulated()
    world = pointer.worlds(source, pace=pace, drawing=_drawing(session_id="demo-2026-11-14_1012"),
                           publish=link.publish)(_SHOWING, {}, 4)
    shown: dict = {}
    display = world.display

    def watched(visible, frame: int) -> None:
        shown[frame] = tuple(visible)
        display(visible, frame)

    world.display = watched
    result = run_trial(_SHOWING, world, FRAME, effects=Recorded())
    world.ended()

    assert result.outcome is Outcome.CORRECT and result.visited == ("a", "b", "c")
    every = round(pointer.REDRAWN_EVERY_S / FRAME)
    last = max(shown)
    changed = min(frame for frame, names in shown.items() if "goal" in names)
    assert shown[changed - 1] == ("dot",)
    expected = [*range(1, changed, every), *range(changed, last + 1, every), last]
    assert [drawn.frame for drawn in link.published] == expected
    assert 1 + every < changed < changed + every < last, "redrawn before its change and after"

    *drawings, blank = link.published
    for drawn in link.published:
        assert (drawn.phase, drawn.session_id, drawn.trial) == ("drawn", "demo-2026-11-14_1012", 4)
        assert drawn.viewports == viewport.viewports(RIG, DIRECT)
        assert drawn.housings == DIRECT.housings and drawn.stand_in is True
        assert drawn.mask_deg is None and drawn.keys == ("lever",)
        assert decode(encode(drawn)) == drawn
    for drawn in drawings:
        assert drawn.screen.frame == drawn.frame
        onsets = {item.name: item.onset_frame for item in drawn.screen.items}
        assert onsets == ({"dot": 1, "goal": changed} if drawn.frame >= changed else {"dot": 1})
        assert [window.name for window in drawn.windows] == ["fix", "goal"]
        assert drawn.outlines == ()
    assert (blank.screen, blank.windows, blank.outlines) == (None, (), ())

    clock, page, source, pace = _rig()
    _still(page, 0.0, 0.0, range(1, 100))
    link = Simulated()
    later = Trial(start="a", states=[State("a", go=[On(After(0.1), "b", do=[Show(DOT)])]),
                                     State("b", go=[On(After(0.1), Outcome.CORRECT)])])
    world = pointer.worlds(source, pace=pace, drawing=_drawing(), publish=link.publish)(later, {}, 0)
    run_trial(later, world, FRAME, effects=Recorded())
    world.ended()
    first, shown_later, blank = link.published
    assert (first.frame, first.screen.items) == (1, ())
    assert [item.name for item in shown_later.screen.items] == ["dot"] and blank.screen is None


def test_an_undrawable_kind_and_a_look_with_no_value_are_outlines_saying_why():
    """§4.4 (§14 item 3): a stimulus the drawer does not draw yet (`screen.NotYetDrawable` names
    its build) and one whose look has no value are outlines where they are, at their size or
    `OUTLINE_DEG` where it cannot be read, each saying why -- an array's, one an object -- and the
    rest of the screen is resolved and drawn. Given its value, the look is drawn."""
    clock, page, source, pace = _rig()
    world = _world(FIX, source, pace)
    ring = Array(n=3, radius=6.0, looks=Noise(aperture=2.0), among=Noise(aperture=2.0))
    visible = {
        "dot": DOT,
        "picture": Stimulus("picture", at=(4.0, 4.0), looks=Picture(size=3.0)),
        "odd": Stimulus("odd", at=(-4.0, 0.0), looks=P("odd_color")),
        "ring": Stimulus("ring", at=(0.0, 0.0), looks=ring),
    }

    drawn = _drawing().drawn(world, visible, {}, FIX, 0, 7)

    assert [item.name for item in drawn.screen.items] == ["dot"]
    outlines = {outline.name: outline for outline in drawn.outlines}
    assert list(outlines) == ["picture", "odd", "ring.0", "ring.1", "ring.2"]
    picture, odd = outlines["picture"], outlines["odd"]
    assert (picture.x_deg, picture.y_deg, picture.size_deg) == (4.0, 4.0, 3.0)
    assert picture.why == "not drawn yet: Picture is drawn in engine build A4"
    assert (odd.x_deg, odd.y_deg, odd.size_deg) == (-4.0, 0.0, pointer.OUTLINE_DEG)
    assert odd.why == "it has no value to be drawn with: no value bound for parameter 'odd_color'"
    for i, (x, y) in enumerate(ring.positions({}, (0.0, 0.0))):
        outline = outlines[f"ring.{i}"]
        assert (outline.x_deg, outline.y_deg, outline.size_deg) == (x, y, 2.0)
        assert outline.why == "not drawn yet: Noise is drawn in engine build A3"
    assert decode(encode(drawn)) == drawn

    valued = _drawing().drawn(world, visible, {"odd_color": Disc(size=1.0, color=Gray(40.0))},
                              FIX, 0, 7)
    assert [item.name for item in valued.screen.items] == ["dot", "odd"]
    assert [outline.name for outline in valued.outlines] == ["picture", "ring.0", "ring.1", "ring.2"]


# --- The mouse and the simulated eye -----------------------------------------------------------

ROOT = Path(__file__).resolve().parents[1]
#: Where a wl-xtasks checkout is looked for, as `tests/test_popout_search.py` looks.
_XTASKS = next((c for c in (ROOT / "wl-xtasks", ROOT.parent / "wl-xtasks")
                if (c / "tasks" / "popout_search.py").is_file()), None)
#: How many trials the agreement test plays.
TRIALS = 200


class _Kept:
    """A gaze source that keeps each sample it hands over (as `tests/test_simeye.py`'s)."""

    def __init__(self, source, kept: list) -> None:
        self.source, self.kept = source, kept

    def poll(self, at: float):
        sample = self.source.poll(at)
        self.kept.append(sample)
        return sample


class _OneAFrame:
    """**A page sending one report a frame**, a trial's in order: report `i` read once the clock has
    reached the trial's frame `i + 1`."""

    def __init__(self, clock: _Clock) -> None:
        self.clock = clock
        self.reports: list = []
        self.start = 0.0
        self.next = 0

    def load(self, reports: list, start: float) -> None:
        self.reports, self.start, self.next = reports, start, 0

    def receive(self, buffer: bytearray) -> int:
        if self.next >= len(self.reports):
            return -1
        if frame_at(self.start, self.next + 1) > self.clock.t + 1e-9:
            return -1
        message = self.reports[self.next]
        self.next += 1
        buffer[_SLOTS[len(message)]] = message
        return len(message)


class _Stops(Simulated):
    """A person's stop, drained before trial `after` (as `tests/test_popout_search.py`'s)."""

    def __init__(self, after: int) -> None:
        super().__init__()
        self.after, self.drains = after, 0

    def drain(self) -> list:
        self.drains += 1
        if self.drains == self.after:
            self.queue(Stop(by=Box("jake")))
        return super().drain()


def _session(root: Path, task: Path) -> Session:
    """A simulated session of the pop-out's plan from Fade-in on the simulators, out of its cage
    and its head fixed, its wall following its frames (`tests/test_popout_search.py`'s)."""
    spec = SessionSpec(
        task=str(task), allocation="tasks/allocation.py", root=root, session_id="2027-01-14_01",
        subject="A", trials=1, frame_period=FRAME, seed=5, values={},
        bounds=Bounds(subject="A",
                      ceilings={"reward_correct": Ceiling(value=0.15, maximum=0.40, unit="mL"),
                                "out_of_cage": Ceiling(value=28_800.0, maximum=100_000.0,
                                                       unit="s")},
                      minima={"daily_fluid": Floor(value=250.0, unit="mL")}),
        already_delivered_today=0.0, deployment=Deployment.RIG_FIXED, geometry=DIRECT,
        session_kind="training", calibration=SRGB, plan="training", start_block="Fade-in",
    )
    session = Session(spec, card=Card(), pump=Pump(), link=_Stops(TRIALS + 1))
    session.wall_clock = lambda: 1_700_000_000.0 + session.now()
    session.left_cage(at=session.wall_now())
    session.head_fixed(at=session.wall_now())
    return session


def _outcomes(session: Session) -> list:
    path = session.directory / "trials.jsonl"
    return [(row["outcome"], row["params"]) for row in map(json.loads,
                                                         path.read_text().splitlines())]


def test_the_mouse_and_the_simulated_eye_agree_on_the_popout(tmp_path, monkeypatch):
    """**Review Focus 4**: a simulated session of the pop-out search (read from wl-xtasks as
    `tests/test_popout_search.py` reads it), played by the simulated eye through `simeye.Seeing`,
    each frame's sample kept; then the same session through `Pointing`, those samples sent as the
    page's reports, one a frame, with no noise of the mouse's own since they carry the eye's: the
    same sample on every frame, so the same outcome every trial, at the same values (the outcomes
    alone survive a mouse a frame late or noisier, which the samples do not). The eye's paths and the mouse's are scored by one
    world, `gaze.Tracked`; this holds the mouse's source to the eye's samples (planner's call)."""
    if _XTASKS is None:
        if os.environ.get("WLX_REQUIRE_XTASKS") == "1":  # pragma: no cover - CI's
            pytest.fail("WLX_REQUIRE_XTASKS=1 but no wl-xtasks checkout holding "
                        "tasks/popout_search.py was found")
        pytest.skip("no wl-xtasks checkout holding tasks/popout_search.py")
    task = _XTASKS / "tasks" / "popout_search.py"

    played = []
    made = simeye.Eye.world

    def seen(eye, trial, values, frame_period):
        world = made(eye, trial, values, frame_period)
        kept: list = []
        played.append((dict(values), kept))
        world.source = _Kept(world.source, kept)
        return world

    monkeypatch.setattr(simeye.Eye, "world", seen)
    by_eye = _session(tmp_path / "eye", task)
    by_eye.run()
    monkeypatch.undo()
    assert len(played) >= TRIALS

    clock = _Clock()
    page = _OneAFrame(clock)
    source = pointer.Source(page.receive, seed=5, noise_deg=0.0)
    make = pointer.worlds(source, pace=pointer.Pace(FRAME, clock=clock, sleep=clock.sleep))
    replayed = []
    seq = iter(range(1, 10**9))

    def pointed(trial, values, index):
        number = len(replayed)
        sampled: list = []
        replayed.append((dict(values), sampled))
        kept = played[number][1] if number < len(played) else []
        page.load([report(next(seq), sample.left.dpi_x(), sample.left.dpi_y())
                   for sample in kept], clock.t)
        world = make(trial, values, index)
        world.source = _Kept(source, sampled)
        return world

    by_mouse = _session(tmp_path / "mouse", task)
    by_mouse.world = pointed
    by_mouse.run()

    eye, mouse = _outcomes(by_eye), _outcomes(by_mouse)
    assert len(eye) >= TRIALS
    assert mouse == eye
    assert [values for values, _ in replayed] == [values for values, _ in played]

    def positions(samples: list) -> list:
        return [(sample.at, sample.left.dpi_x(), sample.left.dpi_y(), sample.right.dpi_x(),
                 sample.right.dpi_y()) for sample in samples]

    for number, ((_, by_eye_samples), (_, by_mouse_samples)) in enumerate(zip(played, replayed)):
        assert positions(by_mouse_samples) == positions(by_eye_samples), number
    counted = Counter(outcome for outcome, _ in eye)
    assert counted["correct"] >= 50 and counted["wrong_target"] >= 5, counted
    assert source.stale == source.malformed == 0


def _popout():
    """The pop-out search, read from wl-xtasks as the agreement test reads it."""
    if _XTASKS is None:
        if os.environ.get("WLX_REQUIRE_XTASKS") == "1":  # pragma: no cover - CI's
            pytest.fail("WLX_REQUIRE_XTASKS=1 but no wl-xtasks checkout holding "
                        "tasks/popout_search.py was found")
        pytest.skip("no wl-xtasks checkout holding tasks/popout_search.py")
    from wl_xcon.cli import _load_task

    return _load_task(_XTASKS / "tasks" / "popout_search.py")


#: **The page's animation frames**, which it reports the pointer on while it moves: 60 Hz.
_ANIMATION = 1 / 60


def _glided(task, glide_s: float, seed: int) -> str:
    """**One pop-out trial answered by a hand's glide**, as the whole-build review's probe played it
    (I2): the pointer resting off the fixation point, onto it at 0.5 s, and at 1.1 s,
    long after the discs are on, a glide of `glide_s` on the minimum-jerk profile to the odd disc
    8° away. **The page as it reports**: a report every animation frame while the pointer moves,
    every 100 ms while it is still, each reaching the rig half a round trip after it was sent, the
    round trip drawn for each report from 2 to 12 ms (assumed, not measured), from `seed`, which
    seeds the mouse's noise too. How it ended: `"correct"`; `"landing bound"`, the pop-out's
    `flight` ended by its own 0.3 s bound on landing (an abort); `"second look"`, ended by a second
    saccade's onset in flight (an abort); or the outcome's value."""
    trial = task.trial
    values = {param.name: param.start for param in task.params if param.start is not None}
    odd, among = task.pool.choices[0]
    values.update(odd_color=odd, distractor_color=among, set_size=4, array_rotation=0.0,
                  response_deadline=3.0, inter_trial=0.3, fix_hold=0.3, target_hold=0.1,
                  timeout=0.0)
    clock, page, source, pace = _rig(seed=seed)
    timing = random.Random(f"{seed}: the page's round trips")

    def sent(at: float, x: float, y: float) -> None:
        page.pointer(at + timing.uniform(0.002, 0.012) / 2, x, y)

    for k in range(5):
        sent(T0 + 0.1 * k, -4.0, -4.0)
    for k in range(6):
        sent(T0 + 0.5 + 0.1 * k, 0.0, 0.0)
    start, k = T0 + 1.1, 0
    while True:
        tau = min(k * _ANIMATION / glide_s, 1.0)
        sent(start + k * _ANIMATION, 8.0 * tau ** 3 * (10 - 15 * tau + 6 * tau * tau), 0.0)
        if tau >= 1.0:
            break
        k += 1
    for j in range(1, 40):
        sent(start + k * _ANIMATION + 0.1 * j, 8.0, 0.0)
    world = pointer.worlds(source, pace=pace)(trial, values, 0)
    began: dict = {}
    told = world.began

    def beginning(state: str, frame: int) -> None:
        began.setdefault(state, frame)
        told(state, frame)

    world.began = beginning
    outcome = run_trial(trial, world, FRAME, values=values, effects=Recorded()).outcome
    if outcome is not Outcome.ABORT or "astray" not in began:
        return outcome.value
    flown = (began["astray"] - began["flight"]) * FRAME
    return "landing bound" if flown >= 0.3 - FRAME / 2 else "second look"


def test_a_glide_reported_irregularly_is_one_saccade_scored_correct():
    """**The whole-build review's I2, closing XC-508**: the pop-out answered by a hand's glide to
    the odd disc, the page's reports an animation frame apart arriving a few milliseconds early or
    late.
    Eased only over the gap since the report before, a move whose next report came a little later
    than that gap stopped between the two, and the rig's detector saw two saccades, the second a
    second look in flight, an abort: the old code ends 5 of these twelve 400 ms glides so, and all
    twelve 600 ms ones. `pointer.EASE_SLACK_S` eases each over the gap and that slack: **every 400
    ms glide is scored correct, and no glide is a second look.** A 600 ms glide is slow enough that
    the pop-out's own 0.3 s bound on landing sometimes ends it, with regular reports too (3 of 60
    seeds here, 2 of 30 in the review's probe): that bound is the task's, which the PI's try-out is
    to judge, so it is told apart here, never counted against the reports (one of these twelve).
    Fixed seeds."""
    task = _popout()
    ended = {(glide_s, seed): _glided(task, glide_s, seed)
             for glide_s in (0.4, 0.6) for seed in range(12)}
    assert {how for (glide_s, _), how in ended.items() if glide_s == 0.4} == {"correct"}, ended
    assert set(ended.values()) <= {"correct", "landing bound"}, ended
    assert sum(how == "correct" for (glide_s, _), how in ended.items() if glide_s == 0.6) >= 10


def test_the_drawn_windows_are_those_tracked_scores_with_the_target_flagged():
    """§3.9, §4.4 (§14 item 4): the pop-out's ring of twelve, turned 33°, drawn as `gaze.Tracked`
    scores it -- each window the center and radius the world judges gaze against on that frame,
    the array's object windows where the trial placed them, its target's object flagged, at its
    placed center, where the drawer draws the odd disc; and the aliases' own stand-ins, which no
    gaze is scored against, never drawn."""
    task = _popout()
    trial = task.trial
    values = {param.name: param.start for param in task.params if param.start is not None}
    odd, among = task.pool.choices[0]
    values.update(odd_color=odd, distractor_color=among, set_size=12, array_rotation=33.0)
    (array,) = [action.stimulus for _, action in actions_of(trial)
                if isinstance(action, Show) and action.stimulus.name == "search"]
    clock, page, source, pace = _rig()
    world = pointer.worlds(source, pace=pace)(trial, values, 0)
    visible = {"search": array}
    world.display(visible, 1)

    drawn = _drawing().drawn(world, visible, values, trial, 0, 1)

    names = [window.name for window in drawn.windows]
    # The fixation point's own window scores it throughout since the pop-out's revision (its
    # design's §2: the point stays on), no remembered `center` beside it.
    assert names == ["fix", *(f"search.{i}" for i in range(12))]
    for window in drawn.windows:
        assert (window.x_deg, window.y_deg, window.radius_deg) == world._judged[window.name]
        assert window.eye == "both"
    (target,) = [window for window in drawn.windows if window.target]
    placed = array.looks.positions(values, (0.0, 0.0))
    assert target.name == "search.0" and (target.x_deg, target.y_deg) == placed[0]
    # A multiple of the disc's radius since the console settings plan's Task 11: 3.0 about 1°.
    assert target.radius_deg == values["object_window"] * values["disc_size"] / 2
    # On the ring's true circle, the ring turned 33° (`task.Array.positions`).
    assert polar_of_deg(*placed[0]) == pytest.approx((values["ring_radius"], 33.0))
    odd_disc = next(item for item in drawn.screen.items if item.name == "search.0")
    assert odd_disc.at_left == pytest.approx((target.x_deg, target.y_deg), abs=1e-12)
    assert len(drawn.screen.items) == 12 and drawn.outlines == ()


# --- The hot path -----------------------------------------------------------------------------

#: **What a frame of a trial through `gaze.Tracked` builds** (`tests/test_simeye.py`'s
#: `_TRACKED_FRAME`): each eye's gaze through its map, and the two eyes' mean the detector is fed.
_TRACKED_FRAME = {("Mapping.degrees_of", "tuple"), ("Tracked.gaze_cyclopean", "tuple")}
#: **And the mouse's sample**: its image position, the pair `(x, y)` the map reads.
_THE_SAMPLE = {("Source.poll", "tuple")}
#: What a frame that takes an edge builds besides (`tests/test_simeye.py`'s `_A_TRANSITION`).
_A_TRANSITION = {
    ("Shown.__new__", "tuple"), ("Placed.__new__", "tuple"), ("Changed.__new__", "tuple"),
    ("_apply", "tuple"), ("_apply", "dict"), ("_apply", "arguments"),
    ("Recorded.mark", "tuple"), ("Recorded.reward", "tuple"),
}

#: A trial through the kinds of guard `Pointing` answers on a frame: fixate, hold (a lever press or
#: the light sensor would end it), the go (a response key would), a saccade to the goal, and a hold
#: there (a touch or a feature would end it). **No clock timed from an event** (`After(since=...)`):
#: the loop itself builds a tuple each frame for one (XC-503), which is not the mouse's.
_SEARCH = Trial(
    start="await_fix",
    windows=[Window("fix", at=(0.0, 0.0), radius=2.0, on="dot"),
             Window("goal", at=(8.0, 0.0), radius=2.0, on="goal")],
    states=[
        State("await_fix", enter=[Show(DOT)],
              go=[On(Entered("fix"), "hold"), On(After(2.0), Outcome.NO_FIXATION)]),
        State("hold", go=[On(Hold("fix", 0.2), "go", do=[Hide("dot"), Show(TARGET)]),
                          On(Pressed("lever"), Outcome.ABORT), On(Onscreen(), Outcome.ABORT),
                          On(Exited("fix"), Outcome.FIXATION_BREAK)]),
        State("go", go=[On(SaccadeTo("goal"), "on"), On(Response("bar"), Outcome.ABORT),
                        On(After(1.0), Outcome.NO_RESPONSE)]),
        State("on", go=[On(Hold("goal", 0.2), Outcome.CORRECT),
                        On(Touched("goal"), Outcome.ABORT),
                        On(FeatureAbove("rate", 1.0), Outcome.ABORT),
                        On(After(1.0), Outcome.NO_RESPONSE)]),
    ],
)


@pytest.mark.parametrize("drawn", [False, True], ids=["in process", "drawn for the page"])
def test_a_frame_with_no_screen_change_builds_only_the_sample(monkeypatch, drawn):
    """**Hot-path discipline** (CLAUDE.md; the demo plan's Global Constraints): every frame of a
    trial through `Pointing` whose screen does not change builds only what `gaze.Tracked` builds on
    a rig's frame and the mouse's sample, its keys kept in integers and its reports read into
    buffers made once; measured on the whole frame, `run._Loop.frame` as `run_trial` calls it, as
    `tests/test_simeye.py` measures the simulated eye's (`_builds.built_on`, which reads what a
    tracemalloc snapshot could not tell apart: whose code built what). And every method a frame can
    run, read whole, builds nothing but the sample. A frame whose screen changed copies what it
    shows (`Pointing._shown_now`), and is kept apart. **Drawn for the page** (§3.9), a frame that
    publishes nothing builds nothing more -- whether one is due is two integers compared -- and a
    frame that publishes, on a change or every `REDRAWN_EVERY_S`, builds its `Drawn`, which a demo
    may spend, and is kept apart too."""
    records = {record.__new__.__code__: f"{record.__name__}.__new__"
               for record in (Shown, Placed, Changed, Confirmed)}
    clock, page, source, pace = _rig()
    _still(page, 5.0, 5.0, range(1, 60))
    _still(page, 0.0, 0.0, range(60, 150))
    for step in range(1, 7):
        page.pointer(frame_at(T0, 148 + 4 * step), 8.0 * step / 6, 0.0)
    _still(page, 8.0, 0.0, range(176, 600))
    published: list = []
    if drawn:
        # Redrawn every quarter second, so this short trial is redrawn with nothing changed too.
        monkeypatch.setattr(pointer, "REDRAWN_EVERY_S", 0.25)
        world = pointer.worlds(source, pace=pace, drawing=_drawing(),
                               publish=published.append)(_SEARCH, {}, 0)
    else:
        world = _world(_SEARCH, source, pace)
    frame_of = run._Loop.frame
    measured, steady, took, redrawn, republished = [], set(), set(), [], []

    def measured_frame(loop, frame: int) -> bool:
        ended, states, sent = [], len(loop.visited), len(published)

        def step() -> None:
            ended.append(frame_of(loop, frame))

        built = set(built_on(step, named=records))
        measured.append(frame)
        if len(published) != sent:
            # Kept apart whole: it builds its `Drawn`.
            republished.append(frame)
            if world._onscreen == frame:
                redrawn.append(frame)
        elif ended[0] or len(loop.visited) != states:
            took.update(built)
        elif world._onscreen == frame:
            redrawn.append(frame)
        else:
            steady.update(built)
        return ended[0]

    monkeypatch.setattr(run._Loop, "frame", measured_frame)
    result = run_trial(_SEARCH, world, FRAME, effects=Recorded())

    assert result.outcome is Outcome.CORRECT, result
    assert result.visited == ("await_fix", "hold", "go", "on")
    assert measured == list(range(1, result.frames + 1))
    assert len(redrawn) == 2 and redrawn[0] == 1, redrawn
    if drawn:
        every = round(pointer.REDRAWN_EVERY_S / FRAME)
        due, expected = 0, []
        for frame in measured:
            if frame in redrawn or frame >= due:
                expected.append(frame)
                due = frame + every
        assert [d.frame for d in published] == expected == republished
        assert set(expected) - set(redrawn), "redrawn with nothing changed too"
    else:
        assert published == [] and republished == []
    assert sorted(steady - _TRACKED_FRAME - _THE_SAMPLE) == []
    assert sorted(took - _TRACKED_FRAME - _THE_SAMPLE - _A_TRANSITION) == []
    on_a_frame = (pointer.Pointing.display, pointer.Pointing.happened, pointer.Pointing._touching,
                  pointer.Pointing._changed, pointer.Source.held, pointer.Source.went_down,
                  pointer.Source.went_up, pointer.Source._live, pointer.Source._drain,
                  pointer.Source._adopt, pointer.Source._ease, pointer.Source._edges,
                  pointer.Pace.start, pointer.Pace.wait)
    assert [built for method in on_a_frame for built in builds_of(method)] == []
    assert builds_of(pointer.Source.poll) == [("Source.poll", "tuple")]
