# XC-288: what records an AI agent could learn training techniques from

> **What this is.** A research note written on 2026-10-09 to prepare the brainstorm that backlog
> item XC-288 asks for (after engine build B, before build C is planned). **It informs the
> brainstorm and decides nothing.** Every requirement in §4 is this note's suggestion, for the
> brainstorm to take, change or drop. Each claim about a paper, standard or program was checked at
> its primary source on 2026-10-09 (Appendix B says how much of each was read); what could not be
> checked is marked UNVERIFIED. Claims about wl-xcon are from its code at `171b8d8` (`main`, the
> `xc288-prep` worktree), and claims about sibling repositories from their local checkouts, named
> where used.

**The PI's idea** (XC-288, his words of 2026-10-08): "save all of the behavioral and task data in such
a way that an AI agent could use a complete backlog of data from all animals all tasks etc to determine
techniques to try to help animals learn tasks. For instance, maybe 5 years down the road we have
hundreds of training sessions from a dozen or so monkeys where experimenters tried a variety of
techniques to help the monkeys learn. The AI agent could learn from those logs to make suggestions for
things to try and perhaps even run sessions (by tweaking task and training parameters) to help the
monkey learn."

## In short

1. An agent can learn "technique X helped" only from records in which X is a **named, typed event**:
   what changed, from what to what, by whom, why, from which trial, set against the animal's state
   before it and its progress after it, over days rather than trials.
2. **wl-xcon already records** every trial's whole resolved parameter set and every live change's
   name, old value, new value and actor. **It does not record** why a change was made, when (the change
   row has no instant and no trial number), what else was considered, or what the change means across
   tasks ("easier"). wl-preproc reads none of the change rows.
3. **Logs of experimenters' choices are observational**: if the animal that struggles gets the most
   interventions, a naive learner concludes that interventions hurt. This is the central difficulty
   in learning treatment policies from clinical records (Gottesman et al. 2018), and the reason
   off-policy methods want the probability with which each logged choice was made (Swaminathan and
   Joachims 2015).
4. The record feature that makes "which helped" answerable without assuming every reason for a choice
   was recorded is
   **randomization at decision points, with its probability recorded** (micro-randomization, Klasnja et
   al. 2015). Whether to randomize any training choice for an animal is the PI's decision.
5. **Prior art**: rule-based automated training is established in mice [@ibl2021standardized] and in
   macaques' home cages [@berger2018standardized], and records outcomes and progression well. None of
   the systems or standards read records the reason for a change or the alternatives considered.
   MonkeyLogic records a trial-by-trial history of changed variables, without who or why.
6. **Algorithmic curricula have been demonstrated on simulated learners only** (Bak et al. 2016; Tong
   et al. 2025). I found no published case of a learned or language-model agent choosing training steps
   for live laboratory animals.
7. **Most of what an agent needs falls in build C's scope**: the task object, live edits as a layer,
   presets and history, procedures' carried state, the condition registry and the simulated animal.
   C's plan is the cheap moment to shape these records.
8. **An agent that acts would act through `Session.set`**, the one write path, welfare-critical and
   bounded by the same ceilings as any actor. It would be a new kind of actor (the engine spec already
   plans a "system actor" beside `Box` and `Member`), and the law names persons, not software, as
   responsible for animals and projects (Directive 2010/63/EU, Articles 24(1) and 40(2)(b)).
9. **No animal session exists yet** (the lab opens January 2027) and build C is ordered before build E,
   the display ready for January's V1, so if that order holds, records shaped in C cover every animal
   session the lab will run.
10. The questions for the brainstorm, ordered by what C's plan needs first, are in §6.

## 1. What an agent needs to learn "which technique helped"

### 1.1 The unit is an intervention, written as a typed event

For "this helped" to be learnable across a dozen animals and many tasks, each intervention has to be
recorded with these parts, and each part in a form a program can compare:

- **What changed.** A parameter (a fixation window), a criterion (when a stage advances), which reward
  entry pays (a procedure may choose among the bounded config's named entries, never an amount; engine
  spec §15.7), a stimulus property (a contrast, a distractor count), the plan (a condition added, a
  block order), a pause or break, a task switch, a step of a training progression. From what, to what,
  in the task's own terms and in terms that mean the same in any task (made it easier along a declared
  factor, by so much).
