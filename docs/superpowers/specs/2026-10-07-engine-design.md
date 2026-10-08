# The engine: what runs a task, from its plan to the animal's screen

**Status: approved by the PI on 2026-10-07 ("approved"), §17.6's reward-size rule included,
after reading it as a doc.** Designed with the PI on 2026-10-07, element by element (fifteen elements, well over a
hundred questions asked in the UI); then reviewed twice (science and feasibility, §26), the PI deciding
every finding that was his (seven more batches) and the rest fixed here. This revision was for the PI's
review. Every decision is the PI's answer as recorded, verbatim, in
[the brainstorm notes](2026-10-07-engine-brainstorm-notes.md), cited as **N§k** (the notes' element
k) or **N§Rk** (the review batches). Where this spec says "recommended", the PI chose the option offered
as recommended; where he chose otherwise, it says what was offered against.

It replaces nothing yet: each build (§24) gets its own plan and review. It amends other documents as
§22 lists, when the build that changes them lands.

## 1. Why

The PI asked to brainstorm "the engine for running tasks" before demo mode, the display engine and
the task runtime as one design, and then to go "far more in-depth ... These are central to a large
component of the experimental setup. So, we need to be careful in making this flexible and effective."

What exists (the surveys `docs/research/2026-10-07-engine-display-state.md` and
`...-engine-runtime-state.md`):

- **No display code.** A throwaway glfw and moderngl spike (`tools/spike_display.py`), `geometry.py`
  (degrees to the field, not to pixels), `photometry.py` (gamut checks, no conversion), and
  `run.World.display`, which draws nothing. ADR-0002 deferred the engine to V1.
- **A trial loop that works and a planner that is starved.** `run.run_trial` runs one declarative
  trial frame by frame; `scheduler.py` has conditions, targets, orders and repeats; but `taskd._plan`
  gives every run one block of one condition, so every trial of a run is the same trial, and no task
  can declare a plan (XC-207). Nothing calls a task's between-trial procedure (XC-242).

What the engine must serve: the PI's thirty-four named paradigms (N§1), from RSVP and adaptation to
most-exciting-image generation, gaze-contingent and closed-loop presentation, M/P/K mapping and manual
RF mapping by mouse, "and probably many more over time!". **That last clause is the first
requirement**: the engine grows by reviewed additions, never by rewrites.

## 2. Principles carried through every section

1. **Tasks are declarations, reviewed without reading drawing code** (ADR-0006).
2. **One definition of every stimulus**: the slow exact drawer (§4.9). The GPU draws to it, the review
   report shows it, analysis rebuilds any frame from it.
3. **Nothing estimated is written as fact.** The record holds what happened and what it was measured
   against; corrections that need a measurement (scan-out, latencies) are applied in analysis from
   that measurement (CLAUDE.md: no timing claim without a measurement).
4. **Imperfect but acceptable is listed, never silently passed** (the PI, 2026-10-07). Whether it is
   acceptable depends on what the session is for (§19).
5. **What was shown is reconstructable**: deterministic generators with recorded seeds, a log of every
   change, every live-driven value per frame, generated media kept.
6. **The hot path stays clean** (CLAUDE.md): screen descriptions and live values are written into
   preallocated buffers in a frame and to disk at the boundary; no logging I/O inside a frame.

## 3. Architecture

### 3.1 Three programs on the rig PC (N "How it fits"; N§7, N§8)

| Program | Language | Role |
|---|---|---|
| **The display process** | Rust, Vulkan | A system service from boot. Owns the animal's screen; refreshes every frame; draws the flip patch and the task patch; shows black when idle; draws exactly the screen description it is handed; reports which content each refresh showed and every late frame. Holds no task logic. |
| **The rig service** (`wlx taskd`) | Python | Sessions, runs, plans, the trial loop in step with the display, welfare, the record, between-trial procedures, the warnings list. Computes every screen description, live positions included (N "where the pieces meet"). |
| **The console** (`wlx serve`) | Python | Pages and controls, the warnings tab, the live schematic for hand mapping, frame-timing health. |

Off the rig: **lab storage** (media sets by checksum, §9.4; per-animal state and condition registries,
§13.7, §14.5) and **a GPU server** that makes generated images between trials (§4.8).

