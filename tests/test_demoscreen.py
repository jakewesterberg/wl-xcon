"""A demo's screen as the page shows it (demo mode design §4.4; its plan's Task 7): `demoscreen`
draws each `link.Drawn` with the exact drawer at a preview of the rig's panel, through the sRGB
standard, as a PNG inside an SVG whose eye groups are centimeters from each eye's straight-ahead
point, +y up, labeled as §4.4's table says, on a thread of its own that draws the newest screen
next. What is held here: the preview is the viewport `viewport.viewports` makes at its pixels; the
image is `exact.draw` at it through sRGB, pixel for pixel; each label of the table; what could not
be drawn, outlined with why; the coordinates, and their degrees as `geometry` maps them; the
stereoscope's eyes side by side; the newest screen drawn next; a blank screen the background alone.

Every `Drawn` here is built as a demo's world builds one, by `pointer.Drawing` from a
`pointer.Pointing` world, except where a test needs a field no trial makes. Engine test material:
no timing claim rests on any number here (CLAUDE.md).
"""

from __future__ import annotations

import base64
import importlib.util
import math
import re
import struct
import threading
import xml.etree.ElementTree as ET
import zlib
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from _rig import DIRECT, RIG, STEREOSCOPE
from wl_xcon import demoscreen, exact, pointer, viewport
from wl_xcon.geometry import separation_deg, stand_in_housings
from wl_xcon.link import Drawn, DrawnWindow, decode, encode
from wl_xcon.photometry import SRGB, Gray, to_xyz
from wl_xcon.task import (
    After, Array, Disc, Noise, ObjectWindows, On, Outcome, P, Picture, Show, State, Stimulus, Trial,
    Window,
)

_SPEC = importlib.util.spec_from_file_location(
    "wlx_measure_demo_drawing_for_the_drawing",
    Path(__file__).resolve().parents[1] / "tools" / "measure_demo_drawing.py")
measured = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(measured)

FRAME = 1 / 240
SVG = "{http://www.w3.org/2000/svg}"
#: A preview small enough to draw quickly: the drawing's rules hold at any width.
SMALL = 96
#: The caption, as §4.4's table has it, for frame 7.
CAPTION_7 = ("demo · the exact drawer's frame 7 · not the rig's panel: color and luminance "
             "approximate · not timing-valid")

DOT = Stimulus("dot", at=(0.0, 0.0), looks=Disc(size=0.5, color=Gray(40.0)))
GOAL = Stimulus("goal", at=(8.0, 4.0), looks=Disc(size=2.0, color=Gray(60.0)))
UP = Stimulus("up", at=(0.0, 5.0), looks=Disc(size=2.0, color=Gray(80.0)))
#: An array of three, its target object 0.
RING = Array(n=3, radius=6.0, looks=Disc(size=1.0, color=Gray(50.0)),
             among=Disc(size=1.0, color=Gray(20.0)))
SEARCH = Stimulus("ring", at=(0.0, 0.0), looks=RING)
#: A trial on a gray background, whose windows are the dot's, the goal's at (8°, 4°), and the
#: array's objects', its target's, `ring.0`, flagged.
TRIAL = Trial(
    start="a",
    background=Gray(10.0),
    windows=[Window("fix", at=(0.0, 0.0), radius=2.0, on="dot"),
             Window("goal", at=(8.0, 4.0), radius=1.5, on="goal"),
             ObjectWindows(of="ring", radius=1.0)],
    states=[State("a", enter=[Show(DOT)], go=[On(After(1.0), "b", do=[Show(SEARCH), Show(GOAL)])]),
            State("b", go=[On(After(1.0), Outcome.CORRECT)])],
)


def _world(trial: Trial, values=None) -> pointer.Pointing:
    """One trial's world as a demo makes it, its pointer reporting nothing."""
    source = pointer.Source(lambda buffer: -1, seed=1, noise_deg=0.0)
    pace = pointer.Pace(FRAME, clock=lambda: 0.0, sleep=lambda seconds: None)
    return pointer.worlds(source, pace=pace)(trial, values or {}, 0)


