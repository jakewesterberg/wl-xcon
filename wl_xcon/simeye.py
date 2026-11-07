"""The simulated eye: a gaze source `gaze.Tracked` reads, looking at what the display draws (XC-456).

**Why it exists.** A simulated session's animal was `simulate.Subject`, which fires a guard by a
hazard rate per guard type and has no gaze: its saccade "to the target" was a weighted coin,
wherever the task drew the target, so the saccade rules the rig scores by (EYE-19) were never asked,
and a census could not show what they do to a task's outcomes. The XC-410 review's probe L: a state
entered as gaze leaves the fixation window, asking for a saccade to the target, scored where the eye
lands on the rig, 24 of 24, and 115 CORRECT / 85 WRONG_TARGET by the simulator's rates. This eye
makes samples, and `gaze.Tracked` -- the rig's gaze world, its map, its tracker's staleness, its
saccade detector and its rules for which saccade counts where -- scores them, every guard of it.

**It reacts to the display, never to a precomputed trace.** Each frame it is shown what the display
draws (`Seeing.display`, before the frame's sample is polled) and told each state's first frame
(`Seeing.began`), and decides from those as a trained animal would:

- **It fixates the fixation point when it is shown**: a state that asks for gaze in a window
  (`Entered`, `Hold`) whose stimulus is drawn, and the eye not in it, gets a saccade to it after a
  latency.
- **It answers at the go**: a state that asks for the answer -- a saccade to a target
  (`SaccadeTo` on a window whose edge does not end the trial wrong), any saccade
  (`SaccadeOnset`), or the eye leaving a window it is not asked to stay in (`Exited` to another
  state, the pop-out search's "next saccade from fixation", its design §3.1) -- gets one saccade,
  after a latency from the state's first frame or from when something to answer is first drawn.
  It lands on the target with probability `accuracy`; otherwise on a distractor if one is drawn,
  else on empty space. Where each is, is where the display draws it on the frame the saccade
  starts (an array's objects wherever its last `Show` or `Update` put them, `task.placements`).
- **Early, before the go, at its early rate**: on a trial drawn early (`early_rate`), the eye
  holding a fixation window it is asked to stay in leaves it once, after a latency from when the
  hold began, as an answer would go; so a hold shorter than the latency answers the go instead.
- **Not at all, at `1 - engagement`**: a trial drawn disengaged looks at empty space and nothing
  else, staying there if it already does, so a task's no-fixation path is reachable, as the hazard
  animal's engagement made it.

It never corrects an answer, never leaves a target it landed on, and makes one answer a trial. It
begins a trial where the last one left it, and its first away from every window. **It
knows the task's rules, not its outcomes**: which state asks for what is read from the trial between
trials (`_read`), as an animal trained on the task knows them; whether a saccade counted, and where,
is `gaze.Tracked`'s alone. **It cannot look at what is not drawn**: a window whose stimulus is off
the display is not looked at, but for one declared `REMEMBERED`.

**Its saccades are ones the rig's detector finds** (`saccade.Detector`, version 11): a
minimum-jerk position profile (a bell-shaped velocity), lasting `DURATION_S` plus
`DURATION_PER_DEG_S` a degree of its true-angle size, straight in per-axis degrees, every sample
carrying independent Gaussian noise of `NOISE_DEG` per axis, without which the detector's
threshold, estimated from the trace's own velocities, is zero and it reports nothing. One sample a
frame, as `gaze.Tracked` polls a tracker: at the 240 Hz a simulated session runs at, the detector
confirms its saccades of 1° to 12°, once each, from where it took off, once its warmup is past
(`tests/test_simeye.py`). At a slower frame rate the detector's minimum of six samples can outlast
a short saccade, as it would on a rig sampled that slowly. **These numbers are
engineering defaults, with no published source sought**: the noise is the repository's own test
traces' (`tests/test_gaze.py`), the profile its saccade-rules probes' (`docs/research/
2026-11-06-saccade-rules-probes/probe_common.py`), and the latency a log-normal of spread
`RT_SPREAD` about `rt_median_s`. It is a stand-in an engine is tested against, not a model of a
macaque, and no timing claim rests on it.

**Its map is the identity** (`MAPPING`): its Purkinje vector, P1 less a P4 at the origin, is its
gaze in degrees, so its samples pass through `gaze.Tracked`'s map, staleness and usability tests as
a tracker's do, without a calibration to invert.

**Hot path.** `Seeing.display` and `Seeing.began` run on the trial loop's path, and so do the eye's
`see`, `began` and `poll`: everything they read was built between trials (`new_trial`), a decision
or a saccade's launch builds nothing, and a frame builds only the eye's sample (its reading's image
position, the pair `(x, y)`; `tests/test_simeye.py` measures the whole frame).
"""

