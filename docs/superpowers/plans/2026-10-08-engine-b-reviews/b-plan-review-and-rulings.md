> Working file of 2026-10-08, committed with the plan it reviewed (`docs/superpowers/plans/2026-10-08-engine-b.md`). "The draft" is that plan before it was committed; line numbers and `.superpowers/drafts/` paths below are the draft's at the time.

# Build B plan draft: the review's findings and the controller's rulings (2026-10-08)

Draft under revision: `.superpowers/drafts/2026-10-08-engine-b-plan.md` (backup of the pre-review
version outside the repo). Line numbers below are the draft's, before revision. File:line references
into `wl_xcon/` and `tests/` are to branch a1-followups.

Each finding is followed by **Ruling:** — what the revision does. Where a ruling says "accept", do
what the finding's fix says.

## Critical

**C1. `wlx taskd` refuses to start when the calibration record will not load.** Plan Task 8, lines
1866-1872 (`Service.__init__` calls `_load_calibration`; its `SystemExit` stops `wlx taskd`); Review
Focus 3 (line 114) and the test at lines 1713-1717 require it. A stranded session's return is taken
only through a running `wlx taskd` (`Service._end` → `_close_stranded`, `wl_xcon/service.py:1058`);
`wlx run` refuses an existing session folder (`wl_xcon/cli.py:1588`). So after a crash, a bad record
means nothing in software can record the animal's return. The codebase deliberately keeps unreadable
records from stopping `wlx taskd` (`resume.read`'s docstring).

**Ruling (C1 and I2 together):** a calibration problem — a record that will not load, or one dated
after today — **never stops `wlx taskd` from starting and never refuses an open.** `wlx taskd` loads
the record at start and keeps the error; every run's pre-flight **fails** on it, with the sentence,
so nothing is drawn on a display whose description is broken; `EndSession`, stranded returns and the
cage-to-cage clock are untouched by it. `_open`'s only new refusal is the operator's: the warnings it
lists were not all accepted on the form. Warnings that the session's kind does not accept are not
offered for acceptance at the open; they fail each run instead (the `warnings` item, through
`refused`). Rewrite welfare item 1, Review Focus 3, Task 6's and Task 10's future-date behavior,
their tests and the Calls to match. `wlx check` and `wlx run` (no animal is waiting on them) may still
refuse a bad record outright; say which in a Call.

## Important — welfare

**I1. In `_open`, `session.accept(...)` runs between `session.open()` and `self.session = session`**
(plan lines 2162-2166; repo `wl_xcon/service.py:699-704`). A raise there escapes after the departure
is marked while `self.session` is still `None`; the draft's own Break 3 (line 2171) shows `accept`
raising out of `_open`; `service.run`'s fault handler (`service.py:1215-1229`) then records neither
"return not recorded" nor a session end.
**Ruling:** accept: the write happens after `self.session = session`, and a fault in it is handled
the way `_open`'s other post-open writes are (read how they are handled and follow it; say which in
the task). Add a test that a raising `accept` leaves `self.session` set and the departure ending
normally.

**I2. A calibration dated after today refuses every open, and is not among the Calls** (Task 6, lines
1390-1394; Task 10, lines 2143-2151; welfare item 1). **Ruling:** see C1.

**I3. `Service._start` (welfare-critical) gains a write outside the run's fault containment**
(`session.accept(newly, ...)` at plan line 2401). Today `_start` writes nothing; every write for a
run happens inside `_run`, whose faults are contained (`service.py:947-974`).
**Ruling:** accept: hand `newly` to the run; the rows are written when the run starts, inside
`_run`. Rewrite welfare item 2/3's wording if it changes what `_start` does.

## Important — correctness against the code

**I4. B makes XC-269 reachable in every session.** The new standard branch at line 1029 evaluates
`color.lum == 0.0 and color.magnitude()`; a `DKL(lum=0.0, l_m=P("c"))` makes `magnitude()` raise
TypeError (`photometry.py:61-62`). After Task 8 every session, `wlx check` and `wlx run` check
against `SRGB`, so in `wlx taskd` it becomes "checks did not finish" and in `wlx run`/`wlx check` a
traceback. **Ruling:** accept: on the default calibration never evaluate `magnitude()` unless every
component is a number (every DKL there is blocking anyway); add the test; the task that does this
narrows XC-269's line to the measured-calibration case (still waiting on A2) in its own commit.

**I5. `_parameter_lights` (lines 1066-1087) misses parameterized contrast and color on `Plaid`,
`Checkerboard`, `Noise` and `RDS`**: `_light` returns `None` for those (`check.py:1029-1044`; their
fields at `task.py:604-646, 721-747`); test_engine_path's "noise" case passes the checker today. It
also compares appearance choices through `_light`, so `Noise(RMS(0.1))` and `Noise(RMS(0.2))`
compare equal and are not counted as a factor. Under Q2-A (meant to fail closed)
`Checkerboard(contrast=Michelson(P("c")))` would record on the default. **Ruling:** accept: walk
each appearance's `color`, `contrast` and `mean` fields (and a `Look`'s fill and outline)
generically, compare choices by those fields; tests for Checkerboard, Plaid, Noise, RDS and a Look.
Note backlog XC-271 (a Look whose fill is a parameter gets no light check): make the walk handle a
fill parameter's choices so B does not inherit that blind spot.

