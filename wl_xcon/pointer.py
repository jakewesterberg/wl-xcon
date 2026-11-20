"""Demo mode's eye: the mouse, through the rig's own gaze path (demo mode design §3.3-§3.5).

**Why it exists.** Demo mode lets a person play a task with the mouse as the eye, scored by the
rig's own eye rules (XC-013). A demo session's world is **`Pointing`, `gaze.Tracked` built as
`simeye.Seeing` is**: the rig's map, staleness, saccade detector and saccade rules, unchanged, with a
fresh `Tracker` and `Detector` each trial; it answers the guards no gaze world answers (keys, touch,
`Onscreen`; §3.4) and paces each frame to the wall clock (§3.5). Its sample source, **`Source`**,
gives one `eye.Sample` a frame from the newest pointer report the page sent, both eyes the pointer,
read through the simulated eye's identity map under its own `why` (`MAPPING`). The map never
changes in a demo: no recentering (§14 item 5).

**A report** (`MESSAGE`, fixed-size binary, §3.8): `wlx serve`'s forwarding count (demo mode's
Task 8), the pointer's x and y in degrees (+y up), whether it is over the drawing (`OVER`), B held
(`B_HELD`), the mouse button down (`BUTTON`), the number keys held (bit `k - 1` for key `k`), and
each key's running press count modulo 65536. **Presses are counted, not sampled**, so a press and
release between two frames is seen once.

**Signal states** (§3.3, §14 items 6 and 7):

- **The newest report wins, in sequence order**: a frame reads at most `DRAIN` reports (bounded
  work, whatever arrives) and keeps the one of highest sequence; one older than it, or than the
  report in hand while that is current, is counted `stale`, and one of the wrong size or not finite
  is counted `malformed` and dropped, as a malformed mark is. **The rig's gaze socket keeps only
  the newest report waiting** (`link.ZmqLink`, ZeroMQ's conflation; the whole-build review's M1),
  so a drain reads one, or the few that arrived while it read; those the socket dropped for a
  newer are never read, so never counted. (The newest can wait for the page's next report:
  `link.ZmqGaze`.) What `stale` counts is a report out of order: one read
  beside a newer, or numbered below the one in hand, as after `wlx serve` restarted, counting from
  1 again.
- **A report is current for `LIVE_S`**: through a page's stall the last position is held, with
  fresh noise each frame, and counts toward holds; past it the source gives nothing, the tracker
  goes stale (`eye.Tracker.staleness`) and the loop sees tracker loss under the task's
  `tracker_lost`. **B held is tracker loss too**, never a blink (`gaze.Tracked.signal` never
  answers `blink` until V3).
- **Off the drawing is gaze off the screen**: `AWAY_DEG`, outside every window a rig shows, as an
  animal looking away, so no fixation or a fixation break, never tracker loss.
- **A report's move spans the frames it took** (§14 item 9): the position is eased from where it
  was to where the report puts it on the minimum-jerk profile the simulated eye flies
  (`10τ³ - 15τ⁴ + 6τ⁵`), over as many frames as passed since the previous report arrived and
  `EASE_SLACK_S` more, at most `LIVE_S`, the arrival frame its first (planner's call; the slack
  since the whole-build review's I2). So a hand's path reaches the detector as motion, a glide
  whose reports come a little irregularly is one saccade, and a one-report flick is still a
  saccade; reports one a frame are taken exactly, with no slack, **but only in a stream**: every
  report since the eye was found the frame after the one before. A report a frame after one that
  came after a gap -- a flick's, the frame after a still pointer's (the 100 ms report), as a hand
  that moves just after one is reported -- is eased with the slack too, since taken in its one
  frame it is a jump the detector never confirms, a look that lands nowhere (2026-11-19, the
  pop-out played with the mouse ending astray). A first report, and the first
  after the one in hand went stale (`LIVE_S`), is taken at once, where the pointer is, as a
  tracker finds the eye again: between trials, and mid-trial too, where a page's stall past
  `LIVE_S` that ends inside the task's `tracker_lost` grace moves the eye at once to where it
  points, a jump, not a saccade.
- **At a trial's first frame** everything waiting but the newest report is discarded and the key
  counts are rebased, so a press in the gap between trials never fires the next trial's `Pressed`
  (`new_trial`).

**The keys** (§3.4): `inputs` numbers each input a task's states name, 1 to `KEYS`, in the order
they first name them; a task naming more is refused (`TooManyInputs`), naming those past it.
`Pressed` and `Response` fire on a key's down edge, `Released` on its up edge, `FeatureAbove` holds
while its key is held and `ChairStill` while its key is not, `Touched(window)` while the mouse
button is down with the pointer in the window (the mouse is both the eye and the hand), and
`Onscreen` on the first frame after the display changed, as a light sensor would see it.

**Real time** (§3.5): `Pace` waits each frame until its moment on `time.perf_counter`, in
`Pointing.display`, where a rig's display blocks on its flip; a frame already late runs at once and
moves the schedule on, never a catch-up burst. **No timing claim follows from it** (CLAUDE.md): the
pacing makes a demo watchable and measures nothing.

**The screen, to the page** (§3.9): `Drawing` resolves what a frame shows (`screen.resolve`, with
the session's calibration, so a color set's light is its realized one) into a `link.Drawn`, whole:
the screen, the trial's windows as `gaze.Tracked` judges them on that frame (an array's object
windows where the trial placed them, its target's flagged), each stimulus it could not resolve
outlined saying why, the setup's viewports, housings and field edge, and the keys. `Pointing`
publishes one on the trial's first frame, on the first frame after its screen changed, and at least
every `REDRAWN_EVERY_S`; and a blank one when the trial has ended (`Pointing.ended`, which the
session calls at the boundary). A drawing and its publisher are given together or not at all.
**A demo run's trial waits for its page's pointer** (`Worlds.waiting`; demo mode's Task 10, and
since the whole-build review's I3 every trial, not only the first): while no page steers -- before
the first report, and once the reports stop (Escape, a tab closed, or a tab hidden, which the
page lets go of as Escape does) -- the trial loop
holds at the boundary before the next trial, the field published blank (`Drawing.field`), since
before the first screen a page has nothing to point at, and an eye nobody steers is tracker loss.

**Numbers fixed here, each with its reason** (the demo plan's Global Constraints; the PI's
"everything adjustable in the console", 2026-11-07, is about a task's numbers, which stay settings):
`KEYS` and `DRAIN`, bounded work a frame (§3.4, §3.8); `LIVE_S`, five of the page's slowest report
intervals (`web.GAZE_EVERY_MS`, 100 ms, demo mode's Task 9), so a demo is playable, claiming
nothing (§3.3); `EASE_SLACK_S`, a report's usual lateness (the whole-build review's I2);
`AWAY_DEG`, beyond any field a rig shows; the noise, `simeye.NOISE_DEG`, imported, drawn from the
run's seed (§14 item 16); `REDRAWN_EVERY_S`, inside `wlx console`'s 5 s timeout and a page's
patience (§3.9); `OUTLINE_DEG`, a mark claiming no size. **Planner's calls**: the ease's
span; the agreement test.

**Hot path.** `Pointing.display` and `happened` run every frame, and so do the source's `poll` and
`Pace.wait`: a report is read into a buffer allocated once and read through views made with it,
key state is kept in integers, and a frame builds only its sample (its reading's image position,
the pair `(x, y)`; `tests/test_pointer.py` measures the whole frame, as `tests/test_simeye.py`
does). Only a frame whose display changed copies what it shows (`Pointing._shown_now`), and only a
frame that publishes builds its `Drawn` (`Pointing._publish`): a demo has no frame budget to protect
(§3.9), and no rig world changes.
"""

