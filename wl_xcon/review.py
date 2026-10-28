"""What a human reviews instead of source.

ADR-0006's acceptance test: a task Claude wrote is approved from a rendered state
diagram, a table of every event code with the state that emits it, the declared
parameters with their ranges, and a simulation report. **If a task cannot be
reviewed from these, the design failed rather than the reviewer.**

The diagram is Mermaid, so it renders in the repository, in a pull request, and in
anything the lab already reads -- rather than needing a viewer nobody has installed
at 8am.
"""

from __future__ import annotations

from dataclasses import fields, is_dataclass

from wl_xcon.task import (
    COUNTED,
    OWED,
    SPENT,
    UNPAID,
    After,
    Background,
    Custom,
    Mark,
    Guard,
    NoChoice,
    Outcome,
    P,
    Hide,
    ObjectWindows,
    Reward,
    Show,
    Stimulus,
    Task,
    Trial,
    Update,
    actions_of,
)


#: The separator in every sequence this artifact renders. A named constant
#: because it is a non-ASCII escape and `review.py` is the one module where such an
#: escape reached an f-string expression and broke Python 3.11.
ARROW = " \u2192 "


def _value_label(value: object) -> str:
    """A parameter reference by name, a literal duration with its unit.

    The unit belongs to the *literal*, not to the name: `After(fix_acquisitions)` reads
    as a parameter nobody declared, and a reviewer who stops trusting the diagram
    goes back to reading source -- which is the thing this artifact replaces.
    """
    if isinstance(value, P):
        return value.name
    if isinstance(value, float):
        return f"{value:g}"
    return str(value)


def _guard_label(guard: Guard) -> str:
    """A guard as a reviewer would say it out loud.

    Unset optional fields are omitted rather than rendered as `None`: a diagram that
    says `After(0.3s, None)` is noisier than the source it replaces, and noise is how
    a reviewer stops reading the artifact. What is *set* is always shown -- an SOA
    timed from photodiode onset rather than state entry is a different experiment,
    so `since` appears whenever it is there.
    """
    given = [
        (name, getattr(guard, name))
        for name in guard.__slots__
        if getattr(guard, name) is not None
    ]
    rendered = [
        _value_label(value) if name != "since" else f"since={_guard_label(value)}"
        for name, value in given
    ]
    label = f"{type(guard).__name__}({', '.join(rendered)})"
    if isinstance(guard, After) and isinstance(guard.seconds, float):
        head, _, tail = label.partition(f"{guard.seconds:g}")
        label = f"{head}{guard.seconds:g}s{tail}"
    return label


def _point_label(at: object) -> str:
    """A position, **eccentricity and direction first, its per-axis (x, y) beside them** (the PI,
    2026-10-19, "Polar first, x-y allowed"): `8° at 45° · (x, y) (5.675, 5.675)`, a `Polar` as
    written and a pair converted exactly (`geometry.polar_deg`'s inverse), each to a
    thousandth; a value a setting holds by its name, and a pair holding one per axis alone, as
    no number converts. Anything else is shown as written: a position's shape is not checked at
    load (XC-272), and an artifact that raises shows nothing at all."""
    from wl_xcon.geometry import polar_deg, polar_of_deg
    from wl_xcon.task import Polar

    def number(value) -> bool:
        return isinstance(value, (int, float)) and not isinstance(value, bool)

    def deg(value: float) -> str:
        return f"{round(value, 3) + 0.0:g}"

    if isinstance(at, Polar):
        e, d = at.eccentricity, at.direction
        polar = " at ".join(f"{_value_label(v)}°" if number(v) else _value_label(v) for v in (e, d))
        if not (number(e) and number(d)):
            return polar
        x, y = polar_deg(e, d)
        return f"{polar} · (x, y) ({deg(x)}, {deg(y)})"
    if isinstance(at, tuple) and len(at) == 2:
        pair = f"(x, y) ({_value_label(at[0])}, {_value_label(at[1])})"
        if not (number(at[0]) and number(at[1])):
            return pair
        e, d = polar_of_deg(float(at[0]), float(at[1]))
        return (f"{deg(e)}°" + (f" at {deg(d)}°" if round(e, 3) else "") + f" · {pair}")
    return _value_label(at)


