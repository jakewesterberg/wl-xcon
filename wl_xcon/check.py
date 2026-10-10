"""Load-time checks (S1 §9). A task failing any of these is refused at load."""

from __future__ import annotations

import dataclasses
import itertools
import math

from wl_xcon.codes import PROVISIONAL, Allocation
from wl_xcon.components import Registry
from wl_xcon.findings import NOT_RECORDING, SESSION_KINDS, Finding
from wl_xcon.geometry import VIEWS, Geometry
from wl_xcon.photometry import (
    CONE_COLORS,
    D65,
    DKL,
    Calibration,
    Color,
    ConeContrast,
    Gray,
    unrealizable,
    xyY,
)
from wl_xcon.task import (
    RDS,
    After,
    Array,
    ItemWindows,
    Custom,
    Entered,
    Exited,
    Hide,
    Hold,
    Mark,
    Outcome,
    P,
    Param,
    Remembered,
    SaccadeTo,
    Show,
    Stimulus,
    Touched,
    Trial,
    Unchanged,
    Update,
    Window,
    actions_of,
    arrays_of,
)


def check(
    trial: Trial,
    allocation: Allocation = PROVISIONAL,
    components: Registry | None = None,
    geometry: Geometry | None = None,
    calibration: Calibration | None = None,
) -> list[Finding]:
    return (
        _unreachable_states(trial)
        + _unbounded_waits(trial)
        + _states_with_no_outcome_path(trial)
        + _shadowed_transitions(trial)
        + _unallocated_codes(trial, allocation)
        + _undeclared_parameters(trial)
        + _custom_components(trial, components or Registry())
        + _offscreen_stimuli(trial, geometry)
        + _unallocated_outcomes(trial, allocation)
        + _undeclared_windows(trial)
        + _uncoupled_windows(trial)
        + _display_faults(trial)
        + _color_faults(trial, calibration)
        + _light_faults(trial)
        + _block_faults(trial)
        + _array_faults(trial)
        + _stereogram_faults(trial)
        + _eye_faults(trial)
        + _overlapping_windows(trial)
        + _unreachable_timeouts(trial)
        + _crowded_arrays(trial)
        + _view_faults(trial, geometry)
        + _placement_faults(trial)
        + _trial_display_faults(trial)
    )


def _unreachable_states(trial: Trial) -> list[Finding]:
    """S1 §9 check 2: every state is reachable from the start state."""
    by_name = {state.name: state for state in trial.states}
    seen: set[str] = set()
    frontier = [trial.start]
    while frontier:
        name = frontier.pop()
        if name in seen or name not in by_name:
            continue
        seen.add(name)
        frontier.extend(
            edge.to for edge in by_name[name].go if isinstance(edge.to, str)
        )
    return [
        Finding("unreachable-state", f"no transition reaches {name!r}")
        for name in (s.name for s in trial.states)
        if name not in seen
    ]


def _unbounded_waits(trial: Trial) -> list[Finding]:
    """S1 §9 check 4: every wait has a time bound, or says it has none.

    The S1 bake-off produced exactly this defect while writing the permissive
    form of a fixation task -- a hold loop with no timeout, invisible on reading.
    A state whose transitions are all event-guarded can wait forever if the event
    never arrives, which for a fixation hold means an animal that has looked away.

    **An `After` with a `since` does not count.** Its clock is started by an event --
    a photodiode confirmation -- so if the flip is dropped or the patch occluded it
    never arms, and a state relying on it alone waits forever while looking bounded
    on the page. That is the same defect this check exists to catch, wearing the
    type that normally satisfies it.
    """
    return [
        Finding(
            "unbounded-wait",
            f"state {state.name!r} has no unconditional `After` transition and does "
            f"not declare `unbounded=True`"
            + (
                " -- an `After` with a `since` is started by an event, so it is not "
                "a bound"
                if any(
                    isinstance(edge.guard, After) and edge.guard.since is not None
                    for edge in state.go
                )
                else ""
            ),
        )
        for state in trial.states
        if not state.unbounded
        and not any(
            isinstance(edge.guard, After) and edge.guard.since is None
            for edge in state.go
        )
    ]


def _states_with_no_outcome_path(trial: Trial) -> list[Finding]:
    """S1 §9 check 3: from every state, some path reaches a terminal outcome.

    Reachability run backwards. A state that cannot reach an outcome is a trap:
    the trial never scores, never ends, and never says why -- it simply stops
    producing trials while the console still shows a session running.
    """
    by_name = {state.name: state for state in trial.states}
    escapes: set[str] = set()
    changed = True
    while changed:
        changed = False
        for state in trial.states:
            if state.name in escapes:
                continue
            if any(
                isinstance(edge.to, Outcome) or edge.to in escapes
                for edge in state.go
            ):
                escapes.add(state.name)
                changed = True
    return [
        Finding(
            "no-outcome-path",
            f"state {name!r} cannot reach any terminal outcome",
        )
        for name in by_name
        if name not in escapes
    ]


def _shadowed_transitions(trial: Trial) -> list[Finding]:
    """S1 §9 check 10, in the form it takes once order is defined.

    The check was written as "no two transitions can fire on the same frame
    without a declared priority." Transitions now fire in **declared order**
    (M0 §4), which resolves the ambiguity that phrasing was worried about --
    so what is left to detect is the decidable half: a guard repeated on one
    state means every later copy is unreachable.

    That is dead code rather than a race, and it is a shape a generated task
    produces readily, since repeating a guard with a different destination looks
    entirely reasonable in isolation.
    """
    findings: list[Finding] = []
    for state in trial.states:
        seen: set[object] = set()
        for edge in state.go:
            if edge.guard in seen:
                findings.append(
                    Finding(
                        "shadowed-transition",
                        f"state {state.name!r} repeats guard {edge.guard!r}; "
                        f"the later transition can never fire",
                    )
                )
            seen.add(edge.guard)
    return findings


def _unallocated_codes(trial: Trial, allocation: Allocation) -> list[Finding]:
    """S1 §9 check 1: every event code a task names exists in the allocation.

    The cheapest guardrail in the design against a model-authored task (P15), and
    the one that fails loudest. A model asked for a stimulus-onset code will emit a
    plausible number; nothing about 4097 looks wrong on the page, and the recording
    it produces carries timing with no meaning. The allocation is the only thing
    that knows.

    Refused at **load** rather than at run: the point is to catch it before an
    animal is in the chair, not when the first trial strobes.
    """
    return [
        Finding(
            "unallocated-code",
            f"state {name!r} emits code {action.code}, which is not in the "
            f"allocation; codes are allocated in wl-exptasks, never invented in a task",
        )
        for name, action in actions_of(trial)
        if isinstance(action, Mark) and action.code not in allocation
    ]


def _iter_param_refs(value: object) -> list[P]:
    """Every parameter reference anywhere inside a value.

    Walks dataclass fields generically rather than knowing the guard and action
    vocabularies, so a new vocabulary member is covered by this check the day it
    is added rather than the day someone remembers to update a list here.
    """
    if isinstance(value, P):
        return [value]
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        found: list[P] = []
        for f in dataclasses.fields(value):
            found.extend(_iter_param_refs(getattr(value, f.name)))
        return found
    if isinstance(value, (list, tuple)):
        return [ref for item in value for ref in _iter_param_refs(item)]
    return []


def parameters_used(trial: Trial) -> frozenset[str]:
    """Every parameter a task references anywhere -- its states, its windows and the
    stimuli they name -- by name: what its trials resolve (`run._resolve`), and so what a
    run must have a value for (`preflight.values`, P4d-2b b3a-2). `_iter_param_refs`,
    from the task down, so a new vocabulary member is covered the day it is added."""
    return frozenset(ref.name for ref in _iter_param_refs(trial))


def _undeclared_parameters(trial: Trial) -> list[Finding]:
    """S1 §9 check 6: every parameter a task references is declared.

    An undeclared reference has no range, no widget and no place in the per-trial
    snapshot -- so it is either live-editable to any value or not editable at all,
    and nothing distinguishes the two from the task file.
    """
    declared = {param.name for param in trial.params}
    findings: list[Finding] = []
    for state in trial.states:
        for ref in _iter_param_refs(state):
            if ref.name not in declared:
                findings.append(
                    Finding(
                        "undeclared-parameter",
                        f"state {state.name!r} references parameter "
                        f"{ref.name!r}, which the task does not declare",
                    )
                )
    for attr in ("background", "background_left", "background_right"):
        for ref in _iter_param_refs(getattr(trial, attr)):
            if ref.name not in declared:
                findings.append(
                    Finding(
                        "undeclared-parameter",
                        f"the trial's {attr.replace('_', ' ')} references parameter "
                        f"{ref.name!r}, which the task does not declare",
                    )
                )
    return findings


def _custom_components(trial: Trial, components: Registry) -> list[Finding]:
    """S1 §9 check 9: every `Custom` component resolves to reviewed framework code.

    Two findings rather than one, because they are different statements. A name
    that resolves to nothing **refuses the load** -- the seam is being used as a
    hole, and the behaviour would simply not exist at run time. A name that does
    resolve is **accepted and flagged**: using the seam is legitimate and still
    puts the task on the human-review list beside the welfare-critical modules.
    """
    findings: list[Finding] = []
    for name, action in actions_of(trial):
        if not isinstance(action, Custom):
            continue
        if action.name in components:
            findings.append(
                Finding(
                    "custom-component-needs-review",
                    f"state {name!r} uses custom component "
                    f"{action.name!r}; this task needs human review",
                    blocking=False,
                )
            )
        else:
            findings.append(
                Finding(
                    "unresolved-custom-component",
                    f"state {name!r} names custom component "
                    f"{action.name!r}, which resolves to no reviewed component",
                )
            )
    return findings


def _extremes(value: object, ranges: dict[str, tuple[float, float]]) -> list[float]:
    """The values a position component can actually take.

    A literal is itself; a parameter is **both ends of its declared range**, because
    every value between them is one an experimenter can dial in live. Checking the
    range rather than a value proves the task cannot place a stimulus off-screen for
    any legal setting, instead of proving it happens not to today.
    """
    if isinstance(value, P):
        low, high = ranges.get(value.name, (0.0, 0.0))
        return [low, high]
    return [float(value)]


class _Unbounded(Exception):
    """A value check 8 cannot bound. Its one argument names the parameter."""


def _domain(value: object, params: dict[str, Param]) -> list:
    """Every value that matters for a property check 8 measures.

    A literal is itself. A parameter is **every choice it offers**, or **both ends of
    its declared range**, because every value between them is one an experimenter
    can dial in live. Anything else -- undeclared, no range, half a range -- can be
    dialled anywhere, so it is `_Unbounded` rather than the 0 it was once read as,
    which is the one place every field contains (XC-038).
    """
    if not isinstance(value, P):
        return [value]
    param = params.get(value.name)
    if param is None:
        raise _Unbounded(value.name)
    if param.choices:
        return list(param.choices)
    if param.low is not None and param.high is not None:
        return [param.low, param.high]
    raise _Unbounded(value.name)


def _numbers(value: object, params: dict[str, Param]) -> list[float]:
    """`_domain`, for a property that is a number: a choice that is not one is not
    something the field can be tested at."""
    found = _domain(value, params)
    if not all(_is_number(v) for v in found):
        raise _Unbounded(value.name if isinstance(value, P) else repr(value))
    return [float(v) for v in found]


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _options(value: object, params: dict[str, Param]) -> list:
    """Every value a field that is not a number can hold -- a light, a contrast, an
    appearance: a literal is itself, a parameter **each of its choices**. A parameter that
    offers none (undeclared, or a range of numbers where a light belongs) has nothing to
    read, so it is `_Unbounded`, as check 8 fails closed."""
    if not isinstance(value, P):
        return [value]
    param = params.get(value.name)
    if param is None or not param.choices:
        raise _Unbounded(value.name)
    return list(param.choices)


