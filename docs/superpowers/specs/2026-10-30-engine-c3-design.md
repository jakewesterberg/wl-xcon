# Engine build C3: varying conditions and the live-edit layer

- **Status:** approved by the PI, 2026-10-30, section by section: "Approve group 1" (§1-4), "Approve group 2"
  (§5-7), "Approve group 3" (§8), "Approve; write the spec" (§9-12); the welfare items of §14, "Approve all four"
  (for the design; the final code returns to him with the plan). His answers to the draft's three open points are
  folded into §2, §6 and §7: "Follow same/fresh (Recommended)", "No, after any change (Recommended)", "Not in C3
  (Recommended)"
- **Date:** 2026-10-30
- **Backlog:** XC-343, XC-344, XC-361, XC-362, XC-363, XC-383, XC-418; the engine build the PI's split of
  2026-10-11 names "C3 varying conditions and the live-edit layer with XC-288's change log"
- **Reviews:** none yet
- **Starting point:** the brainstorm's record, kept as git-ignored scratch in the main checkout's
  `.superpowers/c3-prep/`: `scope.md` (the requirements from committed sources, and in its §4 the controller's
  engineering calls, cited here as "call N"), `code-map.md`, `brainstorm-agenda.md` (the questions, their options and
  sources), `answers.md` (the PI's answers, quoted and dated) and `design-draft.md` (the draft he approved). Every
  answer that binds is quoted here, so this spec stands without them
- **Builds:** C3; the operator's edits at the rig are a build of their own right after it (§1)

His answers are cited by question: Q0 to Q10, all 2026-10-30. **Engineering** marks the controller's own calls,
which he may overturn; every other choice is his, cited. Papers are cited by key from
[`library.bib`](../../references/library.bib).

---

## 1. What C3 builds, and what it leaves to the next builds

**C3 builds:**
- Values drawn at random each trial: where a task writes them, their seeds, what a repeat does with them (§2, §3).
- Conditions made from factors (§4).
- Designed orders, sequence-balanced and priming, with their repeat rule (§5; XC-361).
- The live-edit layer: a person's value over conditions and draws, the hand-back, a drawn range changed live, and
  the console showing where each value comes from (§6).
- Eased trials kept out of moving up (§7).
- The change log and revert, with clears, drumming and training switches moved into the log (§8; XC-363).
- The refusal of settings no animal can get right (§9; XC-343).
- The record of what varied (§10; XC-344), told to wl-preproc first (XC-383).
- A fresh seed for `wlx run` when given none.

**Left to later builds:**
- **Rig edits, a build of their own right after C3** (Q0: "A build right after C3"): adding and removing conditions
  and block types at the rig, and plans made there. Their questions (Q9a, Q9b) go to that build's brainstorm. Two
  committed sources disagree with this and with each other (the C2b plan's decision 38 puts rig edits in C3; the
  PI's split of 2026-10-11 puts them in C6); the answer is followed (§13).
- **C4**: reasons for changes and sign-in for them (TRN-04, TRN-07); ids on control rows.
- **C5**: presets, start and carried values on per-animal storage; the condition registry and its numbers; the log's
  "a preset applied" and "a task revised" rows; XC-405.
- **C6**: interludes and session programs. **C7**: stages across sessions.
- **C8**: the hazard plot, the census per condition and per factorial cell, the simulator playing plans and draws.
- **D**: procedures, and random picks with their odds. **H**: instant parameters.
- **No build yet**: durations converted to frames at load ([engine spec](2026-10-07-engine-design.md) §6.2); the
  once-a-second checks inside a trial (XC-373).

---

## 2. Drawn values in a task

**Distributions** (TSK-24, the PI, 2026-10-07): a uniform range; a weighted set; a normal cut to the setting's
declared range unless it declares its own; a prepared list, played in shuffled passes unless it says "in order"
(engineering, call 19); the non-aging wait (§3). No published source covers the first four. *Engineering:* frozen
classes in `task.py` (`Uniform`, `Weighted`, `TruncatedNormal`, `Listed`, `NonAging`); a task using none keeps its
content hash. A position may be drawn by eccentricity and direction.

**Where (Q1a: "Task default, block may replace"):** one default for the task (`Task.draws`), the plain run included;
a block type may replace it, narrower or wider (`Block.draws`).

**A condition's own range (Q1b: "Yes"):** a condition may draw a setting from its own range; the trial counts toward
it and records the value it got. This revises the approved "set by a condition or drawn, never both (refused at
load)" (engine spec §14.1; TSK-21; §13). "Never both" now reads block by block: a setting is drawn by the block (its
own draw, or the task's it does not replace) or given by its conditions (each a value or its own range), not both.
*Engineering:* a block whose conditions give a setting the task draws must say so in its draws, or it is refused at
load, naming the setting (an authoring rule).

**Seeds and replay** (engine spec §14.6; TSK-06): each draw comes from a generator keyed by run seed, trial and
setting [@salmon2011parallel], apart from the scheduler's, so adding a draw moves no condition or repeat
(engineering, call 5); a run replays from its seed and change log. Draws are taken between trials, never in a frame.
*Engineering, call 23:* `wlx run` draws a fresh seed when given none (today it uses 1).

**On a repeat (Q3: "Per drawn setting, required"):** each drawn setting must declare `same` or `fresh`; a task that
does not is refused at load. This replaces "per task" (engine spec §16.5; TSK-31; §13). **A drummed repeat follows
each setting's `same` or `fresh` too** (the PI, 2026-10-30, "Follow same/fresh"; the option read: the target stays
where it was and the wait is new, so the drum teaches the problem, not the timing). This revises XC-362's "a drum's
repeat keeping its values", which was never his decision (§13).

