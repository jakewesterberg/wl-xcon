"""The screen description: everything on the animal's screen, resolved to numbers
(engine spec §3.3; build A1).

`resolve` is the one place a task's declarations become something to draw: parameters
bound, named kinds expanded into `look` blocks, an `Array` into its items, each eye's
direction computed (disparity, then the vergence offset), colors turned into CIE XYZ, a cone
color against the background through the session's calibration (engine build A2).
Its consumers -- the exact drawer now; the display process (build E), the screen log
(build F), the simulated animal (build C) and demo mode later -- read the `Screen` and
nothing else. It is versioned like telemetry: `SCHEMA`, which the display process's
reader (build E) checks; nothing reads a `Screen` across a process boundary before it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, fields, replace

from wl_xcon import look
from wl_xcon.photometry import CONE_COLORS, D65, Gray, Michelson, Weber, cone_xyz, to_xyz, xyY
from wl_xcon.task import (
    Annulus, Array, Bar, Blank, Cross, Disc, Gabor, Grating, P, Polygon, Square, _value,
)

SCHEMA = 1
_BLACK = (0.0, 0.0, 0.0)

#: The combinations that draw none of a stimulus's own light (engine spec §4.4): a window
#: shows what is below it only inside it, a scotoma hides it there. Its fill's light is
#: never read, so it may have none (the A1 follow-ups' call 3, XC-257); `check` holds it to
#: no light rule either.
LIGHTLESS = ("window", "scotoma")


class NotYetDrawable(ValueError):
    """Something a later build of the engine draws, named with that build."""


@dataclass(frozen=True, slots=True)
class ResolvedFlat:
    """A flat fill's light: absolute, or a contrast against the eye's background. Neither
    on a window or a scotoma (`LIGHTLESS`), which draws no light of its own."""

    #: An absolute light.
    xyz: tuple[float, float, float] | None
    #: Or a contrast against the eye's background.
    weber: float | None


@dataclass(frozen=True, slots=True)
class ResolvedGrating:
    """A sine grating with every parameter bound to a number, but for the light a window or a
    scotoma (`LIGHTLESS`) never draws: there `michelson` is `None`, and `mean_xyz` unread."""

    sf: float
    phase: float
    tf: float
    #: `None` on a window or a scotoma (`LIGHTLESS`), which draws no light of its own.
    michelson: float | None
    #: `None`: what is behind it; and on a window or a scotoma, unread.
    mean_xyz: tuple[float, float, float] | None


@dataclass(frozen=True, slots=True)
class ResolvedOutline:
    """An outline's width and light."""

    width: float
    xyz: tuple[float, float, float]


@dataclass(frozen=True, slots=True)
class Item:
    """One thing on the screen, every field a number."""

    #: `"<stimulus>"`, or `"<array>.<i>"` for an array's items.
    name: str
    #: (order shown, index within its array).
    order: tuple[int, int]
    layer: int
    combine: str
    opacity: float
    eye: str
    #: Each eye's own direction, degrees, after the vergence offset.
    at_left: tuple[float, float]
    at_right: tuple[float, float]
    orientation: float
    #: A `look.Shape`, every field a number.
    shape: object
    fill: ResolvedFlat | ResolvedGrating
    #: A `look.Edge`, every field a number, `applies` resolved.
    edge: object
    outline: ResolvedOutline | None
    onset_frame: int


@dataclass(frozen=True, slots=True)
class Screen:
    """Everything on the animal's screen at one frame."""

    setup: str
    periphery: str
    background_left: tuple[float, float, float]
    background_right: tuple[float, float, float]
    #: Sorted by (layer, order).
    items: tuple[Item, ...]
    frame: int
    frame_period: float
    schema: int = SCHEMA


def _num(value, values) -> float:
    return float(_value(value, values))


def _bind(block, values):
    """`block` with every parameter in it bound to a number."""
    changes = {}
    for f in fields(block):
        v = getattr(block, f.name)
        if isinstance(v, P):
            changes[f.name] = _num(v, values)
        elif isinstance(v, tuple):
            changes[f.name] = tuple(tuple(_num(c, values) for c in point) for point in v)
    return replace(block, **changes) if changes else block


#: What `_Lights` holds for its background when the two eyes' differ: a cone color has no one
#: background to be converted against there, and `check` refuses it at load.
_TWO_BACKGROUNDS = "the two eyes' backgrounds differ"


