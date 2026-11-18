# Console Settings Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **The PI's process rule of 2026-11-07 governs:** "a plan is a design and a list of tests, built once"; one review of the whole build, plus his welfare review of any welfare-listed change. None is planned (Global Constraints); a task that finds it needs one stops there. No per-task review loop.

**Goal:** From its card, a trainer makes any timing setting fixed or drawn, and any size fixed or scaled by eccentricity, its gaze window following it. Limits stand only where a value is impossible, and the rig warns from the layout actually set. Colors are picked by set, hue and two levels, and new ones are defined three ways for the PI to commit. The Task parameters tab reads in sections, and training has a tab and a three-position switch of its own.

**Architecture:** A person's *form* for a setting (a drawn shape, or a scale factor) is new session state beside a person's value. It is offered by one new command, `SetForm`, staged and applied at the boundary as a live range is, recorded as a `form` change row and reverted with the rest. A value typed on the card is still `Session.set`'s, unchanged. The load checks gain a judgment *at the values set*: an open side of a range is pinned to the value in force, and the checks are asked again on every change from `_impossible`, which `_command` already calls ahead of `set`. Every bound a task still declares is hard and carries its reason. Colors gain a per-light `saturation`; a pick names a set and a hue and goes through `set` as the declared choice it names. Sections are `Param.section`. The switch is `Shaping`, with a task's finished version declared as `Plan.full`.

**Tech Stack:** Python 3.11-3.13, the `wl_xcon` package, pytest (+ xdist, Playwright Chromium and WebKit), pyzmq and msgpack (the console extra), numpy, the standard library's `math`, `json` and `os`. **No new dependency** (Task 8 says why).

**Spec:** `docs/superpowers/specs/2026-11-16-console-settings-design.md`, approved by the PI on 2026-11-16, asked in the UI: "Approve both". Section numbers below are its. Its companion, `docs/superpowers/specs/2026-11-16-popout-revision-design.md`, is the next plan's (the seam, below). The decay's literature: `.superpowers/side-2026-11-17/nonaging-decay-report.md`.

**The PI on this plan** (2026-11-16, asked in the UI): frozen trials stay out of the bars ("They don't count"); new colors go to the proposed file first ("Proposed file first"); built with a fresh builder per task once demo mode has merged ("Fresh builder per task").


## Reading the design against the code (`b3d4dd3`)

