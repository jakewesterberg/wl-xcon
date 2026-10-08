# Spike S, part 2: the presentation-timing run (2026-10-08)

Run by the PI on wh-dws0 at the text console (desktop logged out), 2026-10-08 19:51 CEST, with the
program built 2026-10-07 (`tools/spike_vulkan/timing/`, run as
`~/wl-spike-s/timing/target/release/timing`, default 1200 frames). Files copied by the controller over
SSH the same minute; sha256: `run-20261008T175126Z.csv` 707f9e14eb1419b3…, `run-20261008T175126Z.txt`
d3ebcca4fcba1291….

## What was measured

The NVIDIA driver's own present-timing timestamps (VK_EXT_present_timing, stage
IMAGE_FIRST_PIXEL_OUT), converted to CLOCK_MONOTONIC, for 1200 frames of a steady gray screen with a
100×100 px corner square alternating black/white every frame, on the Samsung Odyssey G8 (DP-0) at
3840×2160, 120.000 Hz, through a display-plane surface (no DRM acquire needed), FIFO, 3 images.

**These are driver timestamps, not light.** They show when the GPU sent each frame's first pixel out of
the connector, not when the panel lit; no photodiode was connected. The G8 is the PI's desktop monitor,
not the rig's PG27UCDM.

## Results (from `run-20261008T175126Z.txt`, recomputed by the controller from the CSV)

- 1200 of 1200 frames presented in 10.040 s; 1200 of 1200 with a complete timing report.
- Intervals between successive first-pixel-out times: n 1199, median 8.3333 ms; the CSV's
  monotonic-converted values span 0.03 µs (the summary's percentile columns give min 8.3333, max
  8.3336 ms). **Missed frames (interval > 12.5 ms): 0.**
- Time-domain calibration: SWAPCHAIN_LOCAL to CLOCK_MONOTONIC, max deviation 3.1 µs, drift 4.2 µs over
  the run.
- CPU present call → first pixel out: median 39.4 ms (min 16.6, max 85.8): the FIFO queue with three
  images held frames several refreshes ahead; an engine choosing its queue depth would shorten this.
- Vblank counter: 1194 vblanks between frames 4 and 1199 (1195 frames): one step of 0 between frames 4
  and 5 while the queue filled, read at the present call; no missed frame in the first-pixel-out times.
- The corner square looked steady gray to the PI, as expected at 120 Hz.

## What happened after

When the program released the display the monitor showed no signal and turned off (the PI's report);
the program had finished normally (exit, results written, no process left).
