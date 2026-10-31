# The reply grace -- how often a console loses a session's last acknowledgment, on a development machine

> **This is not a rig measurement, and not a latency.** It counts lost replies in two-CPU
> Linux containers on one loaded development host. It says whether `link.REPLY_GRACE_S`
> removes the loss there, at the loads it was run at, and nothing about how long a rig's
> console takes to read a reply or about a load it was not run at.

**Date:** 2026-10-31 (the defect was found and first measured on 2026-10-30, XC-429).
**Script:** `tools/measure_reply_grace.py`, run as
`python tools/measure_reply_grace.py batch --label LABEL --image xcon-flake:latest --containers 6 --repeats 50 --out .superpowers/reply-grace`,
with `--grace 0` for the batches without a grace, `--burners 14` for the third pair and
`--grace 0 --immediate off` for the last, one batch at a time in the order of the table, then
`python tools/measure_reply_grace.py summarize .superpowers/reply-grace`.
**Code:** this branch's tree as committed with this document: `REPLY_GRACE_S = 0.1`, the
clamped wait of XC-429's review (M3), and `tests/test_serve.py` as it stood at `957ec98`.
**Host:** macOS-27.0.1-arm64, 14 CPUs, Docker 29.4.0 (OrbStack, 14 CPUs to its VM), with
other agents' test suites running on it throughout, so its load was not controlled.
**Containers:** six at once per batch, each `--cpus 2 --network none`, this checkout mounted
read-only, running Linux-7.0.14-orbstack aarch64 (glibc 2.41) from the local image
`xcon-flake:latest` (built 2026-10-01): Python 3.12.14, **pyzmq 27.2.0 (libzmq 4.3.5)**,
pytest 9.1.1, msgpack 1.2.3, pydantic 2.13.5, numpy 2.5.3, pyyaml 6.0.3. CI's mutation jobs
run Python 3.13 on `ubuntu-latest` with the same pyzmq.

## What was measured

The two `wlx serve` end-to-end tests that failed on CI with `assert 504 == 200` (runs
`41025634023` and `41045421173`), `test_e2e_a_write_from_elsewhere_is_refused_and_the_session_never_sees_it`
and `test_e2e_pause_holds_the_trial_count_keeps_the_clock_and_resume_continues`, each run 50
times over, serially, in one pytest process per container, as CI's mutation gate runs the suite.
A probe logs each command `ZmqCommands.deliver` sends and which wait ran out if it was not
delivered, each `ZmqLink.drain` that returned commands, and each `ZmqLink.close`. The host's
one-minute load average was sampled every 5 s until the last container of a batch exited.

| batch | began | grace (s) | IMMEDIATE | burners | load (1 min) | runs | stop's reply lost | close median / max (ms) |
|---|---|---|---|---|---|---|---|---|
| no-grace-1 | 00:50 | 0 | on | 0 | 6.6 to 44.1 | 600 | 11 | 0.6 / 11.5 |
| grace-1 | 00:53 | 0.1 | on | 0 | 6.5 to 13.6 | 600 | 0 | 101.2 / 176.0 |
| no-grace-2 | 00:55 | 0 | on | 0 | 4.7 to 44.8 | 600 | 11 | 0.6 / 11.9 |
| grace-2 | 00:58 | 0.1 | on | 0 | 10.9 to 38.6 | 600 | 0 | 101.6 / 112.3 |
| no-grace-3 | 01:00 | 0 | on | 14 | 11.8 to 103.8 | 600 | 10 | 0.6 / 53.7 |
| grace-3 | 01:03 | 0.1 | on | 14 | 70.1 to 100.1 | 600 | 0 | 101.8 / 123.7 |
| immediate-off-1 | 01:06 | 0 | off | 0 | 18.5 to 97.1 | 600 | 0 | 0.5 / 5.7 |

**Without a grace, 32 of 1,800 runs lost the stop's reply; with `REPLY_GRACE_S = 0.1`, 0 of 1,800.**
With `IMMEDIATE` off on the console's socket and no grace, 0 of 600 did. Every failed run in
these batches was a lost reply: no test failed any other way. Loads without a grace ran from
4.7 to 103.8, and with it from 6.5 to 100.1; the first grace batch ran at the lowest
load of any, and the third's never fell below 70.

## Each lost reply

Every one was a stop, and in every one the console's 15 s reply wait (`REPLY_TIMEOUT_S`) ran
out after the rig had drained the stop, which replies as it reads, and had begun to close its
link 0.5 to 1.4 ms after that drain returned. Times are from when the console sent the stop.
17 were in the write-from-elsewhere test and 15 in the pause test.

