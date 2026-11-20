# Pop-out Revision Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **The PI's process rule of 2026-11-07 governs:** "a plan is a design and a list of tests, built once"; one review of the whole build, plus his welfare review of any welfare-listed change. None is planned (Global Constraints); a task that finds it needs one stops there. No per-task review loop.

**Goal:** The pop-out search keeps its fixation point on through the trial, in a *hold* look until the go and an *act* look from it; the go may follow the array after a delay (`go_delay`, 0 for the reaction-time version, on one frame with the array); reaction time runs from the go. Four kinds of special trial (three catches and a probe) are drawn each trial at their own percentages, counted in the stage's bars and never stepping a staircase. Every bound the task file fixed becomes a setting, and the record and wl-preproc carry all of it.

**Architecture:** A special kind is a trial structure of its own, declared with its share (`task.Special`, `Task.specials`), and drawn between trials from the run's seed in place of the task's default structure; the stage, the staircase's value and the pairing apply as they would to a normal trial, and only the staircase's step is skipped. A catch's array declares it has no target (`Array.found_by="none"`), which is what makes the impossibility check catch-aware; the odd one's empty place is a `Blank` object in an array. The go is an `Update` of the fixation point to its act look; a zero wait passes on the frame its state is entered (run.py), so `go_delay` 0 puts the array and the change on one frame. The fixation point's looks are appearance settings with starts among their choices, colored through the console's color card at saturation 0.

**Tech Stack:** Python 3.11-3.13, the `wl_xcon` package, pytest (+ xdist, Playwright Chromium and WebKit), wl-xtasks' task file. **No new dependency.**

**Spec:** `docs/superpowers/specs/2026-11-16-popout-revision-design.md`, approved by the PI on 2026-11-16, asked in the UI: "Approve both". Section numbers below are its. It revises `docs/superpowers/specs/2026-11-07-popout-search-design.md`. Its companion's plan, `docs/superpowers/plans/2026-11-16-console-settings.md` ("the console plan"), is built first; this build branches from its head after its whole-build review and builds on its interfaces by their names there (the seam, below).

**The PI on this plan** (2026-11-16, asked in the UI): in Alone, a lone distractor at the run's distractor brightness, as planned ("The run's distractor brightness"); the blink and tracker-loss graces become settings ("Yes, a setting", Task 7); built the same way, after the console settings build ("Yes, the same way").


## Reading the design against the code (`f417ceb`)

- **The loop takes one edge a frame.** `run._Loop.frame` breaks after `_take`, so a state whose wait is 0 lasts one frame today: an array shown on entering a delay state of `go_delay` 0 and the dot's change on leaving it would be a frame apart. §3 item 5 asks for one frame, hence Task 2.
- **`Exited` is an edge** (`was_inside` and not `inside_now`) and EYE-30 kept it so. An eye that leaves on the frame a delay ends must therefore be taken by the delay state's `Exited`, listed first, or the go state never sees it leave and waits for its deadline. Task 7 orders the delay state's edges for it, and Review Focus 3 pins it.
- **What already exists for a catch:** `Outcome.CORRECT_REJECT` (in `RIGHT` and `ANSWERS`) and `Outcome.FALSE_ALARM` (in `ANSWERS`), with reason codes 4123 and 4124 already allocated. A false alarm is an answer the bars count wrong (`staircase_verdict` gives `False`), which is the PI's "An error, counted"; `CATCH_BREAK` is no answer and would count nowhere.
- **Structures are per condition already** (`Condition.structure`); `ReactionTime` and `Choice` are judged task-wide ("some structure has"), so a catch structure needs neither `flight` nor object windows.
- **The staircase both gives and steps** under one flag in `Session.run` (`stepping`); a special trial needs the first without the second. `went_on` replays a stopped run's staircase from its lines and must skip the same trials.
- **`screen._items` draws every object of an array**, and `as_look` draws no `Blank`; `record._stimuli` writes `drawn` per stimulus, not per object.
- **`Param.start` refuses an appearance** "until telemetry publishes one (XC-420)". The console plan's Task 7 closes XC-420 for telemetry but leaves that refusal; the looks need starts among their choices (Task 5).
- **The fixed bounds, with their sources** (decisions.md TSK-74 and TSK-75, read 2026-11-16):

| In the task file | Bounds | Source | Here |
|---|---|---|---|
| `After(10.0)` in `hold_fix`, to `NO_FIXATION` | a hold the tracker's stalls keep from completing | the controller's, the fix round (TSK-75: "bounds on the engine's own waits") | `fix_hold_limit`, 10.0 s |
| `After(3.0)` in `on_target`, to `NO_RESPONSE` | the target hold, likewise | the controller's (TSK-75) | `target_hold_limit`, 3.0 s |
| `After(0.3)` in `flight`, to `astray` | a saccade's landing | the builder's (TSK-74 (d): "an engineering bound"), kept by TSK-75 | `landing_limit`, 0.3 s; XC-505's warning reads it once built |
| (new) the catch's go state | the catch hold, as `on_target`'s | this plan's | `catch_hold_limit`, 3.0 s |
| `(0.0, 0.0)` for the point, the ring and the window | the center | the controller's (TSK-75) | kept: not a bound; every place is about it, and the console plan measures eccentricity from straight ahead |
| `Steps(..., 1.0, ...)`, `Steps(..., 12, ...)` | each staircase's hardest end | the PI's stages (the first design §3.3: the distractors at full; "from 4 up to 12"); kept by TSK-75 | kept, with its reason |
| `Uniform(0.0, 360.0, repeat=SAME)` | the ring's direction | the builder's (TSK-74 (b)), kept whole by TSK-75 so the place is random | kept, with its reason |
| `target=1` on each condition; `Array(target=0)` | a stage's minimum; the odd one's index | the builder's (TSK-75; TSK-74 (b)) | kept: structure, no number a trainer tunes |
| `{"set_size": 1}`, `{"set_size": 4}`, `{"distractor_fraction": 1.0}` | the stages' own values | the PI's (the first design §3.3) | kept: conditions' values a person's live value overrides |
| `n=1` in the two lone kinds' arrays (new) | the kinds' definition | the PI's table (§4) | fixed, with its reason |
| `Tolerances()`, blink 0 and tracker lost 0.05 s | not in the file: the engine's defaults | S5; the tracker's a placeholder until V3(a) | settings: `blink_grace` 0 s and `tracker_lost_grace` 0.05 s, section Timing (the PI, 2026-11-16, asked in the UI: "Yes, a setting"); Task 7 |

