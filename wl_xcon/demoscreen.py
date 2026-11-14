"""A demo's screen, as the page shows it (demo mode §4.4; engine spec §23): **the exact drawer's
frame, labeled**, never the rig's panel.

`wlx serve` hands each `link.Drawn` a demo publishes to a `Drawer`, which draws it on a thread of its
own, never in the rig service's process: a drawing in progress finishes, and of the screens that
arrive meanwhile only the newest is drawn next (§4.4; the plan's Review Focus 6). `render` makes one
drawing, an SVG fragment the page shows and steers on:

- **The image is the exact drawer's** (`exact.draw`, engine spec §4.9: the definition of what each
  eye must see) at a preview of the rig's panel, `viewport.preview`: the same centimeters and
  degrees at fewer pixels, each eye side by side through the stereoscope. **In sRGB**: the drawer's
  light through the default calibration, the sRGB standard (`exact.output_levels(image,
  photometry.SRGB)`), clipped where sRGB cannot make it, as the drawer clips, then rounded to
  8 bits, a PNG made with the standard library's `zlib` (`png`).
- **Each eye is one `<g>`, whose user units are the panel's centimeters from that eye's
  straight-ahead point, +y up**, carrying `data-eye`, `data-distance-cm` (`D`, the eye's path to
  the panel), and `data-ahead-x-cm` and `data-ahead-y-cm` (where that point lies from its
  viewport's center, `Viewport.ahead_cm`). The page turns the pointer into degrees as `geometry`
  maps them, `atan(x_cm / D)` per axis (`degrees_of`), from the group's own transform. **Not
  degrees, as the design wrote it** (§4.4, "an SVG fragment whose coordinates are degrees"): one
  linear degree scale over a `D·tan` image is an average pixels-per-degree, which the PI retired
  (2026-10-19: forward calculated "for that specific location rather than using ppd averages"). (The
  plan's call.)
- **Labeled on top, as §4.4's table has it**: the caption, verbatim (`CAPTION`); each window a dashed
  outline of its true-angle circle (`geometry.on_circle_deg`) mapped to centimeters by `D·tan`, at
  `CIRCLE_POINTS` points, with its name, an array's target's object labeled *target*, the scoring
  key (§14 item 4); a stimulus shown to one eye, or with a disparity, L or R in that eye, with its
  disparity when nonzero; what could not be drawn, a solid outline of its size with its name and
  why (§14 item 3); the light sensors' housings shaded, the stand-ins labeled *stand-in*; and the
  field's edge. The page draws the pointer.

**What it is not**: the panel's light (a monitor that is not the rig's shows sRGB as its own), or
anything about timing; the caption says both. How long a drawing takes on the development machine is
`tools/measure_demo_drawing.py`'s, which chose `PREVIEW_WIDTH_PX` and `SUPERSAMPLE`.
"""

from __future__ import annotations

import base64
import html
import math
import struct
import threading
import zlib

import numpy as np

from wl_xcon import exact, viewport
from wl_xcon.geometry import on_circle_deg
from wl_xcon.photometry import SRGB
from wl_xcon.screen import Screen

#: **How often the page reports a still pointer, in milliseconds** (demo mode §3.3, §3.8): the
#: plan's `web.GAZE_EVERY_MS = 100`, which the page (`wl_xcon/web.py`, demo mode's Task 9) takes
#: from here, so the report interval and the preview's size chosen against it never disagree.
#: Five to a `pointer.LIVE_S`, so one late report never reads as tracker loss. The plan's call:
#: playable, claiming nothing about a rig.
GAZE_EVERY_MS = 100

#: **The preview's width in pixels, the whole panel's, and its supersample**: of the pairs
#: `tools/measure_demo_drawing.py` drew (480, 640 and 960 px; 2 and 4), the largest whose median
#: `exact.draw` time was at most `GAZE_EVERY_MS` -- and where none was, the fastest, which is what
#: the development machine measured on 2026-11-14: a median of 495 ms at 480 px and 2
#: (`docs/measurements/dev-machine/2026-11-14-demo-drawing.md`). A display choice for that machine,
#: never a claim about a rig; `tests/test_measure_demo_drawing.py` holds the two to the committed
#: results.
PREVIEW_WIDTH_PX = 480
SUPERSAMPLE = 2