from __future__ import annotations

import dataclasses
import math
import random
import struct
import sys
import time
from typing import Callable

from wl_xcon import screen, simeye, viewport
from wl_xcon.eye import EyeReading, Sample, Tracker
from wl_xcon.gaze import Tracked
from wl_xcon.link import SCHEMA, Drawn, DrawnOutline, DrawnWindow
from wl_xcon.look import GABOR_CUTOFF_SIGMAS
from wl_xcon.task import (
    After,
    Array,
    ChairStill,
    FeatureAbove,
    Gabor,
    Guard,
    Onscreen,
    P,
    Pressed,
    Released,
    Response,
    Touched,
    Trial,
    Window,
    _value,
    position_of,
)

#: **A pointer report** (the module docstring): the sequence number, x and y in degrees, the flags,
#: the keys held, and each of the `KEYS` keys' running press count modulo 65536. 41 bytes,
#: little-endian, packed.
MESSAGE = struct.Struct("<IddBH9H")
#: The flags: over the drawing, B held, the mouse button down.
OVER = 1
B_HELD = 2
BUTTON = 4
#: How many number keys a demo gives a task's inputs, 1 to 9 (§3.4): bounded work a frame.
KEYS = 9
#: How many reports a frame reads at most, keeping the newest (§3.8): bounded work a frame, whatever
#: a link gives. The rig's own socket keeps only the newest waiting (`link.ZmqLink`), so a frame
#: there reads one or two.
DRAIN = 64
#: How long a report stays current, in seconds: five of the page's slowest report intervals
#: (§3.3), so a page's stall is held and counts toward holds, and a page gone quiet is tracker
#: loss. Playable, and claiming nothing.
LIVE_S = 0.5
#: **How much longer than the gap since the report before a report's move is eased**, in seconds
#: (the whole-build review's I2, 2026-11-16, closing XC-508): a report's usual lateness. The page
#: reports once an animation frame while the pointer moves, 16.7 ms apart at 60 Hz, and each
#: arrives some milliseconds earlier or later than the last did (a busy browser, the network;
#: assumed, not measured), so a move eased over only the gap before it could land and stop before
#: the next report, and a glide reached the detector as two saccades. 25 ms, a frame and a half at
#: 60 Hz, is what the review's probe found keeping 400 ms and 600 ms glides one saccade at 2-12 ms
#: round trips, as `tests/test_pointer.py`'s glide test holds; only a report continuing a stream
#: of one a frame goes without it (`Source._adopt`; since 2026-11-19, before which a report a
#: frame after any other did). Playable, and claiming nothing. **What it costs** (the build's
#: re-review, N4; from `tools/measure_demo_ease_slack.py`, on an injected clock with assumed report
#: timings, `docs/measurements/dev-machine/2026-11-16-demo-ease-slack.md`; not timing claims about
#: a rig): the eye trails the hand by about 21 ms more, so a hand that leaves less than about that
#: before the go reads as leaving after it; a stop of 50 ms or less between two moves can merge
#: them into one saccade (5 of 10 at 0-17 ms, 1 of 10 at 33-50 ms); a 600 ms glide meets the
#: pop-out's own 0.3 s landing bound 5 or 6 times in 100, not 2; and 1 in 100 jittered 600 ms
#: glides still splits into two looks.
EASE_SLACK_S = 0.025
#: **Where the pointer off the drawing looks**, in degrees: straight up, beyond any field a rig
#: shows, so outside every window, as an animal looking away.
AWAY_DEG = (0.0, 60.0)
#: **How often a demo's world publishes its screen with nothing changed**, in seconds of the
#: trial's clock, which `Pace` holds to the wall's (§3.9): at least once a second, so `wlx
#: console`'s 5 s receive timeout never ends a watch of a demo that is only drawing, and a page
#: that attaches mid-trial has the screen within a second.
REDRAWN_EVERY_S = 1.0
#: **How wide a stimulus is outlined whose own size cannot be read** (a look with no value), in
#: degrees: a mark to find it by, claiming no size (§4.4).
OUTLINE_DEG = 1.0

#: **The map a demo's samples are read through**: the simulated eye's identity, under its own
#: `why`. It never changes in a demo (no recentering, §14 item 5).
MAPPING = dataclasses.replace(simeye.MAPPING, why="the mouse, in degrees")

