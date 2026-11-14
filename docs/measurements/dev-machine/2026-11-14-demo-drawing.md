# A demo's drawing -- how long the exact drawer takes at a preview's size, on a development machine

> **Followed by `2026-11-14-demo-drawing-preview.md`** (same day): the preview's own drawing,
> `demoscreen.draw`, is the exact drawer's image bit for bit and drew within the interval, and the
> preview's size is now chosen from that record. This one stands as what the exact drawer alone
> takes.

> **This is not a rig measurement, and not a frame time.** It times the exact drawer drawing one
> screen on a development machine, with whatever else ran on it. It is a display choice for a
> demo's preview on this machine (demo mode §4.4). It says nothing about a rig, about the display
> process (engine build E), or about a machine or a screen it was not run on.

**Date:** 2026-11-14, 08:56:08 to 09:12:31 local time (UTC−5), from `results.json`.

**Script:** `tools/measure_demo_drawing.py`, run as
`python tools/measure_demo_drawing.py --out docs/measurements/dev-machine/2026-11-14-demo-drawing`
from this checkout at `06921a1`.
- The script as it ran is copied beside its output, as `2026-11-14-demo-drawing/measure_demo_drawing.py`.
  Its sha256, `3ba575d8…`, is in `results.json` and is the committed script's.
- So is the rig file it read, `tasks/rig.py`, as `rig.py` (sha256 `cad9355e…`).
- The raw output, every drawing's time, is `results.json`. `table.md` and `stdout.txt` are what the
  script printed; the last line of `stdout.txt`, `exit 0`, is the shell's.

**Code:** `wl_xcon` at `06921a1` and `wl_xcon/demoscreen.py` holding `GAZE_EVERY_MS` alone, the
modules imported as the run began.
- `results.json`'s `git_status` was read as the run ended. It lists this build's other files, which
  were being written meanwhile.
- None of them was read by the run after it began. Python imports a module once, and
  `viewport.viewports`, `exact` and `screen` were not changed.

**Host:** macOS-27.0.1-arm64, 14 CPUs. Other agents' work ran on it throughout, so its load was not
controlled. The one-minute load average was:
- 5.5 before the run and 10.4 after it;
- from 4.9 to 17.1 at the rounds' starts.

**Python:** 3.13.9. **numpy:** 2.3.5. The collector was on, as it is in `wlx serve`'s thread.

## What was measured

**The screen:** the pop-out search's heaviest, from wl-xtasks `tasks/popout_search.py` at its commit
`64929fe`, whose sha256 is in `results.json`.
- Its ring at its most discs, `set_size` 12, the setting's top, and its fixation point: thirteen
  flat discs.
- Every other setting at its start, and the pool's first pairing.
- The pop-out never shows the point with the ring (they swap on the go's frame), so this screen holds
  more than any frame it shows.

**How the screen was resolved:** as a demo's world resolves a frame, by `screen.resolve` through the
default calibration, the sRGB standard. It was resolved against `tasks/rig.py`'s direct view at
50 cm, with the stand-in housings in place of the rig's own, which are unmeasured (demo mode §3.6).

**The previews:** each is `viewport.viewports(rig, direct, pixels=(width, height))`.
- The height is the width times the panel's 33.293 cm over its 58.997 cm, rounded.
- This is the viewport `viewport.preview` gives the page's drawing; `tests/test_demoscreen.py` holds
  the two equal.

**The timing:**
- Each pair was drawn once untimed.
- Then came fifty rounds of all six pairs in turn, so a change in the host's load fell on all of
  them alike.
- **`exact.draw` alone is the time the choice reads.** `exact.output_levels` through sRGB, the step
  after it, was timed apart.
- The clock was `time.perf_counter`. The 95th percentile is numpy's, by linear interpolation.

| width × height (px) | supersample | samples | draw median (ms) | draw p95 (ms) | draw min / max (ms) | levels median (ms) |
|---|---|---|---|---|---|---|
| 480 × 271 | 2 | 520,320 | 495.1 | 611.3 | 463.2 / 689.7 | 9.2 |
| 480 × 271 | 4 | 2,081,280 | 2225.7 | 2519.5 | 2131.2 / 2636.0 | 11.5 |
| 640 × 361 | 2 | 924,160 | 1016.2 | 1182.1 | 938.3 / 1230.7 | 19.2 |
| 640 × 361 | 4 | 3,696,640 | 3841.0 | 4206.3 | 3677.4 / 4311.4 | 16.7 |
| 960 × 542 | 2 | 2,081,280 | 2249.1 | 2476.1 | 2123.9 / 2523.3 | 36.1 |
| 960 × 542 | 4 | 8,325,120 | 8948.4 | 9849.2 | 8771.1 / 9960.7 | 35.3 |

The time follows the samples drawn, about a second per million here: the exact drawer computes every
item over every sample of the viewport (engine spec §4.9: slow on purpose, and never inside a frame).

## What it decides

**The plan's rule:** `demoscreen.PREVIEW_WIDTH_PX` and `demoscreen.SUPERSAMPLE` are the largest pair
whose median `exact.draw` time is at most `demoscreen.GAZE_EVERY_MS`, 100 ms, the page's report
interval. That is, a change is drawn within one report.

**No pair met it on this machine.** The fastest, 480 px at supersample 2, took a median of 495 ms,
about five report intervals.

**So the builder's rule for that case applies: the fastest pair.** The preview is **480 px wide at
supersample 2**. `results.json` records this as `chosen`, with `within_bound: false`, and
`tests/test_measure_demo_drawing.py` holds the two constants to that choice.

**What that means for a demo on this machine:**
- A change of the screen reaches the page about half a second after it reaches `wlx serve`.
- A screen that changes faster than that is drawn at its newest, never queued (`demoscreen.Drawer`).

**What it does not say:** how late the page shows the rig's screen. The telemetry link, the stream and
the browser are not in this measurement.
