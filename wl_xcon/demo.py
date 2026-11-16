"""`wlx demo` -- demo mode's quick command (its design §5; its plan's Task 10).

**One command, a task played with the mouse in thirty seconds**: the task checked as `wlx check`
checks it, against the demo's own field; then, on this computer only and never beside a rig
service, **a private copy of the rig service and its page, started as a rig runs them** -- `wlx
taskd --demo` and `wlx serve` as child processes, each binding its own ports and saying them, so no
port is chosen and then lost -- a session opened for the test monkey, `REFERENCE`, as the page
opens one, a run started, and the browser opened on the demo screen. **Ctrl-C ends it**: the run
stopped, the session ended with its return now, both children stopped, and the folder it made
deleted, `--keep DIR` copying the session's folder there first. A child that dies ends the other
and the command, saying which and why.

**Why the children and not a service in this process** (§2, "one engine, two doors"): passing here
is passing on the rig's page, since it is the rig's own two commands that run, talking over the
rig's own link.

**What it accepts as a person would on the page** (§5 item 4): each warning the open lists for the
session's kind, and each unknown of the run's pre-flight, every one printed; a refusal or a
pre-flight failure is printed and ends it. `--as` names the person, recorded as a box actor, this
computer's login name by default.

**A run's first trial waits for the page's pointer** (`pointer.Worlds.waiting`; this task's call):
before the first screen there is nothing drawn to point at, and an eye nobody steers ends a trial as
tracker lost, so the rig holds the first trial until a report arrives, the field drawn for the page
to point at. So the run is started here and the person begins it by pointing.

**The rig lock** (`service.RIG_LOCK`; the plan's call): every `wlx taskd` that is not a demo holds
it shared for its life, and this asks it exclusive without waiting, refused while it cannot have
it; the children are given it too, so a rig service started meanwhile waits until the whole demo
has gone. **A child outlives no `wlx demo`**: each reads its standard input to its end, which comes
when this process goes however it goes, and then stops itself as Ctrl-C stops it. Killed outright,
this command leaves its folder in the temporary folder, outside any rig's data (§7).
"""

from __future__ import annotations

import getpass
import os
import queue
import re
import secrets
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import webbrowser
from dataclasses import replace
from datetime import date, datetime
from pathlib import Path

from wl_xcon import cli as _cli
from wl_xcon import link as _link
from wl_xcon import preflight as _preflight
from wl_xcon import service as _service
from wl_xcon import warnlist
from wl_xcon.actor import Box
from wl_xcon.check import check_task
from wl_xcon.geometry import stand_in_housings
from wl_xcon.welfare import Deployment

#: **How long each child is given to say where it is**: its line, `wlx taskd: --link ...` or `wlx
#: serve: the console is at ...`, after it is started. Far past a start on a loaded computer (an
#: import of the package and a bind); one that takes longer is taken as hung, said, and stopped.
#: A patience, not a measurement.
STARTED_WITHIN_S = 60.0
#: **How long the rig is given to answer a command with the frame it changes**: an open, a check
#: (which loads the task) or a start, and an End, which waits for a trial in progress to end at
#: its boundary (a pop-out trial's longest waits are its settings', each at most ten seconds). A
#: patience, not a measurement: past it the command is said unanswered.
ANSWERED_WITHIN_S = 60.0
#: **How long a child is given to stop** once told to, as Ctrl-C stops it, before it is killed.
STOPPED_WITHIN_S = 10.0
#: How long one wait for a frame lasts, between which this command looks at its children: a
#: responsiveness choice, so a child that dies is said within it.
LOOK_EVERY_S = 0.25
#: **The children's endpoints**: loopback, each port the operating system's choice, bound by the
#: child that holds it and said by it (`wlx taskd --demo` prints all four), never chosen here.
LINK = ",".join(["tcp://127.0.0.1:0"] * 4)
HTTP = "127.0.0.1:0"
#: Where the page is opened: the box's own page, at the demo screen, full-window.
ADDRESS = "http://127.0.0.1:{port}/#demo"

