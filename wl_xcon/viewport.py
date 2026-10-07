"""Each eye's viewport, in degrees (engine spec §5; build A1).

**Positions map to the panel by `D · tan`, per axis**, as `geometry` holds: a sample
`(x_cm, y_cm)` from the eye's straight-ahead point is the direction `(x, y, D)`. A
stimulus's own shape is drawn in a local frame centered on it: in **true visual angle**
the frame is azimuthal-equidistant about the stimulus's direction, so a 2° disc subtends
2° wherever it is; in **center scale** it is the screen's own centimeters at the
center's `D·π/180` cm per degree, as many labs draw (spec §5.3).

Through the stereoscope each eye sees its half of the panel at the folded path `D`, its
axis through the half's center (optics drawing §3). The vergence offset is not here:
`screen.resolve` puts it in each item's per-eye direction. Every number is computed from
the rig file, not measured (V9 measures).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from wl_xcon.geometry import Geometry, Rig


@dataclass(frozen=True, slots=True)
class Viewport:
    eye: str
    width_px: int
    height_px: int
    pitch_cm: tuple[float, float]
    distance_cm: float
    ahead_cm: tuple[float, float]


def viewports(rig: Rig, geometry: Geometry, *, pixels=None) -> tuple[Viewport, ...]:
    """The setup's viewports. `pixels` draws a preview of the same panel at fewer pixels:
    the same centimeters and degrees, a coarser grid."""
    w_px, h_px = pixels or rig.pixels
    pitch = (rig.panel_width_cm / w_px, rig.panel_height_cm / h_px)
    d = geometry.viewing_distance_cm
    if geometry.view == "direct":
        return (Viewport("both", w_px, h_px, pitch, d, rig.straight_ahead_cm),)
    return (
        Viewport("left", w_px // 2, h_px, pitch, d, (0.0, 0.0)),
        Viewport("right", w_px // 2, h_px, pitch, d, (0.0, 0.0)),
    )


def sample_cm(vp: Viewport, supersample: int, region=None):
    """Every sample's position, cm from the eye's straight-ahead point: an `n × n` grid
    inside each pixel of `region` (`x0, y0, x1, y1` in pixels; the whole viewport by
    default), at offsets `(k + 0.5) / n`. Two `(rows·n, cols·n)` arrays; rows run top to
    bottom and y is up."""
    x0, y0, x1, y1 = region or (0, 0, vp.width_px, vp.height_px)
    n = supersample
    cols = x0 + (np.arange((x1 - x0) * n) + 0.5) / n
    rows = y0 + (np.arange((y1 - y0) * n) + 0.5) / n
    x_cm = (cols - vp.width_px / 2) * vp.pitch_cm[0] - vp.ahead_cm[0]
    y_cm = (vp.height_px / 2 - rows) * vp.pitch_cm[1] - vp.ahead_cm[1]
    shape = (rows.size, cols.size)
    return np.broadcast_to(x_cm[None, :], shape), np.broadcast_to(y_cm[:, None], shape)


def directions(x_cm, y_cm, distance_cm):
    """Unit vectors from the eye through each sample; z points straight ahead."""
    v = np.stack([x_cm, y_cm, np.full(np.shape(x_cm), float(distance_cm))], axis=-1)
    return v / np.linalg.norm(v, axis=-1, keepdims=True)


def center(x_deg, y_deg):
    """The direction of a position in degrees, mapped by `D · tan` per axis."""
    t = np.array([math.tan(math.radians(x_deg)), math.tan(math.radians(y_deg)), 1.0])
    return t / np.linalg.norm(t)


def local_true_angle(v, c):
    """Azimuthal-equidistant coordinates of directions `v` about `c`, in degrees: the
    angle from `c`, split along `c`'s own rightward and upward axes."""
    ex = np.array([1.0, 0.0, 0.0]) - c[0] * c
    ex = ex / np.linalg.norm(ex)
    ey = np.cross(c, ex)
    cos_t = np.clip(v @ c, -1.0, 1.0)
    t = v - cos_t[..., None] * c
    tn = np.linalg.norm(t, axis=-1)
    theta = np.degrees(np.arctan2(tn, cos_t))
    safe = np.where(tn > 0, tn, 1.0)
    return theta * (t @ ex) / safe, theta * (t @ ey) / safe


def local_center_scale(x_cm, y_cm, x_deg, y_deg, distance_cm):
    """Centimeters from the stimulus's center, at the screen center's cm per degree."""
    k = distance_cm * math.pi / 180.0
    xc = distance_cm * math.tan(math.radians(x_deg))
    yc = distance_cm * math.tan(math.radians(y_deg))
    return (x_cm - xc) / k, (y_cm - yc) / k