def _drawn(visible, *, trial=TRIAL, geometry=DIRECT, rig=RIG, values=None, frame=7,
           stand_in=True) -> Drawn:
    """Frame `frame` showing `visible`, as a demo's world publishes it."""
    world = _world(trial, values)
    world.display(visible, frame)
    drawing = pointer.Drawing(rig, geometry, SRGB, session_id="demo-1",
                              stand_in=stand_in and geometry.view == "direct")
    return drawing.drawn(world, visible, values or {}, trial, 0, frame)


def _svg(drawn, **kwargs) -> ET.Element:
    """The drawing, parsed as XML: it must be well formed, and ASCII alone."""
    text = demoscreen.render(drawn, **kwargs)
    assert text.isascii()
    return ET.fromstring(text)


def _eyes(root) -> list:
    return root.findall(f"{SVG}g[@class='eye']")


def _words(element) -> str:
    return "".join(element.itertext())


def _png(data: bytes) -> np.ndarray:
    """A PNG read back by hand: its signature, each chunk's CRC, an 8-bit RGB header, unfiltered
    rows. The codes, `(rows, cols, 3)`."""
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    at, kinds, header, idat = 8, [], None, b""
    while at < len(data):
        (length,) = struct.unpack(">I", data[at:at + 4])
        kind, body = data[at + 4:at + 8], data[at + 8:at + 8 + length]
        (crc,) = struct.unpack(">I", data[at + 8 + length:at + 12 + length])
        assert zlib.crc32(kind + body) & 0xFFFFFFFF == crc
        kinds.append(kind)
        if kind == b"IHDR":
            header = struct.unpack(">IIBBBBB", body)
        elif kind == b"IDAT":
            idat += body
        at += 12 + length
    assert kinds == [b"IHDR", b"sRGB", b"IDAT", b"IEND"]
    cols, rows, depth, color, compression, filtering, interlace = header
    assert (depth, color, compression, filtering, interlace) == (8, 2, 0, 0, 0)
    raw = np.frombuffer(zlib.decompress(idat), dtype=np.uint8).reshape(rows, 1 + 3 * cols)
    assert (raw[:, 0] == 0).all()
    return raw[:, 1:].reshape(rows, cols, 3)


def _image(eye) -> np.ndarray:
    (image,) = eye.findall(f"{SVG}image")
    href = image.get("href")
    assert href.startswith("data:image/png;base64,")
    return _png(base64.b64decode(href.split(",", 1)[1]))


def _codes(screen, vp) -> np.ndarray:
    """What the image must be: the exact drawer at `vp` through sRGB, rounded to 8 bits."""
    levels = exact.output_levels(exact.draw(screen, vp, supersample=demoscreen.SUPERSAMPLE), SRGB)
    return np.rint(levels * 255.0).astype(np.uint8)


def _translate(eye) -> tuple[float, float]:
    """The eye group's placement: `translate(tx,ty) scale(1,-1)`, exactly."""
    found = re.fullmatch(r"translate\(([^,]+),([^)]+)\) scale\(1,-1\)", eye.get("transform"))
    assert found, eye.get("transform")
    return float(found.group(1)), float(found.group(2))


def _points(polygon) -> list[tuple[float, float]]:
    return [tuple(float(v) for v in pair.split(",")) for pair in polygon.get("points").split()]


# --- The preview ------------------------------------------------------------------------------


@pytest.mark.parametrize("geometry", [DIRECT, STEREOSCOPE], ids=["direct", "stereoscope"])
@pytest.mark.parametrize("width", [480, 641, 960, SMALL])
def test_a_preview_viewport_is_the_one_viewports_makes_at_those_pixels(geometry, width):
    """§4.4: a preview is the rig's panel at fewer pixels, the same centimeters and degrees, as
    `viewport.viewports(rig, geometry, pixels=...)` makes it -- made from the `Drawn`'s viewport
    alone, which is what `wlx serve` has -- its width the whole panel's, both eyes' through the
    stereoscope, and its height the panel's height to its width, rounded."""
    height = round(width * RIG.panel_height_cm / RIG.panel_width_cm)
    wanted = viewport.viewports(RIG, geometry, pixels=(width, height))
    got = tuple(viewport.preview(vp, width) for vp in viewport.viewports(RIG, geometry))
    assert len(got) == len(wanted)
    for made, want in zip(got, wanted):
        assert (made.eye, made.width_px, made.height_px) == (want.eye, want.width_px,
                                                             want.height_px)
        assert made.pitch_cm == pytest.approx(want.pitch_cm, rel=1e-12)
        assert (made.distance_cm, made.ahead_cm) == (want.distance_cm, want.ahead_cm)
    ahead = replace(RIG, straight_ahead_cm=(3.0, -2.0))
    (vp,) = viewport.viewports(ahead, ahead.direct())
    assert viewport.preview(vp, width).ahead_cm == (3.0, -2.0)
    # The preview the measurement drew is the one the page's drawing draws.
    if geometry is DIRECT:
        timed = measured.preview_viewport(RIG, DIRECT, width)
        assert (timed.width_px, timed.height_px) == (got[0].width_px, got[0].height_px)
        assert timed.pitch_cm == pytest.approx(got[0].pitch_cm, rel=1e-12)


