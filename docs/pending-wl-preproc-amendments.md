# Amendments to wl-preproc

Delivered 2026-10-11 as a dated section of wl-preproc's `HANDOVER-wl-expcontroller.md` (`7183347`); answers are read there.

**Reply read 2026-10-11 (wl-preproc `1dda41b`): see "ANSWERED 2026-10-11" below.**

**Updated 2026-10-11.** Of the four asks opened in August, **all four are done**; each is marked below
with wl-preproc's evidence, and the headings are left as they were. What is open now is XC-288's ask
(XC-321), the asks of engine spec §21 and the older backlog items, all delivered 2026-10-11 and listed
in the section "delivered 2026-10-11" below; the XC-026 note is accepted (see its section).
The first three were opened 2026-08-31 while designing S2
([`superpowers/specs/2026-08-31-S2-event-vocabulary-design.md`](superpowers/specs/2026-08-31-S2-event-vocabulary-design.md)),
and the fourth (`read_online_map`, now `read_xcon_map`) was added before XC-026. Written here rather than applied
there, following that repository's own convention for `wl-works`. The first three were read
against `wl_preproc/contracts/events.py` at commit `f7fb10a` (2026-08-31); the
2026-10-11 section is wl-preproc's own reading of its source, not rechecked here.
**And one from XC-026, opened 2026-10-01**: what a resumed session's stream holds, and **one
from XC-288, opened 2026-10-10**: the change log, reasons, timed events and pauses, both at the
end of this file, before the note that is not an ask.

**Of the first three (all since done), two were free, and the third was small.** Items 2 and 3 change no numbers and
no wire behaviour — one records an ownership split in a docstring, the other corrects a
premise. Only item 1 touches the frozen interface, and it adds one escape without altering
any existing value.

**Note on timing.** `wl-preproc` was committed to on 2026-08-31 and a
`spec/second-order-calibration` branch merged the same day, so this is written against a
moving target. If any of it collides with work in flight, this document is the losing side.

---

# OPEN — one new escape: `PARAM_CHANGE`

> **DONE — wl-preproc added it: `contracts/events.py:157`, commit `5ea827b` (2026-08-31), as listed in its 2026-10-11 handover.** The text below is the ask as written.

## The ask

```python
class Escape(IntEnum):
    ...
    PARAM_CHANGE = 0x8005

PAYLOAD_WORD_COUNTS[Escape.PARAM_CHANGE] = 2   # uint32 change sequence number, high word first
```

No existing value changes. The payload is a **pointer, not content**: a monotonic sequence
number that joins to a record in the session directory carrying what actually changed.

## Why it has to be in the stream at all

wl-xcon supports live parameter editing between trials — changing, for example, a
search array's eccentricity from 0 to 10 degrees while the animal is working. That is a
stated must-have, and it is also the most likely way this controller quietly damages a
dataset: a change made at trial 300 is invisible at analysis time unless it was recorded.
Our own risk register calls it P16.

Every trial already carries a complete resolved parameter snapshot in the session record, so
the *content* is safe. What the snapshot cannot give is **the moment on the recorded clock**
where the discontinuity falls. A `SimpleEvent` code would supply the moment but not which
change it was, which is ambiguous the instant two parameters move in one inter-trial
interval.

## Why a pointer and not the values

Following this file's own reasoning for `BLOCK_START`: content belongs in the stream when the
recording must stay interpretable without external files. A block's task type qualifies —
"self-describing in the recording even when the ELN is wrong or late." Parameter values do
not: they always travel with the session directory, and encoding floats into 16-bit words to
duplicate them would cost precision and buy nothing. Two words for a uint32 also reuses the
exact shape `TRIAL_NUMBER` and `CONDITION` already use, so it needs no new payload idiom.

## What it costs

One enum value, one dictionary entry, and one line in the schema export. `decode_stream`
needs no change — it reads `PAYLOAD_WORD_COUNTS` and checksums generically.

---

# OPEN — record the ownership split, because two manifests currently contradict

