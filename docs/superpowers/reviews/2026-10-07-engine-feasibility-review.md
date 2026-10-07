# Feasibility review: the engine spec against the code

> **What this is.** A design review of `../specs/2026-10-07-engine-design.md` at `8f9cb03`, written on 2026-10-07 by a reviewer subagent the build session dispatched, kept as written. Its findings are being put to the PI (his decisions) or fixed in the spec (the rest); the notes record which.

Spec: `docs/superpowers/specs/2026-10-07-engine-design.md` (cited §k, with spec line numbers), notes
`2026-10-07-engine-brainstorm-notes.md` (N§k). Worktree `.claude/worktrees/b2b-remote-signin`, branch
`engine-design`, HEAD `8f9cb03`, read 2026-10-07. No repository file edited; the test suite was not
run. One read-only Python probe of `scheduler.py` was run (finding 1 and 2, output quoted there).
`wl-preproc/` is the tree's link (`.superpowers/wl-preproc-main`); which wl-preproc commit it is
was not identified (UNVERIFIED), as the runtime survey also noted.

20 findings, most consequential first.

---

## 1. "Not repeated" means nothing in the scheduler: debt redraws every uncounted outcome

**Spec:** §16.1-16.4 (lines 480-490), with §14.3 (sequence-balanced order).

**Evidence.**
- `scheduler.py:190-191`: every refill draws from `pending = [... if self.owed(c.name) > 0]`;
  `owed` is target minus *completed* (`:217-224`); a block without a criterion is `finished` only
  when every condition owes nothing (`:268-274`). `requeue_on` (`:294-298`) only appends to the
  current queue; it is not what brings a condition back.
- §16.3 says aborts do not count toward a target, so an outcome §16.2 marks "not repeated"
  (`TARGET_BREAK`, `BLINK_BREAK`, ...) leaves the debt standing and the condition is redrawn anyway.
  Probe (two conditions `a`, `c`, target 2 each, `requeue_on=frozenset()`, `a` always
  `TARGET_BREAK`): under `Shuffled`, `WithReplacement` and `Constrained` alike, 50 draws, 48 of
  them `a`, `requeued == []`, block never finished.
- The same probe shows the last owed condition drawn back to back: §16.1's "never the very next
  trial" cannot hold once one condition remains owed.
- §16.4's cap ("stops being repeated; its shortfall recorded") cannot end the block either: the
  capped condition still owes, so it is still drawn and `finished` stays false.
- §16.2 names `CATCH_BREAK` and `MOTION_BREAK` as "not ticked"; N§13 batch 1 records only "target
  breaks and blink breaks were not ticked". The PI was not recorded as shown those two, nor
  `NO_RESPONSE`, `ABORT` or `FALSE_ALARM`, which §16.2 does not classify.
- Tests pin today's rule: `tests/test_scheduler.py:62-72` (requeued to the end of the queue) and
  `:240-260` (whose docstring defends `BLINK_BREAK` in the requeue set, which §16.2 removes).

**Why it fails.** §16 treats "repeat" as independent of "debt"; in `scheduler.py` they are one
mechanism. Built as written, a block containing a condition the animal keeps breaking never ends,
and the cap and the not-repeated list change nothing. "A random later point in its block" is also
undefined for draw-with-replacement orders and criterion or time-limited blocks (no fixed length),
and §14.3's sequence-balanced order says nothing about how an inserted repeat keeps its balance.

**Smallest correction.** State the debt rule: an outcome that is neither counted nor repeated
*forgives* the datum (shortfall recorded) or the block cannot end; the cap forgives the rest of a
condition's debt. Define "later point" per order (and for a single remaining condition), define
repeats under the sequence-balanced order, and mark `CATCH_BREAK`, `MOTION_BREAK`, `NO_RESPONSE`,
`ABORT`, `FALSE_ALARM` as not yet asked (ask the PI, do not infer).

## 2. Catch trials never complete: "responded trials" excludes correct rejections, false alarms and misses