def _reach(value: object, params: dict[str, Param]) -> list[float]:
    """Every number a field can hold, for a rule a literal is held to: a literal number is
    itself, a parameter each choice or both ends of its range (`_numbers`, `_Unbounded`
    when it offers neither), and anything else no number this rule reads."""
    if isinstance(value, P):
        return _numbers(value, params)
    literal = _literal(value)
    return [] if literal is None else [literal]


def _points(at: object, params: dict[str, Param]) -> list[tuple[float, float]]:
    """Every centre a position can take.

    A pair is each coordinate's values, crossed. A **whole position as one
    parameter** (`at=P("pos")`) is the points it offers as choices; indexing it as a
    pair was a `TypeError` that would have crashed `taskd`'s load (XC-036). A range,
    or choices that are not points, names no place to test.
    """
    if isinstance(at, P):
        offered = _domain(at, params)
        if not all(
            isinstance(point, (tuple, list))
            and len(point) == 2
            and all(_is_number(c) for c in point)
            for point in offered
        ):
            raise _Unbounded(at.name)
        return [(float(x), float(y)) for x, y in offered]
    return [(x, y) for x in _numbers(at[0], params) for y in _numbers(at[1], params)]


def _form_reach(patch: RDS, params: dict[str, Param]) -> tuple[float, float]:
    """The least and greatest depth a stereogram's form reaches, over **every
    combination** of its parameters' values: evaluating each at its upper bound alone
    measured an amplitude over [-8, 0.1] as 0.1."""
    names = sorted({ref.name for ref in _iter_param_refs((patch.form, patch.aperture))})
    lows, highs = [], []
    for values in itertools.product(*(_numbers(P(name), params) for name in names)):
        low, high = patch.disparity_range(dict(zip(names, values)))
        lows.append(low)
        highs.append(high)
    return (min(lows), max(highs))


def _reachable(
    stimulus: Stimulus, params: dict[str, Param], vergence: float = 0.0
) -> list[tuple[float, float]]:
    """Every point one eye's image of a stimulus can reach, in that eye's own degrees:
    after disparity and, through the stereoscope, the vergence offset.

    The left eye's image sits at `x − d/2 + v` and the right eye's at `x + d/2 − v`,
    `v = atan(E/D)` (engine spec §5.4; optics drawing §6), so straight ahead at 11° the
    left eye's image is at 12.45°, behind a ±12° mask. Per-eye positions are already
    each eye's own direction. Only the eyes that see the stimulus are measured.

    Raises `_Unbounded` when a property it depends on cannot be bounded.
    """
    if stimulus.at_left is not None and stimulus.at_right is not None:
        bases = {-1.0: _points(stimulus.at_left, params), 1.0: _points(stimulus.at_right, params)}
        shift = 0.0
    else:
        points = _points(stimulus.at, params)
        bases = {-1.0: points, 1.0: points}
        shift = vergence
    signs = {"left": (-1.0,), "right": (1.0,)}.get(stimulus.eye, (-1.0, 1.0))
    halves = _numbers(stimulus.disparity, params)
    reached: list[tuple[float, float]] = []
    for looks in _domain(stimulus.looks, params):
        half = halves
        if isinstance(looks, RDS) and looks.form is not None:
            # A disparity *field* has no single value to displace by, so the
            # extremes of the form are added to the stimulus's own disparity: a
            # patch centred safely can still push one eye's image off the panel at
            # the extreme of its corrugation, and only that eye's.
            low, high = _form_reach(looks, params)
            half = [value + reach for value in halves for reach in (low, high)]
        for sign in signs:
            centres = bases[sign]
            if isinstance(looks, Array):
                # An array's items sit on a ring around the stimulus position, so the
                # thing that can leave the field is an *item*, never the centre. The
                # extreme is the widest legal radius: with n a parameter too, every
                # smaller set is a subset of those positions.
                widest = max(_numbers(looks.radius, params))
                centres = [
                    (x + dx, y + dy)
                    for x, y in centres
                    for dx in (widest, -widest, 0.0)
                    for dy in (widest, -widest, 0.0)
                ]
            reached.extend(
                (x + sign * (d / 2 - shift), y) for x, y in centres for d in (min(half), max(half))
            )
    return reached


#: The properties an `Update` can change that the display checks measure.
_UPDATED = ("at", "looks", "disparity", "at_left", "at_right", "eye", "combine")


def _as_updated(trial: Trial) -> dict[int, list[Stimulus]]:
    """What each `Update` can leave on the display, keyed by the action's `id`.

    An update sets what it names and leaves every other property as an earlier
    `Show` or `Update` of that stimulus left it. Which earlier one is a question
    about paths through the task, so each unset property takes **any** value a
    `Show` or another `Update` of that name gives it. That can only add
    combinations, never lose one, so what passes here passes on every path.
    """
    shows: dict[str, list[Stimulus]] = {}
    updates: dict[str, list[Update]] = {}
    for _, action in actions_of(trial):
        if isinstance(action, Show):
            shows.setdefault(action.stimulus.name, []).append(action.stimulus)
        elif isinstance(action, Update):
            updates.setdefault(action.stimulus, []).append(action)
    result: dict[int, list[Stimulus]] = {}
    for name, these in updates.items():
        shown = shows.get(name, [])
        if not shown:
            continue  # nothing to update: `_display_faults` reports that
        for update in these:
            sets = update.changes()
            options = {}
            for prop in _UPDATED:
                values = (
                    [sets[prop]]
                    if prop in sets
                    else [getattr(s, prop) for s in shown]
                    + [other.changes()[prop] for other in these if prop in other.changes()]
                )
                unique: list = []
                for value in values:  # by equality: values need not be hashable
                    if not any(value == seen for seen in unique):
                        unique.append(value)
                options[prop] = unique
            # The first `Show` supplies only the stimulus's name; every property
            # that matters here comes from `options`.
            result[id(update)] = [
                dataclasses.replace(shown[0], **dict(zip(_UPDATED, combo)))
                for combo in itertools.product(*(options[prop] for prop in _UPDATED))
            ]
    return result


def _offscreen_stimuli(trial: Trial, geometry: Geometry | None) -> list[Finding]:
    """S1 §9 check 8: every stimulus can actually be shown.

    Checked **per eye, after disparity**, not at the cyclopean position. Disparity is
    applied as equal and opposite horizontal offsets, so a stimulus comfortably inside
    the field can still put one eye's image outside it -- and only that eye's. On a
    split-screen stereoscope that is a stimulus the animal fuses on one side and loses
    on the other, a far stranger failure than simply not seeing it.

    **And after the vergence offset** through the stereoscope (engine build A1): the
    drawer moves each eye's image by `atan(E/D)`, so the check measures where the
    image is drawn.

    **Against the setup's own field** (direct-view spec §2, §4): the whole panel less
    the light sensors' housings in direct view, the mask through the stereoscope. A
    stimulus under a housing is refused exactly as one off the panel is.

    **It fails closed** (XC-036 to XC-038). Every value a parameter offers is
    measured, an `Update` is measured like the `Show` it changes, and a property that
    cannot be bounded is refused rather than read as 0: a check that passes what it
    could not measure reports safety it does not provide.

    Skipped when no geometry is supplied: a task is not wrong for being checked
    without a rig, it is unchecked, and the caller knows which it wanted. **`taskd` and
    `wlx check` supply one** (`wlx run --rig --view` and `wlx check --rig`, which take
    the field from the rig file); `check()` without a geometry is only for callers that
    have no rig (`wlx review`, the tests).
    """
    if geometry is None:
        return []
    params = {p.name: p for p in trial.params}
    updated = _as_updated(trial)
    vergence = geometry.vergence_half_deg
    field = (
        f"the \u00b1{geometry.half_field_h_deg:.1f}\u00b0 \u00d7 "
        f"\u00b1{geometry.half_field_v_deg:.1f}\u00b0 {geometry.view} field"
        + (", less the light sensors' housings" if geometry.housings else "")
        + (f", each eye's image after the {vergence:.2f}\u00b0 vergence offset" if vergence else "")
    )
    findings: list[Finding] = []
    for name, action in actions_of(trial):
        if isinstance(action, Show):
            stimuli = [action.stimulus]
            what = f"shows a stimulus at ({_described(action.stimulus.at)})"
        elif isinstance(action, Update) and id(action) in updated:
            stimuli = updated[id(action)]
            what = f"updates stimulus {action.stimulus!r}"
        else:
            continue
        try:
            bad = [
                point
                for stimulus in stimuli
                for point in _reachable(stimulus, params, vergence)
                if not geometry.can_show(*point)
            ]
        except _Unbounded as unbounded:
            findings.append(
                Finding(
                    "stimulus-off-screen",
                    f"state {name!r} {what} whose extent cannot be bounded: "
                    f"{unbounded.args[0]!r} has neither a two-sided range nor choices "
                    f"check 8 can measure, so it cannot be proved inside {field}",
                )
            )
            continue
        if not bad:
            continue
        disparities = sorted({str(s.disparity) for s in stimuli if s.disparity})
        findings.append(
            Finding(
                "stimulus-off-screen",
                f"state {name!r} {what} which can reach "
                f"{bad[0][0]:.1f}, {bad[0][1]:.1f} -- outside {field}"
                + (f", with disparity {', '.join(disparities)}" if disparities else ""),
            )
        )
    return findings


def _described(at: object) -> str:
    if isinstance(at, P):
        return at.name
    return ", ".join(f"{v.name}" if isinstance(v, P) else f"{v:g}" for v in at)


def _unallocated_outcomes(trial: Trial, allocation: Allocation) -> list[Finding]:
    """S1 §9 check 5: every terminal outcome maps to an allocated marker.

    An outcome with no marker is a trial that ends without saying how: the
    recording carries the timing of a decision whose result exists only in our
    files, and the pairing between the two is exactly what the hardware-truth rule
    exists to avoid depending on.
    """
    seen: list[object] = []
    for state in trial.states:
        for edge in state.go:
            if isinstance(edge.to, Outcome) and edge.to not in seen:
                seen.append(edge.to)
    return [
        Finding(
            "unallocated-outcome",
            f"outcome {outcome.name} maps to no allocated marker",
        )
        for outcome in seen
        if outcome not in allocation.outcomes
    ]


def _window_refs(value: object) -> list[str]:
    """Window names referenced anywhere. Walks generically, like `_iter_param_refs`,
    so a new guard naming a window is covered the day it is added."""
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        found: list[str] = []
        for f in dataclasses.fields(value):
            attribute = getattr(value, f.name)
            if f.name == "window" and isinstance(attribute, str):
                found.append(attribute)
            else:
                found.extend(_window_refs(attribute))
        return found
    if isinstance(value, (list, tuple)):
        return [name for item in value for name in _window_refs(item)]
    return []


def _undeclared_windows(trial: Trial) -> list[Finding]:
    """S1a §1: every window a task names is declared.

    A task referring to a gaze window nothing declares has no fixation criterion --
    no position, no radius, nothing an experimenter can tune. It is the same defect
    as an undeclared parameter and would read just as reasonably in a generated file.
    """
    declared = _declared_window_names(trial)
    findings: list[Finding] = []
    for state in trial.states:
        for name in _window_refs(state):
            if name not in declared:
                findings.append(
                    Finding(
                        "undeclared-window",
                        f"state {state.name!r} references window {name!r}, "
                        f"which the task does not declare",
                    )
                )
    return findings


# --- What is on the display ------------------------------------------------
#
# Every check above this line inspects the transition graph. None of them models
# the screen, so the class of defect they cannot see is "correct graph, wrong
# experiment" -- and the first reference task carried one: it showed a fixation
# point in one state and asked for a hold on it in the next, which under the
# original state-scoped `Show` removed the point at the exact frame the animal was
# asked to hold it. Ten checks passed. Found by review 2026-08-31.


