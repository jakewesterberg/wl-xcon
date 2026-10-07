# Spike S: a Gabor, two patches and two eye viewports through a Rust Vulkan core, off-screen

Run 2026-10-07, following `BRIEF.md` in `spike-s/`. Nothing was presented to or acquired from the monitor:
the program creates no swapchain and no display surface, and its VK_KHR_display calls only list
displays and modes. (Report written by the spike agent; saved here by the controller, which checked its
headline numbers against `compare-out/compare.json` and `compare-out/sensitivity.jsonl`.)

## The answer

- **It matches.** A 201-line Rust host and a 79-line WGSL compute shader drew the whole 3840×2160
  panel on the RTX 4080 SUPER. Inside a 400×400 px region around each eye's Gabor, the largest
  difference from `exact.draw` is **2.54e-5 cd/m² (left)** and **1.56e-5 cd/m² (right)**: **0.00026**
  and **0.00016** of one stand-in step (100/1023 cd/m², a linear 0-100 cd/m² 10-bit scale standing in
  for build A2's real output levels). The background matches bit-exactly in every region checked and
  across the rest of the panel (7,869,824 pixels). Both patches are exactly 100 cd/m², with exact
  background just outside them. The shader works in f32; the reference is numpy f64.
- **The comparison can fail.** Against the same GPU output, references drawn slightly wrong differ by
  1.8 to 3.4 stand-in steps (phase +1°, orientation +0.5°, position +0.36 px) — 3-4 orders of
  magnitude above the GPU's own difference.
- **The driver advertises the whole present-timing stack** on the NVIDIA device: VK_EXT_present_timing
  (presentTiming, presentAtAbsoluteTime, presentAtRelativeTime all true), present_id/present_wait in
  both versions, VK_EXT_display_control, calibrated timestamps including the two present-timing time
  domains. None of it was exercised; whether a real surface supports it is UNVERIFIED.
- **Off-screen dispatch: median 3.56-3.73 ms of GPU time** per 21-run invocation, for a brute-force
  full-panel shader sharing the GPU with the desktop. Not a presentation-timing claim, not a frame
  budget.
- **Blocking for the later timing test:** the only monitor is held by the PI's KDE Plasma (Wayland)
  session; that monitor is a Samsung Odyssey G8 listing 120 Hz at most (not the rig's PG27UCDM); and
  the newest `ash` (0.38.0, Vulkan headers 1.3.281) has no bindings for VK_EXT_present_timing or the
  "2" versions of present_id/present_wait.

**A mistake, for the PI:** running `plasmashell --version` over SSH to read the Plasma version made
that throwaway process abort with no display (SIGABRT, core dump at 22:09:54 CEST, PID 40294) and
started KDE's crash handler (`drkonqi-coredump-launcher`, PID 40309). A "plasmashell closed
unexpectedly" notification may appear; it concerns that `--version` process only — the desktop's
`plasmashell` (15394) and `kwin_wayland` (15230) kept running. Dismissing it is safe. Whether DrKonqi
submits crash reports automatically depends on the PI's settings (UNVERIFIED).

## Environment

- wh-dws0, Fedora Linux 44 (KDE Plasma Desktop Edition), kernel 7.2.8-200.fc44.x86_64, KWin 6.7.5 on
  Wayland.
- NVIDIA GeForce RTX 4080 SUPER (0x10de/0x2702), driver 615.71.09, device Vulkan 1.4.351, loader
  1.4.341; an AMD iGPU (RADV) and llvmpipe also present — the program picks vendorID 0x10de.
- Sharing the GPU during runs: kwin_wayland, Xwayland, plasmashell, Firefox, Steam. GPU idle (P8,
  210 MHz) before the timed runs, full power (P0, 2700 MHz) just after.
- Monitor: one, "Samsung Odyssey G8 (DP-0)", 3840×2160.
- Rust 1.99.0 by full path; `CARGO_HOME=~/wl-spike-s/cargo-home` for every cargo command.
- Mac: worktree `b2b-remote-signin` at bac7fc5, no local changes to the files used; Python 3.13.9,
  numpy 2.3.5. Blobs read: exact.py 0b26c79, screen.py f28356a, viewport.py 69eed3c, tests/_rig.py
  4d7cbbb, tasks/rig.py 5dedd0a.

## What was built

1. `mac/resolve_scene.py` runs `screen.resolve` on the brief's stimulus (Gabor sf 2, σ 0.5°, phase
   30°, orientation 30°, Michelson 0.5, at (2°, 1°), disparity −0.2) on a `Gray(20.0)` trial through
   `STEREOSCOPE`, asserts the scene's shape, and writes `scene.txt`: at_left = (3.55138°, 1.0°),
   at_right = (0.44862°, 1.0°), radius 2.0°, σ 0.5°, D = 63.14925 cm, pitch 0.0153638 × 0.0154134 cm.
   The GPU never re-implements resolve.
2. `main.rs` computes each eye's direction and local axes in f64, passes everything as push constants
   ("immediates" in naga 30), dispatches one invocation per panel pixel, brackets it with GPU
   timestamps, and writes the panel as raw little-endian f32 Y, row-major, top row first.
3. `draw.wgsl` follows `exact.py` for one covering grating: on 4×4 samples plus a one-sample ring of
   neighbors — cm position, direction, azimuthal-equidistant (u, w) turned by −orientation,
   d = hypot(u, w) − r, per-axis slope as the larger one-sided difference using only neighbors on the
   eye's sample grid, coverage clip(0.5 − d/g), the envelope on contrast, value = bg·(1 + m·sin·env),
   compositing, average of 16 samples; then the patches. One rewrite is mathematically identical
   (`t·ex`, `|t|` as `v·ex`, `hypot(v·ex, v·ey)`) and avoids an f32 cancellation.
4. `mac/compare.py` draws `exact.draw` regions and compares; `mac/sensitivity.py` compares against
   deliberately wrong references.

Determinism: the GPU output was bit-identical (sha256 6d1ad305…) across all 9 invocations of both
builds. Validation: Fedora's `vulkan-validation-layers-1.4.341.0-2.fc44`, downloaded, `rpm -K`
checked, unpacked into `~/wl-spike-s/vvl`, loaded for one run by environment variables: zero
messages. The first build's one error (VK_KHR_display needs VK_KHR_surface) is the only difference
between the two builds.

**Code size** (non-blank, non-comment): `main.rs` 201 (235 lines), `draw.wgsl` 79 (102 lines). Most of
the host is Vulkan setup and teardown; about 20 host lines are the read-only display and time-domain
listing.

**Crates** (licenses from each crate's own `Cargo.toml` in the registry cache, 2026-10-07): `ash`
0.38.0+1.3.281 and `naga` 30.0.1 (`wgsl-in`, `spv-out`), both MIT OR Apache-2.0. 33 crates in the
build graph (`gpu-out/cargo-tree.txt`, `gpu-out/licenses.txt`); those not "MIT OR Apache-2.0":
codespan-reporting (Apache-2.0), spirv (Apache-2.0), foldhash (Zlib), libloading (ISC), cfg_aliases
(MIT), libm (MIT), unicode-ident ((MIT OR Apache-2.0) AND Unicode-3.0), zerocopy/zerocopy-derive
(BSD-2-Clause OR Apache-2.0 OR MIT), rustc-hash ("Apache-2.0/MIT"). All permissive; none copyleft.

## The comparison

`exact.draw` per eye, regions only, 4×4 samples per pixel (0.3 s per 400×400 region). Results in
`compare-out/compare.json`.

| Region | Max \|ΔY\| (cd/m²) | At panel (row, col) | Exact / GPU | Stand-in steps | Mean \|ΔY\| |
|---|---|---|---|---|---|
| Left Gabor, panel cols 1015-1414, rows 808-1207 | 2.54e-5 | (1003, 1227) | 21.843760 / 21.843735 | 0.00026 | 6.1e-7 |
| Right Gabor, panel cols 2712-3111, rows 808-1207 | 1.56e-5 | (1013, 2910) | 19.093958 / 19.093973 | 0.00016 | 5.5e-7 |

Mean signed ΔY −3e-9 and −6e-9 cd/m² (no bias); the exact Gabor spans 10.55-29.85 cd/m². Every
region's border is background in the exact drawer. Six 64×64 background regions (left eye corner,
center, seam; right eye seam, upper right, above the patch) are exact. All 80,000 patch pixels are
exactly 100.0, no other pixel is 100, and the one-pixel ring outside each patch is background. All
7,869,824 pixels outside the Gabor regions and patches are exactly 20.0.

**Sensitivity** (`mac/sensitivity.py`, left-eye region, same GPU output):

| Reference drawn with | Max \|ΔY\| (cd/m²) | Stand-in steps |
|---|---|---|
| the scene as given | 2.54e-5 | 0.00026 |
| phase 31° | 0.174 | 1.78 |
| orientation 30.5° | 0.331 | 3.38 |
| Michelson 0.505 | 0.098 | 1.01 |
| σ 0.505° | 0.073 | 0.75 |
| x + 0.005° (≈0.36 px) | 0.313 | 3.20 |
| x + 0.014° (≈1 px) | 0.875 | 8.95 |

## What the driver exposes (read-only)

From `vk_gpu0.txt`, `vkinfo.txt` and the program's output; enum values decoded with Khronos `vk.xml`
(Vulkan-Docs `main`, VK_HEADER_VERSION 365, fetched 2026-10-07, `dl-vkxml/vk.xml`).

| Item (NVIDIA device) | Reported |
|---|---|
| VK_EXT_present_timing | rev 3; presentTiming = presentAtAbsoluteTime = presentAtRelativeTime = true |
| VK_KHR_present_id / present_id2 | rev 1 / 1; presentId = presentId2 = true |
| VK_KHR_present_wait / present_wait2 | rev 1 / 1; presentWait = presentWait2 = true |
| VK_EXT_display_control | rev 1 (display power control, device/display events incl. first-pixel-out, vblank counter; needs VK_EXT_display_surface_counter and VK_KHR_swapchain) |
| VK_EXT/KHR_calibrated_timestamps | rev 2 / 1 |
| Timestamps | period 1 ns; 64 valid bits on graphics and compute queue families |

Calibrateable time domains: DEVICE, CLOCK_MONOTONIC, CLOCK_MONOTONIC_RAW, PRESENT_STAGE_LOCAL_EXT and
SWAPCHAIN_LOCAL_EXT (the last two from VK_EXT_present_timing). Instance: VK_KHR_display (rev 23),
VK_EXT_acquire_drm_display, VK_EXT_direct_mode_display, VK_EXT_acquire_xlib_display,
VK_EXT_display_surface_counter, VK_KHR_get_display_properties2, VK_EXT_headless_surface,
VK_NV_display_stereo. Displays listed while KWin holds the monitor (nothing acquired): one, "Samsung
Odyssey G8 (DP-0)", 3840×2160, 23 modes; at 3840×2160 29.970, 59.940, 60.000, 119.880, 120.000 Hz;
nothing above 120 Hz at any resolution (`gpu-out/final-run1.txt`). UNVERIFIED: surface-level support
(`VkPresentTimingSurfaceCapabilitiesEXT` needs a surface), and whether KWin passes present timing
through for a window.

## GPU dispatch time (off-screen compute only)

One dispatch (480×270 workgroups of 8×8) bracketed by two GPU timestamps, then submit and wait; the
output buffer is device-local and CPU-mapped (resizable BAR).

| Invocation | Runs | Median (ms) | Min | Max |
|---|---|---|---|---|
| Final binary, 1 | 21 | 3.7345 | 3.6272 | 4.0226 |
| Final binary, 2 | 21 | 3.5676 | 3.5178 | 4.2941 |
| Final binary, 3 | 21 | 3.5571 | 3.5195 | 4.3225 |
| Final binary, long run | 201 | 3.5813 | 3.5201 | 4.9169 |

First build's medians: 3.6679, 3.6588, 3.5681, 3.5671 ms. Whole program 0.64 s wall time. The shader
evaluates 36 samples for every panel pixel with no culling, on a shared GPU from idle clocks. These
numbers say nothing about presentation latency or frame timing.

## What the timing test needs (steps for the PI; not done)

1. **The monitor.** On this machine the test measures the Samsung G8 on DP-0 (120 Hz at most at
   3840×2160), not the PG27UCDM. Whether the ceiling is the monitor, the cable or the link is
   UNVERIFIED.
2. **Free the display.** Save work, log out of Plasma; at the login screen press Ctrl+Alt+F3 and log
   in on the text console. If the login screen still holds the display, stop it for the test with
   `sudo systemctl stop sddm` (and `sudo systemctl start sddm` afterwards).
3. **Run from that console.** The program finds the display with VK_KHR_display, takes it (a display
   surface directly, or vkAcquireDrmDisplayEXT on the graphics device), creates a swapchain, presents,
   and reads VK_EXT_present_timing and VK_EXT_display_control per frame. UNVERIFIED: whether driver
   615.71 allows this from a text console, and whether a process started over SSH may use the device
   while the console session is active; started at the console is the known-good case.
4. **Restore.** Exit, start SDDM if stopped, log back in.

Alternatives: KWin's DRM-lease protocol (for non-desktop outputs only, as far as known; UNVERIFIED for
6.7.5; with one monitor leasing blanks the desktop anyway), or running the desktop from the AMD iGPU on
a second monitor to free the NVIDIA output.

