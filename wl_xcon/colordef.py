"""**A new color, defined from the console three ways, and written as a set's proposed file**
(the console settings design's §6; its plan's Task 8; the PI, 2026-11-16: "1,2,or 3. you select an
option and then enter the info", and "Saved into a color set file"; for this plan "Proposed file
first").

`chromaticity` gives a new color's CIE 1931 xy by one of `METHODS`, in a color set's frame:

- **`hue_angle`** (`hue_deg`): in the set's design frame (`photometry.ColorSet.design`), as the
  PI's generator makes a sector (wl-style's `isohue.py`, `reference_gray` and `colors(t, s)`). The
  gray is the light of the set's apex whose macaque luminance (`photometry.SRGB_MACAQUE`) equals that
  of CAM16's achromatic point at the design's `gray_lightness`; the color's a'b' is the gray's plus
  the design's chroma at angle h about it; and its J' is bisected until its macaque luminance equals
  the gray's (`cam16`). Refused for a set with no design.
- **`dkl`** (`azimuth_deg`, `elevation_deg`, and `contrast`, which defaults to the mean DKL radius of
  the set's colors): a DKL direction about the set's gray, its apex at the set's luminance, in the
  set's own observer -- the CIE's 2° fundamentals (`cones.LMS_TO_XYZ_F2`), never the lab's 10° one
  -- on the sRGB standard, with DKL's axes built as COL-32 builds them (`photometry.cone_contrast`)
  and the luminance axis the set's, L + M at L:M 1 (`cones.MACAQUE_LM`).
- **`xy`** (`x`, `y`): as given, by `photometry._chromaticity`'s rule.

In each, the set then holds its luminance, as it holds every color's: a set's file writes a
chromaticity alone. **A definition is the same on every rig**: it is made on the sRGB standard, never
on a panel, and how a rig's panel shows the set with it is a warning when it is saved
(`service.Service._define_color`).

`proposal` gives the set's whole file with the color added, for the PI to review and commit
(wl-xtasks is curated with him): it is written under `stimuli/proposed/`, never over the set's own
file, since a file in the checkout is read at the next load whether committed or not (XC-150's pull
is not built), and a rig would otherwise use a color nobody reviewed (the planner's call, COL-38).
Between commands, never in a frame.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from importlib import metadata

from wl_xcon import cam16, cones
from wl_xcon.photometry import (
    DESIGN_SPACE,
    MACAQUE_2DEG_LM1,
    SRGB,
    SRGB_MACAQUE,
    ColorSet,
    _apply3,
    _chromaticity,
    _design,
    _held_light,
    _inverse3,
    srgb_hex,
)

#: The three ways a new color is defined, in the order the panel offers them (the PI, 2026-11-16).
METHODS = ("hue_angle", "dkl", "xy")
#: **The numbers each method takes**, required.
NUMBERS = {"hue_angle": ("hue_deg",), "dkl": ("azimuth_deg", "elevation_deg"), "xy": ("x", "y")}
#: And those it may take: a DKL color's distance from the gray.
OPTIONAL = {"hue_angle": (), "dkl": ("contrast",), "xy": ()}
#: **The numbers that make a new set's design frame** (`ColorSet.design`), taken with its first
#: color by hue angle; a set that has a frame keeps its file's.
FRAMING = ("gray_lightness", "chroma")
#: How the panel says each method.
SAID = {"hue_angle": "hue angle (CAM16-UCS)", "dkl": "DKL direction", "xy": "CIE x, y"}

#: **The longest name a new color takes**, in characters: a swatch's label on the card, not a rule
#: about color names (the plan's Task 8).
NAME_LIMIT = 40
#: **The places each chromaticity is written to**: the set files' own (wl-xtasks' `isohue.json`), a
#: step of 1e-5 in xy, far under what any panel resolves; the preview gives the same numbers, so what
#: it shows is what is saved.
PLACES = 5

#: **A new set's apex**, the sRGB standard's white as colour-science writes it (its four-place sRGB
#: matrix), as wl-xtasks' `isohue.json` writes its gray, and its luminance at full, cd/m² of macaque
#: luminance, isohue's 15 (the PI, 2026-11-07, COL-37).
NEW_APEX = (0.31272, 0.32900)
NEW_LUMINANCE = 15.0

#: **How much more a set must give up with a new color before saving it warns**: 1e-6 of its
#: distance from the apex, a thousand of `photometry.DESATURATION_STEP`s, the bisection's own last
#: width, so a set's share found again to that width is never read as a change.
DESATURATED = 1e-6

#: The bisection's bounds and count for a hue angle's lightness: the generator's own [1, 99]
#: (`isohue.py`'s `solve_J`), halved until far under 1e-9 in J'.
_J_LOW, _J_HIGH, _HALVINGS = 1.0, 99.0, 60


def _to_lms2(xyz) -> tuple[float, float, float]:
    """CIE 1931 XYZ to the 2° cone excitations, by the CIE's 2° LMS-to-XYZ_F matrix inverted
    (`cones.LMS_TO_XYZ_F2`), as COL-18 converts on the sRGB standard."""
    return _apply3(_inverse3(cones.LMS_TO_XYZ_F2), xyz)


@dataclass(frozen=True, slots=True)
class Frame:
    """**What a new color is defined in**: a set's name, apex, luminance at full, design frame
    (`ColorSet.design`, or `None`) and its colors by name -- a set read from its file (`frame`), one
    a telemetry frame describes (`ParamRow.color`'s `sets`), or a new set's (`new_set`), which has
    none yet."""

    name: str
    apex: tuple[float, float]
    luminance_cd_m2: float = NEW_LUMINANCE
    design: dict | None = None
    colors: dict = field(default_factory=dict)
    source: str = ""


def frame(colorset: "ColorSet | Frame") -> Frame:
    """A color set's `Frame`."""
    if isinstance(colorset, Frame):
        return colorset
    if not isinstance(colorset, ColorSet):
        raise ValueError(f"a new color is defined in a color set, not {colorset!r}")
    return Frame(name=colorset.name, apex=colorset.apex, luminance_cd_m2=colorset.luminance_cd_m2,
                 design=None if colorset.design is None else dict(colorset.design),
                 colors=dict(colorset.colors), source=colorset.source)


def new_set(name: str, method: str, numbers) -> Frame:
    """**A new set's frame**: `NEW_APEX`, `NEW_LUMINANCE` and macaque luminance held, and, where its
    first color is by hue angle, the design frame its numbers give (`FRAMING`). Refused for a name no
    set's file can have: 1 to `NAME_LIMIT` letters, digits, `-` or `_`, a letter or digit first,
    since it names the file (`<name>.json`)."""
    name = set_name(name)
    design = None
    if method == "hue_angle":
        missing = [key for key in FRAMING if key not in numbers]
        if missing:
            raise ValueError(
                f"a new set's first color by hue angle makes the set's design frame, so it names "
                f"{' and '.join(FRAMING)} too, and this has no {', '.join(missing)}"
            )
        design = _design({"space": DESIGN_SPACE, "gray_lightness": numbers["gray_lightness"],
                          "chroma": numbers["chroma"]}, name)
    return Frame(name=name, apex=NEW_APEX, luminance_cd_m2=NEW_LUMINANCE, design=design)


def set_name(name: object) -> str:
    """A set's name as a file names it: 1 to `NAME_LIMIT` ASCII letters, digits, `-` or `_`, a
    letter or digit first; refused otherwise, since it becomes a path."""
    if not (isinstance(name, str) and 0 < len(name) <= NAME_LIMIT and name.isascii()
            and (name[0].isalnum()) and all(c.isalnum() or c in "-_" for c in name)):
        raise ValueError(
            f"a color set is named by 1 to {NAME_LIMIT} letters, digits, '-' or '_', a letter or "
            f"digit first, since its name is its file's; {name!r} is not one"
        )
    return name


def color_name(name: object, within: Frame) -> str:
    """**A new color's name**: printable text, 1 to `NAME_LIMIT` characters, not blank, and none the
    set has already -- a set's color is never redefined from the panel (the plan's Task 8)."""
    if not (isinstance(name, str) and name.strip() and name.isprintable()
            and len(name) <= NAME_LIMIT):
        raise ValueError(
            f"a new color is named by printable text of 1 to {NAME_LIMIT} characters, and "
            f"{name!r} is not that"
        )
    if name in within.colors:
        raise ValueError(
            f"color set {within.name!r} already has a color {name!r}; a set's color is never "
            f"redefined from the panel, so name the new one otherwise"
        )
    return name


def _numbers(within: Frame, method: str, numbers) -> dict[str, float]:
    if method not in METHODS:
        raise ValueError(f"a new color is defined by {', '.join(METHODS)}, and {method!r} is none "
                         f"of them")
    if not isinstance(numbers, dict):
        raise ValueError(f"a new color's numbers are named numbers, not {numbers!r}")
    framing = FRAMING if method == "hue_angle" else ()
    allowed = (*NUMBERS[method], *OPTIONAL[method], *framing)
    extra = sorted(set(numbers) - set(allowed))
    if extra:
        raise ValueError(f"a new color by {SAID[method]} takes {', '.join(allowed)}, not "
                         f"{', '.join(extra)}")
    missing = [key for key in NUMBERS[method] if key not in numbers]
    if missing:
        raise ValueError(f"a new color by {SAID[method]} names {', '.join(NUMBERS[method])}, and "
                         f"this has no {', '.join(missing)}")
    checked = {}
    for key, value in numbers.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f"a new color's {key} is {value!r}, not a finite number")
        checked[key] = float(value)
    given = [key for key in FRAMING if key in checked]
    if given and (within.design is None or any(
            checked[key] != within.design[key] for key in given)):
        raise ValueError(
            f"color set {within.name!r}'s design frame is its file's, so a hue angle into it names "
            f"hue_deg alone; {' and '.join(FRAMING)} make a new set's frame"
        )
    return checked


