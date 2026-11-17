"""Demo mode's service (its design §3.1, §3.2, §3.6, §3.7; its plan's Task 4): `wlx taskd --demo`,
its folder and its one animal, the simulators, the stand-in field, the record, `Session.run_world`,
a demo never resumed, and a rig's own demo folder (`--demo-root`; the PI, 2026-11-14, "A demo
folder of its own").

**`_open`'s demo path is demo mode's Task 5** (welfare-listed, its two approved changes, held in
`tests/test_demo_open.py`): the tests here open each demo through a plain `Service`'s own `_open`,
and drive the rest of its path -- check, start, end -- through it. The unit tests drive
`Service.step` over an in-process link with an injected wall and an injected pace clock, so nothing
sleeps; the `wlx taskd` tests bind a real link on loopback.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from _rig import PATH as RIG_FILE
from _rig import RIG
from _sessions import OPEN_ACCEPTED, WALL, typed
from _zmq_release import _every_zmq_context_released  # noqa: F401
from wl_xcon import cli, dio, health, pointer, stranded
from wl_xcon import service as service_module
from wl_xcon import taskd as taskd_module
from wl_xcon.actor import Box
from wl_xcon.cli import _load_allocation, _load_rig, main
from wl_xcon.geometry import stand_in_housings
from wl_xcon.link import (
    CheckRun, Drawn, EndSession, Idle, OpenSession, ResumeSession, Simulated, StartRun, Stop,
    Telemetry,
)
from wl_xcon.record import welfare_note
from wl_xcon.service import DEMO_UNRESUMED, Service, demo_folder
from wl_xcon.welfare import Simulated as SimulatedPump

ALLOCATION = "tasks/allocation.py"
EIGHT_HOURS = Path("tasks/eight_hour_bounds.py")
TASK = "fixation_detection.py"
BY = Box("jake")
VALUES = {
    "fix_acquisition": 4.0, "fix_hold": 0.3, "response_deadline": 0.6, "target_hold": 0.2,
    "fix_window": 2.0, "target_window": 3.0, "target_x": 10.0,
}
UNKNOWN = ("warnings", "pump calibration", "eye tracker")
#: This rig's own settings, whose housings are unmeasured, so its direct view refuses to exist.
UNMEASURED = Path("tasks/rig.py")
FOUR = ",".join(["tcp://127.0.0.1:0"] * 4)
#: The session a test opens, and the demo beside it.
SESSION, DEMO = "2027-01-14_01", "demo-20270114-1200"


class _Wall:
    """The service's wall, moved by a test: `WALL` until then."""

    def __init__(self) -> None:
        self.at = WALL

    def __call__(self) -> float:
        return self.at


class _Pace:
    """**A demo's wall clock, injected** (`Service(pace_clock=..., pace_sleep=...)`): its sleep
    moves it on and is kept, so nothing sleeps."""

    def __init__(self) -> None:
        self.t = 1_000.0
        self.slept: list = []

    def clock(self) -> float:
        return self.t

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.t += seconds


def _folders(tmp_path, animals=("REFERENCE",)):
    """`--subjects`, `--tasks` and `--root` for a rig service, as `tests/test_service.py` makes
    them: each animal the eight-hour file renamed for it, `REFERENCE` with its settings, one task."""
    subjects, tasks, root = tmp_path / "subjects", tmp_path / "tasks", tmp_path / "sessions"
    for animal in animals:
        (subjects / animal).mkdir(parents=True)
        (subjects / animal / "bounds.py").write_text(
            EIGHT_HOURS.read_text().replace('subject="REFERENCE"', f'subject="{animal}"'))
    shutil.copy("tasks/reference_subject.py", subjects / "REFERENCE" / "settings.py")
    tasks.mkdir()
    shutil.copy(f"tasks/{TASK}", tasks / TASK)
    root.mkdir()
    return subjects, tasks, root


def _made(folders, *, link=None, rig=RIG, rig_path=RIG_FILE, pace=None, **over):
    subjects, tasks, root = folders
    pace = pace if pace is not None else _Pace()
    return Service(
        rig=rig, rig_path=rig_path, subjects=subjects, tasks=tasks,
        allocation=_load_allocation(Path(ALLOCATION)), allocation_path=ALLOCATION,
        root=root, link=link if link is not None else Simulated(), seed=lambda: 7,
        wall_clock=_Wall(), pace_clock=pace.clock, pace_sleep=pace.sleep, **over,
    )


def _demo_service(tmp_path, **over) -> Service:
    """A demo service, as `wlx taskd --demo` builds one: its folder made by `demo_folder`."""
    subjects, root = demo_folder(tmp_path / "demo")
    tasks = tmp_path / "tasks"
    tasks.mkdir()
    shutil.copy(f"tasks/{TASK}", tasks / TASK)
    return _made((subjects, tasks, root), demo_service=True, **over)


def _rig_service(tmp_path, *, demo_root=True, **over) -> Service:
    """A live rig service that offers demos: a gaze endpoint (`Simulated`'s) and, with
    `demo_root`, a demo folder of its own beside `--root`."""
    root = tmp_path / "demos" if demo_root else None
    return _made(_folders(tmp_path), demo_root=root, **over)


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


def _start(**over) -> StartRun:
    fields = dict(by=BY, task=TASK, values=dict(VALUES), trials=2, acknowledged=UNKNOWN)
    fields.update(over)
    return StartRun(**fields)


def _end(session_id=None, returned="now") -> EndSession:
    return EndSession(by=BY, session_id=session_id, returned=returned, confirm=False)


def _step(service, *commands):
    """One housekeeping pass with `commands` waiting; the last frame it published."""
    for command in commands:
        service.link.queue(command)
    service.step()
    return service.link.published[-1]


def _steered(service) -> None:
    """**A page's pointer report**, waiting on the service's link (`Simulated.gazes`), as a page
    steering its demo sends one: a demo run's first trial waits for one (`pointer.Worlds.waiting`;
    demo mode's Task 10), so a test that starts a demo run sends it first."""
    service.link.gazes.append(pointer.pack(1, 0.0, -5.0, over=True, b=False, button=False,
                                           held=0, presses=(0,) * pointer.KEYS))


class _Page(Simulated):
    """**A page steering a demo**, on the in-process link: from `steer()` on, a report a frame at
    `REST`'s place in `tests/_demo.py`, `(0, -5)`, outside the fixation window, numbered from 1
    (`sent`), `left` of them and then none, as a page that lets go of the eye (Escape), or until
    the test ends. A run waits at each trial's boundary while no page steers (`pointer.Worlds`;
    the whole-build review's I3), so a demo run of more than one trial needs one."""

    def __init__(self) -> None:
        super().__init__()
        self.steering, self.left, self.sent, self._given = False, None, 0, False

    def steer(self, reports=None) -> None:
        """A page steering from now: a report a frame, `reports` of them, or with none, on."""
        self.steering, self.left = True, reports

    def gaze_into(self, buffer):
        # One report a drain while steering: the report, then nothing, so each frame takes one.
        if self.steering and not self._given:
            self._given = True
            self.sent += 1
            message = pointer.pack(self.sent, 0.0, -5.0, over=True, b=False, button=False,
                                   held=0, presses=(0,) * pointer.KEYS)
            buffer[:len(message)] = message
            if self.left is not None:
                self.left -= 1
                self.steering = self.left > 0
            return len(message)
        self._given = False
        return super().gaze_into(buffer)


def _refused(frame) -> list[str]:
    return [refusal.why for refusal in frame.refusals]


