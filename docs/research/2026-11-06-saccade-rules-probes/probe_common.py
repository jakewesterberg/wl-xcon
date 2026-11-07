"""Shared helpers for the XC-410 review probes (reviewer's scratch; not a test).

From the XC-410 review's probes (2026-10-30); it puts the repository's `tests/` on the path itself.
Payload i is fed on loop frame i + 1 (`Tracked.display`, one sample a frame).
"""
from __future__ import annotations

import math
import random
from dataclasses import replace

import sys  # noqa: E402
from pathlib import Path  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "tests"))
import test_gaze as tg  # noqa: E402
from wl_xcon.eye import Replay, Tracker
from wl_xcon.gaze import Tracked
from wl_xcon.run import Recorded, run_trial
from wl_xcon.task import (After, Entered, ObjectWindows, On, Outcome, SaccadeOnset, SaccadeTo,
                          Show, State, Stimulus, Trial, Update)

FP = 0.002
ARRAY = tg._PROBED  # four discs 8 deg out, target search.1 at 90 deg
JUMP = Update("search", at=(3.0, -2.0))


def probe(states):
    return Trial(start=states[0].name, windows=[ObjectWindows(of="search", radius=1.5)],
                 states=states)


def drawn(stim=ARRAY, trial=None):
    trial = trial or probe([State("x", enter=[Show(ARRAY)], go=[On(After(1.0), Outcome.ABORT)])])
    return tg._drawn(stim, {}, trial)


def moved(update=JUMP):
    return drawn(tg._moved(ARRAY, update))


def asks(guard=None):
    asked = ([On(guard, Outcome.CORRECT)] if guard is not None else
             [On(SaccadeTo("search.target"), Outcome.CORRECT),
              On(SaccadeTo("search.distractor"), Outcome.WRONG_TARGET)])
    return [*asked, On(After(0.3), Outcome.NO_RESPONSE)]


def linear(points, dwell=200, steps=10, stay=60, tail=600):
    """Fixate the origin `dwell` samples, then a linear ramp of `steps` samples to each point,
    staying `stay` at each but the last (`tail`). Returns (path, first moving index per saccade,
    first index at rest per saccade)."""
    path, at, starts, arrivals = [(0.0, 0.0)] * dwell, (0.0, 0.0), [], []
    for k, p in enumerate(points):
        starts.append(len(path))
        path += [(at[0] + (p[0] - at[0]) * j / steps, at[1] + (p[1] - at[1]) * j / steps)
                 for j in range(1, steps + 1)]
        arrivals.append(len(path) - 1)  # index of the first sample exactly at p
        path += [p] * (stay if k < len(points) - 1 else tail)
        at = p
    return path, starts, arrivals


def minjerk(points, dwell=200, steps=12, stay=60, tail=600):
    """As `linear`, with a minimum-jerk position profile (bell-shaped velocity)."""
    path, at, starts, arrivals = [(0.0, 0.0)] * dwell, (0.0, 0.0), [], []
    for k, p in enumerate(points):
        starts.append(len(path))
        for j in range(1, steps + 1):
            tau = j / steps
            s = 10 * tau ** 3 - 15 * tau ** 4 + 6 * tau ** 5
            path.append((at[0] + (p[0] - at[0]) * s, at[1] + (p[1] - at[1]) * s))
        arrivals.append(len(path) - 1)
        path += [p] * (stay if k < len(points) - 1 else tail)
        at = p
    return path, starts, arrivals


def replay(path, noise=0.02, seed=5):
    rng = random.Random(seed)
    return Replay(payloads=[(0.0, tg._payload(x + rng.gauss(0, noise), y + rng.gauss(0, noise),
                                              frame=n)) for n, (x, y) in enumerate(path)])


def run(trial, path, noise=0.02, seed=5, frame_period=FP, **kw):
    world = Tracked(Tracker(), tg._fitted_mapping(), trial, frame_period, {},
                    source=replay(path, noise, seed))
    result = run_trial(trial, world, frame_period, values={}, effects=Recorded(), **kw)
    return result, world


def timeline(path, noise=0.02, seed=5, frame_period=FP):
    """Per confirmed saccade: (onset frame as Tracked computes it, confirming frame, landing
    frame as Tracked marks it), feeding the path through a world with no saccade guard."""
    trial = probe([State("x", enter=[Show(ARRAY)], go=[On(After(10.0), Outcome.ABORT)])])
    world = Tracked(Tracker(), tg._fitted_mapping(), trial, frame_period, {},
                    source=replay(path, noise, seed))
    world.began("x", 1)
    out, cur = [], None
    for frame in range(1, len(path) + 1):
        world.display({}, frame)
        if world.detector.onset is not None:
            if cur is not None:
                out.append(cur)
            cur = [world._onset, frame, None]
        if cur is not None and cur[2] is None and world._landed_on == frame:
            cur[2] = frame
            out.append(tuple(cur))
            cur = None
    if cur is not None:
        out.append(tuple(cur))
    return out
