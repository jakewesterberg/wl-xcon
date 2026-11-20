"""**`wlx demo`** (demo mode §5, §7, §9; its plan's Task 10), as a person runs it: its own process,
started at a terminal with Ctrl-C at its default, its two children `wlx taskd --demo` and `wlx
serve` started by it, and every wait bounded. Each test names its own rig lock (`WLX_RIG_LOCK`)
and temporary folder (`TMPDIR`), so the folder `wlx demo` makes, and whether it is gone, is seen
there, and no test's demo is refused for another's rig service. `BROWSER` names a stand-in that
writes the address it is given to a file, so the default browser is never opened.

**The scripted pointer here is a page's**: `POST /gaze` to the demo's own `wlx serve`, as the box's
page sends it, at the place a scripted person aims (`tests/_demo.py`), who reads each screen the
rig publishes on the link's first endpoint, which `wlx demo` prints from its child. Engine test
material on the wall clock: no timing claim rests on it (CLAUDE.md).
"""

from __future__ import annotations

import fcntl
import http.client
import json
import os
import queue
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from _demo import REPORT_EVERY_S, Person, target, xtasks_or_skip
from _rig import PATH as RIG_FILE
from _zmq_release import _every_zmq_context_released  # noqa: F401
from wl_xcon import pointer
from wl_xcon.link import Drawn, Telemetry, ZmqConsole

ROOT = Path(__file__).resolve().parents[1]
#: `wlx` as its own process, as `tests/test_serve.py` starts `wlx serve`.
MAIN = "import sys; from wl_xcon.cli import main; sys.exit(main(sys.argv[1:]))"
#: How long any one thing a test waits for may take: well past a start of three processes on a
#: loaded computer, so a slow one is never read as a fault, and a hang is.
PATIENCE_S = 60.0
#: The pop-out's timings, shortened by its settings as `tests/test_demo_popout.py` has them (its
#: docstring says why each): a quarter second between trials, past the saccade detector's warm-up.
SHORT = ("--set", "inter_trial=0.25", "--set", "fix_hold=0.05", "--set", "target_hold=0.1",
         "--set", "timeout=0")
#: How long a test leaves a run's first trial waiting with no pointer before it looks.
UNSTEERED_S = 1.5

_STARTED = re.compile(r"^wlx demo: (wlx taskd --demo|wlx serve) started \(process (\d+)\)$")
_FOLDER = re.compile(r"^wlx demo: its folder is (.+), deleted when it ends$")
_ADDRESS = re.compile(r"^wlx demo: the demo screen is at (http://127\.0\.0\.1:(\d+)/#demo)$")
_OPENED = re.compile(r"^wlx demo: session (demo-\d{8}-\d{6}) opened for REFERENCE")
_WAITING = re.compile(r"^wlx demo: the run's first trial waits for the pointer")
_LINK = re.compile(r"^wlx taskd: --link (\S+)$")


def _popout() -> Path:
    return xtasks_or_skip() / "popout_search.py"


