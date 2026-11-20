# The pop-out search, revised after the demo try-out: the fixation rule, the go delay, special trials

**Status:** Approved by the PI on 2026-11-16, asked in the UI: 'Approve both'. Brainstormed with him that day.
- It revises the pop-out search task, `wl-xtasks/tasks/popout_search.py`, whose design is
  [2026-11-07-popout-search-design.md](2026-11-07-popout-search-design.md).
- It uses [the console settings design](2026-11-16-console-settings-design.md): timing switches, hard limits,
  scaling, colors, sections and the Training tab.
- wl-xtasks is curated with the PI, so the task's change is reviewed with him.

> **Built 2026-11-19** on `console-build-2026-11-17` (the plan's Tasks 1 to 7, with 5b; wl-xtasks `popout-revision-2026-11-16`), not merged. wl-preproc accepted its record shapes the same day with two changes (a trial line's `trial_kind`; an array with no target writes `target: null` and its `odd_place`), see [pending-wl-preproc-amendments.md](../../pending-wl-preproc-amendments.md). Where the build and this text differ, the plan's amendments and `decisions.md` (TSK-78 to TSK-80) rule.

## 1. Why

Trying the pop-out with the mouse, the PI asked for catch trials:

> "there should be a catch trial percentage (how often a trial where no target appears ant the monkey must maintain
> fix at center) with a catch hold time for reward."

Answering how a catch trial looks, he set a rule for every task:

> "I dont think that fixation should disappear when array appears. as a general rule for tasks, we should have a fix
> color that indicates that the monkey should be looking at fixation, eg, a gray fix dot. then when the monkey should
> "act" (or in the case of a catch, maintain fix), the fix dot changes in some way, eg, changes color or shape or
> hollows out."

And on the go cue:

> "in this task, option 1 [array on and dot changes together], however, if we were to make a "delayed-saccade"
> version of the task instead of the "RT" version, we would delay the changing of the fix dot until after the array
> appears. perhaps for the sake of the flexibility of this task, we can have the period. so that if you want an RT
> version, you can have it, and if you want a delayed version, you can have that. the measure of the RT is should
> then be linked to when the animal is cued to "act", so when the fix dot changes."

## 2. The fixation rule (the PI's, for every task)

