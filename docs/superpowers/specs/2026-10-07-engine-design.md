# The engine: what runs a task, from its plan to the animal's screen

**Status:** designed with the PI on 2026-10-07, element by element (fifteen elements, well over
a hundred questions asked in the UI); this written spec is for the PI's review, after two design
reviews (§26). Every decision below is the PI's answer as recorded, verbatim, in
[the brainstorm notes](2026-10-07-engine-brainstorm-notes.md), which this spec cites as **N§k**
(the notes' element k). Where this spec says "recommended", the PI chose the option offered as
recommended; where he chose otherwise, it says what was offered against.

It replaces nothing yet: each build (§24) gets its own plan and review. It amends other documents
as §22 lists, when the build that changes them lands.

## 1. Why

The PI asked to brainstorm "the engine for running tasks" before demo mode, the display engine
and the task runtime as one design (N, "Decided before the elements"), and then to go "far more
in-depth ... These are central to a large component of the experimental setup. So, we need to be
careful in making this flexible and effective."

What exists (the surveys `docs/research/2026-10-07-engine-display-state.md` and
`...-engine-runtime-state.md`):

- **No display code.** A throwaway glfw and moderngl spike (`tools/spike_display.py`),
  `geometry.py` (degrees to the field, not to pixels), `photometry.py` (gamut checks, no
  conversion), and `run.World.display`, which draws nothing. ADR-0002 deferred the engine to V1.
- **A trial loop that works and a planner that is starved.** `run.run_trial` runs a declarative
  trial frame by frame; `scheduler.py` has conditions, targets, orders and repeats, and runs every
  trial; but `taskd._plan` gives every run one block of one condition, so every trial of a run is
  the same trial, and no task can declare a plan (XC-207). Nothing calls a task's between-trial
  procedure (XC-242).

What the engine must serve: the PI's paradigms, in his words, are in N§1 (thirty-four named
paradigms, from RSVP and adaptation through most-exciting-image generation, gaze-contingent and
closed-loop presentation, M/P/K mapping and manual RF mapping by mouse, "and probably many more
over time!"). **The last clause is the design's first requirement**: the engine grows by
reviewed additions, never by rewrites.

## 2. Principles carried through every section

1. **Tasks are declarations, reviewed without reading drawing code** (ADR-0006). No task file
   draws; a task names blocks, values and procedures.
2. **One definition of every stimulus**: the slow exact drawer (§4.9). The GPU draws to it, the
   review report shows it, analysis rebuilds any frame from it.
3. **Nothing estimated is written as fact.** The record holds what happened and what it was
   measured against; corrections that need a measurement (scan-out, latencies) are applied in
   analysis from that measurement (CLAUDE.md: no timing claim without a measurement).
4. **Imperfect but acceptable is listed, not hidden, and never silently passed** (the PI,
   2026-10-07: a default color calibration is "a nice to have, not a need to have" for training).
   Whether an imperfection is acceptable depends on what the session is for (§19).
5. **What was shown is reconstructable**: seeds for random content, a log of every change, every
   live-driven value per frame, generated media kept (N§1 group 4, N§5).

## 3. Architecture

### 3.1 Three programs on the rig PC (N "How it fits"; N§7, N§8)

| Program | Language | Role |
|---|---|---|
| **The display process** | Rust, Vulkan | A system service from boot. Owns the animal's screen; refreshes every frame; draws the flip patch and the task patch; shows black when idle; draws exactly the screen description it is handed; reports the frame each change landed on and every late frame. Holds no task logic. |
| **The rig service** (`wlx taskd`) | Python | Sessions, runs, plans, the trial loop in step with the display, welfare, the record, between-trial procedures, the warnings list. Computes every screen description, live positions included (N "where the pieces meet"). |
| **The console** (`wlx serve`) | Python | Pages and controls, the warnings tab, the live schematic for hand mapping, frame-timing health. |

Off the rig: **lab storage** (media sets by checksum, §9.4) and **a GPU server** that makes
generated images between trials (§4.8).

**Why a separate display process** (N§7 batch 3): a driver crash cannot take the session with it
(vstimd's notes describe NVIDIA device-lost failures; `docs/research/2026-10-07-vstimd-prior-art.md`);
the background stays up while the rig service restarts; the process gets its own real-time
priority. The rig service hands it each screen description through shared memory and gets back
landing frames. Its cost, a message format and a second program, is accepted.

### 3.2 One trial, end to end

1. The plan (§13) picks a condition; drawn values (§14) are sampled; adaptive procedures (§15)
   adjust; the layers (§17) resolve to one set of values; the condition names its trial structure.
2. Frame by frame, in step with the display: the rig service reads gaze, runs the trial's states,
   applies actions, builds the next **screen description** (§3.3), and hands it to the display.
   Codes go out at the decision (§8.2). The display reports the frame each change landed on.
3. At the end: the outcome, the trial's record line and screen log (§8.5), the procedures'
   update, the repeat rules (§16).

### 3.3 The screen description

One value describes everything on the animal's screen at a moment: the setup and each eye's
background, and every visible item fully resolved to numbers (shape, fill, edge, outline,
placement per eye, layer, how it combines, contrast with its convention, opacity, its seed and the
frame it appeared on, for anything that moves or refreshes). No parameter references remain in it.
It changes only when something changes; between changes the display and the exact drawer compute
frame-dependent content (drift, motion, refreshing noise) from it and the frame number.

**Its consumers, and only these, define "what is on screen"**: the display process, the slow exact
drawer, the simulated animal, demo mode's screen, the hand-mapping schematic and, later, the live
replica. It is versioned like telemetry (a schema number checked on read).

### 3.4 Simulation and demo

The same rig service, with the display process replaced by a no-op that acknowledges frames, or
by the development window (§11.4). The simulated animal (§18.3) reads the same screen description.
Demo mode, when it returns, shows frames from the exact drawer (§23).

## 4. What can be shown (N§1)

### 4.1 The stimulus model: building blocks and reviewed extensions

"Building blocks + reviewed extensions": a stimulus is **a shape, filled with something, seen
through an edge profile, placed and layered**. Named kinds remain as shorthands (a Gabor is a
circle with a grating fill and a Gaussian edge; a plaid is two gratings combined by adding; an
array is items on a ring). A genuinely new block is added once, as reviewed framework code, and
is then usable in any combination (§4.10).

### 4.2 The first set of blocks

**Shapes**: circle and ellipse; rectangle and polygon; ring; a line or curve (a path with a width);
text; the whole screen; an image's own outline (a cut-out). **Every shape may have an outline**
(width and color) separate from its fill ("Yes, on any shape").

**Fills**: flat color; grating; checkerboard; noise; sparse noise; moving dots; random-dot
stereogram; texture field; Mondrian; image; movie.

**Edges**: hard; Gaussian; raised cosine (a ramp of a given width).

**On every stimulus**: position, orientation, size, eye, disparity, layer, contrast, opacity.

### 4.3 What each fill must do (N§1 batches 2, 5, 6)

| Fill | Must support |
|---|---|
| Grating | sine, square, triangle and sawtooth waveforms; drift and counterphase (§6.4) |
| Noise | white, binary, pink (1/f), band-pass (frequency and orientation), **color noise** |
| RF mapping | sparse noise; dense noise or m-sequence; flashed and swept bars; subspace (Ringach/Hartley) gratings |
| Moving dots | coherence, direction, speed, lifetime, size, density, aperture; **the noise dots' rule declared per task** (re-plotted positions, a random direction per dot, a random walk), since each changes what a coherence level means |
| Texture field | a figure defined against its ground by orientation, motion, color or disparity |
| Mondrian | colored rectangles, grayscale rectangles, mixed shapes, image fragments |
| Masks (composed) | noise masks, pattern masks, metacontrast, object substitution (four dots outlasting the target), **a full-screen mask**; any that blocks cannot compose becomes an extension |

**Random content** comes from a seed in the record and is rebuilt exactly by the exact drawer; a
task may ask for the frames it showed to be saved too ("Seed, frames on request").

### 4.4 Combining, grouping and layouts

- **Four ways to overlap**, all required: front covers back (opaque or partly see-through by an
  opacity); contrasts add (plaids, a signal in noise, transparent motion); a window or scotoma (a
  stimulus reveals or hides others only inside its area); one shapes another (multiplication, e.g.
  a contrast envelope).
- **The background is the bottom layer** ("Yes, as the bottom layer"), changeable during a trial;
  on the stereoscope **each eye may have its own background** ("Yes").
- **Groups** ("Yes"): a named group shows, hides, moves and changes a shared property as one; its
  members stay addressable.
- **Search and free-viewing layouts**: a ring (as `Array` today); a grid; listed positions;
  positions drawn between trials from a seed with spacing rules; several rings or clusters. **Each
  item is its own stimulus** ("Each item its own stimulus"): target and distractor are roles, not
  appearances.
- **The busiest display is thousands of elements** (dense line-element textures, large dot fields,
  many-item free viewing); the GPU drawer batches them (§10).

### 4.5 Text and curves

- **Text**: letters, digits and symbols, from one or a few bundled fonts, glyph height in degrees,
  rendered to exact pixels ("Letters, digits, symbols"). Bundled fonts enter ADR-0004's inventory.
- **Curves** (curve tracing): written in the task as fixed paths, or generated between trials from
  a seed by a reviewed procedure (lengths, crossings, distances to distractor curves), saved in the
  record ("Both").

### 4.6 Images and movies

- **A photograph's colors**: the file is read as standard sRGB and converted through the rig's
  calibration, measured or default, so a photo looks the same on any calibrated rig; the record
  names the calibration ("As the photo intends").
- **Size**: declared per stimulus, either degrees (resampled with a stated filter) or pixel for
  pixel ("Declared per stimulus").
- **Matching a set** (mean luminance, RMS contrast, optionally the amplitude spectrum): a declared
  preparation step when a task asks, recorded with the set ("When a task asks").
- **Formats**: any common format; a lossy one (JPEG) carries a warning ("Any common format").
- **Movies**: each movie frame held a whole number of refreshes; a rate that does not divide the
  display rate (25 fps at 240 Hz) is refused until re-timed beforehand ("Whole refreshes only").
  Decoded into memory beforehand or streamed by a decoder thread that stays ahead, declared per
  movie; a streamed frame that misses is recorded late (N§6).
- **Soundtracks** play with the picture when the task asks (§9.1).

### 4.7 Image procedures between trials

Scrambling, filtering, cropping and recoloring run **between trials**: a reviewed procedure, with
its seed, makes the image before the trial that shows it; the result is uploaded and kept in the
record; nothing is computed inside a frame ("Between trials").

### 4.8 Generated images

Most-exciting images and other closed-loop stimuli are made **on another machine**, a GPU server on
the lab network, between trials; the rig checks, records and shows each one, and its own GPU stays
the display's ("Another machine"). **If the next image is not ready in time, the next trial waits
as long as it takes** (N "where the pieces meet"): the welfare clocks keep running, the console
says what it is waiting for, and the operator can pause or stop. Every generated image is kept in
the session's record. The protocol between the rig and the generator is designed in build H.

### 4.9 The slow exact drawer

Plain Python (numpy) that turns a screen description, an eye, the setup's pixel geometry and a
calibration into the image that eye must see, as output levels. It is **the definition of every
block**: the GPU drawer matches it (§10.1); the review report's frames come from it (§18); analysis
rebuilds any recorded frame from it and the record (§8.5); demo mode shows its frames (§23). It
never runs inside a frame.

### 4.10 Adding a block (reviewed extensions)

A new shape, fill or edge arrives as: its exact definition (in the exact drawer), its GPU version,
the match tests between them (§10.1), its load-time checks (what makes its parameters valid), and
**a simple, person-readable report with example frames** (the PI's words, N§1 batch 7). **A lab
member reviews it** before tasks may use it: the definition and the report, not the GPU code
(§10.3). Claude may write a block; Claude does not approve one.

### 4.11 Live-driven stimuli and the record

A stimulus's position may be measured from the screen's center, **another stimulus**, **where the
eye is now**, or **a live input** (the operator's mouse, a joystick, a neural signal) (N§1 batch
1). **Any numeric property** may be driven live (position, orientation, size, contrast, color,
speed: e.g. the mouse moves a bar and its scroll wheel turns it, in manual RF mapping). Every live
value is recorded frame by frame (§8.5): such stimuli break S4 §5's "position is a pure function of
parameters, seed and frame", and the record is what makes them reconstructable.

### 4.12 Contrast

**Always written explicitly** with its convention (e.g. `contrast=Weber(0.3)`, Michelson, RMS);
nothing is implied. A convention defined against the background (Weber) needs a declared
background on black (§7.5).

## 5. Where (N§2)

1. **Coordinates**: cyclopean degrees; **(0°, 0°) is straight ahead**, the rig file recording where
   that falls on the screen (default its center). **Math convention** for every angle: 0° points
   right, counter-clockwise positive, +y up; a bar's orientation 0° is horizontal; a grating's
   orientation names its bars and its drift direction is a separate angle.
2. **Sizes**: one size number is the **full width** (diameter, side, bar length); each block's
   definition states it.
3. **Away from the center**: a task declares **true visual angle** (every stimulus subtends its
   declared degrees wherever it sits; a grating keeps its cycles per degree) or **the screen
   center's scale**; **the default is true visual angle**. (At 30° in direct view a degree covers
   15-33% more screen than at the center.)
4. **Disparity**: in degrees, **near negative**, far positive. **A stimulus may sit at a different
   position in each eye** ("Free per-eye positions"; rivalry in non-corresponding places, nonius,
   fusion tests); disparity stays the shorthand for the common case.
5. **Linked positions**: a link to another stimulus is declared per link, either moving with it or
   placed once at onset.
6. **Gaze-anchored stimuli**: the gaze rule is selectable per stimulus (the newest sample, a
   smoothed one, or one predicted to the frame's appearance; **default the newest**), each frame's
   sample age recorded. When gaze is lost, and whether to move during a saccade or only after
   landing, are declared per task.
7. **Gaze windows may be any shape**: circles, ellipses, rectangles, polygons, or a stimulus's own
   outline grown by a margin.
8. **Off the field**: a stimulus may extend past the field's edge only when the task declares it (a
   sweep entering from off-screen, a scene cropped by the mask); otherwise refused at load, as
   today. Check 8 grows to test extents, not only centers (XC-143, XC-144).
9. **Head-free chaired sessions** use the nominal head position for degrees and windows; the record
   and the warnings list say the head was free; a task may require a fixed head and is then refused
   in chaired sessions.
10. **Manual RF mapping's view** is a live schematic in the console: the fixation point, the
    stimulus, the gaze dot and markers the operator drops, before any full replica (V11).

## 6. When (N§3)

1. **Times are in seconds; tasks run at any refresh rate** (240 or 120 Hz), converted to frames at
   the session's rate; a task may declare a required rate.
2. **Durations that are not whole frames** round to the nearest frame and are recorded as shown; a
   task may mark a duration **exact**, and an exact one that does not fit whole frames at the
   session's rate is refused at load.
3. **A dropped or late frame** never stops a trial: the trial continues and the record marks it
   ("Always continue, mark").
4. **Temporal modulation**: sine modulation at any frequency, sampled per frame and recorded;
   square-wave flicker needs whole frames per half-cycle or is refused.
5. **Onset** is recorded as the frame's start and the stimulus's vertical position. The screen
   scans top to bottom, up to one frame period: an OLED removes slow pixel response, not the scan
   (Blur Busters, read 2026-10-07; UNVERIFIED for the PG27UCDM). Both setups put the light sensors
   at the **bottom**, near the end of the scan, so V1 places test patches top and bottom to measure
   the delay, and analysis applies it by height.
6. **Sequences** (RSVP, predictive sequences, masking streams): either a sequence stimulus (items and
   timing in one declaration, or drawn per trial from a seed, with events such as "item 7 shown"),
   or one state per item, as the task prefers.
7. **Motion paths**: straight sweeps; pursuit targets (step-ramp, sinusoidal, circular, Lissajous);
   waypoint paths; seeded random walks.
8. **The longest trial is 5 minutes**; a trial still running then ends as a fault. Longer
   presentations use **the continuous mode** (§13.6).
9. **Between trials**, the screen shows what the task declares (the background by default; a task
   may keep stimuli up across trials or show an ITI display of its own).
10. **Gaze- and neural-contingent changes** record their delay (sample age plus landing frame); a
    task may declare a maximum, and trials past it are marked. V3's photodiode measurement gives
    the true end-to-end figure.

## 7. Color and luminance (N§4)

1. **The default calibration is standard sRGB**: the panel set to its sRGB mode and the published
   standard (primaries, D65 white, transfer curve) used when the rig file names no measured
   calibration. How closely the panel's sRGB mode follows the standard is UNVERIFIED until
   measured; the warnings list says so.
2. **Isoluminance needs a measured calibration** with a stated observer, in every session kind
   ("No" to isoluminance on the default). `visual_search` keeps its isoluminant colors and waits for
   a measurement; **a plain-color training variant** loads on the default, with the warning.
3. **Color noise and colored Mondrians** are allowed on the default, with the warning, in whatever
   session kinds §19 accepts.
4. **Output is 10-bit** (1024 levels per channel), verified at V1 that the card, cable and panel
   carry it at 4K/240 (UNVERIFIED for this pairing); dithering is the fallback where they do not.
5. **The default background is black.** A task using DKL colors or Weber contrast, both defined
   against the background, must declare its own non-black background or is refused at load.
6. **The transfer is a measured table** per channel (the default uses the sRGB curve). **One
   calibration for the whole panel** ("One for the panel"): the stereoscope's halves are assumed
   equal, which changes S4 §9's plan of one per half.
7. **The panel's brightness limiter (ABL)**: overall brightness is capped so it never engages, at a
   level V9 measures; a display that would exceed the cap is refused at load; the record states the
   cap.
8. **Cone fundamentals** are named in each calibration (a human standard such as Stockman & Sharpe's
   2°, or macaque estimates once a source is chosen and cited); the default uses the human standard
   and says so.
9. **A calibration never expires** but carries its age; **past 30 days it is a warning**.

## 8. Sync and evidence (N§5)

1. **The flip patch** alternates every refresh, unconditionally (S4 §7). **The task patch toggles on
   every screen change** ("Every change"); the record's frame numbers say which change each edge
   was.
2. **Event codes go out at the decision**, as now; the light sensor gives the exact time; codes
   never wait on the display.
3. **Automatic codes**: the framework strobes **"stimulus on"**, **"stimulus off"** and **"stimulus
   changed"** for every stimulus, each followed by the stimulus's number within its trial; a group
   is one code with the group's number, its members listed in the record. Three new framework escape
   codes, asked of wl-preproc, which owns the vocabulary (ADR-0007; §21).
4. **Frames are matched to the recording** by counting flip-patch edges from each trial's start
   code, checked against the trial's known length.
5. **The screen log**: every onset, offset and update with its frame and full resolved description;
   every live-driven value per frame; seeds for every random pattern; the display's landing frames
   and late frames. Any frame is rebuildable by the exact drawer.
6. **The console shows frame timing per trial** (late frames, a running count, a warning past a
   rig-set rate), at trial boundaries.
7. **A frame-clock fault** (the sensor stops, or disagrees with the display's count): a console
   warning and a warnings-list entry, affected trials marked, the session goes on.

## 9. Media and sound (N§6)

1. **Sounds play through the NI card's analog outputs**, sample-accurate on the recording's clock,
   to **two speakers, left and right** (two analog outputs: part of S6's I/O allocation; the card is
   the PI's purchase). **A sound that goes with a visual event starts on a hardware trigger from the
   frame the visual change lands on**; a task may declare an offset (N "where the pieces meet").
2. **Simple sounds are made from parameters** (a tone's frequency, duration, level and ramp; a
   click's width; a noise burst's band and seed), rebuilt from the record; files remain for recorded
   sounds.
3. **Movie soundtracks** play when a task asks, kept in step with the frames.
4. **Media live on lab storage**, each set with a manifest of checksums; a task names a set and a
   version; the rig keeps a local copy, checks every checksum before a session, and records the
   set's identity (XC-027).
5. **Media load per run**: everything a run can show is loaded before it starts; a run whose sets do
   not fit is refused at its start, with the numbers.

## 10. The drawer (N§7)

1. **The GPU drawer matches the exact definition within one output level** per pixel (of 1024), on
   reference scenes for every block and in combinations.
2. **Edges are smooth and sub-pixel** (anti-aliased by coverage), so stimuli sit and move in
   fractions of a pixel.
3. **A pattern near the pixel limit** (about 28-31 cycles/degree at the center in direct view) is
   allowed with a warning naming it.
4. **The core is Rust**, a separate process (§3.1), reached through shared memory. **Tests carry its
   review**: a person reviews the Python definitions and the visual report; the core is held to them
   by the match tests and V1; no core change merges without them passing.
5. **Graphics interface**: the PI asked to spike Vulkan ("it seems like a better long-term option").
   Vulkan offers direct-to-display (`VK_KHR_display`, no compositor in the path) and presentation
   timing (`VK_EXT_present_timing`; reported supported by NVIDIA's Linux driver, UNVERIFIED for the
   RTX 5070 Ti). **The spike** (build S, §24): a Gabor, both patches and two eye viewports drawn by a
   Rust core through Vulkan, offscreen output compared with the exact drawer, the code it took, and
   NVIDIA's documented support checked; **timing waits for Linux and an NVIDIA card**: the PI's
   machine, over SSH, once it is switched on. On a Mac, Vulkan runs through MoltenVK onto Metal and
   says nothing about timing (P4a).
6. **Prior art**: vstimd (Rust, Vulkan, direct display) is AGPL-3.0-only; **no code is reused**,
   only ideas (direct display, a post-flip vblank wait, landing-frame reports, a renderer-owned
   patch, a no-op renderer for CI).
7. **ADR-0002**: the PI chose to build our own drawer now so V1 can compare it with PsychoPy on day
   one; the choice of engine stays V1's. A PsychoPy adapter, if ever chosen, lives in a separate
   GPL-3 package (ADR-0004).

## 11. Lifecycle (N§8)

1. **The display process starts at boot** as a system service, restarts itself if it dies, and owns
   the screen from power-on; the rig service connects to it.
2. **Black when no session runs**; a session's background appears when it opens.
3. **If the display process dies during a trial**: the trial ends as a rig fault, the display
   restarts, and the session **pauses** at that boundary until the operator resumes.
4. **A windowed display** is labeled "development: not timing-valid" and serves simulations, demo
   mode and tests only; a real animal's session needs the rig's panel in exclusive full-screen mode.
5. **The pause screen is declared per task, black by default** (changes V12 item 3's plan of the
   background). The flip patch still alternates.
6. **The screen and its mode are checked** against the rig file (panel identity, resolution, refresh,
   bit depth): a mismatch is a warning.
7. **After a change to the display software or graphics driver**, the warnings list says the timing
   record is older than the change until a V1 matching the current setup exists (core version,
   driver, kernel, mode).
8. **The OLED's own maintenance cycle** is scheduled outside sessions and recorded if the panel lets
   software trigger it; otherwise a session refuses to open while the panel says maintenance is due.
   Whether the PG27UCDM allows either is UNVERIFIED (S0 §5.1).

## 12. Calibration procedures and test screens (N§9)

1. **The color instrument is a spectroradiometer** (full spectra: luminance and cone contrasts for
   any observer, macaque included; XC-002's fork). Buying it stays the PI's.
2. **Color calibration is automated from the console**: with the instrument at the eye point, the
   rig shows the patches, reads the instrument, fits the table, and writes a dated record.
3. **The eye tracker's calibration is required at every session start**, as S5 §7 planned: the
   thirteen-target constellation before any task; no first task without a validated map; calibration
   epochs inside tasks keep tracking drift. (S5's "planned by wl.works" was retired 2026-10-01; this
   is now the rig's rule.)
4. **On the stereoscope, the calibration is two monocular grids**, the PI's method: the
   thirteen-point grid shown to each eye in turn; each eye's map fitted from its own grid; comparing
   the two gives the alignment. **Tolerance 0.25°**, the mismatch reported per point and overall;
   outside it, a warning in training and piloting, refused in a recording session until realigned.
5. **Before every session**: a quick frame-timing check (ten seconds of flips timed by the sensor; a
   warning past a rig-set late-frame rate) and the light-sensor test.
6. **Calibration and timing records are committed per rig** under `docs/measurements/<rig>/`, each
   with an id; the rig file names the calibration in force; every session records it.

## 13. Structure (N§10)

1. **A task's plan lives in its task file**, beside its trial structures; the operator chooses at run
   start among the plans it declares.
2. **The operator may edit freely** at run start and during a run, adding or removing conditions and
   block types, each change recorded with its actor; **every edit passes the same checks as a task
   file** (field, colors, ranges) and is refused if it fails.
3. **A task may declare several trial structures**, each condition naming its own (memory-guided and
   visually-guided saccades interleaved; catch trials with no target).
4. **Interludes**: a run steps aside (a recalibration, a quick RF map, a rest) and returns to the
   same block with its counts and order; recorded as an interlude, not a new block (S8 §1).
5. **Blocks**: block types follow one another in a fixed sequence, repeating, randomized and balanced
   from a recorded seed, or by progression on a criterion. A block ends on a number of trials, every
   condition's target met, a performance criterion, or a time limit.
6. **The continuous mode** (a 20-minute movie with free viewing, long adaptation with probes): its own
   trial-less mode. It can reward (on a schedule, or for gaze), insert probes on a schedule, change
   contingent on gaze or neural data, and take marks and pauses; it ends on a declared duration, its
   media ending, an operator stop or a criterion; it is analyzed as **one epoch with timed events**.
   Its record shape is designed in build K and asked of wl-preproc.
7. **A session program** lists the runs in order; the console offers the next; the operator may skip,
   repeat or insert, all recorded. **Each animal's folder holds its current program**, updated as
   training moves on.
8. **A run ends** when its plan is done, on an operator stop, or at a time limit.
9. **When the animal stops working**: an alert at a task- or rig-set threshold; and a console
   checkbox, with the number of non-engaged trials typed beside it, turns on auto-pause (the PI's
   words, N§10 batch 4).

## 14. Variation (N§11)

1. **Named conditions plus drawn values**: conditions are the design (counted, balanced, numbered in
   the recording); values drawn per trial from declared distributions cover nuisance variables
   (rotation, jitter), recorded per trial.
2. **Factorial designs**: factors and levels declared; the combinations made by the framework, minus
   declared exclusions, each named from its levels; hand-listed conditions remain possible.
3. **Orderings**: shuffled passes; weighted draws (e.g. 20% catch trials); limits on repeats;
   sequence-balanced (each condition follows each other equally often, e.g. de Bruijn).
4. **Distributions**: uniform; a weighted set; normal, truncated to the declared range; a prepared
   list; **a non-aging foreperiod** (constant hazard, so elapsed time does not predict onset).
5. **Condition numbers are fixed per task** (XC-197): a condition keeps its number across runs,
   sessions and animals; one added at the rig takes the next unused number; numbers are never reused.
6. **Seeds**: a fresh seed per run, recorded; any run replayable exactly from its seed.
7. **A live edit to a value a condition sets wins** (S8 §3.4's layering; offered against: the
   condition wins). The record marks every trial whose condition was overridden, since its name no
   longer describes it, and the console shows which conditions an edit overrides.

## 15. Adaptivity (N§12)

1. **Methods**: up-down staircases (transformed rules, fixed or shrinking steps); interleaved
   staircases; Bayesian methods (QUEST, QUEST+, Psi); training progressions (shaping), which may
   **step back** on a criterion as well as advance.
2. **Written as a reviewed library** a task names and configures, **plus task code** (between-trial
   Python in the task file, ADR-0006) for anything new, flagged for review in the task's report.
3. **What moves a staircase is declared per procedure**; the default counts correct as success,
   wrong target and no response as failure, and ignores aborts. (`adaptive_detection`'s own rule is
   revisited when the reference tasks are made right, with the PI.)
4. **State carries per animal when the procedure declares it**, stored per animal and task, resumed
   at the next run or session, recorded whenever read or written.
5. **What a procedure may read**: outcomes and reaction times; anything the trial recorded; gaze
   traces; neural features.
6. **A live value on a procedure-controlled parameter**: the operator's value holds and the procedure
   pauses until released, then resumes from its own state; both recorded.
7. **Reward** (welfare, §20): a procedure may choose **which of the bounded config's named reward
   entries** a trial pays (e.g. `reward_streak`); every entry and ceiling still applies; each choice
   recorded; it can never set an amount.

## 16. Aborts and repeats (N§13)

1. **A repeated trial goes back in at a random later point in its block, never the very next trial.**
   This supersedes the PI's 2026-08-31 rule ("re-queued at the end of the block"; S8 §2, §8 item 3).
2. **Repeated by default**: fixation breaks (`FIXATION_BREAK`), no fixation (`NO_FIXATION`), rig
   faults (`TRACKER_LOST`, `FAULT`). Not repeated by default: wrong targets (as ruled 2026-08-31),
   and the other breaks (`TARGET_BREAK`, `CATCH_BREAK`, `MOTION_BREAK`, `BLINK_BREAK`), which were not
   ticked. A block may override.
3. **What counts toward a target**: responded trials, correct or wrong; aborts do not count.
4. **A cap per condition**: after N repeats of a condition in a block (task-set), it stops being
   repeated; its shortfall recorded and shown; the console flags avoidance.

## 17. Parameters and live control (N§14)

1. **Layers**: deployment → rig → subject → task → session → live edits, all under the bounded
   config's ceilings (S8 §3.4), with live edits over conditions (§14.7) and operator holds over
   procedures (§15.6).
2. **A live edit takes effect at the next trial boundary**, except a parameter the task declares
   **instant**, which changes on the next frame and is recorded with it.
3. **At session open, the operator chooses** where an animal's values start: its last values, the
   task's defaults, or a saved preset (XC-018).
4. **Presets** per animal and task: the current values saved by name, applied with one click as one
   recorded change, kept in the animal's folder.
5. **An edit history with revert**: every edit with who, when, old and new; any earlier state restored
   in one action, itself recorded.

## 18. Recording and review (N§15)

1. **A task's review report** contains: the state diagram and codes; example frames per state (the
   exact drawer, per eye on the stereoscope); the plan (block types, the factorial table with
   exclusions, orders, repeat rules, targets, procedures); a simulation census per condition and
   block; **a timing diagram**. It is generated whenever a task file changes, kept beside that
   version, and on demand from the console; a session records its task's report version.
2. **Simulation is advised, not enforced**: the report shows it; nothing refuses.
3. **The simulated animal** behaves by declared functions (psychometric functions per parameter,
   response-time distributions, in behavioral terms; XC-146's direction), with **named default
   profiles**: perfect behavior, chance behavior, an incorrect strategy, normal performance (85%
   correct), an animal trying to break the task, an animal trying to exploit the reward schedule.
   The last two test whether a task can be gamed.

## 19. Warnings, and what a session is for

1. **Sessions declare what they are for**: training, piloting or recording, chosen at session open
   and recorded (N§4 batch 3).
2. **The warnings list** gathers every imperfection the session runs with: the default calibration,
   a calibration past 30 days, a lossy image, a pattern near the pixel limit, a screen or mode
   mismatch, a timing record older than a graphics change, a head-free session, a stereoscope
   alignment outside tolerance in a non-recording session, frame-clock faults, and today's
   pre-flight unknowns (pump calibration, eye tracker health). Each warning states the session kinds
   it is acceptable in; outside them it is a refusal.
3. **Accepted once per session**: listed in a console tab, written to the record, acknowledged once
   when the session opens; a warning appearing later asks again. Today's unknowns keep the PI's
   2026-09-19 rule: proceed on a recorded acknowledgment.

## 20. Welfare

Welfare-critical code is on architecture.md's list, which the PI keeps unchanged unless he widens it.
This design touches behavior there in these places, each for the PI's numbered welfare summary
before its build merges:

1. **Adaptive procedures choosing among named reward entries** (§15.7): bounded entries and
   ceilings unchanged; choices recorded; never an amount.
2. **Auto-pause on disengagement** (§13.9) and **a display crash pausing the session** (§11.3).
3. **A generated image waited for as long as it takes** (§4.8), with the welfare clocks running.
4. **The parked demo mode's items**, when it returns (its spec §8, §14).

## 21. Asks of other repositories (sent once this spec is approved)

- **wl-preproc**: three framework escape codes ("stimulus on", "stimulus off", "stimulus changed",
  each with a stimulus number; §8.3); condition numbering for `CONDITION` (XC-197, §14.5); the
  continuous mode's record shape (§13.6); the session kind in the record (§19).
- **wl-sync**: two analog outputs for stereo sound and the frame-triggered audio start (§9.1); the
  top-and-bottom test patches for V1's scan-out measurement (§6.5).
- **wl-xtasks**: the task file format with plans, trial structures and procedures (§13, §14, §15).

## 22. Amendments to other documents (each with the build that changes it)

- **ADR-0002**: our drawer built now as a Rust display process (Vulkan, via the spike); V1 still
  chooses; PsychoPy compared on day one.
- **ADR-0004**: Rust crates and bundled fonts enter the inventory with licenses verified at their
  sources.
- **S4**: §2 and §7 to the conventions above; §9 to one calibration per panel; §10's alignment target
  to the monocular grids; §5's "pure function" with live-driven and generated exceptions recorded.
- **S5 §7**: the session-start calibration is the rig's rule; the stereoscope's is the monocular
  grids.
- **S8 §2, §8 item 3**: repeats at a random later point.
- **validation.md V1** (top and bottom patches; the 10-bit path), **V12 item 3** (black pause).
- **architecture.md**: the display process, the screen description, the warnings list.
- **The demo-mode spec**: real images from the exact drawer (§23).

## 23. Demo mode

Parked (XC-013). When it returns, its screen shows frames from the exact drawer, labeled (lower
resolution, not at display speed, uncalibrated on the viewer's screen), instead of a schematic (N
"where the pieces meet"). Its spec's §14 list still applies.

## 24. Builds, in order

The PI's order (N "Build order"): **definition first, display by January**.

| Build | Scope | Needs |
|---|---|---|
| **S** | The Vulkan spike: a Rust core drawing a Gabor, both patches and two viewports; offscreen match against the exact drawer's Gabor; code size; NVIDIA's documented support. Timing on the PI's Linux machine when it is on. | A (the Gabor's definition) |
| **A** | The screen description and the slow exact drawer: every block of §4.2-4.3, combination modes, groups, placement and per-eye positions (§5), the color pipeline (§7), contrast conventions; its tests; the review report's frames. | — |
| **B** | Warnings and session kinds (§19), the default calibration and calibration records (§7, §12.6), the `visual_search` plain-color variant. | A |
| **C + I** | Trials that vary (§13, §14, §16, §17) with condition numbers, session programs, presets, history, the disengagement alert; the review report and the simulated animal's profiles (§18). | A |
| **E** | The display process (§3.1, §8, §10, §11): shared-memory protocol, lockstep, patches, 10-bit, the lookup table, landing reports, the no-op and development drawers. Ready for January's V1. | S, A |
| **D** | The adaptive library (§15). | C |
| **F** | Recording: automatic codes, the screen log, landing frames, onset height (§8). | E; wl-preproc's codes |
| **G** | Media and sound (§4.6, §9). | E |
| **H** | Live control: gaze-anchored and mouse-driven stimuli, the hand-mapping schematic, neural inputs, generated images (§4.8, §4.11, §5). | E, C |
| **J** | Calibration procedures (§12). | E; the instrument |
| **K** | The continuous mode (§13.6). | E, F |
| — | Then the reference tasks made right (with the PI's decisions), then demo mode (§23). | |

## 25. Not decided here, and why

- **What the PI decides when the reference tasks are made right**: `adaptive_detection`'s staircase
  rule and catch trials; `visual_search`'s `item_window` range; `calibration`'s `cal_hold` (the
  demo-mode science review's findings 2, 3, 9).
- **The generator protocol** (build H), **the display's shared-memory format** (build E), **the
  continuous mode's record** (build K): designed in their builds, against this spec.
- **Every UNVERIFIED hardware fact** (the panel's scan-out and sRGB mode, the 10-bit path, the ABL
  level, OLED maintenance control, NVIDIA's present timing on this card): measured at V1, V9 or the
  spike, not assumed.

## 26. Review before the PI reads this

Two design reviews, as for demo mode: a science review (where would a person running these
paradigms be misled or blocked) and a feasibility review (where this spec is false about the code,
contradicts itself, or cannot be built as written). Their findings are fixed here or put to the PI
before he reviews the spec.
