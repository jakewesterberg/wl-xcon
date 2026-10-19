"""Display geometry, for both setups: direct view and the split-screen stereoscope.

**One screen at one place, two paths to it** (direct-view spec §2). The screen is fixed
50 cm from the eyes in both setups (PI, 2026-09-28); the stereoscope is a removable device
in front of it.

- **Direct view:** both eyes see the whole panel, at the screen's own distance. The field
  is the panel's, less the light sensors' housings in a bottom corner (spec §4).
- **The stereoscope:** one panel split down the middle, each eye viewing its half through a
  two-mirror periscope. The mirrors translate rather than deviate, so the *optical path* is
  the physical distance plus the lateral shift: about 63 cm, moving with each animal's eye
  spacing (`Geometry.stereoscope`). A removable mask at the panel stops the field, at ±12°
  to start.

**The panel is given by its active area, not its diagonal.** S0 §5.2's diagonal form
assumes an exact 16:9, and the rig's ASUS PG27UCDM is neither: ASUS publishes its
active area as 589.97 × 332.93 mm (1.772:1) and its diagonal as a rounded "26.5-inch
viewable". Feeding the rounded diagonal through the 16:9 fractions puts each edge
0.6-0.9% short (S0 §5.2).

**Degrees map to the panel by `D · tan`, per axis**, so the field is a rectangle in degrees
as it is in centimeters, and a housing's rectangle on the panel is a region in degrees the
same way.

**An angle at the eye is true visual angle, measured where it is** (the PI, 2026-10-19: "it
is forward calculated for that specific location rather than using ppd averages"). Per-axis
degrees are coordinates, not distances: how far gaze is from a window's center, or one window
or object from another, is the angle between their directions (`separation_deg`,
`least_separation_deg`, `ring_spacing_deg`), and `Geometry.pixels_per_degree` is a reported
mean nothing draws, scores or checks with.

Every number here is derived from `2026-08-31-stereoscope-optics-drawing.md` §3,
S0 §5.2 and the direct-view spec §2, and the tests assert the agreement. **They are
computed, not measured.** V9 measures each eye's real path per animal, because the
mirror carriage is adjustable and the two paths are equal only if the mirrors are.
"""

from __future__ import annotations

import heapq
import itertools
import math
from dataclasses import dataclass

#: The two setups a session can run in (direct-view spec §3). The operator picks one at
#: session start; a task's `Trial.view` names one of these, or `"either"`.
VIEWS = ("direct", "stereoscope")

#: The optics drawing's nominal half-IPD, `E`, in cm (its §1; IPD 32 mm): what the stereoscope is
#: built for when an animal has no settings file, with a warning, the session recording it as
#: nominal (the PI, 2026-10-11, XC-352's C6: "a warning; the nominal 1.6 cm is recorded as
#: nominal"; `warnlist.of_setup`). **Not a measurement** (STE-20).
NOMINAL_HALF_IPD_CM = 1.6


@dataclass(frozen=True, slots=True)
class Housing:
    """One screen-timing light sensor's opaque housing, as a rectangle on the panel.

    **In cm from the active area's bottom-left corner, as the animal faces the screen**:
    `left_cm` and `right_cm` from its left edge, `bottom_cm` and `top_cm` up from its
    bottom edge -- what a person measures at build with a rule against the panel.

    `margin_cm` is recorded beside the rectangle (direct-view spec §4) and widens it on
    every side, because check 8 tests a stimulus's position, not its extent.
    """

    left_cm: float
    right_cm: float
    bottom_cm: float
    top_cm: float
    margin_cm: float

    def __post_init__(self) -> None:
        values = (self.left_cm, self.right_cm, self.bottom_cm, self.top_cm, self.margin_cm)
        if not all(math.isfinite(v) for v in values):
            raise ValueError(
                f"a housing's rectangle must be finite cm; got {values}. A NaN or "
                f"infinite bound compares as neither covering a point nor excluding "
                f"one, so `covers` would go quiet instead of refusing"
            )
        if self.left_cm >= self.right_cm:
            raise ValueError(
                f"a housing's left edge ({self.left_cm:g} cm) must be less than its "
                f"right edge ({self.right_cm:g} cm); left >= right is a rectangle "
                f"that covers no point on the panel, and a stimulus under the real "
                f"housing would pass"
            )
        if self.bottom_cm >= self.top_cm:
            raise ValueError(
                f"a housing's bottom edge ({self.bottom_cm:g} cm) must be less than "
                f"its top edge ({self.top_cm:g} cm); bottom >= top is a rectangle "
                f"that covers no point on the panel, and a stimulus under the real "
                f"housing would pass"
            )
        if self.margin_cm < 0:
            raise ValueError(
                f"a housing's margin must not be negative; got {self.margin_cm:g} "
                f"cm, which would shrink the excluded rectangle instead of widening "
                f"it (direct-view spec §4)"
            )

    def covers(self, x_cm: float, y_cm: float) -> bool:
        """Whether a point on the panel, in the same corner-origin cm, is under this
        housing or its margin."""
        return (
            self.left_cm - self.margin_cm <= x_cm <= self.right_cm + self.margin_cm
            and self.bottom_cm - self.margin_cm <= y_cm <= self.top_cm + self.margin_cm
        )