class _Process:
    """**A `wlx` command as its own process, as a terminal runs it**: SIGINT at its default, as a
    terminal gives it (see `tests/test_serve.py`'s `test_wlx_serve_exits_130_on_a_real_sigint`),
    in a process group of its own, which its children join, so Ctrl-C reaches them all, as a
    terminal sends it (`ctrl_c`); its output read on threads of its own, each line kept, the
    standard output's also queued for `line`."""

    def __init__(self, argv: list[str], env: dict) -> None:
        self.process = subprocess.Popen(
            [sys.executable, "-c", MAIN, *argv], cwd=ROOT, env=env, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, start_new_session=True,
            preexec_fn=lambda: signal.signal(signal.SIGINT, signal.SIG_DFL))
        self.out: list[str] = []
        self.err: list[str] = []
        self._lines: queue.Queue = queue.Queue()
        self._readers = [threading.Thread(target=self._read, args=(stream, kept, queued),
                                          daemon=True)
                         for stream, kept, queued in ((self.process.stdout, self.out, True),
                                                      (self.process.stderr, self.err, False))]
        for reader in self._readers:
            reader.start()

    def _read(self, stream, kept: list, queued: bool) -> None:
        for line in stream:
            kept.append(line.rstrip("\n"))
            if queued:
                self._lines.put(line.rstrip("\n"))
        if queued:
            self._lines.put(None)

    def line(self, pattern: re.Pattern) -> re.Match:
        """The first line of standard output from here on that `pattern` matches; the test fails if
        none comes within `PATIENCE_S` or the process ends first."""
        deadline = time.monotonic() + PATIENCE_S
        while time.monotonic() < deadline:
            try:
                line = self._lines.get(timeout=0.1)
            except queue.Empty:
                continue
            if line is None:
                self.process.wait(PATIENCE_S)
                pytest.fail(f"ended ({self.process.returncode}) with no line {pattern.pattern!r}:"
                            f"\n{self.said()}")
            found = pattern.search(line)
            if found:
                return found
        pytest.fail(f"no line {pattern.pattern!r} within {PATIENCE_S} s:\n{self.said()}")

    def ctrl_c(self) -> None:
        """Ctrl-C at its terminal: SIGINT to its whole process group, its children's too."""
        os.killpg(self.process.pid, signal.SIGINT)

    def ended(self) -> int:
        """Its exit status, once it has ended and its output been read, within `PATIENCE_S`."""
        self.process.wait(PATIENCE_S)
        for reader in self._readers:
            reader.join(PATIENCE_S)
        return self.process.returncode

    def said(self) -> str:
        return "\n".join(self.out + ["--- stderr ---"] + self.err)


class _Wlx:
    """**`wlx` commands for one test**: each with the test's rig lock, temporary folder and
    stand-in browser; every process still running when the test ends killed, `wlx demo`'s
    children among them (named on its output), so none outlives the test, pass or fail."""

    def __init__(self, tmp_path: Path) -> None:
        self.tmp = tmp_path / "tmp"
        self.tmp.mkdir()
        self.lock = tmp_path / "rig.lock"
        self.opened = tmp_path / "opened.txt"
        browser = tmp_path / "browser.sh"
        browser.write_text(f'#!/bin/sh\nprintf "%s" "$1" > "{self.opened}"\n')
        browser.chmod(0o755)
        # Unbuffered: `wlx taskd` prints its startup line unflushed, which a pipe would hold.
        self.env = dict(os.environ, WLX_RIG_LOCK=str(self.lock), TMPDIR=str(self.tmp),
                        BROWSER=str(browser), PYTHONUNBUFFERED="1")
        self.processes: list[_Process] = []

    def __call__(self, *argv: str) -> _Process:
        process = _Process(list(argv), self.env)
        self.processes.append(process)
        return process

    def demo(self, *argv: str) -> _Process:
        return self("demo", *argv)

    def children(self, demo: _Process) -> dict[str, int]:
        """`wlx demo`'s children's process ids, by name, as it said them."""
        return {found.group(1): int(found.group(2)) for found in map(_STARTED.match, demo.out)
                if found}

    def folders(self) -> list[Path]:
        """The demo folders in the test's temporary folder."""
        return sorted(self.tmp.glob("wlx-demo-*"))

    def lock_free(self) -> bool:
        """Whether nothing holds the rig lock: an exclusive one can be had at once."""
        if not self.lock.exists():
            return True
        with open(self.lock) as held:
            try:
                fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return False
            fcntl.flock(held, fcntl.LOCK_UN)
            return True

    def close(self) -> None:
        for process in self.processes:
            pids = [process.process.pid, *self.children(process).values()]
            for pid in pids:
                try:
                    os.kill(pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            process.process.wait(PATIENCE_S)


@pytest.fixture
def wlx(tmp_path):
    made = _Wlx(tmp_path)
    try:
        yield made
    finally:
        made.close()


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def _gone(pid: int) -> bool:
    """Whether process `pid` has ended, within `PATIENCE_S`: a child `wlx demo` stopped is reaped
    by it; one that stopped itself is reaped by the system."""
    deadline = time.monotonic() + PATIENCE_S
    while _alive(pid):
        if time.monotonic() > deadline:
            return False
        time.sleep(0.05)
    return True


def _started(demo: _Process, *, at_run: bool = True) -> dict:
    """`wlx demo` followed to its run's start: its folder, its session, its page's port and its
    link, each as it said them."""
    folder = Path(demo.line(_FOLDER).group(1))
    link = demo.line(_LINK).group(1)
    session = demo.line(_OPENED).group(1)
    address = demo.line(_ADDRESS)
    if at_run:
        demo.line(_WAITING)
    return {"folder": folder, "link": link.split(","), "session": session,
            "address": address.group(1), "port": int(address.group(2))}


def _kinds(xcon: Path) -> list[str]:
    return [json.loads(line)["kind"] for line in (xcon / "welfare_notes.jsonl").read_text()
            .splitlines()]


def _post_gaze(port: int, body: dict) -> tuple[int, dict]:
    """`POST /gaze` as the box's own page sends it: a loopback `Host`, the page's `Origin`, JSON."""
    raw = json.dumps(body).encode("utf-8")
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=PATIENCE_S)
    try:
        connection.request("POST", "/gaze", body=raw, headers={
            "Host": f"127.0.0.1:{port}", "Origin": f"http://127.0.0.1:{port}",
            "Content-Type": "application/json"})
        response = connection.getresponse()
        return response.status, json.loads(response.read())
    finally:
        connection.close()