def _position_label(stimulus: Stimulus) -> str:
    """Where a stimulus is drawn: each eye's own position when it has them, which are
    drawn in place of `at` (engine spec §5.4)."""
    if stimulus.at_left is not None or stimulus.at_right is not None:
        return f"L {_point_label(stimulus.at_left)} / R {_point_label(stimulus.at_right)}"
    return _point_label(stimulus.at)


def _light_label(color: object) -> str:
    """A background as the source declares it, its parameters by name. Unset is said:
    the drawer puts black there, and a blank would read as nothing declared. Something
    that is not a color is shown as written: `wlx review` checks nothing first, and an
    artifact that raises shows nothing at all."""
    if color is None:
        return "black (default)"
    if isinstance(color, P) or not is_dataclass(color):
        return _value_label(color)
    values = ", ".join(_value_label(getattr(color, f.name)) for f in fields(color))
    return f"{type(color).__name__}({values})"


def _background_label(trial: Trial) -> str:
    """The trial's background; each eye's on the stereoscope, where each can have its own
    (`screen.resolve`: an eye's own, else the trial's, else black)."""
    per_eye = trial.background_left is not None or trial.background_right is not None
    if trial.view == "stereoscope" or per_eye:
        left = trial.background if trial.background_left is None else trial.background_left
        right = trial.background if trial.background_right is None else trial.background_right
        return f"left eye {_light_label(left)}; right eye {_light_label(right)}"
    return _light_label(trial.background)


def _scores_label(on: object) -> str:
    """What a window scores. `REMEMBERED` is spelled out, because a window with
    deliberately nothing in it is a claim the reviewer should see made."""
    if on is None:
        return "**nothing declared**"
    if isinstance(on, str):
        return f"`{on}`"
    return "*remembered location*"


def _target_label(target: object) -> str:
    return target.name if isinstance(target, Outcome) else str(target)


def _timeline(trial: Trial) -> list[str]:
    """When each stimulus is on the display, and what happens to it.

    **Position and disparity are not enough.** Every defect the 2026-08-31 reviews
    found was about *when* something was on screen -- a fixation point removed at the
    moment fixation was asked for, an SOA timed from the wrong zero -- so an artifact
    showing only position is a picture a reviewer trusts of the half of the task that
    was never the problem.

    States are listed in declaration order, which is the order a reader follows; it
    is not an execution order, and a branching task has none.
    """
    events: dict[str, list[str]] = {}
    for state in trial.states:
        for action in list(state.enter) + [a for e in state.go for a in e.do]:
            if isinstance(action, Show):
                events.setdefault(action.stimulus.name, []).append(
                    f"shown in `{state.name}`"
                )
            elif isinstance(action, Hide):
                events.setdefault(action.stimulus, []).append(
                    f"hidden in `{state.name}`"
                )
            elif isinstance(action, Update):
                changed = ", ".join(sorted(action.changes()))
                events.setdefault(action.stimulus, []).append(
                    f"changed in `{state.name}` ({changed})"
                )
    if not events:
        return []
    lines = ["## Display timeline", "", "| Stimulus | On screen |", "|---|---|"]
    for name, happenings in events.items():
        if not any(step.startswith("hidden") for step in happenings):
            # Said explicitly rather than left blank: an empty cell reads as missing
            # information, and "never taken down" is a decision worth seeing.
            happenings = happenings + ["**until the trial ends**"]
        # Joined outside the f-string: a backslash inside an f-string *expression*
        # is a syntax error before Python 3.12 (PEP 701 relaxed it), and this
        # package declares >=3.11. The 3.11 CI job is the only thing that can catch
        # that -- a 3.12+ interpreter parses it happily, so it cannot be found
        # locally, and it made `wlx review` unimportable on the declared floor for
        # four days while nothing was pushed.
        sequence = ARROW.join(happenings)
        lines.append(f"| `{name}` | {sequence} |")
    lines.append("")
    return lines


