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
