"""The trial loop: the framework executing a task's declarative data.

This is the loop S1 §5.1 keeps out of task files. A task declares states and
guarded transitions; this runs them, frame by frame, and asks a `World` whether
each non-temporal guard is satisfied. On a rig the world is hardware; in a
simulated session it is a behaviour agent; in demo mode it is a mouse and keyboard.
**They are peers** (S6 §6) -- the loop cannot tell them apart, which is what makes
a simulated session evidence about the real one.

`After` is the one guard the loop evaluates itself, from elapsed frames, because
time is the loop's own property rather than something the world reports.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Callable, Mapping, NamedTuple, NoReturn, Protocol

from wl_xcon.task import (
    Action,
    After,
    Entered,
    Exited,
    Guard,
    Hide,
    Hold,
    Mark,
    Onscreen,
    Outcome,
    P,
    Reward,
    Score,
    Show,
    Stimulus,
    Tolerances,
    Trial,
    Update,
    expand_windows,
    placements,
)


class World(Protocol):
    """Whatever supplies the signals a guard asks about.

    **Two primitives, and the split is what makes worlds interchangeable.** A world
    reports where gaze is (`in_window`) and whether a discrete event occurred
    (`happened`). It does *not* decide what entering, leaving or holding mean --
    the loop derives those from membership, so those semantics, including the
    staleness policy S5 §4.1 requires, exist exactly once.

    If each world implemented them, the simulator and a mouse would disagree about
    what a hold is, and a person validating a task in demo mode would be validating
    different behaviour from the one the animal gets.
    """

    def in_window(self, window: str, frame: int, eye: str = "both") -> bool:
        """Is gaze inside `window`, for the eye the window declares?

        `eye` is `"both"` for an ordinary conjugate criterion, or `"left"`/`"right"`
        when a window scores one eye. The tracker is binocular, so this is a real
        primitive; and on a stereoscope it is the *correct* one, because under
        dichoptic presentation the non-viewing eye deviates to its phoria rather than
        following the stimulus, and a conjugate estimate averages one eye doing the task
        with one eye not looking at the stimulus (S1a §12).
        """

    def happened(self, guard: Guard, state: str, frame: int) -> bool: ...

    def signal(self, frame: int) -> str:
        """The state of the gaze signal: `"ok"`, `"blink"` or `"lost"`.

        Told apart because they are different events with the same appearance in the
        data -- a blink is the animal, tracker loss is the rig -- and scoring both as
        fixation breaks inflates a session's break rate with equipment failure,
        invisibly.
        """
        return "ok"

    def display(self, visible: Mapping[str, Stimulus], frame: int) -> None:
        """What is on the screen this frame.

        Called every frame, before the frame's guards are evaluated, with the
        stimuli a real display would be showing at that moment. On a rig this is
        what draws; in a simulated session it is what the subject can respond to.

        **Without it the display was not modelled anywhere**, so every check
        inspected the transition graph and none could see that a task was holding
        fixation on a point it had taken down.
        """


class Effects(Protocol):
    """What a trial *does*, as against what a `World` tells it.

    Deliberately not part of `World`. A world answers questions -- where gaze is,
    whether an event happened -- and a task's actions answer none: they strobe a code
    onto the recording clock and open a valve. Folding them together would let a
    world implementation report signals *and* deliver fluid, and the simulator would
    then be one edit away from being able to reward an animal.

    Two methods, matching the two actions the vocabulary has that leave the machine.
    `Score` stays the loop's, because it changes no state outside the trial.
    """

    def mark(self, code: int) -> None:
        """Strobe an event code. **Now, not on the next flip** -- see `_emit`."""

    def reward(self, ref: str) -> None:
        """Deliver the reward the bounded config calls `ref`.

        By name, because the task named a *configuration entry* and never a
        magnitude (S8 §4). Whatever implements this is what asks the ceiling.
        """


@dataclass(frozen=True, slots=True)
class Unwired:
    """No I/O. **Refuses, rather than dropping the action.**

    The default, and the reason it is the default: for five days `_apply` executed
    the display actions and silently discarded `Mark` and `Reward`, so the M1 gate
    ran a thousand trials, strobed no codes and delivered no fluid, and every test
    passed. A dropped action is invisible in exactly the two records that would show
    it -- the recording has no codes to be missing from, and the animal cannot say.
    """

    def _refuse(self, what: str) -> None:
        raise RuntimeError(
            f"a task commanded {what} and no I/O is wired to this trial; the loop "
            f"refuses rather than discarding it. Pass effects=Recorded() for a test, "
            f"or the session's own port for a run"
        )

    def mark(self, code: int) -> None:
        self._refuse(f"event code {code}")

    def reward(self, ref: str) -> None:
        self._refuse(f"reward {ref!r}")


@dataclass
class Recorded:
    """Marks and rewards in the order they left the loop.

    `log` keeps the order for `dio.Simulated`'s reason: the order *is* the contract.
    A `REWARD_COMMANDED` code trailing its own delivery describes a different
    sequence of events from the one that happened.
    """

    log: list = field(default_factory=list)

    def mark(self, code: int) -> None:
        self.log.append(("mark", code))

    def reward(self, ref: str) -> None:
        self.log.append(("reward", ref))


@dataclass(frozen=True, slots=True)
class Quiet:
    """A world where nothing ever happens.

    Useful on its own: it proves a trial terminates on its time bounds alone,
    which is the property S1 §9 check 4 exists to make true.
    """

    def in_window(self, window: str, frame: int, eye: str = "both") -> bool:
        return False

    def happened(self, guard: Guard, state: str, frame: int) -> bool:
        return False

    def signal(self, frame: int) -> str:
        return "ok"

    def display(self, visible: Mapping[str, Stimulus], frame: int) -> None:
        return None


@dataclass(frozen=True, slots=True)
class Scripted:
    """A world where named guards fire on given frames.

    Deterministic, so a test can assert a frame count rather than a distribution.
    Frames are counted from the start of the trial, not of the state, because a
    script describes what the animal did and the animal does not know about states.
    """

    at_frame: dict[Guard, int]
    #: Which window gaze occupies on each frame. Membership rather than events,
    #: because entering, leaving and holding are the loop's to derive.
    inside: dict[int, str] = field(default_factory=dict)

    def in_window(self, window: str, frame: int, eye: str = "both") -> bool:
        return self.inside.get(frame) == window

    def happened(self, guard: Guard, state: str, frame: int) -> bool:
        return self.at_frame.get(guard) == frame

    def signal(self, frame: int) -> str:
        return "ok"

    def display(self, visible: Mapping[str, Stimulus], frame: int) -> None:
        return None


class Shown(NamedTuple):
    """One stimulus's time on the display.

    `on` is the first frame it was visible and `off` the first frame it was not,
    so a duration is a subtraction and a presentation still up when the trial ended
    has `off is None`. Half-open because the alternative -- last-visible-frame --
    makes every duration an off-by-one waiting to be reported as a result.
    """

    name: str
    on: int
    off: int | None


class Confirmed(NamedTuple):
    """A photodiode reporting a stimulus actually reached the display.

    The realized onset, against which a declared one can be compared. Without it the
    record says what was asked for and nothing about what happened -- and the two
    differ by exactly the amount `After(since=...)` exists to expose.
    """

    patch: str
    frame: int


class Changed(NamedTuple):
    """An `Update` taking effect: which stimulus, and the first frame it differed."""

    name: str
    frame: int


class Placed(NamedTuple):
    """A stimulus as a `Show` put it on the display or an `Update` left it, and the first frame
    it was so (XC-399): what the record turns into where it was, after the trial
    (`record.SessionRecord.trial`), never in a frame. The stimulus as given, its parameters
    unbound: a reference, kept, never copied. **With what reads it as a timeline** (the review of
    XC-399, I3): which action made it, the fields an `Update` set, its presentation, and when that
    presentation went off."""

    stimulus: Stimulus
    frame: int
    #: `"show"` or `"update"`.
    kind: str
    #: The fields an `Update` set, as `Update.changes()` names them, in its order; `()` for a
    #: `Show`.
    changed: tuple[str, ...]
    #: Its presentation: its index in `Result.shown`, the `Show` it belongs to.
    presentation: int
    #: The first frame its presentation was off the display, after a `Hide`, or `None` when it was
    #: on through the trial's last frame -- set as the trial returns (`_drawn`).
    off: int | None = None


@dataclass(frozen=True, slots=True)
class Scored:
    """One scored response inside a trial: what, where, and when."""

    window: str
    scored_as: Outcome
    frame: int


@dataclass(frozen=True, slots=True)
class Result:
    outcome: Outcome | None
    frames: int
    #: Every state this trial entered, in order. A census over many trials turns
    #: this into starvation detection: a state no trial ever entered is either
    #: unreachable in practice or gated on behaviour the animal never produces,
    #: and the static checks cannot tell the difference.
    visited: tuple[str, ...] = ()
    #: Scored responses in the order they happened. Empty for a task that scores
    #: only at the end, which is most of them.
    scored: tuple[Scored, ...] = ()
    #: What was on the display and when. This is the realized timeline, not the
    #: declared one: comparing the two is how a task whose stimulus was up for a
    #: different duration than its author wrote gets caught.
    shown: tuple[Shown, ...] = ()
    #: Every `Update` that took effect, in order.
    changed: tuple[Changed, ...] = ()
    #: Photodiode confirmations, in order: the display as the world reported it.
    confirmed: tuple[Confirmed, ...] = ()
    #: Every `Show` and every `Update` on the screen for a frame or more of the trial, in the order
    #: they did, each with the stimulus as it was drawn from its frame, which action made it and
    #: when its presentation went off (XC-399, `_drawn`): where each stimulus was, which `shown`
    #: and `changed` name but do not say.
    placed: tuple[Placed, ...] = ()


def _resolve(value: float | P, values: dict[str, float]) -> float:
    """A parameter reference against this trial's bound values.

    **Missing is an error, never a default.** A timeout that silently became 0.0
    would abort every trial immediately -- and that reads as an animal who will not
    work, not as a bug, which is the most expensive way for this to fail.

    **On the trial loop's path** (every `After` and `Hold` a frame evaluates), so the refusal's
    message is built by `_unbound`, as it raises (XC-414).
    """
    if isinstance(value, P):
        if value.name not in values:
            _unbound(value.name)
        return values[value.name]
    return value


def _unbound(name: str) -> NoReturn:
    """`_resolve`'s refusal, its message built as it is raised, never on a frame that resolves."""
    raise KeyError(
        f"no value bound for parameter {name!r}; a trial runs against "
        f"a resolved parameter set, not a partially resolved one"
    )


