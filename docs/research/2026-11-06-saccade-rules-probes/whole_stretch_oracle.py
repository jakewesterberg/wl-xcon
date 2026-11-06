"""Saccade version 9: each stretch of unknown velocities judged whole. The review of version 8 (its
check 1, `q1_rule.py`) wrote the rule as an oracle from its text alone; this is that oracle with
its loss rule replaced by wl-preproc's code on its branch `replay2/eye-lost` at `bb6180e`
(`validity._uncarried`, as `contract_fixtures.detector_input` applies it), and its run rule by the
shape of their `detect_engbert_kliegl`, both read from the source:

- a velocity is unknown because data was lost when its window, `n - 2` to `n + 2` clipped to the
  trace, holds a lost sample or two consecutive samples more than `max_gap_s` apart (their
  `_dilate(missing, 2)`, and `rows_across_gaps` for a break in time);
- each maximal stretch of them is carried only when the samples either side of it are in the trace
  and no two measured samples, taken in turn from the one before it to the one after it, are more
  than `max_gap_s` (plus 1e-9 s) apart; otherwise withheld whole;
- a run is a maximal stretch of velocities outside the threshold or in a carried stretch, from its
  first velocity outside the threshold; it stops one past its last such velocity, or, ending in a
  carried stretch whose next velocity is known, one past that one (the landing); it is dropped with
  fewer than `min_duration_samples` velocities outside the threshold;
- flagged when a velocity in a carried stretch lies in `[start - 2, stop)`; its size is the true
  angle between its first and last present samples; the thresholds are over complete windows of
  known velocities, a trace's first and last two apart.

It shares only `velocity` and `median_scale` with the detector, which the contract tests pin to
wl-preproc's v2. The cases: the review's 5093 (review 5's p1_rules, I2's worst, case 17, the two R11
sweeps, p3_trailing's 2970 and p1d_sweep's 1500), its 1500 with breaks in time and jittered clocks
(`q1b_breaks.py`), and two sweeps of this commit's own: two losses at every separation from 0 to 6
measured samples, each of them long or short, around a saccade; and a loss at each of a trace's first
and last seven samples, a saccade from its start or to its end. Batch against the oracle; online,
its thresholds held at the batch form's, each confirmation's start and flag (over `[start - 2,
confirming velocity]`) and each closed run's `last_stop`.

`python whole_stretch_oracle.py [SACCADE_PY]` checks `SACCADE_PY` (another version's
`wl_xcon/saccade.py`, say `git show c9940a8:wl_xcon/saccade.py`) in place of the working tree's.
With `WLPP_BB6180E_SOURCE` naming a directory holding wl-preproc's `wl_preproc` package at
`bb6180e`, the oracle's runs on every trace with an `i / fs` clock are also compared with their
code's (README.md)."""
from __future__ import annotations

import dataclasses
import importlib.util
import math
import os
import random
import sys

import wl_xcon
import wl_xcon.saccade as ours
from wl_xcon.geometry import separation_deg

sc = ours
if len(sys.argv) > 1:
    spec = importlib.util.spec_from_file_location("saccade_under_test", sys.argv[1])
    sc = importlib.util.module_from_spec(spec)
    sys.modules["saccade_under_test"] = sc
    spec.loader.exec_module(sc)
print("wl_xcon:", wl_xcon.__file__, "| detector under test:", sc.__file__, "VERSION", sc.VERSION)
FS = 500.0
P = ours.Params()
BOUND = P.max_gap_s + 1e-9

THEIRS = None
if os.environ.get("WLPP_BB6180E_SOURCE"):
    sys.path.insert(0, os.environ["WLPP_BB6180E_SOURCE"])
    import numpy as np
    from wl_preproc.eye.detect import contract_fixtures as cf
    from wl_preproc.eye.detect.engbert_kliegl import DEFAULT_EK_PARAMS, detect_engbert_kliegl
    from wl_preproc.eye.detect.geometry import TRUE_ANGLE
    from wl_preproc.eye.detect.labels import Label
    from wl_preproc.eye.detect.velocity import local_velocity
    print("wl_preproc:", cf.__file__)

    def THEIRS(trace):
        gaze_deg = [None if p is None else list(p) for p in trace]
        gaze, offered = cf.detector_input(gaze_deg, [None if p is not None else "lost" for p in gaze_deg],
                                          FS, cf.MAX_LOST_MS)
        lost = np.array([entry is Label.LOST for entry in offered])
        params = dataclasses.replace(DEFAULT_EK_PARAMS, geometry=TRUE_ANGLE)
        return [(int(r.start), int(r.stop), bool(lost[max(r.start - 2, 0):r.stop].any()))
                for r in detect_engbert_kliegl(gaze, local_velocity(gaze, FS), offered, FS, params)]