**Spec:** §16.3 (line 488), with §13.3 ("catch trials with no target"), §14.3 ("20% catch
trials"), §15.3 (misses count as staircase failures).

**Evidence.**
- `scheduler.py:35-44`: `Counting.RESPONDED` is the target and distractor families only;
  `CORRECT_REJECT`, `FALSE_ALARM` (`task.py:65-66`) and `NO_RESPONSE` are not in it.
- Probe: one condition `catch`, target 1, default block, five `CORRECT_REJECT` trials:
  `owed 1`, `finished False`.
- `task.py:22-26` (`Family`): "Nothing here defines correct, error or aborted: that is the PI's to
  define ... where `early_response`, `late_response` and `no_response` fall is open (spec §3,
  2026-09-26)." §15.3 and §16.3 both rest on "aborts" without defining it, and `Outcome.ABORT` is
  a specific outcome (`task.py:47-49`), not the family.

**Why it fails.** The spec's own catch-trial and detection designs produce outcomes its counting
rule never counts: a catch condition never completes, so its block never ends; a detection
condition's misses (`NO_RESPONSE`, a failure for the staircase per §15.3) do not pay its target, so
missed conditions are re-run and the design is silently re-weighted toward them.

**Smallest correction.** Put the withholding family and `NO_RESPONSE` explicitly in or out of the
default counting set (a PI decision: ask), and define "abort" as a named set of outcomes.

## 3. "Live edits beat conditions" cannot be built on `spec.values`, which already merges task starts, run values and live edits

**Spec:** §14.7 (lines 456-458), §17.1 (lines 494-496).

**Evidence.**
- `taskd.py:2200`: `values = {**self.spec.values, **condition.values}`.
- `taskd.py:2007`: a service run sets `self.spec.values = {**starts, **given}`, where `starts` is
  every declared `Param.start`; `taskd.py:1780`: `_apply_staged` writes each live edit into the
  same dict. There is no separate live layer.
- §17.1's "deployment → rig → subject → task → session → live edits" names layers that do not
  exist for task parameters (only task starts and run values: `runs.jsonl`'s
  `layers={"task": starts, "run": given}`, `taskd.py:2041`). S8 §3.4 (S8:83-87) names no condition
  layer at all, so "S8 §3.4's layering" for conditions is this spec's extension, not S8's.
- No position is given for drawn values (§14.1) or procedure outputs (§15) in the order.
- wl-preproc groups trials by condition *name* and summarizes per-trial params as that
  condition's settings (`wl-preproc/wl_preproc/nwb/conditions.py` docstring;
  `events/rigtrials.py:1-10`); it reads no override mark.

**Why it fails.** Reversing the merge at line 2200, the obvious reading, makes every task starting
value beat every condition, so no condition would ever change a trial. Without a full order,
a staircase value and a condition value for the same parameter (adaptive tasks) have no defined
winner. The record's override mark (§14.7) has no reader downstream, so overridden trials are
merged into their condition in the NWB.

**Smallest correction.** Keep live edits as their own layer (the names edited live, and their
values) and write the full order: task start < run value < condition < drawn value < procedure <
live edit (or as the PI decides). Add the override mark to §21's wl-preproc asks.

## 4. §20's welfare list misses changes to functions already on architecture.md's welfare-critical list

**Spec:** §20 (lines 534-544) against §5.9, §11.8, §12.3-12.4, §13.1, §13.6, §17.2-17.5, §19.

**Evidence.** `docs/design/architecture.md:76-84` lists `preflight.gate`, `Service._open`,
`Service._start`, `Session.set` (whole), `Session._ends`, `Session._hold`; `preflight.py:12-16`;
`service.py:625-631` and `:911` ("Welfare-critical"); `taskd.py:939` ("Welfare-critical, the whole
method"). The spec changes each:
- **`gate` / `_start`:** §19.3 moves acknowledgement to once per session at open; today it is
  taken per run (`link.StartRun.acknowledged`, `link.py:1358-1371`; `preflight.gate`
  `preflight.py:336-375`; who acknowledged written per run into `runs.jsonl`, `preflight.rows`
  `:378-400`). §19.2 per-session-kind refusals, §5.9 "refused in chaired sessions", §12.3 "no
  first task without a validated map", §12.4 "refused in a recording session" and §13.1 (plan
  chosen at run start) are all new run-start refusals or inputs.