@dataclass(frozen=True, slots=True)
class Geometry:
    #: The panel's active area. Through the stereoscope each eye's viewport is half its
    #: width and all of its height; in direct view the viewport is the whole panel.
    panel_width_cm: float
    panel_height_cm: float
    #: Along the **folded** optical path through the stereoscope; the screen's own
    #: distance in direct view.
    viewing_distance_cm: float
    #: `"stereoscope"` or `"direct"` (`VIEWS`).
    view: str = "stereoscope"
    #: The stereoscope's mask at the panel, as a half-angle in degrees (direct-view spec
    #: §2), or `None` for the viewport's own field.
    mask_deg: float | None = None
    #: The light sensors' housings, direct view's alone: through the stereoscope the
    #: mask hides them. **Direct view refuses to exist without them.**
    housings: tuple[Housing, ...] = ()
    #: The half-IPD, `E`, a stereoscope field was built for, in cm: one animal's,
    #: from its settings file (PI, 2026-09-29). `None` in direct view, which has none.
    #: Kept on the field so the record and telemetry read it from the object that
    #: decided the field, never from a second copy.
    half_ipd_cm: float | None = None

    def __post_init__(self) -> None:
        if self.view not in VIEWS:
            raise ValueError(
                f"{self.view!r} is not a setup; a geometry is one of {', '.join(VIEWS)}"
            )
        if self.view == "direct" and not self.housings:
            raise ValueError(
                "direct view's field excludes the light sensors' housings, and none were "
                "given. They are measured at build (direct-view spec §9 item 1); a field "
                "without them would pass a stimulus drawn under a housing"
            )
        if self.view == "stereoscope" and self.housings:
            raise ValueError(
                "the stereoscope's mask hides the light sensors, so a stereoscope "
                "geometry takes no housings; a housing there would exclude degrees "
                "the mask already stops, for a reason that does not hold in this "
                "setup"
            )
        if self.view == "direct" and self.mask_deg is not None:
            raise ValueError(
                f"direct view has no mask -- only the stereoscope's removable mask "
                f"stops the field -- so mask_deg={self.mask_deg!r} on a direct "
                f"geometry would silently narrow the field to a value nothing at the "
                f"rig sets"
            )
        if self.view == "direct" and self.half_ipd_cm is not None:
            raise ValueError(
                "direct view has no half-IPD: both eyes see the one screen at its own "
                "distance, so an animal's eye spacing changes nothing in its field"
            )

    @classmethod
    def stereoscope(
        cls,
        panel_width_cm: float,
        panel_height_cm: float,
        *,
        screen_distance_cm: float,
        half_ipd_cm: float,
        mask_deg: float | None = None,
    ) -> Geometry:
        """The field through the periscope, with the screen `screen_distance_cm` from
        the eyes and the eyes `half_ipd_cm` either side of the midline.

        **The screen is fixed and the path follows from it** (PI, 2026-09-28: the same
        physical distance in the stereoscope and in direct view, 50 cm). Each eye's axis
        is carried from x = ∓E out to its viewport's center at ∓W/4, and that lateral
        run is optical path the physical distance does not show: `D = Z + W/4 − E`.
        So the path, and with it the field, is per animal (optics drawing §3, §4.4).
        """
        return cls(
            panel_width_cm=panel_width_cm,
            panel_height_cm=panel_height_cm,
            viewing_distance_cm=screen_distance_cm + panel_width_cm / 4 - half_ipd_cm,
            mask_deg=mask_deg,
            half_ipd_cm=half_ipd_cm,
        )

    @classmethod
    def direct(
        cls,
        panel_width_cm: float,
        panel_height_cm: float,
        *,
        screen_distance_cm: float,
        housings: tuple[Housing, ...],
    ) -> Geometry:
        """The whole panel, seen by both eyes at the screen's own distance, less the
        light sensors' housings (direct-view spec §2, §4)."""
        return cls(
            panel_width_cm=panel_width_cm,
            panel_height_cm=panel_height_cm,
            viewing_distance_cm=screen_distance_cm,
            view="direct",
            housings=tuple(housings),
        )

    @property
    def half_width_cm(self) -> float:
        """The viewport's half-width: the whole panel's in direct view, one eye's half
        through the stereoscope."""
        return self.panel_width_cm / (2 if self.view == "direct" else 4)

    @property
    def half_height_cm(self) -> float:
        return self.panel_height_cm / 2

    @property
    def half_field_h_deg(self) -> float:
        """The horizontal half-field a stimulus may use: the viewport's, or the mask's
        where the mask is narrower."""
        return self._stopped(self._viewport_deg(self.half_width_cm))

    @property
    def half_field_v_deg(self) -> float:
        return self._stopped(self._viewport_deg(self.half_height_cm))

    def _viewport_deg(self, half_cm: float) -> float:
        return math.degrees(math.atan(half_cm / self.viewing_distance_cm))

    def _stopped(self, degrees: float) -> float:
        return degrees if self.mask_deg is None else min(degrees, self.mask_deg)

    @property
    def vergence_half_deg(self) -> float:
        """Each eye's share of the vergence offset, `atan(E/D)` in degrees.

        Through the stereoscope the axes leave parallel, so a stimulus drawn at the same
        place in both viewports sits at optical infinity; moving the left eye's image
        right and the right eye's left by `atan(E/D)` puts zero disparity at the
        screen's optical distance (optics drawing §6: `2·atan(E/D)` = 2.9° at `E` = 1.6
        cm). Computed, not measured. Zero in direct view, where both eyes see one screen.
        """
        if self.view == "direct":
            return 0.0
        if self.half_ipd_cm is None:
            raise ValueError(
                "the vergence offset is atan(E/D), and this stereoscope geometry has no "
                "half-IPD E; build it with Geometry.stereoscope or Rig.stereoscope"
            )
        return math.degrees(math.atan(self.half_ipd_cm / self.viewing_distance_cm))

    def pixels_per_degree(self, horizontal_pixels: int) -> float:
        """S0 §5.2's mean across one viewport, so `horizontal_pixels` is the viewport's:
        half the panel through the stereoscope, all of it in direct view. Across the
        viewport's own extent, not the mask's: the mask covers pixels, it does not
        rescale them.

        **A reported mean, never a scale anything is drawn, scored or checked with** (the PI,
        2026-10-19: forward calculated "for that specific location rather than using ppd
        averages"). A degree spans more pixels away from the center than at it, so no
        drawing, window or check path may read this: positions go through `D · tan` per axis
        and shapes through `viewport`, and angles between positions are `separation_deg`'s.
        `tests/test_geometry.py` asks the parser that nothing else in `wl_xcon/` names it."""
        return horizontal_pixels / (2 * self._viewport_deg(self.half_width_cm))

    def can_show(self, x_deg: float, y_deg: float) -> bool:
        """Whether a cyclopean position lands inside the field the setup shows.

        A position outside it is not a rendering problem to clamp -- the stimulus would
        be drawn off the panel, behind the mask or under a light sensor's housing, the
        animal would never see it, and the trial would score as a miss
        indistinguishable from behavior. Refused at load instead.
        """
        if abs(x_deg) > self.half_field_h_deg or abs(y_deg) > self.half_field_v_deg:
            return False
        x_cm = self.panel_width_cm / 2 + self.viewing_distance_cm * math.tan(
            math.radians(x_deg)
        )
        y_cm = self.panel_height_cm / 2 + self.viewing_distance_cm * math.tan(
            math.radians(y_deg)
        )
        return not any(housing.covers(x_cm, y_cm) for housing in self.housings)


