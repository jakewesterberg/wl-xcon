# The engine for running tasks: brainstorm notes

**What this is.** A running record of the PI's answers while the display engine and the task
runtime are brainstormed as one design, element by element (PI, 2026-10-07: "Both, as one
design"; then "I want to do a far more in-depth brainstorm on the specific elements of the
engine components. These are central to a large component of the experimental setup. So, we
need to be careful in making this flexible and effective."). It is not the spec: the spec is
written from it once the elements are discussed. Every answer is quoted as given in the UI.
The surveys this starts from: `docs/research/2026-10-07-engine-display-state.md` and
`docs/research/2026-10-07-engine-runtime-state.md`.

## Decided before the elements (2026-10-07)

- **Both halves as one design** ("Both, as one design").
- **Our own thin GPU drawer is built now** ("Build our own thin one now"), so January's
  photodiode test (V1) can compare it with PsychoPy on day one. This reopens ADR-0002's
  2026-08-31 ruling "decide after V1" only as far as building the thin stack before the
  measurement; the choice of engine is still V1's.
- **Built in three pieces** ("Looks right"): the display core first (the shared description of
  the screen, degrees to pixels, the patches, colors with the default calibration and the
  warnings list, the slow exact drawer), then trials that vary, then the GPU drawer.
- **Element by element, in depth, before any design section** (the PI's words above).

## The elements

Display engine: 1 what can be shown; 2 where; 3 when; 4 color and luminance; 5 sync and
evidence; 6 media and sound; 7 the drawer; 8 lifecycle; 9 calibration procedures and test
screens. Task runtime: 10 structure; 11 variation; 12 adaptivity; 13 aborts and repeats; 14
parameters and live control; 15 recording and review. The PI chose to start with 1.

## 1. What can be shown

**The paradigms the engine must run in the lab's first years** (asked 2026-10-07, all four
groups chosen: search and attention; RF mapping and laminar probes; natural images and movies;
stereo and dichoptic), and in the PI's words: "rapid serial visual presentation, adapation,
rule-based cue tasks, priming blocked tasks, memory-guided saccades, visually-guided saccades,
multisensory (audiovisual) decision-making, perceptual decision-making, binocular rivalry,
binocular rivalry flash suppression, bar-sweep RF mapping, sparse noise mapping, tuning tasks
(color, orientation, size, spatial frequency), delayed-saccade task, curve tracing, figure-ground
tasks, free viewing visual search, search arrays, 2+ AFC, visual discrimination, visual
detection, color matching, forward and backward masking tasks, most exciting images generation
and testing, gaze-contingent visual stimulation, closed-loop visual presentation based on neural
data, scene grammar tasks, predictive processing sequences, oclusion tasks, monocular vs.
binocular presentation, full screen flash, M/P/K cell mapping tasks, a manually controlled
stimulus movement (use mouse to move stim around screen while monkey fixates to preliminarily
map e.g. RFs), betting tasks, and probably many more over time!"

What that list asks of the display, grouped (the session's reading, put to the PI):

1. More kinds of things to draw: lines and curves, text and symbols, texture fields with a
   figure region, Mondrians, sparse-noise grids, cone-isolating and isoluminant patterns,
   placeholders and arrows.
2. Things combined: objects in front of scenes, apertures on any pattern, layering and
   transparency, free layouts.
3. Changes inside a trial: sequences, motion along a path, flicker and counterphase, brief
   flashes (element 3).
4. Things nobody wrote down in advance: images generated between trials; positions driven live
   by gaze, by the operator's mouse or by neural data. These break "position is a pure function
   of parameters, seed and frame" (S4 §5): their paths, and generated images, must be recorded.
5. Sound with sight (element 6).

**How stimuli are described** — "Building blocks + reviewed extensions": a stimulus is a shape,
filled with something, seen through an edge profile, placed and layered; named kinds (Gabor,
plaid) stay as shorthands; a new block is added once as reviewed framework code with its exact
definition (the slow drawer), its GPU version and tests, and is then usable in any combination.
Task files hold no drawing code (ADR-0006).

**A first set of blocks** was put to the PI (shapes: circle and ellipse, rectangle and polygon,
ring, line or curve, text, whole screen, an image's own outline; fills: flat color, grating,
checkerboard, noise, sparse noise, moving dots, random-dot stereogram, texture field, Mondrian,
image, movie; edges: hard, Gaussian, raised cosine; on every stimulus: position, orientation,
size, eye, disparity, layer, contrast, opacity). Asked whether it was complete, he answered:
"err on the side of asking me more questions, I want lots of questions to answer to help shape
this". The questions that follow take the set apart block by block.

**Image manipulations** (scrambling, filtering, cropping, recoloring) — "Between trials": a
reviewed procedure, with its seed, makes the image before the trial that shows it; the result is
uploaded and kept in the record; the same route the most-exciting-images generator needs;
nothing is computed inside a frame.

**Batch 1, how stimuli combine and are placed** (asked 2026-10-07):

- **Overlap** — all four: "Front covers back" (opaque or partly see-through by an opacity),
  "Contrasts add" (plaids, signal in noise, transparent motion), "Window or scotoma" (a stimulus
  reveals or hides others only inside its area), "One shapes another" (one stimulus multiplies
  another, e.g. a contrast envelope).
- **Position measured from** — all four: the screen's center, another stimulus, where the eye is
  now, a live input (the operator's mouse, a joystick, a neural signal).
- **What a live source may drive** — "Any numeric property": position, orientation, size,
  contrast, color, speed...; every live value recorded frame by frame.
- **Contrast** — "Always written explicitly": every contrast is given with its convention (e.g.
  `contrast=Weber(0.3)`, Michelson, RMS); nothing implied.

**Batch 2, patterned fills** (asked 2026-10-07):

- **Noise** — white, binary, pink (1/f), band-pass, and (the PI's addition) **color noise**.
- **RF mapping** — all four: sparse noise; dense noise or m-sequence; flashed and swept bars;
  subspace (Ringach/Hartley) gratings.
- **Moving dots' noise rule** — "Declared per task": the task names the rule (re-plotted
  positions, a random direction per dot, a random walk), since each changes what a coherence
  level means.
- **What defines a figure against its ground** — all four: orientation, motion, color, disparity.

**Batch 3, images and movies** (asked 2026-10-07; all as recommended):

- **A photograph's colors** — "As the photo intends": the file is read as standard sRGB and
  converted through the rig's calibration (measured or default); the record names the
  calibration.
- **Matching image sets** — "When a task asks": a declared preparation step (mean luminance, RMS
  contrast, optionally the amplitude spectrum), recorded with the set; off unless named.
- **Image size** — "Declared per stimulus": degrees (resampled with a stated filter) or pixel for
  pixel (no resampling).
- **Movie frames to refreshes** — "Whole refreshes only": each movie frame held a whole number of
  refreshes (30 fps = 8 at 240 Hz, 24 fps = 10); a rate that does not divide the display rate is
  refused until the movie is re-timed beforehand; every frame's timing exact and recorded.

**Batch 4, generated images, text, curves, outlines** (asked 2026-10-07; all as recommended):

- **Where generated images are made** — "Another machine": a GPU server on the lab network makes
  each image between trials and sends it; the rig checks, records and shows it; the rig's GPU
  stays the display's.
- **Text** — "Letters, digits, symbols": one or a few bundled fonts, glyph height in degrees,
  rendered to exact pixels.
- **Curve-tracing curves** — "Both": a fixed path written in the task, or a reviewed procedure
  generating curves between trials from a seed, saved in the record.
- **Outlines** — "Yes, on any shape": an outline width and color separate from the fill.

**Batch 5, masks, Mondrians, background, the field's edge** (asked 2026-10-07):

- **Masks** — all four (noise masks; pattern masks; metacontrast; object substitution, four dots
  outlasting the target) and, the PI's addition, a **full screen mask**. Each built from blocks;
  any that cannot be becomes a reviewed extension.
- **Mondrians** — all four materials: colored rectangles, grayscale rectangles, mixed shapes,
  image fragments.
- **The background** — "Yes, as the bottom layer": layer 0, its color and luminance changeable
  during a trial like any stimulus. DKL colors are defined against the background, so the record
  says which background each color was set against.
- **Off the field** — "Only when declared": a stimulus may extend past the field's edge only if
  the task says so (a sweep entering from off-screen, a scene cropped by the mask); otherwise
  refused at load, as today.

**Batch 6, waveforms, randomness, layouts, item variety** (asked 2026-10-07):

- **Grating waveforms** — sine, square, triangle, sawtooth.
- **Random patterns** — "Seed, frames on request": every random pattern from a seed in the
  record, rebuilt exactly by the slow drawer; a task may also ask for the frames it showed to be
  saved (e.g. for reverse correlation on pixels).
- **Layouts** — grid; listed positions; random with spacing rules (drawn between trials from a
  seed); several rings or clusters.
- **Item variety** — "Each item its own stimulus": a display is a list of items, each free in
  shape, fill, color, orientation and size; target and distractor are roles, not appearances.

**Batch 7, scale, review, per-eye backgrounds, groups** (asked 2026-10-07):

- **The busiest display** — "Thousands of elements": dense line-element textures, large dot
  fields, many-item free-viewing displays; the GPU drawer batches many small elements per frame.
- **Who reviews a new block** — a lab member (the first option), and in the PI's words: "but we
  create a simple, person readable report that shows example frames with stages of the task,
  stimuli, etc." The slow exact drawer renders those frames; the same report serves a task's own
  review (ADR-0006's artifact gains example frames of each state).
- **Each eye its own background** on the stereoscope — "Yes"; the default is the same for both.
- **Groups** — "Yes": a named group shows, hides, moves and changes a shared property as one, its
  members still addressable on their own.

**Element 1 is discussed.** What can be shown: shapes x fills x edges, placed and layered, with
four ways to overlap, positions from four references, any numeric property drivable live,
explicit contrast conventions, between-trial image procedures and generators off the rig, and
reviewed extensions with a person-readable report.

## 2. Where

Settled before the element (S4 §2-3, the direct-view spec, the optics drawing): positions in
cyclopean degrees, never pixels; direct view one image at Z = 50 cm; the stereoscope two
halves of one framebuffer, each eye's path measured, a software vergence offset, a ±12° mask;
disparity as equal and opposite horizontal offsets; field limits checked at load.

**Batch 1** (asked 2026-10-07):

- **Sizes and patterns away from the center** — "Declared per task": either true visual angle
  (every stimulus subtends its declared degrees wherever it sits; a grating keeps its cycles per
  degree) or the screen center's scale; the record says which. (At 30° out in direct view a
  degree covers 15-33% more screen than at the center.)
- **Angles** — "Math convention": 0° points right, counter-clockwise positive, +y up, for
  positions, motion directions and orientations alike (0° = horizontal bars); a grating's
  orientation names its bars, its drift direction is a separate angle.
- **Disparity sign** — "Near is negative": crossed negative, uncrossed positive, in degrees.
- **(0°, 0°)** — "Straight ahead": the rig file records where straight ahead falls on the screen
  (default its center).

**Batch 2** (asked 2026-10-07):

- **Default away from the center** — "True visual angle", unless a task declares otherwise.
- **Where the eye is, for a gaze-anchored stimulus** — "selectable between the three options":
  the newest sample, a smoothed one, or one predicted to the frame's appearance, declared by the
  task; each frame's sample age recorded.
- **Gaze window shapes** — "Any shape": circles, ellipses, rectangles, polygons, or a stimulus's
  own outline grown by a margin.
- **Head-free chaired sessions** — "Nominal, recorded": nominal head position for positions and
  windows; the record and the warnings list say the head was free; a task may declare it needs a
  fixed head and is then refused in chaired sessions.

**Batch 3** (asked 2026-10-07; all as recommended):

- **A gaze-anchored stimulus when gaze is lost** — "Declared per task": hold its last position,
  hide, or freeze the trial; every lost frame marked in the record.
- **During a saccade** — "Declared per task": follow every frame, or update only when a saccade
  lands (inside saccadic suppression).
- **Per-eye positions on the stereoscope** — "Free per-eye positions": a stimulus may sit at a
  different position in each eye (rivalry in non-corresponding places, nonius lines, fusion
  tests); disparity stays the shorthand for the common case.
- **Manual RF mapping's view** — "A live schematic": a drawing of the animal's screen in the
  console with the fixation point, the stimulus, the gaze dot and markers the operator drops,
  before the full replica (V11) exists.

**Batch 4** (asked 2026-10-07; all as recommended):

- **Default gaze rule for a gaze-anchored stimulus** — "Newest sample".
- **What one size number means** — "Full width": diameter, side length, full bar length; each
  block's definition states it.
- **A position linked to another stimulus that moves** — "Declared per link": a live link (moves
  with it) or placed once at onset.

**Element 2 is discussed.**

## 3. When

Settled before the element: a decision on frame N shows on frame N+1; motion is a function of
the frame number; late frames are counted, never hidden, and the hardware frame clock (`PD2`) is
the authority; the panel runs 240 Hz (4.17 ms), with 120 Hz available.

**Batch 1** (asked 2026-10-07):

- **Durations that are not whole frames** — "Declared tolerance": rounded to the nearest frame and
  recorded as shown; a task may mark a duration exact, and an exact one that does not fit whole
  frames at the session's rate is refused at load.
- **A dropped or late frame during a trial** — "Always continue, mark": the trial continues; the
  record marks each late frame for analysis to judge.
- **Temporal frequencies that do not fit whole frames** — "Smooth ok, hard refused": sine
  modulation sampled per frame at any frequency (recorded); square-wave flicker needs whole frames
  per half-cycle or is refused at load.
- **Onset and scan-out** — the PI asked: "These are oleds? I dont think there is a scan line
  delay?" Checked: OLEDs remove slow pixel response, not the top-to-bottom refresh; a non-strobed
  OLED lights rows as they arrive, so the bottom changes up to one frame period after the top
  (Blur Busters, "Understanding Display Scan-Out Lag With High Speed Video",
  https://www.blurbusters.com/understanding-display-scanout-lag-with-high-speed-video/, read
  2026-10-07; general, UNVERIFIED for the PG27UCDM until V1). Both setups put the light sensors at
  the bottom, so they report a frame near the end of its scan. Re-asked below.

**Batch 2** (asked 2026-10-07):

- **Onset** — "Frame start + height": the record holds each frame's start and each stimulus's
  vertical position; analysis adds the scan delay for that height from V1's measurement of this
  panel (V1 places test patches top and bottom). Nothing estimated is written as fact.
- **Rapid sequences** — "Both": a sequence stimulus (items and timing in one declaration, or drawn
  per trial from a seed, with events such as "item 7 shown" for the states to react to), or one
  state per item, as the task prefers.
- **Motion paths** — all four: straight sweeps; pursuit targets (step-ramp, sinusoidal, circular,
  Lissajous); waypoint paths; seeded random walks.
- **Refresh rate** — "Any rate": times in seconds, converted at the session's rate (240 or 120
  Hz) under the tolerance rule; a task may declare a required rate.

**Batch 3** (asked 2026-10-07):

- **The longest trial** — "Minutes at most": a fixed cap of a few minutes for every task (the
  number asked next).
- **Continuous presentation** (a 20-minute movie with free viewing, long adaptation with probes) —
  "Yes, as its own mode": a trial-less mode with its own record shape. Its details belong to
  element 10 (structure) and are asked there.
- **Between trials** — "Declared per task": the background by default; a task may keep stimuli up
  across trials (a fixation point, a topped-up adapter) or show an ITI display of its own.
- **Delay from eye or neuron to screen** — "Measured, declared limit": each change records its
  delay (sample age plus the frame it landed on); a task may declare a maximum and trials past it
  are marked; V3's photodiode measurement gives the true end-to-end figure.

**Batch 4** — **the cap on a single trial: "5 minutes"**; a trial still running at the cap ends
as a fault; longer presentations use the continuous mode.

**Element 3 is discussed.**

## 4. Color and luminance

Settled before the element: colors in xyY (absolute) or DKL (cone contrast about the
background, `lum=0` isoluminant); a measured `photometry.Calibration` names its observer; an
uncalibrated color refused today; the PI's 2026-10-07 ruling for a default calibration and a
warnings list. Known hazards: a QD-OLED's transfer is not a power law; ABL dims the panel with
fill; low contrasts need fine steps.

**Batch 1** (asked 2026-10-07):

- **The default calibration** — "Standard sRGB": the panel set to its sRGB mode and the published
  sRGB standard (primaries, D65 white, transfer curve) used when the rig file names no measured
  calibration; how closely the panel's sRGB mode follows it is unknown until measured, and the
  warnings list says so.
- **Isoluminance on the default calibration** — "No": a task claiming isoluminance (DKL `lum=0`
  with a chromatic component) needs a measured calibration with a stated observer, in every
  session. Consequence put to the PI next: `visual_search`'s red and green are isoluminant DKL,
  so it still does not load on the default.
- **Bit depth** — "10-bit, verified at V1": 1024 levels per channel if the card, cable and panel
  carry 10-bit at 4K/240 (unverified for this pairing); dithering as the fallback where not.
- **The panel's transfer** — "A measured table": a lookup table per channel (and per eye's half on
  the stereoscope) from a photometer sweep; the default uses the sRGB curve.

**Batch 2** (asked 2026-10-07):

- **`visual_search` on the default calibration** — "A plain-color variant": the task keeps its
  isoluminant colors and waits for a measured calibration; a training variant uses ordinary red
  and green (no isoluminance claim) that loads on the default, with the warning shown.
- **The panel's brightness limiter (ABL)** — "Stay below it": overall brightness capped so the
  limiter never engages, at a level V9 measures; a display that would exceed it refused at load;
  the record states the cap.
- **The default background** — "Black". Consequence put to the PI next: DKL colors and Weber
  contrasts are defined against the background and mean nothing against black.
- **Accepting warnings** — "Once per session": listed in a console tab, written to the record,
  acknowledged once when the session opens (a warning appearing later asks again); today's
  pre-flight unknowns join the list under the PI's 2026-09-19 rule (proceed on a recorded
  acknowledgment).