def _xcon(root: Path, session_id: str) -> Path:
    return root / session_id / "xcon"


def _config(root: Path, session_id: str) -> dict:
    return json.loads((_xcon(root, session_id) / "config.json").read_text())


def _kinds(root: Path, session_id: str) -> list[str]:
    path = _xcon(root, session_id) / "welfare_notes.jsonl"
    return [json.loads(line)["kind"] for line in path.read_text().splitlines()] if path.exists() else []


def _never_served(self, stop):
    # Every refusal comes before the service serves; one that stopped refusing would serve until
    # interrupted, and the test would hang rather than fail.
    raise AssertionError("wlx taskd served when it should have refused")


def _interrupted(self, stop):
    # Ctrl-C at once: `wlx taskd` has said what it found by then.
    raise KeyboardInterrupt


def _taskd(*extra, link=FOUR) -> list[str]:
    return ["taskd", "--rig", RIG_FILE, "--allocation", ALLOCATION, "--link", link, *extra]


# --- wlx taskd --demo --------------------------------------------------------------------


def test_taskd_demo_refuses_subjects_and_root_beside_it_and_an_existing_dir(tmp_path, monkeypatch):
    """§3.1, §7: `--subjects`, `--root` (and a rig's `--demo-root`) beside `--demo`, an existing
    `DIR`, fewer than four endpoints and no checkout to copy `REFERENCE` from are each refused at
    start, **nothing made**; without `--demo`, `--subjects` and `--root` are required."""
    monkeypatch.setattr(Service, "serve", _never_served)
    subjects, tasks, root = _folders(tmp_path)
    demo, elsewhere = tmp_path / "demo", tmp_path / "elsewhere"
    for flags, named in (
        (("--subjects", str(subjects)), "--subjects cannot"),
        (("--root", str(root)), "--root cannot"),
        (("--demo-root", str(elsewhere)), "--demo-root cannot"),
        (("--subjects", str(subjects), "--root", str(root)), "--subjects and --root cannot"),
    ):
        with pytest.raises(SystemExit, match=f"refused: --demo makes its own folder.*{named} be given"):
            main(_taskd("--tasks", str(tasks), "--demo", str(demo), *flags))
        assert not demo.exists() and not elsewhere.exists()
    with pytest.raises(SystemExit, match="--demo needs --link's four endpoints"):
        main(_taskd("--tasks", str(tasks), "--demo", str(demo), link=FOUR.rsplit(",", 1)[0]))
    assert not demo.exists()
    demo.mkdir()
    (demo / "kept").write_text("another's")
    with pytest.raises(SystemExit, match="exists, and a demo's folder is made new"):
        main(_taskd("--tasks", str(tasks), "--demo", str(demo)))
    assert [p.name for p in demo.iterdir()] == ["kept"]

    fresh = tmp_path / "fresh"
    monkeypatch.setattr(cli, "checkout_tasks", lambda: tmp_path / "subjects")
    with pytest.raises(SystemExit, match="eight_hour_bounds.py is not there"):
        main(_taskd("--tasks", str(tasks), "--demo", str(fresh)))
    assert not fresh.exists()

    def no_checkout():
        raise SystemExit("refused: no checkout")

    monkeypatch.setattr(cli, "checkout_tasks", no_checkout)
    with pytest.raises(SystemExit, match="no checkout"):
        main(_taskd("--tasks", str(tasks), "--demo", str(fresh)))
    assert not fresh.exists()

    for flags, missing in ((("--root", str(root)), "--subjects is"),
                           (("--subjects", str(subjects)), "--root is"),
                           ((), "--subjects and --root are")):
        with pytest.raises(SystemExit, match=f"refused: {missing} required, but beside --demo"):
            main(_taskd("--tasks", str(tasks), *flags))


def test_checkout_tasks_is_this_checkouts_folder_or_refused_saying_why(tmp_path, monkeypatch):
    """Where a demo's `REFERENCE` is copied from: the repository's own `tasks/`, beside the
    package this `wlx` runs from; a `wlx` with no checkout says so."""
    assert cli.checkout_tasks() == Path(cli.__file__).resolve().parents[1] / "tasks"
    assert (cli.checkout_tasks() / "eight_hour_bounds.py").is_file()
    monkeypatch.setattr(cli, "__file__", str(tmp_path / "wl_xcon" / "cli.py"))
    with pytest.raises(SystemExit, match="which has no tasks/ folder"):
        cli.checkout_tasks()


def test_taskd_demo_makes_its_folder_with_reference_alone(tmp_path, monkeypatch, capsys):
    """§3.1: `DIR` made, holding `REFERENCE` alone -- the eight-hour file and the reference
    settings, byte for byte -- and an empty sessions folder; a demo service on the simulators, the
    four bound endpoints printed on one line for `wlx demo` to read."""
    tasks = tmp_path / "tasks"
    tasks.mkdir()
    shutil.copy(f"tasks/{TASK}", tasks / TASK)
    demo = tmp_path / "made" / "demo"
    served = []

    def serve(self, stop):
        served.append(self)
        self.publish()
        raise KeyboardInterrupt

    monkeypatch.setattr(Service, "serve", serve)

    assert main(_taskd("--tasks", str(tasks), "--demo", str(demo))) == 130
    assert sorted(p.name for p in demo.iterdir()) == ["sessions", "subjects"]
    assert [p.name for p in (demo / "subjects").iterdir()] == ["REFERENCE"]
    reference = demo / "subjects" / "REFERENCE"
    assert sorted(p.name for p in reference.iterdir()) == ["bounds.py", "settings.py"]
    assert (reference / "bounds.py").read_bytes() == Path("tasks/eight_hour_bounds.py").read_bytes()
    assert (reference / "settings.py").read_bytes() == Path("tasks/reference_subject.py").read_bytes()
    assert list((demo / "sessions").iterdir()) == []
    (service,) = served
    assert (service.demo_service, service.subjects, service.root) == (
        True, demo / "subjects", demo / "sessions")
    assert (service._card, service._pump) == (dio.Simulated, SimulatedPump)
    assert service._animals() == ("REFERENCE",)
    first = capsys.readouterr().out.splitlines()[0]
    assert first.startswith("wlx taskd: --link ")
    endpoints = first.removeprefix("wlx taskd: --link ").split(",")
    assert len(endpoints) == 4 and len(set(endpoints)) == 4
    assert all(e.startswith("tcp://127.0.0.1:") and not e.endswith(":0") for e in endpoints)
    assert endpoints[3] == service.link.gaze_endpoint, "the fourth is where pointer reports arrive"


def test_a_rig_service_names_its_demo_root_makes_it_and_says_where_demos_go(tmp_path, monkeypatch, capsys):
    """The PI's answer of 2026-11-14: `wlx taskd --demo-root DIR` beside its fourth endpoint, made
    if absent, and said where the operator started it."""
    subjects, tasks, root = _folders(tmp_path)
    demos = tmp_path / "not" / "yet" / "demos"
    served = []

    def serve(self, stop):
        served.append(self)
        raise KeyboardInterrupt

    monkeypatch.setattr(Service, "serve", serve)
    assert main(_taskd("--subjects", str(subjects), "--tasks", str(tasks), "--root", str(root),
                       "--demo-root", str(demos))) == 130
    assert demos.is_dir() and list(demos.iterdir()) == []
    (service,) = served
    assert (service.demo_service, service.demo_root, service.root) == (False, demos, root)
    out = capsys.readouterr().out
    assert f", pointer reports on {service.link.gaze_endpoint}" in out
    assert f"demos: written under {demos}, apart from --root" in out