def true_runs(mask):
    out, k = [], 0
    while k < len(mask):
        if not mask[k]:
            k += 1
            continue
        start = k
        while k < len(mask) and mask[k]:
            k += 1
        out.append((start, k))
    return out


def oracle(gaze, at):
    n = len(gaze)
    g = [None if p is None or not (math.isfinite(p[0]) and math.isfinite(p[1])) else p for p in gaze]
    v = ours.velocity(g, at, P)
    known = [x is not None for x in v]

    def complete(i):
        return known[i] and all(known[j] for j in range(i - 2, i + 3) if 2 <= j < n - 2)

    taken = [i for i in range(n) if complete(i)]
    eta = (P.lambda_ * ours.median_scale([v[i][0] for i in taken]),
           P.lambda_ * ours.median_scale([v[i][1] for i in taken]))
    if eta[0] <= 0 or eta[1] <= 0:
        return eta, []

    def lost_at(k):
        lo, hi = max(k - 2, 0), min(k + 2, n - 1)
        return (any(g[i] is None for i in range(lo, hi + 1))
                or any(at[i + 1] - at[i] > P.max_gap_s for i in range(lo, hi)))

    lost = [lost_at(k) for k in range(n)]
    carried = [False] * n
    for s, e in true_runs(lost):
        before, after = s - 1, e
        whole = before >= 0 and after < n
        if whole:
            measured = [i for i in range(before, after + 1) if g[i] is not None]
            whole = all(at[b] - at[a] <= BOUND for a, b in zip(measured, measured[1:]))
        for i in range(s, e):
            carried[i] = whole
    outside = [known[i] and (v[i][0] / eta[0]) ** 2 + (v[i][1] / eta[1]) ** 2 > 1.0 for i in range(n)]

    def closes_online(e):
        """Whether the online form closes a run whose stretch of velocities ends before `e`: on a
        known velocity there, or inside a stretch on the first velocity (the online form computes them
        to `n - 3`) more than the bound after the last measured sample before it."""
        for c in range(e, n - 2):
            if known[c]:
                return c == e
            previous = max(i for i in range(c) if g[i] is not None)
            if at[c] - at[previous] > BOUND:
                return True
        return False

    runs = []
    for s, e in true_runs([o or c for o, c in zip(outside, carried)]):
        events = [i for i in range(s, e) if outside[i]]
        if len(events) < P.min_duration_samples:
            continue
        start, stop = events[0], events[-1] + 1
        if stop < e < n and known[e]:
            stop = e + 1
        flagged = any(carried[i] for i in range(max(start - 2, 0), min(stop, n)))
        a = next(g[i] for i in range(start, stop) if g[i] is not None)
        b = next(g[i] for i in range(stop - 1, start - 1, -1) if g[i] is not None)
        confirm = events[P.min_duration_samples - 1]
        runs.append(dict(start=start, stop=stop, flagged=flagged, size=separation_deg(a[0], a[1], b[0], b[1]),
                         closes=closes_online(e),
                         online_flag=any(carried[i] for i in range(max(start - 2, 0), confirm + 1))))
    return eta, runs


class Pinned(sc.Detector):
    def __init__(self, eta):
        super().__init__(params=sc.Params())
        self.eta = eta

    def _refresh(self):
        self._eta_x, self._eta_y = self.eta


def online(gaze, at, det):
    conf, closed, reported, ready_centre = [], [], False, None
    for k, (t, x) in enumerate(zip(at, gaze)):
        flying = det.in_flight
        s = det.accept(t, x)
        if ready_centre is None and det.ready:
            ready_centre = k - 2
        if s is not None:
            conf.append((s.start, s.flagged))
            reported = True
        if flying and not det.in_flight:
            if reported:
                closed.append(det.last_stop)
            reported = False
    return conf, closed, det.in_flight and reported, ready_centre


def section():
    return dict(cases=0, eta_bitwise=0, batch_equal=0, online_equal=0, online_warmup_only=0,
                theirs_compared=0, theirs_equal=0, theirs_end_residual=0)


stats = section()
bad = []
theirs_other = []


