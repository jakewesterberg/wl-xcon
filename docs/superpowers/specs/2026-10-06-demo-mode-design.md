# P4d-2b b4: demo mode, the mouse as the eye

**Status: parked 2026-10-07, before the PI's review of this written spec. Read §14 first.**
Designed 2026-10-06, in three parts, each approved by the PI in conversation ("Looks right").
Two design reviews then found that the body below overclaims in places and cannot be built as
written in others; on 2026-10-07 the PI chose to build what it needs first (§14). The body is
kept as approved, and §14 lists every change to make before it goes to the PI. It builds slice
**b4** of
[the P4d-2b console spec](2026-09-26-P4d2b-browser-console-design.md) ("b4 — simulation with
mouse gaze") and closes backlog **XC-013** and **XC-183**. It amends that spec where §11 says.

## 1. Why

Roadmap M1 names two deliverables that do not exist: **keyboard/mouse demo mode** and the
operator document. S9 §5 and the architecture spec §11.2 say what demo mode is for: "any task
drivable with the mouse standing in for gaze and keys for responses, in thirty seconds, with no
hardware". It is how a person confirms that a task Claude wrote does what was asked, before an
animal ever sees it (ADR-0006, D4), and how a student practices before a rig exists. The lab opens
in January 2027; the rigs, and every remaining step of the https sign-in, wait for it.

What exists already:

- **The trial loop takes its world as a seam** (`run.World`; `taskd.SessionSpec.world`). On a
  rig the world is hardware; in a simulated session it is `simulate.Subject`. "In demo mode it is
  a mouse and keyboard" is in `run.py`'s first paragraph, unbuilt.
- **`gaze.Tracked` is the rig's own eye path**: a sample source with `poll(at)`, `eye.Tracker`'s
  staleness, `calibration.Mapping`'s map to degrees, and `saccade.Detector`. Anything that
  produces `eye.Sample`s can drive it.
- **`wlx taskd` already runs whole sessions with the simulated card and pump**, opened, run and
  ended from the page (b3a). Its trials run flat out against the behaviour agent.
- **The mark channel** (P4d-2b b2a) carries a console's input into a running trial, checked once
  per frame without blocking: the model for gaze.

What does not: anything that paces trials to real time, any way for a page to send a pointer to
the rig, and any drawing of what is on the animal's screen. **The display engine itself is
deliberately undecided** until V1 can measure both candidates on a rig (ADR-0002's ruling of
2026-08-31, "decide after V1"), so demo mode draws a schematic, never the stimuli themselves.

## 2. Decided (PI, 2026-10-06, asked in the UI)

- **Demo mode is the next build**, after b2b-ready ("Demo mode", over the operator guide, the
  behavior data table and a page-fixes bundle). Every next step of the sign-in waits on the rigs.
- **Both doors in one build**: a quick command, and the rig page's simulation mode ("Both, in one
  build").
- **One engine, two doors** ("One engine, two doors"): the quick command starts a private copy of
  the rig service and the page and opens the task's screen, so passing the quick check means
  passing on the rig page.
- **A simulation session is for the test monkey alone** ("Only the test monkey"): nothing
  simulated can land in a real animal's fluid or time records; every welfare limit still runs,
  against the test monkey's own; rewards are counted, never delivered.
- **Part 1** (the rig side, §3), **Part 2** (the page, §4) and **Part 3** (the quick command, §5)
  were each approved as presented ("Looks right").

**Engineering calls made here, for the PI's review of this spec:**

1. **The test monkey is `REFERENCE`**, the subject `tasks/reference_bounds.py` and
   `tasks/reference_subject.py` already describe, whose files refuse any real animal.
2. **The pointer is given a small fixed tremor** (§3.3). A perfectly still pointer has no noise,
   so `saccade.Detector`'s noise scale is zero and it never becomes ready: no saccade would ever
   be detected and every `SaccadeTo` would wait out its window. The detector is left exactly as
   the rig runs it; the pointer is made to carry the noise an eye always has.
3. **Starting values for the three other reference tasks** (§6, closing XC-183), the shared ones
   copied from `fixation_detection`'s approved values. They are listed for the PI to approve or
   change.

## 3. The simulation session (the rig service)

### 3.1 What makes one

A session is a simulation when it is opened with `simulation: true`: by the page's New session
dialog (§4.1), or by `wlx demo` (§5), each sending `OpenSession` as the page does today with the
one field added. `wlx run` has none: the console is the path.

`Service._open` refuses a simulation session, each with a sentence and nothing recorded:

- **for any animal but `REFERENCE`**: "a simulation session is for the test monkey, REFERENCE,
  alone; nothing simulated may enter another animal's records";
- **when this rig service was started without a gaze endpoint** (§3.8): "this rig service has no
  gaze endpoint (`--link`'s fourth), so no page could steer a simulation";
- **when `--subjects` holds no `REFERENCE` folder**, as any animal without a folder is refused
  today.

A session opened without `simulation` is what it is today, `REFERENCE` included.

### 3.2 Apparatus

**A simulation session always gets the simulated card and pump** (`dio.Simulated`,
`welfare.Simulated`), whatever card and pump the service was built with. Today the service's own
are the simulators too; the rule is written now so that the day a real pump driver is wired in,
no simulation can open its valve. Rewards are counted, never delivered. Event codes go to the
simulated card and are recorded as in any session.

**Every welfare limit runs as in any session**, against `REFERENCE`'s own bounded config: the
out-of-cage ceiling, the fluid accounting, the departure and the return, the stranded rule.

### 3.3 The eye: the mouse, through the rig's own gaze path

The world a simulation session's trials run against is **`gaze.Tracked`**, the rig's own, with
three parts supplied:

- **A pointer source** (`pointer.Source`): what `poll(at)` returns is an `eye.Sample` built from
  the latest pointer position the page sent, the same position for both eyes, as a reading whose
  Purkinje difference *is* the position in degrees.
- **An identity map**: a `calibration.Mapping`, version 0, whose two eye maps pass degrees
  straight through, `why="the mouse, in degrees"`. Recentering (C) works as it will on a rig: it
  adds an offset and makes a new version.
- **The tremor** (engineering call 2): each sample is offset by seeded Gaussian noise, standard
  deviation `pointer.TREMOR_DEG = 0.02` degrees per axis, drawn from the session's seed. It is a
  simulation constant, not a claim about any eye, and the record names it (§3.7). Tests prove
  both of its properties: a still pointer produces no saccade, and a move that stops produces
  one.

So a hold, a fixation break, the 50 ms staleness placeholder (`eye.Tracker.staleness`, the
OpenIrisDPI paper's stall maximum until V3(a) sets ours) and a saccade behave as they will with
an animal. **A mouse is not an eye**, and two consequences are stated on the screen's key list
rather than hidden: a saccade is the pointer moving and then stopping, landing where it stops;
and a person with a mouse is slower than a monkey's eye, so a task's response window may need
more time (`--set`, or the page's parameters panel). Demo mode never changes a task's numbers by
itself. *(Corrected 2026-10-08: this said "the 50 ms staleness rule".)*

**Signal states.** While the page reports the pointer over its screen, `poll` returns a fresh
sample every frame, stamped `at`, holding the last position. The page reports on every move (at
most once per animation frame), on every key or button change, and at least every
`web.GAZE_EVERY_MS = 100` ms while the pointer is over the screen; the source treats its last
report as current for `pointer.LIVE_S = 0.5` s. Then:

- **pointer off the screen**, or no report for `LIVE_S`: `poll` returns nothing, the tracker goes
  stale, and the loop sees **tracker lost**, under the task's own `tracker_lost` tolerance;
- **B held**: `signal` answers **blink**, under the task's `blink` tolerance. (The rig's own
  tracker never reports a blink until V3; the demo lets the loop's blink path be seen.)

### 3.4 Every other input a task waits on

`pointer.inputs(trial)` gives each non-gaze input the task's states name a **number key, 1 to 9**,
in the order the states first name them: each `Pressed`/`Released`/`Response` device, each
`FeatureAbove` source, and `ChairStill`. A task naming more than nine is refused by the
simulation pre-flight, naming them. Then:

- `Pressed(device)` and `Response(device)` fire on the key going down, `Released(device)` on it
  coming up. **Presses are counted, not sampled**: the page sends each key's running press count,
  so a press and release that both land between two frames is still seen, once.
- `FeatureAbove(source)` holds while its key is held; `ChairStill` holds while its key is *not*
  held (holding it is the animal moving).
- `Touched(window)` holds while the mouse button is down with the pointer inside that window:
  the mouse stands in for touch (S9 §5).
- `Onscreen` fires on the first frame after the display changed, as a light sensor would see it.

### 3.5 Real time

A simulation session's frames run at the session's frame period (`service.FRAME_PERIOD`, 1/240
s). The world's `display` is where a real display would block on its flip, so it is where the
simulation waits: **until the frame's moment** on `time.perf_counter`. A frame that is already
late runs at once and moves the schedule on, so a stall is never followed by a burst faster than
real time. Between trials the session waits its inter-trial interval (`SessionSpec.iti`) in real
time, through the link's `idle`, so a command arriving then (pause, stop, a change) is taken at
once and not after the next trial; the wait then resumes for what is left of the interval. **No timing claim follows from any of this** (CLAUDE.md): the
pacing makes a demo watchable; it measures nothing.

A session opened without `simulation` runs flat out, as today.

### 3.6 The field

**Until the light sensors' housings are measured** (direct-view spec §9 item 1), `tasks/rig.py`'s
direct view refuses to exist, so no shipped task can run. A simulation session in direct view on a
rig whose housings are empty builds its field with **stand-in housings**: the ones `tests/_rig.py`
uses today, one per bottom corner, 4 × 3 cm with a 0.5 cm margin, moved into the package as
`geometry.STAND_IN_HOUSINGS` and still described as nobody's measurement. The field carries
`stand_in=True`, the screen shades them labeled "stand-in", and the record says so.

**A session opened without `simulation` never takes stand-ins**: its direct view on an
unmeasured rig refuses as it does today. `tests/_rig.py` keeps its own role and imports the
package's stand-ins rather than restating them.

### 3.7 The record and the stream

- **`config.json`** gains `"simulation": {"gaze": "mouse", "tremor_deg": 0.02, "stand_in_housings":
  true|false}`, and no such key in any other session. wl-preproc reads only `subject` from it
  (`wl_preproc/events/rigruns.py`, read 2026-10-06).
- **Telemetry schema 15**: every frame, idle or running, carries `simulation` (a boolean), so
  every page and `wlx console` can say so.
- **The pre-flight's eye-tracker item** reads, for a simulation session, "this session's gaze is
  the mouse on a page's simulation screen", still an unknown to acknowledge, as on a live session.

### 3.8 The gaze channel

A **fourth link endpoint, a PULL socket** (`--link PUB,REP,MARK,GAZE` for `wlx taskd` and `wlx
serve` alike), built as the mark socket is: bound loopback-only unless `--link-allow-remote`, and
read without blocking. `pointer.Source.poll` drains what is waiting, **at most
`pointer.DRAIN = 64` messages a frame, keeping the latest**: bounded work, whatever arrives. A
message is fixed-size binary, read into a buffer allocated once: the pointer's x and y in degrees,
whether it is over the screen, B, the mouse button, the keys held, and each key's press count.
One that is the wrong size, or not finite, is counted and dropped, as a malformed mark is. Only a
simulation session's world reads it; at each simulation session's open the socket is drained, so
nothing sent before can steer it.

### 3.9 The screen, from the rig

The world's `display` sees what is visible each frame. **When it changes** (and when a trial
starts), the world publishes **the whole current screen** on the link's PUB socket as a third
message kind, `Screen`, beside `Telemetry` and `Idle`: every visible stimulus as a description in
degrees, every window the trial declares, the field, and the trial's number. Whole, never a
change, because telemetry is lossy and latest-wins (S9a §9): a lost message can never leave a
half-updated picture. A trial's end leaves the screen blank until the next trial's first frame,
as the animal's is.

**Only a simulation session publishes inside a trial.** S9 §1 keeps the network out of the frame
budget, and a live session's loop is unchanged. A simulation has no frame budget to protect, and
the send is ZMQ's non-blocking one.

## 4. The page

### 4.1 New session

The dialog gains a **simulation** choice. Choosing it sets the subject to `REFERENCE` and locks
it, and fills *←cage at* with the current clock time, still editable, typed in the field as the
terminal's rules take it (the page has no `now` spelling; b3a-2 plan decision 6). When the
idle frame offers no `REFERENCE`, or the rig service has no gaze endpoint, the choice is greyed
with the reason.

### 4.2 The tag

Every page viewing a simulation session shows **SIMULATION** in its header, from the frame's
`simulation` field.

### 4.3 The simulation screen

It sits in the right column, where *replica · V11* is now, **only during a simulation session**,
and opens full-window with a click or F (Escape closes it). **It is not the replica.** The
replica redraws a live animal's screen at display rate over the lab network, and V11 must show a
browser can carry that before it exists (console spec §7). This screen claims nothing of the
kind: it draws a simulation's own state when it changes, and the live replica stays gated on V11.

### 4.4 What it draws

`wlx serve` renders each `Screen` to an **SVG fragment in Python**, as every pane is rendered
(console spec §1), and pushes it as a `screen` event; the page swaps it in. The SVG's coordinates
are degrees, so the page turns the pointer into degrees with the SVG's own transform.

| On the animal's screen | Drawn as |
|---|---|
| `Disc`, `Square` | the shape, at its size and color, its contrast as opacity |
| `Bar`, `Cross`, `Polygon`, `Annulus` | the shape, outlined |
| `Gabor`, `Grating`, `Plaid`, `Checkerboard`, `Noise`, `Dots`, `RDS`, `Picture`, `Movie` | an outline of its size (aperture, sigma or size, as it declares), labeled with its kind |
| `Array` | each item as its own appearance; the target marked **T** |
| an appearance that is a parameter with no value | a 1° outline labeled with the stimulus's name |
| `Blank` | nothing |
| each window | a dashed circle, labeled with its name |
| the stand-in housings | shaded, labeled "stand-in" |
| the field's edge | the frame of the drawing |

Under the drawing: the last trial's outcome (from telemetry), and the key list (§3.4), with the
two sentences of §3.3 about what a mouse is not. The pointer's dot is drawn by the page, on top,
where the pointer is.

### 4.5 Steering

- **Who may.** Only a page that may write (`may_write`: at the rig PC, or signed in with
  wl.works), sending from the page as `/commands` requires. Pointer reports go to **`POST
  /gaze`**, which `wlx serve` checks, packs (§3.8) and pushes with ZMQ's non-blocking send, as a
  mark. A frame that says no simulation is running makes `/gaze` answer 409, "not a simulation
  session".
- **One page steers at a time**: the first whose pointer is over its screen. `wlx serve` holds
  that page's id until it reports the pointer gone, or sends nothing for `serve.STEER_HOLD_S =
  1.0` s. Another page's report meanwhile is answered 409, and that page shows "steered from
  another page".
- **Viewers who cannot write** see the stimuli and the windows, and no eye dot.

### 4.6 Keys

P, R, C and M keep their meaning (pause, reward, recenter, mark). The number keys and B are the
simulation's, and act only while the pointer is over the screen or the full-window view is open,
never while typing in a box.

## 5. The quick command, `wlx demo`

```
wlx demo TASK [--tasks DIR] [--rig PATH] [--allocation PATH] [--view direct|stereoscope]
              [--chaired] [--set NAME=VALUE ...] [--trials N] [--as WHO] [--keep DIR]
              [--no-browser]
```

1. **`TASK`** is a task's name in `--tasks` (default `tasks/`), or a path to a task file. It runs
   from a copy of wl-xcon; `--rig` defaults to `tasks/rig.py`, `--allocation` to
   `tasks/allocation.py`.
2. **The task is checked first**: the load checks `wlx check` runs, against the chosen setup.
   A refusal is printed with its sentences, and nothing starts.
3. **Then, on this computer only**, it starts **two child processes, `wlx taskd` and `wlx serve`,
   exactly as a rig runs them**, on free loopback ports, so it never collides with a rig service
   on the same machine:
   - a throwaway root, and a subjects folder holding `REFERENCE` alone, from
     `tasks/reference_bounds.py` and `tasks/reference_subject.py`;
   - head-fixed in direct view unless `--chaired` or `--view stereoscope`;
   - *←cage at* the current clock time; `--as` names the person (default: this computer's login
     name), recorded as a box actor.
4. **It opens the session and starts a run** of the task, `--trials` long (default 1000, the
   page's), with the task's own starting values and any `--set` over them, as `wlx run` takes
   them. It acknowledges the pre-flight's unknowns, printing each one, as a person would on the
   page; a pre-flight failure is printed and stops it.
5. **It opens the default browser** straight onto the full-window simulation screen (Safari on
   the PI's Mac). The person is at the rig PC, so every control works: pause, stop, reward,
   changing a number mid-run, starting another run. `--no-browser` prints the address instead.
6. **Ctrl-C ends it**: the run is stopped, the session ended, the return recorded now, both
   children stopped, and the throwaway root deleted. **`--keep DIR`** first copies the session's
   folder into `DIR` (refused at start if it exists), to look at afterwards. A child that dies
   ends the other and the command, saying which and why.

## 6. Starting values (closes XC-183)

The values the three reference tasks declare, so they run from the page and from `wlx demo`. The
values they share with `fixation_detection` copy its approved ones (the mockup the PI reviewed,
b3a-2 plan decision 1); `adaptive_detection.next_params` already uses the same timings.
**Appearances are not given a start** (`Param` refuses one until something records and publishes
it), so they draw as §4.4 says until a run sets them.

| Task | Parameter | Start | Why |
|---|---|---|---|
| all three | `fix_timeout` | 4.0 s | `fixation_detection`'s |
| `adaptive_detection`, `visual_search` | `fix_hold` | 0.3 s | `fixation_detection`'s |
| | `response_window` | 0.6 s | `fixation_detection`'s |
| | `target_hold` | 0.2 s | `fixation_detection`'s |
| | `fix_window` | 2.0° | `fixation_detection`'s |
| `adaptive_detection` | `target_window` | 3.0° | `fixation_detection`'s |
| | `target_position` | 10.0° | `fixation_detection`'s |
| | `contrast` | 1.0 | the staircase's ceiling: it starts easy and comes down |
| | `eccentricity` | 10.0° | `abs(target_position)`, as the task holds it |
| `visual_search` | `item_window` | 1.0° | the largest its declared range allows |
| | `eccentricity` | 8.0° | `Array`'s own default ring |
| | `set_size` | 4 | `Array`'s own default |
| | `target_index` | 0 | `Array`'s own default |
| | `array_phase` | 0.0° | `Array`'s own default |
| `calibration` | `target_x`, `target_y` | 0.0°, 0.0° | the center |
| | `cal_window` | 4.0° | twice `fix_window`: a calibration window admits gaze as wrong as calibration will correct |
| | `cal_hold` | 0.3 s | `fixation_detection`'s `fix_hold` |

## 7. When things fail

| What | What happens |
|---|---|
| A simulation for another animal | refused at open, with §3.1's sentence; nothing recorded |
| A rig service without a gaze endpoint | the page's choice greyed; an open refused, §3.1 |
| The page closed, or its network gone, mid-trial | after `LIVE_S` the tracker goes stale: tracker lost, under the task's tolerance |
| A malformed or non-finite gaze message | counted and dropped (§3.8); the frame goes on |
| A second page steering | 409; that page says "steered from another page" (§4.5) |
| `/gaze` with no simulation running | 409, "not a simulation session" |
| A frame running late | it runs at once and moves the schedule on; never a catch-up burst (§3.5) |
| `wlx demo`: a task that fails its checks or pre-flight | its sentences printed; nothing left running |
| `wlx demo`: a child process dies | the other stopped, the command ends, naming which and why |
| `wlx demo --keep DIR` with `DIR` existing | refused before anything starts |

## 8. Welfare

`Service._open` is on the welfare-critical list (architecture.md), and this build changes it.
The PI reviews these as a numbered summary before merge:

1. A simulation session is opened for `REFERENCE` alone; any other animal is refused, so nothing
   simulated enters a real animal's fluid or time records.
2. A simulation session always gets the simulated card and pump, whatever the service was built
   with, so no simulation can ever open a real valve.
3. Every welfare limit runs in a simulation session as in any other, against `REFERENCE`'s own
   bounded config.
4. The page fills a simulation's *←cage at* with the current clock time, still editable and
   parsed by the terminal's rules (`marks`), unchanged.

No other welfare-critical function changes. The list of reviewed functions is unchanged (the
PI's rule, 2026-09-30).

## 9. Testing (sim first)

- **The pointer source and world, in process**: the latest position wins; the liveness window;
  off-screen is tracker lost; B is blink; a still pointer produces no saccade, and a move that
  stops produces one that lands where it stopped; keys fire on their edges and a press and
  release between two frames counts once; touch, `Onscreen`, `ChairStill`, `FeatureAbove`; the
  drain bound; a malformed message counted. Pacing is tested against an injected clock, never by
  sleeping.
- **The screen**: each row of §4.4's table, an unset appearance, an array's target, the
  stand-ins; the SVG's coordinates in degrees.
- **The service, over the real ZMQ link**: a simulation session driven by a scripted pointer
  pushed to the gaze endpoint makes a correct trial, a fixation break, a no-fixation, a wrong
  target and a tracker lost, each recorded; another animal refused; **a service built with a
  pump that fails any use still opens a simulation that rewards**, which proves the simulated
  one was used; a live open on an unmeasured rig still refuses direct view.
- **`wlx serve`**: `/gaze`'s gates (a writer, from the page, a simulation running, the steering
  page), the packing, both 409s; the `screen` event.
- **The browser**, in Chromium and WebKit (`WLX_BROWSER=webkit`): the full-window screen, with a
  real Playwright mouse: hold on the fixation point, the target appears, move to it, *correct*;
  leave early, *fixation break*; leave the screen, *tracker lost*; the SIMULATION tag; the New
  session choice locking the subject.
- **`wlx demo`** as a subprocess: it starts, prints its address with `--no-browser`, a scripted
  pointer drives a trial through its `wlx serve`, and SIGINT ends it with the folder gone, or
  copied with `--keep`.
- **The mutation sweep** of every new and changed function, read line by line.

## 10. Review before merge

- The per-task reviews and a final whole-branch review on the most capable model, as before.
- **The PI's welfare review** of §8's four items, as a numbered summary.
- **The PI tries it**: `wlx demo visual_search` in Safari, and a simulation session opened from
  the rig page. The browser tests run WebKit; this is the look and feel no test can judge.

## 11. Amendments to other documents (made with the build)

- **Console spec §4's slice list**: b4 built, dated, pointing here.
- **Console spec §1**: the simulation screen's pointer travels as `POST`s; WebSockets stay
  deferred to the replica pane.
- **Console spec §7**: the replica pane is still gated on V11; the simulation screen (§4.3) is
  not it.
- **S9a §7 (processes and protocol)**: the link's fourth endpoint.
- **Roadmap M1**: demo mode exists; the operator document is still owed (XC-014).
- **architecture.md**: the gaze endpoint beside the mark endpoint in the `console` row, and the
  simulation session's rules where its welfare list describes `Service._open`.

## 12. Out of scope

- **The live replica**: gated on V11, unchanged.
- **Scripted gaze** (the mockup's second option): XC-146, its own item.
- **Drawing the real stimuli**: the display engine is ADR-0002's, decided after V1.
- **The touchscreen kiosk** (S13): the mouse stands in for touch on this screen alone.
- **Leaving simulation sessions out of the end-of-session transfer** (b6): filed in this build,
  since b6 does not exist; a simulation's `config.json` already says what it is.

## 13. Build order

1. The pointer source, the identity map, the tremor, and the world over `gaze.Tracked`, with
   keys and pacing (§3.3-3.5), in process.
2. The gaze endpoint and the `Screen` message on the link (§3.8, §3.9), telemetry schema 15.
3. The simulation session in the service: `simulation` on `OpenSession`, the `REFERENCE` rule,
   the simulated apparatus, the stand-in field, the record (§3.1, §3.2, §3.6, §3.7).
4. `wlx serve`: `/gaze`, steering, the `screen` event and its SVG renderer (§4.4, §4.5).
5. The page: the New session choice, the tag, the screen and its full-window view, the pointer
   and the keys (§4.1-4.3, §4.6).
6. The starting values (§6).
7. `wlx demo` (§5).
8. The documents (§11), and the welfare summary.

## 14. Parked, 2026-10-07: what the reviews found, and what comes first

**The PI's answers, 2026-10-07, asked in the UI after both reviews:**

- **`wlx demo`'s test monkey takes `tasks/eight_hour_bounds.py`** ("The 8-hour file"):
  `REFERENCE` with the real cage-to-cage figure, so a demo is not cut off at
  `reference_bounds.py`'s ten-minute placeholder, whose warning would also show from the first
  frame (`welfare.WARN_WITHIN_DEFAULT` is thirty minutes).
- **A default color calibration, and a warnings list** (in the PI's words): "There should be a
  default color calibration/lut that is used when one isn't specified by the rig file. There
  should maybe also be a warnings tab in the console that lists all things that are imperfect,
  such as this, but as acceptable. E.g., for a training session, having a perfect color
  calibration is a nice to have, not a need to have." This replaces both options offered
  (leave `visual_search` refused; a simulation-only stand-in).
- **Tasks before demo mode**: "Perhaps we should build some tasks before we build demo mode?"
  Then, asked the order: **"Default colors + warnings first"**. The order is: (1) the default
  color calibration and the warnings list; (2) trials that vary, with conditions, blocks and
  between-trial procedures declared by the task (XC-207, and wiring a task's `next_params`);
  (3) the reference tasks made right, with the PI's decisions on the science review's findings
  2, 3 and 9 (the staircase's rule, trials that never vary, `item_window` and `cal_hold`); (4)
  this build.

**What the reviews found.** Both reports are kept as written in `docs/superpowers/reviews/`
(`2026-10-06-demo-mode-science-review.md`, 12 findings; `...-feasibility-review.md`, 15). The
build session re-checked the main claims against the code on 2026-10-06: `visual_search` refused
on `uncalibrated-color` against the stand-in housings (`wlx check`, run); appearances unsettable
(`preflight.values`, `Session.set`); the array's `distractor` alias at the target
(`task.expand_windows`); no recenter anywhere and only P and M bound (`web.py`); the apparatus
and field chosen in `Service._build`, which `_resume` shares; `REFERENCE`'s 600 s ceiling.

**What must change in §1-§13 before this goes to the PI** (S = science review, F = feasibility
review, by number):

1. **§5 step 2 checks against the simulation's own field**, stand-in housings included (S1, F10);
   §10's try-out is `wlx demo fixation_detection --set response_window=1.5` (S1, S10), unless
   the default color calibration has landed by then.
2. **§6 drops the "staircase" rationale**: `contrast` and `eccentricity` are read by nothing,
   and nothing calls `next_params` (S2). Every trial of a run is the same trial, on a rig as in
   a demo, until varying trials exist (S3). Whatever step (2) and (3) above change, §6 is
   rewritten against it, and `cal_hold`'s start is the PI's (S9 argues 0.5 s, not 0.3 s).
3. **Appearances**: no run can set one (S4). A parameterized appearance is drawn as a labeled
   outline; a declared color or contrast is drawn as a **text label**, never as a hue or an
   opacity (S4, F1).
4. **Arrays** are drawn from their concrete item windows, with the `target`/`distractor`
   aliases as labels on their members, never at the alias's nominal position; while appearances
   are unset the drawing says the T is the scoring key, not what the animal sees (S5).
5. **No recentering, and P and M alone** keep their meaning (S6, F6): drop §3.3's recenter
   sentence and §4.6's R and C. The identity map never changes in a simulation.
6. **Pointer reports**: the page keeps one in flight and each carries a per-page sequence
   number, the stale ones dropped (F8, S6); at each trial's first frame everything waiting but
   the newest is discarded and the press counts are rebased (F7). The liveness window and the
   report interval are re-chosen and the held position during a stall is stated (S6).
7. **Off the drawing is gaze off the screen**, a position outside every window, never tracker
   loss; tracker loss is B (until V3, a blink reaches the rig as tracker loss, so B is that and
   never `blink`) or a page gone quiet (S7, S8, F13). Steering is taken when the pointer first
   enters the screen and kept, off the drawing included, until released or quiet (S8).
8. **The world subclasses `gaze.Tracked`**, overriding `happened` for keys, touch, `Onscreen`,
   `ChairStill` and `FeatureAbove`, with a fresh `Tracker` and `Detector` per trial (F13).
9. **A reported move spans the frames it took**: the source eases each report over the report
   interval, so a one-report flick is still a saccade; tests move the pointer across several
   frames (F3).
10. **The apparatus and field rule**: decided in `Service._open` (on the welfare list) and passed
    to `_build`; **a simulation is never resumed, only ended** (`resume.read` reads the flag;
    `_resume` refuses it), so a crashed simulation cannot come back as a live session. Both go
    in §8's welfare summary (F2).
11. **The `Screen` message**: `decode` dispatches on a kind under the schema check; `wlx console`
    skips it but counts it as alive; `service._Routed.publish` passes it through; `wlx serve`'s
    hub keeps screens apart from frames, in order, with their own SSE event name; the world
    republishes the screen at least every second, so `wlx console`'s 5 s timeout and a page
    that attaches mid-trial are both served (F5, F11, S12).
12. **Schema 15 also carries `gaze`** (this rig service has a gaze endpoint), for §4.1's greying
    (F12).
13. **`/gaze` is gated exactly as `/commands` is** (`_command`'s checks, factored out), never by
    `may_write`, which is false on the https page (F9). Each report on the https page costs a
    connection and a token check: stated, not measured.
14. **`wlx demo`** writes `wlx serve`'s health token file into its throwaway root (outside any
    checkout) and chooses its ports before starting the children (F10).
15. **`geometry.stand_in_housings(panel_width_cm)`**, one per bottom corner of the panel given,
    not a constant fitted to one panel (F14).
16. **The tremor is drawn from the run's seed**, not the session's, which is 0 in every `wlx
    taskd` session (F15).
17. **Stated limits**, in §3.3 and on the key list: a hand takes roughly 0.6-1 s from onset to a
    landing where a monkey's eye takes about 0.25 s, so demo mode cannot judge any time window
    (S10); the pointer lands where it is put, so window sizes and holds cannot be judged (S9);
    both eyes are the pointer, so vergence is always zero, and each stimulus not shown to both
    eyes is labeled L or R, with its disparity when nonzero (S11); the mouse is both the eye and
    the hand (S8); a stimulus up for less than a page update may never be drawn, and no duration
    can be judged from the drawing; +y is up, with a test (S12).
