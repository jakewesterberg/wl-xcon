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
