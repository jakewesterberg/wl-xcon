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

**A saccade is consumed by whichever guard takes it.** Without that, one saccade
satisfies `SaccadeTo` on every subsequent frame gaze stays in the window, which is
indistinguishable from the animal saccading there repeatedly and turns one response
into a stream of them.

**The detector is per trial** (S5 §5), so a world is reset per trial; a threshold
carried across would let a quiet trial set a noisy one's sensitivity.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping as MappingType

from wl_xcon.calibration import Collector, Mapping, MappingLog
from wl_xcon.eye import Replay, Tracker
from wl_xcon.geometry import separation_deg
from wl_xcon.saccade import Detector, Saccade
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
        #: log its parameters and version alongside the mapping version.
        self.detector = detector if detector is not None else Detector()
        #: The most recent confirmed saccade not yet claimed by a guard, and whether
        #: it has landed. A saccade in flight cannot have landed in anything.
        self._pending: Saccade | None = None
        self._in_flight = False
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
        """
        if self.tracker.state(self.when(frame)) != "ok":
            return None
        sample = self.tracker.latest
        if sample is None:
            return None
        reading = getattr(sample, which)
        return self.mapping.degrees_of(which, reading.dpi_x(), reading.dpi_y())

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
        return ((left[0] + right[0]) / 2, (left[1] + right[1]) / 2)

    def _look(self, frame: int) -> None:
        """Each eye's gaze at `frame`, kept for the rest of the frame (`_looked`)."""
        self._left = self.gaze("left", frame)
        self._right = self.gaze("right", frame)
        self._looked = frame
        self._sample = self.tracker.latest

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
            x = (left[0] + right[0]) / 2
            y = (left[1] + right[1]) / 2
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

    def happened(self, guard: Guard, state: str, frame: int) -> bool:
        if isinstance(guard, SaccadeOnset):
            found = self._pending is not None and self._in_flight
            if found:
                self._pending = None
            return found
        if isinstance(guard, SaccadeTo):
            if self._pending is None or self._in_flight:
                return False
            # On every frame an unclaimed saccade is pending (XC-410), so nothing is built here: an
            # alias's objects are `_members`' own tuple, and a window is judged as it is.
            members = self._members.get(guard.window)
            if members is None:
                declared = self._windows.get(guard.window)
                landed = declared is not None and self.in_window(guard.window, frame,
                                                                 declared.eye)
            else:
                landed = self._landed(members, frame)
            if not landed:
                return False
            self._pending = None
            return True
        return False

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
            self.tracker.accept(self.source.poll(self.when(frame)))
        # Feed the detector from the same sample the window tests will read, so a
        # saccade and the gaze that guards see cannot come from different frames.
        now = self.when(frame)
        confirmed = self.detector.accept(now, self.gaze_cyclopean(frame))
        if confirmed is not None:
            self._pending = confirmed
            self._in_flight = True
        elif self._in_flight and not self.detector.in_flight:
            # The run closed: the eye has landed, so `SaccadeTo` can now ask where.
            self._in_flight = False


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
