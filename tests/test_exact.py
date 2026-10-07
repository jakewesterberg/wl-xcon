"""The exact drawer (engine spec §4.9; build A1). Previews of the real panel keep these
fast: the same centimeters and degrees at fewer pixels, or a region of a larger grid."""

import math

import numpy as np
import pytest

from _rig import DIRECT, RIG, STEREOSCOPE
from wl_xcon import exact, look, screen, viewport
from wl_xcon.photometry import Gray, Michelson, Weber, to_xyz
from wl_xcon.task import Bar, Disc, Gabor, Stimulus, Trial

TRIAL = Trial(start="s", states=[])
PREVIEW = (384, 216)


def _draw(stimuli, geometry=DIRECT, trial=TRIAL, pixels=PREVIEW, eye=0, region=None,
          frame=0, onsets=None):
    s = screen.resolve({x.name: x for x in stimuli}, {}, trial, geometry, frame_period=1 / 240,
                       frame=frame, onsets=onsets)
    vp = viewport.viewports(RIG, geometry, pixels=pixels)[eye]
    return exact.draw(s, vp, region=region), vp


def _angles(vp, region, x_deg, y_deg):
    """Each pixel's center, as degrees of visual angle from the direction (x°, y°)."""
    x_cm, y_cm = viewport.sample_cm(vp, 1, region)
    v = viewport.directions(x_cm, y_cm, vp.distance_cm)
    return np.degrees(np.arccos(np.clip(v @ viewport.center(x_deg, y_deg), -1.0, 1.0)))


def _pixel(vp, x_deg, y_deg, region=(0, 0)):
    """(row, col) of the pixel at a direction, in an image whose region starts at
    `region[:2]` (the whole viewport by default)."""
    col = vp.width_px / 2 + (vp.distance_cm * math.tan(math.radians(x_deg)) + vp.ahead_cm[0]) / vp.pitch_cm[0]
    row = vp.height_px / 2 - (vp.distance_cm * math.tan(math.radians(y_deg)) + vp.ahead_cm[1]) / vp.pitch_cm[1]
    return int(row) - region[1], int(col) - region[0]


def test_a_disc_is_drawn_at_its_light_and_nothing_else_is_lit():
    image, vp = _draw([Stimulus("d", at=(0.0, 0.0), looks=Disc(size=4.0, color=Gray(40.0)))])
    assert image[_pixel(vp, 0.0, 0.0)] == pytest.approx(np.asarray(to_xyz(Gray(40.0))))
    assert image[0, 0].tolist() == [0.0, 0.0, 0.0]


def test_a_disc_far_off_axis_subtends_its_declared_angle():
    # Review Focus 1: 2° at 25° in direct view is 2° of visual angle.
    region = (1650, 480, 1790, 600)
    image, vp = _draw([Stimulus("d", at=(25.0, 0.0), looks=Disc(size=2.0, color=Gray(40.0)))],
                      pixels=(1920, 1080), region=region)
    angles = _angles(vp, region, 25.0, 0.0)
    assert angles[image[..., 1] > 20.0].max() == pytest.approx(1.0, abs=0.04)
    assert angles[image[..., 1] < 20.0].min() == pytest.approx(1.0, abs=0.04)


def test_true_angle_and_center_scale_differ_off_axis():
    disc = Stimulus("d", at=(25.0, 0.0), looks=Disc(size=2.0, color=Gray(40.0)))
    region = (1650, 480, 1790, 600)
    true, _ = _draw([disc], pixels=(1920, 1080), region=region)
    flat, _ = _draw([disc], pixels=(1920, 1080), region=region,
                    trial=Trial(start="s", states=[], periphery="center_scale"))
    assert flat[..., 1].sum() < 0.9 * true[..., 1].sum()


def test_a_bar_narrower_than_a_pixel_keeps_its_light():
    # Review Focus 2: 0.02°, about 1.1 pixels at the panel's full resolution.
    image, vp = _draw([Stimulus("b", at=(0.0, 0.0), looks=Bar(length=4.0, width=0.02, color=Gray(40.0)))],
                      pixels=RIG.pixels, region=(1800, 960, 2040, 1200))
    px = math.degrees(math.atan(vp.pitch_cm[0] / vp.distance_cm))
    py = math.degrees(math.atan(vp.pitch_cm[1] / vp.distance_cm))
    assert image[..., 1].sum() == pytest.approx(40.0 * 4.0 * 0.02 / (px * py), rel=0.02)