def test_a_preview_is_a_whole_number_of_pixels_for_each_eye():
    (direct,) = viewport.viewports(RIG, DIRECT)
    left, _ = viewport.viewports(RIG, STEREOSCOPE)
    for vp, bad in ((direct, 0), (direct, 2.0), (direct, True), (left, 1)):
        with pytest.raises(ValueError, match="a preview is a whole number of pixels wide"):
            viewport.preview(vp, bad)
    assert viewport.preview(direct, 1).width_px == 1
    assert viewport.preview(left, 2).width_px == 1


# --- The image --------------------------------------------------------------------------------


def test_the_image_is_exact_draw_at_the_preview_through_srgb_pixel_for_pixel():
    """§4.4: the image is the exact drawer's frame at the preview, its light through the default
    calibration, the sRGB standard, rounded to 8 bits: a PNG, 8-bit RGB, tagged sRGB, that reads
    back to exactly those codes. The goal's light is drawn where it is."""
    drawn = _drawn({"dot": DOT, "goal": GOAL})
    (eye,) = _eyes(_svg(drawn, width_px=SMALL))
    vp = viewport.preview(drawn.viewports[0], SMALL)

    codes = _image(eye)

    assert codes.shape == (vp.height_px, vp.width_px, 3)
    assert np.array_equal(codes, _codes(drawn.screen, vp))
    background = np.rint(exact.output_levels(np.array([[to_xyz(Gray(10.0))]]), SRGB) * 255)
    assert (codes == background.astype(np.uint8)).all(axis=2).mean() > 0.9
    assert codes.max() > background.max()
    assert demoscreen.png(np.array([[[0.0, 0.5, 1.0]]])) != demoscreen.png(np.array([[[0, 0, 0.0]]]))
    assert np.array_equal(_png(demoscreen.png(np.array([[[0.0, 0.5, 1.0], [0.2, 1.4, -1.0]]]))),
                          [[[0, 128, 255], [51, 255, 0]]])
    for bad in (np.zeros((2, 2)), np.zeros((0, 2, 3)), np.full((1, 1, 3), np.nan)):
        with pytest.raises(ValueError):
            demoscreen.png(bad)


def test_a_screen_the_drawer_refuses_is_said_with_its_labels_kept():
    """A screen the exact drawer refuses (a retired periphery, which `check` refuses at load) has no
    image: the drawing says why, and its windows and caption are still drawn."""
    drawn = _drawn({"dot": DOT})
    refused = replace(drawn, screen=replace(drawn.screen, periphery="center"))

    root = _svg(refused, width_px=SMALL)

    (eye,) = _eyes(root)
    assert eye.findall(f"{SVG}image") == []
    (said,) = eye.findall(f"{SVG}text[@class='refused']")
    assert _words(said).startswith("the exact drawer did not draw this frame: periphery 'center'")
    names = [g.get("data-name") for g in eye.findall(f"{SVG}g[@class='window']")]
    assert names == [w.name for w in drawn.windows] and "fix" in names
    assert _words(root.find(f"{SVG}text[@class='caption']")) == CAPTION_7


# --- The labels -------------------------------------------------------------------------------


