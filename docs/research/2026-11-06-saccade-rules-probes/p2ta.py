"""wl-preproc's detector at `82380d2`, in true angle (its v2), from an export of its source in the
directory the environment variable `WLPP_V2_SOURCE` names (README.md says how to make one):
`preproc` as p2's, the validity mask included, and `preproc_unavailable`, the lost sample alone
marked unavailable, no dilation."""
from __future__ import annotations

import dataclasses
import sys
from pathlib import Path

import numpy as np

import os  # noqa: E402

if "WLPP_V2_SOURCE" not in os.environ:
    raise SystemExit("set WLPP_V2_SOURCE to a directory holding wl-preproc's wl_preproc/ at 82380d2 (README.md)")
sys.path.insert(0, os.environ["WLPP_V2_SOURCE"])
from wl_preproc.eye.detect.engbert_kliegl import DEFAULT_EK_PARAMS, detect_engbert_kliegl  # noqa: E402
from wl_preproc.eye.detect.geometry import TRUE_ANGLE  # noqa: E402
from wl_preproc.eye.detect.validity import DEFAULT_VALIDITY_PARAMS, validity_labels  # noqa: E402
from wl_preproc.eye.detect.velocity import local_velocity, velocity as pp_velocity  # noqa: E402
from wl_preproc.eye.ohdpi import TrackerLoss  # noqa: E402
import wl_preproc  # noqa: E402

assert wl_preproc.__file__.startswith(os.path.abspath(os.environ["WLPP_V2_SOURCE"])), wl_preproc.__file__
FS = 500.0
TA = dataclasses.replace(DEFAULT_EK_PARAMS, geometry=TRUE_ANGLE)


def _loss(n):
    z = np.zeros(n, dtype=bool)
    return TrackerLoss(blink=z, feature_lost=z.copy(), unreadable=z.copy())


def preproc(gaze_list, frame_gaps=()):
    """The eye PC's file with the frame missing there too (NaN), its validity mask as p2 ran it."""
    g = np.array([[np.nan, np.nan] if p is None else p for p in gaze_list], dtype=float)
    mask = validity_labels(g, pp_velocity(g, FS), _loss(len(g)), frame_gaps, DEFAULT_VALIDITY_PARAMS, fs_hz=FS)
    runs = detect_engbert_kliegl(g, local_velocity(g, FS), list(mask.labels), FS, TA)
    return [(int(r.start), int(r.stop)) for r in runs]


def preproc_unavailable(gaze_list, fill):
    """Each lost sample marked unavailable alone (no dilation), its gaze `fill` (finite), as v2's
    fixtures mask one."""
    g = np.array([fill if p is None else p for p in gaze_list], dtype=float)
    available = [None if p is not None else "blink" for p in gaze_list]
    runs = detect_engbert_kliegl(g, local_velocity(g, FS), np.array(available, dtype=object), FS, TA)
    return [(int(r.start), int(r.stop), r.label.value) for r in runs]