#: Where each field of a report lies in its 41 bytes (`MESSAGE`).
_SEQ = slice(0, 4)
_XY = slice(4, 20)
_FLAGS = 20
_HELD = slice(21, 23)
_PRESSES = slice(23, 41)
#: The whole report, for copying one buffer into another without building a slice in a frame.
_WHOLE = slice(0, MESSAGE.size)
#: A press count's modulus, as `& _COUNT` takes it.
_COUNT = 0xFFFF
#: Where the pointer is off the drawing, per axis (`AWAY_DEG`), read without a tuple in a frame.
_AWAY_X, _AWAY_Y = AWAY_DEG
#: What a demo's reading carries that no gaze reads: its pupil, and P4 at the origin (`simeye`'s).
_PUPIL = (0.0, 0.0)
_PUPIL_AREA = 1.0
_P4 = (0.0, 0.0)


def pack(seq: int, x_deg: float, y_deg: float, *, over: bool, b: bool, button: bool,
         held: int, presses) -> bytes:
    """**A report as the page's sender packs it** (`MESSAGE`): `held` the keys held, bit `k - 1`
    for key `k`; `presses` each of the `KEYS` keys' running press count, kept modulo 65536."""
    if len(presses) != KEYS:
        raise ValueError(f"a report carries {KEYS} keys' press counts, not {len(presses)}")
    flags = (OVER if over else 0) | (B_HELD if b else 0) | (BUTTON if button else 0)
    return MESSAGE.pack(seq, x_deg, y_deg, flags, held, *(count & _COUNT for count in presses))


class _Fields:
    """**A report's fields, read in place**: views of one buffer, made once, so a frame reads a
    report's numbers without unpacking it into a tuple. Native order, which is the report's
    little-endian order on the computers `Source` runs on (it refuses any other)."""

    def __init__(self, buffer: bytearray) -> None:
        whole = memoryview(buffer)
        self.seq = whole[_SEQ].cast("I")
        self.xy = whole[_XY].cast("d")
        self.raw = whole
        self.held = whole[_HELD].cast("H")
        self.presses = whole[_PRESSES].cast("H")


