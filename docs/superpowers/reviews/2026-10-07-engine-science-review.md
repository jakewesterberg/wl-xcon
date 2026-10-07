# Engine spec: science review

> **What this is.** A design review of `../specs/2026-10-07-engine-design.md` at `8f9cb03`, written on 2026-10-07 by a reviewer subagent the build session dispatched, kept as written. Its findings are being put to the PI (his decisions) or fixed in the spec (the rest); the notes record which.

- **Spec under review:** `docs/superpowers/specs/2026-10-07-engine-design.md` (commit 8f9cb03, worktree
  `b2b-remote-signin`), with its brainstorm notes (cited N§k).
- **The question:** for each of the PI's paradigms (N§1), can it be built and run correctly on this
  engine as specified, and where would the engine mislead an experimenter or produce data that is
  subtly wrong?
- **Read:** the spec; the notes; S4; S5 §2-§7; S8 §2-§3; S0 §5.3-§5.4; `run.py`, `scheduler.py`,
  `photometry.py`, `geometry.py`, `task.py` (Outcome, Family, Stimulus, appearances), and the
  `simulate.py` header. Claims about code were checked by reading it, and two were also checked by
  running it (marked "ran").
- **Ground rules:** no welfare-policy questions. No features beyond what keeps a listed paradigm from
  being blocked or misread. Literature is cited approximately. Anything not checked against a primary
  source is marked UNVERIFIED.

## Summary

| # | Finding | Paradigms most affected | Severity | Who decides |
|---|---|---|---|---|
| 1 | Misses and correct rejections never count toward a target, so a detection block with catch trials never ends | detection, catch-trial designs, constant stimuli | blocks a paradigm | PI, then spec |
| 2 | Repeats "at a random later point" are undefined for most block types, impossible at a block's end, and break sequence designs | priming, search, sequence-balanced orders, staircases | misleading | PI, then spec |
| 3 | Rounding to the nearest frame silently merges or unevenly spaces timing levels, and the loop actually rounds up | masking, RSVP, duration staircases, foreperiods | misleading | spec, plus one PI question |
| 4 | On the black default, a patterned stimulus has no defined mean luminance and an edge has no defined meaning | tuning, RF mapping, Gabor tasks, M/P/K | misleading | spec, plus one PI question |
| 5 | An overridden trial still counts toward its condition and still carries the condition's number in the recording | every factorial or tuning design | misleading | PI |
| 6 | The default calibration has no stated session kinds, and isoluminance against a standard observer is not isoluminance for the animal | color tuning, M/P/K, contrast response, `visual_search` | misleading | PI |
| 7 | DKL units are undefined, the existing gamut test is wrong for DKL, and there is no cone-contrast space | color tuning, M/P/K, photographs, MEI | misleading | spec, plus one PI question |
| 8 | "Every change" toggles the patch and strobes a code, which is undefined for live-driven and per-frame content | manual RF mapping, gaze-contingent, arrays, RSVP | misleading | spec, plus one PI question |
| 9 | Reverse correlation needs a defined random generator and a defined rule for late frames | sparse, dense and m-sequence noise | misleading | spec |
| 10 | One calibration for both stereoscope halves leaves the balance between the eyes unmeasured | rivalry, CFS, monocular vs. binocular | misleading | PI |
| 11 | The two-grid alignment check is either empty or confounded with phoria, and disparity's sign is not pinned | everything on the stereoscope | misleading | PI, then spec |
| 12 | Recorded delays and onsets leave out the tracker's latency, the scan to the stimulus's row, and the panel's latency | gaze- and saccade-contingent, full-screen flash, audiovisual | misleading | spec |
| 13 | The continuous mode counts flip edges across 288,000 frames with no re-anchoring | 20-minute movies, long adaptation | misleading | spec (build K) |
| 14 | Pauses, interludes, restarts and generator waits break adaptation and the inter-trial interval without a trace | adaptation and top-up, MEI, any task with a gray background | misleading | PI, then spec |
| 15 | The mode check drops S4 §9's care features and VRR | every paradigm, mostly long static displays | misleading | spec |

---

## 1. Misses and correct rejections never count toward a target, so a detection block with catch trials never ends

**Paradigms:** visual detection; any design with catch trials (rule-based cue tasks with catch trials,
masking detection, breaking-CFS detection); go/no-go; method of constant stimuli near threshold.

**Scenario.** §16.3 counts "responded trials, correct or wrong; aborts do not count". That is today's
`Counting.RESPONDED` (`scheduler.py:35-44`): CORRECT, WRONG_TARGET, and their early and late
variants. It leaves out NO_RESPONSE (the miss on a signal trial), CORRECT_REJECT and FALSE_ALARM, the
outcomes d′ is computed from.

Take a yes/no detection block with a `catch` condition (target 20) and five contrast levels. Catch
trials end CORRECT_REJECT or FALSE_ALARM, and neither counts. The catch condition therefore stays
owed, `_refill` (`scheduler.py:190`) re-queues every owed condition on every pass, and the block never
ends. I ran this: a block of `signal` (target 2) and `catch` (target 1), with misses on signal trials
and correct rejections on catch trials, was still unfinished after 12 trials and had paid nothing.

