# Pop-out Search Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **The PI's process rule of 2026-11-07 governs:** "a plan is a design and a list of tests, built once"; one review of the whole build, plus his welfare review of any welfare-listed change. No per-task review loop, no re-proofs.

**Goal:** The lab's first real training task, pop-out search, runs end to end in simulation through the rig's own eye logic, with the engine gains it needs; demo mode's revised spec goes to the PI.

**Architecture:** The task is a file in wl-xtasks that declares three stages as blocks of a `ByCriterion` plan that waits for a person's confirmation, each with a staircase on one setting, drawing its colors from a plain-data color set the engine realizes on the rig's panel at a held macaque cone luminance. The engine gains a staircase declaration, a confirmed progression, a start at a chosen stage, a color-set light kind, two change-log kinds and four trial-line fields, a trainer panel on the console, and a simulated eye that feeds `gaze.Tracked`.

**Tech Stack:** Python 3.11-3.13, the existing `wl_xcon` package, pytest (+ xdist, Playwright for the console), no new dependency (one bundled data table, under ADR-0012).

**Spec:** `docs/superpowers/specs/2026-11-07-popout-search-design.md` (approved by the PI, 2026-11-07). The interface map this plan's names come from: `/Users/jakewesterberg/GitHub/wl-xcon/.superpowers/first-task-prep/code-map.md` (git-ignored; its file:line references are at `2387e17`).

## Global Constraints

