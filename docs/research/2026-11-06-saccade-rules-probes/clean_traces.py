"""Saccade version 9 on clean traces (no sample lost, none not a number): the review of version 8's
check 2 (its `q2_clean.py`, review 5's `p2_clean.py` before it), kept here as it ran but for the
versions compared. Another version's `wl_xcon/saccade.py` (`git show c9940a8:wl_xcon/saccade.py`,
version 8) against the working tree's: 3000 random traces of 150 to 1600 samples, noise Gaussian
or heavy-tailed, linear and minimum-jerk movements, runs at both edges, on an `i / fs` clock and a
jittered one. Velocities and thresholds bit for bit, `detect`'s runs (sizes by their hex), and
online, with the default warmup and with a warmup of 2, every sample's return, `in_flight`,
`ready`, both thresholds, `onset`, `last_stop` and `seen`. Usage: clean_traces.py OLD_SACCADE_PY"""
import importlib.util
import math
import random
import sys

import wl_xcon
import wl_xcon.saccade as new

print("wl_xcon:", wl_xcon.__file__)
spec = importlib.util.spec_from_file_location("saccade_old", sys.argv[1])
old = importlib.util.module_from_spec(spec)
sys.modules["saccade_old"] = old
spec.loader.exec_module(old)
print("old:", old.__file__, "VERSION", old.VERSION, "| new VERSION", new.VERSION)
FS = 500.0


def trace(rng, n):
    x = y = 0.0
    out = []
    events = []
    k = rng.randint(30, 120)
    while k < n - 10:
        dur = rng.randint(2, 40)
        amp = rng.uniform(0.2, 20.0)
        ang = rng.uniform(0, 2 * math.pi)
        events.append((k, dur, amp * math.cos(ang), amp * math.sin(ang), rng.random() < 0.5))
        k += dur + rng.randint(20, 200)
    noise = rng.choice([0.005, 0.01, 0.02, 0.05])
    heavy = rng.random() < 0.3
    for i in range(n):
        for onset, dur, dx, dy, jerk in events:
            if onset <= i < onset + dur:
                tau0, tau1 = (i - onset) / dur, (i - onset + 1) / dur
                f = (lambda t: 10 * t ** 3 - 15 * t ** 4 + 6 * t ** 5) if jerk else (lambda t: t)
                x += dx * (f(tau1) - f(tau0))
                y += dy * (f(tau1) - f(tau0))
        nx = rng.gauss(0, noise) * (rng.choice([1, 1, 1, 5]) if heavy else 1)
        ny = rng.gauss(0, noise) * (rng.choice([1, 1, 1, 5]) if heavy else 1)
        out.append((x + nx, y + ny))
    return out


def key(s):
    return (s.start, s.stop, s.amplitude_deg.hex(), s.flagged)


rng = random.Random(20261106)
N = 3000
batch_diff = batch_edge = online_diff = samples = confirmations = 0
online_by = {'default': 0, 'warmup 2': 0}
online_kind = {'flag of a run starting at 3 or before': 0, 'other': 0}
edge_examples = []
for case in range(N):
    n = rng.choice([150, 400, 900, 1600])
    g = trace(rng, n)
    # Clocks: i/fs, a rig clock with jitter, and (sometimes) a moving eye at the very start or end.
    if rng.random() < 0.15:
        g = [(p[0] + 0.3 * i, p[1]) for i, p in enumerate(g[:12])] + g[12:]
    if rng.random() < 0.15:
        g = g[:-12] + [(p[0] + 0.3 * i, p[1]) for i, p in enumerate(g[-12:])]
    at = [i / FS for i in range(n)] if rng.random() < 0.7 else \
        [i / FS + rng.uniform(-0.0002, 0.0002) for i in range(n)]
    v_new = new.velocity(g, at, new.Params())
    v_old = old.velocity(g, at, old.Params())
    assert repr(v_new) == repr(v_old), case
    assert repr(new.thresholds(v_new, new.Params())) == repr(old.thresholds(v_old, old.Params())), case
    a = [key(s) for s in new.detect(g, at)]
    b = [key(s) for s in old.detect(g, at)]
    if a != b:
        da = [r for r in a if r not in b]
        db = [r for r in b if r not in a]
        at_edge = False
        if at_edge:
            batch_edge += 1
            if len(edge_examples) < 4:
                edge_examples.append((case, n, db, da))
        else:
            batch_diff += 1
            print("BATCH DIFF", case, db, da)
    for warm in ([], [new.Params(warmup_samples=2)]):
        pn = warm[0] if warm else new.Params()
        po = old.Params(warmup_samples=2) if warm else old.Params()
        dn, do = new.Detector(params=pn), old.Detector(params=po)
        for k, (t, p) in enumerate(zip(at, g)):
            sn, so = dn.accept(t, p), do.accept(t, p)
            samples += 1
            same = ((None if sn is None else key(sn)) == (None if so is None else key(so))
                    and dn.in_flight == do.in_flight and dn.ready == do.ready
                    and repr((dn._eta_x, dn._eta_y)) == repr((do._eta_x, do._eta_y))
                    and (dn.onset is None) == (do.onset is None)
                    and dn.last_stop == do.last_stop and dn.seen == do.seen)
            if sn is not None:
                confirmations += 1
            if not same:
                online_diff += 1
                online_by['warmup 2' if warm else 'default'] += 1
                only_flag = (sn is not None and so is not None and key(sn)[:3] == key(so)[:3] and sn.start <= 3 and so.flagged and not sn.flagged and dn.in_flight == do.in_flight and repr((dn._eta_x, dn._eta_y)) == repr((do._eta_x, do._eta_y)))
                online_kind['flag of a run starting at 3 or before' if only_flag else 'other'] += 1
                if online_diff <= 5:
                    print("ONLINE DIFF", case, "warmup 2" if warm else "default", k,
                          None if so is None else key(so), None if sn is None else key(sn))
print(f"{N} clean traces: velocity and thresholds bit for bit equal in all; detect differs in "
      f"{batch_diff + batch_edge} traces")
print(f"online: {samples} samples (default warm-up and warm-up 2), {confirmations} confirmations; "
      f"samples whose return, in_flight, ready, thresholds or onset differ: {online_diff} {online_by} {online_kind}")
