# Where this build is

**Last updated 2026-11-07**, at the commit this file was committed in (`git log -1 -- docs/CHECKPOINT.md`). **This page
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
  engine fixtures; **no real task exists yet** (they come from wl-xtasks, written with the PI).
- **Running**: the trial loop (`run.py`), the session daemon and CLI (`taskd.py`, `cli.py`: `wlx run`, `wlx taskd`),
  the simulated animal (`simulate.py`; since XC-456 a gaze task's trials are played by the simulated eye, `simeye.py`,
  through the rig's gaze world, `gaze.Tracked`).
- **The console**: a browser page on the LAN (`serve.py`, `web.py`, `link.py`); writes from the box only; sign-in from
  wl.works designed, waiting on the rig's https page (XC-151, XC-152).
- **Welfare** (`bounds.py`, `welfare.py`, `marks.py`, `stranded.py` and the functions architecture.md lists; to be
  enforced by a tracked test, in review): one limit, out of the cage to back in, eight hours (the institution's); the
  day's fluid is a floor and no delivery is refused on volume; each delivery's size is a ceiling; a task names how
  reward is configured, never how much.
- **The record**: the session folder `xcon/` that wl-preproc reads (`record.py`).

## What is next (the PI, 2026-11-07)
1. Finish the work in flight, each reviewed: `small-guards-2026-11-07` and `check-hardening-2026-11-07` (small
   guards, and the load check never raising; to rebase onto this `main`), and `tools-as-tests-2026-11-07` (the
   welfare check and the session fuzzer as tracked tests, `cli._load_bounds` added to the welfare list on the PI's
   word of 2026-11-07). Each merges on his yes.
2. **One real training task**, written with the PI in wl-xtasks and run end to end; with it the simulated animal
   through the rig's own eye logic, and demo mode (XC-013). The operator's guide (XC-014) and the session-number
   client (XC-460) are side work on the same path.
3. **Paused until that task runs**: engine builds C4 to C9 and the rig-edit build.
4. Then the display (build E), in the PI's order.

**How the work is run** (the PI, 2026-11-07): a plan is a design and a list of tests, built once; one review of the
whole build, and the PI's welfare review of any welfare-listed change; side work only on the January path; a rare edge
case is settled from his stated principles and told to him in one line; every merge waits for his yes by name and a
clean CI.

## Working here
- **Suite**: `WLX_REQUIRE_PREPROC=1 WLX_REQUIRE_BROWSER=1 PYTHONDONTWRITEBYTECODE=1 python -m pytest -q -p
  no:cacheprovider -n auto` (a `wl-preproc` checkout or link at the root; wl-sync installed at the commit
  `wl-preproc/pyproject.toml` pins). **5420 passed on `main`**, none skipped.
- **CI**: each push sweeps the changed modules with mutants (`tools/mutation_gate.py`); the nightly sweeps all, in 24
  shards. Read every shard's log to its closing line; the run's summary can be wrong.
- **The neighbours** are read weekly, by their handover files (the PI, 2026-11-07): wl-preproc, wl-sync, wl-works,
  wl-xtasks. Last read: 2026-11-07, by the audit (wl-sync's answer of 2026-10-18 was found unread
  that day: its session endpoint is XC-460). Open asks of each: `docs/pending-*-amendments.md`.
- **The welfare diff**: `tools/welfare_diff.py BASE HEAD` lists the welfare-listed code between two revisions item by item
  (`SAME`/`DIFFERS`); run it at every merge (architecture.md, "Welfare-critical modules").
- **The session fuzzer**: `tools/fuzz_sessions.py`, random tasks through `taskd.Session.run`, read back by wl-preproc and
  checked against the C2b and C3 invariants; `tests/test_fuzz_sessions.py` runs a small budget on every push.