- CLAUDE.md binds every task: US English; sim first; no timing claim without a measurement under `docs/measurements/`; hot path: the staircase, suggestions, the pool and the color set run between trials or at load, never in a frame; a test that cannot fail is not a test (each new test seen failing, and a hand break after the fix); docs in sync in the same commit; the full suite in each commit's `&&` chain.
- **Welfare-listed code is not edited** (architecture.md's list; `tests/welfare_manifest.json` once that branch merges). A task that would need it stops and reports. The reward stays `Reward("reward_correct")`.
- Warnings over refusals (the PI, 2026-10-11): refuse only what the rig cannot run or the checker cannot read.
- Positions and sizes are true visual angle at their place (the PI, 2026-10-19).
- **wl-preproc is told a record field's name and shape before it is written** (Task 1); `record.KINDS` grows only by appending after `training` (its `STROBED = KINDS[:4]` is positional).
- Any new `Telemetry` field bumps `link.SCHEMA` (19 today) once, in the first task that adds one.
- Values the PI fixed (spec §3): fixation within 2.0 s, hold 0.5 s, the go on the items' frame, respond within 1.0 s, target hold 0.3 s, 1.0 s between trials, an error's blank timeout 2.0 s; discs 1° on a ring at 8°, fixation dot 0.3°, fixation window 2°, target window 1.5°; background black; full luminance 15 cd/m²; stages `Alone`, `Fade-in`, `Crowd`; Fade-in at 4 items; Crowd 4 to 12; staircase three correct harder, one error easier; move up at 80% of the last 50 at the stage's hardest step; suggest back below 50% of the last 50; colors blue 260°, purple 320°, red 20°, green 140° of wl-style's isohue sector at chroma 29.5, macaque cone luminance L + M at L:M 1 on the Stockman–Sharpe 2° fundamentals.

## Review Focus

1. **A person's lock during a staircase, then a hand-back mid-stage**: the staircase resumes from the held value, never jumps back to where it was before the lock. Test in Task 3.
2. **A suggestion that goes stale**: the bar is met, the prompt shows, then the next trials drop below it before the trainer answers; the prompt withdraws itself (and a confirmation arriving after withdrawal is refused with a sentence). Test in Task 4.
3. **A panel that cannot show the colors**: the default calibration (no spectra) and a measured one whose gamut falls short both run, the second with all four colors desaturated together and a warning saying by how much; never a clipped color. Test in Task 2.
4. **A session resumed after a crash mid-stage** (`wlx taskd`'s stranded resume): the stage, the staircase's level, the pool and any pending suggestion come back as they were. Test in Task 6.
5. **The trainer empties the pool, or picks one pairing in Alone**: an empty pool is refused with a sentence before the next trial; Alone with any pool runs (only the odd one's color shows). Test in Task 5.

---

### Task 1: Tell wl-preproc the new record fields, before they are written

**Files:** Modify `docs/pending-wl-preproc-amendments.md` (a dated ask section); `docs/backlog.md` (one line for the ask, Next free).
**Interfaces:** Produces the field names every later task writes: trial line `stage` (block name, string), `staircase` (`{"setting": str, "level": number}` or null), `pairing` (`{"odd": str, "distractors": str}` or null), `set_size` (int or null); change-log kinds `suggested` (`{"move": "up"|"back"|"widen", "block": str, "bar": {"correct": int, "of": int}, "at_hardest": bool}`) and `declined` (`{"suggestion": <the suggested row's id>}`), appended to `record.KINDS` after `training`; the run's start row gains `start_block` (block name) beside `plan`.
- [ ] **Step 1:** Write the ask (fields, shapes, which rows strobe: `suggested` and `declined` do not strobe, so wl-preproc times them by its clock fit; see the c3-timing diagnosis before sending if it changes that).
- [ ] **Step 2:** `tests/test_backlog.py` and `tests/test_references.py` pass; commit. The controller sends the ask (a peer session); Tasks 3 to 5, which write the fields, start only after it is sent, and adjust if wl-preproc's answer asks a change.

### Task 2: Macaque cone luminance and the color-set light kind

**Files:** Create `wl_xcon/data/stockman_sharpe_2deg.csv` (or the repository's existing data path for CIE tables; its sha256 checked as ADR-0012 does); Modify `wl_xcon/cones.py`, `wl_xcon/photometry.py`, `wl_xcon/check.py`, `docs/design/decisions/ADR-0012-cie-tables.md` and ADR-0004's inventory (the table's licence and source), `docs/references/decisions.md` (a COL entry: the PI's "wl-style's 2-degree set"); Test `tests/test_color_set.py`.
**Interfaces:**
- `cones.macaque_luminance(spectrum) -> float`: L + M at L:M 1 on the Stockman–Sharpe 2° fundamentals.
- `photometry.ColorSet` (frozen dataclass): `name: str`, `colors: Mapping[str, tuple[float, float]]` (CIE 1931 xy per color name), `apex: tuple[float, float]`, `luminance_cd_m2: float = 15.0`, `held: str = "macaque_2deg_LM1"`; `ColorSet.load(path) -> ColorSet` reads the plain-data file (Task 9's `stimuli/isohue.json`).
- `photometry.ColorSetLight(colorset: ColorSet, color: str, fraction: float | P = 1.0)`: a light (absolute, valid on black) whose chromaticity is the set's color, whose macaque luminance is `fraction × ` that of a D65 light at `luminance_cd_m2`.
- `photometry.realize(colorset, calibration) -> Realized` with `.drive[color] -> (r, g, b)` and `.desaturation: float` (0 when every color fits).
- `check` finding `color-set-desaturated` (a warning in every kind) naming the fraction lost.
- [ ] **Step 1: failing tests.** `test_macaque_luminance_of_d65_matches_wl_style_gray_ratio` (the four sRGB previews #2f93f8, #bc79e0, #ed7474, #54a947 against #969696, computed on the sRGB model: each within 0.6% of the gray, as wl-style's CSV says); `test_color_set_lights_are_equal_in_macaque_luminance_on_a_measured_calibration` (a measured-spectra calibration from `tests/_calibrations.py`: the four realized lights' macaque luminance equal to 0.1%); `test_a_short_gamut_desaturates_all_four_together_and_warns` (a calibration with a narrow green primary: `desaturation > 0`, all four moved toward `apex` by the same fraction in xy, macaque luminance still equal, one `color-set-desaturated` finding); `test_the_default_calibration_runs_with_its_model` (no spectra: realized through the sRGB primaries model, no refusal); `test_a_color_set_light_is_allowed_on_black` (no `cone-color-on-black`).
- [ ] **Step 2:** run; each fails for its reason.
- [ ] **Step 3:** implement. Desaturation moves each color's xy toward `apex` by one shared fraction, the smallest that brings all four inside the panel's gamut at the held luminance (a bisection; my call, spec §3.2: "all four lose chroma together, never luminance").
- [ ] **Step 4:** pass; hand breaks (drop the shared fraction; use CIE Y instead of macaque luminance); full suite; commit.

### Task 3: A staircase on a setting, between trials, that a person's held value stops

**Files:** Modify `wl_xcon/task.py` (a declaration), `wl_xcon/taskd.py` (applied where the scheduler chooses the next trial's values; `Session.observe` or the inter-trial step the map names), `wl_xcon/check.py` (its load checks), `wl_xcon/record.py` (the trial line's `staircase`, after Task 1's answer); Test `tests/test_staircase.py`.
**Interfaces:** `task.Staircase(setting: str, levels: tuple[float, ...], down: int = 3, up: int = 1, start: int | None = None)`: `levels` easiest first; correct counts toward `down` (harder), a failure steps easier; TSK-33's classes (correct = success; wrong target, any §3.1 error after the go, and no response = failure; a trial ending before the go moves nothing). `Block.staircase: Staircase | None = None`. The staircase's current level is the setting's value unless a person holds the setting (C3's held value); a hand-back resumes the staircase at the held value's nearest level.
- [ ] **Step 1: failing tests.** `test_three_correct_step_harder_one_error_easier`; `test_an_early_saccade_moves_nothing`; `test_a_held_value_stops_the_staircase_and_a_hand_back_resumes_from_it` (Review Focus 1); `test_the_trial_line_records_the_level`; `test_a_staircase_on_an_undeclared_setting_is_refused_at_load`; `test_it_stops_at_its_ends` (never past `levels[0]` or `levels[-1]`).
- [ ] **Steps 2-4:** run (fail), implement, pass, hand breaks, full suite, commit. Close XC-242's part this covers, narrow its line.

### Task 4: A progression that suggests, and a person who confirms

**Files:** Modify `wl_xcon/task.py` (`ByCriterion(fall_back=..., confirm: bool = False)`: the existing order, `task.py:2092`, gains `confirm`; each `Block.criterion` `(proportion, window)` is the up bar and `fall_back` the back bar, as today), `wl_xcon/taskd.py` (no automatic move when `confirm`; compute the suggestion; withdraw a stale one), `wl_xcon/link.py` and `wl_xcon/serve.py` (`Decline` command, kind `decline`; the frame's `suggestion` field; `link.SCHEMA` 20), `wl_xcon/record.py` (`suggested`, `declined` kinds per Task 1); Test `tests/test_confirmed_progression.py`.
**Interfaces:** A block's "hardest step" is its staircase at `levels[-1]` (a block with no staircase is always at its hardest). The bar: of the last `window` trials that ended with an answer (spec §3.4: no-fixation and early saccades excluded), at least `proportion` correct, with the staircase at its hardest throughout those trials. `Telemetry.suggestion: Suggestion | None` (`move`, `block`, `correct`, `of`). The trainer confirms with the existing `NextBlock`/`BackBlock` (which `Session._move` records with who) or declines with `Decline`.
**Welfare:** the trainer's answer reaches `Session._move` through `Session._command` (`taskd.py:2399`). If `Decline` needs a branch in `_command`, that branch is a welfare item for the PI, listed in the build's welfare summary, as engine build C3's three branches were; the held pass-through and the `except (Exceeded, TypeError)` line stay byte for byte.
- [ ] **Step 1: failing tests.** `test_a_met_bar_suggests_and_does_not_move`; `test_next_block_after_a_suggestion_moves_and_both_rows_are_logged`; `test_decline_logs_and_keeps_the_stage`; `test_a_suggestion_withdraws_when_the_bar_drops` (Review Focus 2) and `test_a_confirmation_after_withdrawal_is_refused_with_a_sentence`; `test_below_the_back_bar_suggests_the_previous_stage`; `test_the_bar_counts_answers_only`; `test_without_confirm_bycriterion_moves_as_before` (C2b's behavior unchanged).
- [ ] **Steps 2-4:** as above; commit.

### Task 5: The pairing pool

**Files:** Modify `wl_xcon/task.py` (`Pool(setting: str, choices: tuple[tuple[str, str], ...])` declared on the task; each trial draws one pairing uniformly from the setting's current value), `wl_xcon/taskd.py` (the draw, and a `widen` suggestion by Task 4's bar over the pooled current pairings), `wl_xcon/record.py` (the trial line's `pairing`); Test `tests/test_pairing_pool.py`.
**Interfaces:** The pool's current value is a tuple of pairings a person sets with the existing `set` command (the trainer's picks at the prompt); a `widen` suggestion names no pairings (the trainer picks, spec §3.4).
- [ ] **Step 1: failing tests.** `test_each_trial_draws_a_pairing_from_the_current_pool`; `test_the_bar_on_the_pooled_pairings_suggests_widen`; `test_an_empty_pool_is_refused_with_a_sentence` (Review Focus 5); `test_in_alone_any_pool_runs`; `test_the_pool_carries_into_the_next_stage`.
- [ ] **Steps 2-4:** as above; commit.

### Task 6: Start at a chosen stage, with starting values, and resume a stage

**Files:** Modify `wl_xcon/cli.py` (`wlx run --start-block NAME`), `wl_xcon/link.py` (`StartRun`, `CheckRun` gain `start_block`), `wl_xcon/service.py` **only outside its welfare-listed functions** (else stop and report), `wl_xcon/taskd.py` (`Scheduler` starts at the named block), `wl_xcon/resume.py` (stage, staircase level, pool, pending suggestion), `wl_xcon/web.py` (the start form: stage, staircase start, pairings; the previous session's end read from its record); Test `tests/test_start_block.py`, `tests/test_page_browser.py` (one case).
- [ ] **Step 1: failing tests.** `test_a_run_starts_at_the_named_block_and_its_start_row_says_so`; `test_an_unknown_block_is_refused_before_the_run_opens`; `test_the_start_form_shows_yesterdays_end`; `test_a_stranded_session_resumes_its_stage_level_pool_and_suggestion` (Review Focus 4).
- [ ] **Steps 2-4:** as above; commit.

### Task 7: The trainer's panel

**Files:** Modify `wl_xcon/web.py` (a training pane: the stage by name, the staircase's level with the existing hold and hand-back controls as its lock, the last 50's percent correct with errors by kind beside it, the pool, and the suggestion with **Move up** / **Hold** or **Move back** / **Hold**, and a pairings picker for `widen`), `wl_xcon/serve.py` if a route is needed; Test `tests/test_web.py`, `tests/test_page_browser.py` (Chromium and WebKit).
- [ ] **Step 1: failing tests.** `test_the_pane_names_the_stage_and_its_level`; `test_a_suggestion_shows_why_and_its_two_buttons`; `test_move_up_sends_next_block_and_hold_sends_decline`; `test_widen_shows_a_picker_of_unused_pairings`; the browser case clicks through a suggestion in both engines.
- [ ] **Steps 2-4:** as above; commit.

### Task 8: The simulated eye, through `gaze.Tracked` (XC-456)

**Files:** Create `wl_xcon/simeye.py` (a reactive gaze source), Modify `wl_xcon/simulate.py` (a simulated session of a task with gaze guards uses it by default; the hazard `Subject` stays for tasks without), `wl_xcon/taskd.py` (plugged through `Session.world` as `gaze.Calibrating.world` is); Test `tests/test_simeye.py`.
**Interfaces:** `simeye.Eye(accuracy: float, rt_median_s: float, early_rate: float, seed: int)`, a sample source `gaze.Tracked` reads: it fixates the fixation point when shown, saccades after the go to the target with probability `accuracy` (else to a distractor or empty space), early with probability `early_rate`, its saccades as velocity profiles the rig's detector finds.
- [ ] **Step 1: failing tests.** `test_a_simulated_session_scores_as_gaze_tracked_does` (the XC-456 probe's case: outcomes from `Tracked` on the eye's samples equal the session's recorded outcomes, 200 trials); `test_accuracy_one_scores_correct_every_answer`; `test_early_rate_produces_early_saccade_errors`; `test_the_detector_finds_its_saccades`.
- [ ] **Steps 2-4:** as above; close XC-456; commit.

### Task 9: The task, in wl-xtasks

**Files (wl-xtasks):** Create `stimuli/isohue.json` (the four colors' xy, the apex, the held luminance definition, its source: wl-style's `02-color/isohue_spectrum/` at the PI's local working tree, its CSV's values, and the green computed with its generator on 2026-11-07), `tasks/popout_search.py`, `README.md` and `CLAUDE.md` (the layout: `tasks/` and `stimuli/`, stimulus definitions as plain data); **(wl-xcon):** the task's event codes in `tasks/allocation.py` if new ones are needed.
**Interfaces:** `popout_search` is one `Task` with one trial structure and a `Plan` of three `Block`s named `Alone`, `Fade-in`, `Crowd`, each with `criterion=(0.8, 50)`, under `ByCriterion(fall_back=(0.5, 50), confirm=True)`; Fade-in's `Staircase` on the distractors' luminance fraction, Crowd's on `set_size` 4..12; a `Pool` of the twelve pairings; `ColorSetLight` colors from `stimuli/isohue.json` read by a path relative to the task file; the trial: fixate, hold, then one transition shows the array and hides the fixation dot (the go), the next saccade answers (another item, empty space, or leaving the target before 0.3 s: an error with a 2.0 s blank), every `Param` with a `start`, background black.
- [ ] **Step 1: failing tests (in wl-xcon, reading the task by path from a checkout of wl-xtasks, as the suite reads wl-preproc):** `test_popout_loads_clean_but_the_expected_warnings`; `test_the_go_is_the_frame_the_array_appears`; `test_a_saccade_to_empty_space_is_an_error_with_the_timeout`; `test_a_target_break_is_an_error`; `test_a_simulated_session_moves_up_only_on_confirmation`; `test_the_record_reads_back_whole_through_wl_preproc`.
- [ ] **Steps 2-4:** as above; the review report (`wlx review`) of the task in the commit message's body; commit in both repositories.

### Task 10: Demo mode's revised spec, to the PI

**Files:** Modify `docs/superpowers/specs/2026-10-06-demo-mode-design.md` (§14's items applied, the pop-out task as its first task, its welfare items, in `Service._open`, listed for the PI).
- [ ] **Step 1:** revise; **Step 2:** the controller takes its welfare items to the PI (a summary, numbered); building demo mode is a later plan, after his answer.

### Task 11: The docs and the one-page CHECKPOINT

**Files:** `docs/CHECKPOINT.md` (rewritten in place), `docs/design/architecture.md` (the staircase, the confirmed progression, the color set, the simulated eye, telemetry 20, the two kinds), `docs/references/decisions.md` (TSK entries for the confirmed progression and the staircase declaration, citing [@levitt1971transformed]), `docs/backlog.md` (closes and narrows).
- [ ] **Step 1:** write; the docs tests and the full suite pass; commit. Then one review of the whole build (the most capable model), the PI's merge ask.
