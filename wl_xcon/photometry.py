"""Colour as a physical claim, checked against a measured display.

**RGB is not a colour.** It is a triple of instructions to one particular panel,
so the same task file is a different stimulus on every monitor, and a methods
section quoting it describes nothing reproducible. Everything here is specified in
a device-independent space and converted, at load, against a calibration somebody
measured with a photometer.

The word that forces this is *isoluminant*. It is the control condition of most
chromatic experiments, it is a claim about photometry, and an unmeasured claim of
isoluminance is usually false -- so this module makes stating it require a
calibration that names whose luminous efficiency it was measured against. A
macaque's is not a human's.

**No measured calibration for our panels exists yet** (build J measures one). Until a
rig names one, sessions run on `SRGB`, the sRGB standard, and the warnings list says so
(engine spec §7.1, build B). A measured one is a JSON record (`read_calibration`),
committed under `docs/measurements/<rig>/`.
"""

from __future__ import annotations

import json
import math
import os
import re
import stat
from dataclasses import dataclass, field
from datetime import date


@dataclass(frozen=True, slots=True)
class Color:
    """Base for the colour vocabulary. Two spaces, for two different questions."""


@dataclass(frozen=True, slots=True)
class xyY(Color):
    """CIE 1931 chromaticity plus luminance in cd/m^2.

    An **absolute** specification: this names a light. Use it to reproduce a
    published stimulus, or when the quantity that matters is the light itself
    rather than its distance from the background.
    """

    x: float
    y: float
    Y: float


@dataclass(frozen=True, slots=True)
class DKL(Color):
    """Derrington-Krauskopf-Lennie cone-opponent contrast, relative to the background.

    A **modulation**: each component is a contrast away from the background along one
    cardinal axis, so the background itself is `DKL()`. This is the space nearly every
    chromatic experiment wants, because the three axes are the ones early visual
    cortex is organised around and because **`lum=0` is isoluminant by construction**
    rather than by arithmetic somebody did once in a spreadsheet.

    `l_m` is the L-minus-M axis (red/green), `s_lm` the S-cone axis (violet/lime).

    **Read as the PI's hybrid** (A2's Q1; `cone_contrast`): `lum` a luminance contrast, `l_m` and
    `s_lm` pooled cone contrast along their isolating directions, in the lab's observer
    (`cones.CIE2006_10`).
    """

    lum: float = 0.0
    l_m: float = 0.0
    s_lm: float = 0.0


@dataclass(frozen=True, slots=True)
class ConeContrast(Color):
    """Cone contrast about the background: each cone's change in excitation over the
    background's, ΔL/L, ΔM/M and ΔS/S [@brainard1996cone, p. 564, Eq. A.4.1], in the lab's
    observer (`cones.CIE2006_10`). For cone-isolating stimuli (engine spec §7.4): `S=0.5` alone
    raises the S cones' excitation by half and leaves L and M where the background has them.

    A **modulation**, as `DKL` is: relative to the background, so it names no light on black
    (spec §7.5), and the background itself is `ConeContrast()`. Each component may be a parameter.
    Whether one claims isoluminance is `check`'s to say (`isoluminance-on-default`; the engine A2
    plan's call 15)."""

    L: object = 0.0
    M: object = 0.0
    S: object = 0.0


#: The colors defined against the background in cone terms: a light only once a calibration and
#: a background convert them (`cone_xyz`).
CONE_COLORS = (DKL, ConeContrast)


#: CIE 1931 chromaticity of D65, the white point of the sRGB standard (IEC 61966-2-1).
D65 = (0.3127, 0.3290)


@dataclass(frozen=True, slots=True)
class Gray(Color):
    """Achromatic light at an absolute luminance: D65 white at `cd_m2` cd/m^2.

    The PI's rule for an achromatic stimulus that is not a contrast against a declared
    background (2026-10-07, "Absolute cd/m²"): the same light on every calibrated rig.
    `cd_m2` may be a parameter; `screen.resolve` binds it.
    """

    cd_m2: object


def to_xyz(color: "xyY | Gray") -> tuple[float, float, float]:
    """CIE XYZ of an absolute color, Y in cd/m^2.

    Only an absolute color names a light by itself. `DKL` is a modulation relative to
    the background, converted against one through a calibration by `cone_xyz`. A `Gray`
    whose luminance is still a parameter names none until it is bound.
    """
    if isinstance(color, Gray):
        cd_m2 = color.cd_m2
        if not isinstance(cd_m2, (int, float)):
            from wl_xcon.task import P  # `task` imports this module

            if isinstance(cd_m2, P):
                raise TypeError(
                    f"Gray's luminance is parameter {cd_m2.name!r}: bind it to a number "
                    f"first, as `screen.resolve` binds a task's parameters"
                )
        return _XYZ(xyY(D65[0], D65[1], float(cd_m2)))
    if isinstance(color, xyY):
        return _XYZ(color)
    raise TypeError(
        f"{type(color).__name__} is relative to the background, not a light by itself; "
        f"`cone_xyz` converts it against one, through a calibration"
    )


