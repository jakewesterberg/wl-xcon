"""What a suite had done when `tools/mutate.py` stopped waiting for it (XC-275).

A pytest plugin, loaded only by `mutate._run_suite` (`-p wlx_suite_progress`, with this
directory on the child's `PYTHONPATH` and nobody else's, so nothing in `tools/` can shadow
an import). It appends one JSON line to the file named by `WLX_SUITE_PROGRESS` for each
test that starts, each test that fails (in any phase), and each test that finishes.

**Why a file rather than pytest's output.** A mutant whose suite runs past the time
limit is killed, and pytest's short summary -- the only part of its output
`mutate._failures` trusts -- is printed at the end, so for a killed suite it never
exists. Until 2026-10-10 the harness counted such a mutant caught with nothing named,
whether or not any test had noticed it (`mutate.SUITE_TIMEOUT_SECONDS` says what that
hid). These lines are written as each test runs, through pytest's own hooks, so they
survive the kill and say which tests had failed and which one was still running.

**Inert without `WLX_SUITE_PROGRESS`.** With it unset nothing is written and nothing is
opened, so loading this anywhere else changes nothing.
"""

from __future__ import annotations

import json
import os
import time

#: The environment variable naming the file to append to. `mutate.py` reads the name
#: from here rather than spelling it twice.
ENV = "WLX_SUITE_PROGRESS"


def _write(record: dict) -> None:
    path = os.environ.get(ENV)
    if not path:
        return
    # Opened and closed per line, so a line is on disk the moment it is written and
    # a kill can lose at most the line being written.
    with open(path, "a", encoding="utf-8") as out:
        out.write(json.dumps(record) + "\n")


def pytest_runtest_logstart(nodeid, location):
    _write({"event": "start", "nodeid": nodeid, "at": time.time()})


def pytest_runtest_logreport(report):
    if report.failed:
        _write({"event": "failed", "nodeid": report.nodeid, "when": report.when})
    if report.when == "teardown":
        _write({"event": "finished", "nodeid": report.nodeid})
