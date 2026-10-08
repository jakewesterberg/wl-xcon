> Working file of 2026-10-08, committed as the record of the reference library's backfill and checks (plan: `docs/superpowers/plans/2026-10-08-reference-library.md`). Line numbers, commits and paths are as they were then; citations here are quoted as found, some of them since corrected or removed.

# Triage of the 19 places the documents disagree

Read against `origin/main` (backlog next free ID XC-276 there; `origin/engine-b` has used XC-276 to XC-278, so
the next free ID is XC-279 once it merges) and the PI's answers at the end of the engine brainstorm notes on
`origin/engine-b` ("The morning after", 2026-10-08). Passages were read, not the inventory's paraphrase.
"ENG" is the engine spec (approved by the PI 2026-10-07); "N" is the brainstorm notes.

**Tally: (a) 5, (b) 13, (c) 1.** (a) = 3, 4, 11, 12, 18; (b) = 1, 2, 5, 6, 7, 8, 9, 13, 14, 15, 16, 17, 19 (item 8 is
already scheduled in the engine B plan); (c) = 10.

Proposed backlog lines go in the section "Defects and review findings deliberately not fixed" or "debt (stale
wording)" of `docs/backlog.md`. The format is the one in its header: no " — " inside a field.

---

## 1. Panel and viewing distance — (b)

**Governing:** S0 §5.1-§5.2 (PI, 2026-09-27: the 27-inch PG27UCDM replaces the 32-inch; PI, 2026-09-28: screen fixed
50 cm from the eyes in both setups, stereoscope path about 63 cm), DV §1, OPT header.
**Stale passages:** spec map, S0 summary ("a 32-inch-class 16:9 flat OLED ... 57 cm as the build target"); controller
architecture (CA) §16 item 3 ("Answered in S0: 32-inch-class ... 57 cm build distance"). The S0 section itself says the
27-inch "changed from 32-inch-class". Not covered by XC-208 (that one is the day-plan wording) or by ENG §22.

Proposed line:
`- **XC-???** Two passages still give the 32-inch panel and the 57 cm build distance, both replaced by the PG27UCDM at 50 cm (PI, 2026-09-27 and 2026-09-28): the spec map's S0 summary and controller architecture §16 item 3. — 2026-10-08, [S0 §5.1-§5.2](superpowers/specs/2026-08-31-S0-hosts-and-hardware-design.md#51-the-panel) — waits on: nothing`

## 2. The out-of-cage limit in hours — (b)

