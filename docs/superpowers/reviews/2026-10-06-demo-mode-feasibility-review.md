# Demo-mode spec: feasibility review against the code

> **What this is.** A design review of `../specs/2026-10-06-demo-mode-design.md`, written on 2026-10-06 by a reviewer subagent the build session dispatched, kept as written. Its main claims were re-checked by that session (the spec's §14 lists what they change, to fold in when the build resumes). The scratch scripts it mentions were not kept.

Spec: `docs/superpowers/specs/2026-10-06-demo-mode-design.md`, read against the `demo-mode`
worktree at `05f6a3a` (2026-10-06). Every finding below was checked in the source. Three were
also run: `check()` on the four tasks, `wlx check --rig tasks/rig.py`, and
`saccade.Detector` on synthetic pointer traces. No test suite was run and no repository file was
edited. Anything not checked is marked UNVERIFIED.

The findings are ordered with the most consequential first.

---

## 1. `visual_search` cannot load, so `wlx demo visual_search` (the PI's try-it) stops at the check

**Spec:** §10 ("`wlx demo visual_search` in Safari"), §5 step 2, §6 (visual_search's rows), §4.4
("at its size and color").

**Evidence:**
- `wl_xcon/check.py:791-815`. `_color_faults` raises a blocking `uncalibrated-color` (a
  `Finding` blocks by default, `findings.py`) for every appearance with a non-`P` color when
  no `calibration` is passed.
- `check.py:765-789`. `_appearances` includes `Param.choices`.
- `tasks/visual_search.py:15-17, 50-51, 103-116`. Its choices are `DKL` colors, and its own
  docstring says it "will not load without a measured display calibration".
- Nothing passes a calibration: not `taskd.py:1982` (`Session.run`), not `preflight.py:82`
  (the pre-flight's task item), not `wlx check`.
- Ran `check()` on the four tasks: visual_search returns 5 × `uncalibrated-color`. The other
  three return none.

**Why it fails:**
- `wlx demo visual_search` is refused at §5 step 2.
- A visual_search run from the page fails its pre-flight.
- §6's ten starting values for visual_search start nothing.
- §4.4's "at its color" has no conversion to draw with: a `DKL` color is a contrast from a
  measured background, and no measurement exists (`photometry.py` docstring).

**Smallest correction:**
- Name `fixation_detection` (or `adaptive_detection`) for §10's try-it.
- State that visual_search stays refused until a display calibration exists, and keep its §6
  values only as declarations.
- §4.4: draw a declared color as a label, not as a hue.

---

## 2. The simulated card and pump and the stand-in field are chosen in `_build`, which `_resume` shares, so a resumed simulation comes back as a live session

**Spec:** §3.2, §3.6, §8 items 1-3 ("`Service._open` … changes; no other welfare-critical
function changes").

**Evidence:**
- `wl_xcon/service.py:599-600`: the card and pump are `self._card()` and `self._pump()`.
- `service.py:569`: the field is `self.rig.direct()`.
- Both lines are in `Service._build` (533-605), not in `_open` (625-704).
- `_build` is also what `_resume` calls (`service.py:754-758`).
- `resume.read` rebuilds from `config.json`'s `session_id`, `subject`, `deployment`,
  `setup.view` and so on (`resume.py:207-213`). It reads no `simulation` key.
- `_build` is on neither welfare list (`docs/design/architecture.md:82-84, 139-143`).

**Why it fails:**
- Item 2 ("no simulation can ever open a real valve") would be implemented in an unreviewed
  function.
- More seriously, a simulation session left stranded would be rebuilt by `_resume` as an
  ordinary REFERENCE session. A taskd crash or kill during a rig-page simulation is enough; the
  §6.1 stranded rule then blocks every real animal until REFERENCE is ended or resumed.
- That ordinary session gets the service's card and pump, the behaviour-agent world (no
  `world` is passed, so `taskd.py:2025` falls back to `_agent`), and the rig's real field.
- Today the real field makes `rig.direct()` refuse the resume. Once housings are measured and a
  real pump is wired in, which is exactly the day §3.2 is written for, the resumed
  "simulation" can open the real valve.

**Smallest correction:**
- Say where each rule lives: apparatus and field in `_build`/`_session_for`, driven by a flag
  that `_open` passes. Put that on the §8 summary as a change to `_build`. The PI decides the
  list.
- Add a §3.1 rule for resume: refuse to resume a session whose `config.json` carries
  `simulation`, so it can only be ended. Alternatively, `resume.read` returns the flag and
  `_build` honors it.

---

## 3. A move that reaches the rig as one pointer report is never a saccade

**Spec:** §3.3 ("a move that stops produces one", "a saccade is the pointer moving and then
stopping"), §9 browser test ("move to it, *correct*").

**Evidence:**
- `wl_xcon/saccade.py:47`: `min_duration_samples` is 6.
- `saccade.py:336-342`: the five-point velocity, ×40 at 240 Hz.
- `saccade.py:386-399`: confirmation needs 6 consecutive samples outside the threshold.
- One position step `d` between frames `k` and `k+1` produces exactly four nonzero velocities:
  40d, 80d, 80d, 40d at `k-1..k+2`.
- Ran `Detector` with the 0.02° tremor at 240 Hz:

  | Trace | Result |
  |---|---|
  | Still, 20,000 frames | ready, 0 saccades (engineering call 2 holds) |
  | One 10° jump | **0 saccades** |
  | Two reports 4 frames apart | 1 saccade |
  | Twelve reports over 200 ms | 1 saccade |

**Why it fails:**
- These all deliver a single step, so `SaccadeTo` never fires and the trial ends
  `NO_RESPONSE`:
  - a flick inside one animation frame;
  - two reports drained in the same 240 Hz frame (`DRAIN` keeps one);
  - Playwright's `mouse.move(x, y)` without `steps`. Playwright's documented default is
    `steps=1`, UNVERIFIED here because Playwright is not installed in this venv.
- §9's browser test as described would fail. The in-process tests would pass.

**Smallest correction:**
- State the condition: a saccade needs the pointer's position to change on at least two
  frames.
- Specify the browser test as timed moves across at least two animation frames.
- Optionally, have `pointer.Source` interpolate between consecutive reports. The detector stays
  unchanged.

---

## 4. REFERENCE's 600 s out-of-cage ceiling ends every simulation 10 minutes after *←cage at*, with the warning shown from the first frame

**Spec:** §2 ("every welfare limit still runs, against the test monkey's own"), §3.2, §5 steps
4-5 ("`--trials` … default 1000", "starting another run"), §10.

**Evidence:**
- `tasks/reference_bounds.py:58`: `"out_of_cage": Ceiling(value=600.0, maximum=600.0)`. It
  cannot be raised.
- `welfare.py:1149-1159`: `must_stop` fires once out-of-cage exceeds 600 s.
- `welfare.py:101`: `WARN_WITHIN_DEFAULT = 1800`.
- `welfare.py:1196-1203`: with 600 < 1800, the "start bringing the animal back" warning is
  shown for the whole session.
- `taskd.py:1365-1385` (`_ends`) stops a run at the limit, and `preflight.py:250-270`
  (`out_of_cage`) then fails any new run.

**Why it misleads:**
- §5 step 5's "starting another run" and the 1000-trial default cannot happen past about 10
  minutes. Paced trials of a few seconds give a few hundred trials at most.
- A student practicing, and the PI trying it, is cut off by a "limit" stop beside a permanent
  return-the-animal warning.

**Smallest correction:**
- State the ten-minute bound and the standing warning in §3.2 and §5.
- Whether a simulation's REFERENCE should have a different out-of-cage figure is a PI decision,
  to be asked rather than filed.

---

## 5. A third message kind on the PUB socket breaks `encode`, `_Routed.publish`, `decode`, `wlx console` and `wlx serve`'s hub. The spec names none of them

**Spec:** §3.9 (`Screen` "beside `Telemetry` and `Idle`"), §4.4 ("pushes it as a `screen`
event").

**Evidence:**

| Where | What it assumes |
|---|---|
| `link.py:868-909` `encode` | Only `Idle` or `Telemetry`. Anything else goes through `_telemetry_out` and raises `AttributeError`. |
| `service.py:246-254` `_Routed.publish` | Every published object has `.phase`. |
| `link.py:1024-1076` `decode` | Any non-idle payload is a `Telemetry`, so a `Screen` raises `FrameError`. |
| `cli.py:1964-1971` (`wlx console`) | Returns 1 on any `FrameError`. |
| `serve.py:1704-1713` | `hub.reject` on each one: the page shows a refusal. |
| `/health` | Reports a rejecting console as degraded until the next good frame (`_health`, Ruling 11). |
| `Hub` (`serve.py:181-213`) | Keeps one latest frame. |
| `Hub.take` (`serve.py:296-311`) | Keeps only the newest queued item. |
| `event()` (`serve.py:441-443`) | Names every SSE event `frame`. |
| `ZmqConsole` (`link.py:2641`) | Subscribes to everything. |

**Why it fails:**
- As written, the first `Screen` ends `wlx console`. §3.7 says `wlx console` will show
  `simulation`.
- On `wlx serve`, every `Screen` flips the page and `/health` into "frame not shown".

**Smallest correction:** in §3.9, specify:
- how a `Screen` is told apart: its own topic prefix that `ZmqConsole` filters out, or a `kind`
  field that `decode` dispatches on, under the same schema check;
- that `wlx console` skips it;
- that `_Routed.publish` passes it through;
- that `Hub` keeps the latest `Screen` beside the latest frame;
- that SSE gets a second event name.

---

## 6. There is no recentering for C to "keep", and R was deliberately given no key

**Spec:** §3.3 ("Recentering (C) works as it will on a rig: it adds an offset and makes a new
version"), §4.6 ("P, R, C and M keep their meaning").

**Evidence:**
- `web.py:2629-2636`: the page handles only `p` and `m`.
- `docs/superpowers/specs/2026-09-26-P4d2b-browser-console-design.md:432-434`: Give reward is
  "a button … live only while the session is paused …; **no key**" (PI, 2026-09-28).
- `link.py` has no recenter command.
- The b2a plan pins a `recenter` command as refused: "not one this session acts on"
  (`docs/superpowers/plans/2026-09-27-p4d2b-b2a-controls.md:911-925`; `taskd.py:1687`).
- `calibration.py:531-533`: a `MappingLog`'s version 0 is always "no map yet".
- `calibration.py:592-597`: `recenter` raises on it.
- `gaze.py:81, 101`: `Tracked` reads its mapping once per world, so once per trial.

**Why it fails:**
- C and R have no existing meaning to keep.
- Recentering would be a new command, a new page key, and a session-held `MappingLog` whose
  version 0 is not the identity.
- Adding R would also reverse the PI's keyless-reward ruling.

**Smallest correction:**
- §4.6: "P and M keep their meaning."
- §3.3: drop the recentering sentence, or list it as new scope. If it stays, the identity is
  installed as version 1, applied from the next trial.

---

## 7. Gaze reports queue whenever no trial is polling, and the next trial's first frames replay them

**Spec:** §3.8 ("at most `DRAIN = 64` messages a frame, keeping the latest"; drained "at each
simulation session's open"), §3.4 (press counts), §4.5 (the only 409 is "not a simulation
session").

**Evidence:**
- Nothing reads a gaze socket outside a trial:
  - `ZmqLink.idle` polls only REP and mark (`link.py:2484-2496`);
  - `Service.step` (`service.py:364-382`);
  - the paused loop `_hold` (`taskd.py:1433-1446`);
  - between runs, idle housekeeping.
- The page keeps reporting at ≥10 Hz while over the screen (§3.3).
- `/gaze` is accepted whenever the frame says `simulation`, which includes paused and between
  runs.

**Why it fails:**
- After a pause or between runs, the backlog can be hundreds of messages, and a PULL socket
  gives them oldest first.
- Reading 64 a frame and keeping the last read keeps the 64th-oldest, not the latest. The
  trial's first frames see positions from the start of the pause. Under `LIVE_S`, measured
  from the read, they count as live.
- Presses made during the ITI, a pause or between runs raise the running count, so they fire
  `Pressed` on frame 1 of the next trial.
- Draining only at session open does not cover runs, pauses or ITIs.

**Smallest correction:**
- At each trial's first frame, discard everything waiting except the newest, and rebase the
  press counts there.
- Or keep only the newest message on the socket. ZeroMQ's `CONFLATE` would do this, but it is
  UNVERIFIED for this pyzmq/libzmq and needs checking before relying on it.

---

## 8. `/gaze` reports can arrive out of order, and the message carries nothing to order them by

**Spec:** §3.8 (the message's fields: x, y, over, B, button, keys held, press counts), §4.5
("pushes … as a mark").

**Evidence:**
- `serve.py` sets no `protocol_version`, and `BaseHTTPRequestHandler.protocol_version` is
  `HTTP/1.0` (checked in the repo venv, Python 3.12.13). Each POST is therefore its own
  connection and `ThreadingHTTPServer` thread.
- The order reports reach the gaze thread's queue (`Outbox.submit`, `serve.py:754-775`) is the
  order those threads run.
- On the https listener, each report also costs a new TLS handshake (`_PageServer`,
  `serve.py:879-899`) and a token check (`_signed_in`, `serve.py:1125-1137`).

**Why it fails:**
- "Keeping the latest" keeps whatever arrived last.
- A report overtaken by an older one moves gaze backward, a velocity spike the detector can
  read as a saccade.
- Press counts can step down.

**Smallest correction:**
- The page keeps one report in flight, sending the newest state when the previous one answers.
- Each report carries a per-page sequence number, and serve or the source drops anything older
  than the newest seen.

---

## 9. `may_write` is not the write gate, and is never true on the https page

**Spec:** §4.5 ("Only a page that may write (`may_write`: at the rig PC, or signed in with
wl.works)").

**Evidence:**
- `serve.py:1035-1044`: `may_write` returns `False` whenever `_remote` is set ("Never on the
  https page"). On the box it is two of the four checks.
- Writes are gated in `_command` (`serve.py:1179-1210`):
  - on the box, `_from_the_box` (all four checks, `serve.py:1046-1060`);
  - on https, `_from_the_page` and then the bearer token (`serve.py:1118-1137`).

**Why it misleads:**
- A `/gaze` gated on `may_write` refuses every signed-in https page.
- On the box, it skips the Origin and Content-Type checks.

**Smallest correction:** "gated as `POST /commands` is gated (`_command`'s checks, factored out
for `/gaze`)", with no mention of `may_write`.

---

## 10. `wlx demo`'s check refuses every shipped task, and the spec omits `wlx serve`'s required token file

**Spec:** §5 steps 2-3 ("the load checks `wlx check` runs, against the chosen setup"; "exactly
as a rig runs them, on free loopback ports").

**Evidence:**
- Ran `wlx check tasks/fixation_detection.py --rig tasks/rig.py`. It printed "refused: direct
  view's field excludes the light sensors' housings…" (`geometry.py:125-130`). `wlx check` has
  no way to use stand-ins.
- `wlx serve` requires `--health-token-file` (`cli.py:1415-1422`). It is refused inside any
  git checkout, worktrees included (`serve.py:1781-1822`).
- `wlx taskd` prints its bound endpoints without `flush` (`service.py:1192-1197`). A parent
  that asks for port 0 and reads the line from a pipe waits on a block-buffered stdout.

**Why it fails:** as written, the demo refuses every shipped direct-view task before starting
anything.

**Smallest correction:** §5 step 2 checks against the field the service would build, with
stand-ins when the rig's housings are empty. Step 3 also lists:
- a token file in the throwaway root, which must be outside any checkout;
- how ports are learned: chosen beforehand, or read from an unbuffered child.

---

## 11. Paced trials can outlast `wlx console`'s 5 s receive timeout, which it treats as fatal

**Spec:** §3.5 (real time), §3.7 ("every page and `wlx console` can say so"), §3.3 (advising
longer response windows).

**Evidence:**
- Telemetry is published only at trial boundaries and while paused (`taskd.py:2119-2140`,
  `1433-1446`; the `Session.link` docstring).
- `wlx console` builds `ZmqConsole` with its default 5 s timeout (`cli.py:1915`;
  `link.py:2620`) and returns 1 on `TimeoutError` (`cli.py:1961-1963`).
- `wlx serve` is unaffected: 0.5 s timeout, then `continue`.

**Why it fails:**
- Once trials run in real time, a trial plus its 0.5 s ITI longer than 5 s ends `wlx console`.
  Examples: a `fix_timeout` of 5-10 s; a response window lengthened for a mouse, as §3.3
  advises; a hold that runs to its timeout.

**Smallest correction:**
- State that `wlx console` on a simulation is limited by its 5 s timeout, or have it keep
  waiting.
- Alternatively, have the simulation's world publish a telemetry heartbeat between
  boundaries.

---

## 12. The idle frame cannot tell the page whether taskd has a gaze endpoint

**Spec:** §4.1 ("When … the rig service has no gaze endpoint, the choice is greyed"), §3.7
(schema 15 adds only `simulation`).

**Evidence:**
- `link.py:343-405`: `Idle` carries `animals` and `offered_tasks`, and nothing about the link's
  endpoints.
- `wlx serve` knows only its own `--link`, and its fourth endpoint can be given while taskd's
  is not.

**Why it misleads:** §4.1's greying has no source. The page would offer the choice, and the
open would then be refused by §3.1.

**Smallest correction:** schema 15 also adds a `gaze` boolean (taskd has a gaze endpoint) to
`Idle` and `Telemetry`.

---

## 13. `gaze.Tracked` "with three parts supplied" cannot report a blink or any non-gaze guard, and its tracker must not outlive a trial

**Spec:** §3.3 ("The world … is `gaze.Tracked`, the rig's own, with three parts supplied"; "B
held: `signal` answers blink"), §3.4.

**Evidence:**
- `gaze.py:172-179`: `Tracked.signal` "**Never `blink`**".
- `gaze.py:156-170`: `happened` is `False` for everything but `SaccadeOnset` and `SaccadeTo`.
- `gaze.py:103-104`: `when(frame)` restarts at `started_at` each trial.
- `eye.py:149-158`: `Tracker.state` treats any `at - latest.at < staleness`, negative included,
  as `ok`.
- `Calibrating` builds a fresh `Tracker()` per trial for this reason (`gaze.py:248`).

**Why it misleads:**
- B, the number keys, touch, `Onscreen` and `ChairStill` all need a world that overrides
  `signal` and `happened`. The parts listed do not supply them.
- A tracker kept across trials would score the previous trial's last sample as fresh at the
  next trial's first frames.

**Smallest correction:**
- §3.3: "a world that subclasses `gaze.Tracked`, overriding `signal` and `happened`, with a
  `Tracker` and `Detector` per trial".

---

## 14. `STAND_IN_HOUSINGS` as a module constant fits only this panel

**Spec:** §3.6 ("moved into the package as `geometry.STAND_IN_HOUSINGS`"), §5 (`--rig PATH`).

**Evidence:**
- `tests/_rig.py:33-36`: the right-hand housing is at `left_cm=54.997, right_cm=58.997`,
  which is the PG27UCDM's 58.997 cm width less 4.
- Neither `Housing` (`geometry.py:59-94`) nor `Geometry.__post_init__` (`geometry.py:120-149`)
  checks a housing against the panel.

**Why it misleads:** with `--rig` naming another panel, the "bottom corner" stand-in silently
lands mid-panel or off it.

**Smallest correction:** `geometry.stand_in_housings(panel_width_cm)`, placing one housing per
bottom corner of the panel it is given.

---

## 15. The tremor is seeded from "the session's seed", which is 0 for every `wlx taskd` session

**Spec:** §3.3 ("drawn from the session's seed").

**Evidence:**
- `service.py:589`: `_build` constructs every service session with `SessionSpec.seed=0`.
- Each run has its own seed (`RunSpec.seed = self._seed()`, `service.py:940`; `_fresh_seed`,
  `service.py:116-119`), recorded in its start row.

**Why it misleads:** every simulation session's tremor would be the same sequence, and it
would not be the seed the record attributes the run to.

**Smallest correction:** "drawn from the run's seed".

---

### Checked and found sound (for the plan's benefit)

- **Identity map.** `EyeMap(AFFINE, x=(0,1,0), y=(0,0,1), …)` passes degrees through, and
  `Mapping` accepts it at any version (`calibration.py:155-179, 431-475`). It cannot be a
  `MappingLog`'s version 0; see finding 6.
- **Tremor and readiness.** At 0.02° and 240 Hz, the detector becomes ready about 54 frames
  (about 225 ms) into each trial and stays quiet when still (run, above).
- **Staleness.** A fresh sample every frame, stamped `at`, keeps `Tracker.state` `ok`. `None`
  from `poll` reaches "lost" after 50 ms of frame time, then `tracker_lost`'s default 50 ms
  grace applies (`task.py` `Tolerances`).
- **Starting values.** Every §6 starting value is inside its `Param` range. The pre-flight's
  `values` item passes all three tasks with no `--set`; unset categorical appearances are not
  refused (`preflight.py` `values`). Only visual_search's load fails (finding 1).
- **ITI wait.** A real-time ITI through `link.idle` is buildable. `idle` returns 0 on a waiting
  command without consuming it, so the wait loop must drain each time and track its own
  deadline to resume the remainder (`link.py:1944-1948, 2484-2496`).
- **`--link` parsing.** It is fixed at two or three parts in `service.py:1168-1173`,
  `serve.py:1877-1882` and `cli.py:1606-1611`. All need the fourth, as §3.8 implies.
- **`Geometry` and `stand_in`.** `Geometry` can take a defaulted `stand_in` field without
  disturbing its validation. `config.json` is written field by field (`taskd.py:681-706`), so
  the new key appears only where added.
- **`wlx demo`'s subjects layout.** `REFERENCE/bounds.py` (`BOUNDS`) and
  `REFERENCE/settings.py` (`SETTINGS`) match what `_build` loads.
- **`wlx demo`'s allocation.** `tasks/allocation.py` carries all of `FRAMEWORK_CODES`, plus
  `PAUSE`, `RESUME` and `OPERATOR_MARK`.