**Batch 3** (asked 2026-10-07):

- **Background-relative colors and contrasts on the black default** — "It must declare one": a task
  using DKL colors or Weber contrast sets its own non-black background, or is refused at load with
  the reason; absolute colors (xyY) and Michelson contrast run on black.
- **Sessions say what they are for** — "Yes": training, piloting or recording, chosen at session
  open and recorded; each warning states the kinds it is acceptable in (e.g. the default color
  calibration fine for training and piloting, refused for a recording task that declares color
  part of its design).
- **Calibration per eye's half on the stereoscope** — "One for the panel": the halves are assumed
  equal. This changes S4 §9's plan of a transfer per panel half.
- **A calibration's age** — in the PI's words: "never expires, but there is an age that is
  associated with the calibration. A warning pops after 30 days."

**Batch 4** (asked 2026-10-07; both as recommended):

- **Cone sensitivities for DKL** — "Named in the calibration": each calibration names the cone
  fundamentals it converts with (a human standard such as Stockman & Sharpe's 2°, or macaque
  estimates once a source is chosen and cited); the default uses the human standard and says so.
- **Color noise and colored Mondrians on the default** — "Yes, with the warning", in whatever
  session kinds the session-kind rules accept.

**Element 4 is discussed.**

## 5. Sync and evidence