**Why a separate display process** (N§7 batch 3, the PI after asking "why did you recommend same
thread?"): a graphics-driver crash cannot take the session with it; the background stays up while the
rig service restarts; the process gets its own real-time priority. The rig service hands it each
screen description through shared memory and gets back what each refresh showed. Shared memory, the
generator protocol, the per-frame console input (§17.2) and lab-storage sync are new transports: they go
through an ADR (§22) before their builds.

### 3.2 One trial, end to end

1. The plan (§13) picks a condition; drawn values (§14) are sampled; adaptive procedures (§15) adjust;
   the layers resolve in the order of §17.1; the condition names its trial structure.
2. Frame by frame, in step with the display: the rig service reads gaze, runs the trial's states,
   applies actions, updates the **screen description** (§3.3) in place, and hands it to the display.
   Codes go out at the decision (§8.2). The display reports what each refresh showed.
3. At the end: the outcome, the trial's record line and screen log (§8.5) written, the procedures'
   update, the repeat rules (§16).

### 3.3 The screen description

One value describes everything on the animal's screen: the setup, each eye's background, and every
visible item fully resolved to numbers (shape, fill, edge, outline, placement per eye, layer, how it
combines, contrast with its convention, opacity, its seed and the frame it appeared on). No parameter
references remain. Frame-dependent content (drift, motion, refreshing noise, movie frames, sequence
items) is computed from it and the frame number by the display and the exact drawer alike.

**A change** is a discrete onset, an offset, or an update the task declares (§8.1). Live-driven values
(gaze-anchored, mouse-driven, neural-driven) and frame-dependent content are not changes: they update
the description's numbers in place and go to the screen log by frame.

**Its consumers, and only these, define "what is on screen"**: the display process, the slow exact
drawer, the simulated animal, demo mode's screen, the hand-mapping schematic and, later, the live
replica. It is versioned like telemetry (a schema number checked on read).

### 3.4 Simulation and demo

The same rig service, with the display process replaced by a no-op that acknowledges frames, or by
the development window (§11.4). The simulated animal (§18.3) reads the same screen description. Demo
mode, when it returns, shows frames from the exact drawer (§23).

### 3.5 The task object

A task module defines **one task object** (replacing today's rule of exactly one `Trial` per module,
`cli._load_trial`): its trial structures (§13.3), its plans (§13.1), its procedures (§15), and the
union of their declared parameters, which `Session.set` validates against. The loader, the checks, the
pre-flight, the review report and the simulator take the task object. Its exact shape is agreed with
wl-xtasks, where tasks live (§21).

## 4. What can be shown (N§1)

### 4.1 The stimulus model: building blocks and reviewed extensions

A stimulus is **a shape, filled with something, seen through an edge profile, placed and layered**.
Named kinds remain as shorthands (a Gabor is a circle with a grating fill and a Gaussian edge; a plaid
is two gratings combined by adding; an array is items on a ring). A genuinely new block is added once,
as reviewed framework code, and is then usable in any combination (§4.10).

### 4.2 The first set of blocks

**Shapes**: circle and ellipse; rectangle and polygon; ring; a line or curve (a path with a width);
text; the whole screen; an image's own outline. **Every shape may have an outline** (width and color).

**Fills**: flat color; grating; checkerboard; noise; sparse noise; moving dots; random-dot stereogram;
texture field; Mondrian; image; movie.

**Edges**: hard; Gaussian; raised cosine. **Each edge block states whether it is a contrast envelope
(the default for patterned fills: the pattern's contrast falls to zero about its mean, the classic
Gabor) or an opacity ramp, and what the stimulus's size means for it** (e.g. the Gaussian's cut-off and
its σ declared separately) (N§R3, the science review's finding 4).

**On every stimulus**: position, orientation, size, eye, disparity, layer, contrast, opacity.

### 4.3 What each fill must do (N§1 batches 2, 5, 6)

| Fill | Must support |
|---|---|
| Grating | sine, square, triangle and sawtooth waveforms; drift and counterphase (§6.4) |
| Noise | white, binary, pink (1/f), band-pass (frequency and orientation), color noise |
| RF mapping | sparse noise; dense noise or m-sequence; flashed and swept bars; subspace (Ringach/Hartley) gratings |
| Moving dots | coherence, direction, speed, lifetime, size, density, aperture; the noise dots' rule declared per task |
| Texture field | a figure defined against its ground by orientation, motion, color or disparity |
| Mondrian | colored rectangles, grayscale rectangles, mixed shapes, image fragments |
| Masks (composed) | noise masks, pattern masks, metacontrast, object substitution, a full-screen mask |

**A patterned fill has a mean luminance, defaulting to what is behind it.** [@brainard1996cone;
@pelli2013measuring] One whose mean differs (a luminance step under the pattern, e.g. a grating on the
black default) carries a warning naming the step, in every session kind (N§R3: "Always a warning").

**Random content is deterministic**: each random block's generator is part of its definition (a
counter-based function of the seed, the frame and the element, implemented identically in the exact
drawer and the core, with frozen reference outputs committed), so a reconstruction never depends on a
library's version. Seeds are recorded; a task may ask for its frames to be saved too, and those frames
come from the exact drawer.

### 4.4 Combining, grouping and layouts

- **Four ways to overlap**: front covers back (opacity); contrasts add (plaids, signal in noise,
  transparent motion); a window or scotoma; one shapes another (multiplication).
- **The background is the bottom layer**, changeable during a trial; on the stereoscope each eye may
  have its own background.
- **Groups**: a named group shows, hides, moves and changes a shared property as one; its members stay
  addressable. **Arrays and layouts are a group by default** (one code, §8.3).
- **Layouts**: a ring; a grid; listed positions; positions drawn between trials from a seed with spacing
  rules; several rings or clusters. **Each item is its own stimulus**: target and distractor are roles.
- **The busiest display is thousands of elements**; the GPU drawer batches them (§10).

### 4.5 Text and curves

- **Text**: letters, digits and symbols, from one or a few bundled fonts, glyph height in degrees,
  rendered to exact pixels. Bundled fonts enter ADR-0004's inventory.
- **Curves** (curve tracing): written in the task as fixed paths, or generated between trials from a
  seed by a reviewed procedure, saved in the record.

### 4.6 Images and movies

- **A photograph's colors**: the file is read as standard sRGB and converted through the rig's
  calibration; **the luminance of the photo's white is declared** (under the brightness cap, §7.7);
  the record names the calibration [@stokes1996standard; @iec1999multimedia].
- **Size**: declared per stimulus, degrees (resampled with a stated filter) or pixel for pixel.
- **Matching a set** (mean luminance, RMS contrast, optionally the amplitude spectrum): a declared
  preparation step when a task asks, **computed in linear luminance after the calibration**, recorded
  [@willenbockel2010controlling; @brainard2002display].
- **Formats**: any common format; a lossy one carries a warning [@ccitt1992information].
- **Movies**: each movie frame held a whole number of refreshes [@elze2010misspecifications]; a rate
  that does not divide the display rate is refused until re-timed beforehand, and any re-timing is
  recorded in the set's manifest (a 25 fps source re-timed to 24 changes speeds and pitch by 4%).
  Decoded beforehand or streamed by a decoder thread, declared per movie; a streamed frame that misses
  is recorded late.