def _rig_service(wlx: _Wlx, tmp_path: Path, *, demo_root: bool = False) -> tuple[_Process, dict]:
    """A rig service, `wlx taskd` without `--demo`, with `REFERENCE` under its own `--subjects`,
    this checkout's tasks and its own `--root` (and `--demo-root`), on two loopback endpoints."""
    folders = {name: tmp_path / name for name in ("subjects", "root", "demos")}
    (folders["subjects"] / "REFERENCE").mkdir(parents=True)
    shutil.copy(ROOT / "tasks" / "eight_hour_bounds.py",
                folders["subjects"] / "REFERENCE" / "bounds.py")
    folders["root"].mkdir()
    extra = ["--demo-root", str(folders["demos"])] if demo_root else []
    link = ",".join(["tcp://127.0.0.1:0"] * (4 if demo_root else 2))
    return wlx("taskd", "--rig", RIG_FILE, "--subjects", str(folders["subjects"]), "--tasks",
               "tasks", "--root", str(folders["root"]), "--allocation", "tasks/allocation.py",
               "--link", link, *extra), folders


# --- Started, and its address --------------------------------------------------------------------


@pytest.mark.parametrize("browser", [False, True], ids=["--no-browser", "the browser"])
def test_it_prints_its_address_with_no_browser(wlx, browser):
    """§5 item 5: the page is the box's own, at the demo screen, `http://127.0.0.1:PORT/#demo`,
    printed with `--no-browser` and the default browser left alone; without it, that address is
    what the default browser is opened on. The page is served there."""
    demo = wlx.demo(str(_popout()), *([] if browser else ["--no-browser"]))
    started = _started(demo)
    connection = http.client.HTTPConnection("127.0.0.1", started["port"], timeout=PATIENCE_S)
    try:
        connection.request("GET", "/", headers={"Host": f"127.0.0.1:{started['port']}"})
        assert connection.getresponse().status == 200
    finally:
        connection.close()
    if browser:
        deadline = time.monotonic() + PATIENCE_S
        while not wlx.opened.exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        assert wlx.opened.read_text() == started["address"]
    else:
        time.sleep(1.0)
        assert not wlx.opened.exists(), "--no-browser opened the browser"
    demo.ctrl_c()
    assert demo.ended() == 130, demo.said()


# --- Played through its own page ---------------------------------------------------------------


class _Correct(Person):
    """Fixates, and at the go looks to the odd disc and stays."""

    def go(self, drawn):
        return (*target(drawn), False)