def _absolute(color, values) -> xyY | None:
    """An absolute light, its parameters bound, as `xyY`; `None` stays `None` (black). A cone
    color is not one: a background is what it is relative to, and `check` refuses one there."""
    if isinstance(color, P):
        color = _value(color, values)
    if color is None:
        return None
    if isinstance(color, Gray):
        return xyY(D65[0], D65[1], _num(color.cd_m2, values))
    if isinstance(color, xyY):
        return xyY(_num(color.x, values), _num(color.y, values), _num(color.Y, values))
    raise ValueError(f"a background is an absolute light, Gray or xyY, and {color} is not")


@dataclass(frozen=True, slots=True)
class _Lights:
    """How this trial's colors become CIE XYZ: an absolute one as itself, a cone color against
    the background both eyes share, through `calibration` (engine build A2)."""

    values: dict
    calibration: object
    #: The background both eyes see, as `xyY`; `None` for black; `_TWO_BACKGROUNDS` when the
    #: eyes' differ.
    background: object

    def xyz(self, color):
        """CIE XYZ of `color`, its parameters bound; `None` stays `None`."""
        values = self.values
        if isinstance(color, P):
            color = _value(color, values)
        if color is None:
            return None
        if isinstance(color, (Gray, xyY)):
            return to_xyz(_absolute(color, values))
        if isinstance(color, CONE_COLORS):
            if self.calibration is None:
                raise ValueError(f"{color} converts through a calibration, and none was given")
            if self.background == _TWO_BACKGROUNDS:
                raise ValueError(f"{color} is relative to the background, and {_TWO_BACKGROUNDS}")
            bound = type(color)(*(_num(getattr(color, f.name), values) for f in fields(color)))
            return cone_xyz(bound, self.calibration, self.background or xyY(*D65, 0.0))
        raise ValueError(f"{color!r} is not a color; `check` refuses it at load (bad-block)")


def _contrast(contrast, kind, values):
    """A contrast's value, in the convention `kind` its fill takes. A flat light takes a
    color or a Weber contrast in every build; a pattern's other conventions arrive with
    the pattern fills (engine build A3). The checker refuses both at load
    (`contrast-convention`)."""
    if isinstance(contrast, P):
        contrast = _value(contrast, values)
    if contrast is None:
        return None
    if type(contrast) is not kind:
        if kind is Weber:
            raise ValueError(
                f"a flat light takes a color or a Weber contrast, never "
                f"{type(contrast).__name__}, which describes a pattern about its mean"
            )
        raise NotYetDrawable(
            f"{type(contrast).__name__} contrast on a sine grating is drawn with the pattern "
            f"fills, in engine build A3; this build draws {kind.__name__}"
        )
    return _num(contrast.value, values)


def as_look(looks, values) -> look.Look:
    """A named kind expanded into blocks; a `Look` as it is.

    `Disc` is a circle, `Square` and `Bar` rectangles (a bar long along its orientation),
    `Cross` a cross, `Polygon` a regular polygon, `Annulus` a ring, each one flat light.
    `Gabor` is a sine grating in a Gaussian envelope cut at `look.GABOR_CUTOFF_SIGMAS`;
    `Grating` one in a hard circular aperture. Every other kind is a later build's.
    """
    if isinstance(looks, P):
        looks = _value(looks, values)
    if isinstance(looks, look.Look):
        return looks

    def flat(shape, orientation=0.0):
        return look.Look(shape=shape, fill=look.Flat(color=looks.color, contrast=looks.contrast),
                         orientation=orientation)

    if isinstance(looks, Disc):
        return flat(look.Circle(size=looks.size))
    if isinstance(looks, Square):
        return flat(look.Rect(width=looks.size, height=looks.size))
    if isinstance(looks, Bar):
        return flat(look.Rect(width=looks.length, height=looks.width), looks.orientation)
    if isinstance(looks, Cross):
        return flat(look.Cross(size=looks.size, thickness=looks.thickness))
    if isinstance(looks, Polygon):
        return flat(look.RegularPolygon(sides=looks.sides, size=looks.size), looks.orientation)
    if isinstance(looks, Annulus):
        return flat(look.Ring(inner=looks.inner, outer=looks.outer))
    if isinstance(looks, (Gabor, Grating)) and looks.color is not None:
        raise NotYetDrawable(
            "a named grating's color is drawn with the pattern fills, in engine build A3; a "
            "luminance grating about a colored mean is a Look with a SineGrating mean")
    if isinstance(looks, Gabor):
        sigma = _num(looks.sigma, values)
        return look.Look(
            shape=look.Circle(size=2 * look.GABOR_CUTOFF_SIGMAS * sigma),
            fill=look.SineGrating(sf=looks.sf, phase=looks.phase, contrast=looks.contrast),
            edge=look.GaussianEdge(sigma=sigma),
            orientation=looks.orientation,
        )
    if isinstance(looks, Grating):
        return look.Look(
            shape=look.Circle(size=looks.aperture),
            fill=look.SineGrating(sf=looks.sf, phase=looks.phase, contrast=looks.contrast),
            orientation=looks.orientation,
        )
    later = "A4" if type(looks).__name__ in ("Picture", "Movie") else "A3"
    raise NotYetDrawable(f"{type(looks).__name__} is drawn in engine build {later}")


