"""Saccade version 10 against wl-preproc's code at `bb6180e`, with and without its edge rule of
2026-11-06 put in in memory (`preproc_edge_rule.py`): the review of version 9's check 1
(`r2_versus.py`, its own random set), re-run.

3000 traces of 600 samples at 500 Hz, an `i / fs` clock: one or two minimum-jerk saccades anywhere,
one to four losses of 1 to 60 samples placed near a saccade, near a trace's edge, near another loss
or anywhere. Theirs is `contract_fixtures.detector_input`, `velocity.local_velocity` and
`engbert_kliegl.detect_engbert_kliegl` in true angle, flagged as its `build_v3` flags a run (a
carried sample, `Label.LOST`, in `[start - 2, stop)`); ours `detect`. Per trace: the thresholds
(to 1e-9 relative), and the runs' `(start, stop, flagged)`. A difference whose every run of theirs
ends at `n - 1` or `n` after carried samples is their filled-in zero velocity there, ending a carried
run (the review of version 9's concern 2); any other is printed.

Online, with its thresholds held at the batch form's: each confirmation's start, flag and confirming
velocity against the batch run's, its flag `_carried` over `[start - 2, confirming velocity]`, and each closed run's `last_stop` against the
batch stop; a trace whose runs start within the warmup is counted apart.

Reads wl-preproc from the directory `WLPP_BB6180E_SOURCE` names (README.md); `[CASES]`, 3000 by
default. Nothing in wl-preproc is edited."""
import dataclasses
import math
import os
import random
import sys

sys.path.insert(0, os.environ["WLPP_BB6180E_SOURCE"])
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np  # noqa: E402
from wl_preproc.eye.detect import contract_fixtures as cf  # noqa: E402
from wl_preproc.eye.detect.engbert_kliegl import DEFAULT_EK_PARAMS, detect_engbert_kliegl  # noqa: E402
from wl_preproc.eye.detect.engbert_kliegl import thresholds as their_thresholds  # noqa: E402
from wl_preproc.eye.detect.geometry import TRUE_ANGLE  # noqa: E402
from wl_preproc.eye.detect.labels import Label  # noqa: E402
from wl_preproc.eye.detect.velocity import local_velocity  # noqa: E402

import preproc_edge_rule  # noqa: E402
import wl_xcon  # noqa: E402
import wl_xcon.saccade as S  # noqa: E402

print("wl_xcon:", wl_xcon.__file__, "VERSION", S.VERSION, "| wl_preproc:", cf.__file__)
FS = 500.0
N = 600
P = S.Params()
THEIR_PARAMS = dataclasses.replace(DEFAULT_EK_PARAMS, geometry=TRUE_ANGLE)


def theirs(gaze):
    gaze_deg = [None if p is None else list(p) for p in gaze]
    positions, offered = cf.detector_input(gaze_deg, [None if p is not None else "lost" for p in gaze_deg],
                                           FS, cf.MAX_LOST_MS)
    speed = local_velocity(positions, FS)
    known = np.array([entry is None for entry in offered])
    lost = np.array([entry is Label.LOST for entry in offered])
    runs = [(int(r.start), int(r.stop), bool(lost[max(r.start - 2, 0):r.stop].any()))
            for r in detect_engbert_kliegl(positions, speed, offered, FS, THEIR_PARAMS)]
    return runs, their_thresholds(speed, known, THEIR_PARAMS), offered


class Pinned(S.Detector):
    def __init__(self, eta):
        super().__init__(params=P)
        self.eta = eta

    def _refresh(self):
        self._eta_x, self._eta_y = self.eta


def online(gaze, at, detector):
    confirmed, closed, reported, ready_centre = [], [], False, None
    for k, (t, x) in enumerate(zip(at, gaze)):
        flying = detector.in_flight
        saccade = detector.accept(t, x)
        if ready_centre is None and detector.ready:
            ready_centre = k - 2
        if saccade is not None:
            confirmed.append((saccade.start, saccade.flagged, k - 2))
            reported = True
        if flying and not detector.in_flight:
            if reported:
                closed.append(detector.last_stop)
            reported = False
    return confirmed, closed, detector.in_flight and reported, ready_centre


def minimum_jerk(rng):
    noise = rng.choice([0.01, 0.02, 0.05])
    onsets = sorted(rng.sample(range(0, N - 10), rng.choice([1, 2])))
    moves = []
    for onset in onsets:
        duration = rng.randint(8, 40)
        amplitude = rng.uniform(1.0, 15.0)
        angle = rng.uniform(0, 2 * math.pi)
        moves.append((onset, duration, amplitude * math.cos(angle), amplitude * math.sin(angle)))
    gaze = []
    for i in range(N):
        x = y = 0.0
        for onset, duration, dx, dy in moves:
            tau = min(max((i - onset) / duration, 0.0), 1.0)
            reach = 10 * tau ** 3 - 15 * tau ** 4 + 6 * tau ** 5
            x += dx * reach
            y += dy * reach
        gaze.append((x + rng.gauss(0, noise), y + rng.gauss(0, noise)))
    return gaze, onsets