#: **What each child runs**: `wlx` itself, `cli.main`, with two things a terminal does not give
#: it. **Ctrl-C at the terminal is this command's alone** -- ignored here, so it reaches the
#: children only as this command's End and stop -- and **SIGTERM stops a child as Ctrl-C stops it**,
#: a `KeyboardInterrupt`, so each ends by its own path. **And standard input read to its end**: the
#: end comes when `wlx demo` goes, however it goes, and the child then stops itself. Read from the
#: descriptor, never through `sys.stdin`, whose buffer's lock a thread still reading at the
#: interpreter's exit would hold.
_CHILD = (
    "import os, signal, sys, threading\n"
    "def _stop(*_):\n"
    "    raise KeyboardInterrupt\n"
    "signal.signal(signal.SIGINT, signal.SIG_IGN)\n"
    "signal.signal(signal.SIGTERM, _stop)\n"
    "def _orphaned():\n"
    "    try:\n"
    "        while os.read(0, 65536):\n"
    "            pass\n"
    "    finally:\n"
    "        os.kill(os.getpid(), signal.SIGTERM)\n"
    "threading.Thread(target=_orphaned, name='wlx demo gone', daemon=True).start()\n"
    "from wl_xcon.cli import main\n"
    "sys.exit(main(sys.argv[1:]))\n"
)

_TASKD_LINE = re.compile(r"^wlx taskd: --link (\S+)$")
_SERVE_LINE = re.compile(r"the console is at http://127\.0\.0\.1:(\d+)/")


class _Ended(Exception):
    """The demo ends, saying why: a refusal, a pre-flight failure, a child that died, or a command
    the rig did not answer. `status` is the command's exit status."""

    def __init__(self, said: str, status: int = 1) -> None:
        super().__init__(said)
        self.status = status


# --- Before anything starts --------------------------------------------------------------------


def _task_file(given: str, tasks: Path | None, checkout: Path) -> tuple[Path, Path]:
    """**The task file and the folder the demo service takes as `--tasks`** (§5 item 1): `given`
    is a path when it holds a folder separator, and its folder is then the service's `--tasks`
    (`--tasks` naming another is refused); otherwise a task's name under `--tasks`, the checkout's
    `tasks/` by default, `.py` added when it has none. Refused, saying why, when there is no such
    file, or when its name is not one the service takes (`service._folder_name`, ending `.py`)."""
    if os.sep in given or (os.altsep and os.altsep in given):
        path = Path(given).expanduser().resolve()
        if tasks is not None and tasks.expanduser().resolve() != path.parent:
            raise _Ended(
                f"refused: {_cli._printable(given)} is a path, whose folder is the demo's --tasks, "
                f"and --tasks names {_cli._printable(str(tasks))}; give one or the other. Nothing "
                f"was started")
        folder = path.parent
    else:
        folder = (checkout if tasks is None else tasks.expanduser()).resolve()
        path = folder / (given if given.endswith(".py") else f"{given}.py")
    if not path.is_file():
        raise _Ended(f"refused: there is no task file {_cli._printable(str(path))}. Nothing was "
                     f"started")
    if not (_service._folder_name(path.name) and path.name.endswith(".py")):
        raise _Ended(
            f"refused: {_cli._printable(path.name)} is not a name the rig service takes a task "
            f"by -- one file name ending .py, letters, digits, '_', '.' and '-', starting with a "
            f"letter or digit. Nothing was started")
    return path, folder


def _values(assignments: list[str]) -> dict:
    """`--set NAME=VALUE`, as `wlx run` reads it: a number where it is one, else the word."""
    values: dict = {}
    for assignment in assignments:
        name, sep, raw = assignment.partition("=")
        if not sep or not name:
            raise _Ended(f"refused: --set expects NAME=VALUE with a name before the '=', got "
                         f"{_cli._printable(repr(assignment))}. Nothing was started")
        try:
            values[name] = float(raw)
        except ValueError:
            values[name] = raw
    return values