### 4.7 Image procedures between trials

Scrambling, filtering, cropping and recoloring run between trials: a reviewed procedure, with its seed,
makes the image before the trial that shows it; the result is uploaded and kept in the record.

### 4.8 Generated images

Made on another machine (a GPU server on the lab network) between trials; the rig checks, records and
shows each one. **If the next image is not ready in time, the next trial waits as long as it takes**;
the welfare clocks keep running, the console says what it is waiting for, the operator can pause or
stop, and **each trial records how long it waited** (a closed-loop procedure may read it, §15.5).

### 4.9 The slow exact drawer

Plain Python (numpy) that turns a screen description, an eye, the setup's pixel geometry and a
calibration into the output levels that eye must see. It is **the definition of every block**: the GPU
drawer matches it (§10.1); the review report's frames come from it (§18); analysis rebuilds any
recorded frame from it and the record (§8.5); demo mode shows its frames (§23). It never runs inside a
frame.

### 4.10 Adding a block (reviewed extensions)

A new shape, fill or edge arrives as: its exact definition, its GPU version, the match tests, its
load-time checks, and **a simple, person-readable report with example frames** (the PI's words). **A
lab member reviews it** before tasks may use it: the definition and the report, not the GPU code.
Claude may write a block; Claude does not approve one.

### 4.11 Live-driven stimuli

A stimulus's position may be measured from the screen's center, another stimulus, where the eye is now,
or a live input (the operator's mouse, a joystick, a neural signal). **Any numeric property** may be
driven live; every live value is recorded frame by frame. Such stimuli break S4 §5's "position is a pure
function of parameters, seed and frame", and the record is what makes them reconstructable.

### 4.12 Contrast

**Always written with its convention** (`Weber(0.3)`, Michelson, RMS) [@pelli2013measuring]. Today's
appearances default `contrast=1.0` and the reference tasks rely on it; **build A migrates them and their
tests**, after which a bare contrast is refused at load. A convention defined against the background
(Weber) needs a declared non-black background (§7.5) [@pelli2013measuring].

## 5. Where (N§2, N§R5)

1. **Coordinates**: cyclopean degrees; (0°, 0°) is straight ahead (the rig file records where on the
   screen; default its center). **Math convention** for every angle: 0° right, counter-clockwise
   positive, +y up; a bar's orientation 0° is horizontal; a grating's orientation names its bars, its
   drift direction is a separate angle. A test pins +y as up in the drawing.
2. **Sizes**: one size number is the full width; each block's definition states it.
3. **Away from the center**: true visual angle (default) [@marshel2011functional] or the screen center's
   scale, declared per task.
4. **Disparity**: in degrees, near negative [@tanabe2004rejection]. **The per-eye formula is pinned**:
   left eye at x − d/2, right eye at x + d/2, so d < 0 shifts the left eye's image right (crossed,
   near). **A per-eye position** is that eye's own direction in degrees (its viewport, after the
   vergence offset); a stimulus carrying both per-eye positions and a disparity is refused. Both the
   formula and the sign are pinned in the exact drawer's tests, and the sign is verified in an animal by
   its vergence response to a disparity step [@busettini1996shortlatency] (S4 §10 item 6, kept).
5. **Linked positions**: declared per link, moving with the other stimulus or placed once at onset.
6. **Gaze-anchored stimuli**: the gaze rule selectable (newest, default; smoothed; predicted)
   [@santini2007eyeris; @crane1985generationv; @saunders2014direct], each frame's sample age recorded;
   behavior when gaze is lost, and during a saccade, declared per task. **A displacement meant to go
   unseen must land during the saccade** [@deubel1996postsaccadic; @cavanaugh2016saccadic]; one that
   lands after it may be seen (corrected from the notes' gloss, the science review's finding 12; and on
   2026-10-08 from the reference library: suppression of luminance contrast outlasts the saccade by
   about 50 ms [@diamond2000extraretinal] and lessens within 5-25 ms of its end [@saunders2014direct],
   so a change landing just after is neither safely hidden nor reliably seen; chromatic gratings show no
   saccadic suppression [@diamond2000extraretinal], so an isoluminant change is not hidden by landing
   inside a saccade; and trained monkeys did not show humans' benefit from a post-saccadic blank
   [@joiner2013corollary], so human results on post-saccadic visibility do not transfer directly).
7. **Gaze windows may be any shape**, including a stimulus's own outline grown by a margin.
8. **Off the field**: only when declared; check 8 grows to test extents (XC-143, XC-144).
9. **Head-free chaired sessions**: nominal head position, recorded and listed; a task may require a
   fixed head.
10. **Manual RF mapping's view**: a live schematic in the console. Its markers lag the bar by the
    neuron's latency plus the operator's reaction, so receptive fields are reconstructed from the
    per-frame record, not from the markers.

## 6. When (N§3, N§R3)

1. **The session's rate** comes from the display's reported mode, checked against the rig file, and is
   carried in the session and in the load-time checks; a task file is checked at each rate it may run at
   (240 and 120 Hz) or at its declared required rate [@bridges2020timing; @elze2010misspecifications].
2. **Durations are converted to frames once, at load**, and the loop compares frame counts (today it
   compares elapsed seconds, which rounds up and drifts with a measured period)
   [@elze2010misspecifications]. An ordinary duration rounds to the nearest frame, recorded as shown.
   **A duration that is a design level** (a factor level, a sequence's item period, a procedure-stepped
   duration) **is exact by default**: whole frames at the session's rate, or refused at load with the
   nearest valid values listed; two levels landing on one frame count are refused; procedures on time
   step in frames. A sequence declares whether it rounds per item or on cumulative onsets.
