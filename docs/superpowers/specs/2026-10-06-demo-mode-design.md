# P4d-2b b4: demo mode, the mouse as the eye

**Status: revised 2026-11-07, for the PI's review** (it was parked on 2026-10-07). Designed 2026-10-06, in
three parts, each approved by the PI in conversation ("Looks right"); two design reviews then found what §14 lists,
and the PI chose to build other things first. It is part 3 of the pop-out search build
([its design, §2](2026-11-07-popout-search-design.md)), built after the PI approves this revision. It builds slice
**b4** of [the P4d-2b console spec](2026-09-26-P4d2b-browser-console-design.md) ("b4 — simulation with mouse
gaze") and closes backlog **XC-013**.

**For the PI:** §8 (welfare: no welfare-listed function changes) and §15 (one question).

## Revised 2026-11-07: what changed, and why

1. **A demo runs in its own private rig service, never inside a live one** (§3.1). The parked design opened a
   "simulation session" in any rig service, which needed two rules in `Service._open` (welfare-listed) and could
   leave a crashed demo stranded among a rig's real sessions, coming back as a live one (§14 item 10). The quick
   command's private copy of the rig service, which the PI already approved as one of the two doors, now holds
   every demo: its folder, its one animal and its simulated card and pump are its own from the start. **No
   welfare-listed function changes** (§8). The rig page's own door is the PI's to keep or drop (§15).
2. **The pop-out search is the first task it plays** (§5, §10), the mouse as the eye through `gaze.Tracked`, as
   the simulated eye of the same build plays it (§3.3 says how the two relate).
3. **It shows frames from the exact drawer, labeled** (engine spec §23), not the schematic §4.4 drew (§4.4).
4. **§14's items are applied**, each marked there done, changed or still open; the PI's answers of 2026-10-07
   are in.
5. **§6 (starting values) leaves this build**: the pop-out's starts are the PI's; XC-183 stays its own item.

§1-§13 are revised in place; the parked text, as approved on 2026-10-06 with its dated amendments and §14, is this
file at `b2d9cc4`. §2 and §6 are kept as decided, each with a dated note.

## 1. Why

Roadmap M1 names two deliverables that do not exist: **keyboard/mouse demo mode** and the operator document. S9 §5
and the architecture spec §11.2 say what demo mode is for: "any task drivable with the mouse standing in for gaze
and keys for responses, in thirty seconds, with no hardware". It is how a person confirms that a task Claude wrote
does what was asked, before an animal ever sees it (ADR-0006, D4), and how a student practices before a rig exists.
Its first task is **the pop-out search**: a person plays it with the mouse, scored by the rig's own eye rules, and
watches its stages, staircase and suggestions as a trainer will.

What exists (2026-11-07):

- **The trial loop takes its world as a seam** (`run.World`; `taskd.Session.world`).
- **`gaze.Tracked` is the rig's own eye path**, and since XC-456 a simulated session's gaze tasks are played
  through it by the simulated eye (`simeye.Eye`, inside `simeye.Seeing`, a `Tracked` subclass that only adds).
- **`wlx taskd` and `wlx serve` run whole sessions from the page** with the simulated card and pump, the
  trainer's panel included (the pop-out build's Task 7).
- **The screen description and the exact drawer** (`screen.resolve`, `exact.draw`; engine builds A1-A2): the
  definition of what each eye must see.
- **The mark channel** (P4d-2b b2a): a console's input into a running trial, checked once a frame without
  blocking, the model for gaze.

What does not: pacing a session to the wall clock, a way for a page to send a pointer to the rig, and the
animal's screen shown on the page.

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

> **Revised 2026-11-07.** This revision builds the first door alone, the private copy, which needs no
> welfare-listed change; the second, the rig page's, is offered with its cost (§8) and asked (§15). "Only the test
> monkey" now holds by construction (§3.1). Call 1 takes `tasks/eight_hour_bounds.py` (the PI, 2026-10-07). Call
> 2's tremor is the simulated eye's own noise, shared (§3.3). Call 3 left this build with §6.

## 3. The demo service (the rig side)

### 3.1 What makes one

**A demo runs in its own rig service.** `wlx demo` (§5) starts `wlx taskd --demo DIR` beside its own `wlx serve`,
on free loopback ports. With `--demo DIR`, `wlx taskd`:

- **creates `DIR`** (refused if it exists) and in it a subjects folder holding **`REFERENCE` alone**, written from
  the repository's `tasks/eight_hour_bounds.py` and `tasks/reference_subject.py` (the PI, 2026-10-07: "The 8-hour
  file"), and the folder its sessions are written to. **`--subjects` and `--root` are refused beside it**, so a
  demo service cannot reach a real animal's files or a rig's data;
- builds every session with the simulated card and pump (§3.2), the mouse as its eye (§3.3) and, on a rig whose
  light-sensor housings are unmeasured, the stand-in field (§3.6);
- binds the gaze endpoint (§3.8), which a rig service without `--demo` refuses;
- marks every frame and record as a demo's (§3.7).

