"""**CIECAM16 and its uniform space, CAM16-UCS, for one viewing condition** (the console settings
design's §6; its plan's Task 8): the space a color set's hue angle is defined in, so a new color
defined from the console by a hue angle lands where the PI's generator would put it
(wl-style's `02-color/isohue_spectrum/isohue.py`, which made `isohue`).

**No new dependency** (the plan's Task 8, CLAUDE.md's dependency policy): the forward model, its
inverse and the uniform space are plain arithmetic in the standard library's `math`, as the rig's
photometry is. The model is CIECAM16 (CIE 248:2022) and its uniform space Li et al.'s
[@li2017comprehensive]: CAM16's J, M and h mapped by CAM02-UCS's coefficients (K_L 1, c1 0.007, c2
0.0228). **Written step for step as colour-science 0.4.7 computes it** (`colour/appearance/cam16.py`,
`colour/appearance/ciecam02.py`, `colour/models/cam16_ucs.py` and `colour/models/cam02_ucs.py`, read
at the tag v0.4.7 on GitHub, 2026-11-18), the version the PI's generator ran under, since agreeing
with his generator is the requirement: `tests/test_cam16.py` regenerates `isohue`'s four colors from
his numbers within 6e-5 in xy.

**XYZ relative to a white of Y 1**, the generator's frame (colour-science's "reference" domain scale,
in which `XYZ_to_CAM16UCS` multiplies its input by 100); J', a' and b' on their usual scale, J' 100 at
the white. Between trials or at load, never in a frame.
"""

from __future__ import annotations

import functools
import math
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Viewing:
    """One CAM16 viewing condition: the adopted white, CIE XYZ with Y 100; the adapting
    luminance `L_A` in cd/m²; the background's relative luminance `Y_b`; the surround's induction
    factors `F`, `c` and `N_c`; and whether the illuminant is discounted."""

    white: tuple[float, float, float]
    L_A: float
    Y_b: float
    F: float
    c: float
    N_c: float
    discount_illuminant: bool


#: **The viewing condition the PI's generator used**: colour-science 0.4.7's defaults for
#: `XYZ_to_CAM16UCS` and `CAM16UCS_to_XYZ`, which take `CAM_KWARGS_CIECAM02_sRGB` whole
#: (`colour/models/cam16_ucs.py`, `XYZ_to_UCS_Li2017` and `UCS_Li2017_to_XYZ`: `settings =
#: CAM_KWARGS_CIECAM02_sRGB.copy()`), read in its source at the tag v0.4.7 on GitHub
#: (github.com/colour-science/colour, `colour/appearance/ciecam02.py`, read 2026-11-18):
#: `XYZ_w` = `xy_to_XYZ(CCS_ILLUMINANTS["CIE 1931 2 Degree Standard Observer"]["D65"]) * 100`, the
#: D65 chromaticity there (0.31270, 0.32900) (`colour/colorimetry/datasets/illuminants/
#: chromaticity_coordinates.py`); `L_A` = 64 / π × 0.2; `Y_b` = 20; `surround` =
#: `VIEWING_CONDITIONS_CIECAM02["Average"]`, `InductionFactors_CIECAM02(1, 0.69, 1)`, which
#: `VIEWING_CONDITIONS_CAM16` copies (`colour/appearance/cam16.py`); and `XYZ_to_CAM16`'s own default
#: `discount_illuminant=False`. The isohue regeneration test is the gate on these.
VIEWING = Viewing(
    # colour-science's `xy_to_XYZ(xy) * 100`: the light of chromaticity (x, y) at Y 100.
    white=(100.0 * 0.31270 / 0.32900, 100.0, 100.0 * (1.0 - 0.31270 - 0.32900) / 0.32900),
    L_A=64.0 / math.pi * 0.2,
    Y_b=20.0,
    F=1.0,
    c=0.69,
    N_c=1.0,
    discount_illuminant=False,
)

#: CAM16's sharpening matrix, M16, row by row: colour-science 0.4.7's `CAT_CAT16`
#: (`colour/adaptation/datasets/cat.py`, read at v0.4.7 2026-11-18), which its `MATRIX_16` is.
M16 = (
    (0.401288, 0.650173, -0.051461),
    (-0.250268, 1.204414, 0.045854),
    (-0.002079, 0.048952, 0.953127),
)

#: CAM16-UCS's coefficients, K_L, c1 and c2: CAM02-UCS's [@li2017comprehensive], as colour-science
#: 0.4.7's `COEFFICIENTS_UCS_LUO2006["CAM02-UCS"]` (`colour/models/cam02_ucs.py`).
UCS = (1.00, 0.007, 0.0228)