- **`_open`:** §11.8 "a session refuses to open while the panel says maintenance is due".
- **`Session.set`:** §17.2 instant edits; §17.4 presets "applied with one click as one recorded
  change"; §17.5 revert "in one action". The spec does not say whether a preset, a revert or
  §17.3's "its last values" may carry bounded entries such as `reward_correct`; today a reward size
  carries only within one session (`taskd.py:2043`, "Question 1, PI").
- **`_ends` / `_hold`:** §13.6's continuous mode and §6.8's 5-minute trials (finding 6).

**Why it breaks a rule.** CLAUDE.md: welfare-critical code requires human review before merge;
memory: the PI wants a numbered welfare summary. §20 routes four items; at least the ones above
change listed functions and are not routed, so a build plan written from §20 would merge them
without the summary.

**Smallest correction.** Add these items to §20 (this changes no list, only what goes in the
summary), and state whether presets, revert and last values may carry bounded entries.

## 5. "Instant" parameters and per-frame live inputs contradict the PI's 2026-09-19 ruling and a link drained only at trial boundaries

**Spec:** §17.2 (lines 497-498), §4.11 (lines 213-218; mouse and scroll wheel per frame).

**Evidence.**
- `taskd.py:903-906` (`Session.set`): "Validated now, applied at the next trial boundary --
  **every name alike** (PI, 2026-09-19)". S8 §3.2 (S8:66): "Never mid-trial."
- `architecture.md:70` and `taskd.py:14-16`: the link is "drained and published once per trial
  boundary and never per frame"; the one per-frame input is an 8-byte mark signal on a PULL
  socket (`link.py:1417`, `MARK_BYTES`).
- `run.py:438,451-452,519,534`: `values` is resolved every frame, so changing it in place mid-trial
  re-times `After` and `Hold` guards already running.
- `record.py:316-353`: a parameter change is a file open and write; done in-frame it is logging I/O
  in the hot path (CLAUDE.md).
- §22 amends neither S8 §3.2 nor architecture.md's link sentence; build H (§24, line 590) needs only
  "E, C", with no link or console work for the mouse.

**Why it fails.** The spec presents a reversal of a recorded PI ruling as new behavior without
saying it supersedes it, touches a welfare-critical method, and needs a per-frame console-to-rig
channel the architecture rules out.

**Smallest correction.** Say N§14 supersedes the 2026-09-19 "every name alike" for declared-instant,
non-bounded parameters (`Session.set` refuses instant on a bounded name: welfare summary); name
the per-frame input path (an ADR-0003 amendment, finding 20); write the change rows at the next
boundary; add S8 §3.2 and architecture.md to §22 and the link work to build H.

## 6. Continuous mode and 5-minute trials run with no boundary: no limit check, no Stop, no telemetry

**Spec:** §13.6 (lines 429-433), §6.8 (lines 279-280); build K (line 592).

**Evidence.**
- The only places the loop drains commands, publishes and asks `_ends` (the out-of-cage limit
  first) are the top of the per-trial loop (`taskd.py:2120-2145`) and the paused loop `_hold`
  (`taskd.py:1407-1445`); `_ends`' docstring: asked "between trials and on every pass of the
  paused loop" (`taskd.py:1365-1370`). Inside `run_trial` the one per-frame hook is the mark check
  (`run.py:379-385`, `taskd.py:2072-2075`).
- A task's reward reaches welfare only as a trial's action (`run.py:356-357`); `_hold` relies on
  "the task rewards nothing because it cannot" (`taskd.py:1414-1416`).