class Source:
    """**The pointer as a gaze source** (the module docstring): `poll(at)` once a frame, as
    `gaze.Tracked.display` polls a tracker, gives the frame's sample or `None`, and keeps the
    frame's key edges. `receive(buffer)` reads one waiting report into the buffer and returns its
    size, or -1 with none waiting, never blocking. One for a demo session, not a trial: its noise
    generator carries the run's randomness (seeded from the run's seed, §14 item 16), and it holds
    the newest report across trials."""

    def __init__(self, receive: Callable[[bytearray], int], *, seed: int,
                 noise_deg: float = simeye.NOISE_DEG) -> None:
        if sys.byteorder != "little":
            raise RuntimeError(
                "a pointer report is read in place as little-endian numbers, and this computer "
                "stores numbers big-end first: demo mode does not run on it")
        self.receive = receive
        self.seed = seed
        self.noise_deg = noise_deg
        self._noise = random.Random(f"{seed}: the mouse's noise")
        #: Reports read and dropped: older than the newest in hand, or malformed.
        self.stale = 0
        self.malformed = 0
        #: Whether the mouse button is down, by the report in hand.
        self.button = False
        #: What `receive` reads into, and the newest report a drain has kept, each read in place.
        self._buffer = bytearray(MESSAGE.size)
        self._best = bytearray(MESSAGE.size)
        self._in = _Fields(self._buffer)
        self._kept = _Fields(self._best)
        #: A newer report kept and not yet taken (`_adopt`), and its sequence number.
        self._pending = False
        self._best_seq = -1
        #: **The report in hand**: whether there is one, its sequence number, its flags, and when
        #: it arrived, on the source's own clock (`poll`).
        self._current = False
        self._seq = -1
        self._flags = 0
        self._arrived = 0.0
        #: **The source's own clock**: `at` plus an offset, so it runs on across trials, whose
        #: worlds count `at` from each trial's start; the last poll's time, and the step between
        #: polls, one frame.
        self._offset = 0.0
        self._last = 0.0
        self._step = 0.0
        self._polled = False
        #: **Where the pointer is drawn, in degrees**: eased from `_from` to `_to` over `_span`
        #: seconds from `_start`, landed when `_landed`.
        self._x = self._y = 0.0
        self._from_x = self._from_y = self._to_x = self._to_y = 0.0
        self._start = 0.0
        self._span = 0.0
        self._landed = True
        #: **Whether the reports are a stream of one a frame** (`_adopt`): every one since the eye
        #: was found (a report taken at once) the frame after the one before.
        self._streaming = False
        #: **The keys**: the held mask and the press counts in hand and as the previous frame had
        #: them, and the frame's edges, bit `k - 1` for key `k`.
        self._held_now = 0
        self._held_was = 0
        self._counts_now = [0] * KEYS
        self._counts_was = [0] * KEYS
        self._down = 0
        self._up = 0
        #: The next poll is a trial's first frame (`new_trial`); a new source's first poll is one.
        self._rebase = True
        self._samples = 0

    # --- Between trials ---------------------------------------------------------------------

    def new_trial(self) -> None:
        """**Ready for a trial's first frame** (§3.3): everything waiting is read, the newest kept
        to be taken on that frame and the rest counted stale; and that frame rebases the key counts,
        so a press in the gap between trials never fires the trial's `Pressed`. Between trials, so
        the drain is not bounded by `DRAIN`: what waits is what the socket holds."""
        floor = self._seq if self._live(self._last) else -1
        while self._drain(floor) == DRAIN:
            pass
        self._rebase = True

    def steered(self) -> bool:
        """**Whether a page steers the eye now**: everything waiting read, as between trials
        (`new_trial`), the newest kept for the next trial's first frame; true while one is kept,
        or while the report in hand is current (`LIVE_S`) on the source's own clock, which stands
        at the last trial's last frame between trials; a malformed one never counts. So false
        before any report, and once a trial has outlived the last one. Between trials only, never
        in a frame: each trial waits on it (`Worlds.waiting`; demo mode's Task 10, and the
        whole-build review's I3)."""
        floor = self._seq if self._live(self._last) else -1
        while self._drain(floor) == DRAIN:
            pass
        return self._pending or self._live(self._last)

    # --- Each frame ---------------------------------------------------------------------------

    def poll(self, at: float) -> "Sample | None":
        """**The frame's sample**, `at` its time on the trial's clock: the reports waiting read
        (`_drain`) and the newest taken (`_adopt`); the frame's key edges (`_edges`); then `None`
        while no report is current or B is held (tracker loss), `AWAY_DEG` off the drawing, else
        where the pointer is drawn (`_ease`), with noise of `noise_deg` per axis, the same reading
        for both eyes. Its image position is the one thing a frame builds."""
        rebase = self._rebase
        if rebase:
            # A trial's first frame: its worlds count `at` from its start, and the source's clock
            # runs on, a frame after the last.
            self._offset = self._last + self._step - at
        now = at + self._offset
        if self._polled and not rebase:
            self._step = now - self._last
        self._last = now
        self._polled = True
        self._drain(self._seq if self._live(now) else -1)
        if self._pending:
            self._adopt(now)
        self._edges(rebase)
        self._rebase = False
        if not self._live(now) or self._flags & B_HELD:
            return None
        if self._flags & OVER:
            self._ease(now)
            x = self._x
            y = self._y
        else:
            x = _AWAY_X
            y = _AWAY_Y
        noise = self._noise
        self._samples += 1
        reading = EyeReading(self._samples, _PUPIL, _PUPIL_AREA,
                             (x + noise.gauss(0.0, self.noise_deg),
                              y + noise.gauss(0.0, self.noise_deg)), _P4)
        return Sample(at, reading, reading)

    def held(self, key: int) -> bool:
        """Whether number key `key` (1 to `KEYS`) is held, by the report in hand."""
        return (self._held_now >> (key - 1)) & 1 == 1

    def went_down(self, key: int) -> bool:
        """Whether key `key` went down since the previous frame: a press counted, or held now and
        not then."""
        return (self._down >> (key - 1)) & 1 == 1

    def went_up(self, key: int) -> bool:
        """Whether key `key` came up since the previous frame: a release, counted as the presses
        less the change in whether it is held, or held then and not now."""
        return (self._up >> (key - 1)) & 1 == 1

    def _live(self, now: float) -> bool:
        """Whether a report is in hand and current at `now`, on the source's clock: arrived less
        than `LIVE_S` ago."""
        return self._current and now - self._arrived < LIVE_S

    def _drain(self, floor: int) -> int:
        """**Read what waits, at most `DRAIN` reports**, keeping the one of highest sequence above
        `floor` (the report in hand's while it is current, so an older one is stale) in `_best`,
        `_pending` then true. One older than the one kept is counted `stale`, and so is the one it
        replaces; one of the wrong size or not finite is counted `malformed` and dropped. How many
        it read."""
        receive = self.receive
        buffer = self._buffer
        fields = self._in
        kept = self._pending
        best = self._best_seq if kept else floor
        count = 0
        while count < DRAIN:
            size = receive(buffer)
            if size < 0:
                break
            count += 1
            if size != MESSAGE.size:
                self.malformed += 1
                continue
            xy = fields.xy
            if not (math.isfinite(xy[0]) and math.isfinite(xy[1])):
                self.malformed += 1
                continue
            seq = fields.seq[0]
            if seq <= best:
                self.stale += 1
                continue
            if kept:
                self.stale += 1
            self._best[_WHOLE] = buffer
            best = seq
            kept = True
        self._pending = kept
        self._best_seq = best
        return count

    def _adopt(self, now: float) -> None:
        """**The kept report becomes the one in hand**, arriving `now`. Over the drawing, the
        pointer is eased from where it is drawn now to the report's position, over the time since
        the previous report arrived, and `EASE_SLACK_S` more unless the report continues a stream
        of one a frame (`_streaming`), at most `LIVE_S`, starting a frame before `now` so that the
        arrival frame is the move's first (the module docstring); a first report is taken at once,
        as is the first after the one in hand went stale, and one where the pointer already goes
        leaves the move in flight as it was. Off the drawing, it is at `AWAY_DEG` at once. Its keys
        and button are taken as they are; the edges are `_edges`'."""
        fields = self._kept
        x = fields.xy[0]
        y = fields.xy[1]
        flags = fields.raw[_FLAGS]
        live = self._live(now)
        gap = now - self._arrived
        # **A stream of one a frame** goes on while each report comes the frame after the one
        # before (half a frame's margin for the clock's rounding), and begins where the eye is
        # found, a report taken at once; a report after a gap ends it, whatever it carries.
        streaming = (self._streaming and gap <= 1.5 * self._step) if live else True
        if not flags & OVER:
            self._x = self._to_x = _AWAY_X
            self._y = self._to_y = _AWAY_Y
            self._landed = True
        elif not live:
            # **A first report, or the first after the one in hand went stale** (`LIVE_S`): taken
            # at once, as a tracker finds the eye again where it is, never eased from where it
            # was lost. Between trials, once a page lets go and points again, the next trial's eye
            # starts where it now points (the whole-build review's I3); **mid-trial too**: after a
            # page's stall past `LIVE_S` that ends inside the task's `tracker_lost` grace, the eye
            # is where the page points at once, a jump the detector reads as no saccade (its
            # re-review, N3), as a rig's tracker regaining the eye.
            self._x = self._to_x = x
            self._y = self._to_y = y
            self._landed = True
        elif x == self._to_x and y == self._to_y:
            # **A report where the pointer already goes, a still pointer's**: the move in flight
            # goes on as it was. Restarted from rest, it would stop and start again, which the
            # detector reads as a second saccade; with the slack below, a still pointer's next
            # report often comes before its move has landed (the whole-build review's I2).
            pass
        else:
            self._ease(now)
            span = gap
            if not streaming:
                # **A report after a gap, eased over it and `EASE_SLACK_S` more**: one
                # a little later than that gap finds the pointer still moving, not stopped at the
                # last report, so a glide is one saccade. **And one the frame after a report that
                # ended a gap**: a flick's the frame after a still pointer's, as a hand that moves
                # just after the page's 100 ms report sends it. Taken in its one frame it is a jump
                # the detector never confirms, under its six samples outside the threshold, a look
                # landing nowhere (2026-11-19: the pop-out played with the mouse ended astray, the
                # eye in the target's window). Only a report continuing a stream of one a frame has
                # no gap to bridge, and is taken exactly, as before.
                span += EASE_SLACK_S
            if span > LIVE_S:
                span = LIVE_S
            self._from_x = self._x
            self._from_y = self._y
            self._to_x = x
            self._to_y = y
            self._span = span
            self._start = now - self._step
            self._landed = False
        self._streaming = streaming
        self._seq = self._best_seq
        self._flags = flags
        self._arrived = now
        self._current = True
        self._pending = False
        self.button = flags & BUTTON != 0
        self._held_now = fields.held[0]
        presses = fields.presses
        counts = self._counts_now
        key = 0
        while key < KEYS:
            counts[key] = presses[key]
            key += 1

    def _ease(self, now: float) -> None:
        """**Where the pointer is drawn at `now`**, into `_x`, `_y`: `10τ³ - 15τ⁴ + 6τ⁵` of the
        way from `_from` to `_to`, `τ` the share of the span gone (`simeye.Eye._fly`'s profile);
        exactly `_to` once it is all gone."""
        if self._landed:
            return
        span = self._span
        tau = (now - self._start) / span if span > 0.0 else 1.0
        if tau >= 1.0:
            self._x = self._to_x
            self._y = self._to_y
            self._landed = True
            return
        if tau < 0.0:
            tau = 0.0
        share = tau * tau * tau * (10.0 - 15.0 * tau + 6.0 * tau * tau)
        self._x = self._from_x + (self._to_x - self._from_x) * share
        self._y = self._from_y + (self._to_y - self._from_y) * share

    def _edges(self, rebase: bool) -> None:
        """**The frame's key edges**, against the previous frame's counts and held mask: a key went
        down if a press was counted or it is held now and was not; it came up if a release was
        (the presses counted, less the change in whether it is held) or it was held and is not.
        **A trial's first frame rebases**: the counts in hand become the previous frame's, and no
        key has an edge on it."""
        now = self._counts_now
        was = self._counts_was
        held = self._held_now
        held_was = self._held_was
        down = 0
        up = 0
        key = 0
        while key < KEYS:
            if not rebase:
                bit = 1 << key
                pressed = (now[key] - was[key]) & _COUNT
                is_held = 1 if held & bit else 0
                was_held = 1 if held_was & bit else 0
                if pressed > 0 or (is_held and not was_held):
                    down |= bit
                if pressed - is_held + was_held > 0 or (was_held and not is_held):
                    up |= bit
            was[key] = now[key]
            key += 1
        self._held_was = held
        self._down = down
        self._up = up


