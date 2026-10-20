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

import numpy as np

#: The two setups a session can run in (direct-view spec §3). The operator picks one at
#: session start; a task's `Trial.view` names one of these, or `"either"`.
VIEWS = ("direct", "stereoscope")

#: The optics drawing's nominal half-IPD, `E`, in cm (its §1; IPD 32 mm): what the stereoscope is
#: built for when an animal has no settings file, with a warning, the session recording it as
#: nominal (the PI, 2026-10-11, XC-352's C6: "a warning; the nominal 1.6 cm is recorded as
#: nominal"; `warnlist.of_setup`). **Not a measurement** (STE-20).
NOMINAL_HALF_IPD_CM = 1.6

#: What a disparity `d` means (the PI, 2026-10-19, "Keep longitude, say so"; STE-07): each eye's
#: image is shifted `∓d/2` in per-axis horizontal degrees, the angle about the vertical axis, so
#: `d` is the difference in **azimuth longitude** between the two eyes' images -- exact in that
#: convention, a standard definition of horizontal disparity, and not the true angle between the
#: images off the horizontal meridian (about `d·cos y` at elevation `y`). The review report and
#: each session's `config.json` name it, so an analysis knows what `d` means.
DISPARITY_CONVENTION = "azimuth-longitude"


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
#: direction ahead of the eye, and at 90° every position on the other axis is one direction. So
#: per-axis degrees cannot say where a polar position 90° out lies (`polar_deg(90, θ)` is
#: (±90°, ±90°) whatever θ is): the closed forms measure polar positions by their directions
#: (`_polar_unit`), and give a polar sector reaching 90° against a rectangle no closed form
#: (`_exact`), so the boxes that hold it bound it, failing closed.
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


def least_separation_deg(xs_a, ys_a, xs_b, ys_b, *, polar_a: bool = False,
                         polar_b: bool = False) -> float:
    """The least true visual angle between any position of one region and any of another: a
    region is every `(x, y)` with `x` in one of its intervals `xs` and `y` in one of its `ys`,
    each `(low, high)` in degrees, a point being `(v, v)`; or, `polar_a` or `polar_b` set, every
    `polar_deg(e, θ)` with `e` in one of its first intervals and θ in one of its second. What
    `check._closest_approach` asks of two windows whose centers are settings.

    **Two rectangles** in degrees are two rectangles on the tangent plane, so each is a convex
    patch of directions bounded by four arcs of great circles: they are 0° apart where they
    overlap, and otherwise as far apart as a corner of one is from an edge of the other
    (`_rectangles_apart`). A point and a polar sector, and two polar sectors, are as far apart
    as their nearest eccentricities along a direction they share, else as their facing radial
    edges (`_to_sector`, `_sectors_apart`). **Many** -- a coordinate given by choices is a point
    for each -- are searched best first, each group of intervals bounded below by the distance
    between the boxes that hold it (`polar_box_deg` for a polar one), so forty choices an axis
    are never crossed into 2.5 million pairs (the final re-review's m4); a polar sector and a
    rectangle are as far apart as the nearest of a few points on the rectangle's edges is from
    the sector (`_sector_to_rectangle`). Two regions of points alone are compared pair by pair
    with numpy instead (`_pointwise`). A negative eccentricity is the same position a half turn
    round (`_parts`). A side without end is read to 90° (`_SIDE_DEG`), a direction without end
    as every direction.
    """
    polar = (polar_a, polar_b)
    parts_a = _parts(xs_a, ys_a, polar_a)
    parts_b = _parts(xs_b, ys_b, polar_b)
    if not (parts_a and parts_b):
        raise ValueError("a region has at least one interval on each axis")
    return min(_search((*a, *b), polar) for a in parts_a for b in parts_b)