def test_a_bar_turns_counter_clockwise_with_y_up():
    # Spec §5.1: 0° right, counter-clockwise positive, +y up, pinned in the drawing.
    image, vp = _draw([Stimulus("b", at=(0.0, 0.0),
                                looks=Bar(length=6.0, width=0.6, orientation=45.0, color=Gray(40.0)))])
    assert image[_pixel(vp, 1.5, 1.5)][1] == pytest.approx(40.0)
    assert image[_pixel(vp, 1.5, -1.5)][1] == 0.0


@pytest.mark.parametrize("shape, inside, outside", [
    (look.Circle(size=2.0), (0.9, 0.0), (1.1, 0.0)),
    (look.Ellipse(width=2.0, height=1.0), (0.0, 0.45), (0.0, 0.55)),
    (look.Rect(width=2.0, height=1.0), (0.9, 0.4), (0.9, 0.6)),
    (look.Cross(size=2.0, thickness=0.2), (0.9, 0.0), (0.5, 0.5)),
    (look.RegularPolygon(sides=4, size=2.0), (0.0, 0.9), (0.9, 0.9)),
    (look.Vertices(points=((0.0, 1.0), (-1.0, -1.0), (1.0, -1.0))), (0.0, 0.0), (0.0, 1.5)),
    (look.Ring(inner=1.0, outer=2.0), (0.75, 0.0), (0.25, 0.0)),
    (look.Path(points=((-1.0, 0.0), (1.0, 0.0)), width=0.2), (0.0, 0.09), (0.0, 0.11)),
])
def test_each_shape_is_negative_inside_and_positive_outside(shape, inside, outside):
    d = exact.signed_distance(shape, np.array([inside[0], outside[0]]), np.array([inside[1], outside[1]]))
    assert d[0] < 0 < d[1]


def test_the_whole_screen_is_inside_everywhere():
    assert (exact.signed_distance(look.WholeScreen(), np.zeros(3), np.array([0.0, 50.0, -50.0])) < 0).all()


def test_coverage_is_a_sample_s_share_inside_from_its_distance_and_gradient():
    d = np.array([[-1.5, -0.5, 0.0, 0.5, 1.5]])  # one sample apart
    assert exact.coverage(d).ravel().tolist() == pytest.approx([1.0, 1.0, 0.5, 0.0, 0.0])
    assert exact.coverage(np.full((2, 2), -1.0)).tolist() == [[1.0, 1.0], [1.0, 1.0]]


def test_a_raised_cosine_ramps_from_the_boundary_inward():
    p = exact.edge_profile(look.RaisedCosine(width=0.5), np.array([-1.0, -0.5, -0.25, 0.0, 0.1]),
                           np.zeros(5), np.zeros(5))
    assert p.tolist() == pytest.approx([1.0, 1.0, 0.5, 0.0, 0.0])


def test_a_gaussian_edge_is_the_radial_envelope():
    p = exact.edge_profile(look.GaussianEdge(sigma=1.0), np.array([-1.0, -1.0]),
                           np.array([0.0, 1.0]), np.array([0.0, 0.0]))
    assert p.tolist() == pytest.approx([1.0, math.exp(-0.5)])


def test_an_outline_is_a_band_on_the_boundary_over_the_fill():
    looks = look.Look(shape=look.Circle(size=4.0), fill=look.Flat(color=Gray(10.0)),
                      outline=look.Outline(width=0.6, color=Gray(40.0)))
    image, vp = _draw([Stimulus("o", at=(0.0, 0.0), looks=looks)])
    assert image[_pixel(vp, 0.0, 0.0)][1] == pytest.approx(10.0)
    assert image[_pixel(vp, 2.0, 0.0)][1] == pytest.approx(40.0)


def test_weber_contrast_is_against_the_eye_s_background():
    trial = Trial(start="s", states=[], background=Gray(20.0))
    image, vp = _draw([Stimulus("w", at=(0.0, 0.0), looks=Disc(size=4.0, contrast=Weber(0.5)))], trial=trial)
    assert image[_pixel(vp, 0.0, 0.0)][1] == pytest.approx(30.0)
    assert image[0, 0, 1] == pytest.approx(20.0)