Bindings: ash 0.38.0 (newest on crates.io per `cargo info ash`, 2026-10-07) has khr::display,
display_swapchain, present_wait, ext::acquire_drm_display, calibrated timestamps and raw tables for
display_control and present_id; it lacks present_timing, present_id2 and present_wait2 — hand-written
FFI for those calls, ash from git (UNVERIFIED whether its headers include them), or another crate.

## Surprises

- naga 30 renamed push constants to "immediates" (`var<immediate>`, `Capabilities::IMMEDIATES`) — a
  naga dialect, not standard WGSL.
- f32 was enough: the largest difference is about 1e-6 relative; the background is bit-exact.
- VK_KHR_display lists the monitor and all its modes while KWin holds it.
- The output is deterministic across runs.
- Loader 1.4.341, device 1.4.351.

## Exact commands

`S` = spike-s, `W` = the worktree, `PY` = `PYTHONPATH=$W:$W/tests $W/.superpowers/venv/bin/python`,
`R` = `ssh -o BatchMode=yes jakewesterberg@100.116.116.4`,
`CE` = `CARGO_HOME=$HOME/wl-spike-s/cargo-home PATH=$HOME/.cargo/bin:$PATH`.

```
cd $S/mac && $PY resolve_scene.py > ../scene.txt; scp ../scene.txt …:wl-spike-s/
$R 'cd ~/wl-spike-s/spike && export CE && cargo add ash naga --features naga/wgsl-in,naga/spv-out && cargo build --release'
$R 'cd ~/wl-spike-s && ./spike/target/release/spike scene.txt out/panel_y.f32 21'
$R 'cd ~/wl-spike-s && VK_ADD_LAYER_PATH=$HOME/wl-spike-s/vvl/usr/share/vulkan/explicit_layer.d LD_LIBRARY_PATH=$HOME/wl-spike-s/vvl/usr/lib64 VK_INSTANCE_LAYERS=VK_LAYER_KHRONOS_validation ./spike/target/release/spike scene.txt out/panel_y_validated.f32 3'
$R 'cd ~/wl-spike-s/spike && export CE && cargo tree -e normal,build'
cd $S/mac && $PY compare.py ../gpu-out/panel_y.f32 ../compare-out && $PY sensitivity.py ../gpu-out/panel_y.f32
python3 $S/mac/count_lines.py $S/src-copy/src/main.rs $S/src-copy/src/draw.wgsl
```

## On the machine

`~/wl-spike-s` (351 MB) is left for the PI to delete (mostly `spike/target`; also `cargo-home`, `out`,
`vvl`, `vvl-dl`). No spike process is running. Rust itself is in `~/.rustup` and `~/.cargo`.
