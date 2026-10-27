"""Load-time checks (S1 §9). A task failing one that blocks is refused at load.

**Three severities** (`findings.Finding`): a refusal (`blocking`); a warning, acceptable in the
session kinds it names and asked once a session (engine spec §19.2); and a review note
(`blocking=False`, no kinds), which `wlx check` shows and no session refuses or asks. Since the
PI's rulings on XC-352 (2026-10-11: "warnings are more appropriate most of the time with an
explanation of why it may not be a good idea to use a value or follow a path you may think to
refuse. the experimenter needs free control most of the time"), dead code is a review note and a
task the rig can run but should perhaps not is a warning saying why; a refusal is kept for what
is unrunnable, undeclared or would make the record uninterpretable."""

from __future__ import annotations

import ast
import dataclasses
import itertools
import math
from pathlib import Path

from wl_xcon.codes import PROVISIONAL, Allocation
from wl_xcon.components import Registry
from wl_xcon.findings import SESSION_KINDS, Finding
from wl_xcon.geometry import (
    VIEWS, Geometry, circle_extent_deg, least_separation_deg, polar_box_deg, polar_deg,
    ring_spacing_deg,
)
from wl_xcon.photometry import (
    CONE_COLORS,
    D65,
    DKL,
    HELD_STANDARD,
    Calibration,
    Color,
    ConeContrast,
    Gray,
    background_cones,
    luminance_contrast,
    unrealizable,
    xyY,
)
from wl_xcon.run import LONGEST_TRIAL_S
from wl_xcon.task import (
    CHOSEN_BY,
    RDS,
    After,
    Array,
    Custom,
    Entered,
    Exited,
    Hide,
    Hold,
    Mark,
    NoChoice,
    ObjectWindows,
    Outcome,
    P,
    Param,
    Polar,
    Remembered,
    SaccadeTo,
    Show,
    Stimulus,
    Task,
    Touched,
    Trial,
    Unchanged,
    Update,
    Window,
    actions_of,
    arrays_of,
)
from wl_xcon.welfare import Deployment


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
        + _windows_left_behind(trial)
        + _color_faults(trial, calibration)
        + _light_faults(trial)
        + _block_faults(trial)
        + _array_faults(trial)
        + _unbounded_set_sizes(trial)
        + _stereogram_faults(trial)
        + _eye_faults(trial)
        + _overlapping_windows(trial)
        + _unreachable_timeouts(trial)
        + _crowded_arrays(trial)
        + _view_faults(trial, geometry)
        + _placement_faults(trial)
        + _trial_display_faults(trial)
        + _holds_cut_short(trial)
    )


def check_task(
    task: Task,
    allocation: Allocation = PROVISIONAL,
    components: Registry | None = None,
    geometry: Geometry | None = None,
    calibration: Calibration | None = None,
    deployment: Deployment | None = None,
    source: Path | str | None = None,
) -> list[Finding]:
    """The load-time checks of a task object (engine spec §3.5; engine build C1): each trial
    structure's own (`check`), named by its structure where the task has several (the engine C1
    plan's call 13), then what the task declares across them -- one set of settings and one setup,
    every setting's meaning (XC-288 §4.1), its reaction time and its choice (§4.3), a content its
    runs can record (§4.4), and each structure's counting table (engine spec §16.1; engine build
    C2a). **What a caller holds a task to is this**; `check` is one
    structure's part of it, and stays what a bare `Trial` is checked by.

    **Given the session's deployment**, a task that needs a fixed head is a warning in any but a
    head-fixed one, never a refusal (engine spec §20.1; XC-277; the PI, 2026-10-11); without one --
    `wlx check`, the review report -- nothing is said of it. **Given the file it was loaded
    from**, a position the file computes from `cos` and `sin` is a warning (`computed-position`;
    the PI, 2026-10-19)."""
    several = len(task.structures) > 1
    findings: list[Finding] = []
    for name, structure in task.structures.items():
        for finding in check(structure, allocation, components, geometry, calibration):
            findings.append(
                dataclasses.replace(
                    finding, detail=f"in structure {name!r}: {finding.detail}",
                    subjects=tuple(f"{name}: {subject}" for subject in finding.subjects))
                if several else finding
            )
    return (
        findings
        + _structure_faults(task)
        + _meaning_faults(task)
        + _reaction_time_faults(task)
        + _choice_faults(task)
        + _hash_faults(task)
        + _head_faults(task, deployment)
        + _counting_faults(task)
        + ([] if source is None else _computed_positions(Path(source)))
    )


#: The findings a value outside its declared range is refused for when it newly causes them,
#: beside every finding that blocks: what the PI named as breaking the run (2026-10-11, XC-352's
#: D2: "refuse only what would break the run (off screen, windows colliding, colors unmakeable),
#: saying what"). Each is a warning at load, within the declared ranges, since his rulings on
#: A8, A9 and A20 the same day, and so is one that is about nothing new (`Finding.subjects`: the
#: same state and pair of windows, the same array, or the same thing asking for the same color
#: as the task wrote it, only larger -- never merely another appearance of the same type, Task
#: 10's review, I1); off screen (`stimulus-off-screen`) already blocks.
BREAKS_A_RUN = ("overlapping-windows", "crowded-array", "unrealizable-color")

#: The trial cap, as a `longer-than-declared` warning says it: the longest trial, five minutes at
#: the session's rate (`run.LONGEST_TRIAL_S`, `run_trial`'s `max_frames` since engine build C2a;
#: engine spec §6.8), where it was 100,000 frames, about 417 s at 240 Hz.
TRIAL_CAP = f"the longest trial ({LONGEST_TRIAL_S / 60:g} minutes)"


def _among(finding: Finding, findings: list[Finding]) -> bool:
    """Whether `findings` holds one equal to `finding` and about the same things: `Finding`'s
    equality leaves `subjects` out, so two parts of a clip warning that name one light asked for
    by two written colors are equal, and are not the same part (Task 10's review, I1)."""
    return any(f == finding and f.subjects == finding.subjects for f in findings)


def _outside(param: Param, value: object) -> bool:
    """Whether `value` is a finite number outside the range `param` declares (a setting with
    choices has none)."""
    if param.choices or isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    if not math.isfinite(value):
        return False
    return ((param.low is not None and value < param.low)
            or (param.high is not None and value > param.high))


def _waits(task: Task) -> tuple[set[str], float]:
    """The settings a trial waits on -- an `After`'s or a `Hold`'s seconds -- and the longest wait
    the task declares: the highest bound any of them declares, the largest number a choice
    setting among them offers, or its longest literal wait. **A wait setting with no highest
    that is a number can be any length** (Task 10's review, M1), so the longest is unbounded
    (`math.inf`) and no value of any wait is longer than one the task declares."""
    declared = {param.name: param for param in task.params}
    names: set[str] = set()
    longest = 0.0
    for structure in task.structures.values():
        for state in structure.states:
            for edge in state.go:
                if not isinstance(edge.guard, (After, Hold)):
                    continue
                seconds = edge.guard.seconds
                if isinstance(seconds, P):
                    names.add(seconds.name)
                    param = declared.get(seconds.name)
                    if param is None:
                        continue  # refused at load (`_undeclared_parameters`)
                    if param.choices:
                        offered = [float(c) for c in param.choices if _is_number(c)]
                        longest = max([longest, *offered])
                    elif _is_number(param.high):
                        longest = max(longest, float(param.high))
                    else:
                        longest = math.inf
                elif _is_number(seconds):
                    longest = max(longest, float(seconds))
    return names, longest


def widened(task: Task, values) -> Task:
    """`task` with each numeric setting's declared range stretched to take its number in
    `values`, every structure alike: what the load-time checks are run again against for a value
    outside its range (the PI, 2026-10-11, XC-352's D2). A setting with choices, a value that is
    no finite number, a name the task does not declare and a value inside its range leave its
    declaration as it is. A starting value stays: widening only extends a range, so the start
    `Param` held inside it is inside it still."""
    def wide(param: Param) -> Param:
        value = values.get(param.name)
        if not _outside(param, value):
            return param
        low = value if param.low is not None and value < param.low else param.low
        high = value if param.high is not None and value > param.high else param.high
        return dataclasses.replace(param, low=low, high=high)

    return dataclasses.replace(task, structures={
        name: dataclasses.replace(structure, params=[wide(p) for p in structure.params])
        for name, structure in task.structures.items()
    })


def beyond_range(
    task: Task,
    values,
    allocation: Allocation = PROVISIONAL,
    components: Registry | None = None,
    geometry: Geometry | None = None,
    calibration: Calibration | None = None,
    deployment: Deployment | None = None,
) -> list[Finding]:
    """**A value outside its declared range** (the PI, 2026-10-11, XC-352's D2: "re-run the
    load-time checks with the range widened to the new value; accept with a warning that the task
    was not designed for it if nothing breaks; refuse only what would break the run (off screen,
    windows colliding, colors unmakeable), saying what"): for each, a warning, `outside-range`,
    and for a wait longer than any the task declares a second, `longer-than-declared` (`_waits`;
    the PI, 2026-10-12: "Allow, with a warning"), each accepted in every kind. Then each finding
    the task widened to them gives that the task as declared does not, saying which values
    caused it: **refused** when it blocks, or when it is one `BREAKS_A_RUN` names about something
    the declared task's findings are not (`Finding.subjects`); otherwise a warning, among them a
    value that only enlarges an overlap or a clip the task was accepted with at load. **And a
    set size above its highest whose objects would be drawn on one another is refused**,
    whatever the task was accepted with (`_overlapping_objects`; the final review's I1). Nothing
    when every value is inside its range. The declared ranges are what every load-time proof is
    made over (the checks "Reasoning over the whole parameter space" below), which proves a value
    inside them cannot break the task from the console and says nothing of one outside them, so
    the checks run again, widened to it, twice: at a run's start (`preflight.beyond`) and on a
    live edit (`Session.set`)."""
    declared = {param.name: param for param in task.params}
    outside = {name: value for name, value in values.items()
               if name in declared and _outside(declared[name], value)}
    if not outside:
        return []
    # **A wait longer than any the task declares is a warning**, one per wait (the PI, 2026-10-12,
    # on the plan's call 4: "Allow, with a warning"): stop, pause and the out-of-cage limit are
    # heard between trials, never inside one, until they are checked about once a second inside
    # a trial (WEL-11; engine spec §6.8; XC-373), when this sentence changes; the trial cap it
    # names is the longest trial, five minutes since engine build C2a (`TRIAL_CAP`).
    waits, longest = _waits(task)
    findings: list[Finding] = []
    for name, value in outside.items():
        param = declared[name]
        # The bounds it declares, and only those (Task 10's review, M2): a setting with one bound
        # is outside it on that side.
        where = (f"outside the [{param.low}, {param.high}] the task declares"
                 if param.low is not None and param.high is not None
                 else f"above its declared {param.high}" if param.high is not None
                 else f"below its declared {param.low}")
        findings.append(Finding("outside-range", (
            f"{name!r} is {value:g} {param.unit}, {where}, so the task was not designed for it: "
            f"its load-time checks were proved only over its declared range, and were run again "
            f"with the range widened to {value:g}"), blocking=False, accepted_in=SESSION_KINDS))
        if name in waits and value > longest:
            findings.append(Finding("longer-than-declared", (
                f"{name!r} at {value:g} s is a wait longer than any the task declares (its "
                f"longest, {longest:g} s), and a stop, a pause and the out-of-cage limit are heard "
                f"only between trials: while a trial waits on {name!r} they go unheard until that "
                f"trial ends, and {TRIAL_CAP} ends any trial still running then, with no outcome "
                f"(a hang)"), blocking=False, accepted_in=SESSION_KINDS))
    said = ", ".join(f"{name!r} at {value:g}" for name, value in outside.items())
    before = check_task(task, allocation, components, geometry, calibration, deployment)
    # What the declared task's findings are about (the warnings-over-refusals review's I5): a
    # finding of `BREAKS_A_RUN` about the same thing, only larger, was accepted with the task.
    known = {(finding.code, subject) for finding in before for subject in finding.subjects}
    wide = widened(task, outside)
    for finding in check_task(wide, allocation, components, geometry, calibration, deployment):
        # One the declared task gives, about the same things: equality leaves `subjects` out, and
        # a light a value newly asks for can be one the task's clip warning already says, word
        # for word (Task 10's review, I1).
        if _among(finding, before) or not (finding.blocking or finding.is_warning):
            continue
        detail = f"with {said}, outside its declared range: {finding.detail}"
        new = [subject for subject in finding.subjects if (finding.code, subject) not in known]
        if finding.blocking or (finding.code in BREAKS_A_RUN and (new or not finding.subjects)):
            if len(finding.subjects) > 1:
                detail += f" (new with this value: {'; '.join(new)})"
            findings.append(Finding(finding.code, detail))
        else:
            findings.append(dataclasses.replace(finding, detail=detail))
    # **A set size past its highest whose objects would be drawn on one another is refused**,
    # whatever the declared task was accepted with (the final review's I1): no "same array, only
    # larger" waives it, since what breaks is the size itself (`_overlapping_objects`).
    raised = {name: value for name, value in outside.items()
              if _finite(declared[name].high) and value > declared[name].high}
    for name, structure in wide.structures.items():
        where = f"in structure {name!r}: " if len(wide.structures) > 1 else ""
        findings += [
            Finding(finding.code,
                    f"with {said}, outside its declared range: {where}{finding.detail}")
            for finding in _overlapping_objects(structure, raised)
        ]
    return findings