def _parts(first, second, polar: bool) -> list[tuple[tuple, tuple]]:
    """A region's sides, sorted and read to their limits (`_region`), as one or two parts: a
    polar region's eccentricities below 0 are the same positions at their negation a half turn
    round, `(-e, θ + 180°)`, so they are a part of their own, and an interval straddling 0 is
    split between the two, so that every polar part has eccentricities not below 0 and its
    closed forms (`_to_sector`, `_sectors_apart`, `_sector_to_rectangle`)."""
    first, second = _region(first, polar, False), _region(second, polar, True)
    if not (first and second):
        return []
    if not polar:
        return [(first, second)]
    ahead = tuple((max(low, 0.0), high) for low, high in first if high >= 0.0)
    behind = tuple(sorted((max(-high, 0.0), -low) for low, high in first if low < 0.0))
    turned = _region([(low + 180.0, high + 180.0) for low, high in second], True, True)
    return [(eccentricities, directions)
            for eccentricities, directions in ((ahead, second), (behind, turned))
            if eccentricities]


def _search(sides, polar) -> float:
    """The least between two parts (`_parts`), searched best first over their lists of intervals,
    each group bounded below by the distance between the boxes that hold it, until a pair of single
    intervals is reached, whose least has a closed form (`_exact`). Past `_SEARCH_LIMIT` nodes the
    least bound left is the answer, never more than the least."""
    pointwise = _pointwise(sides, polar)
    if pointwise is not None:
        return pointwise
    order = itertools.count()
    queue = [(*_bound(sides, polar), next(order), sides)]
    for searched in itertools.count():
        bound, exact, _, node = heapq.heappop(queue)
        if exact or searched >= _SEARCH_LIMIT or all(len(side) == 1 for side in node):
            return bound
        for child in _halves(node):
            heapq.heappush(queue, (*_bound(child, polar), next(order), child))
    raise AssertionError("unreachable: the search returns from within its loop")


#: The most pairs `_pointwise` compares at once, a float64 matrix of them in memory (32 MB).
_PAIRWISE_LIMIT = 4_000_000


def _pointwise(sides, polar) -> float | None:
    """**When both regions are points** -- every coordinate a literal or a setting's choices --
    the least over every pair, by numpy's pairwise dot products (at load and between trials,
    never in a frame): the pairs whose dot product is within 1e-12 of the greatest, which holds
    the nearest pair whatever the rounding, measured exactly by `separation_deg`. `None` for a
    region with a range in it, a polar point 90° out (`_SIDE_DEG`), or more than
    `_PAIRWISE_LIMIT` pairs, which the search takes."""
    if not all(low == high for side in sides for low, high in side):
        return None
    if any(is_polar and abs(low) >= _SIDE_DEG
           for first, is_polar in ((sides[0], polar[0]), (sides[2], polar[1]))
           for low, _ in first):
        return None
    regions = []
    for first, second, is_polar in ((sides[0], sides[1], polar[0]), (sides[2], sides[3], polar[1])):
        regions.append([polar_deg(e, t) if is_polar else (e, t)
                        for e, _ in first for t, _ in second])
    if len(regions[0]) * len(regions[1]) > _PAIRWISE_LIMIT:
        return None
    a, b = (np.radians(np.array(region, dtype=float)) for region in regions)

    def unit(r: np.ndarray) -> np.ndarray:
        x, y = r[:, 0], r[:, 1]
        v = np.stack([np.sin(x) * np.cos(y), np.cos(x) * np.sin(y), np.cos(x) * np.cos(y)], axis=1)
        return v / np.linalg.norm(v, axis=1, keepdims=True)

    dots = unit(a) @ unit(b).T
    nearest = np.argwhere(dots >= dots.max() - 1e-12)
    return min(separation_deg(*regions[0][i], *regions[1][j]) for i, j in nearest)


#: The most nodes a search expands before it answers with its least bound left, which is never
#: more than the least. Every pair of single intervals has a closed form, so a search ends there
#: in as many nodes as its lists of intervals need; this guards a load check run between two
#: trials (`taskd.Session._beyond_range`) against lists no test has met, at a sound answer.
_SEARCH_LIMIT = 20_000


