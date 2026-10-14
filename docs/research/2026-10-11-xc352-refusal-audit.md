# XC-352: every refusal in the engine, against the PI's rule of 2026-10-11

A read-only audit of `engine-c1` at `2d8717b` (main plus engine build C1). Nothing was changed.

**As of 2026-10-11.** Committed with the build that carries out the PI's rulings on it (below, "The
PI's rulings"; `docs/superpowers/plans/2026-10-11-warnings-over-refusals.md`). Its `file:line`
references were taken at an earlier read of that branch and drift from `2d8717b` by up to about 40
lines in `check.py`, `taskd.py` and `cli.py`; that plan re-read every claim against `2d8717b` and
names functions, not lines.

**The rule** (the PI, 2026-10-11): "warnings are more appropriate most of the time with an explanation of why it may not be a good idea to use a value or follow a path you may think to refuse. the experimenter needs free control most of the time." Incomplete task files stay refused, by his choice, and `head-not-fixed` is already a warning in every kind.

**How a finding refuses.** A blocking `check.check_task` finding fails the pre-flight's `task checks` item (preflight.py:110), and `gate` then blocks. It is refused again by `Session.run`'s backstop (taskd.py:2089) and by `wlx run` (cli.py:1656). A warning outside its kinds fails the `warnings` item (preflight.py:154) and the same backstops. So one row covers all three paths. "Listed" means on architecture.md's welfare-critical list.

**Classes:** Keep: welfare / safety / authoring / record (the record would be uninterpretable) / no path (nothing to act on, or the warning mechanism itself); **Warn** (with the sentence the warning would give); **Ask** (with both sides).

## 1. Load-time findings (`check.py`; blocking in every kind unless noted)