@dataclass(frozen=True, slots=True)
class Rig:
    """The rig's display settings: everything both setups' fields are built from
    (direct-view spec §2), written in the rig's settings file, `tasks/rig.py`.

    **The housings may be empty** while they are unmeasured (spec §9 item 1): then
    `direct` refuses, because `Geometry` does, and the stereoscope still works -- its
    mask hides the sensors.

    **A session's field is built from this**: `wlx run --rig` names the file and
    `--view` the setup, and `taskd`'s load-time check runs against that field before
    anything is recorded (direct view part 2, 2026-09-29).
    """

    panel_width_cm: float
    panel_height_cm: float
    #: `Z`: eye to screen, physical, the same in both setups (PI, 2026-09-28).
    screen_distance_cm: float
    #: The stereoscope's mask, as a half-angle (±12° to start, PI 2026-09-28).
    mask_deg: float
    #: The half-IPDs the stereoscope is drawn for, in cm: the optics drawing's
    #: eye-separation table, IPD 30-38 mm (S0 §7.1.3). An animal outside it runs with a
    #: warning that its field is extrapolated, not drawn (the PI, 2026-10-11, XC-352's C7;
    #: `warnlist.of_setup`); it was refused until then.
    half_ipd_range_cm: tuple[float, float]
    #: The panel's pixels, horizontal and vertical (S0 §5.1).
    pixels: tuple[int, int]
    housings: tuple[Housing, ...] = ()
    #: Direct view's straight-ahead point, cm from the panel's center (x right, y up):
    #: where (0°, 0°) falls (engine spec §5.1). The center unless measured otherwise.
    straight_ahead_cm: tuple[float, float] = (0.0, 0.0)
    #: The panel's color calibration (engine spec §7.6: "one calibration for the whole
    #: panel"): the path of its record, relative to the rig file's folder unless absolute, or
    #: `None`, and sessions then run on the default, the sRGB standard, which the warnings list
    #: says (spec §7.1; `cli._load_calibration`).
    calibration: str | None = None

    def direct(self) -> Geometry:
        return Geometry.direct(
            self.panel_width_cm,
            self.panel_height_cm,
            screen_distance_cm=self.screen_distance_cm,
            housings=self.housings,
        )

    def stereoscope(self, half_ipd_cm: float) -> Geometry:
        """Through the stereoscope, for one animal's half-IPD, `E`, from its settings
        file (spec §2; PI, 2026-09-29), or the nominal one (`NOMINAL_HALF_IPD_CM`). **One
        outside `half_ipd_range_cm` is built too**, its field extrapolated (a warning,
        `warnlist.of_setup`; the PI, 2026-10-11, XC-352's C7). One that leaves no positive
        optical path, `Z + W/4 − E`, or is no number, has no field, and is refused."""
        path = self.screen_distance_cm + self.panel_width_cm / 4 - half_ipd_cm
        if not path > 0:
            raise ValueError(
                f"a half-IPD of {half_ipd_cm:g} cm leaves no positive optical path through this "
                f"stereoscope (Z + W/4 − E = {path:g} cm), so it has no field"
            )
        return Geometry.stereoscope(
            self.panel_width_cm,
            self.panel_height_cm,
            screen_distance_cm=self.screen_distance_cm,
            half_ipd_cm=half_ipd_cm,
            mask_deg=self.mask_deg,
        )


