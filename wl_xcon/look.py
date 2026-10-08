"""The building blocks of what can be shown (engine spec §4.1-4.2; build A1).

**A stimulus is a shape, filled with something, seen through an edge, placed and
layered.** Today's named kinds (`task.Disc`, `Square`, `Bar`, `Gabor`, ...) stay as
shorthands: `screen.as_look` expands each into these blocks, so the exact drawer knows
only blocks. A new block arrives once, as reviewed framework code with its definition in
`exact.py`, its GPU version, its tests and a person-readable report (spec §4.10).

Every size is a full width in degrees (spec §5.2) and every value may be a parameter,
bound by `screen.resolve`. This build draws `Flat` and `SineGrating`; A3 adds the other
fills, A4 text, curves and images.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from wl_xcon.task import Appearance

#: What an edge's profile multiplies (spec §4.2): the stimulus's opacity, or its
#: pattern's contrast about the pattern's mean (the classic Gabor). `None` on an edge
#: means the fill's own default: a contrast envelope on a pattern, an opacity ramp on a
#: flat light (where the two are one thing: a light fading into what is behind it). A
#: window or a scotoma draws no light of its own, so its edge is an opacity ramp whatever
#: its fill: it shapes what shows through (the A1 follow-ups' call 5).
EDGE_APPLIES = ("opacity", "contrast")

#: The `Gabor` shorthand's drawn extent, in envelope standard deviations from its center.
#: At 4σ the envelope is exp(−8) ≈ 3.4 × 10^-4 of the Gabor's own contrast.
GABOR_CUTOFF_SIGMAS = 4.0


@dataclass(frozen=True, slots=True)
class Shape:
    """Where a stimulus is drawn, in its own local frame: degrees from its center,
    before its orientation turns it."""


@dataclass(frozen=True, slots=True)
class Circle(Shape):
    size: object = 1.0  # diameter


@dataclass(frozen=True, slots=True)
class Ellipse(Shape):
    width: object = 2.0
    height: object = 1.0


@dataclass(frozen=True, slots=True)
class Rect(Shape):
    width: object = 1.0
    height: object = 1.0


@dataclass(frozen=True, slots=True)
class Cross(Shape):
    """A plus sign: two bars `size` long and `thickness` wide, along x and y."""

    size: object = 0.5
    thickness: object = 0.1


@dataclass(frozen=True, slots=True)
class RegularPolygon(Shape):
    """`sides` vertices on a circle of diameter `size`, the first at 90° (up): a
    triangle points up, four sides make a diamond."""

    sides: object = 3
    size: object = 1.0


@dataclass(frozen=True, slots=True)
class Vertices(Shape):
    """A closed, simple polygon through `points`, degrees in the local frame."""

    points: tuple = ()


@dataclass(frozen=True, slots=True)
class Ring(Shape):
    inner: object = 1.0  # diameters
    outer: object = 2.0


@dataclass(frozen=True, slots=True)
class Path(Shape):
    """A line through `points`, `width` degrees wide, with round ends."""

    points: tuple = ()
    width: object = 0.1


@dataclass(frozen=True, slots=True)
class WholeScreen(Shape):
    """Every point of the eye's viewport: a full-field flash, a background change."""


@dataclass(frozen=True, slots=True)
class Fill:
    """What is inside the shape."""


@dataclass(frozen=True, slots=True)
class Flat(Fill):
    """One light: an absolute `color` (`Gray`, `xyY`), or a `Weber` `contrast` against
    the trial's declared background. Never both."""

    color: object = None
    contrast: object = None


@dataclass(frozen=True, slots=True)
class SineGrating(Fill):
    """A sine-wave luminance grating. Its bars run along the local x axis, so the
    luminance varies along local y (a grating's orientation names its bars, spec §5.1):
    `sf` cycles per degree, `phase` in degrees, drifting at `tf` cycles per second (a
    speed, never negative) from the frame it appeared. `direction` is the way the bars
    move, in degrees in the screen's frame (0 is right, counter-clockwise, like every
    angle) and must be across the bars; `None` means the grating's orientation + 90
    degrees. A grating's orientation names its bars and its drift direction is a separate
    angle (spec §5.1; the PI, 2026-10-07: "Its own angle"). `contrast` is `Michelson`,
    about `mean`: an absolute color, or `None` for whatever is behind it (spec §4.3)."""

    sf: object = 2.0
    phase: object = 0.0
    tf: object = 0.0
    direction: object = None
    contrast: object = None
    mean: object = None


@dataclass(frozen=True, slots=True)
class Edge:
    """How a stimulus meets what is around it."""


@dataclass(frozen=True, slots=True)
class Hard(Edge):
    applies: "str | None" = None


@dataclass(frozen=True, slots=True)
class RaisedCosine(Edge):
    """A raised-cosine ramp `width` degrees wide, inside the shape's boundary."""

    width: object = 0.1
    applies: "str | None" = None


@dataclass(frozen=True, slots=True)
class GaussianEdge(Edge):
    """A radial Gaussian of standard deviation `sigma` about the stimulus's center. The
    shape's size is the cut-off, declared separately (spec §4.2)."""

    sigma: object = 1.0
    applies: "str | None" = None


@dataclass(frozen=True, slots=True)
class Outline:
    """A band `width` degrees wide, centered on the shape's boundary, in `color`."""

    width: object = 0.05
    color: object = None


@dataclass(frozen=True, slots=True)
class Look(Appearance):
    """A shape, a fill, an edge and an optional outline, turned by `orientation`
    (degrees, counter-clockwise): the general appearance."""

    shape: Shape = field(default_factory=Circle)
    fill: Fill = field(default_factory=Flat)
    edge: Edge = field(default_factory=Hard)
    outline: "Outline | None" = None
    orientation: object = 0.0
