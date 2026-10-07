"""The screen description: everything on the animal's screen, resolved to numbers
(engine spec §3.3; build A1).

`resolve` is the one place a task's declarations become something to draw: parameters
bound, named kinds expanded into `look` blocks, an `Array` into its items, each eye's
direction computed (disparity, then the vergence offset), colors turned into CIE XYZ.
Its consumers -- the exact drawer now; the display process (build E), the screen log
(build F), the simulated animal (build C) and demo mode later -- read the `Screen` and
nothing else. It is versioned like telemetry: `SCHEMA`, checked on read.
"""

from __future__ import annotations

from dataclasses import dataclass, fields, replace

from wl_xcon import look
from wl_xcon.photometry import Gray, Michelson, Weber, to_xyz, xyY
from wl_xcon.task import (
    Annulus, Array, Bar, Blank, Cross, Disc, Gabor, Grating, P, Polygon, Square, _value,
)

SCHEMA = 1
_BLACK = (0.0, 0.0, 0.0)


class NotYetDrawable(ValueError):
    """Something a later build of the engine draws, named with that build."""


@dataclass(frozen=True, slots=True)
class ResolvedFlat:
    """A flat fill's light: absolute, or a contrast against the eye's background."""

    #: An absolute light.
    xyz: tuple[float, float, float] | None
    #: Or a contrast against the eye's background.
    weber: float | None


@dataclass(frozen=True, slots=True)
class ResolvedGrating:
    """A sine grating with every parameter a number."""

    sf: float
    phase: float
    tf: float
    michelson: float
    #: `None`: what is behind it.
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


def _color(color, values):
    """CIE XYZ of an absolute color, its parameters bound; `None` stays `None`."""
    if isinstance(color, P):
        color = _value(color, values)
    if color is None:
        return None
    if isinstance(color, Gray):
        return to_xyz(Gray(_num(color.cd_m2, values)))
    if isinstance(color, xyY):
        return to_xyz(xyY(_num(color.x, values), _num(color.y, values), _num(color.Y, values)))
    raise NotYetDrawable(f"{color} is drawn through cone fundamentals, in engine build A2")


def _contrast(contrast, kind, values):
    if isinstance(contrast, P):
        contrast = _value(contrast, values)
    if contrast is None:
        return None
    if type(contrast) is not kind:
        raise NotYetDrawable(
            f"{type(contrast).__name__} contrast here is drawn in a later engine build; "
            f"this build draws {kind.__name__}"
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
        raise NotYetDrawable("a colored grating is drawn in engine build A2")
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


def _fill(fill, values):
    if isinstance(fill, look.Flat):
        resolved = ResolvedFlat(xyz=_color(fill.color, values),
                                weber=_contrast(fill.contrast, Weber, values))
        if resolved.xyz is None and resolved.weber is None:
            raise ValueError("a flat fill with neither a color nor a contrast has no light")
        return resolved
    if isinstance(fill, look.SineGrating):
        michelson = _contrast(fill.contrast, Michelson, values)
        if michelson is None:
            raise ValueError("a grating with no contrast is its mean alone")
        return ResolvedGrating(sf=_num(fill.sf, values), phase=_num(fill.phase, values),
                               tf=_num(fill.tf, values), michelson=michelson,
                               mean_xyz=_color(fill.mean, values))
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


def _item(stimulus, name, order, looks, offset, values, geometry, onset) -> Item:
    expanded = as_look(looks, values)
    fill = _fill(expanded.fill, values)
    edge = _bind(expanded.edge, values)
    if edge.applies is None:
        edge = replace(edge, applies="contrast" if isinstance(fill, ResolvedGrating) else "opacity")
    outline = None
    if expanded.outline is not None:
        outline = ResolvedOutline(width=_num(expanded.outline.width, values),
                                  xyz=_color(expanded.outline.color, values))
    at_left, at_right = _eyes(stimulus, values, geometry, offset)
    return Item(
        name=name, order=order, layer=stimulus.layer, combine=stimulus.combine,
        opacity=_num(stimulus.opacity, values), eye=stimulus.eye,
        at_left=at_left, at_right=at_right,
        orientation=_num(expanded.orientation, values),
        shape=_bind(expanded.shape, values), fill=fill, edge=edge, outline=outline,
        onset_frame=onset,
    )


def _items(stimulus, order, values, geometry, onset) -> list[Item]:
    looks = _value(stimulus.looks, values) if isinstance(stimulus.looks, P) else stimulus.looks
    if isinstance(looks, Blank):
        return []
    if isinstance(looks, Array):
        return [
            _item(stimulus, f"{stimulus.name}.{i}", (order, i), looks.item_looks(i, values),
                  offset, values, geometry, onset)
            for i, offset in enumerate(looks.positions(values))
        ]
    return [_item(stimulus, stimulus.name, (order, 0), looks, (0.0, 0.0), values, geometry, onset)]


def resolve(visible, values, trial, geometry, *, frame_period, frame=0, onsets=None) -> Screen:
    """The screen as `visible` and `values` make it at `frame`. `visible` keeps the order
    stimuli were shown (the trial loop's `dict`), which breaks ties within a layer;
    `onsets` gives each stimulus's first frame, from which drift is timed."""
    base = _color(trial.background, values) or _BLACK
    left = _color(trial.background_left, values) or base
    right = _color(trial.background_right, values) or base
    items: list[Item] = []
    for order, stimulus in enumerate(visible.values()):
        items.extend(_items(stimulus, order, values, geometry, (onsets or {}).get(stimulus.name, 0)))
    items.sort(key=lambda i: (i.layer, i.order))
    return Screen(setup=geometry.view, periphery=trial.periphery, background_left=left,
                  background_right=right, items=tuple(items), frame=frame,
                  frame_period=frame_period)
