"""A demo's screen, as the page shows it (demo mode §4.4; engine spec §23): the exact drawer's frame,
labeled, never the rig's panel.

This commit holds the numbers the drawing is made at, chosen from `tools/measure_demo_drawing.py`'s
measurement; the drawing itself, `render` and the `Drawer` thread, is demo mode's Task 7's next
commit.
"""

from __future__ import annotations

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