def chromaticity(colorset: "ColorSet | Frame", method: str, numbers) -> tuple[float, float]:
    """**A new color's CIE 1931 (x, y)** by `method`, its `numbers` in `colorset`'s frame (the
    module's docstring). Raises `ValueError`, a sentence saying why, for a method, a number or a
    frame that defines none."""
    within = frame(colorset)
    numbers = _numbers(within, method, numbers)
    if method == "xy":
        return _chromaticity((numbers["x"], numbers["y"]), "a new color's x, y")
    if method == "hue_angle":
        return _hue_angle(within, numbers["hue_deg"])
    return _dkl(within, numbers["azimuth_deg"], numbers["elevation_deg"], numbers.get("contrast"))


def _macaque(xyz) -> float:
    return sum(r * v for r, v in zip(SRGB_MACAQUE, xyz))


def _xy(xyz) -> tuple[float, float]:
    total = xyz[0] + xyz[1] + xyz[2]
    if not total > 0.0:
        raise ValueError("it is no light: its tristimulus values sum to nothing")
    return (xyz[0] / total, xyz[1] / total)


def gray_ucs(within: Frame) -> tuple[tuple[float, float, float], float]:
    """**The design frame's gray**, as wl-style's `reference_gray` finds it: the light of the
    set's apex chromaticity whose macaque luminance equals that of CAM16's achromatic point (a' = b'
    = 0) at the design's `gray_lightness`, relative to a white of Y 1; returned as its CAM16-UCS
    J'a'b' and that macaque luminance, the one every hue is matched to."""
    if within.design is None:
        raise ValueError(
            f"color set {within.name!r} has no design: a hue angle is defined in a set's CAM16-UCS "
            f"design frame, which its file does not give, so define this color by DKL direction or "
            f"by x, y"
        )
    target = _macaque(cam16.from_ucs((within.design["gray_lightness"], 0.0, 0.0)))
    x, y = within.apex
    unit = (x / y, 1.0, (1.0 - x - y) / y)
    scale = target / _macaque(unit)
    return cam16.to_ucs(tuple(scale * u for u in unit)), target


