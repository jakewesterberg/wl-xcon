# Engine build A2: the controller's rulings during execution (2026-10-10)

Every decision the build's controller took on the PI's behalf while executing the approved plan
(`docs/superpowers/plans/2026-10-09-engine-a2.md`), each with why it was taken and what it costs if
wrong, so the PI can read any of them and reverse it. They are copied from the execution ledger
(`.superpowers/sdd/2026-10-09-engine-a2/progress.md` in the `engine-a2` worktree, git-ignored and deleted
after the merge): all 33, the nine on the pre-flight scan's findings and the 24 the ledger marks
"Ruling", none added or dropped, in ledger order under each heading. They are lightly cleaned for a
reader without the ledger: "T3" reads "Task 3", agent IDs are dropped, and commit, review-finding and
backlog IDs are kept ("I" is a reviewer's Important finding, "M" or "m" a minor one). Where the ledger
recorded no reason or no cost for a ruling, its bullet says so rather than supplying one. The controller
judged that none of these needed the PI; the questions that did went to him, and his answers are in the
plan.

## Before Task 1 (the pre-flight scan)

- **No local mutation sweeps (carried from build B, XC-275).** The controller pushes after each task and
  reads CI's per-push gate shard by shard (whole modules whose source or own tests changed); Task 11's
  sweep is one CI sweep of the branch against `main` plus the nightly or full sweep, as the plan says;
  timeouts and import errors are not counted as caught until a targeted local check shows a test failing.
  Why: carried from build B, which ruled it because `tools/mutate.py`'s fixed 300 s suite limit was below
  this machine's suite time while two worktrees ran (XC-275; build B's CHECKPOINT entry). Cost: none
  recorded.

The pre-flight scan (a read-only agent that applied every task's code in order to a scratch copy and ran
the full suite after each: no blocking conflict, green after every task) produced nine rulings, each
carried into its task's dispatch; none needed the PI.

- **Task 3: COL-05's heading.** It still read `DKL(lum=0, l_m=±0.08)`, so Step 6 also amends the heading
  ("its colors superseded by COL-33"). Cost: one line.
- **Task 3: `_cone_color_faults` calls `_backgrounds()`** rather than working out each eye's background
  again, which would repeat logic. Cost: a small refactor in the task.
- **Task 4: the Step 5 break's failure.** The `_lights` DKL-branch break fails with an AssertionError
  naming `l_m=P(name='c')` (Task 2's `_numbers` makes the TypeError a ValueError), not "the TypeError
  XC-269 named". Cost: wording only.
- **Task 5: the `Transfer` docstring.** Its addition goes at the docstring's end, so the sentence Task 9
  replaces stays intact. Cost: none recorded.
- **Task 6: Step 2's expected failures and the `_default_faults` step.** The expected failures are named,
  not counted (`says_nothing…` passes already; `cannot_make` fails with KeyError 'unrealizable-color';
  the fifth on `DKL(lum=P('c'), l_m=0.05)`; the boundary test's first failure is at
  `claims(DKL(lum=0.005, l_m=0.05))`). The `_default_faults` step replaces Task 4's `named = sorted(...)`
  line and its `if named:` block, and says so. A break is added, `if named:` for the cone sentence, so
  that `test_the_default_warning_says_nothing_of_cone_colors_a_task_does_not_use` fails. The V_F,10
  luminance-contrast arithmetic in `_claims_isoluminance` and `_contrast` goes through one shared helper
  (the test helpers stay independent, on purpose). Cost: a small refactor.
- **Task 7: the luminance-step test, the `return []` break and a shared helper.** Step 2's luminance-step
  test fails on `DKL()` (its first assertion); Step 5's `return []` break fails 8 tests (Weber, both
  gratings, the parameter test, four cone-mean cases), not 3. `_light_faults` and `_modulation_faults`
  share the multiply-or-window exemption through one helper, and the break `if False and …` is added so
  that `test_a_multiplier_or_a_window_is_not_held_to_a_reach_of_its_own` fails. Cost: none recorded.