## Global Constraints

- **CLAUDE.md binds every task.** US English. Sim first. No timing claim without a measurement under `docs/measurements/`: nothing here states a latency, and the go's photodiode confirmation is build E's. Each new test is seen failing first, then by a hand break after the fix. Docs stay in sync in the same commit (architecture.md's task model, decisions.md's entries). The full suite runs in each commit's `&&` chain, with `set -o pipefail` and the log written to a file. Never run the suite, edit a test or `git add` while a mutation sweep is in flight.
- **No welfare-listed item changes** (`tests/welfare_manifest.json`; `python3 tools/welfare_diff.py BASE HEAD` at every commit, its output read: every item `SAME`, no `CHECK CHANGED`; `BASE` the build branch's base).
  - `taskd.Session.set`, `_command`'s two listed items, `_hold`, `_ends`, `_schedule`, `_manual_reward`, `OUTSIDE_A_RUN` and `link._setting` are not touched. The percentages are ordinary settings set through `set`. No new command.
  - **A catch's reward is the task's ordinary reward**: `Reward("reward_correct")`, its amount the animal's limits file's and bounded as every reward is, one a trial. `welfare.py`, `bounds.py` and `marks.py` read no outcome (read 2026-11-16), so a reward on `CORRECT_REJECT` is accounted as one on `CORRECT`.
  - `run.py` is not listed; Task 2 changes when a zero wait's edge is taken, never what it emits.
  - A task that finds it needs a listed change stops, and the controller asks the PI with the exact change.
- **Hot path.** A special trial's kind is drawn between trials from `variation.unit(seed, trial, "special trial", 0)`, never in a frame. Task 2's pass is read from a table `_Loop` builds between trials; a frame that takes it allocates nothing.
- **Warnings over refusals** (2026-10-11). Refused: a special declared wrong (as built, or `bad-special`); a catch array scored by a saccade to its target (`bad-array`); a combination no animal can answer (TSK-69's `impossible-trial`, now judged on each special structure too, and so on a hold a bound now set beats on some trial). Warned: percentages over 100; a fixation point hidden at the go.
- **Each fixed number has its reason** (TSK-75): the table above, each reason beside its number in the task file.
- **The record.** Every new shape is told to wl-preproc before it is written: Task 1 comes before Tasks 3, 4 and 7. Telemetry is unchanged (schema 22, the console plan's).
- **wl-xtasks is curated with the PI.** Task 7 is a wl-xtasks branch, `popout-revision-2026-11-16`, from the console plan's `console-settings-2026-11-16`, merged only after he reviews it. Dates are the local day (US Eastern).

## Review Focus

1. **A crash after special trials.** A run with catches stops; the next goes on from it (`went_on`). Its staircase is at the level the stopped run had reached, the special lines having stepped nothing, and its bars hold them (Task 3).
2. **A repeat of a special trial, and a share changed while one waits.** An early saccade on a target-absent catch brings back a target-absent catch, under drumming too, even after its percentage is set to 0; the next fresh trial follows the new percentages (Task 3).
3. **The go's own frame.** With `go_delay` 0.5, an eye leaving the fixation window on the frame the delay ends is an early saccade with the timeout, never a go state waiting out its deadline. With `go_delay` 0, the array and the act look are drawn on one frame, and an eye leaving on the next is the answer (Tasks 2 and 7).
4. **A special kind where it degenerates.** In Alone, *odd one's place empty* shows the fixation point alone and *target absent* one disc in the distractor color. Each runs, is held for its reward, and records its kind (Task 7).
5. **A drawn hold past its bound.** `fix_hold` drawn non-aging up to 12 s against `fix_hold_limit` 10 s gives some trials no time to answer: refused with a sentence naming both, nothing staged, the session running on. Up to 9.9 s it is accepted, and so is `fix_hold_limit` raised to 13 s first (Task 4).

## The seam with the console plan

- **Used here by its names there:**
  - `NonAging.between` (the `fix_hold` draw) and the timing switch, which makes `go_delay`, `catch_hold` and the four bounds drawable with no work here;
  - `Param.section` and `Param.why` (the *Special trials* section, a percentage's limit);
  - the hard-limit rule, `check.LAYOUT`, `check.laid_out` and `Session._laid_out` (the sum warning, judged at the values set);
  - `task.FullTask` and `Plan.full` (the pop-out's full task);
  - `ColorSetLight.saturation`, `task.color_choices` and the color card (the fixation point's colors);
  - `ObjectWindows.scale` (the windows of the search and the probe);
  - XC-513's record shapes (form rows; `saturation` on a light).
- **Added to them here, as the console plan's Task 6 adds `scaled-small`:** `check.LAYOUT` gains `"specials-over-100"`, a sum and no layout, since it is the set judged at the values (Task 4); `check.impossible` gains `specials=` beside the console plan's `forms=` (Task 4).
- **Not planned here, said in this plan's report:** the console plan's desaturation check reads a set at each luminance a light names, not at the light's saturation, so a fixation point at saturation 0 (the set's gray) at 40 cd/m² would be warned `color-set-desaturated`. Task 7's load test expects no new warning, and so needs that check to read each light at its own saturation, in the console plan's Task 7.

## Amendments, 2026-11-19: built on `console-build-2026-11-17`, before it merges

The PI, 2026-11-19, after choosing the settings tabs' summary-and-editor layout: "also build out the rest of the task
parameters before you ask me for more input". So this plan is built on branch `console-build-2026-11-17` after the
console interface rework (`docs/superpowers/plans/2026-11-19-console-interface.md`) and the summary-and-editor
layout (`docs/superpowers/plans/2026-11-19-params-summary-editor.md`), before the branch merges; the PI is asked
nothing until it is built and reviewed (a question goes to `.superpowers/questions-for-pi.md`; a welfare-listed
change still stops for him). Where this plan and the code have moved apart, these amendments rule:

1. **Base and branches.** wl-xcon: this branch at the layout build's head. wl-xtasks: `popout-revision-2026-11-16`
   from `console-settings-2026-11-16` at `c30ca28` (the PI's label review built in), committed only there.
2. **Telemetry is at schema 23** (the rework), not 22. This plan adds no telemetry field; a task that finds it needs
   one stops and reports it.
3. **The backlog's numbers**: take "Next free" from `docs/backlog.md` as it stands (XC-543 at this writing), not 516.
   XC-514 is this plan's existing line if present; otherwise Task 1 files the ask's line from Next free. Task 1 first
   checks codes 4139-4145 are still unallocated in `tasks/allocation.py` and in wl-preproc's frozen layer; if any is
   taken, it takes the next free run and says so in the ask.
4. **Special trials are one group** (the console interface design's goal 8; the PI, 2026-11-19, "One box after
   Timing"; closes XC-534): Task 7 declares `task.Group("Special trials", (the four shares, catch_hold), sentence)`,
   its section `Special trials` placed right after Timing in the declared order, each share `whole=True` (unit
   `"percent"`, 0 to 100, starts 0). Its sentence reads, with the fields in place: "Of every 100 trials:
   {target_absent_percent} target absent, {odd_place_empty_percent} odd place empty, {distractor_alone_percent} a
   distractor alone, {odd_one_alone_percent} the odd one alone; a catch is held {catch_hold}". **The remainder** is
   said after the sentence as "N normal search" (the design's goal 8): rendered in Python from the values in force
   (100 minus the shares' sum, "none" at or past 100 with the `specials-over-100` warning's words), and updated by
   the page from the group's own fields while a draft is open (a small change in `web._group_box` and the script,
   Task 7's wl-xcon side, with its test `test_the_special_trials_line_says_the_rest_are_normal_search`).
5. **Every new setting has a plain name (at most 40 characters) and a one-sentence help (at most 120)**, in the voice
   the PI approved for the pop-out's first 30 (`.superpowers/sdd/2026-11-19-console-interface/task-9-report.md`'s
   table); counts and shares `whole=True`; the fixation point's luminances and the graces in their own units.
   Task 7's report tables them for the PI's review of the wl-xtasks branch.
6. **The summary must still fit**: the layout build's `test_every_popout_line_is_above_the_fold_at_1280x800` keeps
   passing with the revision's settings (about 45 lines). If it cannot, Task 7 stops and reports the count and the
   space; the controller rules (fold the fixation point's two looks into one group line each, or move the bounds
   into a subsection shown as one line).
7. **The seam note is done**: the desaturation check reads each light at its own saturation since the console
   settings build's fix wave (`f8a4071`, Task 7's seam defect 1); saturation is CAM16-UCS chroma (the PI,
   2026-11-18, COL-39), and saturation 0 is still the set's apex at that lightness, so
   `test_the_fixation_point_at_saturation_0_is_todays_gray` stands. Each fixation point entry carries `light_xy`
   (XC-513, accepted).
8. **The PI's review of the wl-xtasks branch** (labels, sentences, the meanings) is asked with the rest, after the
   whole-build review, not before.

9. **A look's shape is a console setting, so Task 5b is added** (Task 5's finding, 2026-11-19: the design's §2 makes
   each look's shape a console setting, but a live pick of a choice goes only through `SetColor`, which takes a color-set
   light, and `link._setting` takes numbers and words, welfare-listed). Between Tasks 5 and 6:

   **Task 5b: Pick any declared choice on its box.** `link.SetChoice(name, choice, by, cid=None)`, wire kind `"choice"`:
   `choice` is the choice's words exactly as `ParamRow.choices` gives them (text of 1 to `TEXT_LIMIT` characters,
   decoded by its own decoder as `SetColor`'s are, never `link._setting`); the session sets the one declared choice whose
   words those are through `Session.set` unchanged, from the next trial, recorded as any value set is (no new record
   shape; wl-preproc is told the new wire command in Task 8, as a note). Its branch sits beside `SetColor`'s in
   `_command`, outside the listed lines; it joins `link.APPLY_KINDS` and `taskd._BOX`, so Apply all and withdraw take
   it. The page: a setting whose choices are words and not all color-set lights shows them as segments (a draft until
   Apply, as a swatch is), its summary line the chosen choice's words. Tests: `test_a_choice_is_picked_by_its_words_and
   _recorded_as_a_value_set`, `test_a_word_naming_no_choice_is_refused_with_the_choices_named`,
   `test_a_choice_pick_rides_apply_all_and_withdraws`, and a browser test in Chromium and WebKit
   `test_a_looks_shape_is_picked_on_its_box_and_applied`. welfare_diff all SAME.

---

### Task 1: Tell wl-preproc the new record shapes and allocate the codes, before any is written (§7)

**Files:** Modify `docs/pending-wl-preproc-amendments.md` (a dated section, `# OPEN — the pop-out's revision: each trial's kind, whether it stepped, the go, and seven codes (new, 2026-11-16)`, in the shape of XC-491's), `tasks/allocation.py`, `docs/backlog.md` (XC-514 in the waiting-on-another-repository section; Next free stays 516: XC-513 is the console plan's Task 1, and main took XC-515 at demo mode's merge, 89f7b94); Test `tests/test_allocation_codes.py`.
**Interfaces (the codes, wl-xtasks' to own, held in `tasks/allocation.py` until it publishes one, ADR-0007):**

| Code | Name | Strobed |
|---|---|---|
| 4139 | `GO_CUE` | the frame the fixation point takes its act look is decided, drawn on the next flip (`run._emit`), normal and catch alike |
| 4140 | `CATCH_FIXATION_HELD` | a catch's `catch_hold` completes, before `OUTCOME_CORRECT_REJECT` and `REWARD_COMMANDED` |
| 4141 | `CATCH_FIXATION_BREAK` | gaze leaves the fixation window on a catch after the go, before `TIMEOUT_ON` |
| 4142 | `SPECIAL_TARGET_ABSENT` | on the array's frame, after `ARRAY_ON` |
| 4143 | `SPECIAL_ODD_PLACE_EMPTY` | likewise |
| 4144 | `SPECIAL_DISTRACTOR_ALONE` | likewise |
| 4145 | `SPECIAL_ODD_ONE_ALONE` | likewise |

**The ask, exactly:**
1. **Each trial line gains `kind` and `stepped`**, always written.
   - `kind`: `"normal"` or a special kind's name (`"target_absent"`, `"odd_place_empty"`, `"distractor_alone"`, `"odd_one_alone"`) for a task declaring special trials; `null` for one declaring none. The line's `structure` names the structure it played.
   - `stepped`: `true` where the trial's outcome counted on its block's staircase (a success or a failure, TSK-33, on a trial whose value the staircase gave); `false` where it moved nothing on it (a special trial, a value a person held, or an outcome that is neither, an early saccade among them); `null` where the block has none. A level's move is read from the next line's `params`, as today.
   - On a lone kind the line's `set_size` is the stage's value, which its array does not read; the objects drawn are its `stimuli` entry's.
2. **The start row gains `specials`**: `{"target_absent": {"share": "target_absent_percent", "structure": "target_absent"}, ...}` in declared order, or `null`. Each trial's percentages are in its `params`.
3. **An array entry of `stimuli[]` gains `found_by`** (`"look"`, `"cue"` or `"none"`), and **each `objects[]` entry gains `drawn`**, false for a place left empty (beside XC-513's `size_deg` and `window_deg`). An array found by `"none"` has no target; its `target` is the index declared, the place an odd one would hold.
4. **The fixation point's two looks** add no key. They are settings in `params`: `fix_look` and `fix_act_look`, appearances in REC-27's form; `fix_color` and `fix_act_color`, color-set lights with XC-513's `saturation`. The go is the `fix` entry of kind `"update"`, `changed: ["looks"]`, at the go's frame.
5. **`go_delay`** is a setting in `params`, and drawn, in `drawn` as any form (XC-513).
6. **The go and reaction time.** The task's reaction time runs from `GO_CUE` to `SACCADE_ONSET` (4098), no longer from `ARRAY_ON` (4103); with `go_delay` 0 the two are on one frame. Where a reader derives one, it starts at `GO_CUE`.
7. **Two outcomes this task now reaches**, both already in the frozen layer: `correct_reject`, a catch held; `false_alarm`, a catch broken (reasons 4123, 4124).
8. **Told, not asked:** a state whose wait is 0 now lasts no frame (Task 2), so a trial with a zero `timeout` ends on the frame of its error, one frame sooner than before.

**Deliberately not asked:** the new warning codes (`specials-over-100`, `fixation-hidden-at-go`), which are values in `warnings.jsonl`; the new settings' names, which are values in `params`.
- [ ] **Step 1: failing test** `test_the_revisions_seven_codes_are_allocated_by_name_and_new`: the table's names at its numbers, each in 4096-32767, and every code the allocation held before (4096-4138, listed in the test) unchanged.
- [ ] **Steps 2-4:** run (it fails), write the codes with a comment each, the ask and XC-514's line; `tests/test_backlog.py` and the full suite pass; commit. The controller sends the ask by message to wl-preproc's session. Tasks 3, 4 and 7 write their shapes only after it is sent, and are rebuilt to any rename it answers.

### Task 2: A zero wait lasts no frame (§3 item 5)

**Files:** Modify `wl_xcon/run.py` (`_Loop.__init__`, `_Loop._take`), `docs/superpowers/specs/2026-10-07-engine-design.md` (§5, a dated note), `docs/references/decisions.md` (TSK-78), `docs/design/architecture.md` (the task model); Test `tests/test_run.py`.
**Interfaces:**
- **The rule** (TSK-78, the builder's, from the PI's "on one frame"): when an edge enters a state whose go list holds a plain `After` (no `since`) whose seconds resolve to 0 or less, that edge is taken on the same frame. Its actions are applied at the same `frame + 1`, after the entering edge's and the state's `enter`. No other edge of the state is judged, the state having lasted no frame. It still appears in `Result.visited`, and the world is told the next state's first frame.
- **At most one pass a frame**: the state a pass enters is judged from the next frame, so a cycle of zero waits ends on the longest trial, never loops in a frame.
- The start state is entered by no edge and is judged from frame 1 as today.
- `_Loop.passes: dict[str, On | None]`, built in `__init__` from the trial's values for every state (the first such edge, else `None`); `_take` reads it by index. A frame that takes a pass allocates nothing.
- [ ] **Step 1: failing tests** in `tests/test_run.py`:
  - `test_a_zero_wait_is_passed_on_the_frame_its_state_is_entered`: a Show on entering `delay` and an Update on leaving it, `go_delay` 0. Both `Placed` entries have one frame, and `visited` holds `delay`.
  - `test_a_wait_above_zero_counts_from_the_next_frame_as_before`: `go_delay` 0.05 at 240 Hz leaves on frame entered + 12.
  - `test_a_zero_wait_listed_after_a_gaze_edge_still_passes`.
  - `test_two_zero_waits_in_a_row_take_one_frame_between_them`.
  - `test_a_cycle_of_zero_waits_ends_on_the_longest_trial`.
  - `test_a_zero_timeout_ends_the_trial_on_the_frame_of_its_error`.
  - `test_a_frame_that_passes_a_zero_wait_allocates_nothing` (the measurement `tests/test_gaze.py` uses).
  - `test_every_reference_tasks_outcomes_are_unchanged_at_their_starts`: the hazard `Subject` at two seeds, 600 trials each. The counts equal those the builder records at the branch's base in the test itself, with the commit.
- [ ] **Steps 2-4:** run (each fails for its reason). Implement and pass. Hand breaks: judge the pass on the next frame; let a pass chain twice. Each existing test pinning a one-frame zero state is rewritten to the rule in this commit, none deleted without its replacement. Then the full suite, `welfare_diff` all `SAME`, commit.

### Task 3: Special trials: declared, drawn, counted in the bars, kept off the staircase (§4)

**Files:** Modify `wl_xcon/task.py`, `wl_xcon/check.py`, `wl_xcon/taskd.py` (`Session.run`, `_Climb.step`, `went_on`, a new `_special`), `wl_xcon/record.py`, `wl_xcon/review.py`, `tests/test_declarations.py` (`DEFAULTS`), `docs/references/decisions.md` (TSK-80), `docs/design/architecture.md`; Test `tests/test_specials.py` (a fixture task: a ring search with a staircase on `set_size`, a pool, and two specials), `tests/test_review.py`, `tests/test_record.py`.
**Interfaces:**
- **The declaration.**
  - `task.Special(kind: str, share: P, structure: str)`, frozen. It is refused as built for a kind not printable text of 1 to 40 characters, a kind of `task.NORMAL`, a `share` that is not a `P`, or an empty `structure`.
  - `task.NORMAL = "normal"`; `task.SPECIAL_UNIT = "percent"`.
  - `Task.specials: tuple = ()`. It is refused as built for anything but `Special`s, or for two of one kind or one structure. At its default it leaves every task's hash as it was (`declarations.canonical`).
- **The load** (`check.check_task`):
  - `bad-special`, refused: a structure the task lacks or its default; a share naming no declared setting of unit `"percent"` bounded 0 to 100.
  - `specials-over-100`, a warning accepted in every kind: the shares at the task's starts add past 100. The sentence names the sum and each share, and says each kind is then drawn in proportion to its percentage and no trial is normal. (The builder's call, ruled in the report.)
- **The draw.** `Session._special(task: Task, draw: Draw) -> Special | None`, between trials, beside `_pairing`.
  - On a repeat it gives the special of the trial it repeats (`_specials`, kept while a repeat waits and pruned with `_paired`).
  - Otherwise a fresh trial takes `share = variation.unit(seed, draw.number, "special trial", 0)` against the shares in `spec.values`, cumulated in declared order and divided by 100, or by their sum past 100. `None` is a normal trial. A share that is no number counts 0.
  - **Only a trial of the task's default structure** (its condition names none, or names the default) can be special. A condition naming another structure plays it as named.
- **The trial.** `structure = special.structure` for a special. Draws, the condition's values, the staircase's value and the pairing apply as to any trial.
  - The staircase **gives** its value as before (`giving`, the old `stepping`). It **steps** only a normal trial: `stepping = giving and special is None`.
  - `hardest = _at_hardest(climb, None if giving else values)`: a special trial at the staircase's last level counts toward moving up, as any trial does (§4, "like any other trial").
  - `scheduler.record` is called for it unchanged, so the bars and the condition count it.
- `_Climb.step(outcome, shown) -> bool`: whether the trial counted on it (a success or a failure). That bool is the line's `stepped`.
- **The record:** `record.trial(..., kind=..., stepped=...)` and the start row's `specials` (Task 1).
- **`went_on`** steps its replayed staircase only on a line whose `kind` is `"normal"`, or which has none (written before this build).
- `review.render` lists each special kind: its share setting, its value, its structure.
- [ ] **Step 1: failing tests** in `tests/test_specials.py`:
  - `test_a_special_declared_wrong_is_refused_as_built_or_at_load`: each case above.
  - `test_the_shares_draw_each_kind_near_its_percentage`: 10% and 20% over 2,000 simulated trials, each within 3 points; at 0, none.
  - `test_the_draw_is_the_runs_seeds_and_the_same_seed_draws_the_same_kinds`.
  - `test_a_special_trial_takes_the_stage_the_staircases_value_and_a_pairing`.
  - `test_a_special_trial_steps_no_staircase_and_counts_in_the_bars`: in a run of three right normal trials, catches between them neither add to the run nor break it. The level steps after the third normal success, and the bar's count includes the catches.
  - `test_each_line_says_its_kind_and_whether_it_stepped`: normal, special, early, held and no staircase.
  - `test_a_repeat_and_a_drum_keep_the_special_kind` (Review Focus 2): its share set to 0 while the repeat waits.
  - `test_a_condition_naming_another_structure_is_never_special`.
  - `test_shares_past_100_are_drawn_in_proportion_and_warned_at_load`.
  - `test_a_stopped_run_with_specials_goes_on_at_its_staircases_level` (Review Focus 1).
  - `test_the_start_row_names_each_special`; `test_the_review_lists_each_special_kind`.
  - `test_no_draw_or_record_of_a_special_runs_in_a_frame`: `_special` is patched to count calls during frames, and counts none.
- [ ] **Steps 2-4:** as Task 2's. Hand breaks: step the staircase on a special; draw a repeat fresh; let `went_on` step a special line. `welfare_diff` all `SAME`. Commit.
- **TSK-80** (decisions.md): the PI's four kinds, "A percentage per kind", one `catch_hold`, "1, same change", "An error, counted", "Only normal trials move it" [@levitt1971transformed]. Separately, the controller's calls: a repeat is the same kind; past 100, in proportion; the default structure only; a special at the hardest step counts toward moving up.

### Task 4: Arrays with no target, places left empty, and the checks that read them (§8; §3's bounds)

**Files:** Modify `wl_xcon/task.py` (`FOUND_BY`, `Array`), `wl_xcon/check.py`, `wl_xcon/screen.py` (`_items`), `wl_xcon/record.py` (`_stimuli`), `wl_xcon/demoscreen.py`, `wl_xcon/taskd.py` (`_possible`'s call), `docs/references/decisions.md` (TSK-69 revised); Test `tests/test_impossible.py`, `tests/test_catch_arrays.py`, `tests/test_screen.py`, `tests/test_record.py`, `tests/test_demoscreen.py`.
**Interfaces:**
- **An array with no target.** `task.FOUND_BY = ("look", "cue", "none")`. `"none"` is an array with no target, a catch, whose right answer is not a look at an object.
  - `_same_looks` and `_swapped` judge no `"none"` array: its distractors may be all alike, since that is the catch.
  - `bad-array`, refused at load: a `"none"` array whose structure scores a `SaccadeTo` or `Hold` on its family's target.
  - A normal array keeps `"look"`, so a normal trial whose target looks like its distractors is still refused.
- **A place left empty**: a `Blank` among an array's looks.
  - `screen._items` draws no item for it.
  - `record._stimuli` writes its object with `drawn: false`, and every array entry with `found_by` (Task 1).
  - The layout checks (`overlapping-objects`, `objects-touch`, `crowded-array`) skip it as they skip a `Blank` stimulus.
  - The demo screen labels no target on a `"none"` array.
- **Each special judged** (TSK-69).
  - `check.impossible(task, blocks, values, *, held, ranges, cued, forms, specials="set")` judges each special's structure on every condition playing the default structure, with that condition's sources.
  - `"set"`, live and at a run's start, judges the specials whose share in `values` is above 0. `"every"`, at load (`_impossible_faults`, `_little_time_faults`), judges each.
  - `Session._possible` passes `"set"`, so raising a share is judged when it is set.
- **Judged at the values set** (the console plan's mechanism): `check.LAYOUT` gains `"specials-over-100"`, so shares set past 100 are a warning on the feed when a change makes them so. A bound beating a hold needs nothing new: TSK-69's no-time-to-answer refusal judges a draw by its extremes, at load and live, once the bound is a setting.
- [ ] **Step 1: failing tests:**
  - `test_a_catch_whose_distractors_all_look_alike_is_accepted_and_a_search_is_still_refused`.
  - `test_a_catch_array_scored_by_a_saccade_to_its_target_is_refused`.
  - `test_an_empty_place_draws_nothing_and_records_its_object_undrawn`.
  - `test_an_empty_place_is_no_object_the_layout_checks_read`.
  - `test_a_special_no_animal_can_answer_is_refused_at_load_whatever_its_share`: `catch_hold` above `catch_hold_limit`.
  - `test_raising_a_share_live_is_judged_then_and_a_special_at_0_blocks_nothing`.
  - `test_a_hold_drawn_past_its_bound_is_refused_and_one_inside_it_accepted` (Review Focus 5).
  - `test_shares_set_past_100_live_are_warned_on_the_feed`.
  - `test_the_demo_screen_labels_no_target_on_a_catch`.
- [ ] **Steps 2-4:** as Task 2's. Hand breaks: judge `"none"` arrays for alike looks; leave the specials out of `impossible`; draw a `Blank` object. Commit.

### Task 5: The fixation point's two looks, in the engine (§2)

**Files:** Modify `wl_xcon/task.py` (`Param`), `wl_xcon/check.py`, `wl_xcon/preflight.py`, `docs/references/decisions.md` (TSK-79), `docs/design/architecture.md`; Test `tests/test_fixation_looks.py`.
**Interfaces:**
- **A setting's start may be one of its choices.** `Param.start` takes a number, as before, or a value equal to one of `choices`; it is refused as built otherwise. This is the other half of XC-420, which the console plan's Task 7 closes for telemetry. A run, the record (REC-27's form), the pre-flight and the card take that start as they take a choice set live.
- **`fixation-hidden-at-go`**, a load warning accepted in every kind (the design §2 leaves it to the builder): a `Hide`, on an edge into the task's reaction-time state, of a stimulus that a window held in the state before names. Its sentence gives the lab's rule since 2026-11-16: the fixation point stays on, and its look changes at the go. No reference task hides one (read 2026-11-16).
- **TSK-79** (decisions.md), the PI's rule for every task, 2026-11-16, his words quoted:
  - the fixation point has a hold look and an act look, each a setting (shape, size, color, luminance);
  - it stays on when the stimuli appear;
  - the act look is the go, and on a catch it means keep holding;
  - for the pop-out, "Hollows out".
- [ ] **Step 1: failing tests:**
  - `test_a_choice_setting_starts_at_one_of_its_choices_and_nothing_else`.
  - `test_a_looks_start_runs_records_and_reverts_as_a_choice_set_live`.
  - `test_hiding_the_fixation_point_at_the_go_is_warned`: the pop-out's shape at `64929fe`, as a fixture.
  - `test_a_fixation_point_that_changes_its_look_at_the_go_is_not_warned`.
- [ ] **Steps 2-4:** as Task 2's; commit.

### Task 6: The simulated animal's false alarms (§4, sim first)

**Files:** Modify `wl_xcon/simeye.py` (`Eye`, `_read`, `_decide`); Test `tests/test_simeye.py`.
**Interfaces:**
- `Eye(..., false_alarm_rate: float = 0.0)`, a probability, refused outside 0 to 1.
- `_read` marks a state whose `Hold` on a window that is no target ends the trial in a right outcome: a catch's go.
- On a trial drawn to false-alarm, the eye leaves that state's window after a latency from its first frame, to a drawn object, else to empty space.
- At 0, nothing it did before moves, and its generator's draws stay in their order.
- [ ] **Step 1: failing tests:**
  - `test_at_its_false_alarm_rate_the_eye_leaves_a_catch_and_the_rig_scores_it_false_alarm`: through `gaze.Tracked`.
  - `test_otherwise_it_holds_a_catch_and_is_rewarded`.
  - `test_a_false_alarm_rate_of_0_moves_no_earlier_session`: a seeded session's outcomes, equal to those before.
- [ ] **Steps 2-4:** as Task 2's; commit.

### Task 7: wl-xtasks: the pop-out revised (§2 to §6)

**Files:** wl-xtasks, on branch `popout-revision-2026-11-16` from `console-settings-2026-11-16`: Modify `tasks/popout_search.py` and `CLAUDE.md` (the fixation rule in "Where things go", for task authors). In wl-xcon, Modify `tests/test_popout_search.py` and `tests/test_demo_popout.py`; Create `tests/test_popout_revision.py`.
**Interfaces (the task file):**
- **The fixation point** (section `Stimuli/fixation point`), one `Stimulus("fix", at=(0.0, 0.0), looks=P("fix_look"))`.
  - `fix_look` and `fix_act_look`, unit `"appearance"`. The choices of each are a disc, a ring (`Annulus(inner=<hole>, outer=<size>)`) and a square, built from that look's own settings. The starts are the disc and the ring ("Hollows out").
  - Each look's numbers:
    - `fix_size` 0.3° and `fix_act_size` 0.3°;
    - `fix_hole` and `fix_act_hole`, the ring's inner diameter, 0.15° each, half its width (the builder's, ruled in the report);
    - `fix_luminance` 40 cd/m² and `fix_act_luminance` 40 cd/m², each with COL-29's 80 and its reason.
  - Each look's color: `fix_color` and `fix_act_color`, the isohue set's four hues, each a `ColorSetLight(ISOHUE, hue, saturation=P(...), luminance=P(...))` at that look's `fix_saturation` or `fix_act_saturation`. Each saturation starts at 0, the set's apex, which is today's D65 gray at the same luminance. The start is the set's first hue.
  - The window `fix` scores it throughout. The `center` window (`REMEMBERED`) goes, since the point is drawn there now.
- **The trial** (`search`):
  - `hold_fix`: its `Hold` goes to `delay` with `Show(ARRAY)` and `Mark(ARRAY_ON)`; `Exited` is early, as before; `After(P("fix_hold_limit"))` goes to `NO_FIXATION`.
  - `delay`: `Exited("fix")` first, early, hiding the point and the array; then `After(P("go_delay"))` to `go`, with `Update("fix", looks=P("fix_act_look"))` and `Mark(GO_CUE)`.
  - `go`: `Exited("fix")` to `flight` with `SACCADE_ONSET`; `After(P("response_deadline"))` as before.
  - `flight`: `After(P("landing_limit"))`.
  - `on_target`: `After(P("target_hold_limit"))`.
  - **The graces as settings** (the PI, 2026-11-16, "Yes, a setting"): `blink_grace` 0 s and `tracker_lost_grace` 0.05 s, unit `s`, section Timing, given to the trial's `Tolerances`. If `Tolerances` cannot take a `P(...)` today, this task gives it one (in wl-xcon, with its test), at the starts unchanged, so no outcome moves.
  - Each error's blank hides the point and the array.
  - `Counting(after_stimulus=SPENT, appears="delay")`.
  - `ReactionTime(state="go", to=("flight",))`, its note "from the go, the frame the fixation point takes its act look, to the eye leaving the fixation window".
- **The four specials** (`Task.specials`, section `Special trials`), each a structure built by one helper from the normal one's states, its array a stimulus named `search` too, so the windows, the choice and the record read one name:
  - `target_absent`: `Array(n=P("set_size"), ..., looks=P("distractor_color"), among=P("distractor_color"), found_by="none")`.
  - `odd_place_empty`: `looks=Blank()`, `found_by="none"`.
  - `distractor_alone`: `n=1`, the distractor look, `found_by="none"`.
  - `odd_one_alone`: `n=1`, the odd look, scored as the search is, with its object windows.
  - The `1` of the lone kinds is fixed, its reason beside it: each kind is defined as one disc (§4's table).
  - Each catch's `go`: `Hold("fix", P("catch_hold"))` to `CORRECT_REJECT` with `CATCH_FIXATION_HELD`, `OUTCOME_CORRECT_REJECT`, `REWARD_COMMANDED` and `Reward("reward_correct")`; `Exited("fix")` to a `false_alarm` blank with `CATCH_FIXATION_BREAK` and `TIMEOUT_ON`, then `FALSE_ALARM`; `After(P("catch_hold_limit"))` to `NO_RESPONSE`.
  - Each special's array edge also marks its kind's code.
  - Shares `target_absent_percent`, `odd_place_empty_percent`, `distractor_alone_percent` and `odd_one_alone_percent`: unit `"percent"`, 0 to 100, each `why="a share of trials is at most 100"`, each starting at 0. Then `catch_hold` 0.5 s.
- **Timing** keeps the six times and adds `go_delay` 0 s. `Timing/bounds` holds `fix_hold_limit` 10.0, `landing_limit` 0.3, `target_hold_limit` 3.0 and `catch_hold_limit` 3.0, each with its reason beside it.
- **The draw and the full task.**
  - `draws` gains `"fix_hold": NonAging.between(0.75, 1.25, repeat=FRESH)` [@westerberg2020priming]. `fix_hold`'s start stays 0.5 s, the switch's fixed side.
  - `TRAINING` gains `full=FullTask("Crowd", {"pairings": <all twelve>})`: its staircase at 12, its distractors at full by its condition.
- **Meanings for every new setting** (the builder's, reviewed with the PI on the branch):
  - `go_delay`, `catch_hold`: clear-cut criteria, raising harder;
  - the four bounds: clear-cut criteria, raising easier;
  - the shares, the looks, holes, colors and saturations: not difficulty settings;
  - `fix_act_size` and `fix_act_luminance`: as `fix_size` and `fix_luminance`.
- The docstring's trial and the comments citing the removed bounds are rewritten.

- [ ] **Step 1: failing tests** in `tests/test_popout_revision.py`, and the pop-out's existing ones rewritten to the revision:
  - `test_the_fixation_point_stays_on_and_hollows_out_at_the_go`: its `stimuli` entries.
  - `test_at_go_delay_0_the_array_and_the_go_are_one_frame_and_rt_runs_from_it`.
  - `test_at_go_delay_half_a_second_leaving_in_the_delay_is_early_with_the_timeout`.
  - `test_leaving_on_the_frame_the_delay_ends_is_early` (Review Focus 3).
  - `test_go_delay_drawn_is_drawn_each_trial`.
  - `test_each_catch_held_pays_one_reward_and_broken_is_a_false_alarm_with_the_timeout`: all three.
  - `test_the_probe_is_scored_as_a_search_and_steps_nothing`.
  - `test_each_special_in_alone_runs_and_records_its_kind` (Review Focus 4).
  - `test_each_special_strobes_array_on_then_its_kind_and_the_go`.
  - `test_every_bound_is_a_setting_at_its_old_value_and_nothing_else_moved`: the new trial at the old starts against the old file's outcomes, through the simulated eye at three seeds.
  - `test_the_fixation_point_at_saturation_0_is_todays_gray`: xy within 1e-4 of D65, Y 40 within 1e-9, on the default calibration.
  - `test_the_popout_loads_with_no_warning_it_did_not_have`: the console build's set of codes, no new one (the seam note).
  - `test_the_special_trials_section_holds_the_four_shares_and_catch_hold`.
  - `test_the_full_task_is_crowd_at_12_every_pairing_distractors_at_full`.
  - `test_fix_hold_is_drawn_non_aging_from_0_75_to_1_25`.
  - `test_every_outcome_of_every_structure_is_reached_by_the_hazard_subject`: `Census.uncovered` empty.
  - `test_a_simulated_session_with_specials_runs_end_to_end_through_the_simulated_eye`: 10% each and a false-alarm rate of 0.1. The kinds appear, the staircase steps on normal trials alone, and wl-preproc reads the record back whole.
  - In `tests/test_demo_popout.py`: `test_a_catch_played_with_the_mouse_is_held_for_its_reward`.
- [ ] **Steps 2-4:** as Task 2's. Hand breaks: list the delay's `After` first; keep the `center` window; leave a bound literal. The wl-xtasks commit stays on its branch; its review with the PI is asked with the build's merge.

### Task 8: The documents, the backlog and the CHECKPOINT

**Files:**
- the two pop-out designs (a dated note in the first pointing to the revision);
- `docs/pitfalls.md` (a zero wait lasted a frame; and an `Exited` the go state cannot see, for an eye that left on the frame the state before ended);
- `docs/roadmap.md`;
- decisions.md, TSK-74 and TSK-75 revised (the go, the delay, the bounds now settings, what stays fixed and why);
- `docs/backlog.md`: each deferred item a line; XC-514 stays until wl-preproc answers;
- `docs/CHECKPOINT.md`, rewritten in place.
- [ ] **Step 1:** write. `tests/test_backlog.py`, `tests/test_references.py` and the full suite pass; commit.
- [ ] **Then:** one review of the whole build, by the most capable model. Then the wl-xtasks branch is reviewed with the PI. Then the merge ask, by his yes and a clean CI.

## The design, traced

| Design | Tasks |
|---|---|
| §1 Why | the Goal |
| §2 The fixation rule | 5 (the rule, the warning, starts among choices), 7 (the pop-out's looks) |
| §3 The trial, revised | 2 (one frame), 7 (the delay, the go, RT from it), 4 and 7 (the bounds) |
| §4 Special trials | 3 (declared, drawn, bars, staircase, record), 4 (judged), 6 (sim), 7 (the four) |
| §5 Sections and the full task | 7 |
| §6 Starting values | 7 |
| §7 The record and wl-preproc | 1, then 3, 4 and 7 |
| §8 The builder check | 4 |
| §9 Left to the builder | Tasks 1, 3, 4, 5 and 7, each call said where it is made |