def _hue_angle(within: Frame, hue_deg: float) -> tuple[float, float]:
    (_, a0, b0), target = gray_ucs(within)
    chroma = within.design["chroma"]
    h = math.radians(hue_deg)
    a, b = a0 + chroma * math.cos(h), b0 + chroma * math.sin(h)

    def luminance(J: float) -> float:
        return _macaque(cam16.from_ucs((J, a, b)))

    low, high = _J_LOW, _J_HIGH
    if not luminance(low) <= target <= luminance(high):
        raise ValueError(
            f"no CAM16-UCS lightness from {_J_LOW:g} to {_J_HIGH:g} gives hue {hue_deg:g}° at "
            f"chroma {chroma:g} in color set {within.name!r} its gray's macaque luminance, so it "
            f"defines no color of the set"
        )
    for _ in range(_HALVINGS):
        middle = (low + high) / 2.0
        low, high = (middle, high) if luminance(middle) < target else (low, middle)
    return _xy(cam16.from_ucs(((low + high) / 2.0, a, b)))


def _gray_cones(within: Frame) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    """The set's gray on the sRGB standard, CIE XYZ in cd/m², and its 2° cone excitations."""
    gray = _held_light(within.apex, within.luminance_cd_m2, SRGB)
    return gray, _to_lms2(gray)


