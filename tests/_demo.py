"""**Demo mode over the real ZMQ link**, for its tests (demo mode §9; its plan's Task 6): a demo
service in process, `Service(..., demo_service=True)` on a `ZmqLink` with its four endpoints, paced
on the wall clock; **a scripted pointer**, a PUSH to the gaze endpoint packing `pointer.MESSAGE`
and a SUB reading `Drawn` for where the discs are, on a thread of its own as a page's pointer is;
and **the trainer's panel**, a console's SUB and REQ, on the test's thread. The service is driven
over its four sockets, not through `wlx serve`, which cannot carry a demo until demo mode's Task 8.

**What a scripted person does** is a `Person`: told each `Drawn` the rig publishes (`seen`), asked
where the pointer is before each report (`aim`). It rests at `REST` until the fixation point is
drawn, and again once the trial's screen goes blank, so each fixation is a move to the point. (Until
2026-11-16 a pointer already on the point as it appeared never entered its window; it has entered
it since, EYE-30, and `test_demo_popout.py`'s `Centered` plays that.) A subclass says what it does
from the go on.

**Reports every `REPORT_EVERY_S`**, the pointer's position changing only on that schedule, so each
move is one report the rig's source eases over the frames since the one before (`pointer.Source`):
a flick across `REPORT_EVERY_S`, which the saccade detector sees as a saccade. **The cyclic garbage
collector is held off while a demo plays** (`Demo`): a collection of the suite's heap stops every
thread at once, the rig's frames lose the time it took, and a move reported across it reaches the
rig as a jump of a frame or two, which is no saccade. Engine test material: the wall-clock pacing
makes a scripted trial run as a person's does, and no timing claim rests on it (CLAUDE.md).

Never collected, since its name does not start with `test_`.
"""

from __future__ import annotations

import gc
import json
import math
import os
import threading
import time
from datetime import datetime
from pathlib import Path

import pytest

from _ports import endpoints
from _rig import PATH as RIG_FILE
from _rig import RIG
from _sessions import OPEN_ACCEPTED
from wl_xcon import pointer
from wl_xcon.actor import Box
from wl_xcon.cli import _load_allocation
from wl_xcon.link import (
    CheckRun, Drawn, DrawnWindow, EndSession, Idle, OpenSession, StartRun, Telemetry, ZmqConsole,
    ZmqGaze, ZmqLink,
)
from wl_xcon.service import Service, demo_folder

ROOT = Path(__file__).resolve().parents[1]
#: Where a wl-xtasks checkout is looked for, as `tests/test_popout_search.py` looks: the link at
#: this repository's root, then beside it; the first holding the pop-out is read.
XTASKS = next((c for c in (ROOT / "wl-xtasks", ROOT.parent / "wl-xtasks")
               if (c / "tasks" / "popout_search.py").is_file()), None)
ALLOCATION = "tasks/allocation.py"
POPOUT = "popout_search.py"
#: The pop-out's array, whose objects are drawn as `search.0`, `search.1` ...
ARRAY = "search"
#: The person at the box, as a page's command carries a typed name.
BY = Box("jake")
#: A demo's session id, as `wlx demo` gives one: `demo-` and the date and time.
SESSION = "demo-20261114-1200"

#: **How often the scripted pointer reports**, and so the span each move is eased over
#: (`pointer.Source`): the page's slowest interval (`web.GAZE_EVERY_MS`, 100 ms, Task 9), as
#: `tests/test_demo_open.py`'s steering page reports. A flick then spans 24 frames at the session's
#: 240 Hz, and the saccade detector needs six above its threshold
#: (`saccade.DEFAULT_MIN_DURATION_SAMPLES`), so a stall of the rig's thread of up to about 75 ms
#: before a move, which the frames lose, still leaves a saccade; at 50 ms a stall of 80 ms made two
#: go phases in ten an abort (the in-process service on an injected clock, 2026-11-14). Five to a
#: `pointer.LIVE_S`, so a late report never reads as tracker loss. The test's call, claiming
#: nothing.
REPORT_EVERY_S = 0.1
#: Where the pointer rests while it waits: outside the fixation window (2° to start) and every
#: disc's on the 8° ring.
REST = (0.0, -5.0)
FIX = (0.0, 0.0)
#: The states a pop-out trial passes through to the fixation hold, and on to the answer: since
#: the pop-out's revision the discs come on as the trial enters `delay`, which at `go_delay` 0 it
#: passes on that frame into `go` (TSK-78), the world told both began.
FIXATED_STATES = ("between", "await_fix", "hold_fix")
ANSWERED_STATES = (*FIXATED_STATES, "delay", "go", "flight")
#: How long the panel waits for a frame it expects before the test fails: well past any trial the
#: tests play, so a slow computer is never read as a fault, and a hang is.
PATIENCE_S = 30.0