3. **A late frame never stops a trial**; the record marks it [@bridges2020timing].
4. **Temporal modulation**: sine at any frequency, sampled per frame; square-wave flicker needs whole
   frames per half-cycle [@elze2010misspecifications].
5. **Onset**: the record holds each frame's start and each stimulus's **vertical extent**. The screen
   scans top to bottom (Blur Busters, read 2026-10-07; UNVERIFIED for this panel), and both setups put
   the light sensors at the bottom, so V1 measures the scan delay with patches top and bottom and
   analysis applies it across the stimulus's extent [@dimigen2026advantages; @saunders2014direct;
   @wang2011lcd; @elze2010misspecifications].
6. **Sequences** (RSVP, predictive, masking streams): a sequence stimulus or one state per item.
7. **Motion paths**: straight sweeps, pursuit targets, waypoint paths, seeded random walks.
8. **The longest trial is 5 minutes** (the loop's frame cap derived from 300 s at the session's rate); a
   trial reaching it is recorded as today's `"hang"` category, which `resume`, `health` and the page
   already read. Longer presentations use the continuous mode (§13.6). **Inside a long trial, stop,
   pause and the welfare limits are checked about once a second**, off the frame path (N§R6).
9. **Between trials**: what the task declares (the background by default).
10. **Contingent changes record their delay**: decision time minus the sample's capture time (on the eye
    PC's clock once aligned), plus the frame's start, plus V1's scan delay at the stimulus's height,
    plus the panel latency V1 measures [@saunders2014direct; @dimigen2026advantages]. Until V1 and V3
    exist, the figure is labeled a lower bound. A task may declare a maximum; trials past it are marked.
11. **A non-aging foreperiod** declares its minimum, mean, maximum and tail rule; the review report's
    timing diagram plots the hazard it actually produces (a truncated exponential's hazard rises near
    its maximum).
12. **Every trial records the time since the last interruption** (pause, interlude, display restart,
    generator wait) and its realized interval before the stimulus; a block may declare what it does on
    resuming after one (e.g. rerun an initial adaptation).

## 7. Color and luminance (N§4, N§R4, N§R5)

1. **The default calibration is standard sRGB** (the panel in its sRGB mode; how closely it follows the
   standard is UNVERIFIED until measured, and the warnings list says so) [@stokes1996standard;
   @iec1999multimedia; @abuhaila2025recent].
2. **In a recording session the default calibration is refused for any task that specifies a color (DKL,
   cone contrast, xyY) or makes contrast a design factor or a procedure-controlled value**, read from
   the task file (N§R4) [@brainard2002display; @abuhaila2025recent]. Training and piloting run on it
   with the warning.
3. **Isoluminance needs a measured calibration**; against the calibration's named observer that is
   enough (N§R4; offered against: a per-animal measured null) [@cie2015fundamental; @sharpe2005luminous;
   @gegenfurtner1994chromatic]. `visual_search` keeps its isoluminant colors and waits; a plain-color
   training variant loads on the default.
4. **Color spaces**: xyY (absolute); **cone contrast** (ΔL/L, ΔM/M, ΔS/S about the background, for
   cone-isolating stimuli); **DKL, defined in cone-contrast terms with one stated normalization**
   [@cie2018colorimetry; @brainard1996cone; @derrington1984chromatic; @macleod1979chromaticity].
   **Realizability is tested by full conversion to primary weights in [0, 1]** for every space,
   replacing `photometry.unrealizable`'s `magnitude() <= max_cone_contrast` test for DKL, which passes
   chromatic contrasts the panel cannot make [@brainard2002display; @brainard1996cone].
5. **The default background is black**; a task using DKL, cone contrast or Weber contrast declares its
   own non-black background [@brainard1996cone; @pelli2013measuring]. The calibration is measured at a
   reference background; limits for a task's own background come from the full conversion, not from a
   stored maximum [@brainard1996cone; @brainard2002display].
6. **The transfer is a measured table** per channel [@brainard2002display]. **One calibration for the
   whole panel**; the stereoscope's two eyes are assumed equal (N§R4, offered against: measuring each
   eye's mirror path). *Stated limitation*: an imbalance between the eyes (panel halves, mirror losses,
   uneven OLED aging, e.g. under one-eyed Mondrian masking) appears as an eye-dominance effect belonging
   to the rig; dichoptic tasks should counterbalance the masked eye across sessions [@zhou2013effect].
7. **The brightness limiter**: overall brightness capped so ABL never engages, at a level V9 measures,
   including V9's cross-half test (one half's fill dimming the other); a display exceeding it is refused
   [@dimigen2026advantages; @abuhaila2025recent; @brainard2002display].
8. **Output is 10-bit**, verified at V1; **dithering, if it is the fallback, is on the warnings list**
   and is deterministic so the exact drawer models it [@brainard2002display; @pelli1991accurate;
   @tyler1997colour; @allard2008noisybit].
9. **Cone fundamentals**: one lab-wide default, **Stockman & Sharpe's 10° (CIE 2006)**; a task may name
   the 2° set for foveal work (N§R5) [@stockman2000spectral; @cie2006fundamental;
   @stockman2023formulae]. No standard macaque set was found to prefer: macaque and human L and M cone
   spectra are "virtually identical" (Schnapf, Kraft, Nunn & Baylor 1988, Vis Neurosci 1:255-261;
   checked 2026-10-07, attribution corrected 2026-10-08 — Baylor, Nunn & Schnapf 1987 is the macaque
   single-cone paper; `docs/research/2026-10-08-engine-a2-color-research.md` §0, §5)
   [@schnapf1988spectral; @baylor1987spectral]. The spectroradiometer's spectra are stored in each
   calibration, so any named set converts from them [@brainard2002display].
10. **A calibration never expires** but carries its age [@brainard2002display; @dimigen2026advantages;
    @spitschan2018method]; past 30 days it is a warning.

