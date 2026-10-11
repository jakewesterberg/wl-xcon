"""What a task declares about its settings beyond its trials (XC-288 §4; engine build C1): the shared
list of the common settings' meanings, the table of the bounded settings' meanings, each of a task's
settings' meaning as resolved, and the task's content hash.

**The shared list** (the PI, 2026-10-11: "a shared list of common settings, override allowed with a
note"). A setting several tasks use alike is declared once, here: a task using that name inherits
its meaning, and may override it only with a note saying why (`Meaning.overrides`), which the task's
declarations, its content hash and its review report all carry. A setting only one task has, or one
that means a different thing in each task using it, is declared by each task (`Task.meanings`).
Every changeable setting ends up with a meaning, and `check.check_task` refuses a task that leaves
one without (XC-288 §4.1: "a missing declaration cannot be told from a forgotten one").

**Each meaning says whether its setting is a criterion or a stimulus** (the PI, 2026-10-11): what
counts as success, or what the animal sees. The bounded settings are neither: a consequence and a
session limit.

**The bounded settings' meanings live here, outside `bounds.py`** (XC-288 §4.1): `reward_correct`
and the out-of-cage limit change live and are declared in the subject's bounded config, whose loader
is welfare-listed and which the task check does not read.

Each entry is the engine C1 plan's proposal (its Appendix B), confirmed by the PI as a numbered list
before that build merged (decisions.md TRN-10). An expected direction is recorded as expected, never
as a fact (XC-288 §4.1).
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
from enum import Enum

from wl_xcon.task import (
    BACKGROUND, CLEAR_CUT, CRITERION, EASIER, EXPECTED, HARDER, NEITHER, NOT_DIFFICULTY, STIMULUS,
    Meaning, Reward, Task, Unchanged, actions_of,
)

#: Where a resolved meaning came from: the shared list, the task's own declaration of a setting only
#: it has, or the task's override of a shared one.
SHARED = "shared list"
OWN = "this task"
OVERRIDE = "overrides the shared list"

#: **The shared list**: every setting two or more reference task files use with one meaning (the
#: engine C1 plan's call 5; its Appendix B, items 4 to 18). A direction reads on raising a number,
#: on moving it away from a reference (`relative_to`), or on changing a list of choices (call 4).
COMMON: dict[str, Meaning] = {
    # Fixation.
    "fix_timeout": Meaning(CLEAR_CUT, CRITERION, raising=EASIER),
    "fix_hold": Meaning(CLEAR_CUT, CRITERION, raising=HARDER),
    "fix_window": Meaning(CLEAR_CUT, CRITERION, raising=EASIER),
    "fix_luminance": Meaning(EXPECTED, STIMULUS, raising=EASIER, relative_to=BACKGROUND, note=(
        "a point farther in luminance from the background is easier to find: on black a brighter "
        "one; on a gray one farther above or below it, so a point near the gray's luminance can "
        "vanish")),
    # Responding.
    "response_window": Meaning(CLEAR_CUT, CRITERION, raising=EASIER),
    "target_hold": Meaning(CLEAR_CUT, CRITERION, raising=HARDER),
    "target_window": Meaning(CLEAR_CUT, CRITERION, raising=EASIER),
    "item_window": Meaning(EXPECTED, CRITERION, raising=EASIER, note=(
        "a wider window accepts a less accurate landing on the target, and can also turn a "
        "near-miss beside a distractor into a wrong target")),
    # The target.
    "target_looks": Meaning(EXPECTED, STIMULUS, raising=HARDER, note=(
        "where to look does not change, but a new look can slow or confuse an animal over the "
        "next few trials: a change along a feature the task does not use; going back to a "
        "familiar look is not harder")),
    "target_luminance": Meaning(EXPECTED, STIMULUS, raising=EASIER, note=(
        "a brighter target is easier to see on black; saccade latency falls as intensity rises "
        "and then levels off, so far above threshold more light changes little")),
    "target_position": Meaning(EXPECTED, STIMULUS, raising=HARDER, relative_to=0, note=(
        "farther from fixation a saccade lands less accurately, and beyond about 10 degrees the "
        "tracker can lose the eye's fourth Purkinje image, which is the rig's harder, not the "
        "animal's; near the center the direction can turn over, the target sitting by the "
        "fixation window and small saccades being slower; which side can matter to an animal "
        "with a bias")),
    # The search array.
    "set_size": Meaning(EXPECTED, STIMULUS, raising=HARDER, note=(
        "while an animal learns, more items mean fewer lucky guesses, chance being 1/n, which is "
        "chance's harder, not the animal's; once it finds the odd item, more items change little")),
    "distractors": Meaning(EXPECTED, STIMULUS, raising=HARDER, note=(
        "read with the target's look: a change can leave the target looking like the distractors, "
        "with no answer, or differing by color, by shape or by both, which is easier; a color swap "
        "slows the next few trials (priming of pop-out)")),
    "target_index": Meaning(NOT_DIFFICULTY, STIMULUS, note="which item of the ring is the target"),
    "array_phase": Meaning(NOT_DIFFICULTY, STIMULUS, note="turns the whole ring"),
}

#: **The bounded settings' meanings** (XC-288 §4.1; Appendix B, items 29 and 30): what changes live
#: in a subject's bounded config, read here and never from `bounds.py`. Neither a criterion nor a
#: stimulus: a consequence and a session limit.
BOUNDED: dict[str, Meaning] = {
    "reward_correct": Meaning(NOT_DIFFICULTY, NEITHER, note=(
        "what a correct trial pays, a consequence: it changes what the animal works for, not how "
        "hard a trial is; a larger reward can keep an animal working, and sate it sooner")),
    "out_of_cage": Meaning(NOT_DIFFICULTY, NEITHER, note=(
        "the welfare limit on time out of the home cage, a session limit: it bounds the session, "
        "not a trial")),
}


def resolved(task: Task) -> dict[str, tuple[Meaning, str]]:
    """Each of `task`'s settings (`Task.params`) with its meaning and where that came from: the
    task's own declaration first -- an override when the name is on the shared list -- else the
    shared list's. **A setting with neither is left out**, and `check.check_task` refuses the task,
    naming it."""
    found: dict[str, tuple[Meaning, str]] = {}
    for param in task.params:
        own = task.meanings.get(param.name)
        if own is not None:
            found[param.name] = (own, OVERRIDE if param.name in COMMON else OWN)
        elif param.name in COMMON:
            found[param.name] = (COMMON[param.name], SHARED)
    return found


#: **The content's format** (the engine C1 plan's call 11), part of every task's content: raised
#: when a field's default changes, since `canonical` leaves a field at its default out and the
#: change would otherwise alter what a task does without moving its hash. A field added at its
#: default needs no raise. `tests/test_declarations.py` holds every default to the format it was
#: written at (`DEFAULTS`).
FORMAT = 1


def rewarded_through(task: Task) -> set[str]:
    """The bounded-config entries `task`'s structures reward through, by name (`Reward.ref`)."""
    return {
        action.ref.name
        for structure in task.structures.values()
        for _, action in actions_of(structure)
        if isinstance(action, Reward)
    }