def render(trial: Trial, allocation_names: dict[int, str] | None = None) -> str:
    names = allocation_names or {}
    lines: list[str] = ["## Trial structure", "", "```mermaid", "stateDiagram-v2"]
    lines.append(f"    [*] --> {trial.start}")
    for state in trial.states:
        for edge in state.go:
            lines.append(
                f"    {state.name} --> {_target_label(edge.to)}: "
                f"{_guard_label(edge.guard)}"
            )
    lines += ["```", ""]

    # **Named by transition, not only by state.** A state can strobe one code on
    # entry and another on each outgoing edge, and an artifact attributing them all
    # to the state cannot be checked against a recording -- which is the one thing
    # this table is for.
    lines += ["## Event codes", "", "| Code | Meaning | Emitted by | When |",
              "|---|---|---|---|"]
    for state in trial.states:
        for action in state.enter:
            if isinstance(action, Mark):
                lines.append(
                    f"| {action.code} | {names.get(action.code, '**UNALLOCATED**')} "
                    f"| `{state.name}` | on entry |"
                )
        for edge in state.go:
            for action in edge.do:
                if isinstance(action, Mark):
                    lines.append(
                        f"| {action.code} "
                        f"| {names.get(action.code, '**UNALLOCATED**')} "
                        f"| `{state.name}` | on {ARROW.strip()} {_target_label(edge.to)} |"
                    )
    lines.append("")

    lines += _timeline(trial)

    if trial.windows:
        lines += ["## Windows", "", "| Name | Centre | Radius | Scores | Eye |",
                  "|---|---|---|---|---|"]
        # Every array a `Show` or an `Update` gives each stimulus, as the checker reads them
        # (`check._array_actions`): an `Update` that grows an array makes windows its `Show` does
        # not (XC-402), and the row read only the `Show`'s count (XC-411).
        from wl_xcon.check import _array_actions

        counts: dict[str, list[str]] = {}
        for _, name, _, array in _array_actions(trial, {p.name: p for p in trial.params}):
            label = _value_label(array.n)
            if label not in counts.setdefault(name, []):
                counts[name].append(label)
        for window in trial.windows:
            if isinstance(window, ObjectWindows):
                # A family, described as one: how many members it has is a
                # parameter, so listing them would be listing one configuration.
                count = " or ".join(counts.get(window.of, [])) or "?"
                lines.append(
                    f"| `{window.of}.*` | {count} objects on a ring "
                    f"| {_value_label(window.radius)} | `{window.of}` "
                    f"| {window.eye} |"
                )
                continue
            lines.append(
                f"| `{window.name}` | {_point_label(window.at)} | {_value_label(window.radius)} "
                f"| {_scores_label(window.on)} | {window.eye} |"
            )
        lines.append("")

    if trial.params:
        lines += ["## Parameters", "", "| Name | Unit | Range | Live |", "|---|---|---|---|"]
        for param in trial.params:
            lines.append(
                f"| {param.name} | {param.unit} | {param.low}–{param.high} "
                f"| {'yes' if param.live else 'no'} |"
            )
        lines.append("")

    welfare = [
        (name, action)
        for name, action in actions_of(trial)
        if isinstance(action, (Reward, Custom))
    ]
    if welfare:
        lines += ["## Needs human review", ""]
        for name, action in welfare:
            what = (
                f"reward, bounded by `{action.ref.name}`"
                if isinstance(action, Reward)
                else f"custom component `{action.name}`"
            )
            lines.append(f"- `{name}`: {what}")
        lines.append("")

    stimuli = [
        (name, action.stimulus)
        for name, action in actions_of(trial)
        if isinstance(action, Show)
    ]
    # Everything the drawer places and combines by (engine spec §4.4, §5.4), as each `Show`
    # declares it: a table of position and disparity alone left the rest of the screen
    # unreviewed (XC-259). The background is stated with or without a `Show`: a blank
    # screen is still one the animal sees.
    lines += ["## Stimuli", "", f"Background: {_background_label(trial)}", ""]
    if not stimuli:
        lines += ["Nothing is shown: no state has a `Show`.", ""]
    else:
        # On the stereoscope a cyclopean position is drawn at ± the vergence offset; an
        # L / R row is already each eye's own direction (engine spec §5.4).
        lines += ["Disparity° is azimuth-longitude disparity: the left eye's image at x − d/2 and "
                  "the right eye's at x + d/2, in per-axis horizontal degrees (STE-07).", "",
                  "| State | Stimulus | Position° (cyclopean, or each eye's) | Disparity° | Eye "
                  "| Layer | Combination | Opacity |",
                  "|---|---|---|---|---|---|---|---|"]
        for name, stimulus in stimuli:
            lines.append(
                f"| `{name}` | `{stimulus.name}` | {_position_label(stimulus)} "
                f"| {_value_label(stimulus.disparity)} | {stimulus.eye} "
                f"| {_value_label(stimulus.layer)} | {stimulus.combine} "
                f"| {_value_label(stimulus.opacity)} |"
            )
        lines.append("")

    return "\n".join(lines)