> **DONE — answered 2026-09-01 ("we agree", in wl-preproc's `docs/CHECKPOINT.md`); commit `7e100ab`; `wl.yaml:522` now declares `event-code-protocol`, so the codec is visible to `wlo`.** The text below is the ask as written.

## The finding

`wl-exptasks/wl.yaml` publishes `task-event-vocabulary` and states *"Nothing is allocated yet"*
and *"wl-preproc reads event handling from here rather than defining it."* Neither is true:
`contracts/events.py` defines the range allocation, the markers, the task-type namespace, the
escapes and the framing, and freezes them.

`wlo validate` cannot catch this. It checks that a published artifact name resolves to exactly
one publisher — and it does. It has no way to know the description is false.

## The ruling taken on our side (2026-08-31)

Ownership splits on **decodability versus meaning**: if getting it wrong makes the recording
*undecodable* it is wl-preproc's; if it makes the recording *uninterpretable* it is
wl-exptasks'.

| Range / artifact | Owner |
|---|---|
| Framing, escapes, checksum, payload word counts, DVA encoding | **wl-preproc** |
| `Marker` 1–255 | **wl-preproc** |
| `TaskEvent` 256–4095 | **wl-exptasks** |
| `TaskTypeCode` 100+ | **wl-exptasks** |
| Task-specific / condition 4096–32767 | **wl-exptasks** |

## The ask

Nothing moves and nothing is renumbered. `TaskEvent`'s four existing values
(`FIXATION_ACQUIRED` 256 … `CALIBRATION_END` 259) **stay exactly where they are** — ownership
moving is not permission to renumber, and this file's own warning about renumbering silently
relabelling prior recordings applies with full force.

What is asked is that the split be **stated** in `TaskEvent`'s docstring, so the next person
to add a code knows which repository allocates it. `wl-exptasks`' manifest is being corrected on
our side in the same change.

If you would rather keep `TaskEvent` 256–4095, say so and we will allocate ours in
4096–32767 instead. The layering matters more than which side of it that range falls on.

## And one thing the registry cannot see at all

`wl-preproc/wl.yaml` publishes seven artifacts — session manifest, job request, health
response, behaviour camera sidecar, done marker, the syncbox log header mirror, and the NWB
session. **The event codec is not among them.** So the most load-bearing cross-repo contract
in the recording path is invisible to `wlo`: nothing can ask who owns it, nothing appears in
`wlo dependents`, and a change to it notifies nobody.

Declaring it — something like `name: event-code-protocol`, `kind: python-model`, `at:
wl_preproc/contracts/events.py`, `stability: stable` — costs one manifest entry and makes the
edge visible. We have deliberately **not** added a matching `consumes` entry on our side yet,
because consuming an artifact nobody publishes is a `V014` warning rather than a recorded
dependency. Ours lands the moment yours does.

---

# OPEN — the DVA comment's premise, under ADR-0005

> **DONE — commit `ae1ece1` (2026-08-31) restated the comment.** The text below is the ask as written.

## The finding

`encode_dva`'s comment reasons about why positions are transmitted in degrees rather than
pixels:

> "The task already knows the geometry because it renders the stimulus, and MonkeyLogic holds
> `ScreenInfo.PixelsPerDegree`."

**The conclusion is right and nothing needs to change on the wire.** But under our ADR-0005,
MonkeyLogic will not be deployed as the working controller — wl-xcon is the day-one
stack, and the MonkeyLogic swap is maintained only at the rig-contract layer.

## The ask

Restate the second clause. The argument survives intact without it, because it never depended
on MonkeyLogic specifically: **whatever renders the stimulus knows the geometry, and the
pipeline deliberately holds none.** wl-xcon holds per-eye viewport geometry,
per-display-mode deg/pixel, and a versioned gaze mapping, so it satisfies the premise at least
as well.

One caveat worth carrying across, since it did not exist when that comment was written: our
rig has two setups sharing one screen — direct view, where both eyes see the whole panel, and
a removable **split-screen mirror stereoscope** in front of it (`2026-09-28-direct-view-design.md`).
Through the stereoscope a single screen carries two viewports with their own centres and their
own folded path lengths, and the display runs in one of two modes with different deg/pixel.
Degrees remain the right unit — more so, not less — but "the" pixels-per-degree of a rig is not
a single number, which is an argument for never putting pixels on the wire.

---

# OPEN — `read_online_map` needs a reader for a controller that is not MonkeyLogic

> **DONE — the reader exists as `eye/xcon.py::read_xcon_map` (line 242), named for our controller rather than for MonkeyLogic. The name `read_online_map` below is the ask's name for it and is kept as history.** The text below is the ask as written.

## The finding

`eye/calibration.py::read_online_map` takes a `.bhv2` path and parses a MonkeyLogic binary.
`CalibrationSource.ONLINE`'s own docstring already anticipates this: *"The behavioural control
system will change, and whatever replaces MonkeyLogic will also save a calibration."*

Under wl-xcon ADR-0005, MonkeyLogic is not deployed, so **there will be no `.bhv2` to
read** and `ONLINE` — the source you rank above carry-forward, because it is the map the animal
was actually held to — would be unavailable for every session.

## The ask

A second reader, for a small text file written into `expcontroller/`. We write it, you read it;
neither side reverse-engineers the other's binary.

Every field below is one you already compute or consume, so the format asserts nothing new:

| Field | Why |
|---|---|
| `model` | `CalibrationModel`: `affine` or `second_order` |
| `coefficients`, per eye | in `basis()` order — `[1, dx, dy]` or `[1, dx, dy, dx², dy², dx·dy]` |
| `raw_definition` | stated explicitly as `CR1 − CR4`, so a future change on either side is loud |
| `targets` | the constellation actually presented, in degrees |
| `conditioning` | as computed by `_conditioning`, so you can check our arithmetic against yours |
| `rms_residual_deg` | as `validate_map` computes it |
| `mapping_version` | ours; every trial cites it, and a recentre or drift correction increments it |

**We fit your basis to your raw vector.** The shape of the map is not ours to design — §2 of our
S5 spec adopts `purkinje_vector` and `CalibrationModel` verbatim rather than defining a second
model that could drift from yours.

## A second, smaller offer: per-trial gaze staleness

`EyeQuality` holds `tracking_loss_fraction` and `blink_rate_hz` per eye, described as *"a lower
bound on how much of a session is unusable."* We can supply a third quantity of the same kind,
which the recording alone cannot give you.

Every gaze decision we make records **how stale the sample it used was** — the tracker's own
`DataQuality` column says detection succeeded, but not that the sample the controller acted on
was fresh. When a stall overlaps a gaze-contingent epoch the trial now proceeds and is marked,
rather than aborting, so a per-trial staleness summary is what keeps that decision honest: it
arrives as a column an analysis must actively drop rather than a flag it can miss.

Offered rather than asked for. If it does not belong in `EyeQuality` it will sit in our own
behavioural table and you can ignore it.

## One thing your conditioning table changed on our side

Your measured constellations (`MIN_CONDITIONING`, and the table above it) show a **ring of eight
scoring 0.0000 on the second-order basis** — degenerate despite having more points than the fit
needs, because points on a circle make the constant, `dx²` and `dy²` columns linearly dependent.

A ring is the intuitive calibration pattern, and adopting it would have silently foreclosed the
second-order rung for every session. Our calibration block now presents a **3×3 grid** and
computes conditioning online, refusing to complete on a degenerate constellation rather than
discovering it in your pipeline. Recorded here because that table is doing work outside your
repository now, and a change to it would reach us.

---

# OPEN — a resumed session's stream: 4137, numbers that go on, and the crashed run's end

> **ACCEPTED — wl-preproc has built the run and block escapes this section depends on:** `RUN_START` `0x8006` (`events.py:162`) and the `RUN_END` marker; accepted 2026-10-01 per `docs/pending-wl-xcon-amendments.md` in wl-preproc (told to us by its 2026-10-11 handover, not checked here). The `assemble` consequence below was asked of nobody and stays recorded.

Opened 2026-10-01 by XC-026 ([its spec](superpowers/specs/2026-10-01-xc026-resume-design.md)
§6, "Told to wl-preproc once built"). Read against wl-preproc's `main` at `6a67ae2`
(2026-10-01), `wl_preproc/events/assemble.py` as it stood there.

## What changed on our side

`wlx taskd` now resumes a session whose process stopped before its animal's return: the same
session, in the same sync-box recording.

- **4137 `SESSION_RESUMED` marks a resume.** A provisional code in our `tasks/allocation.py`,
  beside 4135 and 4136; wl-xtasks owns the final number, as for those two. It is strobed once
  at each resume, when the allocation has it.
- **Numbers continue across it.** The resumed session's next `RUN_START` escape (`0x8006`)
  carries the next run number, and every block (`BLOCK_START`, `0x8002`) and trial
  (`TRIAL_NUMBER`, `0x8001`) number carries on, so one recording never repeats a trial, block
  or run number. That holds across a process crash. A power loss can lose rows a resume numbers
  from, since they are flushed and not `fsync`ed; that is our XC-210.
- **The crashed run stays unclosed**, as any run that faults does: no `RUN_END` marker (4) and
  no 4136 for it, no `BLOCK_END` for its open block, and no `TRIAL_END` for the trial cut short.
- **The head-fixed codes.** A resumed rig-fixed session strobes another `HEAD_FIXED` (4128) at
  the resume, with no `HEAD_RELEASED` (4129) between, since a run needs the head marked fixed
  and nothing recorded whether it was released across the crash. **Unless its runs were ended
  before the crash** (End session, its return not yet given): its 4129 is already in the
  stream, and it comes back waiting for its return (the PI, 2026-10-01: "Bring it back
  waiting") with no run to start, so its resume strobes no 4128. So one recording holds one or
  more 4128 and at most one 4129, after the last 4128: at the session's end, or before the 4137
  of a resume that brings it back waiting. A session ended from a restart with no resume never
  strobes 4129. Restraint bounds nothing on our side; the codes are its durable record.

## One consequence in `assemble`, for you to decide on

`assemble` closes a run left open only at the next `RUN_START` escape, at the last event before
it, and closes that run's open block there too. After a crash and a resume, the last event
before the resumed run's escape is that run's 4135, which follows the 4137 (and, rig-fixed, the
resume's 4128). So **the crashed run's `last_s`, and its open block's, span the downtime**
between the crash and the resume: minutes, or more, in which nothing ran.

The tightest bound the stream gives for the crashed run is its last event before the 4137. We
ask nothing yet: 4137's number is provisional until wl-xtasks allocates it, and reading it
would tie `assemble` to a code `contracts/events.py` does not own. Recorded so that a run's
length read from a resumed recording is not taken at face value meanwhile.

---

# OPEN — XC-288: the change log, reasons, timed events and pauses (new, 2026-10-10)

Opened 2026-10-10 by XC-288 ([its spec](superpowers/specs/2026-10-10-xc288-training-records-design.md), approved by the PI that day), backlog XC-321. The ask is in its
[§6](superpowers/specs/2026-10-10-xc288-training-records-design.md#6-where-the-records-go) and [§7](superpowers/specs/2026-10-10-xc288-training-records-design.md#7-which-build-carries-what). Not read against wl-preproc's
source for this entry; the file list below is what the rig will write, not a description of what wl-preproc
reads today beyond the spec's own statement that it reads none of these.

## What changed on our side

The rig records every change to what the animal experiences, why, and what happened inside each trial, in the
session folder, in every session ([§3](superpowers/specs/2026-10-10-xc288-training-records-design.md#3-what-the-rig-records-in-every-session)). The session folder is
what wl-preproc already ingests. These files are new or grown:

| File | Row shape (spec section) |
|---|---|
| `parameter_changes.jsonl`, grown into **one change log** | One row per setting moved; a preset is one row per setting, all sharing one `change` id. Carries `change`, the instant it applied, the `trial_number` of the first trial it applied to, its run, what (setting, from, to), its declared meaning and direction, who (a wl.works account id), what was offered, the odds when the rig chose at random (empty until a later build), and the procedure and version when one acted. **Only rows that strobe `PARAM_CHANGED` carry `sequence`**; the join to the recording is the codes' count, the n-th `sequence` row to the n-th code, until XC-008 puts the number on the wire ([§3.4](superpowers/specs/2026-10-10-xc288-training-records-design.md#34-one-change-log)) |
| `reasons.jsonl` (new) | **One row per reason, pointing at the `change` id it explains** (or at a pause's `id`), so a reason given later never rewrites a line already written. A preset's rows share one reason through their id. A change unexplained at the close is recorded "no reason given" by the rig. The code list only grows ([§3.5](superpowers/specs/2026-10-10-xc288-training-records-design.md#35-reasons)) |
| the timed event log (new) | Every state the task entered and left with its instant and why it left, and every code strobed with the instant it strobed. Instants are the session's wall clock; events inside a trial are frame offsets from the trial's start ([§3.2](superpowers/specs/2026-10-10-xc288-training-records-design.md#32-a-timed-event-log), [§3.11](superpowers/specs/2026-10-10-xc288-training-records-design.md#311-the-rigs-clock)) |
| `controls.jsonl` | Pauses, stops, resumes, marks and manual rewards, **its writers and fields unchanged; its new rows gain an `id`**, so a reason row can point at a pause ([§3.10](superpowers/specs/2026-10-10-xc288-training-records-design.md#310-what-stays-where-it-is)) |

*Amended 2026-10-18 (XC-321 ask 1, the PI's approval)*: every row of `controls.jsonl` and of `parameter_changes.jsonl` also carries `event_code`, the number its act strobed or `null` when it strobed nothing; a row written before lacks the key, which a reader takes as unknown. So `controls.jsonl`'s fields are no longer unchanged, and the change log's rows join to `PARAM_CHANGED` codes by that number, not by count alone.

## The ask

1. **Read those four into the published dataset.** Today wl-preproc reads none of them (the spec's §6). The join
   keys are the `change` id, `sequence` and `trial_number`, as above.
2. **Accept the agent's file in the session folder without reading it.** A SQLite file, one per session, built by
   the rig's tooling after the session closes ([§5.1](superpowers/specs/2026-10-10-xc288-training-records-design.md#51-one-file-per-session-sqlite)); it is rebuilt by the rig's
   tooling whenever a format version changes or later notes arrive. Ingest must not
   fail on its presence.

## What is deliberately not asked for

- **The agent's file is not read or published.** It is rebuilt from the logs and from wl.works' facts, and
  carries account ids only; it is not part of the dataset.
  *Revised 2026-10-11*: the PI, having discussed it with wl-works ("wl-works and i discussed the id thing
  being too conservative. each person will have an id, but the name should also be present in places
  where who said or did something is useful"): each person keeps a permanent account id, still the join
  key, and the person's name is recorded beside it wherever who said or did something is useful, so the
  change log's who above and the agent's file carry names as well as account ids
  ([§3.6](superpowers/specs/2026-10-10-xc288-training-records-design.md#36-who) and
  [§5.2](superpowers/specs/2026-10-10-xc288-training-records-design.md#52-what-it-holds)'s notes;
  decisions.md TRN-08). The file is still not read or published.
- **No new escape or code.** The change log joins to the stream through the existing `PARAM_CHANGE` pointer
  (the first item of this file) and the codes' count; nothing here asks for a new value.
- **No timing claim.** The rig's event-log instants are wall-clock bookkeeping; the sync box stays the timing
  ground truth ([§3.11](superpowers/specs/2026-10-10-xc288-training-records-design.md#311-the-rigs-clock)).

---

# OPEN — delivered 2026-10-11: engine spec §21 and the older backlog asks

On 2026-10-11 the PI decided to send every open ask to its sibling repositories ("Send all now"). wl-preproc's
handover section lists these eleven; it also lists, as closed, the four August asks above and the XC-026 escapes,
and Offer 2 (the online detector as an eighth registry entry), which had no reply and stays an offer, not a task.
Where a number is given it is the backlog's. wl-preproc did not verify that its ingest tolerates an unknown
SQLite file in the session folder, nor that engine build B's output is "already written"; the handover says so.

| Backlog | The ask | Blocks (wl-xcon) | Source |
|---|---|---|---|
| XC-321 | Read XC-288's training records; accept the agent's file unread | build C (+I) writes them | the XC-288 section above |
| XC-197 | Say how `CONDITION` (`0x8003`) numbers are assigned; carry an "overridden" flag in the trial table | the flag: build F; numbering: XC-207 | [engine spec §14.7, §21](superpowers/specs/2026-10-07-engine-design.md#21-asks-of-other-repositories-sent-once-this-spec-is-approved) |
| XC-323 | Read monocular and session-start calibrations (the stereoscope's monocular grids, interlude recalibrations as `CALIBRATION_START`/`END` epochs, their target positions) | build T | engine spec §12.4, §21 |
| XC-324 | The continuous mode's record shape (the once-a-second check strobes, the screen log's frame record) and the anchor code (the allocation itself is wl-xtasks', ADR-0007) | build K | engine spec §13.6, §8.4, §21 |
| XC-325 | Read `config.json`'s `session_kind` and `calibration`, each run's start row's `calibration` id, and `warnings.jsonl` | nothing (what build B writes) | engine spec §19, §21 |
| XC-326 | Align stimulus onsets through the screen log's frame record and the flip count | build F | engine spec §8, §21 |
| XC-093 | Amend the `bcam` sidecar contract for primary-triggered cameras (`digital_line`, `frame_rate_hz` required; a trigger source for "the primary triggered") | P9 | [P9 spec §7](superpowers/specs/2026-09-27-P9-camera-system-design.md#7-outside-this-repository-asks-not-assumptions) |
| XC-094 | Say whether a `pupil − CR1` fallback is carried (a second `raw_definition`, which `eye/xcon.py:73` refuses by design) or kept out | XC-006 | [S5 §1](superpowers/specs/2026-08-31-S5-eye-tracking-design.md#1-most-of-the-calibration-is-already-decided-and-not-by-us) |
| XC-095 | Correct the eye spec's `DataQuality` description (OpenIrisDPI writes 100 on every row) | nothing | [CHECKPOINT, 2026-09-27 afternoon](CHECKPOINT.md#what-moved-on-2026-09-27-afternoon-b1-merged-b2-designed-the-camera-ci) |
| XC-096 | Per-trial gaze staleness into `EyeQuality` (the offer above; "yes, in `EyeQuality`" or "no, leave it in the behavioral table") | XC-007 | [S5 §10 item 3](superpowers/specs/2026-08-31-S5-eye-tracking-design.md#10-open-items) |
| XC-098 | Who writes `session_manifest.yaml`; wl-xcon supplies `started_at_source` and `stimulus_calibration_id` by whichever route | nothing | [S10 §6 item 1](superpowers/specs/2026-08-31-S10-data-and-lab-integration-design.md#6-open-items) |

**The new ones, in a sentence each, so a reader of this file does not need the handover.** XC-323: the map's provenance
depends on reading which eye a grid was and when a recalibration ran. XC-324: a trial that lasts minutes needs
a record shape `assemble` tolerates. XC-325: a session run with an accepted warning, or in a non-experimental
kind, should be marked so in the published dataset; only carrying, not acting on, the warnings is asked.
XC-326: wl-xcon records the frame each change was strobed on, and the sync box measures the actual onset
(through the speaker tap, V7, which waits on XC-089); the two must join. No timing number is claimed here.
**Nothing here changes the frozen codec**, and wl-xcon sends nothing new on the wire until wl-preproc says it is on `main`.

---

# ANSWERED 2026-10-11 — wl-preproc's reply at `1dda41b`

Read from wl-preproc's `HANDOVER-wl-expcontroller.md` (section "2026-10-11: open asks from wl-xcon"),
its `docs/pending-wl-xcon-amendments.md` (section "OPEN — blinks in the DPI tracker, and raw eye video
from the first sessions") and `docs/superpowers/specs/2026-10-11-eye-loss-design.md` (§1, amendment 9),
all at its `main` `1dda41b`. Its later `main` `9773bda` changed only `docs/CHECKPOINT.md` and `wl.yaml`.

**Answered.**

| Backlog | wl-preproc's answer (2026-10-11) | What is left |
|---|---|---|
| XC-093 | Accepted as the sidecar's version 2: the primary camera may be named as the trigger; `digital_line` and `frame_rate_hz` required; version 1 reads as today. Built when P9 needs it. | Tell it when (XC-093). |
| XC-094 | Carry it, designed once XC-006 settles the switching rule and the second map. | XC-094 waits on XC-006. |
| XC-095 | Corrected: its eye spec §1.1 and §6 say `DataQuality` is necessary, not sufficient (100 on all 1,177,799 frames of each eye). `EyeQuality` and the validity mask now read a lost eye from the 0s OpenIrisDPI writes (branch `fix/eye-loss`). | Closed. |
| XC-096 | No: staleness stays in our behavioral table, not `EyeQuality` (one row per session per eye; staleness is per trial). | Closed. Whether the published trials table carries it is decided with XC-321. |
| XC-098 | wl-xcon writes `session_manifest.yaml` at the session folder's root. | XC-356. A session with no task PC still needs another writer, not yet settled. |
| XC-197 | (a) The task assigns condition numbers, from 1, fixed within a task version, 0 for none. (b) The "overridden" flag is accepted for the published trials table. | Tell it both field names (XC-197). |
| XC-321 | The agent's file is accepted unread: ingest never reads `xcon/`. Reading the records into the dataset is open there, not scheduled. | Extension constraint and the re-archive note (XC-357); XC-321 stays. |
| XC-323 to XC-326 | Listed as open in its handover with no answer. | All four stay as they were. |

**Corrections for XC-006,** quoted from the eye-loss spec: `DataQuality` is 100 on every frame, blinks
included, so it cannot be the switching rule; P4 is reported through every blink, and outside blinks has a
coordinate at 0 on 13,275 left-eye frames (1.13%) and 2,626 right-eye frames (0.22%), "with the pupil high in
the image ... the eye looking up, P1 at 0 too on 12,947 of the left eye's".

**Two asks back, for P10.** (a) Detect a blink from the image, not only a lost pupil, and pad its flanks
(P1 to P4 jumps stay above baseline about 40 to 50 ms before the pupil is lost and about 80 ms after it
returns), spoiled frames reaching taskd as "no sample": XC-358. It also offers, until P10 exists, to run its
offline "no sample" rule online on the samples we receive; we have not taken that up. (b) Record raw eye
video with OpenIrisDPI from the first sessions (`RecordVideo` on, `DecimateVideoRatio` 1), which it needs
for P10's validation. It asked whether the lab's OpenIrisDPI PC records it and where the files land.

**Our answer to (b), from the PI, 2026-10-12:** "Yes, it will record" (his choice: "The OpenIrisDPI PC
records raw video from the first sessions"). He gave no file location, so **the folder is not yet named**;
wl-preproc archives every file of a session folder and reads none of the video yet. Storage at 500 Hz in
both eyes is the cost it flagged. This is an answer to send, not an open item here.

---

# OPEN — engine build C2a: each trial's count and each run's shortfalls

Opened 2026-10-18 by engine build C2a ([its plan](superpowers/plans/2026-10-11-engine-c2a.md), "Calls taken in this plan", calls 10 and 11), backlog XC-365. Read against wl-preproc's `wl_preproc/events/rigtrials.py` (`_FIELDS`) and `rigruns.py` through the worktree's `wl-preproc` link, 2026-10-11 (an export, `ecd1616`), and read again 2026-10-18 in wl-preproc's main at `9f78a3e` (committed 2026-10-18), where the six required fields and the end row's `.get` reads are as described below.

## What changed on our side

Each `trials.jsonl` line keeps the six fields wl-preproc requires and gains eight beside them: `counting` (`counted`, `spent`, `owed` or `unpaid`: what the trial did to its condition's count), `shown` (whether its stimulus had appeared), `repeat_of` (the `index` of the trial it shows again), `at_once` (whether it came straight after that one), `previous` (the condition before it in its block), `drummed` (a drum's repeat), `drumming` (`block`, `run` or null) and `aids` (the training aids on as it was drawn: `drumming`, `clear`). Each `runs.jsonl` **end** row gains `shortfalls`: a list of `{block, condition, trials, because, possible_avoidance, after_trial, by}`, `because` one of `cap`, `rig` or `cleared`; `conditions`: a list of each block's per-condition `{block, condition, trials, presentations, right, wrong, right_first, owed, repeats, moved_past, possible_avoidance, drummed, failing}`, a trial and its drummed repeats one trial (the PI, 2026-10-18); and `presentations`, its lines, while its `trials` now counts trials, a trial and its drummed repeats one -- before C2a the two were equal. A trial that faulted has no line and is not in `presentations`; because a try is counted before its line is written, a run that ended in a fault can leave `trials` and the per-condition counts one try ahead of the lines. **`counting` records what the trial paid, not whether it was an answer**: under drumming every try that is not right is recorded `owed`, wrong answers included, and past a criterion block's targets, where nothing is owed, an `owed` line means "not shown again" unless drumming brought it back at once, which the next line's `drummed` and `repeat_of` say. Judge answers by `outcome`, never by `counting`. `controls.jsonl` gains three row kinds beside its existing ones, each with the common `kind`, `by`, `at`, `at_local`, `trial_index` and `run`: `clear` (a person's clearing from the count: `condition`, `block`, `rest`, `cleared`, the trials cleared, and `owed`, what the condition still owes), `drum` (a drumming switch: `scope`, `block`, the block it is for, `was` and `now`, what drumming read before and after) and `training` (a training switch: `setting`, `clear` or `first_answers`, `was` and `now`). **The `training` rows are the only record of when "first answers only" was on**: a trial's `aids` lists `drumming` and `clear` but not that setting, and it changes how a percentage rule judges the drummed tries. No new `runs.jsonl` row kind: the shortfalls ride the end row, since wl-preproc reports any row but a start or an end as a problem.

## The ask

**Read them into the published dataset**, so an analysis can tell what each trial paid (`counting`; it is not the answer, which `outcome` says), tell a spent trial from an answer, follow the realized sequence, tell a trial run under a training aid, and see each condition's counts, its forgiven debt and whether it was flagged as possible avoidance. Both readers tolerate the fields today (a trial line's extra fields are ignored; an end row is read with `.get`), so nothing breaks before this is done.

## What is deliberately not asked for

No new escape, code or marker: nothing here is strobed. No change to the six required trial fields.

---

# Not an ask — one consequence recorded

`contracts/events.py` states that Intan RHS receives the strobe only, because its 16 digital
inputs cannot carry 16 data lines plus strobe plus barcode. That is correct and we are not
asking for it to change.

Recorded here only because it constrains us in a way that was not obvious from outside:
**analysis in Intan's own timebase is blind to event identity until barcode alignment has
run**, and a real-time client on the Intan host cannot condition on event identity read from
that machine's digital inputs. Our neural plane must therefore learn trial state over the
message bus rather than off the wire. No change requested; noted so the constraint is written
down somewhere before someone assumes otherwise.