Without catch trials the block does end, but the design changes without any sign of it:

- Only hits pay, so a level detected 30% of the time runs about 3.3 times its target.
- "Twenty presentations per level" becomes "twenty hits per level".
- Block length balloons at low contrast, so fatigue and satiety covary with stimulus level.
- The console's "achieved against target" counts hits.

The two defaults also disagree with each other. §15.3 makes "no response" a staircase *failure* (a
datum), while §16.3 makes it count for nothing. `task.Family`'s docstring (`task.py:18-29`) says where
no_response falls "is open" and is the PI's to define. The spec has now defined it twice, in two
different ways.

**Severity:** blocks detection with catch trials when the default is used; misleading for detection
without them. **Type:** PI decision, then a spec correction.

**Question for the PI:** "In a trial structure where withholding is a valid answer (detection, catch
trials, go/no-go), does a miss (no response on a signal trial), a correct rejection or a false alarm
count toward the condition's target?" Recommended: yes, because they are the data.

**Spec change:** counting follows the answers the trial structure declares, and §15.3 and §16.3 read
from one table that classifies every `Outcome`.

## 2. Repeats "at a random later point" are undefined for most block types, impossible at a block's end, and break sequence designs

**Paradigms:** priming blocked tasks (priming of pop-out), search arrays and free-viewing search,
predictive-processing sequences that run across trials, any sequence-balanced (de Bruijn) order, and
adaptive procedures.

**Scenarios.**

- **(a) Priming of pop-out.** In priming of pop-out (Maljkovic & Nakayama 1994, Mem Cognit; Bichot &
  Schall 2002, J Neurosci) the order of trials *is* the manipulation. Suppose trial *n* ends in a
  fixation break after the array appears. Trial *n+1*'s real predecessor is then an aborted trial
  whose array the animal saw. That array may prime the next trial; whether it does is an empirical
  question, and analysis needs the record to answer it. The repeat lands at a random position, so a
  block built as repeat-runs of a given length, or as a de Bruijn sequence (§14.3), no longer has the
  transitions it was designed with. Any "repeat/switch" label computed when the block was planned is
  wrong for every trial next to an abort or a repeat.
- **(b) Search layouts.** The spec does not say whether a repeat re-draws its drawn values (§14.1:
  array rotation, jitter, target position). If it reuses them, an animal that broke fixation after the
  array appeared already knows where the target is, and repeats become faster and more accurate.
- **(c) Block types where the rule has no meaning.**
  - Under weighted draws or draws with replacement there is no planned sequence to insert into.
  - Under criterion- or time-ended blocks (§13.5) the remaining length is unknown.
  - When the repeated condition is the only one still owed, "never the very next trial" cannot be met.
    The block must then stall, end short, or repeat at once, and the spec says none of these.
- **(d) "Not repeated" does not mean "not shown again".** §16.2 says TARGET_BREAK, CATCH_BREAK,
  MOTION_BREAK and BLINK_BREAK are "not repeated", and §16.3 says aborts do not count. In a block that
  ends on targets, such a condition still owes, so `_refill` shows it again on the next pass anyway,
  outside the repeat cap (§16.4). The cap's protection against avoidance therefore does not apply to
  those breaks. The cap itself ("stops being repeated; its shortfall recorded") only lets a
  target-ended block end if it also forgives the debt, and the spec does not say that.
- **(e) Today's code matches neither rule.** A requeue appends to the queue (`scheduler.py:294-298`).
  Under `Shuffled` that puts it at the end of the current pass. Under `WithReplacement` and
  `Constrained` it makes it the very next trial, and under `Constrained` the requeue also bypasses
  `max_run`.
- **(f) Hard conditions drift late.** Conditions the animal breaks on more often migrate toward the
  end of each block. Condition then covaries with time in the block (satiety, fatigue, adaptation).
  This is a limitation to state; position in the block is derivable from the record.

**Severity:** misleading for priming, search and sequence designs; undefined for most block types.
**Type:** PI decision, then spec corrections.

**Questions for the PI:**

1. In blocks whose trial-to-trial sequence is the design (priming, sequence-balanced orders), which
   applies?
   - no repeats;
   - an immediate repeat;
   - a repeat at a random later point, with analysis using the realized sequence (aborted trials
     included as predecessors).
2. Does a repeat re-draw its nuisance values? Recommended: yes.
3. When the repeated condition is the last one owed, what happens: an immediate repeat, or the block
   ends with the shortfall recorded?

**Spec corrections:**

- Define "later point" for each order type and for criterion- and time-ended blocks.
- Say that the cap forgives the debt.
- Make the "repeated" and "counted" lists one table, so a condition that is neither cannot quietly
  return.
- Record each trial's realized predecessor (including aborted trials, and whether their display was
  shown), so sequence analyses do not depend on the plan.

## 3. Rounding to the nearest frame silently merges or unevenly spaces timing levels, and the loop actually rounds up

**Paradigms:** forward and backward masking (SOA as a factor), RSVP, predictive sequences, flash
suppression, detection and discrimination with a staircase on duration, non-aging foreperiods.

**Scenarios.** §6.2 rounds any duration that is not a whole number of frames to the nearest frame,
unless the task marks it exact.

