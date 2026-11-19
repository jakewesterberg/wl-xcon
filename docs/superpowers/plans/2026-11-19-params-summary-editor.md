# The settings tabs as a summary and one editor: implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **The PI's process rule of 2026-11-07 governs:** "a plan is a design and a list of tests, built once"; a fresh builder per task, no per-task review, one review of the whole build. The PI said (2026-11-19) not to ask him for more input until this and the pop-out's revision are built: a question goes to `.superpowers/questions-for-pi.md`; a welfare-listed change still stops for him.

**Goal:** Replace the settings tabs' box grid with a summary of every setting at the top (one line each, by section, in columns) and one editor below that opens the clicked setting, keeping every behavior the boxes have.

**Architecture:** Every setting keeps its `div.box[data-card]` exactly as now (drafts, `patchCards`, `judge`, pins and their tests keep working), rendered into an editor area where only the opened box shows. A new Python-rendered summary (`web._summary`) puts one line per box above it, from the same rows; the page script adds only what it alone knows (a draft, *sending…*, a refusal it has cleared) to each line, and opens, finds and steps through lines.

**Tech Stack:** Python 3.11+ (`wl_xcon/web.py`: rendering, CSS, `_SCRIPT`), pytest, Playwright (Chromium in the suite, WebKit by hand).

**Spec:** `docs/superpowers/specs/2026-11-19-params-summary-editor-design.md`. It builds on `docs/superpowers/specs/2026-11-19-console-interface-design.md` (behavior unchanged). The mock-up the PI chose: `.superpowers/brainstorm/72350-1795122043/content/params-a-vs-c.html`, option A.

## Global Constraints

- No change to what a setting means, its limits, what the page sends, the rig's commands, the record, telemetry's schema (23) or any welfare-listed item (`python3 tools/welfare_diff.py 89f7b94 HEAD` at every commit, read: all `SAME`, no `CHECK CHANGED`).
- Every existing test of a box's behavior keeps passing; a test is rewritten only where it reads the old grid's layout, and none is deleted without its replacement named in the report.
- The summary line's value is the rig's (rendered in Python from the row); the page adds only draft, sending/withdrawing, not-confirmed and cleared-refusal marks, and a draft's text read from the opened box's own fields (never a second number formatter in the script).
- Marks, in precedence, at most two after the name: refused `!`, draft `●`, sending or withdrawing `…`, not confirmed `?`, waiting `◷`, warning `⚠`; `◆` (drawn each trial) always shown; every state present said in words in the line's `title`. Color is never the only signal.
- Draft text on a line: one number field → "in force → typed unit"; a draw → "in force → shortest–longest unit"; a pool → "in force → N of 12"; a color, a group, a shape or a switch alone → "in force → edited"; a draft that cannot send → the typed text, *cannot send* in the title, mark `!`.
- Opening a setting changes nothing above the editor; summary lines keep their height whatever their state (cut with an ellipsis, the whole in the title).
- At 1280 × 800 with the demo screen's column shown, no banner, the drafts bar fixed at the foot: the first summary line within 260 px of the page's top, and every Task parameters line of the pop-out above 800 px. The summary is designed for up to about 45 lines in four columns (a line about 20 px).
- No horizontal page scroll at 1024, 1280 or 1440; columns drop as the page narrows.
- The opened setting per task in `localStorage` (`wlx.opened.<task>`), every access in try/catch, the page correct with storage absent or throwing.
- Safari: UTF-8 declared (already); every test of a press or key in Chromium and in WebKit (`WLX_BROWSER=webkit`).
- US English. No timing claim without a measurement. Every number a console setting (unchanged here).

## Review Focus