def test_a_scripted_pointer_drives_a_trial_through_its_wlx_serve(wlx, zmq_cleanup):
    """§9: a run of one trial of the pop-out, started by `wlx demo`, **waits for the page's pointer
    with the field drawn** -- no trial begins while nobody steers, and no trial is scored (this
    task's call: before the first screen there is nothing to point at) -- and is then played by a
    scripted pointer posting to its `wlx serve` as the box's page does, reading the screens the rig
    publishes: the rig's own eye rules score the look to the odd disc correct. **Its pre-flight
    says that `--set fix_hold=` does nothing** (the pop-out revision's whole-build review, M5): the
    task draws `fix_hold` every trial."""
    from wl_xcon.preflight import DRAWN_GIVEN

    demo = wlx.demo(str(_popout()), "--no-browser", "--trials", "1", *SHORT)
    started = _started(demo)
    (values,) = [line for line in demo.out if line.startswith("wlx demo: pre-flight pass    "
                                                              "starting values: ")]
    assert f"{DRAWN_GIVEN} ('fix_hold')" in values, values
    trials = started["folder"] / "demo" / "sessions" / started["session"] / "xcon" / "trials.jsonl"
    screens = zmq_cleanup(ZmqConsole(started["link"][0], None, settle_s=0.0,
                                     receive_timeout_s=0.05))
    deadline = time.monotonic() + UNSTEERED_S
    unsteered = []
    while time.monotonic() < deadline:
        try:
            unsteered.append(screens.receive())
        except TimeoutError:
            pass
    drawn = [frame for frame in unsteered if isinstance(frame, Drawn)]
    assert drawn, "no field was drawn for the page to point at"
    assert {(d.frame, d.screen, d.trial) for d in drawn} == {(0, None, 0)}, "a trial began"
    assert {f.phase for f in unsteered if isinstance(f, Telemetry)} == {"running"}
    assert not trials.exists() or trials.read_text() == "", "a trial was scored unsteered"

    person, answers, seq = _Correct(), [], 0
    deadline = time.monotonic() + PATIENCE_S
    due = time.monotonic()
    while not (trials.exists() and trials.read_text()) and time.monotonic() < deadline:
        if time.monotonic() >= due:
            x, y, b = person.aim()
            seq += 1
            answers.append(_post_gaze(started["port"], {
                "page": "scripted", "seq": seq, "x": x, "y": y, "over": True, "b": b,
                "button": False, "held": 0, "presses": [0] * pointer.KEYS}))
            due = max(due + REPORT_EVERY_S, time.monotonic())
        try:
            frame = screens.receive()
        except TimeoutError:
            continue
        if isinstance(frame, Drawn):
            person.seen(frame)

    (line,) = [json.loads(text) for text in trials.read_text().splitlines()]
    assert line["outcome"] == "correct", line
    assert {status for status, _ in answers} == {200}, answers
    assert {answer["status"] for _, answer in answers} == {"sent"}
    assert any('"POST /gaze" 200' in line for line in demo.err), "its page's log, said"
    demo.ctrl_c()
    assert demo.ended() == 130, demo.said()


# --- Ended -------------------------------------------------------------------------------------


def test_sigint_ends_it_with_its_folder_gone_and_the_return_recorded(wlx, zmq_cleanup):
    """§5 item 6: Ctrl-C ends it -- the run stopped, the session ended with its return now, the
    frame it closes with published, both children stopped, and the folder it made deleted -- with
    130, as `wlx serve` and `wlx taskd` end on Ctrl-C."""
    demo = wlx.demo(str(_popout()), "--no-browser")
    started = _started(demo)
    children = wlx.children(demo)
    assert set(children) == {"wlx taskd --demo", "wlx serve"}
    assert started["folder"].parent == wlx.tmp and started["folder"].is_dir()
    frames = zmq_cleanup(ZmqConsole(started["link"][0], None, receive_timeout_s=PATIENCE_S))
    frames.receive()
    demo.ctrl_c()
    deadline = time.monotonic() + PATIENCE_S
    closed = None
    while closed is None and time.monotonic() < deadline:
        frame = frames.receive()
        if (isinstance(frame, Telemetry) and frame.session_id == started["session"]
                and frame.phase == "closed"):
            closed = frame
    assert demo.ended() == 130, demo.said()
    assert closed is not None, "the session never closed: its return was not recorded"
    assert (f"wlx demo: session {started['session']} ended, its return recorded now"
            in demo.out), demo.said()
    assert not started["folder"].exists() and wlx.folders() == []
    assert not any(map(_alive, children.values())), "a child outlived wlx demo"
    assert wlx.lock_free()