def _checked(task_path: Path, allocation_path: Path, rig_path: Path, checkout: Path, *,
             view: str, deployment: Deployment, kind: str) -> None:
    """**The load checks `wlx check` runs** (§5 item 2), against the demo's own field -- in
    direct view the stand-in housings where the rig's are unmeasured (§3.6), through the stereoscope
    `REFERENCE`'s half-IPD -- and the rig's calibration or the default, judged for the session's
    kind; and whether its inputs have keys (`preflight.demo_inputs`, `pointer.inputs`). Each
    warning and finding printed as `wlx check --kind` prints it; a refusal ends it before anything
    starts."""
    rig = _cli._load_rig(rig_path)
    calibration, unloaded = _cli._calibration_or_default(rig, rig_path)
    stand_in = view == "direct" and not rig.housings
    try:
        if view == "direct":
            if stand_in:
                rig = replace(rig, housings=stand_in_housings(rig.panel_width_cm))
            geometry = rig.direct()
        else:
            settings = _cli._load_subject_settings(checkout / "reference_subject.py")
            geometry = rig.stereoscope(settings.half_ipd_cm)
    except ValueError as refused:
        raise _Ended(f"refused: {_cli._printable(str(refused))}. Nothing was started") from refused
    task = _cli._load_task(task_path)
    allocation = _cli._load_allocation(allocation_path)
    findings = check_task(task, allocation, geometry=geometry, calibration=calibration,
                          deployment=deployment, source=task_path)
    rig_warnings = (warnlist.of_unloaded(unloaded) if unloaded else []) + warnlist.of_calibration(
        calibration, date.fromtimestamp(time.time()), unloaded=bool(unloaded))
    outside = warnlist.refused(rig_warnings, kind)
    print(f"checked against: {_cli._setup_words(geometry.view, geometry.half_ipd_cm)}"
          + (", the stand-in housings (the rig's are unmeasured)" if stand_in else ""))
    print(f"calibration: {_cli._printable(_cli._calibration_words(calibration))}")
    for entry in rig_warnings:
        marker = "refused " if entry in outside else "warning "
        print(f"{marker} {_cli._printable(entry.code):28} {_cli._printable(entry.detail)} "
              f"(accepted in {', '.join(entry.accepted_in) or 'no session kind'})")
    for finding in findings:
        marker = ("refused " if finding.refuses(kind) else "warning " if finding.is_warning
                  else "review  ")
        kinds = f" (accepted in {', '.join(finding.accepted_in)})" if finding.is_warning else ""
        print(f"{marker} {_cli._printable(finding.code):28} "
              f"{_cli._printable(finding.detail)}{kinds}")
    keys = _preflight.demo_inputs(task)
    print(f"{'refused ' if keys.result == _preflight.FAIL else 'keys    '} "
          f"{keys.name:28} {_cli._printable(keys.said)}")
    refusing = len(outside) + sum(1 for f in findings if f.refuses(kind)) + (
        keys.result == _preflight.FAIL)
    if refusing:
        raise _Ended(f"task refused in a {kind} session, nothing started: {refusing} blocking "
                     f"finding(s), above")


# --- The children ------------------------------------------------------------------------------


