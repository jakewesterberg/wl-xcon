#!/usr/bin/env python3
"""What a demo's ease slack costs and buys, on an injected clock (demo mode §14 item 9; the
build's re-review, N4).

CLAUDE.md: no timing claim without a measurement. `pointer.EASE_SLACK_S` eases a pointer report
that came after a gap over that gap and 25 ms more, so a glide whose reports arrive a little
irregularly stays one saccade (the whole-build review's I2). What it costs is said beside it
from this script's output, and only from it.

**What runs.** The rig's own code, in process: `pointer.Source` and `pointer.worlds` read a page's
reports, `run.run_trial` plays the trial, and the saccade detector and the task's rules score it,
exactly as a demo's world does. **The clock is injected**: `pointer.Pace` waits on a clock this
script moves, and a report is read once that clock has reached the moment it arrives. So nothing
here is timed on the machine it runs on, and a result is the same on any machine; the report
timings are the page's as this script assumes them, never measured.

**Two probes, each with `EASE_SLACK_S` at 0 and at its value:**

- **Glides** (`glides`): the pop-out search, from the wl-xtasks checkout, answered by a glide on the
  minimum-jerk profile from the fixation point to the odd disc 8° away, 400 ms and 600 ms long,
  `--seeds` seeds each (the mouse's noise and the page's timing), as `tests/test_pointer.py`'s glide
  test plays it. The page reports every animation frame (60 Hz) while the pointer moves and every
  100 ms while it is still, each report reaching the rig either 0 ms late (`regular`) or half a
  round trip late, the round trip drawn for each from 2 to 12 ms (`jittered`). For each trial: how
  it ended (`correct`, `landing bound` -- the pop-out's `flight` ended by its own 0.3 s bound --,
  `second look`, or the outcome), when the eye left the fixation window after the glide began
  (`exit_ms`), and how long its flight lasted (`flight_ms`).
- **Merges** (`merges`): a move 5° in 100 ms, a stop of S ms in the page's reports, and a move 5°
  more, the reports jittered as above, `--merge-seeds` seeds per stop; how many saccades over 0.2°
  the detector confirmed. One is two moves merged into one saccade.

    python tools/measure_demo_ease_slack.py --out docs/measurements/dev-machine/2026-11-16-demo-ease-slack

**What this is not.** A measurement of a rig, a browser or a network: the report timings are
assumed, and the clock is the script's. It says what the demo's easing does with reports that
arrive so, nothing more.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import random
import shutil
import statistics
import subprocess
import sys
from collections import deque
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# This checkout's package, never an installed copy.
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from wl_xcon import pointer, saccade, service  # noqa: E402
from wl_xcon.cli import _load_task  # noqa: E402
from wl_xcon.run import Recorded, run_trial  # noqa: E402
from wl_xcon.task import After, On, Outcome, State, Trial  # noqa: E402

TASK = Path("tasks") / "popout_search.py"
#: A demo's frame period, `service.FRAME_PERIOD`'s.
FRAME = service.FRAME_PERIOD
#: The page's animation frames, at 60 Hz, and its still pointer's report interval, in seconds.
ANIMATION = 1 / 60
STILL = 0.1
#: Where the injected clock starts: anywhere but zero.
T0 = 100.0
GLIDES = (0.4, 0.6)
STOPS_MS = (0, 17, 33, 50, 67, 83, 100, 150, 200)
SLACKS = (0.0, pointer.EASE_SLACK_S)
NONE = (0,) * pointer.KEYS


def xtasks() -> Path | None:
    """The wl-xtasks checkout holding the pop-out, looked for as the tests look: the link at this
    repository's root, then beside it."""
    for candidate in (ROOT / "wl-xtasks", ROOT.parent / "wl-xtasks"):
        if (candidate / TASK).is_file():
            return candidate
    return None


class _Clock:
    """The clock `pointer.Pace` waits on, moved by its sleep."""

    def __init__(self) -> None:
        self.t = T0

    def __call__(self) -> float:
        return self.t

    def sleep(self, seconds: float) -> None:
        self.t += seconds


class _Page:
    """The gaze socket as a page fills it: each report read once the clock reaches its arrival."""

    def __init__(self, clock: _Clock) -> None:
        self.clock, self.waiting, self.seq = clock, deque(), 0

    def report(self, at: float, x: float, y: float) -> None:
        self.seq += 1
        self.waiting.append((at, pointer.pack(self.seq, x, y, over=True, b=False, button=False,
                                              held=0, presses=NONE)))

    def receive(self, buffer: bytearray) -> int:
        if not self.waiting or self.waiting[0][0] > self.clock.t + 1e-9:
            return -1
        message = self.waiting.popleft()[1]
        buffer[:len(message)] = message
        return len(message)