def _axes(excited) -> tuple[float, float]:
    """COL-32's `l_m` direction at the set's luminance, L + M at L:M 1 (`cones.MACAQUE_LM`): its
    isoluminant ratio, and the norm that makes it unit pooled cone contrast."""
    weight_l, weight_m = (w * e for w, e in zip(cones.MACAQUE_LM, excited[:2]))
    ratio = weight_l / weight_m
    return ratio, math.sqrt(1.0 + ratio * ratio)


def dkl_of(within: Frame, xy) -> tuple[float, float]:
    """**A chromaticity's place in the set's DKL isoluminant plane**, `(l_m, s_lm)` about its gray:
    its light scaled to the gray's L + M (L:M 1) in the set's 2° observer on the sRGB standard, so
    its `lum` is 0, as every color of a set is isoluminant with the others; then `l_m` and `s_lm` as
    `photometry.cone_contrast` builds them (COL-32), inverted. A chromaticity alone, as a set's file
    writes one: the luminance the set holds it at does not move it."""
    gray, excited = _gray_cones(within)
    x, y = (float(v) for v in xy)
    cones_ = _to_lms2((x / y, 1.0, (1.0 - x - y) / y))
    weights = tuple(w for w in cones.MACAQUE_LM)
    scale = ((weights[0] * excited[0] + weights[1] * excited[1])
             / (weights[0] * cones_[0] + weights[1] * cones_[1]))
    c = [scale * v / e - 1.0 for v, e in zip(cones_, excited)]
    _, norm = _axes(excited)
    return (c[0] * norm, c[2])


def mean_radius(within: Frame) -> float:
    """**The mean DKL radius of the set's colors** about its gray, in its isoluminant plane
    (`dkl_of`): a DKL color's
    contrast where none is given (the planner's call: the design names a direction alone, and a
    color needs a distance). Refused for a set with no colors yet."""
    if not within.colors:
        raise ValueError(
            f"color set {within.name!r} has no colors yet, so a DKL color into it names its "
            f"contrast, its distance from the gray"
        )
    radii = [math.hypot(*dkl_of(within, xy)) for xy in within.colors.values()]
    return sum(radii) / len(radii)