def render_task(task: Task, allocation_names: dict[int, str] | None = None) -> str:
    """A task's review report (engine spec §18.1; engine build C1). **First what a reviewer
    confirms** (XC-288 §4: "the person reviewing the task confirms it, in the review report"): the
    task's content hash, each setting's role, meaning and where it comes from -- the shared list,
    the task's own, or the task's override of the shared list with why (the PI, 2026-10-11) -- the
    bounded settings it rewards through, how its reaction time is defined, what it offers to
    choose, whether it needs a fixed head, and what each trial does to its condition's count
    (engine build C2a). **Then each trial structure**, the default first,
    as `render` draws one, a heading level down. Nothing is checked first, as `wlx review` checks
    nothing: an undeclared meaning is shown as one, and a content that cannot be hashed says so."""
    from wl_xcon.declarations import BOUNDED, OVERRIDE, content_hash, resolved, rewarded_through

    try:
        identity = "`" + content_hash(task) + "`"
    except (TypeError, ValueError) as unread:
        identity = "**cannot be hashed**: " + _cell(str(unread))
    lines = [
        "# Task review",
        "",
        f"Content: {identity} (XC-288 §4.4), as each run's start row names it.",
        "",
        "## What a reviewer confirms",
        "",
        "### What each setting means",
        "",
        "| Setting | Unit | Role | Meaning | Direction | Note | From |",
        "|---|---|---|---|---|---|---|",
    ]
    meanings = resolved(task)
    for param in task.params:
        found = meanings.get(param.name)
        if found is None:
            lines.append(f"| {param.name} | {param.unit} | **UNDECLARED** | | | | |")
            continue
        meaning, origin = found
        source = origin + ": " + _cell(meaning.overrides) if origin == OVERRIDE else origin
        lines.append(
            f"| {param.name} | {param.unit} | {meaning.role} | {meaning.kind} "
            f"| {_direction(meaning, param)} | {_cell(meaning.note)} | {source} |"
        )
    lines.append("")
    rewarded = sorted(rewarded_through(task))
    if rewarded:
        lines += ["### Bounded settings it rewards through", "",
                  "| Setting | Role | Meaning | Note |", "|---|---|---|---|"]
        for name in rewarded:
            meaning = BOUNDED.get(name)
            lines.append(
                f"| {name} | **UNDECLARED** | | |" if meaning is None
                else f"| {name} | {meaning.role} | {meaning.kind} | {_cell(meaning.note)} |"
            )
        lines.append("")
    timed = task.reaction_time
    if timed is None:
        said = "**Not declared.**"
    else:
        ends = " or ".join("`" + _target_label(end) + "`" for end in timed.to)
        said = f"From entering `{timed.state}` to leaving it for {ends}: {_cell(timed.note)}."
    lines += ["### Reaction time", "", said, ""]
    if task.choice is None:
        offered = "**Not declared.**"
    elif isinstance(task.choice, NoChoice):
        offered = "None: the task offers no choice."
    else:
        objects = ", ".join("`" + window + "`" for window in task.choice.objects)
        offered = f"{objects}, chosen by a {task.choice.by}."
    lines += ["### Choice", "", offered, ""]
    head = (
        "Needs a fixed head: a warning, not a refusal, in any session not declared head-fixed "
        "(`RIG_FIXED`; engine spec §20.1)."
        if task.needs_fixed_head
        else "Runs with the head fixed or free; a chaired session lists its free head as a warning."
    )
    lines += ["### Head", "", head, ""]
    lines += _counting(task)
    for name in (task.default, *(other for other in task.structures if other != task.default)):
        heading = f"## Structure `{name}`"
        if name == task.default:
            heading += ", the default: its runs play it until plans exist (engine build C2)"
        lines += [heading, "", _demoted(render(task.structures[name], allocation_names)), ""]
    return "\n".join(lines)


