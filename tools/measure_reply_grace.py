#!/usr/bin/env python3
"""How often a console loses the rig's acknowledgment of a session's last command, with
and without `link.REPLY_GRACE_S` (XC-429).

CLAUDE.md: no timing claim without a measurement. `wlx run --link` closes its link
right after the trial boundary that drained a stop. `wlx serve`'s REQ socket, which sets
`IMMEDIATE` (`link.ZmqCommands`), loses a reply it has not yet read when that connection
goes, so the page was told *not delivered* for a stop that had stopped the session.
`ZmqLink.close` therefore holds its sockets open for `REPLY_GRACE_S` after its last
reply. This script counts how many runs of the two `wlx serve` end-to-end tests that
failed this way on CI lose the stop's reply under load, for a grace and an `IMMEDIATE`
setting given on its command line. Its counts are the only ones anyone may quote for the
grace.

**It needs Docker**, and a local image with Python 3.11 or later and this package's test
dependencies installed: pytest, pyzmq, msgpack, pydantic, numpy and pyyaml. The image is
named with `--image`. Nothing is installed when it runs: each container runs with
`--network none`, with this checkout mounted read-only at `/w`, and the code it tests is
this checkout's, never an installed copy.

**`batch`** runs on the host:
- It starts `--containers` containers at once, each limited to `--cpus` CPUs. Each runs
  this script's `inside` command, which runs the two tests `--repeats` times over in one
  pytest process, serially, as CI's mutation gate does.
- `--burners` adds CPU-burning processes on the host for the length of the batch.
- It samples the host's one-minute load average every 5 s until the last container exits.
- It writes everything to `--out/LABEL/`: one JSON-lines log per container, the host and
  its load samples, and `summary.json`.

**`inside`** runs in a container and installs a probe before running the tests. The
probe logs:
- each command `ZmqCommands.deliver` sends: its kind, how long it took, and whether it was
  delivered or which wait ran out (`reply` or `connect`);
- each `ZmqLink.drain` that returned commands, and their kinds;
- each `ZmqLink.close`: when it began and how long it took.

It sets `link.REPLY_GRACE_S` to `--grace` when one is given. With `--immediate off` it
reconnects each `ZmqCommands` socket without `IMMEDIATE`.

**`summarize`** prints one Markdown row per batch, from what `batch` wrote. Each lost
reply is listed with its timeline: when the rig drained the stop, and when its close
began, both measured from when the console sent it.

**What this is not.** A count of lost replies in two-CPU Linux containers on one loaded
development host. It is not a rig measurement, and not a latency: how long a rig's
console takes to read a reply is not measured here. It shows whether a grace removes
the loss under the load given, and nothing about a load it was not run at.

    python tools/measure_reply_grace.py batch --label no-grace-1 --grace 0 \\
        --image xcon-flake:latest --containers 6 --repeats 50 --out .superpowers/reply-grace
    python tools/measure_reply_grace.py batch --label grace-1 \\
        --image xcon-flake:latest --containers 6 --repeats 50 --out .superpowers/reply-grace
    python tools/measure_reply_grace.py batch --label immediate-off-1 --grace 0 \\
        --immediate off --image xcon-flake:latest --out .superpowers/reply-grace
    python tools/measure_reply_grace.py summarize .superpowers/reply-grace
"""

from __future__ import annotations

import argparse
import json
import multiprocessing
import os
import platform
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

#: The two tests that lost the stop's reply on CI (runs 41025634023 and 41045421173).
TESTS = (
    "tests/test_serve.py::test_e2e_a_write_from_elsewhere_is_refused_and_the_session_never_sees_it",
    "tests/test_serve.py::test_e2e_pause_holds_the_trial_count_keeps_the_clock_and_resume_continues",
)

#: How often `batch` samples the host's load average while it waits.
LOAD_EVERY_S = 5.0


# --- inside a container: the probe ---------------------------------------------------