def check(name, gaze, at, verbose=False, clock_exact=True):
    stats["cases"] += 1
    eta_o, runs = oracle(gaze, at)
    clean = [None if p is None or not (math.isfinite(p[0]) and math.isfinite(p[1])) else p for p in gaze]
    eta = sc.thresholds(sc.velocity(clean, at, sc.Params()), sc.Params())
    stats["eta_bitwise"] += repr(eta) == repr(eta_o)
    got = [(s.start, s.stop, s.flagged, s.amplitude_deg) for s in sc.detect(gaze, at)]
    want = [(r["start"], r["stop"], r["flagged"], r["size"]) for r in runs]
    batch = [x[:3] for x in got] == [x[:3] for x in want] and all(
        abs(a[3] - b[3]) <= 1e-12 for a, b in zip(got, want))
    stats["batch_equal"] += batch
    conf, closed, open_end, ready_centre = online(gaze, at, Pinned(eta))
    wconf = [(r["start"], r["online_flag"]) for r in runs]
    wclosed = [r["stop"] for r in runs if r["closes"]]
    wopen = bool(runs) and not runs[-1]["closes"]
    on = conf == wconf and closed == wclosed and open_end == wopen
    if not on and (ready_centre is None or any(r["start"] < ready_centre + 2 for r in runs)):
        stats["online_warmup_only"] += 1
        on = None
    stats["online_equal"] += on is True
    if THEIRS is not None and clock_exact and all(p is None or math.isfinite(p[0]) for p in gaze):
        stats["theirs_compared"] += 1
        theirs = THEIRS(gaze)
        if theirs == [x[:3] for x in want]:
            stats["theirs_equal"] += 1
        else:
            # Their velocity at a trace's last two samples is a zero they fill in (`local_velocity`), which
            # can end a run carried across a stretch ending there, `stop` one past it; ours has none.
            n = len(gaze)
            residual = len(theirs) == len(want) and all(
                a == b or (a[0] == b[0] and a[1] in (n - 1, n) and b[1] < a[1]) for a, b in zip(theirs, want))
            if residual:
                stats["theirs_end_residual"] += 1
            elif len(theirs_other) < 12:
                theirs_other.append((name, theirs, [x[:3] for x in want]))
    if verbose or batch is False or on is False:
        print(f"{name:52s} batch {[(a, b, c, round(d, 3)) for a, b, c, d in got]} "
              f"oracle {[(a, b, c, round(d, 3)) for a, b, c, d in want]} {'=' if batch else 'BATCH DIFFERS'}")
        if on is not True:
            print(f"{'':52s} online conf {conf} closed {closed} open {open_end} | oracle conf {wconf} "
                  f"closed {wclosed} open {wopen} {'warmup' if on is None else 'ONLINE DIFFERS'}")
        if batch is False or on is False:
            bad.append(name)


def mj(onset=200, duration=30, amplitude=8.0, n=600, noise=0.01, seed=3):
    rng = random.Random(seed)
    g = []
    for i in range(n):
        tau = min(max((i - onset) / duration, 0.0), 1.0)
        reach = 10 * tau ** 3 - 15 * tau ** 4 + 6 * tau ** 5
        g.append((amplitude * reach + rng.gauss(0, noise), rng.gauss(0, noise)))
    return g, [i / FS for i in range(n)]


def lose(g, idx):
    g = list(g)
    for k in idx:
        g[k] = None
    return g


def report(title):
    global stats, bad, theirs_other
    print(f"{title}: {stats}")
    print(f"   differing from the oracle (batch, or held online past its warmup): {len(bad)} {bad[:12]}")
    if THEIRS is not None:
        print(f"   against wl-preproc bb6180e, neither equal nor the end residual: {len(theirs_other)} "
              f"{theirs_other[:6]}")
    stats, bad, theirs_other = section(), [], []


print("-- the review's 5093 cases --")
g, at = mj()
check("clean", g, at, True)
for k in (212, 50, 20, 100, 150, 300):
    tr = list(g)
    tr[k] = (math.nan, tr[k][1])
    check(f"R3 NaN at {k}", tr, at, True)
g190, at190 = mj(onset=190)
check("R11 30 from 190, None 206-229", lose(g190, range(206, 230)), at190, True)
g198, at198 = mj(onset=198)
check("R11 30 from 198, None 214-237", lose(g198, range(214, 238)), at198, True)
for onset in (190, 198):
    g60, at60 = mj(onset=onset, duration=60)
    check(f"R11 60 from {onset}, None {onset + 16}-{onset + 39}", lose(g60, range(onset + 16, onset + 40)), at60, True)
