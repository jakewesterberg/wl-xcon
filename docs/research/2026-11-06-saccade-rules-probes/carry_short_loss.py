"""The review of saccade version 7, its checks 3 and 5 (its `p5_carry.py`, kept here as it ran): where the
gaze world puts the eye at rest (`Tracked._stopped`, from `Detector.last_stop`) when a saccade's last
samples are lost, and what the onset carry and the exit carry then score. Minimum-jerk saccades of 12,
20 and 30 samples to the target, 1 to 20 datagrams lost from each offset in or after them; the
tracker's staleness half a frame, as in the suite's own gaze-world tests, so a missing datagram reaches
the detector as a lost sample, and the rig's 50 ms, where the held sample is fed instead (XC-428).
One row a trial: staleness, duration, trial, first lost, how many, outcome, frames, the sample the
world put the eye at rest on, and whether the eye's noiseless path was still moving there.

Run it under each version's tree and compare the rows (README.md): at version 6 (`d932cb3`) and 8
every outcome and frame is the same; at version 7 (`07aee63`) 122 of the 1820 half-frame trials are
`NO_RESPONSE` where 6 and 8 score them `CORRECT`, the eye put at rest while still moving in 704 of
1660 landings, which 6 and 8 never do."""
import json
import sys

import wl_xcon
from wl_xcon.calibration import EyeMap, Mapping, Model
from wl_xcon.eye import Replay, Tracker
from wl_xcon.gaze import Tracked
from wl_xcon.run import Recorded, run_trial
from wl_xcon.task import (REMEMBERED, After, Exited, On, Outcome, SaccadeOnset, SaccadeTo, State,
                          Trial, Window)

print("wl_xcon:", wl_xcon.__file__)
FRAME = 0.002
IDENT = EyeMap(model=Model.AFFINE, x=(0.0, 1.0, 0.0), y=(0.0, 0.0, 1.0), conditioning=1.0,
               rms_residual_deg=0.0, n_points=3)


def datagram(x, y, k):
    eye = {"FrameNumber": k, "Pupil": {"Center": {"X": x, "Y": y}, "Size": {"Width": 30.0, "Height": 28.0}},
           "CRs": [{"X": x, "Y": y}, {"X": 0.0, "Y": 0.0}, {"X": 0.0, "Y": 0.0}, {"X": 0.0, "Y": 0.0}]}
    return json.dumps({"Left": eye, "Right": eye})


ONSET, N = 200, 700


def path(dur, amp=8.0, noise=0.01):
    import random
    rng = random.Random(3)
    out = []
    for i in range(N):
        tau = min(max((i - ONSET) / dur, 0.0), 1.0)
        f = 10 * tau ** 3 - 15 * tau ** 4 + 6 * tau ** 5
        out.append((amp * f + rng.gauss(0, noise), rng.gauss(0, noise)))
    return out


def trials(fix_radius):
    return {
        "onset carry": Trial(start="a", windows=[Window("target", at=(8.0, 0.0), radius=2.0, on=REMEMBERED)],
                             states=[State("a", go=[On(SaccadeOnset(), "b"), On(After(1.0), Outcome.NO_FIXATION)]),
                                     State("b", go=[On(SaccadeTo("target"), Outcome.CORRECT),
                                                    On(After(0.3), Outcome.NO_RESPONSE)])]),
        f"exit carry, fixation window {fix_radius} deg": Trial(
            start="a", windows=[Window("fix", at=(0.0, 0.0), radius=fix_radius, on=REMEMBERED),
                                Window("target", at=(8.0, 0.0), radius=2.0, on=REMEMBERED)],
            states=[State("a", go=[On(Exited("fix"), "b"), On(After(1.0), Outcome.NO_FIXATION)]),
                    State("b", go=[On(SaccadeTo("target"), Outcome.CORRECT),
                                   On(After(0.3), Outcome.NO_RESPONSE)])]),
    }


def run(trial, g, lose, staleness):
    payloads = [(0.0, "" if k in lose else datagram(x, y, k)) for k, (x, y) in enumerate(g)]
    world = Tracked(Tracker(staleness=staleness), Mapping(version=1, targets=(), left=IDENT, right=IDENT),
                    trial, FRAME, {}, source=Replay(payloads=payloads))
    seen = {}
    display = world.display

    def watching(visible, frame):
        display(visible, frame)
        if world._landed_on == frame:
            seen["landed"] = (frame, world._stopped)

    world.display = watching
    r = run_trial(trial, world, FRAME, values={}, effects=Recorded())
    return r, seen.get("landed"), world


rows = []
for staleness in (FRAME / 2, 0.05):
    for dur in (12, 20, 30):
        for fix_radius in (1.5, 4.0, 6.0):
            for name, trial in trials(fix_radius).items():
                if name == "onset carry" and fix_radius != 1.5:
                    continue
                for first in range(ONSET + 1, ONSET + dur + 2):
                    for m in (1, 2, 3, 4, 6, 10, 20):
                        lose = set(range(first, first + m))
                        g = path(dur)
                        r, landed, world = run(trial, g, lose, staleness)
                        # The sample the world puts the eye at rest on, and whether the eye was still
                        # moving there (its noiseless path not yet at its end).
                        if landed is not None:
                            k = landed[1] - 1
                            moving = k < ONSET + dur
                        else:
                            k, moving = None, None
                        rows.append((staleness, dur, name, first, m, r.outcome.name, r.frames, k, moving))
for row in rows:
    print(*row, sep="\t")