def test_each_label_of_the_table_is_drawn():
    """§4.4's table, in direct view: the caption, verbatim; each window a dashed circle with its
    name, an array's object windows where the trial placed them and its target's labeled *target*,
    the scoring key (§14 item 4); the stand-in housings shaded, labeled *stand-in*; the field's
    edge, the frame of the drawing. Real housings are shaded, not called stand-ins."""
    visible = {"dot": DOT, "ring": SEARCH}
    drawn = _drawn(visible)
    root = _svg(drawn, width_px=SMALL)
    (eye,) = _eyes(root)
    vp = viewport.preview(drawn.viewports[0], SMALL)

    assert _words(root.find(f"{SVG}text[@class='caption']")) == CAPTION_7
    windows = {g.get("data-name"): g for g in eye.findall(f"{SVG}g[@class='window']")}
    assert list(windows) == [w.name for w in drawn.windows]
    assert sorted(windows) == ["fix", "goal", "ring.0", "ring.1", "ring.2"]
    for window in drawn.windows:
        g = windows[window.name]
        (edge,) = g.findall(f"{SVG}polygon")
        assert edge.get("stroke-dasharray") and edge.get("fill") == "none"
        assert len(_points(edge)) == 64
        (name,) = g.findall(f"{SVG}text")
        assert _words(name) == (f"{window.name} · target" if window.target else window.name)
        assert g.get("data-target") == ("true" if window.target else "false")
        x_cm, y_cm = demoscreen.cm_of(vp, window.x_deg, window.y_deg)
        assert (float(g.get("data-x-cm")), float(g.get("data-y-cm"))) == (x_cm, y_cm)
    (target,) = [w for w in drawn.windows if w.target]
    assert target.name == "ring.0"
    placed = RING.positions({}, (0.0, 0.0))[0]
    assert (target.x_deg, target.y_deg) == pytest.approx(placed, abs=1e-12)

    housings = eye.findall(f"{SVG}g[@class='housing']")
    assert len(housings) == 2 and drawn.housings == stand_in_housings(RIG.panel_width_cm)
    for g, housing in zip(housings, drawn.housings):
        assert _words(g) == "stand-in" and g.get("data-stand-in") == "true"
        body = g.find(f"{SVG}rect[@class='housing-body']")
        assert float(body.get("fill-opacity")) > 0
        # On the panel where the housing is: its corner from the panel's bottom-left one.
        w_cm, h_cm = vp.width_px * vp.pitch_cm[0], vp.height_px * vp.pitch_cm[1]
        assert float(body.get("x")) == pytest.approx(-w_cm / 2 + housing.left_cm, abs=1e-6)
        assert float(body.get("y")) == pytest.approx(-h_cm / 2 + housing.bottom_cm, abs=1e-6)
        assert float(body.get("width")) == pytest.approx(housing.right_cm - housing.left_cm,
                                                         abs=1e-6)
    # Names are the task's words, written as text, never as markup.
    odd = replace(drawn, session_id='demo "<&>"', windows=(
        DrawnWindow('a<b & "c"', 0.0, 0.0, 1.0, "both", False),))
    named = _svg(odd, width_px=SMALL)
    assert named.get("data-session") == 'demo "<&>"'
    assert _words(_eyes(named)[0].find(f"{SVG}g[@class='window']")) == 'a<b & "c"'
    real = _svg(replace(drawn, stand_in=False), width_px=SMALL)
    assert [_words(g) for g in _eyes(real)[0].findall(f"{SVG}g[@class='housing']")] == [
        "light sensor", "light sensor"]

    (field,) = eye.findall(f"{SVG}rect[@class='field-edge']")
    w_cm, h_cm = vp.width_px * vp.pitch_cm[0], vp.height_px * vp.pitch_cm[1]
    assert [float(field.get(k)) for k in ("x", "y", "width", "height")] == pytest.approx(
        [-w_cm / 2, -h_cm / 2, w_cm, h_cm], abs=1e-6)
    assert eye.findall(f"{SVG}g[@class='one-eye']") == []