1. **A frame arrives while a line is pressed or the editor is mid-edit**: the press acts once, the opened box keeps its nodes, and the summary line updates without stealing focus (Task 2's test `test_a_frame_during_a_press_on_a_line_opens_it_once`).
2. **The opened setting disappears** (a new task or run without it, a group regrouped): the editor falls back to its "click a setting above to change it" placeholder; the stored name is dropped, no error (Task 1's `test_an_opened_setting_that_is_gone_shows_the_placeholder`).
3. **A draft over a change already waiting** shows `●◷` with both said in the title (Task 2's `test_a_draft_over_a_waiting_change_shows_both_marks`).
4. **Find with no match / Enter on no match** dims everything and opens nothing, saying "no setting matches" (Task 2's `test_find_with_no_match_opens_nothing`).
5. **A refused draft after switching settings**: the refusal mark stays on its line while another setting is opened, and opening it again shows the refusal and the draft back (Task 2's `test_a_refusal_stays_on_its_line_while_another_is_open`).

---

### Task 1: The summary and the editor, drawn; a click opens a setting

**Files:** Modify `wl_xcon/web.py` (`_params`, `_training_params`'s use of it, `_sections`, CSS, `_SCRIPT`). Tests: `tests/test_web.py`, `tests/test_page_browser.py`.

**Interfaces:**
- Consumes: `_box` and `_group_box` unchanged; `ParamRow` (label, value, unit, whole, percent, section, group, switch, shape, members, changed, words, position); `Telemetry.groups`.
- Produces:
  - `web._summary(frame: Telemetry, view: View, training: bool) -> str`: `<div class="summary" data-task=…>` holding, per section in `_sections`' order (Ceilings last), `<div class="ssec" data-section=…><h4>NAME · N settings</h4>` and one `<button type="button" class="line" data-open="NAME" title="…"><span class="mk"></span><span class="ln">plain name</span><span class="lv">value</span></button>` per box (a group: `data-open` its title, `ln` the title, `lv` its settings' values joined by " · "). `data-open` equals the box's `data-card`.
  - `web._summary_value(row) -> str`: the rig's value text: a number at the box's decimals with its unit (a percent ×100 `%`, a whole with none); a draw "a–b unit" (`ParamRow.shape` in force); conditions' values "from conditions"; a pool "N of 12"; a color "from pairings" or its color's word; a position its words; a ceiling its value.
  - Python-known marks in `span.mk` and the line's classes: `◆` (`drawn`), `◷` (`waiting`, a staged change), `⚠` (`warned`), `!` (`refused`, as the box's `_status` ranks it today), `changed`, `ceiling`.
  - `#params` / `#training-params` fragment = summary, a legend line (`div.legend`: "● not sent · ◷ waiting for the next trial · ◆ drawn each trial · ! refused · ⚠ with a warning"), then `div.editor` holding every box (and each New color… panel) with `hidden` on all but the opened; `div.editor > .placeholder` "click a setting above to change it" when none is opened.
  - A section holding a color card has a `<button class="line newcolor" data-open="new-color:SECTION">New color…</button>` after its lines, opening that section's New color… panel in the editor (the design's "Colors" call). Sections no longer collapse (no `<details>` in the summary); `applySections` and `wlx.sections.<task>` are retired, said in the report.
  - Script: `openSetting(name)` (shows that box, hides others, `aria-pressed` on its line, stores `wlx.opened.<task>`), `openedName()`; restore on load and after every `patchCards`.
- [ ] **Step 1: failing tests:**
  - `test_web.py::test_the_summary_has_a_line_for_every_box_in_section_order` (a fixture task with a plain number, a whole, a percent, a draw, a pool, a color, a group and a ceiling: one `.line` each, in section order, Ceilings last, `data-open` equal to each box's `data-card`, values `"1.00 s"`, `"4"`, `"80%"`, `"0.5–1.25 s"`, `"2 of 12"`, …).
  - `test_web.py::test_a_line_marks_what_the_rig_knows` (`◆` on a drawn row, `◷` on a staged one, `!` on a refused one, `ceiling` class on a reward size).
  - `test_page_browser.py::test_a_click_opens_a_setting_and_nothing_above_moves` (every line's bounding box identical before and after opening three settings in turn; only the clicked box visible in `.editor`).
  - `test_page_browser.py::test_the_opened_setting_survives_a_frame_and_a_reload`.
  - `test_page_browser.py::test_an_opened_setting_that_is_gone_shows_the_placeholder` (Review Focus 2).
  - `test_page_browser.py::test_a_group_line_opens_its_sentence` (one Apply; `ApplyMany` as today).
  - `test_page_browser.py::test_new_color_opens_from_the_colors_section`.
  - Rewrite `test_the_first_setting_starts_within_260px_at_1280x800` to the first `.line`; add `test_every_popout_line_is_above_the_fold_at_1280x800` (demo column shown); rewrite `test_no_text_passes_its_box_at_three_widths` to lines and the editor (no line's text past its line; no editor text past `.editor`).
- [ ] **Steps 2-4:** RED (each fails on its assertion), build, GREEN; the browser file in Chromium and WebKit; hand breaks per the contract; tests reading the grid rewritten and listed; full suite; welfare_diff; commit.

### Task 2: What only the page knows, on the lines; find and the keyboard

**Files:** Modify `wl_xcon/web.py` (`_SCRIPT`, CSS). Tests: `tests/test_page_browser.py`.

**Interfaces:**
- Consumes: Task 1's `.line[data-open]`, `span.mk`, `openSetting`; Task 6's `drafts`, `out`, `withdrawing`, `refusedAt`/`refusals`, `lineOf`, `refresh`, `settle`; Task 7's ticks; `applyFind`.
- Produces: `markLine(name)` (called from `refresh` and `settle`): sets `span.mk` to the two highest-precedence marks (Global Constraints), the `lv` text to "in force → draft text" or "in force → waiting value", and the line's `title` to every state in words; `draftText(box) -> string` reading the box's own fields per Global Constraints. Each summary section's header keeps its "· N not sent" count (Task 8's, moved from the old section headers).
- [ ] **Step 1: failing tests** (each in Chromium and WebKit):
  - `test_a_draft_survives_opening_another_and_its_line_says_so` (type in one, open another: the first line shows `●` and `"1.00 → 1.50 s"`; Apply all sends it).
  - `test_a_draft_over_a_waiting_change_shows_both_marks` (Review Focus 3).
  - `test_a_lines_draft_text_for_each_kind` (number, percent `80%`, whole, draw `0.5–1.25 s`, pool `3 of 12`, color and group `edited`, a cannot-send `!` with *cannot send* in the title).
  - `test_a_refusal_stays_on_its_line_while_another_is_open` (Review Focus 5).
  - `test_sending_and_not_confirmed_marks` (`…` while sending; `?` after `ANSWER_FRAMES`).
  - `test_find_highlights_lines_and_enter_opens_the_first` (plain name, code name, section, a group's setting; others dimmed); `test_find_with_no_match_opens_nothing` (Review Focus 4: "no setting matches").
  - `test_the_summary_steps_with_the_arrow_keys` (↑/↓ move, Enter opens and focuses the editor's first field; Esc in a field with no draft leaves it, a second Esc returns focus to its line).
  - `test_a_frame_during_a_press_on_a_line_opens_it_once` (Review Focus 1; extend `test_a_press_during_frames_acts_once` with a `line` case).
- [ ] **Steps 2-4:** as Task 1's.

### Task 3: The Training tab and Runtime's pins as summaries

**Files:** Modify `wl_xcon/web.py`. Tests: `tests/test_page_browser.py`, `tests/test_web.py`.

**Interfaces:**
- Consumes: Tasks 1-2.
- Produces: the Training tab's settings panel as summary + editor below the training switch and the stage ladder (which stay where they are; its find `#tfind` works as Task 2's); Runtime's Pinned strip as summary lines of the pinned settings (`#pinned` holds lines, not copies) with one editor on Runtime that shows the pinned setting's own box (moved there while opened on Runtime, or a mirror, the builder's call, proved by the test), one draft per setting.
- [ ] **Step 1: failing tests:** `test_the_training_tab_is_a_summary_below_the_switch_and_ladder` (the three rules are one line each, opening as their sentences); rewrite `test_a_pinned_box_works_on_runtime_and_survives_a_reload` to `test_a_pinned_line_opens_the_editor_on_runtime_and_survives_a_reload` (a draft made on Runtime shows `●` on the Task parameters line too; Apply from Runtime sends once); `test_nothing_is_pinned_at_first` kept.
- [ ] **Steps 2-4:** as Task 1's.

### Task 4: Documents, backlog, CHECKPOINT; screenshots

**Files:** `docs/design/architecture.md` (the console row's box paragraph: the summary and the editor), `docs/backlog.md` (close what this makes moot, each by name in the commit: XC-539, a tall box stretching its row; XC-538, a drawn value cut in a box's head, if the line and the editor's head now show it whole; say which stay open and why), `docs/CHECKPOINT.md` (rewritten in place: this build, then the pop-out's revision next on this branch, then the reviews, then the PI's try-out). WebKit screenshots at 1024, 1280, 1440 of Task parameters, Training and Runtime with a pin into `.superpowers/sdd/2026-11-19-params-summary-editor/shots/`.
- [ ] **Step 1:** write; `tests/test_backlog.py`, `tests/test_references.py` and the full suite pass; welfare_diff; commit.
- [ ] **Then:** the pop-out's revision (its plan, reconciled with this layout), then one whole-build review of both, then the PI.
