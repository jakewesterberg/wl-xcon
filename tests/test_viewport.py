"""Each eye's viewport, in degrees (engine spec §5; build A1)."""

import math

import numpy as np
import pytest

from _rig import DIRECT, RIG, STEREOSCOPE
from wl_xcon import viewport


def test_direct_view_is_one_viewport_and_the_stereoscope_two_halves():
    (direct,) = viewport.viewports(RIG, DIRECT)
    left, right = viewport.viewports(RIG, STEREOSCOPE)
    assert direct.eye == "both" and (direct.width_px, direct.height_px) == RIG.pixels == (3840, 2160)
    assert (left.eye, right.eye) == ("left", "right")
    assert left.width_px == RIG.pixels[0] // 2 and left.pitch_cm == direct.pitch_cm
    assert left.distance_cm == STEREOSCOPE.viewing_distance_cm


def test_a_preview_keeps_the_panel_s_centimeters():
    (small,) = viewport.viewports(RIG, DIRECT, pixels=(384, 216))
    assert small.pitch_cm == pytest.approx((RIG.panel_width_cm / 384, RIG.panel_height_cm / 216))


def test_the_viewport_s_edge_is_the_field_s_edge():
    (direct,) = viewport.viewports(RIG, DIRECT)
    x_cm, _ = viewport.sample_cm(direct, 1, region=(direct.width_px - 1, 0, direct.width_px, 1))
    edge = math.degrees(math.atan((x_cm[0, 0] + direct.pitch_cm[0] / 2) / direct.distance_cm))
    assert edge == pytest.approx(DIRECT.half_field_h_deg)


def test_samples_sit_inside_their_pixel_and_y_points_up():
    (direct,) = viewport.viewports(RIG, DIRECT, pixels=(4, 2))
    x_cm, y_cm = viewport.sample_cm(direct, 2)
    assert x_cm.shape == y_cm.shape == (4, 8)
    assert x_cm[0, 0] == pytest.approx(-2 * direct.pitch_cm[0] + direct.pitch_cm[0] / 4)
    assert y_cm[0, 0] > 0 > y_cm[-1, 0]


def test_true_angle_coordinates_are_visual_angle_far_off_axis():
    c = viewport.center(30.0, 0.0)
    v = viewport.center(31.0, 0.0)
    u, w = viewport.local_true_angle(v[None, :], c)
    assert float(u[0]) == pytest.approx(math.degrees(math.acos(float(v @ c))), abs=1e-9)
    assert abs(float(w[0])) < 1e-9


def test_the_local_frame_has_x_right_and_y_up():
    c = viewport.center(0.0, 0.0)
    u, w = viewport.local_true_angle(viewport.center(0.0, 2.0)[None, :], c)
    assert float(w[0]) == pytest.approx(2.0) and abs(float(u[0])) < 1e-9
    u, w = viewport.local_true_angle(viewport.center(2.0, 0.0)[None, :], c)
    assert float(u[0]) == pytest.approx(2.0) and abs(float(w[0])) < 1e-9


def test_center_scale_uses_the_center_s_cm_per_degree_everywhere():
    d, k = 50.0, 50.0 * math.pi / 180
    x = np.array([d * math.tan(math.radians(30.0)) + k])
    u, w = viewport.local_center_scale(x, np.array([0.0]), 30.0, 0.0, d)
    assert float(u[0]) == pytest.approx(1.0) and float(w[0]) == pytest.approx(0.0)
