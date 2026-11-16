# Where this build is

**Last updated 2026-11-14**, at the commit this file was committed in (`git log -1 -- docs/CHECKPOINT.md`). **This page
is the current state only, and stays one page** (the PI, 2026-11-07, after a whole-project audit). Every earlier
entry, 2026-08-31 to 2026-11-07, is in `docs/CHECKPOINT-history-2026-08-31-to-2026-11-07.md`, unchanged: read one
there only when this page or a backlog line sends you to it. A session ends by updating this page (CLAUDE.md).

## Read this, and no more
1. **This page.**
2. **`docs/backlog.md`**: everything open, one line per item; a decision for the PI is asked, never filed there.
3. **`CLAUDE.md`**: the conventions every session is bound by.
4. **The spec your work names** (`docs/superpowers/specs/2026-08-31-spec-map.md` maps them) and the section of
   `docs/design/architecture.md` for the modules you touch. Not the others.

## The goal, and the four day-one legs
A real animal's session on a rig, its data read by wl-preproc, in January 2027 (hardware is bought at KU Leuven
from then). **Hardware verified: none.**

| Leg | Where it stands |
|---|---|
| DIO out | `dio.py`: the card's protocol, `Simulated` and `Absent` (refuses); no driver for the card until it is on the bench (pitfall P10). Event words encoded with wl-preproc's frozen codec. |
| Gaze in | UDP ingest, replay, calibration and online saccade detection (saccade version 11, in step with wl-preproc's detector), proven without hardware. |
| Frame on screen | **Not built**: build E, the display process. Spike S ran on Linux (Vulkan, 1,200 of 1,200 frames at 120 Hz by driver timestamps, not light: `docs/measurements/wh-dws0/2026-10-08-vulkan-timing/`). |
| Reward out | End to end to a simulated pump, the day's total and its floor accounted. No pump calibration (millilitres to open time) until the rig. |

**The session number** comes from the sync box: wl-sync serves it since 2026-10-19 (`GET /session`,
`POST /session/open`, `POST /session/close`; its `HANDOVER-wl-expcontroller.md`, "2026-10-18, later"). The PI,
2026-11-07: if the box cannot be reached the rig refuses to open the session and says why. The client is not built
(XC-460); until it is, `wlx run --session-id` takes the number from the operator.

## Where the branches are
- **`main` is `1d77392`**: the pop-out search (merged 2026-11-09) and wl-preproc's XC-491 answers (the trial line's
  `color_realized`, a widening's confirming row naming its `suggestion`), merged on the PI's "Merge it".
  wl-preproc's pop-out reader is on its main, `d8fe06b`, and reads them; XC-491 and XC-461 are closed.
- **Demo mode is built on `demo-build-2026-11-14`** (worktree `.claude/worktrees/demo-plan-2026-11-10`; its plan
  `docs/superpowers/plans/2026-11-10-demo-mode.md`, its design `docs/superpowers/specs/2026-10-06-demo-mode-design.md`),
  with main `1d77392` merged in. **It waits on, in order:** one review of the whole build (the most capable model);
  the PI's welfare review of its two `Service._open` changes as built (two numbered items with
  `tools/welfare_diff.py 1d77392 HEAD`: `service.Service._open` `DIFFERS`, naming his approval of 2026-11-07, every
  other item `SAME`); his try-out in Safari, `wlx demo wl-xtasks/tasks/popout_search.py --set response_deadline=3.0`,
  told first that the run begins when he first points at the demo screen, and that after Escape the trial under way
  ends as tracker lost and the run waits until he points again; and his merge, by his yes by name and a clean CI.

## What exists
- **Tasks**: the task object and its load check (`task.py`, `check.py`), engine builds A1-A2 (stimuli, color), B
  (reference tasks), C1 (the task object), C2a (how trials count), C2b (plans and blocks), C3 (drawn values,
  conditions from factors, designed orders, live edits and the change log). Five reference tasks in `tasks/` are
  engine fixtures; real tasks come from wl-xtasks, written with the PI.
- **The first real task: the pop-out search**, wl-xtasks' `tasks/popout_search.py` (on wl-xtasks' main, `64929fe`),
  tested here by path (`tests/test_popout_search.py`, required in CI); its design is
  `docs/superpowers/specs/2026-11-07-popout-search-design.md`, its choices TSK-72 to TSK-75 and COL-37. What it added
  to the engine (color sets, staircases, confirmed progressions, the pool, every number a setting, the trainer's
  panel, the simulated eye) is in architecture.md. Two facts a session would otherwise get wrong: a crashed session's
  first run goes on from the run its own process stopped in (`Session._going_on`), while the previous session's end
  is only *shown* at a start (§3.6); and a value held at a staircase's hardest level counts toward moving up.
