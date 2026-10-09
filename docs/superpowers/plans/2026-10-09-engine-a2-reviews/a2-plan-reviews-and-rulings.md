# Engine A2's plan: its two reviews and the controller's rulings (2026-10-10)

The draft (`f7198fe`, 11 tasks, 2 Questions, 26 Calls) was reviewed by two independent reviewers on the
most capable model before the PI saw it: an **engineering** seat (will the plan, executed task by task,
produce correct tested software that does what the spec and the PI's answers say) and a
**color-science** seat (are the stimuli it builds physically and scientifically right, and is the PI told
the truth). Both read the code at `171b8d8` and the draft's prototype (`scratchpad/a2-proto/`, the
eleven tasks' code applied to a copy) and ran breaks there. Each finding below is the reviewer's,
condensed; the ruling is the controller's. "Q" rulings go to the PI; everything else is an engineering
ruling applied in the revision.

## What both found right
- The color arithmetic: the DKL construction (Brainard 1996's isolating directions; the hybrid scaling as
  the PI chose), the V_F,10 weights (0.69283932·l̄ + 0.34967567·m̄ reproduces the CIE's V_F,10 within
  4.5e-7), S beyond 615 nm and linear interpolation as the CIE's metadata declares, the LMS→XYZ_F,10
  matrix (refit within 1.7e-7), realizability by full conversion. The color reviewer's independent numbers
  agree with the plan's to every printed digit (isoluminant M:L −2.2164975677 on a D65 gray; reach at
  each gray; the measured path's 5 nm interpolation within 0.0002 of the CIE's 1 nm values after
  integration).
- Every code anchor the plan edits exists at `171b8d8`; the plan's own breaks fail as named.