def test_an_empty_screen_is_its_background():
    s = screen.Screen(setup="direct", periphery="true_angle", background_left=(1.0, 2.0, 3.0),
                      background_right=(0.0, 0.0, 0.0), items=(), frame=0, frame_period=1 / 240)
    vp = viewport.viewports(RIG, DIRECT, pixels=(4, 4))[0]
    assert exact.draw(s, vp).tolist() == [[[1.0, 2.0, 3.0]] * 4] * 4


def test_an_outline_on_an_ellipse_is_as_wide_along_the_major_axis_as_anywhere():
    # Pixels chosen from the preview's pitch: the panel is 384 px across at about 0.15 deg
    # per pixel on axis. x = 2.0 deg is the boundary, so the band spans 1.8 to 2.2 deg
    # (about 2.6 pixels), and the pixel containing 2.0 deg is wholly inside it; x = 2.4 deg
    # is 0.2 deg past the band's outer edge, over a pixel away from both.
    looks = look.Look(shape=look.Ellipse(width=4.0, height=1.0), fill=look.Flat(color=Gray(10.0)),
                      outline=look.Outline(width=0.4, color=Gray(40.0)))
    image, vp = _draw([Stimulus("e", at=(0.0, 0.0), looks=looks)])
    assert image[_pixel(vp, 2.0, 0.0)][1] == pytest.approx(40.0)
    assert image[_pixel(vp, 2.4, 0.0)][1] == pytest.approx(0.0)


def test_a_closed_triangle_has_a_finite_distance():
    closed = look.Vertices(points=((0.0, 1.0), (-1.0, -1.0), (1.0, -1.0), (0.0, 1.0)))
    d = exact.signed_distance(closed, np.array([0.0, 0.0]), np.array([0.0, 1.5]))
    assert np.isfinite(d).all() and d[0] < 0 < d[1]


def test_a_path_with_a_doubled_point_has_a_finite_distance():
    path = look.Path(points=((-1.0, 0.0), (0.0, 0.0), (0.0, 0.0), (1.0, 0.0)), width=0.2)
    d = exact.signed_distance(path, np.array([0.0, 0.0]), np.array([0.09, 0.11]))
    assert np.isfinite(d).all() and d[0] < 0 < d[1]


@pytest.mark.parametrize("k", range(8))
def test_a_line_just_over_a_sample_wide_keeps_its_light_at_every_phase(k):
    probe = viewport.viewports(RIG, DIRECT, pixels=RIG.pixels)[0]
    s = math.degrees(math.atan(probe.pitch_cm[1] / exact.SUPERSAMPLE / probe.distance_cm))
    image, vp = _draw([Stimulus("b", at=(0.0, k * s / 8), looks=Bar(length=4.0, width=1.2 * s, color=Gray(40.0)))],
                      pixels=RIG.pixels, region=(1800, 960, 2040, 1200))
    px = math.degrees(math.atan(vp.pitch_cm[0] / vp.distance_cm))
    py = math.degrees(math.atan(vp.pitch_cm[1] / vp.distance_cm))
    assert image[..., 1].sum() == pytest.approx(40.0 * 4.0 * 1.2 * s / (px * py), rel=0.02)


GABOR_REGION = (820, 400, 1100, 680)  # ±4.9° about the center at 1920 × 1080


def _gray20():
    return Trial(start="s", states=[], background=Gray(20.0))


def test_a_gabor_on_its_mean_is_the_textbook_formula_with_horizontal_bars():
    g = Stimulus("g", at=(0.0, 0.0), looks=Gabor(sf=1.0, sigma=1.0, phase=90.0, contrast=Michelson(0.5)))
    image, vp = _draw([g], trial=_gray20(), pixels=(1920, 1080), region=GABOR_REGION)
    assert image[_pixel(vp, 0.0, 0.0, GABOR_REGION)][1] == pytest.approx(30.0, rel=0.01)  # 20·(1 + 0.5)
    assert image[_pixel(vp, 0.5, 0.0, GABOR_REGION)][1] > 20.0                           # along a bar
    assert image[_pixel(vp, 0.0, 0.5, GABOR_REGION)][1] < 20.0                           # across the bars
    assert image[0, 0, 1] == pytest.approx(20.0)                                          # seamless


