# Amendments to wl-sync

Delivered 2026-10-11 as a dated section of wl-sync's `HANDOVER-wl-expcontroller.md` (`5ca9891`); answers are read there.

**Eight are open.** The first two were opened 2026-08-31 while designing S3
([`superpowers/specs/2026-08-31-S3-sync-integration-design.md`](superpowers/specs/2026-08-31-S3-sync-integration-design.md)),
and are the two full sections below. The other six are listed in "Also delivered 2026-10-11", below the
second: XC-089 to XC-092, which this file omitted until then, and two asks of the engine spec (§21).
The first two were read against `wl-sync` at the commit `wl-preproc` pins, `90b931e`; the 2026-10-11
section was read against wl-sync's `main` at `d933deb`, which found no answer to any of the eight.

Written here rather than applied there, following that repository's own convention. Neither
asks for a change to the barcode codec, the log format, or session identity's *form* — those
are `wl-sync`'s and this project consumes them unchanged, having deleted its own duplicates of
all three (S3 §3).

---

# OPEN — the session id is minted here and cannot be learned from anywhere else

## The finding

`wl_sync/session.py` mints `YYYY-MM-DD_NN` and its own docstring states the consumers:
*"Everything downstream — the rig directory layout, the ELN, wl-preproc — consumes it."*
`wl-preproc/contracts/paths.py` imports `SessionId` from this package and keys the whole session
directory on it, and `wl-xcon` writes into `xcon/` beneath that directory.

**But nothing offers the value to another host.** The date half is derivable; `_NN` is not. A
task controller starting up has no way to know which session it is in.

## Why guessing is not acceptable

`_NN` exists precisely so a day can be indexed, and the continuous-recording design rules that
*"a day is one session, hence `_01`; a restart joins that directory as a new segment rather than
minting `_02`."* If a task PC assumed `_01`, it would be a **second authority on session
identity** — right almost always, and silently wrong exactly when the day is unusual, which is
when a lost recording hurts most. That is the same class of error S3 spent its whole length
deleting from wl-xcon's own design.

## The ask

Some way for a rig host to read the current session id from the sync box. The smallest thing
that would work:

- the day directory name is already on disk and already authoritative, so **if the sync box's
  output root is reachable from the task PC**, reading the newest `YYYY-MM-DD_NN/` directory is
  sufficient and needs no new code at all; or
- a one-line file, or a trivial read-only endpoint, if the root is not shared.

**We have no preference and this is your call.** The requirement is only that the value be
*readable* rather than *inferred*, and that the sync box stay the only thing that mints it. If
the answer is "the output root is shared, read the directory," say so and this amendment closes
with no code written.

---

# OPEN — a day is not one session on these rigs, so something must mint `_02`

## The finding

Three definitions of "session" are live across two repositories:

| Term | Where | Meaning |
|---|---|---|
| Session | `wl-sync` continuous-recording design §3 | *"A day is one session, hence `_01`"* |
| Session | `wl-preproc` `pipeline.Session` (element-session) | keyed `(subject, session_datetime)`; `schema/eye.py` reasons about "a ~40 minute session" |
| Block | `wl-preproc` `core.Block` | *"One run of one task, mirroring wl.works `animal_session_block`"* |

And `wl-preproc` keys the session **directory** on this package's day-scoped `SessionId` while
its `Session` **table** is subject-scoped. Those coincide only if exactly one subject works per
day.

**The rig owner has confirmed that two animals will routinely work in one day on one rig**
(2026-08-31). So they do not coincide, and the continuous-recording design's *"a day is one
session, hence `_01`"* does not hold. This is not a question about whether the case can arise;
it is the ordinary case, and nothing currently mints `_02`.

## Why it reaches you

Because this package mints the identity, so whichever answer is right is a fact about
`YYYY-MM-DD_NN`, not about anyone's table. And because the rig owner is the only person who
knows whether two animals will ever work in one day.

## What wl-xcon did meanwhile

Adopted the interpretation that is correct under **either** resolution, so nothing here is
blocked on an answer: outputs live under the sync box's session id, and **every record names its
subject explicitly**, so a day containing two subjects partitions correctly with no renaming and
no inference. Our own documents now use three distinct words — day, session, block — rather than
overloading one.

## `wl-preproc`'s own contract already answers it

`wl-preproc/contracts/manifest.py::SessionManifest` sits at the root of the session directory
and carries **exactly one `subject`** — a single string, not a list — beside the `session_id` it
validates against your form. **A directory can describe one subject and no more.** So with two
animals in a day, the session id must change when the subject changes; there is no representation
in which it does not.

That is not our preference, it is a consequence of a frozen interface in a third repository, and
it holds whatever anyone here would have chosen.

## The ask

**A subject change mints `_02`.** The remaining question is mechanical rather than definitional:
the sync box runs continuously across both animals and cannot know when one leaves the chair, so
**something has to tell it.** Whether that is the task PC, wl.works, or a person pressing a
button on the box is yours to decide — but whatever it is, it is also the moment the task PC
learns the new id, so the two amendments share one mechanism.