def polar_deg(eccentricity: float, direction: float) -> tuple[float, float]:
    """The position `eccentricity` degrees of visual angle from straight ahead, `direction`
    degrees counter-clockwise from rightward (engine spec §5.1's convention), as per-axis
    degrees: the direction `(sin e cos θ, sin e sin θ, cos e)`, so `atan(tan e cos θ)` across
    and `atan(tan e sin θ)` up (the PI, 2026-10-19: "A task can say 'at eccentricity e, direction
    θ' and the rig converts it exactly").

    **Past 90°**, where `atan(tan e …)` would wrap the position onto the far side of the field
    and a field could show it, it is the same direction as `separation_deg` reads per-axis
    degrees, continued past the side on the axis it leans along: `e` from straight ahead, and
    past every field. The other axis then reads as `separation_deg`'s form does past the side,
    its sign turned; no screen shows such a position, and check 8 refuses it."""
    e, t = math.radians(eccentricity), math.radians(direction)
    vx = math.sin(e) * math.cos(t)
    vy = math.sin(e) * math.sin(t)
    vz = math.cos(e)
    if vz > 0.0:
        return (math.degrees(math.atan2(vx, vz)), math.degrees(math.atan2(vy, vz)))
    if abs(vx) >= abs(vy):
        return (math.degrees(math.atan2(vx, vz)),
                math.degrees(math.atan(vy / vz)) if vz else 0.0)
    return (math.degrees(math.atan(vx / vz)) if vz else 0.0,
            math.degrees(math.atan2(vy, vz)))


def polar_box_deg(eccentricities, directions) -> tuple[tuple[float, float], tuple[float, float]]:
    """The per-axis box, `((x0, x1), (y0, y1))`, holding every `polar_deg(e, θ)` with `e` in the
    interval `eccentricities` and θ in `directions`: its extremes wherever they fall, between the
    ends of the direction's range included (20° out over 0° to 120° reaches 20° up, at 90°).
    Across is `atan(tan e · cos θ)`, a product of two independent ranges, so its extremes are
    among the products of their ends, `cos θ` reaching ±1 where the range holds 0° or 180°; up
    likewise with `sin θ`. Eccentricity is read to 90° either way (`_SIDE_DEG`): past it a
    position is past the side of every field."""
    low, high = sorted(max(-_SIDE_DEG, min(_SIDE_DEG, float(v))) for v in eccentricities)
    tans = (math.tan(math.radians(low)), math.tan(math.radians(high)))

    def extent(shares: tuple[float, float]) -> tuple[float, float]:
        products = [a * b for a in tans for b in shares]
        return (math.degrees(math.atan(min(products))), math.degrees(math.atan(max(products))))

    start, stop = directions
    return extent(_cosine_range(start, stop, 0.0)), extent(_cosine_range(start, stop, 90.0))


def _cosine_range(start: float, stop: float, peak: float) -> tuple[float, float]:
    """The least and greatest `cos(θ − peak)` for θ from `start` to `stop` degrees."""
    if not stop - start < 360.0:
        return (-1.0, 1.0)
    ends = [math.cos(math.radians(v - peak)) for v in (start, stop)]
    return (-1.0 if _holds(start, stop, peak + 180.0) else min(ends),
            1.0 if _holds(start, stop, peak) else max(ends))


def _holds(start: float, stop: float, angle: float) -> bool:
    """Whether `angle`, or one a whole turn from it, lies from `start` to `stop` degrees."""
    return math.ceil((start - angle) / 360.0) <= math.floor((stop - angle) / 360.0)


def _region(intervals, polar: bool, second: bool) -> tuple:
    """One side of a region, sorted: an axis read to 90° either way, an eccentricity likewise,
    and a direction whose range has no end, or turns all the way round, as every direction."""
    if polar and second:
        return tuple(sorted((-180.0, 180.0) if not (math.isfinite(low) and math.isfinite(high)
                                                     and high - low < 360.0) else (low, high)
                            for low, high in intervals))
    return tuple(sorted((_to_side(low), _to_side(high)) for low, high in intervals))


def _halves(node):
    """Two nodes that between them hold every pair `node` does: its longest list of intervals
    halved."""
    longest = max(range(4), key=lambda i: len(node[i]))
    half = len(node[longest]) // 2
    return [node[:longest] + (part,) + node[longest + 1:]
            for part in (node[longest][:half], node[longest][half:])]


