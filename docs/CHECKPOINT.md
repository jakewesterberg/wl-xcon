# Where this build is

**Last updated 2026-11-16**, at the commit this file was committed in (`git log -1 -- docs/CHECKPOINT.md`). **This page
is the current state only, and stays one page** (the PI, 2026-11-07, after a whole-project audit). Every earlier
entry, 2026-08-31 to 2026-11-07, is in `docs/CHECKPOINT-history-2026-08-31-to-2026-11-07.md`, unchanged: read one
there only when this page or a backlog line sends you to it. A session ends by updating this page (CLAUDE.md).

## Read this, and no more
1. **This page.**
2. **`docs/backlog.md`**: everything open, one line per item; a decision for the PI is asked, never filed there.
3. **`CLAUDE.md`**: the conventions every session is bound by.
4. **The spec your work names** (`docs/superpowers/specs/2026-08-31-spec-map.md` says which) and architecture.md's section for your modules.

## The goal, and the four day-one legs
A real animal's session on a rig, its data read by wl-preproc, in January 2027 (hardware is bought at KU Leuven
from then). **Hardware verified: none.**

| Leg | Where it stands |
|---|---|
| DIO out | `dio.py`: the card's protocol, `Simulated` and `Absent` (refuses); no driver until the card is on the bench (pitfall P10). |
| Gaze in | UDP ingest, replay, calibration and online saccade detection (version 11, in step with wl-preproc's), no hardware. |
| Frame on screen | **Not built**: build E, the display process. Spike S: `docs/measurements/wh-dws0/2026-10-08-vulkan-timing/`. |
| Reward out | End to end to a simulated pump, the day's total and its floor accounted; no pump calibration until the rig. |

**The session number** comes from the sync box (wl-sync's `/session` routes, since 2026-10-19); the PI, 2026-11-07:
if the box cannot be reached the rig refuses to open and says why. Its client is XC-460; until then the operator's.

## Where the branches are
- **`main` is `1d77392`**: the pop-out search (merged 2026-11-09) and wl-preproc's XC-491 answers, merged on the
  PI's "Merge it". wl-preproc's pop-out reader is on its main, `d8fe06b`, and reads them.
- **Demo mode is built on `demo-build-2026-11-14`** (worktree `.claude/worktrees/demo-plan-2026-11-10`; its plan
  `docs/superpowers/plans/2026-11-10-demo-mode.md`, its design `docs/superpowers/specs/2026-10-06-demo-mode-design.md`),
  with main `1d77392` merged in; its whole-build review (2026-11-16: 0 Critical, 3 Important, 8 Minor) is answered,
  every finding fixed in one round. **It waits on, in order:** a scoped re-review of that round; the PI's welfare
  review of its two `Service._open` changes (two numbered items with `tools/welfare_diff.py 1d77392 HEAD`: `_open`
  `DIFFERS`, naming his approval of 2026-11-07, every other item `SAME`); his try-out in Safari, `wlx demo
  wl-xtasks/tasks/popout_search.py --set response_deadline=3.0`; and his merge, by his yes by name and a clean CI.
- **Tell him first, in plain words**: the run begins when he first points at the demo screen; after Escape the trial
  under way ends as tracker lost and the run waits until he points again; a slow glide (600 ms) can still end on the
  pop-out's own 0.3 s landing bound, the question the try-out is for, and a quick flick is the steady answer; one page
  steers at a time; colors and durations cannot be judged on the Mac's monitor; and a rig's `--demo-root` must be a
  folder of its own (a real session found there is held as the session it is, and warned of).

## What exists
- **Tasks**: the task object and its load check (`task.py`, `check.py`), engine builds A1 to C3; five reference
  tasks in `tasks/` are engine fixtures; real tasks come from wl-xtasks, written with the PI. **The first real task,
  the pop-out search**, is wl-xtasks' `tasks/popout_search.py` (its main, `64929fe`), tested here by path
  (`tests/test_popout_search.py`); its design `docs/superpowers/specs/2026-11-07-popout-search-design.md`. Two facts
  a session gets wrong: a crashed session's first run goes on from the run its process stopped in
  (`Session._going_on`), the previous session's end only *shown* at a start; a value held at a staircase's hardest
  level counts toward moving up.
- **Running**: the trial loop (`run.py`), the session daemon and CLI (`taskd.py`, `cli.py`), the simulated animal
  and eye (`simulate.py`, `simeye.py`, through the rig's gaze world, `gaze.Tracked`).
- **The console**: a browser page on the LAN (`serve.py`, `web.py`, `link.py`); writes from the box only; sign-in from
  wl.works designed, waiting on the rig's https page (XC-151, XC-152).
- **Demo mode** (on the branch above; XC-013): the mouse as the eye (`pointer.py`), the exact drawer's frames on the
  page (`demoscreen.py`), `POST /gaze`, `wlx taskd --demo`, `wlx demo` (`demo.py`), and a demo for `REFERENCE` from a
  live rig's page (`--demo-root`, `--link`'s fourth endpoint). Its fidelity limit is XC-506; the rig lock's macOS
  reach is XC-509.
- **Welfare** (`bounds.py`, `welfare.py`, `marks.py`, `stranded.py` and the functions architecture.md lists, held to
  `tests/welfare_manifest.json`): one limit, out of the cage to back in, eight hours (the institution's); the day's
  fluid is a floor; each delivery's size is a ceiling; a task names how reward is configured, never how much.
- **The record**: the session folder `xcon/` that wl-preproc reads (`record.py`).

## What is next (the PI, 2026-11-07 and 2026-11-14)
1. **Demo mode's re-review, welfare review, try-out and merge** (above).
2. **The XC-505 warning**, a side build after demo mode (the PI, 2026-11-14: "Warn when settings allow it").
3. **Then the display (build E)**, designed with the PI; "done" includes a real screen.
4. **Side work on the January path**: the sync-box client (XC-460), the operator's guide (XC-014, with a rig's demo
   set-up), the default limits file (XC-459, a welfare design with the PI), and wl-preproc's C3 fixture (XC-510).
5. **Paused until the pop-out search has run on a rig**: engine builds C4 to C9 and the rig-edit build.

**How the work is run** (the PI, 2026-11-07): a plan is a design and a list of tests, built once; one review of the
whole build, and his welfare review of any welfare-listed change; side work only on the January path; a rare edge case
is settled from his stated principles and told to him in one line; every merge waits for his yes by name and clean CI.

## Working here
- **Suite**: `WLX_REQUIRE_PREPROC=1 WLX_REQUIRE_BROWSER=1 WLX_REQUIRE_XTASKS=1 PYTHONDONTWRITEBYTECODE=1 python -m pytest -q -p
  no:cacheprovider -n auto` (a `wl-preproc` checkout or link at the root, at `d8fe06b` or later, and a `wl-xtasks`
  one, git-ignored at `/wl-xtasks`; wl-sync at the commit `wl-preproc/pyproject.toml` pins). **6187 passed on
  `demo-build-2026-11-14`**, none skipped; 5858 on `main`.
- **CI**: each push sweeps the changed modules with mutants (`tools/mutation_gate.py`), the nightly all, in 36 shards;
  a big branch runs that sweep by hand before its merge (`gh workflow run ci.yml --ref <branch>`). Read every shard's
  log to its closing line; the run's summary can be wrong.
- **The neighbors** are read weekly, by their handover files (the PI, 2026-11-07): wl-preproc, wl-sync, wl-works,
  wl-xtasks. Last read: 2026-11-07, by the audit; wl-preproc answered XC-491 and XC-502 on 2026-11-14 and its
  handover was read at `d8fe06b`. Open asks of each: `docs/pending-*-amendments.md`.
- **The welfare diff**: `tools/welfare_diff.py BASE HEAD`, item by item (`SAME`/`DIFFERS`), at every merge. **The
  session fuzzer**: `tools/fuzz_sessions.py`, read back by wl-preproc; `tests/test_fuzz_sessions.py` runs a little.