- **Running**: the trial loop (`run.py`), the session daemon and CLI (`taskd.py`, `cli.py`: `wlx run`, `wlx taskd`),
  the simulated animal (`simulate.py`; a gaze task's trials are played by the simulated eye through the rig's gaze
  world, `gaze.Tracked`).
- **The console**: a browser page on the LAN (`serve.py`, `web.py`, `link.py`); writes from the box only; sign-in from
  wl.works designed, waiting on the rig's https page (XC-151, XC-152).
- **Demo mode** (on the branch above; XC-013): the mouse as the eye through `gaze.Tracked` (`pointer.py`), the
  exact drawer's frames on the page (`demoscreen.py`), `POST /gaze`, `wlx taskd --demo`, `wlx demo` (`demo.py`), and
  a demo for `REFERENCE` from a live rig's page (`--demo-root`, `--link`'s fourth endpoint). Its fidelity limits are
  XC-506 and XC-508; the rig lock's macOS reach is XC-509.
- **Welfare** (`bounds.py`, `welfare.py`, `marks.py`, `stranded.py` and the functions architecture.md lists, held to
  `tests/welfare_manifest.json` by `tests/test_welfare_manifest.py`): one limit, out of the cage to back in, eight
  hours (the institution's); the day's fluid is a floor and no delivery is refused on volume; each delivery's size is
  a ceiling; a task names how reward is configured, never how much.
- **The record**: the session folder `xcon/` that wl-preproc reads (`record.py`).

## What is next (the PI, 2026-11-07 and 2026-11-14)
1. **Demo mode's review, welfare review, try-out and merge** (above).
2. **The XC-505 warning**, a side build after demo mode (the PI, 2026-11-14: "Warn when settings allow it"): a
   warning wherever a task's values let an answer fall inside the saccade detector's warm-up.
3. **Then the display (build E)**, designed with the PI; "done" includes a real screen.
4. **Side work on the January path**: the sync-box client (XC-460), the operator's guide (XC-014, now with a rig's
   demo set-up), the default limits file (XC-459, a welfare design with the PI), and the simulated C3 session folder
   wl-preproc asks for as a contract fixture (XC-510).
5. **Paused until the pop-out search has run on a rig**: engine builds C4 to C9 and the rig-edit build.

**How the work is run** (the PI, 2026-11-07): a plan is a design and a list of tests, built once; one review of the
whole build, and the PI's welfare review of any welfare-listed change; side work only on the January path; a rare edge
case is settled from his stated principles and told to him in one line; every merge waits for his yes by name and a
clean CI.

## Working here
- **Suite**: `WLX_REQUIRE_PREPROC=1 WLX_REQUIRE_BROWSER=1 WLX_REQUIRE_XTASKS=1 PYTHONDONTWRITEBYTECODE=1 python -m pytest -q -p
  no:cacheprovider -n auto` (a `wl-preproc` checkout or link at the root, at its `d8fe06b` or later, and a `wl-xtasks`
  one beside it, git-ignored at `/wl-xtasks`, holding `tasks/popout_search.py`; wl-sync installed at the commit
  `wl-preproc/pyproject.toml` pins). **6174 passed on `demo-build-2026-11-14`**, none skipped; 5858 on `main`.
- **CI**: each push sweeps the changed modules with mutants (`tools/mutation_gate.py`); the nightly sweeps all, in 36
  shards (the PI, 2026-11-09; a big branch starts the same sweep by hand before its merge,
  `gh workflow run ci.yml --ref <branch>`). A new branch's push sweeps against `main`, a later push only what changed
  since the last. Read every shard's log to its closing line; the run's summary can be wrong.
- **The neighbors** are read weekly, by their handover files (the PI, 2026-11-07): wl-preproc, wl-sync, wl-works,
  wl-xtasks. Last read: 2026-11-07, by the audit; wl-preproc answered XC-491 and XC-502 by message on 2026-11-14,
  and its handover was read at `d8fe06b` that day. Open asks of each: `docs/pending-*-amendments.md`.
- **The welfare diff**: `tools/welfare_diff.py BASE HEAD` lists the welfare-listed code between two revisions item by item
  (`SAME`/`DIFFERS`); run it at every merge (architecture.md, "Welfare-critical modules").
- **The session fuzzer**: `tools/fuzz_sessions.py`, random tasks through `taskd.Session.run`, read back by wl-preproc and
  checked against the C2b and C3 invariants; `tests/test_fuzz_sessions.py` runs a small budget on every push.
