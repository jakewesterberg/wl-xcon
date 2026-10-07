"""The exact drawer: the definition of what each eye must see (engine spec §4.9;
build A1).

Slow on purpose, and never inside a frame: plain numpy over every sample of every pixel.
The GPU drawer is held to it within one output level (spec §10.1), the review report's
frames come from it, and analysis rebuilds any recorded frame from it.

**The definition, for each pixel of an eye's viewport:**

1. Sample it on a regular `SUPERSAMPLE × SUPERSAMPLE` grid (`viewport.sample_cm`).
2. For each item that eye sees, bottom layer first: put each sample in the item's local
   frame (true visual angle or center scale), turned by `−orientation`, and find its
   signed distance `d` to the shape (negative inside). Coverage needs only the zero set
   and the sign, since step 3 divides by the gradient, but edges and outlines read `d`
   as degrees, so every shape's `d` is a distance in degrees at least to first order.
3. Weigh the sample by its share inside the shape -- the box filter of one sample's
   width, `clip(0.5 − d / |∇d|, 0, 1)` with `∇d` across the sample grid (`coverage`) --
   times the edge's profile where the edge applies to opacity, times the item's opacity.
   Combine the item with what is below (`_compose`), then cover it with its outline.
4. Average each pixel's samples. The result is CIE XYZ, Y in cd/m²; build A2 turns it
   into the panel's output levels through a calibration.
"""

from __future__ import annotations

import math

import numpy as np

from wl_xcon import look, viewport
from wl_xcon.screen import NotYetDrawable, ResolvedFlat, ResolvedGrating

SUPERSAMPLE = 4
#: The whole screen's distance to its boundary: further than any viewport reaches.
_EVERYWHERE = -1e9


def _slope(d, axis):
    """How fast `d` changes across one sample along `axis`: the larger of the forward and
    backward one-sided differences. For a straight edge that is the central difference;
    at a ridge (a line's center, where |d| has a kink) it still reads the true slope."""
    if d.ndim <= axis or d.shape[axis] < 2:
        return np.zeros_like(d)
    diff = np.abs(np.diff(d, axis=axis))
    first = np.take(diff, [0], axis=axis)
    last = np.take(diff, [-1], axis=axis)
    forward = np.concatenate([diff, last], axis=axis)
    backward = np.concatenate([first, diff], axis=axis)
    return np.maximum(forward, backward)


def coverage(d):
    """Each sample's share of its footprint inside the shape, from the signed distance
    and its gradient across the sample grid (a sample's own width is one step).

    Exact for features at least one sample wide. Narrower ones draw brighter than their
    area, by an amount that depends on where they fall."""
    g = np.hypot(_slope(d, 1), _slope(d, 0))
    soft = np.clip(0.5 - d / np.where(g > 0, g, 1.0), 0.0, 1.0)
    return np.where(g > 0, soft, (d <= 0).astype(float))


def _rect(u, w, half_w, half_h):
    qx, qy = np.abs(u) - half_w, np.abs(w) - half_h
    return np.hypot(np.maximum(qx, 0.0), np.maximum(qy, 0.0)) + np.minimum(np.maximum(qx, qy), 0.0)


def _polygon(u, w, points):
    """Distance to a closed polygon, signed by an even-odd crossing count."""
    pts = np.asarray(points, dtype=float)
    d = np.full(np.shape(u), np.inf)
    sign = np.ones(np.shape(u))
    for i in range(len(pts)):
        a, b = pts[i], pts[i - 1]
        ex, ey = b - a
        if ex * ex + ey * ey == 0.0:
            continue  # adds no distance and no crossing
        wx, wy = u - a[0], w - a[1]
        t = np.clip((wx * ex + wy * ey) / (ex * ex + ey * ey), 0.0, 1.0)
        d = np.minimum(d, (wx - ex * t) ** 2 + (wy - ey * t) ** 2)
        c1, c2, c3 = w >= a[1], w < b[1], ex * wy > ey * wx
        sign = np.where((c1 & c2 & c3) | (~c1 & ~c2 & ~c3), -sign, sign)
    return sign * np.sqrt(d)


def _segments(u, w, points):
    pts = np.asarray(points, dtype=float)
    d = np.full(np.shape(u), np.inf)
    for a, b in zip(pts[:-1], pts[1:]):
        ex, ey = b - a
        if ex * ex + ey * ey == 0.0:
            continue
        wx, wy = u - a[0], w - a[1]
        t = np.clip((wx * ex + wy * ey) / (ex * ex + ey * ey), 0.0, 1.0)
        d = np.minimum(d, np.hypot(wx - ex * t, wy - ey * t))
    return d