from __future__ import annotations

import math
import random

from wl_xcon.calibration import EyeMap, Mapping, Model
from wl_xcon.eye import EyeReading, Sample, Tracker
from wl_xcon.geometry import separation_deg
from wl_xcon.gaze import Tracked
from wl_xcon.task import (
    RIGHT,
    Entered,
    Exited,
    Hold,
    Outcome,
    P,
    Remembered,
    SaccadeOnset,
    SaccadeTo,
    Trial,
    Window,
    expand_windows,
    placements,
    position_of,
)

#: One eye's map, the identity: degrees are the raw vector, `[1, dx, dy]` with coefficients
#: `(0, 1, 0)` across and `(0, 0, 1)` up.
_IDENTITY = EyeMap(model=Model.AFFINE, x=(0.0, 1.0, 0.0), y=(0.0, 0.0, 1.0), conditioning=1.0,
                   rms_residual_deg=0.0, n_points=0)
#: **The map a simulated eye's samples are read through** (the module docstring): its version is
#: the one every trial it scores cites.
MAPPING = Mapping(version=1, targets=(), left=_IDENTITY, right=_IDENTITY,
                  why="the simulated eye's: its raw vector is its gaze in degrees")

#: Each sample's Gaussian noise, in degrees, per axis: the repository's test traces' (engineering
#: default, the module docstring).
NOISE_DEG = 0.02
#: A saccade's duration, `DURATION_S + DURATION_PER_DEG_S * size`, in seconds: 8° in 40 ms, 1° in
#: 22.5 ms (engineering default).
DURATION_S = 0.020
DURATION_PER_DEG_S = 0.0025
#: The spread of the log-normal latency about its median: the standard deviation of its logarithm
#: (engineering default; 90% of latencies within 0.66 and 1.51 times the median).
RT_SPREAD = 0.25
#: How far past a window's edge empty space must lie, in degrees, and how many directions are drawn
#: before it goes beyond every window instead (`Eye._empty`).
MARGIN_DEG = 0.5
TRIES = 32

#: What the eye's reading carries that no gaze reads: its pupil, and P4 at the origin.
_PUPIL = (0.0, 0.0)
_PUPIL_AREA = 1.0
_P4 = (0.0, 0.0)
#: The display before a trial's first frame shows it.
_NOTHING: dict = {}

#: What a planned saccade is for.
_NONE = 0
_FIXATE = 1
_ANSWER = 2
_EARLY = 3
_AWAY = 4