**Why it fails.** A 20-minute continuous epoch "takes marks and pauses", ends "on an operator
stop" and "can reward (on a schedule, or for gaze)" (§13.6), but no pause or stop command is read,
no frame is published and the out-of-cage limit is not asked until it ends. A 5-minute trial
delays a Stop, a pause and the limit by up to 5 minutes. Neither is in §20; build K lists only
"E, F".

**Smallest correction.** Specify housekeeping passes inside a continuous epoch (and inside long
trials, or state the latency the PI accepts), each draining, publishing and asking `_ends`; route
continuous-mode reward and that cadence to the welfare summary.

## 7. An automatic pause has no path: no outcome is ever `FAULT`, a fault ends the run, and `_pause` needs a person and two codes

**Spec:** §11.3 (lines 381-382), §13.9 (lines 438-440).

**Evidence.**
- `Outcome.FAULT` is declared (`task.py:87`) and mapped (`codes.py:147`, `scheduler.py:82`) but
  produced nowhere in `wl_xcon/`.
- A fault inside a trial is an exception: "One frame naming the fault, then it propagates
  unchanged (PI, 2026-09-19)" (`taskd.py:2329`); `Service._run` contains it and the session goes
  back between runs (`service.py:947-975`), not paused.
- `Session._pause(self, by: Actor, index)` (`taskd.py:1135`) refuses when the allocation lacks
  `PAUSE` or `RESUME` (`:1155-1166`); `Actor = Box | Member` (`actor.py:59`): no framework actor.

**Why it fails.** "The trial ends as a rig fault ... and the session pauses at that boundary" needs
a display-loss path that returns an outcome rather than raising, an actor for a pause nobody
pressed, and a rule for an allocation without the two codes (today the pause would be refused and
the session would run on with no display). §13.9's auto-pause has the same two gaps. What happens
when the display dies between trials or while paused is not said.

**Smallest correction.** Specify display loss as a non-exception path returning `Outcome.FAULT`; add
a system actor kind (actor.py, records, telemetry); refuse a run at pre-flight whose allocation
lacks `PAUSE`/`RESUME` when auto-pause or the display is in use.

## 8. Repeating and step-back block sequences break a forward-only scheduler and taskd's spin guard

**Spec:** §13.5 (lines 426-428), §15.1 (line 464, progressions "may step back"), §13.2 (block types
added or removed mid-run).

**Evidence.**
- `scheduler.py:243` (`done` at the last block), `:254-258` (`advance` raises `IndexError` on the
  last block; pinned by `tests/test_scheduler.py:341`).
- `taskd.py:2148-2190`: advances are counted and `advanced >= len(scheduler.blocks)` raises
  `RuntimeError`; its comment: "a session advances exactly `len(blocks) - 1` times".
- The plan is fixed at run start: `Scheduler(blocks=self._plan(run), ...)` (`taskd.py:2024`).

**Why it fails.** "Repeating (Bt1, Bt2, Bt1, Bt2 ...)" until a time limit or a stop, progression by
criterion, and stepping back all need a next block chosen at each block's end, which a finite
list advanced forward cannot give; the first cycle past the list's length trips the guard with an
animal in the chair.

**Smallest correction.** Specify a block-sequence policy object (fixed, cyclic, seeded balanced,
criterion with advance and fall-back) in place of `list[Block]`, and restate the spin guard as a
per-advance progress check, updating the pinned test.

## 9. Several trial structures per task, and interludes, have no place in the one-`Trial`-per-run model

**Spec:** §13.3 (lines 422-423), §13.4 (lines 424-425); build C+I (line 585).

**Evidence.**
- `cli.py:37-52`: `_load_trial` refuses a module that does not define exactly one `Trial`; its
  callers: `taskd.py:1735`, `:1981`; `preflight.py:71`; `cli.py:1543`, `:1976`, `:1979`.
  `Session._params` (`taskd.py:1728-1736`), which `Session.set` validates against, returns one
  trial's params; `check(trial, ...)`, `review.render` and `simulate.prepare` take one `Trial`.