Settled before the element (S4 §7, S3 §8, the direct-view spec §4): the flip patch alternates
every refresh, unconditionally, a frame clock into the NI card (`PD2_COMP`); the task patch is
driven by the display from the scene's own onset; event codes strobe at decision ("now, not on
the next flip"); `Onscreen` advances on the sensor's evidence; dropped frames are detected in
hardware.

**Batch 1** (asked 2026-10-07):

- **What lights the task patch** — "Every change": any onset, offset or update toggles it; the
  record's frame numbers say which change each edge was. (Offered against: close changes blur for
  the sensor, which cannot itself tell changes apart.)
- **When an onset's event code goes out** — "As now": at the decision; the light sensor gives the
  exact time; codes never wait on the display.
- **Matching frames to the recording** — "Count from each trial": flip-patch edges counted from each
  trial's start code, checked against the trial's known length, so a missed edge shifts frames
  within one trial at most.
- **What the record keeps about the screen** — "Changes + live values": every onset, offset and
  update with its frame and full resolved description; every live-driven value per frame; seeds
  for every random pattern; any frame rebuildable by the slow drawer.

**Batch 2** (asked 2026-10-07):

- **Codes for stimulus onsets and offsets** — "Automatic onset/offset codes": the framework strobes
  a code for every stimulus onset and offset (offered against: only the task's codes). Needs codes
  allocated; the event vocabulary is wl-preproc's (ADR-0007). Follow-ups asked next.
- **Frame timing in the console** — "Yes, per trial": late frames per trial and a running count, a
  warning past a rig-set rate, shown at trial boundaries.
- **A frame-clock fault** (the sensor stops, or disagrees with the display's count) — "Warn and
  mark": a console warning and a warnings-list entry, affected trials marked, the session goes on;
  the operator decides whether to stop.

**Batch 3** (asked 2026-10-07; all as recommended):

- **Where the automatic codes come from** — "Two framework codes": new framework escape codes,
  "stimulus on" and "stimulus off", each followed by the stimulus's number within its trial (its
  name in the record), asked of wl-preproc, which owns the vocabulary (ADR-0007), once the spec is
  approved.
- **In-place changes** — "Yes, a third code": "stimulus changed", with the stimulus's number; the
  record says what changed.
- **Groups** — "One code for the group": one "stimulus on" with the group's number; the record
  lists its members.

**Element 5 is discussed.**

## 6. Media and sound

Settled before the element (S4 §6, §8; V7): sounds are declared assets, resident before use,
with `AUDIO_ON`/`AUDIO_OFF` codes and their onset measured by a tap into a misc analog input;
images and movies resident before an epoch, within a budgeted memory, each set versioned and
recorded per trial.

**Batch 1** (asked 2026-10-07):

- **What plays sounds** — "The NI card's analog output": waveforms played by the recording card,
  sample-accurate on the recording's own clock, through an amplifier.
- **Speakers** — "Two, left and right": stereo for lateralized sounds; a centered sound plays on
  both. Consequence: two analog outputs on the NI card, part of S6's I/O allocation (the card is
  the PI's purchase).
- **Movie soundtracks** — "Optional per movie": when played, kept in step with the frames and their
  timing recorded.
- **Image formats** — "Any common format": JPEG allowed, with a warning (offered against: lossless
  only).

**Batch 2** (asked 2026-10-07; all as recommended):

- **Where media live** — "Lab storage, by checksum": sets on the lab's storage (the NAS) with a
  manifest of each file's checksum; a task names a set and version; the rig keeps a local copy,
  checks every checksum before a session and records the set's identity; large media stay out of
  git (backlog XC-027's question).
- **When media are loaded** — "Per run, refused if too big": everything a run can show loaded before
  it starts; a run whose sets do not fit is refused at its start with the numbers.
- **Movie decoding** — "Declared per movie": short clips decoded into memory beforehand; long ones
  streamed by a decoder thread that stays ahead, a missed frame recorded as late.
- **Simple sounds** — "Made from parameters": tones, clicks, noise bursts and sweeps from their
  parameters (and a seed), rebuilt from the record; files remain for recorded sounds.

**Element 6 is discussed.**

## 7. The drawer

Settled before the element: our own thin GPU drawer built now (glfw and moderngl in the 2026-08-31
spike); the slow exact drawer is the definition and the GPU drawer is tested against it; thousands
of elements per frame; 10-bit output with dithering as the fallback; a measured lookup table; no
allocation inside a frame (CLAUDE.md).

**Batch 1** (asked 2026-10-07):

- **How closely the GPU drawer matches the exact definition** — "Within one output level": every
  pixel within one of the 1024 levels, tested on reference scenes for every block and in
  combinations.
- **Edges between pixels** — "Smooth, sub-pixel": anti-aliased by coverage, so stimuli sit and move
  in fractions of a pixel.
- **Patterns near the pixel limit** (about 28-31 cycles/degree at the center in direct view) —
  "Warned": allowed, with a warning naming the stimulus and the limit (offered against: refused).
- **The graphics interface** — the PI: "can we spike vulkan to test? it seems like a better
  long-term option". What the session found, 2026-10-07 (web, not verified on this hardware):
  Vulkan offers direct-to-display (`VK_KHR_display`, no compositor in the path) and per-frame
  presentation timing (`VK_EXT_present_timing`, newly standardized; Phoronix reports NVIDIA's
  Linux driver supports it, UNVERIFIED for the RTX 5070 Ti and its driver); Python routes are raw
  bindings (`vulkan`, realitix, last release 2024), wgpu-py (WebGPU over Vulkan, which hides both
  features) or a compiled core; prior art: vstimd, a Rust Vulkan stimulus server driving displays
  directly with `VK_KHR_display` (maintainer and license not stated on the page read). On this Mac
  Vulkan runs through MoltenVK onto Metal: a spike here tests feasibility, never timing (P4a).

**Batch 2, the Vulkan spike** (asked 2026-10-07):

- **What the spike does now** — "Feasibility now, timing later": draw a Gabor, the light-sensor
  patches and two eye viewports through Vulkan, render offscreen to compare with the slow exact
  drawer, measure the code it takes, and check NVIDIA's documented support for direct display and
  presentation timing; timing waits for Linux and an NVIDIA card.
- **The route from Python** — "A compiled display core": a small Rust or C++ core owning the
  display, called from Python (offered against: raw Python bindings, recommended; wgpu-py).
- **A Linux machine with an NVIDIA GPU before January** — "Yes" (which, and how to reach it, asked
  next).
- **vstimd** — "Yes": read its source as prior art (license, upkeep, how it drives the display and
  paces frames); nothing adopted without asking.

**Batch 3, the compiled core** (asked 2026-10-07; the PI answered the first question and stopped
to clarify the rest):

- **The core's language** — "Rust".
- **vstimd, read** (`docs/research/2026-10-07-vstimd-prior-art.md`): Rust on `ash`, alpha, one
  maintainer; the daemon AGPL-3.0-only and its Python client LGPL-3.0-only, so nothing is reused,
  only ideas; trigger-driven over ZMQ rather than per-frame lockstep; direct display through
  `VK_KHR_display`, FIFO, paced by a post-flip vblank wait; 8-bit sRGB only, no LUT, no stereo, one
  photodiode patch; no committed timing measurement.

**Batch 3, continued** (re-asked 2026-10-07 after the PI asked "why did you recommend same
thread?": the first recommendation was the same process with the core on its own native thread;
reconsidered, a separate process wins on crash containment, keeping the screen up across rig-service
restarts, and its own real-time priority):

- **How Python and the core talk** — "Separate display process": the Rust core runs as its own
  program with real-time priority and owns the screen; the rig service hands it each screen
  description through shared memory and gets back the frame each change landed on; a driver crash
  cannot take the session with it.
- **Who reviews the core** — "Tests carry it": a person reviews the Python exact definitions and
  the visual report; the core is held to them by the one-level match tests and V1; no core change
  merges without them passing.
- **The Linux NVIDIA machine** — SSH from this Mac, and in the PI's words: "it is not on at the
  moment, and I am not at home to switch it on. we can revisit the spike when I am home".

**Element 7 is discussed.**

## 8. Lifecycle

**Batch 1** (asked 2026-10-07):

- **When the display process starts** — "At boot, as a system service": it owns the stimulus
  screen from power-on, restarts itself if it dies, and the rig service connects to it.
- **The animal's screen with no session** — "Black": true OLED black; a session's background
  appears only when it opens.
- **The display process dying during a trial** — "Fault, restart, pause": the trial ends as a rig
  fault, the display restarts on its own, and the session pauses at that boundary until the
  operator resumes.
- **The screen during a pause** — "Declared per task", and in the PI's words "default is black":
  black unless the task declares what stays up. Changes V12 item 3's plan (background during a
  pause). The flip patch still alternates during a pause (S4 §7).

**Batch 2** (asked 2026-10-07):

- **Checking the screen and its mode** — "Warn on a mismatch": the rig file names the panel,
  resolution, refresh rate and bit depth; a difference goes on the warnings list (offered against:
  refuse).
- **A windowed display** — "Simulations only": labeled "development: not timing-valid", for
  simulations, demo mode and tests; a real animal's session needs the rig's panel in exclusive
  full-screen mode.
- **After a change to the display software or graphics driver** — "A warning until re-measured":
  the rig records what V1 measured with (core version, driver, kernel, mode); while no V1 matches
  the current setup, the warnings list says so (offered against: refuse animal sessions).
- **The OLED's own maintenance cycle** — "Scheduled, never in a session": triggered by the rig
  outside sessions and recorded if the panel allows it; otherwise a session refuses to open while
  the panel says maintenance is due. Whether the PG27UCDM allows either is UNVERIFIED (S0 §5.1).

**Element 8 is discussed.**

## 9. Calibration procedures and test screens

Settled before the element: S4 §10's test screens (per-eye alignment, required at every session
start on the stereoscope; geometry grid; gamma ramp; photodiode patch test; frame-timing pattern;
disparity verification); one color calibration for the panel, sRGB by default, 30-day warning;
XC-002 (automated color calibration in the rig) whose instrument choice was never asked.

