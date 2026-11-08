# The first real task: pop-out search, and what it needs

**Status:** designed with the PI on 2026-11-07 (a brainstorm in the browser companion; his answers are quoted below as
he gave them). The design document a builder plans from. Its plan is a design and a list of tests, built once (the PI,
2026-11-07, after the whole-project audit: "Yes, lighter").

## 1. Intent

The lab's first real training task: an animal that already fixates reliably learns to look to the one item that pops
out of a ring of items. It is the first task written with the PI for the task library (wl-xtasks), and the first to
run **end to end**: through the rig's own eye rules in simulation, in demo mode with the mouse as the eye, and drawn on
an actual display ("Also on a real screen", 2026-11-07). It exists to train an animal, and to find out, by running one
real task, what the engine still lacks (the audit's recommendation, which the PI took: pause engine builds C4 to C9
"until one real training task ... runs end to end").

**Goals.** A trainer can run this task on a rig session after session, see where the animal is, confirm each step up,
lock a setting, and read a record wl-preproc understands. The simulated animal scores it as the rig would. A person can
play it with the mouse.

**Non-goals.** No engine generality this task does not use. No reward size by condition (XC-451 stays its own
design). No carrying an animal's stage across sessions automatically (the trainer picks each day; see §3.6).

**Anti-goals** (what would make it a failure even if it ran): the odd one found by brightness where the PI wants
color alone; a simulation that scores the task differently from the rig; a trainer who cannot tell what stage the
animal is in or why the rig suggests a move; a task a reviewer cannot read.

## 2. Its parts, and the order (the PI: "Task, sim, demo; E designed next")

1. **The task** (§3), in wl-xtasks, and what the engine must gain for it (§5).
2. **The simulated animal through the rig's eye rules** (XC-456).
3. **Demo mode** (XC-013; its parked spec, `2026-10-06-demo-mode-design.md`, §14 lists what changes before it is built).
4. **The display program** (build E): designed with the PI right after this, as its own document, because "done"
   includes a real screen and it is the largest build left.

Parts 1 to 3 are one build. Part 4 is the next design conversation.

## 3. The task, as the PI decided it

**Every number below is a setting the trainer may change in the console, its start the PI's value** (the PI,
2026-11-07, on the build's review: "i mean, everything should be adjustable in the console, no?"; TSK-75). A number
stays fixed only with its reason written beside it in the task (the bounds on the engine's own waits, the center, each
staircase's hardest end, the ring's whole-circle direction and each stage's one condition's target; TSK-75). Each setting's
range is the builder's (the fix round).

### 3.1 The trial
"keep this as an RT-search task, meaning there will be no delay between array presentation and fixation dimming/go
cue": the fixation dot goes off on the frame the items appear, and that is the go.

| Step | Value (starting values the trainer may change; "that looks good") |
|---|---|
| get to fixation | within 2.0 s, else no fixation |
| hold fixation | 0.5 s |
| items on, fixation dot off (the go) | the same frame |
| look to the odd one | within 1.0 s, else no response |
| hold on it | 0.3 s, then juice |
| between trials | 1.0 s |
| after a wrong item or an early saccade | a blank screen for about 2 s, no juice ("A short timeout") |

Leaving the fixation window before the go is an early saccade error (the PI, 2026-11-07: "if a saccade starts during
a cue, before the go period, that would be an early saccade error"; and, of an eye still inside the window at the go,
"then it is fine"). **The answer is the next saccade from fixation**: "anything other than looking at the target with
the next saccade from fix to the target is an error". A saccade that lands on another item or on empty space is an
error, and so (my reading of the same rule) is leaving the target before its 0.3 s hold; each gets the timeout. One reward per correct trial; its size is the
animal's own limits file's, as for every task.

**Sizes** (degrees of visual angle, forward-calculated at their place, never from a mean pixels-per-degree), each a
setting: discs 1° across (`disc_size`) on a ring 8° from center (`ring_radius`); fixation dot 0.3° (`fix_size`);
fixation window radius 2°; target window radius 1.5° (at the starts, twelve items on the 8° ring stay 4.1° apart, so
1.5° windows never overlap; over the ranges they can, twelve on the smallest ring, 4°, and the load check warns of it,
`crowded-array`). The background is **black** ("On black, faint to full").

### 3.2 The colors
wl-style's isoluminant set ("the isoluminate bluish color and redish color that was desigined in wl-style for
isoluminance"): its isohue spectrum, a CAM16-UCS hue sector at fixed chroma, matched in **macaque cone luminance**
(L + M at an L:M ratio of 1). Its blue (hue 260°), purple (320°) and red (20°), and a fourth he asked for, **green at hue
140°** ("A is fine"), built the same way (chroma 29.5, same cone luminance; ΔE 51, 59 and 51 from blue, purple and red;
inside the sRGB gamut, whose limit at that hue is chroma 38). The sRGB previews are blue #2f93f8, purple #bc79e0, red
#ed7474, green #54a947; the rig draws them from their definition on its measured panel (§4).

