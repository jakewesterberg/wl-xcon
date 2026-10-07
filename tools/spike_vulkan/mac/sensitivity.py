"""Spike S: can the comparison fail? Draw the left eye's Gabor region with the exact
drawer from slightly wrong scenes and compare each with the GPU's panel, as compare.py
does. usage: sensitivity.py <panel_y.f32>"""
import json, sys
from dataclasses import replace

import numpy as np

import resolve_scene as rs
from _rig import RIG, STEREOSCOPE
from wl_xcon import exact, screen, viewport
from wl_xcon.photometry import Michelson
from wl_xcon.task import Gabor, Stimulus

STEP = 100.0 / 1023.0  # STAND-IN scale
REGION = (1015, 808, 1415, 1208)  # compare.py's gabor-left region, left-eye pixels
gpu = np.fromfile(sys.argv[1], dtype="<f4").reshape(2160, 3840).astype(np.float64)
g = gpu[808:1208, 1015:1415]
vp = viewport.viewports(RIG, STEREOSCOPE)[0]
base = dict(sf=2.0, sigma=0.5, phase=30.0, orientation=30.0, contrast=Michelson(0.5))
cases = {
    "as given": ({}, (2.0, 1.0)),
    "phase 31 deg": ({"phase": 31.0}, (2.0, 1.0)),
    "orientation 30.5 deg": ({"orientation": 30.5}, (2.0, 1.0)),
    "Michelson 0.505": ({"contrast": Michelson(0.505)}, (2.0, 1.0)),
    "sigma 0.505 deg": ({"sigma": 0.505}, (2.0, 1.0)),
    "x + 0.005 deg (~0.36 px)": ({}, (2.005, 1.0)),
    "x + 0.014 deg (~1 px)": ({}, (2.014, 1.0)),
}
for name, (change, at) in cases.items():
    stim = Stimulus("g", at=at, disparity=-0.2, looks=Gabor(**{**base, **change}))
    s = screen.resolve({"g": stim}, {}, rs.TRIAL, STEREOSCOPE, frame_period=1 / 240, frame=0)
    ref = exact.draw(s, vp, region=REGION)[..., 1]
    a = np.abs(g - ref)
    print(json.dumps({"reference": name, "max_abs_dY": float(a.max()), "max_in_steps": float(a.max() / STEP),
                      "mean_abs_dY": float(a.mean())}))