| # | Codes (line) | What is refused | Decided by | Proposal |
|---|---|---|---|---|
| A1 | `undeclared-meaning`, `override-without-why`, `bad-meaning` (:159); `no-reaction-time`, `bad-reaction-time` (:211); `undeclared-choice`, `bad-choice` (:244) | Declarations missing or contradicted | PI: TRN-03, TRN-09, XC-288 §4.3; kept 2026-10-11 | Keep: authoring |
| A2 | `parameter-mismatch`, `view-mismatch` (:131) | Structures disagreeing on a setting or a setup | Engineering (C1) | Keep: authoring |
| A3 | `unhashable-task` (:279) | Content that cannot be hashed | PI, REC-24 | Keep: record (no task version) |
| A4 | `unbounded-wait`, `no-outcome-path`, `undeclared-parameter`, `undeclared-window`, `uncoupled-window`, `unresolved-custom-component`, `unknown-eye`, `unknown-view`, `bad-periphery` | A state that can wait forever or never score; a name with nothing behind it | Engineering (S1 §9, S1a) | Keep: authoring. Escapes already exist (`unbounded=True`, `on=REMEMBERED`) |
| A5 | `unallocated-code` (:430), `unallocated-outcome` (:841) | Codes absent from the allocation | Engineering, on wl-preproc's codec | Keep: record |
| A6 | `nothing-to-look-at`, `duplicate-stimulus`, `absent-stimulus`, `empty-update` (:982, :1016) | Scoring a stimulus not shown; one name for two stimuli; hiding or updating one not shown; an empty update | Engineering | Keep: authoring. The runtime raises on two of them mid-trial (run.py:310-330), and an empty update records a change that did not happen |
| A7 | `unreachable-state` (:312), `shadowed-transition` (:401), `unreachable-timeout` (:2441), `meaning-for-nothing` (:200) | Dead code | Engineering | **Warn, as a review note** (`blocking=False`, `accepted_in=()`, like `custom-component-needs-review`), shown by `wlx check` and the review and never asked at the rig: "this can never take effect; probably a mistake" |
| A8 | `overlapping-windows` (:2397) | Two windows one state scores can overlap within their ranges | Engineering | **Warn**: "a gaze inside both is scored by whichever transition is written first, so a look at one can count as the other". The order is defined (M0 §4) and recorded |
| A9 | `crowded-array` (:2478) | Object windows overlap at the declared extremes | Engineering | **Warn**: "at N objects on an R° ring, a saccade to one object can be scored as its neighbor" |
| A10 | `wrong-eye-criterion` (:2330) | A window scores the eye its stimulus is not shown to | Engineering, EYE-23 | **Warn**: "the animal can do the task with the seeing eye and fail every trial" |
| A11 | `monocular-stereogram` (:2291) | A stereogram shown to one eye | Engineering, STE-10 | **Warn**: "with one eye there is no disparity; don't analyze these trials as a disparity condition". The record carries `eye` |
| A12 | `wrong-setup` (:2743) | A task declared for the other setup | Direct-view spec §3 (spec approved 2026-09-28; the rule itself never asked) | **Warn** when there is no stereo content: "written for direct view; here each eye sees its own half, inside the ±12° mask". `needs-stereoscope` and the field check still refuse |
| A13 | `needs-stereoscope`, `per-eye-background`, `per-eye-misused` (:2590, :2725) | Stereo content or per-eye positions outside the stereoscope; per-eye positions plus a disparity | Engineering (STE-08, STE-09) | Keep: record. Both eyes would see both images, so the record would not describe what was shown |
| A14 | `target-outside-array`, `impossible-correlation` | No target; a correlation outside [−1, 1] | Engineering | Keep: record |
| A15 | `stimulus-off-screen` (:755) | A center off the panel, behind the mask, or under a sensor's housing | Engineering (S1 §9); STE-13 (PI) | Keep: record. No one could see the stimulus, so a miss would read as behavior. The near-edge case is XC-349's warning (PI); the unbounded-parameter case is authoring |
| A16 | `bad-block` (:1993), `bad-placement`, `multiply-needs-modulation`, `unlit`, `overspecified-color`, `contrast-convention`, `bare-contrast` (:1773) | Undrawable or ambiguous values: a size ≤ 0, negative light, a ring turned inside out, a wrong kind, a self-referring parameter, a drift not across the bars, no light, no contrast convention | Engineering; COL-24 and STE-03 are the PI's | Keep: authoring |
| A17 | `weber-on-black`, `cone-color-on-black` | A contrast against black, which divides by zero | PI, COL-09 | Keep: authoring |
| A18 | `cone-color-two-backgrounds` (:1907) | One cone color, two eyes' backgrounds | Engineering (A2 plan, call 10) | Keep: authoring. The color would be two different lights |
| A19 | `isoluminance-on-default` (:1218) | Isoluminance on the sRGB default, in every kind | PI, COL-03 | **Ask.** For a warning: a training animal loses nothing to an unmeasured null. For a refusal: isoluminance is the experiment's control, and on an unmeasured panel it is unknown. A split is possible: accepted in training and piloting, refused in recording, as `color-on-default` is |
| A20 | `unrealizable-color` (:1468, :1240); `exact.output_levels` (exact.py:272) at draw time | A light, or a contrast's extreme, outside the gamut | Engineering (COL-08, -34, -36) | **Ask.** The warning would be "the panel clips this; it is neither the chromaticity nor the luminance asked for". It needs the drawer to clip and the record to carry the light actually shown; otherwise the record is wrong |
| A21 | `color-on-default`, `contrast-on-default`, **in recording** (:1495) | Recording on the default with any color, or any light a parameter sets | PI, COL-02 (2026-10-07, widened 2026-10-08) | **Ask.** For a warning: the record names the default, and today no lab task can record until V9 measures a panel. For a refusal: every luminance in the data is nominal. His ruling, made four days before the rule |

`head-not-fixed`, `luminance-step` and `custom-component-needs-review` are already a warning or a note.

## 2. Color calibration (builds A2 and B)