def losses(rng, onsets):
    lost = set()
    for _ in range(rng.randint(1, 4)):
        where = rng.random()
        length = rng.choice([1, 1, 2, 3, 5, 10, 20, 23, 24, 25, 26, 30, 60])
        if where < 0.4:
            s = rng.choice(onsets) + rng.randint(-10, 45)
        elif where < 0.65:
            s = rng.choice([rng.randint(0, 8), N - rng.randint(1, 10)])
        elif where < 0.85 and lost:
            s = max(lost) + rng.randint(1, 8) if rng.random() < 0.5 else min(lost) - length - rng.randint(1, 8)
        else:
            s = rng.randint(0, N - 1)
        for i in range(s, s + length):
            if 0 <= i < N:
                lost.add(i)
    return sorted(lost)


def traces(cases):
    for seed in range(cases):
        rng = random.Random(seed)
        gaze, onsets = minimum_jerk(rng)
        lost = set(losses(rng, onsets))
        yield seed, sorted(lost), [None if i in lost else gaze[i] for i in range(N)], [i / FS for i in range(N)]


def end_residual(their_runs, our_runs, offered):
    extra = set(their_runs) - set(our_runs)
    return bool(extra) and len(their_runs) == len(our_runs) and all(
        stop in (N - 1, N) and offered[stop - 2] is Label.LOST for _, stop, _ in extra)


def batch(cases, edge_rule):
    unpatch = preproc_edge_rule.patch() if edge_rule else None
    try:
        stats = dict(cases=0, thresholds_equal=0, runs_equal=0, end_residual=0, other=0)
        others = []
        for seed, lost, gaze, at in traces(cases):
            their_runs, their_eta, offered = theirs(gaze)
            ours = [(s.start, s.stop, s.flagged) for s in S.detect(gaze, at)]
            eta = S.thresholds(S.velocity(gaze, at, P), P)
            stats["cases"] += 1
            stats["thresholds_equal"] += all(abs(a - b) <= 1e-9 * max(1.0, abs(b)) for a, b in zip(eta, their_eta))
            if their_runs == ours:
                stats["runs_equal"] += 1
            elif end_residual(their_runs, ours, offered):
                stats["end_residual"] += 1
            else:
                stats["other"] += 1
                if len(others) < 12:
                    others.append((seed, lost[:12], their_runs, ours))
        return stats, others
    finally:
        if unpatch is not None:
            unpatch()


def held_online(cases):
    stats = dict(cases=0, equal=0, warmup=0, differ=0)
    differ = []
    for seed, lost, gaze, at in traces(cases):
        velocities = S.velocity(gaze, at, P)
        eta = S.thresholds(velocities, P)
        carried = S._carried(gaze, at, velocities, P)
        runs = S.detect(gaze, at, P)
        want = []
        for run in runs:
            count, confirming = 0, None
            for i in range(run.start, run.stop):
                if velocities[i] is not None and S._outside(velocities[i], *eta):
                    count += 1
                    if count == P.min_duration_samples:
                        confirming = i
                        break
            want.append((run.start, any(carried[max(run.start - 2, 0):confirming + 1]), confirming))
        confirmed, closed, open_end, ready_centre = online(gaze, at, Pinned(eta))
        stats["cases"] += 1
        if confirmed == want and all(stop in [r.stop for r in runs] for stop in closed) \
                and len(closed) + open_end == len(runs):
            stats["equal"] += 1
        elif ready_centre is None or any(r.start < ready_centre + 2 for r in runs):
            stats["warmup"] += 1
        else:
            stats["differ"] += 1
            if len(differ) < 10:
                differ.append((seed, lost[:12], confirmed, want, closed, [(r.start, r.stop) for r in runs]))
    return stats, differ


if __name__ == "__main__":
    cases = int(sys.argv[1]) if len(sys.argv) > 1 else 3000
    for edge_rule in (False, True):
        stats, others = batch(cases, edge_rule)
        print(f"batch against wl-preproc bb6180e{' with its edge rule (in memory)' if edge_rule else ''}: {stats}")
        for seed, lost, their_runs, ours in others:
            print(f"   seed {seed} lost {lost} ... theirs {their_runs} ours {ours}")
    stats, differ = held_online(cases)
    print(f"online, thresholds held at the batch form's, against the batch form: {stats}")
    for row in differ:
        print("   DIFFERS", row)