def _bound(node, polar) -> tuple[float, bool]:
    """The least angle any pair of positions in `node` can reach, and whether it is exact: that
    between the boxes holding each side's intervals (`polar_box_deg` for a polar side), which hold
    every one of them, and exact where single intervals have a closed form (`_exact`).

    **With a polar side, no less than the gap between the two sides' eccentricities**: two
    positions are at least as far apart as their eccentricities differ (the triangle through
    straight ahead). A box holding a sector that reaches 90° can hold the center too and read 0°
    where the sector is 5° out or more; the gap reads it as it is. A side wholly 90° out, which no
    per-axis box holds, is read by the gap alone, and 0° where there is none."""
    if all(len(side) == 1 for side in node):
        exact = _exact(node, polar)
        if exact is not None:
            return exact, True
    boxes = []
    reaches = []
    at_side = False
    for first, second, is_polar in ((node[0], node[1], polar[0]), (node[2], node[3], polar[1])):
        hulls = [(side[0][0], max(high for _, high in side)) for side in (first, second)]
        # Wholly 90° out, no per-axis box holds a position: read by the gap alone, or 0°.
        at_side = at_side or (is_polar and hulls[0][0] >= _SIDE_DEG)
        # A polar box holds every position short of 90° out, and so bounds those at it too.
        boxes.extend(polar_box_deg(*hulls) if is_polar else hulls)
        reaches.append(hulls[0] if is_polar else _eccentricities(*hulls))
    bound = 0.0 if at_side else _rectangles_apart(*boxes)
    if polar[0] or polar[1]:
        (a0, a1), (b0, b1) = reaches
        bound = max(bound, a0 - b1, b0 - a1)
    return bound, False


def _eccentricities(xs, ys) -> tuple[float, float]:
    """The least and greatest eccentricity of a per-axis rectangle: 0 where it holds straight
    ahead, else the angle from there to its nearest point (`_rectangles_apart`); and the
    farthest of its corners, a side at 90° being 90° out (the angle from straight ahead is
    convex over the hemisphere ahead, so it is greatest at a corner)."""
    least = _rectangles_apart((0.0, 0.0), (0.0, 0.0), xs, ys)
    return least, max(polar_of_deg(x, y)[0] for x in xs for y in ys)


def _exact(node, polar) -> float | None:
    """The least between two single pieces, in closed form: two rectangles; a point and anything;
    two polar sectors, and a polar sector short of the side and a rectangle, eccentricities not
    below 0 (`_parts` makes them so). `None` for a sector reaching 90° against a rectangle, or
    a polar point 90° out against one (`_SIDE_DEG`), which the boxes that hold them bound."""
    (a1,), (a2,), (b1,), (b2,) = node
    a = _point_of(a1, a2, polar[0])
    b = _point_of(b1, b2, polar[1])
    if a is not None and b is not None:
        return separation_deg(*a, *b)
    if not polar[0] and not polar[1]:
        return _rectangles_apart(a1, a2, b1, b2)
    if a is not None and polar[1] and b1[0] >= 0.0:
        return _to_sector(*a, b1, b2)
    if b is not None and polar[0] and a1[0] >= 0.0:
        return _to_sector(*b, a1, a2)
    if a is not None and not polar[1]:
        return _rectangles_apart((a[0], a[0]), (a[1], a[1]), b1, b2)
    if b is not None and not polar[0]:
        return _rectangles_apart(a1, a2, (b[0], b[0]), (b[1], b[1]))
    if polar[0] and polar[1] and a1[0] >= 0.0 and b1[0] >= 0.0:
        return _sectors_apart(a1, a2, b1, b2)
    if polar[0] and not polar[1] and 0.0 <= a1[0] and a1[1] < _SIDE_DEG:
        return _sector_to_rectangle(a1, a2, b1, b2)
    if polar[1] and not polar[0] and 0.0 <= b1[0] and b1[1] < _SIDE_DEG:
        return _sector_to_rectangle(b1, b2, a1, a2)
    return None


def _point_of(first, second, polar: bool) -> tuple[float, float] | None:
    """The per-axis position a piece is when both its intervals are single values, and per-axis
    degrees can say where it is: never a polar one 90° out (`_SIDE_DEG`)."""
    if first[0] != first[1] or second[0] != second[1]:
        return None
    if polar and abs(first[0]) >= _SIDE_DEG:
        return None
    return polar_deg(first[0], second[0]) if polar else (first[0], second[0])