- **Masking at 240 Hz.** SOAs of 10/20/30/40/50 ms become 2/5/7/10/12 frames, which is
  8.3/20.8/29.2/41.7/50.0 ms. The levels are no longer equally spaced (steps alternate 12.5 and
  8.3 ms), and the condition names state times that were never shown.
- **Masking at 120 Hz.** SOAs of 15 and 20 ms both become 2 frames (16.7 ms), so two named conditions
  are the same physical stimulus. The data will "show" no difference between them.
- **Duration staircases.** A staircase with 2 ms steps around 25 ms at 240 Hz moves through
  6.72/6.24/5.76 frames, which rounds to 7/6/6. Half the steps do not change the stimulus, and the
  threshold reported in milliseconds is not a duration that was ever shown.
- **RSVP.** A 25 Hz RSVP stream (40 ms per item) is 9.6 frames per item at 240 Hz. Rounded per item it
  runs at 24 Hz, so a frequency-tagging analysis at 25 Hz looks at the wrong frequency, and the 100th
  item is 167 ms off schedule. Rounded on cumulative onsets it alternates 10- and 9-frame items. §6.6
  does not say which rule applies.

**The code does not round to the nearest frame.** The loop fires `After` and `Hold` when elapsed
seconds ≥ declared seconds (`run.py:451, 515, 520, 534`). That rounds a fractional duration *up*: 10 ms
at 240 Hz takes 3 frames (12.5 ms) where §6.2 says 2 (8.3 ms). It also adds a frame to *whole* durations
whenever the frame period is a measured value slightly shorter than nominal. I computed this: at
240.02 Hz, 50 ms takes 13 frames and 1 s takes 241. Today the period is the constant 1/240
(`service.py:99`, `cli.py:1659`), so this does not bite yet. §6.1's "converted at the session's rate"
would make it bite.

**The non-aging foreperiod (§14.4).** Its definition is incomplete:

- On a frame grid, a constant hazard is a geometric distribution in refreshes. It needs a minimum, a
  mean, a maximum, and a rule for the tail.
- An exponential truncated at a maximum and resampled has a hazard that *rises* toward the maximum, so
  late onsets become predictable, which is the opposite of the design's intent. See Nickerson &
  Burnham 1969, J Exp Psychol (approximate); Janssen & Shadlen 2005, Nat Neurosci, on hazard coding in
  LIP.
- The usual remedy is to put the truncated mass into catch trials, or to report the hazard actually
  produced.

**Severity:** misleading. **Type:** spec correction, plus one PI question.

**Spec changes:**

1. Convert every duration to frames once, at load, by the stated rule, and compare frame counts in
   the loop. Never compare elapsed seconds against a measured period.
2. A duration that is a factor level, a sequence's item period, or a value a procedure controls is
   exact by default. When it does not fit whole frames, refuse it at load and list the nearest valid
   values. Refuse any two levels that round to the same frame count.
3. Procedures on a time parameter step in frames.
4. A sequence declares whether it rounds per item or on cumulative onsets.
5. A foreperiod declares its minimum, mean, maximum and tail rule, and the review report's timing
   diagram plots the hazard it actually produces.

**Question for the PI:** should item 2 be exact-by-default, or a warning?

## 4. On the black default, a patterned stimulus has no defined mean luminance and an edge has no defined meaning

**Paradigms:** tuning tasks (orientation, size, spatial frequency), bar-sweep and sparse-noise mapping,
Gabor detection and discrimination, M/P/K mapping, texture and figure-ground displays, masks.

**Scenario.** §7.5 lets Michelson and RMS contrast run on black, and §4.12 requires a convention. But a
grating or noise patch at "Michelson 0.5" needs a mean luminance, and neither §4 nor §7 gives a
patterned fill one. Today's `Gabor` has only `contrast=1.0` (`task.py:500-512`).

Whatever mean the drawer chooses, on black the stimulus is a luminance increment (a bright blob on
0 cd/m²) with the pattern on top. V1 and V4 neurons respond strongly to the increment:

- Orientation tuning gains an untuned component, which flattens the selectivity index.
- A size-tuning curve measures a bright disk that grows, so surround suppression is confounded with
  luminance flux.
- Bar and sparse-noise maps conflate ON responses with pattern responses.

A methods section that says "Michelson 0.5 Gabor" would describe a stimulus that was never shown.

**The edge profile has no stated meaning (§4.1, §4.2).** A Gaussian edge could taper *opacity*, which
on black blends the patch into a Gaussian luminance blob. Or it could taper *contrast* about the
stimulus's mean, which leaves a flat disk at the mean luminance with a hard rim. The literature's Gabor
is the second, on a background equal to the mean. §5.2's "one size number is the full width" also
leaves open, for a Gaussian edge, whether size means FWHM, ±kσ, or the cut-off. Reported size-tuning
numbers depend on that choice.

**Severity:** misleading. **Type:** spec correction, plus one PI question.

**Spec changes:**

- Each patterned fill has a mean luminance, defaulting to whatever is behind it.
- A stimulus whose mean differs from what is behind it gets a load-time warning that names the
  luminance step.
