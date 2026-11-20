# Architecture

Status: current summary. Reasoning, sources and alternatives live in
`docs/superpowers/specs/2026-08-31-controller-architecture-design.md`; this file is the
orientation document CLAUDE.md sends you to first. Where the two disagree, the spec wins
and this file is stale. The papers behind science-facing choices, and which choice each
supports, are in `docs/references/` (ADR-0010).

Contracts here are proposals until frozen at milestone M0.

## Principles

1. Two planes per rig, joined by messages and by hardware TTLs — never by shared code or
   shared clocks.
2. **The sync box defines session time.** `wl-sync` owns session identity, the barcode
   codec, the log format and event-code routing. We consume them; we do not mint them.
3. Anything scientifically meaningful becomes an edge or word in a recorded stream
   [@hwang2019nimh; @rubel2022neurodata]. Software timestamps are for control flow; hardware
   timestamps are for analysis [@plant2004selfvalidating; @siegle2021survey; @karsh2026sync].
4. Hardware sits behind small interfaces; every interface has a simulator.
5. The hot loop does bounded work: no allocation, no disk I/O, no unbounded queues, and
   it never renders a plot, serves a request, or holds a UI.
6. **Declare once, derive many.** Parameters, trial outcomes, plots, stimuli and gaze
   mappings are versioned data with provenance, not code. One declaration drives
   validation, the console UI, the saved record and the downstream contracts.

## Per-rig topology

```
   OpenIris PC (Windows)          Task PC (Linux)              Acquisition PC (Windows)
   OpenIris + OpenIrisDPI         taskd + console              SpikeGLX <- Neuropixels
   500 Hz binocular dDPI          NI PCIe-6343                 NI PXIe-6353 (nidq)
        |         \                    |                             ^
        | UDP:9003 \ ACCES DAC         | MDR68 x2                    |
        | (control) \ (recorded copy)  |                             |
        v            v                 v                             |
   +--------------- wl-sync breakout board (2U) ----------------------+
   |  conditioning, level shifting, isolation, mux, comparators        |
   +---+--------------------+---------------------+------------------+
       |                    |                     |
       v                    v                     v
   sync box (Pi/CM5)    Intan RHS            wl-juicer / wl-shook /
   barcode, session     record + stimulate   cameras / speakers / mic
   identity, log
```

**Two rigs in v1** (the breakout spec budgets cabling for two; five boards are fabbed, so
headroom exists). One config file per rig.

## The task PC's interface

Fixed in copper by `wl-sync`'s breakout board. See that repo's `hardware/README.md` and
breakout spec §3 and §9.2.

- **Digital out (19):** 16 event-code bits on **P0.8–P0.23** (not zero-based), event
  strobe, reward commanded, stim trigger.
- **Digital in (4):** task-patch photodiode comparator, flip-patch photodiode comparator
  (a frame clock), chair-motion trigger from `wl-shook`, RHS stim output.
- **Analog in (9):** eye X/Y both eyes (from the ACCES DAC), joystick X/Y, 3 misc BNC.
- **Not in copper:** touchscreen and audio output. Both are host-side, and touch events
  reach the recording clock only as strobed event codes.

The two photodiode comparators returning to us turn two offline checks into online
guarantees: state progression can be gated on physical stimulus onset, and dropped frames
are detected at the display surface.

## Components

