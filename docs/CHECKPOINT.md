# Where this build is

**Last updated 2026-11-18**, at the commit this file was committed in (`git log -1 -- docs/CHECKPOINT.md`). **This page
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
- **`main` is `89f7b94`**: demo mode (XC-013), merged 2026-11-17 on the PI's "Merge it", after his welfare review
  (`_open`'s two changes, approved as built), his Safari try-out (his find fixed: an eye already in a window as its
  state begins has entered it, EYE-30) and a clean CI (push 44086214727; full sweep by hand 44086213776, 1608 caught,
  none survived, shards 34 and 35 cut at 6 h, XC-500). wl-preproc was told the commit (XC-502's marking, on its own
  order). Before it: the pop-out search and the XC-491 answers; wl-preproc's pop-out reader is on its main, `d8fe06b`.
- **`console-build-2026-11-17`** (worktree `.claude/worktrees/console-build-2026-11-17`, **not pushed**): the console
  settings build, Tasks 1 to 12 (design `docs/superpowers/specs/2026-11-16-console-settings-design.md`, plan
  `docs/superpowers/plans/2026-11-16-console-settings.md`), built on `main` `89f7b94`; **6379 passed**, none skipped.
  Its wl-xtasks half is the branch **`console-settings-2026-11-16`** (`da695de`, from wl-xtasks `64929fe`, not merged,
  not pushed), which the PI reviews. Filed by the build: XC-516 to XC-519. Open for the PI at review: the DKL default
  contrast (some directions give no possible light), and the whole-build review's list (the plan's ledger, git-ignored,
  in the worktree's `.superpowers/sdd/2026-11-16-console-settings/progress.md`).
- **`tryout-design-2026-11-17`** (worktree `.claude/worktrees/tryout-design-2026-11-17`, not pushed): the pop-out's
  revision, designed with the PI and approved (`...-popout-revision-design.md`, plan `...-popout-revision.md`, 8 tasks,
  ask XC-514, codes from 4139). Its counter text must say XC-520 (the next free) when it is built.
- **wl-preproc** has XC-513 (the console settings' record shapes) and its 2026-11-18 addendum (block end `shaping`, a
  revert of the switch writing a `shaping` row), both sent by message, and **has not answered**. Acceptance is the PI's
  call in that session; we build to our names meanwhile.

## What exists
- **Tasks**: the task object and its load check (`task.py`, `check.py`), engine builds A1 to C3; five reference
  tasks in `tasks/` are engine fixtures; real tasks come from wl-xtasks, written with the PI. **The first real task,
  the pop-out search**, is wl-xtasks' `tasks/popout_search.py` (its main, `64929fe`), tested here by path
  (`tests/test_popout_search.py`); its design `docs/superpowers/specs/2026-11-07-popout-search-design.md`. Two facts
  a session gets wrong: a crashed session's first run goes on from the run its process stopped in
  (`Session._going_on`), the previous session's end only *shown* at a start; a value held at a staircase's hardest
  level counts toward moving up.
- **Running**: the trial loop, daemon and CLI (`run.py`, `taskd.py`, `cli.py`); the simulated animal and eye.
- **The console**: a page on the LAN (`serve.py`, `web.py`, `link.py`), writes from the box only; wl.works sign-in
  waits on the rig's https page (XC-151, XC-152).
- **Demo mode** (`wlx demo <task>`; XC-013): the mouse as the eye (`pointer.py`), the exact drawer's frames on the
  page (`demoscreen.py`), `POST /gaze`, `wlx taskd --demo`, `wlx demo` (`demo.py`), and a demo from a live rig's page
  (`--demo-root`, `--link`'s fourth endpoint). Open: XC-506 (fidelity), XC-509 (the rig lock on macOS), XC-515
  (Ctrl-C raised where it lands in `wlx taskd` and `wlx serve`; `wlx demo` counts it, `demo.py`'s docstring).
- **Welfare** (`bounds.py`, `welfare.py`, `marks.py`, `stranded.py` and the functions architecture.md lists, held to
  `tests/welfare_manifest.json`): one limit, out of the cage to back in, eight hours (the institution's); the day's
  fluid is a floor; each delivery's size is a ceiling; a task names how reward is configured, never how much. **The
  record**: the session folder `xcon/` that wl-preproc reads (`record.py`).

## What is next (the PI, 2026-11-07, 2026-11-14 and 2026-11-16)
1. **The console settings build to merge**, in this order: one whole-build review (the most capable model); the PI's
   review of the wl-xtasks branch `console-settings-2026-11-16`; his Safari try-out; CI (a sweep by hand on the
   branch); the merge on his yes by name. **Then the pop-out revision**, from `tryout-design-2026-11-17`.
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
  one, git-ignored at `/wl-xtasks`; wl-sync at the commit `wl-preproc/pyproject.toml` pins). **6200 passed on
  `main`** (`89f7b94`); 6379 on `console-build-2026-11-17`; none skipped.
- **CI**: each push sweeps the changed modules with mutants (`tools/mutation_gate.py`), the nightly all, in 36 shards;
  a big branch runs that sweep by hand before its merge (`gh workflow run ci.yml --ref <branch>`). Read every shard's
  log to its closing line; the run's summary can be wrong.
- **The neighbors** are read weekly, by their handover files (the PI, 2026-11-07): wl-preproc, wl-sync, wl-works,
  wl-xtasks. Last read: 2026-11-07, by the audit; wl-preproc answered XC-491 and XC-502 on 2026-11-14 and its
  handover was read at `d8fe06b`. Open asks of each: `docs/pending-*-amendments.md`.
- **The welfare diff**: `tools/welfare_diff.py BASE HEAD`, item by item (`SAME`/`DIFFERS`), at every merge. **The
  session fuzzer**: `tools/fuzz_sessions.py`, read back by wl-preproc; `tests/test_fuzz_sessions.py` runs a little.