check("R16 None 214-239", lose(g, range(214, 240)), at, True)
check("R16 None 214-413", lose(g, range(214, 414)), at, True)
g12, at12 = mj(duration=12)
check("R19 12-sample, None 209-212", lose(g12, range(209, 213)), at12, True)
check("R18a None at 233", lose(g, [233]), at, True)
g0, at0 = mj(onset=0)
check("R18b from sample 0", g0, at0, True)
check("R18b from 0, sample 6 lost", lose(g0, [6]), at0, True)
g580, at580 = mj(onset=580)
check("R18b to the end", g580, at580, True)
check("R18b to the end, 590 lost", lose(g580, [590]), at580, True)
check("I2 worst", lose(g, range(209, 229)), at, True)
g17, at17 = mj(onset=139, duration=75, amplitude=13.44, n=560, seed=17)
check("M1 case 17 (140-165 lost)", lose(g17, range(140, 166)), at17, True)
gl, atl = mj(onset=100, duration=400, amplitude=40.0, n=700)
for m in (24, 25):
    for s0 in range(150, 451):
        check(f"R11 sweep m={m} s0={s0}", lose(gl, range(s0, s0 + m)), atl)
for dur in (8, 12, 20, 30, 40):
    for amp in (2.0, 8.0, 15.0):
        gg, aa = mj(duration=dur, amplitude=amp)
        for first in range(203, 200 + dur + 3):
            for m in (1, 2, 3, 4, 6, 10, 15, 20, 24):
                check(f"trailing {dur} {amp} {first} {m}", lose(gg, range(first, first + m)), aa)
rng = random.Random(20261106)
for case in range(1500):
    dur = rng.randint(8, 80)
    amp = rng.uniform(1.0, 20.0)
    onset = rng.randint(60, 400)
    gg, aa = mj(onset=onset, duration=dur, amplitude=amp, n=560, noise=rng.choice([0.005, 0.01, 0.03]), seed=case)
    k = rng.randint(onset - 10, onset + dur + 10)
    m = rng.choice([1, 2, 3, 5, 10, 20, 23, 24, 25, 26, 30, 60])
    stretches = [range(k, min(k + m, 555))]
    if rng.random() < 0.3:
        k2 = rng.randint(onset - 10, onset + dur + 10)
        stretches.append(range(k2, min(k2 + rng.randint(1, 30), 555)))
    check(f"sweep case {case}", lose(gg, [i for s in stretches for i in s]), aa)
report("5093 cases")

print("\n-- the review's 1500 with breaks in time and jittered clocks (q1b_breaks.py) --")
rng = random.Random(20261109)
for case in range(1500):
    dur = rng.randint(8, 60)
    onset = rng.randint(80, 350)
    g, _ = mj(onset=onset, duration=dur, amplitude=rng.uniform(1.0, 15.0), n=500,
              noise=rng.choice([0.005, 0.01, 0.03]), seed=case)
    at = [i / FS + (rng.uniform(-0.0002, 0.0002) if case % 2 else 0.0) for i in range(500)]
    k = rng.randint(onset - 8, onset + dur + 8)
    jump = rng.choice([0.01, 0.03, 0.045, 0.06, 0.2])
    at = [t + (jump if i >= k else 0.0) for i, t in enumerate(at)]
    tr = list(g)
    if rng.random() < 0.5:
        k2 = rng.randint(onset - 8, onset + dur + 8)
        for i in range(k2, min(k2 + rng.choice([1, 2, 5, 10, 24, 30]), 495)):
            tr[i] = None
    check(f"break case {case} jump {jump} at {k}", tr, at, clock_exact=False)
report("1500 with breaks in time")

print("\n-- two losses, 0 to 6 measured samples between, around a saccade --")
for duration, amplitude in ((30, 8.0), (120, 25.0)):
    gg, aa = mj(onset=300, duration=duration, amplitude=amplitude)
    for first in range(250, 300 + duration + 8, 3):
        for between in range(0, 7):
            for m1, m2 in ((1, 2), (3, 20), (20, 3), (24, 1), (30, 2), (2, 30), (12, 12), (20, 20)):
                second = first + m1 + between
                check(f"two losses {duration} {first}+{m1}, {between} between, +{m2}",
                      lose(gg, [*range(first, first + m1), *range(second, second + m2)]), aa)
report("two losses")

print("\n-- a loss at a trace's first or last seven samples --")
for onset, n in ((0, 600), (2, 600), (580, 600), (585, 600)):
    gg, aa = mj(onset=onset, duration=30, n=n)
    for edge in (range(0, 7), range(n - 7, n)):
        for first in edge:
            for m in (1, 2, 3):
                if first + m <= n:
                    check(f"edge onset {onset} {first}+{m}", lose(gg, range(first, first + m)), aa)
report("edges")