@dataclass(frozen=True, slots=True)
class Contrast:
    """A contrast written with its convention (the PI, 2026-10-07: "Always written
    explicitly"). `value` may be a parameter."""

    value: object


@dataclass(frozen=True, slots=True)
class Weber(Contrast):
    """(L − L_background) / L_background: a patch against its background."""


@dataclass(frozen=True, slots=True)
class Michelson(Contrast):
    """(L_max − L_min) / (L_max + L_min): a periodic pattern about its mean."""


@dataclass(frozen=True, slots=True)
class RMS(Contrast):
    """The standard deviation of luminance over its mean: noise and images."""


def _finite_number(value: object) -> bool:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:  # an integer too large for a float, which a JSON record can hold
        return False


@dataclass(frozen=True, slots=True)
class Transfer:
    """One channel's transfer, as measured (engine spec §7.6: "The transfer is a measured table
    per channel"; N§4 batch 1, since a QD-OLED's transfer is not a power law): at each drive
    `level`, the output code over its maximum, the channel's light as a `fraction` of its light
    at full drive. **Stored and checked here, never evaluated in build B**: turning a light into
    output levels through it is build A2's (`exact.py`'s docstring).

    **Black-subtracted** (engine build A2; ADR-0011): its fraction at level 0 is 0, the panel's
    black carried, when build J measures one, as a single ambient term (XC-309)."""

    levels: tuple
    fractions: tuple

    def __post_init__(self) -> None:
        levels, fractions = self.levels, self.fractions
        if not (isinstance(levels, tuple) and isinstance(fractions, tuple)):
            raise ValueError("a transfer's levels and fractions are tuples of numbers")
        if len(levels) != len(fractions) or len(levels) < 2:
            raise ValueError(
                f"a transfer pairs each level with one fraction, at least two of each; this one "
                f"has {len(levels)} levels and {len(fractions)} fractions"
            )
        if not all(_finite_number(v) for v in (*levels, *fractions)):
            raise ValueError("a transfer's levels and fractions are finite numbers")
        if levels[0] != 0.0 or levels[-1] != 1.0:
            raise ValueError(
                f"a transfer runs from level 0 to level 1; this one runs from {levels[0]} to "
                f"{levels[-1]}"
            )
        if any(later <= earlier for earlier, later in zip(levels, levels[1:])):
            raise ValueError("a transfer's levels rise strictly")
        if any(later < earlier for earlier, later in zip(fractions, fractions[1:])):
            raise ValueError("a transfer's fractions never fall as its level rises")
        if fractions[0] != 0.0 or fractions[-1] != 1.0:
            raise ValueError(
                f"a transfer's fractions start at 0 at level 0, the channel's light with the "
                f"panel's black subtracted (ADR-0011), and end at 1, full drive; this one runs "
                f"from {fractions[0]} to {fractions[-1]}"
            )


#: What a calibration's spectra must cover, nm: the CIE table runs 390-830, and beyond 780 nm the
#: L cones take 2.4e-6 of an equal-energy light's excitation and the M cones 2.3e-7 (the bundled
#: table integrated by the trapezoid rule, 2026-10-10), so a spectrum may stop there.
SPECTRA_COVER = (390.0, 780.0)
#: The widest step between a spectrum's wavelengths, nm: the CIE table's own.
SPECTRA_STEP = 5.0