def test_keep_copies_the_session_folder_first(wlx, tmp_path):
    """§5 item 6: `--keep DIR` copies the session's folder there before the demo's own is deleted:
    its whole record, the run started with `--set`'s value over the task's own (§5 item 4, the
    PI's try-out's `response_deadline=3.0`) and ended by the operator, the session ended by its
    return, and its `config.json` saying demo."""
    kept = tmp_path / "kept"
    demo = wlx.demo(str(_popout()), "--no-browser", "--keep", str(kept),
                    "--set", "response_deadline=3.0")
    started = _started(demo)
    demo.ctrl_c()
    assert demo.ended() == 130, demo.said()
    assert not started["folder"].exists()
    xcon = kept / "xcon"
    assert json.loads((xcon / "config.json").read_text())["demo"]["gaze"] == "mouse"
    assert json.loads((xcon / "config.json").read_text())["session_id"] == started["session"]
    assert _kinds(xcon)[-2:] == ["returned", "session ended"]
    run_start, run_end = map(json.loads, (xcon / "runs.jsonl").read_text().splitlines())
    assert run_start["layers"]["run"] == {"response_deadline": 3.0}, "--set, over the task's own"
    assert run_end["stop_kind"] == "operator"


def test_keep_naming_an_existing_dir_is_refused_before_anything_starts(wlx, tmp_path):
    """§5 item 6, §7: `--keep DIR` with `DIR` there is refused at the start: no check, no folder,
    no child and no lock."""
    kept = tmp_path / "kept"
    kept.mkdir()
    demo = wlx.demo(str(_popout()), "--no-browser", "--keep", str(kept))
    assert demo.ended() == 1, demo.said()
    assert demo.err[-1].startswith(f"refused: --keep {kept} exists"), demo.said()
    assert demo.out == [] and wlx.folders() == [] and wlx.lock_free()
    assert list(kept.iterdir()) == []


def test_a_keep_copy_that_fails_says_where_the_folder_is_keeps_it_and_lets_the_lock_go(
        monkeypatch, tmp_path, capsys):
    """The whole-build review's M7: a `--keep` copy that fails at the end -- here no permission
    to make `DIR` -- is said, naming where the session's folder is; the folder `wlx demo` made is
    kept, not deleted, so the record survives; and the rig lock is let go all the same."""
    from wl_xcon import demo as demo_module
    from wl_xcon import service
    from wl_xcon.actor import Box

    monkeypatch.setenv("WLX_RIG_LOCK", str(tmp_path / "rig.lock"))
    lock = service.lock_rig(exclusive=True)
    folder = tmp_path / "wlx-demo-x"
    made = demo_module._Demo(folder, lock, Box("t"))
    made.session_id = "demo-20270114-120000"
    session = made.root / made.session_id
    (session / "xcon").mkdir(parents=True)
    (session / "xcon" / "config.json").write_text("{}")
    shut = tmp_path / "shut"
    shut.mkdir()
    shut.chmod(0o500)
    try:
        made.close(shut / "kept")
    finally:
        shut.chmod(0o700)
    err = capsys.readouterr().err
    assert (f"wlx demo: session {made.session_id}'s folder could not be copied to "
            f"{shut / 'kept'} (") in err, err
    assert (f"); it is kept where it is, {session}, and this command's folder is not deleted"
            in err), err
    assert (session / "xcon" / "config.json").read_text() == "{}"
    assert not (shut / "kept").exists()
    free = service.lock_rig(exclusive=True)
    assert free is not None, "the rig lock outlived the command"
    os.close(free)


class _CtrlCAsTaken:
    """**A child's waitpid lock, and a Ctrl-C the moment it is taken**: `subprocess.Popen`'s own
    lock, which `poll` takes before its `try` (CPython 3.13's `_internal_poll`), with SIGINT raised
    in this process the first time it is had -- where a real one landed under CI's load."""

    def __init__(self, real) -> None:
        self.real, self.armed = real, True

    def acquire(self, *args, **kwargs) -> bool:
        got = self.real.acquire(*args, **kwargs)
        if got and self.armed:
            self.armed = False
            signal.raise_signal(signal.SIGINT)
        return got

    def release(self) -> None:
        self.real.release()

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, *_) -> None:
        self.release()


class _Quiet:
    """Frames that never come: each receive a short wait and a timeout, as `ZmqConsole`'s."""

    def receive(self):
        time.sleep(0.01)
        raise TimeoutError


