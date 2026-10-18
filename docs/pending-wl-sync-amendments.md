# Amendments to wl-sync

Delivered 2026-10-11 as a dated section of wl-sync's `HANDOVER-wl-expcontroller.md` (`5ca9891`); answers are read there.

**Reply read 2026-10-18 (wl-sync `9e60ed6`): see "ANSWERED 2026-10-18" below.** Six of the eight are
answered (XC-089 to XC-092, XC-327, XC-328); **XC-087 and XC-088, the two full sections below, stay open**.
XC-327 kept a remainder (its PFI line and the line-out's grounding); **wl-sync drew both later on 2026-10-18 and
XC-327 is closed**: see "ANSWERED 2026-10-18, later" below.

**Eight were open on 2026-10-11.** The first two were opened 2026-08-31 while designing S3
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

> **Answered 2026-10-18, except XC-087 and XC-088:** see "ANSWERED 2026-10-18" below.
> The table below is what was asked, left as sent.

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
*(Settled 2026-10-18: new copper on wl-sync's board, and `A_MISC3` is the tap; see "ANSWERED 2026-10-18".)*

**One correction to read before XC-090.** wl-sync's old handover still says 2.18 cm at ±17°; XC-090 supersedes
it with 3.22 cm at the ±12° mask, top and bottom strips. *(wl-sync struck the old figures through and replaced
them in place on 2026-10-18, `9e60ed6`.)*

---

# ANSWERED 2026-10-18 — wl-sync's reply at `9e60ed6`

Read from wl-sync's `HANDOVER-wl-expcontroller.md`, section "2026-10-18: replies from wl-sync", at `9e60ed6`
(it says it read wl-xcon at `a607414`), and from the hardware documents its commit `1e44658` changed: its breakout
spec `docs/superpowers/specs/2026-08-13-syncbox-breakout-pcb-design.md` (§9.2's pin table, §12 items 11 and 12),
`hardware/breakout/frame-time-inputs.md` §4 and `hardware/datasheet-params.toml` (`[flir_bfs_gpio]`). Its later
`main`, `16d7a71`, changed only `wl.yaml`. Every source line cited below was read at `9e60ed6` with `git show`
(2026-10-18); a figure that is wl-sync's reasoning rather than a line of its source is attributed to it.

**XC-087, XC-088: not answered.** wl-sync says both turn on one mechanism, whatever tells the box the subject
changed, which reverses its continuous-recording design's "a day is one session" (its §3) and `cli.day_directory`'s
fixed `_01`, and needs a design decision there that this reply does not make. Both stay open, with one addition
from XC-091 below: the reader XC-087 asks for is also what a task-PC read of the delivered line would need.

**XC-089: `A_MISC3` is the audio verification tap** (its breakout spec §12 item 12). Not `A_MISC1`, the only misc
input that also feeds the unfitted fourth comparator and DAC channel `VOUTD`
(`hardware/gen/gen_breakout_comparators.py:373`). Range ±5 V at ÷1 and ±10 V at ÷2 by a ganged shunt
(`gen_breakout_analog_frontend.py:107`); beyond it the signal clips, so a line-level tap fits and a tap at a power
amplifier's speaker terminals may not. **Where the tap is taken is left to us.** No anti-alias filter (only the
microphone has one, its spec §6.4): at the recording NI's 40 kHz scan, onset timing is unaffected but a spectral
measurement of the tap would alias. It reaches the recording NI as AI15, **the task PC's own card as AI8**
(Connector 0 pin 34, `gen_breakout_taskpc_digital.py:1050`), and Intan through the mux, outside its default eight.
**For us:** XC-089 closes. V7 (XC-074) names the input, and since AI8 is on the card whose analog outputs play
the sound, it can time command to tap on one clock. S4 §12 item 3 keeps where the tap is taken.

**XC-090: fine as stated, on two conditions.** Nothing on wl-sync's board depends on where the patches sit; each
comparator compares its TIA's output with a DAC-set threshold. The FDS100 is a TO-5 can 0.36 in across
(`[fds100]`), so both sensors fit side by side in the 3.22 cm strip. **Condition 1:** the photodiode gain (its
finding F3, `R38` = 180 kΩ, peak white near 2.0 V) assumes a sensor flush against a patch at least as large as its
window; a smaller patch, or a sensor standing off the panel, gives a smaller signal, which thresholds (0.5 mV
steps) can follow at bring-up. **Condition 2:** the housings are not wl-sync's; they stay with the rig build. The
old 2.18 cm at ±17° is replaced in its handover. **For us:** XC-090 closes; optics drawing §8 item 3 records both
conditions, and XC-078 carries the first to the build.

**XC-091: readable live on the box itself, and from no other host.** Stated exactly, as asked:

1. **Today nothing records the real line.** Without `--fake`, `wl-sync record` exits 2 (`wl_sync/cli.py:377`), the
   unit ships with `--fake` (`deploy/wl-sync.service:22`), and the RP1 backend is built but not wired into the run
   loop (`docs/next-session.md` §1, §2 Step A). The rest describes the run loop once it is.
2. **What is recorded.** GPIO 23 (`rwd_dlvr`, `wl_sync/pins.py:32`) is an individually captured edge line
   (`pins.py:40`): each rising and falling transition is an `E,<tick_us>,23,<level>` record, in the box's own
   microsecond count, unwrapped within one segment; neither wall time nor the task PC's clock.
3. **It is not a measurement of fluid.** `RWD_DLVR` is the reward-OR gate's output, the signal sent to the reward
   driver from our commanded line or the panel's one-shot. An unpowered or unplugged driver, an empty reservoir
   and a blocked line all still record as delivered.
4. **On the box**, any process can open the open segment read-only: the writer opens it `"x"` (create-exclusive)
   and holds no lock. Records are flushed and `fsync`ed once per emit-loop iteration (`wl_sync/segment.py:110-113`),
   a 200 ms barcode frame plus a 1 s sleep (`cli.py:266-270`), so new records appear about every 1.2 s (wl-sync's
   figure from its code, not a measurement). A torn last line is dropped and read on the next pass, as
   `wl_sync.log.read_log` does (`log.py:155`). *Amended 2026-10-18: wl-sync's Step A (`02b6271`, on its local main,
   not yet pushed; read there) wires the RP1 backend into the run loop, which now runs once a second on the wall
   clock's half seconds (`wl_sync/cli.py:247-254`), so new records appear about once a second (wl-sync's figure
   from its code, not a measurement). The same loop calls `check_health()` every iteration and writes "capture
   degraded, still recording: ..." to the journal once per episode (`cli.py:409-435`), so a dropped edge now
   reaches the journal (item 8), still not the record itself. The unit still ships `--fake` until bench
   acceptance (item 1).*