- **Who and why.** The actor, and the reason in a form that can be counted (a short code) beside any
  free text.
- **When.** The instant, the first trial it applied to, its run, session and day.
- **The animal's state around it.** Performance before, by condition; engagement (breaks,
  no-responses); time in session; fluid earned so far and the day's floor; days since the last
  session; weight and water regime, which wl.works holds (§3.3).
- **The outcome horizon.** The next trials, the session, the days to a criterion. Murphy (2005) names
  why this matters in sequential decisions: "past treatment may have delayed effects", so a step that
  depresses performance today may still shorten training.

Trial-level records are enough to model an animal's learning trajectory: PsyTrack infers "the
trajectory of sensory decision-making strategies from choice data" in mice, rats and people and
reveals "rapid adaptation to changes in task statistics" (Roy et al. 2021), and Bak et al. (2016)
inferred a learning-rule model from rat training data. Both need each trial's stimulus, choice and
outcome, which `trials.jsonl` already holds in full (§3.1). The gap is not the trials; it is the
interventions between them.

### 1.2 The counterfactual problem

**Logs of what experimenters chose are observational.** The choice depends on the animal's state, and
so does the outcome. Gottesman et al. (2018), learning sepsis treatment from intensive-care records,
found learned policies recommending minimal treatment for the sickest patients, because "most patients
who have high SOFA score receive aggressive treatment, and because of the severity of their condition,
the mortality rate for this subpopulation is also high". The training analogue (this note's inference):
the monkey stuck at a stage receives the most technique changes and learns slowest, so a naive learner
would conclude that changing technique slows learning.

Their requirement for the record: it must include "any factors that causally affect both observed
treatment decisions and the outcome", and "it is impossible to verify that all confounders have been
measured based on statistical quantities alone"; domain experts must judge whether the recorded state
is enough (Gottesman et al. 2018, §4). For training, the factors an experimenter acts on include what the
console shows, the animal's demeanor, the time of day and a colleague's advice. Some of these the rig
can record; the rest live in free text or in wl.works' observations, or nowhere.

**Off-policy evaluation needs the probability of each logged choice.** Swaminathan and Joachims (2015,
§3-4) write the usable log as the context, the action, its outcome and its *propensity*, the logging
policy's probability of that action, kept "during the operation of the logging policy". A log of
choices is "both *biased* (predictions favored by the historical algorithm will be over-represented)
and *incomplete* (feedback for other predictions will not be available)"; weighting by the recorded
propensities corrects the bias, and small propensities make the estimate's variance unbounded. Gottesman et al. (2018, §5) show the practical
consequence: when the policy being evaluated differs from the clinicians', "the number of informative
samples may be very small".

**A person's choice has no recorded probability.** Two partial remedies follow, both record design and
neither a decision: record the options that were on offer when a choice was made, so the choice set is
known; and, where the PI judges two options equally acceptable, let the engine choose between them with
a recorded probability.

### 1.3 What makes it answerable

- **Micro-randomization** (Klasnja et al. 2015): an intervention option is randomly assigned "at each
  relevant decision point", and a study "may randomize each person hundreds or thousands of times",
  which lets causal effects be estimated as they change over the study. When an intervention cannot be
  given, the decision point is recorded with an "unavailable" indicator, because "effect estimations
  have to take availability into account". The training analogue: at a stage where two techniques are
  both acceptable, the engine picks one from a recorded seed and probability; a point where neither
  could be given (a limit near, the animal not working) is recorded as unavailable.
- **Sequential randomization** (Murphy 2005): randomizing at each stage of an adaptive strategy, for
  decisions whose effects are delayed, which training steps are.
- **Simulation before animals**: both published teachers were evaluated on simulated learners (§2.3).
  wl-xcon's simulated animal (engine spec §18.3) follows declared functions with named profiles, none of
  them described as learning, and today's `simulate.Subject` has its rates fixed in code (XC-146). As
  specified it could test an agent's safety (does it stay inside the bounds, does it handle refusals),
  not whether its advice works.