#: The points a window's or an outline's true-angle circle is drawn with: a 64-gon, whose sides
#: bow from the circle by 0.12% of its radius (1 − cos(π/64)), under a preview pixel at any size
#: a window has. (The plan's call.)
CIRCLE_POINTS = 64

#: **The caption, verbatim** (§4.4's table), `{frame}` the frame drawn, counted from its trial's
#: first.
CAPTION = ("demo · the exact drawer's frame {frame} · not the rig's panel: color and "
           "luminance approximate · not timing-valid")

#: **The labels' sizes and colors**, in the panel's centimeters: legible on a dark or a light
#: background at a full-window view (a dark halo under each word), and each element carries a class
#: so the page's own style may set them instead. Display choices, claiming nothing.
LABEL_CM = 0.7
CAPTION_CM = 0.8
#: The band under the panel the caption sits in.
BAND_CM = 1.4
STROKE_CM = 0.12
DASH_CM = "0.6 0.35"
WINDOW_COLOR = "#ffd84d"
TARGET_COLOR = "#ff7ad9"
OUTLINE_COLOR = "#ff6b6b"
EYE_COLOR = "#7fdbff"
HOUSING_COLOR = "#9e9e9e"
FIELD_COLOR = "#bdbdbd"
CAPTION_COLOR = "#e8eaed"
BAND_COLOR = "#000000"

#: Below this, a disparity is none: the two eyes' directions are computed, and a stimulus at zero
#: disparity can differ from it by rounding alone.
_NO_DISPARITY_DEG = 1e-9
_BLACK = (0.0, 0.0, 0.0)


# --- Positions --------------------------------------------------------------------------------


def cm_of(vp, x_deg: float, y_deg: float) -> tuple[float, float]:
    """**A position in per-axis degrees, as centimeters on `vp`'s panel** from its eye's
    straight-ahead point, +y up: `D·tan` per axis, as `geometry` maps every position."""
    d = vp.distance_cm
    return d * math.tan(math.radians(x_deg)), d * math.tan(math.radians(y_deg))


def degrees_of(vp, x_cm: float, y_cm: float) -> tuple[float, float]:
    """**`cm_of` read back**: centimeters from `vp`'s straight-ahead point as per-axis degrees,
    `atan(x_cm / D)` per axis -- what the page does with a pointer over the eye's group, from its
    `data-distance-cm` (demo mode's Task 9)."""
    d = vp.distance_cm
    return math.degrees(math.atan(x_cm / d)), math.degrees(math.atan(y_cm / d))


def _circle(vp, x_deg: float, y_deg: float, radius_deg: float) -> list[tuple[float, float]]:
    """A true circle of `radius_deg` about `(x_deg, y_deg)` (`geometry.on_circle_deg`, as an
    array's objects and a window's angle are measured), its `CIRCLE_POINTS` points in centimeters
    on `vp`'s panel; a point 90° or more off the eye's axis meets no panel ahead, and is left out."""
    points = []
    for k in range(CIRCLE_POINTS):
        x, y = on_circle_deg(x_deg, y_deg, radius_deg, 360.0 * k / CIRCLE_POINTS)
        if abs(x) < 90.0 and abs(y) < 90.0:
            points.append(cm_of(vp, x, y))
    return points


# --- The image --------------------------------------------------------------------------------