def _uncoupled_windows(trial: Trial) -> list[Finding]:
    """Every window says what it scores, or says `REMEMBERED`.

    Unset cannot be allowed to mean "nothing there": that would make the
    nothing-to-look-at check opt-in, and the tasks most likely to skip it are the
    ones written fastest. A memory-guided saccade is a real paradigm and its blank
    location is the point -- so it is spelled out rather than defaulted into.
    """
    return [
        Finding(
            "uncoupled-window",
            f"window {window.name!r} does not say which stimulus it scores; give it "
            f"on='<stimulus>', or on=REMEMBERED if nothing is displayed there",
        )
        for window in trial.windows
        # An `ItemWindows` family always couples to its array, by construction.
        if not isinstance(window, ItemWindows) and window.on is None
    ]


def _visible_on_entry(trial: Trial) -> dict[str, frozenset[str]]:
    """For each state, the stimuli on the display on *every* path into it.

    A **must** analysis, not a may: visible on some route in is not visible. A task
    whose one branch shows the target and whose other does not works for a hundred
    trials and then scores a hold against a blank screen on the branch nobody ran.

    Iterated to a fixpoint over the graph rather than walked once, because states
    reachable by several routes -- and cycles, which the vocabulary permits -- have
    no single predecessor to inherit from.
    """
    every = frozenset(
        action.stimulus.name for _, action in actions_of(trial) if isinstance(action, Show)
    )
    by_name = {state.name: state for state in trial.states}
    entry: dict[str, frozenset[str]] = {
        name: (frozenset() if name == trial.start else every) for name in by_name
    }

    def after(visible: frozenset[str], actions: list) -> frozenset[str]:
        for action in actions:
            if isinstance(action, Show):
                visible = visible | {action.stimulus.name}
            elif isinstance(action, Hide):
                visible = visible - {action.stimulus}
        return visible

    for _ in range(len(by_name) + 1):
        arriving: dict[str, list[frozenset[str]]] = {name: [] for name in by_name}
        for state in trial.states:
            leaving = after(entry[state.name], state.enter)
            for edge in state.go:
                if isinstance(edge.to, Outcome):
                    continue
                arriving[edge.to].append(after(leaving, edge.do))
        settled = {
            name: (
                frozenset()
                if name == trial.start
                else frozenset.intersection(*inbound) if inbound else frozenset()
            )
            for name, inbound in arriving.items()
        }
        if settled == entry:
            break
        entry = settled
    return entry


def _display_faults(trial: Trial) -> list[Finding]:
    """Guards and actions checked against what is actually on the screen."""
    scores = _coupling(trial)
    entry = _visible_on_entry(trial)
    findings: list[Finding] = []

    for state in trial.states:
        visible = set(entry.get(state.name, frozenset()))
        for action in state.enter:
            findings += _one_action(state.name, action, visible)

        # Guards are evaluated against the display as the state *begins*, after its
        # entry actions: a state that shows a target and holds it is legal.
        for edge in state.go:
            window = getattr(edge.guard, "window", None)
            if window is not None and isinstance(
                edge.guard, (Entered, Exited, Hold, SaccadeTo, Touched)
            ):
                on = scores.get(window)
                if isinstance(on, str) and on not in visible:
                    findings.append(
                        Finding(
                            "nothing-to-look-at",
                            f"state {state.name!r} scores {window!r} against stimulus "
                            f"{on!r}, which is not on the display there; a hold on a "
                            f"stimulus that has been taken down cannot be satisfied "
                            f"by the animal doing the task correctly",
                        )
                    )
            for action in edge.do:
                findings += _one_action(state.name, action, set(visible))
    return findings


def _one_action(state: str, action, visible: set[str]) -> list[Finding]:
    """Check one display action against the current screen, and apply it."""
    if isinstance(action, Show):
        if action.stimulus.name in visible:
            return [
                Finding(
                    "duplicate-stimulus",
                    f"state {state!r} shows {action.stimulus.name!r}, which is "
                    f"already on the display; two live stimuli under one name make "
                    f"Hide and Update ambiguous",
                )
            ]
        visible.add(action.stimulus.name)
        return []
    if isinstance(action, Hide):
        if action.stimulus not in visible:
            return [
                Finding(
                    "absent-stimulus",
                    f"state {state!r} hides {action.stimulus!r}, which is not on "
                    f"the display",
                )
            ]
        visible.discard(action.stimulus)
        return []
    if isinstance(action, Update):
        found = []
        if action.stimulus not in visible:
            found.append(
                Finding(
                    "absent-stimulus",
                    f"state {state!r} updates {action.stimulus!r}, which is not on "
                    f"the display",
                )
            )
        if not action.changes():
            found.append(
                Finding(
                    "empty-update",
                    f"state {state!r} updates {action.stimulus!r} without changing "
                    f"anything",
                )
            )
        return found
    return []


# --- Colour ----------------------------------------------------------------


def _appearances(trial: Trial):
    """Every appearance a trial can put on screen, including the ones only a
    parameter selects.

    **Parameter choices count.** Pop-out is expressed as an appearance parameter --
    a red target among green distractors is the same task as a circle among squares
    with a different value -- so an appearance reachable only through `Param.choices`
    is as real as one written into a `Show`, and checking only the latter would skip
    exactly the stimuli this vocabulary was extended to express.
    """
    from wl_xcon.task import Appearance, Show, Update

    seen = []
    for _, action in actions_of(trial):
        looks = None
        if isinstance(action, Show):
            looks = action.stimulus.looks
        elif isinstance(action, Update) and not isinstance(action.looks, P):
            looks = action.looks
        if isinstance(looks, Appearance):
            seen.append(looks)
    for param in trial.params:
        seen.extend(c for c in param.choices if isinstance(c, Appearance))
    for looks in list(seen):
        if isinstance(looks, Array):
            seen.extend(m for m in (looks.looks, looks.among) if isinstance(m, Appearance))
    return seen


def _combined(trial: Trial, params: dict[str, Param]) -> list[tuple[object, object]]:
    """Each appearance a stimulus can show, paired with how that stimulus combines with what
    is below it (engine spec §4.4), so a rule can ask what a combination needs of a light.

    A `Show` pairs its looks with its own `combine`. An `Update` of `looks` pairs them with
    the `combine` of each `Show` of that name, since an update cannot change one, or with
    `None` when nothing shows that name, which no rule exempts. An `Array`'s items combine
    as the array does, and a parameter's choices as the stimulus whose looks it is. An
    appearance `_appearances` finds that this pairs with nothing (a parameter's choice no
    stimulus shows) has no combination to exempt it from any rule."""
    from wl_xcon.task import Appearance

    shown: dict[str, list[str]] = {}
    for _, action in actions_of(trial):
        if isinstance(action, Show):
            shown.setdefault(action.stimulus.name, []).append(action.stimulus.combine)
    pairs: list[tuple[object, object]] = []

    def walk(looks, how, inside: frozenset[str]) -> None:
        if isinstance(looks, P):
            if looks.name in inside:
                return  # refused as referring to itself (`_self_referring`)
            param = params.get(looks.name)
            for choice in (param.choices if param is not None else ()):
                walk(choice, how, inside | {looks.name})
        elif isinstance(looks, Appearance):
            pairs.append((looks, how))
            if isinstance(looks, Array):
                walk(looks.looks, how, inside)
                walk(looks.among, how, inside)

    for _, action in actions_of(trial):
        if isinstance(action, Show):
            walk(action.stimulus.looks, action.stimulus.combine, frozenset())
        elif isinstance(action, Update) and "looks" in action.changes():
            for how in shown.get(action.stimulus, [None]):
                walk(action.looks, how, frozenset())
    return pairs


