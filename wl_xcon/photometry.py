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
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path


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
    """

    lum: float = 0.0
    l_m: float = 0.0
    s_lm: float = 0.0

    def magnitude(self) -> float:
        return max(abs(self.lum), abs(self.l_m), abs(self.s_lm))


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
    the background and converts through cone fundamentals (engine build A2). A `Gray`
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
        f"it converts through cone fundamentals (engine build A2)"
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
    output levels through it is build A2's (`exact.py`'s docstring)."""

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
        if fractions[0] < 0.0 or fractions[-1] != 1.0:
            raise ValueError(
                f"a transfer's fractions start at 0 or above and end at 1, full drive; this one "
                f"runs from {fractions[0]} to {fractions[-1]}"
            )


_ISO_DAY = re.compile(r"\d{4}-\d{2}-\d{2}")


@dataclass(frozen=True, slots=True)
class Calibration:
    """A display, as measured. Every field is an observation, not a setting.

    `observer` names whose luminous efficiency the luminances were measured against,
    because that is what makes `lum=0` mean anything: photometric luminance is
    defined by a V(lambda), and using a human one for a macaque produces a stimulus
    that is isoluminant for nobody in the room.

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
    #: The largest cone contrast this panel reaches on its weakest axis, measured; `None` when
    #: a calibration states none, and then no DKL color is realizable against it until build
    #: A2 converts DKL through cone fundamentals (spec §7.4).
    max_cone_contrast: float | None = 0.85

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
        if self.standard:
            return
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
        columns = [_XYZ(p) for p in (self.red, self.green, self.blue)]
        return _solve3(columns, _XYZ(color))


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


def unrealizable(color: Color, panel: Calibration) -> str | None:
    """Why `panel` cannot produce `color`, or `None` if it can."""
    if isinstance(color, xyY):
        try:
            weights = panel.weights(color)
        except ValueError as exc:
            return str(exc)
        if any(w < -TOLERANCE or w > 1.0 + TOLERANCE for w in weights):
            return (
                f"needs primary weights {tuple(round(w, 3) for w in weights)}, "
                f"which are outside [0, 1]; the panel would clip, and a clipped "
                f"colour is neither the requested chromaticity nor the requested "
                f"luminance"
            )
        return None
    if isinstance(color, DKL):
        if panel.max_cone_contrast is None:
            return (
                "this calibration states no cone-contrast limit, so whether the panel can make "
                "it is unknown until build A2 converts DKL through cone fundamentals"
            )
        if color.magnitude() > panel.max_cone_contrast + TOLERANCE:
            return (
                f"asks for cone contrast {color.magnitude():.3f}; this panel was "
                f"measured to reach {panel.max_cone_contrast:.3f}"
            )
        return None
    return None


#: A calibration record's fields, each required and no other (Question 4: one JSON file per
#: measured calibration). `max_cone_contrast` alone is optional, until build A2 replaces it.
RECORD_FIELDS = ("id", "measured_on", "observer", "primaries", "background", "transfer")
_CHANNELS = ("red", "green", "blue")

#: The longest id a record may carry: the rig file, `config.json`, every run's start row and
#: every frame name it, and the calibration-age warning quotes it in a sentence the page's
#: open sends back (`link.NOTE_LIMIT`, Call 25), so it is bounded where it is read.
ID_LIMIT = 64

#: The largest record file read, in bytes: 1 MiB. A record holding the sRGB table at all 1024
#: levels on each channel is 132,160 bytes (224,472 indented; computed 2026-10-08), and the
#: bound keeps a mistaken path, a pipe or a device from being read without end.
RECORD_LIMIT = 1024 * 1024


def read_calibration(path) -> Calibration:
    """A measured calibration from its record (engine spec §12.6: "records committed per rig
    under docs/measurements/<rig>/, each with an id"). **Fills in nothing**: a missing field,
    a field a record does not have or gives twice, or a value that is not what its field holds
    raises `ValueError` naming it, as does a file over `RECORD_LIMIT` or nested too deep to
    parse; a file that cannot be read raises `OSError`. Reading it runs no code, unlike the
    rig's and the animal's Python files."""
    with Path(path).open("rb") as file:
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
    extra = sorted(set(data) - set(RECORD_FIELDS) - {"max_cone_contrast"})
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
    limit = data.get("max_cone_contrast")
    if limit is not None and not (_finite_number(limit) and limit > 0):
        raise ValueError("its max_cone_contrast is a positive number")
    return Calibration(
        red=_light(primaries["red"], "red primary"),
        green=_light(primaries["green"], "green primary"),
        blue=_light(primaries["blue"], "blue primary"),
        background=_light(data["background"], "background"),
        transfer=tuple(_table(transfer[c], f"{c} transfer") for c in _CHANNELS),
        observer=data["observer"],
        measured_on=data["measured_on"],
        id=data["id"],
        max_cone_contrast=None if limit is None else float(limit),
    )


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
    max_cone_contrast=None,
)
