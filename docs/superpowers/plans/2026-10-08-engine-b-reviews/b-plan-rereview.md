> Working file of 2026-10-08, committed with the plan it reviewed (`docs/superpowers/plans/2026-10-08-engine-b.md`). "The draft" is that plan before it was committed; line numbers and `.superpowers/drafts/` paths below are the draft's at the time.

# Build B plan: re-review of the revision (2026-10-08)

Revised draft: `.superpowers/drafts/2026-10-08-engine-b-plan.md` (3,840 lines). "Draft N" below is
a line of that file. Code read only at snapshot `5c385a7` (extracted to a scratchpad, never the
working tree); "file:N" is a line of the snapshot. No suite ran. To check the plan's
numbers I ran a few `python3 -I` probes against the snapshot copy in the scratchpad, never the
repo: the solved sRGB primaries, the 7.6e-7 threshold gap, the measured record's gamut, sentence
lengths, and `check()` on the new light-factor trials. I also fetched the W3C sRGB page.

## What holds (checked, no finding)

- **C1/I2 end to end.** `Service.__init__` catches the load (`SystemExit` and `Exception`, draft
  1994-2002), so `wlx taskd` starts (service.py:1160-1188 builds `Service` after `_load_rig` and
  nothing else reads the record). `_open` offers only entries the kind accepts (draft 2750-2753), so
  an unloaded record (`of_unloaded`, accepted in no kind) and an after-today one (`of_calibration`,
  `()`) never refuse an open, and the departure is marked as before (service.py:669-704). Every
  run's pre-flight fails with the sentence: `warned()` is inside `_contained` (draft 3057-3073),
  `refused` comes before `owed` (draft 3007-3010), and `gate` fails the run on any fail
  (preflight.py:357-360). `_end`, `_unended` and `_close_stranded` are untouched. A resume builds
  with the service's calibration (`_build`, draft 2005) and its runs fail the same way. The
  out-of-cage clock reads none of this. The tests trace correctly: draft 1878-1898,
  2629-2644 and 2921-2942.
- **Call 19 (`SessionSpec.calibration` may be `None`)** is the right call against the alternatives.
  Handing the session `SRGB` would write `srgb-standard` into `config.json` for a rig that named a
  record. A sentinel calibration would be a second silent default (Call 14). Every reader is
  guarded:
  - `Session.run`: the backstop at draft 1949-1956 sits before both `check` and the start row's
    `.id` (draft 1971).
  - `_fixed_config` (draft 1977) and `Telemetry.of` (draft 2440).
  - `preflight.task` → `check(calibration=None)`, which is legal (check.py:47, 954, 984).
  - `cli.render` (draft 2526) and `web._setup` (draft 3750).
  - `resume.read`, which never reads `config.json`'s calibration (resume.py:83-226).
  - `stranded.restore`, which builds no `SessionSpec`.

  `wlx run` and `wlx check` never hold `None`.
- **I1.** The write is `_open`'s last line, after `self.session = session` (draft 2765-2772), and
  it is uncaught, as `record_departure`, `Session.open` and `head_fixed` are (service.py:699-702).
  The test (draft 2672-2696) is sound. `disk_full`'s signature matches the call,
  `pytest.raises` wraps `step()`, and `stranded.find` then finds the session resumable
  (stranded.py:68-72). See I-1 for how the welfare item describes this.
- **I3.** `_start` writes nothing: `carried`, `of_unknowns` and `rows` are reads (draft
  3103-3132). `Session.run` writes the accepted rows after both refusals and before `run_index`
  moves (draft 3146-3148; taskd.py:1993-2008), so a fault there is `_run`'s "the run did not
  start" (service.py:963-974). The test at draft 2945-2960 traces.
- **I4, I5, I6, I8, I9, I10, I11** are carried out. The light-factor trials, probed on the snapshot
  with the solved sRGB calibration, make `check()` raise nothing (RDS adds `needs-stereoscope`,
  which the test ignores). The W3C page (v1.10) states "Luminance level: 80 cd/m2", Table 0.2's
  primaries and D65, and "During standardization, a small numerical error caused by rounding
  error was corrected". The equations are images, as the plan says.

  Numbers re-computed and confirmed:
  - The solved primaries are (17.011, 57.213, 5.775) and give white (1, 1, 1) within 2e-16.
  - The rounded coefficients give (1.00018, 0.99996, 0.99989).
  - The 0.03928/0.04045 gap is 7.55e-7.
  - The measured test record's 80 cd/m² gray weighs (0.41, 0.40, 0.42).
  - The default calibration's sentence is 270 characters.

  The IDs XC-272/273/274 are consistent everywhere (7, 5 and 5 mentions), with the
  "provisional" line. The backlog's Next free ID at the snapshot is XC-272 (backlog.md:18), and
  XC-013's quoted field matches backlog.md:36 exactly.
