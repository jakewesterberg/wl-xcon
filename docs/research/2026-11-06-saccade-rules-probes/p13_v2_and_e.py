"""Probe 13 (2026-11-06): v2 and the PI's measured-samples rule (commit 2) side by side.

(a) wl-preproc's own true-angle detector (82380d2 export) on each v2 trace reproduces the file's runs
    (that this probe drives it as the file was made), and ours (the worktree's, version 4) does too.
(b) Where they part: a run meeting an unavailable sample. A 12-sample 8 deg saccade and a 4-sample
    4 deg one (tests/test_saccade.py's `_trace`), centred and at (20, 0) moving up, one sample lost from
    3 before the run to 12 into it: ours online and batch; theirs with the frame whole, with the lost
    sample alone unavailable (as v2 masks one), and with their validity mask (the frame missing there
    too). Needs WLPP_V2_SOURCE (README.md).
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).parent
ROOT = HERE.resolve().parents[2]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "tests"))
from p2ta import FS, TA, detect_engbert_kliegl, local_velocity, preproc, preproc_unavailable  # noqa: E402
from versions import cur  # noqa: E402

assert cur.VERSION >= 4, cur.VERSION
v2 = json.loads((ROOT / "tests/fixtures/wl-preproc/saccade-v2.json").read_bytes())
for t in v2["traces"]:
    g = np.array(t["gaze_deg"], dtype=float)
    av = np.array(t["available"] or [None] * len(g), dtype=object)
    theirs = [(int(r.start), int(r.stop), r.label.value) for r in detect_engbert_kliegl(g, local_velocity(g, FS), av, FS, TA)]
    want = [(r["start"], r["stop"], r["label"]) for r in t["runs"]]
    gaze = [None if m is not None else (float(x), float(y)) for (x, y), m in zip(t["gaze_deg"], t["available"] or [None] * len(g))]
    at = [i / FS for i in range(len(gaze))]
    ours = [(s.start, s.stop) for s in cur.detect(gaze, at)]
    print(f"(a) {t['name']:<30} theirs reproduce the file: {theirs == want}; ours batch == file intervals: {ours == [w[:2] for w in want]}")


def trace(onset, duration, dx, dy, start=(0.0, 0.0), n=600, noise=0.02, seed=3):
    rng = random.Random(seed)
    x, y = start
    gaze = []
    for i in range(n):
        if onset <= i < onset + duration:
            x += dx / duration
            y += dy / duration
        gaze.append((x + rng.gauss(0, noise), y + rng.gauss(0, noise)))
    return gaze, [i / FS for i in range(n)]


def online(gaze, at):
    d = cur.Detector()
    return [(s.start, s.flagged) for t, g in zip(at, gaze) if (s := d.accept(t, g)) is not None]


for label, args in (("12-sample 8 deg right, centred", (200, 12, 8.0, 0.0)),
                    ("4-sample 4 deg right, centred", (200, 4, 4.0, 0.0)),
                    ("12-sample 2 deg up from (20, 0)", (200, 12, 0.0, 2.0, (20.0, 0.0)))):
    gaze, at = trace(*args)
    whole = [(s.start, s.stop) for s in cur.detect(gaze, at)]
    start = whole[0][0]
    print(f"\n(b) {label}: ours whole {whole}, theirs whole {preproc_unavailable(gaze, (0.0, 0.0))}")
    print(f"    {'lost':>5} | {'ours online (start, flag)':<26} | {'ours batch':<22} | {'theirs, it alone unavailable':<30} | theirs, frame missing, mask")
    for into in range(-3, 13):
        g = list(gaze)
        g[start + into] = None
        fill = gaze[start + into]
        print(f"    {into:>+5} | {str(online(g, at)):<26} | {str([(s.start, s.stop, s.flagged) for s in cur.detect(g, at)]):<22} | "
              f"{str(preproc_unavailable(g, fill)):<30} | {preproc(g)}")