def test_wlx_taskd_says_a_stranded_demo_holds_up_no_real_session(tmp_path, monkeypatch, capsys):
    """Said where the operator started it: a demo left in the demo folder holds up another demo
    and no other session, beside what a stranded animal under `--root` holds up."""
    first = _rig_service(tmp_path)
    _step(first, _demo())
    first.shutdown()
    monkeypatch.setattr(Service, "serve", _interrupted)
    assert main(_taskd("--subjects", str(first.subjects), "--tasks", str(first.tasks),
                       "--root", str(first.root), "--demo-root", str(first.demo_root))) == 130
    assert (f"  stranded demo: session {DEMO} in the demo folder; no demo opens until its return "
            f"is recorded, and it holds up no other session") in capsys.readouterr().out


def test_a_demo_sessions_link_reads_the_pages_reports_through_the_services_own(tmp_path):
    """`_Routed`, the link a service session drains through, is the `Link` protocol whole: its
    gaze channel is the service's link's own, the method itself and its endpoint (Task 3's carry)."""
    service = _rig_service(tmp_path)
    _step(service, _demo())
    routed = service.session.link
    assert routed.gaze_into == service.link.gaze_into
    assert routed.gaze_endpoint == service.link.gaze_endpoint == "simulated"
    service.link.gaze_endpoint = None
    assert routed.gaze_endpoint is None, "read through, never copied"


def test_a_demo_root_is_a_rig_services_own_and_apart_from_its_root(tmp_path):
    """A demo is kept apart from the real sessions by where it is written, so a demo folder that
    is `--root`, inside it or holding it is refused; a demo service takes none."""
    folders = _folders(tmp_path)
    root = folders[2]
    for demos in (root, root / "demos", tmp_path):
        with pytest.raises(SystemExit, match="one holds the other"):
            _made(folders, demo_root=demos)
    assert _made(folders, demo_root=tmp_path / "demos").demo_root == tmp_path / "demos"
    with pytest.raises(SystemExit, match="a demo service's sessions go to its own folder"):
        _made(folders, demo_service=True, demo_root=tmp_path / "demos")


# --- the simulators, and the demo path -------------------------------------------------------


def test_a_demo_service_refuses_any_card_or_pump_but_the_simulators(tmp_path):
    """§3.2: a demo service's card and pump are the simulators, always."""

    class _Card(dio.Simulated):
        pass

    class _Pump(SimulatedPump):
        pass

    folders = _folders(tmp_path)
    for given in ({"card": _Card}, {"pump": _Pump}, {"card": lambda: dio.Simulated()}):
        with pytest.raises(SystemExit, match="card and pump are the simulators, always"):
            _made(folders, demo_service=True, **given)
        _made(folders, **given)  # a rig service takes them
    built = _made(folders, demo_service=True)
    assert (built._card, built._pump) == (dio.Simulated, SimulatedPump)


def test_a_demo_command_not_built_through_the_demo_path_is_refused(tmp_path):
    """A demo command reaching `_session_for` by any path but `_open`'s demo path, which calls it
    with `demo=True` (demo mode §8, its second change), is refused -- never quietly a live session,
    on any card or pump: nothing written, the id free. `_open` takes that path for every demo, in a
    demo service and on a rig service sent one (`tests/test_demo_open.py`)."""
    rig = _rig_service(tmp_path)
    refusal = (
        "a demo opens only through Service._open's demo path, and this one did not come through "
        "it, so nothing was recorded")
    for given in ({}, {"card": dio.Simulated, "pump": SimulatedPump}):
        with pytest.raises(ValueError) as refused:
            rig._session_for(_demo(), **given)
        assert str(refused.value) == refusal
    assert list(rig.root.iterdir()) == [] and not rig.demo_root.exists()
    opened = _step(rig, _demo())
    assert opened.phase == "between_runs" and opened.demo, "through _open, a demo"
    _step(rig, _end())
    opened = _step(rig, _open())
    assert opened.phase == "between_runs" and not opened.demo, "a live open is today's"

    demo = _demo_service(tmp_path / "demo")
    assert _step(demo, _open()).demo, "every open in a demo service is a demo"


def test_build_with_demo_runs_on_the_factories_it_is_given(tmp_path):
    """`_build` builds on the card and the pump the caller's factories make -- the demo path's,
    whatever the service was built with -- and a live session on the service's own. Asked by
    identity: two fresh simulators compare equal."""
    made: list = []

    class _Card(dio.Simulated):
        def __init__(self, *args, **kwargs) -> None:
            super().__init__(*args, **kwargs)
            made.append(self)

    class _Pump(SimulatedPump):
        pass

    mine, my_pump = dio.Simulated(), SimulatedPump()
    service = _rig_service(tmp_path, card=_Card, pump=_Pump)
    given = service._session_for(_demo(), card=lambda: mine, pump=lambda: my_pump, demo=True)
    assert given.card is mine and given.pump is my_pump and made == []
    own = service._session_for(_open())
    assert made == [own.card] and type(own.pump) is _Pump, "a live session's are the service's"
    built, _ = service._build(session_id="x", animal="REFERENCE", deployment="rig_fixed",
                              view="direct", session_kind="training", delivered_today=0.0,
                              card=lambda: mine, pump=lambda: my_pump, demo=False)
    assert built.card is mine and built.pump is my_pump

    _step(service, _demo())
    card, pump = service.session.card, service.session.pump
    assert (type(card), type(pump)) == (dio.Simulated, SimulatedPump), "the demo path's own"
    assert len(made) == 1
    _steered(service)
    _step(service, _start(trials=1))
    run_start = next(code for code, name in service.allocation.task_events.items()
                     if name == "RUN_START")
    assert run_start in card.codes, "the demo's run strobed onto the card it was built on"
    assert len(made) == 1


def test_a_demo_with_no_gaze_endpoint_is_refused_saying_why(tmp_path):
    """§3.8: with no gaze endpoint, the link's fourth, no page could steer a demo."""
    service = _rig_service(tmp_path, link=Simulated(gaze_endpoint=None))
    frame = _step(service, _demo())
    assert _refused(frame) == [
        "this rig service has no gaze endpoint, --link's fourth, so no page could steer a demo"]
    assert service.session is None and not service.demo_root.exists()
    assert list(service.root.iterdir()) == []
    assert frame.gaze is False


def test_a_rig_service_without_a_demo_root_refuses_a_demo_saying_why(tmp_path):
    """The PI, 2026-11-14: a rig service with no `--demo-root` opens no demo, saying why, and
    writes nothing under `--root`."""
    service = _rig_service(tmp_path, demo_root=False)
    frame = _step(service, _demo())
    assert _refused(frame) == [
        "this rig service names no --demo-root, so a demo has nowhere apart from the real "
        "sessions to go"]
    assert service.session is None and list(service.root.iterdir()) == []
    assert frame.gaze is False


# --- the field and the record ------------------------------------------------------------------


