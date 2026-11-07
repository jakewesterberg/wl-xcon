"""The review of saccade version 7, its check 1's sweep (its `p1d_sweep.py`'s 1500 cases): minimum-jerk
saccades of 8 to 80 samples and 1° to 20°, each with one or two lost stretches of 1 to 60 samples near
it, against wl-preproc's proof code on branch `proof/eye-lost` at `68b76b6` (unapproved): its
`contract_fixtures.detector_input` and `detect_engbert_kliegl`, flagged and sized as its `build_v3`
writes v3. Prints how many traces' thresholds equal theirs, how many traces' runs equal theirs in
interval, flag and size, and how many differ only by the end after a short loss both repositories
agreed on 2026-11-06, which `68b76b6` predates: each such run starts as theirs and ends later,
flagged, on the first measured velocity after the unknown ones that follow their stop.

Reads wl-preproc from the directory `WLPP_EYE_LOST_SOURCE` names, outside the repository:
`git -C <wl-preproc> archive 68b76b6 wl_preproc | tar -x -C <dir>` (README.md)."""
from __future__ import annotations

import dataclasses
import os
import random
import sys

sys.path.insert(0, os.environ["WLPP_EYE_LOST_SOURCE"])
import numpy as np  # noqa: E402
from wl_preproc.eye.detect import contract_fixtures as cf  # noqa: E402
from wl_preproc.eye.detect.engbert_kliegl import (DEFAULT_EK_PARAMS,  # noqa: E402
                                                  detect_engbert_kliegl)
from wl_preproc.eye.detect.engbert_kliegl import thresholds as their_thresholds  # noqa: E402
from wl_preproc.eye.detect.geometry import TRUE_ANGLE  # noqa: E402
from wl_preproc.eye.detect.labels import Label  # noqa: E402
from wl_preproc.eye.detect.measure import measure_event_run  # noqa: E402
from wl_preproc.eye.detect.velocity import local_velocity  # noqa: E402

import wl_xcon  # noqa: E402
from wl_xcon.saccade import Params, detect, thresholds, velocity  # noqa: E402

print("wl_xcon:", wl_xcon.__file__)
print("wl_preproc:", cf.__file__)
FS = 500.0


def minimum_jerk(onset: int, duration: int, amplitude: float, n: int, noise: float, seed: int):
    rng = random.Random(seed)
    gaze = []
    for i in range(n):
        tau = min(max((i - onset) / duration, 0.0), 1.0)
        reach = 10 * tau ** 3 - 15 * tau ** 4 + 6 * tau ** 5
        gaze.append((amplitude * reach + rng.gauss(0, noise), rng.gauss(0, noise)))
    return gaze, [i / FS for i in range(n)]


def theirs(trace):
    """Their runs, `(start, stop, flagged, size)`, and their thresholds."""
    gaze_deg = [None if p is None else list(p) for p in trace]
    gaze, offered = cf.detector_input(gaze_deg, [None if p is not None else "lost" for p in gaze_deg],
                                      FS, cf.MAX_LOST_MS)
    speed = local_velocity(gaze, FS)
    lost = np.array([entry is Label.LOST for entry in offered])
    known = np.array([entry is None for entry in offered])
    params = dataclasses.replace(DEFAULT_EK_PARAMS, geometry=TRUE_ANGLE)
    runs = []
    for run in detect_engbert_kliegl(gaze, speed, offered, FS, params):
        measured = measure_event_run(gaze, speed, offered, run.start, run.stop, FS, geometry=TRUE_ANGLE,
                                     runs_end_before_landing=False, min_measured_ms=None)
        runs.append((int(run.start), int(run.stop), bool(lost[max(run.start - 2, 0):run.stop].any()),
                     float(measured.amplitude_deg)))
    return runs, their_thresholds(speed, known, params)


rng = random.Random(20261106)
equal_eta = equal = agreed_end = other = 0
examples = []
for case in range(1500):
    duration = rng.randint(8, 80)
    amplitude = rng.uniform(1.0, 20.0)
    onset = rng.randint(60, 400)
    gaze, at = minimum_jerk(onset, duration, amplitude, 560, rng.choice([0.005, 0.01, 0.03]), case)
    k = rng.randint(onset - 10, onset + duration + 10)
    m = rng.choice([1, 2, 3, 5, 10, 20, 23, 24, 25, 26, 30, 60])
    stretches = [range(k, min(k + m, 555))]
    if rng.random() < 0.3:
        k2 = rng.randint(onset - 10, onset + duration + 10)
        stretches.append(range(k2, min(k2 + rng.randint(1, 30), 555)))
    trace = list(gaze)
    for stretch in stretches:
        for i in stretch:
            trace[i] = None
    their_runs, their_eta = theirs(trace)
    velocities = velocity(trace, at, Params())
    eta = thresholds(velocities, Params())
    equal_eta += abs(eta[0] - their_eta[0]) <= 1e-9 and abs(eta[1] - their_eta[1]) <= 1e-9
    ours = [(s.start, s.stop, s.flagged, s.amplitude_deg) for s in detect(trace, at)]

    def same(a, b):
        return a[:3] == b[:3] and abs(a[3] - b[3]) <= 1e-3

    if len(ours) == len(their_runs) and all(same(a, b) for a, b in zip(ours, their_runs)):
        equal += 1
        continue
    explained = len(ours) == len(their_runs) and all(
        same(a, b) or (a[0] == b[0] and a[1] > b[1] and a[2]
                       and all(velocities[n] is None for n in range(b[1], a[1] - 1))
                       and velocities[a[1] - 1] is not None)
        for a, b in zip(ours, their_runs))
    if explained:
        agreed_end += 1
    else:
        other += 1
        if len(examples) < 6:
            examples.append((case, onset, duration, [(s.start, s.stop) for s in stretches], ours,
                             their_runs))
print(f"1500 traces: thresholds equal to theirs (1e-9) in {equal_eta}; runs equal in {equal}; "
      f"differ only by the agreed end after a short loss in {agreed_end}; otherwise {other}")
for example in examples:
    print(example)