@dataclass(frozen=True, slots=True)
class SubjectSettings:
    """One animal's settings, from the file named at session start with
    `--subject-settings` (PI, 2026-09-29), as its bounded config is named with
    `--bounds`.

    Today it holds what the stereoscope's field needs and nothing more: the animal's
    half-IPD, `E`, "measured per animal" (optics drawing §2; backlog XC-082). Direct
    view reads nothing from it. `subject` is checked against the session's own, so one
    animal's eye spacing cannot quietly become another's.
    """

    subject: str
    half_ipd_cm: float

    def __post_init__(self) -> None:
        if not self.subject:
            raise ValueError("subject settings name no subject")
        # `bool` is an `int`; `None` is the placeholder for an unmeasured animal.
        if (
            isinstance(self.half_ipd_cm, bool)
            or not isinstance(self.half_ipd_cm, (int, float))
            or not (math.isfinite(self.half_ipd_cm) and self.half_ipd_cm > 0)
        ):
            raise ValueError(
                f"half_ipd_cm={self.half_ipd_cm!r} is not a half-IPD: half the distance "
                f"between the eyes' centers, in cm, a positive number"
            )


# --- Angles at the eye -------------------------------------------------------------------------
#
# The PI, 2026-10-19: "when a stimulus is presented at a specific position and size, ... it is
# forward calculated for that specific location rather than using ppd averages." Positions map
# to the panel by `D · tan` per axis and a shape is drawn in true visual angle about its own
# direction (`viewport`); a gaze window, and every load check that measures how far apart two
# positions are, is measured here, in true visual angle where the two positions are.