- `levels.py:112-142`: every trial is counted into the open block (`trial_in_block`, block
  numbers), and S8 §1 says "an interlude creates no block"; `runs.jsonl` and `trial_starts.jsonl`
  name one task per run (`taskd.py:2030-2058`, `record.py:279-288`).
- Backlog XC-207 (`docs/backlog.md:44`) "waits on: wl-xtasks", and §21 asks wl-xtasks for the
  task file format; C+I's "Needs" lists only A.

**Why it fails.** A build plan for C+I hits the loader, the checks, the pre-flight, the review and
the parameter path at once, and has no rule for where an interlude's trials (a recalibration, an RF
map: a different task) sit in the ten position numbers, the stream and the run's task.

**Smallest correction.** Define the task module's top-level object (trial structures, plans,
procedures), how its parameters union for `Session.set`, where interlude trials are numbered and
which task they record; add wl-xtasks to C+I's needs.

## 10. Condition numbers "fixed per task across animals" and per-animal state have no shared home across the two rigs

**Spec:** §14.5 (lines 453-454), §13.2, §13.7 (programs), §15.4 (carried procedure state),
§17.3-17.4 (last values, presets).

**Evidence.**
- `architecture.md:45`: "Two rigs in v1 ... One config file per rig."
- "The animal's folder" is `--subjects/<animal>/` on each `wlx taskd` (`cli.py:1475-1478`,
  `service.py:557`), the folder whose `bounds.py` the service executes (`service.py:557-566`).
- Tasks come from wl-xtasks, pulled before a session (XC-150).

**Why it fails.** "One added at the rig takes the next unused number; numbers are never reused"
needs one registry per task, but none is named: two rigs can give the same number to different
conditions, and a later commit to the task file cannot know numbers a rig assigned. Programs,
presets, last values and procedure state "per animal" diverge between rigs if an animal works on
both (UNVERIFIED whether animals move between rigs), and the spec would have the service write
into the folder holding the bounded config it executes.

**Smallest correction.** Name the registry's home and sole writer (for example: numbers assigned
only in the task file, and rig-added conditions committed back before they get one), and name the
per-animal store and its sync, outside the folder whose `bounds.py` runs, or say why writing
there is safe.

## 11. The automatic codes contradict S2's plan for stimulus codes and mis-state who owns them

**Spec:** §8.3 (lines 320-323), §21 (line 548), §22.

**Evidence.**
- S2 §4 (`S2-event-vocabulary-design.md:116-118`): "our additions are almost all simple codes, not
  escapes -- which matters, because an escape is an amendment against a frozen interface". S2 §5.1
  (`:132`) already plans `STIMULUS_ON` and `STIMULUS_OFF` as task events in wl-xtasks' range.
- `wl-preproc/wl_preproc/contracts/events.py:16-25`: task-event semantics (256-4095) are
  wl-xtasks'; wl-preproc owns framing, escapes and markers; `:51`: "a NEW ESCAPE is an amendment to
  a frozen layer".
- `tasks/allocation.py:25-33`: the reference tasks already strobe their own onsets (`FIX_ON` 4096,
  `TARGET_ON` 4097, `ARRAY_ON` 4103, `CALIBRATION_TARGET_ON` 4105).

**Why it fails.** The spec asks wl-preproc for three escapes "which owns the vocabulary (ADR-0007)",
where ADR-0007's split gives stimulus semantics to wl-xtasks and S2 chose simple codes on purpose;
neither S2 nor the double coding of every onset (the task's code plus the framework's) is
addressed, and §22 does not amend S2.

**Smallest correction.** Either use S2 §5.1's simple codes (allocated by wl-xtasks) with the
stimulus number carried in the 4096+ range or the record, or argue for escapes and amend S2 §4-5 in
§22; say whether the tasks' own onset codes stay.

