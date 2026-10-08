"""Each eye's viewport, in degrees (engine spec §5; build A1)."""

import math
from dataclasses import replace

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
    # Samples are cm from the rig's straight-ahead point, which need not be the panel's center.
    (px, py), (ax, ay) = direct.pitch_cm, direct.ahead_cm
    assert x_cm[0, 0] == pytest.approx(-2 * px + px / 4 - ax)
    assert y_cm[0, 0] == pytest.approx((direct.height_px / 2 - 0.25) * py - ay)
    assert y_cm[0, 0] > 0 > y_cm[-1, 0]


def test_a_straight_ahead_point_right_of_and_above_the_panel_s_center_is_where_0_deg_falls():
    # Rig.straight_ahead_cm is cm from the panel's center, x right and y up; samples are cm
    # from it, so the panel's center sample sits left of and below it.
    (vp,) = viewport.viewports(replace(RIG, straight_ahead_cm=(1.0, 0.5)), DIRECT, pixels=(5, 3))
    x_cm, y_cm = viewport.sample_cm(vp, 1)
    assert (float(x_cm[1, 2]), float(y_cm[1, 2])) == pytest.approx((-1.0, -0.5))


def test_true_angle_coordinates_are_visual_angle_far_off_axis():
    c = viewport.center(30.0, 0.0)
    v = viewport.center(31.0, 0.0)
    u, w = viewport.local_true_angle(v[None, :], c)
    assert float(u[0]) == pytest.approx(math.degrees(math.acos(float(v @ c))), abs=1e-9)
    assert abs(float(w[0])) < 1e-9


def test_true_angle_coordinates_are_visual_angle_off_axis_in_x_and_y():
    c = viewport.center(30.0, 10.0)
    u, w = viewport.local_true_angle(c[None, :], c)
    assert abs(float(u[0])) < 1e-9 and abs(float(w[0])) < 1e-9
    # Directions 1° from c every 45° around it, about axes built another way than the frame's.
    e1 = np.cross(c, [0.0, 0.0, 1.0])
    e1 /= np.linalg.norm(e1)
    e2 = np.cross(c, e1)
    phi = np.radians(np.arange(0.0, 360.0, 45.0))
    v = (math.cos(math.radians(1.0)) * c
         + math.sin(math.radians(1.0)) * (np.cos(phi)[:, None] * e1 + np.sin(phi)[:, None] * e2))
    u, w = viewport.local_true_angle(v, c)
    assert np.hypot(u, w).tolist() == pytest.approx(np.degrees(np.arccos(v @ c)).tolist(), abs=1e-9)
    u, w = viewport.local_true_angle(viewport.center(30.0, 11.0)[None, :], c)
    assert float(w[0]) > 0  # up is up off axis too


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