## 2. Prior art

### 2.1 Training systems and data standards

| System or standard | What it records about training and interventions | What it lacks for XC-288 |
|---|---|---|
| **International Brain Laboratory**, standardized mouse training [@ibl2021standardized] | 140 mice in seven labs on one automated protocol: the stimulus set grows "as performance improved" (Appendix 1, table 1: over 80% correct on each contrast admits the next set); the reward drops by 0.1 µL after a session of over 200 trials while above 1.5 µL; errors on easy trials are more likely followed by a "repeat trial"; "trained 1a/1b" are criteria over three consecutive sessions. A colony database "stored data about each session and mouse (e.g. session start time, animal weight, etc.)" | The progression is one fixed rule for every animal, so its records show how animals respond to one protocol, not which of several techniques helped. I found no passage on how experimenters' departures from the protocol were recorded |
| **Alyx**, IBL's lab database (its source, `alyx/actions/models.py`) | `Weighing` (who, when, grams); `WaterAdministration` (who, when, session, mL, water type, ad lib); `WaterRestriction` (reference weight); every action's users, procedures and `narrative`; a `Session`'s `task_protocol`, `n_trials`, `n_correct_trials`, `qc`. Husbandry and sessions in one database, keyed by subject | No typed intervention: what an experimenter did differently is free text in `narrative`, or a different `task_protocol` |
| **Berger et al.**, automated training of rhesus macaques in the home cage [@berger2018standardized] (abstract) | "across-task unsupervised training (AUT)" of "successively more complex cognitive tasks", designed for "self-paced training schedules with individualized learning speeds based on automatic updating of task conditions"; it revealed differences between animals and "easier and more difficult learning steps"; progress was "primarily determined by the number of interactions with the system rather than the mere exposure time"; "a predefined training strategy allows for an observer-independent comparison of learning between animals and of training approaches" | How deviations were recorded: UNVERIFIED (the full text was not reachable) |
| **Calapai et al.**, the XBI cage-based system [@calapai2017cagebased] | 11 male rhesus macaques; tasks are XML files edited with a custom editor; one experimenter can manage several animals' training remotely; which animal made each interaction was assigned offline from video, with ID tags foreseen | I found no description of recording who changed a task file, when or why |
| **Womelsdorf et al.**, the kiosk station [@womelsdorf2021kiosk] | Its software "saves data for each individual frame, enabling complete reconstruction of the entire experimental session"; its touch task "proceeds through pre-defined difficulty levels that the operator/tester can set flexibly before or during task performance" | No statement found on whether an operator's changes are written to the data |
| **NIMH MonkeyLogic**, `editable` variables (its runtime-functions documentation) | "For editable variables, trial-by-trial change histories are recorded in the data file. Check the VariableChanges field" | Who changed a value and why |
| **NWB 2.11.0** [@nwb2026nwb] | `trials` ("repeated experimental units with consistent structure"), `epochs` ("coarse-grained experimental phases"), any trial column a writer adds, `Subject.weight` ("Weight at time of experiment, at time of surgery and at other important times"), `notes` and `protocol` | No intervention or training-stage concept; notes are free text |
| **ndx-structured-behavior**, an NWB extension (Ly et al. 2024, preprint) | `TaskProgram`, a `TaskArgumentsTable` of the task's "main parameters", type tables and recordings for states, events and actions, and a trials table that references them | No mechanism for training stages; its README calls version 0.2.0 "not stable" |
| **BIDS 1.11.2**, behavioral experiments | `beh/` with `_beh.tsv` and `_events.tsv`; `TaskName`, `Instructions`, `TaskDescription` and cognitive-ontology IDs in the sidecar | No intervention concept; the sidecar describes a task once (`Instructions` is the text given to participants) |

**The pattern.** Per-trial settings and outcomes are recorded everywhere. Change histories are recorded
sometimes (MonkeyLogic, and wl-xcon). Reasons, alternatives and probabilities are recorded by none of
the systems read. Where training was automated it was one fixed rule, which yields comparable animals
but no contrast between techniques.

### 2.2 Husbandry next to sessions

Alyx puts weighings and water next to sessions in one database. The lab already has the husbandry half
in wl.works (§3.3); the gap is the join, not the data.