class Eye:
    """**A simulated eye, the sample source `gaze.Tracked` reads** (the module docstring): its
    behavior in an animal's terms -- how often it answers right, its median latency, how often it
    goes early, how often it engages -- and a seed, as one session's eye. One for a session, not a
    trial: its generator carries the session's randomness, and it looks next trial from where it
    looked last."""

    def __init__(self, accuracy: float, rt_median_s: float, early_rate: float, seed: int,
                 engagement: float = 1.0) -> None:
        for name, value in (("accuracy", accuracy), ("early_rate", early_rate),
                            ("engagement", engagement)):
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"a simulated eye's {name} is a probability, from 0 to 1, "
                                 f"not {value!r}")
        if not (rt_median_s > 0.0 and math.isfinite(rt_median_s)):
            raise ValueError(f"a simulated eye's median latency is a number of seconds above 0, "
                             f"not {rt_median_s!r}")
        self.accuracy = accuracy
        self.rt_median_s = rt_median_s
        self.early_rate = early_rate
        self.engagement = engagement
        self.seed = seed
        #: **Two generators from the one seed**: what it decides (engaged, early, each latency,
        #: where an answer goes) and its samples' noise, so how many frames a trial ran never moves
        #: what it decides next. A string seeds `random` the same way in every process.
        self._rng = random.Random(seed)
        self._noise = random.Random(f"{seed}: the simulated eye's noise")
        self._log_rt = math.log(rt_median_s)
        #: Where it looks, in degrees, kept across trials: a trial begins where the last left it.
        self._x = 0.0
        self._y = 0.0
        #: Samples given, numbering its readings as a tracker's frames are numbered.
        self._samples = 0
        self._frame_period = 1.0 / 240.0
        self._flying = False
        self.new_trial(None, {}, self._frame_period)

    # --- Between trials ---------------------------------------------------------------------

    def world(self, trial: Trial, values: "dict | None", frame_period: float) -> "Seeing":
        """**A trial's world**: `gaze.Tracked`, its gaze this eye's (`Seeing`), the eye readied for
        the trial first (`new_trial`). The shape `taskd.Session.world` takes, given the frame
        period, as `gaze.Calibrating.world` gives one (`simulate.agent`)."""
        values = values or {}
        self.new_trial(trial, values, frame_period)
        return Seeing(self, trial, frame_period, values)

    def new_trial(self, trial: "Trial | None", values: dict, frame_period: float) -> None:
        """Ready for a trial: what each state asks (`_read`), where each window is in every way
        the trial can draw it, and the trial's two draws, engaged and early. Between trials, so
        what it builds is free (ADR-0006). A saccade the last trial's end cut off has landed by
        now, the trials a gap apart."""
        if self._flying:
            self._x = self._to_x
            self._y = self._to_y
        self._frame_period = frame_period
        self._visible = _NOTHING
        self._flying = False
        self._plan_kind = _NONE
        self._plan_at = 0
        self._plan_name = ""
        self._answered = False
        self._broke = False
        self._away = False
        self._seek: tuple = ()
        self._fixating = False
        self._answers = False
        self._aims: tuple = ()
        self._wx = self._wy = self._wr = 0.0
        self._from_x = self._from_y = self._to_x = self._to_y = 0.0
        self._launched = 0
        self._duration = DURATION_S
        self._engaged = True
        self._early = False
        if trial is None:
            self._asks: dict = {}
            self._targets: tuple = ()
            self._distractors: tuple = ()
            self._plain: dict = {}
            self._family: dict = {}
            self._arrays: dict = {}
            self._all: tuple = ()
            self._reach = self._beyond = 0.0
            return
        self._read(trial, values)
        self._engaged = self._rng.random() < self.engagement
        self._early = self._rng.random() < self.early_rate
        if self._samples == 0:
            # Its first trial: the animal has not yet found the fixation point.
            self._empty()
            self._x = self._wx
            self._y = self._wy

    def _read(self, trial: Trial, values: dict) -> None:
        """**The task's rules, as the eye plays them** (the module docstring), and its windows."""
        targets: list = []
        wrong: list = []
        for state in trial.states:
            for edge in state.go:
                guard = edge.guard
                if isinstance(guard, SaccadeTo):
                    if isinstance(edge.to, Outcome) and edge.to not in RIGHT:
                        if guard.window not in wrong:
                            wrong.append(guard.window)
                    elif guard.window not in targets:
                        targets.append(guard.window)
        self._targets = tuple(targets)
        # An answer that is not the target lands on what an error saccade is scored on, and on
        # an array's other objects when it aims at the array's target.
        distractors = [name for name in wrong if name not in targets]
        for name in targets:
            if name.endswith(".target"):
                other = name[: -len(".target")] + ".distractor"
                if other not in distractors:
                    distractors.append(other)
        self._distractors = tuple(distractors)
        asks: dict = {}
        for state in trial.states:
            seek: list = []
            held: list = []
            left: list = []
            aims: list = []
            answers = False
            for edge in state.go:
                guard = edge.guard
                if isinstance(guard, (Entered, Hold)) and guard.window not in seek:
                    seek.append(guard.window)
                if isinstance(guard, Hold):
                    held.append(guard.window)
                elif isinstance(guard, Exited):
                    if isinstance(edge.to, Outcome) and edge.to not in RIGHT:
                        held.append(guard.window)
                    else:
                        left.append(guard.window)
                elif isinstance(guard, SaccadeTo):
                    answers = True
                    if guard.window in targets and guard.window not in aims:
                        aims.append(guard.window)
                elif isinstance(guard, SaccadeOnset):
                    answers = True
            # Leaving a window moves the trial on, and the state does not also ask for gaze there:
            # the eye leaving it is the answer (a relay; a hold that restarts asks for it).
            if any(name not in seek for name in left):
                answers = True
            if answers and not aims:
                aims = list(targets)
            asks[state.name] = (tuple(seek), any(name not in targets for name in held), answers,
                                tuple(aims))
        self._asks = asks
        # Where each window is: a plain one once; an array's objects in every placement the trial
        # can draw it in, each placement's centers built now (as `gaze.Tracked` builds its own).
        self._family = {}
        self._arrays = {}
        every: list = []
        for of, options in placements(trial, values).items():
            built = []
            for placement in options:
                centers = {name: _center(window, values)
                           for name, window in placement.windows.items()}
                built.append((placement, centers))
                every.extend(center for center in centers.values() if center is not None)
                for name in placement.windows:
                    self._family[name] = of
                for alias in placement.members:
                    self._family[alias] = of
            self._arrays[of] = tuple(built)
        declared, _ = expand_windows(trial, values)
        self._plain = {}
        for window in declared:
            if window.name in self._family:
                continue
            center = _center(window, values)
            if center is not None:
                self._plain[window.name] = (center[0], center[1], center[2], window.on)
                every.append(center)
        self._all = tuple(every)
        # Empty space is drawn at the targets' eccentricity, away from every window by the margin,
        # and failing that, beyond every window (`_empty`).
        reach = [separation_deg(0.0, 0.0, x, y) for x, y, _ in self._centers_of(self._targets)]
        self._beyond = max((separation_deg(0.0, 0.0, x, y) + r for x, y, r in every),
                           default=0.0) + 2.0 * MARGIN_DEG
        self._reach = max(reach) if reach else self._beyond

    def _centers_of(self, names: tuple) -> list:
        """Every center a window of `names` has in any placement, between trials."""
        found = []
        for name in names:
            plain = self._plain.get(name)
            if plain is not None:
                found.append(plain[:3])
                continue
            for placement, centers in self._arrays.get(self._family.get(name), ()):
                for concrete in placement.members.get(name, (name,)):
                    if centers.get(concrete) is not None:
                        found.append(centers[concrete])
        return found

    # --- Each frame ---------------------------------------------------------------------------

    def began(self, state: str, frame: int) -> None:
        """State `state` began on `frame` (`run.World.began`): what it asks, read between trials.
        A saccade not yet launched is dropped and decided again in this state; one in flight goes
        on."""
        asks = self._asks[state]
        self._seek = asks[0]
        self._fixating = asks[1]
        self._answers = asks[2]
        self._aims = asks[3]
        self._plan_kind = _NONE

    def see(self, visible, frame: int) -> None:
        """What the display draws on `frame`, before its sample is polled (`Seeing.display`): a
        saccade in flight moves on or lands, one planned starts when its latency is up, and the
        eye otherwise decides what to do next (`_decide`)."""
        self._visible = visible
        if self._flying:
            self._fly(frame)
            if self._flying:
                return
        if self._plan_kind != _NONE:
            if frame >= self._plan_at:
                self._launch(frame)
            return
        self._decide(frame)

    def poll(self, at: float) -> Sample:
        """**The sample** `gaze.Tracked` reads: where the eye is, with its noise, in both eyes (one
        reading, the two eyes conjugate). Its image position is the one thing a frame builds."""
        noise = self._noise
        self._samples += 1
        reading = EyeReading(self._samples, _PUPIL, _PUPIL_AREA,
                             (self._x + noise.gauss(0.0, NOISE_DEG),
                              self._y + noise.gauss(0.0, NOISE_DEG)), _P4)
        return Sample(at, reading, reading)

    def _decide(self, frame: int) -> None:
        """What the eye does next, from what the state asks and the display draws (the module
        docstring): a saccade planned, or nothing."""
        if not self._engaged:
            if not self._away:
                # Looking at empty space already, it stays; else it looks there, once.
                self._wx = self._x
                self._wy = self._y
                if self._clear():
                    self._away = True
                else:
                    self._plan(_AWAY, frame)
            return
        if self._answers and not self._answered:
            if len(self._aims) == 0 or self._aimed(self._aims):
                self._plan(_ANSWER, frame)
            return
        seek = self._seek
        index = 0
        while index < len(seek):
            name = seek[index]
            index += 1
            if not self._where(name):
                continue
            if separation_deg(self._x, self._y, self._wx, self._wy) > self._wr:
                self._plan_name = name
                self._plan(_FIXATE, frame)
            elif self._early and not self._broke and self._fixating:
                self._plan(_EARLY, frame)
            return

    def _plan(self, kind: int, frame: int) -> None:
        """A saccade of `kind`, to start after a latency drawn now."""
        latency = self._rng.lognormvariate(self._log_rt, RT_SPREAD)
        self._plan_kind = kind
        self._plan_at = frame + int(latency / self._frame_period + 0.5)

    def _launch(self, frame: int) -> None:
        """The planned saccade starts, to where its kind sends it, judged on the display now."""
        kind = self._plan_kind
        self._plan_kind = _NONE
        if kind == _FIXATE:
            if self._where(self._plan_name):
                self._go(frame, self._wx, self._wy)
            return
        if kind == _AWAY:
            self._away = True
            self._empty()
            self._go(frame, self._wx, self._wy)
            return
        if kind == _ANSWER:
            self._answered = True
            aims = self._aims
        else:
            self._broke = True
            aims = self._targets
        if self._rng.random() < self.accuracy and self._aimed(aims):
            self._go(frame, self._wx, self._wy)
            return
        count = self._distractor(-1)
        if count > 0:
            pick = int(self._rng.random() * count)
            self._distractor(pick if pick < count else count - 1)
        else:
            self._empty()
        self._go(frame, self._wx, self._wy)

    def _go(self, frame: int, x: float, y: float) -> None:
        """A saccade from where the eye is to `(x, y)`, starting on `frame`."""
        self._from_x = self._x
        self._from_y = self._y
        self._to_x = x
        self._to_y = y
        self._duration = DURATION_S + DURATION_PER_DEG_S * separation_deg(self._x, self._y, x, y)
        self._launched = frame
        self._flying = True

    def _fly(self, frame: int) -> None:
        """Where the saccade has the eye on `frame`: a minimum-jerk profile, `10τ³ - 15τ⁴ + 6τ⁵` of
        the way, `τ` the share of its duration gone; landed at its end."""
        tau = (frame - self._launched) * self._frame_period / self._duration
        if tau >= 1.0:
            self._x = self._to_x
            self._y = self._to_y
            self._flying = False
            return
        share = tau * tau * tau * (10.0 - 15.0 * tau + 6.0 * tau * tau)
        self._x = self._from_x + (self._to_x - self._from_x) * share
        self._y = self._from_y + (self._to_y - self._from_y) * share

    # --- Where things are drawn, on the frame asked ---------------------------------------------

    def _aimed(self, aims: tuple) -> bool:
        """The first of `aims` drawn now, into `_wx`, `_wy`, `_wr`; whether there is one."""
        index = 0
        while index < len(aims):
            name = aims[index]
            index += 1
            if self._where(name):
                return True
        return False

    def _where(self, name: str) -> bool:
        """**Whether window `name` has something drawn to look at now**, its center and radius into
        `_wx`, `_wy` and `_wr` if so: a plain window's stimulus on the display (or the window
        `REMEMBERED`, or scoring none), an array's object where the array is drawn now. An alias,
        `<of>.target`, is its first object."""
        plain = self._plain.get(name)
        if plain is not None:
            on = plain[3]
            if on is not None and not isinstance(on, Remembered) and on not in self._visible:
                return False
            self._wx = plain[0]
            self._wy = plain[1]
            self._wr = plain[2]
            return True
        option = self._drawn(self._family.get(name))
        if option is None:
            return False
        members = option[0].members.get(name)
        if members is not None:
            if len(members) == 0:
                return False
            name = members[0]
        center = option[1].get(name)
        if center is None:
            return False
        self._wx = center[0]
        self._wy = center[1]
        self._wr = center[2]
        return True

    def _drawn(self, of: "str | None"):
        """The placement array `of` is drawn in now, with its centers, or `None` if it is not
        drawn (or `of` names no array)."""
        if of is None:
            return None
        stimulus = self._visible.get(of)
        if stimulus is None:
            return None
        options = self._arrays[of]
        index = 0
        while index < len(options):
            option = options[index]
            index += 1
            if option[0].draws(stimulus):
                return option
        return None

    def _distractor(self, pick: int) -> int:
        """How many distractors are drawn now, and the `pick`th of them into `_wx`, `_wy`, `_wr`
        (none for a `pick` of -1): each window an error saccade is scored on, an alias's objects
        each one."""
        names = self._distractors
        count = 0
        index = 0
        while index < len(names):
            name = names[index]
            index += 1
            plain = self._plain.get(name)
            if plain is not None:
                if self._where(name):
                    if count == pick:
                        return count + 1
                    count += 1
                continue
            option = self._drawn(self._family.get(name))
            if option is None:
                continue
            members = option[0].members.get(name)
            if members is None:
                if self._where(name):
                    if count == pick:
                        return count + 1
                    count += 1
                continue
            member = 0
            while member < len(members):
                center = option[1].get(members[member])
                member += 1
                if center is None:
                    continue
                if count == pick:
                    self._wx = center[0]
                    self._wy = center[1]
                    self._wr = center[2]
                    return count + 1
                count += 1
        return count

    def _empty(self) -> None:
        """**Empty space**, into `_wx`, `_wy`: a direction drawn at random, at the targets'
        eccentricity from the screen's center, outside every window the trial can draw by
        `MARGIN_DEG`; after `TRIES` directions that are not, the last one beyond every window."""
        rng = self._rng
        reach = math.radians(self._reach)
        tries = 0
        while True:
            direction = rng.random() * (2.0 * math.pi)
            self._toward(reach, direction)
            if self._clear():
                return
            tries += 1
            if tries >= TRIES:
                self._toward(math.radians(self._beyond), direction)
                return

    def _toward(self, eccentricity: float, direction: float) -> None:
        """The position `eccentricity` radians of true angle from straight ahead, `direction`
        radians counter-clockwise from rightward, as per-axis degrees into `_wx`, `_wy`
        (`geometry.polar_deg`'s arithmetic, within 90°, built of floats alone)."""
        across = math.sin(eccentricity)
        ahead = math.cos(eccentricity)
        self._wx = math.degrees(math.atan2(across * math.cos(direction), ahead))
        self._wy = math.degrees(math.atan2(across * math.sin(direction), ahead))
        self._wr = 0.0

    def _clear(self) -> bool:
        """Whether `(_wx, _wy)` is outside every window the trial can draw by `MARGIN_DEG`."""
        every = self._all
        index = 0
        while index < len(every):
            center = every[index]
            index += 1
            if separation_deg(self._wx, self._wy, center[0], center[1]) <= center[2] + MARGIN_DEG:
                return False
        return True


