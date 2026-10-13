# Warnings over refusals: the PI's rulings on the refusal audit (XC-352, XC-353) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **Drafted 2026-10-11 to 2026-10-12 for the PI's review**, from his rule and his rulings of 2026-10-11 on the audit of every refusal in the engine (XC-352), which it builds and re-asks none of (below, "The PI's decisions it builds"). **Revised 2026-10-12 to 2026-10-13** after its engineering review (`I1` to `I7`, `M1` to `M9`, each ruled on by the controller) and **the PI's two answers of 2026-10-12**: a wait longer than any the task declares is "Allow, with a warning" (call 4), and TRN-07's "never need sign-in" means at the rig PC only (Task 12). **Its Appendix A is the welfare summary for his approval before the build merges**: `Session.set`, which is welfare-listed, changes in its task-setting branch only; nothing new is refused for a long wait, which is a warning, by his answer; `Service._open`'s code is unchanged, its docstring and one comment are reworded, and what it refuses through the build it shares narrows for three stereoscope cases (item 4).
>
> **Branch**: cut from `main`, which holds engine build C1 (`engine-c1`, at `2d8717b`) and the deployment fix (XC-355, branch `deployment-no-default`) since 2026-10-12, and built **before build C2a** (the PI's order). **This plan is committed at `docs/superpowers/plans/2026-10-11-warnings-over-refusals.md` as Task 1's Step 0**, where the decision log's and the backlog's links to it point. Every code reference here was read at `2d8717b`; the audit's own `file:line` references drift from it by up to about 40 lines, and this plan names functions, not lines. **Backlog IDs**: the base's backlog reads "Next free ID: XC-354" at `2d8717b`, and higher once the deployment fix has merged (XC-355 is its; `main` read XC-359 on 2026-10-13, at `b2c2850`); build C2a's plan uses XC-360 to XC-369; so this plan's lines take **XC-370 to XC-373**, each filed in the task that defers it (XC-370 Task 5, XC-371 and XC-373 Task 10, XC-372 Task 11), and **each "Next free" step replaces that line whatever it reads**: XC-371 after Task 5, **XC-374** from Task 10 on.
>
> **What was run, and what was not.** A scratch copy of `engine-c1` at `2d8717b` (`git archive`, a `wl-preproc` link to `.claude/worktrees/engine-a2/.superpowers/wl-preproc-main`, the interpreter `.claude/worktrees/engine-a2/.superpowers/venv/bin/python`, the shell's directory and `PYTHONPATH` at the copy, `WLX_REQUIRE_PREPROC=1 WLX_REQUIRE_BROWSER=1`) read **3490 passed** at the base (2026-10-11), as the CHECKPOINT says for C1's tip. **The draft's Tasks 1 to 12 were built there, in order**, and their edit blocks generated from the verified commits. **This revision was verified the same way on a fresh copy of `2d8717b` with this plan committed (2026-10-13)**: every edit block below parsed and applied in order, each anchor found once; each task's new tests seen failing as its red step says, then passing; each break under "Prove they can fail" of a task the revision changed applied alone, seen failing the tests it names, the file restored and compared; and the whole suite green after each task, **Task 1 3492, Task 2 3493, Task 3 3498, Task 4 3501, Task 5 3504, Task 6 3504, Task 7 3512, Task 8 3515, Task 9 3515, Task 10 3530, Task 11 3534, Task 12 3535 passed**. Every count and error this plan expects is what printed. **The same blocks apply cleanly to `main` as read on 2026-10-13** (`b2c2850`: C1, the deployment fix and later docs, "Next free" XC-359), every anchor once and in order, and the suite there read **3493 passed** before the build and **3538 passed** after all twelve tasks (the deployment fix's own tests are the difference from `2d8717b`'s counts). **Not run**: Task 12's CI sweep (read from CI), Python 3.11, which this machine does not have, and `tools/mutate.py` as a sweep (each break was applied by hand, one at a time).
>
> Execution: subagent-driven, a fresh implementer and reviewer per task, then a whole-branch review on the most capable model, as A1, A2, B and C1 were. **Every commit** ends with the session's attribution lines, as the repository's history does.

**Goal:** Every check the PI ruled on in the XC-352 audit does what he ruled: fourteen refusals become warnings or review notes that say why a value or a path may not be a good idea, his seven answered questions are built as he answered them, the 48 kept refusals stay, and each warning is shown whole before a person accepts it.

**Architecture:** The warnings model engine build B built is the mechanism throughout: a finding or a `warnlist.Entry` that is a warning names the session kinds it is accepted in (every kind, for every warning here), is listed with its explanation, is accepted once a session, and is recorded in `warnings.jsonl`. Load-time findings change severity in `check.py`; the calibration's, the setup's and a pause's warnings are new `warnlist` entries; a value outside a task's declared range is checked again with the range widened to it (`check.beyond_range`), at a run's start (`preflight.beyond`) and live (`Session._beyond_range`, called from the one branch of `Session.set` that is a task's own setting); the exact drawer clips a light the panel cannot make and gives the light it shows (`exact.shown`); a damaged `warnings.jsonl` row is left out of a resume.

**Tech Stack:** Python 3.11-3.13; dataclasses; numpy (already a dependency, for `exact`); pytest. **No new dependency.**

**Spec:** the audit, `docs/research/2026-10-11-xc352-refusal-audit.md` (committed by Task 12 from the controller's scratchpad, `xc352-refusal-audit.md`, with the PI's rulings appended), and his rulings below; engine spec `docs/superpowers/specs/2026-10-07-engine-design.md` §7, §17, §19 and §20; S8 §3.1; decisions.md COL-01, COL-02, COL-03, COL-21, COL-34, COL-36, DISP-31, STE-10, STE-20, EYE-23, REC-12, TSK-39, TSK-41 and WEL-11. Backlog: XC-352 and XC-353 (closed by this build), XC-306 (edited).

---

## The PI's decisions it builds (2026-10-11, binding)

**His rule**, on reviewing engine build C1: "in general, I think you have been too gung ho on refusals. I think warnings are more appropriate most of the time with an explanation of why it may not be a good idea to use a value or follow a path you may think to refuse. the experimenter needs free control most of the time."

**His answers to the audit**, each where it is built:

1. **D2** (a live or starting value outside the task's declared range): "re-run the load-time checks with the range widened to the new value; accept with a warning that the task was not designed for it if nothing breaks; refuse only what would break the run (off screen, windows colliding, colors unmakeable), saying what." Built: `check.widened`, `check.beyond_range` and `BREAKS_A_RUN` (Task 10), `preflight.beyond` and the starting values item (Task 10), `Session._beyond_range`, called from `Session.set` (Task 11). `Session.set` is welfare-listed; its ceiling branch is unchanged, byte for byte (Appendix A, item 1).
2. **A21** (recording on the default calibration with any color or light setting, COL-02): "a warning in recording too"; the record names the default. Built: Task 4.
3. **A19** (isoluminance on the default, COL-03): "a warning everywhere", saying the colors are only nominally isoluminant on an unmeasured panel. Built: Task 4.
4. **A20** (a color the panel cannot make): "a warning, and the drawer records the light actually shown beside the one asked for". Built now (Task 5): the warning, naming the light the panel shows; `exact.output_levels` clips instead of refusing and `exact.shown` gives the light the clipped levels make; the record carries the light asked for and the light shown together in the warning's row of `warnings.jsonl`, the one place it carries the asked light today. Recording the shown light per frame waits on the display process and the screen log (engine builds E and F): XC-370.
5. **D4** (any setting change between runs): "keep refusing". Nothing changes.
6. **C6** (the stereoscope without a settings file, STE-20): "a warning; the nominal 1.6 cm is recorded as nominal". Built: Task 7 (`config.json`'s `setup.half_ipd_nominal`).
7. **C7** (a half-IPD outside 30-38 mm, STE-20): "a warning" (outside the drawn optics, extrapolated). Built: Task 7.
8. **The fourteen proposed warnings, all approved**: A7 unreachable or shadowed parts as review notes only (Task 2); A8 overlapping windows, A9 a crowded array, A10 a wrong-eye criterion, A11 a monocular stereogram, A12 the wrong setup without stereo content (Task 3); E1 a calibration record that will not load, falling back to the default with a warning, E2 a calibration dated in the future, E3 cone colors on a measured calibration without spectra (Task 6; E1 reaches `Service._open`'s behavior: Appendix A, item 3); B1 the pre-flight warnings item failing on names over 500 characters (Task 1); C8 a settings file naming another animal, H4 `--subject-settings` with `--view direct` (Task 7); C11 one damaged `warnings.jsonl` row blocking a resume (Task 8); D5 a pause refused for a missing PAUSE or RESUME code (Task 9).
9. **The 48 kept refusals stay.** No other refusal changes.
10. **XC-353**, from C1's final fix wave: each warning's explanation shown in full before it is accepted on the console page. Built: Task 1.

**His answers of 2026-10-12**, to the two questions the draft put to him:

11. **A value outside its range making a trial wait longer than the task's longest declared wait** (call 4): **"Allow, with a warning"**. The option he chose read: "Any wait up to the trial cap: about 417 s today, 5 minutes once C2a is built. The warning says Stop, Pause and the out-of-cage limit go unheard until that trial ends." Built: `longer-than-declared` is a warning in every kind, one per wait, saying which wait and how long, that stop, pause and the out-of-cage limit are heard only between trials so they go unheard until that trial ends, and the trial cap (Task 10, at a run's start; Task 11, live); nothing is refused for it (Appendix A, item 2). The once-a-second check inside a trial is filed, XC-373.
12. **TRN-07** ("pause, stop, resume and manual reward never need sign-in"): **at the rig PC only**. His choice read: "No sign-in at the rig PC's own console. From another computer, sign-in is required, as built now, so nobody on the network can stop a session or give a reward unseen. The decision log's wording is clarified." Built: a dated revision of TRN-07 quoting it (Task 12); no code changes.

## What the PI should know

Things this plan does or does not do, in plain terms.

1. **Nothing about reward, the out-of-cage limit, the fluid floor or any bounded setting changes.** `Session.set` still sends a reward size to its ceiling exactly as before; Task 12 compares that branch byte for byte. Every refusal on the welfare list stays.
2. **Your answer on long waits is built: a warning, nothing refused (call 4; Appendix A, item 2).** A stop, a pause and the out-of-cage limit are checked between trials, not inside one, until the once-a-second check you decided in WEL-11 is built (filed, XC-373). A value outside its range may now make a wait as long as the experimenter sets -- a 60 s fixation acquisition in a task whose longest declared wait is 10 s -- with a warning, one per wait, that names the wait and its length, says stop, pause and the out-of-cage limit go unheard until that trial ends, and names the trial cap that ends any trial at the latest: 100,000 frames, about 417 s at 240 Hz today (computed), five minutes once C2a is built. Each wait is warned of on its own: a trial waiting on several long waits in turn can last their sum, up to the cap.
3. **"Windows colliding" and "colors unmakeable" are read as you wrote them for D2, against your A8, A9 and A20** (call 3). Within the declared ranges, windows that can overlap, a crowded array and a color the panel cannot make are warnings (A8, A9, A20). A value outside the range that makes one happen to windows, an array or a color the declared ranges did not already allow is refused, saying which value and what it breaks; one that only makes an overlap, a crowding or a clip the task was accepted with larger is a warning, saying the value. Off screen is refused either way (A15, kept).
4. **The reference search task's isoluminant red and green are just outside the sRGB standard's gamut** (a primary weight of -0.003 to -0.006). Its isoluminance refusal hid this until now. On the default it now runs with its warnings: the colors are only nominally isoluminant, the panel clips them (naming the light it shows), and every color is nominal. One warning names every color that claims isoluminance and one every light the panel clips, each light once, so the run's warnings item reads 2,802 characters where a warning per color made it 5,392 (measured on the scratch copy; 3,107 and 5,697 in a chaired session).
5. **Recording runs on the default calibration** with the warnings accepted; the session's `config.json` names the default, as it always has (`calibration.standard: true`). **A session resumed by a service that runs another calibration than the one it opened on** -- a measured record that stopped loading while `wlx taskd` was down, so the default stands in -- runs, with a warning its first run asks to accept, naming both; its `session resumed` row names the calibration it now runs on, and `config.json` keeps the one it opened on (call 18).
6. **A calibration record that will not load** now opens sessions on the default once that warning is accepted (one more warning on the open's list, Appendix A, item 3), the default's own warning then saying the record would not load rather than that the rig names none; `wlx taskd` prints the loader's whole sentence as it starts. A record dated after today is a warning to check the host's clock.
7. **The stereoscope's settings warnings are asked at the first run, not at the open** (call 7): no settings file (the nominal 1.6 cm, recorded as nominal at the open), another animal's settings, a half-IPD outside the drawn optics. The open's code and the page's New-session dialog are unchanged, **but an open these three refused before now goes ahead and marks the departure** (Appendix A, item 4).
8. **A typed value past a setting's range now goes through, with its warning; the page's arrows still stop at the range** (call 9). Nothing on the page changes.
9. **`wlx run --set` has never checked its values against the declared ranges**, and still does not (it takes no pre-flight, XC-159): filed as XC-371 rather than built, being outside the audit.
10. **Dead code** (a state nothing reaches, a repeated guard, a timeout another always beats, a meaning for no setting) is a review note: `wlx check` shows it, and no session refuses or asks about it.
11. **A damaged row in a stranded session's `warnings.jsonl`** no longer stops its resume: the row is left out, its warning is asked again at the next run, and the resume says so; accepted again, it is written on a line of its own, so a later resume keeps it (call 11).
12. **A pause on an allocation without PAUSE or RESUME codes** is taken, with a warning that the recording shows an unexplained gap; the pause and its resume are in `controls.jsonl`.
13. **A stereoscope task that shows each eye its own content stays refused in direct view** (call 14): a disparity, one eye only, a position per eye or a background per eye. An unmirrored screen cannot show it: the drawer would fail mid-trial on the first three, and a background per eye would leave a record that does not describe what was shown. Your A12 ruling made the wrong setup a warning, and the audit named stereo content as still refused; the positions and backgrounds per eye are this plan's reading, kept as refusals. Otherwise a task written for the other setup runs, with its warning.
14. **TRN-07, as you answered on 2026-10-12**: pause, stop, resume and manual reward need no sign-in at the rig PC's own console, and from another computer they need one, as the page is built. Task 12 records it as a dated revision of TRN-07; no code changes.

## Calls taken in this plan

Engineering decisions made without asking; each says what it costs if wrong.

1. **Every warning this build adds or turns from a refusal is accepted in every session kind** (`findings.SESSION_KINDS`): the audit proposed none limited to some kinds, and A19 and A21 say so of theirs. `findings.NOT_RECORDING` stays as the vocabulary a warning's kinds are written in, which nothing gives now. Cost: a kind limit is one tuple.
2. **A7's dead code is a review note** (`blocking=False`, no kinds, as `custom-component-needs-review` is): shown by `wlx check` ("review"), never refused or asked at the rig; the review report shows no findings, as it never has. Each sentence ends "which is probably a mistake". Cost: none.
3. **D2's refusals are every blocking finding that the task widened gives and the task as declared does not, and each finding `check.BREAKS_A_RUN` names** (`overlapping-windows`, `crowded-array`, `unrealizable-color`) **about something the task as declared gives none of** -- compared by what it is about, not by its sentence (`Finding.subjects`: the state and pair of windows an overlap names, the array a crowding names, each color a clip names; the review's I5, as the controller ruled). A finding the declared ranges already give was accepted with the task; one about the same windows, array or color, only larger, is a warning saying the value. Cost: an overlap, a crowding or a clip the task was accepted with may grow with a value outside its range, warned of each time; the draft refused it. And a color is named as `_colors` names it -- its appearance's type, and the parameter choice that offers it -- so two plain appearances of one type, a disc and another disc, are one subject: a value that newly clips the second, when the first clips at load, is a warning, not a refusal (no stimulus name reaches `_colors`).
4. **A wait longer than any the task declares is a warning, by the PI's answer of 2026-10-12** ("Allow, with a warning"; this call put the question to him): `check._waits` finds the settings a trial waits on and the task's longest declared wait (the highest bound any `After` or `Hold` setting declares, or the longest literal wait), and each value outside its range past that is `longer-than-declared`, accepted in every kind, **one per wait** (the review's I4: it bounds each wait, not the trial), saying which wait and how long, that stop, pause and the out-of-cage limit are heard only between trials so they go unheard until that trial ends, and the trial cap (`check.TRIAL_CAP`: `run_trial`'s 100,000 frames, about 417 s at 240 Hz, computed; a test pins the sentence to `run_trial`'s default, so build C2a's five-minute cap changes it). Nothing is refused for a long wait. The once-a-second check inside a trial (WEL-11; engine spec §6.8) is filed, XC-373, whose landing changes the sentence. Cost: none; the draft's refusal he declined.
5. **A20 now**: `exact.output_levels` clips each primary weight to [0, 1] instead of refusing, a weight that is no number still refused; `exact.shown` gives the light the clipped levels make; `check`'s `unrealizable-color` is a warning, **one per task** (`check._clips`; the review's M8), naming each light the panel cannot make, what asks for it, the primary weights it needs and the light the panel shows ("x=…, y=…, Y=… cd/m²", or "black, every primary off"), a light several things ask for said once; `warnings.jsonl` records it once it is accepted. **A light that does not convert at all stays a refusal**, its own: a cone color on a calibration with no cone matrix (the CIE table refused), against a black background, or with a weight that is no number. Recording the shown light per frame: XC-370, waiting on builds E and F. Cost: none found.
6. **E1's warning quotes the loader's refusal cut in its middle**, keeping the whole sentence within `link.NOTE_LIMIT` (500 characters), which an open's form sends back (`link.WarningRow.of` cuts at that, and the wire refuses a longer accepted sentence); the cut keeps the start (the path) and the end (why). `wlx taskd` prints it whole as it starts. The default's own warning, listed after it, says the record would not load rather than that the rig names none (`warnlist.of_calibration`'s `unloaded`; the review's M4). Cost: a long path loses its middle on the page.
7. **C6-C8's warnings are the session's setup warnings** (`SessionSpec.setup_warnings`, built by `Service._build`), **asked in the first run's pre-flight** (`Service._preflight`), not at the open: the open's code stays as it is, and the page's New-session dialog, which lists the idle frame's warnings before any animal is chosen, never has to offer an animal's. `config.json`'s `setup.half_ipd_nominal` records the nominal half-IPD at the open. The pre-flight's re-read of the settings (`preflight.files`) fails only a file that no longer loads, and drops its `rig` parameter. Cost: the open does not show them; the alternative changes `_open` and the dialog.
8. **C7**: `Rig.stereoscope` builds any half-IPD that leaves a positive optical path (`Z + W/4 − E`), refusing one that does not, or is no number: no field exists for it. Cost: none.
9. **D2 live**: `Session._beyond_range` runs the task's checks twice, at the trial boundary that drains the edit, never in a frame; how long that takes on the rig PC is unmeasured (XC-372; no timing claim without a measurement). Its warnings are accepted by the person who sent the value (`how="set"`), once each, as the value is offered; the value applies at the next boundary as every edit does. A check that raises, or a warning row that cannot be written, refuses the value, since `_command` catches `Exceeded` alone. The page's arrows still stop at the declared range; a typed value passes it. Cost: a warning recorded for a value overridden in the same drain; the arrows, a later change.
10. **D5**: the pause's warning (`pause unmarked`) is accepted by who paused (`how="pause"`), once a session; PAUSE and RESUME are strobed when the allocation has them. PAUSE, RESUME and MANUAL_REWARD are **not** added to the start-up framework codes (the audit's C13 aside): that would be a new refusal nobody ruled on. Cost: none.
11. **C11**: only a damaged row is left out; a `warnings.jsonl` that cannot be read at all is still unresumable (C10, kept). The resume says why on the changes feed, as a `warning`, and in its `session resumed` row; it is not itself a warning to accept. **A warning accepted after a torn row is written on a line of its own** (`SessionRecord.warning` ends a torn last line first, the smaller of the two fixes the review's I1 offered: one function, unlisted, rather than a resume that writes as it reads), so the next resume carries it. Cost: `SessionRecord.warning` reads `warnings.jsonl` before it appends, at an open, a start, a pause or a live edit, never in a frame.
12. **`wlx run --set` is not range-checked**, before or after this build: filed (XC-371), not built. Cost: a `wlx run` value outside its range runs with no warning, as it always has.
13. **XC-353 and B1**: the pre-flight's `warnings` item, when it asks to accept, says every warning whole, uncut, and no length fails it; the frame carries it only between runs (`Session.run` clears it). A fail, which accepts nothing and which the gate's refusal quotes, is still cut at `link.NOTE_LIMIT`. Every warning an open can be asked to accept stays within `link.NOTE_LIMIT`, pinned by a test, so the page's dialog shows each whole. Cost: a long sentence between runs.
14. **A12**: a stereoscope task in direct view stays refused when it shows each eye its own image (`_stereo_content`, and `_per_eye_content`, new: a position or a background per eye, which `screen._eyes` would raise on mid-trial); otherwise the wrong setup is a warning saying what the other setup changes. Cost: none.
15. **A19**: an isoluminant color on the default is still held to the panel's reach (the `continue` after the finding is removed), which is how the search task's clipping (item 4 above) surfaced. **One `isoluminance-on-default` warning per task names every color that claims isoluminance** (the review's M8), as `color-on-default` names its colors; a review of engine build B's Task 4 had asked each choice named in its own finding, which this keeps by naming each. Cost: none.
16. **E3**: a measured calibration without spectra converts cone colors through the default's matrix applied to its measured XYZ (`Calibration._convert`), recorded as such (`photometry.VIA_WITHOUT_SPECTRA`, `HELD_WITHOUT_SPECTRA`), with a task warning, `cone-colors-without-spectra`, naming its cone colors. Cost: none.
17. **Docs that a task invalidates are edited in that task** (CLAUDE.md, "Docs stay in sync"): architecture.md in Tasks 1, 5, 6, 8 and 11, pitfalls.md in Tasks 3, 4 and 5, the search task's docstring and its gray's comment in Task 5. Each backlog line goes in the task that defers or closes it (CLAUDE.md: Tasks 1, 5, 10, 11 and 12). The decision log's dated revisions, the specs' notes and the audit land in Task 12. Cost: none.
18. **A session resumed on another calibration than its `config.json` names is a warning, never a refusal** (the review's I2, as the controller ruled, by the PI's rule; the review offered refusing it as the audit's C10 class): `Service._resume` (unlisted) compares the id `config.json` names (`resume.Restoration.calibration`) with the service's and, when they differ, adds `calibration changed`, naming both, to the session's `setup_warnings`, which the first run's pre-flight asks to accept; the `session resumed` row names the calibration the session now runs on, each run's start row names the one it ran against (the engine B plan's call 26, which kept such a resume unrefused), and `config.json` keeps the one it opened on. Nothing listed changes. Cost: the record says the change three ways and refuses nothing.

## Global Constraints

- US English in code, comments and docs (CLAUDE.md).
- **The PI's rule and rulings of 2026-10-11, as above.** "The 48 kept refusals stay": no refusal the audit kept changes.
- **No function on architecture.md's welfare-critical list changes without going on Appendix A**, and **no welfare limit is softened**. `bounds.py`, `welfare.py`, `marks.py` and `stranded.py` are not edited; `preflight.gate`, `preflight.out_of_cage`, `Service._end`, `_unended`, `_close_stranded`, `_start`, `_unasked`, `_folder_name`, `Session._ends`, `_hold`, `_manual_reward`, `_schedule`, `OUTSIDE_A_RUN`, `_command`, `link._setting`, `cli._settle_departure`, `_settle_return` and `main`'s `_marks.depart(session, departure)` line are unchanged byte for byte; `Session.set` changes in its task-setting branch only; `Service._open`'s code is unchanged (Task 12, Step 7).
- Hot path: **nothing new per frame.** The widened checks run at a run's start and at the trial boundary that drains a live edit; no timing claim is made (XC-372).
- No new dependency.
- Every new or changed function is proven able to fail (a named break, its test seen failing, restored byte for byte with `cmp` against a copy, `__pycache__` cleared). **Read the harness's output, not its exit code** (CLAUDE.md). Never run the suite, edit a test or `git add` while a sweep is in flight.
- **The interpreter**: the build worktree's `.superpowers/venv/bin/python` (written `$PY` below), set up as C1's was, **always with the shell's current directory at the build worktree, in the same call** (`cd <worktree> && $PY …`), never with `-I`, so the worktree's `wl_xcon` is the one imported. Check once: `$PY -c "import wl_xcon; print(wl_xcon.__file__)"` names the worktree's. `WLX_REQUIRE_PREPROC=1` works through the worktree's `wl-preproc` link.
- The suite: `WLX_REQUIRE_PREPROC=1 WLX_REQUIRE_BROWSER=1 PYTHONDONTWRITEBYTECODE=1 $PY -m pytest -q -p no:cacheprovider` (add `-n auto` where pytest-xdist is installed; the counts are the same). Named files: `$PY -m pytest -q -p no:cacheprovider tests/<file> …`.
- **Every edit is an exact replacement**, written "Replace … with …" in the order given: each "Replace" block occurs exactly once in its file at that point, so an exact-match edit applies it. **The one exception is the backlog's "Next free ID" line**, which Tasks 5 and 10 replace whatever it reads, since the deployment fix that merges before this branch moves it. A new test file's imports are already placed in its import block by the blocks given.
- **Every citation in a doc's prose names a key `docs/references/library.bib` has** (`tests/test_references.py`). This plan adds no key; its revisions rest on the PI's decisions and say so.
- Backlog IDs XC-370 to XC-373 are this plan's; paste them as written. XC-355 is the deployment fix's and XC-360 to XC-369 build C2a's.

## Review Focus

The five inputs most likely to bite that no task's own tests would otherwise exercise, each pinned by a test in its owning task:

1. **A value typed on the page past a setting's declared range, during a run.** Expected: a fixation window of 7° (declared 0.5-5°) applies at the next boundary, its warning on the changes feed and in `warnings.jsonl`; a target at 40° (declared ±16°) is refused as off screen, saying so, the previous value standing; a 60 s fixation acquisition is staged with two warnings, outside its range and a wait longer than the task declares, which says stop, pause and the out-of-cage limit go unheard until that trial ends (the PI's answer of 2026-10-12). Tests: Task 11, `test_a_live_value_outside_its_range_applies_with_a_warning_that_the_task_was_not_designed_for_it`, `test_a_live_value_that_would_put_the_target_off_screen_is_refused_saying_so`, `test_a_live_wait_longer_than_any_the_task_declares_is_staged_with_its_warnings`.
2. **A chaired session's reference task on the default calibration, its `head-not-fixed` past the old 500-character cut.** Expected: the page's pre-flight panel shows it whole, "no head tracking" and all, before it is accepted. Test: Task 1, `test_a_chaired_runs_head_warning_is_on_the_page_whole_before_it_is_accepted`.
3. **`wlx taskd` started with a rig naming a calibration record that is not JSON.** Expected: the service starts on the default; an open not accepting the record's warning is refused, nothing written; one accepting it opens, a run starts, and `config.json` names the default. Test: Task 6, `test_a_calibration_record_that_will_not_load_runs_sessions_on_the_default_with_a_warning`.
4. **A stereoscope session for an animal with no settings file, another animal's settings, or a half-IPD of 2.0 cm.** Expected: each opens; the first run's pre-flight asks for its warning; the run starts once accepted; the nominal half-IPD is recorded as nominal. Test: Task 7, `test_a_stereoscope_session_runs_on_its_settings_warnings_once_they_are_accepted` (three cases).
5. **A stranded session whose `warnings.jsonl` ends in half a line.** Expected: resumable; the resume leaves the torn row out, says so on the feed and in its `session resumed` row, and the next run's pre-flight asks for that warning again; accepted, it is written on a line of its own, and a second resume carries it. Tests: Task 8, `test_a_torn_warnings_file_is_resumed_and_its_lost_warning_asked_again`, `test_a_warning_accepted_after_a_torn_row_is_on_a_line_of_its_own_and_resumed_again`.

## File Structure

| File | Change | Responsibility |
|---|---|---|
| `wl_xcon/preflight.py` | modify | `warnings` says every owed warning whole (T1); `files` passes another animal's settings (T7); `starting`, `beyond`, and `values` taking what breaks (T10) |
| `wl_xcon/check.py` | modify | dead code as review notes (T2); five findings as warnings, `_per_eye_content` (T3); the default's color findings in every kind, one isoluminance warning per task (T4); `_unrealizable`, `_clips`, `_clipped` (T5); `_spectra_faults` (T6); `check_task`'s subjects, `BREAKS_A_RUN`, `TRIAL_CAP`, `_outside`, `_waits`, `widened`, `beyond_range`, the subjects of an overlap and a crowding (T10) |
| `wl_xcon/findings.py` | modify | `NOT_RECORDING`'s comment (T4); `Finding.subjects` (T5) |
| `wl_xcon/exact.py` | modify | `_weights`, `output_levels` clips, `shown` (T5) |
| `wl_xcon/photometry.py` | modify | `_convert` without spectra, `VIA_WITHOUT_SPECTRA`, `HELD_WITHOUT_SPECTRA`, `cone_record` (T6) |
| `wl_xcon/warnlist.py` | modify | `of_calibration`, `of_unloaded` in every kind, `of_calibration`'s `unloaded` (T6); `of_setup`, `of_ignored_settings` and their codes (T7); `CALIBRATION_CHANGED`, `of_changed_calibration` (T8); `PAUSE_UNMARKED` (T9); the docstring's lists (T8-T11) |
| `wl_xcon/service.py` | modify | the default in an unloadable record's place, `calibration_warnings` (T6); `_build`'s setup warnings, `_preflight`'s (T7); `_resume`'s warning of another calibration (T8); `_preflight`'s widened starting values (T10) |
| `wl_xcon/cli.py` | modify | `_calibration_or_default` (T6); `_load_subject_settings`, `_session_geometry`, `wlx check`'s and `wlx run`'s setup warnings (T7) |
| `wl_xcon/geometry.py` | modify | `NOMINAL_HALF_IPD_CM`; `Rig.stereoscope` builds any half-IPD with a field (T7) |
| `wl_xcon/resume.py` | modify | `_Damaged`, `_accepted`, `_warnings`, `Restoration.damaged`, `Restoration.calibration` (T8) |
| `wl_xcon/record.py` | modify | `SessionRecord.warning` writes a line of its own after a torn one (T8) |
| `wl_xcon/taskd.py` | modify | comments on a missing calibration (T6); `SessionSpec.setup_warnings`, `config.json`'s `half_ipd_nominal` (T7); `Session.resume` says what it left out and the calibration it runs on (T8); `_pause`, `_resume` (T9); `Session.set`'s task-setting branch, `_beyond_range` (T11) |
| `wl_xcon/task.py`, `wl_xcon/link.py` | modify | docstring and comment only (T10; T6, T8) |
| `tasks/reference_subject.py`, `tasks/visual_search.py` | modify | docstring only (T7); docstring and a comment (T5) |
| `tests/…` | modify | as each task says; `tests/test_references.py`, no two decisions share a number (T12) |
| `docs/design/architecture.md`, `docs/pitfalls.md` | modify | in the tasks that invalidate them |
| `docs/backlog.md` | modify | Tasks 1, 5, 10, 11 and 12, each the line it closes or files |
| `docs/references/decisions.md`, the engine spec, S8, `docs/research/2026-10-11-xc352-refusal-audit.md` | modify / create | Task 12 |

---
### Task 1: A run's pre-flight shows each warning whole before it is accepted (XC-353; XC-352's B1)

The `warnings` item a start acknowledges cut its sentence at 500 characters, so the reference task's `head-not-fixed`, last on the default calibration, lost its why on the page (XC-353), and an item whose warnings' names alone passed 500 characters failed the run (B1). Now an unknown says every warning whole, however long, and no length fails it; a fail, which accepts nothing and which the gate's refusal quotes, is still cut.

**Files:**
- Modify: `wl_xcon/preflight.py` (`warnings`)
- Modify (test): `tests/test_preflight.py`, `tests/test_service.py`
- Modify (docs): `docs/design/architecture.md` ("`Service._open` and `Service._start` and the warnings list"), `docs/backlog.md` (XC-353's line removed: closed)

**Interfaces:**
- Consumes: `warnlist.refused`, `warnlist.owed`, `warnlist.sentence`, `link.cut`, `link.NOTE_LIMIT` (unchanged).
- Produces: `preflight.warnings(entries, kind, accepted) -> tuple[PreflightItem, list]`, signature unchanged: an unknown's `said` is `"{n} not yet accepted this session ({codes}): {sentence of each owed warning}"`, uncut; a fail's is cut at `link.NOTE_LIMIT`.

- [ ] **Step 0: Commit this plan, and record the base and the suite's count there**

Run `git rev-parse --short HEAD` (the branch's base, written `BASE` below, which Task 12 compares the welfare-listed functions against). **Copy this plan to `docs/superpowers/plans/2026-10-11-warnings-over-refusals.md` and commit it alone** (`git add docs/superpowers/plans/2026-10-11-warnings-over-refusals.md && git commit -m "Add the warnings-over-refusals plan (XC-352, XC-353)"`): the decision log's and the backlog's links point at it, and without it Task 5's suite fails `test_every_link_into_the_repository_names_a_file_that_exists` on XC-370's link (the review's M1). Then run the suite (Global Constraints). Expected: green, **3490 passed** at `2d8717b`'s code with the plan committed (2026-10-13); the deployment fix (XC-355), merged before the branch is cut, brings three tests of its own, so on `main` as read 2026-10-13 (`b2c2850`) it reads **3493 passed**, and every suite count in this plan reads three higher (3538 after Task 12). Write both into the plan's commit body as "BASE <hash>, N passed at the base".

- [ ] **Step 1: Write the failing tests**

**`tests/test_preflight.py`** (3 replacements, in order):

Replace:

```python

def test_the_warnings_items_sentence_is_cut_as_the_wire_cuts_and_each_warning_is_kept_whole():
    """A task's `color-on-default` names every colored choice, and a record that will not load
    is quoted with whatever its loader said, so nothing bounds the item's sentence where it is
    made: it is cut to `link.NOTE_LIMIT` characters and "…", as a frame's warning rows are.
    What the start accepts is the warnings themselves, never the sentence, so each keeps every
    word for `warnings.jsonl`."""
    long = Entry("long", "x" * 2_000, SESSION_KINDS)
```

with:

```python

def test_an_unknown_says_each_warning_it_asks_to_accept_whole():
    """XC-353 (the PI, 2026-10-11: warnings "with an explanation of why it may not be a good
    idea"): one acknowledgement of this item accepts every warning it lists, so it says each
    whole -- its code and every word of its sentence -- however long. What the start accepts is
    the warnings themselves, and each keeps every word for `warnings.jsonl`."""
    long = Entry("long", "x" * 2_000 + " the end", SESSION_KINDS)
```

Replace:

```python
    item, owed = preflight.warnings([long], "training", frozenset())
    assert (item.result, len(item.said)) == ("unknown", NOTE_LIMIT + 1)
    assert item.said.startswith("1 not yet accepted this session (long): long: xxx")
    assert item.said.endswith("…")
    assert owed == [long] and owed[0].detail == "x" * 2_000

    refused = Entry("refused", "y" * 2_000, ())
    item, _ = preflight.warnings([refused], "training", frozenset())
    assert (item.result, len(item.said)) == ("fail", NOTE_LIMIT + 1)
    assert item.said.startswith("a training session does not accept refused: yyy")
```

with:

```python
    item, owed = preflight.warnings([long], "training", frozenset())

    assert item.result == "unknown"
    assert item.said == "1 not yet accepted this session (long): long: " + "x" * 2_000 + " the end"
    assert owed == [long]
```

Replace:

```python

def test_an_unknown_names_each_warning_first_or_fails_when_their_names_cannot_all_be_shown():
    """Fix round 1 of Task 12: one acknowledgement accepts every warning the item lists, so its
    head -- the count and each code, "1 not yet accepted this session (<code>)", 34 characters
    and the code -- must fit within `link.NOTE_LIMIT`, which the cut keeps whole. One character
    more, and the item fails, accepting nothing."""
    fits = Entry("c" * (NOTE_LIMIT - 34), "x" * 2_000, SESSION_KINDS)
    item, owed = preflight.warnings([fits], "training", frozenset())
    assert (item.result, owed) == ("unknown", [fits])
    assert item.said == f"1 not yet accepted this session ({fits.code})…"

    over = Entry("c" * (NOTE_LIMIT - 33), "x", SESSION_KINDS)
    item, owed = preflight.warnings([over], "training", frozenset())
    assert (item.result, owed) == ("fail", [])
    assert item.said.startswith(
        "the names of the 1 warning(s) not yet accepted this session run past the 500 characters"
    )
```

with:

```python

def test_an_unknown_names_every_warning_however_long_their_names_and_never_fails_for_it():
    """XC-352's B1 (the PI, 2026-10-11, approving the audit): a display limit is no reason to
    refuse a run. Twenty codes whose names together run past `link.NOTE_LIMIT` failed the item
    before; each is named now, and the item asks to accept them."""
    many = [Entry(f"code-{i:02d}-" + "c" * 40, "x", SESSION_KINDS) for i in range(20)]

    item, owed = preflight.warnings(many, "training", frozenset())

    assert (item.result, owed) == ("unknown", many)
    head = item.said.split("): ")[0]
    assert len(head) > NOTE_LIMIT and all(entry.code in head for entry in many)


def test_a_fail_accepts_nothing_and_is_cut_as_the_refusal_quoting_it_is():
    """A warning the session's kind does not accept fails the item, which accepts nothing, so
    its sentence is cut to `link.NOTE_LIMIT` characters and "…": the gate's refusal quotes it."""
    refused = Entry("refused", "y" * 2_000, ())

    item, owed = preflight.warnings([refused], "training", frozenset())

    assert (item.result, len(item.said), owed) == ("fail", NOTE_LIMIT + 1, [])
    assert item.said.startswith("a training session does not accept refused: yyy")
```

**`tests/test_service.py`** (6 replacements, in order):

Replace:

```python
from _calibrations import BACKGROUND, LINEAR, OBSERVER, PRIMARIES, SPECTRA, measured, promptly
from _ports import endpoints as free_endpoints
```

with:

```python
from _calibrations import BACKGROUND, LINEAR, OBSERVER, PRIMARIES, SPECTRA, measured, promptly
from _frames import view
from _ports import endpoints as free_endpoints
```

Replace:

```python
from wl_xcon.warnlist import Entry
from wl_xcon.welfare import Deployment, Welfare
```

with:

```python
from wl_xcon.warnlist import Entry
from wl_xcon.web import fragments
from wl_xcon.welfare import Deployment, Welfare
```

Replace:

```python

def test_a_task_whose_declarations_are_malformed_fails_its_preflight_and_the_service_goes_on(
```

with:

```python

def test_a_chaired_runs_head_warning_is_on_the_page_whole_before_it_is_accepted(tmp_path):
    """XC-353, from engine C1's final fix wave: on the default calibration the reference task's
    `head-not-fixed` came last in the `warnings` item, past its 500-character cut, so the page
    never showed why ("no head tracking") before a person accepted it. The item and the page's
    pre-flight panel now show every owed warning whole."""
    service = _service(tmp_path)
    _step(service, _open(deployment="rig_chaired"))

    checked = _step(service, CheckRun(by=BY, task=TASK, values=dict(VALUES)))

    item = {i.name: i for i in checked.preflight.items}["warnings"]
    assert item.result == "unknown" and len(item.said) > NOTE_LIMIT
    head = item.said[item.said.index("head-not-fixed: "):]
    assert head.endswith("(engine spec §20.1)") and "no head tracking" in head
    panel = fragments(checked, view())["preflight"]
    assert "no head tracking, so" in panel and "(engine spec §20.1)" in panel


def test_a_task_whose_declarations_are_malformed_fails_its_preflight_and_the_service_goes_on(
```

Replace:

```python

def test_a_runs_warning_sentences_are_cut_on_the_frame_and_written_whole(tmp_path, monkeypatch):
    """Nothing bounds a warning's sentence where it is made -- a task's `color-on-default`
    names every colored choice, a record that will not load is quoted -- so the `warnings`
    item's sentence is cut to `link.NOTE_LIMIT` characters and "…" on the frame and in a
    refusal; the warning itself is never cut, and `warnings.jsonl` keeps every word."""
```

with:

```python

def test_a_runs_warnings_are_shown_whole_before_they_are_accepted_and_written_whole(
    tmp_path, monkeypatch
):
    """XC-353: nothing bounds a warning's sentence where it is made -- a task's
    `color-on-default` names every colored choice -- and the `warnings` item a start
    acknowledges shows each whole on the frame, before it is accepted; `warnings.jsonl` keeps
    every word. A fail, which accepts nothing, is cut in the refusal that quotes it."""
```

Replace:

```python
    item = {i.name: i for i in checked.preflight.items}["warnings"]
    assert (item.result, len(item.said)) == ("unknown", NOTE_LIMIT + 1) and item.said.endswith("…")
```

with:

```python
    item = {i.name: i for i in checked.preflight.items}["warnings"]
    assert item.result == "unknown" and "calibration age: " + "x" * 2_000 in item.said
```

Replace:

```python
    assert before.index("contrast-on-default:") > NOTE_LIMIT, "past the cut before this fix"
    assert len(item.said) == NOTE_LIMIT + 1
    assert item.said.startswith(
        "3 not yet accepted this session (default calibration, color-on-default, "
        "contrast-on-default): default calibration: the rig names no measured calibration"
    )
```

with:

```python
    assert before.index("contrast-on-default:") > NOTE_LIMIT, "past the cut before this fix"
    assert item.said == (
        "3 not yet accepted this session (default calibration, color-on-default, "
        f"contrast-on-default): {warnlist.sentence(owed)}"
    ), "each shown whole (XC-353)"
```

- [ ] **Step 2: Run them and see them fail**

Run: `$PY -m pytest -q -p no:cacheprovider tests/test_preflight.py tests/test_service.py`
Expected: `5 failed, 289 passed`: `test_an_unknown_says_each_warning_it_asks_to_accept_whole` (its sentence ends "…" at 501 characters), `test_an_unknown_names_every_warning_however_long_their_names_and_never_fails_for_it` (`('fail', [])`), `test_a_chaired_runs_head_warning_is_on_the_page_whole_before_it_is_accepted` (`head-not-fixed`'s sentence ends "the task tracks gaze and the …"), `test_a_runs_warnings_are_shown_whole_before_they_are_accepted_and_written_whole` and `test_every_warning_a_start_accepts_is_named_in_the_item_it_accepted` (each sentence cut).

- [ ] **Step 3: Implement**

**`wl_xcon/preflight.py`** (2 replacements, in order):

Replace:

```python

    **The item's sentence is cut to `link.NOTE_LIMIT` characters and "…"**, as a frame's
    warning rows are (`link.WarningRow.of`): nothing bounds a warning's sentence where it is
    made -- a task's `color-on-default` names every colored choice, and a record that will not
    load is quoted with what its loader said. The warnings returned keep every word: they,
    never this sentence, are what a start accepts and `warnings.jsonl` records.

    **An unknown names every warning it lists before it says any** (fix round 1 of Task 12):
    one acknowledgement accepts them all, so a cut may shorten what they say but never drop
    one's name. Its head -- the count and each code, in parentheses -- must fit within
    `link.NOTE_LIMIT` characters, which the cut keeps whole; when it does not, the item
    **fails** rather than ask to accept warnings it cannot show. **A repeated code is named
    once, with its count** ("luminance-step ×30"), in the order the codes first appear (fix
    round 2): a task gives one `luminance-step` per pattern whose mean differs from the
    background, and its names alone must not push the head past the limit."""
```

with:

```python

    **An unknown says every warning it asks to accept, whole** (XC-353; the PI, 2026-10-11:
    warnings "with an explanation of why it may not be a good idea"): its head -- the count and
    each code, a repeated one named once with its count ("luminance-step ×30"), in the order
    the codes first appear -- then each warning's code and every word of its sentence. One
    acknowledgement of this item accepts them all, so each is shown in full before it is
    accepted, on the page and at a terminal alike. **Nothing here cuts it, and no length fails
    it** (XC-352's B1: a display limit is no reason to refuse a run); it is on a frame only
    between runs (`Session.run` clears it as a run starts).

    **A fail is cut to `link.NOTE_LIMIT` characters and "…"**: it accepts nothing, and the
    gate's refusal quotes it. The warnings returned keep every word: they, never this
    sentence, are what a start accepts and `warnings.jsonl` records."""
```

Replace:

```python
        codes = ", ".join(code if n == 1 else f"{code} ×{n}" for code, n in counts.items())
        head = f"{len(owed)} not yet accepted this session ({codes})"
        if len(head) > _link.NOTE_LIMIT:
            return PreflightItem(WARNINGS, FAIL, _link.cut(
                f"the names of the {len(owed)} warning(s) not yet accepted this session run "
                f"past the {_link.NOTE_LIMIT} characters this item shows, so one acknowledgement "
                f"cannot be shown to accept them all, and none is accepted: {codes}",
                _link.NOTE_LIMIT,
            )), []
        return (
            PreflightItem(WARNINGS, UNKNOWN, _link.cut(
                f"{head}: {warnlist.sentence(owed)}", _link.NOTE_LIMIT,
            )),
```

with:

```python
        codes = ", ".join(code if n == 1 else f"{code} ×{n}" for code, n in counts.items())
        return (
            PreflightItem(
                WARNINGS, UNKNOWN,
                f"{len(owed)} not yet accepted this session ({codes}): "
                f"{warnlist.sentence(owed)}",
            ),
```

The docs it changes:

**`docs/design/architecture.md`**:

Replace:

```markdown
accepted is written once the service holds the session. A run's pre-flight has a `warnings` item:
a fail for a warning the session's kind does not accept (or for warnings that cannot be listed, or
too many to name in the item), otherwise an unknown acknowledged by name while any is not yet
accepted this session, and a pass once each is.
```

with:

```markdown
accepted is written once the service holds the session. A run's pre-flight has a `warnings` item:
a fail for a warning the session's kind does not accept (or for warnings that cannot be listed),
otherwise an unknown acknowledged by name while any is not yet accepted this session, which names
and says each whole, however long (XC-353; since 2026-10-11 no length fails it, XC-352's B1), and
a pass once each is.
```

**`docs/backlog.md`**:

Replace:

```markdown
- **XC-352** Audit every refusal in the engine against the PI's rule of 2026-10-11 ("in general, I think you have been too gung ho on refusals. I think warnings are more appropriate most of the time with an explanation of why it may not be a good idea to use a value or follow a path you may think to refuse. the experimenter needs free control most of the time."): list each, propose warning or refusal with the reason (refuse only where welfare, safety or an uninterpretable record demands), and put the list to the PI; changes go through their own reviewed build. — 2026-10-11, [engine spec §20, item 1's revision](superpowers/specs/2026-10-07-engine-design.md#20-welfare), the PI's ruling on reviewing engine build C1 — waits on: nothing
- **XC-353** Show each warning's explanation in full before it is accepted on the console page: the pre-flight's warnings item is cut at 500 characters (`link.NOTE_LIMIT`), and `head-not-fixed` comes last, so its why ("no head tracking") is cut on the page for every reference task on the default calibration, though `wlx run` and `warnings.jsonl` show it whole; the PI's rule of 2026-10-11 asks for warnings "with an explanation". — 2026-10-11, [engine C1 plan, Appendix A](superpowers/plans/2026-10-11-engine-c1.md#appendix-a-welfare-summary-items), found by its final fix wave's re-review — waits on: nothing
```

with:

```markdown
- **XC-352** Audit every refusal in the engine against the PI's rule of 2026-10-11 ("in general, I think you have been too gung ho on refusals. I think warnings are more appropriate most of the time with an explanation of why it may not be a good idea to use a value or follow a path you may think to refuse. the experimenter needs free control most of the time."): list each, propose warning or refusal with the reason (refuse only where welfare, safety or an uninterpretable record demands), and put the list to the PI; changes go through their own reviewed build. — 2026-10-11, [engine spec §20, item 1's revision](superpowers/specs/2026-10-07-engine-design.md#20-welfare), the PI's ruling on reviewing engine build C1 — waits on: nothing
```

- [ ] **Step 4: Run them and see them pass**

Run the two files, then the whole suite. Expected: `294 passed`; the suite **3492 passed**.

- [ ] **Step 5: Prove they can fail**

Each break applied alone, the named tests run, the file restored byte for byte (`cp` before, `cmp` after, `__pycache__` cleared):
- `warnings`' unknown sentence wrapped again in `_link.cut(…, _link.NOTE_LIMIT)`: the five tests Step 2 names fail.
- After its `codes = …` line, `if len(codes) > _link.NOTE_LIMIT: return PreflightItem(WARNINGS, FAIL, "too long"), []`: `test_an_unknown_names_every_warning_however_long_their_names_and_never_fails_for_it` fails.
- The fail's `_link.cut(…)` removed, its sentence whole: `test_a_fail_accepts_nothing_and_is_cut_as_the_refusal_quoting_it_is` and `test_a_runs_warnings_are_shown_whole_before_they_are_accepted_and_written_whole` fail.

- [ ] **Step 6: Commit**

```bash
git add wl_xcon/preflight.py tests/test_preflight.py tests/test_service.py docs/design/architecture.md docs/backlog.md
git commit -m "Show each warning a run asks to accept whole, and never fail on their names' length (closes XC-353)"
```
Body: XC-353 (engine C1's final fix wave) and XC-352's B1 (the PI, 2026-10-11, approving the audit's proposal: "a display limit is no reason to refuse a run"); `preflight.gate` and `Service._start` unchanged; the count; the breaks seen failing.

---

### Task 2: Dead code is a review note (XC-352's A7)

A state nothing reaches, a transition a repeated guard shadows, a timeout another always beats, and a meaning for a setting no structure declares can never take effect. Each was a refusal; each is now a review note (`blocking=False`, no kinds), which `wlx check` shows as "review" and no session refuses or asks about. The tests that used an unreachable state as "a task that fails its checks" take one that still does: a state that can never reach an outcome (S1 §9 check 3, kept).

**Files:**
- Modify: `wl_xcon/check.py` (module docstring; `_meaning_faults`, `_unreachable_states`, `_shadowed_transitions`, `_unreachable_timeouts`)
- Modify (test): `tests/test_task_checks.py`, `tests/test_range_checks.py`, `tests/test_task_object.py`, `tests/test_taskd.py`, `tests/test_cli.py`, `tests/test_service.py`

**Interfaces:**
- Consumes: `findings.Finding` (unchanged).
- Produces: the findings `unreachable-state`, `shadowed-transition`, `unreachable-timeout` and `meaning-for-nothing` with `blocking=False` and `accepted_in=()`, each sentence ending "which is probably a mistake".

- [ ] **Step 1: Write the failing tests**

**`tests/test_cli.py`** (2 replacements, in order):

Replace:

```python
    to be able to refuse it without parsing prose."""
    bad = tmp_path / "bad_task.py"
    bad.write_text(
        "from wl_xcon.task import NO_CHOICE, After, On, Outcome, ReactionTime, State, Task, Trial\n"
        "t = Trial(start='a', states=[\n"
        "    State('a', go=[On(After(1.0), Outcome.CORRECT)]),\n"
        "    State('orphan', go=[On(After(1.0), Outcome.CORRECT)]),\n"
        "])\n"
        "TASK = Task({'t': t}, default='t', choice=NO_CHOICE,\n"
        "            reaction_time=ReactionTime('a', (Outcome.CORRECT,), 'the wait'))\n"
    )

    assert main(["check", str(bad), "--rig", RIG_FILE]) == 1
    assert "unreachable-state" in capsys.readouterr().out
```

with:

```python
    to be able to refuse it without parsing prose."""
    bad = tmp_path / "bad_task.py"
    bad.write_text(
        "from wl_xcon.task import NO_CHOICE, After, On, Outcome, ReactionTime, State, Task, Trial\n"
        "t = Trial(start='a', states=[\n"
        "    State('a', go=[On(After(1.0), Outcome.CORRECT)]),\n"
        "    State('orphan', go=[On(After(1.0), Outcome.CORRECT)]),\n"
        "    State('trap', go=[On(After(1.0), 'trap')]),\n"
        "])\n"
        "TASK = Task({'t': t}, default='t', choice=NO_CHOICE,\n"
        "            reaction_time=ReactionTime('a', (Outcome.CORRECT,), 'the wait'))\n"
    )

    assert main(["check", str(bad), "--rig", RIG_FILE]) == 1
    out = capsys.readouterr().out
    assert "refused  no-outcome-path" in out
    # Dead code is a review note (XC-352's A7): shown, refusing nothing.
    assert "review   unreachable-state" in out
```

Replace:

```python
    monkeypatch.setattr(cli, "check_task", lambda *args, **kwargs: [])
    bad = tmp_path / "bad_task.py"
    bad.write_text(
        "from wl_xcon.task import NO_CHOICE, After, On, Outcome, ReactionTime, State, Task, Trial\n"
        "t = Trial(start='a', states=[\n"
        "    State('a', go=[On(After(1.0), Outcome.CORRECT)]),\n"
        "    State('orphan', go=[On(After(1.0), Outcome.CORRECT)]),\n"
        "])\n"
        "TASK = Task({'t': t}, default='t', choice=NO_CHOICE,\n"
        "            reaction_time=ReactionTime('a', (Outcome.CORRECT,), 'the wait'))\n"
    )
    argv = _run_args(tmp_path, "--out-of-cage-at", _hhmm())
```

with:

```python
    monkeypatch.setattr(cli, "check_task", lambda *args, **kwargs: [])
    bad = tmp_path / "bad_task.py"
    bad.write_text(
        "from wl_xcon.task import NO_CHOICE, After, On, Outcome, ReactionTime, State, Task, Trial\n"
        "t = Trial(start='a', states=[\n"
        "    State('a', go=[On(After(1.0), Outcome.CORRECT)]),\n"
        "    State('orphan', go=[On(After(1.0), Outcome.CORRECT)]),\n"
        "    State('trap', go=[On(After(1.0), 'trap')]),\n"
        "])\n"
        "TASK = Task({'t': t}, default='t', choice=NO_CHOICE,\n"
        "            reaction_time=ReactionTime('a', (Outcome.CORRECT,), 'the wait'))\n"
    )
    argv = _run_args(tmp_path, "--out-of-cage-at", _hhmm())
```

**`tests/test_range_checks.py`** (2 replacements, in order):

Replace:

```python

def test_a_later_after_that_can_never_fire_first_is_refused():
```

with:

```python

def test_a_later_after_that_can_never_fire_first_is_a_review_note():
```

Replace:

```python
    assert "ABORT" in findings[0].detail

```

with:

```python
    assert "ABORT" in findings[0].detail
    # A review note, never a refusal (XC-352's A7).
    assert (findings[0].blocking, findings[0].accepted_in) == (False, ())
    assert findings[0].detail.endswith("which is probably a mistake")

```

**`tests/test_service.py`**:

Replace:

```python
    assert "no head tracking, so" in panel and "(engine spec §20.1)" in panel

```

with:

```python
    assert "no head tracking, so" in panel and "(engine spec §20.1)" in panel


def test_a_task_with_a_state_nothing_reaches_runs_and_is_asked_nothing_about_it(tmp_path):
    """XC-352's A7 (the PI, 2026-10-11): dead code -- a state no transition reaches -- can never
    take effect, so it is a review note: `wlx check` shows it, and at the rig it neither fails the
    task checks nor joins the warnings a start accepts."""
    service = _service(tmp_path)
    text = Path("tasks/fixation_detection.py").read_text()
    states = "    states=[\n"
    assert text.count(states) == 1
    (service.tasks / "orphaned.py").write_text(text.replace(
        states, states + '        State("orphan", go=[On(After(1.0), Outcome.NO_RESPONSE)]),\n'))
    _step(service, _open())

    started = _step(service, _start(task="orphaned.py"))

    items = {item["name"]: item for item in _runs(service.root)[0]["preflight"]}
    assert items["task checks"]["result"] == "pass"
    assert "unreachable-state" not in items["warnings"]["said"]
    assert started.run_index == 0

```

**`tests/test_task_checks.py`** (2 replacements, in order):

Replace:

```python
    assert "orphan" in findings[0].detail

```

with:

```python
    assert "orphan" in findings[0].detail
    # A review note, never a refusal (XC-352's A7; the PI, 2026-10-11): `wlx check` shows it,
    # and no session refuses or asks it.
    assert (findings[0].blocking, findings[0].accepted_in) == (False, ())
    assert findings[0].detail.endswith("which is probably a mistake")

```

Replace:

```python
    assert "decide" in findings[0].detail

```

with:

```python
    assert "decide" in findings[0].detail
    assert (findings[0].blocking, findings[0].accepted_in) == (False, ())
    assert findings[0].detail.endswith("which is probably a mistake")

```

**`tests/test_task_object.py`** (2 replacements, in order):

Replace:

```python

def test_an_override_of_nothing_and_a_meaning_for_no_setting_are_refused():
    """Review Focus 2: a meaning kept for a setting the task no longer declares is refused, and so
    is an override of a name the shared list does not have."""
```

with:

```python

def test_an_override_of_nothing_is_refused_and_a_meaning_for_no_setting_is_a_review_note():
    """Review Focus 2: an override of a name the shared list does not have is refused; a meaning
    kept for a setting the task no longer declares can never take effect, and is a review note,
    never a refusal (XC-352's A7; the PI, 2026-10-11)."""
```

Replace:

```python
    assert found.code == "meaning-for-nothing" and "'speed'" in found.detail
    (found,) = _task_findings(overriding)
```

with:

```python
    assert found.code == "meaning-for-nothing" and "'speed'" in found.detail
    assert (found.blocking, found.accepted_in) == (False, ())
    assert found.detail.endswith("which is probably a mistake")
    (found,) = _task_findings(overriding)
```

**`tests/test_taskd.py`** (4 replacements, in order):

Replace:

```python
    discovers the task is malformed has already put an animal in a chair."""
    bad = tmp_path / "bad.py"
    bad.write_text(
        "from wl_xcon.task import NO_CHOICE, After, On, Outcome, ReactionTime, State, Task, Trial\n"
        "t = Trial(start='a', states=[State('a', go=[On(After(1.0), Outcome.CORRECT)]),"
        " State('orphan', go=[On(After(1.0), Outcome.CORRECT)])])\n"
        "TASK = Task({'t': t}, default='t', choice=NO_CHOICE,"
        " reaction_time=ReactionTime('a', (Outcome.CORRECT,), 'the wait'))\n"
```

with:

```python
    discovers the task is malformed has already put an animal in a chair."""
    bad = tmp_path / "bad.py"
    bad.write_text(
        "from wl_xcon.task import NO_CHOICE, After, On, Outcome, ReactionTime, State, Task, Trial\n"
        "t = Trial(start='a', states=[State('a', go=[On(After(1.0), Outcome.CORRECT)]),"
        " State('orphan', go=[On(After(1.0), Outcome.CORRECT)]), State('trap', go=[On(After(1.0), 'trap')])])\n"
        "TASK = Task({'t': t}, default='t', choice=NO_CHOICE,"
        " reaction_time=ReactionTime('a', (Outcome.CORRECT,), 'the wait'))\n"
```

Replace:

```python
    except SystemExit as exit_:
        assert "unreachable-state" in str(exit_)
```

with:

```python
    except SystemExit as exit_:
        assert "no-outcome-path" in str(exit_)
```

Replace:

```python
    the marks pass."""
    bad = tmp_path / "bad.py"
    bad.write_text(
        "from wl_xcon.task import NO_CHOICE, After, On, Outcome, ReactionTime, State, Task, Trial\n"
        "t = Trial(start='a', states=[State('a', go=[On(After(1.0), Outcome.CORRECT)]),"
        " State('orphan', go=[On(After(1.0), Outcome.CORRECT)])])\n"
        "TASK = Task({'t': t}, default='t', choice=NO_CHOICE,"
        " reaction_time=ReactionTime('a', (Outcome.CORRECT,), 'the wait'))\n"
```

with:

```python
    the marks pass."""
    bad = tmp_path / "bad.py"
    bad.write_text(
        "from wl_xcon.task import NO_CHOICE, After, On, Outcome, ReactionTime, State, Task, Trial\n"
        "t = Trial(start='a', states=[State('a', go=[On(After(1.0), Outcome.CORRECT)]),"
        " State('orphan', go=[On(After(1.0), Outcome.CORRECT)]), State('trap', go=[On(After(1.0), 'trap')])])\n"
        "TASK = Task({'t': t}, default='t', choice=NO_CHOICE,"
        " reaction_time=ReactionTime('a', (Outcome.CORRECT,), 'the wait'))\n"
```

Replace:

```python

    with pytest.raises(SystemExit, match="unreachable-state: no transition reaches 'orphan'"):
```

with:

```python

    with pytest.raises(SystemExit, match="no-outcome-path: state 'trap' cannot reach any terminal outcome"):
```

- [ ] **Step 2: Run them and see them fail**

Run: `$PY -m pytest -q -p no:cacheprovider tests/test_cli.py tests/test_range_checks.py tests/test_service.py tests/test_task_checks.py tests/test_task_object.py tests/test_taskd.py`
Expected: `6 failed, 765 passed`: `test_a_state_no_transition_can_reach_is_reported`, `test_a_transition_shadowed_by_an_earlier_identical_guard_is_reported`, `test_a_later_after_that_can_never_fire_first_is_a_review_note` and `test_an_override_of_nothing_is_refused_and_a_meaning_for_no_setting_is_a_review_note` on `(True, ())` against `(False, ())`; `test_a_task_with_a_blocking_finding_exits_one` (wlx check prints `refused  unreachable-state`); `test_a_task_with_a_state_nothing_reaches_runs_and_is_asked_nothing_about_it` (the task checks fail on the orphan).

- [ ] **Step 3: Implement**

**`wl_xcon/check.py`** (8 replacements, in order):

Replace:

```python
"""Load-time checks (S1 §9). A task failing any of these is refused at load."""
```

with:

```python
"""Load-time checks (S1 §9). A task failing any of these is refused at load.

**Three severities** (`findings.Finding`): a refusal (`blocking`); a warning, acceptable in the
session kinds it names and asked once a session (engine spec §19.2); and a review note
(`blocking=False`, no kinds), which `wlx check` shows and no session refuses or asks. Since the
PI's rulings on XC-352 (2026-10-11: "warnings are more appropriate most of the time with an
explanation of why it may not be a good idea to use a value or follow a path you may think to
refuse. the experimenter needs free control most of the time"), dead code is a review note and a
task the rig can run but should perhaps not is a warning saying why; a refusal is kept for what
is unrunnable, undeclared or would make the record uninterpretable."""
```

Replace:

```python
        if name not in declared:
            findings.append(Finding("meaning-for-nothing", (
                f"the task declares a meaning for {name!r}, which none of its structures "
                f"declares as a setting")))
```

with:

```python
        if name not in declared:
            # A review note, never a refusal (XC-352's A7; the PI, 2026-10-11): it can never take
            # effect.
            findings.append(Finding("meaning-for-nothing", (
                f"the task declares a meaning for {name!r}, which none of its structures "
                f"declares as a setting: it can never take effect, which is probably a mistake"),
                blocking=False))
```

Replace:

```python
def _unreachable_states(trial: Trial) -> list[Finding]:
    """S1 §9 check 2: every state is reachable from the start state."""
```

with:

```python
def _unreachable_states(trial: Trial) -> list[Finding]:
    """S1 §9 check 2: every state is reachable from the start state. One that is not can never
    take effect: **a review note, never a refusal** (XC-352's A7; the PI, 2026-10-11)."""
```

Replace:

```python
    return [
        Finding("unreachable-state", f"no transition reaches {name!r}")
```

with:

```python
    return [
        Finding("unreachable-state", (
            f"no transition reaches {name!r}: it can never take effect, which is probably a "
            f"mistake"), blocking=False)
```

Replace:

```python
    produces readily, since repeating a guard with a different destination looks
    entirely reasonable in isolation.
```

with:

```python
    produces readily, since repeating a guard with a different destination looks
    entirely reasonable in isolation. **A review note, never a refusal** (XC-352's A7;
    the PI, 2026-10-11).
```

Replace:

```python
                        f"state {state.name!r} repeats guard {edge.guard!r}; "
                        f"the later transition can never fire",
```

with:

```python
                        f"state {state.name!r} repeats guard {edge.guard!r}; "
                        f"the later transition can never fire, which is probably a mistake",
                        blocking=False,
```

Replace:

```python
    nobody notices -- the line is right there. Ranges again: two bounds whose ranges
    cross are both live, because either can win depending on the setting.
```

with:

```python
    nobody notices -- the line is right there. Ranges again: two bounds whose ranges
    cross are both live, because either can win depending on the setting. **A review note,
    never a refusal** (XC-352's A7; the PI, 2026-10-11): the state still has its other bound.
```

Replace:

```python
                        f"{_target_name(edge.to)} timeout: another `After` on the "
                        f"same state always fires first, for every legal setting",
```

with:

```python
                        f"{_target_name(edge.to)} timeout: another `After` on the "
                        f"same state always fires first, for every legal setting, which is "
                        f"probably a mistake",
                        blocking=False,
```

- [ ] **Step 4: Run them and see them pass**

Run the six files, then the whole suite. Expected: `771 passed`; the suite **3493 passed**.

- [ ] **Step 5: Prove they can fail**

- `_unreachable_states`' `blocking=False` removed: `test_a_state_no_transition_can_reach_is_reported` and `test_a_task_with_a_state_nothing_reaches_runs_and_is_asked_nothing_about_it` fail.
- `_shadowed_transitions`' `blocking=False,` removed: `test_a_transition_shadowed_by_an_earlier_identical_guard_is_reported` fails.
- `_unreachable_timeouts`' `blocking=False,` removed: `test_a_later_after_that_can_never_fire_first_is_a_review_note` fails.
- `meaning-for-nothing`'s `blocking=False` removed: `test_an_override_of_nothing_is_refused_and_a_meaning_for_no_setting_is_a_review_note` fails.

- [ ] **Step 6: Commit**

```bash
git add wl_xcon/check.py tests/
git commit -m "Make dead code a review note, never a refusal"
```
Body: XC-352's A7 (the PI, 2026-10-11: "review notes only"); call 2; the count; the breaks seen failing.

---

### Task 3: Overlapping windows, a crowded array, a wrong-eye criterion, a monocular stereogram and the wrong setup are warnings (XC-352's A8-A12)

Each warns in every session kind with a sentence saying why it may not be a good idea. The wrong setup stays refused where an unmirrored screen cannot show what the task shows each eye (stereo content, and now a position or a background per eye: `_per_eye_content`), and the field check still holds a task to the setup it runs in, so the reference detection task, whose ±16° the stereoscope's ±12° mask cannot show, is still refused there, for that.

**Files:**
- Modify: `wl_xcon/check.py` (`_stereogram_faults`, `_eye_faults`, `_overlapping_windows`, `_crowded_arrays`, `_view_faults`, new `_per_eye_content`)
- Modify (test): `tests/test_range_checks.py`, `tests/test_per_eye.py`, `tests/test_disparity.py`, `tests/test_task_checks.py`, `tests/test_reference_tasks.py`, `tests/test_preflight.py`, `tests/test_cli.py`, `tests/test_taskd.py`, `tests/test_service.py`
- Modify (docs): `docs/pitfalls.md` (P20)

**Interfaces:**
- Consumes: `_stereo_content`, `actions_of`, `Show`, `Update`, `SESSION_KINDS` (in `check.py` already).
- Produces: `overlapping-windows`, `crowded-array`, `wrong-eye-criterion`, `monocular-stereogram` and, without stereo or per-eye content, `wrong-setup`, each `blocking=False, accepted_in=SESSION_KINDS`; `check._per_eye_content(trial) -> list[str]`. `check.BREAKS_A_RUN` (Task 10) names the first two.

- [ ] **Step 1: Write the failing tests**

**`tests/test_cli.py`**:

Replace:

```python

    assert "wrong-setup" in str(refused.value)
    assert "'direct'" in str(refused.value) and "'stereoscope'" in str(refused.value)
```

with:

```python

    # The setups' mismatch is a warning (XC-352's A12); the reference task's ±16° beyond the
    # stereoscope's ±12° mask still refuses, before anything is recorded.
    assert "stimulus-off-screen" in str(refused.value) and "wrong-setup" not in str(refused.value)
```

**`tests/test_disparity.py`** (3 replacements, in order):

Replace:

```python
from wl_xcon.check import check
from wl_xcon.task import (
```

with:

```python
from wl_xcon.check import check
from wl_xcon.findings import SESSION_KINDS
from wl_xcon.task import (
```

Replace:

```python

def test_a_stereogram_shown_to_one_eye_only_is_refused():
```

with:

```python

def test_a_stereogram_shown_to_one_eye_only_is_a_warning_not_to_analyze_it_as_disparity():
```

Replace:

```python
    Monocular presentation of one is not a degraded version of the stimulus, it is
    a field of random dots with no disparity at all -- and it would still run,
    still record, and still appear in a figure as a disparity condition.
    """
    assert "monocular-stereogram" in codes(a_task(RDS(), eye="left"))
```

with:

```python
    Monocular presentation of one is not a degraded version of the stimulus, it is
    a field of random dots with no disparity at all. **A warning, not a refusal** (XC-352's
    A11; the PI, 2026-10-11): a monocular control is a thing an experimenter may want, and
    the warning says not to analyze those trials as a disparity condition.
    """
    (warning,) = [f for f in check(a_task(RDS(), eye="left")) if f.code == "monocular-stereogram"]
    assert (warning.blocking, warning.accepted_in) == (False, SESSION_KINDS)
    assert "not a disparity condition" in warning.detail
```

**`tests/test_per_eye.py`** (3 replacements, in order):

Replace:

```python
from wl_xcon.check import check
from wl_xcon.run import run_trial
```

with:

```python
from wl_xcon.check import check
from wl_xcon.findings import SESSION_KINDS
from wl_xcon.run import run_trial
```

Replace:

```python

def test_scoring_one_eye_against_a_stimulus_the_other_eye_sees_is_refused():
```

with:

```python

def test_scoring_one_eye_against_a_stimulus_the_other_eye_sees_is_a_warning():
```

Replace:

```python
    )
    assert "wrong-eye-criterion" in {f.code for f in check(trial)}
```

with:

```python
    )
    (warning,) = [f for f in check(trial) if f.code == "wrong-eye-criterion"]
    # A warning, not a refusal (XC-352's A10; the PI, 2026-10-11), saying why.
    assert (warning.blocking, warning.accepted_in) == (False, SESSION_KINDS)
    assert "the animal can do the task perfectly with the seeing eye" in warning.detail
```

**`tests/test_preflight.py`**:

Replace:

```python

def test_a_task_written_for_the_other_setup_fails_naming_the_finding():
    item, _, _ = preflight.task(TASK, ALLOCATION, STEREOSCOPE, SRGB)

    assert item.result == "fail" and "wrong-setup" in item.said
```

with:

```python

def test_a_task_written_for_the_other_setup_fails_on_its_field_and_warns_of_its_setup():
    """XC-352's A12: the setups' mismatch is a warning; the reference task's ±16° beyond the
    stereoscope's mask still fails (A15, kept)."""
    item, _, findings = preflight.task(TASK, ALLOCATION, STEREOSCOPE, SRGB)

    assert item.result == "fail" and "stimulus-off-screen" in item.said
    assert "wrong-setup" not in item.said
    assert [f.code for f in findings if f.is_warning and f.code == "wrong-setup"] == ["wrong-setup"]
```

**`tests/test_range_checks.py`** (7 replacements, in order):

Replace:

```python
from wl_xcon.check import check
from wl_xcon.task import (
```

with:

```python
from wl_xcon.check import check
from wl_xcon.findings import SESSION_KINDS
from wl_xcon.task import (
```

Replace:

```python
    return {f.code for f in check(trial)}

```

with:

```python
    return {f.code for f in check(trial)}


def found(trial, code):
    """The one finding of `code` that `check` gives `trial`."""
    (one,) = [f for f in check(trial) if f.code == code]
    return one

```

Replace:

```python

def test_windows_that_overlap_are_refused():
```

with:

```python

def test_windows_that_overlap_are_a_warning_saying_a_look_at_one_can_count_as_the_other():
```

Replace:

```python

    Which is a coin flip decided by editing order, and it silently relabels errors
    as correct trials or the reverse -- in a task where nothing looks wrong.
    """
    assert "overlapping-windows" in codes(
        two_windows((0.0, 0.0), 3.0, (4.0, 0.0), 3.0)
    )
```

with:

```python

    Which is decided by editing order (M0 §4), and it can relabel errors as correct trials
    or the reverse -- in a task where nothing looks wrong. **A warning, not a refusal**
    (XC-352's A8; the PI, 2026-10-11: "the experimenter needs free control most of the
    time"), accepted in every session kind, saying so.
    """
    warning = found(two_windows((0.0, 0.0), 3.0, (4.0, 0.0), 3.0), "overlapping-windows")

    assert (warning.blocking, warning.accepted_in) == (False, SESSION_KINDS)
    assert "a look at one can count as the other" in warning.detail
```

Replace:

```python

def test_windows_that_overlap_only_at_an_extreme_of_a_range_are_refused():
```

with:

```python

def test_windows_that_overlap_only_at_an_extreme_of_a_range_are_found():
```

Replace:

```python

def test_array_objects_that_can_crowd_into_each_other_are_refused():
```

with:

```python

def test_array_objects_that_can_crowd_into_each_other_are_a_warning():
```

Replace:

```python
    )
    assert "crowded-array" in codes(trial)
```

with:

```python
    )
    warning = found(trial, "crowded-array")
    # A warning, not a refusal (XC-352's A9; the PI, 2026-10-11).
    assert (warning.blocking, warning.accepted_in) == (False, SESSION_KINDS)
    assert "a saccade to one would be scored against another" in warning.detail
```

**`tests/test_reference_tasks.py`**:

Replace:

```python

def test_a_direct_view_task_is_refused_in_the_stereoscope_naming_both(detection):
    """What direct view part 2's session start will say if the operator picks the
    stereoscope for this task: the mismatch, and the ±16° its mask cannot show."""
    allocation = _load("allocation", "ALLOCATION")
    codes = {f.code for f in check(detection, allocation, geometry=RIG.stereoscope(1.6))}

    assert codes == {"wrong-setup", "stimulus-off-screen"}
```

with:

```python

def test_a_direct_view_task_is_refused_in_the_stereoscope_for_its_field_and_warned_for_its_setup(
    detection,
):
    """What a session start says if the operator picks the stereoscope for this task: the ±16°
    its mask cannot show refuses (A15, kept), and the mismatch of setups is a warning (XC-352's
    A12; the PI, 2026-10-11)."""
    allocation = _load("allocation", "ALLOCATION")
    found = {f.code: f for f in check(detection, allocation, geometry=RIG.stereoscope(1.6))}

    assert set(found) == {"wrong-setup", "stimulus-off-screen"}
    assert found["stimulus-off-screen"].blocking and found["wrong-setup"].is_warning
```

**`tests/test_service.py`**:

Replace:

```python
    assert "unreachable-state" not in items["warnings"]["said"]
    assert started.run_index == 0

```

with:

```python
    assert "unreachable-state" not in items["warnings"]["said"]
    assert started.run_index == 0


def test_a_direct_view_task_runs_in_the_stereoscope_once_its_setup_warning_is_accepted(tmp_path):
    """XC-352's A12 (the PI, 2026-10-11): a task written for direct view, whose stimuli the
    stereoscope's ±12° mask can show, runs there: its task checks pass, its warnings item asks
    for `wrong-setup` with what the stereoscope changes, and a start accepting it runs, recording
    it in `warnings.jsonl`."""
    service = _service(tmp_path)
    text = Path("tasks/fixation_detection.py").read_text()
    for axis, start in (("x", "10.0"), ("y", "0.0")):
        wide = f'Param("target_{axis}", unit="deg", low=-16.0, high=16.0, start={start})'
        assert text.count(wide) == 1
        text = text.replace(wide, f'Param("target_{axis}", unit="deg", low=-10.0, high=10.0, start={start})')
    (service.tasks / "narrow.py").write_text(text)
    _step(service, _open(view="stereoscope"))

    checked = _step(service, CheckRun(by=BY, task="narrow.py", values=dict(VALUES)))
    started = _step(service, _start(task="narrow.py"))

    items = {i.name: i for i in checked.preflight.items}
    assert items["task checks"].result == "pass"
    assert items["warnings"].result == "unknown"
    assert "wrong-setup: the task is written for 'direct'" in items["warnings"].said
    assert started.run_index == 0
    warned = _jsonl(service.root / "2027-01-14_01" / "xcon" / "warnings.jsonl")
    assert [row["how"] for row in warned if row["code"] == "wrong-setup"] == ["start"]

```

**`tests/test_task_checks.py`** (3 replacements, in order):

Replace:

```python
from wl_xcon.check import check
from dataclasses import replace
```

with:

```python
from wl_xcon.check import check
from wl_xcon.findings import SESSION_KINDS
from dataclasses import replace
```

Replace:

```python

def test_a_task_written_for_one_setup_is_refused_in_the_other_naming_both():
    """Spec §3: "a stereoscope task in direct view, or a direct task in the
    stereoscope" -- the refusal part 2's session start will show, naming both
    sides."""
```

with:

```python

def test_a_task_written_for_one_setup_is_a_warning_in_the_other_naming_both():
    """Spec §3: "a stereoscope task in direct view, or a direct task in the stereoscope".
    **A warning, not a refusal, when it shows nothing that needs each eye its own image**
    (XC-352's A12; the PI, 2026-10-11): it runs, and the warning says what the other setup
    changes. The field check still holds it to the setup it runs in."""
```

Replace:

```python
    assert in_direct.code == in_stereoscope.code == "wrong-setup"
    assert "written for 'stereoscope'" in in_direct.detail
    assert "checked against 'direct'" in in_direct.detail
    assert "written for 'direct'" in in_stereoscope.detail
    assert "checked against 'stereoscope'" in in_stereoscope.detail
    assert check(_task(view="direct"), geometry=DIRECT) == []
    assert check(_task(view="stereoscope"), geometry=GEOMETRY) == []

```

with:

```python
    assert in_direct.code == in_stereoscope.code == "wrong-setup"
    for warning in (in_direct, in_stereoscope):
        assert (warning.blocking, warning.accepted_in) == (False, SESSION_KINDS)
    assert "written for 'stereoscope'" in in_direct.detail
    assert "checked against 'direct'" in in_direct.detail
    assert "both eyes see the whole panel" in in_direct.detail
    assert "written for 'direct'" in in_stereoscope.detail
    assert "checked against 'stereoscope'" in in_stereoscope.detail
    assert "each eye sees its own half of the panel, inside the ±12° mask" in in_stereoscope.detail
    assert check(_task(view="direct"), geometry=DIRECT) == []
    assert check(_task(view="stereoscope"), geometry=GEOMETRY) == []


@pytest.mark.parametrize("shown", [
    Show(Stimulus("d", at=(1.0, 0.0), looks=LIT, disparity=0.2)),
    Show(Stimulus("l", at=(1.0, 0.0), looks=LIT, eye="left")),
    Show(Stimulus("p", at=(0.0, 0.0), looks=LIT, at_left=(1.0, 0.0), at_right=(-1.0, 0.0))),
], ids=["a disparity", "one eye", "a position per eye"])
def test_a_stereoscope_task_that_shows_each_eye_its_own_image_is_refused_in_direct_view(shown):
    """What an unmirrored screen cannot show stays refused (XC-352's A12: "`needs-stereoscope`
    and the field check still refuse"): both eyes would see both images, so the record would
    not describe what was shown."""
    (refusal,) = check(_task(shown, view="stereoscope"), geometry=DIRECT)

    assert refusal.code == "wrong-setup" and refusal.blocking
    assert "which an unmirrored screen cannot show" in refusal.detail


def test_a_stereoscope_task_with_a_background_per_eye_is_refused_in_direct_view():
    """Engine spec §4.4: each eye's own background is the stereoscope's; an unmirrored screen
    has one."""
    task = replace(_task(view="stereoscope"), background_left=Gray(10.0), background_right=Gray(20.0))

    (refusal,) = [f for f in check(task, geometry=DIRECT) if f.code == "wrong-setup"]

    assert refusal.blocking and "it gives each eye its own background" in refusal.detail

```

**`tests/test_taskd.py`**:

Replace:

```python

    assert "wrong-setup" in str(refused.value)
    assert "'direct'" in str(refused.value) and "'stereoscope'" in str(refused.value)
```

with:

```python

    # The setups' mismatch is a warning (XC-352's A12); its ±16° beyond the mask still refuses.
    assert "stimulus-off-screen" in str(refused.value) and "wrong-setup" not in str(refused.value)
```

- [ ] **Step 2: Run them and see them fail**

Run: `$PY -m pytest -q -p no:cacheprovider tests/test_cli.py tests/test_disparity.py tests/test_per_eye.py tests/test_preflight.py tests/test_range_checks.py tests/test_reference_tasks.py tests/test_service.py tests/test_task_checks.py tests/test_taskd.py`
Expected: `14 failed, 868 passed`: each warning's test on its `(True, ())` against `(False, SESSION_KINDS)`; the four stereoscope-in-direct-view refusals on the missing "which an unmirrored screen cannot show"; the reference task's, the pre-flight's, `wlx run`'s and `Session.run`'s on `wrong-setup` still refusing; the service test on the task checks failing in the stereoscope.

- [ ] **Step 3: Implement**

**`wl_xcon/check.py`** (10 replacements, in order):

Replace:

```python
        if getattr(stimulus, "eye", "both") != "both":
            findings.append(
```

with:

```python
        if getattr(stimulus, "eye", "both") != "both":
            # A warning, not a refusal (XC-352's A11; the PI, 2026-10-11): a monocular control
            # is the experimenter's to choose; the warning says what its trials are not.
            findings.append(
```

Replace:

```python
                    f"state {state!r} shows a stereogram to the "
                    f"{stimulus.eye} eye only; monocular presentation of one half "
                    f"is not a degraded stereogram, it is a field of random dots "
                    f"with no disparity -- and it would still run, still record, "
                    f"and still appear in a figure as a disparity condition",
```

with:

```python
                    f"state {state!r} shows a stereogram to the "
                    f"{stimulus.eye} eye only; with one eye there is no disparity, only a "
                    f"field of random dots, so these trials are not a disparity condition and "
                    f"are not to be analyzed as one (the task, which each run names by its "
                    f"content hash, says which eye)",
                    blocking=False,
                    accepted_in=SESSION_KINDS,
```

Replace:

```python
    every trial for a reason invisible in the data: the animal was doing the task
    perfectly with the eye nobody scored.
```

with:

```python
    every trial for a reason invisible in the data: the animal was doing the task
    perfectly with the eye nobody scored. **A warning, not a refusal** (XC-352's A10; the
    PI, 2026-10-11), saying so; an eye that is not one of `EYES` is still refused.
```

Replace:

```python
                    f"{on!r}, which is shown only to the {stimulus_eye} eye; the "
                    f"animal can do the task perfectly and abort every trial",
```

with:

```python
                    f"{on!r}, which is shown only to the {stimulus_eye} eye; the "
                    f"animal can do the task perfectly with the seeing eye and fail every "
                    f"trial, for a reason the data will not show",
                    blocking=False,
                    accepted_in=SESSION_KINDS,
```

Replace:

```python
    states are never both live, and a task that reuses a position across states is
    doing something ordinary.
```

with:

```python
    states are never both live, and a task that reuses a position across states is
    doing something ordinary. **A warning, not a refusal** (XC-352's A8; the PI,
    2026-10-11): the order is defined (M0 §4) and is part of the task's content, which each
    run names by its hash.
```

Replace:

```python
                            f"satisfies both guards, and which one scores is decided "
                            f"by the order the transitions happen to be written in",
```

with:

```python
                            f"satisfies both guards, and which one scores is decided "
                            f"by the order the transitions happen to be written in, so "
                            f"a look at one can count as the other",
                            blocking=False,
                            accepted_in=SESSION_KINDS,
```

Replace:

```python
    adjacent centres are `2 R sin(pi/n)` apart, and two windows touch when that
    falls below their summed radius.
```

with:

```python
    adjacent centres are `2 R sin(pi/n)` apart, and two windows touch when that
    falls below their summed radius. **A warning, not a refusal** (XC-352's A9; the PI,
    2026-10-11), saying which settings crowd it.
```

Replace:

```python
                    f"saccade to one would be scored against another",
                )
```

with:

```python
                    f"saccade to one would be scored against another",
                    blocking=False,
                    accepted_in=SESSION_KINDS,
                )
```

Replace:

```python
    property of the task, not of the session, so it is refused at every load. **Against
    a geometry, a task written for the other setup is refused, naming both**, so a
    caller that passes the session's geometry has nothing else to do. `taskd` and
```

with:

```python
    property of the task, not of the session, so it is refused at every load. **Against
    a geometry, a task written for the other setup is a warning, naming both and saying what
    the other setup changes** (XC-352's A12; the PI, 2026-10-11), unless it is a stereoscope
    task that shows each eye its own image -- a disparity, one eye, a position or a
    background per eye (`_per_eye_content`) -- in direct view, which an unmirrored screen
    cannot show, and that stays refused. The field check holds it to the setup it runs in
    (`_offscreen_stimuli`), so a caller that passes the session's geometry has nothing else
    to do. `taskd` and
```

Replace:

```python
    if geometry is not None and trial.view not in ("either", geometry.view):
        findings.append(
            Finding(
                "wrong-setup",
                f"the task is written for {trial.view!r} and is checked against "
                f"{geometry.view!r}; a task written for one setup is refused in the "
                f"other (direct-view spec §3)",
            )
        )
    return findings


```

with:

```python
    if geometry is not None and trial.view not in ("either", geometry.view):
        written = (f"the task is written for {trial.view!r} and is checked against "
                   f"{geometry.view!r}")
        both = _stereo_content(trial) + _per_eye_content(trial)
        if geometry.view == "direct" and both:
            findings.append(Finding("wrong-setup", (
                f"{written}: {both[0]}, which an unmirrored screen cannot show, since each eye "
                f"would see both images (direct-view spec §3)")))
        elif geometry.view == "direct":
            findings.append(Finding("wrong-setup", (
                f"{written}: here both eyes see the whole panel, unmirrored, at "
                f"{geometry.viewing_distance_cm:g} cm; it shows nothing that needs each eye "
                f"its own image, so it runs, but it was not designed for this setup "
                f"(direct-view spec §3)"), blocking=False, accepted_in=SESSION_KINDS))
        else:
            stop = ("its field" if geometry.mask_deg is None
                    else f"the ±{geometry.mask_deg:g}° mask")
            findings.append(Finding("wrong-setup", (
                f"{written}: here each eye sees its own half of the panel, inside "
                f"{stop}, through the mirrors at "
                f"{geometry.viewing_distance_cm:.2f} cm; its positions and sizes are degrees, so "
                f"they hold, but it was not designed for this setup (direct-view spec §3)"),
                blocking=False, accepted_in=SESSION_KINDS))
    return findings


def _per_eye_content(trial: Trial) -> list[str]:
    """What a stereoscope task shows each eye that `_stereo_content` does not name: a position
    per eye (engine spec §5.4), by a `Show` or an `Update`, and a background per eye (§4.4). An
    unmirrored screen cannot show either, so neither runs in direct view (`_view_faults`)."""
    found = []
    for state, action in actions_of(trial):
        if isinstance(action, Show) and (
            action.stimulus.at_left is not None or action.stimulus.at_right is not None
        ):
            found.append(f"state {state!r} gives {action.stimulus.name!r} a position per eye")
        elif isinstance(action, Update) and any(
            action.changes().get(eye) is not None for eye in ("at_left", "at_right")
        ):
            found.append(f"state {state!r} gives {action.stimulus!r} a position per eye")
    if trial.background_left is not None or trial.background_right is not None:
        found.append("it gives each eye its own background")
    return found


```

The doc it invalidates:

**`docs/pitfalls.md`**:

Replace:

```markdown
Mitigation: anything a parameter generates gets a check reasoning over the declared
ranges, not the current values.
```

with:

```markdown
Mitigation: anything a parameter generates gets a check reasoning over the declared
ranges, not the current values. *Since the PI's rulings on XC-352 (2026-10-11)* the crowding
check, like the overlapping-windows one, is a warning a person accepts with its reason rather
than a refusal ("the experimenter needs free control most of the time"); the check still runs
on every load, and a value a console sends outside the declared range is checked again with the
range widened to it, and refused if it newly crowds the array (`check.BREAKS_A_RUN`).
```

- [ ] **Step 4: Run them and see them pass**

Run the nine files, then the whole suite. Expected: `882 passed`; the suite **3498 passed**.

- [ ] **Step 5: Prove they can fail**

- `overlapping-windows`' `blocking=False, accepted_in=SESSION_KINDS,` removed: `test_windows_that_overlap_are_a_warning_saying_a_look_at_one_can_count_as_the_other` fails.
- `crowded-array`'s removed: `test_array_objects_that_can_crowd_into_each_other_are_a_warning` fails.
- `wrong-eye-criterion`'s removed: `test_scoring_one_eye_against_a_stimulus_the_other_eye_sees_is_a_warning` fails.
- `monocular-stereogram`'s removed: `test_a_stereogram_shown_to_one_eye_only_is_a_warning_not_to_analyze_it_as_disparity` fails.
- `_view_faults`' `if geometry.view == "direct" and both:` → `if geometry.view == "direct" and False:`: the three cases of `test_a_stereoscope_task_that_shows_each_eye_its_own_image_is_refused_in_direct_view` fail.
- `_per_eye_content`'s `return found` → `return []`: its "a position per eye" case and `test_a_stereoscope_task_with_a_background_per_eye_is_refused_in_direct_view` fail.
- The stereoscope branch's `blocking=False, accepted_in=SESSION_KINDS` removed: `test_a_task_written_for_one_setup_is_a_warning_in_the_other_naming_both`, the service's, the reference task's and the pre-flight's tests fail.

- [ ] **Step 6: Commit**

```bash
git add wl_xcon/check.py tests/ docs/pitfalls.md
git commit -m "Make overlapping windows, a crowded array, a wrong-eye criterion, a monocular stereogram and the wrong setup warnings"
```
Body: XC-352's A8-A12 (the PI, 2026-10-11, approving the audit's proposals); A13 and A15 kept (stereo content outside the stereoscope, the field); call 14; the count; the breaks seen failing.

---

### Task 4: The default calibration's colors are warnings in recording too, and isoluminance on it a warning everywhere (XC-352's A21, A19)

`color-on-default` and `contrast-on-default` are accepted in every kind, saying that every color or luminance is nominal and that the session's `config.json` names the default; `isoluminance-on-default` is a warning in every kind that the colors are only nominally isoluminant, **one per task naming each color that claims it** (the review's M8; engine build B's Task 4 review had each choice named in a finding of its own, five near-identical sentences for the search task). An isoluminant color is now still held to the panel's reach, which shows the search task's red and green just outside the sRGB standard's gamut (refused here as `unrealizable-color` until Task 5 makes that a warning; the search task was refused on the default before this task too). The tests of `Session.run`'s, `wlx run`'s and `wlx check`'s refusal of a warning outside its kinds keep that mechanism tested with a stand-in finding, since no real one is now.

**Files:**
- Modify: `wl_xcon/check.py` (imports; `_color_faults`, `_default_faults`), `wl_xcon/findings.py` (`NOT_RECORDING`'s comment)
- Modify (test): `tests/test_color.py`, `tests/test_reference_tasks.py`, `tests/test_service.py`, `tests/test_taskd.py`, `tests/test_cli.py`
- Modify (docs): `docs/pitfalls.md` (P19)

**Interfaces:**
- Produces: `isoluminance-on-default` (one per task, "…; the colors that claim it: <each>"), `color-on-default`, `contrast-on-default`, each `blocking=False, accepted_in=SESSION_KINDS`. `check.py` no longer imports `NOT_RECORDING`.

- [ ] **Step 1: Write the failing tests**

**`tests/test_cli.py`** (5 replacements, in order):

Replace:

```python
)
from wl_xcon.findings import SESSION_KINDS, Finding
```

with:

```python
)
from wl_xcon.findings import NOT_RECORDING, SESSION_KINDS, Finding
```

Replace:

```python
    assert "calibration: srgb-standard (the sRGB standard, measured by nobody)" in out
    assert "warning  contrast-on-default" in out and "(accepted in training, piloting)" in out
```

with:

```python
    assert "calibration: srgb-standard (the sRGB standard, measured by nobody)" in out
    assert "warning  contrast-on-default" in out
    assert "(accepted in training, piloting, recording)" in out
```

Replace:

```python
@pytest.mark.parametrize("kind, code", [("training", 0), ("piloting", 0), ("recording", 1)])
def test_wlx_check_for_a_kind_refuses_a_warning_that_kind_does_not_accept(kind, code):
```

with:

```python
@pytest.mark.parametrize("kind, code", [("training", 0), ("piloting", 0), ("recording", 1)])
def test_wlx_check_for_a_kind_refuses_a_warning_that_kind_does_not_accept(kind, code, monkeypatch):
    """No finding is accepted in fewer kinds since COL-02's revision (the PI, 2026-10-11), so a
    stand-in is; the reference task checks clean in every kind (below)."""
    monkeypatch.setattr(cli, "check_task", lambda *a, **k: [Finding(
        "color-on-default", "names colors", blocking=False, accepted_in=NOT_RECORDING)])
```

Replace:

```python
                 "--kind", kind]) == code

```

with:

```python
                 "--kind", kind]) == code


@pytest.mark.parametrize("kind", ["training", "piloting", "recording"])
def test_wlx_check_passes_the_reference_task_on_the_default_in_every_kind(kind):
    """COL-02, revised (the PI, 2026-10-11, XC-352's A21): a warning in recording too."""
    assert main(["check", GOOD, "--rig", RIG_FILE, "--allocation", ALLOCATION, "--view", "direct",
                 "--kind", kind]) == 0

```

Replace:

```python

def test_wlx_run_refuses_a_task_its_kind_does_not_accept_before_anything_is_recorded(tmp_path):
    argv = _run_args(tmp_path, "--out-of-cage-at", _hhmm())
    argv[argv.index("tasks/fixation_detection.py")] = "tasks/visual_search_training.py"
```

with:

```python

def test_wlx_run_refuses_a_task_its_kind_does_not_accept_before_anything_is_recorded(
    tmp_path, monkeypatch
):
    """A stand-in finding: none is accepted in fewer kinds since COL-02's revision (2026-10-11)."""
    monkeypatch.setattr(cli, "check_task", lambda *a, **k: [Finding(
        "color-on-default", "names colors", blocking=False, accepted_in=NOT_RECORDING)])
    argv = _run_args(tmp_path, "--out-of-cage-at", _hhmm())
```

**`tests/test_color.py`** (19 replacements, in order):

Replace:

```python
from wl_xcon.cones import CIE2006_10
from wl_xcon.findings import NOT_RECORDING
```

with:

```python
from wl_xcon.cones import CIE2006_10
from wl_xcon.findings import SESSION_KINDS
```

Replace:

```python

def test_isoluminance_needs_a_measured_calibration_in_every_kind():
    found = _found(a_task(Disc(color=DKL(lum=0.0, l_m=0.08))))

    assert found["isoluminance-on-default"].blocking
    assert "measured calibration" in found["isoluminance-on-default"].detail
```

with:

```python

def test_isoluminance_on_the_default_is_a_warning_in_every_kind_that_it_is_only_nominal():
    """COL-03, revised (the PI, 2026-10-11, XC-352's A19: "a warning everywhere"): isoluminance on
    the sRGB default is accepted in every session kind, and the warning says the colors are only
    nominally isoluminant on an unmeasured panel."""
    warning = _found(a_task(Disc(color=DKL(lum=0.0, l_m=0.08))))["isoluminance-on-default"]

    assert (warning.blocking, warning.accepted_in) == (False, SESSION_KINDS)
    assert "only nominally isoluminant on an unmeasured panel" in warning.detail
```

Replace:

```python

def test_a_cone_color_on_the_default_trains_and_pilots_with_the_warning():
    """Engine build A2 (B's call 9 retired): a DKL color that claims no isoluminance, or a cone
    contrast that does not, converts through the CIE's matrix on the default and is refused only
    in recording, by `color-on-default`, whose sentence says how it converted and which luminance
    it held (2026-10-08's Q2; COL-18; the review's S-I2)."""
```

with:

```python

def test_a_cone_color_on_the_default_runs_in_every_kind_with_the_warning():
    """Engine build A2 (B's call 9 retired): a DKL color that claims no isoluminance, or a cone
    contrast that does not, converts through the CIE's matrix on the default with `color-on-default`,
    accepted in every kind since COL-02's revision (the PI, 2026-10-11, XC-352's A21: "a warning in
    recording too"), whose sentence says how it converted and which luminance it held (2026-10-08's
    Q2; COL-18; the review's S-I2)."""
```

Replace:

```python
        assert [f.code for f in found] == ["color-on-default"], color
        assert found[0].accepted_in == NOT_RECORDING
```

with:

```python
        assert [f.code for f in found] == ["color-on-default"], color
        assert found[0].accepted_in == SESSION_KINDS
```

Replace:

```python

def test_a_dkl_color_that_can_be_isoluminant_is_refused_on_the_default_whatever_its_parameters():
```

with:

```python

def test_a_dkl_color_that_can_be_isoluminant_is_warned_of_on_the_default_whatever_its_parameters():
```

Replace:

```python
        trial = replace(a_task(Disc(color=color)), background=GRAY_BG, params=[contrast, up])
        assert _found(trial)["isoluminance-on-default"].blocking, color
```

with:

```python
        trial = replace(a_task(Disc(color=color)), background=GRAY_BG, params=[contrast, up])
        assert _found(trial)["isoluminance-on-default"].is_warning, color
```

Replace:

```python

def test_a_named_color_on_the_default_is_refused_only_in_recording():
```

with:

```python

def test_a_named_color_on_the_default_is_a_warning_in_every_kind_naming_the_record():
    """COL-02, revised (the PI, 2026-10-11, XC-352's A21: "a warning in recording too"; the record
    names the default)."""
```

Replace:

```python
    warning = found["color-on-default"]
    assert (warning.blocking, warning.accepted_in) == (False, NOT_RECORDING)
    assert "Disc" in warning.detail


def test_a_light_a_parameter_sets_is_refused_only_in_recording_on_the_default():
```

with:

```python
    warning = found["color-on-default"]
    assert (warning.blocking, warning.accepted_in) == (False, SESSION_KINDS)
    assert "Disc" in warning.detail
    assert "the session's config.json names the default calibration" in warning.detail


def test_a_light_a_parameter_sets_is_a_warning_in_every_kind_on_the_default():
```

Replace:

```python
    assert "'lum'" in found["contrast-on-default"].detail
    assert found["contrast-on-default"].accepted_in == NOT_RECORDING
```

with:

```python
    assert "'lum'" in found["contrast-on-default"].detail
    assert found["contrast-on-default"].accepted_in == SESSION_KINDS
    assert "the session's config.json names the default calibration" in found["contrast-on-default"].detail
```

Replace:

```python
    trial = replace(_showing(P("op")), params=[Param("op", unit="fraction", low=0.2, high=1.0)])

    found = _found(trial)

    assert "'op'" in found["contrast-on-default"].detail
    assert found["contrast-on-default"].refuses("recording")


```

with:

```python
    trial = replace(_showing(P("op")), params=[Param("op", unit="fraction", low=0.2, high=1.0)])

    found = _found(trial)

    assert "'op'" in found["contrast-on-default"].detail
    assert found["contrast-on-default"].is_warning


```

Replace:

```python

    found = _found(trial)

    assert "'op'" in found["contrast-on-default"].detail
    assert found["contrast-on-default"].refuses("recording")
    assert "contrast-on-default" not in _found(_showing(1.0, Update("s", at=(1.0, 0.0))))
```

with:

```python

    found = _found(trial)

    assert "'op'" in found["contrast-on-default"].detail
    assert found["contrast-on-default"].is_warning
    assert "contrast-on-default" not in _found(_showing(1.0, Update("s", at=(1.0, 0.0))))
```

Replace:

```python
        assert "'looks'" in found["contrast-on-default"].detail
        assert found["contrast-on-default"].refuses("recording")
```

with:

```python
        assert "'looks'" in found["contrast-on-default"].detail
        assert found["contrast-on-default"].is_warning
```

Replace:

```python
def test_each_choice_of_an_appearance_parameter_is_named_in_its_own_finding():
    """Task 4's review: the search task's five isoluminant choices were five identical lines."""
    red, green = DKL(lum=0.0, l_m=0.08), DKL(lum=0.0, l_m=-0.08)
    found = check(_choosing(Disc(size=1.0, color=red), Square(size=1.0, color=green)),
                  calibration=SRGB)

    details = [f.detail for f in found if f.code == "isoluminance-on-default"]

    assert len(details) == 2
    assert details[0].startswith("Disc (choice 1 of parameter 'looks') claims isoluminance")
    assert details[1].startswith("Square (choice 2 of parameter 'looks') claims isoluminance")
    shared = Disc(size=1.0, color=red)
    twice = replace(_choosing(shared), params=[
        Param("looks", unit="appearance", choices=(shared,)),
        Param("other", unit="appearance", choices=(Square(size=1.0, color=green), shared)),
    ])
    assert any(f.detail.startswith(
        "Disc (choice 1 of parameter 'looks', choice 2 of parameter 'other') claims")
        for f in check(twice, calibration=SRGB))
```

with:

```python
def test_one_warning_names_each_isoluminant_choice_of_an_appearance_parameter():
    """Task 4's review: the search task's five isoluminant choices were five identical lines, so
    each was named in its own finding. **One warning per task names each** since the
    warnings-over-refusals review's M8, as `color-on-default` names its colors: five findings ran
    the search task's warnings item to thousands of characters."""
    red, green = DKL(lum=0.0, l_m=0.08), DKL(lum=0.0, l_m=-0.08)
    found = check(_choosing(Disc(size=1.0, color=red), Square(size=1.0, color=green)),
                  calibration=SRGB)

    (detail,) = [f.detail for f in found if f.code == "isoluminance-on-default"]

    assert detail.endswith("the colors that claim it: Disc (choice 1 of parameter 'looks'); "
                           "Square (choice 2 of parameter 'looks')")
    shared = Disc(size=1.0, color=red)
    twice = replace(_choosing(shared), params=[
        Param("looks", unit="appearance", choices=(shared,)),
        Param("other", unit="appearance", choices=(Square(size=1.0, color=green), shared)),
    ])
    (detail,) = [f.detail for f in check(twice, calibration=SRGB)
                 if f.code == "isoluminance-on-default"]
    assert "Disc (choice 1 of parameter 'looks', choice 2 of parameter 'other')" in detail
```

Replace:

```python
    warning = _found(trial)["color-on-default"]

    assert (warning.blocking, warning.accepted_in) == (False, NOT_RECORDING)
```

with:

```python
    warning = _found(trial)["color-on-default"]

    assert (warning.blocking, warning.accepted_in) == (False, SESSION_KINDS)
```

Replace:

```python

def test_a_cone_contrast_with_one_isoluminant_chromatic_choice_is_refused_on_the_default():
```

with:

```python

def test_a_cone_contrast_with_one_isoluminant_chromatic_choice_is_warned_of_on_the_default():
```

Replace:

```python
                     Param("c", unit="contrast", choices=(0.1, 0.5)))

    assert found["isoluminance-on-default"].blocking
```

with:

```python
                     Param("c", unit="contrast", choices=(0.1, 0.5)))

    assert found["isoluminance-on-default"].is_warning
```

Replace:

```python
    found = _found(trial)

    assert found["isoluminance-on-default"].blocking
```

with:

```python
    found = _found(trial)

    assert found["isoluminance-on-default"].is_warning
```

Replace:

```python
@pytest.mark.parametrize("written", ["fill", "outline"])
def test_an_isoluminant_color_a_looks_fill_or_outline_parameter_offers_is_refused_on_the_default(
```

with:

```python
@pytest.mark.parametrize("written", ["fill", "outline"])
def test_an_isoluminant_color_a_looks_fill_or_outline_parameter_offers_is_warned_of_on_the_default(
```

Replace:

```python
    parameter offers were never read, so an isoluminant DKL among them trained and piloted on
    the default with no `isoluminance-on-default`. It is refused in every kind, naming the
    parameter."""
    found = _found(_offered_by(written, DKL(l_m=0.1)))

    assert found["isoluminance-on-default"].blocking
```

with:

```python
    parameter offers were never read, so an isoluminant DKL among them trained and piloted on
    the default with no `isoluminance-on-default`. It is a warning in every kind (COL-03, revised
    2026-10-11), naming the parameter."""
    found = _found(_offered_by(written, DKL(l_m=0.1)))

    assert found["isoluminance-on-default"].is_warning
```

**`tests/test_reference_tasks.py`** (4 replacements, in order):

Replace:

```python
@pytest.mark.parametrize("name", sorted(REFERENCE))
def test_on_the_default_every_reference_task_trains_but_the_search_task(name):
    """Spec §7.2-7.3 on the four tasks: each runs in training on the default calibration, with
    its warning, except the search task's isoluminant colors; none records on it (Q2-A)."""
```

with:

```python
@pytest.mark.parametrize("name", sorted(REFERENCE))
def test_on_the_default_every_reference_task_runs_in_every_kind_with_its_warnings(name):
    """Spec §7.2-7.3 on the four tasks, as the PI revised COL-02 and COL-03 (2026-10-11, XC-352's
    A19 and A21): each runs on the default calibration in every session kind, recording included,
    with its warnings -- the search task's isoluminant colors among them. **But the search task's
    isoluminant red and green are just outside the sRGB standard's gamut** (a primary weight of
    -0.003 to -0.006), which its isoluminance refusal hid until then: `unrealizable-color` still
    refuses them here, until a light the panel cannot make is a warning (XC-352's A20)."""
```

Replace:

```python

    in_training = {f.code for f in found if f.refuses("training")}
    in_recording = {f.code for f in found if f.refuses("recording")}
    if name == "visual_search":
        assert in_training == {"isoluminance-on-default"}
        assert in_recording == {
            "isoluminance-on-default", "color-on-default", "contrast-on-default"}
    else:
        assert in_training == set()
        assert in_recording == {"contrast-on-default"}
```

with:

```python

    refusing = {f.code for f in found if any(f.refuses(kind) for kind in SESSION_KINDS)}
    warned = {f.code for f in found if f.is_warning}
    if name == "visual_search":
        assert refusing == {"unrealizable-color"}
        assert warned == {"isoluminance-on-default", "color-on-default", "contrast-on-default"}
    else:
        assert refusing == set() and warned == {"contrast-on-default"}
```

Replace:

```python

def test_the_training_variant_trains_on_the_default_and_never_records_on_it(training):
```

with:

```python

def test_the_training_variant_runs_on_the_default_in_every_kind_with_its_warnings(training):
    """COL-02, revised (the PI, 2026-10-11): a warning in recording too."""
```

Replace:

```python

    assert [f for f in found if f.refuses("training") or f.refuses("piloting")] == []
    assert {f.code for f in found if f.refuses("recording")} == {
        "color-on-default", "contrast-on-default"}
```

with:

```python

    assert [f for f in found if any(f.refuses(kind) for kind in SESSION_KINDS)] == []
    assert {f.code for f in found if f.is_warning} == {"color-on-default", "contrast-on-default"}
```

**`tests/test_service.py`** (2 replacements, in order):

Replace:

```python

def test_a_recording_session_refuses_a_run_whose_task_warning_recording_does_not_accept(tmp_path):
    """Review Focus 4, the pre-flight's side."""
```

with:

```python

def test_a_recording_session_on_the_default_runs_once_its_warnings_are_accepted(tmp_path):
    """COL-02, revised (the PI, 2026-10-11, XC-352's A21: "a warning in recording too"; the record
    names the default): a recording session's run of the reference task, on the default
    calibration, asks to accept `contrast-on-default` and starts once it is accepted; its
    config.json names the default."""
```

Replace:

```python
    _step(service, _open(session_kind="recording"))

    frame = _step(service, _start())

    assert frame.run_index is None
    (why,) = [r.why for r in frame.refusals if r.name == "start"]
    assert "warnings: a recording session does not accept contrast-on-default" in why
    assert not (service.root / "2027-01-14_01" / "xcon" / "runs.jsonl").exists()
```

with:

```python
    _step(service, _open(session_kind="recording"))

    asked = _step(service, _start(acknowledged=("pump calibration", "eye tracker")))
    started = _step(service, _start())

    item = {i.name: i for i in asked.preflight.items}["warnings"]
    assert item.result == "unknown" and "contrast-on-default" in item.said
    assert asked.run_index is None and started.run_index == 0
    folder = service.root / "2027-01-14_01" / "xcon"
    rows = _jsonl(folder / "warnings.jsonl")
    assert [(r["code"], r["session_kind"]) for r in rows if r["how"] == "start"][0] == (
        "contrast-on-default", "recording")
    calibration = json.loads((folder / "config.json").read_text())["calibration"]
    assert (calibration["id"], calibration["standard"]) == ("srgb-standard", True)
```

**`tests/test_taskd.py`** (2 replacements, in order):

Replace:

```python

def test_a_recording_session_refuses_a_task_its_kind_does_not_accept(tmp_path):
    """Review Focus 4, `Session.run`'s own backstop: the training variant names colors. **And
    nothing of the run is strobed or written** (the engine B final review): the animal is out of
    its cage, so the refusal is `run`'s alone, never `welfare.preflight`'s."""
    made = _sessions.session(tmp_path)
    made.spec.session_kind = "recording"
    made.spec.task = "tasks/visual_search_training.py"
```

with:

```python

def test_a_recording_session_refuses_a_task_its_kind_does_not_accept(tmp_path, monkeypatch):
    """Review Focus 4, `Session.run`'s own backstop: a warning its kind does not accept. No
    finding is one since COL-02's revision (the PI, 2026-10-11), so a stand-in is. **And nothing
    of the run is strobed or written** (the engine B final review): the animal is out of its cage,
    so the refusal is `run`'s alone, never `welfare.preflight`'s."""
    monkeypatch.setattr("wl_xcon.taskd.check_task", lambda *a, **k: [Finding(
        "color-on-default", "names colors", blocking=False, accepted_in=NOT_RECORDING)])
    made = _sessions.session(tmp_path)
    made.spec.session_kind = "recording"
```

Replace:

```python

def test_a_run_refused_by_its_backstop_writes_no_accepted_warning(tmp_path):
    """The engine B plan, call 23: the rows are written once both refusals pass."""
    made = _sessions.session(tmp_path)
    made.spec.session_kind = "recording"
    made.spec.task = "tasks/visual_search_training.py"
```

with:

```python

def test_a_run_refused_by_its_backstop_writes_no_accepted_warning(tmp_path, monkeypatch):
    """The engine B plan, call 23: the rows are written once both refusals pass."""
    monkeypatch.setattr("wl_xcon.taskd.check_task", lambda *a, **k: [Finding(
        "color-on-default", "names colors", blocking=False, accepted_in=NOT_RECORDING)])
    made = _sessions.session(tmp_path)
    made.spec.session_kind = "recording"
```

- [ ] **Step 2: Run them and see them fail**

Run: `$PY -m pytest -q -p no:cacheprovider tests/test_cli.py tests/test_color.py tests/test_reference_tasks.py tests/test_service.py tests/test_taskd.py`
Expected: `24 failed, 838 passed`: the isoluminance tests on `is_warning` (False), and `test_one_warning_names_each_isoluminant_choice_of_an_appearance_parameter` on two findings, one per choice; the color and contrast tests on `NOT_RECORDING` against `SESSION_KINDS`; the reference tasks' on the recording refusals; the service's recording run refused; `wlx check`'s kinds and its recording check exiting 1.

- [ ] **Step 3: Implement**

**`wl_xcon/check.py`** (8 replacements, in order):

Replace:

```python
from wl_xcon.components import Registry
from wl_xcon.findings import NOT_RECORDING, SESSION_KINDS, Finding
```

with:

```python
from wl_xcon.components import Registry
from wl_xcon.findings import SESSION_KINDS, Finding
```

Replace:

```python
    findings: list[Finding] = []
    for what, color in _colors(trial, params):
```

with:

```python
    findings: list[Finding] = []
    # Each color that claims isoluminance on the default, for the task's one warning, and where
    # that warning goes among the findings (the warnings-over-refusals review's M8).
    isoluminant: list[str] = []
    at = 0
    for what, color in _colors(trial, params):
```

Replace:

```python
                and _claims_isoluminance(color, params, panel, backgrounds)):
            # Spec §7.3: "Isoluminance needs a measured calibration", in every session (N§4
            # batch 1). Asked of the color as written, before its values are read, so a `lum`
            # whose range crosses 0 claims it too (XC-269).
            finding = Finding("isoluminance-on-default", (
                f"{what} claims isoluminance, which needs a measured calibration (engine spec "
                f"§7.3); the default calibration is the sRGB standard, measured by nobody"))
            if finding not in findings:
                findings.append(finding)
            continue
```

with:

```python
                and _claims_isoluminance(color, params, panel, backgrounds)):
            # Spec §7.3 asked a measured calibration for isoluminance; since COL-03's revision
            # (the PI, 2026-10-11, XC-352's A19: "a warning everywhere") it is a warning in every
            # kind, saying the colors are only nominally isoluminant: **one per task, naming each
            # color that claims it** (below; the warnings-over-refusals review's M8). Asked of the
            # color as written, before its values are read, so a `lum` whose range crosses 0
            # claims it too (XC-269). Its lights are still held to the panel's reach, below.
            if not isoluminant:
                at = len(findings)
            if what not in isoluminant:
                isoluminant.append(what)
```

Replace:

```python
                if finding not in findings:  # one value's corners can say the same
                    findings.append(finding)
    if panel is not None:
```

with:

```python
                if finding not in findings:  # one value's corners can say the same
                    findings.append(finding)
    if isoluminant:
        findings.insert(at, Finding("isoluminance-on-default", (
            f"the default calibration is the sRGB standard, measured by nobody, so this task's "
            f"colors that claim isoluminance are only nominally isoluminant on an unmeasured "
            f"panel: the luminance they hold constant is {HELD_STANDARD}, and what this panel "
            f"shows of it is unknown (engine spec §7.3); the colors that claim it: "
            f"{'; '.join(isoluminant)}"), blocking=False, accepted_in=SESSION_KINDS))
    if panel is not None:
```

Replace:

```python
def _default_faults(trial: Trial, params: dict[str, Param]) -> list[Finding]:
    """What a recording cannot carry on the default calibration (engine spec §7.2; N§R4: "Yes,
    from the task file"): a task that names a color, or one a parameter of which sets a light
    or a contrast -- this build's reading of "a design factor or a procedure-controlled value",
    until build C lets a task declare its factors (Question 2). Each is one warning per task,
    accepted in training and piloting. Since engine build A2 the color finding also says how the
```

with:

```python
def _default_faults(trial: Trial, params: dict[str, Param]) -> list[Finding]:
    """What the default calibration makes nominal (engine spec §7.2; N§R4: "Yes, from the task
    file"): a task that names a color, or one a parameter of which sets a light or a contrast --
    this build's reading of "a design factor or a procedure-controlled value", until build C lets
    a task declare its factors (Question 2). Each is one warning per task, **accepted in every
    session kind, recording included** (COL-02, revised by the PI on 2026-10-11, XC-352's A21: "a
    warning in recording too"; refused in recording until then), saying that the session's
    `config.json` names the default. Since engine build A2 the color finding also says how the
```

Replace:

```python
        findings.append(Finding("color-on-default", (
            "a recording session refuses this task on the default calibration, the sRGB "
            "standard, measured by nobody (engine spec §7.2); there its cone colors (DKL, cone "
            "contrast) convert through the inverse of the CIE's LMS-to-XYZ_F,10 matrix, a use "
            "outside the CIE's definition, so how far each is from the cone contrast it names "
            f"is unknown, and the luminance they hold constant is {HELD_STANDARD}; the colors "
            f"it names: {'; '.join(named)}"),
            blocking=False, accepted_in=NOT_RECORDING))
```

with:

```python
        findings.append(Finding("color-on-default", (
            "on the default calibration, the sRGB standard, measured by nobody (engine spec "
            "§7.2), this task's cone colors (DKL, cone contrast) convert through the inverse of "
            "the CIE's LMS-to-XYZ_F,10 matrix, a use outside the CIE's definition, so how far "
            "each is from the cone contrast it names is unknown, and the luminance they hold "
            f"constant is {HELD_STANDARD}; every color in the data is nominal, and the "
            f"session's config.json names the default calibration; the colors it names: "
            f"{'; '.join(named)}"),
            blocking=False, accepted_in=SESSION_KINDS))
```

Replace:

```python
        findings.append(Finding("color-on-default", (
            f"this task names colors ({'; '.join(named)}), and the default calibration is the sRGB "
            f"standard, measured by nobody: a recording session refuses it until a measured "
            f"calibration is in use (engine spec §7.2)"),
            blocking=False, accepted_in=NOT_RECORDING))
```

with:

```python
        findings.append(Finding("color-on-default", (
            f"the default calibration is the sRGB standard, measured by nobody, so every color "
            f"this task names is nominal, in a recording as in training, and the session's "
            f"config.json names the default calibration (engine spec §7.2); the colors it names: "
            f"{'; '.join(named)}"),
            blocking=False, accepted_in=SESSION_KINDS))
```

Replace:

```python
            f"an opacity, which this build counts as a design factor until a task can declare its "
            f"own (engine build C): a recording session refuses them on the default calibration "
            f"(engine spec §7.2)"),
            blocking=False, accepted_in=NOT_RECORDING))
```

with:

```python
            f"an opacity, which this build counts as a design factor until a task can declare its "
            f"own (engine build C): on the default calibration every such value is nominal, in a "
            f"recording as in training, and the session's config.json names the default "
            f"calibration (engine spec §7.2)"),
            blocking=False, accepted_in=SESSION_KINDS))
```

**`wl_xcon/findings.py`**:

Replace:

```python

#: A warning acceptable everywhere but in a recording (spec §7.2: the default calibration
#: "refused in recording" for a task that names a color or makes contrast a factor).
```

with:

```python

#: A warning acceptable everywhere but in a recording. **No finding gives it since the PI's
#: rulings of 2026-10-11** (XC-352's A21: the default calibration's colors are "a warning in
#: recording too", COL-02, revised); kept as the vocabulary a warning's kinds are written in.
```

The doc it invalidates:

**`docs/pitfalls.md`**:

Replace:

```markdown
| **P19** | **A colour nobody measured reaches a methods section** | **High** | Device-independent colour only, checked against the rig's calibration; on the default sRGB calibration a warning, refused in recording; isoluminance against a named observer, which the methods section states — see expanded note |
```

with:

```markdown
| **P19** | **A colour nobody measured reaches a methods section** | **High** | Device-independent colour only, checked against the rig's calibration; on the default sRGB calibration a warning in every session kind, the record naming the default; isoluminance against a named observer, which the methods section states — see expanded note |
```

**`docs/pitfalls.md`**:

Replace:

```markdown
nobody** (engine spec §7.1; engine build B, 2026-10-08). On the default a task that names
a colour or lets a setting change a light loads in training and piloting with a warning a
person accepts and the record keeps, and is **refused in a recording session** (PI,
2026-10-07 and 2026-10-08; engine spec §7.2); isoluminance needs a measured calibration in
every session (§7.3).
```

with:

```markdown
nobody** (engine spec §7.1; engine build B, 2026-10-08). On the default a task that names
a colour or lets a setting change a light loads with a warning a person accepts and the
record keeps, **in a recording session too**, the session's `config.json` naming the
default (the PI, 2026-10-11, XC-352's A21, revising his rulings of 2026-10-07 and 2026-10-08,
which refused it in recording; engine spec §7.2); isoluminance on the default is a warning in
every session that the colours are only nominally isoluminant (XC-352's A19; §7.3).
```

- [ ] **Step 4: Run them and see them pass**

Run the five files, then the whole suite. Expected: `862 passed`; the suite **3501 passed**.

- [ ] **Step 5: Prove they can fail**

- `isoluminance-on-default`'s `blocking=False, accepted_in=SESSION_KINDS` removed: twelve fail, `test_isoluminance_on_the_default_is_a_warning_in_every_kind_that_it_is_only_nominal` and the reference search task's among them.
- The cone branch's `color-on-default` kinds → `("training", "piloting")`: `test_a_cone_color_on_the_default_runs_in_every_kind_with_the_warning`, `test_a_cone_contrast_names_a_color_on_the_default_as_an_xyy_does` and the reference search task's fail.
- The named branch's → `("training", "piloting")`: `test_a_named_color_on_the_default_is_a_warning_in_every_kind_naming_the_record` and `test_the_training_variant_runs_on_the_default_in_every_kind_with_its_warnings` fail.
- `contrast-on-default`'s → `("training", "piloting")`: nine fail, `test_a_recording_session_on_the_default_runs_once_its_warnings_are_accepted` and `test_wlx_check_passes_the_reference_task_on_the_default_in_every_kind[recording]` among them.
- `continue` restored after the isoluminant color is named: `test_on_the_default_every_reference_task_runs_in_every_kind_with_its_warnings[visual_search]` fails (its clipping hidden again).
- `if what not in isoluminant:` → `if not isoluminant:` (only the first color named): `test_one_warning_names_each_isoluminant_choice_of_an_appearance_parameter` fails.

- [ ] **Step 6: Commit**

```bash
git add wl_xcon/check.py wl_xcon/findings.py tests/ docs/pitfalls.md
git commit -m "Accept the default calibration's color warnings in recording, and isoluminance on it as a warning"
```
Body: XC-352's A21 ("a warning in recording too"; the record names the default) and A19 ("a warning everywhere"), the PI, 2026-10-11, revising COL-02 and COL-03 (Task 12 records it); call 15 and the search task's clipping; one isoluminance warning per task, naming each color (the review's M8); the count; the breaks seen failing.

---

### Task 5: A light the panel cannot make is a warning naming the light it shows; the drawer clips it (XC-352's A20)

`exact.output_levels` clips each primary weight to [0, 1] instead of refusing, and `exact.shown` gives the light the clipped levels make. `check`'s `unrealizable-color` is a warning in every kind, **one per task** (the review's M8), naming each light the panel cannot make, what asks for it, the primary weights it needs and the light the panel shows -- a light several things ask for said once -- which `warnings.jsonl` records once it is accepted. A light that does not convert at all (no cone matrix, a black background, a weight that is no number) stays a refusal, its own. The search task runs on the default, and its docstring and its gray's comment say so.

**Files:**
- Modify: `wl_xcon/exact.py` (docstring; new `_weights`, `output_levels`, new `shown`, `inverse_transfer`'s docstring), `wl_xcon/check.py` (`_color_faults`, `_modulation_faults`, `_one_color`, new `_unrealizable`, `_clips`, `_clipped`), `wl_xcon/findings.py` (`Finding.subjects`), `tasks/visual_search.py` (docstring; `BACKGROUND`'s comment)
- Modify (test): `tests/test_color.py`, `tests/test_exact.py`, `tests/test_reference_tasks.py`, `tests/test_service.py`
- Modify (docs): `docs/pitfalls.md` (P19), `docs/design/architecture.md` ("Color, since engine build A2"), `docs/backlog.md` (XC-306 edited; XC-370 filed; "Next free" XC-371)

**Interfaces:**
- Produces: `exact.shown(image, calibration) -> ndarray` (rows, cols, 3) CIE XYZ cd/m²; `exact._weights(image, calibration) -> (primaries, weights)`, raising `ValueError("N pixel(s) need a primary weight that is not a number; …")`; `findings.Finding.subjects: tuple[str, ...] = ()`, what a finding is about, no part of its equality; `check._unrealizable(said, why, light, panel, background=None, *, what) -> Finding` (a refusal saying `why`, or one part of the clip warning, about `what`); `check._clips(findings) -> list[Finding]` (the parts as one warning, where the first stood, `subjects` each `what`); `check._clipped(light, panel, background=None) -> tuple[tuple, str] | None` (the primary weights to three places, and "x=…, y=…, Y=… cd/m²" or "black, every primary off").

- [ ] **Step 1: Write the failing tests**

**`tests/test_color.py`** (18 replacements, in order):

Replace:

```python

import pytest
```

with:

```python

import numpy as np

import pytest
```

Replace:

```python
from _calibrations import LINEAR, measured
from wl_xcon import cones, look
```

with:

```python
from _calibrations import LINEAR, measured
from wl_xcon import cones, exact, look
```

Replace:

```python
    Weber,
    to_xyz,
```

with:

```python
    Weber,
    cone_xyz,
    to_xyz,
```

Replace:

```python

def test_a_colour_the_panel_cannot_produce_is_refused():
```

with:

```python

def test_a_colour_the_panel_cannot_produce_is_found():
```

Replace:

```python

def test_a_luminance_the_panel_cannot_reach_is_refused():
```

with:

```python

def test_a_luminance_the_panel_cannot_reach_is_found():
```

Replace:

```python

def test_a_cone_color_the_panel_cannot_make_on_its_background_is_refused():
    """Full conversion, not a stored maximum (engine spec §7.4; COL-08): a red-green contrast the
    old 0.85 gate passed is outside the panel's gamut."""
    trial = replace(a_task(Disc(color=DKL(l_m=-0.5))), background=GRAY_BG)

    found = _found(trial, calibration=measured())

    assert found["unrealizable-color"].detail.startswith(
```

with:

```python

def test_a_cone_color_the_panel_cannot_make_is_a_warning_naming_the_light_it_shows():
    """Full conversion, not a stored maximum (engine spec §7.4; COL-08): a red-green contrast the
    old 0.85 gate passed is outside the panel's gamut. **A warning, not a refusal** (COL-08, COL-34
    and COL-36, revised by the PI on 2026-10-11, XC-352's A20: "a warning, and the drawer records
    the light actually shown beside the one asked for"), accepted in every kind, its sentence
    naming the light asked for and the light the panel shows -- the drawer's clipped light
    (`exact.shown`) -- which `warnings.jsonl` records when it is accepted."""
    panel = measured()
    trial = replace(a_task(Disc(color=DKL(l_m=-0.5))), background=GRAY_BG)

    warning = _found(trial, calibration=panel)["unrealizable-color"]

    assert (warning.blocking, warning.accepted_in) == (False, SESSION_KINDS)
    assert warning.detail.startswith(
```

Replace:

```python
        "xyY(x=0.3127, y=0.329, Y=20.0)")
    assert "outside [0, 1]" in found["unrealizable-color"].detail
```

with:

```python
        "xyY(x=0.3127, y=0.329, Y=20.0)")
    assert "outside [0, 1]" in warning.detail
    light = cone_xyz(DKL(l_m=-0.5), panel, xyY(*D65, 20.0))
    X, Y, Z = exact.shown(np.array([[light]]), panel)[0, 0]
    weights = tuple(round(float(w), 3) for w in panel.weights_of(light))
    assert (f": primary weights {weights}, outside [0, 1], so the panel shows "
            f"x={X / (X + Y + Z):.4f}, y={Y / (X + Y + Z):.4f}, Y={Y:.4g} cd/m²") in warning.detail
    assert warning.detail.endswith(
        "a clipped light is neither the chromaticity nor the luminance asked for (engine spec §7.4)")
```

Replace:

```python

    assert "measured without spectra" in _found(trial, calibration=PANEL)["unrealizable-color"].detail
```

with:

```python

    refusal = _found(trial, calibration=PANEL)["unrealizable-color"]
    # No light to clip: the color does not convert at all, which stays a refusal (XC-352's A20).
    assert refusal.blocking and "measured without spectra" in refusal.detail
```

Replace:

```python
    trial = replace(a_task(Disc(color=DKL(l_m=0.08))), background=GRAY_BG)
    assert "is not the CIE's file" in _found(trial, calibration=panel)["unrealizable-color"].detail
```

with:

```python
    trial = replace(a_task(Disc(color=DKL(l_m=0.08))), background=GRAY_BG)
    refusal = _found(trial, calibration=panel)["unrealizable-color"]
    assert refusal.blocking and "is not the CIE's file" in refusal.detail
```

Replace:

```python

def test_an_absolute_luminance_the_panel_cannot_reach_is_refused():
```

with:

```python

def test_an_absolute_luminance_the_panel_cannot_reach_is_found():
```

Replace:

```python
    assert "unrealizable-color" in codes(a_task(looks))

```

with:

```python
    assert "unrealizable-color" in codes(a_task(looks))


def test_a_light_below_black_is_shown_as_black():
    """A luminance below 0 has every primary weight below 0: clipped, the panel shows black."""
    trial = replace(a_task(Disc(color=Gray(P("lum")))),
                    params=[Param("lum", unit="cd/m2", low=-10.0, high=50.0)])

    (warning,) = [f for f in check(trial, calibration=SRGB) if f.code == "unrealizable-color"]

    assert warning.is_warning
    assert "so the panel shows black, every primary off; the drawer clips" in warning.detail


def test_every_light_the_panel_cannot_make_is_one_warning_saying_each_light_once():
    """The warnings-over-refusals review's M8: one `unrealizable-color` warning per task, naming
    each light the panel cannot make, what asks for it and the light it shows; a light that
    several choices ask for is said once, naming each."""
    red = xyY(0.72, 0.28, 40.0)
    found = check(_choosing(Disc(size=1.0, color=red), Square(size=1.0, color=red),
                            Disc(size=1.0, color=Gray(900.0))), calibration=SRGB)

    (warning,) = [f for f in found if f.code == "unrealizable-color"]

    assert warning.is_warning and warning.detail.count("so the panel shows") == 2
    assert warning.detail.startswith(
        "Disc (choice 1 of parameter 'looks') and Square (choice 2 of parameter 'looks') ask for "
        "xyY(x=0.72, y=0.28, Y=40.0): primary weights")
    assert ("; Disc (choice 3 of parameter 'looks') asks for xyY(x=0.3127, y=0.329, Y=900.0): "
            "primary weights") in warning.detail

```

Replace:

```python

def test_a_cone_color_the_default_cannot_make_is_refused_on_it():
```

with:

```python

def test_a_cone_color_the_default_cannot_make_is_a_warning_on_it():
```

Replace:

```python

    assert _found(trial)["unrealizable-color"].blocking
```

with:

```python

    assert _found(trial)["unrealizable-color"].is_warning
```

Replace:

```python
    """Finite components near the float maximum make weights of infinity or NaN; NaN fails both
    range comparisons, so the test must fail closed."""
```

with:

```python
    """Finite components near the float maximum make weights of infinity or NaN; NaN fails both
    range comparisons, so the test must fail closed. **And it stays a refusal** (XC-352's A20):
    no light can be clipped from a weight that is no number."""
```

Replace:

```python
    assert unrealizable(color, measured(), xyY(*D65, 20.0)) is not None

```

with:

```python
    assert unrealizable(color, measured(), xyY(*D65, 20.0)) is not None
    trial = replace(a_task(Disc(color=color)), background=GRAY_BG)
    (refusal,) = [f for f in check(trial, calibration=measured()) if f.code == "unrealizable-color"]
    assert refusal.blocking and "the panel shows" not in refusal.detail

```

Replace:

```python

def test_a_weber_light_brighter_than_the_panel_makes_on_its_background_is_refused():
```

with:

```python

def test_a_weber_light_brighter_than_the_panel_makes_on_its_background_is_found():
```

Replace:

```python

def test_a_grating_whose_brightest_bar_the_panel_cannot_make_is_refused():
```

with:

```python

def test_a_grating_whose_brightest_bar_the_panel_cannot_make_is_found():
```

Replace:

```python

    assert found["unrealizable-color"].blocking
```

with:

```python

    assert found["unrealizable-color"].is_warning
```

**`tests/test_exact.py`** (4 replacements, in order):

Replace:

```python

def test_a_pixel_the_panel_cannot_make_is_refused_never_clipped():
    with pytest.raises(ValueError, match=r"^1 pixel\(s\) need a primary weight outside \[0, 1\]"):
        exact.output_levels(_pixels(Gray(40.0), Gray(SRGB_WHITE_CD_M2 + 1.0)), SRGB)
```

with:

```python

def test_a_pixel_the_panel_cannot_make_is_clipped_and_shown_as_the_light_it_makes():
    """XC-352's A20 (the PI, 2026-10-11: "a warning, and the drawer records the light actually
    shown beside the one asked for"): each primary weight is clipped to [0, 1], never refused, and
    `shown` gives the light the clipped levels make -- the panel's white for a gray brighter than
    it -- and the light asked for wherever the panel makes it."""
    image = _pixels(Gray(40.0), Gray(SRGB_WHITE_CD_M2 + 1.0))

    out = exact.output_levels(image, SRGB)
    seen = exact.shown(image, SRGB)

    assert out[0, 1] == pytest.approx((1.0, 1.0, 1.0), abs=1e-12)
    assert seen.shape == image.shape
    assert seen[0, 0] == pytest.approx(image[0, 0])
    assert seen[0, 1] == pytest.approx(to_xyz(Gray(SRGB_WHITE_CD_M2)))
    assert seen[0, 1, 1] < image[0, 1, 1]
```

Replace:

```python

def test_a_pixel_that_is_not_a_number_is_refused_too():
    """A NaN fails every comparison, so a range check written as "any weight out of range"
    would pass it; this one asks that every weight be in range."""
```

with:

```python

def test_a_pixel_that_is_not_a_number_is_refused_never_clipped():
    """A NaN fails every comparison and has nothing to be clipped to: the drawer and `shown`
    refuse it."""
```

Replace:

```python
        image[0, 1, 1] = bad
        with pytest.raises(ValueError, match=r"need a primary weight outside"):
            exact.output_levels(image, SRGB)
```

with:

```python
        image[0, 1, 1] = bad
        for drawn in (exact.output_levels, exact.shown):
            with pytest.raises(ValueError, match=r"^1 pixel\(s\) need a primary weight that is not a number"):
                drawn(image, SRGB)
```

Replace:

```python

def test_a_refusal_names_the_farthest_weight_to_more_places_than_the_tolerance():
    """`{:g}` printed a weight of 1.000002 as "1", a weight in range (the A2 final review's item
    10)."""
    panel = measured()

    with pytest.raises(ValueError, match=r"\(the farthest 1\.000002\)"):
        exact.output_levels(np.array([[(1.0 + 2 * TOLERANCE) * _full(panel)]]), panel)
```

with:

```python

def test_a_weight_past_full_drive_beyond_the_tolerance_is_clipped_to_full_drive():
    """Past `TOLERANCE` it is no rounding, and is clipped as any weight outside [0, 1] is
    (XC-352's A20): full drive, which shows the panel's full white."""
    panel = measured()
    image = np.array([[(1.0 + 2 * TOLERANCE) * _full(panel)]])

    assert exact.output_levels(image, panel)[0, 0].tolist() == [1.0, 1.0, 1.0]
    assert exact.shown(image, panel)[0, 0] == pytest.approx(_full(panel))
```

**`tests/test_reference_tasks.py`** (2 replacements, in order):

Replace:

```python
    A19 and A21): each runs on the default calibration in every session kind, recording included,
    with its warnings -- the search task's isoluminant colors among them. **But the search task's
    isoluminant red and green are just outside the sRGB standard's gamut** (a primary weight of
    -0.003 to -0.006), which its isoluminance refusal hid until then: `unrealizable-color` still
    refuses them here, until a light the panel cannot make is a warning (XC-352's A20)."""
```

with:

```python
    A19 and A21): each runs on the default calibration in every session kind, recording included,
    with its warnings -- the search task's isoluminant colors among them. **The search task's
    isoluminant red and green are just outside the sRGB standard's gamut** (a primary weight of
    -0.003 to -0.006), which its isoluminance refusal hid until then: `unrealizable-color` warns of
    them, naming the light the panel shows (XC-352's A20)."""
```

Replace:

```python
    warned = {f.code for f in found if f.is_warning}
    if name == "visual_search":
        assert refusing == {"unrealizable-color"}
        assert warned == {"isoluminance-on-default", "color-on-default", "contrast-on-default"}
    else:
        assert refusing == set() and warned == {"contrast-on-default"}
```

with:

```python
    warned = {f.code for f in found if f.is_warning}
    assert refusing == set()
    if name == "visual_search":
        assert warned == {"isoluminance-on-default", "unrealizable-color", "color-on-default",
                          "contrast-on-default"}
    else:
        assert warned == {"contrast-on-default"}
```

**`tests/test_service.py`**:

Replace:

```python
    assert [row["how"] for row in warned if row["code"] == "wrong-setup"] == ["start"]

```

with:

```python
    assert [row["how"] for row in warned if row["code"] == "wrong-setup"] == ["start"]


def test_the_search_task_runs_on_the_default_and_records_the_light_the_panel_shows(tmp_path):
    """XC-352's A19 and A20 (the PI, 2026-10-11): the search task's isoluminant red and green,
    just outside the sRGB standard's gamut, are warnings, not refusals; once accepted the run
    starts, and `warnings.jsonl` records each color asked for beside the light the panel shows."""
    service = _service(tmp_path)
    shutil.copy("tasks/visual_search.py", service.tasks)
    _step(service, _open())

    checked = _step(service, CheckRun(by=BY, task="visual_search.py", values=dict(SEARCH_VALUES)))
    started = _step(service, _start(task="visual_search.py", values=dict(SEARCH_VALUES)))

    items = {i.name: i for i in checked.preflight.items}
    assert items["task checks"].result == "pass" and items["warnings"].result == "unknown"
    assert started.run_index == 0
    rows = _jsonl(service.root / "2027-01-14_01" / "xcon" / "warnings.jsonl")
    # One warning naming each color asked for and the light the panel shows, each light once
    # (the warnings-over-refusals review's M8): the search task's red and green.
    (clipped,) = [r["detail"] for r in rows if r["code"] == "unrealizable-color"]
    assert clipped.count(" ask for DKL(") == 2 and clipped.count("so the panel shows x=") == 2
    assert len(items["warnings"].said) < 3_000, "5,392 with one per light and per isoluminant color"

```

- [ ] **Step 2: Run them and see them fail**

Run: `$PY -m pytest -q -p no:cacheprovider tests/test_color.py tests/test_exact.py tests/test_reference_tasks.py tests/test_service.py`
Expected: `11 failed, 482 passed`: the color tests on `unrealizable-color` blocking and naming no light shown, `test_every_light_the_panel_cannot_make_is_one_warning_saying_each_light_once` among them; `test_exact.py`'s three on `ValueError: 1 pixel(s) need a primary weight outside [0, 1]` or `AttributeError: … 'shown'`; the reference search task on `unrealizable-color` refusing; the service's search run refused.

- [ ] **Step 3: Implement**

**`wl_xcon/check.py`** (5 replacements, in order):

Replace:

```python
        findings += [f for f in _modulation_faults(trial, params, panel, backgrounds)
                     if f not in findings]
```

with:

```python
        findings += [f for f in _modulation_faults(trial, params, panel, backgrounds)
                     if f not in findings]
        # One clip warning per task, each light once (`_clips`; the review's M8).
        findings = _clips(findings)
```

Replace:

```python
    ones is not known here; the exact drawer refuses a pixel the panel cannot make
    (`exact.output_levels`; XC-306). A window, a scotoma and a multiplier
    draw no light of their own and are left out."""
```

with:

```python
    ones is not known here; the exact drawer clips a pixel the panel cannot make
    (`exact.output_levels`; XC-306). A window, a scotoma and a multiplier
    draw no light of their own and are left out. **Each is one part of the task's one warning,
    naming the light the panel shows** (`_unrealizable`, `_clips`; XC-352's A20)."""
```

Replace:

```python
        if why is not None:
            finding = Finding("unrealizable-color", f"{what}'s {said} reaches {light}: {why}")
```

with:

```python
        if why is not None:
            finding = _unrealizable(f"{what}'s {said} reaches {light}", why, light, panel,
                                    what=what)
```

Replace:

```python
    if isinstance(color, CONE_COLORS):
        return [Finding("unrealizable-color", f"{what} asks for {color} on a background of "
                                              f"{background}: {why}")
```

with:

```python
    if isinstance(color, CONE_COLORS):
        return [_unrealizable(f"{what} asks for {color} on a background of {background}", why,
                              color, panel, background, what=what)
```

Replace:

```python
    if why is not None:
        return [Finding("unrealizable-color", f"{what} asks for {color}: {why}")]
    return []

```

with:

```python
    if why is not None:
        return [_unrealizable(f"{what} asks for {color}", why, color, panel, what=what)]
    return []


def _unrealizable(said: str, why: str, light, panel: Calibration, background=None, *,
                  what: str) -> Finding:
    """A light the panel cannot make (engine spec §7.4; COL-08, COL-34, COL-36), `said` naming
    `what` asks for it, and `why` what `photometry.unrealizable` said of it: **a warning naming the
    primary weights it needs and the light the panel shows instead**, accepted in every session
    kind (the PI, 2026-10-11, XC-352's A20: "a warning, and the drawer records the light actually
    shown beside the one asked for"), which `warnings.jsonl` records with the light asked for once
    it is accepted: one part of the task's one `unrealizable-color` warning (`_clips`), about
    `what`. **A light that does not convert at all stays a refusal**, saying `why`: a cone color on
    a calibration with no cone matrix, or against a black background, or a weight that is no
    number, has no light to clip (`_clipped`)."""
    clipped = _clipped(light, panel, background)
    if clipped is None:
        return Finding("unrealizable-color", f"{said}: {why}")
    weights, shown = clipped
    return Finding("unrealizable-color", (
        f"{said}: primary weights {weights}, outside [0, 1], so the panel shows {shown}"),
        blocking=False, accepted_in=SESSION_KINDS, subjects=(what,))


def _clips(findings: list[Finding]) -> list[Finding]:
    """**One `unrealizable-color` warning per task**, where its first part stood, naming each light
    the panel cannot make, what asks for it and the light it shows (the warnings-over-refusals
    review's M8: a warning per light ran the search task's warnings item to thousands of
    characters). A light several things ask for is said once, naming each (`Finding.subjects`). A
    light that does not convert at all stays its own refusal."""
    parts = [f for f in findings if f.code == "unrealizable-color" and f.is_warning]
    if not parts:
        return findings
    asking: dict[str, list[str]] = {}
    for part in parts:
        (what,) = part.subjects
        asking.setdefault(part.detail[len(what):], []).append(what)
    said = []
    for rest, whats in asking.items():
        if len(whats) > 1 and rest.startswith(" asks for "):
            said.append(f"{', '.join(whats[:-1])} and {whats[-1]} ask for "
                        f"{rest[len(' asks for '):]}")
        else:
            said += [what + rest for what in whats]
    first = findings.index(parts[0])
    rest = [f for f in findings if f not in parts]
    return rest[:first] + [Finding("unrealizable-color", (
        "; ".join(said) + "; the drawer clips each primary weight to [0, 1], and a clipped light "
        "is neither the chromaticity nor the luminance asked for (engine spec §7.4)"),
        blocking=False, accepted_in=SESSION_KINDS,
        subjects=tuple(what for whats in asking.values() for what in whats))] + rest[first:]


def _clipped(light, panel: Calibration, background=None) -> "tuple[tuple, str] | None":
    """The primary weights `light` needs on `panel`, to three places, and the light the panel shows
    for it, in words: its weights clipped to [0, 1], as the drawer clips a pixel (`exact.shown`)
    -- or `None` when it names no light the panel can be asked for (a cone color that does not
    convert, a weight that is no number)."""
    import numpy as np

    from wl_xcon import exact
    from wl_xcon.photometry import cone_xyz, to_xyz

    try:
        if isinstance(light, CONE_COLORS):
            if background is None:
                return None
            xyz = cone_xyz(light, panel, background)
        elif isinstance(light, xyY):
            xyz = to_xyz(light)
        else:
            return None
        weights = tuple(round(float(w), 3) for w in panel.weights_of(xyz))
        X, Y, Z = (float(v) for v in exact.shown(np.array([[xyz]], dtype=float), panel)[0, 0])
    except (ValueError, TypeError, OverflowError):
        return None
    total = X + Y + Z
    if not total > 0.0:
        return weights, "black, every primary off"
    return weights, f"x={X / total:.4f}, y={Y / total:.4f}, Y={Y:.4g} cd/m²"

```

**`wl_xcon/findings.py`**:

Replace:

```python
from dataclasses import dataclass
```

with:

```python
from dataclasses import dataclass, field
```

Replace:

```python
    accepted_in: tuple[str, ...] = ()

    def __post_init__(self) -> None:
```

with:

```python
    accepted_in: tuple[str, ...] = ()
    #: **What it is about**, where that must be told apart from its sentence, which carries
    #: numbers: the color each part of a task's one `unrealizable-color` warning names
    #: (`check._clips`), and, for a value outside its declared range, whether a finding of
    #: `check.BREAKS_A_RUN` is about something the declared ranges already give
    #: (`check.beyond_range`). No part of its equality, nor of what a session accepts.
    subjects: tuple[str, ...] = field(default=(), compare=False)

    def __post_init__(self) -> None:
```

**`tasks/visual_search.py`** (2 replacements, in order):

Replace:

```python
which is a claim about photometry, so this task **runs only on a measured display calibration that
carries its primaries' spectra** (engine spec §7.3; engine build A2): on the default it is refused
in every kind of session. Its red and green are the PI's 2023 pop-out objects' (Westerberg et al.
```

with:

```python
which is a claim about photometry, so this task **is meant for a measured display calibration that
carries its primaries' spectra** (engine spec §7.3; engine build A2). On the default it runs with
warnings that its colors are only nominally isoluminant and that the panel clips its red and green
(the PI's rulings of 2026-10-11, XC-352's A19 and A20; refused in every kind of session until
then). Its red and green are the PI's 2023 pop-out objects' (Westerberg et al.
```

Replace:

```python
#: drive on a 17.7 cd/m² gray, so 16 leaves 9.4% (computed 2026-10-10); re-set when the panels
#: are measured (XC-310). The fixation point's starting 40 cd/m² stays
```

with:

```python
#: drive on a 17.7 cd/m² gray, so 16 leaves 9.4% (computed 2026-10-10); re-set when the panels
#: are measured (XC-310). **Both are just outside the sRGB standard's gamut all the same**: a
#: primary goes negative in each -- RED's blue (-0.006), GREEN's red and blue (-0.0034, -0.0054;
#: computed 2026-10-10) -- so the default's panel clips them, which `check` warns of (XC-352's
#: A20). The fixation point's starting 40 cd/m² stays
```

**`wl_xcon/exact.py`** (5 replacements, in order):

Replace:

```python
   build A2): the primary weights that make it, then each channel's measured transfer read
   backwards. A pixel the panel cannot make is refused, never clipped.
```

with:

```python
   build A2): the primary weights that make it, then each channel's measured transfer read
   backwards. A pixel the panel cannot make is clipped, each weight to [0, 1], and `shown` gives
   the light the clipped levels make (the PI, 2026-10-11, XC-352's A20: "a warning, and the
   drawer records the light actually shown beside the one asked for").
```

Replace:

```python

def output_levels(image, calibration):
```

with:

```python

def _weights(image, calibration):
    """The panel's primaries, as the columns of a 3×3 of CIE XYZ, and each pixel's primary weights
    (as `Calibration.weights` solves them), one row per pixel. **A weight that is no number
    raises**: there is nothing to clip it to."""
    primaries = np.array([to_xyz(p) for p in (calibration.red, calibration.green,
                                              calibration.blue)]).T
    weights = np.linalg.solve(primaries, np.asarray(image, dtype=float).reshape(-1, 3).T).T
    if not np.isfinite(weights).all():
        pixels = int((~np.isfinite(weights)).any(axis=1).sum())
        raise ValueError(
            f"{pixels} pixel(s) need a primary weight that is not a number; there is nothing to "
            f"clip it to"
        )
    return primaries, weights


def output_levels(image, calibration):
```

Replace:

```python
    channel's measured transfer read backwards** (spec §7.6, `inverse_transfer`). **A pixel the
    panel cannot make raises**, naming how many and the farthest weight, rather than being
    clipped (spec §7.4); `check` refuses at load every such light it can see
    (`unrealizable-color`). **Continuous, never quantized** (the engine A2 plan's call 19):
    rounding to the output's codes, and dithering if it is the fallback (spec §7.8), are the
    display process's (engine build E), held to this within one output level (spec §10.1)."""
    primaries = np.array([to_xyz(p) for p in (calibration.red, calibration.green,
                                              calibration.blue)]).T
    weights = np.linalg.solve(primaries, np.asarray(image, dtype=float).reshape(-1, 3).T).T
    # Asked as "every weight is in range", so a NaN, which fails every comparison, is refused.
    inside = (weights >= -TOLERANCE) & (weights <= 1.0 + TOLERANCE)
    if not inside.all():
        pixels = int((~inside).any(axis=1).sum())
        bad = weights[~inside]
        worst = bad[np.argmax(np.abs(bad - 0.5))]
        raise ValueError(
            f"{pixels} pixel(s) need a primary weight outside [0, 1] (the farthest {worst:.7g}); "
            f"`check` refuses a light it can see that does this, and this one it could not"
        )
```

with:

```python
    channel's measured transfer read backwards** (spec §7.6, `inverse_transfer`). **A pixel the
    panel cannot make is clipped**, each weight to [0, 1] (the PI, 2026-10-11, XC-352's A20: "a
    warning, and the drawer records the light actually shown beside the one asked for"): its
    light is then neither the chromaticity nor the luminance asked for, which `check` warns of at
    load for every such light it can see (`unrealizable-color`), naming the light `shown` gives.
    A weight that is no number raises (`_weights`). **Continuous, never quantized** (the engine
    A2 plan's call 19): rounding to the output's codes, and dithering if it is the fallback (spec
    §7.8), are the display process's (engine build E), held to this within one output level
    (spec §10.1)."""
    _, weights = _weights(image, calibration)
```

Replace:

```python

def inverse_transfer(transfer, weights):
```

with:

```python

def shown(image, calibration):
    """The light each pixel of a drawn eye is shown as on `calibration`'s panel, `(rows, cols, 3)`
    CIE XYZ in cd/m²: the light `output_levels`' clipped weights make -- the pixel itself wherever
    the panel can make it, within `TOLERANCE` -- for a record to carry beside the light asked for
    (XC-352's A20). Recording it per frame is the display process's and the screen log's
    (engine builds E and F); `check`'s warning names it for each light it can see."""
    primaries, weights = _weights(image, calibration)
    return (np.clip(weights, 0.0, 1.0) @ primaries.T).reshape(np.shape(image))


def inverse_transfer(transfer, weights):
```

Replace:

```python
    is flat, the lowest level that gives that light**. Every weight lies in [0, 1], the table's
    own span (its fractions are black-subtracted, ADR-0011); `output_levels` refuses any other
```

with:

```python
    is flat, the lowest level that gives that light**. Every weight lies in [0, 1], the table's
    own span (its fractions are black-subtracted, ADR-0011); `output_levels` clips any other
```

The docs it changes:

**`docs/pitfalls.md`**:

Replace:

```markdown
background is refused. A measured calibration is taken with a **spectroradiometer** (engine spec §12 item 1),
written as one JSON record (ADR-0011).
```

with:

```markdown
background is refused. **A light the panel cannot make is a warning naming the light it shows**
(the PI, 2026-10-11, XC-352's A20): the clipping this pitfall is about is no longer silent, and
the exact drawer clips it (`exact.output_levels`) and gives the light shown (`exact.shown`);
recording that light per frame waits on the display process and the screen log (engine builds E
and F). A measured calibration is taken with a **spectroradiometer** (engine spec §12 item 1),
written as one JSON record (ADR-0011).
```

**`docs/design/architecture.md`**:

Replace:

```markdown
turns each pixel into output levels through the calibration's measured, black-subtracted transfer
(`exact.output_levels`), refusing one the panel cannot make.
```

with:

```markdown
turns each pixel into output levels through the calibration's measured, black-subtracted transfer
(`exact.output_levels`), clipping one the panel cannot make, whose light `exact.shown` gives and
`check`'s `unrealizable-color` warning names (the PI, 2026-10-11, XC-352's A20).
```

**`docs/backlog.md`** -- first replace the base's `**Next free ID: XC-NNN.**` line, whatever it reads (XC-354 at `2d8717b`; XC-359 on `main` on 2026-10-13, after the deployment fix, XC-355, merged), with `**Next free ID: XC-371.**`; then (2 replacements, in order):

Replace:

```markdown
- **XC-319** Bring MonkeyLogic sessions on the swapped rig (ADR-0005) into an animal's training history with what they record, marked as having no reasons. — 2026-10-10, [XC-288 spec §10](superpowers/specs/2026-10-10-xc288-training-records-design.md#10-not-decided-here-and-why) — waits on: XC-288's file (build C)
- **XC-340** Record wl-xcon's own version (its commit, and whether its tree was clean) in each session's config.json among the facts recorded at its open: a task's content hash names what the task declares and, through declarations.FORMAT, the defaults it was read with, but not the engine that ran it. — 2026-10-11, [engine C1 plan, call 11](superpowers/plans/2026-10-11-engine-c1.md#calls-taken-in-this-plan) — waits on: engine build C4 (the facts recorded at a session's open)
```

with:

```markdown
- **XC-319** Bring MonkeyLogic sessions on the swapped rig (ADR-0005) into an animal's training history with what they record, marked as having no reasons. — 2026-10-10, [XC-288 spec §10](superpowers/specs/2026-10-10-xc288-training-records-design.md#10-not-decided-here-and-why) — waits on: XC-288's file (build C)
- **XC-370** Record the light the panel actually shows beside the light asked for wherever a drawn light is clipped, per frame or per trial, from the display process's clipped output (exact.shown defines it): the PI, 2026-10-11, XC-352's A20, "the drawer records the light actually shown beside the one asked for"; until then only check's unrealizable-color warning names it, recorded in warnings.jsonl, for each light it can see at load. — 2026-10-11, [warnings-over-refusals plan, call 5](superpowers/plans/2026-10-11-warnings-over-refusals.md#calls-taken-in-this-plan) — waits on: engine builds E and F (the display process and the screen log)
- **XC-340** Record wl-xcon's own version (its commit, and whether its tree was clean) in each session's config.json among the facts recorded at its open: a task's content hash names what the task declares and, through declarations.FORMAT, the defaults it was read with, but not the engine that ran it. — 2026-10-11, [engine C1 plan, call 11](superpowers/plans/2026-10-11-engine-c1.md#calls-taken-in-this-plan) — waits on: engine build C4 (the facts recorded at a session's open)
```

Replace:

```markdown
- **XC-300** A fault whose own `str()` raises is still formatted unguarded at sites XC-291 did not list, none of which stops `wlx taskd`: `taskd.Session.run`'s fault handler (~:2452), after which the run's `runs.jsonl` end row records no reason and a null `stop_kind` and no frame says fault (a probe, 2026-10-10); `taskd.Session._command`'s `set` refusal (~:1734 and :1737), where a `Bounds` subclass whose `validate` refuses with such a fault ends the run as a fault instead of recording a refusal, left unchanged because it sits beside `_command`'s welfare-critical `except` line; `await_return`'s handler (~:2567), reached only from `wlx run` (`cli.py` ~:600), which then says the post-loop phase failed with a `RuntimeError` and publishes no fault frame; and `preflight.task`, `values` and `files` and `cli._load_named`, whose item or refusal quotes the formatting's own `RuntimeError` in place of the fault; say each by `service._said`'s rule. — 2026-10-10, found closing XC-291's other sites, which arose in [CHECKPOINT, engine build B](CHECKPOINT.md#what-moved-on-2026-10-08-engine-build-b-what-a-session-is-for-and-the-warnings-list) — waits on: nothing
- **XC-306** A light drawn over another stimulus is not held to the panel's reach at load (a grating with no declared mean covering a lit stimulus, an added stimulus over another): check holds each to the background only, exact.output_levels refuses the pixel when drawn, and the display process must refuse or flag it rather than clip it. — 2026-10-09, [engine A2 plan, call 18](superpowers/plans/2026-10-09-engine-a2.md#calls-taken-in-this-plan) — waits on: engine build E
```

with:

```markdown
- **XC-300** A fault whose own `str()` raises is still formatted unguarded at sites XC-291 did not list, none of which stops `wlx taskd`: `taskd.Session.run`'s fault handler (~:2452), after which the run's `runs.jsonl` end row records no reason and a null `stop_kind` and no frame says fault (a probe, 2026-10-10); `taskd.Session._command`'s `set` refusal (~:1734 and :1737), where a `Bounds` subclass whose `validate` refuses with such a fault ends the run as a fault instead of recording a refusal, left unchanged because it sits beside `_command`'s welfare-critical `except` line; `await_return`'s handler (~:2567), reached only from `wlx run` (`cli.py` ~:600), which then says the post-loop phase failed with a `RuntimeError` and publishes no fault frame; and `preflight.task`, `values` and `files` and `cli._load_named`, whose item or refusal quotes the formatting's own `RuntimeError` in place of the fault; say each by `service._said`'s rule. — 2026-10-10, found closing XC-291's other sites, which arose in [CHECKPOINT, engine build B](CHECKPOINT.md#what-moved-on-2026-10-08-engine-build-b-what-a-session-is-for-and-the-warnings-list) — waits on: nothing
- **XC-306** A light drawn over another stimulus is not held to the panel's reach at load (a grating with no declared mean covering a lit stimulus, an added stimulus over another): check holds each to the background only, exact.output_levels clips the pixel when drawn and exact.shown gives the light it shows (the PI, 2026-10-11, XC-352's A20: a warning, never a refusal), and the display process must clip it the same way and record the light shown (XC-370). — 2026-10-09, [engine A2 plan, call 18](superpowers/plans/2026-10-09-engine-a2.md#calls-taken-in-this-plan) — waits on: engine build E
```

- [ ] **Step 4: Run them and see them pass**

Run the four files, then the whole suite. Expected: `493 passed`; the suite **3504 passed**.

- [ ] **Step 5: Prove they can fail**

- `_unrealizable`'s `clipped = _clipped(light, panel, background)` → `clipped = None`: eight fail, `test_a_cone_color_the_panel_cannot_make_is_a_warning_naming_the_light_it_shows` and the service's search run among them.
- `_clipped`'s `return weights, "black, every primary off"` → `return None`: `test_a_light_below_black_is_shown_as_black` fails.
- `output_levels`' `np.clip(weights[:, channel], 0.0, 1.0)` → `weights[:, channel]`: three of `test_exact.py`'s fail.
- `shown`'s `np.clip(weights, 0.0, 1.0)` → `weights`: `test_a_pixel_the_panel_cannot_make_is_clipped_and_shown_as_the_light_it_makes` and `test_a_weight_past_full_drive_beyond_the_tolerance_is_clipped_to_full_drive` fail.
- `_weights`' `if not np.isfinite(weights).all():` → `if False:`: `test_a_pixel_that_is_not_a_number_is_refused_never_clipped` and the three cases of `test_a_color_whose_weights_overflow_is_unrealizable_not_realizable` fail.
- `_clips`' `if len(whats) > 1 and rest.startswith(" asks for "):` → `if False:` (each light said once per thing asking): `test_every_light_the_panel_cannot_make_is_one_warning_saying_each_light_once` and the service's search run fail.
- `_color_faults`' `findings = _clips(findings)` → `pass`, or `_clips`' `if not parts:` → `if True:` (a warning per light again): four fail, `test_every_light_the_panel_cannot_make_is_one_warning_saying_each_light_once` and the service's search run among them.

- [ ] **Step 6: Commit**

```bash
git add wl_xcon/exact.py wl_xcon/check.py wl_xcon/findings.py tasks/visual_search.py tests/ docs/pitfalls.md docs/design/architecture.md docs/backlog.md
git commit -m "Warn of a light the panel cannot make, naming the light it shows, and clip it in the drawer"
```
Body: XC-352's A20 (the PI, 2026-10-11: "a warning, and the drawer records the light actually shown beside the one asked for"); call 5 (what is built now; XC-370 filed for the rest, XC-306 edited); one clip warning per task, each light said once (`Finding.subjects`, `check._clips`; the review's M8); the search task's docstring and its gray's comment; the count; the breaks seen failing.

---
### Task 6: A calibration that will not load, one dated after today, and one measured without spectra are warnings (XC-352's E1, E2, E3)

**E1**: `wlx taskd`, `wlx run` and `wlx check` put the default, the sRGB standard, in the place of a record the rig names that will not load, with a warning in every kind quoting why (its middle cut, so it stays within `link.NOTE_LIMIT`, which the open's form sends back), the default's own warning then saying the record would not load, not that the rig names none (the review's M4). `wlx taskd` prints the whole sentence as it starts. **E2**: a record dated after today is a warning in every kind to check the host's clock. Both were accepted in no kind, so every run failed on them; now an open asks to accept them like the default's own warning (`Service._open`'s code is unchanged; its docstring and one comment are reworded: Appendix A, item 3). **E3**: a measured calibration without spectra converts cone colors as the default does, with a task warning, `cone-colors-without-spectra`.

**Files:**
- Modify: `wl_xcon/warnlist.py` (docstring; imports; `of_calibration`, `of_unloaded`), `wl_xcon/service.py` (imports; `Service.__init__`, `calibration_warnings`, `_open`'s docstring and one comment, `run`'s start-up line), `wl_xcon/cli.py` (`_load_calibration`'s docstring, new `_calibration_or_default`, `wlx run`, `wlx check`), `wl_xcon/photometry.py` (`Calibration._convert`, `VIA_WITHOUT_SPECTRA`, `HELD_WITHOUT_SPECTRA`, `cone_record`), `wl_xcon/check.py` (a comment in `_color_faults`, new `_spectra_faults`), `wl_xcon/preflight.py`, `wl_xcon/link.py`, `wl_xcon/taskd.py` (docstrings and comments on a missing calibration)
- Modify (test): `tests/test_warnlist.py`, `tests/test_service.py`, `tests/test_cli.py`, `tests/test_cone_colors.py`, `tests/test_display_calibration.py`, `tests/test_color.py`, `tests/test_reference_tasks.py`, `tests/test_taskd.py`
- Modify (docs): `docs/design/architecture.md` (the warnings-list paragraph; "Color, since engine build A2")

**Interfaces:**
- Produces: `warnlist.of_calibration(calibration, today, unloaded=False)`, a future date now `accepted_in=SESSION_KINDS`, and with `unloaded` the default's sentence saying the record would not load (the review's M4); `warnlist.of_unloaded(refusal)` → `[Entry("calibration record", <refusal, middle cut> + "; this session runs on the default calibration, …", SESSION_KINDS)]`; `cli._calibration_or_default(rig, rig_path) -> tuple[Calibration, str]`; `Service.calibration` is `photometry.SRGB` in an unloadable record's place, `calibration_refused` saying why; `photometry.VIA_WITHOUT_SPECTRA`, `HELD_WITHOUT_SPECTRA`; the finding `cone-colors-without-spectra` (warning, every kind).

- [ ] **Step 1: Write the failing tests**

**`tests/test_cli.py`** (8 replacements, in order):

Replace:

```python

def test_wlx_check_refuses_a_calibration_record_that_will_not_load(tmp_path):
    """Review Focus 3, `wlx check`'s side (Call 20): no animal waits on it."""
```

with:

```python

def test_wlx_check_checks_on_the_default_when_the_record_will_not_load_saying_why(tmp_path, capsys):
    """XC-352's E1 (the PI, 2026-10-11): the default stands in for a record that will not load,
    with a warning saying why, and the task is checked against it."""
```

Replace:

```python

    with pytest.raises(SystemExit) as refused:
        main(["check", GOOD, "--rig", str(rig), "--allocation", ALLOCATION])

    assert str(refused.value).startswith("refused: the calibration")
    assert "not JSON" in str(refused.value)
```

with:

```python

    assert main(["check", GOOD, "--rig", str(rig), "--allocation", ALLOCATION, "--view", "direct"]) == 0

    out = capsys.readouterr().out
    assert "calibration: srgb-standard (the sRGB standard, measured by nobody)" in out
    assert "warning  calibration record" in out and "not JSON" in out
```

Replace:

```python
@pytest.mark.parametrize("kind", SESSION_KINDS)
def test_wlx_check_for_a_kind_refuses_a_calibration_dated_after_today(kind, tmp_path, capsys):
    """In every kind, as `wlx run` refuses it (call 20)."""
    assert main(["check", GOOD, "--rig", _dated_after_today(tmp_path), "--allocation", ALLOCATION,
                 "--view", "direct", "--kind", kind]) == 1
```

with:

```python
@pytest.mark.parametrize("kind", SESSION_KINDS)
def test_wlx_check_for_a_kind_warns_of_a_calibration_dated_after_today(kind, tmp_path, capsys):
    """XC-352's E2 (the PI, 2026-10-11): a warning in every kind, as `wlx run` lists it."""
    assert main(["check", GOOD, "--rig", _dated_after_today(tmp_path), "--allocation", ALLOCATION,
                 "--view", "direct", "--kind", kind]) == 0
```

Replace:

```python
    out = capsys.readouterr().out
    assert "refused  calibration age" in out and "(accepted in no session kind)" in out
    assert f"task refused in a {kind} session" in out
```

with:

```python
    out = capsys.readouterr().out
    assert "warning  calibration age" in out and "check this host's clock" in out
```

Replace:

```python

def test_wlx_run_refuses_a_calibration_record_that_will_not_load_before_anything_is_recorded(tmp_path):
    """Review Focus 3, `wlx run`'s side (Call 20): no animal is waiting on it, so it refuses
    outright, before the session opens and before the departure is asked about."""
```

with:

```python

def test_wlx_run_runs_on_the_default_when_the_record_will_not_load_once_that_is_accepted(tmp_path):
    """XC-352's E1 (the PI, 2026-10-11): the default stands in, with a warning saying why, which
    the flag accepts; the session's config.json names the default."""
```

Replace:

```python
    argv[argv.index(RIG_FILE)] = str(naming(tmp_path / "rig", str(tmp_path / "cal.json")))

    with pytest.raises(SystemExit) as refused:
        main(argv)

    assert str(refused.value).startswith("refused: the calibration")
    assert "not JSON" in str(refused.value)
    assert not (tmp_path / "2027-01-14_01").exists()
```

with:

```python
    argv[argv.index(RIG_FILE)] = str(naming(tmp_path / "rig", str(tmp_path / "cal.json")))

    assert _main_uninterrupted(argv) == 0

    folder = tmp_path / "2027-01-14_01" / "xcon"
    assert json.loads((folder / "config.json").read_text())["calibration"]["id"] == "srgb-standard"
    codes = [json.loads(line)["code"] for line in (folder / "warnings.jsonl").read_text().splitlines()]
    assert codes[:2] == ["calibration record", "default calibration"]
```

Replace:

```python

def test_wlx_run_refuses_a_calibration_dated_after_today_before_anything_is_recorded(tmp_path):
    """Call 20: the one session-level warning no kind accepts, refused with or without the
    flag, before anything is recorded."""
```

with:

```python

def test_wlx_run_runs_on_a_calibration_dated_after_today_once_its_warning_is_accepted(tmp_path):
    """XC-352's E2 (the PI, 2026-10-11): a warning, listed and accepted by the flag; without the
    flag nothing is recorded."""
```

Replace:

```python
    argv[argv.index(RIG_FILE)] = _dated_after_today(tmp_path)

    with pytest.raises(SystemExit) as refused:
        main(argv)

    assert "a training session does not accept calibration age" in str(refused.value)
    assert not (tmp_path / "2027-01-14_01").exists()
```

with:

```python
    argv[argv.index(RIG_FILE)] = _dated_after_today(tmp_path)
    unflagged = [a for a in argv if a != "--accept-warnings"]

    with pytest.raises(SystemExit) as refused:
        main(unflagged)
    assert "calibration age" in str(refused.value) and "--accept-warnings" in str(refused.value)
    assert not (tmp_path / "2027-01-14_01").exists()

    assert _main_uninterrupted(argv) == 0
    rows = (tmp_path / "2027-01-14_01" / "xcon" / "warnings.jsonl").read_text()
    assert '"code": "calibration age"' in rows
```

**`tests/test_color.py`** (2 replacements, in order):

Replace:

```python

def test_a_cone_color_on_a_measured_calibration_without_spectra_is_refused():
```

with:

```python

def test_a_cone_color_on_a_measured_calibration_without_spectra_is_a_warning_naming_the_conversion():
    """XC-352's E3 (the PI, 2026-10-11): it converts as the default's do (COL-18), with a warning
    in every kind saying so, and is held to the panel's reach like any other; until then it was
    refused, and a panel measured without spectra ran fewer tasks than the unmeasured default."""
```

Replace:

```python

    refusal = _found(trial, calibration=PANEL)["unrealizable-color"]
    # No light to clip: the color does not convert at all, which stays a refusal (XC-352's A20).
    assert refusal.blocking and "measured without spectra" in refusal.detail
```

with:

```python

    found = _found(trial, calibration=PANEL)

    assert set(found) == {"cone-colors-without-spectra"}
    warning = found["cone-colors-without-spectra"]
    assert (warning.blocking, warning.accepted_in) == (False, SESSION_KINDS)
    assert "a use outside the CIE's definition" in warning.detail and "Disc" in warning.detail
    assert "cone-colors-without-spectra" not in _found(
        a_task(Disc(color=xyY(0.3, 0.35, 20.0))), calibration=PANEL)
```

**`tests/test_cone_colors.py`** (5 replacements, in order):

Replace:

```python
    HELD_STANDARD,
    SRGB,
```

with:

```python
    HELD_STANDARD,
    HELD_WITHOUT_SPECTRA,
    SRGB,
```

Replace:

```python
    VIA_STANDARD,
    ConeContrast,
```

with:

```python
    VIA_STANDARD,
    VIA_WITHOUT_SPECTRA,
    ConeContrast,
```

Replace:

```python

def test_a_measured_calibration_without_spectra_converts_no_cone_color():
```

with:

```python

def test_a_measured_calibration_without_spectra_converts_cone_colors_as_the_default_does():
    """XC-352's E3 (the PI, 2026-10-11): through the inverse of the CIE's LMS-to-XYZ_F,10 matrix,
    applied to its measured CIE 1931 XYZ (COL-18's conversion), with a warning (`check`'s
    `cone-colors-without-spectra`); until then it converted none."""
```

Replace:

```python

    assert panel.cones is None
    with pytest.raises(ValueError, match="measured without spectra"):
        cone_xyz(DKL(l_m=0.08), panel, xyY(0.3127, 0.329, 20.0))
```

with:

```python

    assert panel.cones == SRGB.cones and panel.cones_refused == ""
    assert cone_xyz(DKL(l_m=0.08), panel, xyY(0.3127, 0.329, 20.0))
```

Replace:

```python
    assert (cone_record(measured(spectra=None))["via"],
            cone_record(measured(spectra=None))["luminance"]) == (None, None)
```

with:

```python
    assert (cone_record(measured(spectra=None))["via"],
            cone_record(measured(spectra=None))["luminance"]) == (VIA_WITHOUT_SPECTRA,
                                                                  HELD_WITHOUT_SPECTRA)
    assert "outside the CIE's definition" in VIA_WITHOUT_SPECTRA
    assert "measured CIE 1931 Y" in HELD_WITHOUT_SPECTRA
```

**`tests/test_display_calibration.py`**:

Replace:

```python
    assert "no background was given" in unrealizable(DKL(l_m=0.08), SRGB)
    assert "measured without spectra" in unrealizable(DKL(l_m=0.08), measured(spectra=None), gray)
```

with:

```python
    assert "no background was given" in unrealizable(DKL(l_m=0.08), SRGB)
    # Without spectra, as the default does (XC-352's E3).
    assert unrealizable(DKL(l_m=0.08), measured(spectra=None), gray) is None
```

**`tests/test_reference_tasks.py`** (2 replacements, in order):

Replace:

```python

def test_the_search_task_is_refused_on_a_measured_display_without_spectra(search):
    """A cone color converts through a measured calibration's spectra and has none to use
    (call 8)."""
```

with:

```python

def test_the_search_task_runs_on_a_measured_display_without_spectra_with_a_warning(search):
    """XC-352's E3 (the PI, 2026-10-11): its cone colors convert as the default's do, with a
    warning in every kind; until then it was refused (call 8)."""
```

Replace:

```python

    found = [f for f in check(search, allocation, geometry=GEOMETRY,
                              calibration=replace(PANEL, spectra=None))
             if f.code == "unrealizable-color"]

    assert found and all(f.blocking for f in found)
    assert all("measured without spectra" in f.detail for f in found)
```

with:

```python

    found = check(search, allocation, geometry=GEOMETRY, calibration=replace(PANEL, spectra=None))

    assert [f for f in found if f.blocking] == []
    assert "cone-colors-without-spectra" in {f.code for f in found if f.is_warning}
```

**`tests/test_service.py`** (18 replacements, in order):

Replace:

```python
    service = _service(tmp_path)
    service.calibration, service.calibration_refused = None, "refused: " + "x" * 2_000

    unloaded, head = _step(service).warnings

    assert (unloaded.code, unloaded.accepted_in) == ("calibration record", ())
    assert unloaded.detail == ("refused: " + "x" * 2_000)[:NOTE_LIMIT] + "…"
```

with:

```python
    service = _service(tmp_path)
    service.calibration_refused = "refused: " + "x" * 2_000

    unloaded, default, head = _step(service).warnings

    # XC-352's E1: a warning every kind accepts, quoting its refusal cut, so it reaches the frame
    # whole (`warnlist.of_unloaded`).
    assert (unloaded.code, unloaded.accepted_in) == ("calibration record", SESSION_KINDS)
    assert len(unloaded.detail) <= NOTE_LIMIT and not unloaded.detail.endswith("…")
    assert default.code == "default calibration"
```

Replace:

```python
    worst = measured(measured_on=oldest, id="x" * ID_LIMIT)

    for name, calibration in (("default", None), ("measured", worst)):
        service = _service(tmp_path / name)
        if calibration is not None:
            service.calibration = calibration
```

with:

```python
    worst = measured(measured_on=oldest, id="x" * ID_LIMIT)
    # Since XC-352's E1 and E2, a record that will not load (quoting any refusal) and one dated
    # after today are offered at an open too.
    future = measured(measured_on="9999-12-31", id="y" * ID_LIMIT)
    expected = {
        "default": ["default calibration", "head free"],
        "measured": ["calibration age", "head free"],
        "future": ["calibration age", "head free"],
        "unloaded": ["calibration record", "default calibration", "head free"],
    }

    for name in expected:
        service = _service(tmp_path / name)
        if name == "measured":
            service.calibration = worst
        if name == "future":
            service.calibration = future
        if name == "unloaded":
            service.calibration_refused = "refused: " + "z" * 2_000
```

Replace:

```python
        listed = [e for e in service.open_warnings(Deployment.RIG_CHAIRED) if e.accepted_in]
        assert [(w.code, w.detail) for w in offered] == [e.key for e in listed]
        assert all(len(w.detail) <= NOTE_LIMIT for w in offered), name
        assert [w.code for w in offered] == [
            "default calibration" if calibration is None else "calibration age", "head free",
        ]
    assert "9999 days ago" in offered[0].detail
```

with:

```python
        listed = [e for e in service.open_warnings(Deployment.RIG_CHAIRED) if e.accepted_in]
        assert [(w.code, w.detail) for w in offered] == [e.key for e in listed], name
        assert all(len(w.detail) <= NOTE_LIMIT for w in offered), name
        assert [w.code for w in offered] == expected[name], name
```

Replace:

```python
    the second and not; one measured 2027-02-20 is today's in the first and dated after
    today in the second, which no session kind accepts."""
```

with:

```python
    the second and not; one measured 2027-02-20 is today's in the first and dated after
    today in the second, a warning in every kind since XC-352's E2."""
```

Replace:

```python
    (future,) = service.calibration_warnings()
    assert future.accepted_in == () and "after today (2027-02-19)" in future.detail
```

with:

```python
    (future,) = service.calibration_warnings()
    assert future.accepted_in == SESSION_KINDS and "after today (2027-02-19)" in future.detail
```

Replace:

```python

def test_a_calibration_record_that_will_not_load_never_stops_wlx_taskd_or_an_open(tmp_path):
    """The review's C1 (Review Focus 3): `wlx taskd` starts, a session opens with no
    calibration, its departure and its return are taken, and no run starts. Task 12's
    pre-flight then fails the run first, naming the record
    (`test_a_calibration_problem_fails_every_runs_preflight_naming_it`)."""
```

with:

```python

def test_a_calibration_record_that_will_not_load_runs_sessions_on_the_default_with_a_warning(
    tmp_path,
):
    """XC-352's E1 (the PI, 2026-10-11): `wlx taskd` starts on the sRGB default in the record's
    place. An open asks to accept that, beside the default's own warning, and is refused, nothing
    recorded, until both are accepted; then it opens, a run starts, and the session's config.json
    names the default. Until then no kind accepted it and every run failed on it."""
```

Replace:

```python
    service = _made(folders, rig=dataclasses.replace(RIG, calibration=str(tmp_path / "cal.json")))

    assert service.calibration is None
```

with:

```python
    service = _made(folders, rig=dataclasses.replace(RIG, calibration=str(tmp_path / "cal.json")))

    assert service.calibration is SRGB
```

Replace:

```python
    assert "not JSON" in service.calibration_refused
    opened = _step(service, _open())
    assert opened.phase == "between_runs" and service.session.spec.calibration is None
    config = json.loads((service.root / "2027-01-14_01" / "xcon" / "config.json").read_text())
    assert config["calibration"] is None
    refused = _step(service, _start())
    assert refused.run_index is None and _runs(service.root) == []
    assert refused.refusals[-1].name == "start" and service.session.card.codes == [4128]
    ended = _step(service, _end())
    assert isinstance(ended, Idle) and _kinds(service.root)[-2:] == ["returned", "session ended"]
```

with:

```python
    assert "not JSON" in service.calibration_refused
    record, default = service.open_warnings(Deployment.RIG_FIXED)
    assert (record.code, record.accepted_in, default.code) == (
        "calibration record", SESSION_KINDS, "default calibration")
    # The default's own sentence says why it stands in, not that the rig names none (M4).
    assert default.detail.startswith("the calibration record the rig names would not load, so ")

    unaccepted = _step(service, _open())
    assert service.session is None and "calibration record: refused: the calibration" in _refused(
        unaccepted)[-1]
    assert not (service.root / "2027-01-14_01").exists()
    _step(service, _open(accepted=(record.key, default.key)))
    started = _step(service, _start())

    assert started.run_index == 0
    folder = service.root / "2027-01-14_01" / "xcon"
    assert json.loads((folder / "config.json").read_text())["calibration"]["id"] == "srgb-standard"
    assert [r["code"] for r in _jsonl(folder / "warnings.jsonl") if r["how"] == "open"] == [
        "calibration record", "default calibration"]
```

Replace:

```python
    service = promptly(lambda: _made(folders, rig=dataclasses.replace(RIG, calibration=str(pipe))), pipe)

    assert service.calibration is None
```

with:

```python
    service = promptly(lambda: _made(folders, rig=dataclasses.replace(RIG, calibration=str(pipe))), pipe)

    assert service.calibration is SRGB
```

Replace:

```python
    )
    assert _step(service, _open()).phase == "between_runs"
```

with:

```python
    )
    accepted = tuple(e.key for e in service.open_warnings(Deployment.RIG_FIXED))
    assert _step(service, _open(accepted=accepted)).phase == "between_runs"
```

Replace:

```python
        assert isinstance(frame, Idle) and second.stranded == []
        assert (second.calibration is None) == (rig is bad)
```

with:

```python
        assert isinstance(frame, Idle) and second.stranded == []
        assert bool(second.calibration_refused) == (rig is bad)
```

Replace:

```python

def test_a_calibration_problem_never_refuses_an_open(tmp_path):
    """The review's C1: a record dated after today, or one that will not load, is a warning no
    kind accepts, so it is not offered at the open and never refuses it; every run's
    pre-flight fails on it instead (Task 12)."""
```

with:

```python

def test_a_calibration_problem_is_a_warning_the_open_asks_to_accept(tmp_path):
    """XC-352's E1 and E2 (the PI, 2026-10-11): a record dated after today, or one that will not
    load, is a warning every kind accepts, offered at the open like the default's; an open that
    does not accept it is refused before anything is marked, and one that does records it."""
```

Replace:

```python

    for name, record in (("future", future), ("broken", tmp_path / "broken.json")):
        folders = _folders(tmp_path / name)
        service = _made(folders, rig=dataclasses.replace(RIG, calibration=str(record)))

        frame = _step(service, _open(accepted=()))

        assert frame.phase == "between_runs", name
        assert _kinds(folders[2]) == ["departure", "session opened"], name
        assert not (folders[2] / "2027-01-14_01" / "xcon" / "warnings.jsonl").exists(), name
```

with:

```python

    for name, record, code in (("future", future, "calibration age"),
                               ("broken", tmp_path / "broken.json", "calibration record")):
        folders = _folders(tmp_path / name)
        service = _made(folders, rig=dataclasses.replace(RIG, calibration=str(record)))
        listed = service.open_warnings(Deployment.RIG_FIXED)

        refused = _step(service, _open(accepted=()))
        assert service.session is None and f"{code}: " in _refused(refused)[-1], name
        assert _kinds(folders[2]) == [], name
        opened = _step(service, _open(accepted=tuple(e.key for e in listed)))

        assert opened.phase == "between_runs", name
        rows = _jsonl(folders[2] / "2027-01-14_01" / "xcon" / "warnings.jsonl")
        assert code in [r["code"] for r in rows], name
```

Replace:

```python

def test_a_calibration_problem_fails_every_runs_preflight_naming_it(tmp_path):
    """The review's C1 (Review Focus 3): a record dated after today, or one that will not
    load, is a warning no kind accepts. The open is taken, every run's pre-flight fails on
    its `warnings` item with the sentence, and the session ends with its return."""
```

with:

```python

def test_a_calibration_problem_accepted_at_the_open_lets_every_run_start(tmp_path):
    """XC-352's E1 and E2: accepted once at the open, a record dated after today, or one that
    will not load, is not asked again; the runs start, and the session ends with its return."""
```

Replace:

```python

    for name, record, said in (
        ("future", future, "calibration age: calibration rig1 is dated"),
        ("broken", tmp_path / "broken.json", "calibration record: refused: the calibration"),
    ):
```

with:

```python

    for name, record in (("future", future), ("broken", tmp_path / "broken.json")):
```

Replace:

```python
        service = _made(folders, rig=dataclasses.replace(RIG, calibration=str(record)))
        _step(service, _open())

        refused = _step(service, _start())

        assert refused.run_index is None and _runs(folders[2]) == [], name
        assert (f"pre-flight failed, so the run does not start: warnings: a training session "
                f"does not accept {said}") in _refused(refused)[-1], name
```

with:

```python
        service = _made(folders, rig=dataclasses.replace(RIG, calibration=str(record)))
        _step(service, _open(accepted=tuple(
            e.key for e in service.open_warnings(Deployment.RIG_FIXED))))

        started = _step(service, _start())

        assert started.run_index == 0, name
        item = {r["name"]: r for r in _runs(folders[2])[0]["preflight"]}["warnings"]
        assert "calibration age" not in item["said"], name
        assert "calibration record" not in item["said"], name
        _run_to_its_end(service)
```

Replace:

```python
):
    """The second review's Minor 12: the operator who started it sees why every run will
    be refused, before any page is opened."""
```

with:

```python
):
    """The second review's Minor 12: the operator who started it sees why, before any page is
    opened, and that sessions run on the default in its place (XC-352's E1)."""
```

Replace:

```python
    assert "  calibration: refused: the calibration" in out
    assert "every run's pre-flight fails on it" in out
```

with:

```python
    assert "  calibration: refused: the calibration" in out
    assert "sessions run on the default calibration, the sRGB standard, with a warning" in out
```

**`tests/test_taskd.py`**:

Replace:

```python
def test_a_session_with_no_calibration_runs_nothing(tmp_path):
    """Call 19's backstop: `wlx taskd` gives a session no calibration while the rig's record
    will not load, and its pre-flight refuses every run (Task 12); `run` refuses one too."""
```

with:

```python
def test_a_session_with_no_calibration_runs_nothing(tmp_path):
    """Call 19's backstop, for a caller that gives a session no calibration: since XC-352's E1
    neither `wlx taskd` nor `wlx run` does, the default standing in for a record that will not
    load; `run` refuses one."""
```

**`tests/test_warnlist.py`** (5 replacements, in order):

Replace:

```python
from wl_xcon.findings import NOT_RECORDING, SESSION_KINDS, Finding
from wl_xcon.link import PreflightItem
```

with:

```python
from wl_xcon.findings import NOT_RECORDING, SESSION_KINDS, Finding
from wl_xcon.link import NOTE_LIMIT, PreflightItem
```

Replace:

```python

def test_a_calibration_dated_after_today_is_accepted_in_no_kind():
    """The review's C1: no session kind accepts it, so every run's pre-flight fails on it --
    and nothing else does: an open, an end and a return never read it (Call 19)."""
```

with:

```python

def test_a_calibration_dated_after_today_is_a_warning_in_every_kind_to_check_the_clock():
    """XC-352's E2 (the PI, 2026-10-11): its date or this host's clock is wrong, which a warning
    says, in every session kind, never a refusal (until then no kind accepted it)."""
```

Replace:

```python

    assert (entry.code, entry.accepted_in) == ("calibration age", ())
    assert [warnlist.refused([entry], kind) for kind in SESSION_KINDS] == [[entry]] * 3
    assert "after today" in entry.detail and "every run's pre-flight fails" in entry.detail
    # Read once and its clock anchored once, both as `wlx taskd` starts (the final review).
    assert entry.detail.endswith(
        "until the one that is wrong is corrected and wlx taskd started again"
    )
```

with:

```python

    assert (entry.code, entry.accepted_in) == ("calibration age", SESSION_KINDS)
    assert [warnlist.refused([entry], kind) for kind in SESSION_KINDS] == [[]] * 3
    assert "after today" in entry.detail and "check this host's clock" in entry.detail
```

Replace:

```python

def test_a_calibration_that_will_not_load_is_one_entry_no_kind_accepts():
```

with:

```python

def test_a_calibration_that_will_not_load_is_a_warning_that_the_default_runs_in_its_place():
    """XC-352's E1 (the PI, 2026-10-11): the session falls back to the sRGB default with a
    warning, in every kind, quoting why the record would not load -- cut, so the whole sentence
    stays within what an open's form sends back (`link.NOTE_LIMIT`)."""
```

Replace:

```python
    (entry,) = warnlist.of_unloaded(refusal)

    assert (entry.code, entry.accepted_in) == ("calibration record", ())
    assert entry.detail.startswith(refusal) and "every run's pre-flight fails" in entry.detail
```

with:

```python
    (entry,) = warnlist.of_unloaded(refusal)
    (long,) = warnlist.of_unloaded("refused: " + "x" * 2_000)

    assert (entry.code, entry.accepted_in) == ("calibration record", SESSION_KINDS)
    assert entry.detail.startswith(refusal)
    assert "this session runs on the default calibration, the sRGB standard" in entry.detail
    assert len(long.detail) <= NOTE_LIMIT and "…" in long.detail
    # Cut in its middle: a record's refusal names its path first and why it would not load last.
    assert long.detail.startswith("refused: xxx")
    # The default's own warning says why it stands in, never that the rig names none (the
    # warnings-over-refusals review's M4).
    (default,) = warnlist.of_calibration(SRGB, TODAY, unloaded=True)
    assert default.detail.startswith("the calibration record the rig names would not load, so ")
```

- [ ] **Step 2: Run them and see them fail**

Run: `$PY -m pytest -q -p no:cacheprovider tests/test_cone_colors.py`
Expected: an `ImportError: cannot import name 'HELD_WITHOUT_SPECTRA' from 'wl_xcon.photometry'` as the module is collected.

Run: `$PY -m pytest -q -p no:cacheprovider tests/test_cli.py tests/test_color.py tests/test_display_calibration.py tests/test_reference_tasks.py tests/test_service.py tests/test_taskd.py tests/test_warnlist.py`
Expected: `19 failed, 948 passed`: the warnings accepted in no kind; the service starting with no calibration; `wlx run` and `wlx check` refusing the record; a spectra-less panel refusing cone colors.

- [ ] **Step 3: Implement**

**`wl_xcon/check.py`** (2 replacements, in order):

Replace:

```python
    for what, color in _colors(trial, params):
        # With no calibration at all -- `wlx taskd` while the rig's record will not load (the
        # engine B plan, call 19), or a direct `check()` call -- an absolute luminance is not
        # checked here, since every run's pre-flight fails on the missing calibration; on the
        # default it is the session's one warning (`warnlist.of_calibration`, accepted at the
        # open). Any other color with no calibration is unmeasured once, as written; with one,
```

with:

```python
    for what, color in _colors(trial, params):
        # With no calibration at all -- a direct `check()` call; no session runs without one
        # since XC-352's E1 (2026-10-11), the default standing in for a record that will not
        # load -- an absolute luminance is not checked here; on the default it is the session's
        # one warning (`warnlist.of_calibration`, accepted at the open). Any other color with no
        # calibration is unmeasured once, as written; with one,
```

Replace:

```python
        findings += _default_faults(trial, params)
    return findings

```

with:

```python
        findings += _default_faults(trial, params)
    if panel is not None and not panel.standard and panel.spectra is None:
        findings += _spectra_faults(trial, params, panel)
    return findings


def _spectra_faults(trial: Trial, params: dict[str, Param], panel: Calibration) -> list[Finding]:
    """Cone colors on a measured calibration without spectra, which convert as the default's do
    (COL-18's conversion): **a warning in every kind** (the PI, 2026-10-11, XC-352's E3: "convert
    as the default does, with COL-18's sentence"; refused until then, so a panel measured without
    spectra ran fewer tasks than the unmeasured default). One per task, naming its cone colors."""
    named = sorted({what for what, color in _colors(trial, params)
                    if isinstance(color, CONE_COLORS)})
    if not named:
        return []
    return [Finding("cone-colors-without-spectra", (
        f"calibration {panel.id or panel.measured_on} was measured without spectra, so this task's "
        f"cone colors (DKL, cone contrast) convert as the default's do, through the inverse of the "
        f"CIE's LMS-to-XYZ_F,10 matrix applied to its measured CIE 1931 XYZ, a use outside the "
        f"CIE's definition, so how far each is from the cone contrast it names is unknown, and the "
        f"luminance they hold constant is its measured CIE 1931 Y (COL-18); the colors it names: "
        f"{'; '.join(named)}"), blocking=False, accepted_in=SESSION_KINDS)]

```

**`wl_xcon/cli.py`** (6 replacements, in order):

Replace:

```python
    standard -- when it names none. **A named record that will not load refuses**, with its
    sentence: it never falls back to the default, which would run a session on an unmeasured
    panel its operator believes measured. `wlx check` and `wlx run` let this refusal stop
    them, since no animal waits on either; `wlx taskd` keeps its sentence and fails every run
    on it (the engine B plan, calls 19 and 20)."""
```

with:

```python
    standard -- when it names none. **A named record that will not load refuses**, with its
    sentence. Its callers put the default in its place with a warning saying why
    (`_calibration_or_default`, `service.Service`; the PI, 2026-10-11, XC-352's E1), so no
    session runs on an unmeasured panel its operator believes measured."""
```

Replace:

```python
        raise SystemExit(f"refused: the calibration {rig_path} names, {path}: {refused}") from refused

```

with:

```python
        raise SystemExit(f"refused: the calibration {rig_path} names, {path}: {refused}") from refused


def _calibration_or_default(rig: Rig, rig_path) -> tuple[Calibration, str]:
    """The calibration a rig names, with "" -- or, when the record will not load, **the default
    in its place, with why** (the PI, 2026-10-11, XC-352's E1: "fall back to the default with a
    warning"), which `warnlist.of_unloaded` makes the warning a session accepts. `wlx run` and
    `wlx check` read the rig's calibration through this; a rig file's own refusal of its field
    (not the path of a record) still stops them."""
    try:
        return _load_calibration(rig, rig_path), ""
    except SystemExit as refused:
        if not str(refused.code).startswith("refused: the calibration "):
            raise
        return SRGB, str(refused.code)

```

Replace:

```python
        # not this command.
        # The rig's color calibration (engine spec §7.1): a record that will not load refuses
        # here, before anything is recorded (the engine B plan, call 20).
        calibration = _load_calibration(rig, args.rig)
```

with:

```python
        # not this command.
        # The rig's color calibration (engine spec §7.1): the default in the place of a record
        # that will not load, with a warning saying why (XC-352's E1), accepted below.
        calibration, unloaded = _calibration_or_default(rig, args.rig)
```

Replace:

```python
        # today's unknowns is among them. A task warning its kind does not accept was refused
        # above; a calibration dated after today, which no kind accepts, is refused here (the
        # engine B plan, call 20); the rest are accepted by the flag, or the session does not
        # start. Said through `_printable`: a task's warning quotes the task.
        warnings = (
            warnlist.of_calibration(calibration, date.fromtimestamp(time.time()))
```

with:

```python
        # today's unknowns is among them. A task warning its kind does not accept was refused
        # above, and one of the rig's would be here (since XC-352's E1 and E2, 2026-10-11, none
        # is); the rest are accepted by the flag, or the session does not start. Said through
        # `_printable`: a task's warning quotes the task.
        warnings = (
            (warnlist.of_unloaded(unloaded) if unloaded else [])
            + warnlist.of_calibration(calibration, date.fromtimestamp(time.time()),
                                      unloaded=bool(unloaded))
```

Replace:

```python
    rig = _load_rig(args.rig)
    # A record that will not load refuses here (the engine B plan, call 20).
    calibration = _load_calibration(rig, args.rig)
```

with:

```python
    rig = _load_rig(args.rig)
    # The default in the place of a record that will not load, said below (XC-352's E1).
    calibration, unloaded = _calibration_or_default(rig, args.rig)
```

Replace:

```python
                findings.append(finding)
    # **With a kind, the calibration's own warnings first**, as `wlx run` lists them (the
    # engine B plan, call 20: one dated after today is accepted in no kind). Without one there
    # is no session to judge them for. The deployment's are `wlx run`'s: a check names none.
    rig_warnings = (
        [] if args.session_kind is None
        else warnlist.of_calibration(calibration, date.fromtimestamp(time.time()))
    )
```

with:

```python
                findings.append(finding)
    # **The calibration's own warnings first**, as `wlx run` lists them: a record that will not
    # load, always, since the task was checked against the default in its place (XC-352's E1);
    # and with a kind, the calibration's age or the default (without one there is no session to
    # judge them for). The deployment's are `wlx run`'s: a check names none.
    rig_warnings = (warnlist.of_unloaded(unloaded) if unloaded else []) + (
        [] if args.session_kind is None
        else warnlist.of_calibration(calibration, date.fromtimestamp(time.time()),
                                     unloaded=bool(unloaded))
    )
```

**`wl_xcon/link.py`**:

Replace:

```python
    #: `session.spec.calibration.id`: the color calibration colors are checked against, or
    #: `None` while the rig's record will not load (the engine B plan, call 19).
```

with:

```python
    #: `session.spec.calibration.id`: the color calibration colors are checked against, or
    #: `None` for a session given none, which neither `wlx taskd` nor `wlx run` does since
    #: XC-352's E1 (2026-10-11): the default stands in for a record that will not load.
```

**`wl_xcon/photometry.py`** (4 replacements, in order):

Replace:

```python
        from its spectrum (`cones.excitations`), times the inverse of the primaries' measured XYZ
        -- exact for every mixture of the three, which is every light the panel makes. Without
        spectra, or when the bundled table is refused (`cones.cie_file`), there is no matrix and
        `cones_refused` says why: plain colors still check, and each cone color is refused with
        that sentence."""
```

with:

```python
        from its spectrum (`cones.excitations`), times the inverse of the primaries' measured XYZ
        -- exact for every mixture of the three, which is every light the panel makes. **Measured
        without spectra, as the standard does**: the inverse of the CIE's matrix applied to its
        measured CIE 1931 XYZ (the PI, 2026-10-11, XC-352's E3; `check`'s
        `cone-colors-without-spectra` warns of it; until then it converted none). When the bundled
        table is refused (`cones.cie_file`), there is no matrix and `cones_refused` says why: plain
        colors still check, and each cone color is refused with that sentence."""
```

Replace:

```python
        name = self.id or self.measured_on
        if self.standard:
            matrix = _inverse3(cones.LMS_TO_XYZ_F10)
        elif self.spectra is None:
            refused = (
                f"calibration {name} was measured without spectra, so no cone color converts "
                f"against it: a measured calibration converts cone colors from its primaries' "
                f"spectra (engine spec §7.9)"
            )
```

with:

```python
        name = self.id or self.measured_on
        if self.standard or self.spectra is None:
            matrix = _inverse3(cones.LMS_TO_XYZ_F10)
```

Replace:

```python
VIA_SPECTRA = "its primaries' measured spectra"
#: What a `DKL` number means, as a record states it: the normalization must be stated whenever
```

with:

```python
VIA_SPECTRA = "its primaries' measured spectra"
#: How one measured without spectra converts them, as the standard does (XC-352's E3).
VIA_WITHOUT_SPECTRA = (
    "the inverse of the CIE's LMS-to-XYZ_F,10 matrix applied to the measured primaries' CIE 1931 "
    "XYZ, a use outside the CIE's definition, since it was measured without spectra"
)
#: And which luminance its isoluminance holds.
HELD_WITHOUT_SPECTRA = "the measured CIE 1931 Y, which the CIE's matrix equates with V_F,10"
#: What a `DKL` number means, as a record states it: the normalization must be stated whenever
```

Replace:

```python
        via, held = VIA_STANDARD, HELD_STANDARD
    elif panel.cones is not None:
```

with:

```python
        via, held = VIA_STANDARD, HELD_STANDARD
    elif panel.cones is not None and panel.spectra is None:
        via, held = VIA_WITHOUT_SPECTRA, HELD_WITHOUT_SPECTRA
    elif panel.cones is not None:
```

**`wl_xcon/preflight.py`** (2 replacements, in order):

Replace:

```python
    **Its findings come back too**, for the run's `warnings` item: a warning is never this
    item's fail, whatever the session's kind; and `calibration` is the session's, or `None`
    while the rig's record will not load (the engine B plan, call 19). **The session's deployment**
```

with:

```python
    **Its findings come back too**, for the run's `warnings` item: a warning is never this
    item's fail, whatever the session's kind; and `calibration` is the session's (the default in
    the place of a record that will not load, since XC-352's E1). **The session's deployment**
```

Replace:

```python
    """The run's warnings (engine spec §19.2-19.3): the rig's calibration's, the deployment's
    and its task's. **Fail** when the session's kind does not accept one -- among them a
    calibration that will not load or is dated after today, which no kind accepts (the engine
    B plan, call 19); **unknown**, acknowledged by name, when any is not yet accepted this
```

with:

```python
    """The run's warnings (engine spec §19.2-19.3): the rig's calibration's, the deployment's
    and its task's. **Fail** when the session's kind does not accept one (since the PI's rulings
    on XC-352, 2026-10-11, no warning the rig lists is one; a calibration that will not load or
    is dated after today was); **unknown**, acknowledged by name, when any is not yet accepted this
```

**`wl_xcon/service.py`** (6 replacements, in order):

Replace:

```python
from wl_xcon.geometry import Rig
from wl_xcon.photometry import Calibration
```

with:

```python
from wl_xcon.geometry import Rig
from wl_xcon.photometry import SRGB, Calibration
```

Replace:

```python
        self.allocation, self.allocation_path = allocation, allocation_path
        #: The rig's color calibration (engine spec §7.1, §7.6), loaded once, here -- or
        #: `None` when the record the rig names will not load, `calibration_refused` saying
        #: why. **Which never stops `wlx taskd`** (the engine B plan, call 19): a stranded
        #: session's return is taken only through a running service, and an open, an end and
        #: a return never read this; every run's pre-flight fails on it instead (Task 12).
        self.calibration: Calibration | None = None
```

with:

```python
        self.allocation, self.allocation_path = allocation, allocation_path
        #: The rig's color calibration (engine spec §7.1, §7.6), loaded once, here -- or **the
        #: default, the sRGB standard, in the place of a record the rig names that will not
        #: load**, `calibration_refused` saying why (the PI, 2026-10-11, XC-352's E1: "fall back
        #: to the default with a warning"; `warnlist.of_unloaded`, which an open asks to accept).
        #: **Which never stops `wlx taskd`** (the engine B plan, call 19): a stranded session's
        #: return is taken only through a running service.
        self.calibration: Calibration = SRGB
```

Replace:

```python
        """The rig's calibration on the warnings list (engine spec §7.1, §7.10): the default,
        a measured one's age past 30 days, one dated after today -- or, while the record the
        rig names will not load, that, which no session kind accepts (the engine B plan,
        call 19)."""
        if self.calibration is None:
            return warnlist.of_unloaded(self.calibration_refused)
        return warnlist.of_calibration(self.calibration, self._today())
```

with:

```python
        """The rig's calibration on the warnings list (engine spec §7.1, §7.10): the default,
        a measured one's age past 30 days, one dated after today -- and, while the record the
        rig names will not load, that the default runs in its place, first (XC-352's E1), the
        default's own sentence saying why it stands in (the warnings-over-refusals review's M4)."""
        refused = self.calibration_refused
        unloaded = warnlist.of_unloaded(refused) if refused else []
        return unloaded + warnlist.of_calibration(self.calibration, self._today(),
                                                  unloaded=bool(refused))
```

Replace:

```python
        **And its warnings** (engine build B): those the session's kind accepts, accepted on
        the form by their sentences, or the open is refused before anything is marked; a
        calibration problem is never one of them (it fails every run instead). If the
```

with:

```python
        **And its warnings** (engine build B): those the session's kind accepts, accepted on
        the form by their sentences, or the open is refused before anything is marked; since
        XC-352's E1 and E2 (the PI, 2026-10-11) a calibration that will not load, or is dated after
        today, is one of them, accepted in every kind. If the
```

Replace:

```python
        # its sentence (the engine B plan, calls 7 and 25), refused before anything is marked
        # or written, as a refused departure is. One no kind accepts -- a calibration that will
        # not load or is dated after today -- is not offered and never refuses an open: it
        # fails every run's pre-flight (call 19). This is the open's only new refusal.
```

with:

```python
        # its sentence (the engine B plan, calls 7 and 25), refused before anything is marked
        # or written, as a refused departure is. One no kind accepts is not offered and never
        # refuses an open; since XC-352's E1 and E2 (2026-10-11) none is. This is the open's
        # only new refusal.
```

Replace:

```python
            )
        if service.calibration is None:
            # Said where the operator started it (the second review's Minor 12): every run
            # this service takes will be refused until the record loads.
            # Through `_printable`, as the console prints it: the sentence quotes the record's
            # path and what its loader said, its field names among them.
            print(
                f"  calibration: {_printable(service.calibration_refused)}; every run's pre-flight "
                f"fails on it until the record is repaired and wlx taskd started again"
```

with:

```python
            )
        if service.calibration_refused:
            # Said where the operator started it (the second review's Minor 12), whole: the
            # open's warning quotes it cut (XC-352's E1). Through `_printable`, as the console
            # prints it: the sentence quotes the record's path and what its loader said.
            print(
                f"  calibration: {_printable(service.calibration_refused)}; sessions run on the "
                f"default calibration, the sRGB standard, with a warning, until the record is "
                f"repaired and wlx taskd started again"
```

**`wl_xcon/taskd.py`** (2 replacements, in order):

Replace:

```python
    #: names, or `photometry.SRGB`, the default, when it names none (spec §7.1). **Required,
    #: with no default** (the engine B plan, call 14). `None` only in `wlx taskd` while the
    #: rig's record will not load (call 19), and `run` then refuses every run.
```

with:

```python
    #: names, or `photometry.SRGB`, the default, when it names none (spec §7.1). **Required,
    #: with no default** (the engine B plan, call 14). `None` only from a caller that gives
    #: none -- since XC-352's E1 (2026-10-11) `wlx taskd` and `wlx run` put the default in the
    #: place of a record that will not load -- and `run` then refuses every run.
```

Replace:

```python
        if self.spec.calibration is None:
            # The backstop for a caller that took no pre-flight (the engine B plan, call 19):
            # `wlx taskd`'s pre-flight fails every run while the rig's record will not load.
```

with:

```python
        if self.spec.calibration is None:
            # The backstop for a caller that gives no calibration (the engine B plan, call 19);
            # since XC-352's E1 neither `wlx taskd` nor `wlx run` does.
```

**`wl_xcon/warnlist.py`** (5 replacements, in order):

Replace:

```python
**What this build lists:** the default calibration and a calibration past 30 days (spec §7.1,
§7.10); a calibration that will not load or is dated after today, which no kind accepts (the
engine B plan, call 19: every run's pre-flight fails on it, and nothing else reads it); a
chaired session's free head (§5.9); a task's warnings, its load-time findings that
```

with:

```python
**What this build lists:** the default calibration and a calibration past 30 days (spec §7.1,
§7.10); a calibration that will not load, in whose place the default runs, and one dated after
today (accepted in every kind since the PI's rulings on XC-352, 2026-10-11, E1 and E2: no kind
accepted them, and every run's pre-flight failed on them, until then); a chaired session's free
head (§5.9); a task's warnings, its load-time findings that
```

Replace:

```python

from wl_xcon.findings import SESSION_KINDS, kind_named
```

with:

```python

from wl_xcon import link as _link
from wl_xcon.findings import SESSION_KINDS, kind_named
```

Replace:

```python
def of_calibration(calibration: Calibration, today: date) -> list[Entry]:
    """The calibration's: the default's, or a measured one's age past 30 days -- or, dated
    after `today`, one no session kind accepts, since its date or this host's clock is wrong
    (the engine B plan, call 19). **Its sentence says `wlx taskd` must start again**, as
    `of_unloaded`'s does (the engine B final review): the service reads the record once and
    anchors its clock once, both as it starts, so a corrected file or clock counts only then."""
    if calibration.standard:
        return [Entry(DEFAULT_CALIBRATION, (
            f"the rig names no measured calibration, so colors and luminances are the sRGB "
```

with:

```python
def of_calibration(calibration: Calibration, today: date, unloaded: bool = False) -> list[Entry]:
    """The calibration's: the default's, or a measured one's age past 30 days -- or, dated
    after `today`, a warning in every kind that its date or this host's clock is wrong (the PI,
    2026-10-11, XC-352's E2; no kind accepted it until then, the engine B plan's call 19). Every
    sentence an open can be asked to accept fits `link.NOTE_LIMIT`, which the open's form sends
    back (a calibration's id is at most `photometry.ID_LIMIT` characters). **`unloaded`**: the
    default stands in for a record the rig names that would not load (`of_unloaded`, listed
    first; XC-352's E1), and its sentence says so, not that the rig names none (the
    warnings-over-refusals review's M4)."""
    if calibration.standard:
        why = ("the calibration record the rig names would not load" if unloaded
               else "the rig names no measured calibration")
        return [Entry(DEFAULT_CALIBRATION, (
            f"{why}, so colors and luminances are the sRGB "
```

Replace:

```python
            f"calibration {calibration.id} is dated {calibration.measured_on}, after today "
            f"({today.isoformat()}): its date or this host's clock is wrong, and no session kind "
            f"accepts it, so every run's pre-flight fails on it until the one that is wrong is "
            f"corrected and wlx taskd started again"), ())]
```

with:

```python
            f"calibration {calibration.id} is dated {calibration.measured_on}, after today "
            f"({today.isoformat()}): its date or this host's clock is wrong; check this host's "
            f"clock, which every welfare time is anchored to, and the record's date (wlx taskd "
            f"reads both as it starts)"), SESSION_KINDS)]
```

Replace:

```python
    """A calibration record the rig names and that will not load, as `cli._load_calibration`
    refused it (the review's C1): one entry no session kind accepts, so every run's pre-flight
    fails on it, with the refusal's own sentence, while `wlx taskd` goes on taking opens, ends
    and returns."""
    return [Entry(CALIBRATION_RECORD, (
        f"{refusal}; no session kind accepts a calibration that will not load, so every run's "
        f"pre-flight fails on it until the record is repaired and wlx taskd started again"), ())]
```

with:

```python
    """A calibration record the rig names and that will not load, as `cli._load_calibration`
    refused it: **a warning in every kind that the default runs in its place** (the PI,
    2026-10-11, XC-352's E1: "fall back to the default with a warning"; no kind accepted it, and
    every run's pre-flight failed on it, until then). The refusal is quoted cut in its middle, so
    the whole sentence stays within `link.NOTE_LIMIT`, which the open's form sends back, and keeps
    why it would not load; `wlx taskd` prints it whole as it starts."""
    tail = (
        "; this session runs on the default calibration, the sRGB standard, in its place, until "
        "the record is repaired and read again (wlx taskd reads it as it starts; engine spec §7.1)"
    )
    room = _link.NOTE_LIMIT - len(tail)
    if len(refusal) > room:
        # Its middle cut: a record's refusal names its path first and why it would not load last.
        head = room // 3
        refusal = refusal[:head] + "…" + refusal[-(room - head - 1):]
    return [Entry(CALIBRATION_RECORD, refusal + tail, SESSION_KINDS)]
```

The docs it invalidates:

**`docs/design/architecture.md`**:

Replace:

```markdown
by its code and its sentence, and that is its only new refusal; a calibration problem (a
calibration that will not load or is dated after today) never refuses an open and never stops
`wlx taskd`, and fails every run instead, as a fault listing the warnings does; what an open
```

with:

```markdown
by its code and its sentence, and that is its only new refusal; since the PI's rulings on XC-352
(2026-10-11, E1 and E2) a calibration that will not load, in whose place the default runs, and
one dated after today are among those warnings, accepted in every kind (until then no kind
accepted them, and they failed every run instead); none stops `wlx taskd`; what an open
```

**`docs/design/architecture.md`**:

Replace:

```markdown
(`photometry.cone_xyz`): on the default through the CIE's LMS-to-XYZ_F,10 matrix inverted, on a
measured record through its primaries' spectra (ADR-0011).
```

with:

```markdown
(`photometry.cone_xyz`): on the default through the CIE's LMS-to-XYZ_F,10 matrix inverted, on a
measured record through its primaries' spectra (ADR-0011), and on one measured without spectra as
on the default, with a warning (XC-352's E3).
```

- [ ] **Step 4: Run them and see them pass**

Run the eight files, then the whole suite. Expected: `994 passed`; the suite **3504 passed**.

- [ ] **Step 5: Prove they can fail**

Over the eight files:
- `of_calibration`'s future-dated `SESSION_KINDS` → `()`: nine fail.
- `of_unloaded`'s `SESSION_KINDS` → `()`: seven fail.
- `Service.__init__`'s `self.calibration: Calibration = SRGB` → `= None`: four fail.
- `calibration_warnings`' `unloaded = warnlist.of_unloaded(refused) if refused else []` → `unloaded = []`: four fail.
- `_calibration_or_default`'s `if not str(refused.code).startswith(…):` → `if True:`: two fail (`wlx run`'s and `wlx check`'s).
- `of_unloaded`'s `if len(refusal) > room:` → `if False:`: `test_a_calibration_that_will_not_load_is_a_warning_that_the_default_runs_in_its_place`, `test_an_idle_frames_sentences_are_cut_as_the_wire_cuts_its_other_text` and `test_every_warning_an_open_can_be_asked_to_accept_reaches_the_frame_whole` fail.
- `_convert`'s `if self.standard or self.spectra is None:` → `if self.standard:`, run over `tests/test_cone_colors.py tests/test_display_calibration.py tests/test_reference_tasks.py` (`tests/test_color.py` then fails to collect, building a spectra-less panel at import, which is no catch): eight fail.
- `_color_faults`' `if panel is not None and not panel.standard and panel.spectra is None:` → `if False:`: `test_a_cone_color_on_a_measured_calibration_without_spectra_is_a_warning_naming_the_conversion` and `test_the_search_task_runs_on_a_measured_display_without_spectra_with_a_warning` fail.
- `cone_record`'s spectra-less branch `elif panel.cones is not None and panel.spectra is None:` → `elif False:`: `test_a_record_says_how_its_cone_colors_became_light` fails.
- `calibration_warnings`' `unloaded=bool(refused))` → `unloaded=False)` (the default's sentence says the rig names none, M4): `test_a_calibration_record_that_will_not_load_runs_sessions_on_the_default_with_a_warning` fails.
- `of_calibration`'s `… if unloaded` → `… if False`: that test and `test_a_calibration_that_will_not_load_is_a_warning_that_the_default_runs_in_its_place` fail.

- [ ] **Step 6: Commit**

```bash
git add wl_xcon/ tests/ docs/design/architecture.md
git commit -m "Run on the default in a calibration record's place, accept one dated after today, convert cone colors without spectra, each with a warning"
```
Body: XC-352's E1, E2 and E3 (the PI, 2026-10-11, approving the audit's proposals); the engine B plan's calls 19 and 20 and the A2 plan's call 8, superseded; call 6; `Service._open`'s code unchanged (its docstring and one comment reworded, Appendix A, item 3); the unloaded default's own sentence (the review's M4); three long lines rewrapped (M3); the count; the breaks seen failing.

---

### Task 7: The stereoscope runs on the nominal half-IPD, another animal's settings or an undrawn half-IPD, and direct view ignores settings, each with a warning (XC-352's C6, C7, C8, H4)

An animal with no settings file gets the optics drawing's nominal half-IPD, 1.6 cm (`geometry.NOMINAL_HALF_IPD_CM`), recorded as nominal (`config.json`'s `setup.half_ipd_nominal`); another animal's settings are used as given; a half-IPD outside 30-38 mm IPD builds a field the optics extrapolate; `--subject-settings` given with direct view is ignored. Each is a warning in every kind, saying so: in `wlx taskd` the session's setup warnings, asked with the first run's pre-flight (call 7); in `wlx run`, with its other warnings; in `wlx check`, printed. A half-IPD with no positive optical path is still refused. **An open these three refused now goes ahead and marks the departure**: `Service._open` builds its session through `_build`, so its code is unchanged and what it refuses narrows (Appendix A, item 4; the review's I3).

**Files:**
- Modify: `wl_xcon/geometry.py` (`NOMINAL_HALF_IPD_CM`; `Rig.half_ipd_range_cm`'s comment; `Rig.stereoscope`), `wl_xcon/warnlist.py` (codes; docstring; imports; new `of_setup`, `of_ignored_settings`), `wl_xcon/cli.py` (imports; `_load_subject_settings`, `_DIRECT_READS_NO_SETTINGS` removed, `_session_geometry`, `wlx run`, `wlx check`), `wl_xcon/service.py` (imports; `_build`; `_preflight`), `wl_xcon/taskd.py` (`SessionSpec.setup_warnings`; `_fixed_config`), `wl_xcon/preflight.py` (imports; `files`), `tasks/reference_subject.py` (docstring)
- Modify (test): `tests/test_geometry.py`, `tests/test_warnlist.py`, `tests/test_preflight.py`, `tests/test_service.py`, `tests/test_cli.py`, `tests/test_taskd.py`

**Interfaces:**
- Produces: `geometry.NOMINAL_HALF_IPD_CM = 1.6`; `Rig.stereoscope(half_ipd_cm)` refusing only a half-IPD with no positive optical path (`ValueError: "… leaves no positive optical path …"`); `warnlist.NOMINAL_HALF_IPD = "nominal half-IPD"`, `OTHER_ANIMALS_SETTINGS = "another animal's settings"`, `HALF_IPD_OUTSIDE = "half-IPD outside the optics"`, `SETTINGS_NOT_READ = "settings not read"`; `warnlist.of_setup(rig, subject, half_ipd_cm, settings, path) -> list[Entry]`; `warnlist.of_ignored_settings(path) -> list[Entry]`; `cli._load_subject_settings(path) -> SubjectSettings` (the `subject` parameter removed); `cli._session_geometry(args, rig) -> tuple[Geometry, list]`; `SessionSpec.setup_warnings: tuple = ()`; `preflight.files(bounds_path, subject, settings_path)` (the `rig` parameter removed).

- [ ] **Step 1: Write the failing tests**

**`tests/test_cli.py`** (8 replacements, in order):

Replace:

```python

def test_wlx_check_refuses_settings_that_a_direct_view_check_would_ignore(capsys):
    """`--subject-settings` holds the stereoscope's half-IPD. Given with `--view direct`
    it would be read by nothing and said nowhere; `wlx run` refuses it, in the same
    sentence (final review, item 5)."""
    with pytest.raises(SystemExit) as refused:
        main(["check", GOOD, "--rig", RIG_FILE, "--allocation", ALLOCATION,
              "--view", "direct", "--subject-settings", "tasks/reference_subject.py"])

    assert str(refused.value) == cli._DIRECT_READS_NO_SETTINGS
    assert str(refused.value).startswith("refused: --subject-settings holds")
```

with:

```python

def test_wlx_check_warns_of_settings_that_a_direct_view_check_ignores(capsys):
    """`--subject-settings` holds the stereoscope's half-IPD. Given with `--view direct` it is
    read by nothing, which a warning says (XC-352's H4; the PI, 2026-10-11), as `wlx run`'s does."""
    assert main(["check", GOOD, "--rig", RIG_FILE, "--allocation", ALLOCATION,
                 "--view", "direct", "--subject-settings", "tasks/reference_subject.py"]) == 0

    out = capsys.readouterr().out
    assert "warning  settings not read" in out and "direct view reads nothing from it" in out
```

Replace:

```python

def test_subject_settings_for_another_animal_are_refused(tmp_path):
    """Review Focus 3."""
```

with:

```python

def test_subject_settings_load_whoever_they_name(tmp_path):
    """XC-352's C8 (the PI, 2026-10-11): another animal's settings are a warning
    (`warnlist.of_setup`), so the loader reads them, naming whose they are."""
```

Replace:

```python

    with pytest.raises(SystemExit) as exited:
        _load_subject_settings(Path("tasks/reference_subject.py"), "B")
    assert "'REFERENCE'" in str(exited.value) and "'B'" in str(exited.value)
```

with:

```python

    assert _load_subject_settings(Path("tasks/reference_subject.py")).subject == "REFERENCE"
```

Replace:

```python

def test_wlx_run_in_the_stereoscope_needs_the_animals_settings(tmp_path):
    argv = _run_args(tmp_path, "--out-of-cage-at", _hhmm())
    argv[argv.index("direct")] = "stereoscope"

    with pytest.raises(SystemExit, match="needs --subject-settings"):
        main(argv)
```

with:

```python

def _warned(tmp_path) -> list[str]:
    path = tmp_path / "2027-01-14_01" / "xcon" / "warnings.jsonl"
    return [json.loads(line)["code"] for line in path.read_text().splitlines()]


def test_wlx_run_in_the_stereoscope_without_settings_runs_on_the_nominal_half_ipd(tmp_path):
    """XC-352's C6 (the PI, 2026-10-11): a warning, accepted by the flag; the record says the
    half-IPD was nominal."""
    argv = _run_args(tmp_path, "--out-of-cage-at", _hhmm())
    argv[argv.index("tasks/fixation_detection.py")] = _either_task(tmp_path, 10.0)
    argv[argv.index("direct")] = "stereoscope"

    assert _main_uninterrupted(argv) == 0

    assert "nominal half-IPD" in _warned(tmp_path)
    setup = json.loads((tmp_path / "2027-01-14_01" / "xcon" / "config.json").read_text())["setup"]
    assert (setup["half_ipd_cm"], setup["half_ipd_nominal"]) == (1.6, True)
```

Replace:

```python

def test_wlx_run_refuses_subject_settings_in_direct_view(tmp_path):
    """Direct view reads nothing from them, and accepting them would say it did."""
```

with:

```python

def test_wlx_run_warns_of_subject_settings_in_direct_view_and_records_none(tmp_path):
    """XC-352's H4: direct view reads nothing from them, which a warning says; the record names
    no settings file, since none was read."""
```

Replace:

```python

    with pytest.raises(SystemExit, match="direct view reads nothing from it"):
        main(argv)
```

with:

```python

    assert _main_uninterrupted(argv) == 0

    assert "settings not read" in _warned(tmp_path)
    config = json.loads((tmp_path / "2027-01-14_01" / "xcon" / "config.json").read_text())
    assert config["versions"]["subject_settings"] == ""
```

Replace:

```python

def test_wlx_run_refuses_another_animals_settings(tmp_path):
    """Review Focus 3, through `wlx run`."""
```

with:

```python

def test_wlx_run_runs_on_another_animals_settings_with_a_warning(tmp_path):
    """XC-352's C8 (the PI, 2026-10-11), through `wlx run`."""
```

Replace:

```python
    argv = _run_args(tmp_path, "--out-of-cage-at", _hhmm(), "--subject-settings", str(other))
    argv[argv.index("direct")] = "stereoscope"

    with pytest.raises(SystemExit, match="holds 'B'"):
        main(argv)
```

with:

```python
    argv = _run_args(tmp_path, "--out-of-cage-at", _hhmm(), "--subject-settings", str(other))
    argv[argv.index("tasks/fixation_detection.py")] = _either_task(tmp_path, 10.0)
    argv[argv.index("direct")] = "stereoscope"

    assert _main_uninterrupted(argv) == 0

    assert "another animal's settings" in _warned(tmp_path)
```

**`tests/test_geometry.py`** (2 replacements, in order):

Replace:

```python
from tasks.rig import RIG
from wl_xcon.geometry import Geometry, SubjectSettings
```

with:

```python
from tasks.rig import RIG
from wl_xcon.geometry import NOMINAL_HALF_IPD_CM, Geometry, SubjectSettings
```

Replace:

```python

def test_the_stereoscope_refuses_a_half_ipd_it_is_not_built_for():
    """The optics drawing tabulates IPD 30-38 mm (S0 §7.1.3), so the rig is built for
    half-IPDs 1.5-1.9 cm. Outside that, the mirrors and the field are nobody's drawing."""
    assert RIG.half_ipd_range_cm == (1.5, 1.9)
    RIG.stereoscope(half_ipd_cm=1.5)
    RIG.stereoscope(half_ipd_cm=1.9)
    for half in (1.49, 1.91, float("nan")):
        with pytest.raises(ValueError, match="IPD 30-38 mm"):
            RIG.stereoscope(half_ipd_cm=half)

```

with:

```python

def test_the_stereoscope_builds_any_half_ipd_its_optics_extend_to():
    """The optics drawing tabulates IPD 30-38 mm (S0 §7.1.3), so the rig is drawn for half-IPDs
    1.5-1.9 cm. Outside that, the mirrors and the field are extrapolated: a warning
    (`warnlist.of_setup`; the PI, 2026-10-11, XC-352's C7), never a refusal. A half-IPD that
    leaves no positive optical path, or is no number, has no field, and is refused."""
    assert RIG.half_ipd_range_cm == (1.5, 1.9)
    for half in (1.49, 1.91, 3.0):
        assert RIG.stereoscope(half_ipd_cm=half).half_ipd_cm == half
    for half in (100.0, float("nan")):
        with pytest.raises(ValueError, match="no positive optical path"):
            RIG.stereoscope(half_ipd_cm=half)
    assert NOMINAL_HALF_IPD_CM == 1.6

```

**`tests/test_preflight.py`** (4 replacements, in order):

Replace:

```python
    item, _, _ = preflight.task(bad, ALLOCATION, DIRECT, SRGB)
    kept = preflight.files(bad, "A", None, RIG)[0]
```

with:

```python
    item, _, _ = preflight.task(bad, ALLOCATION, DIRECT, SRGB)
    kept = preflight.files(bad, "A", None)[0]
```

Replace:

```python

    items = preflight.files(folder / "bounds.py", "REFERENCE", folder / "settings.py", RIG)
```

with:

```python

    items = preflight.files(folder / "bounds.py", "REFERENCE", folder / "settings.py")
```

Replace:

```python
        ("bounded config", "pass"), ("subject settings", "pass"),
    ]

```

with:

```python
        ("bounded config", "pass"), ("subject settings", "pass"),
    ]


def test_settings_that_name_another_animal_or_an_undrawn_half_ipd_pass_saying_so(tmp_path):
    """XC-352's C7 and C8 (the PI, 2026-10-11): warnings, listed with the run's (the session's
    `setup_warnings`), so the re-read passes, saying whose settings they are; only a file that no
    longer loads fails."""
    folder = tmp_path / "A"
    folder.mkdir()
    shutil.copy("tasks/reference_bounds.py", folder / "bounds.py")
    (folder / "settings.py").write_text(
        "from wl_xcon.geometry import SubjectSettings\n"
        "SETTINGS = SubjectSettings(subject='B', half_ipd_cm=2.4)\n")

    _, settings = preflight.files(folder / "bounds.py", "REFERENCE", folder / "settings.py")

    assert settings.result == "pass"
    assert "gives 'B''s half-IPD of 2.4 cm" in settings.said

```

Replace:

```python

    items = preflight.files(folder / "bounds.py", "B", folder / "settings.py", RIG)
```

with:

```python

    items = preflight.files(folder / "bounds.py", "B", folder / "settings.py")
```

**`tests/test_service.py`** (2 replacements, in order):

Replace:

```python
        ({"animal": "C"}, "there is no animal 'C'"),
        ({"view": "stereoscope", "animal": "B"}, "settings"),
```

with:

```python
        ({"animal": "C"}, "there is no animal 'C'"),
```

Replace:

```python
    assert len(items["warnings"].said) < 3_000, "5,392 with one per light and per isoluminant color"

```

with:

```python
    assert len(items["warnings"].said) < 3_000, "5,392 with one per light and per isoluminant color"


def _narrow(service) -> str:
    """`fixation_detection`, its target held to ±10° so the stereoscope's ±12° mask shows it."""
    text = Path("tasks/fixation_detection.py").read_text()
    for axis, start in (("x", "10.0"), ("y", "0.0")):
        wide = f'Param("target_{axis}", unit="deg", low=-16.0, high=16.0, start={start})'
        assert text.count(wide) == 1
        text = text.replace(wide, f'Param("target_{axis}", unit="deg", low=-10.0, high=10.0, start={start})')
    (service.tasks / "narrow.py").write_text(text)
    return "narrow.py"


@pytest.mark.parametrize(("settings", "code"), [
    (None, "nominal half-IPD"),
    ("SubjectSettings(subject='B', half_ipd_cm=1.7)", "another animal's settings"),
    ("SubjectSettings(subject='REFERENCE', half_ipd_cm=2.0)", "half-IPD outside the optics"),
], ids=["no settings file", "another animal's", "outside the drawn optics"])
def test_a_stereoscope_session_runs_on_its_settings_warnings_once_they_are_accepted(
    tmp_path, settings, code
):
    """XC-352's C6, C7 and C8 (the PI, 2026-10-11): an animal with no settings file runs on the
    nominal half-IPD, recorded as nominal; another animal's settings, and a half-IPD outside the
    drawn optics, run as given. Each is a warning in the run's pre-flight, and the run starts once
    it is accepted, `warnings.jsonl` recording it; until then each refused the open."""
    service = _service(tmp_path)
    found = service.subjects / "REFERENCE" / "settings.py"
    if settings is None:
        found.unlink()
    else:
        found.write_text(f"from wl_xcon.geometry import SubjectSettings\nSETTINGS = {settings}\n")
    task = _narrow(service)
    _step(service, _open(view="stereoscope"))

    checked = _step(service, CheckRun(by=BY, task=task, values=dict(VALUES)))
    started = _step(service, _start(task=task))

    item = {i.name: i for i in checked.preflight.items}["warnings"]
    assert item.result == "unknown" and f"{code}: " in item.said
    assert started.run_index == 0
    folder = service.root / "2027-01-14_01" / "xcon"
    assert [r["how"] for r in _jsonl(folder / "warnings.jsonl") if r["code"] == code] == ["start"]
    setup = json.loads((folder / "config.json").read_text())["setup"]
    assert setup["half_ipd_nominal"] is (settings is None)
    assert setup["half_ipd_cm"] == {"nominal half-IPD": 1.6, "another animal's settings": 1.7,
                                    "half-IPD outside the optics": 2.0}[code]

```

**`tests/test_taskd.py`**:

Replace:

```python
    assert config["setup"]["half_ipd_cm"] is None
    assert config["setup"]["viewing_distance_cm"] == DIRECT.viewing_distance_cm
```

with:

```python
    assert config["setup"]["half_ipd_cm"] is None
    assert config["setup"]["half_ipd_nominal"] is None, "direct view has no half-IPD"
    assert config["setup"]["viewing_distance_cm"] == DIRECT.viewing_distance_cm
```

**`tests/test_warnlist.py`** (2 replacements, in order):

Replace:

```python
from wl_xcon import warnlist
from wl_xcon.findings import NOT_RECORDING, SESSION_KINDS, Finding
from wl_xcon.link import NOTE_LIMIT, PreflightItem
```

with:

```python
from wl_xcon import warnlist
from _rig import RIG
from wl_xcon.findings import NOT_RECORDING, SESSION_KINDS, Finding
from wl_xcon.geometry import SubjectSettings
from wl_xcon.link import NOTE_LIMIT, PreflightItem
```

Replace:

```python
    assert default.detail.startswith("the calibration record the rig names would not load, so ")

```

with:

```python
    assert default.detail.startswith("the calibration record the rig names would not load, so ")


def test_a_stereoscope_built_without_settings_is_a_warning_that_records_the_half_ipd_as_nominal():
    """XC-352's C6 (the PI, 2026-10-11: "a warning; the nominal 1.6 cm is recorded as nominal")."""
    (entry,) = warnlist.of_setup(RIG, "A", 1.6, None, "")

    assert (entry.code, entry.accepted_in) == ("nominal half-IPD", SESSION_KINDS)
    assert "'A' has no settings file" in entry.detail and "not a measurement" in entry.detail
    assert "records it as nominal" in entry.detail


def test_another_animals_settings_are_a_warning_naming_whose_half_ipd_the_session_uses():
    """XC-352's C8 (the PI, 2026-10-11)."""
    theirs = SubjectSettings(subject="B", half_ipd_cm=1.7)

    (entry,) = warnlist.of_setup(RIG, "A", 1.7, theirs, "subjects/A/settings.py")

    assert (entry.code, entry.accepted_in) == ("another animal's settings", SESSION_KINDS)
    assert "these are 'B''s settings" in entry.detail and "half-IPD of 1.7 cm" in entry.detail
    assert warnlist.of_setup(RIG, "B", 1.7, theirs, "subjects/B/settings.py") == []


@pytest.mark.parametrize("half", [1.4, 2.0])
def test_a_half_ipd_outside_the_drawn_optics_is_a_warning_that_they_are_extrapolated(half):
    """XC-352's C7 (the PI, 2026-10-11: "outside the drawn optics, extrapolated")."""
    (entry,) = warnlist.of_setup(RIG, "A", half, SubjectSettings(subject="A", half_ipd_cm=half), "s.py")

    assert (entry.code, entry.accepted_in) == ("half-IPD outside the optics", SESSION_KINDS)
    assert f"a half-IPD of {half:g} cm is outside the 1.5-1.9 cm" in entry.detail
    assert "extrapolated" in entry.detail


def test_settings_direct_view_reads_nothing_from_are_a_warning_that_they_are_ignored():
    """XC-352's H4 (the PI, 2026-10-11)."""
    (entry,) = warnlist.of_ignored_settings("tasks/reference_subject.py")

    assert (entry.code, entry.accepted_in) == ("settings not read", SESSION_KINDS)
    assert "direct view reads nothing from it" in entry.detail

```

- [ ] **Step 2: Run them and see them fail**

Run: `$PY -m pytest -q -p no:cacheprovider tests/test_geometry.py`
Expected: an `ImportError: cannot import name 'NOMINAL_HALF_IPD_CM' from 'wl_xcon.geometry'` as the module is collected.

Run: `$PY -m pytest -q -p no:cacheprovider tests/test_cli.py tests/test_preflight.py tests/test_service.py tests/test_taskd.py tests/test_warnlist.py`
Expected: `18 failed, 752 passed`: `warnlist.of_setup` and `of_ignored_settings` missing; `preflight.files` still taking `rig`; the three stereoscope cases refused at the open (no settings file) or by their range or animal; `wlx run` and `wlx check` refusing; `config.json` with no `half_ipd_nominal`.

- [ ] **Step 3: Implement**

**`tasks/reference_subject.py`**:

Replace:

```python
the subject is `REFERENCE`, the one `reference_bounds.py` is written for, so a session
refuses this file for any real animal.
```

with:

```python
the subject is `REFERENCE`, the one `reference_bounds.py` is written for, so a session
warns that it holds another animal's settings for any real animal (XC-352's C8).
```

**`wl_xcon/cli.py`** (12 replacements, in order):

Replace:

```python
from wl_xcon.codes import PROVISIONAL, Allocation
from wl_xcon.geometry import VIEWS, Geometry, Rig, SubjectSettings
```

with:

```python
from wl_xcon.codes import PROVISIONAL, Allocation
from wl_xcon.geometry import NOMINAL_HALF_IPD_CM, VIEWS, Geometry, Rig, SubjectSettings
```

Replace:

```python

def _load_subject_settings(path: Path, subject: str | None) -> SubjectSettings:
    """Load one animal's settings (PI, 2026-09-29): a Python file defining `SETTINGS`.
    **Refused for another animal**, as a bounded config is, when `subject` is given:
    one animal's eye spacing is not another's."""
```

with:

```python

def _load_subject_settings(path: Path) -> SubjectSettings:
    """Load one animal's settings (PI, 2026-09-29): a Python file defining `SETTINGS`, whoever
    it names. **Another animal's is a warning, never a refusal** (the PI, 2026-10-11, XC-352's
    C8; `warnlist.of_setup`), which its caller lists."""
```

Replace:

```python
        raise SystemExit(f"{path} must define SETTINGS, a geometry.SubjectSettings")
    if subject is not None and found.subject != subject:
        raise SystemExit(
            f"refused: {path} holds {found.subject!r}'s settings and this session is "
            f"for {subject!r}; one animal's eye spacing is not another's"
        )
    return found


#: Said by `wlx run` and `wlx check` alike, so the two cannot drift apart.
_DIRECT_READS_NO_SETTINGS = (
    "refused: --subject-settings holds the stereoscope's half-IPD, and direct view "
    "reads nothing from it; leave it off, or pass --view stereoscope"
)
```

with:

```python
        raise SystemExit(f"{path} must define SETTINGS, a geometry.SubjectSettings")
    return found
```

Replace:

```python

def _session_geometry(args, rig: Rig) -> Geometry:
    """The field a `wlx run` session is held to, from `rig` (`--rig`'s, loaded once by the
    caller), `--view` and `--subject-settings` (direct-view spec §3; PI, 2026-09-29). Every
    refusal is a sentence: an unmeasured rig, an animal the stereoscope is not built for,
    another animal's file, or a file where none belongs."""
    if args.view == "direct":
        if args.subject_settings is not None:
            raise SystemExit(_DIRECT_READS_NO_SETTINGS)
```

with:

```python

def _session_geometry(args, rig: Rig) -> tuple[Geometry, list]:
    """The field a `wlx run` session is held to, from `rig` (`--rig`'s, loaded once by the
    caller), `--view` and `--subject-settings` (direct-view spec §3; PI, 2026-09-29), **with the
    warnings its setup runs with** (the PI, 2026-10-11, XC-352's C6, C7, C8 and H4; each refused
    until then): settings direct view ignores, the nominal half-IPD with no settings, another
    animal's, a half-IPD outside the drawn optics. A refusal is a sentence: an unmeasured rig,
    or a half-IPD with no field."""
    if args.view == "direct":
        setup = ([] if args.subject_settings is None
                 else warnlist.of_ignored_settings(args.subject_settings))
```

Replace:

```python
    else:
        if args.subject_settings is None:
            raise SystemExit(
                "refused: --view stereoscope needs --subject-settings, the file "
                "holding this animal's half-IPD (PI, 2026-09-29)"
            )
        half = _load_subject_settings(args.subject_settings, args.subject).half_ipd_cm
```

with:

```python
    else:
        settings = (None if args.subject_settings is None
                    else _load_subject_settings(args.subject_settings))
        half = NOMINAL_HALF_IPD_CM if settings is None else settings.half_ipd_cm
        setup = warnlist.of_setup(rig, args.subject, half, settings, args.subject_settings)
```

Replace:

```python
    try:
        return build()
```

with:

```python
    try:
        return build(), setup
```

Replace:

```python
        rig = _load_rig(args.rig)
        geometry = _session_geometry(args, rig)
```

with:

```python
        rig = _load_rig(args.rig)
        geometry, setup = _session_geometry(args, rig)
```

Replace:

```python
            + warnlist.of_deployment(deployment)
            + warnlist.of_findings(findings)
```

with:

```python
            + warnlist.of_deployment(deployment)
            + setup
            + warnlist.of_findings(findings)
```

Replace:

```python
                        rig_config=str(args.rig),
                        subject_settings=(
                            "" if args.subject_settings is None else str(args.subject_settings)
```

with:

```python
                        rig_config=str(args.rig),
                        # None read in direct view, whatever was given (XC-352's H4).
                        subject_settings=(
                            "" if args.subject_settings is None or args.view == "direct"
                            else str(args.subject_settings)
```

Replace:

```python
    settings = (
        _load_subject_settings(args.subject_settings, None)
```

with:

```python
    settings = (
        _load_subject_settings(args.subject_settings)
```

Replace:

```python
    geometries = _setups(task, rig, args.view, settings)
    if settings is not None and geometries and {g.view for g in geometries} == {"direct"}:
        raise SystemExit(_DIRECT_READS_NO_SETTINGS)
```

with:

```python
    geometries = _setups(task, rig, args.view, settings)
    # The settings' own warnings (XC-352's C7 and H4): ignored in direct view; a half-IPD
    # outside the drawn optics, through the stereoscope. A check names no animal, so whose
    # settings they are is the session's to warn of.
    setup = [] if settings is None else (
        warnlist.of_ignored_settings(args.subject_settings)
        if geometries and {g.view for g in geometries} == {"direct"}
        else warnlist.of_setup(rig, settings.subject, settings.half_ipd_cm, settings,
                               args.subject_settings)
    )
```

Replace:

```python
        else warnlist.of_calibration(calibration, date.fromtimestamp(time.time()),
                                     unloaded=bool(unloaded))
    )
```

with:

```python
        else warnlist.of_calibration(calibration, date.fromtimestamp(time.time()),
                                     unloaded=bool(unloaded))
    ) + setup
```

**`wl_xcon/geometry.py`** (3 replacements, in order):

Replace:

```python
VIEWS = ("direct", "stereoscope")

```

with:

```python
VIEWS = ("direct", "stereoscope")

#: The optics drawing's nominal half-IPD, `E`, in cm (its §1; IPD 32 mm): what the stereoscope is
#: built for when an animal has no settings file, with a warning, the session recording it as
#: nominal (the PI, 2026-10-11, XC-352's C6: "a warning; the nominal 1.6 cm is recorded as
#: nominal"; `warnlist.of_setup`). **Not a measurement** (STE-20).
NOMINAL_HALF_IPD_CM = 1.6

```

Replace:

```python
    mask_deg: float
    #: The half-IPDs the stereoscope is built for, in cm: the optics drawing's
    #: eye-separation table, IPD 30-38 mm (S0 §7.1.3). An animal outside it is refused
    #: rather than given a field nobody drew.
```

with:

```python
    mask_deg: float
    #: The half-IPDs the stereoscope is drawn for, in cm: the optics drawing's
    #: eye-separation table, IPD 30-38 mm (S0 §7.1.3). An animal outside it runs with a
    #: warning that its field is extrapolated, not drawn (the PI, 2026-10-11, XC-352's C7;
    #: `warnlist.of_setup`); it was refused until then.
```

Replace:

```python
        """Through the stereoscope, for one animal's half-IPD, `E`, from its settings
        file (spec §2; PI, 2026-09-29)."""
        low, high = self.half_ipd_range_cm
        if not low <= half_ipd_cm <= high:
            raise ValueError(
                f"a half-IPD of {half_ipd_cm:g} cm is outside the {low:g}-{high:g} cm "
                f"this stereoscope is built for (IPD {20 * low:g}-{20 * high:g} mm, the "
                f"optics drawing's table); its mirrors and its field are unknown there"
```

with:

```python
        """Through the stereoscope, for one animal's half-IPD, `E`, from its settings
        file (spec §2; PI, 2026-09-29), or the nominal one (`NOMINAL_HALF_IPD_CM`). **One
        outside `half_ipd_range_cm` is built too**, its field extrapolated (a warning,
        `warnlist.of_setup`; the PI, 2026-10-11, XC-352's C7). One that leaves no positive
        optical path, `Z + W/4 − E`, or is no number, has no field, and is refused."""
        path = self.screen_distance_cm + self.panel_width_cm / 4 - half_ipd_cm
        if not path > 0:
            raise ValueError(
                f"a half-IPD of {half_ipd_cm:g} cm leaves no positive optical path through this "
                f"stereoscope (Z + W/4 − E = {path:g} cm), so it has no field"
```

**`wl_xcon/preflight.py`** (5 replacements, in order):

Replace:

```python
from wl_xcon.cli import _load_bounds, _load_subject_settings, _load_task, _setup_words
from wl_xcon.geometry import Rig
```

with:

```python
from wl_xcon.cli import _load_bounds, _load_subject_settings, _load_task, _setup_words
```

Replace:

```python

def files(
    bounds_path: Path, subject: str, settings_path: Path | None, rig: Rig
) -> list[PreflightItem]:
    """The animal's files, read again (spec §6.2: "fail if refused"): the bounded config
    loads and names this animal, and in the stereoscope its settings load, name it, and
    give a half-IPD this rig is built for. **The session runs under what it loaded when
    it opened**; a file that no longer loads or names another animal is a sign
    something about this animal's files has gone wrong since, and blocks a new run."""
```

with:

```python

def files(bounds_path: Path, subject: str, settings_path: Path | None) -> list[PreflightItem]:
    """The animal's files, read again (spec §6.2: "fail if refused"): the bounded config
    loads and names this animal, and in the stereoscope its settings load. **The session runs
    under what it loaded when it opened**; a bounded config that no longer loads or names
    another animal, or settings that no longer load, are a sign something about this animal's
    files has gone wrong since, and block a new run. Settings naming another animal, or a
    half-IPD outside the drawn optics, pass, saying whose they are: each is a warning, which
    the run's warnings item lists from the session's open (the PI, 2026-10-11, XC-352's C7 and
    C8)."""
```

Replace:

```python
        try:
            half = _load_subject_settings(settings_path, subject).half_ipd_cm
            rig.stereoscope(half)
```

with:

```python
        try:
            found = _load_subject_settings(settings_path)
```

Replace:

```python
                    PASS,
                    f"{settings_path} loads, names {subject!r}, and gives a half-IPD of "
                    f"{half:g} cm this stereoscope is built for",
```

with:

```python
                    PASS,
                    f"{settings_path} loads and gives {found.subject!r}'s half-IPD of "
                    f"{found.half_ipd_cm:g} cm; the session runs under the setup it opened with",
```

Replace:

```python
            items.append(PreflightItem(SUBJECT_SETTINGS, FAIL, _said(refused, settings_path)))
        except ValueError as refused:
            items.append(PreflightItem(SUBJECT_SETTINGS, FAIL, str(refused)))
```

with:

```python
            items.append(PreflightItem(SUBJECT_SETTINGS, FAIL, _said(refused, settings_path)))
```

**`wl_xcon/service.py`** (6 replacements, in order):

Replace:

```python
from wl_xcon.dio import Simulated as SimulatedCard
from wl_xcon.geometry import Rig
```

with:

```python
from wl_xcon.dio import Simulated as SimulatedCard
from wl_xcon.geometry import NOMINAL_HALF_IPD_CM, Rig
```

Replace:

```python
            )
        settings_path = None
```

with:

```python
            )
        settings_path, setup = None, []
```

Replace:

```python
        else:
            settings_path = folder / "settings.py"
            if not settings_path.is_file():
                raise ValueError(
                    f"the stereoscope needs {animal!r}'s settings, and "
                    f"{settings_path} does not exist"
                )
            geometry = self.rig.stereoscope(
                _load_subject_settings(settings_path, animal).half_ipd_cm
            )
```

with:

```python
        else:
            # The animal's settings, or the nominal half-IPD with none; another animal's, or a
            # half-IPD outside the drawn optics, as given: each a warning its runs' pre-flights
            # list (the PI, 2026-10-11, XC-352's C6, C7 and C8; each refused here until then).
            found = folder / "settings.py"
            settings = _load_subject_settings(found) if found.is_file() else None
            settings_path = found if settings is not None else None
            half = NOMINAL_HALF_IPD_CM if settings is None else settings.half_ipd_cm
            setup = warnlist.of_setup(self.rig, animal, half, settings, found)
            geometry = self.rig.stereoscope(half)
```

Replace:

```python
                subject_settings="" if settings_path is None else str(settings_path),
            ),
```

with:

```python
                subject_settings="" if settings_path is None else str(settings_path),
                setup_warnings=tuple(setup),
            ),
```

Replace:

```python
            try:
                rig = self.open_warnings(session.spec.deployment)
```

with:

```python
            try:
                # The setup's warnings too (XC-352's C6-C8): known at the open, asked with the
                # first run's, accepted once a session.
                rig = (self.open_warnings(session.spec.deployment)
                       + list(session.spec.setup_warnings))
```

Replace:

```python
                        Path(session.spec.bounds_config), session.spec.subject, settings,
                        self.rig,
```

with:

```python
                        Path(session.spec.bounds_config), session.spec.subject, settings,
```

**`wl_xcon/taskd.py`** (2 replacements, in order):

Replace:

```python
    subject_settings: str = ""
    #: Rates per second, not per frame (S9/simulate). Roughly: acquires fixation
```

with:

```python
    subject_settings: str = ""
    #: The warnings a stereoscope's setup was built with (the PI, 2026-10-11, XC-352's C6, C7
    #: and C8; `warnlist.of_setup`): the nominal half-IPD for an animal with no settings file,
    #: another animal's settings, a half-IPD outside the drawn optics. A `wlx taskd` run's
    #: pre-flight lists them (`Service._preflight`), accepted once a session.
    setup_warnings: tuple = ()
    #: Rates per second, not per frame (S9/simulate). Roughly: acquires fixation
```

Replace:

```python
                "half_ipd_cm": geometry.half_ipd_cm,
                "viewing_distance_cm": geometry.viewing_distance_cm,
```

with:

```python
                "half_ipd_cm": geometry.half_ipd_cm,
                # Whether that half-IPD is the nominal one, read from no settings file (XC-352's
                # C6): `None` in direct view, which has none.
                "half_ipd_nominal": (None if geometry.view == "direct"
                                     else not self.spec.subject_settings),
                "viewing_distance_cm": geometry.viewing_distance_cm,
```

**`wl_xcon/warnlist.py`** (4 replacements, in order):

Replace:

```python
accepted them, and every run's pre-flight failed on them, until then); a chaired session's free
head (§5.9); a task's warnings, its load-time findings that
```

with:

```python
accepted them, and every run's pre-flight failed on them, until then); a chaired session's free
head (§5.9); a stereoscope's setup -- the nominal half-IPD, another animal's settings, a
half-IPD outside the drawn optics -- and settings direct view ignores (the PI's rulings on
XC-352, 2026-10-11, C6, C7, C8 and H4); a task's warnings, its load-time findings that
```

Replace:

```python
from wl_xcon.findings import SESSION_KINDS, kind_named
from wl_xcon.photometry import SRGB_WHITE_CD_M2, Calibration
```

with:

```python
from wl_xcon.findings import SESSION_KINDS, kind_named
from wl_xcon.geometry import Rig, SubjectSettings
from wl_xcon.photometry import SRGB_WHITE_CD_M2, Calibration
```

Replace:

```python
HEAD_FREE = "head free"
#: The code of a row saying the warnings could not be listed at all (`service.Service`'s idle
```

with:

```python
HEAD_FREE = "head free"
NOMINAL_HALF_IPD = "nominal half-IPD"
OTHER_ANIMALS_SETTINGS = "another animal's settings"
HALF_IPD_OUTSIDE = "half-IPD outside the optics"
SETTINGS_NOT_READ = "settings not read"
#: The code of a row saying the warnings could not be listed at all (`service.Service`'s idle
```

Replace:

```python

def of_unknowns(items: Iterable) -> list[Entry]:
```

with:

```python

def of_setup(
    rig: Rig, subject: str, half_ipd_cm: float, settings: SubjectSettings | None, path
) -> list[Entry]:
    """A stereoscope's setup for `subject`, built for `half_ipd_cm` from `settings` (read from
    `path`), or for the nominal half-IPD when there are none (the PI, 2026-10-11, XC-352's C6, C7
    and C8; each refused until then), **each a warning in every kind**: no settings file, so the
    nominal half-IPD, recorded as nominal (`config.json`'s `setup.half_ipd_nominal`); another
    animal's settings, whose half-IPD the session uses; and a half-IPD outside the optics
    drawing's table, its field extrapolated."""
    entries = []
    if settings is None:
        entries.append(Entry(NOMINAL_HALF_IPD, (
            f"{subject!r} has no settings file, so the stereoscope is built for the optics "
            f"drawing's nominal half-IPD, {half_ipd_cm:g} cm, which is not a measurement (STE-20): "
            f"disparities and the vergence offset assume it, and the session records it as "
            f"nominal"), SESSION_KINDS))
    elif settings.subject != subject:
        entries.append(Entry(OTHER_ANIMALS_SETTINGS, (
            f"{path} holds {settings.subject!r}'s settings, and this session is {subject!r}'s: "
            f"these are {settings.subject!r}'s settings, so the stereoscope is built for "
            f"{settings.subject!r}'s half-IPD of {half_ipd_cm:g} cm"), SESSION_KINDS))
    low, high = rig.half_ipd_range_cm
    if not low <= half_ipd_cm <= high:
        entries.append(Entry(HALF_IPD_OUTSIDE, (
            f"a half-IPD of {half_ipd_cm:g} cm is outside the {low:g}-{high:g} cm this "
            f"stereoscope is drawn for (IPD {20 * low:g}-{20 * high:g} mm, the optics drawing's "
            f"table): its mirrors and its field are extrapolated there, not drawn, so positions "
            f"and the off-screen check rest on an unmodeled field"), SESSION_KINDS))
    return entries


def of_ignored_settings(path) -> list[Entry]:
    """`--subject-settings` given with direct view, which reads nothing from it: a warning that
    the session ignores it (the PI, 2026-10-11, XC-352's H4; refused until then)."""
    return [Entry(SETTINGS_NOT_READ, (
        f"--subject-settings {path} holds the stereoscope's half-IPD, and direct view reads "
        f"nothing from it, so this session ignores it"), SESSION_KINDS)]


def of_unknowns(items: Iterable) -> list[Entry]:
```

- [ ] **Step 4: Run them and see them pass**

Run the six files, then the whole suite. Expected: `807 passed`; the suite **3512 passed**.

- [ ] **Step 5: Prove they can fail**

Over the six files:
- `Rig.stereoscope`'s `if not path > 0:` → `if not 1.5 <= half_ipd_cm <= 1.9:`: `test_the_stereoscope_builds_any_half_ipd_its_optics_extend_to` and the service's "outside the drawn optics" case fail.
- `of_setup`'s `if settings is None:` → `if False:`: three fail (the warnlist's, the service's "no settings file" case, `wlx run`'s).
- Its `elif settings.subject != subject:` → `elif False:`: three fail.
- Its `if not low <= half_ipd_cm <= high:` → `if False:`: three fail.
- `_preflight`'s `+ list(session.spec.setup_warnings)` removed: the service's three cases fail.
- `_fixed_config`'s `else not self.spec.subject_settings),` → `else False),`: the service's "no settings file" case and `wlx run`'s nominal test fail.
- `wlx run`'s `+ setup` removed: its three tests fail.
- `wlx check`'s `) + setup` → `)`: `test_wlx_check_warns_of_settings_that_a_direct_view_check_ignores` fails.
- `wlx run`'s `or args.view == "direct"` removed: `test_wlx_run_warns_of_subject_settings_in_direct_view_and_records_none` fails.
- `_build`'s `geometry = self.rig.stereoscope(half)` → `geometry = self.rig.stereoscope(NOMINAL_HALF_IPD_CM)` (the review's I7: a stereoscope built at 1.6 cm whatever the settings say): the service's "another animal's" and "outside the drawn optics" cases fail, on `config.json`'s `half_ipd_cm`.

- [ ] **Step 6: Commit**

```bash
git add wl_xcon/ tasks/reference_subject.py tests/
git commit -m "Run the stereoscope on the nominal half-IPD, another animal's settings or an undrawn half-IPD, and ignore direct view's settings, each with a warning"
```
Body: XC-352's C6 ("a warning; the nominal 1.6 cm is recorded as nominal"), C7 ("a warning"), C8 and H4 (the PI, 2026-10-11); calls 7 and 8; `Service._open`'s code unchanged (the warnings are the run's), and what it refuses through `_build` narrows (Appendix A, item 4; the review's I3); the half-IPD assertion per case (I7); the count; the breaks seen failing.

---

### Task 8: A damaged `warnings.jsonl` row is left out of a resume, and a resume on another calibration is a warning (XC-352's C11; the review's I1 and I2)

`resume.read` leaves a row that is not what `SessionRecord.warning` writes (half a line, a field missing or of the wrong kind, a warning `Entry` refuses) out of what the session accepted, instead of making the whole record unresumable: its warning is asked again at the next run, the safe direction, and `Session.resume` says why on the changes feed and in its `session resumed` row. A `warnings.jsonl` that cannot be read at all is still unresumable. **The next warning accepted is written on a line of its own** (`SessionRecord.warning` ends a torn last line first; the review's I1), so a second resume carries it. **A session resumed by a service running another calibration than its `config.json` names** -- under E1 (Task 6), the default in the place of a record that stopped loading while `wlx taskd` was down -- **is a warning, never a refusal** (the controller's ruling on the review's I2, by the PI's rule): `Service._resume`, which is not welfare-listed, adds `calibration changed`, naming both, to the session's `setup_warnings`, which its first run's pre-flight asks to accept; the `session resumed` row names the calibration the session now runs on, and `config.json` keeps the one it opened on. `link.Control`'s docstring names the `warning` kind (the review's M5).

**Files:**
- Modify: `wl_xcon/resume.py` (`Restoration.damaged`, `Restoration.calibration`; new `_Damaged`; `_accepted`; new `_warnings`; `_read`), `wl_xcon/taskd.py` (`SessionSpec.setup_warnings`' comment; `Session.resume`), `wl_xcon/record.py` (`SessionRecord.warning`), `wl_xcon/service.py` (`Service._resume`), `wl_xcon/warnlist.py` (docstring; `CALIBRATION_CHANGED`; new `of_changed_calibration`), `wl_xcon/link.py` (`Control`'s docstring)
- Modify (test): `tests/test_resume.py`, `tests/test_stranded.py`, `tests/test_service.py`
- Modify (docs): `docs/design/architecture.md` (the resume paragraph)

**Interfaces:**
- Produces: `resume.Restoration.damaged: tuple = ()` (sentences, each "its warnings.jsonl row N …, so it is not carried and its warning is asked again"); `resume.Restoration.calibration: str | None = None` (the id `config.json` names); `resume._warnings(directory, session_kind) -> tuple[tuple, tuple]`; `warnlist.CALIBRATION_CHANGED = "calibration changed"`; `warnlist.of_changed_calibration(opened_on, now) -> list[Entry]`; the control kind `warning` on the changes feed.

- [ ] **Step 1: Write the failing tests**

**`tests/test_resume.py`** (5 replacements, in order):

Replace:

```python

def test_a_damaged_accepted_warning_row_makes_a_record_unresumable(tmp_path):
    directory = _folder(tmp_path)
    _jsonl(directory / "warnings.jsonl", [{"code": "head free"}])

    with pytest.raises(Unresumable, match="KeyError"):
        read(directory, DEPARTURE)
```

with:

```python

def test_a_damaged_accepted_warning_row_is_not_carried_and_the_record_is_resumed(tmp_path):
    """XC-352's C11 (the PI, 2026-10-11): one damaged row no longer makes a record unresumable;
    it is left out, and its warning is asked again (the safe direction), saying so."""
    directory = _folder(tmp_path)
    _jsonl(directory / "warnings.jsonl", [{"code": "head free"}, _accepted_row()])

    restored = read(directory, DEPARTURE)

    assert [w[0] for w in restored.accepted] == ["head free"] and len(restored.accepted) == 1
    assert restored.damaged == (
        "its warnings.jsonl row 1 has no 'detail', so it is not carried and its warning is "
        "asked again",)
```

Replace:

```python
         "by-extra-field", "code-with-a-count", "code-with-a-comma", "code-empty", "kind-twice"])
def test_a_damaged_accepted_warning_row_is_refused_naming_its_field_never_coerced(
```

with:

```python
         "by-extra-field", "code-with-a-count", "code-with-a-comma", "code-empty", "kind-twice"])
def test_a_damaged_accepted_warning_row_is_left_out_naming_its_field_never_coerced(
```

Replace:

```python
    """The engine B plan, call 12: a `warnings.jsonl` row that is not what
    `SessionRecord.warning` writes makes the record unresumable through `read`, so
    `stranded.find` marks it so, rather than a resume `Session.resume` would then refuse or a
    value coerced into something nobody accepted. The second row, after one that is whole."""
```

with:

```python
    """The engine B plan, call 12: a `warnings.jsonl` row that is not what
    `SessionRecord.warning` writes is never coerced into something nobody accepted. **It is left
    out, and the record resumed** (the PI, 2026-10-11, XC-352's C11; it made the record
    unresumable until then): its warning is asked again, and why is said. The second row, after
    one that is whole."""
```

Replace:

```python
           [_accepted_row(), _accepted_row(**{"code": "other", **damage})])

    with pytest.raises(Unresumable) as refused:
        read(directory, DEPARTURE)

    assert str(refused.value).startswith(f"its warnings.jsonl row 2 {named}")
    assert str(refused.value).endswith("; end it instead")
```

with:

```python
           [_accepted_row(), _accepted_row(**{"code": "other", **damage})])

    restored = read(directory, DEPARTURE)

    assert [w[0] for w in restored.accepted] == ["head free"]
    (why,) = restored.damaged
    assert why.startswith(f"its warnings.jsonl row 2 {named}")
    assert why.endswith(", so it is not carried and its warning is asked again")


def test_a_torn_accepted_warning_row_is_left_out_and_the_rows_before_it_carried(tmp_path):
    """XC-352's C11: half a line, a process that died writing it, is one damaged row."""
    directory = _folder(tmp_path)
    whole = json.dumps(_accepted_row()) + "\n" + json.dumps(_accepted_row(code="other"))
    (directory / "warnings.jsonl").write_text(whole[: -len(whole) // 4])

    restored = read(directory, DEPARTURE)

    assert [w[0] for w in restored.accepted] == ["head free"]
    (why,) = restored.damaged
    assert why.startswith("its warnings.jsonl row 2 is not JSON (")
```

Replace:

```python

    with pytest.raises(Unresumable) as refused:
        read(directory, DEPARTURE)

    said = str(refused.value)
    assert _quoted(value) in said and "k" * (TEXT_LIMIT + 1) not in said
    assert said.endswith("; end it instead") and len(said) < 2 * TEXT_LIMIT + 200
```

with:

```python

    if where == "row-kind":
        # A damaged row is left out since XC-352's C11, and why is said as cut.
        (said,) = read(directory, DEPARTURE).damaged
        assert said.endswith("asked again")
    else:
        with pytest.raises(Unresumable) as refused:
            read(directory, DEPARTURE)
        said = str(refused.value)
        assert said.endswith("; end it instead")
    assert _quoted(value) in said and "k" * (TEXT_LIMIT + 1) not in said
    assert len(said) < 2 * TEXT_LIMIT + 200
```

**`tests/test_service.py`** (3 replacements, in order):

Replace:

```python

def test_a_torn_warnings_file_is_not_resumable_and_its_return_is_still_taken(tmp_path):
    """The whole path, not the piece: a process that died writing an accepted warning leaves
    half a line; `wlx taskd` starts again, `stranded.find` marks the session not resumable
    with `resume.read`'s sentence, a resume is refused with it, and End session takes the
    animal's return."""
    folders = _folders(tmp_path)
    first = _made(folders)
    _step(first, _open())
    first.session.accept([Entry("head free", "the head is free", SESSION_KINDS)],
                         by=BY, how="open", run=None)
    path = folders[2] / "2027-01-14_01" / "xcon" / "warnings.jsonl"
```

with:

```python

def test_a_torn_warnings_file_is_resumed_and_its_lost_warning_asked_again(tmp_path):
    """XC-352's C11 (the PI, 2026-10-11), the whole path: a process that died writing an accepted
    warning leaves half a line. `wlx taskd` starts again, the session is resumable, the resume
    leaves the torn row out, saying so on the feed and in its `session resumed` row, and the next
    run's pre-flight asks for that warning again. Until then the session could only be ended."""
    folders = _folders(tmp_path)
    first = _made(folders)
    _step(first, _open())
    path = folders[2] / "2027-01-14_01" / "xcon" / "warnings.jsonl"
```

Replace:

```python
    (found,) = _step(second).stranded
    assert (found.session_id, found.resumable) == ("2027-01-14_01", False)
    assert found.left_at is not None, "its departure is read, so its return can be taken"
    assert found.why.startswith("its warnings.jsonl cannot be read (")
    assert _resume_refused(second, "2027-01-14_01") == found.why
    frame = _step(second, _end(session_id="2027-01-14_01"))

    assert isinstance(frame, Idle) and second.stranded == []
    assert _kinds(folders[2])[-1] == "returned"


def test_an_accepted_warning_whose_code_an_entry_refuses_is_not_resumable_and_its_return_is_taken(
    tmp_path,
):
    """The engine B final review, the whole path: a `warnings.jsonl` row whose code holds "×",
    which `Entry` refuses and `Session.resume` would have raised on after restoring the
    departure. `wlx taskd` starts again, `stranded.find` marks the session not resumable with
    `resume.read`'s sentence naming the row, a resume is refused with it, and End session takes
    the animal's return."""
```

with:

```python
    (found,) = _step(second).stranded
    resumed = _step(second, ResumeSession(by=BY, session_id="2027-01-14_01"))
    checked = _step(second, CheckRun(by=BY, task=TASK, values=dict(VALUES)))

    assert found.resumable and resumed.phase == "between_runs"
    said = [c.said for c in resumed.controls if c.kind == "warning"]
    assert said and said[0].startswith("its warnings.jsonl row 1 is not JSON (")
    (row,) = [r for r in _rows(folders[2]) if r["kind"] == "session resumed"]
    assert "row 1 is not JSON" in row["reason"]
    item = {i.name: i for i in checked.preflight.items}["warnings"]
    assert item.result == "unknown" and "default calibration" in item.said


def test_an_accepted_warning_whose_code_an_entry_refuses_is_left_out_of_a_resume(tmp_path):
    """The engine B final review's case, since XC-352's C11: a `warnings.jsonl` row whose code
    holds "×", which `Entry` refuses and `Session.resume` would have raised on after restoring
    the departure. The session resumes, without that row, naming it on its feed."""
```

Replace:

```python

    (found,) = _step(second).stranded
    assert (found.session_id, found.resumable) == ("2027-01-14_01", False)
    assert found.why.startswith(
        f"its warnings.jsonl row {len(rows)} is not a warning as the rig lists one (a warning's "
        f"code never holds '×'"
    )
    assert _resume_refused(second, "2027-01-14_01") == found.why
    frame = _step(second, _end(session_id="2027-01-14_01"))

    assert isinstance(frame, Idle) and second.stranded == []
    assert _kinds(folders[2])[-1] == "returned"
```

with:

```python

    resumed = _step(second, ResumeSession(by=BY, session_id="2027-01-14_01"))

    assert resumed.phase == "between_runs"
    assert [w[0] for w in second.session.warnings] == [r["code"] for r in rows[:-1]]
    assert any(c.kind == "warning" and c.said.startswith(
        f"its warnings.jsonl row {len(rows)} is not a warning as the rig lists one (a warning's "
        f"code never holds '×'") for c in resumed.controls)


def test_a_warning_accepted_after_a_torn_row_is_on_a_line_of_its_own_and_resumed_again(tmp_path):
    """The warnings-over-refusals review's I1, the whole path: a torn row is left out of a resume,
    its warning is accepted again as the next run starts -- on a line of its own, not glued to
    the fragment -- and a second resume carries that acceptance, leaving out the torn row alone."""
    folders = _folders(tmp_path)
    first = _made(folders)
    _step(first, _open())
    path = folders[2] / "2027-01-14_01" / "xcon" / "warnings.jsonl"
    whole = path.read_text()
    path.write_text(whole[: len(whole) // 2])
    second = _made(folders)
    _step(second, ResumeSession(by=BY, session_id="2027-01-14_01"))
    assert _step(second, _start()).run_index == 0
    _run_to_its_end(second)
    third = _made(folders)

    resumed = _step(third, ResumeSession(by=BY, session_id="2027-01-14_01"))

    assert resumed.phase == "between_runs"
    assert "default calibration" in [w[0] for w in third.session.warnings]
    said = [c.said for c in resumed.controls if c.kind == "warning"]
    assert len(said) == 1 and said[0].startswith("its warnings.jsonl row 1 is not JSON (")


def test_a_session_resumed_on_another_calibration_asks_its_first_run_to_accept_that(tmp_path):
    """The warnings-over-refusals review's I2: a session opened on a measured record that stops
    loading while `wlx taskd` is down, so the service starts again on the default in its place
    (XC-352's E1). The resume is not refused (the PI's rule of 2026-10-11): its `session resumed`
    row names the calibration it now runs on, config.json keeps the one it opened on, and its
    first run's pre-flight asks to accept the change, naming both, which the start records."""
    today = date.fromtimestamp(WALL).isoformat()
    panel = measured(measured_on=today, id=f"rig1@{today}")
    record = tmp_path / "cal.json"
    record.write_text(json.dumps({
        "id": panel.id, "measured_on": panel.measured_on, "observer": OBSERVER,
        "primaries": PRIMARIES, "background": BACKGROUND,
        "transfer": {c: [list(p) for p in zip(LINEAR.levels, LINEAR.fractions)]
                     for c in ("red", "green", "blue")},
        "spectra": {name: list(getattr(SPECTRA, name)) for name in ("nm", "red", "green", "blue")},
    }))
    rig = dataclasses.replace(RIG, calibration=str(record))
    folders = _folders(tmp_path)
    first = _made(folders, rig=rig)
    _step(first, _open())
    record.write_text("{")
    second = _made(folders, rig=rig)

    _step(second, ResumeSession(by=BY, session_id="2027-01-14_01"))
    checked = _step(second, CheckRun(by=BY, task=TASK, values=dict(VALUES)))
    started = _step(second, _start())

    assert first.calibration == panel and second.calibration is SRGB
    (row,) = [r for r in _rows(folders[2]) if r["kind"] == "session resumed"]
    assert "; it runs on calibration srgb-standard" in row["reason"]
    folder = folders[2] / "2027-01-14_01" / "xcon"
    assert json.loads((folder / "config.json").read_text())["calibration"]["id"] == panel.id
    item = {i.name: i for i in checked.preflight.items}["warnings"]
    assert (f"calibration changed: this session opened on calibration {panel.id}, which its "
            f"config.json names, and is resumed on calibration srgb-standard") in item.said
    assert started.run_index == 0
    assert [r["how"] for r in _jsonl(folder / "warnings.jsonl")
            if r["code"] == "calibration changed"] == ["start"]
```

**`tests/test_stranded.py`** (4 replacements, in order):

Replace:

```python

@pytest.mark.parametrize("where", ["config.json", "trials.jsonl", "a number", "a warning", "an actor"])
```

with:

```python

@pytest.mark.parametrize("where", ["config.json", "trials.jsonl", "a number"])
```

Replace:

```python
        start = "its record cannot be read (ValueError: could not convert string to float: "
    elif where == "a warning":
        (directory / "warnings.jsonl").write_text(json.dumps(_ACCEPTED) + "\n")

        def refused(*_fields):
```

with:

```python
        start = "its record cannot be read (ValueError: could not convert string to float: "

    (found,) = stranded.find(tmp_path)

    assert (found.left_at, found.resumable) == (WALL - 900, False)
    assert found.why.startswith(start) and found.why.endswith("; end it instead")
    assert long not in found.why and "…" in found.why


@pytest.mark.parametrize("where", ["a warning", "an actor"])
def test_a_damaged_warning_rows_long_sentence_is_cut_and_the_session_stays_resumable(
    tmp_path, monkeypatch, where
):
    """XC-299's cut, for a damaged `warnings.jsonl` row, which leaves the session resumable since
    XC-352's C11 (the PI, 2026-10-11): why it is not carried quotes what its reader said cut."""
    long = "e" * 10_000
    directory = _notes(tmp_path, "2027-01-13_01", ("departure", WALL - 900))
    _config(directory)
    (directory / "warnings.jsonl").write_text(json.dumps(_ACCEPTED) + "\n")
    if where == "a warning":
        def refused(*_fields):
```

Replace:

```python
        start = "its warnings.jsonl row 1 is not a warning as the rig lists one ("
    elif where == "an actor":
        (directory / "warnings.jsonl").write_text(json.dumps(_ACCEPTED) + "\n")

```

with:

```python
        start = "its warnings.jsonl row 1 is not a warning as the rig lists one ("
    else:
```

Replace:

```python
        start = "its warnings.jsonl row 1 has a by that is not an actor's map or null ("

    (found,) = stranded.find(tmp_path)

    assert (found.left_at, found.resumable) == (WALL - 900, False)
    assert found.why.startswith(start) and found.why.endswith("; end it instead")
    assert long not in found.why and "…" in found.why
```

with:

```python
        start = "its warnings.jsonl row 1 has a by that is not an actor's map or null ("

    (found,) = stranded.find(tmp_path)
    (why,) = resume.read(directory, WALL - 900).damaged

    assert found.resumable
    assert why.startswith(start) and long not in why and "…" in why
```

- [ ] **Step 2: Run them and see them fail**

Run: `$PY -m pytest -q -p no:cacheprovider tests/test_resume.py tests/test_service.py tests/test_stranded.py`
Expected: `26 failed, 295 passed`: `resume.read` raising `Unresumable` on each damaged row; `Restoration` with no `damaged`; the two service resumes refused; `test_a_warning_accepted_after_a_torn_row_is_on_a_line_of_its_own_and_resumed_again` (the torn session not resumable) and `test_a_session_resumed_on_another_calibration_asks_its_first_run_to_accept_that` (no `calibration changed` asked).

- [ ] **Step 3: Implement**

**`wl_xcon/resume.py`** (6 replacements, in order):

Replace:

```python

def _cut(error: Exception) -> str:
```

with:

```python

class _Damaged(Exception):
    """A `warnings.jsonl` row that is not what `SessionRecord.warning` writes: left out of a
    resume, its message saying why (XC-352's C11)."""


def _cut(error: Exception) -> str:
```

Replace:

```python
    accepted: tuple

```

with:

```python
    accepted: tuple
    #: Why each damaged `warnings.jsonl` row was left out of `accepted` (the PI, 2026-10-11,
    #: XC-352's C11): its warning is asked again, and `Session.resume` says so.
    damaged: tuple = ()
    #: The id of the calibration `config.json` names, the one the session opened on, or `None`
    #: for none: `Service._resume` warns when the service now runs another (the
    #: warnings-over-refusals review's I2).
    calibration: str | None = None

```

Replace:

```python
    """Row `number` of `ACCEPTED_WARNINGS`, as `SessionRecord.warning` writes it, read back as
    `Session.warnings` gives it -- or `Unresumable`, naming the field that is not what that
    method writes (the engine B plan, call 12). **Nothing is coerced**, as `Service._resume`
    says of the rest of the record: a damaged row is not what anyone accepted, so
    `stranded.find` marks the session not resumable rather than restoring a guess. A field
    the row lacks is a `KeyError`, which `read` names."""

    def damaged(what: str) -> Unresumable:
        return Unresumable(
            f"its {ACCEPTED_WARNINGS} row {number} {what}, so what the session accepted "
            f"cannot be known; end it instead"
        )

    code, detail, kinds, by, at = (
```

with:

```python
    """Row `number` of `ACCEPTED_WARNINGS`, as `SessionRecord.warning` writes it, read back as
    `Session.warnings` gives it -- or `_Damaged`, naming the field that is not what that method
    writes (the engine B plan, call 12). **Nothing is coerced**, as `Service._resume` says of
    the rest of the record: a damaged row is not what anyone accepted, so it is left out and
    its warning asked again (`_warnings`; XC-352's C11), never restored as a guess."""

    def damaged(what: str) -> _Damaged:
        return _Damaged(f"its {ACCEPTED_WARNINGS} row {number} {what}")

    if not isinstance(row, dict):
        raise damaged("is not a row")
    missing = [name for name in ("code", "detail", "accepted_in", "session_kind", "by", "at")
               if name not in row]
    if missing:
        raise damaged(f"has no {missing[0]!r}")
    code, detail, kinds, by, at = (
```

Replace:

```python
    return (code, detail, tuple(kinds), accepted_by, float(at))

```

with:

```python
    return (code, detail, tuple(kinds), accepted_by, float(at))


def _warnings(directory: Path, session_kind: str) -> tuple[tuple, tuple]:
    """What the session accepted (`ACCEPTED_WARNINGS`), each row as `Session.warnings` gives it,
    and why each damaged row was left out: **a damaged row never makes the record unresumable**
    (the PI, 2026-10-11, XC-352's C11; it did until then) -- its warning is not carried, so it is
    asked again, the safe direction. A row is numbered among the file's non-blank lines; half a
    line, from a process that died writing it, is one that is not JSON. A file that cannot be
    read at all is still `Unresumable`."""
    path = directory / ACCEPTED_WARNINGS
    if not path.exists():
        return (), ()
    try:
        lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    except (OSError, ValueError) as error:
        raise Unresumable(
            f"its {ACCEPTED_WARNINGS} cannot be read ({_cut(error)}); end it instead") from error
    accepted, damaged = [], []
    for number, line in enumerate(lines, start=1):
        try:
            try:
                row = json.loads(line)
            except ValueError as error:
                raise _Damaged(
                    f"its {ACCEPTED_WARNINGS} row {number} is not JSON ({_cut(error)})") from error
            accepted.append(_accepted(row, number, session_kind))
        except _Damaged as why:
            damaged.append(f"{why}, so it is not carried and its warning is asked again")
    return tuple(accepted), tuple(damaged)

```

Replace:

```python
        stop_kind = "operator"
    accepted = tuple(
        _accepted(row, number, session_kind)
        for number, row in enumerate(_rows(directory, ACCEPTED_WARNINGS), start=1)
    )
```

with:

```python
        stop_kind = "operator"
    accepted, damaged = _warnings(directory, session_kind)
```

Replace:

```python
        accepted=accepted,
    )
```

with:

```python
        accepted=accepted,
        damaged=damaged,
        calibration=(config["calibration"].get("id")
                     if isinstance(config.get("calibration"), dict) else None),
    )
```

**`wl_xcon/taskd.py`** (3 replacements, in order):

Replace:

```python
    #: The warnings a stereoscope's setup was built with (the PI, 2026-10-11, XC-352's C6, C7
    #: and C8; `warnlist.of_setup`): the nominal half-IPD for an animal with no settings file,
    #: another animal's settings, a half-IPD outside the drawn optics. A `wlx taskd` run's
    #: pre-flight lists them (`Service._preflight`), accepted once a session.
```

with:

```python
    #: The warnings a stereoscope's setup was built with (the PI, 2026-10-11, XC-352's C6, C7
    #: and C8; `warnlist.of_setup`): the nominal half-IPD for an animal with no settings file,
    #: another animal's settings, a half-IPD outside the drawn optics; and a resumed session's
    #: calibration, when it is not the one it opened on (`Service._resume`; the
    #: warnings-over-refusals review's I2). A `wlx taskd` run's pre-flight lists them
    #: (`Service._preflight`), accepted once a session.
```

Replace:

```python
        before its process stopped, so no run starts again, and its head, released then by
        `end_runs`, is not marked fixed again. Its return closes it as any other's does."""
```

with:

```python
        before its process stopped, so no run starts again, and its head, released then by
        `end_runs`, is not marked fixed again. Its return closes it as any other's does.

        **A damaged `warnings.jsonl` row is left out** (`resume.read`; the PI, 2026-10-11,
        XC-352's C11): its warning is asked again, and why is said on the changes feed, as a
        `warning`, and in the `session resumed` row, which also names the calibration the
        session now runs on (the warnings-over-refusals review's I2)."""
```

Replace:

```python
        self.opened_wall_at = self.resumed_at = now
        self._note(
            "session resumed", now, by, how,
            reason=f"after its process stopped; its record was last written at "
                   f"{_local(restoration.last_written_at)}",
        )
        self._record = SessionRecord.open(
```

with:

```python
        self.opened_wall_at = self.resumed_at = now
        # The calibration it now runs on (the warnings-over-refusals review's I2): config.json
        # keeps the one it opened on.
        on = "none" if self.spec.calibration is None else self.spec.calibration.id
        self._note(
            "session resumed", now, by, how,
            reason=f"after its process stopped; its record was last written at "
                   f"{_local(restoration.last_written_at)}; it runs on calibration {on}"
                   + "".join(f"; {why}" for why in restoration.damaged),
        )
        for why in restoration.damaged:
            self._feed("warning", by, now, why)
        self._record = SessionRecord.open(
```

**`wl_xcon/record.py`**:

Replace:

```python
        """One accepted warning, as `taskd.Session.accept` gives it."""
        with (self.directory / ACCEPTED_WARNINGS).open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({
```

with:

```python
        """One accepted warning, as `taskd.Session.accept` gives it, **on a line of its own**: a
        last row a process died writing -- half a line, which a resume leaves out (XC-352's C11)
        -- is ended first, so this row is never glued to it and lost with it (the
        warnings-over-refusals review's I1)."""
        path = self.directory / ACCEPTED_WARNINGS
        torn = path.exists() and path.read_bytes()[-1:] not in (b"", b"\n")
        with path.open("a", encoding="utf-8") as handle:
            handle.write(("\n" if torn else "") + json.dumps({
```

**`wl_xcon/service.py`**:

Replace:

```python
        try:
            session.resume(restoration, by=command.by, how="wlx taskd")
```

with:

```python
        # **On another calibration than it opened on** (the warnings-over-refusals review's I2):
        # config.json names the one the session opened with, and this service may run another --
        # the default in the place of a record that no longer loads (XC-352's E1), or a new
        # record. A warning, never a refusal (the PI's rule of 2026-10-11), asked with the
        # resumed session's first run, naming both; each run's start row names the calibration
        # it ran against, and the `session resumed` row the one it now runs on.
        if restoration.calibration != session.spec.calibration.id:
            session.spec.setup_warnings += tuple(warnlist.of_changed_calibration(
                restoration.calibration, session.spec.calibration))
        try:
            session.resume(restoration, by=command.by, how="wlx taskd")
```

**`wl_xcon/warnlist.py`** (3 replacements, in order):

Replace:

```python
accepted them, and every run's pre-flight failed on them, until then); a chaired session's free
head (§5.9); a stereoscope's setup -- the nominal half-IPD, another animal's settings, a
```

with:

```python
accepted them, and every run's pre-flight failed on them, until then); a resumed session's
calibration, when it is not the one the session opened on (the warnings-over-refusals review's
I2); a chaired session's free head (§5.9); a stereoscope's setup -- the nominal half-IPD,
another animal's settings, a
```

Replace:

```python
CALIBRATION_RECORD = "calibration record"
HEAD_FREE = "head free"
```

with:

```python
CALIBRATION_RECORD = "calibration record"
CALIBRATION_CHANGED = "calibration changed"
HEAD_FREE = "head free"
```

Replace:

```python
    return [Entry(CALIBRATION_RECORD, refusal + tail, SESSION_KINDS)]
```

with:

```python
    return [Entry(CALIBRATION_RECORD, refusal + tail, SESSION_KINDS)]


def of_changed_calibration(opened_on: str | None, now: Calibration) -> list[Entry]:
    """A stranded session resumed by a service that runs `now`, not the calibration it opened on,
    whose id its `config.json` names (`opened_on`, `None` for none): **a warning in every kind,
    never a refusal** (the warnings-over-refusals review's I2; the PI's rule of 2026-10-11), asked
    with the resumed session's first run, naming both. The record stays interpretable: each run's
    start row names the calibration it ran against."""
    was = "no calibration" if opened_on is None else f"calibration {opened_on}"
    standard = ", the sRGB standard, measured by nobody," if now.standard else ""
    return [Entry(CALIBRATION_CHANGED, (
        f"this session opened on {was}, which its config.json names, and is resumed on calibration "
        f"{now.id}{standard} which this wlx taskd runs on: its runs from here are checked and "
        f"drawn against {now.id}, and each run's start row in runs.jsonl names the calibration it "
        f"ran against"), SESSION_KINDS)]
```

**`wl_xcon/link.py`**:

Replace:

```python
    `note`, `schedule`, `cancel`, `scheduled_stop`, `set` (a staged setting applied) or
    `reward` (a manual reward, given while paused);
```

with:

```python
    `note`, `schedule`, `cancel`, `scheduled_stop`, `set` (a staged setting applied),
    `reward` (a manual reward, given while paused) or `warning` (a warning said as it
    happens, since the PI's rulings on XC-352, 2026-10-11);
```

The doc it invalidates:

**`docs/design/architecture.md`**:

Replace:

```markdown
or before engine build B, so what the session is for is unknown; unreadable; a start row without
its run numbers; a `config.json` naming another session than its folder, or a session kind other
than training, piloting or recording; or a damaged `warnings.jsonl` row: a field missing, a code
or detail that is not text, an `accepted_in` that is not a list of those kinds, a warning
`warnlist.Entry` refuses (an empty code, a code holding ",", "(", ")" or "×", or a kind named
twice), a `session_kind` other than `config.json`'s, an `at` that is not a finite number, or a
`by` that is neither an actor's map nor null) or names two animals;
```

with:

```markdown
or before engine build B, so what the session is for is unknown; unreadable; a start row without
its run numbers; or a `config.json` naming another session than its folder, or a session kind
other than training, piloting or recording) or names two animals. **A damaged `warnings.jsonl`
row is left out, never a refusal** (the PI, 2026-10-11, XC-352's C11): a field missing, a code
or detail that is not text, an `accepted_in` that is not a list of those kinds, a warning
`warnlist.Entry` refuses (an empty code, a code holding ",", "(", ")" or "×", or a kind named
twice), a `session_kind` other than `config.json`'s, an `at` that is not a finite number, a
`by` that is neither an actor's map nor null, or half a line; its warning is asked again, and
the resume says so on the changes feed and in its `session resumed` row, which names the
calibration the session now runs on; one resumed on another calibration than its `config.json`
names is a warning its first run asks to accept, naming both (the warnings-over-refusals
review's I2), never a refusal.
It is refused, too,
```

- [ ] **Step 4: Run them and see them pass**

Run the three files, then the whole suite. Expected: `321 passed`; the suite **3515 passed**.

- [ ] **Step 5: Prove they can fail**

- `_warnings`' `damaged.append(…)` → `raise Unresumable(str(why)) from why`: twenty-five fail.
- `_read`'s `damaged=damaged,` → `damaged=(),`: twenty-five fail.
- `Session.resume`'s `for why in restoration.damaged: self._feed(…)` removed: the three service tests of a damaged row fail.
- Its note's `+ "".join(f"; {why}" …)` removed: `test_a_torn_warnings_file_is_resumed_and_its_lost_warning_asked_again` fails.
- `_accepted`'s `if missing: raise damaged(…)` removed: `test_a_damaged_accepted_warning_row_is_not_carried_and_the_record_is_resumed` fails (the `KeyError` read as an unreadable record).
- `SessionRecord.warning`'s `torn = …` → `torn = False` (the review's I1): `test_a_warning_accepted_after_a_torn_row_is_on_a_line_of_its_own_and_resumed_again` fails ("default calibration" not carried by the second resume).
- `Service._resume`'s `if restoration.calibration != session.spec.calibration.id:` → `if False:`; or `_read`'s `calibration=(…)` → `calibration=None,`; or `Session.resume`'s reason without `; it runs on calibration {on}` (the review's I2): each fails `test_a_session_resumed_on_another_calibration_asks_its_first_run_to_accept_that`.

- [ ] **Step 6: Commit**

```bash
git add wl_xcon/ tests/ docs/design/architecture.md
git commit -m "Leave a damaged warnings.jsonl row out of a resume, and warn of a resume on another calibration"
```
Body: XC-352's C11 (the PI, 2026-10-11, approving the audit's proposal); C10 kept (an unreadable file); call 11, with the next warning written on a line of its own (the review's I1); call 18, a resume on another calibration a warning, never a refusal (the review's I2, as the controller ruled); `link.Control`'s `warning` kind (M5); `Service._resume`, `Session.resume`, `resume.py` and `SessionRecord.warning` off the welfare list (the PI, 2026-10-02, for the first three), the restored departure, fluid and limits untouched; the count; the breaks seen failing.

---

### Task 9: A pause the allocation cannot mark is taken, with a warning (XC-352's D5)

An allocation without PAUSE or RESUME codes no longer refuses a pause: the session holds, PAUSE and RESUME are strobed when the allocation has them, and a warning that the recording shows an unexplained gap is said on the changes feed and accepted into `warnings.jsonl` by who paused, once a session. `_hold`, which asks the out-of-cage limit on every pass, is unchanged.

**Files:**
- Modify: `wl_xcon/taskd.py` (imports; `_pause`, `_resume`), `wl_xcon/warnlist.py` (`PAUSE_UNMARKED`; docstring)
- Modify (test): `tests/test_taskd.py`

**Interfaces:**
- Produces: `warnlist.PAUSE_UNMARKED = "pause unmarked"`; `Session._pause` accepting `Entry(PAUSE_UNMARKED, …, SESSION_KINDS)` with `how="pause"`.

- [ ] **Step 1: Write the failing test**

**`tests/test_taskd.py`** (2 replacements, in order):

Replace:

```python

def test_a_pause_is_refused_when_the_allocation_cannot_mark_it(tmp_path):
    """A pause the recording cannot show is refused rather than taken silently: the
    allocation must carry both `PAUSE` and `RESUME`, so the gap has two ends."""
    from dataclasses import replace

    link = _Scripted()
```

with:

```python

def test_a_pause_the_allocation_cannot_mark_holds_with_a_warning_never_a_refusal(tmp_path):
    """XC-352's D5 (the PI, 2026-10-11): a pause the recording cannot show both ends of is taken,
    with a warning, never refused: the allocation has no `RESUME`, so the gap's end is unmarked.
    `PAUSE` is strobed, `RESUME` is not, the pause and its resume are in `controls.jsonl`, and the
    warning is on the changes feed and in `warnings.jsonl`, accepted by who paused."""
    from dataclasses import replace

    link = _Scripted(script={2: [Resume(by=Box("sam"))]})
```

Replace:

```python

    assert session.stop_kind == "completed"
    ((name, _, why),) = session.refusals
    assert name == "pause"
    assert "no RESUME event code" in why
    assert link.waits == []
```

with:

```python

    assert session.stop_kind == "completed" and session.refusals == []
    assert len(link.waits) == 2, "it held"
    assert PAUSE_CODE in session.card.codes and RESUME_CODE not in session.card.codes
    assert [row["kind"] for row in _controls_rows(session)] == ["pause", "resume"]
    (warned,) = [c for c in session.controls if c[0] == "warning"]
    assert "no RESUME event code" in warned[3] and "unexplained gap" in warned[3]
    rows = [json.loads(line) for line in (session.directory / "warnings.jsonl").read_text().splitlines()]
    assert [(r["code"], r["how"], r["by"]["name"]) for r in rows] == [("pause unmarked", "pause", "jake")]
```

- [ ] **Step 2: Run it and see it fail**

Run: `$PY -m pytest -q -p no:cacheprovider tests/test_taskd.py`
Expected: `1 failed, 250 passed`: the pause refused ("no RESUME event code … it is refused").

- [ ] **Step 3: Implement**

**`wl_xcon/taskd.py`** (5 replacements, in order):

Replace:

```python
)
from wl_xcon.findings import kind_named
```

with:

```python
)
from wl_xcon.findings import SESSION_KINDS, kind_named
```

Replace:

```python
from wl_xcon.task import Entered, Exited, Outcome, Param, SaccadeTo, Task, Trial
from wl_xcon.warnlist import Entry, sentence
```

with:

```python
from wl_xcon.task import Entered, Exited, Outcome, Param, SaccadeTo, Task, Trial
from wl_xcon.warnlist import PAUSE_UNMARKED, Entry, sentence
```

Replace:

```python
        **Refused, with the sentence, when it would not hold a session that can
        resume and be seen to**: a session already stopping -- a `Stop` drained
        ahead of this in the same pass (Review Focus 3) -- one already paused (a
        double click), or an allocation without both `PAUSE` and `RESUME`, which
        would leave a gap in the recording with an end nobody could find."""
```

with:

```python
        **Refused, with the sentence, when it would not hold a session that can
        resume**: a session already stopping -- a `Stop` drained ahead of this in the
        same pass (Review Focus 3) -- or one already paused (a double click). **An
        allocation without both `PAUSE` and `RESUME` holds it with a warning, never a
        refusal** (the PI, 2026-10-11, XC-352's D5; refused until then): the recording
        shows an unexplained gap, `controls.jsonl` says when the pause began and ended,
        and the warning, on the changes feed, is accepted into `warnings.jsonl` by who
        paused, once a session."""
```

Replace:

```python
        missing = [name for name, code in codes.items() if code is None]
        if missing:
            self._refuse(
                "pause",
                by,
                f"this session's allocation has no {' or '.join(missing)} event code, "
                f"so the recording could not show the pause; it is refused",
            )
            return
        self.card.emit(codes["PAUSE"])
        self.paused_at = self._control("pause", by, f"paused at trial {index}", index)
```

with:

```python
        missing = [name for name, code in codes.items() if code is None]
        if codes["PAUSE"] is not None:
            self.card.emit(codes["PAUSE"])
        self.paused_at = self._control("pause", by, f"paused at trial {index}", index)
        if missing:
            entry = Entry(PAUSE_UNMARKED, (
                f"this session's allocation has no {' or '.join(missing)} event code, so the "
                f"recording cannot show where a pause begins and ends: each pause leaves an "
                f"unexplained gap in it, and when it began and ended are in controls.jsonl"),
                SESSION_KINDS)
            self._feed("warning", by, self.paused_at, entry.detail)
            self.accept([entry], by=by, how="pause", run=self.run_index)
```

Replace:

```python
            return
        self.card.emit(self.allocation.code_for("RESUME"))
```

with:

```python
            return
        code = self._code("RESUME")
        if code is not None:
            # Strobed when the allocation has it; otherwise the pause's warning said so (D5).
            self.card.emit(code)
```

**`wl_xcon/warnlist.py`** (2 replacements, in order):

Replace:

```python
half-IPD outside the drawn optics -- and settings direct view ignores (the PI's rulings on
XC-352, 2026-10-11, C6, C7, C8 and H4); a task's warnings, its load-time findings that
```

with:

```python
half-IPD outside the drawn optics -- and settings direct view ignores (the PI's rulings on
XC-352, 2026-10-11, C6, C7, C8 and H4); a pause the allocation cannot mark (D5), accepted as it
is taken; a task's warnings, its load-time findings that
```

Replace:

```python
SETTINGS_NOT_READ = "settings not read"
#: The code of a row saying the warnings could not be listed at all (`service.Service`'s idle
```

with:

```python
SETTINGS_NOT_READ = "settings not read"
#: A pause the allocation cannot mark (`taskd.Session._pause`; the PI, 2026-10-11, XC-352's D5).
PAUSE_UNMARKED = "pause unmarked"
#: The code of a row saying the warnings could not be listed at all (`service.Service`'s idle
```

- [ ] **Step 4: Run it and see it pass**

Run the file, then the whole suite. Expected: `251 passed`; the suite **3515 passed**.

- [ ] **Step 5: Prove it can fail**

- `_pause`'s `self.accept([entry], by=by, how="pause", run=self.run_index)` → `pass`: the test fails.
- Its `self._feed("warning", by, self.paused_at, entry.detail)` → `pass`: the test fails.
- `_resume`'s `code = self._code("RESUME")` → `code = self.allocation.code_for("RESUME")`: the test fails (the `KeyError` ends the run as a fault).
- `_pause`'s `if codes["PAUSE"] is not None:` → `if False:`: seven fail, the strobe tests among them.

- [ ] **Step 6: Commit**

```bash
git add wl_xcon/taskd.py wl_xcon/warnlist.py tests/test_taskd.py
git commit -m "Take a pause the allocation cannot mark, with a warning"
```
Body: XC-352's D5 (the PI, 2026-10-11, approving the audit's proposal); REC-12 revised in Task 12; call 10 (no start-up refusal added); `_hold` and `_command` unchanged; the count; the breaks seen failing.

---

### Task 10: A starting value outside its declared range is checked widened to it, and refused only for what breaks the run (XC-352's D2)

`check.beyond_range` runs a task's load-time checks again with each range widened to the values outside it (`check.widened`): each such value is a warning, `outside-range`, that the task was not designed for it, and a wait longer than any the task declares a second warning, `longer-than-declared`, that stop, pause and the out-of-cage limit go unheard until that trial ends (the PI's answer of 2026-10-12, "Allow, with a warning"; call 4, Appendix A, item 2). What the widening newly makes block is refused, saying which value; so is a finding of `BREAKS_A_RUN` (windows colliding, a crowded array, a color the panel cannot make) about something the declared task's findings are not about (`Finding.subjects`, set here for overlapping windows and crowded arrays, and by Task 5 for a clip; the review's I5), while one that only enlarges an overlap or a clip the task was accepted with is a warning. `preflight.beyond` runs it on a run's starting values, its warnings joining the run's warnings item and what is refused failing the starting values item, which no longer fails a value only for being outside its range.

**Files:**
- Modify: `wl_xcon/check.py` (`check_task`; new `BREAKS_A_RUN`, `TRIAL_CAP`, `_outside`, `_waits`, `widened`, `beyond_range`; `_overlapping_windows`', `_crowded_arrays`' subjects), `wl_xcon/preflight.py` (imports; new `starting`, `beyond`; `values`), `wl_xcon/service.py` (`_preflight`), `wl_xcon/task.py` (`Param.start`'s comment), `wl_xcon/warnlist.py` (docstring)
- Modify (test): `tests/test_range_checks.py`, `tests/test_preflight.py`, `tests/test_service.py`
- Modify (docs): `docs/backlog.md` (XC-371 and XC-373 filed; "Next free" XC-374)

**Interfaces:**
- Produces: `check.BREAKS_A_RUN: tuple[str, ...]`; `check.TRIAL_CAP: str`; `check.widened(task, values) -> Task`; `check.beyond_range(task, values, allocation=PROVISIONAL, components=None, geometry=None, calibration=None, deployment=None) -> list[Finding]` (per value an `outside-range` warning and, for a wait longer than any the task declares, a `longer-than-declared` warning; then the widened task's new findings, each detail starting "with '<name>' at <value>, outside its declared range: "); `overlapping-windows` and `crowded-array` with `subjects` (the state and pair of windows; the array), and a several-structure task's subjects named by structure (`check_task`); `preflight.starting(task, given) -> dict`; `preflight.beyond(task, given, allocation, geometry, calibration, deployment) -> list[Finding]`, never raising (a fault is a blocking `outside-range`); `preflight.values(task, given, refused=()) -> PreflightItem`.

- [ ] **Step 1: Write the failing tests**

**`tests/test_preflight.py`** (5 replacements, in order):

Replace:

```python
        ({"fix_hold": 0.3}, "pass", "each declared and in range"),
        ({"fix_hold": 99.0}, "fail", "outside"),
```

with:

```python
        ({"fix_hold": 0.3}, "pass", "each declared and in range"),
        # Outside its range: a warning, never this item's fail (XC-352's D2; `preflight.beyond`).
        ({"fix_hold": 99.0}, "pass", "1 outside its declared range ('fix_hold')"),
```

Replace:

```python
    assert "'fix_hold' could not be checked against its declaration: TypeError: " in item.said
    assert "'fix_acquisition' is declared over [0.5, 10.0] s and 99.0 is outside it" in item.said
```

with:

```python
    assert "'fix_hold' could not be checked against its declaration: TypeError: " in item.said
    # Outside its range, a warning (XC-352's D2): never among this item's fails.
    assert "'fix_acquisition'" not in item.said
```

Replace:

```python

def test_a_tasks_own_start_outside_its_range_fails_as_a_sent_value_does():
    """`Param` refuses such a start as the task is built (m2), so a task file cannot
    declare one; the pre-flight still holds every merged value to its range."""
```

with:

```python

def test_a_tasks_own_start_outside_its_range_is_held_as_a_sent_value_is():
    """`Param` refuses such a start as the task is built (m2), so a task file cannot
    declare one; the pre-flight still holds every merged value to its range, which outside it
    is a warning since XC-352's D2 (the PI, 2026-10-11)."""
```

Replace:

```python

    assert item.result == "fail"
    assert "'fix_hold' is declared over [0.05, 2.0] s and 99.0 is outside it" in item.said
```

with:

```python

    assert item.result == "pass" and "1 outside its declared range ('fix_hold')" in item.said
```

Replace:

```python
        _as_task(_unchecked(_trial(), "fix_hold", 99.0)), {"fix_hold": 0.3}
    ).result == "pass", (
        "what was sent is what the run starts with"
    )

```

with:

```python
        _as_task(_unchecked(_trial(), "fix_hold", 99.0)), {"fix_hold": 0.3}
    ).said == "10 starting value(s), each declared and in range", (
        "what was sent is what the run starts with"
    )


def test_a_starting_value_outside_its_range_is_checked_widened_and_what_breaks_fails_the_item():
    """XC-352's D2 (the PI, 2026-10-11): the load-time checks run again with the range widened to
    the value (`preflight.beyond`); what breaks the run -- here the target off direct view's
    screen -- fails the starting values item, saying which value, and the rest are warnings."""
    task = _load_task(TASK)

    off = preflight.beyond(task, {"target_x": 40.0}, ALLOCATION, DIRECT, SRGB, None)
    wide = preflight.beyond(task, {"fix_window": 7.0}, ALLOCATION, DIRECT, SRGB, None)
    item = preflight.values(task, {"target_x": 40.0}, [f for f in off if f.blocking])

    assert [(f.code, f.blocking) for f in wide] == [("outside-range", False)]
    assert {f.code for f in off if f.blocking} == {"stimulus-off-screen"}
    assert item.result == "fail"
    assert "stimulus-off-screen: with 'target_x' at 40, outside its declared range: " in item.said


def test_a_check_that_cannot_run_widened_fails_closed(tmp_path, monkeypatch):
    """Nothing a task's declarations hold raises out of the pre-flight: a widened check that
    raises refuses the value, naming why."""
    monkeypatch.setattr(preflight, "beyond_range", lambda *a, **k: 1 / 0)

    (refusal,) = preflight.beyond(_load_task(TASK), {"fix_window": 7.0}, ALLOCATION, DIRECT, SRGB, None)

    assert refusal.blocking and refusal.code == "outside-range"
    assert "could not be run again with the range widened (ZeroDivisionError" in refusal.detail

```

**`tests/test_range_checks.py`** (4 replacements, in order):

Replace:

```python

from wl_xcon.check import check
```

with:

```python

import inspect
from dataclasses import replace

from wl_xcon.check import BREAKS_A_RUN, beyond_range, check, widened
```

Replace:

```python
from wl_xcon.task import (
    After,
```

with:

```python
from wl_xcon.photometry import SRGB, Gray
from wl_xcon.run import run_trial
from wl_xcon.task import (
    Task,
    After,
```

Replace:

```python
    Show,
    State,
```

with:

```python
    Show,
    Square,
    State,
```

Replace:

```python
    assert "crowded-array" not in codes(trial)

```

with:

```python
    assert "crowded-array" not in codes(trial)


# --- A value outside its declared range (the PI, 2026-10-11, XC-352's D2) -------------------


def _windows_task(high: float) -> Task:
    """`two_windows` as a task: `fix_window`'s radius over [0.5, `high`], 6° from a 2° window."""
    trial = two_windows((0.0, 0.0), P("fix_window"), (6.0, 0.0), 2.0,
                        params=[Param("fix_window", unit="deg", low=0.5, high=high, start=1.0)])
    return Task({"windows": trial}, default="windows")


def test_a_value_inside_its_range_is_checked_as_declared_and_adds_nothing():
    assert beyond_range(_windows_task(3.0), {"fix_window": 3.0}) == []
    assert widened(_windows_task(3.0), {"fix_window": 2.0}).params == _windows_task(3.0).params


def test_a_range_is_widened_to_a_value_outside_it_and_nowhere_else():
    task = widened(_windows_task(3.0), {"fix_window": 0.2, "other": 9.0, "fix_hold": "words"})

    (param,) = task.params
    assert (param.low, param.high) == (0.2, 3.0)


def test_a_value_outside_its_range_that_breaks_nothing_is_a_warning_the_task_was_not_designed_for_it():
    """D2: "accept with a warning that the task was not designed for it if nothing breaks"."""
    (warning,) = beyond_range(_windows_task(3.0), {"fix_window": 0.2})

    assert (warning.code, warning.blocking, warning.accepted_in) == (
        "outside-range", False, SESSION_KINDS)
    assert warning.detail.startswith(
        "'fix_window' is 0.2 deg, outside the [0.5, 3.0] the task declares, so the task was not "
        "designed for it")


def test_a_value_outside_its_range_that_makes_windows_collide_is_refused_saying_what():
    """D2: "refuse only what would break the run (off screen, windows colliding, colors
    unmakeable), saying what". Windows that can overlap within the declared ranges are a warning
    at load (A8); widened past them to a value that makes them collide, refused."""
    found = beyond_range(_windows_task(3.0), {"fix_window": 5.0})

    (refusal,) = [f for f in found if f.blocking]
    assert refusal.code == "overlapping-windows" and refusal.code in BREAKS_A_RUN
    assert refusal.detail.startswith(
        "with 'fix_window' at 5, outside its declared range: state 'wait' scores")
    assert [f.code for f in found if not f.blocking] == ["outside-range"]
    assert set(BREAKS_A_RUN) == {"overlapping-windows", "crowded-array", "unrealizable-color"}


def _waiting_task() -> Task:
    """One state waiting on `fix_acquisition` (0.5-10 s) for a fixation, or `fix_hold` (0.05-2 s)
    inside its window; the task's longest declared wait is 10 s."""
    trial = Trial(
        start="wait",
        params=[Param("fix_acquisition", unit="s", low=0.5, high=10.0, start=4.0),
                Param("fix_hold", unit="s", low=0.05, high=2.0, start=0.3)],
        windows=[Window("fix", at=(0.0, 0.0), radius=2.0, on="fix")],
        states=[State("wait", enter=[Show(FIX)], go=[
            On(Hold("fix", P("fix_hold")), Outcome.CORRECT),
            On(After(P("fix_acquisition")), Outcome.NO_FIXATION),
        ])],
    )
    return Task({"waiting": trial}, default="waiting")


def test_a_wait_outside_its_range_but_within_the_tasks_longest_is_a_warning():
    """`fix_hold` at 8 s is outside its 0.05-2 s and within the 10 s the task already waits."""
    assert [(f.code, f.blocking) for f in beyond_range(_waiting_task(), {"fix_hold": 8.0})] == [
        ("outside-range", False)]


def test_a_wait_longer_than_any_the_task_declares_is_a_warning_that_stop_and_the_limit_go_unheard():
    """The plan's call 4, answered by the PI on 2026-10-12: "Allow, with a warning". Stop, pause
    and the out-of-cage limit are heard between trials, never inside one, until they are checked
    about once a second inside a trial (XC-373), so the warning, one per wait, says they go
    unheard until that trial ends, and names the trial cap that ends it at the latest."""
    found = beyond_range(_waiting_task(), {"fix_acquisition": 60.0})

    assert [(f.code, f.blocking, f.accepted_in) for f in found] == [
        ("outside-range", False, SESSION_KINDS), ("longer-than-declared", False, SESSION_KINDS)]
    assert found[1].detail.startswith(
        "'fix_acquisition' at 60 s is a wait longer than any the task declares (its longest, 10 s)")
    assert "they go unheard until that trial ends" in found[1].detail
    # The cap it names is the loop's; build C2a's five-minute cap changes both (engine spec §6.8).
    assert inspect.signature(run_trial).parameters["max_frames"].default == 100_000
    assert "the trial cap, 100,000 frames (about 417 s at 240 Hz)" in found[1].detail


def test_a_literal_wait_counts_toward_the_tasks_longest():
    """A literal `After` of 30 s makes the task's longest wait 30 s, so `fix_acquisition` may go
    to 20 s with a warning."""
    trial = _waiting_task().structures["waiting"]
    state = trial.states[0]
    longer = replace(trial, states=[replace(state, go=[*state.go, On(After(30.0), Outcome.ABORT)])])

    found = beyond_range(Task({"waiting": longer}, default="waiting"), {"fix_acquisition": 20.0})

    assert [(f.code, f.blocking) for f in found] == [("outside-range", False)]


def test_a_finding_the_declared_ranges_already_give_is_not_refused_again():
    """What the declared task's checks already find was accepted with it; only what the
    widening adds is judged."""
    found = beyond_range(_windows_task(5.0), {"fix_window": 0.2})

    assert [f.code for f in found] == ["outside-range"]


def test_a_value_that_only_enlarges_an_overlap_the_task_was_accepted_with_is_a_warning():
    """The warnings-over-refusals review's I5: windows that already overlap at the declared
    extreme were accepted with the task at load (A8); a value past it that only brings them
    closer is about nothing new (`Finding.subjects`: the same state and pair of windows), and is
    a warning saying the value, never a refusal."""
    found = beyond_range(_windows_task(5.0), {"fix_window": 5.2})

    assert [(f.code, f.blocking) for f in found] == [
        ("outside-range", False), ("overlapping-windows", False)]
    assert found[1].detail.startswith(
        "with 'fix_window' at 5.2, outside its declared range: state 'wait' scores")


def _array_task(most: int) -> Task:
    """Two to `most` objects on a ring 8-12° out, each window up to 2° in radius: they crowd past
    twelve objects."""
    from wl_xcon.task import Array, ObjectWindows, SaccadeTo

    trial = Trial(
        start="search",
        params=[Param("set_size", unit="objects", low=2, high=most),
                Param("array_eccentricity", unit="deg", low=8.0, high=12.0),
                Param("object_window", unit="deg", low=0.5, high=2.0)],
        windows=[ObjectWindows(of="search", radius=P("object_window"))],
        states=[State("search", enter=[Show(Stimulus("search", at=(0.0, 0.0), looks=Array(
            n=P("set_size"), radius=P("array_eccentricity"), target=0)))], go=[
            On(SaccadeTo("search.target"), Outcome.CORRECT),
            On(After(1.0), Outcome.NO_RESPONSE),
        ])],
    )
    return Task({"search": trial}, default="search")


def test_an_array_crowded_further_is_a_warning_and_one_newly_crowded_is_refused():
    """The review's I5, for an array: one that crowds at sixteen objects was accepted with the
    task (A9), so twenty is a warning; one that never crowded, at most six, is refused at
    twenty."""
    worse = beyond_range(_array_task(16), {"set_size": 20})
    newly = beyond_range(_array_task(6), {"set_size": 20})

    assert [(f.code, f.blocking) for f in worse] == [
        ("outside-range", False), ("crowded-array", False)]
    assert [(f.code, f.blocking) for f in newly] == [
        ("outside-range", False), ("crowded-array", True)]


def _two_lights(brightest: float) -> Task:
    """A disc lit by `disc`, over 10 to `brightest` cd/m², and a square by `square`, over 10 to
    50: the sRGB default's white is 80 cd/m²."""
    trial = Trial(
        start="on",
        params=[Param("disc", unit="cd/m2", low=10.0, high=brightest, start=20.0),
                Param("square", unit="cd/m2", low=10.0, high=50.0, start=20.0)],
        states=[State("on", enter=[
            Show(Stimulus("d", at=(-2.0, 0.0), looks=Disc(size=1.0, color=Gray(P("disc"))))),
            Show(Stimulus("s", at=(2.0, 0.0), looks=Square(size=1.0, color=Gray(P("square"))))),
        ], go=[On(After(1.0), Outcome.CORRECT)])],
    )
    return Task({"lights": trial}, default="lights")


def test_a_light_clipped_further_is_a_warning_and_one_newly_clipped_is_refused_naming_it():
    """The review's I5, for colors: the disc, which the panel clips at the top of its declared
    range, was accepted with the task (A20), so a value that only clips it further is a warning;
    one that makes the square too bright for the panel, which made it, is refused, naming it."""
    further = beyond_range(_two_lights(100.0), {"disc": 150.0}, calibration=SRGB)
    newly = beyond_range(_two_lights(100.0), {"square": 150.0}, calibration=SRGB)

    assert [f.blocking for f in further if f.code == "unrealizable-color"] == [False]
    (refusal,) = [f for f in newly if f.blocking]
    assert refusal.code == "unrealizable-color"
    assert refusal.detail.endswith("(new with this value: Square)")


def test_an_overlap_new_in_one_structure_is_refused_though_another_has_one_of_the_same_names():
    """What a finding is about is named by its structure in a task of several (`check_task`): two
    structures whose windows share their names, one overlapping at the declared extreme and one
    not, widened until the second overlaps too -- that overlap is new, and refused."""
    def windows(far: float) -> Trial:
        return two_windows((0.0, 0.0), P("fix_window"), (far, 0.0), 2.0,
                           params=[Param("fix_window", unit="deg", low=0.5, high=5.0, start=1.0)])
    task = Task({"near": windows(6.0), "far": windows(10.0)}, default="near")

    found = beyond_range(task, {"fix_window": 9.0})

    (refusal,) = [f for f in found if f.blocking]
    assert refusal.code == "overlapping-windows" and "in structure 'far'" in refusal.detail

```

**`tests/test_service.py`** (2 replacements, in order):

Replace:

```python

def test_a_task_whose_declarations_are_malformed_fails_its_preflight_and_the_service_goes_on(
```

with:

```python

def test_a_starting_value_outside_its_range_starts_with_a_warning_unless_it_breaks_the_run(tmp_path):
    """XC-352's D2 (the PI, 2026-10-11: "re-run the load-time checks with the range widened to the
    new value; accept with a warning that the task was not designed for it if nothing breaks;
    refuse only what would break the run"): a fixation window of 7° (declared 0.5-5°) asks for its
    warning and starts once accepted, `warnings.jsonl` recording it; a target at 40° (declared
    ±16°) is off direct view's screen, and the start is refused, saying so."""
    service = _service(tmp_path)
    _step(service, _open())

    off = _step(service, _start(values={**VALUES, "target_x": 40.0}))
    wide = _step(service, CheckRun(by=BY, task=TASK, values={**VALUES, "fix_window": 7.0}))
    started = _step(service, _start(values={**VALUES, "fix_window": 7.0}))

    assert off.run_index is None
    assert ("starting values: stimulus-off-screen: with 'target_x' at 40, outside its declared "
            "range: ") in _refused(off)[-1]
    items = {i.name: i for i in wide.preflight.items}
    assert items["starting values"].result == "pass" and items["warnings"].result == "unknown"
    assert "outside-range: 'fix_window' is 7 deg, outside the [0.5, 5.0]" in items["warnings"].said
    assert started.run_index == 0
    rows = _jsonl(service.root / "2027-01-14_01" / "xcon" / "warnings.jsonl")
    assert [r["how"] for r in rows if r["code"] == "outside-range"] == ["start"]


def test_a_task_whose_declarations_are_malformed_fails_its_preflight_and_the_service_goes_on(
```

Replace:

```python
    [
        ({"values": {**VALUES, "fix_hold": 99.0}}, "starting values"),
```

with:

```python
    [
        # Off the screen: a starting value outside its range that breaks the run (XC-352's D2).
        ({"values": {**VALUES, "target_x": 40.0}}, "starting values"),
```

- [ ] **Step 2: Run them and see them fail**

Run: `$PY -m pytest -q -p no:cacheprovider tests/test_range_checks.py`
Expected: an `ImportError: cannot import name 'BREAKS_A_RUN' from 'wl_xcon.check'` as the module is collected.

Run: `$PY -m pytest -q -p no:cacheprovider tests/test_preflight.py tests/test_service.py`
Expected: `7 failed, 298 passed`: the starting values item still failing a value outside its range; `preflight.beyond` missing; the service's starts refused on the range alone.

- [ ] **Step 3: Implement**

**`wl_xcon/check.py`** (4 replacements, in order):

Replace:

```python
            findings.append(
                dataclasses.replace(finding, detail=f"in structure {name!r}: {finding.detail}")
                if several else finding
            )
```

with:

```python
            findings.append(
                dataclasses.replace(
                    finding, detail=f"in structure {name!r}: {finding.detail}",
                    subjects=tuple(f"{name}: {subject}" for subject in finding.subjects))
                if several else finding
            )
```

Replace:

```python
        + _head_faults(task, deployment)
    )

```

with:

```python
        + _head_faults(task, deployment)
    )


#: The findings a value outside its declared range is refused for when it newly causes them,
#: beside every finding that blocks: what the PI named as breaking the run (2026-10-11, XC-352's
#: D2: "refuse only what would break the run (off screen, windows colliding, colors unmakeable),
#: saying what"). Each is a warning at load, within the declared ranges, since his rulings on
#: A8, A9 and A20 the same day, and so is one that is about nothing new (`Finding.subjects`: the
#: same pair of windows, array or color, only larger); off screen (`stimulus-off-screen`)
#: already blocks.
BREAKS_A_RUN = ("overlapping-windows", "crowded-array", "unrealizable-color")

#: The trial cap, as a `longer-than-declared` warning says it: `run.run_trial`'s `max_frames`
#: backstop, 100,000 frames, about 417 s at the 240 Hz `wlx taskd` runs at (computed). Build C2a
#: makes it five minutes at the session's rate (engine spec §6.8), and this changes with it.
TRIAL_CAP = "the trial cap, 100,000 frames (about 417 s at 240 Hz)"


def _outside(param: Param, value: object) -> bool:
    """Whether `value` is a finite number outside the range `param` declares (a setting with
    choices has none)."""
    if param.choices or isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    if not math.isfinite(value):
        return False
    return ((param.low is not None and value < param.low)
            or (param.high is not None and value > param.high))


def _waits(task: Task) -> tuple[set[str], float]:
    """The settings a trial waits on -- an `After`'s or a `Hold`'s seconds -- and the longest wait
    the task declares: the highest bound any of them declares, or its longest literal wait."""
    declared = {param.name: param for param in task.params}
    names: set[str] = set()
    longest = 0.0
    for structure in task.structures.values():
        for state in structure.states:
            for edge in state.go:
                if not isinstance(edge.guard, (After, Hold)):
                    continue
                seconds = edge.guard.seconds
                if isinstance(seconds, P):
                    names.add(seconds.name)
                    param = declared.get(seconds.name)
                    if param is not None and _is_number(param.high):
                        longest = max(longest, float(param.high))
                elif _is_number(seconds):
                    longest = max(longest, float(seconds))
    return names, longest


def widened(task: Task, values) -> Task:
    """`task` with each numeric setting's declared range stretched to take its number in
    `values`, every structure alike: what the load-time checks are run again against for a value
    outside its range (the PI, 2026-10-11, XC-352's D2). A setting with choices, a value that is
    no finite number, a name the task does not declare and a value inside its range leave its
    declaration as it is."""
    def wide(param: Param) -> Param:
        value = values.get(param.name)
        if not _outside(param, value):
            return param
        low = value if param.low is not None and value < param.low else param.low
        high = value if param.high is not None and value > param.high else param.high
        return dataclasses.replace(param, low=low, high=high, start=None)

    return dataclasses.replace(task, structures={
        name: dataclasses.replace(structure, params=[wide(p) for p in structure.params])
        for name, structure in task.structures.items()
    })


def beyond_range(
    task: Task,
    values,
    allocation: Allocation = PROVISIONAL,
    components: Registry | None = None,
    geometry: Geometry | None = None,
    calibration: Calibration | None = None,
    deployment: Deployment | None = None,
) -> list[Finding]:
    """**A value outside its declared range** (the PI, 2026-10-11, XC-352's D2: "re-run the
    load-time checks with the range widened to the new value; accept with a warning that the task
    was not designed for it if nothing breaks; refuse only what would break the run (off screen,
    windows colliding, colors unmakeable), saying what"): for each, a warning, `outside-range`,
    and for a wait longer than any the task declares a second, `longer-than-declared` (`_waits`;
    the PI, 2026-10-12: "Allow, with a warning"), each accepted in every kind. Then each finding
    the task widened to them gives that the task as declared does not, saying which values
    caused it: **refused** when it blocks, or when it is one `BREAKS_A_RUN` names about something
    the declared task's findings are not (`Finding.subjects`); otherwise a warning, among them a
    value that only enlarges an overlap or a clip the task was accepted with at load. Nothing
    when every value is inside its range. The ranges are what every load-time proof is made over
    (S1 §9's "a check against declared ranges proves an experimenter cannot break it from the
    console"), so the checks run again, twice, here: at a run's start (`preflight.beyond`) and on
    a live edit (`Session.set`)."""
    declared = {param.name: param for param in task.params}
    outside = {name: value for name, value in values.items()
               if name in declared and _outside(declared[name], value)}
    if not outside:
        return []
    # **A wait longer than any the task declares is a warning**, one per wait (the PI, 2026-10-12,
    # on the plan's call 4: "Allow, with a warning"): stop, pause and the out-of-cage limit are
    # heard between trials, never inside one, until they are checked about once a second inside
    # a trial (WEL-11; engine spec §6.8; XC-373), when this sentence changes, as it does with
    # build C2a's five-minute cap (`TRIAL_CAP`).
    waits, longest = _waits(task)
    findings: list[Finding] = []
    for name, value in outside.items():
        findings.append(Finding("outside-range", (
            f"{name!r} is {value:g} {declared[name].unit}, outside the [{declared[name].low}, "
            f"{declared[name].high}] the task declares, so the task was not designed for it: its "
            f"load-time checks were proved only over that range, and were run again with the "
            f"range widened to {value:g}"), blocking=False, accepted_in=SESSION_KINDS))
        if name in waits and value > longest:
            findings.append(Finding("longer-than-declared", (
                f"{name!r} at {value:g} s is a wait longer than any the task declares (its "
                f"longest, {longest:g} s), and a stop, a pause and the out-of-cage limit are heard "
                f"only between trials: while a trial waits on {name!r} they go unheard until that "
                f"trial ends, and {TRIAL_CAP} ends any trial still running then, with no outcome "
                f"(a hang)"), blocking=False, accepted_in=SESSION_KINDS))
    said = ", ".join(f"{name!r} at {value:g}" for name, value in outside.items())
    before = check_task(task, allocation, components, geometry, calibration, deployment)
    # What the declared task's findings are about (the warnings-over-refusals review's I5): a
    # finding of `BREAKS_A_RUN` about the same thing, only larger, was accepted with the task.
    known = {(finding.code, subject) for finding in before for subject in finding.subjects}
    for finding in check_task(widened(task, outside), allocation, components, geometry,
                              calibration, deployment):
        if finding in before or not (finding.blocking or finding.is_warning):
            continue
        detail = f"with {said}, outside its declared range: {finding.detail}"
        new = [subject for subject in finding.subjects if (finding.code, subject) not in known]
        if finding.blocking or (finding.code in BREAKS_A_RUN and (new or not finding.subjects)):
            if len(finding.subjects) > 1:
                detail += f" (new with this value: {'; '.join(new)})"
            findings.append(Finding(finding.code, detail))
        else:
            findings.append(dataclasses.replace(finding, detail=detail))
    return findings

```

Replace:

```python
                            f"a look at one can count as the other",
                            blocking=False,
                            accepted_in=SESSION_KINDS,
                        )
```

with:

```python
                            f"a look at one can count as the other",
                            blocking=False,
                            accepted_in=SESSION_KINDS,
                            subjects=(f"state {state.name!r}: {pair[0]!r} and {pair[1]!r}",),
                        )
```

Replace:

```python
                    f"saccade to one would be scored against another",
                    blocking=False,
                    accepted_in=SESSION_KINDS,
                )
```

with:

```python
                    f"saccade to one would be scored against another",
                    blocking=False,
                    accepted_in=SESSION_KINDS,
                    subjects=(f"array {declared.of!r}",),
                )
```

**`wl_xcon/preflight.py`** (6 replacements, in order):

Replace:

```python
from wl_xcon.bounds import Exceeded
from wl_xcon.check import check_task, parameters_used
from wl_xcon.cli import _load_bounds, _load_subject_settings, _load_task, _setup_words
from wl_xcon.link import Preflight, PreflightItem
```

with:

```python
from wl_xcon.bounds import Exceeded
from wl_xcon.check import beyond_range, check_task, parameters_used
from wl_xcon.cli import _load_bounds, _load_subject_settings, _load_task, _setup_words
from wl_xcon.findings import Finding
from wl_xcon.link import Preflight, PreflightItem
```

Replace:

```python

def values(task: Task | None, given: dict) -> PreflightItem:
```

with:

```python

def starting(task: Task, given: dict) -> dict:
    """A run's starting values: its task's own (`Param.start`), with what a console sent over
    them (P4d-2b spec §6.2; S8 §3.4)."""
    starts = {param.name: param.start for param in task.params if param.start is not None}
    return {**starts, **given}


def beyond(task: Task | None, given: dict, allocation, geometry, calibration, deployment) -> list:
    """**A run's starting values outside their declared ranges** (the PI, 2026-10-11, XC-352's D2):
    the load-time checks run again with each range widened to its value (`check.beyond_range`),
    the session's setup, calibration and deployment theirs. Its warnings join the run's warnings
    item and what blocks fails the starting values item (`values`). **Nothing raises out of
    here**: a check that does not finish refuses the values, naming why."""
    if task is None:
        return []
    try:
        return beyond_range(task, starting(task, given), allocation, geometry=geometry,
                            calibration=calibration, deployment=deployment)
    except Exception as broken:  # noqa: BLE001 -- the checks run on code; their fault refuses
        return [Finding("outside-range", (
            f"a starting value is outside its declared range, and the load-time checks could not "
            f"be run again with the range widened ({type(broken).__name__}: {broken})"))]


def values(task: Task | None, given: dict, refused=()) -> PreflightItem:
```

Replace:

```python
    its trial structures' (engine spec §3.5):
    **fail** for a name it does not declare, a word where it takes a number, a number
    outside its range, a choice it does not offer, or a declaration it cannot be
    compared with; and **for a number the task uses that nothing gives a value** (the
```

with:

```python
    its trial structures' (engine spec §3.5):
    **fail** for a name it does not declare, a word where it takes a number, a choice it does
    not offer, or a declaration it cannot be compared with; for what `refused` holds, the
    findings that block once the checks are run again with a range widened to a value outside
    it (`beyond`; the PI, 2026-10-11, XC-352's D2: a value outside its range is a warning,
    never this item's fail, unless it breaks the run); and **for a number the task uses that
    nothing gives a value** (the
```

Replace:

```python
    merged = {**starts, **given}
    wrong = []
```

with:

```python
    merged = {**starts, **given}
    wrong, outside = [], []
```

Replace:

```python
            ):
                wrong.append(
                    f"{name!r} is declared over [{param.low}, {param.high}] {param.unit} and "
                    f"{value} is outside it"
                )
```

with:

```python
            ):
                outside.append(name)
```

Replace:

```python
            )
    if wrong:
        return PreflightItem(STARTING_VALUES, FAIL, "; ".join(wrong))
    return PreflightItem(
```

with:

```python
            )
    wrong += [f"{f.code}: {f.detail}" for f in refused]
    if wrong:
        return PreflightItem(STARTING_VALUES, FAIL, "; ".join(wrong))
    if outside:
        return PreflightItem(STARTING_VALUES, PASS, (
            f"{len(merged)} starting value(s), each declared; {len(outside)} outside its declared "
            f"range ({', '.join(repr(name) for name in outside)}), a warning the warnings item "
            f"asks to accept"))
    return PreflightItem(
```

**`wl_xcon/service.py`** (3 replacements, in order):

Replace:

```python
            checked, loaded, findings = _unfinished((_preflight.TASK_CHECKS,), broken), None, []

```

with:

```python
            checked, loaded, findings = _unfinished((_preflight.TASK_CHECKS,), broken), None, []
        # Starting values outside their declared ranges, checked widened (XC-352's D2): its
        # warnings join the run's, and what breaks the run fails the starting values item.
        beyond = _preflight.beyond(loaded, values, self.allocation, session.spec.geometry,
                                   session.spec.calibration, session.spec.deployment)

```

Replace:

```python
            item, found = _preflight.warnings(
                rig + warnlist.of_findings(findings),
```

with:

```python
            item, found = _preflight.warnings(
                rig + warnlist.of_findings(findings + beyond),
```

Replace:

```python
                *_contained(
                    (_preflight.STARTING_VALUES,), lambda: _preflight.values(loaded, values)
```

with:

```python
                *_contained(
                    (_preflight.STARTING_VALUES,),
                    lambda: _preflight.values(loaded, values, [f for f in beyond if f.blocking]),
```

**`wl_xcon/task.py`**:

Replace:

```python
    #: b3a-2 final review, m2). A bound that is not a real number is left to
    #: `preflight.values`, which holds the merged values to `[low, high]` again and fails
    #: closed on a bound it cannot compare. `None`, the default, leaves it to whoever
```

with:

```python
    #: b3a-2 final review, m2). A bound that is not a real number is left to
    #: `preflight.values`, which holds the merged values to `[low, high]` again -- one outside
    #: it a warning since XC-352's D2 (2026-10-11), unless the checks widened to it refuse it
    #: (`preflight.beyond`) -- and fails closed on a bound it cannot compare. `None`, the
    #: default, leaves it to whoever
```

**`wl_xcon/warnlist.py`**:

Replace:

```python
are warnings (`luminance-step`, `color-on-default`, `contrast-on-default`, and, since the PI's
ruling of 2026-10-11, `head-not-fixed`); and today's
```

with:

```python
are warnings (`luminance-step`, `color-on-default`, `contrast-on-default`, and, since the PI's
rulings of 2026-10-11, `head-not-fixed`, `overlapping-windows`, `crowded-array`,
`wrong-eye-criterion`, `monocular-stereogram`, `wrong-setup`, `isoluminance-on-default`,
`unrealizable-color`, `cone-colors-without-spectra` and, for a starting value outside its range,
`outside-range` and, for a wait longer than any the task declares, `longer-than-declared`, by
his answer of 2026-10-12); and today's
```

The backlog (calls 12 and 4):

**`docs/backlog.md`** -- first replace the `**Next free ID: XC-NNN.**` line, whatever it reads (XC-371 since Task 5), with `**Next free ID: XC-374.**` (XC-372 is Task 11's); then:

Replace:

```markdown
- **XC-370** Record the light the panel actually shows beside the light asked for wherever a drawn light is clipped, per frame or per trial, from the display process's clipped output (exact.shown defines it): the PI, 2026-10-11, XC-352's A20, "the drawer records the light actually shown beside the one asked for"; until then only check's unrealizable-color warning names it, recorded in warnings.jsonl, for each light it can see at load. — 2026-10-11, [warnings-over-refusals plan, call 5](superpowers/plans/2026-10-11-warnings-over-refusals.md#calls-taken-in-this-plan) — waits on: engine builds E and F (the display process and the screen log)
- **XC-340** Record wl-xcon's own version (its commit, and whether its tree was clean) in each session's config.json among the facts recorded at its open: a task's content hash names what the task declares and, through declarations.FORMAT, the defaults it was read with, but not the engine that ran it. — 2026-10-11, [engine C1 plan, call 11](superpowers/plans/2026-10-11-engine-c1.md#calls-taken-in-this-plan) — waits on: engine build C4 (the facts recorded at a session's open)
```

with:

```markdown
- **XC-370** Record the light the panel actually shows beside the light asked for wherever a drawn light is clipped, per frame or per trial, from the display process's clipped output (exact.shown defines it): the PI, 2026-10-11, XC-352's A20, "the drawer records the light actually shown beside the one asked for"; until then only check's unrealizable-color warning names it, recorded in warnings.jsonl, for each light it can see at load. — 2026-10-11, [warnings-over-refusals plan, call 5](superpowers/plans/2026-10-11-warnings-over-refusals.md#calls-taken-in-this-plan) — waits on: engine builds E and F (the display process and the screen log)
- **XC-371** Check wlx run's --set starting values against their declared ranges as wlx taskd's pre-flight does since XC-352's D2 (widened, refused only for what breaks the run, otherwise a warning --accept-warnings accepts): wlx run takes no pre-flight (XC-159) and runs a value outside its range with no warning at all, as it did before the ruling. — 2026-10-11, [warnings-over-refusals plan, call 12](superpowers/plans/2026-10-11-warnings-over-refusals.md#calls-taken-in-this-plan) — waits on: nothing
- **XC-373** Build the once-a-second checks of stop, pause and the welfare limits inside a long trial (engine spec §6.8 and §20 item 4; WEL-11): until then they are heard only between trials, which check's longer-than-declared warning says of a wait outside its declared range (the PI, 2026-10-12, "Allow, with a warning"); that warning's sentence changes when this lands. — 2026-10-12, [warnings-over-refusals plan, call 4](superpowers/plans/2026-10-11-warnings-over-refusals.md#calls-taken-in-this-plan) — waits on: a build that takes on engine spec §6.2 and §6.8
- **XC-340** Record wl-xcon's own version (its commit, and whether its tree was clean) in each session's config.json among the facts recorded at its open: a task's content hash names what the task declares and, through declarations.FORMAT, the defaults it was read with, but not the engine that ran it. — 2026-10-11, [engine C1 plan, call 11](superpowers/plans/2026-10-11-engine-c1.md#calls-taken-in-this-plan) — waits on: engine build C4 (the facts recorded at a session's open)
```

- [ ] **Step 4: Run them and see them pass**

Run the three files, then the whole suite. Expected: `324 passed`; the suite **3530 passed**.

- [ ] **Step 5: Prove they can fail**

Over the three files:
- `_outside`'s last `return` → `return False`: fourteen fail.
- `widened`'s two `low = …`, `high = …` lines → `low, high = param.low, param.high`: nine fail, the windows-colliding test among them.
- `beyond_range`'s `if finding in before or not (…)` → `if not (…)`: eleven fail, `test_a_finding_the_declared_ranges_already_give_is_not_refused_again` among them.
- Its `if finding.blocking or (finding.code in BREAKS_A_RUN and (new or not finding.subjects)):` → `if finding.blocking:`: four fail, `test_a_value_outside_its_range_that_makes_windows_collide_is_refused_saying_what` among them.
- **The review's I5**: the same line → `if finding.blocking or finding.code in BREAKS_A_RUN:` (the draft's rule, by sentence), or `known = {…}` → `known = set()`: four fail, `test_a_value_that_only_enlarges_an_overlap_the_task_was_accepted_with_is_a_warning` (`fix_window=5.2`), the array's and the light's among them. `_overlapping_windows`' `subjects=…` line removed: that test and the several-structure one fail; `_crowded_arrays`' removed: `test_an_array_crowded_further_is_a_warning_and_one_newly_crowded_is_refused` fails; `check_task`'s `subjects=tuple(f"{name}: {subject}" …)` → `subjects=finding.subjects`: `test_an_overlap_new_in_one_structure_is_refused_though_another_has_one_of_the_same_names` fails; `if len(finding.subjects) > 1:` → `if False:`: `test_a_light_clipped_further_is_a_warning_and_one_newly_clipped_is_refused_naming_it` fails.
- Its `if name in waits and value > longest:` → `if False:`: `test_a_wait_longer_than_any_the_task_declares_is_a_warning_that_stop_and_the_limit_go_unheard` fails.
- `_waits`' literal branch `elif _is_number(seconds): longest = …` → `elif False: pass`: `test_a_literal_wait_counts_toward_the_tasks_longest` fails.
- Its `if param is not None and _is_number(param.high): longest = …` → `pass`: `test_a_wait_outside_its_range_but_within_the_tasks_longest_is_a_warning` and the wait-warning test fail.
- `values`' `wrong += [f"{f.code}: {f.detail}" for f in refused]` → `pass`: three fail.
- `_preflight`'s `findings + beyond` → `findings`: `test_a_starting_value_outside_its_range_starts_with_a_warning_unless_it_breaks_the_run` fails.
- `beyond`'s `except Exception` → `except KeyError`: `test_a_check_that_cannot_run_widened_fails_closed` and `test_a_task_whose_declarations_are_malformed_fails_its_preflight_and_the_service_goes_on` fail.

- [ ] **Step 6: Commit**

```bash
git add wl_xcon/check.py wl_xcon/preflight.py wl_xcon/service.py wl_xcon/task.py wl_xcon/warnlist.py tests/ docs/backlog.md
git commit -m "Check a starting value outside its declared range widened to it, refusing only what breaks the run"
```
Body: XC-352's D2 (the PI, 2026-10-11, quoted) and his answer of 2026-10-12 on long waits ("Allow, with a warning", quoted); calls 3 and 4 (the review's I4 and I5); XC-371 and XC-373 filed (calls 12 and 4); `preflight.gate` and `Service._start` unchanged; the count; the breaks seen failing.

---

### Task 11: A live value outside its declared range is checked widened to it, in `Session.set`'s task-setting branch (XC-352's D2)

**Welfare-listed**: `Session.set` changes, in the branch for a task's own setting only (Appendix A, item 1). Its range refusal calls `Session._beyond_range` instead, which runs `check.beyond_range` with the session's values, those staged and this one, in its setup, calibration and deployment; refuses, as `Exceeded`, what refuses the session's kind, saying what; otherwise accepts the warnings by the person who sent the value (`how="set"`), says them on the changes feed, and lets `set` stage it. Nothing but `Exceeded` leaves it. The ceiling branch (`if name in self.spec.bounds.ceilings:` to its `return`) is unchanged, byte for byte.

**Files:**
- Modify: `wl_xcon/taskd.py` (imports; `Session.set`'s docstring and its task-setting range check; new `Session._beyond_range`), `wl_xcon/warnlist.py` (docstring)
- Modify (test): `tests/test_taskd.py`
- Modify (docs): `docs/design/architecture.md` (the `Session.set` paragraph), `docs/backlog.md` (XC-372 filed; "Next free" stays XC-374, set by Task 10)

**Interfaces:**
- Consumes: `check.beyond_range` (Task 10), `warnlist.of_findings`, `Session.accept`, `Session._feed`.
- Produces: `Session._beyond_range(name, value, by) -> None`, raising `Exceeded` only.

- [ ] **Step 1: Write the failing tests**

**`tests/test_taskd.py`** (2 replacements, in order):

Replace:

```python

def test_a_live_write_outside_a_parameters_declared_range_is_refused(tmp_path):
    """The declaration S8 §3.1 turns into validation. It is the same declaration the
    console builds its widget from, so a value it cannot show is a value it cannot
    send."""
    session = _session(_spec(tmp_path, trials=4))

    with pytest.raises(Exceeded, match="fix_hold"):
        session.set("fix_hold", 99.0, by=Box("console"))

```

with:

```python

def test_a_live_write_outside_a_parameters_declared_range_is_staged_with_its_warning(tmp_path):
    """The declaration S8 §3.1 turns into validation. Since XC-352's D2 (the PI, 2026-10-11) a
    value outside its range is checked again with the range widened to it, and staged with its
    warning when nothing breaks; with no record open to write that warning into, it is refused."""
    unopened = _session(_spec(tmp_path / "unopened", trials=4))
    with pytest.raises(Exceeded, match="'fix_hold' at 8 is outside its declared range, and its "
                                       "warning could not be recorded"):
        unopened.set("fix_hold", 8.0, by=Box("console"))
    session = _session(_spec(tmp_path / "opened", trials=4))
    session.open()

    session.set("fix_hold", 8.0, by=Box("console"))

    assert session.staged[-1][:3] == ("fix_hold", VALUES["fix_hold"], 8.0)
    assert [row["code"] for row in _warned(session)] == ["outside-range"]


def test_a_live_wait_longer_than_any_the_task_declares_is_staged_with_its_warnings(tmp_path):
    """The plan's call 4, answered by the PI on 2026-10-12: "Allow, with a warning". A stop, a
    pause and the out-of-cage limit are heard between trials, so `fix_acquisition` at 60 s --
    past the 10 s the reference task's longest wait declares -- is staged with two warnings, that
    it is outside its range and that they go unheard until that trial ends."""
    session = _session(_spec(tmp_path, trials=4))
    session.open()

    session.set("fix_acquisition", 60.0, by=Box("console"))

    assert session.staged[-1][:3] == ("fix_acquisition", VALUES["fix_acquisition"], 60.0)
    assert [row["code"] for row in _warned(session)] == ["outside-range", "longer-than-declared"]
```

Replace:

```python
    assert said in session.refusals[0][2]

```

with:

```python
    assert said in session.refusals[0][2]


def _warned(session) -> list[dict]:
    path = session.directory / "warnings.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def test_a_live_value_outside_its_range_applies_with_a_warning_that_the_task_was_not_designed_for_it(
    tmp_path,
):
    """XC-352's D2 (the PI, 2026-10-11: "re-run the load-time checks with the range widened to the
    new value; accept with a warning that the task was not designed for it if nothing breaks"): a
    fixation window of 7° (declared 0.5-5°) is staged and applied at the next boundary; its
    warning, accepted by who set it, is in `warnings.jsonl` and on the changes feed."""
    link = Simulated()
    link.queue(SetParameter(name="fix_window", value=7.0, by=Box("jake")))
    session = _session(_spec(tmp_path, trials=3), link=link)

    session.run()

    assert session.refusals == [] and session.spec.values["fix_window"] == 7.0
    (row,) = _warned(session)
    assert (row["code"], row["how"], row["by"], row["run"]) == (
        "outside-range", "set", {"kind": "box", "name": "jake"}, 0)
    assert row["detail"].startswith("'fix_window' is 7 deg, outside the [0.5, 5.0] the task declares")
    (warned,) = [c for c in session.controls if c[0] == "warning"]
    assert warned[3].startswith("outside-range: 'fix_window' is 7 deg")


def test_a_live_value_that_would_put_the_target_off_screen_is_refused_saying_so(tmp_path):
    """XC-352's D2: "refuse only what would break the run (off screen, ...), saying what". A
    target 40° out (declared ±16°) is off direct view's screen: refused, the previous value
    stands, and no warning is recorded."""
    link = Simulated()
    link.queue(SetParameter(name="target_x", value=40.0, by=Box("jake")))
    session = _session(_spec(tmp_path, trials=3), link=link)

    session.run()

    (refusal,) = session.refusals
    assert refusal[:2] == ("target_x", Box("jake"))
    assert "with the range widened to it the load-time checks refuse it: stimulus-off-screen: " in (
        refusal[2])
    assert refusal[2].endswith("the previous value stands")
    assert session.spec.values["target_x"] == VALUES["target_x"] and _warned(session) == []


def test_a_live_value_whose_widened_checks_raise_or_whose_warning_cannot_be_written_is_refused(
    tmp_path, monkeypatch
):
    """Nothing but `Exceeded` leaves `set` for a value outside its range (`Session._command`
    catches it alone): a check that raises, or a warning row that cannot be written, refuses the
    value, and the session runs on."""
    monkeypatch.setattr("wl_xcon.taskd.beyond_range", lambda *a, **k: 1 / 0)
    link = Simulated()
    link.queue(SetParameter(name="fix_window", value=7.0, by=Box("jake")))
    raised = _session(_spec(tmp_path / "raised", trials=3), link=link)
    raised.run()
    monkeypatch.undo()

    def refused(record, **row):
        raise OSError("disk full")

    monkeypatch.setattr(SessionRecord, "warning", refused)
    link = Simulated()
    link.queue(SetParameter(name="fix_window", value=7.0, by=Box("jake")))
    unwritten = _session(_spec(tmp_path / "unwritten", trials=3), link=link)
    unwritten.run()

    for session, said in ((raised, "could not be run again with the range widened (ZeroDivisionError"),
                          (unwritten, "its warning could not be recorded (OSError: disk full)")):
        assert session.stop_kind == "completed"
        (refusal,) = session.refusals
        assert said in refusal[2] and session.spec.values["fix_window"] == VALUES["fix_window"]

```

- [ ] **Step 2: Run them and see them fail**

Run: `$PY -m pytest -q -p no:cacheprovider tests/test_taskd.py`
Expected: `5 failed, 250 passed`: each live value outside its range refused with the old "is declared over … and … is outside it"; the third test also on `wl_xcon.taskd` having no `beyond_range` to replace.

- [ ] **Step 3: Implement**

**`wl_xcon/taskd.py`** (4 replacements, in order):

Replace:

```python
from wl_xcon.bounds import Bounds, Exceeded, _finite
from wl_xcon.check import check_task
```

with:

```python
from wl_xcon.bounds import Bounds, Exceeded, _finite
from wl_xcon.check import beyond_range, check_task
```

Replace:

```python
from wl_xcon.task import Entered, Exited, Outcome, Param, SaccadeTo, Task, Trial
from wl_xcon.warnlist import PAUSE_UNMARKED, Entry, sentence
```

with:

```python
from wl_xcon.task import Entered, Exited, Outcome, Param, SaccadeTo, Task, Trial
from wl_xcon.warnlist import PAUSE_UNMARKED, Entry, of_findings, sentence
```

Replace:

```python
        `bounds.validate` against its ceiling, and an ordinary one against the task's
        own `Param` declaration. Reward volume is in the first, which is why the
        console can adjust it and cannot exceed it. Both then go on `_staged` and
```

with:

```python
        `bounds.validate` against its ceiling, and an ordinary one against the task's
        own `Param` declaration -- outside its range, by the load-time checks run again
        with the range widened to it, refused only for what breaks the run and otherwise
        accepted with its warnings (`_beyond_range`; the PI, 2026-10-11, XC-352's D2).
        Reward volume is in the first, which is why the console can adjust it and cannot
        exceed it; the first's branch is unchanged by D2. Both then go on `_staged` and
```

Replace:

```python
            if (low is not None and value < low) or (high is not None and value > high):
                raise Exceeded(
                    f"{name!r} is declared over [{low}, {high}] {declared.unit} and "
                    f"{value} is outside it"
                )
        self._staged.append((name, self.spec.values.get(name), value, by, False))

```

with:

```python
            if (low is not None and value < low) or (high is not None and value > high):
                # Outside its declared range (the PI, 2026-10-11, XC-352's D2): the load-time
                # checks run again with the range widened to it, refusing only what breaks the
                # run and otherwise accepting its warnings (`_beyond_range`).
                self._beyond_range(name, value, by)
        self._staged.append((name, self.spec.values.get(name), value, by, False))

    def _beyond_range(self, name: str, value: float, by: Actor) -> None:
        """**A live value outside its setting's declared range** (the PI, 2026-10-11, XC-352's D2:
        "re-run the load-time checks with the range widened to the new value; accept with a
        warning that the task was not designed for it if nothing breaks; refuse only what would
        break the run (off screen, windows colliding, colors unmakeable), saying what"). The run's
        task, checked again with each range widened to the values outside it -- the session's,
        those staged and this one (`check.beyond_range`) -- in the session's setup, calibration
        and deployment. **Refused**, as `Exceeded` saying what breaks, when a finding refuses this
        session's kind; otherwise its warnings are accepted by `by` (`warnings.jsonl`, once each)
        and said on the changes feed, and `set` stages the value. **Nothing but `Exceeded` leaves
        here** (`_command` catches it alone): a check that raises, or a warning that cannot be
        written, refuses the value. Run between trials, as the command is drained, never in a
        frame. Not welfare-critical: `set` calls it only for a task's own setting, never a
        ceiling."""
        values = {**self.spec.values,
                  **{n: now for n, _, now, _, bounded in self._staged if not bounded},
                  name: value}
        try:
            found = beyond_range(self._task, values, self.allocation,
                                 geometry=self.spec.geometry, calibration=self.spec.calibration,
                                 deployment=self.spec.deployment)
        except Exception as broken:  # noqa: BLE001 -- see the docstring
            raise Exceeded(
                f"{name!r} at {value:g} is outside its declared range, and the load-time checks "
                f"could not be run again with the range widened ({type(broken).__name__}: "
                f"{broken}), so it is refused and the previous value stands"
            ) from broken
        refusing = [f for f in found if f.refuses(self.spec.session_kind)]
        if refusing:
            raise Exceeded(
                f"{name!r} at {value:g} is outside its declared range, and with the range widened "
                f"to it the load-time checks refuse it: "
                + "; ".join(f"{f.code}: {f.detail}" for f in refusing)
                + "; the previous value stands"
            )
        entries = of_findings(found)
        new = [entry for entry in entries if entry.key not in self._warnings]
        try:
            self.accept(entries, by=by, how="set", run=self.run_index)
        except Exception as broken:  # noqa: BLE001 -- see the docstring
            raise Exceeded(
                f"{name!r} at {value:g} is outside its declared range, and its warning could not "
                f"be recorded ({type(broken).__name__}: {broken}), so it is refused and the "
                f"previous value stands"
            ) from broken
        at = self.wall_now()
        for entry in new:
            self._feed("warning", by, at, f"{entry.code}: {entry.detail}")

```

**`wl_xcon/warnlist.py`**:

Replace:

```python

**Not built: a warning appearing during a run** (spec §19.3's pause at the next trial). Nothing
in this build can appear mid-run outside its kinds: the calibration is loaded once, as `wlx
taskd` starts; a calibration's age is accepted in every kind; and the rest are fixed when a run
starts. XC-276 waits on build E, the first that can.
```

with:

```python

**Not built: a warning appearing during a run outside its kinds** (spec §19.3's pause at the
next trial). Nothing in this build can: the calibration is loaded once, as `wlx taskd` starts;
a calibration's age is accepted in every kind; the rest are fixed when a run starts; and the two
that can appear during a run since the PI's rulings on XC-352 (2026-10-11) -- a live value
outside its declared range (`outside-range`, D2) and a pause the allocation cannot mark (D5) --
are accepted in every kind, by whoever set the value or paused, as they happen. XC-276 waits on
build E, the first that can.
```

The docs it changes:

**`docs/design/architecture.md`**:

Replace:

```markdown
parameter alike (M8, item 4), and it sends a ceiling's name to `bounds.validate`, which
is what keeps a reward size set from the page under its approved ceiling (item 3).
```

with:

```markdown
parameter alike (M8, item 4), and it sends a ceiling's name to `bounds.validate`, which
is what keeps a reward size set from the page under its approved ceiling (item 3). **A task's own
setting outside its declared range** is checked again with the range widened to it
(`Session._beyond_range`, not on this list), refused only for what breaks the run and otherwise
staged with its warnings, which are written to `warnings.jsonl` (the PI, 2026-10-11, XC-352's
D2); the ceiling's branch is unchanged, byte for byte.
```

**`docs/backlog.md`** ("Next free" already reads XC-374, from Task 10):

Replace:

```markdown

- **XC-062** Bench the NI PCIe-6343 with NI-DAQmx on Ubuntu 24.04, V2's output latency and V2b's input latency included. — 2026-08-31, [S0 §3.1](superpowers/specs/2026-08-31-S0-hosts-and-hardware-design.md#31-the-bench-test-in-order) — waits on: the card
```

with:

```markdown

- **XC-372** Measure how long a live edit outside its declared range holds the trial boundary that drains it on the rig PC (Session._beyond_range runs the task's load-time checks twice, between trials, never in a frame): no timing claim without a measurement, and the inter-trial interval it lengthens is unmeasured. — 2026-10-11, [warnings-over-refusals plan, call 9](superpowers/plans/2026-10-11-warnings-over-refusals.md#calls-taken-in-this-plan) — waits on: the rig PC
- **XC-062** Bench the NI PCIe-6343 with NI-DAQmx on Ubuntu 24.04, V2's output latency and V2b's input latency included. — 2026-08-31, [S0 §3.1](superpowers/specs/2026-08-31-S0-hosts-and-hardware-design.md#31-the-bench-test-in-order) — waits on: the card
```

- [ ] **Step 4: Run them and see them pass**

Run the file, then the whole suite. Expected: `255 passed`; the suite **3534 passed**.

- [ ] **Step 5: Prove they can fail**

- `set`'s `self._beyond_range(name, value, by)` → `pass`: the five new tests fail.
- `_beyond_range`'s `if refusing:` → `if False:`: `test_a_live_value_that_would_put_the_target_off_screen_is_refused_saying_so` fails.
- Its `self.accept(entries, by=by, how="set", run=self.run_index)` → `pass`: four fail, the live wait test among them.
- Its `self._feed("warning", …)` → `pass`: `test_a_live_value_outside_its_range_applies_with_a_warning_that_the_task_was_not_designed_for_it` fails.
- Its second `except Exception` (the warning's write) → `except KeyError`: two fail (the `RuntimeError` of an unopened record, and the `OSError`, end the session or the call).
- And Task 10's `beyond_range` wait break (`if name in waits and value > longest:` → `if False:`) now fails `test_a_live_wait_longer_than_any_the_task_declares_is_staged_with_its_warnings` too.

- [ ] **Step 6: Commit**

```bash
git add wl_xcon/taskd.py wl_xcon/warnlist.py tests/test_taskd.py docs/design/architecture.md docs/backlog.md
git commit -m "Check a live value outside its declared range widened to it in Session.set's task-setting branch"
```
Body: XC-352's D2 (the PI, 2026-10-11, quoted) and his answer of 2026-10-12 on long waits ("Allow, with a warning"); **`Session.set` is welfare-listed: its ceiling branch is unchanged, byte for byte** (Task 12, Step 7), and its task-setting branch calls `_beyond_range`, which is not listed; call 9 (XC-372 filed); Appendix A, items 1 and 2; the count; the breaks seen failing.

---
### Task 12: The record of it: the audit and his rulings, the decision log, the specs, the backlog, the sweep, welfare byte for byte

**Files:**
- Create: `docs/research/2026-10-11-xc352-refusal-audit.md` (the audit, from the controller's scratchpad, with a dated header and the PI's rulings and answers)
- Modify: `docs/references/decisions.md` (fourteen dated revisions, TRN-07's among them, and TSK-51), `docs/superpowers/specs/2026-10-07-engine-design.md` (§7, §19 items 2 and 3, §20 items 1 and 3), `docs/superpowers/specs/2026-08-31-S8-session-management-design.md` (§3.1), `docs/backlog.md`
- Modify (test): `tests/test_references.py` (no two decisions share a number; the review's M2)

- [ ] **Step 1: The audit and his rulings** -- copy it in, then edit it:

```bash
cp /private/tmp/claude-501/-Users-jakewesterberg-GitHub-wl-xcon/4e9472e4-813d-44dc-a368-91630da8d513/scratchpad/xc352-refusal-audit.md docs/research/2026-10-11-xc352-refusal-audit.md
```

**`docs/research/2026-10-11-xc352-refusal-audit.md`** (2 replacements, in order):

Replace:

```markdown
A read-only audit of `engine-c1` at `2d8717b` (main plus engine build C1). Nothing was changed.

```

with:

```markdown
A read-only audit of `engine-c1` at `2d8717b` (main plus engine build C1). Nothing was changed.

**As of 2026-10-11.** Committed with the build that carries out the PI's rulings on it (below, "The
PI's rulings"; `docs/superpowers/plans/2026-10-11-warnings-over-refusals.md`). Its `file:line`
references were taken at an earlier read of that branch and drift from `2d8717b` by up to about 40
lines in `check.py`, `taskd.py` and `cli.py`; that plan re-read every claim against `2d8717b` and
names functions, not lines.

```

Replace:

```markdown
Summary: 69 rows — keep 48 (welfare 17, record 15, authoring 10, safety 3, no path 3), make it a warning 14, ask the PI 7.

```

with:

```markdown
Summary: 69 rows — keep 48 (welfare 17, record 15, authoring 10, safety 3, no path 3), make it a warning 14, ask the PI 7.

## The PI's rulings, 2026-10-11

His rule, on reviewing engine build C1: "in general, I think you have been too gung ho on refusals. I
think warnings are more appropriate most of the time with an explanation of why it may not be a good
idea to use a value or follow a path you may think to refuse. the experimenter needs free control
most of the time."

- **D2** (a live or starting value outside the task's declared range): re-run the load-time checks
  with the range widened to the new value; accept with a warning that the task was not designed for
  it if nothing breaks; refuse only what would break the run (off screen, windows colliding, colors
  unmakeable), saying what.
- **A21** (recording on the default calibration with any color or light setting): a warning in
  recording too; the record names the default.
- **A19** (isoluminance on the default): a warning everywhere, saying the colors are only nominally
  isoluminant on an unmeasured panel.
- **A20** (a color the panel cannot make): a warning, and the drawer records the light actually shown
  beside the one asked for.
- **D4** (a setting change between runs): keep refusing.
- **C6** (the stereoscope without a settings file): a warning; the nominal 1.6 cm is recorded as
  nominal.
- **C7** (a half-IPD outside 30-38 mm): a warning (outside the drawn optics, extrapolated).
- **The fourteen proposed warnings, all approved**: A7 (review notes only), A8, A9, A10, A11, A12, E1,
  E2, E3, B1, C8, C11, D5, H4.
- **The 48 kept refusals stay.**

## The PI's answers, 2026-10-12

Asked by the plan named below, before its build:

- **A value outside its range making a trial wait longer than the task's longest declared wait**:
  "Allow, with a warning". The option he chose read: "Any wait up to the trial cap: about 417 s
  today, 5 minutes once C2a is built. The warning says Stop, Pause and the out-of-cage limit go
  unheard until that trial ends."
- **TRN-07** ("pause, stop, resume and manual reward never need sign-in"), against the https page,
  which refuses them without one: at the rig PC only. His choice read: "No sign-in at the rig PC's
  own console. From another computer, sign-in is required, as built now, so nobody on the network
  can stop a session or give a reward unseen. The decision log's wording is clarified."

How each was built, and the calls taken in building them: the plan named above. Of "Found on the
way", the head-fixed default is fixed by XC-355 (the deployment fix, merged before that build); a
warning longer than 500 characters at an open is answered by bounding every warning an open lists
within it (E1's quoted refusal is cut in its middle); the TRN-07 wording is answered above.

```

- [ ] **Step 2: The decision log** (`docs/references/decisions.md`) -- each revision a `- **Revised:**` line after its entry's last line, quoting the PI, and TSK-51 after TSK-50; and a test that no two decisions share a number (the review's M2: this build and build C2a both drafted TSK-51; this build keeps it, and C2a renumbers):

**`docs/references/decisions.md`** (15 replacements, in order):

Replace:

```markdown
- **Basis:** PI decision, 2026-10-07. What "standard sRGB" means: [@stokes1996standard] — primaries R (0.64, 0.33), G (0.30, 0.60), B (0.15, 0.06), D65 white (0.3127, 0.3290), the piecewise transfer (a linear segment of slope 12.92 at or below 0.00304, otherwise 1.055·x^(1/2.4) − 0.055) and a reference display luminance of 80 cd/m² (Part 2, "Definition of the sRGB color space": Tables 0.1 and 0.2, Eqs. 1.2a-b). That breakpoint is the 1996 draft's: the page notes that "During standardization, a small numerical error caused by rounding error was corrected", and 0.0031308 is IEC 61966-2-1's corrected value (not opened: UNVERIFIED). The page marks itself obsolete and superseded by [@iec1999multimedia], the standard that defines sRGB (its description page read; its text not opened). Why the panel's conformance is a warning and not an assumption: [@abuhaila2025recent] — three consumer displays calibrated to γ = 2.2 fitted γ 1.98-2.30 across channels afterwards, grayscale 2.01-2.29 (Results, "Linearity and gamma function", Table 3), and performance "cannot be assumed or guaranteed" across units of one model (Discussion, "Caveats and limitations").

```

with:

```markdown
- **Basis:** PI decision, 2026-10-07. What "standard sRGB" means: [@stokes1996standard] — primaries R (0.64, 0.33), G (0.30, 0.60), B (0.15, 0.06), D65 white (0.3127, 0.3290), the piecewise transfer (a linear segment of slope 12.92 at or below 0.00304, otherwise 1.055·x^(1/2.4) − 0.055) and a reference display luminance of 80 cd/m² (Part 2, "Definition of the sRGB color space": Tables 0.1 and 0.2, Eqs. 1.2a-b). That breakpoint is the 1996 draft's: the page notes that "During standardization, a small numerical error caused by rounding error was corrected", and 0.0031308 is IEC 61966-2-1's corrected value (not opened: UNVERIFIED). The page marks itself obsolete and superseded by [@iec1999multimedia], the standard that defines sRGB (its description page read; its text not opened). Why the panel's conformance is a warning and not an assumption: [@abuhaila2025recent] — three consumer displays calibrated to γ = 2.2 fitted γ 1.98-2.30 across channels afterwards, grayscale 2.01-2.29 (Results, "Linearity and gamma function", Table 3), and performance "cannot be assumed or guaranteed" across units of one model (Discussion, "Caveats and limitations").
- **Revised:** 2026-10-11, the PI, on [the XC-352 audit](../research/2026-10-11-xc352-refusal-audit.md) (E1, approving the proposed warning; his rule "in general, I think you have been too gung ho on refusals. I think warnings are more appropriate most of the time with an explanation of why it may not be a good idea to use a value or follow a path you may think to refuse. the experimenter needs free control most of the time."): a calibration record the rig names that will not load puts the default in its place, with a warning in every session kind saying why, which an open asks to accept; until then no kind accepted it and every run failed on it (the engine B plan, call 19). Built by [the warnings-over-refusals build](../superpowers/plans/2026-10-11-warnings-over-refusals.md), Task 6.

```

Replace:

```markdown
- **Basis:** PI decision, 2026-10-07 and 2026-10-08. Supporting its premise, that stimulus values are known only for a characterized display: [@brainard2002display] — accurate rendering means choosing digital values from the measured primary spectra and the measured gamma functions of the display in use (pp. 177-179, "Characterization using the standard CRT model"); [@abuhaila2025recent] — performance depends on the monitor's settings and firmware (abstract) and cannot be assumed across units of one model (Discussion, "Caveats and limitations").

```

with:

```markdown
- **Basis:** PI decision, 2026-10-07 and 2026-10-08. Supporting its premise, that stimulus values are known only for a characterized display: [@brainard2002display] — accurate rendering means choosing digital values from the measured primary spectra and the measured gamma functions of the display in use (pp. 177-179, "Characterization using the standard CRT model"); [@abuhaila2025recent] — performance depends on the monitor's settings and firmware (abstract) and cannot be assumed across units of one model (Discussion, "Caveats and limitations").
- **Revised:** 2026-10-11, the PI, on [the XC-352 audit](../research/2026-10-11-xc352-refusal-audit.md) (A21): "a warning in recording too"; the record names the default. A task that names a color, or whose settings set a light, a contrast or an opacity, runs on the default in every session kind with `color-on-default` or `contrast-on-default`, each saying that every color or luminance in the data is nominal and that the session's config.json names the default. The heading and the lines above record the refusal as decided on 2026-10-07 and widened on 2026-10-08. Built by [the warnings-over-refusals build](../superpowers/plans/2026-10-11-warnings-over-refusals.md), Task 4.

```

Replace:

```markdown
- **Caveat:** Isoluminance here is the CIE 10° standard observer's (V_F,10), not the animal's. Macaque red-green equiluminance points differ from humans' and between animals, consistent with L:M ratios near 1:1 against 2:1 [@dobkins2000comparison]; monkeys are more sensitive than humans to 15 Hz red-green isoluminant modulation in a way optics do not explain [@lindbloombrown2014spectral]; the macaque luminance plane differs from the human definition [@horwitz2015what]; if "human and monkey cone fundamentals are indeed substantially different", then "a stimulus that is equiluminant for a human may possess luminance contrast for a monkey" [@conway2014color, section "MT"]; even among 22 young humans, settings against the Stockman–Sharpe 2° observer spanned M:L cone-contrast ratios of −6.1 to −0.7 [@he2021modeling]; per-observer flicker photometry is the published remedy where silencing luminance matters [@brainard2002display, p. 183]. Against them, MT null planes lay close to photometric isoluminance [@gegenfurtner1994chromatic]. A methods section states that the isoluminance is the standard observer's; a result that rests on it (laminar M/P/K mapping, chromatic motion) says so.

```

with:

```markdown
- **Caveat:** Isoluminance here is the CIE 10° standard observer's (V_F,10), not the animal's. Macaque red-green equiluminance points differ from humans' and between animals, consistent with L:M ratios near 1:1 against 2:1 [@dobkins2000comparison]; monkeys are more sensitive than humans to 15 Hz red-green isoluminant modulation in a way optics do not explain [@lindbloombrown2014spectral]; the macaque luminance plane differs from the human definition [@horwitz2015what]; if "human and monkey cone fundamentals are indeed substantially different", then "a stimulus that is equiluminant for a human may possess luminance contrast for a monkey" [@conway2014color, section "MT"]; even among 22 young humans, settings against the Stockman–Sharpe 2° observer spanned M:L cone-contrast ratios of −6.1 to −0.7 [@he2021modeling]; per-observer flicker photometry is the published remedy where silencing luminance matters [@brainard2002display, p. 183]. Against them, MT null planes lay close to photometric isoluminance [@gegenfurtner1994chromatic]. A methods section states that the isoluminance is the standard observer's; a result that rests on it (laminar M/P/K mapping, chromatic motion) says so.
- **Revised:** 2026-10-11, the PI, on [the XC-352 audit](../research/2026-10-11-xc352-refusal-audit.md) (A19): "a warning everywhere", saying the colors are only nominally isoluminant on an unmeasured panel. `isoluminance-on-default` is accepted in every session kind, and the color is still held to the panel's reach; the reference search task's isoluminant red and green, just outside the sRGB standard's gamut (a primary weight of -0.003 to -0.006), run on the default with both warnings. The heading records the decision as first made. Built by [the warnings-over-refusals build](../superpowers/plans/2026-10-11-warnings-over-refusals.md), Tasks 4 and 5.

```

Replace:

```markdown
- **Basis:** PI decision, 2026-10-07. That displays drift, which is why age is tracked: [@brainard2002display] — warm-up of 45-60 min with luminance rising by up to 20%, lifetime decay of CRT phosphors and LCD backlights, and one CRT's cutoff rising by about six levels (of 255) per month (p. 182, "Temporal homogeneity"); [@dimigen2026advantages] — an OLED monitor reached 99% of its asymptotic luminance after 36 min, and its luminance drifted with panel temperature over minutes (Results, "Operating time", "Slow temperature-luminance interactions"); [@spitschan2018method] — device output drifts "need to be either calibrated, or at least characterized" ("Challenges to silent substitution", "Device uncertainty"). The 30-day interval has no published source: none of these, nor a PubMed and web search for OLED aging or recalibration intervals in vision science, gives one; they support tracking age, not 30 days.

```

with:

```markdown
- **Basis:** PI decision, 2026-10-07. That displays drift, which is why age is tracked: [@brainard2002display] — warm-up of 45-60 min with luminance rising by up to 20%, lifetime decay of CRT phosphors and LCD backlights, and one CRT's cutoff rising by about six levels (of 255) per month (p. 182, "Temporal homogeneity"); [@dimigen2026advantages] — an OLED monitor reached 99% of its asymptotic luminance after 36 min, and its luminance drifted with panel temperature over minutes (Results, "Operating time", "Slow temperature-luminance interactions"); [@spitschan2018method] — device output drifts "need to be either calibrated, or at least characterized" ("Challenges to silent substitution", "Device uncertainty"). The 30-day interval has no published source: none of these, nor a PubMed and web search for OLED aging or recalibration intervals in vision science, gives one; they support tracking age, not 30 days.
- **Revised:** 2026-10-11, the PI, on [the XC-352 audit](../research/2026-10-11-xc352-refusal-audit.md) (E2, approving the proposed warning): a calibration dated after today, which no kind accepted (the engine B plan, call 19, engineering), is a warning in every kind that its date or this host's clock is wrong, saying to check the clock. Built by [the warnings-over-refusals build](../superpowers/plans/2026-10-11-warnings-over-refusals.md), Task 6.

```

Replace:

```markdown
- **Basis:** Engineering default on a published method: the weights that produce a light are the measured primaries' inverse times its coordinates, and a weight is a number in [0, 1] [@brainard2002display] (pp. 177-178, Eq. 14; p. 173, Eq. 1). Checking each corner of a parameter's range is exact for a `Gray` background, since the converted weights are bilinear in its luminance and the color's components (arithmetic); for a background whose chromaticity is a range it is corners only (XC-307). Refusing cone colors on a measured calibration without spectra, rather than borrowing the default's matrix, is the plan's call 8, with no paper behind it.

```

with:

```markdown
- **Basis:** Engineering default on a published method: the weights that produce a light are the measured primaries' inverse times its coordinates, and a weight is a number in [0, 1] [@brainard2002display] (pp. 177-178, Eq. 14; p. 173, Eq. 1). Checking each corner of a parameter's range is exact for a `Gray` background, since the converted weights are bilinear in its luminance and the color's components (arithmetic); for a background whose chromaticity is a range it is corners only (XC-307). Refusing cone colors on a measured calibration without spectra, rather than borrowing the default's matrix, is the plan's call 8, with no paper behind it.
- **Revised:** 2026-10-11, the PI, on [the XC-352 audit](../research/2026-10-11-xc352-refusal-audit.md): a light the panel cannot make is a warning, not a refusal (A20: "a warning, and the drawer records the light actually shown beside the one asked for"), naming the light the panel shows, its weights clipped to [0, 1] (`exact.shown`); a light that does not convert at all is still refused. And a measured calibration without spectra converts cone colors as the default does, with a warning (E3, approving the proposed warning; the plan's call 8 had no paper behind it). Built by [the warnings-over-refusals build](../superpowers/plans/2026-10-11-warnings-over-refusals.md), Tasks 5 and 6; recording the light shown per frame waits on engine builds E and F (XC-370).

```

Replace:

```markdown
- **Basis:** Engineering default. A light the panel cannot make is clipped, and a clipped light is neither the color nor the luminance asked for (COL-04, arithmetic); checking a grating at both extremes is the A2 research note's procedure (§3, step 5), a computation, not a paper. Weights in [0, 1]: [@brainard2002display] (p. 173, Eq. 1). What a light over another stimulus is depends on that stimulus, so it is refused at draw time (XC-306).

```

with:

```markdown
- **Basis:** Engineering default. A light the panel cannot make is clipped, and a clipped light is neither the color nor the luminance asked for (COL-04, arithmetic); checking a grating at both extremes is the A2 research note's procedure (§3, step 5), a computation, not a paper. Weights in [0, 1]: [@brainard2002display] (p. 173, Eq. 1). What a light over another stimulus is depends on that stimulus, so it is refused at draw time (XC-306).
- **Revised:** 2026-10-11, the PI, on [the XC-352 audit](../research/2026-10-11-xc352-refusal-audit.md) (A20: "a warning, and the drawer records the light actually shown beside the one asked for"): a contrast's extreme the panel cannot make is a warning naming the light it shows, and the exact drawer clips such a pixel (`exact.output_levels`) and gives the light shown (`exact.shown`) rather than refusing it. Built by [the warnings-over-refusals build](../superpowers/plans/2026-10-11-warnings-over-refusals.md), Task 5.

```

Replace:

```markdown
- **Basis:** PI decision (the program's design and the rig's operation); no published basis.

```

with:

```markdown
- **Basis:** PI decision (the program's design and the rig's operation); no published basis.
- **Revised:** 2026-10-11, the PI, on [the XC-352 audit](../research/2026-10-11-xc352-refusal-audit.md) (A12, approving the proposed warning; his rule "in general, I think you have been too gung ho on refusals. I think warnings are more appropriate most of the time with an explanation of why it may not be a good idea to use a value or follow a path you may think to refuse. the experimenter needs free control most of the time."): a task written for one setup runs in the other with a warning saying what that setup changes, unless it shows each eye its own image (a disparity, one eye, a position or a background per eye) in direct view, which stays refused, as stereo content outside the stereoscope is; the field check holds it to the setup it runs in. Built by [the warnings-over-refusals build](../superpowers/plans/2026-10-11-warnings-over-refusals.md), Task 3.

```

Replace:

```markdown
- **Basis:** Engineering (splitting a stereogram's appearance, `RDS` with its `correlation` field, from disparity-defined form, `Corrugation` and `Slant`), on published stimuli. [@julesz1960binocular] — computer-generated stereo pairs "When viewed monocularly … appear completely random, but if viewed binocularly, certain correlated point domains are seen in depth" (abstract, p. 1125): the basis for refusing a one-eye stereogram; and a pair in which one picture is the negative of the other ("all points are complemented") cannot be fused and rivals (pp. 1140–1141, Figs. 15–16; full text, archive.org scan): an anticorrelated stereogram (the paper makes no claim to be the first). [@cumming1997responses] — anticorrelated random-dot stereograms give no depth percept, yet disparity-selective V1 neurons signal their disparity (abstract): why anticorrelation is the control. [@tanabe2004rejection] — the full control set in one macaque design: correlated and anticorrelated RDS at nine disparities (for the first monkey; thirteen for later cells), left-eye-only and right-eye-only presentations, and a binocularly uncorrelated RDS (Materials and Methods, "Electrophysiology"), the anticorrelated one made by reversing dot contrast in one eye only ("Task and visual stimulation"; full text). [@nienborg2004receptive] — RDS "in which disparity varied as a sinusoidal function of vertical position ('corrugations')" in awake macaques (abstract; full text read). [@nguyenkim2003disparitybased] — planar surfaces "depicted by random-dot stereograms containing a linear gradient of horizontal disparities", parameterized by tilt and slant, in macaque MT (abstract; full text read).

```

with:

```markdown
- **Basis:** Engineering (splitting a stereogram's appearance, `RDS` with its `correlation` field, from disparity-defined form, `Corrugation` and `Slant`), on published stimuli. [@julesz1960binocular] — computer-generated stereo pairs "When viewed monocularly … appear completely random, but if viewed binocularly, certain correlated point domains are seen in depth" (abstract, p. 1125): the basis for refusing a one-eye stereogram; and a pair in which one picture is the negative of the other ("all points are complemented") cannot be fused and rivals (pp. 1140–1141, Figs. 15–16; full text, archive.org scan): an anticorrelated stereogram (the paper makes no claim to be the first). [@cumming1997responses] — anticorrelated random-dot stereograms give no depth percept, yet disparity-selective V1 neurons signal their disparity (abstract): why anticorrelation is the control. [@tanabe2004rejection] — the full control set in one macaque design: correlated and anticorrelated RDS at nine disparities (for the first monkey; thirteen for later cells), left-eye-only and right-eye-only presentations, and a binocularly uncorrelated RDS (Materials and Methods, "Electrophysiology"), the anticorrelated one made by reversing dot contrast in one eye only ("Task and visual stimulation"; full text). [@nienborg2004receptive] — RDS "in which disparity varied as a sinusoidal function of vertical position ('corrugations')" in awake macaques (abstract; full text read). [@nguyenkim2003disparitybased] — planar surfaces "depicted by random-dot stereograms containing a linear gradient of horizontal disparities", parameterized by tilt and slant, in macaque MT (abstract; full text read).
- **Revised:** 2026-10-11, the PI, on [the XC-352 audit](../research/2026-10-11-xc352-refusal-audit.md) (A11, approving the proposed warning): a stereogram shown to one eye is a warning that its trials are not a disparity condition and are not to be analyzed as one, never a refusal. The heading records the refusal as first decided. Built by [the warnings-over-refusals build](../superpowers/plans/2026-10-11-warnings-over-refusals.md), Task 3.

```

Replace:

```markdown
- **Basis:** PI decision; per-animal measurement is published practice and the range can be checked against published values. [@walton2019rhesus] — "the small interpupillary distance in rhesus monkeys (typically 25–35 mm)" (Methods, "Data Analysis"; stated without a source) and "We measured the interpupillary distances of both monkeys to be approximately 34 mm" (Results, "Fixation of a Full Field Near Target"; full text). [@hadjidimitrakis2011fix] — "The interocular distance of the monkeys M1 and M2 was 35 mm and 32 mm" (Materials and Methods, "Behavioral task"; full text). [@ferrea2025frontal] — "the interpupillary distance of the monkeys was measured (Monkey Y = 33.2 mm, Monkey Z = 33.1 mm). The setup software and screen projections were then calibrated to these individual values" (Materials and methods, "Stereoscopic 3D virtual reality setup"; full text). [@wirth2017gazeinformed] — disparity calibrated "using the actual interpupillary distance of the monkeys (3.1 cm for monkey K and 3.0 cm for monkey S)" (Materials and methods, "Behavioral methods and setup"; full text). [@cumming1999binocular] — convergence of 2.25° and 2.32° at 89 cm (Materials and Methods; full text), which implies IPDs of about 35 and 36 mm (our arithmetic). Ten animals in these sources span about 30–36 mm.

```

with:

```markdown
- **Basis:** PI decision; per-animal measurement is published practice and the range can be checked against published values. [@walton2019rhesus] — "the small interpupillary distance in rhesus monkeys (typically 25–35 mm)" (Methods, "Data Analysis"; stated without a source) and "We measured the interpupillary distances of both monkeys to be approximately 34 mm" (Results, "Fixation of a Full Field Near Target"; full text). [@hadjidimitrakis2011fix] — "The interocular distance of the monkeys M1 and M2 was 35 mm and 32 mm" (Materials and Methods, "Behavioral task"; full text). [@ferrea2025frontal] — "the interpupillary distance of the monkeys was measured (Monkey Y = 33.2 mm, Monkey Z = 33.1 mm). The setup software and screen projections were then calibrated to these individual values" (Materials and methods, "Stereoscopic 3D virtual reality setup"; full text). [@wirth2017gazeinformed] — disparity calibrated "using the actual interpupillary distance of the monkeys (3.1 cm for monkey K and 3.0 cm for monkey S)" (Materials and methods, "Behavioral methods and setup"; full text). [@cumming1999binocular] — convergence of 2.25° and 2.32° at 89 cm (Materials and Methods; full text), which implies IPDs of about 35 and 36 mm (our arithmetic). Ten animals in these sources span about 30–36 mm.
- **Revised:** 2026-10-11, the PI, on [the XC-352 audit](../research/2026-10-11-xc352-refusal-audit.md): an animal with no settings file runs on the stereoscope at the nominal half-IPD, 1.6 cm, with a warning (C6: "a warning; the nominal 1.6 cm is recorded as nominal": config.json's `setup.half_ipd_nominal`); a half-IPD outside 30-38 mm IPD runs with a warning that the optics are extrapolated there, not drawn (C7, "a warning"); and another animal's settings file runs with a warning naming whose half-IPD the session uses (C8, approving the proposed warning); settings given in direct view are a warning that they are ignored (H4). Each was refused until then; a half-IPD that leaves no positive optical path is still refused, having no field. The heading records the refusal as first decided. Built by [the warnings-over-refusals build](../superpowers/plans/2026-10-11-warnings-over-refusals.md), Task 7.

```

Replace:

```markdown
- **Basis:** Engineering default, on published findings. [@gantz2020synchronization] — heterophoria is the deviation of the eyes' axes without fusion, revealed by covering one eye or by showing the eyes elements that cannot be fused (Introduction); the covered eye moves to its heterophoric position (Results, Fig. 4), which in 30 normally sighted adults ranged from 14Δ exophoria to 4Δ esophoria (abstract). [@svede2015monocular] — under monocular viewing the vergence state is the heterophoria (abstract). Macaque: [@pirdankar2016influence] — in a normal monkey the covered eye was nearly as stable as the viewing eye (mean BCEA difference 0.03 deg², Results; covered-eye BCEA 0.20 deg², Fig. 3 legend). The rule stands; its stated reason, that the non-viewing eye "drifts", was corrected on 2026-10-08: it deviates to its phoria, and in a normal macaque stays nearly as stable as the viewing eye.

```

with:

```markdown
- **Basis:** Engineering default, on published findings. [@gantz2020synchronization] — heterophoria is the deviation of the eyes' axes without fusion, revealed by covering one eye or by showing the eyes elements that cannot be fused (Introduction); the covered eye moves to its heterophoric position (Results, Fig. 4), which in 30 normally sighted adults ranged from 14Δ exophoria to 4Δ esophoria (abstract). [@svede2015monocular] — under monocular viewing the vergence state is the heterophoria (abstract). Macaque: [@pirdankar2016influence] — in a normal monkey the covered eye was nearly as stable as the viewing eye (mean BCEA difference 0.03 deg², Results; covered-eye BCEA 0.20 deg², Fig. 3 legend). The rule stands; its stated reason, that the non-viewing eye "drifts", was corrected on 2026-10-08: it deviates to its phoria, and in a normal macaque stays nearly as stable as the viewing eye.
- **Revised:** 2026-10-11, the PI, on [the XC-352 audit](../research/2026-10-11-xc352-refusal-audit.md) (A10, approving the proposed warning): a window scoring the eye its stimulus is not shown to is a warning that the animal can do the task with the seeing eye and fail every trial, never a refusal; an eye that is not left, right or both is still refused. Built by [the warnings-over-refusals build](../superpowers/plans/2026-10-11-warnings-over-refusals.md), Task 3.

```

Replace:

```markdown
- **Revised:** 2026-10-11, settings renamed (TRN-13), by the PI: `item_window` is `object_window`, `array_phase` is `array_rotation` and the ring's `eccentricity` is `array_eccentricity`, and an array's members are objects, not items; the lines above keep the names they were decided under.

```

with:

```markdown
- **Revised:** 2026-10-11, settings renamed (TRN-13), by the PI: `item_window` is `object_window`, `array_phase` is `array_rotation` and the ring's `eccentricity` is `array_eccentricity`, and an array's members are objects, not items; the lines above keep the names they were decided under.
- **Revised:** 2026-10-11, the PI, on [the XC-352 audit](../research/2026-10-11-xc352-refusal-audit.md) (A9, approving the proposed warning): object windows that can overlap at the declared extremes are a warning that a saccade to one can be scored as its neighbor, never a refusal; a console value outside the declared range that newly crowds them is refused (D2). Built by [the warnings-over-refusals build](../superpowers/plans/2026-10-11-warnings-over-refusals.md), Tasks 3 and 10.

```

Replace:

```markdown
- **Basis:** PI decision; operational, with no published basis (searched 2026-10-08 only for analogues in MonkeyLogic's documentation).

```

with:

```markdown
- **Basis:** PI decision; operational, with no published basis (searched 2026-10-08 only for analogues in MonkeyLogic's documentation).
- **Revised:** 2026-10-11, the PI, on [the XC-352 audit](../research/2026-10-11-xc352-refusal-audit.md): since his rulings no warning the rig lists is outside any session kind (the default calibration's colors are accepted in recording too, COL-02; a calibration that will not load or is dated after today in every kind, COL-01 and COL-21); two can appear during a run, each accepted as it happens by whoever caused it -- a live value outside its declared range (TSK-51) and a pause the allocation cannot mark (REC-12) -- and a run's pre-flight shows each owed warning whole before it is accepted (XC-353). Built by [the warnings-over-refusals build](../superpowers/plans/2026-10-11-warnings-over-refusals.md).

```

Replace:

```markdown
- **Basis:** PI decision, 2026-10-11; engineering default for the shape. wl-xtasks holds no code (its `wl.yaml`, read 2026-10-11: "The repository holds no code yet", its tasks "written in wl-xcon's task-definition format"), and had not replied to the ask of 2026-10-11 when the plan was written (its `origin/main` at `0486476`, the delivery itself).

```

with:

```markdown
- **Basis:** PI decision, 2026-10-11; engineering default for the shape. wl-xtasks holds no code (its `wl.yaml`, read 2026-10-11: "The repository holds no code yet", its tasks "written in wl-xcon's task-definition format"), and had not replied to the ask of 2026-10-11 when the plan was written (its `origin/main` at `0486476`, the delivery itself).

### TSK-51 — Warnings over refusals: a check an experimenter may reasonably override is a warning saying why it may not be a good idea, accepted and recorded; a refusal is kept where welfare, safety, an authoring rule or an uninterpretable record demands it; a value outside a task's declared range is checked again with the range widened to it and refused only for what breaks the run
- **Decided:** 2026-10-11, the PI: his rule, on reviewing engine build C1 ("in general, I think you have been too gung ho on refusals. I think warnings are more appropriate most of the time with an explanation of why it may not be a good idea to use a value or follow a path you may think to refuse. the experimenter needs free control most of the time."), and his rulings the same day on the audit of every refusal it asked for (XC-352), item by item: the fourteen proposed warnings approved; a value outside its declared range, "re-run the load-time checks with the range widened to the new value; accept with a warning that the task was not designed for it if nothing breaks; refuse only what would break the run (off screen, windows colliding, colors unmakeable), saying what"; a setting change between runs, "keep refusing"; and the 48 kept refusals kept. And on 2026-10-12, asked whether such a value may make a trial wait longer than the task's longest declared wait: "Allow, with a warning" (the option read: "Any wait up to the trial cap: about 417 s today, 5 minutes once C2a is built. The warning says Stop, Pause and the out-of-cage limit go unheard until that trial ends.").
- **Where:** [the audit and his rulings](../research/2026-10-11-xc352-refusal-audit.md); [the warnings-over-refusals plan](../superpowers/plans/2026-10-11-warnings-over-refusals.md); [`wl_xcon/check.py`](../../wl_xcon/check.py) (`beyond_range`, `BREAKS_A_RUN`); [`wl_xcon/warnlist.py`](../../wl_xcon/warnlist.py); COL-01, COL-02, COL-03, COL-21, COL-34, COL-36, DISP-31, STE-10, STE-20, EYE-23, REC-12, TSK-39 and TSK-41's revisions of that day.
- **Basis:** PI decision; operational, with no published basis. Which refusals stay -- welfare 17, record 15, authoring 10, safety 3, no path 3 -- is the audit's classification, which he kept. Reading "windows colliding" and "colors unmakeable" as refusing only what a value outside the declared range newly causes -- an overlap of two windows, a crowded array or a color the panel cannot make that the task as declared does not already give, compared by what each is about (the state and pair of windows, the array, the color), not by its sentence -- while the same findings within the declared ranges, and a value that only enlarges one of them, are warnings (his rulings on A8, A9 and A20), is engineering (the plan's call 3).

```

Replace:

```markdown
- **Basis:** PI decision; no published basis (searched 2026-10-08 for experimenter annotations timestamped and synchronized with neural recordings: only video-scoring tools).

```

with:

```markdown
- **Basis:** PI decision; no published basis (searched 2026-10-08 for experimenter annotations timestamped and synchronized with neural recordings: only video-scoring tools).
- **Revised:** 2026-10-11, the PI, on [the XC-352 audit](../research/2026-10-11-xc352-refusal-audit.md) (D5, approving the proposed warning): a pause the session's allocation cannot mark (no `PAUSE` or no `RESUME` code) is taken, with a warning that the recording shows an unexplained gap and that `controls.jsonl` holds when the pause began and ended, accepted into `warnings.jsonl` by who paused; until then it was refused. Built by [the warnings-over-refusals build](../superpowers/plans/2026-10-11-warnings-over-refusals.md), Task 9.

```

Replace:

```markdown
- **Basis:** PI decision, 2026-10-10.

### TRN-08 — The agent's file names nobody
```

with:

```markdown
- **Basis:** PI decision, 2026-10-10.
- **Revised:** 2026-10-12, the PI, asked by [the warnings-over-refusals plan](../superpowers/plans/2026-10-11-warnings-over-refusals.md) (the [XC-352 audit](../research/2026-10-11-xc352-refusal-audit.md)'s "Found on the way": the https page refuses pause, stop, resume and manual reward without a sign-in), chose: "No sign-in at the rig PC's own console. From another computer, sign-in is required, as built now, so nobody on the network can stop a session or give a reward unseen. The decision log's wording is clarified." So "never need sign-in" means at the rig PC's own console; from another computer each needs one, as the page is built. The heading keeps the words decided on 2026-10-10.

### TRN-08 — The agent's file names nobody
```

**`tests/test_references.py`**:

Replace:

```python
            if not (DECISIONS.parent / target.partition("#")[0]).resolve().exists():
                missing.append((number, target))
    assert missing == [], missing

```

with:

```python
            if not (DECISIONS.parent / target.partition("#")[0]).resolve().exists():
                missing.append((number, target))
    assert missing == [], missing


#: A decision's number, as its heading opens: an area's letters and a number ("### TSK-51 — ").
DECISION_ID = re.compile(r"^### (?P<id>[A-Z]+-\d+)\b")


def _shared_numbers(text: str) -> list[str]:
    """Each decision number that more than one `### ` heading in `text` opens with, sorted."""
    ids = [found["id"] for line in text.splitlines() if (found := DECISION_ID.match(line))]
    return sorted({number for number in ids if ids.count(number) > 1})


def test_no_two_decisions_share_a_number():
    """A decision is cited by its number (COL-02, TSK-51) in code, plans and the backlog, so two
    entries under one number make every citation of it ambiguous. Two builds planned side by side
    can each take the next free one: the warnings-over-refusals plan and build C2a's both took
    TSK-51 (that plan's review, M2)."""
    assert _shared_numbers("### TSK-51 — one\n### TSK-52 — two\n### TSK-51 — three\n") == ["TSK-51"]
    assert _shared_numbers(DECISIONS.read_text(encoding="utf-8")) == []

```

- [ ] **Step 3: The specs' dated notes**

**`docs/superpowers/specs/2026-10-07-engine-design.md`** (5 replacements, in order):

Replace:

```markdown
"until build A2" (that note stays as written; it was true of its date).
Item 9's 2° set for foveal work is not built (XC-302); the record's second
```

with:

```markdown
"until build A2" (that note stays as written; it was true of its date).

*The PI's rulings on XC-352, 2026-10-11* (`docs/research/2026-10-11-xc352-refusal-audit.md`; built
by `docs/superpowers/plans/2026-10-11-warnings-over-refusals.md`): item 2, on the default a task that names a color or whose
settings set a light is a warning in recording too, the session's config.json naming the default
("a warning in recording too", A21); item 3, isoluminance on the default is "a warning everywhere",
saying the colors are only nominally isoluminant on an unmeasured panel (A19); item 4, a light the
panel cannot make is a warning naming the light it shows, the exact drawer clipping it and giving
the light shown ("a warning, and the drawer records the light actually shown beside the one asked
for", A20; recording it per frame waits on builds E and F, XC-370); A2's "a record without them
converts none": a measured calibration without spectra converts cone colors as the default does,
with a warning (E3); build B's record that will not load: the default stands in for it, with a
warning (E1); item 10, a calibration dated after today is a warning in every kind (E2). The search
task's isoluminant red and green, just outside the sRGB standard's gamut, run on the default with
both warnings.
Item 9's 2° set for foveal work is not built (XC-302); the record's second
```

Replace:

```markdown
   unknowns; the others wait on the builds that make them (`wl_xcon/warnlist.py`).
3. **Accepted once per session**, at open, recorded. **A warning appearing during a run that its kinds do
```

with:

```markdown
   unknowns; the others wait on the builds that make them (`wl_xcon/warnlist.py`).
   *The PI's rulings on XC-352, 2026-10-11*: a calibration that will not load, in whose place the
   default runs, and one dated after today are warnings every kind accepts (E1, E2); a stereoscope's
   setup -- the nominal half-IPD with no settings file, another animal's settings, a half-IPD
   outside the drawn optics -- and settings direct view ignores are listed (C6-C8, H4); a task's
   warnings gain `overlapping-windows`, `crowded-array`, `wrong-eye-criterion`,
   `monocular-stereogram`, `wrong-setup` (without stereo content), `isoluminance-on-default`,
   `unrealizable-color`, `cone-colors-without-spectra` and `outside-range`, and `color-on-default`
   and `contrast-on-default` are accepted in recording. No warning the rig lists refuses any kind.
3. **Accepted once per session**, at open, recorded. **A warning appearing during a run that its kinds do
```

Replace:

```markdown
   mid-run outside its kinds (XC-276, call 8).

```

with:

```markdown
   mid-run outside its kinds (XC-276, call 8).
   *The PI's rulings on XC-352, 2026-10-11*: two warnings can appear during a run, each accepted in
   every kind as it happens by whoever caused it: a live value outside its declared range (D2) and a
   pause the allocation cannot mark (D5); XC-276's pause stays for one outside its kinds. A run's
   pre-flight shows every warning it asks to accept whole (XC-353).

```

Replace:

```markdown
   his rule (XC-352).
2. **`Service._open`**: the session kind; a refusal while the OLED's maintenance is due.
```

with:

```markdown
   his rule (XC-352).
   *The PI's rulings on XC-352, 2026-10-11* (decisions.md TSK-51): fourteen refusals became warnings
   or review notes, seven questions he answered, 48 refusals kept. `preflight.gate` and
   `Service._start` are unchanged, byte for byte, and `Service._open`'s code too; what an open asks
   to accept now includes a calibration that will not load or is dated after today (E1, E2).
2. **`Service._open`**: the session kind; a refusal while the OLED's maintenance is due.
```

Replace:

```markdown
   never carry a bounded setting (§17.6).
4. **`Session._ends` and `_hold`**: checked about once a second inside long trials and the continuous
```

with:

```markdown
   never carry a bounded setting (§17.6).
   *The PI's rulings on XC-352, 2026-10-11* (D2): a task's own setting outside its declared range is
   checked again with the range widened to it, refused only for what breaks the run and otherwise
   staged with its warnings; the bounded setting's branch is unchanged, byte for byte. *And his
   answer of 2026-10-12*: such a value that makes a wait longer than any the task declares is
   allowed, "with a warning" that a stop, a pause and the out-of-cage limit go unheard until that
   trial ends, since item 4's once-a-second check inside a trial is not built (XC-373).
4. **`Session._ends` and `_hold`**: checked about once a second inside long trials and the continuous
```

**`docs/superpowers/specs/2026-08-31-S8-session-management-design.md`**:

Replace:

```markdown
code (ADR-0006).

```

with:

```markdown
code (ADR-0006).

*The PI, 2026-10-11 (XC-352's D2; engine build "warnings over refusals")*: the declared range is
what the task was designed for, not a limit. A value outside it, at a run's start or live, is
checked again with the range widened to it, accepted with a warning that the task was not designed
for it, and refused only for what would break the run (off screen, windows colliding, colors
unmakeable), saying what (`check.beyond_range`; decisions.md TSK-51).

```

- [ ] **Step 4: The backlog** (`docs/backlog.md`) -- remove XC-352's line (closed). "Next free ID" already reads **XC-374** (Task 10), and every ID this build files, XC-370 to XC-373, is filed by the task that defers it (Tasks 5, 10 and 11):

**`docs/backlog.md`**:

Replace:

```markdown
- **XC-350** Decide number normalization in a task's content hash before engine build C5's "task revised" compares hashes (low=1 and low=1.0 hash differently), and refuse non-finite parameter bounds (Param accepts a NaN low or an infinite high, check_task passes it, and the hash writes NaN or Infinity). — 2026-10-11, [engine C1 plan, call 11](superpowers/plans/2026-10-11-engine-c1.md#calls-taken-in-this-plan), found by its final review — waits on: engine build C5
- **XC-352** Audit every refusal in the engine against the PI's rule of 2026-10-11 ("in general, I think you have been too gung ho on refusals. I think warnings are more appropriate most of the time with an explanation of why it may not be a good idea to use a value or follow a path you may think to refuse. the experimenter needs free control most of the time."): list each, propose warning or refusal with the reason (refuse only where welfare, safety or an uninterpretable record demands), and put the list to the PI; changes go through their own reviewed build. — 2026-10-11, [engine spec §20, item 1's revision](superpowers/specs/2026-10-07-engine-design.md#20-welfare), the PI's ruling on reviewing engine build C1 — waits on: nothing
```

with:

```markdown
- **XC-350** Decide number normalization in a task's content hash before engine build C5's "task revised" compares hashes (low=1 and low=1.0 hash differently), and refuse non-finite parameter bounds (Param accepts a NaN low or an infinite high, check_task passes it, and the hash writes NaN or Infinity). — 2026-10-11, [engine C1 plan, call 11](superpowers/plans/2026-10-11-engine-c1.md#calls-taken-in-this-plan), found by its final review — waits on: engine build C5
```

- [ ] **Step 5: Run the docs' tests, then the suite.** `$PY -m pytest -q -p no:cacheprovider tests/test_references.py tests/test_backlog.py`: **`53 passed`** (the links to this plan resolve once it is committed at `docs/superpowers/plans/2026-10-11-warnings-over-refusals.md`, as Task 1's Step 0 does). **Prove the new test can fail**: rename TSK-51's heading `### TSK-50 —` (`cp` before, `cmp` after); `test_no_two_decisions_share_a_number` fails, naming TSK-50; restored. The suite: **3535 passed**.

- [ ] **Step 6: The sweep.** As C1 did: **CI's per-push gate** sweeps every function of each module a push changes (`--changed-only --shard k/12`); after the last task, one CI run of the branch against `main` is read **shard by shard** (the per-job API where `gh` truncates; a shard's log counts as read only if it ends with the gate's closing line), every line a real `N failed`, never the job's color. The modules: `check` (`[]`), `preflight`, `service`, `taskd`, `warnlist`, `resume`, `exact`, `photometry`, `geometry`, `cli`, `findings`, `task` and `link` (comment and docstring only). **The full sweep too**: this branch changes `tasks/reference_subject.py`, on which `--changed-only` never escalates, so one `mutation-full` run (`workflow_dispatch`) is read the same way. Each function caught only by `timed out after 300s` or an import error (XC-275's verdicts) is then neutered locally (`tools/mutate.py`'s own `_neuter_source`) with its own test file run alone, and must fail a named test, against a control of the same files unmutated. A survivor gets a test in a fix commit before anything else.

- [ ] **Step 7: Welfare, byte for byte** -- each listed function's source at `BASE` (Task 1, Step 0) and at the branch's tip, compared as text and, where the text differs, as code with its docstrings removed (`ast`; comments are no part of it); and `Session.set`'s ceiling branch on its own:

```bash
cd <worktree> && $PY - "$BASE" <<'EOF'
import ast, copy, subprocess, sys

BASE = sys.argv[1]
LISTED = {
    "wl_xcon/preflight.py": ["gate", "out_of_cage"],
    "wl_xcon/service.py": ["Service._open", "Service._end", "Service._unended",
                           "Service._close_stranded", "Service._start", "_unasked", "_folder_name"],
    "wl_xcon/taskd.py": ["OUTSIDE_A_RUN", "Session._ends", "Session._hold",
                         "Session._manual_reward", "Session.set", "Session._schedule",
                         "Session._command"],
    "wl_xcon/link.py": ["_setting"],
    "wl_xcon/cli.py": ["_settle_departure", "_settle_return"],
}


def named(nodes, name):
    for node in nodes:
        if getattr(node, "name", None) == name:
            return node
        if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == name for t in node.targets):
            return node
    raise LookupError(name)


def node_of(text, dotted):
    node, nodes = None, ast.parse(text).body
    for part in dotted.split("."):
        node = named(nodes, part)
        nodes = getattr(node, "body", [])
    return node


def code_only(node):
    """The node as code: its docstrings removed (comments are no part of the tree)."""
    node = copy.deepcopy(node)
    for n in ast.walk(node):
        body = getattr(n, "body", None)
        if (isinstance(body, list) and body and isinstance(body[0], ast.Expr)
                and isinstance(getattr(body[0], "value", None), ast.Constant)
                and isinstance(body[0].value.value, str)):
            n.body = body[1:] or [ast.Pass()]
    return ast.dump(node, include_attributes=False)


def at(path, rev):
    return subprocess.run(["git", "show", f"{rev}:{path}"], capture_output=True, text=True,
                          check=True).stdout


for path, names in LISTED.items():
    base, tip = at(path, BASE), open(path, encoding="utf-8").read()
    for name in names:
        b, t = node_of(base, name), node_of(tip, name)
        if ast.get_source_segment(base, b) == ast.get_source_segment(tip, t):
            print("same", path, name)
        else:
            print("CODE SAME, TEXT DIFFERS" if code_only(b) == code_only(t) else "DIFFERS", path, name)


def ceiling_branch(text):
    session = named(ast.parse(text).body, "Session")
    branch = named(session.body, "set").body[1]
    assert isinstance(branch, ast.If) and ast.unparse(branch.test) == "name in self.spec.bounds.ceilings"
    return ast.get_source_segment(text, branch)


taskd = at("wl_xcon/taskd.py", BASE), open("wl_xcon/taskd.py", encoding="utf-8").read()
print("Session.set's ceiling branch:", "same" if ceiling_branch(taskd[0]) == ceiling_branch(taskd[1]) else "DIFFERS")
EOF
git diff --stat "$BASE" -- wl_xcon/bounds.py wl_xcon/welfare.py wl_xcon/marks.py wl_xcon/stranded.py
git show "$BASE":wl_xcon/cli.py | grep -c '_marks.depart(session, departure)'; grep -c '_marks.depart(session, departure)' wl_xcon/cli.py
```

Expected, as the scratch build printed at `2d8717b` against its tip: every line `same` but `CODE SAME, TEXT DIFFERS wl_xcon/service.py Service._open` (its docstring and one comment, Task 6) and `DIFFERS wl_xcon/taskd.py Session.set` (its docstring and task-setting branch, Task 11); `Session.set's ceiling branch: same`; the `git diff --stat` prints nothing; both counts `1`. Anything else goes to the PI in plain terms before the merge.

- [ ] **Step 8: CHECKPOINT** -- the controller's entry, "What moved on YYYY-MM-DD: warnings over refusals (XC-352)": what was built, task by task; the PI's rule and his rulings of 2026-10-11, quoted; his two answers of 2026-10-12 (a long wait a warning; TRN-07 at the rig PC), quoted; the calls (3 above all); the search task's clipping found on the way; the sweep read shard by shard; the backlog (XC-353 closed by Task 1 and XC-352 here, XC-306 edited, XC-370 to XC-373 filed, Next free XC-374); the welfare comparison and the PI's answer on Appendix A; and the next build, C2a. The Status table's Load-time checks row gains `outside-range`, `longer-than-declared` and `cone-colors-without-spectra`, and notes which findings are now warnings and which review notes; its Reference tasks row no longer says `visual_search` "runs only on a measured calibration with spectra": it runs on the default and on a measured calibration without spectra, with warnings.

- [ ] **Step 9: Commit** -- `git add docs/ tests/test_references.py && git commit -m "Record the PI's rulings on XC-352: the audit, the decision log, the specs and the backlog (closes XC-352)"` (body: the docs this changes and why; the sweep and the welfare comparison as read).

The whole-branch review (most capable model) follows, then its fix wave, then the merge, which the PI decides once he has approved Appendix A.

---

## Not in this build

- **What waits on later builds**: recording the light the panel showed per frame or per trial (XC-370, builds E and F); the once-a-second in-trial check of stop, pause and the welfare limits (XC-373; WEL-11, engine spec §6.8), whose landing changes `longer-than-declared`'s sentence; a warning appearing during a run outside its kinds (XC-276, build E).
- **Filed, not built**: `wlx run --set`'s values against their ranges (XC-371); how long the widened checks hold a trial boundary (XC-372, a measurement on the rig PC).
- **Kept as they are, by his rulings**: a setting change between runs (D4, "keep refusing"), and the 48 refusals the audit kept, among them every welfare refusal, a stimulus off screen, stereo content outside the stereoscope, an authoring fault, and an incomplete task file.
- **Fixed elsewhere**: the page's New-session dialog preselecting head-fixed, which the audit found on the way (XC-355, the deployment fix, merged before this branch is cut).

## Self-review

- **The source, item by item.** His rule: the header, the decisions section, TSK-51. D2: Tasks 10 and 11, calls 3, 4 and 9, Appendix A items 1-2, TSK-51, S8's note. A21 and A19: Task 4, COL-02, COL-03, P19. A20: Task 5, call 5, COL-34, COL-36, XC-370, XC-306. D4: kept, unchanged ("Not in this build"). C6, C7: Task 7, calls 7 and 8, STE-20. The fourteen: A7 Task 2; A8-A12 Task 3 (DISP-31, STE-10, EYE-23, TSK-39, P20); E1-E3 Task 6 (COL-01, COL-21, COL-34; Appendix A item 3); B1 Task 1; C8 and H4 Task 7 (Appendix A item 4); C11 Task 8; D5 Task 9 (REC-12). The 48: no task touches them; Task 12, Step 7 compares the welfare ones. XC-353: Task 1. The audit's "Found on the way": the head-fixed default (XC-355, the deployment fix), the 500-character open (call 6, Task 6's test), TRN-07 (answered, Task 12). **His answers of 2026-10-12**: the long wait, call 4, Tasks 10 and 11, Appendix A item 2, TSK-51, the engine spec's §20 note, XC-373; TRN-07, Task 12.
- **The review, item by item** (each as the controller ruled): I1 Task 8 (`SessionRecord.warning`, call 11); I2 Task 8 (`Service._resume`, call 18); I3 Appendix A item 4 and "What the PI should know" item 7; I4 call 4, worded per wait, by his answer; I5 Task 10 (`Finding.subjects`, call 3, TSK-51's basis, the `fix_window=5.2` case); I6 the header, Tasks 5, 10, 11 and 12 (XC-370 to XC-373, "Next free" replaced whatever it reads); I7 Task 7's assertion and break; M1 Task 1's Step 0; M2 Task 12's test (TSK-51 kept); M3 the six lines rewrapped (no added product line passes 100 columns); M4 Task 6; M5 Task 8; M6 "What the PI should know" item 13; M7 kept; M8 Tasks 4 and 5 and the search task's comment; M9 Task 2's break.
- **Welfare.** Every listed function is named in Appendix A or shown unchanged by Step 7; no welfare limit is softened: the ceiling branch, `bounds`, `welfare` and every listed function but two are unchanged, `_open`'s code is unchanged though what it refuses through `_build` narrows (Appendix A item 4), and a long wait is a warning that says what goes unheard until the trial ends, by the PI's answer, while the trial cap still ends every trial.
- **Names used before they are defined**: none. `SESSION_KINDS` is in `check.py` already; `_per_eye_content` (Task 3) is used in Task 3; `exact.shown` and `Finding.subjects` (Task 5) are used by `check._clipped` and `_clips` (Task 5), and `subjects` by `beyond_range` (Task 10); `warnlist.of_setup` and `of_ignored_settings` (Task 7) by `cli` and `service` (Task 7); `SessionSpec.setup_warnings` (Task 7) by `Service._resume` (Task 8); `warnlist.of_changed_calibration` (Task 8) by `Service._resume` (Task 8); `PAUSE_UNMARKED` (Task 9) by `taskd` (Task 9); `check.beyond_range` (Task 10) by `preflight` (Task 10) and `taskd` (Task 11).
- **Each task leaves the suite green**, as run: the counts in the header, the edit blocks replayed onto a fresh `2d8717b` with this plan committed.
- **The hot path**: nothing new in a frame; `beyond_range` runs at a run's start and at the trial boundary that drains a live edit (XC-372 to measure); `SessionRecord.warning`'s read of its file's last byte runs as a warning is accepted, never in a frame.
- **External facts**: none new. The optics drawing's nominal `E` of 1.6 cm (its §1, read 2026-10-11) and the sRGB standard's 80 cd/m² white are the repository's own; 100,000 frames at 240 Hz is arithmetic.
- **Placeholders**: `YYYY-MM-DD` is the day Step 8 runs; `BASE` is the hash Task 1, Step 0 records; `<worktree>` is the build worktree. No other.

---

## Appendix A: Welfare summary items

For the PI's numbered approval before the build merges. **Nothing about a reward size, the out-of-cage limit, the daily fluid floor, a bounded setting's ceiling, a departure or a return changes**, and no function on architecture.md's welfare-critical list changes but the two named here. Task 12, Step 7 compares each byte for byte: `bounds.py`, `welfare.py`, `marks.py` and `stranded.py` whole; `preflight.gate` and `out_of_cage`; `Service._end`, `_unended`, `_close_stranded`, `_start`, `_unasked`, `_folder_name`; `taskd.Session._ends`, `_hold`, `_manual_reward`, `_schedule`, `OUTSIDE_A_RUN` and `_command` whole; `link._setting`; `cli._settle_departure`, `_settle_return` and `main`'s `_marks.depart(session, departure)` line: all unchanged.

1. **`Session.set` (listed) changes in its task-setting branch only** (Task 11; XC-352's D2). A value for one of a task's own settings that is outside its declared range is no longer refused for that alone: the task's checks are run again with the range widened to it, and it is refused only for what would break the run -- off screen, or windows colliding, an array crowding or a color the panel cannot make where the declared ranges did not already allow it -- saying what; otherwise it is staged with its warnings (a value that only enlarges an overlap or a clip the task was accepted with among them, and a long wait, item 2), which are written to `warnings.jsonl` as accepted by the person who sent it, and applies at the next trial boundary like any edit. **The branch for a bounded setting -- a reward size, sent to `bounds.validate` against its ceiling -- is unchanged, byte for byte** (Step 7 compares it on its own). Its two type guards are unchanged. The new work is in `Session._beyond_range`, which is not on the list.
2. **A wait longer than any the task declares is a warning; nothing is refused for it** (Tasks 10 and 11, call 4; not in a listed function). You answered on 2026-10-12: **"Allow, with a warning"** ("Any wait up to the trial cap: about 417 s today, 5 minutes once C2a is built. The warning says Stop, Pause and the out-of-cage limit go unheard until that trial ends."). A stop, a pause and the out-of-cage limit are checked between trials, not inside one, until the once-a-second check of WEL-11 is built (filed, XC-373). A value outside its range that makes a wait longer than the task's longest declared wait (10 s in the detection task) is accepted, at a run's start or live, with a warning per wait naming the wait and its length, saying stop, pause and the out-of-cage limit go unheard until that trial ends, and naming the trial cap that ends any trial at the latest (100,000 frames, about 417 s at 240 Hz, computed; five minutes once C2a is built). A trial waiting on several such waits in turn can last their sum, up to the cap. `_hold`, `_ends` and the trial cap are unchanged.
3. **`Service._open` (listed): its code is unchanged; its docstring and one comment are reworded, and what it asks to accept grows** (Task 6; XC-352's E1 and E2). A calibration record that will not load, or one dated after today, was a warning no session kind accepted: an open never offered it, and every run's pre-flight failed on it. It is now a warning every kind accepts, so an open lists it with the rig's other warnings and opens only once each is accepted (refused, with nothing recorded, until then, as for any warning an open lists); the session then runs on the default calibration. `preflight.gate` and `Service._start` are unchanged.
4. **`Service._open` (listed): its code is unchanged, and what it refuses through the build it shares narrows** (Task 7; XC-352's C6, C7 and C8; the review's I3). `_open` builds its session through `_built` and `Service._build`, neither on the list (`_built` was reviewed with `_open` in XC-026's summary). Since this build `_build` builds a stereoscope session for an animal with no settings file (on the nominal half-IPD, 1.6 cm, recorded as nominal), with another animal's settings, or with a half-IPD outside the drawn optics; each of these opens was refused before, and each now goes ahead and marks the departure, its warning asked at the first run's pre-flight, where a run starts only once it is accepted. A half-IPD that leaves no positive optical path is still refused, at the open.
5. **For information, outside the list** (each reviewed as ordinary code): a pause on an allocation without PAUSE or RESUME codes now holds, with a warning (Task 9); `_hold`, which asks the out-of-cage limit on every paused pass, is unchanged. A stranded session whose `warnings.jsonl` has a damaged row can now be resumed (Task 8), and a warning accepted after a torn row is written on a line of its own; a session resumed on another calibration than it opened on is a warning its first run asks to accept (Task 8). `resume.py`, `Session.resume` and `Service._resume` are off the list (your ruling of 2026-10-02, "None of them"), and the departure, fluid, bounds and limit a resume restores are read and checked exactly as before.