def test_a_demo_field_takes_stand_ins_on_an_unmeasured_rig_and_a_live_open_never_does(tmp_path):
    """§3.6: on `tasks/rig.py`, whose housings are unmeasured, a demo in direct view takes the
    stand-ins, and its record says so; a live open in direct view is refused as `Rig.direct`
    refuses it. Where the housings are measured -- the tests' rig -- or through the stereoscope,
    whose mask hides them, a demo takes none."""
    rig = _load_rig(UNMEASURED)
    service = _rig_service(tmp_path, rig=rig, rig_path=str(UNMEASURED))
    _step(service, _demo())
    spec = service.session.spec
    assert spec.geometry.housings == stand_in_housings(rig.panel_width_cm)
    assert spec.demo.stand_in_housings is True
    assert _config(service.demo_root, DEMO)["demo"]["stand_in_housings"] is True
    assert _config(service.demo_root, DEMO)["setup"]["housings"] == [
        {"left_cm": h.left_cm, "right_cm": h.right_cm, "bottom_cm": h.bottom_cm,
         "top_cm": h.top_cm, "margin_cm": h.margin_cm} for h in stand_in_housings(58.997)]
    _steered(service)
    _step(service, _start(trials=1))
    drawn = [f for f in service.link.published if isinstance(f, Drawn)]
    assert drawn and {d.stand_in for d in drawn} == {True}, "the drawing labels them"
    assert {d.housings for d in drawn} == {stand_in_housings(rig.panel_width_cm)}
    _step(service, _end())
    live = _step(service, _open())
    assert service.session is None and "housings" in _refused(live)[-1]
    assert list(service.root.iterdir()) == []

    measured = _rig_service(tmp_path / "measured")
    _step(measured, _demo())
    assert measured.session.spec.geometry.housings == RIG.housings
    assert measured.session.spec.demo.stand_in_housings is False
    _step(measured, _end())
    _step(measured, _demo(session_id="demo-2", view="stereoscope"))
    assert measured.session.spec.geometry.housings == ()
    assert measured.session.spec.demo.stand_in_housings is False


def test_a_demos_config_json_carries_demo_and_no_other_sessions_does(tmp_path):
    """§3.7: `config.json` gains `"demo": {"gaze": "mouse", "noise_deg": 0.02,
    "stand_in_housings": ...}`, and no other session has the key; every frame of a demo says
    `demo`, and no other session's does."""
    service = _rig_service(tmp_path)
    frame = _step(service, _demo())
    assert _config(service.demo_root, DEMO)["demo"] == {
        "gaze": "mouse", "noise_deg": 0.02, "stand_in_housings": False}
    assert isinstance(frame, Telemetry) and frame.demo is True
    _steered(service)
    _step(service, _start(trials=1))
    frames = [f for f in service.link.published if isinstance(f, Telemetry)]
    assert {f.demo for f in frames if f.session_id == DEMO} == {True}
    _step(service, _end())
    live = _step(service, _open())
    assert "demo" not in _config(service.root, SESSION) and live.demo is False
    _step(service, _start(trials=1))
    assert {f.demo for f in service.link.published
            if isinstance(f, Telemetry) and f.session_id == SESSION} == {False}


# --- running a demo -----------------------------------------------------------------------------


def test_a_demo_paces_to_the_wall_clock_and_a_live_session_runs_flat_out(tmp_path, monkeypatch):
    """§3.5: a demo's frames wait for their moment on the wall clock (`pointer.Pace`, the
    service's `pace_clock`, its sleep the service's `pace_sleep`); a live session's never wait.
    And its worlds are the mouse's, made for each run from the run's own seed (§14 item 16): read
    through the session's link, the page's report among them, its screen published through it,
    blank at each trial's end (§3.9)."""
    seeds = []

    class _Source(pointer.Source):
        def __init__(self, receive, *, seed, **kwargs) -> None:
            seeds.append(seed)
            super().__init__(receive, seed=seed, **kwargs)

    monkeypatch.setattr(pointer, "Source", _Source)
    pace = _Pace()
    service = _rig_service(tmp_path, pace=pace, link=_Page())
    service._seed = iter((41, 42, 43)).__next__
    _step(service, _demo())
    service.link.steer()
    _step(service, _start(trials=2))
    assert seeds == [41] and service.link.sent > 100, "the page's reports were read"
    assert len(pace.slept) > 100
    assert all(s == pytest.approx(service_module.FRAME_PERIOD, abs=1e-9) for s in pace.slept)
    drawn = [f for f in service.link.published if isinstance(f, Drawn)]
    assert drawn and {d.session_id for d in drawn} == {DEMO}
    assert [d.trial for d in drawn if d.screen is None] == [0, 1], "a blank at each trial's end"
    assert drawn[0].frame == 1 and drawn[0].stand_in is False
    _steered(service)
    _step(service, _start(trials=1))
    assert seeds == [41, 42], "a source a run, from that run's seed"

    _step(service, _end())
    slept = len(pace.slept)
    _step(service, _open())
    _step(service, _start(trials=2))
    assert len(pace.slept) == slept, "a live session waits on nothing"
    assert seeds == [41, 42]
    assert [f for f in service.link.published if isinstance(f, Drawn) and f.session_id == SESSION] == []


def test_the_preflight_names_the_mouse_as_a_demos_gaze(tmp_path):
    """§3.7: in a demo the eye tracker's item says the session's gaze is the mouse on its demo
    page, still an unknown to acknowledge, and the demo's keys are an item of their own; a live
    session's pre-flight is today's."""
    service = _rig_service(tmp_path)
    _step(service, _demo())
    checked = _step(service, CheckRun(by=BY, task=TASK, values=dict(VALUES))).preflight
    items = {item.name: item for item in checked.items}
    assert items["eye tracker"].result == "unknown"
    assert items["eye tracker"].said.startswith(
        "this session's gaze is the mouse on its demo page")
    assert (items["demo inputs"].result, items["demo inputs"].said) == (
        "pass", "the task waits on no input but the gaze, so no key is needed")
    assert [item.name for item in checked.items][-3:] == [
        "pump calibration", "eye tracker", "demo inputs"]
    _step(service, _end())
    _step(service, _open())
    live = _step(service, CheckRun(by=BY, task=TASK, values=dict(VALUES))).preflight
    assert "demo inputs" not in [item.name for item in live.items]
    (tracker,) = [item for item in live.items if item.name == "eye tracker"]
    assert "the simulated animal's" in tracker.said


def _ten_inputs(folder: Path) -> str:
    """The reference task waiting on ten levers as it waits for fixation, written into `folder`."""
    text = Path(f"tasks/{TASK}").read_text()
    old = '                On(Entered("fix"), "hold_fix"),\n'
    assert text.count(old) == 1
    levers = "".join(f'                On(Pressed("lever{n}"), Outcome.NO_FIXATION),\n'
                     for n in range(1, 11))
    text = text.replace(old, old + levers).replace("    P,\n", "    P,\n    Pressed,\n", 1)
    (folder / "ten_inputs.py").write_text(text)
    return "ten_inputs.py"


def test_a_demo_task_naming_ten_inputs_fails_its_preflight_naming_them(tmp_path):
    """§3.4: a demo gives each input a number key, 1 to 9; a task naming more fails the demo's
    pre-flight, naming those past nine, and no run starts. A live session's has no such item."""
    service = _rig_service(tmp_path)
    task = _ten_inputs(service.tasks)
    _step(service, _demo())
    checked = _step(service, CheckRun(by=BY, task=task, values=dict(VALUES))).preflight
    (item,) = [item for item in checked.items if item.name == "demo inputs"]
    assert item.result == "fail"
    assert "this task names 10: lever10 would have none" in item.said
    refused = _step(service, _start(task=task, acknowledged=UNKNOWN))
    assert refused.run_index is None and "demo inputs" in _refused(refused)[-1]
    _step(service, _end())
    _step(service, _open())
    live = _step(service, CheckRun(by=BY, task=task, values=dict(VALUES))).preflight
    assert "demo inputs" not in [item.name for item in live.items]