@dataclasses.dataclass(frozen=True)
class Input:
    """**A number key and the input it stands for** (§3.4): `guard` the first guard a state names
    it by -- a `Pressed`, `Released` or `Response` device, a `FeatureAbove` source, or
    `ChairStill`."""

    key: int
    guard: Guard

    @property
    def label(self) -> str:
        """What the input is called on the key list and in a refusal: a device's name, a feature
        source's, or the chair."""
        guard = self.guard
        if isinstance(guard, FeatureAbove):
            return f"feature {guard.source}"
        if isinstance(guard, ChairStill):
            return "the chair"
        return guard.device


class TooManyInputs(ValueError):
    """**A task naming more inputs than a demo has keys** (§3.4, the demo's pre-flight): refused,
    naming those past `KEYS`, the one refusal of a task demo mode makes."""

    def __init__(self, named: "tuple[Input, ...]") -> None:
        self.inputs = named
        past = ", ".join(item.label for item in named[KEYS:])
        super().__init__(
            f"a demo gives each input a task waits on a number key, 1 to {KEYS}, and this task "
            f"names {len(named)}: {past} would have none, so it cannot be played by hand "
            f"(demo mode §3.4)")


def _identity(guard: Guard) -> "tuple | None":
    """The input `guard` names, as one key stands for it: a device, a feature source, or the
    chair; `None` for a guard that names none."""
    if isinstance(guard, (Pressed, Released, Response)):
        return ("device", guard.device)
    if isinstance(guard, FeatureAbove):
        return ("feature", guard.source)
    if isinstance(guard, ChairStill):
        return ("chair",)
    return None


def _named(trial: Trial):
    """Every guard `trial`'s states name, in order: each edge's, then the guard its clock is timed
    from (`After.since`)."""
    for state in trial.states:
        for edge in state.go:
            guard = edge.guard
            while guard is not None:
                yield guard
                guard = guard.since if isinstance(guard, After) else None


def inputs(trial: Trial) -> "tuple[Input, ...]":
    """**Each input `trial` waits on, numbered 1 to `KEYS`** in the order its states first name
    them (§3.4): one key a `Pressed`, `Released` or `Response` device, one a `FeatureAbove` source,
    one `ChairStill`. More than `KEYS` is refused (`TooManyInputs`), naming those past it."""
    found: list = []
    seen: set = set()
    for guard in _named(trial):
        identity = _identity(guard)
        if identity is None or identity in seen:
            continue
        seen.add(identity)
        found.append(Input(len(found) + 1, guard))
    if len(found) > KEYS:
        raise TooManyInputs(tuple(found))
    return tuple(found)


class Pace:
    """**A demo's frames on the wall clock** (§3.5): `start()` on a trial's first frame, then
    `wait(frame)` before each later one, sleeping until the frame's moment, `frame_period` apart.
    **A frame already late runs at once and moves the schedule on**: the frames after it are timed
    from it, never run back to back to catch up. Between trials it waits nothing. The clock and the
    sleep are given, so a test injects both and never sleeps."""

    def __init__(self, frame_period: float, *, clock: Callable[[], float] = time.perf_counter,
                 sleep: Callable[[float], None] = time.sleep) -> None:
        self.frame_period = frame_period
        self._clock = clock
        self._sleep = sleep
        #: The moment of frame `_first`, from which each later frame's is counted.
        self._zero = 0.0
        self._first = 1

    def start(self) -> None:
        """A trial's first frame: its moment is now."""
        self._zero = self._clock()
        self._first = 1

    def wait(self, frame: int) -> None:
        """Until frame `frame`'s moment; at once, the schedule moved on to now, if it has passed."""
        moment = self._zero + (frame - self._first) * self.frame_period
        now = self._clock()
        if now < moment:
            self._sleep(moment - now)
            return
        self._zero = now
        self._first = frame


