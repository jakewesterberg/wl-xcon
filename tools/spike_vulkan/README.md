# SPIKE S — throwaway. A Rust Vulkan core against the exact drawer (engine spec §10.5)

**Not production code.** It exists to answer one question and produce numbers: can a small Rust
program draw what `wl_xcon/exact.py` defines, through Vulkan on an NVIDIA Linux machine, within one
output level, and does the driver give per-frame presentation timing? What survives into the display
process (engine build E) is written again, test-first, behind the interfaces in
`docs/design/architecture.md`. CI does not build anything here.

Run on the PI's desktop wh-dws0 (RTX 4080 SUPER, driver 615.71.09, Fedora 44) on 2026-10-07, from
`~/wl-spike-s/` there; results and the exact commands are in
`docs/measurements/wh-dws0/2026-10-07-vulkan-spike/` (`REPORT.md` for part 1, `TIMING-REPORT.md` for
part 2).

- `offscreen/` — part 1: a Gabor, two light-sensor patches and both eye viewports of the stereoscope,
  drawn off-screen by a WGSL compute shader (201 + 79 code lines), written as raw f32 luminance.
  Build: `CARGO_HOME=… cargo build --release`; run: `target/release/spike scene.txt out.f32 21`.
- `mac/` — `resolve_scene.py` resolves the scene with `screen.resolve` and writes `scene.txt` for the
  GPU; `compare.py` and `sensitivity.py` compare the GPU's panel with `exact.draw`; `count_lines.py`
  counts code lines. Run with this repository on `PYTHONPATH` (and `tests/` for `_rig`).
- `timing/` — part 2: drives the monitor directly (VK_KHR_display, no compositor) and records each
  frame's present-stage times (VK_EXT_present_timing, hand-written FFI checked at compile time against
  Khronos `vk.xml` by `tools/gen_layout_check.py`). Run from a text console as `RUN-ME.txt` says; it
  refuses cleanly while a desktop holds the display.

Crates: `ash` 0.38.0 and `naga` 30.0.1 (MIT OR Apache-2.0), listed in ADR-0004's inventory as
spike-only.