**Governing:** S8 §5.2 item 4 (PI correction, 2026-10-01: the institution's limit is 8 hours, the 12 was wrong); already
carried into architecture.md, P9 §5 (which says the rest "still use twelve") and `tasks/eight_hour_bounds.py`.
**Stale passages:** M0 §3.1 item 4 (the re-answer row says "twelve hours", no correction note); S0 §7.6 storage
arithmetic (the 12 h table rows, "8 TB holds a 12-hour ... session"), S0 C16 and the S0 check-2 mentions (lines about
"8 cameras for 12 hours"); P9 §6 bring-up check 2; the backlog line XC-085 ("8 cameras for 12 hours"). P9 §5 notes the
S0 and check-2 staleness but no backlog line files it. Note for the editor: for storage sizing, 12 h may be kept as a
deliberate margin; if so, say so in S0 §7.6 rather than leave it reading as the limit.

Proposed line:
`- **XC-???** Twelve hours still stands where the out-of-cage limit is meant (eight, PI correction 2026-10-01): M0-REVIEW §3.1 item 4, S0 §7.6's storage arithmetic and bring-up check 2, P9 §6 check 2 and XC-085; amend each or mark 12 h as a deliberate sizing margin. — 2026-10-08, [S8 §5.2 item 4](superpowers/specs/2026-08-31-S8-session-management-design.md#52-the-session-duration-limit) — waits on: nothing`

## 3. Where an aborted trial is repeated, and which — (a)

**Filed by:** ENG §22 ("S8: §2 and §8 item 3 (repeats, counting)"), which is the amendment that applies ENG §16 items 2-3
(random later point, never the very next trial; fixation break, no fixation, tracker lost and fault repeat by default;
"superseding 2026-08-31's 'end of the block'"). The code (`scheduler.REQUEUED`, requeue onto the current draw queue) is
the thing build C replaces (ENG §24, "C + I", repeats and counting table), so no separate line is needed. Minor, not
covered: M0 §3.1 item 5 is an "Answered" row with the old policy; it is a review record, and the S8 amendment will
make it history, so leave it.

## 4. One calibration or one per panel half — (a)

**Filed by:** ENG §22, S4 bullet ("§9 one calibration per panel"). The decision is N §4 Batch 3 (PI, 2026-10-07: "One
for the panel"), which says it changes S4 §9. S4 §10 item 3 ("gamma and luminance ramp, per half") and S9 §6's ramp are
test screens, still meaningful as a check that the halves match (ENG §7.7 keeps V9's cross-half test), so they are not
stale.

## 5. The stereoscope's alignment check — (b), for the passages §22 does not list

**Governing:** ENG §12.3 and N Batch R5 (PI, 2026-10-07: two monocular 13-point grids, offsets reported, "instead of
having a threshold ... the experimenter can choose to accept", acceptance recorded; replaces N §9's 0.25 degree
tolerance). ENG §22 lists only S4 §10 (alignment target replaced by the grids, "the disparity check kept") and S5 §7.
**Stale and unlisted:** S9 §2 (the session-start gate row "Optics alignment residual within tolerance") and §6 (test-screen
list); OPT §4.5 and §7 (Nonius or vernier "run at every session start, residual recorded"); CA §11.3 (the Nonius/vernier
alignment procedure) and CA statement (the "mirror angles set vergence" paragraph) that alignment is "a calibrated rig parameter ... (Nonius/vernier)";
roadmap M5 ("per-eye alignment target"); `validation.md` V9 ("vergence alignment residual after the Nonius/vernier
procedure"). The S4 amendment in §22 will not reach these.

Proposed line:
`- **XC-???** Six passages beyond S4 §10 still call for a Nonius or vernier alignment residual held to a tolerance, replaced by the two monocular grids with offsets reported and the experimenter's acceptance recorded (PI, 2026-10-07): S9 §2 and §6, optics drawing §4.5 and §7, controller architecture §11.3, roadmap M5 and validation V9. — 2026-10-08, [engine spec §12.3](superpowers/specs/2026-10-07-engine-design.md#12-calibration-procedures-and-test-screens-n9-nr5) — waits on: engine build T`

## 6. Color without a measured calibration — (b)

**Governing:** ENG §7 items 1-3 and §12.1 (approved 2026-10-07), from N §4 Batches 1-3 and R4 (PI, 2026-10-07): a
default sRGB calibration; chromatic tasks refused on it only in recording sessions (training and piloting run with the
warning); isoluminance needs a measured calibration, with a named observer being enough; the instrument is a
spectroradiometer. Also the PI's 2026-10-07 "imperfect but acceptable" ruling (labeled default plus warnings list).
**Stale passages:** S1a §12 ("Colour without a measured `Calibration` is refused"); PIT P19 (mitigation "refused without
one", "Chromatic tasks will not load until a photometer measurement is committed", and the "photometer" wording); XC-071
(backlog: "so chromatic tasks load", "photometer"-era phrasing, and "against a macaque luminous efficiency", see item 7);
S4 §9's photometer-sweep wording. Engine build B lands the behavior but its plan names only S4 §9 and the engine spec
among docs to change.

Proposed line:
`- **XC-???** S1a §12 and pitfall P19 still say color without a measured calibration is refused and chromatic tasks will not load until a photometer measurement exists; since 2026-10-07 the default sRGB calibration loads them in training and piloting with a warning, refuses them in recording, and the instrument is a spectroradiometer (engine spec §7 and §12.1); amend both and XC-071's wording. — 2026-10-08, [engine spec §7](superpowers/specs/2026-10-07-engine-design.md#7-color-and-luminance-n4-nr4-nr5) — waits on: engine build B`

## 7. Whose luminosity defines isoluminance — (b)

**Governing:** N Batch R4 (PI, 2026-10-07: "A named observer is enough", a per-animal measured null declined), and A2's Q5
(PI, 2026-10-08: "Cone-based V(lambda), 10 degrees (Recommended)", offered against classic CIE V(lambda), follow the task,
and measured per animal): isoluminance and the DKL luminance axis use V_F,10; cd/m^2 stays on CIE V(lambda), so the record
carries two luminances. ENG §7.3 and §7.9. The inventory says R-A2 Q5 "still holds the luminosity function open"; that
research note predates the answer, so the note, not the decision, is stale.
**Stale passages:** S1a §12 ("a macaque V(lambda) is not a human one"); PIT P19 ("a human V(lambda) makes a stimulus that
is isoluminant for nobody in the room"); XC-071 ("against a macaque luminous efficiency"); CHECKPOINT line about "a macaque
V(lambda), not a human one" (history, leave). The macaque question is also answered for cones: human 10 degrees with a
macaque lens or macular setting switchable later (A2 Q4).

Proposed line (could be merged with item 6's if the controller prefers one edit):
`- **XC-???** S1a §12, pitfall P19 and XC-071 say the luminosity function must be a macaque's and that a human V(lambda) makes isoluminance wrong for everyone; the PI chose the cone-based human 10 degree V(lambda) for isoluminance and the DKL luminance axis on 2026-10-08 (A2 Q5) and declined a per-animal null on 2026-10-07 (R4); reword them to say the calibration names its observer and the record carries both luminances, and mark R-A2 Q5 answered. — 2026-10-08, [brainstorm notes, "The morning after"](superpowers/specs/2026-10-07-engine-brainstorm-notes.md#the-morning-after-asked-2026-10-08) — waits on: nothing`

## 8. The luminance bound — (b), already scheduled

**Governing:** N "The morning after" (PI, 2026-10-08, build B Q1: "80, the standard"): the reference tasks' luminance
settings run 0-80 cd/m^2 until a panel is measured, lowering the 2026-10-07 bound of 100; 40 stays the start.
**Stale:** the four tasks' `Param(... high=100.0)` and their "Bounded at 100 until V9 ..." comments, and N "Build A's
plans" (history, leave).
**Already scheduled:** the engine B plan (`docs/superpowers/plans/2026-10-08-engine-b.md`, file table and the Step "Bound the
reference tasks' luminances at the default's white") edits all four tasks and the reference test. No separate line is
needed if engine B merges; the line below is for the controller to add only if B is deferred.

Fallback line:
`- **XC-???** The four reference tasks' luminance Params still run to 100 cd/m^2 with comments saying so; the PI set 0-80 on 2026-10-08 (build B Q1). — 2026-10-08, [brainstorm notes, "The morning after"](superpowers/specs/2026-10-07-engine-brainstorm-notes.md#the-morning-after-asked-2026-10-08) — waits on: engine build B`

## 9. Tracker graces from the paper's numbers — (b)

**Governing:** S5 §4 ("Nothing downstream may quote the paper's 2% as though it described our rig") and §10 item 2
(staleness ceiling and graces "frozen only after V3(a)"), ROAD M3, CA §9.2; XC-072 already holds the V3 work that sets
the real values. The code (`eye.py` `staleness = 0.05`, `task.py` `tracker_lost = 0.05`) carries the paper's roughly 50 ms
maximum as a placeholder, which is acceptable only if labeled so; no document says it is.
**Stale passages:** S1a §13 ("defaulting to P6's **measured** stall maximum for OpenIrisDPI"; P6's figure is the paper's,
not measured on our rig); DEMO §3.3 ("the 50 ms staleness rule" stated as the rule). XC-072 does not file the wording.
No PI question: S5 already decides that these values come from V3; what is missing is the label.

Proposed line:
`- **XC-???** The 0.05 s tracker-loss grace and staleness ceiling are the OpenIris paper's stall maximum, but S1a §13 calls it P6's measured figure and the demo spec §3.3 states it as the rule; reword both as a placeholder until V3(a) sets ours (S5 §4 and §10 item 2), and label the two defaults in `task.py` and `eye.py`. — 2026-10-08, [S5 §4](superpowers/specs/2026-08-31-S5-eye-tracking-design.md#4-p6--the-stall-problem-handled-honestly) — waits on: nothing`

## 10. Leaving the target during its hold — (c)

**What the documents say:** S1a §7 lists `TARGET_BREAK` under "Breaks — a hold not maintained", and `visual_search` scores
leaving the target during its hold that way. `fixation_detection` and `adaptive_detection` score the same act
(`Exited("target")` in the verify state) as `WRONG_TARGET`, which S1a files under "response to a distractor". No dated
decision covers it. ENG §25 defers the staircase and catch-trial rules, not this labeling, but this label decides what
the staircase sees: a hold failure after landing becomes a counted wrong answer and a failure for the staircase, not a
break (ENG §16.2 leaves breaks other than the four named to the task: spent or owed). The 2026-10-06 science review
(finding 2) found this makes the staircase converge on hold reliability, not on detection threshold.

**Question for the PI (plain terms):** In the detection tasks, when the animal looks at the target but looks away before
the required hold time ends, should that trial be counted as a wrong answer (as the tasks do now) or as a broken hold
(an aborted trial that is not scored as right or wrong)?

**Options:**
1. **A broken hold, not a wrong answer (recommended).** Matches the vocabulary spec and `visual_search`; the staircase is
   moved only by real answers and by misses, so it tracks detection and not how steady the eyes are; the trial may be
   repeated or spent (ENG §16.2). Cost: a small edit to two tasks, and the task must say whether the broken hold is
   owed again.
2. **A wrong answer (today).** No edit. Cost: hold failures make the staircase harder or lower contrast artificially, and
   they are counted toward the condition's target as if the animal had answered.
3. **A wrong answer only if the eye lands on a distractor; a plain break otherwise.** Same as 1 for the detection
   tasks, which have no distractor; mention only if a future task adds one.

**Timing:** this belongs with the reference-tasks-made-right step (ENG §25, CHECKPOINT order step 3), asked there in the UI
alongside items 11 and 12's questions; it does not need an answer before engine builds A to C.

## 11. What moves a staircase — (a)

**Filed by:** ENG §25 ("What the PI decides when the reference tasks are made right: `adaptive_detection`'s staircase and
catch trials"), which CHECKPOINT's four-step order repeats as step 3 ("ask them then, in the UI; they are not in the
backlog because they are his"), plus XC-242 (nothing calls `next_params`). ENG §15 item 3 (no response is a failure by
default, each procedure declares its own) is the engine's default; the task's own rule is the deferred ask. Nothing to
add; the PI decision is to be asked at that step.

## 12. A contrast with no convention — (a)

**Filed by:** XC-242 (`adaptive_detection`'s `contrast` is never moved and read by no stimulus) and ENG §4.12 (build A
migrates the reference tasks; a bare contrast is refused once a stimulus reads one). The `contrast` Param is not an
appearance contrast today, so A1's migration passed over it. Which convention (Weber, Michelson, RMS) the staircase
contrast uses is a science choice that has no document yet; it arises with the same wiring, so ask it with item 10 and
item 11 at the reference-tasks step. Suggest that XC-242's line mention it when next touched.

## 13. What plays sound — (b), for the passages §22 does not list

**Governing:** ENG §9.1 (approved 2026-10-07; N Batch R5: audio on two analog outputs of the task PC's PCIe-6343, on its own
clock, started by the task-patch edge; a line-out asked of wl-sync, ENG §21). N §6 Batch 1's "recording card ... on the
recording's own clock" was corrected inside the notes by R5 and the ENG header says so; nothing to amend there.
ENG §22 already lists S4 (§8 audio through the task PC's analog outputs) and S6 §1 (two analog outputs allocated).
**Stale and unlisted:** architecture.md "The task PC's interface" ("Not in copper: touchscreen and audio output. Both are
host-side"); CA §3.2 (same sentence), and CA §8.5 and §9.4 on audio (a USB/host sound path tapped to a misc BNC).
The wl-sync line-out is not yet agreed, so the amendment should say "planned: two analog outputs, pending wl-sync".

Proposed line:
`- **XC-???** architecture.md's interface section and controller architecture §3.2, §8.5 and §9.4 still say audio output is host-side and not in copper; the engine plays sound from two analog outputs of the task PC's PCIe-6343 started by the task-patch edge (engine spec §9.1, PI 2026-10-07), pending a line-out from wl-sync; S4 and S6 are already in the engine spec §22. — 2026-10-08, [engine spec §9](superpowers/specs/2026-10-07-engine-design.md#9-media-and-sound-n6-nr5-nr6) — waits on: engine build G`

## 14. The calibration constellation — (b)

**Governing:** S5 §2 as amended 2026-09-05 (measured conditioning: "The constellation is thirteen targets, not nine"), kept
by ENG §12.2 (the thirteen-target constellation before any task) and by the PI's own description (N §9, "the 13-point
calibration grid"; direct view keeps the ordinary thirteen-point calibration).
**Stale passage:** S9a §2.2 ("The calibration grid (S5 §7, a 3×3 — never a ring)"). Nothing in the backlog or §22.

Proposed line:
`- **XC-???** S9a §2.2 still describes the calibration grid as a 3×3; S5 §2 (amended 2026-09-05) and the engine spec §12.2 make it thirteen targets. — 2026-10-08, [S5 §2](superpowers/specs/2026-08-31-S5-eye-tracking-design.md) — waits on: nothing`

## 15. Where the photodiode patches go — (b)

**Governing:** S3 §8, S4 §7, OPT §5 and DV §4 (the bottom strip, 3.22 cm at the ±12 degree mask; in direct view a bottom
corner under the sensor housings); OPT §8 items 3-4 keep the central strip only as a fallback. XC-090 files the
wl-sync confirmation but not this passage; XC-049 strikes S3 §10 item 5, not item 3.
**Stale passage:** S3 §10 item 3 ("candidate found (central strip from the nasal clip)").

Proposed line:
`- **XC-???** S3 §10 item 3 still names the central strip from the nasal clip as the photodiode patch candidate; the bottom strip (3.22 cm at the ±12 degree mask, and direct view's housings) replaced it in S3 §8, S4 §7 and the optics drawing §5. — 2026-10-08, [S3 §10](superpowers/specs/2026-08-31-S3-sync-integration-design.md) — waits on: nothing`

## 16. Which protocol photometers the panel halves — (b)

**Governing:** V9 (validation.md "Display geometry and per-half photometry"), S4 §11, S0 §5.4, CA §14, DV §7.
**Stale passage:** architecture.md "The display" ("Panel left/right nonuniformity ... is photometered in V1"); V1 is display
timing by photodiode. Trivial wording fix; not in §22 (which names architecture.md only for the display process, screen
description, task object, warnings list and console input).

Proposed line:
`- **XC-???** architecture.md "The display" says panel left/right nonuniformity is photometered in V1; it is V9 (V1 is display timing). — 2026-10-08, [validation V9](validation.md#v9--display-geometry-and-per-half-photometry-split-screen-stereoscope) — waits on: nothing`

## 17. A trial that reaches the five-minute cap — (b)

**Governing:** ENG §6 item 8 (the later document, approved 2026-10-07 after the two reviews): the cap is 5 minutes and a
trial reaching it "is recorded as today's `hang` category". In the code `hang` is a trial with no outcome (`taskd` records
`"hang"` when `result.outcome` is None; `scheduler.REQUEUED` has no entry for it), so it is not a `FAULT`
and is not repeated. N §3 Batch 4 ("ends as a fault") is the notes' record of the answer as first offered; the ENG
revision superseded it, and the notes are kept as written, so no edit there. The remaining gap is ENG §16.2, which does
not say whether a hang is repeated; if it were treated as a fault it would repeat a trial that just ran 5 minutes, and a
stuck task would hang again.
**Proposed engineering call (not the PI's; same standing as M0 §4's calls made without asking):** a hang is recorded, not
repeated, and counts as not answered. If the controller reads this as animal-facing, turn it into a question.

Proposed line:
`- **XC-???** State in the engine spec §16.2 whether a trial that reaches the 5-minute cap (recorded as hang, outcome none) is repeated; N §3 Batch 4 says it ends as a fault and §6 item 8 says hang, and a fault repeats by default; the proposed call is not repeated, recorded and flagged. — 2026-10-08, [engine spec §6 item 8](superpowers/specs/2026-10-07-engine-design.md#6-when-n3-nr3) — waits on: engine build C`

## 18. Variation the task docstrings describe and the tasks do not perform — (a)

**Filed by:** XC-207 (block plans and conditions from the task program, so `fixation_detection`'s six target positions and
`calibration`'s constellation walk can exist), XC-242 (`next_params`, the held-eccentricity mini-blocks), XC-183 (starting
values), and ENG §24 build C ("trials that vary: plans, conditions, drawn values, orders") with the reference tasks made
right after it. CHECKPOINT's four-step order step 2 states "every trial is the same trial" explicitly. Nothing to add.

## 19. Whether the 30-minute warning is settled — (b)

**Governing:** S8 §5.2 item 4 ("Accepted by the PI on 2026-09-20 as a starting value, so it is his figure"; it stays
configurable, `welfare.WARN_WITHIN_DEFAULT` = 1,800 s, not derived from any measurement).
**Stale passage:** S9 §3 ("The threshold is configurable and its default is a proposal, not a settled figure"). The
welfare code is not touched by a wording change.

Proposed line:
`- **XC-???** S9 §3 still calls the approaching-limit warning's 30-minute default "a proposal, not a settled figure"; the PI accepted it as a starting value on 2026-09-20 (S8 §5.2 item 4). — 2026-10-08, [S8 §5.2](superpowers/specs/2026-08-31-S8-session-management-design.md#52-the-session-duration-limit) — waits on: nothing`
