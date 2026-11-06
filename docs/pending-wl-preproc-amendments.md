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
end of this file, before the note that is not an ask. **And one from engine build C3, opened 2026-10-30**:
what varied in each trial and block, and the change log grown, the last section of this file.

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

*Amended 2026-10-30 (engine build C3)*: each `clear`, `drum` and `training` row above is also written to
`parameter_changes.jsonl`, as a change row of the same kind (the C3 section below), and stays in `controls.jsonl`
exactly as above until you read and time the change log's rows (our XC-442). The `training` rows, in either file,
remain the only record of when "first answers only" was on.

## The ask

**Read them into the published dataset**, so an analysis can tell what each trial paid (`counting`; it is not the answer, which `outcome` says), tell a spent trial from an answer, follow the realized sequence, tell a trial run under a training aid, and see each condition's counts, its forgiven debt and whether it was flagged as possible avoidance. Both readers tolerate the fields today (a trial line's extra fields are ignored; an end row is read with `.get`), so nothing breaks before this is done.

## What is deliberately not asked for

No new escape, code or marker: nothing here is strobed. No change to the six required trial fields.

---

# OPEN — engine build C2b: each run's plan, how each block ended, and each trial's structure

Opened 2026-10-20 by engine build C2b ([its plan](superpowers/plans/2026-10-19-engine-c2b.md), Task 1), backlog XC-404, **before any of these fields is written**: the build writes this first, and wl-preproc is told before the build merges. Read against wl-preproc's `wl_preproc/events/rigruns.py` (the `start`/`end` row filter and its `.get` reads), `rigtrials.py` (`_FIELDS`), `schema/core.py` (`stop_kind` stored as text up to 64 characters) and `schema/events.py` (a block's type kept only where every trial of it names one `block`), in wl-preproc's main at `b74d4f3` as read 2026-10-19.

## What changed on our side

**A run plays one of its task's plans** (the PI, 2026-10-07: "the operator chooses at run start among the plans it declares"), or the plain run of N trials as before. Each `runs.jsonl` **start** row gains `plan`, the plan's name in its task (whose content hash `versions.task` already carries), or null for the plain run, and `plan_form`, the plan as declared, in the form the content hash reads it (each declaration by its class's name and the fields it sets away from their defaults), so a reader can tell a balanced plan from a random one without the task file; its `blocks` lists the plan's block types **as declared**, in the plan's order -- not the run's sequence of blocks, which the end row's `blocks_run` and `block_ends` give -- and its `trials` is null for a planned run, whose lengths are its plan's. Each **end** row gains `block_ends`: a list, one per block the run opened, in order, of `{block, ended, by, after_trial, block_in_session, position, passed_at}` -- `ended` one of `rule` (its own end rule met), `time` (its own time limit), `fall_back` (a training progression's fall-back rule), `next` and `back` (a person moved the run on a block, or back one, `by` naming who), `run_time` (the run's own time limit ended the run with it open) or `run` (the run ended with it open otherwise: a stop, the out-of-cage limit, a fault, or the plan unable to go on); `after_trial`, the run's last trial before it ended, counted from 0 as `trial_index` is; `block_in_session`, the block's number in the session's stream, the one its `BLOCK_START` carries, **or null for a block that ran no trial**, which is neither opened nor closed in the stream and takes no number (a plan's block can be over before it draws one); `position`, its place in the run's sequence of blocks, from 0 -- a training progression's stage, which a fall-back or a person's *back one* moves back by one; and `passed_at`, for a training progression's top stage, where the animal keeps working once its rule is met, the trial after which that rule was first met, null otherwise -- since `BLOCK_END` carries no reason and the stream cannot. The end row gains `end_reason` too, beside `stop_kind` `completed`: `plan_done` (its plan's last block ended), `plan_time` (the plan's time limit), `stalled` (every block type the plan has was opened since its last trial and each ended before it drew one) or `cannot_draw` (a block that can draw nothing and does not end); null for a run that ended any other way. Its `shortfalls` gain `because` `time`, what a block still owed when its own time ran out, and `run_time`, what the open block still owed when the run's time ran out (the PI, 2026-10-19: "recorded as not run, 'time ran out'"), each forgiving nothing. A run that a plan's time limit ends, or whose plan can draw no further trial, ends `completed` with a sentence saying so -- **never `limit`, which stays the out-of-cage welfare stop's** (a plan's time limit is not a welfare limit). Each `trials.jsonl` line gains `structure`, the trial structure it played (its condition's, or the task's default), and `overridden`, the names of the values its condition set that a live edit replaced (engine spec §14.7; empty otherwise). `controls.jsonl` gains `next_block` and `back_block` rows (`block`, the block left; `to`, the one moved to; `dropped`, the condition whose drummed trial was waiting to come back and was dropped by the move, or null). **Their `event_code` is null**: a move closes a block that ran a trial with `BLOCK_END` (code 3), as an advance does, but every block that ends on its own strobes one with no row, so the n-th row naming 3 would not be the n-th 3 in the recording, and each move row is timed by its own `at`. **Each block still opens with `BLOCK_START` before its first trial and closes with `BLOCK_END` after its last, every trial of it naming one `block`, its type** -- a cyclic plan's second visit to a type is a new block with its own number -- so a block's type is kept as today. No new `runs.jsonl` row kind. **And a setting's value that is a polar position** (since true visual angle merged on 2026-10-20, a setting whose value is a whole position may offer `task.Polar` values, and a plan's condition may set one) **is recorded, wherever a value is written -- each `trials.jsonl` line's `params`, a start row's `layers` and `resolved`, a `parameter_changes.jsonl` row's `was` and `now` -- as an object: `{"eccentricity": 8.0, "direction": 45.0, "x": 5.675270513286652, "y": 5.675270513286651}`**, eccentricity and direction first, in degrees of visual angle, the direction counter-clockwise from rightward (engine spec §5.1), and beside them the per-axis degrees the screen is drawn in, converted exactly (`geometry.polar_deg`: `atan(tan e cos θ)` across and `atan(tan e sin θ)` up), so a reader that wants (x, y) has it without converting (the PI, 2026-10-20, "Both, polar first"). Its keys are `Polar`'s own field names and the (x, y) every per-axis position is written in. A value written as an (x, y) pair is a two-item list, as today, and every existing task writes its positions so. This is not XC-399 -- each shown stimulus's true eccentricity and polar angle on its trial line, which comes after C2b -- only how a setting that holds a polar position is written. **Revised 2026-10-30** (the PI, "0 to 360 everywhere" and "Empty at center"): that direction is written as the task wrote it but from 0° to 360°, so `Polar(8, -90)` is written 270, and null at eccentricity 0, so `Polar(0, 45)` is written with a null direction, normalized as the XC-399 ask below says.

*Amended 2026-10-30 (engine build C3)*: `overridden` also names a setting a person held over its condition's own
range; each `block_ends` entry gains `varied`, `planned` and `counts`, and `shortfalls` gain `because` `designed`; and
`plan_form`, still in the form the content hash reads, now carries a block type's own draws (`Block.draws`), a
condition's own ranges and a block type's factorial (`Block.factorial`), as declared and unexpanded (the start row's
`generated` lists what each factorial expanded to). Each is in the C3 section below.

## The ask