**Batch 1** (asked 2026-10-07):

- **The instrument for color calibration** (a scientific choice; buying it stays the PI's) — "A
  spectroradiometer": full spectra, so luminance and cone contrasts for any observer, macaque
  included, and any cone fundamentals named later (XC-002's fork).
- **Who runs it** — "Automated, from the console": with the instrument at the eye point, the rig
  shows the patches, reads the instrument, fits the table and writes a dated calibration record.
- **Checks before every session** — the quick frame-timing check (ten seconds of flips timed by the
  sensor; a warning past a rig-set late-frame rate) and the light-sensor (photodiode) test. The PI
  asked whether "eye alignment" meant the eye tracker's calibration: it did not (S4 §10 item 1 is
  the stereoscope's per-eye alignment target, already required every session there), and the
  vague "direct view" option offered was dropped.
- **The eye tracker's calibration at session start** — "Full calibration, every session", as S5 §7
  planned: the thirteen-target constellation before any task runs; no first task without a
  validated map; calibration epochs inside tasks keep tracking drift. (S5's "planned by wl.works"
  was retired 2026-10-01; this is now the rig's rule.)
- **Where calibration and timing records live** — "Committed per rig": under
  `docs/measurements/<rig>/`, each with an id; the rig file names the calibration in force; every
  session records the id.
- **The stereoscope's per-eye alignment check** — the PI's method, in his words: "You do
  monocular presentations of the 13-point calibration grid. Then you look at the alignment of eye
  position between the presentations in each eye. If the the alignment is good, then the eye
  positions should be the same between the each monocular grid. If they are not aligned well, the
  eyes will be in different positions. this is something that the console can recognize and
  quantify. We should have a tolerance that is acceptable for off-alignment." (Offered against: a
  person with a camera at setup plus a tracker check, both, or either alone.)

**Batch 2** (asked 2026-10-07; as recommended, with the tightest tolerance):

- **One procedure on the stereoscope** — "Yes": each eye's monocular grid fits that eye's map, and
  comparing them gives the alignment; no separate binocular calibration there. Direct view keeps
  the ordinary thirteen-point calibration.
- **The tolerance between the eyes' grids** — "0.25°"; the console reports the mismatch at each
  point and overall.
- **Outside the tolerance** — "By session kind": a warning in training and piloting; refused in a
  recording session until the mirrors are realigned and the check passes.

**Element 9 is discussed, and with it the display engine (elements 1-9).**

## 10. Structure

Settled before the element: the PI's vocabulary of 2026-10-01 (session, task, run, block type,
block, condition, trial; the session-levels spec §2); `scheduler.py` (conditions with targets,
blocks with criteria, counting, orders, requeue) built and driven every trial; but `taskd._plan`
gives every run one block of one condition, and no task can declare a plan (XC-207).

**Batch 1** (asked 2026-10-07):

- **Where a task's plan lives** — "In the task file": beside its trial(s), one reviewable file; the
  operator chooses at run start among the plans it declares.
- **The operator's edits** — "Edit freely": at run start and during a run the operator may also add
  or remove conditions and block types, each change recorded with its actor (offered against: pick
  and adjust within declared ranges).
- **Several kinds of trial in one task** — "Yes, chosen per condition": a task declares several
  trial structures; each condition names its own; interleaving them in a block is ordinary.
- **Interludes** — "Yes": a run steps aside (a recalibration, a quick RF map, a rest) and returns to
  the same block with its counts and order; recorded as an interlude, not a new block (S8 §1).

**Batch 2** (asked 2026-10-07):

- **Edits at the rig** — "Yes, refused if not": checked exactly as the task file is (field, colors,
  ranges); an edit that fails is not applied and the console says why.
- **The continuous mode can** — all four: rewards (on a schedule, or for gaze on the screen or a
  region); probes on a schedule; gaze- or neural-contingent changes; operator marks and pauses.
- **It ends on** — all four: a declared duration; its media ending; an operator stop; a criterion.
- **Its analysis** — "One epoch with timed events": every change, probe, reward and mark
  time-stamped on the recording clock; analysis cuts it as it likes.

**Batch 3** (asked 2026-10-07):

- **Block order within a run** — all four: a fixed sequence; repeating (Bt1, Bt2, Bt1, Bt2...);
  randomized from a recorded seed, balanced; progression by criterion (training stages, shaping).
- **What ends a block** — all four: a number of trials; every condition's target met; a
  performance criterion; a time limit.
- **Across a session** — "A program, free to deviate": a session program lists the runs in order;
  the console offers the next; the operator may skip, repeat or insert runs, all recorded.
- **What ends a run** — its plan done; an operator stop; a time limit. Disengagement (e.g. N
  no-responses in a row) was offered and not chosen.

**Batch 4** (asked 2026-10-07):

- **When the animal stops working** — an alert by default, and in the PI's words "with a checkbox in
  the consle for 2. e.g., somewhere sensible there is a box that can be checked to auto-pause if
  monkey does not engage for a number of trials that is set next to the checkbox": a console
  checkbox turns on auto-pause after the number of non-engaged trials typed beside it.
- **Where session programs live** — "Per animal": each animal's folder holds its current program,
  updated as training moves on (offered against: the task library, recommended; built in the
  console).

**Element 10 is discussed.**

## 11. Variation

Settled before the element: a condition is a named set of values with a target (`scheduler.Condition`);
a block declares its order (`Shuffled`, `WithReplacement(weights)`, `Constrained(max_run, weights)`);
seeds recorded; today one condition per run; condition numbering for the recording undecided
(XC-197).

**Batch 1** (asked 2026-10-07):

- **Values that change trial to trial** — "Conditions + drawn values": named conditions for the
  design's factors (counted, balanced, numbered in the recording), plus values drawn per trial
  from declared distributions for nuisance variables (array rotation, jitter), recorded per trial
  but not conditions.
- **Factorial designs** — "Yes, with exclusions": factors and levels declared; the framework makes
  the combinations minus declared exclusions, each named from its levels; hand-listed conditions
  remain possible.
- **Orderings** — all four: shuffled passes; weighted draws (e.g. 20% catch trials); limits on
  repeats; sequence-balanced (each condition follows each other equally often, e.g. de Bruijn).
- **A live edit to a value a condition sets** — "The live edit": the operator's value overrides
  every condition's (S8 §3.4's layering) (offered against: the condition wins, recommended).
  Consequence: the record marks each trial whose condition was overridden, since its name no longer
  describes it.

