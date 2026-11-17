"""Demo mode's two `Service._open` changes (its design §8; its plan's Task 5), welfare-listed and
approved by the PI on 2026-11-07, asked in the UI: "Approve both and the design".

1. **A demo is refused for any animal but `REFERENCE`, before anything is written**: no question
   posed, nothing marked, no folder made, the id free.
2. **A demo session gets the simulated card and pump, and on an unmeasured rig the stand-in field,
   whatever the service was built with**, decided in `_open` and passed to `_build`, so no demo can
   open a real valve; a live open is today's, on the service's own.

And the path, not the piece (CLAUDE.md): a demo opened from a live rig's own page is opened,
checked, run and ended through `_open`, `_start` and `_end`, its run the pop-out search steered
through `link.Simulated`'s gaze channel, every limit its animal's eight-hour file's. The tests drive
`Service.step` over an in-process link with an injected wall and an injected pace clock, so nothing
sleeps (as `tests/test_demo_service.py` does).
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import pytest

from _rig import PATH as RIG_FILE
from _rig import RIG
from _sessions import OPEN_ACCEPTED, WALL, typed
from wl_xcon import dio, pointer
from wl_xcon.actor import Box
from wl_xcon.cli import _load_allocation, _load_rig
from wl_xcon.geometry import stand_in_housings
from wl_xcon.link import (
    CheckRun, Drawn, EndSession, Idle, ManualReward, OpenSession, Simulated, StartRun, Stop,
    Telemetry,
)
from wl_xcon.service import Service, demo_folder
from wl_xcon.welfare import Simulated as SimulatedPump

ROOT = Path(__file__).resolve().parents[1]
ALLOCATION = "tasks/allocation.py"
EIGHT_HOURS = Path("tasks/eight_hour_bounds.py")
TASK = "fixation_detection.py"
BY = Box("jake")
#: This rig's own settings, whose housings are unmeasured, so its direct view refuses to exist.
UNMEASURED = Path("tasks/rig.py")
#: The session a test opens, and the demo beside it.
SESSION, DEMO = "2027-01-14_01", "demo-20270114-1200"
#: **Change 1's sentence**, word for word.
FOR_REFERENCE_ALONE = (
    "a demo is for the test monkey, REFERENCE, alone: nothing simulated may enter another "
    "animal's records. Nothing was recorded"
)
#: `tasks/eight_hour_bounds.py`'s: its `reward_correct` (mL), and its out-of-cage ceiling (s).
REWARD_ML, EIGHT_HOURS_S = 0.05, 28_800.0
#: The manual reward's event code (`tasks/allocation.py`'s `MANUAL_REWARD`).
MANUAL_REWARD = 4134
#: Where a wl-xtasks checkout is looked for, as `tests/test_popout_search.py` looks.
_XTASKS = next((c for c in (ROOT / "wl-xtasks", ROOT.parent / "wl-xtasks")
                if (c / "tasks" / "popout_search.py").is_file()), None)


class _Wall:
    """The service's wall: `WALL`."""

    def __call__(self) -> float:
        return WALL


class _Pace:
    """**A demo's wall clock, injected** (`Service(pace_clock=..., pace_sleep=...)`): its sleep
    moves it on, so nothing sleeps."""

    def __init__(self) -> None:
        self.t = 1_000.0

    def clock(self) -> float:
        return self.t

    def sleep(self, seconds: float) -> None:
        self.t += seconds


def _folders(tmp_path, animals=("M1", "REFERENCE"), tasks=None):
    """`--subjects`, `--tasks` and `--root` for a live rig service holding `animals`, each the
    eight-hour file renamed for it, `REFERENCE` with its settings; the tasks `tasks`, or one."""
    subjects, root = tmp_path / "subjects", tmp_path / "sessions"
    for animal in animals:
        (subjects / animal).mkdir(parents=True)
        (subjects / animal / "bounds.py").write_text(
            EIGHT_HOURS.read_text().replace('subject="REFERENCE"', f'subject="{animal}"'))
    shutil.copy("tasks/reference_subject.py", subjects / "REFERENCE" / "settings.py")
    if tasks is None:
        tasks = tmp_path / "tasks"
        tasks.mkdir()
        shutil.copy(f"tasks/{TASK}", tasks / TASK)
    root.mkdir()
    return subjects, tasks, root


