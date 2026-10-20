"""Display geometry, and the check that a stimulus can actually be shown.

The numbers come from S0 §5.2's formula and the optics drawing: the ASUS PG27UCDM's
published active area, 589.97 × 332.93 mm (ASUS spec page, read 2026-09-28), split into
two viewports. The screen is fixed 50 cm from the eyes in both setups (PI, 2026-09-28), so
the stereoscope's folded path is `D = Z + HW − E`: 63.15 cm at the drawing's `E` = 1.6 cm.

**Each property is asserted directly.** Before 2026-09-28 the four extents were covered
only by `tests/test_gaze.py` computing a constellation at import, so a mutation reached
the suite as a collection error rather than as a failed assertion.
"""

from __future__ import annotations

import ast
import math
import random
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from _rig import DIRECT, RIG as STAND_IN_RIG
from tasks.rig import RIG
from wl_xcon import geometry
from wl_xcon.geometry import (
    NOMINAL_HALF_IPD_CM,
    Geometry,
    SubjectSettings,
    least_separation_deg,
    polar_deg,
    ring_spacing_deg,
    separation_deg,
)

#: The PG27UCDM through the stereoscope, the screen at 50 cm, `E` = 1.6 cm
#: (S0 §5.1, §5.2; PI 2026-09-27, 2026-09-28).
STEREOSCOPE = Geometry.stereoscope(
    panel_width_cm=58.997, panel_height_cm=33.293, screen_distance_cm=50.0, half_ipd_cm=1.6
)


def test_each_viewport_is_a_quarter_of_the_width_and_half_the_height():
    """The panel is split down the middle: each eye's viewport is half the active
    width and all of its height, so its half-extents are W/4 and H/2."""
    assert STEREOSCOPE.half_width_cm == pytest.approx(14.749, abs=0.001)
    assert STEREOSCOPE.half_height_cm == pytest.approx(16.647, abs=0.001)


def test_the_extents_come_from_the_active_area_not_a_diagonal():
    """ASUS's active area is not exactly 16:9 (1.772:1), and its "26.5-inch viewable"
    is rounded. Width and height are each their own input, so changing one must not
    move the other."""
    wider = Geometry(panel_width_cm=60.0, panel_height_cm=33.293, viewing_distance_cm=63.0)

    assert wider.half_width_cm == pytest.approx(15.0)
    assert wider.half_height_cm == pytest.approx(STEREOSCOPE.half_height_cm)


def test_the_stereoscope_path_is_the_screen_distance_plus_the_lateral_run():
    """The periscope carries each eye's axis from x = ∓E out to its viewport's center at
    ∓W/4, and that run is optical path the screen's physical distance does not show:
    `D = Z + W/4 − E`."""
    assert STEREOSCOPE.viewing_distance_cm == pytest.approx(63.149, abs=0.001)

    other = Geometry.stereoscope(
        panel_width_cm=60.0, panel_height_cm=30.0, screen_distance_cm=40.0, half_ipd_cm=2.0
    )
    assert other.viewing_distance_cm == pytest.approx(53.0)
    assert other.panel_width_cm == 60.0
    assert other.panel_height_cm == 30.0


def test_the_path_is_per_animal_because_the_screen_is_fixed():
    """With the screen fixed, wider-set eyes need less lateral run, so the path is
    shorter and the field wider: IPD 30-38 mm spans 63.25-62.85 cm."""
    narrow = Geometry.stereoscope(
        panel_width_cm=58.997, panel_height_cm=33.293, screen_distance_cm=50.0, half_ipd_cm=1.5
    )
    wide = Geometry.stereoscope(
        panel_width_cm=58.997, panel_height_cm=33.293, screen_distance_cm=50.0, half_ipd_cm=1.9
    )

    assert narrow.viewing_distance_cm == pytest.approx(63.249, abs=0.001)
    assert wide.viewing_distance_cm == pytest.approx(62.849, abs=0.001)
    assert narrow.half_field_h_deg == pytest.approx(13.126, abs=0.001)
    assert wide.half_field_h_deg == pytest.approx(13.207, abs=0.001)


def test_field_matches_the_optics_drawing():
    """If this drifts from `2026-08-31-stereoscope-optics-drawing.md` §3, one of
    the two is wrong and the rig will be built to whichever nobody checked."""
    assert STEREOSCOPE.half_field_h_deg == pytest.approx(13.146, abs=0.001)
    assert STEREOSCOPE.half_field_v_deg == pytest.approx(14.768, abs=0.001)


def test_pixels_per_degree_matches_the_optics_drawing():
    """S0 §5.2's mean over the viewport: 1920 px across 2 × 13.15°."""
    assert STEREOSCOPE.pixels_per_degree(horizontal_pixels=1920) == pytest.approx(
        73.02, abs=0.005
    )


def test_the_field_meets_the_stereoscope_requirement():
    """PI, 2026-09-27: "for the stereoscope setup +/- 10 deg is enough". Every corner
    of a ±10° square must be showable."""
    for x in (-10.0, 10.0):
        for y in (-10.0, 10.0):
            assert STEREOSCOPE.can_show(x, y)


def test_the_mask_fits_inside_the_field_for_every_ipd():
    """The PI's removable mask at the panel starts at ±12° (2026-09-28). The field it
    stops must be at least that wide for every IPD the drawing tabulates, or the mask
    stops nothing on one side."""
    for half_ipd_cm in (1.5, 1.6, 1.9):
        field = Geometry.stereoscope(
            panel_width_cm=58.997,
            panel_height_cm=33.293,
            screen_distance_cm=50.0,
            half_ipd_cm=half_ipd_cm,
        )
        for x in (-12.0, 12.0):
            for y in (-12.0, 12.0):
                assert field.can_show(x, y)


def test_a_position_outside_the_field_is_not_showable():
    """A model asked for a peripheral target will happily write 30 degrees. The
    stimulus would be drawn off the panel, the animal would never see it, and the
    trial would score as a miss that looks like behaviour."""
    assert STEREOSCOPE.can_show(10.0, 5.0)
    assert not STEREOSCOPE.can_show(30.0, 0.0)
    assert not STEREOSCOPE.can_show(0.0, 25.0)


def test_the_field_edge_is_where_the_drawing_puts_it():
    """±13.5°, the reference tasks' bound for the screen at 43.85 cm, is outside the
    field with the screen at 50 cm."""
    assert STEREOSCOPE.can_show(13.14, 0.0)
    assert STEREOSCOPE.can_show(-13.14, 0.0)
    assert not STEREOSCOPE.can_show(13.16, 0.0)
    assert not STEREOSCOPE.can_show(-13.16, 0.0)
    assert not STEREOSCOPE.can_show(13.5, 0.0)
    assert STEREOSCOPE.can_show(0.0, 14.76)
    assert STEREOSCOPE.can_show(0.0, -14.76)
    assert not STEREOSCOPE.can_show(0.0, 14.78)
    assert not STEREOSCOPE.can_show(0.0, -14.78)


