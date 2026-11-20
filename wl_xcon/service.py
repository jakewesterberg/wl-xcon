"""`wlx taskd` -- the rig service (P4d-2b spec §6.1).

One process on the rig PC, all day: idle until a console opens a session, then one
animal's session across as many runs as the operator starts, until its return to the cage
is recorded, and then idle again for the next animal. **All of one animal's welfare state
lives in one `taskd.Session`** (PI, 2026-09-29: "One always-on rig service"), which is
the shape S9a §7 drew; nothing carries from one session to the next.

Its commands are the link's -- `OpenSession`, `CheckRun`, `StartRun`, `EndSession` and
`ResumeSession` beside b2a's -- over the socket `wlx run --link` binds. **They are read
once per housekeeping pass while no run is in progress, and at each trial boundary during
one**, never per frame (the b3a-1 plan, decision 18). A run sees the link through `_Routed`:
**an `EndSession` during a run stops it**, and the session ends once the run has
returned; any other of the service's own commands during a run is refused, never kept
for later. **Every run is checked before it starts** (`_start`): its pre-flight taken
again, and S9a §10's rule asked of it -- fail blocks, an unknown proceeds only on a named
acknowledgement written into `runs.jsonl`. **A run's fault is contained** (decision 14):
published, written into its end row, said on stderr, and the session left open between
runs with its animal still out, so the return can be taken.

**After a crash, nothing new opens until the stranded session is ended or resumed** (spec
§6.1; XC-026). On start the service finds every session under `--root` with a departure
and no return (`stranded.find`), and while one exists it opens no session, for that
animal or any other, until an `EndSession` naming it records the return -- **or a
`ResumeSession` naming it resumes that same session from its record** (XC-026,
`_resume`), which is not a new one. A record that cannot carry a resume is refused one,
so its only recovery is its return.

**A confirm or an amend is taken only as the answer to a question this service posed**
(the b3a-1 review's Ruling 1, 2026-09-29; `_unasked`). The PI's rule for a far mark is a
warning the experimenter must click through (2026-09-20), and the wire cannot tell a
click-through from a confirm sent blind in the first request. So a far mark with no
answer puts a `Question` on the frame; an answer is taken while that question is pending,
for its mark, its session and the instant it asked about -- and, for a departure, the
animal, deployment and setup of the open it was asked about; and **the question stays
until it is answered or another replaces it**, so a refused answer -- an amendment with
no reason -- can be corrected and sent again without the warning being lost.

**Every mark is taken on one thread** (the b3a-1 review's Ruling 2): the departure, its
amendment, the head's fixation and release and the return are each taken while a command
is routed, on the thread running `serve`, one command at a time -- which is what lets
`taskd.Session.returned_to_cage` run without the lock it once had.

**Welfare-critical: `Service._open`, `Service._end` (with `Service._unended`, its
refusals before anything is stopped or marked), `Service._close_stranded`,
`Service._start`, `_unasked` and `_folder_name`** (`docs/design/architecture.md`): the
page's route into the two marks, the stranded rule, which answers are taken, the gate a
run passes before it starts, and the rule that keeps a name from any wire or record from
becoming a path out of `--subjects` or `--tasks`. The rest is ordinary.

**The simulators, today**: the card, the pump and the animal are `wlx run`'s, because no
hardware port exists (docs/CHECKPOINT.md: nothing has touched hardware); a rig's own
replace them when they do.

**Demo mode** (its design §3.1-§3.7): a session whose eye is the mouse on its page
(`pointer`), on the simulated card and pump, for the test monkey, `REFERENCE`, kept apart from
real data by where it is written. **`wlx taskd --demo DIR` is a demo service**: `DIR` made new
(`demo_folder`), holding `REFERENCE` alone and the folder its sessions go to, every open in it a
demo (`Service._route`), its card and pump the simulators always. **A rig service opens a demo
only with a demo folder of its own** (`--demo-root`; the PI, 2026-11-14, "A demo folder of its
own"), never under `--root`, so a demo never sits among the real sessions and a stranded one
never holds up a real animal's open (`Service._in_demo_root`); **a real session stranded there is
the session it is** (`_demo_folder_split`), holding up every open, and warned of at start. Either
way a demo needs the link's fourth endpoint, where its page's pointer reports arrive; it is never
resumed, only ended; and its pre-flight names the mouse as its gaze and gives each input a key
(`Service._preflight`). **A demo opens only through `Service._open`'s demo path**, its two
changes the PI approved (demo mode §8; 2026-11-07, "Approve both and the design"): a demo for any
animal but `REFERENCE` is refused before anything is written, and a demo is built on the simulated
card and pump, and on an unmeasured rig the stand-in field, whatever the service was built with. A
demo command reaching `_session_for` by any other path is refused, never quietly a live session.
"""

from __future__ import annotations

import argparse
import dataclasses
import fcntl
import gc
import json
import os
import re
import secrets
import shutil
import sys
import tempfile
import threading
import time
import traceback
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import TypeVar

from wl_xcon import cli as _cli
from wl_xcon import link as _link
from wl_xcon import marks as _marks
from wl_xcon import pointer
from wl_xcon import preflight as _preflight
from wl_xcon import resume as _resume_mod
from wl_xcon import stranded as _stranded
from wl_xcon import warnlist
from wl_xcon.actor import Actor
from wl_xcon.bounds import Bounds, Exceeded
from wl_xcon.cli import (
    _load_allocation,
    _load_bounds,
    _load_calibration,
    _load_rig,
    _load_subject_settings,
    _printable,
)
from wl_xcon.check import in_reach
from wl_xcon.codes import Allocation
from wl_xcon.dio import Simulated as SimulatedCard
from wl_xcon.geometry import NOMINAL_HALF_IPD_CM, Rig, stand_in_housings
from wl_xcon.photometry import SRGB, Calibration
from wl_xcon.record import XCON_DIRNAME
from wl_xcon.taskd import (
    Demo, RunSpec, Session, SessionSpec, bounds_record, ended_said, start_rows,
)
from wl_xcon.welfare import OUT_OF_CAGE, Deployment, SessionClock
from wl_xcon.welfare import Simulated as SimulatedPump

#: Seconds between housekeeping passes while no run is in progress: one frame published,
#: the link drained, a mark stamped. The wait ends early when a command or a mark
#: arrives. **A display cadence, not a measurement** -- `await_return`'s own, and well
#: inside `ZmqConsole`'s 5 s receive timeout.
HOUSEKEEPING_S = 1.0

#: The framework events every session here strobes on paths any session can reach:
#: head-fixation at open, its release at the end, an applied setting, and each run's
#: start and end (the b3a-1 plan, decision 12).
FRAMEWORK_CODES = ("HEAD_FIXED", "HEAD_RELEASED", "PARAM_CHANGED", "RUN_START", "RUN_END")

#: The frame period every session here runs at: `wlx run`'s own (`cli.main`).
FRAME_PERIOD = 1 / 240

#: One folder name (the b3a-1 plan, decision 19): a session id, an animal or a task
#: file, each of which becomes a path. Letters, digits, `_`, `.` and `-`, starting with
#: a letter or digit -- so never `.`, `..`, or anything with a separator.
_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}")

#: **The test monkey**, a demo's one animal (demo mode §3.1, §3.7): the subject of the checkout's
#: reference bounded configs, whose files refuse any real animal.
REFERENCE = "REFERENCE"

#: **Why a stranded demo is offered only *end*** (demo mode §8, Review Focus 7): what its banner
#: and a resume's refusal say. A crashed demo never comes back as a live session.
DEMO_UNRESUMED = "a demo is never resumed, only ended: record its return with End session"

#: **Where a rig service says it runs on this computer** (demo mode §5 item 3; its plan's Task 10,
#: the planner's call): every `wlx taskd` without `--demo` holds a shared `flock` on this file for its
#: life (`run`), and `wlx demo` asks an exclusive one without waiting and is refused while it cannot
#: have it (`demo.run`), since a demo's drawing would share the processor a live session's frames
#: run on; a demo's children hold its exclusive one with it. In the temporary folder, so it is this
#: computer's -- this user's, where the temporary folder is a user's own, as macOS gives one.
#: `WLX_RIG_LOCK` names another file (`rig_lock`), for tests.
RIG_LOCK = Path(tempfile.gettempdir()) / "wlx-taskd.lock"


def rig_lock() -> Path:
    """The rig lock's file: the one `WLX_RIG_LOCK` names, else `RIG_LOCK`."""
    named = os.environ.get("WLX_RIG_LOCK")
    return Path(named) if named else RIG_LOCK


def lock_rig(*, exclusive: bool, wait: bool = False) -> "int | None":
    """**The rig lock taken** (`RIG_LOCK`): shared, as a rig service holds it, or exclusive, as
    `wlx demo` asks it; without waiting, `None` while another holds it the other way, or with
    `wait`, once it can be had. Its open descriptor, which holds it until it is closed and is
    passed to a child that is to hold it too. The file is made if absent, and opened to read
    only, which is all a lock needs, so one user's file serves another's."""
    path = rig_lock()
    try:
        fd = os.open(path, os.O_RDONLY)
    except FileNotFoundError:
        fd = os.open(path, os.O_RDONLY | os.O_CREAT, 0o644)
    try:
        fcntl.flock(fd, (fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)
                    | (0 if wait else fcntl.LOCK_NB))
    except BlockingIOError:
        os.close(fd)
        return None
    except BaseException:
        os.close(fd)
        raise
    return fd


def demo_folder(path: Path) -> tuple[Path, Path]:
    """**A demo service's folder** (`wlx taskd --demo DIR`; demo mode §3.1): `path` made new,
    **refused if it exists**, holding a subjects folder with **`REFERENCE` alone** -- its
    `bounds.py` and `settings.py` copied from the checkout's `tasks/eight_hour_bounds.py` and
    `tasks/reference_subject.py` (the PI, 2026-10-07: "The 8-hour file"; `cli.checkout_tasks`,
    refused with no checkout) -- and an empty folder its sessions go to. Returned as `--subjects`
    and `--root` would be. **Nothing is made before every refusal has passed**, so a refused
    `--demo` leaves nothing behind. A demo service reaches no real animal's files and no rig's
    data: these are the only ones it is given."""
    path = Path(path)
    if path.exists():
        raise SystemExit(
            f"refused: --demo {_printable(str(path))} exists, and a demo's folder is made new, so "
            f"it holds nothing of another's. Nothing was made"
        )
    tasks = _cli.checkout_tasks()
    files = {"bounds.py": tasks / "eight_hour_bounds.py",
             "settings.py": tasks / "reference_subject.py"}
    for source in files.values():
        if not source.is_file():
            raise SystemExit(
                f"refused: {_printable(str(source))} is not there, and a demo's {REFERENCE} is "
                f"written from it. Nothing was made"
            )
    subjects, root = path / "subjects", path / "sessions"
    try:
        (subjects / REFERENCE).mkdir(parents=True)
    except FileExistsError as made:
        raise SystemExit(
            f"refused: --demo {_printable(str(path))} was made by something else as this one made "
            f"it, and a demo's folder is its own"
        ) from made
    for name, source in files.items():
        shutil.copyfile(source, subjects / REFERENCE / name)
    root.mkdir()
    return subjects, root


def _within(inner: Path, outer: Path) -> bool:
    """Whether `inner` is `outer` or inside it, both resolved."""
    inner, outer = Path(inner).resolve(), Path(outer).resolve()
    return inner == outer or outer in inner.parents


def _demos_marked(found: list, root: Path) -> list:
    """`found`, the stranded sessions under `root`, **each demo's marked not resumable**, saying
    why (`DEMO_UNRESUMED`), so its banner offers only *end* (demo mode §8): one whose
    `config.json` carries `demo` (`resume.is_demo`). **Here, not in `stranded.find`**, which is
    welfare-listed: as `Service._resume` marks one past its limit. A record whose welfare notes
    cannot be read keeps its own sentence: it is repaired by hand first."""
    return [
        dataclasses.replace(entry, resumable=False, why=DEMO_UNRESUMED)
        if entry.left_at is not None
        and _resume_mod.is_demo(Path(root) / entry.session_id / XCON_DIRNAME)
        else entry
        for entry in found
    ]