def _drift(fill, values, orientation) -> float:
    """The drawer's signed speed: `fill.tf`, positive toward the bars' local +y (the
    orientation + 90 degrees), negative the other way. `direction` must be across the bars
    (spec §5.1; PI, 2026-10-07), and `check` refuses one that is not at load."""
    tf = _num(fill.tf, values)
    if tf < 0.0:
        raise ValueError(f"a grating's tf is a speed, never negative (got {tf:g}); "
                         f"`direction` says which way it drifts")
    if fill.direction is None:
        return tf
    direction = _num(fill.direction, values)
    turn = math.radians(direction - (orientation + 90.0))
    if abs(math.sin(turn)) > 1e-9:
        raise ValueError(f"a grating's drift direction {direction:g} degrees is not across the "
                         f"bars: with orientation {orientation:g} it is "
                         f"{orientation + 90.0:g} or {orientation + 270.0:g}")
    return tf if math.cos(turn) > 0.0 else -tf


def _fill(fill, lights, orientation=0.0, lit=True):
    """A fill with every parameter bound. `lit` is false on a window or a scotoma
    (`LIGHTLESS`), which draws none of its own light: there its light is not read, so it may
    have none, and a flat fill resolves to no light and a grating to its bars alone."""
    values = lights.values
    if isinstance(fill, look.Flat):
        if not lit:
            return ResolvedFlat(xyz=None, weber=None)
        resolved = ResolvedFlat(xyz=lights.xyz(fill.color),
                                weber=_contrast(fill.contrast, Weber, values))
        if resolved.xyz is None and resolved.weber is None:
            raise ValueError("a flat fill with neither a color nor a contrast has no light")
        return resolved
    if isinstance(fill, look.SineGrating):
        michelson = _contrast(fill.contrast, Michelson, values) if lit else None
        if lit and michelson is None:
            raise ValueError("a grating with no contrast is its mean alone")
        return ResolvedGrating(sf=_num(fill.sf, values), phase=_num(fill.phase, values),
                               tf=_drift(fill, values, orientation), michelson=michelson,
                               mean_xyz=lights.xyz(fill.mean) if lit else None)
    raise NotYetDrawable(f"{type(fill).__name__} is drawn in engine build A3")


def _position(value, values) -> tuple[float, float]:
    if isinstance(value, P):
        value = _value(value, values)
    return (_num(value[0], values), _num(value[1], values))


def _eyes(stimulus, values, geometry, offset):
    """Each eye's own direction, in degrees (engine spec §5.4): per-eye positions as
    given; otherwise the left eye at `x − d/2 + v` and the right at `x + d/2 − v`, `v`
    the vergence offset (zero in direct view)."""
    dx, dy = offset
    if stimulus.eye != "both" and geometry.view != "stereoscope":
        raise ValueError(f"{stimulus.name!r} is shown to the {stimulus.eye} eye only outside "
                         f"the stereoscope")
    if stimulus.at_left is not None:
        if geometry.view != "stereoscope":
            raise ValueError(f"{stimulus.name!r} has per-eye positions outside the stereoscope")
        (lx, ly), (rx, ry) = _position(stimulus.at_left, values), _position(stimulus.at_right, values)
        return (lx + dx, ly + dy), (rx + dx, ry + dy)
    x, y = _position(stimulus.at, values)
    d = _num(stimulus.disparity, values)
    if d and geometry.view != "stereoscope":
        raise ValueError(f"{stimulus.name!r} has a disparity outside the stereoscope")
    v = geometry.vergence_half_deg
    return (x + dx - d / 2 + v, y + dy), (x + dx + d / 2 - v, y + dy)