def _rig(seed: int):
    clock = _Clock()
    page = _Page(clock)
    source = pointer.Source(page.receive, seed=seed)
    return clock, page, source, pointer.Pace(FRAME, clock=clock, sleep=clock.sleep)


def _sender(page: _Page, seed: int, jittered: bool, stream: str = "the page's round trips"):
    """A page's report, half a round trip late when `jittered`, the round trips drawn from
    `stream`: the glide test's, `tests/test_pointer.py`'s, or the merges' own."""
    timing = random.Random(f"{seed}: {stream}")

    def sent(at: float, x: float, y: float) -> None:
        page.report(at + (timing.uniform(0.002, 0.012) / 2 if jittered else 0.0), x, y)
    return sent


def _jerk(tau: float) -> float:
    tau = min(max(tau, 0.0), 1.0)
    return tau ** 3 * (10 - 15 * tau + 6 * tau * tau)


def _glide(sent, start: float, x0: float, x1: float, duration: float) -> float:
    """Reports an animation frame apart from `start`, `x0` to `x1` over `duration`; the last's
    moment."""
    k = 0
    while True:
        at = start + k * ANIMATION
        sent(at, x0 + (x1 - x0) * _jerk(k * ANIMATION / duration), 0.0)
        if k * ANIMATION >= duration:
            return at
        k += 1


def glide_trial(task, glide_s: float, seed: int, jittered: bool) -> dict:
    """One pop-out trial answered by a glide (the module docstring)."""
    trial = task.trial
    values = {param.name: param.start for param in task.params if param.start is not None}
    odd, among = task.pool.choices[0]
    values.update(odd_color=odd, distractor_color=among, set_size=4, array_rotation=0.0,
                  response_deadline=3.0, inter_trial=0.3, fix_hold=0.3, target_hold=0.1,
                  timeout=0.0)
    clock, page, source, pace = _rig(seed)
    sent = _sender(page, seed, jittered)
    for k in range(5):
        sent(T0 + STILL * k, -4.0, -4.0)
    for k in range(6):
        sent(T0 + 0.5 + STILL * k, 0.0, 0.0)
    start = T0 + 1.1
    last = _glide(sent, start, 0.0, 8.0, glide_s)
    for j in range(1, 40):
        sent(last + STILL * j, 8.0, 0.0)
    world = pointer.worlds(source, pace=pace)(trial, values, 0)
    began: dict = {}
    told = world.began

    def beginning(state: str, frame: int) -> None:
        began.setdefault(state, frame)
        told(state, frame)

    world.began = beginning
    outcome = run_trial(trial, world, FRAME, values=values, effects=Recorded()).outcome
    flight = began.get("flight")
    end = began.get("on_target", began.get("astray"))
    how = outcome.value
    if outcome is Outcome.ABORT and "astray" in began:
        flown = (began["astray"] - flight) * FRAME
        how = "landing bound" if flown >= 0.3 - FRAME / 2 else "second look"
    return {
        "ended": how,
        "exit_ms": None if flight is None else round(((flight - 1) * FRAME - 1.1) * 1000, 3),
        "flight_ms": None if flight is None or end is None else round((end - flight) * FRAME
                                                                       * 1000, 3),
    }


def merge_trial(stop_ms: float, seed: int) -> int:
    """A move, a stop of `stop_ms` in the page's reports, a move: the saccades over 0.2° the
    detector confirmed."""
    confirmed: list = []
    accept = saccade.Detector.accept

    def counted(detector, at, gaze):
        found = accept(detector, at, gaze)
        if found is not None:
            confirmed.append(found)
        return found

    saccade.Detector.accept = counted
    try:
        trial = Trial(start="s", states=[State("s", go=[On(After(2.5), Outcome.CORRECT)])])
        clock, page, source, pace = _rig(seed)
        sent = _sender(page, seed, True, "round trips")
        for k in range(10):
            sent(T0 + STILL * k, 0.0, 0.0)
        end = _glide(sent, T0 + 1.0, 0.0, 5.0, 0.1)
        moves_on = end + max(stop_ms / 1000, ANIMATION)
        still = end + STILL
        while still < moves_on - 1e-9:
            sent(still, 5.0, 0.0)
            still += STILL
        end = _glide(sent, moves_on, 5.0, 10.0, 0.1)
        for j in range(1, 10):
            sent(end + STILL * j, 10.0, 0.0)
        world = pointer.worlds(source, pace=pace)(trial, {}, 0)
        run_trial(trial, world, FRAME, values={}, effects=Recorded())
    finally:
        saccade.Detector.accept = accept
    return sum(1 for found in confirmed if found.amplitude_deg > 0.2)


