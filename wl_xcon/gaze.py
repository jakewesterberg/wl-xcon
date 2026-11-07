"""The join: a tracker, a versioned map, and a trial's windows, as a `World`.

Four modules become one working path here. `eye` produces samples in camera pixels,
`calibration` turns a raw Purkinje vector into degrees at a stated mapping version,
`task` declares where the windows are, and `run` asks one question -- *is gaze inside
this window* -- without knowing that any of the above exists.

**What this deliberately does not do.** It does not decide what entering, leaving or
holding mean; the trial loop derives those from membership so the semantics exist
once, and a world that re-derived them would let the simulator and the rig disagree
about what a hold is. It does not implement staleness either: `Tracker.state` owns
that, and this reports it.

**Saccades arrive from `saccade.Detector`, and the two guards are different events.**
`SaccadeOnset` fires on the frame a saccade is *confirmed* -- which trails its true
onset, by arithmetic the detector's docstring sets out. `SaccadeTo(window)` cannot fire
then, because at confirmation the eye is still in flight and has not landed anywhere;
it fires once the saccade has ended and gaze is inside the named window. Conflating the
two would make `SaccadeTo` fire on a saccade heading somewhere else entirely.

**A saccade's landing is taken by the `SaccadeTo` that fires on it, and its onset is
only observed.** Without the first, one saccade satisfies `SaccadeTo` on every
subsequent frame gaze stays in the window, which is indistinguishable from the animal
saccading there repeatedly and turns one response into a stream of them. `SaccadeOnset`
fires on the one frame the saccade is confirmed, for every guard of the state that asks
then, a clock's (`After(since=SaccadeOnset())`) and an edge's alike, so a clock started
by an onset neither uses up the landing nor keeps the onset from an edge (the
controller's rulings, 2026-10-30).

**Which saccade counts for a state: a `SaccadeOnset` by its onset, a `SaccadeTo` by where its eye
stopped, judged where it landed** (XC-410, the PI, 2026-10-30; "Count it both ways", the PI,
2026-11-06). **A `SaccadeOnset` counts only a saccade begun in its state**: one begun before it is
anticipatory, as an early response would be ("No; it must start in the state"). **A `SaccadeTo`
counts any saccade the detector puts at rest (its stop field, `Saccade.stop`, as `saccade.detect`
reports it) on its state's first frame or after, wherever its onset fell**, judged on the frame it
lands, against the windows drawn then: "A saccade to X lands in X's window at the moment it lands."
That rule is the PI's answer of 2026-11-06 as built: "The same eye movement scores the same
whichever way the task is written: a saccade already under way at the go cue counts where it lands.
The rule that a saccade counts only in the state it began in gets one exception: a saccade in flight
when the go cue's state begins". Which state is the go cue's the world cannot know, so a saccade in
flight as any state begins counts there, whatever edge entered it, and a stop always follows its
onset, so one begun in the state comes to rest on its first frame or after too: **for a `SaccadeTo`
the in-flight rule is the whole rule**, and XC-410's "it must start in the state" now governs only a
`SaccadeOnset`, which a carried saccade never satisfies (review 9 of the saccade rules, its I1,
2026-11-07). One whose eye stopped before the state's first frame landed in the state before and
counts for nothing there (the controller's ruling on the review's I1); a further transition while it
is still in flight carries it on. **The PI was asked (2026-11-07, in the UI)** whether a state that
waits for a saccade to the target counts any saccade whose eye stops there, wherever its onset fell,
and answered "Yes, count where it lands (Recommended)". So an intrasaccadic displacement, at once or
delayed, is scored where the eye lands ("Yes, that one saccade carries"; "Yes, carry it too"), so is
the saccade that takes the eye out of a window (2026-11-04, "Carry it over"; 2026-11-06, "Yes, count
it"), and so is an anticipation begun just before the go cue when the cue's state asks where the eye
lands or an `Exited` relays it, though not when a `SaccadeOnset` relays it (`task.SaccadeOnset`):
what were the onset's, the timer's and the exit's carries is one rule, and a timer from a state's
entry and `Entered` carry as any edge does, where until then they carried nothing. Past the go cue
too: XC-410's own case, a saccade begun the frame before a plain timer's state and landing in it,
scored no response until that answer and is scored where it lands since. Until XC-410 the last
saccade no guard had taken waited for the rest of the trial, so an object shown or moved onto where
it had landed took it on the frame the object was drawn there.

**The detector is per trial** (S5 §5), so a world is reset per trial; a threshold
carried across would let a quiet trial set a noisy one's sensitivity.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping as MappingType, NoReturn

from wl_xcon.calibration import Collector, Mapping, MappingLog
from wl_xcon.eye import Replay, Tracker
from wl_xcon.geometry import separation_deg
from wl_xcon.saccade import Detector
from wl_xcon.task import (
    Guard,
    Outcome,
    P,
    SaccadeOnset,
    SaccadeTo,
    Stimulus,
    Trial,
    Window,
    expand_windows,
    placements,
    position_of,
)


def _resolve(value: float | P, values: dict[str, float]) -> float:
    """A literal or a parameter reference, as a number. Mirrors `run._resolve`;
    kept here rather than imported to avoid a cycle, and small enough that the
    duplication is cheaper than the coupling."""
    return values[value.name] if isinstance(value, P) else value


def _placed(window: Window, values: dict) -> "tuple[float, float, float]":
    """A window's center and radius as the numbers gaze is compared with: its center in any form
    a task writes it, a `Polar` converted exactly (`position_of`), and its radius."""
    cx, cy = position_of(window.at, values)
    return (cx, cy, _resolve(window.radius, values))


def _judged(window: "Window | None", values: dict) -> "tuple[float, float, float] | Window | None":
    """**A window as `Tracked.in_window` judges it, resolved between trials** (XC-413): its center
    and radius (`_placed`), or `None` for no window. **A window these values cannot place stays as
    it is**, and is resolved where it is asked about, raising there as it always has, never when
    the world is built: a setting with no value bound (a world built for its gaze alone, as tests
    build one; a run that would start so is refused before it starts, `check.unplaced`, XC-415),
    or one bound to a value that is no position, which reaches a run only when `wlx run` binds one
    that is none of its choices (XC-159); a setting that can hold no value, or any choice that is
    no position, is refused at load (`check._position_kind_faults`).
    Raised here, it stopped a session on a trial that never asks about the window (the
    gaze-followups review, I1). So any exception is deferred, whatever it is."""
    if window is None:
        return None
    try:
        return _placed(window, values)
    except Exception:
        return window


def _untold(state: str, told: "str | None") -> NoReturn:
    """`Tracked._began_in`'s refusal, its message built as it is raised, never on a frame that
    asks."""
    raise RuntimeError(
        f"state {state!r} was asked about a saccade, and this world was told only that "
        f"{told!r} began: a `SaccadeTo` counts a saccade whose eye stops in its state and a "
        f"`SaccadeOnset` one that begins in it (XC-410), so the loop tells the world each "
        f"state's first frame (`run.World.began`)"
    )


def _closed(confirmed) -> NoReturn:
    """`Tracked.display`'s refusal of a saccade confirmed on a closed run, its message built as it
    is raised, never on a frame that confirms one in flight."""
    raise RuntimeError(
        f"the detector confirmed a saccade ({confirmed.start} to {confirmed.stop}) on a run already "
        f"closed: a gaze world lands a saccade as its detector's run closes, so it needs each one "
        f"confirmed while its run is open, as `saccade.Detector` confirms every one since version 3"
    )


class Tracked:
    """A `World` whose gaze comes from a real (or replayed) tracker.

    Frames are converted to session time as `frame * frame_period + started_at`,
    which is the only place the loop's frame clock and the tracker's arrival stamps
    meet. The loop counts frames because a display does; the tracker stamps arrivals
    because a poll-based protocol carries no clock we can trust (`eye.py`). Neither
    is wrong and the conversion has to live somewhere.
    """

    def __init__(
        self,
        tracker: Tracker,
        mapping: Mapping,
        trial: Trial,
        frame_period: float,
        values: dict[str, float] | None = None,
        started_at: float = 0.0,
        source=None,
        detector: Detector | None = None,
    ) -> None:
        self.tracker = tracker
        self.mapping = mapping
        self.frame_period = frame_period
        self.started_at = started_at
        #: Anything with `poll(at)` -- `eye.Replay` or `eye.UdpSource`. Optional so
        #: a test can drive the tracker directly, but on a rig this is how gaze
        #: arrives, and it is polled in `display` for the reason given there.
        self.source = source
        #: Per trial, per S5 §5. Supplied rather than created when a caller wants to
        #: log its parameters and version alongside the mapping version, and **fresh**:
        #: it numbers the samples this world feeds it, one a frame, from its first (`_fed`),
        #: so one already fed is refused (the review's M4): every onset would be placed later
        #: than it was, and a saccade begun before its state would count.
        if detector is not None and detector.seen:
            raise ValueError(
                f"this detector has already been fed {detector.seen} samples; a gaze world numbers "
                f"the samples it feeds from the detector's first, so it needs a fresh one, or one "
                f"reset (`Detector.reset`)"
            )
        self.detector = detector if detector is not None else Detector()
        #: **The last saccade the detector confirmed, as a guard may take it** (XC-410): the frame
        #: of its onset, its first sample (`Saccade.start`), by which a `SaccadeOnset` takes it
        #: only in the state it began in; the frame it was confirmed on, the one frame
        #: `SaccadeOnset` sees it; whether it is still in flight; the frame it landed on, the one
        #: frame `SaccadeTo` judges it on (`None` while in flight); the frame the detector puts the
        #: eye at rest on (its stop field, `Saccade.stop`, as `saccade.detect` reports it), by
        #: which a `SaccadeTo` counts it for its state or not, wherever its onset fell (`began`);
        #: and whether a `SaccadeTo` has taken it, as one has before any saccade is confirmed. A
        #: saccade in flight cannot have landed in anything. **Nothing is kept of the edge that
        #: began a state** (the PI, 2026-11-06, "Count it both ways"): until then whether the
        #: saccade's onset or a timer from it had ended the state before, a `SaccadeOnset` having
        #: seen it, or an `Exited` had.
        self._onset = 0
        self._confirmed_on: int | None = None
        self._in_flight = False
        self._landed_on: int | None = None
        self._stopped = 0
        self._taken = True
        #: How many samples this world has fed the detector, one each `display`: the next one's
        #: index in the detector's numbering, which `Saccade.start` counts in.
        self._fed = 0
        #: **The state the loop is in and its first frame** (`began`): a saccade counts for the
        #: state's `SaccadeOnset` only if its onset is on that frame or after, and for its
        #: `SaccadeTo` only if its eye is at rest on that frame or after. `None` until the loop
        #: says, and a saccade guard asked from a state this world was not told of is refused
        #: (`_untold`).
        self._state: str | None = None
        self._began = 0
        self._values = values or {}
        declared, aliases = expand_windows(trial, self._values)
        self._windows: dict = {window.name: window for window in declared}
        #: **An array's aliases, by the objects they name**: `<of>.target` and `<of>.distractor`
        #: to their objects' windows. `SaccadeTo` reaches the world directly rather than through
        #: the loop's membership, so this is where a saccade to "any distractor" is judged at every
        #: distractor, each with its own eye, and never at the alias's own window, a stand-in at the
        #: target that names the array and its eye. Switched with the windows in `display`.
        self._members: dict = dict(aliases)
        #: **An array's object windows follow it** (XC-402): each array with object windows, every
        #: placement it can be drawn in this trial, built now, between trials (`task.placements`),
        #: each with its windows judged (`_judged`); and the stimulus last seen drawing it.
        #: `display` switches `_windows` and `_judged` to the placement on the display, so an
        #: `Update` that moves an array moves its windows on the frame its objects are first drawn
        #: there. Every name any placement has is a key from the start, `None` while the placement
        #: drawn has no such object, so a switch adds none.
        self._arrays = tuple(
            (of, tuple((placement, {name: _judged(window, self._values)
                                    for name, window in placement.windows.items()})
                       for placement in options))
            for of, options in placements(trial, self._values).items()
        )
        self._drawn: dict = {of: None for of, _ in self._arrays}
        for _, options in self._arrays:
            for placement, _ in options:
                for name in placement.windows:
                    self._windows.setdefault(name, None)
                for alias in placement.members:
                    self._members.setdefault(alias, ())
        #: **Each window's center and radius as numbers, resolved now, between trials** (XC-413):
        #: `in_window` runs every frame for every window a guard asks about, and they change only
        #: when an array's placement switches, which swaps in the placement's own (`display`).
        self._judged: dict = {name: _judged(window, self._values)
                              for name, window in self._windows.items()}
        #: **Each eye's gaze, converted once a frame** however many windows ask (XC-413): the
        #: frame and the sample it was converted for, and each eye's position or `None`. Gaze at a
        #: frame is a function of the two, the map, the clock and the tracker's staleness being
        #: fixed for a world's trial; `display` converts it, for the detector, before any window is
        #: asked about, and a frame asked about without one, or a sample accepted since, converts
        #: it again.
        self._looked: int | None = None
        self._sample = None
        self._left: tuple[float, float] | None = None
        self._right: tuple[float, float] | None = None
        #: **The last sample `display` judged usable and the eyes' positions it converted to**
        #: (`_usable`), so the frame's one conversion is that one when the tracker still holds it.
        self._usable_sample = None
        self._usable_left: tuple[float, float] | None = None
        self._usable_right: tuple[float, float] | None = None
        #: Which mapping version scored this trial. S5 §6: every trial cites the
        #: version in force, and it is read off the map rather than passed in, so a
        #: trial cannot cite a version it was not actually scored under.
        self.mapping_version = mapping.version

    def when(self, frame: int) -> float:
        return self.started_at + frame * self.frame_period

    def gaze(self, which: str, frame: int) -> tuple[float, float] | None:
        """Where that eye is looking, in degrees, or `None`.

        `None` means one of three different things -- no sample yet, the sample is
        too old, or this eye has no map -- and they are deliberately not told apart
        here. The loop asks `signal` when it needs to know which, because a window
        test only ever needed the answer "not usable".

        **On the trial loop's path**, once a frame for each eye (`_look`), so the eye's
        dual-Purkinje vector reaches its map as its two numbers (`EyeReading.dpi_x`, `dpi_y`;
        `Mapping.degrees_of`) and the one thing built is the position returned (XC-414).

        **No position either where the map's answer is not finite**, for a tracker driven directly
        (the controller's ruling of 2026-11-06): a sample that reaches the world through `display`
        never gives one, being a lost sample there when its map's answer is not finite
        (`_usable`), its last good one held; a tracker given one some other way gives that eye no
        position on the frame rather than an infinity, which raised in a window's angle and the
        saccade detector's directions. A backstop, not the rule: an eye that has a map has a
        position on every frame the tracker is "ok", and one without has none on any.
        """
        if self.tracker.state(self.when(frame)) != "ok":
            return None
        sample = self.tracker.latest
        if sample is None:
            return None
        reading = getattr(sample, which)
        position = self.mapping.degrees_of(which, reading.dpi_x(), reading.dpi_y())
        if position is not None and not (math.isfinite(position[0])
                                         and math.isfinite(position[1])):
            return None
        return position

    def gaze_cyclopean(self, frame: int) -> tuple[float, float] | None:
        """Both eyes averaged, which is what the detector runs on. A per-eye detector
        would need a per-eye threshold and would answer a question no guard asks:
        `SaccadeOnset` is about the animal, not about one of its eyes. One eye alone when the
        other has no position, and `None` when neither has.

        **On the trial loop's path** (`display`, every frame), so each eye is the frame's one
        conversion (`_look`), and the mean is taken without a list or a generator (XC-413)."""
        if frame != self._looked or self.tracker.latest is not self._sample:
            self._look(frame)
        left = self._left
        right = self._right
        if left is None:
            return right
        if right is None:
            return left
        # Halved, then summed (the review of d932cb3, its I2): bit for bit `(a + b) / 2` wherever
        # that is finite and no subnormal number arises (`5e-324 * 0.5` is 0, where
        # `(5e-324 + 5e-324) / 2` is 5e-324; no gaze is near one), and finite whenever both eyes
        # are, where their sum could overflow.
        return (left[0] * 0.5 + right[0] * 0.5, left[1] * 0.5 + right[1] * 0.5)

    def _look(self, frame: int) -> None:
        """Each eye's gaze at `frame`, kept for the rest of the frame (`_looked`): the positions
        `display` converted the sample to when it judged it usable, while the tracker holds it and
        it is fresh, so a frame converts each eye once; else as `gaze` gives them."""
        sample = self.tracker.latest
        if sample is not None and sample is self._usable_sample:
            if self.tracker.state(self.when(frame)) == "ok":
                self._left = self._usable_left
                self._right = self._usable_right
            else:
                self._left = None
                self._right = None
        else:
            self._left = self.gaze("left", frame)
            self._right = self.gaze("right", frame)
        self._looked = frame
        self._sample = sample

    def _usable(self, sample) -> bool:
        """**Whether a sample is usable**: each eye's map's answer finite (the controller's ruling
        of 2026-11-06, on the review of d932cb3, its I3: a reading whose P1 - P4, map or eyes' mean
        is not finite is a lost sample for the whole datagram). `eye.parse` judges P1 - P4; the map
        is this world's, so it is judged here, before the tracker accepts the sample, and the eyes'
        mean, halved then summed, is finite whenever both eyes are. Until then an eye whose map
        overflowed had no position for that frame while the signal said "ok": a hold broke, and
        two such frames made a saccade. The positions are kept for the frame's conversion
        (`_look`)."""
        left = self.mapping.degrees_of("left", sample.left.dpi_x(), sample.left.dpi_y())
        if left is not None and not (math.isfinite(left[0]) and math.isfinite(left[1])):
            return False
        right = self.mapping.degrees_of("right", sample.right.dpi_x(), sample.right.dpi_y())
        if right is not None and not (math.isfinite(right[0]) and math.isfinite(right[1])):
            return False
        self._usable_sample = sample
        self._usable_left = left
        self._usable_right = right
        return True

    def in_window(self, window: str, frame: int, eye: str = "both") -> bool:
        """**On the trial loop's path**, every frame for every window a guard asks about, so it
        builds nothing (XC-413): the window's center and radius were resolved between trials
        (`_judged`), each eye's gaze is the frame's one conversion (`_look`), and the two eyes'
        mean is taken without a list or a generator."""
        judged = self._judged.get(window)
        if judged is None:
            return False
        if isinstance(judged, Window):
            # These values could not place it when this world was built: resolved here, raising.
            judged = _placed(judged, self._values)
        cx, cy, radius = judged
        if frame != self._looked or self.tracker.latest is not self._sample:
            self._look(frame)
        if eye == "both":
            # A conjugate criterion is the mean of the two eyes, not either one: an
            # `eye="both"` window asks where the animal is looking, and under dichoptic
            # presentation one eye alone answers a different question. A window that
            # wants one eye says so, which is what `Window.eye` exists for.
            left = self._left
            right = self._right
            if left is None or right is None:
                return False
            # Halved, then summed, as `gaze_cyclopean` takes it (the review of d932cb3, its I2).
            x = left[0] * 0.5 + right[0] * 0.5
            y = left[1] * 0.5 + right[1] * 0.5
        else:
            # Any other name is no eye, and `gaze` refuses it as it always has.
            position = (self._left if eye == "left" else self._right if eye == "right"
                        else self.gaze(eye, frame))
            if position is None:
                return False
            x = position[0]
            y = position[1]
        # **True visual angle, at the window's own location** (the PI, 2026-10-19): the angle
        # at the eye between where it points and the window's center. Per axis,
        # `hypot(x - cx, y - cy)` made a 2° window at (20°, 0°) 1.879° tall. Gaze and window
        # are both cyclopean degrees mapped by `D · tan` per axis, the map fitted to targets
        # placed as every stimulus is (EYE-10): in direct view, directions from straight ahead.
        # Through the stereoscope each eye sees in its own viewport's degrees, the vergence
        # offset away per axis, which moves this angle by up to 0.72% of it over the ±12° mask
        # (computed, for gaze within 8° of the window's center); which frame an eye's map is in
        # is the stereoscope calibration task's to settle (XC-005).
        return separation_deg(x, y, cx, cy) <= radius

    def began(self, state: str, frame: int) -> None:
        """State `state` began, `frame` its first (`run.World.began`): from now on
        a saccade counts for a `SaccadeOnset` only if its onset is on `frame` or after (XC-410),
        and for a `SaccadeTo` if it began here **or was in flight as the state began**, for its
        landing alone (the PI, 2026-11-06, asked whether a state that itself waits for the go
        saccade should count one begun just before the go cue, as a state relayed by the eye leaving
        the fixation window already did: "Count it both ways": "The same eye movement scores the
        same whichever way the task is written: a saccade already under way at the go cue counts
        where it lands. The rule that a saccade counts only in the state it began in gets one
        exception: a saccade in flight when the go cue's state begins."). Which state is the go
        cue's this world cannot know, so it is any state, **whatever edge entered it** -- a
        saccade's onset or a timer from one, an `Exited`, an `Entered`, a timer from the state's
        entry, any other -- and it is not told which.

        **For a `SaccadeTo` that is the whole rule** (review 9 of the saccade rules, its I1,
        2026-11-07): a stop always follows its onset, so a saccade begun here comes to rest on
        `frame` or after too, and a `SaccadeTo` counts any saccade the detector puts at rest on
        `frame` or after, wherever its onset fell. XC-410's "it must start in the state" now
        governs only a `SaccadeOnset`. XC-410's own case, a saccade begun the frame before a plain
        timer's state and landing in it, scored no response until that answer and is scored where
        it lands since (`tests/test_gaze.py`, the straddle test's `[SaccadeTo]` case). The PI
        answered on 2026-11-07, asked in the UI whether a state that waits for a saccade to the
        target counts any saccade whose eye stops there, wherever its onset fell: "Yes, count where
        it lands (Recommended)".

        **In flight as it began**, by this world's own record of the saccade, as the exit carry read
        it (2026-11-06): its onset (`_onset`, the detector's `Saccade.start`) on the transition's
        frame, `frame - 1`, or before, so before `frame`, and its eye not at rest until `frame` or
        after (`_stopped`, `Saccade.stop`, the first sample at rest): the detector's run holds the
        transition's frame. Judged when it lands (`happened`), never by the detector's state at the
        transition, which may hold it as an open run not yet confirmed, as one confirmed and not yet
        landed, or, its velocities trailing the eye by `HALF_WINDOW` samples, not as a run at all,
        so nothing is chosen here. **One saccade**, runs not overlapping. **Only if its eye stops in
        this state**: one the detector puts at rest on the transition's frame or before landed in
        the state before and counts for nothing here (the review of XC-410, its I1). **A further
        transition while it is still in flight carries it on**, by the same rule, and one after its
        eye stopped ends it. **It never satisfies a `SaccadeOnset` here** (`happened`): its onset
        was before this state.

        **One rule for what were three carries.** The onset carry (the PI, 2026-10-30: "Only the
        saccade whose start ended the previous state carries over"), the timer carry ("Yes, carry
        it too") and the exit carry (2026-11-04, "Carry it over"; widened 2026-11-06, "Yes, count
        it") each took the saccade in flight as its edge began the next state; now every edge does.
        Until that evening a timer from the state's entry carried nothing, even while a saccade a
        clock was timing was in flight, nor did `Entered`, nor an onset's or a timer's edge for a
        saccade no `SaccadeOnset` had seen, nor, but for another `Exited`, an edge taken after an
        exit carried a saccade on."""
        self._state = state
        self._began = frame

    def happened(self, guard: Guard, state: str, frame: int) -> bool:
        """`SaccadeOnset` on the frame the last saccade is confirmed, if it began in `state`, and
        `SaccadeTo` on the frame it lands, if it landed in the window and the detector puts its eye
        at rest on the state's first frame or after, wherever its onset fell (`began`).
        **`SaccadeOnset` observes the onset and takes nothing** (the controller's ruling on the
        review's M1): every one of the state's asking on that frame sees it, a clock's and an
        edge's alike, and it is seen once, on that frame. **`SaccadeTo` takes the landing**, so
        one saccade is one response, that of a saccade begun in the state or in flight as it began
        (the PI, 2026-11-06, "Count it both ways"), whatever edge began it, its eye at rest on the
        state's first frame or after (the review's I1): for a `SaccadeTo` the stop alone decides
        (review 9 of the saccade rules, its I1). A saccade in flight as the state began is never a
        `SaccadeOnset`'s: its onset was before this state, whether the detector confirmed it before
        or here.

        **On the trial loop's path**, every frame a state asks for a saccade, so nothing is built
        here: an alias's objects are `_members`' own tuple, and a window is judged as it is."""
        if isinstance(guard, SaccadeOnset):
            return self._began_in(state) and self._confirmed_on == frame
        if isinstance(guard, SaccadeTo):
            # Judged on the frame it landed, against the windows drawn then, and never after: a
            # saccade that landed on empty space is not one to an object drawn there later, or to a
            # window gaze drifts into (the PI, 2026-10-30). Begun in this state, or in flight as it
            # began, its eye at rest on its first frame or after (`began`). **The stop alone
            # decides**: a stop follows its onset, so `_began_in(state)` true implies the stop test,
            # and it stays first for its refusal of a state this world was not told of (`_untold`;
            # review 9 of the saccade rules, its I1, 2026-11-07).
            if (not (self._began_in(state) or self._stopped >= self._began)
                    or self._taken or self._landed_on != frame):
                return False
            members = self._members.get(guard.window)
            if members is None:
                declared = self._windows.get(guard.window)
                landed = declared is not None and self.in_window(guard.window, frame,
                                                                 declared.eye)
            else:
                landed = self._landed(members, frame)
            if not landed:
                return False
            self._taken = True
            return True
        return False

    def _began_in(self, state: str) -> bool:
        """Whether the last saccade began in `state`: on its first frame or after (XC-410). **A
        state this world was not told began is refused** (`_untold`): without its first frame,
        every saccade of the trial would count."""
        if state != self._state:
            _untold(state, self._state)
        return self._onset >= self._began

    def _landed(self, names: "tuple[str, ...]", frame: int) -> bool:
        """Whether gaze is inside any of the windows `names`, the objects an array's alias names
        (`_members`), each judged for its own eye. Walked by index, so not even an iterator is
        made on the frames it runs (XC-414)."""
        index = 0
        while index < len(names):
            name = names[index]
            index += 1
            declared = self._windows.get(name)
            if declared is not None and self.in_window(name, frame, declared.eye):
                return True
        return False

    def signal(self, frame: int) -> str:
        """`"ok"` or `"lost"`. **Never `"blink"`**, because telling a blink from a
        dropped camera needs the pupil-area collapse `eye.py` records as UNVERIFIED
        -- what OpenIris emits when tracking fails is not documented in the material
        read, and a fabricated rule here decides whether an animal is looking. Until
        the V3 bench measurement, a blink reaches the loop as tracker loss, which
        over-reports equipment failure rather than under-reporting it."""
        return self.tracker.state(self.when(frame))

    def display(self, visible: MappingType[str, Stimulus], frame: int) -> None:
        """Also where gaze is polled, which is not an abuse of the name.

        `World.display` is the loop's only per-frame call that lands **before** the
        frame's guards are evaluated -- `signal` and `in_window` both come after --
        so it is the one place a sample can arrive and be current for the frame that
        reads it. Polling anywhere else means every window test scores the previous
        frame's gaze, and at 8 ms a frame that is a whole frame of lag introduced by
        the harness rather than by the tracker. The first version of this class had
        the poll in `in_window`, and the trial died of staleness at frame 7 because
        `signal` ran first and saw a sample nothing had refreshed.
        """
        # The windows of what this frame draws (XC-402): an array a `Show` or an `Update` changed
        # since the last frame switches to the placement it is now drawn in, built between trials.
        # One identity test per array on every other frame, and a switch overwrites existing keys.
        # Walked by index, so a frame makes no iterator (XC-414).
        arrays = self._arrays
        index = 0
        while index < len(arrays):
            of, options = arrays[index]
            index += 1
            stimulus = visible.get(of)
            if stimulus is None or stimulus is self._drawn[of]:
                continue
            self._drawn[of] = stimulus
            option = 0
            while option < len(options):
                placement, judged = options[option]
                option += 1
                if placement.draws(stimulus):
                    self._windows.update(placement.windows)
                    self._judged.update(judged)
                    self._members.update(placement.members)
                    break
        if self.source is not None:
            # **An unusable reading is a lost sample** (`_usable`): dropped before the tracker
            # accepts it, its last good sample held under staleness, as for a missing datagram.
            sample = self.source.poll(self.when(frame))
            if sample is not None and not self._usable(sample):
                sample = None
            self.tracker.accept(sample)
        # Feed the detector from the same sample the window tests will read, so a
        # saccade and the gaze that guards see cannot come from different frames.
        now = self.when(frame)
        fed = self._fed
        self._fed = fed + 1
        confirmed = self.detector.accept(now, self.gaze_cyclopean(frame))
        if confirmed is not None:
            # Its onset as a frame (XC-410): this frame's sample is the detector's `fed`th, and
            # one is fed a frame, so its first, `start`, was fed `fed - start` frames ago.
            self._onset = frame - (fed - confirmed.start)
            self._confirmed_on = frame
            self._taken = False
            # **Confirmed while its run is open, always**: since version 3 of the detector
            # (2026-11-04) a run is confirmed on the velocity outside the threshold that gives it
            # `min_duration_samples` measured ones, never on the sample that ends it, as version 2
            # could (`tests/test_saccade.py` sweeps it). So it is in flight, and lands as its run
            # closes (below). **A detector that confirms one on a closed run is refused** (the
            # controller's ruling of 2026-11-06, fail closed): taken as in flight, it would land a
            # frame late, its stop two frames off. Until version 4 a branch took such a saccade as
            # landed on that frame (the review of XC-410's I2), which no detector reached.
            if not self.detector.in_flight:
                _closed(confirmed)
            self._in_flight = True
            self._landed_on = None
        elif self._in_flight and not self.detector.in_flight:
            # The run closed: the eye has landed, so `SaccadeTo` can now ask where, on this frame.
            # **Where the eye stopped** (the review's I1): the run's end as the detector closed it,
            # `saccade.detect`'s `Saccade.stop` (`Detector.last_stop`), fed `fed - last_stop`
            # frames ago: the closing velocity's own sample, `HALF_WINDOW` back, the first known at
            # rest; or, the run carried through a short loss to it, the sample after, the closing
            # one the run's last (version 8); or, a long loss ending the run, one past its last
            # measured velocity (version 7). Version 7 stopped a run whose landing a short loss took
            # there too, while the eye was still moving, and both carries refused the saccade
            # that landed in the next state; until version 7 a long loss stopped it past the loss
            # (pinned against `detect` by `tests/test_gaze.py` and `tests/test_saccade.py`).
            self._in_flight = False
            self._landed_on = frame
            self._stopped = frame - (fed - self.detector.last_stop)


@dataclass
class Calibrating:
    """A session's calibration block, from replayed or live gaze to a written map.

    **The driver, not a composition.** Every piece existed before this -- the
    scheduler walks the constellation, `tasks/calibration.py` scores each target,
    `Collector` averages, `fit_eye` fits, `MappingLog.install` versions, and
    `GazeCalibration.to_yaml` writes the bytes `wl-preproc` reads -- and none of them
    ran inside a session. A test composed them by hand and its docstring said it was
    "the shape the driver has to take", which is a different claim from a session
    producing the file.

    Plugs into `taskd.Session` through its two hooks: `world` makes the trial's
    world, `observe` decides what that trial contributed. Neither knows about
    calibration, which is the point -- a session runs blocks, and what a particular
    block is *for* is not the session's business.
    """

    #: The map the block itself is scored through. Version 0 maps nothing, so a
    #: session's first calibration needs one from somewhere: yesterday's file, or a
    #: rough one from an operator. The window is sized to admit gaze that is wrong by
    #: the amount calibration is about to correct, which is what makes that workable.
    bootstrap: Mapping
    log: MappingLog
    frame_period: float
    #: `(target) -> [(offset, payload)]`. A replay for a test or a bench run; on a
    #: rig this is `None` and `source` is the live socket.
    replay: object = None
    source: object = None
    collector: Collector = field(default_factory=Collector)
    #: How many trials contributed a fixation. Not the same as how many ran.
    collected: int = 0
    _world: "Tracked | None" = field(default=None, repr=False)
    _seen: list = field(default_factory=list, repr=False)

    def world(self, trial, values: dict, index: int) -> "Tracked":
        self._seen = []
        source = self.source if self.replay is None else Replay(
            payloads=list(self.replay((values["target_x"], values["target_y"])))
        )
        self._world = Tracked(
            Tracker(),
            self.bootstrap,
            trial,
            self.frame_period,
            values,
            source=_Watched(source, self._seen),
        )
        return self._world

    def observe(self, condition, values: dict, result) -> None:
        """Collect what the trial actually held, if the task paid for it.

        **The hold, not the trial.** A calibration trial begins with the animal
        looking somewhere else -- that is what `Entered("cal")` is waiting for -- so
        averaging the whole trial's samples would drag every target toward wherever
        the animal happened to be looking beforehand, by an amount that depends on
        how long it took to acquire. The hold's duration is the task's own
        `cal_hold`, and the hold ended on the frame the trial did.
        """
        if result.outcome is not Outcome.CORRECT:
            return
        end = result.frames * self.frame_period
        began = end - _resolve(values["cal_hold"], values)
        held = [sample for at, sample in self._seen if at >= began]
        target = (values["target_x"], values["target_y"])
        if self.collector.accept(target, held):
            self.collected += 1

    def install(self, at: float, tested_eccentricity_deg: float):
        """Fit both eyes and install the result as the next mapping version."""
        left, right, findings = self.collector.fit(
            tested_eccentricity_deg=tested_eccentricity_deg
        )
        if [f for f in findings if f.blocking]:
            return None, findings
        mapping = self.log.install(
            at=at,
            targets=self.log.current.targets,
            left=left,
            right=right,
            why="calibration block",
        )
        return mapping, findings

    def write(self, directory) -> "Path":
        """The file, beside the record it came from.

        Named `eye_calibration.yaml` rather than anything session-specific: the
        session directory already carries the identity, and a name that repeats it is
        a second place for it to disagree.
        """
        path = Path(directory) / "eye_calibration.yaml"
        path.write_text(
            self.log.current.as_calibration().to_yaml(), encoding="utf-8"
        )
        return path


@dataclass
class _Watched:
    """A gaze source that keeps what it handed out.

    So `observe` can average the samples the *trial* saw rather than re-deriving
    them: a second copy of the replay would be a second animal, differing from the
    first wherever the poll schedule did.
    """

    source: object
    seen: list

    def poll(self, at: float):
        sample = self.source.poll(at) if self.source is not None else None
        if sample is not None:
            self.seen.append((at, sample))
        return sample