class _Child:
    """**One child process, as a rig runs it**: `wlx` with `argv`, its standard output and error
    each read on a thread of its own and printed here as they come, each output line kept for
    `line`. **Once it is told to stop, what it says on its error is printed only if it ends some
    other way than as told** (`stop`): its own sentence for a Ctrl-C ("the session keeps running
    on the box") is about a rig, not a demo this command has just ended. Given the rig lock's
    descriptor, which it holds with this command."""

    def __init__(self, name: str, argv: list[str], *, env: dict, cwd: Path, lock: int) -> None:
        self.name = name
        self.process = subprocess.Popen(
            [sys.executable, "-c", _CHILD, *argv], stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1, env=env,
            cwd=cwd, pass_fds=(lock,))
        self._lines: queue.Queue = queue.Queue()
        self._stopping = False
        #: What it said on its error once told to stop.
        self._held: list[str] = []
        self._readers = [
            threading.Thread(target=self._read, name=f"{name}'s output", daemon=True),
            threading.Thread(target=self._errors, name=f"{name}'s errors", daemon=True),
        ]
        for reader in self._readers:
            reader.start()

    def _read(self) -> None:
        for line in self.process.stdout:
            sys.stdout.write(line)
            sys.stdout.flush()
            self._lines.put(line.rstrip("\n"))
        self._lines.put(None)

    def _errors(self) -> None:
        for line in self.process.stderr:
            if self._stopping:
                self._held.append(line)
            else:
                sys.stderr.write(line)
                sys.stderr.flush()

    def line(self, pattern: re.Pattern, within_s: float) -> re.Match:
        """The first line it prints that `pattern` finds, within `within_s`; `_Ended` saying why if
        it ends first or takes longer."""
        deadline = time.monotonic() + within_s
        while True:
            try:
                line = self._lines.get(timeout=LOOK_EVERY_S)
            except queue.Empty:
                if time.monotonic() > deadline:
                    raise _Ended(f"wlx demo: {self.name} did not say where it is within "
                                 f"{within_s:g} s, so the demo was stopped") from None
                continue
            if line is None:
                self.process.wait(STOPPED_WITHIN_S)
                raise _Ended(f"wlx demo: {self.name} ended before it said where it is "
                             f"({self.how_it_ended()}), so the demo was stopped")
            found = pattern.search(line)
            if found:
                return found

    def ended(self) -> bool:
        return self.process.poll() is not None

    def how_it_ended(self) -> str:
        """Its exit status in words: the status, or the signal that ended it."""
        code = self.process.returncode
        if code is None:
            return "still running"
        if code < 0:
            try:
                return f"killed by signal {-code} ({signal.Signals(-code).name})"
            except ValueError:
                return f"killed by signal {-code}"
        return f"exit status {code}"

    def stop(self) -> None:
        """Ended as Ctrl-C ends it (SIGTERM, which the child takes as one), within
        `STOPPED_WITHIN_S`, else killed; its output read to its end, and what it said on its error
        meanwhile printed if it ended some other way than Ctrl-C's 130."""
        self._stopping = True
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(STOPPED_WITHIN_S)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(STOPPED_WITHIN_S)
        if self.process.stdin is not None:
            self.process.stdin.close()
        for reader in self._readers:
            reader.join(STOPPED_WITHIN_S)
        if self.process.returncode != 130 and self._held:
            sys.stderr.writelines(self._held)
            sys.stderr.flush()


# --- The demo ----------------------------------------------------------------------------------


