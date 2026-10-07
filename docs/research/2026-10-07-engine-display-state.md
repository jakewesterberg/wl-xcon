# Display engine: what wl-xcon already decides, leaves open, and has built

> **What this is.** A survey of what the repository decided, built and left open, written on 2026-10-07 by a research subagent for the engine design (display engine and task runtime, brainstormed as one design at the PI's request). Kept as written; its section 6 or 7 is its own inference, not a decision. Check a claim against the code before relying on it.

Researched 2026-10-07 in worktree `.../.claude/worktrees/b2b-remote-signin` (branch tip = `main` at b2b-ready). Read-only. No tests run. Paths are relative to the worktree root. "S4" = `docs/superpowers/specs/2026-08-31-S4-stimulus-presentation-design.md`; other specs are in the same directory (`SPECS/`).

Headline: **no display code exists.** Only `tools/spike_display.py` (throwaway), `wl_xcon/geometry.py` (degrees to field, not to pixels), `wl_xcon/photometry.py` (color gamut checks), and `World.display` (a no-op protocol hook).

---

## 1. Decided

### 1.1 Seam and obligations (S4 §4, lines 75-89; ADR-0002)
- `DisplayAdapter` is "The seam ADR-0002 exists to preserve ... the adapter is ours and is what the simulators substitute for" (S4:77-78). Five obligations (S4:82-89):
  1. Flip-locked: "Everything scheduled for a frame is drawn before the flip; nothing is drawn between flips."
  2. "The frame period is never assumed ... 4.2, 8.3 or 2.08 ms, and S13's kiosk something else again. Code that hardcodes a period is a bug the checker should catch."
  3. "No allocation, no disk I/O, no logging inside a frame. Assets are resident before an epoch begins."
  4. Draws the photodiode patches every frame, "unconditionally, on every code path".
  5. "Reports the frame index so motion (§5) and any logged position are reconstructable."
- CLAUDE.md "Hot-path discipline": no allocation, no logging I/O, no unbounded work per frame; GC managed around trials.
- Decision-to-display: "Decision -> display change: next flip, engine flip-locked" (controller-architecture §13 table, ~line 688). The loop models this as "A display action decided while processing frame N takes effect on frame N+1" (`wl_xcon/run.py:297`).
- Unfinished frames: "If a trial's stimuli overrun the ITI, the ITI extends; frames are never dropped" (controller-architecture ~line 275).

### 1.2 Coordinates and per-eye viewports (S4 §2-3, lines 23-71)
- "A task never names a pixel. Positions are cyclopean degrees; the display module maps them to viewport pixels using measured optics." (S4:25-26). Degrees are the API (direct-view spec §2).
- Mapping per setup: "In direct view there is one viewport, the whole panel, at the screen's own distance Z ... Either way a position maps by D · tan per axis, so each field is a rectangle in degrees" (S4:37-39). `wl_xcon/geometry.py` fixes the mapping "it must implement".
- Mapping inputs are "measured, not derived": each eye's folded path, each viewport's centre, the vergence offset (software constant), deg/pixel per mode. They live in the session snapshot; a change to any is a discontinuity of the P16 class (S4:43-47).
- Disparity: "a stimulus property, applied as equal and opposite horizontal offsets about the cyclopean position. A monocular task is the zero-disparity case of the same path" (S4:49-51; D6 in controller-architecture).
- `Stimulus.eye` = "both"/"left"/"right" for dichoptic and monocular presentation (`wl_xcon/task.py` Stimulus docstring, ~line 890).
- Calibration targets are presented at zero disparity (S4 §3): per-eye maps are fitted independently against a shared cyclopean grid. Disparity is "verified separately (§10)".
- Stereoscope: "Two viewports on one framebuffer. One window, one flip, one refresh clock, no genlock. Stereo is not a second pipeline." (controller-architecture §8.2).
- Vergence is a software constant: "Do this in software, as a constant horizontal offset between the two viewports, not by angling the mirrors" (optics drawing §6). Nominal 2.9° at E = 1.6 cm (see 6.1 for S4's contradictory 3.2°).
- The mirrors translate, not deviate, so a zero-offset stimulus sits at optical infinity while accommodation is at 63.15 cm (optics §6).
- Nonius/vernier alignment is a required procedure; residual recorded every session (S4 §10 item 1).

### 1.3 Two setups, one fixed screen (direct-view spec; PI 2026-09-28)
- "One physical screen distance for both setups, and the screen never moves." `Z` = 50 cm. The operator picks the setup at session start, no default, via `wlx run --view direct|stereoscope`. The PI declined a presence switch (§1, §3).
- Direct view: whole panel, same image to both eyes, ±30.5° × ±18.4°, 56.8 px/deg centre (62.9 mean), less the sensors' housings. Stereoscope: `D = Z + HW − E` = 63.15 cm at E = 1.6 cm, 71.7 px/deg centre, stopped by a removable mask "starting at ±12°" (PI 2026-09-28; requirement ±10°, PI 2026-09-27).
- `Trial.view` is "direct" | "stereoscope" | "either" (default either). "Disparity requires the stereoscope"; a mismatch refuses to start (direct-view §3).
- "A wrong pick for an 'either' task still runs, with degrees computed on the wrong distance. That is the cost the PI accepted when he declined the switch."
- The first animal task runs in direct view (PI 2026-09-28). Calibration constellation is per setup: direct ±15° × ±15°; stereoscope ±12° (direct-view §6).
- Field checks (check 8) run per eye after disparity, against the chosen setup's field, and "fail closed" (`wl_xcon/check.py` `_offscreen_stimuli`, ~line 460).
- Rig settings: `tasks/rig.py` holds a `geometry.Rig` (active area, Z, mask half-angle, housings). Housings are empty until measured, "so direct view refuses on this rig's settings" (S0 §5.5).

### 1.4 Frame model, motion, gaze contingency (S4 §5, lines 93-107; controller-architecture §8.3)
- "Position is a pure function of (parameters, seed, frame index). Never a logged per-frame trajectory." Offline reconstruction exact; hot path allocation-free; "random-dot kinematograms reproduce by the same mechanism: the seed is the stimulus."
- The same rule is in the code vocabulary: `Dots` ("motion is a pure function of parameters, seed and frame index"), `Noise` ("`seed` is the stimulus ... `refresh_hz` above zero makes it dynamic"), `RDS` (all `wl_xcon/task.py`).
- Gaze-contingency "is a stimulus property, not a code path. A stimulus declares `anchored_to="gaze"` and the display module resolves its position each frame from the current gaze sample" (S4:105-107). **No such field exists in `task.py`** (grep "anchored": no hit); see XC-028 in section 5.
- `Update` changes a live stimulus "without the offset transient `Hide`+`Show` inserts" (`task.py` `Update` docstring); `Show` persists until `Hide` or trial end (not state-scoped).
- Saccade-contingent display changes "must land inside saccadic suppression" (controller-architecture ~line 403; roadmap M3); S5:211-212 and V3(b) measure it photodiode to photodiode.

### 1.5 Appearance vocabulary the engine must draw (`wl_xcon/task.py` 451-760)
Disc, Square, Bar, Gabor, Dots (RDK), Annulus, Cross, Polygon, Grating, Plaid, Checkerboard, Noise, Picture, Movie, Blank, RDS (with `correlation` including -1 anticorrelated, and optional `Form`: Corrugation, Slant), Array (n items on a ring, set size as a value). ADR-0002's "fifteen appearances" count is older than RDS/Array/Form. Every appearance with a `color` field carries `Color | P | None`. `contrast` is on the appearance. Sizes/positions in degrees. Assets: `Picture.asset`, `Movie.asset` (strings; resolution unspecified).
- The spike's comment (`tools/spike_display.py:31-33`): "The vocabulary in S1a is shader-shaped -- Gabor, grating, plaid, checkerboard, noise, disc".

### 1.6 Color, gamma, LUT (S4 §9; `wl_xcon/photometry.py`; S1a ~line 276; pitfalls P19)
- "RGB is not a colour ... a different stimulus on every monitor" (`photometry.py:1-7`; P19). Task color is `xyY` (absolute light, cd/m²) or `DKL` (cone-opponent modulation about the background, "`lum=0` is isoluminant by construction").
- `Calibration` fields: red/green/blue/background `xyY`, **one scalar `gamma`**, `observer` (whose V(λ); "a macaque's is not a human's"), `measured_on`, `max_cone_contrast` (default 0.85). `unrealizable()` solves the 3×3 primary mixture and refuses weights outside [0,1] ("a clipped colour is neither the requested chromaticity nor the requested luminance"). **Nothing converts a color to framebuffer values**; photometry only judges realizability.
- `check._color_faults` (`check.py:791`) emits blocking `uncalibrated-color` (no calibration), `unrealizable-color`, and an isoluminance finding when the calibration does not name its observer. "As of 2026-08-31 no calibration for our panels exists. The `Calibration` in the tests is illustrative." (`photometry.py:15-17`).
- S4 §9 defines `SessionManifest.stimulus_calibration_id` as the identity of a stimulus calibration record containing: per-mode gamma/luminance transfer per panel half; measured deg/pixel per eye per mode; vergence offset; panel identity, firmware and state of every "care" feature; ABL fill-factor limit as interocular coupling; the V1/V9 artifacts. "A session runs against exactly one stimulus calibration id, and the id changes whenever any input to it changes — including a mirror-carriage move for a different animal."
- PI ruling 2026-10-07 (CHECKPOINT "What moved on 2026-10-07", build 1; demo-mode spec ~line 442): "There should be a default color calibration/lut that is used when one isn't specified by the rig file. There should maybe also be a warnings tab in the console that lists all things that are imperfect, such as this, but as acceptable. E.g., for a training session, having a perfect color calibration is a nice to have, not a need to have." It is the first of four ordered builds (PI: "Default colors + warnings first"). Not designed yet.
- XC-002 (PI request 2026-09-28): "Automated color calibration and gray-tone linearization, built into the rig." Prior analysis (CHECKPOINT at `42e4a9f`, lines ~399-411, via `git show`): "a QD-OLED is not a power law, and its ABL makes luminance depend on how much of the screen is lit"; a tristimulus colorimeter measures for a human observer, macaque-weighted luminance "needs spectra, i.e. a spectroradiometer: the expensive, science-facing fork"; measure at the eye point (automatable with screen fixed at 50 cm; through each periscope for the stereoscope); how often, and what a session does with a stale calibration. These questions are **not yet put to the PI**.
- Burn-in: "Burn-in mitigation may not touch the stimulus (ruled 2026-08-31)". Fixation-point jitter rejected; mitigation is hardware-side; "running well below peak luminance is a longevity strategy as well as an ABL one" (S0 §5.4).
- Test screen for gamma/luminance ramp per half (S4 §10 item 3; S9 §6).

### 1.7 Photodiode patches (S4 §7; S3 §8; direct-view §4)
- `A_PD1` task patch (stimulus onset), `A_PD2` flip patch ("alternates every refresh and is therefore a frame clock"), "fixed in copper (wl-sync breakout spec §3.1)", both return as digital comparator inputs (`PD1_COMP`, `PD2_COMP`).
- "The flip patch alternates on every refresh, unconditionally, including during blanks, aborts, pauses and error states. A frame clock that stops during an abort is not a frame clock." (S4:130-132; S3 §4 item 4).
- "The task patch is driven by the display module from the scene's own onset, so a task cannot forget it and cannot desynchronise it from what it drew." (S4:146-147).
- Placement: stereoscope = bottom strip, full width, 3.22 cm at the ±12° mask (1.90 cm at ±13.15°, 5.51 cm at ±10°), outside both viewports, at one bottom corner. Direct view = "no strip": each patch is under its sensor's opaque housing near (±30°, −18°), a margin-bearing rectangle that the field excludes.
- "Verified dark to each eye at bring-up, in both setups, not assumed from geometry" (V9 items).
- The loop's guard `Onscreen(patch="task")` "advances on evidence, not on the belief that a flip happened"; `After(0.05, since=Onscreen(...))` never arms if the patch is occluded, so a bare one is refused by check 4 (`task.py:250-322`).
- Dropped frames: "Dropped frames are detected in hardware, live, from `PD2_COMP` at the display surface — not from the engine's own frame-interval accounting (parent §11.5)" (S4:212-213).
- Pause: "No display process exists to show the task's background yet; V12 item 3 proves it on a rig" (CHECKPOINT ~line 1449). V12 item 3: during a pause the patch and panel show the background and PAUSE/RESUME edges bracket it.

### 1.8 Panel and modes (S0 §5; PI)
- Panel: ASUS ROG Swift OLED PG27UCDM, 26.5" tandem QD-OLED, 4K/240, active area 589.97 × 332.93 mm (PI 2026-09-27; QD-OLED a requirement, PI 2026-09-26). "ASUS PG27UCDM stays (PI, 2026-09-28)" after comparing the Alienware AW2725Q (DP 1.4, DSC); recheck Dell DP 2.1 UHBR20 27" QD-OLED in January 2027 at KU Leuven (CHECKPOINT ~line 1602).
- GPU: NVIDIA RTX 5070 Ti (PI 2026-09-26), DP 2.1b UHBR20; with it 4K/240 runs without DSC (S0 §5.1).
- "Mode is a rig configuration" (S0 §5.3): 4K (8.3 ms @120, 4.2 ms @240) vs FHD (2.08 ms @480). "V1 runs in every mode the rig will use; each mode carries its own calibration and deg/pixel; the mode is recorded in the session snapshot; and gaze-contingent code never assumes a frame period." **The PG27UCDM lists no FHD/480 mode**, so the 2.08 ms mode is unavailable on this panel (S0 §5.1).
- DSC: "Prefer a GPU and panel that can avoid it; if DSC is unavoidable, its effect is measured, not assumed." (S0 §5.3).
- Panel acceptance (S0 §5.4, folded into V9): burn-in protection fully defeatable (pixel shift "can walk the patch off its sensor"); ABL as interocular coupling; per-half uniformity; gamma/additivity/channel independence; pixel response and onset per mode; sustained 100% APL. Criteria 1 and 2 disqualify. The PG27UCDM's pixel shift and "Neo Proximity Sensor ... switches to a black screen" may not be defeatable: "ask ASUS before buying" (S0 §5.1). UNVERIFIED whether answered.
- Graphics stack: P4 "X11-vs-Wayland, compositor bypass, and NVIDIA vsync behavior all move timing. Pin distro/driver/session type per rig ... re-run V1 after any change." Remote desktop/VNC off during recording ("Remote work uses a remote console (ZMQ telemetry), not remote pixels").
- Task PC OS: Ubuntu 24.04 (Python 3.12) per `wl.yaml:40-48`.

### 1.9 Assets and audio (S4 §6, §8)
- Image sets resident before an epoch; "Loading, decoding and uploading to texture memory happen at block or session boundaries, never inside a trial and never inside a free-viewing epoch." Set declared, versioned, identity recorded per trial; memory budgeted at session start ("a set that does not fit is refused then"). The kiosk has different memory, so "asset residency must therefore be a declared requirement".
- Audio (S4 §8, same spec and spec-map "Owns" list as the DisplayAdapter): declared assets resident, `AUDIO_ON`/`AUDIO_OFF` codes, no separate feedback subsystem; electrically tapped into a misc analog BNC (V7).

### 1.10 Test screens (S4 §10; S9 §6)
Run from the console; one required every session start: (1) per-eye alignment/vergence target (Nonius/vernier), residual recorded; (2) geometry and linearity grid per eye; (3) gamma and luminance ramp per half; (4) photodiode patch test; (5) frame-timing pattern for V1 per mode; (6) disparity verification. Roadmap M5 repeats the per-eye alignment target.

### 1.11 Kiosk (S13)
- "One screen, no mirrors. Monocular by construction; the display module's zero-disparity path (S4 §2), with the kiosk's own geometry and no vergence offset" (S13:50-51). "The same task model. A task written for the rig runs here if its declared device requirements are met" (S13:65). Wired touch panel, not a tablet (PI 2026-09-19). Kiosk stimulus vocabulary (whole or subset) is open (XC-030). Touch at the rig is a separate open item (controller-architecture §8.4).

### 1.12 Licensing (ADR-0004, Accepted 2026-09-05, PI)
- Apache-2.0 for the repo; copyright holder Jacob A. Westerberg. "There is no PsychoPy import, and there never has been" (ADR-0004:32-34).
- "If ADR-0002 ever chooses PsychoPy, the adapter that imports it goes in a separate package under GPL-3, behind the DisplayAdapter seam ... The core does not become GPL because a display backend did." (ADR-0004:46-49).
- "An added dependency under a copyleft license is now a decision that reopens this ADR" (ADR-0004:54-55). New dependencies need a one-line justification and an inventory row (CLAUDE.md). The inventory currently has no display library row (pydantic, numpy, pytest, pyyaml, pyzmq, msgpack, fonts, pyjwt, cryptography, playwright only).
- glfw (zlib) and moderngl (MIT) are named as permissive in ADR-0004:36-37. License facts for those two are asserted in that ADR with no citation or as-of date (CLAUDE.md "No fabrication": UNVERIFIED here).
- `pyproject.toml:16`: core dependencies are `pydantic>=2`, `numpy>=1.24` only. Extras: `dev` (pytest), `contract` (pyyaml), `console` (pyzmq, msgpack), plus signin/browser. **No display extra; neither psychopy, glfw nor moderngl is declared.**

### 1.13 Simulation, replica, demo
- The simulated animal "sees the screen": `simulate.py:137` `display()` records visible stimuli; "An animal cannot look at something that is not there" (P18).
- Console replica pane: S9a §2 "exact replica scaled to the experimenter's" in task coordinates, disparity as annotation, gaze per eye; gated on V11 (XC-077) and open dichoptic question (XC-024).
- Demo mode (parked 2026-10-07, XC-013): "The display engine itself is ADR-0002's, decided after V1, so demo mode draws a schematic, never the stimuli themselves" (demo-mode spec ~lines 35-37). It renders each `Screen` message to an SVG in Python (§4.4) and lists "Drawing the real stimuli" as out of scope (§ ~415). **This is a second, non-engine renderer of the stimulus vocabulary.**

### 1.14 Interface the engine plugs into (`wl_xcon/run.py`)
- `World` protocol (`run.py:42-102`): `display(visible: Mapping[str, Stimulus], frame: int) -> None`, "Called every frame, before the frame's guards are evaluated, with the stimuli a real display would be showing ... On a rig this is what draws". Its body is a no-op stub ("NOT MUTABLE: `welfare.emit` and `run.display`, both protocol stubs", CHECKPOINT ~line 1504).
- `run_trial(..., frame_period, each_frame=..., effects=...)` takes `frame_period` as a parameter, never a constant. `each_frame` runs first on every frame (before display). `Effects.mark` strobes "now, not on the next flip" (`_emit`, `run.py:339-350`), explicitly distinct from the one-frame display rule.
- `gaze.py:181` `display()` doubles as the per-frame gaze poll point ("the loop's only per-frame call that lands before the frame's guards are evaluated") and `simulate.py` records visibility; a real display's `display()` must coexist with that.
- Principle "A safety component ships with its consumer, or its absence fails" (CLAUDE.md) and `Unwired` refusing: by analogy a missing display adapter should raise, not silently draw nothing. Not yet implemented for display (inference).

---

## 2. The engine choice (ADR-0002, `docs/design/decisions/ADR-0002-display-engine.md`)

**Status line (line 3):** "Proposed. Deferred to V1 (PI, 2026-08-31) — neither stack is built properly until a rig can measure both".

Sequence in the file (all 2026-08-30/31):
1. **Decision (2026-08-30, lines 10-14):** "PsychoPy used strictly as a library (no Builder), behind a thin DisplayAdapter interface owned by us." Reasons: "photodiode-measured 0.34 ms onset variability on Ubuntu (Bridges et al. 2020), active maintenance (2026.2.3), flip callbacks, huge community." Alternatives rejected: raw pyglet/OpenGL ("re-derives solved problems (gamma, text, movies, calibration); no timing pedigree of its own"), MWorks (macOS-only), Bonsai/BonVision (Windows, C#), Unity/M-USE (C#, frame-level only).
2. **Accepted 2026-08-31 (lines 27-42):** "Accepted unchanged." Because S4 needs flip-locked callbacks and S11 could not declare a display dependency while Proposed. Declined spiking raw pyglet first. Took "GPL-3 gravity" deliberately.
3. **Reopened the same day (lines 44-72)**, after installing PsychoPy. Four reasons: (1) "pip install psychopy pulls 81 dependencies — py2app, dmgbuild, flake8, a Sphinx docs theme, MeshPy, Phidget22, gevent, pygame, opencv-python, pandas, matplotlib, moviepy, h5py, pyarrow. That is an application being installed on a rig, not a library"; (2) "A Python ceiling of 3.12"; (3) "We already cannot use its coordinate system. geometry.py exists because a folded optical path with two viewports and a software vergence offset is not expressible in PsychoPy's monitor model"; (4) "Its stimuli are stateful objects that advance themselves, and S4 §5 makes motion a pure function of parameters, seed and frame index". What survives: Bridges et al.'s photodiode pedigree and a large stimulus library. Ruling: "So: spike the thin stack first (PI, 2026-08-31). A DisplayAdapter over a window, a vsync-locked flip and fragment shaders — our fifteen appearances are mostly 10–40 lines of GLSL. Measure it under V1 on the same rig. If it hits the timing, take it; if not, PsychoPy is still there and we have lost days rather than months."
4. **Ruling 2026-08-31: decide after V1 (lines 74-90):** "Neither stack is built properly yet. The spike stays a spike, PsychoPy stays installed, and the choice is made when a rig exists and V1 can measure both under the same photodiode protocol." The "build the thin stack now" recommendation: "That reasoning is unchanged and stands as the case to re-read in January — what the ruling rejects is committing display code before anything can measure it". Cost: "P5 becomes hardware-blocked". Benefit: "no chance of building the display layer twice, and a decision made on a photodiode rather than on a laptop that already produced one misleading verdict (P4a)."

So: **the thin-stack recommendation is the author's (an AI session's) recommendation, endorsed as the first spike (PI 2026-08-31), but the PI's final ruling defers the choice to a V1 head-to-head on a rig.** The thin stack = glfw + moderngl + numpy (3 dependencies vs 81, Python 3.13 capable; `docs/measurements/dev-machine/2026-08-31-display-spike.md`).

Deferred to measurement: V1 on both stacks, every mode, same photodiode protocol (XC-069); M2 gates "onset variability < 1 ms; drops < 0.1%" (proposed). XC-068 (P5, whole display process) waits on "the panel; XC-069, which decides ADR-0002".

Landscape context (`docs/research/landscape.md:34-40, 100`): PsychoPy "No published macaque ephys rig runs PsychoPy as controller (negative search result, 2026-08-30)"; verdict then "build thin on PsychoPy-as-library".

**Other engine facts in the repo:**
- Bridges et al. 2020 figures (0.34 ms SD, 4.71 ms constant lag) are cited as "their measurement, not ours; V1 measures ours" (controller-architecture §8.1). The paper (peerj 9414) was not re-read here: UNVERIFIED.
- PsychoPy "2026.2.3 declares `>=3.10,<3.13`" (`wl.yaml:42`); read from the install on 2026-08-31.
- `wl.yaml:67-76` still declares `psychopy >=2026.2` as "accepted in ADR-0002 on 2026-08-31" (stale; XC-052).

---

## 3. Built

### 3.1 Drawing code
- **`tools/spike_display.py`** (168 lines, "SPIKE — throwaway ... What survives into DisplayAdapter gets written again, test-first"). glfw window, `swap_interval(1)`, moderngl fullscreen quad, one fragment shader drawing a Gabor (about 25 lines of GLSL) plus two photodiode patches in a bottom strip (flip patch alternates `frame % 2`; task patch toggles every 60 frames). Reports frame-interval statistics only. Key finding encoded at lines 133-140: `ctx.finish()` after `swap_buffers` is required; without it "the loop free-runs". Its uniforms hard-code `deg_per_ndc = (17.0, 19.0)  # S0 §5.2 at 57 cm`, an old panel/distance. No gamma, no per-eye viewports, one viewport only. `ctx.clear(0.5, 0.5, 0.5)` and `vec3(lum)` output means no color path. Imports glfw/moderngl/numpy (not declared anywhere in `pyproject.toml`, so it is not runnable from the declared environment, UNVERIFIED whether they are installed on the dev machine).
- **Measurement of it:** `docs/measurements/dev-machine/2026-08-31-display-spike.md`. macOS, 120 Hz internal, windowed. PsychoPy 8.336 ms median, sd 1.30, 1.79% long frames; glfw+moderngl first attempt sd 4.78, 36.0% long; drained sd 3.21, 15.5% long; fullscreen first attempt 4.521 ms (221 Hz on a 120 Hz panel). Header: "This is not a V1 measurement and must never be cited as one." "do not compare display stacks on a development machine again" (line 55); pitfall P4a.
- No PsychoPy code, no OpenGL code, no shader outside the spike. `rg moderngl|glfw|psychopy` in `wl_xcon/`: none (inferred from the file list and pyproject; not grepped with a clean command, see UNVERIFIED note in section 6).

### 3.2 Code that models the display without drawing it
- `wl_xcon/run.py`: `World.display` hook; loop keeps `visible` dict, `Shown(name, on, off)` realized timeline, `Changed`, `Confirmed` (photodiode) records; one-frame rule for display actions; `Onscreen` simulated "on the first frame after the display changed" in demo spec.
- `wl_xcon/geometry.py` (329 lines): `Housing`, `Geometry` (`stereoscope()`, `direct()`, `pixels_per_degree(horizontal_pixels)`, `can_show(x_deg, y_deg)`), `Rig`, `SubjectSettings`. Computed from the optics drawing, "They are computed, not measured." Maps degrees to panel cm and field limits; does **not** produce pixel positions, per-eye viewport centres, the vergence offset, or per-eye path lengths. (`pixels_per_degree` exists.)
- `wl_xcon/photometry.py` (161 lines): color types and gamut/cone-contrast refusal. No conversion to RGB, no gamma application, no LUT, no DKL-to-cone matrix (DKL realizability is only `magnitude() <= max_cone_contrast`).
- `wl_xcon/check.py`: check 8 (offscreen, per eye after disparity), color faults, display timeline (`review.py`), "nothing-to-look-at", "absent-stimulus", etc.
- Tests: `tests/test_display.py` (7 tests), `test_display_checks.py`, `test_color.py`, `test_geometry.py`, `test_disparity.py`, `test_per_eye.py`, `test_array.py`, `test_onset_timing.py`, `test_review_display.py`.
- `simulate.py:137` and `gaze.py:181` implement `World.display` for the simulated animal and for gaze polling; **no implementation draws**.
- Web: `wlx serve` renders nothing about stimuli yet; demo mode will (parked, SVG schematic).

### 3.3 What the trial loop calls today in place of a display
`World.display(visible, frame)` on the world passed in; real sessions' world is the gaze-bearing one (`gaze.py`) whose `display` polls the tracker and ignores `visible`. The photodiode confirmation `happened(Onscreen, ...)` is supplied by the world (simulated: as a light sensor would see it). The flip patch, task patch, dropped-frame detection from `PD2_COMP`, and the DIO side (`dio.Absent`) are not wired to a display.

### 3.4 Dependencies
Core `pydantic`, `numpy`. Numpy's stated ADR-0004 justification: "Fitting only -- applying a map in the trial loop is plain float arithmetic". Any in-loop display math is not covered by that sentence.

---

## 4. Measurements the decision waits on

| Protocol | What | Decides | Rig needed? |
|---|---|---|---|
| **V1** (`docs/validation.md:8-12`) | "Photodiode on a corner patch driven by known flip sequences; recorded in NIDQ analog. Report: onset lag (constant), onset variability (SD), duration error, dropped frames over >= 2 h under task-like load. Run at rig acceptance and after ANY graphics change (P4)." Per mode (S0 §5.3). XC-069, waits on panel and card. | ADR-0002 engine choice (both stacks, same protocol); roadmap M2 gates (SD < 1 ms; drops < 0.1%, proposed); X11 vs Wayland per rig (P4). | Yes: panel, NI card, photodiode comparator. Spike script `tools/spike_display.py` is only a proxy ("it measures what the GPU handed the compositor, not what reached the panel"). |
| **V9** (validation lines 77-110; S0 §5.4) | Each eye's folded path and viewport centre and deg/px, per-half photometry (luminance and chromaticity), vergence residual after Nonius, six-criterion panel acceptance (burn-in defeatable, ABL as interocular coupling, uniformity, gamma/additivity/channel independence, pixel response, 100% APL), direct view items (measure `Z`, patches invisible, camera line clear, stereoscope insertion). XC-070 waits on the panel. | Per-eye mapping constants (the "measured, not derived" inputs); the stimulus calibration record (S4 §9); whether the panel is disqualified; ABL fill-factor range as a stimulus-design constraint. | Yes; photometer. |
| **V3(b)** | Artificial eye step to display change measured by photodiode, full distribution. | Gaze-contingent budget; whether saccade-triggered updates land inside suppression (M3 gate). | Yes (tracker + display). |
| **V2b** | Photodiode comparator to state transition via NI change detection. | Whether `Onscreen`-gated progression works inside a frame (the display's feedback path). | Yes. |
| **V7** | Audio onset via misc BNC tap. | Audio (same module owner). | Yes. |
| **V12** | Frame timing with the mark check; mark lands in its frame; pause shows background. | Whether per-frame console check disturbs frames. | Yes. |
| **V11** | Replica pane over LAN in browser at 120/60 Hz, 10 min each. XC-077, "waits on: nothing (a LAN, no rig)". | Whether the browser can carry the replica (not the engine). | **No rig.** |
| Calibration record (XC-071) | "Measure the panel's color calibration (primaries, background, gamma, against a macaque luminous efficiency) so chromatic tasks load." Waits on the panel and the instrument XC-002 chooses. | Real `Calibration` for photometry; `stimulus_calibration_id`. | Yes: spectroradiometer or colorimeter. |
| Pupil/ridge fade (XC-081) | Pupils under rig luminance and P4's real reach. | Ridge fade at the mask's nasal edge. | Yes. |
| `tools/calibration_design.py` per setup | Already rerun 2026-09-28 (two records in `docs/measurements/dev-machine/`). Not display, but sets calibration target region. | — | No (done). |

Existing measurement artifacts: `docs/measurements/dev-machine/` has `2026-08-31-display-spike.md` (explicitly deciding nothing), `2026-09-05-calibration-constellation.md`, `2026-09-28-calibration-constellation-{direct,stereoscope}.md`, `2026-09-28-mark-check.md`, `2026-09-27-p10-dpi-spike/`, `2026-09-27-panel-27-vs-32/{direct_view,geometry,p4_range}.json`. **No photodiode, V1, V9, or photometry artifact exists.** The README says "One directory per rig".

Could be run without a rig: V11 (LAN, synthetic); the dev-machine mark-check CPU cost (already done); a CPU-side shader/geometry correctness test (inference, see section 7). A hypothetical off-rig frame-pacing test is explicitly barred by P4a.

---

## 5. Open questions already recorded

**S4 §12 (lines 217-225):**
- Item 1: "Whether `TARGET_POSITION` ever needs a disparity field, or stereo targets stay in our record | nothing today; §3 avoids it" (XC-029, waits on a stereo task, M8).
- Item 2: "Who writes `SessionManifest` — us, ingest, or wl.works | S10" (XC-098).
- Item 3: "Misc-BNC assignment for the audio tap | wl-sync" (XC-089).
- Item 4: "Whether the kiosk shares the stimulus vocabulary or a subset | S13" (XC-030, waits on XC-107).
- Item 5: "Image-set versioning and where sets live on disk | S10" (XC-027).

**docs/backlog.md lines mentioning display/S4/V1/photometry/color/gamma:**
- XC-001 (line 22): "Which eye or eyes task control listens to online".
- XC-002 (line 23): "Automated color calibration and gray-tone linearization, built into the rig." Waits on: nothing.
- XC-013 (line 36): demo mode "waits on: the default color calibration and the warnings list, then XC-207 and XC-242, then the reference tasks made right (PI, 2026-10-07)".
- XC-024 (55): "The replica pane, including whether dichoptic trials need two panels and which rendering path it takes." Waits on XC-077.
- XC-027 (57): "Where image sets and their versions live on disk."
- XC-028 (58): "Frame-accurate `Update` semantics for gaze-anchored stimuli." Waits on XC-068.
- XC-029 (59), XC-030 (60): above.
- XC-052 (139): "`wl.yaml` still declares PySide6 and PyQtGraph for a desktop console ADR-0008 replaced, and calls ADR-0002 accepted though it is deferred to V1."
- XC-068 (194): "P5, the display process: `DisplayAdapter`, viewports, photodiode patches, audio and the test screens." Waits on: the panel; XC-069, which decides ADR-0002.
- XC-069 (195): "V1: display timing by photodiode, in every mode the rig uses." Waits on the panel and the card.
- XC-070 (196): "V9 and the panel acceptance test".
- XC-071 (197): "Measure the panel's color calibration ... so chromatic tasks load."
- XC-077 (203): V11. XC-081 (207): pupils.
- XC-089 (221), XC-090 (222: "wl-sync: confirm the photodiode patches (the bottom strip, 3.22 cm at the ±12° mask, and direct view's housings); our handover there still says 2.18 cm at ±17°").
- XC-143 (114): "Check 8 adds an item ring's radius but not the depth of a corrugated or slanted stereogram used as an `Array`'s item". XC-144 (115): "Check 8 tests centres ... and never a stimulus's own size, so a 6° disc centred at 11.5° passes the stereoscope's ±12° mask."
- XC-242 (45): `adaptive_detection`'s `contrast` "is read by no stimulus either".

**Other recorded opens:**
- S1a / S1 §10 item 5 (frame-accurate Update for gaze-anchored: XC-028).
- Controller-architecture §8.4: touch "second panel, a rig mode with the stereoscope out of path, or deferred".
- Controller-architecture open item 3: "Remaining: whether burn-in protection is defeatable, and whether GPU + panel can avoid DSC" (the latter answered by S0 §5.1: RTX 5070 Ti + PG27UCDM runs 4K/240 without DSC).
- S9a §11 item 1: dichoptic replica.
- Optics §8: item 1 (E per animal), 3 (patch placement with wl-sync), 5 (enclosure/baffling vs ambient light), 8 (ridge fade).
- Direct-view §9 item 1 (not read in full): housings "measured at build" (S0 §5.5). The housing rectangle values are empty in `tasks/rig.py`.
- S0 §5.1: ask ASUS whether pixel shift/proximity sensor can be disabled.
- PI (2026-10-07): default color calibration/LUT and a warnings tab: "Not designed yet" (CHECKPOINT).
- CHECKPOINT line 3 / backlog: kiosk hardware (XC-107).
- Nothing in the repository records: the pixel format/bit depth the framebuffer uses (8-bit vs 10-bit output for DP 2.1 at 4K/240), the HDR/SDR mode of the panel, how a per-channel LUT is applied (GPU LUT vs shader vs panel), or per-eye anti-aliasing/filtering policy. (Absence found by grep for "10-bit", "LUT", "HDR" in S4/S0: S0 §5.3 mentions 10-bit only for link bandwidth, "HDR" only in vendor listings.)

---

## 6. Contradictions and stale statements

1. **Vergence offset:** S4 §2 line 44-45 says "3.2° nominal — optics drawing §6"; optics drawing §6 says 2.9° at E = 1.6 cm (2.7–3.5° over IPD 30–38 mm). (`grep "3.2°"` in specs: only S4.) Stale after the 50 cm redraw.
2. **S4 line 84-85:** "4.2, 8.3 or 2.08 ms" frame periods; S0 §5.1 says the PG27UCDM has no FHD/480 mode so 2.08 ms is "unavailable on this panel". Harmless for a never-assume-period rule, but S4's list is not this rig's.
3. **Engine of record:** controller-architecture §8.1 "PsychoPy as a library behind our own DisplayAdapter (ADR-0002, unchanged)" and `wl.yaml:67-76` ("accepted in ADR-0002") vs ADR-0002's own "Reopened ... same day" and "decide after V1". XC-052 already records the wl.yaml one; the architecture spec line is not in the backlog (the same spec's open-item 2/3 table is more current). docs/research/landscape.md verdict 1 ("build thin on PsychoPy-as-library") and verdict 3 ("MonkeyLogic stays as bridge") are older than ADR-0005 (which withdrew the bridge).
4. **S11 line 10-11:** "declares no display or messaging dependency, because ADR-0002 and ADR-0003 are still Proposed" vs ADR-0003 Accepted 2026-08-31 and `wl.yaml` now declaring psychopy. Stale.
5. **ADR-0004 vs roadmap M10:** ADR-0004 Accepted 2026-09-05 (Apache-2.0) but roadmap M10 still lists "ADR-0004 decided" as a pending gate (`docs/roadmap.md:84`). Stale. Also ADR-0004's "Revisit at M7" in the superseded lean.
6. **Kiosk display path:** S13:50-51 "the display module's zero-disparity path (S4 §2)" (shared module) vs `wl.yaml:72-73` "the kiosk has its own display path". Direct conflict on whether the kiosk shares the display engine; XC-030 is only about vocabulary.
7. **Photometry location:** architecture.md (display section) says panel left/right nonuniformity "is photometered in V1"; V9 is the photometry protocol (direct-view §7 corrected the same slip for ABL; architecture.md was not).
8. **S3 §8 open item 3 (line 247):** "Photodiode patch placement — candidate found (central strip from the nasal clip)" vs the same file's body and optics §5: bottom strip. The central strip is only the fallback (optics §8 item 4). Stale row.
9. **S4 §5 vs code:** `anchored_to="gaze"` does not exist in `task.py` (XC-028 tracks semantics; the field name in S4 may or may not be the final name).
10. **ADR-0002 "fifteen appearances"** vs ≥17 classes now (add RDS, Array; Form is not an appearance).
11. **Spike's geometry:** `tools/spike_display.py:113` uses `deg_per_ndc = (17.0, 19.0)  # S0 §5.2 at 57 cm`, the 31.5" panel's field; current panel gives ±30.5° × ±18.4° (direct) at 50 cm.
12. **Pause display:** S4 §7 says the flip patch alternates "during blanks, aborts, pauses"; today `run_trial` returns at trial end and "no display process exists", so between trials nothing drives a display (the loop is trial-scoped; CHECKPOINT ~line 1449: "no trial runs, so nothing is drawn"). Not a contradiction, but the display adapter must outlive trials, which `World.display` (called per frame inside a trial) does not express. (inference)
13. **ADR-0006 consequence** ("Keyboard/mouse demo mode ... same status as the display module") vs the demo-mode spec drawing a schematic not the display engine; consistent but note demo mode is therefore not a display test.
14. **Roadmap M8 vs direct-view:** M8 "Stereo" mentions "Cheap by construction if M2 built viewports properly"; the first animal task is direct view (single viewport) so M2's viewport mandate now applies to both setups, with stereoscope second. Not stale, but the roadmap does not mention direct view (grep: none) while architecture does.
15. **S4 title/status:** status "proposed, for PI review"; dated 2026-08-31 and since partly amended (§7) by direct-view; direct-view §8 lists "S4 §2 (the viewport mapping per setup)" and "S4 §7" as docs to change. S4 §2 and §7 text has been updated (mentions direct view), consistent. But S4 §10 and §9 still say "per half of the panel" with no per-setup variant for direct view (direct view has no halves; a direct-view gamma is whole-panel).

UNVERIFIED items in this report: Bridges et al. numbers and Python-ceiling claim (read only from repo text); glfw/moderngl licenses and whether either is installed on the dev machine; exact S0 §5.1 vendor claims (pixel-shift defeatability); direct-view spec §9 (not read beyond §8); whether any docs outside those searched mention a pixel format or LUT mechanism (searched S4, S0, architecture, ADRs only).

---

## 7. Inference: what a design can settle now, and what cannot be settled

(This section is my inference, not recorded anywhere.)

**Can be settled now, no rig needed:**
1. The `DisplayAdapter` interface as a Protocol: lifecycle (open/close/outlive trials), `draw(frame, visible)`, `flip() -> frame_index`, `frame_period` supplied by the adapter (never assumed), residency declaration for assets, a `refuse-if-absent` default (like `Unwired`/`dio.Absent`) so a missing display raises. `World.display` is currently a per-trial, per-frame hook; decide whether the adapter is that hook's implementation or a separate object the world calls.
2. A pure CPU reference renderer: given `(Stimulus, appearance params, seed, frame)` produce a numpy luminance/RGB image. It would be the sim-first test oracle for any shader and the "motion is a pure function" property (determinism, reconstruction from the record alone), plus golden-image tests. Fits CLAUDE.md "sim first" and "No allocation in the hot path" (the oracle is off-path).
3. Degrees-to-pixels mapping for both setups: per-eye viewport centres, vergence offset, disparity as equal and opposite offsets, Nonius target geometry, as pure functions on top of `geometry.py`, with the measured inputs as parameters (defaults flagged "computed, not measured"). Includes the bottom-strip patch rectangles and the housing exclusion in framebuffer pixels.
4. Photodiode patch logic as pure state: flip patch alternation, task patch tied to scene onset, "unconditional on every code path", including a blank/idle/pause scene. Testable against a recorded frame sequence.
5. Color pipeline math: xyY/DKL to linear primary weights to display values via a calibration object; the default-calibration policy the PI asked for (what the default is, how it is labeled "imperfect but acceptable", how the warning is raised); per-channel LUT representation (extending the scalar `gamma`); per-half versus whole-panel calibration records and `stimulus_calibration_id` composition. DKL needs cone fundamentals (not in the repo; source and as-of date needed per CLAUDE.md).
6. The calibration record schema and id derivation (S4 §9): what fields, how hashed, where stored (touches XC-098 manifest ownership, so ask).
7. Asset residency API and budget-refusal logic (S4 §6), image-set versioning (XC-027).
8. Appearance-by-appearance shader spec (Gabor, grating, plaid, checkerboard, dots, noise, RDS, polygon, Array) with parameter units and edge behavior (hard aperture vs Gaussian), written as CPU reference first.
9. Dependency and license policy for the engine: ADR-0004 inventory rows for glfw, moderngl (permissive, verify and cite) or a separate GPL-3 package for a PsychoPy adapter. Note neither is currently a declared dependency; also decide an optional `display` extra so the core stays two dependencies.
10. The extension of check 8 to stimulus extents (XC-143, XC-144) and the housing exclusions in pixels.
11. Kiosk: decide shared-module versus own display path (contradiction 6), and the vocabulary subset (XC-030).
12. What the live replica and demo renderer share with the engine (one scene description, e.g. the demo spec's `Screen` message) so there is one source of truth for "what is on screen" across three consumers (engine, replica pane, simulated animal).

**Cannot be settled until a rig measures it:**
- Which stack meets timing (V1, both stacks, per mode, per X11/Wayland, per driver); whether compositor bypass, vsync enforcement and the pipeline-drain (`ctx.finish()`) behave on Linux/NVIDIA as they did on macOS. P4a bars any off-rig verdict.
- Onset lag constant and drop rate (M2 gates are proposed numbers).
- The panel's real transfer function (QD-OLED not a power law; ABL depends on fill factor), primaries, and macaque-weighted luminance; therefore the content of the default LUT and the real calibration (XC-071, XC-002); and the instrument choice (PI's science-facing fork, not yet asked).
- Per-eye optical path lengths, viewport centres, deg/pixel, vergence alignment residual (V9); `Z` and housing rectangles (the rig file is empty so direct view refuses).
- Whether patches are dark to each eye, and the sensors' physical fit at one corner.
- Whether pixel shift and the proximity sensor can be defeated; whether 4K/240 is uncompressed over the RTX 5070 Ti and PG27UCDM in practice (DSC effect "measured, not assumed").
- 10-bit versus 8-bit output path, HDR/SDR setting, and ABL interocular coupling range (stimulus-design constraint).
- Gaze-contingent end-to-end latency and its relation to saccadic suppression (V3b).
