"""The review of saccade version 7, its check 3 (its `p3_trailing.py`, widened): a short loss at a
saccade's end, within the 50 ms bound, batch. Minimum-jerk saccades of 8 to 40 samples and 2° to 15°
from sample 200 (sd 0.01°), each losing 1 to 24 samples from three into it to two past its end;
versions 6 (`d932cb3`) and 7 (`16a5961`), read from this repository's history, against the working
tree's (`cur`). Prints how many runs version 7 cut back to before the loss and reported unflagged,
the working tree's differences from version 6 by kind, and the smallest size as a share of the
movement under each."""
from __future__ import annotations

import collections
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from versions import _load, cur  # noqa: E402

v6 = _load("saccade_v6", "d932cb3")
v7 = _load("saccade_v7", "16a5961")
assert (v6.VERSION, v7.VERSION) == (6, 7)
print("cur is version", cur.VERSION)
FS = 500.0


def minimum_jerk(duration: int, amplitude: float, onset: int = 200, n: int = 600,
                 noise: float = 0.01, seed: int = 3):
    rng = random.Random(seed)
    gaze = []
    for i in range(n):
        tau = min(max((i - onset) / duration, 0.0), 1.0)
        reach = 10 * tau ** 3 - 15 * tau ** 4 + 6 * tau ** 5
        gaze.append((amplitude * reach + rng.gauss(0, noise), rng.gauss(0, noise)))
    return gaze, [i / FS for i in range(n)]


def runs(module, trace, at):
    return [(s.start, s.stop, s.flagged, s.amplitude_deg) for s in module.detect(trace, at)]


cut = 0
kinds = collections.Counter()
smallest = {"7": 1.0, "cur": 1.0}
total = 0
for duration in (8, 12, 20, 30, 40):
    for amplitude in (2.0, 8.0, 15.0):
        gaze, at = minimum_jerk(duration, amplitude)
        for first in range(203, 200 + duration + 3):
            for m in (1, 2, 3, 4, 6, 10, 15, 20, 24):
                trace = list(gaze)
                for k in range(first, first + m):
                    trace[k] = None
                a, b, c = runs(v6, trace, at), runs(v7, trace, at), runs(cur, trace, at)
                total += 1
                for name, found in (("7", b), ("cur", c)):
                    for run in found:
                        smallest[name] = min(smallest[name], run[3] / amplitude)
                if len(a) == len(b) == 1 and a[0][2] and not b[0][2] and b[0][1] < a[0][1]:
                    cut += 1
                one = len(a) == len(c) == 1
                if c == a:
                    kinds["as version 6"] += 1
                elif (one and (a[0][0], a[0][2]) == (c[0][0], c[0][2]) and c[0][1] == a[0][1] + 1
                      and abs(c[0][3] - a[0][3]) < 0.05):
                    kinds["version 6's run and its landing sample, size within 0.05 deg"] += 1
                elif m == 24 and len(c) == 1 and c[0][2] and c[0][1] > first + m:
                    kinds["a 50 ms loss version 6 ended the run at, carried (R11, version 7) to "
                          "the landing"] += 1
                elif one and a[0][2] and not c[0][2] and a[0][1] == c[0][1] and b[0][2] is False:
                    apart = "" if a[0][0] == c[0][0] else ", its start a sample earlier (M2)"
                    kinds["unflagged since version 7, the loss after the run (R18)" + apart] += 1
                elif (one and a[0][2] == c[0][2] and abs(a[0][0] - c[0][0]) == 1
                      and abs(a[0][3] - c[0][3]) < 0.05):
                    kinds["a start a sample apart, the scale's (M2), size within 0.05 deg"] += 1
                else:
                    kinds["else"] += 1
print(f"{total} saccades: version 7 cut {cut} back to before the loss, unflagged")
print("the working tree against version 6:")
for kind, count in kinds.most_common():
    print(f"  {count:5d}  {kind}")
print("smallest size as a share of the movement:", {k: round(v, 3) for k, v in smallest.items()})
