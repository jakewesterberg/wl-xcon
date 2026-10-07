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