def _made(folders, *, link=None, rig=RIG, rig_path=RIG_FILE, pace=None, **over) -> Service:
    """A plain `Service`: `_open`'s own demo path, no stand-in for it."""
    subjects, tasks, root = folders
    pace = pace if pace is not None else _Pace()
    return Service(
        rig=rig, rig_path=rig_path, subjects=subjects, tasks=tasks,
        allocation=_load_allocation(Path(ALLOCATION)), allocation_path=ALLOCATION,
        root=root, link=link if link is not None else Simulated(), seed=lambda: 7,
        wall_clock=_Wall(), pace_clock=pace.clock, pace_sleep=pace.sleep, **over,
    )


def _rig_service(tmp_path, *, demo_root=True, animals=("M1", "REFERENCE"), tasks=None,
                 **over) -> Service:
    """A live rig service that offers demos: a gaze endpoint (`Simulated`'s) and, with
    `demo_root`, a demo folder of its own beside `--root`."""
    root = tmp_path / "demos" if demo_root else None
    return _made(_folders(tmp_path, animals, tasks), demo_root=root, **over)


def _open(**over) -> OpenSession:
    fields = dict(
        by=BY, session_id=SESSION, animal="REFERENCE", deployment="rig_fixed", view="direct",
        session_kind="training", departure=typed(60), delivered_today=0.0, answer=None,
        amend_to=None, amend_reason="", accepted=OPEN_ACCEPTED,
    )
    fields.update(over)
    return OpenSession(**fields)


def _demo(**over) -> OpenSession:
    return _open(**{"session_id": DEMO, "demo": True, **over})


def _end(session_id=None, returned="now") -> EndSession:
    return EndSession(by=BY, session_id=session_id, returned=returned, confirm=False)


def _step(service, *commands):
    """One housekeeping pass with `commands` waiting; the last frame it published."""
    for command in commands:
        service.link.queue(command)
    service.step()
    return service.link.published[-1]


def _refused(frame) -> list[str]:
    return [refusal.why for refusal in frame.refusals]


def _xcon(root: Path, session_id: str) -> Path:
    return root / session_id / "xcon"


def _config(root: Path, session_id: str) -> dict:
    return json.loads((_xcon(root, session_id) / "config.json").read_text())


def _kinds(root: Path, session_id: str) -> list[str]:
    path = _xcon(root, session_id) / "welfare_notes.jsonl"
    if not path.exists():
        return []
    return [json.loads(line)["kind"] for line in path.read_text().splitlines()]


def _marked(tmp_path) -> list[Path]:
    """Every welfare record under `tmp_path`: a departure marked anywhere writes one."""
    return sorted(tmp_path.rglob("welfare_notes.jsonl"))


def _pump_item(service, task: str = TASK):
    """The pump calibration's pre-flight item, as a check of `task` takes it now."""
    checked = _step(service, CheckRun(by=BY, task=task, values={})).preflight
    (item,) = [item for item in checked.items if item.name == "pump calibration"]
    return item


def _recording():
    """**A rig built with its own card and pump, stood in for**: a card class keeping each one made,
    and a pump that is no `welfare.Simulated` -- a real valve's driver as the pre-flight reads one
    -- keeping each made and every volume it is asked for. A demo must reach neither."""
    cards: list = []
    valves: list = []

    class _RigCard(dio.Simulated):
        def __init__(self, *args, **kwargs) -> None:
            super().__init__(*args, **kwargs)
            cards.append(self)

    class _Valve:
        def __init__(self) -> None:
            self.delivered: list = []
            valves.append(self)

        def deliver(self, ml: float) -> None:
            self.delivered.append(ml)

    return _RigCard, _Valve, cards, valves


# --- Change 1: a demo is for REFERENCE alone -----------------------------------------------------