# --- a run's first trial waits for its page's pointer (Task 10) ---------------------------------


class _Unsteered(_Page):
    """**A page that steers late**: once `armed`, each wait asked of the link (`idle`, which a run
    waiting for its pointer calls once a pass, as `Service.step` calls it once a housekeeping pass)
    counted, and at the `at`-th, `then(self)` -- steering begun (`_Page.steer`), a command queued,
    the wall moved on -- with how much had been published by then kept in `before`. **Two
    backstops**: past `BACKSTOP` passes (each a `drain`) a Stop is queued, so a run that never
    stopped waiting ends; and past `BACKSTOP * 5` waits one raises, the run's fault, for a wait
    that never comes back to the boundary: either way its test fails on what it finds rather than
    hanging. Never waits: a simulated session's clocks are the test's."""

    BACKSTOP = 40

    def __init__(self, at: int) -> None:
        super().__init__()
        self.at, self.then = at, None
        self.armed, self.waits, self.before, self.drains = False, 0, None, 0

    def drain(self):
        if self.armed:
            self.drains += 1
            if self.drains == self.BACKSTOP:
                self.queue(Stop(by=Box("backstop")))
        return super().drain()

    def idle(self, timeout):
        if self.armed:
            self.waits += 1
            if self.waits == self.at:
                self.before = len(self.published)
                self.then(self)
            if self.waits > self.BACKSTOP * 5:
                raise AssertionError("the run waited for its pointer apart from its boundary")
        return super().idle(timeout)


def _unsteered(tmp_path, then) -> tuple[Service, _Unsteered]:
    """A demo open on a rig service whose page steers at the fourth wait: the step's own, then the
    run's first three passes waiting for the pointer; armed, and a run of two trials started."""
    link = _Unsteered(4)
    service = _rig_service(tmp_path, link=link)
    link.then = lambda link: then(service, link)
    _step(service, _demo())
    link.armed = True
    _step(service, _start(trials=2))
    return service, link


def _trial_rows(service) -> list:
    path = _xcon(service.demo_root, DEMO) / "trials.jsonl"
    return path.read_text().splitlines() if path.exists() else []


def _run_ends(service) -> list:
    path = _xcon(service.demo_root, DEMO) / "runs.jsonl"
    return [row for row in map(json.loads, path.read_text().splitlines())
            if row.get("stop_kind") is not None]


def test_a_demo_runs_first_trial_waits_for_its_pages_pointer_with_the_field_drawn(tmp_path):
    """Demo mode's Task 10: before a run's first screen a page has nothing to point at, and an eye
    nobody steers ends a trial as tracker lost, so **a demo run's first trial waits at the boundary
    until a pointer report arrives**: the field published blank for the page to point at, once a
    pass, the feed saying why once, and no trial drawn, opened or scored meanwhile. Then the run
    plays, and while the page steers no later trial waits: the second runs at once."""
    service, link = _unsteered(tmp_path, lambda service, link: link.steer())
    published = link.published
    drawn = [(at, f) for at, f in enumerate(published) if isinstance(f, Drawn)]
    fields = [(at, f) for at, f in drawn if f.frame == 0]
    assert len(fields) == 3, "the field, once each of the three passes before the report"
    assert {(f.trial, f.screen, f.windows, f.keys, f.session_id) for _, f in fields} == {
        (0, None, (), (), DEMO)}
    assert all(at < link.before for at, _ in fields)
    assert all(at >= link.before for at, f in drawn if f.frame >= 1), "a trial drew before it"
    assert drawn[:3] == fields, "the field only before the first trial"
    assert len(_trial_rows(service)) == 2, "both trials played once it arrived"
    assert link.drains < link.BACKSTOP
    said = [c.said for c in published[-1].controls if c.kind == "demo"]
    assert said == [taskd_module.POINTER_AWAITED]


def test_a_mark_while_a_demo_run_waits_for_its_pointer_is_stamped_there(tmp_path):
    """The wait is a paused pass's (`link.idle`), which returns early with a mark: the mark is
    stamped there, between trials before the first, as the paused loop stamps one."""
    def then(service, link):
        link.marks.append(7)
        link.steer()

    service, link = _unsteered(tmp_path, then)
    stamped = [c.said for c in link.published[-1].controls if c.kind == "mark"]
    assert stamped and stamped[0].startswith("mark 1 stamped between trials, before trial 0")
    assert len(_trial_rows(service)) == 2


@pytest.mark.parametrize("case", ["stop", "end", "out of cage"])
def test_while_a_demo_run_waits_for_its_pointer_every_boundary_rule_holds(tmp_path, case):
    """The wait is the boundary's own pass, repeated: a person's Stop ends the run, End ends it and
    the session with its return, and the out-of-cage limit ends it as between any two trials
    (`Session._ends`), each with no trial drawn or scored."""
    def then(service, link):
        if case == "stop":
            link.queue(Stop(by=BY))
        elif case == "end":
            link.queue(_end())
        else:
            service.wall_clock.at += 9 * 3600.0

    service, link = _unsteered(tmp_path, then)
    assert link.waits == 4 and link.before is not None and link.drains < link.BACKSTOP
    assert [f for f in link.published if isinstance(f, Drawn) and f.frame >= 1] == []
    assert _trial_rows(service) == []
    (ended,) = _run_ends(service)
    assert ended["stop_kind"] == {"stop": "operator", "end": "operator",
                                  "out of cage": "limit"}[case], ended
    if case == "end":
        assert service.session is None
        assert _kinds(service.demo_root, DEMO)[-2:] == ["returned", "session ended"]


def test_once_its_page_lets_go_a_demo_run_waits_before_its_next_trial_until_it_steers_again(
        tmp_path):
    """**The whole-build review's I3**: a page points (the first trial waits for it), steers the
    run's first trial and then lets go of the eye (Escape, a tab closed or hidden): that trial ends
    as tracker lost, as the rig's eye rules end it, and **the next trial waits at the boundary**,
    as the first did -- the field published for the page, the feed saying why again, no trial
    drawn, opened or scored -- until a report arrives; then the run plays on. Before it, every
    later trial ended as tracker lost, about fifteen a second, and a 1,000-trial run played itself
    out in about a minute."""
    link = _Unsteered(4)
    service = _rig_service(tmp_path, link=link)
    steps = iter([lambda: link.steer(200), link.steer])
    played, before = [], []

    def then(link):
        played.append(len(_trial_rows(service)))
        before.append(len(link.published))
        next(steps)()
        link.at = link.waits + 3

    link.then = then
    _step(service, _demo())
    link.armed = True
    _step(service, _start(trials=3))

    outcomes = [json.loads(row)["outcome"] for row in _trial_rows(service)]
    assert outcomes == ["tracker_lost", "no_fixation", "no_fixation"], outcomes
    assert played == [0, 1], "no trial while it waited, before the first or after the Escape"
    published = link.published
    waited = [at for at, f in enumerate(published)
              if isinstance(f, Drawn) and f.trial == 1 and f.frame == 0]
    assert len(waited) == 3 and all(before[0] < at < before[1] for at in waited), waited
    assert not [f for f in published[:before[1]]
                if isinstance(f, Drawn) and f.trial == 1 and f.frame >= 1], "trial 2 drew early"
    said = [c.said for c in published[-1].controls if c.kind == "demo"]
    assert said == [taskd_module.POINTER_AWAITED] * 2, "said as each wait began"
    (ended,) = _run_ends(service)
    assert link.drains < link.BACKSTOP and ended["stop_kind"] == "completed", ended