def xtasks_or_skip() -> Path:
    """The wl-xtasks checkout's `tasks/` folder; a skip without one, a failure under
    `WLX_REQUIRE_XTASKS=1`, as `tests/test_popout_search.py` has them."""
    if XTASKS is None:
        if os.environ.get("WLX_REQUIRE_XTASKS") == "1":  # pragma: no cover - CI's
            pytest.fail("WLX_REQUIRE_XTASKS=1 but no wl-xtasks checkout holding "
                        "tasks/popout_search.py was found")
        pytest.skip("no wl-xtasks checkout holding tasks/popout_search.py")
    return XTASKS / "tasks"


# --- What the person does --------------------------------------------------------------------


class Person:
    """**A person with the pointer, one trial at a time**: `seen(drawn)` for each screen the rig
    publishes, from the pointer's thread, and `aim()` before each report, giving `(x, y, b)`, the
    pointer's place in degrees and whether B is held. At `REST` until the fixation point is drawn,
    then on it, and at `REST` again once the trial's screen is blank; from the go, the frame an
    array's object is first drawn, `go(drawn)` says. `since_fix` and `since_go` count the reports
    sent since each, so a script times its moves in reports."""

    def __init__(self) -> None:
        self.trial = -1
        self.go_drawn: Drawn | None = None
        self.fixating = False
        self.ended = False
        self.since_fix = self.since_go = 0
        #: Every screen seen, in order.
        self.drawn: list[Drawn] = []

    def seen(self, drawn: Drawn) -> None:
        self.drawn.append(drawn)
        if drawn.frame == 0:
            # The field before a run's first trial, drawn while that trial waits for the pointer
            # (`pointer.Drawing.field`; demo mode's Task 10): no trial has begun, so none has ended.
            return
        if drawn.trial != self.trial:
            self.trial = drawn.trial
            self.go_drawn, self.fixating, self.ended = None, False, False
            self.since_fix = self.since_go = 0
        if drawn.screen is None:
            self.ended = True
            return
        shown = shown_names(drawn)
        if "fix" in shown:
            self.fixating = True
        if self.go_drawn is None and any(discs(drawn)):
            self.go_drawn = drawn

    def aim(self) -> tuple[float, float, bool]:
        if self.ended or not self.fixating:
            return (*REST, False)
        if self.go_drawn is None:
            self.since_fix += 1
            return self.holding()
        self.since_go += 1
        return self.go(self.go_drawn)

    def holding(self) -> tuple[float, float, bool]:
        """While the fixation point is up: on it."""
        return (*FIX, False)

    def go(self, drawn: Drawn) -> tuple[float, float, bool]:
        """From the go: where the pointer is, `drawn` the screen the discs came on in."""
        raise NotImplementedError

    def next_in(self) -> "float | None":
        """**How long after the report just sent the next one goes**, in seconds, timed from
        when it was sent; `None`, the schedule's, every `REPORT_EVERY_S`: for a script that must
        time a move finer than the schedule (`test_demo_popout.py`'s second look)."""
        return None


def shown_names(drawn: Drawn) -> set[str]:
    """What `drawn` shows, by item name: an array's object `search.0` is drawn as an item of that
    name, and a window is listed whether or not what it belongs to is shown."""
    return set() if drawn.screen is None else {item.name for item in drawn.screen.items}


def discs(drawn: Drawn) -> tuple[DrawnWindow | None, list[DrawnWindow]]:
    """**The shown discs' windows, where the trial placed them**: the odd one's, the one the drawing
    flags as the target, or `None` with none shown; and the distractors'."""
    shown = shown_names(drawn)
    placed = [w for w in drawn.windows if w.name in shown and w.name.startswith(ARRAY + ".")]
    odd = [w for w in placed if w.target]
    return (odd[0] if odd else None), [w for w in placed if not w.target]


def target(drawn: Drawn) -> tuple[float, float]:
    """Where the odd disc is; where the fixation point was, for a person who sees none."""
    odd, _ = discs(drawn)
    return FIX if odd is None else (odd.x_deg, odd.y_deg)


def distractor(drawn: Drawn) -> tuple[float, float]:
    """Where the first distractor is; where the fixation point was, for a person who sees none."""
    _, others = discs(drawn)
    return FIX if not others else (others[0].x_deg, others[0].y_deg)


