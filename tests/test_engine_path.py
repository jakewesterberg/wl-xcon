"""What the checker accepts, the drawer draws (engine build A1, the final review).

Each piece was tested alone and the chain between them was not: the checker accepted
tasks the exact drawer then raised on, or drew invisibly or out of range, mostly when a
value was written as a parameter. So this walks the path a session will: `check`, then
`screen.resolve`, then `exact.draw` on a small preview of each eye. A trial the checker
accepts must draw, finite, never negative and visibly, or raise `NotYetDrawable` naming
the build that draws it (A2, A3 or A4).
"""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

import numpy as np
import pytest

from _calibrations import LINEAR
from _rig import DIRECT, RIG, STEREOSCOPE
from wl_xcon import exact, screen, viewport
from wl_xcon.check import check
from wl_xcon.photometry import DKL, RMS, SRGB, Calibration, Gray, Michelson, Weber, xyY
from wl_xcon.task import (
    After,
    Array,
    Disc,
    Gabor,
    Noise,
    On,
    Outcome,
    P,
    Param,
    Show,
    Square,
    State,
    Stimulus,
    Trial,
)

TASKS = Path(__file__).resolve().parents[1] / "tasks"
GRAY = Gray(20.0)
LIT = Disc(size=2.0, color=Gray(40.0))
GABOR = Gabor(sf=1.0, sigma=1.0, contrast=Michelson(0.5))

#: Illustrative, not measured (as `tests/test_reference_tasks.py`'s): a real calibration
#: comes from a photometer and is committed under `docs/measurements/`.
PANEL = Calibration(
    red=xyY(0.640, 0.330, 45.0),
    green=xyY(0.300, 0.600, 145.0),
    blue=xyY(0.150, 0.060, 15.0),
    background=xyY(0.3127, 0.3290, 50.0),
    transfer=(LINEAR,) * 3,
    observer="macaque V(lambda) -- placeholder, unmeasured",
    measured_on="2026-08-31",
)