def test_the_gabor_is_cut_where_its_envelope_is_negligible():
    sigma = 0.5
    g = Stimulus("g", at=(0.0, 0.0), looks=Gabor(sf=1.0, sigma=sigma, contrast=Michelson(1.0)))
    image, vp = _draw([g], trial=_gray20(), pixels=(1920, 1080), region=GABOR_REGION)
    angles = _angles(vp, GABOR_REGION, 0.0, 0.0)
    cutoff = look.GABOR_CUTOFF_SIGMAS * sigma
    assert np.all(image[..., 1][angles > cutoff + 0.05] == 20.0)
    near = (angles > cutoff - 0.1 * sigma) & (angles <= cutoff)
    # A pixel's samples reach half a pixel (0.025°) further in than its center.
    assert np.abs(image[..., 1][near] - 20.0).max() < 20.0 * math.exp(-((cutoff - 0.15 * sigma) / sigma) ** 2 / 2)


def test_a_drifting_grating_moves_with_the_frame_from_its_onset():
    looks = look.Look(shape=look.Circle(size=6.0), fill=look.SineGrating(sf=1.0, tf=2.0, contrast=Michelson(0.5)))
    g = Stimulus("g", at=(0.0, 0.0), looks=looks)
    first, _ = _draw([g], trial=_gray20(), frame=0)
    later, _ = _draw([g], trial=_gray20(), frame=30)
    again, _ = _draw([g], trial=_gray20(), frame=10, onsets={"g": 10})
    assert not np.allclose(first, later)
    assert np.array_equal(first, again)


def test_a_grating_with_a_declared_mean_sits_on_that_mean():
    looks = look.Look(shape=look.Circle(size=6.0),
                      fill=look.SineGrating(sf=1.0, phase=90.0, contrast=Michelson(0.5), mean=Gray(10.0)))
    image, vp = _draw([Stimulus("g", at=(0.0, 0.0), looks=looks)], trial=_gray20(), pixels=(1920, 1080),
                      region=GABOR_REGION)
    assert image[_pixel(vp, 0.0, 0.0, GABOR_REGION)][1] == pytest.approx(15.0, rel=0.01)  # 10·(1 + 0.5)


def test_a_positive_tf_drifts_toward_local_plus_y():
    looks = look.Look(shape=look.Circle(size=6.0),
                      fill=look.SineGrating(sf=1.0, phase=0.0, tf=2.0, contrast=Michelson(0.5)))
    image, vp = _draw([Stimulus("g", at=(0.0, 0.0), looks=looks)], trial=_gray20(), pixels=(1920, 1080),
                      region=GABOR_REGION, frame=30)  # a quarter cycle at 1/240 s per frame
    assert image[_pixel(vp, 0.0, 0.5, GABOR_REGION)][1] == pytest.approx(30.0, rel=0.02)  # the crest


def test_a_grating_without_a_declared_mean_sits_on_what_is_behind_it():
    disc = Stimulus("d", at=(0.0, 0.0), looks=Disc(size=9.0, color=Gray(40.0)))
    gabor = Stimulus("g", at=(0.0, 0.0), layer=1,
                     looks=Gabor(sf=1.0, sigma=0.5, phase=90.0, contrast=Michelson(0.5)))
    image, vp = _draw([disc, gabor], trial=_gray20(), pixels=(1920, 1080), region=GABOR_REGION)
    assert image[_pixel(vp, 0.0, 0.0, GABOR_REGION)][1] == pytest.approx(60.0, rel=0.01)  # 40·(1 + 0.5)
    angles = _angles(vp, GABOR_REGION, 0.0, 0.0)
    seam = (angles > 2.1) & (angles < 2.5)
    assert seam.any()
    assert np.abs(image[..., 1][seam] - 40.0).max() < 0.01  # seamless onto the disc


def _patch(name, x, lum, size=4.0, **fields):
    return Stimulus(name, at=(x, 0.0), looks=Disc(size=size, color=Gray(lum)), **fields)


def _at_center(image, vp):
    return image[_pixel(vp, 0.0, 0.0)][1]


def test_cover_puts_the_later_stimulus_on_top_within_a_layer():
    # Review Focus 3.
    image, vp = _draw([_patch("a", 0.0, 10.0), _patch("b", 0.0, 40.0)])
    assert _at_center(image, vp) == pytest.approx(40.0)
    image, vp = _draw([_patch("b", 0.0, 40.0), _patch("a", 0.0, 10.0)])
    assert _at_center(image, vp) == pytest.approx(10.0)


def test_a_higher_layer_covers_a_lower_one_whatever_the_order_shown():
    image, vp = _draw([_patch("top", 0.0, 40.0, layer=2), _patch("low", 0.0, 10.0)])
    assert _at_center(image, vp) == pytest.approx(40.0)