#: The post-adaptation matrix of CAM16's inverse, row by row, over 1403
#: (`matrix_post_adaptation_non_linear_response_compression`).
_POST = ((460.0, 451.0, 288.0), (460.0, -891.0, -261.0), (460.0, -220.0, -6300.0))

#: colour-science's `EPSILON` floor on J in the inverse's `temporary_magnitude_quantity_inverse`
#: (`np.finfo(np.float64).eps`), so J at 0 does not divide by zero.
_EPSILON = 2.220446049250313e-16


def _apply(m, v) -> tuple[float, float, float]:
    return tuple(m[i][0] * v[0] + m[i][1] * v[1] + m[i][2] * v[2] for i in range(3))


def _inverse(m) -> tuple:
    """The inverse of a 3×3 given row by row, by its adjugate."""
    det = (m[0][0] * (m[1][1] * m[2][2] - m[1][2] * m[2][1])
           - m[0][1] * (m[1][0] * m[2][2] - m[1][2] * m[2][0])
           + m[0][2] * (m[1][0] * m[2][1] - m[1][1] * m[2][0]))
    cofactor = [[(m[(i + 1) % 3][(j + 1) % 3] * m[(i + 2) % 3][(j + 2) % 3]
                  - m[(i + 1) % 3][(j + 2) % 3] * m[(i + 2) % 3][(j + 1) % 3])
                 for j in range(3)] for i in range(3)]
    return tuple(tuple(cofactor[j][i] / det for j in range(3)) for i in range(3))


def _spow(a: float, p: float) -> float:
    """colour-science's `spow`: the sign of `a` times |a| to the `p`."""
    return math.copysign(abs(a) ** p, a) if a else 0.0


@dataclass(frozen=True, slots=True)
class _Condition:
    """What a viewing condition fixes, computed once (`_condition`)."""

    D_RGB: tuple[float, float, float]
    F_L: float
    n: float
    N_bb: float
    N_cb: float
    z: float
    A_w: float


def _compress(value: float, F_L: float) -> float:
    """CAM16's post-adaptation response compression, forward."""
    f = _spow(F_L * abs(value) / 100.0, 0.42)
    return (400.0 * math.copysign(1.0, value) * f) / (27.13 + f) + 0.1 if value else 0.1


def _expand(value: float, F_L: float) -> float:
    """CAM16's post-adaptation response compression, inverse."""
    d = value - 0.1
    if d == 0.0:
        return 0.0
    return math.copysign(1.0, d) * 100.0 / F_L * _spow((27.13 * abs(d)) / (400.0 - abs(d)),
                                                        1.0 / 0.42)


def _achromatic(rgb_a, N_bb: float) -> float:
    return (2.0 * rgb_a[0] + rgb_a[1] + rgb_a[2] / 20.0 - 0.305) * N_bb


@functools.lru_cache(maxsize=8)
def _condition(viewing: Viewing) -> _Condition:
    """What `viewing` fixes, once for each viewing condition, on first use."""
    X_w, Y_w, Z_w = viewing.white
    rgb_w = _apply(M16, viewing.white)
    D = 1.0 if viewing.discount_illuminant else min(max(
        viewing.F * (1.0 - (1.0 / 3.6) * math.exp((-viewing.L_A - 42.0) / 92.0)), 0.0), 1.0)
    n = viewing.Y_b / Y_w
    k = 1.0 / (5.0 * viewing.L_A + 1.0)
    k4 = k ** 4
    F_L = 0.2 * k4 * (5.0 * viewing.L_A) + 0.1 * (1.0 - k4) ** 2 * _spow(5.0 * viewing.L_A, 1.0 / 3.0)
    N_bb = N_cb = 0.725 * _spow(1.0 / n, 0.2)
    z = 1.48 + math.sqrt(n)
    D_RGB = tuple(D * Y_w / w + 1.0 - D for w in rgb_w)
    rgb_aw = tuple(_compress(d * w, F_L) for d, w in zip(D_RGB, rgb_w))
    return _Condition(D_RGB=D_RGB, F_L=F_L, n=n, N_bb=N_bb, N_cb=N_cb, z=z,
                      A_w=_achromatic(rgb_aw, N_bb))


def _eccentricity(h: float) -> float:
    return 0.25 * (math.cos(2.0 + h * math.pi / 180.0) + 3.8)


