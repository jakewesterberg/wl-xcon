"""Online Engbert-Kliegl saccade detection, and the batch form it is checked against.

**The algorithm is not ours and the choice was made for one reason.** S5 §5: it is
already `wl-preproc`'s offline baseline, so online-versus-offline disagreement measures
*staleness and latency* rather than two different algorithms. Anything else would have
made the disagreement uninterpretable, which is the whole point of running the same
method twice. Read `wl_preproc/eye/detect/engbert_kliegl.py` and `.../velocity.py`
before changing anything here; the constants below are theirs.

**Two functions and one class, in that order of trust.** `velocity` and `median_scale`
are theirs, reimplemented (a task PC does not import a pipeline that pulls DataJoint)
and contract-tested against the originals. `detect` is the batch form, which must agree
with their detector interval for interval on the same trace. `Detector` is the online
form the trial loop uses, and it is checked against `detect` -- so the online path is
never compared against a second idea of the algorithm, only against the shared one.

**What online costs, stated rather than discovered later.** Their five-point estimator
is `(x[n+2] + x[n+1] - x[n-1] - x[n-2]) * fs / 6`, so the velocity *at* sample n is not
computable until sample n+2 has arrived. A run is then only a saccade once
`min_duration_samples` of it exist. Detection therefore trails true onset by at least
`2 + min_duration_samples` samples -- 16 ms at 500 Hz -- **before** any display can
react, and later still when samples near its start are missing: at most five samples
later for one (`Detector`). That number is arithmetic, not a measurement: whether it
lands inside saccadic suppression is V3(b)'s to answer, photodiode to photodiode, and
S5 says so explicitly because a budget computed from component latencies is the thing
that is always wrong.

**The stall rule is why this is not just their code in a loop.** A tracker gap produces
an apparent velocity that is an artifact of the gap: two samples 80 ms apart differenced
as though they were 2 ms apart is an enormous fake velocity, and it both fires the
detector and inflates the threshold that is supposed to catch it. So velocity is
computed only across five samples that are genuinely consecutive in time, and a
detection whose window touched a gap is **flagged rather than dropped or silently
reported** (S5 §5). Dropping it would hide a real saccade; reporting it unmarked would
launder an artifact into the record. Until version 2 the online form did both, near a
run's start: a sample lost there could hide its confirmation, and a gap just before its
first velocity went unmarked (`Detector`; the PI, 2026-10-30, "Count it, marked").
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

#: Engbert & Kliegl's own conventional values, and `wl-preproc`'s defaults. Mirrored
#: rather than imported, and asserted equal to theirs in the contract tests: a
#: threshold that differs between the online and offline detector would make their
#: disagreement a parameter difference, which is exactly what S5 chose this algorithm
#: to avoid.
DEFAULT_LAMBDA = 6.0
DEFAULT_MIN_DURATION_SAMPLES = 6

#: Samples each side of the sample being estimated; the window spans `[n-2, n+2]`.
HALF_WINDOW = 2

#: Denominator of the five-point weighted difference.
_WEIGHT_SUM = 6.0

#: Bumped whenever anything here changes what a session would detect. It belongs in the
#: trial record beside the mapping version, because S5 §5 makes a detector change a
#: discontinuity of the same class as a parameter change (P16) -- two sessions run
#: under different versions are not comparable and must not silently look it. *Nothing
#: writes it yet (2026-10-30), nor a saccade's flag: backlog XC-427, waiting on build T.*
#:
#: **2 since 2026-10-30** (the PI, "Count it, marked"): `Detector` confirms a run on the
#: first velocity that shows it long enough, counted as `detect` counts it, rather than
#: only on the one that makes it exactly so, and reports it flagged; and it flags a run
#: with a gap in the windows of the two velocities before it, as `detect` does. So the
#: online form now counts and marks a run by `detect`'s rule: a saccade that a sample lost
#: near its start hid, which 1 never reported, is reported, flagged, at the start `detect`
#: gives it, and wl-preproc on the eye PC's whole trace. 1 and 2 detect the same thing,
#: sample for sample, wherever no sample is missing, and no two are more than `max_gap_s`
#: apart, within four samples of a velocity outside the threshold. **Beyond what the PI
#: was asked** (a question for him, 2026-10-30): a lost sample beside a single noise
#: velocity outside the threshold makes a run of six, now reported, marked, and taken by
#: a saccade guard, where 1 and wl-preproc report nothing. **Not wl-preproc's fixture set
#: "v2"** (true angle, XC-398): that numbers their published fixture files, and this
#: numbers our detector.
VERSION = 2


@dataclass(frozen=True, slots=True)
class Params:
    """Logged with every session. Not per-task, and not re-derivable in a task: S5 §5
    is explicit that parameters affecting results make two sessions incomparable if a
    task can set them privately."""

    lambda_: float = DEFAULT_LAMBDA
    min_duration_samples: int = DEFAULT_MIN_DURATION_SAMPLES
    #: The largest gap between consecutive samples that still counts as consecutive.
    #: Defaults to `eye.Tracker.staleness`, because the two answer the same question
    #: -- is this information still about the same stretch of time -- and two answers
    #: to it would drift.
    max_gap_s: float = 0.05
    #: How many usable velocity samples must exist before the threshold means
    #: anything. Below this the detector reports nothing rather than reporting
    #: against a scale estimated from noise -- the same refusal `Tracker.state` makes
    #: before its first sample, for the same reason.
    warmup_samples: int = 50


@dataclass(frozen=True, slots=True)
class Saccade:
    """One detected event, in sample indices into the trace that produced it."""

    start: int
    stop: int
    #: Degrees, start point to end point -- not path length.
    amplitude_deg: float
    #: True when the detection window touched a tracker gap. **Never dropped, never
    #: unmarked**: the velocity that triggered it may be an artifact of the gap
    #: rather than of the eye, and only the record can decide that afterwards.
    flagged: bool = False


def median(values: list[float]) -> float:
    """The middle value, on a copy, matching numpy's even-length averaging."""
    if not values:
        return 0.0
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2.0