def _paired(drawing, publish) -> None:
    """**A drawing and its publisher come together, or neither does**: a drawing with no publisher
    would be resolved for nobody, and a publisher with no drawing would never be called, a page
    left blank with nothing raising. Neither is an in-process world's, which shows nobody."""
    if (drawing is None) != (publish is None):
        raise ValueError(
            "a demo world draws its screen for the page and publishes it, or does neither: give a "
            "`Drawing` and a publisher together (demo mode §3.9)")


class Drawing:
    """**What a demo's world shows, as the page draws it** (§3.9, §4.4; the module docstring): for a
    session's rig, field and calibration, each `drawn` frame resolved into a `link.Drawn`. Built once
    for a session, between trials; `drawn` and `blank` run on a frame that publishes, which a demo
    may spend (§3.9)."""

    def __init__(self, rig, geometry, calibration, *, session_id: str, stand_in: bool) -> None:
        self.rig = rig
        self.geometry = geometry
        self.calibration = calibration
        self.session_id = session_id
        #: Whether the field's housings are the stand-ins (§3.6), which the page labels so.
        self.stand_in = stand_in
        #: The setup's viewports at the rig's own pixels: the page draws a preview of them.
        self.viewports = viewport.viewports(rig, geometry)

    def drawn(self, world, visible, values, trial: Trial, index: int, frame: int) -> Drawn:
        """**Frame `frame` of trial `index` as `world` shows it**: `visible` resolved through
        `screen.resolve` with the session's calibration, each stimulus it cannot resolve -- a kind
        the drawer does not draw yet (`screen.NotYetDrawable`), a look with no value -- outlined
        saying why and the rest resolved; the windows `world`'s own as `gaze.Tracked` judges them
        on this frame (`drawn_windows`); and the setup and the keys."""
        resolved, outlines = self._resolved(world, visible, values, trial, frame)
        return self._made(_labels(world), index, frame, resolved, drawn_windows(world), outlines)

    def blank(self, world, index: int, frame: int) -> Drawn:
        """**The screen after trial `index` has ended**: blank, as the animal's is until the next
        trial's first frame, with no windows; the setup and the keys as before."""
        return self._made(_labels(world), index, frame, None, (), ())

    def field(self, index: int) -> Drawn:
        """**The field before trial `index` has begun**, frame 0: blank, with no windows and no
        keys, since no trial is drawn yet. What a page points at while a run's first trial waits
        for its pointer (`Worlds.waiting`; demo mode's Task 10): before it nothing is drawn, and a
        page with no drawing has nowhere to put the eye."""
        return self._made((), index, 0, None, (), ())

    def _made(self, keys, index, frame, resolved, windows, outlines) -> Drawn:
        geometry = self.geometry
        return Drawn(
            schema=SCHEMA, phase="drawn", session_id=self.session_id, trial=index, frame=frame,
            screen=resolved, windows=windows, outlines=outlines, viewports=self.viewports,
            housings=tuple(geometry.housings), stand_in=self.stand_in, mask_deg=geometry.mask_deg,
            keys=keys, vergence_half_deg=geometry.vergence_half_deg,
        )

    def _resolved(self, world, visible, values, trial, frame):
        """The screen and the outlines: the whole of `visible` resolved at once, and only where
        that fails, each stimulus alone, so the one that cannot be drawn is outlined and the rest
        are resolved together, in the order shown."""
        onsets = world.onsets

        def resolve(shown):
            return screen.resolve(shown, values, trial, self.geometry,
                                  frame_period=world.frame_period, frame=frame, onsets=onsets,
                                  calibration=self.calibration)

        try:
            return resolve(visible), ()
        except (KeyError, ValueError):
            pass
        kept: dict = {}
        outlines: list = []
        for name, stimulus in visible.items():
            try:
                resolve({name: stimulus})
            except (KeyError, ValueError) as exc:
                outlines.extend(_outlined(stimulus, values, _why(exc)))
                continue
            kept[name] = stimulus
        return resolve(kept), tuple(outlines)


def _labels(world) -> tuple:
    """A world's inputs' labels, in the order of their keys, as a `Drawn` lists them."""
    return tuple(item.label for item in sorted(world.keys, key=lambda item: item.key))


def _why(exc: Exception) -> str:
    """Why a stimulus is outlined, in the drawing's words (§4.4): a kind not drawn yet names the
    build that draws it (`screen.NotYetDrawable`); a value it needs with none names the setting."""
    if isinstance(exc, screen.NotYetDrawable):
        return f"not drawn yet: {exc}"
    if isinstance(exc, KeyError):
        said = exc.args[0] if exc.args else exc
        return f"it has no value to be drawn with: {said}"
    return f"it cannot be drawn: {exc}"


def _outlined(stimulus, values, why: str) -> "list[DrawnOutline]":
    """**`stimulus` as outlines** where it is: one at its position the size its look says, or, for
    an array whose objects can be placed, one an object; at the center, saying so, when its own
    position has no value."""
    try:
        x, y = position_of(stimulus.at, values)
    except (KeyError, TypeError, ValueError):
        x, y = 0.0, 0.0
        why = f"{why}; and its position has no value, so it is outlined at the center"
    looks = stimulus.looks
    if isinstance(looks, P):
        looks = values.get(looks.name)
    if isinstance(looks, Array):
        try:
            centers = looks.positions(values, (x, y))
            return [DrawnOutline(f"{stimulus.name}.{i}", float(cx), float(cy),
                                 _extent(looks.object_looks(i, values), values), why)
                    for i, (cx, cy) in enumerate(centers)]
        except (KeyError, TypeError, ValueError):
            pass
    return [DrawnOutline(stimulus.name, float(x), float(y), _extent(looks, values), why)]


