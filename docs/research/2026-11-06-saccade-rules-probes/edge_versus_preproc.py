"""Saccade version 9 at a trace's edges, against wl-preproc's code on its branch `replay2/eye-lost` at
`bb6180e` (`contract_fixtures.detector_input` and `detect_engbert_kliegl`, flagged as its `build_v3`
flags): the review of version 8's `q8_edge.py` (its N3), widened to every one of a trace's first four
and last five samples. An 8° minimum-jerk saccade over 30 samples from sample 0, or from 580 of 600
(still moving at the end), one sample lost. Runs `(start, stop, flagged)`, ours and theirs, and their
labels for the samples around the loss (`.` offered, `L` carried, `I` withheld).

Run it with each version's tree on `PYTHONPATH` (README.md); reads wl-preproc from the directory
`WLPP_BB6180E_SOURCE` names, outside the repository: wl-preproc's `wl_preproc` package at `bb6180e`."""
import dataclasses
import os
import random
import sys

sys.path.insert(0, os.environ["WLPP_BB6180E_SOURCE"])
import numpy as np  # noqa: E402
from wl_preproc.eye.detect import contract_fixtures as cf  # noqa: E402
from wl_preproc.eye.detect.engbert_kliegl import DEFAULT_EK_PARAMS, detect_engbert_kliegl  # noqa: E402
from wl_preproc.eye.detect.geometry import TRUE_ANGLE  # noqa: E402
from wl_preproc.eye.detect.labels import Label  # noqa: E402
from wl_preproc.eye.detect.velocity import local_velocity  # noqa: E402

import wl_xcon  # noqa: E402
from wl_xcon.saccade import VERSION, detect  # noqa: E402

print("wl_xcon:", wl_xcon.__file__, "VERSION", VERSION, "| wl_preproc:", cf.__file__)
FS = 500.0


def minimum_jerk(onset, duration=30, amplitude=8.0, n=600, noise=0.01, seed=3):
    rng = random.Random(seed)
    gaze = []
    for i in range(n):
        tau = min(max((i - onset) / duration, 0.0), 1.0)
        gaze.append((amplitude * (10 * tau ** 3 - 15 * tau ** 4 + 6 * tau ** 5) + rng.gauss(0, noise),
                     rng.gauss(0, noise)))
    return gaze, [i / FS for i in range(n)]


for onset, losses in ((0, (0, 1, 2, 3)), (580, (595, 596, 597, 598, 599))):
    gaze, at = minimum_jerk(onset)
    for lost in losses:
        trace = list(gaze)
        trace[lost] = None
        gaze_deg = [None if p is None else list(p) for p in trace]
        positions, offered = cf.detector_input(gaze_deg, [None if p is not None else "lost" for p in gaze_deg],
                                               FS, cf.MAX_LOST_MS)
        carried = np.array([entry is Label.LOST for entry in offered])
        theirs = [(int(r.start), int(r.stop), bool(carried[max(r.start - 2, 0):r.stop].any()))
                  for r in detect_engbert_kliegl(positions, local_velocity(positions, FS), offered, FS,
                                                 dataclasses.replace(DEFAULT_EK_PARAMS, geometry=TRUE_ANGLE))]
        ours = [(s.start, s.stop, s.flagged) for s in detect(trace, at)]
        labels = "".join("." if e is None else ("L" if e is Label.LOST else "I") for e in offered)
        lo, hi = max(lost - 4, 0), min(lost + 5, len(trace))
        print(f"onset {onset:3d}, sample {lost:3d} lost: ours {ours} theirs {theirs} "
              f"{'same' if ours == theirs else 'DIFFER'}; their labels [{lo}:{hi}] {labels[lo:hi]}")