**I6. Task 2 misses one test calibration**: `tests/test_engine_path.py:49-57`'s `PANEL` has
`measured_on="unmeasured"`; the new `__post_init__` raises at import, so the file fails to collect.
**Ruling:** accept: add it to Task 2's Files and steps.

**I7. Existing tests the tasks break but do not list** ("each task leaves the suite green" fails):
- Task 7: `tests/test_serve.py:1211` `_SETUP` (used by `wlx run` at 1342 and 3198) has no `--kind`;
  `tests/test_resume.py:51` `_config()` has no `session_kind`, so every resume test refuses with
  `PREDATES_KINDS`.
- Task 9: the stand-in session at `tests/test_link.py:138` needs `spec.session_kind`,
  `spec.calibration` and `warnings`; nine literal schema-14 assertions in `test_link.py` (2039, 2102,
  2110, 2204, 2260, 2282, 2411, 2481, 2498); the `Telemetry(...)` fixture at `tests/test_cli.py:944`.
- Task 11: `tests/test_service.py:933` (exact item list) and `:987` (`CHECKED`) need the `warnings`
  item; `tests/test_serve.py:4098` expects the same unknowns for runs 0 and 1 of one session, but run
  1's `warnings` item passes; `tests/test_preflight.py:35,122` unpack `item, _ = preflight.task(...)`,
  which now returns three values.
- Task 12: `tests/test_cli.py:141` and `:169` assert "no findings" for the good task, which now
  carries `contrast-on-default`: define the warnings-only summary line and update both.
**Ruling:** accept: add each to its task's Files and steps, with the exact edit. Re-scan every task
for others of this class (grep the tests for each changed signature, schema number and item list).

**I8. Task 13's proof that its test can fail cannot fail**: `Session.run` already sets
`self.preflight = None` (`taskd.py:2021`). **Ruling:** accept: take a `CheckRun` before
`SetSessionKind`, then assert the pre-flight is dropped.

## Important — questions and spec fidelity

**I9. Q1-A's rationale is unverified**: "the panel's sRGB mode can be set so its white reads about 80
cd/m²" — spec §25 lists the panel's sRGB mode as UNVERIFIED. **Ruling:** accept: mark it UNVERIFIED
with a pointer to §25; the recommendation stands on "one published definition".

**I10. Deferred items are not filed** (CLAUDE.md: an item goes in the moment it is deferred): call
16's OLED-maintenance refusal (spec §20.2) has no backlog line; XC-013 (demo mode) waits on this
build, so its line should be updated. **Ruling:** the plan's items deferred *by the plan* are filed
by the commit that commits the plan, not by Task 15: add a short section near the top, "Filed when
this plan is committed", with each backlog line in full (mid-run pause; fixed-head task in a chaired
session; OLED-maintenance refusal) and the XC-013 edit. Task 15 then files only what execution
defers.

**I11. Backlog IDs collide.** XC-269, XC-270 and XC-271 are now taken (a1-followups). **Ruling:**
use **XC-272** (mid-run pause), **XC-273** (fixed-head task in a chaired session), **XC-274**
(OLED-maintenance refusal), and put one line in that section: "IDs provisional: renumber from
docs/backlog.md's Next free ID when this plan is committed." Every other mention (calls, task
steps, spec notes, warnlist docstring) uses the same three IDs, so a renumber is a search and
replace.

## Minor — rulings

- Task 9: `cli.render`'s new lines print wire strings without `_printable` (required, `cli.py:882`).
  **Accept.**
- Call 7 vs the open: the open matches accepted warnings by code only (line 2152); match by code
  **and** sentence, as call 7 says. **Accept.**
- Task 12: put `wlx run`'s `session.accept` inside the `try` that follows `session.open`
  (`cli.py:1724`). **Accept.**
- Missing test imports — test_record: `WARNINGS`, `_local`; test_service: `date`, `timedelta`,
  `datetime`, `dataclasses`, `Entry`, `SESSION_KINDS`, `SetSessionKind`; test_link: `_sessions`,
  `Entry`, `WarningRow`, `_telemetry_out`; test_taskd: `Entry`, `NOT_RECORDING`, `SESSION_KINDS`,
  `Preflight`, `PreflightItem`, `Box`. **Accept** (after any renames below).
- Task 4 Step 3: three more new tests already pass before the change (gray above white, measured
  calibration, shape-only choices). **Accept: say so.**