@dataclass(frozen=True, slots=True)
class Spectra:
    """Each primary's spectral radiance at full drive, W·sr⁻¹·m⁻²·nm⁻¹, at the wavelengths `nm`
    the spectroradiometer sampled (engine spec §7.9: "The spectroradiometer's spectra are stored in
    each calibration, so any named set converts from them"). **The record holds what was
    measured**: the cone tables are interpolated onto these wavelengths, never these onto the
    tables' (`cones.excitations`)."""

    nm: tuple
    red: tuple
    green: tuple
    blue: tuple

    def __post_init__(self) -> None:
        nm = self.nm
        if not (isinstance(nm, tuple) and len(nm) >= 2 and all(_finite_number(v) for v in nm)):
            raise ValueError("a calibration's spectra are sampled at a tuple of finite wavelengths")
        if any(later <= earlier for earlier, later in zip(nm, nm[1:])):
            raise ValueError("a calibration's spectra's wavelengths rise strictly")
        if nm[0] > SPECTRA_COVER[0] or nm[-1] < SPECTRA_COVER[1]:
            raise ValueError(
                f"a calibration's spectra cover {SPECTRA_COVER[0]:g} to {SPECTRA_COVER[1]:g} nm; "
                f"these run from {nm[0]:g} to {nm[-1]:g}"
            )
        widest = max(later - earlier for earlier, later in zip(nm, nm[1:]))
        if widest > SPECTRA_STEP:
            raise ValueError(
                f"a calibration's spectra are sampled at least every {SPECTRA_STEP:g} nm, the CIE "
                f"table's step; these leave a gap of {widest:g} nm"
            )
        for channel in _CHANNELS:
            values = getattr(self, channel)
            if not (isinstance(values, tuple) and len(values) == len(nm)):
                raise ValueError(
                    f"the {channel} spectrum gives one radiance at each of the {len(nm)} "
                    f"wavelengths, as a tuple"
                )
            if not all(_finite_number(v) and v >= 0.0 for v in values) or not any(values):
                raise ValueError(
                    f"the {channel} spectrum is finite radiances, none negative and not all zero"
                )


_ISO_DAY = re.compile(r"\d{4}-\d{2}-\d{2}")