- Each edge block states whether it is a contrast envelope or an opacity ramp.
- The Gaussian edge's "full width" is defined.

**Question for the PI:** "In recording sessions, should a patterned stimulus whose mean differs from
its background be refused rather than warned?"

## 5. An overridden trial still counts toward its condition and still carries the condition's number in the recording

**Paradigms:** every factorial and tuning design; bar-sweep mapping; search with condition-set
features.

**Scenario.** §14.7 says a live edit to a value a condition sets wins, and the record marks the
overridden trials. Take an orientation-tuning block of 12 conditions. The operator sets `orientation`
to 45° to look at something and forgets to release it for 40 trials. Then:

- Every one of those trials shows 45°.
- Each one still counts toward its own condition's target (§16.3), so the block can end "complete"
  with 40 trials of the design missing, and nothing re-runs them.
- Each one carries its condition's fixed number in the recording (§14.5), so in wl-preproc's trial
  table, sorted by condition, 40 trials at 45° are spread across all twelve orientations, which
  flattens the tuning curve.

The mark lives in the rig's record. An analysis that groups by the recorded condition number never
sees it.

**Severity:** misleading. **Type:** PI decision.

**Questions for the PI:**

1. "Should a trial whose condition was overridden count toward that condition's target?" Recommended:
   no, so the block runs the design it planned.
2. "Should the override reach the recording itself?" For example, the framework's parameter-change code
   plus a per-trial `overridden` column in the behavioral table, so that grouping by condition number
   cannot silently include it.

## 6. The default calibration has no stated session kinds, and isoluminance against a standard observer is not isoluminance for the animal

**Paradigms:** color tuning, M/P/K mapping, color matching, `visual_search`, contrast-response
measurements, color noise and Mondrians.

**Scenarios.**

- **(a) Only isoluminance is refused on the default.** §7.2 refuses isoluminance on the default
  calibration. §19.2 says each warning names the session kinds it is acceptable in, but the spec never
  names them for the default calibration. N§4 batch 3's example ("refused for a recording task that
  declares color part of its design") did not reach the spec, and it depends on the task opting in. So
  the following all load on the default in *recording* sessions, with a warning:
  - L- or M-cone-isolating stimuli, which are not isoluminant;
  - DKL color tuning at non-zero elevation;
  - contrast-response functions.
- **(b) Even a perfect sRGB mode leaves cone contrast unknown.** The sRGB standard fixes CIE 1931
  chromaticities. This QD-OLED's primaries are narrowband, and under Stockman-Sharpe or macaque cone
  fundamentals their cone excitations differ from those computed from the sRGB primaries (observer
  metamerism with narrowband primaries; the size of the effect on this panel is UNVERIFIED). Cone
  contrasts on the default are therefore unknown, not approximately right. Luminance contrast on the
  sRGB curve, against the panel's real transfer, is least reliable near black, which is where the black
  default puts it.
- **(c) A standard observer is not the animal.** §7.2 asks for "a stated observer". The isoluminant
  point of a human standard observer is not that of any particular macaque: L:M cone ratio and macular
  pigment differ between animals, so some luminance is left over. MT and V1 neurons respond to small
  luminance residues, which is why chromatic work in monkeys nulls luminance per animal or per site
  (minimum-motion or flicker nulls; MT-based nulls, e.g., Dobkins & Albright 1994, J Neurosci;
  Gegenfurtner et al. 1994, Vis Neurosci; approximate). In laminar M/P/K mapping, leftover luminance
  drives the magnocellular input layers and would be read as chromatic input.

**Severity:** misleading. **Type:** PI decision.

**Questions for the PI:**

1. "In recording sessions, should the default calibration be refused for any task that specifies a
   color in DKL, cone contrast or xyY, or that makes contrast a factor or a procedure-controlled value,
   decided from the task file rather than by the task declaring color part of its design?"
2. "For an isoluminance claim in a recording session, is a named standard observer enough, or must
   each animal have a measured isoluminant point (kept in its subject settings, applied as a luminance
   offset, and recorded)?"

## 7. DKL units are undefined, the existing gamut test is wrong for DKL, and there is no cone-contrast space

**Paradigms:** color tuning, M/P/K mapping (cone-isolating stimuli), color noise, color matching,
photographs and most-exciting images.

**Scenarios.**

- **(a) DKL units.** DKL has several normalizations: cone contrast of each axis's mechanism, or scaled
  to the monitor's maximum per axis (Brainard 1996, in Kaiser & Boynton, *Human Color Vision*). §7 fixes
  none, so `DKL(l_m=0.1)` names different stimuli in different labs and under different calibrations.
- **(b) The gamut test.** `photometry.unrealizable` treats a DKL color as realizable when
  `max(|lum|, |l_m|, |s_lm|) <= max_cone_contrast` (`photometry.py:155`, default 0.85 at line 86).
  On common displays, isoluminant L-M cone contrast tops out near 0.1-0.2, while S-cone contrast
  reaches about 0.8 (UNVERIFIED for this panel; V9 measures it). So `l_m=0.5` passes the gate and is
  clipped when drawn. Clipping changes chromaticity and luminance together, so an "isoluminant"
  stimulus stops being isoluminant with no warning.