def _at_default(spec: dataclasses.Field, value: object) -> bool:
    """Whether a dataclass field holds the default its class declares."""
    if spec.default is not dataclasses.MISSING:
        return value == spec.default
    if spec.default_factory is not dataclasses.MISSING:
        return value == spec.default_factory()
    return False


def canonical(value: object) -> object:
    """`value` as plain data for the content hash (the engine C1 plan's call 11): each declaration
    by its class's name and the fields it sets away from their defaults -- so a field a later build
    adds, at its default, leaves every task's hash as it was, and a default that changes raises
    `FORMAT` -- an `Enum` by its class and value, and sequences and text-keyed dicts element by
    element. **A `Reward` is read for the entry it names before the dataclass rule**, which would
    read no field of it (call 19). Anything else raises `TypeError`: a value written by its
    address would make every process's hash its own."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, Enum):
        return {"enum": type(value).__name__, "value": canonical(value.value)}
    if isinstance(value, (list, tuple)):
        return [canonical(item) for item in value]
    if isinstance(value, dict):
        for key in value:
            if not isinstance(key, str):
                raise TypeError(f"a declaration's keys are text, and {key!r} is not")
        return {key: canonical(item) for key, item in value.items()}
    if isinstance(value, Reward):
        return {"class": "Reward", "fields": {"ref": canonical(value.ref)}}
    if isinstance(value, Unchanged):
        return {"class": "Unchanged", "fields": {}}
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {"class": type(value).__name__, "fields": {
            spec.name: canonical(getattr(value, spec.name))
            for spec in dataclasses.fields(value)
            if not _at_default(spec, getattr(value, spec.name))
        }}
    raise TypeError(
        f"{type(value).__name__!r} is not a declaration the task's content hash can read"
    )


def content(task: Task) -> dict:
    """What `task` declares, as `canonical` writes it (XC-288 §4.4), under the content's `FORMAT`:
    the task object -- its structures, default, reaction time, choice, own meanings and whether it
    needs a fixed head -- every setting's meaning as resolved, since a shared meaning is part of
    what a task declares, and the meaning of each bounded setting it rewards through, which its
    review report shows beside the hash. Not its file, its path, or its between-trial Python
    (call 11)."""
    return {
        "format": FORMAT,
        "task": canonical(task),
        "meanings": canonical({name: meaning for name, (meaning, _) in resolved(task).items()}),
        "bounded": canonical(
            {ref: BOUNDED[ref] for ref in rewarded_through(task) if ref in BOUNDED}
        ),
    }


def content_hash(task: Task) -> str:
    """The task's identity in the record (XC-288 §4.4: "always: a hash of its content, never its file
    path"): `"sha256:"` and the hex digest of `content(task)` written as JSON with sorted keys and
    no spaces. Each run's start row carries it as `versions.task` (`taskd.Session.run`)."""
    text = json.dumps(content(task), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return "sha256:" + hashlib.sha256(text.encode("ascii")).hexdigest()