@dataclass(frozen=True, slots=True)
class Calibration:
    """A display, as measured. Every field is an observation, not a setting.

    `observer` names whose luminous efficiency **this record's own luminances** were measured
    against (its cd/m², CIE V(λ) as photometry has it). **Isoluminance is not the record's**: it
    is the lab observer's V_F,10 (A2's Q5; `cones.CIE2006_10`), the same on every calibration and
    recorded with each session.

    **Or the standard** (`standard=True`, `SRGB`): the default a session runs on when its
    rig names no measured calibration (engine spec §7.1), measured by nobody, and listed as
    a warning (`warnlist`). One calibration for the whole panel (spec §7.6)."""

    red: xyY
    green: xyY
    blue: xyY
    background: xyY
    #: Each channel's measured transfer: red, green, blue (spec §7.6). Replaces the gamma
    #: exponent nothing read (build B).
    transfer: tuple
    observer: str
    #: The day it was measured, `YYYY-MM-DD`; empty for the standard, which nobody measured.
    measured_on: str
    #: The record's name, as the rig file, the session record and the page give it.
    id: str = ""
    #: Whether this is the sRGB standard rather than a measurement (spec §7.1).
    standard: bool = False
    #: Each primary's measured spectrum (engine spec §7.9), from which cone colors convert; `None`
    #: for the standard, which has none, and for a measured calibration taken without them, against
    #: which no cone color converts (`cones`).
    spectra: Spectra | None = None
    #: The 3×3 from CIE XYZ to the lab observer's cone excitations (`cones`), computed once, as
    #: the calibration is built; and, where there is none, why no cone color converts.
    _cones: tuple | None = field(init=False, default=None, compare=False, repr=False)
    cones_refused: str = field(init=False, default="", compare=False, repr=False)

    def __post_init__(self) -> None:
        if not (
            isinstance(self.transfer, tuple)
            and len(self.transfer) == 3
            and all(isinstance(t, Transfer) for t in self.transfer)
        ):
            raise ValueError("a calibration holds three transfers: red, green and blue")
        # Lights a display can make: a primary at full drive gives light, the background may be
        # black (spec §7.5), and x + y may pass 1 by `TOLERANCE`, for rounding alone.
        for what, light in (
            ("red primary", self.red),
            ("green primary", self.green),
            ("blue primary", self.blue),
            ("background", self.background),
        ):
            least = "0 or above" if what == "background" else "above 0"
            if not (
                isinstance(light, xyY)
                and all(_finite_number(v) for v in (light.x, light.y, light.Y))
                and light.x >= 0.0
                and light.y > 0.0
                and light.x + light.y <= 1.0 + TOLERANCE
                and (light.Y >= 0.0 if what == "background" else light.Y > 0.0)
            ):
                raise ValueError(
                    f"the {what} is {light}, a light no display makes: its x is 0 or above, its "
                    f"y above 0, x + y at most 1 and its luminance {least}, each a finite number"
                )
        if abs(_det3([[p.x, p.y, 1.0] for p in (self.red, self.green, self.blue)])) < 1e-12:
            raise ValueError(
                "the three primaries lie on one line in xy, so they do not span a gamut"
            )
        if self.spectra is not None and not isinstance(self.spectra, Spectra):
            raise ValueError("a calibration's spectra are a `Spectra`, or None")
        if self.standard:
            if self.spectra is not None:
                raise ValueError("the standard is measured by nobody, so it has no spectra")
            self._convert()
            return
        if not (isinstance(self.observer, str) and self.observer.strip()):
            raise ValueError(
                "a measured calibration names the observer its luminances were measured against"
            )
        if not (isinstance(self.measured_on, str) and _ISO_DAY.fullmatch(self.measured_on)):
            raise ValueError(
                f"measured_on is the day it was measured, YYYY-MM-DD; got {self.measured_on!r}"
            )
        try:
            date.fromisoformat(self.measured_on)
        except ValueError as refused:
            raise ValueError(
                f"measured_on is the day it was measured, YYYY-MM-DD; {self.measured_on!r} is "
                f"no such day"
            ) from refused
        self._convert()

    def _convert(self) -> None:
        """Compute the cone matrix once (`cones`). **The standard**: the inverse of the CIE's
        LMS-to-XYZ_F,10 transformation, applied to the standard's CIE 1931 XYZ (A2's Q2, "CIE's
        published matrix"; COL-18) -- **a use outside the CIE's definition**, which defines it for
        XYZ_F,10, and recorded as such (`cone_record`). **Measured**: each primary's excitations
        from its spectrum (`cones.excitations`), times the inverse of the primaries' measured XYZ
        -- exact for every mixture of the three, which is every light the panel makes. Without
        spectra, or when the bundled table is refused (`cones.cie_file`), there is no matrix and
        `cones_refused` says why: plain colors still check, and each cone color is refused with
        that sentence."""
        from wl_xcon import cones

        matrix, refused = None, ""
        name = self.id or self.measured_on
        if self.standard:
            matrix = _inverse3(cones.LMS_TO_XYZ_F10)
        elif self.spectra is None:
            refused = (
                f"calibration {name} was measured without spectra, so no cone color converts "
                f"against it: a measured calibration converts cone colors from its primaries' "
                f"spectra (engine spec §7.9)"
            )
        else:
            try:
                s = self.spectra
                excited = [cones.excitations(s.nm, getattr(s, c)) for c in _CHANNELS]
                lms = tuple(tuple(excited[j][i] for j in range(3)) for i in range(3))
                xyz = tuple(
                    tuple(_XYZ(p)[i] for p in (self.red, self.green, self.blue)) for i in range(3))
                matrix = _product3(lms, _inverse3(xyz))
            except ValueError as error:
                refused = f"calibration {name}'s cones could not be computed: {error}"
        object.__setattr__(self, "_cones", matrix)
        object.__setattr__(self, "cones_refused", refused)

    def age_days(self, today: date) -> int | None:
        """Whole days since it was measured, by the calendar (spec §7.10: a calibration "never
        expires" but carries its age); `None` for the standard, which nobody measured."""
        if self.standard:
            return None
        return (today - date.fromisoformat(self.measured_on)).days

    def weights(self, color: xyY) -> tuple[float, float, float]:
        """Linear primary weights for a colour, by solving the 3x3 mixture.

        Inside the gamut exactly when all three weights lie in [0, 1]: that is what
        "this panel can make this light" means, and it covers chromaticity and
        luminance in one test rather than two approximations.
        """
        return self.weights_of(_XYZ(color))

    def weights_of(self, xyz) -> tuple[float, float, float]:
        """`weights`, for a light given as CIE XYZ."""
        columns = [_XYZ(p) for p in (self.red, self.green, self.blue)]
        return _solve3(columns, xyz)

    @property
    def cones(self) -> tuple | None:
        """The 3×3 that turns CIE XYZ (Y in cd/m²) into the lab observer's cone excitations
        (`cones.CIE2006_10`) for every light this panel makes, row by row, computed once as the
        calibration is built (`_convert`); `None` where no cone color converts, `cones_refused`
        saying why."""
        return self._cones


#: What luminance a DKL color's `lum` and isoluminance hold on the standard (the engine A2 plan's
#: review S-I2): the CIE's matrix makes V_F,10 the standard's own CIE 1931 Y, so on a panel
#: whose real primaries differ, the true V_F,10 contrast of such a light is unknown.
HELD_STANDARD = "the standard's CIE 1931 Y, which the CIE's matrix equates with V_F,10"
#: And on a measured calibration with spectra.
HELD_SPECTRA = "V_F,10, computed from the primaries' measured spectra"


def _inverse3(m) -> tuple:
    """The inverse of a 3×3 given row by row, by its adjugate."""
    det = _det3(m)
    if abs(det) < 1e-12:
        raise ValueError("a 3×3 with no inverse: its rows are not independent")
    cofactor = [[(m[(i + 1) % 3][(j + 1) % 3] * m[(i + 2) % 3][(j + 2) % 3]
                  - m[(i + 1) % 3][(j + 2) % 3] * m[(i + 2) % 3][(j + 1) % 3])
                 for j in range(3)] for i in range(3)]
    return tuple(tuple(cofactor[j][i] / det for j in range(3)) for i in range(3))


