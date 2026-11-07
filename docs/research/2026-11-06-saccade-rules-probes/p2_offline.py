"""Reviewer's probe 2: live (v1, v2) against offline, on a saccade with one sample lost near its start.

Offline is three things here, and question 8 named only one:
  detect      -- wl-xcon's own batch form (`saccade.detect`) on the trace the rig had
  pp-whole    -- wl-preproc's detector on the whole trace (the eye PC's file kept the frame)
  pp-nan      -- wl-preproc's pipeline with the frame missing there too: NaN gaze, its validity mask
                 (DEFAULT_VALIDITY_PARAMS, dilate 5), then detect_engbert_kliegl
  pp-gap      -- the same, the dropped frame as its timebase gives it: hold-previous fill and a
                 FrameGap
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).parent
ROOT = HERE.resolve().parents[2]
sys.path.insert(0, str(HERE))
import os  # noqa: E402

#: wl-preproc as the suite reads it, its per-axis detector (v1): the repository's git-ignored `wl-preproc`
#: link, or the directory `WLPP_PER_AXIS` names (README.md). Outside the repository either way.
sys.path.insert(0, os.environ.get("WLPP_PER_AXIS", str(ROOT / "wl-preproc")))
from versions import v1, v2, cur  # noqa: E402
from wl_preproc.eye.detect.engbert_kliegl import DEFAULT_EK_PARAMS, detect_engbert_kliegl  # noqa: E402
from wl_preproc.eye.detect.validity import DEFAULT_VALIDITY_PARAMS, validity_labels  # noqa: E402
from wl_preproc.eye.detect.velocity import velocity as pp_velocity  # noqa: E402
from wl_preproc.eye.ohdpi import FrameGap, TrackerLoss  # noqa: E402

sys.path.insert(0, str(ROOT / "tests"))
from test_saccade import _trace  # noqa: E402

FS = 500.0


def online(module, gaze, at):
    d = module.Detector()
    found = []
    for k, (t, g) in enumerate(zip(at, gaze)):
        s = d.accept(t, g)
        if s is not None:
            found.append((s.start, s.stop, s.flagged, k, d.in_flight))
    return found


def _loss(n):
    z = np.zeros(n, dtype=bool)
    return TrackerLoss(blink=z, feature_lost=z.copy(), unreadable=z.copy())


def preproc(gaze_list, frame_gaps=()):
    g = np.array([[np.nan, np.nan] if p is None else p for p in gaze_list], dtype=float)
    vel = pp_velocity(g, FS)
    mask = validity_labels(g, vel, _loss(len(g)), frame_gaps, DEFAULT_VALIDITY_PARAMS, fs_hz=FS)
    runs = detect_engbert_kliegl(g, vel, list(mask.labels), FS, DEFAULT_EK_PARAMS)
    return [(int(r.start), int(r.stop)) for r in runs]


def lost(gaze, k):
    out = list(gaze)
    out[k] = None
    return out


def held(gaze, k):
    out = list(gaze)
    out[k] = out[k - 1]
    return out


if __name__ == "__main__":
    for dur, amp in [(12, 8.0), (4, 4.0), (8, 2.0)]:
        gaze, at = _trace([(200, dur, amp, 0.0)])
        whole_v1 = online(v1, gaze, at)
        start = whole_v1[0][0]
        print(f"\n{dur}-sample saccade of {amp} deg; whole trace: v1 {whole_v1}, "
              f"detect {[(s.start, s.stop, s.flagged) for s in cur.detect(gaze, at)]}, "
              f"pp-whole {preproc(gaze)}")
        print(f"{'lost':>5} | {'v1 live':<22} | {'v2 live (start,stop,flag,at,flying)':<34} | "
              f"{'cur live':<34} | {'cur detect':<20} | {'pp-nan':<12} | pp-gap")
        for into in range(-3, dur + 4):
            k = start + into
            g = lost(gaze, k)
            a = online(v1, g, at)
            b = online(v2, g, at)
            c = online(cur, g, at)
            d = [(s.start, s.stop, s.flagged) for s in cur.detect(g, at)]
            pn = preproc(g)
            pg = preproc(held(gaze, k), (FrameGap(row=k - 1, n_missing=1),))
            print(f"{into:>+5} | {str([x[:3] for x in a]):<22} | {str(b):<34} | {str(c):<34} | {str(d):<20} | "
                  f"{str(pn):<12} | {pg}")