def test_a_stimulus_shown_to_one_eye_or_with_a_disparity_is_l_or_r():
    """§4.4's table through the stereoscope (§14 item 17): a stimulus shown to one eye is L or R in
    that eye alone; one with a disparity is L and R in each, with its disparity, read from its two
    eyes' directions less the vergence offset the `Drawn` carries; one at zero disparity is not
    labeled. The field's edge is the mask's, ±12° about each eye's axis."""
    visible = {
        "dot": DOT,
        "left_only": Stimulus("left_only", at=(-5.0, 0.0), looks=Disc(size=1.0, color=Gray(40.0)),
                              eye="left"),
        "deep": Stimulus("deep", at=(5.0, 0.0), looks=Disc(size=1.0, color=Gray(40.0)),
                         disparity=0.4),
    }
    trial = replace(TRIAL, windows=[Window("fix", at=(0.0, 0.0), radius=2.0, on="dot")])
    drawn = _drawn(visible, trial=trial, geometry=STEREOSCOPE)
    assert drawn.vergence_half_deg == STEREOSCOPE.vergence_half_deg > 1.0
    assert decode(encode(drawn)).vergence_half_deg == drawn.vergence_half_deg

    left, right = _eyes(_svg(drawn, width_px=SMALL))

    def labels(eye):
        return {g.get("data-name"): _words(g) for g in eye.findall(f"{SVG}g[@class='one-eye']")}

    assert labels(left) == {"left_only": "L", "deep": "L · disparity 0.4°"}
    assert labels(right) == {"deep": "R · disparity 0.4°"}
    for eye in (left, right):
        vp = viewport.preview(drawn.viewports[0], SMALL)
        reach = vp.distance_cm * math.tan(math.radians(12.0))
        (field,) = eye.findall(f"{SVG}rect[@class='field-edge']")
        # The mask is narrower than the eye's half of the panel, and than its height.
        w_cm, h_cm = vp.width_px * vp.pitch_cm[0], vp.height_px * vp.pitch_cm[1]
        assert reach < w_cm / 2 < h_cm / 2
        assert [float(field.get(k)) for k in ("x", "y", "width", "height")] == pytest.approx(
            [-reach, -reach, 2 * reach, 2 * reach], abs=1e-6)
        assert eye.findall(f"{SVG}g[@class='housing']") == []
    # Without the vergence offset, the dot at zero disparity would read as one, and the deep one's
    # as another number.
    flat = _eyes(_svg(replace(drawn, vergence_half_deg=0.0), width_px=SMALL))[1]
    assert "dot" in labels(flat) and labels(flat)["deep"] != "R · disparity 0.4°"


def test_an_undrawable_kind_and_a_look_with_no_value_are_outlined_with_why():
    """§4.4's table (§14 item 3): a stimulus the drawer does not draw yet and a look with no value
    are each a solid outline of its size where it is -- its true-angle circle, half its size about
    its position -- labeled with its name and why, in each eye; the rest of the screen is drawn."""
    visible = {
        "dot": DOT,
        "picture": Stimulus("picture", at=(4.0, 4.0), looks=Picture(size=3.0)),
        "odd": Stimulus("odd", at=(-4.0, 0.0), looks=P("odd_color")),
        "noise": Stimulus("noise", at=(0.0, -6.0), looks=Noise(aperture=2.0)),
    }
    drawn = _drawn(visible)
    assert [item.name for item in drawn.screen.items] == ["dot"]
    (eye,) = _eyes(_svg(drawn, width_px=SMALL))
    vp = viewport.preview(drawn.viewports[0], SMALL)

    found = {g.get("data-name"): g for g in eye.findall(f"{SVG}g[@class='undrawn']")}

    assert list(found) == ["picture", "odd", "noise"]
    assert _words(found["picture"]) == "picture: not drawn yet: Picture is drawn in engine build A4"
    assert _words(found["odd"]) == ("odd: it has no value to be drawn with: no value bound for "
                                    "parameter 'odd_color'")
    assert _words(found["noise"]) == "noise: not drawn yet: Noise is drawn in engine build A3"
    for outline in drawn.outlines:
        (edge,) = found[outline.name].findall(f"{SVG}polygon")
        assert edge.get("stroke-dasharray") is None and edge.get("fill") == "none"
        points = _points(edge)
        assert len(points) == 64
        for x_cm, y_cm in points:
            at = demoscreen.degrees_of(vp, x_cm, y_cm)
            assert separation_deg(*at, outline.x_deg, outline.y_deg) == pytest.approx(
                outline.size_deg / 2, abs=1e-5)


# --- Coordinates ------------------------------------------------------------------------------