- **What the code already has, which the design's words do not show:**
  - `NonAging(minimum, mean, maximum, repeat)` puts its mean second, so a derived mean cannot be an optional field; hence `NonAging.between`.
  - No task file writes a `NonAging` yet.
  - `variation.realized_mean` and `hazard_ratio` already give §3's figures.
  - `SetRange` decodes through `_numbers`, which calls the listed `_setting`.
  - `_impossible` is called from one non-listed line of `_command`, ahead of `set`, which is the seam every change already passes.
  - A value outside its range reaches `_beyond_range` only from inside the listed `set`.
  - `photometry.SRGB_MACAQUE` is the PI's generator's own sRGB model (`conelum`'s).
  - `record._stimuli` writes each array object's place already.
  - `Service.tasks` holds `--tasks`.
- **The existing `link.Training` is the clear and first-answers aid**, so the three-position switch is a new command, `Shaping` (the mockup's word, `docs/superpowers/mockups/2026-10-01-console-mockup-v13.html`).
- **XC-420 is open**: telemetry cannot carry an appearance among a run's values. A color pick is the first console path that puts one there, so Task 7 closes it.
- **XC-150 (the library pull) is not built**, so a file in the wl-xtasks checkout is read at the next load, committed or not. That decides where a new color goes (Task 8).
- **The planner's calls**, each said where it is made: a typed value stays the switch's *fixed* side (Task 2); a live non-aging range derives its decay again (Task 2); every declared bound is hard (Task 4); the layout is judged with open sides pinned (Task 4); eccentricity is measured from straight ahead and `scaled-small` (Task 6); the color levels' units (Task 7); new colors go to `stimuli/proposed/` and the DKL contrast (Task 8); and freezing (Task 10).

**Why twelve tasks, not the brief's nine and the ask.** §4 is two tasks: the mechanism (Task 4), and taking the five reference tasks' caps away (Task 5), whose test churn a reviewer can reject on its own. The wl-xtasks change is its own task (Task 11): another repository, curated with the PI and merged only on his review. The rest follow the brief's cut, with §3's card split into the switch (Task 2) and its histogram (Task 3).

## Global Constraints

- **CLAUDE.md binds every task.** US English. Sim first. No timing claim without a measurement under `docs/measurements/`: the profile and the decay figures are arithmetic of a declared distribution and say so. Each new test is seen failing first, then by a hand break after the fix. Docs stay in sync in the same commit: architecture.md's task-model and console rows, and each decisions.md entry in the task that builds it. The full suite runs in each commit's `&&` chain, with `set -o pipefail` and the log written to a file. Never run the suite, edit a test or `git add` while a mutation sweep is in flight.
- **No welfare-listed item changes** (`tests/welfare_manifest.json`; `python3 tools/welfare_diff.py BASE HEAD` at every commit, its output read: every item `SAME`, no `CHECK CHANGED`; `BASE` the build branch's base).
  - `taskd.Session.set` is unchanged.
  - `link._setting` is unchanged, and every new decoder calls it (`_numbers` gains a `kind` keyword; it is not listed).
  - In `Session._command`, the listed first statement and the listed `except (Exceeded, TypeError) as refused:` line are unchanged. That line is counted within `_command`, so no new branch there writes a second one. The new branches (`SetForm`, `SetColor`, `Shaping`) are written beside `SetRange`'s. The one non-listed line calling `self._impossible(...)` gains `by=command.by` (Task 4).
  - `service.Service._start`, `preflight.gate`, `Session._schedule`, `_hold`, `_ends`, `_manual_reward` and `OUTSIDE_A_RUN` are not touched.
  - No reward amount, out-of-cage clock or welfare limit changes (§2's non-goals). A task that finds it needs a listed change stops, and the controller asks the PI with the exact change.
- **Hot path.** Draws, forms, scaled sizes, placements, profiles and the layout checks all run between trials, as `variation.draw` does. `screen.resolve` binds a scaled size where it binds a fixed one, from values made between trials. No trial-loop frame does new work or allocates.
- **Warnings over refusals** (2026-10-11). A refusal is kept for: §4's five impossibles; what the checks already block; an authoring rule (a reason or section too long, two window sizes); and a pick or form naming nothing the task has.
- **No average ppd** (2026-10-19). An object's eccentricity is its true angle from straight ahead (`geometry.polar_of_deg`), at its own place.
- **Each fixed number has its reason** (TSK-75):
  - `task.NONAGING_DECAY = 3`, TSK-15's revision;
  - `variation.PROFILE_BINS = 20`, a display choice;
  - `link.LISTED_LIMIT = 64`, a wire bound as `VALUES_LIMIT` is;
  - text limits of 120 characters for a reason and 60 for a section, as `Staircase.hardest`'s.
- **Telemetry schema 21 → 22, once** (Task 2). Later tasks add their fields to 22 before the merge.
- **The record.** `record.KINDS` gains `"form"` and `"shaping"` after `"declined"`, and `record.STROBED` becomes `(*KINDS[:4], "form")`. wl-preproc is told every new shape before any is written: Task 1 comes before Tasks 2, 6, 7 and 10.
- **wl-xtasks is curated with the PI.** Task 11 is a wl-xtasks branch, merged only after he reviews it. Dates are the local day (US Eastern).

## Review Focus

1. **A switch over what a block gives.** The trainer switches `fix_hold` to drawn in a block whose conditions set it, whose own draw draws it, or whose staircase steps it. Then he hands it back. The person's form wins over each from the next trial, the card names what it overrides, and the hand-back gives the block's own back (Task 2).
2. **Degenerate shapes.** These are refused with a sentence, nothing staged, the session running on (Task 2):
   - a shortest at or past the longest;
   - an SD at or below 0;
   - an empty list, or one past `LISTED_LIMIT`;
   - weights of another length, all zero or negative;
   - a word among the numbers.
3. **One setting's change breaks another's layout.** The trainer raises `set_size`, and the windows at the current `ring_radius` overlap. That is a warning naming the pair and both values, and it is accepted on the feed. Lowering it again adds nothing. A ring radius drawn is judged at both its ends. A ring set off the field is refused, whichever setting moved it there (Task 4).
4. **Scaled at or near the center.** `fix_size` scaled at eccentricity 0 is warned as not drawn. A ring close in, at the PI's 0.3, is warned smaller than its fixed size. An object-window ratio below 1 is warned (Task 6).
5. **Both saturations at 0.** Every hue then becomes the set's gray, so the odd one is odd no longer. It is refused as `impossible-trial` at the moment it is set; one light at 0 is accepted (Task 7).

## The seam with the second plan (the pop-out's revision)

- **This plan builds what the second one uses:**
  - `NonAging.between` and `NONAGING_DECAY` (`fix_hold` drawn non-aging 0.75 to 1.25 s in the task file);
  - the timing switch, on every unit-`s` setting with no task change (`go_delay`, `catch_hold`);
  - `Param.section` (its *Special trials* section) and `Param.why`;
  - the hard-limit rule and `check.laid_out`;
  - `Plan.full`, the shaping switch and its `drawn: "full"` token;
  - `ColorSetLight.saturation`;
  - Task 1's record shapes.
- **This plan changes the pop-out only as §4, §5 and §7 need** (Task 11): its sections, its caps, `object_window` as a ratio, and its color set's `design`.
- **The second plan's, left untouched here:**
  - every piece of trial logic: the fixation point's two looks, `go_delay`, the special trials and `catch_hold`, the catch-aware `check.impossible`, and the fixed bounds as settings;
  - the pop-out's own `Plan.full` declaration (its §5);
  - its `fix_hold` draw;
  - any saturation setting it wants;
  - its event codes;
  - its own wl-preproc ask.

---

### Task 1: Tell wl-preproc the new record shapes, before any is written (§9)

**Files:** Modify `docs/pending-wl-preproc-amendments.md` (a dated section, `# OPEN — the console settings: forms, scaled sizes, a light's saturation, the training switch (new, 2026-11-16)`, in the shape of XC-502's) and `docs/backlog.md` (XC-513, in the waiting-on-another-repository section; Next free stays 516: XC-514 is the pop-out plan's, and main took XC-515 at demo mode's merge).
**Interfaces (the ask, exactly):**
1. **A drawn or switched timing setting.**
   - `parameter_changes.jsonl` gains kind `form`, after `declined`. It **is strobed**: it carries `sequence`, and `STROBED` becomes set, hand_back, range, revert, form.
     - `now` is the person's form. A draw is in `recorded`'s class/fields form, every field, `repeat` `"fresh"`: `{"class": "NonAging", "fields": {"minimum": 0.75, "mean": 0.9166666666666666, "maximum": 1.25, "repeat": "fresh"}}`. A scaling is `{"class": "Scaled", "fields": {"factor": 0.3}}`.
     - `was` follows the existing rule (`_given_by`): null where a draw, a staircase, a pool or the conditions gave the setting; the person's value or earlier form where one stood; else the run's value.
     - Detail `"shape"` is one of `non_aging`, `uniform`, `normal`, `list`, `weights`, `scaled`.
   - A form ends by a `set` row, a `hand_back` row (its `was` the form) or `revert` rows (forms or values in `was`/`now`).
   - Each trial line's `drawn[name]` is the form row's `change` id, an integer, as for a live range. `params[name]` is the value drawn, or the `Scaled` object.
   - A block end's `varied[name]` is `{"by": "draw", "from": <id>, "distribution": <now>}`, or `{"by": "scaled", "from": <id>, "factor": <f>}`.
   - **A non-aging wait a person gives has its mean derived:** shortest + (longest − shortest)/3. One a task declares is written as declared.
2. **A scaled size and its window.**
   - Each `stimuli[]` entry gains `size_deg`: the look's size drawn at its place. It is null for an array, whose objects carry theirs, and for a look with no single `size`.
   - Each `objects[]` entry gains `size_deg` and `window_deg`, its object window's radius (null where the array has none). Both keys are always written.
   - An object window may be declared as a multiple of its object's radius. Its setting's value is then that multiple: the pop-out's `object_window` is 3.0 to start, where it was 1.5°. `window_deg` gives the degrees.
3. **A color by set, hue and both levels.**
   - The `ColorSetLight` form gains `"saturation"`, always written: a number, 1.0 by default, or a setting by reference.
   - Each realization entry (the start row's `color_sets[set].realized[]`, a line's `color_realized[set][]`) gains `"macaque_row": [rX, rY, rZ]`.
   - `color_sets[set]` gains `"design"`, `{"space": "CAM16-UCS", "gray_lightness": 65.0, "chroma": 29.49}` or null.
   - **A reader's light:**
     - its chromaticity: xy = apex + saturation × (realized xy − apex);
     - its macaque luminance: L = fraction × luminance;
     - its XYZ: with u = (x/y, 1, (1 − x − y)/y), XYZ = u × L / (macaque_row · u).
4. **The training switch.**
   - Change kind `shaping`, not strobed: `name` `"shaping"`, `was` and `now` one of `"on"`, `"frozen"`, `"full"`, `meaning` null.
   - Each trial line gains `"shaping"`.
   - `drawn[name]` may be `"full"`, a new source token, for a value the task's full version gives.
   - A run starts on. Nothing is added to the start row.

**Deliberately not asked:** the new warning codes (values in `warnings.jsonl`'s `code`, not shapes); sections and limit reasons (the task's declaration, which the record hashes as before).
- [ ] **Step 1:** write the ask and XC-513's line. **Step 2:** `tests/test_backlog.py` and the full suite pass; commit. The controller sends it by message to wl-preproc's session. Tasks 2, 6, 7 and 10 write their shapes only after it is sent, and are rebuilt to any rename it answers.

### Task 2: The timing switch: a person's form, staged, drawn, recorded and reverted (§3)

**Files:** Modify `wl_xcon/task.py`, `wl_xcon/variation.py`, `wl_xcon/link.py`, `wl_xcon/taskd.py`, `wl_xcon/record.py`, `wl_xcon/serve.py` (`parse_command`), `wl_xcon/web.py`, `docs/design/architecture.md` (the console row: schema 22, `SetForm`), `docs/references/decisions.md` (TSK-15's revision), `docs/references/library.bib`; Test `tests/test_forms.py`, `tests/test_variation.py`, `tests/test_link.py`, `tests/test_web.py`, `tests/test_page_browser.py`.
**Interfaces:**
- **The decay** (TSK-15's revision):
  - `task.NONAGING_DECAY = 3`; `NonAging.between(shortest, longest, *, repeat=None) -> NonAging`, a classmethod whose mean is shortest + (longest − shortest)/NONAGING_DECAY.
  - `variation.LIVE_NUMBERS[NonAging] = ("minimum", "maximum")`. `with_numbers` on a `NonAging` derives its mean from the new ends, and the redraw is kept. A declared mean stands until a person moves an end. (Planner's call: the PI's "Derived from min and max" supersedes C3's live "average".)
  - `words` says a non-aging draw as `non-aging from 0.75 s to 1.25 s (τ 0.1667 s, 1 in 20 drawn again, mean 0.8905 s)`, its arithmetic as `realized_mean` gives it.
- `task.SHAPES = ("non_aging", "uniform", "normal", "list", "weights")`; `task.Scaled(factor: float)`, frozen (used from Task 6).
- **The command.** `link.SetForm(name, shape, numbers, by, values=(), weights=())`, `KIND = "form"`.
  - Its numbers by shape: non_aging `shortest`, `longest`; uniform `low`, `high`; normal `mean`, `sd`, `low`, `high`; list `values`, played in shuffled passes; weights `values` and `weights`; scaled `factor` (Task 6).
  - The numbers decode through `_numbers(data, name, by, kind="form")`, and each value and weight through `_setting`, unchanged. A word is refused, and so are more than `LISTED_LIMIT = 64` values.
  - `serve.parse_command`, `_command_from` and `_encode_command` take it.
- **The session.** `Session._forms: dict[str, Distribution | Scaled]`, applied.
  - `Session._form(command, index)` beside `_range`. It never raises, and refuses with a sentence, nothing staged:
    - a ceiling, an undeclared name, or a setting not live;
    - a drawn shape on a setting whose unit is not `"s"`;
    - an undrawable draw (`check.undrawable`);
    - a draw whose extreme is past a hard limit (`_beyond_range` at each, Task 4);
    - a draw that leaves trials impossible (`_possible(forms=...)`);
    - the layout (`_laid_out`, Task 4).
  - It builds the distribution with `repeat=FRESH` (the PI's "Follow same/fresh") and offers `Pending("form", name, was, now, by, after, form=<form>)`.
  - `_apply_staged` applies it: `_forms[name] = form`, the person's value released, a strobed `form` row. A later `set` of the name drops its form, and so does `hand_back`.
  - `_draw`'s order: a person's value, then **a person's draw (keyed `("person", name)`, its source the form row's id)**, then staircase, pool, a condition's own range, the block's or the task's draw, the conditions, the run.
  - `_source` gives `"form"`. `_outside_sets`, `_possible` and `check.impossible` (a new `forms=` keyword) judge a form at its extremes, a person's draw beating the conditions as a held value does. `Moment.forms`, so `_undone` and `_revert` take forms back. `staged` lists a pending form.
- **`ParamRow` (schema 22).**
  - `switch`: `"drawn"` on a live unit-`s` setting, else None.
  - `shape`: `{"shape", "numbers", "values", "weights", "by"}` for the shape in force, a person's or the open block's draw, `by` one of `"person"`, `"block"`, `"task"`; None where fixed.
  - The card (`web`): *fixed* | *drawn*.
    - Fixed is today's number field, `set`.
    - Drawn is a shape select and that shape's fields with *apply*, which sends `form`.
    - The card says what the form overrides, as `_whence` does.
- [ ] **Step 1: failing tests.**
  - `test_nonaging_between_derives_tau_a_third_of_the_range`: `between(0.75, 1.25)`:
    - its mean is 0.75 + 0.5/3;
    - `realized_mean` ≈ 0.8905 (±5e-4);
    - the share drawn again is e^-3 ≈ 0.0498;
    - `hazard_ratio` over its value at 0.75 is 1.06, 1.22, 1.50 and 3.67 at 0.875, 1.0, 1.0833 and 1.2 (±0.01).
  - `test_the_decay_has_one_hazard_profile_at_every_range`: 0.4-1.4 and 0.75-1.25 give the same ratio at each fraction of the range, to 1e-12.
  - `test_a_live_nonaging_range_derives_its_decay_again`: the maximum set to 1.5, the mean becomes 0.75 + 0.75/3.
  - `test_a_nonagings_live_numbers_are_its_shortest_and_longest`: a `SetRange` naming `mean` is refused, naming the two.
  - `test_a_timing_setting_switched_to_drawn_is_drawn_from_the_next_trial`: a simulated pop-out run.
    - The trial running is unchanged.
    - Each later trial draws `fix_hold` inside [0.75, 1.25], not all alike.
    - Each line's `drawn.fix_hold` is the form row's id.
  - `test_a_switch_replaces_the_blocks_conditions_draw_or_staircase_until_handed_back` (Review Focus 1): parametrized over the three. The card names what it overrides; after the hand-back, the block's own gives it again.
  - `test_a_typed_value_on_a_drawn_card_holds_it_fixed_and_ends_the_form`.
  - `test_a_repeat_draws_a_switched_setting_fresh`.
  - `test_degenerate_shapes_are_refused_with_a_sentence` (Review Focus 2): each case refused and nothing staged.
  - `test_a_form_is_judged_at_its_extremes`: a longest that its state's bound always beats is refused, `impossible-trial`.
  - `test_the_drawn_switch_is_a_timing_settings_alone`: a `deg` setting's drawn form is refused, and its `switch` is None.
  - `test_a_form_row_strobes_and_says_what_it_replaced`: the row as Task 1 says, with a `sequence`.
  - `test_a_revert_takes_a_form_back_with_the_rest`.
  - `test_set_form_round_trips_and_its_numbers_pass_through_setting`: `_setting` is patched to count its calls.
  - `test_a_timing_card_offers_fixed_and_drawn_with_each_shapes_fields`.
  - Browser, both engines: `test_switching_fix_hold_to_nonaging_sends_its_shortest_and_longest`.
- [ ] **Steps 2-4:** run (each fails for its reason). Implement and pass. Hand breaks: drop the derived mean; let a condition beat a form; strobe nothing. Then the full suite, `welfare_diff` all `SAME`, and commit.
- **TSK-15's revision** (decisions.md):
  - Decided: 2026-11-16, the PI ("Derived from min and max"; "Keep drawing again").
  - Basis: an engineering default, the redraw kept. The literature gives no criterion (the report, §0, §3). The longest wait sits at the 95th percentile of the uncut wait; the hazard has one profile at every range; R/τ = 3 is inside published practice [@grabenhorst2019anticipation]. The PI's range is [@westerberg2020priming].
  - Caveat: only catch trials keep the hazard flat to the last moment [@los2014outlines] (footnote 3), [@ray2013strength]; the PI kept the redraw.
  - Published practice runs from about 0.9 (`srinivasan2013action`) to about 4.8 (`vangkilde2013temporal`), each cited by key once this task has added it.
- **The library.** The report's §7 entries not yet in `library.bib` go in with this task, as §11 says, each with its `note` as read. The three the design cites are there already.

### Task 3: The card's histogram and hazard (§3)

**Files:** Modify `wl_xcon/variation.py`, `wl_xcon/taskd.py` (`parameters`), `wl_xcon/link.py`, `wl_xcon/web.py`; Test `tests/test_profile.py`, `tests/test_web.py`.
**Interfaces:**
- `variation.PROFILE_BINS = 20`; `variation.Profile(edges: tuple, density: tuple, hazard: tuple)`.
- `variation.profile(distribution, declared=None, *, bins=PROFILE_BINS) -> Profile`:
  - density is each bin's share of draws;
  - hazard is each bin's as a multiple of its value in the first, so flat is 1 ("against flat", the report's columns);
  - a list or a weighted set has one bar for each value, its hazard discrete: P(v) / P(≥ v);
  - a normal is cut as `bounds_of` cuts it.
  - Arithmetic of the declared distribution, not of the rig. Cached by distribution, so `parameters` computes none twice.
- `ParamRow.profile: dict | None` (`edges`, `density`, `hazard`) wherever `shape` is not None.
- `web._profile(row) -> str`: inline SVG, bars for the density, a line for the hazard, a dashed line at 1 marked *flat*, the words *the declared distribution, not a measurement*. Python renders every word.
- [ ] **Step 1: failing tests.**
  - `test_the_pis_foreperiods_profile_has_the_reports_figures`: density sums to 1. The hazard in the bins holding 1/4, 1/2, 2/3 and 9/10 of the range is within 0.05 of 1.06, 1.22, 1.50 and 3.67.
  - `test_a_uniforms_hazard_rises_to_its_end`: monotone, the last bin's above 5.
  - `test_a_lists_profile_is_one_bar_a_value`.
  - `test_a_profile_is_computed_once_a_distribution`: call count.
  - `test_a_drawn_card_draws_its_histogram_and_hazard_against_flat`.
  - `test_the_profile_says_it_is_the_declared_distribution`.
- [ ] **Steps 2-4:** as Task 2's; commit.

### Task 4: Hard limits and warnings from the layout set (§4, the mechanism)

**Files:** Modify `wl_xcon/task.py`, `wl_xcon/check.py`, `wl_xcon/preflight.py`, `wl_xcon/taskd.py` (outside every listed item), `wl_xcon/service.py` (`_preflight`), `wl_xcon/link.py`, `wl_xcon/web.py`, `docs/design/architecture.md` (the task model: hard bounds, the layout at the values); Test `tests/test_limits.py`, `tests/test_check.py`, `tests/test_preflight.py`, `tests/test_web.py`.
**Interfaces:**
- **Every declared bound is a hard limit**, refused past, with its one-line reason. (Planner's call: after §4 a bound stands only where a value cannot be, so nothing past one is accepted.)
  - `Param.why: str = ""`: printable, one line, at most 120 characters, refused otherwise as built.
  - `task.COUNT_UNITS = ("objects", "answers", "pairings", "trials")`. `task.limit_reason(param, side) -> str | None` gives `why`, or the standard reason:
    - low 0: "below 0 cannot be";
    - low 1 on a count unit: "fewer than 1 cannot be: one is needed";
    - high 1 on `fraction`: "a fraction is at most 1".
  - `check.UNEXPLAINED_LIMIT = "unexplained-limit"`: a load warning for a bound with no reason.
- **`check.beyond_range`** gives, for a value past a bound, a **blocking** `past-limit` finding first: `'fix_hold' at -0.1 s is below its 0: below 0 cannot be`. So `Session.set`, through `_beyond_range`, and the pre-flight refuse it by their existing paths, and `set` is unchanged.
- **The layout at the values set.**
  - `check.at_values(task, values) -> Task`: each numeric setting named is pinned, `low = high = start = value`, or to a `(least, most)` span for a draw or a staircase's ends.
  - `check.LAYOUT = ("stimulus-off-screen", "overlapping-windows", "crowded-array", "answer-window-reaches-objects", "window-inside-object", "objects-touch")`; Task 6 adds `"scaled-small"`.
  - `check.laid_out(task, values, *, allocation, geometry, calibration, deployment) -> list[Finding]` runs the layout checks on `at_values(task, values)`.
  - `check_task` judges an **open side** at the setting's start. One with no start is left to the run's start: no `stimulus-off-screen` for an open range at load.
  - New warnings: `window-inside-object` (an object window's radius below its object's) and `objects-touch` (two objects closer center to center than their sizes' mean). `_overlapping_objects`' refusal is reached by no open range; §4 lists touching discs as a warning.
  - `longer-than-declared` compares with the longest wait the task's own starting values give. (Planner's call: with no declared highest, the PI's 2026-10-12 warning keeps its sense.)
- **Where it is asked.**
  - `preflight.laid_out(task, given, plan, allocation, geometry, calibration, deployment) -> list[PreflightItem]` judges at the run's values, each block's conditions, and each draw's and staircase's two ends. A blocking finding fails; the warnings are offered for acceptance at the start. `Service._preflight` adds it.
  - `Session._laid_out(changed=None, *, handed=frozenset(), ranges=None, forms=None, shaping=None, by) -> None`:
    - It judges the layout at what the run will hold after the change, composed as `_possible` composes it, for each block, condition and extreme.
    - It compares that with the layout at the values in force (`Session._laid`, kept at each boundary).
    - A new blocking finding is `Exceeded` naming it. New warnings are accepted by `by` (`accept(..., how="set")`) and said on the feed.
  - It is called from `_impossible(name, value, by=None)`. Its one call line in `_command` passes `by=command.by`; it is not listed, and the listed two stay unchanged. It is called too from `_range`, `_form`, `_hand_back` and `_revert` (and from Tasks 7 and 10).
- `ParamRow.why: dict | None` (`{"low": reason, "high": reason}`). `web._range` says `0 to 1 fraction · a fraction is at most 1`, or *no limit*.
- [ ] **Step 1: failing tests**, on fixture tasks in `tests/test_limits.py`: a ring of discs with object windows in degrees, the ranges open.
  - `test_a_value_past_a_bound_is_refused_with_its_reason`: −0.1 s, and a fraction of 1.2.
  - `test_standard_bounds_need_no_reason_and_others_are_warned_unexplained`.
  - `test_param_why_is_one_printable_line_of_120_at_most`.
  - `test_the_layout_is_judged_at_the_values_on_every_change` (Review Focus 3):
    - `set_size` raised: `crowded-array`, naming the pair and both values;
    - lowered: nothing new;
    - a ring drawn `Uniform`: judged at both ends.
  - `test_a_stimulus_set_off_the_field_is_refused_whichever_setting_moved_it`.
  - `test_a_window_smaller_than_its_disc_is_warned`, `test_touching_discs_are_warned`, `test_the_fixation_window_reaching_the_discs_is_still_warned`.
  - `test_an_open_range_is_judged_at_its_start_at_load`: a geometry given, no blocking finding.
  - `test_the_preflight_judges_the_layout_at_the_runs_values`.
  - `test_every_change_path_asks_the_layout`: set, range, form, hand back and revert, each refused for an off-field result.
  - `test_the_card_says_each_limits_reason`.
- [ ] **Steps 2-4:** as Task 2's; the hand breaks are to skip the pin and to let `past-limit` warn. `welfare_diff`: `Session.set`, both `_command` items and `link._setting` `SAME`. Commit.

### Task 5: The reference tasks' caps go (§4)

**Files:** Modify `tasks/fixation_detection.py`, `tasks/adaptive_detection.py`, `tasks/visual_search.py`, `tasks/visual_search_training.py`, `tasks/calibration.py`, the tests that read their ranges, `docs/references/decisions.md` (TSK-35 and TSK-39 revised: the builder's ranges retired 2026-11-16, the PI's "Hard limits only where impossible"); Test `tests/test_reference_limits.py`.
**Interfaces:** each bound kept only where a value cannot be, with `why` where its reason is not standard. COL-29's 80 cd/m² stays, a PI decision with its reason: "white on the default calibration, the published sRGB 80 cd/m² (COL-29)". Each test that asserted a builder range is rewritten, in the same commit, to the layout at the values it meant. None is deleted without its replacement.
- [ ] **Step 1: failing tests.**
  - `test_every_reference_tasks_bound_is_impossible_or_decided_with_its_reason`: `limit_reason` for each, no `unexplained-limit`.
  - `test_visual_search_twelve_on_a_five_degree_ring_warns_crowding_at_those_values`: TSK-39's old guard, now a warning.
- [ ] **Steps 2-4:** as Task 2's; commit.

### Task 6: Sizes scaled by eccentricity, windows as a ratio (§5)

**Files:** Modify `wl_xcon/task.py`, `wl_xcon/screen.py`, `wl_xcon/check.py`, `wl_xcon/taskd.py`, `wl_xcon/record.py`, `wl_xcon/link.py`, `wl_xcon/web.py`, `docs/design/architecture.md`, `docs/references/decisions.md` (STE-31); Test `tests/test_scaling.py`, `tests/test_screen.py`, `tests/test_record.py`, `tests/test_web.py`.
**Interfaces:**
- **The sizes.**
  - `task.size_settings(task) -> frozenset[str]`: the settings a look's `size` field names (`Disc`, `Square`, `Cross`, `Polygon`), through a look setting's choices.
  - `task.size_at(value, at) -> float`: a number as itself; a `Scaled` as factor × `geometry.polar_of_deg(*at)[0]`, measured from straight ahead (0°, 0°), where every lab task fixates. (Planner's call.)
  - `screen._item` binds a size at the item's own cyclopean place.
  - `SetForm` shape `scaled` (`factor`) is accepted on a setting in `size_settings` alone.
  - The trial's values carry `Scaled(factor)` for it; `spec.values` keeps the fixed number, so no `Scaled` reaches telemetry.
- **The windows.** `ObjectWindows.scale: float | P | None = None`.
  - Each object's window radius is `scale` × its object's radius: half its size at its own place (STE-05). It means the same whether the size is fixed or scaled.
  - Exactly one of `radius` and `scale` is declared, refused as built. A `scale` window on a look with no single `size` is refused at load (`unsized-window`).
  - `expand`, `placements` and every check read each object's own radius.
- **The warnings.**
  - `window-inside-object` for a ratio below 1.
  - `scaled-small`: a scaled stimulus at eccentricity 0 is *not drawn*; one whose size there is below its fixed value says both. (Planner's call: "near the center" made checkable against the task's own size.)
- **The record:** Task 1's `size_deg` and `window_deg`; `params[name]` is the `Scaled` form, `drawn[name]` the form's id.
- **The card.**
  - `ParamRow.switch = "scaled"` on a size setting, with its *fixed* | *scaled* switch and a factor field.
  - `ParamRow.gives: str | None`, the rig's words for each distinct eccentricity of the open placement, three at most, then "and N more": `radius 1.5° at 8° out, every object`, or `2.4° at 8° out`.
- [ ] **Step 1: failing tests.**
  - `test_size_at_is_the_factor_times_true_eccentricity`: 0.3 at (8, 0) is 2.4; at (6, 6), 0.3 × `polar_of_deg(6, 6)[0]`, never √72.
  - `test_a_scaled_array_draws_each_object_at_its_own_eccentricity`: an array about (4, 0), radius 4; the items' sizes differ, each its own.
  - `test_object_windows_by_scale_are_that_multiple_of_each_objects_radius`: 3 × 0.5 = 1.5; scaled to 2.4°, 3.6°.
  - `test_a_ratio_means_the_same_fixed_or_scaled`.
  - `test_radius_and_scale_both_or_neither_are_refused`; `test_a_scale_window_on_an_unsized_look_is_refused_at_load`.
  - `test_scaled_at_the_center_and_below_its_fixed_size_are_warned` (Review Focus 4).
  - `test_a_window_ratio_below_one_is_warned`.
  - `test_scaling_is_a_size_settings_alone`.
  - `test_the_record_writes_each_objects_size_and_window`.
  - `test_the_card_says_the_radius_each_object_gets`.
  - `test_a_scaled_size_never_reaches_telemetry_as_an_object`.
- [ ] **Steps 2-4:** as Task 2's; the hand break is an average ppd (√(x² + y²)). Commit. STE-31 (decisions.md): "Size = factor × eccentricity", the PI 2026-11-16, 0.3° per degree [@westerberg2020priming]; the window "Grows in proportion".

### Task 7: Colors by set, hue and two levels; the record (§6)

**Files:** Modify `wl_xcon/photometry.py`, `wl_xcon/screen.py`, `wl_xcon/check.py`, `wl_xcon/task.py`, `wl_xcon/link.py`, `wl_xcon/taskd.py`, `wl_xcon/record.py`, `wl_xcon/serve.py`, `wl_xcon/web.py`, `docs/backlog.md` (closes XC-420); Test `tests/test_color_card.py`, `tests/test_photometry.py`, `tests/test_record.py`, `tests/test_link.py`, `tests/test_web.py`, `tests/test_page_browser.py`.
**Interfaces:**
- **`ColorSetLight.saturation: object = 1.0`**, a number or a setting, a fraction and so hard at [0, 1].
  - Its chromaticity is apex + s × (realized xy − apex); its macaque luminance (fraction × `at()`) is held.
  - Every saturation of a realizable set is realizable: a line in xy is a line in the light's equal-luminance plane, whose intersection with the gamut is convex. The docstring says so.
  - `colorset_xyz`, `screen` and `check` read it.
  - The impossibility check reads a light at saturation 0 as its set's apex, whatever its hue.
  - `photometry.srgb_hex(xyz) -> str` gives a swatch on `SRGB`.
- **The record:** the light's form with `saturation`, each realization with `macaque_row`, `color_sets[...].design` (Task 8's field, null until then).
- **XC-420 closed.** A value that is an appearance or a color is carried in telemetry as its words, wherever one appears (`ParamRow.words`, `Staged`'s `was`/`now` through `_carried`), with `value` null.
- **The pick.**
  - `task.color_choices(param) -> dict[tuple[str, str], object] | None`: a setting's choices by (set, hue) of their light, a look's `color` or the choice itself. None unless every choice has one. A key two choices share is left out, and the load warns `ambiguous-color-choice`.
  - `link.SetColor(name, colorset, color, by)`, `KIND = "color"`. `Session._color(command, index)` maps it to the one declared choice and refuses a pick naming none.
  - It then calls `_impossible(name, choice, by)` and `set(name, choice, by)`, unchanged, as `_revert` does, catching `Exceeded`; it never raises.
- **`ParamRow.color: dict | None`.**
  - `sets` holds each set's apex, luminance, `design`, and each hue's xy and `srgb`.
  - `set` and `hue` are those of the run's value (null where the pool draws it), with `approximate: true`.
  - `saturation` and `luminance` are each `{"setting": name | None, "value": v, "cd_m2": c}`. The luminance names the light's `fraction` setting where it is one, else its `luminance` setting, which moves every light of the set, as the card says.
- **The card.** Set, then hue swatches with names, then the two levels.
  - Each level field is typed in its setting's own unit, the cd/m² beside it. (Planner's call: the fraction is what the record writes and what Fade-in's staircase steps.)
  - A level that is a number in the task file is shown as fixed there.
  - The caption: *approximate: this screen is not measured; the rig's measured panel decides what is drawn*.
- [ ] **Step 1: failing tests.**
  - `test_saturation_moves_a_light_toward_the_apex_holding_its_macaque_luminance`: s 0, 0.5 and 1; 0 is the apex xy and 0.5 the midpoint; luminance within 1e-9.
  - `test_every_saturation_of_a_realizable_set_is_realizable`: a grid, on `SRGB` and a narrow test calibration.
  - `test_both_saturations_at_zero_leave_no_odd_one` (Review Focus 5).
  - `test_a_color_pick_holds_that_sets_hue_through_set`: the card's source becomes person.
  - `test_a_pick_naming_no_choice_is_refused`.
  - `test_a_held_look_and_a_staged_one_publish_as_words`: XC-420; the frame encodes and decodes.
  - `test_the_color_card_offers_set_hue_and_two_levels_and_says_approximate`.
  - `test_a_light_records_its_saturation_and_each_realization_its_macaque_row`.
  - `test_a_reader_rebuilds_each_lights_xyz_from_the_record_alone`: Task 1's formula against `colorset_xyz`, 1e-9.
  - Browser: `test_picking_a_hue_swatch_sends_color`.
- [ ] **Steps 2-4:** as Task 2's; the hand break is to drop the apex reading. Commit.

### Task 8: New colors, three ways, saved as a set's proposed file (§6)

**Dependency choice: none new.**
- `wl_xcon/cam16.py` implements CIECAM16 forward and inverse (CIE 248:2022) and its uniform space, CAM16-UCS (Li et al. 2017), in the standard library's `math`, for one viewing condition.
- Why:
  - The rig's photometry is already plain arithmetic.
  - colour-science, which the PI's generator uses (`wl-style/02-color/isohue_spectrum/isohue.py`), is a general library brought in for four functions.
  - Agreement with his generator is the requirement, and a test proves it against his own file.
- `cam16.VIEWING` holds the conditions that generator used: colour-science 0.4.7's `XYZ_to_CAM16UCS` defaults. The builder reads them from its source and cites it with the date read; until then they are UNVERIFIED.
- ADR-0004's inventory is unchanged.

**Files:** Create `wl_xcon/cam16.py`, `wl_xcon/colordef.py`; Modify `wl_xcon/photometry.py`, `wl_xcon/link.py`, `wl_xcon/service.py` (`_route`), `wl_xcon/serve.py`, `wl_xcon/web.py`, `docs/references/library.bib` (`li2017comprehensive`, checked at its DOI by the builder before adding, as `docs/references/README.md` says), `docs/references/decisions.md` (COL-38); Test `tests/test_cam16.py`, `tests/test_colordef.py`, `tests/test_define_color.py`, `tests/test_page_browser.py`.
**Interfaces:**
- **The space.** `cam16.to_ucs(xyz) -> (J, a, b)` and `cam16.from_ucs(jab) -> xyz`, XYZ relative to a white of Y 1, the generator's frame.
- **The set's design frame.** `ColorSet.design: Mapping | None = None`, the file's optional `design`: `{"space": "CAM16-UCS", "gray_lightness": float, "chroma": float}`, refused otherwise. `COLORSET_OPTIONAL` gains it.
- **The three methods.** `colordef.METHODS = ("hue_angle", "dkl", "xy")`. `colordef.chromaticity(colorset, method, numbers) -> (x, y)`:
  - **hue_angle** (`hue_deg`), in the set's design frame, as `isohue.py`'s `reference_gray` and `colors(t, s)` do:
    - The gray is the D65 light whose macaque luminance (`SRGB_MACAQUE`) equals that of CAM16's achromatic point at `gray_lightness`.
    - a′b′ = the gray's a′b′ + chroma × (cos h, sin h). Its own design chroma is "the set's saturation".
    - J′ is bisected until the light's macaque luminance equals the gray's.
    - Refused for a set with no `design`.
  - **dkl** (`azimuth_deg`, `elevation_deg`, `contrast`): about the set's gray, the apex at the set's luminance.
    - It uses the CIE's 2° fundamentals already bundled (`cones`, `CIE_lms_cf_2deg.csv`, sha256 `f48160ed…`), the set's own observer (§6), never the lab's 10° one.
    - Its axes are built as COL-32 builds them, with the luminance axis L + M at L:M 1, which the set holds.
    - It goes to XYZ through `SRGB`'s primaries.
    - `contrast` defaults to the mean DKL radius of the set's colors. (Planner's call: the design names a direction alone, and a color needs a distance.)
  - **xy** (`x`, `y`): as given, `_chromaticity`'s rule.
  - In each, the set then holds the luminance, as every set color's.
- **The file.**
  - `colordef.proposal(colorset, name, xy, *, method, numbers, by, rig, on) -> dict`: the set's whole file with the color added. Its `source` is extended: `<name>: <method> <numbers>, defined on <rig> by <who> on <date> (wl-xcon <version>), proposed for review`. A name already in the set is refused: a set's color is never redefined from the panel. So is a name not printable or over 40 characters.
  - A new set takes the D65 apex (0.31272, 0.32900), 15 cd/m², `macaque_2deg_LM1`, and `design` when its first color is by hue angle, from the numbers given.
- **The command.** `link.DefineColor(colorset, new_set, name, method, numbers, by)`, `KIND = "define_color"`, its numbers through `_numbers(..., kind="define_color")`.
  - `Service._define_color` handles it in `_route`, in any phase.
  - It reads `<--tasks>/../stimuli/<set>.json` and writes `<--tasks>/../stimuli/proposed/<set>.json` atomically (a temporary file and `os.replace`), extending a proposal already there.
  - Refused: a set that is missing unless new, or that exists if new; and a `--tasks` with no `stimuli` folder beside it, "as wl-xtasks has".
  - Its realizability on the session's calibration, or the default, is a warning on the feed: "adding it desaturates isohue by N% on calibration X".
  - (Planner's call: never the set's own file. XC-150's pull is not built, so a rig would otherwise use an uncommitted color. The PI commits it by moving it into `stimuli/`.)
- **The preview.** `GET /color-preview?set=&method=&...` on `wlx serve` returns `{"x", "y", "srgb", "in_srgb", "said"}` by `colordef.chromaticity` on the frame's set. Any viewer may preview; it writes nothing.
- **The page.** *New color* in the color card: the method, its fields, a name, into an existing set or a new one's name, then *preview* and *save as a proposal*. It says: *saved to wl-xtasks/stimuli/proposed/isohue.json for the PI to review and commit; a rig uses it once committed and pulled*.
- [ ] **Step 1: failing tests.**
  - `test_cam16_round_trips_over_a_grid`: 1e-9.
  - `test_the_generators_gray_sits_where_its_methods_say`: #969696's J′ is 65 ± 0.01 and its a′b′ within 0.05 of (−1.4, −0.8), wl-style's METHODS.md.
  - `test_hue_angle_regenerates_the_isohue_set`: hues 260, 320, 20 and 140, chroma 29.49, gray J′ 65 (the file's own source sentence). Each xy is within 6e-5 of wl-xtasks' `stimuli/isohue.json`, which the PI's generator made under colour-science 0.4.7. This is the gate on `VIEWING`.
  - `test_dkl_at_azimuth_and_elevation_zero_lies_on_the_l_m_axis`: S and V_F,10 unmoved, 1e-9.
  - `test_xy_is_taken_as_given_and_one_no_light_has_is_refused`.
  - `test_a_proposal_is_the_sets_file_plus_the_color_and_its_source`: it loads with `ColorSet.load` and the old colors are identical.
  - `test_define_color_writes_under_proposed_and_never_the_sets_own_file`: the file's bytes unchanged.
  - `test_define_color_refuses_a_name_in_the_set_and_a_tasks_folder_without_stimuli`.
  - `test_a_color_desaturating_the_set_on_this_panel_is_warned`.
  - `test_the_preview_is_what_the_rig_would_save`.
  - Browser: `test_defining_a_color_by_hue_angle_previews_and_saves`.
- [ ] **Steps 2-4:** as Task 2's; commit. COL-38 (decisions.md):
  - the PI's three methods and "Saved into a color set file", 2026-11-16;
  - CAM16-UCS's basis, `li2017comprehensive` once added and checked, and the PI's generator;
  - the proposal folder, the planner's call.

### Task 9: The Task parameters tab in sections (§7)

**Files:** Modify `wl_xcon/task.py`, `wl_xcon/taskd.py` (`parameters`), `wl_xcon/link.py`, `wl_xcon/web.py`, `docs/references/decisions.md` (TSK-76); Test `tests/test_sections.py`, `tests/test_web.py`, `tests/test_page_browser.py`.
**Interfaces:**
- **The declaration.** `Param.section: str = ""`, named by the task file. One `/` makes a subsection (`"Stimuli/fixation point"`); it is printable, at most 60 characters and two levels, refused otherwise as built.
  - `task.section_of(param) -> str` gives its own, else `task.TIMING = "Timing"` for unit `s`, else `task.OTHER = "Other"`.
  - `task.TRAINING_SECTION = "Training"`: a section under it goes to the Training tab (Task 10).
- **The row.** `ParamRow.section: str`. `ParamRow.changed: bool` is true where it differs from the task's start: a person holds it, a range or a form a person gave is in force, or the run's value is not the task's start.
- **The page.** Sections in the order their first setting is declared, subsections nested, each a collapsible `<details>` headed `Timing · 7 settings · 2 changed`.
  - A find box on top filters cards by name and opens their sections.
  - Each section opens as last left, per task, in `localStorage` under `wlx.sections.<task>`, inside `try`, so a store that throws leaves every section open.
- [ ] **Step 1: failing tests.**
  - `test_a_settings_section_falls_back_to_timing_by_unit_then_other`.
  - `test_param_section_is_one_printable_line_of_two_levels_at_most`.
  - `test_cards_are_grouped_in_declared_order_each_header_counting`.
  - `test_a_changed_setting_counts_in_its_sections_header`.
  - Browser:
    - `test_the_find_box_finds_a_setting_in_a_collapsed_section_and_opens_it`;
    - `test_sections_open_as_last_left_per_task`;
    - `test_a_store_that_throws_leaves_every_section_open`.
- [ ] **Steps 2-4:** as Task 2's; commit.

### Task 10: The Training tab and its three-position switch (§8)

**Files:** Modify `wl_xcon/task.py`, `wl_xcon/check.py`, `wl_xcon/scheduler.py`, `wl_xcon/taskd.py`, `wl_xcon/link.py`, `wl_xcon/record.py`, `wl_xcon/serve.py`, `wl_xcon/web.py`, `docs/design/architecture.md`, `docs/references/decisions.md` (TSK-77; TSK-70 amended: the switch is reverted); Test `tests/test_shaping.py` (a fixture task with a confirmed progression, two staircases, a pool and a `Plan.full`), `tests/test_web.py`, `tests/test_page_browser.py`.
**Interfaces:**
- **The declaration.** `task.FullTask(block: str, values: dict)`, `values` empty by default (`field(default_factory=dict)`); `Plan.full: FullTask | None = None`.
  - The task's finished version: its `block`, every staircase held at its hardest level, `values` over its conditions, each marked `drawn: "full"`.
  - Checked at load (`bad-full-task`): a block the plan has, settings the task declares, values inside their limits, a pool's value naming a pool.
- **The command.** `task.SHAPING = ("on", "frozen", "full")`. `link.Shaping(position, by)`, `KIND = "shaping"`, and `Session._shaping(command, index)`.
  - Refused: a position not in `SHAPING`; the one already set; `full` for a plan with none; any position in a run with no progression, staircase or pool.
  - It is staged as `Pending("shaping", ...)`. At the boundary it is applied with `_possible` and `_laid_out` asked first: a `shaping` change row, `Moment.shaping`, so a revert takes it back.
- **Frozen.** `Scheduler.freeze(on)`.
  - No criterion or fall-back is judged, no suggestion is offered, and no staircase steps.
  - A standing suggestion is withdrawn as `_lapse` withdraws one.
  - A frozen trial enters neither the stage's bars nor a staircase's runs.
  - A person's own move, value or hand-back still applies.
  - Each card the staircase or pool gives says `frozen at 0.6` (source `"frozen"`).
  - (Planner's calls, from "the experimenter needs free control".)
- **Full.** The run enters `full.block` as a block of its own, with no moves. On again, the stage left reopens at its staircase's level, as "Pick up where it left" has it.
- **The wire.** `Telemetry.shaping: str` and `Telemetry.full_task: bool`; each trial line's `shaping`.
- **The page.**
  - A **Training** tab (`t-training`, `tp-training`) holds the switch, *on · frozen · full task*, its *full task* grayed with why where the plan declares none.
  - It holds today's `rt-train` panel, moved, and the cards of every section under `Training`.
  - The Runtime tab keeps one line, `rt-shaping`: `training frozen · stage Crowd · Training tab`, so nothing is hidden.
- [ ] **Step 1: failing tests.**
  - `test_frozen_makes_no_move_no_suggestion_and_no_step`: 100 correct trials frozen in Fade-in leave it there, at its level, with no `suggested` row.
  - `test_frozen_trials_count_toward_no_bar`.
  - `test_a_standing_suggestion_is_withdrawn_on_freezing`.
  - `test_a_persons_move_still_applies_while_frozen`.
  - `test_full_task_plays_its_block_at_its_hardest_with_its_values`.
  - `test_on_after_full_reopens_the_stage_left_at_its_level`.
  - `test_full_is_refused_for_a_plan_declaring_none`.
  - `test_a_shaping_switch_is_staged_recorded_and_reverted`.
  - `test_a_bad_full_task_is_refused_at_load`.
  - `test_each_trial_line_says_its_shaping`.
  - `test_the_training_tab_holds_the_switch_the_panel_and_the_training_sections`.
  - `test_runtime_says_the_switch_in_one_line`.
  - Browser: `test_freezing_from_the_training_tab_sends_shaping`.
- [ ] **Steps 2-4:** as Task 2's; commit.

### Task 11: wl-xtasks: the pop-out's sections, its caps, its window as a ratio

**Files:** wl-xtasks, on branch `console-settings-2026-11-16`: Modify `tasks/popout_search.py` and `stimuli/isohue.json` (`design`: gray lightness 65, chroma 29.49, from its own source sentence). In wl-xcon, Modify `tests/test_popout_search.py`.
**Interfaces:**
- **The sections** (the companion's §5, the training ones split):
  - Timing: the six times, by unit;
  - Gaze windows: `fix_window`, `object_window`;
  - `Stimuli/fixation point`: `fix_size`, `fix_luminance`;
  - `Stimuli/array`: `disc_size`, `ring_radius`, `set_size`, `array_rotation`;
  - Colors: `odd_color`, `distractor_color`, `color_luminance`, `distractor_fraction`;
  - Pairings: `pairings`;
  - `Training/bars`: the four bars;
  - `Training/staircases`: the counts, steps and floors;
  - `Training/suggestions`: `suggestion_margin`.
  - *Special trials* is the second plan's.
- **The bounds.** Each is kept only where a value cannot be, with its reason where it is not standard:
  - `array_rotation` 0 to 360, "a direction, written from 0 to 360 (the PI, 2026-10-30)";
  - `fix_luminance`'s 80, COL-29;
  - `pairings` low 1, its pool's own refusal past its pairings.
- **The window.** `ObjectWindows(of="search", scale=P("object_window"))`; `Param("object_window", unit="× disc radius", low=0.0, start=3.0, section="Gaze windows")`.
- The comments that cite the removed ranges are rewritten to the layout warnings.
- [ ] **Step 1: failing tests** in `tests/test_popout_search.py`:
  - `test_the_popout_declares_the_companion_designs_sections`;
  - `test_the_popouts_bounds_are_impossible_ones_with_reasons`;
  - `test_the_popouts_object_window_is_three_times_a_discs_radius`: 1.5° at the start, as before;
  - `test_the_popout_loads_with_no_layout_warning_at_its_starts`;
  - `test_isohue_carries_its_design_frame`.
- [ ] **Steps 2-4:** as Task 2's. The wl-xtasks commit stays on its branch; its review with the PI is asked with the build's merge.

### Task 12: The documents, the backlog and the CHECKPOINT

**Files:**
- the console spec, the S8 spec's settings section and the engine spec §14 (each a dated note pointing here);
- `docs/pitfalls.md` (a range proof fails closed once its cap goes: judge at the values);
- `docs/roadmap.md`;
- `docs/backlog.md`: each deferred item a line; XC-513 stays until wl-preproc answers;
- `docs/CHECKPOINT.md`, rewritten in place.
- [ ] **Step 1:** write. `tests/test_backlog.py`, `tests/test_references.py` and the full suite pass; commit.
- [ ] **Then:** one review of the whole build, by the most capable model. Then the wl-xtasks branch is reviewed with the PI. Then the merge ask, by his yes and a clean CI.