#: Where a side a range leaves without end is read to: past 90° a degree on an axis names no
#: direction ahead of the eye, and at 90° every position on the other axis is one direction.
_SIDE_DEG = 90.0


def separation_deg(x1: float, y1: float, x2: float, y2: float) -> float:
    """The true visual angle, in degrees, between two positions: the angle at the eye between
    the directions they name.

    A position `(x, y)` is the direction `(tan x, tan y, 1)` (`D · tan` per axis,
    `viewport.center`), taken here as its multiple by `cos x cos y`, `(sin x cos y, cos x sin y,
    cos x cos y)`: the same direction for every position a screen shows, and one that continues
    past the side of the field where `tan`'s period would wrap a position past 90° (a broken gaze
    map's, never a stimulus's) to the far side. The angle is `atan2(|u × v|, u · v)`, exact at
    small angles, where `acos` of a dot product loses its digits.

    **On the trial loop's hot path** (`gaze.Tracked.in_window`, every frame): floats and
    `math` only, no numpy and no container.
    """
    ax, ay = math.radians(x1), math.radians(y1)
    bx, by = math.radians(x2), math.radians(y2)
    cos_ax, cos_ay, cos_bx, cos_by = math.cos(ax), math.cos(ay), math.cos(bx), math.cos(by)
    ux = math.sin(ax) * cos_ay
    uy = cos_ax * math.sin(ay)
    uz = cos_ax * cos_ay
    vx = math.sin(bx) * cos_by
    vy = cos_bx * math.sin(by)
    vz = cos_bx * cos_by
    across = math.hypot(uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx)
    return math.degrees(math.atan2(across, ux * vx + uy * vy + uz * vz))


def least_separation_deg(xs_a, ys_a, xs_b, ys_b) -> float:
    """The least true visual angle between any position of one region and any of another: a
    region is every `(x, y)` with `x` in one of its intervals `xs` and `y` in one of its `ys`,
    each `(low, high)` in degrees, a point being `(v, v)`. What `check._closest_approach` asks of
    two windows whose centers are settings.

    **Two rectangles** in degrees are two rectangles on the tangent plane, so each is a convex
    patch of directions bounded by four arcs of great circles: they are 0° apart where they
    overlap, and otherwise as far apart as a corner of one is from an edge of the other
    (`_rectangles_apart`). **Many** -- a coordinate given by choices is a point for each -- are
    searched best first, each group of intervals bounded below by its hull's distance, so the
    first pair of single intervals reached is the least, and forty choices an axis are never
    crossed into 2.5 million pairs (the final re-review's m4). A side without end is read to
    90° (`_SIDE_DEG`).
    """
    sides = tuple(tuple(sorted((_to_side(low), _to_side(high)) for low, high in side))
                  for side in (xs_a, ys_a, xs_b, ys_b))
    if not all(sides):
        raise ValueError("a region has at least one interval on each axis")
    order = itertools.count()
    queue = [(_bound(sides), next(order), sides)]
    while queue:
        bound, _, node = heapq.heappop(queue)
        longest = max(range(4), key=lambda i: len(node[i]))
        if len(node[longest]) == 1:
            return bound
        half = len(node[longest]) // 2
        for part in (node[longest][:half], node[longest][half:]):
            child = node[:longest] + (part,) + node[longest + 1:]
            heapq.heappush(queue, (_bound(child), next(order), child))
    raise AssertionError("unreachable: a search over non-empty sides ends at a leaf")