def test_coordinates_are_cm_with_y_up_and_turn_into_degrees_as_geometry_maps_them():
    """§4.4 and the PI's rule of 2026-10-19 (no average pixels-per-degree): an eye's group is the
    panel's centimeters from its straight-ahead point, +y up, placed by its transform where that
    point is on the panel; the page turns a point there into degrees by `atan(x_cm / D)` per axis
    from the group's `data-distance-cm`. A window at (8°, 4°) goes out and back within 1e-9, through
    the transform too; its circle is its true-angle circle; a stimulus at +5° is drawn above the
    center, the image on the panel wherever the straight-ahead point is."""
    ahead = replace(RIG, straight_ahead_cm=(3.0, -2.0))
    drawn = _drawn({"dot": DOT, "up": UP}, rig=ahead, geometry=ahead.direct())
    root = _svg(drawn, width_px=SMALL)
    (eye,) = _eyes(root)
    vp = viewport.preview(drawn.viewports[0], SMALL)
    d = float(eye.get("data-distance-cm"))
    assert d == DIRECT.viewing_distance_cm
    assert (float(eye.get("data-ahead-x-cm")), float(eye.get("data-ahead-y-cm"))) == (3.0, -2.0)

    goal = eye.find(f"{SVG}g[@data-name='goal']")
    x_cm, y_cm = float(goal.get("data-x-cm")), float(goal.get("data-y-cm"))
    assert x_cm > 0 and y_cm > 0
    assert (math.degrees(math.atan(x_cm / d)), math.degrees(math.atan(y_cm / d))) == pytest.approx(
        (8.0, 4.0), abs=1e-9)
    assert demoscreen.degrees_of(vp, *demoscreen.cm_of(vp, 8.0, 4.0)) == pytest.approx(
        (8.0, 4.0), abs=1e-9)
    # Through the group's transform, as the page inverts it: the panel's cm from its top-left
    # corner, y down, and back.
    tx, ty = _translate(eye)
    outer = (tx + x_cm, ty - y_cm)
    back = (outer[0] - tx, ty - outer[1])
    assert (math.degrees(math.atan(back[0] / d)), math.degrees(math.atan(back[1] / d))) == \
        pytest.approx((8.0, 4.0), abs=1e-9)
    # The straight-ahead point is the panel's center moved by `ahead_cm` (x right, y up).
    w_cm, h_cm = vp.width_px * vp.pitch_cm[0], vp.height_px * vp.pitch_cm[1]
    assert (tx, ty) == pytest.approx((w_cm / 2 + 3.0, h_cm / 2 + 2.0), abs=1e-12)
    # Its circle: each point 1.5° of true angle from its center.
    (edge,) = goal.findall(f"{SVG}polygon")
    for px, py in _points(edge):
        assert separation_deg(*demoscreen.degrees_of(vp, px, py), 8.0, 4.0) == pytest.approx(
            1.5, abs=1e-5)

    # The image fills the panel, its first row at the top, whatever the straight-ahead point.
    (image,) = eye.findall(f"{SVG}image")
    assert image.get("transform") == "scale(1,-1)" and image.get("preserveAspectRatio") == "none"
    left, top = tx + float(image.get("x")), ty + float(image.get("y"))
    assert (left, top) == pytest.approx((0.0, 0.0), abs=1e-6)
    assert (float(image.get("width")), float(image.get("height"))) == pytest.approx((w_cm, h_cm),
                                                                                    abs=1e-6)
    # The stimulus at +5°, drawn above the center: where its light is, in the image's rows.
    codes = _image(eye).astype(int).sum(axis=2)
    # The disc at +5° is white (80 cd/m², sRGB's), the dot at the center not.
    rows, cols = np.nonzero(codes > 700)
    assert rows.size
    row_cm = (vp.height_px / 2 - (rows.mean() + 0.5)) * vp.pitch_cm[1] - vp.ahead_cm[1]
    col_cm = ((cols.mean() + 0.5) - vp.width_px / 2) * vp.pitch_cm[0] - vp.ahead_cm[0]
    assert row_cm > 0
    assert (col_cm, row_cm) == pytest.approx(demoscreen.cm_of(vp, 0.0, 5.0),
                                             abs=vp.pitch_cm[0])