def test_a_ctrl_c_as_a_childs_lock_is_taken_is_answered_with_it_let_go(monkeypatch, tmp_path):
    """**The demo build's CI fix, 2026-11-17**: `wlx demo` took Ctrl-C as Python's
    `KeyboardInterrupt`, raised wherever the signal landed, and one landing as `Popen.poll` took a
    child's waitpid lock left it held: that child's stop then timed out twice and `wlx demo` ended
    1, its folder left, as the Ctrl-C tests above ended on CI under load. **A Ctrl-C is counted, and
    answered at the start of a wait's pass** (`_Demo.ctrl_c`, `_Demo.interrupted`): here one comes
    as the watch loop polls a child, and the watch ends on it with the lock let go, the child then
    stopped as Ctrl-C stops it, and the handler before it back once the demo lets Ctrl-C go."""
    from wl_xcon import demo as demo_module
    from wl_xcon.actor import Box

    # A stand-in child: stopped as `wlx demo`'s children are, SIGTERM taken as Ctrl-C, 130.
    monkeypatch.setattr(demo_module, "_CHILD", (
        "import signal, sys, time\n"
        "signal.signal(signal.SIGTERM, lambda *_: sys.exit(130))\n"
        "print('ready', flush=True)\n"
        "time.sleep(600)\n"))
    folder = tmp_path / "wlx-demo-x"
    folder.mkdir()
    lock = os.open(tmp_path / "rig.lock", os.O_RDWR | os.O_CREAT)
    try:
        made = demo_module._Demo(folder, lock, Box("t"))
        child = made._child("a child", [], dict(os.environ))
        made.frames = _Quiet()
        taken = _CtrlCAsTaken(child.process._waitpid_lock)
        before = signal.getsignal(signal.SIGINT)
        try:
            with made.taking_ctrl_c():
                child.line(re.compile("^ready$"), PATIENCE_S, made.interrupted)
                child.process._waitpid_lock = taken
                # A pass is a hundredth of a second here: ten seconds is a Ctrl-C never answered.
                with pytest.raises(KeyboardInterrupt):
                    made.frame(lambda frame: False, "frame", within_s=10.0)
                assert not taken.armed, "no Ctrl-C came as the lock was taken"
                assert not taken.real.locked(), "the Ctrl-C left the child's waitpid lock held"
            assert signal.getsignal(signal.SIGINT) is before
        finally:
            # Disarmed, and let go if it was left held, so the stop below says how it ended.
            child.process._waitpid_lock = taken.real
            if taken.real.locked():
                taken.real.release()
            child.stop()
        assert child.process.returncode == 130, child.how_it_ended()
    finally:
        os.close(lock)


# --- Refused -------------------------------------------------------------------------------------


def test_it_is_refused_beside_a_running_rig_service(wlx, tmp_path):
    """§5 item 3, §7: a rig service, `wlx taskd` without `--demo`, holds the rig lock for its life,
    and `wlx demo` beside it is refused before anything starts, saying why; once it has gone a
    demo starts."""
    service, _ = _rig_service(wlx, tmp_path)
    service.line(re.compile(r"^wlx taskd: publishing on "))
    demo = wlx.demo(str(_popout()), "--no-browser")
    assert demo.ended() == 1, demo.said()
    assert demo.err[-1].startswith("refused: a rig service runs on this computer"), demo.said()
    assert not any(map(_STARTED.match, demo.out)) and wlx.folders() == []
    service.ctrl_c()
    assert service.ended() == 130, service.said()
    assert wlx.lock_free()


def _ten_inputs(folder: Path) -> Path:
    """The reference task waiting on ten levers as it waits for fixation: more inputs than a demo
    has number keys (`tests/test_demo_service.py`'s)."""
    text = (ROOT / "tasks" / "fixation_detection.py").read_text()
    old = '                On(Entered("fix"), "hold_fix"),\n'
    assert text.count(old) == 1
    levers = "".join(f'                On(Pressed("lever{n}"), Outcome.NO_FIXATION),\n'
                     for n in range(1, 11))
    path = folder / "ten_inputs.py"
    path.write_text(text.replace(old, old + levers).replace("    P,\n", "    P,\n    Pressed,\n", 1))
    return path


def _off_the_field(folder: Path) -> Path:
    """The reference task whose target starts 80° out, past any field a rig shows (its range, which
    reached 80° here, is gone; an open side is judged at its start)."""
    text = (ROOT / "tasks" / "fixation_detection.py").read_text()
    old = 'Param("target_x", unit="deg", start=10.0)'
    assert text.count(old) == 1
    path = folder / "off_the_field.py"
    path.write_text(text.replace(old, old.replace("start=10.0", "start=80.0")))
    return path