- **Whose luminance**: L + M at L:M 1 on the **Stockman–Sharpe 2° cone fundamentals**, as wl-style computes it ("wl-style's
  2-degree set"), not the CIE 2006 10° set the engine uses for its other colors. The rig holds them on the CIE's own 2006
  2° table, the same fundamentals (bundled 2026-11-07, the PI: "Swap before merge"; ADR-0012, amended).
- **How bright at full**: **15 cd/m²** on every rig, a setting the trainer may change ("15 cd/m² on every rig"):
  `color_luminance`, 1 to 30 cd/m², checked over that range at load (a value a panel would desaturate the four at is a
  warning saying which part of the range). Fade-in's distractors run from a fraction of that to it.
- **A panel that cannot show them** at that level and chroma (my call): all four lose chroma together, never luminance,
  and the load check warns saying by how much; no color is clipped, since clipping breaks the luminance match.

**A pool of four** ("A pool of four"): on each trial one color is the odd one and another fills the distractors, so the
animal learns the odd one, not the blue one. Twelve ordered pairings exist. **The pool starts small and widens**
("Start with fewer, add more"): the trainer picks the first pairings ("The trainer picks"), and the rig suggests adding
more by the same rule as a stage (§3.4; "Same rule: rig suggests").

### 3.3 The stages, named
"stage numbers are not descriptive enough. there should be short stage names": **Alone, Fade-in, Crowd.**

| Stage | What the animal sees | What moves within it |
|---|---|---|
| **Alone** | the odd one alone on the ring | nothing |
| **Fade-in** | 4 items: the odd one at full, 3 distractors at a fraction of full luminance | distractor luminance, faint to full ("By brightness instead"; "On black, faint to full") |
| **Crowd** | items at full, from 4 up to 12 | set size, one at a time ("set size starts at 4, and finer steps") |

At the end of Fade-in the distractors match the odd one's luminance, so it differs by color alone.

### 3.4 Moving within and between stages
- **Within a stage, a staircase** ("Automatic within a stage"): three correct in a row step harder, one error steps
  easier (`staircase_down`, `staircase_up`, shared by both stages), holding performance near 79% correct
  [@levitt1971transformed], close to the bar below. Errors are TSK-33's default: a wrong item and no response count as
  failures; a trial that ends before the decision (no fixation, an early saccade) moves nothing. The step sizes are the
  builder's (§7), each a setting: Fade-in's distractors by a tenth of full (`fade_in_step`), Crowd's discs one at a time
  (`crowd_step`); a step changed live re-derives the levels at the level nearest the staircase's value. Each
  staircase's easiest end is a setting too, a tenth of full (`fade_in_floor`) and four discs (`crowd_floor`); its hardest
  end, full and twelve, is the stage's own.
- **A lock**: "there should also be a way for the experimenter to lock the parameters". A person's live value on a
  setting holds it, and the staircase leaves it alone until it is handed back (TSK-32: "a live value on its parameter
  holds it"; built in engine build C3 as a held setting and a hand-back).
- **Between stages, the rig suggests and the trainer confirms** ("Rig suggests, trainer confirms"). The bar: "80%
  correct, last 50 trials" (`move_up_bar`, `move_up_window`, one pair for every stage, read at each judgment), judged at
  the stage's hardest step ("Hardest step reached, 80% there"): Fade-in's distractors at full luminance, Crowd at 12
  items, Alone as it is -- whoever set it there (the PI, 2026-11-07: "Any trial played at the hardest step counts,
  whoever set it there").
- **A suggestion stays up until its bar is missed by more than 3 answers** (the PI, 2026-11-08, asked in the UI: "Stay
  up until 3 below"): "With the 80% bar, it appears at 40 of 50 and goes only below 37. The 3 is itself a console
  setting" (`suggestion_margin`); the same in mirror for moving back and for widening the pool.
- **Back down, the same way** ("Rig suggests, trainer confirms"): below 50% of the last 50 ("Below 50% of the last 50",
  a setting the trainer may change: `move_back_bar`, `move_back_window`), the rig suggests the previous stage, or a
  narrower pool, and the trainer confirms or holds; the trainer may also move back by hand. **The narrower pool is not
  built**: the PI, 2026-11-07, "File it; trainer narrows by hand" (XC-463).
- **Widening the pairing pool** uses the same bar; at the prompt **the trainer picks** which pairings to add ("Trainer
  picks at the prompt"). My calls: the bar is judged over all the current pairings pooled; in Alone, where no distractor
  shows, a pairing is only the odd one's color; when one window of trials meets both bars, one prompt offers both, the
  stage first; a widening leaves the staircase where it is; the pool carries into the next stage. **Taking one
  re-offers the other at once** (the PI, 2026-11-07, on the build's review: "Re-offer the other at once"): a move up
  taken, the widening comes straight back in the next stage on the window that met it; a widening taken, the move up
  comes straight back on its window, which the widening does not empty.
- **The last 50** (my call, following the engine's rule that moving up judges answers only, and TSK-33): the trials
  that reached the go and ended with an answer (correct, an error of §3.1, or no response); no-fixation trials and early
  saccades are left out of the 50 and shown beside it, so the trainer sees them.

### 3.5 What the trainer sees
The PI accepted the sketch with the stage names (`.superpowers/brainstorm/` "trainer" screen): at the day's start, the
stage, the staircase's starting level and the pairings to pick, with yesterday's end shown; during the session, the stage
by name, the staircase's level and its lock, the last 50 trials' percent correct and errors by kind, the pairings on,
and, when the bar is met, a prompt naming why ("the distractors are at full brightness and 41 of the last 50 were
correct") with **Move up** and **Hold**.

### 3.6 Each new day
"The trainer picks" where the animal starts: stage, level and pairings, at the run's start. Nothing carries the stage
across sessions on its own (that is the paused build C7's).

## 4. Where it lives
- **The task file**: wl-xtasks, its first real task (the PI's rule for that library: its tasks are "carefully built and
  curated with serious input from me"). Until the library pull exists (XC-150) it runs by path.
- **The stimulus definitions** ("Definitions in wl-xtasks"): a shared stimuli part of wl-xtasks holds what each color
  is (hue, chroma, the held luminance and its observer), as **plain data** a reader needs no wl-xcon code to read (my
  call); **the engine computes** the drive values for the rig's measured panel; wl-style may draw its figure palettes
  from the same definition. **This build does not edit wl-style**: its `02-color/isohue_spectrum/` is the PI's own work,
  not committed there today (`git status` 2026-11-07: untracked), and is his to commit or move; the definition's numbers
  are copied into wl-xtasks with their source named.
- **Its event codes**: from an allocation (wl-xtasks has none yet; `tasks/allocation.py` until it does).

## 5. What the engine must gain (each the builder's to design within this document)
1. **A trainer-confirmed move.** `ByCriterion` moves a progression up on its own when a rule is met; this task needs the
   rig to *suggest* and a person to confirm (or hold), the suggestion and the answer in the change log.
2. **A staircase** that runs between trials on a named setting (transformed up-down, three down one up, TSK-32's
   library; today the reference task's `next_params` is called by nothing, XC-242), that a person's held value stops
   and a hand-back restarts.
3. **A second dimension of progression**, the pairing pool, widened by the same bar.
4. **Macaque cone luminance** as a luminance the photometry holds equal (L + M at L:M 1 on the Stockman–Sharpe 2°
   fundamentals, as wl-style computes it), beside the CIE 2006 10° set the engine uses today (a new bundled table:
   ADR-0012's license and source rules apply), and the isohue colors computed from their definition on a measured panel
   at 15 cd/m² (wl-style's `build_from_measurement.py` is the reference method; a test reproduces wl-style's delivered
   values on its sRGB model).
5. **The day's start**: the trainer picks the stage, the staircase's level and the pairings when the run starts, with
   the previous session's end shown.
6. **The record**: every trial line carries its stage, the staircase's level, its pairing and its set size; every
   suggestion, confirmation, hold, lock and hand-back is a change-log row (wl-preproc reads the change log by kind since
   its 295f9c9, 2026-11-07).
7. **The simulated animal through `gaze.Tracked`** (XC-456), so a simulated session of this task scores as the rig
   would; and **demo mode** (XC-013), the mouse as the eye. **Demo mode's parked spec places a rule in
   `Service._open`, which is welfare-listed** (its §14 item 10): its revised spec goes to the PI with its welfare items
   before it is built, as that spec says; approving this document does not approve it.

## 6. Constraints
- CLAUDE.md binds the build: sim first; hot-path discipline (the staircase and the suggestion run between trials,
  never in a frame); no timing claim without a measurement; warnings over refusals (the PI, 2026-10-11); welfare-listed
  code changes only with his review (nothing here should touch it; the reward stays `Reward("reward_correct")`).
- The task names how reward is configured, never how much.
- Positions and sizes are true visual angle at their place (the PI, 2026-10-19).

## 7. Left to the builder
The staircase's step sizes and its floor and ceiling within each stage; how the suggestion is shown in the console's
existing panes; the trial line's field names (told to wl-preproc before they are written); the stimuli module's file
layout in wl-xtasks; the event codes; the demo mode details its parked spec already settles.

## 8. Not in this design
The display program (build E, next); reward size by condition (XC-451); a default limits file (XC-459, a welfare
design with the PI); the sync-box client (XC-460); a per-animal measurement of isoluminance (wl-style's note: L:M varies
0.45 to 1.94 across animals); the permanent task designer the PI wants "at some point".