def test_the_stereoscope_draws_each_eye_side_by_side():
    """§4.4: through the stereoscope each eye is its own group, left then right, side by side as the
    panel holds its halves, each centimeters from its own eye's straight-ahead point at its half's
    center, at its own path `D`; each image the exact drawer's for that eye, a stimulus shown to the
    left eye alone in the left image alone; each window in the eyes it is judged for."""
    visible = {"dot": DOT, "left_only": Stimulus("left_only", at=(-5.0, 0.0),
                                                 looks=Disc(size=2.0, color=Gray(80.0)),
                                                 eye="left")}
    trial = replace(TRIAL, windows=[Window("fix", at=(0.0, 0.0), radius=2.0, on="dot"),
                                    Window("seen", at=(-5.0, 0.0), radius=1.5, on="left_only",
                                           eye="left")])
    drawn = _drawn(visible, trial=trial, geometry=STEREOSCOPE)
    root = _svg(drawn, width_px=SMALL)
    left, right = _eyes(root)
    vps = [viewport.preview(vp, SMALL) for vp in drawn.viewports]

    assert [eye.get("data-eye") for eye in (left, right)] == ["left", "right"]
    w_cm = vps[0].width_px * vps[0].pitch_cm[0]
    h_cm = vps[0].height_px * vps[0].pitch_cm[1]
    assert _translate(left) == pytest.approx((w_cm / 2, h_cm / 2), abs=1e-12)
    assert _translate(right) == pytest.approx((3 * w_cm / 2, h_cm / 2), abs=1e-12)
    view = [float(v) for v in root.get("viewBox").split()]
    assert view[:3] == pytest.approx([0.0, 0.0, 2 * w_cm], abs=1e-12)
    for eye, vp in zip((left, right), vps):
        assert float(eye.get("data-distance-cm")) == STEREOSCOPE.viewing_distance_cm
        assert np.array_equal(_image(eye), _codes(drawn.screen, vp))
    lit_left, lit_right = (_image(eye).astype(int).sum(axis=2) for eye in (left, right))
    # The left-only disc is white; nothing in the right eye is.
    assert (lit_right > 600).sum() == 0 < (lit_left > 600).sum()
    assert [g.get("data-name") for g in left.findall(f"{SVG}g[@class='window']")] == ["fix", "seen"]
    assert [g.get("data-name") for g in right.findall(f"{SVG}g[@class='window']")] == ["fix"]


# --- Blank ------------------------------------------------------------------------------------


def test_a_blank_drawn_is_the_background_alone():
    """§3.9: a trial's end is published blank, as the animal's screen is until the next trial's
    first frame, the background by default (engine spec §3.3 item 9). Its drawing is the background
    alone -- the last screen's, which `Drawer` keeps, or black where none was drawn -- with no
    window, outline or stimulus label; the caption, the housings and the field's edge stay."""
    world = _world(TRIAL)
    drawing = pointer.Drawing(RIG, DIRECT, SRGB, session_id="demo-1", stand_in=True)
    blank = drawing.blank(world, 0, 240)
    gray = to_xyz(Gray(10.0))

    for background, light in ((None, (0.0, 0.0, 0.0)), ((gray, gray), gray)):
        root = _svg(blank, width_px=SMALL, background=background)
        (eye,) = _eyes(root)
        codes = _image(eye)
        want = np.rint(exact.output_levels(np.array([[light]]), SRGB) * 255).astype(np.uint8)
        assert (codes == want).all()
        for kind in ("window", "undrawn", "one-eye"):
            assert eye.findall(f"{SVG}g[@class='{kind}']") == []
        assert len(eye.findall(f"{SVG}g[@class='housing']")) == 2
        assert len(eye.findall(f"{SVG}rect[@class='field-edge']")) == 1
        assert "frame 240 " in _words(root.find(f"{SVG}text[@class='caption']"))
    assert want.max() > 0

    drawings: list = []
    done = threading.Event()

    def kept(drawn, svg):
        drawings.append(svg)
        if len(drawings) == 2:
            done.set()

    drawer = demoscreen.Drawer(kept, width_px=SMALL)
    try:
        drawer.offer(_drawn({"dot": DOT}))
        _wait_for(lambda: len(drawings) == 1)
        drawer.offer(blank)
        assert done.wait(30.0)
    finally:
        drawer.close()
    (eye,) = _eyes(ET.fromstring(drawings[1]))
    assert (_image(eye) == want).all()