## 8. Sync and evidence (N§5, N§R3, N§R5)

1. **The flip patch** alternates every refresh. **The task patch toggles on every change** (§3.3):
   every onset, offset and declared update, and **each item of a sequence** (N§R3); never for
   live-driven values or frame-dependent content. The record's frame numbers say which change each edge
   was, and a per-trial check matches task-patch edges against logged changes, as §8.4 does for the flip
   patch.
2. **Event codes go out at the decision**; the light sensor gives the exact time [@hwang2019nimh;
   @bridges2020timing; @elze2010achieving; @ibl2021standardized].
3. **Stimulus codes are task codes, as S2 §5.1 planned** (N§R5): `STIMULUS_ON`, `STIMULUS_OFF` and
   `STIMULUS_CHANGED`, allocated once in wl-xtasks' range for every task; which stimulus each was is in
   the record by frame; a group is one code; no amendment to wl-preproc's frozen codec. Tasks' own
   onset codes (`FIX_ON`, `TARGET_ON`) stay.
4. **Frames are matched to the recording** by counting flip-patch edges from each trial's start code,
   checked against the trial's length [@siegle2021survey]. **The continuous mode strobes an
   anchor code about once a
   second** and the screen log records the frame each was strobed on, so a miscount is confined to one
   interval and located.
5. **The screen log**: every change with its frame and full resolved description; every live-driven
   value per frame; seeds; and **the display's per-refresh report of which content it showed**
   [@asaad2008flexible]. **A late
   frame repeats the previous content for one refresh, and the sequence then continues from where it
   was** (the loop never skips a frame number); m-sequence and other reverse-correlation trials with any
   repeat are marked [@reid1997use].
6. **The console shows frame timing per trial**, at boundaries.
7. **A frame-clock fault**: a warning and a warnings-list entry, affected trials marked, the session
   goes on (acceptable in every session kind) [@nwb2026nwb].

## 9. Media and sound (N§6, N§R5, N§R6)

1. **Sounds play through two of the task PC's PCIe-6343 analog outputs** (4 on the card, NI, read
   2026-10-07; the card runs on its own clock, not the recording's) [@hwang2019nimh]. **The wl-sync
   board is asked to
   bring them to a line-out** beside the existing speaker tap (§21). The output is armed at the decision
   and **started by the task patch's next edge**, which marks the frame the visual change lands on (at
   the bottom of the screen); a task may declare an offset, including the scan delay to the stimulus's
   height. **The actual onset is measured into the recording by the speaker tap** (V7)
   [@babjack2015reducing; @bridges2020timing]. Speaker-to-ear
   delay is acoustic and not in V7.
2. **Simple sounds are made from parameters**, rebuilt from the record; files remain for recorded sounds.
3. **Movie soundtracks** play when a task asks, in step with the frames.
4. **Media live on lab storage** by checksum; the rig keeps a verified local copy; the set's identity is
   recorded (XC-027).
5. **Media load per run**; a run whose sets do not fit is refused at its start, with the numbers.

## 10. The drawer (N§7)

1. **The GPU drawer matches the exact definition within one output level** per pixel.
2. **Edges are smooth and sub-pixel.** [@bach1997antialiasing; @bach2001freiburg]
3. **A pattern near the pixel limit** is allowed with a warning [@shannon1949communication;
   @merigan1990spatial].
4. **The core is Rust**, a separate process (§3.1), held to the exact definitions by the match tests and
   V1; **tests carry its review**.
5. **Graphics interface**: Vulkan offers direct-to-display (`VK_KHR_display`) and presentation timing
   (`VK_EXT_present_timing`; Phoronix reported NVIDIA's Linux driver supporting it, read 2026-10-07;
   UNVERIFIED for the RTX 5070 Ti). **The spike** (build S) draws a Gabor, both patches and two eye
   viewports through a Rust core, compares offscreen output with the exact drawer, measures the code it
   took, and checks NVIDIA's documented support; **timing waits for Linux and an NVIDIA card** (the PI's
   machine, over SSH, once it is on). On a Mac, Vulkan runs through MoltenVK and says nothing about
   timing (P4a).
   *Spike S, 2026-10-07* (`docs/measurements/wh-dws0/2026-10-07-vulkan-spike/`): on the PI's desktop
   (an RTX 4080 SUPER, driver 615.71.09 — not the RTX 5070 Ti, for which support stays UNVERIFIED) the
   off-screen Rust core matched the exact drawer within 2.6e-5 cd/m² (about 0.0003 of a 10-bit step on
   a stand-in 0-100 cd/m² scale), and the driver exposes VK_EXT_present_timing (presentAtAbsoluteTime
   included) with IMAGE_FIRST_PIXEL_OUT on its display surface; the on-screen timing run waits for the
   PI at a text console.
6. **Prior art**: vstimd is AGPL-3.0-only; **no code is reused**, only ideas (direct display, a post-flip
   vblank wait, landing reports, a renderer-owned patch, a no-op renderer for CI).
7. **ADR-0002**: our drawer is built now so V1 compares it with PsychoPy on day one; V1 chooses
   [@bridges2020timing; @peirce2019psychopy].

## 11. Lifecycle (N§8, N§R3)

1. **The display process starts at boot** as a system service and restarts itself if it dies.
2. **Black when no session runs.**
3. **If the display process dies during a trial**: the trial returns `Outcome.FAULT` (a non-exception
   path, so the run is not ended), the display restarts, and the session **pauses** at that boundary,
   recorded as a pause by **a system actor** (a new actor kind beside `Box` and `Member`). If it dies
   between trials or while paused, the session pauses (or stays paused) until it is back. A run that may
   pause by itself (a display in use, auto-pause on) needs `PAUSE` and `RESUME` in its allocation; the
   pre-flight refuses it otherwise.
