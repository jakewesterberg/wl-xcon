# Console settings from the demo try-out: timing, limits, scaling, colors, sections, training

**Status:** Approved by the PI on 2026-11-16, asked in the UI: 'Approve both'. Brainstormed with him that day during
his Safari try-out of demo mode; its plan is
[`2026-11-16-console-settings.md`](../plans/2026-11-16-console-settings.md). A companion design, [the pop-out's
revision](2026-11-16-popout-revision-design.md), uses what this one builds.

> **Built 2026-11-18** on branch `console-build-2026-11-17` (Tasks 1 to 12 of the plan, not merged; wl-xtasks'
> half on `console-settings-2026-11-16`). Where the build differs from this design, the plan's ledger and the
> code are the record: a size's lowest is left open rather than given an invented number; `frozen` also holds a
> stage's time limit, **and since the PI's answers of 2026-11-18 stops its clock**, so on again picks up with the
> time it had left; **a return from the full task picks the stage up where it was** (its count, its windows, its
> time left); **a light's saturation scales its CAM16-UCS chroma at a fixed hue** (COL-39), each line writing the
> light's `light_xy`; the DKL default contrast stays the set's mean radius (the PI, 2026-11-18).

> **Its page was reworked 2026-11-19** on the same branch: each setting a box with its own Apply, groups and percents, one bar, find and pins. Where this design describes the cards, their send path or the page's layout, [`2026-11-19-console-interface-design.md`](2026-11-19-console-interface-design.md) is the record; the settings, limits, forms and colors here stand.

## 1. Why

The PI played the pop-out search with the mouse as the eye (demo mode). He liked it, and asked for four changes to
how a task's settings work. His words, 2026-11-16:

1. "there should be options for how the time ranges work, eg, i want (most of the time) a nonaging foreperiod for
   the fix_hold, there should be a way for the temporal parameters to dictate whether they are a fixed value or a
   value taken from a distribution with a min and max and specific distribution shape."
2. "the task parameters screen is cluttered, it would be helpful to organize the parameters logically and perhaps
   have collapsable sections, e.g., temporal parameters, stimulus parameters, training parameters, etc."
3. "i dont understand the limits you have listed, eg, why is object_window only 0.5-2 deg? Also, for stimuli, there
   should be options to scale with eccentricity at a specific scaling factor."
4. "the free response boxes for things like object_color makes no sense to me. there should be a better way to
   define colors."

Then, on the sections mockup: "the training parameters should be in a whole different tab (like the original
mockup draft from long ago) and easily toggleable so that they can all be turned off."

Everything here follows his standing rules:
- every number a task uses is a console setting (2026-11-07);
- warnings over refusals (2026-10-11);
- no average ppd: every size and position is worked out at its own place (2026-10-19).

## 2. Goals, non-goals, anti-goals

**Goals**
- A trainer can make any timing setting fixed or drawn, mid-run, from its card.
- Ranges stop being the builder's guesses. A limit stands only where a value is impossible, and the rig warns from
  the layout actually set.
- A stimulus size can follow eccentricity by one factor, and its gaze window with it.
- Colors are picked from what the lab has made, by set, then hue, then salience. New colors can be made and kept.
- The Task parameters tab reads in sections. Training has a tab of its own, with one switch.

**Non-goals**
- No change to reward amounts, the out-of-cage clock or any welfare limit. If a part turns out to need a
  welfare-listed item (`tests/welfare_manifest.json`; `taskd.Session.set` and `link._setting` are on it), the build
  stops and asks the PI.
  - Note: `Session.set` already accepts a value outside a setting's range with warnings (XC-352's D2). So §4 is
    expected to need no listed change.
- No new task logic. Catch trials, the fixation rule and the go delay are the pop-out's, in the companion design.
- No color calibration of the Mac or any unmeasured panel. The page's swatches are approximate, and say so.

**Anti-goals** (what would make this a failure even if it works)
- A drawn value that the record does not carry, trial by trial, with what it was drawn from.
- A limit kept on a card with no reason the PI can read.
- A color picked on the page that differs from what the rig draws, with nothing saying so.
- Sections or a Training tab that hide a setting the trainer needs, or a changed setting he cannot find.

## 3. Timing settings: fixed, or drawn each trial

What exists today:
- The engine draws a setting each trial (engine build C3; TSK-21, TSK-24). The distributions are `Uniform`,
  `Weighted`, `TruncatedNormal`, `Listed` and `NonAging`.
- A draw is declared in the task file (`Task.draws`, `Block.draws`). The console can change a draw's numbers live
  (`SetRange`, `range`).
- No card can turn a fixed setting into a drawn one, or a drawn one into a fixed one.

The PI's answers (2026-11-16):
- **Every timing setting** (unit `s`) gets the switch on its card: *fixed* or *drawn*. This holds whatever the task
  file declares. It is staged until the next trial, like any change.