@pytest.mark.parametrize(("made", "refusing"), [
    (_ten_inputs, "refused  demo inputs"),
    (_off_the_field, "refused  stimulus-off-screen"),
], ids=["ten inputs", "off the field"])
def test_a_task_that_fails_its_checks_starts_nothing(wlx, tmp_path, made, refusing):
    """§5 item 2, §7: the task is checked first, as `wlx check` checks it against the demo's field
    (the stand-ins on this checkout's unmeasured rig) and for keys enough for its inputs; a refusal
    is printed with its sentence and nothing starts -- no folder, no child, no lock."""
    tasks = tmp_path / "tasks"
    tasks.mkdir()
    demo = wlx.demo(str(made(tasks)), "--no-browser")
    assert demo.ended() == 1, demo.said()
    assert any(line.startswith(refusing) for line in demo.out), demo.said()
    assert demo.err[-1].startswith("task refused in a training session, nothing started")
    assert not any(map(_STARTED.match, demo.out)) and wlx.folders() == [] and wlx.lock_free()


# --- A child that dies ---------------------------------------------------------------------------


@pytest.mark.parametrize("dies", ["wlx taskd --demo", "wlx serve"])
def test_a_child_that_dies_ends_the_other_and_says_which(wlx, dies):
    """§5 item 6, §7: a child that dies ends the other and the command, naming which and how it
    ended; the folder is deleted. With the rig service still there, the session is ended first,
    its return recorded."""
    demo = wlx.demo(str(_popout()), "--no-browser")
    started = _started(demo)
    children = wlx.children(demo)
    os.kill(children[dies], signal.SIGKILL)
    assert demo.ended() == 1, demo.said()
    assert f"wlx demo: {dies} ended (killed by signal 9 (SIGKILL))" in demo.err, demo.said()
    (other,) = set(children) - {dies}
    assert not _alive(children[other]), f"{other} was left running"
    assert not started["folder"].exists() and wlx.lock_free()
    recorded = f"wlx demo: session {started['session']} ended, its return recorded now"
    assert (recorded in demo.out) == (dies == "wlx serve"), demo.said()


# --- After a demo --------------------------------------------------------------------------------


@pytest.mark.parametrize("ended", ["ctrl-c", "killed outright"])
def test_a_rig_service_started_after_a_demo_finds_nothing_of_it(wlx, tmp_path, ended):
    """§9, Review Focus 7: a rig service started after a demo finds nothing of it, ended or killed
    outright and stranded: nothing stranded in its folders, which the demo never touched, and the
    rig lock free once the demo's processes have gone. Killed outright, the demo's children stop
    themselves, and its folder stays in the temporary folder, outside any rig's data (§7)."""
    demo = wlx.demo(str(_popout()), "--no-browser")
    started = _started(demo)
    children = wlx.children(demo)
    if ended == "ctrl-c":
        demo.ctrl_c()
        assert demo.ended() == 130, demo.said()
    else:
        demo.process.kill()
        demo.ended()
    assert all(_gone(pid) for pid in children.values()), "a child outlived wlx demo"

    service, folders = _rig_service(wlx, tmp_path, demo_root=True)
    service.line(re.compile(r"^wlx taskd: publishing on "))
    service.ctrl_c()
    assert service.ended() == 130, service.said()
    assert not any("stranded" in line for line in service.out + service.err), service.said()
    assert list(folders["root"].iterdir()) == [] and list(folders["demos"].iterdir()) == []
    if ended == "ctrl-c":
        assert wlx.folders() == []
    else:
        (left,) = wlx.folders()
        assert left == started["folder"]
        xcon = left / "demo" / "sessions" / started["session"] / "xcon"
        assert "return not recorded" in _kinds(xcon), "the rig service ended by its own path"


# --- The rig lock --------------------------------------------------------------------------------