### 2.3 Algorithms that choose training steps

- **Bak et al. (2016)** inferred "the parameters of a policy-gradient-based learning algorithm" from rats
  training on "a two-interval sensory discrimination task", then proposed AlignMax, which picks each trial's
  stimulus to move the animal's inferred policy toward a goal. **It was tested in simulation**:
  "Simulations show that our method can in theory provide a substantial speedup". Its discussion names
  two risks for real animals: "the animal may suffer a loss of motivation due to the low success rate,
  which is a natural consequence of the adaptive training algorithm", and mismatch of either model.
  "These issues are subject to tests on real training experiments."
- **Tong et al. (2025)**: a teacher that "decides its student's task based on the student's transcript
  of successes and failures", near-optimal by Monte Carlo planning, and a simple adaptive heuristic.
  **Tested on simulated learners and deep reinforcement-learning agents, not animals.** It lists what
  makes animals harder: "limited flexibility in controlling rewards and exploration statistics",
  "partial observability", and "no delineation between training and test trials".
- **Live animals.** Searches on 2026-10-09 found no published case of a learned or language-model agent
  choosing training steps for live laboratory animals. The closest are the fixed rules above (IBL,
  Berger et al.), which act without a person in the loop and are what wl-xcon's procedures (engine spec
  §15, build D) will be.

## 3. What wl-xcon records today, and what is missing

### 3.1 The session folder (`wl_xcon/record.py`, `wl_xcon/taskd.py`)

| File | What it holds that matters here | Missing for XC-288 |
|---|---|---|
| `config.json` | Subject, deployment, **`session_kind`** (training, piloting or recording, since build B), calibration, bounded config, `already_delivered_today`, the config files' names, the setup | Days since the last session; weight (in wl.works) |
| `runs.jsonl` | Per run, a start row (task, allocation, `versions`, trials, seed, block names, `layers` {task, run}, `resolved` values, bounded values, pre-flight rows, `by`) and an end row (`stopped_because`, `stop_kind`, trials, blocks run) | The task's `versions` entry is its path as given, not a content version; why this run and not another |
| `trials.jsonl` | Every trial: outcome, **the whole resolved parameter set**, block and condition names, ten position numbers, fluid commanded | Condition numbers stable across sessions (build C's registry, §14.5); whether a live edit overrode the condition's value (§14.7, an ask of wl-preproc) |
| `parameter_changes.jsonl` | Each applied live change: `sequence` (joined to the `PARAM_CHANGED` code on the recording clock), `name`, `was`, `now`, `by`, `run` | **A reason; an instant; the first trial it applied to** (placed only by the code's sequence and the file's order); the options on offer; a cross-task meaning |
| `controls.jsonl` | Stops, pauses, resumes, marks with their free-text notes, schedules, cancellations, manual rewards while paused: `kind`, `by`, `at`, `trial_index`, `run` | A reason for a pause or stop |
| `welfare_notes.jsonl` | Session opened and ended, departure, return, amendments with their reason | — (welfare marks, not training) |
| `warnings.jsonl`, `refusals.jsonl` | Accepted warnings; refused welfare-bounded writes, capped at 50 | — |

**Who.** Every `by` is an actor: a `Box` (a name typed at the rig, "unverified") or a `Member` (a
wl.works account whose token `wlx serve` checked), or null for the process's own rows
(`wl_xcon/actor.py`). The engine spec plans a third kind, "a system actor (a new actor kind beside
`Box` and `Member`)", for automatic pauses (§11.3, §13.9); it is not built.

**Free text** exists in two places: a mark's note (`controls.jsonl`) and an amendment's reason
(`welfare_notes.jsonl`). Nothing records a reason for a parameter change.

### 3.2 Where the records go

wl-preproc (local checkout at `a9a47a0`, 2026-10-08) reads `trials.jsonl` (each trial's resolved
values become trial-table columns in its NWB), `runs.jsonl`, `config.json` (to check the subject) and
an `xcon/*.yaml` calibration log. **It reads none of `parameter_changes.jsonl`, `controls.jsonl`,
`welfare_notes.jsonl` or `warnings.jsonl`**; reading `warnings.jsonl` is an open ask (engine spec §21).
Today, the who and why of a change would not reach the published dataset.