def test_a_demo_is_refused_for_any_animal_but_reference_before_anything_is_written(tmp_path):
    """§8, change 1; Review Focus 1: on a live rig service holding `M1` and `REFERENCE`, a demo
    for `M1` is refused saying so, **before anything is written**: no folder under either root,
    no departure marked, no question posed, the id free. A far departure for `M1` sent as a demo,
    which a live open would ask confirm-or-amend of, is refused by this and never asked; so is one
    answered *confirm* with no question posed, which `_unasked` would otherwise refuse. It comes
    after the open-session and stranded refusals and ahead of the build, so a rig with no demo
    folder says this, not its own refusal."""
    service = _rig_service(tmp_path)
    far = typed(3 * 3600)
    for sent in (_demo(animal="M1"), _demo(animal="M1", departure=far),
                 _demo(animal="M1", departure=far, answer="confirm")):
        frame = _step(service, sent)
        assert isinstance(frame, Idle) and frame.question is None
        assert _refused(frame)[-1] == FOR_REFERENCE_ALONE
        assert service.session is None and service.question is None
    assert _refused(frame) == [FOR_REFERENCE_ALONE] * 3
    assert list(service.root.iterdir()) == [] and not service.demo_root.exists()
    assert _marked(tmp_path) == []

    bare = _rig_service(tmp_path / "bare", demo_root=False)
    assert _refused(_step(bare, _demo(animal="M1")))[-1] == FOR_REFERENCE_ALONE

    # The id is free: the same id opens a demo for REFERENCE, and while it is open a demo for M1
    # is refused as any open is, the open session's refusal first.
    opened = _step(service, _demo())
    assert isinstance(opened, Telemetry) and opened.demo is True and opened.session_id == DEMO
    assert _refused(_step(service, _demo(animal="M1", session_id="demo-2")))[-1].startswith(
        "a session is open for 'REFERENCE'")
    _step(service, _end())
    # And a live open for M1 is today's: its far departure is asked, never refused by this.
    asked = _step(service, _open(animal="M1", departure=far))
    assert isinstance(asked, Idle) and asked.question is not None
    assert asked.question.mark == "departure" and FOR_REFERENCE_ALONE not in _refused(asked)
    live = _step(service, _open(animal="M1", departure=far, answer="confirm"))
    assert isinstance(live, Telemetry) and live.demo is False
    assert _kinds(service.root, SESSION)[:3] == ["departure", "departure confirmed",
                                                 "session opened"]


def test_a_live_open_for_reference_is_unchanged(tmp_path):
    """§8: an open that is not a demo goes today's path, for `REFERENCE` too: under `--root`, on
    the card and the pump the service was built with, no `demo` in its record or its frames, and
    nothing in the demo folder."""
    card, valve, cards, valves = _recording()
    service = _rig_service(tmp_path, card=card, pump=valve)
    opened = _step(service, _open())
    assert isinstance(opened, Telemetry) and opened.demo is False
    session = service.session
    assert session.spec.demo is None
    assert cards == [session.card] and valves == [session.pump], "the service's own"
    assert "demo" not in _config(service.root, SESSION)
    assert sorted(p.name for p in service.root.iterdir()) == [SESSION]
    assert not service.demo_root.exists()
    assert _kinds(service.root, SESSION)[:2] == ["departure", "session opened"]


# --- Change 2: the simulators, and the stand-in field --------------------------------------------


def test_a_demo_session_gets_the_simulated_card_and_pump_whatever_the_service_was_built_with(
    tmp_path,
):
    """§8, change 2; Review Focus 1: a rig service built with its own card and a real valve's
    pump driver opens a demo on `dio.Simulated` and `welfare.Simulated`, never making either of its
    own; a reward given in the demo is counted on the simulator, as any session's is, and the
    valve is never asked for a drop; its pre-flight reads the simulator's pump. A live open after
    it is on the rig's own, its reward on the valve."""
    card, valve, cards, valves = _recording()
    service = _rig_service(tmp_path, card=card, pump=valve)

    demo = _step(service, _demo())
    assert isinstance(demo, Telemetry) and demo.demo is True
    session = service.session
    assert (type(session.card), type(session.pump)) == (dio.Simulated, SimulatedPump)
    assert cards == [] and valves == [], "neither of the rig's own was made"
    given = _step(service, ManualReward(by=BY))
    assert session.pump.delivered == [REWARD_ML]
    assert given.fluid_session_ml == pytest.approx(REWARD_ML), "counted, as any session's"
    assert session.card.codes.count(MANUAL_REWARD) == 1
    assert _pump_item(service).result == "unknown", "the simulator's, acknowledgeable"
    assert cards == [] and valves == []
    _step(service, _end())

    _step(service, _open())
    live = service.session
    assert cards == [live.card] and valves == [live.pump], "a live open's are the rig's"
    _step(service, ManualReward(by=BY))
    assert live.pump.delivered == [REWARD_ML]
    assert session.pump.delivered == [REWARD_ML], "the demo's simulator untouched by it"
    assert _pump_item(service).result == "fail", "a real driver's, unmeasured"