5. **From another host, nothing makes it readable**, live or at session end. It lives at
   `/data/rig1/<YYYY-MM-DD>_01/seg-NNN.log` on the box's NVMe, and NAS transfer is outside its design (its
   continuous-recording design §9). wl-sync says a task-PC read needs the same new thing XC-087 asks for.
6. **There is no session end on the box.** It records all day, and a segment closes only when the process stops,
   so a session-end read is a read of an open segment too.
7. **A restart splits the record**: a new segment, header and clock epoch. Ticks in different segments cannot be
   compared, a pulse straddling the restart is cut in two, and the gap is bounded only by the day's manifest.
8. **A dropped edge is not marked in the file.** A kernel edge-buffer overflow is detected
   (`wl_sync/rp1/gpio.py:127`) but not written to the segment; once Step A is wired it reaches the journal through
   `check_health()`. **A pulse count from the file is exact only for a day whose journal shows no dropped-edge
   error.** Marking it in the record would change the log format wl-preproc pins, and is not decided there.

**For us:** XC-091 closes and S8 §8 item 2 records the answer. Reading the record into fluid reconciliation is
XC-384, waiting on XC-087. Item 3 bears on S8 §5.1, which calls this record "the truth" about fluid; that is the
PI's to weigh, and nothing in wl-xcon's welfare text or code is changed here.