### 3.3 What lives outside the rig

- **wl.works** (local checkout at `aa58852e`, `src/db/schema/welfare.ts`) holds per animal: weights
  (`animal_weight`: measured when, grams, by whom), a reference weight with its reason, water entries
  with their source (`rig` or `home_cage`), the water regime (`free`, `bottle` or `control`, with a
  minimum over a window and a reason), and observations (`clinical`, `behaviour` or `general`, free
  text, a concern flag). An animal's `rig_name` is the rig's subject (`^[a-z0-9]{1,8}$`, unique in the
  table). Whether a rig name can be edited or reused after an animal leaves: UNVERIFIED (not read).
- **The rig cannot push to wl.works** (architecture.md, "Data outputs and lab integration"); it receives
  the day's delivered fluid with `prepare-session`, and nothing of a plan since 2026-10-01.
- **The kiosk's record is undesigned.** S13 §5 leaves it open with three candidates and recommends "a
  lighter record of its own" outside the pipeline for a first version. If home-cage training is where
  much of the training happens, a backlog that omits it is missing the part XC-288 is about.
- **Per-animal state on lab storage** (engine spec §13.7: programs, presets, last values, procedure
  state, one writer at a time) is designed in build C; its carried state is "recorded whenever read or
  written" (brainstorm notes, element 12).

## 4. Candidate requirements (this note's suggestions)

Each is a suggestion for the brainstorm, tagged with the build that would carry it. None widens the
welfare-critical list; where a suggestion touches a listed function, that is said.

| # | Suggestion | Why | Build |
|---|---|---|---|
| R1 | **One typed change event** for everything that changes what the animal experiences: a live edit, a preset applied, a revert, a plan or condition edit (§13.2), a procedure's step, a reward entry chosen, a task switch, an interlude, a pause | One shape an agent reads, instead of several files with different keys | C (live edits as a layer, presets, history) |
| R2 | **A reason on every change**: a short list of codes (e.g. "animal stalled", "too many breaks", "scheduled step", "testing an idea") plus optional free text | The reason is the confounder (§1.2); without it, "stalled, so changed" and "on schedule, so changed" look alike | C |
| R3 | **The instant and the first trial** on every change row | Today's row has neither; a change must be placeable without the recording | C (the row is written by `record.parameter_change`, called from `Session._apply_staged`, which is not on the welfare-critical list but also applies bounded values) |
| R4 | **Declared training factors** in the task object: which parameters make the task easier or harder, in which direction, in what unit | Makes "made it easier by X" comparable across tasks, the only way a dozen tasks become one dataset | C, agreed with wl-xtasks (§21) |
| R5 | **A procedure's decisions as events**: advance or fall back, with the criterion values that triggered it | Procedures are the automated techniques; their steps are interventions | C (the event), D (the library) |
| R6 | **The options on offer and, when known, the probability** of the one chosen: presets offered, an agent's ranked suggestions, a randomized step's probability | Off-policy evaluation needs the probability; the choice set is the least a person's choice can carry | C reserves the fields; D for randomized procedures |
| R7 | **Unavailable decision points**: a planned step not taken, and why (a limit near, the animal not working) | Klasnja et al.'s availability indicator | D |
| R8 | **Stable identifiers across years**: the animal (its wl.works rig name and record id), the task and its version (the review report version, §18.1, or a content hash), condition numbers (§14.5), a procedure's identity and version | Five years of records join only on identifiers that never change meaning | C |
| R9 | **A daily summary per animal and task**: trials, correct by condition, reaction times, breaks, fluid, time in chair, the stage reached | The outcome an agent learns against is daily progress, not single trials | XC-011's session summary; C defines "stage" |
| R10 | **Free-text notes kept apart from typed events, and able to point at one** (a note naming the change it explains) | Free text carries what no code anticipated; keeping it separate keeps the typed record countable | C |
| R11 | **Every record reaches one corpus**: wl-preproc reading the change rows, the kiosk writing the same shapes, per-animal history on lab storage | An agent learns only from what reaches it | asks of wl-preproc; S13 §5 |
| R12 | **A simulated animal that learns**, as a test bed for any agent's policy before an animal | Both published teachers were developed against simulated learners | C+I's simulated animal profiles, XC-146 |
| R13 | **Room for an agent actor** in the actor and event shapes (§5) | So the first agent does not need a schema change of every file | C reserves; built when an agent is |