# ---------------------------------------------------------------------------
# Direct view, and the stereoscope's mask (direct-view spec §2, §4)
# ---------------------------------------------------------------------------

#: **Stand-ins for the light sensors' housings, not a measurement**: the real ones are
#: measured at build (direct-view spec §9 item 1). One per bottom corner, 4 × 3 cm with
#: a 0.5 cm margin, in cm from the active area's bottom-left corner.
HOUSINGS = STAND_IN_RIG.housings

#: The same screen through the stereoscope at `E` = 1.6 cm, stopped by the PI's ±12° mask.
MASKED = Geometry.stereoscope(
    58.997, 33.293, screen_distance_cm=50.0, half_ipd_cm=1.6, mask_deg=12.0
)


def test_direct_view_is_the_whole_panel_at_the_screens_own_distance():
    """No periscope, so no lateral run: the path is `Z`, and the viewport is the whole
    panel, seen by both eyes."""
    assert DIRECT.view == "direct"
    assert DIRECT.viewing_distance_cm == 50.0
    assert DIRECT.half_width_cm == pytest.approx(29.4985)
    assert DIRECT.half_height_cm == pytest.approx(16.6465)


def test_direct_views_field_is_the_spec_tables():
    """The direct-view spec §2's table: ±30.5° × ±18.4° at `Z` = 50 cm."""
    assert DIRECT.half_field_h_deg == pytest.approx(30.539, abs=0.001)
    assert DIRECT.half_field_v_deg == pytest.approx(18.414, abs=0.001)


def test_pixels_per_degree_in_direct_view_are_across_the_whole_panel():
    """S0 §5.2's mean, with the viewport the whole panel: 3840 px across 2 × 30.54°.
    (The spec's 56.8 is the center's, a different statistic.)"""
    assert DIRECT.pixels_per_degree(horizontal_pixels=3840) == pytest.approx(
        62.87, abs=0.005
    )


def test_direct_view_refuses_to_exist_without_the_housings():
    """A missing measurement is not an absent housing. A direct-view field with no
    exclusions would pass a stimulus drawn under a sensor, so it is refused, by either
    road to it, naming what is missing."""
    with pytest.raises(ValueError, match="§9 item 1"):
        Geometry.direct(58.997, 33.293, screen_distance_cm=50.0, housings=())
    with pytest.raises(ValueError, match="housings"):
        Geometry(panel_width_cm=58.997, panel_height_cm=33.293, viewing_distance_cm=50.0,
                 view="direct")


def test_a_setup_that_is_neither_is_refused():
    """`view="stereo"` is not a setup. Read as one or the other it would compute a
    field for a screen nobody has."""
    with pytest.raises(ValueError, match="'stereo' is not a setup"):
        Geometry(panel_width_cm=58.997, panel_height_cm=33.293, viewing_distance_cm=50.0,
                 view="stereo")


# ---------------------------------------------------------------------------
# M5: a typo in a housing, or a housing/mask on the wrong setup, fails open
# ---------------------------------------------------------------------------


def test_a_housing_with_left_not_less_than_right_is_refused():
    """`left >= right` is a rectangle that covers nothing on the panel, so `covers`
    would never be true and a stimulus under the real housing would pass."""
    with pytest.raises(ValueError, match="left"):
        replace(HOUSINGS[0], left_cm=4.0, right_cm=4.0)
    with pytest.raises(ValueError, match="left"):
        replace(HOUSINGS[0], left_cm=5.0, right_cm=4.0)


def test_a_housing_with_bottom_not_less_than_top_is_refused():
    """The same failure, the other axis."""
    with pytest.raises(ValueError, match="top"):
        replace(HOUSINGS[0], bottom_cm=3.0, top_cm=3.0)
    with pytest.raises(ValueError, match="top"):
        replace(HOUSINGS[0], bottom_cm=4.0, top_cm=3.0)


def test_a_housing_with_a_negative_margin_is_refused():
    """A negative margin would shrink the excluded rectangle instead of widening it,
    which is not what `margin_cm` is for (direct-view spec §4)."""
    with pytest.raises(ValueError, match="margin"):
        replace(HOUSINGS[0], margin_cm=-0.5)


def test_a_housing_with_a_non_finite_value_is_refused():
    """NaN and infinity satisfy no useful `<`/`>=` comparison, so `covers` on a
    non-finite housing would either cover the whole panel or nothing, silently."""
    with pytest.raises(ValueError, match="finite"):
        replace(HOUSINGS[0], right_cm=math.inf)
    with pytest.raises(ValueError, match="finite"):
        replace(HOUSINGS[0], margin_cm=math.nan)


def test_a_stereoscope_geometry_refuses_housings():
    """The mask hides the light sensors through the stereoscope; housings on a
    stereoscope geometry would exclude degrees the mask already stops, for the wrong
    reason, and were never meant to be checked there."""
    with pytest.raises(ValueError, match="housings"):
        Geometry(
            panel_width_cm=58.997,
            panel_height_cm=33.293,
            viewing_distance_cm=63.149,
            view="stereoscope",
            housings=HOUSINGS,
        )


def test_a_direct_geometry_refuses_a_mask():
    """Direct view has no mask -- only the stereoscope's removable one stops the
    field. A `mask_deg` on a direct geometry silently narrowed the field to a value
    nothing at the rig sets (review M5: `mask_deg=10` gave a 10° field)."""
    with pytest.raises(ValueError, match="mask"):
        Geometry(
            panel_width_cm=58.997,
            panel_height_cm=33.293,
            viewing_distance_cm=50.0,
            view="direct",
            mask_deg=10.0,
            housings=HOUSINGS,
        )


def test_a_stimulus_under_a_housing_cannot_be_shown():
    """Direct-view spec §4: check 8 refuses a stimulus that could overlap a housing,
    exactly as it refuses one off the panel. Both bottom corners here, since which
    corner the sensors take is a build finding."""
    assert not DIRECT.can_show(-29.0, -17.0)
    assert not DIRECT.can_show(29.0, -17.0)
    assert DIRECT.can_show(-29.0, 0.0), "the side of the panel, above the housing"
    assert DIRECT.can_show(0.0, -18.0), "the bottom of the panel, between them"
    assert DIRECT.can_show(16.0, 0.0)
    assert not DIRECT.can_show(31.0, 0.0), "off the panel"
    assert not DIRECT.can_show(0.0, 18.5), "off the panel"