def _unit(x: float, y: float) -> tuple[float, float, float]:
    """A per-axis position's direction, as `separation_deg` reads it (not of unit length)."""
    ax, ay = math.radians(x), math.radians(y)
    return (math.sin(ax) * math.cos(ay), math.cos(ax) * math.sin(ay), math.cos(ax) * math.cos(ay))


def _polar_unit(eccentricity: float, direction: float) -> tuple[float, float, float]:
    """A polar position's unit direction, `(sin e cos θ, sin e sin θ, cos e)`, which says where it
    is at 90° out too, where per-axis degrees cannot."""
    e, t = math.radians(eccentricity), math.radians(direction)
    return (math.sin(e) * math.cos(t), math.sin(e) * math.sin(t), math.cos(e))


def _angle(u, v) -> float:
    """The angle between two directions, in degrees: `atan2(|u × v|, u · v)`, as `separation_deg`."""
    across = math.hypot(u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2],
                        u[0] * v[1] - u[1] * v[0])
    return math.degrees(math.atan2(across, u[0] * v[0] + u[1] * v[1] + u[2] * v[2]))


def polar_of_deg(x: float, y: float) -> tuple[float, float]:
    """A per-axis position's eccentricity and direction, in degrees: `polar_deg`'s inverse, the
    direction in (-180°, 180°]."""
    ax, ay = math.radians(x), math.radians(y)
    ux = math.sin(ax) * math.cos(ay)
    uy = math.cos(ax) * math.sin(ay)
    uz = math.cos(ax) * math.cos(ay)
    return (math.degrees(math.atan2(math.hypot(ux, uy), uz)), math.degrees(math.atan2(uy, ux)))


def _to_sector(x: float, y: float, eccentricities, directions) -> float:
    """The least true visual angle from `(x, y)` to every position at an eccentricity from
    `eccentricities` (not below 0) and a direction from `directions`.

    Every position is at least as far from `(x, y)` as their eccentricities differ (the triangle
    on straight ahead), and along its own direction it is that far: so a point whose direction
    the sector holds is as far as its eccentricity is from the sector's. Any other is nearest a
    radial edge: along an arc at one eccentricity the angle only grows away from its direction."""
    eccentricity, direction = polar_of_deg(x, y)
    e0, e1 = eccentricities
    start, stop = directions
    if eccentricity == 0.0 or not stop - start < 360.0 or _holds(start, stop, direction):
        return max(0.0, e0 - eccentricity, eccentricity - e1)
    return min(_to_meridian(_unit(x, y), eccentricities, edge) for edge in (start, stop))


def _to_meridian(u, eccentricities, direction: float) -> float:
    """The least true visual angle from the direction `u` to the radial edge at `direction`,
    eccentricity over `eccentricities`: an arc of the great circle through straight ahead, along
    which the angle falls to the foot of the perpendicular and rises after, so the least is at
    the foot held to the edge's ends, or at an end. Each is measured by its direction
    (`_polar_unit`), so an edge reaching 90° out is measured where it is."""
    ux, uy, uz = u
    t = math.radians(direction)
    foot = math.degrees(math.atan2(ux * math.cos(t) + uy * math.sin(t), uz))
    e0, e1 = eccentricities
    return min(_angle(u, _polar_unit(e, direction)) for e in (e0, e1, min(max(foot, e0), e1)))