def median_scale(component: list[float]) -> float:
    """`sqrt(median(v²) - median(v)²)`, the paper's own scale estimate.

    **A median-based scale, not a standard deviation**, and the difference is the
    point: an SD is inflated by the very saccades the threshold exists to find, so the
    detector would grow less sensitive exactly as a session contained more of what it
    is looking for.

    **The `variance > 0` guard is not caution.** The quantity is bounded below by zero
    by an order-statistics argument, but that is about exact arithmetic; in float64 two
    near-tied middle order statistics can make the subtraction round to a small
    negative number, and `sqrt` of that is `nan` rather than an error -- silent, not
    loud. `wl-preproc` measured `-1.78e-15` on a literal four-sample array. The guard
    turns that back into the zero it should have been.
    """
    if not component:
        return 0.0
    variance = median([v * v for v in component]) - median(component) ** 2
    return math.sqrt(variance) if variance > 0 else 0.0


def velocity(
    gaze_deg: list[tuple[float, float] | None],
    at: list[float],
    params: Params,
) -> list[tuple[float, float] | None]:
    """Degrees per second per sample, or `None` where it cannot honestly be computed.

    `None` in two cases, and they are the same case: the five-sample window is not
    fully present, or it spans a gap wider than `max_gap_s`. **The edges are `None`
    rather than zero**, which is where this deliberately differs from `wl-preproc`'s
    array form -- they return zeros because an array has to have a value there, and
    their docstring says the fabricated edge is the hazard. Having the option of
    "no answer" here, we take it, and `detect` excludes those samples from the
    threshold as well as from the output.
    """
    out: list[tuple[float, float] | None] = [None] * len(gaze_deg)
    for n in range(HALF_WINDOW, len(gaze_deg) - HALF_WINDOW):
        window = range(n - HALF_WINDOW, n + HALF_WINDOW + 1)
        if any(gaze_deg[i] is None for i in window):
            continue
        if any(at[i + 1] - at[i] > params.max_gap_s for i in range(n - HALF_WINDOW, n + HALF_WINDOW)):
            continue
        span = at[n + HALF_WINDOW] - at[n - HALF_WINDOW]
        if span <= 0:
            continue
        # `fs` from the window's own span rather than a declared sampling rate: the
        # protocol is poll-based and its interval is not guaranteed (`eye.py`), so a
        # nominal rate would be an assumption where a measurement is available.
        fs = 2 * HALF_WINDOW / span
        out[n] = (
            (gaze_deg[n + 2][0] + gaze_deg[n + 1][0] - gaze_deg[n - 1][0] - gaze_deg[n - 2][0])
            * fs / _WEIGHT_SUM,
            (gaze_deg[n + 2][1] + gaze_deg[n + 1][1] - gaze_deg[n - 1][1] - gaze_deg[n - 2][1])
            * fs / _WEIGHT_SUM,
        )
    return out