def png(levels) -> bytes:
    """**Output levels as an 8-bit RGB PNG**: `(rows, cols, 3)` fractions of full scale, 0 to 1
    (`exact.output_levels`), each rounded to the nearest of 0-255, unfiltered rows, one `IDAT` by
    the standard library's `zlib`, tagged sRGB, which these levels are."""
    levels = np.asarray(levels, dtype=float)
    if levels.ndim != 3 or levels.shape[2] != 3 or levels.shape[0] < 1 or levels.shape[1] < 1:
        raise ValueError(f"a PNG is made of (rows, cols, 3) output levels, not an array of shape "
                         f"{levels.shape}")
    if not np.isfinite(levels).all():
        raise ValueError("an output level that is not a number has no code to round to")
    codes = np.rint(np.clip(levels, 0.0, 1.0) * 255.0).astype(np.uint8)
    rows, cols = codes.shape[:2]
    raw = np.zeros((rows, 1 + 3 * cols), dtype=np.uint8)
    raw[:, 1:] = codes.reshape(rows, 3 * cols)

    def chunk(kind: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + kind + data
                + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF))

    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", cols, rows, 8, 2, 0, 0, 0))
            + chunk(b"sRGB", b"\x00")
            + chunk(b"IDAT", zlib.compress(raw.tobytes(), 6))
            + chunk(b"IEND", b""))


def _shown(drawn, eyes, background) -> Screen:
    """The screen the image is drawn from: the `Drawn`'s, or for a blank one (a trial's end), the
    background alone, `background`'s two lights or black where none is known."""
    if drawn.screen is not None:
        return drawn.screen
    left, right = background or (_BLACK, _BLACK)
    return Screen(setup="direct" if eyes[0].eye == "both" else "stereoscope",
                  periphery="true_angle", background_left=tuple(left),
                  background_right=tuple(right), items=(), frame=drawn.frame, frame_period=0.0)


def _images(drawn, eyes, background):
    """Each eye's PNG, `exact.draw` at the preview through the sRGB standard; or, where the drawer
    refuses the screen (`screen.NotYetDrawable` and the backstops `check` keeps from a loaded task
    are `ValueError`s), none, and why."""
    shown = _shown(drawn, eyes, background)
    try:
        return [png(exact.output_levels(exact.draw(shown, vp, supersample=SUPERSAMPLE), SRGB))
                for vp in eyes], None
    except ValueError as refused:
        return [None] * len(eyes), refused


# --- The SVG ----------------------------------------------------------------------------------


def _esc(words: str) -> str:
    """Words as SVG text or an attribute's value, in ASCII alone (each other character a numeric
    reference), so the fragment reads the same in any page's encoding."""
    return html.escape(str(words), quote=True).encode("ascii", "xmlcharrefreplace").decode("ascii")


def _f(value: float) -> str:
    """A drawn coordinate, in centimeters: to 10 nm."""
    return f"{value:.6f}"


def _exact(value: float) -> str:
    """A number the page computes with: as Python holds it, read back exactly."""
    return repr(float(value))


def _text(x: float, y: float, words: str, kind: str, color: str, *, size: float = LABEL_CM,
          anchor: str = "middle") -> str:
    """Words upright at `(x, y)` in an eye's +y-up centimeters, on a dark halo."""
    return (f'<text class="{kind}" x="{_f(x)}" y="{_f(-y)}" transform="scale(1,-1)" '
            f'font-size="{size}" text-anchor="{anchor}" fill="{color}" stroke="#000000" '
            f'stroke-width="{_f(size * 0.18)}" paint-order="stroke">{_esc(words)}</text>')


def _polygon(points, kind: str, color: str, *, dashed: bool) -> str:
    dash = f' stroke-dasharray="{DASH_CM}"' if dashed else ""
    return (f'<polygon class="{kind}" points="{" ".join(f"{_f(x)},{_f(y)}" for x, y in points)}" '
            f'fill="none" stroke="{color}" stroke-width="{STROKE_CM}"{dash}/>')


def _sees(eye: str, vp) -> bool:
    """Whether a window or a stimulus for `eye` is in `vp`'s eye, as `exact` decides it."""
    return vp.eye == "both" or eye in ("both", vp.eye)


def _windows(drawn, vp) -> list[str]:
    """Each window `vp`'s eye is judged in: its true-angle circle dashed, its name above it, an
    array's target's object labeled *target* (§14 item 4)."""
    parts = []
    for window in drawn.windows:
        if not _sees(window.eye, vp):
            continue
        color = TARGET_COLOR if window.target else WINDOW_COLOR
        points = _circle(vp, window.x_deg, window.y_deg, window.radius_deg)
        x_cm, y_cm = cm_of(vp, window.x_deg, window.y_deg)
        top = max((y for _, y in points), default=y_cm)
        name = f"{window.name} · target" if window.target else window.name
        parts.append(
            f'<g class="window" data-name="{_esc(window.name)}" '
            f'data-target="{"true" if window.target else "false"}" data-eye="{_esc(window.eye)}" '
            f'data-x-cm="{_exact(x_cm)}" data-y-cm="{_exact(y_cm)}">'
            f'{_polygon(points, "window-edge", color, dashed=True)}'
            f'{_text(x_cm, top + 0.25, name, "window-name", color)}</g>')
    return parts