| # | What is refused, and where | Decided by | Proposal |
|---|---|---|---|
| E1 | A named record that will not load. `cli._load_calibration`:159 stops `wlx run` and `wlx check`. In `wlx taskd`, `warnlist.of_unloaded`:128 is accepted in no kind, so every run fails, with `Session.run`:2078 and `uncalibrated-color` behind it | Engineering (engine B plan, call 19) | **Warn**, and fall back to the default: "calibration X would not load (why); this session runs on the sRGB default". COL-02 still governs recording. The sentence must fit the 500 characters the open's form sends back |
| E2 | A calibration dated after today (`warnlist.of_calibration`:101), accepted in no kind | Engineering (call 19) | **Warn**, in every kind: "its date or this host's clock is wrong; check the clock, which every welfare time is read on" |
| E3 | Cone colors on a measured calibration without spectra (`Calibration._convert`) | Engineering (A2 plan, call 8; COL-34: "no paper behind it") | **Warn**: convert as the default does, with COL-18's sentence. Today a panel measured without spectra runs fewer tasks than the unmeasured default |

The default calibration and a calibration's age are already warnings (COL-01, COL-21).

## 3. Pre-flight items and the gate

| # | What is refused | Decided by | Proposal |
|---|---|---|---|
| B1 | `warnings` fails when the codes' names pass 500 characters (preflight.py:165) | Engineering (build B fix) | **Warn**, or list them all. A display limit is no reason to refuse a run (cf. XC-353) |
| B2 | `warnings` fails when the warnings cannot be listed | Engineering (call 31) | Keep: record. The run's imperfections would be unknown |
| B3 | `starting values`: an undeclared name, a word where a number belongs, a value not among the choices, a non-finite number, a number with no value (:183) | Engineering (b3a-2) | Keep: authoring. Otherwise the run faults after `RUN_START`. Out of range is D2 |
| B4 | `bounded config` re-read fails, or names another animal | Engineering, S8 | Keep: welfare |
| B5 | `out of cage` (listed) | PI | Keep: welfare |
| B6 | `pump calibration` with a real driver (:389) | S9a §10 (PI); off the list by the PI's ruling of 2026-09-30 | Keep: welfare. Without a calibration a mL ceiling means nothing. Unreachable until a driver exists |
| B7 | `gate` (listed) | PI | Keep: welfare. Its acknowledgement is already the warning mechanism |

## 4. The service (`service.py`)

| # | What is refused | Decided by | Proposal |
|---|---|---|---|
| C1 | `_open` (listed): a second session; any session while an animal is stranded; an answer nobody asked for; the departure marks | PI | Keep: welfare |
| C2 | An open whose warnings are not accepted (:841); `wlx run` without `--accept-warnings` | PI, TSK-41 | Keep: no path. This is how a warning is accepted |
| C3 | A name that is not one folder name (`_folder_name`, listed; `_task`) | Engineering | Keep: safety. Code from outside `--subjects` or `--tasks` would run |
| C4 | A session id already used (:666; cli:1717) | Engineering (XC-201) | Keep: record |
| C5 | No `bounds.py`, or one naming another animal (`_build`) | Engineering | Keep: welfare |
| C6 | The stereoscope with no `settings.py` (:719; cli:253) | PI, 2026-09-29 (STE-20) | **Ask.** For a warning: "disparities and the vergence offset assume the nominal 1.6 cm", recorded as nominal, as a chaired session's free head is. For a refusal: STE-20 says the nominal value "is not a measurement" |
| C7 | A half-IPD outside 30-38 mm (geometry.py:317) | PI, 2026-08-31 (STE-20: "no stated basis") | **Ask.** For a warning: "outside the drawn optics, the field is extrapolated". For a refusal: positions and the off-screen check would rest on an unmodeled field |
| C8 | A settings file naming another animal (cli:170, `_build`, `preflight.files`) | Engineering | **Warn**: "these are X's settings; this session uses X's half-IPD of N cm" |
| C9 | A resume past the limit, with changed bounds, or with fluid unknown | PI ("Resume or end"; resume code unlisted) | Keep: welfare. Ending is always offered |
| C10 | A resume whose record is unreadable, inconsistent, or missing its kind or run numbers | Engineering (XC-026) | Keep: record |
| C11 | A resume refused for one damaged `warnings.jsonl` row (resume.py:99) | Engineering | **Warn**: "row N is damaged and not carried; its warnings are asked again". Asking again is the safe direction |
| C12 | No session; the session has ended; a run already starting; idle commands and marks; a reward with no session (XC-158) | Engineering | Keep: no path |
| C13 | At start-up, an allocation without the framework codes (:385) | Engineering | Keep: record. Also add PAUSE, RESUME and MANUAL_REWARD to it (D5, D6) |
| C14 | `_end`, `_unended`, `_close_stranded` (listed) | PI | Keep: welfare |