def _structure_faults(task: Task) -> list[Finding]:
    """One set of settings and one setup across a task's structures (engine spec §3.5, §13.3): a name
    two structures declare differently would be validated by `Session.set` against whichever came
    first, and a task's runs are checked against one field."""
    findings: list[Finding] = []
    first: dict[str, tuple[str, Param]] = {}
    for name, structure in task.structures.items():
        for param in structure.params:
            where, declared = first.setdefault(param.name, (name, param))
            if declared == param:
                continue
            said = (
                f"structure {name!r} declares setting {param.name!r} twice, differently"
                if where == name
                else f"setting {param.name!r} is declared one way by structure {where!r} and "
                f"another by {name!r}"
            )
            findings.append(Finding("parameter-mismatch", (
                f"{said}; a task's settings are one set, which a live edit is checked against "
                f"(engine spec §3.5)")))
    views = sorted({str(structure.view) for structure in task.structures.values()})
    if len(views) > 1:
        findings.append(Finding("view-mismatch", (
            f"the task's structures are written for different setups ({', '.join(views)}); a "
            f"task runs in one")))
    return findings


def _meaning_faults(task: Task) -> list[Finding]:
    """Every setting a person can change declares what it means (XC-288 §4.1; TRN-03): the shared
    list's (`declarations.COMMON`), or the task's own -- which, for a setting on the shared list, is
    an override and says why (the PI, 2026-10-11). **Required**: "a missing declaration cannot be
    told from a forgotten one". The bounded settings a task rewards through take theirs from
    `declarations.BOUNDED`. A meaning for no setting, an override of nothing, a direction read
    relative to anything on a list of choices, and one read relative to no other setting the task
    declares are refused too."""
    from wl_xcon.declarations import BOUNDED, COMMON, rewarded_through

    findings: list[Finding] = []
    declared = {param.name: param for param in task.params}
    for name, param in declared.items():
        own = task.meanings.get(name)
        meaning = own if own is not None else COMMON.get(name)
        if meaning is None:
            findings.append(Finding("undeclared-meaning", (
                f"setting {name!r} declares no meaning: clear-cut with a direction, expected with "
                f"a direction and a note, or not a difficulty setting (XC-288 §4.1); a missing "
                f"declaration cannot be told from a forgotten one")))
            continue
        if own is not None and name in COMMON and not own.overrides.strip():
            findings.append(Finding("override-without-why", (
                f"the task gives {name!r} a meaning of its own, and {name!r} is on the shared "
                f"list; a task overrides a shared meaning only with a note saying why "
                f"(Meaning.overrides)")))
        if own is not None and name not in COMMON and own.overrides:
            findings.append(Finding("bad-meaning", (
                f"{name!r}'s meaning says it overrides the shared list, which has no "
                f"{name!r}")))
        relative = meaning.relative_to
        if relative is not None and param.choices:
            findings.append(Finding("bad-meaning", (
                f"{name!r}'s direction reads relative to {relative!r}, and its values are "
                f"choices, which are no distance from anything")))
        elif isinstance(relative, str) and (relative == name or relative not in declared):
            findings.append(Finding("bad-meaning", (
                f"{name!r}'s direction reads relative to setting {relative!r}, which is not "
                f"another setting the task declares")))
    for name in task.meanings:
        if name not in declared:
            # A review note, never a refusal (XC-352's A7; the PI, 2026-10-11): it can never
            # take effect.
            findings.append(Finding("meaning-for-nothing", (
                f"the task declares a meaning for {name!r}, which none of its structures "
                f"declares as a setting: it can never take effect, which is probably a mistake"),
                blocking=False))
    for ref in sorted(rewarded_through(task)):
        if ref not in BOUNDED:
            findings.append(Finding("undeclared-meaning", (
                f"bounded setting {ref!r}, which the task rewards through, has no meaning in "
                f"declarations.BOUNDED (XC-288 §4.1)")))
    return findings


def _reaction_time_faults(task: Task) -> list[Finding]:
    """How the task's reaction time is defined (XC-288 §4.3): declared, from a state some structure
    has, ending where that state's transitions go (the engine C1 plan's call 8)."""
    timed = task.reaction_time
    if timed is None:
        return [Finding("no-reaction-time", (
            "the task does not say how its reaction time is defined, from which event to which "
            "(XC-288 §4.3), so its trials' reaction times would mean nothing; declare "
            "reaction_time=ReactionTime(state, to, note)"))]
    states = [
        state
        for structure in task.structures.values()
        for state in structure.states
        if state.name == timed.state
    ]
    if not states:
        return [Finding("bad-reaction-time", (
            f"the reaction time is timed from state {timed.state!r}, which no structure has"))]
    leaves = {edge.to for state in states for edge in state.go}
    return [
        Finding("bad-reaction-time", (
            f"the reaction time ends when {timed.state!r} is left for {_destination(end)}, and "
            f"no structure's {timed.state!r} goes there"))
        for end in timed.to
        if end not in leaves
    ]


def _destination(end: object) -> str:
    """Where a transition goes, as a finding names it: an outcome by its name, a state quoted."""
    return end.name if isinstance(end, Outcome) else repr(end)


def _choice_faults(task: Task) -> list[Finding]:
    """What the task offers to choose between (XC-288 §4.3): declared -- a `Choice`, or `NO_CHOICE`
    for a task that offers none, since an unset choice cannot be told from a forgotten one (the
    engine C1 plan's call 10) -- and each object a window some structure's transition fires on by
    the act the choice names (`CHOSEN_BY`)."""
    choice = task.choice
    if choice is None:
        return [Finding("undeclared-choice", (
            "the task does not say what it offers to choose between (XC-288 §4.3), and an unset "
            "choice cannot be told from a forgotten one; declare choice=Choice(objects, by), or "
            "choice=NO_CHOICE for a task that offers none"))]
    if isinstance(choice, NoChoice):
        return []
    acts = CHOSEN_BY[choice.by]
    chosen = {
        _chosen(edge.guard)
        for structure in task.structures.values()
        for state in structure.states
        for edge in state.go
        if isinstance(edge.guard, acts)
    }
    return [
        Finding("bad-choice", (
            f"{offered!r} is declared a choice made by {choice.by}, and no structure's transition "
            f"fires on a {choice.by} to it"))
        for offered in choice.objects
        if offered not in chosen
    ]


def _chosen(guard: object) -> "str | None":
    """The window -- or, for a lever, the device -- a choosing guard names."""
    return getattr(guard, "window", None) or getattr(guard, "device", None)


#: The constructors that take a position, with where it sits among their positional arguments,
#: and the keywords that name one.
_PLACED = {"Stimulus": (1, "a stimulus's"), "Window": (1, "a window's"),
           "Update": (1, "an update's")}
_POSITION_KEYWORDS = ("at", "at_left", "at_right")
_TRIGONOMETRY = ("cos", "sin")


def _computed_positions(source: Path) -> list[Finding]:
    """**A position a task file computes from `cos` and `sin` itself, a warning** (the PI,
    2026-10-19: "the load check warns where a task computes a position as e·cosθ itself"): per
    axis, `(e·cos θ, e·sin θ)` is less than `e` out off the axes, 7.975° for 8° at 45°, and
    `Polar(e, θ)` is converted exactly. By load the task object holds only the numbers, so the
    file is read with the parser, never a pattern over its text (CLAUDE.md).

    **What it finds**: a call of `math`'s or numpy's `cos` or `sin`, by any name the file imports
    it as, inside a position -- `Stimulus`'s, `Window`'s and `Update`'s, by keyword or in its
    place, and the `at`, `at_left` and `at_right` of each -- written there, through a name the
    file assigns at its top level, or among the choices of a setting a position names by `P`.
    **What it passes**: anything inside a `Polar(...)`, whose fields are an eccentricity and a
    direction however they are computed. **What it misses**: a position a function returns, one
    assigned inside a function or in another module, a name assigned twice (it reads the last),
    anything reached through `getattr`, `eval` or a loop that builds the trial, and trigonometry
    by another route (`cmath`, `scipy`, `numpy.exp(1j·θ)`). A warning in every session kind,
    never a refusal."""
    try:
        tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
    except (OSError, SyntaxError, UnicodeDecodeError):
        return []
    modules: set[str] = set()
    functions: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules |= {a.asname or a.name for a in node.names if a.name in ("math", "numpy")}
        elif isinstance(node, ast.ImportFrom) and node.module in ("math", "numpy"):
            functions |= {a.asname or a.name for a in node.names if a.name in _TRIGONOMETRY}

    def called(node: ast.Call) -> str | None:
        func = node.func
        return func.id if isinstance(func, ast.Name) else (
            func.attr if isinstance(func, ast.Attribute) else None)

    def outside_polar(node: ast.AST):
        """Every node of `node` but those inside a `Polar(...)`."""
        if isinstance(node, ast.Call) and called(node) == "Polar":
            return
        yield node
        for child in ast.iter_child_nodes(node):
            yield from outside_polar(child)

    def trigonometry(expression: ast.AST) -> bool:
        return any(
            isinstance(call, ast.Call) and (
                (isinstance(call.func, ast.Name) and call.func.id in functions)
                or (isinstance(call.func, ast.Attribute) and call.func.attr in _TRIGONOMETRY
                    and isinstance(call.func.value, ast.Name) and call.func.value.id in modules))
            for call in outside_polar(expression))

    assigned = {target.id: (statement.value, statement.lineno) for statement in tree.body
                if isinstance(statement, ast.Assign)
                for target in statement.targets if isinstance(target, ast.Name)}
    chosen: dict[str, tuple[ast.AST, int]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and called(node) == "Param":
            name = next((a.value for a in node.args[:1] if isinstance(a, ast.Constant)), None)
            name = next((k.value.value for k in node.keywords if k.arg == "name"
                         and isinstance(k.value, ast.Constant)), name)
            choices = next((k.value for k in node.keywords if k.arg == "choices"), None)
            if isinstance(name, str) and choices is not None:
                chosen[name] = (choices, node.lineno)

    found: dict[tuple[int, str], Finding] = {}
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and called(node) in _PLACED):
            continue
        place, whose = _PLACED[called(node)]
        given = [k.value for k in node.keywords if k.arg in _POSITION_KEYWORDS]
        if place is not None and len(node.args) > place:
            given.append(node.args[place])
        for position in given:
            how = None
            if trigonometry(position):
                how = ""
            for name in (n.id for n in outside_polar(position) if isinstance(n, ast.Name)):
                if how is None and name in assigned and trigonometry(assigned[name][0]):
                    how = f" through `{name}` (line {assigned[name][1]})"
            for call in outside_polar(position):
                if (how is None and isinstance(call, ast.Call) and called(call) == "P"
                        and call.args and isinstance(call.args[0], ast.Constant)
                        and call.args[0].value in chosen
                        and trigonometry(chosen[call.args[0].value][0])):
                    how = (f" through the choices of setting {call.args[0].value!r} "
                           f"(line {chosen[call.args[0].value][1]})")
            if how is not None:
                found[(position.lineno, how)] = Finding("computed-position", (
                    f"line {position.lineno}: {whose} position{how} is computed from cos or sin "
                    f"per axis, as (e·cos θ, e·sin θ), which is less than e out off the axes "
                    f"(7.975° for 8° at 45°); write it as Polar(eccentricity, direction), which "
                    f"the rig converts exactly (the PI, 2026-10-19)"),
                    blocking=False, accepted_in=SESSION_KINDS)
    return [found[key] for key in sorted(found)]