- **The shapes:**
  - non-aging: shortest, longest;
  - uniform: min, max;
  - normal cut to a range: mean, SD, min, max;
  - a list of values: shuffled passes, or a weight each.
- **The non-aging decay is derived from the shortest and longest** ("Derived from min and max"). He asked for it to
  rest on the literature ("can you look into the psych literature to determine what the best decay?").
  - **The rule: τ = (longest − shortest) / 3.** The search (`.superpowers/side-2026-11-17/nonaging-decay-report.md`,
    2026-11-16) found no criterion in the literature for choosing τ from a range. So this is an engineering default,
    recorded as one. Its grounds:
    - the longest wait sits at the uncut wait's 95th percentile;
    - the hazard has the same profile at every range;
    - it is inside published practice, R/τ from about 0.9 to 4.8;
    - it equals the ratio of the one study that states both a scale and a shifted range: 0.33 s over 0.4–1.4 s
      [@grabenhorst2019anticipation].
  - **For 750–1250 ms it gives:**
    - τ = 167 ms;
    - 1 draw in 20 redrawn (his "Draw again", 2026-10-30);
    - a mean of 890 ms;
    - a hazard 1.06× its start a quarter in, 1.22× at half, 1.5× at two thirds and 3.7× at nine tenths.
  - **The PI's own papers give only the range,** a "nonaging foreperiod function" of 750–1250 ms run in TEMPO
    [@westerberg2020priming; @westerberg2023feedforward]. What TEMPO drew is not recorded there (UNVERIFIED).
  - **Only catch trials keep the hazard flat to the very end.** A share of draws past the longest give no array, and
    the animal is rewarded for holding fixation. This is the literature's prescription [@los2014outlines, footnote 3],
    and its macaque form appears in [@ray2013strength].
    - Asked on 2026-11-16, the PI kept the redraw: **"Keep drawing again"**.
    - The reason: every trial stays a search trial, and the rise near the longest wait is below what an animal's
      timing resolves under the standard blur model.
  - The card shows the draw's histogram and its hazard against flat, as the mockup did.

The controller's calls:
- **A repeat draws fresh.** This follows the PI's "Follow same/fresh" (2026-10-30): "the target stays where it was and
  the wait is new". A setting switched to drawn on the console takes `FRESH`.
- **Over a block, a person's choice replaces the block's** until handed back, as a typed value does today. This
  covers a block that sets the setting, draws it, or gives it by its conditions. The card names what it overrides,
  as `_whence` does now.
- **Each trial records the value it drew.** The change row records the switch, its shape and its numbers. A revert
  takes the switch back with the rest.
- **The load checks judge a drawn timing setting at its extremes,** as they judge a range: its shortest and its
  longest.

## 4. Limits: hard only where impossible, warnings from the layout

His answer: "Hard limits only where impossible".
- **A hard limit stands only for what cannot be:**
  - a size or a time below zero;
  - a fraction outside 0 to 1;
  - a stimulus or window off the setup's field;
  - a set size past the array's places;
  - a count below one where one is needed.
