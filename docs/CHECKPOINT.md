# Where this build is

**Last updated 2026-11-08**, at the commit this file was committed in (`git log -1 -- docs/CHECKPOINT.md`). **This page
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

## What exists
- **Tasks**: the task object and its load check (`task.py`, `check.py`), engine builds A1-A2 (stimuli, color), B
  (reference tasks), C1 (the task object), C2a (how trials count), C2b (plans and blocks), C3 (drawn values,
  conditions from factors, designed orders, live edits and the change log). Five reference tasks in `tasks/` are
  engine fixtures; real tasks come from wl-xtasks, written with the PI.
- **The first real task: the pop-out search**, wl-xtasks' `tasks/popout_search.py`, on wl-xtasks' main since the PI's
  "Merge it" (2026-11-08, `c1a61e9`; its later edits on branch `popout-search-2026-11-08b`), tested here by path
  (`tests/test_popout_search.py`); its design is `docs/superpowers/specs/2026-11-07-popout-search-design.md`, its
  choices TSK-72 to TSK-75 and COL-37.
  Built on branch `popout-build-2026-11-07`, reviewed whole and its fix round done. What it added to the engine
  (color sets, staircases, confirmed progressions, the pool, every number a setting, the trainer's panel, the
  simulated eye) is in architecture.md. Two facts a session would otherwise get wrong: a crashed session's first run
  goes on from the run its own process stopped in (`Session._going_on`), while the previous session's end is only
  *shown* at a start (§3.6); and a value held at a staircase's hardest level counts toward moving up.
- **Running**: the trial loop (`run.py`), the session daemon and CLI (`taskd.py`, `cli.py`: `wlx run`, `wlx taskd`),
  the simulated animal (`simulate.py`; a gaze task's trials are played by the simulated eye through the rig's gaze
  world, `gaze.Tracked`).
- **The console**: a browser page on the LAN (`serve.py`, `web.py`, `link.py`); writes from the box only; sign-in from
  wl.works designed, waiting on the rig's https page (XC-151, XC-152).
- **Welfare** (`bounds.py`, `welfare.py`, `marks.py`, `stranded.py` and the functions architecture.md lists, held to
  `tests/welfare_manifest.json` by `tests/test_welfare_manifest.py`, on `main` since `0b175ea`): one limit, out of
  the cage to back in, eight hours (the institution's); the day's fluid is a floor and no delivery is refused on
  volume; each delivery's size is a ceiling; a task names how reward is configured, never how much.
- **The record**: the session folder `xcon/` that wl-preproc reads (`record.py`).

## What is next (the PI, 2026-11-07)
1. **Merge the pop-out search build**, behind the PI's yes by name, after its CI is read shard by shard. wl-xtasks'
   main holds the task (`c1a61e9`, merged on his word 2026-11-08), so CI requires it (`WLX_REQUIRE_XTASKS=1` in every
   job); its branch `popout-search-2026-11-08b` (a comment) merges on his word the same way. The
   wl-preproc ask in its amendments section is still to be sent (XC-491): the color-set shapes, `luminance`, the
   `realized` list and line field with `xyz`, `remakes`, and the start row's `left`. **Decided 2026-11-08**: a suggestion stays up until its bar
   is missed by more than 3 answers (`suggestion_margin`), and a stage the animal returns to picks up where it left.
   **To tell him at the merge ask, a line each**: the builder's ranges for every new setting (TSK-75); a live change of
   `disc_size`, `fix_size` or `color_luminance` (expected) keeps trials out of moving up until handed back; a re-made
   widening stands on the old stage's bar until answered, beside a move back too; bars set live so they bounce are not
   warned; the fixation window reaching the discs' windows is a warning, the ranges as they are (the re-review's I-2).
2. **Demo mode**, with its own plan: its design (`docs/superpowers/specs/2026-10-06-demo-mode-design.md`) and its two
   `Service._open` welfare changes are approved by the PI (2026-11-07; XC-013).
3. **Then the display (build E)**, designed with the PI; "done" includes a real screen.
4. **Side work on the January path**: the sync-box client (XC-460), the operator's guide (XC-014), the default limits
   file (XC-459, a welfare design with the PI).
5. **Paused until the pop-out search has run on a rig**: engine builds C4 to C9 and the rig-edit build.

**How the work is run** (the PI, 2026-11-07): a plan is a design and a list of tests, built once; one review of the
whole build, and the PI's welfare review of any welfare-listed change; side work only on the January path; a rare edge
case is settled from his stated principles and told to him in one line; every merge waits for his yes by name and a
clean CI.

## Working here
- **Suite**: `WLX_REQUIRE_PREPROC=1 WLX_REQUIRE_BROWSER=1 WLX_REQUIRE_XTASKS=1 PYTHONDONTWRITEBYTECODE=1 python -m pytest -q -p
  no:cacheprovider -n auto` (a `wl-preproc` checkout or link at the root, and a `wl-xtasks` one beside it, git-ignored
  at `/wl-xtasks`, holding `tasks/popout_search.py`; wl-sync installed at the commit `wl-preproc/pyproject.toml` pins).
  **5603 passed on `main`** (`56ccca2`); the pop-out build's branch has more (**5830 passed**), none skipped.
- **CI**: each push sweeps the changed modules with mutants (`tools/mutation_gate.py`); the nightly sweeps all, in 36
  shards (the PI, 2026-11-09; a big branch starts the same sweep by hand before its merge). Read every shard's log to its closing line; the run's summary can be wrong.
- **The neighbors** are read weekly, by their handover files (the PI, 2026-11-07): wl-preproc, wl-sync, wl-works,
  wl-xtasks. Last read: 2026-11-07, by the audit (wl-sync's answer of 2026-10-18 was found unread
  that day: its session endpoint is XC-460). Open asks of each: `docs/pending-*-amendments.md`.
- **The welfare diff**: `tools/welfare_diff.py BASE HEAD` lists the welfare-listed code between two revisions item by item
  (`SAME`/`DIFFERS`); run it at every merge (architecture.md, "Welfare-critical modules").
- **The session fuzzer**: `tools/fuzz_sessions.py`, random tasks through `taskd.Session.run`, read back by wl-preproc and
  checked against the C2b and C3 invariants; `tests/test_fuzz_sessions.py` runs a small budget on every push.