def _edge(edge, fill, lit, name):
    """An edge with `applies` resolved. Only a pattern that draws its own light has a
    contrast for the edge to shape; a flat light's edge fades its light, and a window's or
    a scotoma's, whatever its fill, shapes what shows through it (call 5: a Gabor-shaped
    window is a Gaussian aperture). `check` refuses `"contrast"` on either at load
    (`bad-block`); this is the backstop for input it never saw, as `_drift` is."""
    patterned = lit and isinstance(fill, ResolvedGrating)
    if edge.applies is None:
        return replace(edge, applies="contrast" if patterned else "opacity")
    if edge.applies == "contrast" and not patterned:
        what = "a flat light" if lit else "a window or a scotoma"
        raise ValueError(f"{name!r}'s edge applies to 'contrast', and {what} has no contrast of "
                         f"its own for it to shape; it applies to 'opacity'")
    return edge


def _item(stimulus, name, order, looks, offset, lights, geometry, onset) -> Item:
    values = lights.values
    expanded = as_look(looks, values)
    orientation = _num(expanded.orientation, values)
    lit = stimulus.combine not in LIGHTLESS
    fill = _fill(expanded.fill, lights, orientation, lit=lit)
    edge = _edge(_bind(expanded.edge, values), fill, lit, name)
    outline = None
    if expanded.outline is not None:
        outline = ResolvedOutline(width=_num(expanded.outline.width, values),
                                  xyz=lights.xyz(expanded.outline.color))
        if outline.xyz is None:
            raise ValueError(f"{name!r}'s outline has no light; an outline is drawn in a color")
    at_left, at_right = _eyes(stimulus, values, geometry, offset)
    return Item(
        name=name, order=order, layer=stimulus.layer, combine=stimulus.combine,
        opacity=_num(stimulus.opacity, values), eye=stimulus.eye,
        at_left=at_left, at_right=at_right,
        orientation=orientation,
        shape=_bind(expanded.shape, values), fill=fill, edge=edge, outline=outline,
        onset_frame=onset,
    )


def _items(stimulus, order, lights, geometry, onset) -> list[Item]:
    values = lights.values
    looks = _value(stimulus.looks, values) if isinstance(stimulus.looks, P) else stimulus.looks
    if isinstance(looks, Blank):
        return []
    if isinstance(looks, Array):
        return [
            _item(stimulus, f"{stimulus.name}.{i}", (order, i), looks.item_looks(i, values),
                  offset, lights, geometry, onset)
            for i, offset in enumerate(looks.positions(values))
        ]
    return [_item(stimulus, stimulus.name, (order, 0), looks, (0.0, 0.0), lights, geometry, onset)]


def resolve(visible, values, trial, geometry, *, frame_period, frame=0, onsets=None,
            calibration=None) -> Screen:
    """The screen as `visible` and `values` make it at `frame`. `visible` keeps the order
    stimuli were shown (the trial loop's `dict`), which breaks ties within a layer;
    `onsets` gives each stimulus's first frame, from which drift is timed. **A cone color
    (`DKL`, `ConeContrast`) converts against the background through `calibration`** (engine
    build A2), so a trial with one needs it; the screen description itself stays CIE XYZ."""
    base = _absolute(trial.background, values)
    left = _absolute(trial.background_left, values) or base
    right = _absolute(trial.background_right, values) or base
    shared = left if left == right else _TWO_BACKGROUNDS
    lights = _Lights(values=values, calibration=calibration, background=shared)
    items: list[Item] = []
    for order, stimulus in enumerate(visible.values()):
        items.extend(_items(stimulus, order, lights, geometry, (onsets or {}).get(stimulus.name, 0)))
    items.sort(key=lambda i: (i.layer, i.order))
    return Screen(setup=geometry.view, periphery=trial.periphery,
                  background_left=to_xyz(left) if left else _BLACK,
                  background_right=to_xyz(right) if right else _BLACK,
                  items=tuple(items), frame=frame, frame_period=frame_period)
