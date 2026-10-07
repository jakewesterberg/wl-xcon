"""Load-time checks (S1 §9). A task failing any of these is refused at load."""

from __future__ import annotations

import dataclasses
import itertools
import math

from wl_xcon.codes import PROVISIONAL, Allocation
from wl_xcon.components import Registry
from wl_xcon.findings import Finding
from wl_xcon.geometry import VIEWS, Geometry
from wl_xcon.photometry import D65, DKL, Calibration, Color, Gray, unrealizable, xyY
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


def _literal(value) -> float | None:
    """A literal number, or None for a parameter, a missing value or anything else."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _colors(trial: Trial, params: dict[str, Param]):
    """Every color a trial can put on screen, with what carries it: each appearance's,
    each block's (a flat fill, a grating's mean, an outline), and the backgrounds. A color
    that is a parameter is each of its choices; one offering none to read is refused by
    `_light_faults`, so it is not one here."""
    from wl_xcon import look

    def each(what, color):
        try:
            choices = _options(color, params)
        except _Unbounded:
            return
        for choice in choices:
            if choice is not None:
                yield (what if choice is color
                       else f"{what} (a choice of parameter {color.name!r})"), choice

    for looks in _appearances(trial):
        what = type(looks).__name__
        if isinstance(looks, look.Look):
            for part in (looks.fill, looks.outline):
                for attr in ("color", "mean"):
                    yield from each(f"{what}'s {type(part).__name__}", getattr(part, attr, None))
        else:
            yield from each(what, getattr(looks, "color", None))
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
    findings: list[Finding] = []
    for what, color in _colors(trial, params):
        lights = [color]
        if isinstance(color, Gray):
            # Absolute luminance on the default calibration is a session warning, which
            # the warnings list carries (engine build B, XC-243); with a calibration it is
            # checked like any light, at each luminance a parameter can take: both ends of
            # its range, or each choice.
            if panel is None:
                continue
            try:
                lights = [xyY(D65[0], D65[1], v) for v in _reach(color.cd_m2, params)]
            except _Unbounded:
                continue  # refused as a bad block: it cannot be bounded
        for light in lights:
            findings += _one_color(what, light, panel)
    return findings


def _one_color(what: str, color, panel: Calibration | None) -> list[Finding]:
    """One light against the calibration, or against its absence."""
    if panel is None:
        return [
            Finding(
                "uncalibrated-color",
                f"{what} asks for {color}, but no display calibration was "
                f"supplied; colour is a physical claim and this one is "
                f"unmeasured",
            )
        ]
    findings: list[Finding] = []
    if isinstance(color, DKL) and color.lum == 0.0 and color.magnitude() > 0.0:
        if not panel.observer:
            findings.append(
                Finding(
                    "unstated-observer",
                    f"{what} claims isoluminance, but the calibration measured "
                    f"{panel.measured_on} does not say whose luminous efficiency "
                    f"it used; a human V(lambda) makes a stimulus that is "
                    f"isoluminant for nobody in the room",
                )
            )
    why = unrealizable(color, panel)
    if why is not None:
        findings.append(
            Finding("unrealizable-color", f"{what} asks for {color}: {why}")
        )
    return findings


# --- Light and contrast (engine build A1) ----------------------------------

#: Block fields that are full widths in degrees, so must be positive (spec §5.2).
_SIZES = ("size", "width", "height", "length", "thickness", "outer", "sigma", "aperture")


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


def _black(color, params: dict[str, Param]) -> bool:
    """Whether a background can be black: the default, a zero luminance, or a parameter
    whose choices or range reach one. One that cannot be read or bounded can, failing
    closed."""
    try:
        if isinstance(color, P):
            return any(_black(choice, params) for choice in _options(color, params))
        if color is None:
            return True
        if isinstance(color, Gray):
            return any(v <= 0.0 for v in _reach(color.cd_m2, params))
    except _Unbounded:
        return True
    return isinstance(color, xyY) and color.Y == 0.0


def _background_fix(backgrounds: list, params: dict[str, Param]) -> str:
    """What to write so an eye's background is not black: raise the low end of a declared
    range that reaches 0, otherwise declare the background."""
    for background in backgrounds:
        light = background.cd_m2 if isinstance(background, Gray) else None
        param = params.get(light.name) if isinstance(light, P) else None
        if param is not None and param.low is not None and param.high is not None \
                and param.low <= 0.0:
            return (f"raise the low end of parameter {param.name!r}'s range, which the "
                    f"background is, above 0")
    return "declare the trial's background"


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
    exactly the lights the lab makes live."""
    from wl_xcon import look
    from wl_xcon.photometry import Contrast, Michelson, Weber

    params = {p.name: p for p in trial.params}
    backgrounds = _backgrounds(trial)
    on_black = any(_black(b, params) for b in backgrounds)
    fix = _background_fix(backgrounds, params)
    findings: list[Finding] = []

    def found(code: str, detail: str, blocking: bool = True) -> None:
        finding = Finding(code, detail, blocking=blocking)
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
        if isinstance(looks, look.Look) and looks.outline is not None:
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
            if mean is None and on_black:
                found("unlit", (
                    f"{what}'s mean is whatever is behind it, and an eye's background is "
                    f"or can be black, so it may draw nothing; {fix}, or declare its mean"))
            if mean is not None and not isinstance(mean, P) and any(mean != b for b in backgrounds):
                found("luminance-step", (
                    f"{what}'s mean {mean} differs from the background, so a luminance step "
                    f"sits under the pattern (engine spec §4.3: always a warning)"),
                    blocking=False)
    return findings


