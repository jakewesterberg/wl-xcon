"""CIECAM16 and CAM16-UCS in the standard library (`wl_xcon.cam16`; the console settings plan's
Task 8): its forward and inverse agree, the PI's generator's gray sits where wl-style's METHODS.md
says, and a hue angle in isohue's design frame lands on wl-xtasks' `stimuli/isohue.json`, which
that generator made under colour-science 0.4.7 -- the gate on `cam16.VIEWING`.

Arithmetic only, of published formulas and the PI's own numbers: nothing here is a measurement.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from _demo import xtasks_or_skip
from wl_xcon import cam16, colordef, photometry
from wl_xcon.photometry import D65, SRGB_WHITE_CD_M2, _srgb_fraction, srgb_hex

#: isohue's design, as the file's own source sentence gives it: "a CAM16-UCS hue sector at chroma
#: 29.49", its gray at J' 65 (wl-style's METHODS.md, "J′ = 65").
DESIGN = {"space": "CAM16-UCS", "gray_lightness": 65.0, "chroma": 29.49}
#: Each of isohue's colors by its hue angle about the gray: the file's source sentence.
HUES = {"blue": 260.0, "purple": 320.0, "red": 20.0, "green": 140.0}
#: How near each regenerated xy lies to the file's (the plan's Task 8): the file writes 5 places,
#: and its chroma to 2 (29.49), so a step of 5e-6 in each and of up to 0.005 in chroma.
NEAR = 6e-5


def test_cam16_round_trips_over_a_grid():
    """`from_ucs` inverts `to_ucs` to 1e-9 over a grid of lights, relative to a white of Y 1, from
    dark to bright and around the hue circle, achromatic ones among them."""
    worst = 0.0
    for J in (5.0, 20.0, 45.0, 65.0, 85.0, 99.0):
        for chroma in (0.0, 5.0, 15.0, 30.0):
            for hue in range(0, 360, 30):
                jab = (J, chroma * math.cos(math.radians(hue)),
                       chroma * math.sin(math.radians(hue)))
                back = cam16.to_ucs(cam16.from_ucs(jab))
                worst = max(worst, max(abs(a - b) for a, b in zip(jab, back)))
    assert worst < 1e-9, worst
    for xyz in ((0.2065, 0.1220, 0.0514), (0.3, 0.3, 0.3), (0.05, 0.1, 0.4), (0.9505, 1.0, 1.089)):
        back = cam16.from_ucs(cam16.to_ucs(xyz))
        assert max(abs(a - b) for a, b in zip(xyz, back)) < 1e-9, (xyz, back)


def test_cam16_agrees_with_colour_sciences_own_examples():
    """colour-science 0.4.7's own docstring examples, read at its v0.4.7 tag (2026-11-18):
    `XYZ_to_CAM16` of (19.01, 20.00, 21.78) under the white (95.05, 100.00, 108.88), L_A 318.31,
    Y_b 20 and the average surround gives J 41.7312079, h 217.0679597 and M 0.1074367; and
    `XYZ_to_UCS_Li2017` of (0.20654008, 0.12197225, 0.05136952) with CAM02-LCD's coefficients under
    the defaults gives (46.0658603, 41.0758649, 14.5102582)."""
    viewing = cam16.Viewing(white=(95.05, 100.0, 108.88), L_A=318.31, Y_b=20.0, F=1.0, c=0.69,
                            N_c=1.0, discount_illuminant=False)
    J, M, h = cam16.jmh((0.1901, 0.2000, 0.2178), viewing)
    assert (round(J, 7), round(h, 7), round(M, 7)) == (41.7312079, 217.0679598, 0.1074368)
    J, M, h = cam16.jmh((0.20654008, 0.12197225, 0.05136952))
    _, c1, c2 = 0.77, 0.007, 0.0053  # CAM02-LCD's
    J_p = ((1.0 + 100.0 * c1) * J) / (1.0 + c1 * J)
    M_p = math.log1p(c2 * M) / c2
    lcd = (J_p, M_p * math.cos(math.radians(h)), M_p * math.sin(math.radians(h)))
    assert [round(v, 7) for v in lcd] == [46.0658604, 41.0758649, 14.5102583]


def _gray(level: float) -> tuple[float, float, float]:
    """An sRGB gray of 8-bit level `level` as CIE XYZ relative to the white, Y 1."""
    lin = _srgb_fraction(level / 255.0)
    x, y = D65
    return (lin * x / y, lin, lin * (1.0 - x - y) / y)


def test_the_generators_gray_sits_where_its_methods_say():
    """wl-style's METHODS.md: the reference gray is "display-neutral (R = G = B) sRGB gray with
    CAM16-UCS lightness J′ = 65 (#969696 ...)", at a′, b′ ≈ −1.4, −0.8. **#969696 is that gray in
    8 bits, not a gray at J′ 65 itself**: its own J′ is 64.889 (computed 2026-11-18), so the test
    holds what the sentence says -- the D65 gray at J′ 65 shows as #969696 on the sRGB standard,
    #969696 is the 8-bit gray nearest J′ 65, and the gray's a′b′ lies within 0.05 of (−1.4, −0.8),
    as does the design frame's own gray (`colordef.gray_ucs`, at the gray's macaque luminance)."""
    low, high = 0.0, 1.0
    x, y = D65
    for _ in range(60):
        middle = (low + high) / 2.0
        J = cam16.to_ucs((middle * x / y, middle, middle * (1.0 - x - y) / y))[0]
        low, high = (middle, high) if J < 65.0 else (low, middle)
    Y = (low + high) / 2.0
    J, a, b = cam16.to_ucs((Y * x / y, Y, Y * (1.0 - x - y) / y))
    assert abs(J - 65.0) < 0.01
    white = SRGB_WHITE_CD_M2
    assert srgb_hex((white * Y * x / y, white * Y, white * Y * (1.0 - x - y) / y)) == "#969696"
    off = {level: abs(cam16.to_ucs(_gray(level))[0] - 65.0) for level in (149, 150, 151)}
    assert min(off, key=off.get) == 150, off
    assert math.hypot(a + 1.4, b + 0.8) < 0.05, (a, b)
    frame = colordef.Frame(name="isohue", apex=(0.31272, 0.32900), design=DESIGN)
    (_, a0, b0), _ = colordef.gray_ucs(frame)
    assert math.hypot(a0 + 1.4, b0 + 0.8) < 0.05, (a0, b0)


def test_hue_angle_regenerates_the_isohue_set():
    """**The gate on `cam16.VIEWING`** (the plan's Task 8): hues 260, 320, 20 and 140 at chroma
    29.49 about the gray at J′ 65 (the file's own source sentence), each matched to the gray's
    macaque luminance, land within 6e-5 in xy of wl-xtasks' `stimuli/isohue.json`, which the PI's
    generator made under colour-science 0.4.7. Its colors are read from the checkout, its design
    passed here (wl-xtasks' file gains its `design` in the plan's Task 11)."""
    path = xtasks_or_skip().parent / "stimuli" / "isohue.json"
    data = json.loads(path.read_text())
    data.pop("design", None)
    colorset = photometry.ColorSet(**data, design=DESIGN)
    residuals = {}
    for name, hue in HUES.items():
        x, y = colordef.chromaticity(colorset, "hue_angle", {"hue_deg": hue})
        fx, fy = colorset.colors[name]
        residuals[name] = (x - fx, y - fy)
    assert all(abs(dx) < NEAR and abs(dy) < NEAR for dx, dy in residuals.values()), residuals


@pytest.mark.parametrize("field, value", [("Y_b", 18.0), ("L_A", 64.0 / math.pi), ("c", 0.59)])
def test_another_viewing_condition_misses_the_set(field, value):
    """The gate can fail: another background, adapting luminance or surround moves at least one of
    isohue's four colors past `NEAR`."""
    import dataclasses

    other = dataclasses.replace(cam16.VIEWING, **{field: value})
    colorset = photometry.ColorSet.load(Path(__file__).parent / "fixtures" / "isohue_design.json")
    frame = colordef.frame(colorset)
    target = colordef._macaque(cam16.from_ucs((65.0, 0.0, 0.0), other))
    x, y = frame.apex
    unit = (x / y, 1.0, (1.0 - x - y) / y)
    gray = tuple(target / colordef._macaque(unit) * u for u in unit)
    _, a0, b0 = cam16.to_ucs(gray, other)
    worst = 0.0
    for name, hue in HUES.items():
        a = a0 + 29.49 * math.cos(math.radians(hue))
        b = b0 + 29.49 * math.sin(math.radians(hue))
        low, high = 1.0, 99.0
        for _ in range(60):
            middle = (low + high) / 2.0
            lum = colordef._macaque(cam16.from_ucs((middle, a, b), other))
            low, high = (middle, high) if lum < target else (low, middle)
        X, Y, Z = cam16.from_ucs(((low + high) / 2.0, a, b), other)
        fx, fy = colorset.colors[name]
        worst = max(worst, abs(X / (X + Y + Z) - fx), abs(Y / (X + Y + Z) - fy))
    assert worst > NEAR, worst
