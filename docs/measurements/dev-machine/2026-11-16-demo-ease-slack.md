# A demo's ease slack -- what it costs and buys, on an injected clock

> **This is not a rig measurement, nor a browser's or a network's.** It runs the rig's own code
> (`pointer.Source`, `pointer.worlds`, `run.run_trial`, the saccade detector and the pop-out's
> rules) in process on a clock the script moves, with report timings the script assumes. Its
> numbers say what a demo's easing does with reports that arrive so, on any machine, and nothing
> about a rig, a browser or how late a real page's reports are. It is the source of every number
> said beside `pointer.EASE_SLACK_S` and in the demo design's §14 item 9 note (the build's
> re-review, N4).

**Date:** 2026-11-16, 17:25:47 to 17:25:53 local time (UTC−5), from `results.json`.

**Script:** `tools/measure_demo_ease_slack.py`, run as
`python tools/measure_demo_ease_slack.py --out docs/measurements/dev-machine/2026-11-16-demo-ease-slack`
from this checkout at `541f16d`, with the re-review's second fix round being written beside it.
- The script as it ran is copied beside its output; its sha256, `669586c7…`, is in `results.json`.
- `results.json` holds every trial; `table.md` and `stdout.txt` are what it printed, the last line of
  `stdout.txt`, `exit 0`, the shell's.

**Code:** `wl_xcon/pointer.py` as at `541f16d` (`EASE_SLACK_S` 0.025 s, `LIVE_S` 0.5 s, a frame
1/240 s). The files `results.json`'s `git_status` lists as changed were none the run read: the page,
the service, the link and tests. **Task:** wl-xtasks `tasks/popout_search.py` at `64929fe`.

**Host:** macOS-27.0.1-arm64, Python 3.13.9. The clock is injected, so the host's speed and load
change no number here.

## What was run

- **Glides:** the pop-out answered by a minimum-jerk glide from the fixation point to the odd disc
  8° away, 400 ms and 600 ms long, 100 seeds each, as `tests/test_pointer.py`'s glide test plays
  it. The page reports every animation frame (60 Hz) while the pointer moves and every 100 ms
  while still; each report arrives either at once (`regular`) or half a round trip late, the round
  trip drawn for each from 2 to 12 ms (`jittered`). Each with the slack at 0 and at 25 ms.
- **Merges:** a move 5° in 100 ms, a stop of S ms in the page's reports, a move 5° more, jittered,
  10 seeds a stop; the saccades over 0.2° the detector confirmed.

## Results

| Glide | Reports | Slack | Ended (of 100) | Left the fixation window, mean | Flight, mean |
|---|---|---|---|---|---|
| 400 ms | regular | 0 ms | correct 100 | 162.5 ms | 210.3 ms |
| 400 ms | regular | 25 ms | correct 100 | 183.3 ms | 209.9 ms |
| 400 ms | jittered | 0 ms | correct 59, second look 41 | 167.5 ms | 150.8 ms |
| 400 ms | jittered | 25 ms | correct 100 | 187.5 ms | 209.3 ms |
| 600 ms | regular | 0 ms | correct 98, landing bound 2 | 232.5 ms | 278.4 ms |
| 600 ms | regular | 25 ms | correct 95, landing bound 5 | 254.2 ms | 282.9 ms |
| 600 ms | jittered | 0 ms | correct 7, second look 93 | 237.9 ms | 107.8 ms |
| 600 ms | jittered | 25 ms | correct 93, landing bound 6, second look 1 | 259.4 ms | 266.3 ms |

| Stop in the page's reports | One saccade (of 10), no slack | One saccade (of 10), 25 ms slack |
|---|---|---|
| 0 ms | 1 | 5 |
| 17 ms | 1 | 5 |
| 33 ms | 0 | 1 |
| 50 ms | 0 | 1 |
| 67 ms | 0 | 0 |
| 83 ms | 1 | 0 |
| 100, 150, 200 ms | 0 | 0 |

## What it says

- **It buys:** a glide whose reports come a few milliseconds early or late stays one saccade. Without
  the slack, 41 of 100 jittered 400 ms glides and 93 of 100 600 ms ones end as a second look; with
  it, none at 400 ms and 1 of 100 at 600 ms.
- **The eye trails the hand by about 21 ms more**: the eye leaves the fixation window 20.0 to
  21.7 ms later, mean over 100 seeds, at both lengths and both timings. A hand that leaves less than about that
  before the go reads as leaving after it.
- **A stop of 50 ms or less between two moves can merge them into one saccade**: 5 of 10 at 0 to
  17 ms, 1 of 10 at 33 to 50 ms, against 1, 1, 0 and 0 without it; none from 67 ms.
- **A 600 ms glide meets the pop-out's own 0.3 s landing bound a little more often**: 2 in 100
  without the slack, 5 with it, 6 jittered; the mean flight 4.5 ms longer with regular reports.
  The bound is the task's, which a person's try-out judges.
- **1 in 100 jittered 600 ms glides still splits** into two looks.

These were first found by the re-review's own probe (the same model and seeds); this script is
their record.
