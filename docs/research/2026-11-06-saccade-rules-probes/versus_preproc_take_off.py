"""Saccade version 11 against wl-preproc's code at `5772c2e` (its branch `feat/eye-lost-and-region`,
not merged there): a run whose take-off a carried loss hides is measured from the last sample with a
known velocity before that loss (wl-preproc's final review of 2026-11-07, its I2, agreed by both
sessions that day; in their code since `fe0e2f3`).

(A) **v3's own traces.** Their `contract_fixtures.build_v3`, run in memory on v2, must give the
`v3.json` beside their code byte for byte (so the code read is the code that wrote it); then ours
`detect` on each of v3's own traces, a loss or a blink in v1's 8° step: runs `(start, stop, flagged)`
exactly, size held to v3's tolerance (`|got - want| <= 1e-9 + 1e-12 * |want|`). v3 is not published
(no digest is pinned, nothing is vendored); this reads it only to compare.

(B) **A sweep at the take-off.** Minimum-jerk saccades along x of 0.9° to 8° over 8 to 30 samples,
fixational noise, each losing `m` samples (1 to 26) whose last is from six before the onset to eight
after it, so the stretch of unknown velocities ends near the run's start. Theirs is
`contract_fixtures.detector_input`, `velocity.local_velocity`, `engbert_kliegl.detect_engbert_kliegl`
in true angle, a run's flag as `build_v3` gives it (a `Label.LOST` sample in `[start - 2, stop)`) and
its size as `build_v3` measures it (`measure.measure_event_run`); ours `detect`. Per run: intervals and
flags exactly, size to v3's tolerance, and the label each size gives at the 1° cut (ours has no label:
"saccade" at or above `microsaccade_max_deg`, as `tests/test_saccade.py` reads ours). A run is a
take-off case when their `Label.LOST` stretch ends on the sample before its start.

(C) **Online**, its thresholds held at the batch form's: each confirmation's start the batch run's,
its flag their `Label.LOST` over what a confirmation can know, `[start - 2, confirming velocity]`, and
its size the true angle from the sample their labels put the take-off at (the last before the
`Label.LOST` stretch adjoining the start, else the start) to the confirming sample.

`python versus_preproc_take_off.py [SACCADE_PY]` checks `SACCADE_PY` (another version's
`wl_xcon/saccade.py`, say `git show 8bc667e:wl_xcon/saccade.py`) in place of the working tree's. Reads
wl-preproc from the directory `WLPP_SOURCE` names, holding its `wl_preproc` package and its
`docs/fixtures/saccade/v2.json` and `v3.json` as `v2.json` and `v3.json` (README.md). Nothing in
wl-preproc is edited."""
import dataclasses
import importlib.util
import json
import math
import os
import random
import sys

sys.path.insert(0, os.environ["WLPP_SOURCE"])
import numpy as np  # noqa: E402
from wl_preproc.eye.detect import contract_fixtures as cf  # noqa: E402
from wl_preproc.eye.detect.engbert_kliegl import DEFAULT_EK_PARAMS, detect_engbert_kliegl  # noqa: E402
from wl_preproc.eye.detect.geometry import TRUE_ANGLE  # noqa: E402
from wl_preproc.eye.detect.labels import Label  # noqa: E402
from wl_preproc.eye.detect.measure import measure_event_run  # noqa: E402
from wl_preproc.eye.detect.velocity import local_velocity  # noqa: E402

import wl_xcon  # noqa: E402
import wl_xcon.saccade as ours  # noqa: E402
from wl_xcon.geometry import separation_deg  # noqa: E402

S = ours
if len(sys.argv) > 1:
    spec = importlib.util.spec_from_file_location("saccade_under_test", sys.argv[1])
    S = importlib.util.module_from_spec(spec)
    sys.modules["saccade_under_test"] = S
    spec.loader.exec_module(S)
print("wl_xcon:", wl_xcon.__file__, "| detector under test:", S.__file__, "VERSION", S.VERSION)
print("wl_preproc:", cf.__file__)
FS = 500.0
P = S.Params()
CUT = 1.0
THEIR_PARAMS = dataclasses.replace(DEFAULT_EK_PARAMS, geometry=TRUE_ANGLE)


def held(got, want):
    return abs(got - want) <= 1e-9 + 1e-12 * abs(want)


def theirs(trace):
    """Their runs on `trace` (`None` a lost sample): `(start, stop, flagged, size, label)` each, and
    their labels."""
    gaze_deg = [None if p is None else list(p) for p in trace]
    gaze, offered = cf.detector_input(gaze_deg, [None if p is not None else "lost" for p in gaze_deg],
                                      FS, cf.MAX_LOST_MS)
    speed = local_velocity(gaze, FS)
    lost = np.array([entry is Label.LOST for entry in offered])
    runs = []
    for r in detect_engbert_kliegl(gaze, speed, offered, FS, THEIR_PARAMS):
        size = measure_event_run(gaze, speed, offered, r.start, r.stop, FS, geometry=TRUE_ANGLE,
                                 runs_end_before_landing=False, min_measured_ms=None).amplitude_deg
        runs.append((int(r.start), int(r.stop), bool(lost[max(r.start - 2, 0):r.stop].any()), float(size),
                     r.label.value))
    return runs, lost


def took_off(lost, start):
    """Where their labels put a run's take-off: the sample before the `Label.LOST` stretch that ends
    on the sample before `start`, else `start`."""
    first = start
    while first > 0 and lost[first - 1]:
        first -= 1
    return first - 1 if first < start else start


class Pinned(S.Detector):
    def __init__(self, eta):
        super().__init__(params=S.Params())
        self.eta = eta

    def _refresh(self):
        self._eta_x, self._eta_y = self.eta