- **I7 and its re-scan.** Every construction site the tasks break is listed:
  - `SessionSpec(`, `OpenSession(`, `Telemetry(` and `Idle(`.
  - The `open` bodies.
  - Both `_SETUP`s and every `*_SETUP` user.
  - `UNKNOWN`/`CHECKED` and the exact item lists.
  - The nine schema literals.
  - `preflight.task`'s five callers.
  - The resume and stranded `_config`s.

  Unlisted tests that touch the same values still pass as written:
  - test_serve.py:4192-4216 (substring and per-run maps).
  - test_service.py:1167 (only `out of cage` fails).
  - test_serve.py:4941-4949 (warnings rows' `by` is the member).
  - test_web.py:724-735 (new divs carry their fragments).
  - test_web.py:1543 (carried rows don't match `_frames`' warning).
- **"Prove it can fail."** Every break in Tasks 8-14 fails its named test, except Task 8's Break 4
  (Minor 8). I checked Task 11's Break 5 in particular: `Session.left_cage` writes the departure
  row and creates the folder (taskd.py:742-776), so the test does fail.
- **Welfare list.** No function on architecture.md's list changes except `_open` and `_start`
  (architecture.md:80-87). The byte-for-byte list in draft 85 covers the rest of that list.
- **PI-facing sections.** Both are present and in plain terms. Q1 carries the I9 correction
  (draft 47). Q2 carries the "nothing records on the default until build J" consequence (draft
  53), as does item 4 of "What the PI should know".

## Critical

None.

## Important

**I-1. Welfare item 1, the text the PI approves, misdescribes `_open` twice (draft 80; the same
claim in Call 22, draft 112).**

The plan's code is right. The words are not.

1. "The departure, its far-mark question and every existing refusal run as before, **after the new
   check**." Four existing refusals run *before* it:
   - a session already open (service.py:633-640);
   - an animal stranded (service.py:642-654);
   - an answer nobody was asked for (service.py:657-664);
   - a session that cannot be built (`_built`, service.py:665-667; the plan inserts after it,
     draft 2741).

   Only the departure, its question and its refusals (service.py:668-697) come after.
2. "A fault writing those rows is treated as a fault in the open's other writes after the departure
   **already is**: `wlx taskd` stops, recording the animal's return as not recorded". That is not
   how the other writes are treated today. `record_departure`, `Session.open` and `head_fixed`
   (service.py:699-702) run *before* `self.session = session` (service.py:704). The fault handler
   calls `shutdown` only for a held session (service.py:1221). So a fault in those writes stops
   `wlx taskd` with no "return not recorded" row and no "session ended" row. Only the new write,
   made once the session is held, gets both. Either way the session is found stranded at the next
   start, so the behavior is sound.

   Call 22's clause "`_marks.record_departure`, `Session.open` and `head_fixed` each raise out of
   the service loop to `wlx taskd`'s fault handler, which, with a session held, records…" implies
   the same parity. The code comment at draft 2768-2771 is accurate.

**Smallest fix (text only).** In welfare item 1, replace "The departure, its far-mark question and
every existing refusal run as before, after the new check." with:

> The refusals an open already has run first, as before (a session already open, an animal
> stranded, an answer nobody asked for, a session that cannot be built); then the new check;
> then the departure and its far-mark question, as before.

Replace the last sentence with:

> A fault writing those rows is not caught, as the open's other writes after the departure are
> not, so `wlx taskd` stops; because the service already holds the session by then, it first
> records the animal's return as not recorded and the session as ended (a fault in the earlier
> writes stops it without those two rows). Either way its next start finds the session stranded,
> to resume or to take the return.

In Call 22, change "which, with a session held, records" to "which records only a held session's
return as not recorded and its end (this write's case; the three earlier writes happen before the
service holds the session)".

## Minor

1. **`_open` calls `open_warnings` uncontained** (draft 2750-2753). Call 27 contained the same
   listing for idle frames (draft 2497-2511).
   - A raise here comes before the departure is marked, and leaves `step`.
   - `run`'s handler then stops `wlx taskd` with no session held (service.py:1216-1231), against
     the C1 principle that a calibration problem is never the service's end.
   - Nothing in it can raise today: the record is validated at load, and `Deployment` is checked by
     the link (link.py:1769-1774).

   Fix: wrap the call in `_open` and refuse the open with "the warnings an open asks to accept
   could not be listed: …", before anything is marked. Add that clause to welfare item 1.
2. **The idle listing's fault row is said as something every run refuses.** It has
   `accepted_in=()` (draft 2506-2510). So `_render_idle` prints "every run refuses: warnings: …"
   (draft 2542-2545), and `_warning_row` prints "no session kind accepts this: every run's
   pre-flight fails on it" (draft 3664-3668). Neither is true of a listing fault. Fix: render a row
   whose code is `warnings` as "could not be listed" in both places.
3. **Call 25 (draft 115) checks the link's limits but not the page's own.** `serve.BODY_LIMIT` is
   4096 bytes (serve.py:466) and bounds every `POST /commands` body. The worst case fits with room
   to spare:
   - the default calibration's sentence: 270 characters (272 bytes);
   - head free: 111;
   - the age sentence: at most 193 with `ID_LIMIT` 64;
   - at most two offered;
   - `amend_reason` at most 500;
   - total about 1.3 KB.

   No other command carries a sentence. Frames have no length check on decode (link.py:1024-1077).
   Fix: one sentence in Call 25 naming `BODY_LIMIT` and that margin, so a later rig warning cannot
   quietly push an open past it.