## 12. "Every change" toggles the task patch and strobes codes on every frame once anything is live-driven

**Spec:** §8.1 (lines 315-317), §8.3, §3.3 (lines 84-90), with §4.11, §5.6, §6.4, §17.2, §4.4.

**Evidence.**
- §3.3: drift and refreshing noise are computed from the frame number and are not changes; but a
  gaze-anchored position (§5.6), a mouse-driven bar (§4.11) or an instant edit (§17.2) changes the
  description every frame.
- `task.py:313-322`: `Onscreen(patch="task")` means "the photodiode says the stimulus reached the
  display"; tasks gate on it.
- Each escape is the escape word, its payload and a checksum (`encode.py:84-110`), emitted word by
  word, synchronously, on the loop thread (`dio.py:54`, `taskd.py` `self.card.emit`); §4.4 allows
  "thousands of elements", each its own stimulus.
- CLAUDE.md hot path: no allocation, no logging I/O, no unbounded work per frame; §3.3 builds a
  fully resolved description per change and §8.5 records live values per frame.

**Why it fails.** With one live stimulus the task patch toggles every frame (a second flip patch),
`Onscreen` fires on whichever change lands first rather than the stimulus a state waits for, and
"stimulus changed" goes out every frame; an array onset of N items is N escapes in one frame. The
per-frame description rebuild and per-frame value logging are allocation and I/O in the hot path
unless the spec says otherwise.

**Smallest correction.** Define which changes toggle the patch and earn codes (onsets, offsets,
declared discrete updates; not live-driven or modulated values, which go to the screen log), make
arrays and groups one code, and require in-place, preallocated description and value buffers
written out at the boundary.

## 13. The rig's calibration, monocular grids included, is invisible to wl-preproc's calibration reader, and §21 asks nothing

**Spec:** §12.3-12.4 (lines 402-409), §13.4 (recalibration interlude "not a new block"), §21.

**Evidence.**
- `wl-preproc/wl_preproc/schema/eye.py:497-551`: a calibration window runs from
  `FIXATION_ACQUIRED` (256) to `FIXATION_END` (257), paired with the latest `TARGET_POSITION`
  (`:509`), and counts as calibration only inside a block whose `BLOCK_START` task type is
  `TaskTypeCode.CALIBRATION` (7) (`:542`) or a `TaskEvent.CALIBRATION_START/END` (258/259) epoch;
  the windows are "identical for both eyes" (`:559-560`). `TARGET_POSITION` is (role, x, y), no eye
  (`contracts/events.py:169`).
- The rig strobes `BLOCK_START` with task code 0 (`taskd.py:2220`, `encode.py:43`), frames no
  `TARGET_POSITION` (`encode.py` has no framing for it), and strobes `FIX_ON` 4096 and
  `CALIBRATION_START/END` as 4107/4108 (`tasks/allocation.py:25-38`).

**Why it fails.** The session-start calibration the spec makes the rig's rule produces nothing
wl-preproc can fit; a monocular grid would be fitted against both eyes, though one eye saw nothing;
and an interlude that "is not a new block" cannot use the block mechanism.

**Smallest correction.** Add a wl-preproc ask for monocular calibration (a per-eye target or epoch
marker; near XC-029), and specify how the session-start block (task code 7) and interlude
recalibrations (258/259, via wl-xtasks) are marked and which target escapes they send.

## 14. The every-session eye-tracker calibration waits on the spectroradiometer

**Spec:** §24 build J (line 591), §12.3 (lines 402-405), §12.1.

**Evidence.** J: "Calibration procedures (§12). Needs: E; the instrument", and N's build order puts
J after D, F, G and H. §12.3: "required at every session start ... no first task without a
validated map". §12.1: buying the instrument "stays the PI's". `preflight.py:327` keeps the eye
tracker an acknowledgeable unknown today; `docs/CHECKPOINT.md:60`: the lab opens January 2027.