def _literal(value) -> float | None:
    """A literal number, or None for a parameter, a missing value or anything else."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _colors(trial: Trial, params: dict[str, Param]):
    """Every color a trial can put on screen, with what carries it: each appearance's,
    each block's (a flat fill, a grating's mean, an outline), and the backgrounds. A color
    that is a parameter is each of its choices; one offering none to read is refused by
    `_light_faults`, and a value that is not a color by `_block_faults`, so neither is one
    here. An appearance a parameter offers is named as that parameter's choice (every one
    it is, when the same object is offered twice), so the choices' findings say which is
    which."""
    from wl_xcon import look

    offered: dict[int, list[str]] = {}
    for param in trial.params:
        for at, choice in enumerate(param.choices, 1):
            offered.setdefault(id(choice), []).append(f"choice {at} of parameter {param.name!r}")

    def each(what, color):
        try:
            choices = _options(color, params)
        except _Unbounded:
            return
        for choice in choices:
            if isinstance(choice, Color):
                yield (what if choice is color
                       else f"{what} (a choice of parameter {color.name!r})"), choice

    for looks in _appearances(trial):
        what = type(looks).__name__
        chosen = f" ({', '.join(offered[id(looks)])})" if id(looks) in offered else ""
        if isinstance(looks, look.Look):
            for part in (looks.fill, looks.outline):
                for attr in ("color", "mean"):
                    yield from each(f"{what}'s {type(part).__name__}{chosen}",
                                    getattr(part, attr, None))
        else:
            yield from each(f"{what}{chosen}", getattr(looks, "color", None))
    for attr in ("background", "background_left", "background_right"):
        yield from each(f"the trial's {attr.replace('_', ' ')}", getattr(trial, attr))


def _color_faults(trial: Trial, panel: Calibration | None) -> list[Finding]:
    """Colour checked against a display somebody measured.

    RGB is a set of instructions to one panel, so a colour that is not checked
    against a measurement is a colour nobody knows. The specific failure this
    prevents: a monitor asked for a colour outside its gamut clips silently, and a
    clipped colour has neither the requested chromaticity nor the requested
    luminance -- so an isoluminant pair stops being isoluminant and a chromatic
    experiment's control condition quietly becomes a luminance manipulation.
    """
    params = {p.name: p for p in trial.params}
    backgrounds = _background_lights(trial, params)
    findings: list[Finding] = []
    for what, color in _colors(trial, params):
        # With no calibration at all -- `wlx taskd` while the rig's record will not load (the
        # engine B plan, call 19), or a direct `check()` call -- an absolute luminance is not
        # checked here, since every run's pre-flight fails on the missing calibration; on the
        # default it is the session's one warning (`warnlist.of_calibration`, accepted at the
        # open). Any other color with no calibration is unmeasured once, as written; with one,
        # it is checked as each light it can be.
        if panel is None and isinstance(color, Gray):
            continue
        if what.startswith("the trial's ") and isinstance(color, CONE_COLORS):
            continue  # a background is an absolute light, and `_block_faults` refuses one that is not
        try:
            lights = [color] if panel is None else _lights(color, params)
        except _Unbounded:
            continue  # refused as a bad block: it cannot be bounded
        for light in lights:
            for finding in _one_color(what, light, panel, backgrounds):
                if finding not in findings:  # one value's corners can say the same
                    findings.append(finding)
    if panel is not None and panel.standard:
        findings += _default_faults(trial, params)
    return findings


def _background_lights(trial: Trial, params: dict[str, Param]) -> list:
    """Every lit light an eye's background can be, as an `xyY`, for a cone color's conversion:
    each choice of a background parameter, each corner of a `Gray`'s or an `xyY`'s ranges
    (`_lights`; exact for a luminance range, corners only for a chromaticity one, the engine A2
    plan's call 11). Black is left out (`cone-color-on-black` refuses a cone color there), as is
    one that cannot be bounded or is not an absolute light (`_block_faults` refuses it)."""
    found: list = []
    for background in _backgrounds(trial):
        try:
            values = _options(background, params)
        except _Unbounded:
            continue
        for value in values:
            if not isinstance(value, (Gray, xyY)):
                continue
            try:
                lights = _lights(value, params)
            except _Unbounded:
                continue
            for light in lights:
                if light.Y > 0.0 and light not in found:
                    found.append(light)
    return found


def _lights(color, params: dict[str, Param]) -> list:
    """Each light `color` can be, for a calibration to test, at each value a parameter in it
    can take (`_reach`: each choice, or both ends of a range): a `Gray` is D65 white at each
    luminance, an `xyY` each combination of its `x`, `y` and `Y` (XC-261). A component that
    is no number names no light; `_block_faults` refuses it.

    The ends of the ranges are enough: the panel's gamut is convex, and xyY to XYZ maps a box
    of values with y > 0 into the convex hull of its corners' images (projective in x and y,
    linear in Y)."""
    if isinstance(color, Gray):
        return [xyY(D65[0], D65[1], v) for v in _reach(color.cd_m2, params)]
    if isinstance(color, xyY):
        return [xyY(x, y, Y) for x, y, Y in itertools.product(
            *(_reach(v, params) for v in (color.x, color.y, color.Y)))]
    if isinstance(color, DKL):
        return [DKL(lum, l_m, s_lm) for lum, l_m, s_lm in itertools.product(
            *(_reach(v, params) for v in (color.lum, color.l_m, color.s_lm)))]
    if isinstance(color, ConeContrast):
        return [ConeContrast(L, M, S) for L, M, S in itertools.product(
            *(_reach(v, params) for v in (color.L, color.M, color.S)))]
    return [color]


def _one_color(what: str, color, panel: Calibration | None, backgrounds: list) -> list[Finding]:
    """One light against the calibration, or against its absence: a cone color against each lit
    light the trial's background can be (`_background_lights`), since its conversion and so its
    reach depend on the background (COL-10)."""
    if panel is None:
        return [
            Finding(
                "uncalibrated-color",
                f"{what} asks for {color}, but no display calibration was "
                f"supplied; colour is a physical claim and this one is "
                f"unmeasured",
            )
        ]
    if panel.standard and isinstance(color, DKL):
        # Spec §7.3: "Isoluminance needs a measured calibration", in every session (N§4
        # batch 1); any other DKL converts through cone fundamentals, which build A2 adds.
        # **`magnitude()` is never asked here** (the engine B plan, call 9): a component that
        # is a parameter makes it raise (XC-269), and from engine build B's Task 8 every
        # session checks against this calibration. A literal `lum` of 0 beside another
        # component that is a parameter or not 0 claims isoluminance at some value; every DKL
        # here is refused either way.
        if _literal(color.lum) == 0.0 and any(_literal(v) != 0.0 for v in (color.l_m, color.s_lm)):
            return [Finding("isoluminance-on-default", (
                f"{what} claims isoluminance, which needs a measured calibration (engine spec "
                f"§7.3); the default calibration is the sRGB standard, measured by nobody"))]
        return [Finding("dkl-on-default", (
            f"{what} is a DKL color, which converts through cone fundamentals (engine build "
            f"A2); until then it loads only against a measured calibration"))]
    # Isoluminance is the lab observer's V_F,10 (A2's Q5), named by `cones.CIE2006_10` and
    # recorded with the session; a measured calibration names its own photometry's observer or
    # does not load (`Calibration`), so nothing is left for a finding here (engine build A2).
    if isinstance(color, CONE_COLORS):
        return [Finding("unrealizable-color", f"{what} asks for {color} on a background of "
                                              f"{background}: {why}")
                for background in backgrounds
                if (why := unrealizable(color, panel, background)) is not None]
    why = unrealizable(color, panel)
    if why is not None:
        return [Finding("unrealizable-color", f"{what} asks for {color}: {why}")]
    return []


def _default_faults(trial: Trial, params: dict[str, Param]) -> list[Finding]:
    """What a recording cannot carry on the default calibration (engine spec §7.2; N§R4: "Yes,
    from the task file"): a task that names a color, or one a parameter of which sets a light
    or a contrast -- this build's reading of "a design factor or a procedure-controlled value",
    until build C lets a task declare its factors (Question 2). Each is one warning per task,
    accepted in training and piloting."""
    findings = []
    named = sorted({what for what, color in _colors(trial, params) if isinstance(color, (xyY, *CONE_COLORS))})
    if named:
        findings.append(Finding("color-on-default", (
            f"this task names colors ({'; '.join(named)}), and the default calibration is the sRGB "
            f"standard, measured by nobody: a recording session refuses it until a measured "
            f"calibration is in use (engine spec §7.2)"),
            blocking=False, accepted_in=NOT_RECORDING))
    set_by = _parameter_lights(trial, params)
    if set_by:
        findings.append(Finding("contrast-on-default", (
            f"parameter(s) {', '.join(repr(name) for name in set_by)} set a light, a contrast or "
            f"an opacity, which this build counts as a design factor until a task can declare its "
            f"own (engine build C): a recording session refuses them on the default calibration "
            f"(engine spec §7.2)"),
            blocking=False, accepted_in=NOT_RECORDING))
    return findings


def _parameter_lights(trial: Trial, params: dict[str, Param]) -> list[str]:
    """The parameters that set a light, a contrast or an opacity anywhere a trial can show, by
    name, sorted (the engine B plan, call 24): every parameter inside what lights an
    appearance (`_lit`), a background or a shown or updated stimulus's `opacity` (spec §4.4:
    front covers back by it), **and inside each choice such a parameter offers** -- so a
    parameter that is a `Look`'s whole fill or outline counts and its fills or outlines are
    read (XC-271's shape, and XC-273's outline) -- and an appearance parameter whose
    choices differ in what lights them, an `Array`'s items included (`_shown`). A parameter
    met again inside its own choices adds nothing more: `_self_referring` refuses it."""
    from wl_xcon.task import Appearance

    names: set[str] = set()

    def walk(value, inside: frozenset[str]) -> None:
        for ref in _iter_param_refs(value):
            names.add(ref.name)
            param = params.get(ref.name)
            if param is None or ref.name in inside:
                continue
            for choice in param.choices:
                walk(_lit(choice), inside | {ref.name})

    for looks in _appearances(trial):
        walk(_lit(looks), frozenset())
    for attr in ("background", "background_left", "background_right"):
        walk(getattr(trial, attr), frozenset())
    for _, action in actions_of(trial):
        if isinstance(action, Show):
            walk(action.stimulus.opacity, frozenset())
        elif isinstance(action, Update):
            walk(action.opacity, frozenset())
    for param in trial.params:
        lit = [_shown(choice, params) for choice in param.choices if isinstance(choice, Appearance)]
        if any(other != lit[0] for other in lit[1:]):
            names.add(param.name)
    return sorted(names)


def _shown(looks, params: dict[str, Param], inside: frozenset[str] = frozenset()) -> list:
    """What lights an appearance, for comparing an appearance parameter's choices: `_lit`, with
    an `Array`'s items read in turn, and an appearance parameter among them as what each of its
    choices shows. **Being named in an `Array` never makes a parameter a light factor**; its
    own choices decide that. One undeclared, or met again inside its own choices, is read as
    itself, so two of them differ by name: it fails closed."""
    if isinstance(looks, P):
        param = params.get(looks.name)
        if param is None or looks.name in inside:
            return [looks]
        return [_shown(choice, params, inside | {looks.name}) for choice in param.choices]
    if isinstance(looks, Array):
        return [_shown(looks.looks, params, inside), _shown(looks.among, params, inside)]
    return _lit(looks)


def _lit(value) -> list:
    """What lights `value`, as written, for `_parameter_lights` (the review's I5): an
    appearance's or a fill's `color`, `contrast` and `mean`, whichever it has -- read
    generically, so a `Checkerboard`, `Plaid`, `Noise` or `RDS`, whose light `_light` leaves
    to a later build, is read too -- a `Look`'s fill and its outline's color; anything else,
    a color, a contrast or a parameter, is its own light. **A `Look`'s fill and outline are
    read as written**: one that is a parameter is its own light, whose choices the walk
    reads (XC-271, XC-273), and one of another kind, which `_block_faults` refuses, is never
    asked for a color (`check()` raised AttributeError doing that until the A1 follow-ups'
    fix wave)."""
    from wl_xcon import look
    from wl_xcon.task import Appearance

    if isinstance(value, look.Look):
        return [_lit(value.fill), _lit(value.outline)]
    if isinstance(value, look.Outline):
        return [value.color]
    if isinstance(value, (Appearance, look.Fill)):
        return [getattr(value, attr, None) for attr in ("color", "contrast", "mean")]
    return [value]


# --- Light and contrast (engine build A1) ----------------------------------

#: Block fields that are full widths in degrees, so must be positive (spec §5.2).
_SIZES = ("size", "width", "height", "length", "thickness", "outer", "sigma", "aperture")

#: Block fields that hold a number or a parameter (XC-245): every size, the rest the drawer
#: reads as one, a contrast's `value`, a `Gray`'s `cd_m2` and an `xyY`'s `x`, `y` and `Y`.
#: `None` is a value of one only where its block's own default is `None` (a grating's
#: `direction`).
_NUMBERS = (*_SIZES, "inner", "sides", "sf", "phase", "tf", "direction", "orientation", "value",
            "cd_m2", "x", "y", "Y", "lum", "l_m", "s_lm", "L", "M", "S")

#: Block fields that hold a light: a `Color`, `None`, or a parameter offering those (XC-264).
_LIGHTS = ("color", "mean")


def _light(looks) -> tuple | None:
    """What lights a stimulus, as `(kind, color, contrast, mean)`: kind `"flat"` for one
    light, `"grating"` for a sine grating about a mean; `None` for an appearance whose
    light a later build of the engine defines (noise, dots, pictures, ...)."""
    from wl_xcon import look
    from wl_xcon.task import Annulus, Bar, Cross, Disc, Gabor, Grating, Polygon, Square

    if isinstance(looks, (Disc, Square, Bar, Cross, Polygon, Annulus)):
        return ("flat", looks.color, looks.contrast, None)
    if isinstance(looks, (Gabor, Grating)):
        return ("grating", looks.color, looks.contrast, None)
    if isinstance(looks, look.Look) and isinstance(looks.fill, look.Flat):
        return ("flat", looks.fill.color, looks.fill.contrast, None)
    if isinstance(looks, look.Look) and isinstance(looks.fill, look.SineGrating):
        return ("grating", None, looks.fill.contrast, looks.fill.mean)
    return None


def _backgrounds(trial: Trial) -> list:
    """The background each eye sees: one in direct view, two through the stereoscope."""
    if trial.view == "stereoscope":
        return [trial.background_left or trial.background,
                trial.background_right or trial.background]
    return [trial.background]


def _luminance(color):
    """A light's luminance as written, a number or a parameter: a `Gray`'s `cd_m2`, an
    `xyY`'s `Y`; `None` for anything else."""
    if isinstance(color, Gray):
        return color.cd_m2
    if isinstance(color, xyY):
        return color.Y
    return None


def _black(color, params: dict[str, Param], inside: frozenset[str] = frozenset()) -> bool:
    """Whether a background can be black: the default, a zero luminance, or a parameter
    whose choices or range reach one, the background's own or its luminance's (a `Gray`'s
    or an `xyY`'s, XC-266). One that cannot be read or bounded can, failing closed. A
    parameter met again inside its own choices adds none: they are being read already, and
    it is refused as referring to itself (`_self_referring`)."""
    try:
        if isinstance(color, P):
            if color.name in inside:
                return False
            return any(_black(choice, params, inside | {color.name})
                       for choice in _options(color, params))
        if color is None:
            return True
        return any(v <= 0.0 for v in _reach(_luminance(color), params))
    except _Unbounded:
        return True


def _background_fix(backgrounds: list, params: dict[str, Param]) -> str:
    """What to write so no eye's background is black, for every way `_black` finds one can
    be (XC-268): each parameter whose values reach black, named with what to change -- the
    low end of its range, its black choices, or a bound it lacks -- and each eye whose
    background is unset or written black, told to declare one (naming the eye on the
    stereoscope when only one is). A parameter met again inside its own choices adds
    nothing: `_self_referring` refuses it."""
    fixes: list[str] = []
    unset: list[int] = []
    written: list[int] = []

    def fix(said: str) -> None:
        if said not in fixes:
            fixes.append(said)

    def dark(color) -> bool:
        """Black as written: no light, or a literal luminance of 0."""
        luminance = _literal(_luminance(color))
        return color is None or (luminance is not None and luminance <= 0.0)

    def walk(color, eye: int, inside: frozenset[str]) -> None:
        if isinstance(color, P):
            if color.name in inside:
                return
            param = params.get(color.name)
            if param is None or not param.choices:
                fix(f"give parameter {color.name!r} lit colors as its choices")
                return
            black = [choice for choice in param.choices if dark(choice)]
            if black:
                fix(f"remove {', '.join(map(repr, black))} from parameter {color.name!r}'s choices")
            for choice in param.choices:
                if not dark(choice):
                    walk(choice, eye, inside | {color.name})
            return
        if color is None:
            unset.append(eye)
            return
        light = _luminance(color)
        try:
            reached = [v for v in _reach(light, params) if v <= 0.0]
        except _Unbounded:
            fix(f"bound parameter {light.name!r} above 0: it has neither a two-sided range nor "
                f"numeric choices, so it can be anything")
            return
        if not reached:
            return
        if not isinstance(light, P):
            written.append(eye)
        elif params[light.name].choices:
            fix(f"remove {', '.join(f'{v:g}' for v in reached)} from parameter {light.name!r}'s "
                f"choices")
        else:
            fix(f"raise the low end of parameter {light.name!r}'s range above 0")

    for eye, background in enumerate(backgrounds):
        walk(background, eye, frozenset())

    def whose(eyes: list[int]) -> str:
        if len(backgrounds) == 1 or len(eyes) == len(backgrounds):
            return "the trial's"
        return ("the left eye's", "the right eye's")[eyes[0]]

    if unset:
        fix(f"declare {whose(unset)} background")
    if written:
        fix(f"declare {whose(written)} background lit: as written it is black")
    return " and ".join(fixes) or "declare the trial's background"


def _bare(contrast, params: dict) -> bool:
    """A contrast with no convention: a number, or a parameter whose values are numbers."""
    from wl_xcon.photometry import Contrast

    if _literal(contrast) is not None:
        return True
    if isinstance(contrast, P) and contrast.name in params:
        choices = params[contrast.name].choices
        return not (choices and all(isinstance(c, Contrast) for c in choices))
    return False


def _through(*values) -> str:
    """How a finding names the parameters a value came through, if any."""
    names = [repr(v.name) for v in values if isinstance(v, P)]
    return f" (through parameter {', '.join(names)})" if names else ""


def _light_faults(trial: Trial) -> list[Finding]:
    """Engine spec §4.12, §4.3, §7.5: every stimulus has a light, every contrast names its
    convention, and a light relative to the background has a background to be relative
    to. An invisible stimulus is not a rendering problem: the trial would score as a miss
    indistinguishable from behavior.

    **A light written as a parameter is held to these rules at each of its choices**, and
    one that offers no choices to read is refused: a check that read only literals passed
    exactly the lights the lab makes live.

    **What a light must be depends on how it is combined** (`_combined`), and an appearance
    is exempt only when every stimulus that can show it is. A window or a scotoma draws
    none of its own light (`screen.LIGHTLESS`; call 3, XC-257), so its light is held to
    none of these rules; how it is written still is (`bare-contrast`, a parameter with no
    choices to read), and its outline, which is drawn, still needs a light. A multiplying
    grating draws only its modulation, so a mean it lacks is not a light it lacks on black
    (the multiplying half of XC-256); one it declares is refused where the combination is
    (`_placement_faults`)."""
    from wl_xcon import look
    from wl_xcon.photometry import Contrast, Michelson, Weber
    from wl_xcon.screen import LIGHTLESS

    params = {p.name: p for p in trial.params}
    backgrounds = _backgrounds(trial)
    on_black = any(_black(b, params) for b in backgrounds)
    fix = _background_fix(backgrounds, params)
    combined = _combined(trial, params)
    findings: list[Finding] = []

    def found(code: str, detail: str, blocking: bool = True, accepted_in: tuple = ()) -> None:
        finding = Finding(code, detail, blocking=blocking, accepted_in=accepted_in)
        if finding not in findings:  # one parameter's choices can repeat a finding
            findings.append(finding)

    def unread(what: str, name: str) -> None:
        found("bad-block", (
            f"{what} is parameter {name!r}, which offers no choices, so its light cannot be "
            f"read; a light written as a parameter offers its lights as choices"))

    for attr in ("background", "background_left", "background_right"):
        try:
            _options(getattr(trial, attr), params)
        except _Unbounded as unbounded:
            unread(f"the trial's {attr.replace('_', ' ')}", unbounded.args[0])
    for looks in _appearances(trial):
        what = type(looks).__name__
        # Only an `Outline` has a color to read: one of another kind is `_block_faults`' to
        # refuse, and one written as a parameter is read by no rule yet (XC-273).
        if isinstance(looks, look.Look) and isinstance(looks.outline, look.Outline):
            color = looks.outline.color
            try:
                if any(choice is None for choice in _options(color, params)):
                    found("unlit", f"{what}'s outline has no color{_through(color)}")
            except _Unbounded as unbounded:
                unread(f"{what}'s outline color", unbounded.args[0])
        light = _light(looks)
        if light is None:
            continue
        kind, color, contrast, mean = light
        if _bare(contrast, params):
            found("bare-contrast", (
                f"{what} gives a contrast with no convention; write it as Weber(...), "
                f"Michelson(...) or RMS(...), whose value may be a parameter (engine "
                f"spec §4.12)"))
            continue
        try:
            each = list(itertools.product(*(_options(v, params) for v in (color, contrast, mean))))
        except _Unbounded as unbounded:
            unread(f"{what}'s light", unbounded.args[0])
            continue
        # A list, not a set: a `combine` that is not a string is refused, not hashed.
        how = [combine for shown, combine in combined if shown == looks]
        if how and all(combine in LIGHTLESS for combine in how):
            continue
        # A window or a scotoma reads no mean either, so with a multiplier it is still unread.
        multiplied = bool(how) and all(combine == "multiply" or combine in LIGHTLESS
                                       for combine in how)
        what += _through(color, contrast, mean)
        for color, contrast, mean in each:
            if kind == "flat":
                if color is None and contrast is None:
                    found("unlit", (
                        f"{what} has no light: give it a color, such as Gray(40) for 40 "
                        f"cd/m², or a Weber contrast against a declared background"))
                if color is not None and contrast is not None:
                    found("overspecified-color", (
                        f"{what} sets an absolute colour and a contrast of {contrast}; both "
                        f"claim to set the same physical quantity. Use one"))
                if isinstance(contrast, Contrast) and not isinstance(contrast, Weber):
                    found("contrast-convention", (
                        f"{what} is one flat light, and {type(contrast).__name__} contrast "
                        f"describes a pattern about its mean; a flat light takes a color or "
                        f"a Weber contrast"))
                if isinstance(contrast, Weber) and on_black:
                    found("weber-on-black", (
                        f"{what} is a Weber contrast against the background, and an eye's "
                        f"background is or can be black; {fix} (engine spec §7.5)"))
                continue
            if contrast is None:
                found("unlit", (
                    f"{what} has no contrast, so it is its mean alone; give it "
                    f"Michelson(...)"))
            elif isinstance(contrast, Contrast) and not isinstance(contrast, Michelson):
                found("contrast-convention", (
                    f"{what} is a sine grating, drawn at a Michelson contrast in this build; "
                    f"{type(contrast).__name__} contrast for patterns arrives with the "
                    f"pattern fills (engine build A3)"))
            if mean is None and on_black and not multiplied:
                found("unlit", (
                    f"{what}'s mean is whatever is behind it, and an eye's background is "
                    f"or can be black, so it may draw nothing; {fix}, or declare its mean"))
            if mean is not None and not isinstance(mean, P) and any(mean != b for b in backgrounds):
                found("luminance-step", (
                    f"{what}'s mean {mean} differs from the background, so a luminance step "
                    f"sits under the pattern (engine spec §4.3: always a warning)"),
                    blocking=False,
                    accepted_in=SESSION_KINDS)  # Always a warning, in every kind (N§R3).
    findings += _cone_color_faults(trial, params, on_black, fix)
    return findings


def _cone_color_faults(trial: Trial, params: dict[str, Param], on_black: bool,
                       fix: str) -> list[Finding]:
    """A cone color (`DKL`, `ConeContrast`) is a contrast about its background in cone terms, so
    **it needs a background that is lit** (engine spec §7.5; the PI, N§4 batch 3: "It must
    declare one"; A1's call 6) **and one background**: through the stereoscope, a trial whose
    eyes' backgrounds differ as written is refused one, since the same color would be two
    different lights (the engine A2 plan's call 10). One finding each, naming every carrier."""
    carriers = sorted({what for what, color in _colors(trial, params)
                       if isinstance(color, CONE_COLORS) and not what.startswith("the trial's ")})
    if not carriers:
        return []
    findings = []
    if on_black:
        findings.append(Finding("cone-color-on-black", (
            f"{'; '.join(carriers)}: a cone color is relative to the background, and an eye's "
            f"background is or can be black; {fix} (engine spec §7.5)")))
    left, right = (_backgrounds(trial) * 2)[:2]
    if trial.view == "stereoscope" and left != right:
        findings.append(Finding("cone-color-two-backgrounds", (
            f"{'; '.join(carriers)}: a cone color is relative to the background, and the two eyes' "
            f"backgrounds differ ({left} and {right}), so it would be two lights; give both eyes "
            f"one background, or write the color as an absolute light (xyY)")))
    return findings


def _parts(value, params: dict[str, Param], inside: frozenset[str] = frozenset()) -> list:
    """`value` and every block inside it, depth first, **a parameter's choices included**.
    It stops at an `Array` and at an appearance a parameter offers: `_appearances` yields
    both as appearances of their own, so descending would report a fault in one twice. It
    stops too at a parameter it is already inside, whose choices it is walking already;
    `_self_referring` refuses that parameter, once (XC-263)."""
    from wl_xcon.task import Appearance

    if isinstance(value, P):
        if value.name in inside:
            return []
        param = params.get(value.name)
        return [
            part
            for choice in (param.choices if param is not None else ())
            if not isinstance(choice, Appearance)
            for part in _parts(choice, params, inside | {value.name})
        ]
    if not dataclasses.is_dataclass(value):
        return []
    found = [value]
    if isinstance(value, Array):
        return found
    for f in dataclasses.fields(value):
        found.extend(_parts(getattr(value, f.name), params, inside))
    return found


def _self_referring(params: dict[str, Param]) -> list[str]:
    """Every parameter whose choices name it, directly or through other parameters'
    choices (XC-263). It has no value a trial could bind, since each would hold itself, and
    a walk that follows a parameter into its choices would follow it round forever: those
    walks stop where they meet a name they are inside, and it is refused here."""
    named = {name: {ref.name for ref in _iter_param_refs(param.choices)}
             for name, param in params.items()}
    found = []
    for name in named:
        seen: set[str] = set()
        frontier = list(named[name])
        while frontier:
            other = frontier.pop()
            if other == name:
                found.append(name)
                break
            if other not in seen:
                seen.add(other)
                frontier.extend(named.get(other, ()))
    return found


def _area(points) -> float | None:
    """The area a closed outline through `points` encloses (the shoelace formula), or
    `None` when a point is not a pair of literal numbers."""
    if not all(isinstance(point, (tuple, list)) and len(point) == 2
               and all(_is_number(c) for c in point) for point in points):
        return None
    ring = list(points)
    return abs(sum(x0 * y1 - x1 * y0
                   for (x0, y0), (x1, y1) in zip(ring, ring[1:] + ring[:1]))) / 2.0


def _block_faults(trial: Trial) -> list[Finding]:
    """Degenerate values in what is drawn, refused here so the drawer never meets them:
    a size is a positive full width, a contrast stays inside its convention, a light is
    not negative, a ring's inside is inside it, a shape has enough points (engine spec
    §4.2, §5.2). In the stimuli and in the backgrounds.

    **Each rule holds at every value a parameter can take**, each choice or both ends of its
    range, as check 8 measures a position; a parameter in one of these fields that offers
    neither cannot be bounded, and is refused rather than passed (engine A1 final review).

    **And every value is of its field's kind** (XC-245, XC-264, XC-265): a number where a
    number belongs, a color where a light does, an appearance where a stimulus's looks do,
    and a shape, a fill, an edge or an outline where a `Look`'s are, each choice of a
    parameter included. A value of another kind passed every rule above unread, and
    `resolve` met it first. A parameter whose choices name it is refused too (XC-263)."""
    from wl_xcon import look
    from wl_xcon.photometry import Michelson, Weber
    from wl_xcon.screen import LIGHTLESS
    from wl_xcon.task import Annulus, Appearance, Polygon

    params = {p.name: p for p in trial.params}
    findings: list[Finding] = []

    def bad(detail: str) -> None:
        finding = Finding("bad-block", detail)
        if finding not in findings:  # one parameter, or one block, met twice
            findings.append(finding)

    def values(part, attr: str) -> list[tuple[float, str]]:
        """Each number `part.attr` can be, with how to say it ("Disc.size is 0", "Disc.size
        can be -1 (parameter 's')"); a parameter that cannot be bounded is refused here."""
        raw = getattr(part, attr)
        name = f"{type(part).__name__}.{attr}"
        try:
            reached = _reach(raw, params)
        except _Unbounded as unbounded:
            bad(f"{name} is parameter {unbounded.args[0]!r}, which has neither a two-sided "
                f"range nor numeric choices, so it cannot be bounded")
            return []
        if isinstance(raw, P):
            return [(v, f"{name} can be {v:g} (parameter {raw.name!r})") for v in reached]
        return [(v, f"{name} is {v:g}") for v in reached]

    def first(pairs, fails) -> None:
        """Refuse the first value that fails, with what it says."""
        for v, said in pairs:
            if fails(v):
                bad(said)
                return

    def kind(what: str, raw, fits, noun: str) -> None:
        """Refuse the first value `raw` can hold that is not `noun`: a literal, or each
        choice of a parameter (one offering none is refused where the field is read)."""
        if isinstance(raw, P):
            offered = params[raw.name].choices if raw.name in params else ()
            pairs = [(c, f"{what} can be {c!r} (parameter {raw.name!r})") for c in offered]
        else:
            pairs = [(raw, f"{what} is {raw!r}")]
        first([(v, f"{said}, not {noun}") for v, said in pairs], lambda v: not fits(v))

    def light(v) -> bool:
        return v is None or isinstance(v, Color)

    def absolute(v) -> bool:
        return v is None or isinstance(v, (Gray, xyY))

    def shown(what: str, looks) -> None:
        """An appearance: a parameter offering none is refused, as one of another kind is."""
        if isinstance(looks, P) and not (looks.name in params and params[looks.name].choices):
            bad(f"{what} is parameter {looks.name!r}, which offers no appearances as choices")
        else:
            kind(what, looks, lambda v: isinstance(v, Appearance), "an appearance")

    lightless = [looks for looks, how in _combined(trial, params) if how in LIGHTLESS]
    for circular in _self_referring(params):
        bad(f"parameter {circular!r} refers to itself: one of its choices names it, directly or "
            f"through another parameter's choices, so it has no value a trial could bind")
    for _, action in actions_of(trial):
        if isinstance(action, Show):
            shown(f"{action.stimulus.name!r}'s appearance", action.stimulus.looks)
        elif isinstance(action, Update) and "looks" in action.changes():
            shown(f"{action.stimulus!r}'s appearance", action.looks)
    blocks = [part for looks in _appearances(trial) for part in _parts(looks, params)]
    for attr in ("background", "background_left", "background_right"):
        blocks += _parts(getattr(trial, attr), params)
        kind(f"the trial's {attr.replace('_', ' ')}", getattr(trial, attr), absolute,
             "an absolute light, Gray or xyY: what a contrast or a cone color is relative to")
    for part in blocks:
        name = type(part).__name__
        for f in dataclasses.fields(part):
            raw = getattr(part, f.name)
            if f.name in _NUMBERS:
                kind(f"{name}.{f.name}", raw,
                     lambda v, f=f: _is_number(v) or (v is None and f.default is None), "a number")
            if f.name in _LIGHTS:
                kind(f"{name}.{f.name}", raw, light, "a color")
            if f.name in _SIZES:
                first([(v, f"{said}; a size is a positive full width in degrees")
                       for v, said in values(part, f.name)], lambda v: v <= 0.0)
        if isinstance(part, Array):
            for attr in ("looks", "among"):
                shown(f"Array.{attr}", getattr(part, attr))
        if isinstance(part, Michelson):
            first([(v, f"{said}, outside [0, 1]") for v, said in values(part, "value")],
                  lambda v: not 0.0 <= v <= 1.0)
        if isinstance(part, Weber):
            first([(v, f"{said}: below -1 asks for negative light")
                   for v, said in values(part, "value")], lambda v: v < -1.0)
        if isinstance(part, Gray):
            first([(v, f"{said}: negative light") for v, said in values(part, "cd_m2")],
                  lambda v: v < 0.0)
        if isinstance(part, xyY):
            for attr in ("x", "y", "Y"):
                # Bounded here; whether the panel makes each value is `_color_faults`' test.
                values(part, attr)
        if isinstance(part, (look.Ring, Annulus)):
            inner, outer = values(part, "inner"), values(part, "outer")
            first(inner, lambda v: v < 0.0)
            if inner and outer and max(inner)[0] >= min(outer)[0]:
                bad(f"{name}'s inner diameter is not inside its outer: {max(inner)[1]}, "
                    f"{min(outer)[1]}")
        if isinstance(part, (look.RegularPolygon, Polygon)):
            first([(v, f"{said}; a polygon has at least 3 sides")
                   for v, said in values(part, "sides")], lambda v: v < 3)
        if isinstance(part, look.Vertices):
            if len(part.points) < 3:
                bad(f"Vertices has {len(part.points)} points; a polygon has at least 3")
            elif (area := _area(part.points)) is not None and area < 1e-12:
                bad(f"Vertices through {part.points} encloses no area: its points lie on one "
                    f"line, or its outline goes back over itself")
        if isinstance(part, look.Path) and len(part.points) < 2:
            bad(f"Path has {len(part.points)} point; a line has at least 2")
        if isinstance(part, look.Edge) and part.applies not in (None, *look.EDGE_APPLIES):
            bad(f"{name} applies to {part.applies!r}; one of {', '.join(look.EDGE_APPLIES)}")
        if isinstance(part, look.SineGrating):
            first([(v, f"{said}; tf is a speed in cycles per second, and `direction` says "
                       f"which way the bars move (engine spec §5.1)")
                   for v, said in values(part, "tf")], lambda v: v < 0.0)
        if isinstance(part, look.Look):
            # A block where its block belongs: `resolve` reads each as one, and met a value of
            # another kind first, as a bare TypeError (`check` itself, for an outline).
            kind("Look.shape", part.shape, lambda v: isinstance(v, look.Shape),
                 "a shape, such as look.Circle(size=1.0)")
            kind("Look.fill", part.fill, lambda v: isinstance(v, look.Fill),
                 "a fill, such as look.Flat(color=Gray(40.0))")
            kind("Look.edge", part.edge, lambda v: isinstance(v, look.Edge),
                 "an edge, such as look.Hard()")
            kind("Look.outline", part.outline, lambda v: v is None or isinstance(v, look.Outline),
                 "an outline, such as look.Outline(width=0.05, color=Gray(40.0)), or None")
            try:
                fills = _options(part.fill, params)
            except _Unbounded as unbounded:
                bad(f"the Look's fill is parameter {unbounded.args[0]!r}, which offers no "
                    f"choices, so its drift direction cannot be read")
                fills = []
            for fill in fills:
                if isinstance(fill, look.SineGrating) and fill.direction is not None:
                    _direction_faults(part, fill, params, bad)
                # One light has no contrast of its own to fade, and the drawer would fade its
                # opacity instead: the same light over the background, a different one over
                # another stimulus (call 2, XC-249).
                if isinstance(fill, look.Flat) and getattr(part.edge, "applies", None) == "contrast":
                    bad(f"{type(part.edge).__name__}.applies is 'contrast' on a flat fill: a flat "
                        f"light's edge fades its light, so `applies` is \"opacity\" (or left "
                        f"unset); \"contrast\" applies to a pattern")
            # A window or a scotoma draws no light, so has no contrast for its edge to shape:
            # the edge shapes what shows through it, whatever the fill (call 5).
            if getattr(part.edge, "applies", None) == "contrast" and any(
                    part == shown for shown in lightless):
                bad(f"{type(part.edge).__name__}.applies is 'contrast' on a window or a scotoma: "
                    f"it draws no light of its own, so its edge shapes what shows through it and "
                    f"`applies` is \"opacity\" (or left unset)")
    return findings


def _direction_faults(looks, grating, params: dict[str, Param], bad) -> None:
    """A grating's drift `direction` is across its bars: orientation + 90 or + 270 degrees
    (engine spec §5.1; PI, 2026-10-07). Every (orientation, direction) pair the two fields
    can take is held to it. A range names directions that are not across the bars, and one
    cannot be checked against a fixed direction, so either must offer choices."""
    direction, orientation = grating.direction, looks.orientation

    def choices(value, what: str, why: str) -> list[float] | None:
        if not isinstance(value, P):
            return _reach(value, params)
        offered = params[value.name].choices if value.name in params else ()
        if not offered or not all(_is_number(c) for c in offered):
            bad(f"{what} is parameter {value.name!r}, which offers no numeric choices; {why}")
            return None
        return [float(c) for c in offered]

    directions = choices(direction, "SineGrating.direction", (
        "a range names directions that are not across the bars, so offer choices such as "
        "(orientation + 90, orientation + 270)"))
    orientations = choices(orientation, "the grating's orientation", (
        "a range cannot be checked against a fixed direction, so offer choices, or leave "
        "`direction` out to drift toward orientation + 90"))
    for o in orientations or []:
        for d in directions or []:
            if abs(math.sin(math.radians(d - (o + 90.0)))) > 1e-9:
                bad(f"a grating with orientation {o:g} cannot drift toward {d:g} degrees: that is "
                    f"not across its bars. Write direction={o + 90:g} or {o + 270:g}, or leave "
                    f"`direction` out to drift toward {o + 90:g}")
                return


# --- Arrays ----------------------------------------------------------------


def _ranges(trial: Trial) -> dict[str, tuple[float, float]]:
    return {
        p.name: (p.low, p.high)
        for p in trial.params
        if p.low is not None and p.high is not None
    }


def _widest(value, ranges) -> tuple[float, float]:
    """The lowest and highest a value can take over its declared range."""
    if isinstance(value, P):
        low, high = ranges.get(value.name, (0.0, 0.0))
        return (low, high)
    return (float(value), float(value))


def _declared_window_names(trial: Trial) -> set[str]:
    """Window names a task has, including every one an array generates.

    An array's items are named `<of>.<i>` and are as declared as anything an author
    typed -- the whole point is that the author cannot type them, because how many
    there are is not known until a trial runs.
    """
    arrays = arrays_of(trial)
    ranges = _ranges(trial)
    names: set[str] = set()
    for window in trial.windows:
        if isinstance(window, ItemWindows):
            names |= {f"{window.of}.target", f"{window.of}.distractor"}
            array = arrays.get(window.of)
            if array is not None:
                highest = int(_widest(array.n, ranges)[1])
                names |= {f"{window.of}.{i}" for i in range(highest)}
        else:
            names.add(window.name)
    return names


def _coupling(trial: Trial) -> dict[str, object]:
    """Which stimulus each window scores, generated families included."""
    scores: dict[str, object] = {}
    for name in _declared_window_names(trial):
        scores[name] = None
    for window in trial.windows:
        if isinstance(window, ItemWindows):
            for name in list(scores):
                if name.startswith(f"{window.of}."):
                    scores[name] = window.of
        else:
            scores[window.name] = window.on
    return scores


def _array_faults(trial: Trial) -> list[Finding]:
    """An array's target must be one of its items, for every legal setting.

    Set size and target index are both live parameters, so an experimenter can put
    the target at position 6 of a four-item array between one trial and the next.
    Reasoning over declared ranges is the only way to catch that before it is a
    session rather than a load.
    """
    ranges = _ranges(trial)
    findings: list[Finding] = []
    for state, action in actions_of(trial):
        looks = getattr(getattr(action, "stimulus", None), "looks", None)
        if not isinstance(looks, Array):
            continue
        lowest_n = int(_widest(looks.n, ranges)[0])
        lowest_t, highest_t = (int(v) for v in _widest(looks.target, ranges))
        if lowest_t < 0 or highest_t >= lowest_n:
            findings.append(
                Finding(
                    "target-outside-array",
                    f"state {state!r} shows an array of as few as {lowest_n} items "
                    f"with a target index reaching {highest_t}; the target must be "
                    f"one of the items for every setting the console allows, not "
                    f"only the one it has today",
                )
            )
    return findings


# --- Stereograms -----------------------------------------------------------


def _stereogram_faults(trial: Trial) -> list[Finding]:
    """A stereogram is a relationship between two images, so it needs both."""
    ranges = _ranges(trial)
    findings: list[Finding] = []
    for state, action in actions_of(trial):
        stimulus = getattr(action, "stimulus", None)
        looks = getattr(stimulus, "looks", None)
        if not isinstance(looks, RDS):
            continue
        low, high = _widest(looks.correlation, ranges)
        if low < -1.0 or high > 1.0:
            findings.append(
                Finding(
                    "impossible-correlation",
                    f"state {state!r} shows a stereogram whose correlation reaches "
                    f"{low if low < -1.0 else high:g}; correlation runs from -1 "
                    f"(anticorrelated) through 0 (uncorrelated) to +1. A value "
                    f"outside that is not a stronger stimulus, it is not a stimulus",
                )
            )
        if getattr(stimulus, "eye", "both") != "both":
            findings.append(
                Finding(
                    "monocular-stereogram",
                    f"state {state!r} shows a stereogram to the "
                    f"{stimulus.eye} eye only; monocular presentation of one half "
                    f"is not a degraded stereogram, it is a field of random dots "
                    f"with no disparity -- and it would still run, still record, "
                    f"and still appear in a figure as a disparity condition",
                )
            )
    return findings


# --- Which eye ---------------------------------------------------------------

EYES = ("both", "left", "right")


def _eye_faults(trial: Trial) -> list[Finding]:
    """Per-eye criteria must name an eye, and must name one that can see.

    A window scoring the eye a stimulus is *not* shown to runs, records, and aborts
    every trial for a reason invisible in the data: the animal was doing the task
    perfectly with the eye nobody scored.
    """
    findings: list[Finding] = []
    shown_to = {
        action.stimulus.name: getattr(action.stimulus, "eye", "both")
        for _, action in actions_of(trial)
        if isinstance(action, Show)
    }
    for window in trial.windows:
        eye = window.eye
        name = getattr(window, "name", None) or f"{window.of}.*"
        if eye not in EYES:
            findings.append(
                Finding(
                    "unknown-eye",
                    f"window {name!r} scores eye {eye!r}; it must be one of "
                    f"{', '.join(EYES)}. An unrecognised eye is not a criterion, "
                    f"it is a guard that is silently never true",
                )
            )
            continue
        on = getattr(window, "on", None)
        if not isinstance(on, str):
            continue
        stimulus_eye = shown_to.get(on)
        if stimulus_eye is None or stimulus_eye == "both" or eye == "both":
            continue
        if stimulus_eye != eye:
            findings.append(
                Finding(
                    "wrong-eye-criterion",
                    f"window {name!r} scores the {eye} eye against stimulus "
                    f"{on!r}, which is shown only to the {stimulus_eye} eye; the "
                    f"animal can do the task perfectly and abort every trial",
                )
            )
    return findings


# --- Reasoning over the whole parameter space ---------------------------------
#
# A task with live parameters is not one configuration, it is a space of them. A
# check against current values proves the task happens not to be broken today; a
# check against declared ranges proves an experimenter cannot break it from the
# console between two trials.


def _closest_approach(a: Window, b: Window, ranges) -> tuple[float, float]:
    """Least possible centre separation, and greatest possible summed radius."""
    a_x, a_y = a.at
    b_x, b_y = b.at
    gaps = [
        math.hypot(ax - bx, ay - by)
        for ax in _extremes(a_x, ranges)
        for ay in _extremes(a_y, ranges)
        for bx in _extremes(b_x, ranges)
        for by in _extremes(b_y, ranges)
    ]
    reach = max(_extremes(a.radius, ranges)) + max(_extremes(b.radius, ranges))
    return (min(gaps), reach)


def _overlapping_windows(trial: Trial) -> list[Finding]:
    """No two windows a state scores can contain the same point.

    A gaze position inside both satisfies both guards, and the loop takes whichever
    transition is listed first -- so which one scores is decided by editing order.
    That silently relabels errors as correct trials or the reverse, in a task where
    nothing reads as wrong.

    Only windows scored by the *same state* are compared: two windows in different
    states are never both live, and a task that reuses a position across states is
    doing something ordinary.
    """
    ranges = _ranges(trial)
    by_name = {w.name: w for w in trial.windows if not isinstance(w, ItemWindows)}
    findings: list[Finding] = []
    seen: set[tuple[str, str]] = set()
    for state in trial.states:
        scored = [
            name
            for edge in state.go
            for name in _window_refs(edge.guard)
            if name in by_name
        ]
        for i, first in enumerate(scored):
            for second in scored[i + 1 :]:
                pair = tuple(sorted((first, second)))
                if first == second or pair in seen:
                    continue
                seen.add(pair)
                gap, reach = _closest_approach(by_name[first], by_name[second], ranges)
                if gap < reach:
                    findings.append(
                        Finding(
                            "overlapping-windows",
                            f"state {state.name!r} scores {first!r} and {second!r}, "
                            f"which can come within {gap:.2f}° while their radii "
                            f"sum to {reach:.2f}°; a gaze position inside both "
                            f"satisfies both guards, and which one scores is decided "
                            f"by the order the transitions happen to be written in",
                        )
                    )
    return findings


def _unreachable_timeouts(trial: Trial) -> list[Finding]:
    """A time bound that another always beats is dead code.

    It reads as a safety net, so the case it was meant to catch goes unprotected and
    nobody notices -- the line is right there. Ranges again: two bounds whose ranges
    cross are both live, because either can win depending on the setting.
    """
    ranges = _ranges(trial)
    findings: list[Finding] = []
    for state in trial.states:
        bounds = [
            (edge, _widest(edge.guard.seconds, ranges))
            for edge in state.go
            if isinstance(edge.guard, After) and edge.guard.since is None
        ]
        for index, (edge, (low, _high)) in enumerate(bounds):
            beaten = [
                other
                for position, (other, (_o_low, o_high)) in enumerate(bounds)
                if position != index and o_high < low
            ]
            if beaten:
                findings.append(
                    Finding(
                        "unreachable-timeout",
                        f"state {state.name!r} can never reach its "
                        f"{_target_name(edge.to)} timeout: another `After` on the "
                        f"same state always fires first, for every legal setting",
                    )
                )
    return findings


def _target_name(target: object) -> str:
    return target.name if isinstance(target, Outcome) else repr(target)


def _crowded_arrays(trial: Trial) -> list[Finding]:
    """An array's own items must not overlap, for any legal setting.

    Set size, eccentricity and window radius are all live, so crowding is something
    an experimenter dials in between two trials: twelve items on a small ring with
    generous windows overlap, and a saccade to one distractor is then scored against
    another, or against the target. **Nobody ever reads these windows** -- they are
    generated, which is the whole point of `ItemWindows` and the reason this needs a
    check rather than an author's eye.

    The worst case is the most items on the smallest ring with the largest windows:
    adjacent centres are `2 R sin(pi/n)` apart, and two windows touch when that
    falls below their summed radius.
    """
    arrays = arrays_of(trial)
    ranges = _ranges(trial)
    findings: list[Finding] = []
    for declared in trial.windows:
        if not isinstance(declared, ItemWindows):
            continue
        array = arrays.get(declared.of)
        if array is None:
            continue
        most = max(_extremes(array.n, ranges))
        tightest = min(_extremes(array.radius, ranges))
        widest = max(_extremes(declared.radius, ranges))
        if most < 2:
            continue
        spacing = 2.0 * tightest * math.sin(math.pi / most)
        if spacing < 2.0 * widest:
            findings.append(
                Finding(
                    "crowded-array",
                    f"array {declared.of!r} can put {int(most)} items on a "
                    f"{tightest:g}° ring, {spacing:.2f}° apart, with windows of "
                    f"{widest:g}° radius; adjacent items would overlap and a "
                    f"saccade to one would be scored against another",
                )
            )
    return findings


# --- Which setup -------------------------------------------------------------

#: What `Trial.view` may say (direct-view spec §3): one setup, or either.
TRIAL_VIEWS = (*VIEWS, "either")


def _nonzero(value) -> bool:
    """Whether a disparity can be other than zero: a parameter can."""
    return isinstance(value, P) or bool(_literal(value))


def _modulates(looks, params: dict[str, Param], inside: frozenset[str] = frozenset()) -> bool:
    """Whether a stimulus can multiply the contrast below it, for every value it can take:
    a pattern, or a flat Weber contrast (a gain of 1 + c). An absolute light names no gain.
    An `Array` modulates only if each of its items does, and a parameter only if each of
    its choices does; one with no choices to read is `_Unbounded`, naming it. One met again
    inside its own choices adds nothing: they are being read already, and it is refused as
    referring to itself (`_self_referring`)."""
    from wl_xcon.photometry import Weber

    def options(value, field: str) -> list:
        try:
            return _options(value, params)
        except _Unbounded as unbounded:
            raise _Unbounded(unbounded.args[0], field) from None

    if isinstance(looks, P):
        if looks.name in inside:
            return True
        return all(_modulates(choice, params, inside | {looks.name})
                   for choice in options(looks, "appearance"))
    if isinstance(looks, Array):
        return _modulates(looks.looks, params, inside) and _modulates(looks.among, params, inside)
    light = _light(looks)
    if light is None:
        return True  # a fill engine build A3 defines: checked where it is defined
    kind, color, contrast, _ = light
    return kind == "grating" or all(
        c is None and isinstance(k, Weber)
        for c in options(color, "color")
        for k in options(contrast, "contrast")
    )


def _declares_mean(looks, params: dict[str, Param], inside: frozenset[str] = frozenset()) -> bool:
    """Whether a stimulus can be a grating that declares its own mean, at any value it can
    take. Multiplying draws a grating's modulation alone (`exact._gain`), so a mean it
    declares would be ignored without a word (call 1, XC-253). An `Array` can if either of
    its items can, a parameter if any of its choices can, a mean parameter if any choice is
    a light. One with no choices to read declares none here: it is refused where its light
    or its modulation is read."""
    if isinstance(looks, P):
        if looks.name in inside:
            return False
        param = params.get(looks.name)
        return any(_declares_mean(choice, params, inside | {looks.name})
                   for choice in (param.choices if param is not None else ()))
    if isinstance(looks, Array):
        return (_declares_mean(looks.looks, params, inside)
                or _declares_mean(looks.among, params, inside))
    light = _light(looks)
    if light is None or light[0] != "grating":
        return False
    mean = light[3]
    if isinstance(mean, P):
        param = params.get(mean.name)
        return any(choice is not None for choice in (param.choices if param is not None else ()))
    return mean is not None


def _placement_faults(trial: Trial) -> list[Finding]:
    """How a stimulus is placed and layered, as the drawer needs it (engine spec §4.4,
    §5.4): opacity in [0, 1], a whole-number layer, a known combination, and per-eye
    positions given in pairs (an update may move one eye of a stimulus that has both),
    never with a disparity or an updated `at`, cleared only with an `at`, and only on the
    stereoscope."""
    from wl_xcon.task import COMBINE, Show, Update

    params = {p.name: p for p in trial.params}
    findings: list[Finding] = []

    def refuse(code: str, detail: str) -> None:
        findings.append(Finding(code, detail))

    def unmodulated(looks) -> str:
        """Why `looks` cannot multiply the contrast below it, or "" if it can."""
        try:
            return "" if _modulates(looks, params) else "it can be an absolute light, which has none"
        except _Unbounded as unbounded:
            field = unbounded.args[1] if len(unbounded.args) > 1 else "appearance"
            return (f"its {field} is parameter {unbounded.args[0]!r}, which offers no "
                    f"choices, so its modulation cannot be read")

    updated = _as_updated(trial)
    for _, action in actions_of(trial):
        if isinstance(action, Show):
            s = action.stimulus
            name, looks = s.name, s.looks
            sets = {"opacity": s.opacity, "layer": s.layer, "combine": s.combine,
                    "disparity": s.disparity}
            sets.update({k: v for k, v in (("at_left", s.at_left), ("at_right", s.at_right))
                         if v is not None})
        elif isinstance(action, Update):
            name, looks, sets = action.stimulus, None, action.changes()
            # Every combination `_as_updated` says this update can leave on the
            # display, so an update after another update is checked as well as one
            # after a `Show`.
            left = updated.get(id(action), [])
            if any((c.at_left is not None or c.at_right is not None) and _nonzero(c.disparity)
                   for c in left):
                refuse("per-eye-misused", (
                    f"an update of {name!r} can leave it with both per-eye positions and a "
                    f"disparity, from the update itself or from what it was shown and "
                    f"updated with; they are two ways to say one thing (engine spec §5.4)"))
            why = next((w for c in left if c.combine == "multiply" and (w := unmodulated(c.looks))),
                       "")
            if why:
                refuse("multiply-needs-modulation", (
                    f"an update of {name!r} can leave it multiplying the contrast below it by "
                    f"its own modulation, and {why}; give it a Weber contrast or a pattern"))
            if any(c.combine == "multiply" and _declares_mean(c.looks, params) for c in left):
                refuse("bad-placement", (
                    f"an update of {name!r} can leave it a grating that multiplies the contrast "
                    f"below by its modulation, so its declared mean would be ignored; remove it"))
            # Per-eye positions are drawn in place of `at` (`screen._eyes`), so an `at` that
            # can meet them changes nothing on the screen (XC-259).
            if "at" in sets and any(c.at_left is not None or c.at_right is not None for c in left):
                refuse("per-eye-misused", (
                    f"an update of {name!r} sets `at`, but {name!r} has per-eye positions, so "
                    f"`at` is not used; update `at_left` and `at_right`, or set both to None in "
                    f"the same update to draw it at `at`"))
            # Clearing a per-eye position draws the stimulus at `at` again, so the update that
            # clears one says where (the A1 follow-ups, Task 4's ruling): an `at` left from the
            # `Show` is the one XC-259's refusal tells the author is not used.
            if "at" not in sets and any(eye in sets and sets[eye] is None
                                        for eye in ("at_left", "at_right")):
                refuse("per-eye-misused", (
                    f"an update of {name!r} clears a per-eye position without giving `at`, so "
                    f"it would be drawn at the `at` it was shown with; give `at` and clear both "
                    f"per-eye positions in the same update"))
            # One eye's position alone keeps the other eye's (XC-260), so the other must be
            # there whatever it was shown and updated with. (One never shown at all is
            # `absent-stimulus`.)
            if ("at_left" in sets) != ("at_right" in sets) and any(
                    (c.at_left is None) != (c.at_right is None) for c in left):
                refuse("per-eye-misused", (
                    f"an update of {name!r} gives one eye's position, and {name!r} can be on the "
                    f"display without the other's; give `at_left` and `at_right` together, or "
                    f"show it with both"))
        else:
            continue
        # At every value a parameter can take, as `_block_faults` holds a block's values.
        opacity = sets.get("opacity")
        if "opacity" in sets and not (_is_number(opacity) or isinstance(opacity, P)):
            refuse("bad-placement", f"{name!r}'s opacity is {opacity!r}, not a number")
        try:
            outside = [v for v in _reach(opacity, params) if not 0.0 <= v <= 1.0]
        except _Unbounded as unbounded:
            refuse("bad-placement", (
                f"{name!r}'s opacity is parameter {unbounded.args[0]!r}, which has neither a "
                f"two-sided range nor numeric choices, so it cannot be bounded to [0, 1]"))
            outside = []
        if outside:
            said = (f"can be {outside[0]:g} (parameter {opacity.name!r})" if isinstance(opacity, P)
                    else f"{outside[0]:g}")
            refuse("bad-placement", f"{name!r}'s opacity {said} is outside [0, 1]")
        # A disparity is degrees, each choice of a parameter included: `_disparity_is_zero`
        # and `screen._eyes` read it as a number.
        if "disparity" in sets:
            disparity = sets["disparity"]
            offered = ([(c, f"can be {c!r} (parameter {disparity.name!r})")
                        for c in (params[disparity.name].choices if disparity.name in params else ())]
                       if isinstance(disparity, P) else [(disparity, f"is {disparity!r}")])
            said = next((said for v, said in offered if not _is_number(v)), None)
            if said is not None:
                refuse("bad-placement", f"{name!r}'s disparity {said}, not a number of degrees")
        layer = sets.get("layer", 0)
        if isinstance(layer, bool) or not isinstance(layer, int):
            refuse("bad-placement", f"{name!r}'s layer {layer!r} is not a whole number")
        if "combine" in sets:
            if sets["combine"] not in COMBINE:
                refuse("bad-placement", (
                    f"{name!r} combines as {sets['combine']!r}; one of {', '.join(COMBINE)}"))
            elif sets["combine"] == "multiply" and (why := unmodulated(looks)):
                refuse("multiply-needs-modulation", (
                    f"{name!r} multiplies the contrast below it by its own modulation, and "
                    f"{why}; give it a Weber contrast or a pattern"))
            if sets["combine"] == "multiply" and _declares_mean(looks, params):
                refuse("bad-placement", (
                    f"{name!r} is a grating that multiplies the contrast below by its "
                    f"modulation, so its declared mean would be ignored; remove it"))
        if isinstance(action, Show) and ("at_left" in sets) != ("at_right" in sets):
            refuse("per-eye-misused", f"{name!r} gives one eye's position without the other's")
        if "at_left" in sets or "at_right" in sets:
            if _nonzero(sets.get("disparity", 0.0)):
                refuse("per-eye-misused", (
                    f"{name!r} gives per-eye positions and a disparity; they are two ways "
                    f"to say one thing (engine spec §5.4)"))
            if trial.view != "stereoscope":
                refuse("per-eye-misused", (
                    f"{name!r} gives per-eye positions in a task written for "
                    f"{trial.view!r}; only the stereoscope shows each eye its own image"))
    return findings


def _trial_display_faults(trial: Trial) -> list[Finding]:
    """The trial's own display settings: a known periphery (engine spec §5.3), and per-eye
    backgrounds only on the stereoscope (§4.4)."""
    from wl_xcon.task import PERIPHERY

    findings: list[Finding] = []
    if trial.periphery not in PERIPHERY:
        findings.append(Finding("bad-periphery", (
            f"periphery {trial.periphery!r} is not one of {', '.join(PERIPHERY)}")))
    if trial.view != "stereoscope" and (
        trial.background_left is not None or trial.background_right is not None
    ):
        findings.append(Finding("per-eye-background", (
            f"a per-eye background in a task written for {trial.view!r}; only the "
            f"stereoscope shows each eye its own")))
    return findings


def _view_faults(trial: Trial, geometry: Geometry | None) -> list[Finding]:
    """A task says which setup it is written for, and is held to it (direct-view
    spec §3).

    **Stereo content needs the stereoscope, with or without a geometry**: it is a
    property of the task, not of the session, so it is refused at every load. **Against
    a geometry, a task written for the other setup is refused, naming both**, so a
    caller that passes the session's geometry has nothing else to do. `taskd` and
    `wlx check` are those callers (`wlx run --rig --view` and `wlx check --rig`, which
    take the field from the rig file); without a geometry (`wlx review`, the tests)
    only the stereo-content finding is reachable. An unrecognized `view` is refused
    outright, as an unrecognized eye is: it would be checked as neither.
    """
    if trial.view not in TRIAL_VIEWS:
        return [
            Finding(
                "unknown-view",
                f"the task's view is {trial.view!r}; it must be one of "
                f"{', '.join(TRIAL_VIEWS)}. An unrecognized setup is not a "
                f"declaration, and nothing could be checked against it",
            )
        ]
    findings: list[Finding] = []
    if trial.view != "stereoscope":
        findings += [
            Finding(
                "needs-stereoscope",
                f"{what}, and the task declares view={trial.view!r}; only the "
                f"stereoscope shows each eye its own image, so declare "
                f"view='stereoscope'. On an unmirrored screen both eyes see both "
                f"images, which is not the stimulus the task describes",
            )
            for what in _stereo_content(trial)
        ]
    if geometry is not None and trial.view not in ("either", geometry.view):
        findings.append(
            Finding(
                "wrong-setup",
                f"the task is written for {trial.view!r} and is checked against "
                f"{geometry.view!r}; a task written for one setup is refused in the "
                f"other (direct-view spec §3)",
            )
        )
    return findings


def _has_rds(looks) -> bool:
    """Whether an appearance is a random-dot stereogram. `_appearances` reports an
    `Array`'s own `looks`/`among` as appearances of their own, so an array of
    stereograms is found through them (review I1(b)), once."""
    return isinstance(looks, RDS)


def _disparity_is_zero(value, trial: Trial) -> bool:
    """Whether a disparity value is provably zero (review I1(a)).

    A literal is zero only at exactly `0.0`, and one that is no number is not provably
    zero (`_placement_faults` refuses it; reading it as a float raised out of `check`). A
    parameter is zero only if it is *declared* and its whole domain is zero: every
    `choices` entry is `0.0`, or `low == high == 0.0`. An undeclared parameter -- one
    `_ranges` cannot see because it has neither a two-sided range nor `choices` -- is not
    provably anything, so it counts as stereo content rather than failing open the way
    `_widest`'s `(0, 0)` fallback did.
    """
    if not isinstance(value, P):
        return _literal(value) == 0.0
    param = next((p for p in trial.params if p.name == value.name), None)
    if param is None:
        return False
    if param.choices:
        return all(choice == 0.0 for choice in param.choices)
    if param.low is not None and param.high is not None:
        return param.low == 0.0 and param.high == 0.0
    return False


def _stereo_content(trial: Trial) -> list[str]:
    """Everything a task shows that only the stereoscope can: disparity, a
    random-dot stereogram (direct-view spec §3), and a stimulus shown to one eye.

    **Parameter choices count**, for `_appearances`' reason: an appearance only a
    parameter selects is as real as one written into a `Show`.
    """
    found = [
        "it can show a random-dot stereogram"
        for looks in _appearances(trial)
        if _has_rds(looks)
    ]
    for state, action in actions_of(trial):
        if isinstance(action, Show):
            name, carrier = action.stimulus.name, action.stimulus
        elif isinstance(action, Update):
            name, carrier = action.stimulus, action
        else:
            continue
        if not isinstance(carrier.disparity, Unchanged) and not _disparity_is_zero(
            carrier.disparity, trial
        ):
            found.append(f"state {state!r} gives {name!r} disparity")
        if not isinstance(carrier.eye, Unchanged) and carrier.eye != "both":
            found.append(f"state {state!r} shows {name!r} to the {carrier.eye} eye only")
    return found