class _Demo:
    """**One demo, from its children's start to their stop**: the folder it made, the rig lock,
    the two children, and the console it opens the session as (`link.ZmqCommands` for commands,
    `link.ZmqConsole` for frames, as `wlx serve` holds them)."""

    def __init__(self, folder: Path, lock: int, by: Box) -> None:
        self.folder = folder
        self.lock = lock
        self.by = by
        self.children: list[_Child] = []
        self.taskd: _Child | None = None
        self.commands = None
        self.frames = None
        #: The last frame that was not a drawing: whether a session is open, and which.
        self.latest = None
        #: The session this command opened, and the demo service's sessions' folder.
        self.session_id: str | None = None
        self.root = folder / "demo" / "sessions"

    # --- Starting ---------------------------------------------------------------------------

    def start(self, *, rig: Path, tasks: Path, allocation: Path) -> int:
        """Both children started, each waited for until it says where it is; the console
        connected. Returns `wlx serve`'s port."""
        token = self.folder / "health-token"
        descriptor = os.open(token, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w") as written:
            written.write(secrets.token_urlsafe(32) + "\n")
        env = dict(os.environ)
        # The children run this `wlx`'s own package, wherever it was started from.
        package = str(Path(_cli.__file__).resolve().parents[1])
        env["PYTHONPATH"] = os.pathsep.join(
            [package] + ([env["PYTHONPATH"]] if env.get("PYTHONPATH") else []))
        self.taskd = self._child("wlx taskd --demo", [
            "taskd", "--demo", str(self.folder / "demo"), "--rig", str(rig), "--tasks",
            str(tasks), "--allocation", str(allocation), "--link", LINK], env)
        link = self.taskd.line(_TASKD_LINE, STARTED_WITHIN_S).group(1)
        serve = self._child("wlx serve", [
            "serve", "--link", link, "--http", HTTP, "--health-token-file", str(token)], env)
        port = int(serve.line(_SERVE_LINE, STARTED_WITHIN_S).group(1))
        pub, rep, _, _ = link.split(",")
        self.frames = _link.ZmqConsole(pub, None, receive_timeout_s=LOOK_EVERY_S)
        self.commands = _link.ZmqCommands(rep)
        return port

    def _child(self, name: str, argv: list[str], env: dict) -> _Child:
        child = _Child(name, argv, env=env, cwd=self.folder, lock=self.lock)
        self.children.append(child)
        print(f"wlx demo: {name} started (process {child.process.pid})", flush=True)
        return child

    # --- Frames and commands ----------------------------------------------------------------

    def _died(self, children) -> None:
        """`_Ended` naming one of `children` that has died, and how."""
        for child in children:
            if child.ended():
                raise _Ended(f"wlx demo: {child.name} ended ({child.how_it_ended()})")

    def frame(self, wanted, what: str, within_s: float = ANSWERED_WITHIN_S, children=None):
        """The first frame `wanted` takes, a drawing never; `_Ended` if one of `children` (both, by
        default) dies first or none comes within `within_s`, saying `what` was waited for."""
        deadline = time.monotonic() + within_s
        while True:
            self._died(self.children if children is None else children)
            if time.monotonic() > deadline:
                raise _Ended(f"wlx demo: no {what} within {within_s:g} s")
            try:
                frame = self.frames.receive()
            except TimeoutError:
                continue
            if isinstance(frame, _link.Drawn):
                continue
            self.latest = frame
            if wanted(frame):
                return frame

    def send(self, command) -> None:
        """`command` delivered (`ZmqCommands.deliver`), or `_Ended` saying why. **One handed over
        and not yet acknowledged is delivered**: the rig reads commands at a trial's boundary, and
        the frame that follows says whether it was applied (`answered`)."""
        try:
            self.commands.deliver(command)
        except _link.Unacknowledged:
            pass
        except _link.NotDelivered as why:
            raise _Ended(f"wlx demo: the {command.KIND} was {why}") from why

    def answered(self, command, kind: str, done, what: str, children=None):
        """`command` sent, and the frame it changes as `done` takes it; `_Ended` with the rig's
        own sentence if it refuses it instead (a refusal named `kind` that was not on the frame
        before), or as `frame` ends."""
        before = set(self.latest.refusals) if self.latest is not None else set()
        self.send(command)

        def settled(frame) -> bool:
            return done(frame) or any(
                refusal.name == kind and refusal not in before for refusal in frame.refusals)

        frame = self.frame(settled, what, children=children)
        if done(frame):
            return frame
        refused = [r for r in frame.refusals if r.name == kind and r not in before]
        raise _Ended(f"wlx demo: the {kind} was refused: {_cli._printable(refused[-1].why)}")

    # --- The session ------------------------------------------------------------------------

    def open(self, *, view: str, deployment: Deployment, kind: str) -> None:
        """**The session opened for `REFERENCE`** as the page opens one (§5 item 4): its id
        `demo-YYYYMMDD-HHMMSS` and its departure now, to the minute, both this computer's clock;
        each warning the idle frame lists for the kind -- a chaired session's only when it is one
        -- accepted, and printed."""
        idle = self.frame(lambda f: isinstance(f, _link.Idle), "frame from the demo service")
        now = datetime.now()
        self.session_id = now.strftime("demo-%Y%m%d-%H%M%S")
        chaired = set() if deployment is Deployment.RIG_CHAIRED else {
            entry.key for entry in warnlist.of_deployment(Deployment.RIG_CHAIRED)}
        accepted = [row for row in idle.warnings
                    if kind in row.accepted_in and (row.code, row.detail) not in chaired]
        for row in accepted:
            print(f"wlx demo: warning accepted: {_cli._printable(row.code)}: "
                  f"{_cli._printable(row.detail)}")
        self.answered(_link.OpenSession(
            by=self.by, session_id=self.session_id, animal=_service.REFERENCE,
            deployment=deployment.value, view=view, session_kind=kind,
            departure=now.strftime("%Y-%m-%dT%H:%M"), delivered_today=None, answer=None,
            amend_to=None, amend_reason="", accepted=tuple((r.code, r.detail) for r in accepted),
            demo=True,
        ), "open", lambda f: isinstance(f, _link.Telemetry) and f.session_id == self.session_id,
            "frame of the session opened")
        print(f"wlx demo: session {self.session_id} opened for {_service.REFERENCE}, out of the "
              f"cage at {now.strftime('%H:%M')}, as {self.by}", flush=True)

    def run(self, *, task: str, values: dict, plan: str | None, start_block: str | None,
            trials: int) -> None:
        """**The run checked and started** (§5 item 4): its pre-flight taken, each item printed,
        each unknown acknowledged as a person would on the page; a failure ends it. Then the start,
        with the task's own starts and `values` over them."""
        run = dict(task=task, values=values, plan=plan, start_block=start_block)
        checked = self.answered(
            _link.CheckRun(by=self.by, **run), "check",
            lambda f: isinstance(f, _link.Telemetry) and f.preflight is not None,
            "pre-flight").preflight
        for item in checked.items:
            print(f"wlx demo: pre-flight {item.result:7} {_cli._printable(item.name)}: "
                  f"{_cli._printable(item.said)}")
        failed = [item.name for item in checked.items if item.result == _preflight.FAIL]
        if failed:
            raise _Ended(f"wlx demo: the run's pre-flight failed ({', '.join(failed)}), so no "
                         f"run started")
        unknown = tuple(item.name for item in checked.items if item.result == _preflight.UNKNOWN)
        if unknown:
            print(f"wlx demo: acknowledged: {', '.join(unknown)}")
        self.answered(
            _link.StartRun(by=self.by, trials=trials, acknowledged=unknown, **run), "start",
            lambda f: isinstance(f, _link.Telemetry) and f.phase == "running",
            "frame of the run started")

    def watch(self) -> None:
        """Until Ctrl-C, or a child dies: every frame read, the last kept."""
        while True:
            self.frame(lambda f: False, "end", within_s=float("inf"))

    # --- Ending -----------------------------------------------------------------------------

    def end(self) -> None:
        """**The open session ended with its return now** (§5 item 6), a run in progress stopped
        first by the rig itself, and the frame it closes with awaited -- or nothing, with no session
        open. Whichever session is open: the person may have ended this command's and opened
        another from the page."""
        latest = self.latest
        if not isinstance(latest, _link.Telemetry) or latest.phase == "closed":
            return
        ending = latest.session_id
        self.answered(
            _link.EndSession(by=self.by, session_id=None, returned="now", confirm=False), "end",
            lambda f: isinstance(f, _link.Idle) or (
                f.session_id == ending and f.phase == "closed"),
            "frame of the session closed", children=[self.taskd])
        print(f"wlx demo: session {ending} ended, its return recorded now", flush=True)

    def close(self, keep: Path | None) -> None:
        """Both children stopped, the console closed, `keep` given a copy of the session's folder,
        and the folder this command made deleted; the rig lock let go. Ctrl-C is ignored meanwhile,
        so nothing is left half-done. **A copy to `keep` that fails** -- no permission, a full disk
        (the whole-build review's M7) -- is said, naming where the session's folder is, and this
        command's folder is kept, not deleted; the lock is let go whatever happens."""
        previous = signal.signal(signal.SIGINT, signal.SIG_IGN)
        try:
            for child in reversed(self.children):
                child.stop()
            for closing in (self.frames, self.commands):
                if closing is not None:
                    closing.close()
            copied = True
            if keep is not None:
                kept = self.root / self.session_id if self.session_id else None
                if kept is not None and kept.is_dir():
                    try:
                        shutil.copytree(kept, keep)
                    except OSError as why:
                        # `shutil.Error`, a partial copy's, is an `OSError` too.
                        copied = False
                        print(f"wlx demo: session {self.session_id}'s folder could not be copied "
                              f"to {keep} ({why}); it is kept where it is, {kept}, and this "
                              f"command's folder is not deleted", file=sys.stderr, flush=True)
                    else:
                        print(f"wlx demo: session {self.session_id}'s folder copied to {keep}")
                else:
                    print(f"wlx demo: no session was opened, so nothing was copied to {keep}")
            if copied:
                shutil.rmtree(self.folder, ignore_errors=True)
        finally:
            try:
                os.close(self.lock)
            finally:
                signal.signal(signal.SIGINT, previous)


def run(args) -> int:
    """`wlx demo` (§5): see the module docstring. 130 when Ctrl-C ends it, as `wlx serve` and `wlx
    taskd` end; 1 when anything else does, saying why."""
    try:
        return _run(args)
    except _Ended as ended:
        print(str(ended), file=sys.stderr)
        return ended.status
    except KeyboardInterrupt:
        print("wlx demo: interrupted before anything started", file=sys.stderr)
        return 130


def _run(args) -> int:
    checkout = _cli.checkout_tasks()
    keep = None if args.keep is None else args.keep.expanduser().resolve()
    if keep is not None and keep.exists():
        raise _Ended(f"refused: --keep {_cli._printable(str(args.keep))} exists, and the session's "
                     f"folder is copied to a new one. Nothing was started")
    who = args.actor if args.actor is not None else getpass.getuser()
    if not who:
        raise _Ended("refused: no login name is known on this computer, so name the person with "
                     "--as WHO. Nothing was started")
    task_path, tasks = _task_file(args.task, args.tasks, checkout)
    rig = (checkout / "rig.py" if args.rig is None else args.rig.expanduser()).resolve()
    allocation = (checkout / "allocation.py" if args.allocation is None
                  else args.allocation.expanduser()).resolve()
    _cli._require_file(rig, "--rig")
    _cli._require_file(allocation, "--allocation")
    values = _values(args.set)
    deployment = Deployment.RIG_CHAIRED if args.chaired else Deployment.RIG_FIXED
    _checked(task_path, allocation, rig, checkout, view=args.view, deployment=deployment,
             kind=args.session_kind)

    lock = _service.lock_rig(exclusive=True)
    if lock is None:
        raise _Ended(
            f"refused: a rig service runs on this computer (wlx taskd holds "
            f"{_service.rig_lock()}), and a demo's drawing would share the processor its "
            f"session's frames run on. End the rig service first. Nothing was started")
    demo = _Demo(Path(tempfile.mkdtemp(prefix="wlx-demo-")), lock, Box(who))
    print(f"wlx demo: its folder is {demo.folder}, deleted when it ends", flush=True)
    status = 0
    try:
        try:
            port = demo.start(rig=rig, tasks=tasks, allocation=allocation)
            demo.open(view=args.view, deployment=deployment, kind=args.session_kind)
            demo.run(task=task_path.name, values=values, plan=args.plan,
                     start_block=args.start_block, trials=args.trials)
            address = ADDRESS.format(port=port)
            print(f"wlx demo: the demo screen is at {address}", flush=True)
            print("wlx demo: the run's first trial waits for the pointer: point at the demo "
                  "screen to begin it. Ctrl-C here ends the demo", flush=True)
            if not args.no_browser:
                webbrowser.open(address)
            demo.watch()
        except KeyboardInterrupt:
            status = 130
            print("wlx demo: ending: the run stopped, the session ended with its return now, the "
                  "rig service and its page stopped", file=sys.stderr, flush=True)
            _ending(demo)
        except _Ended as ended:
            status = ended.status
            print(str(ended), file=sys.stderr, flush=True)
            if demo.taskd is not None and not demo.taskd.ended():
                _ending(demo)
            for child in demo.children:
                if not child.ended():
                    print(f"wlx demo: stopping {child.name}", file=sys.stderr, flush=True)
    finally:
        demo.close(keep)
    return status


def _ending(demo: _Demo) -> None:
    """`demo.end()`, said when it cannot be done: a second Ctrl-C, a child gone, or no answer."""
    try:
        demo.end()
    except KeyboardInterrupt:
        print("wlx demo: interrupted again: stopped without recording the session's return",
              file=sys.stderr, flush=True)
    except _Ended as ended:
        print(f"{ended}; the session's return was not recorded", file=sys.stderr, flush=True)
