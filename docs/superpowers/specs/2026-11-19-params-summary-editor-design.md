# The settings tabs as a summary and one editor (2026-11-19)

Status: **approved by the PI, 2026-11-19** (in chat, after mock-ups A and C in the browser: "go A", then "looks
good"); the rest is marked *our call*. Built on branch `console-build-2026-11-17` **before** it merges, replacing
the box grid of [the console interface design](2026-11-19-console-interface-design.md) (its goal 1's layout, not
its behavior). The PI also said: "build out the rest of the task parameters before you ask me for more input", so
the pop-out's revision ([its design](2026-11-16-popout-revision-design.md)) is built on the same branch after this,
before he is asked again.

> **Built 2026-11-19** on `console-build-2026-11-17` (its plan's Tasks 1 to 4, then the whole-build review of this
> and the pop-out revision, and its fix wave), not merged. **One deviation**: goal 1's "four at 1280 wide" is **three
> at 1280 and two at 1024**, beside the demo screen's column: the columns are as wide as the widest line a tab's
> settings can show (`web._widest`, `web._line_width`), and four would cut the pop-out's longest names (the ledger's
> ruling for Task 2). Since the fix wave the width never follows a value in force: turning special trials on moves
> nothing (`test_turning_special_trials_on_moves_nothing_in_the_summary`). A group's line is sized by its name
> alone; **the Special trials line no longer cuts** (the PI, 2026-11-20, from his try-out: "Shorter line, no cut";
> until then its value in force, "10% · 10% · ... · 0.50 s", cut at 1280 once shares were on): it says only the
> shares that are on, in short words from their plain names ("absent 10% · empty 5%"), "none" with every share at
> 0, the catch hold left off it, and where the shares on would not fit its column, how many kinds and their sum
> ("4 kinds · 400% of trials", the controller's ruling); every share and the catch hold whole in its title and in
> the editor (`web._shares_said`). The test holds it uncut at 1024, 1280 and 1440 in Chromium and WebKit. Another
> group's values may still cut, whole in its title.

## Why

Trying the reworked console in Safari, the PI said:

> "i dont know that i love the boxes, the grid is a bit messy. maybe there is a better way to organize everything
> within the params tab?"

He uses the tab both ways: "both, depending on the need in the moment" (hunting one setting to change; reading down
all of them to check what the animal is running on). His own proposal: "perhaps some way to visualize all params at
top and clicking opens the ability to change it below". What made the grid messy (WebKit screenshots of his live
session, `.superpowers/sdd/2026-11-19-console-interface/shots-pi-tryout/`):
- **Ragged rows**: each section wraps its boxes, so Timing ran five then one alone, Gaze windows two and a gap.
- **Boxes of very different sizes**: a one-number box beside a color box three times taller and the pairings grid.
- **Nothing lines up**: labels, fields and units fall in a different place in every box; no column to read down.

The mock-up he chose: `.superpowers/brainstorm/72350-1795122043/content/params-a-vs-c.html`, option **A**.

## Goals