def _extent(looks, values) -> float:
    """**How wide a look is drawn, in degrees**: its size, aperture, outer diameter or length,
    whichever it has; a Gabor's cut-off, as `screen.as_look` draws it; `OUTLINE_DEG` where none can
    be read -- a look with no value, or one whose size has none."""
    if isinstance(looks, P):
        looks = values.get(looks.name)
    try:
        if isinstance(looks, Gabor):
            width = 2 * GABOR_CUTOFF_SIGMAS * float(_value(looks.sigma, values))
        else:
            shape = getattr(looks, "shape", looks)
            named = next((getattr(shape, name) for name in ("size", "aperture", "outer", "length",
                                                            "width")
                          if getattr(shape, name, None) is not None), None)
            width = OUTLINE_DEG if named is None else float(_value(named, values))
    except (KeyError, TypeError, ValueError):
        return OUTLINE_DEG
    return width if math.isfinite(width) and width > 0.0 else OUTLINE_DEG


def _targetless(drawn, options, values: dict) -> bool:
    """Whether an array family has no target on the screen (`drawn_windows`): the array its drawn
    stimulus shows is found by `"none"`, or, none drawn yet, every placement's is."""
    def none(looks) -> bool:
        looks = values.get(looks.name) if isinstance(looks, P) else looks
        return isinstance(looks, Array) and looks.found_by == "none"

    if drawn is not None:
        return none(drawn.looks)
    return bool(options) and all(none(placement.looks) for placement, _ in options)


def drawn_windows(world: Tracked) -> "tuple[DrawnWindow, ...]":
    """**`world`'s windows as it judges them now** (§3.9, §14 item 4): each declared window and
    array object window with the center and radius `gaze.Tracked.in_window` compares gaze with on
    this frame -- an array's object windows where the trial placed them, switched with the array in
    `Tracked.display` -- and the eye it is judged for; an array alias's own stand-in left out, never
    drawn at the alias's nominal place, and an array's target's objects flagged, the scoring key.
    **But an array's with no target** (`Array.found_by` `"none"`, a catch; the pop-out revision's
    Task 4): its declared place is where an odd one would be, which nothing is, so no object of it
    is labeled *target* -- while it is drawn so, or, before it is drawn, where each way the trial
    can draw it is. A window the trial's values cannot place is drawn nowhere: the loop raises if
    a guard asks."""
    aliases = world._members
    targetless = {f"{of}.target" for of, options in world._arrays
                  if _targetless(world._drawn.get(of), options, world._values)}
    targets = {name for alias, names in aliases.items()
               if alias.endswith(".target") and alias not in targetless for name in names}
    found = []
    for name, declared in world._windows.items():
        if declared is None or name in aliases:
            continue
        judged = world._judged.get(name)
        if isinstance(judged, Window):
            try:
                cx, cy = position_of(judged.at, world._values)
                judged = (cx, cy, _value(judged.radius, world._values))
            except Exception:  # noqa: BLE001 -- unplaceable, as `gaze._judged` defers it
                continue
        if judged is None:
            continue
        cx, cy, radius = judged
        found.append(DrawnWindow(name, float(cx), float(cy), float(radius), declared.eye,
                                 name in targets))
    return tuple(found)