| Component | Runs on | Language | Job | Simulator |
|---|---|---|---|---|
| `taskd` | Task PC (Linux) | Python | Trial execution, display, gaze logic, DIO, session record; since P4d-2b b3a also `wlx taskd`, the rig service that holds one animal's session across runs, opened, run and ended from a console (`service.py`); and since engine build B, what a session is for and its warnings list: the imperfections it runs with, each acceptable in some session kinds, accepted once a session and recorded in `warnings.jsonl` (`warnlist.py`); and since demo mode (2026-11-14) its demo sessions, the mouse on a page as the eye (`pointer.py`): `wlx taskd --demo DIR`, a demo service, makes `DIR` new holding the test monkey `REFERENCE` alone (the checkout's eight-hour file and reference settings) and its sessions' folder, refuses `--subjects`, `--root` and `--demo-root` beside it, needs `--link`'s fourth endpoint (the pointer reports' PULL socket, loopback only) and prints its four bound endpoints on one line, and makes every open a demo on the simulated card and pump, which it refuses anything but; a rig service opens a demo only with `--demo-root DIR`, a demo folder of its own, never inside `--root` nor holding it (the PI, 2026-11-14), where the demo is written and where a crashed one is found at start, offered only *end*, holding up another demo and never a real animal's open, its End taken against the demo folder by the stranded rule's own code and refused, ending nothing, while a session under `--root` has its id. A demo session's spec carries `taskd.Demo`, which `config.json` writes as `demo` (no other session has the key) and every frame says; it takes `geometry.stand_in_housings` in direct view where the rig's are unmeasured; its worlds are made for each run (`Session.run_world`), the mouse's noise from the run's seed, paced to the wall clock and publishing the screen it shows; its pre-flight names the mouse as its gaze and fails a task waiting on more than nine inputs; it is never resumed, only ended. **A demo run's trial waits for its page's pointer** (demo mode's Task 10; every trial since the whole-build review's I3, 2026-11-16; `pointer.Worlds.waiting`): before the first screen a page has nothing to point at and an eye nobody steers is tracker loss, so while no page steers (`pointer.Source.steered`: no report yet, or the last past `LIVE_S`) the run holds at the boundary before the next trial, each pass the boundary's own (commands drained, a frame published, `_ends` asked) with the field published blank for the page (`pointer.Drawing.field`); the trial under way when the reports stop (Escape, a tab closed) ends as tracker lost, and the next waits. **`wlx demo TASK`** (`demo.py`, demo mode §5) checks the task as `wlx check` does against the demo's field, then runs `wlx taskd --demo` and `wlx serve` as its children on loopback ports they bind and print, opens a session for `REFERENCE` and starts a run as the page would, accepting the open's warnings and the pre-flight's unknowns, each printed, and opens the browser at `/#demo`; Ctrl-C ends the session with its return now, stops both children and deletes its temporary folder (`--keep DIR` copying the session's first), and a child that dies ends the other, said; each child stops itself when `wlx demo` goes. **The rig lock** (`service.RIG_LOCK`, in the temporary folder): every `wlx taskd` without `--demo` holds it shared for its life, and while a demo holds it says so and waits; `wlx demo` takes it exclusive without waiting, refused beside a rig service, and its children hold it with it. **It opens only through `Service._open`'s demo path** (`Service._session_for` refuses any other): `_open` refuses a demo for any animal but `REFERENCE` before anything is written, and builds a demo on the simulated card and pump, and on an unmeasured rig the stand-in field, whatever the service was built with (the PI's two approved changes, 2026-11-07; the welfare section below) | Full headless run against replayed/synthetic inputs |
| `console` | The control box, in a browser on the LAN | Python server + web client | Experimenter UI, live plots, parameter writes, preflight, test screens. **The box authenticates and records the actor** — anybody attached has full access, with visibility rather than a lock (S9a §8); `wl-works` lists devices and links to them, and carries no welfare-affecting action (ADR-0008). **The link exists** (`wl_xcon/link.py`, P4d-1, 2026-09-19): `taskd` holds a `Link` port, drained and published once per trial boundary and never per frame (but for a demo's world, which publishes its screen inside a trial, below), whose live implementation (`ZmqLink`) binds a ZMQ PUB socket for `Telemetry`, a REP socket for its commands — `SetParameter` and `Stop`, and since P4d-2b b2a `Pause`, `Resume`, `Mark` (a mark's note), `ScheduleStop`, `CancelScheduledStop` and `ManualReward` (a manual reward: while paused and, in a `wlx taskd` session, between runs and while the return is awaited), and since P4d-2b b3a `OpenSession`, `CheckRun`, `StartRun` and `EndSession`, and since XC-026 (2026-10-01) `ResumeSession` (wire kind `resume_session`: a stranded session resumed from its record), which `wlx taskd` acts on and a `wlx run` session refuses — which the page sends since b3a-2 — from its forms, and since XC-026 from the stranded banner's *resume session* button, and since engine build C2a, from its Still-needed pane, `ClearOwed` (`clear`: one trial, or the rest, cleared from a condition's count), `Drum` (`drum`: drumming switched for a block or a run) and `Training` (`training`: the training aid *clear*, or the setting that judges only each drummed trial's first answer for a percentage, switched on or off), and since engine build C2b `NextBlock` (`next_block`) and `BackBlock` (`back_block`: the run moved on a block, or back one, by hand), and since engine build C3 `HandBack` (`hand_back`: a setting a person holds handed back to what gives it in the open block), `SetRange` (`range`: new numbers for the draw the open block uses) and `Revert` (`revert`: the run's task settings and drawn ranges taken back to an earlier change of the run, or to its start), and since the pop-out search build (2026-11-07) `Decline` (`decline`: the trainer's hold of the rig's suggestion under a confirmed progression, named by its row's id) and a `NextBlock` or `BackBlock` naming the suggestion it confirms, and since the console settings build (2026-11-17) `SetForm` (`form`: a timing setting switched to drawn on its card, a person's draw of one of five shapes, `task.SHAPES`, staged to the next trial, or a size setting scaled by eccentricity, shape `scaled` with its `factor`) and `SetColor` (`color`: a color setting's hue picked by its set on its card, the one declared choice it names set through `Session.set`), and since its Task 10 `Shaping` (`shaping`: the training switch, on, frozen or the plan's full task, staged to the next trial), and since the console interface rework's Task 4 `ApplyMany` (`apply_many`: 1 to `link.APPLY_LIMIT` values, ranges, draws and color picks, `link.APPLY_KINDS`, each by its own kind's fields with no `by` or `cid` of its own, judged and staged together under the command's required `cid`, or refused whole, a reward size among them refusing it; `Session._apply_many`) and `Withdraw` (`withdraw`: the act of a `cid` taken back while it waits, a `withdrawn` change row for each setting it covered, refused "already in force from trial N" once applied and for a reward size; `Session._withdraw`), and since the pop-out revision's Task 5b `SetChoice` (`choice`: one of a setting's declared choices picked among its box's segments by its words, `link.choice_words`, the one declared choice they name set through `Session.set`; a look's shape among them) — through `POST /commands`, built by the wire's own rules (`link._command_from`), and whose closed session's summary `wlx taskd`'s idle frame carries until the next session opens (telemetry schema 23, `link.SCHEMA`; the summary since 11; since 23 (the console interface rework, 2026-11-19) each row says what its box needs -- whether it is whole, its step (`task.step_of`), its choices as words (at most `link.CHOICES_LIMIT`, else none), its start, its plain name and sentence, the group whose box holds it, whether it shows as a percent, on the pool's setting its pairings as data (`ParamRow.members`, each a `link.PoolMember`: bit, the odd and distractor colors by name with their sRGB swatches, and whether the value holds it; `taskd.pool_members`), and the change in force on it, the trial it took effect at and who made it, with the warnings it carried (`ParamRow.applied`, a `link.Applied`, and `ParamRow.warned`) -- and every verdict names the command id the page made for the press it answers: a box's command (`set`, `hand_back`, `range`, `form`, `color`; `link.CID_KINDS`) carries a `cid` beside its fields, printable text of 1 to 64 characters decoded by `link._cid`, never by `link._setting`, and `Staged.cid` and `Refused.cid` echo it (`Session._answering_for`, `_answered`, beside `_command`'s listed lines), a staged change carrying the warnings judging it gave (`Staged.warnings`) and a refusal the value refused (`Refused.value`), and the page draws each setting as a **box** (the console interface rework's Task 5, `web._box`; the PI, 2026-11-19, "Small boxes"): `div.box[data-card]` of a head (the plain name with the code name small, or the code name alone; the value in force, and what waits for the next trial after an arrow), an editor (the field between − and + with its unit beside it, every field's unit shown, the drawn side's too, a weighted list's weights `relative`; or the fixed/drawn or fixed/scaled switch and its sides; or a color's set and swatches; or, since the pop-out revision's Task 5b, a setting's declared choices as segments by their words, `ParamRow.choices`, a look's among them, pressed as a draft as a swatch is and sent as `choice`), one status line (what waits and who, the last refusal's value and gist, the change in force from trial N, with a warning, or at rest the limits in short), with Apply and Discard at its right hidden by `visibility` until the script marks a draft, and a `<details class="more">` opened in place, kept open across frames, holding the sentence, the limits with their reasons, where the value comes from, *hand back* and a draw's live numbers, the staged change, the warnings and the whole refusal, and a draw's profile; a box shows a number at its step's decimals or more where the value holds more, a whole setting's with none, and no text passes a box's edge at 1024, 1280 or 1440 wide in Chromium or WebKit (`test_no_text_passes_its_box_at_three_widths`); and since the rework's Task 6 (the PI, 2026-11-19: "i prefer an apply button in each box for making a change") **a box sends nothing until its Apply**: typing, −/+ (Shift ten steps), a switch's segment and a swatch each make a draft the box says is *not sent*, Enter in a field is Apply and Esc Discard, a whole setting's field takes no decimal point, nor the digits after one refused ("12.5" stays "12", *cannot send · whole numbers only* until the field is edited otherwise or left), and a fraction pasted is *cannot send · whole numbers only*; Apply sends the box's one change, or several as `apply_many`, under a command id the page makes, and the box says *sending…*, then the rig's *waiting · you* (its title *waiting for the next trial · you*; another console's *waiting · NAME*), *in force from trial N*, *in force, with a warning*, or *refused <value> · <reason>* with the draft back (an act refused whole by any refusal carrying its id) -- or, an act answered *sent* that three frames (`ANSWER_FRAMES`) pass without the rig's word, *not confirmed by the rig · check the value in force*, the edit a draft again, Discard and Esc letting an answered act go once a frame has come since without the rig's word (never before: Enter then Esc to leave the field keeps the change on its way) -- a refusal cleared once a later change of the setting is accepted; a draft equal to what the box is headed to is none; a draft under someone else's change keeps its value and says who (`data-under`); a bar at the window's foot says "N edits not sent: names · Discard all · Apply all", Apply all one `apply_many` of at most `web.APPLY_ALL_LIMIT` (50, the frame's refusal history) changes, a reward size left out and said to be sent alone; a waiting act offers *withdraw* on each of its boxes, "withdraw all N" where it holds more, its box saying *withdrawing…* until the rig answers, *withdrawn · it never applied* only on a frame that lists the act (`Telemetry.withdrawals`), a refused withdrawal said on them, and a waiting box's head gives what waits its room ("0.30 → 0.50 s", the unit once, after the new value); drafts are kept across frames and tab switches, dropped at the run's end (`data-run`) and on a reload, closing the page with drafts asking once; *hand back*, the training switch, *revert to this* and *lock at* still act at once; since the rework's Task 7 the pool's setting is a **grid** of its pairs (`web._pairings`: the odd one's color down, the distractors' across, each with the rig's swatch, the diagonal empty, a tick per pair carrying its `PoolMember.bit`), its ticks a draft its Apply sends as one `set` of the pool's number, the bits summed, a pair added or taken away live, the box two columns wide and its head saying how many pairs it holds; a task's **group** (`Telemetry.groups`) is one box, `data-card` its title, standing where its first setting would, its editor the group's sentence with each setting's field in place (a percent's `%` beside it, other units left to the sentence) or each field under its plain name, its one Apply always one `apply_many` under one command id, so its *withdraw* takes back the whole group ("withdraw all N"), its draft named by the title in the drafts bar and its section counting each of its settings (`web._group_box`), and since the pop-out revision's Task 7 a group holding special trials' shares (settings in `task.SPECIAL_UNIT`) saying after its sentence the trials it leaves normal, "N normal search", "none normal search" at 100 and the `specials-over-100` warning's words past it (`web._rest`, from the values in force, and while a draft is open from its own fields, `restOf`); a **percent** setting's box (`ParamRow.percent`) shows its value, step and limits ×100 with `%` and the rig's sentences about it in percent (`web._hundred`, a float's noise taken off at twelve significant digits, and `web._in_percent`), its field sending the fraction, the typed decimal's point moved two places (`80` is `80e-2`, 0.8); and each section holding a color card has one **New color…** panel after its boxes, keyed by the section (`web._new_colors`), no color card its own; since the rework's Task 8 the page's top is **one bar that stays in view** (`#bar`, sticky: the state, the trial, the session's right answers, the fluid today and the cage time, `web._bar_nums`, each the strip's own figure, the run's buttons as they were, the last command's answer, the stop's confirm and the mark's note), the session's details -- who, the strip, the signed-in member or the box's name, the next run's task, plan and pre-flight, a scheduled stop -- behind its *session* button, hidden on the Task parameters and Training tabs and shown on the others; the find box, on both settings tabs (`#pfind`, `#tfind`), finds a box by its plain name, its code name, a group's settings' names or a section it stands in; each section's header and each settings tab's label say how many edits are not sent ("· 2 not sent", the page's own, after the rig's counts); every box's *more* opens from a ⋯ in its head's corner, the head says the value in force only while it differs from the field (`data-echo`, `web._echoes`) and a plain name wraps rather than being cut, so a box at rest is three lines and keeps its height as its status changes (`test_a_box_keeps_its_height_as_its_status_changes`); *pin to Runtime*, first in a box's *more*, puts a working copy of it in Runtime's Pinned strip, kept per task in `localStorage` (`wlx.pins.<task>`, every access guarded, nothing pinned until a person pins), the copy `data-pin`, outside every box lookup, a mirror of its box that passes each press and key to it, so a setting keeps one box, one draft and one act; and the demo screen's keys and limits fold to one line, *keys and demo limits*, open the first time this browser shows a demo (`wlx.demo-keys-seen`, every visit a first where the store throws); since the summary and editor rework's Task 1 (the PI, 2026-11-19: "go A") each settings tab is a **summary** of every setting above one **editor**: one line per box (`web._summary`; a group's one, its settings' values joined, but a group of special trials' shares saying only those on in short words, "none" at rest, or "N kinds · M% of trials" where those would not fit, never cut, `web._shares_said`; the PI, 2026-11-20), its plain name and the rig's value as its box shows it (`web._summary_value`: "1.00 s", a whole number's "4", "80%", a draw's "0.5–1.25 s", a pool's "2 of 12", a color's hue or "from pairings", and since the pop-out revision's Task 7 a choice among segments as its segment says it, "Ring" (a look by its kind in people's words, `task.kind_words`; the PI, 2026-11-20), in force and waiting alike, its words whole in the line's title), what waits after an arrow, the marks the rig knows (◆ drawn each trial, ◷ waiting, ! refused, ⚠ a warning; `changed`, `ceiling`) and every state in its title, in its sections in columns, Ceilings last, the sections no longer folding (`wlx.sections.<task>` retired), a section holding a color card ending in a *New color…* line, then a legend; the editor holds every box and each New color… panel, `hidden` but the one a line opens (`openSetting`), with "click a setting above to change it" while none is, the opened setting kept per task and tab in `localStorage` (`wlx.opened.<task>`, `wlx.training-opened.<task>`, every access guarded, dropped once the setting is gone), nothing above the editor moving as a setting opens, a frame patching each line in place, the find box dimming the lines it does not find, the first line within 260 px of the top and every pop-out line above 800 px at 1280 × 800; since its Task 2 the page adds to each line what it alone knows (`markLine`, from the rig's line as the frame drew it, its `data-now`, `data-said` and `data-unit`): ● a draft, the value "in force → draft" read from the box's own fields (`draftText`: a number as typed with its unit once, a draw's two ends, a pool's "N of 12", else "edited"), … sending or withdrawing, ? not confirmed by the rig, ! a draft that cannot send or an act refused together, the rig's ! dropped once a later change clears it, at most two marks in precedence (! ● … ? ◷ ⚠) and then ◆, every state in its title; the columns as wide as the longest plain name a task may declare with a value beside it (two at 1280 beside the demo screen, three at 1440; no pop-out name cut), the lines saying degrees and cd/m² short ("°", "cd/m²"; the box keeps the setting's unit); the find box highlights what it finds, Enter in it opens the first found and "no setting matches" is said where nothing is; ↑ and ↓ step the lines, Enter opens one with its first field focused, and a second Esc returns from a field to its line; the editor area is `div.editing`; since its Task 3 the columns are as wide as the tab's own longest line, its plain name and value in force (`web._line_width`, an estimate in `ch` of its characters' measured widths, never under `web.SUMMARY_FLOOR_CH`), so the pop-out's own settings take three columns at 1280 and the longest plain names two, a section holding subsections breaking between them; where the find box hides the setting opened the editor says "the opened setting is hidden by find · clear find to see it"; and Runtime's Pinned strip is a summary of the pinned settings' lines (`#pinned`, each its tab's line's mirror, marks and draft included) above an editor of its own (`#pinned-editing`), a click opening the setting's mirror box there, one at a time, kept per task (`wlx.pinned-opened.<task>`); and the page patches box by box (`patchCards`), a box with a draft, its act out or a field focused keeping its editor's nodes, its untouched controls following the frame, its head, status line and *more* taking the news, and a frame waiting whole only while a pointer is down (the 600 ms sends of a field and the arrows, *change the range*, a drawn side's *apply* and a swatch's send on its click are gone; `test_a_press_during_frames_acts_once`, in Chromium and WebKit); since 22 each card says whether it offers the timing switch, *fixed* or *drawn*, on a live setting in seconds (`ParamRow.switch`), and the shape in force for its drawn side, a person's draw or the open block's (`ParamRow.shape`), a person's draw is a card's source `form`, and a staged row may be of kind `form`, and a card whose shape is in force carries its draw's profile, the density as bars and the hazard against flat (`ParamRow.profile`, `variation.profile`: arithmetic of the declared distribution, not a measurement, cached by distribution and built between trials; drawn on the card as inline SVG, `web._profile`) (the console settings design's §3), and each card says why each limit its setting declares stands, in one line beside its range, a fraction's "a fraction is at most 1", or *no limit* (`ParamRow.why`, `task.limit_reason`; the design's §4), and a size's card offers *fixed* or *scaled* (`ParamRow.switch` `scaled`, a factor field sending `form`) and a scaled size's or an object window ratio's card what it gives each object in degrees, made by the rig (`ParamRow.gives`; the design's §5), and a color setting's card its set, its hues as named swatches on the sRGB standard, approximate and saying so, and its saturation and luminance levels, each by its setting with the light's cd/m² (`ParamRow.color`; the design's §6), and a value that is a look or a color travels as the rig's words for it, `value` null, on its card and a staged row (`ParamRow.words`, `review.appearance_words`; XC-420), and each card its section and whether it differs from the task's start (`ParamRow.section`, `task.section_of`, `ParamRow.changed`), which the page lays out in sections with a find box on top, since the summary and editor rework the sections of each settings tab's summary, which no longer fold (`web._sections`; the design's §7; TSK-76), and the training switch (`Telemetry.shaping`, `""` for a run with none, and `Telemetry.full_task`, whether the plan declares a full task; a card the switch holds says `frozen at` or `full task at` its value, source `frozen` or `full`) on a **Training** tab of its own, holding the switch, *on · frozen · full task* (*full task* grayed saying why where the plan declares none), the trainer's panel and the cards of every section under `Training` (`task.TRAINING_SECTION`), which the Task parameters tab no longer holds, the Runtime tab keeping one line, `training frozen · stage Crowd · Training tab` (`web._shaping`, `_training_params`, `_runtime_shaping`; the design's §8; TSK-77); since 21 every frame, idle or running, says whether it is a demo's (`Telemetry.demo`; `Idle.demo`, a demo service's), an idle frame whether a demo can be opened there (`Idle.gaze`), and a third kind of message, `Drawn` (phase `drawn`), carries a demo session's screen whole, published by its world inside a trial on the trial's first frame, on a change and at least once a second, and blank at its end: the `screen.Screen` in its wire form (`screen.to_wire`, each block by its class name from a closed list), the windows as the trial placed them with an array's target's flagged, what could not be drawn outlined saying why, the setup's viewports, housings and field edge, each eye's share of the vergence offset, and the keys (demo mode §3.7-§3.9); `wlx console` skips a `Drawn`, counting it alive, and says DEMO on a demo's frame; since 20 the rig's suggestion under a confirmed progression (`Telemetry.suggestion`: its `suggested` row's id, which an answer names, the move, the stage it was judged in and the one it suggests, and the bar's numbers as they read now), and beside it its suggestion to widen the task's pool of pairings (`Telemetry.widen`, a suggestion of move `"widen"` with no stage to go to), and, for the trainer, the open block's staircase at its level and whether a person holds its setting (`Telemetry.staircase`), the stage's last answers, in a window only a stage change starts afresh (no hold and no change of the pool clears it; the build's final fixes), the wrong ones and the trials left out of them by outcome, and the bar to move up as it reads (`Telemetry.bars`), and the pool's pairings in its declared order with its value (`Telemetry.pool`), all shown since the pop-out search build's Task 7 on the *Training* panel, the Runtime tab's until the console settings build's Task 10 moved it to the Training tab, whose *Move up* and *Move back* send `next_block` and `back_block` naming the suggestion they confirm and *Hold* a `decline` naming it, *lock at* holds the staircase's setting with a person's `set` (*hand back* resumes it) and *add* widens the pool with a `set` of its value plus the pairings ticked, and whose pre-flight check sends the stage picked, as the start does; since 19 each setting's card says where its value comes from in the open block (the task, the run, its conditions, a draw, in the rig's words with the numbers a person may change live, or a person) and names the conditions of the run's plan that set or draw it, each staged change, a hand-back, a live range and a revert's among them, says its kind and names the conditions it will override, or a range the blocks it reaches, before it applies, the frame lists the moments of the run a revert can go back to, the run's start always among them, each with what a revert to it changes, and it says which settings a person's change keeps trials out of moving up by (engine build C3's spec §6; XC-418); since 18 a setting whose value is a whole position, a `task.Polar`, or an (x, y) pair where the setting's choices declare one, travels as the rig's words for it, eccentricity and direction first with its (x, y) beside them, `27.236° at 45° · (x, y) (20, 20)`, the review report's (`review.position_words`; since 2026-10-30 every direction from 0° to 360° and none at eccentricity 0, `0° · (x, y) (0, 0)`, the PI's "0 to 360 everywhere" and "Empty at center", in the same words and schema; a setting whose value is a number is shown as the number it holds, even one a task uses as a direction, which the load check warns of outside 0 to 360, `direction-outside-0-360`), on its parameter card with no input, on a staged change and on the changes feed (any other value that is neither a number nor a word is shown as written with no input, so the page and its controls always render), and on the parameter and staged lines `wlx console` already had, which still shows none of schema 16's, 17's and 19's additions (XC-387); the PI, 2026-10-19, "Polar first, x-y allowed", STE-30; each stimulus's and window's position is XC-401, after XC-399) — each checked where it is decoded — and, given a third endpoint, a PULL socket for an operator's mark signal, which the trial loop checks once per frame (ADR-0003's transport, untouched: a third socket on the same link), and, given a fourth (demo mode §3.8), a PULL socket for a demo's pointer reports, bound on loopback whatever `--link-allow-remote` says and keeping only the newest waiting (ZeroMQ's `CONFLATE`, at both ends, since the demo build's review, M1), which a demo's world reads up to `pointer.DRAIN` a frame into one buffer (`ZmqLink.gaze_into`; `ZmqGaze`, its PUSH sender, never blocks). `ZmqConsole` is the other end. Reached today by `wlx run --link PUB,REP` or `wlx taskd --link PUB,REP` and a terminal client, `wlx console --sub PUB --req REP --as WHO`. **The browser console exists** (P4d-2b slice b1, 2026-09-26, read-only then; the box's writes since b2a and its session forms since b3a-2, below): `wlx serve --link PUB,REP --http HOST:PORT --health-token-file PATH` is its own process — a stdlib `ThreadingHTTPServer`, one `ZmqConsole` on a telemetry thread, server-sent events to each browser from a bounded queue, and every pane rendered in Python (`web.py`) so the page's script only swaps fragments. The wl-works fonts are bundled and served by the box, so the page never reaches the internet (PI, 2026-09-26). Reads are open to the LAN. **Writes come from the box** (P4d-2b slice b2a, 2026-09-28): `POST /commands` is accepted only from a loopback peer, with a `Host` naming loopback, the page's own `Origin` and `Content-Type: application/json` (spec §2), and recorded as the box's actor map (`{"kind": "box", "name": …}`) and shown as `NAME (box, unverified)`; every request is answered only when its `Host` names this console (`--allow-host` adds names). `wlx serve` owns each socket on one thread — a read-only telemetry thread, a command thread whose REQ socket waits for `taskd`'s acknowledgment (*sent*, *not delivered*, *busy*), and a mark thread that sends the signal ahead of every command. **A demo is steered and drawn here** (demo mode §4.4-§4.5, 2026-11-14): given `--link`'s fourth endpoint, `wlx serve --link PUB,REP,MARK,GAZE` takes a demo's pointer reports, `POST /gaze`, gated exactly as `/commands` is (`_writer`, the write checks factored out of `_command`, never `may_write` alone), answered 409 while no demo session runs; one page steers at a time, kept until it lets go or is quiet for `serve.STEER_HOLD_S`, and a gaze thread of its own owning a `link.ZmqGaze` pushes each report, packed as `pointer.MESSAGE` and numbered with `wlx serve`'s own rising count, with the non-blocking send. Each `Drawn` the telemetry thread reads goes to `Hub.offer_drawn`, never `offer`, and is drawn with the exact drawer on a thread of its own (`demoscreen.Drawer`), each drawing sent to every stream as its own server-sent event, `drawn`, in order and apart from the frames, with the key list for its screen's keys (`web.demo_keys`), a stream that connects being sent the latest. **The page shows and plays a demo** (demo mode §4.1-§4.3, §4.6, its Task 9): DEMO in the header on every demo frame; while the frame says demo, the demo screen in place of the replica pane, showing only a drawing of the session the frame is, opened full-window by F, a click or `#demo` and closed by Escape, under it the last trial's outcome and the key list (the number keys' inputs, B, Escape and §3.3's limits, `web.DEMO_LIMITS`); the pointer turned into degrees from the drawing's own eye group, `atan(x_cm / D)` per axis, and posted to `/gaze` at most once an animation frame while it moves and at least every `web.GAZE_EVERY_MS` (`demoscreen`'s one definition) while still, one in flight, with the page's random id and a rising `seq`, a 504 or 503 (no rig connected to the gaze endpoint, or the gaze thread busy; never between runs since the demo build's review, M1) said quietly and the reports kept going; the number keys and B only over the drawing or in the full window, never while typing in a box; Escape or the page going away a `release` (`fetch` with `keepalive`); a page that may not write sees the drawing and no dot; the CSP admits `data:` images, the drawing's PNGs, and nothing else. Its New session dialog offers a demo service `REFERENCE` alone, the departure and the id (`demo-YYYYMMDD-HHMMSS`) filled with the clock's now, and on a rig service whose idle frame says `gaze` and offers `REFERENCE` a **demo** box that fills the same and locks the subject, grayed saying why otherwise; the open sends `demo`, a boolean on the wire since this build (`link._command_from`, absent false). A stranded demo in a rig's demo folder says so (`Stranded.demo_folder`, schema 21, XC-504): the page and `wlx console` say it holds up only another demo, and *new session* stays live beside it. Writes from people signed in to wl-works are b2b slice 2, below | Runs against a fake `taskd` (`link.Simulated`), or a real one over loopback sockets |
| `neurofeatd` | Acquisition PC | C++ | SpikeGLX `fetchLatest` on the filtered AP stream -> MUA features -> ZMQ PUB | Synthetic feature publisher |
| `rhxfeatd` | Intan host | C++/Rust | RHX Spike Output socket -> features -> ZMQ PUB; bounded reader | Synthetic spike-raster publisher |
| `labhost` | Task PC | Python | The pull-only endpoint wl-works polls — **a surface of `console` since 2026-09-19, not its own process** (S9a §7): same server, separate path, separate auth. Served as `GET /health` by `wlx serve` (`health.py`, P4d-2b b1): `HealthResponse` schema 1, contract-tested against wl-preproc's own model; a bearer token read from a file outside the repository, compared with `hmac.compare_digest`, one `401` for every credential failure — the rules of wl-preproc's `responder/handler.py`. Exactly one reading is featured, the most urgent (PI, 2026-09-26), because wl-works shows only the first | Contract tests |
| `openiris` | OpenIris PC | (existing C#) | dDPI tracking; UDP 9003; remote API; analog out | UDP replay server |

Welfare-critical modules requiring human review: reward scheduling and per-delivery limits,
fluid and session-duration accounting (a fluid **floor**, an out-of-cage **ceiling**),
token-to-fluid conversion, stimulation bounds and gating, and the bounded-config loader.

**In code, that is `wl_xcon/bounds.py`, `wl_xcon/welfare.py`, `wl_xcon/marks.py` and
`wl_xcon/stranded.py`, two functions in `wl_xcon/preflight.py` (`out_of_cage`, `gate`),
seven in `wl_xcon/service.py` (`Service._open`, `Service._end` with `Service._unended`,
`Service._close_stranded`, `Service._start`, `_unasked`, `_folder_name`), three functions in
`wl_xcon/cli.py` (`_load_bounds`, `_settle_departure`, `_settle_return`) plus one line inside a
fourth — and, since
P4d-2b b2a, five functions in `wl_xcon/taskd.py` plus two parts of a sixth
(`Session._command`'s `held` pass-through and one `except` line), and one function in
`wl_xcon/link.py`.** The
modules are kept small deliberately: everything in them can hurt an animal if it is
wrong, and a small file is one a person can actually read before signing it off.
**`marks.py` is the out-of-cage interval's two marks, decided once for the terminal and
the page** (P4d-2b b3a, 2026-09-29; the PI: "The page takes both times", under the
terminal's exact rules through one shared piece of code): the parser that turns a typed
clock time into an instant (`clock_time`, `clock_or_now`, which were
`cli._wall_clock_time` and `cli._clock_or_now` and moved unchanged), whether a far mark
was confirmed or amended, by whom and how, and the row that says so. `welfare` refuses
what is impossible, but a wrong instant that is merely plausible passes every refusal,
so the parsing and the confirmation are part of the limit. **Two of the `cli` functions are
`_settle_departure` and `_settle_return`**, the terminal's prompting around `marks` —
which answer a person gave, and the name and reason an amendment carries — and **the
line is `main`'s `_marks.depart(session, departure)`**, which marks the departure as
`marks` decided it, `confirmed=` included, which `welfare._refuse_unconfirmed` trusts
its caller on. **The third is `cli._load_bounds`**, the bounded-config loader this section's
first sentence names (on the list since 2026-11-07; the PI, asked that day: "Add it to the
list"): it loads a subject's bounded config, the file a `wlx run` or `wlx taskd` session's
ceilings and floor are read from, and refuses a file that does not define a `Bounds` as
`BOUNDS`. It reads that file from its source each time, never a bytecode cache that could
hold the limits as they were before a rewrite of the same size within the same second
(changed 2026-11-08; the PI, asked that day: "Approve the fix"). A change to any of these, or to the two `preflight` functions, the seven
`service` functions, the `taskd` and `link` functions and the two parts of
`Session._command` below, is a change requiring review; a change elsewhere is not.
Since 2026-11-07 the list is also data, and enforced (the PI: "turn the welfare check ... into
tests in the repository"): `tests/welfare_manifest.json` holds each item with the SHA-256 of its
source as last approved (a line, its count), and `tests/test_welfare_manifest.py` fails when an
item changes, cannot be found, or has its name bound more than once in its module; when the
manifest names what this section does not; and when the summary above counts or names a function
or part, or this section names a constant (a module's upper-case name), that the manifest lacks.
The suite cannot see an approval, only that a hash was updated, and the manifest lives in the
branch it judges, so **at a merge** `git diff <base> <head> -- tests/welfare_manifest.json
tests/test_welfare_manifest.py tools/welfare_diff.py` is empty, or each changed item's `approved`
names the PI's approval with its date and any change to the check itself has been read:
`tools/welfare_diff.py <base> <head>` prints each item `SAME` or `DIFFERS` between the two, and
fails on a manifest change whose `approved` does not name the PI and a date or is the base's
unchanged, on a removed item, and on a change to the check itself.

**`preflight.out_of_cage` and `preflight.gate`** (P4d-2b b3a): the first is what refuses
a new run once the out-of-cage limit is reached between runs, and the second is S9a
§10's rule — fail blocks, an unknown proceeds only on a named acknowledgement written
into `runs.jsonl` — and a mistake in it lets a run start that should not.

**`stranded.py`, `Welfare.restore_departure`, and `service.Service._open`, `_end` (with
`_unended`, its refusals before anything is marked, which a run in progress asks too, so an
End refused before anything is marked never stops a run) and `_close_stranded`** (P4d-2b
b3a): the rule that no session opens while an animal's return is missing from the record,
how such a session is found and its return taken, and the page's route into the two marks.
`restore_departure` reads back a recorded departure without `left_cage`'s refusals, which
were applied when it was taken; a mistake in any of
these leaves an animal out of its cage with nothing saying so, or records its return
against the wrong instant. **Since XC-026 (2026-10-01) a stranded session can also be
resumed** (the PI: "Resume or end"): the page offers *resume session* beside *end
session…*, and `Service._resume` reopens the same session from its record (`resume.read`,
then `Session.resume`) — between runs, or waiting for its return when its runs were ended
before its process stopped (the PI, 2026-10-01: "Bring it back waiting"), its departure
restored by `restore_departure` and
never re-taken, its fluid so far by `Welfare.restore_fluid`, its next run numbered on and
every block and trial number continuing, its out-of-cage limit the one the session last had,
and its last run as its record left it (`Restoration.last_run`), which its next run of the same
task and plan goes on from where that run stopped with its process (the pop-out search build's
Task 6; "Plans and blocks" below).
It is refused, before anything is written: while a session is open; for an id that is not
stranded, or one marked not resumable; when its record cannot carry it (written before XC-026,
or before engine build B, so what the session is for is unknown; unreadable; a start row without
its run numbers; or a `config.json` naming another session than its folder, or a session kind
other than training, piloting or recording) or names two animals. **A damaged `warnings.jsonl`
row is left out, never a refusal** (the PI, 2026-10-11, XC-352's C11): a field missing, a code
or detail that is not text, an `accepted_in` that is not a list of those kinds, a warning
`warnlist.Entry` refuses (an empty code, a code holding ",", "(", ")" or "×", or a kind named
twice), a `session_kind` other than `config.json`'s, an `at` that is not a finite number, a
`by` that is neither an actor's map nor null, or half a line; its warning is asked again, and
the resume says so on the changes feed and in its `session resumed` row, which names the
calibration the session now runs on; one resumed on another calibration than its `config.json`
names is a warning its first run asks to accept, naming both (the warnings-over-refusals
review's I2), never a refusal; so is a stereoscope session resumed on another half-IPD than
its `config.json` names (its settings file removed, added or changed while `wlx taskd` was
down; `setup changed`, Task 7's review, I1), whose `session resumed` row names the half-IPD
it now runs on.
It is refused, too, when its animal's bounded
config or settings will not load, or its bounds changed since it opened; when the animal is
past its out-of-cage limit, on the recorded departure and that limit, after which the page
offers only *end* for it; and when
the record holds a value its animal's bounds or `welfare` refuse (a reward size over its
maximum, or a fluid that is not a real, non-negative number), which `Session.resume` checks
before its first write; the out-of-cage limit over its maximum, or one that is no number, is
refused one step earlier, by `Service._resume`'s own copy of that limit, as it checks the
past-limit stop. A resume is not a new session, so
the rule above still holds; with two stranded, each is resumed or ended on its own.
`Service._resume`, `Session.resume`, `resume.py` and `Service._built` are not on this list:
the PI was asked whether the resume code should join it, and answered "None of them"
(2026-10-02, approving XC-026's eleven-item welfare summary). `_built`, the build handler
`_open` has shared with `_resume` since that plan's Task 4 review, was in the same summary as
a change to `_open`.
**And `service._unasked`** (the b3a-1 review's Ruling 1): a
page's *confirm*, or a departure's *amend*, is taken only as the answer to the question
the service posed — for that mark, that session and the instant it asked about, and for a
departure the animal, deployment and setup of the open it was asked about — since the
PI's rule for a far mark is a warning the experimenter clicks through, and nothing on the
wire tells a click-through from a confirm sent blind; a mistake in it lets a far mark be
taken that no person was shown. **And `service._folder_name`** (fix round 1): one folder
name, the rule for a session id, an animal and a run's task from the wire and for a
stranded record's animal, whose `bounds.py` is code the service runs — a mistake in it runs
a file from outside `--subjects` on the return path, or from outside `--tasks` as a run
is checked. **And `service.Service._start`** (P4d-2b b3a), which asks S9a §10's
gate of a pre-flight taken as a run is started, never an earlier one, with the out-of-cage
item always among its items — so a run past the limit is refused before `RUN_START`, since
`Session.run` refuses none — and hands the run, for its start row, who acknowledged each
unknown (since engine build B, the name of whoever acknowledged it at an earlier run of the
session when it is carried, below), writing nothing itself; a mistake in it starts a run that
should not start. Since engine build C2b it hands the run the plan its start names, its pre-flight
taken for that plan -- a plan the task lacks fails that pre-flight's task checks, which the gate
refuses -- three lines (the engine C2b plan's Appendix A, item 1). **Since the pop-out search
build's Task 6 it hands the run the block of that plan its start names** (`start_block`), its
pre-flight taken for that block too -- a block the run cannot start at fails the task checks, which
the gate refuses -- two lines and a docstring sentence (the PI, 2026-11-07, asked in the UI:
"Approve").

**`Service._open` and `Service._start` and the warnings list** (engine build B: approved by the
PI as planned on 2026-10-08, and as built on the day he approves its welfare summary): an open is
refused, before anything is marked, until the warnings its session's kind accepts (the default
calibration's, a calibration's age past 30 days, a chaired session's free head) are accepted, each
by its code and its sentence, and that is its only new refusal; since the PI's rulings on XC-352
(2026-10-11, E1 and E2) a calibration that will not load, in whose place the default runs, and
one dated after today are among those warnings, accepted in every kind (until then no kind
accepted them, and they failed every run instead); none stops `wlx taskd`; what an open
accepted is written once the service holds the session. A run's pre-flight has a `warnings` item:
a fail for a warning the session's kind does not accept (or for warnings that cannot be listed),
otherwise an unknown acknowledged by name while any is not yet accepted this session, which names
and says each whole, however long (XC-353; since 2026-10-11 no length fails it, XC-352's B1), and
a pass once each is. The pre-flight's unknowns are acknowledged once a session and carried to its
later runs while each one's sentence is unchanged, under the name of whoever acknowledged them;
`_start` writes nothing, and what it accepted is written as the run starts, inside the run's
containment.

**`Service._open` and demo mode** (2026-11-14; the PI approved both changes and the design on
2026-11-07, asked in the UI: "Approve both and the design"; demo mode's design §8 and §15): a demo,
the mouse on a page as the eye, opens through `_open` as any session does, in a demo service
(`wlx taskd --demo`) or from a live rig's own page, with two changes. **A demo is refused for any
animal but the test monkey, `REFERENCE`, before anything is written**: after the open-session and
stranded refusals and ahead of the departure's question, so no question is posed, nothing is
marked, no folder is made and the id stays free, and nothing simulated enters another animal's
records. **A demo session gets the simulated card and pump, and on an unmeasured rig the stand-in
field, whatever the service was built with**: decided in `_open` and passed to `_build`, so no demo
can open a real valve. Neither touches a reward's size, a limit, the fluid count (a demo's rewards
are counted as any session's, on the simulated pump) or any clock, and every limit runs against
`REFERENCE`'s eight-hour file. What else keeps a demo apart is off this list, which the PI kept
unchanged on 2026-09-30: its own folder (`--demo-root`, or a demo service's), never resumed, only
ended (`Service._resume`), and a demo command reaching `Service._session_for` by any other path
refused. A stranded demo's return is taken by `_end` and `_close_stranded`, unchanged, with the
service pointed at the demo folder for that one call (`Service._in_demo_root`), and its End is
refused, ending nothing, while a session under `--root` has its id. **Only a record saying `demo`
for `REFERENCE` is a demo there** (2026-11-16, the whole-build review's I1): any other stranded
record in the demo folder -- a real animal's session in a folder later named as `--demo-root` -- is
the session it is, held in `stranded`, where `_open`'s unchanged rule refuses every open on it,
published as an animal's (`/health` degraded), resumed or ended in its own folder, and warned of at
start (`service._demo_folder_split`); every session there that is no demo, stranded or not, is named
at every start (`service._not_demos`).

**The three `taskd` functions are `Session._ends`, `Session._hold` and
`Session._manual_reward`** (P4d-2b b2a, 2026-09-28; the third since the PI's 2026-09-28
amendment). `_ends` is the one place the trial loop asks `welfare.must_stop`, between
trials and on every pass of a paused session alike, and where a scheduled stop — "after X
mL this session" among them, read from `welfare.session_total()` — ends a session; it asks
the limit first, so a session at its limit ends as `limit`. `_hold` is the paused loop:
no trial runs, so the task rewards nothing; each pass still drains, publishes and asks
`_ends`; and during a run the commands it drains are the only ones a manual reward is
given for. `_manual_reward` gives one: a person's press of *give reward*, one delivery of
the bounded config's `reward_correct` through `welfare.Rig.reward`, strobed
`MANUAL_REWARD` first — during a run only while it is held paused, and since P4d-2b b3a-2
(spec §6.0, PI 2026-09-29) in a `wlx taskd` session between runs and while its animal's
return is awaited — and refused at any other time: during a trial (XC-157), with no
session open (XC-158), after a `wlx run` session's run (XC-184). **Which phases outside a
run give one is `taskd.OUTSIDE_A_RUN`**, a constant `_manual_reward` reads, so it is part
of that function's rule: a change to it is a change requiring review (the b3a-2 final
review, m3; the page's `web._hand_reward_now` repeats it, pinned equal by a test).
`Session._command` hands every reward to `_manual_reward` first, in every phase, with
`held`, which only `_hold` sets — so a change to that pass-through is also a change to
welfare-critical behavior. All
three call `welfare` unchanged, and none holds a clock or a limit of its own; they are on
this list because a plausible mistake in any — the limit asked on one path and not the
other, a paused session that forgot to ask, a reward given while trials run, given outside
a run where no session is open to count it, or paid from another entry — ends a session
late or rewards an animal when nobody meant it to, and passes every refusal `welfare` has.
*2026-10-18: the PI approved passing the `MANUAL_REWARD` number `_manual_reward` emitted into its
`_control` call, so the reward's row in `controls.jsonl` says which code it strobed (wl-preproc's ask,
XC-321 ask 1); a record-only change, since nothing about how much is given, when, or what is refused
moved.*

**The other two `taskd` functions are `Session.set`, whole, and `Session._schedule`; the
line is `Session._command`'s `except (Exceeded, TypeError) as refused:`; and the `link`
function is `link._setting`** (the P4d-2b b2a final review, 2026-09-28: `set`, the line
and `link._setting` are what the PI's items 3 and 4 rest on, and `_schedule` is what item
2 rests on). `set` is the one write path for a setting from a console: its two type
guards refuse a value that is not a number, for a welfare ceiling and for a numeric
parameter alike (M8, item 4), and it sends a ceiling's name to `bounds.validate`, which
is what keeps a reward size set from the page under its approved ceiling (item 3). **A task's own
setting outside its declared range** is checked again with the range widened to it, and since engine
build C3 with each condition of the run's plan and each extreme of a draw in force, once per
distinct set of values outside their ranges (`Session._beyond_range`, not on this list), refused
only for what breaks the run and otherwise
staged with its warnings, which are written to `warnings.jsonl` (the PI, 2026-10-11, XC-352's
D2); since the console settings build (2026-11-18; the PI, 2026-11-16, "Hard limits only where
impossible") every declared bound is a hard limit, so that check refuses such a value first,
saying the limit's reason, by the same path; the ceiling's branch is unchanged, byte for byte,
and so is `set`.
`link._setting` is M8 where bytes become a command — in `_command_from` for the wire's
`_decode_command`, and in `serve.parse_command` for a `POST /commands` body: a `set`'s
value directly and, through `_command_from` since P4d-2b b3a-2, each starting value a
page's `check` or `start` carries — refusing a value that is neither a finite number nor a
bounded word before any session sees it. The `except` line turns what `set` raises into a
refusal on the feed, and a ceiling's refusal into a row in the record, rather than the end
of a session (item 4); like `main`'s `confirmed=` line, it is one line, and with the
`held` pass-through above it is all of `_command` that is welfare-critical; the rest of
that function is ordinary. Since engine build C2a three branches of that rest, beside the pause,
hand `ClearOwed`, `Drum` and `Training` to `Session._clear`, `_drum` and `_train`, which are not on
this list and touch no reward, bounded setting, clock or pump; `_hold` drains through `_command`, so
one sent while paused is applied while paused (the PI approved the first two with the plan on 2026-10-13 and
the third on 2026-10-18: the engine C2a plan's Appendix A, items 1 and 4).
Since engine build C2b two more hand `NextBlock` and `BackBlock` to `Session._move`, likewise off
this list, touching no reward, bounded setting, welfare clock or pump (the engine C2b plan's
Appendix A, item 2, approved by the PI, 2026-10-19).
Since engine build C3 one line of that rest, ahead of `set` in the setting path, runs the live
refusal of settings no animal can get right (`Session._impossible`, off this list; TSK-69): it raises
only `Exceeded`, or what `set` raises on the same value, which the listed `except` line turns into a
refusal on the feed; a check that cannot run refuses the change, never the session; and it leaves to
`set`, unjudged, a ceiling's name, so no reward size passes through it, and every value `set`
refuses (the C3 spec's §14 item 2, approved by the PI for the design, "Approve all four",
2026-10-30). A run's start is refused for the same combinations by `wlx taskd`'s pre-flight
(`preflight.beyond`, failing its starting-values item) and, for a run that takes none, by
`Session.run` before its first trial; neither is on this list.
Since engine build C3 two more branches beside the pause hand `HandBack` and `SetRange` to
`Session._hand_back` and `_range`, off this list (the C3 spec's §14 item 1, approved by the PI for
the design, "Approve all four", 2026-10-30): each refuses what it cannot accept with its sentence,
a check that raises among them, and never raises; what it accepts applies at the next boundary in
`_apply_staged`, with the values staged. **Neither passes through `set`** (an amendment to the C3
spec's item 3, approved by the PI on 2026-10-31, "Approve (Recommended)": the engine C3 plan's
Appendix A, item 5). A
hand-back carries no new value: it puts back the run's own starting value, judged at the run's
start for trials no animal can get right and, in a `wlx taskd` session, checked by its pre-flight
(`wlx run --set`'s are not range-checked, XC-371). A range changes a draw's numbers, never its
kind, each a finite number from `link._setting`, refused where they cannot be drawn
(`check.undrawable`) and where an extreme outside the setting's declared range breaks the run
(`_beyond_range`, as a typed value). Both are refused where they would leave trials no animal can
get right, and both refuse a ceiling's name: a reward size is never held as a task setting nor
drawn.
Since the console settings build (2026-11-17) a fourth branch beside them hands `SetForm` to
`Session._form`, off this list, written beside `SetRange`'s, the listed first statement and the
listed `except` line unchanged: a person's draw of a timing setting, refused with its sentence and
never raising, as a range is. **It does not pass through `set`**: a draw is no value, each of its
numbers decoded by `link._setting` on the wire, called unchanged. It refuses a ceiling's name and
any setting not in seconds, so no reward size is ever drawn; what it accepts applies at the next
boundary as a `form` change row, which strobes, and is drawn each trial, fresh on a repeat,
until a typed value (`set`, unchanged), a hand-back or a revert ends it. A size scaled by
eccentricity (since the build's Task 6) takes the same branch and the same refusals, for a setting
a look draws its size by alone, so no reward size is ever scaled either. A fifth (the build's Task
7) hands `SetColor` to `Session._color`, written beside them, off this list: it maps the set and hue
picked to the one choice the setting declares, then calls `_impossible` and `set`, unchanged, as a
revert sets a value, refusing with its sentence and never raising; no ceiling has choices, so no
reward size is picked. A new color (`DefineColor`, the build's Task 8) never reaches `_command`:
`Service._route` and `_Routed.drain`, neither listed, take it to `Service._define_color`, which
writes a proposed color-set file beside `--tasks` and sets nothing.
A sixth (the build's Task 10) hands `Shaping` to `Session._shaping`, written beside `SetRange`'s,
off this list, the listed first statement and `except` line unchanged: the training switch, on,
frozen or the plan's full task (`task.FullTask`, `Plan.full`), refused with its sentence and never
raising, staged to the next boundary and applied there (`Session._apply_shaping`) as a `shaping`
change row that strobes nothing. **It passes through no `set` and moves no reward size, no session
duration and no fluid**: frozen holds the stage, the staircases and the pool's pairings, and full
plays task settings only, a full task giving a bounded setting refused at load (`bad-full-task`);
`_schedule`, `_hold`, `_ends` and `_manual_reward` are untouched.
Since the console interface rework (2026-11-19) **a box's command is judged answering its press**:
around the setting path's listed `try`, and around the hand-back's, range's, form's and color's
branches and the refusal outside a run, `_command` calls `Session._answering_for` and
`Session._answered`, off this list, the listed first statement, the listed `except` line and
everything after it unchanged. They hold the command's page-made id and a value's carried form
while it is judged, so a refusal made then (`_refuse`, which keeps them beside `refusals`) and what
it stages name them on the feed, and gather the warnings `_laid_out` accepts for it; they decide
nothing, refuse nothing and touch no reward size, clock or pump. The id is decoded beside the
command by `link._cid`, never by `link._setting`, which is unchanged. **A whole setting sent a
fraction** is refused by `Session._impossible`, off this list, raising only `Exceeded`, which the
listed line turns into a refusal; it never judges a ceiling's name, and `set` is unchanged.
Since its plan's Task 4 two more branches beside `SetRange`'s, as `Revert`'s is, off this list, the
listed first statement and `except` line unchanged and no second such line written, hand
`ApplyMany` (wire kind `apply_many`) to `Session._apply_many` and `Withdraw` (`withdraw`) to
`Session._withdraw`, each between the answering calls above. **An apply of several** -- a group
box's Apply or an Apply all, one act of 1 to 64 values, ranges, draws and color picks, each decoded
on the wire by its own kind's rule, so every value and number passes `link._setting`, called
unchanged -- is judged together and staged together or refused whole, nothing staged, each change
refused with its own reason or "refused with" the one that refused it: each change alone first
(`Session._value_faults`, the whole-number refusal among them, `_color_choice`, `_range_new`,
`_form_new`), each value then **through `set`, unchanged**, then the run with all of it at once
(`_possible`, `_laid_out`), as a revert is judged; what it accepts applies at the next boundary as
today, each change its own act and row. **A withdrawal** takes back, while it waits, every change
the act of its command id staged, and writes one `withdrawn` change row for each setting it covered
(XC-529), strobing nothing; once the act has applied it is refused, "already in force from trial
N", writing no row. **It is read ahead of the boundary that would apply it** (the rework's
whole-build review, C1): `Session.run`, not on this list, drains a boundary's commands once, hands
each `Withdraw` to `_command` before `_apply_staged` (one naming an act sent earlier in that same
drain waits for it, in arrival order; `taskd._ahead`), then applies what waits, `_repooled`,
`_check_marks`, and hands the drain's other commands on in arrival order, so a press made from the
frame that showed the change waiting reaches it in time, while a change staged in a pass still
applies only at the next boundary and is on that boundary's frame (`Telemetry.staged`), and a
mark's stamp is still written ahead of its note. The frame lists each act withdrawn by its command
id (`Telemetry.withdrawals`, kept as deep as the frame's refusals), the rig's word the page waits for
before it says "withdrawn". A reward size refused in an apply of several is written to the record
whatever its place in the act. **Neither touches a reward size**: a welfare ceiling's name in an apply refuses
the whole, with a sentence, its refusal written to the record as a ceiling's always is, and a
withdrawal naming a reward size's change is refused, so a staged reward is never taken back and
never sent beside other settings (XC-527: a reward size in either would need the listed refusal
recording repeated and a staged reward withdrawn, which is the PI's to approve, and is not built).
Neither changes `_schedule`, `_hold`, `_ends` or `_manual_reward`.
Since the pop-out revision's Task 5b (2026-11-19) one more branch beside `SetColor`'s, off this list,
the listed first statement and `except` line unchanged, hands `SetChoice` (wire kind `choice`) to
`Session._choice`, between the answering calls: **one of a setting's declared choices picked by its
words** (`link.choice_words`, the words its row's `choices` give; a look's shape, a disc, a ring or a
square, is no number, no word `link._setting` takes and no color-set light), mapped to the one
choice those words name, then `_impossible` and `set`, unchanged, as `_color` does, refusing with
its sentence and never raising. The words are decoded on the wire by `link._word`, as a color's set
and hue are, never by `link._setting`. **It never picks a reward size**: no ceiling has choices,
and a ceiling's name is refused first, its refusal written to the record as a hand-back's is; in an
apply of several it is one more kind of change, refused whole beside a reward size as
any change is, and a withdrawal takes it back as it takes a value. **A whole setting's range's and
draw's ends** are judged whole off this list (`Session._whole_ends`), and **a run's starting value**
in the pre-flight's starting-values item (`preflight.values`), never in `preflight.gate`.
Since engine build C3 a third branch beside the pause hands `Revert` to `Session._revert`, off this
list (the C3 spec's §14 items 1 and 3, approved by the PI for the design, "Approve all four",
2026-10-30). **Revert is on the welfare summary**: it takes the run back to an earlier moment of
it, restoring task settings and drawn ranges only. Each value it puts back goes through `set`,
unchanged; its hand-backs and ranges go as the two buttons' do, without the buttons' widened
re-checks of ranges widened since (each layer it restores was checked as it was made), as approved
by the PI on 2026-10-31 (the engine C3 plan's Appendix A, item 5); and all of it is judged at once for trials no animal can get
right. If `set` refuses any one value, or that judgment refuses the whole, or a check raises, none
of it applies and no change row is written, though a warning `set` accepted for one of its values
ahead of the refused one stays accepted. **It never reaches a bounded setting**: a reward size is
staged and applied by `set`'s and `bounds`' own branch, never held as a task setting and never
drawn, so no moment a revert goes back to holds one.
Since the pop-out search build (2026-11-07) one more branch beside the pause hands `Decline`, the
trainer's hold of the rig's suggestion under a confirmed progression, to `Session._decline`, off this
list (the PI approved the branch on 2026-11-07): it refuses with its sentence a suggestion no longer
standing, else writes a `declined` change row and starts the declined move's window afresh; it
touches no reward, bounded setting, welfare clock or pump. A confirmation goes by the existing
`NextBlock` and `BackBlock` branches, unchanged, to `Session._move`. The held pass-through and the
`except` line are unchanged, byte for byte.
`_schedule` fixes the target `_ends` compares against — a
trial count from the trial about to run, an instant on the session's clock, or mL this
session, refused when already reached — so a wrong target ends a session early or late
while every check in `_ends` passes.

The split between the two is what keeps each reviewable. `bounds.py` is **pure** — the
ceilings, the daily *floor*, and the arithmetic of whether a number is past one or short of
it, with no clock, no hardware and no state outliving a question. **Fluid has a floor, not a
ceiling** (PI, 2026-09-06): the daily figure is a minimum the animal must reach, supplemented
by hand after the session [@nc3rs2012refining; @gray2016physiological], so a delivery is never
refused on volume and `Floor` is a different
type from `Ceiling` precisely so the two cannot be confused at a call site. **One ceiling ends
a session, and it is time out of the cage** (PI, 2026-09-19): out of the home cage to back in
it, eight hours (the PI corrected the twelve recorded here on 2026-10-01), which is the
interval the institutional limit is about. Chair time and trial
count were the two until then; there is no session-length maximum, per-condition targets are
`scheduler`'s, and chair time is recorded by `HEAD_FIXED`/`HEAD_RELEASED` and bounds nothing.
**Checking a value and moving it are
two calls** — `Bounds.validate` then `Bounds.set` (PI, 2026-09-19) — because a change is
refused when a console offers it and applied a trial boundary later; `set` goes through
`validate`, so the ceiling rule has exactly one home. **A `Ceiling.maximum` is not always a
protocol figure**: it is either that, or a *fault bound* set far above anything a protocol
would ask for, so that what it refuses is software commanding an impossible quantity rather
than an animal earning a ration. `reward_correct`'s maximum is the second kind and
`out_of_cage`'s the first; a bounded config is expected to say which at each entry.
*2026-10-18: the PI approved rewording `reconcile_report`'s fault message ("Approve rewording").
The sync box's delivered line is a count of reward commands that sits before the pump (S8 §5.1),
so a commanded total above it says a reward was counted but its pump call failed before it ran
(`Welfare.deliver` charges first, by design; asked whether to add that cause, he chose "Add it"),
or a command did not reach the line, or a recording is wrong, and never that the pump or the
tubing failed. A message-only change: the module's AST, every string blanked, is identical before
and after. In `welfare.py` the same day, text only: he approved correcting the comment on
`Welfare.commanded` ("Approve the comment fix": commanded is what was asked for, not what the
animal got); the comment on `Welfare.delivered` beside it was corrected too and asked about
afterwards, and he kept it ("Keep it"); and he approved rewording `Welfare.total_today`'s
docstring ("Approve rewording": the day's earlier figure from wl-works, water received by its
rule, plus this session's commanded total). `welfare.py`'s AST is identical with that one
docstring blanked.*

`welfare.py` has all three: the day's running total, two clocks — the out-of-cage one that
bounds the session and the restraint one that is recorded beside it — the wall they are both
read on (`SessionClock`, the host clock read once per session and carried forward on a
steady clock that counts the time the host is asleep; moved here from `taskd` by the P4d-2a
final review, because it decides the interval), the pump, and `Rig`,
which is what a task's `Reward` action actually reaches. **The whole route from a task's
declaration to fluid is readable in `welfare.py` alone**, which is the property to preserve —
"can anything deliver reward without asking the ceiling" should stay a question one file
answers.

**`deliver` also keeps the instant the reward was commanded, once the pump returns**
(`Welfare.last_delivery_wall_at`, P4d-2b b1, 2026-09-26). `Rig.reward` reads that instant
through `Session.wall_now` — the session's `SessionClock`, the one clock every welfare
instant is on — before `deliver` runs, so it is when the reward was commanded, before the
charge and the valve. The charge — `commanded` and `deliveries` — still lands before the
valve opens, as it always did, and the instant is stored only once the pump returns, so a
delivery the pump refused is charged but not timed. It is read for the console's time
since the last reward. Nothing compares it with a limit, and it is not refused when it is
not a number, so a display field can never end a trial.

**Whether a duration limit applies at all is declared, not inferred** (`welfare.Deployment`,
PI 2026-09-19). A rig session declares `RIG_FIXED` or `RIG_CHAIRED` and is refused without both
its mark and its ceiling; a cage-side kiosk session declares `CAGE_SIDE` and has no duration bound,
which S13 §4.0 carries. The field is required on `SessionSpec` with no default, because a rig
session nobody marked and a kiosk session with nothing to mark are indistinguishable to
anything that answers zero — and the absence of a mark must never be what disables a limit.

**Nor may the presence of both.** The interval is opened once, closed once and never runs
backwards: a return is refused unless it closes an open interval, refused while the animal is
recorded head-fixed, and refused before the departure; a closed interval refuses a preflight
and stops a running session rather than freezing its clock. **Out and back is one session**
(PI, asked and answered 2026-09-20): an animal returned briefly and brought out again starts a
new one, at the cost — which he weighed and accepted — of two session directories for an
animal returned mid-day, rather than one record with an unexplained gap. And **both marks are
wall-clock instants, and every welfare duration is read on the wall** (PI, 2026-09-20; P4d-2a
spec §10, 2026-09-26): the departure, the return and the head-fixation marks are kept as the
wall instants they are, so transport and chairing count by subtraction and no caller has a
second base to get wrong. The frame-derived session clock times trials and is passed to
`welfare` nowhere — a simulator counts frames without waiting for them, and mapping one base
onto the other is what failed. S8 §5.2 item 4 has all three accounts.

**Nor may a value that is not a number.** Every guard above is an *ordered* comparison and
**NaN is `False` against all of them**, so one NaN switched the duration limit off entirely —
through a bounded config's ceiling, and through `wlx run --out-of-cage-ago nan` (that flag is
`--out-of-cage-at TIME` since 2026-09-20 and can no longer carry a NaN; the guard stands for
every other caller). `bounds`
refuses a non-finite value at `Ceiling`, at `Floor` and at `validate`, so a limit that is not
a number cannot be constructed at all; `welfare` refuses one at the mark and on the computed
duration. **`inf` breaks them the other way and was not already refused**: it is ordered
but unreachable, so `seconds > inf` is `False` for every real duration and an `inf` ceiling is
never exceeded. An earlier version of this paragraph said `inf` was safe; that was measured
false, which is why the check is finiteness rather than a larger comparison.

Added 2026-09-06, because ceilings alone were not enough: `bounds.check_delivery` was called
by nothing outside its own tests for a week, so a task could command reward, a session could
run to completion, and no ceiling was ever asked. A bound nothing calls reads as present and
is not.

**Not yet welfare-critical, because they do not exist:** token-to-fluid conversion (no token
vocabulary) and stimulation bounds and gating (no `Stim` action). Both belong on this list
the day they are written.

## The task model

**Within a trial: declarative data.** States, guarded transitions, entry/exit actions,
outcome codes. `taskd` executes it; the task never owns the frame loop. Statically
checkable, exhaustively simulatable, renderable as a diagram.

**A state whose wait is zero lasts no frame, since the pop-out revision (2026-11-19; TSK-78).** The
loop takes one edge a frame, its actions drawn on the next, and a state's waits count from the
frame after it is entered; but an edge entering a state whose plain `After` resolves to 0 or less
takes that `After`'s edge on the same frame (`run._Loop.passes`, built between trials), so with
`go_delay` 0 the array and the go are drawn on one frame. At most one such pass a frame, so a
cycle of zero waits ends on the longest trial, never looping inside a frame.

**The fixation point has a hold look and an act look, since the pop-out revision (the PI,
2026-11-16; TSK-79).** It stays on when the stimuli appear, and its change to its act look (an
`Update` of its looks) is the go. Each look is a setting of choices, and **a setting's start may be
one of its choices** (`Param.start`; XC-517): a run, the record (REC-27's form), the pre-flight and
the card take it as they take a choice set live, and a start that is none of them is refused as
the setting is built. A task that hides the point a window held the eye on, on an edge into its
reaction-time state or in that state's entry, is warned at load, accepted in every kind
(`fixation-hidden-at-go`, `check._hidden_at_go`).

**Between trials: ordinary Python.** Condition selection, blocks, staircases, adaptive
updates.

Representation is **Python declarations** (dataclass/pydantic) — plain text, diffable, and
readable in an ordinary IDE with autocomplete and type checking. Tasks are primarily
model-authored under experimenter direction, so the API optimizes for verifiability and
review rather than authoring ergonomics.

Event codes are **allocated in `wl-exptasks`, never invented in a task**; validation refuses
an unregistered code at load time.

**The task object, since engine build C1.** A task file defines one `Task` (`wl_xcon/task.py`;
engine spec §3.5): its trial structures by name, the default one -- the plain run's, and a
condition's that names none -- its plans (since engine build C2b, below), the settings it draws
at random each trial and from what (`Task.draws`, which a block type may replace with its own,
`Block.draws`; since engine build C3), what each of its
settings means (XC-288 §4.1: clear-cut with a direction, expected with
a direction and a note, or not a difficulty setting; and whether the setting is a criterion or a
stimulus), what it offers to choose (or `NO_CHOICE`) and how its reaction time is defined (§4.3),
and whether it needs a fixed head. The common settings' meanings are declared once, in
`wl_xcon/declarations.py`'s shared list, which a task overrides only with a note saying why; the
bounded settings' are a table there, outside `bounds.py`. `check.check_task` refuses a task that
leaves any of it undeclared, and gives one that needs a fixed head, in any session not declared
head-fixed (`RIG_FIXED`), a warning saying why, never a refusal (engine spec §20.1; the PI,
2026-10-11: "the experimenter needs free control most of the time"); `Session.set` validates
against the union of its structures' settings; each run's start row names the task by a hash of
what it declares (`versions.task`), never its path (§4.4), the hash carrying the format its
defaults were read at (`declarations.FORMAT`). The format is defined here, in wl-xcon (the PI,
2026-10-11), and wl-xtasks writes its tasks in it.

**Hard limits and the layout at the values set, since the console settings build (2026-11-18).**
Every bound a setting declares is a hard limit (the console settings design's §4; the PI,
2026-11-16, "Hard limits only where impossible"): a value past one is refused, `past-limit`, live
and at a run's start, by the paths that judged a value outside its range before
(`check.beyond_range`, which `Session.set` reaches through `_beyond_range` and the pre-flight
through `preflight.beyond`), saying the limit's one line of reason (`task.limit_reason`: below
0, a count below 1, a fraction above 1, or the task's own `Param.why`, 120 characters at most); a
bound with no reason is warned at load, `unexplained-limit`. A setting left open on a side
declares no span it was designed for, so the load judges it at its start (`check._at_start`), one
with no start left to the run's; a setting with both bounds is judged over them, and a set size
still declares its highest (`unbounded-set-size`, the PI's "Refuse at load" of 2026-10-14). **The
layout is judged at the values set** (`check.laid_out`): off the field, overlapping windows, a
crowded array, a window whose exit starts the answer reaching the objects, an object window
smaller than its object, touching objects, and a color set shown less saturated than asked or
past what the panel can show over a drawn luminance (`color-set-desaturated`,
`color-set-unreachable`; the whole-build review's I2) (`check.LAYOUT`), each naming the settings
beside their values; any refusal a structure's checks newly give at the values (a target index
past its array, a correlation past 1, a size of 0, a gaze window's radius or an object window's
ratio at or below 0, `bad-window-radius`, the whole-build review's I1); and a wait longer than any the task's own starting values give
(`longer-than-declared`). It is asked at a run's start, over each block, condition and each
draw's and staircase's two ends (`preflight.laid_out`, in `wlx taskd`'s pre-flight), and on every
change as it is offered -- a value, a range, a person's draw, a hand-back and a revert -- at what
the run will hold after it (`Session._laid_out`), compared with the layout at the values in force
(`Session._laid`): a new refusal refuses the change, nothing staged, and each new warning is
accepted by who made it and said on the feed; a layout check that raises at a run's start is
refused as `layout-unjudged`. Between trials, never in a frame. The checks
widened to a value outside its range (XC-352's D2) still run, behind the refusal (XC-516).
**The reference tasks keep only the bounds that stand** (the console settings plan's Task 5):
luminance's 80 cd/m² (the PI's, COL-29) and the training variant's primaries' full drive, a hold's
highest (its state ends at a fixed 10 s, or 3 s for the target's), a set size's highest, and the
standard 0 and 1; every size, window, place, ring, wait for fixation and rotation is open, and a
draw of one gives its own `low` and `high` (`bad-draw` otherwise).

**What a setting's box shows, declared by the task, since the console interface rework
(2026-11-19).** A `Param` may give a plain name, `label`, at most `task.LABEL_LIMIT` (40)
characters, and one sentence of what it is, `help`, at most `task.REASON_LIMIT` (120), each one
printable line (the design's goal 5; the PI, "Plain name, code name small"); declare itself
`whole`, its box showing no decimals and stepping by 1, its start, lowest, highest and step whole
where given or refused at load, `bad-whole` (goal 6; the task declares it, the console never
guesses it from the unit); a `step` above 0, else its unit's (`task.step_of`: `task.UNIT_STEPS`,
s 0.05, deg 0.1, mL 0.01, cd/m2 1, fraction 0.05, × disc radius 0.1, % 1; a whole setting 1; any
other unit 0.01); and, on a fraction, `percent`, shown ×100 with `%` while the setting, its
commands and the record keep the fraction. A task's `groups` (`task.Group`: a title of at most 40
characters, its settings' names, each once, and optionally a sentence placing each of them once as
`{name}`, read by the format parser, its words at most 120 characters) are settings that share one
box and one Apply (goal 8); each names a setting the task declares, sits in one group only, and is
never a ceiling, `reward_correct` or any entry the task rewards through, since "a reward size is
sent alone, by its own Apply" (`check.REWARD_ALONE`), and a group's settings share one section,
where its box sits (`task.section_of`; `bad-group`, at load). Each frame lists the task's groups,
title, settings in order, sentence and section (`Telemetry.groups`, each a `link.GroupRow`;
`Session.groups`; schema 23), which the page draws as one box (the console row above). Two settings declaring one plain name, case and spaces
aside, are refused at load too (`bad-label`), since their boxes would read alike. Each malformed
value is refused as the setting or group is built; each field is at a default that changes nothing
(`declarations.FORMAT` unraised), and each is part of the task's content hash. The reference tasks
declare their set sizes and target indices whole and nothing else; wl-xtasks' tasks, curated with
the PI, carry the names, sentences and groups. **A whole setting sent a fraction live** is refused
with a sentence where a change is judged (`Session._impossible`, ahead of its bounds), nothing
staged, never in `Session.set` (the plan's Review Focus 5); each row carries what the box needs
(telemetry schema 23).

**Sizes scaled by eccentricity, and object windows as a ratio, since the console settings build
(2026-11-18).** A setting a look draws its `size` by (`task.size_settings`: a `Disc`'s, `Square`'s,
`Cross`'s or `Polygon`'s, an array's looks and a look setting's choices among them) may be scaled on
its card (the design's §5; the PI, 2026-11-16, "Size = factor x eccentricity", 0.3° per degree as
in his 2020 arrays; STE-31): a person's form, `task.Scaled(factor)`, sent as a `SetForm` of shape
`scaled`, judged and staged as any form (`Session._scale`) and carried in each trial's values from
the next, `spec.values` keeping the fixed number beneath it, so no `Scaled` reaches telemetry. Each
object is drawn at `factor` times its own true eccentricity from straight ahead
(`task.size_at`, `geometry.polar_of_deg`; never an average, STE-27), bound where a fixed size is
bound, at the item's own cyclopean place (`screen._bind`), from values made between trials. An
object window may be a multiple of its object's radius (`ObjectWindows.scale`, exactly one of it
and `radius`, refused as built; on an array with a look of no single size, refused at load,
`unsized-window`), each object's window that ratio times half its own size at its own place
(`ObjectWindows.radius_at`), the same whether the size is fixed or scaled. The layout reads a
scaled size over the sizes it gives where it is drawn (`check._scaled_sizes`, `task.sized_places`):
a stimulus straight ahead is not drawn, and one drawn smaller than its fixed size says both
(`scaled-small`, a warning); a size past its declared bound at some object is refused
(`past-limit`); a window ratio below 1 is `window-inside-object`. Each trial line writes each
stimulus's `size_deg` and each array object's `size_deg`, `window_deg` and `drawn`
(`record._stimuli`), the scaling itself as its setting's `params` value, its `drawn` the form row's id, and a block end's
`varied` a `{"by": "scaled", "from", "factor"}`; the card says what each object gets in degrees
(`ParamRow.gives`), all as wl-preproc was told (XC-513, group 2).

**The training switch, since the console settings build (2026-11-18; its design's §8; TSK-77).**
A run with a training progression, a staircase or a pool has one switch, `Shaping`, staged to the
next trial: **on**, training as declared; **frozen** (`Scheduler.freeze`), a training
progression's stage moved by no rule, fall-back or time, nothing suggested and a suggestion
standing withdrawn, no staircase stepping, each frozen trial entering no bar nor, in a training
progression, its stage's count of trials or targets, nor its stage's time limit, whose clock
stops while frozen and picks up with the time it had left (`Scheduler.clock_held`; the PI,
2026-11-18, "Stop the clock"; the run's own time limit runs on), a person's move, value and
hand-back still applying; **full task** (`Scheduler.play_full`), the plan's declared finished version
(`Plan.full`, a `task.FullTask`: a block of the plan and values over its conditions, checked at
load, `bad-full-task`), entered as a block of its own, the stage left closing `shaping`, its
staircase held at its hardest level and its values where a condition's own would sit, under a
person's value and draw, each named `drawn: "full"`, no move by hand while it plays; on again, the
stage left reopens as a block of its own at its staircase's level, **picking up where it was**
(the PI, 2026-11-18): its trial count, its criterion and fall-back windows, a confirmed
progression's bars and the panel's last answers, and its time left as the full task found them,
the full task's trials and time in none of them (`scheduler._CARRIED`; `taskd.Session
._stage_spent`), each block's report in the run's end row counting its own trials. Each switch is judged at what it
leaves (`_possible`, `_laid_out` with the full task's block, `Session._full_judged`), written as a
`shaping` change row (`name` `"shaping"`, its two positions, no `sequence`), kept in each moment
(`Moment.shaping`) so a revert takes it back, and said on each trial line (`shaping`), as wl-preproc
was told (XC-513, group 4); a resumed run's replay of its record leaves frozen and full-task lines
out (`went_on`).

**Counting and repeats, since engine build C2a.** Each trial structure declares its counting table
(`task.Counting`; engine spec §16.1-16.2), naming the state its stimulus appears in: every answer
counted; a fixation break, no fixation, a lost tracker and a fault owed, shown again; a break after
the stimulus appears spent or owed as the task says, with no default (`check.check_task` refuses a
structure without a table); no response a miss where withholding is an answer; a wrong answer under
"until N correct" unpaid, never placed as a repeat; and a repeat limit, none unless a task sets one,
counting failed tries in a row of one trial, which any answer ends (the task's limit holding in
every block unless the block sets its own). A block may count by a table of its own
(`scheduler.Block.counting`). The scheduler places a repeat at a free random slot within the next k
trials, k at least 3, never the very next, unless nothing else can be drawn (§16.3); judges every
answer for a block's rule, and only answers (a block whose own table pays a broken hold, or a
failure to acquire the fixation point, as counted -- a hold-training block -- has it judged a miss;
a lost tracker and a fault never) -- a streak (a proportion of 1.0) every try in order, a percentage
every try unless a trainer sets it to *first answers only* (the recorded setting is
`first_answers`); ends a criterion block once its criterion is met, every target is used up and no
drum is waiting, drawing every condition past the targets; drums a block or a run when asked (every
trial that is not right back at once until it is, a console warning after ten failed tries in a
row); and forgives a condition's debt past its limit -- flagged as possible avoidance only when the
animal's own failures reached it -- or when a person clears one trial of it, or the rest, from the
console. **Drumming and *clear* are training aids** (the PI, 2026-10-18): off until a block declares
drumming or a trainer switches either on, with a standing banner on the console (a warning outside a training session) while one is on,
worded for the session's kind. Each trial's row records what it did to the count, whether its
stimulus appeared, the trial it repeats, the condition before it and the aids on; each run's end
row records the shortfalls, each condition's counts, and the run's `trials`, a trial and its
drummed repeats one, beside its `presentations`, the lines written. A trial that reaches the longest
trial, five minutes at the session's rate (`run.LONGEST_TRIAL_S`), is a missed acquisition
(`task.HANG_COUNTS_AS`, counted as no fixation is), owed by its structure's table and one of the N
in a plain "run N trials" run, whose table (`scheduler.EVERY_TRIAL`)
spends every non-answer, and said on the console. A hold runs its own time: the load-time check warns where a timeout on its
state can cut it short, a timeout listed before the hold that ties it included (`hold-cut-short`).
**What a trial draws, since engine build C3,** is arithmetic in one pure module,
`wl_xcon/variation.py`, shared by the code that checks, plays, records and reviews it: each value
from a hash of the run's seed, the trial's number in the run and the setting, never from the
scheduler's generators, so adding a draw moves no condition or repeat; a prepared list in shuffled
passes; the non-aging wait's tail drawn again; a factorial's conditions and their names; and a
sequence-balanced block's de Bruijn sequence, each cycle played as the linear one, its first
trials a lead-in. **The trial loop draws between trials**
(`taskd.Session._draw`): each setting from the open block's own draw, else the task's, or from its
condition's own range, but one a person holds; a repeat, ordinary or a drum's, keeps a `same`
setting's value and source and draws a `fresh` one anew; a factorial's conditions play as
hand-listed ones (`Session._plan`). Each trial's line says what it drew and from where (`drawn`)
and what a person held (`live`), a drawn direction written from 0 to 360, which of a person's
changes kept it out of moving up (`eased`) and its place in a designed block's plan (`planned`);
each run's start row records the task's draws, every field, and what each factorial made
(`generated`), and its end row, for each block, what varied in it -- by its conditions, by a draw
and from which range, or by a person (`varied`) -- and a designed block's plan (`planned`). The
change log (`parameter_changes.jsonl`) holds every change by its kind, each act with a change id:
a value set, a hand-back, a range, a revert, and the clears and switches also written to
`controls.jsonl`, and since the pop-out search build a confirmed progression's two, the rig's
suggestion of a move or of widening the task's pool (`suggested`) and a person's hold of one
(`declined`), appended after the rest; those that strobe `PARAM_CHANGED` carry `sequence`, and resume reads every kind,
failing closed on a row it cannot (REC-28; XC-288 §3.4). **A designed
block** (`task.SequenceBalanced`,
`task.Priming`) plays a plan the scheduler draws as it opens, from a generator of its own: a break
in it is never placed as a repeat, a sequence-balanced block's lost place recorded as a `designed`
shortfall, unless the block brings the trial back at once, under the repeat limit. **A trial a
live change eased** (`Scheduler.record`'s `eased`) is left out of a block's criterion and, in a
training progression, of a stage's number of trials and targets, and still judged toward the
fall-back.

**Plans and blocks, since engine build C2b.** A task declares its plans (`Task.plans`; engine spec
§13.1), and the operator chooses one at run start -- from the page, its pre-flight taken for
it, the task's first preselected for a session's first run and the plan last run for its later
ones (a plain last run repeated as the plain run), the plain run one more choice, or
`wlx run --plan` -- or none, the plain run.
A plan is its block types (`task.Block`: a named set of conditions, each naming the trial
structure it plays and counted by that structure's table unless its block has its own; ending once
every target is used up and, as declared, a criterion is met, a number of trials is run, or its
time runs out), how they follow (`Fixed`, `Cyclic`, `Balanced` -- shuffled rounds within the run --
`Random`, or `ByCriterion`, a training progression that moves up on a stage's rule or its time,
back one on a fall-back rule, and keeps its top stage going) and a run time limit. **A training
progression may be confirmed** (`ByCriterion(confirm=True)`; the pop-out search build, 2026-11-07;
the PI, "Rig suggests, trainer confirms"): no stage moves on its rules; between trials the rig
suggests moving up where a stage's criterion is met on its last answers given at the stage's
hardest step (its staircase at its last level, or a value a person holds at that level or beyond it
in the harder direction, `task.at_hardest` -- "Any trial played at the hardest step counts, whoever
set it there", the PI, 2026-11-07; a value merely near it stays eased -- or any
for a stage with none; an answer at an easier level neither counts nor breaks the window), and
back where the fall-back's is on its last
first answers, each judged on answers as a staircase classes them, never on a trial a person's
change eased toward moving up (`Scheduler.suggestion`); the suggestion is a `suggested`
change row and the frame's `suggestion`, withdrawn once its bar is missed by more than the plan's
margin, in answers (`ByCriterion.margin`, `Scheduler.holds`; the PI, 2026-11-08, "Stay up until 3
below"; 0, as soon as it stops being met), and a person
confirms it with *next block* or *back one* naming it, their `controls.jsonl` row naming it too,
or holds with `Decline`, a `declined` row (`Session._suggest`, `_move`, `_decline`); an answer to
a suggestion no longer standing is refused with a sentence. Every stage works on until a person
moves the run; a stage's time still moves it up. **A task may draw each trial's pair of looks from
a pool of pairings** (`task.Pool`, `Task.pool`; the pop-out search build's Task 5; the PI, "A pool
of four", "Start with fewer, add more", "Trainer picks at the prompt"): the pool's setting is a
whole number, the sum of the numbers 1, 2, 4 ... of the pairings it holds, so the existing `set`,
a run's start and the wire carry it unchanged, and one naming no pairing is refused with a
sentence at load, at a run's start and live (`check.unpooled`); each pairing is named, on the
console, in the review report and in those sentences, by its two looks' words, or by its colors'
names, `blue among red`, where each look's color is a color-set light, else by its place
(`Pool.named`; the build's final fixes); each trial draws one of the
pairings it holds, each as likely, into the odd one's look and the distractors', each line marking
both `drawn` `"pool"`, a repeat keeping its pairing and a person's value on either look holding
it; under a confirmed progression the stage's bar to move up, judged over every pairing pooled,
also suggests widening it (`Scheduler.widening`, a `suggested` row of move `"widen"`, the frame's
`widen`), the stage's move offered first in one prompt that one hold answers whole, the trainer
widening with a `set`, which, as any change to the pool, starts both bars afresh and leaves the
staircase where it is (`Session._repooled`); a widening standing is confirmed where the pool's value
applied at a boundary adds a pairing, by a `set`, a hand-back or a revert, and the change row
applying that value names it (`suggestion`, as a confirming move's control row does; XC-491,
`taskd._pool_adds`, the one rule for both, and `Session._confirms`); the pool carries into the next
stage. **The trainer
taking one half of a prompt re-offers the other at once** (the PI, 2026-11-07, "Re-offer the other
at once"): a move up taken, the widening beside it is made again in the next stage on the bar that
met it (`Session._remake_widening`); a widening taken, the move up beside it is made again on its
own window, which the widening does not empty (`Scheduler.afresh`'s `keep_up`, the widening judged
on a twin window, `_widen`; `Session._remake_move`) -- each a new `suggested` row naming the one it
makes again (`remakes`), the old one answered "made again". **A block may
step one of its settings by a staircase** (`task.Staircase`, `Block.staircase`; the pop-out search
build, 2026-11-07): between trials, as the trial loop draws (`taskd.Session._climbing`), a level
harder after `down` right answers in a row and a level easier after `up` failures, by TSK-33's
classes (`task.staircase_verdict`), never past either end, started afresh as each block opens --
but a stage of a training progression the run returns to resumes at the level its staircase had
when the run left it, its count fresh (`Session._leave` at the move, `_climbing`, `_left`, rebuilt
by `went_on` after a crash from the lines and the start row's `left`; the PI, 2026-11-08, "Pick up
where it left"); a
person's value on the setting holds it and a hand-back resumes it at the level nearest that value,
and each trial's line marks the value it gave `drawn` `"staircase"`. **A task may declare special
trials** (`task.Special`, `Task.specials`; the pop-out revision's Task 3, 2026-11-19; TSK-80): each
kind its name, the setting giving its percentage of trials (in percent, 0 to 100) and the structure
it plays, refused at load where the structure is the task's default or absent or the share no such
setting (`bad-special`), their percentages past 100 at the task's starts a warning
(`specials-over-100`). Between trials, a trial of the default structure is drawn special or normal
from the run's seed (`Session._special`: `variation.unit(seed, trial, "special trial", 0)` against
the shares cumulated in declared order over 100, or over their sum past 100), a repeat keeping the
kind of the trial it repeats (`_specials`, pruned with `_paired`); a special trial plays its kind's
structure with the stage's values, draws, staircase value and pairing, counts in its bars and its
condition's count, **and steps no staircase** (the PI's "Only normal trials move it"; `giving` and
`stepping` apart in `Session.run`, `went_on` stepping only on a normal line). Each line writes
`trial_kind` (`"normal"`, the kind, or null for a task declaring none) and `stepped`
(`_Climb.step`'s answer, null where no staircase runs), and the start row `specials` (XC-543).
**A catch's array has no target** (`Array.found_by="none"`, one of `task.FOUND_BY`; the pop-out
revision's Task 4, its design's §8): neither look check judges it, since its objects may all look
alike, and a structure scoring a `SaccadeTo` or a `Hold` on its family's target is refused
(`bad-array`); **a place left empty** is a `Blank` among an array's looks, drawn as no item
(`screen._items`), no object to the layout checks (`check._neighbors`) and recorded `drawn: false`
on its `objects[]` entry. Each array entry writes `found_by`, and a `"none"` array `target: null`
with the declared place as `odd_place` (null on every other array; XC-543, wl-preproc 2026-11-19).
**Each special kind's structure is judged for what no animal can get right** (TSK-69 revised;
`check.impossible`'s `specials`) on every condition playing the default structure: each kind at
load, whatever its percentage; at a run's start and live (`Session._possible`), each kind above 0,
so raising one is judged when it is set. Percentages set past 100 live are a warning on the feed
(`specials-over-100`, one of `check.LAYOUT`, `check._over_100`). The demo screen labels no
*target* on a catch's array (`pointer.drawn_windows`).
**Every number in a staircase
or a bar may be a setting** (the fix round, 2026-11-07; the PI, "everything should be adjustable in
the console"; TSK-75): a staircase's `down` and `up` and its levels by a step (`task.Steps`), read
from the run's live values between trials, a step changed re-deriving the levels at the level
nearest the value (`taskd._Climb.restep`); a criterion's and a fall-back's proportion and window,
read at each judgment (`task.rule_at`), their windows kept as long as their settings' highest so a
change restarts nothing. **A run may start at a named
block of its plan** (`start_block`; the pop-out search build's Task 6; its design §3.6, "the
trainer picks"), the blocks before it still there to move or fall back to: `wlx run
--start-block`, and `CheckRun` and `StartRun`'s `start_block`; one the run cannot start at (no
block of that name, no plan, an order that draws its blocks at random; `check.unstarted`) fails
the pre-flight's task checks, is refused by `wlx run` before its session opens and by
`Session.run` as their backstop; its start row records `start_block`, null for the first.
**The console's start carries it** through `Service._start`, welfare-listed, its pre-flight taken
for that block (the PI approved the change on 2026-11-07, asked in the UI; see that function's
paragraph above). The pre-flight offers the plan's stages, each staircase's levels and the level it would
start at, and the pool's pairings (`Preflight.stages`, `pool`), which the page's Setup tab draws
and its start sends as values only where a person changed them, and shows the animal's previous
session's end of the plan as its record left it (`Preflight.previous`; `resume.previous`,
`taskd.ended_said`), never carried (the design's §3.6: "nothing carries the stage across sessions on its
own"). **A resumed session's first run goes on from the run its process stopped in** (the
pop-out search plan's Review Focus 4): where it plays the same task, by its content, and plan,
names no block to start at, and that run's record holds no end for it or Ctrl-C ended it, it
starts at that run's stage, its staircase where the last step left it, count and all, its pool,
and a suggestion of a move or a widening still standing under its own id -- read back from the
record by the engine's own rules (`resume.LastRun`, `taskd.went_on`, `Scheduler.judged`), said in
its pre-flight (`Preflight.continues`) and on its changes feed; a person's value held is not
carried, nor a repeat waiting, and a record it cannot read back starts the run at its first
block. A block is one
stretch of trials under one type inside one run, opened by `BLOCK_START` before its first trial
and closed by `BLOCK_END` after its last. **Time limits are read between trials, in the run loop,
never in `Session._ends`**: on the time trials ran, pauses not counting; a drummed trial waiting
finishes first; neither is a welfare limit, and a run they end is `completed`, never `limit`, its
end row saying why (`end_reason`). A plan that can draw no further trial ends its run with a
sentence (the per-advance progress check).
A person moves a run on a block, or back one, from the console.
A live edit wins over a value a condition sets (engine spec §14.7). The load-time checks refuse a
plan that cannot run (`bad-plan`) and warn of one that may not do what was meant. Each run's start
row names its plan and writes it as declared, its end row says how each block ended and which block
of the stream it was (`block_ends`), and each trial's row names the structure it played and any
value a live edit overrode.

A session is a sequence of runs, each a sequence of **blocks**, and **interludes** (sub-tasks
such as calibration that the session enters and leaves without ending; engine build C6). Token
economies require session-scoped state and a persistent display layer that per-trial scenes do
not reset.

**The simulated animal plays a gaze task through the rig's gaze world, since the pop-out search
build** (XC-456, 2026-11-07). A simulated session (`wlx run`, `wlx taskd`, any `taskd.Session` whose
`world` is unset) plays each trial with gaze guards through `gaze.Tracked`, its gaze a simulated
eye's (`wl_xcon/simeye.py`: `Eye`, the sample source, and `Seeing`, `Tracked` showing it the
display; chosen per trial by `simulate.agent`), so the trial is scored by the rig's own map,
staleness, saccade detector and saccade rules (EYE-19), never by a rate. The eye is shown what the
display draws each frame and told each state's first frame, and plays the task's rules as a trained
animal knows them, read from the trial between trials: it fixates the fixation point when it is
shown; it answers once at the go, landing on the target at its `accuracy`, otherwise on a
distractor if one is drawn, else on empty space, after a log-normal latency about its
`rt_median_s`; on `early_rate` of trials it leaves fixation before the go; on `1 - engagement` it
looks away; on `false_alarm_rate` of trials (default 0, which adds no draw) it leaves the fixation window
in a catch's go, a `Hold` ending the trial in a right outcome, to an object drawn else empty space,
and `gaze.Tracked` scores it `FALSE_ALARM`. Its saccades have a minimum-jerk profile with Gaussian noise on every sample, ones the
detector confirms at the session's 240 Hz; its map is the identity (`simeye.MAPPING`). Its numbers
are engineering defaults with no published source sought, but the 85% correct of the engine spec's
"normal" animal (TSK-40), and are `taskd.SessionSpec`'s (`accuracy`, `rt_median_s`, `early_rate`,
`engagement`, and since the pop-out revision's Task 7 `false_alarm_rate`, 0 by default), set in
code (XC-146). A trial with no gaze guard, or one asking a guard no gaze
world answers (a lever, a touch, the photodiode; `simulate.gazes`), stays with the hazard
`simulate.Subject`, as does a census given one (`simulate.simulate`). Until then every simulated
trial was the `Subject`'s, which fires a guard by a hazard rate and has no gaze: the XC-410
review's probe L scored 115 CORRECT / 85 WRONG_TARGET by its rates where the rig scored where the
eye landed. The simulator is not the rig, but `gaze.Tracked` is: a frame through the eye builds
only what a rig's frame builds and the eye's sample (`tests/test_simeye.py`).

## Message contracts (draft v0)

- **Eye samples** (openiris -> taskd): OpenIris-native UDP poll on 9003
  (`WAITFORDATA` -> JSON). We stamp arrival with `CLOCK_MONOTONIC` and compute staleness.
  The protocol is not modified. The ACCES analog copy is a recorded channel, not the
  control path.
- **Neural features** (`neurofeatd`/`rhxfeatd` -> taskd): ZMQ PUB/SUB, msgpack,
  schema-versioned; feature vector, channel-map hash, source sample index, publisher
  monotonic time, sequence number. Latest-wins.
- **Control/telemetry** (console <-> taskd): ZMQ REQ/REP for commands, PUB for telemetry,
  and PUSH/PULL for an operator's mark signal — eight bytes, read by the trial loop once
  per frame and stamped in the frame it arrives (P4d-2b b2a). Bearer token, rate limit,
  and a write-arbitration rule for concurrent writers.
- **Browser** (browser <-> console): HTTP, with server-sent events carrying rendered HTML
  fragments to the page (P4d-2b spec §1). WebSockets are deferred to the replica pane, if
  V11 shows a browser can carry it at display rate.
- **Who did it, in the record** (P4d-2b b2b slice 1, 2026-10-02): every row that names who
  (`controls.jsonl`, `welfare_notes.jsonl`, `runs.jsonl` and its pre-flight
  acknowledgments, `parameter_changes.jsonl`, `refusals.jsonl`, and since engine build B
  `warnings.jsonl`, each of whose rows names who accepted its warning and when) holds `by` as an actor's map
  (`actor.to_map`): `{"kind": "box", "name": …}` for a name typed at the rig PC, or
  `{"kind": "member", …}` for a wl.works member (**`wlx serve` makes one** from a token it
  has checked, b2b slice 2, built 2026-10-05; see the console's second listener below). A row the process writes itself, and a
  mark's stamp, holds `null`. **A string is a name recorded before b2b**; readers take
  it as written (`actor.read`), and no record is rewritten. The page shows the two kinds
  apart (`web._who`), so a box name typed to look like a member's still reads as typed.
- **The console's second listener** (P4d-2b b2b slice 2, built 2026-10-05; spec
  `2026-10-02-p4d2b-b2b-remote-signin-design.md`): `wlx serve --https HOST:PORT --tls-cert
  PATH --tls-key PATH --rig-page NAME=URL --wl-works-issuer URL --wl-works-cache PATH`
  also serves the rig's page over https on the lab network. A member signs in there with
  wl.works (PKCE); the browser holds the tokens in `sessionStorage`. `wlx serve` checks
  each Bearer token offline against wl.works' keys (`signin.py`, imported only when
  `--https` is given) and dispatches the command as that token's `actor.Member`. A broken https setup never
  stops `wlx serve`: the https page is off, the terminal and the rig PC's page say why, and
  the rig PC's page serves. wl.works is asked after binding, and its key set is fetched again
  every 15 minutes (b2b-ready, 2026-10-06). The rig
  PC's plain-http page is unchanged: a box name, loopback only. **`taskd`'s REP socket
  still trusts a member map from any local sender** (`actor.from_map`; XC-218), so
  loopback remains what bounds it. The welfare-critical list below is not widened.
- **Hardware truth:** every trial event gets a strobed word into the recorders and a JSONL
  record carrying the word, frame index and monotonic time. **Each trial is framed in the
  stream** (XC-155): `TRIAL_START` (32) and its `TRIAL_NUMBER` escape (`0x8001`, four
  words) at the boundary before its first frame, and `TRIAL_END` (33) after its outcome
  marker. A trial with no outcome (a hang) still gets `TRIAL_END`; a trial that faults or
  is interrupted gets none. The escape is unbroken on every path the loop takes, but not
  on every exit: a card fault, a Ctrl-C, a SIGTERM or a crash between its words cuts it
  short, and wl-preproc's decoder then takes the next words as its payload whatever they
  are, losing that trial and what comes next with it. When a `wlx taskd` session goes on
  to another run with nothing strobed between, that is the next run's `RUN_START` and, if
  the escape was cut after its first or second word, that run's escape (below), and what
  the decoder makes of the rest can lose the opening of its first block and its first
  trial too (XC-199). wl-preproc's `assemble` then folds that run into the faulted one,
  which reads as closed by design, since the next run's `RUN_END` marker closes it; and a
  cut after the second word reads run number 2, 3 or 4 as a bare `SESSION_END`,
  `BLOCK_END` or `RUN_END`. A block's `BLOCK_START` escape and a run's (below) are cut
  short the same way. Read the stream
  through wl-preproc's `decode_stream`, never by value: from trial 1 the escape's payload
  words take marker values (1-4 are `SESSION_START`, `SESSION_END`, `BLOCK_END` and
  `RUN_END`, 32-38 the trial markers), trial 3's checksum is `BLOCK_START`'s `0x8002`,
  and trial 7's is the run escape's `0x8006`. The
  number counts from 1 across
  a session's runs and is the trial's `trial_number` in `trials.jsonl`, the field
  wl-preproc now joins a line to its recorded trial by: its `events/rigtrials.py`
  keys each line by it, and `nwb/conditions.py`'s `join` matches that key to the
  stream's `TRIAL_NUMBER` (its `main`, `b0f8b52`, 2026-10-01).
  Every line carries ten position numbers (`levels.Position`; session-levels spec §3),
  and since XC-026 (2026-10-01) the fluid commanded during the trial (`fluid_ml`) and its
  last reward's instant (`last_reward_at`), and since XC-399 (2026-10-28) where each
  stimulus it showed was, and when (`stimuli`: for every `Show` and `Update` on the
  screen for a frame or more, its kind, its frame, when its presentation went off, the
  fields an `Update` set, whether its appearance is something to draw, its (x, y) and its
  true eccentricity and direction beside them, the direction from 0° to 360° and null at
  eccentricity 0 since 2026-10-30, an array's objects and target too; REC-26),
  which the trial loop keeps by reference (`run.Result.placed`) and the record resolves as
  the line is written, never in a frame. A position that cannot be resolved is written null with why (`unresolved`), never
  raised, so a trial that ran always has its line, and each unresolved stimulus is said on
  the changes feed once a run for each reason. **A run never starts with a place's setting
  unset** (XC-415; the PI, 2026-10-30, "Refuse to start"): a setting that can hold no value is
  refused at load wherever it places a window, a stimulus, an update or an array's objects (its
  set size, ring radius, phase or target index), or sizes a window, and one nothing gives a value
  in a structure the run plays is refused before the run starts -- by `wlx taskd`'s pre-flight,
  by `wlx run` before its session opens, and by `Session.run` (`check.unplaced`); so a position,
  an array's objects or its target is unresolved only where a value cannot be read (one `wlx run
  --set` binds that is none of its kind, XC-159). **Each trial's start is written too**, as a
  row of `trial_starts.jsonl` — its ten numbers, its run and its task — at the boundary,
  after its words are computed and before its first strobe (XC-026 spec §8a item 1): a
  trial that dies mid-trial has strobed its number and has no line, and a resume takes
  every number from these rows, so none is issued twice after a process crash (below).
  `CONDITION` is not emitted yet (XC-197).
  **Each block is marked too** (the session-levels spec, 2026-10-01): `BLOCK_START`
  (`0x8002`, its `block_in_session` and its task's code, 0 until wl-xtasks allocates
  codes) just before the block's first `TRIAL_START`, and `BLOCK_END` (3) after its last
  `TRIAL_END` when its block type is done or its run ends by design; a run that faults
  or is interrupted (a Ctrl-C or a SIGTERM) sends no `BLOCK_END` for its open block,
  as it sends no `RUN_END`. A block is a
  stretch of trials under one block type inside a run, not a run (the PI, 2026-10-01).
  **And each run, in wl-preproc's terms** (XC-205, sent since 2026-10-01): its `RUN_START`
  escape (`0x8006`, the run's `run_in_session` and its task's code, 0 as for a block),
  unbroken, right after the allocation's `RUN_START` code (4135) and before the run's
  first `BLOCK_START`; and its `RUN_END` marker (4) on an end by design, after the run's
  last `BLOCK_END` and before the allocation's `RUN_END` code (4136). So a run reads
  4135, the escape, each block with its trials and its `BLOCK_END`, marker 4, 4136. A run
  that faults or is interrupted sends neither the marker nor 4136, and a run stopped
  before its first trial is the escape and the marker with no block between. The escape
  and the marker go out whether or not the allocation has 4135 and 4136; wl-preproc
  stores those two and reads nothing from them.
  **A resumed session goes on in the same recording** (XC-026, 2026-10-01): the crashed
  run, its open block and its trial cut short stay unclosed, as for any interrupted run;
  the resume strobes the provisional `SESSION_RESUMED` (4137) once, when the allocation
  has that code, and the next run's escape carries the next run number, with every block
  and trial number continuing, so one recording never repeats a trial, block or run
  number. **That holds across a process crash, not a power loss**: the start rows a
  resume numbers from are flushed to the operating system before their strobes, never
  `fsync`ed, so a host that loses power can lose rows whose numbers the recording
  already holds, and a resume would issue them again. **A resumed rig-fixed
  session strobes another `HEAD_FIXED` (4128) at the resume, with no `HEAD_RELEASED`
  (4129) between, unless its runs were ended before the crash** (XC-026 spec §8a item 2,
  and §3's note of 2026-10-01): a run needs the head marked fixed, and nothing recorded
  whether it was released across the crash. A session ended before the crash had its
  4129 strobed by End session and comes back waiting for its return, with no run to
  start, so its resume strobes no 4128. So a stream holds one or more 4128 and at most
  one 4129, after the last 4128: at the session's end, or before the 4137 of a resume
  that brings it back waiting. The session's own restraint time counts from the latest
  4128, an undercount. Restraint bounds nothing (the PI, 2026-09-19 and 2026-09-26).

## The display: direct view, and stereo as viewports

**Two setups share one screen, fixed 50 cm from the eyes** (`2026-09-28-direct-view-design.md`).
**Direct view** — both eyes see the whole panel — is where most experiments run, the first
animal task included. The split-screen mirror stereoscope is a removable device in front of the
same screen. The operator picks the setup at session start. Each setup has its own field in
`geometry.py`, built from the rig's settings (`tasks/rig.py`): the whole panel less the light
sensors' housings, or the stereoscope's viewport stopped by its mask.

**A task says which setup it is written for**: `Trial.view`, `"direct"`, `"stereoscope"` or
`"either"` (the default). Disparity, a random-dot stereogram or a stimulus shown to one eye needs
`"stereoscope"`, a load-time finding at every load. Check 8 against the session's field, and the
finding for a task written for the other setup, need the session's geometry, and **the checks now
run against the session's own field, from `--rig` and `--view`** (`wlx run` and `wlx check`,
direct view part 2, 2026-09-29): a task that does not pass in the chosen setup is refused before
the session opens. *Since the PI's rulings on XC-352 (2026-10-11, A12)* a task written for the
other setup is a warning saying what that setup changes, not a refusal, unless it shows each eye
its own image in direct view, which an unmirrored screen cannot show; its field still holds it.
The setup is in the session record and in telemetry (schema 23; the setup since 9).

Through the stereoscope each eye views one half of the panel through redirection mirrors
[@wheatstone1838contributions; @cox2019temporal; @dougherty2021binocular]. Therefore one
window, one flip, one refresh clock, no genlock — **two viewports on one framebuffer**, in
cyclopean coordinates with disparity as a stimulus property. A task without disparity or
per-eye content is the zero-disparity case of the same path, and runs in either setup.

Per-eye viewport geometry (center, folded optical path length, deg/pixel) is computed from
the rig file (`geometry.py`, `viewport.py`) until V9 measures it. **Vergence is not set by
angling the mirrors** (optics drawing §6 rules that out): each eye's image is moved by a
software offset, `atan(E/D)` from the rig file's half-IPD `E` and path `D`
(`Geometry.vergence_half_deg`, engine build A1), computed, not measured. Photodiode patches
sit outside both viewports, at a bottom corner, and under the sensors' housings in direct
view. Panel left/right nonuniformity is by construction an interocular mismatch and is
photometered in V9 (validation.md; V1 is display timing). *(Corrected 2026-10-08: this said V1.)*

The **screen description** (`wl_xcon/screen.py`) and the **exact drawer** (`wl_xcon/exact.py`, with
`look.py` and `viewport.py`) exist since engine build A1 (2026-10-07). No session's own display calls
them yet: the display process (engine build E) and the screen log (engine build F) will. Since demo
mode (2026-11-14) a demo's world resolves its screen for the page (`pointer.Drawing`), and
`wl_xcon/demoscreen.py` draws it with the exact drawer for `wlx serve`, never in the rig service's
process: at a preview of the panel (`viewport.preview`, its size chosen by
`tools/measure_demo_drawing.py`'s measurement, `docs/measurements/dev-machine/2026-11-14-demo-drawing-preview.md`),
through the sRGB standard, as a PNG in an SVG labeled as demo mode §4.4's table says, on a thread of its
own that draws the newest screen next. It draws the exact drawer's image bit for bit, faster
(`demoscreen.draw`): the background once, then each group of stimuli by `exact.draw` over its own
box alone (its `region`), `exact.py` unchanged.

**Color, since engine build A2.** A cone color (`DKL`, `ConeContrast`) is a contrast about its
background in the lab's one observer, the CIE 2006 10° cone fundamentals (`wl_xcon/cones.py`; the
CIE's table bundled unmodified in `wl_xcon/cie/` under CC BY-SA 4.0 and read only when its
checksum is the CIE's, ADR-0012), turned into CIE XYZ through the session's calibration
(`photometry.cone_xyz`): on the default through the CIE's LMS-to-XYZ_F,10 matrix inverted, on a
measured record through its primaries' spectra (ADR-0011), and on one measured without spectra as
on the default, with a warning (XC-352's E3). `check` holds every light to the panel
by full conversion against every lit value of its background, and the exact drawer's last step
turns each pixel into output levels through the calibration's measured, black-subtracted transfer
(`exact.output_levels`), clipping one the panel cannot make, whose light `exact.shown` gives and
`check`'s `unrealizable-color` warning names (the PI, 2026-10-11, XC-352's A20). Each session's `config.json` records
the observer, how its cone colors converted and which luminance their isoluminance held.

**Color sets, since the pop-out search build (2026-11-07).** A `ColorSet` (`wl_xcon/photometry.py`)
is plain data, named CIE 1931 chromaticities with an apex and a luminance, read from a file beside
its task (wl-xtasks' `stimuli/`), and a `ColorSetLight` is one of its colors as an absolute light,
so it runs on the black background, where no cone color does. `photometry.realize` puts the set on
the session's calibration with each color's **macaque luminance**, L + M at L:M 1 on the
Stockman-Sharpe 2° fundamentals (`cones.macaque_luminance`; the CIE's own 2006 2° table, bundled
unmodified and read only when its sha256 is the CIE's, ADR-0012 amended 2026-11-07), equal to a D65
light's at the set's cd/m², 15 on every rig (the PI, 2026-11-07; COL-37) -- or a light's own, a
number or a setting (`ColorSetLight.luminance`; the pop-out's `color_luminance`, 15 to start, which
the trainer may change, TSK-75): through the primaries'
spectra on a measured record, through wl-style's model of the sRGB primaries on the default and on
a record without spectra, with a warning there (`color-set-without-spectra`). A panel that cannot
show the whole set moves every color toward the apex by one shared share, never dimming or
clipping one, and `check` warns by how much (`color-set-desaturated`); one that cannot show even the
apex refuses it -- **but where a setting gives the luminance, the part of its range the panel cannot
show at all is a warning naming the reachable top** (`color-set-unreachable`, `check.reachable_top`;
the PI's warnings over refusals), and only a value above it set live is refused
(`taskd.Session._impossible`, ahead of the listed `Session.set`; `check.unshowable`); **a run
starting above it starts at it**, with a warning a person accepts with the run's others,
`start-at-reachable-top`, naming the setting, the value asked, the value used and why
(`check.in_reach`, one function for the pre-flight, `Session.run` and `wlx run`; the PI,
2026-11-20, from his try-out, "Start at the brightest it can, warn"), the value used recorded as
the run's own start; a run is refused only where no value the setting allows shows the set (XC-494,
which the load refuses first, `unrealizable-color`); over the range, `color-set-desaturated` says which part desaturates, and at a
value set live the share given up there, each a layout warning naming its set (`check.LAYOUT`). The set is realized between trials, once for each luminance a run draws it at on
each calibration (`photometry.realized`), never in a frame. **The record
names a color-set light's set by its name alone** (`record._written`; REC-27, revised 2026-11-07 by
the build's final fixes), and each run's start row defines every set its task declares once
(`color_sets`): as its file reads, and as the run's calibration drew it at each luminance its
starting values give, each color as shown, the share of chroma given up together and each color's
output levels; a luminance a later trial draws it at first is that trial line's `color_realized`
(wl-preproc's name for it, 2026-11-14, XC-491), once a run (`taskd.Session._realize`); a task declaring two different
sets of one name is refused at load (`color-set-named-twice`). **A light has a saturation, since the
console settings build (2026-11-17; its design §6)**: `ColorSetLight.saturation`, a fraction 0 to 1,
a number or a setting, **scales its CAM16-UCS chroma at a fixed hue** (the PI, 2026-11-18; COL-39):
the realized color's (a', b') in the set's design frame (its `gray_lightness`, or the generator's J'
65, `photometry.GRAY_LIGHTNESS`), taken toward the apex's at the same J' by `s`
(`photometry.saturated_xy`), only its chromaticity kept, its macaque luminance, its fraction of the
set's, held (`photometry.colorset_xyz`); `s = 1` is the realized color and `s = 0` the apex,
exactly. A CAM16-UCS hue line is no straight line in xy, so a saturation between may leave the
panel's gamut where both ends are inside: such a light is moved toward the apex in xy by the least
share that shows it, as `realize` moves a set (`photometry.colorset_xy`), and warned
`color-set-desaturated`, naming the light, its saturation and the share (a range read every 0.05,
`check.SATURATION_STEPS`; live, the value set). The checks read each light at its own saturation:
one at 0 is its set's apex whatever its hue, so it adds no `color-set-desaturated`, and two lights
alike but for a hue are alike when both are at 0 (an odd one is then odd no longer,
`impossible-trial`). The record writes each light's `saturation`, each realization's `macaque_row`,
each set's `design` (its file's, or null), and **each look's `light_xy`**, the CIE 1931 `[x, y]` it
is drawn at, on each `stimuli[]` and `objects[]` entry of a trial line (null for an array's own
entry, a look in no set's light, and where it cannot be read; `record._light_xy`), all accepted by
wl-preproc 2026-11-18 (XC-513, closed), so a reader computes every light from the record alone:
`u = (x/y, 1, (1 − x − y)/y)`, `L = fraction × luminance`, `XYZ = u × L / (macaque_row · u)`.
A setting whose choices each show a color-set light is picked by set and hue on its card
(`task.color_choices`; two choices of one set's one hue warn `ambiguous-color-choice` at load). **A new
color is defined from its card three ways** (the console settings build's Task 8; the design's §6;
COL-38; `wl_xcon/colordef.py`): a hue angle in its set's CAM16-UCS design frame (`ColorSet.design`,
the file's optional `design`), CAM16 computed in the standard library's `math` (`wl_xcon/cam16.py`)
under the viewing condition the PI's generator used, colour-science 0.4.7's defaults, which a test
holds to isohue's own colors; a DKL direction about the set's gray in the set's 2° observer on the
sRGB standard; or CIE x, y. `wlx serve` previews it (`GET /color-preview`, writing nothing), and
`wlx taskd` saves it in any phase (`link.DefineColor`, `Service._define_color`, outside every listed
item) as its set's whole file with the color added under `stimuli/proposed/` beside `--tasks`, never
the set's own file, for the PI to review and commit; how the panel in use shows the set with it is a
warning on the changes feed. Cone colors still convert through the lab observer and hold V_F,10.

## Neural plane and stimulation

Both systems record; either may gate the loop; **Intan always stimulates.**

| | Local-activity gating | Distant-area gating |
|---|---|---|
| Source | Intan RHX Spike Output socket | SpikeGLX `fetchLatest`, filtered AP stream |
| Client | `rhxfeatd`, Intan host | `neurofeatd`, acquisition PC, C++, loopback |
| Artifact | Severe (same amplifier); RHS amp-settle plus our blanking | Absent |

RHS stimulation is **hardware-triggered from a digital input** — no software in the trigger
path. Stim parameters are pushed over RHX's TCP command interface at safe points only
(session start, block boundaries, ITI), **read back and confirmed**, and bounded by the
rig/subject config. Delivery is counted against the RHS stim-output line, not against
intent.

Three stimulation tiers: epoch-triggered and gaze-triggered are **v1** (so welfare
interlocks are v1 work); neural-triggered is post-v1.

## Sync conventions (day-one requirements)

Owned by `wl-sync`; our obligations are to feed it correctly. One shared barcode line into
the recorders and the camera GPIOs; two photodiode patches with fixed roles; 16-bit strobed
event words; every TTL we emit also recorded; offline reconstruction scripts with
round-trip tests.

## Data outputs and lab integration

Per session: JSONL trial/event log, parquet behavioral tables, a complete config and
provenance snapshot (resolved parameters, bounded config, gaze-mapping versions, task and
code versions, plot declaration, parameter-change log), and a DONE marker conforming to
`wl-preproc`'s published schema. Raw neural data never touches the task PC.

**The rig cannot push to the ELN.** wl-works binds only to WireGuard and lab machines have
no route in **for the application layer**, and `wl-preproc` enforces "never initiates a
connection" with an AST guardrail. **One narrow exception exists since ADR-0009
(2026-09-20): a lab host has a route to wl-works on UDP 123 only, to synchronize its
wall clock over NTP against `time.wl.works`** — the hostname was the PI's, named
2026-09-20 as `ntp.wl.works` and changed on 2026-11-04 to wl.works' own `time.wl.works` (ADR-0009) — because welfare marks are now clock times and the daily fluid figure
spans deployments that must agree what time it is, and nothing did. **That route does
not exist yet**: naming the server settled which system serves the time and not how a
lab host reaches it, and the ask is open in `docs/pending-wl-works-amendments.md`. Be precise about
what changed: a system time daemon is a different layer from the AST-guarded
application source, so the guardrail above is untouched; what is no longer unqualified
is the routing claim itself, narrowed rather than reversed. NTP serves bookkeeping time
only — which day it is, when a mark was made — never the timing record, which remains
the sync box's hardware ticks and the strobed event words (S3) [@mills2010network;
@karsh2026sync]. Application integration
is otherwise still pull-based and reuses `wl-preproc`'s existing lab-host protocol: live
session state is exposed as **readings on `GET /health`**, and the finished session
summary is **a file in the session directory** that `wl-preproc` ingests, because the
protocol declines result upload. What the rig wants from the ELN at a session's open (the
animal's permanent id, its newest weight and water state, the day's water so far, its open
rig visit and the lab's people list) **is read by the rig's own page, signed in through
wl.works**, from a read-only resource of wl.works' (its stage 10c-1, designed 2026-10-11 and
not built; backlog XC-100): wl.works withdrew the `prepare-session` action it was to push
on 2026-10-11, and sends a rig no action and no data. No welfare-affecting action —
reward, stimulation, session start, parameter change — is ever published through the
protocol, since wl-works' permission model is flat by design. Drafted at
`docs/pending-wl-works-amendments.md`.

Behavioral visualization lives here; **neural visualization stays in `wl-expviz`**.

## Platform

**NI-DAQmx 2026 Q2 supports RHEL 9.6/10.0, openSUSE 15.6/16.0 and Ubuntu 22.04/24.04 LTS —
not Fedora** (read 2026-08-31). `wl-stack` standardizes the lab on Fedora, so the task PC
deviates deliberately: **Ubuntu 24.04 LTS**, recorded as a rig-class decision, dual-booting
Windows to satisfy the MonkeyLogic swap. `PCIe-6343`-on-Linux is **UNVERIFIED** until a card
runs on a bench (P10).

## Open questions

Tracked in the design spec §16. The ones that block others: escape-hatch strictness (S1),
touchscreen configuration, display panel and refresh, photodiode patch placement against
the real optics, and the event-code allocation.