def _sector_to_rectangle(eccentricities, directions, xs, ys) -> float:
    """The least true visual angle between a polar sector (eccentricities not below 0, short of
    90°: `_SIDE_DEG`) and the rectangle `xs × ys`.

    The angle from a position to the sector has no positive minimum inside the rectangle (moving
    toward the sector lowers it), so the least is 0 where they meet and otherwise on the
    rectangle's edges, each an arc of a great circle. Cut each edge where it crosses the radial
    lines of the sector's two directions and at its foot from straight ahead: between the cuts
    a piece lies wholly in the sector's directions or wholly out of them, and along it the
    eccentricity only rises or only falls. In the directions, the angle to the sector is the
    eccentricity's distance from the sector's, so they meet where a piece's eccentricities reach
    the sector's, and otherwise the least is at a cut; out of them, it is the angle to a radial
    edge, two great-circle arcs, least at an end of one: a cut, or a corner of the sector, whose
    angle to the rectangle is exact (`_rectangles_apart`). Every cut is measured exactly
    (`_to_sector`)."""
    e0, e1 = eccentricities
    t0, t1 = directions
    every = not t1 - t0 < 360.0
    least = min(_rectangles_apart((x, x), (y, y), xs, ys)
                for x, y in (polar_deg(e, t) for e in (e0, e1) for t in (t0, t1)))
    for fixed, value, along in ((0, xs[0], ys), (0, xs[1], ys), (1, ys[0], xs), (1, ys[1], xs)):

        def at(v: float, fixed=fixed, value=value) -> tuple[float, float]:
            return (value, v) if fixed == 0 else (v, value)

        cuts = {along[0], along[1]}
        if along[0] < 0.0 < along[1]:
            cuts.add(0.0)
        if not every:
            cuts |= _crossings(fixed, value, along, (t0, t1))
        cuts = sorted(cuts)
        for v in cuts:
            least = min(least, _to_sector(*at(v), eccentricities, directions))
        for a, b in zip(cuts, cuts[1:]):
            middle, direction = polar_of_deg(*at((a + b) / 2.0))
            if every or middle == 0.0 or _holds(t0, t1, direction):
                ga, gb = polar_of_deg(*at(a))[0], polar_of_deg(*at(b))[0]
                if min(ga, gb) <= e1 and max(ga, gb) >= e0:
                    return 0.0
    return least


def _crossings(fixed: int, value: float, along, directions) -> set[float]:
    """Where the edge at `value` on axis `fixed` (0 across, 1 up), running over `along` on the
    other, crosses the radial line of each direction: where the edge's great circle meets the
    plane through straight ahead and that direction, on the direction's own side, ahead of the
    eye."""
    a = math.radians(value)
    m = (math.cos(a), 0.0, -math.sin(a)) if fixed == 0 else (0.0, math.cos(a), -math.sin(a))
    found: set[float] = set()
    for direction in directions:
        t = math.radians(direction)
        n = (-math.sin(t), math.cos(t), 0.0)
        w = (m[1] * n[2] - m[2] * n[1], m[2] * n[0] - m[0] * n[2], m[0] * n[1] - m[1] * n[0])
        for sign in (1.0, -1.0):
            vx, vy, vz = (sign * c for c in w)
            if vz <= 0.0 or vx * math.cos(t) + vy * math.sin(t) <= 0.0:
                continue
            v = math.degrees(math.atan2(vy if fixed == 0 else vx, vz))
            if along[0] <= v <= along[1]:
                found.add(v)
    return found


def _sectors_apart(eccentricities_a, directions_a, eccentricities_b, directions_b) -> float:
    """The least true visual angle between two polar sectors, eccentricities not below 0: as far
    as their eccentricities are apart where their directions meet; otherwise the angle between
    any two positions grows with the angle between their directions, so it is the least between
    the two radial edges that face each other across the narrower gap."""
    (a0, a1), (s0, s1) = eccentricities_a, directions_a
    (b0, b1), (t0, t1) = eccentricities_b, directions_b
    if (a0 == 0.0 and b0 == 0.0) or not (s1 - s0 < 360.0 and t1 - t0 < 360.0) or _holds(
            s0, s1, t0) or _holds(t0, t1, s0):
        return max(0.0, a0 - b1, b0 - a1)

    def gap(one: float, other: float) -> float:
        return (other - one) % 360.0

    # The narrower of the two gaps between the ranges, and the edges facing across it.
    if gap(s1, t0) <= gap(t1, s0):
        edge_a, edge_b = s1, t0
    else:
        edge_a, edge_b = s0, t1
    return min(
        min(_to_meridian(_polar_unit(e, edge_a), eccentricities_b, edge_b) for e in (a0, a1)),
        min(_to_meridian(_polar_unit(e, edge_b), eccentricities_a, edge_a) for e in (b0, b1)),
    )