def _product3(a, b) -> tuple:
    """`a` times `b`, two 3×3 given row by row."""
    return tuple(tuple(sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3))
                 for i in range(3))


def _apply3(m, v) -> tuple[float, float, float]:
    """A 3×3, row by row, times a vector."""
    return tuple(sum(m[i][k] * v[k] for k in range(3)) for i in range(3))


def cone_contrast(color, panel: "Calibration", background: xyY) -> tuple[float, float, float]:
    """ΔL/L, ΔM/M and ΔS/S of a cone color about `background` on `panel`, in the lab's observer.

    **A `DKL` color is read as the PI's hybrid** (A2's Q1, "Hybrid"; COL-07)
    [@brainard1996cone, pp. 571-572]: `lum` is a luminance contrast, the background scaled, so
    each cone changes by `lum`; `l_m` and `s_lm` are pooled cone contrast, the root of the sum of
    the three contrasts squared [@brainard1996cone, p. 568, Eq. A.4.2], along their isolating
    directions. The `l_m` direction changes L and M and not S, at the ratio that keeps V_F,10
    (`cones.V_F10`) where the background has it, so `lum=0` is isoluminant by construction in the
    lab's observer (A2's Q5); the `s_lm` direction changes S alone, which V_F,10 does not see.
    **Signs** (the engine A2 plan's call 14): `+l_m` raises L and lowers M (toward red), `+s_lm`
    raises S (toward violet), `+lum` brightens. A `ConeContrast` is its own three numbers.
    Every component a number: `screen.resolve`
    binds a task's parameters first, and `check` reads each value one can take."""
    return _contrast(color, background_cones(panel, background))


def background_cones(panel: "Calibration", background: xyY) -> tuple[float, float, float]:
    """The lab observer's cone excitations of `background` on `panel`. **Refused on black**: a
    cone color is a contrast about its background, and black has none to be relative to (engine
    spec §7.5; COL-09). Refused too on a measured calibration with no spectra."""
    return _excited(_cone_matrix(panel), background)


def cone_xyz(color, panel: "Calibration", background: xyY) -> tuple[float, float, float]:
    """CIE XYZ, Y in cd/m², of a cone color against `background` on `panel`
    [@brainard2002display, pp. 177-178, Eq. 14]: the background's excitations, each scaled by one
    plus its contrast (`cone_contrast`), back through `Calibration.cones`."""
    matrix = _cone_matrix(panel)
    excited = _excited(matrix, background)
    contrast = _contrast(color, excited)
    return _apply3(_inverse3(matrix), tuple(e * (1.0 + c) for e, c in zip(excited, contrast)))


def _cone_matrix(panel: "Calibration") -> tuple:
    if panel.cones is None:
        raise ValueError(panel.cones_refused)
    return panel.cones


def _excited(matrix, background: xyY) -> tuple[float, float, float]:
    if background.Y <= 0.0:
        raise ValueError(
            "a cone color is relative to its background, and this background is black (engine "
            "spec §7.5)"
        )
    return _apply3(matrix, _XYZ(background))


def _contrast(color, excited) -> tuple[float, float, float]:
    if isinstance(color, ConeContrast):
        return _numbers(color, (color.L, color.M, color.S))
    if not isinstance(color, DKL):
        raise TypeError(f"{type(color).__name__} is not a cone color")
    weight_l, weight_m = v_f10_weights(excited)
    ratio = weight_l / weight_m
    norm = math.sqrt(1.0 + ratio * ratio)
    lum, l_m, s_lm = _numbers(color, (color.lum, color.l_m, color.s_lm))
    return (lum + l_m / norm, lum - l_m * ratio / norm, lum + s_lm)


def v_f10_weights(excited) -> tuple[float, float]:
    """V_F,10's weights on the L and M contrasts about a background whose excitations are
    `excited`: each cone's V_F,10 coefficient times its excitation."""
    from wl_xcon import cones

    return cones.V_F10[0] * excited[0], cones.V_F10[1] * excited[1]


def luminance_contrast(L: float, M: float, excited) -> float:
    """The V_F,10 luminance contrast of cone contrasts `L` and `M` about a background (a `DKL`
    color's `lum`, which `_contrast` inverts): their weighted mean under `v_f10_weights`."""
    weight_l, weight_m = v_f10_weights(excited)
    return (weight_l * L + weight_m * M) / (weight_l + weight_m)