def toward_target(drawn: Drawn, eccentricity_deg: float) -> tuple[float, float]:
    """The place `eccentricity_deg` from the fixation point on the line to the odd disc; where the
    fixation point was, for a person who sees none."""
    x, y = target(drawn)
    if (x, y) == FIX:
        return FIX
    scale = eccentricity_deg / math.hypot(x, y)
    return x * scale, y * scale


def empty_space(drawn: Drawn, eccentricity_deg: float = 5.0) -> tuple[float, float]:
    """**A place no disc is**: of the directions a degree apart at `eccentricity_deg`, the one
    farthest from every shown window, which must leave it outside each by a degree."""
    shown = [w for w in drawn.windows if w.name in shown_names(drawn)]
    best, clear = None, -math.inf
    for step in range(360):
        angle = math.radians(step)
        x, y = eccentricity_deg * math.cos(angle), eccentricity_deg * math.sin(angle)
        margin = min(math.hypot(x - w.x_deg, y - w.y_deg) - w.radius_deg for w in shown)
        if margin > clear:
            best, clear = (x, y), margin
    assert clear > 1.0, f"no empty place at {eccentricity_deg}°: {shown}"
    return best


# --- The pointer, the panel, and the service --------------------------------------------------


class Pointer:
    """**The scripted pointer** (the page's, in a test): on a thread of its own, a report every
    `REPORT_EVERY_S` through a `ZmqGaze` (the PUSH `wlx serve` sends with), packed as
    `pointer.MESSAGE`, over the drawing, at `person.aim()`; and a read-only console's SUB, each
    `Drawn` on it given to `person.seen`. Built on the test's thread, so the suite's teardown holds
    its sockets (`register`); used only on its own once started. A fault on it is raised by
    `close`."""

    def __init__(self, person: Person, gaze_endpoint: str, pub_endpoint: str, register) -> None:
        self.person = person
        self._gaze = register(ZmqGaze(gaze_endpoint))
        self._drawn = register(ZmqConsole(pub_endpoint, None, settle_s=0.0,
                                          receive_timeout_s=0.005))
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="scripted pointer", daemon=True)
        self.fault: BaseException | None = None
        #: Reports sent, and those the PUSH could not hand over (no rig connected; a connected
        #: one's socket keeps the newest and refuses none, `link.ZmqGaze`).
        self.sent = self.refused = 0

    def start(self) -> None:
        self._thread.start()

    def _run(self) -> None:
        seq = 0
        due = time.perf_counter()
        presses = (0,) * pointer.KEYS
        try:
            while not self._stop.is_set():
                if time.perf_counter() >= due:
                    x, y, b = self.person.aim()
                    seq += 1
                    report = pointer.pack(seq, x, y, over=True, b=b, button=False, held=0,
                                          presses=presses)
                    if self._gaze.send(report):
                        self.sent += 1
                    else:
                        self.refused += 1
                    wait = self.person.next_in()
                    due = (time.perf_counter() + wait if wait is not None
                           else max(due + REPORT_EVERY_S, time.perf_counter()))
                try:
                    frame = self._drawn.receive()
                except TimeoutError:
                    continue
                if isinstance(frame, Drawn):
                    self.person.seen(frame)
        except BaseException as fault:  # noqa: BLE001 -- raised on the test's thread by `close`
            self.fault = fault

    def close(self) -> None:
        self._stop.set()
        self._thread.join(5.0)
        self._gaze.close()
        self._drawn.close()
        if self.fault is not None:
            raise AssertionError("the scripted pointer's thread failed") from self.fault