class Pointing(Tracked):
    """**`gaze.Tracked`, the rig's gaze world, whose tracker is the mouse** (`Source`; the module
    docstring): every gaze guard, map, staleness and saccade rule is `Tracked`'s, with a fresh
    `Tracker` and `Detector`, and it answers the guards no gaze world answers from the keys, the
    button and the display (`happened`). `keys` numbers the trial's inputs (`inputs`), and must
    number each one it names. `index` is the trial's in the run. **Given a `drawing` and
    `publish`, it publishes its screen** (the module docstring): on the trial's first frame, on the
    first frame after the screen changed, at least every `REDRAWN_EVERY_S`, and blank once the trial
    has ended (`ended`); the two come together or not at all."""

    def __init__(self, source: Source, trial: Trial, frame_period: float,
                 values: "dict | None", *, pace: Pace, keys: "tuple[Input, ...]", index: int = 0,
                 drawing: "Drawing | None" = None, publish=None) -> None:
        _paired(drawing, publish)
        Tracked.__init__(self, Tracker(), MAPPING, trial, frame_period, values, source=source)
        self.pace = pace
        self.keys = keys
        self.index = index
        self.trial = trial
        self.drawing = drawing
        self.publish = publish
        #: **When the screen is next published with nothing changed**: the first frame at least
        #: `REDRAWN_EVERY_S` after the last one published, as a frame number, so a frame compares
        #: two integers; 0 before the first, which every trial's first frame is past.
        self._redraw_every = max(1, math.ceil(REDRAWN_EVERY_S / frame_period - 1e-9))
        self._redraw_at = 0
        #: The last frame displayed, which a blank screen at the trial's end is numbered by.
        self._frame = 0
        #: **Each stimulus shown's first frame**, by name, from which `screen.resolve` times a
        #: drift: kept while it stays on the display, an `Update` included, and new with a `Show`
        #: after a `Hide`. Rebuilt on a frame the display changed (`_shown_now`).
        self.onsets: dict = {}
        #: Each input's key by what names it, read in `happened` without building a lookup's key.
        self._devices: dict = {}
        self._features: dict = {}
        self._chair = 0
        keyed = set()
        for item in keys:
            guard = item.guard
            keyed.add(_identity(guard))
            if isinstance(guard, (Pressed, Released, Response)):
                self._devices[guard.device] = item.key
            elif isinstance(guard, FeatureAbove):
                self._features[guard.source] = item.key
            elif isinstance(guard, ChairStill):
                self._chair = item.key
        unkeyed = [item.label for item in inputs(trial) if _identity(item.guard) not in keyed]
        if unkeyed:
            raise ValueError(f"the keys given number none of {', '.join(unkeyed)}, which this "
                             f"trial waits on: a demo world needs `inputs(trial)`")
        #: **What the display showed last**, name by name, to tell the first frame after it changed
        #: (`Onscreen`): blank at a trial's start, as the animal's screen is between trials.
        self._names: list = []
        self._stimuli: list = []
        self._onscreen = 0

    def display(self, visible, frame: int) -> None:
        """**The frame**: paced first (`Pace.start` on the trial's first frame, `wait` on every
        later one), where a rig's display blocks on its flip; then `Tracked.display`, which polls
        the source for the frame's sample and key edges; then whether what the frame shows changed,
        which `Onscreen` reports; then, given a drawing, the screen published if the frame is the
        trial's first, its screen changed, or `REDRAWN_EVERY_S` has passed (`_publish`). A frame
        that publishes nothing compares two integers for it, and builds nothing."""
        if frame == 1:
            self.pace.start()
        else:
            self.pace.wait(frame)
        Tracked.display(self, visible, frame)
        self._frame = frame
        changed = self._changed(visible)
        if changed:
            self._onscreen = frame
            self._shown_now(visible, frame)
        if self.publish is not None and (changed or frame >= self._redraw_at):
            self._publish(visible, frame)

    def ended(self) -> None:
        """**The trial has ended** (§3.9): its screen published blank, as the animal's is until the
        next trial's first frame, given a drawing; nothing without one. The session calls it at the
        trial's boundary (demo mode's Task 4)."""
        if self.publish is not None:
            self.publish(self.drawing.blank(self, self.index, self._frame))

    def _publish(self, visible, frame: int) -> None:
        """The screen of `frame` drawn (`Drawing.drawn`) and published, whole, and the next redraw
        due `REDRAWN_EVERY_S` on. **Only on a frame that publishes**, which a demo may spend
        (§3.9)."""
        self.publish(self.drawing.drawn(self, visible, self._values, self.trial, self.index, frame))
        self._redraw_at = frame + self._redraw_every

    def happened(self, guard: Guard, state: str, frame: int) -> bool:
        """`Pressed` and `Response` on their key's down edge, `Released` on its up edge,
        `FeatureAbove` while its key is held, `ChairStill` while its key is not, `Touched(window)`
        while the mouse button is down with the pointer in the window, `Onscreen` on the first frame
        after the display changed; every other guard `Tracked.happened`'s. **On the trial loop's
        path**, so nothing is built."""
        source = self.source
        if isinstance(guard, Pressed):
            return source.went_down(self._devices[guard.device])
        if isinstance(guard, Response):
            return source.went_down(self._devices[guard.device])
        if isinstance(guard, Released):
            return source.went_up(self._devices[guard.device])
        if isinstance(guard, FeatureAbove):
            return source.held(self._features[guard.source])
        if isinstance(guard, ChairStill):
            return not source.held(self._chair)
        if isinstance(guard, Touched):
            return source.button and self._touching(guard.window, frame)
        if isinstance(guard, Onscreen):
            return frame == self._onscreen
        return Tracked.happened(self, guard, state, frame)

    def _touching(self, window: str, frame: int) -> bool:
        """Whether the pointer is in `window`, an array's alias at any of its objects, as
        `Tracked.happened` judges a landing."""
        members = self._members.get(window)
        if members is None:
            declared = self._windows.get(window)
            return declared is not None and self.in_window(window, frame, declared.eye)
        return self._landed(members, frame)

    def _changed(self, visible) -> bool:
        """Whether `visible` differs from what the display showed last: another count of stimuli,
        or another stimulus under a name (an `Update` makes a new one). Walked by index."""
        names = self._names
        count = len(names)
        if len(visible) != count:
            return True
        stimuli = self._stimuli
        index = 0
        while index < count:
            if visible.get(names[index]) is not stimuli[index]:
                return True
            index += 1
        return False

    def _shown_now(self, visible, frame: int) -> None:
        """What the display shows now, kept, on a frame it changed; and each stimulus's first
        frame (`onsets`), its own while it stayed on the display, `frame` for one new to it."""
        was = self.onsets
        self.onsets = {name: was.get(name, frame) for name in visible}
        self._names = list(visible)
        self._stimuli = list(visible.values())


class Worlds:
    """**A demo run's worlds**, one a trial, as `taskd.Session.world` takes them, `(trial, values,
    index) -> Pointing`: the source readied for the trial's first frame (`new_trial`) and the
    trial's inputs numbered (`inputs`), at the pace's frame period, each publishing its screen
    through `publish` drawn by `drawing`, given both. One source, one pace and one drawing for the
    run.

    **And whether each trial waits for its page's pointer** (`waiting`; demo mode's Task 10, every
    trial since the whole-build review's I3). Before a run's first screen there is nothing drawn
    to point at, so no page can steer, and a trial whose eye nobody steers ends as tracker lost: a
    run's first trial would be scored before anyone could play it, and once a person lets go of
    the eye (Escape, a tab closed, or hidden, which the page lets go of as Escape does; the build's
    re-review, N1), every trial after would, about fifteen a second. So
    the trial loop asks `waiting` at the boundary before each trial (`taskd.Session.run`), and
    while no page steers holds there, as a pause does, the field published for a page to point
    at."""

    def __init__(self, source: Source, *, pace: Pace, drawing: "Drawing | None" = None,
                 publish=None) -> None:
        _paired(drawing, publish)
        self.source = source
        self.pace = pace
        self.drawing = drawing
        self.publish = publish

    def __call__(self, trial: Trial, values: dict, index: int) -> Pointing:
        self.source.new_trial()
        return Pointing(self.source, trial, self.pace.frame_period, values, pace=self.pace,
                        keys=inputs(trial), index=index, drawing=self.drawing,
                        publish=self.publish)

    def waiting(self, index: int) -> bool:
        """**Whether trial `index` waits for a page's pointer**: true while no page steers the eye
        (`Source.steered`) -- before any report, and once the reports have stopped and the last is
        past `LIVE_S`; while it waits, the field is published (`Drawing.field`), given a drawing, so
        a page has something to point at. Asked between trials, once a housekeeping pass while it
        waits. **The trial under way when the reports stop still ends as tracker lost**, under the
        task's `tracker_lost`, as the rig's own eye rules end it (§3.3); the next one waits (the
        whole-build review's I3)."""
        if self.source.steered():
            return False
        if self.publish is not None:
            self.publish(self.drawing.field(index))
        return True


def worlds(source: Source, *, pace: Pace, drawing: "Drawing | None" = None,
           publish=None) -> Worlds:
    """**A demo run's worlds** (`Worlds`): `(trial, values, index) -> Pointing`, as
    `taskd.Session.world` takes them, and `waiting`, which the trial loop asks before each
    trial."""
    return Worlds(source, pace=pace, drawing=drawing, publish=publish)