def thresholds(velocities: list[tuple[float, float] | None], params: Params) -> tuple[float, float]:
    """The per-axis elliptic thresholds, from the usable velocities only.

    Unusable samples are excluded from the estimate as well as from the output, for
    the reason `wl-preproc`'s detector gives: a gap's velocity spike would otherwise
    inflate the scale and desensitise the detector for the rest of the trial.
    """
    usable = [v for v in velocities if v is not None]
    return (
        params.lambda_ * median_scale([v[0] for v in usable]),
        params.lambda_ * median_scale([v[1] for v in usable]),
    )


def _outside(v: tuple[float, float], eta_x: float, eta_y: float) -> bool:
    """The paper's elliptic test: outside the ellipse whose semi-axes are the two
    thresholds. Not a speed threshold -- the axes are scaled independently, because
    horizontal and vertical noise differ and a circular test would be set by whichever
    axis was worse."""
    return _outside_xy(v[0], v[1], eta_x, eta_y)


def _outside_xy(vx: float, vy: float, eta_x: float, eta_y: float) -> bool:
    """`_outside`, the velocity given as its two numbers: the online detector's form, which holds
    no velocity as a pair (XC-414)."""
    return (vx / eta_x) ** 2 + (vy / eta_y) ** 2 > 1.0


def _amplitude(gaze_deg: list[tuple[float, float] | None], start: int, stop: int) -> float:
    first = next((gaze_deg[i] for i in range(start, stop) if gaze_deg[i] is not None), None)
    last = next((gaze_deg[i] for i in range(stop - 1, start - 1, -1) if gaze_deg[i] is not None), None)
    if first is None or last is None:
        return 0.0
    return math.hypot(last[0] - first[0], last[1] - first[1])


def detect(
    gaze_deg: list[tuple[float, float] | None],
    at: list[float],
    params: Params = Params(),
) -> list[Saccade]:
    """Every saccade in a trace. The batch form, and the reference `Detector` is
    checked against -- so the online path is compared with the shared algorithm rather
    than with a second idea of it."""
    velocities = velocity(gaze_deg, at, params)
    eta_x, eta_y = thresholds(velocities, params)
    if eta_x <= 0 or eta_y <= 0:
        return []

    found: list[Saccade] = []
    run_start: int | None = None
    for n, v in enumerate(velocities):
        continuous = n == 0 or (at[n] - at[n - 1]) <= params.max_gap_s
        if v is None:
            # **An unknown velocity does not end a run, as long as time is
            # continuous.** One dropped camera frame in the middle of a saccade used
            # to split the run into two pieces, each below the minimum duration, and
            # delete the event entirely -- so a single missing sample made the task
            # miss a response the animal really made. Unknown means unknown: the run
            # carries on and is flagged. A break in *time*, though, is different, and
            # ends the run: we no longer know what the eye did in between.
            if not continuous:
                if run_start is not None and n - run_start >= params.min_duration_samples:
                    found.append(_saccade(gaze_deg, velocities, run_start, n))
                run_start = None
            continue
        if _outside(v, eta_x, eta_y):
            if run_start is None:
                run_start = n
        elif run_start is not None:
            if n - run_start >= params.min_duration_samples:
                found.append(_saccade(gaze_deg, velocities, run_start, n))
            run_start = None
    if run_start is not None and len(velocities) - run_start >= params.min_duration_samples:
        found.append(_saccade(gaze_deg, velocities, run_start, len(velocities)))
    return found


