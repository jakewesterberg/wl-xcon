"""The session fuzzer, in a budget CI can afford on every push: a few sessions find nothing, and
the fuzzer's own controls, each a known defect it injects, are each found, so this can fail.

`tools/fuzz_sessions.py` runs random tasks through `taskd.Session.run` with the simulated animal
and a person acting at random, and checks each session's record and strobed stream, read by
wl-preproc's own code, against engine build C2b's invariants and the C3 spec §12's list (its
docstring names each invariant and each control). Engine build C3 ran it by hand before its
merge, 1,000 sessions and every control (docs/CHECKPOINT.md); here, on every push, a few:

- seeds 0 to 19 find nothing;
- two of its controls are each found, in the invariant the fuzzer names for it, on seeds 0 to 4:
  `bounded` (C10: a revert also sets the reward size, which no revert may reach) and
  `impossible` (C12: the live refusal of trials no animal can get right switched off);
- replay mode agrees on seeds 0 and 1 (C1: one seed gives the same draws, order and repeats in
  two processes; C2: a draw added of a setting no state reads moves no condition or repeat), and
  its own two controls are each found on seed 0: `pid` (C1, a draw mixing in the process id) and
  `shared` (C2, the added draw also drawing from the scheduler's generator).

**Each run is a process of its own**, as the fuzzer is built to be run: importing it replaces
scheduler and session methods with instrumented ones for the rest of the process, and a control
replaces more, which a test worker's process must never carry. `PYTHONHASHSEED=0`, as its
docstring runs it, so a seed's session is the same session on every run.

**Its wall time**, measured with `time` on the development machine (2026-11-07; an Apple M3 Max,
14 cores, Python 3.13.9, while other suites held its load average near 200): 18.5 s for this file
run alone and serially, as CI's test job runs the suite, of which the twenty sessions took 6.2 s
and each other test 2.2 to 2.7 s. Each test is a process of its own, so under `-n auto` they run
side by side.

It needs wl-preproc, as the suite's other tests that read through wl-preproc's code do: a missing
checkout skips locally and fails under `WLX_REQUIRE_PREPROC=1`, which CI sets.
"""

from __future__ import annotations

import ast
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FUZZER = ROOT / "tools" / "fuzz_sessions.py"
#: Past this, a run is a hang, never a slow pass: seconds, far above any run here.
TIMEOUT_S = 300

_REQUIRED = os.environ.get("WLX_REQUIRE_PREPROC") == "1"
try:
    from wl_preproc.contracts.events import decode_stream
    from wl_preproc.events.assemble import assemble
    from wl_preproc.events.rigrecords import read_rig_records
    from wl_preproc.events.rigtiming import time_records
except ImportError as exc:  # pragma: no cover - exercised by the CI job
    if _REQUIRED:
        raise AssertionError(
            f"WLX_REQUIRE_PREPROC=1 but wl-preproc is not importable ({exc}). The fuzzer reads "
            f"every session's record and stream through wl-preproc's own code; skipping it would "
            f"report sessions nobody read"
        ) from exc
    decode_stream = assemble = read_rig_records = time_records = None

pytestmark = pytest.mark.skipif(
    assemble is None,
    reason="wl-preproc checkout neither beside this repo nor inside it; the fuzzer reads "
    "through its code",
)


def _fuzz(tmp_path: Path, *args: str) -> str:
    """The fuzzer's report for `args`, run from the tree's root in a process of its own."""
    try:
        done = subprocess.run(
            [sys.executable, str(FUZZER), *args, str(tmp_path / "fuzz")],
            cwd=ROOT,
            env={**os.environ, "PYTHONHASHSEED": "0"},
            capture_output=True,
            text=True,
            timeout=TIMEOUT_S,
        )
    except subprocess.TimeoutExpired:
        pytest.fail(f"tools/fuzz_sessions.py {' '.join(args)} ran past {TIMEOUT_S} s")
    assert done.returncode == 0, (
        f"tools/fuzz_sessions.py {' '.join(args)} exited {done.returncode}:\n"
        f"{done.stdout[-3000:]}\n{done.stderr[-3000:]}"
    )
    return done.stdout


def _line(report: str, start: str) -> dict[str, str]:
    """The `name=value` pairs of the report's line beginning `start`."""
    for line in report.splitlines():
        if line.startswith(start):
            return dict(re.findall(r"(\w+)=(\S+)", line))
    raise AssertionError(f"the fuzzer's report has no line beginning {start!r}:\n{report}")


def _kinds(report: str) -> dict[str, int]:
    """How many findings of each invariant the report counts."""
    for line in report.splitlines():
        if line.startswith("finding kinds "):
            return ast.literal_eval(line[len("finding kinds ") :])
    raise AssertionError(f"the fuzzer's report has no finding kinds:\n{report}")


def test_twenty_sessions_find_nothing(tmp_path):
    report = _fuzz(tmp_path, "20", "none", "0")
    said = _line(report, "control=")
    assert said["sessions"] == "20", report
    # Most sessions must have run, or nothing was tested: a refusal at load or at start is the
    # task's, never a finding.
    assert int(said["ran"]) >= 10, f"only {said['ran']} of 20 sessions ran:\n{report}"
    assert said["with_findings"] == "0", f"the fuzzer found something:\n{report}"


@pytest.mark.parametrize(("control", "invariant"), [("bounded", "C10"), ("impossible", "C12")])
def test_a_control_is_found(tmp_path, control, invariant):
    report = _fuzz(tmp_path, "5", control, "0")
    said = _line(report, "control=")
    assert said["control"] == control, report
    assert int(said["with_findings"]) >= 1, (
        f"control {control!r} injected and nothing found in seeds 0 to 4; if these sessions no "
        f"longer exercise {invariant}, widen the seeds rather than drop the control:\n{report}"
    )
    assert invariant in _kinds(report), (
        f"control {control!r} found, but not in {invariant}, the invariant it breaks:\n{report}"
    )


def test_replay_agrees(tmp_path):
    report = _fuzz(tmp_path, "replay", "2", "none", "0")
    c1, c2 = _line(report, "C1 "), _line(report, "C2 ")
    assert c1["seeds"] == "2" and int(c1["ran"]) >= 1 and c1["raised"] == "0", report
    assert c1["differing"] == "0", f"C1: a seed differed between two processes:\n{report}"
    assert int(c2["compared"]) >= 1, report
    assert c2["moved"] == "0", f"C2: an added draw moved a condition or repeat:\n{report}"


@pytest.mark.parametrize(("control", "check", "found"), [("pid", "C1 ", "differing"),
                                                         ("shared", "C2 ", "moved")])
def test_a_replay_control_is_found(tmp_path, control, check, found):
    report = _fuzz(tmp_path, "replay", "1", control, "0")
    said = _line(report, check)
    assert said["control"] == control, report
    assert int(said[found]) >= 1, (
        f"replay control {control!r} injected and {check.strip()} found nothing on seed 0:\n"
        f"{report}"
    )
