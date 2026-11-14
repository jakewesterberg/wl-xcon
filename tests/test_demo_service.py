"""Demo mode's service (its design §3.1, §3.2, §3.6, §3.7; its plan's Task 4): `wlx taskd --demo`,
its folder and its one animal, the simulators, the stand-in field, the record, `Session.run_world`,
a demo never resumed, and a rig's own demo folder (`--demo-root`; the PI, 2026-11-14, "A demo
folder of its own").

**`_open`'s demo path is demo mode's Task 5** (welfare-listed, its two approved changes). Until it
lands, every demo open through `Service._open` is refused (`Service._session_for`), which
`test_a_demo_command_not_built_through_the_demo_path_is_refused` holds; the tests that need a demo
open stand in for that path with `_DemoPath`, which builds a demo exactly as Task 5's second change
does, and drive the rest of the service's own path -- open, check, start, end -- through it. The
unit tests drive `Service.step` over an in-process link with an injected wall and an injected pace
clock, so nothing sleeps; the `wlx taskd` tests bind a real link on loopback.
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
from wl_xcon import cli, dio, pointer, preflight, stranded
from wl_xcon import service as service_module
from wl_xcon.actor import Box
from wl_xcon.cli import _load_allocation, _load_rig, main
from wl_xcon.geometry import stand_in_housings
from wl_xcon.link import (
    CheckRun, Drawn, EndSession, Idle, OpenSession, ResumeSession, Simulated, StartRun, Telemetry,
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


class _DemoPath(Service):
    """**Demo mode's Task 5, stood in for, until it lands**: `_open`'s second approved change --
    a demo built on the simulated card and pump with `demo=True`, whatever the service was built
    with -- made here, in `_session_for`, which `_open` calls. Its first change, a demo refused for
    any animal but `REFERENCE`, is not stood in for: these tests open demos for `REFERENCE` alone.
    `demo_card` and `demo_pump` are the factories it passes, so a test can give its own."""

    demo_card = dio.Simulated
    demo_pump = SimulatedPump

    def _session_for(self, command, *, card=None, pump=None, demo=False):
        if command.demo and not demo:
            return super()._session_for(command, card=type(self).demo_card,
                                        pump=type(self).demo_pump, demo=True)
        return super()._session_for(command, card=card, pump=pump, demo=demo)


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


def _made(folders, *, cls=Service, link=None, rig=RIG, rig_path=RIG_FILE, pace=None, **over):
    subjects, tasks, root = folders
    pace = pace if pace is not None else _Pace()
    return cls(
        rig=rig, rig_path=rig_path, subjects=subjects, tasks=tasks,
        allocation=_load_allocation(Path(ALLOCATION)), allocation_path=ALLOCATION,
        root=root, link=link if link is not None else Simulated(), seed=lambda: 7,
        wall_clock=_Wall(), pace_clock=pace.clock, pace_sleep=pace.sleep, **over,
    )


def _demo_service(tmp_path, *, cls=_DemoPath, **over) -> Service:
    """A demo service, as `wlx taskd --demo` builds one: its folder made by `demo_folder`."""
    subjects, root = demo_folder(tmp_path / "demo")
    tasks = tmp_path / "tasks"
    tasks.mkdir()
    shutil.copy(f"tasks/{TASK}", tasks / TASK)
    return _made((subjects, tasks, root), cls=cls, demo_service=True, **over)


def _rig_service(tmp_path, *, demo_root=True, cls=_DemoPath, **over) -> Service:
    """A live rig service that offers demos: a gaze endpoint (`Simulated`'s) and, with
    `demo_root`, a demo folder of its own beside `--root`."""
    root = tmp_path / "demos" if demo_root else None
    return _made(_folders(tmp_path), cls=cls, demo_root=root, **over)


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
    """Until `_open` has its demo path (demo mode's Task 5), every demo open is refused -- never
    quietly a live session: in a demo service, whose every open is a demo (`_route`), and on a rig
    service sent one. Nothing written, the id free, no departure."""
    demo = _demo_service(tmp_path / "a", cls=Service)
    refused = _step(demo, _open())
    assert isinstance(refused, Idle) and demo.session is None
    assert _refused(refused) == [
        "a demo opens only through Service._open's demo path, and this one did not come through "
        "it, so nothing was recorded"]
    assert list(demo.root.iterdir()) == []

    rig = _rig_service(tmp_path / "b", cls=Service)
    assert _refused(_step(rig, _demo()))[-1].startswith("a demo opens only through")
    assert list(rig.root.iterdir()) == [] and not rig.demo_root.exists()
    with pytest.raises(ValueError, match="demo path"):
        rig._session_for(_demo())
    opened = _step(rig, _open())
    assert opened.phase == "between_runs" and not opened.demo, "a live open is today's"


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
    service = _rig_service(tmp_path, pace=pace)
    service._seed = iter((41, 42, 43)).__next__
    _step(service, _demo())
    service.link.gazes.append(pointer.pack(1, 0.0, 0.0, over=True, b=False, button=False,
                                           held=0, presses=(0,) * pointer.KEYS))
    _step(service, _start(trials=2))
    assert seeds == [41] and service.link.gazes == [], "the page's report was read"
    assert len(pace.slept) > 100
    assert all(s == pytest.approx(service_module.FRAME_PERIOD, abs=1e-9) for s in pace.slept)
    drawn = [f for f in service.link.published if isinstance(f, Drawn)]
    assert drawn and {d.session_id for d in drawn} == {DEMO}
    assert [d.trial for d in drawn if d.screen is None] == [0, 1], "a blank at each trial's end"
    assert drawn[0].frame == 1 and drawn[0].stand_in is False
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
    service = _made(folders, cls=_DemoPath, demo_service=True)
    (found,) = service.stranded
    assert (found.session_id, found.resumable, found.why) == (SESSION, False, DEMO_UNRESUMED)
    frame = _step(service)
    assert [(s.session_id, s.resumable, s.why) for s in frame.stranded] == [
        (SESSION, False, DEMO_UNRESUMED)]
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
    service = _made(folders, cls=_DemoPath, demo_root=first.demo_root)
    assert service.stranded == []
    (found,) = service.stranded_demos
    assert (found.session_id, found.resumable, found.why) == (DEMO, False, DEMO_UNRESUMED)
    assert [s.session_id for s in _step(service).stranded] == [DEMO]
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
    service = _made((first.subjects, first.tasks, first.root), cls=_DemoPath,
                    demo_root=first.demo_root)
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