def _saccade(gaze_deg, velocities, start: int, stop: int) -> Saccade:
    """Flagged when the window that produced it touched a sample with no velocity --
    the trace of a gap, by the time the run is being closed."""
    touched_gap = any(
        velocities[i] is None
        for i in range(max(0, start - HALF_WINDOW), min(len(velocities), stop + HALF_WINDOW))
    )
    return Saccade(start, stop, _amplitude(gaze_deg, start, stop), flagged=touched_gap)


@dataclass
class Detector:
    """The online form: one trial's worth of samples, fed as they arrive.

    **The threshold is per trial and adaptive** (S5 §5), which online means estimated
    from what the trial has produced so far. Before `warmup_samples` usable
    velocities exist it reports nothing at all, because a scale estimated from a
    handful of samples is a scale estimated from noise, and a detector that fires on
    it is worse than one that stays quiet.

    **Confirmed once its run is long enough, counted as `detect` counts it** (version 2;
    the PI, 2026-10-30, "Count it, marked"). A velocity the five-sample window cannot give
    -- a sample missing, or two more than `max_gap_s` apart -- does not end an open run
    while time is continuous, and counts toward its length, as in `detect`. So a run is
    reported on the first sample with a velocity that shows it at least
    `min_duration_samples` long: one outside the threshold, the run still open and `stop`
    the sample after it, or the one inside it that ends the run, `stop` that sample -- the
    eye has landed, and where is measured. Version 1 confirmed a run only on the velocity
    that made it exactly that long, so a sample lost near its start, which leaves the five
    velocities around it unknown, could hide that one, and the saccade was never reported
    while `detect` reported it. Such a run is reported **flagged**, as is one with a gap
    in the windows of the two velocities before it (`_saccade`'s window begins two samples
    before the run). **Counting unknown velocities has a cost the PI was not asked about**
    (a question for him, 2026-10-30): one noise velocity outside the threshold, then the
    five a lost sample leaves unknown, then one inside it, is a run of six, reported
    flagged as it ends, where version 1 and wl-preproc report nothing. **What a
    confirmation cannot know, it does not claim**: a gap after it, in the run or in the two
    samples beyond it, flags the batch form's saccade and not this one; and a run a break
    in time ends before it is confirmed is not reported here, where `detect` reports it
    once long enough -- the PI counted a saccade whose landing is measured, and after a
    break in time nothing is. *On the rig's default path none of this is reached yet
    (2026-10-30): `gaze.Tracked` gives a lost datagram as the held sample again, never as
    a gap, until the tracker's staleness runs out (backlog XC-428, waiting on build T and
    V3(a)).*

    **Bounded work per sample.** Velocity is five plain multiplications on a ring of the
    last five samples (`_WINDOW`). The threshold is *not* recomputed per sample -- that
    would be a median over a growing list inside a trial loop, which is the unbounded
    per-frame work CLAUDE.md forbids -- but every `refresh_every` usable velocities (and
    every one while both thresholds are still zero), over the last `history` of them. What
    that costs is unmeasured and stays unmeasured here: it is a number for a tools/ script
    and `docs/measurements/`, not for a docstring.

    **And nothing built per sample but what one returns** (XC-414): a sample is
    `gaze.Tracked.display`'s every frame, so every buffer is built with the detector, its
    size fixed by its parameters -- the last five samples, the last `history` velocities,
    and the list their medians are sorted in -- and a sample overwrites values in them.
    What a sample still builds: the `Saccade` a confirming sample returns, one a saccade,
    and the list `_refresh` re-estimates over when a NaN is among the velocities before
    `history` of them exist (`_thresholds_as_listed`). Until 2026-10-29 every sample
    appended to three growing lists, sliced two, walked them with generators, and every
    refresh copied the velocities into a list and sorted copies of it.
    """

    params: Params = field(default_factory=Params)
    #: How many usable velocities the threshold is estimated over, and how often it is
    #: re-estimated. Bounded so the trial loop's cost does not grow with trial length.
    history: int = 1000
    refresh_every: int = 50

    #: **The last samples, a ring**: sample `k` of the trial (counting from 0) in slot
    #: `k % len(_t)`, its gaze in `_x` and `_y` when `_present`. The five-sample window
    #: (`_WINDOW`): never a sample older than it needs, so nothing is trimmed. A run's
    #: first sample is kept apart as the run starts (`_run_x`, `_run_y`).
    _x: list = field(init=False, repr=False)
    _y: list = field(init=False, repr=False)
    _t: list = field(init=False, repr=False)
    _present: list = field(init=False, repr=False)
    #: How many samples this trial has accepted. A sample's index is absolute, which is
    #: what makes `Saccade.start` mean the same thing as it does in `detect`.
    _seen: int = field(default=0, init=False, repr=False)
    #: **The last `history` usable velocities, a ring**: `_v_count` of them, the next
    #: written at `_v_next`, the oldest `_v_count` slots before it.
    _vx: list = field(init=False, repr=False)
    _vy: list = field(init=False, repr=False)
    _v_count: int = field(default=0, init=False, repr=False)
    _v_next: int = field(default=0, init=False, repr=False)
    #: Where a median is taken (`_median`): the velocities, oldest first, then +inf.
    _sorting: list = field(init=False, repr=False)
    _eta_x: float = field(default=0.0, init=False, repr=False)
    _eta_y: float = field(default=0.0, init=False, repr=False)
    _since_refresh: int = field(default=0, repr=False)
    #: Absolute sample index of the open run.
    _run_start: int | None = field(default=None, repr=False)
    #: Whether the open run's window has touched a gap, from two samples before its start.
    _run_had_gap: bool = field(default=False, repr=False)
    #: Whether the open run has been reported, so it is reported once (version 2).
    _run_confirmed: bool = field(default=False, init=False, repr=False)
    #: **The open run's first sample, kept as it starts** (version 2): a run with unknown
    #: velocities in it can outgrow any ring before it is confirmed, and its size is measured
    #: from here (`_amplitude`).
    _run_x: float = field(default=0.0, init=False, repr=False)
    _run_y: float = field(default=0.0, init=False, repr=False)
    #: The last sample with no velocity, by absolute index; until there is one, sample 1, the
    #: later of the two `velocity` gives none for want of a window. A run whose first velocity
    #: is within `HALF_WINDOW` samples of it is flagged, as `_saccade` flags it (version 2).
    _last_unknown: int = field(default=HALF_WINDOW - 1, init=False, repr=False)
    #: Set for the sample on which a saccade was confirmed, and cleared by the next
    #: `accept`. The trial loop asks once per frame, so an edge has to survive exactly
    #: one question, not until someone happens to ask.
    onset: Saccade | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        """Every buffer, built once, as the detector is (XC-414)."""
        ring = _WINDOW
        self._x = [0.0] * ring
        self._y = [0.0] * ring
        self._t = [0.0] * ring
        self._present = [False] * ring
        kept = max(self.history, 0)
        self._vx = [0.0] * kept
        self._vy = [0.0] * kept
        self._sorting = [0.0] * kept

    def reset(self) -> None:
        """A new trial. The threshold is per trial, so carrying one across trials
        would make the first trial's noise decide the second trial's sensitivity.
        The buffers are kept, and written over from their first slot."""
        self._seen = 0
        self._v_count = 0
        self._v_next = 0
        self._eta_x = 0.0
        self._eta_y = 0.0
        self._since_refresh = 0
        self._run_start = None
        self._run_had_gap = False
        self._run_confirmed = False
        self._last_unknown = HALF_WINDOW - 1
        self.onset = None

    @property
    def in_flight(self) -> bool:
        """Whether a supra-threshold run is currently open -- the eye is still moving
        and has not landed anywhere yet."""
        return self._run_start is not None

    @property
    def ready(self) -> bool:
        """Whether the threshold rests on enough samples to mean anything: enough
        velocities, and the smaller threshold above zero (`min`'s choice of the two)."""
        eta_x = self._eta_x
        eta_y = self._eta_y
        return (self._v_count >= self.params.warmup_samples
                and (eta_y if eta_y < eta_x else eta_x) > 0)

    def accept(self, at: float, gaze_deg: tuple[float, float] | None) -> Saccade | None:
        """One sample. Returns a saccade on the sample that confirms it, else `None`.

        Confirmation, not onset: the run is reported on the first sample with a velocity
        that shows at least `min_duration_samples` of it (the class docstring), and
        `Saccade.start` is where it actually began. The lag between the two is the
        detector's, and it is arithmetic rather than measurement -- see the module
        docstring.
        """
        self.onset = None
        xs = self._x
        ys = self._y
        ts = self._t
        present = self._present
        ring = len(ts)
        slot = self._seen % ring
        if gaze_deg is None:
            present[slot] = False
        else:
            present[slot] = True
            xs[slot] = gaze_deg[0]
            ys[slot] = gaze_deg[1]
        ts[slot] = at
        self._seen += 1

        centre = self._seen - 1 - HALF_WINDOW
        if centre < HALF_WINDOW:
            return None

        # The five-sample window, `centre - 2` to `centre + 2`, by slot.
        w0 = (centre - 2) % ring
        w1 = (centre - 1) % ring
        w2 = centre % ring
        w3 = (centre + 1) % ring
        w4 = slot
        gap = self.params.max_gap_s
        moved = False
        vx = vy = 0.0
        if (present[w0] and present[w1] and present[w2] and present[w3] and present[w4]
                and ts[w1] - ts[w0] <= gap and ts[w2] - ts[w1] <= gap
                and ts[w3] - ts[w2] <= gap and ts[w4] - ts[w3] <= gap):
            span = ts[w4] - ts[w0]
            if span > 0:
                fs = 2 * HALF_WINDOW / span
                vx = (xs[w4] + xs[w3] - xs[w1] - xs[w0]) * fs / _WEIGHT_SUM
                vy = (ys[w4] + ys[w3] - ys[w1] - ys[w0]) * fs / _WEIGHT_SUM
                moved = True

        if moved:
            kept = len(self._vx)
            if kept:
                self._vx[self._v_next] = vx
                self._vy[self._v_next] = vy
                self._v_next = self._v_next + 1 if self._v_next + 1 < kept else 0
                if self._v_count < kept:
                    self._v_count += 1
            self._since_refresh += 1
            if self._since_refresh >= self.refresh_every or (
                    self._eta_x == 0.0 and self._eta_y == 0.0):
                self._refresh()
                self._since_refresh = 0
        else:
            # `velocity`'s `None`, remembered so a run starting within the window of it is
            # flagged as `_saccade` flags one (version 2).
            self._last_unknown = centre

        if not self.ready:
            self._run_start = None
            self._run_had_gap = False
            return None

        continuous = ts[w2] - ts[w1] <= gap
        if not moved:
            # Same rule as `detect`: unknown velocity flags an open run rather than
            # ending it, and counts toward its length; a break in time ends it. Two
            # answers here would make the online and offline detectors disagree about
            # gaps specifically, which is the one thing S5 §5 wants their disagreement to
            # be measurable against. One remains, and the class docstring says why: a
            # run a break in time ends unconfirmed is not reported here.
            if self._run_start is not None:
                self._run_had_gap = True
                if not continuous:
                    self._run_start = None
                    self._run_had_gap = False
            return None

        # **Confirmed on the first velocity that shows the run long enough** (version 2):
        # outside the threshold, the run counted to here, or inside it, ending the run
        # here, as `detect` ends one. Not only on the velocity that makes it exactly
        # `min_duration_samples` long, which a sample lost near its start can hide.
        start = self._run_start
        if _outside_xy(vx, vy, self._eta_x, self._eta_y):
            if start is None:
                start = self._run_start = centre
                self._run_x = xs[w2]
                self._run_y = ys[w2]
                self._run_confirmed = False
                self._run_had_gap = centre - self._last_unknown <= HALF_WINDOW
            if self._run_confirmed or centre - start + 1 < self.params.min_duration_samples:
                return None
            stop = centre + 1
        elif start is None:
            return None
        else:
            self._run_start = None
            if self._run_confirmed or centre - start < self.params.min_duration_samples:
                return None
            stop = centre
        self._run_confirmed = True
        found = Saccade(
            start=start,
            stop=stop,
            amplitude_deg=self._amplitude(stop),
            flagged=self._run_had_gap,
        )
        self.onset = found
        return found

    def _amplitude(self, stop: int) -> float:
        """`_amplitude` over the open run's samples to `stop - 1`, start point to end point: the
        run's first sample, kept as it started (`_run_x`, `_run_y`), to sample `stop - 1` in the
        ring. **Both are the first and last present samples `_amplitude` would find**: a run
        starts, and is confirmed, only on a sample with a velocity, whose window holds it and the
        two each side of it, and `stop - 1` is the confirming sample or the one before it."""
        last = (stop - 1) % len(self._t)
        return math.hypot(self._x[last] - self._run_x, self._y[last] - self._run_y)

    def _refresh(self) -> None:
        """The thresholds, re-estimated from the last `history` velocities: `thresholds` over
        them, oldest first, **bit for bit** (XC-414), with nothing built. Each median sorts the
        values in `_sorting`, the velocities oldest first and, while fewer than `history` exist,
        +inf after them (`_median`); a stable sort over values `<` orders totally leaves the first
        `count` exactly as `sorted` orders the velocities alone. **A NaN orders nothing**, so
        while the buffer is filling and one is among them the thresholds are `thresholds` over the
        velocities as a list, which builds it: a tracker handing over NaN, never one that works.
        Once it is full, the sort is over the velocities alone, in the order `sorted` met them."""
        count = self._v_count
        kept = len(self._vx)
        oldest = self._v_next - count
        if oldest < 0:
            oldest += kept
        if count < kept and _any_nan(self._vx, self._vy, oldest, count):
            self._eta_x, self._eta_y = _thresholds_as_listed(self._vx, self._vy, oldest, count,
                                                              self.params)
            return
        self._eta_x = self.params.lambda_ * self._scale(self._vx, oldest, count)
        self._eta_y = self.params.lambda_ * self._scale(self._vy, oldest, count)

    def _scale(self, ring: list, oldest: int, count: int) -> float:
        """`median_scale` over `count` values of a velocity ring from slot `oldest`."""
        if count == 0:
            return 0.0
        variance = (self._median(ring, oldest, count, True)
                    - self._median(ring, oldest, count, False) ** 2)
        return math.sqrt(variance) if variance > 0 else 0.0

    def _median(self, ring: list, oldest: int, count: int, squared: bool) -> float:
        """`median` over `count` values of a velocity ring from slot `oldest`, each squared when
        `squared`, sorted in `_sorting` after +inf fills the rest of it."""
        sorting = self._sorting
        kept = len(ring)
        index = 0
        slot = oldest
        while index < count:
            value = ring[slot]
            sorting[index] = value * value if squared else value
            index += 1
            slot += 1
            if slot == kept:
                slot = 0
        while index < kept:
            sorting[index] = math.inf
            index += 1
        sorting.sort()
        middle = count // 2
        if count % 2:
            return sorting[middle]
        return (sorting[middle - 1] + sorting[middle]) / 2.0