def test_a_housings_margin_is_part_of_it():
    """The margin is recorded beside each rectangle and widens it on every side.
    4.5 cm in from the left edge is 26.565° left of center at 50 cm; 3.5 cm up from
    the bottom is 14.731° below it."""
    housing = HOUSINGS[0]
    assert housing.covers(4.5, 1.0) and not housing.covers(4.51, 1.0)
    assert housing.covers(-0.5, 1.0) and not housing.covers(-0.51, 1.0)
    assert housing.covers(2.0, 3.5) and not housing.covers(2.0, 3.51)
    assert housing.covers(2.0, -0.5) and not housing.covers(2.0, -0.51)

    assert not DIRECT.can_show(-26.6, -16.0)
    assert DIRECT.can_show(-26.5, -16.0)
    assert not DIRECT.can_show(-29.0, -14.8)
    assert DIRECT.can_show(-29.0, -14.6)


def test_the_mask_is_the_stereoscopes_field():
    """The PI's removable mask at the panel, ±12° to start (2026-09-28): inside the
    viewport's ±13.15° × ±14.77°, so it sets both edges."""
    assert MASKED.half_field_h_deg == 12.0
    assert MASKED.half_field_v_deg == 12.0
    assert MASKED.can_show(11.99, -11.99)
    assert not MASKED.can_show(12.01, 0.0)
    assert not MASKED.can_show(0.0, -12.01)


def test_a_mask_wider_than_the_viewport_stops_nothing():
    """The mask can only narrow the field. One cut wider than the viewport leaves the
    viewport's own edge, which is where the mirrors end."""
    wide = Geometry.stereoscope(
        58.997, 33.293, screen_distance_cm=50.0, half_ipd_cm=1.6, mask_deg=20.0
    )
    assert wide.half_field_h_deg == pytest.approx(13.146, abs=0.001)
    assert wide.half_field_v_deg == pytest.approx(14.768, abs=0.001)


def test_the_mask_covers_pixels_and_does_not_rescale_them():
    """Pixels per degree are the viewport's: the mask hides the edge, it does not
    change what one pixel subtends."""
    assert MASKED.pixels_per_degree(horizontal_pixels=1920) == pytest.approx(
        STEREOSCOPE.pixels_per_degree(horizontal_pixels=1920)
    )
    assert MASKED.pixels_per_degree(horizontal_pixels=1920) == pytest.approx(73.02, abs=0.005)


# ---------------------------------------------------------------------------
# The rig's settings (direct-view spec §2), `tasks/rig.py`
# ---------------------------------------------------------------------------


def test_the_rigs_settings_are_its_screen_its_distance_and_its_mask():
    """"The rig's settings hold everything the geometry needs": the PG27UCDM's
    published active area, `Z` = 50 cm in both setups, and the mask at ±12° (PI,
    2026-09-28)."""
    assert (RIG.panel_width_cm, RIG.panel_height_cm) == (58.997, 33.293)
    assert RIG.screen_distance_cm == 50.0
    assert RIG.mask_deg == 12.0


def test_the_rigs_housings_are_unmeasured_so_direct_view_refuses_on_its_settings():
    """NOT YET MEASURED (direct-view spec §9 item 1), and this pins it: when the
    housings are written into `tasks/rig.py`, this fails, and is replaced by a test of
    the measured rectangles. Until then no task passes direct view on this rig."""
    assert RIG.housings == ()
    with pytest.raises(ValueError, match="§9 item 1"):
        RIG.direct()


def test_the_rig_gives_direct_view_the_panel_at_z_and_its_housings():
    assert replace(RIG, housings=HOUSINGS).direct() == DIRECT


def test_the_rig_gives_the_stereoscope_its_mask_and_the_subjects_path():
    """`E` comes from the subject's record (spec §2), so the stereoscope's field is
    built per subject; the mask is the rig's and stops it at every IPD the drawing
    tabulates."""
    assert RIG.stereoscope(half_ipd_cm=1.6) == MASKED
    assert RIG.stereoscope(half_ipd_cm=1.9).viewing_distance_cm == pytest.approx(
        62.849, abs=0.001
    )
    for half_ipd_cm in (1.5, 1.6, 1.9):
        field = RIG.stereoscope(half_ipd_cm=half_ipd_cm)
        assert (field.half_field_h_deg, field.half_field_v_deg) == (12.0, 12.0)


def test_subject_settings_refuse_a_blank_subject_or_an_impossible_half_ipd():
    """One animal's settings, from the file named at session start (PI, 2026-09-29).
    A blank subject could match nothing it is checked against, and a half-IPD that
    is not a positive number is not a distance."""
    assert SubjectSettings(subject="A", half_ipd_cm=1.6).half_ipd_cm == 1.6
    for subject, half in (("", 1.6), ("A", 0.0), ("A", -1.6), ("A", float("nan"))):
        with pytest.raises(ValueError):
            SubjectSettings(subject=subject, half_ipd_cm=half)


def test_subject_settings_refuse_a_half_ipd_that_is_not_a_number():
    """`None` is the natural placeholder while an animal's half-IPD is unmeasured
    (XC-082): it is refused in a sentence, not left as a `TypeError`. A `bool` is an
    `int` and would otherwise pass as 1 cm."""
    for half in (None, "1.6", True):
        with pytest.raises(ValueError, match="not a half-IPD"):
            SubjectSettings(subject="A", half_ipd_cm=half)


def test_the_stereoscope_builds_any_half_ipd_its_optics_extend_to():
    """The optics drawing tabulates IPD 30-38 mm (S0 §7.1.3), so the rig is drawn for half-IPDs
    1.5-1.9 cm. Outside that, the mirrors and the field are extrapolated: a warning
    (`warnlist.of_setup`; the PI, 2026-10-11, XC-352's C7), never a refusal. A half-IPD that
    leaves no positive optical path, or is no number, has no field, and is refused."""
    assert RIG.half_ipd_range_cm == (1.5, 1.9)
    for half in (1.49, 1.91, 3.0):
        assert RIG.stereoscope(half_ipd_cm=half).half_ipd_cm == half
    for half in (100.0, float("nan")):
        with pytest.raises(ValueError, match="no positive optical path"):
            RIG.stereoscope(half_ipd_cm=half)
    assert NOMINAL_HALF_IPD_CM == 1.6


def test_a_geometry_carries_the_half_ipd_it_was_built_for():
    """The record and telemetry read the animal's half-IPD from the field it built,
    not from a second copy. Direct view has none, and refuses one."""
    assert RIG.stereoscope(half_ipd_cm=1.6).half_ipd_cm == 1.6
    assert DIRECT.half_ipd_cm is None
    with pytest.raises(ValueError, match="direct view has no half-IPD"):
        replace(DIRECT, half_ipd_cm=1.6)