| batch | test | command | rig drained it (ms) | rig's close began (ms) | reply wait ran out (s) |
|---|---|---|---|---|---|
| no-grace-1 | write from elsewhere | Stop | 13.1 | 13.6 | 15.022 |
| no-grace-1 | pause | Stop | 1.6 | 2.9 | 15.010 |
| no-grace-1 | pause | Stop | 3.8 | 4.3 | 15.017 |
| no-grace-1 | write from elsewhere | Stop | 2.7 | 3.2 | 15.017 |
| no-grace-1 | write from elsewhere | Stop | 5.9 | 6.5 | 15.002 |
| no-grace-1 | pause | Stop | 6.1 | 7.2 | 15.025 |
| no-grace-1 | pause | Stop | 1.4 | 1.9 | 15.024 |
| no-grace-1 | pause | Stop | 1.9 | 3.0 | 15.013 |
| no-grace-1 | pause | Stop | 8.1 | 9.3 | 15.017 |
| no-grace-1 | pause | Stop | 6.7 | 7.2 | 15.017 |
| no-grace-1 | pause | Stop | 9.5 | 10.7 | 15.018 |
| no-grace-2 | write from elsewhere | Stop | 7.4 | 8.6 | 15.019 |
| no-grace-2 | write from elsewhere | Stop | 2.9 | 3.7 | 15.002 |
| no-grace-2 | write from elsewhere | Stop | 4.1 | 4.9 | 15.024 |
| no-grace-2 | write from elsewhere | Stop | 6.3 | 7.1 | 15.002 |
| no-grace-2 | write from elsewhere | Stop | 4.9 | 6.1 | 15.015 |
| no-grace-2 | write from elsewhere | Stop | 2.0 | 2.7 | 15.024 |
| no-grace-2 | write from elsewhere | Stop | 5.8 | 6.5 | 15.005 |
| no-grace-2 | write from elsewhere | Stop | 37.8 | 38.6 | 15.054 |
| no-grace-2 | write from elsewhere | Stop | 6.5 | 7.2 | 15.019 |
| no-grace-2 | pause | Stop | 1.7 | 2.6 | 15.017 |
| no-grace-2 | pause | Stop | 11.7 | 13.1 | 15.015 |
| no-grace-3 | write from elsewhere | Stop | 5.8 | 6.5 | 15.012 |
| no-grace-3 | write from elsewhere | Stop | 2.4 | 3.7 | 15.026 |
| no-grace-3 | pause | Stop | 1.6 | 2.5 | 15.022 |
| no-grace-3 | pause | Stop | 4.4 | 5.5 | 15.016 |
| no-grace-3 | pause | Stop | 5.9 | 6.8 | 15.021 |
| no-grace-3 | write from elsewhere | Stop | 9.1 | 10.5 | 15.002 |
| no-grace-3 | pause | Stop | 1.6 | 2.6 | 15.005 |
| no-grace-3 | pause | Stop | 7.1 | 8.1 | 15.019 |
| no-grace-3 | write from elsewhere | Stop | 65.4 | 66.7 | 15.081 |
| no-grace-3 | write from elsewhere | Stop | 6.6 | 7.6 | 15.023 |

## What it shows, and what it does not

- **The reply is lost on the console's side, not the rig's.** With the console's REQ socket
  reconnected without `IMMEDIATE`, nothing was lost. On 2026-10-30, closing the rig's REP
  socket with a 1 s linger did not help (12 of 600, from this script's scratch predecessor),
  and that close never waited, so nothing was left queued at the rig. Why `IMMEDIATE` drops a
  reply not yet read when the connection goes is not read in libzmq's source here; it is
  measured, not explained.
- **The grace removed the loss at every load it was run at here**, and its cost is the close:
  about 100 ms, only when a command was answered less than `REPLY_GRACE_S` before it.
- **It narrows the race and does not close it.** A console kept from reading for longer than
  the grace still loses the reply. Closing it on the console's side is XC-429.
- **It is not a rig.** The loss depends on how soon the console's thread reads after the rig
  closes, which depends on the console's machine and load. Nothing here measures a rig's.

## Raw logs

One JSON-lines log per container, each batch's host record, load samples and `summary.json`,
5.3 MB in all: not committed. They were kept in the git-ignored `.superpowers/reply-grace/` of
the `xc429-e2e-room` worktree on the development machine, which is deleted after merge, and
the script regenerates them. The tables above are `summarize`'s output, rearranged.

**Before this script existed** (2026-10-30), the same measurement made by scratch probes, not
committed, agreed: 56 of 3,120 runs lost the stop's reply without a grace, 0 of 1,800 with it,
and 0 of 600 each with `IMMEDIATE` off or with the link held open 100 ms before closing. They
are recorded here for the record only; the numbers to quote are the ones above.