def _load(name: str, attribute: str):
    sys.path.insert(0, str(TASKS))
    spec = importlib.util.spec_from_file_location(name, TASKS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return getattr(module, attribute)


def _shown(*stimuli, params=(), **fields) -> Trial:
    return Trial(
        start="on",
        params=list(params),
        states=[State("on", enter=[Show(s) for s in stimuli], go=[On(After(1.0), Outcome.ABORT)])],
        **fields,
    )


def _s(name, looks, **fields) -> Stimulus:
    return Stimulus(name, at=fields.pop("at", (0.0, 0.0)), looks=looks, **fields)


def _big(lum=30.0) -> Stimulus:
    return _s("big", Disc(size=6.0, color=Gray(lum)))


#: Each case: the trial (one state showing every stimulus), the parameter values, the
#: geometry, and the calibration it is checked against.
CASES = {
    "a lit disc": (_shown(_s("d", LIT)), {}, DIRECT, None),
    "a Weber disc on gray": (_shown(_s("d", Disc(size=2.0, contrast=Weber(0.5))), background=GRAY),
                             {}, DIRECT, None),
    "a Gabor on gray": (_shown(_s("g", GABOR), background=GRAY), {}, DIRECT, None),
    "a Gabor over a lit disc": (_shown(_big(40.0), _s("g", GABOR, layer=1), background=GRAY),
                                {}, DIRECT, None),
    "add": (_shown(_big(), _s("a", Disc(size=2.0, color=Gray(25.0)), combine="add"), background=GRAY),
            {}, DIRECT, None),
    "a window": (_shown(_big(40.0), _s("w", Disc(size=1.0, color=Gray(1.0)), combine="window", layer=1),
                        background=GRAY), {}, DIRECT, None),
    "a scotoma": (_shown(_big(40.0), _s("s", Disc(size=1.0, color=Gray(1.0)), combine="scotoma",
                                        layer=1), background=GRAY), {}, DIRECT, None),
    "multiply by a Weber disc": (_shown(_big(), _s("m", Disc(size=1.0, contrast=Weber(-0.5)),
                                                   combine="multiply", layer=1), background=GRAY),
                                 {}, DIRECT, None),
    "multiply by a Gabor": (_shown(_big(), _s("m", GABOR, combine="multiply", layer=1), background=GRAY),
                            {}, DIRECT, None),
    # It draws none of its own light, so it needs none (XC-257).
    "a window with no light": (_shown(_big(40.0), _s("w", Disc(size=1.0), combine="window", layer=1)),
                               {}, DIRECT, None),
    # Its mean is never used, so the black default leaves nothing undrawn (XC-256).
    "multiply by a Gabor on black": (_shown(_big(), _s("m", GABOR, combine="multiply", layer=1)),
                                     {}, DIRECT, None),
    "per-eye positions on the stereoscope": (
        _shown(_s("r", LIT, at_left=(2.0, 0.0), at_right=(-2.0, 0.0)), view="stereoscope"),
        {}, STEREOSCOPE, None),
    "a near disparity on the stereoscope": (
        _shown(_s("n", LIT, disparity=-0.5), view="stereoscope"), {}, STEREOSCOPE, None),
    "an array of lit items": (
        _shown(_s("a", Array(n=4, radius=5.0, looks=LIT, among=Square(size=2.0, color=Gray(40.0))))),
        {}, DIRECT, None),
    "a light written as parameters": (
        _shown(_s("p", Disc(size=P("s"), contrast=P("c"))), background=Gray(P("bg")),
               params=[Param("s", unit="deg", low=0.5, high=4.0, start=2.0),
                       Param("c", unit="contrast", choices=(Weber(0.5), Weber(-0.5))),
                       Param("bg", unit="cd/m2", low=10.0, high=40.0, start=20.0)]),
        {"s": 2.0, "c": Weber(0.5), "bg": 20.0}, DIRECT, None),
    "noise, a later build's fill": (_shown(_s("n", Noise(contrast=RMS(0.2))), background=GRAY),
                                    {}, DIRECT, None),
    "an isoluminant color, a later build's light": (
        _shown(_s("k", Disc(size=2.0, color=DKL(lum=0.0, l_m=0.08))), background=GRAY),
        {}, DIRECT, PANEL),
}

#: Each reference task, with the stimulus it shows first and the calibration it needs.
REFERENCE = {
    "fixation_detection": ("detection", "FIX", None),
    "adaptive_detection": ("adaptive_detection", "FIX", None),
    "visual_search": ("search", "FIX", PANEL),
    "visual_search_training": ("search", "FIX", SRGB),
    "calibration": ("calibration", "TARGET", None),
}


def _drawn_or_named(trial, stimuli, values, geometry):
    """Resolve and draw each eye; a `NotYetDrawable` must name the build that draws it."""
    try:
        s = screen.resolve({x.name: x for x in stimuli}, values, trial, geometry, frame_period=1 / 240)
        eyes = viewport.viewports(RIG, geometry, pixels=(192, 108))
        images = [exact.draw(s, vp, supersample=2) for vp in eyes]
    except screen.NotYetDrawable as later:
        assert re.search(r"\bA[234]\b", str(later)), f"names no later build: {later}"
        return
    for vp, image in zip(eyes, images):
        background = np.asarray(s.background_right if vp.eye == "right" else s.background_left)
        assert np.isfinite(image).all() and image.min() >= 0.0, vp.eye
        assert np.abs(image - background).max() > 0.1, f"nothing visible in the {vp.eye} eye"


@pytest.mark.parametrize("case", CASES)
def test_a_trial_the_checker_accepts_is_drawn_or_names_the_build_that_will(case):
    trial, values, geometry, calibration = CASES[case]
    assert [f for f in check(trial, geometry=geometry, calibration=calibration) if f.blocking] == []
    _drawn_or_named(trial, [a.stimulus for a in trial.states[0].enter], values, geometry)


@pytest.mark.parametrize("task", REFERENCE)
def test_each_reference_task_s_first_stimulus_is_drawn_at_its_starting_values(task):
    attribute, stimulus, calibration = REFERENCE[task]
    trial = _load(task, attribute)
    allocation = _load("allocation", "ALLOCATION")
    assert [f for f in check(trial, allocation, geometry=DIRECT, calibration=calibration)
            if f.blocking] == []
    values = {p.name: p.start for p in trial.params if p.start is not None}
    # `calibration` declares no starting position yet (XC-183); straight ahead is one it allows.
    values.setdefault("target_x", 0.0)
    values.setdefault("target_y", 0.0)
    _drawn_or_named(trial, [_load(task, stimulus)], values, DIRECT)