def ring_spacing_deg(radius: float, n: float) -> float:
    """How far apart neighbors are among `n` objects spaced evenly on a true circle of `radius`
    degrees of visual angle, as `task.Array.positions` places an array's objects about its own
    direction (the PI, 2026-10-19, "True circle"): `2·asin(sin R·sin(π/n))`, the chord of the
    circle on the sphere, at any phase and wherever the array is. `n` without end gives 0; a
    negative `radius`, read by `check._crowded_arrays` as the least a range declares, gives a
    negative spacing, which no check reads as apart."""
    return math.degrees(2.0 * math.asin(math.sin(math.radians(radius)) * math.sin(math.pi / n)))


def on_circle_deg(x: float, y: float, radius: float, angle: float) -> tuple[float, float]:
    """The position `radius` degrees of true visual angle from `(x, y)`, `angle` degrees
    counter-clockwise from its local rightward axis: where `task.Array.positions` puts an
    array's object, an array about `(x, y)` being a true circle of visual angle about that
    direction (the PI, 2026-10-19, "True circle").

    **The local frame is the one a shape is drawn in** (`viewport.local_true_angle`): rightward
    is the screen's rightward axis brought onto the plane square to the center's direction, and
    upward is square to both, so an array's phase is read as a bar's orientation is. The object
    is `cos r·c + sin r·(cos θ·e_x + sin θ·e_y)`, as per-axis degrees, `atan2` of each axis
    against the axis ahead."""
    ax, ay = math.radians(x), math.radians(y)
    cx = math.sin(ax) * math.cos(ay)
    cy = math.cos(ax) * math.sin(ay)
    cz = math.cos(ax) * math.cos(ay)
    norm = math.sqrt(cx * cx + cy * cy + cz * cz)
    cx, cy, cz = cx / norm, cy / norm, cz / norm
    # Rightward: the screen's x axis less its share along the center's direction.
    ex, ey, ez = 1.0 - cx * cx, -cx * cy, -cx * cz
    norm = math.sqrt(ex * ex + ey * ey + ez * ez)
    ex, ey, ez = ex / norm, ey / norm, ez / norm
    # Upward: the center's direction crossed with rightward.
    ux, uy, uz = cy * ez - cz * ey, cz * ex - cx * ez, cx * ey - cy * ex
    r, t = math.radians(radius), math.radians(angle)
    along, across = math.cos(r), math.sin(r)
    vx = along * cx + across * (math.cos(t) * ex + math.sin(t) * ux)
    vy = along * cy + across * (math.cos(t) * ey + math.sin(t) * uy)
    vz = along * cz + across * (math.cos(t) * ez + math.sin(t) * uz)
    return (math.degrees(math.atan2(vx, vz)), math.degrees(math.atan2(vy, vz)))


def circle_extent_deg(x: float, y: float, radius: float) -> tuple[float, float]:
    """How far a true circle of `radius` degrees of visual angle about `(x, y)` reaches on each
    axis, either side of the center, in per-axis degrees: what check 8 holds an array's ring to.

    A per-axis `x` is the angle about the vertical axis, so the circle's leftmost and rightmost
    points are where planes through the vertical axis touch its cone: `asin(sin r / √(1 −
    c_y²))` either side of `x`, `c` the center's unit direction; and up and down `asin(sin r /
    √(1 − c_x²))` either side of `y`. Off the axes it reaches further than `r` across the way
    the center sits: about (20°, 10°), an 8° circle 8.50° up. A circle wide enough to hold an
    axis's pole reaches 90°."""
    ax, ay = math.radians(x), math.radians(y)
    cx = math.sin(ax) * math.cos(ay)
    cy = math.cos(ax) * math.sin(ay)
    cz = math.cos(ax) * math.cos(ay)
    norm2 = cx * cx + cy * cy + cz * cz
    reach = abs(math.sin(math.radians(radius)))

    def side(share: float) -> float:
        ratio = reach / math.sqrt(1.0 - share * share / norm2)
        return 90.0 if ratio >= 1.0 else math.degrees(math.asin(ratio))

    return (side(cy), side(cx))


def _to_side(value: float) -> float:
    return max(-_SIDE_DEG, min(_SIDE_DEG, float(value)))


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