# --- The thread -------------------------------------------------------------------------------


def _wait_for(condition, patience: float = 30.0) -> None:
    """Until `condition()` holds, or fail: well past any drawing here, so a slow computer is never
    read as a fault, and a hang is."""
    ready = threading.Event()
    deadline = patience
    step = 0.005
    while not condition():
        if deadline <= 0:
            pytest.fail("the drawer never got there")
        ready.wait(step)
        deadline -= step


def _blocking(monkeypatch):
    """`render` replaced by one that waits on drawing 1 until released, recording each drawing's
    frame as it starts."""
    started: list = []
    release = threading.Event()

    def held(drawn, *, width_px, background=None):
        started.append(drawn.frame)
        if drawn.frame == 1:
            assert release.wait(30.0)
        if drawn.frame == 99:
            raise RuntimeError("a fault in the drawing")
        return f"<svg>{drawn.frame}</svg>"

    monkeypatch.setattr(demoscreen, "render", held)
    return started, release


def test_a_newer_screen_during_a_drawing_replaces_the_one_waiting(monkeypatch):
    """§4.4 (Review Focus 6): screens faster than drawings -- a drawing in progress finishes, and of
    the screens offered meanwhile only the newest is drawn next, each handed on in the order drawn,
    on the drawer's own thread."""
    started, release = _blocking(monkeypatch)
    handed: list = []
    threads: set = set()

    def on_drawn(drawn, svg):
        threads.add(threading.current_thread().name)
        handed.append((drawn.frame, svg))

    frames = {n: replace(_drawn({"dot": DOT}), frame=n) for n in (1, 2, 3, 4)}
    drawer = demoscreen.Drawer(on_drawn, width_px=SMALL)
    try:
        drawer.offer(frames[1])
        _wait_for(lambda: started == [1])
        for n in (2, 3, 4):
            drawer.offer(frames[n])
        release.set()
        _wait_for(lambda: len(handed) == 2)
    finally:
        drawer.close()
    assert started == [1, 4]
    assert handed == [(1, "<svg>1</svg>"), (4, "<svg>4</svg>")]
    assert threads == {"demoscreen.Drawer"}


def test_a_drawing_that_fails_is_said_and_the_next_is_drawn(monkeypatch):
    """A drawing that raises is handed on as one that failed, saying why, never a thread ended
    quietly with the page left on the last screen; the next screen is drawn."""
    started, release = _blocking(monkeypatch)
    release.set()
    handed: list = []
    drawer = demoscreen.Drawer(lambda drawn, svg: handed.append(svg), width_px=SMALL)
    try:
        drawer.offer(replace(_drawn({"dot": DOT}), frame=99))
        _wait_for(lambda: len(handed) == 1)
        drawer.offer(replace(_drawn({"dot": DOT}), frame=5))
        _wait_for(lambda: len(handed) == 2)
    finally:
        drawer.close()
    root = ET.fromstring(handed[0])
    assert _words(root.find(f"{SVG}text[@class='refused']")) == (
        "this frame could not be drawn: RuntimeError: a fault in the drawing")
    assert "frame 99 " in _words(root.find(f"{SVG}text[@class='caption']"))
    assert handed[1] == "<svg>5</svg>"


def test_close_lets_a_drawing_finish_and_drops_what_waits(monkeypatch):
    """`close` ends the thread: the drawing in progress finishes and is handed on, the screen
    waiting is dropped, and an offer after it is dropped too."""
    started, release = _blocking(monkeypatch)
    handed: list = []
    drawer = demoscreen.Drawer(lambda drawn, svg: handed.append(drawn.frame), width_px=SMALL)
    drawer.offer(replace(_drawn({"dot": DOT}), frame=1))
    _wait_for(lambda: started == [1])
    drawer.offer(replace(_drawn({"dot": DOT}), frame=2))
    closing = threading.Thread(target=drawer.close)
    closing.start()
    _wait_for(lambda: drawer._closed)
    release.set()
    closing.join(30.0)
    assert not closing.is_alive() and not drawer._thread.is_alive()
    drawer.offer(replace(_drawn({"dot": DOT}), frame=3))
    assert started == [1] and handed == [1]