- **(c) No cone-contrast space.** N§1 asked for cone-isolating patterns, but §7 offers only xyY and
  DKL. An L- or M-cone-isolating stimulus therefore has to be assembled by hand from DKL axes under a
  normalization nobody has stated. A slip in sign or scale gives a stimulus that is not cone-isolating
  while the task file says it is.
- **(d) Fundamentals depend on eccentricity.** §7.8 names the cone fundamentals in the calibration,
  but the right ones depend on where the stimulus falls. 2° fundamentals (with macular pigment) suit
  the fovea; 10° fundamentals suit parafoveal and peripheral receptive fields (Stockman & Sharpe 2000,
  Vision Res; CIE 170-1:2006), and most V4 receptive fields lie outside the macula. The instrument
  records spectra (§12.1), so the calibration can keep them and the task can name the fundamentals.
- **(e) Photographs (§4.6).** sRGB defines no absolute luminance. "Looks the same on any calibrated
  rig" therefore needs a stated luminance for the photo's white, under the ABL cap. Set matching (mean
  luminance, RMS contrast, amplitude spectrum) has to be computed on linear luminance after the
  calibration. Tools commonly used for it (e.g., the SHINE toolbox, Willenbockel et al. 2010, Behav Res
  Methods; approximate) work on pixel values, which equal luminance only on a linearized display.

**Severity:** misleading. **Type:** spec correction, plus one PI question.

**Spec changes:**

- Define the DKL axes in cone-contrast terms, with one stated normalization.
- Add cone contrast (ΔL/L, ΔM/M, ΔS/S about the background) as a color specification. It is the space
  DKL is computed through anyway.
- Test realizability by full conversion to primary weights and a [0, 1] check, as xyY already is.
- Declare the luminance of a photo's white.
- Match image sets in linear luminance.

**Question for the PI:** "Cone fundamentals named per task (applied to spectra stored in the
calibration) rather than per calibration?" He chose "Named in the calibration" (N§4 batch 4).

## 8. "Every change" toggles the patch and strobes a code, which is undefined for live-driven and per-frame content

**Paradigms:** manual RF mapping by mouse, gaze-contingent and neural-contingent displays, search
arrays, texture and dot displays built from items, RSVP.

**Scenarios.**

- **Live-driven stimuli.** A live-driven stimulus (a mouse-driven bar, a gaze-anchored patch, a
  neural-driven value) changes the screen description on every frame (§3.3, §4.11). Under §8.1 every
  change toggles the task patch, and under §8.3 "stimulus changed" plus the stimulus's number is
  strobed for every change. During hand mapping or gaze-contingent presentation, the task patch
  becomes a second frame clock. It can no longer mark the one change the experimenter cares about,
  such as the saccade-contingent displacement. Meanwhile the event lines carry at least 2 words per
  live stimulus per refresh (480 words/s at 240 Hz for one stimulus) beside the task's own codes.
  Strobe throughput is unmeasured.
- **Arrays.** "Each item its own stimulus" (§4.4) means a 24-item search array puts 48 words on the
  lines at one decision unless the author groups the items. Grouping is optional.
- **Codes are not onset times.** Codes go out at the decision. With the patch toggling on every
  change, tying a photodiode edge to one particular stimulus needs a join on the screen log's landing
  frames and the flip count. §21 asks wl-preproc for codes, not for that join. Analysts used to
  aligning to "stimulus on" will align to the decision.

**Severity:** misleading. **Type:** spec correction, plus one PI question.

**Spec changes:**

- For §8.1 and §8.3, a "change" is a discrete onset, offset or declared update. Live-driven per-frame
  values and frame-dependent content (drift, noise refresh, movie frames) neither toggle the patch nor
  strobe a code; they live in the screen log by frame.
- Arrays and layouts strobe once as a group by default.
- Ask wl-preproc for onset alignment through the screen log and the flip count, and for a per-trial
  check of task-patch edges against logged changes, as §8.4 does for the flip patch.

**Question for the PI:** "Should each RSVP or sequence item toggle the task patch?" Recommended: yes;
items are discrete events analysts align to.

## 9. Reverse correlation needs a defined random generator and a defined rule for late frames

**Paradigms:** sparse noise mapping, dense noise and m-sequences, subspace (Ringach/Hartley) gratings,
color noise, random-dot stimuli.

**Scenarios.**

- **(a) The generator.** "Seed, frames on request" (§4.3) rebuilds noise from a seed in the exact
  drawer, which is numpy, while the Rust core draws it on the GPU. Unless the generator is specified
  as part of the block (a counter-based hash of seed, frame and element, implemented the same way in
  Python and Rust), the two differ. Even then, a numpy upgrade can change the reconstruction.
  numpy's compatibility policy allows `Generator` methods to change their streams across feature
  releases; only `BitGenerator`s carry stronger guarantees (numpy.org, "Compatibility policy", read
  2026-10-07). An analysis machine on a different numpy than the rig would silently rebuild different
  frames, and every kernel estimated from them would be computed against the wrong stimulus.