def _parts(value, params: dict[str, Param]) -> list:
    """`value` and every block inside it, depth first, **a parameter's choices included**.
    It stops at an `Array` and at an appearance a parameter offers: `_appearances` yields
    both as appearances of their own, so descending would report a fault in one twice."""
    from wl_xcon.task import Appearance

    if isinstance(value, P):
        param = params.get(value.name)
        return [
            part
            for choice in (param.choices if param is not None else ())
            if not isinstance(choice, Appearance)
            for part in _parts(choice, params)
        ]
    if not dataclasses.is_dataclass(value):
        return []
    found = [value]
    if isinstance(value, Array):
        return found
    for f in dataclasses.fields(value):
        found.extend(_parts(getattr(value, f.name), params))
    return found


def _block_faults(trial: Trial) -> list[Finding]:
    """Degenerate values in what is drawn, refused here so the drawer never meets them:
    a size is a positive full width, a contrast stays inside its convention, a light is
    not negative, a ring's inside is inside it, a shape has enough points (engine spec
    §4.2, §5.2). In the stimuli and in the backgrounds.

    **Each rule holds at every value a parameter can take**, each choice or both ends of its
    range, as check 8 measures a position; a parameter in one of these fields that offers
    neither cannot be bounded, and is refused rather than passed (engine A1 final review)."""
    from wl_xcon import look
    from wl_xcon.photometry import Michelson, Weber
    from wl_xcon.task import Annulus, Polygon

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

    blocks = [part for looks in _appearances(trial) for part in _parts(looks, params)]
    for attr in ("background", "background_left", "background_right"):
        blocks += _parts(getattr(trial, attr), params)
    for part in blocks:
        name = type(part).__name__
        for f in dataclasses.fields(part):
            if f.name in _SIZES:
                first([(v, f"{said}; a size is a positive full width in degrees")
                       for v, said in values(part, f.name)], lambda v: v <= 0.0)
        if isinstance(part, Michelson):
            first([(v, f"{said}, outside [0, 1]") for v, said in values(part, "value")],
                  lambda v: not 0.0 <= v <= 1.0)
        if isinstance(part, Weber):
            first([(v, f"{said}: below -1 asks for negative light")
                   for v, said in values(part, "value")], lambda v: v < -1.0)
        if isinstance(part, Gray):
            first([(v, f"{said}: negative light") for v, said in values(part, "cd_m2")],
                  lambda v: v < 0.0)
        if isinstance(part, (look.Ring, Annulus)):
            inner, outer = values(part, "inner"), values(part, "outer")
            first(inner, lambda v: v < 0.0)
            if inner and outer and max(inner)[0] >= min(outer)[0]:
                bad(f"{name}'s inner diameter is not inside its outer: {max(inner)[1]}, "
                    f"{min(outer)[1]}")
        if isinstance(part, (look.RegularPolygon, Polygon)):
            first([(v, f"{said}; a polygon has at least 3 sides")
                   for v, said in values(part, "sides")], lambda v: v < 3)
        if isinstance(part, look.Vertices) and len(part.points) < 3:
            bad(f"Vertices has {len(part.points)} points; a polygon has at least 3")
        if isinstance(part, look.Path) and len(part.points) < 2:
            bad(f"Path has {len(part.points)} point; a line has at least 2")
        if isinstance(part, look.Edge) and part.applies not in (None, *look.EDGE_APPLIES):
            bad(f"{name} applies to {part.applies!r}; one of {', '.join(look.EDGE_APPLIES)}")
        if isinstance(part, look.SineGrating):
            first([(v, f"{said}; tf is a speed in cycles per second, and `direction` says "
                       f"which way the bars move (engine spec §5.1)")
                   for v, said in values(part, "tf")], lambda v: v < 0.0)
        if (isinstance(part, look.Look) and isinstance(part.fill, look.SineGrating)
                and part.fill.direction is not None):
            _direction_faults(part, params, bad)
    return findings