4. **A windowed display** is labeled "development: not timing-valid" and serves simulations, demo mode
   and tests only.
5. **The pause screen**: declared per task; by default **the task's background when it has a non-black
   one**, black otherwise (N§R3). The flip patch still alternates.
6. **The screen and its mode are checked** against the rig file: panel identity, resolution, refresh,
   bit depth, **and the panel's care features** (pixel shift, its brightness mode, the proximity sensor,
   variable refresh, which must be off) [@asus2026rogb; @asus2026rog;
   @dimigen2026advantages; @poth2018ultrahigh; @saunders2014direct], recorded at bring-up; a mismatch is
   a warning.
7. **After a graphics change**, the warnings list says so until a matching V1 exists [@bridges2020timing;
   @plant2016reminder].
8. **The OLED's own maintenance** is scheduled outside sessions, or a session refuses to open while it
   is due [@dimigen2026advantages; @asus2026rogb] (UNVERIFIED whether the PG27UCDM allows
   either).

## 12. Calibration procedures and test screens (N§9, N§R5)

1. **The color instrument is a spectroradiometer** [@brainard2002display]; calibration is automated from
   the console (build J).
2. **The eye tracker's calibration is required at every session start** (S5 §7) [@kimmel2012tracking]:
   the thirteen-target constellation before any task; no first task without a validated map; calibration
   epochs inside tasks track drift [@hornof2002cleaning]. **It is its own early build (T)**, needing
   only the display and the tracker, before the first animal session; it does not wait on the
   spectroradiometer.