- **(b) Late frames.** §3.3 computes frame-dependent content "from the frame number". When a frame is
  late, the spec does not say whether the next refresh shows content *k+1* (the sequence slips) or
  *k+2* (*k+1* was never shown). The exact drawer and the display must agree, and analysis must know
  which happened. For m-sequences, a skipped or duplicated element breaks the orthogonality the kernel
  estimate rests on (Reid, Victor & Shapley 1997, Vis Neurosci).
- **(c) Dithering.** Dithering is §7.4's fallback if 10-bit fails, but it is not on §19.2's warnings
  list. Temporal dithering adds pixel noise that the exact drawer cannot rebuild unless the dither is
  deterministic and modeled.

**Severity:** misleading. **Type:** spec correction.

**Spec changes:**

- Specify each random block's generator algorithm and commit frozen reference outputs.
- State the late-frame rule. Have the display report, per refresh, which content index it showed, and
  mark m-sequence trials with any drop.
- Add dithering to the warnings list.
- Say that frames saved "on request" come from the exact drawer, not from the GPU.

## 10. One calibration for both stereoscope halves leaves the balance between the eyes unmeasured

**Paradigms:** binocular rivalry, binocular rivalry flash suppression and CFS, monocular
vs. binocular presentation, dichoptic masking.

**Scenarios.**

- **The halves are not equal.** §7.6 assumes them equal. S0 §5.4 item 3 itself records about 4%
  left-right nonuniformity on a 27-inch OLED (the JOV study) and calls left-right nonuniformity "an
  interocular mismatch". S4 §9 planned a transfer per half.
- **The mirrors add more.** Each eye looks through two front-surface mirrors whose losses need not
  match (coating, dust, angle). A calibration taken at one eye point, or in direct view, also misstates
  the stereoscope's absolute luminance by the mirrors' loss.
- **Why it matters.** Rivalry predominance shifts with the relative strength of the two eyes' stimuli
  (Levelt 1965). How long CFS suppresses depends on each eye's contrast. Monocular-versus-binocular
  comparisons need equal monocular luminances. A few-percent imbalance appears as an eye-dominance
  effect that belongs to the rig, not to the animal.
- **Two OLED aggravations.**
  - CFS keeps flashing, high-contrast Mondrians in one half for whole sessions. If the masked eye is
    not counterbalanced across sessions, that half ages faster.
  - Brightness coupling between halves (S0 §5.4 item 2) lets the mask's fill modulate the other eye's
    target at the mask's flicker rate. §7.7's cap must come from V9's cross-half test, not from
    full-field ABL alone.
- **Contrast ramps (limitation).** Breaking-CFS ramps the target's contrast (Jiang, Costello & He 2007,
  Psychol Sci; approximate). §6 offers sine modulation, square flicker and paths for position, but no
  ramp on contrast. A ramp can only be written as a sequence of items, each of which toggles the patch
  and strobes a code (finding 8).

**Severity:** misleading for dichoptic paradigms. **Type:** PI decision.

**Question for the PI:** "Keep one calibration for the panel, but measure each eye's luminance and
white point through its own mirror path at every calibration (the automated procedure run at both eye
points), record the ratio between the eyes, and warn or refuse dichoptic tasks in recording sessions
beyond a tolerance? Or one calibration per eye's path?"

## 11. The two-grid alignment check is either empty or confounded with phoria, and disparity's sign is not pinned

**Paradigms:** everything on the stereoscope, especially rivalry at non-corresponding positions, nonius
and fusion tests, and disparity tuning.

**Scenarios.**

- **(a) An empty comparison.** §12.4 fits each eye's map from that eye's own monocular grid and
  "compares the two". If the comparison uses each eye's calibrated position on its own grid, the
  answer is zero by construction: each fit absorbs any offset, rotation or scale between that eye and
  its half-image.
- **(b) The informative comparison mixes in phoria.** The comparison that does carry information uses
  the *covered* eye. During the left-eye grid, the right eye (seeing black) is recorded too; mapped
  through its own fit, it shows where the right eye pointed while the left eye fixated target *i*.
  That deviation is optical misalignment **plus the animal's dissociated phoria**: under monocular
  viewing the covered eye drifts to its phoria, which is not a property of the mirrors. Horizontal
  phorias can plausibly exceed 0.25° (macaque values UNVERIFIED; in humans, near phorias of
  a few prism diopters, roughly 1-3°, are common; approximate). Vertical phorias are usually smaller, so the vertical component is the cleaner
  test of mirror alignment.

  Consequences: a 0.25° tolerance on the total would refuse recording sessions because of the animal's
  eyes. "Realigning the mirrors" to null it would build the phoria into the optics. That may be
  acceptable, since it lowers the fusional demand, but it changes where zero disparity sits, and the
  choice should be made knowingly.
- **(c) Noise.** Fixation scatter and per-point calibration residuals in a fixating macaque are of the
  order of tenths of a degree (UNVERIFIED for this tracker). The difference of two independent grids
  has √2 that noise. A *per-point* 0.25° limit would fail on noise alone.