def _numbers(color, values) -> tuple[float, ...]:
    """A cone color's components as numbers. **A `ValueError`, never a `TypeError`**, for one that
    is still a parameter or not a number: `check` reads each value a parameter can take first, and
    `screen.resolve` binds them; a caller that did neither is refused by the same sentence an
    unrealizable color is (XC-269; the engine A2 plan's call 28)."""
    if not all(_finite_number(v) for v in values):
        raise ValueError(
            f"{color} has a component that is not a number: a parameter is bound, or read at each "
            f"value it can take, before a cone color converts"
        )
    return tuple(float(v) for v in values)


def _XYZ(c: xyY) -> tuple[float, float, float]:
    """xyY to CIE XYZ. `y == 0` is not a colour; it is a typo."""
    if c.y <= 0.0:
        raise ValueError(f"chromaticity y must be positive, got {c.y}")
    return (c.Y * c.x / c.y, c.Y, c.Y * (1.0 - c.x - c.y) / c.y)


def _solve3(columns, target) -> tuple[float, float, float]:
    """Solve `columns @ w = target` by Cramer's rule.

    Three unknowns, done by hand rather than by pulling in a linear-algebra
    dependency for nine multiplications (CLAUDE.md's dependency policy).
    """
    a = [[columns[j][i] for j in range(3)] for i in range(3)]
    det = _det3(a)
    if abs(det) < 1e-12:
        raise ValueError("display primaries are degenerate: they do not span a gamut")
    out = []
    for j in range(3):
        m = [row[:] for row in a]
        for i in range(3):
            m[i][j] = target[i]
        out.append(_det3(m) / det)
    return (out[0], out[1], out[2])


def _det3(m) -> float:
    return (
        m[0][0] * (m[1][1] * m[2][2] - m[1][2] * m[2][1])
        - m[0][1] * (m[1][0] * m[2][2] - m[1][2] * m[2][0])
        + m[0][2] * (m[1][0] * m[2][1] - m[1][1] * m[2][0])
    )


#: A hair of slack on the gamut test. Measured primaries carry measurement error,
#: and refusing a colour that sits 10^-9 outside a boundary would reject stimuli
#: that are physically fine for a reason no experimenter could act on.
TOLERANCE = 1e-6


def unrealizable(color: Color, panel: Calibration, background: xyY | None = None) -> str | None:
    """Why `panel` cannot produce `color`, or `None` if it can: **by full conversion to primary
    weights, for every space** (engine spec §7.4; COL-08) [@brainard2002display, pp. 177-178,
    Eq. 14]. Each weight must lie in [0, 1] within `TOLERANCE`: a transfer's fractions are
    black-subtracted (ADR-0011), so 0 is what each channel adds undriven. A cone color is
    converted against `background` first (`cone_xyz`), so it is realizable only against one: the
    same `DKL` fits on a mid gray and not on a bright one (COL-10). This replaces the
    `max_cone_contrast` gate, which passed red-green contrasts no panel could make (the science
    review's 7(b); the A2 research note §3)."""
    try:
        if isinstance(color, CONE_COLORS):
            if background is None:
                return "it is relative to the background, and no background was given"
            xyz = cone_xyz(color, panel, background)
        elif isinstance(color, xyY):
            xyz = _XYZ(color)
        else:
            return None
        weights = panel.weights_of(xyz)
    except ValueError as exc:
        return str(exc)
    if not all(-TOLERANCE <= w <= 1.0 + TOLERANCE for w in weights):  # NaN fails closed
        return (
            f"needs primary weights {tuple(round(w, 3) for w in weights)}, which are outside "
            f"[0, 1]; the panel would clip, and a clipped color is neither the requested "
            f"chromaticity nor the requested luminance"
        )
    return None


#: A calibration record's fields, each required and no other but `RECORD_OPTIONAL` (Question 4:
#: one JSON file per measured calibration).
RECORD_FIELDS = ("id", "measured_on", "observer", "primaries", "background", "transfer")
#: The one field a record may leave out (engine build A2): its primaries' spectra, without which it
#: converts no cone color (`Calibration.cones`). Given, it is never `null`.
RECORD_OPTIONAL = ("spectra",)
_CHANNELS = ("red", "green", "blue")

#: The longest id a record may carry: the rig file, `config.json`, every run's start row and
#: every frame name it, and the calibration-age warning quotes it in a sentence the page's
#: open sends back (`link.NOTE_LIMIT`, Call 25), so it is bounded where it is read.
ID_LIMIT = 64

#: The largest record file read, in bytes: 1 MiB. A record holding the sRGB table at all 1024
#: levels on each channel is 132,160 bytes (224,472 indented; computed 2026-10-08), and the
#: bound keeps a mistaken path to a large regular file from being read whole. A pipe, a device
#: or a directory is never read at all (`_kind`): opening a named pipe to read waits for a
#: writer, which no size bound reaches.
RECORD_LIMIT = 1024 * 1024


