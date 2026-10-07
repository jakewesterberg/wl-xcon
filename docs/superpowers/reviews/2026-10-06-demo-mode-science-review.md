# Demo mode spec (2026-10-06): where a person validating a task would be misled

> **What this is.** A design review of `../specs/2026-10-06-demo-mode-design.md`, written on 2026-10-06 by a reviewer subagent the build session dispatched, kept as written. Its main claims were re-checked by that session (the spec's §14 lists what they change, to fold in when the build resumes). The scratch scripts it mentions were not kept.

Science review of `docs/superpowers/specs/2026-10-06-demo-mode-design.md`, read against the
worktree `b2b-remote-signin`, 2026-10-06. Welfare policy deliberately not reviewed.

**How claims were checked.** Every code claim below was read in source and, where it could
be, run: `wlx check` on all four reference tasks (with `tasks/rig.py` and with
`tests/_rig.py`'s stand-in housings); `check.parameters_used` on each task; and synthetic
traces through `saccade.Detector` (script: `scratchpad/detsim.py`, run with `python3 -I`).
**The detector numbers are arithmetic on synthetic minimum-jerk traces, not measurements of
this system.** Literature numbers are approximate and cited. Anything not verifiable is
marked UNVERIFIED.

Severity scale: **misleading** (a person would come away believing the animal gets a
different experiment from the one it gets), **limitation to state** (true of any mouse
demo; harmless once said), **minor**.

---

## 1. As specified, `wlx demo` cannot start any reference task, and `visual_search` cannot start at all

**Scenario.** The PI follows §10: `wlx demo visual_search` in Safari. §5 step 2 runs "the
load checks `wlx check` runs, against the chosen setup" before anything starts.

- Against `tasks/rig.py` (§5 item 1's default `--rig`), **every** task refuses: `refused: direct
  view's field excludes the light sensors' housings, and none were given` (run 2026-10-06
  on all four). §3.6's stand-in housings are given to the *simulation session*, not to the
  step-2 check that runs before the session exists.
- Against the stand-ins (`tests/_rig.py`), `fixation_detection`, `adaptive_detection` and
  `calibration` pass, and `visual_search` is refused with three blocking
  `uncalibrated-color` findings (its DKL red and green; `check._color_faults`,
  `check.py:791`). Nothing in `cli.py`, `taskd.py` or `service.py` supplies a
  `photometry.Calibration` to `check()` (`taskd.py:1982`, `preflight.py:82`), so this refuses
  in every session, simulated or live. The task says so on purpose (`visual_search.py:15-17`).

**What the person sees:** a refusal printed and nothing started. §6's starting values for
`visual_search` ("so they run from the page and from `wlx demo`") cannot make it run, and
§10's acceptance step cannot be performed.

**Severity:** misleading (about what the spec delivers; the spec's own acceptance step fails).

**Smallest change.**
- §5 step 2: "checked against the field the simulation session will build, stand-in housings
  included (§3.6)".
- §6 and §10: "`visual_search` refuses in every session, demo included, until a measured
  display calibration exists (its `uncalibrated-color` findings are blocking); its starting
  values are declared for that day. The PI's try-out is `wlx demo fixation_detection`."
- If the PI wants search demonstrable before photometry, that is a science-facing call to
  ask, not to file: a simulation-only stand-in panel mirroring §3.6 (labeled, recorded,
  never taken by a live session) would load the task — but see finding 4: it would still
  draw no colors, because no run can set an appearance.

---

## 2. `adaptive_detection`'s adaptation is wired to nothing, so the demo shows plain detection as "adaptive"

**Scenario.** `wlx demo adaptive_detection`. The person holds the fixation point, the target
comes up at 10°, they move to it, *correct*, over and over. It looks like the task works.

**What the animal would get.** Plain fixed-contrast detection at one location:
- `contrast` and `eccentricity` are declared (`adaptive_detection.py:71-73`) and read by
  **no** stimulus, window or guard: `check.parameters_used` returns neither. The target's
  look is `P("target_looks")`, whose choices are `Disc(size=1.0)` / `Square(size=1.0)` with
  the default `contrast=1.0` literal.
- `next_params` (the staircase) is called by nothing in `wl_xcon/` (grep, 2026-10-06; only
  `tests/test_reference_tasks.py` calls it). Nothing in `taskd` loads or calls a task
  module's `next_params`; its between-trial hooks (`make_world`, `observe`) are the
  framework's.

§6's "`contrast` 1.0 — the staircase's ceiling: it starts easy and comes down" is false: it
never comes down, and if it did, nothing would draw or display it.

**A science problem underneath, for the PI when this is wired** (asked, not filed). As
written, `next_params` moves the staircase only on `CORRECT` vs `WRONG_TARGET`. In this task
`WRONG_TARGET` is only `Exited("target")` during the 0.2 s verify hold — a hold failure
after landing, not a perceptual error. The perceptual miss is `NO_RESPONSE`, which
`next_params` deliberately excludes. With the target at a fixed location within a
mini-block and no target-absent trials, an animal that saccades to the known location after
`fix_hold` is paid at any contrast, so the staircase would descend toward its 0.02 floor on
anticipations and never be driven back up by a miss. It would converge on hold reliability,
not on detection threshold.

**Severity:** misleading.

**Smallest change.** Replace §6's two rows with: "`contrast`, `eccentricity`: declared and
read by nothing — no stimulus or window uses them and nothing calls `next_params`; the task
runs as fixed-contrast detection at `target_position`, in a demo and on the rig." File the
wiring as a backlog item. Optional, cheap, and squarely "keeps the demo honest": the
simulation pre-flight names declared parameters nothing reads (`preflight.values` already
computes `parameters_used`), because a demo can never show a knob that turns nothing.

---

## 3. Every trial is the same trial — in the demo and on the rig today — and the spec does not say so

**Scenario.** `wlx demo fixation_detection` / `calibration` / (once it loads) `visual_search`,
1000 trials.

**What the person sees:** the target at 10° right on every trial; the calibration target at
(0, 0) on every trial; the search target at item 0, phase 0°, on every trial.

**What the animal would get:** exactly the same. A run is one block of one condition with no
values (`taskd._plan`, `taskd.py:1798-1815`; values per trial are `spec.values` +
`condition.values` = `{}`, `taskd.py:2199-2200`; XC-207). Nothing varies `target_position`
("one of six positions", `fixation_detection.py:3`), `array_phase` ("randomised between
trials so the animal cannot learn positions", `visual_search.py:99`) or `target_index`;
nothing walks the 13-point constellation (`calibration.conditions` and `gaze.Calibrating`
are used only by tests); nothing runs the staircase (finding 2). For an animal, a search
target always in the same place is not search, and a detection target always in the same
place is a learnable location.

The danger is interpretive: a person reading the task docstrings will take the demo's
sameness for a simplification of the demo, when it is the experiment.

**Severity:** misleading.

**Smallest change.** One sentence in §6 (or §3): "Every trial of a run uses the same values —
the task's starts, `--set` and live edits — because a run is one block of one condition
(`taskd._plan`, XC-207), on a rig as in a demo. Nothing yet varies target position, array
phase or target index, walks the calibration constellation, or runs a staircase: what the
demo shows trial after trial is what the animal would get." Whether live runs of these
tasks should be allowed before XC-207 is a PI question.

---

## 4. No appearance can ever be set, so the demo never shows what a stimulus looks like

**Scenario.** Any task whose look is a parameter: `fixation_detection`'s and
`adaptive_detection`'s target, `visual_search`'s target and distractors.

**What the person sees:** for the whole demo, "a 1° outline labeled with the stimulus's name"
(§4.4). §6 says appearances "draw as §4.4 says **until a run sets them**" — but no run can:
- `--set target_looks=…` arrives as a string (`cli.py:1574-1577`) and `preflight.values`
  refuses a value not in `choices` (`preflight.py:154-156`), whose members are `Disc(...)`
  objects;
- the page sends a number or a word (`link._setting`), and `Session.set` refuses anything
  not in `choices` (`taskd.py:972-974`).

So shape (disc vs square), size, color and contrast are never shown. The demo cannot reveal
a target that is the wrong shape, a distractor set that is the same as the target, or a
contrast that is wrong.

**When appearances do become settable**, §4.4's "its color" and "its contrast as opacity"
would mislead in their own right: DKL and xyY colors have no meaning on the viewer's
uncalibrated screen (the isoluminant red/green pair `visual_search` is built on would be
drawn with whatever luminance difference the conversion happens to produce — a luminance
cue the animal does not get), and opacity has no sign, so it cannot carry a decrement.

**Severity:** misleading.

**Smallest change.** §6: "No run can set an appearance today: `--set` and the page carry
numbers and words, and an appearance is neither. Every parameterized appearance is drawn as
an outline labeled with its stimulus's name for the whole demo; demo mode checks where
things are and how they are scored, never what they look like." §4.4: color and contrast
are drawn as **text labels** ("DKL l−m +0.08", "contrast 0.12"), never as fill color or
opacity.

---

## 5. The search drawing hands the person the answer, and a literal renderer would draw the distractor window on the target

**Scenario.** `visual_search` (once it loads, finding 1).

**What the person sees:** four identical outlines (finding 4) with a **T** on one. They move to
the T and score *correct*. That validates scoring, but nothing about whether the target can
be found from the display, which is the experiment.

Worse, §3.9 says `Screen` carries "every window the trial declares" and §4.4 draws "each
window: a dashed circle, labeled with its name". The one definition of those windows,
`task.expand_windows`, emits `search.target` **and** `search.distractor` both at the
target's position — the distractor alias's `at` is "nominal; membership is the union of the
others" (`task.py:851-858`). Drawn literally, the target carries a dashed circle labeled
`search.distractor`.

**Severity:** misleading.

**Smallest change.** §4.4 `Array` row: "items are drawn from the concrete windows
`<of>.0…n−1`; the aliases are drawn as labels on their members (the target 'T / target', the
others 'distractor'), never at the alias's own nominal position. While the target's and the
distractors' appearances are unset, the drawing says 'target and distractors drawn alike:
T is the scoring key, not what the animal sees'." Add the alias case to §9's screen tests.

---

## 6. The drawn eye dot is the pointer, not the gaze the trial scored

**Scenario A (recenter).** §3.3: "Recentering (C) works as it will on a rig: it adds an
offset." The person presses C with the pointer 1.5° right of center. From then on (map
versions are session-level) the rig scores pointer − 1.5°, while the page draws the dot
"where the pointer is" (§4.4). The person sees their dot squarely in the fixation window and
the trials end `no_fixation` / `fixation_break`: **a correct task looks broken**, every
trial, for the rest of the session. (Also: C has no meaning on the page today — `web.py`
binds only P and M, `web.py:2629-2635` — and nothing outside `calibration.py` calls
`MappingLog.recenter`. "Keep their meaning" is UNVERIFIED as built.)

**Scenario B (order and staleness).** `wlx serve`'s page server is a `ThreadingHTTPServer`
(`serve.py:879`), so two `POST /gaze` in flight can be pushed in either order; §3.8's message
has no sequence number, so "keeping the latest" keeps the latest *arrived*. And the source
re-issues the last report as a fresh sample every frame for `LIVE_S` = 0.5 s, so a page that
stalls (Safari throttling, focus loss, a GC pause) holds its last position for half a second
and that frozen position **counts toward holds**. §3.3's claim that "the 50 ms staleness rule
(`eye.Tracker.staleness`) … behave[s] as [it] will with an animal" is not true: in a demo the
rule fires only after leaving the screen, or 0.5 s + 50 ms after the last report. With an
animal a 60 ms gap is `tracker_lost` (default tolerance 0.05 s on all four tasks).

**Severity:** misleading.

**Smallest change.** Draw the eye dot where the rig **scored** gaze (the mapped, recentered,
latest-kept sample, sent back in telemetry); the OS cursor already shows the pointer. If
that is too much for this build: refuse C in a simulation ("the mouse is the gaze; there is
no calibration error to correct"), add a sequence number to §3.8's message, and replace
§3.3's sentence with "the staleness rule is exercised only by leaving the screen; a page
that stalls is held at its last position for `LIVE_S` and that time counts toward holds".

---

## 7. B shows a blink path the rig cannot produce until V3

**Scenario.** The person holds B during `hold_fix`. All four tasks declare `blink=0.0`, so the
trial ends `blink_break` (family *breaks*) on the first frame. They raise a task's blink
tolerance to 0.3 s, hold B, and watch the hold survive.

**What the animal gets:** `gaze.Tracked.signal` "Never `blink`" (`gaze.py:172-179`): until V3
a blink reaches the loop as tracker loss, which with the default 50 ms staleness plus 50 ms
`tracker_lost` grace ends the trial `tracker_lost` (family *rig*) about 0.1 s in, well
inside an ordinary blink. If instead OpenIris keeps sending structurally complete samples with
garbage corneal reflections during a blink, it is a `fixation_break` (which of the two:
UNVERIFIED, `eye.py:26-30`). Either way, never `blink_break`, and a blink tolerance set on
the demo's evidence protects nothing on the animal. (The spec also says the world *is*
`gaze.Tracked`; answering `blink` means overriding the rig's own `signal`.)

**Severity:** misleading.

**Smallest change.** Until V3, B answers `lost`, as the rig does. Key list: "B: a blink, as
the rig sees one today — tracker loss, under the task's `tracker_lost`." §9's test becomes
"B held is tracker lost".

---

## 8. The pointer cannot look off the screen, and cannot look at one place while touching another

**Scenario A.** The drawing's frame is the field's edge (§4.4) and a pointer off the drawing is
tracker loss (§3.3). A person in the right-column view reaches for the parameters panel
between trials, or tests "the animal isn't looking" by parking the pointer off the drawing.
Each trial then ends `tracker_lost` (family *rig*) within about 0.1 s of starting (a
fresh `Tracker` is "lost before the first sample" and an old sample is stale,
`eye.py:149-158`).

**What the animal gets:** a monkey looking away from the screen is still tracked; its gaze is a
position outside every window, so `await_fix` ends `no_fixation` after `fix_timeout` (4 s),
a *no engagement* outcome, and a look-away from a held window is `fixation_break`. The demo
fills the tally with rig failures where the animal would produce disengagement. (A fast flick
from inside a window straight off the drawing between two pointer reports does the same.)
§9's browser test "leave the screen, *tracker lost*" encodes the wrong mapping.

**Scenario B.** `Touched(window)` is the mouse button with the *same* pointer that is the eye
(§3.4). A task that requires fixating the center while touching a peripheral target cannot be
completed by hand; one whose gaze and touch criteria must coincide always passes.

**Severity:** misleading (A); limitation to state (B).

**Smallest change.** A: a pointer off the drawing (or over the page's other panes) is gaze off
the screen — a position outside every window — not tracker loss; tracker loss is B (finding 7)
or a page that stops reporting. §9: "leave the screen, *fixation break*"; "hold B, *tracker
lost*". B: one sentence in §3.4: "The mouse is both the eye and the hand: a task that needs
them in different places cannot be completed by hand, and one that needs them together
always is."

---

## 9. The pointer is far more accurate and steadier than a monkey's eye; windows and holds cannot be validated, and two §6 values are scientifically tight

**Scenario.** Any window. The mouse lands where it is put and holds to 0.02° white noise.

**What the animal gets.** Saccade endpoints scatter with an SD of roughly 5–10% of amplitude
(van Opstal & van Gisbergen, 1989, *Vision Res* 29:1183 — approximate), primary saccades
typically undershoot and are followed by a corrective saccade ~100–200 ms later (Becker,
1989, in Wurtz & Goldberg (eds), *Rev Oculomot Res* 3), and fixation drifts and makes
microsaccades of ~0.1–0.5° at ~1–2 Hz (Martinez-Conde, Macknik & Hubel, 2000, *Nat Neurosci*;
Hafed, Goffart & Krauzlis, 2009, *Science*). A window a mouse fills comfortably can be one a
monkey misses on a large fraction of correct responses. (Also: at 240 Hz the detector's
6-sample minimum is 25 ms, so on a synthetic 0.5° / 15 ms microsaccade it detects nothing;
the demo can never produce such an event to show this.)

**§6 values this bears on (for the PI's approval):**
- `visual_search` `item_window` **1.0°** — the declared ceiling — at **8°** eccentricity. With
  endpoint SD ~0.4–0.8° per axis there, a 1° radius loses a substantial share of correct
  target saccades to "landed in no window", which this task scores as nothing until a
  corrective saccade or `no_response`. The ceiling comes from the worst case (12 items on a
  5° ring, adjacent centers 2.59° apart, `visual_search.py:82-88`); at set size 4 on 8°,
  neighbors are 11.3° apart. Whether the range should follow set size and eccentricity is a
  task question to ask; the demo cannot inform it.
- `calibration` `cal_hold` **0.3 s** (copied from `fix_hold`). `Calibrating.observe` averages
  every sample of the hold (`gaze.py:257-274`; `Collector.accept` takes a plain mean), and
  the hold starts at `Entered("cal")` of a 4° window — i.e., at the primary saccade's
  hypometric landing. A corrective saccade 100–200 ms later falls inside the averaged 0.3 s,
  biasing each calibration point toward the undershoot. ≥0.5 s dilutes this; the real fix
  (average only the hold's settled tail) is the calibration driver's, for the backlog. A
  mouse lands with no corrective saccade and the demo's identity map is never refit
  (finding 3), so the demo can show neither.
- `cal_window` 4.0° and the shared timings are reasonable bootstrap values.

**Severity:** limitation to state (plus a starting-value concern).

**Smallest change.** §3.3: "The pointer lands exactly where it is put and holds to 0.02°. A
monkey's saccades scatter by roughly 5–10% of their amplitude, undershoot and correct, and
its fixation drifts and makes microsaccades: a window the mouse fills comfortably can be too
small for an animal, and demo mode says nothing about window sizes or hold durations." §6:
note the two values above for the PI's decision rather than presenting them as copied and
uncontroversial.

---

## 10. A hand needs about a second for what a monkey does in a quarter, so the demo cannot judge any time window

**Arithmetic on synthetic traces** (`saccade.Detector` as shipped, 0.02° tremor, pointer
reported at 60 Hz and held at 240 Hz; not a measurement of this system):
- tremor alone sets the elliptic threshold at ~6.5°/s; a still pointer yields no saccade;
- a 10° minimum-jerk pointer movement of 400 ms is confirmed ~90 ms after it starts and
  **lands ~360 ms after it starts**; one of 700 ms lands ~560 ms after it starts, 0.7° short
  of where it stops (the run closes in the hand's slow homing phase);
- a 10° / 40 ms eye saccade, sampled every frame, is confirmed 29 ms and lands ~54 ms after
  onset.

Add a human visual reaction time of ~0.2–0.3 s before the hand moves (and an unmeasured page
transport delay before the person even sees the target), and a brisk 400 ms movement uses
the whole of `fixation_detection`'s 0.6 s `response_window`; anything slower ends
`no_response`. Human mouse pointing at this difficulty takes a few hundred ms (Fitts' law;
MacKenzie, 1992, *Human–Computer Interaction* 7:91 — approximate). A monkey's visually guided
saccade latency is ~0.15–0.25 s (express ~0.08–0.1 s; Fischer & Boch, 1983, *Brain Res*), so
0.6 s is reasonable for the animal.

**The misleading part** is the asymmetry: a `response_window` too short for the monkey
(say 0.2 s) fails in the demo in exactly the way 0.6 s does, so the person attributes it to
"a mouse is slower", raises it, passes, and the error ships. And any time window too *long*
is invisible. §3.5's pacing also stretches every declared interval in wall time by each late
frame (the schedule moves on; the trial clock is frames), so demo windows are never shorter
than declared and sometimes longer.

**Severity:** limitation to state.

**Smallest change.** Replace §3.3's "may need more time" with: "From target onset to a
detected landing a hand takes roughly 0.6–1 s and a monkey's eye about 0.25 s. Demo mode
cannot tell whether a task's time windows suit an animal: one too short for the monkey fails
exactly as one too short for a hand does. Drive a task with `--set response_window=1.5` and
judge every time window from the task, not from the demo." Put that `--set` in §10's PI
try-out command.

---

## 11. In the stereoscope both eyes are the pointer, and the drawing shows no eye and no disparity

**Scenario.** A dichoptic or disparity task under `wlx demo --view stereoscope` (none of the
four reference tasks; all declare `view="direct"`). The pointer is "the same position for
both eyes" (§3.3) and §4.4's table has no row for `Stimulus.eye` or `Stimulus.disparity`.

- A left-eye-only stimulus scored by a conjugate (`eye="both"`) window passes `wlx check`
  (`_eye_faults` skips any window whose eye is `both`, `check.py:1002`) and passes the demo
  perfectly. On the animal, "the non-viewing eye drifts, and scoring it against a conjugate
  estimate scores an average of one eye doing the task and one eye doing nothing" — the
  hazard `Window.eye`'s own docstring names (`task.py:235-240`).
- Per-eye windows placed at a disparate stimulus's cyclopean position are tested at zero
  vergence; a fusing animal's two eyes sit ± half the disparity away.
- Two dichoptic stimuli at one location superimpose in the drawing; a task that sends both to
  the same eye, or uses the wrong disparity sign, draws identically to the correct one.

**Severity:** misleading (for any stereoscope task).

**Smallest change.** §4.4: label each stimulus with its eye when it is not `both` ("L"/"R")
and its disparity when nonzero (with the sign convention spelled out). §3.3: "Both eyes are
the pointer: vergence is always zero and a non-viewing eye never drifts. Per-eye windows on
disparate stimuli, and conjugate windows on monocular ones, behave in a demo as they never
will on the animal."

---

## 12. The drawing can drop brief stimuli, and nothing pins its "up" to the animal's

**Brief stimuli.** §3.9 publishes whole screens, latest-wins, and `serve.Hub.take` returns
"the newest item waiting" and skips older ones (`serve.py:296-310`). A cue flashed for
50–100 ms (memory-guided saccade with a `REMEMBERED` window, a gap or flash paradigm) can be
published and superseded before the page renders it: the person never sees the cue and
concludes the task never shows it — **a correct task looks broken** — and no duration, SOA or
gap can be judged by eye from the drawing at all. If `screen` events share a subscriber queue
with telemetry, `take` would also drop a `Screen` that a telemetry frame follows (UNVERIFIED:
unbuilt). None of the four reference tasks hides anything, so they are unaffected.

**Orientation.** Task degrees are y-up (`Array.phase` is counter-clockwise from +x); SVG is
y-down. Because the page converts the pointer through the SVG's own transform (§4.4), a
flipped drawing scores consistently and passes every scripted-pointer test; only a person
looking would notice, and a person who does not already know where the target belongs would
not.

**Severity:** misleading (brief-presentation tasks); minor (orientation).

**Smallest change.** §4.4: "The drawing is latest-wins: a stimulus up for less than a page
update may never be drawn, and no duration, SOA or gap can be judged from it." Keep `Screen`
out of telemetry's latest-wins queue. Add "+y is up on the drawing" to §4.4 and a §9 test that
a stimulus at +y is drawn above the fixation point.

---

### Claims in the spec that the demo will not bear out (cross-reference)

| Spec says | Finding |
|---|---|
| §1 a person confirms "a task Claude wrote does what was asked" | 2, 3, 4, 10, 11 |
| §3.3 the 50 ms staleness rule and saccades "behave as they will with an animal" | 6, 9, 10 |
| §3.3 recentering "works as it will on a rig" | 6 |
| §3.3 B makes "the loop's blink path be seen" | 7 |
| §6 contrast "starts easy and comes down" | 2 |
| §6 appearances draw as outlines "until a run sets them" | 4 |
| §10 "`wlx demo visual_search` in Safari" | 1 |
