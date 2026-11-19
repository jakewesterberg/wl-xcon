# The Console's Interface Rework Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
> **The PI's process rule (2026-11-07) overrides the skill**: a plan is a design and a list of tests, built once; a
> fresh builder per task, no per-task review, one whole-build review, his Safari try-out, his merge.

**Goal:** Make the console's settings small boxes that send nothing until Apply, with plain names, whole numbers,
a pairings grid, group boxes, withdraw and Apply all, as the PI approved on 2026-11-19.

**Architecture:** The rig declares more on each setting's row (whole, step, label, help, group, choices, start, pool
members, verdicts keyed to a page-made command id); two new commands (apply several, withdraw) sit beside
`SetRange`'s in `Session._command`; the page is rebuilt around a three-zone box with a draft map, patched box by box.
The task file declares labels, help, whole numbers and groups.

**Tech Stack:** Python 3.11 (CI's floor), the page's own server-rendered HTML, CSS and script in `wl_xcon/web.py`,
Playwright (Chromium and WebKit) for browser tests. No new dependency.

**Spec:** `docs/superpowers/specs/2026-11-19-console-interface-design.md` (approved). The reviews it rests on, with
file:line facts: `.superpowers/sdd/2026-11-16-console-settings/ui-review/{layout,controls,workflow}.md`, the mock-up
`ui-review/shots/layout/mockup.html`.

## Global Constraints

- **CLAUDE.md binds every task.** US English. Sim first. No timing claim without a measurement. Each new test seen
  failing first, then by a hand break after the fix (file restored, sha256 checked). Docs in sync in the same commit
  (architecture.md's console rows and task model). The full suite in each commit's `&&` chain, `set -o pipefail`, the
  log to a file. Python 3.11: no backslash or the f-string's own quote inside a replacement field.
- **No welfare-listed item changes** (`tests/welfare_manifest.json`; `python3 tools/welfare_diff.py 89f7b94 HEAD`
  read before each commit, every item `SAME`, no `CHECK CHANGED`): `taskd.Session.set`; `link._setting` (every new
  decoder calls it); `Session._command`'s listed first statement and its listed `except (Exceeded, TypeError) as
  refused:` line (new branches beside `SetRange`'s; no new branch writes a second such line); `service.Service._start`,
  `preflight.gate`, `Session._schedule`, `_hold`, `_ends`, `_manual_reward`, `OUTSIDE_A_RUN`. **A task that finds it
  needs a listed change stops and reports the exact change.**
- **A reward size is never in Apply all and never withdrawn** (the design's call; XC-527): a bounded (ceiling)
  setting in an apply-several or a withdraw is refused by the page and by the rig, with a sentence.
- **The whole-number refusal is made where `_impossible` judges a change** (non-listed), never in `Session.set`.
- **Telemetry schema 22 → 23, once** (Task 3); later tasks add fields to 23 before the merge.
- **The record**: wl-preproc is told every new shape before any is written (Task 1 before Task 4). Each change still
  writes its own row as today.
- **Safari**: every page declares UTF-8 first; every browser test runs in Chromium in the suite and in WebKit
  (`WLX_BROWSER=webkit`) by the builder, both counts in the report.
- **Words on the page** (the design): *not sent* · *sending…* · *waiting for the next trial · <who>* · *in force from
  trial N* · *in force, with a warning* · *refused <value> · <one line>* · *cannot send · <why>*; a word beside every
  icon; color never the only signal. Apply all's bar: `N edits not sent: <names> · Discard all · Apply all`.
- **Limits**: `task.LABEL_LIMIT = 40`, help at most `task.REASON_LIMIT` (120), both printable, one line, refused as
  built.
- **Step defaults** (the design's call; `task.UNIT_STEPS`): `s` 0.05, `deg` 0.1, `mL` 0.01, `cd/m2` 1.0, `fraction`
  0.05, `× disc radius` 0.1, `%` 1.0; a whole setting steps by 1; any other unit 0.01; Shift+click ×10.
- **wl-xtasks is curated with the PI**: Task 9 is a commit on the wl-xtasks branch `console-settings-2026-11-16`,
  reviewed with him before it merges. Dates are the local day (US Eastern `date`).

## Review Focus

1. **A frame lands while a trainer presses or types in a box**, for each control (field, −/+, segment, tick, swatch,
   Apply, withdraw, hand back): the press acts once and the box shows the frame's news after (Task 6).
2. **Apply all with one change the rig refuses**: nothing is staged, every box in it says *refused* with its own
   reason or "refused with <name>" (Task 4, Task 6).
3. **Withdraw after the boundary passed**: the change is already in force; the rig refuses with "already in force
   from trial N" and the box shows *in force* (Task 4).
4. **Someone else changes a setting under a trainer's draft** (another console, a staircase, a revert): the draft is
   untouched, the head shows the new value in force, the status says who changed it (Task 6).
5. **A whole setting given `4.5`** by paste or by a hand-made POST: the page refuses it as *cannot send*; the rig
   refuses it with a sentence if it arrives anyway (Task 3, Task 6).

---

### Task 1: Ask wl-preproc for the withdrawal row (and Apply all's, if any)

**Files:** Modify `docs/pending-wl-preproc-amendments.md` (a new section, XC-number from the backlog's Next free),
`docs/backlog.md` (the ask's line).
**Interfaces:** Produces the accepted names Task 4 writes.
- [ ] **Step 1:** read `record.py` (`KINDS`, `STROBED`, `change()`), `Session._staged`/`_apply_staged`, and when a
  `set` row is written (staged or applied). Draft: kind `withdrawn` appended after `shaping`; whether it strobes
  (it changes nothing on screen: the design expects not); its `was`/`now`; the command id it withdraws and the names
  it covers; `by` and `at`. Decide from the code whether Apply all needs a shared marker on its rows (the design's
  "our call"); if so, draft it.
- [ ] **Step 2:** commit the ask behind the suite. The controller sends it and builds to these names until the answer.

### Task 2: The task declares labels, help, whole numbers, steps, percent display and groups

**Files:** Modify `wl_xcon/task.py`, `wl_xcon/check.py`, `wl_xcon/declarations.py` (defaults; raise `FORMAT` only if a
field's default changes a task's behavior), `docs/design/architecture.md`. Test: `tests/test_labels.py` (new).
**Interfaces:** Produces `Param.label: str = ""`, `Param.help: str = ""`, `Param.whole: bool = False`,
`Param.step: float | None = None`, `Param.percent: bool = False`; `task.Group(name: str, settings: tuple[str, ...],
sentence: str = "")`, `Task.groups: tuple[Group, ...] = ()`; `task.LABEL_LIMIT = 40`; `task.UNIT_STEPS` (Global
Constraints); `task.step_of(param) -> float`.
- [ ] **Step 1: failing tests** in `tests/test_labels.py`:
  - `test_a_label_is_one_printable_line_of_40_at_most` and `test_help_is_one_printable_line_of_120_at_most`;
  - `test_a_whole_setting_declares_whole_start_low_and_high` (start 4.5 refused as `bad-whole`; low 1, high 36 pass);
  - `test_the_step_comes_from_the_unit_unless_declared` (each `UNIT_STEPS` entry; whole → 1; declared 0.01 wins);
  - `test_percent_is_for_a_fraction_only` (`percent=True` on unit `s` refused as built);
  - `test_a_group_names_settings_the_task_has_each_once` (unknown name `bad-group`; one setting in two groups
    `bad-group`; a ceiling in a group `bad-group`, since a reward size is never applied with others);
  - `test_a_groups_sentence_places_each_of_its_settings_once` (`"Move up when at least {move_up_bar} of the last
    {move_up_window} answers are right"` passes; a missing or unknown place refused).
- [ ] **Steps 2-4:** RED, build, GREEN; the reference tasks declare `whole=True` on their counts (set sizes, staircase
  counts) and nothing else.

### Task 3: Each row says what a box needs; verdicts carry the page's command id

**Files:** Modify `wl_xcon/link.py` (`ParamRow`, `Staged`, `Refused`, `SCHEMA = 23`, encoders and decoders),
`wl_xcon/taskd.py` (rows; `_impossible` gains the whole-number refusal; verdict ids), `wl_xcon/serve.py` (the command
envelope's `cid`). Tests: `tests/test_link.py`, `tests/test_taskd.py`.
**Interfaces:** Consumes Task 2's fields. Produces on `ParamRow`: `whole: bool`, `step: float`, `choices:
tuple[str, ...]` (at most `link.CHOICES_LIMIT = 30`, else empty), `start: object`, `label: str`, `help: str`,
`group: str | None`, `percent: bool`, `members: tuple[PoolMember, ...] | None`, `applied: Applied | None`,
`warned: tuple[str, ...]`; `link.PoolMember(bit: int, odd: str, among: str, odd_hex: str, among_hex: str, on: bool)`;
`link.Applied(trial: int, by: str)`; `Staged.cid: str | None`, `Staged.warnings: tuple[str, ...]`; `Refused.cid:
str | None`, `Refused.value: object`. A command's `cid` (≤ 64 printable characters, page-made) rides the POST
envelope beside the command, never inside `link._setting`.
- [ ] **Step 1: failing tests:**
  - `test_link.py::test_a_row_carries_what_a_box_needs_over_the_wire` (each new field round-trips; schema 23);
  - `test_link.py::test_the_pool_row_lists_its_pairs_as_data` (the pop-out's 12 members, bits 1..2048, odd/among
    names and `#rrggbb` swatches, `on` matching the value 66);
  - `test_taskd.py::test_a_verdict_names_the_command_it_answers` (a staged and a refused change echo the cid; the
    refusal carries the value refused);
  - `test_taskd.py::test_a_staged_change_carries_its_warnings` (a crowding `set_size` staged with its warning);
  - `test_taskd.py::test_a_row_says_the_trial_its_value_took_effect` (`applied.trial` after the boundary);
  - `test_taskd.py::test_a_whole_setting_refuses_a_fraction_with_a_sentence` (`set_size` 4.5 refused, nothing staged;
    Review Focus 5).
- [ ] **Steps 2-4:** RED, build, GREEN. If echoing a cid or a value on `Refused` can only be done in a listed line,
  stop and report the exact change (Global Constraints).

### Task 4: Two commands: apply several together, and withdraw a waiting change

**Files:** Modify `wl_xcon/link.py` (`ApplyMany`, `Withdraw`), `wl_xcon/taskd.py` (two branches beside `SetRange`'s),
`wl_xcon/record.py` (the `withdrawn` kind and any Apply all marker, as Task 1's accepted ask names them),
`wl_xcon/serve.py`, architecture.md. Tests: `tests/test_apply_withdraw.py` (new), `tests/test_link.py`.
**Interfaces:** Consumes Task 3's cid. Produces `link.ApplyMany(changes: tuple, cid: str, by)` (each change a
`SetParameter`, `SetForm`, `SetRange` or `SetColor`, at most 64; judged together as `Revert` judges its changes:
refused whole, nothing staged) and `link.Withdraw(cid: str, by)` (takes back the whole act of that cid while it
waits; refused once applied).
- [ ] **Step 1: failing tests** in `tests/test_apply_withdraw.py`:
  - `test_applied_together_they_take_effect_on_the_same_trial` (`fix_hold` and `response_deadline`, one boundary);
  - `test_one_refusal_refuses_the_whole_apply` (Review Focus 2: nothing staged, each name refused with its reason or
    "refused with fix_hold");
  - `test_a_reward_size_is_never_applied_with_others` (`reward_correct` in an `ApplyMany` refused whole);
  - `test_a_waiting_change_withdrawn_never_takes_effect_and_is_recorded` (the `withdrawn` row as accepted);
  - `test_withdraw_takes_back_the_whole_act` (one cid, three names, all withdrawn);
  - `test_withdraw_after_the_boundary_is_refused_as_in_force` (Review Focus 3: "already in force from trial N");
  - `test_a_reward_size_cannot_be_withdrawn`;
  - `test_link.py::test_apply_many_and_withdraw_round_trip_and_call_setting` (each decoded change through
    `link._setting`).
- [ ] **Steps 2-4:** RED, build, GREEN; welfare_diff read.

### Task 5: The box, drawn: three zones, plain names, whole fields, nothing past its edge

**Files:** Modify `wl_xcon/web.py` (the Python that renders a box: `_params`, `_training_params`, `_sections`,
`_color_card`, `_drawn_side`, `_scaled_side`, `_range_editor`, `_whence`, `_beneath`, the CSS; Runtime's "Still
needed"). Tests: `tests/test_web.py`, `tests/test_page_browser.py`.
**Interfaces:** Consumes Task 3's rows. Produces the box markup Tasks 6-8 script: `<div class="box" data-card="<name>">`
with zones `.head` (label, code name small, the value in force), `.editor` (field with −/+ and unit, the form
switch), `.status` (one reserved line, Apply and Discard right, `visibility` hidden until a draft), and `.more`
(a `<details>` opened in place: limits and reasons, source, the full refusal or warning, hand back, profile).
- [ ] **Step 1: failing tests:**
  - `test_web.py::test_a_box_shows_its_plain_name_and_code_name` (label, code name small; code name alone where no
    label);
  - `test_web.py::test_a_whole_box_shows_no_decimals_and_steps_by_one` (`set_size` `4`, `step="1"`,
    `inputmode="numeric"`);
  - `test_web.py::test_a_box_keeps_its_reasons_behind_more` (limits, source and refusal text inside `.more` only;
    the status line at most one line);
  - `test_web.py::test_every_field_says_its_unit_the_drawn_side_too`;
  - `test_page_browser.py::test_no_text_passes_its_box_at_three_widths` (1024, 1280, 1440: no box's descendant has
    `scrollWidth > clientWidth` or a right edge past the box; the color boxes included);
  - `test_page_browser.py::test_the_first_setting_starts_within_260px_at_1280x800`;
  - `test_web.py::test_runtime_still_needed_reads_as_words` (no one-letter-per-line layout).
- [ ] **Steps 2-4:** RED, build, GREEN; WebKit run by hand.

### Task 6: Drafts, Apply, Apply all, withdraw, and a frame that never eats a press

**Files:** Modify `wl_xcon/web.py` (`_SCRIPT`). Tests: `tests/test_page_browser.py`.
**Interfaces:** Consumes Task 5's zones, Tasks 3-4's cid, verdicts and commands. Produces the page-side draft map by
setting name; `applyBox(name)`, `applyAll()`, `withdraw(cid)`, `patchCards(fragment)`; the six old send paths
(600 ms field and arrow sends, *change the range*, form *apply*, a hue's click) removed; *hand back*, the training
switch, *revert to this* and *lock at* still act at once; drafts kept across frames and tab switches, dropped at
the run's end and on a reload, and closing the page with drafts asks once (`beforeunload`).
- [ ] **Step 1: failing tests** (each in Chromium; WebKit by the builder):
  - `test_nothing_is_sent_until_apply` (typing, −/+, a segment: no POST; the box says *not sent*);
  - `test_enter_applies_and_escape_undoes`;
  - `test_a_draft_equal_to_the_value_in_force_is_no_draft`;
  - `test_the_box_walks_through_its_states` (not sent → sending… → waiting for the next trial · you → in force from
    trial N; and refused <value> · reason, the draft kept; and in force, with a warning);
  - `test_a_later_accepted_change_clears_the_refusal`;
  - `test_apply_all_sends_one_command_and_both_take_effect_on_one_trial`;
  - `test_a_reward_box_is_left_out_of_apply_all_and_says_so`;
  - `test_withdraw_on_one_box_says_it_takes_back_the_whole_act`;
  - `test_a_change_under_a_draft_leaves_the_draft_and_says_who` (Review Focus 4);
  - `test_a_press_during_frames_acts_once` parametrized over field, −/+, segment, tick, swatch, Apply, withdraw,
    hand back, with a frame that changes the box's head and a neighbor (Review Focus 1);
  - `test_tab_reaches_apply_on_every_box` (WebKit);
  - `test_drafts_survive_a_tab_switch_and_are_dropped_at_the_runs_end`;
  - `test_a_whole_box_refuses_a_point_at_the_keyboard_and_on_paste` (Review Focus 5).
- [ ] **Steps 2-4:** RED, build, GREEN; WebKit by hand; the earlier hold tests kept passing or rewritten to the
  per-box rule with their docstrings saying why.

### Task 7: Pairings as a grid, group boxes, percents, and one New color panel

**Files:** Modify `wl_xcon/web.py` (rendering and script). Tests: `tests/test_web.py`, `tests/test_page_browser.py`.
**Interfaces:** Consumes Task 3's `members`, `group`, `percent`; Task 6's drafts. Produces the pool's grid (odd color
down, distractor across, diagonal empty, swatches, ticks a draft, two columns wide, in the Colors section); a group
box (its title, its settings' fields in its sentence where it has one, one Apply sending an `ApplyMany`); a percent
field (shown ×100 with `%`, limits and steps converted, the command and record in the fraction); the *New color…*
panel once per Colors section.
- [ ] **Step 1: failing tests:**
  - `test_page_browser.py::test_pairings_are_a_grid_of_twelve_ticks` (66 shows blue/red and red/blue ticked; ticking
    green among red and Apply sends 66 + 2048; unticking sends less: add and remove live);
  - `test_page_browser.py::test_a_group_box_applies_its_settings_together` (one `ApplyMany`);
  - `test_web.py::test_a_groups_sentence_reads_with_its_fields_in_place`;
  - `test_page_browser.py::test_a_percent_field_shows_80_and_sends_0_8`;
  - `test_web.py::test_one_new_color_panel_per_colors_section`.
- [ ] **Steps 2-4:** RED, build, GREEN; WebKit by hand.

### Task 8: The page around the boxes: one bar, find, counts, pins, the demo panel

**Files:** Modify `wl_xcon/web.py`. Tests: `tests/test_web.py`, `tests/test_page_browser.py`.
**Interfaces:** Consumes Tasks 5-7. Produces the sticky top bar (state, trial, correct, fluid, cage time, the run's
buttons; the session's details behind a *session* button); the find box matching label, code name and section, on
both settings tabs; section headers counting changed and not sent, and the tab label marked while drafts exist; a
pin on every box and a Runtime "Pinned" strip of working copies, kept per task in `localStorage` (wrapped in
try/catch; nothing pinned by default); the demo's keys and caveats folded to one line, open on the first visit only.
- [ ] **Step 1: failing tests:**
  - `test_page_browser.py::test_the_top_bar_stays_in_view_while_settings_scroll`;
  - `test_page_browser.py::test_find_matches_a_plain_name_a_code_name_and_a_section`;
  - `test_web.py::test_a_section_counts_its_unsent_drafts`;
  - `test_page_browser.py::test_a_pinned_box_works_on_runtime_and_survives_a_reload` (and nothing pinned at first);
  - `test_page_browser.py::test_the_demo_keys_fold_after_the_first_visit`.
- [ ] **Steps 2-4:** RED, build, GREEN; WebKit by hand.

### Task 9: wl-xtasks: the pop-out's names, sentences, whole numbers and groups

**Files:** wl-xtasks branch `console-settings-2026-11-16`: Modify `tasks/popout_search.py`. In wl-xcon Modify
`tests/test_popout_search.py`.
**Interfaces:** Consumes Task 2's declarations. Each setting gets a `label` and a `help` sentence (drafted here,
reviewed with the PI on the branch); counts `whole=True` (`set_size`, `pairings`, the windows, counts, steps and
floors); the bars `percent=True`; groups: "Move up" (`move_up_bar`, `move_up_window`), "Move back" (`move_back_bar`,
`move_back_window`), "Staircase" (`staircase_down`, `staircase_up`), each with its sentence; `pairings` moved into
the Colors section.
- [ ] **Step 1: failing tests** in `tests/test_popout_search.py`: `test_every_popout_setting_has_a_label_and_help`,
  `test_the_popouts_counts_are_whole`, `test_the_popouts_training_rules_read_as_sentences`,
  `test_pairings_sit_with_the_colors`.
- [ ] **Steps 2-4:** as Task 2's; two commits (wl-xtasks, then wl-xcon), each behind the suite.

### Task 10: Documents, backlog, CHECKPOINT; screenshots for the PI

**Files:** architecture.md (console rows, the commands), `docs/pitfalls.md` (one line: a page that sends on a timer
records half-way values; send on Apply), the console settings design (a dated note pointing here), `docs/backlog.md`,
`docs/CHECKPOINT.md` (rewritten in place), and a backlog line for the pop-out revision plan (branch
`tryout-design-2026-11-17`): its special trials are declared as one `task.Group` after Timing, whole percentages. Screenshots re-taken in WebKit at 1024, 1280, 1440 into the git-ignored
`ui-review/shots/after/`.
- [ ] **Step 1:** write; `tests/test_backlog.py`, `tests/test_references.py` and the full suite pass; commit.
- [ ] **Then:** one whole-build review (the most capable model), the PI's review of the wl-xtasks branch (labels and
  sentences), his Safari try-out, push, CI, his merge yes by name.