## Critical
- **E-C1 (engineering).** Task 7's `_modulation_faults` sends a grating's cone-colored mean with a
  parameter inside straight to `cone_xyz`, and `_contrast`'s `float(P)` raises `TypeError` past `except
  ValueError`: `check()` crashes on a valid task (reproduced on SRGB and a measured record), the failure
  XC-269 tracks, in the branch that closes it. **Ruling: fix** as the reviewer proposes (expand the mean
  through `_lights(declared, params)` inside the `_Unbounded` guard; `except ValueError` per value; and
  `_contrast` raises `ValueError` on a non-number), with tests for a DKL and a ConeContrast mean with a
  parameter, on both calibrations.
- **S-C1 (color science).** Q1 and Q2 leave out that the gray decides whether the PI's published colors
  can be made. His 2023 paper (Westerberg et al. 2023, Methods, "Task design: Pop-out search") gives the
  background's cone excitations (L 1.86, M 0.94, S 0.023) and the items' cone contrasts (red C_L +0.27,
  C_M −0.54, C_S −0.94; green −0.06, +0.13, −0.87), L+M 2.80 for all three. An isoluminant saturated red
  needs a gray no brighter than the red primary's own maximum (17.0 cd/m² on sRGB at an 80 cd/m² white):
  the 2023 red needs a red weight of 0.167 at 2.8 cd/m² and 1.19 at 20 (refused). The search task's
  ±0.08 items are about a fifth of 2023's L−M difference and have no S decrement. **COL-05's basis ("no
  paper gives a DKL or pooled-cone-contrast magnitude for isoluminant red-green search items") is
  contradicted by the PI's own paper.** **Rulings:** (1) Q1 and Q2 become one question about the scene
  (the gray and the items' colors together), with the 2023 numbers, the ~17 cd/m² ceiling, a photopic
  middle option, and each option's cost stated (below); (2) COL-05's basis is corrected now, with a dated
  correction, its "Decided" left as the PI's.

## Important
- **E-I1 / S-I1 (both).** `ConeContrast` never claims isoluminance (call 15), so the PI's rule refusing
  isoluminance on the default is bypassed by spelling: `DKL(s_lm=0.3)` is refused in every kind,
  `ConeContrast(S=0.3)` — the same light, identical XYZ — loads with a warning, and so does the search
  task's own red written as a cone contrast. And on the default, "isoluminant" means constant CIE 1931 Y
  (the CIE matrix's luminance row makes the model's V_F,10 identically 1931 Y): on two modeled panels at a
  20 cd/m² gray, `ConeContrast(S=+0.5)` carries +2.2% / +1.9% true V_F,10 luminance contrast — enough
  to drive magnocellular responses in a laminar M/P/K mapping. **Ruling: a Question for the PI** (new
  Q3), with that consequence stated; call 15 is not built until he answers. Options as both reviewers
  framed them, recommended first: a cone contrast claims isoluminance when L and M are both 0 or sit at
  V_F,10's ratio with S changing (refused on the default, as DKL is); every cone contrast needs a measured
  calibration in every kind; as drafted.
- **E-I2 (with S-M1).** Call 13 makes each channel's level-0 fraction a floor: summing three such floors
  counts the panel's black three times (the standard display model adds it once), and with
  `fractions[0] = 1e-4` every black pixel is unrealizable at draw while `check` passes it; "Cost: none"
  is wrong. **Ruling:** fractions are black-subtracted — ADR-0011 amended to say so, and
  `read_calibration` refuses a record whose fraction at level 0 is not 0, with a sentence naming it (no
  measured record exists yet, so nothing that loads today is refused); black as an additive ambient term
  is build J's (a backlog line); call 13 rewritten with its cost.
- **E-I3.** The checksum guard on `cones.table()`'s read path is untested (a break reading the file
  without `cie_file` survives 147 tests). **Ruling: fix**: the test empties `cones._TABLE`, patches
  `CIE_FILES[TABLE]`, asserts `cones.table()` raises "is not the CIE's file", and that `check` then
  refuses a cone color with that sentence.
- **E-I4.** `_claims_isoluminance`/`_can_be`'s boundaries are untested (`<=` → `<` and `any` → `all`
  survive). **Ruling: fix** with the four cases the reviewer lists.
- **E-I5 / S-I4.** Q2's "the animal trains on the scene it will later be tested on" overstates: the
  training red's setting tops out at 17 cd/m² and both items start at 15, so on a 20 cd/m² gray the
  training items are darker-than-background patches and the red can never match the gray; and the
  training items are saturated primaries while the test's are ±0.08. **Ruling:** folded into the new
  scene question, stated plainly.
- **S-I2.** A default session's `config.json` says "lum is luminance contrast under V_F,10", while on this
  calibration the luminance held is the standard's CIE 1931 Y. **Ruling: fix**: on a standard
  calibration `cone_record` and the warning add "on this calibration the luminance held constant is the
  standard's CIE 1931 Y, which the CIE's matrix equates with V_F,10".
- **S-I3.** The record does not carry what a DKL number means for its background (Brainard 1996 p. 575:
  "an explicit specification of the cone excitation coordinates of the background"; the PI's 2023 methods
  report exactly these). **Ruling: deferred to build F's screen log, with a backlog line** — the record
  already allows them to be computed (the calibration record, the observer and each trial's resolved
  background) — and a "What the PI should know" item saying a methods section needs them and how to get
  them until F.

## Questions for the PI after this revision
1. **The search task's scene** (replaces Q1 and Q2): the gray, the items' colors (the task's ±0.08 or his
   2023 contrasts), and whether the training variant shares the gray — one question, in plain terms,
   with the 2023 numbers and the ~17 cd/m² ceiling, a photopic middle option (about 10-15 cd/m²), and each
   option's cost: 40 cd/m² has the room for the task's colors toward green only (toward red 0.164
   against 20's 0.491); a live gray changes adaptation and every item's absolute light mid-session; 2.8
   cd/m² lies in what CIE 191:2010 calls mesopic (about 0.005-5 cd/m², UNVERIFIED unless opened), where
   rods, dense at the task's 5-14°, can break a cone-based null, and makes the 40 cd/m² fixation point
   Weber +13. The recommendation is the drafter's to make, with its reason.
2. **A cone contrast and isoluminance on the default** (new; E-I1/S-I1).
3. **A one-line confirm** (E, "missing as questions"): the observer is the CIE's published table, not
   rebuilt from its parts, which departs from the wording of the Q4 option he chose ("its parameters
   recorded, built from the CIE's parts"); the plan's reason (the CIE publishes no parts as data, and
   formulae give slightly different numbers from the Q3 table) in one sentence.

## Minor rulings (all applied unless said)
- Header: say exactly what the prototype ran and what it did not (Task 3's training change and test,
  Task 1's `pyproject.toml`, the docs edits); the suite count it read (3197 passed, 65 skipped).
- Task 10 Step 2's `-k` selects nothing (`..._name_its_calibration`): fix the name.
- The "Filed when approved" lines: no parenthetical inside the bold ID (`tests/test_backlog.py`).
- `Calibration.cones` re-integrates per call: compute once at construction (`field(init=False,
  compare=False)` set in `__post_init__`); remove the undated "which no session calls yet" claim.
- Call 18: its backstop is the exact drawer, which no session runs; say the display process (E) must
  refuse or flag such a pixel rather than clip it, and the backlog line waits on E.
- A grating about an isoluminant cone mean (and about `DKL()`) gets a false `luminance-step` warning,
  recorded in `warnings.jsonl`: filter cone means with `lum` 0; test it.
- B10: pin `_background_lights`' "black is left out" with a test.
- Task 1's test docstring "row 32 (counted from 0)": the metadata is 1-based (index 31 = 545 nm).
- Packaging: `wl_xcon/cie/* -text` in `.gitattributes`; a test that the files are found through the
  package (or a wheel-build check).
- Stale docs to Task 11: the S4 spec's 2026-10-07 note ("the rest of §7 is engine build A2's"); COL-28's
  "on the black background".
- Task 11's sweep: read the nightly `--all` sweep shard by shard too (`tests/_calibrations.py`, `tasks/`
  and `pyproject.toml` escalate only there).
- Global Constraints name the interpreter (`.claude/worktrees/b2b-remote-signin/.superpowers/venv`, run
  with the cwd at the worktree) or add a setup step.
- A record's `observer` is free text: a build J backlog line (a record's observer is CIE V(λ), or the
  session warns).
- ADR-0004's amendment narrowed to ADR-0012's files (Q3 answered for these files, not every CC BY-SA
  table).
- The observer record: add the interpolation ("linear between 5 nm points") and V_F,10's weights; the
  standard observer's age only if verified at a primary source (Stockman & Rider 2023, or CIE 170-1),
  else marked UNVERIFIED in the plan and not recorded.
- COL-19's caveat gains spectral-shape constancy across drive levels as an assumption, and build J's
  backlog line a spot check of spectra at a few levels.
- The beyond-780 nm shares: state the integration method (the color reviewer's trapezoid over 780-830 nm
  gives L 2.4e-6, M 2.3e-7 against the plan's 2.0e-6, 2.0e-7); recompute and say which.
- "What the PI should know" gains: the lab's 2020/2023 "isoluminant" was, by the color reviewer's
  reading, the Smith-Pokorny/Judd-Vos luminance (L+M; the reviewer named Cole & Hine 1992) — check it
  against the two papers' methods before writing it, and cite only what they say — and A2's is V_F,10; for L−M items the difference is
  at most about 0.2% (modeled), for S-varying stimuli about 2% per 50% S — a methods section comparing
  datasets says so.

## Declined (with reason)
- Whether CC BY-SA data beside Apache-2.0 code needs more than ADR-0012 provides: legal, marked
  UNVERIFIED in the plan, put to the PI as part of ADR-0012's record.