def _apply(
    actions: "list[Action]",
    visible: "dict[str, Stimulus]",
    shown: "list[Shown]",
    open_at: "dict[str, int]",
    changed: "list[Changed]",
    placed: "list[Placed]",
    frame: int,
) -> None:
    """Execute the display actions among `actions`, effective from `frame`.

    **A display action decided while processing frame N takes effect on frame N+1.**
    The loop chooses during a frame what the *next* flip will carry; recording it as
    though it were already visible would build the one-frame lie into every realized
    duration this system reports, and reporting durations honestly is most of why it
    exists.

    **Each `Show` and `Update` keeps the stimulus it drew** (`placed`, XC-399), a reference
    beside the name `shown` and `changed` keep, at the same transitions: nothing is resolved
    here, and the record says where it was after the trial.

    Non-display actions are not this function's business: `Score` is the loop's and
    `Mark` and `Reward` are `_emit`'s, on a different clock -- see there.

    **On the frame an edge is taken** (`_Loop._take`), so it builds the records it keeps and the
    stimulus an `Update` leaves, and nothing else (XC-414): the actions are walked by index, and a
    refusal's message is built by `_refused`, as it raises.
    """
    index = 0
    while index < len(actions):
        action = actions[index]
        index += 1
        if isinstance(action, Show):
            name = action.stimulus.name
            if name in visible:
                _refused(name, "is already on the display; two live stimuli under one name would "
                               "make Hide and Update ambiguous")
            visible[name] = action.stimulus
            open_at[name] = len(shown)
            shown.append(Shown(name, frame, None))
            placed.append(Placed(action.stimulus, frame, "show", (), open_at[name]))
        elif isinstance(action, Hide):
            if action.stimulus not in visible:
                _refused(action.stimulus, "is not on the display, so it cannot be hidden")
            del visible[action.stimulus]
            at = open_at.pop(action.stimulus)
            was = shown[at]
            shown[at] = Shown(was.name, was.on, frame)
        elif isinstance(action, Update):
            if action.stimulus not in visible:
                _refused(action.stimulus, "is not on the display, so it cannot be updated")
            changes = action.changes()
            visible[action.stimulus] = replace(visible[action.stimulus], **changes)
            changed.append(Changed(action.stimulus, frame))
            placed.append(Placed(visible[action.stimulus], frame, "update", tuple(changes),
                                 open_at[action.stimulus]))