#: A counting class in the words the PI confirms it in (the engine C2a plan's Appendix B).
_CLASS_WORDS = {COUNTED: "counted", SPENT: "used up", OWED: "shown again", UNPAID: "pays nothing"}


def _counting(task: Task) -> list[str]:
    """What each trial does to its condition's count, structure by structure (engine spec
    §16.1-16.2; engine build C2a): the state its stimulus appears in; every outcome's class once
    the stimulus has appeared and before it, and a hang's; whether withholding is an answer; the
    repeat limit. A structure without a table, or whose table names no such state, says so, which
    the load-time check refuses (`undeclared-counting`)."""
    lines = ["### What each trial does to its condition's count", ""]
    for name in (task.default, *(other for other in task.structures if other != task.default)):
        table = task.structures[name].counting
        if table is None:
            lines += [f"Structure `{name}`: **no counting table**, which the load-time check "
                      f"refuses.", ""]
            continue
        appears = (f"its stimulus appears in `{table.appears}`" if table.appears is not None
                   else "**it names no state its stimulus appears in**")
        withholding = ("withholding is an answer, so no response is a miss" if table.withholding
                       else "withholding is no answer")
        limit = ("no repeat limit: a condition is repeated until done" if table.cap is None
                 else f"a repeat limit of {table.cap} failed repeats in a row")
        lines += [f"Structure `{name}`: {appears}; {withholding}; {limit}.", "",
                  "| Outcome | After the stimulus appears | Before it |", "|---|---|---|"]
        rows = [(outcome.value, outcome) for outcome in Outcome]
        for said, outcome in [*rows, ("hang (the five-minute cap)", None)]:
            lines.append(f"| {said} | {_CLASS_WORDS[table.of(outcome)]} "
                         f"| {_CLASS_WORDS[table.of(outcome, shown=False)]} |")
        lines.append("")
    return lines


def _demoted(text: str) -> str:
    """`render`'s report a heading level down, to sit under its structure's heading."""
    return "\n".join("#" + line if line.startswith("## ") else line for line in text.split("\n"))


def _cell(text: str) -> str:
    """Text for one cell of a Markdown table: a bar escaped, a line break a space."""
    return text.replace("|", "\\|").replace("\n", " ")


def _direction(meaning, param) -> str:
    """Which way a setting moves the task, as `Meaning.raising` reads (the engine C1 plan's call
    4): changing a list of choices; raising a number; or moving it away from what it reads
    relative to -- a number, another setting, or the trial's background."""
    if meaning.raising is None:
        return "none"
    if param.choices:
        return f"changing it: {meaning.raising}"
    relative = meaning.relative_to
    if relative is None:
        return f"raising it: {meaning.raising}"
    if isinstance(relative, Background):
        return f"farther from the background: {meaning.raising}"
    if isinstance(relative, str):
        return f"farther from `{relative}`: {meaning.raising}"
    return f"farther from {relative:g}: {meaning.raising}"
