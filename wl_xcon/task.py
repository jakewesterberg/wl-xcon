"""The within-trial task representation.

Declarative data, not code (ADR-0006). A trial is states and guarded transitions;
`taskd` executes it and the task never owns the frame loop. Plain Python
declarations rather than a text DSL, so an ordinary editor gives autocomplete and
type checking -- and so a model authoring one is writing the language it writes best.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from enum import Enum
from typing import NamedTuple

from wl_xcon.geometry import on_circle_deg, polar_deg
from wl_xcon.photometry import Color, Contrast


class Family(Enum):
    """Which kind of ending an `Outcome` is: the groups `Outcome`'s own comments have
    always drawn, held as data so a console can group by them (P4d-2b spec §3).

    **Grouping, never a rollup.** A console shows each outcome that occurred with its
    count, under its family, and never sums a family into one number. Nothing here
    defines correct, error or aborted: that is the PI's to define -- fixed on this
    enum or per task. Where `early_response` and `late_response` fall, open since
    2026-09-26 (spec §3), the PI settled on 2026-10-18: each is a wrong answer, judged
    and never right ("Both wrong answers (as built)"); `no_response` is a miss where a
    structure makes withholding an answer (`Counting.withholding`), and otherwise a
    break after the stimulus.

    The values are the words a console prints.
    """

    TARGET = "target"
    DISTRACTOR = "distractor"
    WITHHOLD = "withhold"
    NO_ENGAGEMENT = "no engagement"
    BREAKS = "breaks"
    RIG = "rig"


class Outcome(Enum):
    """How a trial ended.

    **Six families, held as data** (`Family`, `Outcome.family`, P4d-2b spec §3):
    responses to the target, responses to a distractor, withholding, no engagement,
    breaks -- the trial ending because a hold was not maintained -- and the rig. The
    comments below mark the same groups.

    `ABORT` is the residual and is deliberately not a break: the animal went
    somewhere that was neither target nor distractor, which is a different statement
    from failing to hold something.
    """

    # Responses to the target
    CORRECT = "correct"
    EARLY_RESPONSE = "early_response"
    LATE_RESPONSE = "late_response"

    # Responses to a distractor
    WRONG_TARGET = "wrong_target"
    EARLY_ERROR = "early_error"
    LATE_ERROR = "late_error"

    # Correctly withholding, and failing to. **Without both, d' and criterion are
    # not computable** -- and not recoverable offline either, because a correct
    # rejection was previously indistinguishable from an animal that did nothing.
    CORRECT_REJECT = "correct_reject"
    FALSE_ALARM = "false_alarm"

    # Nothing at all
    NO_FIXATION = "no_fixation"
    NO_RESPONSE = "no_response"
    ABORT = "abort"

    # Breaks: a hold that was not maintained
    FIXATION_BREAK = "fixation_break"
    TARGET_BREAK = "target_break"
    CATCH_BREAK = "catch_break"
    MOTION_BREAK = "motion_break"
    #: A blink longer than the task tolerates. Behaviour, and separable from a
    #: fixation break because some tasks must not tolerate blinks at all.
    BLINK_BREAK = "blink_break"

    # The rig, not the animal. Kept apart from `ABORT` -- which means the animal
    # went somewhere that was neither target nor distractor -- because mixing them
    # makes a session's abort rate a number about two unrelated things, with no way
    # to tell whether to fix the animal or the camera.
    TRACKER_LOST = "tracker_lost"
    FAULT = "fault"

    @property
    def family(self) -> "Family":
        """This outcome's `Family`, from `_FAMILY` below the class. A property rather
        than part of the value, so `Outcome.value` stays the wire string every record
        and every telemetry frame already carries."""
        return _FAMILY[self]


#: Every `Outcome`'s family: the comment groups above, as data. **Total** --
#: `tests/test_task.py` fails if an outcome is added without one.
_FAMILY: dict[Outcome, Family] = {
    Outcome.CORRECT: Family.TARGET,
    Outcome.EARLY_RESPONSE: Family.TARGET,
    Outcome.LATE_RESPONSE: Family.TARGET,
    Outcome.WRONG_TARGET: Family.DISTRACTOR,
    Outcome.EARLY_ERROR: Family.DISTRACTOR,
    Outcome.LATE_ERROR: Family.DISTRACTOR,
    Outcome.CORRECT_REJECT: Family.WITHHOLD,
    Outcome.FALSE_ALARM: Family.WITHHOLD,
    Outcome.NO_FIXATION: Family.NO_ENGAGEMENT,
    Outcome.NO_RESPONSE: Family.NO_ENGAGEMENT,
    Outcome.ABORT: Family.NO_ENGAGEMENT,
    Outcome.FIXATION_BREAK: Family.BREAKS,
    Outcome.TARGET_BREAK: Family.BREAKS,
    Outcome.CATCH_BREAK: Family.BREAKS,
    Outcome.MOTION_BREAK: Family.BREAKS,
    Outcome.BLINK_BREAK: Family.BREAKS,
    Outcome.TRACKER_LOST: Family.RIG,
    Outcome.FAULT: Family.RIG,
}


@dataclass(frozen=True, slots=True)
class Param:
    """One live-editable parameter: name, unit, and the range it may hold.

    The single declaration S8 §3.1 turns into validation, the console's widget,
    the per-trial snapshot and the ELN summary -- which is what makes live control
    work for a task nobody hand-wrote, with no per-task UI code.
    """

    name: str
    unit: str
    #: Numeric parameters carry a range; categorical ones carry `choices` instead.
    #: Categorical exists because **appearance is a parameter** -- swapping circles
    #: among squares for penguins among elephants is a value change, and a range
    #: cannot express it (S1a §4).
    low: float | None = None
    high: float | None = None
    choices: tuple = ()
    live: bool = True
    #: **The value a run starts with when nobody gives one** (P4d-2b spec §6.2:
    #: "Starting values are the task's own"; S8 §3.4's *task* layer, under what a console
    #: or `wlx run --set` gives): a number inside the parameter's own declared range.
    #: `__post_init__` refuses any other as the task is built: a starting appearance is
    #: not carried until telemetry publishes one (XC-420; the record writes one since REC-27),
    #: and a start outside `[low, high]` would run under `wlx run`, which takes no
    #: pre-flight (XC-159; the b3a-2 final review, m2). A bound that is not a real number is left to
    #: `preflight.values`, which holds the merged values to `[low, high]` again -- one outside
    #: it a warning since XC-352's D2 (2026-10-11), unless the checks widened to it refuse it
    #: (`preflight.beyond`) -- and fails closed on a bound it cannot compare. `None`, the
    #: default, leaves it to whoever
    #: starts the run -- and a `wlx taskd` run whose trials use a number nobody gave is
    #: refused by its pre-flight (`preflight.values`), not faulted at its first trial.
    start: object = None

    def __post_init__(self) -> None:
        start = self.start
        if start is not None and (
            isinstance(start, bool)
            or not isinstance(start, (int, float))
            or not math.isfinite(start)
        ):
            raise ValueError(
                f"parameter {self.name!r}: a task's starting value is a number, and "
                f"{start!r} is not a finite one; a starting appearance is not carried "
                f"until telemetry publishes one (XC-420)"
            )
        if start is None:
            return
        low, high = _real(self.low), _real(self.high)
        side = (
            "below" if low is not None and start < low
            else "above" if high is not None and start > high
            else None
        )
        if side is not None:
            declared = (
                f"[{low!r}, {high!r}]" if low is not None and high is not None
                else f"at least {low!r}" if low is not None
                else f"at most {high!r}"
            )
            raise ValueError(
                f"parameter {self.name!r}: its starting value {start!r} is {side} the "
                f"range it declares, {declared}; a run would start outside it"
            )


def _real(bound: object) -> float | None:
    """A declared bound a start is held to: a finite real number that is not a `bool`,
    or `None` -- for no bound, and for one `Param` cannot compare, which the pre-flight
    fails closed on instead (`preflight.values`)."""
    if isinstance(bound, bool) or not isinstance(bound, (int, float)):
        return None
    return bound if math.isfinite(bound) else None


@dataclass(frozen=True, slots=True)
class P:
    """A reference to a declared parameter, usable anywhere a value is."""

    name: str


@dataclass(frozen=True, slots=True)
class Remembered:
    """The marker for a window with deliberately nothing in it.

    A memory-guided saccade scores gaze against a location the animal must hold in
    memory; the defining feature of the paradigm is that the display is blank there.
    That is indistinguishable, from the outside, from an author who forgot to show
    the stimulus -- so the two are made distinguishable by making one of them
    something you have to write down.
    """


REMEMBERED = Remembered()


@dataclass(frozen=True, slots=True)
class Polar:
    """**A position as its eccentricity and direction: how a task writes one by default** (the
    PI, 2026-10-19: "Polar first, x-y allowed"). `Polar(8, 45)` is 8° of visual angle from
    straight ahead, 45° counter-clockwise from rightward (engine spec §5.1's convention: 0°
    right, counter-clockwise positive, +y up), converted exactly to the per-axis degrees the
    screen is drawn in (`geometry.polar_deg`). Accepted wherever a position is: a stimulus's,
    each eye's own, an `Update`'s, a window's center and an array's center; either field may be
    a setting. A pair `(x, y)` stays for axis-aligned designs -- a grid, a meridian, the
    calibration constellation -- and is per axis: `(8·cos 45°, 8·sin 45°)` is 7.975° out, not
    8°, which is why a task file that computes a position from `cos` and `sin` is warned at
    load (`check`'s `computed-position`).

    Named for the coordinates it holds, as `Disc` and `Array` are for what they draw; its fields
    are the PI's words, "at eccentricity e, direction θ", the direction an angle as a grating's
    drift direction is."""

    eccentricity: "float | P"
    direction: "float | P"


def is_point(value: object) -> bool:
    """**A position written out in numbers**: a `Polar` whose eccentricity and direction are
    numbers, or an (x, y) pair of two numbers, a tuple or a list. What check 8 reads among the
    choices of a setting that is a whole position (`check._points`), and what makes a setting one
    on the console (`review.declares_position`; XC-401's second fix round, N1): one function, so
    the two cannot read a setting differently. A `bool` is no number, here as elsewhere."""

    def number(item: object) -> bool:
        return isinstance(item, (int, float)) and not isinstance(item, bool)

    if isinstance(value, Polar):
        return number(value.eccentricity) and number(value.direction)
    return isinstance(value, (tuple, list)) and len(value) == 2 and all(number(v) for v in value)


def position_of(at: object, values: dict) -> tuple[float, float]:
    """A position as the per-axis degrees everything downstream reads -- the screen, the gaze
    windows, the checks: a `Polar` converted exactly (`geometry.polar_deg`), a pair coordinate by
    coordinate, a whole-point setting as its value is. Floats and `math` only: `screen.resolve`
    reads each stimulus's position through it at a frame. A gaze window's center is read through it
    once, between trials (`gaze._judged`), where until XC-413 it was read every frame."""
    if isinstance(at, P):
        at = _value(at, values)
    if isinstance(at, Polar):
        return polar_deg(float(_value(at.eccentricity, values)),
                         float(_value(at.direction, values)))
    return (float(_value(at[0], values)), float(_value(at[1], values)))


@dataclass(frozen=True, slots=True)
class Window:
    """A named region gaze, a joystick or a touch is tested against.

    Declared rather than referred to in passing: position and radius are exactly
    what an experimenter tunes, so both may be parameters, and a task naming a
    window nothing declares has no criterion at all.
    """

    name: str
    #: Its center: a `Polar` by default, or a per-axis pair (`Polar`'s docstring says when).
    at: "Polar | tuple[float, float] | P"
    radius: "float | P"
    #: The stimulus this window scores, by name -- or `REMEMBERED` when nothing is
    #: displayed there on purpose. **Unset is refused at load**, because the whole
    #: value of the coupling is that "nothing is there" has to be a claim someone
    #: made rather than a state the task fell into. With it, a hold on a window
    #: whose stimulus is not on the display is a load-time error instead of a
    #: silently different experiment (S1a §11).
    on: "str | Remembered | None" = None
    #: `"both"`, `"left"` or `"right"`. The tracker is binocular (architecture
    #: §1: 500 Hz binocular dDPI), so a per-eye criterion is available and is the
    #: correct primitive on a stereoscope: under dichoptic presentation the
    #: non-viewing eye deviates to its phoria rather than following the stimulus, and
    #: scoring it against a conjugate estimate scores an average of one eye doing the
    #: task and one eye not looking at the stimulus (S1a §12).
    eye: str = "both"


@dataclass(frozen=True, slots=True)
class Guard:
    """Base for the guard vocabulary (S1 §2.2). A guard is data: the framework
    evaluates it, the task never does."""


@dataclass(frozen=True, slots=True)
class After(Guard):
    """Elapsed time in seconds, from state entry by default.

    **`since` moves the zero.** Timed from state entry, an interval starts before the
    stimulus it follows exists: the transition happens during a frame and the flip
    that carries the stimulus is 8-33 ms later, depending on refresh rate and where
    in the frame the transition landed. Every SOA written that way is wrong by a
    variable amount -- and variable error is worse than constant error, because it
    cannot be corrected offline. `After(0.05, since=Onscreen("task"))` runs from the
    photodiode saying the stimulus reached the display.

    A plain `After` is the only guard that bounds a wait by construction, which is
    why the checker asks about it by type. **One with a `since` is not**: if the flip
    is dropped or the patch occluded, the guard never arms, so a state relying on it
    alone could wait forever -- and check 4 refuses that.
    """

    seconds: "float | P"
    #: What starts the clock. `None` is state entry.
    since: "Guard | None" = None


@dataclass(frozen=True, slots=True)
class Entered(Guard):
    """Gaze entered a window and settled. Pairs with `Exited`."""

    window: str


@dataclass(frozen=True, slots=True)
class Exited(Guard):
    """Gaze left a window after acquiring it."""

    window: str


@dataclass(frozen=True, slots=True)
class Hold(Guard):
    """Gaze continuously inside a window for a duration. ML's `holdfix`.

    Imperative rather than past tense, because a task file describes what should
    happen rather than what did. Distinct from `Entered` followed by `After`, because the hold restarts if gaze
    leaves -- and because the staleness policy differs: a hold spanning a tracker
    stall is not a hold that was observed (S5 §4.1).
    """

    window: str
    seconds: "float | P"


@dataclass(frozen=True, slots=True)
class SaccadeTo(Guard):
    """A detected saccade landing in a window. Detection is the versioned
    Engbert-Kliegl component (S5 §5), never re-derived per task.

    **Only a saccade begun in this state, judged where it landed** (EYE-19, revised 2026-10-30,
    the PI): one whose onset is before the state's first frame is anticipatory and never counts,
    and the window is the one drawn on the frame the saccade lands, never later. **One
    exception, the carry**: the saccade whose onset ended the state before -- a transition on
    `SaccadeOnset`, or on `After(t, since=SaccadeOnset())` -- counts here too, if the detector
    puts its eye at rest on this state's first frame or after, so an intrasaccadic jump is scored
    where the eye lands."""

    window: str


@dataclass(frozen=True, slots=True)
class SaccadeOnset(Guard):
    """A saccade began, wherever it lands. What a gaze-contingent update rides.

    **Only a saccade begun in this state** (EYE-19, revised 2026-10-30), seen on the frame the
    detector confirms it, by every `SaccadeOnset` of the state asking then, a clock's
    (`After(since=SaccadeOnset())`) and an edge's alike. A saccade carried in from the state
    before (`SaccadeTo`'s carry) never satisfies it: its onset ended that state."""


@dataclass(frozen=True, slots=True)
class Onscreen(Guard):
    """The photodiode says the stimulus reached the display (S6 §3).

    Named for the world rather than for our intention, which is the whole
    distinction: a state waiting on `Onscreen` advances on evidence, not on the
    belief that a flip happened.
    """

    patch: str = "task"


@dataclass(frozen=True, slots=True)
class Pressed(Guard):
    device: str


@dataclass(frozen=True, slots=True)
class Released(Guard):
    device: str


@dataclass(frozen=True, slots=True)
class Touched(Guard):
    window: str


@dataclass(frozen=True, slots=True)
class ChairStill(Guard):
    """`wl-shook`'s motion gate: the chair is quiet enough to proceed."""


@dataclass(frozen=True, slots=True)
class FeatureAbove(Guard):
    """A neural feature over threshold. Tier-3 gating (S7); the decision stays in
    `taskd`, never in the feature client.

    Named for the *feature* rather than for a rate, because `FeatureSource` publishes
    whichever of the two feature types an experiment chose (S7 §5) and may one day
    publish something that is not a rate at all -- a phase, a decoder output.
    """

    source: str
    threshold: float


@dataclass(frozen=True, slots=True)
class Response(Guard):
    device: str


@dataclass(frozen=True, slots=True)
class On:
    """One guarded transition: when `guard` fires, do `do`, then go to `to`.

    Actions belong on the transition rather than on the destination because the
    scoring action -- reward -- happens on the *edge* that scores. A terminal
    outcome has no state to enter, so an entry action could never express it.
    """

    guard: Guard
    to: "str | Outcome"
    do: list["Action"] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class State:
    name: str
    enter: list[Action] = field(default_factory=list)
    go: list[On] = field(default_factory=list)
    #: Declared when a state deliberately has no time bound -- free viewing of
    #: natural images is the motivating case (S1 §5.4). The checker refuses an
    #: undeclared one, so an unbounded wait is always a choice on the record
    #: rather than an omission nobody noticed.
    unbounded: bool = False


@dataclass(frozen=True, slots=True)
class Tolerances:
    """How long the gaze signal may be interrupted before the trial ends.

    **Two graces, because they are two phenomena.** A blink is the animal; tracker
    loss is the rig. They look identical in the data -- gaze leaves the window -- so
    scoring both as fixation breaks inflates a session's break rate with equipment
    failure, invisibly, and an animal looks worse than it is.

    `blink` defaults to zero: a task that tolerates blinks says so, because the other
    way round a task inherits a tolerance nobody chose and reports holds that were
    never observed. `tracker_lost` defaults to 50 ms, which is the OpenIrisDPI paper's
    reported stall maximum (~2% of frames >= 10 ms, max ~50 ms), a placeholder until
    V3(a) -- that is the tracker's behaviour, not the animal's, and blaming the animal
    for it would cost roughly one trial in every few.

    `None` switches enforcement off, explicitly: a joystick-only task has no gaze
    criterion to protect and should not abort because a camera nobody is using
    dropped out.
    """

    blink: "float | P | None" = 0.0
    tracker_lost: "float | P | None" = 0.05


@dataclass(frozen=True, slots=True)
class Trial:
    start: str
    states: list[State]
    params: list[Param] = field(default_factory=list)
    #: Hand-written windows and `ObjectWindows` families, in one list: a window is a
    #: window whether an author typed it or an array generated it, and keeping them
    #: apart would mean every check that walks windows had to walk two lists.
    windows: "list[Window | ObjectWindows]" = field(default_factory=list)
    tolerances: "Tolerances" = field(default_factory=lambda: Tolerances())
    #: Which setup the task is written for: `"direct"`, `"stereoscope"` or `"either"`
    #: (direct-view spec §3). **`"either"` is safe as the default** because the field
    #: check runs against the setup the session chose -- `taskd` and `wlx check` pass
    #: the session's geometry (`wlx run --rig --view`) -- so an undeclared task in the
    #: stereoscope is held to its mask. Disparity, a random-dot stereogram
    #: or a stimulus shown to one eye needs `"stereoscope"`, and the checker says so.
    view: str = "either"
    #: The bottom layer (engine spec §4.4, §7.5): an absolute color, or `None` for the
    #: black default. A task using Weber contrast declares its own.
    background: "Color | P | None" = None
    #: Each eye's own background, stereoscope only; `None` is `background`.
    background_left: "Color | P | None" = None
    background_right: "Color | P | None" = None
    #: One of `PERIPHERY`.
    periphery: str = "true_angle"

    #: Its counting table (engine spec §16.1; engine build C2a): what each outcome does to its
    #: condition's count. `None` is undeclared, which `check.check_task` refuses in a task's
    #: structure (the PI, 2026-10-11: "no default; each task declares"); a bare `Trial`, a test's
    #: or `check`'s, needs none.
    counting: "Counting | None" = None


@dataclass(frozen=True, slots=True)
class Bounded:
    """A reference to an entry in the rig/subject bounded config (S8 §4).

    The task names it; it never holds the value. Resolution happens against the
    subject's ceiling at run time, in the process that also owns the accounting.
    """

    name: str


@dataclass(frozen=True, slots=True)
class Action:
    """Base for the action vocabulary (S1 §2.3)."""


@dataclass(frozen=True, slots=True)
class Appearance:
    """What a stimulus looks like. Never what it is *for* -- that is its window.

    Separating the two is what lets a visual search task switch from circles among
    squares to penguins among elephants **without touching the task**: the structure
    is identical and only an appearance changes. Since appearance can be a parameter
    (§`Param.choices`), that switch is a value applied in an inter-trial interval
    rather than a new task or a new block.
    """


@dataclass(frozen=True, slots=True)
class Disc(Appearance):
    size: "float | P" = 1.0
    contrast: "Contrast | P | None" = None
    #: Device-independent colour, or `None` when the light is a `contrast` against the
    #: trial's background. On the appearance rather than the stimulus because colour is
    #: a feature: "red among green" and "circles among squares" are then the same kind of
    #: switch, and both are values a parameter can carry (S1a §4).
    color: "Color | P | None" = None


@dataclass(frozen=True, slots=True)
class Square(Appearance):
    size: "float | P" = 1.0
    contrast: "Contrast | P | None" = None
    #: Device-independent colour, or `None` when the light is a `contrast` against the
    #: trial's background. On the appearance rather than the stimulus because colour is
    #: a feature: "red among green" and "circles among squares" are then the same kind of
    #: switch, and both are values a parameter can carry (S1a §4).
    color: "Color | P | None" = None


@dataclass(frozen=True, slots=True)
class Bar(Appearance):
    """For receptive-field mapping."""

    length: "float | P" = 4.0
    width: "float | P" = 0.5
    orientation: "float | P" = 0.0
    contrast: "Contrast | P | None" = None
    #: Device-independent colour, or `None` when the light is a `contrast` against the
    #: trial's background. On the appearance rather than the stimulus because colour is
    #: a feature: "red among green" and "circles among squares" are then the same kind of
    #: switch, and both are values a parameter can carry (S1a §4).
    color: "Color | P | None" = None


@dataclass(frozen=True, slots=True)
class Gabor(Appearance):
    """Field names throughout: `sf` is spatial frequency in cycles per degree,
    `sigma` the Gaussian envelope. A model writing
    `spatial_frequency_cycles_per_degree` has not read a methods section."""

    sf: "float | P" = 2.0
    orientation: "float | P" = 0.0
    phase: "float | P" = 0.0
    contrast: "Contrast | P | None" = None
    sigma: "float | P" = 1.0
    #: Device-independent colour, or `None` when the light is a `contrast` against the
    #: trial's background. On the appearance rather than the stimulus because colour is
    #: a feature: "red among green" and "circles among squares" are then the same kind of
    #: switch, and both are values a parameter can carry (S1a §4).
    color: "Color | P | None" = None


@dataclass(frozen=True, slots=True)
class Dots(Appearance):
    """A random-dot kinematogram. `seed` is the stimulus: motion is a pure function
    of parameters, seed and frame index, so a trial reconstructs exactly (S4 §5)."""

    coherence: "float | P" = 0.5
    direction: "float | P" = 0.0
    speed: "float | P" = 5.0
    density: "float | P" = 1.0
    aperture: "float | P" = 5.0
    seed: int = 0
    #: Device-independent colour, or `None` when the light is a `contrast` against the
    #: trial's background. On the appearance rather than the stimulus because colour is
    #: a feature: "red among green" and "circles among squares" are then the same kind of
    #: switch, and both are values a parameter can carry (S1a §4).
    color: "Color | P | None" = None


@dataclass(frozen=True, slots=True)
class Annulus(Appearance):
    inner: "float | P" = 1.0
    outer: "float | P" = 2.0
    contrast: "Contrast | P | None" = None
    #: Device-independent colour, or `None` when the light is a `contrast` against the
    #: trial's background. On the appearance rather than the stimulus because colour is
    #: a feature: "red among green" and "circles among squares" are then the same kind of
    #: switch, and both are values a parameter can carry (S1a §4).
    color: "Color | P | None" = None


@dataclass(frozen=True, slots=True)
class Cross(Appearance):
    """A plus sign. The other thing people fixate, besides a disc."""

    size: "float | P" = 0.5
    thickness: "float | P" = 0.1
    contrast: "Contrast | P | None" = None
    #: Device-independent colour, or `None` when the light is a `contrast` against the
    #: trial's background. On the appearance rather than the stimulus because colour is
    #: a feature: "red among green" and "circles among squares" are then the same kind of
    #: switch, and both are values a parameter can carry (S1a §4).
    color: "Color | P | None" = None


@dataclass(frozen=True, slots=True)
class Polygon(Appearance):
    """`sides=3` a triangle, `sides=4` a diamond, and so on. One appearance rather
    than a class per shape -- the same reasoning that produced `Stimulus`."""

    sides: int = 3
    size: "float | P" = 1.0
    orientation: "float | P" = 0.0
    contrast: "Contrast | P | None" = None
    #: Device-independent colour, or `None` when the light is a `contrast` against the
    #: trial's background. On the appearance rather than the stimulus because colour is
    #: a feature: "red among green" and "circles among squares" are then the same kind of
    #: switch, and both are values a parameter can carry (S1a §4).
    color: "Color | P | None" = None


@dataclass(frozen=True, slots=True)
class Grating(Appearance):
    """A grating in a hard aperture. Distinct from `Gabor`, whose envelope is
    Gaussian -- the difference matters for edge artifacts and for spatial-frequency
    bandwidth, which is why the field names them separately."""

    sf: "float | P" = 2.0
    orientation: "float | P" = 0.0
    phase: "float | P" = 0.0
    contrast: "Contrast | P | None" = None
    aperture: "float | P" = 5.0
    #: Device-independent colour, or `None` when the light is a `contrast` against the
    #: trial's background. On the appearance rather than the stimulus because colour is
    #: a feature: "red among green" and "circles among squares" are then the same kind of
    #: switch, and both are values a parameter can carry (S1a §4).
    color: "Color | P | None" = None


@dataclass(frozen=True, slots=True)
class Plaid(Appearance):
    """Two superimposed gratings. `angle` is the separation between components."""

    sf: "float | P" = 2.0
    orientation: "float | P" = 0.0
    angle: "float | P" = 90.0
    contrast: "Contrast | P | None" = None
    aperture: "float | P" = 5.0
    #: Device-independent colour, or `None` when the light is a `contrast` against the
    #: trial's background. On the appearance rather than the stimulus because colour is
    #: a feature: "red among green" and "circles among squares" are then the same kind of
    #: switch, and both are values a parameter can carry (S1a §4).
    color: "Color | P | None" = None


@dataclass(frozen=True, slots=True)
class Checkerboard(Appearance):
    """RF mapping and evoked potentials."""

    check_size: "float | P" = 1.0
    contrast: "Contrast | P | None" = None
    aperture: "float | P" = 10.0
    #: Device-independent colour, or `None` when the light is a `contrast` against the
    #: trial's background. On the appearance rather than the stimulus because colour is
    #: a feature: "red among green" and "circles among squares" are then the same kind of
    #: switch, and both are values a parameter can carry (S1a §4).
    color: "Color | P | None" = None


@dataclass(frozen=True, slots=True)
class Noise(Appearance):
    """`exponent` 0 is white, 1 is pink, 2 is brown. `seed` is the stimulus, so a
    trial reconstructs exactly; `refresh_hz` above zero makes it dynamic."""

    exponent: "float | P" = 1.0
    contrast: "Contrast | P | None" = None
    aperture: "float | P" = 5.0
    refresh_hz: "float | P" = 0.0
    seed: int = 0
    #: Device-independent colour, or `None` when the light is a `contrast` against the
    #: trial's background. On the appearance rather than the stimulus because colour is
    #: a feature: "red among green" and "circles among squares" are then the same kind of
    #: switch, and both are values a parameter can carry (S1a §4).
    color: "Color | P | None" = None


@dataclass(frozen=True, slots=True)
class Picture(Appearance):
    asset: str = ""
    size: "float | P" = 10.0


@dataclass(frozen=True, slots=True)
class Movie(Appearance):
    asset: str = ""
    size: "float | P" = 10.0
    loop: bool = False


@dataclass(frozen=True, slots=True)
class Blank(Appearance):
    """Nothing. A catch trial's stimulus is not the absence of a `Show` -- it is a
    `Show` of nothing, which is what makes catch and non-catch trials structurally
    identical and therefore comparable."""


@dataclass(frozen=True, slots=True)
class Form:
    """A disparity field across a patch: depth at every point, not one number.

    `Stimulus.disparity` displaces a whole stimulus, which is position disparity and
    nothing else. Everything the 3D-shape and surface literature is built on -- a
    slant, a curvature, a corrugation -- is a *field*, and a patch carrying one has
    no single disparity to displace by.
    """

    def range(self, values: dict) -> "tuple[float, float]":
        """The least and greatest disparity this form reaches, in degrees."""
        raise NotImplementedError


@dataclass(frozen=True, slots=True)
class Corrugation(Form):
    """A sinusoidal depth grating: the standard probe for disparity-defined shape.

    `sf` is in cycles per degree of visual angle, `amplitude` the peak disparity in
    degrees, `orientation` the corrugation's axis in degrees.
    """

    sf: "float | P" = 0.5
    amplitude: "float | P" = 0.1
    orientation: "float | P" = 0.0
    phase: "float | P" = 0.0

    def range(self, values: dict) -> "tuple[float, float]":
        peak = abs(float(_value(self.amplitude, values)))
        return (-peak, peak)


@dataclass(frozen=True, slots=True)
class Slant(Form):
    """A planar disparity gradient, in degrees of disparity per degree of position.

    The extreme disparity depends on how wide the patch is, so `range` is answered
    against the aperture rather than reported on its own -- an amplitude quoted
    without the aperture it spans is not a quantity.
    """

    gradient: "float | P" = 0.05
    orientation: "float | P" = 0.0

    def range(self, values: dict, aperture: float = 0.0) -> "tuple[float, float]":
        reach = abs(float(_value(self.gradient, values))) * aperture / 2.0
        return (-reach, reach)


@dataclass(frozen=True, slots=True)
class RDS(Appearance):
    """A random-dot stereogram: form carried by binocular disparity alone.

    **`correlation` is why this is its own appearance.** +1 is an ordinary
    stereogram, 0 is uncorrelated noise, and **-1 is anticorrelated** -- dots of
    opposite contrast in the two eyes. That is the control condition every disparity
    paper is asked for, because V1 responds to it while perceived depth inverts or
    vanishes, so it separates a correlation-based response from a depth-based one.
    There is no way to express it by displacing a stimulus, which is all
    `Stimulus.disparity` can do.

    A parameter, so correlated and anticorrelated conditions interleave within a
    session. Comparing them across sessions compares two states of the animal.

    `seed` is the stimulus: the dot field is a pure function of parameters, seed and
    frame index, so a trial reconstructs exactly (S4 §5).
    """

    correlation: "float | P" = 1.0
    #: Internal depth structure, or `None` for a frontoparallel patch at whatever
    #: disparity the stimulus carries.
    form: "Form | None" = None
    density: "float | P" = 1.0
    dot_size: "float | P" = 0.1
    aperture: "float | P" = 5.0
    contrast: "Contrast | P | None" = None
    seed: int = 0
    color: "Color | P | None" = None

    def disparity_range(self, values: dict) -> "tuple[float, float]":
        """The least and greatest disparity anywhere in this patch.

        What check 8 needs: a patch centred safely can still push one eye's image
        off the panel at the extreme of its corrugation, and only that eye's.
        """
        if self.form is None:
            return (0.0, 0.0)
        if isinstance(self.form, Slant):
            return self.form.range(values, float(_value(self.aperture, values)))
        return self.form.range(values)


@dataclass(frozen=True, slots=True)
class Array(Appearance):
    """`n` objects evenly spaced on a ring, one of them the target.

    **This exists so that set size is a value.** Written the obvious way -- an
    N-object array as N separate `Show` actions -- set size becomes a change to the
    *shape* of the task: a different task file for four objects and eight, unavailable
    to live editing, and untouchable by a parameter. That is the commonest
    manipulation in visual search, and visual search is the lab's programme.

    An appearance rather than an action, so the whole array is **one named stimulus**
    on the display. The rest of the system -- `Hide`, `Update`, the visibility
    analysis, the review artifact -- then needs to know nothing about arrays.
    """

    n: "int | P" = 4
    radius: "float | P" = 8.0
    #: Index of the target within the ring. A parameter, so target position is
    #: manipulable between trials like anything else.
    target: "int | P" = 0
    looks: "Appearance | P" = field(default_factory=Disc)
    #: What the other objects look like. Target and distractors differing in exactly
    #: one property is what makes this a feature-search array rather than a
    #: collection of unrelated shapes -- and `looks`/`among` being parameters is what
    #: makes "red among green" and "circle among squares" the same task.
    among: "Appearance | P" = field(default_factory=Disc)
    #: Where object 0 sits, in degrees counter-clockwise from the positive x axis.
    #: Randomising it between trials is what stops an animal learning positions.
    phase: "float | P" = 0.0

    def positions(
        self, values: dict, at: "tuple[float, float]" = (0.0, 0.0)
    ) -> "list[tuple[float, float]]":
        """Object centers, in the degrees `at` is given in, for an array whose center is `at`.

        **A true circle of visual angle about the array's own direction** (the PI, 2026-10-19,
        "True circle": "every object exactly R from the array's center in visual angle,
        wherever the array is"), so neighbors are `2·asin(sin R·sin(π/n))` apart at any phase
        (`geometry.ring_spacing_deg`). Object `i` is at `phase + 360 i / n` degrees
        counter-clockwise from the array's local rightward axis, the frame a shape's orientation
        is drawn in (`geometry.on_circle_deg`; `viewport.local_true_angle`)."""
        n = int(_value(self.n, values))
        radius = float(_value(self.radius, values))
        phase = float(_value(self.phase, values))
        return [on_circle_deg(at[0], at[1], radius, phase + 360.0 * i / n) for i in range(n)]

    def object_looks(self, index: int, values: dict) -> "Appearance | P":
        target = int(_value(self.target, values))
        return self.looks if index == target else self.among


def _value(value, values: dict):
    """A parameter reference against bound values, for expansion.

    Missing is an error rather than a default, for the reason `run._resolve` gives:
    a set size that silently became zero would draw an empty screen, and an empty
    screen reads as an animal who will not work.
    """
    if isinstance(value, P):
        if value.name not in values:
            raise KeyError(f"no value bound for parameter {value.name!r}")
        return values[value.name]
    return value


@dataclass(frozen=True, slots=True)
class ObjectWindows:
    """The per-object windows an `Array` needs, declared once.

    One declaration rather than n, because n is not known until a trial runs. It
    generates `<of>.<i>` per object plus two aliases: **`<of>.target`**, and
    **`<of>.distractor`**, which is satisfied by any non-target object.

    The distractor alias is the point. Without it, every error saccade would have to
    be enumerated as one transition per object -- which is the same structure-versus-
    value problem one level down, and it would make the measurement search tasks
    exist to produce, target-versus-distractor, unavailable.
    """

    of: str
    radius: "float | P"
    eye: str = "both"

    def expand(self, array: Array, values: dict, at: object = (0.0, 0.0)) -> "list[Window]":
        """Each object's window, centered where the object is drawn: on the array's true circle
        about `at`, the array stimulus's own position in any form (`position_of`; XC-397: each
        window was on the ring about (0°, 0°) wherever the array was)."""
        at = array.positions(values, position_of(at, values))
        target = int(_value(array.target, values))
        windows = [
            Window(f"{self.of}.{i}", at=xy, radius=self.radius, on=self.of, eye=self.eye)
            for i, xy in enumerate(at)
        ]
        windows.append(
            Window(
                f"{self.of}.target",
                at=at[target],
                radius=self.radius,
                on=self.of,
                eye=self.eye,
            )
        )
        windows.append(
            Window(
                f"{self.of}.distractor",
                # A stand-in no gaze is scored against: it names the array and the eye, and the
                # alias is judged by the objects it names, every one but the target (the loop's
                # membership; `gaze.Tracked`'s for a saccade).
                at=at[target],
                radius=self.radius,
                on=self.of,
                eye=self.eye,
            )
        )
        return windows

    def members(self, array: Array, values: dict) -> "dict[str, tuple[str, ...]]":
        """Alias name to the concrete object windows that satisfy it."""
        n = int(_value(array.n, values))
        target = int(_value(array.target, values))
        return {
            f"{self.of}.target": (f"{self.of}.{target}",),
            f"{self.of}.distractor": tuple(
                f"{self.of}.{i}" for i in range(n) if i != target
            ),
        }


#: How a stimulus overlaps what is below it (engine spec §4.4): it covers it; its
#: light beyond the background adds to it; what is below shows only inside it (a
#: window) or is hidden inside it (a scotoma); it multiplies the contrast below (one
#: shapes another).
COMBINE = ("cover", "add", "window", "scotoma", "multiply")

#: How sizes behave away from the center (engine spec §5.3): each stimulus subtends its
#: declared degrees wherever it is. **The screen center's scale, `"center_scale"`, is retired**
#: (the PI, 2026-10-19, "Retire it": "Every stimulus is drawn in true visual angle; a task
#: declaring center scale is refused at load"; `check`'s `center-scale-retired`). The field keeps
#: its one value so a task that writes the default loads, and every task hashes, as before.
PERIPHERY = ("true_angle",)


@dataclass(frozen=True, slots=True)
class Stimulus:
    """Something on the display: a position, an appearance, and how it is shown.

    **Its position is written as eccentricity and direction by default**, `Polar(8, 45)`, or as
    a per-axis pair for an axis-aligned design (the PI, 2026-10-19; `Polar`).

    **One class, because the structure of a task does not change when the things in
    it change.** Position is cyclopean degrees; the display module maps it to
    per-eye viewport pixels using measured optics, so a task never names a pixel and
    the same task runs at a different distance, on a different panel, in either
    display mode, and on the kiosk.
    """

    #: The handle. `Hide` and `Update` address a stimulus by it, a `Window` names
    #: the one it scores, and the review artifact labels the timeline with it.
    #: Positional and required: an anonymous stimulus can be put up and never
    #: referred to again, which is the whole of what went wrong.
    name: str
    at: "Polar | tuple[float, float] | P"
    looks: "Appearance | P" = field(default_factory=Disc)
    disparity: "float | P" = 0.0
    #: `"both"`, `"left"` or `"right"`. Monocular and dichoptic presentation are
    #: first-class on a stereoscope: rivalry, monocular RF mapping and
    #: interocular-suppression designs all need one viewport to carry what the other
    #: does not. Distinct from disparity, which shifts one stimulus in both eyes.
    eye: str = "both"
    #: Drawing order: higher layers on top, ties in the order shown (engine spec §4.4).
    layer: int = 0
    #: One of `COMBINE`.
    combine: str = "cover"
    opacity: "float | P" = 1.0
    #: Each eye's own direction in degrees, after the vergence offset (engine spec §5.4),
    #: for dichoptic designs that place each eye's image themselves. Both or neither,
    #: never with a disparity, and only on the stereoscope; the checker refuses the rest.
    at_left: "Polar | tuple[float, float] | P | None" = None
    at_right: "Polar | tuple[float, float] | P | None" = None

    # Mapping a cyclopean position to each eye's direction (disparity, then the vergence
    # offset) is `screen.resolve`'s (engine build A1), from the session's `Geometry`; a
    # task names degrees, never pixels.


class Unchanged:
    """`Update`'s "leave this alone", which `None` cannot mean.

    `None` is a legal value for several stimulus properties, so a default of `None`
    would make "set it to nothing" and "do not touch it" the same instruction.
    """

    def __repr__(self) -> str:
        # No longer `# pragma: no cover`: the sentinel's legibility in a traceback
        # is a small contract and `tests/test_display.py` now holds it.
        return "UNCHANGED"


UNCHANGED = Unchanged()


@dataclass(frozen=True, slots=True)
class Show(Action):
    """Put a stimulus on the display. **It stays until `Hide` or the end of the
    trial** -- not until its state ends.

    State-scoped presentation was the original wording and it was wrong in a way no
    check could see: the reference task shows a fixation point in one state and asks
    for a hold on it in the next, so the point was removed at the exact frame the
    animal was asked to hold it. The task was written correctly and passed all ten
    checks. Persistence also makes `Hide` and `Update` mean something, which
    state-scoping did not.
    """

    stimulus: Stimulus


@dataclass(frozen=True, slots=True)
class Hide(Action):
    """Take a stimulus off the display, by name."""

    stimulus: str


@dataclass(frozen=True, slots=True)
class Update(Action):
    """Change properties of a stimulus already on the display, without an offset.

    Change detection, apparent motion and gaze-contingent updating all need one
    uninterrupted presentation with one property different. `Hide` followed by
    `Show` inserts an offset transient and at least one blank frame -- which is the
    exact confound those paradigms are built to avoid, so expressing them that way
    would be expressing a different experiment.
    """

    stimulus: str
    at: "Polar | tuple[float, float] | P | Unchanged" = UNCHANGED
    looks: "Appearance | P | Unchanged" = UNCHANGED
    disparity: "float | P | Unchanged" = UNCHANGED
    eye: "str | Unchanged" = UNCHANGED
    layer: "int | Unchanged" = UNCHANGED
    opacity: "float | P | Unchanged" = UNCHANGED
    at_left: "Polar | tuple[float, float] | P | Unchanged" = UNCHANGED
    at_right: "Polar | tuple[float, float] | P | Unchanged" = UNCHANGED

    def changes(self) -> dict:
        """The properties this actually sets. Empty means the action does nothing,
        which the checker refuses."""
        return {
            field_name: value
            for field_name, value in (
                ("at", self.at),
                ("looks", self.looks),
                ("disparity", self.disparity),
                ("eye", self.eye),
                ("layer", self.layer),
                ("opacity", self.opacity),
                ("at_left", self.at_left),
                ("at_right", self.at_right),
            )
            if not isinstance(value, Unchanged)
        }


@dataclass(frozen=True, slots=True)
class Score(Action):
    """Record a scored response *within* a trial (S1a §8).

    A trial emits scored events as it goes and the terminal outcome summarises. That
    is what lets a task express several correct targets -- *which* one was chosen is
    the thing the experiment is about, and it was previously not expressible anywhere
    -- and free viewing, where an animal moves between windows producing a sequence
    of responses rather than one.

    **The classification reuses `Outcome`**, because the same taxonomy applies at
    both grains: a single choice can be early, late, to a distractor or correct
    exactly as a whole trial can. A second vocabulary would have to be kept in step
    with this one for no gain.
    """

    window: str
    scored_as: Outcome


@dataclass(frozen=True, slots=True)
class Custom(Action):
    """Behaviour the vocabulary lacks, named rather than contained (S1 §8).

    Resolves to a reviewed component in the framework's own source. A task using
    one is flagged onto the human-review list beside the welfare-critical modules
    -- accepted is not the same as unremarkable.
    """

    name: str


@dataclass(frozen=True, slots=True)
class Mark(Action):
    """Strobe an event code -- what ML and the field both call an *event marker*.

    The code is allocated elsewhere (S2, ADR-0007) and validated at load; a task
    naming an unallocated one is refused.
    """

    code: int


class Reward(Action):
    """Deliver reward, by bounded-config reference.

    **Refuses a magnitude, deliberately and at runtime.** A type checker catches
    `Reward(0.15)` too, but nothing guarantees one is running on the machine that
    loads a generated task -- and welfare bounds that depend on someone having run
    a linter are not bounds. See S8 §7's welfare-critical module list.
    """

    __slots__ = ("ref",)

    def __init__(self, ref: "str | Bounded") -> None:
        if isinstance(ref, Bounded):
            ref = ref.name
        if not isinstance(ref, str):
            raise TypeError(
                f"Reward takes the name of a bounded-config entry, not "
                f"{type(ref).__name__}: a task may name how reward is configured "
                f"but never how much it is"
            )
        object.__setattr__(self, "ref", Bounded(ref))


def actions_of(trial: Trial) -> list[tuple[str, Action]]:
    """Every action in a trial, with the state it belongs to.

    **Both places.** Actions sit on state entry and on transitions, and anything
    walking them must walk both -- reward can only ever be a transition action,
    because a terminal outcome has no state to enter. The first real task passed a
    checker with this gap while emitting an unallocated code, which is how it was
    found.

    One definition rather than two, because `check.py` and `review.py` both need
    it: a review artifact showing a different set of actions from the one the
    checker inspected would be the worst possible artifact -- a picture the
    reviewer trusts, of a task nobody validated.
    """
    found: list[tuple[str, Action]] = []
    for state in trial.states:
        found.extend((state.name, action) for action in state.enter)
        for edge in state.go:
            found.extend((state.name, action) for action in edge.do)
    return found



# --- Shortcuts -------------------------------------------------------------
#
# Named constructors over `Stimulus`, not classes beside it. A fixation point is a
# small disc at the origin often enough that every task would otherwise spell it
# out, and "fix point" is the most-used phrase in the field -- so it earns a name
# without earning a type. Expect more of these; the rule is that a shortcut adds
# **defaults and a name**, never a concept, and anything it produces is an ordinary
# `Stimulus` the rest of the system cannot distinguish.


def FixPoint(
    name: str = "fix",
    at: "tuple[float, float] | P" = (0.0, 0.0),
    size: "float | P" = 0.3,
    **kwargs,
) -> Stimulus:
    """A small disc at the origin: the fixation point."""
    return Stimulus(name=name, at=at, looks=Disc(size=size), **kwargs)


def array_actions(trial: Trial) -> "list[tuple[str, str, bool, Array]]":
    """**Every array a `Show` or an `Update` gives**, by the action that gives it: the state, the
    stimulus's name, whether an `Update` gives it, and the array, as written or among a setting's
    choices (a setting in its own choices is read once). Since XC-402 an array's object windows
    follow an `Update` that changes it, so the load checks and the review report read every one of
    these, never a `Show`'s alone (`check._array_faults`, `check._declared_window_names`,
    `check._shown_arrays`; `review.render`'s windows table; XC-411)."""
    params = {param.name: param for param in trial.params}
    found: list[tuple[str, str, bool, Array]] = []

    def walk(state: str, name: str, updated: bool, looks: object, inside: frozenset[str]) -> None:
        if isinstance(looks, P):
            param = params.get(looks.name)
            if param is not None and looks.name not in inside:
                for choice in param.choices:
                    walk(state, name, updated, choice, inside | {looks.name})
        elif isinstance(looks, Array) and (state, name, updated, looks) not in found:
            found.append((state, name, updated, looks))

    for state, action in actions_of(trial):
        if isinstance(action, Show):
            walk(state, action.stimulus.name, False, action.stimulus.looks, frozenset())
        elif isinstance(action, Update) and "looks" in action.changes():
            walk(state, action.stimulus, True, action.looks, frozenset())
    return found


def expand_windows(
    trial: Trial, values: dict
) -> "tuple[list[Window], dict[str, tuple[str, ...]]]":
    """A trial's windows with every array family expanded, plus alias membership.

    One definition, used by the trial loop, the gaze world and the simulator alike
    (`run.run_trial`, `gaze.Tracked`, `simulate.prepare`), for the reason `actions_of`
    gives: a world scoring a different set of windows from the one the loop asks about
    would be scoring a task nobody runs. The load checks do not read it: they reason over
    every value a setting allows, where this builds the windows for one trial's values.

    **An array's object windows here are where its last `Show` puts it**, which is where they
    are until it is first drawn: from then they follow it, wherever a `Show` or an `Update` draws
    it (`placements`; XC-402).
    """
    # Each array with the position its last `Show` gives it, so its objects' windows are there.
    shown = {action.stimulus.name: action.stimulus for _, action in actions_of(trial)
             if isinstance(action, Show) and isinstance(action.stimulus.looks, Array)}
    windows: list[Window] = []
    aliases: dict[str, tuple[str, ...]] = {}
    for declared in trial.windows:
        if isinstance(declared, ObjectWindows):
            stimulus = shown.get(declared.of)
            if stimulus is None:
                continue
            windows.extend(declared.expand(stimulus.looks, values, stimulus.at))
            aliases.update(declared.members(stimulus.looks, values))
        else:
            windows.append(declared)
    return windows, aliases


class Placement(NamedTuple):
    """One way a trial can draw an array that has object windows -- a position and an appearance
    its `Show`s and `Update`s give it -- with the object windows and aliases built there, by
    `ObjectWindows.expand` and `ObjectWindows.members` (`placements`). A record the run builds,
    as `run.Shown` is, and never part of a task: not a dataclass of this vocabulary."""

    #: As declared: the very objects a `Show` or an `Update` wrote, which the loop carries onto
    #: the display (`run._apply`), so a stimulus on the display is matched by identity.
    at: object
    looks: object
    #: Every object window name the family has in any of the trial's placements, to its window
    #: here, or `None` where this placement has no such object: a smaller set size. Every name, so
    #: switching to it overwrites the last placement's windows whole and adds no key.
    windows: "dict[str, Window | None]"
    #: `<of>.target` and `<of>.distractor` to the objects each names here.
    members: "dict[str, tuple[str, ...]]"

    def draws(self, stimulus: Stimulus) -> bool:
        """Whether `stimulus`, as on the display, is drawn this way. **On the trial loop's path**,
        on the frame a stimulus changes: identity first, and equality only for a stimulus made
        some other way."""
        return ((stimulus.at is self.at or stimulus.at == self.at)
                and (stimulus.looks is self.looks or stimulus.looks == self.looks))


def placements(trial: Trial, values: dict) -> "dict[str, tuple[Placement, ...]]":
    """**Every placement each array with object windows can be drawn in, its windows built there**
    (XC-402): each position a `Show` or an `Update` of the array gives it, with each appearance one
    gives it, so an `Update` that moves the array -- its position, in any form; its ring's radius;
    its rotation; its set size; which object is its target -- moves its windows with it.

    **Built between trials**, for the trial's values: which `Update`s will have run is a question
    about paths through the task, so every pairing is built, as `check._as_updated` reasons, and a
    trial's frames only switch from one to another (`Placement.draws`; `gaze.Tracked.display`,
    `run.run_trial`). Each object's window is built by `ObjectWindows.expand`, the route that
    places it where `screen` draws it (`Array.positions` about `position_of`): one geometry, never
    a second copy. An appearance that is not an array, or a setting whose value is not one, draws
    no objects, so it has no placement: the windows stay where the objects were last drawn, as
    they do while the array is hidden. A family whose array no `Show` gives has none."""
    shows: dict[str, list[Stimulus]] = {}
    updates: dict[str, list[Update]] = {}
    for _, action in actions_of(trial):
        if isinstance(action, Show):
            shows.setdefault(action.stimulus.name, []).append(action.stimulus)
        elif isinstance(action, Update):
            updates.setdefault(action.stimulus, []).append(action)

    def unique(found: list) -> list:
        kept: list = []
        for value in found:  # by equality: values need not be hashable
            if not any(value is seen or value == seen for seen in kept):
                kept.append(value)
        return kept

    found: dict[str, tuple[Placement, ...]] = {}
    for declared in trial.windows:
        if not isinstance(declared, ObjectWindows) or declared.of not in shows:
            continue
        shown, changed = shows[declared.of], updates.get(declared.of, [])
        built = []
        for at in unique([s.at for s in shown] + [u.at for u in changed if "at" in u.changes()]):
            for looks in unique([s.looks for s in shown]
                                + [u.looks for u in changed if "looks" in u.changes()]):
                array = _value(looks, values)
                if not isinstance(array, Array):
                    continue
                windows = {w.name: w for w in declared.expand(array, values, at)}
                built.append((at, looks, windows, declared.members(array, values)))
        names = {name: None for _, _, windows, _ in built for name in windows}
        found[declared.of] = tuple(
            Placement(at, looks, {**names, **windows}, members)
            for at, looks, windows, members in built
        )
    return found


# --- The task object (engine spec §3.5; engine build C1) --------------------------------
#
# A task file defines one `Task`: its trial structures by name, the default one -- which the plain
# run plays, and a condition that names no structure -- its plans (engine build C2b), and what
# XC-288 §4 has a task declare about itself: what each of its settings means, which of its objects
# count as choices, and how its reaction time is defined. Its format is defined here, in wl-xcon
# (the PI, 2026-10-11; the engine C1 plan). Procedures (D) and stages (C7) join it as fields with
# defaults.

#: What a setting's meaning may be (XC-288 §4.1; TRN-03): clear-cut with a direction, expected
#: with a direction and a context note, or not a difficulty setting.
CLEAR_CUT = "clear-cut"
EXPECTED = "expected"
NOT_DIFFICULTY = "not a difficulty setting"
MEANING_KINDS = (CLEAR_CUT, EXPECTED, NOT_DIFFICULTY)

#: Which way a clear-cut or expected setting moves the task.
EASIER = "easier"
HARDER = "harder"
DIRECTIONS = (EASIER, HARDER)

#: What a setting is (the PI, 2026-10-11): a **criterion**, what counts as success -- a window, a
#: hold, the time allowed to acquire fixation, a response deadline -- or a **stimulus**, what the
#: animal sees -- brightness, size, position, appearance -- or **neither**: the bounded settings, a
#: consequence and a session limit.
CRITERION = "criterion"
STIMULUS = "stimulus"
NEITHER = "neither"
ROLES = (CRITERION, STIMULUS, NEITHER)


@dataclass(frozen=True, slots=True)
class Background:
    """`Meaning.relative_to`'s "the trial's background": a direction read on moving a luminance
    away from that of the background the trial is shown on (`Trial.background`; black when that
    is `None`)."""


BACKGROUND = Background()


def _text(value: object, what: str) -> None:
    """`value` is text, or a `ValueError` naming `what`."""
    if not isinstance(value, str):
        raise ValueError(f"{what} is text, not {type(value).__name__}")


def _reference(value: object) -> bool:
    """Whether a direction can read from `value` (`Meaning.relative_to`): `None`, a finite number
    that is not a `bool`, a setting's name, or `BACKGROUND`."""
    if value is None or isinstance(value, Background):
        return True
    if isinstance(value, str):
        return bool(value)
    return (
        isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
    )


@dataclass(frozen=True, slots=True)
class Meaning:
    """What changing one setting does to the task (XC-288 §4.1; TRN-03), so a change to it can be
    recorded as easier or harder, or as neither, and an expected direction is never recorded as a
    fact; and **whether the setting is a criterion or a stimulus** (`role`; the PI, 2026-10-11),
    so a lenient criterion is never read as an easier stimulus.

    **`raising` reads relative to `relative_to`** (the engine C1 plan's call 4): with `None`, what
    raising the value does; with a number, what moving the value away from it does (0 for a
    position, whose side is not its difficulty); with another setting's name, what moving the
    value away from that setting's current value does; with `BACKGROUND`, what moving a luminance
    away from the trial's background does. For a setting whose values are choices
    (`Param.choices`), which have no order, it is what changing it does. `overrides` is set only
    where a task overrides the shared meaning of a common setting (`declarations.COMMON`), and
    says why (the PI, 2026-10-11)."""

    kind: str
    role: str
    raising: "str | None" = None
    note: str = ""
    relative_to: "float | str | Background | None" = None
    overrides: str = ""

    def __post_init__(self) -> None:
        if self.kind not in MEANING_KINDS:
            raise ValueError(
                f"a setting's meaning is {', '.join(repr(k) for k in MEANING_KINDS)}, "
                f"not {self.kind!r}"
            )
        if self.role not in ROLES:
            raise ValueError(
                f"a setting's role is {', '.join(repr(r) for r in ROLES)}, not {self.role!r}: "
                f"what counts as success, what the animal sees, or neither (the PI, 2026-10-11)"
            )
        _text(self.note, "a meaning's note")
        _text(self.overrides, "why a meaning overrides the shared one")
        if not _reference(self.relative_to):
            raise ValueError(
                f"a meaning's relative_to is None (raising the value), a number, another "
                f"setting's name or BACKGROUND, not {self.relative_to!r}"
            )
        if self.kind == NOT_DIFFICULTY:
            if self.raising is not None or self.relative_to is not None:
                raise ValueError(
                    "a setting that is not a difficulty setting moves the task neither way, "
                    "so it takes no direction"
                )
            return
        if self.raising not in DIRECTIONS:
            raise ValueError(
                f"a setting that is {self.kind} says which way raising it moves the task, "
                f"{EASIER!r} or {HARDER!r}, not {self.raising!r}"
            )
        if self.kind == EXPECTED and not self.note.strip():
            raise ValueError(
                "an expected direction comes with a note on why it might not hold for an "
                "animal (XC-288 §4.1)"
            )


@dataclass(frozen=True, slots=True)
class ReactionTime:
    """How a task's reaction time is defined (XC-288 §4.3), so one column means one thing per task:
    from the instant a trial entered `state` to the instant it left that state for one of `to` (a
    state's name or an `Outcome`). A trial that left it any other way -- a timeout, a break -- has
    none. `note` says in words what it measures (the engine C1 plan's call 8)."""

    state: str
    to: tuple
    note: str

    def __post_init__(self) -> None:
        _text(self.state, "a reaction time's state")
        _text(self.note, "a reaction time's note")
        if not self.state or not self.note.strip():
            raise ValueError("a reaction time names its state and says what it measures")
        if not isinstance(self.to, tuple) or not self.to:
            raise ValueError(
                "a reaction time ends where its state is left for: a tuple of states or "
                "outcomes, at least one"
            )
        for end in self.to:
            if not isinstance(end, (str, Outcome)):
                raise ValueError(
                    f"a reaction time ends on leaving for a state or an outcome, not {end!r}"
                )


#: What choosing an object is (XC-288 §4.3, as amended 2026-10-11: "object", not "item"), as the
#: guards that make it: a saccade landing, gaze entering or held, a touch, a lever.
CHOSEN_BY: "dict[str, tuple[type, ...]]" = {
    "saccade": (SaccadeTo,),
    "gaze": (Entered, Hold),
    "touch": (Touched,),
    "lever": (Pressed, Released),
}


@dataclass(frozen=True, slots=True)
class Choice:
    """What a task offers to choose between (XC-288 §4.3): the windows -- or an array's object
    families, `"search.target"` -- whose objects count as choices, and what choosing one is, one
    of `CHOSEN_BY`, so each trial can record the object chosen (engine build C7)."""

    objects: tuple
    by: str

    def __post_init__(self) -> None:
        if not isinstance(self.objects, tuple) or not self.objects:
            raise ValueError("a choice names its objects: a tuple of windows, at least one")
        for chosen in self.objects:
            if not isinstance(chosen, str) or not chosen:
                raise ValueError(f"a choice's object is a window's name, not {chosen!r}")
        if self.by not in CHOSEN_BY:
            raise ValueError(f"a choice is made by {', '.join(CHOSEN_BY)}, not {self.by!r}")


@dataclass(frozen=True, slots=True)
class NoChoice:
    """`Task.choice`'s "this task offers nothing to choose between" (XC-288 §4.3), which leaving
    `choice` unset cannot mean: unset is refused at load (`check.check_task`'s
    `undeclared-choice`), so a task offering none says so, as a window with nothing in it says
    `REMEMBERED`, and a forgotten choice cannot pass for no choice."""


NO_CHOICE = NoChoice()


# --- Counting and repeats (engine spec §16; engine build C2a) ---------------------------------
#
# What each trial does to its condition's count, declared by each trial structure (§16.1: "One
# table classifies every outcome, per trial structure"), so the scheduler never decides an
# experimental design: "run until ten correct" and "show the array a hundred times" are both
# ordinary (TSK-26).

#: What a trial does to its condition's count (engine spec §16.1-16.2): **counted**, an answer,
#: paying the condition's debt; **spent**, used up -- it pays the debt as a presentation and is
#: marked an abort; **owed**, shown again later, paying nothing; **unpaid**, paying nothing and
#: not shown again -- the block's order draws the condition as it would have -- which is what
#: "run until ten correct" does with a wrong answer (the PI, 2026-08-31: "wrong choice not"
#: re-queued; §16.2: "Not repeated: wrong targets").
COUNTED = "counted"
SPENT = "spent"
OWED = "owed"
UNPAID = "unpaid"
COUNTING_CLASSES = (COUNTED, SPENT, OWED, UNPAID)

#: The right answers: a correct trial, and a correct rejection, which `codes.py` marks correct
#: too ("A correct rejection *is* a correct trial"). What ends a drum, and what a criterion and a
#: condition's correct count count as right (`scheduler.Scheduler.record`).
RIGHT = frozenset({Outcome.CORRECT, Outcome.CORRECT_REJECT})

#: The answers, counted in every structure (§16.1; TSK-27): the responses to the target and to a
#: distractor, early and late ones too, and a correct rejection and a false alarm, which a task
#: produces only where withholding is an answer.
ANSWERS = frozenset(
    {
        Outcome.CORRECT,
        Outcome.EARLY_RESPONSE,
        Outcome.LATE_RESPONSE,
        Outcome.WRONG_TARGET,
        Outcome.EARLY_ERROR,
        Outcome.LATE_ERROR,
        Outcome.CORRECT_REJECT,
        Outcome.FALSE_ALARM,
    }
)

#: Ending before the decision, the animal not engaging or the rig failing: owed by default (§16.2;
#: TSK-29), so the condition still gets its datum.
REPEATED = frozenset(
    {Outcome.FIXATION_BREAK, Outcome.NO_FIXATION, Outcome.TRACKER_LOST, Outcome.FAULT}
)

#: The breaks after the stimulus appears (§16.2's "other breaks"): leaving the target, a catch
#: trial's or a motion's break, a long blink, and looking elsewhere (`ABORT`, which is no break but
#: ends a trial after the stimulus as one does). **No default** (the PI, 2026-10-11): each
#: structure says whether they are spent or owed (`Counting.after_stimulus`). One that ends a trial
#: before its stimulus appeared is owed, as a fixation break is, unless the table gives the outcome
#: a class of its own (`Counting.of`).
AFTER_STIMULUS = frozenset(
    {
        Outcome.TARGET_BREAK,
        Outcome.CATCH_BREAK,
        Outcome.MOTION_BREAK,
        Outcome.BLINK_BREAK,
        Outcome.ABORT,
    }
)

#: What a trial that reached the longest trial counts as (engine spec §6.8; `run.LONGEST_TRIAL_S`):
#: **a missed acquisition** (the PI, 2026-10-11: "it isn't a fixation break, it is a missed
#: acquisition"), `NO_FIXATION`'s class -- owed unless the structure says otherwise, so it is
#: repeated like a fault. Its record still says `hang` (§6.8), which `resume`, `health` and the
#: page read.
HANG_COUNTS_AS = Outcome.NO_FIXATION

#: **A block's "no limit"** (XC-380; engine build C2b): a block's own counting table whose `cap` is
#: this removes its task's repeat limit in that block, where `None` leaves the task's in force (the
#: PI, 2026-10-18: "No: the task's limit applies unless the block sets its own"). Text, so a task's
#: content hash writes it as it writes any declaration.
NO_LIMIT = "no limit"


@dataclass(frozen=True, slots=True)
class Counting:
    """One trial structure's counting table (engine spec §16.1-16.2): what each outcome does to its
    condition's count, as five declarations.

    - `after_stimulus`: whether a break after the stimulus appears (`AFTER_STIMULUS`, and no
      response where withholding is not an answer) is `SPENT` -- used up, counted as presented
      and marked an abort -- or `OWED`, shown again. **Required, with no default** (the PI,
      2026-10-11: "no default; each task declares"); `check.check_task` refuses a task's structure
      without a table.
    - `appears`: the state the stimulus appears in -- the target's or the array's, a cued task's
      cue (the PI, 2026-10-13: "Task names it, required") -- so a break before the trial reached
      it ended the trial before anything was presented. `check.check_task` refuses a task's
      structure whose table names none, or a state it does not have; a table a block counts by
      (`scheduler.Block.counting`) names none, the structure's own saying where its stimulus
      appears.
    - `withholding`: whether not answering is an answer here (detection, catch trials, go/no-go), so
      no response is a miss, counted (§16.1; the PI, 2026-10-11, for both detection tasks).
    - `outcomes`: an outcome's class where it differs from those rules, by its wire string
      (`Outcome.value`): a training block counting a fixation break as an error, or "run until ten
      correct" leaving every answer but a right one unpaid.
    - `cap`: how many failed repeats in a row of one trial of a condition are allowed before its
      remaining debt is forgiven, its shortfall recorded and shown (§16.6, as the PI read it on
      2026-10-12: "The condition is moved past after 3 failed repeats in a row, and the count
      resets once it is done"): any trial not shown again ends the count (the PI, 2026-10-18).
      `None`, no limit, repeated until done (the PI, 2026-10-11), with the console's *clear* --
      a training aid a trainer switches on (the PI, 2026-10-18) -- to move past one by hand. In a
      block's own table `None` is "not set", so the structure's limit holds there (the PI,
      2026-10-18: "the task's limit applies unless the block sets its own"), and **`NO_LIMIT`
      removes it** (XC-380); in a structure's table the two say the same.

    Every answer (`ANSWERS`) is counted and every outcome of `REPEATED` owed, unless `outcomes` says
    otherwise; `of` reads the table."""

    after_stimulus: str
    appears: "str | None" = None
    withholding: bool = False
    outcomes: "dict[str, str]" = field(default_factory=dict)
    cap: "int | str | None" = None

    def __post_init__(self) -> None:
        if self.after_stimulus not in (SPENT, OWED):
            raise ValueError(
                f"a break after the stimulus is {SPENT} (used up) or {OWED} (shown again), not "
                f"{self.after_stimulus!r}"
            )
        if self.appears is not None and (not isinstance(self.appears, str) or not self.appears):
            raise ValueError(
                f"a counting table's appears names the state its stimulus appears in, not "
                f"{self.appears!r}"
            )
        if not isinstance(self.withholding, bool):
            raise ValueError("a counting table's withholding is True or False")
        if not isinstance(self.outcomes, dict):
            raise ValueError("a counting table's outcomes are a dict of outcome names to classes")
        names = {outcome.value for outcome in Outcome}
        for name, kind in self.outcomes.items():
            if name not in names:
                raise ValueError(
                    f"{name!r} is not an outcome; the outcomes are {', '.join(sorted(names))}"
                )
            if kind not in COUNTING_CLASSES:
                raise ValueError(
                    f"an outcome is {', '.join(COUNTING_CLASSES)}, and {name!r} is given {kind!r}"
                )
        if self.cap is not None and self.cap != NO_LIMIT and (
            isinstance(self.cap, bool) or not isinstance(self.cap, int) or self.cap < 0
        ):
            raise ValueError(
                f"a repeat cap is a whole number of repeats, 0 or more, None for no limit, or "
                f"NO_LIMIT where a block removes its task's; not {self.cap!r}"
            )

    def of(self, outcome: "Outcome | None", shown: bool = True) -> str:
        """What `outcome` does to its condition's count. `None`, a trial that reached the longest
        trial, counts as `HANG_COUNTS_AS`. `shown` is whether the trial's stimulus had appeared
        (`taskd`: the trial entered the state the structure's table names, `appears`): a break
        before it ended the trial before anything was presented, so it is owed, as a fixation
        break is, whatever `after_stimulus` says -- though a class `outcomes` gives the outcome
        still decides it."""
        if outcome is None:
            outcome = HANG_COUNTS_AS
        declared = self.outcomes.get(outcome.value)
        if declared is not None:
            return declared
        if outcome in ANSWERS or (outcome is Outcome.NO_RESPONSE and self.withholding):
            return COUNTED
        if outcome in REPEATED or not shown:
            return OWED
        return self.after_stimulus


# --- Plans and blocks (engine spec §13.1, §13.3, §13.5, §13.8; engine build C2b) --------------
#
# **A task's plans live in its task object** (the PI, 2026-10-07: "In the task file": "beside its
# trial(s), one reviewable file; the operator chooses at run start among the plans it declares").
# A plan is its block types, how they follow one another, and a run time limit. A block type is a
# named set of conditions; **a block is one stretch of consecutive trials under one block type
# inside one run** (the PI, 2026-10-01: "it is important that blocks are temporal instances"):
# types recur, and each occurrence is a new block. The vocabulary lives here, the task's, so the
# content hash and its format pins read it as they read every declaration; `scheduler` plays it
# and imports it from here.


@dataclass(frozen=True, slots=True)
class Order:
    """How the next condition is chosen. **Declared per block** (PI, 2026-08-31)."""


@dataclass(frozen=True, slots=True)
class Shuffled(Order):
    """Every still-owed condition once per pass, in random order.

    Balance as the block progresses, and a bound on how long an animal waits for any
    condition. Partly predictable near the end of a pass, when few remain.
    """


@dataclass(frozen=True, slots=True)
class WithReplacement(Order):
    """Each trial drawn independently, optionally weighted.

    No sequential predictability, and it supports conditions wanted rarely -- catch
    trials, probes. Balance only in expectation, so the counters matter more.
    """

    weights: dict = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Constrained(Order):
    """Drawn with replacement, refusing runs longer than `max_run`.

    What most search and attention designs actually use, because an animal exploits
    runs: three of the same target position in a row and it stops searching and
    starts predicting.
    """

    max_run: int = 2
    weights: dict = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Condition:
    """One condition of a block (engine spec §14.1): its `name`, the `values` it sets, the trials
    it is owed (`target`; a minimum where its block has another end rule), and **the trial
    structure it plays** (`structure`, one of the task's by name; `None`, the task's default) --
    the PI, 2026-10-07: "a task declares several trial structures; each condition names its own;
    interleaving them in a block is ordinary". Its trials count by that structure's table
    (`Trial.counting`) unless its block counts by one of its own. **A value it sets gives way to
    a live edit** of the same setting for the rest of the run (engine spec §14.7), and the trial
    still counts toward it."""

    name: str
    values: dict
    target: int
    structure: "str | None" = None


@dataclass(frozen=True, slots=True)
class Block:
    """One block type (engine spec §13.5): its `name`, its `conditions`, and how a block of it
    ends -- every condition's target used up, and where it declares them a criterion, a number of
    trials, or a time limit -- with how it orders its conditions, what it counts by and whether it
    drums. A name is what each trial's row records as its `block`, the block's type (wl-preproc
    reads it so), so no two block types of one plan share one."""

    name: str
    conditions: "list[Condition]"
    #: `(proportion, window)` -- "80% correct over the last 20 answers", a percentage; a proportion
    #: of 1.0 is a streak, "N correct in a row" (the engine C2a plan, revised 2026-10-18). Judged on
    #: every answer, and on a broken hold or a failure to acquire fixation where this block's own
    #: table scores it (`scheduler.Scheduler._scored`); a percentage judges only each trial's first
    #: answer under `first_answers`, a streak never. The block ends once every condition is owed
    #: nothing and, with a criterion, the criterion is met too: **its targets are a minimum**
    #: (`scheduler.Scheduler.finished`).
    criterion: "tuple[float, int] | None" = None
    #: The table this block counts by, **replacing its conditions' structures'** (TSK-26: what
    #: counts is declared per block): `scheduler.CORRECT_ONLY`, `PRESENTED`, `EVERY_TRIAL` or any
    #: `Counting` -- a block training an animal to hold fixation may count a fixation break as an
    #: error that pays its debt -- and its rule then judges that break a miss (the PI, 2026-10-18,
    #: "Yes, where the block says so"; `scheduler.Scheduler._scored`) -- while a block measuring a
    #: psychometric function must not. What is an answer stays the structure's: a block's own
    #: `withholding` is not read, nor its `appears` (`scheduler.Scheduler._class`;
    #: `taskd._appeared`). `None`, each condition's structure's own.
    counting: "Counting | None" = None
    order: Order = field(default_factory=Shuffled)
    #: **Drumming** (the PI, 2026-10-11: "a training tool ... where a trial is repeated until
    #: correct"): every trial of this block that is not right comes back at once, paying nothing,
    #: until it is. A trainer switches it on or off for a block or a run from the console as well
    #: (`scheduler.Scheduler.drum`).
    drum: bool = False
    #: **A number of trials** (engine spec §13.5; the PI, 2026-10-07, "a number of trials"): the
    #: block ends once it has run this many trials -- a trial and its drummed repeats one (the PI,
    #: 2026-10-18: "200 trials; drummed repeats inside them"), an ordinary repeat a trial of its own
    #: -- **and every target is used up**: its targets are a minimum, as under a criterion, and past
    #: them every condition is drawn by its order (`scheduler.Scheduler.past_targets`). `None`, no
    #: such rule.
    trials: "int | None" = None
    #: **A time limit**, in seconds of trials run (engine spec §13.5; the PI, 2026-10-19): read
    #: between trials, so a trial in flight finishes and pays if earned ("Finish trial, then end");
    #: a drummed trial waiting comes back until it is right first ("Finish the drum first"); time
    #: paused does not count ("Pauses don't count"). What the block still owes then is recorded as
    #: not run, "time ran out" (`scheduler.TIME`). `None`, no limit. Not a welfare limit: the
    #: out-of-cage limit ends the session whatever a block says.
    time_limit_s: "float | None" = None


@dataclass(frozen=True, slots=True)
class BlockOrder:
    """How a plan's blocks follow one another (engine spec §13.5; the PI, 2026-10-07: "a fixed
    sequence; repeating (Bt1, Bt2, Bt1, Bt2...); randomized from a recorded seed, balanced;
    progression by criterion (training stages, shaping)"). Declared per plan;
    `scheduler.Scheduler` plays it, drawing a random order from the run's recorded seed."""


@dataclass(frozen=True, slots=True)
class Fixed(BlockOrder):
    """Each block type once, in the order the plan lists them; the plan is done after the last."""


@dataclass(frozen=True, slots=True)
class Cyclic(BlockOrder):
    """The plan's block types in order, over and over (Bt1, Bt2, Bt1, Bt2...): `cycles` passes, or
    with `None` until a time limit, a stop or the out-of-cage limit ends the run."""

    cycles: "int | None" = None


@dataclass(frozen=True, slots=True)
class Balanced(BlockOrder):
    """**Shuffled rounds, within each run** (the PI, 2026-10-11: "A 'balanced' block order balances
    within each run"; 2026-10-19, "Shuffled rounds"): each round shows every block type once, in an
    order drawn from the run's seed, **and never the type just played first** ("Never
    back-to-back": "Each new round starts with a different type than the last one played, so every
    block boundary is a real switch"); `blocks` in all, or with `None` round after round until a
    time limit, a stop or the out-of-cage limit. A count that is not whole rounds leaves the last
    round partial, the seed choosing which types it shows (a warning at load); a run cut short
    leaves its last round incomplete, as recorded."""

    blocks: "int | None" = None


@dataclass(frozen=True, slots=True)
class Random(BlockOrder):
    """**Each block a type drawn at random** from the run's seed (the PI, 2026-10-19, "Both, as two
    choices": "random can repeat a type and leave another out by chance, recorded with its seed"):
    `blocks` in all, or with `None` until a time limit, a stop or the out-of-cage limit."""

    blocks: "int | None" = None


@dataclass(frozen=True, slots=True)
class ByCriterion(BlockOrder):
    """**A training progression** (the PI, 2026-10-07: "advance on one criterion, fall back on
    another, as declared"; 2026-10-19, "Same, but top keeps going" and "Move on anyway"): the
    plan's block types are its stages, easiest first, and the run starts at the first. **A stage
    whose own rule is met moves up one**; a stage whose time runs out moves up one whether it
    passed or not. **`fall_back`, `(proportion, window)`**: back one stage, started fresh, when
    fewer than `proportion` of the last `window` answers are right, judged once that many answers
    are in and on answers only, as every rule -- **each trial's first answer only**, however the
    stage's own rule counts drummed tries ("First answer only": "so one stubborn trial can't demote
    a stage the animal is otherwise doing well in"), and a broken hold where the stage's own table
    scores one, as toward moving up ("Yes, the same"). **At the top stage the animal keeps
    working** once its rule is met, until a time limit, a stop or the session's end; the top
    stage's own time limit, with nowhere to move on to, ends the run. `None`, no fall-back."""

    fall_back: "tuple[float, int] | None" = None


@dataclass(frozen=True, slots=True)
class Plan:
    """One plan (engine spec §13.1): its block types (`blocks`), how they follow one another
    (`order`, `Fixed()` by default), and **a run time limit** (`time_limit_s`, in seconds of trials
    run; the PI, 2026-10-19, "Yes, in the plan": "the run ends at the first pause between trials
    after its time", pauses not counting, a drummed trial waiting answered right first, "Finish
    the drum first") -- which is no welfare limit: the out-of-cage limit ends the session whatever
    a plan says, and the console's scheduled stop stays as it is, whichever comes first ending the
    run. **Its shape is refused as it is built**, as a `Task`'s is; what it declares is checked at
    load (`check.check_task`)."""

    blocks: "list[Block]"
    order: BlockOrder = field(default_factory=Fixed)
    time_limit_s: "float | None" = None

    def __post_init__(self) -> None:
        if not isinstance(self.blocks, list) or not all(
                isinstance(block, Block) for block in self.blocks):
            raise ValueError("a plan's blocks are a list of Blocks")
        if not isinstance(self.order, BlockOrder):
            raise ValueError(
                "a plan's order is a BlockOrder: Fixed(), Cyclic(), Balanced(), Random() or "
                "ByCriterion()"
            )
        if self.time_limit_s is not None and (
                isinstance(self.time_limit_s, bool)
                or not isinstance(self.time_limit_s, (int, float))):
            raise ValueError(
                f"a plan's time limit is a number of seconds, or None; not {self.time_limit_s!r}"
            )


@dataclass(frozen=True, slots=True)
class Task:
    """One task (engine spec §3.5): its trial structures by name (§13.3), `default` the one the
    plain run plays and a condition naming no structure plays, its plans by name (§13.1; engine
    build C2b), and what XC-288 §4 has it declare: what its settings mean beyond the shared list
    (`meanings`; `declarations.COMMON`), what it offers to choose -- a `Choice`, or `NO_CHOICE` --
    how its reaction time is defined, and whether it needs a fixed head. **Its shape is refused as
    it is built**, as a `Param`'s start is; what it declares is checked at load
    (`check.check_task`), which refuses an unset reaction time or choice."""

    structures: "dict[str, Trial]"
    default: str
    reaction_time: "ReactionTime | None" = None
    choice: "Choice | NoChoice | None" = None
    meanings: "dict[str, Meaning]" = field(default_factory=dict)
    #: Whether the task needs the animal's head fixed (engine spec §20.1; STE-25): a warning, never
    #: a refusal (the PI, 2026-10-11), in any session not declared head-fixed (`RIG_FIXED`), where
    #: a free head would position every stimulus against a nominal head.
    needs_fixed_head: bool = False
    #: **Its plans, by name** (engine spec §13.1; engine build C2b): what the operator chooses among
    #: at run start, the first preselected on the page (the PI, 2026-10-19, "Preselect first, keep
    #: plain"). Empty, the plain run only: one block of the default structure, every trial paying.
    plans: "dict[str, Plan]" = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.structures, dict) or not self.structures:
            raise ValueError("a task has its trial structures, by name: a dict, at least one")
        for name, structure in self.structures.items():
            if not isinstance(name, str) or not name:
                raise ValueError(f"a trial structure is named by text, not {name!r}")
            if not isinstance(structure, Trial):
                raise ValueError(f"structure {name!r} is a Trial, not {type(structure).__name__}")
        if self.default not in self.structures:
            raise ValueError(
                f"the task's default structure {self.default!r} is not one of its structures "
                f"({', '.join(self.structures)})"
            )
        if self.reaction_time is not None and not isinstance(self.reaction_time, ReactionTime):
            raise ValueError("a task's reaction_time is a ReactionTime")
        if self.choice is not None and not isinstance(self.choice, (Choice, NoChoice)):
            raise ValueError("a task's choice is a Choice, or NO_CHOICE when it offers none")
        if not isinstance(self.meanings, dict):
            raise ValueError("a task's meanings are a dict of setting names to Meanings")
        for name, meaning in self.meanings.items():
            if not isinstance(name, str) or not isinstance(meaning, Meaning):
                raise ValueError(
                    f"a task's meanings name a setting by text and give it a Meaning; {name!r} "
                    f"does not"
                )
        if not isinstance(self.needs_fixed_head, bool):
            raise ValueError("a task's needs_fixed_head is True or False")
        if not isinstance(self.plans, dict):
            raise ValueError("a task's plans are a dict of plan names to Plans")
        for name, plan in self.plans.items():
            if not isinstance(name, str) or not name:
                raise ValueError(f"a plan is named by text, not {name!r}")
            if not isinstance(plan, Plan):
                raise ValueError(f"plan {name!r} is a Plan, not {type(plan).__name__}")

    @property
    def trial(self) -> Trial:
        """The default structure: what the plain run plays, and a condition naming none."""
        return self.structures[self.default]

    @property
    def view(self) -> str:
        """The setup the task is written for: its structures' one view (`check_task` refuses
        structures that differ)."""
        return self.trial.view

    @property
    def params(self) -> "list[Param]":
        """The union of its structures' declared parameters (engine spec §3.5), the default
        structure's first, each name once: what `Session.set` validates against and a run's
        values are held to. A name two structures declare differently is refused at load
        (`check_task`); here the first declaration stands."""
        union: dict[str, Param] = {}
        for name in (self.default, *(other for other in self.structures if other != self.default)):
            for param in self.structures[name].params:
                union.setdefault(param.name, param)
        return list(union.values())