**XC-092: added, and it raises a question.** The 200S6 row was not meant to cover both: `[flir_bfs_gpio]` now
carries the BFS-U3-16S2 page's table verbatim (wl-sync read it 2026-10-18; the BFS-U3-04S2 page has the same
table), which splits every level into "No Load" and "Load". Our figures stand (0.92 V low unloaded, 0.86 V loaded,
at 5 V / 1.0 kΩ: 1.58 V of margin under 2.50 V). **The same row's loaded high is 2.29 V, below the 2.50 V
threshold.** FLIR do not define "Load". wl-sync's input is close to no load, but in FLIR's primary/secondary
scheme the primary's opto output also drives each secondary's opto input; if that is "Load", a group strobe sits
at 2.29 V and gives no frame-time edges, with nothing else complaining. Open in its `frame-time-inputs.md` §4,
pending a bench measurement with a group wired as the rig will be; wl-sync says our S0 §7.4 fan-out board, which
copies that front end at 2.50 V, inherits the question. **For us:** XC-092 closes and the question joins XC-033.
Our wiring is not the scheme wl-sync reasons from: each group's Line 1 drives only wl-sync's input (S0 §7.1
row 12, §7.4), the secondaries are driven on Line 0 by the fan-out board's '541, and the board reads the primary's
Line 2, an open-drain output on its own 5 V pull-up that the opto-output table does not cover. So an opto-input
load sits on neither line here; that is an inference from a term FLIR leave undefined, and the bench measurement
decides (S0 §7.4).

**XC-327: both parts committed for this board revision, before layout** (its breakout spec §12 item 11; sources
it read 2026-10-18: NI X Series User Manual 370784K-01, Figure A-5 and §5 "AO Start Trigger Signal", and the
PCIe-6343 Specifications 377873B-01). **(a)** The line-out goes on wl-sync's board and cannot be outside it: AO 0/1
are on Connector 0 pins 22/21 (AO GND 55/54), both of the card's connectors are cabled into the board, and those
pins are no-connect there today (`gen_breakout_taskpc_digital.py:1006`). It adds a connector body and a back-face
panel hole. The outputs are ±10 V, 0.2 Ω, ±5 mA; keeping the amplitude inside the amplifier's input range is the
engine's job. Grounding (AO GND is the card's analog return, the amplifier is mains-powered, and the board's BNCs
are isolated) is settled when the copper is drawn. **(b)** `PD1_COMP` reaches the task PC on P0.27 (Connector 1
pin 46, `gen_breakout_taskpc_digital.py:1104`), which cannot be an AO Start Trigger: NI's list names PFI 0–15,
RTSI, internal triggers and the Change Detection Event, but no P0 line. Change Detection on P0.27 is listed but
untested, with no NI latency figure, so **a second, buffered copy of `PD1_COMP` goes onto a Connector 0 PFI pin**
(P0.27 stays); it needs a new buffer channel (the bank is 8 of 8), and wl-sync will name the PFI line in its
handover when it is drawn. wl-sync also corrected its spec §9.2: all sixteen PFI lines are on Connector 0, and no
wiring moves. **For us:** XC-327 stays, amended to what is left. Engine spec §9.1's "may be new copper or may be
nothing" is settled: new copper.
*(The remainder was drawn later the same day and XC-327 closed; see "ANSWERED 2026-10-18, later" below.)*

**XC-328: a rig procedure; no third channel.** `A_PD1` and `A_PD2` are identical copper and "task patch" and
"flip patch" are roles, so for V1 keep `A_PD1` on the bottom patch and move `A_PD2`'s sensor to the top patch. The
cost is no flip-patch frame clock during that run: acceptable for validation, not for a session. The top strip is
3.22 cm and dark too. The cable is designed for 6 m and tested at 3 to 5 m (its spec §6.3.1), and the TIA is
compensated to about 50 m of coax (finding M1), so an extra screen height of lead changes nothing.
**The threshold caveat:** a display transition is slow, so a comparator edge moves with its threshold; if the two
channels' thresholds sit at different fractions of their own peaks, top minus bottom is biased. Either set both
to the same fraction of each channel's measured peak, or take a fixed-fraction crossing offline from the analog
copies (NI, 40 kHz). A misc BNC cannot be a third channel, since the sensors are passive and need the board's TIA.
**For us:** XC-328 closes; validation V1 carries the procedure and the caveat.

---

# ANSWERED 2026-10-18, later — XC-327 is drawn (wl-sync `0683ad6`)