- **Task 9: the files list and the tolerance.** The files list gains `wl_xcon/photometry.py` (Step 3
  edits `Transfer`'s docstring). `exact.output_levels`' own vectorized solve is accepted (the exact
  drawer is the definition build E's drawer is held to), but its range check uses the same `TOLERANCE`
  constant as `Calibration.weights_of` and `unrealizable`, not a restated literal. Cost: none recorded.
- **Task 10: the service test's oracle.** The plan's oracle was `cone_record(SRGB)`, the function under
  test (the plan's own break passes it); the test asserts against the literal record `test_taskd` pins
  instead. Cost: none recorded.
- **Task 11: the Self-review's placeholder IDs.** "XC-??? each" becomes XC-301 and XC-302. Reason and
  cost: none recorded.

## During the tasks

- **Task 1: the imports at the top of `tests/test_cones.py`.** The three function-level imports move to
  the top of the file: the Global Constraint binds over the brief's own code block, and the plan says
  that where a step shows imports above tests they move to the top. Cost, if wrong: nothing (a move).
- **Task 1: one more docstring edit in the same round.** "The review's minor:" is dropped from the same
  docstring (the same lines; it points at a review no reader can find). Cost, if wrong: nothing.
- **Task 2: attribution in a subagent's commit.** A subagent's commit names its own model in
  Co-Authored-By (`e7b6b41` says Sonnet 5.5): the attribution is accurate, and pushed history is not
  amended. The implementers' common rules now say to use the line the implementer's own harness gives,
  plus this session's Claude-Session line. Cost, if wrong: nothing.
- **Task 4's review: fix I1 as the reviewer proposes.** I1: a cone color whose component is a parameter
  that cannot be bounded was no longer refused. In `_block_faults`, beside the xyY branch, each field of
  a cone-color part is bounded with `values(part, field)`, so the comment at check.py:983 is true. Tests:
  on a measured calibration, an unbounded `l_m` and a half-range S give `bad-block`; on the default, the
  unbounded `DKL(lum=0, l_m=P)` is refused again. The spec's §7.4 (every space by full conversion) and
  §7.3 bind over the plan's code, and Task 6's `_claims_isoluminance` (`except _Unbounded: return True`)
  and Task 7's `_Unbounded` handling are consistent with it. Cost, if wrong: a `bad-block` finding added
  to any later task's test whose parameter has no range (carried as a note to Tasks 6 and 7).
- **Task 4's review: fix I2 with one test.** I2: `_default_faults`' change to cover every cone color was
  pinned by no test (with it reverted, a `ConeContrast` on the default checked clean even in a recording
  session). A luminance-changing `ConeContrast` (not an isoluminant one, so Task 6 leaves it unchanged)
  on SRGB with a gray background gives `color-on-default`, non-blocking, accepted outside recording; the
  test asserts the code, `blocking` and `accepted_in`, not the sentence (Task 6 rewrites it). Cost, if
  wrong: nothing.
- **Task 4's review: two more items in the same round.** (a) `unrealizable`'s weight test fails closed on
  NaN (`if not all(-TOLERANCE <= w <= 1.0 + TOLERANCE for w in weights)`; the probes
  `ConeContrast(L=1e308)`, `DKL(l_m=1e308)` and xyY `Y=1.7e308` had returned realizable): a one-line
  correctness fix in the function this task rewrote. (b) Two pins for claims the plan makes: a
  `ConeContrast` on a black background gives `cone-color-on-black`, and the search task on a measured
  calibration without spectra gives `unrealizable-color`. Cost: a few lines of tests if judged
  unnecessary.
- **Task 5: `Spectra` left out of an import.** `tests/test_display_calibration.py` does not import
  `Spectra`: nothing there uses it, and an unused import is noise. Cost: nothing.
- **Task 4's fix round: `bad-block` as the refusal of an unbounded isoluminant DKL on the default.**
  After the fix, `DKL(lum=0, l_m=P("s"))` with a parameter that cannot be bounded is refused on the sRGB
  default as a blocking `bad-block` ("cannot be bounded"), not as `isoluminance-on-default`. Accepted: it
  blocks in every session kind (stricter than `isoluminance-on-default`, which blocks it too) and names
  the root defect, the unbounded parameter; with a bounded parameter Task 6's `_claims_isoluminance`
  gives `isoluminance-on-default`. Cost: a differently worded refusal for a task no one can load either
  way.
- **Push once per task, when its review loop closes,** not after every commit: CI runs one push at a time
  here (Task 2's run was 39 minutes in, with four queued behind it), and each push's gate sweeps the
  modules changed since the push before it, so fewer, larger pushes keep the same coverage with a shorter
  queue. Cost: later CI feedback per commit. CI so far then: `cbcb816`, `fd1c194` and `63a4333` green,
  the `cones` module's six functions caught by failing tests each time.
- **Task 6's review: fix I1 (isoluminance judged at one value).** I1: the `ConeContrast` half pooled
  every value of every parameter into one span and asked whether some cone changes across all of them,
  not at the same value, so a luminance-changing series, an achromatic one and the literal
  `ConeContrast(0.003, 0.003, 0.003)` were refused in every session while the same lights written as
  `DKL` loaded with warnings. Now a `ConeContrast` claims isoluminance if and only if, at some value its
  parameters can take, on some lit background, its V_F,10 luminance contrast is within
  `ISOLUMINANT_WITHIN` and it is chromatic at that same value (L, M, S not all equal, the DKL half's "a
  chromatic component"). Choices are judged exactly per combination; ranges stay fail-closed within a
  combination (a span over the range ends that meets the band claims) unless the color is achromatic at
  every value of the combination (L, M, S the same literal or the same parameter). Why: the PI's Q2
  answer "catch it either way" means the same light gets the same verdict however it is spelled, and
  `DKL(lum=0.003)` is exactly `ConeContrast(0.003, 0.003, 0.003)`; this is not a new PI decision. Cost,
  if wrong: a cone-contrast design the PI would want refused loads with warnings in training or piloting.
- **Task 6's review: fix M2 in the same round.** `_can_be` read a range in declared order
  (check.py:1083-1084), so `DKL(lum=P c in [0.1, -0.1])` missed its claim; the fix is
  `spans(*sorted((low, high)))`. A missed refusal in the safety direction, one line. Cost: nothing.
- **Task 6's review: defer M1 to the backlog as XC-314.** A `ConeContrast` on a background whose
  chromaticity is a parameter range is judged per background corner, so `ConeContrast(L=0.08, M=-0.18)`
  on `xyY(P bx in [0.27, 0.37], 0.33, 20)`, exactly isoluminant at bx = 0.32, loads with two warnings (a
  DKL on the same background is refused). It is exotic (no reference task has a chromaticity-ranged
  background), and the fix needs background provenance that `_background_lights` does not carry. Cost:
  that exotic task trains on the default unrefused until fixed.
- **Task 8's fix round 1.** The docstring sentence (the Important: `tests/test_engine_path.py`'s module
  docstring was not edited as the brief said), plus Minor 2 treated as Important
  (`tests/test_reference_tasks.py`:213-214 imported `V_F10` and `_apply3` inside the test; the Global
  Constraint binds over the brief's code, as for Task 1), plus Minor 1 (a stereoscope test with two
  explicit equal per-eye backgrounds resolving a DKL, so the `is` break fails). Cheap, the same files.
  Cost, if wrong: nothing.
- **Task 11: cancel two queued per-push runs and run the full sweep instead.** The two queued runs
  (`ae5f4e1`, `fdd4b6a`) are cancelled and the full sweep (`mutation-full`, `workflow_dispatch`, run
  `38042608784`) runs at `ba50387`: it sweeps every function of every module at the tip, a superset of
  what those gates would have swept, and CI here runs about two runs at once. Cost: those two commits'
  own test-matrix runs (the tip's push run, `38042603715`, has the matrix).
- **Task 11's fix round 1.** Its review's I1 (the CHECKPOINT preamble still called `xc288-prep` unmerged
  and spoke of three branches) and I2 (the sweep paragraph said the per-push gates had run, though two
  were cancelled and only Tasks 1 and 2's were read, and it omitted the full sweep's and the tip's runs),
  plus the minors in what a later session believes: (m1) "0739cee to 747e717 are the eleven tasks' code"
  becomes Tasks 1 to 10's code from `cbcb816`, `0739cee` being the morning checkpoint; (m2) the A2 note
  in the engine spec's §7 says it supersedes item 3's "visual_search keeps its isoluminant colors and
  waits" and the B note's "until build A2"; (m3) the welfare paragraph says `service.py` differs from
  `171b8d8` only by `main`'s fault-sentences merge, with no listed function changed; (m5) the Status
  table's Reference tasks row is checked against `tasks/visual_search.py` and corrected if stale. Why:
  CLAUDE.md, a stale checkpoint is believed. Cost: nothing.

## The side job, XC-275

XC-275 (sweep timeouts) was worked on its own branch, `xc275-sweep-timeouts`, in parallel with A2, as the
PI chose on 2026-10-10.

- **The design: judge a timed-out mutant by what its suite had done (the proposal's design C, with design
  B's limit).** A pytest plugin (hooks, not a terminal regex) logs each test's start and outcome. On a
  timeout, a failure seen before the kill reads caught and names the test; none reads `TIMED OUT` and
  fails the run. The limit is max(300 s, twice the baseline). XC-275's part (b), an asserting test or a
  bounded loop for each function that reads `TIMED OUT`, stays empty until the first full sweep under the
  new rule. Why: an engineering call within the backlog item's stated aim, not science-facing or
  animal-facing. Cost, if the probe behind it was wrong: the first nightly after the merge goes red on
  the functions reading `TIMED OUT`, each then needing a test.
- **Backlog IDs across both branches.** The controller assigns them: XC-312 (import-error mutants counted
  caught) and XC-313 (`--maxfail=3` for mutant runs) go to `xc275-sweep-timeouts`; A2's own deferrals
  take XC-314 on. The XC-275 branch does not edit the CHECKPOINT; the controller records it there. Reason
  and cost: none recorded.
- **Keep the toy suites' 3 s limit.** It adds about 6 s per suite run, about 80 CI minutes per nightly by
  the implementing agent's estimate (unmeasured). Why: a 1 s child limit risks flakes on a loaded CI
  runner, and the nightly has headroom (203-259 of 360 minutes per shard). Cost: about 7 minutes per
  nightly shard.
- **Accept the two unasked additions.** The no-progress guard and the plugin's path in the gate's
  `GLOBAL` both refuse rather than pass silently, each with a test. Cost: nothing.
- **The XC-275 branch's fix round 1.** Fix the review's Important (no test tied the limit to the real
  baseline's time), plus the two pins in the permissive direction (a kill between tests with no failure
  gives `TIMED OUT`; verdicts are explicit, and an unexpected one raises), the wrong "under half the
  limit" comment (mutate.py:105), and XC-140 kept open for the speed residue (`service.step`'s exit hang
  of about 200 s). Cost: nothing.

## The final review and its fix wave

- **Fix all three Importants in one fix wave.** I1 (`check()` raised on a parameter range whose bound is
  not a number) is a regression A2 made. I2 (ADR-0011 never said a record's primaries and spectra are
  black-subtracted) is a docs consequence of the PI-approved black-subtraction (call 13), not a new
  choice: the math is only right if the primaries and spectra exclude the black. I3 (a cone color offered
  by a `Look`'s fill or outline parameter got past `isoluminance-on-default`) is the PI's isoluminance
  rule end to end, about 6 lines (`_colors` walks a Look's fill and outline parameter choices as `_parts`
  and `_lit` do), with XC-271 narrowed to its other half (a fill parameter gets no light check, and
  `resolve`'s misleading A3 message). Cost, if I3 is wrong: extra findings on tasks offering looks by
  parameter.
- **The same wave fixes the reviewer's smaller items.** Its fix-before-merge minors (ADR-0004's blank
  line; the `_NUMBERS` comment; `assert steps(ConeContrast(L=0.1))`; `_claims_isoluminance`'s docstring
  against the DKL half, and its 168-character line; a test of `exact.py`'s clip; `{worst:.7g}`), its new
  docs minors (ADR-0004's numpy row "Fitting only" is stale, since `photometry`, `check` and `taskd` now
  import numpy through `cones`; `photometry`'s module docstring, lines 9-13, describes the retired rule),
  Task 11's re-review minors (the CHECKPOINT sweep paragraph's overlap; the stale
  `tasks/visual_search_training.py` docstring, lines 3-4), and the three deferred cone-matrix minors
  (Task 2's: `cone_xyz` inverts the matrix on every call, against an absolute singularity threshold; Task
  5's two: a record with radiances near 1e308 loads with a non-finite matrix, and one with three
  identical spectra loads with a singular matrix that is refused only later, by a sentence naming no
  calibration), folded into XC-315's line (invert once in `_convert`, inside its `try`; refuse a
  non-finite or singular matrix with a sentence naming the calibration). Every other deferred minor the
  reviewer triaged "drop" is dropped, for the reasons the reviewer gave in its report to the controller;
  that report is not copied into the repository. Cost: nothing.
- **No second fix wave** (the skill's rule). The CHECKPOINT's residuals (the counts, the review done, the
  fix wave's commits, which runs cover what, the XC-275 branch for the PI) are fixed in a docs-only
  commit now, so the entry point is true at the pushed tip. Two residuals are dropped as minor: a NaN
  range bound is still refused, but by a sentence that does not name the bound; and XC-309's line and
  `Spectra`'s docstring name only the transfers as black-subtracted. Cost: a less precise refusal
  sentence for a NaN bound.
