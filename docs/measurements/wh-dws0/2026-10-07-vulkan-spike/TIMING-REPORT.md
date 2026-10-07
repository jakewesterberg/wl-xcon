# Spike S, part 2: the presentation-timing program (built 2026-10-07; not yet run on the display)

Report by the agent that built it, saved here by the controller. The program is
`~/wl-spike-s/timing/target/release/timing` on wh-dws0; instructions for the PI in
`~/wl-spike-s/timing/RUN-ME.txt` (sha256 f239fee3512c1151…, identical to `src-copy-timing/RUN-ME.txt`).

## Status

Built, and its failure path tested: with the desktop holding the monitor it asked for the display
three times and was refused cleanly each time. kwin_wayland (PID 15230) and plasmashell (15394) were
unchanged before and after every test; each refusal produced no kernel or udev events, no journal
entries and no output files. Ctrl+C, SIGTERM, SIGHUP and the watchdog exit cleanly. The code that runs
only once it holds the display (time domains, past-presentation results, calibration) has not yet run
against the NVIDIA driver; it is tested off-screen and by a synthetic test.

## What it does (ash 0.38 plus hand-written FFI; no new crates)

- Lists displays, modes and planes; picks DP-0 at its highest refresh (3840×2160 @ 120.000 Hz,
  plane 0); `--mode WxH@HZ` picks another.
- Device extensions: VK_KHR_swapchain, VK_KHR_present_id2, VK_KHR_calibrated_timestamps,
  VK_EXT_present_timing, VK_EXT_display_control.
- Takes the display with a display-plane surface and a FIFO swapchain; if refused, opens the NVIDIA DRM
  node and calls vkAcquireDrmDisplayEXT, then retries (added because in NVIDIA's open-module source,
  tag 615.71.09, with `nvidia_drm.fbdev=Y` — set on this machine — nvidia-drm takes the NvKms display
  ownership at load; whether the plain path is refused even at the console is UNVERIFIED).
- Screen: steady gray (8-bit code 64) with a 100×100 px square in the bottom-left corner alternating
  black/white each frame.
- Per frame: present id; CPU time just before and after vkQueuePresentKHR (CLOCK_MONOTONIC); every
  present-stage time the surface supports, raw and converted to CLOCK_MONOTONIC (time domain preferred
  CLOCK_MONOTONIC > SWAPCHAIN_LOCAL > PRESENT_STAGE_LOCAL; calibration at start and end, drift
  reported); the vblank counter.
- Writes `out/run-<UTC>.csv` and a `.txt` summary (mode, the driver's refresh period, frames presented,
  interval distribution median/min/max/p1/p5/p95/p99, missed frames over 1.5 periods, stages used,
  CPU-present-to-stage latency, vblank count) and prints the summary.
- Default 1200 frames; runs longer than 50 s at the chosen rate rejected; watchdog asks to stop at
  55 s, forces exit at 60 s; teardown on every exit path; nothing printed while holding the display;
  a second Ctrl+C forces exit. Exit codes: 0 ok; 1 error/incomplete; 2 display refused; 124 watchdog;
  128+signal.
- Test options: `--hold-ms N` (pause before asking for the display), `--headless` (off-screen on the AMD
  iGPU), `--list`.

## Code size (non-blank, non-comment)

`main.rs` 715 (plus a 35-line test module; `measure()` about 310), `ffi.rs` 187, `layout_check.rs`
233 (generated), `tools/gen_layout_check.py` about 143.

## FFI checked against Khronos vk.xml

`gen_layout_check.py` reads `dl-vkxml/vk.xml` (VK_HEADER_VERSION 365, sha256 e0af1941…) and writes
compile-time assertions, so a mismatch fails the build: 14 structs (size, alignment, every member's
offset and Rust type on x86_64), 13 sType values, 9 enum and bit values, the four commands' signatures
and name strings, both extension names. Eight deliberate mistakes in a copy each broke the build. Types
ash already provides were not re-checked.

## Failure-path test, final binary (2026-10-07 22:51; desktop active and locked, tty2)

```
surface: presentTimingSupported 1, stages 0x5 (QUEUE_OPERATIONS_END, IMAGE_FIRST_PIXEL_OUT), presentId2Supported 1, vblank counter true, B8G8R8A8_UNORM (of 6 formats), images 2..8
timing: cannot take the display (vkCreateSwapchainKHR: ERROR_INITIALIZATION_FAILED, and without timing: ERROR_INITIALIZATION_FAILED; vkAcquireDrmDisplayEXT: ERROR_INITIALIZATION_FAILED); another program, such as the desktop or the login screen, probably holds it. Nothing was changed.
exit code 2; ran .2177 s
udev/kernel events during the run (1 s before to 3 s after): 0    files written to out/: 0
journal entries since the run: 0 (system), 0 (user)
```

New information part 1 could not get: the NVIDIA display surface supports present timing, with the
stages QUEUE_OPERATIONS_END and IMAGE_FIRST_PIXEL_OUT, so the run will report first-pixel-out.

Signals: Ctrl+C exit 130 within 0.04 s ("stopped before taking the display; nothing was changed");
SIGTERM 143; SIGHUP 129; two Ctrl+Cs 130; watchdog 124 at 55.05 s. `--headless` on RADV: 600/600
frames, results written, exit 0; Ctrl+C mid-run stopped at frame 1721 of 6000 with partial results
(RADV's headless surface offers no present timing). `cargo test`: 1200 synthetic frames with a known
clock offset and one late frame check the summary; five deliberate mistakes each fail it.

## Listing (`timing --list`)

```
device: NVIDIA GeForce RTX 4080 SUPER, driver 615.71.9
display Samsung Odyssey G8 (DP-0): 3840x2160 px, 23 modes (3840x2160 @ 120.000 | 119.880 | 60.000 | 59.940 | 29.970; …)
chosen: Samsung Odyssey G8 (DP-0) at 3840x2160 @ 120.000 Hz, plane 0
features: presentTiming 1, presentAtAbsoluteTime 1, presentAtRelativeTime 1, presentId2 1
calibrateable time domains: DEVICE, CLOCK_MONOTONIC, CLOCK_MONOTONIC_RAW, SWAPCHAIN_LOCAL, PRESENT_STAGE_LOCAL
--list: stopping here, before taking the display; nothing was taken.
```

## For the PI

His screen locker started at 22:41:53, one second after the first refused attempt (22:41:52.7-53.0).
With no `kscreenlockerrc`, Plasma's default idle auto-lock applies (taken to be 5 minutes, UNVERIFIED
for Plasma 6.7), which would fit his last activity around 22:37. No known mechanism makes a refused
display request lock the screen, and the later refusals produced no events — but whether that lock was
idle, manual or caused by the test was not proven.

## UNVERIFIED

Whether either path takes the display from the text console; whether the console returns by itself
after the run (RUN-ME: Ctrl+Alt+F4 then F3 if it stays dark); the whole timing-result path on NVIDIA;
the forced exit at 60 s (needs a real hang); whether an unprivileged udev monitor would show DRM
events at all.

## Housekeeping

Sources copied back to `src-copy-timing/` (checksums match). NVIDIA source excerpts in `nvsrc/`, Khronos
pages in `vkdocs/`. On the machine: `out/` empty, test copies deleted, nothing running;
`~/wl-spike-s/timing` is 139 MB (mostly `target/`). One slip: a monitored run wrote a udev log to the
machine's `/tmp` (`/tmp/.wl-udev.<pid>`), deleted within seconds.