---

## 3. The non-aging wait

`NonAging(minimum, mean, maximum)`: the minimum plus a wait whose chance of ending is the same at every moment. It is
the PI's tasks' foreperiod, 750-1250 ms "to reduce expectancy" [@westerberg2020priming; @westerberg2023feedforward].
Such a wait keeps the target's chance constant [@han2022revisiting], and LIP and V4 track that chance over time
[@janssen2005representation; @ghose2002attentional].

**The tail: draw again (Q2: "Draw again").** A wait drawn past the maximum is drawn again, so every wait falls between
the shortest and the longest. TSK-15 and engine spec §6.11 have each task declare a tail rule; there is now one rule,
which the record and report state (§13). No paper in the library compares tail rules; how the PI's 2020 tasks
handled the tail is not recorded (UNVERIFIED).

**The report shows the rise.** Drawing again makes the target's chance climb near the longest wait. The review
report's plan tables give, from the declared numbers, the hazard across the range against the flat rate, and the
declared and realized averages. *Engineering, call 20:* "mean" is the constant-hazard wait's own, before redrawing,
so the realized average is lower. An example (arithmetic; a mean of 1000 ms assumed), 750-1250 ms:

| At | Chance per moment, against the flat rate |
|---|---|
| 750 ms | 1.2 times |
| 1000 ms | 1.6 times |
| 1150 ms | 3 times |
| 1225 ms | 10 times |

Its waits average 922 ms. The plot is C8's timing diagram (engine spec §18.1).

**Plainly:** these describe the declared distribution, not the rig. A rig's wait ends on a frame; durations are not
yet converted to frames at load (engine spec §6.2), and the realized interval before the stimulus is not yet
recorded (§6.12). No timing claim is made.

---

## 4. Conditions from factors

A block may declare `Factorial(factors, exclude, target)`: factors and their levels. The rig makes every combination
except the declared exclusions, each named from its levels (TSK-22, the PI, 2026-10-07). Hand-listed conditions
remain, beside a factorial in the same block.

- **Equal cells (Q4: "Yes, each cell equal"):** each remaining combination owes the same number of trials; a
  hand-written number per combination is allowed. After exclusions, levels no longer appear equally often overall,
  so the review report shows each level's share rather than hiding it.
- **Names** (engineering, call 13) come from the levels in the factors' declared order:
  `"target_contrast=0.1, side=left"`. Each trial line records it as its `condition`; wl-preproc groups by it; C5's
  registry will number it. A level may be a number, a choice, a position or (Q1b) a range of its own.
- **Expanded at load** into ordinary conditions (engineering), so a generated condition gets everything a
  hand-listed one does: counting, repeats, overrides, the checks.
- **Listed for review:** nobody writes generated conditions, so nobody reads them unless shown (pitfall P20). The
  review report's plan tables list each one with its values and target, the exclusions applied, and each level's
  overall share; each run's start row lists them too, so the record needs no task file.
- **Refused at load** (authoring rules, or breaks a run): an exclusion naming a factor or level that does not exist;
  two conditions in one block with one name; exclusions that leave nothing.

TSK-22 records that no source was opened for factorial designs, which are standard practice.

---

## 5. Designed orders

**Sequence-balanced** (TSK-23, the PI, 2026-10-07: "each condition follows each other equally often, e.g. de
Bruijn"). The block plays a de Bruijn cycle of its conditions [@aguirre2011de], picked from the run's seed as a
random Euler circuit through them [@brooks2012counterbalancing]. **Depth (Q5a: "Block picks; pairs default").**
Pairs: each condition follows each, itself included, once per cycle, n² trials (4 conditions: 16); triples, n³ (64).
*Engineering:* `SequenceBalanced(depth=2, cycles=1)` (`task.Balanced` is a block order's name); the block ends when
its cycles are played out, owing nothing more (call 14). A trial count or time limit can cut a cycle short; the
record says so. *Amended 2026-10-31 (the PI, on the engine C3 plan's Appendix B, item 1: "Add one closing trial
(Recommended)"):* each cycle is played as the linear de Bruijn sequence, n^depth + depth − 1 trials (4 conditions:
17 at pairs, 66 at triples), so every pair (or triple) is shown once per cycle; its first depth − 1 trials are a
lead-in that only precedes what follows, each such trial's line marking it (`planned`'s `lead_in`) so an analysis
can drop it.

**On a break (Q5b: "'Again at once' as an option"):** no repeat by default (TSK-31). The sequence goes on; the lost
transition is recorded as a shortfall `because` `"designed"` (engineering). A block may choose **"again at once"**:
the broken trial comes straight back, so every planned transition still happens, its drawn values following Q3. Its
cost is the one the PI turned down for ordinary blocks (TSK-30): breaking brings the display straight back
[@nimhmonkeylogic2026task].

**Priming (Q6: "Both of the last two"):** within one block, on a setting it names (its `feature`, e.g. the target's
color), either a set chance that the next trial repeats the last one's value, interleaved, or runs of one value with
drawn lengths (e.g. 3 to 7), then a switch. *Engineering:* a switch picks another value at random; within a value,
conditions are shuffled; "last" is the last trial whose stimulus appeared; the block ends on its trial count or time.
Block swaps (his 2020 design) stay plan block types (C2b) [@westerberg2020priming; @bichot2002priming]. No paper in
the library describes building such sequences.

**The record** keeps C2a's realized sequence (`previous`, `shown`, `repeat_of`, `at_once`), and adds each trial's
`planned` place (position and cycle, or planned repeat or switch and its run) and each block's planned sequence, so
lost transitions count against the plan.

---

## 6. Live edits

**A person's value over conditions and draws** (TSK-19, the PI, 2026-10-07; built for conditions in C2b): it wins
from the next trial, and the trial counts toward its condition, marked `overridden`. C3 extends it to draws: a
person's value replaces a draw (the task's, a block's, or a condition's own range). The trial is then not `drawn`
for that setting, and is `overridden` where the draw was a condition's.

**The hand-back (Q7a: "Yes, a 'hand back' button"):** a *hand back* button on each setting a person holds. From the
next trial the conditions' values (or the draw) apply again, trials are no longer marked, and it is recorded as a
change. This revises "setting it back does not hand control back" (C2b Appendix B item 1, confirmed 2026-10-19;
engine spec §14.7's note; TSK-19; §13). Typing the old value back still does not hand control back; the button does.
*Engineering:* where only the run gives the setting, the hand-back restores the run's own value.

**A drawn range, live (Q7b: "Yes, range changes live"):** a person may change the numbers of a task's or a block's
draw (a uniform's ends; a wait's shortest, average and longest) from the next trial, recorded as a change. Trials
stay drawn, not overridden, and each records the range it was drawn from. *Engineering:* the kind of distribution
cannot change live (that is a task edit); numbers outside the declared range are re-checked widened, as a value is
(TSK-51); a range travels by its own command, never as a `SetParameter`, its numbers decoded by `link._setting`
unchanged. **A condition's own range is not editable live in C3** (the PI, 2026-10-30, "Not in C3"): a person may set
one value over it (trials marked `overridden`) or hand it back; editing the range is a condition edit, which belongs
to the rig-edit build.

**The console** (engine spec §14.7; S8 §3.4): each setting's card says where its value comes from (task, run,
conditions, a draw and its range, or a person) and which conditions set or draw it. A staged change names the
conditions it will override **before** it applies; today only the applied line on the feed does. Telemetry schema 19
(18 since XC-401); narrows XC-418; retires `taskd._overriding`'s stand-in.

---

## 7. Eased trials and a block's rule

**The PI's answer (Q8, given with the C2b merge: "Merge; fix eased trials in C3"):** a trial a person's change made
easier does not count toward **moving up** (a training stage's pass rule, or the criterion that ends a block) and
does count toward **moving back** (a plan's fall-back rule). An animal is never moved up on eased trials; one failing
even when eased still moves back. It carries his training-record stage rule (Q13, 2026-10-10, TRN-06: "no live
change had eased one") into stages within a run, so the two agree. C2b as built counts every answer.

Such a trial still counts toward its condition's target (TSK-19), and its line names the settings that kept it out
of moving up (`eased`).

**What keeps a trial out of moving up**, read from each setting's declared meaning (TRN-03): clear-cut, expected, or
not a difficulty setting; which way raising it goes; relative to what (a number, another setting, the background). A
live change (a person's value or a live range) keeps a trial out when:
- it gave a **clear-cut** setting a value easier than the trial would otherwise have had (engineering, from XC-288
  §4.1): the condition's or the run's value, or, for a drawn setting, the value the seed draws for that trial from
  the range as written (the keyed generator makes it computable; on a repeat, a `same` setting's is the value of
  the trial it repeats, a `fresh` one's drawn on the repeat's own number). A criterion setting counts as a stimulus setting
  does: a larger window eases;
- it held an **expected** setting at any value but the one the trial would otherwise have had, either way (the PI,
  2026-10-30, "No, after any change": trials after any change to an expected setting do not count toward moving up),
  matching his stage rule (Q13: "each expected setting at that value"; TRN-06). An expected direction is not a fact
  (TRN-03), so no guess at one decides a move up.

A setting declared not a difficulty setting never keeps a trial out. A hand-back ends it from the next trial.

*Engineering:* `Scheduler.record` learns whether a trial was kept out; such a trial skips the rule's window
(`_window`) and still feeds the fall-back's (`_back`).

*Amended 2026-10-31 (the PI, on the engine C3 plan's Appendix B):* **a range changed live is judged as a whole**
(item 18, "Judge the range as a whole (Recommended)"): against the written range, if it reaches any value easier than
that allows (for a uniform, either end moved the easier way; anything that cannot be read, or mixed, counts as
easier), none of its trials count toward moving up until it is put back, by typing the written numbers again or by
revert, and its change row says which way it went; a trial is no longer compared, trial by trial, with what the
written range would have drawn. **A sequence-balanced stage below a training progression's top** moves up when its
sequence is played out, eased trials or not, and the load warns of it (item 10, "Only warn at load").

---

## 8. The change log and revert

**The log** ([XC-288 §3.4](2026-10-10-xc288-training-records-design.md#34-one-change-log), approved 2026-10-10; told
to the PI 2026-10-30): `parameter_changes.jsonl` grows into one log of every change to what the animal experiences.
C3's kinds: `set` (a person's value), `hand_back`, `range`, `revert`, and the clear, drumming and training switches
C2a writes as control rows (XC-363). Each row: a `change` id (one per revert), `kind`, the instant applied, the first
`trial_number`, the run, the setting from and to, its declared meaning with direction and step, who, `offered`
(empty), `odds` (null until D), `event_code`; and `sequence` only where `PARAM_CHANGED` is strobed (*engineering:* a
person's value, revert rows, hand-backs and range changes; clears and switches strobe nothing). Not filled in C3:
presets and "task revised" (C5), interludes (C6), condition edits (the rig-edit build), reasons (C4).

**Resume:** `resume._read`, which welfare-listed `stranded.find` reads through, fails closed on a row without
`sequence`; it learns every kind in the commit writing the first such row. A revert never names a reward size, so
what resume restores of reward sizes and the out-of-cage limit is unchanged.

**Revert** ("Yes, with revert", the PI, 2026-10-07; TSK-43): any earlier moment the log names, restored in one
recorded action: each task setting to its value then, held or handed back as it was then, and each drawn range as it
was. Never a bounded setting (engine spec §17.6). Each value goes through `Session.set`, and the revert is refused
whole if any value is. Counts and training aids are not reverted (engineering); presets are C5's.

**Welfare:** revert goes on the welfare summary (engine spec §20 item 3). **`Session.set` stays byte-identical**:
change ids are assigned where changes apply (`_apply_staged`, call 9), and the live layer stays merged in the run's
values, its names kept apart and recorded (call 8); §17.1's "not merged" is met in the record. **The one
welfare-listed function whose text changes is `Session._command`**: three branches beside the pause (hand back,
range, revert) to functions off the list, and one line ahead of `set` for §9's live refusal; its listed `held`
pass-through and `except` line unchanged. `link._setting`, `Service._start` and `stranded.py` stay unchanged. The
items the PI approved are §14.

---

## 9. Settings no animal can get right

**The PI's answer (Q10: "Refuse in file and live"):** refused in the task file and when set live, judged per
concrete combination (per condition, per live change). Under TSK-51 this "breaks a run": no answer can be paid, and
with drumming on such a trial comes back forever, holding the time limits open ("Finish the drum first", TSK-59)
until a person or the out-of-cage limit ends it. XC-343 asked for a refusal; the answer agrees.

**Concrete values, not ranges** (engineering, call 17): the reference tasks' declared ranges already allow these
combinations (`target_hold` up to 1 s, `response_deadline` from 0.1 s), so a range check would refuse every such
task. `hold-cut-short` keeps warning over ranges, as now.

**Judged together:** at load, each condition of each block with the task's and block's values and every draw's full
range (a draw that can produce an impossible trial is refused, since some trials would take that value; engineering,
reading his answer). Live, each change as offered (a value, range, hand-back or revert) against every condition of
the run's blocks and the draws in force, refused at once, naming the conditions it would make impossible.

**The three** (XC-343):
1. **No way to answer in time:** a hold always beaten by a timeout on its state that ends the trial (`target_hold` at
   least `response_deadline`). The hold starts only when the gaze arrives, so it never finishes. Ties go by the
   order the state lists its exits, as `hold-cut-short` reads them.
2. **A target that looks like its distractors:** an array whose target and distractor appearances resolve to the
   same value. Equality only, not similarity.
3. **Two objects whose looks swap:** set size 2, in a block where some trial's target appearance is another trial's
   distractor appearance. Two objects have no odd one out, so one display can call for either answer.

Each refusal names the values, the condition and the fix.

*Amended 2026-10-31 (the PI, on the engine C3 plan's Appendix B, item 17: "Refuse only odd-one-out tasks
(Recommended)"):* items 2 and 3 are refused only where the task says its target is found by its look, the default
(`Array.found_by`, `"look"`). Where it says something else names the target (`"cue"`: a cue, a remembered sample, a
place), each becomes a load warning, `cued-target` ("the target must be named by a cue; check that one is shown"),
the same at a run's start, and live a change they would refuse on an odd-one-out array is accepted on a cued one.
Item 1 is refused whatever names the target.

---

## 10. The record and wl-preproc

**Each trial line gains** (engineering shapes, call 7):
- `drawn`: each setting drawn and where its range came from: `task`, `block`, `condition`, or the `change` id of a
  live range (Q7b). Values stay in `params`.
- `live`: the settings a person set; `overridden` stays those of them a condition gave.
- `eased`: the settings that kept it out of moving up (§7); `planned`, in a designed block (§5).

**Each start row gains** the task's draws as declared (in the hash's form; `plan_form` already carries blocks'
draws, conditions' ranges and factorials) and each block's generated conditions. **Each `block_ends` entry gains**
`varied` (XC-344): each setting that varied in the block and how (condition, draw with its distribution, or a
person), and a designed block's planned sequence. Shortfalls gain `because` `"designed"`. The change log: §8.
XC-344's premise ("uncertainty about where a target appears raises thresholds") has no library paper and is not
cited until one is (told to the PI 2026-10-30).

**Directions** (the PI, 2026-10-30: "0 to 360 in both repos", "Empty at center"): any direction C3 writes (a drawn
position, a change's from and to, a range of directions) runs 0° to 360°, null at eccentricity 0, as wl-preproc
writes them.

**The ask (XC-383)**: a new "OPEN — engine build C3" section of
[`pending-wl-preproc-amendments.md`](../../pending-wl-preproc-amendments.md), in its shape (what changes on our side;
the ask; what is deliberately not asked for), checked first against wl-preproc's current source, written before the
build and sent before C3 merges.
- **Why:** its reader keeps six trial fields (`rigtrials.py`) and summarizes every varying setting per condition
  (`nwb/conditions.py`), so drawn, condition-set and overridden settings read alike; `drawn`, `live` and
  `overridden` tell design, nuisance and override apart. It accepted `overridden` but has not built it (XC-404).
- **Also:** clears and the two switches move from `controls.jsonl` to the change log, amending C2a's ask (XC-365);
  whether to write both for a while depends on whether its source reads them.
- **Not asked:** no new escape or code; the six required fields unchanged; no condition numbers (C5).

---

## 11. Checks, warnings and refusals

The PI's rule (TSK-51, 2026-10-11): refuse only for welfare, safety, an authoring rule, an unreadable record, or what
breaks a run; otherwise warn, saying why.

| Refused | Why |
|---|---|
| A draw, a live range or a condition's value naming a bounded setting (a reward size); a condition's is refused at load as built, since delivery reads the session's bounds and the trial line would record a dose no trial was given | Welfare |
| A drawn setting declaring neither same nor fresh (Q3) | Authoring rule |
| A block that draws a setting its conditions give, without saying so (Q1b) | Authoring rule |
| A distribution that cannot be drawn: lowest above highest, a non-finite number, an empty list, all-zero weights, a spread of zero or less, a non-aging average outside its shortest and longest | Breaks a run |
| A draw its setting cannot hold (numbers for a setting of choices; a list item the record cannot write) | Unreadable record |
| A factorial exclusion naming nothing real; duplicate condition names; nothing left | Authoring; breaks a run |
| A designed block's written target contradicting its sequence; a priming feature with fewer than two values | Authoring; breaks a run |
| A draw reaching past its declared range into a finding that breaks the run (`BREAKS_A_RUN`, as a live value now) | Breaks a run |
| §9's three combinations, at load and live (Q10) | Breaks a run |

**Warned:** a draw reaching outside its setting's declared range (`outside-range`; for a wait,
`longer-than-declared`, saying stop, pause and the out-of-cage limit go unheard until that trial ends, XC-373); a
designed block whose trial count or time limit can end it mid-cycle, unbalanced; `hold-cut-short` over ranges, as
now.

**Where:** at load, `check._plan_faults` and the new checks. At a run's start, `preflight.beyond` and
`preflight.values`, where a drawn setting counts as given, so no run is refused for a number "nothing gives" (call
24). Live, `Session._beyond_range` (off the list) learns conditions and draws, and §9's check runs ahead of `set`
(§8).

---

## 12. Testing

**Simulator first** (CLAUDE.md): each behavior ships with a simulator-backed test; each new check is shown able to
fail (`tools/mutate.py --all`, its output read, not its exit code). **The path, not the piece** (pitfall P21): a
`wlx taskd` session driven through the console's commands (a draw, a hand-back, a range change, a revert, a refused
impossible change), its record read back by `resume` and by wl-preproc's reader.

**Fuzzed** (C2b's session fuzz extended; engineering, call 26):
- one seed gives the same draws, order and repeats in two processes (XC-409's lesson); adding a draw moves no
  condition or repeat;
- every draw inside its range; every non-aging wait between its shortest and longest; a `same` setting on a repeat,
  drummed or not, equals the original trial's value;
- each pair (or triple) once per de Bruijn cycle, realized and planned sequences agreeing; priming runs in range,
  every switch a change;
- after a hand-back, no trial `overridden` or `live` for that setting; after a range change, every draw inside it and
  naming it;
- a revert never moves a bounded setting, and restores the chosen moment's values;
- a trial kept out of moving up is never in a block's rule window, always in its fall-back window;
- no trial runs with a §9 combination, whatever the random changes;
- every strobing log row has `sequence`, the n-th matching the n-th code; every session resumable, none refused by
  `stranded.find` over a change row.

**The mutation gate:** C3's code in existing modules (`task`, `check`, `scheduler`, `taskd`, `record`, `resume`,
`link`, `web`, `serve`, `review`, `preflight`, `cli`) is swept by CI's per-push gate, as C2b's was. *Engineering:* a
new module (say, a pure `variation.py` for drawing and sequences) must be entered in `tools/mutation_gate.py`'s
`RETURNS`, or the gate fails. The last CI run is read shard by shard, each to its closing line; `welfare_cmp.py`
shows every listed function identical but `Session._command`'s approved lines.

---

## 13. Decisions this spec revises

Each committed rule the PI's answers change, and where its dated revision lands. **The revisions are written with
the build**, in the commits that make the code true (CLAUDE.md: docs stay in sync), not now. Plans are left as
written, records of their day.

1. **TSK-21** ("a parameter is set by one or the other, never both") and engine spec §14.1 ("refused at load"):
   never both reads block by block, and a condition may hold its own range (Q1b; §2). A dated "Revised" line on
   TSK-21; a dated note under engine spec §14.
2. **TSK-15** (a non-aging foreperiod "declares its ... tail rule") and engine spec §6.11: one rule, draw again (Q2;
   §3). A "Revised" line on TSK-15; a note under engine spec §6.
3. **TSK-31** ("a repeat's drawn values are fresh or the same per task") and engine spec §16.5 ("declared per
   task"): declared per drawn setting, required (Q3; §2). A "Revised" line on TSK-31; a note under engine spec §16.
4. **XC-362**'s "a drum's repeat keeping its values whatever ordinary repeats do" (also the C2a plan's "Not in
   C2a"): a drummed repeat follows each setting's same or fresh ("Follow same/fresh"; §2). The backlog line closes
   with the build ("closes XC-362"), and TSK-31's revision says so.
5. **The C2b plan's Appendix B item 1** ("setting the value back does not hand control back to the condition; it
   stays yours until the run ends", confirmed 2026-10-19): the hand-back (Q7a; §6). Engine spec §14.7's C2b note gets
   a dated note after it.
6. **TSK-19's note** (revised 2026-10-20: the edit "is not undone by setting the value back", and "until the console
   shows them, the edit's line on the changes feed names the conditions it overrides"): the hand-back, and the
   console showing the overrides (§6). A second "Revised" line on TSK-19.
7. **The C2b plan's decision 38** (the operator's edits at the rig are C3's; likewise its "Not in C2b" and engine
   spec §13's C2b note, "the operator's edits (item 2), C3's") and **the PI's split of 2026-10-11** (CHECKPOINT: "C6
   programs, rig edits and interludes"): rig edits are a build of their own right after C3 (Q0; §1). A dated note
   under engine spec §13, and CHECKPOINT's build list.

Not a revision but a reading, made in the record (engineering, call 8): engine spec §17.1's live edits "not merged
into the run's values" (§8); a dated note under engine spec §17 says how.

---

## 14. Welfare items

The PI approved these four for the design on 2026-10-30, "Approve all four"; the final code comes back to him with
the plan. The welfare-critical list ([architecture.md](../../design/architecture.md), "Welfare-critical modules") is
not widened.

Numbered as they were put to him:

1. **`Session._command` gains three branches beside the pause** (hand back, range, revert), each handing to a
   function off the list, as C2a's and C2b's buttons did; its listed `held` pass-through and `except` line are
   unchanged.
2. **One line in `Session._command`'s setting path, ahead of `set`**, runs §9's live refusal, so the listed `except`
   line turns an impossible change into a refusal on the feed; the listed parts are unchanged.
3. **Revert goes on the welfare summary** (engine spec §20 item 3): it restores task settings and drawn ranges only,
   never a bounded setting such as a reward size (§17.6); each value goes through `Session.set` unchanged, and the
   revert is refused whole if any value is.
4. **Unchanged byte for byte: `Session.set`, `link._setting`, `Service._start` and `stranded.py`.** `Session.set`
   stays so because change ids are assigned where changes apply (`_apply_staged`, off the list), and the live layer
   stays merged in the run's values, its names kept apart and recorded beside them. The welfare comparison at merge,
   function by function on exact source, shows it.

Why item 4 holds: `link._setting` decodes the new commands' numbers as it does today; `Service._start` meets no
rig-made plan in C3; `stranded.py`'s verdicts depend on `resume._read` reading every change kind (§8). Every other
listed function is unchanged too. A draw or a live range cannot reach a reward: a bounded setting is no task
setting, and naming one is refused (§11).