**Batch 2** (asked 2026-10-07):

- **Condition numbers in the recording** (XC-197) — "Fixed per task": a condition's number stays the
  same across runs, sessions and animals while it exists; one added at the rig takes the next
  unused number; numbers never reused.
- **Distributions for drawn values** — uniform range; a weighted set; normal, truncated to the
  declared range; a prepared list; and, the PI's addition, "for e.g. timings, a nonaging
  foreperiod function" (a constant-hazard foreperiod, so elapsed time does not predict onset).
- **Repeatable runs** — "New seed, replayable": a fresh seed per run, recorded; any run replayed
  exactly from its seed.

**Element 11 is discussed.**

## 12. Adaptivity

Settled before the element: ADR-0006 puts adaptive logic between trials in ordinary Python;
`adaptive_detection.next_params` and its staircase are called by nothing (XC-242); the science
review's finding 2: it moves only on correct versus wrong target, so misses never make it easier.

**Batch 1** (asked 2026-10-07; all as recommended):

- **Methods** — all four: up-down staircases (transformed rules, fixed or shrinking steps);
  interleaved staircases; Bayesian methods (QUEST, QUEST+, Psi); training progressions (shaping).
- **Where they are written** — "Library + task code": common procedures as a reviewed library a
  task names and configures; anything new as between-trial Python in the task file (ADR-0006),
  flagged for review in the task's report.