def test_a_demo_on_an_unmeasured_rig_gets_the_stand_in_field(tmp_path):
    """§8, change 2; §3.6: on `tasks/rig.py`, whose housings are unmeasured, a demo opened on a
    live rig service takes the stand-ins in direct view, its `config.json` saying
    `stand_in_housings: true`; a live open in direct view there is refused, as `Rig.direct`
    refuses it, writing nothing."""
    rig = _load_rig(UNMEASURED)
    service = _rig_service(tmp_path, rig=rig, rig_path=str(UNMEASURED))
    opened = _step(service, _demo())
    assert isinstance(opened, Telemetry) and opened.demo is True
    assert _config(service.demo_root, DEMO)["demo"] == {
        "gaze": "mouse", "noise_deg": 0.02, "stand_in_housings": True}
    assert service.session.spec.geometry.housings == stand_in_housings(rig.panel_width_cm)
    _step(service, _end())
    live = _step(service, _open())
    assert service.session is None and "housings" in _refused(live)[-1]
    assert list(service.root.iterdir()) == []


def test_in_a_demo_service_every_open_is_a_demo(tmp_path):
    """§3.1, §8: in a demo service (`wlx taskd --demo`) every open is a demo, whatever the page
    sent, so both changes apply to each: one for another animal is refused by change 1's sentence,
    not by its missing files; one for `REFERENCE` opens as a demo on the simulators."""
    subjects, root = demo_folder(tmp_path / "demo")
    tasks = tmp_path / "tasks"
    tasks.mkdir()
    shutil.copy(f"tasks/{TASK}", tasks / TASK)
    service = _made((subjects, tasks, root), demo_service=True)

    refused = _step(service, _open(animal="M1", demo=False))
    assert _refused(refused) == [FOR_REFERENCE_ALONE] and service.session is None
    assert list(root.iterdir()) == []

    opened = _step(service, _open(demo=False))
    assert isinstance(opened, Telemetry) and opened.demo is True
    session = service.session
    assert session.spec.demo is not None and session.spec.root == root
    assert (type(session.card), type(session.pump)) == (dio.Simulated, SimulatedPump)
    assert _config(root, SESSION)["demo"]["gaze"] == "mouse"


# --- The path: open, check, run and end a demo from a live rig's page ----------------------------


class _Steering(Simulated):
    """**A page steering a demo, in process** (`link.Simulated`'s gaze channel): a report of the
    pointer every `pointer.LIVE_S / 5` on the demo's wall clock, as often as the page sends them,
    at the window the newest `Drawn` flags as the target while the array is shown, else at the
    fixation point; and a
    person's Stop once `trials` trials have ended, each ending on a blank `Drawn`. So it plays the
    pop-out as a person does, reading the drawing the rig published.

    **Two backstops, so a run that does not stop fails its test rather than hanging it** (the demo
    build's CI fix, 2026-11-17: with `Pointing.ended` neutered no blank screen came, so no Stop,
    and the run played on until the mutation sweep's limit killed it). A trial drawn past the
    `trials` this plays sends the Stop then, said in `overran`; and a run still asking for the
    pointer `PLAYED_WITHIN_S` into the demo's clock raises, said there too, a fault the service
    contains (`Service._run`), for a run whose trials never come back to a boundary. Both count
    the demo's own trials and its own clock, injected, never the wall's, so a loaded computer
    reaches neither."""

    #: Where the pointer rests while nothing is shown: outside the fixation window (2° to start)
    #: and every disc's on the 8° ring.
    REST = (0.0, -5.0)
    #: **How far the demo's clock may run while this plays**, in its seconds: far past the open
    #: and the trials this plays, which end well inside it on the same seed every time.
    PLAYED_WITHIN_S = 60.0

    def __init__(self, clock, trials: int) -> None:
        super().__init__()
        self.clock, self.trials = clock, trials
        self.drawn: Drawn | None = None
        self.ended = self.seq = 0
        self.next_at = float("-inf")
        self.until = clock() + self.PLAYED_WITHIN_S
        #: What a backstop found, as a sentence; `None` while the run stops as this plays it.
        self.overran: str | None = None

    def publish(self, telemetry) -> None:
        super().publish(telemetry)
        if isinstance(telemetry, Drawn):
            self.drawn = telemetry
            if telemetry.screen is None:
                self.ended += 1
                if self.ended == self.trials:
                    self.queue(Stop(by=BY))
            elif telemetry.trial >= self.trials and self.overran is None:
                self.overran = (
                    f"trial {telemetry.trial + 1} was drawn, though this plays {self.trials}: "
                    f"{self.ended} ended on a blank screen (`Pointing.ended`), so the Stop was "
                    f"sent only then")
                self.queue(Stop(by=BY))

    def _aim(self) -> tuple[float, float]:
        """The target's window while its object is on the screen (a window is listed whether or
        not what it belongs to is shown; an array's object `search.0` is drawn as an item of that
        name), the fixation point while it is, else `REST`, so each fixation is a move to the point
        (an eye already on it as it comes on has entered it too, since 2026-11-16: EYE-30)."""
        drawn = self.drawn
        shown = set() if drawn is None or drawn.screen is None else {
            item.name for item in drawn.screen.items}
        for window in () if drawn is None else drawn.windows:
            if window.target and window.name in shown:
                return window.x_deg, window.y_deg
        return (0.0, 0.0) if "fix" in shown else self.REST

    def gaze_into(self, buffer: bytearray) -> int:
        now = self.clock()
        if now > self.until:
            self.overran = (
                f"the run was still asking for the pointer {self.PLAYED_WITHIN_S:g} s into the "
                f"demo's clock, {self.ended} of the {self.trials} trials this plays ended on a "
                f"blank screen: it never stopped")
            raise AssertionError(self.overran)
        if not self.gazes and now >= self.next_at:
            self.next_at = now + pointer.LIVE_S / 5
            self.seq += 1
            self.gazes.append(pointer.pack(self.seq, *self._aim(), over=True, b=False,
                                           button=False, held=0, presses=(0,) * pointer.KEYS))
        return super().gaze_into(buffer)