def _hash_faults(task: Task) -> list[Finding]:
    """A run records which version of its task it ran by the task's content hash (XC-288 §4.4), so
    a task whose content cannot be hashed is refused before any run."""
    from wl_xcon.declarations import content_hash

    try:
        content_hash(task)
    except (TypeError, ValueError) as unread:
        return [Finding("unhashable-task", (
            f"the task's content could not be hashed ({unread}), so a run could not record which "
            f"version of it ran (XC-288 §4.4)"))]
    return []


def _counting_faults(task: Task) -> list[Finding]:
    """Each structure's counting table (engine spec §16.1-16.2; engine build C2a). **Refused when a
    structure declares none**, an authoring rule (the PI, 2026-10-11: a break after the stimulus
    has "no default; each task declares", and "the load-time check refuses a task that does not
    say"): a missing table cannot be told from a forgotten one, and the scheduler would have no
    answer for the first such break. **And when its table names no state its stimulus appears
    in, or one the structure does not have** (the PI, 2026-10-13, "Task names it, required"):
    whether a break came before anything was presented is read from that state."""
    findings: list[Finding] = []
    for name, structure in task.structures.items():
        table = structure.counting
        states = sorted(state.name for state in structure.states)
        if table is None:
            findings.append(Finding("undeclared-counting", (
                f"structure {name!r} has no counting table, so nothing says whether a break after "
                f"its stimulus is spent (used up) or owed (shown again); give it "
                f"counting=Counting(after_stimulus=SPENT or OWED) (engine spec §16.2)")))
        elif table.appears is None:
            findings.append(Finding("undeclared-counting", (
                f"structure {name!r}'s counting table does not name the state its stimulus "
                f"appears in, so nothing says whether a break came before anything was presented; "
                f"give it appears=, one of {', '.join(map(repr, states))} -- a cued task's cue")))
        elif table.appears not in states:
            findings.append(Finding("bad-counting", (
                f"structure {name!r}'s counting table says its stimulus appears in "
                f"{table.appears!r}, which is not one of its states "
                f"({', '.join(map(repr, states))})")))
    return findings


def _head_faults(task: Task, deployment: "Deployment | None") -> list[Finding]:
    """A task that needs a fixed head, in any session not declared head-fixed (`RIG_FIXED`; engine
    spec §20.1; STE-25), is **a warning, not a refusal** (the PI, 2026-10-11: "in general, I think
    you have been too gung ho on refusals ... the experimenter needs free control most of the
    time"): the run goes ahead, the warning saying why that may be a bad idea, accepted in every
    session kind. Given in every deployment but `RIG_FIXED` (the engine C1 plan's call 16), a
    cage-side session as much as a chaired one; it reads the deployment, not the head's state
    (XC-347). A load-time finding, so it reaches the pre-flight's warnings item and `wlx run`'s
    `--accept-warnings` as every task warning does, and `preflight.gate` and `Service._start` stay
    as they are."""
    if task.needs_fixed_head and deployment is not None and deployment is not Deployment.RIG_FIXED:
        return [Finding("head-not-fixed", (
            f"the task needs a fixed head, and this session's deployment, {deployment.value}, does "
            f"not declare one fixed: the task tracks gaze and the rig has no head tracking, so "
            f"with the head free its gaze decisions (holding fixation, where a saccade lands) may "
            f"be wrong (engine spec §20.1)"), blocking=False, accepted_in=SESSION_KINDS)]
    return []


def _unreachable_states(trial: Trial) -> list[Finding]:
    """S1 §9 check 2: every state is reachable from the start state. One that is not can never
    take effect: **a review note, never a refusal** (XC-352's A7; the PI, 2026-10-11)."""
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
        Finding("unreachable-state", (
            f"no transition reaches {name!r}: it can never take effect, which is probably a "
            f"mistake"), blocking=False)
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
    entirely reasonable in isolation. **A review note, never a refusal** (XC-352's A7;
    the PI, 2026-10-11).
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
                        f"the later transition can never fire, which is probably a mistake",
                        blocking=False,
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


def _span(
    value: object, params: dict[str, Param], least: float = -math.inf
) -> tuple[float, float]:
    """The least and the greatest a value a range check reads can be over every setting the
    console allows: a window's coordinate or radius, an array's size, ring or target index, a
    stereogram's correlation, a time bound's seconds. **The one reading of a declared range
    every range check shares** (`_widest`, which read a setting with one bound as 0 to 0, is
    gone since Task 10's review, fix round 2).

    A literal is itself; a parameter is **its declared range**, because every value in it is
    one an experimenter can dial in live, or the least and greatest of its choices. Checking
    the range rather than a value proves a task cannot be broken from the console, instead of
    proving it happens not to be today.

    **A side it does not bound reaches as far as that side can go** (Task 10's review, I2):
    `least` below -- 0 for a radius, a count or seconds, which mean nothing lower, and without
    end for a position, an index or a correlation -- and without end above, so that no check
    reads a setting with one bound, or none, as the 0 it was once read as, and passes what a
    value it accepts would fail. A bound or a choice that is no finite number bounds nothing,
    failing closed, and so does an undeclared setting (`_undeclared_parameters` refuses it). A
    value widened past its one bound (`widened`) moves that bound and leaves the other side
    unbounded.
    """
    if not isinstance(value, P):
        return (float(value), float(value))
    param = params.get(value.name)
    if param is None:
        return (least, math.inf)
    if param.choices:
        offered = [float(c) for c in param.choices if _finite(c)]
        if len(offered) < len(param.choices):
            return (least, math.inf)
        return (min(offered), max(offered))
    return (float(param.low) if _finite(param.low) else least,
            float(param.high) if _finite(param.high) else math.inf)