def _refused(name: str, why: str) -> NoReturn:
    """`_apply`'s refusal of an action, its message built as it is raised."""
    raise ValueError(f"stimulus {name!r} {why}")


def _drawn(placed: "list[Placed]", shown: "list[Shown]", last: int) -> "tuple[Placed, ...]":
    """What the trial drew, as it returns -- once, never in a frame (XC-399): each placement that
    took effect by its last frame, with the first frame its presentation was off. **A `Show` or
    `Update` on an edge to an outcome** takes effect on the frame after the last, so it was never
    on the screen and is left out (the review's I2); **a `Hide` there** leaves its presentation on
    through the last frame, so its `off` is `None`, as a presentation still up at the end. **A
    placement its presentation's `Hide` took effect with** -- a `Show` and a `Hide`, or an `Update`
    and a `Hide`, on one transition -- was on the screen for no frame, and is left out too (the
    re-review's minor 2). A `Show` and an `Update` on one frame stay two placements: the first was
    so for no frame, which the `Update` at its frame says."""
    kept = []
    for place in placed:
        if place.frame > last:
            continue
        off = shown[place.presentation].off
        if off is not None and off <= place.frame:
            continue
        kept.append(place._replace(off=off if off is not None and off <= last else None))
    return tuple(kept)


def _emit(actions: "list[Action]", effects: "Effects") -> None:
    """Execute the actions that leave the machine, **on this frame, not the next**.

    The one-frame rule `_apply` follows is a fact about a display: what the loop
    decides during frame N is carried by the flip that ends it. It is not a fact
    about a digital line. A strobe written while frame N is processed is on the wire
    during frame N, so recording it as N+1 would be a lie in the opposite direction
    from the one `_apply` exists to prevent.

    That the two differ is not a wrinkle to smooth over -- it is the gap the
    photodiode measures and `After(since=Onscreen(...))` exposes. `FIX_ON` strobed at
    N with the point visible at N+1 is what actually happens, and a system reporting
    them as simultaneous would be hiding its own display latency inside its own
    event stream.

    On the frame an edge is taken, so the actions are walked by index (XC-414).
    """
    index = 0
    while index < len(actions):
        action = actions[index]
        index += 1
        if isinstance(action, Mark):
            effects.mark(action.code)
        elif isinstance(action, Reward):
            effects.reward(action.ref.name)