**Why it fails.** The rule every animal session depends on is bundled with color calibration, so
either January's first sessions run without it or they wait for an instrument purchase and four
other builds.

**Smallest correction.** Move §12.3-12.5 (tracker calibration, stereoscope grids, pre-session
timing check) to a build that needs only E and the tracker, scheduled before the first animal
session; keep §12.1-12.2 in J.

## 15. Audio through "the NI card's analog outputs, on the recording's clock" names a card the rig service does not own

**Spec:** §9.1 (lines 336-339), §21 (wl-sync), §22.

**Evidence.**
- `architecture.md:28-30`: the task PC has the NI PCIe-6343; the recording card is the PXIe-6353
  (nidq) on the Windows acquisition PC, under SpikeGLX. N§6 batch 1: "waveforms played by the
  recording card, sample-accurate on the recording's own clock".
- S6 §1 (`S6-io-subsystem-design.md:15-28`): the 6343's allocation is 19 DO, 4 DI, 9 AI, no analog
  output. Whether it has analog outputs is not recorded anywhere in the repo (UNVERIFIED).
- S4 §8 (`S4:151-166`) plans audio measured through a misc-BNC tap (V7, XC-074, XC-089); §22
  amends neither S4 §8 nor S6 §1.

**Why it fails.** `wlx taskd` runs on the task PC and cannot play through the acquisition PC's card;
the 6343's outputs, if it has any, are not on the recording's clock. "Sample-accurate on the
recording's clock" is an unverified hardware claim stated as fact, and the trigger "from the frame
the visual change lands on" has only the task-patch comparator to go on, which toggles on every
change (§8.1).