def test_the_reference_subject_is_the_reference_bounds_subject():
    """So the reference settings can never quietly become a real animal's."""
    from tasks.reference_bounds import BOUNDS
    from tasks.reference_subject import SETTINGS

    assert SETTINGS.subject == BOUNDS.subject == "REFERENCE"


def test_the_vergence_offset_is_atan_e_over_d_per_eye_and_none_in_direct_view():
    stereo = RIG.stereoscope(half_ipd_cm=1.6)
    assert stereo.vergence_half_deg == pytest.approx(
        math.degrees(math.atan(1.6 / stereo.viewing_distance_cm)))
    assert 2 * stereo.vergence_half_deg == pytest.approx(2.9, abs=0.01)  # optics drawing §6
    assert DIRECT.vergence_half_deg == 0.0


def test_a_stereoscope_with_no_half_ipd_has_no_vergence_offset_to_give():
    bare = Geometry(panel_width_cm=58.997, panel_height_cm=33.293, viewing_distance_cm=63.15)
    with pytest.raises(ValueError, match="half-IPD"):
        bare.vergence_half_deg


# --- Angles at the eye, measured where they are (the PI, 2026-10-19) -------------------------
#
# "We should be careful that when a stimulus is presented at a specific position and size, that
# it is forward calculated for that specific location rather than using ppd averages." Every
# expectation below is computed from directions, `D · tan` per axis (`viewport.center`), by an
# arithmetic of its own: numpy's dot products, never `geometry`'s cross product.


def _directions(points) -> np.ndarray:
    t = np.array([[math.tan(math.radians(x)), math.tan(math.radians(y)), 1.0] for x, y in points])
    return t / np.linalg.norm(t, axis=1, keepdims=True)


def _least_by_dots(ps, qs) -> float:
    """The least angle between any of `ps` and any of `qs`, by the largest dot product."""
    dots = np.clip(_directions(ps) @ _directions(qs).T, -1.0, 1.0)
    return math.degrees(math.acos(dots.max()))


def test_separation_is_the_angle_at_the_eye_between_two_positions():
    """Seeded, over ±40° on each axis: `separation_deg` is the angle between the two positions'
    directions, the same either way round; along the horizontal meridian and the vertical one,
    which are great circles, it is the difference in degrees."""
    rng = random.Random(20261019)
    for _ in range(500):
        p = (rng.uniform(-40.0, 40.0), rng.uniform(-40.0, 40.0))
        q = (rng.uniform(-40.0, 40.0), rng.uniform(-40.0, 40.0))
        expected = _least_by_dots([p], [q])
        if expected < 0.5:
            continue  # `acos` loses digits near 0°; the next test covers small angles
        assert separation_deg(*p, *q) == pytest.approx(expected, abs=1e-9)
        assert separation_deg(*q, *p) == pytest.approx(separation_deg(*p, *q), abs=1e-12)
    assert separation_deg(-13.0, 0.0, 27.5, 0.0) == pytest.approx(40.5, abs=1e-12)
    assert separation_deg(0.0, 18.0, 0.0, -6.25) == pytest.approx(24.25, abs=1e-12)


def test_separation_keeps_its_digits_at_small_angles():
    """`atan2(|u × v|, u · v)` rather than `acos(u · v)`: 1e-6° from (20°, 20°), built from the
    direction, reads 1e-6° to six significant figures, where `acos` of the dot product can read
    only 0, 0.854e-6°, 1.207e-6° and so on, a float's steps below 1, and reads this one as
    0.854e-6°."""
    c = _directions([(20.0, 20.0)])[0]
    up = np.cross(c, np.cross(np.array([0.0, 1.0, 0.0]), c))
    up /= np.linalg.norm(up)
    a = math.radians(1e-6)
    d = math.cos(a) * c + math.sin(a) * up
    q = (math.degrees(math.atan2(d[0], d[2])), math.degrees(math.atan2(d[1], d[2])))

    assert separation_deg(20.0, 20.0, *q) == pytest.approx(1e-6, rel=1e-6)


def test_a_position_past_90_degrees_continues_past_the_side_rather_than_wrapping():
    """No screen shows a position past 90° on an axis, but a broken gaze map can report one: it
    is 10° on from 85°, where `tan`'s period would put it on the far side of the field."""
    assert separation_deg(85.0, 0.0, 95.0, 0.0) == pytest.approx(10.0, abs=1e-9)
    assert separation_deg(-85.0, 0.0, 95.0, 0.0) > 90.0


@pytest.mark.parametrize("pairwise", [True, False], ids=["numpy pairwise", "best-first search"])
def test_the_least_separation_between_sets_of_points_is_the_least_over_every_pair(
        pairwise, monkeypatch):
    """Seeded: windows placed by choices on each axis, 1-6 an axis, anywhere in ±30°: by numpy's
    pairwise dot products, as such regions are measured, and by the best-first search, which
    takes them past `_PAIRWISE_LIMIT` pairs (the review of the first commit's item 4)."""
    if not pairwise:
        monkeypatch.setattr(geometry, "_PAIRWISE_LIMIT", 0)
    rng = random.Random(7)
    for _ in range(200):
        sides = [sorted(rng.uniform(-30.0, 30.0) for _ in range(rng.randint(1, 6)))
                 for _ in range(4)]
        a = [(x, y) for x in sides[0] for y in sides[1]]
        b = [(x, y) for x in sides[2] for y in sides[3]]
        found = least_separation_deg(*([(v, v) for v in side] for side in sides))
        assert found == pytest.approx(_least_by_dots(a, b), abs=1e-7)



def test_regions_of_choices_on_one_axis_and_a_range_on_the_other_are_searched_exactly():
    """A window at one of five heights over a range across, and one at one of four places across
    over a range of heights: no closed form for the pair, so the search splits their lists of
    intervals; it finds the least a fine sweep of both finds, and never more."""
    xs_a, ys_a = [(-12.0, -2.0)], [(v, v) for v in (-9.0, -4.0, 1.5, 6.0, 11.0)]
    xs_b, ys_b = [(v, v) for v in (3.0, 7.5, 14.0, 21.0)], [(-6.0, 9.0)]
    a = [(x, y) for x in np.linspace(*xs_a[0], 401) for y, _ in ys_a]
    b = [(x, y) for x, _ in xs_b for y in np.linspace(*ys_b[0], 601)]
    swept = min(_least_by_dots(a, b[k::5]) for k in range(5))

    found = least_separation_deg(xs_a, ys_a, xs_b, ys_b)

    assert swept - 1e-3 <= found <= swept + 1e-9