def _outlines(drawn, vp) -> list[str]:
    """What could not be drawn: a solid true-angle circle of its size where it is, with its name
    and why (§14 item 3)."""
    parts = []
    for outline in drawn.outlines:
        points = _circle(vp, outline.x_deg, outline.y_deg, outline.size_deg / 2.0)
        x_cm, y_cm = cm_of(vp, outline.x_deg, outline.y_deg)
        bottom = min((y for _, y in points), default=y_cm)
        why = _text(x_cm, bottom - 0.25 - LABEL_CM, f"{outline.name}: {outline.why}", "undrawn-why",
                    OUTLINE_COLOR)
        parts.append(f'<g class="undrawn" data-name="{_esc(outline.name)}">'
                     f'{_polygon(points, "undrawn-edge", OUTLINE_COLOR, dashed=False)}{why}</g>')
    return parts


def _one_eyed(drawn, vp) -> list[str]:
    """Through the stereoscope, each stimulus not the same to both eyes: L or R in each eye it is
    shown to, with its disparity when nonzero -- the two eyes' horizontal directions apart, less
    the vergence offset that puts zero at the screen's optical distance (`screen._eyes`;
    `geometry.DISPARITY_CONVENTION`, azimuth longitude)."""
    if drawn.screen is None or vp.eye == "both":
        return []
    letter = "L" if vp.eye == "left" else "R"
    parts = []
    for item in drawn.screen.items:
        if not _sees(item.eye, vp):
            continue
        disparity = item.at_right[0] - item.at_left[0] + 2.0 * drawn.vergence_half_deg
        if item.eye == "both" and abs(disparity) <= _NO_DISPARITY_DEG:
            continue
        words = letter
        if abs(disparity) > _NO_DISPARITY_DEG:
            words = f"{letter} · disparity {round(disparity, 3):g}°"
        x_cm, y_cm = cm_of(vp, *(item.at_left if vp.eye == "left" else item.at_right))
        parts.append(f'<g class="one-eye" data-name="{_esc(item.name)}">'
                     f'{_text(x_cm, y_cm - 0.5 - LABEL_CM, words, "eye-label", EYE_COLOR)}</g>')
    return parts


def _housings(drawn, x0: float, y0: float) -> list[str]:
    """The light sensors' housings, shaded where they are on the panel, its bottom-left corner at
    `(x0, y0)`, each margin dotted; the stand-ins labeled *stand-in* (§3.6)."""
    parts = []
    for housing in drawn.housings:
        left, bottom = x0 + housing.left_cm, y0 + housing.bottom_cm
        width, height = housing.right_cm - housing.left_cm, housing.top_cm - housing.bottom_cm
        m = housing.margin_cm
        label = _text(left + width / 2, bottom + height / 2 - LABEL_CM / 3,
                      "stand-in" if drawn.stand_in else "light sensor", "housing-name", "#ffffff")
        parts.append(
            f'<g class="housing" data-stand-in="{"true" if drawn.stand_in else "false"}">'
            f'<rect class="housing-margin" x="{_f(left - m)}" y="{_f(bottom - m)}" '
            f'width="{_f(width + 2 * m)}" height="{_f(height + 2 * m)}" fill="none" '
            f'stroke="{HOUSING_COLOR}" stroke-width="{STROKE_CM}" stroke-dasharray="0.15 0.2"/>'
            f'<rect class="housing-body" x="{_f(left)}" y="{_f(bottom)}" width="{_f(width)}" '
            f'height="{_f(height)}" fill="{HOUSING_COLOR}" fill-opacity="0.55"/>{label}</g>')
    return parts