**Smallest correction.** Name the card and PC, how its clock relates to the recording (or keep
V7's tap as the measurement), mark the analog outputs UNVERIFIED, and add S4 §8 and S6 §1 to §22.

## 16. The session's refresh rate has no source, and the 5-minute cap collides with `max_frames` and "hang"

**Spec:** §6.1, §6.2, §6.4, §4.6 (refusals "at load" at the session's rate), §6.8 (lines 279-280).

**Evidence.**
- `service.py:99`: `FRAME_PERIOD = 1 / 240`, "the frame period every session here runs at";
  `cli.py:1659`: `frame_period=1 / 240`. `check()` takes no rate (`check.py:42-48`); §18.1's report is
  generated per task file, with no session.
- `run.py:364`: `max_frames: int = 100_000`, not passed by `taskd.py:2238-2245`: 416.7 s at 240 Hz,
  833 s at 120 Hz (arithmetic), neither 5 minutes.
- A trial reaching it returns no outcome and is recorded `"hang"` (`taskd.py:2267`), read by
  `resume.py:170`, `health.py:84-85`, `web.py:138`, pinned by `tests/test_taskd.py:4818-4851`. §6.8
  says it "ends as a fault".

**Why it fails.** Every rounding, exact-duration, flicker and movie-rate refusal needs a rate that
today is a constant, and load-time checks cannot see a session at all. The cap needs both the rate
and a decision between the spec's "fault" and the existing "hang" category.

**Smallest correction.** Name the rate's source (the display's reported mode, checked against the
rig file), carry it in `SessionSpec` and `check()`, check task files at each supported rate (or the
declared required one), derive `max_frames` from 300 s, and choose `FAULT` or `"hang"` with the
readers and the pinned test.

## 17. The session kind has no home, and a warning's meaning mid-run is contradictory

**Spec:** §19 (lines 520-532), §8.7 (lines 331-332); build B.

**Evidence.**
- `link.OpenSession` (`link.py:1324-1343`) carries no kind; nor do `SessionSpec` (built in
  `service.py:533-605`), `config.json` (`taskd.py:681-706`), telemetry (`link.py:146`, schema 14) or
  `resume.Restoration` (`resume.py:43-63`), so a resumed session would lose its kind.
- Blocking check findings refuse a run whatever the session is for: `Session.run`
  (`taskd.py:1982-1988`) and `preflight.task` (`preflight.py:96-102`); `uncalibrated-color` is
  blocking (`check.py:791-812`). A warning "acceptable in training" that is today a check finding
  needs a severity check findings do not have.
- §8.7: a frame-clock fault "goes on". §19.2 lists frame-clock faults with "outside [its kinds] it
  is a refusal", and §19.3 says "a warning appearing later asks again"; neither says what happens to
  a run in progress.

**Why it fails.** Build B (warnings and session kinds) has no named fields, no resume rule and no
severity model to build on, and two sections disagree about a mid-run warning in a recording session.

**Smallest correction.** Name the fields (OpenSession, SessionSpec, config.json, Restoration,
schema bump), give check findings a "warning, accepted in kinds K" severity, and say what a mid-run
warning does (record and continue, or pause).

## 18. "Nothing implied" for contrast and a task-declared background contradict the vocabulary and the calibration model build A starts from

**Spec:** §4.12 (lines 222-224), §7.5 (lines 300-301), §4.4 (background per trial and per eye).

**Evidence.**
- `task.py:465-738`: every appearance declares `contrast: "float | P" = 1.0` (twelve classes), and
  no reference task sets a stimulus's contrast (`grep contrast tasks/`), so every reference task
  relies on the implied value §4.12 forbids.
- `photometry.py:66-86`: the background is a *measured* field of `Calibration`, and
  `max_cone_contrast` "is a property of the primaries and the background ... measured"; `task.py`
  has no background field.

**Why it fails.** As written, build A, the first build, either refuses every reference task (and the
tests that load them: CLAUDE.md "nothing merges with a red test suite") or keeps an implied default.
Moving the background into the task invalidates the measured cone-contrast limit for any other
background, which the spec does not address.

**Smallest correction.** Say whether bare contrast keeps a named default convention or the reference
tasks and tests migrate in A; reconcile §7.5 with `Calibration.background` and say how the cone
contrast limit is obtained for a task's background.

## 19. A citation that its source does not support, and an external fact left unattributed

**Spec:** §3.1 (lines 66-67), §10.5 (lines 361-364).

**Evidence.**
- §3.1: "vstimd's notes describe NVIDIA device-lost failures;
  `docs/research/2026-10-07-vstimd-prior-art.md`". That document says nothing of device loss or
  crashes (grep "device", "lost", "crash"; its only driver issue is "an nvidia-modeset VRR bug on
  JetPack 6.x", line 48). The phrase appears nowhere else in `docs/`.
- §10.5: present timing "reported supported by NVIDIA's Linux driver"; N§7 batch 1 attributes it
  to Phoronix (web, 2026-10-07); the spec drops the source and date.

**Why it breaks a rule.** CLAUDE.md "No fabrication": cite the primary source with an as-of date or
mark UNVERIFIED.

**Smallest correction.** Drop the vstimd attribution (N§7 batch 3's own reasons carry the separate
process); cite Phoronix with its date and mark NVIDIA support UNVERIFIED.

## 20. New transports are decided without an ADR

**Spec:** §3.1 and §10.4 (shared memory to the display process), §4.8 (the GPU server), §4.11 (a
per-frame console input), §9.4 (lab storage); §22 (lines 555-568).

**Evidence.** CLAUDE.md: "Engine, transport, file-format, and license decisions go through
`docs/design/decisions/`." ADR-0003 (`ADR-0003-messaging-and-transport.md`) covers the eye UDP
protocol and ZMQ with msgpack, extended once for HTTP; architecture.md:70 records even the mark
signal as "ADR-0003's transport, untouched: a third socket". §22 amends only ADR-0002 and ADR-0004;
§25 defers the formats to builds E and H, which is fine for formats but not for the transport
choice.

**Why it breaks a rule.** Shared memory, a rig-to-generator protocol and a per-frame input channel
are transport decisions the rule routes through an ADR.

**Smallest correction.** Add an ADR-0003 amendment (or a new ADR) to §22 covering these transports.