## 5. The session (`taskd.py`, `run.py`)

| # | What is refused | Decided by | Proposal |
|---|---|---|---|
| D1 | `Session.set` (listed): a bounded setting that is not a number, or over its ceiling | PI (REW-02; items 3 and 4) | Keep: welfare |
| D2 | **A live value outside the task's declared range** (taskd.py:1029); a starting value likewise (preflight.py:234) | S8 §3.1, engineering. The ranges are mostly the authors' choices | **Ask, first.** For a warning: "outside the declared range; the load-time checks were proved only inside it". For a refusal: every proof (on screen, windows apart, colors realizable, target in the array) is made over the range, and outside it a run can fault mid-session or record nonsense. A middle path: re-run the checks with the range widened to the new value, warn if nothing new blocks, refuse what does. This touches `Session.set`, which is listed; its ceiling path need not change |
| D3 | `Session.set`: an undeclared name, a setting not live, a value not among the choices, a non-finite number | Engineering (S8 §3.1, M8) | Keep: authoring. A typo would run the old value while the console shows the new one |
| D4 | **Every setting change between runs** (:1669). A start carries only task settings, so a reward size cannot be set before trial 0 | Engineering (P4d-2a, b3a) | **Ask.** Hold the change for the next run and say so. Check against REW-11 ("carried values never carry it"). Welfare-adjacent |
| D5 | A pause with no PAUSE or RESUME code (:1195) | REC-12 (PI) | **Warn**: "paused; the recording shows an unexplained gap, and the pause is in `controls.jsonl`". Better: refuse such an allocation at start-up (C13) |
| D6 | A manual reward with no MANUAL_REWARD code (:1588, listed) | REW-13 (PI) | Keep: welfare. Move the check to start-up (C13); `_manual_reward` is untouched |
| D7 | A reward during a trial, or after a `wlx run` session's run | Filed: XC-157, XC-184 | Keep: welfare |
| D8 | `_schedule` (listed): a malformed stop, or one already reached | Engineering | Keep: welfare |
| D9 | `welfare.preflight` (no departure; animal home; head-fixed but not marked) | PI | Keep: welfare |
| D10 | Pausing twice, resuming when not paused, cancelling nothing, any of these while stopping | Engineering | Keep: no path |
| D11 | Mid-run: `Unwired`; a parameter with no value; a code too wide; a pump fault | CLAUDE.md, REC-08, PI | Keep: record |

## 6. Loaders, CLI, console, link, welfare modules, gaze

| # | What is refused | Proposal |
|---|---|---|
| H1 | Task, rig and settings loaders (no `Task`, a file written before C1, no `RIG` or `SETTINGS`, a bad calibration path) | Keep: authoring (C1 plan, call 2; PI) |
| H2 | An allocation file with no `ALLOCATION` | Keep: record |
| H3 | A bounds file with no `BOUNDS`; welfare refusals while building a session (cli:1828) | Keep: welfare |
| H4 | `--subject-settings` with `--view direct` (cli:249) | **Warn**: "direct view ignores it" |
| H5 | A `--link` other hosts can reach without `--link-allow-remote` | Keep: safety. The flag already overrides it |
| H6 | `wlx console --set` or `--stop` without `--as`; argument syntax | Keep: record |
| I1 | Wire decoding (`_command_from`, `check_schedule`, `_mark`, `decode`, `parse_command`) | Keep: record |
| I2 | Host, Origin and loopback writes; body size; sign-in tokens; the `/health` token; a token file inside the repo; the remote bind | Keep: safety |
| I3 | `link._setting` (listed) | Keep: welfare |
| I4 | A cage-side open via `wlx taskd`; the page's copies of welfare rules (reward, stranded, unasked answers, return time) | Keep: welfare |
| I5 | A command with no session kind or no sender | Keep: record |
| G1 | `bounds`, `welfare`, `marks`, `stranded`: every refusal | Keep: welfare. No change proposed |
| F1 | `calibration.fit_eye`: `too-few-targets`, `degenerate-constellation` (EYE-05) | Keep: record. No map can be fit. Nothing outside the tests calls it yet |