#: **The longest trial** (engine spec §6.8), in seconds: a trial that reaches it without an
#: outcome ends there as a hang (`Result.outcome` `None`), which `taskd` records as `hang` and
#: counts as a missed acquisition (`task.HANG_COUNTS_AS`; the PI, 2026-10-11, XC-287). Five
#: minutes; longer presentations are the continuous mode's (§13.6).
LONGEST_TRIAL_S = 300.0


def longest_trial_frames(frame_period: float) -> int:
    """`LONGEST_TRIAL_S` in whole frames at `frame_period` (engine spec §6.8: "the loop's frame cap
    derived from 300 s at the session's rate"), to the nearest frame: 72,000 at 240 Hz and 36,000
    at 120 Hz."""
    return round(LONGEST_TRIAL_S / frame_period)


def run_trial(
    trial: Trial,
    world: World,
    frame_period: float,
    max_frames: int | None = None,
    values: dict[str, float] | None = None,
    effects: "Effects | None" = None,
    each_frame: "Callable[[int], None] | None" = None,
) -> Result:
    """Run one trial to its outcome.

    **`max_frames` is the longest trial** (engine spec §6.8), `longest_trial_frames` at this
    frame period unless a caller gives its own: five minutes at the session's rate, where the
    100,000 frames it was until engine build C2a were about 417 s at 240 Hz. A well-formed task
    reaches it only through a state declared `unbounded=True` -- check 4 proves every other wait
    bounded -- or a bound longer than five minutes, or a chain of bounded states, or a cycle among
    them, whose waits add up to more; the trial then ends with no outcome, a hang.

    `effects` is where marks and rewards go. It defaults to `Unwired`, which refuses:
    a task that commands neither never touches it, and one that does may not have the
    command quietly dropped.

    **`each_frame`, the loop's one per-frame hook** (P4d-2b spec §5.1): called with
    the frame's number first thing on every frame -- before the display, before any
    guard, and on a frame the gaze signal was lost -- so what it does happens in the
    frame it names. `taskd.Session` passes its mark check, which strobes an
    operator's mark in the frame it arrives. **Hot path**: whatever is passed must
    not block, log or allocate when there is nothing to do; this loop does not check.
    """
    if max_frames is None:
        max_frames = longest_trial_frames(frame_period)
    loop = _Loop(trial, world, frame_period, values, effects, each_frame)
    # Frames counted, not iterated: this runs every frame of the trial, so its own code builds
    # nothing either (XC-414), and anything a frame builds is `_Loop.frame`'s, where it is measured.
    frame = 1
    while frame <= max_frames:
        if loop.frame(frame):
            return loop.result(loop.ended_as, frame)
        frame += 1
    return loop.result(None, max_frames)