def test_a_demo_runs_last_trial_ends_the_run_without_waiting_for_a_pointer(tmp_path):
    """I3's wait is the boundary's last question, just before a trial is drawn: a run whose last
    trial has played ends then, completed, though its page has let go, never waiting for a page to
    point at a trial it will not play (the backstop's Stop would end it as the operator's)."""
    link = _Unsteered(10**6)
    service = _rig_service(tmp_path, link=link)
    _step(service, _demo())
    link.armed = True
    link.steer(200)
    _step(service, _start(trials=1))
    assert [json.loads(row)["outcome"] for row in _trial_rows(service)] == ["tracker_lost"]
    (ended,) = _run_ends(service)
    assert ended["stop_kind"] == "completed" and link.waits == 1, (ended, link.waits)


# --- the idle frame ------------------------------------------------------------------------------


def test_the_idle_frame_says_demo_and_gaze(tmp_path):
    """Schema 21: `Idle.demo` says a demo service; `Idle.gaze` whether a demo can open here -- a
    gaze endpoint and, on a rig service, a demo folder of its own."""
    cases = [
        (lambda p: _demo_service(p), (True, True)),
        (lambda p: _demo_service(p, link=Simulated(gaze_endpoint=None)), (True, False)),
        (lambda p: _rig_service(p), (False, True)),
        (lambda p: _rig_service(p, demo_root=False), (False, False)),
        (lambda p: _rig_service(p, link=Simulated(gaze_endpoint=None)), (False, False)),
    ]
    for number, (make, said) in enumerate(cases):
        frame = _step(make(tmp_path / str(number)))
        assert isinstance(frame, Idle) and (frame.demo, frame.gaze) == said, number


# --- kept apart: the demo folder, and a demo never resumed ---------------------------------------


def test_a_live_rig_service_writes_a_demo_under_its_demo_root_never_its_root(tmp_path):
    """The PI, 2026-11-14: a demo opened on a live rig is written under its `--demo-root`, its
    whole record there, and nothing under `--root`; a real session under `--root` and nothing in
    the demo folder; and one id names one session across both."""
    service = _rig_service(tmp_path)
    _step(service, _demo())
    assert sorted(p.name for p in service.demo_root.iterdir()) == [DEMO]
    assert list(service.root.iterdir()) == []
    _steered(service)
    _step(service, _start(trials=1))
    _step(service, _end())
    assert _kinds(service.demo_root, DEMO)[-2:] == ["returned", "session ended"]
    assert (_xcon(service.demo_root, DEMO) / "runs.jsonl").is_file()
    assert list(service.root.iterdir()) == []

    used = _step(service, _open(session_id=DEMO))
    assert _refused(used)[-1] == (
        f"session id {DEMO!r} is already used under {service.demo_root}; every session has its own")
    _step(service, _open())
    assert sorted(p.name for p in service.root.iterdir()) == [SESSION]
    assert sorted(p.name for p in service.demo_root.iterdir()) == [DEMO]
    _step(service, _end())
    again = _step(service, _demo(session_id=SESSION))
    assert _refused(again)[-1] == (
        f"session id {SESSION!r} is already used under {service.root}; every session has its own")


def test_a_demos_start_shows_no_real_sessions_end(tmp_path, monkeypatch):
    """What a run's start shows of the animal's previous session (`resume.previous`, the pop-out
    search build's Task 6) is looked for in the folder the session is written to: a demo's in the
    demo folder, never among the real sessions under `--root`, and a real session's under it."""
    asked = []

    def previous(root, subject, other_than, task, plan):
        asked.append((Path(root), subject, other_than))

    monkeypatch.setattr(service_module._resume_mod, "previous", previous)
    service = _rig_service(tmp_path)
    _step(service, _open())
    _step(service, CheckRun(by=BY, task=TASK, values=dict(VALUES)))
    _step(service, _end())
    _step(service, _demo())
    _step(service, CheckRun(by=BY, task=TASK, values=dict(VALUES)))
    assert asked == [(service.root, "REFERENCE", SESSION), (service.demo_root, "REFERENCE", DEMO)]


def test_a_demo_record_is_never_resumed_only_ended(tmp_path):
    """§8, Review Focus 7: a crashed demo is found at start marked not resumable, so its banner
    offers only *end*; a resume is refused saying so, writing nothing -- also for one not yet
    marked (`_resume` reads `Restoration.demo`); its return is taken as any stranded session's."""
    first = _demo_service(tmp_path)
    _step(first, _open())
    first.shutdown()
    folders = (first.subjects, first.tasks, first.root)
    service = _made(folders, demo_service=True)
    (found,) = service.stranded
    assert (found.session_id, found.resumable, found.why) == (SESSION, False, DEMO_UNRESUMED)
    frame = _step(service)
    # Under the demo service's own root: it holds up every open there, so not `demo_folder`.
    assert [(s.session_id, s.resumable, s.why, s.demo_folder) for s in frame.stranded] == [
        (SESSION, False, DEMO_UNRESUMED, False)]
    before = _kinds(service.root, SESSION)
    refused = _step(service, ResumeSession(by=BY, session_id=SESSION))
    assert _refused(refused)[-1] == DEMO_UNRESUMED and service.session is None
    assert _kinds(service.root, SESSION) == before

    service.stranded = stranded.find(service.root)
    assert service.stranded[0].resumable is True, "its record could carry a resume"
    refused = _step(service, ResumeSession(by=BY, session_id=SESSION))
    assert _refused(refused)[-1] == DEMO_UNRESUMED and service.session is None
    assert (service.stranded[0].resumable, service.stranded[0].why) == (False, DEMO_UNRESUMED)
    assert _kinds(service.root, SESSION) == before

    ended = _step(service, _end(session_id=SESSION))
    assert ended.stranded == () and _kinds(service.root, SESSION)[-1] == "returned"


def test_a_stranded_demo_in_the_demo_root_never_holds_up_a_real_open(tmp_path):
    """The PI, 2026-11-14: a demo crashed on a live rig is found in its demo folder at start,
    offered only *end*, and never holds up a real animal's open under `--root`; it holds up another
    demo until its return is recorded, which is written into its own record in the demo folder by
    the stranded rule's own code."""
    first = _rig_service(tmp_path)
    _step(first, _demo())
    first.shutdown()
    folders = (first.subjects, first.tasks, first.root)
    service = _made(folders, demo_root=first.demo_root)
    assert service.stranded == []
    (found,) = service.stranded_demos
    assert (found.session_id, found.resumable, found.why) == (DEMO, False, DEMO_UNRESUMED)
    # XC-504: the idle frame says it is in the demo folder, so the page keeps *new session* live.
    assert [(s.session_id, s.demo_folder) for s in _step(service).stranded] == [(DEMO, True)]
    assert _refused(_step(service, ResumeSession(by=BY, session_id=DEMO)))[-1] == DEMO_UNRESUMED

    opened = _step(service, _open())
    assert isinstance(opened, Telemetry) and opened.session_id == SESSION
    assert _kinds(service.root, SESSION)[:2] == ["departure", "session opened"]
    _step(service, _end())
    held = _step(service, _demo(session_id="demo-2"))
    assert _refused(held)[-1].startswith(
        f"no demo opens while a demo's return is not recorded: session {DEMO}, in")
    assert not (service.demo_root / "demo-2").exists()

    ended = _step(service, _end(session_id=DEMO))
    assert ended.stranded == () and service.stranded_demos == []
    assert _kinds(service.demo_root, DEMO)[-1] == "returned"
    assert service.root == folders[2] and service.stranded == []
    assert _kinds(service.root, SESSION)[-1] == "session ended", "the real record is untouched"
    _step(service, _demo(session_id="demo-2"))
    assert service.session.spec.session_id == "demo-2"


