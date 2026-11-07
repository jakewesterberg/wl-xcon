"""Reviewer's probe 3: what v2 newly reports where the eye made NO saccade.

A run is a saccade once `min_duration_samples` long counting unknown velocities, and one lost
sample leaves five unknown. So one supra-threshold velocity just before a lost sample, and an
inside one just after the five unknowns, is a six-sample run: `detect` reports it, flagged, and
v2 now reports it live, where v1 never did. wl-preproc never does: its mask ends a run.

(a) one constructed case: a 0.12 deg one-sample step in fixation, a sample lost three after it.
(b) fixation only (no saccade at all), Gaussian or heavy-tailed noise, one or three single lost
    samples per 2 s trial: how many trials does v2 report a saccade in, v1, detect, wl-preproc?
"""
from __future__ import annotations

import math
import random
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from versions import v1, v2, cur  # noqa: E402
from p2_offline import online, preproc  # noqa: E402

DT = 0.002


def fixation(rng, n, noise, heavy):
    gaze, at = [], []
    for i in range(n):
        if heavy:
            ex = noise * rng.gauss(0, 1) / math.sqrt(rng.gammavariate(1.5, 1 / 1.5))
            ey = noise * rng.gauss(0, 1) / math.sqrt(rng.gammavariate(1.5, 1 / 1.5))
        else:
            ex, ey = rng.gauss(0, noise), rng.gauss(0, noise)
        gaze.append((ex, ey))
        at.append(i * DT)
    return gaze, at


# (a)
rng = random.Random(1)
gaze, at = fixation(rng, 600, 0.02, False)
step = 0.12
gaze = [(x + (step if i >= 300 else 0.0), y) for i, (x, y) in enumerate(gaze)]
print("cur is version", cur.VERSION)
print("(a) whole: v1", online(v1, gaze, at), "v2", online(v2, gaze, at), "cur", online(cur, gaze, at),
      "v2 detect", [(s.start, s.stop, s.flagged) for s in v2.detect(gaze, at)],
      "cur detect", [(s.start, s.stop, s.flagged) for s in cur.detect(gaze, at)], "pp", preproc(gaze))
for k in range(298, 306):
    g = list(gaze)
    g[k] = None
    a, b, c = online(v1, g, at), online(v2, g, at), online(cur, g, at)
    d2 = [(s.start, s.stop, s.flagged, round(s.amplitude_deg, 3)) for s in v2.detect(g, at)]
    d = [(s.start, s.stop, s.flagged, round(s.amplitude_deg, 3)) for s in cur.detect(g, at)]
    print(f"    lost {k}: v1 {a}  v2 {b}  cur {c}  v2-detect {d2}  cur-detect {d}  pp-nan {preproc(g)}  pp-whole {preproc(gaze)}")

# (b)
for heavy in (False, True):
    for losses in (1, 3):
        rng = random.Random(100 + losses + (10 if heavy else 0))
        trials = 2000
        counts = {"v1": 0, "v2": 0, "cur": 0, "v2-detect": 0, "cur-detect": 0, "pp-whole": 0, "pp-nan": 0}
        amps = []
        for _ in range(trials):
            gaze, at = fixation(rng, 1000, 0.02, heavy)
            g = list(gaze)
            for _ in range(losses):
                g[rng.randrange(100, 990)] = None
            r1, r2, r3 = online(v1, g, at), online(v2, g, at), online(cur, g, at)
            counts["v1"] += bool(r1)
            counts["v2"] += bool(r2)
            counts["cur"] += bool(r3)
            counts["v2-detect"] += bool(v2.detect(g, at))
            counts["cur-detect"] += bool(cur.detect(g, at))
            counts["pp-whole"] += bool(preproc(gaze))
            counts["pp-nan"] += bool(preproc(g))
            if r2 and not r1:
                det = v2.Detector()
                for t, x in zip(at, g):
                    s = det.accept(t, x)
                    if s is not None:
                        amps.append(round(s.amplitude_deg, 3))
        print(f"(b) fixation only, noise {'t' if heavy else 'gauss'} 0.02 deg, {losses} lost/trial, "
              f"{trials} trials of 2 s: trials with a saccade reported: {counts}; v2-only amplitudes "
              f"(deg) {sorted(amps)[:12]}{' ...' if len(amps) > 12 else ''}")