class Log:
    """One JSON object per line, each stamped with `time.monotonic()` and the test that
    was running when it was written."""

    def __init__(self, path: Path) -> None:
        self._file = open(path, "a", buffering=1, encoding="utf-8")

    def __call__(self, event: str, **fields) -> None:
        fields.setdefault("t", time.monotonic())
        test = os.environ.get("PYTEST_CURRENT_TEST", "").split(" ")[0]
        self._file.write(json.dumps({"ev": event, "test": test, **fields}) + "\n")

    def close(self) -> None:
        self._file.close()


def install(log, grace: float | None = None, immediate: bool = True, patch=setattr) -> None:
    """Wrap `link`'s console sender and session link so that `log` sees each delivery,
    drain and close. `patch` sets each attribute, so a test can pass `monkeypatch.setattr`
    and have everything undone."""
    from wl_xcon import link

    if grace is not None:
        patch(link, "REPLY_GRACE_S", grace)

    deliver = link.ZmqCommands.deliver

    def timed_deliver(self, command) -> None:
        began = time.monotonic()
        kind = type(command).__name__
        try:
            deliver(self, command)
        except link.Unacknowledged:
            log("deliver", kind=kind, ok=False, bound="reply", began=began,
                took_s=time.monotonic() - began)
            raise
        except link.NotDelivered:
            log("deliver", kind=kind, ok=False, bound="connect", began=began,
                took_s=time.monotonic() - began)
            raise
        log("deliver", kind=kind, ok=True, began=began, took_s=time.monotonic() - began)

    patch(link.ZmqCommands, "deliver", timed_deliver)

    drain = link.ZmqLink.drain

    def logged_drain(self):
        commands = drain(self)
        if commands:
            log("drained", kinds=[type(c).__name__ for c in commands])
        return commands

    patch(link.ZmqLink, "drain", logged_drain)

    close = link.ZmqLink.close

    def timed_close(self) -> None:
        began = time.monotonic()
        try:
            close(self)
        finally:
            log("close", t=began, took_s=time.monotonic() - began)

    patch(link.ZmqLink, "close", timed_close)

    if not immediate:
        import zmq

        open_ = link.ZmqCommands._open

        def without_immediate(self):
            req = open_(self)
            # `IMMEDIATE` applies to connections made after it is set.
            req.disconnect(self.endpoint)
            req.setsockopt(zmq.IMMEDIATE, 0)
            req.connect(self.endpoint)
            return req

        patch(link.ZmqCommands, "_open", without_immediate)


class _Repeat:
    """A pytest plugin: every collected test, `times` times over."""

    def __init__(self, times: int, log) -> None:
        self.times = times
        self.log = log

    def pytest_generate_tests(self, metafunc) -> None:
        if self.times > 1:
            metafunc.fixturenames.append("reply_grace_repeat")
            metafunc.parametrize("reply_grace_repeat", range(self.times))

    def pytest_runtest_logreport(self, report) -> None:
        if report.when == "call" or report.outcome != "passed":
            last = str(report.longrepr).splitlines()[-1][:300] if report.longrepr else None
            self.log("result", test=report.nodeid, when=report.when, outcome=report.outcome,
                     said=last)


def inside(args) -> int:
    """Run the tests with the probe installed, logging to `args.log`."""
    import pytest
    import zmq

    sys.path.insert(0, str(Path.cwd()))
    from wl_xcon import link

    log = Log(Path(args.log) / f"{socket.gethostname()}-{os.getpid()}.jsonl")
    immediate = args.immediate == "on"
    install(log, args.grace, immediate)
    log("config", grace=link.REPLY_GRACE_S, immediate=immediate, repeats=args.repeats,
        python=platform.python_version(), pyzmq=zmq.__version__, libzmq=zmq.zmq_version(),
        platform=platform.platform(), wl_xcon=link.__file__)
    try:
        return int(pytest.main(
            ["-q", "-p", "no:cacheprovider", "-rfE", *args.tests],
            plugins=[_Repeat(args.repeats, log)],
        ))
    finally:
        log.close()


# --- on the host: a batch --------------------------------------------------------------