class Demo:
    """**A demo service in process, over the real link** (`wlx taskd --demo DIR`'s, built as
    `service.run` builds one): its folder under `tmp_path`, the pop-out's checkout its `--tasks`,
    `Service.serve` on a thread of its own; the trainer's panel on the test's thread, and the
    scripted pointer, `person`'s -- none with `person` `None`, where a page in a real browser is
    the pointer (`tests/test_page_browser.py`, demo mode's Task 9). `register` is the suite's
    `zmq_cleanup`, so every socket is released when the test returns, pass or fail."""

    def __init__(self, tmp_path: Path, person: Person | None, register) -> None:
        tasks = xtasks_or_skip()
        pub, rep, mark, gaze = endpoints(4)
        self.link = register(ZmqLink(pub, rep, mark, gaze))
        subjects, self.root = demo_folder(tmp_path / "demo")
        self.service = Service(
            rig=RIG, rig_path=RIG_FILE, subjects=subjects, tasks=tasks,
            allocation=_load_allocation(Path(ALLOCATION)), allocation_path=ALLOCATION,
            root=self.root, link=self.link, demo_service=True,
        )
        self._stop = threading.Event()
        self._serving = threading.Thread(target=self.service.serve, args=(self._stop,),
                                         name="wlx taskd --demo", daemon=True)
        self.panel = register(ZmqConsole(self.link.pub_endpoint, self.link.rep_endpoint))
        self.pointer = None if person is None else Pointer(
            person, self.link.gaze_endpoint, self.link.pub_endpoint, register)
        #: Every frame the panel has read, in order.
        self.frames: list = []

    def __enter__(self) -> "Demo":
        # The module docstring: no collection while a demo plays, one before it.
        self._collecting = gc.isenabled()
        gc.collect()
        gc.disable()
        self._serving.start()
        if self.pointer is not None:
            self.pointer.start()
        return self

    def __exit__(self, kind, *_) -> None:
        """The pointer stopped, then the service, between passes: within a housekeeping wait on
        the way a test ends, and given a moment where a test failed, a run perhaps still going,
        which the suite's teardown then ends by releasing its sockets."""
        try:
            if self.pointer is not None:
                self.pointer.close()
            self._stop.set()
            self._serving.join(PATIENCE_S if kind is None else 1.0)
            self.panel.close()
            self.link.close()
        finally:
            if self._collecting:
                gc.enable()

    # --- The panel ------------------------------------------------------------------------------

    def first(self, wanted, within_s: float):
        """**The first frame the panel reads that is `wanted`**, or `None` if none comes within
        `within_s`; each frame read kept in `frames`."""
        deadline = time.monotonic() + within_s
        while time.monotonic() < deadline:
            try:
                frame = self.panel.receive()
            except TimeoutError:
                continue
            self.frames.append(frame)
            if wanted(frame):
                return frame
        return None

    def until(self, wanted, what: str):
        """`first`, or the test fails saying `what` it waited for, if none comes within
        `PATIENCE_S`."""
        frame = self.first(wanted, PATIENCE_S)
        if frame is None:
            raise AssertionError(f"no {what} within {PATIENCE_S} s")
        return frame

    def send(self, command) -> None:
        self.panel.send(command)

    def open(self) -> Telemetry:
        """Open the demo's session for `REFERENCE`, left the cage a minute ago, accepting the open's
        warnings, as the page's New session sends it; its first frame."""
        self.until(lambda f: isinstance(f, Idle), "idle frame")
        departure = datetime.fromtimestamp(time.time() - 60).astimezone().isoformat(
            timespec="seconds")
        self.send(OpenSession(
            by=BY, session_id=SESSION, animal="REFERENCE", deployment="rig_fixed",
            view="direct", session_kind="training", departure=departure, delivered_today=0.0,
            answer=None, amend_to=None, amend_reason="", accepted=OPEN_ACCEPTED,
        ))
        opened = self.until(lambda f: isinstance(f, Telemetry) or (isinstance(f, Idle)
                                                                    and f.refusals), "open")
        assert isinstance(opened, Telemetry), [r.why for r in opened.refusals]
        return opened

    def start(self, values: dict, *, plan: str | None = None, start_block: str | None = None,
              trials: int = 1) -> None:
        """Check a run of the pop-out, then start it acknowledging each unknown by name, as a
        person does on the page; once its first trial is under way, as its first screen says."""
        run = dict(task=POPOUT, values=values, plan=plan, start_block=start_block)
        self.send(CheckRun(by=BY, **run))
        checked = self.until(lambda f: isinstance(f, Telemetry) and f.preflight is not None,
                             "pre-flight").preflight
        results = {item.name: item.result for item in checked.items}
        assert "fail" not in results.values(), checked
        unknown = tuple(name for name, result in results.items() if result == "unknown")
        self.send(StartRun(by=BY, trials=trials, acknowledged=unknown, **run))
        self.until(lambda f: isinstance(f, Drawn), "first screen")

    def ended_run(self) -> Telemetry:
        """The frame the run ends on: the session back between runs."""
        return self.until(lambda f: isinstance(f, Telemetry) and f.phase == "between_runs",
                          "run's end")

    def end(self) -> Idle:
        """End the session with its return now; the idle frame after it."""
        self.send(EndSession(by=BY, session_id=None, returned="now", confirm=False))
        return self.until(lambda f: isinstance(f, Idle), "idle frame after End")

    # --- The record -----------------------------------------------------------------------------

    @property
    def record(self) -> Path:
        return self.root / SESSION / "xcon"

    def rows(self, name: str) -> list[dict]:
        path = self.record / name
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []
