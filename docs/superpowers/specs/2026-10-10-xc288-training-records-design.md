# XC-288: training records an AI agent can learn from

- **Status:** proposed, for the PI's review
- **Date:** 2026-10-10
- **Backlog:** XC-288 (the PI, 2026-10-08), brainstormed with the PI on 2026-10-10, while engine build A2's CI ran
- **Reviews:** an engineering and an NHP-training review, 2026-10-10; their fixes are folded in as defaults, and
  the questions they raised for the PI are marked where they arise
- **Starting point:** the research note
  [2026-10-09-xc288-ai-learnable-training-records.md](../../research/2026-10-09-xc288-ai-learnable-training-records.md),
  which informs this design and decides nothing; its §4 suggestions R1 to R13 are taken, changed or left as §2 says
- **Builds:** mostly engine build C, with parts in T, D, F and K (§7); the engine spec's build order is unchanged

---

## 1. Why

The PI's idea, in his words of 2026-10-08: "save all of the behavioral and task data in such a way that an
AI agent could use a complete backlog of data from all animals all tasks etc to determine techniques to
try to help animals learn tasks. For instance, maybe 5 years down the road we have hundreds of training
session[s] from a dozen or so monkeys where experimenters tried a variety of techniques to help the
monkeys learn. The AI agent could learn from those logs to make suggestions for things to try and perhaps
even run sessions (by tweaking task and training parameters) to help the monkey learn."

And in the brainstorm: "we want the agent to have as much information as possible to learn from"; "the
training log should be aware of all parameters and the behavior of the animal. even the eye data could be
informative"; "the rig/xcon console is responsible for generating a file for ai agents to learn from".

**What has to be true, years on**: a question like "when someone did X for an animal stuck at stage Y, what
followed, against when they did not?" is answerable from the records alone, across animals and tasks,
without reconstructing anything from memory or notebooks. **What is urgent now is the record, not the
agent**: no session has run (the lab opens in January 2027), and every session recorded before the record
holds what an agent needs is history an agent cannot use. Build C, which builds the task object, live edits
as a layer, presets and history, is where most of it lands.

**What exists today** (the research note, §3, and a reading of `wl_xcon` at `7fea382`): `trials.jsonl` holds
every trial's outcome and whole resolved parameter set; `parameter_changes.jsonl` holds each applied live
change's name, old and new value, actor and run. Missing: **why** a change was made, **when** (no instant, no
`trial_number`), what else was on offer, what a change means across tasks, and **everything the animal did
below "correct or not"**: no reaction time, no item chosen, no fixation-break time, no trial times and no
state transitions with times (timing exists only as codes strobed to the sync box), no saccades and no eye
samples (`gaze.py` writes the calibration, `eye_calibration.yaml`, and no samples; no session wires
`eye.UdpSource` yet; the eye PC's own file is the record by S5 §3, and nothing says it runs in a training
session).

## 2. What the PI decided (2026-10-10)

Each was asked through the console's question tool in plain terms; the recommended option was first.

| # | Question | His answer | Offered against |
|---|---|---|---|
| Q1 | Scope | **Records first**: settle what every session records; leave room for an agent, design it when one is built | design the agent now too; only leave room |
| Q2 | What counts as a technique | **Rig changes as countable events, plus wl.works' facts** (weights, water regime, observations) joined by the animal's permanent id; other off-rig training in free-text notes | rig changes only; off-rig techniques counted in wl.works too |
| Q3 | Whether tasks say what their settings do | **Clear-cut settings get a definite direction; others an expected direction with a context note**: "some animals find some things harder when others find it easier. some things genuinely dont make things harder or easier. there are some things that are clear cut, though"; "e.g., dimmer a distractor may make the task easier, but for some monkeys a distinct change along a feature dimension that is orthogonal to the utility in the task can make it harder to understand" | a required easier/harder mark; optional marks; nothing marked |
| Q4 | Reasons for changes | **One tap at the change or by the session's close**, never holding the change | optional reasons; reasons only at the end |
| Q5 | Random choice between steps judged equally good | **Allowed, off by default**, the odds recorded | not now, room left; never |
| Q6 | When a stage counts as learned | **Stages declare their pass rules**; the rig records when one is met; a trainer may mark it by hand | the trainer marks it; computed later |
| Q7 | Who made a change | **Changes need a wl.works sign-in** | pick from a lab list; keep typed names |
| Q8 | When nobody can sign in | **Allowed, marked unverified**: a name from the lab list, recorded "not signed in" with why | refuse changes; allow until opening |
| Q9 | The shape on disk | "**it should be more than just changes.** the training log should be aware of all parameters and the behavior of the animal. even the eye data could be informative..." | one change log; fields on today's files; a separate log |
| Q10 | Behavior and eye data in training sessions | **The rig keeps its own full log, every session**: "i think the rig/xcon console is responsible for generating a file for ai agents to learn from" | always run the sync box and eye PC; behavior without gaze |
| Q11 | What the agent reads | **One self-describing file per session**, built at close from the rig's logs, rebuildable | the logs themselves; one history per animal |
| Q12 | Section 1, what the rig writes | Agreed, adding "**the experimenter notes, which will come from the eln on wl works**" | — |

Sections 3 to 8 are the brainstorm's five design sections, each agreed as presented; §9 and §10 gather what
they said about welfare and what was left for later; §11, added at review, lists the documents this changes.
Two defaults were stated without asking and stood: **what the console offered** is recorded beside what was
chosen (R6), and **the corpus is the session folders** that wl-preproc already ingests (§6). Every decision
here is in [decisions.md](../../references/decisions.md), section "Training records".

## 3. What the rig records in every session

Every session kind (training, piloting, recording), the home-cage kiosk's included (§6). **Nothing below
is written inside a frame or a trial's loop**: each is buffered during the trial and written at the trial's
boundary, as the hot-path rule requires.

- **Buffers are sized from the trial's `max_frames`**. An overflow is counted and flagged in the trial's
  row, never flushed inside a frame.
- **No new per-frame allocation** beyond what `run_trial` already does: it appends to per-trial lists today.
- **A trial that faults** has its buffer written in `Service._run`'s containment, so the fault keeps its
  record.
- **The continuous mode** (build K) has no trial boundary: it flushes at its once-a-second check (engine
  spec §13.6).

The cost is measured by a script in `tools/` before any number is stated.

### 3.1 Each trial's row gains

- its **start and end instants** (§3.11);
- its **reaction time**, as the task declares it (§4.3: a fixation's end to a choice's start, a lever
  release), and **which item was chosen**, for any task that offers a choice;
