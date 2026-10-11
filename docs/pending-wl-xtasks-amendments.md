# Amendments to wl-xtasks

Delivered 2026-10-11 as a dated section of wl-xtasks' `HANDOVER-wl-xcon.md` (`0486476`, a new file there); answers are read there.

**Two are open, both delivered 2026-10-11**, the PI having decided that day to send every open ask to its
sibling repositories ("Send all now"). They come from the engine spec
([`superpowers/specs/2026-10-07-engine-design.md`](superpowers/specs/2026-10-07-engine-design.md) §3.5, §8.3, §8.4 and
§21). Written here rather than applied there, following the convention of the other three
`pending-wl-*-amendments.md` files: in the requesting repository, for the other side to accept, amend or refuse.
This file did not exist before 2026-10-11; wl-xtasks had been asked nothing in writing except the earlier
citation convention (XC-293, done by wl-xtasks in `ffeb62f`, 2026-10-08, and not re-asked).

**Read against** wl-xtasks `main` at `ffeb62f` (its `wl.yaml`: `lifecycle: scaffolded`, "The repository holds no
code yet"; `task-event-vocabulary` published with stability `planned`). That is wl-xtasks' own state as its
2026-10-11 handover read it, not rechecked here.

---

# OPEN — the task object's format

## The ask

**Information, adopt, and say now.** The PI decided on 2026-10-11 that wl-xcon's engine build C defines the
task object's format, in wl-xcon, and that **his approval of build C's plan is the agreement**: nothing is
negotiated in advance. When C's plan is approved, wl-xcon publishes the format by reference. Asked of wl-xtasks:

1. **Adopt that format when tasks move** here (XC-108).
2. **Say now**, in `HANDOVER-wl-xcon.md`, if wl-xtasks needs anything of the format that wl-xcon might not
   think of: a library layout, a manifest per task, a version rule, how a task cites
   `docs/references/library.bib` (the `ffeb62f` convention). Said before C's plan is approved it can go into
   the plan; after, it is a change request.

## What the format will carry, so wl-xtasks is not surprised

- Engine spec §3.5: one task object per task module, replacing "exactly one `Trial` per module". It holds the
  trial structures (§13.3), the plans (§13.1), the procedures (§15) and the union of their declared parameters,
  which `Session.set` validates against.
- XC-288 §4's declarations, which a task author writes and the load-time check enforces
  ([spec](superpowers/specs/2026-10-10-xc288-training-records-design.md), §4 and §7, approved by the PI 2026-10-10):
  each changeable setting's meaning (clear-cut with a difficulty direction, expected with a direction and a
  context note, or not a difficulty setting); stages in order, each with an id that lasts across the task's
  versions and a pass rule written in what the rig already counts; what "the item chosen" means and how
  reaction time is defined; the task's content hash, of content and never of a file path.

## Not asked

No task is to be written or moved yet. No design of the format is asked of wl-xtasks, and no library layout
is imposed. Whether the format's version is checked by a manifest there is for wl-xtasks to say under item 2.
**Blocks** wl-xcon build C (with I), only if item 2 turns up a need; the approval of C's plan is the agreement.
Backlog XC-329.

---

# OPEN — event codes for build F: `STIMULUS_ON`, `STIMULUS_OFF`, `STIMULUS_CHANGED`, and the anchor code

## The ask

Allocate, once and in one commit, four codes (engine spec §21, from §8.3 and §8.4):

1. **`STIMULUS_ON`, `STIMULUS_OFF`, `STIMULUS_CHANGED`**: lab-wide task codes for every task. Which stimulus each
   referred to is in wl-xcon's screen log by frame; a group is one code. A task's own onset codes (`FIX_ON`,
   `TARGET_ON`) stay as they are. S2 §5.1 puts the first two in the lab-wide `TaskEvent` range 256-4095;
   **`STIMULUS_CHANGED` is not in S2 §5.1** (it is new in the engine spec), and wl-xcon assumes it joins them.
   wl-xtasks is asked to say otherwise if it would place them elsewhere.
2. **The anchor code**: a code the continuous mode (engine spec §13.6) strobes about once a second, so the screen
   log can place a frame against the recording and confine a miscount to one interval. **The spec fixes its use
   but not its range, nor whether it is one code or a small family** (§8.4, §13.6 are silent); wl-xcon asks
   wl-xtasks to decide, with wl-preproc's framing in mind. XC-324 asks wl-preproc separately to tolerate the
   continuous mode's record shape and anchor codes.

## Who allocates what, as the sources state it

ADR-0007 (accepted 2026-08-31) splits ownership on decodability versus meaning: wl-preproc owns framing,
escapes, checksum, DVA encoding and `Marker` 1-255; wl-xtasks owns `TaskEvent` 256-4095, `TaskTypeCode` 100+, and
task-specific and condition codes 4096-32767; "wl-xcon allocates nothing itself", and a task naming an
unregistered code is refused at load. wl-preproc agreed on 2026-09-01 that 256-4095 is wl-xtasks'. The four
values already there (`FIXATION_ACQUIRED` 256, `FIXATION_END` 257, `CALIBRATION_START` 258, `CALIBRATION_END` 259)
are allocated and never renumbered. wl-xcon's `tasks/allocation.py` holds a provisional allocation in
4096-32767 only, with no `STIMULUS_*` and no anchor code; it moves with XC-108.

## Not asked

No renumbering of anything allocated. No change to wl-preproc's frozen codec: the codes ride the existing
framing. No codes for the XC-288 training records, which are not strobed. No review of the provisional
4096-32767 allocation. The token codes S2 §5.1 lists as proposed (`TOKEN_AWARDED`, `TOKEN_LOST`, `TOKEN_CASHED`;
XC-289) are **not** to be allocated yet.
**Blocks** wl-xcon build F (the stimulus codes) and build K (the anchor). Neither is the next build; C comes first.
Backlog XC-330.

---

# Not an ask — what waits on wl-xtasks, recorded so it is visible

The 2026-10-11 handover lists these against wl-xtasks without asking anything new: XC-108 (move `tasks/` and
`tasks/allocation.py` there; follows the first ask), XC-150 (the library pull before a session's first run;
wl-xcon's to build, waits on tasks existing there), XC-207 (block plans and conditions; waits on tasks there and
on the format), XC-289 (the token economy; do not allocate its codes yet), XC-142 (wl-xcon's own documents still
say `wl-exptasks` or `wl-mllib` in places; wl-xcon's to fix), and XC-294 and XC-295 (the reference library's
round trip and citation scan; wl-xcon's, though the library is shared).