def _center(window: Window, values: dict) -> "tuple[float, float, float] | None":
    """A window's center and radius as numbers, or `None` where these values cannot place it (the
    eye does not look at it; `gaze.Tracked` raises when asked about it, as it always has)."""
    if window is None:
        return None
    try:
        x, y = position_of(window.at, values)
        radius = values[window.radius.name] if isinstance(window.radius, P) else window.radius
        return (float(x), float(y), float(radius))
    except Exception:  # noqa: BLE001 -- an unplaceable window is one the eye does not look at
        return None


class Seeing(Tracked):
    """**`gaze.Tracked`, the rig's gaze world, whose tracker is a simulated eye** (`Eye`): every
    guard, map, staleness and saccade rule is `Tracked`'s, and the eye is shown the display and told
    each state's first frame before `Tracked` is, so its sample for a frame answers that frame."""

    def __init__(self, eye: Eye, trial: Trial, frame_period: float,
                 values: "dict | None" = None) -> None:
        Tracked.__init__(self, Tracker(), MAPPING, trial, frame_period, values, source=eye)
        self.eye = eye

    def began(self, state: str, frame: int) -> None:
        self.eye.began(state, frame)
        Tracked.began(self, state, frame)

    def display(self, visible, frame: int) -> None:
        self.eye.see(visible, frame)
        Tracked.display(self, visible, frame)