- its **latency to acquire fixation**, a named column, for a task that asks for one;
- **when and where a fixation broke**, for a trial that ended on a break;
- the condition's **permanent number** (XC-197, engine spec §14.5) beside its name;
- **which settings a live edit had overridden** (engine spec §14.7's flag), by name;
- the task's **content hash** (§4.4), once per run in the run's start row rather than per trial.

XC-022's planned `rt_approx_ms` is this reaction time; one definition serves the console's plots and the
record.

### 3.2 A timed event log

**Every state the task entered and left, with its instant and why it left** (a timeout, a fixation broken,
a choice), and every code the rig strobed with the instant it strobed it. **A reward's instant is its
code's**, taken where the card strobes it; `welfare.Rig` is not wrapped. In a recording session these are
the same moments the sync box receives, so the two can be checked against each other (build F); in a
training session with no sync box running, this log is the only timing there is.

### 3.3 Saccades and eye samples (build T)

- **Detected saccades**, per trial: onset and end instants, where each started and landed, peak speed, as
  the online detector (`saccade.Detector`, [@engbert2003microsaccades]) found them. The offline detector in
  wl-preproc stays the analysis-grade one; these record what the rig acted on.
- **Every eye sample the rig polled**: its instant, the tracker's frame number, each eye's raw P1 − P4
  signal and **pupil size** (OpenIris sends it, S5 §3; `eye.EyeReading` carries `pupil_area`), the
  calibrated position in degrees, the calibration map's version and the tracker's staleness state. These are
  the samples the rig used, not every frame the camera took; the frame number lets them be matched to the
  eye PC's file. Stored in a compact binary file, not text.
- **Which design polls is build T's to settle.** No session wires `eye.UdpSource` yet; only the calibration
  block builds a `gaze.Tracked`, which polls from the loop and stamps the frame's time. S5 §3 specifies a
  polling thread with `CLOCK_MONOTONIC` arrival stamps. The sample's instant is whichever holds.
- **In a recording session the eye PC's file remains the official record** (S5 §3), and the rig's copy is
  labeled a copy wherever it appears. In a training session it may be the only gaze there is.

### 3.4 One change log

Today's `parameter_changes.jsonl` grows into **one log of every change to what the animal experiences**, one
row shape for all of them. Kinds in build C: a live edit, a preset applied, a revert, a plan or condition
edit (engine spec §13.2), a task switch between runs, an interlude, and **a task revised**: written at the
session's open when the task's content hash differs from the one the animal last ran, naming the
declarations that differ and taking a reason (§3.5). Build T adds **a recenter** (a new gaze-map version with
its offsets, S5 §6). Build D adds a procedure's step, a random pick, and a decision point where a planned
step could not be taken.

**[PI: in-session hand techniques]**

Each row carries:

- **its `change` id**, unique in the session. **A preset is one row per setting it moved**, all sharing one
  `change` id;
- **when**: the instant it applied (taken in `_apply_staged` for a setting), the `trial_number` of the first
  trial it applied to, its run;
- **what**: the setting, from what to what;
- **what it means**: the setting's declared meaning (§4.1), and for a clear-cut or expected setting the
  direction ("easier", "harder") and the size of the step, relative to the old value;
- **who** (§3.6);
- **what was offered**, when the console offered a list (the presets shown at the session's open, the
  start choices of last values, defaults or a preset; later, an agent's suggestions);
- **the odds**, when the rig chose at random (§4.5; build D): the probability of the option taken, the
  options and the seed, so the pick replays. The field exists from build C and is empty until D;
- **the procedure and its version**, when a procedure acted (build D).

**Only rows that strobe `PARAM_CHANGED` carry `sequence`.** A setting applied through `Session.set` strobes
it once, in `_apply_staged`, as today: a live edit, each setting of a preset, a revert, and in build D a
procedure's step that moves a setting. A task switch, a plan or condition edit, an interlude, a task
revised, a recenter, a random pick and an unavailable decision point strobe nothing and carry none. The join
to the recording is the codes' count, the n-th `sequence` row to the n-th code, until XC-008 puts the number
on the wire.

**Resume is build C's work too.** `resume.read`, through `_read`, sorts and counts every row by its
`sequence` and fails closed, so a row without one would leave its session unresumable. It learns to read
every kind (§8).

### 3.5 Reasons

- **A change applies at once and never waits for its reason.** The console then offers one tap from a short
  list, with optional words. The proposed list, for the PI's review of this spec: *struggling*, *too many
  breaks or no-responses*, *doing well, pushing on*, *planned step*, *trying an idea*, *correcting a
  mistake*, *compensating for a rig or tracking problem*, *animal agitated, drowsy or distracted*, *other*.
- **A reason not given by the session's close is asked for there**, in the page's End form, every
  unexplained change of the day in one list, skippable. The page sends the answers as a new command kind
  before its `EndSession`, since `_end` drops the session; `Session._command` routes it ahead of its
  outside-a-run refusal, as it routes a mark's note.
- **The close is never held by it**: a change still unexplained is recorded "no reason given" by the rig, in
  `Session.close` (in `await_return` for a `wlx run` session, whose terminal does not ask), so an empty
  field can never be mistaken for a lost one. A stranded session's unexplained changes get the same when
  `_close_stranded` closes it.
- **A reason is its own row, in `reasons.jsonl`**, pointing at the `change` id it explains, so a reason
  given later never rewrites a line already written. A preset's rows share one reason through their id.
- **The list only grows**: a code is never renamed or removed once used, so five years of reasons count
  alike.
- **Pauses and stops** stay in `controls.jsonl`, the welfare record, with its writers unchanged. **Its new
  rows gain an `id`**, so a reason row can point at a pause.

Why a reason matters: in records of choices made by people, what drove a choice also drives the outcome, so
an animal that is stuck gets the most changes and learns slowest, and a learner reading the raw history
concludes that changes slow learning. The record has to carry "any factors that causally affect both
observed treatment decisions and the outcome", and "it is impossible to verify that all confounders have
been measured based on statistical quantities alone" [@gottesman2018evaluating, §4]; their learned policies
recommended minimal treatment for the sickest patients, who were the ones treated most and died most (§3). The reason is the trainer's own statement of the most important one.

### 3.6 Who

- **A change needs a person signed in through wl.works**: a `Member`, with a permanent account id. Typed
  names drift ("Jake", "jake w", "JW") and an agent learning whose technique worked would learn from a messy
  list; who trained is also a factor that drives both the choice and the outcome.
- **The rig PC's own page never signs in** (architecture.md: a box name, loopback only). A trainer at the
  rig PC signs in by opening the rig's https page in its browser, once XC-151 and XC-152 give it one; a
  change from the plain page is "not signed in".
- **When nobody can sign in** — sign-in not yet set up at that rig (XC-151, XC-152), or wl.works or the
  network down — **the change goes through**: the person picks their name from **the lab's people list**,
  and the row is recorded **"not signed in"**, with why. Until XC-151 and XC-152 are done, that is every
  change. **Until XC-320's `prepare-session` carries the list, it is a file on lab storage kept by hand**,
  each entry a wl.works account id and a display name.
- **"Not signed in" is a third actor kind**, beside box and member, on the wire and in the record, carrying
  the account id picked and why. `actor.from_map` refuses any kind but those two today, and resume reads
  `by` through it, so both learn it in build C. **[PI: names or ids only]**
- **Pause, stop, resume and a manual reward never need sign-in.** They are welfare actions, and they work
  as they do today, for any actor.
- **Where the rule is checked**: a setting in `Session._command`'s ordinary part, after its `SetParameter`
  check and before the `try` around `set`, so the `held` pass-through above it and the welfare `except` line
  are untouched; a task switch in `Service._route`, before `_start`. `_command` holds two welfare-listed
  parts, so the check goes on build C's welfare summary (§9). **What it proves is bounded by XC-218**:
  `taskd`'s command socket trusts a member map from any local sender, so the check holds a page to the rule
  and does not prove who sent a command.
- **Room for software actors**: the planned system actor (engine spec §11.3, §13.9) and, later, an agent
  take their place in the same field, each naming the person accountable for it (R13). Nothing here builds
  one. An agent's identity in the record also waits on XC-218.

### 3.7 Stages

**When a stage's pass rule is met** (§4.2), the rig records it as an event, with the counts that met it:
**every outcome class** (correct, wrong, broken, no response, aborted) by condition, not only the trials
answered. **A trainer may also mark a stage passed by hand**, recorded as theirs, with a reason. Moving an
animal on stays someone's decision, or a procedure's (build D); the record keeps both moments, "the rule was
met" and "the animal was moved on", so the delay between them is visible too.

**Failures are recorded too**, so an agent does not learn from survivors alone: a stage abandoned, a task
dropped for an animal and an animal withdrawn from training are each an event, with who and a reason.

### 3.8 At the session's open

- **The animal's permanent wl.works id** beside its rig name: a rig name can be edited and reused in
  wl.works, `animal.id` never changes (the research note, §3.3). Until wl.works sends it, the record holds the
  rig name, and the agent's file is joined to the id at its build from wl.works' record of which animal had
  which rig name on which day.
- **That day's weight, with the date it was measured, and water regime**, copied in when wl.works sends
  them with the session's details (XC-100), so the record shows what the trainer saw; until then joined at
  the file's build, with **wl.works' water entries** before the session (amounts, sources, supplements,
  ad-lib days).
- **The reward fluid** (type, dilution), recorded at the open.
- **The restraint mode** (kiosk, head-free chair, head-fixed): `config.json`'s `deployment` already says it
  (`cage_side`, `rig_chaired`, `rig_fixed`).
- **Who was in the room**: one optional tap at the open, present, watching remotely or absent.

### 3.9 Experimenter notes and welfare observations

The agent's file takes in **that session's notes from the ELN on wl.works, and the animal's welfare
observations and health over time**, not only that day's, each with its author, when it was written and what
it was about. Notes are often written after the session, so they arrive at a rebuild (§5.4), and the file
says how recent its notes are. **What is missing in wl-works** (read at `71b04613`): the ELN's per-session
notes are designed (its plan 11 and 16b, `animal_session`) and not built; nothing ties a note to a rig
session; nothing delivers notes to lab storage. Observations exist, per animal, with when it happened and
when it was written. The asks are in §7; until they are met, the file says it holds no ELN notes.

### 3.10 What stays where it is

`controls.jsonl`, `welfare_notes.jsonl`, `warnings.jsonl` and `refusals.jsonl` keep their writers and their
fields. `controls.jsonl`'s new rows gain an `id`, and pauses and stops gain reasons only by new rows (§3.5).
The welfare-listed code this touches is in §9.

### 3.11 The rig's clock

**Instants are `wall_now()`**: the session's wall clock, read at its open and carried on a steady clock, the
one every welfare call is given. **Events inside a trial are frame offsets from the trial's start.** Time
since the open derives from `opened_wall_at`; no new clock is kept (`now()` advances only at trial ends, and
a resume restarts it). **The sync box stays the timing ground truth** (S3), and **no accuracy is claimed for
the rig's clock until a script in `tools/` has measured it** (CLAUDE.md).

## 4. What a task declares

Agreed with wl-xtasks as part of build C's task object (engine spec §21's ask). The task's author proposes
each; **the person reviewing the task confirms it**, in the review report (engine spec §18.1).

### 4.1 What each setting means

Every task setting a person can change between trials declares one of:

1. **Clear-cut**, with its direction: "raising it makes the task easier" or "harder" (a fixation window's
   size; a hold's duration).
2. **Expected**, with the direction expected and **a short context note** on why it might not hold for an
   animal: "dimmer distractor: expected easier (less salient); a change along a feature irrelevant to the
   task can confuse some animals".
3. **Not a difficulty setting.**

**Required**: the load-time check refuses a task that leaves one undeclared, because a missing declaration
cannot be told from a forgotten one. "Expected" is an honest answer whenever the author is unsure. An
expected direction is recorded as expected, never as a fact; comparing it with what followed, animal by
animal, is one of the things an agent can learn.

**Two bounded settings change live**, `reward_correct` and the out-of-cage limit. They are declared in the
bounded config, whose loader is welfare-listed, so the task check does not cover them: their meanings come
from a table in wl-xcon, outside `bounds.py`.

### 4.2 Stages and their pass rules

A training task (later, a procedure) declares its **stages in order**, each with **an id that lasts across
the task's versions** and **a pass rule written in what the rig already counts**: the counting table (engine
spec §16.1), the trial rows' outcomes by condition, over the last N trials, within a session, across
consecutive sessions: "at least 80% correct over the last 200 trials, in each of 2 sessions in a row".

- **Every rule names its denominator**: all trials, or the trials answered, which is what the counting table
  counts by default.
- **A rule may require balance** across conditions or sides.
- **A rule spanning sessions** reads the per-animal state on lab storage (engine spec §13.7).

The check refuses a rule that names something the rig does not count, or no denominator. A stage's rule is
part of the task's content hash; its id outlasts a revision, so a stage's trials count on across one.

**[PI: whether a pass rule counts only trials at the stage's target difficulty]**

### 4.3 What "the item chosen" and "reaction time" mean

A task that offers a choice declares which of its items count as choices and what choosing one is (a gaze
landing, a touch, a lever), so every trial records the one chosen (§3.1). **Every task declares how its
reaction time is defined**, from which event to which, so one column means one thing per task.

### 4.4 Identities that hold for years

- **The task's content hash**, always: a hash of its content, never its file path (the research note's §3.1
  found `versions` holds the path as given).
- **Stages' ids** (§4.2), and **conditions' permanent numbers** from the task's registry on lab storage
  (engine spec §14.5).
- **A procedure's identity and version** (build D).

### 4.5 Steps that may be chosen at random (build D)

A procedure may declare **steps judged equally acceptable** at a decision point, for the rig to choose
between with stated odds. **Off unless a person switches it on for a given animal and task**; never a reward
amount or anything under a welfare ceiling (engine spec §15.7); each pick recorded with its odds and seed
(§3.4). A decision point where no step could be taken (a limit near, the animal not working) is recorded as
**unavailable**, with why.

Why: from records of choices people made, an agent can learn what tended to follow a technique, not what it
caused. Learning from logged choices uses the probability with which each was made, which has to be
recorded while the choosing policy runs [@swaminathan2015batch, §4]; randomizing at each decision point,
and recording when an option was unavailable, is how causal effects of in-the-moment interventions are
estimated [@klasnja2015microrandomized, "Micro-randomized trial design" and "Randomization and participant
availability"]; and sequential multiple assignment randomized trials are the design advocated for adaptive
treatment strategies, because "past treatment may have delayed effects" [@murphy2005experimental, abstract],
as a training step's are.

## 5. The agent's file

### 5.1 One file per session, SQLite

**One SQLite database per session**, in the session's folder beside its logs, so it travels wherever the
session goes; an agent reads a folder of them. SQLite is in Python's standard library, so it adds no
dependency (ADR-0004's inventory is unchanged), and Python and R read it; an agent learns what is in a file
with one query. Considered: Parquet, the data-science standard, which needs `pyarrow`, a large new
dependency; NWB, which is wl-preproc's domain. If XC-011's Parquet behavioral table is built, it and this
file are both made from the same logs; neither is the other's source.

### 5.2 What it holds

| Table | What |
|---|---|
| `about` | the file's format version; when it was built and by which wl-xcon version; the logs it was built from, each with its checksum; its wl.works snapshot's date (§5.4), so how recent its notes are; whether its gaze is the official record or the rig's copy; the session's camera videos, if any (P9), by path, never copied |
| `dictionary` | **every table and column: what it means and its unit**, so the file explains itself |
| `animal`, `session` | permanent id and rig name; the session's kind, rig, calibration, restraint mode, reward fluid, who was in the room; who opened it, a new `config.json` field (today it names no one); that day's weight with its date, and water regime |
| `water` | wl.works' water entries before the session: amounts, sources, supplements, ad-lib days (§3.8) |
| `task` | the task's declarations, copied in: each setting's meaning (§4.1), stages with their ids and pass rules, choices, reaction time's definition, content hash |
| `runs`, `trials`, `trial_settings` | every run; every trial with its behavior (§3.1); every setting's value on every trial |
| `events`, `saccades`, `gaze` | the timed event log (§3.2); saccades and eye samples with pupil size (§3.3, from version 2) |
| `changes`, `offered`, `reasons` | the change log (§3.4), what was offered, and the reasons (§3.5) |
| `controls` | pauses, stops, resumes, marks, manual rewards, with their reasons |
| `stages` | rules met, stages marked, and the failures (§3.7) |
| `notes` | ELN notes, and welfare observations and health over time (§3.9) |
| `warnings` | the imperfections the session accepted (engine spec §19) |
| `summary` | per task in the session: trials by outcome class, percent correct by condition with its denominator, reaction times, latency to acquire fixation, breaks and no-responses, fluid earned, time in the chair (from the `HEAD_FIXED` and `HEAD_RELEASED` codes in the event log, their only record today), stage reached; **XC-011's session summary**, one computation for both |

People are recorded by wl.works account id. **[PI: names or ids only]**

### 5.3 When it is built

**After the session has closed, as its own process.** The close (`Service._end`, welfare-listed) is
untouched. The build is spawned from `_end`'s unlisted callers, `Service._route` and `Service.step`, and for
`wlx run` from its close path, which runs through the welfare-listed `_settle_return`: that spawn goes on
build C's welfare summary, unless the plan finds an unlisted site. A separate process, because a build inside
`wlx taskd` would stall its housekeeping loop and leave garbage to be collected during the next session's
trials. **A build that fails never touches the close or the animal's return**: it raises a notice on the
console (not one of engine spec §19's warnings), and the file is built again later (§5.4).

### 5.4 Rebuilding and versions

- **One command rebuilds the file** for one session or for every session in a folder. **Its network part
  runs on one named lab workstation**, with its own wl.works client (XC-320) and a member's sign-in: never
  the rig, and never a wl-preproc host, which never initiates a connection. **The rig gets no new network
  route.** The workstation's read of wl.works is new, and architecture.md's "Data outputs and lab
  integration", which allows a lab host only NTP to wl-works, is amended for it (§11).
- **It writes a dated snapshot of what it fetched** (ELN notes and wl.works' facts) **into the session's
  folder**, and the build reads only the folder, so it can never disagree with it and **the same folder
  gives the same contents** (compared as a canonical dump, `about`'s build time and wl-xcon version left out,
  since SQLite's bytes can differ).
- **It lists every session whose file is missing, older than the current version, or built on a snapshot
  older than a date given**, since notes written later trigger nothing.
- **Every format change bumps the version**, and every past session rebuilds into it, with tables a
  session never had (gaze before build T) present and empty.

## 6. Where the records go

- **The corpus is the session folders** on lab storage, the agent's file in each; the same folders
  wl-preproc already ingests.
- **wl-preproc** carries the change log, reasons, timed events and pauses into the published dataset
  (today it reads none of them) and leaves the agent's file alone.
- **wl.works' facts** (weights, water regime and entries, observations, ELN notes) are joined by the
  animal's permanent id at the file's build, from the folder's snapshot (§5.4), and, once XC-100 exists,
  also copied in at the session's open.
- **The home-cage kiosk** runs the same task code and writes the same logs and the same file into whatever
  record S13 §5 settles (it suggests no session folder). Nobody may be present at its close, so its close
  records "no reason given" for every unexplained change.

## 7. Which build carries what

| Build | What |
|---|---|
| **C** (+I) | §4.1 to §4.4's declarations and their load-time checks, and the table for bounded settings; §3.1's trial fields and §3.2's event log; the change log (§3.4) with every field, the odds empty, and `resume._read` for every kind; reasons on the console and at the close, `reasons.jsonl` (§3.5); sign-in for changes, the "not signed in" actor, the people list's interim file (§3.6); stage and failure events (§3.7); the open's facts (§3.8); **the agent's file, version 1, and its rebuild command** (§5) |
| **T** | eye samples with pupil size, saccades, and which ingest design holds (§3.3); a recenter as a change (§3.4); the file's version 2 |
| **D** | procedures' steps as changes; random picks with odds; unavailable decision points (§4.5) |
| **F** | the rig's event log checked against the sync box's codes in recording sessions (§3.2) |
| **K** | the continuous mode's buffers flushed at its once-a-second check (§3) |

**Asks of other repositories**, sent once this spec is approved:

- **wl-xtasks**: §4's declarations, in build C's task-object agreement (engine spec §21).
- **wl-works**: `prepare-session` (XC-100) to carry the animal's permanent id, that day's weight with its
  date and water regime, and the lab's people list with each person's account id; the ELN's session (16b's
  `animal_session`) keyed to the rig's session (subject and session folder name); each note with its own
  author and time, not only whole-session revisions; a client for the rebuild's workstation (§5.4) and a
  read path by which it, signed in as a member, reads a session's notes and an animal's observations and
  health, weights with their dates, water regime and water entries (amounts, sources, supplements, ad-lib
  days), and rig names over time; and **a record per animal per day of whether it trained, and why not**.
- **wl-preproc**: read the change log, reasons, timed events and `controls.jsonl` into the published
  dataset; accept the agent's file in the session folder without reading it.
- **wl-touchtrain** (the kiosk): the same logs and file (S13 §5).

## 8. Testing

Simulation first: no animal, no tracker, no network.

- **A simulated session end to end**: a task with declared settings and stages runs on the simulated
  subject; it takes live changes with and without reasons, signed in and not, a preset, a pause with a
  reason, a stage's rule met and a stage abandoned; the test reads the agent's file back and checks every
  row against what happened.
- **Every row kind resumes**: a session holding each change kind, with and without `sequence`, a reason, a
  "not signed in" actor and a controls row with an `id`, resumes from its record.
- **The file explains itself**: a test fails if any table or column lacks a definition and a unit.
- **Rebuilds are faithful**: the same folder gives the same canonical dump, `about`'s build fields aside; a
  stored version-1 session rebuilds into every later version.
- **Nothing waits on paperwork**: a change applies before its reason; the close asks for missing reasons,
  records "no reason given" for those skipped, and closes either way, a stranded session's close included;
  pause, stop, resume and a manual reward work with nobody signed in; a failed build leaves the close and
  the animal's return untouched and raises its notice.
- **The load-time check** refuses a task with a setting undeclared (§4.1), a pass rule naming something the
  rig does not count or no denominator (§4.2), or no reaction-time definition (§4.3).
- **The trial loop stays fast**: the new fields are written between trials, a buffer's overflow is counted,
  and a faulted trial's buffer is written; their cost is measured by a script in `tools/` before any number
  is stated.
- **Every new check proven able to fail** (`tools/mutate.py`, read line by line).

## 9. Welfare

**XC-288 changes welfare-listed code in these places, each for build C's welfare summary.** No function is
added to architecture.md's list.

1. **`Session._command`**: the sign-in check for a setting, in its ordinary part, between the `held`
   pass-through and the welfare `except` line (§3.6); the close-time reasons' command, routed ahead of its
   outside-a-run refusal (§3.5).
2. **`Session.set`**: XC-288's preset grouping, one `change` id across a preset's rows, joins engine spec
   §20.3's item for presets and revert.
3. **`Service._close_stranded`**: "no reason given" for a stranded session's unexplained changes (§3.5).
4. **`wlx run`'s close path**, through `_settle_return`: the file's build spawned, unless the plan finds an
   unlisted site (§5.3).

Unlisted, named so the plan need not look for them: `Service._route` (a task switch's check, before
`_start`; the build's spawn), `Service.step` (the spawn), `_apply_staged` (the applied instant),
`Session.close` and `await_return` ("no reason given").

Sign-in is never needed for pause, stop, resume or a manual reward (§3.6); the close is never held by a
reason or by the file's build (§3.5, §5.3); random choice never touches a reward amount or a welfare ceiling
and is off unless a person switches it on (§4.5). An agent acting on sessions would act through the same
paths as a person and be bounded the same way (the research note, §5); how far it may go is not decided
here (§10).

## 10. Not decided here, and why

- **The agent itself**: how it acts (suggest, act on approval, act within an envelope), whether it has
  limits tighter than a person's, who answers for it, what "helped" means as its objective. Q1 left it for
  when an agent is built; the record leaves room (§3.6) and keeps what every candidate objective needs
  (days, trials, reward, engagement; §5.2's `summary`). A backlog item.
- **Personal data**: the file names lab members and holds free-text notes. It stays on lab storage; which
  rules govern it at KU Leuven, and whether any of it is ever published, is UNVERIFIED and the PI's. A
  backlog item.
- **A simulated animal that learns**, as a test bed for an agent before an animal (R12): every published
  teacher found was tried on simulated learners first (the research note, §2.3). A backlog item, beside
  XC-146.
- **MonkeyLogic sessions** on the swapped rig (ADR-0005): brought into an animal's history with what they
  carry, marked as having no reasons. A backlog item.
- **The reason list's final wording** (§3.5): for the PI's review of this spec.
- **The file's size with eye samples**: measured once a session exists; if the `gaze` table makes files
  unwieldy, a later version may keep gaze beside the file.

## 11. Amendments to other documents (each with the build that changes it)

- **architecture.md** (C): "Data outputs and lab integration": a session's files gain the change log's new
  kinds, `reasons.jsonl`, the event log and the agent's file (the gaze file in T); the rebuild's workstation
  reads wl.works with its own client, beside the NTP route (§5.4); the console's actors gain "not signed in"
  (§3.6).
- **S5** (T): §3, which ingest design holds, and the rig's sample file with pupil size (§3.3); §6, a
  recenter is a change row (§3.4).
- **S8** (C): §3, the change log's one row shape, its `change` ids, `sequence` only on rows that strobe, and
  reasons in `reasons.jsonl` (§3.4, §3.5).
- **S10** (C): §2, the files a session writes and the rebuild's snapshot (§5.4); §5, §7's asks.
- **Engine spec §20** (C): item 3 gains the preset grouping; §9's items 1, 3 and 4 join the list.
- **Engine spec §24** (C, T, D, F, K): each build's row gains its part of §7.

## Sources

Cited by key from [library.bib](../../references/library.bib): [@gottesman2018evaluating];
[@swaminathan2015batch]; [@klasnja2015microrandomized]; [@murphy2005experimental];
[@engbert2003microsaccades]. The research note's Appendix B says how much of each source it read; the
library's notes say what was opened when these were entered on 2026-10-10.
