# Engine build A2: the whole-branch review's triage of deferred findings (2026-10-10)

The whole-branch review (most capable model, `0739cee..ba50387`) was asked to rule on every finding the
task reviews had deferred as minor. This is its triage, copied from its report so the reasons outlive the
build's git-ignored ledger. The controller adopted it: items marked **fix before merge** went into the one
fix wave (`b5005de`, `95bc590`, `d34da87`, re-reviewed clean); **backlog** items are in XC-314 and XC-315;
**drop** items were dropped for the reason given. The controller's own rulings are in
[a2-build-rulings.md](a2-build-rulings.md).

## Fix before merge (all fixed in the fix wave)

- ADR-0004's "Any other CC BY-SA table…" rendering inside the last bullet: trivial.
- `check._NUMBERS`' comment omitting the cone fields: trivial.
- Nothing pinned that a `ConeContrast` mean changing L or M still lists `luminance-step`: one assert.
- `_claims_isoluminance`'s docstring said both halves judge "at one value"; the DKL half judges `lum` and
  chroma independently: docstring only.
- `exact.output_levels`' clip at full drive untested: one test.
- `exact.output_levels`' refusal printed its farthest weight with `{worst:g}`: `.7g`.
- ADR-0011 not saying the primaries and spectra are black-subtracted (raised as Important 2).

## Backlog

- `cone_xyz` inverting the cone matrix per call with an absolute 1e-12 singularity threshold; a non-finite
  matrix from radiances near 1e308; a singular matrix (three identical spectra) refused later with a
  sentence naming no calibration — folded into **XC-315**: invert once in `Calibration._convert` inside its
  `try`, refusing a singular or non-finite matrix with a sentence naming the calibration. Realistic
  matrices in W·sr⁻¹·m⁻²·nm⁻¹ have determinants around 1e-9 to 1e-10, so the threshold has margin.
- A `ConeContrast` on a background whose chromaticity is a parameter range, judged per background corner
  (**XC-314**, filed at Task 11): reproduced; exotic.
- `screen.resolve` converting each item's cone color separately (**XC-315**): must close before build E
  calls `resolve` every frame (the hot-path rule).

## Drop

- Task 1's imports moved and planning pointer dropped: done.
- `cbcb816`'s commit body abbreviating two checksums: pushed history; the full values are in ADR-0012 and
  the tests.
- The CIE checksum guard tested only on `cie_file`: resolved by the table-tamper test through `table()`
  and a calibration (`tests/test_color.py`).
- `cones.table()`'s cached array writeable: nothing mutates it.
- `cones.excitations` with fewer than two samples: `Spectra` guards its only consumer.
- The V_F,10 data-set claim and the observer's parameters: resolved by `63a4333` (dated and checked).
- A subagent's Co-Authored-By naming its own model: accepted.
- Forward references to later tasks' names; the final grep for stale "until build A2" text: nothing live.
- A break count not pasted into a report: covered by later runs.
- `_convert`'s fallback untested; a missing CIE file raising `OSError`: the fallback is now tested.
- `_convert`'s docstring naming `cone_record` early: built.
- Task 3's carry list to Task 4: all four verified by probe or test.
- `(_backgrounds(trial) * 2)[:2]` reading as a puzzle: cosmetic.
- The carrier filter in `_cone_color_faults` untested: without it a cone-colored background, already
  `bad-block`, would get one more refusal.
- Report evidence, COL-05's double link, a commit body's plan-internal "Task 4": cosmetic or history.
- Task 4's rulings (every cone field bounded; the default-faults pin; NaN failing closed): done and
  verified by probe.
- Task 4's long lines and docstrings: the stale docstring is now correct; the long lines are cosmetic.
- Task 4's forward references (black-subtracted fractions; "plus one optional"; `ConeContrast`'s
  isoluminance): built.
- `Spectra` left out of an unused import: accepted.
- Task 5's ADR heading naming `RECORD_FIELDS`; "a list of numbers" for non-finite values; no service-level
  malformed-spectra test: cosmetic; the catch-all test covers the path.
- The bad-block ruling for an unbounded isoluminant DKL; the push-once-per-task cadence: agreed.
- A test name saying "isoluminant" for a `bad-block` refusal; a trailing blank line: cosmetic.
- Task 6's per-value `ConeContrast` rule and reversed range: done and verified by probe.
- Task 6's degenerate `ConeContrast` range refused: the safe direction.
- Task 6's missing named breaks for its new helpers: covered by the reviewer's own runs and the CI sweep.
- Weber below −1 and Michelson above 1 refused twice: both sentences are accurate.
- COL-36's wording, a test docstring's "five times as bright", blank lines, `_multiplied`'s name: COL-36's
  Where names `exact.output_levels`, and XC-306 says the rest.
- Task 8's "checked" docstring, the `_TWO_BACKGROUNDS` sentinel's type, one eye `Gray(0)` beside an unset
  one reading "differ": both findings fire there, and both are accurate.
- `exact.output_levels` not checking its last axis is 3; `inverse_transfer` asymmetric outside [0, 1]:
  `draw` always hands (rows, columns, 3).
- Task 10's spec wrapping, the record pinned in two tests, branches tested by calling `cone_record`
  directly: test hygiene.
- Cancelling two queued per-push runs for the full sweep at the tip: agreed; the merge waits on the full
  sweep's output, read line by line, not its exit code.

## What the review declined to judge

- An `OverflowError` from a literal like `10**400` in a cone color: predates A2 for `Gray` and `xyY`.
- A position range with string bounds passing `check` silently: predates A2, outside color.
- `DKL(lum=0.006, l_m=0.1)` loading on the default: by design, the PI's half-percent band (Q2).
- An `xyY` at the background's luminance not counting as an isoluminance claim: the PI's rule names DKL
  and cone-contrast spellings.
- Whether CC BY-SA reaches Apache-2.0 code: marked UNVERIFIED and left to the PI by ADR-0012.
- 16 cd/m² and "by his numbers": the PI's decisions (Q1).
- The trapezoid's half bin at 390 nm for spectra starting below it: well under 0.1% for any panel's blue,
  and consistent with the CIE's declared extrapolation.
- `check`'s combinatorial cost over many parameter choices: load time only; the pattern predates A2.
- `check` refusing grating peaks a coarse drawer preview does not sample: conservative by design (call 18).