## 5. An agent that runs sessions

**What bounds it is already built, and does not change.** A setting reaches a session through
`Session.set`, "the one validated write path, whatever the origin", which is welfare-critical whole
(architecture.md). A welfare-bounded name goes to `bounds.validate` against its ceiling; a task
parameter is held to its declaration. A procedure may choose among named reward entries and "never an
amount" (§15.7), and presets, revert and carried values "never carry a bounded setting" (§17.6). An
agent acting through the same path is bounded the same way; the out-of-cage clock, the daily fluid floor
and every ceiling apply to it as to a person.

**Where it could act from.** wl.works can publish nothing welfare-affecting to a rig: "No
welfare-affecting action — reward, stimulation, session start, parameter change — is ever published
through it" (architecture.md). The console link binds loopback by default. That leaves two places an
agent could act from: the rig itself, or the rig's https page signed in as a wl.works member, the way a
person off the rig acts (built in b2b slice 2, and switched off until XC-151 and XC-152 are done).
Either way it reaches `Session.set` like any console; changing the wl.works rule instead would be a
decision of its own.

**Who it is in the record.** Today an actor is a `Box` or a `Member`; the system actor is planned.
An agent would be a further kind. Fields the brainstorm may want (suggestions): its name and version,
the policy or model it used, the person accountable for it, the approval mode it acted under, and the
suggestion it was acting on.

**A named person stays accountable.** Directive 2010/63/EU requires "one or several persons on site who
shall ... be responsible for overseeing the welfare and care of the animals" (Article 24(1)(a)), and
every project authorisation names "the persons responsible for the overall implementation of the
project and its compliance with the project authorisation" (Article 40(2)(b)). An agent cannot hold
either role, so each of its acts would name the person who is.

**Approval modes.** Parasuraman et al. (2000) treat automation per function (information acquisition,
information analysis, "decision and action selection", action implementation), each at a level "from
fully manual to fully automatic", with "the costs of decision/action consequences" among the criteria.
Applied here, a mode could differ by kind of change:

- **Suggest**: the agent proposes on the console; a person applies it, and the change is the person's,
  naming the suggestion.
- **Act on approval**: the agent stages a change; it applies once a person approves.
- **Act unless vetoed**: the change applies after a stated delay unless a person refuses it.
- **Act within an envelope**: a person pre-approves, per animal and task, which factors the agent may
  move, how far and how often; anything outside asks.