**Planned refusals not yet built**, to be put to the rule when each build is planned:
- no validated eye map;
- the stereoscope's alignment not accepted;
- a self-pausing run without pause codes (spec §20.1);
- the OLED's maintenance being due (DISP-19);
- the ABL cap (COL-13);
- frame-quantization refusals (DISP-07, -11, -15).

## Summary

**69 rows:**
- **Keep:** welfare 17, record 15, authoring 10, safety 3, no path 3
- **Warn:** 14 (A7-A12, E1-E3, B1, C8, C11, D5, H4)
- **Ask:** 7 (A19-A21, C6, C7, D2, D4)

**For the PI first:**
1. **D2**, ranges, in `Session.set` (listed). The largest free-control question.
2. **A21**, COL-02. No lab task can record until a panel is measured.
3. **E1**. One bad calibration file stops every run in every kind.
4. **D4**. No reward size can be set before trial 0.
5. **A19 and A20**: split training from recording, or keep the refusals.
6. **A8 and A9**. Because these are proved over declared ranges, authors narrow the ranges; as warnings, the ranges could widen, which is half of D2.

**Welfare-listed code:**
- D2 touches `Session.set`, and D4 sits next to it.
- Every Warn proposal is in unlisted code.
- E1 changes what `open_warnings` returns. `_open` (listed) reads that list but its own code does not change. The PI may still want E1 in a welfare summary.

## Found on the way (to file)

- **The page's New-session deployment defaults to head-fixed** (web.py:3034), against WEL-06's "no default". A chaired session left at that default opens as `RIG_FIXED`, so `HEAD_FIXED` is strobed for an unfixed animal and both `head free` and `head-not-fixed` go unlisted. Fix: a blank choice that must be picked, as the session kind has. Welfare-adjacent.
- **A warning longer than 500 characters could never be accepted at an open from the page.** `WarningRow.of` cuts it, and the open matches the full sentence. None is that long today (the longest is 270), but E1's could be. Related to XC-353.
- **TRN-07 against the https page.** TRN-07 says pause, stop, resume and manual reward need no sign-in, but the https page refuses them without a token. The two agree only if TRN-07 means at the rig PC. A wording question.

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

## The PI's answers, 2026-10-12 and 2026-10-14

Asked by the plan named below, before its build, and, the last, at its whole-branch review:

- **A value outside its range making a trial wait longer than the task's longest declared wait**:
  "Allow, with a warning". The option he chose read: "Any wait up to the trial cap: about 417 s
  today, 5 minutes once C2a is built. The warning says Stop, Pause and the out-of-cage limit go
  unheard until that trial ends."
- **TRN-07** ("pause, stop, resume and manual reward never need sign-in"), against the https page,
  which refuses them without one: at the rig PC only. His choice read: "No sign-in at the rig PC's
  own console. From another computer, sign-in is required, as built now, so nobody on the network
  can stop a session or give a reward unseen. The decision log's wording is clarified."
- **2026-10-14: a set size, a target index or a stereogram's correlation declared with only one
  limit**, which the build refuses at load (`target-outside-array`, `impossible-correlation`;
  it loaded before, its open side read as 0), where the plan's decisions he read said "No other
  refusal changes" (the review's I4): keep that, or warn at load and check every value sent
  widened?
  "Refuse at load". The option he chose read: "The task author adds the missing limit, a
  one-line fix. Nothing changes for the experimenter at the rig. It matches how a color or a
  position with one missing limit is already refused at load." Each such refusal names the
  setting and the fix ("'ti' declares no lowest; declare both limits"; decisions.md TSK-51).

How each was built, and the calls taken in building them: the plan named above. Of "Found on the
way", the head-fixed default is fixed by XC-355 (the deployment fix, merged before that build); a
warning longer than 500 characters at an open is answered by bounding every warning an open lists
within it (E1's quoted refusal is cut in its middle); the TRN-07 wording is answered above.