- **What moves a staircase** — "Declared, with a default": each procedure declares it; the default
  counts correct as success, wrong target and no response as failure, and ignores aborts. (Settles
  the science review's finding 2 for the library; `adaptive_detection`'s own rule is revisited
  when the reference tasks are made right.)
- **Carrying state** — "Per animal, declared": a procedure declares whether its state carries;
  carried state is stored per animal and per task, resumed at the next run or session, and
  recorded whenever read or written.

**Batch 2** (asked 2026-10-07; all as recommended):

- **Adaptive reward** (welfare-related; goes on the welfare summary) — "Among named entries": a
  procedure may choose which of the bounded config's named reward entries a trial pays (e.g.
  `reward_streak` for a streak); every entry and ceiling still applies; each choice recorded; it
  can never set an amount.
- **A live value on a procedure-controlled parameter** — "Operator holds it": the procedure pauses
  until the operator releases it, then resumes from its own state; both recorded.
- **Training progressions** — "Both ways, by criteria": advance on one criterion, fall back on
  another, as declared.
- **What a procedure may read** — all four: outcomes and RTs; anything the trial recorded; gaze
  traces; neural features (closed-loop selection such as most-exciting images).

**Element 12 is discussed.**

## 13. Aborts and repeats

Settled before the element: the PI's ruling of 2026-08-31 (S8 §2, §8 item 3): "a fixation break is
re-queued at the end of the block; a wrong choice is not ... End of block rather than immediately,
so the animal cannot make an easy condition repeat by breaking on the hard one. Overridable per
block." The code differs (the runtime survey §5 item 1): a requeued condition goes to the end of
the current pass under `Shuffled` and is the very next trial under `WithReplacement`; and
`scheduler.REQUEUED` also repeats no-fixation, target breaks, blink breaks, tracker loss and rig
faults. What counts toward a target is declared per block (`Counting`).