def _burn(until: float) -> None:
    while time.time() < until:
        pass


def _docker(*argv: str) -> str:
    return subprocess.run(["docker", *argv], check=True, capture_output=True,
                          text=True).stdout.strip()


def batch(args) -> int:
    """Run one batch of containers and write what it found to `args.out/args.label`."""
    out = Path(args.out).resolve() / args.label
    if out.exists():
        raise SystemExit(f"refused: {out} exists; give the batch another --label")
    out.mkdir(parents=True)
    host = {
        "label": args.label,
        "platform": platform.platform(),
        "cpus": os.cpu_count(),
        "docker": _docker("version", "--format", "{{.Server.Version}}"),
        "docker_cpus": _docker("info", "--format", "{{.NCPU}}"),
        "image": args.image,
        "containers": args.containers,
        "cpus_each": args.cpus,
        "repeats": args.repeats,
        "burners": args.burners,
        "grace": args.grace,
        "immediate": args.immediate,
        "started": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    (out / "host.json").write_text(json.dumps(host, indent=1))
    burners = [
        multiprocessing.Process(target=_burn, args=(time.time() + args.burn_limit_s,))
        for _ in range(args.burners)
    ]
    for burner in burners:
        burner.start()
    names = [f"reply-grace-{args.label}-{i}" for i in range(1, args.containers + 1)]
    inner = ["python3", "/w/tools/measure_reply_grace.py", "inside", "--log", "/log",
             "--repeats", str(args.repeats), "--immediate", args.immediate, *args.tests]
    if args.grace is not None:
        inner[5:5] = ["--grace", str(args.grace)]
    loads = [os.getloadavg()[0]]
    try:
        for name in names:
            _docker("run", "-d", "--rm", "--network", "none", "--cpus", str(args.cpus),
                    "--hostname", name, "--name", name, "-v", f"{ROOT}:/w:ro",
                    "-v", f"{out}:/log", "-w", "/w", "-e", "PYTHONPATH=/w",
                    "-e", "PYTHONDONTWRITEBYTECODE=1", args.image, *inner)
        while _docker("ps", "-q", *[f"--filter=name=^{n}$" for n in names]):
            time.sleep(LOAD_EVERY_S)
            loads.append(os.getloadavg()[0])
    finally:
        for burner in burners:
            burner.terminate()
            burner.join()
    (out / "load.json").write_text(json.dumps(loads))
    found = summarize_batch(out)
    (out / "summary.json").write_text(json.dumps(found, indent=1))
    print(row(found))
    return 0


# --- reading a batch ---------------------------------------------------------------------


def _rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def summarize_batch(out: Path) -> dict:
    """What one batch's logs say: how many runs, how many lost a reply and at which
    wait, and, for each lost reply, when the rig drained the command and when its close
    began, in milliseconds from when the console sent it."""
    host = json.loads((out / "host.json").read_text()) if (out / "host.json").exists() else {}
    loads = json.loads((out / "load.json").read_text()) if (out / "load.json").exists() else []
    runs = failed = 0
    lost: list[dict] = []
    closes: list[float] = []
    config: dict = {}
    for path in sorted(out.glob("*.jsonl")):
        rows = _rows(path)
        for r in rows:
            if r["ev"] == "config":
                config = {k: r[k] for k in ("grace", "immediate", "python", "pyzmq", "libzmq",
                                            "platform")}
            elif r["ev"] == "result" and r["when"] == "call":
                runs += 1
                failed += r["outcome"] == "failed"
            elif r["ev"] == "close":
                closes.append(r["took_s"])
            elif r["ev"] == "deliver" and not r["ok"]:
                began, ended = r["began"], r["began"] + r["took_s"]
                seen = sorted(
                    (x for x in rows if x["ev"] in ("drained", "close")
                     and x["test"] == r["test"] and began <= x["t"] <= ended),
                    key=lambda x: x["t"],
                )
                lost.append({
                    "test": r["test"],
                    "kind": r["kind"],
                    "bound": r["bound"],
                    "waited_s": round(r["took_s"], 3),
                    "timeline_ms": [
                        [x["ev"] + (" " + ",".join(x["kinds"]) if x["ev"] == "drained" else ""),
                         round((x["t"] - began) * 1000, 1)]
                        for x in seen
                    ],
                })
    closes.sort()
    return {
        "label": host.get("label", out.name),
        "host": host,
        "config": config,
        "load": [min(loads), max(loads)] if loads else None,
        "runs": runs,
        "failed": failed,
        "lost": lost,
        "close_s": {"median": closes[len(closes) // 2], "max": closes[-1]} if closes else None,
    }


def row(found: dict) -> str:
    """One batch as a Markdown table row."""
    config, host = found["config"], found["host"]
    load = "-" if not found["load"] else f"{found['load'][0]:.1f}-{found['load'][1]:.1f}"
    bounds: dict = {}
    for item in found["lost"]:
        key = f"{item['kind']} at the {item['bound']} wait"
        bounds[key] = bounds.get(key, 0) + 1
    close = found["close_s"]
    closing = "-" if not close else f"{close['median'] * 1000:.1f} / {close['max'] * 1000:.1f}"
    return (
        f"| {found['label']} | {config.get('grace')} | "
        f"{'on' if config.get('immediate') else 'off'} | {host.get('burners', '-')} | {load} | "
        f"{found['runs']} | {found['failed']} | {len(found['lost'])} "
        f"({', '.join(f'{k}: {v}' for k, v in bounds.items()) or 'none'}) | "
        f"{closing} |"
    )


def summarize(args) -> int:
    """Every batch under `args.out`, as a table, then each lost reply's timeline."""
    batches = [summarize_batch(p) for p in sorted(Path(args.out).iterdir()) if p.is_dir()]
    print("| batch | grace (s) | IMMEDIATE | burners | load (1 min) | runs | failed | "
          "replies lost | close median / max (ms) |")
    print("|---|---|---|---|---|---|---|---|---|")
    for found in batches:
        print(row(found))
    for found in batches:
        for item in found["lost"]:
            steps = ", ".join(f"{what} at {ms} ms" for what, ms in item["timeline_ms"])
            print(f"- {found['label']}: {item['kind']}, {item['bound']} wait ran out at "
                  f"{item['waited_s']} s; {steps or 'nothing drained or closed meanwhile'}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    commands = parser.add_subparsers(dest="command", required=True)

    run = commands.add_parser("batch", help="run one batch of containers (needs Docker)")
    run.add_argument("--label", required=True)
    run.add_argument("--out", default=str(ROOT / ".superpowers" / "reply-grace"))
    run.add_argument("--image", required=True)
    run.add_argument("--grace", type=float, default=None,
                     help="REPLY_GRACE_S for the batch; the product's own when omitted")
    run.add_argument("--immediate", choices=("on", "off"), default="on")
    run.add_argument("--containers", type=int, default=6)
    run.add_argument("--cpus", type=float, default=2.0)
    run.add_argument("--repeats", type=int, default=50)
    run.add_argument("--burners", type=int, default=0)
    run.add_argument("--burn-limit-s", type=float, default=900.0,
                     help="the longest any burner runs, whatever happens to the batch")
    run.add_argument("tests", nargs="*", default=list(TESTS))
    run.set_defaults(func=batch)

    within = commands.add_parser("inside", help="in a container: the tests, with the probe")
    within.add_argument("--log", required=True)
    within.add_argument("--repeats", type=int, default=1)
    within.add_argument("--grace", type=float, default=None)
    within.add_argument("--immediate", choices=("on", "off"), default="on")
    within.add_argument("tests", nargs="*", default=list(TESTS))
    within.set_defaults(func=inside)

    read = commands.add_parser("summarize", help="every batch under a directory, as a table")
    read.add_argument("out", nargs="?", default=str(ROOT / ".superpowers" / "reply-grace"))
    read.set_defaults(func=summarize)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
