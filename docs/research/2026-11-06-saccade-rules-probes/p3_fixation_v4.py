"""Probe 3, rerun on version 4 (2026-11-06): the false-alarm probe of commit 2 in true angle.
(a) the 0.12 deg step at sample 300, sample 298..305 lost; (b) fixation only, 2000 trials of 2 s.
wl-preproc's columns are its true-angle detector at 82380d2 (p2ta), whole and masked."""
from __future__ import annotations

import math
import random
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from versions import v1, v2, v3, cur  # noqa: E402
from p2ta import preproc  # noqa: E402

assert cur.VERSION >= 4, cur.VERSION
DT = 0.002


def fixation(rng, n, noise, heavy, at_deg=(0.0, 0.0)):
    gaze, at = [], []
    for i in range(n):
        if heavy:
            ex = noise * rng.gauss(0, 1) / math.sqrt(rng.gammavariate(1.5, 1 / 1.5))
            ey = noise * rng.gauss(0, 1) / math.sqrt(rng.gammavariate(1.5, 1 / 1.5))
        else:
            ex, ey = rng.gauss(0, noise), rng.gauss(0, noise)
        gaze.append((at_deg[0] + ex, at_deg[1] + ey))
        at.append(i * DT)
    return gaze, at


def online(module, gaze, at):
    d = module.Detector()
    return [(s.start, s.stop, s.flagged, k) for k, (t, g) in enumerate(zip(at, gaze)) if (s := d.accept(t, g)) is not None]


if __name__ == "__main__":
    rng = random.Random(1)
    gaze, at = fixation(rng, 600, 0.02, False)
    gaze = [(x + (0.12 if i >= 300 else 0.0), y) for i, (x, y) in enumerate(gaze)]
    print("(a) whole: v3", online(v3, gaze, at), "v4", online(cur, gaze, at), "v4 detect",
          [(s.start, s.stop, s.flagged) for s in cur.detect(gaze, at)], "pp(v2) whole", preproc(gaze))
    for k in range(298, 306):
        g = list(gaze)
        g[k] = None
        print(f"    lost {k}: v2 {online(v2, g, at)}  v3 {online(v3, g, at)}  v4 {online(cur, g, at)}  "
              f"v3-detect {[(s.start, s.stop, s.flagged) for s in v3.detect(g, at)]}  v4-detect {[(s.start, s.stop, s.flagged) for s in cur.detect(g, at)]}  "
              f"pp(v2) masked {preproc(g)}")
    for where in ((0.0, 0.0), (20.0, 0.0)):
        for heavy in (False, True):
            for losses in (1, 3):
                rng = random.Random(100 + losses + (10 if heavy else 0))
                counts = {"v1": 0, "v2": 0, "v3": 0, "v4": 0, "v3-detect": 0, "v4-detect": 0, "pp(v2)-whole": 0, "pp(v2)-masked": 0}
                for _ in range(2000):
                    gz, at = fixation(rng, 1000, 0.02, heavy, where)
                    g = list(gz)
                    for _ in range(losses):
                        g[rng.randrange(100, 990)] = None
                    counts["v1"] += bool(online(v1, g, at))
                    counts["v2"] += bool(online(v2, g, at))
                    counts["v3"] += bool(online(v3, g, at))
                    counts["v4"] += bool(online(cur, g, at))
                    counts["v3-detect"] += bool(v3.detect(g, at))
                    counts["v4-detect"] += bool(cur.detect(g, at))
                    counts["pp(v2)-whole"] += bool(preproc(gz))
                    counts["pp(v2)-masked"] += bool(preproc(g))
                print(f"(b) fixation at {where}, noise {'t' if heavy else 'gauss'} 0.02 deg, {losses} lost/trial, 2000 trials of 2 s: {counts}")