**Precedents.** Fixed rules already change training without a person in the loop (IBL's reward and
contrast steps; Berger et al.'s automatic updating), and wl-xcon's procedures will be such rules. A
learned agent acting on live animals has no published precedent that I found. Bak et al.'s caution
applies directly: a teacher that maximizes learning speed may lower the animal's success rate, and with
it reward and motivation, so what an agent optimizes is a decision (question 7 below).

## 6. Questions for the brainstorm

Ordered by what build C's plan needs first. They are asked, not answered.

1. **What counts as a "technique"?** Only what the rig can change (settings, criteria, rewards, task
   order, breaks), or also what happens off the rig (handling, the water schedule, enrichment, who
   trains)? The first fits in C's change event; the second needs wl.works to record training actions
   too.
2. **Should every task say which of its settings make it easier or harder** (its training factors),
   so a change means the same thing in every task?
3. **Should a person give a reason for each change during a session**, from a short list with optional
   words? Required or optional? Typing during a session has a cost.
4. **Should the record keep what was on offer** when a choice was made (the presets shown, an agent's
   suggestions), and not only what was chosen?
5. **Would you accept the system choosing at random between two training steps you judge equally good,
   at some decision points, with the odds recorded?** Without this, the records can show what tended to
   follow a technique but not what it caused.
6. **Where should an animal's training history live**, and who reads it: lab storage beside its
   programs and presets, wl.works beside its weights and water, the published NWB, or all three? And
   should home-cage (kiosk) training be recorded in the same shape as rig sessions?
7. **What should "helped" mean?** Fewer days to a criterion, fewer trials, steadier performance, and
   with which floor on the animal's reward rate and engagement while it learns?
8. **How far should an agent go first?** Suggest only, or act within limits a person sets? Who is
   accountable for its acts: you, or the animal's primary researcher in wl.works?
9. **Should weight and water be copied into each session's record at its start**, or joined from
   wl.works when the history is analyzed?
10. **Should sessions run outside wl-xcon count**: a MonkeyLogic session on the swapped rig (ADR-0005
    keeps the swap at the rig-contract and data layer), whose record carries what changed but not who
    or why, or other labs' shared data?

## Appendix A. Where each wl-xcon fact was read

- Record files and their fields: `wl_xcon/record.py` (`SessionRecord.trial`, `trial_start`,
  `configure`, `run_row`, `warning`, `parameter_change`, `control`, `refusal`, `welfare_note`).
- What `config.json` holds: `taskd.Session._fixed_config`. The run rows: `taskd.Session.run` (start
  row with `layers`, `resolved`, `bounded`, `preflight`; end row in its `finally`). The change row:
  `taskd.Session._apply_staged`, which passes `sequence`, `name`, `was`, `now`, `by` and `run`, and no
  instant or trial number.
- The write path and its checks: `taskd.Session.set`; its welfare-critical status: architecture.md,
  "The other two `taskd` functions are `Session.set`, whole, and `Session._schedule`".
- Actors: `wl_xcon/actor.py`. The planned system actor: engine spec §11.3, §13.9, §20 item 6.
- Build C's scope: engine spec §3.5, §13-18, §24. Procedures' carried state: engine brainstorm notes,
  element 12. The kiosk's record: S13 §5. The rig's link to wl.works: architecture.md, "Data outputs
  and lab integration"; `docs/pending-wl-works-amendments.md` (the withdrawn plan fields, 2026-10-01).
- wl-preproc's readers: `wl_preproc/events/rigtrials.py`, `events/rigruns.py`, `nwb/intervals.py`,
  `eye/xcon.py`; a search of `wl_preproc/` for the other file names found no reader.
- wl.works' welfare tables: `src/db/schema/welfare.ts` (`animal`, `animal_weight`,
  `animal_reference_weight`, `animal_water_entry`, `animal_water_requirement`, `animal_observation`).
- wl-xtasks (`ffeb62f`) holds no task code yet; wl-touchtrain (`9d377c9`, registry lifecycle
  `scaffolded`) holds no design yet.

## Appendix B. Sources, as checked on 2026-10-09

In `docs/references/library.bib` (cited above by key; each re-read here for the claims made):
[@ibl2021standardized] full text (PMC8137147, including Appendix 1, table 1);
[@berger2018standardized] abstract only (PubMed 29142094; the publisher's full text refused the
request); [@calapai2017cagebased] full text (PMC5352800); [@womelsdorf2021kiosk] full text (the
publisher's page); [@nwb2026nwb] the format page (version 2.11.0) and `core/nwb.file.yaml` on the
schema repository's `dev` branch.

Not in the library (full references in Sources below): Bak et al. 2016, full text; Swaminathan and
Joachims 2015, full text of sections 1-4; Gottesman et al. 2018, full text of sections 1-5; Klasnja et
al. 2015, full text (PMC4732571); Murphy 2005, abstract (PubMed 15586395); Roy et al. 2021, abstract
(PubMed 33412101); Tong et al. 2025, full text (PMC12448964); Parasuraman et al. 2000, abstract (PubMed
11760769); Ly et al. 2024, full text (bioRxiv's source XML) and the extension's README; the Alyx source
file; MonkeyLogic's runtime-functions page; the BIDS page and its changelog; Directive 2010/63/EU on
EUR-Lex, Articles 24 and 40.

**UNVERIFIED or not read:**

- Gottesman et al.'s shorter comment, "Guidelines for reinforcement learning in healthcare" (Nature
  Medicine 25:16-18, 2019, doi 10.1038/s41591-018-0310-5), was not readable (paywall); the note cites
  their 2018 preprint, which was read, instead.
- Berger et al. 2018 beyond its abstract, including how deviations from the protocol were recorded.
- Whether IBL recorded experimenters' departures from the automated protocol: not found in the paper;
  their code was not read.
- The published version of IBL's data-architecture preprint (bioRxiv 10.1101/827873, abstract read;
  bioRxiv lists doi 10.1038/s41592-022-01742-6 as its publication): not opened, and not cited.