@pytest.mark.parametrize("returned", [False, True], ids=["stranded", "returned"])
def test_an_end_naming_a_stranded_demo_whose_id_a_real_session_has_is_refused_ending_nothing(
    tmp_path, returned
):
    """A stranded demo's End is taken against the demo folder (`_in_demo_root`), so it is refused,
    ending nothing, when a session under `--root` has the same id, stranded or not: the real
    session's record is untouched byte for byte, and the demo stays stranded. The service never
    gives two folders one id (`_session_for`), so this is planted by hand, as only a hand makes
    it."""
    first = _rig_service(tmp_path)
    _step(first, _demo())
    first.shutdown()
    real = _xcon(first.root, DEMO)
    real.mkdir(parents=True)
    left_at = WALL - 3600
    for kind in ("departure", "returned") if returned else ("departure",):
        welfare_note(real, kind=kind, subject="REFERENCE", was=left_at, now=left_at, reason="",
                     by=BY, how="t", recorded_at=left_at)
    (real / "config.json").write_text(json.dumps({"session_id": DEMO, "subject": "REFERENCE"}))

    def files(root: Path) -> dict:
        return {path: path.read_bytes() for path in sorted((root / DEMO).rglob("*"))
                if path.is_file()}

    real_before, demo_before = files(first.root), files(first.demo_root)
    service = _made((first.subjects, first.tasks, first.root), demo_root=first.demo_root)
    assert [s.session_id for s in service.stranded] == ([] if returned else [DEMO])
    assert [s.session_id for s in service.stranded_demos] == [DEMO]

    frame = _step(service, _end(session_id=DEMO))

    assert _refused(frame)[-1] == (
        f"session {DEMO} is a stranded demo in the demo folder ({service.demo_root}), and a "
        f"session under --root ({service.root}) has the same id, so an End naming it could be "
        f"read as either; nothing was ended. Move the demo's folder out of {service.demo_root} "
        f"by hand, then restart wlx taskd")
    assert files(service.root) == real_before, "the real session's record is untouched"
    assert files(service.demo_root) == demo_before and _kinds(service.demo_root, DEMO)[-1] == (
        "session ended")
    assert [s.session_id for s in service.stranded_demos] == [DEMO], "the demo is still stranded"
    assert [s.session_id for s in service.stranded] == ([] if returned else [DEMO])
    assert (service.root, service.question) == (first.root, None)


# --- a real session stranded in the demo folder is the session it is (the review's I1) -----------

#: The real session a rig service ran and left stranded, and the next one for its animal.
REAL, NEXT = "2027-01-14_01", "2027-01-14_02"


def _old_root_as_demo_root(tmp_path, animal="M1"):
    """**The whole-build review's probe** (I1): rig service A runs a real session for `animal`
    and dies, so that session is stranded under its `--root`; the next start uses a new `--root`
    and names A's old one as `--demo-root` -- a typo, last week's root, a sibling rig's share.
    The service so started, and A's old root."""
    subjects, tasks, old = _folders(tmp_path, animals=("REFERENCE", "M1"))
    first = _made((subjects, tasks, old), demo_root=tmp_path / "demos-a")
    _step(first, _open(session_id=REAL, animal=animal))
    first.shutdown()
    new = tmp_path / "sessions-b"
    new.mkdir()
    return _made((subjects, tasks, new), demo_root=old), old


def _degraded(frame) -> bool:
    return health.verdict(frame, frame_age_s=0.0, stale_after_s=5.0, rejected=None) == "degraded"


def test_a_real_session_stranded_in_the_demo_folder_holds_up_every_open_until_its_return(tmp_path):
    """**I1**: only a record whose `config.json` says `demo` and whose animal is `REFERENCE` is a
    demo. M1's session found in the demo folder is the real session it is: in `stranded`, where it
    holds up a new real open for M1 and a demo alike, said as an animal's on the page and on
    `/health`, degraded, and offered resume or end as one under `--root` is. Its End records its
    return in its own record, in the demo folder; then M1's next session opens under `--root`."""
    service, old = _old_root_as_demo_root(tmp_path)
    assert service.stranded_demos == []
    assert [(s.session_id, s.subject, s.resumable) for s in service.stranded] == [
        (REAL, "M1", True)]
    assert service.stranded_astray == service.stranded
    frame = _step(service)
    assert [(s.session_id, s.subject, s.demo_folder) for s in frame.stranded] == [
        (REAL, "M1", False)]
    assert _degraded(frame)
    assert health._state_text(frame) == (
        "idle · no session open · an animal's return is not recorded")

    refused = _step(service, _open(session_id=NEXT, animal="M1"))
    assert _refused(refused)[-1] == (
        f"no session opens while an animal's return is not recorded: M1 in session {REAL}. Resume "
        f"it, or record its return with End session, naming its session")
    assert not (service.root / NEXT).exists() and service.session is None
    held = _step(service, _demo())
    assert _refused(held)[-1].startswith("no session opens while an animal's return is not")
    assert not (old / DEMO).exists()

    ended = _step(service, _end(session_id=REAL))
    assert ended.stranded == () and not _degraded(ended)
    assert (service.stranded, service.stranded_astray) == ([], [])
    assert _kinds(old, REAL)[-1] == "returned", "its return is written into its own record"
    assert service.root == tmp_path / "sessions-b" and list(service.root.iterdir()) == []
    opened = _step(service, _open(session_id=NEXT, animal="M1"))
    assert isinstance(opened, Telemetry) and opened.session_id == NEXT
    assert _kinds(service.root, NEXT)[:2] == ["departure", "session opened"]


def test_a_real_session_stranded_in_the_demo_folder_is_resumed_in_its_own_folder(tmp_path):
    """I1: its banner offers resume as one under `--root` does, and the resume reads and writes its
    own record, where it is; `--root` stays the service's, and nothing is made under it."""
    service, old = _old_root_as_demo_root(tmp_path)
    resumed = _step(service, ResumeSession(by=BY, session_id=REAL))
    assert isinstance(resumed, Telemetry) and resumed.session_id == REAL
    assert service.session.spec.root == old
    assert (service.stranded, service.stranded_astray) == ([], [])
    assert service.root == tmp_path / "sessions-b" and list(service.root.iterdir()) == []
    assert _kinds(old, REAL)[-1] == "session resumed"
    _step(service, _end())
    assert service.session is None and _kinds(old, REAL)[-2:] == ["returned", "session ended"]