3. **On the stereoscope, the calibration is two monocular grids** (the PI's method) [@cox2019temporal;
   @mitchell2022stimulating; @dougherty2021binocular]: the grid shown to each eye in turn; each eye's
   map fitted from its own grid; and, from the covered eye recorded during the other eye's grid, **the
   offset between the eyes at each point is reported** (mirror misalignment plus the animal's phoria)
   [@svede2015monocular]. **No threshold: the experimenter accepts or not, and the acceptance is
   recorded** (N§R5).
4. **wl-preproc must be able to read these calibrations** (an ask, §21): a monocular grid's eye, the
   session-start block marked with the calibration task type, interlude recalibrations as
   `CALIBRATION_START`/`END` epochs, and the target positions they use.
5. **Before every session**: a quick frame-timing check and the light-sensor test
   [@plant2004selfvalidating; @bridges2020timing].
6. **Records committed per rig** under `docs/measurements/<rig>/`, each with an id.

## 13. Structure (N§10, N§R1, N§R6)

1. **A task's plans live in its task object**; the operator chooses among them at run start.
2. **The operator may edit freely** (conditions and block types added or removed), each change recorded
   and **checked exactly as the task file is**, refused if it fails.
3. **Several trial structures per task**, each condition naming its own.
4. **Interludes** (a recalibration, a quick RF map, a rest): the run steps aside and returns to the same
   block. An interlude's trials keep the session's trial numbering but belong to no block, and record the
   task they ran.
5. **Blocks follow a block-sequence policy** (replacing a fixed list): fixed, cyclic, seeded and
   balanced, or by criterion with advance and fall-back. A block ends on a number of trials, every
   condition's target met, a performance criterion, or a time limit. `taskd`'s guard against a spinning
   plan becomes a per-advance progress check.
6. **The continuous mode**: its own trial-less mode for long presentations. It can reward
   [@russ2015functional], insert probes on a schedule, change contingent on gaze or neural data,
   and take marks and pauses; it ends on a
   declared duration, its media ending, an operator stop or a criterion; it is analyzed as one epoch with
   timed events. **Stop, pause and the welfare limits are checked about once a second inside it**, with a
   console update; it strobes anchor codes (§8.4); it declares calibration probes, or the record states
   the gaze map's age. Its record shape is designed in build K and asked of wl-preproc.
7. **A session program** lists the runs; the console offers the next; the operator may deviate.
   **Per-animal state** (programs, presets, last values, procedure state) **lives on lab storage**,
   synced to whichever rig runs the animal (animals sometimes work on both, N§R6), one writer at a time,
   **outside the folder whose `bounds.py` the rig executes**.
8. **A run ends** when its plan is done, on an operator stop, or at a time limit.
9. **When the animal stops working**: an alert; a console checkbox with a trial count turns on
   auto-pause (a system-actor pause, §11.3).

## 14. Variation (N§11, N§R1, N§R2)

1. **Named conditions plus drawn values.** A parameter is set by a condition or drawn, never both (refused
   at load).
2. **Factorial designs**: factors and levels, combinations minus exclusions, named from their levels.
3. **Orderings**: shuffled passes; weighted draws; limits on repeats; sequence-balanced.
4. **Distributions**: uniform; a weighted set; normal, truncated; a prepared list; a non-aging
   foreperiod (§6.11).
5. **Condition numbers are fixed per task** (XC-197): a condition keeps its number across runs, sessions,
   animals and both rigs; **numbers are assigned by the task's registry on lab storage** (one writer), a
   rig-added condition taking the next unused one; numbers never reused.
6. **Seeds**: fresh per run, recorded, replayable.
7. **A live edit to a value a condition sets wins**, and **the trial still counts toward its condition**
   (N§R2, offered against: not counting it). The parameter-change code goes out, and **the trial table
   carries an "overridden" flag** that wl-preproc reads (an ask, §21), so grouping by condition number
   cannot silently include overridden trials. The console shows which conditions an edit overrides.

## 15. Adaptivity (N§12)

1. **Methods**: up-down staircases, interleaved staircases, Bayesian methods (QUEST, QUEST+, Psi),
   training progressions that may step back.
2. **A reviewed library plus task code** (between-trial Python, flagged for review).
3. **What moves a staircase is declared per procedure**; the default reads the counting table (§16.1):
   correct as success, wrong and miss as failure, trials ending before the decision ignored.
4. **State carries per animal when declared** (§13.7).
5. **What a procedure may read**: outcomes and reaction times; anything the trial recorded (the
   generator wait included); gaze traces; neural features.
6. **A live value on a procedure-controlled parameter** holds and pauses the procedure until released.
7. **Reward** (welfare, §20): a procedure may choose among the bounded config's named reward entries;
   never an amount.

## 16. Counting and repeats (N§13, N§R1, N§R2)

1. **One table classifies every outcome**, per trial structure: whether it **counts** toward its
   condition's target, and whether it is **repeated**. **Counted by default: every trial with an
   answer** (N§R1): correct, wrong, early and late variants, and, where withholding is an answer (catch
   trials, detection, go/no-go), misses, correct rejections and false alarms. **Not counted: trials that
   end before the decision** (breaks, no fixation, faults).
2. **Repeated by default**: `FIXATION_BREAK`, `NO_FIXATION`, `TRACKER_LOST`, `FAULT`. **For other breaks
   the task chooses, when repeats are active, whether such a trial is spent** (counted as presented and
   marked an abort) **or owed** (shown again later) (N§R1). Not repeated: wrong targets (2026-08-31).
3. **Where a repeat goes**: at a random later point in its block, never the very next trial
   (superseding 2026-08-31's "end of the block") **unless it is the only condition still owed, when it
   repeats at once, recorded** (N§R2). Build C defines "later" for each order type and for criterion- and
   time-ended blocks.
4. **Blocks whose order is the design** (priming, sequence-balanced) **declare their repeat rule**,
   defaulting to no repeats; **the realized sequence is recorded either way**: each trial's actual
   predecessor, aborted ones included, and whether their display was shown.
5. **A repeat's drawn values** are fresh or the same, declared per task (N§R1).
6. **A cap per condition**: past N repeats in a block, the condition's remaining debt is forgiven, its
   shortfall recorded, shown and flagged as possible avoidance (N§R2).
7. *Stated limitation*: conditions the animal breaks on more often drift toward the end of a block, so
   condition can covary with time in the block; position in the block is in the record.

## 17. Parameters and live control (N§14, N§R7)

1. **The order of values**: task start < run value < condition or drawn value < procedure < live edit,
   all under the bounded config's ceilings; **live edits are their own layer** (the names edited and
   their values), not merged into the run's values; an operator's hold pauses a procedure.
2. **A live edit takes effect at the next trial boundary**, except a parameter the task declares
   **instant**, which changes on the next frame, superseding the PI's 2026-09-19 "every name alike" for
   those (N§R7). **A bounded setting is never instant.** Instant edits and live inputs from the console
   reach the rig through a per-frame channel (the ADR, §22); their record rows are written at the next
   boundary, never inside a frame.
3. **At session open, the operator chooses** where an animal's values start: last values, the task's
   defaults, or a preset.
4. **Presets** per animal and task, applied as one recorded change.
5. **An edit history with revert.**
6. **Presets, revert and carried-over values never carry a bounded setting** (a reward size), keeping
   the PI's b3a rule that a reward size changed in a run lasts only for that session. On the welfare
   summary for his confirmation.

## 18. Recording and review (N§15)

1. **A task's review report**: the state diagrams and codes; example frames per state (exact drawer,
   per eye); the plan in tables; a simulation census per condition and block; a timing diagram (with the
   foreperiod's realized hazard, §6.11). Made for each task version and kept; a session records its
   task's report version.
2. **Simulation is advised, not enforced.**
3. **The simulated animal** follows declared functions with named profiles: perfect, chance, an
   incorrect strategy, normal (85% correct), trying to break the task, trying to exploit the reward
   schedule.

## 19. Warnings, and what a session is for (N§4, N§R6)

1. **Sessions declare what they are for**: training, piloting or recording, chosen at session open and
   carried in `OpenSession`, the session spec, `config.json`, the restoration a resume reads, and
   telemetry (a schema bump).
2. **The warnings list** gathers every imperfection a session runs with: the default calibration, a
   calibration past 30 days, dithering, a lossy image, a luminance step under a pattern, a pattern near
   the pixel limit, a screen, mode or care-feature mismatch, a timing record older than a graphics change,
   a head-free session, frame-clock faults, and today's pre-flight unknowns. **Each states the session
   kinds it is acceptable in**; outside them it refuses. Load-time check findings gain this severity
   ("a warning, accepted in kinds K") beside blocking.
3. **Accepted once per session**, at open, recorded. **A warning appearing during a run that its kinds do
   not accept pauses the run at the next trial**, for the operator to accept (recorded) or stop (N§R6).
   Today's unknowns keep the 2026-09-19 rule: proceed on a recorded acknowledgment.

## 20. Welfare

Welfare-critical code is on architecture.md's list (the PI keeps it unchanged unless he widens it). This
design changes listed functions or welfare-adjacent behavior in these places, each for the PI's numbered
summary before its build merges:

1. **`preflight.gate` and `Service._start`**: warnings acknowledged once per session instead of per run;
   new run-start refusals (a warning outside its session kinds; a fixed-head task in a chaired session;
   no validated eye map; the stereoscope's alignment not accepted; a self-pausing run without
   `PAUSE`/`RESUME`).
2. **`Service._open`**: the session kind; a refusal while the OLED's maintenance is due.
3. **`Session.set`**: instant parameters, never a bounded setting; presets, revert and carried values
   never carry a bounded setting (§17.6).
4. **`Session._ends` and `_hold`**: checked about once a second inside long trials and the continuous
   mode; continuous-mode rewards.
5. **Adaptive procedures choosing among named reward entries** (§15.7).
6. **Automatic pauses**: on a display crash (§11.3) and on disengagement (§13.9), by a system actor.
7. **A generated image waited for as long as it takes** (§4.8), with the welfare clocks running.
8. **The parked demo mode's items**, when it returns.

## 21. Asks of other repositories (sent once this spec is approved)

- **wl-preproc**: condition numbering for `CONDITION` (XC-197); the trial table's "overridden" flag
  (§14.7); reading monocular and session-start calibrations (§12.4); the continuous mode's record shape
  and anchor codes (§13.6, §8.4); the session kind in the record (§19); onset alignment through the
  screen log and the flip count. **No change to its frozen codec.**
- **wl-xtasks**: the task object's format (§3.5) and plans; allocation of `STIMULUS_ON`, `STIMULUS_OFF`,
  `STIMULUS_CHANGED` and the anchor code (§8.3, §8.4).
- **wl-sync**: a two-channel line-out from the task PC card's analog outputs, started by the task-patch
  edge (§9.1); top-and-bottom test patches for V1's scan-out measurement (§6.5).

## 22. Amendments to other documents (each with the build that changes it)

- **A new ADR, or ADR-0003 amended**: the display's shared memory, the generator protocol, the per-frame
  console input, lab-storage sync (CLAUDE.md: transports go through an ADR).
- **ADR-0002**: our drawer built now as a Rust display process; V1 still chooses.
- **ADR-0004**: Rust crates and bundled fonts in the inventory, licenses verified at their sources.
- **S2 §4-5**: the stimulus codes now used, as task codes.
- **S4**: §2 and §7 to these conventions; §5's "pure function" with the live-driven and generated
  exceptions; §8 audio through the task PC's analog outputs; §9 one calibration per panel; §10's
  alignment target to the monocular grids, the disparity check kept.
- **S5 §7**: the session-start calibration is the rig's rule; the stereoscope's is the monocular grids.
- **S6 §1**: two analog outputs of the 6343 allocated to audio.
- **S8**: §2 and §8 item 3 (repeats, counting); §3.2 (instant parameters); §3.4 (the value order).
- **validation.md**: V1 (top and bottom patches, the 10-bit path, panel latency), V7, V12 item 3 (the
  pause screen).
- **architecture.md**: the display process, the screen description, the task object, the warnings list,
  the per-frame console input beside the mark socket.
- **The demo-mode spec**: real images from the exact drawer (§23).

## 23. Demo mode

Parked (XC-013). When it returns, its screen shows frames from the exact drawer, labeled, instead of a
schematic. Its spec's §14 list still applies.

## 24. Builds, in order

The PI's order: **definition first, display by January**.

| Build | Scope | Needs |
|---|---|---|
| **S** | The Vulkan spike (§10.5). | A's Gabor definition; the PI's Linux machine for timing |
| **A** | The screen description and the slow exact drawer: blocks, edges' semantics, combinations, groups, placement and per-eye positions, the color spaces and conversion, contrast conventions (migrating the reference tasks), deterministic generators; the review report's frames. | — |
| **B** | Session kinds and the warnings list with its severity model; the default calibration and calibration records; the `visual_search` training variant. | A |
| **C + I** | The task object; trials that vary (plans, block-sequence policy, conditions, drawn values, orders, counting table, repeats, caps, interludes, condition registry); live edits as a layer; presets, history; the disengagement alert; the review report and the simulated animal's profiles. | A; wl-xtasks' agreement on the task object |
| **E** | The display process: shared memory (after the ADR), lockstep, patches, 10-bit, the lookup table, per-refresh reports, the no-op and development drawers, the rate from the display's mode. Ready for January's V1. | S, A |
| **T** | The eye tracker's session-start calibration, the stereoscope's monocular grids, the pre-session checks (§12.2-12.5). Before the first animal session. | E; the tracker |
| **D** | The adaptive library. | C |
| **F** | Recording: stimulus codes, the screen log, per-refresh reports, onset extents, overridden flags. | E; wl-xtasks' codes |
| **G** | Media and sound (audio through the task PC card). | E; wl-sync's line-out |
| **H** | Live control: gaze-anchored and mouse-driven stimuli, instant parameters and the per-frame console channel, the hand-mapping schematic, neural inputs, generated images. | E, C; the ADR |
| **J** | Color calibration by spectroradiometer (§12.1). | E; the instrument |
| **K** | The continuous mode, with its once-a-second checks and anchor codes. | E, F |
| — | Then the reference tasks made right (with the PI's decisions), then demo mode. | |

## 25. Not decided here, and why

- **What the PI decides when the reference tasks are made right**: `adaptive_detection`'s staircase and
  catch trials, `visual_search`'s `item_window`, `calibration`'s `cal_hold`.
- **Formats designed in their builds**: the shared-memory layout (E), the generator protocol (H), the
  continuous mode's record (K), the task object's exact shape (C, with wl-xtasks), "later" per order
  type (C).
- **Every UNVERIFIED hardware fact**: the panel's scan-out, sRGB mode, care features and maintenance
  control; the 10-bit path; the ABL level; NVIDIA's present timing on this card; which connector carries
  the 6343's analog outputs. Measured at V1, V9, bring-up or the spike, never assumed.

## 26. The reviews

Two design reviews of the first draft (`8f9cb03`), kept as written: the science review
(`docs/superpowers/reviews/2026-10-07-engine-science-review.md`, 15 findings) and the feasibility review
(`...-engine-feasibility-review.md`, 20). The PI decided the findings that were his (N§R1-R7); this
revision fixes the rest, including two errors of the first draft: a citation its source did not support
(vstimd's notes do not describe NVIDIA device-lost failures) and an audio option that called the task
PC's card "the same card that records".