- Whether a wl.works rig name can change or be reused.

## Sources

Not in `library.bib`; each read on 2026-10-09.

- Bak, J. H., Choi, J. Y., Akrami, A., Witten, I., & Pillow, J. W. (2016). Adaptive optimal training of
  animal behavior. *Advances in Neural Information Processing Systems 29* (NIPS 2016).
  https://papers.neurips.cc/paper_files/paper/2016/hash/7fec306d1e665bc9c748b5d2b99a6e97-Abstract.html
- European Parliament and Council (2010). Directive 2010/63/EU of 22 September 2010 on the protection
  of animals used for scientific purposes. *Official Journal of the European Union*, L 276,
  20.10.2010, 33-79.
  https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32010L0063
- Gottesman, O., Johansson, F., Meier, J., Dent, J., Lee, D., Srinivasan, S., Zhang, L., Ding, Y.,
  Wihl, D., Peng, X., Yao, J., Lage, I., Mosch, C., Lehman, L. H., Komorowski, M., Faisal, A., Celi,
  L. A., Sontag, D., & Doshi-Velez, F. (2018). Evaluating reinforcement learning algorithms in
  observational health settings. arXiv:1805.12298. https://arxiv.org/abs/1805.12298
- International Brain Laboratory and others. Alyx, `alyx/actions/models.py`, `master` branch.
  https://github.com/cortex-lab/alyx
- Klasnja, P., Hekler, E. B., Shiffman, S., Boruvka, A., Almirall, D., Tewari, A., & Murphy, S. A.
  (2015). Microrandomized trials: an experimental design for developing just-in-time adaptive
  interventions. *Health Psychology*, 34S, 1220-1228. doi 10.1037/hea0000305
- Ly, R., Avaylon, M., Wulf, M., Kepecs, A., & Ruebel, O. (2024). Structured behavioral data format:
  an NWB extension standard for task-based behavioral neuroscience experiments. bioRxiv, doi
  10.1101/2024.01.08.574597 (preprint, not peer reviewed). Extension:
  https://github.com/rly/ndx-structured-behavior
- Murphy, S. A. (2005). An experimental design for the development of adaptive treatment strategies.
  *Statistics in Medicine*, 24(10), 1455-1481. doi 10.1002/sim.2022
- NIMH MonkeyLogic. Runtime functions (`editable`). Software documentation.
  https://monkeylogic.nimh.nih.gov/docs_RuntimeFunctions.html
- Parasuraman, R., Sheridan, T. B., & Wickens, C. D. (2000). A model for types and levels of human
  interaction with automation. *IEEE Transactions on Systems, Man, and Cybernetics, Part A*, 30(3),
  286-297. doi 10.1109/3468.844354
- Roy, N. A., Bak, J. H., et al. (2021). Extracting the dynamics of behavior in sensory decision-making
  experiments. *Neuron*, 109(4), 597-610. doi 10.1016/j.neuron.2020.12.004
- Swaminathan, A., & Joachims, T. (2015). Batch learning from logged bandit feedback through
  counterfactual risk minimization. *Journal of Machine Learning Research*, 16, 1731-1755.
  https://jmlr.org/papers/v16/swaminathan15a.html
- The BIDS Contributors. Brain Imaging Data Structure, version 1.11.2 (2026-09-29), "Behavioral
  experiments (with no neural recordings)".
  https://bids-specification.readthedocs.io/en/stable/modality-specific-files/behavioral-experiments.html
- Tong, W. L., Murthy, V. N., & Reddy, G. (2025). Adaptive algorithms for shaping behavior. *PLOS
  Computational Biology*, 21(9), e1013454. doi 10.1371/journal.pcbi.1013454