def test_a_demo_from_a_live_rigs_page_opens_runs_and_ends_through_open_start_and_end(tmp_path):
    """**The path** (§8: "A demo session goes through `Service._open`, `_start` and `_end` exactly
    as a page's session does, and every limit runs against `REFERENCE`'s eight-hour file"): on a
    live rig service holding `M1` and `REFERENCE`, a demo opened for `REFERENCE` is checked, and
    a run of the pop-out search (read from wl-xtasks) is started at its first stage, steered by a
    page through the gaze channel, each look to the odd disc scored correct by the rig's own eye
    rules and paid on the simulated pump; a person's stop ends the run, and End records the return.
    Its out-of-cage ceiling is the eight-hour file's, its whole record is in the demo folder and
    nothing is under `--root`."""
    if _XTASKS is None:
        if os.environ.get("WLX_REQUIRE_XTASKS") == "1":  # pragma: no cover - CI's
            pytest.fail("WLX_REQUIRE_XTASKS=1 but no wl-xtasks checkout holding "
                        "tasks/popout_search.py was found")
        pytest.skip("no wl-xtasks checkout holding tasks/popout_search.py")
    trials = 3
    pace = _Pace()
    card, valve, cards, valves = _recording()
    service = _rig_service(tmp_path, tasks=_XTASKS / "tasks", link=_Steering(pace.clock, trials),
                           pace=pace, card=card, pump=valve)

    opened = _step(service, _demo())
    assert isinstance(opened, Telemetry) and opened.demo is True
    assert opened.out_of_cage_limit_s == EIGHT_HOURS_S, "the eight-hour file's ceiling"
    assert _config(service.demo_root, DEMO)["versions"]["bounds"] == str(
        service.subjects / "REFERENCE" / "bounds.py")

    run = dict(task="popout_search.py", values={}, plan="training", start_block="Alone")
    checked = _step(service, CheckRun(by=BY, **run)).preflight
    results = {item.name: item.result for item in checked.items}
    assert "fail" not in results.values(), checked
    assert results["pump calibration"] == "unknown" and results["demo inputs"] == "pass"
    unknown = tuple(name for name, result in results.items() if result == "unknown")
    _step(service, StartRun(by=BY, trials=1, acknowledged=unknown, **run))
    _step(service)
    assert service.link.overran is None, service.link.overran

    rows = [json.loads(line) for line in
            (_xcon(service.demo_root, DEMO) / "trials.jsonl").read_text().splitlines()]
    assert [row["outcome"] for row in rows] == ["correct"] * trials, rows
    session = service.session
    assert session.pump.delivered == [REWARD_ML] * trials, "each correct paid on the simulator"
    assert cards == [] and valves == []
    frames = [f for f in service.link.published if isinstance(f, Telemetry)]
    assert {f.out_of_cage_limit_s for f in frames} == {EIGHT_HOURS_S}
    assert {f.demo for f in frames} == {True}
    assert frames[-1].phase == "between_runs"

    ended = _step(service, _end())
    assert isinstance(ended, Idle) and service.session is None
    assert _kinds(service.demo_root, DEMO)[-2:] == ["returned", "session ended"]
    assert list(service.root.iterdir()) == []