@pytest.mark.parametrize("seed", range(12))
def test_the_least_separation_to_a_range_is_never_more_than_any_point_in_it_reaches(seed):
    """A window at a point, another anywhere over a range on each axis, 2-20° wide, both in ±30°:
    the least is no more than the least over an 801 × 801 grid of the range (never overstated,
    which would pass a pair that can overlap), and no less than that grid's least by more than
    its spacing allows: where the least lies along an edge the grid's error is second order in
    its spacing, and a point inside the range is 0° from it."""
    rng = random.Random(seed)
    p = (rng.uniform(-30.0, 30.0), rng.uniform(-30.0, 30.0))
    x0, y0 = rng.uniform(-30.0, 10.0), rng.uniform(-30.0, 10.0)
    xs, ys = (x0, x0 + rng.uniform(2.0, 20.0)), (y0, y0 + rng.uniform(2.0, 20.0))
    tx, ty = (np.tan(np.radians(np.linspace(*side, 801))) for side in (xs, ys))
    grid = np.stack(np.broadcast_arrays(tx[:, None], ty[None, :], 1.0), axis=-1).reshape(-1, 3)
    grid = grid / np.linalg.norm(grid, axis=1, keepdims=True)
    swept = math.degrees(math.acos(min(1.0, float((grid @ _directions([p])[0]).max()))))

    found = least_separation_deg([(p[0], p[0])], [(p[1], p[1])], [xs], [ys])

    if xs[0] <= p[0] <= xs[1] and ys[0] <= p[1] <= ys[1]:
        assert found == 0.0
    else:
        half_step = 1.1 * max(xs[1] - xs[0], ys[1] - ys[0]) / 800 / 2
        assert swept - half_step ** 2 / (2 * found) - 1e-9 <= found <= swept + 1e-9


def test_two_ranges_are_as_far_apart_as_a_corner_of_either_and_the_others_edge():
    """A window anywhere over x 0-10°, y 0-1°, and another over x 4-5°, y 3-4°: the nearest pair
    is the second's lower corners and the first's top edge, so a search from one region's
    corners alone reads them about 4.5° apart, and it is the same either way round. The least of
    a 4001-point grid along that top edge from each lower corner is the least the two can
    reach: along the second's lower edge the angle to the first's falls toward the side of the
    field, where the two edges' great circles meet."""
    edge = [(x, 1.0) for x in np.linspace(0.0, 10.0, 4001)]
    swept = min(_least_by_dots([corner], edge) for corner in ((4.0, 3.0), (5.0, 3.0)))

    one_way = least_separation_deg([(0.0, 10.0)], [(0.0, 1.0)], [(4.0, 5.0)], [(3.0, 4.0)])
    other_way = least_separation_deg([(4.0, 5.0)], [(3.0, 4.0)], [(0.0, 10.0)], [(0.0, 1.0)])

    assert one_way == other_way
    assert swept - 1e-5 <= one_way <= swept + 1e-9


def test_regions_that_share_a_position_are_0_apart_and_a_side_without_end_reaches_90():
    """Overlapping regions are 0° apart. A side a range leaves without end is read to 90°, where
    a degree stops naming a direction ahead of the eye: a window anywhere from x 4° outward is 4°
    from one at the center, and two that both run outward at heights 5° and -5° meet out there,
    where every height on that axis is one direction."""
    assert least_separation_deg([(-5.0, 5.0)], [(0.0, 3.0)], [(4.0, 9.0)], [(2.0, 2.0)]) == 0.0
    assert least_separation_deg([(4.0, math.inf)], [(0.0, 0.0)], [(0.0, 0.0)], [(0.0, 0.0)]) == (
        pytest.approx(4.0, abs=1e-9))
    assert least_separation_deg([(0.0, math.inf)], [(5.0, 5.0)], [(0.0, math.inf)],
                                [(-5.0, -5.0)]) == pytest.approx(0.0, abs=1e-9)


def _true_circle(center, radius: float, thetas) -> np.ndarray:
    """Directions `radius`° of visual angle from `center`, at each angle in `thetas` (degrees)
    counter-clockwise from its local rightward axis, the frame `viewport.local_true_angle` uses:
    built here from the frame's definition, not from `geometry`."""
    c = _directions([center])[0]
    ex = np.array([1.0, 0.0, 0.0]) - c[0] * c
    ex /= np.linalg.norm(ex)
    ey = np.cross(c, ex)
    t = np.radians(np.asarray(thetas, dtype=float))[:, None]
    r = math.radians(radius)
    return math.cos(r) * c + math.sin(r) * (np.cos(t) * ex + np.sin(t) * ey)


def _degrees_of(v: np.ndarray) -> np.ndarray:
    return np.degrees(np.stack([np.arctan2(v[:, 0], v[:, 2]), np.arctan2(v[:, 1], v[:, 2])], axis=1))


def test_a_true_circles_neighbors_are_2_asin_sin_r_sin_pi_over_n_apart():
    """`ring_spacing_deg`: an array's objects sit on a true circle about its own direction (the PI,
    2026-10-19, "True circle"), so neighbors are `2·asin(sin R·sin(π/n))` apart at any phase and
    wherever the array is: twelve on a 20° ring 10.16°, where per axis they were 10.35° apart and
    9.77° where that ring crossed an axis."""
    for center in ((0.0, 0.0), (10.0, 5.0), (25.0, -15.0)):
        for radius in (1.0, 5.0, 12.0, 20.0):
            for n in (2, 3, 5, 12, 64):
                ring = _degrees_of(_true_circle(center, radius, 17.0 + 360.0 * np.arange(n) / n))
                apart = [_least_by_dots([tuple(p)], [tuple(q)])
                         for p, q in zip(ring, np.roll(ring, -1, axis=0))]
                assert apart == pytest.approx([ring_spacing_deg(radius, n)] * n, abs=1e-7)

    assert ring_spacing_deg(20.0, 12) == pytest.approx(10.1571, abs=1e-4)
    assert ring_spacing_deg(8.0, math.inf) == 0.0


def test_a_position_on_a_circle_is_its_radius_away_at_its_angle_in_the_local_frame():
    """`on_circle_deg(x, y, r, θ)`: the position `r`° of visual angle from `(x, y)`, `θ` degrees
    counter-clockwise from its local rightward axis, which `task.Array.positions` places an
    array's objects with."""
    from wl_xcon.geometry import on_circle_deg

    for center in ((0.0, 0.0), (10.0, 5.0), (-20.0, 20.0)):
        thetas = np.arange(0.0, 360.0, 15.0)
        expected = _degrees_of(_true_circle(center, 7.5, thetas))
        found = np.array([on_circle_deg(*center, 7.5, theta) for theta in thetas])
        assert found == pytest.approx(expected, abs=1e-9)