Everything else is the rig's own path, unchanged: a session is opened, run and ended through `Service._open`,
`_start` and `_end`, as the page opens one. **A live rig service gains nothing**: no simulation choice, no rule, no
gaze endpoint. (The builder's: whether `wlx taskd --demo` writes the subjects folder or `wlx demo` writes it and
`--demo` refuses one holding anything but `REFERENCE`; either way a demo service holds no other animal.)

### 3.2 Apparatus

**A demo service's card and pump are the simulators, always** (`dio.Simulated`, `welfare.Simulated`): rewards are
counted, never delivered; event codes go to the simulated card and are recorded as in any session, never to a sync
box. Today `wlx taskd` has no other card or pump to build (`service.run` builds `Service` with its defaults, the
simulators); the day it gains a real one, `--demo` refuses it. **It drives no display**: its frames go to its page
(§3.9, §4.4), never to a display process (engine build E, not built).

**Every welfare limit runs as in any session**, against `REFERENCE`'s eight-hour file: the out-of-cage ceiling and
its warning, the fluid accounting, the departure and the return, and the stranded rule within the demo's own folder.

### 3.3 The eye: the mouse, through the rig's own gaze path

A demo session's world is **`Pointing`, a subclass of `gaze.Tracked` built as `simeye.Seeing` is**: the rig's
map, staleness, saccade detector and rules for which saccade counts where are all `Tracked`'s, unchanged, with a
fresh `Tracker` and `Detector` each trial (§14 item 8). It overrides `happened` only for the non-gaze guards of
§3.4. Its sample source, **`pointer.Source`**, gives one `eye.Sample` a frame from the newest position the page
sent, the same for both eyes, read through **the simulated eye's identity maps** (`simeye.MAPPING`'s, with its own
`why`, "the mouse, in degrees"). The map never changes in a demo: no recentering (§14 item 5).

**The mouse and the simulated eye** are two sample sources for one world:

| | The simulated eye (`simeye.Eye`, built) | The mouse (`pointer.Source`, this build) |
|---|---|---|
| Where it looks | the program's choice, from the display and the task's states | wherever the person puts the pointer |
| A saccade | a minimum-jerk profile it plans | the hand's path, each report eased across the frames it took (§14 item 9) |
| Noise | 0.02° per axis, `simeye.NOISE_DEG` | the same constant, imported, drawn from the run's seed (§14 item 16) |
| Map | the identity | the same identity maps |
| Scored by | `gaze.Tracked`, unchanged | `gaze.Tracked`, unchanged |
| Pace | as fast as the computer runs | the wall clock (§3.5) |
| Where | any simulated session (`Session._agent`), a census | a demo service only |

