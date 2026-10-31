"""`tools/measure_reply_grace.py` (XC-429): its probe logs what it says it logs, and its
summary counts a lost reply at the wait that ran out, with the rig's drain and close on
its timeline.

Its counts are not tested: they are what it exists to find out, and they are committed
under `docs/measurements/` by whoever runs it. What is tested is that it cannot quietly
count something else. Its `batch` command needs Docker and is not run here.
"""

from __future__ import annotations

import importlib.util
import json
import threading
import time
from pathlib import Path

import pytest

from wl_xcon import link
from wl_xcon.actor import Box
from wl_xcon.link import Stop, ZmqCommands, ZmqLink

_SPEC = importlib.util.spec_from_file_location(
    "wlx_measure_reply_grace",
    Path(__file__).resolve().parents[1] / "tools" / "measure_reply_grace.py",
)
tool = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(tool)


class _Rows(list):
    """A `log` for `tool.install` that keeps each row."""

    def __call__(self, event: str, **fields) -> None:
        self.append({"ev": event, **fields})


def test_the_probe_logs_a_delivery_the_drain_that_answered_it_and_the_close(
    zmq_cleanup, monkeypatch
):
    rows = _Rows()
    tool.install(rows, grace=0.0, patch=monkeypatch.setattr)
    assert link.REPLY_GRACE_S == 0.0, "the batch's grace is the one the link uses"
    session = zmq_cleanup(ZmqLink(pub_endpoint="tcp://127.0.0.1:0", rep_endpoint="tcp://127.0.0.1:0"))
    commands = zmq_cleanup(ZmqCommands(session.rep_endpoint, reply_timeout_s=10.0))
    stop = threading.Event()

    def rig() -> None:
        deadline = time.monotonic() + 10.0
        while not stop.is_set() and time.monotonic() < deadline:
            if session.drain():
                return
            time.sleep(0.005)

    draining = threading.Thread(target=rig)
    draining.start()
    try:
        commands.deliver(Stop(by=Box("jake")))
    finally:
        stop.set()
        draining.join(10)
    session.close()

    events = [row["ev"] for row in rows]
    assert sorted(events) == ["close", "deliver", "drained"]
    (sent,) = [row for row in rows if row["ev"] == "deliver"]
    assert (sent["kind"], sent["ok"]) == ("Stop", True)
    (drained,) = [row for row in rows if row["ev"] == "drained"]
    assert drained["kinds"] == ["Stop"]


def test_a_reply_the_rig_never_gives_is_logged_at_the_reply_wait(zmq_cleanup, monkeypatch):
    rows = _Rows()
    tool.install(rows, patch=monkeypatch.setattr)
    session = zmq_cleanup(ZmqLink(pub_endpoint="tcp://127.0.0.1:0", rep_endpoint="tcp://127.0.0.1:0"))
    commands = zmq_cleanup(ZmqCommands(session.rep_endpoint, reply_timeout_s=0.2))

    with pytest.raises(link.Unacknowledged):
        commands.deliver(Stop(by=Box("jake")))

    (sent,) = rows
    assert (sent["ev"], sent["kind"], sent["ok"], sent["bound"]) == (
        "deliver", "Stop", False, "reply"
    )


@pytest.mark.parametrize(("immediate", "expected"), [(True, 1), (False, 0)])
def test_immediate_off_reconnects_the_consoles_socket_without_it(
    zmq_cleanup, monkeypatch, immediate, expected
):
    import zmq

    tool.install(_Rows(), immediate=immediate, patch=monkeypatch.setattr)
    commands = zmq_cleanup(ZmqCommands("tcp://127.0.0.1:1"))

    assert commands._req.getsockopt(zmq.IMMEDIATE) == expected


def _write(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))


def test_a_lost_reply_is_counted_at_its_wait_with_the_rigs_drain_and_close_on_its_timeline(
    tmp_path,
):
    a, b = "tests/test_serve.py::x[0]", "tests/test_serve.py::x[1]"
    (tmp_path / "host.json").write_text(json.dumps({"label": "b1", "burners": 0}))
    (tmp_path / "load.json").write_text(json.dumps([3.0, 9.5, 4.0]))
    _write(tmp_path / "c1.jsonl", [
        {"ev": "config", "test": "", "grace": 0.0, "immediate": True, "python": "3.12",
         "pyzmq": "27.2.0", "libzmq": "4.3.5", "platform": "Linux"},
        {"ev": "deliver", "test": a, "kind": "Stop", "ok": True, "began": 10.0,
         "took_s": 0.01, "t": 10.01},
        {"ev": "drained", "test": a, "kinds": ["Stop"], "t": 10.005},
        {"ev": "close", "test": a, "took_s": 0.0005, "t": 10.02},
        {"ev": "result", "test": a, "when": "call", "outcome": "passed"},
        {"ev": "deliver", "test": b, "kind": "Stop", "ok": False, "bound": "reply",
         "began": 20.0, "took_s": 15.0, "t": 35.0},
        {"ev": "drained", "test": b, "kinds": ["Stop"], "t": 20.003},
        {"ev": "close", "test": b, "took_s": 0.0007, "t": 20.004},
        {"ev": "result", "test": b, "when": "call", "outcome": "failed"},
    ])

    found = tool.summarize_batch(tmp_path)

    assert (found["runs"], found["failed"]) == (2, 1)
    assert found["load"] == [3.0, 9.5]
    (lost,) = found["lost"]
    assert (lost["kind"], lost["bound"], lost["waited_s"]) == ("Stop", "reply", 15.0)
    assert lost["timeline_ms"] == [["drained Stop", 3.0], ["close", 4.0]]
    assert "| b1 | 0.0 | on | 0 | 3.0-9.5 | 2 | 1 | 1 (Stop at the reply wait: 1) |" in tool.row(found)