def _not_demos(demo_root: Path) -> list[tuple[str, str]]:
    """**Every session in a rig's demo folder that is no demo**, stranded or not, as `(session id,
    animal)`, in folder order: a folder holding an `xcon` record whose `config.json` does not say
    `demo` for `REFERENCE` (`resume.is_demo`), the animal its `config.json` names, or `""` when it
    cannot be read. What `wlx taskd` warns of at every start (the build's re-review, N2): a demo
    folder holds demos alone, and a real session left there -- ended, resumed and ended, or
    stranded -- is named each time until it is moved out."""
    found = []
    root = Path(demo_root)
    if not root.is_dir():
        return found
    for record in sorted(root.glob(f"*/{XCON_DIRNAME}")):
        if not record.is_dir():
            continue
        try:
            config = json.loads((record / "config.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            config = None
        subject = config.get("subject") if isinstance(config, dict) else None
        subject = subject if isinstance(subject, str) else ""
        if subject == REFERENCE and _resume_mod.is_demo(record):
            continue
        found.append((record.parent.name, subject))
    return found


def _demo_folder_split(found: list, demo_root: Path) -> tuple[list, list]:
    """`found`, the stranded sessions in a rig's demo folder (`--demo-root`), as **the demos and
    the rest**. A demo is a record whose `config.json` carries `demo` (`resume.is_demo`) **and**
    whose animal is `REFERENCE`, marked not resumable (`DEMO_UNRESUMED`). **Every other one is the
    real session it is** (the whole-build review's I1, 2026-11-16): a real animal's session left
    in a folder later named as `--demo-root` -- by a typo, last week's root, a sibling rig's share
    -- or a record nobody can read, which fails closed. It is marked as one under `--root` is
    (`_demos_marked`), and `Service` holds it in `stranded`, where it holds up every open."""
    demos, real = [], []
    for entry in found:
        if (entry.left_at is not None and entry.subject == REFERENCE
                and _resume_mod.is_demo(Path(demo_root) / entry.session_id / XCON_DIRNAME)):
            demos.append(dataclasses.replace(entry, resumable=False, why=DEMO_UNRESUMED))
        else:
            real.append(entry)
    return demos, _demos_marked(real, demo_root)


def _folder_name(name: str) -> bool:
    """**Welfare-critical** (fix round 1 of Task 7). Whether `name` is one folder name
    (`_NAME`, and no `..`): the one rule for a session id and an animal arriving over the
    wire, for the animals the idle frame offers, and for a stranded record's animal,
    whose `bounds.py` is code this service runs -- so a name that is not one never
    becomes a path, and nothing outside `--subjects` runs for it."""
    return _NAME.fullmatch(name) is not None and ".." not in name


def _fresh_seed() -> int:
    """A run's seed, drawn here and written into its start row (the b3a-1 plan,
    decision 15), so the run can be replayed."""
    return secrets.randbelow(2**31)


def _sentence(refused: BaseException) -> str:
    """What a refusal says: a `SystemExit`'s message, or the exception's own. **It raises when
    that message's own `str()` does**, so a refusal raised by code the service does not own
    goes through `_sentence_or` instead. Kept as it was because `Service._close_stranded`,
    welfare-critical, says a bounded config's fault and a return's refusal through it: making
    this fault-safe would change that function unreviewed (XC-291 holds both sites)."""
    return str(refused.code if isinstance(refused, SystemExit) else refused)


def _sentence_or(refused: BaseException, failing: str) -> str:
    """`_sentence`, for a refusal raised by code the service runs and does not own -- a task
    file, an animal's `bounds.py` or `settings.py` -- or, when its own `str()` raises,
    `failing` with the refusal said by its type (`_said`), so saying it does not become a fault
    that stops `wlx taskd` (XC-291). **`_said`'s limits are this one's**: a `KeyboardInterrupt`
    goes on, and a `str()` that never returns is not bounded."""
    try:
        return _sentence(refused)
    except KeyboardInterrupt:
        raise
    except BaseException:  # noqa: BLE001 -- see the docstring
        return f"{failing}: {_said(refused)}"


def _type_name(broken: BaseException) -> str:
    """The name `broken`'s class was made with, read through `type`'s own descriptor -- so a
    metaclass that redefines `__name__`, to raise or to give something that is not text, is
    never asked -- and copied out as a plain `str`, since that descriptor will also hold a
    `str` subclass, whose own `__format__` could raise (XC-291's review, M1)."""
    return str.__str__(type.__dict__["__name__"].__get__(type(broken)))


def _said(broken: BaseException) -> str:
    """`Type: message` for a fault -- or its type's name alone (`_type_name`) when its own
    `str()` raises, whatever it raises, `SystemExit` included -- so saying a fault does not
    become a second one where code the service does not own can raise it: a pre-flight item
    (`_unfinished`), a build (`Service._built`), a run that did not start (`Service._run`), a
    refusal's own sentence (`_sentence_or`), and `run`'s own fault handler, which must still
    reach the shutdown that records an open session's return as not recorded (XC-291 and its
    review's M1). **Its one limit is chosen**: a `KeyboardInterrupt` raised while the message
    is said goes on, so Ctrl-C still ends `wlx taskd` as this module says it does; and a
    `str()` that never returns is not bounded here.

    **`_fault` beside it is kept as it was**, because `Service._open`, welfare-critical, says a
    listing fault through it: hardening `_fault` would change that function unreviewed, so the
    same edges there go to the PI with XC-298."""
    name = _type_name(broken)
    try:
        return f"{name}: {broken}"
    except KeyboardInterrupt:
        raise
    except BaseException:  # noqa: BLE001 -- see the docstring
        return name


def _fault(broken: BaseException) -> str:
    """`Type: message` for a fault -- or its type's name alone when its own `str()` raises, so
    saying a fault never becomes a second one (`Service._idle_warnings`)."""
    try:
        return f"{type(broken).__name__}: {broken}"
    except Exception:  # noqa: BLE001 -- see the docstring
        return type(broken).__name__


def _local(at: float) -> str:
    """An instant as this host's local date and time, to the second, with its zone."""
    return time.strftime("%Y-%m-%d %H:%M:%S (%Z)", time.localtime(at))


def _unasked(
    question: _link.Question | None,
    mark: str,
    session_id: str,
    text: str | None,
    now: Callable[[], float] | None = None,
    posed_for: tuple = (),
    sent_for: tuple = (),
) -> str | None:
    """**Welfare-critical** (the b3a-1 review's Ruling 1). Why an answer sent with the
    time `text` -- a page's *confirm*, or a departure's *amend* -- is not the answer to
    the question this service posed, or `None` when it is: the question pending, for
    this `mark`, this session, and the instant `text` is read as by the parser
    `marks.page_departure` and `marks.page_return` read it with (`now` for a return,
    which may be typed `now`) -- **and for what the question was posed for**
    (`posed_for`, against the answer's `sent_for`; fix round 1 of Task 7): a departure's
    warning names one animal and was asked about one open, so its animal, deployment and
    setup must be the answer's too. A return's question is bound by its session alone,
    which fixes all three.

    **PI, 2026-09-20:** a far mark is *"a warning ... that the experimenter must click
    through to confirm"*. A console learns of the warning only from the `Question` on a
    frame, and nothing on the wire tells a confirm clicked on it from one sent blind in
    the first request, so an answer is taken only while its question is pending -- and
    only for the instant it asked about, since a confirm of another time, or of another
    session's mark, is a confirm of something no warning was shown for. Refused before
    anything is built or marked."""
    at = None
    if text is not None:
        try:
            at = _marks._page_time(text, now)
        except argparse.ArgumentTypeError as bad:
            return str(bad)
    if question is not None and (question.mark, question.session_id) == (mark, session_id):
        if question.at == at and posed_for == sent_for:
            return None
        if question.at == at:
            return (
                f"the warning shown was for session {session_id}'s {mark} of "
                f"{', '.join(map(repr, posed_for))}, and this {mark} is of "
                f"{', '.join(map(repr, sent_for))}; an answer is taken only for what it "
                f"was asked about, so it is refused and nothing was recorded. Send it "
                f"without an answer, and answer the warning shown for it"
            )
        return (
            f"the warning shown was for session {session_id}'s {mark} at "
            f"{_local(question.at)}, and this {mark} is "
            f"{'given no time' if at is None else 'at ' + _local(at)}; an answer is taken "
            f"only for the time it was asked about, so it is refused and nothing was "
            f"recorded. Send the time without an answer, and answer the warning shown "
            f"for it"
        )
    answer = "a confirmation or an amendment" if mark == "departure" else "a confirmation"
    return (
        f"{answer} answers the warning a far {mark} is shown with, and none is owed for "
        f"session {session_id}'s {mark}, so it is refused and nothing was recorded: the "
        f"warning is one the experimenter clicks through (PI, 2026-09-20). Send the time "
        f"without an answer, and answer the warning if one is shown"
    )


def _unfinished(names: tuple[str, ...], broken: BaseException) -> tuple:
    """A fail for each of `names`, the pre-flight items whose check raised `broken`, said
    through `_said`, so one whose own `str()` raises is said by its type (XC-291)."""
    return tuple(
        _link.PreflightItem(
            name,
            _preflight.FAIL,
            f"this item's check did not finish: {_said(broken)}",
        )
        for name in names
    )


def _contained(names: tuple[str, ...], build: Callable[[], object]) -> tuple:
    """The items `build` returns -- one, or a list -- or, if it raises, a fail for each
    of `names` (`Service._preflight`)."""
    try:
        built = build()
    except Exception as broken:  # noqa: BLE001 -- `Service._preflight`'s docstring
        return _unfinished(names, broken)
    return tuple(built) if isinstance(built, list) else (built,)


#: What `Service._built` returns: whatever the build it is given returns.
_Built = TypeVar("_Built")

#: What a resume refused by code it does not own says, when that code's own sentence
#: cannot be said (`_sentence_or`).
_UNRESUMED = "the session could not be resumed"

#: The service's own commands: taken between runs, never handed to a run.
_SERVICE_COMMANDS = (
    _link.OpenSession, _link.CheckRun, _link.StartRun, _link.EndSession, _link.ResumeSession,
)

#: **The service's commands taken in any phase** (the console settings build's Task 8): never a
#: run's, and never refused for a run in progress -- a new color is saved as its set's proposed
#: file between runs and at a run's boundary alike (`Service._define_color`).
_ANY_PHASE = (_link.DefineColor,)


class _Routed:
    """The link a service session drains through (the b3a-1 plan, decision 18): the
    service's own link, with the service's commands taken out of what a run sees.

    **An `EndSession` during a run stops it** -- a `Stop` in its place, at the boundary
    that drained it -- and is kept for the service to finish once the run has returned
    (`Service.step`), since `Service._end` is for a session between runs or awaiting
    its return. One `_end` would refuse before anything is marked (`Service._unended`)
    is refused here instead, before anything is stopped. Any other service command
    during a run is refused on the session's feed: a run is in progress. **Everything
    else is the real link's**: `mark_signal` and `idle` are the link's own bound
    methods, so the per-frame mark check is the call V12 measured, with nothing added;
    and so is `gaze_into`, with `gaze_endpoint`, which a demo's mouse reads its page's
    pointer reports through, up to `pointer.DRAIN` a frame (demo mode §3.8).
    `publish`, once per trial boundary and never per frame, is the link's too, and also
    keeps the frame a session closes with for the idle frames that follow
    (`Service.closed`); a demo's world also publishes its screen through it inside a trial, a
    `link.Drawn`, which passes through as it is (demo mode §3.9)."""

    def __init__(self, link, service: "Service") -> None:
        self._link = link
        self._service = service
        self.mark_signal = link.mark_signal
        self.idle = link.idle
        self.gaze_into = link.gaze_into

    @property
    def gaze_endpoint(self) -> str | None:
        """The real link's gaze endpoint, or `None` for one with none (the `Link` protocol)."""
        return self._link.gaze_endpoint

    def publish(self, frame) -> None:
        """The real link's `publish`; and a `closed` frame -- the one `Session.close`
        publishes as the return is recorded -- kept as the service's `closed`, since the
        same pass drops the session and every frame after it is idle (the b3a-2 final
        review, I2). Kept here rather than in `Service._end`, which is welfare-critical and
        unchanged, and without a reference to the session, which `_end` collects."""
        self._link.publish(frame)
        if frame.phase == "closed":
            self._service.closed = frame

    @property
    def refused(self):
        return self._link.refused

    @property
    def refused_dropped(self) -> int:
        return self._link.refused_dropped

    def drain(self) -> list:
        """At a trial boundary, or a paused run's housekeeping pass: the commands a run
        takes, with the service's own taken out."""
        service, kept = self._service, []
        for command in self._link.drain():
            if isinstance(command, _link.EndSession) and service._ending is None:
                why = service._unended(command)
                if why is not None:
                    service.session.refuse(command.KIND, command.by, why)
                    continue
                service._ending = command
                kept.append(_link.Stop(by=command.by))
            elif isinstance(command, _ANY_PHASE):
                # A new color is the service's in any phase, a run's never (the console settings
                # build's Task 8): saved as its set's proposed file at this boundary, between trials.
                service._define_color(command)
            elif isinstance(command, _SERVICE_COMMANDS):
                service.session.refuse(
                    command.KIND,
                    command.by,
                    "a run is in progress, so this is refused rather than kept for later; "
                    "send it again once the run has ended",
                )
            else:
                kept.append(command)
        return kept


class Service:
    """`wlx taskd`'s state and loop: the link, the open session if any, the stranded
    sessions, and the question and refusals an idle frame carries.

    **A demo service** (`demo_service`; `wlx taskd --demo`): every open a demo, on the
    simulators, which it is refused anything but. **A rig service's demo folder** (`demo_root`;
    `--demo-root`): where a demo opened here is written, never `root`, neither one holding the
    other. `pace_clock` and `pace_sleep` are each demo run's `pointer.Pace`'s, the wall clock a
    demo's frames wait on, so a test injects both and never sleeps (demo mode §3.5)."""

    def __init__(
        self,
        *,
        rig: Rig,
        rig_path: str,
        subjects: Path,
        tasks: Path,
        allocation: Allocation,
        allocation_path: str,
        root: Path,
        link,
        card: Callable[[], object] = SimulatedCard,
        pump: Callable[[], object] = SimulatedPump,
        seed: Callable[[], int] = _fresh_seed,
        wall_clock: Callable[[], float] | None = None,
        demo_service: bool = False,
        demo_root: Path | None = None,
        pace_clock: Callable[[], float] = time.perf_counter,
        pace_sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        missing = [
            name for name in FRAMEWORK_CODES if name not in allocation.task_events.values()
        ]
        if missing:
            raise SystemExit(
                f"refused: the allocation "
                f"{allocation_path or '(none given, so the provisional one)'} has no "
                f"{', '.join(missing)} event code; every session wlx taskd runs strobes "
                f"each, so give --allocation with them all"
            )
        if demo_service and (card is not SimulatedCard or pump is not SimulatedPump):
            # Demo mode §3.2: "the day it gains a real one, `--demo` refuses it".
            raise SystemExit(
                "refused: a demo service's card and pump are the simulators, always (demo mode "
                "§3.2): its rewards are counted and never delivered, and its event codes go to no "
                "sync box, and it was given another"
            )
        if demo_service and demo_root is not None:
            raise SystemExit(
                "refused: --demo-root is a rig service's; a demo service's sessions go to its own "
                "folder, so it takes none"
            )
        if demo_root is not None and (_within(demo_root, root) or _within(root, demo_root)):
            # The PI, 2026-11-14 ("A demo folder of its own"): a demo is kept apart from the real
            # sessions by where it is written, so their two folders never share one.
            raise SystemExit(
                f"refused: --demo-root {_printable(str(demo_root))} and --root "
                f"{_printable(str(root))} are one folder, or one holds the other, and a demo is "
                f"kept apart from the real sessions by where it is written; name a folder of its "
                f"own"
            )
        self.rig, self.rig_path = rig, rig_path
        self.subjects, self.tasks, self.root = Path(subjects), Path(tasks), Path(root)
        #: Whether this is a demo service (`wlx taskd --demo`), and a rig service's demo folder,
        #: or `None` for a rig that opens no demo.
        self.demo_service = demo_service
        self.demo_root = None if demo_root is None else Path(demo_root)
        self._pace_clock, self._pace_sleep = pace_clock, pace_sleep
        self.allocation, self.allocation_path = allocation, allocation_path
        #: The rig's color calibration (engine spec §7.1, §7.6), loaded once, here -- or **the
        #: default, the sRGB standard, in the place of a calibration the rig names that will not
        #: load**, a record or a field that is no record's path, `calibration_refused` saying why
        #: (the PI, 2026-10-11, XC-352's E1: "fall back to the default with a warning";
        #: `warnlist.of_unloaded`, which an open asks to accept), as `wlx run` and `wlx check`
        #: fall back (`cli._calibration_or_default`). **Which never stops `wlx taskd`** (the
        #: engine B plan, call 19): a stranded session's return is taken only through a running
        #: service.
        self.calibration: Calibration = SRGB
        self.calibration_refused = ""
        try:
            self.calibration = _load_calibration(rig, rig_path)
        except (SystemExit, Exception) as refused:  # noqa: BLE001 -- see the comment above
            self.calibration_refused = (
                _sentence(refused)
                if isinstance(refused, SystemExit)
                else f"refused: the calibration {rig_path} names would not load: "
                f"{type(refused).__name__}: {refused}"
            )
        self.link = link
        self._card, self._pump, self._seed = card, pump, seed
        #: Injected by a test; otherwise the service's own anchored wall.
        self.wall_clock = wall_clock
        self._clock = SessionClock()
        self.session: Session | None = None
        #: The stranded sessions under `--root`, each demo's among them offered only *end*, and
        #: after them each real one in the demo folder (`stranded_astray`).
        self.stranded: list = _demos_marked(_stranded.find(self.root), self.root)
        #: **The stranded demos in this rig's demo folder** (`--demo-root`), each offered only
        #: *end*: kept apart from `stranded`, which `_open` refuses every open on, so a crashed
        #: demo never holds up a real animal's open (the PI, 2026-11-14). It holds up another demo
        #: (`_session_for`), as the stranded rule does within a demo's own folder (demo mode §3.2).
        #: **And the real sessions stranded there** (`_demo_folder_split`; the whole-build review's
        #: I1): each is in `stranded` too, so it holds up every open as any stranded session does,
        #: is published as an animal's, and is resumed or ended in its own folder (`_astray`).
        self.stranded_demos: list = []
        self.stranded_astray: list = []
        if self.demo_root is not None:
            self.stranded_demos, self.stranded_astray = _demo_folder_split(
                _stranded.find(self.demo_root), self.demo_root)
            self.stranded.extend(self.stranded_astray)
        #: A departure, or a stranded session's return, a console owes an answer on:
        #: kept until it is answered or another replaces it (`_unasked`).
        self.question: _link.Question | None = None
        #: What a departure's `question` was posed for -- the animal, deployment and
        #: setup of its open (fix round 1 of Task 7). **Set whenever a departure question
        #: is posed, and read only beside one** (`_open`), so it is never cleared; a
        #: stranded return's question is bound by its session alone.
        self._posed_for: tuple = ()
        #: The service's own refusals while no session is open, capped as a session's.
        self.refusals: list = []
        self.refusals_dropped = 0
        #: **What the service did itself while no session is open** (`Idle.controls`; the console
        #: settings build's Task 8): a new color saved, and how the panel shows its set, for the
        #: changes feed; the last `link.CONTROL_HISTORY`, cleared as a session opens.
        self.controls: list = []
        #: **The last closed session's final frame** (the b3a-2 final review, I2; spec
        #: §6.2: "The session then closes and the page shows its summary"), for the idle
        #: frames until the next session opens (`Idle.closed`). Set as the session
        #: publishes its `closed` frame (`_Routed.publish`), cleared as the next opens
        #: (`_route`).
        self.closed: _link.Telemetry | None = None
        #: The service's runs (the b3a-1 plan, decision 18): a run `_start` accepted
        #: this pass and not started, `(RunSpec, rows, by, accepted)` with `by` an `Actor`
        #: and `accepted` the warnings its start accepted; and an `EndSession` that arrived
        #: during a run (`_Routed`), finished once the run returns (`step`).
        self._starting = None
        self._ending = None
        #: The idle frame's warnings and the calendar day they were listed on (the engine B
        #: plan, call 27), or `None` before the first idle frame.
        self._idle_listed: tuple | None = None

    def wall_now(self) -> float:
        """The service's wall: a test's, or its own `SessionClock`, anchored once."""
        return self.wall_clock() if self.wall_clock is not None else self._clock.now()

    def _today(self) -> date:
        """The service's calendar day, on its own wall: what a calibration's age counts to.
        **This host's local date**, in the zone `wlx taskd` runs in (`date.fromtimestamp`): a
        record's `measured_on` is a date with no zone, written on the rig's own calendar, so
        its age and whether it is dated after today are counted on that calendar, never UTC's
        -- a calibration turns 31 days old at the rig's local midnight."""
        return date.fromtimestamp(self.wall_now())

    def calibration_warnings(self) -> list:
        """The rig's calibration on the warnings list (engine spec §7.1, §7.10): the default,
        a measured one's age past 30 days, one dated after today -- and, while the record the
        rig names will not load, that the default runs in its place, first (XC-352's E1), the
        default's own sentence saying why it stands in (the warnings-over-refusals review's M4)."""
        refused = self.calibration_refused
        unloaded = warnlist.of_unloaded(refused) if refused else []
        return unloaded + warnlist.of_calibration(self.calibration, self._today(),
                                                  unloaded=bool(refused))

    def open_warnings(self, deployment: Deployment) -> list:
        """The warnings an open lists (engine spec §19.3: "at open"): the rig's calibration's,
        and a chaired session's free head -- known before any run."""
        return self.calibration_warnings() + warnlist.of_deployment(deployment)

    def _idle_warnings(self) -> tuple:
        """What an idle frame lists, unaccepted: every warning an open can ask for, a chaired
        session's included (`open_warnings`), which the dialog marks as a chaired session's.
        **Listed once per calendar day of the service's wall** (the engine B plan, call 27),
        not on every pass; and a fault listing them is one row saying so, never the end of
        publishing -- an open lists them again itself. Only a listing that succeeds is kept for
        the day: while it faults it is tried again at every pass, so the row goes once it lists.
        The fault is said through `_fault`, so one whose own `str()` raises is said by its type.
        Each row is cut for the frame (`link.WarningRow.of`): a record that will not load is
        quoted, and a fault says anything."""
        try:
            today = self._today()
            if self._idle_listed is not None and self._idle_listed[0] == today:
                return self._idle_listed[1]
            rows = tuple(
                _link.WarningRow.of(entry.code, entry.detail, entry.accepted_in, None, None)
                for entry in self.open_warnings(Deployment.RIG_CHAIRED)
            )
        except Exception as broken:  # noqa: BLE001 -- see the docstring
            return (_link.WarningRow.of(
                warnlist.UNLISTED,
                f"listing the warnings an open asks to accept raised {_fault(broken)}; an open "
                f"lists them again itself",
                (), None, None,
            ),)
        self._idle_listed = (today, rows)
        return rows

    # --- the loop -----------------------------------------------------------------

    def serve(self, stop: threading.Event) -> None:
        """Pass after pass until `stop` is set: `wlx taskd`'s loop, and the one thread
        every mark is taken on. `stop` is read between passes."""
        while not stop.is_set():
            self.step()

    def step(self) -> None:
        """One housekeeping pass: wait for a console (up to `HOUSEKEEPING_S`), stamp a
        mark, take every command waiting, publish one frame -- and then run a run
        accepted in this pass, finishing an `EndSession` that arrived during it."""
        mark = self.link.idle(HOUSEKEEPING_S)
        if mark:
            self._mark(mark)
        for command in self.link.drain():
            self._route(command)
        self.publish()
        if self._starting is None:
            return
        run, rows, by, accepted = self._starting
        self._starting = None
        self._run(run, rows, by, accepted)
        if self._ending is not None:
            ending, self._ending = self._ending, None
            self._end(ending)
        self.publish()

    def publish(self) -> None:
        """The open session's frame, or an idle one."""
        if self.session is not None:
            self.session.offered_tasks = self._tasks()
            self.session.publish()
            return
        self.link.publish(
            _link.Idle.of(
                wall_at=self.wall_now(),
                # A stranded demo in this rig's demo folder says so (XC-504): it holds up only
                # another demo's open, and a page keeps *new session* live beside it.
                stranded=(*self.stranded, *(dataclasses.replace(found, demo_folder=True)
                                            for found in self.stranded_demos)),
                question=self.question,
                refusals=self.refusals,
                refusals_dropped=self.refusals_dropped,
                link=self.link,
                animals=self._animals(),
                offered_tasks=self._tasks(),
                closed=self.closed,
                warnings=self._idle_warnings(),
                controls=self.controls,
                # Schema 21 (demo mode §3.7): whether this is a demo service, and whether a demo
                # can open here -- a gaze endpoint, and on a rig service a demo folder of its own.
                demo=self.demo_service,
                gaze=self.link.gaze_endpoint is not None
                and (self.demo_service or self.demo_root is not None),
            )
        )

    def shutdown(self, why: str = "wlx taskd stopped with the session open") -> None:
        """The process is stopping -- Ctrl-C at `wlx taskd`'s terminal, or a fault out of
        its loop (`run`) -- so a session still open is recorded as ended without its
        return, saying `why`, and its clock closed. The next start finds it stranded
        (`stranded.find`), which is what makes it safe to stop rather than wait."""
        session, self.session = self.session, None
        if session is None:
            return
        if (
            session.welfare.left_cage_wall_at is not None
            and session.welfare.returned_wall_at is None
        ):
            session.return_not_recorded(why, how="wlx taskd")
        if session.opened_wall_at is not None and session.ended_wall_at is None:
            session.end(how="wlx taskd")

    # --- commands -----------------------------------------------------------------

    def _route(self, command) -> None:
        if isinstance(command, _link.OpenSession):
            if self.demo_service:
                # **Every open in a demo service is a demo** (demo mode §3.1; the plan's call: one
                # path), whatever the page sent, so `_open`'s demo path takes each.
                command = dataclasses.replace(command, demo=True)
            idle = self.session is None
            self._open(command)
            if idle and self.session is not None:
                # **The idle feed starts afresh with each session** (the b3a-1 final
                # review, Minor 7): its refusals were about the time before this one --
                # "send it again answering confirm" among them -- and shown again once
                # the session closed, they would read as pending. While it is open,
                # refusals go to its own feed (`_refuse`). **And the End tab's summary is
                # replaced by this session's** (the b3a-2 final review, I2).
                self.refusals.clear()
                self.refusals_dropped = 0
                self.controls.clear()
                self.closed = None
        elif isinstance(command, _link.EndSession):
            if self.session is None and self._demo_stranded(command.session_id) is not None:
                self._end_stranded_demo(command)
            elif self.session is None and self._astray(command.session_id) is not None:
                self._in_its_folder(command, lambda: self._end(command))
            else:
                self._end(command)
        elif isinstance(command, _link.CheckRun):
            self._check(command)
        elif isinstance(command, _link.StartRun):
            self._start(command)
        elif isinstance(command, _link.ResumeSession):
            idle = self.session is None
            if idle and self._astray(command.session_id) is not None:
                self._in_its_folder(command, lambda: self._resume(command))
            else:
                self._resume(command)
            if idle and self.session is not None:
                # As for an open: the idle feed and the last summary were about before.
                self.refusals.clear()
                self.refusals_dropped = 0
                self.controls.clear()
                self.closed = None
        elif isinstance(command, _link.DefineColor):
            self._define_color(command)
        elif self.session is not None:
            self.session.receive(command)
        elif isinstance(command, _link.ManualReward):
            # Spec §6.0: with no session open the button flushes the line, counted to no
            # animal -- a slice of its own (XC-158). Until then, refused as a reward.
            self._refuse(
                "reward",
                command.by,
                "no session is open, so no reward was given: a reward with no session "
                "open, which flushes the line, waits on XC-158",
            )
        else:
            self._refuse(
                command.name if isinstance(command, _link.SetParameter) else command.KIND,
                command.by,
                "no session is open, so a command for a run is not applied; open a "
                "session first",
            )

    def _define_color(self, command: _link.DefineColor) -> None:
        """**A new color saved as its set's proposed file** (`link.DefineColor`; the console settings
        design's §6; its plan's Task 8; the PI, 2026-11-16: "Saved into a color set file", and for
        this plan "Proposed file first"), in any phase, the service's and never a run's.

        It reads `<--tasks>/../stimuli/<set>.json` -- or the proposal already made of it,
        `stimuli/proposed/<set>.json`, which it extends -- defines the color by its method in that
        set's frame (`colordef.chromaticity`), and writes the set's whole file with the color added
        (`colordef.proposal`) to `stimuli/proposed/<set>.json`, atomically (a temporary file beside
        it, then `os.replace`). **Never the set's own file** (the planner's call, COL-38): XC-150's
        pull is not built, so a file in the checkout is read at the next load whether committed or
        not, and a rig would use a color the PI had not reviewed; he commits it by moving it into
        `stimuli/`. **A new set** (`new_set`) takes `colordef.new_set`'s apex, luminance and, by
        hue angle, its design.

        **Refused, writing nothing**, with the sentence on the feed: a `--tasks` with no `stimuli`
        folder beside it, as wl-xtasks has; a set that is missing, unless new, or that exists, if
        new; a set's name no file can have; and whatever the definition or the proposal refuses (a
        name the set has, a number no color has). **Then said on the changes feed** -- the open
        session's (`Session.say`), or the idle frame's (`controls`): where it was saved, and, as a
        `warning`, how the session's panel shows the set with it, or with no session open the
        rig's (the default where it names none): "adding it desaturates isohue by N% on
        calibration X" (`photometry.realize`). Between trials or between runs, never in a frame."""
        from wl_xcon import colordef
        from wl_xcon.photometry import ColorSet, realize

        by, kind = command.by, command.KIND
        stimuli = self.tasks.parent / "stimuli"
        if not stimuli.is_dir():
            self._refuse(kind, by, (
                f"--tasks {self.tasks} has no stimuli folder beside it, as wl-xtasks has, so "
                f"there is no color set to add {command.name!r} to; nothing was written"))
            return
        try:
            named = colordef.set_name(command.colorset)
        except ValueError as refused:
            self._refuse(kind, by, f"{refused}; nothing was written")
            return
        own, proposed = stimuli / f"{named}.json", stimuli / "proposed" / f"{named}.json"
        if command.new_set and own.exists():
            self._refuse(kind, by, (
                f"color set {named!r} exists already ({own}); a new set takes a name no set has, "
                f"so {command.name!r} was not saved"))
            return
        if not command.new_set and not own.is_file():
            self._refuse(kind, by, (
                f"there is no color set {named!r} under {stimuli}; a color goes into a set that is "
                f"there, or a new one, so {command.name!r} was not saved"))
            return
        numbers = dict(command.numbers)
        try:
            if proposed.is_file():
                within = colordef.frame(ColorSet.load(proposed))
            elif command.new_set:
                within = colordef.new_set(named, command.method, numbers)
            else:
                within = colordef.frame(ColorSet.load(own))
            xy = colordef.chromaticity(within, command.method, numbers)
            data = colordef.proposal(
                within, command.name, xy, method=command.method, numbers=numbers, by=by,
                rig=Path(self.rig_path).stem or "this rig",
                on=date.fromtimestamp(self.wall_now()).isoformat())
            added = ColorSet(**data)
        except (ValueError, OSError) as refused:
            self._refuse(kind, by, f"{command.name!r} was not saved: {refused}")
            return
        try:
            proposed.parent.mkdir(exist_ok=True)
            handle, temporary = tempfile.mkstemp(dir=proposed.parent, prefix=f".{named}.",
                                                 suffix=".json")
            try:
                with os.fdopen(handle, "w", encoding="utf-8") as file:
                    file.write(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
                    file.flush()
                    os.fsync(file.fileno())
                os.replace(temporary, proposed)
            except BaseException:
                Path(temporary).unlink(missing_ok=True)
                raise
        except OSError as failed:
            self._refuse(kind, by, f"{command.name!r} was not saved: {proposed} could not be "
                                   f"written ({failed})")
            return
        x, y = added.colors[command.name]
        shown = f"{self.tasks.parent.name}/stimuli/proposed/{named}.json"
        said = [(kind, (
            f"{command.name} ({colordef.SAID[command.method]}: "
            f"{colordef.numbers_words(command.method, numbers)}) at x {x:.5f}, y {y:.5f} saved "
            f"to {shown} for the PI to review and commit; a rig uses it once committed and "
            f"pulled"))]
        calibration = self.calibration if self.session is None else self.session.spec.calibration
        panel = calibration.id or calibration.measured_on
        try:
            before = 0.0 if not within.colors else realize(ColorSet(
                name=within.name, colors=within.colors, apex=within.apex,
                luminance_cd_m2=within.luminance_cd_m2), calibration).desaturation
            after = realize(added, calibration).desaturation
        except ValueError as unshown:
            said.append(("warning", f"adding {command.name} to {named}: {unshown}"))
        else:
            if after > before + colordef.DESATURATED:
                was = f", where without it the set gives up {100 * before:.1f}%" if before else ""
                said.append(("warning", (
                    f"adding {command.name} desaturates {named} by {100 * after:.1f}% on "
                    f"calibration {panel}{was}: every color of the set gives up that share of its "
                    f"distance from the apex so all fit, their luminance held")))
        for row_kind, sentence in said:
            if self.session is not None:
                self.session.say(row_kind, by, sentence)
            else:
                self.controls.append(_link.Control(kind=row_kind, by=by, at=self.wall_now(),
                                                   said=sentence))
                del self.controls[: -_link.CONTROL_HISTORY]

    def _refuse(self, name: str, by: Actor | None, why: str) -> None:
        """Onto the open session's feed, or, with none open, the idle frame's."""
        if self.session is not None:
            self.session.refuse(name, by, why)
            return
        self.refusals.append(_link.Refused(name=name, by=by, why=why))
        if len(self.refusals) > _link.REFUSAL_HISTORY:
            self.refusals_dropped += len(self.refusals) - _link.REFUSAL_HISTORY
            del self.refusals[: -_link.REFUSAL_HISTORY]

    def _demo_stranded(self, session_id: str | None):
        """The stranded demo in this rig's demo folder that `session_id` names, or `None`."""
        return next((found for found in self.stranded_demos if found.session_id == session_id),
                    None)

    def _astray(self, session_id: str | None):
        """The real session stranded in this rig's demo folder that `session_id` names
        (`stranded_astray`), or `None`."""
        return next((found for found in self.stranded_astray if found.session_id == session_id),
                    None)

    def _in_its_folder(self, command, act: Callable[[], None]) -> None:
        """**A real session stranded in the demo folder, resumed or ended where it is**
        (`_route`, with no session open; the whole-build review's I1): `act` -- `_resume`, or
        `_end` and so `_close_stranded`, each by its own rules -- taken with `root` the demo
        folder's (`_in_demo_root`) and `stranded` as it is, which holds it, so its record is read
        and written in its own folder and its entry leaves `stranded` as any one's does. **Refused,
        doing nothing, when a session under `--root` has the same id**, as a demo's End is
        (`_end_stranded_demo`)."""
        found = self._astray(command.session_id)
        if (self.root / command.session_id).exists():
            self._refuse(
                command.KIND, command.by,
                f"session {command.session_id} of {found.subject or 'an unreadable record'} is "
                f"stranded in the demo folder ({self.demo_root}), and a session under --root "
                f"({self.root}) has the same id, so a command naming it could be read as either; "
                f"nothing was done. Move one of the two folders by hand, then restart wlx taskd",
            )
            return
        try:
            self._in_demo_root(act, self.stranded)
        finally:
            # As `act` left it in `stranded`, which only it has the id in: gone once resumed or
            # its return recorded, or marked not resumable in its place (`_resume`).
            now = next((entry for entry in self.stranded
                        if entry.session_id == found.session_id), None)
            at = next(i for i, entry in enumerate(self.stranded_astray) if entry is found)
            if now is None:
                del self.stranded_astray[at]
            else:
                self.stranded_astray[at] = now

    def _end_stranded_demo(self, command: _link.EndSession) -> None:
        """**A stranded demo's End, in this rig's demo folder** (`_route`, with no session open):
        **refused, ending nothing, when a session under `--root` has the same id**, stranded or
        not, so an End can never reach a real animal's record through the demo folder's path,
        nor be read as meaning the other; otherwise taken against the demo folder
        (`_in_demo_root`). The service never gives two folders one id (`_session_for`), so only a
        folder copied or renamed by hand meets the refusal, which says how to undo it."""
        if (self.root / command.session_id).exists():
            self._refuse(
                "end", command.by,
                f"session {command.session_id} is a stranded demo in the demo folder "
                f"({self.demo_root}), and a session under --root ({self.root}) has the same id, so "
                f"an End naming it could be read as either; nothing was ended. Move the demo's "
                f"folder out of {self.demo_root} by hand, then restart wlx taskd",
            )
            return
        self._in_demo_root(lambda: self._end(command), self.stranded_demos)

    def _in_demo_root(self, act: Callable[[], None], stranded: list) -> None:
        """**`act` taken against this rig's demo folder**: `root` is its (`demo_root`) and
        `stranded` the list given while it runs, then `--root`'s again. So a stranded demo's
        return is taken by `_end` and `_close_stranded`, welfare-critical and **unchanged**, by
        the rules and the rows of any stranded session's, written into its own record in the
        demo folder; the question a far return poses stays the service's, for its session.
        Asked by `_end_stranded_demo` with `stranded_demos`, and by `_in_its_folder` with
        `stranded` itself, once no session under `--root` has the id.

        **Nothing else reads either meanwhile.** `wlx taskd` runs one Python thread, the one
        running `serve`, which takes every command and every mark and publishes each frame, one
        after another (`step`); the link is sockets read on that thread, with no thread of its
        own; `wlx serve` and its threads are another process. A Ctrl-C between the two restores
        can leave `stranded` the demo folder's, and its handler (`run`) reads neither before
        `wlx taskd` exits: `shutdown` reads only the open session, and none is open here."""
        root, kept = self.root, self.stranded
        self.root, self.stranded = self.demo_root, stranded
        try:
            act()
        finally:
            self.root, self.stranded = root, kept

    def _mark(self, mark: int) -> None:
        """A mark signal with no run checking for one: stamped into the open session, or
        refused while idle, since it belongs to no session (the b3a-1 plan, decision 16)."""
        if self.session is not None:
            self.session.stamp(mark)
        else:
            self._refuse("mark", None, "no session is open, so the mark was not recorded")

    def _animals(self) -> tuple[str, ...]:
        """The animals a session may be opened for: folders under `--subjects` holding a
        bounded config, **named as an open accepts** (`_folder_name`; fix round 1 of Task
        7), so the idle frame never offers an animal every open would refuse."""
        if not self.subjects.is_dir():
            return ()
        return tuple(
            sorted(
                p.name
                for p in self.subjects.iterdir()
                if _folder_name(p.name) and (p / "bounds.py").is_file()
            )
        )

    def _tasks(self) -> tuple[str, ...]:
        """The task files a run may use: `*.py` under `--tasks`, **named as a run
        accepts** (`_folder_name`, which also leaves out a `_`-prefixed module), so a
        frame never offers a task every run would refuse (`_task`)."""
        if not self.tasks.is_dir():
            return ()
        return tuple(sorted(p.name for p in self.tasks.glob("*.py") if _folder_name(p.name)))

    # --- opening --------------------------------------------------------------------

    def _session_for(self, command: _link.OpenSession, *, card: Callable[[], object] | None = None,
                     pump: Callable[[], object] | None = None, demo: bool = False) -> Session:
        """The session an `OpenSession` asks for, built and **not opened**: nothing is
        written. Raises `SystemExit`, `ValueError` or `Exceeded` with the sentence a
        refusal says. **Built on the card and the pump `card` and `pump` make**, the service's own
        when `None`; **a demo with `demo`** (demo mode; `_build`).

        **A command whose `demo` is set is refused unless `demo` is given** ("a demo opens only
        through Service._open's demo path"): `_open` decides a demo's apparatus and passes it here
        (demo mode §8, its second change), so a demo never becomes a live session by a path that
        did not. **A demo's session id is free in both of a rig's folders, and on a rig service no
        demo opens while one in its demo folder is stranded** (the stranded rule within a demo's
        own folder, demo mode §3.2); a real session's id is free in its demo folder too, so an End
        naming one names one session."""
        if command.demo and not demo:
            raise ValueError(
                "a demo opens only through Service._open's demo path, and this one did not come "
                "through it, so nothing was recorded"
            )
        for what, name in (("session id", command.session_id), ("animal", command.animal)):
            if not _folder_name(name):
                raise ValueError(
                    f"a {what} is one folder name -- letters, digits, '_', '.' and '-', "
                    f"starting with a letter or digit -- and {name!r} is not one"
                )
        # Asked for its refusal alone: a rig service's demo with no demo folder has nowhere to go.
        self._session_root(demo)
        if demo and not self.demo_service and self.stranded_demos:
            names = "; ".join(f"session {found.session_id}" for found in self.stranded_demos)
            raise ValueError(
                f"no demo opens while a demo's return is not recorded: {names}, in "
                f"{self.demo_root}. Record its return with End session, naming its session"
            )
        for folder in (self.root,) if self.demo_root is None else (self.root, self.demo_root):
            if (folder / command.session_id).exists():
                raise ValueError(
                    f"session id {command.session_id!r} is already used under {folder}; "
                    f"every session has its own"
                )
        session, _bounds = self._build(
            session_id=command.session_id, animal=command.animal,
            deployment=command.deployment, view=command.view,
            session_kind=command.session_kind,
            delivered_today=command.delivered_today,
            card=self._card if card is None else card,
            pump=self._pump if pump is None else pump,
            demo=demo,
        )
        return session

    def _session_root(self, demo: bool) -> Path:
        """**Where a session is written**: `--root`; a demo service's demo there too, its own
        folder's; and **a demo on a rig service in its demo folder** (`--demo-root`), never under
        `--root` (the PI, 2026-11-14, "A demo folder of its own"), refused with none."""
        if not demo or self.demo_service:
            return self.root
        if self.demo_root is None:
            raise ValueError(
                "this rig service names no --demo-root, so a demo has nowhere apart from the real "
                "sessions to go"
            )
        return self.demo_root

    def _build(
        self,
        *,
        session_id: str,
        animal: str,
        deployment: str,
        view: str,
        session_kind: str,
        delivered_today: float | None,
        card: Callable[[], object],
        pump: Callable[[], object],
        demo: bool,
    ) -> tuple[Session, Bounds]:
        """A session for `animal`, built from its files under `--subjects` and **not
        opened**: nothing is written. Returned with the bounds it loaded, which a resume
        compares with its record's (`_resume`). Raises `SystemExit`, `ValueError` or
        `Exceeded` with the sentence a refusal says. **On the card and the pump the factories
        `card` and `pump` make**, which the caller decides (`_session_for`, `_resume`).

        **A demo** (`demo`; demo mode §3.1-§3.7) is refused with no gaze endpoint, the link's
        fourth, since no page could steer it, and is written where `_session_root` says. **In
        direct view on a rig whose housings are unmeasured it takes the stand-ins**
        (`geometry.stand_in_housings`, §3.6), which its record and its drawing say; a session
        that is not a demo never does, and `Rig.direct` refuses it. Its spec carries what it is
        (`taskd.Demo`), and its worlds are the mouse's, made for each run (`_demo_worlds`).

        **The animal is held to `_folder_name` before any path is built** (XC-026): an
        open has already checked it (`_session_for`), and a resume's comes from a record
        -- `config.json`'s subject, which `wlx run --subject` took as any text before XC-161 and a
        hand-edited record can still make anything -- so a
        `../outside` or an absolute path never makes a `bounds.py` outside `--subjects`
        the code that runs, as `_close_stranded` refuses one."""
        if demo and self.link.gaze_endpoint is None:
            raise ValueError(
                "this rig service has no gaze endpoint, --link's fourth, so no page could steer a "
                "demo"
            )
        root = self._session_root(demo)
        if not _folder_name(animal):
            raise ValueError(
                f"an animal is one folder name -- letters, digits, '_', '.' and '-', "
                f"starting with a letter or digit -- and {animal!r} is not one"
            )
        folder = self.subjects / animal
        bounds_path = folder / "bounds.py"
        if not bounds_path.is_file():
            raise ValueError(f"there is no animal {animal!r}: {bounds_path} does not exist")
        bounds = _load_bounds(bounds_path)
        if bounds.subject != animal:
            raise ValueError(
                f"{bounds_path} holds {bounds.subject!r}'s bounded config, and this folder "
                f"is {animal!r}'s; ceilings belong to an animal"
            )
        settings_path, setup = None, []
        rig, stand_in = self.rig, False
        if view == "direct":
            if demo and not rig.housings:
                rig, stand_in = dataclasses.replace(
                    rig, housings=stand_in_housings(rig.panel_width_cm)), True
            geometry = rig.direct()
        else:
            # The animal's settings, or the nominal half-IPD with none; another animal's, or a
            # half-IPD outside the drawn optics, as given: each a warning its runs' pre-flights
            # list (the PI, 2026-10-11, XC-352's C6, C7 and C8; each refused here until then).
            found = folder / "settings.py"
            settings = _load_subject_settings(found) if found.is_file() else None
            settings_path = found if settings is not None else None
            half = NOMINAL_HALF_IPD_CM if settings is None else settings.half_ipd_cm
            setup = warnlist.of_setup(self.rig, animal, half, settings, found)
            geometry = self.rig.stereoscope(half)
        record = Demo(stand_in_housings=stand_in) if demo else None
        routed = _Routed(self.link, self)
        session = Session(
            SessionSpec(
                task="",
                allocation=self.allocation_path,
                root=root,
                session_id=session_id,
                subject=animal,
                trials=0,
                frame_period=FRAME_PERIOD,
                seed=0,
                values={},
                bounds=bounds,
                already_delivered_today=delivered_today,
                deployment=Deployment(deployment),
                geometry=geometry,
                session_kind=session_kind,
                calibration=self.calibration,
                bounds_config=str(bounds_path),
                rig_config=self.rig_path,
                subject_settings="" if settings_path is None else str(settings_path),
                setup_warnings=tuple(setup),
                demo=record,
            ),
            card=card(),
            pump=pump(),
            link=routed,
            service=True,
            wall_clock=self.wall_clock,
            run_world=None if record is None else self._demo_worlds(
                routed, rig, geometry, session_id, record),
        )
        return session, bounds

    def _demo_worlds(self, routed: _Routed, rig: Rig, geometry, session_id: str,
                     record: Demo) -> Callable[[RunSpec], Callable]:
        """**A demo session's worlds, made for each run** (`Session.run_world`; demo mode
        §3.3-§3.5, §3.9): `pointer.worlds` over the mouse, `pointer.Source` reading the page's
        pointer reports through the session's link (`routed.gaze_into`), its noise the record's
        drawn from the run's own seed (§14 item 16); a `pointer.Pace` at the session's frame
        period on this service's wall clock (`pace_clock`, `pace_sleep`); and a `pointer.Drawing`
        of the rig, the field (stand-ins and all) and the calibration, published through the
        session's link, as its frames are."""

        def run_world(run: RunSpec):
            source = pointer.Source(routed.gaze_into, seed=run.seed, noise_deg=record.noise_deg)
            pace = pointer.Pace(FRAME_PERIOD, clock=self._pace_clock, sleep=self._pace_sleep)
            drawing = pointer.Drawing(rig, geometry, self.calibration, session_id=session_id,
                                      stand_in=record.stand_in_housings)
            return pointer.worlds(source, pace=pace, drawing=drawing, publish=routed.publish)

        return run_world

    def _built(self, kind: str, by: Actor, build: Callable[[], _Built]) -> _Built | None:
        """What `build` returns -- a session built and not opened, for an open or a
        resume -- or `None`, refused under `kind`, saying why: a `SystemExit`,
        `ValueError`, `TypeError` or `Exceeded` with its own sentence, and anything else
        named, since the animal's files are code and a broken one is never the
        service's end. **The one handler `_open` and `_resume` share** (review fix
        round 1 of XC-026 Task 4), so the two cannot drift. Either one whose own `str()`
        raises is said by its type (`_sentence_or`, `_said`; XC-291), so saying it does not
        stop `wlx taskd`, within `_said`'s limits."""
        failing = "the session could not be built"
        try:
            return build()
        except (SystemExit, ValueError, TypeError, Exceeded) as refused:
            self._refuse(kind, by, _sentence_or(refused, failing))
        except Exception as broken:  # noqa: BLE001 -- the animal's files are code
            self._refuse(kind, by, f"{failing}: {_said(broken)}")
        return None

    def _open(self, command: _link.OpenSession) -> None:
        """**Welfare-critical.** Open a session (P4d-2b spec §6.2): **none while one is
        open, and none for any animal while one is stranded** (§6.1); an answer taken
        only for the question posed (`_unasked`); then the departure through `marks`,
        the terminal's own rules; and **nothing written until it is accepted**, so a
        refused or unanswered departure leaves no folder and its id free (the b3a-1
        plan, decision 11). A far departure with no answer puts the question on the idle
        frame, with a refusal row saying what to send.

        **And its warnings** (engine build B): those the session's kind accepts, accepted on
        the form by their sentences, or the open is refused before anything is marked; since
        XC-352's E1 and E2 (the PI, 2026-10-11) a calibration that will not load, or is dated after
        today, is one of them, accepted in every kind. If the
        warnings cannot be listed, the open goes ahead with none offered, says so on the
        session's feed, and no run starts until they can be (call 31). Each accepted one is
        written once the service holds the session."""
        if self.session is not None:
            self._refuse(
                "open",
                command.by,
                f"a session is open for {self.session.spec.subject!r} "
                f"({self.session.spec.session_id}); end it, with its animal's return, "
                f"before another opens",
            )
            return
        if self.stranded:
            names = "; ".join(
                f"{found.subject or 'an unreadable record'} in session {found.session_id}"
                for found in self.stranded
            )
            self._refuse(
                "open",
                command.by,
                f"no session opens while an animal's return is not recorded: {names}. "
                f"Resume it, or record its return with End session, naming its session",
            )
            return
        # **A demo is for the test monkey alone** (demo mode §8, change 1; the PI, 2026-11-07,
        # "Approve both and the design"): refused before anything is written.
        if command.demo and command.animal != "REFERENCE":
            self._refuse(
                "open",
                command.by,
                "a demo is for the test monkey, REFERENCE, alone: nothing simulated may enter "
                "another animal's records. Nothing was recorded",
            )
            return
        # What a departure's question is posed for, beside its session and instant (fix
        # round 1 of Task 7): the animal its warning names, the deployment and the setup.
        asked_about = (command.animal, command.deployment, command.view)
        if command.answer is not None:
            unasked = _unasked(
                self.question, "departure", command.session_id, command.departure,
                posed_for=self._posed_for, sent_for=asked_about,
            )
            if unasked is not None:
                self._refuse("open", command.by, unasked)
                return
        # **A demo on the simulated card and pump, whatever this service was built with** (demo
        # mode §8, change 2; the same approval), and on an unmeasured rig the stand-in field,
        # which `demo=True` gives it in `_build`.
        if command.demo:
            session = self._built("open", command.by, lambda: self._session_for(
                command, card=SimulatedCard, pump=SimulatedPump, demo=True))
        else:
            session = self._built("open", command.by, lambda: self._session_for(command))
        if session is None:
            return
        # **The warnings this open asks to accept** (engine spec §19.3: "Accepted once per
        # session, at open, recorded"): those the session's kind accepts, each by its code and
        # its sentence (the engine B plan, calls 7 and 25), refused before anything is marked
        # or written, as a refused departure is. One no kind accepts is not offered and never
        # refuses an open; since XC-352's E1 and E2 (2026-10-11) none is. This is the open's
        # only new refusal.
        try:
            listed, unlisted = self.open_warnings(Deployment(command.deployment)), None
        except Exception as broken:  # noqa: BLE001 -- the engine B plan, call 31
            # A fault listing them never refuses an open (call 31): nothing is offered, the
            # fault is said on the session's feed once it opens, and every run's pre-flight
            # fails on the same listing until it lists (`_preflight`). Said through `_fault`,
            # so one whose own `str()` raises is said by its type and the open still goes ahead.
            listed, unlisted = [], _fault(broken)
        offered = [entry for entry in listed if command.session_kind in entry.accepted_in]
        unaccepted = warnlist.owed(offered, set(command.accepted))
        if unaccepted:
            self._refuse(
                "open", command.by,
                f"a session opens once its warnings are accepted, and these are not, as they "
                f"read now: {warnlist.sentence(unaccepted)}. Nothing was recorded: send it "
                f"again accepting them",
            )
            return
        try:
            decision = _marks.page_departure(
                session,
                departure=command.departure,
                answer=command.answer,
                amend_to=command.amend_to,
                amend_reason=command.amend_reason,
                by=command.by,
            )
            _marks.depart(session, decision)
        except _marks.Owed as owed:
            self.question = _link.Question(
                mark="departure",
                session_id=command.session_id,
                at=owed.at,
                said=owed.warning,
                answers=owed.answers,
            )
            self._posed_for = asked_about
            self._refuse(
                "open",
                command.by,
                f"{owed.warning}. Nothing was recorded: send it again answering "
                f"confirm, or amend with the corrected time, a reason and your name",
            )
            return
        except (argparse.ArgumentTypeError, Exceeded) as refused:
            self._refuse("open", command.by, str(refused))
            return
        # Marked: whatever was asked is answered, or moot now a session is open.
        self.question = None
        _marks.record_departure(session, decision)
        session.open(how="wlx taskd")
        if session.spec.deployment is Deployment.RIG_FIXED:
            session.head_fixed(session.wall_now())
        session.offered_tasks = self._tasks()
        self.session = session
        if unlisted is not None:
            self._refuse(
                "open", command.by,
                f"the warnings an open asks to accept could not be listed ({unlisted}); the "
                f"session opened with none accepted, and no run starts until they can be listed",
            )
        # Written once the service holds the session (the engine B plan, call 22). A fault
        # here is not caught, as `record_departure`, `open` and `head_fixed` above are not: it
        # reaches `wlx taskd`'s fault handler, which records a held session's return as not
        # recorded and its end, so the next start finds it stranded.
        session.accept(offered, by=command.by, how="open", run=None)

    def _resume(self, command: _link.ResumeSession) -> None:
        """**Not on the welfare-critical list** (the PI, 2026-10-02: "None of them"), though
        it restores the out-of-cage clock and the fluid; it was reviewed with XC-026's
        welfare summary. A stranded session
        resumed (XC-026 spec §5): refused, saying why, while a session is open, for an id
        not stranded, when its record cannot give what a resume needs or names two
        animals, when its animal's bounds changed since it opened, or when the animal is
        past its out-of-cage limit on the recorded departure -- each **before anything is
        written** (plan ruling 6). Otherwise built as `_open` builds one (`_build`), from
        its record (`resume.read`), and resumed (`Session.resume`). Another session still
        stranded is no bar: each is resumed or ended on its own (spec §5; plan ruling 7).
        **A record it cannot carry is a refusal, never the service's end** (the
        controller's ruling on Task 4): what `stranded.restore` raises is said too, and
        what `Session.resume` refuses before it writes. **One refused for being past its
        limit is then marked not resumable**, with the refusal's sentence, so the page
        offers only *end* (spec §5; fix round 1 of Task 7); a stranded session marked
        not resumable, by this or by `stranded.find`, is refused with what it is marked.
        **One resumed on another calibration, or another half-IPD, than its `config.json`
        names is a warning asked at its first run**, naming both, never a refusal.

        **A demo is never resumed, only ended** (demo mode §8, Review Focus 7): one in this rig's
        demo folder, or any whose `config.json` carries `demo` (`Restoration.demo`), is refused
        and marked so (`DEMO_UNRESUMED`), as `Service` marks each as it finds it, so a crashed demo
        never comes back as a live session."""
        if self.session is not None:
            self._refuse(command.KIND, command.by,
                         f"a session is open ({self.session.spec.session_id}); a stranded "
                         f"session is resumed only while none is")
            return
        found = next((s for s in (*self.stranded, *self.stranded_demos)
                      if s.session_id == command.session_id), None)
        if found is None or found.left_at is None:
            self._refuse(command.KIND, command.by,
                         f"no stranded session {command.session_id!r} can be resumed"
                         + ("" if found is None else f": {found.why}"))
            return
        if not found.resumable:
            # What the banner says of it, so the page and the refusal agree: its record
            # cannot carry a resume (`stranded.find`), or its animal is past its limit
            # (below). Neither is taken back while this service runs.
            self._refuse(command.KIND, command.by, found.why)
            return
        directory = self.root / found.session_id / XCON_DIRNAME
        try:
            restoration = _resume_mod.read(directory, found.left_at)
        except _resume_mod.Unresumable as refused:
            # `_sentence`, not `_sentence_or`: `resume.read` raises an `Unresumable` carrying a
            # plain `str` it built itself, which says itself without raising.
            self._refuse(command.KIND, command.by, _sentence(refused))
            return
        if restoration.demo:
            # Marked as `Service` marks each stranded demo it finds, so its banner offers only end.
            self.stranded[self.stranded.index(found)] = dataclasses.replace(
                found, resumable=False, why=DEMO_UNRESUMED
            )
            self._refuse(command.KIND, command.by, DEMO_UNRESUMED)
            return
        if restoration.subject != found.subject:
            # `_build` loads bounds for `config.json`'s animal, and `stranded.restore`
            # holds them to the departure row's: one record, so one animal.
            self._refuse(command.KIND, command.by,
                         f"session {found.session_id}'s config.json names "
                         f"{restoration.subject!r} and its departure names {found.subject!r}; "
                         f"a record that disagrees with itself is not resumed, so end it instead")
            return
        built = self._built(command.KIND, command.by, lambda: self._build(
            session_id=found.session_id, animal=restoration.subject,
            deployment=restoration.deployment, view=restoration.view,
            session_kind=restoration.session_kind,
            delivered_today=restoration.already_today,
            card=self._card, pump=self._pump, demo=False,
        ))
        if built is None:
            return
        session, bounds = built
        now_bounds = bounds_record(bounds)
        changed = sorted(
            name
            for kind in ("ceilings", "minima")
            for name in set(restoration.bounds_at_open[kind]) | set(now_bounds[kind])
            if restoration.bounds_at_open[kind].get(name) != now_bounds[kind].get(name)
        )
        if changed:
            self._refuse(command.KIND, command.by,
                         f"{restoration.subject!r}'s bounds changed since session "
                         f"{found.session_id} opened ({', '.join(changed)}); a session's "
                         f"limits do not change across a restart, so end it instead")
            return
        try:
            # **Against the limit the session had** (the final review's I2): one it lowered
            # is the one `Session.resume` restores, so it is the one this check reads, set
            # through `Bounds.set` on a copy, which holds it under the file's maximum.
            limits = dataclasses.replace(bounds, ceilings=dict(bounds.ceilings))
            if OUT_OF_CAGE in restoration.bounded:
                limits.set(OUT_OF_CAGE, restoration.bounded[OUT_OF_CAGE], by=command.by)
            stop = _stranded.restore(found, limits, directory, self.wall_now).welfare.must_stop(
                self.wall_now()
            )
        except (Exceeded, TypeError, ValueError) as refused:
            # A start row's `out_of_cage` that is no number raises from `Bounds.set`,
            # as `Session.resume`'s own call below is caught: a refusal, never the end
            # of the service. Not coerced in `resume.read`: `float("0.05")` would accept
            # damage that is refused today. Through `_sentence_or` (XC-291's review, M3): the
            # bounds are the animal's `bounds.py`'s, whose own subclass can raise anything.
            self._refuse(command.KIND, command.by, _sentence_or(refused, _UNRESUMED))
            return
        if stop is not None:
            # **The page then asks for the return, and only end is offered** (spec §5;
            # fix round 1 of Task 7): the entry is marked so, with this sentence, and its
            # banner loses *resume session*. Past the limit only ever stays true, so the
            # mark is never wrong. Changed bounds stay a plain refusal: restoring the
            # animal's file makes the session resumable again.
            why = f"{stop}; record its return with End session instead"
            self.stranded[self.stranded.index(found)] = dataclasses.replace(
                found, resumable=False, why=why
            )
            self._refuse(command.KIND, command.by, why)
            return
        # **On another calibration than it opened on** (the warnings-over-refusals review's I2):
        # config.json names the one the session opened with, and this service may run another --
        # the default in the place of a record that no longer loads (XC-352's E1), or a new
        # record. A warning, never a refusal (the PI's rule of 2026-10-11), asked with the
        # resumed session's first run, naming both; each run's start row names the calibration
        # it ran against, and the `session resumed` row the one it now runs on.
        # It compares ids only, so a record measured again under the same id is not noticed (a
        # known limit of this warning).
        if restoration.calibration != session.spec.calibration.id:
            session.spec.setup_warnings += tuple(warnlist.of_changed_calibration(
                restoration.calibration, session.spec.calibration))
        # **On another half-IPD than it opened on** (Task 7's review, I1): its settings file may
        # have been removed, added or changed while `wlx taskd` was down, and `_build` reads the
        # file as it is now. The same warning, asked with its first run. A record with no
        # half-IPD (direct view) has nothing to compare, so adds none; one written before XC-352's
        # C6 has the half-IPD and no nominal flag, and `resume.read` reads it as opened from a file.
        geometry = session.spec.geometry
        if (geometry.view == "stereoscope" and restoration.half_ipd_cm is not None
                and restoration.half_ipd_nominal is not None):
            now_nominal = not session.spec.subject_settings
            if (restoration.half_ipd_cm != geometry.half_ipd_cm
                    or restoration.half_ipd_nominal != now_nominal):
                session.spec.setup_warnings += tuple(warnlist.of_changed_setup(
                    restoration.half_ipd_cm, restoration.half_ipd_nominal,
                    geometry.half_ipd_cm, now_nominal))
        try:
            session.resume(restoration, by=command.by, how="wlx taskd")
        except (Exceeded, TypeError, ValueError) as refused:
            # Its welfare rules refuse a value from the record -- a reward size over its
            # maximum, a negative fluid, a size that is no number -- before its first
            # write (review fix round 1, Important 1). Through `_sentence_or`, as above.
            self._refuse(command.KIND, command.by, _sentence_or(refused, _UNRESUMED))
            return
        session.offered_tasks = self._tasks()
        self.session = session
        # A return asked about it while it was stranded is moot now, as `_close_stranded`
        # leaves it (the final review's I4); another stranded session's question stays.
        if self.question is not None and self.question.session_id == found.session_id:
            self.question = None
        self.stranded.remove(found)

    # --- runs -----------------------------------------------------------------------

    def _between_runs(self, kind: str, by: Actor) -> Session | None:
        """The open session, when a run may be checked or started; otherwise refused,
        saying why."""
        if self.session is None:
            self._refuse(kind, by, "no session is open, so no run starts; open a session first")
            return None
        if self.session.phase != "between_runs":
            self._refuse(
                kind, by,
                "the session has ended and waits for its animal's return, so no run starts",
            )
            return None
        if self._starting is not None:
            self._refuse(kind, by, "a run is already starting, so this is refused")
            return None
        return self.session

    def _task(self, name: str, kind: str, by: Actor) -> Path | None:
        """A task file under `--tasks`, named by one file name ending `.py`; refused
        otherwise. **The name is held to `_folder_name` before any path is built**
        (carried from Task 7): it arrives over the wire, and the file it names is code
        the pre-flight and the run load, so a parent reference or an absolute path would
        run a file from outside `--tasks`."""
        if not (_folder_name(name) and name.endswith(".py")):
            self._refuse(
                kind, by,
                f"{name!r} is not a task file under {self.tasks}: a task is named by one "
                f"file name ending .py -- letters, digits, '_', '.' and '-', starting with "
                f"a letter or digit -- so nothing was loaded",
            )
            return None
        path = self.tasks / name
        if not path.is_file():
            self._refuse(
                kind, by, f"{name!r} is not a task file under {self.tasks}, so nothing was loaded"
            )
            return None
        return path

    def _preflight(self, session: Session, task: Path, values: dict,
                   plan: str | None = None, start_block: str | None = None) -> tuple:
        """Spec §6.2's items, taken now, in order -- the out-of-cage item always among
        them, since `preflight.gate` refuses a pre-flight without it.

        **Whatever raises while one item is checked is that item's fail** (the b3a-1
        final review's ruling), under the item's own name, and the other items are
        still taken: a check or a start never ends the service through its pre-flight,
        whatever item a later change adds. The out-of-cage item keeps its name when its
        own check raises, so the gate blocks on its fail, never on its absence.

        **It returns the run's warnings not yet accepted too**, for `_start` to hand to the
        run. **Taken for `plan`**, by its name in the task, or the plain run (engine build C2b):
        a plan the task lacks fails the task checks item, and the starting values cover the
        structures the plan's conditions play, each condition's values held to their ranges.
        **And for the block of it the run starts at** (`start_block`; the pop-out search build's
        Task 6), which fails the task checks item where the run cannot start there; it carries
        what the run's start offers to pick, the animal's previous session's end and what a
        resumed session's run goes on from (`_start_offers`).

        **In a demo** (demo mode §3.4, §3.7): the eye tracker's item names the mouse on its demo
        page as the session's gaze, still an unknown (`preflight.unmeasured`), and one more item
        fails a task waiting on more inputs than a demo has keys, naming them
        (`preflight.demo_inputs`)."""
        settings = Path(session.spec.subject_settings) if session.spec.subject_settings else None
        demo = session.spec.demo is not None
        owed: list = []
        try:
            item, loaded, findings = _preflight.task(
                task, self.allocation, session.spec.geometry, session.spec.calibration,
                deployment=session.spec.deployment, plan=plan, start_block=start_block,
            )
            checked = (item,)
        except Exception as broken:  # noqa: BLE001 -- see the docstring
            checked, loaded, findings = _unfinished((_preflight.TASK_CHECKS,), broken), None, []
        # **A starting luminance the panel cannot show its color set at, at the panel's reachable
        # top** (`check.in_reach`; the PI, 2026-11-20, "Start at the brightest it can, warn"):
        # the run's values as `Session.run` starts them, which every item below judges, and each
        # such a warning of the run's, asked with its others. One no value its setting allows
        # shows is left as asked, for the starting values item to refuse; a fault here leaves them
        # all as asked, that item saying what raised.
        reached: list = []
        if loaded is not None:
            try:
                used, reached, _ = in_reach(loaded, _preflight.starting(loaded, values),
                                                session.spec.calibration)
                values = {**values, **used}
            except Exception:  # noqa: BLE001 -- see above
                reached = []
        # Starting values outside their declared ranges, checked widened (XC-352's D2): its
        # warnings join the run's, and what breaks the run fails the starting values item.
        beyond = _preflight.beyond(loaded, values, self.allocation, session.spec.geometry,
                                   session.spec.calibration, session.spec.deployment, plan)
        # **And the layout at the run's values** (the console settings design's §4): what blocks
        # fails the starting values item with what `beyond` refuses, and its warnings join the
        # run's, those the load already gives said once.
        beyond += [finding for finding in _preflight.laid_out(
            loaded, values, plan, self.allocation, session.spec.geometry,
            session.spec.calibration, session.spec.deployment) if finding not in findings]

        def warned():
            try:
                # The setup's warnings too (XC-352's C6-C8): known at the open, asked with the
                # first run's, accepted once a session.
                rig = (self.open_warnings(session.spec.deployment)
                       + list(session.spec.setup_warnings))
            except Exception as broken:  # noqa: BLE001 -- the engine B plan, call 31
                # The rig's warnings could not be listed: the item fails, saying so, until they
                # list -- never a run started without them asked (call 31). Said through
                # `_fault`, so a fault whose own `str()` raises is said by its type, and cut as
                # the item's other sentences are (`preflight.warnings`).
                return _link.PreflightItem(
                    _preflight.WARNINGS, _preflight.FAIL,
                    _link.cut(
                        f"the warnings could not be listed: {_fault(broken)}; no run starts "
                        f"until they can be",
                        _link.NOTE_LIMIT,
                    ),
                )
            item, found = _preflight.warnings(
                rig + warnlist.of_findings(findings + beyond + reached),
                session.spec.session_kind,
                session.accepted_keys(),
            )
            owed.extend(found)
            return item

        return _link.Preflight(
            task=task.name,
            items=(
                *checked,
                *_contained((_preflight.WARNINGS,), warned),
                *_contained(
                    (_preflight.STARTING_VALUES,),
                    lambda: _preflight.values(loaded, values, [f for f in beyond if f.blocking],
                                              plan, calibration=session.spec.calibration),
                ),
                *_contained(
                    (_preflight.BOUNDED_CONFIG,)
                    + (() if settings is None else (_preflight.SUBJECT_SETTINGS,)),
                    lambda: _preflight.files(
                        Path(session.spec.bounds_config), session.spec.subject, settings,
                    ),
                ),
                *_contained(
                    (_preflight.OUT_OF_CAGE_MARK,), lambda: _preflight.out_of_cage(session)
                ),
                *_contained(
                    (_preflight.PUMP_CALIBRATION, _preflight.EYE_TRACKER),
                    lambda: _preflight.unmeasured(session.pump, demo=demo),
                ),
                *(_contained((_preflight.DEMO_INPUTS,), lambda: _preflight.demo_inputs(loaded))
                  if demo else ()),
            ),
            plan=plan,
            plans=() if loaded is None else tuple(loaded.plans),
            start_block=start_block,
            **self._start_offers(session, task, loaded, values, plan, start_block),
        ), owed

    def _start_offers(self, session: Session, path: Path, loaded, values: dict,
                      plan: str | None, start_block: str | None) -> dict:
        """**What a run's start offers to pick, and what the trainer is shown beside it** (the
        pop-out search build's Task 6; its design §3.5: "the stage, the staircase's starting level
        and the pairings to pick, with yesterday's end shown"), as the pre-flight's fields: the
        plan's stages and the task's pool (`taskd.start_rows`), the animal's previous session's
        end of this plan (`resume.previous`, `taskd.ended_said`) -- shown, never carried (§3.6) --
        and what a resumed session's first run goes on from (`Session.continues`); the previous
        session is looked for in the folder this one is written to, so a demo's is a demo's and a
        real session's never one (demo mode). **None of it is an item, so none of it fails a
        run**: a record that cannot be read is said so in `previous`, a task that did not load
        offers nothing."""
        if loaded is None:
            return {}
        stages, pool = start_rows(loaded, plan, values)
        try:
            # The session's own folder (demo mode): a demo's previous session is a demo's.
            last = _resume_mod.previous(session.spec.root, session.spec.subject,
                                        session.spec.session_id, path.name, plan)
            previous = None if last is None else ended_said(loaded, last)
        except Exception as broken:  # noqa: BLE001 -- shown, never a check: see the docstring
            previous = _link.cut(f"the previous session's end could not be read: {_fault(broken)}",
                                 _link.NOTE_LIMIT)
        return {"stages": stages, "pool": pool, "previous": previous,
                "continues": session.continues(loaded, plan, start_block, values)}

    def _check(self, command: _link.CheckRun) -> None:
        """Take a run's pre-flight and put it on the frame, starting nothing."""
        session = self._between_runs("check", command.by)
        if session is None:
            return
        task = self._task(command.task, "check", command.by)
        if task is not None:
            session.preflight, _ = self._preflight(session, task, command.values, command.plan,
                                                   command.start_block)

    def _start(self, command: _link.StartRun) -> None:
        """**Welfare-critical.** Accept a run (spec §6.2): the pre-flight **taken now**,
        never trusted from an earlier check, and S9a §10's rule asked of it with the
        items this person acknowledged by name (`preflight.gate`); only then is the run
        kept to start once this pass has published, with a seed drawn for it and the
        pre-flight as its start row records it -- who acknowledged each unknown
        (`preflight.rows`). It plays the plan the start names among its task's (XC-207;
        engine build C2b), which its pre-flight is taken for, or with none the plain run.
        **And at the block of it the start names** (the pop-out search build's Task 6), which its
        pre-flight's task checks fail where the run cannot start there.

        **A run past the out-of-cage limit is refused here, before `RUN_START`**
        (carried from Task 3): `Session.run` refuses none -- `welfare.preflight` checks no
        ceiling -- so it would strobe the start and write its row before `_ends` stopped
        it. The pre-flight's out-of-cage item fails once `welfare.must_stop` fires, and
        a fail blocks whatever is acknowledged.

        **Warnings, once a session** (engine build B): a run's new ones are its `warnings`
        item, a fail when the session's kind does not accept one and otherwise an unknown
        acknowledged by name; the pump calibration and the eye tracker, once acknowledged, are
        carried to the session's later runs while their sentences hold, and each start row
        says who acknowledged them. What a start accepts goes to the run with it, and is
        written as the run starts."""
        session = self._between_runs("start", command.by)
        if session is None:
            return
        task = self._task(command.task, "start", command.by)
        if task is None:
            return
        checked, owed = self._preflight(session, task, command.values, command.plan,
                                        command.start_block)
        session.preflight = checked
        # **Accepted once per session** (engine spec §19.3, §20.1): an unknown item accepted at
        # an earlier run, with the same sentence, counts as acknowledged here, under the name of
        # whoever accepted it. S9a §10's rule is `gate`'s, unchanged.
        carried = session.carried(checked)
        # `gate` is handed what was sent with the carried names added, never a set built from
        # it, so its own refusal of a bare string still applies (the second review's Minor 4).
        acknowledged = command.acknowledged
        if not isinstance(acknowledged, (str, bytes)):
            acknowledged = (*acknowledged, *carried)
        why = _preflight.gate(checked, acknowledged)
        if why is not None:
            self._refuse("start", command.by, why)
            return
        named = set(command.acknowledged)
        # What this start accepts, **handed to the run, which writes it as it starts** (the
        # engine B plan, call 23; `_start` writes nothing): the warnings item's list, when it
        # was acknowledged, and each unknown named here for the first time.
        newly = list(owed) if _preflight.WARNINGS in named else []
        newly += warnlist.of_unknowns(
            item for item in checked.items
            if item.name in named and item.name not in carried and item.name != _preflight.WARNINGS
        )
        self._starting = (
            RunSpec(
                task=str(task),
                trials=command.trials,
                seed=self._seed(),
                values=dict(command.values),
                plan=command.plan,
                start_block=command.start_block,
            ),
            _preflight.rows(checked, command.by, command.acknowledged, carried),
            command.by,
            newly,
        )

    def _run(self, run: RunSpec, rows: list, by: Actor, accepted=()) -> None:
        """The run, to its end. **Its backstop refusals** (`Session.run`'s, for a blocking
        finding, a plan the task lacks or a place with no value, XC-415; and
        `welfare.preflight`'s), raised before it starts, are refusals here.
        **Anything else is a fault, and contained** (the b3a-1 plan, decision 14): one
        raised once the run started -- `Exceeded` from a delivery `welfare` would not
        make among them -- `run()` has published and written into the run's end row;
        the session is back between runs with the animal still out, and the traceback
        goes to this process's stderr; the service goes on, so the return can be taken.
        **One raised before the run started** (fix round 1 of Task 8) -- a task edited to
        fail between its pre-flight and its run -- goes to stderr too, and is a start
        refusal on the feed, so a page shows why no run started. Ctrl-C is not caught:
        `wlx taskd` ends on it. What the start accepted is written by `Session.run` as the run
        starts, inside this containment (the engine B plan, call 23); a fault's sentence is
        cut for the feed (`link.NOTE_LIMIT`), since `Session.accept`'s refusal joins every
        sentence it refuses, and the traceback on stderr keeps every word. A refusal or a
        fault whose own `str()` raises -- a task file's -- is said by its type (`_sentence_or`,
        `_said`; XC-291), so saying it does not stop `wlx taskd`, within `_said`'s limits."""
        session = self.session
        before = session.run_index
        failing = "the run did not start"
        try:
            session.run(run, preflight_rows=rows, by=by, accepted=accepted)
        except (SystemExit, Exception) as ended:  # noqa: BLE001 -- see the docstring
            if session.run_index != before:
                traceback.print_exc(file=sys.stderr)
            elif isinstance(ended, (SystemExit, Exceeded)):
                session.refuse("start", by, _sentence_or(ended, failing))
            else:
                traceback.print_exc(file=sys.stderr)
                session.refuse("start", by, _link.cut(
                    f"{failing}: {_said(ended)}", _link.NOTE_LIMIT,
                ))

    # --- ending ---------------------------------------------------------------------

    def _end(self, command: _link.EndSession) -> None:
        """**Welfare-critical.** End the open session (P4d-2b spec §6.2): refused before
        anything is marked when it names another session or answers a question nobody
        was asked (`_unended`); a run accepted in this pass does not start; then its
        runs end and its head is released (`Session.end_runs`, the b3a-1 plan, decision
        6), then its return is taken through `marks`, the terminal's rules -- or, given
        no return, it waits for one. With none open, the stranded session it names.

        **Never during a run**: one sent then stops the run (`_Routed`) and is finished
        here once the run has returned (`step`), so the session is between runs or
        awaiting its return whenever this runs."""
        if self.session is None:
            self._close_stranded(command)
            return
        session = self.session
        unended = self._unended(command)
        if unended is not None:
            self._refuse("end", command.by, unended)
            return
        if self._starting is not None:
            self._starting = None
            self._refuse(
                "start", command.by,
                "the session was ended in the same pass, so the run does not start",
            )
        if session.phase == "between_runs":
            session.end_runs(command.by)
        if command.returned is None:
            return
        try:
            _marks.page_return(
                session, returned=command.returned, confirm=command.confirm, by=command.by
            )
        except _marks.Owed as owed:
            session.question = _link.Question(
                mark="return",
                session_id=session.spec.session_id,
                at=owed.at,
                said=owed.warning,
                answers=owed.answers,
            )
            self._refuse(
                "end",
                command.by,
                f"{owed.warning}. Send it again answering confirm, or with the time "
                f"typed again",
            )
            return
        except (argparse.ArgumentTypeError, Exceeded) as refused:
            self._refuse("end", command.by, str(refused))
            return
        session.close(how="wlx taskd")
        self.session = None
        # The session is a reference cycle (`welfare.Rig`'s docstring): collected here,
        # between sessions, never during a run (the b3a-1 plan, decision 17). **The
        # local goes first**: a collection with it still held frees nothing, and the
        # cycle would wait for an automatic one that could land in the next run.
        del session
        gc.collect()

    def _unended(self, command: _link.EndSession) -> str | None:
        """**Welfare-critical, as `_end`'s first step.** Why an `EndSession` ends nothing
        of the open session, or `None`: it names another session, or it confirms a
        return nobody was asked about (`_unasked`). Asked by `_end`, before anything is
        marked, and by `_Routed` during a run, before anything is stopped -- one rule
        for both, so an End refused before anything is marked never stops this animal's
        run. An End whose return time `_end` refuses later -- one it cannot read, or a
        far one sent unconfirmed, which poses a question -- has stopped the run by then,
        as between runs it has ended them."""
        session = self.session
        if command.session_id not in (None, session.spec.session_id):
            return (
                f"the session open is {session.spec.session_id}, not "
                f"{command.session_id}; nothing was ended"
            )
        if command.confirm is not False:
            return _unasked(
                session.question, "return", session.spec.session_id, command.returned,
                session.wall_now,
            )
        return None

    def _close_stranded(self, command: _link.EndSession) -> None:
        """**Welfare-critical.** A stranded session's return (spec §6.1), checked against
        its recorded departure under `welfare`'s rules (`stranded.restore`), written into
        its own record; a confirm taken only for the question posed (`_unasked`).
        Refused while its record cannot be read or its animal's bounded config is gone
        or will not load -- each with what to do."""
        found = next(
            (s for s in self.stranded if s.session_id == command.session_id), None
        )
        if found is None:
            self._refuse(
                "end",
                command.by,
                "no session is open"
                + (
                    f", and no stranded session is {command.session_id!r}"
                    if command.session_id
                    else "; to record a stranded animal's return, name its session"
                )
                + "; nothing was ended",
            )
            return
        if command.returned is None:
            self._refuse(
                "end", command.by,
                f"give the time {found.subject or 'the animal'} went back into its home cage",
            )
            return
        if command.confirm is not False:
            unasked = _unasked(
                self.question, "return", found.session_id, command.returned, self.wall_now
            )
            if unasked is not None:
                self._refuse("end", command.by, unasked)
                return
        bounds = None
        if found.left_at is not None:
            # **Before any path is built** (fix round 1 of Task 7): the subject is the
            # record's, and `wlx run --subject` takes any text, so `../outside` or an
            # absolute path would make a `bounds.py` outside `--subjects` the code that
            # runs next. An open's own rule, `_folder_name`, applies to it.
            if not _folder_name(found.subject):
                self._refuse(
                    "end",
                    command.by,
                    f"session {found.session_id}'s record names no animal folder: its "
                    f"animal is {found.subject!r}, which is not one folder name under "
                    f"--subjects, so no bounded config is loaded for it and no return can "
                    f"be checked. Repair the record by hand -- the departure row's "
                    f"subject is the animal's folder name -- then restart wlx taskd",
                )
                return
            bounds_path = self.subjects / found.subject / "bounds.py"
            if not bounds_path.is_file():
                self._refuse(
                    "end",
                    command.by,
                    f"{found.subject!r}'s bounded config ({bounds_path}) is needed to "
                    f"check its return against its departure, and it does not exist; "
                    f"restore it",
                )
                return
            try:
                bounds = _load_bounds(bounds_path)
            except (SystemExit, Exception) as broken:  # noqa: BLE001 -- the animal's files are code
                self._refuse(
                    "end",
                    command.by,
                    f"{found.subject!r}'s bounded config ({bounds_path}) is needed to "
                    f"check its return against its departure, and it would not load "
                    f"({type(broken).__name__}: {_sentence(broken)}); repair it",
                )
                return
        try:
            restored = _stranded.restore(
                found, bounds, self.root / found.session_id / XCON_DIRNAME, self.wall_now
            )
            _marks.page_return(
                restored,
                returned=command.returned,
                confirm=command.confirm,
                by=command.by,
                how="the page, after a restart",
            )
        except _marks.Owed as owed:
            self.question = _link.Question(
                mark="return", session_id=found.session_id, at=owed.at,
                said=owed.warning, answers=owed.answers,
            )
            self._refuse(
                "end", command.by,
                f"{owed.warning}. Send it again answering confirm, or with the time typed again",
            )
            return
        except (argparse.ArgumentTypeError, Exceeded) as refused:
            self._refuse("end", command.by, _sentence(refused))
            return
        if self.question is not None and self.question.session_id == found.session_id:
            self.question = None
        self.stranded.remove(found)


def run(args) -> int:
    """`wlx taskd`: load the rig and the allocation, bind the link, and serve until
    interrupted.

    **`--demo DIR`, a demo service** (demo mode §3.1): `--subjects`, `--root` and `--demo-root`
    refused beside it and `--link`'s four endpoints required, each before anything is made; then
    `DIR` made (`demo_folder`) and the four bound endpoints printed on one line, `wlx taskd: --link
    PUB,REP,MARK,GAZE`, flushed, for the process that started it to read (`wlx demo`). Without it,
    `--subjects` and `--root` are required, and **`--demo-root DIR`** names where a demo opened
    here goes, made if absent once the service has taken it. **A rig service holds the rig lock,
    shared, for its life** (`RIG_LOCK`; demo mode's Task 10), taken once its refusals are past and
    before its link binds; while `wlx demo` holds it, it says so and waits for the demo to end."""
    rig = _load_rig(args.rig)
    allocation = _load_allocation(args.allocation)
    demo = args.demo
    if demo is not None:
        beside = [flag for flag, given in (("--subjects", args.subjects), ("--root", args.root),
                                           ("--demo-root", args.demo_root)) if given is not None]
        if beside:
            raise SystemExit(
                f"refused: --demo makes its own folder, holding the reference animal alone, so "
                f"{' and '.join(beside)} cannot be given beside it: a demo service reaches no real "
                f"animal's files and no rig's data. Nothing was made"
            )
    else:
        missing = [flag for flag, given in (("--subjects", args.subjects), ("--root", args.root))
                   if given is None]
        if missing:
            raise SystemExit(
                f"refused: {' and '.join(missing)} {'is' if len(missing) == 1 else 'are'} "
                f"required, but beside --demo, which makes its own"
            )
    for flag, folder in (() if demo is not None else (("--subjects", args.subjects),)) + (
            ("--tasks", args.tasks),):
        if not folder.is_dir():
            raise SystemExit(f"refused: {flag} {folder} is not a folder")
    parts = args.link.split(",")
    if len(parts) not in (2, 3, 4):
        raise SystemExit(
            f"--link expects PUB,REP, PUB,REP,MARK or PUB,REP,MARK,GAZE (two to four "
            f"comma-separated endpoints), got {args.link!r}"
        )
    if demo is not None and len(parts) != 4:
        raise SystemExit(
            "refused: --demo needs --link's four endpoints, PUB,REP,MARK,GAZE: the fourth is "
            "where its page's pointer reports arrive, so with none no page could steer it. "
            "Nothing was made"
        )
    if demo is not None:
        return _serve(args, rig, allocation, parts)
    # **A rig service holds the rig lock for its life** (`RIG_LOCK`; demo mode §5 item 3), shared,
    # so `wlx demo` is refused beside it; while a demo holds it, this one says so and waits for the
    # demo to end rather than serving beside it, since its frames would share the processor.
    held = lock_rig(exclusive=False)
    if held is None:
        print(
            f"wlx taskd: a demo runs on this computer (wlx demo holds {rig_lock()}); this rig "
            f"service starts once it ends -- Ctrl-C at the demo's terminal ends it",
            file=sys.stderr, flush=True,
        )
        try:
            held = lock_rig(exclusive=False, wait=True)
        except KeyboardInterrupt:
            print("taskd: interrupted", file=sys.stderr)
            return 130
    try:
        return _serve(args, rig, allocation, parts)
    finally:
        os.close(held)


def _say_started(service: Service, link, demo) -> None:
    """**`wlx taskd`'s startup lines**, each flushed (the whole-build review's M6): where it
    publishes, its demo folder, each stranded session, each record in the demo folder that is no
    demo (its re-review, N2) and a refused calibration. Said inside `_serve`'s `try` (XC-512): the
    first line is the one a supervisor or a test waits for, and a Ctrl-C taken while the rest are
    said -- the demo folder read for them -- is an interrupt like any, not an uncaught
    `KeyboardInterrupt`."""
    if demo is not None:
        print(
            f"wlx taskd: --link {link.pub_endpoint},{link.rep_endpoint},"
            f"{link.mark_endpoint},{link.gaze_endpoint}",
            flush=True,
        )
    else:
        # Each startup line flushed (the whole-build review's M6), as a demo service's is: a
        # terminal or a supervisor reading the service's output sees them as it starts.
        print(
            f"wlx taskd: publishing on {link.pub_endpoint}, commands on "
            f"{link.rep_endpoint}"
            + (f", marks on {link.mark_endpoint}" if link.mark_endpoint else "")
            + (f", pointer reports on {link.gaze_endpoint}" if link.gaze_endpoint else ""),
            flush=True,
        )
        if service.demo_root is not None:
            print(f"  demos: written under {service.demo_root}, apart from --root",
                  flush=True)
    for found in service.stranded:
        print(
            f"  stranded: session {found.session_id} "
            f"({found.subject or 'record unreadable'}); no session opens until its "
            f"return is recorded",
            flush=True,
        )
    held = {found.session_id: found for found in service.stranded_astray}
    for session_id, subject in ([] if service.demo_root is None
                                else _not_demos(service.demo_root)):
        # **Warned, never refused** (the whole-build review's I1; the PI's warnings over
        # refusals, 2026-10-11), **every start, stranded or not** (its re-review, N2): the
        # service starts, holding a stranded one as the session it is.
        found = held.get(session_id)
        animal = (found.subject if found is not None else subject) or "record unreadable"
        then = ("It is held as the stranded session it is; once its return is recorded, move "
                "it out" if found is not None else "Move it out")
        print(
            f"  warning: the demo folder {service.demo_root} holds session {session_id} "
            f"({animal}), which is no demo: a demo is REFERENCE's, its config.json saying "
            f"demo, and a demo folder holds demos alone. Its folder is "
            f"{service.demo_root / session_id}. {then} of {service.demo_root}, or name "
            f"another folder as --demo-root",
            flush=True,
        )
    for found in service.stranded_demos:
        print(
            f"  stranded demo: session {found.session_id} in the demo folder; no demo opens "
            f"until its return is recorded, and it holds up no other session",
            flush=True,
        )
    if service.calibration_refused:
        # Said where the operator started it (the second review's Minor 12), whole: the
        # open's warning quotes it cut (XC-352's E1). Through `_printable`, as the console
        # prints it: the sentence quotes the record's path and what its loader said.
        print(
            f"  calibration: {_printable(service.calibration_refused)}; sessions run on the "
            f"default calibration, the sRGB standard, with a warning, until the record is "
            f"repaired and wlx taskd started again",
            flush=True,
        )


def _serve(args, rig: Rig, allocation: Allocation, parts: list) -> int:
    """`run`'s own, once its refusals are past and, for a rig service, the rig lock is held: the
    link bound, the service built, and served until interrupted."""
    demo = args.demo
    pub, rep, *more = parts
    try:
        link = _link.ZmqLink(
            pub, rep, more[0] if more else None, more[1] if len(more) > 1 else None,
            allow_remote=args.link_allow_remote,
        )
    except _link.RemoteBindRefused as refused:
        raise SystemExit(str(refused)) from refused
    with link:
        subjects, root = (args.subjects, args.root) if demo is None else demo_folder(demo)
        service = Service(
            rig=rig,
            rig_path=str(args.rig),
            subjects=subjects,
            tasks=args.tasks,
            allocation=allocation,
            allocation_path=str(args.allocation) if args.allocation else "",
            root=root,
            link=link,
            demo_service=demo is not None,
            demo_root=args.demo_root,
        )
        if args.demo_root is not None:
            try:
                args.demo_root.mkdir(parents=True, exist_ok=True)
            except OSError as why:
                raise SystemExit(
                    f"refused: --demo-root {_printable(str(args.demo_root))} cannot be made a "
                    f"folder: {why.strerror}"
                ) from why
        try:
            _say_started(service, link, demo)
            service.serve(threading.Event())
        except KeyboardInterrupt:
            open_session = service.session is not None
            service.shutdown()
            print(
                "taskd: interrupted -- the session was open, and the return to the cage "
                "was not recorded; the next start finds it stranded"
                if open_session
                else "taskd: interrupted",
                file=sys.stderr,
            )
            return 130
        except BaseException as fault:
            # **Any other way out says why too** (fix round 1 of Task 7): a fault with a
            # session open is recorded as the reason its return was not, then goes on to
            # the caller unchanged. A kill (SIGTERM, SIGKILL) writes nothing, and the
            # missing row is the signal, as for `wlx run`. **Said through `_said`**
            # (XC-291): a fault whose own `str()` raised here, before `shutdown` was called,
            # skipped the rows that make the next start find the session stranded.
            if service.session is not None:
                service.shutdown(
                    f"wlx taskd stopped on a fault with the session open: {_said(fault)}"
                )
                print(
                    f"taskd: stopped by {_type_name(fault)} -- the session was open, "
                    f"and the return to the cage was not recorded; the next start finds "
                    f"it stranded",
                    file=sys.stderr,
                )
            raise
    return 0