- **Every other cap goes from the task files** (in wl-xtasks, and wl-xcon's reference tasks).
- **Warnings come from the layout actually set,** recomputed whenever a value changes, through the load checks the
  console already runs on a change (XC-352's D2). For the pop-out:
  - neighboring object windows overlap at this set size and ring radius;
  - a window smaller than its disc;
  - the fixation window reaching the discs (already a warning);
  - discs touching.
- **Each card says why** for any limit that stays, in one line.

## 5. Stimuli that scale with eccentricity

His answers:
- "Size = factor x eccentricity", as in his 2020 arrays: 0.3° per degree [@westerberg2020priming]; decisions.md's
  STE entry on the fixation dot's size already cites it.
- "Its gaze window" scales too.

So:
- **A size setting gets a switch like the timing one:** *fixed*, or *scaled* by a factor. Size = factor ×
  eccentricity, worked out at each object's own eccentricity, never from an average (no average ppd). Eccentricity 0
  gives size 0, so the load check warns for a scaled stimulus at or near the center.
- **Its window grows in proportion** (the PI, 2026-11-16, "Grows in proportion", answering the builder check). The
  window keeps the same ratio to its disc: a disc twice as big gets a window twice as big.
  - *The controller's reading,* for the PI to check: an object window's setting becomes **its radius as a multiple of
    its disc's radius**. The start is 3.0, today's 1.5° around a 1° disc.
  - The setting means the same whether the size is fixed or scaled.
  - The card shows the radius in degrees it gives at each object's eccentricity.
  - A ratio below 1 (a window smaller than its disc) is a warning.
- **Scaling is per stimulus definition, a card setting,** staged like any change, and recorded per trial at each
  object's realized size.

## 6. Colors

His answers:
- "I think you select a set, and then you have hue options from the set, then you have salience options for each
  hue."
- Salience is "Both, as two choices": a saturation level (gray to full, luminance held) and a luminance level
  (saturation held).
- A new color is defined by "1,2,or 3. you select an option and then enter the info":
  - a hue angle (CAM16-UCS) at the set's saturation and macaque luminance;
  - DKL azimuth and elevation around the set's gray;
  - CIE x, y, its luminance held to the set's.
- New colors are "Saved into a color set file".

So:
- **A color setting's card is three steps:**
  1. the set, from the color files a task may use (today `isohue`: blue, purple, red, green);
  2. the hue, as swatches with names;
  3. two salience levels, saturation 0–1 toward the set's apex (its gray) and luminance in cd/m², each also typeable.
- **What exists:** `ColorSet` holds each color's chromaticity, the `apex` and the set's macaque luminance.
  `ColorSetLight` takes a `fraction` and a `luminance`; the set loses chroma together where a panel cannot show it
  (`realize`).
  - Saturation is new as a per-light setting.
  - Today's `distractor_fraction` and the Fade-in staircase are a luminance salience, and keep working.
- **A new color** is made in a panel: the method, its numbers and a name, into a set (existing or new).
  - It is written as that set's file in wl-xtasks, with its numbers' source, for the PI to review and commit
    (wl-xtasks is curated with him). A rig uses it once committed and pulled.
  - DKL needs the cone fundamentals already bundled (the CIE's 2° file, sha256 f48160ed…).
  - CAM16-UCS needs its formulas (CIE 248:2022) or a library. A new dependency goes through ADR-0004's inventory; the
    builder chooses and justifies.
- **The record names a color by set, hue and both levels,** with its chromaticity and luminance as realized (the
  start row's `color_sets` already does the realized part).
- **The swatches are approximate on any panel not measured,** and the page says so. The rig's measured panel decides
  what is drawn.

## 7. The Task parameters tab in sections

His answers:
- **Sections are named by the task file** ("The task file names it"). A setting naming none goes by its unit (seconds
  go to Timing), and the rest into Other.
- **Opened as last left** ("As you last left them"), per task, in the browser's own storage, failing safe to all open.
- Each header counts its settings and how many differ from the task's start. A find box is on top.
- The pop-out's sections (the companion design names them): Timing; Gaze windows; Stimuli, as fixation point and
  array; Colors; Pairings; Special trials.

## 8. A Training tab of its own, with one switch

His answer: "the training parameters should be in a whole different tab (like the original mockup draft from long
ago) and easily toggleable so that they can all be turned off".
- The original draft is `docs/superpowers/mockups/2026-10-01-console-mockup-v13.html`. Its Training tab holds a
  Shaping switch with its bars and trial helpers.
- The tab gathers everything a task declares as training:
  - the stages' bars;
  - the staircases;
  - the pairings' widening and the suggestions;
  - and today's Runtime-tab Training panel (pop-out build, Task 7).
- **One switch, three positions** (his "both, a freeze training option and a full task option"):
  - **on:** training as now.
  - **frozen:** the stage, the staircase levels and the pairings stay exactly as they are. There are no moves, no
    suggestions and no staircase steps until it is on again. Each frozen value shows on its card.
  - **full task:** the task's finished version, which the task declares (for the pop-out: the last stage at its
    hardest, every pairing; the companion design says).
- A change of the switch is staged to the next trial, recorded as a change row, and revertible.

## 9. The record and wl-preproc

wl-preproc reads our session records into NWB. Before anything here ships, it is told the new shapes and accepts
them, as with XC-491 and XC-502:
- a drawn or switched timing setting;
- a scaled size and window;
- a color by set, hue and levels;
- the training switch.

The ask is written before the build that writes them, by message to its session.

## 10. Left to the builder

- Every name and wire shape. The command for the switches may extend `SetRange` or be new.
- How the card draws the histogram and hazard.
- How a section is declared in a task file.
- How "full task" is declared.
- The CAM16-UCS route, under the dependency policy.
- The order of the work, as tasks in one plan.

## 11. References

- [@westerberg2020priming]: items scaled at 0.3 dva per dva; the 750–1250 ms non-aging foreperiod.
- [@han2022revisiting]: what a non-aging foreperiod keeps constant.
- [@grabenhorst2019anticipation]: an exponential with scale 0.33 s over 0.4–1.4 s, R/τ = 3.0.
- [@los2014outlines] (footnote 3) and [@ray2013strength]: catch trials keep the hazard constant to the last moment.
- The literature search's BibTeX entries (in its report, §7) go into `docs/references/library.bib` with the build,
  and the rule goes into decisions.md (TSK-15's revision) as an engineering default.