def _dkl(within: Frame, azimuth_deg: float, elevation_deg: float,
         contrast: float | None) -> tuple[float, float]:
    if not -90.0 <= elevation_deg <= 90.0:
        raise ValueError(f"a DKL elevation is from -90° to 90°, and {elevation_deg:g}° is not")
    if contrast is None:
        contrast = mean_radius(within)
    if not contrast > 0.0:
        raise ValueError(f"a DKL color's contrast is its distance from the gray, above 0, and "
                         f"{contrast:g} is not")
    gray, excited = _gray_cones(within)
    az, el = math.radians(azimuth_deg), math.radians(elevation_deg)
    lum = contrast * math.sin(el)
    l_m = contrast * math.cos(el) * math.cos(az)
    s_lm = contrast * math.cos(el) * math.sin(az)
    ratio, norm = _axes(excited)
    moved = (lum + l_m / norm, lum - l_m * ratio / norm, lum + s_lm)
    xyz = _apply3(cones.LMS_TO_XYZ_F2, tuple(e * (1.0 + c) for e, c in zip(excited, moved)))
    if not all(v >= 0.0 for v in xyz) or not xyz[1] > 0.0:
        raise ValueError(
            f"a DKL color at contrast {contrast:g} toward azimuth {azimuth_deg:g}°, elevation "
            f"{elevation_deg:g}° about color set {within.name!r}'s gray is no light: it asks for "
            f"CIE XYZ ({xyz[0]:.3g}, {xyz[1]:.3g}, {xyz[2]:.3g}) cd/m², a tristimulus value below "
            f"nothing; a smaller contrast reaches a light"
        )
    return _chromaticity(_xy(xyz), "a DKL color")


def written(xy) -> tuple[float, float]:
    """A chromaticity as a set's file writes it, to `PLACES` places."""
    return (round(float(xy[0]), PLACES), round(float(xy[1]), PLACES))


def swatch(within: Frame, xy) -> tuple[str, bool]:
    """**How the sRGB standard shows a chromaticity at the set's luminance**: its `#rrggbb`
    (`photometry.srgb_hex`) and whether it is inside the standard's gamut there, within
    `photometry.TOLERANCE`. Approximate on any panel not measured, as the color card says."""
    from wl_xcon.photometry import TOLERANCE

    light = _held_light(tuple(xy), within.luminance_cd_m2, SRGB)
    weights = SRGB.weights_of(light)
    return srgb_hex(light), all(-TOLERANCE <= w <= 1.0 + TOLERANCE for w in weights)


def numbers_words(method: str, numbers) -> str:
    """A definition's numbers as a source sentence says them, in its method's order."""
    order = (*NUMBERS[method], *OPTIONAL[method], *(FRAMING if method == "hue_angle" else ()))
    return ", ".join(f"{key} {numbers[key]:g}" for key in order if key in numbers)


def version() -> str:
    """This package's version as installed, or `"unknown"` where it is run from a tree that is
    not."""
    try:
        return metadata.version("wl-xcon")
    except metadata.PackageNotFoundError:
        return "unknown"


def proposal(colorset: "ColorSet | Frame", name: str, xy, *, method: str, numbers, by,
             rig: str, on: str) -> dict:
    """**The set's whole file with the color added**, as JSON data for `stimuli/proposed/`: its
    fields as `ColorSet.load` reads them, its colors as they were and the new one after them at
    `written(xy)`, its `design` where it has one, and its `source` extended by one sentence:
    `<name>: <method> (<numbers>), defined on <rig> by <who> on <date> (wl-xcon <version>), proposed
    for review.` A name the set has, or one not printable or over `NAME_LIMIT` characters, is
    refused (`color_name`)."""
    within = frame(colorset)
    name = color_name(name, within)
    if method not in METHODS:
        raise ValueError(f"a new color is defined by {', '.join(METHODS)}, not {method!r}")
    x, y = written(_chromaticity(tuple(xy), f"new color {name!r}"))
    said = (f"{name}: {method} ({numbers_words(method, numbers)}), defined on {rig} by {by} on "
            f"{on} (wl-xcon {version()}), proposed for review.")
    data = {
        "name": within.name,
        "colors": {**{color: list(at) for color, at in within.colors.items()}, name: [x, y]},
        "apex": list(within.apex),
        "luminance_cd_m2": within.luminance_cd_m2,
        "held": MACAQUE_2DEG_LM1,
        "source": f"{within.source} {said}" if within.source else said,
    }
    if within.design is not None:
        data["design"] = dict(within.design)
    return data