def _eye(drawn, vp, left_cm: float, panel_h: float, image, refused) -> str:
    """One eye's group, placed `left_cm` from the panel's left edge: its image, the housings, the
    field's edge, what could not be drawn, the one-eyed labels and the windows, in its own +y-up
    centimeters from its straight-ahead point."""
    w_cm, h_cm = vp.width_px * vp.pitch_cm[0], vp.height_px * vp.pitch_cm[1]
    ax, ay = vp.ahead_cm
    # The viewport's extent from the eye's straight-ahead point (`viewport.sample_cm`).
    x0, x1 = -w_cm / 2 - ax, w_cm / 2 - ax
    y0, y1 = -h_cm / 2 - ay, h_cm / 2 - ay
    parts = [
        f'<g class="eye" data-eye="{_esc(vp.eye)}" data-distance-cm="{_exact(vp.distance_cm)}" '
        f'data-ahead-x-cm="{_exact(ax)}" data-ahead-y-cm="{_exact(ay)}" '
        f'transform="translate({_exact(left_cm + w_cm / 2 + ax)},{_exact(panel_h / 2 - ay)}) '
        f'scale(1,-1)">'
    ]
    if image is not None:
        parts.append(
            f'<image class="frame" x="{_f(x0)}" y="{_f(-y1)}" width="{_f(w_cm)}" '
            f'height="{_f(h_cm)}" transform="scale(1,-1)" preserveAspectRatio="none" '
            f'href="data:image/png;base64,{base64.b64encode(image).decode("ascii")}"/>')
    else:
        parts.append(f'<rect class="frame" x="{_f(x0)}" y="{_f(y0)}" width="{_f(w_cm)}" '
                     f'height="{_f(h_cm)}" fill="#000000"/>')
        parts.append(_text((x0 + x1) / 2, (y0 + y1) / 2,
                           f"the exact drawer did not draw this frame: {refused}", "refused",
                           OUTLINE_COLOR))
    parts.extend(_housings(drawn, x0, y0))
    fx0, fx1, fy0, fy1 = x0, x1, y0, y1
    if drawn.mask_deg is not None:
        # The stereoscope's mask stops the field at ±mask_deg per axis about the eye's axis.
        reach = vp.distance_cm * math.tan(math.radians(drawn.mask_deg))
        fx0, fx1, fy0, fy1 = max(x0, -reach), min(x1, reach), max(y0, -reach), min(y1, reach)
    parts.append(f'<rect class="field-edge" x="{_f(fx0)}" y="{_f(fy0)}" width="{_f(fx1 - fx0)}" '
                 f'height="{_f(fy1 - fy0)}" fill="none" stroke="{FIELD_COLOR}" '
                 f'stroke-width="{STROKE_CM}"/>')
    parts.extend(_outlines(drawn, vp))
    parts.extend(_one_eyed(drawn, vp))
    parts.extend(_windows(drawn, vp))
    parts.append("</g>")
    return "".join(parts)


def render(drawn, *, width_px: int = PREVIEW_WIDTH_PX, background=None) -> str:
    """**One drawing of a demo's screen**, an SVG fragment (the module docstring): each eye's group
    side by side as the panel holds them, the exact drawer's frame at a preview `width_px` wide
    through the sRGB standard, §4.4's labels on top, and the caption in a band beneath. A blank
    `Drawn` (a trial's end) is the background alone: `background`'s two lights, left and right, CIE
    XYZ in cd/m², as the last screen drawn had them (`Drawer` keeps them), or black."""
    eyes = tuple(viewport.preview(vp, width_px) for vp in drawn.viewports)
    if not eyes:
        raise ValueError("a drawing with no viewport has no eye to draw")
    widths = [vp.width_px * vp.pitch_cm[0] for vp in eyes]
    panel_w = sum(widths)
    panel_h = max(vp.height_px * vp.pitch_cm[1] for vp in eyes)
    images, refused = _images(drawn, eyes, background)
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" class="demo-drawing" '
        f'viewBox="0 0 {_exact(panel_w)} {_exact(panel_h + BAND_CM)}" '
        f'data-session="{_esc(drawn.session_id)}" data-trial="{drawn.trial}" '
        f'data-frame="{drawn.frame}" font-family="sans-serif">'
    ]
    left = 0.0
    for vp, width, image in zip(eyes, widths, images):
        parts.append(_eye(drawn, vp, left, panel_h, image, refused))
        left += width
    parts.append(f'<rect class="band" x="0" y="{_f(panel_h)}" width="{_f(panel_w)}" '
                 f'height="{BAND_CM}" fill="{BAND_COLOR}"/>')
    parts.append(f'<text class="caption" x="0.4" y="{_f(panel_h + BAND_CM * 0.68)}" '
                 f'font-size="{CAPTION_CM}" fill="{CAPTION_COLOR}">'
                 f'{_esc(CAPTION.format(frame=drawn.frame))}</text>')
    parts.append("</svg>")
    return "".join(parts)


