"""EYE-19's 2026-10-30 sentence, as corrected: how far after the eye's first sample at rest a run
carried through a short loss stops (the review of version 8's `q9_rest.py`, its N4(a), kept here as it
ran). Abrupt (linear) saccades of 4 to 20 samples, 8°, noise 0.01°, at rest from sample r; a loss of
m samples (1 to 24) starting anywhere from r - 6 to r + 3: for each run carried through the loss to
its landing (a stop past the loss), stop - r - m, counted, and the worst case. `detect`; the online
form closes with the same stop (`last_stop`). Run it with each version's tree on `PYTHONPATH`."""
import random
from collections import Counter

import wl_xcon
from wl_xcon.saccade import VERSION, detect

print("wl_xcon:", wl_xcon.__file__, "VERSION", VERSION)
FS = 500.0
excess = Counter()
worst = None
for dur in (4, 6, 8, 12, 20):
    onset = 200
    r = onset + dur
    rng = random.Random(dur)
    g = []
    for i in range(500):
        f = min(max((i - onset) / dur, 0.0), 1.0)
        g.append((8.0 * f + rng.gauss(0, 0.01), rng.gauss(0, 0.01)))
    at = [i / FS for i in range(500)]
    for first in range(r - 6, r + 4):
        for m in (1, 2, 3, 5, 10, 20, 24):
            tr = list(g)
            for k in range(first, first + m):
                tr[k] = None
            for s in detect(tr, at):
                if s.start < r and s.stop > first + m:
                    e = s.stop - r - m
                    excess[e] += 1
                    if worst is None or e > worst[0]:
                        worst = (e, dur, first, m, (s.start, s.stop, s.flagged))
print("stop - first sample at rest - loss length, over carried runs:", sorted(excess.items()))
print("worst (excess, duration, first lost, m, run):", worst)