- **(d) Disparity's sign is named, not pinned.** §5.4 names the convention ("near negative") but not
  the per-eye offsets. A sign error in the drawer would invert every near/far result and still pass
  every match test, because the exact drawer and the GPU drawer would agree with each other. The
  correct formula: left-eye x = x − d/2 and right-eye x = x + d/2, so d < 0 shifts the left eye's image
  right, which is crossed, which is near. §12 does not carry forward S4 §10 item 6's disparity
  verification, and in an animal, "confirmed fused and at the intended depth" can only mean a vergence
  response of the right sign to a disparity step (short-latency disparity vergence: Busettini, Miles &
  Krauzlis 1996, J Neurophysiol; approximate).
- **(e) Per-eye positions are undefined.** §5.4 does not say what a per-eye position is measured in, or
  what happens when a stimulus carries both per-eye positions and a disparity.

**Severity:** misleading. **Type:** PI decision on (b) and (c); spec correction on (a), (d) and (e).

**Questions for the PI:**

1. "The check measures the mirrors plus the animal's phoria. Should the tolerance apply to the
   vertical component only, or to the total?"
2. "Should it apply to the systematic difference between the two eyes' maps (offset, rotation, scale
   across the 13 points), judged against the same eye's test-retest repeatability, rather than per
   point?"

**Spec corrections:**

- Say exactly which positions are compared.
- Write the per-eye disparity formula into the exact drawer's tests.
- Keep the disparity-sign check, done by vergence.
- Define a per-eye position as that eye's own direction in degrees (its viewport, after the vergence
  offset), and refuse a stimulus carrying both per-eye positions and a disparity.

## 12. Recorded delays and onsets leave out the tracker's latency, the scan to the stimulus's row, and the panel's latency

**Paradigms:** gaze-contingent and saccade-contingent displays, gaze-anchored stimuli, full-screen flash
(CSD mapping), multisensory audiovisual decisions.

**Scenarios.**

- **(a) The recorded delay is a lower bound.** §6.10 records a delay as "sample age plus landing
  frame", and a task's declared maximum is checked against it.
  - S5 §3 stamps a sample's age from its *arrival* at the rig, so the tracker's capture-to-arrival
    latency is left out. That includes camera exposure and processing; OpenIrisDPI reports 1.1 ms
    median processing with about 2% of frames at 10 ms or more on its authors' hardware (S5 §4).
  - The landing frame is the frame's *start*, so the scan down to the stimulus's row (up to one frame
    period) and the panel's own latency are left out too.

  Trials are therefore marked "within the limit" when they were not.
- **(b) Saccade-contingent changes.** For a change meant to fall *during* a saccade, what matters is
  whether it reached the stimulus's row before the saccade ended. The notes' gloss on N§2 batch 3,
  "update only when a saccade lands (inside saccadic suppression)", is wrong for displacements:
  displacement during a saccade goes unseen, but displacement after landing is readily seen (Bridgeman,
  Hendry & Stark 1975, Vision Res; Deubel, Schneider & Bridgeman 1996, Vision Res). Task authors will
  reuse that phrase.
- **(c) Large stimuli.** §6.5 records "the stimulus's vertical position". A full-screen flash, a
  full-field mask or a large grating lights over the whole scan, so a single center height mistimes
  the receptive field's location by up to half a frame. That bias is systematic in laminar latency
  comparisons.
- **(d) Audiovisual timing.** §9.1 starts the sound on a hardware trigger "from the frame the visual
  change lands on" without naming the trigger: the bottom photodiode edge, or the flip. Either way, the
  asynchrony between sound and sight then depends on the visual stimulus's height, by up to a frame.
  The speaker-to-ear delay (about 3 ms per meter) is invisible to V7's electrical tap.

**Severity:** misleading for contingent paradigms; minor but systematic for the others. **Type:** spec
correction.

**Spec changes:**

- The delay is decision time minus the sample's capture time (from the eye PC's clock, once aligned),
  plus the frame start, plus V1's scan delay at the stimulus's height, plus the measured panel latency.
  Until V1 and V3 exist, the mark is labeled a lower bound.
- Record each stimulus's vertical *extent*, not a center.
- Name the audio trigger reference, and let the declared offset include the scan delay to the
  stimulus's height.
- Correct the notes' saccadic-suppression gloss.

## 13. The continuous mode counts flip edges across 288,000 frames with no re-anchoring

**Paradigms:** the 20-minute free-viewing movie, long adaptation with probes, any continuous-mode
session.

**Scenarios.**

- **(a) Frame identity can slip.** §8.4 matches frames to the recording by counting flip-patch edges
  from each trial's start code, checked against the trial's known length. A continuous epoch has one
  start: 20 minutes at 240 Hz is 288,000 edges. One missed or extra edge shifts every later movie
  frame against the neural data by 4.17 ms. Nothing notices until the end, and the end check can say
  only "off by n", not where.
- **(b) Gaze drift goes uncorrected.** S5's in-task calibration epochs gather points from fixations on
  known targets. Twenty minutes of free viewing has none, so the gaze map drifts uncorrected unless the
  scheduled probes include fixation targets.
- **(c) 25 fps movies (limitation).** Movies at 25 fps (PAL sources, common in Europe) are refused at
  both 240 and 120 Hz (§4.6). Re-timing to 24 fps changes every motion speed and the soundtrack's pitch
  by 4%, and pulldown introduces judder. Whichever is done should be recorded in the media set's
  manifest. Whether the panel runs at a rate 25 divides, such as 200 Hz, is UNVERIFIED.

