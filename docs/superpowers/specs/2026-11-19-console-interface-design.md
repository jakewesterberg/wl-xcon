# The console's interface, reworked from the PI's Safari try-out (2026-11-19)

Status: **approved decisions from the PI, 2026-11-19** (AskUserQuestion, after a mock-up in Safari); the rest marked
*our call*. Built on branch `console-build-2026-11-17` **before** that branch merges (the PI: "Rework first, then
merge"). Builds on [the console settings design](2026-11-16-console-settings-design.md); the pop-out's revision
([its design](2026-11-16-popout-revision-design.md)) builds on this one.

## Why

Trying the console settings build in Safari, the PI said:

> "text overruns the boxes, eg, color section. i prefer an apply button in each box for making a change.
> descriptions are too long. where are catch trials. what are pairings? for necessary whole numbers (set size),
> there should not be a decimal option for entry. Think deeply about how to make this more useful as an interface"

Three reviewers (Fable; lenses layout, controls, workflow) read the page in WebKit and its code. Their reports,
git-ignored: `.superpowers/sdd/2026-11-16-console-settings/ui-review/{layout,controls,workflow}.md`, the mock-up the
PI saw `ui-review/shots/layout/mockup.html`. What they found, in short:
- **The overrun has one cause**: `.param` is a grid with an `auto` column and `.param .rn` a non-wrapping
  inline-flex, so a color card's luminance line forces 351 px into a 198 px box (`web.py` ~3272, ~3335).
- **A card prints everything it knows**: limits and their reasons, where the value came from, a refusal of 14 lines
  that never leaves; one long card stretches its whole row (to 444 px).
- **Six send paths**, none an Apply: a field and its arrows send 600 ms after a change (one edit of
  `fix_acquisition` recorded four changes), a range has *change the range*, a form *apply*, a hue sends on click,
  *hand back* at once. The POST answers "sent", never the verdict; the verdict arrives in a frame tied to no press,
  and "sent"/"not sent" are said in a line at the top of the page.
- **Every unit but mL, s and deg steps by 0.01**, so `set_size` reads `4.00`; the training counts too.
- **Pairings is a bit-sum** (blue among purple = 1 ... green among red = 2048) typed as `66.00`.
- **Half a laptop screen goes before the first setting**; the demo's key list and caveats take 1,326 px on every tab.
- **Frames freeze a whole tab** while one field has focus (`busy()`); in Safari, Tab reaches no button on a card.
- Smaller: Runtime's "Still needed" drawn one letter per line; the drawn side's fields carry no unit; a stale refusal
  stays under a later accepted change.

## Goals

1. **A setting is a small box** (the PI: "Small boxes"): its plain name with the code name small, its value with
   −/+ and **Apply**, one status line. Everything else opens inside the box on a click: the fixed / drawn / scaled
   switch and its editor, the limits and their reasons, where the value came from, a refusal's or warning's full
   text, *hand back*, the profile. About 30 settings on one laptop screen (1280 × 800). Nothing overruns its box at
   1024, 1280 or 1440 wide.
2. **Nothing is sent until Apply** (the PI: "Apply per box, plus Apply all"). Any edit (typing, −/+, a segment, a
   tick, a swatch) makes a draft the box shows as *not sent*. Apply sends the whole box as one change; Enter in a
   field is Apply; Esc (or *undo*) puts the box back to what is in force. While any draft exists, one bar says
   "N edits not sent: fix_hold, set_size · Discard all · Apply all", and Apply all stages them **together, on the
   same trial**.
3. **A waiting change can be withdrawn** (the PI: "Yes, a withdraw button"): after Apply, until the next trial, the
   box's status line offers *withdraw*; a withdrawal is its own recorded act.
4. **Every outcome on the box, in one reserved line**: not sent · sending · waiting for the next trial (by whom) ·
   in force from trial N · in force, with a warning [why] · refused [value, one line, why] · cannot send [why].
   Words beside every icon; color never the only signal. A refusal is cleared by a later accepted change of that
   setting.
5. **Plain names** (the PI: "Plain name, code name small"): each setting declares a plain name and one sentence
   ("what it is") in the task file; the box shows the plain name, the code name small beneath it; the find box
   matches both, and section names.
6. **Whole numbers are whole** (the PI's words): a setting the task declares whole shows no decimals, steps by 1,
   and refuses a `.` at the keyboard; a non-whole value sent anyway is refused by the rig.
7. **Pairings is a grid** (the PI: "4 × 4 grid, add or remove"): odd color down, distractor color across, the
   12 pairs as ticks with their swatches, the diagonal empty; ticks are a draft until Apply; adding and removing
   are both allowed live (the suggestions still only suggest adding). The record still writes the pool's number.
8. **Special trials have one box, right after Timing** (the PI: "One box after Timing"): a task may declare a
   **group** of settings that share one box and one Apply. This rework builds the group; the pop-out's revision
   declares its special-trials group in it (each kind's percentage, whole; the remainder shown as "normal search";
   the catch hold). The training rules use the same group: a bar and its window, one box, read as a sentence
   ("Move up when at least [80]% of the last [50] answers are right").
9. **The trainer pins settings to Runtime** (the PI: "Yes, you choose only"): a pin on any box puts a copy of it,
   working the same way, in a "Pinned" strip on Runtime. Nothing is pinned until the trainer pins it.
10. **A frame never eats a press**, by construction: the page patches box by box; a box with a draft, focus, a
    pointer down or a request out keeps its editor's nodes and has only its head and status lines updated.

## Non-goals

- No change to what a setting means, its limits, the layout checks, or any welfare-listed item. (*Our call*, from
  the reviewers' welfare note: the whole-number refusal is made in the non-listed path a change is judged on, as
  `_impossible` is, never in `Session.set`.)
- Not built here: catch trials themselves (the pop-out's revision), yesterday's ending values offered at set-up
  (a reviewer's idea; filed in the backlog), milliseconds on the page.
- No new dependency; the page stays one server-rendered page with its own script (ADR-0004's inventory unchanged).

## Anti-goals

- A trainer who believes an unsent edit is in force. *Not sent* and *waiting* never look alike, and the head
  always shows the value in force.
- A box whose height jumps as its status changes, moving Apply under the pointer.
- A record that no longer says who changed what, when: every Apply, Apply all and withdrawal is recorded.

## Decided by us (each told to the PI in one line)

- **−/+ wait for Apply**, as typing does (no half-way values in the record). Shift+click steps ten times.
- **Deliberate presses act at once**: *hand back*, the training switch, *revert to this*, *lock at*; a swatch or a
  tick is a draft.
- **Step sizes from the unit** unless a setting declares its own: counts 1, s 0.05, deg 0.1, mL 0.01, cd/m² 1,
  fraction 0.05, × (ratio) 0.1, % 1. The task declares `whole`; the console does not guess it from the unit.
- **Seconds stay seconds**, the unit beside every field, the drawn side's fields included.
- **The top of the page becomes one bar that stays in view**: state, trial, correct, fluid, cage time and the run's
  buttons; the session's details behind a *session* button.
- **The demo's key list and caveats** fold to one line ("keys and demo limits"), open on the first visit only.
- **The new-color panel** moves out of each color's box into one *New color…* panel for the Colors section.
- **Colors and pairings** share a section, the pairings grid wide (two columns).
- **Drafts** are kept per setting across frames and tab switches, dropped at the run's end and on a reload; closing
  the page with drafts asks once (`beforeunload`).
- **A reward size (a welfare ceiling, today `reward_correct`) keeps its own Apply only**: it is left out of Apply
  all and offers no withdraw, and its box says so ("sent alone · cannot be withdrawn"). Both new commands sit beside
  `SetRange`'s in `_command`, outside its listed lines; a reward size in them would need the welfare-listed
  refusal recording repeated and a staged reward taken back, which is the PI's welfare review to approve, so not
  built here (filed in the backlog for him). The non-goal holds: no welfare-listed item changes.
- **Withdraw takes back the whole act**: a group box's Apply or an Apply all is one act, judged together, so
  withdrawing from any of its boxes withdraws all of it, and the box says so first ("withdraws the 3 applied
  together"). A change's row is written only when it takes effect, so a withdrawal names the command id the page
  made; that is the shape drafted for wl-preproc.
- **A fraction may be shown as a percent**: a setting may declare that the console shows it ×100 with `%`
  (the training bars, so the sentence reads "at least [80]% of the last [50] answers"); its steps, limits and the
  rig's sentences are converted on the page, and the setting, the command and the record keep the fraction.

## What the rig must send that it does not (from the controls review §4)

On each row (`link.ParamRow`): `whole`, `step`, `choices` (bounded), `start`, `label`, `help`, the pool's members as
data (each pair's odd and distractor color, swatches, bit, on/off), and the group a setting belongs to. On a verdict:
a command id the page made, echoed on `Staged` and `Refused` (with the refused value), the warnings a staged change
carries keyed to its setting, and the trial a change took effect at. Commands: **apply several** (staged together,
judged together) and **withdraw** (a waiting change, by its id). Telemetry's schema rises once.

## The record (wl-preproc is told first, as XC-513 was)

Each change applied is still its own row, as today; Apply all adds no shape if its rows carry nothing new (*our
call*: the build's first task reads `record.py` and decides whether a shared id is needed to say they were applied
together, and if so asks). A **withdrawal** is a new row kind, appended to `KINDS`, its shape drafted against
`record.py` (whether it strobes, its `was`/`now`, the change it withdraws) and **sent to wl-preproc before it is
written**. Labels, help sentences and groups are the task's declaration, hashed as before.

## Task-file declarations (wl-xtasks, curated with the PI)

`Param` gains `label` (a plain name, at most 40 characters), `help` (one sentence, at most 120), `whole` (bool) and
`step` (optional). A **group** names its settings, its box's title and, where it reads as a sentence, the sentence
with its settings' places. The pop-out search gets a label and help for each setting, drafted by us and reviewed with
the PI on the wl-xtasks branch before it merges; its training bars and windows grouped; its counts whole.

## How it is judged done

- The three reviewers' screenshots re-taken in WebKit at 1024, 1280 and 1440: no text past a box; the first setting
  within the first 260 px at 1280 × 800.
- Browser tests in Chromium and WebKit for each state of a box, Apply, Enter, Esc, Apply all (two settings, one
  trial), withdraw, a whole-number box refusing `.`, the pairings grid, a pin, and a press during frames for each
  control type.
- The PI's next Safari try-out.