@pytest.mark.parametrize("record", ["demo, another animal", "REFERENCE, no demo"])
def test_a_demo_is_a_record_saying_demo_for_reference_and_nothing_else_is(tmp_path, record):
    """I1's two edges, each real: a record whose `config.json` says `demo` but whose animal is
    another (here a demo's record hand-edited to M1), and `REFERENCE`'s session with no `demo` (a
    real session for the test monkey). Each holds up every open, is said as an animal's, and is
    offered what one under `--root` is: a record saying `demo` is never resumed."""
    if record == "REFERENCE, no demo":
        service, old = _old_root_as_demo_root(tmp_path, animal="REFERENCE")
        found_id, animal, resumable, why = REAL, "REFERENCE", True, ""
    else:
        first = _made(_folders(tmp_path, animals=("REFERENCE", "M1")),
                      demo_root=tmp_path / "demos")
        _step(first, _demo())
        first.shutdown()
        old = first.demo_root
        for name in ("welfare_notes.jsonl", "config.json"):
            path = _xcon(old, DEMO) / name
            text = path.read_text()
            assert '"subject": "REFERENCE"' in text, name
            path.write_text(text.replace('"subject": "REFERENCE"', '"subject": "M1"'))
        assert "demo" in _config(old, DEMO)
        service = _made((first.subjects, first.tasks, first.root), demo_root=old)
        found_id, animal, resumable, why = DEMO, "M1", False, DEMO_UNRESUMED
    assert service.stranded_demos == []
    assert [(s.session_id, s.subject, s.resumable, s.why) for s in service.stranded] == [
        (found_id, animal, resumable, why)]
    frame = _step(service)
    assert [(s.session_id, s.demo_folder) for s in frame.stranded] == [(found_id, False)]
    assert _degraded(frame)
    refused = _step(service, _open(session_id=NEXT))
    assert _refused(refused)[-1].startswith("no session opens while an animal's return is not")
    assert not (service.root / NEXT).exists()


def test_wlx_taskd_warns_of_a_real_session_in_the_demo_folder_and_starts(tmp_path, monkeypatch,
                                                                         capsys):
    """I1, warned and never refused (the PI's warnings over refusals): `wlx taskd` starts, says the
    session found in the demo folder is stranded as any is, and warns that a demo folder holds
    demos alone."""
    service, old = _old_root_as_demo_root(tmp_path)
    monkeypatch.setattr(Service, "serve", _interrupted)
    assert main(_taskd("--subjects", str(service.subjects), "--tasks", str(service.tasks),
                       "--root", str(service.root), "--demo-root", str(old))) == 130
    out = capsys.readouterr().out
    assert (f"  stranded: session {REAL} (M1); no session opens until its return is recorded"
            in out)
    assert (f"  warning: the demo folder {old} holds session {REAL} (M1), which is no demo: a "
            f"demo is REFERENCE's, its config.json saying demo, and a demo folder holds demos "
            f"alone. Its folder is {old / REAL}. It is held as the stranded session it is; once "
            f"its return is recorded, move it out of {old}, or name another folder as "
            f"--demo-root") in out
    assert "stranded demo:" not in out


def test_wlx_taskd_names_every_real_session_in_the_demo_folder_at_every_start(tmp_path,
                                                                             monkeypatch, capsys):
    """The build's re-review, N2: a real session in the demo folder is named at every start,
    stranded or not -- here M1's, its return recorded, so it holds up nothing and no banner shows
    it, yet it still sits among the demos -- with where its folder is; and so is every other record
    there that is no demo: `REFERENCE`'s without `demo`, `demo` for another animal, and one whose
    `config.json` cannot be read. A demo (`demo` for `REFERENCE`), stranded beside them, is not."""
    service, old = _old_root_as_demo_root(tmp_path)
    _step(service, _end(session_id=REAL))
    assert _kinds(old, REAL)[-1] == "returned" and service.stranded == []
    demo = _rig_service(tmp_path / "beside", demo_root=True)
    _step(demo, _demo())
    demo.shutdown()
    shutil.copytree(demo.demo_root / DEMO, old / DEMO)
    planted = {"ref-real": {"subject": "REFERENCE"}, "m1-demo": {"subject": "M1", "demo": {}},
               "unreadable": None}
    for name, config in planted.items():
        _xcon(old, name).mkdir(parents=True)
        (_xcon(old, name) / "config.json").write_text(
            "{not json" if config is None else json.dumps(config))
    monkeypatch.setattr(Service, "serve", _interrupted)
    assert main(_taskd("--subjects", str(service.subjects), "--tasks", str(service.tasks),
                       "--root", str(service.root), "--demo-root", str(old))) == 130
    out = capsys.readouterr().out
    assert (f"  warning: the demo folder {old} holds session {REAL} (M1), which is no demo: a "
            f"demo is REFERENCE's, its config.json saying demo, and a demo folder holds demos "
            f"alone. Its folder is {old / REAL}. Move it out of {old}, or name another folder as "
            f"--demo-root") in out
    for name, animal in (("m1-demo", "M1"), ("ref-real", "REFERENCE"),
                         ("unreadable", "record unreadable")):
        assert (f"  warning: the demo folder {old} holds session {name} ({animal}), which is no "
                f"demo") in out, name
    assert out.count("  warning: the demo folder") == 4, "the demo beside them is not named"
    assert f"  stranded demo: session {DEMO} in the demo folder" in out
    assert "  stranded: session" not in out


def test_a_ctrl_c_while_wlx_taskd_reads_its_demo_folder_is_an_interrupt(tmp_path, monkeypatch,
                                                                       capsys):
    """XC-512: `wlx taskd` says its ready line, then reads its demo folder for the startup warnings
    (`_not_demos`). A Ctrl-C there, which a supervisor or a test may send once the ready line is
    out, ended it by an uncaught `KeyboardInterrupt` (status -2, not 130): seen once under the full
    suite's load in `test_demo_command.py`. The startup lines are said inside `_serve`'s `try`, so
    it is an interrupt like any: 130, and *taskd: interrupted*."""
    service, old = _old_root_as_demo_root(tmp_path)

    def interrupted(demo_root):
        raise KeyboardInterrupt

    monkeypatch.setattr(service_module, "_not_demos", interrupted)
    try:
        status = main(_taskd("--subjects", str(service.subjects), "--tasks", str(service.tasks),
                             "--root", str(service.root), "--demo-root", str(old)))
    except KeyboardInterrupt:
        pytest.fail("a Ctrl-C while the startup lines were said escaped wlx taskd uncaught")
    said = capsys.readouterr()
    assert status == 130
    assert "wlx taskd: publishing on " in said.out, "the ready line came first"
    assert "taskd: interrupted" in said.err



@pytest.mark.parametrize("command", ["end", "resume"])
def test_a_real_session_in_the_demo_folder_whose_id_one_under_root_has_is_refused_doing_nothing(
    tmp_path, command
):
    """I1, as a demo's End is (`_end_stranded_demo`): a session under `--root` with the same id --
    only a hand makes one -- means a command naming it could be read as either, so it is refused,
    both records untouched byte for byte and the session still stranded."""
    service, old = _old_root_as_demo_root(tmp_path)
    twin = _xcon(service.root, REAL)
    twin.mkdir(parents=True)
    (twin / "config.json").write_text(json.dumps({"session_id": REAL, "subject": "M1"}))

    def files(root: Path) -> dict:
        return {path: path.read_bytes() for path in sorted((root / REAL).rglob("*"))
                if path.is_file()}

    before = files(old), files(service.root)
    sent = (_end(session_id=REAL) if command == "end"
            else ResumeSession(by=BY, session_id=REAL))
    frame = _step(service, sent)
    assert _refused(frame)[-1] == (
        f"session {REAL} of M1 is stranded in the demo folder ({old}), and a session under "
        f"--root ({service.root}) has the same id, so a command naming it could be read as "
        f"either; nothing was done. Move one of the two folders by hand, then restart wlx taskd")
    assert (files(old), files(service.root)) == before
    assert service.session is None and [s.session_id for s in service.stranded] == [REAL]
    assert service.stranded_astray == service.stranded and service.root == tmp_path / "sessions-b"