def _with_slack(slack: float, act):
    kept = pointer.EASE_SLACK_S
    pointer.EASE_SLACK_S = slack
    try:
        return act()
    finally:
        pointer.EASE_SLACK_S = kept


def glides(task, seeds: int) -> list[dict]:
    rows = []
    for glide_s in GLIDES:
        for jittered in (False, True):
            for slack in SLACKS:
                trials = _with_slack(slack, lambda: [glide_trial(task, glide_s, seed, jittered)
                                                     for seed in range(seeds)])
                ended: dict = {}
                for one in trials:
                    ended[one["ended"]] = ended.get(one["ended"], 0) + 1
                exits = [one["exit_ms"] for one in trials if one["exit_ms"] is not None]
                flights = [one["flight_ms"] for one in trials if one["flight_ms"] is not None]
                rows.append({
                    "glide_ms": round(glide_s * 1000), "timing": "jittered" if jittered else
                    "regular", "slack_ms": round(slack * 1000), "seeds": seeds, "ended": ended,
                    "exit_ms_mean": round(statistics.mean(exits), 2) if exits else None,
                    "flight_ms_mean": round(statistics.mean(flights), 2) if flights else None,
                    "trials": trials,
                })
    return rows


def merges(seeds: int, stops_ms=STOPS_MS) -> list[dict]:
    rows = []
    for stop in stops_ms:
        for slack in SLACKS:
            counts = _with_slack(slack, lambda: [merge_trial(stop, seed) for seed in range(seeds)])
            rows.append({"stop_ms": stop, "slack_ms": round(slack * 1000), "seeds": seeds,
                         "one": counts.count(1), "two": counts.count(2),
                         "other": len(counts) - counts.count(1) - counts.count(2),
                         "counts": counts})
    return rows


def table(glide_rows: list[dict], merge_rows: list[dict]) -> str:
    lines = ["| Glide | Reports | Slack | Ended | Exit, mean | Flight, mean |",
             "|---|---|---|---|---|---|"]
    for row in glide_rows:
        ended = ", ".join(f"{how} {n}" for how, n in sorted(row["ended"].items()))
        lines.append(f"| {row['glide_ms']} ms | {row['timing']} | {row['slack_ms']} ms | {ended} "
                     f"| {row['exit_ms_mean']} ms | {row['flight_ms_mean']} ms |")
    lines += ["", "| Stop | Slack | One saccade | Two | Other |", "|---|---|---|---|---|"]
    for row in merge_rows:
        lines.append(f"| {row['stop_ms']} ms | {row['slack_ms']} ms | {row['one']} | {row['two']} "
                     f"| {row['other']} |")
    return "\n".join(lines) + "\n"


def _git(*args: str) -> str:
    try:
        return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True,
                              check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return ""


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--seeds", type=int, default=100)
    parser.add_argument("--merge-seeds", type=int, default=10)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    found = xtasks()
    if found is None:
        raise SystemExit("no wl-xtasks checkout holding tasks/popout_search.py, at this "
                         "repository's root or beside it")
    task = _load_task(found / TASK)
    started = datetime.now().astimezone().isoformat(timespec="seconds")
    glide_rows = glides(task, args.seeds)
    merge_rows = merges(args.merge_seeds)
    args.out.mkdir(parents=True, exist_ok=True)
    script = Path(__file__).resolve()
    shutil.copyfile(script, args.out / script.name)
    results = {
        "started": started, "ended": datetime.now().astimezone().isoformat(timespec="seconds"),
        "git_head": _git("rev-parse", "HEAD"), "git_status": _git("status", "--short"),
        "script_sha256": hashlib.sha256(script.read_bytes()).hexdigest(),
        "task": str(TASK), "xtasks_head": _git("-C", str(found), "rev-parse", "HEAD"),
        "python": platform.python_version(), "host": platform.platform(),
        "ease_slack_s": pointer.EASE_SLACK_S, "live_s": pointer.LIVE_S, "frame_s": FRAME,
        "seeds": args.seeds, "merge_seeds": args.merge_seeds,
        "glides": glide_rows, "merges": merge_rows,
    }
    (args.out / "results.json").write_text(json.dumps(results, indent=1) + "\n")
    text = table(glide_rows, merge_rows)
    (args.out / "table.md").write_text(text)
    print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
