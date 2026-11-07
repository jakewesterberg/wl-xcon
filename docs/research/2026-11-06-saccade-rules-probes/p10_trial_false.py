"""Probe 10 on version 4: the catch trial of commit 2 (fixation, a 0.12 deg step at 300, datagram 302 lost)."""
from __future__ import annotations

import math
import random
import sys
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.resolve().parents[2]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "tests"))
from versions import v1, v2, v3, cur  # noqa: E402
import test_saccade as T  # noqa: E402
from wl_xcon.calibration import Mapping  # noqa: E402
from wl_xcon.eye import Replay, Tracker  # noqa: E402
from wl_xcon.gaze import Tracked  # noqa: E402
from wl_xcon.run import Recorded, run_trial  # noqa: E402
from wl_xcon.task import After, On, Outcome, SaccadeOnset, State, Trial  # noqa: E402

DT = 0.002


def fixation(rng, n, noise, heavy):
    """Fixation noise about the origin, drawn as `p3_fixation.fixation` draws it."""
    gaze, at = [], []
    for i in range(n):
        if heavy:
            ex = noise * rng.gauss(0, 1) / math.sqrt(rng.gammavariate(1.5, 1 / 1.5))
            ey = noise * rng.gauss(0, 1) / math.sqrt(rng.gammavariate(1.5, 1 / 1.5))
        else:
            ex, ey = rng.gauss(0, noise), rng.gauss(0, noise)
        gaze.append((ex, ey))
        at.append(i * DT)
    return gaze, at


def _fresh(module):
    """A fresh detector of `module`; version 1 predates `Detector.seen`, which `gaze.Tracked` reads."""
    detector = module.Detector()
    if not hasattr(type(detector), "seen"):
        detector.seen = 0
    return detector


CATCH = Trial(start="hold", windows=[], states=[
    State("hold", go=[On(SaccadeOnset(), Outcome.EARLY_RESPONSE), On(After(1.0), Outcome.CORRECT_REJECT)])])
rng = random.Random(1)
gaze, _ = fixation(rng, 600, 0.02, False)
gaze = [(x + (0.12 if i >= 300 else 0.0), y) for i, (x, y) in enumerate(gaze)]
for module in (v1, v2, v3, cur):
    for lose in (set(), {302}):
        payloads = [(0.0, "" if k in lose else T._datagram(x, y, k)) for k, (x, y) in enumerate(gaze)]
        world = Tracked(Tracker(staleness=T._FRAME / 2),
                        Mapping(version=1, targets=(), left=T._IDENTITY, right=T._IDENTITY), CATCH,
                        T._FRAME, {}, source=Replay(payloads=payloads), detector=_fresh(module))
        try:
            result = run_trial(CATCH, world, T._FRAME, values={}, effects=Recorded())
        except RuntimeError as refused:
            print(f"version {module.VERSION}, lost {sorted(lose) or 'none'}: refused by the gaze world: {str(refused)[:60]}...")
            continue
        print(f"version {module.VERSION}, lost {sorted(lose) or 'none'}: {result.outcome.name} at frame {result.frames}")