def jmh(xyz, viewing: Viewing = VIEWING) -> tuple[float, float, float]:
    """CAM16's lightness J, colorfulness M and hue angle h (degrees, 0 to 360) of CIE XYZ relative
    to a white of Y 1, under `viewing` (colour-science 0.4.7's `XYZ_to_CAM16`, step for step)."""
    k = _condition(viewing)
    rgb = _apply(M16, tuple(100.0 * float(v) for v in xyz))
    rgb_a = tuple(_compress(d * v, k.F_L) for d, v in zip(k.D_RGB, rgb))
    R, G, B = rgb_a
    a = R - 12.0 * G / 11.0 + B / 11.0
    b = (R + G - 2.0 * B) / 9.0
    h = math.degrees(math.atan2(b, a)) % 360.0
    A = _achromatic(rgb_a, k.N_bb)
    J = 100.0 * _spow(A / k.A_w, viewing.c * k.z)
    denominator = R + G + 21.0 * B / 20.0
    t = ((50000.0 / 13.0) * viewing.N_c * k.N_cb
         * (_eccentricity(h) * math.hypot(a, b) / denominator if denominator else 0.0))
    C = _spow(t, 0.9) * _spow(J / 100.0, 0.5) * _spow(1.64 - 0.29 ** k.n, 0.73)
    M = C * _spow(k.F_L, 0.25)
    return (J, M, h)


def to_ucs(xyz, viewing: Viewing = VIEWING) -> tuple[float, float, float]:
    """**CAM16-UCS's J', a' and b'** of CIE XYZ relative to a white of Y 1 [@li2017comprehensive]:
    J' = (1 + 100 c1) J / (1 + c1 J), M' = ln(1 + c2 M) / c2, (a', b') = M' (cos h, sin h)."""
    J, M, h = jmh(xyz, viewing)
    _, c1, c2 = UCS
    J_p = ((1.0 + 100.0 * c1) * J) / (1.0 + c1 * J)
    M_p = (1.0 / c2) * math.log1p(c2 * M)
    hr = math.radians(h)
    return (J_p, M_p * math.cos(hr), M_p * math.sin(hr))


def from_ucs(jab, viewing: Viewing = VIEWING) -> tuple[float, float, float]:
    """**CIE XYZ, relative to a white of Y 1, of CAM16-UCS's J', a' and b'**: `to_ucs`'s inverse
    (colour-science 0.4.7's `CAM16UCS_to_XYZ`, step for step)."""
    k = _condition(viewing)
    J_p, a_p, b_p = (float(v) for v in jab)
    _, c1, c2 = UCS
    J = -J_p / (c1 * J_p - 1.0 - 100.0 * c1)
    M = math.expm1(math.hypot(a_p, b_p) * c2) / c2
    h = math.degrees(math.atan2(b_p, a_p)) % 360.0
    C = M / _spow(k.F_L, 0.25)
    t = _spow(C / (math.sqrt(max(J, _EPSILON) / 100.0) * _spow(1.64 - 0.29 ** k.n, 0.73)),
              1.0 / 0.9)
    e_t = _eccentricity(h)
    A = k.A_w * _spow(J / 100.0, 1.0 / (viewing.c * k.z))
    P_2 = A / k.N_bb + 0.305
    P_3 = 21.0 / 20.0
    if t == 0.0:
        a = b = 0.0
    else:
        P_1 = (50000.0 / 13.0) * viewing.N_c * k.N_cb * e_t / t
        hr = math.radians(h)
        sin_h, cos_h = math.sin(hr), math.cos(hr)
        n = P_2 * (2.0 + P_3) * (460.0 / 1403.0)
        if abs(sin_h) >= abs(cos_h):
            b = n / (P_1 / sin_h + (2.0 + P_3) * (220.0 / 1403.0) * (cos_h / sin_h)
                     - (27.0 / 1403.0) + P_3 * (6300.0 / 1403.0))
            a = b * (cos_h / sin_h)
        else:
            a = n / (P_1 / cos_h + (2.0 + P_3) * (220.0 / 1403.0)
                     - ((27.0 / 1403.0) - P_3 * (6300.0 / 1403.0)) * (sin_h / cos_h))
            b = a * (sin_h / cos_h)
    rgb_a = tuple(v / 1403.0 for v in _apply(_POST, (P_2, a, b)))
    rgb = tuple(_expand(v, k.F_L) / d for v, d in zip(rgb_a, k.D_RGB))
    X, Y, Z = _apply(_inverse(M16), rgb)
    return (X / 100.0, Y / 100.0, Z / 100.0)