def _kind(mode: int) -> str:
    """What a file that is not a regular file is, in words, for the refusal."""
    for test, said in (
        (stat.S_ISFIFO, "a named pipe"),
        (stat.S_ISDIR, "a directory"),
        (stat.S_ISCHR, "a character device"),
        (stat.S_ISBLK, "a block device"),
        (stat.S_ISSOCK, "a socket"),
    ):
        if test(mode):
            return said
    return "a special file"


def read_calibration(path) -> Calibration:
    """A measured calibration from its record (engine spec §12.6: "records committed per rig
    under docs/measurements/<rig>/, each with an id"). **Fills in nothing**: a missing field,
    a field a record does not have or gives twice, or a value that is not what its field holds
    raises `ValueError` naming it, as does a file over `RECORD_LIMIT` or nested too deep to
    parse; a file that cannot be read raises `OSError`. Reading it runs no code, unlike the
    rig's and the animal's Python files. Its one optional field, `spectra` (engine build A2), is
    read when given and never filled in when not.

    **Only a regular file is read** (the engine B final review): anything else -- a named
    pipe, a directory, a device -- raises `ValueError` saying what it is, before a byte is
    read. Opened without waiting (`O_NONBLOCK`) and asked through that descriptor, so a named
    pipe with no writer never holds `wlx taskd` at its start, and the file checked is the file
    read. Like every refusal here it leaves the path to its caller, which names it
    (`cli._load_calibration`)."""
    descriptor = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
    try:
        mode = os.fstat(descriptor).st_mode
        if not stat.S_ISREG(mode):
            raise ValueError(
                f"it is {_kind(mode)}, not a regular file, so it was not read; a calibration "
                f"record is a JSON file"
            )
        file = os.fdopen(descriptor, "rb")
    except BaseException:
        os.close(descriptor)
        raise
    with file:
        raw = file.read(RECORD_LIMIT + 1)
    if len(raw) > RECORD_LIMIT:
        raise ValueError(
            f"it is larger than {RECORD_LIMIT} bytes (1 MiB), which no calibration record needs"
        )
    try:
        data = json.loads(raw.decode("utf-8"), object_pairs_hook=_once_each)
    except (json.JSONDecodeError, RecursionError) as error:
        raise ValueError(f"it is not JSON ({error})") from error
    if not isinstance(data, dict):
        raise ValueError("a calibration record is one JSON object")
    missing = [name for name in RECORD_FIELDS if name not in data]
    if missing:
        raise ValueError(f"it has no {', '.join(missing)}")
    extra = sorted(set(data) - set(RECORD_FIELDS) - set(RECORD_OPTIONAL))
    if extra:
        raise ValueError(f"it has {', '.join(extra)}, which a calibration record does not")
    for name in ("id", "measured_on", "observer"):
        if not isinstance(data[name], str):
            raise ValueError(f"its {name} is text")
    if not data["id"].strip():
        raise ValueError("its id is empty")
    if len(data["id"]) > ID_LIMIT:
        raise ValueError(f"its id is at most {ID_LIMIT} characters, and this one is {len(data['id'])}")
    # The terminal, the page and every frame quote the id: a control character or a stray
    # space there garbles or misleads.
    if data["id"] != data["id"].strip():
        raise ValueError(f"its id {data['id']!r} begins or ends with whitespace")
    if not data["id"].isprintable():
        raise ValueError(f"its id {data['id']!r} holds a character that does not print")
    primaries = _channels(data["primaries"], "primaries")
    transfer = _channels(data["transfer"], "transfer")
    return Calibration(
        red=_light(primaries["red"], "red primary"),
        green=_light(primaries["green"], "green primary"),
        blue=_light(primaries["blue"], "blue primary"),
        background=_light(data["background"], "background"),
        transfer=tuple(_table(transfer[c], f"{c} transfer") for c in _CHANNELS),
        observer=data["observer"],
        measured_on=data["measured_on"],
        id=data["id"],
        spectra=_spectra(data["spectra"]) if "spectra" in data else None,
    )


def _spectra(value: object) -> Spectra:
    """A record's `spectra`: `nm`, `red`, `green` and `blue`, each once, each a list of numbers,
    held to what `Spectra` holds them to."""
    names = ("nm", *_CHANNELS)
    if not isinstance(value, dict) or sorted(value) != sorted(names):
        raise ValueError("its spectra name nm, red, green and blue, each once")
    for name in names:
        if not (isinstance(value[name], list) and all(_finite_number(v) for v in value[name])):
            raise ValueError(f"its spectra's {name} is a list of numbers")
    try:
        return Spectra(**{name: tuple(float(v) for v in value[name]) for name in names})
    except ValueError as refused:
        raise ValueError(f"its spectra: {refused}") from refused