def ring_spacing_deg(radius: float, n: float) -> float:
    """The least true visual angle between neighbors of `n` objects spaced evenly at per-axis
    offsets of `radius` degrees about (0°, 0°), where `task.Array.positions` places them and
    `task.ObjectWindows` their windows, **over every phase** the ring can be turned to.

    Per axis neighbors are `2 R sin(π/n)` apart at every phase; in true visual angle the ring
    is nearer together where it crosses an axis, the vertical a degree there spanning `cos x` of
    one, and further apart across a diagonal. The per-axis map has the square's symmetries, so a
    pair's spacing is even about each axis and each diagonal, and the least is at one of the
    two: checked at every degree of phase, from 2 to 1000 objects on rings out to 44°
    (`tests/test_geometry.py`). `n` without end gives 0.
    """
    half = math.pi / n
    return min(
        separation_deg(radius * math.cos(center - half), radius * math.sin(center - half),
                       radius * math.cos(center + half), radius * math.sin(center + half))
        for center in (0.0, math.pi / 4)
    )


def _to_side(value: float) -> float:
    return max(-_SIDE_DEG, min(_SIDE_DEG, float(value)))


def _bound(node) -> float:
    """The least angle any pair of rectangles in `node` can reach: that between the hulls of its
    intervals, which hold every one of them. Exact when each side is one interval."""
    hulls = [(side[0][0], max(high for _, high in side)) for side in node]
    return _rectangles_apart(*hulls)


def _rectangles_apart(ax, ay, bx, by) -> float:
    """The least true visual angle between the rectangles `ax × ay` and `bx × by`.

    Rectangles that overlap on both axes share a position. Otherwise the least is from a corner
    of one to an edge of the other: were both ends of the shortest arc inside edges, that arc
    would meet both great circles square, and the one arc that does joins the points where each
    circle is furthest from the other, where moving along the edge brings them closer."""
    if ax[0] <= bx[1] and bx[0] <= ax[1] and ay[0] <= by[1] and by[0] <= ay[1]:
        return 0.0
    if ax[0] == ax[1] and ay[0] == ay[1] and bx[0] == bx[1] and by[0] == by[1]:
        return separation_deg(ax[0], ay[0], bx[0], by[0])
    return min(
        min(_to_rectangle(x, y, bx, by) for x in set(ax) for y in set(ay)),
        min(_to_rectangle(x, y, ax, ay) for x in set(bx) for y in set(by)),
    )


def _to_rectangle(x: float, y: float, xs, ys) -> float:
    """The least true visual angle from `(x, y)` to the edges of the rectangle `xs × ys`. The
    axes trade places for its top and bottom: swapping them reflects every direction in one
    plane, which keeps every angle."""
    return min(
        _to_edge(x, y, xs[0], ys), _to_edge(x, y, xs[1], ys),
        _to_edge(y, x, ys[0], xs), _to_edge(y, x, ys[1], xs),
    )


def _to_edge(x: float, y: float, edge_x: float, ys) -> float:
    """The least true visual angle from `(x, y)` to the edge `edge_x × ys`, an arc of the great
    circle every position at `edge_x` lies on.

    Along that circle's half ahead of the eye the angle falls to the foot of the perpendicular
    from `(x, y)` and rises after it, so the least over the edge is at the foot, held to the
    edge's ends. The foot is ahead of the eye when `1 + tan(edge_x) tan(x) > 0`, that is when
    `x` is within 90° of `edge_x`, and its height is then `tan y (1 + tan² edge_x) / (1 +
    tan(edge_x) tan(x))` on the tangent plane; otherwise the angle only rises from the ends
    inward, and the least is at one of them."""
    low, high = ys
    t_edge, t_x = math.tan(math.radians(edge_x)), math.tan(math.radians(x))
    ahead = 1.0 + t_edge * t_x
    if ahead > 0.0:
        foot = math.degrees(math.atan(math.tan(math.radians(y)) * (1.0 + t_edge * t_edge) / ahead))
        return separation_deg(x, y, edge_x, min(max(foot, low), high))
    return min(separation_deg(x, y, edge_x, low), separation_deg(x, y, edge_x, high))