class _Loop:
    """**One trial's loop**: what `run_trial` builds before the trial's first frame, and `frame`,
    one frame of it -- a function of its own so that a frame is what can be measured
    (`tests/test_gaze.py`, XC-414).

    **A frame builds nothing** (CLAUDE.md: "Inside trial loops: no allocation"). Every container a
    frame writes is built here, between trials, holding every key it ever will -- the membership of
    each window the world is asked about, whether each window a guard names is inside, the frame
    each hold began (`None` for none running), the frame each `since` clock started (`None` until
    it does) -- and a frame overwrites values. The windows' insides are two dicts the frames take in
    turn, this frame's becoming the next one's previous, as a fresh dict a frame used to be. Every
    walk is by index, so not even an iterator is made. **An edge taken is `_take`'s**, which builds
    the trial's record of it (`_apply`): never called on a frame that takes none. The trial's
    `Result` is built as it returns (`result`), after its last frame.
    """

    def __init__(
        self,
        trial: Trial,
        world: World,
        frame_period: float,
        values: "dict[str, float] | None",
        effects: "Effects | None",
        each_frame: "Callable[[int], None] | None",
    ) -> None:
        self.world = world
        self.frame_period = frame_period
        self.effects = Unwired() if effects is None else effects
        self.each_frame = each_frame
        #: The values a frame resolves against: the trial's own, read as a frame reads them
        #: (`values or ...`), or this, one empty dict for the trial rather than a new one a frame.
        self.values = values
        self.no_values: dict[str, float] = {}
        bound = values or self.no_values
        self.by_name = {state.name: state for state in trial.states}
        self.current = self.by_name[trial.start]
        self.entered_at = 0
        self.visited = [self.current.name]
        self.scored: list[Scored] = []
        #: Window membership on the previous frame, so entering and leaving are edges
        #: rather than states, and the frame a hold began, so leaving restarts it.
        tracked = {
            guard.window
            for state in trial.states
            for edge in state.go
            if isinstance(edge.guard, (Entered, Exited, Hold))
            for guard in (edge.guard,)
        }
        # An array's windows do not exist until `n` is bound, so aliases -- `<of>.target`
        # and `<of>.distractor` -- are resolved here against this trial's values. A
        # saccade guard reaches the world directly, which judges an alias by the objects it
        # names itself (`gaze.Tracked.happened`); membership is derived by the loop, so an
        # unresolved alias is simply never satisfied and the animal fixates the target while
        # the task waits forever.
        declared, aliases = expand_windows(trial, bound)
        # Which eye each window scores. A window that declares one and is asked about
        # the conjugate estimate is a criterion nobody applied.
        eyes = {window.name: window.eye for window in declared}
        asked = {
            name: aliases.get(name, (name,))
            for name in tracked
        }
        tracked = {concrete for names in asked.values() for concrete in names}
        # **And an array's aliases follow it** (XC-402): an `Update` can change its set size or its
        # target, and with them which objects `<of>.target` and `<of>.distractor` name. Every
        # placement the array can be drawn in is built now (`task.placements`), each with what it
        # makes of the aliases a guard here asks; the frame loop switches `asked` to the one on the
        # display, as `gaze.Tracked` switches the windows. Every object any of them can name is
        # asked of the world every frame -- one with no window where the array is drawn is outside
        # it -- and every window any of them builds has its eye.
        arrays = []
        for of, options in placements(trial, bound).items():
            switches = []
            for placement in options:
                members = {alias: concretes for alias, concretes in placement.members.items()
                           if alias in asked}
                switches.append((placement, members))
                tracked.update(concrete for concretes in members.values() for concrete in concretes)
                for name, window in placement.windows.items():
                    if window is not None:
                        eyes.setdefault(name, window.eye)
            if any(members for _, members in switches):
                arrays.append((of, tuple(switches)))
        self.arrays = tuple(arrays)
        self.drawn: dict[str, object] = {of: None for of, _ in arrays}
        self.asked = asked
        #: Each name a guard asks about, in `asked`'s order; each window the world is asked about,
        #: in the order the frames have always asked (the set's), with the eye it scores.
        self.names = tuple(asked)
        self.concretes = tuple(tracked)
        self.concrete_eyes = tuple(eyes.get(name, "both") for name in self.concretes)
        self.membership: dict[str, bool] = dict.fromkeys(self.concretes, False)
        self.was_inside: dict[str, bool] = dict.fromkeys(asked, False)
        self.inside_now: dict[str, bool] = dict.fromkeys(asked, False)
        self.holding_since: "dict[str, int | None]" = dict.fromkeys(asked)

        #: When each `since` guard fired, per state entry. Reset on every transition,
        #: because a clock started in one state saying something about a later one is
        #: the same defect as a hold clocked from the wrong zero. Every `since` the trial's
        #: edges have is a key from the start, `None` until its clock starts.
        self.clocks = tuple(dict.fromkeys(
            since
            for state in trial.states
            for edge in state.go
            if (since := getattr(edge.guard, "since", None)) is not None
        ))
        self.started_at: "dict[Guard, int | None]" = dict.fromkeys(self.clocks)
        self.confirmed: list[Confirmed] = []
        self.visible: dict[str, Stimulus] = {}
        self.shown: list[Shown] = []
        self.open_at: dict[str, int] = {}
        self.changed: list[Changed] = []
        self.placed: list[Placed] = []
        # The display. The start state's entry actions run before the loop, so what
        # they put up is visible on frame 1 -- the same one-frame rule every other
        # entry action follows, counted from a notional frame 0.
        _apply(self.current.enter, self.visible, self.shown, self.open_at, self.changed,
               self.placed, 1)
        _emit(self.current.enter, self.effects)

        # Two independent graces, in frames. `None` is enforcement switched off.
        def _grace(value) -> "int | None":
            if value is None:
                return None
            return _resolve(value, bound) / frame_period

        self.graces = {
            "blink": (_grace(trial.tolerances.blink), Outcome.BLINK_BREAK),
            "lost": (_grace(trial.tolerances.tracker_lost), Outcome.TRACKER_LOST),
        }
        self.interrupted_for = 0
        self.interruption = "ok"
        #: How the trial ended, once `frame` says it has.
        self.ended_as: Outcome | None = None

    def frame(self, frame: int) -> bool:
        """Run frame `frame`; `True` when the trial ended on it, how in `ended_as`."""
        if self.each_frame is not None:
            self.each_frame(frame)
        world = self.world
        visible = self.visible
        world.display(visible, frame)
        # The aliases of what this frame draws (XC-402), on the frame the world's windows switch:
        # one identity test per array that has aliases asked, and a switch overwrites keys `asked`
        # already has.
        arrays = self.arrays
        index = 0
        while index < len(arrays):
            of, switches = arrays[index]
            index += 1
            stimulus = visible.get(of)
            if stimulus is None or stimulus is self.drawn[of]:
                continue
            self.drawn[of] = stimulus
            option = 0
            while option < len(switches):
                placement, members = switches[option]
                option += 1
                if placement.draws(stimulus):
                    self.asked.update(members)
                    break
        frame_period = self.frame_period
        elapsed = (frame - self.entered_at) * frame_period
        bound = self.values or self.no_values
        holding = self.holding_since
        names = self.names

        # The gaze signal, before anything reads membership. An interruption within
        # its grace **freezes** the trial's view of gaze rather than lapsing it: the
        # blind frames are not counted toward a hold, so a hold spanning a forgiven
        # stall completes later than an uninterrupted one. Counting them would report
        # a hold nobody observed (S5 4.1); restarting would punish the animal for the
        # camera.
        state_of_signal = world.signal(frame)
        if state_of_signal == "ok":
            self.interrupted_for = 0
            self.interruption = "ok"
        else:
            self.interrupted_for = (
                self.interrupted_for + 1 if self.interruption == state_of_signal else 1
            )
            self.interruption = state_of_signal
            allowed, ends_as = self.graces.get(state_of_signal, (None, None))
            if allowed is not None and self.interrupted_for > allowed:
                self.ended_as = ends_as
                return True
            # Frozen: hold clocks do not advance and no edges are derived.
            index = 0
            while index < len(names):
                since = holding[names[index]]
                if since is not None:
                    holding[names[index]] = since + 1
                index += 1
            return False

        # Membership first, once per frame: entering and leaving are edges against
        # the previous frame, and a hold that lapses restarts rather than pausing.
        membership = self.membership
        concretes = self.concretes
        concrete_eyes = self.concrete_eyes
        index = 0
        while index < len(concretes):
            membership[concretes[index]] = world.in_window(concretes[index], frame,
                                                           concrete_eyes[index])
            index += 1
        inside_now = self.inside_now
        asked = self.asked
        index = 0
        while index < len(names):
            name = names[index]
            index += 1
            members = asked[name]
            inside = False
            member = 0
            while member < len(members):
                if membership[members[member]]:
                    inside = True
                    break
                member += 1
            inside_now[name] = inside
            if not inside:
                holding[name] = None
            elif holding[name] is None:
                holding[name] = frame

        # Arm any `since` clocks this frame, before the guards that read them, so a
        # zero-length interval fires on the frame the photodiode reports rather than
        # one frame later.
        current = self.current
        go = current.go
        started_at = self.started_at
        index = 0
        while index < len(go):
            since = getattr(go[index].guard, "since", None)
            index += 1
            if since is not None and started_at.get(since) is None:
                if world.happened(since, current.name, frame):
                    started_at[since] = frame
                    if isinstance(since, Onscreen):
                        self.confirmed.append(Confirmed(since.patch, frame))

        was_inside = self.was_inside
        index = 0
        while index < len(go):
            edge = go[index]
            index += 1
            guard = edge.guard
            if isinstance(guard, After):
                if guard.since is None:
                    fired = elapsed >= _resolve(guard.seconds, bound)
                else:
                    began = started_at.get(guard.since)
                    fired = began is not None and (
                        (frame - began) * frame_period
                        >= _resolve(guard.seconds, bound)
                    )
            elif isinstance(guard, Entered):
                fired = inside_now[guard.window] and not was_inside[guard.window]
            elif isinstance(guard, Exited):
                fired = was_inside[guard.window] and not inside_now[guard.window]
            elif isinstance(guard, Hold):
                # The entry frame counts: gaze inside on frames 2, 3 and 4 is
                # 30 ms of hold at a 10 ms frame, completing on frame 4. Counting
                # from the frame *after* entry would make every hold one frame
                # longer than declared, which at 240 Hz is invisible and at 60 Hz
                # is 17 ms of unasked-for fixation.
                since = holding.get(guard.window)
                fired = since is not None and (
                    (frame - since + 1) * frame_period >= _resolve(guard.seconds, bound)
                )
            else:
                fired = world.happened(guard, current.name, frame)
            if not fired:
                continue
            if self._take(edge, frame):
                return True
            break
        # This frame's insides are the next frame's previous ones, and the previous frame's
        # dict is the one the next frame writes.
        self.was_inside, self.inside_now = inside_now, was_inside
        return False

    def _take(self, edge, frame: int) -> bool:
        """The edge `edge`, taken on `frame`: its scored responses, its actions, and the state it
        enters or the outcome it ends the trial with (`True`). **The trial's record of it is built
        here** (`Scored`, and `_apply`'s), on a frame that takes an edge only."""
        do = edge.do
        index = 0
        while index < len(do):
            action = do[index]
            index += 1
            if isinstance(action, Score):
                self.scored.append(Scored(action.window, action.scored_as, frame))
        if isinstance(edge.to, Outcome):
            _apply(do, self.visible, self.shown, self.open_at, self.changed, self.placed,
                   frame + 1)
            _emit(do, self.effects)
            self.ended_as = edge.to
            return True
        self.current = current = self.by_name[edge.to]
        self.entered_at = frame
        _apply(do, self.visible, self.shown, self.open_at, self.changed, self.placed, frame + 1)
        _emit(do, self.effects)
        _apply(current.enter, self.visible, self.shown, self.open_at, self.changed, self.placed,
               frame + 1)
        _emit(current.enter, self.effects)
        # **Entering a state clears every hold.** A hold declared in a state
        # means held continuously *since that state began*. Carrying the window's
        # own entry frame across a transition let a later state's hold be
        # satisfied by presence that began before it -- a memory-guided structure
        # with a declared 0.3 s delay ran that delay for **one frame** and scored
        # CORRECT, with the task written correctly and every load-time check
        # passing. Found by review 2026-08-31; every working-memory delay in the
        # v1 inventory is written this way.
        holding = self.holding_since
        names = self.names
        index = 0
        while index < len(names):
            holding[names[index]] = None
            index += 1
        started_at = self.started_at
        clocks = self.clocks
        index = 0
        while index < len(clocks):
            started_at[clocks[index]] = None
            index += 1
        self.visited.append(current.name)
        return False

    def result(self, outcome: "Outcome | None", last: int) -> Result:
        """The trial's `Result`, ended `outcome` on frame `last` -- built once, as it returns."""
        return Result(
            outcome,
            last,
            tuple(self.visited),
            tuple(self.scored),
            tuple(self.shown),
            tuple(self.changed),
            tuple(self.confirmed),
            _drawn(self.placed, self.shown, last),
        )
