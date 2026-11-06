"""Probe 12 (2026-11-06): real saccades straddling lost samples that v2 reported and the worktree's
detector does not. A saccade of every duration 2..30 samples (500 Hz), at amplitudes 0.5 to 15 deg,
linear and raised-cosine profiles, Gaussian noise 0.02 deg; k = 1, 2 or 3 consecutive samples lost at
every offset from 6 before its first moving sample to 4 after its last. For each duration: cases v2
reports and cur misses, and the same for v1. Run with PYTHONPATH=<worktree>.
"""
from __future__ import annotations

import math
import random
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from versions import v1, v2, cur  # noqa: E402

DT = 0.002


def trace(onset, dur, amp, profile, seed, n=500, noise=0.02):
    rng = random.Random(seed)
    gaze = []
    for i in range(n):
        if i < onset:
            f = 0.0
        elif i < onset + dur:
            u = (i - onset + 1) / dur
            f = u if profile == "linear" else (1 - math.cos(math.pi * u)) / 2
        else:
            f = 1.0
        gaze.append((amp * f + rng.gauss(0, noise), rng.gauss(0, noise)))
    return gaze, [i * DT for i in range(n)]


def online(module, gaze, at):
    d = module.Detector()
    return [s.start for t, g in zip(at, gaze) if (s := d.accept(t, g)) is not None]


print("cur is version", cur.VERSION, "from", cur.__file__)
# by (k, whole-trace run length as cur.detect gives it): cases v2 reports, of which cur misses, of which v1 misses
by_run = defaultdict(lambda: [0, 0, 0])
by_amp = defaultdict(lambda: [0, 0, None])  # (k, amp) -> [v2 reports, cur misses, longest duration missed]
shortest = {}
new_in_cur = 0
seed = 0
onset = 220
for dur in range(2, 31):
    for amp in (0.5, 1.0, 2.0, 4.0, 8.0, 15.0):
        for profile in ("linear", "cosine"):
            seed += 1
            gaze, at = trace(onset, dur, amp, profile, seed)
            if not online(v2, gaze, at):
                continue
            whole = cur.detect(gaze, at)
            run = whole[0].stop - whole[0].start if len(whole) == 1 else None
            for k in (1, 2, 3):
                for off in range(-6, dur + 5):
                    g = list(gaze)
                    for j in range(onset + off, onset + off + k):
                        g[j] = None
                    a, b, c = online(v1, g, at), online(v2, g, at), online(cur, g, at)
                    if c and not b:
                        new_in_cur += 1
                    if not b:
                        continue
                    row = by_run[(k, run)]
                    row[0] += 1
                    by_amp[(k, amp)][0] += 1
                    if not c:
                        row[1] += 1
                        row[2] += not a
                        cell = by_amp[(k, amp)]
                        cell[1] += 1
                        cell[2] = dur if cell[2] is None else max(cell[2], dur)
                        if (k not in shortest) or dur < shortest[k][0]:
                            shortest[k] = (dur, amp, profile, off, run)
for k in (1, 2, 3):
    tot = sum(r[0] for (kk, _), r in by_run.items() if kk == k)
    mis = sum(r[1] for (kk, _), r in by_run.items() if kk == k)
    mv1 = sum(r[2] for (kk, _), r in by_run.items() if kk == k)
    print(f"{k} lost: of {tot} cases v2 reports, cur misses {mis} (v1 misses {mv1} of those); "
          f"shortest missed: {shortest.get(k)} (duration samples, amplitude, profile, first lost offset, whole run length)")
    runs = sorted(r for (kk, r), row in by_run.items() if kk == k and row[1] and r is not None)
    print(f"   whole-trace run lengths with a miss: {runs}; longest {max(runs) if runs else None}")
    for (kk, r), row in sorted(by_run.items(), key=lambda x: (x[0][0], x[0][1] or 0)):
        if kk == k and row[1]:
            print(f"     run {r}: cur misses {row[1]} of {row[0]} (v1 also misses {row[2]})")
    for amp in (0.5, 1.0, 2.0, 4.0, 8.0, 15.0):
        cell = by_amp[(k, amp)]
        print(f"   amplitude {amp:4} deg: cur misses {cell[1]:4d} of {cell[0]:4d}; longest movement missed {cell[2]} samples")
print("cases cur reports and v2 does not:", new_in_cur)