@pytest.mark.parametrize("center", [(0.0, 0.0), (20.0, 10.0), (-25.0, 15.0), (12.0, -18.0)])
def test_a_true_circles_reach_on_each_axis_is_its_bounding_box(center):
    """`circle_extent_deg(x, y, r)`: how far a true circle of `r`° about `(x, y)` reaches on each
    axis, in per-axis degrees, either side (check 8 tests the box's corners against the field):
    `asin(sin r / √(1 − c_y²))` across and `asin(sin r / √(1 − c_x²))` up, `c` the center's unit
    direction. No point of the circle, at a tenth of a degree's steps, lies beyond it, and the
    farthest comes within that step's error of it."""
    from wl_xcon.geometry import circle_extent_deg

    ring = _degrees_of(_true_circle(center, 8.0, np.arange(0.0, 360.0, 0.1)))
    reach = np.abs(ring - np.array(center)).max(axis=0)

    across, up = circle_extent_deg(*center, 8.0)

    assert reach[0] <= across + 1e-9 and reach[1] <= up + 1e-9
    assert (across, up) == pytest.approx(tuple(reach), abs=1e-5)


def test_the_mean_pixels_per_degree_reaches_no_drawing_window_or_check():
    """`Geometry.pixels_per_degree` is S0 §5.2's reported mean, and a mean is what the PI ruled
    out of every position, size and window (2026-10-19). Nothing in `wl_xcon/` names it, as an
    attribute, a name, an import or a string, but its own definition; asked of the parser, so
    a comment or a docstring that mentions it is not a use."""
    root = Path(geometry.__file__).parent
    named = []
    for path in sorted(root.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if ((isinstance(node, ast.Attribute) and node.attr == "pixels_per_degree")
                    or (isinstance(node, ast.Name) and node.id == "pixels_per_degree")
                    or (isinstance(node, ast.alias) and node.name == "pixels_per_degree")
                    or (isinstance(node, ast.Constant) and node.value == "pixels_per_degree")):
                named.append(f"{path.relative_to(root)}:{node.lineno}")

    assert named == []
    assert hasattr(Geometry, "pixels_per_degree")


# --- A position written as its eccentricity and direction (the PI, 2026-10-19) ----------------


def test_a_polar_position_is_its_direction_as_per_axis_degrees():
    """`polar_deg(e, θ)`: the direction `(sin e cos θ, sin e sin θ, cos e)`, as per-axis degrees,
    `atan(tan e cos θ)` across and `atan(tan e sin θ)` up, θ in the math convention (0° right,
    counter-clockwise positive, +y up; engine spec §5.1). (8 cos 45°, 8 sin 45°) per axis is
    7.975° out; the polar position is 8°."""
    for e in (0.0, 0.5, 8.0, 20.0, 45.0, 89.0):
        for theta in (0.0, 30.0, 45.0, 90.0, 135.0, 200.0, -60.0):
            x, y = polar_deg(e, theta)
            t, c, s = math.tan(math.radians(e)), math.cos(math.radians(theta)), math.sin(
                math.radians(theta))
            assert (x, y) == pytest.approx(
                (math.degrees(math.atan(t * c)), math.degrees(math.atan(t * s))), abs=1e-9)
            assert _least_by_dots([(0.0, 0.0)], [(x, y)]) == pytest.approx(e, abs=1e-6)
    assert polar_deg(8.0, 45.0) == pytest.approx((5.6753, 5.6753), abs=1e-4)
    assert _least_by_dots([(0.0, 0.0)], [(8 * math.cos(math.pi / 4), 8 * math.sin(math.pi / 4))]) \
        == pytest.approx(7.975, abs=1e-3)


def test_a_polar_position_past_90_degrees_is_past_the_side_never_wrapped_onto_the_field():
    """No screen shows a position 90° or more out, but a setting can reach one: past 90° `atan(tan
    e cos θ)` would wrap it onto the far side of the field, where check 8 would pass it. Here it
    stays its own direction as `separation_deg` reads per-axis degrees, `e` from straight ahead,
    and past the side on the axis it leans along, so no field can show it."""
    for e in (90.0, 100.0, 135.0, 170.0, 179.0):
        for theta in (0.0, 20.0, 45.0, 90.0, 160.0, 180.0, 250.0, -45.0):
            x, y = polar_deg(e, theta)
            assert separation_deg(0.0, 0.0, x, y) == pytest.approx(e, abs=1e-6)
            assert max(abs(x), abs(y)) >= 90.0 - 1e-9
            assert not DIRECT.can_show(x, y)


@pytest.mark.parametrize("es, thetas", [
    ((8.0, 8.0), (0.0, 360.0)), ((2.0, 16.0), (-30.0, 120.0)), ((5.0, 12.0), (100.0, 260.0)),
    ((20.0, 20.0), (0.0, 120.0)), ((0.0, 10.0), (45.0, 45.0))])
def test_a_polar_regions_reach_on_each_axis_is_its_bounding_box(es, thetas):
    """`polar_box_deg((e0, e1), (θ0, θ1))`: the per-axis box every position at an eccentricity in
    the first and a direction in the second lies in, its extremes wherever they fall, between
    the ends of the direction's range included (20° at 90° is 20° up, though neither 0° nor
    120° is). No sampled position lies outside it, and its edges are reached."""
    from wl_xcon.geometry import polar_box_deg

    sampled = np.array([polar_deg(e, t) for e in np.linspace(*es, 41)
                        for t in np.linspace(*thetas, 721)])
    (x0, x1), (y0, y1) = polar_box_deg(es, thetas)

    assert sampled[:, 0].min() >= x0 - 1e-9 and sampled[:, 0].max() <= x1 + 1e-9
    assert sampled[:, 1].min() >= y0 - 1e-9 and sampled[:, 1].max() <= y1 + 1e-9
    assert (x0, x1, y0, y1) == pytest.approx(
        (sampled[:, 0].min(), sampled[:, 0].max(), sampled[:, 1].min(), sampled[:, 1].max()),
        abs=0.02)


@pytest.mark.parametrize("seed", range(8))
def test_the_least_separation_with_a_polar_region_is_never_more_than_any_of_its_positions(seed):
    """A window whose center is a polar region (an eccentricity over a range and a direction over
    another) against one at a point and one over a per-axis range: the least is never more than
    a fine sweep of the region finds, and within its spacing's error of it; at a point at the
    region's own center, every direction at one eccentricity is that far, exactly."""
    rng = random.Random(seed)
    e0 = rng.uniform(1.0, 20.0)
    es = (e0, e0 + rng.uniform(0.0, 6.0))
    t0 = rng.uniform(-180.0, 180.0)
    thetas = (t0, t0 + rng.uniform(5.0, 300.0))
    region = np.array([polar_deg(e, t) for e in np.linspace(*es, 61)
                       for t in np.linspace(*thetas, 1201)])
    point = (rng.uniform(-25.0, 25.0), rng.uniform(-18.0, 18.0))
    box = ((point[0] - 1.0, point[0] + 2.0), (point[1] - 0.5, point[1] + 0.5))

    to_point = least_separation_deg([es], [thetas], [(point[0], point[0])],
                                    [(point[1], point[1])], polar_a=True)
    swept = _least_by_dots([point], [tuple(p) for p in region])
    assert swept - 0.01 <= to_point <= swept + 1e-9

    corners = [(x, y) for x in np.linspace(*box[0], 31) for y in np.linspace(*box[1], 11)]
    to_box = least_separation_deg([es], [thetas], [box[0]], [box[1]], polar_a=True)
    swept = min(_least_by_dots(corners, [tuple(p) for p in region[k::7]]) for k in range(7))
    assert swept - 0.05 <= to_box <= swept + 1e-9

    assert least_separation_deg([(8.0, 8.0)], [(0.0, 360.0)], [(0.0, 0.0)], [(0.0, 0.0)],
                                polar_a=True) == pytest.approx(8.0, abs=1e-9)


@pytest.mark.parametrize("seed", range(10))
def test_two_polar_regions_are_as_far_apart_as_every_pair_of_their_positions(seed):
    """Two windows whose centers are polar regions, each an eccentricity over a range and a
    direction over another: the least, which has a closed form for sectors about one center
    (`_sectors_apart`), is never more than a fine sweep of both finds and within its spacing's
    error of it."""
    rng = random.Random(100 + seed)

    def sector():
        e0 = rng.uniform(0.0, 20.0)
        t0 = rng.uniform(-180.0, 180.0)
        return (e0, e0 + rng.uniform(0.0, 8.0)), (t0, t0 + rng.uniform(0.0, 150.0))

    (ea, ta), (eb, tb) = sector(), sector()
    a = [polar_deg(e, t) for e in np.linspace(*ea, 41) for t in np.linspace(*ta, 301)]
    b = [polar_deg(e, t) for e in np.linspace(*eb, 41) for t in np.linspace(*tb, 301)]
    swept = min(_least_by_dots(a, b[k::9]) for k in range(9))

    found = least_separation_deg([ea], [ta], [eb], [tb], polar_a=True, polar_b=True)

    assert swept - 0.05 <= found <= swept + 1e-9


# --- The search between two windows ends in closed forms (the review of commits 2-5, item 1) ---
#
# A load check runs between two trials for a value a console sends past its range
# (`taskd.Session._beyond_range`), where stop, pause and the out-of-cage limit wait on it; so no
# pair of single intervals is left to a slow search.


def test_a_negative_eccentricity_is_the_same_position_a_half_turn_round_in_closed_form(
        monkeypatch):
    """The review's case: a thin sector at eccentricities -5.96° to -5.94°, 37° to 176°, against one
    at 16.9° to 18.5°, 197° to 341°, ran the search to its 200,000-node limit. A negative
    eccentricity at θ is the same position at its negation and θ + 180°, so the pair is two
    sectors, in closed form: no node is searched, and the answer is the one for the sector
    written the other way."""
    def searched(*_):
        raise AssertionError("searched a pair that has a closed form")

    monkeypatch.setattr(geometry, "_halves", searched)
    negative = least_separation_deg([(-5.96, -5.94)], [(37.0, 176.0)], [(16.9, 18.5)],
                                    [(197.0, 341.0)], polar_a=True, polar_b=True)
    turned = least_separation_deg([(5.94, 5.96)], [(217.0, 356.0)], [(16.9, 18.5)],
                                  [(197.0, 341.0)], polar_a=True, polar_b=True)
    straddling = least_separation_deg([(-3.0, 4.0)], [(30.0, 30.0)], [(4.0, 16.0)],
                                      [(-8.0, 8.0)], polar_a=True)

    assert negative == turned
    region = [polar_deg(e, t) for e in np.linspace(-5.96, -5.94, 5)
              for t in np.linspace(37.0, 176.0, 1401)]
    other = [polar_deg(e, t) for e in np.linspace(16.9, 18.5, 33)
             for t in np.linspace(197.0, 341.0, 1441)]
    swept = min(_least_by_dots(region, other[k::11]) for k in range(11))
    assert swept - 0.01 <= negative <= swept + 1e-9
    # An eccentricity from -3° to 4° at 30° is two parts, 0° to 3° at 210° and 0° to 4° at 30°.
    line = [polar_deg(e, 30.0) for e in np.linspace(-3.0, 4.0, 701)]
    window = [(x, y) for x in np.linspace(4.0, 16.0, 241) for y in np.linspace(-8.0, 8.0, 321)]
    swept = min(_least_by_dots(line, window[k::13]) for k in range(13))
    assert swept - 0.02 <= straddling <= swept + 1e-9


@pytest.mark.parametrize("seed", range(6))
def test_a_sector_and_a_rectangle_are_apart_in_closed_form_never_more_than_any_pair(seed,
                                                                                  monkeypatch):
    """`_sector_to_rectangle`, with no node searched: never more than a fine sweep of both finds,
    and within its spacing's error of it; a thin rectangle crossing an annulus with no corner of
    either inside the other is 0° from it."""
    def searched(*_):
        raise AssertionError("searched a pair that has a closed form")

    monkeypatch.setattr(geometry, "_halves", searched)
    rng = random.Random(500 + seed)
    e0 = rng.uniform(-15.0, 25.0)
    es = (e0, e0 + rng.uniform(0.0, 8.0))
    t0 = rng.uniform(-180.0, 180.0)
    ts = (t0, t0 + rng.uniform(0.0, 300.0))
    x0, y0 = rng.uniform(-30.0, 30.0), rng.uniform(-20.0, 20.0)
    xs, ys = (x0, x0 + rng.uniform(0.0, 15.0)), (y0, y0 + rng.uniform(0.0, 10.0))
    sector = [polar_deg(e, t) for e in np.linspace(*es, 33) for t in np.linspace(*ts, 601)]
    box = [(x, y) for x in np.linspace(*xs, 61) for y in np.linspace(*ys, 41)]
    swept = min(_least_by_dots(sector[k::7], box) for k in range(7))

    found = least_separation_deg([es], [ts], [xs], [ys], polar_a=True)

    assert swept - 0.1 <= found <= swept + 1e-9
    assert least_separation_deg([(8.0, 10.0)], [(0.0, 360.0)], [(-0.05, 0.05)], [(-20.0, 20.0)],
                                polar_a=True) == 0.0


def test_a_search_past_its_limit_stops_there_with_a_bound_never_more_than_the_least(monkeypatch):
    """`_SEARCH_LIMIT` guards a load check against lists of intervals no test has met: the search
    expands no more nodes than it, and the least bound left is then the answer, never more than
    the least. A window over forty choices across and a range up, against one over a range
    across and thirty choices up, takes more than three nodes in full; at a limit of 3 it
    expands 3, and at 0, 3 and 30 is never read farther apart than the whole search reads it."""
    rng = random.Random(9)
    sides = ([(v, v) for v in sorted(rng.uniform(-30, 30) for _ in range(40))], [(-4.0, 6.0)],
             [(12.0, 20.0)], [(v, v) for v in sorted(rng.uniform(-15, 15) for _ in range(30))])
    count = [0]
    halves = geometry._halves

    def counting(*args):
        count[0] += 1
        return halves(*args)

    monkeypatch.setattr(geometry, "_halves", counting)
    least = least_separation_deg(*sides)
    assert count[0] > 3
    for limit in (0, 3, 30):
        monkeypatch.setattr(geometry, "_SEARCH_LIMIT", limit)
        count[0] = 0
        assert 0.0 <= least_separation_deg(*sides) <= least + 1e-12
        assert count[0] <= limit


def test_a_search_over_lists_and_sectors_ends_well_inside_its_limit(monkeypatch):
    """The worst the review found for a sector against a rectangle, 46,565 nodes, needs none now;
    a polar window over twelve directions and two eccentricity ranges, against one over twenty
    places across and a range up, ends in far fewer nodes than `_SEARCH_LIMIT`."""
    count = [0]
    halves = geometry._halves

    def counting(*args):
        count[0] += 1
        return halves(*args)

    monkeypatch.setattr(geometry, "_halves", counting)
    least_separation_deg([(2.0, 4.0), (9.0, 11.0)], [(t, t) for t in range(0, 360, 30)],
                         [(v, v) for v in range(-20, 20, 2)], [(-3.0, 3.0)], polar_a=True)

    assert 0 < count[0] < geometry._SEARCH_LIMIT // 10


def test_a_rectangle_passing_through_a_sector_away_from_its_foot_meets_it():
    """A strip 8.6°-8.7° up across ±20° passes through a sector 9°-11° out at 60°-70°, near x 4°,
    with no corner of either inside the other (the sector's are 7.8°, 8.5°, 9.6° and 10.4° up)
    and away from the strip's foot from straight ahead at (0°, 8.6°): the cuts where the strip
    crosses the sector's radial lines are what find that they meet."""
    assert least_separation_deg([(9.0, 11.0)], [(60.0, 70.0)], [(-20.0, 20.0)], [(8.6, 8.7)],
                                polar_a=True) == 0.0


# --- Positions at the side of the field (the review of the fix commit, item 1) -----------------
#
# Per-axis degrees cannot say where a position 90° out lies: `polar_deg(90, θ)` is (±90, ±90)
# whatever θ is. A least measured through it could be more than the least; these hold the closed
# forms to true directions there.


def _true_directions(points):
    """Directions from eccentricity and direction pairs, never through per-axis degrees."""
    e = np.radians(np.array([p[0] for p in points]))
    t = np.radians(np.array([p[1] for p in points]))
    return np.stack([np.sin(e) * np.cos(t), np.sin(e) * np.sin(t), np.cos(e)], axis=1)


def _least_true(polar_points, axis_points) -> float:
    dots = np.clip(_true_directions(polar_points) @ _directions(axis_points).T, -1.0, 1.0)
    return math.degrees(math.acos(dots.max()))


def test_a_position_at_the_side_is_measured_by_its_direction():
    """(90°, 0°) per axis is the direction straight to the right; a sector 80°-90° out at 10°-20°
    comes within 10° of it, at 90° out and 10°, which per-axis degrees could not say."""
    from wl_xcon.geometry import _to_sector

    assert _to_sector(90.0, 0.0, (80.0, 90.0), (10.0, 20.0)) == pytest.approx(10.0, abs=1e-9)
    assert least_separation_deg([(80.0, 90.0)], [(10.0, 20.0)], [(90.0, 90.0)], [(0.0, 0.0)],
                                polar_a=True) == pytest.approx(10.0, abs=1e-9)
    # A polar position 90° out at 30°, as a choice, is 30° from straight right.
    assert least_separation_deg([(90.0, 90.0)], [(30.0, 30.0)], [(90.0, 90.0)], [(0.0, 0.0)],
                                polar_a=True) == pytest.approx(30.0, abs=1e-9)
    # Wholly 90° out against a rectangle, where no per-axis box holds it: never more than the least.
    box = [(x, y) for x in np.linspace(80.0, 90.0, 41) for y in np.linspace(10.0, 20.0, 41)]
    assert least_separation_deg([(90.0, 90.0)], [(25.0, 35.0)], [(80.0, 90.0)], [(10.0, 20.0)],
                                polar_a=True) <= _least_true(
        [(90.0, t) for t in np.linspace(25.0, 35.0, 101)], box) + 1e-9


@pytest.mark.parametrize("seed", range(10))
def test_a_region_reaching_the_side_is_never_read_farther_than_its_positions(seed):
    """Seeded: a polar region whose eccentricity reaches 88°-90° or has no end, against a per-axis
    region reaching the side, and against a point at it: the least read is never more than a
    sweep of true directions finds."""
    rng = random.Random(900 + seed)
    e0 = rng.uniform(40.0, 88.0)
    high = rng.choice([90.0, math.inf, rng.uniform(88.0, 90.0)])
    t0 = rng.uniform(-180.0, 180.0)
    thetas = (t0, t0 + rng.uniform(1.0, 120.0))
    xs = sorted((rng.choice([90.0, -90.0]), rng.uniform(-90.0, 90.0)))
    ys = sorted((rng.uniform(-90.0, 90.0), rng.uniform(-90.0, 90.0)))
    sector = [(e, t) for e in np.linspace(e0, min(high, 90.0), 61)
              for t in np.linspace(*thetas, 241)]
    box = [(x, y) for x in np.linspace(*xs, 91) for y in np.linspace(*ys, 91)]
    side = (xs[0], 0.0) if abs(xs[0]) == 90.0 else (xs[1], 0.0)

    to_box = least_separation_deg([(e0, high)], [thetas], [tuple(xs)], [tuple(ys)], polar_a=True)
    to_side = least_separation_deg([(e0, high)], [thetas], [(side[0], side[0])],
                                   [(side[1], side[1])], polar_a=True)

    assert to_box <= _least_true(sector, box) + 1e-9
    assert to_side <= _least_true(sector, [side]) + 1e-9