So a trial means the same under both: the task, its rules and its scoring are the rig's; only who chooses where to
look differs. A test holds them together (§9): the simulated eye's own samples, sent as pointer reports one a
frame, score the same outcomes through `Pointing` as through `Seeing`. And the paths the simulated eye never takes
(it "never corrects an answer, never leaves a target it landed on", `simeye`'s docstring), a second look and leaving
the target early, a person takes by hand.

**Reports and signal states** (§14 items 6 and 7):

- The page reports the pointer in degrees, from the drawing's own transform, at most once an animation frame while
  it moves and at least every `web.GAZE_EVERY_MS` while it is still; one report in flight at a time, each with a
  per-page sequence number, and `wlx serve` forwards only a report newer than the last it forwarded from that page.
- The source holds the newest report as current for `pointer.LIVE_S`; through a page's stall the last position is
  held and counts toward holds. Both numbers are the builder's, a few report intervals: they make a demo playable
  and claim nothing.
- **Off the drawing** (over the page's other panes, or out of the window) is **gaze off the screen**: a position
  outside every window, as an animal looking away, so no fixation or a fixation break, never tracker loss.
- **B held, or a page silent past `LIVE_S`**, is **tracker loss**: the source returns nothing, the tracker goes
  stale (`eye.Tracker.staleness`), and the loop sees tracker loss under the task's `tracker_lost`, as the rig sees
  a blink until V3 (`Tracked.signal` never answers `blink`).
- At each trial's first frame everything waiting but the newest report is discarded and the key press counts are
  rebased.

**What a mouse is not** (§14 item 17), said here and on the screen's key list:

- **A hand is slower than an eye.** A mouse is positioned on text in a mean 1.29 s (SD 0.42) after 0.36 s of homing
  [@card1977evaluation, Table 2, p. 10], where a monkey's saccadic reaction times are about 200 ms with no gap
  [@fischer1983saccadic]: a demo cannot judge any time window. The pop-out's 1.0 s to respond is an eye's; a player
  raises it with `--set response_deadline=3.0`, its declared maximum. Its 0.3 s from leaving the fixation window to
  landing (the `flight` state's `After(0.3)`, a literal in the task) cannot be raised: a hand slower than that, or
  one that stops short and corrects, is scored a look elsewhere (abort). If trying it shows a hand cannot land in
  time, that bound becomes a setting in wl-xtasks, reviewed with the task, never changed by demo mode.
- **The pointer lands where it is put**: window sizes and holds cannot be judged.
- **Both eyes are the pointer**: vergence is always zero, and each stimulus shown to one eye is labeled L or R,
  with its disparity when nonzero.
- **The mouse is both the eye and the hand** (§3.4).
- **A stimulus up for less than a drawing may never be drawn**, and no duration can be judged from the drawing;
  +y is up, with a test.
- **The operator's monitor is not the rig's panel**: the pop-out's colors are drawn as the exact drawer defines
  them, but whether they are isoluminant, and at 15 cd/m², cannot be judged by eye on it.

### 3.4 Every other input a task waits on

`pointer.inputs(trial)` gives each non-gaze input the task's states name a **number key, 1 to 9**, in the order the
states first name them: each `Pressed`/`Released`/`Response` device, each `FeatureAbove` source, and `ChairStill`.
A task naming more than nine is refused by the demo's pre-flight, naming them. `Pressed(device)` and
`Response(device)` fire on the key going down, `Released(device)` on it coming up; **presses are counted, not
sampled**, so a press and release between two frames is seen once. `FeatureAbove(source)` holds while its key is
held; `ChairStill` holds while its key is *not* held. `Touched(window)` holds while the mouse button is down with the
pointer inside that window, so the mouse is both the eye and the hand: a task that needs them in different places
cannot be completed by hand, and one that needs them together always is. `Onscreen` fires on the first frame after
the display changed, as a light sensor would see it. The pop-out uses none of these.

### 3.5 Real time

A demo session's frames run at the session's frame period (`service.FRAME_PERIOD`, 1/240 s). The world's `display`
is where a real display blocks on its flip, so it is where a demo waits: **until the frame's moment** on
`time.perf_counter`. A frame already late runs at once and moves the schedule on, never a catch-up burst. **Between
trials it waits nothing a rig does not**: the rig waits no gap outside a trial (`SessionSpec.iti` is added to the
session's frame clock, never waited), so a task's gap is a state of its own, as the pop-out's 1.0 s blank
(`between`) is, paced like any frame. A command (pause, stop, a change) is taken at the trial's boundary, as on a
rig. **No timing claim follows from any of this** (CLAUDE.md): the pacing makes a demo watchable; it measures
nothing.

### 3.6 The field

**Until the light sensors' housings are measured** (direct-view spec §9 item 1), `tasks/rig.py`'s direct view
refuses to exist. A demo service on such a rig builds its field with **stand-in housings**,
`geometry.stand_in_housings(panel_width_cm)`: one per bottom corner of the panel given, 4 × 3 cm with a 0.5 cm
margin, as `tests/_rig.py`'s today (which then imports them), and still nobody's measurement (§14 item 15). The
field and the record say "stand-in", and the drawing shades them so labeled. **A rig service without `--demo` never
takes stand-ins.**

### 3.7 The record, the stream, and keeping a demo apart from real data

- **`config.json`** gains `"demo": {"gaze": "mouse", "noise_deg": 0.02, "stand_in_housings": true|false}`, and no
  other session has the key. wl-preproc is told its name and shape before it is written.
- **The next telemetry schema** (21; `link.SCHEMA` is 20 today): every frame, idle or running, carries `demo` (a
  boolean), so every page and `wlx console` can say so (§14 item 12).
- **The pre-flight's eye-tracker item** (`preflight.unmeasured`, not welfare-listed) reads, in a demo, "this
  session's gaze is the mouse on its demo page", still an unknown to acknowledge.

**A demo is kept apart from real data by where it runs**, not by a rule anyone must remember:

1. **Its own folder.** Every session lands under `DIR`, made new in the computer's temporary folder and deleted when
   the demo ends (`--keep` copies it out first, §5), never a rig's `--root`: a rig service never finds it, stranded
   or not, and the end-of-session transfer (b6, not built) never sees it.
2. **Its own animal.** `REFERENCE`, whose files refuse any real animal; no real animal's folder is reachable
   (§3.1).
3. **Its own session number.** `demo-` and the date and time, given by `wlx demo`. It never asks the sync box for
   one (XC-460's client, not built 2026-11-07, is never called by a demo service), so no number of the lab's
   sequence is spent.
4. **Its own wires.** Loopback ports only, so no other computer reaches its page, its health endpoint or its link;
   its event codes go to the simulated card, never to a sync box or a recording.
5. **It says what it is**: the `demo` key in its record (in a kept copy too), and DEMO on every page (§4.2).

### 3.8 The gaze channel

**A fourth link endpoint, a PULL socket** (`--link PUB,REP,MARK,GAZE`), a demo service's alone (a rig service
refuses four endpoints), built as the mark socket is: bound loopback-only and read without blocking.
`pointer.Source.poll` drains what is waiting, **at most `pointer.DRAIN = 64` messages a frame, keeping the
newest**: bounded work, whatever arrives. A message is fixed-size binary, read into a buffer allocated once: the
page's sequence number, the pointer's x and y in degrees, whether it is over the drawing, B, the mouse button, the
keys held, and each key's press count. One the wrong size, or not finite, is counted and dropped, as a malformed
mark is.

### 3.9 The screen, from the rig

When what is visible changes, when a trial starts, and at least once a second, the demo's world **resolves the
screen description** (`screen.resolve`, with the session's calibration, so a color set's light is its realized
one) and publishes it whole on the link's PUB socket as a third message kind, **`Drawn`**, beside `Telemetry` and
`Idle`: the `screen.Screen`, the trial's windows as placed (an array's object windows where `task.placements` puts
them, with its target's alias named), the setup's viewports, and the trial and frame numbers. Whole, never a
change, because telemetry is lossy and latest-wins (S9a §9). A trial's end leaves the screen blank until the next
trial's first frame, as the animal's is. On the wire (§14 item 11): `decode` dispatches on a kind under the schema
check; `wlx console` skips it but counts it as alive; `service._Routed.publish` passes it through; `wlx serve`'s
hub keeps drawings apart from frames, in order, with their own event name.

**Only a demo's world publishes inside a trial**, with ZMQ's non-blocking send, and it allocates on a frame the
screen changes: a demo has no frame budget to protect (it waits on the wall clock, §3.5), and no rig world changes.

## 4. The page

The demo's own `wlx serve` serves **the rig's page, unchanged** but for what this section adds.

### 4.1 New session

A demo service's New session dialog offers `REFERENCE` alone, the one animal its subjects folder holds, and fills
*←cage at* with the clock time, still editable, parsed by `marks` as every departure is (a page convenience in
`web.py`; `marks` unchanged). No rig's page gains a simulation choice (§15).

### 4.2 The tag

Every page viewing a demo service shows **DEMO** in its header, from the frame's `demo` field.

### 4.3 The demo screen

It sits in the right column, where *replica · V11* is now, **only on a demo service's page**, and opens full-window
with a click or F (Escape closes it). **It is not the replica**, which redraws a live animal's screen at display rate
and stays gated on V11 (console spec §7).

### 4.4 What it shows: frames from the exact drawer, labeled (engine spec §23)

`wlx serve` draws each `Drawn` with **the exact drawer** (`exact.draw`, engine spec §4.9: the definition of what each
eye must see), on a thread of its own and never in the rig service's process: a drawing in progress finishes, and of
the screens that arrive meanwhile only the newest is drawn next. The image is:

- **a preview of the rig's panel**: its centimeters and degrees at fewer pixels (`viewport.viewports(...,
  pixels=...)`), each eye side by side through a stereoscope;
- **in sRGB**: the drawer's light through the default calibration, the sRGB standard
  (`exact.output_levels(image, photometry.SRGB)`), clipped where sRGB cannot make it, as the drawer clips;
- **a PNG** (the standard library's `zlib`, no new dependency) inside an SVG fragment whose coordinates are degrees,
  so the page turns the pointer into degrees with the drawing's own transform.

Labeled, on top of it:

| Label | Drawn as |
|---|---|
| the caption | "demo · the exact drawer's frame N · not the rig's panel: color and luminance approximate · not timing-valid" |
| each window | a dashed circle with its name; an array's object windows where the trial placed them, its target's labeled *target*, the scoring key (§14 item 4) |
| a stimulus shown to one eye | L or R, with its disparity when nonzero |
| a stimulus the drawer does not draw yet (`screen.NotYetDrawable` names its build), or a look with no value | an outline of its size, labeled with its name and why (§14 item 3) |
| the stand-in housings | shaded, labeled *stand-in* |
| the field's edge | the frame of the drawing |
| the pointer | a dot the page draws where the pointer is |

Under the drawing: the last trial's outcome (from telemetry) and the key list, with §3.3's limits. **Beside it, the
rest of the rig's page**: the trainer's panel shows the stage, the staircase's level and its lock, the last 50 answers
and the rig's suggestions with *Move up* and *Hold*, so a demo of the pop-out walks its stages as a trainer will.

The pop-out's discs and fixation point are flat discs, which the drawer draws today (engine build A1). **How long a
drawing takes is unmeasured**: the builder measures it with a script under `tools/` before any number is written
(CLAUDE.md), and chooses the preview's size from it.

### 4.5 Steering

- **Who may.** `POST /gaze` is gated exactly as `/commands` is (`_command`'s checks, factored out), never by
  `may_write`, which is false on the https page (§14 item 13); `wlx serve` checks, packs (§3.8) and pushes each
  report with ZMQ's non-blocking send, as a mark. Each report costs a request: stated, not measured. With no demo
  running, `/gaze` answers 409, "not a demo".
- **One page steers at a time**: the first whose pointer enters its drawing takes it and keeps it, off the drawing
  included, until that page releases it (Escape, or the page closed) or sends nothing for `serve.STEER_HOLD_S`.
  Another page's report meanwhile is answered 409, and that page shows "steered from another page".
- **Viewers who cannot write** see the drawing, and no dot.

### 4.6 Keys

**P and M keep their meaning** (pause, mark), the only keys the page binds today. The number keys and B are the
demo's, and act only while the pointer is over the drawing or the full-window view is open, never while typing in a
box.

## 5. The quick command, `wlx demo`

```
wlx demo TASK [--tasks DIR] [--rig PATH] [--allocation PATH] [--view direct|stereoscope]
              [--chaired] [--kind training|piloting|recording] [--plan NAME] [--start-block NAME]
              [--set NAME=VALUE ...] [--trials N] [--as WHO] [--keep DIR] [--no-browser]
```

1. **`TASK`** is a task's name in `--tasks` (default `tasks/`), or a path to a task file: for the pop-out,
   `wl-xtasks/tasks/popout_search.py`, its colors read beside it. `--rig` defaults to `tasks/rig.py`,
   `--allocation` to `tasks/allocation.py`.
2. **The task is checked first**, by the load checks `wlx check` runs, against the demo's own field (stand-ins
   where the rig's housings are unmeasured) and the rig's calibration or the default (§14 item 1). A refusal is
   printed with its sentences and nothing starts; warnings are printed.
3. **Then, on this computer only**: refused while a rig service runs on it (its drawing would share the processor a
   live session's frames run on; how it knows is the builder's). It chooses free loopback ports, makes `DIR` in the
   temporary folder with `wlx serve`'s health token file in it (§14 item 14), and starts **`wlx taskd --demo DIR`
   and `wlx serve` as child processes, as a rig runs them**.
4. **It opens a session** for `REFERENCE`, *←cage at* now, as `--kind` (default training), head-fixed in direct
   view unless `--chaired` or `--view stereoscope` (the pop-out needs a fixed head, so `--chaired` runs it with the
   `head-not-fixed` warning); and **starts a run** of the task, `--trials` long (default 1000, the page's), at
   `--start-block` (default the plan's first), with the task's own starts and any `--set` over them, as `wlx run`
   takes them. It accepts the open's warnings and the pre-flight's unknowns, printing each, as a person would on the
   page; a pre-flight failure is printed and stops it. `--as` names the person (default: this computer's login
   name), recorded as a box actor.
5. **It opens the default browser** on the full-window demo screen (Safari on the PI's Mac). The person is at the
   computer, so every control works: pause, stop, reward, a change mid-run, the trainer's panel, another run.
   `--no-browser` prints the address instead.
6. **Ctrl-C ends it**: the run stopped, the session ended with its return now, both children stopped, and `DIR`
   deleted. **`--keep DIR`** first copies the session's folder there (refused at start if it exists). A child that
   dies ends the other and the command, saying which and why.

## 6. Starting values (closes XC-183)

> **Revised 2026-11-07: no longer part of this build.** Demo mode's first task is the pop-out, whose starting values
> are the PI's (its design §3.1). XC-183 stays its own item, and `cal_hold`'s start is asked when it is built
> (§14 item 2). The section is kept as decided, the record `docs/references/decisions.md` cites.

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

> **Amended 2026-10-11 (the PI, confirming engine build C1's plan's Appendix B):** the reference
> tasks' settings in this table and in §14 were renamed: `fix_timeout` → `fix_acquisition`,
> `response_window` → `response_deadline`, `target_position` → `target_x`, `item_window` →
> `object_window`, `array_phase` → `array_rotation`, `visual_search`'s `eccentricity` →
> `array_eccentricity`, and `adaptive_detection`'s `contrast` and `eccentricity` → `target_contrast`
> and `target_eccentricity`; an array's members are objects, not items. The two detection tasks
> gained a `target_y`, at the PI's request the same day, starting at 0 (the controller's choice,
> not his). And every reference task now needs a fixed head (its Appendix B, item 31), so none
> runs in a chaired or cage-side session: a demo session runs one head-fixed, and `--chaired`
> (§5 item 3) refuses it. *Revised the same day, the PI on reviewing build C1 ("warnings are more
> appropriate most of the time")*: in a chaired or cage-side session each runs with the
> `head-not-fixed` warning, not refused, so `--chaired` runs one, printing that warning among the
> pre-flight's unknowns it acknowledges (§5 item 4). The text is left as approved.

## 7. When things fail

| What | What happens |
|---|---|
| `wlx taskd --demo` with `--subjects` or `--root`, or `DIR` existing | refused at start, nothing made |
| A fourth link endpoint on a rig service without `--demo` | refused at start |
| `wlx demo` on a computer where a rig service runs | refused before anything starts |
| The page closed, its network gone, or B held, mid-trial | tracker loss after `LIVE_S`, under the task's `tracker_lost` |
| The pointer off the drawing | gaze off the screen: no fixation, or a fixation break |
| A report older than one already forwarded | dropped by `wlx serve` |
| A malformed or non-finite gaze message | counted and dropped (§3.8); the frame goes on |
| A second page steering | 409; that page says "steered from another page" (§4.5) |
| `/gaze` with no demo running | 409, "not a demo" |
| A frame running late | it runs at once and moves the schedule on; never a catch-up burst (§3.5) |
| A stimulus the drawer cannot draw | an outline, labeled with why (§4.4) |
| Screens changing faster than they are drawn | the newest drawn next; those between never (§3.3's limits) |
| `wlx demo`: a task that fails its checks or pre-flight | its sentences printed; nothing left running |
| `wlx demo`: a child process dies | the other stopped, the command ends, naming which and why |
| `wlx demo --keep DIR` with `DIR` existing | refused before anything starts |
| `wlx demo` killed outright, with no Ctrl-C | its folder stays in the temporary folder, outside any rig's data |

## 8. Welfare

**This design changes no welfare-listed function.** Every item of architecture.md's list, held by
`tests/welfare_manifest.json` (26 items), stays byte for byte; `tools/welfare_diff.py` at the merge shows each one
`SAME`. A demo session goes through `Service._open`, `_start` and `_end` exactly as a page's session does, and every
limit runs against `REFERENCE`'s eight-hour file.

What keeps a demo away from any animal is where it runs, not a new rule in reviewed code: its one animal is
`REFERENCE`, whose files it writes itself (§3.1); its card and pump are the simulators and it drives no display
(§3.2); its sessions live in their own folder, never a rig's (§3.7); and it will not start beside a rig service (§5).
Those live in `service.run` and `cli`, with `Service._build` passing a demo's world and record on (none on the list,
which stays unchanged, the PI's rule of 2026-09-30).

**Only if the PI keeps the rig page's door (§15)**, a demo is opened inside a live rig service, and it needs two
changes, both in `Service._open`, for his review:

1. **A demo is refused for any animal but `REFERENCE`**, before anything is written. *What it does:* keeps
   simulated trials, rewards and times out of a real animal's records. *What it never touches:* a reward's size, a
   limit, the fluid count or any clock; it adds one refusal ahead of them.
2. **A demo session gets the simulated card and pump, and on an unmeasured rig the stand-in field, whatever the
   service was built with**, decided in `_open` and passed to `_build`. *What it does:* no demo can open a real
   valve. *What it never touches:* a reward's size, a limit, the fluid count (rewards are counted as in any
   session) or any clock.

With them, outside the list: a demo is never resumed, only ended (`_resume` refuses it, the flag read by
`resume.read`; the PI kept both off the list on 2026-10-02), and until a crashed demo in the rig's folder is ended,
`_open`'s existing stranded rule blocks every real animal's open.

## 9. Testing (sim first)

- **The pointer source and `Pointing`, in process**: the newest report wins, in sequence order; the liveness
  window; off the drawing is gaze off the screen; B is tracker loss; a still pointer makes no saccade, and a move
  across several frames that stops makes one that lands where it stopped; keys on their edges, a press and release
  between two frames counted once, rebased at a trial's start; touch, `Onscreen`, `ChairStill`, `FeatureAbove`; the
  drain bound; a malformed message counted. Pacing against an injected clock, never by sleeping.
- **The mouse and the simulated eye agree**: the simulated eye's samples for a session of the pop-out, sent as
  pointer reports one a frame, score the same outcomes through `Pointing` as through `Seeing`.
- **The pop-out by a scripted pointer, over the real ZMQ link**, each outcome recorded: correct; an early
  saccade; a wrong disc; a look to empty space; a second look; a target break; no response; no fixation; tracker
  loss by B; and a suggestion answered from the trainer's panel.
- **Kept apart**: `--demo` refuses `--subjects`, `--root` and an existing `DIR`; a rig service refuses a fourth
  endpoint; a demo service's sessions run on the simulated card and pump; a demo's `config.json` carries `demo` and
  no other session's does; a rig service started after a demo finds nothing of it, stranded or not.
- **The welfare list**: `tools/welfare_diff.py` from the build's base shows every item `SAME`.
- **The drawing**: `wlx serve`'s image of a `Drawn` equals `exact.draw` at the preview through sRGB, pixel for
  pixel; each label of §4.4's table; a look with no value and a kind not yet drawable outlined with why; an array's
  target labeled at its placed window; the stand-ins; L and R; coordinates in degrees, +y up; a newer screen during a
  drawing replacing the one waiting.
- **`wlx serve`**: `/gaze`'s gates, those of `/commands`; the packing; a stale report dropped; both 409s; the
  drawing's event.
- **The browser**, in Chromium and WebKit (`WLX_BROWSER=webkit`): the full-window screen, with a real Playwright
  mouse, plays the pop-out: hold on the point, the ring appears, move to the odd one, *correct*; leave early, an
  early saccade; leave the drawing, *no fixation*; hold B, *tracker lost*; the DEMO tag.
- **`wlx demo`** as a subprocess: it prints its address with `--no-browser`, a scripted pointer drives a trial
  through its `wlx serve`, and SIGINT ends it with its folder gone, or copied with `--keep`; refused beside a running
  rig service.
- Each new test seen failing first, and hand breaks after the fix; CI's mutation gate on every changed module.

## 10. Review before merge

- One review of the whole build, on the most capable model (the PI's process rule, 2026-11-07).
- The welfare diff, every item `SAME` (§8); and the PI's welfare review of §8's two items only if he keeps the rig
  page's door (§15).
- **The PI tries it**: `wlx demo wl-xtasks/tasks/popout_search.py --set response_deadline=3.0` in Safari. The browser
  tests run WebKit; this is the look and feel no test can judge.

## 11. Amendments to other documents (made with the build)

- **Console spec**: §4's slice list, b4 built, dated, pointing here; §1, the pointer travels as `POST`s and
  WebSockets stay deferred to the replica pane; §7, the replica pane is still gated on V11 and the demo screen is
  not it.
- **S9a §7 (processes and protocol)**: the link's fourth endpoint, a demo service's alone.
- **Engine spec §23**: demo mode built, its frames the exact drawer's.
- **Roadmap M1**: demo mode exists; the operator document is still owed (XC-014).
- **architecture.md**: the demo service in the `taskd` row; the gaze endpoint and the `Drawn` message in the
  `console` row. Nothing in its welfare section (§8).
- **`docs/pending-wl-preproc-amendments.md`**: the `demo` key, before it is written.
- **Backlog**: XC-013 closed; XC-146's "demo mode's path" removed, both sources now playing through
  `gaze.Tracked`.

## 12. Out of scope

- **A demo opened from a live rig's page**, unless the PI keeps it (§15).
- **The live replica**: gated on V11, unchanged.
- **Watching the simulated eye play on the demo screen, paced**: the same world seam; XC-146's.
- **The display process** (engine build E): a demo never drives a display.
- **The touchscreen kiosk** (S13): the mouse stands in for touch on this screen alone.
- **XC-183's starting values** (§6).

## 13. Build order

1. The pointer source and `Pointing` over `gaze.Tracked`, with keys and pacing, in process (§3.3-3.5), and the test
   that holds it to the simulated eye.
2. The gaze endpoint and the `Drawn` message on the link, telemetry schema 21 (§3.8, §3.9).
3. The demo service: `wlx taskd --demo`, its folder and animal, the simulators, the stand-in field, the record (§3.1,
   §3.2, §3.6, §3.7), wl-preproc told of `demo` first.
4. `wlx serve`: `/gaze`, steering, and the exact drawer's frames and labels (§4.4, §4.5).
5. The page: the tag, the demo screen and its full-window view, the pointer and the keys, *←cage at* filled (§4.1-4.3,
   §4.6).
6. `wlx demo` (§5).
7. The documents (§11).

## 14. Parked, 2026-10-07: what the reviews found, and what comes first

> **Revised 2026-11-07.** Each answer and item below is kept as written, its status after it in bold: **done** (the
> revision applies it, where named), **changed** (applied otherwise, and why), or **open**.

**The PI's answers, 2026-10-07, asked in the UI after both reviews:**

- **`wlx demo`'s test monkey takes `tasks/eight_hour_bounds.py`** ("The 8-hour file"):
  `REFERENCE` with the real cage-to-cage figure, so a demo is not cut off at
  `reference_bounds.py`'s ten-minute placeholder, whose warning would also show from the first
  frame (`welfare.WARN_WITHIN_DEFAULT` is thirty minutes). **Done**: §3.1, §3.2.
- **A default color calibration, and a warnings list** (in the PI's words): "There should be a
  default color calibration/lut that is used when one isn't specified by the rig file. There
  should maybe also be a warnings tab in the console that lists all things that are imperfect,
  such as this, but as acceptable. E.g., for a training session, having a perfect color
  calibration is a nice to have, not a need to have." This replaces both options offered
  (leave `visual_search` refused; a simulation-only stand-in). **Done**: built in engine build B (the default, the
  sRGB standard, and the session's warnings list).
- **Tasks before demo mode**: "Perhaps we should build some tasks before we build demo mode?"
  Then, asked the order: **"Default colors + warnings first"**. The order is: (1) the default
  color calibration and the warnings list; (2) trials that vary, with conditions, blocks and
  between-trial procedures declared by the task (XC-207, and wiring a task's `next_params`);
  (3) the reference tasks made right, with the PI's decisions on the science review's findings
  2, 3 and 9 (the staircase's rule, trials that never vary, `item_window` and `cal_hold`); (4)
  this build. **Changed**: (1) built in engine build B; (2) built in engine builds C2a to C3, with a declared
  staircase in the pop-out build (XC-242 still open for a task's own code); (3) replaced by the PI's order of
  2026-11-07, one real training task first, the pop-out, so demo mode waits on no reference task; XC-183 and
  `cal_hold` stay open with that work.

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
   the default color calibration has landed by then. **Changed**: the check is against the demo's own field (§5
   step 2); the default calibration has landed, so a color task loads on it with `color-on-default`, and the
   try-out is the pop-out with `--set response_deadline=3.0` (§10).
2. **§6 drops the "staircase" rationale**: `contrast` and `eccentricity` are read by nothing,
   and nothing calls `next_params` (S2). Every trial of a run is the same trial, on a rig as in
   a demo, until varying trials exist (S3). Whatever step (2) and (3) above change, §6 is
   rewritten against it, and `cal_hold`'s start is the PI's (S9 argues 0.5 s, not 0.3 s).
   **Changed**: §6 leaves this build (its dated note). Trials vary since engine builds C2a to C3. **Open**, with
   XC-183: §6's rewrite and `cal_hold`'s start, asked then.
3. **Appearances**: no run can set one (S4). A parameterized appearance is drawn as a labeled
   outline; a declared color or contrast is drawn as a **text label**, never as a hue or an
   opacity (S4, F1). **Changed**: frames come from the exact drawer (engine spec §23), so a light is drawn as its
   light, labeled approximate on the operator's monitor; a look with no value, or a kind the drawer does not draw
   yet, is a labeled outline saying why (§4.4). The pop-out's looks have a value every trial, drawn from its pool.
4. **Arrays** are drawn from their concrete item windows, with the `target`/`distractor`
   aliases as labels on their members, never at the alias's nominal position; while appearances
   are unset the drawing says the T is the scoring key, not what the animal sees (S5). **Done**: §3.9, §4.4 (the
   array as the drawer draws it, its object windows where the trial placed them, the target's labeled as the
   scoring key).
5. **No recentering, and P and M alone** keep their meaning (S6, F6): drop §3.3's recenter
   sentence and §4.6's R and C. The identity map never changes in a simulation. **Done**: §3.3, §4.6.
6. **Pointer reports**: the page keeps one in flight and each carries a per-page sequence
   number, the stale ones dropped (F8, S6); at each trial's first frame everything waiting but
   the newest is discarded and the press counts are rebased (F7). The liveness window and the
   report interval are re-chosen and the held position during a stall is stated (S6). **Done**: §3.3, §3.8; the
   two numbers are the builder's.
7. **Off the drawing is gaze off the screen**, a position outside every window, never tracker
   loss; tracker loss is B (until V3, a blink reaches the rig as tracker loss, so B is that and
   never `blink`) or a page gone quiet (S7, S8, F13). Steering is taken when the pointer first
   enters the screen and kept, off the drawing included, until released or quiet (S8). **Done**: §3.3, §4.5.
8. **The world subclasses `gaze.Tracked`**, overriding `happened` for keys, touch, `Onscreen`,
   `ChairStill` and `FeatureAbove`, with a fresh `Tracker` and `Detector` per trial (F13). **Done**: §3.3,
   `Pointing`, built as the simulated eye's `simeye.Seeing` is.
9. **A reported move spans the frames it took**: the source eases each report over the report
   interval, so a one-report flick is still a saccade; tests move the pointer across several
   frames (F3). **Done**: §3.3, §9.
10. **The apparatus and field rule**: decided in `Service._open` (on the welfare list) and passed
    to `_build`; **a simulation is never resumed, only ended** (`resume.read` reads the flag;
    `_resume` refuses it), so a crashed simulation cannot come back as a live session. Both go
    in §8's welfare summary (F2). **Changed**: a demo runs in its own rig service (§3.1), so no rule enters
    `Service._open` and no demo can come back as a live session: a rig service never sees its folder. If the PI
    keeps the rig page's door (§15), this item stands, as §8's two items.
11. **The `Screen` message**: `decode` dispatches on a kind under the schema check; `wlx console`
    skips it but counts it as alive; `service._Routed.publish` passes it through; `wlx serve`'s
    hub keeps screens apart from frames, in order, with their own SSE event name; the world
    republishes the screen at least every second, so `wlx console`'s 5 s timeout and a page
    that attaches mid-trial are both served (F5, F11, S12). **Done**: §3.9, named `Drawn`, apart from
    `screen.Screen`, which it carries.
12. **Schema 15 also carries `gaze`** (this rig service has a gaze endpoint), for §4.1's greying
    (F12). **Changed**: schema 21 carries `demo`, since a whole service is a demo's or not (§3.7), and no page
    greys a choice (§4.1).
13. **`/gaze` is gated exactly as `/commands` is** (`_command`'s checks, factored out), never by
    `may_write`, which is false on the https page (F9). Each report on the https page costs a
    connection and a token check: stated, not measured. **Done**: §4.5.
14. **`wlx demo`** writes `wlx serve`'s health token file into its throwaway root (outside any
    checkout) and chooses its ports before starting the children (F10). **Done**: §5 step 3.
15. **`geometry.stand_in_housings(panel_width_cm)`**, one per bottom corner of the panel given,
    not a constant fitted to one panel (F14). **Done**: §3.6.
16. **The tremor is drawn from the run's seed**, not the session's, which is 0 in every `wlx
    taskd` session (F15). **Done**: §3.3.
17. **Stated limits**, in §3.3 and on the key list: a hand takes a second or more from onset to a
    landing (a mouse positioned on text in a mean 1.29 s, SD 0.42, after 0.36 s of homing
    [@card1977evaluation, Table 2, p. 10]) where a monkey's eye takes about 0.25 s (saccadic
    reaction times about 200 ms with no gap [@fischer1983saccadic]), so demo mode cannot judge any
    time window (S10); the pointer lands where it is put, so window sizes and holds cannot be
    judged (S9); both eyes are the pointer, so vergence is always zero, and each stimulus not
    shown to both eyes is labeled L or R, with its disparity when nonzero (S11); the mouse is both
    the eye and the hand (S8); a stimulus up for less than a page update may never be drawn, and
    no duration can be judged from the drawing; +y is up, with a test (S12). *(Corrected
    2026-10-08: this said a hand takes "roughly 0.6-1 s" to land, a figure given without a
    source.)* **Done**: §3.3, with the pop-out's own windows and its colors.

## 15. Questions for the PI

1. A demo can run only as its own private copy of the rig service, which changes no welfare-listed code: is that
   enough, or do you also want a demo opened from a live rig's own page, which needs the two `Service._open` changes
   in §8 for your welfare review?