**Severity:** misleading. **Type:** spec correction, as a requirement on build K.

**Spec changes:**

- In continuous mode, strobe a frame-index code periodically (for example every second), so a miscount
  is confined to one interval and located.
- A continuous run declares its calibration probes, or the record states the gaze map's age.
- Record any movie re-timing.

## 14. Pauses, interludes, restarts and generator waits break adaptation and the inter-trial interval without a trace

**Paradigms:** adaptation with top-up, long adaptation, any task with a non-black background, and
most-exciting-image generation.

**Scenarios.**

- **(a) Adaptation breaks with no trace.** An adaptation run keeps its adapter up across trials (§6.9)
  and relies on short top-ups after a long initial adaptation. Any of the following lets the adapted
  state decay (contrast adaptation recovers over seconds to tens of seconds: Ohzawa, Sclar & Freeman
  1985, J Neurophysiol; Kohn 2007, J Neurophysiol):
  - a pause, black by default (§11.5);
  - an auto-pause on disengagement (§13.9);
  - a display restart (§11.3);
  - an interlude such as a recalibration or a quick RF map, after which the run "returns to the same
    block with its counts and order" (§13.4).

  The next trials resume on a top-up alone, and unadapted trials are pooled with adapted ones.
- **(b) The black pause resets luminance adaptation.** For any task with a gray background, the black
  default pause also resets luminance adaptation, so the first trials after a resume run under a
  luminance transient.
- **(c) Generator waits vary the inter-trial interval.** A most-exciting-image wait (§4.8) lengthens
  the interval before the next image. If generation time grows with the optimization's step or with
  image complexity, the interval covaries with the closed loop's progress. Responses depend on that
  interval (recovery from adaptation, arousal), so the optimization can climb an interval artifact.
  The spec records that the console waits, not how long the trial waited.

**Severity:** misleading for adaptation and closed-loop paradigms. **Type:** PI decision, then a spec
correction.

**Question for the PI:** "For a task that declares a non-black background, should the pause screen
default to that background rather than black?"

**Spec changes:**

- Record per trial the time since the last interruption and the realized interval before each
  stimulus.
- Let a task declare what a block does when it resumes after an interruption (for example, rerun the
  initial adaptation).
- Let a closed-loop procedure read the wait (§15.5 already allows "anything the trial recorded").

## 15. The mode check drops S4 §9's care features and VRR

**Paradigms:** every paradigm, especially long static displays (fixation, adaptation, the continuous
mode) and anything that relies on the gaze-to-pixel geometry.

**Scenario.** §11.6 checks panel identity, resolution, refresh and bit depth. S4 §9 listed "the state
of every 'care' feature", and S0 §5.4 test 1 disqualifies a panel whose care features cannot be turned
off. Four settings are missing:

- **Pixel shift** periodically translates the whole image, silently breaking the geometry and possibly
  walking the photodiode patch off its sensor.
- **The OSD's brightness mode.** A Uniform Brightness setting is reported to cap the panel near
  250 cd/m², and with it off ABL-style dimming depends on content (displayninja review, read
  2026-10-07; UNVERIFIED). This is the same quantity §7.7 caps in software.
- **VRR.** Under VRR a late frame stretches the refresh instead of repeating it, which contradicts the
  late-frame model in finding 9. OLEDs are also widely reported to change brightness with the refresh
  interval under VRR (UNVERIFIED for this panel).
- **The proximity sensor's "black screen"** (S0 §5.3).

None of these can be corrected in analysis.

**Severity:** misleading. **Type:** spec correction.

**Spec changes:**

- The rig file records these settings, bring-up verifies them, and the mode check covers them.
- Whether "on" refuses a recording session or only warns follows the PI's existing choice of "warn on
  a mismatch" unless he wants these refused.

---

## Checked, with no finding

- **Monocular presentation in direct view.** Already refused by the checker: a stimulus shown to one
  eye needs `view="stereoscope"` (`task.py:426-431`). Build A should extend the same refusal to per-eye
  positions and per-eye backgrounds.
- **Manual RF mapping by mouse.** Positions are recorded every frame, which is what matters. Two
  limitations to state:
  - The console is a browser, and Safari delivers pointer events at its own refresh rate (UNVERIFIED
    for the PI's machine) plus network delay, so the bar moves in steps of a few refreshes.
  - A marker the operator drops lags the stimulus by neural latency plus reaction time, so on a moving
    bar it sits displaced along the motion. Reconstruct receptive fields from the per-frame record,
    not from the markers.
- **M/P/K temporal frequencies.** Fine at 240 Hz: sine modulation at any frequency, and square flicker
  at 120/60/40/30/24/20 Hz. The color side is findings 6 and 7.
- **Full-screen flash.** Its luminance is bounded by the §7.7 cap, which is set by sustained full-field
  luminance (S0 §5.4 item 6, unmeasured). This is a limitation to state, not a defect.
- **Curve tracing, occlusion, figure-ground textures, memory-guided, visually guided and delayed
  saccades, rule-based cue tasks, betting.** Nothing beyond findings 1-5.