#: How many samples `Detector` keeps: the five-sample window. **Not the run as well**, as it was
#: until version 2: a run whose velocities include unknown ones is confirmed when it is long enough
#: as `detect` counts it, which no ring sized by `min_duration_samples` holds, so its first sample
#: is kept apart as it starts (`Detector._run_x`).
_WINDOW = 2 * HALF_WINDOW + 1


def _any_nan(xs: list, ys: list, oldest: int, count: int) -> bool:
    """Whether any of `count` velocities in a ring from slot `oldest` has a NaN component."""
    kept = len(xs)
    index = 0
    slot = oldest
    while index < count:
        if xs[slot] != xs[slot] or ys[slot] != ys[slot]:
            return True
        index += 1
        slot += 1
        if slot == kept:
            slot = 0
    return False


def _thresholds_as_listed(xs: list, ys: list, oldest: int, count: int,
                          params: Params) -> tuple[float, float]:
    """`thresholds` over `count` velocities of a ring from slot `oldest`, as the list of pairs
    the online detector kept until XC-414, oldest first: what `Detector._refresh` gives when a
    NaN is among them before the ring is full, so the order the values were met in decides the
    median as it always did."""
    kept = len(xs)
    return thresholds([(xs[(oldest + i) % kept], ys[(oldest + i) % kept]) for i in range(count)],
                      params)
