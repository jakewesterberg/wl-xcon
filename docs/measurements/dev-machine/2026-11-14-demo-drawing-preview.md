# A demo's drawing, the preview's own path -- how long it takes at each preview size, on a development machine

> **This is not a rig measurement, and not a frame time.** It times the preview's drawing of one
> screen on a development machine, under a heavy and uncontrolled load. It is a display choice for a
> demo's preview on this machine (demo mode §4.4). It says nothing about a rig, about the display
> process (engine build E), or about a machine or a screen it was not run on.

**Date:** 2026-11-14, 09:49:48 to 09:50:48 local time (UTC−5), from `results.json`.

**Script:** `tools/measure_demo_drawing.py`, run as
`python tools/measure_demo_drawing.py --drawer preview --out docs/measurements/dev-machine/2026-11-14-demo-drawing-preview`
from this checkout at `5ea1dad`.
- The script as it ran is copied beside its output, as `2026-11-14-demo-drawing-preview/measure_demo_drawing.py`.
  Its sha256, `0aeb4579…`, is in `results.json` and is the committed script's.
- So is the rig file it read, `tasks/rig.py`, as `rig.py` (sha256 `cad9355e…`, unchanged since the
  first measurement).
- The raw output, every drawing's time, is `results.json`. `table.md` and `stdout.txt` are what the
  script printed; the last line of `stdout.txt`, `exit 0`, is the shell's.

**Code:** `wl_xcon` at `5ea1dad`, which holds `demoscreen.draw`. The only uncommitted files, listed in
`results.json`'s `git_status`, were the script and its tests, committed with this record.

**Host:** macOS-27.0.1-arm64, 14 CPUs. Other agents' test suites ran on it throughout, so its load
was not controlled, and it was heavy. The one-minute load average was:
- 10.8 before the run and 63.4 after it;
- from 9.9 to 63.4 at the rounds' starts, with a median of 38.5.

The first measurement ran at 4.9 to 17.1.

**Python:** 3.13.9. **numpy:** 2.3.5. The collector was on.

## What was measured

**The screen and the previews:** the same as the first measurement's,
`2026-11-14-demo-drawing.md`. That is the pop-out's ring of twelve and its point, on `tasks/rig.py`'s
direct view with the stand-ins, at preview widths 480, 640 and 960 px and supersamples 2 and 4.

**The drawing:** each was `demoscreen.draw`, the preview's own path (the follow-up to Task 7,
XC-507).
- It draws the background once with `exact.draw`.
- Over it, each group of stimuli whose boxes overlap is drawn by `exact.draw` over that group's box
  alone (`region=`).
- **Its kept background was dropped before every drawing**, so every time below includes drawing
  the background over the whole panel, as on the first screen of a new background.

**Held to the exact drawer:** before anything was timed, each pair's drawing was compared with
`exact.draw`'s whole image of the same screen. All six were identical bit for bit
(`identical_to_exact`). `tests/test_demoscreen.py` holds the same over every kind the drawer draws.

**The timing:**
- Each pair was drawn once untimed.
- Then came fifty rounds of all six in turn.
- Timed apart: the drawing, `exact.output_levels` through sRGB, and `demoscreen.png`. The image is
  the three together.
- The clock was `time.perf_counter`. The 95th percentile is numpy's, by linear interpolation.

| width × height (px) | supersample | samples | draw median (ms) | draw p95 (ms) | draw min / max (ms) | levels median (ms) | PNG median (ms) | image median (ms) | image p95 (ms) |
|---|---|---|---|---|---|---|---|---|---|
| 480 × 271 | 2 | 520,320 | 20.3 | 62.8 | 13.7 / 103.5 | 14.3 | 3.4 | 40.6 | 94.4 |
| 480 × 271 | 4 | 2,081,280 | 59.6 | 134.4 | 40.2 / 197.9 | 10.9 | 3.3 | 76.6 | 153.8 |
| 640 × 361 | 2 | 924,160 | 30.4 | 68.8 | 23.4 / 85.9 | 17.7 | 5.8 | 54.3 | 116.1 |
| 640 × 361 | 4 | 3,696,640 | 97.1 | 159.6 | 70.2 / 189.5 | 18.2 | 6.0 | 120.4 | 198.1 |
| 960 × 542 | 2 | 2,081,280 | 71.8 | 132.7 | 51.5 / 227.0 | 46.2 | 16.6 | 132.5 | 226.2 |
| 960 × 542 | 4 | 8,325,120 | 219.3 | 278.3 | 164.6 / 292.8 | 58.6 | 16.6 | 305.4 | 416.8 |

**Against the first measurement:** at 480 px and supersample 2 the drawing's median fell from
495.1 ms (`exact.draw` alone) to 20.3 ms, under a heavier load, its background drawn every time.

## What it decides

**The rule:** `demoscreen.PREVIEW_WIDTH_PX` and `demoscreen.SUPERSAMPLE` are the largest pair (the
widest, then the finer supersample) whose median is at most `demoscreen.GAZE_EVERY_MS`, 100 ms (the
plan's rule).

**The median read is the whole image's.** The drawing is no longer most of the time, so it is the
drawing, the levels and the PNG together (`chosen_by: "image"`; the builder's call).

**Three pairs meet it:** 480 at 2 (40.6 ms), 480 at 4 (76.6 ms) and 640 at 2 (54.3 ms). The largest is
**640 px at supersample 2** (`results.json`'s `chosen`, `within_bound: true`).
`tests/test_measure_demo_drawing.py` holds the two constants to it.

**Two caveats:**
- At this load, 640 at 4 (120.4 ms) and 960 at 2 (132.5 ms) did not fit. Whether they would on a
  quieter host was not measured.
- The 95th percentile of the chosen pair's image, 116.1 ms, is above the interval: under this load,
  6 of its 50 images took longer than a report (2 of 50 at 480 and 2).

**What it does not say:** how late the page shows the rig's screen. The telemetry link, the stream
and the browser are not in this measurement. A screen whose background has not changed skips the
background's drawing, which this record always included and did not time apart.