Read 2026-10-18 from wl-sync's local `main` at `0683ad6` (not yet pushed there), with `git show`: its
`HANDOVER-wl-expcontroller.md`, section "7, later on 2026-10-18: XC-327 is drawn", and
`hardware/breakout/line-out-and-pfi-copy.md`, which cites NI's X Series User Manual 370784K-01 (May 2019) and the
PCIe-6343 Specifications 377873B-01 (May 2026) for every figure (both read by wl-sync 2026-10-18; we have not
re-read NI's documents). The line-out's reference designator, J57, is named in the handover, its breakout spec's
§12 and its netlist contract, not in the line-out document. **XC-327 closes.** What remains is wl-sync's layout.

**The PFI copy of `PD1_COMP` is on PFI 7: Connector 0 pin 38 (P1.7) of the task PC card.** It is `PD1_COMP`
through a spare channel of the `SN74LVC541A` level shifter on wl-sync's `pi-interface` sheet, then 100 Ω. P0.27
(Connector 1 pin 46) still carries `PD1_COMP` exactly as before; the control loop keeps reading it there.
- **The engine routes `ao/StartTrigger` from `/Dev/PFI7`** (the line-out document's wording; `Dev` is the card's
  device name).
- **The engine must never configure PFI 7 as an output.** The board drives it. PFI 7 was chosen because PFI 12 to
  15 are the card's default counter outputs (NI manual Table 7-9, as wl-sync cites it): a counter task with default
  routing would drive one of those pins against the board. **PFI 7 is counter 3's AUX input by default; the engine
  must leave it unrouted to any counter** (the handover's instruction; the line-out document says only that it is
  an input by default).
- **Levels at the card, wl-sync's figures:** high 3.3 V against the 6343's V_IH minimum of 2.2 V (a 1.1 V margin);
  low about 0.2 V against V_IL maximum of 0.8 V (377873B-01, Digital I/O; 50 kΩ pull-down). These are wl-sync's
  design figures from its parts' specifications, not a measurement of the built board.

**The line-out is J57, a dual BNC on the back face** (Amphenol RF 031-6575 per its BOM).
- **First port: AO 0 (left); second port: AO 1 (right)** (Connector 0 pins 22 and 21). Each passes through 100 Ω,
  which costs under 1% of amplitude into a line input of 10 kΩ or more (wl-sync's calculation). The panel labels
  will say which is which.
- **The shells are on AO GND (Connector 0 pins 55 and 54) and nothing else on the board.** NI ties AO GND to D GND
  on the card ("All three ground references, AI GND, AO GND and D GND, are connected on the device", manual Table
  3-1, as wl-sync quotes it), so the amplifier's ground meets the card's regardless; the board keeps the audio
  return current off its own planes. There are no clamp diodes.
- The card's analog outputs are ±10 V, 0.2 Ω, ±5 mA (377873B-01, Analog Output). **Keeping the amplitude inside the
  amplifier's input range stays the engine's job.**

**One change from wl-sync's 2026-10-18 proposal:** the proposal tied a Connector 0 digital ground pin so the PFI
edge returned beside its signal. Drawing it showed that would make Connector 0 a second component on both of the
board's grounds after its star-point net tie (its AISENSE is on AGND), so it was reversed: the PFI edge returns
through Connector 1's digital ground, in the parallel cable. That changes nothing for us. wl-sync's spec §9.2
therefore now has one digital line riding the analog cable, accepted for a line that changes at stimulus rate.

**Where this lands for us.** No code of ours configures an NI line yet (nothing under `wl_xcon/` or `tools/`
names DAQmx or a PFI line, checked 2026-10-18), so the two engine obligations below bind the code that will: build
G's audio output and the task PC card's configuration at rig bring-up.
1. Never configure PFI 7 as an output, and never route it to a counter.
2. Keep AO amplitude inside the amplifier's input range.

Both are recorded in [engine spec §9.1](superpowers/specs/2026-10-07-engine-design.md#9-media-and-sound-n6-nr5-nr6)
(amendment of 2026-10-18, later), with validation V7 and S4 §8 brought into line. Backlog XC-327 is removed; XC-074
now waits on the rig. Not yet verified by anyone: that a start trigger on PFI 7 starts the analog output with the
latency the design needs (no figure exists; V7 measures it) and that the card runs on the lab's Linux (pitfall P10).

---

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