def _once_each(pairs: list) -> dict:
    """A JSON object whose every name is given once, at every level: otherwise the last of two
    `"id"`s or two `"red"`s would silently win."""
    named: dict = {}
    for name, value in pairs:
        if name in named:
            raise ValueError(f"it gives {name!r} twice, and a record gives each name once")
        named[name] = value
    return named


def _channels(value: object, what: str) -> dict:
    if not isinstance(value, dict) or sorted(value) != sorted(_CHANNELS):
        raise ValueError(f"its {what} name red, green and blue, each once")
    return value


def _light(value: object, what: str) -> xyY:
    if not (isinstance(value, list) and len(value) == 3 and all(_finite_number(v) for v in value)):
        raise ValueError(f"its {what} is three numbers, x, y and Y")
    return xyY(*(float(v) for v in value))


def _table(value: object, what: str) -> Transfer:
    if not (isinstance(value, list) and all(isinstance(p, list) and len(p) == 2 for p in value)):
        raise ValueError(f"its {what} is a list of [level, fraction] pairs")
    try:
        return Transfer(levels=tuple(p[0] for p in value), fractions=tuple(p[1] for p in value))
    except ValueError as refused:
        raise ValueError(f"its {what}: {refused}") from refused


#: The highest output code of a 10-bit output (spec §7.8: "Output is 10-bit").
TEN_BIT = 1023


def _srgb_fraction(level: float) -> float:
    """The sRGB standard's transfer, from output level to linear light. **The 0.04045
    threshold is IEC 61966-2-1's as commonly quoted; the IEC standard itself was not opened,
    so it is UNVERIFIED.** W3C's "A Standard Default Color Space for the Internet - sRGB",
    version 1.10 (https://www.w3.org/Graphics/Color/sRGB.html, read 2026-10-08), uses 0.03928
    (its equations 1.7a-b, printed as images), and its own note says the IEC standard
    corrected "a small numerical error caused by rounding error"; between the two thresholds
    the two branches differ by under 1e-6 of full scale (computed 2026-10-08)."""
    return level / 12.92 if level <= 0.04045 else ((level + 0.055) / 1.055) ** 2.4


#: The sRGB curve at each 10-bit level: the default calibration's transfer, every channel.
SRGB_TRANSFER = Transfer(
    levels=tuple(code / TEN_BIT for code in range(TEN_BIT + 1)),
    fractions=tuple(_srgb_fraction(code / TEN_BIT) for code in range(TEN_BIT + 1)),
)

#: The default calibration's white, cd/m²: the sRGB standard's reference luminance level
#: (W3C sRGB version 1.10, Table 0.1, "80 cd/m2", read 2026-10-08). The PI's answer to
#: Question 1 of the engine B plan.
SRGB_WHITE_CD_M2 = 80.0


def _srgb_primaries(white: float) -> tuple[xyY, xyY, xyY]:
    """The sRGB primaries' chromaticities, each at the luminance that makes full drive on all
    three the standard's D65 white at `white` cd/m² -- **solved, not the rounded 0.2126,
    0.7152 and 0.0722**, whose white misses D65 by 2e-4 and would be refused as out of gamut
    by `TOLERANCE` (computed 2026-10-08)."""
    chromaticities = ((0.64, 0.33), (0.30, 0.60), (0.15, 0.06))
    unit = [_XYZ(xyY(x, y, 1.0)) for x, y in chromaticities]
    luminances = _solve3(unit, _XYZ(xyY(D65[0], D65[1], white)))
    return tuple(xyY(x, y, Y) for (x, y), Y in zip(chromaticities, luminances))


_RED, _GREEN, _BLUE = _srgb_primaries(SRGB_WHITE_CD_M2)

#: **The default calibration** (engine spec §7.1; the PI, N§4 batch 1: "Standard sRGB"): the
#: panel in its sRGB mode, and the published standard's primaries and D65 white (W3C sRGB
#: version 1.10, Table 0.2, read 2026-10-08) and its transfer curve (`_srgb_fraction`).
#: How closely the panel follows it is UNVERIFIED until measured, and the warnings list says
#: so. Its background is black, the default background (spec §7.5).
SRGB = Calibration(
    red=_RED,
    green=_GREEN,
    blue=_BLUE,
    background=xyY(D65[0], D65[1], 0.0),
    transfer=(SRGB_TRANSFER,) * 3,
    observer="CIE 1931 2° (the sRGB standard's)",
    measured_on="",
    id="srgb-standard",
    standard=True,
)