def _direction_faults(looks, params: dict[str, Param], bad) -> None:
    """A grating's drift `direction` is across its bars: orientation + 90 or + 270 degrees
    (engine spec §5.1; PI, 2026-10-07). Every (orientation, direction) pair the two fields
    can take is held to it. A range names directions that are not across the bars, and one
    cannot be checked against a fixed direction, so either must offer choices."""
    direction, orientation = looks.fill.direction, looks.orientation

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


def _modulates(looks, params: dict[str, Param]) -> bool:
    """Whether a stimulus can multiply the contrast below it, for every value it can take:
    a pattern, or a flat Weber contrast (a gain of 1 + c). An absolute light names no gain.
    An `Array` modulates only if each of its items does, and a parameter only if each of
    its choices does; one with no choices to read is `_Unbounded`, naming it."""
    from wl_xcon.photometry import Weber

    def options(value, field: str) -> list:
        try:
            return _options(value, params)
        except _Unbounded as unbounded:
            raise _Unbounded(unbounded.args[0], field) from None

    if isinstance(looks, P):
        return all(_modulates(choice, params) for choice in options(looks, "appearance"))
    if isinstance(looks, Array):
        return _modulates(looks.looks, params) and _modulates(looks.among, params)
    light = _light(looks)
    if light is None:
        return True  # a fill engine build A3 defines: checked where it is defined
    kind, color, contrast, _ = light
    return kind == "grating" or all(
        c is None and isinstance(k, Weber)
        for c in options(color, "color")
        for k in options(contrast, "contrast")
    )


def _placement_faults(trial: Trial) -> list[Finding]:
    """How a stimulus is placed and layered, as the drawer needs it (engine spec §4.4,
    §5.4): opacity in [0, 1], a whole-number layer, a known combination, and per-eye
    positions given in pairs, never with a disparity, and only on the stereoscope."""
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
        else:
            continue
        # At every value a parameter can take, as `_block_faults` holds a block's values.
        opacity = sets.get("opacity")
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
        if ("at_left" in sets) != ("at_right" in sets):
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

    A literal is zero only at exactly `0.0`. A parameter is zero only if it is
    *declared* and its whole domain is zero: every `choices` entry is `0.0`, or
    `low == high == 0.0`. An undeclared parameter -- one `_ranges` cannot see because
    it has neither a two-sided range nor `choices` -- is not provably anything, so it
    counts as stereo content rather than failing open the way `_widest`'s `(0, 0)`
    fallback did.
    """
    if not isinstance(value, P):
        return float(value) == 0.0
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