4. **`gate`'s bare-string guard is no longer reached on `_start`'s path.** `_start` hands `gate`
   the set `named | set(carried)` (draft 3109-3110). `gate`'s fail-closed guard against a bare
   string (preflight.py:348) therefore never sees what was sent, and `rows` still raises on a
   string (preflight.py:383), now after the gate has passed. This is harmless while
   `_command_from` admits only a list or tuple of names (link.py:1837-1845). Fix, keeping `gate`
   byte-identical:
   ```python
   acknowledged = command.acknowledged
   if not isinstance(acknowledged, (str, bytes)):
       acknowledged = (*acknowledged, *carried)
   why = _preflight.gate(checked, acknowledged)
   ```
5. **Welfare item 3 (draft 82) implies one box per warning.** "Warnings not yet accepted this
   session are an unknown, acknowledged by name". In fact one box, named `warnings`, accepts every
   warning it lists (draft 3117), and each is then recorded. Say so in plain terms.
6. **The "for information" paragraph (draft 85) should mention `stranded.find`.** `stranded.py`
   stays byte-identical, but its `find` now marks two more kinds of record not resumable, through
   `resume.read` (stranded.py:68-72; Tasks 7 and 9):
   - a record written before B;
   - one whose `warnings.jsonl` is damaged.

   The return is still taken. One clause beside Call 12 covers it.
7. **Two new choices sit inside fragments that the stream replaces.** `kind-sel` is inside
   `setup` (draft 3761-3776) and `dn-accept` is inside `dn-warnings` (draft 3695-3703). `swap`
   replaces a fragment whenever it changes (serve.py:1412; web.py:2245-2254). It restores a
   person's choice only when the fragment node is itself a SELECT. This is the b3a-2 plan's
   decision 11, pinned by test_web.py:1920-1934.
   - For `dn-accept`, the reset is the wanted behavior when the list changes. Say so in Task 15.
   - For `kind-sel`, restore the chosen value after the swap (as `choose` does), or move the
     control out of the fragment.
8. **Task 8 Break 4 (draft 2027) fails for a reason other than the one it names.** Moving the load
   below `session.open` makes the earlier `check(..., calibration=calibration)` raise
   `UnboundLocalError` before the folder exists. Fix: break it as "catch the load's `SystemExit` in
   `wlx run` and fall back to `SRGB`". The test then fails because the session ran.
9. **Task 8 Step 2 (draft 1932) predicts the wrong failure.** It says the `SessionSpec` TypeError
   comes "at collection". It comes at test time: every construction site is inside a function
   (`_sessions.session`, test_taskd.py:135, test_gaze.py:645/751, test_serve.py:432).
10. **Task 11's reworded comment (draft 2777) lands on a branch whose meaning B changes.** The
    comment sits on `if panel is None and isinstance(color, Gray)` (check.py:954). After Task 8
    the default is `SRGB`, not `None`. That branch now means "no calibration at all": `wlx taskd`
    while the record will not load, or a direct `check()` call. Reword it to say so.
11. **Test name (draft 2672).** `..._leaves_the_session_held_and_its_return_recorded`: what is
    recorded is that the return was *not* recorded. Rename it
    `..._and_records_that_its_return_was_not`.
12. **`wlx taskd` says nothing at its terminal when the record will not load.** It prints only its
    endpoints and stranded sessions (service.py:1192-1203). Add one line there with
    `calibration_refused`.
13. **The real page cannot open a session mid-branch.** From Task 7 the page's dialog sends no
    `session_kind`, and from Task 11 no `accepted`, so every open from the real page is refused
    until Task 15. No test drives `openSession` end to end, so the suite stays green. That is
    acceptable on a branch that merges whole. A sentence in Task 7 would spare someone testing by
    hand.

## Note for the controller (not a finding)

The I1 ruling asked for a test that "a raising `accept` leaves `self.session` set and the departure
ending normally". The revision reads "normally" as the fault handler's path: the session is
stranded, then resumed or returned. That follows "handled the way `_open`'s other post-open writes
are".

If "normally" meant the return taken with `wlx taskd` still up, the alternative is safe. Catching
the fault after `self.session = session` and putting a refusal on the session's feed loses nothing.
Every run's pre-flight lists the rig's warnings again (`warned()` includes
`calibration_warnings()` and `of_deployment`, draft 3058-3061), so an unrecorded open acceptance
is asked again at the first run. That would be a welfare-item change, so it is the controller's
call, not the reviser's.

## Verdict

**Needs another revision.** It is small:
- I-1 is a text fix to welfare item 1 and Call 22, with no code change.
- The Minors can go in the same pass.

The C1/I1/I3 code paths are correct as written and need no re-review after it.