def test_opacity_mixes_with_what_is_below():
    image, vp = _draw([_patch("a", 0.0, 10.0), _patch("b", 0.0, 40.0, opacity=0.25)])
    assert _at_center(image, vp) == pytest.approx(10.0 + 0.25 * 30.0)


def test_add_adds_light_beyond_the_background():
    image, vp = _draw([_patch("a", 0.0, 30.0), _patch("b", 0.0, 25.0, combine="add")], trial=_gray20())
    assert _at_center(image, vp) == pytest.approx(30.0 + (25.0 - 20.0))


def test_two_gratings_added_are_a_plaid_about_the_background():
    def grating(name, m, combine):
        return Stimulus(name, at=(0.0, 0.0), combine=combine,
                        looks=look.Look(shape=look.Circle(size=6.0),
                                        fill=look.SineGrating(sf=1.0, phase=90.0, contrast=Michelson(m))))
    image, vp = _draw([grating("one", 0.3, "cover"), grating("two", 0.2, "add")], trial=_gray20(),
                      pixels=(1920, 1080), region=GABOR_REGION)
    assert image[_pixel(vp, 0.0, 0.0, GABOR_REGION)][1] == pytest.approx(20.0 * (1 + 0.3 + 0.2), rel=0.01)


def test_a_window_shows_what_is_below_only_inside_it():
    window = _patch("w", 0.0, 1.0, size=1.0, combine="window", layer=1)
    image, vp = _draw([_patch("big", 0.0, 40.0), window], trial=_gray20())
    assert _at_center(image, vp) == pytest.approx(40.0)
    assert image[_pixel(vp, 1.5, 0.0)][1] == pytest.approx(20.0)


def test_a_scotoma_hides_what_is_below_inside_it():
    scotoma = _patch("s", 0.0, 1.0, size=1.0, combine="scotoma", layer=1)
    image, vp = _draw([_patch("big", 0.0, 40.0), scotoma], trial=_gray20())
    assert _at_center(image, vp) == pytest.approx(20.0)
    assert image[_pixel(vp, 1.5, 0.0)][1] == pytest.approx(40.0)


def test_multiply_scales_the_contrast_below():
    gain = Stimulus("m", at=(0.0, 0.0), looks=Disc(size=1.0, contrast=Weber(-0.5)), combine="multiply", layer=1)
    image, vp = _draw([_patch("big", 0.0, 30.0), gain], trial=_gray20())
    assert _at_center(image, vp) == pytest.approx(20.0 + (30.0 - 20.0) * 0.5)
    assert image[_pixel(vp, 1.5, 0.0)][1] == pytest.approx(30.0)


def test_multiply_by_an_absolute_light_is_refused_not_guessed():
    with pytest.raises(ValueError, match="gain"):
        _draw([_patch("big", 0.0, 30.0), _patch("m", 0.0, 10.0, combine="multiply")], trial=_gray20())


def test_each_eye_sees_its_own_stimuli_moved_by_the_vergence_offset():
    left_only = _patch("l", 0.0, 40.0, eye="left")
    left, vp = _draw([left_only], geometry=STEREOSCOPE, eye=0)
    right, _ = _draw([left_only], geometry=STEREOSCOPE, eye=1)
    assert left[..., 1].max() == pytest.approx(40.0) and right[..., 1].max() == 0.0
    cols = np.nonzero(left[left.shape[0] // 2, :, 1] > 20.0)[0]
    assert (cols.min() + cols.max() + 1) / 2 > vp.width_px / 2  # right of center, in the left eye


def test_a_stimulus_past_one_eye_s_viewport_is_clipped_there_and_whole_in_the_other():
    # Review Focus 4: check 8 refuses this at load; drawn anyway, it clips without error.
    edge = _patch("e", 11.5, 40.0)
    left, _ = _draw([edge], geometry=STEREOSCOPE, eye=0)
    right, _ = _draw([edge], geometry=STEREOSCOPE, eye=1)
    assert right[..., 1].sum() > left[..., 1].sum() > 0.0


def test_each_eye_has_its_own_background():
    trial = Trial(start="s", states=[], background=Gray(20.0), background_right=Gray(10.0))
    left, _ = _draw([], geometry=STEREOSCOPE, trial=trial, eye=0)
    right, _ = _draw([], geometry=STEREOSCOPE, trial=trial, eye=1)
    assert (left[0, 0, 1], right[0, 0, 1]) == pytest.approx((20.0, 10.0))