**Batch 1** (asked 2026-10-07):

- **Where a repeated trial goes** — "Later, at a random point": reinserted at a random later position
  in the block, never the very next trial. **This supersedes the PI's 2026-08-31 "end of block"
  rule** (S8 §2, §8 item 3) — the anti-avoidance reasoning holds in part, since a repeat never
  comes back at once.
- **Repeated by default** — fixation breaks; no fixation; rig faults (tracker loss, a dropped
  display, hardware). Not repeated: wrong target (as ruled 2026-08-31); target breaks and blink
  breaks were not ticked. A block may override.
- **What counts toward a target** — "Responded trials": correct or wrong; aborts do not count.
- **A condition broken again and again** — "Cap per condition": after N repeats of a condition in a
  block (task-set), it stops being repeated; its shortfall recorded and shown; the console flags
  avoidance.

**Element 13 is discussed.**

## 14. Parameters and live control

Settled before the element: declared parameters with ranges and a live flag (S8 §3.1); layers
deployment → rig → subject → task → session → live edits, and live edits now over conditions
(element 11); staged and applied at a trial boundary (S8 §3.2); one validated write path, the
actor recorded; several writers with visibility instead of a lock (S9a §8).

**Batch 1** (asked 2026-10-07):

- **When a live edit takes effect** — "Next trial; 'instant' if declared": at the next trial boundary,
  except a parameter the task declares instant, which changes on the next frame, recorded with it.