def compare(trace, at, stats, bad, name):
    their_runs, lost = theirs(trace)
    mine = S.detect(trace, at)
    stats["cases"] += 1
    stats["runs"] += len(their_runs)
    adjoining = [took_off(lost, r[0]) < r[0] for r in their_runs]
    stats["take_off_runs"] += sum(adjoining)
    if [(s.start, s.stop, s.flagged) for s in mine] != [r[:3] for r in their_runs]:
        stats["runs_differ"] += 1
        bad.append((name, "runs", [(s.start, s.stop, s.flagged) for s in mine], [r[:3] for r in their_runs]))
        return
    for s, r, adj in zip(mine, their_runs, adjoining):
        if held(s.amplitude_deg, r[3]):
            stats["sizes_held"] += 1
        else:
            stats["sizes_differ"] += 1
            stats["sizes_differ_at_take_off"] += adj
            if len(bad) < 12:
                bad.append((name, "size", (s.start, s.stop, round(s.amplitude_deg, 4)), (r[0], r[1], round(r[3], 4))))
        label = "saccade" if s.amplitude_deg >= CUT else "microsaccade"
        stats["labels_equal" if label == r[4] else "labels_differ"] += 1
    # Online, its thresholds the batch form's.
    eta = S.thresholds(S.velocity(trace, at, P), P)
    detector = Pinned(eta)
    confirmed = [s for t, g in zip(at, trace) if (s := detector.accept(t, g)) is not None]
    want = [(r[0], bool(lost[max(r[0] - 2, 0):c.stop].any())) for r, c in zip(their_runs, confirmed)]
    if len(confirmed) != len(mine) or [(s.start, s.flagged) for s in confirmed] != want:
        stats["online_differs"] += 1
        bad.append((name, "online", [(s.start, s.flagged) for s in confirmed], want))
        return
    for s in confirmed:
        a = trace[took_off(lost, s.start)]
        b = trace[s.stop - 1]
        stats["online_sizes_equal" if s.amplitude_deg == separation_deg(a[0], a[1], b[0], b[1])
              else "online_sizes_differ"] += 1


def section():
    return dict(cases=0, runs=0, take_off_runs=0, runs_differ=0, sizes_held=0, sizes_differ=0,
                sizes_differ_at_take_off=0, labels_equal=0, labels_differ=0, online_differs=0,
                online_sizes_equal=0, online_sizes_differ=0)


def minimum_jerk(onset, duration, amplitude, n=500, noise=0.01, seed=3):
    rng = random.Random(seed)
    gaze = []
    for i in range(n):
        tau = min(max((i - onset) / duration, 0.0), 1.0)
        reach = 10 * tau ** 3 - 15 * tau ** 4 + 6 * tau ** 5
        gaze.append((amplitude * reach + rng.gauss(0, noise), rng.gauss(0, noise)))
    return gaze, [i / FS for i in range(n)]


if __name__ == "__main__":
    source = os.environ["WLPP_SOURCE"]
    v2_text = open(os.path.join(source, "v2.json"), "rb").read()
    v3_text = open(os.path.join(source, "v3.json")).read()
    import hashlib
    rebuilt = cf.dumps(cf.build_v3(json.loads(v2_text), hashlib.sha256(v2_text).hexdigest()))
    print("(A) their build_v3 on v2 gives the v3.json beside their code:", rebuilt == v3_text)
    v3 = json.loads(v3_text)
    stats, bad = section(), []
    for trace in v3["traces"]:
        if trace["inputs_from"] != "v3":
            continue
        # A blink is a mask label, which withholds its samples there; ours has no mask, so they are
        # lost samples to it, carried as a short loss is (EYE-19, the true-angle revision): not the
        # rule under test.
        blink = any(label not in (None, "lost") for label in trace["available"] or [])
        gaze = [None if (p is None or label is not None) else tuple(p)
                for p, label in zip(trace["gaze_deg"], trace["available"] or [None] * len(trace["gaze_deg"]))]
        at = [i / FS for i in range(len(gaze))]
        mine = S.detect(gaze, at)
        want = [(r["start"], r["stop"], r["flagged"]) for r in trace["runs"]]
        got = [(s.start, s.stop, s.flagged) for s in mine]
        sizes = len(mine) == len(want) and all(held(s.amplitude_deg, r["amplitude_deg"])
                                               for s, r in zip(mine, trace["runs"]))
        print(f"    {trace['name']:40s} runs {'=' if got == want else 'DIFFER'} sizes {'held' if sizes else 'DIFFER'}"
              f"{' (a blink: ours has no mask)' if blink else ''}"
              f" | ours {[(a, b, c, round(s.amplitude_deg, 4)) for (a, b, c), s in zip(got, mine)]}"
              f" theirs {[(r['start'], r['stop'], r['flagged'], round(r['amplitude_deg'], 4)) for r in trace['runs']]}")

    for amplitude in (0.9, 1.0, 1.1, 1.2, 1.5, 2.0, 8.0):
        for duration in (8, 12, 20, 30):
            gaze, at = minimum_jerk(200, duration, amplitude)
            for last in range(194, 209):
                for m in (1, 2, 3, 5, 10, 20, 24, 26):
                    lost = range(last - m + 1, last + 1)
                    trace = [None if i in lost else p for i, p in enumerate(gaze)]
                    compare(trace, at, stats, bad, f"{amplitude} deg {duration} samples, lost {lost.start}-{last}")
    print(f"(B, C) the sweep at the take-off: {stats}")
    for row in bad[:12]:
        print("   ", row)