def _finite(value: object) -> bool:
    """Whether `value` is a finite number, and not a `bool`."""
    return _is_number(value) and math.isfinite(value)


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
    parameter** (`at=P("pos")`) is the points it offers as choices, a `Polar` of numbers
    converted (`polar_deg`); indexing it as a pair was a `TypeError` that would have crashed
    `taskd`'s load (XC-036). A range, or choices that are not points, names no place to test.
    """
    if isinstance(at, P):
        offered = [polar_deg(float(point.eccentricity), float(point.direction))
                   if isinstance(point, Polar) and _is_number(point.eccentricity)
                   and _is_number(point.direction) else point
                   for point in _domain(at, params)]
        if not all(
            isinstance(point, (tuple, list))
            and len(point) == 2
            and all(_is_number(c) for c in point)
            for point in offered
        ):
            raise _Unbounded(at.name)
        return [(float(x), float(y)) for x, y in offered]
    if isinstance(at, Polar):
        # Every direction a range allows, not its ends alone: 20° out over 0° to 120° is 20° up
        # at 90°. The corners of each piece's per-axis box (`polar_box_deg`), which a field, a
        # per-axis rectangle, holds exactly when it holds the piece.
        return [(x, y)
                for es in _polar_sides(at.eccentricity, params, bounded=True)
                for ds in _polar_sides(at.direction, params, bounded=False)
                for xs, ys in (polar_box_deg(es, ds),) for x in xs for y in ys]
    return [(x, y) for x in _numbers(at[0], params) for y in _numbers(at[1], params)]


def _polar_sides(
    value: object, params: dict[str, Param], bounded: bool
) -> list[tuple[float, float]]:
    """The values a polar position's eccentricity or direction can take, as intervals: a literal
    or each choice a point, a range one interval. One check 8 cannot bound is `_Unbounded`, as
    every other is, but for a direction (`bounded` false), which without bounds is every one."""
    if not isinstance(value, P):
        return [(float(value), float(value))]
    param = params.get(value.name)
    if param is not None and param.choices and all(_finite(c) for c in param.choices):
        return [(float(c), float(c)) for c in param.choices]
    if (param is not None and not param.choices and _finite(param.low)
            and _finite(param.high)):
        return [(float(param.low), float(param.high))]
    if bounded:
        raise _Unbounded(value.name)
    return [(-180.0, 180.0)]


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
                # An array's objects sit on a true circle about the stimulus position
                # (`Array.positions`), so the thing that can leave the field is an *object*,
                # never the center: the corners of the circle's box in per-axis degrees, which
                # off the axes reaches further than its radius (`geometry.circle_extent_deg`).
                # The extreme is the widest legal radius: with n a parameter too, every
                # smaller set is a subset of those positions.
                widest = max(_numbers(looks.radius, params))
                centres = [
                    (x + sx * across, y + sy * up)
                    for x, y in centres
                    for across, up in (circle_extent_deg(x, y, widest),)
                    for sx in (1.0, -1.0, 0.0)
                    for sy in (1.0, -1.0, 0.0)
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
    if isinstance(at, Polar):
        return "eccentricity " + ", direction ".join(
            v.name if isinstance(v, P) else f"{v:g}" for v in (at.eccentricity, at.direction))
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
        # An `ObjectWindows` family always couples to its array, by construction.
        if not isinstance(window, ObjectWindows) and window.on is None
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


def _windows_left_behind(trial: Trial) -> list[Finding]:
    """**An array's object window asked about after an `Update` that can draw the array as no
    array, warned** (the XC-402 review, I2; the controller's ruling of 2026-10-27, pending the
    PI). No objects are drawn then, so their windows stay where the objects were last drawn
    (`task.placements`), and gaze there is scored as on them: right for a memory-guided design that
    blanks the array on purpose, wrong if it was not meant. A `Hide` of the array is refused
    instead (`nothing-to-look-at`). A **may** analysis, unlike `_visible_on_entry`'s must: one
    path into a state on which the array is drawn as no array is enough to say so. An appearance a
    setting holds counts as no array when any of its choices is not one, or it has none. A warning
    in every kind (the PI, 2026-10-11: warnings over refusals)."""
    families = {w.of for w in trial.windows if isinstance(w, ObjectWindows)}
    if not families:
        return []
    params = {p.name: p for p in trial.params}

    def no_array(looks: object, inside: frozenset[str] = frozenset()) -> bool:
        if isinstance(looks, P):
            param = params.get(looks.name)
            if param is None or not param.choices:
                return True
            return any(no_array(choice, inside | {looks.name}) for choice in param.choices
                       if not (isinstance(choice, P) and choice.name in inside))
        return not isinstance(looks, Array)

    def after(blanked: frozenset[str], actions: list) -> frozenset[str]:
        for action in actions:
            if isinstance(action, Show) and action.stimulus.name in families:
                blanked = blanked - {action.stimulus.name}
            elif (isinstance(action, Update) and action.stimulus in families
                  and "looks" in action.changes()):
                blanked = (blanked | {action.stimulus} if no_array(action.looks)
                           else blanked - {action.stimulus})
        return blanked

    entry: dict[str, frozenset[str]] = {state.name: frozenset() for state in trial.states}
    for _ in range(len(entry) + 1):
        arriving: dict[str, frozenset[str]] = {name: frozenset() for name in entry}
        for state in trial.states:
            leaving = after(entry[state.name], state.enter)
            for edge in state.go:
                if not isinstance(edge.to, Outcome) and edge.to in arriving:
                    arriving[edge.to] = arriving[edge.to] | after(leaving, edge.do)
        if arriving == entry:
            break
        entry = arriving

    findings: list[Finding] = []
    for state in trial.states:
        blanked = after(entry[state.name], state.enter)
        for edge in state.go:
            window = getattr(edge.guard, "window", None)
            if window is None or not isinstance(
                edge.guard, (Entered, Exited, Hold, SaccadeTo, Touched)
            ):
                continue
            for of in sorted(blanked):
                if window not in (f"{of}.target", f"{of}.distractor") and \
                        _object_index(window, of) is None:
                    continue
                finding = Finding(
                    "windows-left-behind",
                    f"state {state.name!r} scores {window!r}, an object window of array {of!r}, "
                    f"after an update that can draw {of!r} as no array; its object windows stay "
                    f"where its objects were last drawn, and gaze there is scored as on them: "
                    f"right for a memory-guided design that blanks the array on purpose, wrong "
                    f"if it was not meant (a Hide of the array is refused instead)",
                    blocking=False,
                    accepted_in=SESSION_KINDS,
                )
                if finding not in findings:
                    findings.append(finding)
    return findings


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
    `None` when nothing shows that name, which no rule exempts. An `Array`'s objects combine
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
    each block's (a flat fill, a grating's mean, an outline), and the backgrounds. A color,
    or a `Look`'s fill or outline, that is a parameter is each of its choices; a color
    offering none to read is refused by `_light_faults`, and a value that is not a color by
    `_block_faults`, so neither is one here. An appearance a parameter offers is named as
    that parameter's choice (every one it is, when the same object is offered twice), so the
    choices' findings say which is which."""
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
            for written in (looks.fill, looks.outline):
                # A fill or an outline that is a parameter is each fill or outline its choices
                # offer, through any parameter among them (`_parts`; the A2 final review's I3).
                parts, by = [written], ""
                if isinstance(written, P):
                    parts = [part for part in _parts(written, params)
                             if isinstance(part, (look.Fill, look.Outline))]
                    by = f" (a choice of parameter {written.name!r})"
                for part in parts:
                    for attr in ("color", "mean"):
                        yield from each(f"{what}'s {type(part).__name__}{by}{chosen}",
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
    # Each color that claims isoluminance on the default, for the task's one warning, and where
    # that warning goes among the findings (the warnings-over-refusals review's M8).
    isoluminant: list[str] = []
    at = 0
    for what, color in _colors(trial, params):
        # With no calibration at all -- a direct `check()` call; no session runs without one
        # since XC-352's E1 (2026-10-11), the default standing in for a record that will not
        # load -- an absolute luminance is not checked here; on the default it is the session's
        # one warning (`warnlist.of_calibration`, accepted at the open). Any other color with no
        # calibration is unmeasured once, as written; with one,
        # it is checked as each light it can be.
        if panel is None and isinstance(color, Gray):
            continue
        if what.startswith("the trial's ") and isinstance(color, CONE_COLORS):
            continue  # a background is an absolute light, and `_block_faults` refuses one that is not
        if (panel is not None and panel.standard
                and _claims_isoluminance(color, params, panel, backgrounds)):
            # Spec §7.3 asked a measured calibration for isoluminance; since COL-03's revision
            # (the PI, 2026-10-11, XC-352's A19: "a warning everywhere") it is a warning in every
            # kind, saying the colors are only nominally isoluminant: **one per task, naming each
            # color that claims it** (below; the warnings-over-refusals review's M8). Asked of the
            # color as written, before its values are read, so a `lum` whose range crosses 0
            # claims it too (XC-269). Its lights are still held to the panel's reach, below.
            if not isoluminant:
                at = len(findings)
            if what not in isoluminant:
                isoluminant.append(what)
        try:
            lights = [color] if panel is None else _lights(color, params)
        except _Unbounded:
            continue  # refused as a bad block: it cannot be bounded
        # What a clip of these lights is about (`Finding.subjects`): what asks for them and the
        # color as the task wrote it, before `_lights` reads each value it can take. Two things
        # asking for one written color clip alike; two written colors of one appearance type
        # are two things a value can newly clip (Task 10's review, I1).
        about = f"{what} asking for {color}"
        for light in lights:
            for finding in _one_color(what, light, panel, backgrounds, about=about):
                if not _among(finding, findings):  # one value's corners can say the same
                    findings.append(finding)
    if isoluminant:
        findings.insert(at, Finding("isoluminance-on-default", (
            f"the default calibration is the sRGB standard, measured by nobody, so this task's "
            f"colors that claim isoluminance are only nominally isoluminant on an unmeasured "
            f"panel: the luminance they hold constant is {HELD_STANDARD}, and what this panel "
            f"shows of it is unknown (engine spec §7.3); the colors that claim it: "
            f"{'; '.join(isoluminant)}"), blocking=False, accepted_in=SESSION_KINDS))
    if panel is not None:
        findings += [f for f in _modulation_faults(trial, params, panel, backgrounds)
                     if f not in findings]
        # One clip warning per task, each light once (`_clips`; the review's M8).
        findings = _clips(findings)
    if panel is not None and panel.standard:
        findings += _default_faults(trial, params)
    if panel is not None and not panel.standard and panel.spectra is None:
        findings += _spectra_faults(trial, params, panel)
    return findings


def _spectra_faults(trial: Trial, params: dict[str, Param], panel: Calibration) -> list[Finding]:
    """Cone colors on a measured calibration without spectra, which convert as the default's do
    (COL-18's conversion): **a warning in every kind** (the PI, 2026-10-11, XC-352's E3: "convert
    as the default does, with COL-18's sentence"; refused until then, so a panel measured without
    spectra ran fewer tasks than the unmeasured default). One per task, naming its cone colors."""
    named = sorted({what for what, color in _colors(trial, params)
                    if isinstance(color, CONE_COLORS)})
    if not named:
        return []
    return [Finding("cone-colors-without-spectra", (
        f"calibration {panel.id or panel.measured_on} was measured without spectra, so this task's "
        f"cone colors (DKL, cone contrast) convert as the default's do, through the inverse of the "
        f"CIE's LMS-to-XYZ_F,10 matrix applied to its measured CIE 1931 XYZ, a use outside the "
        f"CIE's definition, so how far each is from the cone contrast it names is unknown, and the "
        f"luminance they hold constant is its measured CIE 1931 Y (COL-18); the colors it names: "
        f"{'; '.join(named)}"), blocking=False, accepted_in=SESSION_KINDS)]


def _modulation_faults(trial: Trial, params: dict[str, Param], panel: Calibration,
                       backgrounds: list) -> list[Finding]:
    """**The lights a contrast makes, held to the panel's reach** (engine spec §7.4, "for every
    space"; the A2 research note §3, step 5: "check both extremes of a grating"): a flat
    `Weber` light is its background times one plus its contrast, a sine grating's brightest and
    darkest bars its mean times one plus and one minus its `Michelson` contrast -- the mean it
    declares, absolute or a cone color on each background, or else each lit background. At each
    value a parameter can take, the mean's own included (the plan's review, E-C1: a parameter in
    a cone mean reached `cone_xyz` unbound). **Against the background only** (the plan's call 18):
    drawn over another stimulus, a pattern's mean is that stimulus's light, and a sum of added
    ones is not known here; the exact drawer clips a pixel the panel cannot make
    (`exact.output_levels`; XC-306). A window, a scotoma and a multiplier
    draw no light of their own and are left out. **Each is one part of the task's one warning,
    naming the light the panel shows** (`_unrealizable`, `_clips`; XC-352's A20)."""
    from wl_xcon.photometry import Michelson, Weber, cone_xyz

    combined = _combined(trial, params)
    findings: list[Finding] = []

    def held(what: str, about: str, base: xyY, factor: float, said: str) -> None:
        light = xyY(base.x, base.y, base.Y * factor)
        why = unrealizable(light, panel)
        if why is not None:
            finding = _unrealizable(f"{what}'s {said} reaches {light}", why, light, panel,
                                    what=what, about=about)
            if not _among(finding, findings):
                findings.append(finding)

    for looks in _appearances(trial):
        if _multiplied([combine for shown, combine in combined if shown == looks]):
            continue
        light = _light(looks)
        if light is None:
            continue
        kind, _, contrast, mean = light
        what = type(looks).__name__
        try:
            contrasts = [c for c in _options(contrast, params) if isinstance(c, (Weber, Michelson))]
            means = [None] if mean is None else _options(mean, params)
            values = {id(c): _reach(c.value, params) for c in contrasts}
        except _Unbounded:
            continue  # refused where it is read: it cannot be bounded
        for c in contrasts:
            for value in values[id(c)]:
                # What each clip is about (`Finding.subjects`): what asks for the light, and its
                # contrast and mean as the task wrote them (Task 10's review, I1).
                if kind == "flat" and isinstance(c, Weber):
                    for background in backgrounds:
                        held(what, f"{what} asking for {c}", background, 1.0 + value,
                             f"Weber contrast of {value:g} on a background of {background}")
                if kind != "grating" or not isinstance(c, Michelson):
                    continue
                for declared in means:
                    about = (f"{what} asking for {c} about "
                             f"{'its background' if declared is None else declared}")
                    if declared is None:
                        bases = [(b, f"mean, its background {b}") for b in backgrounds]
                        values_of_mean = []
                    else:
                        try:
                            values_of_mean = _lights(declared, params)  # each value it can take
                        except _Unbounded:
                            continue  # refused where it is read: it cannot be bounded
                        bases = [(m, f"mean {m}") for m in values_of_mean
                                 if isinstance(m, xyY) and m.Y > 0.0]
                    for m in values_of_mean:
                        if not isinstance(m, CONE_COLORS):
                            continue
                        for b in backgrounds:
                            try:
                                X, Y, Z = cone_xyz(m, panel, b)
                            except ValueError:
                                continue  # the mean itself is refused where it is checked
                            if Y > 0.0:
                                bases.append((xyY(X / (X + Y + Z), Y / (X + Y + Z), Y),
                                              f"mean {m} on {b}"))
                    for base, said in bases:
                        for sign, bar in ((1.0, "brightest"), (-1.0, "darkest")):
                            held(what, about, base, 1.0 + sign * value,
                                 f"{bar} bar at Michelson {value:g} about its {said}")
    return findings


def _multiplied(how: list) -> bool:
    """Whether every stimulus that can show an appearance draws no light of its own: a
    multiplier draws only its modulation, a window or a scotoma (`screen.LIGHTLESS`) none
    (spec §4.4). Shared by the rules that would hold such a light to something."""
    from wl_xcon.screen import LIGHTLESS

    return bool(how) and all(combine == "multiply" or combine in LIGHTLESS for combine in how)


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


#: How near zero a color's luminance contrast may be and still claim isoluminance: half a
#: percent (the engine A2 plan's Q2, A; call 15). A hand-written cone contrast near V_F,10's
#: ratio is a claim, and so is a DKL `lum` written as 0.001.
ISOLUMINANT_WITHIN = 0.005


def _claims_isoluminance(color, params: dict[str, Param], panel: Calibration,
                         backgrounds: list) -> bool:
    """Whether a color claims isoluminance (the PI, N§4 batch 1: "DKL `lum=0` with a chromatic
    component"; the engine A2 plan's Q2, A): its luminance contrast under V_F,10 can be within
    `ISOLUMINANT_WITHIN` of 0 **and** it can be chromatic. Written as literals, both halves say
    it the same way, so one light gets one verdict however it is spelled; with parameters, each
    half asks it its own way.

    A `DKL` color's contrast is `lum`, and it is chromatic when `l_m` or `s_lm` is other than 0
    (`lum` scales every cone alike). **The DKL half asks each separately** (`_can_be`): whether
    `lum` can be in the band, and whether `l_m` or `s_lm` can be other than 0, each at any value
    its parameter can take, not at one value of them all. So `DKL(lum=P("c"), l_m=P("c"))`, c 0
    or 0.1, claims, though at no value is it both: a refusal of a color that is not
    isoluminant, the safe direction.

    A `ConeContrast`'s contrast is the V_F,10 weighted change of L and M on each lit background
    (`_background_lights`), and it is chromatic when L, M and S are not all equal. **The
    ConeContrast half asks at one value of its parameters**, per combination of their values:
    choices exactly, one by one; a range by the ends of each (the contrast is linear in each
    component, and a parameter in two components has one value), which claims when they span
    the band, unless the color is achromatic at every value of the combination (L, M and S the
    same literal or the same parameter).

    **Both fail closed**: a value that cannot be read can be anything, and a chromatic range
    crossing 0 claims, though at 0 it is the background (the plan's call 15). A component that
    is no number names no light (`_lights`), and `_block_faults` refuses it."""
    tol = ISOLUMINANT_WITHIN
    if isinstance(color, DKL):
        return (_can_be(color.lum, params, lambda v: abs(v) <= tol,
                        lambda lo, hi: lo <= tol and hi >= -tol)
                and any(_can_be(v, params, lambda v: v != 0.0,
                                lambda lo, hi: lo != 0.0 or hi != 0.0)
                        for v in (color.l_m, color.s_lm)))
    if not isinstance(color, ConeContrast):
        return False
    parts = (color.L, color.M, color.S)
    names = sorted({v.name for v in parts if isinstance(v, P)})
    if not all(isinstance(v, P) or _is_number(v) for v in parts):
        return False
    try:
        # Per parameter: its choices (each exact), or its range (the ends, together).
        domains = {name: _domain(P(name), params) for name in names}
    except _Unbounded:
        return True
    if not all(_is_number(v) for values in domains.values() for v in values):
        return True
    ranged = {name for name in names if not (params[name].choices)}
    # The same parameter, or the same literal, in all three: a name never equals a number.
    achromatic = len({v.name if isinstance(v, P) else float(v) for v in parts}) == 1
    excitations = []
    for background in backgrounds:
        try:
            excitations.append(background_cones(panel, background))
        except ValueError:
            continue
    fixed = [name for name in names if name not in ranged]
    for chosen in itertools.product(*(domains[name] for name in fixed)):
        bound = dict(zip(fixed, chosen))
        corners = [dict(bound, **dict(zip(sorted(ranged), ends))) for ends in itertools.product(
            *(domains[name] for name in sorted(ranged)))]
        lights = [tuple(float(point[v.name]) if isinstance(v, P) else float(v) for v in parts)
                  for point in corners]
        if not ranged and len({*lights[0]}) == 1:
            continue  # one value, achromatic
        if ranged and achromatic:
            continue  # achromatic at every value
        for excited in excitations:
            contrasts = [luminance_contrast(L, M, excited) for L, M, _ in lights]
            if min(contrasts) <= tol and max(contrasts) >= -tol:
                return True
    return False


def _can_be(value, params: dict[str, Param], holds, spans) -> bool:
    """Whether `value` can satisfy `holds`: a literal number itself, a parameter any of its
    choices or, with a range of numbers, `spans(low, high)` (low first, however it was
    declared). Anything else can, failing closed: a bound that is no number, which
    `_block_faults` refuses, is read as no bound (the A2 final review's I1)."""
    if isinstance(value, P):
        param = params.get(value.name)
        if param is not None and param.choices:
            return any(not _is_number(c) or holds(float(c)) for c in param.choices)
        if param is not None and _is_number(param.low) and _is_number(param.high):
            return spans(*sorted((float(param.low), float(param.high))))
        return True
    return not _is_number(value) or holds(float(value))


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


def _one_color(what: str, color, panel: Calibration | None, backgrounds: list, *,
               about: str) -> list[Finding]:
    """One light against the calibration, or against its absence: a cone color against each lit
    light the trial's background can be (`_background_lights`), since its conversion and so its
    reach depend on the background (COL-10). A clip of it is about `about` (`_unrealizable`)."""
    if panel is None:
        return [
            Finding(
                "uncalibrated-color",
                f"{what} asks for {color}, but no display calibration was "
                f"supplied; colour is a physical claim and this one is "
                f"unmeasured",
            )
        ]
    # Isoluminance is the lab observer's V_F,10 (A2's Q5), named by `cones.CIE2006_10` and
    # recorded with the session; a measured calibration names its own photometry's observer or
    # does not load (`Calibration`), so nothing is left for a finding here (engine build A2).
    if isinstance(color, CONE_COLORS):
        return [_unrealizable(f"{what} asks for {color} on a background of {background}", why,
                              color, panel, background, what=what, about=about)
                for background in backgrounds
                if (why := unrealizable(color, panel, background)) is not None]
    why = unrealizable(color, panel)
    if why is not None:
        return [_unrealizable(f"{what} asks for {color}", why, color, panel, what=what,
                              about=about)]
    return []


def _unrealizable(said: str, why: str, light, panel: Calibration, background=None, *,
                  what: str, about: str) -> Finding:
    """A light the panel cannot make (engine spec §7.4; COL-08, COL-34, COL-36), `said` naming
    `what` asks for it, and `why` what `photometry.unrealizable` said of it: **a warning naming the
    primary weights it needs and the light the panel shows instead**, accepted in every session
    kind (the PI, 2026-10-11, XC-352's A20: "a warning, and the drawer records the light actually
    shown beside the one asked for"), which `warnings.jsonl` records with the light asked for once
    it is accepted: one part of the task's one `unrealizable-color` warning (`_clips`). A part's
    `subjects` are two: `what`, which its sentence starts with, and `about`, what asks for the
    light and the color as the task wrote it, which the warning is about (`Finding.subjects`).
    **A light that does not convert at all stays a refusal**, saying `why`: a cone color on a
    calibration with no cone matrix, or against a black background, or a weight that is no
    number, has no light to clip (`_clipped`)."""
    clipped = _clipped(light, panel, background)
    if clipped is None:
        return Finding("unrealizable-color", f"{said}: {why}")
    weights, shown = clipped
    return Finding("unrealizable-color", (
        f"{said}: primary weights {weights}, outside [0, 1], so the panel shows {shown}"),
        blocking=False, accepted_in=SESSION_KINDS, subjects=(what, about))


def _clips(findings: list[Finding]) -> list[Finding]:
    """**One `unrealizable-color` warning per task**, where its first part stood, naming each light
    the panel cannot make, what asks for it and the light it shows (the warnings-over-refusals
    review's M8: a warning per light ran the search task's warnings item to thousands of
    characters). A light several things ask for is said once, naming each once -- two written
    colors of one appearance type can ask for the same light. The warning is about what each part
    is (`_unrealizable`), each once (`Finding.subjects`). A light that does not convert at all
    stays its own refusal."""
    parts = [f for f in findings if f.code == "unrealizable-color" and f.is_warning]
    if not parts:
        return findings
    asking: dict[str, list[str]] = {}
    about: list[str] = []
    for part in parts:
        what, subject = part.subjects
        whats = asking.setdefault(part.detail[len(what):], [])
        if what not in whats:
            whats.append(what)
        if subject not in about:
            about.append(subject)
    said = []
    for rest, whats in asking.items():
        if len(whats) > 1 and rest.startswith(" asks for "):
            said.append(f"{', '.join(whats[:-1])} and {whats[-1]} ask for "
                        f"{rest[len(' asks for '):]}")
        else:
            said += [what + rest for what in whats]
    first = findings.index(parts[0])
    rest = [f for f in findings if f not in parts]
    return rest[:first] + [Finding("unrealizable-color", (
        "; ".join(said) + "; the drawer clips each primary weight to [0, 1], and a clipped light "
        "is neither the chromaticity nor the luminance asked for (engine spec §7.4)"),
        blocking=False, accepted_in=SESSION_KINDS, subjects=tuple(about))] + rest[first:]


def _clipped(light, panel: Calibration, background=None) -> "tuple[tuple, str] | None":
    """The primary weights `light` needs on `panel`, to three places, and the light the panel shows
    for it, in words: its weights clipped to [0, 1], as the drawer clips a pixel (`exact.shown`)
    -- or `None` when it names no light the panel can be asked for (a cone color that does not
    convert, a weight that is no number)."""
    import numpy as np

    from wl_xcon import exact
    from wl_xcon.photometry import cone_xyz, to_xyz

    try:
        if isinstance(light, CONE_COLORS):
            if background is None:
                return None
            xyz = cone_xyz(light, panel, background)
        elif isinstance(light, xyY):
            xyz = to_xyz(light)
        else:
            return None
        weights = tuple(round(float(w), 3) for w in panel.weights_of(xyz))
        X, Y, Z = (float(v) for v in exact.shown(np.array([[xyz]], dtype=float), panel)[0, 0])
    except (ValueError, TypeError, OverflowError):
        return None
    total = X + Y + Z
    if not total > 0.0:
        return weights, "black, every primary off"
    return weights, f"x={X / total:.4f}, y={Y / total:.4f}, Y={Y:.4g} cd/m²"


def _default_faults(trial: Trial, params: dict[str, Param]) -> list[Finding]:
    """What the default calibration makes nominal (engine spec §7.2; N§R4: "Yes, from the task
    file"): a task that names a color, or one a parameter of which sets a light or a contrast --
    this build's reading of "a design factor or a procedure-controlled value", until build C lets
    a task declare its factors (Question 2). Each is one warning per task, **accepted in every
    session kind, recording included** (COL-02, revised by the PI on 2026-10-11, XC-352's A21: "a
    warning in recording too"; refused in recording until then), saying that the session's
    `config.json` names the default. Since engine build A2 the color finding also says how the
    default's cone colors converted and which luminance they held."""
    findings = []
    colors = [(what, color) for what, color in _colors(trial, params)
              if isinstance(color, (xyY, *CONE_COLORS))]
    named = sorted({what for what, _ in colors})
    if named and any(isinstance(color, CONE_COLORS) for _, color in colors):
        # 2026-10-08's Q2 (COL-18): the default's cone colors convert through the CIE's matrix
        # outside its definition, and the warning a person accepts says so, and which luminance
        # isoluminance held there (the review's S-I2), so the record does too. Both come before
        # the colors' names, which nothing bounds, so a screen showing a warning's first
        # `link.NOTE_LIMIT` characters shows them (the re-review's M4).
        findings.append(Finding("color-on-default", (
            "on the default calibration, the sRGB standard, measured by nobody (engine spec "
            "§7.2), this task's cone colors (DKL, cone contrast) convert through the inverse of "
            "the CIE's LMS-to-XYZ_F,10 matrix, a use outside the CIE's definition, so how far "
            "each is from the cone contrast it names is unknown, and the luminance they hold "
            f"constant is {HELD_STANDARD}; every color in the data is nominal, and the "
            f"session's config.json names the default calibration; the colors it names: "
            f"{'; '.join(named)}"),
            blocking=False, accepted_in=SESSION_KINDS))
    elif named:
        findings.append(Finding("color-on-default", (
            f"the default calibration is the sRGB standard, measured by nobody, so every color "
            f"this task names is nominal, in a recording as in training, and the session's "
            f"config.json names the default calibration (engine spec §7.2); the colors it names: "
            f"{'; '.join(named)}"),
            blocking=False, accepted_in=SESSION_KINDS))
    set_by = _parameter_lights(trial, params)
    if set_by:
        findings.append(Finding("contrast-on-default", (
            f"parameter(s) {', '.join(repr(name) for name in set_by)} set a light, a contrast or "
            f"an opacity, which this build counts as a design factor until a task can declare its "
            f"own (engine build C): on the default calibration every such value is nominal, in a "
            f"recording as in training, and the session's config.json names the default "
            f"calibration (engine spec §7.2)"),
            blocking=False, accepted_in=SESSION_KINDS))
    return findings


def _parameter_lights(trial: Trial, params: dict[str, Param]) -> list[str]:
    """The parameters that set a light, a contrast or an opacity anywhere a trial can show, by
    name, sorted (the engine B plan, call 24): every parameter inside what lights an
    appearance (`_lit`), a background or a shown or updated stimulus's `opacity` (spec §4.4:
    front covers back by it), **and inside each choice such a parameter offers** -- so a
    parameter that is a `Look`'s whole fill or outline counts and its fills or outlines are
    read (XC-271's shape, and XC-273's outline) -- and an appearance parameter whose
    choices differ in what lights them, an `Array`'s objects included (`_shown`). A parameter
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
    an `Array`'s objects read in turn, and an appearance parameter among them as what each of its
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
#: reads as one, a contrast's `value`, a `Gray`'s `cd_m2`, an `xyY`'s `x`, `y` and `Y`, a
#: `DKL`'s `lum`, `l_m` and `s_lm`, and a `ConeContrast`'s `L`, `M` and `S`.
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
        multiplied = _multiplied(how)
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
            if (mean is not None and not isinstance(mean, P) and not _isoluminant_as_written(mean)
                    and any(mean != b for b in backgrounds)):
                found("luminance-step", (
                    f"{what}'s mean {mean} differs from the background, so a luminance step "
                    f"sits under the pattern (engine spec §4.3: always a warning)"),
                    blocking=False,
                    accepted_in=SESSION_KINDS)  # Always a warning, in every kind (N§R3).
    findings += _cone_color_faults(trial, params, on_black, fix)
    return findings


def _isoluminant_as_written(color) -> bool:
    """A cone color with no luminance step as written: a `DKL` whose `lum` is a literal 0
    (`DKL()` among them), or a `ConeContrast` changing S alone. A grating about such a mean has
    no luminance step under it, so `luminance-step` does not list one (the engine A2 plan's call
    29). One whose L and M sit at V_F,10's ratio still lists one: that ratio needs the
    calibration, which `_light_faults` does not read."""
    if isinstance(color, DKL):
        return _literal(color.lum) == 0.0
    if isinstance(color, ConeContrast):
        return _literal(color.L) == 0.0 and _literal(color.M) == 0.0
    return False


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
        if isinstance(part, CONE_COLORS):
            for field in dataclasses.fields(part):
                # Bounded here, as an `xyY`'s are; whether the panel makes each is `_color_faults`'.
                values(part, field.name)
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


def _whole(value: float) -> float:
    """A count or an index as the run reads it (`int`, as `Array.positions` and
    `ObjectWindows.expand` do), and one without end as it is (`_span`)."""
    return value if math.isinf(value) else int(value)


def _declared_window_names(trial: Trial) -> set[str]:
    """Window names a task has, including every one an array generates.

    An array's objects are named `<of>.<i>` and are as declared as anything an author
    typed -- the whole point is that the author cannot type them, because how many
    there are is not known until a trial runs. Each the task names is declared when its
    index is below the most objects the set size can reach (`_span`), any index when it has
    no highest. **Only the ones the task names are listed**: listing every index up to the
    highest set size made a value sent past its range cost as many names as it is large,
    in the widened check run between two trials (Task 10's review, fix round 2).
    """
    arrays = arrays_of(trial)
    params = {p.name: p for p in trial.params}
    named = set(_window_refs(trial.states))
    names: set[str] = set()
    for window in trial.windows:
        if isinstance(window, ObjectWindows):
            names |= {f"{window.of}.target", f"{window.of}.distractor"}
            array = arrays.get(window.of)
            if array is not None:
                most = _whole(_span(array.n, params, 0.0)[1])
                names |= {name for name in named
                          if (index := _object_index(name, window.of)) is not None
                          and index < most}
        else:
            names.add(window.name)
    return names


def _object_index(name: str, of: str) -> int | None:
    """The index of the object of array `of` that `name` names, exactly as
    `ObjectWindows.expand` names it (`<of>.<i>`), or `None` for any other name: `search.05`
    names no window a trial has."""
    suffix = name[len(of) + 1:] if name.startswith(f"{of}.") else ""
    if not suffix.isdecimal() or suffix != str(int(suffix)):
        return None
    return int(suffix)


def _coupling(trial: Trial) -> dict[str, object]:
    """Which stimulus each window scores, generated families included."""
    scores: dict[str, object] = {}
    for name in _declared_window_names(trial):
        scores[name] = None
    for window in trial.windows:
        if isinstance(window, ObjectWindows):
            for name in list(scores):
                if name.startswith(f"{window.of}."):
                    scores[name] = window.of
        else:
            scores[window.name] = window.on
    return scores


def _array_faults(trial: Trial) -> list[Finding]:
    """An array's target must be one of its objects, for every legal setting.

    Set size and target index are both live parameters, so an experimenter can put
    the target at position 6 of a four-object array between one trial and the next.
    Reasoning over declared ranges is the only way to catch that before it is a
    session rather than a load.

    Each is read over its declared range or its choices (`_span`). **A side either leaves
    undeclared cannot be proved inside the array**, so it gives this finding, saying so (Task
    10's review, fix round 2): a set size with no lowest can be no objects, and a target
    index with no highest past any, or with no lowest below 0, where the target window is
    never one of the objects. Read as 0, either passed at load and widened past its bound. The
    sentence then names the setting and the fix (`_open_sides`; the PI kept this refusal on
    2026-10-14, the final review's I4). A set size with no highest is refused too, by
    `_unbounded_set_sizes`.

    **Every array a `Show` or an `Update` gives** (`_array_actions`), as written or among a
    setting's choices: since XC-402 an array's windows follow an `Update` that changes it, and
    a run builds each one's windows before its first frame, where a target outside the objects
    raises (the XC-402 review, I1).
    """
    params = {p.name: p for p in trial.params}
    findings: list[Finding] = []
    for state, name, updated, looks in _array_actions(trial, params):
        lowest_n = _whole(_span(looks.n, params, 0.0)[0])
        lowest_t, highest_t = (_whole(v) for v in _span(looks.target, params))
        if lowest_t < 0 or highest_t >= lowest_n:
            index = (f"reaching {highest_t}" if math.isfinite(highest_t)
                     else "with no declared highest")
            if math.isinf(lowest_t):
                index += " that can be below 0, its lowest undeclared"
            findings.append(
                Finding(
                    "target-outside-array",
                    f"state {state!r} "
                    + (f"updates {name!r} to an array" if updated else "shows an array")
                    + f" of as few as {lowest_n} objects "
                    f"with a target index {index}; the target must be "
                    f"one of the objects for every setting the console allows, not "
                    f"only the one it has today"
                    + _open_sides(((looks.n, ("lowest",)),
                                   (looks.target, ("lowest", "highest"))), params),
                )
            )
    return findings


def _unbounded_set_sizes(trial: Trial) -> list[Finding]:
    """**A set size declared with no highest is refused at load** (the PI, 2026-10-14, asked of
    "how many items the array has" missing a limit: "Refuse at load"; the final review's I4):
    it can be any number a console sends, inside its range, so the checks widened to a value past
    its highest never run (`beyond_range`, `_overlapping_objects`), and a run builds every object
    and its window before a trial's first frame, so a large enough set size stalls it, a stop, a
    pause and the out-of-cage limit unheard (the final fix wave's concern 1). One declared by
    choices that are all finite numbers has a highest; one with a choice that is no finite number
    has none, failing closed (`_span`). A set size with no lowest is `_array_faults`' to name."""
    params = {p.name: p for p in trial.params}
    findings: list[Finding] = []
    for name, array in _shown_arrays(trial, params):
        if not isinstance(array.n, P) or array.n.name not in params:
            continue  # a literal is its own highest; an undeclared setting is refused at load
        if math.isfinite(_span(array.n, params, 0.0)[1]):
            continue
        # The fix: the missing limit, or, for choices, a choice that is a finite number (the
        # final re-review's m7).
        fix = (f"; {array.n.name!r} offers a choice that is no finite number; give every choice "
               f"as a finite number" if params[array.n.name].choices
               else _open_sides(((array.n, ("highest",)),), params))
        findings.append(Finding("unbounded-set-size", (
            f"array {name!r} can be shown with any number of objects: its set size has no "
            f"declared highest, so a console can send one too large to draw, and a run builds "
            f"every object and its window before a trial's first frame, where a large enough set "
            f"size stalls it, a stop, a pause and the out-of-cage limit unheard" + fix)))
    return findings


def _open_sides(values: tuple, params: dict[str, Param]) -> str:
    """A refusal's last clause naming each setting among `values` -- `(value, sides)`, the sides
    of its range the refusal turns on -- that declares a range and leaves one of those sides
    open, and the fix: "; 'ti' declares no lowest; declare both limits", or "" for none. The PI
    kept these refusals at load (2026-10-14, the final review's I4: "The task author adds the
    missing limit, a one-line fix")."""
    said: dict[str, list[str]] = {}
    for value, sides in values:
        param = params.get(value.name) if isinstance(value, P) else None
        if param is None or param.choices:
            continue
        bounds = {"lowest": param.low, "highest": param.high}
        for side in sides:
            if not _finite(bounds[side]) and side not in said.get(value.name, []):
                said.setdefault(value.name, []).append(side)
    return "".join(f"; {name!r} declares no {' or '.join(sides)}"
                   for name, sides in said.items()) + ("; declare both limits" if said else "")


# --- Stereograms -----------------------------------------------------------


def _stereogram_faults(trial: Trial) -> list[Finding]:
    """A stereogram is a relationship between two images, so it needs both.

    Its correlation is read over its declared range or its choices (`_span`): **a side it
    leaves undeclared reaches past -1 or +1**, so it gives `impossible-correlation`, saying
    so, naming the setting and the fix (`_open_sides`; the PI kept this refusal on 2026-10-14,
    the final review's I4); read as 0, it passed at load and widened past its bound (Task 10's
    review, fix round 2).
    """
    params = {p.name: p for p in trial.params}
    findings: list[Finding] = []
    for state, action in actions_of(trial):
        stimulus = getattr(action, "stimulus", None)
        looks = getattr(stimulus, "looks", None)
        if not isinstance(looks, RDS):
            continue
        low, high = _span(looks.correlation, params)
        if low < -1.0 or high > 1.0:
            reached = [f"{v:g}" for v, out in ((low, low < -1.0), (high, high > 1.0))
                       if out and math.isfinite(v)]
            said = [f"reaches {' and '.join(reached)}"] if reached else []
            said += [f"has no declared {side}" for v, side in ((low, "lowest"), (high, "highest"))
                     if math.isinf(v)]
            findings.append(
                Finding(
                    "impossible-correlation",
                    f"state {state!r} shows a stereogram whose correlation "
                    f"{' and '.join(said)}; correlation runs from -1 "
                    f"(anticorrelated) through 0 (uncorrelated) to +1. A value "
                    f"outside that is not a stronger stimulus, it is not a stimulus"
                    + _open_sides(((looks.correlation, ("lowest", "highest")),), params),
                )
            )
        if getattr(stimulus, "eye", "both") != "both":
            # A warning, not a refusal (XC-352's A11; the PI, 2026-10-11): a monocular control
            # is the experimenter's to choose; the warning says what its trials are not.
            findings.append(
                Finding(
                    "monocular-stereogram",
                    f"state {state!r} shows a stereogram to the "
                    f"{stimulus.eye} eye only; with one eye there is no disparity, only a "
                    f"field of random dots, so these trials are not a disparity condition and "
                    f"are not to be analyzed as one (the task, which each run names by its "
                    f"content hash, says which eye)",
                    blocking=False,
                    accepted_in=SESSION_KINDS,
                )
            )
    return findings


# --- Which eye ---------------------------------------------------------------

EYES = ("both", "left", "right")


def _eye_faults(trial: Trial) -> list[Finding]:
    """Per-eye criteria must name an eye, and must name one that can see.

    A window scoring the eye a stimulus is *not* shown to runs, records, and aborts
    every trial for a reason invisible in the data: the animal was doing the task
    perfectly with the eye nobody scored. **A warning, not a refusal** (XC-352's A10; the
    PI, 2026-10-11), saying so; an eye that is not one of `EYES` is still refused.
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
                    f"animal can do the task perfectly with the seeing eye and fail every "
                    f"trial, for a reason the data will not show",
                    blocking=False,
                    accepted_in=SESSION_KINDS,
                )
            )
    return findings


# --- Reasoning over the whole parameter space ---------------------------------
#
# A task with live parameters is not one configuration, it is a space of them. A
# check against current values proves the task happens not to be broken today; a
# check against declared ranges proves an experimenter cannot break it from the
# console between two trials **with any value inside them**. Since XC-352's D2 a
# console can send a value outside its range too, and that value is checked again
# with the ranges widened to it (`beyond_range`).


def _closest_approach(a: Window, b: Window, params: dict[str, Param]) -> tuple[float, float]:
    """Least possible centre separation, and greatest possible summed radius (`_span`).

    **Each centre is the regions it can be in** (`_centres`): a coordinate given by choices is
    each choice, a point, and one given by a range is that interval, so a window at x -10° or
    10° is never at 0 (the final review's I2: read as the interval between them, it was said to
    come within 0.00° of a window at the centre, and a value sent past its range that made the
    two truly collide was then the same pair only larger, a warning). The corners of the ranges
    alone were wrong whenever the ranges overlap on an axis (Task 10's review, I2): a target
    window over x 0-16° and y ±8° sits on a fixation window at the center at (0, 0), while every
    corner is 8° or more from it. Settings shared between the axes or the windows are read as
    independent, which can only make the separation smaller: a warning, never a pass.

    **The separation is true visual angle, where the centers are** (the PI, 2026-10-19), as a
    window holds gaze (`gaze.Tracked.in_window`), a center written as a `Polar` read as every
    eccentricity and direction its values allow: the least over every pair of regions, searched
    without crossing forty choices an axis into 2.5 million pairs (the final re-review's m4;
    `geometry.least_separation_deg`). Per axis, the hypotenuse of the gaps misread it off the
    axes: windows at (25°, 0°) and (25°, 4.2°) are 3.81° apart, not 4.2°. A whole position as
    one setting (`at=P("pos")`) is still unpacked as a pair, and raises `TypeError` out of
    `check` (XC-156, filed; two tests use such a task as one the checks cannot finish on)."""
    (a_1, a_2, a_polar), (b_1, b_2, b_polar) = (_centers(window.at) for window in (a, b))
    reach = _span(a.radius, params, 0.0)[1] + _span(b.radius, params, 0.0)[1]
    return (least_separation_deg(_intervals(a_1, params), _intervals(a_2, params),
                                 _intervals(b_1, params), _intervals(b_2, params),
                                 polar_a=a_polar, polar_b=b_polar), reach)


def _centers(at: object) -> tuple[object, object, bool]:
    """A window's center as two values and whether they are an eccentricity and a direction
    (a `Polar`) rather than a per-axis pair."""
    if isinstance(at, Polar):
        return at.eccentricity, at.direction, True
    x, y = at
    return x, y, False


def _intervals(
    value: object, params: dict[str, Param], least: float = -math.inf
) -> list[tuple[float, float]]:
    """The values a number can be, as intervals: a literal, or each choice of a setting, a point;
    a range one interval (`_span`, with its `least`). Choices that are not all finite numbers are
    read as `_span` reads them, failing closed. Read by `_closest_approach` for a window's
    coordinate (the final review's I2) and by `_overlapping_objects` for a ring (the final
    re-review's m1): a coordinate or a ring of -10° or 10° is never 0."""
    param = params.get(value.name) if isinstance(value, P) else None
    if param is not None and param.choices and all(_finite(c) for c in param.choices):
        return [(float(c), float(c)) for c in param.choices]
    return [_span(value, params, least)]


def _overlapping_windows(trial: Trial) -> list[Finding]:
    """No two windows a state scores can contain the same point.

    A gaze position inside both satisfies both guards, and the loop takes whichever
    transition is listed first -- so which one scores is decided by editing order.
    That silently relabels errors as correct trials or the reverse, in a task where
    nothing reads as wrong.

    Only windows scored by the *same state* are compared: two windows in different
    states are never both live, and a task that reuses a position across states is
    doing something ordinary. **A warning, not a refusal** (XC-352's A8; the PI,
    2026-10-11): the order is defined (M0 §4) and is part of the task's content, which each
    run names by its hash.
    """
    params = {p.name: p for p in trial.params}
    by_name = {w.name: w for w in trial.windows if not isinstance(w, ObjectWindows)}
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
                gap, reach = _closest_approach(by_name[first], by_name[second], params)
                if gap < reach:
                    radii = (f"their radii sum to {reach:.2f}°" if math.isfinite(reach)
                             else "a radius has no declared highest, so they can be any size")
                    findings.append(
                        Finding(
                            "overlapping-windows",
                            f"state {state.name!r} scores {first!r} and {second!r}, "
                            f"which can come within {gap:.2f}° while {radii}; "
                            f"a gaze position inside both "
                            f"satisfies both guards, and which one scores is decided "
                            f"by the order the transitions happen to be written in, so "
                            f"a look at one can count as the other",
                            blocking=False,
                            accepted_in=SESSION_KINDS,
                            subjects=(f"state {state.name!r}: {pair[0]!r} and {pair[1]!r}",),
                        )
                    )
    return findings


def _unreachable_timeouts(trial: Trial) -> list[Finding]:
    """A time bound that another always beats is dead code.

    It reads as a safety net, so the case it was meant to catch goes unprotected and
    nobody notices -- the line is right there. Ranges again: two bounds whose ranges
    cross are both live, because either can win depending on the setting; a side a setting
    leaves undeclared reaches 0 below and without end above (`_span`), never the 0 to 0 it
    was once read as, which called a bound dead that a setting could still let win. **A
    review note, never a refusal** (XC-352's A7; the PI, 2026-10-11): the state still has its
    other bound.
    """
    params = {p.name: p for p in trial.params}
    findings: list[Finding] = []
    for state in trial.states:
        bounds = [
            (edge, _span(edge.guard.seconds, params, 0.0))
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
                        f"same state always fires first, for every legal setting, which is "
                        f"probably a mistake",
                        blocking=False,
                    )
                )
    return findings


def _holds_cut_short(trial: Trial) -> list[Finding]:
    """A `Hold` that an `After` on the same state can beat, within their declared ranges, is a hold
    cut off in progress: the trial ends on the timeout, scored as whatever it leads to, while the
    animal is still holding (the engine C2a plan's science review, O2: a held target scored a miss
    when `target_hold` was set past `response_deadline`). **A warning, never a refusal** (the PI,
    2026-10-11: warnings over refusals), naming the state, the hold, the bound and their settings.
    Only a plain `After` is compared -- one with a `since` starts later -- and a bound naming the
    hold's own setting cannot beat it **unless it is listed before the hold**: a state's edges are
    evaluated in order and a tie fires on one frame, so the first listed wins it (an `After` first
    is warned when its lowest is at most the hold's highest). It assumes the hold starts as the
    state is entered; a state the gaze enters later is not modeled. Each setting is read through
    `_span`, as every range check is: a side its range does not bound reaches as far as that
    side can go, so a hold with no highest can be cut short by any timeout, and a timeout with
    no lowest can end at once."""
    params = {p.name: p for p in trial.params}

    def span(value) -> "tuple[float, float] | None":
        if isinstance(value, P) or _is_number(value):
            return _span(value, params, 0.0)
        return None

    def said(value) -> str:
        return f"`{value.name}`" if isinstance(value, P) else f"{value:g} s"

    findings: list[Finding] = []
    for state in trial.states:
        holds = [edge for edge in state.go if isinstance(edge.guard, Hold)]
        bounds = [edge for edge in state.go
                  if isinstance(edge.guard, After) and edge.guard.since is None]
        for hold in holds:
            for bound in bounds:
                held, waits = span(hold.guard.seconds), span(bound.guard.seconds)
                if held is None or waits is None:
                    continue
                # Edges are evaluated in order and a tie fires on one frame: a timeout listed
                # first wins it, so it beats a hold up to its highest; listed after, it must
                # fall short of the hold's highest, and its own setting never does.
                first = state.go.index(bound) < state.go.index(hold)
                if not first and bound.guard.seconds == hold.guard.seconds:
                    continue
                if waits[0] <= held[1] if first else waits[0] < held[1]:
                    longest = (f"up to {held[1]:g} s" if math.isfinite(held[1])
                               else "with no longest declared")
                    findings.append(Finding("hold-cut-short", (
                        f"state {state.name!r} ends on its {_target_name(bound.to)} timeout after "
                        f"{said(bound.guard.seconds)}, as soon as {waits[0]:g} s, while its "
                        f"{hold.guard.window!r} hold takes {said(hold.guard.seconds)}, "
                        f"{longest}: an animal still holding is cut off and scored "
                        f"{_target_name(bound.to)}; bound the state by a wait longer than the "
                        f"longest hold"), blocking=False, accepted_in=SESSION_KINDS))
    return findings


def _target_name(target: object) -> str:
    return target.name if isinstance(target, Outcome) else repr(target)


def _crowded_arrays(trial: Trial) -> list[Finding]:
    """An array's own objects must not overlap, for any legal setting.

    Set size, eccentricity and window radius are all live, so crowding is something
    an experimenter dials in between two trials: twelve objects on a small ring with
    generous windows overlap, and a saccade to one distractor is then scored against
    another, or against the target. **Nobody ever reads these windows** -- they are
    generated, which is the whole point of `ObjectWindows` and the reason this needs a
    check rather than an author's eye.

    The worst case is the most objects on the smallest ring with the largest windows:
    adjacent centers are `2·asin(sin R·sin(π/n))` apart (`geometry.ring_spacing_deg`), the
    objects on a true circle about the array's own direction and each window where its object is
    drawn, at any phase and position (the PI, 2026-10-19, "True circle"; XC-397), and two
    windows touch when that falls below their summed radius. Each is read over its declared
    range or its choices (`_span`), the count as the run reads it, a whole number (`_whole`): a count or a radius
    with no highest can be any size, and crowds; a ring with no lowest can be 0 (Task 10's
    review, I2). **A warning, not a refusal** (XC-352's A9; the PI, 2026-10-11), saying which
    settings crowd it. A set size sent past its range that draws the objects on one another,
    windows or none, is refused (`_overlapping_objects`). **Every array a `Show` or an `Update`
    gives the family's stimulus** (`_shown_arrays`): since XC-402 the windows follow an `Update`
    that changes the array (the XC-402 review, I1).
    """
    params = {p.name: p for p in trial.params}
    findings: list[Finding] = []
    for declared in trial.windows:
        if not isinstance(declared, ObjectWindows):
            continue
        for name, array in _shown_arrays(trial, params):
            if name == declared.of:
                findings += _crowded(declared, array, params)
    unique: list[Finding] = []
    for finding in findings:  # two arrays crowding alike are one warning
        if finding not in unique:
            unique.append(finding)
    return unique


def _crowded(declared: ObjectWindows, array: Array, params: dict[str, Param]) -> list[Finding]:
    """`crowded-array` for one array of a family, or nothing (`_crowded_arrays`)."""
    most = _whole(_span(array.n, params, 0.0)[1])
    tightest = _span(array.radius, params, 0.0)[0]
    widest = _span(declared.radius, params, 0.0)[1]
    if most < 2:
        return []
    spacing = ring_spacing_deg(tightest, most)
    if spacing >= 2.0 * widest:
        return []
    objects = "any number of" if math.isinf(most) else f"{int(most)}"
    windows = "of any" if math.isinf(widest) else f"of {widest:g}°"
    return [
        Finding(
            "crowded-array",
            f"array {declared.of!r} can put {objects} objects on a "
            f"{tightest:g}° ring, {spacing:.2f}° apart, with windows "
            f"{windows} radius; adjacent objects would overlap and a "
            f"saccade to one would be scored against another",
            blocking=False,
            accepted_in=SESSION_KINDS,
            subjects=(f"array {declared.of!r}",),
        )
    ]


def _overlapping_objects(trial: Trial, raised: dict[str, float]) -> list[Finding]:
    """**A set size sent above its highest** (`raised`, by setting) **whose array would draw its
    objects on one another, refused** (the final review's I1), with object windows or without:
    what D2 refuses as breaking the run (the PI, 2026-10-11, XC-352's D2: "refuse only what would
    break the run"). A run builds every object, and its window, before a trial's first frame
    (`Array.positions`, `expand_windows`) and resolves each every frame, so a set size far past
    its range stalls `taskd` there, a stop, a pause and the out-of-cage limit unheard until it is
    built -- and `crowded-array` cannot say so: it reads windows, which an array need not have,
    and the declared task's warning about the same array, only larger, waives it. No timing is
    claimed: past where adjacent objects overlap a larger set size draws nothing more and only
    adds work, and objects of any size above 0 overlap at some set size (`visual_search`'s 1°
    objects on its 5° ring past 31, computed), so no set size is left to stall the run.

    **The reading** (I1: "the object size as the task declares it, the ring radius at its
    least"): adjacent centers `2·asin(sin R·sin(π/n))` apart on the array's true circle
    (`geometry.ring_spacing_deg`; the PI, 2026-10-19), `n` the value sent and `R` the least the
    ring's radius can be, its distance from 0 -- each choice a point (`_intervals`; the final
    re-review's m1), a range read at its least and 0 where it reaches 0, has no lowest or
    crosses 0, a deliberate fail-closed for a degenerate ring (XC-378) -- against the smallest
    object the array can show, so that the objects are drawn on one another on the tightest ring
    whatever else the console sets (`_narrowest`). The sentence names the fix, the most that ring
    keeps apart (`_most_apart`). A set size sent below its lowest draws fewer objects, further
    apart, and is never refused here."""
    params = {p.name: p for p in trial.params}
    findings: list[Finding] = []
    for name, array in _shown_arrays(trial, params):
        if not (isinstance(array.n, P) and array.n.name in raised):
            continue
        n = _whole(raised[array.n.name])
        if n < 2:
            continue
        ring = min(0.0 if low <= 0.0 <= high else min(abs(low), abs(high))
                   for low, high in _intervals(array.radius, params, 0.0))
        spacing = ring_spacing_deg(ring, n)
        size = min(_narrowest(array.looks, params), _narrowest(array.among, params))
        if spacing >= size:
            continue
        most = _most_apart(ring, size)
        across = (f"closer than its smallest object is across ({size:g}°), so they would be drawn "
                  f"on one another, where "
                  + (f"at most {most} stay apart" if most >= 2 else "not even two stay apart")
                  if math.isfinite(size)
                  else "and no object it can show declares a width this check can read, so "
                  "nothing shows them drawn apart")
        on = (f"its {ring:g}° ring" if not isinstance(array.radius, P)
              else f"its ring at its least, {ring:g}°")
        findings.append(Finding("overlapping-objects", (
            f"array {name!r} at {n:g} objects would put adjacent objects {spacing:.2f}° apart on "
            f"{on}, {across}; that breaks the run (XC-352's D2): a run builds every object and "
            f"its window before a trial's first frame, so past where they overlap a larger set "
            f"size only adds work, and far past it the run stalls there, a stop, a pause and the "
            f"out-of-cage limit unheard until it is built")))
    return findings


def _most_apart(ring: float, size: float) -> int:
    """The most objects a ring of radius `ring` keeps apart, adjacent centers
    `2·asin(sin R·sin(π/n))` at least `size` (`geometry.ring_spacing_deg`): the fix an
    `overlapping-objects` refusal names (the final re-review's m7). 1 when not even two are,
    across its diameter."""
    if not (ring > 0.0 and 0.0 < size <= ring_spacing_deg(ring, 2)):
        return 1
    share = math.sin(math.radians(size / 2.0)) / math.sin(math.radians(ring))
    most = max(2, math.floor(math.pi / math.asin(min(1.0, share))))
    while most > 2 and ring_spacing_deg(ring, most) < size:
        most -= 1  # rounding at the boundary
    while ring_spacing_deg(ring, most + 1) >= size:
        most += 1
    return most


def _shown_arrays(trial: Trial, params: dict[str, Param]) -> list[tuple[str, Array]]:
    """Every array a trial can show, with the stimulus that shows it: a `Show`'s looks or an
    `Update`'s, as written or among a parameter's choices."""
    found: list[tuple[str, Array]] = []
    for _, name, _, array in _array_actions(trial, params):
        if (name, array) not in found:
            found.append((name, array))
    return found


def _array_actions(trial: Trial, params: dict[str, Param]) -> list[tuple[str, str, bool, Array]]:
    """`_shown_arrays` by the action that gives each: the state, the stimulus's name, whether an
    `Update` gives it, and the array, as written or among a parameter's choices."""
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


def _narrowest(
    looks: object, params: dict[str, Param], inside: frozenset[str] = frozenset()
) -> float:
    """The least width, in degrees, an array's object can be drawn at: over each appearance
    `looks` can be -- each choice of a parameter -- the narrowest of the full widths it declares
    (`_SIZES`; a `Look`'s are its shape's), each at the least its setting allows (`_span`), and a
    polygon's the circle inside its sides, its size being the circle through its corners. Each
    object holds a disc that wide about its centre, so two whose centres are closer than it are
    drawn on one another. **One that declares none** -- a `Blank`, a `Look` drawn by its points
    or over the whole screen, an appearance a parameter offers none of -- **is without end**,
    failing closed: nothing shows such objects drawn apart."""
    from wl_xcon import look
    from wl_xcon.task import Polygon

    if isinstance(looks, P):
        param = params.get(looks.name)
        if param is None or looks.name in inside or not param.choices:
            return math.inf
        return min(_narrowest(choice, params, inside | {looks.name}) for choice in param.choices)
    if isinstance(looks, look.Look):
        return _narrowest(looks.shape, params, inside)
    if not dataclasses.is_dataclass(looks):
        return math.inf
    # A size that is no number is refused at load (`_block_faults`), and read as nothing here.
    widths = [getattr(looks, f.name) for f in dataclasses.fields(looks) if f.name in _SIZES]
    least = min((_span(width, params, 0.0)[0] for width in widths
                 if isinstance(width, P) or _finite(width)), default=math.inf)
    if isinstance(looks, (Polygon, look.RegularPolygon)) and math.isfinite(least):
        # Fewer than 3 sides, or sides that are no number, are refused at load (`_block_faults`).
        sides = looks.sides if isinstance(looks.sides, P) or _finite(looks.sides) else 3.0
        least *= math.cos(math.pi / max(3.0, _span(sides, params, 3.0)[0]))
    return least


# --- Which setup -------------------------------------------------------------

#: What `Trial.view` may say (direct-view spec §3): one setup, or either.
TRIAL_VIEWS = (*VIEWS, "either")


def _nonzero(value) -> bool:
    """Whether a disparity can be other than zero: a parameter can."""
    return isinstance(value, P) or bool(_literal(value))


def _modulates(looks, params: dict[str, Param], inside: frozenset[str] = frozenset()) -> bool:
    """Whether a stimulus can multiply the contrast below it, for every value it can take:
    a pattern, or a flat Weber contrast (a gain of 1 + c). An absolute light names no gain.
    An `Array` modulates only if each of its objects does, and a parameter only if each of
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
    its objects can, a parameter if any of its choices can, a mean parameter if any choice is
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
    if trial.periphery == "center_scale":
        findings.append(Finding("center-scale-retired", (
            'periphery="center_scale" draws every stimulus at the screen center\'s size per '
            'degree, which the PI retired on 2026-10-19 ("Every stimulus is drawn in true visual '
            'angle; a task declaring center scale is refused at load"): remove it, or write '
            '"true_angle", and each stimulus is drawn in true visual angle about its own '
            "direction, the same size wherever it is")))
    elif trial.periphery not in PERIPHERY:
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
    a geometry, a task written for the other setup is a warning, naming both and saying what
    the other setup changes** (XC-352's A12; the PI, 2026-10-11), unless it is a stereoscope
    task that shows each eye its own image -- a disparity, one eye, a position or a
    background per eye (`_per_eye_content`) -- in direct view, which an unmirrored screen
    cannot show, and that stays refused. The field check holds it to the setup it runs in
    (`_offscreen_stimuli`), so a caller that passes the session's geometry has nothing else
    to do. `taskd` and
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
        written = (f"the task is written for {trial.view!r} and is checked against "
                   f"{geometry.view!r}")
        both = _stereo_content(trial) + _per_eye_content(trial)
        if geometry.view == "direct" and both:
            findings.append(Finding("wrong-setup", (
                f"{written}: {both[0]}, which an unmirrored screen cannot show, since each eye "
                f"would see both images (direct-view spec §3)")))
        elif geometry.view == "direct":
            findings.append(Finding("wrong-setup", (
                f"{written}: here both eyes see the whole panel, unmirrored, at "
                f"{geometry.viewing_distance_cm:g} cm; it shows nothing that needs each eye "
                f"its own image, so it runs, but it was not designed for this setup "
                f"(direct-view spec §3)"), blocking=False, accepted_in=SESSION_KINDS))
        else:
            stop = ("its field" if geometry.mask_deg is None
                    else f"the ±{geometry.mask_deg:g}° mask")
            findings.append(Finding("wrong-setup", (
                f"{written}: here each eye sees its own half of the panel, inside "
                f"{stop}, through the mirrors at "
                f"{geometry.viewing_distance_cm:.2f} cm; its positions and sizes are degrees, so "
                f"they hold, but it was not designed for this setup (direct-view spec §3)"),
                blocking=False, accepted_in=SESSION_KINDS))
    return findings


def _per_eye_content(trial: Trial) -> list[str]:
    """What a stereoscope task shows each eye that `_stereo_content` does not name: a position
    per eye (engine spec §5.4), by a `Show` or an `Update`, and a background per eye (§4.4). An
    unmirrored screen cannot show either, so neither runs in direct view (`_view_faults`)."""
    found = []
    for state, action in actions_of(trial):
        if isinstance(action, Show) and (
            action.stimulus.at_left is not None or action.stimulus.at_right is not None
        ):
            found.append(f"state {state!r} gives {action.stimulus.name!r} a position per eye")
        elif isinstance(action, Update) and any(
            action.changes().get(eye) is not None for eye in ("at_left", "at_right")
        ):
            found.append(f"state {state!r} gives {action.stimulus!r} a position per eye")
    if trial.background_left is not None or trial.background_right is not None:
        found.append("it gives each eye its own background")
    return found


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
    `choices` entry is `0.0`, or `low == high == 0.0`. An undeclared parameter, or one with
    neither a two-sided range nor `choices`, is not provably anything, so it counts as
    stereo content rather than failing open the way the `(0, 0)` that `_widest` read such a
    parameter as did (`_widest` is gone since Task 10's review, fix round 2; `_span`).
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