1. **A summary of every setting at the top of each settings tab** (Task parameters and Training): each setting one
   line, its plain name and its value in force, grouped by section, the sections in columns (four at 1280 wide;
   fewer as the page narrows, never a horizontal scroll). All of the pop-out's Task parameters fit above the editor
   on a 1280 × 800 screen with the top bar (*our call*: the test is the last summary line's bottom within 800 px).
2. **One editor below the summary**, full width: a click on a summary line (or Enter on it) opens that setting
   there, with everything its box has today: the plain name with its code name small, the help sentence, the field
   between − and + with its unit, or the fixed/drawn or fixed/scaled switch and its sides, or a color's set and
   swatches, or the pairings grid; Apply and Discard; the status line (*not sent*, *sending…*, *waiting · who*,
   *in force from trial N*, a warning, a refusal, *not confirmed*); *withdraw*; and ⋯ *more* (the limits and their
   reasons, where the value comes from, *hand back*, a draw's live numbers and profile, *pin to Runtime*).
3. **The summary line says the state at a glance**, with words or a mark beside the value and color never the only
   signal: ● an edit not sent (the line shows "in force → draft"), ◷ a change waiting for the next trial
   ("in force → waiting"), ◆ a value drawn each trial (the line shows the draw, e.g. "0.5–1.25 s"), a refusal mark
   while a refusal is the box's state, "changed" when it differs from the task's start, and the welfare-ceiling
   color on a reward size. A legend line under the summary says what each mark means.
4. **An unsent edit survives opening another setting**: its line keeps ●; the drafts bar and Apply all are
   unchanged (every draft sent together, a reward size left out).
5. **The opened setting stays opened** across frames, tab switches and a reload (per task, the browser's own
   storage, guarded as the pins are); with none opened, the editor says "click a setting above to change it".
6. **A group is one line and one editor**: the training rules and, once the pop-out's revision declares it, the
   special trials (one line right after Timing). The line reads the group's title and its settings' values; its
   editor is the group's sentence with its fields in place and one Apply, as today.
7. **The keyboard**: in the summary, ↑/↓ move the highlight, Enter opens; in the editor, Enter applies and Esc
   discards as today, and a key opens the summary again (*our call*: Esc in a field with no draft leaves the field;
   a second Esc returns focus to the summary line).
8. **Find** highlights matching summary lines (plain name, code name, section, a group's settings) and dims the
   rest; Enter in the find box opens the first match.
9. **Pins on Runtime become summary lines**: Runtime's Pinned strip is a short summary of the pinned settings, and a
   click opens the same editor on Runtime (one editor per tab, the setting's one draft shared).

## Non-goals

- No change to what a setting means, its limits, what the page sends, the rig's commands, the record, or any
  welfare-listed item. The drafts, Apply, Apply all, withdraw, the whole-number and percent rules, the frame
  patching and "a frame never eats a press" all stay; this rework changes where things are drawn.
- No new dependency; still one server-rendered page with its own script.
- Not the Setup, Warnings or End of session tabs.

## Anti-goals

- **The page jumping under the pointer**: opening a setting changes nothing above the editor; the summary's lines
  keep their size whatever their state (a waiting or draft value may cut with an ellipsis, the full value in its
  title and in the editor).
- **A trainer who believes an unsent edit is in force**: the summary never shows a draft as the value in force;
  "in force → draft" with ● and the word *not sent* in its title.
- **Losing the read-down**: the summary is never hidden by the editor; a long editor (the colors, the grid) scrolls
  the page below the summary, not over it.

## Decided by us (each to be told to the PI in one line)

- **Every setting keeps its box under the hood** (*our call*, the cheapest safe path): the page still renders one
  `div.box[data-card]` per setting (and per group) exactly as now, and the editor area shows only the opened one;
  the others stay in the document, hidden, so drafts, `patchCards`, `judge`, the pins' mirror and every test of a
  box keep working. The summary is a new, separately rendered list of lines, one per box, patched by frames as the
  boxes are.
- **The summary's value is the rig's**: rendered in Python from the same row the box uses (the value in force, a
  draw's range, a pool's "N of 12", a color's "from pairings"), and the page adds only the draft and waiting marks
  it alone knows.
- **Section order** is the task's, as today; the Ceilings section comes last. A section's header in the summary
  keeps its "· N not sent" count; sections no longer collapse (the summary is short enough), but the find dims.
- **Colors**: the *New color…* panel opens from the Colors section's header in the summary, into the editor.
- **The 260 px rule** becomes: the first summary line within 260 px of the top at 1280 × 800.
- **What a line shows for a draft** (from the builder check): the page reads the opened box's own fields, never a
  second formatter, so the line never says a number the box does not: one number field, "in force → typed unit"
  (a percent's `%`, a whole number as typed); a draw, "in force → shortest–longest unit" from its two fields; a
  pool, "in force → N of 12" from its ticks; a color, a group, a shape or a switch alone, "in force → edited";
  a draft that cannot send, the typed text with *cannot send* in the line's title and the refusal mark.
- **When states combine** the line keeps the value in force first and stacks at most two marks after the name, in
  this order of precedence: refused (!), a draft (●), sending or withdrawing (…), not confirmed (?), waiting (◷),
  a warning (⚠); ◆ (drawn) is the value's kind, not a state, and is always shown. The arrow's value is the draft's
  if there is one, else the waiting value's; every state present is said in words in the line's title (and in full
  in the editor), so a draft over a change already waiting shows ● ◷ and says both.
- **The Training tab**: the training switch and the stage ladder stay where they are; the summary and the editor
  replace the boxes in its settings panel, below them. The 260 px rule is Task parameters' only.
- **The fold test** measures the pop-out as built at that commit, at 1280 × 800 with the demo screen's column shown
  (as in the PI's try-out), no banner, and the drafts bar at the window's foot (it is fixed, not in the flow). The
  summary is designed for up to about 45 lines in four columns (a line about 20 px), so the pop-out's revision,
  which adds 10 to 15 settings, still fits; its build keeps the test passing.
- **The editor keeps the box's own head** (the value in force, and what waits after an arrow) and status line, so
  the words a box says are unchanged; the mock-up's "in force now: …" phrase is not added.

## How it is judged done

- WebKit screenshots at 1024, 1280, 1440 of Task parameters and Training: no text past its line or the editor's
  edge; at 1280 × 800 every pop-out Task parameters line above the fold.
- Browser tests in Chromium and WebKit: a click opens a setting and nothing above the editor moves; a draft survives
  opening another and its line shows ● and "in force → draft"; Apply from the editor; the waiting mark; find
  highlights and Enter opens; ↑/↓/Enter in the summary; the opened setting survives a frame and a reload; a group
  opens as its sentence; a pinned line on Runtime opens the editor there; every existing test of the boxes' behavior
  still passes (rewritten only where it reads the old grid's layout, none deleted without a replacement).
- The PI's next Safari try-out, after the pop-out's revision is built too.