- Mutation sweeps in Tasks 6 and 15 omit `--returns None` (`mutate.py` defaults to `[]`; the gate's
  `RETURNS` says `None`). **Accept.**
- Review Focus 3 not pinned for `wlx check` or `wlx run` end to end: add one `main([...])` case each
  (consistent with the C1 ruling's Call). **Accept.**
- Page: carried pre-flight items still render as unknown with an acknowledge box
  (`web.py:686-699`); show who accepted them earlier this session. **Accept.**
- Resume after the rig's calibration changed keeps the old calibration id in `config.json`.
  **Ruling:** record the calibration id on each run's start row (do not refuse the resume).
- Call 14: `SessionSpec.calibration=SRGB` is a second silent default, against the house rule for
  `deployment` and `geometry`. **Accept: make it required; pass `SRGB` explicitly in the test helper.**
- Task 14: the Q5-B control is a placeholder (no test code; `_setup` takes no `view` for `_gate`).
  **Accept: write it out in full** — the plan builds Q5-B, so its task must be complete.
- Citation: "0.03928, read 2026-10-07" is not in the cited A2 research doc. **Ruling:** fetch the W3C
  sRGB page (https://www.w3.org/Graphics/Color/sRGB.html, v1.10) and cite it with today's as-of date
  if it states 0.03928; otherwise mark UNVERIFIED. Do not substitute 0.04045 without a source.
- Naming: `record.WARNINGS` and `preflight.WARNINGS` mean different things; `Entry.said` sits beside
  `Finding.detail`. **Accept: give them distinct names; follow `Finding`'s field name.**
- XC-243's line is removed in Task 15, not in the commit that does the work. **Accept: remove it in
  the commit that closes it.**
- Idle frames: `Service.publish` computes the warnings on every idle pass (the stranded-return path).
  **Accept: compute them once per calendar day, and contain a fault so it never stops publishing.**
- Task 9 tests: "both shapes" refused by schema tested for `Telemetry` only; add `Idle`. **Accept.**
- Task 8 is large. **Split it only if a reviewer could reject one half and approve the other;**
  renumber tasks consistently if you do.
- wl-preproc ask: update the pending §21 ask's text in this repo's docs with the real fields
  (`config.json`'s `session_kind`, `warnings.jsonl`). **Accept as a doc edit in the task that lands
  those fields; nothing is sent.**

## What the PI should know (add near the top, before the Questions, in plain terms)

1. The `visual_search_training` variant cannot be started from the page in this build: its other
   numbers have no starting values (XC-183), so it runs only through `wlx run --set`.
2. Every DKL color on the default calibration is refused in every session kind until A2. That is
   stricter than his 2026-10-07 rule (training and piloting run with the warning); A2's research asks
   him about the default's cone colors separately.
3. The pump-calibration and eye-tracker acknowledgements are taken at the first run that asks, not at
   the open: the open has no pre-flight, and his 2026-10-07 answer says a warning appearing later asks
   again. (Call 6 — keep it, say it here.)
4. With Q1-A and Q2-A, no lab task can record on the default calibration; recording waits for a
   measured calibration (build J, which needs E and the instrument). Put this consequence inside Q2's
   text as well.
5. The calibration record's fields will grow in A2 and J (spectra, cone fundamentals); because unknown
   fields are refused, the ADR's field list is provisional.

---

# Round 2: the re-review's findings (`.superpowers/drafts/b-plan-rereview.md`) and the controller's rulings

- **I-1 (welfare item 1 and Call 22 wording).** Accept the re-review's replacement text exactly
  (its "Smallest fix" section), adjusted only for Minor 1's ruling below.
- **Note for the controller (catch the accept fault, or let `wlx taskd` stop?).** Ruling: keep the
  revision's choice — the write is not caught; `wlx taskd` stops; the held session's return is
  recorded as not recorded and its end; the next start finds it stranded. This is the existing fault
  design (a disk fault mid-open is not something to carry on through), and it changes no behavior
  beyond what welfare item 1 now states. No edit needed beyond I-1's text.
- **Minor 1 (`open_warnings` uncontained in `_open`).** Ruling, *not* the re-review's fix: a fault
  listing the warnings never refuses an open (the C1 principle: a warnings or calibration problem is
  never the end of the service or a refused open). Contain the call; on a fault the open proceeds
  with nothing offered for acceptance, the fault is kept, and every run's pre-flight fails on it
  ("the warnings could not be listed: …"), as `warned()` already does inside `_contained`. Add a
  test, a break, and one plain-terms clause to welfare item 1 ("if the warnings cannot be listed,
  the open goes ahead and no run can start until they can").
- **Minors 2-13.** Accept each as the re-review states it; for Minor 7, restore `kind-sel`'s chosen
  value after the swap (as `choose` does) and say in Task 15 that `dn-accept`'s reset on a changed
  list is intended; for Minor 8, use the re-review's break; for Minor 11, use its test name.