def signed_distance(shape, u, w):
    """Degrees from the shape's boundary in its local frame, negative inside. Each
    formula here is the shape's definition."""
    if isinstance(shape, look.Circle):
        return np.hypot(u, w) - shape.size / 2
    if isinstance(shape, look.Ellipse):
        a, b = shape.width / 2, shape.height / 2
        # First-order distance: (k - 1) over the gradient of k, k = hypot(u/a, w/b).
        k = np.hypot(u / a, w / b)
        grad = np.hypot(u / a ** 2, w / b ** 2)
        safe = np.where(grad > 0, grad, 1.0)
        return np.where(grad > 0, (k - 1.0) * k / safe, -min(a, b))
    if isinstance(shape, look.Rect):
        return _rect(u, w, shape.width / 2, shape.height / 2)
    if isinstance(shape, look.Cross):
        return np.minimum(_rect(u, w, shape.size / 2, shape.thickness / 2),
                          _rect(u, w, shape.thickness / 2, shape.size / 2))
    if isinstance(shape, look.Ring):
        r = np.hypot(u, w)
        return np.maximum(r - shape.outer / 2, shape.inner / 2 - r)
    if isinstance(shape, look.RegularPolygon):
        n, r = int(shape.sides), shape.size / 2
        angles = np.radians(90.0 + 360.0 * np.arange(n) / n)
        return _polygon(u, w, np.stack([r * np.cos(angles), r * np.sin(angles)], axis=1))
    if isinstance(shape, look.Vertices):
        return _polygon(u, w, shape.points)
    if isinstance(shape, look.Path):
        return _segments(u, w, shape.points) - shape.width / 2
    if isinstance(shape, look.WholeScreen):
        return np.full(np.shape(u), _EVERYWHERE)
    raise NotYetDrawable(f"{type(shape).__name__} is drawn in a later engine build")


def edge_profile(edge, d, u, w):
    """The edge's profile at each sample; coverage, not this, cuts at the boundary."""
    if isinstance(edge, look.Hard):
        return np.ones(np.shape(d))
    if isinstance(edge, look.RaisedCosine):
        return 0.5 * (1.0 - np.cos(np.pi * np.clip(-d / edge.width, 0.0, 1.0)))
    if isinstance(edge, look.GaussianEdge):
        return np.exp(-(u * u + w * w) / (2.0 * edge.sigma ** 2))
    raise NotYetDrawable(f"{type(edge).__name__} is drawn in a later engine build")


def _local(item, x_cm, y_cm, vp, periphery):
    """Each sample in the item's own frame, turned by −orientation."""
    xd, yd = item.at_right if vp.eye == "right" else item.at_left
    if periphery == "center_scale":
        u, w = viewport.local_center_scale(x_cm, y_cm, xd, yd, vp.distance_cm)
    else:
        u, w = viewport.local_true_angle(viewport.directions(x_cm, y_cm, vp.distance_cm),
                                         viewport.center(xd, yd))
    th = math.radians(item.orientation)
    return u * math.cos(th) + w * math.sin(th), -u * math.sin(th) + w * math.cos(th)


def _sees(item, vp) -> bool:
    return vp.eye == "both" or item.eye in ("both", vp.eye)


def _phase(fill, w, item, screen):
    """A grating's phase at each sample: bars along local x, luminance along local y,
    drifting toward +y at `tf` from the frame the item appeared (spec §4.3, §5.1)."""
    t = (screen.frame - item.onset_frame) * screen.frame_period
    return 2.0 * math.pi * (fill.sf * w - fill.tf * t) + math.radians(fill.phase)


def _light(fill, mean, background, envelope, w, item, screen):
    """The light an item would be with nothing below it, at each sample; `mean` is what a
    pattern's mean is when it declares none."""
    if isinstance(fill, ResolvedFlat):
        if fill.xyz is not None:
            return np.asarray(fill.xyz, dtype=float)
        return background * (1.0 + fill.weber)
    if isinstance(fill, ResolvedGrating):
        base = mean if fill.mean_xyz is None else np.asarray(fill.mean_xyz, dtype=float)
        return base * (1.0 + fill.michelson * np.sin(_phase(fill, w, item, screen)) * envelope)[..., None]
    raise NotYetDrawable(f"{type(fill).__name__} is drawn in engine build A3")


def _compose(item, below, background, a, envelope, w, screen):
    """How an item meets what is below it (engine spec §4.4); `a` is its weight at each
    sample, `background` the eye's background."""
    a3 = a[..., None]
    if item.combine == "cover":
        return below + a3 * (_light(item.fill, below, background, envelope, w, item, screen) - below)
    raise NotYetDrawable(f"combining by {item.combine!r} is drawn in Task 10 of engine build A1")


def draw(screen, vp, *, region=None, supersample=SUPERSAMPLE):
    """The eye `vp` describes, as `screen` makes it at `screen.frame`: `(rows, cols, 3)`
    CIE XYZ in cd/m², each pixel the mean of its samples."""
    x_cm, y_cm = viewport.sample_cm(vp, supersample, region)
    background = np.asarray(
        screen.background_right if vp.eye == "right" else screen.background_left, dtype=float)
    canvas = np.empty(x_cm.shape + (3,))
    canvas[...] = background
    for item in screen.items:
        if not _sees(item, vp):
            continue
        u, w = _local(item, x_cm, y_cm, vp, screen.periphery)
        d = signed_distance(item.shape, u, w)
        profile = edge_profile(item.edge, d, u, w)
        on_opacity = item.edge.applies == "opacity" or isinstance(item.fill, ResolvedFlat)
        a = coverage(d) * item.opacity * (profile if on_opacity else 1.0)
        envelope = 1.0 if on_opacity else profile
        canvas = _compose(item, canvas, background, a, envelope, w, screen)
        if item.outline is not None:
            band = coverage(np.abs(d) - item.outline.width / 2) * item.opacity
            canvas = canvas + band[..., None] * (np.asarray(item.outline.xyz) - canvas)
    rows, cols = canvas.shape[0] // supersample, canvas.shape[1] // supersample
    return canvas.reshape(rows, supersample, cols, supersample, 3).mean(axis=(1, 3))