- **The fixation point has two looks:** *hold* ("keep looking here") and *act* ("act now", or on a catch, "keep
  holding"). Both are settings on the console: shape, size, color and luminance.
- **It stays on when the stimuli appear.** It is never hidden as a go cue.
- **For the pop-out, the act look is the hold look hollowed out** ("Hollows out"): a filled gray dot becomes a gray
  ring of the same size.
- **This is the lab's rule for tasks to come.** It goes into decisions.md as the PI's decision, and into wl-xtasks'
  guidance for task authors. A load-time warning for a task that hides its fixation point at its go is the builder's
  call.

## 3. The trial, revised

1. **between:** blank, `inter_trial`.
2. **await_fix:** the dot on, in its hold look, until gaze enters its window (an eye already there has entered it,
   EYE-30), or `fix_acquisition` runs out (`NO_FIXATION`).
3. **hold_fix:** `fix_hold`, by default drawn non-aging. Leaving is an early break.
4. **The array appears.** The dot stays, in its hold look.
5. **After `go_delay` the dot takes its act look: the go.**
   - `go_delay` is 0 by default: the reaction-time version, with the array and the change on one frame.
   - Above 0 is the delayed-saccade version. During the delay, leaving the fixation window is an early saccade.
   - `go_delay` is a timing setting like any other, so it can be drawn.
6. **Reaction time runs from the go** (the dot's change), never from the array's onset. A mark for the go is recorded
   on the frame the change is drawn (photodiode-confirmed where the task patch toggles). The answer's saccade and its
   landing are scored as today.
7. Correct, wrong and timeout follow as today.

The fixed 0.3 s landing bound (`After(0.3)` in `flight`) and the other fixed bounds in the task file become settings,
unless the PI fixed one on purpose. This is the controller's call, under "every number adjustable"; the builder lists
each one with its source.

## 4. Special trials

His answers: four kinds, "A percentage per kind", one shared `catch_hold`, the same dot change ("1, same change"),
and errors "An error, counted".

| Kind | What appears at the go | The right answer |
|---|---|---|
| **target absent** | the array, all in the distractor color (no odd one) | keep looking at the dot for `catch_hold` |
| **odd one's place empty** | every distractor, and the odd one's place empty ("Odd one's place left empty") | keep looking for `catch_hold` |
| **distractor alone** | one disc in the distractor color ("Either, as two kinds") | keep looking for `catch_hold` |
| **odd one alone** | only the odd one (a probe) | look at it, scored as a normal trial |

- **Each kind has its own percentage of trials,** 0 by default, in a *Special trials* section. Each is a setting.
  `catch_hold` is a timing setting, so it can be drawn.
- **On a catch, the dot hollows out exactly as at a normal go.** Holding gaze in the fixation window for `catch_hold`
  after the go is correct and rewarded (the task's reward, its amount bounded as every reward is). Looking away
  before then is an error, with the usual timeout.
- **Counted in the bars, not on the staircase.** Catch trials and probes count in the stage's bars, to move up and
  back, like any other trial ("An error, counted").
  - **Only normal search trials step the Fade-in and Crowd staircases** (the PI, 2026-11-16, "Only normal trials move
    it", answering the builder check). The staircase then keeps tracking about 79% right on search itself
    [@levitt1971transformed].
  - A special trial moves nothing on it: it neither adds to a run nor breaks one, as `Staircase` already allows.
  - Each trial's record says whether it stepped.
- **Which trials are special** is drawn per trial from the percentages, between trials, keyed by the run's seed.
- **A special trial otherwise follows the open stage:**
  - the pairing is drawn from the pool, and its colors give the distractor color;
  - the set size comes from the stage's staircase;
  - a repeat of a special trial is the same kind (the controller's call).
- **The percentages add to at most 100.** More is a load warning naming the sum, and the rest are normal trials.
- **The record names each trial's kind,** and the marks carry it. New event codes for the go, for a catch's held
  fixation and for its break go through the allocation with wl-preproc (ADR-0007).

## 5. The pop-out's sections and its full task

- **Task parameters sections:** Timing; Gaze windows; Stimuli (fixation point; array); Colors; Pairings; Special
  trials.
- **The Training tab** holds the stage bars, the staircases, the pairings' widening and the suggestions.
- **"Full task"** (the console design, §8): the Crowd stage at its hardest, with all 12 discs, distractors at full and
  every pairing. This is the controller's reading; the PI checks it.

## 6. Starting values (the controller's calls, each a setting)

- `fix_hold`: drawn non-aging, 0.75–1.25 s, the PI's published foreperiod [@westerberg2020priming].
- `go_delay`: 0 s.
- `catch_hold`: 0.5 s.
- Every special-trial percentage: 0.
- Disc size: fixed, as today. Scaling is there to switch on.

## 7. The record and wl-preproc

wl-preproc is asked, before the build writes anything, to accept:
- the trial's kind;
- the go mark and its time;
- reaction time measured from it;
- the fixation point's two looks;
- `go_delay`.

## 8. Found by the builder check

The engine refuses, at load, an array whose target looks like its distractors (`Array.found_by="look"`, the PI's rule
of 2026-10-31, `check.impossible`). The target-absent catch is exactly such an array. The check must become
catch-aware: it still refuses a normal trial whose target cannot be told apart, and it accepts a declared catch kind.

## 9. Left to the builder

- How the task file says the special kinds; the engine may need an array with a place left empty.
- The new marks' names.
- The fixed bounds listed in §3, each with its source.