This is now a **prerequisite for the first amendment**, not a companion to it: if `_02` can
exist, then reading "the newest `YYYY-MM-DD_NN/` directory" is not sufficient for a task PC to
learn which session it is in, because the newest directory may belong to the animal that just
finished.

---

# OPEN — also delivered 2026-10-11: XC-089 to XC-092, and two asks of the engine spec

wl-sync's handover section lists all eight as open ("Closed since last time: none"). Each is a short ask;
the long reasoning is where the source column says.

| Backlog | The ask | Blocks (wl-xcon) | Source |
|---|---|---|---|
| XC-087 | The first section above | the first run against a real sync box | this file |
| XC-088 | The second section above | nothing in a named build | this file |
| XC-089 | Assign one of the three misc analog inputs (`A_MISC1` to `A_MISC3`) to an audio verification tap, a copy of the audio output so NI records sound onset. wl-sync's own spec records the misc inputs as input-only, which suits a tap | XC-074 (V7) and the verification half of build G | [S4 §12 item 3](superpowers/specs/2026-08-31-S4-stimulus-presentation-design.md#12-open-items) |
| XC-090 | Confirm the photodiode patch geometry: wl-sync's old handover says a bottom strip of 2.18 cm at ±17°; the optics drawing now says a removable mask at ±12° (PI, 2026-09-28), 3.22 cm strips top and bottom with the screen at 50 cm, patches in the bottom strip, direct view on the same screen. "Fine as stated" is the expected answer | rig commissioning | [optics drawing §8 item 3](superpowers/specs/2026-08-31-stereoscope-optics-drawing.md#8-what-is-still-open) |
| XC-091 | Is the delivered-line record readable live, or only at session end? Nothing in-session depends on a live read since 2026-09-06. Welfare-critical on our side, so the answer is wanted stated exactly | nothing | [S8 §8 item 2](superpowers/specs/2026-08-31-S8-session-management-design.md#8-open-items) |
| XC-092 | wl-sync's `[flir_bfs_gpio]` cites the BFS-U3-200S6 page's 0.87 V low; our S0 figures come from the BFS-U3-16S2 page (0.92 V unloaded, 0.86 V loaded). We have not verified which model each rig runs | the trigger fan-out board's design check | [S0 §7.4](superpowers/specs/2026-08-31-S0-hosts-and-hardware-design.md#74-the-trigger-fan-out-board-custom-needs-a-design-check) |
| XC-327 | A two-channel line-out from the task PC card's (PCIe-6343) analog outputs, started by the task patch's next edge (engine spec §9.1, the PI, 2026-10-07): (a) a place for the two outputs to leave the rig for the speaker amplifier, possibly nothing if the card's connector can feed it directly; (b) confirmation that `PD1_COMP` reaches the task PC on a pin the 6343 can use as a start trigger (a PFI line), which wl-sync could not verify | build G (media and sound); builds A to F do not need it | [engine spec §9.1, §21](superpowers/specs/2026-10-07-engine-design.md#9-media-and-sound-n6-nr5-nr6) |
| XC-328 | For validation V1's scan-out measurement, a photodiode at the top of the screen as well as the bottom: mounted for the V1 run as a rig procedure (for example `A_PD2` moved), or a third channel, given that the board fixes `A_PD1` and `A_PD2` to the task and flip patches. The patches themselves are wl-xcon's drawing | nothing; the scan-delay term in the engine's contingent-delay figure is a lower bound until V1 exists | [engine spec §6.5, §21](superpowers/specs/2026-10-07-engine-design.md#6-when-n3-nr3), [validation V1](validation.md) |

**A finding in wl-sync's reply that corrects our spec.** The engine spec §9.1 said the line-out sits "beside the
existing speaker tap". **wl-sync has no speaker tap** (XC-089 is unassigned) and its misc BNCs are input-only by
construction (`docs/superpowers/specs/2026-08-13-syncbox-breakout-pcb-design.md:990` there: an output port "would
be a respin"). wl-sync also found no task-PC analog-output net in its `hardware/README.md`; the task PC's
connector 0 carries nine analog inputs. XC-327 (a) may therefore be new copper or may be nothing. Amended in
the engine spec on 2026-10-11. XC-286 is this repository's documents' side of the same decision.

**One correction to read before XC-090.** wl-sync's old handover still says 2.18 cm at ±17°; XC-090 supersedes
it with 3.22 cm at the ±12° mask, top and bottom strips.

---

# Not an ask — three things we now depend on, recorded so a change here is visible

None of these need to change. They are written down because `wl-xcon` now relies on
them and `wlo dependents wl-sync` would not otherwise show it:

1. **The sync box independently records every event word we strobe** (`W` records via PIO
   capture). This is why our own log is deliberately *not* a timing record and carries meaning
   only — a simplification we took on the strength of your capture, not ours.
2. **The barcode carries identity, not timing**, and one frame is guaranteed in any 2.0 s
   window. We never emit one and never derive time from one.
3. **Cameras free-run and the box records their `ExposureActive` strobes** on GPIO 26/27. So
   `wl-xcon` does not trigger cameras and does not set their rate — a role it might
   otherwise have assumed.