- **An animal's starting values at a new session** (XC-018) — "Operator chooses each time": at session
  open the console asks whether to start from the animal's last values, the task's defaults, or a
  saved preset (offered against: the animal's last values, recommended).
- **Presets** — "Yes, per animal and task": the current values saved as a named preset for an animal
  and a task, applied with one click as one recorded change, kept in the animal's folder.
- **Edit history** — "Yes, with revert": every edit listed with who, when, old and new; any earlier
  state restored in one action, itself recorded.

**Element 14 is discussed.**

## 15. Recording and review

Settled before the element: per-trial full values, block and condition names, the ten position
numbers (`trials.jsonl`); conditions numbered fixed per task in the recording (element 11);
automatic stimulus on/off/changed codes and the screen log with live values and seeds (element 5);
ADR-0006's review artifact (diagram, code table, timeline) plus the PI's example frames per state
(element 1).

**Batch 1** (asked 2026-10-07):

- **A task's review report contains** — the state diagram and codes; example frames per state (the
  slow exact drawer, per eye on the stereoscope); the plan (block types, the factorial table with
  exclusions, orders, repeat rules, targets, adaptive procedures); a simulation census per
  condition and block; and, the PI's addition, **a timing diagram**.
- **Simulation before an animal** — "Advised, not enforced": the report shows it; nothing refuses
  (offered against: required before recording sessions, recommended).
- **The simulated animal** — in the PI's words: "yes, declared functions with some defaults. e.g.,
  perfect behavior, chance behavior, animal with incorrect strategy, normal performance (85%
  accuracy), animal trying to break task, animal trying to exploit reward schedule". Psychometric
  functions per parameter and response-time distributions, set in behavioral terms (XC-146's
  direction), with these named profiles as defaults; the last two test whether a task can be
  gamed.
- **The report's life** — "Per task version, kept": generated whenever a task file changes, kept
  beside that version, and on demand from the console; a session records its task's report
  version.

**Element 15 is discussed, and with it every element of the engine (2026-10-07).**

## How it fits (put to the PI 2026-10-07)

Three programs on the rig PC: **the display process** (Rust, Vulkan, a system service from boot;
owns the animal's screen, flips every refresh, both patches, black when idle; draws what it is
handed; reports each change's landing frame and late frames); **the rig service** (`wlx taskd`:
sessions, runs, plans, the trial loop in step with the display, welfare, the record, between-trial
procedures); **the console** (`wlx serve`). Off the rig: lab storage (media by checksum) and a GPU
server for generated images. A trial: the plan picks a condition, drawn values are sampled,
procedures adjust, layers resolve, the condition names the trial structure; frame by frame the
rig service reads gaze, runs the states, hands the display the next screen description, codes go
out at the decision, the display reports landing; at the end the outcome, the record, procedures,
repeats. Simulation and demo swap the display for a no-op or development window; the simulated
animal reads the same description. The slow exact drawer is the definition, the report's frames,
and the reconstruction of any recorded frame.

**Where the pieces meet** (asked 2026-10-07):

- **A live-driven position each frame** — "In the rig service": it reads gaze or the mouse, places the
  stimulus and hands the display the finished description; no task behavior lives in the Rust core.
- **Audiovisual timing** — "Started on the frame": the NI card starts a sound on a hardware trigger
  from the frame the visual change lands on; a task may declare an offset.
- **Demo mode's screen, when it returns** — "Real images, labeled": the browser shows frames from the
  exact drawer (lower resolution, not at display speed, uncalibrated on the viewer's screen and
  said so). Supersedes the parked demo spec's schematic.
- **A generated image not ready in time** — "Wait as long as it takes": the next trial waits; the
  welfare clocks run, the console says it is waiting, and the operator can pause or stop.

## Build order and write-up (asked 2026-10-07)

- **Order** — "Definition first, display by January": A (the screen description and the slow exact
  drawer), then B (warnings, session kinds, default colors), then C with I (trials that vary, with
  the report and simulation profiles), then E (the display process, after the Vulkan spike) in time
  for January's V1; then D, F, G, H, J, K; then the reference tasks; then demo mode. The cross-repo
  asks go out with the spec.
- **Write-up** — "Umbrella spec + per-build plans": one spec for the whole engine, for the PI's
  review; each build then gets its own plan and the usual build-review-merge cycle.

## The design reviews' questions (asked 2026-10-07)

Two reviews of the spec at `8f9cb03` (`docs/superpowers/reviews/2026-10-07-engine-science-review.md`,
15 findings; `...-engine-feasibility-review.md`, 20) found the counting and repeat rules unworkable
as written (a detection block with catch trials never ends; "not repeated" breaks are redrawn as
owed), several misleading defaults, and gaps against the code. The PI's decisions, by batch:

**Batch R1, counting and repeats:**

- **What counts toward a target where withholding is an answer** — "Every trial with an answer":
  hits, misses, correct rejections, false alarms, correct and wrong choices; only trials ending
  before the decision (breaks, no fixation, faults) do not count.
- **Breaks chosen not to repeat** — in the PI's words, "selectable by task if repeats are active":
  each task says whether such a trial is spent (counted as presented, marked an abort) or owed
  (shown again later).
- **Blocks whose order is the design** (priming, sequence-balanced) — "Declared per block": such blocks
  default to no repeats; the realized sequence, aborted predecessors included (and whether their
  display was shown), is recorded either way.
- **A repeat's drawn values** — in the PI's words, "declarable per task. it may be useful to be
  random, it may be necessary to repeat specific conditions.": fresh or the same, per task.