def failed(drawn, why: BaseException) -> str:
    """**A drawing that failed**, said as one (`Drawer`): the caption's band and what went wrong, so
    the page shows why instead of the last screen."""
    said = f"this frame could not be drawn: {type(why).__name__}: {why}"
    return (f'<svg xmlns="http://www.w3.org/2000/svg" class="demo-drawing demo-failed" '
            f'viewBox="0 0 60 {BAND_CM * 2}" data-session="{_esc(drawn.session_id)}" '
            f'data-trial="{drawn.trial}" data-frame="{drawn.frame}" font-family="sans-serif">'
            f'<rect class="band" x="0" y="0" width="60" height="{BAND_CM * 2}" '
            f'fill="{BAND_COLOR}"/>'
            f'<text class="caption" x="0.4" y="{_f(BAND_CM * 0.68)}" font-size="{CAPTION_CM}" '
            f'fill="{CAPTION_COLOR}">{_esc(CAPTION.format(frame=drawn.frame))}</text>'
            f'<text class="refused" x="0.4" y="{_f(BAND_CM * 1.68)}" font-size="{CAPTION_CM}" '
            f'fill="{OUTLINE_COLOR}">{_esc(said)}</text></svg>')


# --- The thread -------------------------------------------------------------------------------


class Drawer:
    """**Draws each screen offered on a thread of its own** (§4.4): `offer` keeps only the newest
    screen waiting, a drawing in progress finishes, and each drawing goes to `on_drawn(drawn, svg)`
    on this thread, in the order drawn. A drawing that raises is handed on as one that failed,
    saying why (`failed`), and the thread draws on. A blank screen is drawn with the last screen's
    background. `close` drops what waits, lets a drawing in progress finish and be handed on, and
    ends the thread; an offer after it is dropped."""

    def __init__(self, on_drawn, *, width_px: int = PREVIEW_WIDTH_PX) -> None:
        self._on_drawn = on_drawn
        self._width_px = width_px
        self._ready = threading.Condition()
        self._waiting = None
        self._closed = False
        #: The last screen drawn's two backgrounds, which a blank one is drawn with.
        self._background = None
        self._thread = threading.Thread(target=self._run, name="demoscreen.Drawer", daemon=True)
        self._thread.start()

    def offer(self, drawn) -> None:
        """Draw `drawn` next, in place of any screen still waiting."""
        with self._ready:
            self._waiting = drawn
            self._ready.notify()

    def close(self) -> None:
        """Drop what waits, let a drawing in progress finish, and end the thread."""
        with self._ready:
            self._closed = True
            self._ready.notify()
        if threading.current_thread() is not self._thread:
            self._thread.join()

    def _run(self) -> None:
        while True:
            with self._ready:
                while self._waiting is None and not self._closed:
                    self._ready.wait()
                if self._closed:
                    # What waits, and any offer from now on, is never drawn.
                    return
                drawn, self._waiting = self._waiting, None
            try:
                svg = render(drawn, width_px=self._width_px, background=self._background)
            except Exception as why:  # noqa: BLE001 -- said on the page; the next screen is drawn
                svg = failed(drawn, why)
            if drawn.screen is not None:
                self._background = (drawn.screen.background_left, drawn.screen.background_right)
            self._on_drawn(drawn, svg)