**Read them into the published dataset**, so an analysis can tell which plan a run played and how it was declared, how each block ended (its rule, its time, a fall-back, a person's move, the run's time, or the run's end) and which block in the stream each entry is, why a completed run ended, what a timed-out block left unrun, which structure each trial played, and which trials ran with a value a live edit put over their condition's. Ask too, as wl-preproc's to decide: whether `plan` should be a column on `core.RunRecord`, a field on `ListedRun` and the NWB runs table (each `extra="forbid"`, so wl-works' validators must accept it before it appears), and whether the NWB `blocks` table should carry a block's end reason. Both readers tolerate the fields today (a start or end row is read with `.get`; a trial line's extra fields are ignored), so nothing breaks before this is done.

## What is deliberately not asked for

No new escape, code or marker: a plan's name, a block's end reason and a structure travel in the session folder, never the stream (wl-preproc's own rule, `contracts/events.py`: "parameter VALUES do not"). No change to the six required trial fields. **No condition numbers yet**: `CONDITION` (0x8003) stays unsent and the condition's name is in the trial line, until the lab's condition registry numbers conditions for good (the PI, 2026-10-19, "Wait for the registry"; XC-197; engine build C5).

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

---

# OPEN — saccades in true visual angle, online and offline together (new, 2026-10-19)

Opened 2026-10-19 on the PI's decision, backlog XC-398. Yours to accept, amend or refuse.

## The finding

The PI ruled on 2026-10-19 that a stimulus is forward-calculated for its own location, never from an average
pixels-per-degree ("it changes subtly as a function of eccentricity of the stimulus and the exact distance the observer
is from the monitor"). Calibrated gaze, here and in wl-preproc's reading of it, is in degrees per axis: a point `(X, Y)`
cm from straight ahead at distance `D` is `(atan(X/D), atan(Y/D))`, so its direction is `normalize(tan x, tan y, 1)`.
Distances taken in those coordinates shrink off center: a 2° step straight up from (20°, 0°) is 1.879° of visual
angle, from (30°, 0°) 1.732°. wl-xcon's gaze windows and stimulus-spacing checks now measure the true angle between
directions (its branch `true-angle-windows`, `geometry.separation_deg`). **Saccade detection does not**, on either side,
and on purpose: our `saccade.py` mirrors your detector exactly (Engbert–Kliegl velocities per axis, the elliptic test,
and `_amplitude` as your `measure.amplitude`'s `np.hypot`), so online and offline detection agree (S5 §5), and your 1°
microsaccade cut assumes it. Asked whether to keep that match or move both to true angle, the PI answered **"Change
both repos"**: "Ask wl-preproc to move its detector and size to true angle too, then change ours to match; contract
tests in both change."

## The ask

**Move saccade detection and saccade size to true visual angle, and say what you choose so wl-xcon matches it to the
sample.** A proposal, yours to change:
1. **Size**: the angle between the first and last usable samples' directions, `atan2(|u × v|, u · v)`.
2. **Velocity**: each sample's angular velocity in the local frame at the window's center sample, its rightward and
   upward axes (as wl-xcon's `viewport.local_true_angle` builds them), so the elliptic test keeps its two thresholds,
   horizontal and vertical noise still scaled apart.
3. **The 1° microsaccade cut**, read in true angle (unchanged at the center; larger in screen degrees off center).
4. **The shared contract fixtures** that pin our detector to yours, updated on both sides in one exchange: you change
   and publish first; wl-xcon matches and its contract tests read your new fixtures.

Nothing on the wire changes. Until both sides move, the two keep matching as they do today.

**Widened the same day** (the PI, asked how far true angle goes in the eye-movement coding, answered **"Events and
every sample"**): each detected saccade and fixation also carries its **true direction** (in the eye's frame at its
start; `atan2(dy, dx)` on the screen's axes bends off center) and its **endpoints' true eccentricity and polar angle**,
`atan(√(tan²x + tan²y))` and `atan2(tan y, tan x)`; and **each eye sample carries its true eccentricity and polar
angle** beside its per-axis position. The rig's own eye records follow your definitions (XC-400). And, separately,
**each shown stimulus's true eccentricity and polar angle** will be on its trial's row (XC-399): its field names and
shape come to you before they are written.

**Your reply (2026-10-19):** a written spec first, since `np.hypot` also sits in six other detectors and the seven-way
agreement, the main sequence and stored detections read the same coordinates; and versioned contract fixtures, v1 the
per-axis behavior (which our `tests/test_saccade.py` reads instead of importing your live code, before anything
changes), v2 the true-angle one beside it, never replacing it. *(2026-10-19: v1 is vendored here at `tests/fixtures/wl-preproc/saccade-v1.json` from `10ea913` and pinned by SHA-256; `tests/test_saccade.py` no longer imports your detector.)*

**The range of every angle, relayed 2026-10-30 and adopted** (the PI, 2026-10-30, "0 to 360 in both repos" and "Empty at center", relayed to you the same day): your true-angle spec (`docs/superpowers/specs/2026-10-30-true-angle-saccades-design.md`) adopted it as its amendment 1 (`dc3ef56`, 2026-10-30): every stored angle in [0°, 360°), a position's or an endpoint's polar angle and an event's direction alike, `atan2`'s result in degrees mod 360, and 0 where that rounds to 360; the polar angle NULL at zero eccentricity, and an event's direction NULL for a zero displacement. The rig's own eye records follow it (XC-400). **A setting's number stays the number it holds**: one you publish from `params` as a trials-table column is not normalized, even where a task uses it as a direction, since neither repo can tell it is one; the rig warns the task's author at load to write it from 0 to 360 (`direction-outside-0-360`, the PI's "Warn at load" of the same day), and each stimulus's entry in `stimuli` (below) carries the direction from 0° to 360°.

---

# OPEN — XC-399: where each shown stimulus was, in true eccentricity and direction, on its trial's line (new, 2026-10-28)

Opened 2026-10-28 on the PI's decision of 2026-10-19 (**"Record both, tell wl-preproc"**), backlog XC-399 (built; your reading of it is XC-416), **before any of these fields is written**. Written, not yet sent: the controller sends it to wl-preproc's session before the build that writes the field merges (it is stacked on engine build C2b). Revised the same day after its review (a timeline, entries never drawn, positions that cannot be resolved, the vergence offset), before anything was sent. Read against wl-preproc's `wl_preproc/events/rigtrials.py` (`_FIELDS`, the six fields a line must carry; every other field is ignored) and `nwb/conditions.py` (`trial_columns`, one trials-table column per setting in `params` **that varies across the trials**, which `nwb/intervals.py::_setting_columns` names) through this worktree's `wl-preproc` link, which is **a local export from 2026-10-02, not your main**; C2b's ask above read your main at `b74d4f3` (2026-10-19) and found `_FIELDS` the same. **Revised 2026-10-30** on the PI's answer to the direction's range, which this ask had left pending: every direction is written from 0° to 360°, and none at eccentricity 0 (`direction` and the example below).

## What changes on our side

Positions are per screen axis, `(x, y)` = `(atan(X/D), atan(Y/D))`, so `√(x² + y²)` overstates how far out a stimulus is off the axes: 28.28° for 27.24° at (20°, 20°), 42.43° for 39.23° at (30°, 30°). **Until now no trial line said where its stimuli were**: a position was in `params` only where a setting held it (`target_x` and `target_y`, or since C2b a whole position, REC-25), and a literal one -- the fixation point's (0°, 0°), every object of an array -- was in the task file alone.

**Each `trials.jsonl` line gains `stimuli`**: a list with one entry each time the trial put a stimulus on the screen (a `Show`) or changed one already there (an `Update`), in the order they took effect, **only those on the screen for at least one frame of the trial**: a `Show` or `Update` on the transition that ends the trial would take effect on the frame after its last, and one that its presentation's `Hide` took effect with (a `Show` and a `Hide`, or an `Update` and a `Hide`, on one transition) was on it for no frame, so neither has an entry:

```json
"stimuli": [
  {"name": "fix", "kind": "show", "frame": 1, "off": 61, "changed": null, "drawn": true, "unresolved": null,
   "eccentricity": 0.0, "direction": null, "x": 0.0, "y": 0.0},
  {"name": "target", "kind": "show", "frame": 85, "off": null, "changed": null, "drawn": true, "unresolved": null,
   "eccentricity": 27.23631347517073, "direction": 45.0, "x": 20.0, "y": 20.0},
  {"name": "target", "kind": "update", "frame": 97, "off": null, "changed": ["opacity"], "drawn": true,
   "unresolved": null, "eccentricity": 27.23631347517073, "direction": 45.0, "x": 20.0, "y": 20.0},
  {"name": "search", "kind": "show", "frame": 85, "off": null, "changed": null, "drawn": true, "unresolved": null,
   "eccentricity": 0.0, "direction": null, "x": 0.0, "y": 0.0, "target": 0,
   "objects": [{"eccentricity": 8.0, "direction": 0.0, "x": 8.0, "y": 0.0}, ...]}
]
```

**Every entry carries these eleven fields** (an array's and a per-eye stimulus's add the fields below them):
- **`name`** (text): the stimulus's name in its task, the one `Hide`, `Update` and its window use.
- **`kind`** (text): `"show"`, a `Show` put it up, or `"update"`, an `Update` changed it while it was up.
- **`frame`** (integer): the trial's frame from which it was so, counted from 1 at the trial's first frame, as the trial loop counts (the frame a `Show` makes it visible, the frame an `Update` first differs). **A `Show` and an `Update` can take effect on one frame** (the `Update` in the same transition as the `Show`, or in the state it enters): both have entries at that frame, in that order, and the `Show`'s describes the screen for no frame -- what was shown is the `Update`'s. Not a time: frames are matched to the recording by flip-patch edges from `TRIAL_START` (engine spec §8.4), which the screen log will carry (build F).
- **`off`** (integer or null): the first frame of the trial on which its presentation -- the stimulus from the `Show` that put it up to the `Hide` that took it down, an `Update` belonging to the presentation it changed -- was no longer on the screen, after a `Hide`; **null when it was on through the trial's last frame** (a `Hide` on the transition that ends the trial included). Half-open, as a duration is a subtraction: an entry describes the screen from its `frame` up to, not including, the next entry of the same presentation (an `Update`) or its `off`, whichever is first, or the trial's end. So a gap trial (the fixation point's `off` before the target's `frame`) and an overlap trial (its `off` null, or after) read differently.
- **`changed`** (list of text, or null): for an `Update`, the fields it set, in this order among `at`, `looks`, `disparity`, `eye`, `layer`, `opacity`, `at_left` and `at_right` (an `Update` that moved nothing repeats the position, and this says what it did change); null for a `Show`.
- **`drawn`** (true, false or null): **whether its appearance is something to draw, not whether it reached the screen** -- **false for a `Blank`** (a catch trial's stimulus: a `Show` of nothing, recorded where it was placed); **null when its appearance is a setting with no value** (the reference detection task leaves `target_appearance` to the run); true otherwise. Nothing draws a trial's screen before the display process (build E), and a stimulus whose position could not be resolved has null `x` and `y` beside `drawn: true`.
- **`unresolved`** (text or null): null when everything in the entry resolved; otherwise why not -- that its position, an array's objects or its target **could not be read** (a value that is none of its kind, as `wlx run --set` can bind one), or **`"setting 'set_size' has no value"`** where one names a setting with no value -- and the fields it could not give are null. (A run whose position, set size, ring radius, phase or target index names a setting with no value is refused before it starts since 2026-10-30, XC-415, so no run of today's writes the second.) **A line is never lost to a position**: a trial that ran and paid has its line.
- **`x`, `y`** (degrees): the cyclopean per-axis position, `(atan(X/D), atan(Y/D))`; a position the task wrote as `Polar(e, θ)` converted exactly, `x = atan(tan e·cos θ)` and `y = atan(tan e·sin θ)`, as REC-25 writes a setting's polar value. **In direct view it is exactly where the screen draws the stimulus** (both eyes see one screen, the vergence offset is 0 and a disparity is refused there). **Through the stereoscope** no image is drawn at it: the left eye's image is drawn at `x − d/2 + v` and the right's at `x + d/2 − v`, `d` its disparity (in `params` or the task file) and `v = atan(E/D)` the vergence offset, `E` and `D` being `config.json`'s `setup.half_ipd_cm` and `setup.viewing_distance_cm` (engine spec §5.4).
- **`eccentricity`** (degrees of visual angle): its true angle from straight ahead, **`atan(√(tan²x + tan²y))`**.
- **`direction`** (degrees, or null): its polar angle, counter-clockwise from rightward (engine spec §5.1: 0° right, +y up), **`atan2(tan y, tan x)`**, written **from 0° to 360°**: the angle mod 360, then 0 where that gives 360.0 (a tiny negative angle, −1e-15 say, is 360.0 mod 360 in float64), as your spec's amendment 1 of 2026-10-30 normalizes it, so the two repos agree to the sample -- straight down is 270, never −90, and leftward 180. **Null at eccentricity 0**, where the position is the origin and has no direction, decided exactly (the eccentricity written is 0), with no tolerance. The PI, 2026-10-30, asked "Today a task that writes 270 degrees sees 270 on the console but -90 in the record": **"0 to 360 everywhere"** ("As tasks write it, e.g. 270. One form in the task, the console and the record"), **"0 to 360 in both repos"** (your database and NWB files too), and **"Empty at center"** ("The record writes no direction at eccentricity 0, and the console shows only '0°'. Matches wl-preproc.") Until then this ask said (−180°, 180°], pending him.
- **How they are computed**: by `geometry.shown_polar` -- `geometry.polar_of_deg`, then the direction normalized as above by `geometry.shown_direction` -- `polar_of_deg` taking `atan2(√(u_x² + u_y²), u_z)` and `atan2(u_y, u_x)` of the direction `u = (sin x cos y, cos x sin y, cos x cos y)`, which is `(tan x, tan y, 1)` scaled by `cos x cos y`: the two formulas above, for every position a screen shows (|x|, |y| < 90°), equal to rounding (about 10⁻¹⁴°). **Always from `x` and `y`**, never copied from the task: a stimulus written `Polar(10, 135)` reads `eccentricity` 10.0 and `direction` 135.0 only to rounding. Where a setting holds the whole position, its value is in `params` as REC-25 writes it: as written, its direction from 0° to 360° and null at eccentricity 0 (REC-25's revision of 2026-10-30). **A setting that holds a number is in `params` as the number it holds**, even where the task places a direction with it (`Polar(8, P("dir"))`, `dir` = -90 gives `params` -90 beside this entry's 270); the rig warns the task's author at load to write such a setting from 0 to 360 (`direction-outside-0-360`; the PI, 2026-10-30, "Warn at load").

**An array's entry adds two**:
- **`objects`**: a list, entry `i` its object `i` -- the object the screen calls `<name>.<i>` and its window `<of>.<i>` -- each `{eccentricity, direction, x, y}` as above (one an appearance setting holds included, when the run sets it); the array's own fields are its center. The objects sit on a true circle of its radius about its center (STE-28), so each is `radius` from the center in true visual angle, not in `(x, y)`. Null when they cannot be placed (`unresolved` says why).
- **`target`** (integer or null): the index in `objects` of the object the array declares its target (`Array.target`, 0 unless set; every array has one); null when it cannot be read.

**A stimulus drawn by per-eye positions** (on the stereoscope only; no reference task has one) has null `eccentricity`, `direction`, `x` and `y`, since nothing is drawn at a cyclopean position, and adds **`left`** and **`right`**: each eye's own position as drawn (engine spec §5.4: that eye's own direction, **after the vergence offset**), each `{eccentricity, direction, x, y}` in that eye's own frame. **A per-eye array** keeps `target` at the top level of its entry, one index for both eyes, and has its `objects` inside `left` and `right`, each eye's ring about that eye's position, none at the top level. **They include the vergence offset** (+`v` on the left eye, −`v` on the right, `v` as above), so they are not comparable with a cyclopean entry until it is taken off. An eye given no position (which the load check refuses) is null.

**The position is cyclopean**: a disparity is not applied to `x` and `y`. A trial that showed nothing has an empty list; a trial that faulted writes no line, as today. The six required fields are unchanged.

## The ask

**Read `stimuli` into the published dataset**, so an analysis takes each stimulus's eccentricity and polar angle from its trial's line instead of computing `√(x² + y²)`, and can tell when each was on the screen. Yours to decide: how a list per trial is published (the trials table holds one value per trial per column; a JSON column, a column per stimulus name's first entry, or a table of its own keyed by trial and frame); and whether your eye events' endpoints, which your saccade spec gives the same two formulas (the section above, "Widened the same day"), should take the same names, `eccentricity` and `direction`, so a saccade's landing and the target it went to are read by one name. Both readers tolerate the field today (a trial line's extra fields are ignored), so nothing breaks before this is done.

## What is deliberately not asked for

No new escape, code or marker: positions travel in the session folder, never the stream (your `contracts/events.py`: "parameter VALUES do not, since they always travel with the session directory"). No change to the six required fields or to `params`. Not the screen log (engine spec §8.5, build F), which will carry every change's frame and full resolved description: this is only where each stimulus was, and when.

# OPEN — a setting's value that is an appearance (new, 2026-10-28)

Opened 2026-10-28, **before any such value is written**: found by the review of wl-xcon's XC-399 branch, and older than it.
Read against wl-preproc's `origin/main` at `bbdfa0e` (2026-10-20), with `git show`: `wl_preproc/events/rigtrials.py` (a
line's `params` must be an object; its values are not read one by one), `wl_preproc/nwb/conditions.py` (`trial_columns`,
`block_conditions`, `_summarise`), `wl_preproc/nwb/intervals.py` (`_setting_columns`), `wl_preproc/events/rigrecords.py`
(`read_rig_records`: a `parameter_changes.jsonl` row's `was` and `now` kept as JSON text with sorted keys, `_json`, into
`core.ParameterChange`'s `mediumtext` columns) and `wl_preproc/nwb/rig_record.py` (`_add_changes`: the NWB file's
`processing/rig_record/parameter_changes` table, `was` and `now` as that JSON text).

## What changed on our side

**A task's setting may offer appearances as its choices**, which is how "circles among squares" becomes a value applied
between trials rather than a new task: the reference task `fixation_detection`'s `target_appearance` offers a disc and a
square, and `visual_search`'s `target_appearance` and `distractor_appearance` offer discs and squares in its red and
green. A setting may equally hold a piece of one -- a color, a contrast, or a `Look`'s shape, fill, edge or outline --
when an appearance names it by `P`. **Until now a run with one chosen faulted writing its start row** (the value is not
JSON), before its first strobe, so no record holds one. **Such a value is now recorded, wherever a setting's value is
written** -- each `trials.jsonl` line's `params`, a `runs.jsonl` start row's `layers` and `resolved`, a
`parameter_changes.jsonl` row's `was` and `now` -- **as an object: the declaration's class by name and every one of its
fields**, `{"class": ..., "fields": {...}}`, nested declarations written the same way. It is the form wl-xcon's task
hash reads a declaration in (`declarations.canonical`, the form of a start row's `plan_form`) with one difference:
**every field is written, those at their defaults included**, where the hash leaves a default out, so a reader never
needs the defaults of the wl-xcon that wrote the line. **A setting the appearance refers to stays a reference by its
name**, `{"class": "P", "fields": {"name": ...}}`. Its value is found where that setting's value is: in a trial line,
the same line's `params` entry of that name; in a start row, the same row's `resolved` entry (`layers` holds only the
values each layer gave, so the name may be in another layer than the appearance); and for a `parameter_changes.jsonl`
row, which holds only the setting it changed, the `params` of each trial line the change applies to, from the first
trial after the row's code in the recording on, since every change made between two trials applies at once to the
trial after them. The reference task's disc, as a trial line's `params` holds it (keys sorted, as every line is
written):

```json
"target_appearance": {"class": "Disc", "fields": {"color": {"class": "Gray", "fields": {"cd_m2": {"class": "P", "fields": {"name": "target_luminance"}}}}, "contrast": null, "size": 1.0}},
"target_luminance": 40.0
```

Its square is the same with `"class": "Square"`. A class is named as wl-xcon's vocabulary names it (`Disc`, `Gray`,
`DKL`, `Weber`, `Look`, `Flat`), an enum as `{"enum": ..., "value": ...}`, and a tuple as a list. **A choice's index is
deliberately not written**, alone or beside it: a number there would become a number column and be summarized by its
least and greatest, which says nothing about a disc or a square. A number, a word, an (x, y) pair and a polar position
are written as before (the polar position as in the C2b section above). This applies wherever a setting's value is
recorded, today and in any row added later.

## The ask

**Say whether this is the form you want to publish.** Nothing on your side has to change for it to be read: `rigtrials`
takes any `params` object, and `conditions.py` writes a setting that is not a number as JSON text with sorted keys --
in the trials table's `setting_target_appearance` where it varies across a session's trials, among a condition's
constant `settings` or its varying values' distinct list otherwise -- so the disc above is published as the text of its
object; `rigrecords.py` keeps a change row's `was` and `now` as the same JSON text, and `rig_record.py` publishes it in
the `parameter_changes` table, so a change of appearance there names its luminance by reference, its value in the trials
table when the luminance varies, or in the conditions table's constant `settings` when it does not. If you would rather publish an appearance otherwise (its class alone in a column of its own, say), it is yours to
decide; the record keeps every field either way.

## What is deliberately not asked for

No new escape, code or marker: parameter values travel in the session folder, never the stream (your own rule,
`contracts/events.py`: "parameter VALUES do not"). No change to the six required trial fields.

---

# OPEN — engine build C3: what varied in each trial and block, and the change log grown (new, 2026-10-30)

Opened 2026-10-30 by engine build C3 ([its spec](superpowers/specs/2026-10-30-engine-c3-design.md), approved by the
PI that day, [§10](superpowers/specs/2026-10-30-engine-c3-design.md#10-the-record-and-wl-preproc);
[its plan](superpowers/plans/2026-10-30-engine-c3.md), Task 3), backlog XC-383 (its C3 part) and XC-441, **before any
of these fields is written**. The build's first task writes this section, and it is sent before the build merges.
It also answers your own later ask 2 of 2026-10-18 for build C3: "the file name and row shape of the grown change
log" (your `docs/pending-wl-xcon-amendments.md:85`). Read against wl-preproc's `main` at `4bd10f1` (2026-10-30), with
`git show`: `wl_preproc/events/rigtrials.py`, `events/rigruns.py`, `events/rigrecords.py`, `events/rigtiming.py`,
`schema/core.py`, `schema/events.py`, `schema/main_sequence.py`, `nwb/conditions.py`, `nwb/intervals.py`,
`nwb/gather.py`, `nwb/rig_record.py`, `contracts/protocol.py` and `listing/entry.py`. Every line number below is at
that commit. **This section amends the C2a section above**, because clears and the two switches are written to the
change log too, **and widens the C2b section's `overridden`**. Neither section has reached your `main` (your
handover names neither at `4bd10f1`; our XC-365 and XC-404), so all three go to you together. **One thing here
differs from the spec**: a draw is recorded with every field, its defaults included, not in the form the task's
content hash reads (its §10, "in the hash's form"), so a reader never needs the defaults of the wl-xcon that wrote
it. The hash and `plan_form` keep their form.

## What changes on our side

**Values drawn at random each trial**
([§2](superpowers/specs/2026-10-30-engine-c3-design.md#2-drawn-values-in-a-task),
[§3](superpowers/specs/2026-10-30-engine-c3-design.md#3-the-non-aging-wait)). A task may draw a setting each trial
from one of these distributions:
- a uniform range, `Uniform`;
- a weighted set, `Weighted`;
- a normal cut to a range, `TruncatedNormal`, cut to the setting's declared range unless it declares its own;
- a prepared list, `Listed`, played in shuffled passes unless it says "in order";
- a non-aging wait, `NonAging(minimum, mean, maximum)`: the minimum, plus a wait whose chance of ending is the same at
  every moment. A wait drawn past the maximum is drawn again, so every wait falls between the shortest and the
  longest.

The task declares a default (`Task.draws`), which a block type may replace (`Block.draws`), and a condition may draw a
setting from a range of its own. **Each drawn setting declares what a repeat of its trial takes, a drummed repeat
included: the same value (`same`) or a fresh one (`fresh`).** Each draw comes from a generator keyed by the run's
seed, the trial and the setting, kept apart from the scheduler's. So a run replays from its start row's `seed` and the
change log. `wlx run` given no seed now draws one and records it; until now it used 1. A drawn value is in the trial
line's `params`, as every value is, so **today it reads exactly like a value its condition set** (the table below).
A non-aging wait's declared `mean` is the mean of the constant-hazard wait before redrawing, so the waits' realized
average is lower than the declared `mean`. These numbers describe the declared distribution, not the rig: durations are
not yet converted to frames, and the realized interval before the stimulus is not yet recorded.

**Conditions made from factors**
([§4](superpowers/specs/2026-10-30-engine-c3-design.md#4-conditions-from-factors)). A block may declare
`Factorial(factors, exclude, target)`. At load it expands into ordinary conditions, each named from its levels in the
factors' declared order, for example `"target_contrast=0.1, side=left"`. That name is the trial line's `condition`, as
any condition's name is. A level may be a number, a choice, a position, or a range of its own. **A condition's name
longer than 200 characters is warned at load** (`long-condition-name`): past 200 a person cannot clear it from the
console, and past 255 your main-sequence table gives it no group (the table below).

**Designed orders** ([§5](superpowers/specs/2026-10-30-engine-c3-design.md#5-designed-orders)). A block may play one
of two designed orders:
- **sequence-balanced**, `SequenceBalanced(depth, cycles)`: a de Bruijn sequence of its conditions played `cycles`
  times, drawn from the run's seed, and drawn again each time the block opens. **Each cycle is the linear de Bruijn
  sequence** (the PI, 2026-10-31): with `n` conditions, `n` to the power `depth` trials plus `depth - 1` (17 for 4
  conditions at depth 2, 66 at depth 3), so each pair of conditions in a row, a condition after itself included (at
  depth 3, each triple), occurs exactly once in every cycle. **The first `depth - 1` trials of each cycle are a
  lead-in** that only precedes what follows: each such trial's `planned` says so (`lead_in`, below), so an analysis
  can drop it. The block ends when its sequence is played out or its number of trials is run, whichever comes first,
  and owes nothing then.
- **priming**, on one setting the block names (its `feature`): either a set chance that the next trial repeats the
  value of the last trial whose stimulus appeared, or runs of one value whose lengths are drawn, each followed by a
  switch to another value. A run's length counts only the trials whose stimulus appeared (`shown`). A priming block
  ends on its number of trials or its time limit, and its conditions owe no number of trials.

By default a trial that breaks is not played again, and the sequence goes on. In a sequence-balanced block the lost
place is recorded as a shortfall (below). A priming block loses no place, since a break before the stimulus is not a
trial of its run and a break after it is a shown one, so it writes no shortfall. A block may choose "again at once"
instead: the broken trial comes straight back with the same planned place, and past the task's repeat limit it is
moved past as any repeat is, a shortfall `because` `cap` or `rig` as the C2a section describes.

**Live edits and eased trials** ([§6](superpowers/specs/2026-10-30-engine-c3-design.md#6-live-edits),
[§7](superpowers/specs/2026-10-30-engine-c3-design.md#7-eased-trials-and-a-blocks-rule)). Each of these acts takes
effect from the next trial:
- A person's value now replaces a draw too: the task's, a block's, or a condition's own range.
- A *hand back* button gives a setting a person holds back to what gives it in the open block: its conditions, its
  draw, or the run's value.
- A person may change the numbers of the draw the open block uses, its own or the task's, for the rest of the run
  wherever that draw applies: a uniform's ends; a truncated normal's mean, spread and cut; a wait's shortest, average
  and longest. The trials stay drawn. A condition's own range, a weighted set, a prepared list, a direction setting's
  range and the draw of a setting the task declares not live are not changed live in C3.
- A *revert* goes back to an earlier moment of the run, a change in it or the run's start: the values a person held
  then, and the ranges in force then. A setting held now and not then is handed back. It never touches a reward size,
  the out-of-cage limit, a count or a training aid.

A trial that a live change made easier is an **eased** trial. Whether a change eased it is read from each setting's
declared meaning. An eased trial is left out of moving up: of the answers its block's criterion judges (the criterion
that ends a block, or a training stage's pass rule) and, in a training progression, of its stage's number of trials
and its targets. Otherwise it counts as any trial does: toward moving back (a plan's fall-back rule), and, outside a
training progression, toward its block's own number of trials and its condition's target, so such a block can end on
eased trials. And a sequence-balanced stage below a training progression's top moves up when its sequence is played
out, eased trials or not (the PI, 2026-10-31, "Only warn at load"; the load warns of such a stage,
`sequence-stage-moves-up`). *Corrected 2026-11-07: the ask as sent on 2026-11-06 said an eased trial does not count
toward a block's end rule, and that a stage is never ended on eased trials; neither is so, as built or by the spec's
[§7](superpowers/specs/2026-10-30-engine-c3-design.md#7-eased-trials-and-a-blocks-rule).*

**Each `trials.jsonl` line gains four fields**, beside the six you require and those the sections above add:
- **`drawn`** (an object): each setting drawn for this trial, and where its range came from:
  - `"task"` or `"block"`, while that draw is as declared;
  - `"condition"`, for a condition's own range;
  - the integer `change` id of the live act that put the range in force (a `range` row, or a `revert` that restored
    a changed range; the change log is below).

  It is `{}` when nothing was drawn. A setting that a person held for the trial was not drawn and is not listed. **On
  a repeat, drummed or not** (the trial it repeats is its `repeat_of`), a `same` setting takes the value of the trial
  it repeats and is listed with that trial's source, even after the range has changed live; a `fresh` setting is
  drawn again and listed with the source in force. A `same` setting that the repeated trial did not draw, because a
  person held it, is drawn again.
- **`live`** (a sorted list of text): the settings a person held at a value for this trial, over its conditions, its
  draw or the run's value. It is empty otherwise. **`overridden` stays the subset of them that a condition gave**, and
  since C3 that includes a condition's own range. So C2b's meaning is unchanged for a value a condition sets. A live
  range is not in `live`: its trials stay drawn, and `drawn` names the range's change id.
- **`eased`** (a sorted list of text): the settings whose live change kept the trial out of moving up. It is empty
  otherwise.
  - **A trial whose `eased` is not empty was left out of moving up**: of the answers its block's criterion judged
    (a block's own criterion, or a training stage's rule, which decide `block_ends`' `ended` `rule` and its
    `passed_at`, in the C2b section), and, in a training progression, of its stage's number of trials and its
    targets. Otherwise it was counted as any trial: its fall-back rule (`fall_back`) counted it; outside a training
    progression its block's own number of trials and its condition's target counted it, so a block can end `rule` on
    eased trials there; and the end row's `conditions` count it toward its condition. A sequence-balanced stage below
    a training progression's top ends `rule` when its sequence is played out, eased trials or not (the PI,
    2026-10-31, "Only warn at load"). *Corrected 2026-11-07: the ask as sent on 2026-11-06 said such a trial was left
    out whenever its block's end rule was judged.*
  - A clear-cut setting keeps the trial out when a person's value set it easier than the trial would otherwise have
    had it. "Otherwise" means its condition's value, the run's value or, for a drawn setting, the value the seed draws
    for that trial from the range as written (on a repeat, a `same` setting's is the value of the trial it repeats, a
    `fresh` one's drawn on the repeat's own number). A setting whose values are choices, or are appearances, is read by what
    its meaning says changing it does.
  - **A range changed live is judged as a whole** (the PI, 2026-10-31): every trial drawn from it is kept out while
    it reaches any value easier than the range the task writes allows (for a uniform, either end moved the easier
    way) or which way it moved cannot be read, mixed changes among them, and, for an expected setting, while it
    differs from the range written at all, until it is put back, by its written numbers sent again or by a revert.
    Its change row says which way it went (`meaning`'s `went`, below).
  - An expected setting keeps the trial out when a live change held it at any value other than that one, either way.
  - Where which way a change went cannot be read, a live change keeps the trial out: an animal is never moved up on
    doubt. It cannot be read only for a value read against the trial's background (a luminance, say), against another
    setting that holds no number, or against no value at all.
  - A setting declared not a difficulty setting never keeps a trial out.
- **`planned`** (an object, or null): in a designed block, the trial's planned place.
  - In a sequence-balanced block: `{"cycle": c, "position": p, "lead_in": l}`, `cycle` and `position` each counted
    from 0. `lead_in` is true on the first `depth - 1` trials of each cycle, which only precede what follows (one
    trial at pairs, two at triples), and false on the rest, whose pairs (or triples) each occur once a cycle.
  - In a priming block: `{"run": r, "switch": s, "value": v}`. `run` counts the block's runs of one feature value
    from 0. `switch` says whether this trial is the first of its run. `value` is the value planned, written as a
    setting's value is.
  - Null in any other block.

  A trial played again at once has the same `planned` as the trial that broke. Read with C2a's `previous`, `shown`,
  `repeat_of` and `at_once`, it lets an analysis set a block's planned sequence against its realized one.

**Each `runs.jsonl` start row gains three fields:**
- **`draws`**: the task's draws as declared, `{setting: draw}`, or null when the task draws nothing. **Each draw is
  written with every field, its defaults included**, as a setting's value that is an appearance is (the section
  above): `{"class": "Uniform", "fields": {"high": 0.8, "low": 0.2, "repeat": "fresh"}}`. A truncated normal is
  written with its cut, the setting's declared range where the task gives none. A range of directions is written
  from 0° to 360° (below). This is not `plan_form`'s form, which leaves out the fields at their defaults: `plan_form`
  stays the declared plan as the C2b section says, so a block's draws, a condition's own ranges and a factorial are in
  it in that form, unexpanded. Each drawn setting's `same` or `fresh` is in one or the other.
- **`generated`**: for each block type whose factorial expanded, an entry `{block, conditions, excluded}`. Its
  `conditions` lists every condition generated, each as `{name, values, target}`, a level that is a range of its own
  written in `values` as `draws` writes a draw. `excluded` lists the exclusions applied, each `{factor: level}`. It
  is `[]` when no factorial expanded, as in a plain run. The record then names every generated condition without the
  task file. *Added 2026-11-07:* a generated condition's name keeps the task's own terms for a level of a direction
  setting, a number or a range of its own (`target_dir=-90.0`, `target_dir=uniform from -45.0 to 45.0`), never
  turned to 0° to 360°, since a condition's name is the task's words, as a given value is written as given.
- **`directions`**: the names of the settings that place a position's direction (a `Polar`'s), sorted, `[]` when none.
  Each is an angle, written from 0° to 360°, so take circular statistics of it: a draw declared -45° to 45° sits near
  0° and near 360°, and a plain mean of it reads 180°.

**Each `block_ends` entry on the end row gains three fields** (XC-344):
- **`varied`**: an object naming each setting that varied in the block, each with a list of the ways it varied:
  - `{"by": "condition"}`: its conditions give it different values, or ranges of their own;
  - `{"by": "draw", "from": f, "distribution": d}`: it was drawn. One entry for each draw the block's trials were
    drawn from (each condition's own range a draw of its own): `from` takes the values a trial line's `drawn` takes,
    and `d` is that draw, written with every field as the start row's `draws` writes it;
  - `{"by": "person"}`: a person held it on some of the block's trials.

  It is read from what the block declared and did, never from the values its trials happened to get. A block that ran
  no trial has `{}`.
- **`planned`**: a designed block's planned sequence, or null for any other block. For a sequence-balanced block it
  lists the conditions in planned order, played or not: a place that no trial line's `planned` names was never played.
  For a priming block it lists each planned run as `{value, length}`, as far as the block played.
- **`counts`**: for each condition that ran a trial in the block, `{"trials": n, "overridden": k, "eased": e}`: its
  trial lines in the block, those on which a person's value overrode something its condition set (`overridden` not
  empty), and those kept out of moving up (`eased` not empty). A condition's trials still count toward it whatever a
  person did (the C2b section), so a factorial cell can be met by trials that never showed its level; these say how
  many. `{}` for a block that ran no trial.

**The end row's `shortfalls` gain `because` `"designed"`**: a planned trial in a sequence-balanced block that broke
and was not played again. Each such trial gets one entry: `trials` 1, its planned condition, `after_trial` the trial
that broke, and `by` null. It is never flagged as possible avoidance. That trial's `planned` names the place that was
lost. A priming block writes none (above). **A sequence-balanced block cut short** by its number of trials or a time
limit owes nothing, so the places it never reached are in its `planned` and in no shortfall.

**The change log** ([§8](superpowers/specs/2026-10-30-engine-c3-design.md#8-the-change-log-and-revert);
[XC-288 §3.4](superpowers/specs/2026-10-10-xc288-training-records-design.md#34-one-change-log)).
`parameter_changes.jsonl` grows into one log of every change to what the animal experiences. It keeps its name and its
rows' present fields: `name`, `was`, `now`, `by`, `run`, `event_code`, and `sequence` on a row whose act strobed
`PARAM_CHANGED`. Each row gains these fields:
- `kind`;
- `change`: an integer id, never 0, unique in the session, shared by the rows of one act (a revert's, for example);
- `at` and `at_local`: the instant it applied, on the session's anchored clock, written as a control row writes its
  instant;
- `trial_number`: the first trial it applies to, numbered as that trial's line and its `TRIAL_NUMBER` escape number
  it. That trial may never run, if the session ends first;
- `meaning`: the setting's declared meaning, an object of six keys, or null on a row that names no task setting (a
  welfare ceiling's, such as a reward size, and every `clear`, `drum` and `training` row):
  - `kind`: `"clear-cut"`, `"expected"` or `"not a difficulty setting"`;
  - `role`: `"criterion"`, `"stimulus"` or `"neither"`;
  - `raising`: what raising the value does to the task, `"easier"` or `"harder"`, or null for a setting that is not
    a difficulty setting;
  - `relative_to`: what `raising` is read against: null (the value itself), a number, another setting's name, or
    `"background"` (the trial's background), raising then meaning moving the value away from it;
  - `went`: the way this change went by that meaning, `"easier"` or `"harder"` (for an expected setting, the
    expected way, not a fact), or null where that cannot be read or the setting is not a difficulty setting. **On a
    `range` row, and a `revert` row that puts a range back**, it is the new range judged as a whole against the
    range the task writes (the PI, 2026-10-31): `"easier"` where it reaches any value easier than the written range
    allows (for a uniform, either end moved the easier way; a normal's spread changed counts so, its values moving
    both ways), `"harder"` where it moved only the harder way, null where it is the written range again or which way
    cannot be read;
  - `step`: `now` minus `was`, in the setting's unit, or null where either is not a number;
- `offered`: an empty list until a later build;
- `odds`: null until build D.

**Where a person's value, or a revert's, lands on a setting drawn or given by its conditions at that moment** (by the
open block's draw or the task's, or by its conditions, a value or a range of their own, no person holding it), **its
row writes `was` null, and `meaning`'s `went` and `step` null**: no trial held one value before it, and what the
animal saw is in each trial line's `params`.

C3 writes these kinds:

| `kind` | One row for each | `name`; `was` and `now` | Its own fields | Strobes `PARAM_CHANGED` (so carries `sequence` and that code as `event_code`) |
|---|---|---|---|---|
| `set` | person's value applied | the setting; its value before and after | none | yes |
| `hand_back` | setting handed back | the setting; the person's value, then the run's value where `to` is `"run"`, else null | `to`: what takes the setting back in the open block, `"conditions"`, `"draw"` or `"run"` | yes |
| `range` | change to a draw's numbers | the setting; the draw before and after, with every field, as the start row's `draws` writes it | `from`: `"task"` or `"block"`, whose draw it changed; `block`: that block type's name where it is a block's own draw, else null | yes |
| `revert` | setting a revert restores | the setting; what it held before, then what it holds again: a value, null for a setting handed back, or a draw as `range` writes it | `moment`: the change id of the moment it goes back to, 0 for the run's start; `from` and `block`, as `range` writes them, where it restores a range | yes, once for each row |
| `clear` | person's clearing from a condition's count | `"owed"`; what the condition owed before and after | the control row's `condition`, `block`, `rest` and `cleared` | no |
| `drum` | drumming switch | `"drumming"`; what drumming read before and after | the control row's `scope` and `block` | no |
| `training` | training switch | the training setting, `"clear"` or `"first_answers"`; off or on, before and after | the control row's `setting` | no |

**Every row names something in `name`, the three kinds also written to `controls.jsonl` included**, because your
reader leaves out a row that does not (the table below). **A row written before C3 has no `kind`. Read it as a
`set`**, the only kind there was. Each row that strobed `PARAM_CHANGED` strobed it once, so the n-th row carrying that
number still matches the n-th such code. A revert never names a bounded setting (a reward size or the out-of-cage
limit). `at` is the rig's bookkeeping, not a time on the recording's clock. It has no stated accuracy until a `tools/`
script has measured the rig's clock.

**Clears and the two switches are written to the change log too** (XC-363), amending the C2a section above. Today
your reader carries every `controls.jsonl` row, and it would leave the change log's rows of these kinds untimed (the
table below). So **C3 writes them in both files**: the control rows exactly as C2a writes them, and the change-log
rows beside them. We write both until you say you read and time the change-log rows. We will tell you before we stop
writing the control rows (our XC-442). `next_block` and `back_block` (C2b) stay control rows only.

**Directions** (the PI, 2026-10-30: "0 to 360 in both repos", "Empty at center"; and the same day, "Warn at load": a
setting's number is shown and recorded as the number it holds). Every direction the rig produces runs from 0° up to
360°, counter-clockwise from rightward, and is null at eccentricity 0: the angle in degrees mod 360, and 0 where that
gives 360.0. In C3 that covers:
- **a drawn value of a direction setting** (a number a task's position reads as its direction), in the trial line's
  `params`: a task declares the draw in its own terms, `Uniform(-45, 45)` say, and a value drawn as −30 is written
  330;
- **a range of directions**, wherever a draw is written, end by end, so its lowest may be above its highest:
  `{"class": "Uniform", "fields": {"high": 45.0, "low": 315.0, "repeat": "fresh"}}` runs from 315° up through 0° to
  45°, crossing rightward. A task still declares its lowest at most its highest, spanning at most 360°.
  In a direction draw, equal ends mean the whole turn (a span of 360 is written `low` equal to `high`), and a draw
  from one direction is refused at load: write the value.

**A value a person or the task gives a direction setting is written as given everywhere, change rows included**, as
the XC-399 section above says: a person's −90 is −90 in `params` and in its change row's `was` and `now`. So are a
condition's value and a run's starting value in `params`, a generated condition's `values` and a priming `planned`'s
`value`. Only a value the rig draws is normalized when written. The rig warns the task's author at load to write a
direction setting from 0 to 360 (`direction-outside-0-360`), but not for a setting it draws in every block of every
run, with no choices and no start outside 0 to 360, whose every value in `params` is then drawn. A whole position (a
`Polar`) is written as the C2b section says, its direction from 0° to 360° wherever it is written. On 2026-10-30 you
adopted the same rule for every angle you store (your true-angle saccades spec,
`docs/superpowers/specs/2026-10-30-true-angle-saccades-design.md`, amendment 1, at `dc3ef56` on your branch
`proof/true-angle`). Your `main` still writes a saccade's direction in (−180°, 180°] (`eye/detect/measure.py:44-53`).

## What your `main` does with each today

| What | Today | Where |
|---|---|---|
| A trial line's `drawn`, `live`, `eased`, `planned` | **Ignored.** A line must carry the six fields, and only those six are kept | `events/rigtrials.py:37`, `:71`, `:90-91` |
| A drawn value in `params` | **Read like a value the condition set.** It gets a trials-table column wherever it varies across the session, and appears in its condition's `varying` summary beside a person's values, with nothing to tell them apart | `nwb/conditions.py:98-106`, `:126-136`; `nwb/intervals.py:84-92` |
| A person's value on every trial of a condition | **Misread** as the condition's own constant setting | `nwb/conditions.py:102-103` |
| A drawn position (an object, not a number) | Summarized by at most 20 of its distinct values, with no range | `nwb/conditions.py:20`, `:62-70` |
| A generated condition's name | Kept as text and grouped by. A name longer than 255 characters gets no main-sequence group | `events/rigtrials.py:91`; `nwb/conditions.py:83`; `schema/main_sequence.py:34`, `:98`, `:228` |
| A start row's `draws`, `generated`, `directions` | **Ignored.** A start row is read only for `task`, `calibration`, `at` and `run_in_session` | `events/rigruns.py:119-124` |
| A `block_ends` entry's `varied`, `planned`, `counts`; a shortfall's `because` `"designed"` | **Ignored.** An end row is read only for `stopped_because`, `stop_kind` and `at` | `events/rigruns.py:125-128` |
| Change rows of kind `set`, `hand_back`, `range`, `revert` | Kept: each row's setting, its `was` and `now` as JSON text, and its whole line. Each is timed by its place in the count of `PARAM_CHANGED` codes | `events/rigrecords.py:166-171`; `events/rigtiming.py:140-164`, `:171`; `schema/core.py:162-189` |
| A change row's `kind`, `change`, `at`, `trial_number`, `meaning`, `offered`, `odds`, and a kind's own `to`, `from`, `block`, `moment` | Kept only in the database's copy of the line (`row`). The NWB file publishes only the setting, `was`, `now`, `sequence`, run, the kind of actor and the session time. So **a hand-back, a range change and each row of a revert are misread as changes of value**: a range's `was` and `now` read as if the setting's value had become a distribution, and a revert reads as unrelated changes | `schema/core.py:188`; `nwb/gather.py:117-120`; `nwb/rig_record.py:84-101` |
| The count wl.works is sent as "live parameter changes" | Counts every row, including hand-backs, range changes, revert rows, clears and switches | `contracts/protocol.py:530-540`; `listing/entry.py:274-275` |
| A change row without a non-empty `name` | **Refused**: reported as "not a change naming its setting" and left out. At most 20 problems are kept per session | `events/rigrecords.py:153-155`, `:166`; `schema/core.py:86-87`; `schema/events.py:296` |
| `clear`, `drum`, `training` rows in the change log | Kept, because they are named, but **untimed**. A change row is timed only by its code, these strobe nothing, and the rig's clock fit times control rows only. As control rows today, they are kept, timed through that fit, and published in the NWB `controls` table | `events/rigtiming.py:171`, `:173-186`; `events/rigrecords.py:173-179`; `nwb/rig_record.py:104-125` |
| A direction in [0°, 360°), null at eccentricity 0 | Nothing on `main` reads a direction from the rig's record. A position is JSON text. A null where a number column holds numbers becomes NaN, the same as an absent value | `nwb/conditions.py:130-136` |

## The ask

1. **Read the trial line's `drawn`, `live`, `eased` and `planned` into the published dataset, beside `overridden`**
   (XC-404). With them an analysis can:
   - tell a condition's design from a drawn nuisance and from a person's override;
   - leave eased trials out of a measure of learning, as the rig leaves them out of moving up;
   - set a designed block's planned sequence against its realized one.

   Today your reader keeps six trial fields (`events/rigtrials.py:37`) and summarizes every varying setting per
   condition (`nwb/conditions.py:98-106`), so drawn, condition-set and overridden settings read alike. You accepted
   the overridden flag on 2026-10-11 (your `HANDOVER-wl-expcontroller.md:287`) and have not built it. How to publish
   these fields is yours to decide. In particular, decide whether a condition's `settings` and `varying` should leave
   out, or mark, the values a person set (`live`) and the values drawn (`drawn`), which today read as the condition's
   own.
2. **Read the start row's `draws`, `generated` and `directions`, each `block_ends` entry's `varied`, `planned` and
   `counts`, and the
   `"designed"` shortfall**, beside the C2a and C2b fields (XC-365, XC-404). Whether the NWB `blocks` table should
   carry `varied` is yours to decide, as is whether it carries a block's end reason.
3. **Read the change log by its `kind`, and publish `kind` and `change` beside the setting in the NWB
   `parameter_changes` table**, with a kind's own `to`, `from`, `block` and `moment`. Then a hand-back, a range change
   and a revert are not read as changes of value, and a revert's rows read as one act. Say, too, whether wl.works'
   count of "live parameter changes" should count only the `set` rows.
4. **Time a change row that strobed nothing as you time such a control**: through the rig's clock fit, by its `at`.
   `events/rigtiming.py:173-186` does this for control rows only. Until it does so for change rows too, the clears'
   and switches' rows have no session time in the change log, which is why we write them in both files. Tell us when
   we may stop writing the control rows.

Your readers tolerate everything here today except a change row without a `name`, which we will not write. A trial
line's extra fields are ignored, a start or end row is read with `.get`, and a change row is kept whole.

## What is deliberately not asked for

No new escape, code or marker. A drawn value, a range, a hand-back and a revert travel in the session folder. The four
kinds that change a setting strobe `PARAM_CHANGED`, as a person's value does today; clears and switches strobe
nothing, as now. No change to the six required trial fields. No condition numbers: `CONDITION` stays unsent until the
condition registry (engine build C5). And none of these yet:
- reasons for changes (C4, `reasons.jsonl`);
- a preset applied, and a task revised (C5);
- interludes (C6);
- condition edits at the rig (the build right after C3);
- the timed event log (C7);
- a random pick's odds (D).

No timing claim: the change rows' `at` is wall-clock bookkeeping, and a non-aging wait's declared numbers describe a
distribution, not the rig.
