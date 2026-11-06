"""Reviewer's probe 1: version 1 against version 2, sample for sample, on traces with no sample
missing and no break in time, and on traces whose gaps are far from any run.

Independent of the implementer's compare.py: own trace generator (smooth and linear profiles,
post-saccadic ringing, drift, Gaussian and heavy-tailed noise, jittered timestamps), own
parameter grid, and the comparison is every per-sample observable: the return value, `onset`,
`in_flight` and `ready`.
"""
from __future__ import annotations

import importlib.util
import math
import random
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from versions import v1, v2, cur  # noqa: E402


def make_trace(rng: random.Random, n: int, gaps: str):
    dt = 0.002
    at = []
    t = 0.0
    jitter = rng.choice([0.0, 0.0, 0.0002, 0.0008])
    for i in range(n):
        at.append(t)
        t += dt + (rng.uniform(-jitter, jitter) if jitter else 0.0)
    noise = rng.choice([0.005, 0.02, 0.05, 0.08])
    heavy = rng.random() < 0.3
    drift = rng.choice([0.0, 0.0, 0.5, 2.0])  # deg/s
    k = rng.randint(0, 6)
    onsets = sorted(rng.sample(range(120, n - 60), k)) if n > 200 else []
    sacc = []
    last = -100
    for o in onsets:
        if o - last < 40:
            continue
        dur = rng.randint(2, 25)
        amp = rng.choice([0.1, 0.3, 0.8, 2.0, 5.0, 8.0, 15.0]) * rng.uniform(0.7, 1.3)
        ang = rng.uniform(0, 2 * math.pi)
        profile = rng.choice(["linear", "cos", "cos_ring"])
        sacc.append((o, dur, amp * math.cos(ang), amp * math.sin(ang), profile))
        last = o + dur
    x = y = 0.0
    pos = []
    for i in range(n):
        x += drift * dt
        pos.append([x, y])
    for o, dur, dx, dy, profile in sacc:
        for i in range(o, n):
            if i < o + dur:
                u = (i - o + 1) / dur
                f = u if profile == "linear" else (1 - math.cos(math.pi * u)) / 2
            else:
                f = 1.0
                if profile == "cos_ring":
                    s = i - (o + dur)
                    f += 0.08 * math.exp(-s / 6) * math.sin(2 * math.pi * s / 8)
            pos[i][0] += dx * f
            pos[i][1] += dy * f
    gaze = []
    for i in range(n):
        if heavy:
            ex = noise * rng.gauss(0, 1) / math.sqrt(rng.gammavariate(1.5, 1 / 1.5))
            ey = noise * rng.gauss(0, 1) / math.sqrt(rng.gammavariate(1.5, 1 / 1.5))
        else:
            ex, ey = rng.gauss(0, noise), rng.gauss(0, noise)
        gaze.append((pos[i][0] + ex, pos[i][1] + ey))
    return gaze, at, sacc


def run(module, gaze, at, params, history, refresh):
    d = module.Detector(params=params, history=history, refresh_every=refresh)
    out = []
    for k, (t, g) in enumerate(zip(at, gaze)):
        s = d.accept(t, g)
        out.append((s, d.onset, d.in_flight, d.ready))
    return out


def as_tuple(s):
    return None if s is None else (s.start, s.stop, s.amplitude_deg.hex(), s.flagged)


def compare(rng, trials, gaps, A=None, B=None):
    runs = differing = confirmations = 0
    examples = []
    for trial in range(trials):
        n = rng.randint(300, 1500)
        gaze, at, sacc = make_trace(rng, n, gaps)
        md = rng.choice([3, 4, 5, 6, 6, 6, 7, 8, 10])
        lam = rng.choice([4.0, 6.0, 6.0, 8.0])
        warm = rng.choice([20, 50])
        history = rng.choice([30, 60, 1000])
        refresh = rng.choice([1, 7, 50])
        p1 = A.Params(lambda_=lam, min_duration_samples=md, warmup_samples=warm)
        p2 = B.Params(lambda_=lam, min_duration_samples=md, warmup_samples=warm)
        a = run(A, gaze, at, p1, history, refresh)
        b = run(B, gaze, at, p2, history, refresh)
        runs += 1
        for k, (x, y) in enumerate(zip(a, b)):
            if x[0] is not None:
                confirmations += 1
            if (as_tuple(x[0]), as_tuple(x[1]), x[2], x[3]) != (as_tuple(y[0]), as_tuple(y[1]), y[2], y[3]):
                differing += 1
                if len(examples) < 5:
                    examples.append((trial, k, as_tuple(x[0]), as_tuple(y[0]), x[2:], y[2:]))
    return runs, confirmations, differing, examples


if __name__ == "__main__":
    for a, b, an, bn in ((v1, v2, "v1", "v2"), (v2, cur, "v2", f"cur(v{cur.VERSION})"), (v1, cur, "v1", f"cur(v{cur.VERSION})")):
        rng = random.Random(20261030)
        runs, conf, diff, ex = compare(rng, 3000, "none", a, b)
        print(f"clean, {an} against {bn}: {runs} traces, {conf} {an} confirmations, {diff} differing samples")
        for e in ex:
            print("  ", e)