def _taskd_args(tmp_path: Path, *, demo: bool) -> list[str]:
    """`wlx taskd`'s arguments: a demo service's, or a rig service's with `REFERENCE` alone."""
    common = ["taskd", "--rig", RIG_FILE, "--tasks", "tasks", "--allocation", "tasks/allocation.py"]
    if demo:
        return [*common, "--demo", str(tmp_path / "demo"), "--link",
                ",".join(["tcp://127.0.0.1:0"] * 4)]
    (tmp_path / "subjects" / "REFERENCE").mkdir(parents=True)
    shutil.copy(ROOT / "tasks" / "eight_hour_bounds.py",
                tmp_path / "subjects" / "REFERENCE" / "bounds.py")
    (tmp_path / "root").mkdir()
    return [*common, "--subjects", str(tmp_path / "subjects"), "--root", str(tmp_path / "root"),
            "--link", "tcp://127.0.0.1:0,tcp://127.0.0.1:0"]


def test_the_rig_lock_is_in_the_temporary_folder_unless_named(monkeypatch, tmp_path):
    """`service.RIG_LOCK` is this computer's, in the temporary folder; `WLX_RIG_LOCK` names
    another, for tests; and the two ways of holding it, shared and exclusive, exclude each other
    and not themselves."""
    import tempfile

    from wl_xcon import service

    assert service.RIG_LOCK == Path(tempfile.gettempdir()) / "wlx-taskd.lock"
    monkeypatch.delenv("WLX_RIG_LOCK")
    assert service.rig_lock() == service.RIG_LOCK
    monkeypatch.setenv("WLX_RIG_LOCK", str(tmp_path / "named.lock"))
    assert service.rig_lock() == tmp_path / "named.lock"
    shared = [service.lock_rig(exclusive=False) for _ in range(2)]
    assert None not in shared, "two rig services hold it together"
    assert service.lock_rig(exclusive=True) is None, "a demo is refused beside them"
    for held in shared:
        os.close(held)
    demo = service.lock_rig(exclusive=True)
    assert demo is not None
    assert service.lock_rig(exclusive=False) is None and service.lock_rig(exclusive=True) is None
    os.close(demo)


@pytest.mark.parametrize("demo", [False, True], ids=["rig service", "demo service"])
def test_a_rig_service_holds_the_rig_lock_for_its_life_and_a_demo_service_never(
        monkeypatch, tmp_path, demo):
    """Every `wlx taskd` without `--demo` holds the rig lock, shared, while it serves, so a `wlx
    demo` is refused beside it, and lets it go as it ends; a demo service takes none, its `wlx demo`
    holding it."""
    from wl_xcon import service
    from wl_xcon.cli import main

    monkeypatch.setenv("WLX_RIG_LOCK", str(tmp_path / "rig.lock"))
    seen = []

    def serve(self, stop):
        free = service.lock_rig(exclusive=True)
        seen.append(free is not None)
        if free is not None:
            os.close(free)
        raise KeyboardInterrupt

    monkeypatch.setattr(service.Service, "serve", serve)
    assert main(_taskd_args(tmp_path, demo=demo)) == 130
    assert seen == [demo]
    after = service.lock_rig(exclusive=True)
    assert after is not None, "the lock outlived the service"
    os.close(after)


def test_a_rig_service_started_while_a_demo_runs_says_so_and_waits_for_it(
        monkeypatch, tmp_path, capsys):
    """A rig service started while `wlx demo` holds the rig lock says so, and serves only once the
    demo has let it go: its frames never share the processor with a demo's drawing."""
    from wl_xcon import service
    from wl_xcon.cli import main

    monkeypatch.setenv("WLX_RIG_LOCK", str(tmp_path / "rig.lock"))
    demo = service.lock_rig(exclusive=True)
    served = threading.Event()

    def serve(self, stop):
        served.set()
        raise KeyboardInterrupt

    monkeypatch.setattr(service.Service, "serve", serve)
    ended: list = []
    runner = threading.Thread(target=lambda: ended.append(main(_taskd_args(tmp_path, demo=False))),
                              daemon=True)
    runner.start()
    time.sleep(1.0)
    assert not served.is_set(), "it served beside the demo"
    os.close(demo)
    runner.join(PATIENCE_S)
    assert served.is_set() and ended == [130]
    assert (f"wlx taskd: a demo runs on this computer (wlx demo holds {tmp_path / 'rig.lock'}); "
            f"this rig service starts once it ends") in capsys.readouterr().err
