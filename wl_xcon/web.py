"""The browser console's panes and page: a `Telemetry` frame in, HTML out.

P4d-2b slice b1 (`docs/superpowers/specs/2026-09-26-P4d2b-browser-console-design.md`
§1, §4.2). **Pure** -- no socket, no clock, no thread. `wlx serve` reads the clock and
the stream and hands them in as a `View`, so every pane is tested the way `cli.render`
is: "fluid session and the supplement are never dropped" is an assertion on this
module's output (spec §4.4), not a hope about a browser.

**Every telemetry string reaches the page through `_e`** (`html.escape`, quotes
included), in elements and attributes alike. A task path, a condition, a refusal's
reason and an actor's typed name are text a person or a peer chose.

**Every number is read from the frame**, as `cli.render`'s are, with the arithmetic a
display needs and no more: the strip's correct counts, which add `correct_reject` to
`correct` -- the one rollup, ruled for the strip alone (PI, 2026-09-26, spec §3) -- and
their percentages, the fluid bar's width, the deadline back to the cage (the frame's
instant less the time out, plus the limit: the session-levels plan, ruling 5), and the
time since the last reward -- the frame's own instant less the reward's, both on the
session's anchored clock, plus how long `wlx serve` has held the frame on its steady
clock (`View.frame_age_s`; ledger Ruling 1, 2026-09-27). No host clock is read against
a session instant. Trials per minute is derived by `wlx serve`, never here.

**Unknown is a word, never 0**: a day nobody measured, a reward not given yet, a
configuration nobody named, and the three *Wrong?* measurements nothing takes yet. A
rate not derived yet is left off the strip, as mockup v13 leaves it, never `0.0/min`.

**The strip carries two cells** (session-levels spec §6, amending P4d-2b spec §4.0):
fluid today against its floor, with the supplement, the last reward and back to cage
beneath it; and correct over trials for the session, its task, this run and this
block. Fluid session is on Runtime and End of session, and the supplement on both as
well as the strip, where **both are on the page in every state**: the zero-reward
ruling (S9a §9) rests on their being visible.

**A demo** (demo mode §4.1-§4.3, §4.6; its plan's Task 9): DEMO in the header on every demo frame
(`Telemetry.demo`, `Idle.demo`); while the frame says so, the demo screen in place of the replica
pane, filled by the stream's `drawn` events (`serve`), opened full-window by F, a click or `#demo`
in the address, under it the last trial's outcome and the key list (`demo_keys`, `DEMO_LIMITS`);
the pointer turned into degrees from the drawing's own eye group, `atan(x_cm / D)` per axis, and
posted to `/gaze` by the script; and the New session dialog's demo choice (`_dn_demo`).
"""

from __future__ import annotations

import html
import dataclasses
import math
import re
import string
import time
from dataclasses import dataclass
from decimal import Decimal
from importlib import resources
from pathlib import PurePath

from wl_xcon import health as _health
from wl_xcon.actor import Actor, Member
from wl_xcon.cli import _clock, _moment, _setup_words
from wl_xcon.demoscreen import GAZE_EVERY_MS
from wl_xcon.link import RECENT_OUTCOMES, ConditionRow, Counts, Idle, Question, Telemetry
# The segments' bound, said where a choice is said in short (`link.choice_label`).
from wl_xcon.link import CHOICE_LABEL_LIMIT, choice_label  # noqa: F401
from wl_xcon.pointer import KEYS as _KEYS
from wl_xcon.pointer import LIVE_S as _LIVE_S
from wl_xcon.task import (
    BELOW_ZERO, CEILINGS, OTHER, SPECIAL_UNIT, TRAINING_SECTION, Family, Outcome, at_hardest,
)
from wl_xcon.warnlist import HEAD_FREE, UNLISTED


@dataclass(frozen=True, slots=True)
class View:
    """What `wlx serve` adds to a frame: facts about the stream and the viewer, never
    about the session."""

    #: Seconds since `wlx serve` received the latest frame, on its own steady clock
    #: (`serve.Hub`); `None` before any. **Also what the time since the last reward is
    #: aged by** (ledger Ruling 1, 2026-09-27): the frame's `wall_at` less its
    #: `last_reward_at`, both on the session's anchored clock, plus this. There is no
    #: wall clock here on purpose: `wlx serve`'s host clock parts from the session's
    #: anchor by any step it has taken since the session began, and a step back once
    #: read the age short -- clamped at `0 s`, the direction that hides a working,
    #: unpaid animal.
    frame_age_s: float | None
    #: `--stale-after`: a display choice (spec §3), not a measurement.
    stale_after_s: float
    #: Derived by `wlx serve` from `trial_index` over the frames of the last five
    #: minutes (spec §4.1); `None` until two frames a moment apart exist.
    trials_per_min: float | None
    #: Whether the browser this render is for is on the box (a loopback peer).
    on_box: bool
    #: How many event streams are open from other hosts.
    lan_viewers: int
    #: Why the last frame `wlx serve` received could not be used, or `None`.
    rejected: str | None
    #: The PUB endpoint this console reads, `--link`'s first half (`serve.Hub`). With
    #: no frame and no refusal, what the page and `/health` can truthfully say is
    #: that nothing has arrived *here* -- never that nothing is publishing (m4).
    endpoint: str
    #: Whether this page may write (P4d-2b spec §2, §5.2): the box's own page, a
    #: loopback peer that named loopback in `Host`. Everywhere else every control is
    #: greyed with `CONTROLS_AT_THE_BOX`. `False` unless `wlx serve` says otherwise:
    #: a view that did not say may not write.
    can_write: bool = False
    #: Whether this console has the session's mark endpoint (`wlx serve --link
    #: PUB,REP,MARK`); without it the mark control is greyed with `NO_MARK_ENDPOINT`.
    can_mark: bool = False
    #: Whether this is the https page, whose controls work once the script holds a
    #: sign-in (b2b spec §4): a control that needs only that renders `disabled
    #: data-signin` (`_gate`).
    signin: bool = False
    #: Whether this is the plain-http page of a rig that also has an https page (b2b
    #: spec §3): a LAN viewer's greyed controls then say where else controls work.
    https_page: bool = False
    #: `(streams open, the cap)` for `/health`'s *streams* reading, which the *wl-works
    #: sees* pane shows too; `None` where the caller does not say (no such reading).
    streams: tuple[int, int] | None = None
    #: Whether this console has a demo's gaze endpoint (`wlx serve --link PUB,REP,MARK,GAZE`;
    #: demo mode §4.5), so a page may steer a demo from here through `POST /gaze`, under the
    #: write checks every write takes. `False` unless `wlx serve` says otherwise.
    can_gaze: bool = False


@dataclass(frozen=True, slots=True)
class SignIn:
    """What the https page needs to sign a member in (b2b spec §4), from `wlx serve`.
    `web` must not import `signin`, which imports `jwt`: `unavailable` is the sentence
    for a rig with no keys yet, and `authorize` and `token_endpoint` are `None` then."""

    authorize: str | None
    token_endpoint: str | None
    client_id: str
    page: str
    resource: str
    unavailable: str | None = None


#: Every fragment `fragments` renders, in page order. Each is the inner HTML of the
#: element with that id; the page's script swaps them by the same id.
FRAGMENT_IDS = (
    "demo-tag",
    "state",
    "bar-nums",
    "head-id",
    "presence",
    "strip",
    "banners",
    "task-sel",
    "plan-sel",
    "pf-pill",
    "controls",
    "rt-trials",
    "rt-work",
    "rt-shaping",
    "rt-need",
    "rt-wrong",
    "rt-health",
    "rt-changes",
    "params",
    "moments",
    "shaping",
    "rt-train",
    "training-params",
    "pf-sum",
    "preflight",
    "setup",
    "warnings",
    "end-actions",
    "end",
    "demo-under",
    "dn-demo",
    "dn-subject",
    "dn-warnings",
)

# --- a demo (demo mode §4; its plan's Task 9) ---------------------------------------------------

#: **How often the page reports a still pointer, in milliseconds**: `demoscreen.GAZE_EVERY_MS`, the
#: one definition, which the preview's size was chosen against (demo mode §3.3); imported above. The
#: page reports at most once an animation frame while the pointer moves, and at least this often
#: while it is still, one report in flight at a time.

#: **The test monkey's folder**, a demo's one animal: `service.REFERENCE`, which this module does
#: not import (`tests/test_web.py` holds the two equal).
REFERENCE = "REFERENCE"

#: **Why the live rig's demo box is grayed** (the PI, 2026-11-14: a demo is offered on a rig only
#: where its idle frame says `gaze`): no `REFERENCE` to open one for, or nowhere for one to run.
NO_REFERENCE = "no REFERENCE folder under --subjects"
NO_GAZE = "this rig names no gaze endpoint or no --demo-root"
#: And while a demo in the rig's demo folder is stranded: the service opens no other demo (XC-504).
DEMO_STRANDED = "a demo's return is not recorded: end it from its Stranded banner first"
#: What the demo screen says before a drawing of this session has come (Task 8's carried (c): the
#: hub keeps the last drawing after a demo ends, and the page shows only the session's own).
DEMO_NO_SCREEN = "no screen yet: each trial's first frame draws it"
#: Why a page steers no demo (demo mode §4.5): a console with no gaze endpoint, or a page that may
#: not write, which sees the drawing and no dot.
DEMO_NO_GAZE = (
    "watching only: this console was started without the demo's gaze endpoint, so no page "
    "steers the demo from here (wlx serve --link PUB,REP,MARK,GAZE)"
)
DEMO_WATCHING = "watching only: the demo's eye is steered where controls work"

#: **What a mouse is not** (demo mode §3.3, §14 item 17; decisions.md TSK-48), under the demo
#: screen beside its keys, as the design says it, its sources cited as there.
DEMO_LIMITS = (
    "A hand is slower than an eye. A mouse is positioned on text in a mean 1.29 s (SD 0.42) after "
    "0.36 s of homing [@card1977evaluation, Table 2, p. 10], where a monkey's saccadic reaction "
    "times are about 200 ms with no gap [@fischer1983saccadic]: a demo cannot judge any time "
    "window. The pop-out's 1.0 s to respond is an eye's; a player raises it to 3.0 s, its "
    "declared maximum (--set response_deadline=3.0, or Task parameters). Its 0.3 s from leaving "
    "the fixation window to landing cannot be raised: a hand slower than that, or one that stops "
    "short and corrects, is scored a look elsewhere (abort).",
    "The pointer lands where it is put: window sizes and holds cannot be judged.",
    "Both eyes are the pointer: vergence is always zero, and each stimulus shown to one eye is "
    "labeled L or R, with its disparity when nonzero.",
    "The mouse is both the eye and the hand: a task that needs them in different places cannot "
    "be completed by hand, and one that needs them together always is.",
    "A stimulus up for less than a drawing may never be drawn, and no duration can be judged from "
    "the drawing; +y is up.",
    "The operator's monitor is not the rig's panel: the pop-out's colors are drawn as the exact "
    "drawer defines them, but whether they are isoluminant, and at 15 cd/m², cannot be judged by "
    "eye on it.",
)

#: The key list's rows that stand whatever the task (demo mode §3.3, §3.4, §4.3, §4.5, §4.6), each
#: `(the key, what it does)`; B's says what the trial loop does with a key pressed while it is held
#: (demo mode's Task 2), and Escape's what it does mid-trial (Task 8) and after (the whole-build
#: review's I3), beside it.
DEMO_INPUTS = (
    ("pointer", "the eye, over the drawing; off it the eye looks away, outside every window: no "
                "fixation, or a break, never tracker loss"),
    ("button", "the mouse button: a touch where the pointer is, so the mouse is the eye and the "
               "hand at once"),
    ("B", "held: tracker loss, as a rig's tracker loses the eye; the trial ends as its "
          "tracker_lost says. A number key pressed while B is held is not seen, since the trial "
          "asks no guard while the tracker is lost"),
    ("Esc", f"closes the full window and lets go of the eye, as hiding the tab does. With no page "
            f"steering, the eye reads as tracker loss after {_LIVE_S:g} s, so an Escape mid-trial "
            f"ends that trial as tracker lost, and the run waits before the next until a page "
            f"points again"),
    ("F", "the full window; a click on the screen opens it too"),
    ("P · M", "pause or resume · mark, as everywhere on the page"),
)
#: Where the number keys and B act (demo mode §4.6).
DEMO_KEYS_WHERE = (
    "The number keys and B act only while the pointer is over the drawing or the full window is "
    "open, never while typing in a box."
)


#: The ticks' legend: one entry per `Family`, then the two strings that are none.
LEGEND = tuple((family.name.lower(), family.value) for family in Family) + (
    ("hang", "hang"),
    ("other", "unknown outcome"),
)

#: What a refused write says, and what a LAN viewer's greyed controls say on the
#: plain-http page (P4d-2b spec §2, b2b spec §3): the first without an https page
#: configured, the second with one.
CONTROLS_AT_THE_BOX = "controls work only at the rig PC"
CONTROLS_ELSEWHERE = "controls work at the rig PC, or signed in on this rig's https page"
#: What the rig PC's page and `wlx serve`'s terminal say, with the reason, when the rig's
#: https page could not be set up (b2b-ready §3.1).
HTTPS_OFF = "the rig's https page is off"
#: How often the https page tries a renewal or a confirmation again while wl.works or this
#: rig cannot be reached (b2b-ready §4.2-§4.3): housekeeping, not a measurement. Rendered
#: on `<body>`, so a test can shorten it.
SIGNIN_RETRY_MS = 30_000
#: How often a https page that could offer no sign-in asks this rig again whether it can
#: check one (b2b-ready §4.6), the keys thread's own interval: housekeeping, not a
#: measurement. Rendered on `<body>`, so a test can shorten it.
KEYS_RECHECK_MS = 60_000
#: How long the https page waits for a stored sign-in's lock before taking the sign-in for
#: another tab's copy (b2b-ready §4.5): housekeeping, not a measurement. Rendered on
#: `<body>`, so a test can lengthen it.
SIGNIN_LOCK_WAIT_MS = 1_000
#: What a control says on the https page to a browser not signed in (b2b spec §4).
SIGN_IN_FIRST = "sign in with wl.works to use the controls"
#: Why the mark control is greyed on a console started without the mark endpoint.
NO_MARK_ENDPOINT = (
    "this console was started without the session's mark endpoint: give wlx serve "
    "--link PUB,REP,MARK, as wlx run was given it"
)
#: Why *give reward* is greyed while a run's trials run: during a run the rig gives a
#: manual reward only while it is paused (PI, 2026-09-28); outside a run, in a `wlx
#: taskd` session, it gives one between runs and while the return is awaited (PI,
#: 2026-09-29, spec §6.0; `taskd.Session._manual_reward`).
REWARD_ONLY_PAUSED = "a manual reward is given only while the session is paused: pause first"
#: **The most changes Apply all sends as one act** (the console interface rework's Task 6): a
#: refused act writes a refusal per change, and a frame keeps only the last
#: `link.REFUSAL_HISTORY` (50) of them, so an act of more could lose some boxes' own reasons. Below
#: `link.APPLY_LIMIT` (64), which the rig takes. The page's script reads it from `<body>`.
APPLY_ALL_LIMIT = 50

#: **The page around the boxes** (the console interface rework's Task 8), its words: the *session*
#: button's title, the find box's, Runtime's Pinned strip's line, and the demo screen's folded keys
#: (the design's call: "fold to one line ("keys and demo limits"), open on the first visit only").
SESSION_SAID = ("the session's details: who, which run and block, the animal's fluid and time out, "
                "the next run's task and plan, a scheduled stop")
FIND_SAID = "find a setting or section"
#: **What the find box says where nothing matches** (the summary and editor plan's Review Focus 4:
#: "Find with no match / Enter on no match dims everything and opens nothing, saying 'no setting
#: matches'").
NO_MATCH = "no setting matches"
PINNED_SAID = ("settings you pinned from the settings tabs; click one to change it here, one draft "
               "between here and its tab")
#: **What Runtime's editor says with no pinned setting opened** (the summary and editor build's
#: Task 3: the design's goal 9, "a click opens the same editor on Runtime").
PINNED_EMPTY = "click a pinned setting above to change it"
#: **What the editor says where the find box hides the setting opened in it** (the ledger's
#: ruling for the summary and editor build's Task 3), in place of a blank editor.
FIND_HIDES_OPENED = "the opened setting is hidden by find · clear find to see it"
DEMO_FOLD_SAID = "keys and demo limits"
#: The trials the plain run is offered with: `wlx run --trials`'s default (`cli`), the flat run
#: of N trials, one block (the b3a-2 plan, decision 6). A run of one of its task's plans has its
#: plan's lengths, and the box is hidden while a plan is chosen (engine build C2b). A starting
#: figure the person changes, not a rule or a measurement.
RUN_TRIALS = 1000
#: The plain run as the plan picker offers it (the PI, 2026-10-19, "Preselect first, keep plain":
#: "the plain run stays as one more labeled choice").
PLAIN_RUN = "plain run: the trials below, each counted once, none shown again"
#: What *end session* asks before it is sent (the mockup's `end-confirm`, P4d-2b spec
#: §6.2): what ending does here, the head's release now and the return now or later (the
#: b3a-1 plan, decision 6) -- not the mockup's "the in-session clock stops, and the code
#: it used is packaged", which predates it and slice b6.
END_CONFIRM = (
    "end the session? no further run starts in it; a run in progress stops at its next "
    "trial boundary, and the head's release is recorded then. give the time the animal "
    "went back into its home cage now, or leave it blank and record it once the animal "
    "is home"
)

_NONE = '<span class="nm">no session</span>'
_UNKNOWN_DAY = "unknown: the day's prior total was not supplied"
#: Spec §3: "Drops, tracker staleness and RHX margin have no source and render not
#: measured, never 0."
_NOT_MEASURED = ("dropped frames", "tracker staleness", "RHX margin")
_VERDICT_TONE = {"ok": "ok", "degraded": "warn", "down": "crit"}


def _e(value: object) -> str:
    """The one way telemetry text reaches the page."""
    return html.escape(str(value), quote=True)


def _num(value: object) -> str:
    """A parameter's value: `unset` for `None`, two decimals for a number, and the
    text of a categorical choice. Formatting, not derivation."""
    if value is None:
        return "unset"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return f"{value:.2f}"
    return str(value)


def _pct(part: float, whole: float) -> float:
    """A bar's width, held to 0-100. Display arithmetic on two published numbers."""
    if whole <= 0:
        return 0.0
    return max(0.0, min(100.0, 100.0 * part / whole))


# --- the header -------------------------------------------------------------------


def _clock_time(at: float | None) -> str:
    """A session instant as this host's local clock time, `HH:MM:SS`, as `cli.render`
    prints the last reward: formatting an instant the frame carries, never reading a
    clock. One that is not a number is `—`, never a crash of every pane -- and so is a
    finite one too far out for `time.localtime`, which raises `OverflowError`,
    `OSError` or `ValueError` for it, by platform and by how far (the b2a final
    review)."""
    if at is None or not math.isfinite(at):
        return "—"
    try:
        return time.strftime("%H:%M:%S", time.localtime(at))
    except (OverflowError, OSError, ValueError):
        return "—"


def _wall_minute(at: float) -> str:
    """A session instant as this host's `HH:MM`, as `_clock_time` gives `HH:MM:SS`."""
    return _clock_time(at)[:5]


def _state(frame: Telemetry | None) -> str:
    """The header's pill, from `phase`, `stop_kind` and -- P4d-2b b2a -- `paused_at`:
    a session that ended while paused shows how it ended, never *paused*."""
    if frame is None:
        return '<span class="pill neutral" data-state="none">no session</span>'
    if frame.phase == "between_runs":
        # `run_index` counts from 0 on the wire, as the record's `run` does; a person
        # reads runs from 1, as the strip's `run_in_session` gives them (session-levels
        # spec §3), so the header, this pill, the banner and the strip name one run.
        label = (
            "between runs"
            if frame.run_index is None
            else f"between runs · run {frame.run_index + 1} ended · {frame.stop_kind}"
        )
        tone = "crit" if frame.stop_kind in ("fault", "limit") else "neutral"
        return f'<span class="pill {tone}" data-state="between-runs">{_e(label)}</span>'
    if frame.stop_kind is None and frame.paused_at is not None:
        return (
            f'<span class="pill warn" data-state="paused">paused · since '
            f"{_clock_time(frame.paused_at)}</span>"
        )
    if frame.stop_kind is None:
        return '<span class="pill ok" data-state="running">running</span>'
    tone = "crit" if frame.stop_kind in ("fault", "limit") else "neutral"
    label = f"ended · {frame.stop_kind}"
    if frame.phase == "awaiting_return":
        label += " · awaiting return"
    elif frame.phase == "closed":
        label += " · returned"
    return f'<span class="pill {tone}" data-state="ended">{_e(label)}</span>'


def _head(frame: Telemetry | None) -> str:
    """Session, subject, deployment, block, trial, and the in-session clock."""
    if frame is None:
        return _NONE
    in_session = (
        "—" if frame.in_session_seconds is None else _clock(frame.in_session_seconds)
    )
    cells = (
        ("Session", _e(frame.session_id), ""),
        ("Subject", _e(frame.subject), ""),
        ("Deployment", _e(frame.deployment), ""),
        ("For", _e(frame.session_kind), ""),
        # Counted from 1, as `_state` says why.
        ("Run", "—" if frame.run_index is None else _e(frame.run_index + 1), ""),
        ("Block", "—" if frame.block is None else _e(frame.block), ""),
        ("Trial", _e(frame.trial_index), f' data-trial="{_e(frame.trial_index)}"'),
        ("In session", in_session, ""),
    )
    return "".join(
        f'<span><span class="k">{name}</span><span class="v"{attr}>{value}</span></span>'
        for name, value, attr in cells
    )


def _bar_nums(frame: Telemetry | None) -> str:
    """**The top bar's numbers** (the console interface design's call: "the top of the page
    becomes one bar that stays in view: state, trial, correct, fluid, cage time and the run's
    buttons"; the layout review's finding 4): the trial, the session's right answers over its
    trials as the strip's first line counts them (`_level`), the fluid given today, and when the
    animal is due back in its cage (`_back_to_cage`) -- each the strip's own figure, so the bar and
    the strip behind *session* never disagree. Nothing before a session: the pill says so."""
    if frame is None:
        return ""
    _, right, percent, _, _ = _level("session", frame.performance.session, "")
    fluid = ('<span class="nm">unknown</span>' if frame.fluid_today_ml is None
             else f'{frame.fluid_today_ml:.2f}<span class="u"> mL</span>')
    _, cage, _, note, tone = _back_to_cage(frame)
    cells = (
        ("trial", _e(frame.trial_index), "", ""),
        ("correct", f"{right} {percent}".strip(), "", ""),
        ("fluid today", fluid, "", ""),
        ("cage", cage, tone, note),
    )
    out = []
    for label, value, tone, note in cells:
        classes = "bn " + tone if tone else "bn"
        title = f' title="{note}"' if note else ""
        out.append(f'<span class="{classes}"{title}><span class="k">{label}</span> <b>{value}</b></span>')
    return " ".join(out)


def _presence(view: View) -> str:
    """This box, or a LAN viewer, and how many LAN viewers there are (spec §4.2)."""
    count = view.lan_viewers
    lan = f"{count} LAN viewer{'' if count == 1 else 's'}"
    who = "this box" if view.on_box else "LAN viewer"
    return f"<b>{who}</b> · {lan}"


# --- the strip --------------------------------------------------------------------


def _who(by: Actor | None) -> str:
    """Who sent a control, as the page shows it (b2b spec §6): a member as *NAME
    (wl.works)*, a box name set apart as *NAME (box, unverified)*, so a typed name
    dressed as a member's still reads as typed; nothing for nobody."""
    if by is None:
        return ""
    if isinstance(by, Member):
        return f'<span class="who-m">{_e(by.name)} <span class="nm">(wl.works)</span></span>'
    return f'<span class="who-b">{_e(by.name)} <span class="nm">(box, unverified)</span></span>'


def _cell(
    label: str,
    value: str,
    *,
    sub: str = "",
    bar: tuple[float, str] | None = None,
    after: str = "",
) -> str:
    """One strip cell. `label` and `sub` are this module's own text; `value` and
    `after` are HTML built from escaped parts."""
    parts = [
        f'<div class="row"><span class="lab">{label}</span>'
        f'<span class="val">{value}</span></div>'
    ]
    if bar is not None:
        width, tone = bar
        parts.append(
            f'<div class="bar" aria-hidden="true">'
            f'<div class="fill {tone}" style="width:{width:.1f}%"></div></div>'
        )
    if sub:
        parts.append(f'<span class="sub">{sub}</span>')
    if after:
        parts.append(after)
    return "<div>" + "".join(parts) + "</div>"


def _lines(rows: list[tuple[str, str, str, str, str]]) -> str:
    """A strip cell's lines: each `(name, value, percent, note, tone)`. `value` is
    HTML built from escaped parts; `tone` is `""`, `"warn"` or `"crit"`."""
    out = []
    for name, value, percent, note, tone in rows:
        hot = f" {tone}" if tone else ""
        out.append(
            f'<span class="k{hot}">{_e(name)}</span><span class="n{hot}">{value}</span>'
            f'<span class="n">{percent}</span><span class="x">{note}</span>'
        )
    return '<div class="lines">' + "".join(out) + "</div>"


def _fluid(frame: Telemetry, view: View) -> str:
    """The strip's first cell (session-levels spec §6): fluid today against the floor
    with its bar, then the supplement, the last reward, and back to cage."""
    floor = f'<span class="u">/ {frame.floor_ml:.2f} mL</span>'
    if frame.fluid_today_ml is None:
        head = f'<span class="nm">unknown</span>{floor}'
        bar = None
    else:
        head = f"{frame.fluid_today_ml:.2f}{floor}"
        tone = "ok" if frame.fluid_today_ml >= frame.floor_ml else ""
        bar = (_pct(frame.fluid_today_ml, frame.floor_ml), tone)
    rows = [_supplement(frame), _reward_line(frame, view), _back_to_cage(frame)]
    return _cell("Fluid today / floor", head, bar=bar, after=_lines(rows))


def _supplement(frame: Telemetry) -> tuple:
    if frame.shortfall_ml is None:
        return (
            "supplement",
            '<span class="nm">unknown</span>',
            "",
            "the day's prior total was not supplied",
            "",
        )
    if frame.shortfall_ml <= 0:
        return ("supplement", '<span class="u">none</span>', "", "floor met", "")
    return (
        "supplement",
        f'{frame.shortfall_ml:.2f}<span class="u"> mL</span>',
        "",
        "to reach the floor",
        "",
    )


def _reward_line(frame: Telemetry, view: View) -> tuple:
    if frame.last_reward_at is None:
        return ("last reward", '<span class="nm">none yet</span>', "", "", "")
    # Ledger Ruling 1 (2026-09-27): the frame's own instant less the reward's, one
    # interval on the session's anchored clock, plus how long `wlx serve` has held the
    # frame, on its steady clock. `frame_age_s` is `None` only before any frame, and
    # a render with a frame and no age is the age as of the frame.
    held = view.frame_age_s or 0.0
    since = frame.wall_at - frame.last_reward_at + held
    # m1: a reward instant that is not a number is stored, not refused (it bounds
    # nothing), so it can arrive here; it is a word, never a crash of every pane.
    age = (
        '<span class="nm">unknown</span>'
        if not math.isfinite(since)
        else _e(_health.ago(since) + " ago")
    )
    return ("last reward", age, "", _e(_per_correct(frame)), "")


def _per_correct(frame: Telemetry) -> str:
    """The reward size the run pays a correct trial (plan ruling 6), or "no run going"."""
    if frame.phase != "running":
        return "no run going"
    for row in frame.params:
        if row.name == "reward_correct" and isinstance(row.value, (int, float)):
            return f"{row.value:.2f} {row.unit} per correct"
    return ""


def _back_to_cage(frame: Telemetry) -> tuple:
    out = frame.out_of_cage_seconds
    if out is None:
        return ("back to cage", '<span class="nm">cage-side</span>', "", "no limit", "")
    if frame.returned_at is not None:
        return (
            "back to cage",
            _e(f"at {_wall_minute(frame.returned_at)}"),
            "",
            _e(f"{_clock(out)} out · recorded"),
            "",
        )
    limit = frame.out_of_cage_limit_s
    if limit is None:
        return ("back to cage", _e(_clock(out)), "", "out · no limit published", "")
    left = limit - out
    tone = (
        "crit"
        if frame.stop_kind == "limit" or left <= 0
        else "warn" if frame.duration_warning else ""
    )
    # Plan ruling 5: display arithmetic on published numbers, like `_pct`.
    when = f"by {_wall_minute(frame.wall_at - out + limit)}"
    note = f"{_clock(out)} out · " + (f"{_clock(left)} left" if left > 0 else "past the limit")
    return ("back to cage", _e(when), "", _e(note), tone)


def _correct_of(counts: Counts) -> tuple[int, int]:
    """The strip's one rollup (PI, 2026-09-26, P4d-2b spec §3): `correct` plus
    `correct_reject`, both the right answer on their trial, over every trial at the
    level, hangs included. The Working? pane and `/health` stay unrolled."""
    correct = counts.outcomes.get(Outcome.CORRECT.value, 0) + counts.outcomes.get(
        Outcome.CORRECT_REJECT.value, 0
    )
    return correct, sum(counts.outcomes.values()) + counts.hangs


def _level(name: str, counts: Counts, note: str, *, none_yet: str | None = None) -> tuple:
    """One level's line. With no trials its value is a dash, never `0 / 0` or `0%`, and
    it keeps its note -- "run 3", "1 run", as session-levels spec §6 and mockup v13 have
    it -- or says `none_yet` in its place where one is given."""
    correct, trials = _correct_of(counts)
    if trials == 0:
        return (name, '<span class="u">—</span>', "", _e(note if none_yet is None else none_yet), "")
    if counts.drummed:
        # **Right first time beside right per presentation** (the PI, 2026-10-18, "Show both"): a
        # trial and its drummed repeats are one trial, so where trials were drummed the line leads
        # with the trials right first time, and its note gives every presentation's figure.
        first, firsts = correct - counts.right_drummed, trials - counts.drummed
        said = (f"right first time; {100.0 * correct / trials:.0f}% per presentation "
                f"({correct} / {trials})")
        return (
            name,
            f'{_e(first)}<span class="u"> / {_e(firsts)}</span>',
            f"{100.0 * first / firsts:.0f}%",
            _e(f"{note} · {said}" if note else said),
            "",
        )
    return (
        name,
        f'{_e(correct)}<span class="u"> / {_e(trials)}</span>',
        f"{100.0 * correct / trials:.0f}%",
        _e(note),
        "",
    )


def _performance(frame: Telemetry, view: View) -> str:
    """The strip's second cell (session-levels spec §6): session, task, this run, this
    block -- or, while no run goes, one line saying so (plan ruling 4)."""
    perf = frame.performance
    # Presentations per minute, drummed tries included, from `trial_index` (`serve`), and said so.
    rate = "" if view.trials_per_min is None else f"{view.trials_per_min:.1f} presentations/min"
    rows = [_level("session", perf.session, rate, none_yet="no trials yet")]
    if perf.run is None:
        said = "between runs" if frame.phase == "between_runs" else "no run going"
        rows.append((said, "", "", "", ""))
    else:
        runs = f"{perf.runs_of_task} run" + ("" if perf.runs_of_task == 1 else "s")
        rows.append(_level(perf.task_name, perf.task, runs))
        rows.append(_level("this run", perf.run, f"run {perf.run_in_session}"))
        if perf.block is None:
            rows.append(("block", '<span class="u">—</span>', "", "", ""))
        else:
            rows.append(
                _level(f"block {perf.block_in_session} · {perf.block_type}", perf.block, "")
            )
    return _cell("Correct / trials", "", after=_lines(rows))


def _gate(view: View, other: str = "") -> str:
    """A control's attributes (the plan's Ruling 7). `other` is its own reason to be
    greyed, or nothing. On the box's page, `other`. On the https page, `other`, or, when
    it has none, greyed until the script holds a sign-in (`data-signin`). Everywhere else,
    greyed saying where controls work."""
    if other and not other.startswith(" disabled"):
        raise ValueError("a control's own reason must grey it: it starts with ' disabled'")
    if view.can_write:
        return other
    if view.signin:
        return other or f' disabled data-signin title="{_e(SIGN_IN_FIRST)}"'
    why = CONTROLS_ELSEWHERE if view.https_page else CONTROLS_AT_THE_BOX
    return f' disabled title="{_e(why)}"'


def _note(view: View) -> str:
    """The words beside a control bar greyed away from where controls work: nothing on
    the box's page, and nothing on the https page, whose header says it."""
    if view.can_write or view.signin:
        return ""
    why = CONTROLS_ELSEWHERE if view.https_page else CONTROLS_AT_THE_BOX
    return f'<span class="nm">{why}</span>'


def _scheduled(frame: Telemetry, view: View) -> str:
    """The strip's third cell, while a scheduled stop is held (spec §5.2): *stop at
    14:30 · set by jake*, in the rig's own words, with a cancel button."""
    stop = frame.scheduled_stop
    cancel = (
        f'<button type="button" class="btn small" data-cmd="cancel"{_gate(view)}>'
        f"cancel</button>"
    )
    return _cell("Scheduled", f"stop {_e(stop.said)}", sub=f"set by {_who(stop.by)} {cancel}")


def _strip(frame: Telemetry | None, view: View) -> str:
    if frame is None:
        return _cell("Fluid today / floor", _NONE) + _cell("Correct / trials", _NONE)
    return (
        _fluid(frame, view)
        + _performance(frame, view)
        # Only while the session runs: since Task 8's fix, `Telemetry.of` sends
        # `scheduled_stop=None` once `stopped_because` is set, so an ended session's
        # frame should never carry one. This guard defends against a frame the rig
        # no longer sends, not a schedule it still carries.
        + (
            _scheduled(frame, view)
            if frame.scheduled_stop is not None and frame.stop_kind is None
            else ""
        )
    )


# --- banners ----------------------------------------------------------------------


def _banner(tone: str, tag: str, text: str) -> str:
    return (
        f'<div class="banner {tone}"><span class="tag">{tag}</span>'
        f"<span>{text}</span></div>"
    )


def _resumed_sentence(resumed_at: float) -> str:
    """What a resumed session says of itself (XC-026), in the banner and the closed
    summary, at the resume's instant as this host's `HH:MM`."""
    return f"this session was resumed after its process stopped, at {_wall_minute(resumed_at)}"


def _aids_banner(frame: Telemetry) -> str:
    """The standing warning while a training aid is on and the run goes (the PI, 2026-10-18: "a
    warning that training aids are on in the console"; outside a training session, "Allow it, with
    a warning"): drumming, a block's or a trainer's, and *clear*, as the scheduler lists them
    (`Telemetry.aids`, never recomputed here: the controller's smaller ruling). Every trial's row
    marks them."""
    on = list(frame.aids)
    if not on or frame.phase != "running" or frame.stop_kind is not None:
        return ""
    aids = " and ".join(on)
    if frame.session_kind == "training":
        return _banner("info", "Training aid", _e(f"{aids} on: the record marks every trial"))
    return _banner("warn", "Training aid", _e(
        f"{aids} on in a {frame.session_kind} session, though training aids are meant for "
        f"training sessions: the record marks every trial"))


def _eased_banner(frame: Telemetry) -> str:
    """**The standing line while a person's change keeps trials out of moving up** (the engine C3
    plan's engineering review, I-2, and its science review, I-4: a trainer who widened a window
    sees a perfect streak and a block that will not end, and is left guessing why): the settings
    the rig names (`Telemetry.eased`, never recomputed here), and the ways back -- *hand back* on
    a card, the range as the task writes it, or *revert*. The changes feed said it once a block;
    this stands while it lasts."""
    if not frame.eased:
        return ""
    return _banner("warn", "Not counting", _e(
        f"trials are not counting toward moving up: a person changed {', '.join(frame.eased)}; "
        f"hand each back, or send its range as the task writes it, or revert, to count them "
        f"again"))


def _banners(frame: Telemetry | None, view: View) -> str:
    """A refused frame first, then the duration warning and the stop reason -- where
    a person looks when something is wrong. The stream's own banner (stale, lost) is
    the page script's, in its own element.

    **With no frame, *Waiting* only when nothing was refused either** (Ruling 11,
    2026-09-27): a refused frame is a session publishing in a form this console
    cannot read, so a sentence saying nothing had arrived would be false beside it."""
    out = []
    if view.rejected:
        out.append(_banner("crit", "Refused", _e(view.rejected)))
    if frame is None:
        if view.rejected:
            return "".join(out)
        out.append(
            _banner(
                "info",
                "Waiting",
                f"no telemetry yet: no frame has arrived on {_e(view.endpoint)}",
            )
        )
        return "".join(out)
    if frame.duration_warning:
        tone = "crit" if frame.stop_kind == "limit" else "warn"
        out.append(_banner(tone, "Warning", _e(frame.duration_warning)))
    if frame.question is not None:
        out.append(_question_banner(frame.question, view))
    if frame.resumed_at is not None:
        out.append(_banner("info", "Resumed", _e(_resumed_sentence(frame.resumed_at))))
    out.append(_aids_banner(frame))
    out.append(_eased_banner(frame))
    if frame.stopped_because:
        tone = "crit" if frame.stop_kind in ("fault", "limit") else "info"
        tag = (
            # Counted from 1, as `_state` says why.
            f"Run {frame.run_index + 1} ended"
            if frame.phase == "between_runs" and frame.run_index is not None
            else "Ended"
        )
        out.append(_banner(tone, tag, _e(frame.stopped_because)))
    return "".join(out)


# --- the run's task and its pre-flight (P4d-2b b3a-2) ------------------------------


def _plans(frame: Telemetry | Idle | None) -> str:
    """The plan picker's options (engine build C2b; the PI, 2026-10-19, "Preselect first, keep
    plain"): the plans the shown pre-flight's task declares, in order, then the plain run, one
    more labeled choice; the plan the pre-flight was taken for selected, so a wrong one shows. Each
    names the task it is for (`data-for`): the page's script preselects a task's first plan once
    that task's own plans arrive with its pre-flight. No pre-flight shown, the plain run alone --
    but while a plan runs, that run's plan, so the bar never reads the plain run's label over a
    plan's run. Only while it runs: between runs the frame still carries the last run's plan
    (`Session.plan`, "the run in progress, or the last one"), not what the next run plays.
    That last plan is what a session's second and later runs preselect (the PI, 2026-10-22, "The
    plan last run"): the option for it, when the frame's last run was of this pre-flight's task,
    is marked `data-last` -- the plain run's too, when the last run was plain, which is then
    repeated -- and a frame with no run yet (`run_index` is `None`), the first run's, marks
    none."""
    preflight = None if frame is None or isinstance(frame, Idle) else frame.preflight
    if preflight is None:
        if (frame is not None and not isinstance(frame, Idle) and frame.plan is not None
                and frame.phase == "running" and frame.stop_kind is None):
            return f'<option value="{_e(frame.plan)}" selected>plan {_e(frame.plan)}</option>'
        return f'<option value="">{_e(PLAIN_RUN)}</option>'
    task = _e(preflight.task)
    # The frame's task is the run's file path, the pre-flight's the name the page offered it by.
    ran = (frame.run_index is not None and frame.task is not None
           and PurePath(frame.task).name == preflight.task)

    def option(value: str, label: str) -> str:
        chosen = " selected" if (preflight.plan or "") == value else ""
        again = " data-last" if ran and (frame.plan or "") == value else ""
        return f'<option value="{_e(value)}" data-for="{task}"{again}{chosen}>{_e(label)}</option>'

    return "".join(option(name, f"plan {name}") for name in preflight.plans) + option("", PLAIN_RUN)


def _options(names, none: str, choose: str | None = None) -> str:
    """A select's options, one per name, or one empty option saying why there is none.
    A frame re-renders them; the page's script keeps the option a person chose (the
    b3a-2 plan, decision 11). With `choose`, an empty option saying it comes first, so
    nothing is chosen until a person chooses: the *New session* dialog's subject, which
    had silently become the first animal once the last session closed (the b3a-2 final
    review, I1)."""
    if not names:
        return f'<option value="">{_e(none)}</option>'
    first = "" if choose is None else f'<option value="">{_e(choose)}</option>'
    return first + "".join(f'<option value="{_e(name)}">{_e(name)}</option>' for name in names)


def _pf_state(frame: Telemetry | Idle | None) -> tuple[str, str]:
    """The pre-flight pill's tone and words (the mockup's `drawPreflight`), from the
    frame's pre-flight: a fail counts first, then the unknowns a person acknowledges --
    an item that is neither pass nor unknown counts as a fail, as `preflight.gate`
    counts it -- and outside a `wlx taskd` session between runs, why there is none. An
    unknown accepted earlier this session is carried, not counted (the engine B plan, call 30)."""
    if frame is None or isinstance(frame, Idle):
        return "neutral", "no session"
    if not frame.service:
        return "neutral", "pre-flight · wlx run takes none"
    if frame.phase == "running":
        return "neutral", "pre-flight · taken as the run started"
    if frame.phase != "between_runs":
        return "neutral", "pre-flight · the session has ended"
    if frame.preflight is None:
        return "neutral", "pre-flight · not taken"
    items = frame.preflight.items
    fails = sum(1 for item in items if item.result not in ("pass", "unknown"))
    carried = _accepted(frame)
    unknown = sum(
        1 for item in items if item.result == "unknown" and (item.name, item.said) not in carried
    )
    if fails:
        return "crit", f"pre-flight · {fails} fail"
    if unknown:
        return "warn", f"pre-flight · {unknown} to acknowledge"
    return "ok", "pre-flight ✓"


def _pf_sum(frame: Telemetry | Idle | None) -> str:
    """The Setup tab's pre-flight pill (the mockup's `pf-sum`)."""
    tone, said = _pf_state(frame)
    return f'<span class="pill {tone}">{_e(said)}</span>'


def _pf_pill(frame: Telemetry | Idle | None, view: View) -> str:
    """The control bar's pre-flight pill (the mockup's `pf-pill`): between runs, a button
    that takes the pre-flight for the task chosen and opens the Setup tab at its panel
    (the b3a-2 plan, decision 7); otherwise the words alone."""
    if isinstance(frame, Telemetry) and frame.service and frame.phase == "between_runs":
        tone, said = _pf_state(frame)
        # Greyed like any control, with this title when nothing else is said (a title
        # alone would leave it enabled on the https page before a sign-in).
        off = _gate(view) or ' title="take the pre-flight for the task chosen"'
        return (
            f'<button type="button" class="pill {tone}" data-cmd="check"{off}>'
            f"{_e(said)}</button>"
        )
    return _pf_sum(frame)


#: A result's dot (the mockup's `.st`): an unknown is what nothing measured, which the
#: mockup draws as the hollow *untested* ring; anything but pass or unknown is a fail.
_DOTS = {"pass": "pass", "unknown": "untested"}


def _pf_row(item, view: View, accepted: dict | None = None) -> str:
    """One pre-flight item: its dot, name and sentence, and -- for an unknown -- the box
    that acknowledges it, carrying its exact name and never ticked here (decision 9); for
    one the session accepted at an earlier run, who accepted it instead of a box."""
    earlier = (accepted or {}).get((item.name, item.said)) if item.result == "unknown" else None
    if earlier is not None:
        # Carried from an earlier run of this session (the engine B plan, call 30): who
        # accepted it and when, and no box, since it needs no new acknowledgement.
        acknowledge = (
            f'<span class="sub">accepted earlier this session'
            f'{"" if earlier.by is None else " by " + _who(earlier.by)} at '
            f"{_e(_clock_time(earlier.at))}</span>"
        )
    elif item.result == "unknown":
        acknowledge = (
            f'<label class="chk"><input type="checkbox" data-ack="{_e(item.name)}" '
            f'aria-label="acknowledge {_e(item.name)}"{_gate(view)}> acknowledge</label>'
        )
    else:
        acknowledge = "<span></span>"
    return (
        f'<div class="row"><span class="st {_DOTS.get(item.result, "fail")}" '
        f'title="{_e(item.result)}"></span><span>{_e(item.name)}</span>'
        f'<span class="val">{_e(item.said)}</span>{acknowledge}</div>'
    )


def _preflight_pane(frame: Telemetry | Idle | None, view: View) -> str:
    """The Setup tab's pre-flight (the mockup's `pf-panel`, drawn from `wlx taskd`'s items
    rather than the mockup's list: spec §6.2): one row per item, under a line naming the
    task and S9a §10's rule. The mockup's *must* tag is left out, since every fail blocks
    (the b3a-2 plan, decision 6). **No "unplanned run" warning**: the PI retired that
    ruling on 2026-10-01, through wl-works (P4d-2b spec §4.0), and every run is a run."""
    if frame is None or isinstance(frame, Idle):
        return _NONE
    if not frame.service:
        return '<span class="nm">wlx run takes no pre-flight (XC-159)</span>'
    if frame.phase == "running":
        return (
            '<span class="nm">a run is in progress: its pre-flight was taken as it '
            "started, and its start row in runs.jsonl holds it</span>"
        )
    if frame.phase != "between_runs":
        return '<span class="nm">the session has ended: no run starts in it</span>'
    if frame.preflight is None:
        return (
            '<span class="nm">not taken: choose a task, or press the pre-flight '
            "pill</span>"
        )
    task = _e(frame.preflight.task)
    # The plan it was taken for (engine build C2b): a wrong one shows here and in the start row.
    plan = ("the plain run" if frame.preflight.plan is None
            else f"plan {_e(frame.preflight.plan)}")
    carried = _accepted(frame)
    rows = "".join(_pf_row(item, view, carried) for item in frame.preflight.items)
    return (
        f'<div class="sub">for {task} · {plan} · a fail blocks the run; each unknown starts it '
        "only on your acknowledgement, by name, written into runs.jsonl</div>"
        f'<div class="pf" data-task="{task}">{rows}</div>'
        + _run_start(frame.preflight, view)
    )


def _run_start(preflight, view: View) -> str:
    """**Where the run starts, picked at its start** (the pop-out search build's Task 6; its
    design §3.5, the PI's sketch of the trainer's screen: "at the day's start, the stage, the
    staircase's starting level and the pairings to pick, with yesterday's end shown"): the plan's
    stage to start at (`start-block`; the first sends none), each stage's staircase level where its
    task declares none -- shown only for the stage picked -- and the pool's pairings, ticked as the
    run would start; the page's script sends only what a person changed from that, as the start's
    values (`startRun`). Then the animal's previous session's end of this plan, as its record left
    it: shown, never carried (§3.6). **A resumed session's run that goes on from the run its
    process stopped in** (`Preflight.continues`) shows what it comes back with in their place,
    since it starts there."""
    parts = []
    if preflight.continues is not None:
        parts.append('<div class="row" id="continues"><span>goes on</span>'
                     f'<span class="val">{_e(preflight.continues)}</span></div>')
    else:
        stages = preflight.stages
        if len(stages) > 1:
            picked = preflight.start_block or stages[0].name
            options = "".join(
                f'<option value="{_e(stage.name)}"{" selected" if stage.name == picked else ""}>'
                f"{_e(stage.name)}</option>" for stage in stages)
            parts.append('<label class="row"><span>stage</span><select id="start-block" '
                         f'aria-label="the stage the run starts at"{_gate(view)}>{options}'
                         "</select></label>")
        for stage in stages:
            if stage.setting is None or not stage.levels:
                continue
            at = stage.levels[stage.start or 0]
            if stage.declared:
                parts.append(f'<div class="row" data-stage="{_e(stage.name)}">'
                             f"<span>{_e(stage.setting)} in {_e(stage.name)}</span>"
                             f'<span class="val">starts at {_rung(at)}, as its task declares'
                             "</span></div>")
                continue
            options = "".join(
                f'<option value="{_rung(level)}"{" selected" if level == at else ""}>'
                f"{_rung(level)}</option>" for level in stage.levels)
            parts.append(f'<label class="row" data-stage="{_e(stage.name)}">'
                         f"<span>{_e(stage.setting)} in {_e(stage.name)}</span>"
                         f'<select data-start-setting="{_e(stage.setting)}" '
                         f'data-default="{_rung(at)}" aria-label="{_e(stage.setting)} at the start"'
                         f"{_gate(view)}>{options}</select></label>")
        pool = preflight.pool
        if pool is not None:
            # The pool the run would start with, ticked; none where it has no whole number.
            start = (int(pool.start) if isinstance(pool.start, (int, float))
                     and not isinstance(pool.start, bool) and math.isfinite(pool.start)
                     and float(pool.start).is_integer() and pool.start >= 0 else 0)
            boxes = "".join(
                f'<label class="chk"><input type="checkbox" data-pairing="{1 << at}"'
                f'{" checked" if start >> at & 1 else ""} aria-label="pairing {_e(name)}"'
                f"{_gate(view)}> {_e(name)}</label>" for at, name in enumerate(pool.pairings))
            parts.append(f'<div class="row" data-pool-row="{_e(pool.setting)}" '
                         f'data-default="{start}"><span>pairings</span>{boxes}</div>')
        if stages or pool is not None:
            parts.append('<div class="sub" id="previous-end">'
                         + ("the previous session: " + _e(preflight.previous)
                            if preflight.previous is not None
                            else "no previous session of this animal ran this plan")
                         + "</div>")
    if not parts:
        return ""
    return '<div class="pf" id="run-start">' + "".join(parts) + "</div>"


def _rung(value: object) -> str:
    """A staircase's level as the start form shows and sends it: a number as Python's `g`."""
    return f"{value:g}" if isinstance(value, (int, float)) else str(value)


def _warning_row(row) -> str:
    """One warning: its code and sentence, the kinds it is accepted in, and who accepted it
    and when -- nothing for one an open has yet to ask; a chaired session's says so. One no
    kind accepts is marked so and carries no `data-warn`, so no form can send it as accepted:
    the rig lists none since XC-352's E1 and E2 (2026-10-11), which made a calibration that will
    not load or is dated after today, the engine B plan's calls 19 and 21, a warning every kind
    accepts. And a row saying the warnings could not be listed (`UNLISTED`, calls 27 and 31) is
    said as that, being no warning."""
    if row.code == UNLISTED and not row.accepted_in:
        return (
            f'<div class="row" data-unlisted=""><span>{_e(row.code)}</span>'
            f'<span class="val">{_e(row.detail)}</span>'
            '<span class="sub">could not be listed</span></div>'
        )
    if not row.accepted_in:
        return (
            f'<div class="row" data-refused="{_e(row.code)}"><span>{_e(row.code)}</span>'
            f'<span class="val">{_e(row.detail)}</span>'
            '<span class="sub">no session kind accepts this: every run\'s pre-flight fails on it</span></div>'
        )
    kinds = ", ".join(row.accepted_in)
    who = "" if row.by is None else f" · accepted by {_who(row.by)} at {_e(_clock_time(row.at))}"
    only = " · a chaired session's" if row.code == HEAD_FREE and row.by is None else ""
    return (
        f'<div class="row" data-warn="{_e(row.code)}" data-detail="{_e(row.detail)}" '
        f'data-kinds="{_e(" ".join(row.accepted_in))}"><span>{_e(row.code)}</span>'
        f'<span class="val">{_e(row.detail)}</span>'
        f'<span class="sub">accepted in {_e(kinds)}{only}{who}</span></div>'
    )


def _warnings_pane(frame: Telemetry | Idle | None) -> str:
    """The Warnings tab (engine spec §3.1, §19): the session's accepted warnings, or, with none
    open, what an open asks to accept."""
    if frame is None:
        return _NONE
    rows = "".join(_warning_row(row) for row in frame.warnings)
    if isinstance(frame, Idle):
        return ('<div class="sub">no session open · an open asks to accept these, once, for the '
                'session</div>' + (rows or '<span class="nm">nothing</span>'))
    return (f'<div class="sub">a {_e(frame.session_kind)} session · each accepted once, for the '
            "session; a new one is asked in the next run's pre-flight</div>"
            + (rows or '<span class="nm">none accepted yet</span>'))


def _dn_warnings(frame: Idle, view: View) -> str:
    """The *New session* dialog's warnings, and the one box that accepts those the chosen
    kind accepts (`acceptedWarnings` sends each with its sentence: the engine B plan, call
    25). The box is drawn only when a row can be accepted -- one a kind accepts, and not the
    row saying the list could not be made (D7): a box that accepts nothing would read as
    accepting something."""
    if not frame.warnings:
        return '<span class="nm">no warnings to accept</span>'
    rows = "".join(_warning_row(row) for row in frame.warnings)
    if not any(row.accepted_in and row.code != UNLISTED for row in frame.warnings):
        return rows
    return (rows + f'<label class="chk"><input type="checkbox" id="dn-accept"{_gate(view)}> '
            "accept these warnings for this session</label>")


def _accepted(frame: Telemetry) -> dict:
    """The session's accepted warnings by code and sentence, for the pre-flight's rows: an
    unknown among them was accepted at an earlier run and is carried (engine spec §20.1;
    the engine B plan, call 30)."""
    return {(row.code, row.detail): row for row in frame.warnings}


# --- the controls (P4d-2b b2a) ------------------------------------------------------


def _hand_reward_now(frame: Telemetry) -> bool:
    """Whether the rig gives a manual reward now (`taskd.Session._manual_reward`): a run
    held paused (PI, 2026-09-28), or a `wlx taskd` session between runs or awaiting its
    animal's return (PI, 2026-09-29, spec §6.0). During a trial it waits on XC-157, and
    after a `wlx run` session's run on XC-184."""
    return frame.paused_at is not None or (
        frame.service and frame.phase in ("between_runs", "awaiting_return")
    )


def _reward_button(frame: Telemetry, view: View) -> str:
    """The manual reward's button (PI, 2026-09-28 and 2026-09-29): live whenever the rig
    gives one (`_hand_reward_now`), and greyed with `REWARD_ONLY_PAUSED` while a run's
    trials run, and with the §2 sentence away from the box. **One button and no key**:
    a click is one command, and the script holds the button until that command's
    answer."""
    live = _hand_reward_now(frame)
    off = _gate(view, "" if live else f' disabled title="{_e(REWARD_ONLY_PAUSED)}"')
    return f'<button type="button" class="btn" data-cmd="reward"{off}>give reward</button>'


def _reward_answer(frame: Telemetry) -> str:
    """Beside a live *give reward*, what became of the last press (PI, 2026-09-28), from
    the frames the rig publishes: the session's fluid total, the newest reward given with
    its size and where, and the newest press refused with the rig's sentence -- *last*,
    since a refusal carries no time, as on a parameter card. Nothing while the button is
    greyed."""
    if not _hand_reward_now(frame):
        return ""
    said = [f"fluid session {frame.fluid_session_ml:.2f} mL"]
    given = [control for control in frame.controls if control.kind == "reward"]
    if given:
        said.append(f"last given {_clock_time(given[-1].at)}: {_e(given[-1].said)}")
    refused = [refusal for refusal in frame.refusals if refusal.name == "reward"]
    if refused:
        said.append(f"last refused: {_e(refused[-1].why)}")
    return f'<span class="nm">{" · ".join(said)}</span>'


def _mark_button(view: View) -> str:
    """*mark (M)*: greyed on its own when this console has no mark endpoint."""
    off = _gate(view, "" if view.can_mark else f' disabled title="{_e(NO_MARK_ENDPOINT)}"')
    return f'<button type="button" class="btn" data-cmd="mark"{off}>mark (M)</button>'


def _start_button(frame: Telemetry, view: View) -> str:
    """*start run* (the mockup's `a-start`), carrying the task of the pre-flight the frame
    shows: the page's script sends that task, and only while it is the one chosen (the
    b3a-2 plan, decision 8). Greyed, with the reason, until a pre-flight is shown with no
    item failing (spec §6.2); `Service._start` takes the pre-flight again and refuses a
    start it would block anyway."""
    preflight = frame.preflight
    if preflight is None:
        why = "take the pre-flight first: choose a task, or press the pre-flight pill"
    else:
        failing = [i.name for i in preflight.items if i.result not in ("pass", "unknown")]
        why = f"pre-flight: {', '.join(failing)} failing" if failing else None
    task = "" if preflight is None else preflight.task
    # The plan it was taken for, which the script sends with it (engine build C2b).
    plan = "" if preflight is None or preflight.plan is None else preflight.plan
    off = _gate(view, "" if why is None else f' disabled title="{_e(why)}"')
    return (
        f'<button type="button" class="btn go" data-cmd="start" data-task="{_e(task)}" '
        f'data-plan="{_e(plan)}"{off}>start run</button>'
    )


#: The service's own commands, which a person sends from the page's forms (P4d-2b spec
#: §6.2): the newest refusal of one is shown beside the controls (`_session_refused`).
SESSION_COMMANDS = ("open", "check", "start", "end")


def _session_refused(refusals) -> str:
    """The newest refusal of an open, a check, a start or an end, with the rig's sentence,
    for the always-visible control bar: a start refused on the Setup tab, or a return on
    the End tab, showed only in the Runtime tab's feed, where the person was not (the
    b3a-2 final review, I3; `serve.SERVICE_SENT` promises the page shows a refusal with its
    reason). *Last*, and drawn as a reward's refusal is (`_reward_answer`), since a refusal
    carries no time (XC-113): it stays after a later command succeeds, so it reads as the
    last one, not as an alarm about the one just sent."""
    refused = [refusal for refusal in refusals if refusal.name in SESSION_COMMANDS]
    if not refused:
        return ""
    last = refused[-1]
    return f'<span class="nm">last refused · {_e(last.name)}: {_e(last.why)}</span>'


def _outside_a_run(frame: Telemetry, view: View) -> str:
    """A `wlx taskd` session between runs or awaiting its animal's return (spec §6.0,
    §6.2): *start run* between runs, and *give reward* and *mark* in both, since the rig
    gives a hand reward and stamps a mark outside a run (the b3a-2 plan, decision 13).
    Pause and stop have no run to act on. Nothing beside *start run* warns of an
    unplanned run: the PI retired that ruling on 2026-10-01 (P4d-2b spec §4.0)."""
    # Concatenated, not an f-string: an apostrophe inside a replacement field of a
    # single-quoted f-string is a syntax error before Python 3.12, and 3.11 is supported.
    lead = (
        _start_button(frame, view)
        if frame.phase == "between_runs"
        else '<span class="nm">'
        + _e("session ended · waiting for the animal's return")
        + "</span>"
    )
    note = _note(view)
    return (
        lead + _reward_button(frame, view) + _mark_button(view) + _reward_answer(frame)
        + _session_refused(frame.refusals) + note
    )


def _controls(frame: Telemetry | None, view: View) -> str:
    """Pause or resume, mark, give reward, and stop (spec §5.2), while a run runs; and,
    since P4d-2b b3a-2, *start run*, *give reward* and *mark* outside a run in a `wlx
    taskd` session (`_outside_a_run`).

    **Pause or resume by the session's state**, never a toggle: the page sends what
    the button says, and the click handler's `toggleAllowed` stops a double click
    from sending it twice, as `rewardAllowed` does for a reward (R2, 2026-09-28).
    **Stop run** (the mockup's `a-stop`; b2a's *stop…*) opens the page's confirm step.
    **Mark** is greyed on its own when this console has no mark endpoint, and **give
    reward** while trials run (`_reward_button`). **Everywhere but the box**, every
    control is greyed with the §2 sentence, which is also said beside them."""
    if frame is None:
        return '<span class="nm">controls · no session</span>'
    if frame.service and frame.phase in ("between_runs", "awaiting_return"):
        return _outside_a_run(frame, view)
    if frame.stop_kind is not None:
        return '<span class="nm">controls · the session has ended</span>'
    off = _gate(view)
    cmd, label = ("resume", "resume (P)") if frame.paused_at is not None else ("pause", "pause (P)")
    note = _note(view)
    return (
        f'<button type="button" class="btn" data-cmd="{cmd}"{off}>{label}</button>'
        f"{_mark_button(view)}"
        f"{_reward_button(frame, view)}"
        f'<button type="button" class="btn danger" data-cmd="stop"{off}>stop run</button>'
        f"{_reward_answer(frame)}{note}"
    )


# --- runtime ------------------------------------------------------------------------


def _trials(frame: Telemetry | None) -> str:
    """The last outcomes as ticks, oldest first, colored by family, with a legend."""
    if frame is None:
        return _NONE
    recent = frame.recent_outcomes
    blanks = '<span class="tk"></span>' * max(0, RECENT_OUTCOMES - len(recent))
    ticks = "".join(
        f'<span class="tk f-{_health.family_key(outcome)}" title="{_e(outcome)}"></span>'
        for outcome in recent
    )
    legend = "".join(
        f'<span><i class="tk f-{key}"></i>{label}</span>' for key, label in LEGEND
    )
    return (
        f'<div class="sub">the last {len(recent)} of {_e(frame.trial_index)} presentations, '
        f"oldest first</div>"
        f'<div class="ticks">{blanks}{ticks}</div><div class="legend">{legend}</div>'
    )


def _fluid_and_supplement(frame: Telemetry) -> str:
    """Fluid session and the supplement: welfare-load-bearing, never dropped. (Named
    apart from the strip's `_fluid`, its first cell, since the session-levels spec §6.)"""
    supplement = (
        f'<span class="nm">{_UNKNOWN_DAY}</span>'
        if frame.shortfall_ml is None
        else f'<span class="num">{frame.shortfall_ml:.2f} mL</span>'
    )
    return (
        f'<div class="kv"><span>fluid session</span>'
        f'<span class="num">{frame.fluid_session_ml:.2f} mL</span></div>'
        f'<div class="kv"><span>supplement owed</span>{supplement}</div>'
    )


def _work(frame: Telemetry | None) -> str:
    """Total trials, then every outcome that occurred with its count, by family, and
    no rollup -- `health.families`, so this and `/health` agree (spec §3)."""
    if frame is None:
        return _NONE
    groups = "".join(
        f'<div class="fam"><h3>{_e(label)}</h3>'
        + "".join(
            f'<div class="kv"><span>{_e(name)}</span>'
            f'<span class="num">{_e(count)}</span></div>'
            for name, count in rows
        )
        + "</div>"
        for _, label, rows in _health.families(frame.outcomes)
    )
    hangs = (
        f'<div class="fam"><h3>Hangs</h3><div class="kv"><span>hangs</span>'
        f'<span class="num">{_e(frame.hangs)}</span></div></div>'
    )
    # **Trials, and the presentations beside them where they differ** (the PI, 2026-10-18: "The
    # console would show both"; the controller's ruling I1): a trial and its drummed repeats one.
    beside = (f" · {_e(frame.trial_index)} presentations" if frame.trials != frame.trial_index
              else "")
    return (
        f'<div class="selrow"><span class="big">{_e(frame.trials)}</span>'
        f'<span class="unit">trials{beside}</span></div>'
        f'<div class="counts">{groups}{hangs}</div>{_fluid_and_supplement(frame)}'
    )


#: The drumming switches, each scope's label (`scheduler.DRUM_SCOPES`; the PI, 2026-10-11).
DRUM_SWITCHES = (("block", "drum this block"), ("run", "drum this run"), ("off", "stop drumming"))

#: Why a repeat limit forgave a condition's debt, as the pane says it (engine spec §16.6), and
#: since engine build C2b what a block's time left owed (the PI, 2026-10-19: "recorded as not
#: run, 'time ran out'").
_FORGIVEN = {
    "cap": "possible avoidance: its failed repeats in a row reached its limit",
    "rig": ("its repeat limit was reached with tries the rig lost (a lost tracker or a fault): not "
            "flagged as avoidance"),
    "time": "not run: its block's time ran out",
    # Whose time ran out, said (the engine C2b plan's science review, I3).
    "run_time": "not run: the run's time ran out",
}


def _left(seconds: float) -> str:
    """Seconds of trials left, as minutes and seconds."""
    whole = int(seconds)
    return f"{whole // 60}:{whole % 60:02d}"


def _plan_row(frame: Telemetry, view: View) -> str:
    """The run's plan (engine build C2b): its name, the open block and the one its plan goes on
    to, the time left before the block's and the run's limits, a pause not counting (the PI,
    2026-10-19), and *next block* and *back one* (the PI, 2026-10-19, "'Next' and 'back one'":
    "Both directions by hand, each recorded with who"), *next block* greyed, saying why, at the
    plan's last block. The rig refuses *back one* at the run's first block, saying so. And how
    often a training progression fell back a stage (the plan's science review, I2)."""
    said = [f"plan {frame.plan}", f"block {frame.block}"]
    if frame.block_left_s is not None:
        said.append(f"{_left(frame.block_left_s)} of the block's time left")
    if frame.run_left_s is not None:
        said.append(f"{_left(frame.run_left_s)} of the run's time left")
    said.append(f"next: {frame.next_block}" if frame.next_block is not None
                else "the plan's last block")
    if frame.fell_back:
        # How often the plan moved the animal back a stage (the plan's science review, I2).
        said.append("fell back once" if frame.fell_back == 1
                    else f"fell back {frame.fell_back} times")
    nothing = ("" if frame.next_block is not None
               else ' disabled title="this block is the last its plan gives"')
    return (
        f'<div class="kv wrap"><span class="nm">{_e(" · ".join(said))}</span>'
        f'<button type="button" class="btn" data-cmd="next_block"{_gate(view, nothing)}>'
        f"next block</button>"
        f'<button type="button" class="btn" data-cmd="back_block"{_gate(view)}>back one</button>'
        f"</div>"
    )


def _counted(row: ConditionRow) -> str:
    """One condition's counts (the PI, 2026-10-18): its trials, a trial and its drummed repeats
    one, and presentations; right and wrong answers and percent right first time; repeats placed;
    trials moved past, with the possible-avoidance flag; drummed tries; and the failed run of its
    trial being drummed now. What it owes is on its line above."""
    first = f"{100.0 * row.right_first / row.trials:.0f}%" if row.trials else "—"
    moved = f"{row.moved_past} moved past" + (" (possible avoidance)" if row.possible_avoidance
                                              else "")
    said = [f"{row.trials} trials", f"{row.presentations} presentations", f"{row.right} right",
            f"{row.wrong} wrong", f"{first} right first time", f"{row.repeats} repeats", moved,
            f"{row.drummed} drummed"]
    if row.failing:
        said.append(f"failing {row.failing} in a row")
    return f'<div class="kv"><span class="nm">{_e(" · ".join(said))}</span></div>'


def _need(frame: Telemetry | None, view: View) -> str:
    """Still needed (engine spec §16.6): every condition of the open block with what it still owes
    (`scheduler.owed`) and, beneath it, its counts (`_counted`); beside each owing any, while a run
    runs, the training aid *clear* is on (`clearing`; the PI, 2026-10-18) and a trial of the block
    can be owed (`clearable`), *clear one* (the PI, 2026-10-11: "there should be some way in the
    console to manually advance beyond or clear a specific trial in the count") and, owing more
    than one, *clear the rest* (the engine C2a plan's science review, D5); then the run's
    shortfalls, a repeat limit's flagged as possible avoidance or named for the rig, a clear's with
    who cleared it; then, while a run runs, drumming and its switches (the PI, 2026-10-11), and the
    training switches: *clear* on or off, and how a percentage counts drummed answers. While a plan
    runs the pane leads with the plan's row (`_plan_row`), and a block past its targets says what it
    draws until -- its criterion, its number of trials or both -- or, once a training progression's
    top stage has passed, that it keeps working (engine build C2b)."""
    if frame is None:
        return _NONE
    live = frame.phase == "running" and frame.stop_kind is None
    counted = {row.condition: row for row in frame.conditions}

    def clears(condition: str, count: int) -> str:
        if not (live and frame.clearing and frame.clearable and count):
            return ""
        name, off = _e(condition), _gate(view)
        one = (f'<button type="button" class="btn" data-cmd="clear" data-condition="{name}"{off}>'
               f"clear one</button>")
        rest = (f'<button type="button" class="btn" data-cmd="clear" data-condition="{name}" '
                f'data-rest="1"{off}>clear the rest</button>')
        return one + (rest if count > 1 else "")

    rows = []
    for condition, count in frame.owed.items():
        rows.append(f'<div class="kv"><span class="mono">{_e(condition)}</span>'
                    f'<span class="num">{_e(count)}</span>{clears(condition, count)}</div>')
        if condition in counted:
            rows.append(_counted(counted[condition]))
    rows = rows or ['<span class="nm">nothing still needed</span>']
    if live and frame.plan is not None:
        rows.insert(0, _plan_row(frame, view))
    if live and frame.passed_at is not None:
        # A training progression's top stage passed, its animal working on (the PI, 2026-10-19,
        # "Same, but top keeps going"; the plan's science review, I1).
        rows.append(f'<div class="kv"><span class="nm">top stage passed at trial '
                    f'{_e(frame.passed_at)}; keeps working</span></div>')
    elif live and frame.past_targets:
        # Past its targets nothing is owed, and every condition comes until what else ends the
        # block is met: its criterion, its number of trials, or both (the PI, 2026-10-18; the
        # plan's science review, I1).
        until = " and ".join(said for said, on in (
            ("the criterion is met", frame.rule is not None),
            (f"{frame.trials_to_run} trials are run", frame.trials_to_run is not None)) if on)
        rows.append(f'<div class="kv"><span class="nm">every target used up: drawing until '
                    f'{_e(until or "its rule is met")}</span></div>')
    for short in frame.shortfalls:
        why = (f"cleared by {_who(short.by)}" if short.because == "cleared"
               else _FORGIVEN.get(short.because, _e(short.because)))
        rows.append(
            f'<div class="kv"><span class="mono keep">{_e(short.condition)}</span>'
            f'<span class="nm">{_e(short.trials)} short in {_e(short.block)} · {why}</span></div>'
        )
    if live:
        now = {"block": "drumming this block", "run": "drumming this run"}.get(
            frame.drumming, "not drumming")
        switches = "".join(
            f'<button type="button" class="btn" data-cmd="drum" data-scope="{scope}"{_gate(view)}>'
            f"{label}</button>"
            for scope, label in DRUM_SWITCHES
            if scope != (frame.drumming or "off")
        )
        # A row of a sentence and its buttons wraps, the buttons going under the sentence where
        # both do not fit (`.kv.wrap`; the workflow review's F12: a button that would not shrink
        # squeezed "this block has no percentage rule..." to one letter a line).
        rows.append(f'<div class="kv wrap"><span class="nm">{now}</span>{switches}</div>')
        if frame.clearing:
            # The controller's ruling M4: on where nothing in the run can be cleared, it says so.
            said = ("clear is on" if frame.clearable
                    else "clear is on, but nothing in this block can be cleared")
            clear = (said, "0", "switch clear off")
        else:
            clear = ("clear is off", "1", "switch clear on")
        # The switch acts only in a block whose rule is a percentage (`Scheduler._first_answers`),
        # so its label names the block's percentage, not the strip's, and a block with another
        # rule, or none, says it changes nothing (the controller's ruling M4; Task 9's fix round).
        judged = (("a percentage counts first answers only", "0",
                   "the block's percentage: count every answer")
                  if frame.first_answers
                  else ("a percentage counts every answer, drummed too", "1",
                        "the block's percentage: count first answers only"))
        if frame.rule == "streak":
            judged = (f"{judged[0]} -- a streak counts every try, so this changes nothing in this "
                      f"block", *judged[1:])
        elif frame.rule is None:
            judged = ("this block has no percentage rule, so this changes nothing here",
                      *judged[1:])
        for setting, (said, on, label) in (("clear", clear), ("first_answers", judged)):
            rows.append(
                f'<div class="kv wrap"><span class="nm">{said}</span><button type="button" class="btn" '
                f'data-cmd="training" data-setting="{setting}" data-on="{on}"{_gate(view)}>'
                f"{label}</button></div>"
            )
    return "".join(rows)


#: Each outcome's place for the trainer's panel's counts by kind (`_by_kind`): `Outcome`'s order,
#: then a hang.
_OUTCOME_ORDER = {outcome.value: at for at, outcome in enumerate(Outcome)} | {"hang": len(Outcome)}


def _by_kind(counts: dict) -> str:
    """Counts by outcome, `wrong_target 7 · no_response 4`: each outcome's wire string, as the
    *This run* pane names them, in `Outcome`'s order, a hang after them and any other sorted;
    `none` where there are none."""
    if not counts:
        return "none"
    order = sorted(counts, key=lambda said: (_OUTCOME_ORDER.get(said, len(_OUTCOME_ORDER)),
                                             str(said)))
    return " · ".join(f"{_e(said)} {_e(counts[said])}" for said in order)


def _percent(part: int, whole: int) -> str:
    """Display arithmetic on two published counts (plan ruling 5), to a whole percent."""
    return f"{100.0 * part / whole:.0f}%"


def _whole(value: object) -> int | None:
    """A pool's value as the whole number it is (`task.Pool`), or `None` for any other."""
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(value) or not float(value).is_integer()):
        return None
    return int(value)


def _ladder(frame: Telemetry, view: View) -> str:
    """The trainer's panel's staircase row (`Telemetry.staircase`): its setting at the level the
    next trial takes, which level of how many, its rule, and **its lock** (TSK-32: "a live value on
    its parameter holds it"): *lock at* sends that level as a person's value, the hold the setting's
    card gives; held, the person's value (its card's), where the staircase waits, and *hand back*,
    engine build C3's, which resumes it at the level nearest the value held."""
    ladder = frame.staircase
    card = next((row for row in frame.params if row.name == ladder.setting), None)
    unit = "" if card is None or not card.unit else f" {_e(card.unit)}"
    name = _e(ladder.setting)
    known = (isinstance(ladder.level, int) and not isinstance(ladder.level, bool)
             and 0 <= ladder.level < len(ladder.levels))
    at = _e(_rung(ladder.levels[ladder.level])) if known else None
    # The value *lock at* sends, the level exactly (`repr`, which reads back as the same number):
    # a held value is judged against the level the staircase stopped at (`taskd.Session._eased`),
    # so one rounded to the six figures shown could count as eased.
    exact = _e(repr(ladder.levels[ladder.level])) if known else None
    where = (f"level {ladder.level + 1} of {len(ladder.levels)}" if known
             else "at a level its staircase does not have")
    if ladder.held:
        value = "unset" if card is None or card.value is None else _e(_rung(card.value))
        waits = f"its staircase waits at {at}, {where}" if known else f"its staircase waits {where}"
        return (f'<div class="kv"><span>{name} <b>{value}</b>{unit}, held by a person</span>'
                f'<span class="nm">{waits}; a hand-back resumes it at the level nearest the value '
                f'held</span><button type="button" class="btn small" data-cmd="hand_back" '
                f'data-name="{name}"{_gate(view)}>hand back</button></div>')
    rule = f"set by its staircase ({_e(ladder.down)} right harder, {_e(ladder.up)} wrong easier)"
    if not known:
        return (f'<div class="kv"><span>{name}</span><span class="nm">{where}, {rule}</span>'
                "</div>")
    return (f'<div class="kv"><span>{name} <b>{at}</b>{unit}</span>'
            f'<span class="nm">{where}, {rule}</span><button type="button" class="btn small" '
            f'data-cmd="lock" data-name="{name}" data-value="{exact}"{_gate(view)}>lock at {at}'
            "</button></div>")


def _answers(bars) -> list[str]:
    """The trainer's panel's last answers (`Telemetry.bars`; the design's §3.4 and §3.5): the
    stage's last ones, each trial's first, which no hold or change of the pool clears (the build's
    final fixes, on Task 7's report), right with their percent, the wrong ones by kind beside them,
    and the trials left out of them beneath; then the bar to move up as it reads, at the stage's
    hardest step, with its proportion and window. A stage that has given fewer than the window
    shows them all, as the stage's; an empty one says so, never a percent of nothing."""
    rows = []
    if bars.of:
        plural = "" if bars.of == 1 else "s"
        which = (f"last {_e(bars.of)}" if bars.of >= bars.window
                 else _e(f"this stage's {bars.of}"))
        rows.append(f'<div class="kv"><span>{which} answer{plural} '
                    f"<b>{_e(bars.correct)} right ({_percent(bars.correct, bars.of)})</b></span>"
                    f'<span class="nm">wrong: {_by_kind(bars.wrong)}</span></div>'
                    f'<div class="kv"><span class="nm">left out of them: '
                    f"{_by_kind(bars.left_out)}</span></div>")
    elif bars.window:
        rows.append(f'<div class="kv"><span>no answers yet in this stage</span><span class="nm">'
                    f"it shows its last {_e(bars.window)}</span></div>")
        if bars.left_out:
            rows.append(f'<div class="kv"><span class="nm">left out so far: '
                        f"{_by_kind(bars.left_out)}</span></div>")
    if bars.up_at is None:
        rows.append('<div class="kv"><span class="nm">this stage has no bar to move up</span></div>')
    else:
        judged = (f"{_e(bars.up_correct)} of the last {_e(bars.up_of)} answers at its hardest step "
                  "right" if bars.up_of else "no answers at its hardest step yet")
        rows.append(f'<div class="kv"><span class="nm">toward moving up: {judged}; the rig '
                    f"suggests it at {bars.up_at:.0%} of {_e(bars.up_window)}</span></div>")
    return rows


def _pairings_on(frame: Telemetry) -> str:
    """The trainer's panel's pool (`Telemetry.pool`): the pairings on, in the pool's order, how many
    of how many, and the bar the rig suggests adding more at; a value that names no pool, said."""
    pool, bars = frame.pool, frame.bars
    whole, total = _whole(pool.value), len(pool.pairings)
    if whole is None or not 1 <= whole < 1 << total:
        return (f'<div class="kv"><span>{_e(pool.setting)} <b>{_e(_rung(pool.value))}</b></span>'
                f'<span class="nm">names no pool of its {total} pairings</span></div>')
    on = [name for at, name in enumerate(pool.pairings) if whole >> at & 1]
    note = f"all {total}" if len(on) == total else f"{len(on)} of {total}"
    if len(on) < total and bars is not None and bars.up_at is not None:
        note += f"; the rig suggests adding more at {bars.up_at:.0%} of {bars.up_window}"
    return (f'<div class="kv"><span>pairings on <b>{_e(", ".join(map(str, on)))}</b></span>'
            f'<span class="nm">{_e(note)}</span></div>')


def _picker(frame: Telemetry, widen, view: View) -> str:
    """**The widening's picker** ("Trainer picks at the prompt"; Task 5): a box for each pairing
    the pool does not hold yet, in its declared order, each with its number, and *add*, which sends
    the pool's value now plus the numbers ticked -- Task 5's whole number, the `set` that answers
    the widening. None where the frame's pool names none to add to."""
    pool = frame.pool
    whole = None if pool is None else _whole(pool.value)
    if whole is None or not 1 <= whole < 1 << len(pool.pairings):
        return '<span class="nm">the frame names no pool to add to</span>'
    boxes = "".join(
        f'<label class="chk"><input type="checkbox" data-widen="{1 << at}" '
        f'data-suggestion="{_e(widen.change)}" aria-label="add pairing {_e(name)}"{_gate(view)}> '
        f"{_e(name)}</label>"
        for at, name in enumerate(pool.pairings) if not whole >> at & 1)
    return boxes + (f'<button type="button" class="btn" data-cmd="widen" '
                    f'data-suggestion="{_e(widen.change)}" data-name="{_e(pool.setting)}" '
                    f'data-value="{whole}"{_gate(view)}>add the pairings ticked</button>')


def _held_at(change: int, label: str, view: View) -> str:
    """*Hold*: `decline`, naming the suggestion -- one hold holds the whole prompt (Task 5)."""
    return (f'<button type="button" class="btn" data-cmd="decline" data-suggestion="{_e(change)}"'
            f"{_gate(view)}>{_e(label)}</button>")


def _moved(suggestion, move: str, label: str, view: View) -> str:
    """*Move up* or *Move back*: `next_block` or `back_block`, naming the suggestion it confirms."""
    return (f'<button type="button" class="btn primary" data-cmd="confirm" data-move="{move}" '
            f'data-suggestion="{_e(suggestion.change)}"{_gate(view)}>{_e(label)}</button>')


_AFRESH = "Tick those to add; adding any starts both bars afresh."
_ACTS = '<div class="acts">'


def _ladder_at_top(frame: Telemetry, ladder) -> bool:
    """Whether the open stage's staircase gives its hardest step now: at its last level, or, held
    by a person, at a value at that level or beyond it in the harder direction (`task.at_hardest`;
    the controller's ruling on the re-review, I-1), the value the frame's card of the setting
    shows."""
    if not ladder.held:
        return 0 <= ladder.level == len(ladder.levels) - 1
    card = next((row for row in frame.params if row.name == ladder.setting), None)
    return card is not None and at_hardest(tuple(ladder.levels), card.value)


def _prompts(frame: Telemetry, view: View) -> list[str]:
    """**The rig's suggestions, each a prompt naming why** (the design's §3.5; the PI's sketch):
    to move up, the setting at its stage's hardest step and the answers right there, with *Move up*
    and *Hold*; to move back, the answers right and the bar they fell under, with *Move back* and
    *Hold*; to widen the pool, the answers at the hardest step and the pairings on, with the picker
    and *Hold*. **One window meeting both bars, one prompt offers both, the stage's first** (§3.4),
    whose one *Hold* holds both (Task 5); at the top stage a widening may stand beside a move back,
    which read different windows, as a prompt of its own after it."""
    stage, widen = frame.suggestion, frame.widen
    prompts = []
    if stage is not None and stage.move == "up":
        ladder = frame.staircase
        pct = _percent(stage.correct, stage.of) if stage.of else "—"
        top = (ladder is not None and bool(ladder.levels) and frame.block == stage.block
               and _ladder_at_top(frame, ladder))
        if top and ladder.hardest:
            # The task's own words for its hardest step (the build's review, M7; the PI's sketch),
            # said only while the trial's value is at it (`task.at_hardest`; the re-review, I-1).
            why = (f"{ladder.hardest[:1].upper()}{ladder.hardest[1:]} and {stage.correct} of the "
                   f"last {stage.of} were correct ({pct}).")
        elif top:
            why = (f"{ladder.setting} is at its hardest step, {_rung(ladder.levels[-1])}, and "
                   f"{stage.correct} of the last {stage.of} answers there were right ({pct}).")
        elif ladder is not None and ladder.levels and frame.block == stage.block:
            # Not at it now (a level below, or a person's value short of it): the bar as it is.
            why = (f"{stage.correct} of the last {stage.of} answers at its hardest step, "
                   f"{_rung(ladder.levels[-1])}, were right ({pct}).")
        else:
            why = f"{stage.correct} of the last {stage.of} answers were right ({pct})."
        body = (f'<div class="prompt" data-prompt="{_e(stage.change)}"><div><b>Ready for '
                f"{_e(stage.to)}.</b> {_e(why)}</div>" + _ACTS
                + _moved(stage, "next_block", f"Move up to {stage.to}", view)
                + _held_at(stage.change, f"Hold at {stage.block}", view) + "</div>")
        if widen is not None:
            body += (f"<div><b>And ready for more pairings.</b> {_AFRESH}</div>" + _ACTS
                     + _picker(frame, widen, view) + "</div>")
        prompts.append(body + "</div>")
        return prompts
    if stage is not None:
        pct = _percent(stage.correct, stage.of) if stage.of else "—"
        bars = frame.bars
        under = ("" if bars is None or bars.back_at is None
                 else f", under {bars.back_at:.0%}")
        prompts.append(
            f'<div class="prompt back" data-prompt="{_e(stage.change)}"><div><b>Back to '
            f"{_e(stage.to)}?</b> {_e(stage.correct)} of the last {_e(stage.of)} answers were "
            f"right ({pct}){under}.</div>" + _ACTS
            + _moved(stage, "back_block", f"Move back to {stage.to}", view)
            + _held_at(stage.change, f"Hold at {stage.block}", view) + "</div></div>")
    if widen is not None:
        pool = frame.pool
        whole = None if pool is None else _whole(pool.value)
        over = ""
        if whole is not None and 1 <= whole < 1 << len(pool.pairings):
            count = bin(whole).count("1")
            over = f", over the {count} pairing{'' if count == 1 else 's'} on"
        pct = _percent(widen.correct, widen.of) if widen.of else "—"
        prompts.append(
            f'<div class="prompt" data-prompt="{_e(widen.change)}"><div><b>Ready for more '
            f"pairings.</b> {_e(widen.correct)} of the last {_e(widen.of)} answers at its hardest "
            f"step were right ({pct}){over}. {_AFRESH}</div>" + _ACTS
            + _picker(frame, widen, view) + _held_at(widen.change, "Hold", view) + "</div></div>")
    return prompts


def _trainer(frame: Telemetry | None, view: View) -> str:
    """**The trainer's panel** (the pop-out search build's Task 7; its design §3.5, the PI's sketch
    of the trainer's screen, accepted with short stage names on 2026-11-07): while a run runs, the
    stage by name, with its plan and the stage it goes on to; the open block's staircase at its
    level, with its lock (`_ladder`); the stage's last answers, the wrong ones and those left out
    by kind, and the bar to move up (`_answers`); the pairings on (`_pairings_on`); and each
    suggestion the rig makes, a prompt naming why with its buttons (`_prompts`). **Empty** -- the
    section then hidden (`#rt-train:empty`) -- for a run with no staircase, no confirmed
    progression, no pool and no suggestion, for a run being stopped, and between runs. Each from
    the frame, never computed here but the percentages (plan ruling 5's display arithmetic)."""
    if frame is None or frame.phase != "running" or frame.stop_kind is not None:
        return ""
    if all(part is None for part in (frame.staircase, frame.bars, frame.pool, frame.suggestion,
                                     frame.widen)):
        return ""
    said = []
    if frame.plan is not None:
        said = [f"plan {frame.plan}", f"next: {frame.next_block}" if frame.next_block is not None
                else "the plan's last stage"]
    rows = ['<div class="top"><h2>Training</h2></div>',
            f'<div class="kv"><span>stage <b>{_e(frame.block)}</b></span>'
            + (f'<span class="nm">{_e(" · ".join(said))}</span>' if said else "") + "</div>"]
    if frame.staircase is not None:
        rows.append(_ladder(frame, view))
    if frame.bars is not None:
        rows.extend(_answers(frame.bars))
    if frame.pool is not None:
        rows.append(_pairings_on(frame))
    rows.extend(_prompts(frame, view))
    return "".join(rows)


def _wrong(frame: Telemetry | None) -> str:
    """Hangs, which are counted, and the three measurements nothing takes yet."""
    hangs = _NONE if frame is None else f'<span class="num">{_e(frame.hangs)}</span>'
    rows = [f'<div class="kv"><span>hangs</span>{hangs}</div>']
    rows += [
        f'<div class="kv"><span>{name}</span><span class="nm">not measured</span></div>'
        for name in _NOT_MEASURED
    ]
    return "".join(rows)


def _health_pane(frame: Telemetry | Idle | None, view: View) -> str:
    """*wl-works sees*: `/health`'s verdict and readings, as they would be sent --
    `health.response` itself, from the same `View` fields `serve`'s `/health` hands
    it (the streams reading included), so the two cannot disagree about a refusal
    (Ruling 11) or the streams open."""
    body = _health.response(
        frame,
        frame_age_s=view.frame_age_s,
        stale_after_s=view.stale_after_s,
        rejected=view.rejected,
        endpoint=view.endpoint,
        streams=view.streams,
    )
    verdict = body["verdict"]
    rows = "".join(
        f'<div class="r"><span class="f">{"◆" if reading["featured"] else ""}</span>'
        f'<span class="l">{_e(reading["label"])}</span>'
        f'<span class="v">{_e(reading["value"])}</span></div>'
        for reading in body["readings"]
    )
    return f'<div><span class="pill {_VERDICT_TONE[verdict]}">{verdict}</span></div>{rows}'


#: How the changes feed and a card lead a staged change of each kind but a person's value
#: (`Staged.kind`, telemetry schema 19; the C3 spec §6 and §8).
_STAGED_KINDS = {"hand_back": "hand back", "range": "range", "revert": "revert",
                 # A person's draw (the console settings build; telemetry schema 22).
                 "form": "drawn"}


def _becomes(change, row=None) -> str:
    """**What a staged change leaves its setting with**, in words (the C3 plan's calls 23 and 30;
    its review, M-15). A hand-back's is where the rig says it goes (`Staged.to`, as it is offered,
    read from the open block as the hand-back is): its conditions, its draw, or the run -- the
    run's own value where it has one (`now`), else the run, which gives it no value, as the applied
    line says -- never "unset", which it is not. A revert's change that hands a setting back
    (`Staged.hands_back`, whatever its `now`) says so the same way, "handed back to ...". Any other
    change's is its new value, a range's its new draw in the rig's words, as `_num` shows a
    value. Escaped (`_e`), ready for the page. Given its setting's `row`, a number is shown as its
    box shows it (`_figure`: a whole setting's with no decimals); the feed's, without, as `_num`."""
    shown = _num if row is None else (lambda value: _figure(row, value))
    if row is not None and row.members is not None:
        # A pool's value is its pairings' numbers summed: said as how many it holds (`_pooled`).
        shown = lambda value: _pooled(row, value)  # noqa: E731
    if change.hands_back:
        back = ("its draw" if change.to == "draw"
                else "the run's " + _e(shown(change.now)) if change.to == "run" and
                change.now is not None
                else "the run, which gives it no value" if change.to == "run"
                else "its conditions")
        return back if change.kind == "hand_back" else "handed back to " + back
    return _e(shown(change.now))


def _will_override(named: tuple) -> str:
    """**What a staged value will override from the next trial, named before it applies** (the
    C3 spec §6: "today only the applied line on the feed does"; TSK-19): the conditions of the
    run's plan that set or draw the setting (`Staged.overrides`), worded as the applied line
    words them; nothing where none does."""
    if not named:
        return ""
    if len(named) == 1:
        return f"; it will override what condition {_e(named[0])} sets or draws"
    return f"; it will override what conditions {', '.join(map(_e, named))} set or draw"


def _reaches(named: tuple) -> str:
    """**The blocks a staged range reaches, named before it applies** (a person's range's
    `Staged.overrides`; the engine C3 plan's science review, M-2: "the staged row names the blocks
    it reaches, as it names the conditions a value overrides"): a range on the task's draw reaches
    every block of the run's plan that uses it, for the rest of the run, a later test block among
    them; nothing where the rig names none."""
    if not named:
        return ""
    return (f"; it reaches block{'s' if len(named) > 1 else ''} {', '.join(map(_e, named))} "
            f"for the rest of the run")


def _said_reach(change) -> str:
    """What a staged change reaches beyond its card, as the feed ends its row: a person's range
    the blocks it reaches (`_reaches`), any other change the conditions it will override
    (`_will_override`), each from its `Staged.overrides`."""
    if change.kind == "range":
        return _reaches(change.overrides)
    return _will_override(change.overrides)


def _changes(frame: Telemetry | None) -> str:
    """The changes feed (spec §5.2): staged changes first, then the control events --
    applied settings, pauses, resumes, marks and their notes, schedules -- newest
    first with when and who, then the refusals with the dropped-refusal count before
    them, as `cli.render` does.

    **Each staged change says its kind and what it will override** (telemetry schema 19; the C3
    spec §6): a person's value as before, naming the conditions it will override before it
    applies (`_will_override`); a hand-back, a live range and a revert's changes each led by
    their kind (`_STAGED_KINDS`), a hand-back saying what takes the setting back and a revert's
    one handing a setting back saying so (`_becomes`), a range saying its draw before and after
    in the rig's words and the blocks it reaches (`_reaches`; the C3 plan's science review,
    M-2)."""
    if frame is None:
        return _NONE
    rows = []
    for change in frame.staged:
        what = "welfare-bounded ceiling" if change.bounded else "task parameter"
        lead = _STAGED_KINDS.get(change.kind)
        rows.append(
            f'<div class="ev staged"><span class="kind">staged</span><span>'
            f"{'' if lead is None else lead + ': '}{_e(change.name)} {_e(_num(change.was))} → "
            f"{_becomes(change)} by {_who(change.by)} ({what}, applies at the next "
            f"trial){_said_reach(change)}</span></div>"
        )
    for control in reversed(frame.controls):
        who = f" · {_who(control.by)}" if control.by is not None else ""
        rows.append(
            f'<div class="ev ctl"><span class="kind">{_e(control.kind)}</span><span>'
            f"{_clock_time(control.at)} · {_e(control.said)}{who}</span></div>"
        )
    if frame.controls_dropped:
        rows.append(
            f'<div class="ev ctl"><span class="kind">earlier</span><span>'
            f"{_e(frame.controls_dropped)} earlier control event(s) not shown: only "
            f"the most recent {len(frame.controls)} are kept</span></div>"
        )
    if frame.refusals_dropped:
        rows.append(
            f'<div class="ev refused"><span class="kind">refused</span><span>'
            f"{_e(frame.refusals_dropped)} earlier refusal(s) not shown: only the most "
            f"recent {len(frame.refusals)} are kept</span></div>"
        )
    for refusal in frame.refusals:
        # Nobody (`None`, b2b spec §6) names no one, where a placeholder name stood.
        who = "" if refusal.by is None else f" by {_who(refusal.by)}"
        rows.append(
            f'<div class="ev refused"><span class="kind">refused</span><span>'
            f"{_e(refusal.name)}{who}: {_e(refusal.why)}</span></div>"
        )
    return "".join(rows) or '<span class="nm">nothing staged, controlled or refused</span>'


# --- task parameters, setup, end of session ----------------------------------------


def _significant(value: float) -> str:
    """A number's own significant decimals, never rounded away.

    `_num`'s two-decimal display would round a welfare ceiling's own figure short of
    what the arrows can still reach: a review of Task 10 (fix round 1) found a 0.125
    mL ceiling showed "0.12" while the arrows -- clamping to `[lo, hi]` before
    `toFixed` rounded the display -- could still send "0.13", over it. `f"{value:g}"`
    keeps every digit the value carries, trailing zeros stripped, for the magnitudes
    a bound uses here. Only the ceiling's own display changes; `_num` is unchanged
    everywhere else."""
    return f"{value:g}"


def _range(row) -> str:
    """**A box's limits and why each stands, whole** (`ParamRow.why`), as its *more* says them:
    each end at the box's own decimals (`_figure`), a whole setting's with none (the design's goal
    6: "1 to 36 objects")."""
    if row.bounded:
        return f"welfare ceiling {_e(_significant(row.high))} {_e(row.unit)}"
    if row.low is None and row.high is None:
        return "no limit"
    ends = ("open" if end is None else _figure(row, end) for end in (row.low, row.high))
    said = f"{_e(next(ends))} to {_e(next(ends))} {_e(_unit_of(row))}"
    # **Why each limit stands, in one line** (`ParamRow.why`; the console settings design's §4:
    # "each card says why for any limit that stays"). The standard "below 0 cannot be" is left
    # unsaid beside another reason, which it goes without saying beside (the builder's call): a
    # fraction's card reads "0 to 1 fraction · a fraction is at most 1".
    why = row.why or {}
    reasons = list(dict.fromkeys(reason for reason in (why.get("low"), why.get("high"))
                                 if reason))
    if len(reasons) > 1 and BELOW_ZERO in reasons:
        reasons.remove(BELOW_ZERO)
    reasons = [_in_percent(row, reason) for reason in reasons]
    return f"{said} · {_e('; '.join(reasons))}" if reasons else said


def _step(row) -> float:
    """**How far one press of a box's − or + moves it** (`ParamRow.step`, the rig's `task.step_of`:
    a declared step, else 1 for a whole setting, else its unit's, else 0.01; the console interface
    design's call on steps): 1 for a whole setting whatever a hand-made row says. A display
    choice, not a rule about values: `Session.set` and `_impossible` judge whatever reached them."""
    return 1.0 if row.whole else row.step


def _hundred(value: float) -> float:
    """**A fraction as its percent** (`ParamRow.percent`; the console interface design's call: "a
    fraction may be shown as a percent"), with a float's noise taken off at twelve significant
    digits: 0.07 is 7, never 7.000000000000001, and 0.575 is 57.5, never 57.49999999999999. Display
    arithmetic only: the setting, the command and the record keep the fraction."""
    return float(f"{value * 100:.12g}")


def _shown_step(row) -> float:
    """A box's step as its field steps (`_step`), ×100 for a percent (`_hundred`): 0.05 is 5."""
    return _hundred(_step(row)) if row.percent else _step(row)


def _unit_of(row) -> str:
    """The unit a box shows beside its numbers: `%` for a percent, else its setting's own."""
    return "%" if row.percent else row.unit


#: A number as the rig writes one in a sentence (`f"{value:g}"`), not inside a name or a longer
#: number, and the word ` fraction` after it where the sentence gives its unit (`_in_percent`).
_SAID_NUMBER = re.compile(r"(?<![\w.])(-?\d+(?:\.\d+)?(?:e[-+]?\d+)?)(?!\w|\.\d)( fraction\b)?")
#: What ties a number to a setting in the rig's sentence, read just before it (`_in_percent`): the
#: setting's quoted name, `'move_up_bar' at ` or `'move_up_bar' `, as `Session.set` and the checks
#: write a value ("'move_up_bar' at 1.2 is refused").
_NAMED_BEFORE = re.compile(r"'([^']+)'(?: at| is| of| =)? $")
#: And what ties one to the setting the sentence is about: "its 1", "its lowest, 0.2, ", and the
#: standard limit's "a fraction is at most 1" (`task.FRACTION_TOP`).
_ITS_BEFORE = re.compile(r"(?:\bits(?: \w+,)? |\ba fraction is at most )$")


def _percents(frame) -> frozenset:
    """The settings a frame shows as percents (`ParamRow.percent`), by name: a sentence's number
    given as one of theirs is converted in any box (`_in_percent`)."""
    return frozenset(row.name for row in frame.params if row.percent) if frame else frozenset()


def _in_percent(row, said: str, peers: frozenset = frozenset()) -> str:
    """**The rig's sentence about a percent setting, in percent** (the console interface design's
    call: "the rig's sentences are converted on the page"), each number **where the sentence ties
    it to a percent setting** (the whole-build review, I7): after a percent setting's quoted name
    -- the row's own, or a peer's among `peers` (`_percents`), "'move_up_bar' at 0.8" -- and, in a
    sentence about the row's own percent setting, after "its" or "a fraction is at most", or given
    in its unit ("1.2 fraction", its ` fraction` dropped), as `_hundred` shows it with `%`:
    "'move_up_bar' at 120% is above its 100%". Any other number stands as written -- "block 1",
    "the last 1 answers" -- whatever the setting's limits or value. A sentence naming no percent
    setting is as the rig wrote it. Plain words in, plain words out, escaped where used."""
    named = set(peers) | ({row.name} if row.percent else set())
    if not named:
        return said

    def shown(found: re.Match) -> str:
        before = said[:found.start()]
        quoted = _NAMED_BEFORE.search(before)
        tied = (quoted is not None and quoted.group(1) in named) or (row.percent and (
            found.group(2) is not None or _ITS_BEFORE.search(before) is not None))
        if not tied:
            return found.group(0)
        return f"{_hundred(float(found.group(1))):g}%"

    return _SAID_NUMBER.sub(shown, said)


def _places(step: float) -> int:
    """The decimals a step shows: 0.05 two, 0.1 one, 1 and 10 none."""
    exponent = Decimal(repr(float(step))).normalize().as_tuple().exponent
    return max(0, -exponent) if isinstance(exponent, int) else 0


#: The most decimals a box shows of a value's own (`_figure`): a value's digits past its step's are
#: shown, never rounded away, up to these.
_OWN_PLACES = 6


def _figure(row, value: object) -> str:
    """**A number as its box shows it** (the console interface design's goal 6, the PI: "for
    necessary whole numbers (set size), there should not be a decimal option"): a whole setting's
    with no decimals, `4`, never `4.00` (its step is 1, `_step`); any other's at its step's
    decimals (`_places`), or more where the value holds more -- 0.35 on a 0.1 step reads 0.35,
    never 0.3 -- up to `_OWN_PLACES`, so a box never shows a value it does not hold. `unset` for `None`; a word as
    written. Formatting, not derivation."""
    if value is None:
        return "unset"
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return str(value)
    number = float(value)
    if not math.isfinite(number):
        return str(value)
    if row.percent:
        # A fraction shown ×100 (`ParamRow.percent`), its step's decimals the percent's: 0.8 is 80.
        number = _hundred(number)
    own = f"{number:.{_OWN_PLACES}f}".rstrip("0").partition(".")[2]
    return f"{number:.{max(_places(_shown_step(row)), len(own))}f}"


def _unit(said: str) -> str:
    """A field's unit beside it (the design's call: "the unit beside every field, the drawn side's
    fields included"); nothing where there is none."""
    return f'<span class="unit">{_e(said)}</span>' if said else ""


def _field(row, view: View, unit: bool = True) -> str:
    """**A box's field** (the console interface design's goal 1): − , the value, +, and its unit
    beside it. A number is shown as `_figure` shows it and carries the step and the declared range
    for the script's − and +, which clamp to it; a whole setting's field steps by 1 and asks for
    the numeric keyboard (goal 6). A categorical value is a word, with neither. **A percent**
    (`ParamRow.percent`; the console interface rework's Task 7) is shown ×100, its step and its
    range ×100 too (`_hundred`), `%` its unit, and marked `data-percent`: the script sends what is
    typed as the fraction it is. `unit` false leaves the unit out but a percent's `%`, for a field
    standing in its group's sentence, which names what it counts. Greyed away from the box."""
    off = _gate(view)
    name = _e(row.name)
    if isinstance(row.value, str):
        return (
            f'<span class="fu"><span class="spin"><input class="field mono" data-param="{name}" '
            f'data-kind="word" value="{_e(row.value)}" aria-label="{name}"{off}></span></span>'
        )
    step = _shown_step(row)
    value = "" if row.value is None else _figure(row, row.value)
    edges = "".join(
        f' data-{end}="{_e(f"{_hundred(edge):g}" if row.percent else edge)}"'
        for end, edge in (("min", row.low), ("max", row.high))
        if edge is not None
    )
    keys = "numeric" if row.whole else "decimal"
    whole = ' data-whole="1"' if row.whole else ""
    if row.percent:
        whole += ' data-percent="1"'
    said = _unit(_unit_of(row)) if unit or row.percent else ""
    return (
        f'<span class="fu"><span class="spin">'
        f'<button type="button" class="stp" data-dir="-1" tabindex="-1" '
        f'aria-label="decrease {name}"{off}>−</button>'
        f'<input class="field mono" data-param="{name}" '
        f'data-step="{step:g}"{edges}{whole} inputmode="{keys}" value="{_e(value)}" '
        f'aria-label="{name}"{off}>'
        f'<button type="button" class="stp" data-dir="1" tabindex="-1" '
        f'aria-label="increase {name}"{off}>+</button></span>{said}</span>'
    )


#: Where a card's value comes from in the open block, for the sources whose value the card shows
#: (`ParamRow.source`, telemetry schema 19; the C3 spec §6: "task, run, conditions, a draw and its
#: range, or a person").
_SOURCES = {
    "task": "from the task's start",
    "run": "given by this run",
    "person": "held by a person",
    # The training switch (the console settings design's §8; telemetry schema 22).
    "frozen": "training frozen",
    "full": "given by the full task",
}
#: **What the training switch holds a card at** (`Telemetry.shaping`; the console settings
#: design's §8: "each frozen value shows on its card"): its value led by these words -- `frozen at
#: 0.6` -- and what its field to set a value over it is for. A person's value still applies ("the
#: experimenter needs free control").
_HELD_BY = {
    "frozen": ("frozen at", "a value over the frozen training"),
    "full": ("full task at", "a value over the full task"),
}
#: The sources that give each trial a value of its own -- its conditions, or its draw -- whose
#: words stand in the value's place on the card, the run's value being one no trial of the open
#: block takes (XC-418); each with what its field to set one value over them is for.
_PER_TRIAL = {
    # Said of both a condition's value and a condition's own range, which the rig sends alike
    # (source `conditions`, no draw): "set or drawn", true of each (review, minor 3).
    "conditions": ("set or drawn by its conditions", "a value over its conditions"),
    "draw": ("drawn each trial", "a value over its draw"),
    # A draw whose range a person changed live says so where its value would stand (the C3
    # plan's science review, I-4: "a card whose range was changed live says so").
    "range": ("drawn each trial, from a range a person changed live", "a value over its draw"),
    # A block's staircase (`task.Staircase`; the pop-out search build, 2026-11-07): its level moves
    # between trials, and a value set over it holds it, the lock, until handed back.
    "staircase": ("set each trial by its staircase", "a value over its staircase"),
    # A task's pool of pairings (`task.Pool`; the pop-out search build's Task 5): each trial draws
    # a pairing into the odd one's look and the distractors', and a value set over either holds it.
    "pool": ("drawn each trial from its pool", "a value over its pool"),
    # A person's draw from the card's drawn side (the console settings build; telemetry schema
    # 22): each trial draws it, and a value set over it ends it, the card's fixed side.
    "form": ("drawn each trial, from a person&#x27;s draw", "a value over this draw"),
}

#: A size a person scales by eccentricity (the console settings design's §5; `_params`): said in
#: its value's place, each object having its own, with what its field to set one value over it is
#: for.
_SCALED = ("scaled by eccentricity, by a person", "a value over this scaling")

#: **The shapes a timing card's drawn side offers, in the trainer's words** (`task.SHAPES`; the
#: console settings design's §3, the PI, 2026-11-16), each with the fields its numbers are typed in,
#: by the names a `form` command sends them under (`variation.FORM_NUMBERS`; a list's and a weighted
#: list's typed as numbers between commas). A size's scaling is not offered here: a size's card
#: takes it, *fixed* or *scaled* (`_scaled_side`; the design's §5).
_SHAPES = (
    ("non_aging", "non-aging", ("shortest", "longest")),
    ("uniform", "uniform", ("low", "high")),
    ("normal", "normal, cut", ("mean", "sd", "low", "high")),
    ("list", "a list, in shuffled passes", ("values",)),
    ("weights", "a list, weighted", ("values", "weights")),
)


def _typed(value: object) -> str:
    """A number as a drawn side's field holds it, every digit (a float's `str`, the shortest that
    reads back the same), or a list of them between commas; empty for none."""
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return ", ".join(str(item) for item in value)
    return str(value)


def _switch(row, view: View, drawn: bool, other: str = "drawn") -> str:
    """**A timing card's switch, *fixed* or *drawn*** (`ParamRow.switch`; the console settings
    design's §3: "every timing setting gets the switch on its card"), **or a size's, *fixed* or
    *scaled*** (`other`; the design's §5): two buttons, the side open pressed. Pressing one opens
    its side on the page alone, a draft of its box; nothing is sent until the box's Apply (the
    console interface rework's Task 6). Greyed away from the box."""
    name, off = _e(row.name), _gate(view)

    def side(which: str, on: bool) -> str:
        return (f'<button type="button" class="btn small seg{" on" if on else ""}" '
                f'data-switch="{which}" data-name="{name}" '
                f'aria-pressed="{"true" if on else "false"}"{off}>{which}</button>')

    return (f'<div class="sw" role="group" aria-label="{name}: fixed or {other}">'
            f'{side("fixed", not drawn)}{side(other, drawn)}</div>')


#: **What a size's factor multiplies**, beside its field as its unit (the design's call: "the unit
#: beside every field").
SCALED_UNIT = "× each object's eccentricity"

#: **What a weighted list's weights are counted in**, beside their field: each weight against the
#: others, not in the setting's unit (`variation`'s weighted list).
WEIGHTS_UNIT = "relative"


def _scaled_side(row, view: View) -> str:
    """**A size card's scaled side** (the console settings design's §5; the PI, 2026-11-16, "Size =
    factor x eccentricity"): its factor, filled from the scaling in force (`ParamRow.shape`); the
    box's Apply sends it as `form` with shape `scaled` (`link.SetForm`), staged until the next
    trial: each object is then drawn at the factor times its own eccentricity. Greyed away from the
    box."""
    off, name = _gate(view), _e(row.name)
    shape = row.shape or {}
    factor = (shape.get("numbers") or {}).get("factor") if shape.get("shape") == "scaled" else None
    return (f'<div class="shp rng" data-fields="scaled"><label class="rn">factor'
            f'<input class="field mono" data-form="factor" inputmode="decimal" '
            f'value="{_e(_typed(factor))}" aria-label="{name}: factor"{off}>'
            f"{_unit(SCALED_UNIT)}</label></div>")


def _drawn_side(row, view: View) -> str:
    """**A timing card's drawn side** (the console settings design's §3; the PI, 2026-11-16: "the
    shapes: non-aging: shortest, longest; uniform: min, max; normal cut to a range: mean, SD, min,
    max; a list of values: shuffled passes, or a weight each"): the shape select, the shape in
    force selected (`ParamRow.shape`, a person's or the block's) or non-aging, and each shape's
    fields, only the selected shape's shown, each filled from the shape in force where it is that
    shape, each with its unit beside it (a weighted list's weights `WEIGHTS_UNIT`); the box's Apply
    sends them as `form` (`link.SetForm`), staged until the next trial. Its profile is in the
    box's *more* (`_profile`). Greyed away from the box."""
    off, name = _gate(view), _e(row.name)
    shape = row.shape or {}
    chosen = shape.get("shape", "non_aging")
    options = "".join(
        f'<option value="{key}"{" selected" if key == chosen else ""}>{_e(said)}</option>'
        for key, said, _ in _SHAPES)
    groups = []
    for key, _, fields in _SHAPES:
        mine = shape if key == chosen else {}
        numbers = mine.get("numbers") or {}
        typed = {field: _typed(mine.get(field) if field in ("values", "weights")
                               else numbers.get(field)) for field in fields}
        cells = "".join(
            f'<label class="rn">{field}<input class="field mono" data-form="{field}" '
            f'inputmode="decimal" value="{_e(typed[field])}" '
            f'aria-label="{name}: {field}"{off}>'
            f'{_unit(WEIGHTS_UNIT if field == "weights" else row.unit)}</label>'
            for field in fields)
        groups.append(f'<div class="shp rng" data-fields="{key}"'
                      f'{"" if key == chosen else " hidden"}>{cells}</div>')
    return (f'<select class="field" data-shape="{name}" aria-label="{name}: shape"{off}>'
            f"{options}</select>{''.join(groups)}")


#: **The profile's drawing, in the SVG's own units** (`_profile`): its width, each panel's left,
#: right, top and base, and the words under it. Fixed here because they are a figure's geometry, not
#: a setting; the figure scales to its card (`.prof` in the style).
_PROFILE_W, _PROFILE_LEFT, _PROFILE_RIGHT = 240, 8, 232
_PROFILE_PANELS = ((14, 54), (76, 116))
_PROFILE_SAID = "the declared distribution, not a measurement"


def _profile(row) -> str:
    """**A drawn card's histogram and hazard** (`ParamRow.profile`; the console settings design's
    §3; the PI, 2026-11-16): one inline SVG of two panels -- bars for the density, each bin's share
    of the draws, scaled to the tallest; and a line for the hazard against a dashed line at 1,
    *flat*, a rising line meaning the chance of the draw ending climbs -- under the words *the
    declared distribution, not a measurement*, since it is arithmetic of what was declared. A range
    has a bar a bin, a list a bar a value. Plain inline SVG, nothing outside it: no font file, no
    link, no style of its own beyond the page's classes. Every word is rendered here, escaped; ""
    where the rig sent none or an empty one."""
    shown = row.profile
    if not shown or not shown.get("density"):
        return ""
    edges, density, hazard = shown["edges"], shown["density"], shown["hazard"]
    count = len(density)
    discrete = len(edges) == count
    slot = (_PROFILE_RIGHT - _PROFILE_LEFT) / count
    width = slot * (0.6 if discrete else 1.0)
    (top_a, base_a), (top_b, base_b) = _PROFILE_PANELS
    tallest = max(density) or 1.0
    ceiling = max(max(hazard), 1.0) or 1.0

    def at(place: int) -> float:
        return _PROFILE_LEFT + slot * (place + 0.5)

    bars = "".join(
        f'<rect class="bar" x="{at(place) - width / 2:.2f}" '
        f'y="{base_a - (base_a - top_a) * share / tallest:.2f}" width="{width:.2f}" '
        f'height="{(base_a - top_a) * share / tallest:.2f}"/>'
        for place, share in enumerate(density))
    rises = " ".join(f"{at(place):.2f},{base_b - (base_b - top_b) * rate / ceiling:.2f}"
                     for place, rate in enumerate(hazard))
    flat = base_b - (base_b - top_b) / ceiling
    ends = (edges[0], edges[-1]) if count > 1 or not discrete else (edges[0],)
    unit = f" {row.unit}" if row.unit else ""
    sides = "".join(
        f'<text class="ax" x="{x}" y="128" text-anchor="{anchor}">{_e(f"{end:.4g}{unit}")}</text>'
        for (x, anchor), end in zip(((_PROFILE_LEFT, "start"), (_PROFILE_RIGHT, "end")), ends))
    name = f"{row.name}: {_PROFILE_SAID}, its density and its hazard against flat"
    return (
        f'<svg class="prof" viewBox="0 0 {_PROFILE_W} 144" role="img" aria-label="{_e(name)}">'
        f'<text class="ax" x="{_PROFILE_LEFT}" y="10">share of draws</text>{bars}'
        f'<line class="base" x1="{_PROFILE_LEFT}" y1="{base_a}" x2="{_PROFILE_RIGHT}" '
        f'y2="{base_a}"/>'
        f'<text class="ax" x="{_PROFILE_LEFT}" y="72">chance it ends, given it has not, against flat'
        f'</text>'
        f'<line class="flat" x1="{_PROFILE_LEFT}" y1="{flat:.2f}" x2="{_PROFILE_RIGHT}" '
        f'y2="{flat:.2f}" stroke-dasharray="4 3"/>'
        f'<text class="ax" x="{_PROFILE_RIGHT}" y="{flat - 3:.2f}" text-anchor="end">flat</text>'
        f'<polyline class="haz" points="{rises}"/>{sides}'
        f'<text class="ax" x="{_PROFILE_LEFT}" y="141">{_PROFILE_SAID}</text></svg>')


#: **What a color card says of its swatches** (the console settings design's §6: "the swatches are
#: approximate on any panel not measured, and the page says so"), word for word.
COLOR_APPROXIMATE = (
    "approximate: this screen is not measured; the rig's measured panel decides what is drawn")

#: A swatch's color as the page may write it into a style: `#` and six hex digits, nothing else.
_HEX = frozenset("0123456789abcdef")


def _swatch(hex_: object) -> str:
    """A swatch's `#rrggbb` as the rig sent it (`photometry.srgb_hex`), or `""` where it is not one,
    so nothing but a color ever reaches the style attribute."""
    if (isinstance(hex_, str) and len(hex_) == 7 and hex_[0] == "#"
            and set(hex_[1:].lower()) <= _HEX):
        return hex_.lower()
    return ""


def _color_level(said: str, level: object, frame, view: View, note: str = "") -> str:
    """**One of a color card's two levels** (`ParamRow.color`'s `saturation` or `luminance`): typed in
    its setting's own unit, as that setting's card types it (`set`, the setting's name), the cd/m²
    of the light beside it; or, where the task file writes a number, shown as fixed there."""
    level = level if isinstance(level, dict) else {}
    setting, value, cd_m2 = level.get("setting"), level.get("value"), level.get("cd_m2")
    lit = (f' <span class="unit">· {_e(_num(cd_m2))} cd/m²</span>'
           if isinstance(cd_m2, (int, float)) and not isinstance(cd_m2, bool) else "")
    if not isinstance(setting, str) or not setting:
        shown = _num(value) if isinstance(value, (int, float)) else "–"
        return (f'<span class="rn lvl">{_e(said)} <span class="mono">{_e(shown)}</span>'
                f'{" cd/m²" if said == "luminance" else ""}, fixed in the task file{lit}</span>')
    row = next((other for other in getattr(frame, "params", ()) if other.name == setting), None)
    unit = row.unit if row is not None else ""
    typed = "" if not isinstance(value, (int, float)) or isinstance(value, bool) else f"{value:g}"
    return (f'<label class="rn lvl">{_e(said)} <span class="mono">{_e(setting)}</span>'
            f'<input class="field mono" data-param="{_e(setting)}" inputmode="decimal" '
            f'value="{_e(typed)}" aria-label="{_e(setting)}: {_e(said)}"{_gate(view)}>'
            f'<span class="unit">{_e(unit)}</span>{lit}{note}</label>')


#: **What the New color panel says of where a color goes** (the console settings design's §6; its
#: plan's Task 8, "Proposed file first"), the set's name between its two halves.
NEW_COLOR_SAVED = ("saved to wl-xtasks/stimuli/proposed/", ".json for the PI to review and commit; "
                   "a rig uses it once committed and pulled")

#: Each method's fields as the panel offers them (`colordef.NUMBERS`, `OPTIONAL` and `FRAMING`):
#: the field, its label's unit, and whether it is sent only for a new set.
_NEW_COLOR_FIELDS = {
    "hue_angle": (("hue_deg", "°", False), ("gray_lightness", "J′, a new set's frame", True),
                  ("chroma", "a new set's frame", True)),
    "dkl": (("azimuth_deg", "°", False), ("elevation_deg", "°", False),
            ("contrast", "blank: the set's mean radius", False)),
    "xy": (("x", "", False), ("y", "", False)),
}


def _new_color(section: str, sets: dict, chosen: str, view: View) -> str:
    """**The New color… panel of a section of color cards** (the console settings design's §6; the
    PI, 2026-11-16: "1,2,or 3. you select an option and then enter the info", "Saved into a color
    set file"; the console interface design's call: "the new-color panel moves out of each color's
    box into one *New color…* panel for the Colors section"), once per section holding a color
    card, after its boxes, keyed by the section (`data-newc`): the method (`colordef.METHODS`, in
    its words, `colordef.SAID`), its fields, a name, and the set it goes into -- one of the
    section's cards' sets, or a new one by its name -- then *preview*, which asks `wlx serve` (`GET
    /color-preview`) and writes nothing, so any viewer may, and *save as a proposal*, which sends
    `define_color` (`link.DefineColor`), greyed away from the box. Then where it goes:
    `NEW_COLOR_SAVED`, naming the set."""
    from wl_xcon.colordef import METHODS, NAME_LIMIT, SAID

    name, off = _e(section), _gate(view)
    methods = "".join(f'<option value="{m}">{_e(SAID[m])}</option>' for m in METHODS)
    fields = []
    for method in METHODS:
        inputs = "".join(
            f'<label class="rn"{" data-newset-only" if only else ""}>{_e(field)} '
            f'<input class="field mono" data-newc-num="{field}" inputmode="decimal" '
            f'aria-label="{name}: new color {_e(field)}"><span class="unit">{_e(unit)}</span></label>'
            for field, unit, only in _NEW_COLOR_FIELDS[method])
        fields.append(f'<div class="nf" data-newc-fields="{method}"'
                      f'{"" if method == METHODS[0] else " hidden"}>{inputs}</div>')
    into = "".join(
        f'<option value="{_e(named)}"{" selected" if named == chosen else ""}>{_e(named)}</option>'
        for named in sets) + '<option value="">a new set</option>'
    return (f'<details class="newc" data-newc="{name}"><summary>New color…</summary>'
            f'<label class="rn">by <select class="field" data-newc-method aria-label="{name}: '
            f'new color method">{methods}</select></label>{"".join(fields)}'
            f'<label class="rn">name <input class="field" data-newc-name maxlength="{NAME_LIMIT}" '
            f'aria-label="{name}: new color name"></label>'
            f'<label class="rn">into <select class="field" data-newc-into aria-label="{name}: '
            f'new color set">{into}</select><input class="field" data-newc-set maxlength="'
            f'{NAME_LIMIT}" placeholder="a name for the new set" aria-label="{name}: new set name" hidden>'
            f'</label>'
            f'<div class="newc-do"><button type="button" class="btn small" data-cmd="preview_color" '
            f'data-name="{name}">preview</button><button type="button" class="btn small" '
            f'data-cmd="define_color" data-name="{name}"{off}>save as a proposal</button></div>'
            f'<span class="newc-out" aria-live="polite"></span>'
            f'<span class="src">{_e(NEW_COLOR_SAVED[0])}<span data-newc-path>{_e(chosen)}</span>'
            f'{_e(NEW_COLOR_SAVED[1])}</span></details>')


def _color_card(row, frame, view: View) -> str:
    """**A color setting's card** (`ParamRow.color`; the console settings design's §6; the PI,
    2026-11-16: "you select a set, and then you have hue options from the set, then you have
    salience options for each hue"), three steps: **the set** (a select of the sets its choices
    show, the run's value's chosen), **the hue** (a swatch with its name for each hue the set
    offers, the run's value's pressed; pressing one is a draft of its box, which the box's Apply
    sends as `color`, `link.SetColor`, staged until the next trial: the console interface rework's
    Task 6), and **two levels** (`_color_level`): its saturation, gray to full, its luminance
    held, and its luminance, its saturation held -- the latter the light's fraction setting, or its
    set's luminance setting, which moves every light of the set that reads it. The caption,
    `COLOR_APPROXIMATE`, is in its box's *more*, its status line saying "approximate on this
    screen" at rest (`_box`). Each swatch's color is the rig's (`photometry.srgb_hex`), written only
    where it is a `#rrggbb`. Greyed away from the box. `""` where the rig sent none."""
    color = row.color
    if not isinstance(color, dict) or not isinstance(color.get("sets"), dict) or not color["sets"]:
        return ""
    name, off = _e(row.name), _gate(view)
    sets = color["sets"]
    chosen = color.get("set") if color.get("set") in sets else next(iter(sets))
    options = "".join(
        f'<option value="{_e(named)}"{" selected" if named == chosen else ""}>{_e(named)}</option>'
        for named in sets)
    groups = []
    for named, entry in sets.items():
        hues = entry.get("hues") if isinstance(entry, dict) else None
        buttons = []
        for hue, shown in (hues or {}).items():
            hex_ = _swatch((shown or {}).get("srgb"))
            on = named == color.get("set") and hue == color.get("hue")
            chip = (f'<span class="chip" style="background:{hex_}"></span>' if hex_
                    else '<span class="chip none"></span>')
            buttons.append(
                f'<button type="button" class="btn small hue{" on" if on else ""}" '
                f'data-name="{name}" data-colorset="{_e(named)}" '
                f'data-color="{_e(hue)}" aria-pressed="{"true" if on else "false"}"{off}>'
                f"{chip}{_e(hue)}</button>")
        groups.append(f'<div class="hues" data-hues="{_e(named)}" data-name="{name}"'
                      f'{"" if named == chosen else " hidden"}>{"".join(buttons)}</div>')
    luminance = color.get("luminance") if isinstance(color.get("luminance"), dict) else {}
    # The light's set's luminance moves every light of the set that reads it, not this one alone
    # (the design's §6, as the card says).
    every = (' <span class="unit">· moves every light of the set</span>'
             if luminance.get("setting") and luminance.get("set_wide") is True else "")
    return (f'<div class="clr" data-color="{name}">'
            f'<label class="rn">set <select class="field" data-colorset="{name}" '
            f'aria-label="{name}: color set"{off}>{options}</select></label>'
            f'{"".join(groups)}'
            f'<div class="lvls">{_color_level("saturation", color.get("saturation"), frame, view)}'
            f'{_color_level("luminance", luminance, frame, view, every)}</div></div>')


def _new_colors(rows: list, view: View) -> dict:
    """**Each section's one New color… panel** (`_new_color`), by section, for every section that
    holds a color card (`ParamRow.color` with its sets): the sets its cards show, in the order they
    first show them, the first card's set chosen."""
    panels: dict = {}
    for section, row in rows:
        color = row.color
        if not isinstance(color, dict) or not isinstance(color.get("sets"), dict) or not color["sets"]:
            continue
        sets, chosen = panels.setdefault(section, ({}, [None]))
        for named, entry in color["sets"].items():
            sets.setdefault(named, entry)
        if chosen[0] is None:
            chosen[0] = color.get("set") if color.get("set") in color["sets"] else next(
                iter(color["sets"]))
    return {section: _new_color(section, sets, chosen[0], view)
            for section, (sets, chosen) in panels.items()}


#: **What a pool's box says at rest** (the console interface design's goal 7), its status line.
POOL_REST = "odd color down, distractor across · each trial draws one pair ticked"


def _pooled(row, value: object) -> str:
    """**A pool's value as its box says it**: how many of its pairings it holds (`ParamRow
    .members`, each a bit of the value: `task.Pool.number`), "2 of 12 pairs"; the value as written
    where it names no pool of them (no whole number from 1, or a bit past its pairings)."""
    total = len(row.members)
    whole = _whole(value)
    if whole is None or not 1 <= whole < 1 << total:
        return _figure(row, value)
    held = sum(1 for member in row.members if whole & member.bit)
    return f"{held} of {total} pair{'' if total == 1 else 's'}"


def _pairings(row, view: View) -> str:
    """**A pool's grid** (`ParamRow.members`; the console interface design's goal 7; the PI,
    2026-11-19: "4 × 4 grid, add or remove"): the odd one's color down, the distractors' across,
    each color with its swatch (`PoolMember.odd_hex`, `among_hex`, the rig's, written only where
    it is a `#rrggbb`), a tick for each pair the pool offers, ticked where the value holds it
    (`on`), named "blue among red" for a screen reader, carrying its number (`data-bit`); the
    diagonal empty, a color never among itself, and a cell empty where the pool offers no such
    pair. Ticks are a draft of the box: its Apply sends one `set` of the pool's number, the ticked
    pairs' bits summed (the script's `poolSum`), which is what is recorded; adding and removing
    pairs both go live. The bits and swatches are the rig's, never worked out here. Greyed away
    from the box."""
    name, off = _e(row.name), _gate(view)
    colors: dict = {}
    for member in row.members:
        for named, hex_ in ((member.odd, member.odd_hex), (member.among, member.among_hex)):
            if not colors.get(named):
                colors[named] = _swatch(hex_)
    pairs = {(member.odd, member.among): member for member in row.members}

    def color(named: str) -> str:
        hex_ = colors[named]
        chip = (f'<span class="chip" style="background:{hex_}"></span>' if hex_
                else '<span class="chip none"></span>')
        return f"{chip}{_e(named)}"

    head = "".join(f'<th scope="col">{color(named)}</th>' for named in colors)
    lines = []
    for odd in colors:
        cells = []
        for among in colors:
            member = pairs.get((odd, among))
            if odd == among:
                cells.append('<td class="diag"></td>')
            elif member is None:
                cells.append('<td class="none"></td>')
            else:
                said = _e(f"{odd} among {among}")
                cells.append(
                    f'<td><input type="checkbox" class="tick" data-bit="{member.bit}"'
                    f'{" checked" if member.on else ""} aria-label="{said}" title="{said}"{off}></td>')
        lines.append(f'<tr><th scope="row">{color(odd)}</th>{"".join(cells)}</tr>')
    return (f'<table class="pairs" data-pool="{name}" aria-label="{name}: pairs, odd color down, '
            f'distractor across"><thead><tr><th scope="col" class="corner">'
            f'<span>odd ↓</span><span>among →</span></th>{head}</tr></thead>'
            f'<tbody>{"".join(lines)}</tbody></table>')


def _beneath(row, frame) -> str:
    """**What a person's draw overrides**, as its card says it (the console settings design's §3:
    "the card names what it overrides, as `_whence` does"): the open block's staircase where it
    steps the setting (`Telemetry.staircase`), its draw where one draws it (`ParamRow.draw`), its
    conditions where they set it, else the run's value."""
    stair = getattr(frame, "staircase", None)
    if stair is not None and stair.setting == row.name:
        return "its staircase"
    if row.draw is not None:
        return "its draw"
    if row.conditions:
        return "its conditions"
    return "the run's value"


def _over(row, place: str, view: View) -> str:
    """**The field that sets one value over what gives each trial its own** -- the card's
    conditions or its draw -- from the next trial, where it wins (TSK-19: a trial its conditions
    set still counts toward its condition, marked overridden; the C3 spec §6: "a person's value
    replaces a draw"): empty, since no one number is in force for it to show, and **never a
    spinner** (XC-418), no arrows stepping from a number no trial takes. A word where the run's
    value is one, else a number, as `_field` reads it; greyed away from the box."""
    word = isinstance(row.value, str)
    keys = ' data-kind="word"' if word else (
        ' data-whole="1" inputmode="numeric"' if row.whole else ' inputmode="decimal"')
    if row.percent and not word:
        keys += ' data-percent="1"'
    name = _e(row.name)
    return (f'<span class="fu"><input class="field mono over" data-param="{name}"{keys} value="" '
            f'placeholder="{place}" aria-label="{name}: {place}"{_gate(view)}>'
            f'{"" if word else _unit(_unit_of(row))}</span>')


def _range_editor(row, view: View) -> str:
    """**The numbers of the card's draw a person may change live** (`ParamRow.numbers`; the PI,
    2026-10-30, Q7b: "Yes, range changes live"), each in a field of its own as the wire carried
    it, every digit (a float's `str` is the shortest that reads back the same). A number changed
    is a draft of its box, sent by the box's Apply as a `range` of those a person changed
    (`SetRange`), laid by the rig over the numbers in force (the console interface rework's Task
    6: *change the range* is gone, the box's Apply its one send). On a card whose `numbers` is not
    `None` alone: none for a setting declared not live, a direction, a weighted set or a list
    (review M-4; XC-443, XC-445). Greyed away from the box."""
    off, name = _gate(view), _e(row.name)
    fields = "".join(
        f'<label class="rn">{_e(number)}<input class="field mono" data-number="{_e(number)}" '
        f'inputmode="decimal" value="{_e(value)}" aria-label="{name}: {_e(number)}"{off}>'
        f"{_unit(row.unit)}</label>"
        for number, value in row.numbers.items()
    )
    return f'<div class="rng">{fields}</div>'


def _whence(row, view: View, over: str = "", ranges: bool = True) -> str:
    """**Where a card's value comes from, and what a person may do about it** (telemetry schema
    19; the C3 spec §6: "each setting's card says where its value comes from (task, run,
    conditions, a draw and its range, or a person) and which conditions set or draw it"),
    beneath its range:
    - the task's start, the run, or a person, where the card shows the value they give (its
      conditions and its draw say so in the value's place, `_PER_TRIAL`);
    - every condition of the run's plan that sets or draws it, whose value a person's replaces
      until handed back (TSK-19), the rest counted where the rig names only the first;
    - the open block's draw of it in the rig's words: what gives each trial its value, or, while
      a person holds it, what a hand-back gives it back to;
    - the numbers of that draw a person may change live (`_range_editor`);
    - on a card a person holds, *hand back* (the PI, 2026-10-30, Q7a: "Yes, a 'hand back'
      button"): from the next trial its conditions, its draw or the run's own value give it
      again, recorded as a change. Typing the old value back does not hand it back; this does.
    - on a card a person's draw gives (`source` `form`; the console settings build), what it
      overrides (`over`, from `_beneath`) and *hand back*, which ends the draw.

    Nothing between runs, nor for a ceiling, when the rig sends none. `ranges` false leaves out
    the live numbers' fields, for a group box's *more*, whose one Apply sends its fields' values
    only (`_group_box`)."""
    parts = []
    if row.source in _SOURCES:
        parts.append(f'<span class="src">{_SOURCES[row.source]}</span>')
    if row.source == "form":
        what = ("scaling" if row.shape is not None and row.shape.get("shape") == "scaled"
                else "draw")
        parts.append(f'<span class="src">a person&#x27;s {what}, over {_e(over)}</span>')
    if row.conditions:
        # The rig names at most twenty and counts the rest (`ParamRow.more`; the C3 plan's
        # engineering review, M-5).
        plural = "s" if len(row.conditions) + row.more > 1 else ""
        more = f" and {row.more} more" if row.more else ""
        parts.append(f'<span class="src">set or drawn by condition{plural} '
                     f'{", ".join(map(_e, row.conditions))}{more}</span>')
    if row.draw is not None:
        parts.append(f'<span class="src">its draw: {_e(row.draw)}</span>')
    if row.numbers is not None and ranges:
        parts.append(_range_editor(row, view))
    if row.source in ("person", "form"):
        parts.append(f'<button type="button" class="btn small" data-cmd="hand_back" '
                     f'data-name="{_e(row.name)}"{_gate(view)}>hand back</button>')
    return "".join(parts)


def _plain(markup: str) -> str:
    """Markup this module made, as the words it shows, for a `title` that holds a cut text whole."""
    return " ".join(html.unescape(re.sub(r"<[^>]+>", "", markup)).split())


#: **How much of a refusal its box's status line says** (`_gist`), in characters: its reason, cut
#: at a word; the whole sentence is in the box's *more* (the layout review's finding 2: "a refusal
#: of 14 lines that never leaves").
GIST_LIMIT = 80


def _gist(why: str) -> str:
    """**A refusal's reason in short**, for its box's one status line: the part after the rig's
    "...is refused, and the previous value stands:" where it says one, else the sentence, cut at a
    word to `GIST_LIMIT` characters with "…"."""
    said = " ".join((why.partition(": ")[2] or why).split())
    if len(said) <= GIST_LIMIT:
        return said
    return (said[:GIST_LIMIT].rpartition(" ")[0] or said[:GIST_LIMIT]).rstrip(",;:") + "…"


def _limits(row) -> str:
    """**A box's limits in short**, for its status line at rest (the layout review's finding 2:
    "`0 or more` for `0.00 to open s · below 0 cannot be`"): its ends as `_figure` shows them, a
    whole setting's said whole; the sentence with each limit's reason is in its *more*
    (`_range`). Plain words, escaped where used."""
    if row.bounded:
        return f"welfare ceiling {_significant(row.high)} {row.unit}"
    low, high = (None if end is None else _figure(row, end) for end in (row.low, row.high))
    said = ("" if low is None and high is None else f"{low} or more" if high is None
            else f"up to {high}" if low is None else f"{low} to {high}")
    if row.whole:
        return f"{said} · whole number" if said else "whole number"
    return said


def _status(row, change, refusal, peers: frozenset = frozenset()) -> tuple[str, str]:
    """**A box's one status line** (the console interface design's goal 4) as the rig's frame
    says it, and the state it marks the box with: a change waiting for the next trial and who
    sent it (`staged`); else the last refusal of it, the value refused and its gist (`refused`);
    else, while a run plays, the change in force and the trial it took effect at (`Applied`), with
    a warning where the rig judged one (`warned`, else `applied`); else, at rest, its limits in
    short (`_limits`) -- a color's that its swatches are approximate. The page's own states (*not
    sent*, *sending…*, *cannot send*) are its script's (the plan's Task 6)."""
    if change is not None:
        return "staged", f"{WAITING} · {_who(change.by)}"
    if refusal is not None:
        value = "" if refusal.value is None else f" {_e(_refused_value(row, refusal.value))}"
        return "refused", f"refused{value} · {_e(_gist(_in_percent(row, refusal.why, peers)))}"
    if row.applied is not None:
        if row.warned:
            return "warned", f"in force, with a warning · from trial {_e(row.applied.trial)}"
        return "applied", f"in force from trial {_e(row.applied.trial)}"
    if row.members is not None:
        return "", _e(POOL_REST)
    return "", _e("approximate on this screen" if row.color is not None else _limits(row))


def _refused_value(row, value: object) -> str:
    """The value a refusal refused, as its box shows it (`_figure`), a percent's with its `%`."""
    shown = _figure(row, value)
    return f"{shown}%" if row.percent and isinstance(value, (int, float)) else shown


def _under(row, change) -> str:
    """**Who changed a box under a person's draft, in words** (the console interface plan's Review
    Focus 4: "the draft is untouched, the head shows the new value in force, the status says who
    changed it"): a change waiting for the next trial, who sent it and what it leaves the setting
    with; else the change in force, who made it and the trial it took effect at. Plain text, for
    the box's `data-under`, which the script says after *not sent* while a draft stands over it;
    "" for neither."""
    if change is not None:
        return f"{_plain(_who(change.by))} is changing this to {_plain(_becomes(change, row))}"
    if row.applied is not None:
        return f"{row.applied.by} changed this from trial {row.applied.trial}"
    return ""


def _withdraw(change, together: tuple, view: View) -> str:
    """**A waiting change's *withdraw*** (the console interface design's goal 3; the PI,
    2026-11-19: "Yes, a withdraw button"), in its box's status line beside Apply: it sends
    `withdraw` naming the act's command id (`Staged.cid`, `link.Withdraw`), which takes back the
    whole act, so it says so first where the act holds more than this box ("withdraw all 3",
    "withdraws the 3 applied together: ..." in its title; the design's call). None for a change
    no page sent (no cid). Greyed away from the box."""
    if change is None or not change.cid:
        return ""
    if len(together) > 1:
        said, title = (f"withdraw all {len(together)}",
                       f"withdraws the {len(together)} applied together: {', '.join(together)}")
    else:
        said, title = "withdraw", "takes this change back before the next trial"
    # The title rides on a wrapper: the button's own is the gate's ("controls work only at the rig
    # PC"), which the sign-in's script takes while it is live.
    return (f'<span class="wd" title="{_e(title)}"><button type="button" class="btn small" '
            f'data-withdraw="{_e(change.cid)}" tabindex="0"{_gate(view)}>{_e(said)}</button></span>')


#: **A waiting change's status line, short, and its whole** (the console interface rework's
#: whole-build review, I4): beside *withdraw* a box of 190 px has about 100 px for its line, so it
#: says "waiting · who" and its title the whole, "waiting for the next trial · who".
WAITING, WAITING_WHOLE = "waiting", "waiting for the next trial"


def _awaited(value: str, change, row, lead: str | None = None) -> str:
    """**A head's value in force and what waits for the next trial after an arrow** (`_box`,
    `_group_box`): a number's unit said once, after what waits -- "0.30 → 0.50 s", "4 → 12 objects"
    -- so the arrow and the new value fit a narrow box (the whole-build review, I4); any other value
    -- a draw, a person's hold, words, a pool's pairs -- as it is, then the arrow. `value` alone where
    nothing waits."""
    if change is None:
        return value
    becomes = f'→ {"" if lead is None else _e(lead) + " "}{_becomes(change, row)}'
    unit = _e(_unit_of(row))
    tail = f' <span class="unit">{unit}</span></span>'
    if lead is None and value.startswith('<span class="pv">') and value.endswith(tail):
        return (f'{value[:-len(tail)]}</span> <span class="to">{becomes}</span>'
                f' <span class="unit">{unit}</span>')
    return f'{value} <span class="to">{becomes}</span>'


def _whole_say(state: str, said: str) -> str:
    """A status line's whole, for its `title`: a waiting one's "waiting for the next trial · who"
    (`WAITING_WHOLE`), any other as it is. Plain text."""
    plain = _plain(said)
    if state == "staged" and plain.startswith(WAITING + " · "):
        return WAITING_WHOLE + plain[len(WAITING):]
    return plain


def _box(row, frame, view: View, value: str, editor: str, change, refusal,
         together: tuple = ()) -> str:
    """**One setting's box** (the console interface design's goal 1; the PI, 2026-11-19, "Small
    boxes"; the controls review's §2, "three zones, fixed places"), the markup the page's script
    works on:

        <div class="box[ state][ ceiling][ wide]" data-card="NAME">
          <div class="head">   the plain name (`ParamRow.label`) with the code name small, or the
                               code name alone; the ceiling's mark; the value in force, and what
                               waits for the next trial after an arrow
          <div class="editor"> the field with − and + and its unit, or the fixed/drawn switch and
                               its sides, or a color's set and swatches
          <div class="status"> one line (`_status`) and, at its right, *withdraw* for a change
                               waiting under a command id (`_withdraw`), Discard and Apply, hidden
                               by `visibility` until the script marks the box `draft` (or the box
                               is `staged`), so its height never jumps; Apply and Discard are
                               in the Tab order, Safari's too (`tabindex="0"`)
          <details class="more"> opened in place: what it is (`ParamRow.help`), its limits and
                               why (`_range`), where its value comes from and *hand back*
                               (`_whence`), what it gives, the staged change, the warnings and the
                               last refusal whole, and a draw's profile

    Every text a narrow box may cut short carries its whole in its `title`.

    **What the script reads off a box** (the console interface rework's Task 6): `data-staged-cid`,
    the command id of the change waiting (`Staged.cid`); `data-refusal`, a key of the last
    refusal shown, and `data-refusal-cid`, its command id (`Refused.cid`); `data-applied`, the
    trial the change in force took effect at; `data-under`, who changed it under a draft
    (`_under`); and on a refusal's status line, `data-rest` and `data-rest-state`, what the line
    says once a later change has been accepted (the design's goal 4: "a refusal is cleared by a
    later accepted change of that setting")."""
    name, off = _e(row.name), _gate(view)
    if row.label:
        names = (f'<span class="names"><span class="lbl" title="{_e(row.label)}">{_e(row.label)}'
                 f'</span><span class="code" title="{name}">{name}</span></span>')
    else:
        names = f'<span class="names"><span class="code only" title="{name}">{name}</span></span>'
    flag = '<span class="ceil">ceiling</span>' if row.bounded else ""
    lead = None if change is None else _STAGED_KINDS.get(change.kind)
    if change is not None and change.kind == "form" and row.switch == "scaled":
        lead = "scaled"
    now = _awaited(value, change, row, lead)
    peers = _percents(frame)
    state, said = _status(row, change, refusal, peers)
    mark = (
        ""
        if change is None
        else f'<span class="stg">staged{"" if lead is None else " " + lead} → '
        f"{_becomes(change, row)} by {_who(change.by)}</span>"
    )
    more = [_pin(name)]
    if row.help:
        more.append(f'<span class="what">{_e(row.help)}</span>')
    more.append(f'<span class="range">{_range(row)}</span>')
    more.append(_whence(row, view, _beneath(row, frame)))
    if row.gives is not None:
        # What it gives each object, in degrees, made by the rig (`ParamRow.gives`; the
        # console settings design's §5).
        more.append(f'<span class="src gives">gives {_e(row.gives)}</span>')
    more.append(mark)
    more.extend(f'<span class="wrn">warning: {_e(_in_percent(row, warned, peers))}</span>'
                for warned in row.warned)
    if refusal is not None:
        more.append(f'<span class="rfs">last refused: '
                    f'{_e(_in_percent(row, refusal.why, peers))}</span>')
    if row.switch == "drawn":
        more.append(_profile(row))
    if isinstance(row.color, dict) and row.color.get("sets"):
        more.append(f'<span class="src approx">{_e(COLOR_APPROXIMATE)}</span>')
    wide = row.color is not None or row.members is not None
    classes = " ".join(word for word in ("box", state, "ceiling" if row.bounded else "",
                                         "wide" if wide else "") if word)
    marks = []
    if change is not None and change.cid:
        marks.append(f' data-staged-cid="{_e(change.cid)}"')
    if refusal is not None:
        marks.append(f' data-refusal="{_e(refusal.cid or refusal.why)}"')
        if refusal.cid:
            marks.append(f' data-refusal-cid="{_e(refusal.cid)}"')
    if row.applied is not None:
        marks.append(f' data-applied="{_e(row.applied.trial)}"')
    under = _under(row, change)
    if under:
        marks.append(f' data-under="{_e(under)}"')
    if _echoes(row):
        marks.append(" data-echo")
    rest = ""
    if state == "refused":
        rest_state, rest_said = _status(row, change, None, peers)
        rest = f' data-rest="{_e(_plain(rest_said))}" data-rest-state="{rest_state}"'
    return (
        f'<div class="{classes}" data-card="{name}"{"".join(marks)}>'
        f'<div class="head">{names}{flag}<span class="now" title="{_e(_plain(now))}">{now}</span>'
        f"</div>"
        f'<div class="editor">{editor}</div>'
        f'<div class="status"><span class="say" title="{_e(_whole_say(state, said))}"{rest}>'
        f'{said}</span><span class="acts">'
        f'{_withdraw(None if row.bounded else change, together, view)}'
        f'<button type="button" class="btn small" data-discard="{name}" tabindex="0"{off}>'
        f'Discard</button><button type="button" class="btn small primary" '
        f'data-apply="{name}" tabindex="0"{off}>Apply</button></span></div>'
        f'<details class="more"><summary aria-label="{_e(MORE_SAID)}" title="{_e(MORE_SAID)}">⋯'
        f'</summary><div class="detail">{"".join(more)}</div></details></div>'
    )


def _params(frame: Telemetry | None, view: View, training: bool = False) -> str:
    """**A settings tab: the summary, its legend, then the editor** (the summary and editor design
    of 2026-11-19, mock-up A, which the PI chose: "go A"): one line per box in the summary
    (`_summary`), and in the editor below it every box and each section's New color… panel, each
    `hidden` but the one the page opens (`_hidden`; `openSetting` in the script), with a
    placeholder said while none is.

    One box per `ParamRow` (`_box`, the console interface rework's Task 5: head, editor, one
    status line and a *more* opened in place): value, unit, range, the ceiling flag, a staged
    marker, and -- P4d-2b b2a -- the input and its − and + that set it and the last refusal of it
    with its sentence (spec §5.2: "A refusal shows on the card and in the feed"), its gist on the
    status line and the whole in *more*. *Last* is the word because a refusal carries no time: it
    stays on the box beside whatever the value has since become, and says it is the last.

    **A setting holding a whole position** shows the rig's words for it, eccentricity and
    direction first with its (x, y) beside them, its unit in them (`ParamRow.position`; the PI,
    2026-10-19, "Polar first, x-y allowed"; XC-401), and no input or arrows: nothing a console
    sends sets a position, `link._setting` taking a number or a word. **Any other value that is
    neither a number nor a word** -- a pair a setting not declared a position holds, arriving as a
    list, or a `bool` -- is shown as written, with no input either (XC-401's second fix round):
    formatted as a number it raised, and `serve` builds the page and its event stream from these
    cards unguarded, so the page went blank and took the controls with it.

    **Where each value comes from** (telemetry schema 19; engine build C3's spec §6; narrows
    XC-418, whose spinner stays on a setting holding no value of its own): a card whose conditions
    or whose draw give each trial a value of its own says so in the value's place, never a
    spinner, with a field to set one value over them (`_over`); then, beneath its range, where
    its value comes from, the conditions that set or draw it, its draw, the numbers of that draw
    a person may change live, and *hand back* (`_whence`). A staged change on the card is led by
    its kind and says what it leaves the setting with (`_becomes`).

    **A timing card is fixed or drawn** (`ParamRow.switch`; telemetry schema 22; the console
    settings design's §3): its switch (`_switch`), then its fixed side -- the field above, `set` --
    and its drawn side (`_drawn_side`), the side open drawn where a draw is in force
    (`ParamRow.shape`), else fixed; where its value comes from stays above both."""
    if frame is None:
        return _NONE
    if not frame.params:
        return '<span class="nm">this task declares no parameters</span>'
    staged = {change.name: change for change in frame.staged}
    refused = {refusal.name: refusal for refusal in frame.refusals}
    # The settings of each act waiting under a command id, in order (`_withdraw`: one act's
    # *withdraw* takes back all of it).
    acts: dict = {}
    for change in frame.staged:
        if change.cid:
            acts.setdefault(change.cid, []).append(change.name)
    entries = [entry for entry in _entries(frame) if _training(entry[0]) == training]
    cards = []
    for section, row, group, members in entries:
        if group is not None:
            cards.append((section, _group_box(group, members, frame, view, staged, acts)))
            continue
        change = staged.get(row.name)
        refusal = refused.get(row.name)
        together = tuple(acts.get(change.cid, ())) if change is not None and change.cid else ()
        label, editor = _editor(row, frame, view)
        cards.append((section, _box(row, frame, view, label, editor, change, refusal, together)))
    panels = _new_colors([(section, row) for section, row, group, _ in entries if group is None],
                         view)
    # **The editor** (the summary and editor design's goal 2): every box, and each section's New
    # color… panel after its boxes, in the summary's order, each `hidden` until the page's script
    # opens it (`openSetting`), so drafts, `patchCards` and `judge` keep every box; the
    # placeholder said while none is opened.
    shown = []
    for top, node in _in_order(cards):
        for section, found in [(top, node["own"])] + [
                (f"{top}/{sub}", subs) for sub, subs in node["subs"].items()]:
            shown.extend(_hidden(html) for _, html in found)
            if section in panels and found:
                shown.append(_hidden(panels[section]))
    # **A withdrawal the rig refused** (`Refused` named `withdraw`, its `cid` the act's; the
    # console interface rework's Task 4), its reason in short, for the script to say on the act's
    # boxes ("not withdrawn · it is already in force from trial 41 ..."): no box is named
    # `withdraw`, so none carries it.
    declined = "".join(f'<span class="wdr" data-cid="{_e(refusal.cid)}">{_e(_gist(refusal.why))}'
                       f"</span>" for refusal in frame.refusals
                       if refusal.name == "withdraw" and refusal.cid)
    # **And a withdrawal the rig did** (`Telemetry.withdrawals`; the whole-build review's I1): the
    # act's id, the rig's word that it was taken back, which alone lets the script say "withdrawn"
    # -- a change waiting no more may have applied.
    declined += "".join(f'<span class="wdn" data-cid="{_e(cid)}"></span>'
                        for cid in frame.withdrawals)
    return (_summary(frame, view, training)
            + f'<div class="legend">{_e(SUMMARY_LEGEND)}</div>'
            + f'<div class="editing"><div class="placeholder">{_e(EDITOR_EMPTY)}</div>'
            + f'<div class="findhid" hidden>{_e(FIND_HIDES_OPENED)}</div>'
            + "".join(shown) + "</div>"
            + f'<div class="wdrs" hidden>{declined}</div>')


#: **What each mark on a summary line means** (the summary and editor design's goal 3; the page's own
#: marks, … and ?, since that build's Task 2), said once under the summary.
SUMMARY_LEGEND = ("● not sent · … sending · ? not confirmed by the rig · ◷ waiting for the next trial · "
                  "◆ drawn each trial · ! refused or cannot send · ⚠ with a warning")

#: **What the editor says with no setting opened** (the summary and editor design's goal 5).
EDITOR_EMPTY = "click a setting above to change it"

#: **A section's line that opens its New color… panel** (the summary and editor design's call:
#: "the *New color…* panel opens from the Colors section's header in the summary, into the
#: editor"), and the prefix of its `data-open`, the section after it.
NEW_COLOR_LINE, NEW_COLOR_OPEN = "New color…", "new-color:"


def _hidden(markup: str) -> str:
    """A box's or a panel's markup with `hidden` on its own tag, for the editor (`_params`): the
    page's script shows the one opened (`openSetting`), last among its attributes. Every value
    this module writes in an attribute is escaped (`_e`), so its tag's first `>` closes it."""
    tag, close, rest = markup.partition(">")
    if not tag.startswith("<") or not close:
        raise ValueError("the editor hides an element")
    return f"{tag} hidden>{rest}"


def _entries(frame) -> list:
    """**Each box a frame's settings make, in the frame's order** (`_params`, `_summary`):
    `(section, row, None, (row,))` for a setting's own box, `(section, None, group, members)` for
    a group's (`Telemetry.groups`; the console interface rework's Task 7), which stands where its
    first setting would, by the first group naming each setting, a ceiling never (`check`'s
    `bad-group` refuses one at load); a group's settings have no box of their own. A row naming no
    section is under Other."""
    rows = {row.name: row for row in frame.params}
    grouped: dict = {}
    for group in frame.groups:
        for setting in group.settings:
            if setting in rows and not rows[setting].bounded:
                grouped.setdefault(setting, group)
    drawn: set = set()
    found = []
    for row in frame.params:
        section = row.section or OTHER
        group = grouped.get(row.name)
        if group is None:
            found.append((section, row, None, (row,)))
        elif group.name not in drawn:
            drawn.add(group.name)
            found.append((section, None, group,
                          [rows[name] for name in group.settings if grouped.get(name) is group]))
    return found


def _in_order(items: list) -> list:
    """**`(section, ...)` items in their sections' order** (the console settings design's §7; the
    PI, 2026-11-16: "The task file names it"; the summary and editor design's call: "the Ceilings
    section comes last"): each section in the order its first item comes, a subsection
    (`"Stimuli/fixation point"`) under its parent, which keeps its own items first, and Ceilings
    (`task.CEILINGS`) last. `[(top, {"own": [...], "subs": {sub: [...]}})]`."""
    tree: dict = {}
    for item in items:
        top, _, sub = item[0].partition("/")
        node = tree.setdefault(top, {"own": [], "subs": {}})
        (node["subs"].setdefault(sub, []) if sub else node["own"]).append(item)
    return ([(top, node) for top, node in tree.items() if top != CEILINGS]
            + [(top, node) for top, node in tree.items() if top == CEILINGS])


#: **A unit a summary line says short** (the ledger's ruling for the summary and editor build's
#: Task 2: "pick the columns and the summary's short units ('°', 'cd/m²') so that every line
#: still fits"): degrees as the sign, against the number ("2.0°"), and cd/m² with its square. The
#: box, its editor and *more* keep the setting's own unit.
_SHORT_UNITS = {"deg": "°", "cd/m2": "cd/m²"}


def _line_unit(row) -> str:
    """**What a summary line writes after a number of a setting** (`_number_said`, `_drawn_said`,
    and `data-unit` for the page's draft text, `_line`): a percent's `%` and a degree's `°`
    against it, a whole number's nothing ("4", the mock-up the PI chose: "Number of discs 4"),
    any other unit after a space, short where `_SHORT_UNITS` has it. **A special kind's share**
    (`task.SPECIAL_UNIT`, a whole percent) writes `%` too (the pop-out revision's whole-build
    review, M9: "0% · 0% · 0% · 0% · 0.50 s")."""
    if row.percent or row.unit == SPECIAL_UNIT:
        return "%"
    if row.whole or not row.unit:
        return ""
    unit = _SHORT_UNITS.get(row.unit, row.unit)
    return unit if unit == "°" else f" {unit}"


def _number_said(row, value: object) -> str:
    """**A number as a summary line says it** (`_summary_value`): at its box's decimals
    (`_figure`), a percent's ×100, with what the line writes after it (`_line_unit`)."""
    return f"{_figure(row, value)}{_line_unit(row)}"


#: **The numbers of a draw a summary line says as its range** (`ParamRow.shape`'s, by shape):
#: shortest to longest, low to high; a list's values from least to most.
_DRAW_ENDS = {"non_aging": ("shortest", "longest"), "uniform": ("low", "high"),
              "normal": ("low", "high")}

#: **What a summary line says in a value's place** where each trial has one of its own and no
#: shape says its range (the sources of `_PER_TRIAL`), in short; the line's title says it whole.
_PER_TRIAL_SHORT = {
    "conditions": "from conditions", "pool": "from pairings", "staircase": "by its staircase",
    "draw": "drawn each trial", "range": "drawn each trial", "form": "drawn each trial",
}


def _drawn_said(row) -> str | None:
    """**A draw in force as a summary line says it** (`ParamRow.shape`): its range, "0.5–1.25 s",
    each end every digit it holds (`_significant`), a percent's ×100; a scaling, its factor
    against `SCALED_UNIT`; with no shape, the range of the draw's live numbers a person may change
    (`ParamRow.numbers`, its `low` and `high`); `None` where none names a range."""
    shape = row.shape or {}
    kind = shape.get("shape")
    numbers = shape.get("numbers") or {}
    if not shape and row.source in ("draw", "range") and isinstance(row.numbers, dict):
        kind, numbers = "uniform", row.numbers
    if kind == "scaled":
        factor = numbers.get("factor")
        return None if factor is None else f"{_significant(float(factor))} {SCALED_UNIT}"
    if kind in _DRAW_ENDS:
        ends = [numbers.get(name) for name in _DRAW_ENDS[kind]]
    elif kind in ("list", "weights") and shape.get("values"):
        ends = [min(shape["values"]), max(shape["values"])]
    else:
        return None
    if not all(isinstance(end, (int, float)) and not isinstance(end, bool) for end in ends):
        return None
    if row.percent:
        return f"{_significant(_hundred(ends[0]))}–{_significant(_hundred(ends[1]))}%"
    return f"{_significant(float(ends[0]))}–{_significant(float(ends[1]))}{_line_unit(row)}"


def _summary_value(row, level: object = None) -> str:
    """**The value in force as a summary line says it** (the summary and editor design's call:
    "the summary's value is the rig's: rendered in Python from the same row the box uses"), plain
    text: a pool's "2 of 12"; a color's hue, or "from pairings" where its pool draws it; a value
    the training switch holds, in its words ("frozen at 0.60 s"); a position or an appearance in
    the rig's words, a choice among segments as its segment says it (`_choice_label`); a draw in
    force as its range, "0.5–1.25 s" (`_drawn_said`); a value each
    trial gives its own, in short (`_PER_TRIAL_SHORT`); else the number at its box's decimals with
    its unit (`_number_said`), a ceiling's too, or the value as written."""
    if row.members is not None:
        whole = _whole(row.value)
        total = len(row.members)
        if whole is None or not 1 <= whole < 1 << total:
            return _figure(row, row.value)
        return f"{sum(1 for member in row.members if whole & member.bit)} of {total}"
    if row.color is not None:
        hue = row.color.get("hue") if isinstance(row.color, dict) else None
        if hue:
            return str(hue)
        if row.source == "pool":
            return _PER_TRIAL_SHORT["pool"]
        return row.words if row.words is not None else _figure(row, row.value)
    held = _HELD_BY.get(row.source)
    if held is not None:
        return f"{held[0]} {_number_said(row, row.value)}"
    if row.position is not None:
        return row.position
    if row.words is not None and row.words in row.choices:
        # A look picked among its segments says what its segment says, "Ring" for "Ring:
        # inner fix_act_hole, outer ...", its words whole in the line's title (the pop-out
        # revision's Amendments, item 6: the summary still fits).
        return _choice_label(row.words, row.choices)
    if row.words is not None:
        return row.words
    drawn = _drawn_said(row)
    if drawn is not None:
        return drawn
    if (row.source == "staircase" and isinstance(level, (int, float))
            and not isinstance(level, bool)):
        # **A staircase's level in force after its words** (the pop-out revision's whole-build
        # review, M8, and its re-review, N1: "by its staircase · 9"): `level`, the value at the
        # level the frame's own staircase row is at (`Telemetry.staircase`, `_stepped`), never the
        # row's value, which is the run's start; a condition's or a pool's each trial's own, which
        # no frame carries, says its words alone.
        return f"{_PER_TRIAL_SHORT['staircase']} · {_number_said(row, level)}"
    if row.source in _PER_TRIAL_SHORT:
        return _PER_TRIAL_SHORT[row.source]
    if isinstance(row.value, (int, float)) and not isinstance(row.value, bool):
        return _number_said(row, row.value)
    return _figure(row, row.value)


def _widest(row) -> str:
    """**The widest value a summary line of `row` can say** (the pop-out revision's whole-build
    review, I1: turning special trials on reflowed the summary, its columns sized from the values
    in force), so the columns never move with a value: the value in force, and beside it what its
    setting can come to show -- a number at each declared bound (a share's "100%", a set size's
    "36"), after the words of what gives it where a staircase or the training switch does ("by its
    staircase · 36"); a pool's "12 of 12"; each hue its color card offers; each choice's segment.
    A number with an open side is said at its value in force there, which no rig value changes
    but a person's own. Formatting, not derivation."""
    said = [_summary_value(row)]
    if row.members is not None:
        said.append(f"{len(row.members)} of {len(row.members)}")
    elif row.color is not None:
        sets = row.color.get("sets") if isinstance(row.color, dict) else None
        for entry in (sets.values() if isinstance(sets, dict) else ()):
            hues = entry.get("hues") if isinstance(entry, dict) else None
            said += [str(hue) for hue in (hues or {})]
        said.append(_PER_TRIAL_SHORT["pool"])
    elif row.choices:
        said += [_choice_label(words, row.choices) for words in row.choices]
    elif row.position is None and not isinstance(row.value, str):
        for end in (row.low, row.high):
            if isinstance(end, (int, float)) and not isinstance(end, bool) and math.isfinite(end):
                number = _number_said(row, end)
                said.append(number)
                if row.source == "staircase":
                    said.append(f"{_PER_TRIAL_SHORT['staircase']} · {number}")
                if row.source in _HELD_BY:
                    said.append(f"{_HELD_BY[row.source][0]} {number}")
    return max(said, key=len)


def _stepped(frame) -> tuple:
    """**The setting the frame's staircase steps and the value at its level in force**
    (`Telemetry.staircase`: its setting, its levels and the level it is at), or `("", None)` with
    none, for `_summary_value`. Formatting, not derivation."""
    row = getattr(frame, "staircase", None)
    if row is None:
        return "", None
    try:
        return row.setting, row.levels[row.level]
    except (IndexError, TypeError):
        return "", None


def _drawn(row) -> bool:
    """**Whether a summary line marks its value ◆, drawn each trial** (the summary and editor
    design's goal 3): a value its conditions, its draw, its pool or its staircase gives each trial
    (`_PER_TRIAL`), a person's draw among them -- not a size scaled by eccentricity, whose objects
    each have their own but no trial draws."""
    if row.source not in _PER_TRIAL:
        return False
    return not (row.shape is not None and row.shape.get("shape") == "scaled")


def _waits(row, change, now: str) -> str:
    """**A line's value with what waits for the next trial after an arrow** (the summary and
    editor design's goal 3: "in force → waiting"): a number's unit once, after what waits ("0.30 →
    0.50 s"), anything else as it is, then the arrow; `now` alone where nothing waits."""
    if change is None:
        return now
    becomes = _plain(_becomes(change, row))
    if not change.hands_back and becomes in row.choices:
        # A choice picked among segments, as its segment says it (`_summary_value`).
        becomes = _choice_label(becomes, row.choices)
    if (not change.hands_back and isinstance(change.now, (int, float))
            and not isinstance(change.now, bool) and row.members is None
            and now == _number_said(row, row.value)):
        return f"{_figure(row, row.value)} → {_number_said(row, change.now)}"
    return f"{now} → {becomes}"


def _line(name: str, label: str, codes: str, now: str, shown: str, state: str, said: str,
          drawn: bool, changed: bool, bounded: bool, words: str, unit: str | None = None,
          whole: str = "") -> str:
    """**One summary line** (the summary and editor design's goal 1), a button that opens its
    setting in the editor (`data-open`, its box's `data-card`): its marks (`span.mk`), its plain
    name (`span.ln`) and its value in force (`span.lv`, the in force alone in `data-now`), with
    what waits after an arrow. The marks the rig knows (the design's call on combined states):
    ◷ a change waiting (`waiting`), else ! a refusal (`refused`), else ⚠ a warning (`warned`), as
    the box's status line ranks them (`_status`), then ◆ a value drawn each trial (`drawn`); and
    the classes `changed` (it differs from the task's start) and `ceiling`. Its `title` says
    every state in words: the whole name, the value -- and a choice's words whole (`whole`) where
    the line says it in short -- the status line whole, how it is drawn, changed, a ceiling.

    **What the page reads to add what it alone knows** (the summary and editor build's Task 2,
    `markLine` in the script): `data-now`, the value in force alone, for "in force → draft";
    `data-said`, the status said in the title, where there is one, which the page's own words
    replace or join; and `data-unit`, on a number's line, what the line writes after a number
    (`_line_unit`: "%", "°", " s", nothing for a whole number), so a draft is said as the value in
    force is, its typed text read from the box's own field."""
    mark, kind = {"staged": ("◷", "waiting"), "refused": ("!", "refused"),
                  "warned": ("⚠", "warned")}.get(state, ("", ""))
    classes = " ".join(word for word in ("line", kind, "drawn" if drawn else "",
                                         "changed" if changed else "",
                                         "ceiling" if bounded else "") if word)
    named = label if label == codes else f"{label} ({codes})"
    told = [named, shown] + ([whole] if whole and whole != shown else [])
    status = _whole_say(state, said) if state else ""
    if status:
        told.append(status)
    if drawn:
        told.append(words)
    if changed:
        told.append("changed from the task's start")
    if bounded:
        told.append("a welfare ceiling: sent alone, by its own Apply")
    extra = f' data-said="{_e(status)}"' if status else ""
    if unit is not None:
        extra += f' data-unit="{_e(unit)}"'
    return (f'<button type="button" class="{classes}" data-open="{_e(name)}"{extra} '
            f'title="{_e(" · ".join(told))}"><span class="mk">{mark}{"◆" if drawn else ""}</span>'
            f'<span class="ln">{_e(label)}</span><span class="lv" data-now="{_e(now)}">'
            f"{_e(shown)}</span></button>")


def _summary(frame, view: View, training: bool) -> str:
    """**The summary of a settings tab** (the summary and editor design's goal 1; the PI,
    2026-11-19: "perhaps some way to visualize all params at top and clicking opens the ability to
    change it below", mock-up A): one line per box `_params` draws (`_line`), a group's one
    (its title, its settings' values joined by " · "; special trials' shares only those on,
    `_shares_said`), in its sections (`_sections`), the Ceilings section last; a section holding a
    color card ends with a *New color…* line that opens its panel. Each line's value is the rig's
    (`_summary_value`); the page's script adds what it alone knows. `view` is the boxes' (nothing
    here is gated: a line sends nothing)."""
    staged = {change.name: change for change in frame.staged}
    refused = {refusal.name: refusal for refusal in frame.refusals}
    peers = _percents(frame)
    entries = [entry for entry in _entries(frame) if _training(entry[0]) == training]
    lines = []
    widths = [_line_width(NEW_COLOR_LINE, "")]
    stepped, level = _stepped(frame)
    for section, row, group, members in entries:
        if group is None:
            change = staged.get(row.name)
            state, said = _status(row, change, refused.get(row.name), peers)
            now = _summary_value(row, level if row.name == stepped else None)
            drawn = _drawn(row)
            words = _plain(_PER_TRIAL[row.source][0]) if drawn else ""
            number = (row.members is None and row.color is None and row.position is None
                      and not isinstance(row.value, str))
            shown = _waits(row, change, now)
            widths.append(_line_width(row.label or row.name, _widest(row)))
            lines.append((section, 1 if row.changed else 0, _line(
                row.name, row.label or row.name, row.name, now, shown,
                state, said, drawn, row.changed, row.bounded, words,
                _line_unit(row) if number else None,
                row.words if row.words is not None and row.words in row.choices else ""), 1))
            continue
        state, said = _group_state(members, frame, staged)
        values = [_summary_value(member, level if member.name == stepped else None)
                  for member in members]
        now = " · ".join(values)
        shown = " · ".join(_waits(member, staged.get(member.name), value)
                           for member, value in zip(members, values))
        drawn = [member for member in members if _drawn(member)]
        words = "; ".join(f"{member.label or member.name} {_plain(_PER_TRIAL[member.source][0])}"
                          for member in drawn)
        changed = sum(1 for member in members if member.changed)
        whole = ""
        if any(member.unit == SPECIAL_UNIT for member in members):
            # **A group of special trials' shares says only the shares that are on** (the PI,
            # 2026-11-20, from his try-out: "Shorter line, no cut"), each in short words, or
            # "none", or where that would not fit, how many kinds and their sum
            # (`_shares_said`), judged once the columns' width is known, below; every setting
            # of the group whole in its title.
            whole = " · ".join(
                f"{member.label or member.name} {_waits(member, staged.get(member.name), value)}"
                for member, value in zip(members, values))
        # **A group's line is not sized by its values** (I1): its name shows whole; a group's
        # values may cut with an ellipsis, whole in its title, but special trials' never do.
        widths.append(_line_width(group.name, ""))
        lines.append((section, changed, (
            group.name, group.name, ", ".join(member.name for member in members), now, shown,
            state, said, bool(drawn), bool(changed), False, words, None, whole, members),
            len(members)))
    colored = {section for section, row, group, _ in entries
               if group is None and isinstance(row.color, dict) and row.color.get("sets")}
    panels = {section: f'<button type="button" class="line newcolor" '
                       f'data-open="{_e(NEW_COLOR_OPEN + section)}" title="{_e(NEW_COLOR_LINE)} '
                       f'{_e(section)}: define a color and save it as a proposal"><span class="mk">'
                       f'</span><span class="ln">{_e(NEW_COLOR_LINE)}</span><span class="lv">'
                       f"</span></button>" for section in colored}
    run = f"{frame.session_id}/{frame.run_index}" if frame.phase == "running" else ""
    width = max(widths)
    for at, (section, changed, made, counted) in enumerate(lines):
        if isinstance(made, tuple):
            *fields, whole, members = made
            if whole:
                fields[3], fields[4] = _shares_said(fields[0], members, staged,
                                                    max(width, SUMMARY_FLOOR_CH))
            lines[at] = (section, changed, _line(*fields, whole), counted)
    return _sections(frame.task, lines, run, panels, width)


#: **The most of its line a value takes** (`.line > .lv`'s `max-width` in the page's CSS), so a
#: special trials' line is judged to fit as the page lays it out (`_shares_said`).
LINE_VALUE_SHARE = 0.62
#: **A value's character as wide as it is drawn**, in the summary's `ch`: IBM Plex Mono at 12 px,
#: 7.2 px each, every character alike (measured in Chromium and WebKit on 2026-11-19, the build's
#: `task-3-report.md`, and again on 2026-11-20: "4 kinds · 400% of trials", 24 characters, is
#: 172.8 px in both; layout, not timing), where `_VALUE_CH` takes it as 0.9 to spare. A special
#: trials' line is judged with it (`_shares_said`), its name and padding still by the estimate that
#: is never short, and the browser test holds the line uncut at three widths in both engines.
_MONO_CH = 7.2 / 8.4


def _share_words(members: list) -> dict:
    """**Each special trials' share by its short words** (`_shares_said`): its plain name, less a
    closing "trials", lower case, cut to its last words that tell it from every other share of the
    group -- the pop-out's "absent", "empty", "distractor alone" and "disc alone". Formatting, not
    derivation."""
    named = {}
    for member in members:
        if member.unit != SPECIAL_UNIT:
            continue
        words = (member.label or member.name.removesuffix("_percent").replace("_", " ")).split()
        if len(words) > 1 and words[-1].lower() in ("trials", "trial"):
            words = words[:-1]
        named[member.name] = [word.lower() for word in words]
    short = {}
    for name, words in named.items():
        for count in range(1, len(words) + 1):
            tail = words[-count:]
            if all(other[-count:] != tail for key, other in named.items() if key != name):
                break
        short[name] = " ".join(tail)
    return short


def _shares_said(name: str, members: list, staged: dict, width: float) -> tuple[str, str]:
    """**A special trials group's summary line, in force and with what waits** (the PI,
    2026-11-20, from his try-out: "Shorter line, no cut"; the controller's ruling for the form that
    does not fit): only the shares that are on, each in short words (`_share_words`), "absent 10% ·
    distractor alone 5%", one waiting to change said with its arrow ("absent 0% → 10%"); "none"
    with every share at 0. **Where that would not fit its column** -- `width`, the summary's
    columns in `ch` at their narrowest, the name and padding by the estimate that is never short
    (`_line_width`), the value as drawn (`_MONO_CH`) and at most `LINE_VALUE_SHARE` of the line --
    how many kinds are on and their sum, "4 kinds · 400% of trials",
    from the values in force; its title says every setting of the group whole (`_summary`). The
    group's other settings, a catch's hold, are left off the line: they matter only while a
    share is on, and the editor and the title say them. Formatting, not derivation."""
    short = _share_words(members)
    shares = [member for member in members if member.name in short]

    def on(value) -> bool:
        return isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0

    def said(items) -> str:
        return " · ".join(items) if items else "none"

    now = [f"{short[member.name]} {_summary_value(member)}" for member in shares
           if on(member.value)]
    shown = []
    for member in shares:
        change = staged.get(member.name)
        waiting = change is not None and not change.hands_back and on(change.now)
        if on(member.value) or waiting:
            shown.append(f"{short[member.name]} "
                         f"{_waits(member, change, _summary_value(member))}")

    def fits(text: str) -> bool:
        value = len(text) * _MONO_CH
        return _line_width(name, "") + value <= width and value <= LINE_VALUE_SHARE * width

    if fits(said(now)) and fits(said(shown)):
        return said(now), said(shown)
    kinds = len(now)
    total = sum(member.value for member in shares if on(member.value))
    counted = (f"{kinds} kind{'' if kinds == 1 else 's'} · {_significant(float(total))}% of "
               f"trials") if kinds else "none"
    return counted, counted


#: **How wide a summary line's characters are, in the summary's `ch`** (the ledger's ruling for the
#: summary and editor build's Task 3: "size the summary's columns from the tab's own longest
#: line"), measured in WebKit and Chromium on 2026-11-19 (layout, not timing; the build's
#: `task-3-report.md`): the summary's `ch` is 8.4 px (IBM Plex Sans at 14 px); a plain name is
#: IBM Plex Sans at 12.5 px, its characters 0.24 to 0.93 em wide, taken here by the widest of four
#: kinds -- narrow (0.38 em: "i", "l", "t", "f", "r", a space, most punctuation), wide (0.93 em:
#: "m", "w", "M", "W", "%", "@", "→", "…"), any other capital (0.72 em), anything else (0.6 em) --
#: so an estimate is never short (over the pop-out's own names it is 13 to 20 % long); a value is
#: IBM Plex Mono at 12 px, 7.2 px a character, taken as 0.9 ch; and a line's padding, its marks'
#: 2 em and its gaps take 40 px, taken as 5.5 ch with 6 px to spare.
_NARROW = frozenset(" 'ijlftr/,.!:;|[](){}·²\\")
_WIDE = frozenset("mwMW%@→…")
_NAME_CH = 12.5 / 8.4
_VALUE_CH = 0.9
_LINE_CH = 5.5
#: **The narrowest a summary's columns are** (an engineering default: four columns of a 1280 wide
#: window beside the demo screen, the summary and editor design's goal 1), in `ch`.
SUMMARY_FLOOR_CH = 24.0


def _line_width(label: str, shown: str) -> float:
    """**How wide a summary line must be for its plain name and its value to show whole**, in the
    summary's `ch` (`_NAME_CH`, `_VALUE_CH`, `_LINE_CH`), as the summary's columns take it from
    its longest line (`_summary`, `_sections`): the widest value its setting can show
    (`_widest`), never the value in force alone, nor what waits after an arrow or a draft, so a
    change applied, waiting or typed never moves the columns and the editor under the pointer
    (the design's anti-goal; the pop-out revision's whole-build review, I1); a group's line by
    its name alone. Any may cut with an ellipsis, its whole in the line's title."""
    name = sum(0.38 if char in _NARROW else 0.93 if char in _WIDE else 0.72 if char.isupper()
               else 0.6 for char in label)
    return name * _NAME_CH + len(shown) * _VALUE_CH + _LINE_CH


def _group_state(members: list, frame, staged: dict) -> tuple[str, str]:
    """**A group's state and status line, as its box ranks them** (`_group_box`): a change of it
    waiting, the last refusal of any of its settings, the change in force latest, else
    `GROUP_REST`; its marks on its summary line (`_line`)."""
    by_name = {row.name: row for row in members}
    change = next((staged[row.name] for row in members if row.name in staged), None)
    if change is not None:
        return "staged", f"{WAITING} · {_who(change.by)}"
    refusal = None
    for one in frame.refusals:
        if one.name in by_name:
            refusal = one
    if refusal is not None:
        row = by_name[refusal.name]
        value = "" if refusal.value is None else f" {_e(_refused_value(row, refusal.value))}"
        gist = _gist(_in_percent(row, refusal.why, _percents(frame)))
        return "refused", f"refused {_e(row.label or row.name)}{value} · {_e(gist)}"
    applied = [row for row in members if row.applied is not None]
    if applied:
        last = max(applied, key=lambda row: row.applied.trial)
        if last.warned:
            return "warned", f"in force, with a warning · from trial {_e(last.applied.trial)}"
        return "applied", f"in force from trial {_e(last.applied.trial)}"
    return "", _e(GROUP_REST)


def _echoes(row) -> bool:
    """**Whether a box's field shows the value its head would** (the ledger's density ruling for
    the console interface rework's Task 8: "the head shows the value in force only when it differs
    from the field (a draft or a waiting change, e.g. "2.0 → 1.5"), not twice"): a number or a word
    in a field of its own, as `_entry`'s last branch draws it -- not a value held by the training
    switch, given each trial, a position, an appearance, a color, a pool, or a setting picked among
    its choices' segments, whose head is the only place the value in force is said. Its box carries `data-echo`, and the page's CSS hides the
    head's value at rest while it does."""
    settable = row.value is None or isinstance(row.value, str) or (
        isinstance(row.value, (int, float)) and not isinstance(row.value, bool))
    scaled = (row.switch == "scaled" and row.shape is not None
              and row.shape.get("shape") == "scaled")
    return (settable and row.members is None and row.color is None and not scaled
            and _HELD_BY.get(row.source) is None and _PER_TRIAL.get(row.source) is None
            and row.position is None and row.words is None and not row.choices)


#: **What a box's *more* says on its ⋯** (the ledger's density ruling for Task 8: "*more* becomes a
#: ⋯ in the box's head, not its own line"), for a screen reader and a pointer's tooltip.
MORE_SAID = "more: what it is, its limits and why, where its value comes from"


def _pin(name: str) -> str:
    """**A box's pin**, `name` its `data-card` as escaped there (the console interface design's goal 9; the PI, 2026-11-19: "Yes, you choose
    only"), the first thing in its *more*: it puts a working copy of the box in Runtime's Pinned
    strip, or takes it away, kept per task in this browser (the page's script); nothing is
    pinned until a person pins it. It sends nothing, so no gate grays it."""
    return (f'<button type="button" class="btn small pin" data-pin-toggle="{name}" '
            f'aria-pressed="false">pin to Runtime</button>')


def _entry(row, view: View, unit: bool = True) -> tuple[str, str]:
    """**A setting's value in force and its field**, as its box's head and editor show them
    (`_params`): a value held by the training switch, given by its conditions, its draw, its pool
    or its scaling in those words with a field to set one value over them (`_over`); a position or
    an appearance in the rig's words, with none; else the value and its unit, with its field
    (`_field`; `unit`, as there) where it is a number or a word. **A setting whose row gives its
    choices by their words** (`ParamRow.choices`) has its segments in place of any field
    (`_choice_segments`; the pop-out revision's Task 5b). Escaped markup, both."""
    settable = row.value is None or isinstance(row.value, str) or (
        isinstance(row.value, (int, float)) and not isinstance(row.value, bool))
    per_trial = _PER_TRIAL.get(row.source)
    scaled = (row.switch == "scaled" and row.shape is not None
              and row.shape.get("shape") == "scaled")
    if scaled and row.source == "form":
        per_trial = _SCALED
    held_by = _HELD_BY.get(row.source)
    if held_by is not None:
        label = (f'<span class="pv">{held_by[0]} {_e(_figure(row, row.value))} '
                 f'<span class="unit">{_e(_unit_of(row))}</span></span>')
        entry = _over(row, held_by[1], view) if settable and row.position is None else ""
    elif per_trial is not None:
        label = f'<span class="pv">{per_trial[0]}</span>'
        entry = _over(row, per_trial[1], view) if settable and row.position is None else ""
    elif row.position is not None:
        label, entry = f'<span class="pv">{_e(row.position)}</span>', ""
    elif row.words is not None:
        # An appearance or a color in the rig's words (`ParamRow.words`; XC-420), no field:
        # a color setting's is picked on its color card, below.
        label, entry = f'<span class="pv">{_e(row.words)}</span>', ""
    else:
        label = (f'<span class="pv">{_e(_figure(row, row.value))} '
                 f'<span class="unit">{_e(_unit_of(row))}</span></span>')
        entry = _field(row, view, unit) if settable else ""
    if row.choices and row.members is None and row.color is None:
        # Its declared choices by their words, as segments (`ParamRow.choices`; the pop-out
        # revision's Task 5b), in place of a field: a look, or a word, is picked, never typed.
        entry = _choice_segments(row, view)
    return label, entry


def _choice_label(words: str, choices: tuple) -> str:
    """**What a choice's segment says** (`_choice_segments`): `link.choice_label`, which the
    changes feed and the moments say a choice by too. Formatting, not derivation."""
    return choice_label(words, choices)


def _choice_segments(row, view: View) -> str:
    """**A setting's declared choices as segments** (`ParamRow.choices`, each choice by its words;
    the pop-out revision's design §2, a look's shape "a setting on the console"; its plan's Task
    5b): one button for each, in the order declared, saying it in short (`_choice_label`) and
    whole in its title, the choice in force pressed -- the value's words, or the word it is, none
    where each trial gives its own. Pressing one is a draft of its box, as a hue's swatch is,
    which the box's Apply sends as `choice`, `link.SetChoice`, by the words, staged until the next
    trial. Greyed away from the box."""
    name, off = _e(row.name), _gate(view)
    held = (None if _PER_TRIAL.get(row.source) is not None
            else row.words if row.words is not None else row.value)
    buttons = []
    for words in row.choices:
        on = words == held
        # The title rides on a span: the sign-in takes a gated button's own (`applySignIn`).
        buttons.append(
            f'<span class="chw" title="{_e(words)}">'
            f'<button type="button" class="btn small seg ch{" on" if on else ""}" '
            f'data-name="{name}" data-choice="{_e(words)}" '
            f'aria-pressed="{"true" if on else "false"}"{off}>'
            f"{_e(_choice_label(words, row.choices))}</button></span>")
    return (f'<div class="sw chs" role="group" data-choices="{name}" '
            f'aria-label="{name}: its choices">{"".join(buttons)}</div>')


def _editor(row, frame, view: View) -> tuple[str, str]:
    """**A box's head value and its editor** (`_params`): a timing card's switch and its fixed and
    drawn sides, a size's fixed and scaled sides, a color's set and swatches, a pool's grid of
    pairs (`_pairings`, its head how many it holds), else its field (`_entry`)."""
    label, entry = _entry(row, view)
    if row.members is not None:
        # A pool's pairings as a grid (the console interface design's goal 7), whatever gives it.
        return (f'<span class="pv">{_e(_pooled(row, row.value))}</span>',
                _pairings(row, view))
    if row.switch == "drawn":
        drawn = row.shape is not None
        return label, (_switch(row, view, drawn)
                       + f'<div class="side fixed" data-side="fixed"{" hidden" if drawn else ""}>'
                       f"{entry}</div>"
                       + f'<div class="side drawn" data-side="drawn"{"" if drawn else " hidden"}>'
                       f"{_drawn_side(row, view)}</div>")
    if row.switch == "scaled":
        scaled = row.shape is not None and row.shape.get("shape") == "scaled"
        return label, (_switch(row, view, scaled, "scaled")
                       + f'<div class="side fixed" data-side="fixed"{" hidden" if scaled else ""}>'
                       f"{entry}</div>"
                       + f'<div class="side scaled" data-side="scaled"{"" if scaled else " hidden"}>'
                       f"{_scaled_side(row, view)}</div>")
    if row.color is not None:
        # A color setting: its set, its hues as swatches, its two levels (the design's §6).
        return label, _color_card(row, frame, view)
    return label, entry


#: **What a group's box says at rest** (the console interface design's goal 8), its status line.
GROUP_REST = "applied together, by one Apply"
#: **The trials a special trials group leaves normal**, said after its sentence (the console
#: interface design's goal 8: "the remainder shown as "normal search""; the pop-out revision's
#: Amendments, item 4). The words are the pop-out's, the one task that declares special trials:
#: a frame names no task's default structure, and a second task's words wait for a field that
#: carries them (XC-544).
NORMAL_REST = "normal search"


def _rest_said(total: float) -> str:
    """**A special trials group's remainder**, from its shares' sum (`check.special_share` each,
    as the draw reads them): "N normal search" below 100, "none normal search" at 100, and past it
    the `specials-over-100` warning's words after it (`check.IN_PROPORTION`). The script says the
    same from the box's fields while a draft is open (`restOf`)."""
    from wl_xcon.check import IN_PROPORTION

    if total < 100:
        return f"{100 - total:g} {NORMAL_REST}"
    return f"none {NORMAL_REST}" + (f": {IN_PROPORTION}" if total > 100 else "")


def _sentence_unit(row, sentence: str) -> bool:
    """**Whether a group's sentence shows a setting's unit beside its field** (the pop-out
    revision's whole-build review: "a catch is held [0.50] s"): a setting of a unit the sentence
    does not name -- not a whole count, which the sentence counts in words, nor a percent or a
    share, whose `%` the field shows -- where the sentence does not write it after the field."""
    if row.whole or row.percent or row.unit == SPECIAL_UNIT or not row.unit:
        return False
    for literal, field, _, _ in string.Formatter().parse(sentence):
        if field == row.name:
            after = sentence.partition("{" + field + "}")[2].lstrip()
            unit = _SHORT_UNITS.get(row.unit, row.unit)
            return not (after.startswith(unit) or after.startswith(row.unit))
    return True


def _rest(rows: list) -> str:
    """**The remainder a group holding special trials' shares says after its sentence**
    (`_rest_said`), on a line of its own naming the shares (`data-shares`) and carrying the words
    the script needs (`data-words`, `data-over`); "" for a group holding no share. A share is a
    setting in `task.SPECIAL_UNIT`, the unit `check`'s `bad-special` holds every special kind's
    share to."""
    from wl_xcon.check import IN_PROPORTION, special_share

    shares = [row for row in rows if row.unit == SPECIAL_UNIT]
    if not shares:
        return ""
    total = sum(special_share(row.value) for row in shares)
    names = " ".join(row.name for row in shares)
    return (f'<div class="gr" data-shares="{_e(names)}" data-words="{_e(NORMAL_REST)}" '
            f'data-over="{_e(IN_PROPORTION)}">{_e(_rest_said(total))}</div>')


def _group_box(group, rows: list, frame, view: View, staged: dict, acts: dict) -> str:
    """**A group's one box** (`Telemetry.groups`, a `link.GroupRow`; the console interface design's
    goal 8; the PI, 2026-11-19: "One box after Timing"), laid out as `_box`'s, its markup the
    script's too, `data-card` the group's title and `group` among its classes:

    - its head: the title, its settings' code names small, and each one's value in force with what
      waits for the next trial after an arrow;
    - its editor: the group's sentence with each setting's field in its place, the unit left to
      the sentence but a percent's `%` (`_field`'s `unit`) -- "Move up when at least [80] % of the
      last [50] answers are right" -- or, where it declares none, each setting's field under its
      plain name;
    - its status: one line for the whole box -- a change of it waiting, the last refusal of any of
      its settings (named), the change in force latest, else `GROUP_REST` -- *withdraw* for a change
      waiting under a command id, which takes back the whole act ("withdraw all 2"), then Discard
      and Apply. **Its Apply is one act**: the script sends every setting it changed as one
      `apply_many` under one command id, judged and staged together, or refused whole;
    - its *more*: each setting's plain name, what it is, its limits and why, where its value comes
      from and *hand back*, what waits, its warnings and its last refusal whole. A draw's live
      numbers are not offered here: the box's one Apply sends its fields' values (`_whence`'s
      `ranges`).

    A ceiling is never in one (`check`'s `bad-group`: "a reward size is sent alone, by its own
    Apply"); `_params` leaves any a frame names out."""
    title, off = _e(group.name), _gate(view)
    by_name = {row.name: row for row in rows}
    peers = _percents(frame)
    codes = ", ".join(row.name for row in rows)
    names = (f'<span class="names"><span class="lbl" title="{title}">{title}</span>'
             f'<span class="code" title="{_e(codes)}">{_e(codes)}</span></span>')
    entries = {row.name: _entry(row, view, unit=not group.sentence
                                or _sentence_unit(row, group.sentence)) for row in rows}
    shown = []
    for row in rows:
        shown.append(_awaited(entries[row.name][0], staged.get(row.name), row))
    now = " · ".join(shown)
    if group.sentence:
        pieces = []
        for literal, field, _, _ in string.Formatter().parse(group.sentence):
            if literal:
                pieces.append(f'<span class="gs">{_e(literal)}</span>')
            if field is not None:
                pieces.append(entries[field][1] if field in by_name
                              else f'<span class="gs code">{_e(field)}</span>')
        editor = f'<div class="sentence">{"".join(pieces)}</div>{_rest(rows)}'
    else:
        editor = "".join(f'<div class="gm"><span class="gl">{_e(row.label or row.name)}</span>'
                         f"{entries[row.name][1]}</div>" for row in rows)
    changes = [staged[row.name] for row in rows if row.name in staged]
    change = changes[0] if changes else None
    refusal = None
    for one in frame.refusals:
        if one.name in by_name:
            refusal = one
    applied = [row for row in rows if row.applied is not None]
    last = max(applied, key=lambda row: row.applied.trial) if applied else None

    def line(refused) -> tuple[str, str]:
        if change is not None:
            return "staged", f"{WAITING} · {_who(change.by)}"
        if refused is not None:
            row = by_name[refused.name]
            value = ("" if refused.value is None
                     else f" {_e(_refused_value(row, refused.value))}")
            gist = _gist(_in_percent(row, refused.why, peers))
            return "refused", f"refused {_e(row.label or row.name)}{value} · {_e(gist)}"
        if last is not None:
            if last.warned:
                return "warned", f"in force, with a warning · from trial {_e(last.applied.trial)}"
            return "applied", f"in force from trial {_e(last.applied.trial)}"
        return "", _e(GROUP_REST)

    state, said = line(refusal)
    more = [_pin(title)]
    for row in rows:
        bits = [f'<span class="gn">{_e(row.label or row.name)}</span>']
        if row.help:
            bits.append(f'<span class="what">{_e(row.help)}</span>')
        bits.append(f'<span class="range">{_range(row)}</span>')
        bits.append(_whence(row, view, _beneath(row, frame), ranges=False))
        if row.gives is not None:
            bits.append(f'<span class="src gives">gives {_e(row.gives)}</span>')
        waiting = staged.get(row.name)
        if waiting is not None:
            bits.append(f'<span class="stg">staged → {_becomes(waiting, row)} by '
                        f"{_who(waiting.by)}</span>")
        bits.extend(f'<span class="wrn">warning: {_e(_in_percent(row, warned, peers))}</span>'
                    for warned in row.warned)
        if refusal is not None and refusal.name == row.name:
            bits.append(f'<span class="rfs">last refused: '
                        f'{_e(_in_percent(row, refusal.why, peers))}</span>')
        more.append(f'<div class="gmore" data-member="{_e(row.name)}">{"".join(bits)}</div>')
    marks = []
    if change is not None and change.cid:
        marks.append(f' data-staged-cid="{_e(change.cid)}"')
    if refusal is not None:
        marks.append(f' data-refusal="{_e(refusal.cid or refusal.why)}"')
        if refusal.cid:
            marks.append(f' data-refusal-cid="{_e(refusal.cid)}"')
    if last is not None:
        marks.append(f' data-applied="{_e(last.applied.trial)}"')
    under = next((said for said in (_under(row, staged.get(row.name)) for row in rows) if said), "")
    if under:
        marks.append(f' data-under="{_e(under)}"')
    if all(_echoes(row) for row in rows):
        marks.append(" data-echo")
    rest = ""
    if state == "refused":
        rest_state, rest_said = line(None)
        rest = f' data-rest="{_e(_plain(rest_said))}" data-rest-state="{rest_state}"'
    together = tuple(acts.get(change.cid, ())) if change is not None and change.cid else ()
    classes = " ".join(word for word in ("box", "group", "wide", state) if word)
    return (
        f'<div class="{classes}" data-card="{title}"{"".join(marks)}>'
        f'<div class="head">{names}<span class="now" title="{_e(_plain(now))}">{now}</span></div>'
        f'<div class="editor">{editor}</div>'
        f'<div class="status"><span class="say" title="{_e(_whole_say(state, said))}"{rest}>'
        f'{said}</span><span class="acts">{_withdraw(change, together, view)}'
        f'<button type="button" class="btn small" data-discard="{title}" tabindex="0"{off}>'
        f'Discard</button><button type="button" class="btn small primary" '
        f'data-apply="{title}" tabindex="0"{off}>Apply</button></span></div>'
        f'<details class="more"><summary aria-label="{_e(MORE_SAID)}" title="{_e(MORE_SAID)}">⋯'
        f'</summary><div class="detail">{"".join(more)}</div></details></div>'
    )


def _training(section: str) -> bool:
    """**Whether a section is the Training tab's** (`task.TRAINING_SECTION`, or one under it; the
    console settings design's §8: "the tab gathers everything a task declares as training"), and
    so not the Task parameters tab's."""
    return section.partition("/")[0] == TRAINING_SECTION


def _training_params(frame: Telemetry | None, view: View) -> str:
    """**The settings of every section under Training** (`_training`; the console settings
    design's §8), as the Task parameters tab lays its own out (`_params`: the summary, in its
    sections, and the editor), each box as `_params` makes it; a line saying none where the task
    declares none."""
    if frame is None:
        return _NONE
    if not any(_training(row.section or OTHER) for row in frame.params):
        return '<span class="nm">this task declares no Training section</span>'
    whole = _params(dataclasses.replace(frame, params=tuple(
        row for row in frame.params if _training(row.section or OTHER))), view, training=True)
    return whole


#: **The training switch's positions as the Training tab offers them** (`link.Shaping`;
#: `task.SHAPING`), each with its label.
_SWITCHES = (("on", "on"), ("frozen", "frozen"), ("full", "full task"))

#: **Why *full task* is grayed** where the run's plan declares none (`Telemetry.full_task`; the
#: console settings design's §8).
NO_FULL_TASK = "this run's plan declares no full task, so there is none to play"


def _shaping(frame: Telemetry | None, view: View) -> str:
    """**The training switch** (`Telemetry.shaping`; the console settings design's §8; the PI,
    2026-11-16: "both, a freeze training option and a full task option"): *on · frozen · full
    task*, the position in force pressed, each sending `shaping` with its position (`link.Shaping`),
    staged to the next trial; *full task* grayed, saying why, where the plan declares none
    (`Telemetry.full_task`); a switch staged said beside it. A line saying why there is none for a
    run with no training progression, staircase or pool, and between runs."""
    if frame is None:
        return _NONE
    if frame.phase != "running":
        return '<span class="nm">no run in progress: no training to switch</span>'
    if not frame.shaping:
        return ('<span class="nm">this run has no training progression, no staircase and no pool, '
                'so there is no training to switch</span>')
    buttons = []
    for position, label in _SWITCHES:
        other = ""
        if position == "full" and not frame.full_task:
            other = f' disabled title="{_e(NO_FULL_TASK)}"'
        pressed = "true" if position == frame.shaping else "false"
        buttons.append(f'<button type="button" class="btn small" data-cmd="shaping" '
                       f'data-position="{position}" aria-pressed="{pressed}"'
                       f'{_gate(view, other)}>{label}</button>')
    staged = next((change for change in frame.staged if change.name == "shaping"), None)
    said = ("" if staged is None else
            f'<span class="stg">staged → {_e(dict(_SWITCHES).get(staged.now, staged.now))} by '
            f'{_who(staged.by)}</span>')
    why = ("" if frame.full_task
           else f'<span class="nm">full task: {_e(NO_FULL_TASK)}</span>')
    return (f'<div class="kv"><span>training</span><span class="selrow" role="group" '
            f'aria-label="training switch">{"".join(buttons)}</span></div>{said}{why}')


def _runtime_shaping(frame: Telemetry | None) -> str:
    """**The Runtime tab's one line for the training switch** (`rt-shaping`; the console settings
    design's §8), so nothing the Training tab holds is hidden: `training frozen · stage Crowd ·
    Training tab`; empty where the run has no switch, and between runs."""
    if frame is None or frame.phase != "running" or not frame.shaping:
        return ""
    state = {"on": "training on", "frozen": "training frozen", "full": "full task"}.get(
        frame.shaping, frame.shaping)
    return (f'<span class="nm">{_e(state)} · stage <b>{_e(frame.block)}</b> · '
            f'<label for="t-training" class="lnk">Training tab</label></span>')


def _count(settings: int, changed: int) -> str:
    """A section header's counts whole (`7 settings · 2 changed`; the console settings design's §7:
    "each header counts its settings and how many differ from the task's start"), its `title`
    in the summary, whose line says the settings alone (`_sections`)."""
    return f"{settings} setting{'' if settings == 1 else 's'} · {changed} changed"


def _sections(task: str, cards: list, run: str = "", panels: dict | None = None,
              width: float | None = None) -> str:
    """**The summary's lines in their sections** (the console settings design's §7; the PI,
    2026-11-16: "The task file names it"; the summary and editor design's goal 1): each `(section,
    changed, html, settings)` under the section its row names (`ParamRow.section`; a row naming
    none, one made by hand, under Other), **in the order each section's first setting is
    declared**, Ceilings last (`_in_order`), a subsection (`"Stimuli/fixation point"`) nested in
    its parent, which keeps its own lines first. Each is a `<div class="ssec" data-section=…>`
    headed by its name and how many settings it holds (`<h4>Timing · 6 settings</h4>`, a parent's
    taking in its subsections', a group's box counting each of its settings), on one line, the
    whole with how many changed from the task's start in its `title` (`_count`); sections no
    longer fold (the design's call: "the summary is short enough"). A section with no setting is
    not made. `panels` gives a section's *New color…* line, after its lines. `task` names the task
    (`data-task`: what the page keeps the opened setting and the pins under), and `run` the run in
    progress (`data-run`; "" between runs): the script drops every draft when it changes (the
    console interface design's call: "drafts ... dropped at the run's end"). `width`, in `ch`, is
    its columns' (`_line_width` of its longest line, never under `SUMMARY_FLOOR_CH`; the ledger's
    ruling for the build's Task 3), so a task of short names gets more columns than one of long."""
    panels = panels or {}

    def block(name: str, own: list, counted: list, inside: tuple = ()) -> str:
        settings = sum(item[3] for item in counted)
        whole = _count(settings, sum(item[1] for item in counted))
        label = name.rpartition("/")[2]
        said = f"{settings} setting{'' if settings == 1 else 's'}"
        lines = "".join(item[2] for item in own) + (panels.get(name, "") if own else "")
        head = f'<h4 title="{_e(label)} · {whole}">{_e(label)} · {said}</h4>'
        if inside and not own:
            # **A section of subsections alone keeps its header with its first** (the pop-out
            # revision's whole-build review, I1: WebKit honors no `break-after: avoid` on a header
            # whose section holds only sections, and left "Stimuli · 16 settings" alone at a
            # column's foot): the two in one block no column breaks (`.skeep`).
            head, inside = f'<div class="skeep">{head}{inside[0]}</div>', inside[1:]
        return (f'<div class="ssec" data-section="{_e(name)}">{head}{lines}'
                f'{"".join(inside)}</div>')

    parts = []
    for top, node in _in_order(cards):
        subs = tuple(block(f"{top}/{sub}", found, found) for sub, found in node["subs"].items())
        every = node["own"] + [one for found in node["subs"].values() for one in found]
        parts.append(block(top, node["own"], every, subs))
    wide = "" if width is None else (
        f' style="column-width: {math.ceil(max(width, SUMMARY_FLOOR_CH) * 10) / 10:g}ch"')
    return (f'<div class="summary" data-task="{_e(task)}" data-run="{_e(run)}"{wide}>'
            f'{"".join(parts)}</div>')


def _reverting(changes: tuple) -> str:
    """**What a revert to a moment would change**, as the rig previews it (`MomentRow.changes`; the
    engine C3 plan's science review, M-1: "a one-step preview listing each setting and the value
    it will take"), in the changes feed's words, escaped; or that it would change nothing now,
    which the rig refuses."""
    if not changes:
        return "would change nothing now"
    return "would change: " + "; ".join(map(_e, changes))


#: A moment's *revert to this* where a revert to it would change nothing now, which the rig
#: refuses: greyed, saying so (fix round 1 of the C3 plan's Task 18, review minor 7).
_NOTHING = ' disabled title="a revert to this would change nothing now"'


def _moments(frame: Telemetry | None, view: View) -> str:
    """**The moments of the run in progress a revert can go back to** (`Telemetry.moments`,
    telemetry schema 19; the C3 spec §8; TSK-43, the PI, 2026-10-07, "Yes, with revert": "any
    earlier state restored in one action, itself recorded"), newest first as the rig sends them
    and the run's start last, kept however many came after (review M-15): each with when it was
    kept, what was done then in the changes feed's words, and *revert to this*, which sends its
    change id (`Revert`), then what a revert to it would change (`_reverting`). The rig takes
    every task setting and drawn range back to that moment at the next trial, refusing it whole if
    any value is, and never a reward size. Greyed away from the box, and on a moment a revert to
    which would change nothing now. None between runs, when no revert reaches back."""
    if frame is None:
        return _NONE
    if not frame.moments:
        return '<span class="nm">no run in progress: no moment to go back to</span>'
    return "".join(
        f'<div class="kv"><span>{_clock_time(moment.at)} · {_e(moment.said)}</span>'
        f'<button type="button" class="btn small" data-cmd="revert" '
        f'data-change="{_e(moment.change)}"{_gate(view, "" if moment.changes else _NOTHING)}'
        f'>revert to this</button></div>'
        f'<div class="rv">{_reverting(moment.changes)}</div>'
        for moment in frame.moments
    )


def _setup(frame: Telemetry | None) -> str:
    """S9a §3's configuration information. Display mode is the setup the session runs
    in (direct-view spec §3); stimulus calibration has no source yet and says so. Also what
    the session is for, fixed for the session, and its color calibration (engine build B)."""
    if frame is None:
        return _NONE
    limit = (
        '<span class="nm">none: cage-side</span>'
        if frame.out_of_cage_limit_s is None
        else _clock(frame.out_of_cage_limit_s)
    )
    rows = (
        ("session", _e(frame.session_id)),
        ("subject", _e(frame.subject)),
        ("deployment", _e(frame.deployment)),
        ("task", '<span class="nm">no run yet</span>' if frame.task is None else _e(frame.task)),
        (
            "allocation",
            _e(frame.allocation)
            if frame.allocation
            else '<span class="nm">provisional: none given</span>',
        ),
        (
            "bounds config",
            _e(frame.bounds_config)
            if frame.bounds_config
            else '<span class="nm">not given</span>',
        ),
        ("daily fluid floor", f"{frame.floor_ml:.2f} mL"),
        ("out-of-cage limit", limit),
        ("for", _e(frame.session_kind)),
        ("display mode", _e(_setup_words(frame.view, frame.half_ipd_cm))),
        (
            "color calibration",
            '<span class="nm">none loaded: no run starts without one</span>'
            if frame.calibration is None
            else _e(frame.calibration),
        ),
        ("stimulus calibration", '<span class="nm">no source yet: S4 §9\'s id waits on V1 and V9</span>'),
    )
    return (
        '<dl class="dl">'
        + "".join(f"<dt>{name}</dt><dd>{value}</dd>" for name, value in rows)
        + "</dl>"
    )


def _end(frame: Telemetry | None) -> str:
    """The supplement owed, fluid session, out-of-cage and in-session time, and the
    stop reason (spec §4.2)."""
    if frame is None:
        return _NONE
    owed = (
        f'<span class="nm">{_UNKNOWN_DAY}</span>'
        if frame.shortfall_ml is None
        else f'<span class="big">{frame.shortfall_ml:.2f}</span><span class="unit">mL</span>'
    )
    cage = (
        '<span class="nm">cage-side · no out-of-cage interval</span>'
        if frame.out_of_cage_seconds is None
        else _clock(frame.out_of_cage_seconds)
    )
    in_session = (
        '<span class="nm">not recorded</span>'
        if frame.in_session_seconds is None
        else _clock(frame.in_session_seconds)
    )
    reason = (
        _e(frame.stopped_because)
        if frame.stopped_because
        else '<span class="nm">no run yet</span>'
        if frame.phase == "between_runs"
        else '<span class="nm">still running</span>'
    )
    resumed = (
        ""
        if frame.resumed_at is None
        else f'<p class="nm">{_e(_resumed_sentence(frame.resumed_at))}</p>'
    )
    return (
        f'<div class="owe"><h2>Supplement owed</h2>{owed}</div>'
        f"{resumed}"
        f'<dl class="dl"><dt>fluid session</dt><dd>{frame.fluid_session_ml:.2f} mL</dd>'
        f"<dt>out of cage</dt><dd>{cage}</dd>"
        f"<dt>in session</dt><dd>{in_session}</dd>"
        f"<dt>stop reason</dt><dd>{reason}</dd></dl>"
    )


def _question_banner(question: Question, view: View) -> str:
    """The answer a console owes on a far mark (P4d-2b spec §6.2), with a button for each
    of the frame's own answers, naming its mark and session: the page's script re-sends
    the time as typed with the one pressed, and only for a question this page raised
    (the b3a-2 plan, decision 10). Greyed away from the box."""
    buttons = "".join(
        f'<button type="button" class="btn small" data-answer="{_e(answer)}" '
        f'data-mark="{_e(question.mark)}" data-session="{_e(question.session_id)}"'
        f'{_gate(view)}>{_e(answer)}{"…" if answer == "amend" else ""}</button>'
        for answer in question.answers
    )
    return _banner(
        "warn",
        "Confirm",
        f"{_e(question.said)} · answer "
        f"{' or '.join(_e(answer) for answer in question.answers)} "
        f"(session {_e(question.session_id)}) {buttons}",
    )


def _new_session_button(view: View, why: str | None = None) -> str:
    """*new session* (the mockup's `a-new`): opens the page's *New session* dialog."""
    off = _gate(view, "" if why is None else f' disabled title="{_e(why)}"')
    return f'<button type="button" class="btn small primary" data-cmd="new"{off}>new session</button>'


def _blocking(frame: Idle) -> tuple:
    """The stranded sessions that keep any session from opening: all but a rig's stranded demos
    (`Stranded.demo_folder`), which hold up only another demo (XC-504)."""
    return tuple(found for found in frame.stranded if not found.demo_folder)


def _stranded_demo(found, view: View) -> str:
    """**A stranded demo in a rig's demo folder** (XC-504; the PI, 2026-11-14, "A demo folder of
    its own"): it holds up only another demo, so the banner says a real animal's session opens
    beside it, and offers *end session…* alone, a demo being never resumed."""
    end = (
        f'<button type="button" class="btn small danger" data-return="{_e(found.session_id)}"'
        f"{_gate(view)}>end session…</button>"
    )
    if found.left_at is None:
        return (
            f"demo session {_e(found.session_id)}, in this rig's demo folder: its welfare record "
            f"cannot be read, so no demo opens until the file is repaired and its return recorded; "
            f"a real animal's session opens beside it"
        )
    return (
        f"demo session {_e(found.session_id)} ({_e(found.subject)}) left its cage at "
        f"{_e(_moment(found.left_at))}, in this rig's demo folder, and its return is not recorded; "
        f"no demo opens until it is, and a real animal's session opens beside it. "
        f"{_e(found.why)}. {end}"
    )


def _idle_banners(frame: Idle, view: View) -> str:
    """A refused frame, then every stranded animal -- each with *resume session*, when its record can carry one
    (XC-026), and *end session…*, which takes its return naming its session (XC-176) -- then a question owed, then, with no
    animal stranded, *no session open* beside *new session* (spec §6.1). A stranded
    departure is given as this host's local date, minute and zone, as the terminal gives
    it (`cli._moment`): an animal out since days ago must not read as since this morning
    (the b3a-1 final review, Minor 1). A record that cannot be read has no button: it is
    repaired by hand first. **A stranded demo in a rig's demo folder** holds up only another
    demo, said so in a banner of its own, and *new session* stays beside it (XC-504)."""
    out = []
    if view.rejected:
        out.append(_banner("crit", "Refused", _e(view.rejected)))
    for found in frame.stranded:
        if found.demo_folder:
            out.append(_banner("warn", "Stranded demo", _stranded_demo(found, view)))
            continue
        if found.left_at is None:
            text = (
                f"session {_e(found.session_id)}: its welfare record cannot be read, so its "
                f"animal's return cannot be checked; no session opens until the file is "
                f"repaired and the return recorded"
            )
        else:
            resume = (
                f'<button type="button" class="btn small" '
                f'data-resume="{_e(found.session_id)}"{_gate(view)}>resume session</button> '
                if found.resumable
                else ""
            )
            cannot = "" if found.resumable else f" It cannot be resumed: {_e(found.why)}."
            text = (
                f"{_e(found.subject)} left its cage at {_e(_moment(found.left_at))} in "
                f"session {_e(found.session_id)}, and its return is not recorded; no "
                f"session opens until it is resumed or its return recorded.{cannot} "
                f"{resume}"
                f'<button type="button" class="btn small danger" '
                f'data-return="{_e(found.session_id)}"{_gate(view)}>end session…</button>'
            )
        out.append(_banner("crit", "Stranded", text))
    if frame.question is not None:
        out.append(_question_banner(frame.question, view))
    if not _blocking(frame):
        out.append(_banner("info", "Idle", f"no session open {_new_session_button(view)}"))
    return "".join(out)


def _idle_setup(frame: Idle, view: View) -> str:
    """The Session panel with no session open (the mockup's Setup tab): *new session*,
    grayed while an animal is stranded -- not for a rig's stranded demo, which holds up only
    another demo (XC-504) -- and what `wlx taskd` offers a session."""
    why = (
        "an animal's return is not recorded: end its session from its Stranded banner first"
        if _blocking(frame)
        else None
    )
    rows = (
        ("animals", ", ".join(frame.animals) or "none: no folder under --subjects holds a bounds.py"),
        ("tasks offered", ", ".join(frame.offered_tasks) or "none: no task file under --tasks"),
    )
    return (
        f'<div class="selrow">{_new_session_button(view, why)}</div><dl class="dl">'
        + "".join(f"<dt>{name}</dt><dd>{_e(value)}</dd>" for name, value in rows)
        + "</dl>"
    )


def _end_actions(frame: Telemetry | Idle | None, view: View) -> str:
    """The Summary's pill and *end session* (the mockup's `end-pill`, `a-end`) while a
    `wlx taskd` session is open -- during a run too, which it stops first -- and, once it
    has ended, *record return…*, the second step (the b3a-2 plan, decision 12). A `wlx
    run` session's return is taken at its terminal, so its pill stands alone."""
    if frame is None or isinstance(frame, Idle):
        return '<span class="pill neutral">none</span>'
    session = _e(frame.session_id)
    if not frame.service:
        return f'<span class="pill neutral">{"open" if frame.stop_kind is None else "ended"}</span>'
    if frame.phase in ("between_runs", "running"):
        return (
            '<span class="pill neutral">open</span><button type="button" class="btn small '
            f'danger" data-cmd="end" data-session="{session}"{_gate(view)}>end session</button>'
        )
    if frame.phase == "awaiting_return":
        return (
            '<span class="pill warn">ended · awaiting the return</span><button type="button" '
            f'class="btn small danger" data-return="{session}"{_gate(view)}>record return…</button>'
        )
    return '<span class="pill ok">ended</span>'


def _idle_refusals(frame: Idle) -> str:
    rows = []
    if frame.refusals_dropped:
        rows.append(
            f'<div class="ev refused"><span class="kind">refused</span><span>'
            f"{_e(frame.refusals_dropped)} earlier refusal(s) not shown: only the most "
            f"recent {len(frame.refusals)} are kept</span></div>"
        )
    for refusal in frame.refusals:
        # Nobody (`None`, b2b spec §6) names no one, where a placeholder name stood.
        who = "" if refusal.by is None else f" by {_who(refusal.by)}"
        rows.append(
            f'<div class="ev refused"><span class="kind">refused</span><span>'
            f"{_e(refusal.name)}{who}: {_e(refusal.why)}</span></div>"
        )
    return "".join(rows) or '<span class="nm">nothing refused</span>'


def _closed_actions(frame: Telemetry) -> str:
    """The Summary's pill for the last closed session an idle frame carries: which
    session and animal the summary below it is, until the next session opens."""
    return (
        '<span class="pill ok">closed</span><span class="nm">session '
        f"{_e(frame.session_id)} · {_e(frame.subject)} · returned · shown until the next "
        "session opens</span>"
    )


# --- a demo's panes (demo mode §4; its plan's Task 9) ------------------------------------------


def _input_words(label: str) -> str:
    """What a number key does for the input `label` names (`pointer.Input.label`, demo mode §3.4):
    the chair, a feature source, or a device."""
    if label == "the chair":
        return "held: the chair moves; let go: the chair is still"
    if label.startswith("feature "):
        return f"held: {label} is above its threshold"
    return f"down: {label} pressed or answered; up: {label} released"


def demo_keys(keys) -> str:
    """**The demo screen's key list** (demo mode §3.3, §3.4, §4.3, §4.6): each number key and the
    input it stands for, from the drawing's `Drawn.keys` (key `k`'s at index `k - 1`), or that the
    task waits on none; then the pointer, the button, B, Escape, F, P and M (`DEMO_INPUTS`); where
    the keys act; and what a mouse is not (`DEMO_LIMITS`). `wlx serve` sends it beside each drawing
    (`serve`'s `_send_drawing`), and the page holds `demo_keys(())` before any."""
    if len(keys) > _KEYS:
        raise ValueError(f"a demo has {_KEYS} number keys, and {len(keys)} inputs were given")
    rows = [
        (str(number), f"{_e(label)} · {_e(_input_words(label))}")
        for number, label in enumerate(keys, start=1)
    ] or [(f"1-{_KEYS}", "this task waits on no other input")]
    rows += [(_e(key), _e(words)) for key, words in DEMO_INPUTS]
    return (
        '<dl class="dl demo-keylist">'
        + "".join(f'<dt><kbd>{key}</kbd></dt><dd>{words}</dd>' for key, words in rows)
        + f'</dl><p class="sub">{_e(DEMO_KEYS_WHERE)}</p><ul class="demo-limits">'
        + "".join(f"<li>{_e(limit)}</li>" for limit in DEMO_LIMITS)
        + "</ul>"
    )


def _demo_tag(frame: Telemetry | Idle | None) -> str:
    """**DEMO, in the header, on every demo frame** (demo mode §4.2): a demo session's
    (`Telemetry.demo`), and a demo service's idle frame (`Idle.demo`); nothing on any other. It
    names the session, for the script to show only that session's drawing (Task 8's carried (c)),
    and says whether a page may steer: a demo session between runs or in one (`data-steerable`),
    whose eye a page keeps so the next run's first frame finds it live."""
    if frame is None or not frame.demo:
        return ""
    title = "a demo: the mouse is the eye, and nothing here is an animal's data"
    if isinstance(frame, Idle):
        return f'<span class="pill demo" data-demo="service" data-session="" title="{title}">DEMO</span>'
    steerable = ' data-steerable="1"' if frame.phase in ("between_runs", "running") else ""
    return (
        f'<span class="pill demo" data-demo="session" data-session="{_e(frame.session_id)}"'
        f'{steerable} title="{title}">DEMO</span>'
    )


def _demo_under(frame: Telemetry | Idle | None) -> str:
    """**Under the demo screen, the last trial's outcome** (demo mode §4.4), from the frame
    (`Telemetry.recent_outcomes`), or that there is none yet, or no session; nothing off a demo."""
    if frame is None or not frame.demo:
        return ""
    if isinstance(frame, Idle):
        return '<span class="nm">no session open</span>'
    if not frame.recent_outcomes:
        return '<span class="k">last trial</span> <span class="nm">none yet</span>'
    outcome = frame.recent_outcomes[-1]
    return (
        f'<span class="k">last trial</span> <b class="mono" data-outcome="{_e(outcome)}">'
        f'{_e(str(outcome).replace("_", " "))}</b>'
    )


def _dn_demo(frame: Idle, view: View) -> str:
    """**The New session dialog's demo choice** (demo mode §4.1, the plan's door on a live rig):
    on a demo service, a line saying every session here is a demo, for `REFERENCE` alone; on a rig
    service, a **demo** box, offered where its idle frame says `gaze` and offers `REFERENCE`, which
    the script ticks to lock the subject to `REFERENCE` and fill the departure and the id, and the
    open then sends `demo: true`. Grayed, saying why, where it cannot open one: no `REFERENCE`
    (`NO_REFERENCE`), no gaze endpoint or no demo folder (`NO_GAZE`), or a demo stranded in the
    demo folder (`DEMO_STRANDED`), which the service would refuse."""
    if frame.demo:
        return (
            '<p class="sub" data-demo-service="1">a demo service: every session here is a demo, '
            f"for {REFERENCE} alone; the mouse is its eye, the simulated card and pump its "
            "apparatus</p>"
        )
    why = []
    if not frame.gaze:
        why.append(NO_GAZE)
    if REFERENCE not in frame.animals:
        why.append(NO_REFERENCE)
    if any(found.demo_folder for found in frame.stranded):
        why.append(DEMO_STRANDED)
    said = "; ".join(why)
    attrs = _gate(view, f' disabled title="{_e(said)}"' if said else "")
    note = f'<span class="sub" id="dn-demo-why">{_e(said)}</span>' if said else ""
    return (
        f'<label class="chk"><input type="checkbox" id="dn-demo-box" data-reference="{REFERENCE}"{attrs}> demo · for '
        f"{REFERENCE}, the test monkey: the mouse is its eye, the simulated card and pump its "
        f"apparatus, its record in this rig's demo folder</label>{note}"
    )


def _idle(frame: Idle, view: View) -> dict[str, str]:
    """The page while `wlx taskd` has no session open (P4d-2b spec §6.1: "the page shows
    *no session open* beside the form that opens one"): every pane as before any frame,
    except the pill, the header, the banners, the controls, *wl-works sees* (`/health`
    as it would be sent for this frame, stranded animals included), the refusals, the
    tasks offered, the Session panel, the Warnings tab and the dialog's animals and warnings --
    **and the End tab**, which shows the last closed session's summary, supplement owed first, until the next
    session opens (schema 11; spec §6.2: "The session then closes and the page shows its
    summary"; the b3a-2 final review, I2), rendered by `_end` as any closed frame is. **And a
    demo's** (demo mode §4.1-§4.2): a demo service's DEMO, the line under its demo screen, its
    dialog's `REFERENCE` alone, and on a rig service the dialog's demo box (`_dn_demo`)."""
    panes = fragments(None, view)
    if frame.closed is not None:
        panes["end-actions"] = _closed_actions(frame.closed)
        panes["end"] = _end(frame.closed)
    panes["demo-tag"] = _demo_tag(frame)
    panes["state"] = '<span class="pill neutral" data-state="idle">no session open</span>'
    panes["head-id"] = '<span class="nm">no session open</span>'
    panes["banners"] = _idle_banners(frame, view)
    panes["controls"] = (
        '<span class="nm">controls · no session open</span>' + _session_refused(frame.refusals)
    )
    panes["rt-health"] = _health_pane(frame, view)
    panes["rt-changes"] = _idle_refusals(frame)
    panes["task-sel"] = _options(frame.offered_tasks, "no task offered")
    panes["plan-sel"] = _plans(None)
    panes["setup"] = _idle_setup(frame, view)
    panes["demo-under"] = _demo_under(frame)
    panes["dn-demo"] = _dn_demo(frame, view)
    # A demo service offers `REFERENCE` alone, chosen (demo mode §4.1); a rig its animals.
    panes["dn-subject"] = (
        _options(tuple(name for name in frame.animals if name == REFERENCE), NO_REFERENCE)
        if frame.demo
        else _options(frame.animals, "no animal offered", "choose the animal")
    )
    panes["warnings"] = _warnings_pane(frame)
    panes["dn-warnings"] = _dn_warnings(frame, view)
    return panes


def fragments(frame: Telemetry | Idle | None, view: View) -> dict[str, str]:
    """Every pane of the page for one frame, keyed by the id of the element each one
    fills (`FRAGMENT_IDS`, in that order). `frame` is `None` before any has arrived,
    and every pane then says so; an `Idle` is `wlx taskd` with no session open."""
    if isinstance(frame, Idle):
        return _idle(frame, view)
    return {
        "demo-tag": _demo_tag(frame),
        "state": _state(frame),
        "bar-nums": _bar_nums(frame),
        "head-id": _head(frame),
        "presence": _presence(view),
        "strip": _strip(frame, view),
        "banners": _banners(frame, view),
        "task-sel": _options(() if frame is None else frame.offered_tasks, "no task offered"),
        "plan-sel": _plans(frame),
        "pf-pill": _pf_pill(frame, view),
        "controls": _controls(frame, view),
        "rt-trials": _trials(frame),
        "rt-work": _work(frame),
        "rt-shaping": _runtime_shaping(frame),
        "rt-need": _need(frame, view),
        "rt-wrong": _wrong(frame),
        "rt-health": _health_pane(frame, view),
        "rt-changes": _changes(frame),
        "params": _params(frame, view),
        "moments": _moments(frame, view),
        "shaping": _shaping(frame, view),
        "rt-train": _trainer(frame, view),
        "training-params": _training_params(frame, view),
        "pf-sum": _pf_sum(frame),
        "preflight": _preflight_pane(frame, view),
        "setup": _setup(frame),
        "warnings": _warnings_pane(frame),
        "end-actions": _end_actions(frame, view),
        "end": _end(frame),
        "demo-under": _demo_under(frame),
        "dn-demo": "",
        "dn-subject": _options((), "no animal offered"),
        "dn-warnings": "",
    }


# --- the page -------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Font:
    """One face the page uses: bundled at `wl_xcon/fonts/<directory>/<file>`
    and served by `wlx serve` at `/fonts/<file>`."""

    family: str
    weight: int
    style: str
    directory: str
    file: str


#: **Every face the page's CSS asks for, and no other** (PI, 2026-09-26: "bundle the
#: fonts", so the page keeps the wl-works look and never reaches the internet). The
#: unmodified woff2 files their primary sources publish -- the IBM/plex GitHub releases
#: and productiontype/Newsreader -- fetched 2026-09-26, each family's OFL-1.1 license
#: beside them as `OFL.txt`; ADR-0004's inventory carries the sources and licenses.
#: The weights are the ones `_CSS` sets; italics are synthesized, as in the mockup.
#: Newsreader draws only the logo, from its 72pt optical-size cut.
FONTS = (
    Font("IBM Plex Sans", 400, "normal", "ibm-plex-sans", "IBMPlexSans-Regular.woff2"),
    Font("IBM Plex Sans", 500, "normal", "ibm-plex-sans", "IBMPlexSans-Medium.woff2"),
    Font("IBM Plex Sans", 600, "normal", "ibm-plex-sans", "IBMPlexSans-SemiBold.woff2"),
    Font(
        "IBM Plex Sans Condensed",
        400,
        "normal",
        "ibm-plex-sans-condensed",
        "IBMPlexSansCondensed-Regular.woff2",
    ),
    Font(
        "IBM Plex Sans Condensed",
        600,
        "normal",
        "ibm-plex-sans-condensed",
        "IBMPlexSansCondensed-SemiBold.woff2",
    ),
    Font(
        "IBM Plex Sans Condensed",
        700,
        "normal",
        "ibm-plex-sans-condensed",
        "IBMPlexSansCondensed-Bold.woff2",
    ),
    Font("IBM Plex Mono", 400, "normal", "ibm-plex-mono", "IBMPlexMono-Regular.woff2"),
    Font("IBM Plex Mono", 500, "normal", "ibm-plex-mono", "IBMPlexMono-Medium.woff2"),
    Font("IBM Plex Mono", 600, "normal", "ibm-plex-mono", "IBMPlexMono-SemiBold.woff2"),
    Font("Newsreader", 700, "normal", "newsreader", "Newsreader72pt-Bold.woff2"),
    Font("Newsreader", 700, "italic", "newsreader", "Newsreader72pt-BoldItalic.woff2"),
)


def font_bytes(font: Font) -> bytes:
    """A bundled font file, read as package data -- the same bytes from a checkout and
    from an installed wheel (`pyproject.toml`'s `package-data`)."""
    return (
        resources.files("wl_xcon")
        .joinpath("fonts")
        .joinpath(font.directory)
        .joinpath(font.file)
        .read_bytes()
    )


#: One `@font-face` per bundled face, each fetched from this box's `/fonts/` route.
_FONT_FACES = "".join(
    f'@font-face {{ font-family: "{font.family}"; font-style: {font.style}; '
    f"font-weight: {font.weight}; font-display: swap; "
    f'src: url("/fonts/{font.file}") format("woff2"); }}\n'
    for font in FONTS
)

#: The mockup's wl-works tokens and layout (`docs/superpowers/mockups/
#: 2026-09-26-console-mockup-v12.html`), trimmed to what b1 builds. **The fonts are the
#: box's own** (`FONTS`, `_FONT_FACES`); each stack's system faces are only the fallback
#: while they load. Tabs are radio inputs styled by `:checked`, so they need no script.
_CSS = """
:root {
  --bg: #faf8f3; --surface: #fffefb; --surface-2: #f2f0e9; --ink: #050c19; --muted: #55606f;
  --rule: rgb(136 148 166 / 0.45); --edge: rgb(5 12 25 / 0.08);
  --accent: #0a6e6b; --accent-fg: #faf8f3; --accent-soft: #dfecea;
  --ok: #2e7a4f; --ok-soft: #deefe4; --warn: #9a5b00; --warn-soft: #f6e7cf;
  --crit: #b3261e; --crit-soft: #f6dcda;
  --screen: #081122; --screen-ink: #8ea0bc; --rf: #67b2ea; --mock: #452d81;
  --wl-muted: #55606f; --distract: #c9187b;
  --shadow: inset 0 1px 0 rgb(255 255 255 / 0.9), inset 0 -1px 0 rgb(5 12 25 / 0.06), 0 1px 2px rgb(5 12 25 / 0.04), 0 8px 28px -12px rgb(5 12 25 / 0.18);
  --sans: "IBM Plex Sans", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", sans-serif;
  --cond: "IBM Plex Sans Condensed", "IBM Plex Sans", "Arial Narrow", sans-serif;
  --mono: "IBM Plex Mono", ui-monospace, SFMono-Regular, Menlo, monospace;
}
@media (prefers-color-scheme: dark) {
  :root {
    color-scheme: dark;
    --bg: #050c19; --surface: #112037; --surface-2: #152743; --ink: #faf8f3; --muted: #8ea0bc;
    --rule: rgb(136 148 166 / 0.3); --edge: rgb(250 248 243 / 0.1);
    --accent: #12a5a1; --accent-fg: #050c19; --accent-soft: #0f3a44;
    --ok: #5cba80; --ok-soft: #133427; --warn: #e6a646; --warn-soft: #382a12;
    --crit: #f07166; --crit-soft: #3c1b1a;
    --screen: #02060d; --mock: #b3a2ea; --wl-muted: #8ea0bc; --distract: #d6579c;
    --shadow: inset 0 1px 0 rgb(250 248 243 / 0.06), inset 0 -1px 0 rgb(0 0 0 / 0.25), 0 1px 2px rgb(0 0 0 / 0.3), 0 8px 28px -12px rgb(0 0 0 / 0.6);
  }
}
* { box-sizing: border-box; }
[hidden] { display: none !important; }
body { margin: 0; background: var(--bg); color: var(--ink); font-family: var(--sans); font-size: 14px; line-height: 1.4; padding: 0 12px 28px; }
.wrap { max-width: 1520px; margin: 0 auto; display: grid; grid-template-columns: minmax(0, 1fr); gap: 8px; }
.num, .mono { font-family: var(--mono); font-variant-numeric: tabular-nums; }
h2 { font-family: var(--cond); font-weight: 700; font-size: 12px; letter-spacing: 0.08em; text-transform: uppercase; color: var(--muted); margin: 0; }
h3 { margin: 0; font-family: var(--cond); font-weight: 600; font-size: 11.5px; letter-spacing: 0.07em; text-transform: uppercase; color: var(--muted); }
.sub { font-size: 12.5px; color: var(--muted); }
.nm { color: var(--muted); font-style: italic; }
.who-b { font-style: italic; }
.later { font-size: 11px; color: var(--mock); font-family: var(--cond); letter-spacing: 0.05em; text-transform: uppercase; font-weight: 600; }
.glass { background: var(--surface); border: 1px solid var(--edge); border-radius: 8px; box-shadow: var(--shadow); }
.head { display: flex; flex-wrap: wrap; gap: 6px 18px; align-items: center; padding: 6px 12px; }
.topbar { position: sticky; top: 0; z-index: 15; display: grid; gap: 4px; padding: 4px 10px; border-top: 0; border-radius: 0 0 8px 8px; }
.barline { display: flex; flex-wrap: wrap; align-items: center; gap: 4px 12px; min-width: 0; }
.topbar .logo svg { height: 22px; }
.topbar .logo .app { padding-left: 8px; }
.topbar .nums { display: flex; flex-wrap: wrap; gap: 2px 12px; align-items: baseline; font-size: 13.5px; }
.topbar .bn { white-space: nowrap; }
.topbar .bn .k { font-family: var(--cond); font-size: 11px; letter-spacing: 0.06em; text-transform: uppercase; color: var(--muted); margin-right: 4px; }
.topbar .bn b { font-family: var(--mono); font-weight: 600; font-variant-numeric: tabular-nums; }
.topbar .bn .u { color: var(--muted); font-weight: 400; }
.topbar .bn.warn b { color: var(--warn); } .topbar .bn.crit b { color: var(--crit); }
.topbar .spacer { flex: 1; }
.topbar .ctlrow .btn { padding: 3px 10px; font-size: 13px; }
.topbar .ctlrow .nm { font-size: 12px; }
.topbar .sent { flex: 1 1 0; min-width: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.session { display: grid; gap: 8px; }
body:has(#t-task:checked) .session, body:has(#t-training:checked) .session { display: none; }
body.session-open .session { display: grid !important; }
body.session-shut .session { display: none !important; }
.logo { display: flex; align-items: center; gap: 10px; color: var(--ink); }
.logo svg { height: 34px; width: auto; display: block; }
.logo .app { font-family: var(--cond); font-weight: 600; letter-spacing: 0.06em; text-transform: uppercase; font-size: 12px; color: var(--muted); border-left: 1px solid var(--rule); padding-left: 10px; }
.head .id { display: flex; flex-wrap: wrap; gap: 4px 16px; align-items: baseline; }
.head .k { font-family: var(--cond); font-size: 12px; letter-spacing: 0.06em; text-transform: uppercase; color: var(--muted); margin-right: 4px; }
.head .v { font-family: var(--mono); font-weight: 500; }
.head .spacer { flex: 1; }
.presence { font-size: 12.5px; color: var(--muted); }
.presence b { color: var(--ink); font-weight: 600; }
.pill { font-family: var(--cond); font-weight: 700; letter-spacing: 0.08em; font-size: 12px; text-transform: uppercase; border-radius: 999px; padding: 3px 10px; display: inline-flex; gap: 6px; align-items: center; white-space: nowrap; }
.pill::before { content: ""; width: 7px; height: 7px; border-radius: 50%; background: currentColor; }
.pill.ok { background: var(--ok-soft); color: var(--ok); }
.pill.warn { background: var(--warn-soft); color: var(--warn); }
.pill.crit { background: var(--crit-soft); color: var(--crit); }
.pill.neutral { background: var(--surface-2); color: var(--muted); }
.strip { display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); overflow: hidden; }
.strip > div { padding: 5px 12px; display: grid; gap: 3px; border-left: 1px solid var(--rule); }
.strip > div:first-child { border-left: 0; }
.strip .row { display: flex; flex-wrap: wrap; justify-content: space-between; align-items: baseline; gap: 0 8px; }
.strip .lab { font-family: var(--cond); font-weight: 700; font-size: 11.5px; letter-spacing: 0.07em; text-transform: uppercase; color: var(--muted); white-space: nowrap; }
.strip .val { font-family: var(--mono); font-variant-numeric: tabular-nums; font-size: 14.5px; font-weight: 600; white-space: nowrap; }
.strip .val .u { font-size: 12px; color: var(--muted); font-family: var(--sans); font-weight: 400; margin-left: 3px; }
.strip .bar { height: 4px; }
.strip .lines { display: grid; grid-template-columns: auto auto auto 1fr; gap: 1px 10px; font-size: 12.5px; align-items: baseline; }
.strip .lines .k { color: var(--muted); white-space: nowrap; }
.strip .lines .n { font-family: var(--mono); font-variant-numeric: tabular-nums; text-align: right; white-space: nowrap; }
.strip .lines .n .u { color: var(--muted); }
.strip .lines .x { color: var(--muted); font-size: 11.5px; white-space: nowrap; }
.strip .lines .warn { color: var(--warn); font-weight: 600; }
.strip .lines .crit { color: var(--crit); font-weight: 600; }
.banners { display: grid; gap: 6px; }
.banner { border-radius: 6px; padding: 6px 12px; font-size: 13.5px; display: flex; gap: 10px; align-items: baseline; flex-wrap: wrap; }
.banner.warn { background: var(--warn-soft); border-left: 4px solid var(--warn); }
.banner.crit { background: var(--crit-soft); border-left: 4px solid var(--crit); }
.banner.info { background: var(--accent-soft); border-left: 4px solid var(--accent); }
.banner .tag { font-family: var(--cond); font-weight: 700; letter-spacing: 0.06em; text-transform: uppercase; font-size: 12px; }
.shell { display: grid; gap: 10px; grid-template-columns: minmax(0, 1fr) 250px; align-items: stretch; }
@media (max-width: 1100px) { .shell { grid-template-columns: minmax(0, 1fr) 200px; } }
@media (max-width: 900px) { .shell { grid-template-columns: minmax(0, 1fr); } }
.main { display: flex; flex-direction: column; gap: 10px; min-width: 0; }
.main > input { position: absolute; opacity: 0; pointer-events: none; }
.tabs { display: flex; flex-wrap: wrap; gap: 2px; border-bottom: 1px solid var(--rule); }
.tab { border: 1px solid transparent; border-bottom: 0; padding: 7px 12px 6px; cursor: pointer; font-family: var(--cond); font-weight: 700; letter-spacing: 0.06em; text-transform: uppercase; font-size: 12.5px; color: var(--muted); border-radius: 6px 6px 0 0; margin-bottom: -1px; }
#t-runtime:checked ~ .tabs [for="t-runtime"], #t-task:checked ~ .tabs [for="t-task"], #t-training:checked ~ .tabs [for="t-training"], #t-setup:checked ~ .tabs [for="t-setup"], #t-warn:checked ~ .tabs [for="t-warn"], #t-end:checked ~ .tabs [for="t-end"] { background: var(--surface); border-color: var(--edge); color: var(--ink); }
#t-runtime:focus-visible ~ .tabs [for="t-runtime"], #t-task:focus-visible ~ .tabs [for="t-task"], #t-training:focus-visible ~ .tabs [for="t-training"], #t-setup:focus-visible ~ .tabs [for="t-setup"], #t-warn:focus-visible ~ .tabs [for="t-warn"], #t-end:focus-visible ~ .tabs [for="t-end"] { outline: 2px solid var(--accent); outline-offset: 2px; }
.tabpanel { display: none; flex-direction: column; gap: 10px; }
#t-runtime:checked ~ .panels #tp-runtime, #t-task:checked ~ .panels #tp-task, #t-training:checked ~ .panels #tp-training, #t-setup:checked ~ .panels #tp-setup, #t-warn:checked ~ .panels #tp-warn, #t-end:checked ~ .panels #tp-end { display: flex; }
.cols { display: grid; gap: 10px; align-items: stretch; }
.cols.c3 { grid-template-columns: repeat(3, minmax(0, 1fr)); }
@media (max-width: 1100px) { .cols.c3 { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 700px) { .cols.c3 { grid-template-columns: minmax(0, 1fr); } }
.stack, .aside { display: flex; flex-direction: column; gap: 10px; min-width: 0; }
.panel { padding: 9px 12px; display: grid; gap: 7px; align-content: start; min-width: 0; }
.panel .top { display: flex; justify-content: space-between; align-items: baseline; gap: 8px; flex-wrap: wrap; }
.dl { display: grid; grid-template-columns: auto minmax(0, 1fr); gap: 3px 10px; font-size: 13px; margin: 0; }
.dl dt { color: var(--muted); }
.dl dd { margin: 0; font-family: var(--mono); font-size: 12.5px; overflow-wrap: anywhere; }
.big { font-family: var(--mono); font-variant-numeric: tabular-nums; font-size: 22px; font-weight: 600; line-height: 1.1; }
.unit { font-size: 13px; color: var(--muted); font-weight: 500; margin-left: 3px; font-family: var(--sans); }
.selrow { display: flex; gap: 8px; align-items: baseline; flex-wrap: wrap; }
.bar { height: 8px; background: var(--surface-2); border-radius: 3px; position: relative; overflow: hidden; }
.bar .fill { position: absolute; inset: 0 auto 0 0; background: var(--accent); }
.bar .fill.ok { background: var(--ok); } .bar .fill.warn { background: var(--warn); } .bar .fill.crit { background: var(--crit); }
.counts { display: grid; gap: 6px 14px; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); }
.fam { display: grid; gap: 1px; align-content: start; }
.kv { display: flex; justify-content: space-between; gap: 8px; font-size: 13px; }
.kv > span { min-width: 0; overflow-wrap: anywhere; }
.kv > .keep { overflow-wrap: normal; white-space: nowrap; flex-shrink: 0; }
.kv > .btn { flex-shrink: 0; }
.kv.wrap { flex-wrap: wrap; align-items: baseline; row-gap: 4px; }
.kv.wrap > span { flex: 1 1 12em; }
.kv.wrap > .btn { flex-shrink: 1; max-width: 100%; }
.owe { display: flex; align-items: baseline; gap: 10px; flex-wrap: wrap; background: var(--accent-soft); border-radius: 6px; padding: 8px 10px; }
.params { display: grid; gap: 8px; }
/* Columns as wide as the tab's own longest line, its plain name and its value whole (`_line_width`;
   the ledger's ruling for the summary and editor build's Task 3), set on the summary by Python;
   330 px, a line of the longest plain name a task may declare (`task.LABEL_LIMIT`), where none is
   (Task 2's ruling). Runtime's Pinned lines take their tabs' widest. */
.summary { columns: auto 330px; column-gap: 20px; min-width: 0; }
.ssec { break-inside: avoid; -webkit-column-break-inside: avoid; page-break-inside: avoid; margin: 0 0 6px; min-width: 0; }
.ssec .ssec { margin: 3px 0 0; }
/* A section holding subsections breaks between them across columns, so the Training tab, one
   section of several, has columns too (the summary and editor build's Task 3); its header never
   stands alone at a column's foot. */
.ssec:has(> .ssec), .ssec:has(> .skeep) { break-inside: auto; -webkit-column-break-inside: auto; page-break-inside: auto; }
.skeep { break-inside: avoid; -webkit-column-break-inside: avoid; page-break-inside: avoid; }
.ssec > h4, .skeep > h4 { break-after: avoid; -webkit-column-break-after: avoid; page-break-after: avoid; }
.ssec > h4, .skeep > h4 { margin: 0 0 1px; height: 17px; line-height: 16px; font-size: 11px; font-weight: 600; letter-spacing: 0.05em; text-transform: uppercase; color: var(--muted); border-bottom: 1px solid var(--rule); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.ssec .ssec > h4 { text-transform: none; letter-spacing: 0; font-weight: 500; border-bottom: 0; }
.ssec > h4 .ns, .skeep > h4 .ns, .tab .tns { color: var(--accent); font-weight: 600; }
.line { display: flex; align-items: center; gap: 5px; box-sizing: border-box; width: 100%; height: 20px; margin: 0; padding: 0 4px; border: 0; border-radius: 3px; background: transparent; color: var(--ink); font: inherit; font-size: 12.5px; line-height: 20px; text-align: left; cursor: pointer; min-width: 0; }
.line:hover { background: var(--surface-2); }
.line:focus-visible { outline: 2px solid var(--accent); outline-offset: -2px; }
.line[aria-pressed="true"] { background: var(--accent-soft); box-shadow: inset 0 0 0 1px var(--accent); }
.line > .mk { flex: none; min-width: 2em; font-size: 11px; color: var(--accent); white-space: nowrap; text-align: center; }
.line > .ln { flex: 1 1 auto; min-width: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.line > .lv { flex: 0 1 auto; max-width: 62%; min-width: 0; font-family: var(--mono); font-size: 12px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: right; }
.line.waiting > .lv { color: var(--accent); }
.line.refused > .mk, .line.refused > .lv { color: var(--crit); }
.line.warned > .mk { color: var(--warn); }
.line.changed > .ln { font-weight: 600; }
.line.ceiling > .ln { color: var(--warn); font-weight: 600; }
.line.newcolor > .ln { color: var(--accent); }
.summary .line.nofind { display: flex !important; opacity: 0.35; }
.summary .line.found { box-shadow: inset 3px 0 0 var(--accent); background: var(--surface-2); }
.line.draft > .lv, .line.sending > .lv { color: var(--accent); font-style: italic; }
.line.unconfirmed > .mk { color: var(--warn); }
.top > .nomatch { font-size: 12.5px; font-weight: 600; color: var(--crit); }
.params > .legend { font-size: 11px; color: var(--muted); }
.params > .editing { border-top: 2px solid var(--ink); padding-top: 8px; min-width: 0; }
.params > .editing > .placeholder, .params > .editing > .findhid { color: var(--muted); font-size: 13px; padding: 4px 0; }
.cards { display: grid; gap: 5px; grid-template-columns: repeat(auto-fill, minmax(186px, 1fr)); align-items: start; }
.nofind { display: none !important; }
.panel .top.tools { justify-content: flex-start; }
.top > .field.find { width: 220px; max-width: 100%; font-size: 13px; padding: 2px 6px; }
.box { position: relative; border: 1px solid var(--rule); border-radius: 5px; padding: 3px 6px 2px; display: grid; grid-template-columns: minmax(0, 1fr); gap: 2px; align-content: start; background: var(--surface-2); min-width: 0; }
.box.wide { grid-column: span 2; }
@media (max-width: 520px) { .box.wide { grid-column: auto; } }
.box:has(> details.more[open]) { grid-column: 1 / -1; background: var(--surface); }
.box > .head { display: grid; grid-template-columns: minmax(0, max-content) auto minmax(4.5em, 1fr); align-items: center; gap: 0 6px; padding: 0 18px 0 0; min-width: 0; line-height: 16px; }
.box > .head > *, .box > .head .code, .box > .head .now * { line-height: 16px; }
.box > .head > .now, .box > .head > .ceil, .box > .head .code { height: 16px; }
.box .names { display: contents; }
.box .lbl { grid-column: 1 / -1; font-size: 13px; font-weight: 600; line-height: 1.25; overflow-wrap: anywhere; min-width: 0; }
.box .names .code { grid-column: 1; }
.box > .head > .ceil { grid-column: 2; }
.box > .head > .now { grid-column: 3; text-align: right; }
.box[data-echo]:not(.draft):not(.staged):not(.sending) > .head > .now { display: none; }
.box[data-echo]:not(.draft):not(.staged):not(.sending) > .head { grid-template-columns: minmax(0, 1fr) auto 0; }
/* A waiting box's head gives what waits the room it needs (the whole-build review's I4): the code
   name under a plain name goes (it is in the title and in *more*), a code name alone gives way to
   "0.30 → 0.50 s", cut first; the head keeps its rows, so the box keeps its height. */
.box.staged > .head { grid-template-columns: minmax(2.5em, 1fr) auto max-content; }
.box.staged > .head .lbl ~ .code { display: none; }
/* Who sent it, by name on the line: "(box, unverified)" and "(wl.works)" ride in its title. */
.box.staged > .status .say .nm { display: none; }
.box > .more:not([open]) { margin-top: -2px; }
.box .code { font-family: var(--mono); font-size: 11.5px; color: var(--muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.box .code.only { font-size: 12.5px; color: var(--ink); font-weight: 500; }
.box .ceil { font-family: var(--cond); font-size: 11px; letter-spacing: 0.05em; text-transform: uppercase; color: var(--warn); font-weight: 700; }
.box .now { max-width: 100%; min-width: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.box .pv { font-family: var(--mono); font-size: 13px; }
.box .now .to { font-family: var(--mono); font-size: 13px; color: var(--accent); }
.box > .editor { display: flex; flex-wrap: wrap; gap: 4px 6px; align-items: center; min-width: 0; }
.box > .editor > * { min-width: 0; max-width: 100%; }
.box > .status { position: relative; display: flex; align-items: center; min-height: 22px; min-width: 0; font-size: 12px; color: var(--muted); }
.box .btn.small { padding: 1px 8px; }
.box .status .say { flex: 1 1 auto; min-width: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.box .status .acts { position: absolute; right: 0; top: 0; bottom: 0; display: flex; gap: 4px; align-items: center; padding-left: 6px; background: inherit; visibility: hidden; }
.box.draft .status .acts, .box.sending .status .acts, .box.staged .status .acts:has([data-withdraw]) { position: static; flex: none; visibility: visible; }
.box:not(.draft):not(.sending) .status .acts [data-apply], .box:not(.draft):not(.sending) .status .acts [data-discard] { display: none; }
.box.draft { border-color: var(--accent); border-style: dashed; }
.box.draft .status .say, .box.sending .status .say { color: var(--accent); }
.box.cannot .status .say { color: var(--crit); }
.box.staged { border-color: var(--accent); box-shadow: inset 3px 0 0 var(--accent); }
.box.staged .status .say { color: var(--accent); }
.box.refused { border-color: var(--crit); box-shadow: inset 3px 0 0 var(--crit); }
.box.refused .status .say { color: var(--crit); }
.box.warned .status .say { color: var(--warn); }
.box.ceiling:not(.staged):not(.refused) { box-shadow: inset 3px 0 0 var(--warn); }
.box > .more > summary { position: absolute; top: 1px; right: 2px; list-style: none; cursor: pointer; font-size: 14px; line-height: 1; padding: 2px 4px; border-radius: 3px; color: var(--muted); }
.box > .more > summary::-webkit-details-marker { display: none; }
.box > .more > summary::marker { content: ""; }
.box > .more > summary:hover, .box > .more[open] > summary { background: var(--surface); color: var(--ink); }
.box .detail .pin[aria-pressed="true"] { background: var(--accent-soft); border-color: var(--accent); }
.box .detail { display: grid; gap: 3px; margin-top: 4px; padding-top: 5px; border-top: 1px solid var(--rule); font-size: 12.5px; min-width: 0; }
.box .detail > * { min-width: 0; overflow-wrap: anywhere; }
.box .detail .what { color: var(--ink); }
.box .range, .box .stg { font-size: 12px; color: var(--muted); }
.box .stg { color: var(--accent); }
.box .wrn { font-size: 12px; color: var(--warn); }
.feed { display: grid; align-content: start; max-height: 300px; overflow-y: auto; overscroll-behavior: contain; padding-right: 4px; }
.ev { display: grid; grid-template-columns: 5.5em minmax(0, 1fr); gap: 6px; padding: 4px 0; border-top: 1px solid var(--rule); font-size: 12.5px; }
.ev:first-child { border-top: 0; }
.ev > span { min-width: 0; overflow-wrap: anywhere; }
.ev .kind { font-family: var(--cond); font-weight: 700; letter-spacing: 0.05em; text-transform: uppercase; font-size: 11px; }
.ev.staged .kind { color: var(--accent); } .ev.refused .kind { color: var(--crit); }
.health .r { display: grid; grid-template-columns: 1em minmax(0, 7.5em) minmax(0, 1fr); gap: 6px; font-size: 12.5px; }
.health .r .f { color: var(--accent); } .health .r .l { color: var(--muted); }
.health .r .v { font-family: var(--mono); font-size: 12px; overflow-wrap: anywhere; }
.ticks { display: grid; grid-template-columns: repeat(30, minmax(0, 1fr)); gap: 2px; }
.tk { display: block; height: 12px; border-radius: 2px; background: var(--surface-2); }
.tk.f-target { background: var(--accent); } .tk.f-distractor { background: var(--crit); } .tk.f-withhold { background: var(--rf); }
.tk.f-no_engagement { background: color-mix(in srgb, var(--muted) 60%, transparent); } .tk.f-breaks { background: var(--warn); } .tk.f-rig { background: var(--mock); }
.tk.f-hang { background: var(--ink); } .tk.f-other { background: transparent; box-shadow: inset 0 0 0 1px var(--muted); }
.legend { display: flex; flex-wrap: wrap; gap: 3px 12px; font-size: 11.5px; color: var(--muted); }
.legend i { display: inline-block; width: 9px; height: 9px; border-radius: 2px; margin-right: 4px; vertical-align: -1px; }
.screen { border-radius: 5px; background: var(--screen); color: var(--screen-ink); aspect-ratio: 16 / 9; display: grid; place-items: center; font-family: var(--mono); font-size: 12px; }
.duo { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
.xbtn { width: 30px; height: 30px; display: grid; place-items: center; border: 1.5px solid var(--distract); color: var(--distract); background: transparent; border-radius: 6px; cursor: pointer; padding: 0; flex: none; }
.xbtn:hover { background: var(--distract); color: var(--bg); }
.xbtn svg { width: 12px; height: 12px; }
.btn { border: 1px solid var(--rule); background: var(--surface); color: inherit; border-radius: 5px; padding: 5px 12px; cursor: pointer; font-family: var(--cond); font-weight: 600; font-size: 14px; }
.btn.primary { background: var(--accent); border-color: var(--accent); color: var(--accent-fg); }
.scrim { position: fixed; inset: 0; background: var(--bg); display: grid; place-items: center; padding: 16px; z-index: 30; overflow-y: auto; }
.scrim > .dialog { margin: auto; }
.dialog { padding: 16px; width: min(520px, 100%); display: grid; gap: 12px; }
.dialog h2 { font-size: 14px; color: var(--ink); }
.dialog .actions { display: flex; justify-content: flex-end; }
.controlbar { display: flex; flex-wrap: wrap; gap: 6px 12px; align-items: center; padding: 6px 12px; }
.ctlrow { display: flex; flex-wrap: wrap; gap: 6px 10px; align-items: center; }
.controlbar .spacer { flex: 1; }
.btn.small { padding: 2px 8px; font-size: 12.5px; }
.btn.danger { border-color: var(--crit); color: var(--crit); }
.btn:disabled, .field:disabled, .stp:disabled, select:disabled { opacity: 0.45; cursor: not-allowed; }
.who { font-size: 12.5px; color: var(--muted); }
.who b { color: var(--ink); font-weight: 600; }
body:not([data-signed-in="1"]) .si{display:none} body[data-signed-in="1"] .so{display:none}
.sent { font-size: 12.5px; }
.drafts { position: fixed; left: 50%; bottom: 10px; transform: translateX(-50%); z-index: 20; display: flex; gap: 8px; align-items: center; max-width: min(960px, calc(100vw - 32px)); padding: 6px 10px; font-size: 13px; }
.drafts[hidden] { display: none; }
.drafts .say { flex: 1 1 auto; min-width: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.drafts .btn { flex: none; }
body.drafted > .wrap { padding-bottom: 56px; }
.sent.ok { color: var(--ok); } .sent.crit { color: var(--crit); }
.inline { display: flex; flex-wrap: wrap; gap: 6px 10px; align-items: center; padding: 6px 12px; border-radius: 6px; font-size: 13px; background: var(--surface-2); }
.inline.crit { background: var(--crit-soft); } .inline.info { background: var(--accent-soft); }
.inline input, .inline select { font: inherit; color: inherit; background: var(--surface); border: 1px solid var(--rule); border-radius: 3px; padding: 1px 4px; }
#mark-note { width: min(34em, 60vw); }
#sched-value { width: 7em; }
.fu { display: inline-flex; flex-wrap: wrap; align-items: center; gap: 2px 4px; min-width: 0; max-width: 100%; }
.fu .unit, .box .rn .unit { margin-left: 0; font-size: 12px; overflow-wrap: anywhere; min-width: 0; }
.spin { display: inline-flex; align-items: stretch; }
.field { width: 6em; border: 1px solid var(--rule); border-radius: 3px; padding: 1px 4px; background: var(--surface); color: inherit; font-size: 12.5px; }
.field.pending { border-color: var(--accent); }
.spin .stp { width: 22px; min-height: 22px; border: 1px solid var(--rule); background: var(--surface); color: var(--muted); cursor: pointer; padding: 0; font-family: var(--sans); font-size: 14px; line-height: 1; }
.spin .stp:first-child { border-radius: 3px 0 0 3px; border-right: 0; }
.spin .stp:last-child { border-radius: 0 3px 3px 0; border-left: 0; }
.spin .stp + .field { border-radius: 0; width: 5em; text-align: right; font-size: 14px; font-weight: 600; }
.box .rfs { font-size: 12px; color: var(--crit); }
.box .src, .box .rn { font-size: 12px; color: var(--muted); }
.box .src { overflow-wrap: anywhere; }
.box .rng { display: flex; flex-wrap: wrap; gap: 4px; align-items: center; min-width: 0; }
.box .rn { display: inline-flex; flex-wrap: wrap; gap: 3px; align-items: center; min-width: 0; max-width: 100%; }
.box .rn .field { width: 4.5em; }
.box .sw { display: inline-flex; gap: 0; }
.box .sw .seg { border-radius: 0; }
.box .sw .seg:first-child { border-radius: 4px 0 0 4px; }
.box .sw .seg:last-child { border-radius: 0 4px 4px 0; }
.box .sw .seg.on { background: var(--ink); color: var(--bg); }
.box .chs { flex-wrap: wrap; gap: 4px; }
.box .chs .chw .seg { border-radius: 4px; }
.box .side { display: flex; flex-wrap: wrap; gap: 4px; align-items: center; flex: 1 1 100%; min-width: 0; }
.box .side[hidden], .box .shp[hidden] { display: none; }
.box .prof { display: block; width: 100%; max-width: 280px; height: auto; margin-top: 6px; }
.box .prof .bar { fill: var(--accent-soft); stroke: var(--accent); stroke-width: 0.6; }
.box .prof .base { stroke: var(--rule); stroke-width: 1; }
.box .prof .haz { fill: none; stroke: var(--warn); stroke-width: 1.6; stroke-linejoin: round; }
.box .prof .flat { stroke: var(--muted); stroke-width: 1; }
.box .prof .ax { fill: var(--muted); font: 8px sans-serif; }
.box .shp .rn .field[data-form="values"], .box .shp .rn .field[data-form="weights"] { width: 9em; }
.box .detail .btn { justify-self: start; }
.box .clr { display: grid; grid-template-columns: minmax(0, 1fr); gap: 4px; min-width: 0; flex: 1 1 100%; }
.box .clr .hues { display: flex; flex-wrap: wrap; gap: 4px; }
.box .clr .hues[hidden] { display: none; }
.box .clr .hue { display: inline-flex; gap: 4px; align-items: center; }
.box .clr .hue.on { background: var(--ink); color: var(--bg); }
.box .clr .chip { display: inline-block; width: 14px; height: 14px; border-radius: 3px; border: 1px solid var(--rule); }
.box .clr .chip.none { background: repeating-linear-gradient(45deg, var(--surface-2), var(--surface-2) 3px, var(--rule) 3px, var(--rule) 4px); }
.box .clr .lvls { display: grid; grid-template-columns: minmax(0, 1fr); gap: 4px; min-width: 0; }
.box .clr .lvl .field { width: 4.5em; }
.box .clr .src { overflow-wrap: anywhere; }
.sec > .newc { display: grid; grid-template-columns: minmax(0, 1fr); gap: 4px; min-width: 0; margin-top: 6px; border: 1px solid var(--rule); border-radius: 5px; padding: 5px 7px; background: var(--surface-2); font-size: 12.5px; }
.sec > .newc > summary { cursor: pointer; font-size: 12.5px; font-weight: 600; width: max-content; max-width: 100%; }
.newc .rn { display: inline-flex; flex-wrap: wrap; gap: 3px; align-items: center; min-width: 0; max-width: 100%; font-size: 12px; color: var(--muted); }
.newc .rn .unit { font-size: 12px; overflow-wrap: anywhere; min-width: 0; }
.newc .src { font-size: 12px; color: var(--muted); overflow-wrap: anywhere; }
.newc select.field { width: auto; max-width: 100%; }
.newc .nf { display: flex; flex-wrap: wrap; gap: 4px 10px; }
.newc .nf[hidden], .newc [data-newset-only][hidden], .newc [data-newc-set][hidden] { display: none; }
.newc .nf .field { width: 4.5em; }
.newc .newc-do { display: flex; flex-wrap: wrap; gap: 6px; }
.newc .newc-out { overflow-wrap: anywhere; }
.newc .chip, .pairs .chip { display: inline-block; width: 14px; height: 14px; border-radius: 3px; border: 1px solid var(--rule); vertical-align: -2px; margin-right: 4px; }
.pairs .chip.none { background: repeating-linear-gradient(45deg, var(--surface-2), var(--surface-2) 3px, var(--rule) 3px, var(--rule) 4px); }
.box .pairs { border-collapse: collapse; font-size: 12px; max-width: 100%; table-layout: fixed; }
.box .pairs th { font-weight: 500; text-align: left; padding: 2px 6px 2px 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.box .pairs thead th { text-align: center; padding: 2px 3px; }
.box .pairs .corner { display: grid; color: var(--muted); font-size: 11px; line-height: 1.2; text-align: left; }
.box .pairs td { text-align: center; padding: 2px 3px; border: 1px solid var(--rule); }
.box .pairs td.diag { background: repeating-linear-gradient(45deg, transparent, transparent 3px, var(--rule) 3px, var(--rule) 4px); }
.box .pairs .tick { width: 16px; height: 16px; margin: 0; cursor: pointer; }
.box.group .sentence { display: flex; flex-wrap: wrap; align-items: center; gap: 4px 5px; min-width: 0; font-size: 13px; }
.box.group .sentence .gs { overflow-wrap: anywhere; min-width: 0; }
.box.group .gr { margin-top: 4px; overflow-wrap: anywhere; min-width: 0; font-size: 13px; }
.box.group .gm { display: flex; flex-wrap: wrap; align-items: center; gap: 4px 6px; flex: 1 1 100%; min-width: 0; }
.box.group .gl { font-size: 12.5px; min-width: 0; overflow-wrap: anywhere; }
.box .gmore { display: grid; gap: 2px; min-width: 0; }
.box .gmore + .gmore { margin-top: 4px; padding-top: 4px; border-top: 1px dotted var(--rule); }
.box .gmore .gn { font-weight: 600; }
.fu:has(> .over) { display: flex; flex-wrap: nowrap; width: 100%; }
.field.over { flex: 1 1 auto; width: auto; min-width: 0; max-width: 100%; }
.box select.field, .box .rn select.field { width: auto; max-width: 100%; }
#moments .rv { font-size: 11.5px; color: var(--muted); margin: -2px 0 6px; overflow-wrap: anywhere; }
.ev.ctl .kind { color: var(--accent); }
.controlbar .sep { width: 1px; align-self: stretch; background: var(--rule); margin: 0 4px; }
.tsel { display: inline-flex; align-items: center; gap: 6px; }
.tsel .k { font-family: var(--cond); font-weight: 600; font-size: 12px; letter-spacing: 0.06em; text-transform: uppercase; color: var(--muted); }
.tsel select { font-family: var(--mono); font-size: 13.5px; padding: 4px 6px; }
.tsel .field { width: 5em; border-radius: 3px; }
button.pill { border: 0; cursor: pointer; }
.btn.go { background: var(--ok); border-color: var(--ok); color: var(--bg); }
.pf { display: grid; grid-template-columns: minmax(0, 1fr); gap: 0 20px; }
.pf .row { display: grid; grid-template-columns: 12px minmax(0, 10em) minmax(0, 1fr) auto; gap: 8px; align-items: center; font-size: 13px; padding: 3px 0; border-bottom: 1px solid var(--rule); min-height: 30px; }
.pf .val { font-family: var(--mono); font-size: 12px; color: var(--muted); overflow-wrap: anywhere; }
#warnings .row, #dn-warnings .row { display: grid; grid-template-columns: minmax(0, 10em) minmax(0, 1fr); gap: 2px 8px; font-size: 13px; padding: 3px 0; border-bottom: 1px solid var(--rule); }
#warnings .val, #dn-warnings .val { font-family: var(--mono); font-size: 12px; color: var(--muted); overflow-wrap: anywhere; }
#warnings .sub, #dn-warnings .sub { grid-column: 2; }
.st { width: 10px; height: 10px; border-radius: 50%; }
.st.pass { background: var(--ok); } .st.warn { background: var(--warn); } .st.fail { background: var(--crit); } .st.untested { box-shadow: inset 0 0 0 1.5px var(--muted); }
.chk { display: flex; gap: 8px; align-items: center; font-size: 13px; }
#rt-train:empty { display: none; }
#rt-shaping:empty { display: none; }
[data-cmd="shaping"][aria-pressed="true"] { background: var(--accent-soft); border-color: var(--accent); color: var(--ink); }
.prompt { border-radius: 6px; padding: 8px 12px; background: var(--ok-soft); border-left: 4px solid var(--ok); display: grid; gap: 6px; font-size: 13.5px; }
.prompt.back { background: var(--warn-soft); border-left-color: var(--warn); }
.prompt .acts { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
.dialog .grid { display: grid; grid-template-columns: auto 1fr; gap: 8px 12px; align-items: center; }
.dialog .end { display: flex; gap: 8px; justify-content: flex-end; flex-wrap: wrap; }
.dialog .field, .dialog select { width: 100%; border-radius: 3px; font: inherit; }
#amend-to, #ret-at { width: 13em; }
#end-return { width: 32ch; }
#amend-why { width: min(28em, 50vw); }
body.stale .strip, body.stale .panels { filter: grayscale(1); opacity: 0.55; }
.pill.demo { background: var(--mock); color: var(--bg); }
.demo-screen { position: relative; border-radius: 5px; background: var(--screen); min-height: 120px; overflow: hidden; cursor: crosshair; }
.demo-drawing svg { display: block; width: 100%; height: auto; }
.demo-none { position: absolute; inset: 0; display: grid; place-items: center; padding: 8px; text-align: center; color: var(--screen-ink); font-family: var(--mono); font-size: 12px; }
.demo-dot { position: absolute; width: 12px; height: 12px; margin: -6px 0 0 -6px; border-radius: 50%; background: #ff3b30; box-shadow: 0 0 0 2px #ffffff; pointer-events: none; }
.demo-dot.lost { background: transparent; box-shadow: 0 0 0 2px #ff3b30; }
.demo-bar { display: flex; flex-wrap: wrap; gap: 4px 12px; align-items: baseline; font-size: 12.5px; }
.demo-bar .k { color: var(--muted); }
.demo-esc { display: none; }
.demo-keylist kbd { font-family: var(--mono); font-size: 11.5px; border: 1px solid var(--rule); border-radius: 3px; padding: 0 4px; background: var(--surface-2); white-space: nowrap; }
.demo-limits { margin: 0; padding-left: 16px; font-size: 12px; color: var(--muted); display: grid; gap: 3px; }
.demo-pane.full { position: fixed; inset: 0; z-index: 25; border-radius: 0; padding: 0; gap: 0; background: #000000; color: #e8eaed; grid-template-rows: minmax(0, 1fr) auto; }
.demo-pane.full > .top, .demo-pane.full > .demo-fold, .demo-pane.full > #demo-who { display: none; }
.demo-fold > summary { cursor: pointer; font-size: 12.5px; color: var(--muted); }
.demo-fold[open] > summary { margin-bottom: 4px; }
.demo-pane.full .demo-screen { border-radius: 0; min-height: 0; background: #000000; }
.demo-pane.full .demo-drawing { position: absolute; inset: 0; }
.demo-pane.full .demo-drawing svg { width: 100%; height: 100%; }
.demo-pane.full .demo-bar { padding: 8px 14px; }
.demo-pane.full .demo-bar .k, .demo-pane.full .demo-esc { color: #8ea0bc; }
.demo-pane.full .demo-esc { display: inline; }
body.demo-full { overflow: hidden; }
#dn-demo .chk { align-items: baseline; }
@media (prefers-reduced-motion: reduce) { * { transition: none !important; } }
"""

#: The wl.works mark, as the mockup draws it. No `xmlns`: an inline SVG in an HTML
#: document needs none, and the page names no other host, not even as a namespace.
_LOGO = (
    '<svg viewBox="0 0 395.67 147.54" role="img" aria-label="wl.works">'
    '<circle cx="130.40" cy="34.98" r="11" fill="currentColor"/>'
    '<circle cx="97.40" cy="11.00" r="11" fill="currentColor"/>'
    '<circle cx="56.60" cy="11.00" r="11" fill="currentColor"/>'
    '<circle cx="23.60" cy="34.98" r="11" fill="#C9187B"/>'
    '<circle cx="11.00" cy="73.77" r="11" fill="currentColor"/>'
    '<circle cx="23.60" cy="112.56" r="11" fill="currentColor"/>'
    '<rect x="45.6" y="125.54" width="22" height="22" fill="currentColor"/>'
    '<circle cx="97.40" cy="136.54" r="11" fill="currentColor"/>'
    '<text x="71" y="112.77" font-family="Newsreader, Georgia, serif" font-size="72" '
    'font-weight="700" letter-spacing="-1.44" fill="currentColor">w'
    '<tspan font-style="italic">l</tspan>'
    '<tspan style="fill: var(--wl-muted)">.works</tspan></text></svg>'
)

#: **The page's whole script, and all it does** (spec §4.3, §4.4, and since P4d-2b
#: b2a §5.2): open the event stream, swap each fragment into the element with its id,
#: run the stale timer while more frames are due, close the stream on the ✕, and
#: reconnect -- and, from b2a, send the controls as JSON `POST`s to `/commands`,
#: debounce the parameter arrows, handle the **P** and **M** keys, and ask for the
#: operator's name. `EventSource` reconnects on its own after a dropped connection,
#: and `wlx serve` sends a full render first on every new stream, so a reconnect
#: re-renders in full. **It still renders nothing itself**: every `innerHTML` it
#: writes is a fragment `wlx serve` rendered, and what it writes of its own -- the
#: name and the last command's answer -- goes in as `textContent`.
#:
#: **The stale timer runs from the frame's age, not from an event's arrival**
#: (Ruling 12, 2026-09-27). Every event carries `age`, the seconds `wlx serve` has
#: held the latest frame; the baseline is the arrival less that, and the stream is
#: stale once `now - baseline` reaches `--stale-after` -- `>=`, so the page agrees
#: with `/health`'s own boundary -- with that interval as the banner's N. A `null`
#: age -- no frame yet -- runs no timer. It shares with `/health` *when* frames are
#: due (`live`, `health.expects_frames`), not the clock: this one is the page's own
#: `performance.now()`, monotonic so a browser clock step never skews it, carried
#: from `wlx serve`'s steady clock by `age`.
#:
#: **A lost stream is greyed as a stale one is** (m3): the timer stands down while
#: the stream is lost, so without this a red *stream lost* banner sat over
#: full-color numbers nothing was updating. The next frame's `check()` clears it.
#:
#: **The controls (P4d-2b b2a).** The box's own page may write (`data-can-write` on
#: `<body>`, from `View.can_write`), and since b2b so may the rig's https page while a
#: wl.works member is signed in there (`data-signin`, the sign-in's block below);
#: everywhere else every control is disabled in the HTML and `post` sends nothing. The
#: name is asked once, kept in `localStorage` -- inside `try`, since a private window
#: may refuse it -- and a prompt refused or cleared sends nothing. **A setting's box sends
#: nothing until its Apply** (the console interface rework's Task 6): an edit is a draft, Enter
#: in a field is Apply, Esc is Discard, Apply all sends every box's draft as one act, a waiting
#: act can be withdrawn; each box is patched alone, and one with a draft, a focused field or its
#: act out keeps its editor's nodes, so a frame never replaces an input under a person's hands;
#: a frame for a root a pointer is down in waits for the press to end. P and M do
#: nothing in a text box or when held. A mark sends its signal at once with
#: `pressed_at` -- the browser's clock, and the only `Date.now()` outside the sign-in's
#: block, which reads it for its tokens' expiry -- then opens the note box: Enter
#: attaches the note, Esc leaves the mark bare, and a second mark leaves the first bare.
#:
#: **Sessions from the page (P4d-2b b3a-2).** Choosing a task between runs, or pressing the
#: pre-flight pill, takes the pre-flight (`check`); *start run* sends the task of the
#: pre-flight shown, the trial count and the unknown items ticked, then clears the ticks;
#: *new session* sends the dialog's fields as typed, and they are cleared once the page
#: shows that session open (the b3a-2 final review, I1); *end session* sends the return typed, or
#: none for later; a warning's *confirm* or *amend* re-sends the open or the return this
#: page sent, with its answer, and a warning this page did not raise is not answered.
#: A swap keeps a select's chosen option and the ticks. It still renders nothing itself.
_SCRIPT = """
(function () {
  "use strict";
  var body = document.body;
  var staleMs = Number(body.getAttribute("data-stale-after")) * 1000;
  var canWrite = body.getAttribute("data-can-write") === "1";
  var NAME_KEY = "wlx-console-name";
  // P4d-2b b2b (spec §4): signing a member in on the rig's https page. The tokens live
  // in this tab's sessionStorage only; Python renders every word a person reads.
  var signinPage = body.getAttribute("data-signin") === "1";
  var SIGNIN_KEY = "wlx-signin";
  var PKCE_KEY = "wlx-signin-pkce";
  // Housekeeping, not measurements (spec §4): renew this long before the hour is up,
  // and renew first before a command when less than this is left.
  var RENEW_BEFORE_MS = 5 * 60 * 1000;
  var FRESH_FOR_MS = 60 * 1000;
  // Housekeeping too, rendered by Python (`web.SIGNIN_RETRY_MS`): while wl.works or this
  // rig cannot be reached, a renewal or a confirmation is tried again this often, and a
  // renewal at the token's lapse when that comes first (spec §7; b2b-ready §4.1-§4.3).
  var RETRY_MS = Number(body.getAttribute("data-retry-ms")) || 30 * 1000;
  // How often a page that could offer no sign-in asks this rig again (b2b-ready §4.6),
  // rendered by Python (`web.KEYS_RECHECK_MS`); housekeeping.
  var RECHECK_MS = Number(body.getAttribute("data-recheck-ms")) || 60 * 1000;
  // One sign-in per tab (b2b-ready §4.5; XC-224). A duplicated tab copies sessionStorage,
  // and with it the renewal token. The tab holding a sign-in holds a lock named by its id
  // while it is open, and a tab that finds its stored sign-in's lock held elsewhere is a
  // duplicate. Housekeeping, not a measurement: how long a page waits for that lock, which
  // a reloading tab's old document gives up as it goes. Rendered by Python
  // (`web.SIGNIN_LOCK_WAIT_MS`).
  var LOCK_WAIT_MS = Number(body.getAttribute("data-lock-wait-ms")) || 1000;
  var DUPLICATE = "this sign-in is in use in another tab; use that tab, or sign in again here";
  var releaseLock = null;
  // True while this tab holds its sign-in's lock, or cannot tell (no Web Locks). Until then
  // the stored sign-in may be another tab's copy: it is neither renewed nor signed out at
  // the rig, either of which would end the original's.
  var lockHeld = false;
  // Why the page signs itself out at a lapse (b2b-ready §4.1): wl.works out of reach (the
  // final review, I1), wl.works answering without a token, or this rig never confirming.
  var UNREACHED = "wl.works could not be reached to renew this sign-in; the rig PC's page keeps every control";
  var NOT_RENEWED = "wl.works did not renew this sign-in before it lapsed; the rig PC's page keeps every control";
  var NEVER_CONFIRMED = "this rig did not confirm the sign-in before it lapsed; the rig PC's page keeps every control";
  // What the page says while it keeps a sign-in it is trying to renew or confirm.
  var RETRYING = "could not reach wl.works to renew this sign-in; trying again until it lapses";
  var BUSY = "wl.works could not renew this sign-in just now; trying again until it lapses";
  var UNCONFIRMED = "this rig has not confirmed the sign-in; trying again";
  var NO_SIGNIN = "sign in with wl.works to use the controls";
  var renewTimer = null;
  var lapseTimer = null;
  var confirmTimer = null;
  function readStore(key) {
    try { return JSON.parse(window.sessionStorage.getItem(key) || "null"); } catch (e) { return null; }
  }
  function writeStore(key, value) {
    try {
      if (value === null) { window.sessionStorage.removeItem(key); }
      else { window.sessionStorage.setItem(key, JSON.stringify(value)); }
    } catch (e) { /* this tab's memory only, then */ }
  }
  var signin = signinPage ? readStore(SIGNIN_KEY) : null;
  function signedIn() { return !!(signin && signin.name); }
  function b64url(bytes) {
    var text = "";
    for (var i = 0; i < bytes.length; i++) { text += String.fromCharCode(bytes[i]); }
    return btoa(text).replace(/\\+/g, "-").replace(/\\//g, "_").replace(/=+$/, "");
  }
  function random(n) { var bytes = new Uint8Array(n); crypto.getRandomValues(bytes); return b64url(bytes); }
  // Whether /whoami has confirmed the sign-in this tab holds. A sign-in read back from
  // sessionStorage enables nothing until it has been.
  var confirmed = false;
  // The one renewal in flight, or null: every caller shares it, because a second use of
  // the same renewal token is a reuse to wl.works, which ends every sign-in of the member.
  var renewing = null;
  // Bumped by every `forget()` and every new sign-in (`keep`): an answer that arrives
  // after it changed belongs to a sign-in this tab no longer holds, and is dropped
  // without being kept, stored or shown. A sign-out must stand against a renewal in flight.
  var generation = 0;
  // Why the page last signed itself out, so a press that finds it signed out says so
  // (`post`). Empty after every other sign-out (one someone asked for, or the rig's
  // refusal of the token in `deliver`) and after a new sign-in.
  var signedOutFor = "";
  // Why the sign-in this tab holds would end, were its lapse now: empty while nothing has
  // gone wrong since wl.works last renewed it and this rig last confirmed it.
  var trouble = "";
  // Why the sign-in this tab holds cannot act now though it is held (this rig has not
  // confirmed it, cannot check sign-ins, or disagrees on the time); empty when it can.
  var unusableFor = "";
  // From a renewal's new pair (`keep`) until this rig has answered /whoami for it: a press
  // then waits for that renewal (`fresh`), never sending a token the rig has not seen.
  var confirming = false;
  // When the renewal in flight began, and how the lapse ends it (`lapse`).
  var renewStarted = 0;
  var endRenewal = null;
  function applySignIn() {
    if (!signinPage) { return; }
    body.setAttribute("data-signed-in", signedIn() ? "1" : "0");
    var member = el("member");
    if (member) { member.textContent = signedIn() ? signin.shown : ""; }
    var usable = signedIn() && confirmed;
    Array.prototype.forEach.call(document.querySelectorAll("[data-signin]"), function (node) {
      // A reward button held until its answer stays held, signed in or not, and the subject a
      // demo locks to REFERENCE stays locked (demo mode's Task 9).
      if (node.hasAttribute("data-held") || node.hasAttribute("data-demo-locked")) { return; }
      node.disabled = !usable;
      if (usable) {
        if (node.hasAttribute("title")) {
          node.setAttribute("data-signin-title", node.getAttribute("title"));
          node.removeAttribute("title");
        }
      } else if (node.hasAttribute("data-signin-title")) {
        node.setAttribute("title", node.getAttribute("data-signin-title"));
        node.removeAttribute("data-signin-title");
      }
    });
  }
  function startSignIn() {
    var verifier = random(32);
    var state = random(16);
    crypto.subtle.digest("SHA-256", new TextEncoder().encode(verifier)).then(function (digest) {
      writeStore(PKCE_KEY, { verifier: verifier, state: state });
      var url = new URL(body.getAttribute("data-authorize"));
      var fields = {
        response_type: "code",
        client_id: body.getAttribute("data-client"),
        redirect_uri: body.getAttribute("data-page"),
        scope: "offline_access",
        resource: body.getAttribute("data-resource"),
        code_challenge: b64url(new Uint8Array(digest)),
        code_challenge_method: "S256",
        state: state
      };
      Object.keys(fields).forEach(function (key) { url.searchParams.set(key, fields[key]); });
      window.location.assign(url.toString());
    });
  }
  function tokenRequest(fields) {
    return fetch(body.getAttribute("data-token-endpoint"), {
      method: "POST",
      credentials: "omit",
      cache: "no-store",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams(fields).toString()
    }).then(function (response) {
      return response.json().then(
        function (answer) { return { ok: response.ok, status: response.status, answer: answer || {} }; },
        function () { return { ok: false, status: response.status, answer: {} }; }
      );
    });
  }
  // A new pair from wl.works. `prior` is the sign-in a renewal replaces, whose member it
  // keeps; `null` for a new sign-in.
  function keep(answer, prior) {
    generation += 1;
    signedOutFor = "";
    trouble = "";
    unusableFor = "";
    signin = {
      id: prior ? prior.id : random(16),
      access: answer.access_token,
      refresh: answer.refresh_token || (prior && prior.refresh) || null,
      expires: Date.now() + Number(answer.expires_in) * 1000,
      name: prior ? prior.name : null,
      shown: prior ? prior.shown : null
    };
    armLapse();
  }
  function forget(why) {
    generation += 1;
    signin = null;
    confirmed = false;
    confirming = false;
    trouble = "";
    unusableFor = "";
    signedOutFor = why || "";
    if (releaseLock) { releaseLock(); releaseLock = null; }
    lockHeld = false;
    writeStore(SIGNIN_KEY, null);
    clearTimeout(renewTimer);
    clearTimeout(lapseTimer);
    clearTimeout(confirmTimer);
    applySignIn();
  }
  // The page signs itself out, saying why now and on any press after (`post`).
  function dropSignIn(why) {
    forget(why);
    tell("signed out: " + why, "crit");
  }
  // What a page served while this rig could not check sign-ins says of itself: the sentence
  // in `#mode`, which Python renders with no token endpoint.
  function unavailable() {
    var said = el("mode") ? el("mode").querySelector(".nm") : null;
    return said ? said.textContent : "not signed in: this rig cannot check sign-ins";
  }
  // Every sign-in ends at its access token's lapse unless a renewal has replaced that token
  // by then, whatever is in flight (b2b-ready §4.1). A renewal begun before the lapse ends
  // with it; one begun at or after it (a tab whose timers were held back, the rig's
  // `expired`) is given RETRY_MS (the plan's Ruling 2).
  function deadline() {
    if (renewing && renewStarted >= signin.expires) { return renewStarted + RETRY_MS; }
    return signin.expires;
  }
  function armLapse() {
    clearTimeout(lapseTimer);
    if (signin) { lapseTimer = setTimeout(lapse, Math.max(0, deadline() - Date.now())); }
  }
  function lapse() {
    if (!signin) { return; }
    if (deadline() > Date.now()) { armLapse(); return; }
    if (!renewing && trouble !== NEVER_CONFIRMED) {
      // No renewal in flight at the lapse: one more, within RETRY_MS of its own. A tab whose
      // timers were held back renews here, and so does a retry due at the lapse itself;
      // wl.works still out of reach then signs the page out (`notRenewed`).
      renew();
      armLapse();
      return;
    }
    var end = endRenewal;
    dropSignIn(trouble || (confirming ? NEVER_CONFIRMED : UNREACHED));
    if (end) { end(); }
  }
  // Resolves true when this tab holds the lock of sign-in `id`, false when another tab
  // does. A browser without Web Locks cannot tell, and is let through (b2b-ready §4.5).
  function holdLock(id) {
    if (releaseLock) { releaseLock(); releaseLock = null; }
    lockHeld = false;
    if (!id || !navigator.locks) { lockHeld = true; return Promise.resolve(true); }
    return new Promise(function (resolve) {
      var abort = new AbortController();
      var timer = setTimeout(function () { abort.abort(); }, LOCK_WAIT_MS);
      navigator.locks.request("wlx-signin:" + id, { signal: abort.signal }, function () {
        clearTimeout(timer);
        // The sign-in was forgotten or replaced during the wait: nothing here is to be
        // held. Resolves true, not false, so the caller does not take it for a duplicate;
        // it finds its sign-in gone or changed and stops.
        if (!signin || signin.id !== id) { resolve(true); return undefined; }
        lockHeld = true;
        resolve(true);
        return new Promise(function (release) { releaseLock = release; });
      }).catch(function () { resolve(false); });
    });
  }
  // What a rig's answer is, read from its response: **an answer the page cannot read as one is
  // read as an answer lost**, so it takes the handling every call gives a lost answer (a reward's
  // "unknown" sentence, a sign-in kept and asked again). That is a failed response (not 2xx)
  // whose body is not JSON or carries no `said`: `wlx serve`'s 500 for a handler that raised
  // has `{"error": ...}` (XC-042). **Any answer with a `said` is read as it was before, whatever
  // its status**: 503 busy, and 504 not delivered or a reward's unknown, are the rig's own
  // words, which a trainer needs as they are. The one place every call to this rig reads its
  // answer through.
  function answerOf(response) {
    return response.json().then(function (answer) {
      if (!response.ok && !(answer && typeof answer.said === "string")) {
        throw new Error("wlx serve faulted");
      }
      return answer;
    });
  }
  // /whoami with the held token. Answers true when it confirms the sign-in. A refusal
  // is read by its reason word (the plan's Ruling 8): `expired` renews (once: a token
  // just renewed is not expired), `clock` and `no_keys` keep the sign-in, say why and,
  // on a page that can renew, ask again every RETRY_MS (a restart's window without keys
  // passes, b2b-ready §3.2), and the rest end it. A rig out of reach keeps it too, greyed, asked again every
  // RETRY_MS until the lapse (b2b-ready §4.3).
  function whoami(mayRenew) {
    var mine = generation;
    clearTimeout(confirmTimer);
    return fetch("/whoami", {
      method: "POST",
      cache: "no-store",
      headers: { "Content-Type": "application/json", "Authorization": "Bearer " + signin.access },
      body: "{}"
    }).then(answerOf).then(function (answer) {
      if (mine !== generation) { return false; }
      if (answer.status === "signed_in") {
        signin.name = answer.name;
        signin.shown = answer.shown;
        confirmed = true;
        trouble = "";
        unusableFor = "";
        writeStore(SIGNIN_KEY, signin);
        scheduleRenew();
        applySignIn();
        return true;
      }
      if (answer.reason === "expired" && mayRenew) { return renew(); }
      if (answer.reason === "clock" || answer.reason === "no_keys") {
        confirmed = false;
        unusableFor = answer.said;
        tell("signed in, but not usable now: " + answer.said, "crit");
        applySignIn();
        // A page without a token endpoint waits for b2b-ready §4.6's reload, which confirms it.
        if (body.getAttribute("data-token-endpoint")) {
          confirmTimer = setTimeout(function () { if (signin) { whoami(false); } }, RETRY_MS);
        }
        return false;
      }
      forget(answer.said);
      tell("not signed in: " + answer.said, "crit");
      return false;
    }, function () {
      if (mine !== generation || !signin) { return false; }
      confirmed = false;
      unusableFor = UNCONFIRMED;
      trouble = NEVER_CONFIRMED;
      tell(UNCONFIRMED, "crit");
      applySignIn();
      confirmTimer = setTimeout(function () { if (signin) { whoami(false); } }, RETRY_MS);
      return false;
    });
  }
  // Resolves true when it exchanged a code and /whoami has already run for it.
  function finishSignIn() {
    var params = new URLSearchParams(window.location.search);
    if (!params.has("code") && !params.has("error")) { return Promise.resolve(false); }
    window.history.replaceState(null, "", window.location.pathname);
    var kept = readStore(PKCE_KEY);
    writeStore(PKCE_KEY, null);
    if (params.has("error")) {
      tell("not signed in: " + (params.get("error_description") || params.get("error")), "crit");
      return Promise.resolve(false);
    }
    if (!body.getAttribute("data-token-endpoint")) {
      tell(unavailable(), "crit");
      return Promise.resolve(false);
    }
    if (!kept || kept.state !== params.get("state")) {
      tell("not signed in: this sign-in was not started from this page", "crit");
      return Promise.resolve(false);
    }
    var mine = generation;
    return tokenRequest({
      grant_type: "authorization_code",
      code: params.get("code"),
      redirect_uri: body.getAttribute("data-page"),
      client_id: body.getAttribute("data-client"),
      code_verifier: kept.verifier
    }).then(function (result) {
      if (mine !== generation) { return false; }
      if (!result.ok || !result.answer.access_token) {
        tell("not signed in: " + (result.answer.error_description || "wl.works did not sign you in"), "crit");
        return false;
      }
      keep(result.answer, null);
      return holdLock(signin.id).then(function () { return signin ? whoami(false) : false; }).then(function () { return true; });
    }, function () {
      tell("not signed in: could not reach wl.works to finish signing in", "crit");
      return false;
    });
  }
  // Every caller shares the one renewal in flight (`renewing`). Never rejects. The lapse
  // can end it early (`endRenewal`); its late answer is then dropped (`generation`).
  function renew() {
    if (renewing) { return renewing; }
    renewStarted = Date.now();
    renewing = new Promise(function (resolve) {
      endRenewal = function () { resolve(false); };
      renewNow().then(resolve, function () { resolve(false); });
    });
    renewing.then(function () { renewing = null; endRenewal = null; });
    return renewing;
  }
  function renewNow() {
    if (!signin || !signin.refresh) {
      if (signin) { dropSignIn("this sign-in has lapsed and cannot be renewed"); } else { forget(); }
      return Promise.resolve(false);
    }
    if (!body.getAttribute("data-token-endpoint")) {
      // No token endpoint to ask; b2b-ready §4.6's recheck reloads into a page that has one.
      trouble = unavailable();
      if (signin.expires - Date.now() > 0) { return Promise.resolve(signedIn()); }
      dropSignIn(trouble);
      return Promise.resolve(false);
    }
    var mine = generation;
    var prior = signin;
    return tokenRequest({
      grant_type: "refresh_token",
      refresh_token: signin.refresh,
      client_id: body.getAttribute("data-client")
    }).then(function (result) {
      if (mine !== generation) { return false; }
      if (result.ok && result.answer.access_token) {
        keep(result.answer, prior);
        // The renewal token just presented is spent: the new pair is stored now, not once
        // the rig has confirmed it, or a reload would present the spent one. The controls
        // stay tied to /whoami (`confirmed`), and a press waits for it (`confirming`).
        writeStore(SIGNIN_KEY, signin);
        confirming = true;
        return whoami(false).then(function (ok) { confirming = false; return ok; });
      }
      // Only wl.works' own refusal ends the sign-in (b2b-ready §4.2): 400 or 401 with an
      // OAuth error. Any other answer without a token is no answer.
      if ((result.status === 400 || result.status === 401) && typeof result.answer.error === "string") {
        dropSignIn(result.answer.error_description || "wl.works did not renew this sign-in");
        return false;
      }
      return notRenewed(NOT_RENEWED, BUSY);
    }, function () {
      if (mine !== generation) { return false; }
      return notRenewed(UNREACHED, RETRYING);
    });
  }
  // wl.works did not renew, and did not refuse. The token works at the rig until it lapses
  // (the check is offline): keep the sign-in and try again, at the lapse at the latest.
  // Once it has lapsed, the page signs itself out with `why` (spec §7; b2b-ready §4.1-§4.2).
  function notRenewed(why, now) {
    trouble = why;
    var left = signin.expires - Date.now();
    if (left > 0) {
      tell(now, "crit");
      clearTimeout(renewTimer);
      renewTimer = setTimeout(renew, Math.min(left, RETRY_MS));
      return signedIn();
    }
    dropSignIn(why);
    return false;
  }
  function scheduleRenew() {
    clearTimeout(renewTimer);
    if (!signin) { return; }
    var left = signin.expires - Date.now();
    renewTimer = setTimeout(renew, Math.max(left / 2, left - RENEW_BEFORE_MS));
  }
  function fresh() {
    // Between a renewal's new pair and the rig's confirmation of it, a press waits for that
    // renewal rather than being sent with a token the rig has not yet seen (`confirming`).
    if (confirming) { return renewing || Promise.resolve(false); }
    if (!signedIn() || unusableFor) { return Promise.resolve(false); }
    if (signin.expires - Date.now() > FRESH_FOR_MS) { return Promise.resolve(true); }
    return renew();
  }
  // The rig refused a command as `expired` (b2b-ready §4.4), the token it carried being
  // `refused`: the rig's offline check is the authority, so that token has lapsed whatever
  // the page counted. Acts on that token only: a newer one already held is not clamped or
  // renewed again. Resolves true only when the page holds a token newer than `refused`.
  function expiredAtTheRig(refused) {
    if (!signin) { return Promise.resolve(false); }
    if (signin.access !== refused) { return Promise.resolve(true); }
    signin.expires = Math.min(signin.expires, renewing ? renewStarted : Date.now());
    var renewal = renew();
    armLapse();
    return renewal.then(function (ok) { return ok && !!signin && signin.access !== refused; });
  }
  function signOut() {
    var held = signin;
    var post = lockHeld;  // a copy still waiting for its lock is forgotten, never signed out
    forget();
    // wl.works itself stays signed in, so the next sign-in here goes straight through as
    // the same member (spec §2): on a shared browser, the next person must sign out there.
    tell(held && held.name
      ? "signed out at this rig; wl.works is still signed in as " + held.name +
        ", so anyone else using this browser must sign out of wl.works there first"
      : "signed out at this rig", "ok");
    if (!held || !post) { return; }
    fetch("/signout", {
      method: "POST",
      cache: "no-store",
      headers: { "Content-Type": "application/json", "Authorization": "Bearer " + held.access },
      body: "{}"
    }).catch(function () { /* the tab has forgotten it either way */ });
  }
  // Housekeeping -- a double click's span with margin -- not a measurement: keeps a
  // double click, or a re-render's fresh button under the second click of one, from
  // toggling a pause or resume the first click already sent (spec §5.2: "never a
  // toggle").
  var TOGGLE_HOLD_MS = 1000;
  var lastToggleAt = -Infinity;
  var source = null;
  var baseline = null;
  var live = false;
  var lost = false;
  var closed = false;
  var heldMoments = null;
  // **The two tabs of setting boxes**, which every patch and every box lookup reads alike.
  var CARDS = ["#params", "#training-params"];
  function inCards(selector) {
    return CARDS.map(function (root) { return root + " " + selector; }).join(", ");
  }
  var pressedAt = null;
  var PRESS_MS = 10000;
  // **A frame held while a pointer is down in its root** (fix round 2 of the C3 plan's Task 18: a
  // frame landing between the mouse going down and up replaced the button under it, in WebKit
  // above all), by root id, patched in once the press ends (`release`). The newest only.
  var heldCards = {};
  // **Drafts, Apply, Apply all and withdraw** (the console interface rework's Task 6; the PI,
  // 2026-11-19: "i prefer an apply button in each box for making a change"; the controls
  // review's §2 and §3). Nothing a box holds is sent until its Apply, Enter in one of its fields,
  // or Apply all. Each box is patched alone (`patchCards`): a box with a draft, a field or select
  // focused in it, or its act out keeps its editor's nodes, and only its head and status line --
  // and *more*, but for a draft's range numbers -- take the frame's news, so a press lands on a
  // node no frame replaced. By setting name:
  // - `served`, each box as the latest frame drew it, never shown: what a draft is judged against
  //   and what Discard puts back;
  // - `drafts`, each box's draft, `{changes, error}` (`draftOf`), kept across frames and tab
  //   switches, dropped at the run's end (`data-run`) and on a reload;
  // - `out`, each box whose act this page sent and the rig has not yet answered in a frame,
  //   `{cid, state, snapshot, phase: "sending" | "waiting", answered}`: what was sent, which a draft
  //   is judged against meanwhile;
  // - `refusedAt`, the act of the box the rig refused and the draft it refused, so the box says
  //   *refused* while that draft stands; `notes`, a line the page says on a box until its news
  //   changes (a send not delivered, a withdrawal's answer); `refusals`, each box's refusal as
  //   first seen and whether a later change of the setting has been accepted since (the design's
  //   goal 4); `since`, the trial in force when each draft began, so a change made under it is said.
  // And by command id: `acts`, the settings of each act this page sent; `mine`, every id it made;
  // `withdrawing`, each act whose withdrawal is out.
  var served = {};
  var drafts = {};
  var out = {};
  var refusedAt = {};
  var notes = {};
  var refusals = {};
  var since = {};
  var kept = {};
  var acts = {};
  var mine = {};
  var withdrawing = {};
  var runKey = null;
  // The page's own command ids: a random prefix per page and a count, printable, at most 64
  // characters (`link.CID_LIMIT`).
  var pageId = random(6);
  var cidCount = 0;
  var APPLY_ALL_LIMIT = Number(body.getAttribute("data-apply-all-limit")) || 50;
  // The box's words (the console interface design's goal 4; the plan's "Words on the page").
  var NOT_SENT = "not sent";
  var SENDING = "sending…";
  var CANNOT = "cannot send · ";
  var ALONE = "sent alone · cannot be withdrawn";
  var TOGETHER = "refused · with the changes applied together";
  var WITHDRAWN = "withdrawn · it never applied";
  // Short beside *withdraw*, its whole in the line's title (the whole-build review's I4; `web
  // .WAITING`): `WHOLE_OF` gives a line's title where it is not the line itself.
  var WAITING_YOU = "waiting · you";
  var WHOLE_OF = {};
  WHOLE_OF[WAITING_YOU] = "waiting for the next trial · you";
  var WHOLE = "whole numbers only";
  var WITHDRAWING = "withdrawing…";
  var NO_WORD = "not confirmed by the rig · check the value in force";
  // **How many frames an act answered *sent* waits for the rig's word** (the whole-build review's
  // I2) -- housekeeping, not a measurement: the rig answers a command on the first frame after the
  // drain that reads it, the frame this page's answer races or the next, and a refusal or a
  // withdrawal stays on every frame after; a third frame without it is a word lost (a frame
  // missed while the change came and went, a refusal no box is named for). Counted by frames, so
  // a paused rig's, which come every housekeeping pass, count alike. `framesSeen` counts them.
  var ANSWER_FRAMES = 3;
  var framesSeen = 0;
  // A color card's set a person chose to see the hues of (the design's §6), by setting, kept
  // across the frames that replace the cards until a hue of it is picked.
  var colorSets = {};
  // A color card's New color panel (the console settings build's Task 8; the design's §6), by
  // setting: open or not, its method, its set, what is typed and the last preview, kept across the
  // frames that replace the cards.
  var newColors = {};
  var markNo = null;
  var rewarding = false;
  var REWARD_LOST = "unknown: this page lost wlx serve's answer, so whether the reward was given is not known, and it was not sent again; check the session's fluid total before pressing again";
  // Housekeeping, not a measurement (R2, 2026-09-28): the same double click's span as
  // TOGGLE_HOLD_MS, since a reward's answer can return well inside it on loopback,
  // leaving the button live again before a double click's second click lands.
  var REWARD_HOLD_MS = 1000;
  var lastRewardAt = -Infinity;
  // A clear is held as a reward is (Task 9's fix round): the button stays until the next trial
  // boundary, so a double click, or two quick ones, cleared two trials. Kept per button -- the
  // condition and whether it is *the rest* -- so *clear one* then *the rest* still go.
  var lastClearAt = {};
  // P4d-2b b3a-2 (spec §6.2). The last open and the last return this page sent, kept so
  // an answer to the warning they raise re-sends the same typed time with it -- the rig
  // takes an answer only for the time it asked about (`service._unasked`); the unknown
  // pre-flight items ticked, by name, for the run about to start, cleared whenever a
  // pre-flight is asked for or a run started, so no tick outlives the run it was for;
  // and the session the return form is for.
  var lastOpen = null;
  var lastEnd = null;
  // The session id of an open this page sent and has not yet seen open (`settleOpen`).
  var pendingOpen = null;
  var acked = {};
  // What a person picked in the run's start (the pop-out search build's Task 6): the stage, each
  // staircase's level and each pairing, kept across the frames that redraw the pre-flight, and
  // cleared as the ticks are: whenever a pre-flight is asked for or a run started.
  var picked = {};
  // The pairings a person ticked in the trainer's panel's widening (the pop-out search build's
  // Task 7), by the suggestion they were ticked for and each pairing's number, kept across the
  // frames that redraw the panel.
  var widened = {};
  var returnFor = null;
  function el(id) { return document.getElementById(id); }
  function say(text, tone) {
    var banner = el("stream");
    banner.textContent = text || "";
    banner.className = "banner " + (tone || "");
    banner.hidden = !text;
  }
  function check() {
    if (closed || lost) { return; }
    if (!live || baseline === null) {
      body.classList.remove("stale");
      say("");
      return;
    }
    var held = performance.now() - baseline;
    if (held >= staleMs) {
      body.classList.add("stale");
      say("stream stale · last frame " + Math.floor(held / 1000) + " s ago", "warn");
    } else {
      body.classList.remove("stale");
      say("");
    }
  }
  function cardOf(name) {
    return document.querySelector(inCards('.box[data-card="' + CSS.escape(name) + '"]'));
  }
  function showSide(card, which) {
    Array.prototype.forEach.call(card.querySelectorAll("[data-side]"), function (side) {
      side.hidden = side.getAttribute("data-side") !== which;
    });
    Array.prototype.forEach.call(card.querySelectorAll("[data-switch]"), function (button) {
      var on = button.getAttribute("data-switch") === which;
      button.classList.toggle("on", on);
      button.setAttribute("aria-pressed", on ? "true" : "false");
    });
  }
  function showShape(card, shape) {
    var select = card.querySelector("select[data-shape]");
    if (select) { select.value = shape; }
    Array.prototype.forEach.call(card.querySelectorAll("[data-fields]"), function (group) {
      group.hidden = group.getAttribute("data-fields") !== shape;
    });
  }
  // **The setting opened in each settings tab's editor** (the summary and editor design's goals 2
  // and 5; the PI, 2026-11-19: "clicking opens the ability to change it below"): a click on a
  // summary line (`.line[data-open]`) shows that setting's box -- or its section's New color…
  // panel, `new-color:SECTION` -- in the editor below, every other hidden and the placeholder with
  // them, its line `aria-pressed`; nothing above the editor moves. Kept per task and per tab, the
  // last opened, in the browser's own storage under `wlx.opened.<task>` for the Task parameters
  // tab and `wlx.training-opened.<task>` for the Training tab, every access inside `try`, and held
  // for the page as well, so a store that throws keeps it while the page is shown; shown again on
  // a reload and after every frame (`applyOpened`). One no longer among the tab's settings -- a
  // new task or run without it, a group regrouped -- is dropped, and the placeholder said (the
  // plan's Review Focus 2). Sections no longer fold: the summary is short enough (the design's
  // call), so `wlx.sections.<task>` is no longer read or written.
  var OPENED_KEY = "wlx.opened.";
  var TRAINING_OPENED_KEY = "wlx.training-opened.";
  var NEW_COLOR_OPEN = "new-color:";
  var openedHeld = {};
  function openedKey(root) {
    var summary = root.querySelector(":scope > .summary");
    if (!summary) { return null; }
    return (root.id === "training-params" ? TRAINING_OPENED_KEY : OPENED_KEY) +
      (summary.getAttribute("data-task") || "");
  }
  function readOpened(key) {
    if (!Object.prototype.hasOwnProperty.call(openedHeld, key)) {
      var name = null;
      try {
        var raw = window.localStorage.getItem(key);
        name = typeof raw === "string" && raw !== "" ? raw : null;
      } catch (e) { name = null; }
      openedHeld[key] = name;
    }
    return openedHeld[key];
  }
  function writeOpened(key, name) {
    openedHeld[key] = name;
    try {
      if (name === null) { window.localStorage.removeItem(key); }
      else { window.localStorage.setItem(key, name); }
    } catch (e) { /* kept for this page only */ }
  }
  // What `name` opens in `editor`: its box, or its section's New color… panel.
  function openable(editor, name) {
    if (name.indexOf(NEW_COLOR_OPEN) === 0) {
      return editor.querySelector(':scope > [data-newc="' + CSS.escape(name.slice(NEW_COLOR_OPEN.length)) + '"]');
    }
    return editor.querySelector(':scope > .box[data-card="' + CSS.escape(name) + '"]');
  }
  // `id` the tab's root (`params` by default): the name opened in its editor, else null.
  function openedName(id) {
    var root = el(id || "params");
    var key = root ? openedKey(root) : null;
    return key === null ? null : readOpened(key);
  }
  function applyOpened(root) {
    var key = openedKey(root);
    var editor = root.querySelector(":scope > .editing");
    if (key === null || !editor) { return; }
    var name = readOpened(key);
    var shown = name === null ? null : openable(editor, name);
    var line = name === null ? null : root.querySelector(':scope > .summary .line[data-open="' + CSS.escape(name) + '"]');
    if (name !== null && (!shown || !line)) {
      writeOpened(key, null);
      name = null;
      shown = null;
    }
    // The words find's hiding says are said after, by `sayFindHides`.
    Array.prototype.forEach.call(editor.children, function (child) {
      var hide = child.classList.contains("placeholder") ? shown !== null : child !== shown;
      if (child.hidden !== hide) { child.hidden = hide; }
    });
    Array.prototype.forEach.call(root.querySelectorAll(":scope > .summary .line[data-open]"), function (one) {
      var on = one.getAttribute("data-open") === name ? "true" : "false";
      if (one.getAttribute("aria-pressed") !== on) { one.setAttribute("aria-pressed", on); }
    });
    sayFindHides(root);
  }
  // **Where the find box hides the setting opened** (the ledger's ruling for the summary and
  // editor build's Task 3), the editor says so -- "the opened setting is hidden by find · clear
  // find to see it" -- in place of going blank; the box stays hidden, as find leaves it.
  function sayFindHides(root) {
    var editor = root.querySelector(":scope > .editing");
    var note = editor ? editor.querySelector(":scope > .findhid") : null;
    if (!note) { return; }
    var shown = Array.prototype.filter.call(editor.children, function (child) {
      return !child.hidden && child !== note && !child.classList.contains("placeholder");
    })[0];
    var hide = !(shown && shown.classList.contains("nofind"));
    if (note.hidden !== hide) { note.hidden = hide; }
  }
  function openSetting(name) {
    var root = null;
    CARDS.forEach(function (id) {
      var found = document.querySelector(id + ' > .summary .line[data-open="' + CSS.escape(name) + '"]');
      if (found && !root) { root = found.closest(CARDS.join(", ")); }
    });
    if (!root) { return; }
    var key = openedKey(root);
    var editor = root.querySelector(":scope > .editing");
    if (key === null || !editor || !openable(editor, name)) { return; }
    writeOpened(key, name);
    applyOpened(root);
    // A section's New color… panel opens unfolded, and is kept so across frames (`newColors`).
    var panel = name.indexOf(NEW_COLOR_OPEN) === 0 ? openable(editor, name) : null;
    if (panel && !panel.open) {
      panel.open = true;
      newColorRead(panel);
    }
  }
  // **The find box, on both settings tabs** (the console interface design's goal 5; the ledger's
  // find ruling for the rework's Task 8): a box is found by its code name, its plain name, a
  // group's settings' code names and plain names, or the name of a section it stands in -- a
  // parent's name finds its subsections' boxes too; each summary line takes its box's mark, the
  // lines found left as they are and the rest dimmed (the summary and editor design's goal 8), a
  // New color… line found by its words or its section's name.
  function findIn(root) {
    var box = root.closest("#params") ? el("pfind") : root.closest("#training-params") ? el("tfind") : null;
    return box ? box.value.trim().toLowerCase() : "";
  }
  function findText(card) {
    var said = [card.getAttribute("data-card") || ""];
    Array.prototype.forEach.call(card.querySelectorAll(
        ":scope > .head .lbl, :scope > .head .code, :scope > details.more .gmore > .gn"), function (node) {
      said.push(node.textContent);
    });
    return said.join(" ").toLowerCase();
  }
  function markFind(root) {
    var find = findIn(root);
    var found = 0;
    Array.prototype.forEach.call(root.querySelectorAll(":scope > .summary .line[data-open]"), function (line) {
      var name = line.getAttribute("data-open");
      var section = line.closest(".ssec");
      var where = section ? (section.getAttribute("data-section") || "").toLowerCase() : "";
      var card = name.indexOf(NEW_COLOR_OPEN) === 0 ? null :
        root.querySelector(':scope > .editing > .box[data-card="' + CSS.escape(name) + '"]');
      var said = card ? findText(card) : line.textContent.toLowerCase();
      var unfound = find !== "" && said.indexOf(find) === -1 && where.indexOf(find) === -1;
      line.classList.toggle("nofind", unfound);
      // Found: highlighted while a find stands (the summary and editor design's goal 8).
      line.classList.toggle("found", find !== "" && !unfound);
      if (find !== "" && !unfound) { found += 1; }
      if (card) { card.classList.toggle("nofind", unfound); }
    });
    // Nothing found says so (the plan's Review Focus 4: "no setting matches").
    var none = el(root.id === "training-params" ? "tfind-none" : "pfind-none");
    if (none) { none.hidden = find === "" || found > 0; }
    sayFindHides(root);
    return find;
  }
  function applyFind() {
    CARDS.forEach(function (id) { if (document.querySelector(id)) { markFind(document.querySelector(id)); } });
  }
  // **Enter in a find box opens the first line found** (the summary and editor design's goal 8),
  // in the summary's order; with nothing found, nothing (the plan's Review Focus 4).
  function openFound(id) {
    var root = el(id === "tfind" ? "training-params" : "params");
    if (!root || findIn(root) === "") { return; }
    var first = root.querySelector(":scope > .summary .line.found[data-open]");
    if (first) { openSetting(first.getAttribute("data-open")); }
  }
  ["pfind", "tfind"].forEach(function (id) {
    if (!el(id)) { return; }
    el(id).addEventListener("input", applyFind);
    el(id).addEventListener("keydown", function (e) {
      if (e.key === "Enter") { e.preventDefault(); applyFind(); openFound(id); }
    });
  });
  applyFind();
  // **A box's *more* a person opened** (the console interface design's goal 1: "everything else
  // opens inside the box on a click"), by setting, kept open across the frames that replace the
  // boxes until it is closed. The click is on its summary, before it toggles.
  var mores = {};
  function keepMore(e) {
    var summary = e.target.closest(inCards(".box > details.more > summary"));
    if (!summary) { return; }
    var name = summary.closest(".box").getAttribute("data-card");
    if (summary.parentNode.open) { delete mores[name]; } else { mores[name] = true; }
  }
  // **What a box shows that is the page's own**, put back after a frame replaces it: its *more*
  // open, the color set a person chose to see the hues of, its New color panel as left.
  function restoreBox(box) {
    var name = box.getAttribute("data-card");
    var more = box.querySelector(":scope > details.more");
    if (more && mores[name]) { more.open = true; }
    Array.prototype.forEach.call(box.querySelectorAll("select[data-colorset]"), function (select) {
      var named = colorSets[select.getAttribute("data-colorset")];
      if (named !== undefined) { showHues(select, named); }
    });
  }
  function newColorKey(input) {
    if (input.hasAttribute("data-newc-num")) {
      return input.closest("[data-newc-fields]").getAttribute("data-newc-fields") + "/" +
        input.getAttribute("data-newc-num");
    }
    return input.hasAttribute("data-newc-name") ? "name" : "set";
  }
  function newColorRead(panel) {
    var kept = newColors[panel.getAttribute("data-newc")] || {};
    var state = { open: panel.open, method: panel.querySelector("[data-newc-method]").value,
                  into: panel.querySelector("[data-newc-into]").value, fields: {},
                  out: kept.out || null };
    Array.prototype.forEach.call(panel.querySelectorAll("input"), function (input) {
      state.fields[newColorKey(input)] = input.value;
    });
    newColors[panel.getAttribute("data-newc")] = state;
  }
  function newColorShow(panel) {
    var method = panel.querySelector("[data-newc-method]").value;
    var into = panel.querySelector("[data-newc-into]").value;
    var fresh = panel.querySelector("[data-newc-set]");
    Array.prototype.forEach.call(panel.querySelectorAll("[data-newc-fields]"), function (group) {
      group.hidden = group.getAttribute("data-newc-fields") !== method;
    });
    Array.prototype.forEach.call(panel.querySelectorAll("[data-newset-only]"), function (label) {
      label.hidden = into !== "";
    });
    fresh.hidden = into !== "";
    panel.querySelector("[data-newc-path]").textContent = into !== "" ? into : fresh.value.trim();
  }
  function newColorOut(panel, answer) {
    var out = panel.querySelector(".newc-out");
    out.textContent = "";
    if (!answer) { return; }
    if (typeof answer.srgb === "string" && /^#[0-9a-f]{6}$/.test(answer.srgb)) {
      var chip = document.createElement("span");
      chip.className = "chip";
      chip.style.background = answer.srgb;
      out.appendChild(chip);
      out.appendChild(document.createTextNode(" "));
    }
    out.appendChild(document.createTextNode(String(answer.said || "")));
  }
  function restoreNewColors() {
    Object.keys(newColors).forEach(function (setting) {
      var panel = document.querySelector('#params [data-newc="' + CSS.escape(setting) + '"]');
      if (!panel) { return; }
      var state = newColors[setting];
      panel.open = state.open;
      panel.querySelector("[data-newc-method]").value = state.method;
      choose(panel.querySelector("[data-newc-into]"), state.into);
      Array.prototype.forEach.call(panel.querySelectorAll("input"), function (input) {
        var typed = state.fields[newColorKey(input)];
        if (typed !== undefined) { input.value = typed; }
      });
      newColorOut(panel, state.out);
      newColorShow(panel);
    });
  }
  // The New color panel's command as typed, or null with the page told what is missing: the set
  // chosen, or a new one by its name; the method's fields, a new set's frame only for a new set, a
  // blank contrast left to the set's mean radius.
  function newColorCommand(panel) {
    var method = panel.querySelector("[data-newc-method]").value;
    var into = panel.querySelector("[data-newc-into]").value;
    var fresh = into === "";
    var colorset = fresh ? panel.querySelector("[data-newc-set]").value.trim() : into;
    var numbers = {};
    var bad = null;
    var group = panel.querySelector('[data-newc-fields="' + CSS.escape(method) + '"]');
    Array.prototype.forEach.call(group.querySelectorAll("input[data-newc-num]"), function (input) {
      var field = input.getAttribute("data-newc-num");
      var raw = input.value.trim();
      if (input.closest("[data-newset-only]") && !fresh) { return; }
      if (field === "contrast" && raw === "") { return; }
      var value = Number(raw);
      if (raw === "" || !isFinite(value)) { bad = bad || field; }
      numbers[field] = value;
    });
    if (bad !== null) { tell("not sent: the new color's " + bad + " needs a number", "crit"); return null; }
    if (!colorset) { tell("not sent: a new set needs its name", "crit"); return null; }
    return { colorset: colorset, new_set: fresh, method: method, numbers: numbers,
             name: panel.querySelector("[data-newc-name]").value.trim() };
  }
  function previewColor(button) {
    var panel = button.closest("[data-newc]");
    var asked = newColorCommand(panel);
    if (!asked) { return; }
    var query = new URLSearchParams();
    query.set("set", asked.colorset);
    query.set("method", asked.method);
    Object.keys(asked.numbers).forEach(function (field) {
      query.set(field, String(asked.numbers[field]));
    });
    fetch("/color-preview?" + query.toString(), { cache: "no-store" }).then(function (response) {
      return response.json();
    }).then(function (answer) {
      var shown = document.querySelector('#params [data-newc="' + CSS.escape(panel.getAttribute("data-newc")) + '"]') || panel;
      newColorRead(shown);
      newColors[shown.getAttribute("data-newc")].out = { said: answer.said, srgb: answer.srgb };
      newColorOut(shown, newColors[shown.getAttribute("data-newc")].out);
    }).catch(function () {
      newColorOut(panel, { said: "not previewed: this page could not reach wlx serve", srgb: null });
    });
  }
  function showHues(select, named) {
    select.value = named;
    var card = select.closest(".clr");
    Array.prototype.forEach.call(card.querySelectorAll("[data-hues]"), function (group) {
      group.hidden = group.getAttribute("data-hues") !== named;
    });
  }
  // A pointer down inside the boxes or the moments pane holds their frames until it is up (fix
  // round 2: a frame landing between the mouse going down and up replaced the button under it,
  // so the press was lost -- in WebKit, which never focuses a clicked button, and in Chromium),
  // so nothing moves under the pointer, a neighbor growing above it included. A release the page
  // never sees ends the hold after ten seconds.
  function pressing() {
    return pressedAt !== null && performance.now() - pressedAt < PRESS_MS;
  }
  function boxes() { return document.querySelectorAll(inCards(".box")); }
  function nameOf(box) { return box.getAttribute("data-card"); }
  // **A box's controls as they stand**, keyed by what each sends: the side open (`side`), each
  // value field shown (`p:` and the setting it sets), the shape chosen and its fields (`shape`,
  // `f:`), the hue pressed (`hue`), each setting's choice pressed among its segments (`c:` and the
  // setting), and a draw's live numbers in its *more* (`n:`). A number is
  // compared as a number -- `0.50` is `0.5`, as `1.250` is `1.25` -- a list as its numbers, and
  // what is no number as typed.
  function numberOf(raw) {
    var value = Number(raw);
    return raw === "" ? "" : isFinite(value) ? "#" + value : raw;
  }
  function listOf(raw) {
    return raw.split(/[\\s,]+/).filter(Boolean).map(numberOf).join(",");
  }
  function shownIn(box, node) {
    for (var at = node; at && at !== box; at = at.parentElement) {
      if (at.hidden) { return false; }
    }
    return true;
  }
  function paneOf(box, side) {
    return box.querySelector(':scope > .editor [data-side="' + CSS.escape(side) + '"]');
  }
  function shapeOf(pane) {
    var select = pane ? pane.querySelector("select[data-shape]") : null;
    return select ? select.value : "scaled";
  }
  function formFields(box, side) {
    var pane = paneOf(box, side);
    var group = pane ? pane.querySelector('[data-fields="' + CSS.escape(shapeOf(pane)) + '"]') : null;
    return group ? group.querySelectorAll("input[data-form]") : [];
  }
  // **A pool's grid's ticks as the pool's number** (the console interface rework's Task 7): each
  // ticked pair's bit (`data-bit`, the rig's `PoolMember.bit`) summed, the value a `set` of the
  // pool sends and the record keeps.
  function poolSum(grid) {
    var sum = 0;
    Array.prototype.forEach.call(grid.querySelectorAll("input.tick[data-bit]"), function (tick) {
      if (tick.checked) { sum += Number(tick.getAttribute("data-bit")); }
    });
    return sum;
  }
  // **What a percent field holds, as the fraction it sends** (`data-percent`; the console
  // interface design's call: "the setting, the command and the record keep the fraction"): the
  // typed decimal's point moved two places (`80` is read as `80e-2`, so 0.8, never
  // 0.8000000000000002), else divided by 100.
  function fromPercent(raw) {
    return /^[-+]?(\\d+\\.?\\d*|\\.\\d+)$/.test(raw) ? Number(raw + "e-2") : Number(raw) / 100;
  }
  // **One choice pressed among a setting's segments** (`web._choice_segments`), `words` its words,
  // or none pressed for `null`; nothing sent.
  function pressChoice(group, words) {
    Array.prototype.forEach.call(group.querySelectorAll(".ch[data-choice]"), function (segment) {
      var on = words !== null && segment.getAttribute("data-choice") === words;
      segment.classList.toggle("on", on);
      segment.setAttribute("aria-pressed", on ? "true" : "false");
    });
  }
  function stateOf(box) {
    var state = {};
    var side = box.querySelector(":scope > .editor [data-switch].on");
    if (side) { state.side = side.getAttribute("data-switch"); }
    Array.prototype.forEach.call(box.querySelectorAll(":scope > .editor input[data-param]"), function (input) {
      if (!shownIn(box, input)) { return; }
      var raw = input.value.trim();
      state["p:" + input.getAttribute("data-param")] =
        input.getAttribute("data-kind") === "word" ? raw : numberOf(raw);
    });
    // A pool's ticks, keyed as the setting's value they send (`draftOf`: one `set`).
    Array.prototype.forEach.call(box.querySelectorAll(":scope > .editor [data-pool]"), function (grid) {
      if (!shownIn(box, grid)) { return; }
      state["p:" + grid.getAttribute("data-pool")] = "#" + poolSum(grid);
    });
    if (state.side && state.side !== "fixed") {
      state.shape = shapeOf(paneOf(box, state.side));
      Array.prototype.forEach.call(formFields(box, state.side), function (input) {
        var field = input.getAttribute("data-form");
        var raw = input.value.trim();
        state["f:" + field] = field === "values" || field === "weights" ? listOf(raw) : numberOf(raw);
      });
    }
    var hue = box.querySelector(":scope > .editor .hue.on[data-color]");
    if (hue) { state.hue = hue.getAttribute("data-colorset") + "/" + hue.getAttribute("data-color"); }
    // A setting's choices as segments, keyed by the setting (`c:`), the words of the one pressed.
    Array.prototype.forEach.call(box.querySelectorAll(":scope > .editor [data-choices]"), function (group) {
      var on = group.querySelector(".ch.on[data-choice]");
      if (on) { state["c:" + group.getAttribute("data-choices")] = on.getAttribute("data-choice"); }
    });
    Array.prototype.forEach.call(box.querySelectorAll(".detail > .rng input[data-number]"), function (input) {
      state["n:" + input.getAttribute("data-number")] = numberOf(input.value.trim());
    });
    return state;
  }
  function same(a, b) {
    var keys = Object.keys(a);
    return keys.length === Object.keys(b).length &&
      keys.every(function (key) { return a[key] === b[key]; });
  }
  // **A box's draft** (the controls review's §2, rules 1, 2 and 4): what its Apply would send, as
  // changes -- each `{kind, name, ...}` by its own kind's fields, `set`, `range`, `form`, `color`
  // or `choice` (`link.APPLY_KINDS`) -- and why it cannot be sent (`error`, the page's own checks: a
  // number that is not one, a fraction for a whole setting); `null` where the box holds what it
  // is headed to, the value in force or what this page sent and the rig has not yet applied ("a
  // draft equal to what is in force is no draft"). A range sends the numbers that differ from
  // those in force, which the rig lays over them.
  function draftOf(box) {
    var name = nameOf(box);
    var now = stateOf(box);
    var given = served[name] ? stateOf(served[name]) : now;
    var base = out[name] ? out[name].state : given;
    if (same(now, base)) { return null; }
    var changes = [];
    var error = "";
    function wrong(why) { if (!error) { error = why; } }
    Object.keys(now).forEach(function (key) {
      if (key.indexOf("p:") !== 0 || now[key] === base[key]) { return; }
      var setting = key.slice(2);
      var field = null;
      Array.prototype.forEach.call(box.querySelectorAll(":scope > .editor input[data-param]"), function (input) {
        if (input.getAttribute("data-param") === setting && shownIn(box, input)) { field = input; }
      });
      if (!field) {
        // A pool's grid: its ticks are one `set` of the pool's number, a pair added or taken
        // away alike; none ticked is no pool, which the rig refuses (`task.Pool`).
        var grid = box.querySelector(':scope > .editor [data-pool="' + CSS.escape(setting) + '"]');
        var sum = grid ? poolSum(grid) : 0;
        if (!sum) { wrong("tick at least one pair"); return; }
        changes.push({ kind: "set", name: setting, value: sum });
        return;
      }
      var raw = field.value.trim();
      if (field.getAttribute("data-kind") === "word") {
        if (raw === "") { wrong(setting + " needs a word"); }
        changes.push({ kind: "set", name: setting, value: raw });
        return;
      }
      var value = Number(raw);
      if (raw === "" || !isFinite(value)) { wrong(setting + " needs a number"); return; }
      if (field.hasAttribute("data-whole") && Math.floor(value) !== value) { wrong(WHOLE); return; }
      if (field.hasAttribute("data-percent")) { value = fromPercent(raw); }
      changes.push({ kind: "set", name: setting, value: value });
    });
    var drawn = now.side !== undefined && now.side !== "fixed";
    var reshaped = drawn && (now.side !== base.side || now.shape !== base.shape ||
      Object.keys(now).some(function (key) { return key.indexOf("f:") === 0 && now[key] !== base[key]; }));
    if (reshaped) {
      var command = { kind: "form", name: name, shape: now.shape };
      var numbers = {};
      Array.prototype.forEach.call(formFields(box, now.side), function (input) {
        var field = input.getAttribute("data-form");
        var raw = input.value.trim();
        if (field === "values" || field === "weights") {
          var items = raw.split(/[\\s,]+/).filter(Boolean).map(Number);
          if (!items.length || items.some(function (item) { return !isFinite(item); })) {
            wrong(name + "'s " + field + " needs a number");
          }
          command[field] = items;
          return;
        }
        var value = Number(raw);
        if (raw === "" || !isFinite(value)) { wrong(name + "'s " + field + " needs a number"); }
        numbers[field] = value;
      });
      if (Object.keys(numbers).length) { command.numbers = numbers; }
      changes.push(command);
    }
    if (now.hue !== undefined && now.hue !== base.hue) {
      var hue = box.querySelector(":scope > .editor .hue.on[data-color]");
      changes.push({ kind: "color", name: name, colorset: hue.getAttribute("data-colorset"),
                     color: hue.getAttribute("data-color") });
    }
    // A choice pressed among a setting's segments: a `choice` by its words (`link.SetChoice`).
    Object.keys(now).forEach(function (key) {
      if (key.indexOf("c:") !== 0 || now[key] === base[key]) { return; }
      changes.push({ kind: "choice", name: key.slice(2), choice: now[key] });
    });
    var ranged = {};
    var moved = Object.keys(now).some(function (key) {
      return key.indexOf("n:") === 0 && now[key] !== base[key];
    });
    if (moved) {
      Object.keys(now).forEach(function (key) {
        if (key.indexOf("n:") !== 0 || now[key] === given[key]) { return; }
        var number = key.slice(2);
        var raw = box.querySelector('.detail > .rng input[data-number="' + CSS.escape(number) + '"]').value.trim();
        var value = Number(raw);
        if (raw === "" || !isFinite(value)) { wrong(name + "'s " + number + " needs a number"); return; }
        ranged[number] = value;
      });
      if (Object.keys(ranged).length) { changes.push({ kind: "range", name: name, numbers: ranged }); }
    }
    var named = {};
    changes.forEach(function (change) {
      if (named[change.name]) { wrong("a value over " + change.name + "'s draw and its range go one at a time"); }
      named[change.name] = true;
    });
    if (changes.length && fractions[name]) { wrong(WHOLE); }
    if (!changes.length && !error) { return null; }
    return { changes: changes, error: error };
  }
  // What a frame says of a box that the page tells news by: the change waiting, the refusal, the
  // change in force.
  function newsOf(box) {
    return [box.classList.contains("staged") ? "staged" : "", box.getAttribute("data-staged-cid"),
            box.getAttribute("data-refusal"), box.getAttribute("data-applied")].join("|");
  }
  function noted(box, said) {
    notes[nameOf(box)] = { said: said, news: newsOf(box), state: stateOf(box) };
  }
  // A button the page holds off for a reason of its own (no draft, a draft it cannot send, an
  // act out), or lets go to what this page may do: `data-held`, which the sign-in leaves alone.
  function hold(button, off) {
    if (!button) { return; }
    if (off) {
      button.disabled = true;
      button.setAttribute("data-held", "");
      return;
    }
    button.removeAttribute("data-held");
    button.disabled = signinPage ? !(signedIn() && confirmed) : !canWrite;
  }
  // **A box's one status line**, where the page has its own word to say (the plan's "Words on
  // the page"): *sending…* while its act is out; *cannot send · why* for a draft its checks
  // refuse; a line kept until the box's news changes (a send not delivered, a withdrawal's
  // answer); *refused* for the draft the rig refused, by its own reason or, for an act refused
  // whole, as applied together; *not sent* for a draft, saying a reward size is sent alone and
  // never withdrawn, and who changed the box under it (the plan's Review Focus 4); *waiting for
  // the next trial · you* for a change this page sent. `null`: the rig's own line.
  function withdrawalOf(name) {
    return Object.keys(withdrawing).some(function (cid) {
      return withdrawing[cid].names.indexOf(name) !== -1;
    });
  }
  function lineOf(box, draft) {
    var name = nameOf(box);
    var sent = out[name];
    if (sent && sent.phase === "sending") { return SENDING; }
    // A withdrawal out is said until the rig answers it, whatever the frames meanwhile show: a
    // change waiting no more may have applied (the whole-build review's I1).
    if (withdrawalOf(name)) { return WITHDRAWING; }
    if (draft && draft.error) { return CANNOT + draft.error; }
    var note = notes[name];
    if (note && note.news === newsOf(box) && same(note.state, stateOf(box))) { return note.said; }
    delete notes[name];
    var refused = refusedAt[name];
    if (refused && draft && same(refused.state, stateOf(box))) {
      return box.getAttribute("data-refusal-cid") === refused.cid ? null : TOGETHER;
    }
    var waiting = box.getAttribute("data-staged-cid");
    var under = box.getAttribute("data-under");
    if (draft) {
      var said = NOT_SENT;
      if (box.classList.contains("ceiling")) { said += " · " + ALONE; }
      if (box.classList.contains("staged")) {
        if (waiting && mine[waiting]) {
          var to = box.querySelector(".head .to");
          said += " · " + (to ? to.textContent.replace(/^→\\s*/, "") : "a change") + " is waiting";
        } else if (under) { said += " · " + under; }
      } else if (under && (box.getAttribute("data-applied") || "") !== (since[name] || "")) {
        said += " · " + under;
      }
      return said;
    }
    if (box.classList.contains("staged") && waiting && mine[waiting]) { return WAITING_YOU; }
    return null;
  }
  // **A box brought up to date with the page's own state**: its draft judged, its marks
  // (`draft`, `sending`, `cannot`), its status line, and Apply and Discard live only where they
  // would do something. The rig's line and state come from `served`; a refusal a later accepted
  // change has cleared says what the line would say without it.
  function refresh(box) {
    var name = nameOf(box);
    var fresh = served[name];
    var draft = draftOf(box);
    if (draft) {
      if (!drafts[name]) { since[name] = box.getAttribute("data-applied") || ""; }
      drafts[name] = draft;
    } else {
      delete drafts[name];
      delete since[name];
    }
    var sending = Boolean(out[name] && out[name].phase === "sending");
    // The rig's state from the frame, the find box's mark kept (a box brought up to date between
    // two `settle`s -- an act sent, a step -- stays found or not as the find box left it).
    if (fresh) {
      var unfound = box.classList.contains("nofind");
      box.className = fresh.className;
      if (unfound) { box.classList.add("nofind"); }
    }
    var said = lineOf(box, draft);
    var say = box.querySelector(":scope > .status > .say");
    var given = fresh ? fresh.querySelector(":scope > .status > .say") : null;
    if (say && given) {
      var copy = given.cloneNode(true);
      say.replaceWith(copy);
      say = copy;
    }
    var seen = refusals[name];
    if (said === null && seen && seen.cleared && box.classList.contains("refused") && say &&
        say.hasAttribute("data-rest")) {
      box.classList.remove("refused");
      if (say.getAttribute("data-rest-state")) { box.classList.add(say.getAttribute("data-rest-state")); }
      said = say.getAttribute("data-rest");
    }
    if (said === TOGETHER) { box.classList.add("refused"); }
    if (said !== null && say) {
      say.textContent = said;
      say.title = WHOLE_OF[said] || said;
    }
    box.classList.toggle("draft", Boolean(draft) && !sending);
    box.classList.toggle("sending", sending);
    box.classList.toggle("cannot", Boolean(draft && draft.error) && !sending);
    hold(box.querySelector("[data-apply]"), !draft || Boolean(draft.error) || sending);
    hold(box.querySelector("[data-discard]"), sending ? !answeredLong(out[name]) : !draft);
    restOf(box);
    mirrorOne(name);
    markLine(name);
  }
  // **A special trials group's remainder, from its fields** (`web._rest`; the pop-out revision's
  // Amendments, item 4): the shares its span names, as typed, each one counted as the draw counts
  // it -- a number above 0, anything else none -- so a draft says what it leaves normal before it
  // is applied; with no draft the fields hold the values in force, and it says what the rig drew.
  function restOf(box) {
    var rest = box.querySelector(":scope > .editor > .gr[data-shares]");
    if (!rest) { return; }
    var total = 0;
    rest.getAttribute("data-shares").split(" ").forEach(function (name) {
      var field = box.querySelector(':scope > .editor input[data-param="' + CSS.escape(name) + '"]');
      var typed = field ? field.value.trim() : "";
      var value = typed === "" ? NaN : Number(typed);
      if (isFinite(value) && value > 0) { total += value; }
    });
    var words = rest.getAttribute("data-words");
    rest.textContent = total < 100 ? String(Math.round((100 - total) * 1e9) / 1e9) + " " + words
      : "none " + words + (total > 100 ? ": " + rest.getAttribute("data-over") : "");
  }
  // **What only the page knows, on a summary line** (the summary and editor design's goal 3 and
  // its call "when states combine"; the plan's Global Constraints): the rig's line (`_line`) is
  // kept as the frame drew it (`wlxRig`, taken again after every `patchLine`), and where the page
  // knows more -- a draft, a draft that cannot send, an act sending or a withdrawal out, an act the
  // rig never confirmed, a refusal of an act applied together, a refusal a later change cleared --
  // the line says it: at most two marks after the name, in precedence (`LINE_MARKS`), then ◆ where
  // the value is drawn each trial; the value "in force → draft" (`draftText`); and in its title
  // every state present in words, the rig's among them.
  var EDITED = "edited";
  var LINE_MARKS = ["!", "●", "…", "?", "◷", "⚠"];
  var DRAW_ENDS = { non_aging: ["shortest", "longest"], uniform: ["low", "high"], normal: ["low", "high"] };
  function linesOf(name) {
    return document.querySelectorAll(inCards('.summary .line[data-open="' + CSS.escape(name) + '"]'));
  }
  function rigOf(line) {
    var mk = line.querySelector(":scope > .mk");
    var lv = line.querySelector(":scope > .lv");
    var state = ["waiting", "refused", "warned"].filter(function (kind) {
      return line.classList.contains(kind);
    })[0] || "";
    return { title: line.getAttribute("title") || "", mk: mk ? mk.textContent : "",
             lv: lv ? lv.textContent : "", state: state, said: line.getAttribute("data-said") || "" };
  }
  // A typed number as its line says it: after it what the line writes after a number (`data-unit`,
  // `web._line_unit`: "%", "°", " s"), else the unit beside the box's field.
  function unitOf(box, field) {
    var line = linesOf(nameOf(box))[0];
    if (line && line.hasAttribute("data-unit")) { return line.getAttribute("data-unit"); }
    var holder = field ? field.closest(".fu, label") : null;
    var unit = holder ? holder.querySelector(".unit") : null;
    return unit && unit.textContent ? " " + unit.textContent : "";
  }
  function endsOf(box, fields, kind, ends) {
    var typed = ends.map(function (end) {
      var found = Array.prototype.filter.call(fields, function (input) {
        return input.getAttribute(kind) === end;
      })[0];
      return found ? found.value.trim() : "";
    });
    if (typed[0] === "" || typed[1] === "") { return EDITED; }
    return typed[0] + "–" + typed[1] + unitOf(box, null);
  }
  // **A box's draft as its summary line says it** (the plan's Global Constraints), read from the
  // box's own fields, never formatted again: one field, as typed with its unit -- a percent's `%`,
  // a whole number as typed -- or as typed alone where the draft cannot send; a draw, its two ends
  // as typed, "0.5–1.25 s"; a pool, "N of 12" from its ticks; a choice pressed among its segments,
  // its words; a color, a group, a shape or a switch alone, or more than one kind of change,
  // "edited". What differs from the frame's box (`served`),
  // so an act still sending says what it sent; "" where nothing does.
  function draftText(box) {
    var name = nameOf(box);
    var now = stateOf(box);
    var given = served[name] ? stateOf(served[name]) : now;
    var moved = Object.keys(now).concat(Object.keys(given)).filter(function (key, at, all) {
      return all.indexOf(key) === at && now[key] !== given[key];
    });
    if (!moved.length) { return ""; }
    if (box.classList.contains("group")) { return EDITED; }
    var values = moved.filter(function (key) {
      return key.indexOf("p:") === 0 && Object.prototype.hasOwnProperty.call(now, key);
    });
    var drawn = now.side !== undefined && now.side !== "fixed";
    var formed = drawn && moved.some(function (key) {
      return key === "side" || key === "shape" || key.indexOf("f:") === 0;
    });
    var ranged = moved.some(function (key) { return key.indexOf("n:") === 0; });
    var chosen = moved.filter(function (key) {
      return key.indexOf("c:") === 0 && Object.prototype.hasOwnProperty.call(now, key);
    });
    var kinds = values.length + (formed ? 1 : 0) + (ranged ? 1 : 0) + (moved.indexOf("hue") !== -1 ? 1 : 0) +
      chosen.length;
    if (kinds !== 1) { return EDITED; }
    // A choice pressed among its segments: as its segment says it, "Ring" for a look's long
    // words (`web._choice_label`), as the line says the choice in force; its words whole where
    // no segment says them.
    if (chosen.length) {
      var words = now[chosen[0]];
      var said = Array.prototype.filter.call(box.querySelectorAll(":scope > .editor [data-choice]"),
        function (segment) { return segment.getAttribute("data-choice") === words; })[0];
      return said ? said.textContent : words;
    }
    if (values.length) {
      var setting = values[0].slice(2);
      var field = null;
      Array.prototype.forEach.call(box.querySelectorAll(":scope > .editor input[data-param]"), function (input) {
        if (input.getAttribute("data-param") === setting && shownIn(box, input)) { field = input; }
      });
      if (field) {
        var raw = field.value.trim();
        var cannot = drafts[name] && drafts[name].error;
        return field.getAttribute("data-kind") === "word" || cannot ? raw : raw + unitOf(box, field);
      }
      var grid = box.querySelector(':scope > .editor [data-pool="' + CSS.escape(setting) + '"]');
      if (!grid) { return EDITED; }
      return grid.querySelectorAll("input.tick[data-bit]:checked").length + " of " +
        grid.querySelectorAll("input.tick[data-bit]").length;
    }
    if (formed && DRAW_ENDS[now.shape]) {
      return endsOf(box, formFields(box, now.side), "data-form", DRAW_ENDS[now.shape]);
    }
    if (formed && now.shape === "scaled") {
      var factor = formFields(box, now.side)[0];
      var unit = factor ? factor.parentElement.querySelector(":scope > .unit") : null;
      return factor && factor.value.trim() ? factor.value.trim() + (unit ? " " + unit.textContent : "") : EDITED;
    }
    if (ranged) {
      var numbers = box.querySelectorAll(".detail > .rng input[data-number]");
      var named = Array.prototype.map.call(numbers, function (input) { return input.getAttribute("data-number"); });
      var ends = named.indexOf("shortest") !== -1 ? ["shortest", "longest"] : ["low", "high"];
      if (named.indexOf(ends[0]) !== -1 && named.indexOf(ends[1]) !== -1) {
        return endsOf(box, numbers, "data-number", ends);
      }
    }
    return EDITED;
  }
  // "in force → draft": a number's unit said once, after the draft ("1.00 → 1.50 s"), as the rig's
  // line says what waits (`web._waits`); anything else as it is, then the arrow.
  function arrowed(line, typed) {
    var now = line.querySelector(":scope > .lv").getAttribute("data-now") || "";
    var unit = line.getAttribute("data-unit");
    var number = /^-?\\d+(\\.\\d+)?$/;
    if (unit !== null && now.slice(now.length - unit.length) === unit &&
        typed.slice(typed.length - unit.length) === unit &&
        number.test(now.slice(0, now.length - unit.length)) &&
        number.test(typed.slice(0, typed.length - unit.length))) {
      return now.slice(0, now.length - unit.length) + " → " + typed;
    }
    return now + " → " + typed;
  }
  // Each state of a box present, `{mark, said, page}` in precedence: `page` where it is the page's
  // own, which the rig's line does not say.
  function lineStates(box, rig) {
    var name = nameOf(box);
    var draft = drafts[name] || null;
    var sending = Boolean(out[name] && out[name].phase === "sending");
    var say = box.querySelector(":scope > .status > .say");
    var text = say ? say.textContent : "";
    var given = served[name] ? served[name].querySelector(":scope > .status > .say") : null;
    var cleared = rig.state === "refused" && !box.classList.contains("refused");
    var rest = cleared && given ? given.getAttribute("data-rest-state") || "" : "";
    var restSaid = cleared && given ? given.getAttribute("data-rest") || "" : "";
    var states = [];
    function add(mark, said, page) { states.push({ mark: mark, said: said, page: page }); }
    if (draft && draft.error && !sending) { add("!", CANNOT + draft.error, true); }
    if (text === TOGETHER) { add("!", TOGETHER, true); }
    else if (rig.state === "refused" && !cleared) { add("!", rig.said, false); }
    if (draft && !sending) { add("●", text.indexOf(NOT_SENT) === 0 ? (say.title || text) : NOT_SENT, true); }
    if (sending) { add("…", SENDING, true); }
    else if (withdrawalOf(name)) { add("…", WITHDRAWING, true); }
    if (text.indexOf(NO_WORD) !== -1) { add("?", text, true); }
    if (rig.state === "waiting") { add("◷", rig.said, false); }
    if (rig.state === "warned") { add("⚠", rig.said, false); }
    if (cleared) { add(rest === "warned" ? "⚠" : "", rest === "" ? "" : restSaid, true); }
    else if (!rig.state && rig.said) { add("", rig.said, false); }
    return states;
  }
  function markLine(name) {
    var box = cardOf(name);
    Array.prototype.forEach.call(linesOf(name), function (line) {
      if (!line.wlxRig) { line.wlxRig = rigOf(line); }
      var rig = line.wlxRig;
      var states = box ? lineStates(box, rig) : [];
      var own = states.some(function (one) { return one.page; });
      var marks = [];
      states.forEach(function (one) {
        if (one.mark && marks.indexOf(one.mark) === -1 && marks.length < 2) { marks.push(one.mark); }
      });
      marks.sort(function (a, b) { return LINE_MARKS.indexOf(a) - LINE_MARKS.indexOf(b); });
      var shown = rig.lv;
      var typed = box && (drafts[name] || (out[name] && out[name].phase === "sending")) ? draftText(box) : "";
      if (typed) { shown = arrowed(line, typed); }
      var title = rig.title;
      if (own || shown !== rig.lv) {
        var saids = states.map(function (one) { return one.said; }).filter(Boolean);
        var at = rig.title.indexOf(" · " + rig.lv);
        if (at === -1) { title = [rig.title].concat(saids).join(" · "); }
        else {
          var tail = rig.title.slice(at + 3 + rig.lv.length);
          if (rig.said && tail.indexOf(" · " + rig.said) === 0) { tail = tail.slice(3 + rig.said.length); }
          title = [rig.title.slice(0, at), shown].concat(saids).join(" · ") + tail;
        }
      }
      var mark = own ? marks.join("") + (line.classList.contains("drawn") ? "◆" : "") : rig.mk;
      var mk = line.querySelector(":scope > .mk");
      var lv = line.querySelector(":scope > .lv");
      if (mk && mk.textContent !== mark) { mk.textContent = mark; }
      if (lv && lv.textContent !== shown) { lv.textContent = shown; }
      if (line.getAttribute("title") !== title) { line.setAttribute("title", title); }
      var has = function (mark) { return states.some(function (one) { return one.mark === mark; }); };
      line.classList.toggle("refused", has("!"));
      line.classList.toggle("draft", has("●"));
      line.classList.toggle("sending", has("…"));
      line.classList.toggle("unconfirmed", has("?"));
      line.classList.toggle("warned", has("⚠"));
    });
    mirrorLine(name);
  }
  // **A box that keeps its editor**: one with a draft, its act out, or a field or select focused
  // in it (the controls review's §3, rule 2); a button focused is not one, Chromium focusing
  // the button it pressed (*hand back*).
  function dirty(box) {
    var name = nameOf(box);
    var focused = document.activeElement;
    var copy = focused ? pinOf(focused) : null;
    return Boolean(drafts[name] || out[name] ||
      (focused && (box.contains(focused) || (copy && copy.getAttribute("data-pin") === name)) &&
       focused.matches && focused.matches("input, select")));
  }
  // A refusal as first seen on a box, and whether a change of the setting has been accepted since
  // (the design's goal 4: "a refusal is cleared by a later accepted change of that setting"): a
  // change waiting that was not when it was first seen, or the change in force moving on.
  function track(box) {
    var name = nameOf(box);
    var fresh = served[name] || box;
    var key = fresh.getAttribute("data-refusal") || "";
    var staged = fresh.classList.contains("staged") ? (fresh.getAttribute("data-staged-cid") || "staged") : "";
    var applied = fresh.getAttribute("data-applied") || "";
    var seen = refusals[name];
    if (!key) { delete refusals[name]; return; }
    if (!seen || seen.key !== key) {
      refusals[name] = { key: key, staged: staged, applied: applied, cleared: false };
      return;
    }
    if (!seen.cleared && ((staged && staged !== seen.staged) || (!seen.staged && applied !== seen.applied))) {
      seen.cleared = true;
    }
  }
  // **A kept editor's controls a person has not touched follow the frame**: each that still holds
  // what the last frame drew moves to what this one draws, its node kept -- its value set, never
  // replaced -- so a box kept only for a field focused, or kept for one edit, never shows a value
  // the rig no longer holds as a draft of its own; one a person changed stays.
  function controlsOf(node) {
    var found = {};
    Array.prototype.forEach.call(node.querySelectorAll(
        ":scope > .editor input[data-param], :scope > .editor input[data-form], " +
        ":scope > .editor select[data-shape], :scope > .editor input.tick[data-bit], " +
        ":scope > details.more > .detail > .rng input[data-number]"), function (control) {
      var key = control.hasAttribute("data-param") ? "p:" + control.getAttribute("data-param")
        : control.hasAttribute("data-bit") ? "t:" + control.getAttribute("data-bit")
        : control.hasAttribute("data-number") ? "n:" + control.getAttribute("data-number")
        : control.hasAttribute("data-form") ? "f:" + control.closest("[data-fields]").getAttribute("data-fields") +
          "/" + control.getAttribute("data-form")
        : "shape";
      found[key] = control;
    });
    return found;
  }
  function valueOf(control) {
    if (control.type === "checkbox") { return control.checked ? "1" : ""; }
    var raw = control.value.trim();
    return control.tagName === "SELECT" || control.getAttribute("data-kind") === "word" ? raw
      : control.getAttribute("data-form") === "values" || control.getAttribute("data-form") === "weights"
      ? listOf(raw) : numberOf(raw);
  }
  function follow(box, before, given) {
    var have = controlsOf(box);
    var was = controlsOf(before);
    var now = controlsOf(given);
    Object.keys(have).forEach(function (key) {
      var control = have[key];
      if (!was[key] || !now[key] || valueOf(control) !== valueOf(was[key]) ||
          valueOf(now[key]) === valueOf(was[key])) { return; }
      if (control.type === "checkbox") { control.checked = now[key].checked; return; }
      control.value = now[key].value;
      if (key === "shape") { showShape(box, control.value); }
    });
    var sideOf = function (node) {
      var on = node.querySelector(":scope > .editor [data-switch].on");
      return on ? on.getAttribute("data-switch") : null;
    };
    if (sideOf(box) !== null && sideOf(box) === sideOf(before) && sideOf(given) !== sideOf(before)) {
      showSide(box, sideOf(given));
    }
    var hueOf = function (node) {
      var on = node.querySelector(":scope > .editor .hue.on[data-color]");
      return on ? on.getAttribute("data-colorset") + "/" + on.getAttribute("data-color") : "";
    };
    if (hueOf(box) === hueOf(before) && hueOf(given) !== hueOf(before)) {
      Array.prototype.forEach.call(box.querySelectorAll(":scope > .editor .hue[data-color]"), function (hue) {
        var on = hue.getAttribute("data-colorset") + "/" + hue.getAttribute("data-color") === hueOf(given);
        hue.classList.toggle("on", on);
        hue.setAttribute("aria-pressed", on ? "true" : "false");
      });
    }
    // Each setting's segments, as its hue's swatches: one a person has not pressed follows the frame.
    var choiceOf = function (node, setting) {
      var on = node.querySelector(':scope > .editor [data-choices="' + CSS.escape(setting) + '"] .ch.on[data-choice]');
      return on ? on.getAttribute("data-choice") : null;
    };
    Array.prototype.forEach.call(box.querySelectorAll(":scope > .editor [data-choices]"), function (group) {
      var setting = group.getAttribute("data-choices");
      var then = choiceOf(before, setting);
      var told = choiceOf(given, setting);
      if (choiceOf(box, setting) !== then || told === then) { return; }
      pressChoice(group, told);
    });
  }
  // **A dirty box patched by zone** (the controls review's §3): its head and its status line's
  // news from the frame, its *withdraw* as the frame has it, its *more* -- but a draft's or a
  // sent act's live range numbers, and not while a field in it is focused -- and its marks; its
  // editor's nodes, and Apply and Discard, never replaced.
  function patchDirty(box, given, before) {
    // Not while its act is out: what it sent is judged against the editor as sent.
    if (before && !out[nameOf(box)]) { follow(box, before, given); }
    box.querySelector(":scope > .head").replaceWith(given.querySelector(":scope > .head"));
    var acts = box.querySelector(":scope > .status > .acts");
    var gone = acts.querySelector(":scope > .wd");
    var come = given.querySelector(":scope > .status > .acts > .wd");
    if (gone && come) { gone.replaceWith(come); }
    else if (gone) { gone.remove(); }
    else if (come) { acts.insertBefore(come, acts.firstChild); }
    var detail = box.querySelector(":scope > details.more > .detail");
    var news = given.querySelector(":scope > details.more > .detail");
    var focused = document.activeElement;
    if (detail && news && !(focused && detail.contains(focused))) {
      var range = detail.querySelector(":scope > .rng");
      var fresh = news.querySelector(":scope > .rng");
      var now = stateOf(box);
      var was = before ? stateOf(before) : now;
      var ranged = Boolean(out[nameOf(box)]) || Object.keys(now).some(function (key) {
        return key.indexOf("n:") === 0 && now[key] !== was[key];
      });
      if (range && fresh && ranged) { fresh.replaceWith(range); }
      detail.replaceWith(news);
    }
    ["data-staged-cid", "data-refusal", "data-refusal-cid", "data-applied", "data-under"].forEach(function (attr) {
      if (given.hasAttribute(attr)) { box.setAttribute(attr, given.getAttribute(attr)); }
      else { box.removeAttribute(attr); }
    });
    box.className = given.className;
  }
  // A tab's layout: its summary's sections and their lines, then its editor's boxes and panels,
  // in order; null for a tab that lays out none. `root` is the tab's root or a frame's fragment,
  // whose own children are read (`:scope` names no element in a fragment).
  function skeletonOf(root) {
    var own = function (name) {
      return Array.prototype.filter.call(root.children, function (child) {
        return child.classList.contains(name);
      })[0] || null;
    };
    var summary = own("summary");
    var editor = own("editing");
    if (!summary || !editor) { return null; }
    return Array.prototype.map.call(summary.querySelectorAll(".ssec"), function (section) {
      return section.getAttribute("data-section") + ":" + Array.prototype.map.call(
        section.querySelectorAll(":scope > .line"), function (line) {
          return line.getAttribute("data-open");
        }).join(",");
    }).join("|") + "||" + Array.prototype.map.call(editor.children, function (child) {
      return child.getAttribute("data-card") || child.getAttribute("data-newc") || child.className;
    }).join(",");
  }
  // **A summary line brought up to the frame's in place** (the summary and editor design's
  // anti-goal: "the page jumping under the pointer"), its node kept, so a focused line keeps its
  // focus: its classes, title and value, and each mark; `aria-pressed` is the page's own
  // (`applyOpened`).
  function patchLine(line, given) {
    Array.prototype.slice.call(line.attributes).forEach(function (attr) {
      if (attr.name !== "aria-pressed" && !given.hasAttribute(attr.name)) { line.removeAttribute(attr.name); }
    });
    Array.prototype.forEach.call(given.attributes, function (attr) {
      if (line.getAttribute(attr.name) !== attr.value) { line.setAttribute(attr.name, attr.value); }
    });
    Array.prototype.forEach.call(given.children, function (part, at) {
      var have = line.children[at];
      if (!have) { line.appendChild(part.cloneNode(true)); return; }
      if (have.textContent !== part.textContent) { have.textContent = part.textContent; }
      Array.prototype.forEach.call(part.attributes, function (attr) {
        if (have.getAttribute(attr.name) !== attr.value) { have.setAttribute(attr.name, attr.value); }
      });
    });
    // As the frame drew it again: what the page adds is said anew from it (`markLine`).
    line.wlxRig = null;
  }
  // Every draft dropped (the console interface design's call: "dropped at the run's end"), and a
  // field focused in a box left, so no box keeps an editor of a run that is over.
  function dropDrafts() {
    drafts = {};
    out = {};
    refusedAt = {};
    notes = {};
    since = {};
    withdrawing = {};
    var focused = document.activeElement;
    if (focused && focused.closest && focused.closest(CARDS.join(", "))) { focused.blur(); }
    // Every box is put back as the frame draws it, an unchanged one too: its editor may hold a
    // draft just dropped.
    Array.prototype.forEach.call(boxes(), function (box) { kept[nameOf(box)] = true; });
  }
  // **A frame's boxes, patched box by box** (the console interface design's goal 10; the controls
  // review's §3): held whole while a pointer is down (`pressing`); else each box the frame
  // changed is replaced whole where it is clean, and patched by zone where it is dirty
  // (`patchDirty`), its editor's nodes kept, so a press or a field being typed in is never under a
  // node a frame replaced. The sections' headers are rewritten in place. Where the frame lays the
  // boxes out anew (a setting come or gone, a section moved), the tab is rebuilt around the dirty
  // boxes' own nodes, the field that had focus focused again.
  function patchCards(id, html) {
    var root = el(id);
    if (!root) { return; }
    if (pressing()) { heldCards[id] = html; return; }
    delete heldCards[id];
    var made = document.createElement("template");
    made.innerHTML = html;
    var next = made.content;
    var secs = next.querySelector(".summary");
    // Only a tab that lays out boxes names the run: the Training tab of a task with no Training
    // section names none.
    if (secs) {
      var run = secs.getAttribute("data-run") || "";
      if (runKey !== null && run !== runKey) { dropDrafts(); }
      runKey = run;
    }
    var given = {};
    var before = {};
    Array.prototype.forEach.call(next.querySelectorAll(".box"), function (box) {
      var name = nameOf(box);
      given[name] = box;
      before[name] = served[name] || null;
      served[name] = box.cloneNode(true);
    });
    var held = {};
    Array.prototype.forEach.call(root.querySelectorAll(".box"), function (box) {
      var name = nameOf(box);
      if (!given[name]) {
        delete drafts[name];
        delete out[name];
        delete kept[name];
      } else if (dirty(box)) { held[name] = true; }
    });
    var layout = skeletonOf(root);
    if (layout !== null && layout === skeletonOf(next)) {
      var live = root.querySelector(":scope > .summary");
      ["data-task", "data-run"].forEach(function (attr) {
        live.setAttribute(attr, secs.getAttribute(attr) || "");
      });
      // Its columns' width, from its longest line (`web._line_width`).
      if ((live.getAttribute("style") || "") !== (secs.getAttribute("style") || "")) {
        if (secs.hasAttribute("style")) { live.setAttribute("style", secs.getAttribute("style")); }
        else { live.removeAttribute("style"); }
      }
      Array.prototype.forEach.call(live.querySelectorAll(".ssec"), function (section) {
        var other = secs.querySelector('.ssec[data-section="' + CSS.escape(section.getAttribute("data-section")) + '"]');
        var header = headOf(section);
        var fresh = headOf(other);
        // The rig's counts; what is not sent is said after them again by `settle` (`countDrafts`).
        if (header.textContent !== fresh.textContent) { header.textContent = fresh.textContent; }
        if (header.title !== fresh.title) { header.title = fresh.title; }
        Array.prototype.forEach.call(section.querySelectorAll(":scope > .line"), function (line, at) {
          patchLine(line, other.querySelectorAll(":scope > .line")[at]);
        });
      });
      var oldRefused = root.querySelector(":scope > .wdrs");
      var newRefused = next.querySelector(".wdrs");
      if (oldRefused && newRefused) { oldRefused.replaceWith(newRefused); }
      else if (newRefused) { root.appendChild(newRefused); }
      else if (oldRefused) { oldRefused.remove(); }
      Array.prototype.forEach.call(root.querySelectorAll(".box"), function (box) {
        var name = nameOf(box);
        if (held[name]) {
          patchDirty(box, given[name], before[name]);
          kept[name] = true;
        } else if (kept[name] || !before[name] || !before[name].isEqualNode(given[name])) {
          // Shown or hidden in the editor as the box it replaces (`applyOpened`).
          given[name].hidden = box.hidden;
          box.replaceWith(given[name]);
          delete kept[name];
          restoreBox(given[name]);
        }
      });
    } else {
      var focused = document.activeElement;
      var mark = null;
      if (focused && root.contains(focused) && focused.matches("input")) {
        try { mark = [focused.selectionStart, focused.selectionEnd]; } catch (e) { mark = null; }
      }
      Array.prototype.forEach.call(root.querySelectorAll(".box"), function (box) {
        var name = nameOf(box);
        if (held[name]) {
          patchDirty(box, given[name], before[name]);
          given[name].replaceWith(box);
          kept[name] = true;
        } else { delete kept[name]; }
      });
      root.replaceChildren(next);
      Array.prototype.forEach.call(root.querySelectorAll(".box"), function (box) {
        if (!kept[nameOf(box)]) { restoreBox(box); }
      });
      if (focused && root.contains(focused) && document.activeElement !== focused) {
        focused.focus();
        if (mark) { try { focused.setSelectionRange(mark[0], mark[1]); } catch (e) { /* not a text field */ } }
      }
    }
    Array.prototype.forEach.call(root.querySelectorAll(".box"), track);
    judge();
    // The opened setting shown again (`applyOpened`), in `settle`.
    settle();
  }
  // **The rig's answers to this page's acts, read off the frame**: an act whose id a box's
  // refusal carries is refused whole, every box of it (the controls' ruling: a frame keeps only
  // the last refusals, so not every box of a large act may carry its own); one a box's waiting
  // change carries is waiting; one waiting no more, or answered *sent* with the boxes now holding
  // what it sent, has applied or been replaced. A withdrawal the rig refused (`.wdr`, by the act's
  // id) is said on its boxes; one the rig says it did (`.wdn`, `Telemetry.withdrawals`) has taken
  // the act back, and its boxes go back to the value in force -- never one only waiting no more,
  // which a change that applied is too (the whole-build review's I1). **An act or a withdrawal
  // answered *sent* that `ANSWER_FRAMES` frames pass without the rig's word** says so on its
  // boxes, and they are let go: a box never stays *sending…* or *withdrawing…* (its I2).
  function judge() {
    var staged = {};
    var refused = {};
    var declined = {};
    var done = {};
    Array.prototype.forEach.call(boxes(), function (box) {
      var cid = box.getAttribute("data-staged-cid");
      if (cid) { staged[cid] = true; }
      var no = box.getAttribute("data-refusal-cid");
      if (no) { refused[no] = true; }
    });
    Array.prototype.forEach.call(document.querySelectorAll(inCards(".wdrs .wdr")), function (row) {
      var cid = row.getAttribute("data-cid");
      declined[cid] = { count: (declined[cid] ? declined[cid].count : 0) + 1, said: row.textContent };
    });
    Array.prototype.forEach.call(document.querySelectorAll(inCards(".wdrs .wdn")), function (row) {
      done[row.getAttribute("data-cid")] = true;
    });
    Object.keys(withdrawing).forEach(function (cid) {
      var asked = withdrawing[cid];
      var no = declined[cid];
      if (no && no.count > asked.seen) {
        asked.names.forEach(function (name) {
          var box = cardOf(name);
          if (box) { noted(box, "not withdrawn · " + no.said); }
        });
        delete withdrawing[cid];
      } else if (!done[cid]) {
        if (asked.answered && framesSeen - asked.at >= ANSWER_FRAMES) {
          delete withdrawing[cid];
          asked.names.forEach(function (name) {
            var sent = out[name];
            var box = cardOf(name);
            if (sent && sent.cid === cid) {
              delete out[name];
              if (box && same(stateOf(box), sent.state) && served[name]) { putBack(box); }
            }
            if (served[name]) {
              notes[name] = { said: "withdraw " + NO_WORD, news: newsOf(served[name]),
                              state: stateOf(served[name]) };
            }
          });
        }
      } else {
        asked.names.forEach(function (name) {
          var sent = out[name];
          var box = cardOf(name);
          if (sent && sent.cid === cid) {
            delete out[name];
            if (box && same(stateOf(box), sent.state) && served[name]) { putBack(box); }
          }
          if (served[name]) {
            notes[name] = { said: WITHDRAWN, news: newsOf(served[name]), state: stateOf(served[name]) };
          }
        });
        delete withdrawing[cid];
      }
    });
    Object.keys(out).forEach(function (name) {
      var sent = out[name];
      var box = cardOf(name);
      if (!box) { delete out[name]; return; }
      // An act whose withdrawal is out is judged by the withdrawal's answer, above: a frame that
      // comes before that answer, the act waiting no more, has not applied it (found under the
      // suite's load in the console interface rework's Task 7: the box then kept what it sent as
      // a draft, "not sent", where it was withdrawn).
      if (withdrawing[sent.cid] && !refused[sent.cid]) { return; }
      if (refused[sent.cid]) {
        refusedAt[name] = { cid: sent.cid, state: stateOf(box) };
        delete out[name];
      } else if (staged[sent.cid]) {
        sent.phase = "waiting";
      } else if (sent.phase === "waiting" ||
                 (sent.answered && served[name] && same(sent.state, stateOf(served[name])))) {
        delete out[name];
      } else if (sent.answered && framesSeen - sent.at >= ANSWER_FRAMES) {
        // Neither waiting, refused nor in force as sent: the edit is a draft again, said so.
        delete out[name];
        noted(box, NO_WORD);
      }
    });
  }
  // A box put back to the frame's, whole.
  function putBack(box) {
    var name = nameOf(box);
    var back = served[name].cloneNode(true);
    back.hidden = box.hidden;
    box.replaceWith(back);
    delete kept[name];
    restoreBox(back);
    return back;
  }
  // **Every box made current**: a kept box that is clean again replaced whole by the frame's
  // (no merge logic for the common case: the controls review's §3, rule 4), every box's state
  // and line refreshed, the sections, the sign-in's gray and the drafts bar after. Never while a
  // pointer is down.
  function settle() {
    if (!pressing()) {
      Array.prototype.forEach.call(boxes(), function (box) {
        var name = nameOf(box);
        // Its draft judged first: an act answered just now (refused, not delivered) leaves the
        // box's edit a draft again, which a box put back would lose.
        if (kept[name]) { refresh(box); }
        if (kept[name] && served[name] && !dirty(box)) {
          var fresh = served[name].cloneNode(true);
          fresh.hidden = box.hidden;
          box.replaceWith(fresh);
          delete kept[name];
          restoreBox(fresh);
        }
      });
    }
    CARDS.forEach(function (id) { if (document.querySelector(id)) { applyOpened(document.querySelector(id)); } });
    Array.prototype.forEach.call(boxes(), refresh);
    applyFind();
    restoreNewColors();
    applySignIn();
    showBar();
    mirrorPins();
  }
  // **The drafts bar** (the console interface design's goal 2): "N edits not sent: names ·
  // Discard all · Apply all", in the order the boxes stand. A reward size is sent alone, by its
  // own box's Apply, never in Apply all (the design's call; XC-527); Apply all is held off, saying
  // why, for a draft that cannot be sent, a setting changed in two boxes, or more than
  // `APPLY_ALL_LIMIT` changes.
  function gathered() {
    var every = [];
    var named = [];
    var alone = [];
    var changes = [];
    var why = "";
    Array.prototype.forEach.call(boxes(), function (box) {
      var name = nameOf(box);
      var draft = drafts[name];
      if (!draft || (out[name] && out[name].phase === "sending")) { return; }
      every.push(name);
      if (box.classList.contains("ceiling")) { alone.push(name); return; }
      named.push(name);
      if (draft.error && !why) { why = name + " cannot send: " + draft.error; }
      draft.changes.forEach(function (change) { changes.push(change); });
    });
    var seen = {};
    changes.forEach(function (change) {
      if (seen[change.name] && !why) { why = change.name + " is changed in two boxes: apply one first"; }
      seen[change.name] = true;
    });
    if (!why && changes.length > APPLY_ALL_LIMIT) {
      why = "Apply all sends at most " + APPLY_ALL_LIMIT + " changes at once: apply some boxes alone first";
    }
    return { every: every, named: named, alone: alone, changes: changes, why: why };
  }
  function showBar() {
    countDrafts();
    var bar = el("drafts");
    if (!bar) { return; }
    var all = gathered();
    bar.hidden = all.every.length === 0;
    body.classList.toggle("drafted", all.every.length > 0);
    if (!all.every.length) { return; }
    var said = all.every.length + (all.every.length === 1 ? " edit" : " edits") + " not sent: " +
      all.every.join(", ");
    if (all.alone.length) {
      said += " · " + all.alone.join(", ") + (all.alone.length === 1 ?
        " is sent alone, by its own Apply" : " are sent alone, each by its own Apply");
    }
    if (all.why) { said += " · " + all.why; }
    el("drafts-say").textContent = said;
    el("drafts-say").title = said;
    hold(el("drafts-apply"), !all.named.length || Boolean(all.why));
    hold(el("drafts-discard"), false);
  }
  function nextCid() {
    cidCount += 1;
    var cid = pageId + "-" + cidCount;
    mine[cid] = true;
    return cid;
  }
  // **One act** (the console interface design's goal 2): the changes of `names`' boxes sent as one
  // command under a fresh command id -- a box's one change as its own kind, several (a box's, or
  // Apply all's) as `apply_many`, judged and staged together or refused whole
  // (`Session._apply_many`). Each box says *sending…* until a frame answers the id; one the page
  // could not deliver gets its draft back, saying why.
  function sendAct(names, changes, together) {
    var cid = nextCid();
    var command;
    if (changes.length === 1 && !together) {
      command = {};
      Object.keys(changes[0]).forEach(function (key) { command[key] = changes[0][key]; });
      command.cid = cid;
    } else {
      command = { kind: "apply_many", cid: cid, changes: changes };
    }
    acts[cid] = names.slice();
    names.forEach(function (name) {
      var box = cardOf(name);
      out[name] = { cid: cid, state: stateOf(box), snapshot: box.cloneNode(true), phase: "sending",
                    answered: false };
      delete notes[name];
      delete refusedAt[name];
      refresh(box);
    });
    showBar();
    var answered = false;
    function failed(said) {
      names.forEach(function (name) {
        if (!out[name] || out[name].cid !== cid) { return; }
        delete out[name];
        var box = cardOf(name);
        if (box) { noted(box, NOT_SENT + " · " + said); }
      });
      settle();
    }
    post(command, function (answer) {
      answered = true;
      if (answer.status !== "sent") { failed(answer.said); return; }
      names.forEach(function (name) {
        if (out[name] && out[name].cid === cid) {
          out[name].answered = true;
          out[name].at = framesSeen;
        }
      });
      judge();
      settle();
    }, function () { if (!answered) { failed(el("sent").textContent); } });
  }
  // **Apply** (and Enter in a box's field): the box's draft as one act.
  // A group's box (the console interface rework's Task 7) is one act whatever it changed: one
  // `apply_many` under one command id, which its *withdraw* takes back whole.
  function applyBox(name) {
    var box = cardOf(name);
    if (!box || (out[name] && out[name].phase === "sending")) { return; }
    refresh(box);
    var draft = drafts[name];
    if (!draft || draft.error) { return; }
    sendAct([name], draft.changes, draft.changes.length > 1 || box.classList.contains("group"));
  }
  // **Apply all** (the console interface design's goal 2: "Apply all stages them together, on the
  // same trial"): every box's draft but a reward size's, one `apply_many`.
  function applyAll() {
    var all = gathered();
    if (!all.named.length || all.why) { showBar(); return; }
    sendAct(all.named, all.changes, true);
  }
  // The selector of a box's field, to focus it again in a box put back.
  function fieldOf(input) {
    if (input.hasAttribute("data-param")) {
      return 'input[data-param="' + CSS.escape(input.getAttribute("data-param")) + '"]';
    }
    if (input.hasAttribute("data-number")) {
      return 'input[data-number="' + CSS.escape(input.getAttribute("data-number")) + '"]';
    }
    if (input.hasAttribute("data-bit")) {
      return 'input.tick[data-bit="' + CSS.escape(input.getAttribute("data-bit")) + '"]';
    }
    var group = input.closest("[data-fields]");
    if (group && input.hasAttribute("data-form")) {
      return '[data-fields="' + CSS.escape(group.getAttribute("data-fields")) + '"] input[data-form="' +
        CSS.escape(input.getAttribute("data-form")) + '"]';
    }
    return null;
  }
  // **Discard** (and Esc): the box back to what it is headed to -- what this page sent and the rig
  // has not yet applied, else the value in force -- the field it was typed in focused again.
  // **An act answered *sent* and not yet answered by a frame** is let go by Discard and Esc too (the
  // whole-build review's I2: a box always has a way back), once a frame has come since without the
  // rig's word on it (`answeredLong`): the box back to the value in force, saying the rig has not
  // confirmed it -- a frame that then shows it waiting or in force says so.
  function answeredLong(sent) {
    // Not before (the fix wave's re-review, N1): Enter then Esc to leave the field, the design's
    // keys, comes before the rig's next frame, and must leave the change on its way.
    return Boolean(sent && sent.answered && framesSeen - sent.at >= 1);
  }
  function discard(name, field) {
    var box = cardOf(name);
    var sent = out[name];
    if (!box || (sent && sent.phase === "sending" && !answeredLong(sent))) { return; }
    var picked = field ? fieldOf(field) : null;
    if (sent && sent.phase === "sending") {
      delete out[name];
      if (served[name]) { box = putBack(box); }
      delete drafts[name];
      delete refusedAt[name];
      noted(box, NO_WORD);
      applySignIn();
      if (picked) {
        var again = box.querySelector(picked);
        if (again) { again.focus(); }
      }
      settle();
      return;
    }
    if (out[name]) {
      var sent = out[name].snapshot.cloneNode(true);
      box.querySelector(":scope > .editor").replaceWith(sent.querySelector(":scope > .editor"));
      var range = box.querySelector(".detail > .rng");
      var back = sent.querySelector(".detail > .rng");
      if (range && back) { range.replaceWith(back); }
    } else if (served[name]) {
      var fresh = served[name].cloneNode(true);
      fresh.hidden = box.hidden;
      box.replaceWith(fresh);
      delete kept[name];
      restoreBox(fresh);
      box = fresh;
    }
    delete drafts[name];
    delete refusedAt[name];
    delete notes[name];
    // The box put back comes grayed as served until the sign-in's script lets it go, and a
    // disabled field takes no focus.
    applySignIn();
    if (picked) {
      var again = box.querySelector(picked);
      if (again) { again.focus(); }
    }
    settle();
  }
  function discardAll() {
    gathered().every.forEach(function (name) { discard(name); });
  }
  // **Withdraw** (the console interface design's goal 3; the PI, 2026-11-19, "Yes, a withdraw
  // button"): the act a box's waiting change was sent in, by its command id, taken back whole --
  // its button said how many first. A double click is one withdrawal, as a clear's is.
  function withdraw(cid, detail) {
    if (!clearAllowed(detail, "withdraw/" + cid) || withdrawing[cid]) { return; }
    var names = Array.prototype.filter.call(boxes(), function (box) {
      return box.getAttribute("data-staged-cid") === cid;
    }).map(nameOf);
    var seen = document.querySelectorAll(inCards('.wdrs .wdr[data-cid="' + CSS.escape(cid) + '"]')).length;
    withdrawing[cid] = { names: names, answered: false, seen: seen, at: framesSeen };
    names.forEach(function (name) { noted(cardOf(name), WITHDRAWING); });
    settle();
    var answered = false;
    function failed(said) {
      if (!withdrawing[cid]) { return; }
      delete withdrawing[cid];
      names.forEach(function (name) {
        var box = cardOf(name);
        if (box) { noted(box, "not withdrawn · " + said); }
      });
      settle();
    }
    post({ kind: "withdraw", cid: cid }, function (answer) {
      answered = true;
      if (answer.status !== "sent") { failed(answer.said); return; }
      if (withdrawing[cid]) {
        withdrawing[cid].answered = true;
        withdrawing[cid].at = framesSeen;
      }
      judge();
      settle();
    }, function () { if (!answered) { failed(el("sent").textContent); } });
  }
  // **What is not sent, counted where a person looks** (the console interface rework's Task 8):
  // each section's header after the rig's counts ("Timing · 7 settings · 2 changed · 1 not sent", a
  // group's settings each counted once, as the rig's counts take them, a parent's taking in its
  // subsections'), and each settings tab's label while a box on it holds a draft.
  function unsent(box) {
    var draft = drafts[nameOf(box)];
    if (!draft) { return 0; }
    return box.classList.contains("group") ? Math.max(1, draft.changes.length) : 1;
  }
  function slotIn(holder, kind) {
    var slot = holder.querySelector(":scope > ." + kind);
    if (!slot) {
      slot = document.createElement("span");
      slot.className = kind;
      holder.appendChild(slot);
    }
    return slot;
  }
  function sayIn(slot, count) {
    var said = count ? " · " + count + " not sent" : "";
    if (slot.textContent !== said) { slot.textContent = said; }
  }
  // **A summary section's header**: its own `h4`, or, for a section of subsections alone, the one
  // it keeps with its first subsection (`web._sections`, `.skeep`).
  function headOf(section) {
    return section.querySelector(":scope > h4") || section.querySelector(":scope > .skeep > h4");
  }
  function countDrafts() {
    [["params", "t-task"], ["training-params", "t-training"]].forEach(function (pair) {
      var root = el(pair[0]);
      var tab = document.querySelector('label.tab[for="' + pair[1] + '"]');
      if (!root || !tab) { return; }
      Array.prototype.forEach.call(root.querySelectorAll(":scope > .summary .ssec"), function (section) {
        var header = headOf(section);
        var count = 0;
        Array.prototype.forEach.call(section.querySelectorAll(".line[data-open]"), function (line) {
          var box = root.querySelector(':scope > .editing > .box[data-card="' + CSS.escape(line.getAttribute("data-open")) + '"]');
          if (box) { count += unsent(box); }
        });
        if (header) { sayIn(slotIn(header, "ns"), count); }
      });
      var total = 0;
      Array.prototype.forEach.call(root.querySelectorAll(".box"), function (box) { total += unsent(box); });
      sayIn(slotIn(tab, "tns"), total);
    });
  }
  // **Pins** (the console interface design's goal 9; the PI, 2026-11-19: "Yes, you choose only"): a
  // box's *pin to Runtime*, in its *more*, puts its setting's summary line in Runtime's Pinned
  // strip (`#pinned`), kept per task in this browser's storage under `wlx.pins.<task>` -- the
  // names pinned, in the order pinned -- every access inside `try`, so a store that throws keeps
  // them for this page alone; nothing is pinned until a person pins it. **A click on a pinned line
  // opens it in Runtime's own editor below** (`#pinned-editing`; the summary and editor design's
  // goal 9: "a click opens the same editor on Runtime (one editor per tab, the setting's one draft
  // shared)"), kept as a tab's is, under `wlx.pinned-opened.<task>`. A pinned line is its tab's
  // line's mirror (`mirrorLine`: what the rig said and what the page adds, `markLine`), and the
  // editor's box **its original's mirror, never a second box** (the ledger's pin ruling: "one
  // draft per setting, never two diverging copies"): it carries `data-pin` where its original
  // carries `data-card`, outside the roots every box lookup reads (`CARDS`, `cardOf`), so a
  // setting keeps one box, one draft and one act. What a person does in a copy -- typing, a tick,
  // a segment, a swatch, −/+, Apply, Discard, Esc, Enter, *withdraw*, *hand back* -- is done to its
  // original (`pinOf`, `twinOf`), and the copy is brought up to it node by node (`morph`), its own
  // *more* left open or closed, so a press in it lands on a node no frame replaced.
  var PINS_KEY = "wlx.pins.";
  var PINNED_OPENED_KEY = "wlx.pinned-opened.";
  var pinsHeld = {};
  var TWINS = "input, select, textarea, button";
  function pinTask() {
    var summary = document.querySelector(inCards(".summary"));
    return summary ? summary.getAttribute("data-task") || "" : "";
  }
  function readPins(task) {
    if (!pinsHeld[task]) {
      var list = [];
      try {
        var raw = window.localStorage.getItem(PINS_KEY + task);
        var kept = raw ? JSON.parse(raw) : [];
        if (Array.isArray(kept)) {
          list = kept.filter(function (name) { return typeof name === "string"; });
        }
      } catch (e) { list = []; }
      pinsHeld[task] = list;
    }
    return pinsHeld[task].slice();
  }
  function writePins(task, list) {
    pinsHeld[task] = list.slice();
    try { window.localStorage.setItem(PINS_KEY + task, JSON.stringify(list)); } catch (e) { /* kept for this page only */ }
  }
  function togglePin(name) {
    var task = pinTask();
    var list = readPins(task);
    var at = list.indexOf(name);
    if (at === -1) { list.push(name); } else { list.splice(at, 1); }
    writePins(task, list);
    mirrorPins(true);
  }
  function pinOf(node) {
    return node && node.closest ? node.closest("#pinned-editing > .box[data-pin]") : null;
  }
  function pinnedLine(name) {
    var strip = el("pinned");
    return strip ? strip.querySelector(':scope > .line[data-open="' + CSS.escape(name) + '"]') : null;
  }
  function pinnedCopy(name) {
    var holder = el("pinned-editing");
    return holder ? holder.querySelector(':scope > .box[data-pin="' + CSS.escape(name) + '"]') : null;
  }
  // **A pinned line brought up to its tab's line** in place, its node kept (`patchLine`'s rule):
  // every attribute but whether it is opened, which is Runtime's (`applyPinnedOpened`), and its
  // tab's find marks, which are its tab's; and each part's text.
  function mirrorLine(name) {
    var line = pinnedLine(name);
    var from = line ? linesOf(name)[0] : null;
    if (!from) { return; }
    var own = function (attr) { return attr === "aria-pressed"; };
    Array.prototype.slice.call(line.attributes).forEach(function (attr) {
      if (!own(attr.name) && !from.hasAttribute(attr.name)) { line.removeAttribute(attr.name); }
    });
    Array.prototype.forEach.call(from.attributes, function (attr) {
      if (own(attr.name)) { return; }
      var value = attr.name !== "class" ? attr.value : attr.value.split(" ").filter(function (word) {
        return word !== "nofind" && word !== "found";
      }).join(" ");
      if (line.getAttribute(attr.name) !== value) { line.setAttribute(attr.name, value); }
    });
    Array.prototype.forEach.call(from.children, function (part, at) {
      var have = line.children[at];
      if (!have) { line.appendChild(part.cloneNode(true)); return; }
      if (have.textContent !== part.textContent) { have.textContent = part.textContent; }
    });
  }
  // **The pinned setting opened in Runtime's editor** (`#pinned-editing`), as a tab's is
  // (`applyOpened`): its copy shown, every other hidden, the placeholder said while none is; one
  // no longer pinned dropped.
  function applyPinnedOpened() {
    var holder = el("pinned-editing");
    if (!holder) { return; }
    var key = PINNED_OPENED_KEY + pinTask();
    var name = readOpened(key);
    var shown = name === null ? null : pinnedCopy(name);
    if (name !== null && (!shown || !pinnedLine(name))) {
      writeOpened(key, null);
      name = null;
      shown = null;
    }
    Array.prototype.forEach.call(holder.children, function (child) {
      var hide = child.classList.contains("placeholder") ? shown !== null : child !== shown;
      if (child.hidden !== hide) { child.hidden = hide; }
    });
    Array.prototype.forEach.call(el("pinned").children, function (one) {
      var on = one.getAttribute("data-open") === name ? "true" : "false";
      if (one.getAttribute("aria-pressed") !== on) { one.setAttribute("aria-pressed", on); }
    });
  }
  function openPinned(name) {
    if (!pinnedCopy(name)) { return; }
    writeOpened(PINNED_OPENED_KEY + pinTask(), name);
    applyPinnedOpened();
  }
  // A copy's control's twin in its original: the same place among the box's controls, which the
  // copy shares with it node for node (`morph`).
  function twinOf(copy, node) {
    var original = cardOf(copy.getAttribute("data-pin"));
    if (!original) { return null; }
    var mine = copy.querySelectorAll(TWINS);
    var theirs = original.querySelectorAll(TWINS);
    var at = Array.prototype.indexOf.call(mine, node);
    return at === -1 || mine.length !== theirs.length ? null : theirs[at];
  }
  function valuesOf(from, to) {
    var given = from.querySelectorAll("input, select, textarea");
    var have = to.querySelectorAll("input, select, textarea");
    if (given.length !== have.length) { return; }
    Array.prototype.forEach.call(given, function (control, at) {
      var twin = have[at];
      if (control.type === "checkbox" || control.type === "radio") {
        if (twin.checked !== control.checked) { twin.checked = control.checked; }
      } else if (twin.value !== control.value) { twin.value = control.value; }
    });
  }
  function copyOf(node) {
    var made = node.cloneNode(true);
    if (made.nodeType === 1) {
      made.removeAttribute("id");
      Array.prototype.forEach.call(made.querySelectorAll("[id]"), function (one) { one.removeAttribute("id"); });
      valuesOf(node, made);
    }
    return made;
  }
  // `to` brought up to `from` in place: each node kept where both have the same kind of node in the
  // same place, its attributes and text set, else its children made again; a copy's `data-card`
  // never taken, nor a `<details>`'s `open`, nor an id; and the values of the controls set last.
  function morph(from, to, top) {
    if (from.nodeType !== 1) {
      if (to.data !== from.data) { to.data = from.data; }
      return;
    }
    var keep = function (name) {
      return name === "id" || (name === "open" && to.tagName === "DETAILS") ||
        (top && (name === "data-card" || name === "data-pin" || name === "hidden"));
    };
    Array.prototype.slice.call(to.attributes).forEach(function (attr) {
      if (!keep(attr.name) && !from.hasAttribute(attr.name)) { to.removeAttribute(attr.name); }
    });
    Array.prototype.forEach.call(from.attributes, function (attr) {
      if (!keep(attr.name) && to.getAttribute(attr.name) !== attr.value) { to.setAttribute(attr.name, attr.value); }
    });
    var given = from.childNodes;
    var have = to.childNodes;
    var same = given.length === have.length && Array.prototype.every.call(given, function (node, at) {
      return node.nodeType === have[at].nodeType && node.nodeName === have[at].nodeName;
    });
    if (same) {
      Array.prototype.forEach.call(given, function (node, at) { morph(node, have[at], false); });
    } else {
      to.replaceChildren.apply(to, Array.prototype.map.call(given, copyOf));
    }
    if (top) {
      // Found or not by the find box of its own tab, the copy is always shown.
      to.classList.remove("nofind");
      valuesOf(from, to);
    }
  }
  // `now`: the copy's own press has been done to its original, so its copy is brought up at once,
  // not at the press's end (it is the node pressed that the hold keeps; `morph` keeps it).
  function mirrorOne(name, now) {
    if (pressing() && !now) { return; }
    var copy = pinnedCopy(name);
    var original = copy ? cardOf(name) : null;
    if (copy && original) { morph(original, copy, true); }
  }
  // `now`: a pin or an unpin, a deliberate press, shown at once.
  function mirrorPins(now) {
    var holder = el("pinned-editing");
    var strip = el("pinned");
    if (!holder || !strip) { return; }
    var names = readPins(pinTask()).filter(function (name) {
      return cardOf(name) !== null && linesOf(name).length > 0;
    });
    Array.prototype.forEach.call(document.querySelectorAll(inCards("[data-pin-toggle]")), function (button) {
      var on = names.indexOf(button.getAttribute("data-pin-toggle")) !== -1;
      var said = on ? "unpin from Runtime" : "pin to Runtime";
      if (button.textContent !== said) { button.textContent = said; }
      button.setAttribute("aria-pressed", on ? "true" : "false");
    });
    if (pressing() && !now) { return; }
    Array.prototype.slice.call(holder.querySelectorAll(":scope > .box[data-pin]")).forEach(function (copy) {
      if (names.indexOf(copy.getAttribute("data-pin")) === -1) { copy.remove(); }
    });
    Array.prototype.slice.call(strip.children).forEach(function (line) {
      if (names.indexOf(line.getAttribute("data-open")) === -1) { line.remove(); }
    });
    var widest = 0;
    names.forEach(function (name, at) {
      var original = cardOf(name);
      var from = linesOf(name)[0];
      var line = pinnedLine(name);
      if (!line) {
        line = from.cloneNode(true);
        line.removeAttribute("aria-pressed");
        line.classList.remove("nofind", "found");
      }
      mirrorLine(name);
      if (strip.children[at] !== line) { strip.insertBefore(line, strip.children[at] || null); }
      // As wide as the widest of the summaries its lines are from (`web._line_width`).
      var width = parseFloat(from.closest(".summary").style.columnWidth) || 0;
      if (width > widest) { widest = width; }
      var copy = pinnedCopy(name);
      if (!copy) {
        copy = copyOf(original);
        copy.removeAttribute("data-card");
        // Shown only while opened on Runtime, whether or not its original is opened on its tab
        // (`applyPinnedOpened`, below).
        copy.setAttribute("data-pin", name);
        copy.classList.remove("nofind");
        var more = copy.querySelector(":scope > details.more");
        if (more) { more.open = false; }
      } else { morph(original, copy, true); }
      // After the placeholder, in the order pinned.
      if (holder.children[at + 1] !== copy) { holder.insertBefore(copy, holder.children[at + 1] || null); }
    });
    var said = widest ? widest + "ch" : "";
    if (strip.style.columnWidth !== said) { strip.style.columnWidth = said; }
    applyPinnedOpened();
    el("pinned-pane").hidden = names.length === 0;
  }
  if (el("pinned")) {
    el("pinned").addEventListener("click", function (e) {
      var line = e.target.closest("#pinned > .line[data-open]");
      if (line) { openPinned(line.getAttribute("data-open")); }
    });
  }
  if (el("pinned-editing")) {
    el("pinned-editing").addEventListener("click", function (e) {
      var copy = pinOf(e.target);
      if (!copy) { return; }
      e.stopPropagation();
      // Its own *more* opens in place; a tick toggles itself and its `input` is passed on.
      if (e.target.closest("summary")) { return; }
      var button = e.target.closest("button");
      var twin = button && copy.contains(button) ? twinOf(copy, button) : null;
      // Only a button's press is passed here, the copy brought up after it. A click on anything
      // else -- a tick above all, which the browser toggles before this runs and before its
      // `input` -- is left to the `input` and `change` handlers below: mirrored now, the copy's
      // tick was set back to its box's old state before its `input` passed it on (the
      // whole-build review's I3).
      if (!twin) { return; }
      twin.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true, shiftKey: e.shiftKey,
                                                   detail: e.detail }));
      mirrorOne(copy.getAttribute("data-pin"), true);
      mirrorPins();
    }, true);
    ["input", "change"].forEach(function (type) {
      el("pinned-editing").addEventListener(type, function (e) {
        var copy = pinOf(e.target);
        if (!copy) { return; }
        e.stopPropagation();
        var twin = twinOf(copy, e.target);
        if (!twin) { return; }
        if (twin.type === "checkbox" || twin.type === "radio") { twin.checked = e.target.checked; }
        else { twin.value = e.target.value; }
        twin.dispatchEvent(new Event(type, { bubbles: true }));
        mirrorOne(copy.getAttribute("data-pin"), true);
        mirrorPins();
      }, true);
    });
    el("pinned-editing").addEventListener("keydown", function (e) {
      var copy = pinOf(e.target);
      if (!copy || !e.target.matches("input")) { return; }
      var twin = twinOf(copy, e.target);
      if (!twin) { return; }
      e.stopPropagation();
      fieldKeys(e, twin, e.target);
      mirrorOne(copy.getAttribute("data-pin"), true);
      mirrorPins();
    }, true);
  }
  // **The session's details behind *session*** (the console interface design's call: "the
  // session's details behind a *session* button"; the layout review's finding 4: "closed on the
  // settings tabs"): hidden on the Task parameters and Training tabs, shown on the others, where a
  // run is started and a session opened and ended; the button shows or hides them on the tab shown
  // until another tab is chosen.
  function sessionShown() { return getComputedStyle(el("session")).display !== "none"; }
  function showSession() {
    el("session-btn").setAttribute("aria-expanded", sessionShown() ? "true" : "false");
  }
  el("session-btn").addEventListener("click", function () {
    var shown = sessionShown();
    body.classList.toggle("session-open", !shown);
    body.classList.toggle("session-shut", shown);
    showSession();
  });
  Array.prototype.forEach.call(document.querySelectorAll('input[name="tab"]'), function (radio) {
    radio.addEventListener("change", function () {
      body.classList.remove("session-open", "session-shut");
      showSession();
    });
  });
  showSession();
  // **The demo's keys and limits, folded** (the console interface design's call: "fold to one line
  // ("keys and demo limits"), open on the first visit only"): open the first time this browser
  // shows a demo screen, remembered under `wlx.demo-keys-seen` the guarded way, every access
  // inside `try` -- a store that throws makes every visit a first, so the limits are never folded
  // away from someone who may not have read them -- and folded on each visit after, one click
  // opening it.
  var DEMO_SEEN_KEY = "wlx.demo-keys-seen";
  var demoFolded = false;
  function foldDemoKeys() {
    if (demoFolded || el("demo-pane").hidden) { return; }
    demoFolded = true;
    var seen = false;
    try { seen = window.localStorage.getItem(DEMO_SEEN_KEY) === "1"; } catch (e) { seen = false; }
    el("demo-fold").open = !seen;
    try { window.localStorage.setItem(DEMO_SEEN_KEY, "1"); } catch (e) { /* every visit is a first */ }
  }
  function swap(id, html) {
    if (id === "params" || id === "training-params") {
      patchCards(id, html);
      applySignIn();
      return;
    }
    if (id === "moments" && pressing()) { heldMoments = html; return; }
    // A frame shown is the newest: an older one held meanwhile must never be written back over
    // it by a later release (fix round 3 of the C3 plan's Task 18).
    if (id === "moments") { heldMoments = null; }
    var node = el(id);
    // The plan picker shows the plan its pre-flight was taken for, so a frame's choice stands.
    var chosen = node && node.tagName === "SELECT" && id !== "plan-sel" ? node.value : null;
    if (node) { node.innerHTML = html; }
    if (chosen !== null) { choose(node, chosen); }
    // Before the hooks: `holdReward` must see a button as the sign-in leaves it.
    applySignIn();
    if (id === "controls") { holdReward(); }
    if (id === "preflight") { restoreAcks(); restoreStarts(); }
    if (id === "rt-train") { restoreWidening(); }
    if (id === "plan-sel") { preselect(); }
    if (id === "end-actions") { settleOpen(); }
    if (id === "demo-tag") { demoFrame(); }
    if (id === "dn-demo" || id === "dn-subject") { restoreDemoBox(); }
  }
  // A press ended: the frames held under it shown, the newest of each; and every box made current.
  function release() {
    if (pressing()) { return; }
    Object.keys(heldCards).forEach(function (id) {
      var html = heldCards[id];
      delete heldCards[id];
      patchCards(id, html);
    });
    if (heldMoments !== null) {
      el("moments").innerHTML = heldMoments;
      heldMoments = null;
    }
    settle();
  }
  // The boxes as the page was served: each as `served`, its refusal tracked, the run noted.
  function startBoxes() {
    Array.prototype.forEach.call(boxes(), function (box) {
      served[nameOf(box)] = box.cloneNode(true);
      track(box);
    });
    var summary = document.querySelector(inCards(".summary"));
    runKey = summary ? summary.getAttribute("data-run") : null;
    settle();
  }
  function choose(select, value) {
    // A frame re-renders a select's options; the option a person chose stays chosen
    // while it is still offered (the b3a-2 plan, decision 11).
    Array.prototype.forEach.call(select.options, function (option) {
      if (option.value === value) { select.value = value; }
    });
  }
  function settleOpen() {
    // The b3a-2 final review, I1: once the page shows the session it sent open -- the
    // Summary's *end session* names it -- the New session dialog forgets what was typed
    // for it, so the next session's starts empty and with no animal chosen. A refused or
    // unanswered open keeps it, for a retry.
    if (pendingOpen === null) { return; }
    var shown = el("end-actions").querySelector('[data-cmd="end"][data-session]');
    if (!shown || shown.getAttribute("data-session") !== pendingOpen) { return; }
    el("dn-left").value = "";
    el("dn-id").value = "";
    el("dn-given").value = "";
    el("dn-subject").value = "";
    el("dn-deployment").value = "";
    el("dn-kind").value = "";
    if (el("dn-accept")) { el("dn-accept").checked = false; }
    demoBoxed = false;
    demoFilled = { left: "", id: "" };
    restoreDemoBox();
    el("dn-msg").textContent = "";
    pendingOpen = null;
  }
  function restoreStarts() {
    var stage = el("start-block");
    if (stage && picked.block !== undefined) { choose(stage, picked.block); }
    Array.prototype.forEach.call(document.querySelectorAll("select[data-start-setting]"),
      function (select) {
        var value = picked["level:" + select.getAttribute("data-start-setting")];
        if (value !== undefined) { choose(select, value); }
      });
    Array.prototype.forEach.call(document.querySelectorAll("input[data-pairing]"), function (box) {
      var value = picked["pairing:" + box.getAttribute("data-pairing")];
      if (value !== undefined) { box.checked = value; }
    });
    showStage();
  }
  // Each staircase's level is shown for the stage picked only: the others start where they would.
  function showStage() {
    var stage = el("start-block");
    var name = stage ? stage.value : null;
    Array.prototype.forEach.call(document.querySelectorAll("#run-start [data-stage]"),
      function (row) { row.hidden = name !== null && row.getAttribute("data-stage") !== name; });
  }
  // The start's block and values from the run's start: the stage picked, or none for the first;
  // the picked stage's staircase level and the pool, each only where a person changed it from
  // where the run would start.
  function runStart() {
    var stage = el("start-block");
    var values = {};
    Array.prototype.forEach.call(document.querySelectorAll("select[data-start-setting]"),
      function (select) {
        var row = select.closest("[data-stage]");
        if (row && row.hidden) { return; }
        if (select.value !== select.getAttribute("data-default")) {
          values[select.getAttribute("data-start-setting")] = Number(select.value);
        }
      });
    var pool = document.querySelector("#run-start [data-pool-row]");
    if (pool) {
      var sum = 0;
      Array.prototype.forEach.call(pool.querySelectorAll("input[data-pairing]"), function (box) {
        if (box.checked) { sum += Number(box.getAttribute("data-pairing")); }
      });
      if (String(sum) !== pool.getAttribute("data-default")) {
        values[pool.getAttribute("data-pool-row")] = sum;
      }
    }
    return { block: stage && stage.selectedIndex > 0 ? stage.value : null, values: values };
  }
  function restoreWidening() {
    Array.prototype.forEach.call(el("rt-train").querySelectorAll("input[data-widen]"), function (box) {
      var value = widened[box.getAttribute("data-suggestion") + ":" + box.getAttribute("data-widen")];
      if (value !== undefined) { box.checked = value; }
    });
  }
  function restoreAcks() {
    Array.prototype.forEach.call(document.querySelectorAll("input[data-ack]"), function (box) {
      box.checked = acked[box.getAttribute("data-ack")] === true;
    });
  }
  // Demo mode (§4.3-§4.6; its plan's Task 9): the demo screen in place of the replica while the
  // frame says demo, the pointer as the demo's eye, the number keys and B. Housekeeping, rendered
  // by Python (`web.GAZE_EVERY_MS`, `demoscreen`'s one definition): a still pointer is reported this
  // often, a moving one at most once an animation frame, one report in flight at a time.
  var GAZE_EVERY_MS = Number(body.getAttribute("data-gaze-every-ms")) || 100;
  var canGaze = body.getAttribute("data-can-gaze") === "1";
  var demo = {
    on: false,         // the frame says demo
    session: "",       // the demo session the frame is; "" for a demo service's idle frame
    steerable: false,  // a demo session between runs or in one
    full: false,
    wantFull: window.location.hash === "#demo",
    svg: null,         // the latest drawing, whichever session it is of
    keys: null,
    steer: ""
  };
  var gaze = {
    id: random(16), seq: 0, inFlight: false, timer: null, framed: false, moved: false,
    lastAt: -Infinity, engaged: false, hush: false, epoch: 0,
    x: null, y: null, inside: false,
    b: false, button: false, held: 0, presses: [0, 0, 0, 0, 0, 0, 0, 0, 0]
  };
  // What a page says while the demo takes no reports (`wlx serve`'s 504 and 503): no rig connected
  // to the gaze endpoint, or the gaze thread busy, which is no fault (Task 8's carried (a); since
  // the whole-build review's M1 a rig between runs or paused keeps the newest report, refusing
  // none).
  var DEMO_WAITING = "the demo is not reading the pointer now; this page keeps its eye for the next run";
  var DEMO_STEERING = "steering: this page's pointer is the demo's eye";
  function demoFrame() {
    var tag = el("demo-tag").querySelector("[data-demo]");
    demo.on = Boolean(tag);
    demo.session = tag ? tag.getAttribute("data-session") : "";
    demo.steerable = Boolean(tag && tag.hasAttribute("data-steerable"));
    el("replica-pane").hidden = demo.on;
    el("demo-pane").hidden = !demo.on;
    foldDemoKeys();
    if (!demo.steerable) { letGo(false); }
    if (!demo.on) { closeFull(); }
    else if (demo.wantFull) { demo.wantFull = false; openFull(); }
    showDrawing();
    placeDot();
    pump(false);
  }
  function onDrawn(event) {
    var payload = JSON.parse(event.data);
    demo.svg = payload.svg;
    if (payload.keys !== demo.keys) {
      demo.keys = payload.keys;
      el("demo-keys").innerHTML = payload.keys;
    }
    el("demo-drawing").innerHTML = payload.svg;
    showDrawing();
    placeDot();
  }
  // Only the drawing of the session the frame is (Task 8's carried (c)): the hub keeps the last
  // drawing after a demo ends, and a demo service's idle frame is no session's.
  function showDrawing() {
    var svg = el("demo-drawing").querySelector("svg");
    var mine = Boolean(svg && demo.on && demo.session &&
                       svg.getAttribute("data-session") === demo.session);
    el("demo-drawing").hidden = !mine;
    el("demo-none").hidden = mine;
  }
  function openFull() {
    if (!demo.on) { return; }
    demo.full = true;
    el("demo-pane").classList.add("full");
    body.classList.add("demo-full");
    placeDot();
  }
  function closeFull() {
    demo.full = false;
    el("demo-pane").classList.remove("full");
    body.classList.remove("demo-full");
    placeDot();
  }
  // The drawing under client point (x, y), or null: the drawing shown, its viewBox mapped to the
  // window by its own transform, so a letterbox around it is off the drawing.
  function drawingAt(x, y) {
    if (x === null || !demo.on || el("demo-drawing").hidden) { return null; }
    var svg = el("demo-drawing").querySelector("svg");
    var m = svg ? svg.getScreenCTM() : null;
    if (!m || !svg.viewBox || !svg.viewBox.baseVal) { return null; }
    var box = svg.viewBox.baseVal;
    var left = m.a * box.x + m.e, top = m.d * box.y + m.f;
    if (x < left || y < top || x > left + m.a * box.width || y > top + m.d * box.height) { return null; }
    return svg;
  }
  // **The pointer in degrees** (demo mode §3.3, §4.4; `demoscreen`): each eye of the drawing is a
  // `g.eye` whose user units are centimeters from that eye's straight-ahead point, +y up; the point
  // is read into the eye it lies over by the group's own transform, then turned into degrees per
  // axis, atan(x_cm / D), D its `data-distance-cm`, as `geometry` maps every position -- never an
  // average pixels per degree (the PI, 2026-10-19).
  function degreesAt(svg, x, y) {
    var eyes = svg.querySelectorAll("g.eye");
    var eye = null;
    var gap = Infinity;
    Array.prototype.forEach.call(eyes, function (group) {
      var shown = (group.querySelector(".frame") || group).getBoundingClientRect();
      var away = x < shown.left ? shown.left - x : (x > shown.right ? x - shown.right : 0);
      if (away < gap) { gap = away; eye = group; }
    });
    if (!eye) { return null; }
    var point = svg.createSVGPoint();
    point.x = x;
    point.y = y;
    var cm = point.matrixTransform(eye.getScreenCTM().inverse());
    var d = Number(eye.getAttribute("data-distance-cm"));
    var deg = { x: Math.atan(cm.x / d) * 180 / Math.PI, y: Math.atan(cm.y / d) * 180 / Math.PI };
    return isFinite(deg.x) && isFinite(deg.y) ? deg : null;
  }
  function pointerNow() {
    var svg = gaze.inside ? drawingAt(gaze.x, gaze.y) : null;
    var deg = svg ? degreesAt(svg, gaze.x, gaze.y) : null;
    return deg ? { over: true, x: deg.x, y: deg.y } : { over: false, x: 0, y: 0 };
  }
  // Whether this page may steer now: a demo session's frame, a console with the gaze endpoint, and
  // a page that may write -- the box's own, or the https page signed in (§4.5).
  function maySteer() {
    if (!canGaze || !demo.on || !demo.steerable) { return false; }
    return signinPage ? (signedIn() && confirmed) : canWrite;
  }
  // The number keys and B act only over the drawing or in the full window (§4.6).
  function keysLive() {
    return maySteer() && (demo.full || (gaze.inside && drawingAt(gaze.x, gaze.y) !== null));
  }
  // The pointer's dot, drawn where the pointer is over the drawing, for a page that may steer; a
  // viewer who cannot write sees the drawing and no dot (§4.5). Hollow while B is held.
  function placeDot() {
    var dot = el("demo-dot");
    var show = maySteer() && gaze.inside && drawingAt(gaze.x, gaze.y) !== null;
    dot.hidden = !show;
    if (!show) { return; }
    var screen = el("demo-screen").getBoundingClientRect();
    dot.style.left = (gaze.x - screen.left) + "px";
    dot.style.top = (gaze.y - screen.top) + "px";
    dot.classList.toggle("lost", gaze.b);
  }
  function steerSays(state, text, tone) {
    if (demo.steer !== state) {
      demo.steer = state;
      el("demo-pane").setAttribute("data-steer", state);
    }
    var line = el("demo-steer");
    if (line.textContent !== text) { line.textContent = text; }
    line.className = "sent " + (tone || "");
  }
  function changed() {
    gaze.moved = true;
    if (demo.on && !gaze.framed) {
      gaze.framed = true;
      window.requestAnimationFrame(function () { gaze.framed = false; pump(true); });
    }
  }
  function arm(ms) {
    clearTimeout(gaze.timer);
    gaze.timer = setTimeout(function () { pump(false); }, ms);
  }
  // A report now, or the timer armed for the next: at most one an animation frame while the
  // pointer moves (`framed`), at least every GAZE_EVERY_MS while it is still, one in flight. A
  // page sends nothing while its pointer is off the drawing and it does not steer, nor after an
  // Escape until its pointer moves again.
  function pump(framed) {
    if (gaze.inFlight || !demo.on) { return; }
    if (!maySteer() || gaze.hush) { gaze.moved = false; arm(GAZE_EVERY_MS); return; }
    var now = pointerNow();
    if (!now.over && !gaze.engaged) { gaze.moved = false; arm(GAZE_EVERY_MS); return; }
    var wait = GAZE_EVERY_MS - (performance.now() - gaze.lastAt);
    if ((framed && gaze.moved) || wait <= 0) { report(now); return; }
    arm(wait);
  }
  function gazePost(payload, keepalive) {
    var headers = { "Content-Type": "application/json" };
    if (signinPage && signin) { headers["Authorization"] = "Bearer " + signin.access; }
    return fetch("/gaze", {
      method: "POST",
      headers: headers,
      body: JSON.stringify(payload),
      cache: "no-store",
      keepalive: keepalive
    }).then(answerOf);
  }
  function report(now) {
    clearTimeout(gaze.timer);
    gaze.inFlight = true;
    gaze.moved = false;
    gaze.lastAt = performance.now();
    gaze.seq += 1;
    var epoch = gaze.epoch;
    var payload = {
      page: gaze.id, seq: gaze.seq, x: now.x, y: now.y, over: now.over, b: gaze.b,
      button: gaze.button, held: gaze.held, presses: gaze.presses.slice()
    };
    (signinPage ? fresh() : Promise.resolve(true)).then(function (ok) {
      if (!ok) {
        gaze.engaged = false;
        steerSays("", "not steering: " + (unusableFor || signedOutFor || NO_SIGNIN), "crit");
        return null;
      }
      return gazePost(payload, false).then(function (answer) {
        if (epoch === gaze.epoch) { steered(answer); }
      });
    }).catch(function () {
      gaze.engaged = false;
      steerSays("", "not sent: this page could not reach wlx serve", "crit");
    }).then(function () {
      gaze.inFlight = false;
      if (gaze.moved && !gaze.framed) {
        gaze.framed = true;
        window.requestAnimationFrame(function () { gaze.framed = false; pump(true); });
      }
      pump(false);
    });
  }
  // What `wlx serve` made of a report (`serve.Steering`): sent, the steer this page's; another page
  // steers, said; no demo running; not delivered or busy, which is no fault and is said quietly,
  // the page keeping its eye; a refusal, said.
  function steered(answer) {
    var status = answer.status;
    if (status === "sent") {
      gaze.engaged = true;
      steerSays("steering", DEMO_STEERING, "ok");
    } else if (status === "steered_elsewhere") {
      gaze.engaged = false;
      steerSays("elsewhere", answer.said, "warn");
    } else if (status === "not_delivered" || status === "busy") {
      steerSays("waiting", DEMO_WAITING, "");
    } else if (status === "not_a_demo") {
      gaze.engaged = false;
      steerSays("", "", "");
    } else if (status !== "dropped") {
      gaze.engaged = false;
      steerSays("", answer.said, "crit");
      if (answer.reason === "signed_out" || answer.reason === "other_rig" ||
          answer.reason === "not_accepted" || answer.reason === "no_token") { forget(); }
    }
  }
  // **Letting go of the eye** (§4.5): Escape, the tab hidden, the page going away, or the demo
  // session's end. A release goes even as the page unloads (`keepalive`); an answer to a report
  // sent before it is not taken as the steer kept (`epoch`). After an Escape or a hidden tab
  // (`hush`) nothing is sent until the pointer moves again.
  function letGo(hush) {
    var held = gaze.engaged || gaze.inFlight;
    gaze.engaged = false;
    gaze.epoch += 1;
    if (hush) { gaze.hush = true; }
    if (held) {
      gazePost({ page: gaze.id, release: true }, true).then(function (answer) {
        steerSays("", answer.said, "");
      }, function () { /* nothing to undo: the steer lapses on its own */ });
    } else if (demo.steer) {
      steerSays("", "", "");
    }
  }
  function digitOf(e) {
    if (/^[1-9]$/.test(e.key)) { return Number(e.key); }
    var code = /^(?:Digit|Numpad)([1-9])$/.exec(e.code || "");
    return code ? Number(code[1]) : 0;
  }
  document.addEventListener("pointermove", function (e) {
    gaze.x = e.clientX;
    gaze.y = e.clientY;
    gaze.inside = true;
    gaze.hush = false;
    placeDot();
    changed();
  });
  document.addEventListener("mouseout", function (e) {
    if (e.relatedTarget) { return; }
    gaze.inside = false;  // out of the window: gaze away, as off the drawing
    placeDot();
    changed();
  });
  document.addEventListener("pointerdown", function (e) {
    if (e.button === 0) { gaze.button = true; changed(); }
  });
  document.addEventListener("pointerup", function (e) {
    if (e.button === 0) { gaze.button = false; changed(); }
  });
  window.addEventListener("blur", function () {
    // A key or the button let go while the page could not see it.
    if (gaze.held || gaze.b || gaze.button) {
      gaze.held = 0;
      gaze.b = false;
      gaze.button = false;
      placeDot();
      changed();
    }
  });
  document.addEventListener("keyup", function (e) {
    var digit = digitOf(e);
    if (digit && (gaze.held & (1 << (digit - 1)))) {
      gaze.held &= ~(1 << (digit - 1));
      changed();
    } else if ((e.key === "b" || e.key === "B" || e.code === "KeyB") && gaze.b) {
      gaze.b = false;
      placeDot();
      changed();
    }
  });
  // Escape closes the full window and lets go of the eye, wherever focus is (§4.3, §4.5).
  document.addEventListener("keydown", function (e) {
    if (e.key !== "Escape" || e.repeat) { return; }
    if (demo.full) { closeFull(); }
    if (gaze.engaged || gaze.inFlight) { letGo(true); }
  });
  window.addEventListener("pagehide", function () {
    if (gaze.engaged || gaze.inFlight) { letGo(false); }
  });
  // **A hidden tab lets go as Escape does** (the build's re-review, N1): a browser throttles a
  // hidden tab's timers but runs them, so a still pointer's reports would go on and let a trial
  // through each boundary to end as tracker lost. Hushed whether or not it steers, it sends nothing
  // until the pointer moves on the page again.
  document.addEventListener("visibilitychange", function () {
    if (document.visibilityState !== "hidden") { return; }
    if (gaze.engaged || gaze.inFlight) { letGo(true); } else { gaze.hush = true; }
  });
  el("demo-screen").addEventListener("click", function () { if (!demo.full) { openFull(); } });
  // The New session dialog's demo choice (§4.1): on a demo service the departure and the id filled
  // for it, REFERENCE its one animal; on a rig the demo box, which fills the same and locks the
  // subject to REFERENCE. Each fill is the clock's now, editable; one left as filled is refilled
  // when the dialog opens again, one edited kept.
  var demoFilled = { left: "", id: "" };
  var demoBoxed = false;
  function two(n) { return (n < 10 ? "0" : "") + n; }
  function demoService() { return Boolean(el("dn-demo").querySelector("[data-demo-service]")); }
  function demoTicked() {
    var box = el("dn-demo-box");
    return Boolean(box && box.checked && !box.disabled);
  }
  function fillDemo() {
    var now = new Date();
    var left = two(now.getHours()) + ":" + two(now.getMinutes());
    var id = "demo-" + now.getFullYear() + two(now.getMonth() + 1) + two(now.getDate()) + "-" +
      two(now.getHours()) + two(now.getMinutes()) + two(now.getSeconds());
    if (el("dn-left").value === "" || el("dn-left").value === demoFilled.left) {
      el("dn-left").value = left;
      demoFilled.left = left;
    }
    if (el("dn-id").value === "" || el("dn-id").value === demoFilled.id) {
      el("dn-id").value = id;
      demoFilled.id = id;
    }
  }
  function unfillDemo() {
    if (el("dn-left").value === demoFilled.left) { el("dn-left").value = ""; }
    if (el("dn-id").value === demoFilled.id) { el("dn-id").value = ""; }
    demoFilled = { left: "", id: "" };
  }
  function lockSubject(locked) {
    var subject = el("dn-subject");
    var box = el("dn-demo-box");
    if (locked && box) {
      choose(subject, box.getAttribute("data-reference"));
      subject.disabled = true;
      subject.setAttribute("data-demo-locked", "1");
    } else if (subject.hasAttribute("data-demo-locked")) {
      subject.removeAttribute("data-demo-locked");
      subject.disabled = signinPage ? !(signedIn() && confirmed) : !canWrite;
    }
  }
  function restoreDemoBox() {
    var box = el("dn-demo-box");
    if (box) { box.checked = demoBoxed && !box.disabled; }
    lockSubject(demoTicked());
  }
  function onFrame(event) {
    var payload = JSON.parse(event.data);
    framesSeen += 1;
    Object.keys(payload.frags).forEach(function (id) { swap(id, payload.frags[id]); });
    // A frame whose boxes are as the last drew them sends none (`wlx serve` sends what changed), and
    // is still one of the frames an act waits on for the rig's word (`ANSWER_FRAMES`).
    if (!("params" in payload.frags) && !("training-params" in payload.frags) && !pressing() &&
        (Object.keys(out).length || Object.keys(withdrawing).length)) {
      judge();
      settle();
    }
    live = payload.live;
    baseline = payload.age === null ? null : performance.now() - payload.age * 1000;
    lost = false;
    check();
  }
  function open() {
    closed = false;
    lost = false;
    el("gone").hidden = true;
    source = new EventSource("/events");
    source.addEventListener("frame", onFrame);
    source.addEventListener("drawn", onDrawn);
    source.onerror = function () {
      if (closed) { return; }
      lost = true;
      body.classList.add("stale");
      say("stream lost", "crit");
      if (source.readyState === EventSource.CLOSED) {
        setTimeout(function () { if (!closed && lost) { open(); } }, 3000);
      }
    };
  }
  function storedName() {
    try { return window.localStorage.getItem(NAME_KEY) || ""; } catch (e) { return ""; }
  }
  var name = storedName();
  function showName() {
    if (!el("who")) { return; }
    el("who").textContent = name ? name + " (box, unverified)" : "not given yet";
  }
  function askName() {
    var given = window.prompt("Your name, for the session record:", name);
    if (given === null) { return ""; }
    given = given.trim();
    if (!given) { return ""; }
    name = given;
    try { window.localStorage.setItem(NAME_KEY, given); } catch (e) { /* kept for this page only */ }
    showName();
    return given;
  }
  function tell(text, tone) {
    var line = el("sent");
    line.textContent = text;
    // The bar's one line, cut short: its whole in the title, so the bar never grows under a press.
    line.title = text;
    line.className = "sent " + (tone || "");
    // Task 6's deferred point: the control bar's line is behind the dialog's scrim.
    if (!el("dlg-new").hidden) { el("dn-msg").textContent = text; }
  }
  function post(command, then, after) {
    var done = after || function () {};
    if (signinPage) {
      fresh().then(function (ok) {
        if (!ok) {
          tell("not sent: " + (unusableFor || signedOutFor || NO_SIGNIN), "crit");
          done();
          return;
        }
        deliver(command, { "Authorization": "Bearer " + signin.access }, then, done);
      }, function () {
        tell("not sent: this sign-in could not be renewed", "crit");
        done();
      });
      return;
    }
    if (!canWrite) { done(); return; }
    var by = name || askName();
    if (!by) {
      tell("not sent: give your name first -- every command records who sent it", "crit");
      done();
      return;
    }
    command.by = by;
    deliver(command, {}, then, done);
  }
  function deliver(command, extra, then, done) {
    tell("sending…", "");
    var headers = { "Content-Type": "application/json" };
    Object.keys(extra).forEach(function (key) { headers[key] = extra[key]; });
    var carried = String(headers["Authorization"] || "").replace("Bearer ", "");
    fetch("/commands", {
      method: "POST",
      headers: headers,
      body: JSON.stringify(command),
      cache: "no-store"
    }).then(answerOf).then(function (answer) {
      tell(answer.said, answer.status === "sent" || answer.status === "signaled" ? "ok" : "crit");
      // A refusal for the token (the plan's Ruling 8): never re-sent; renew, or sign out.
      if (answer.reason === "expired") {
        expiredAtTheRig(carried).then(function (renewed) {
          if (renewed) { tell("this sign-in was renewed; the command was not sent: send it again", "ok"); }
        });
      }
      else if (answer.reason === "signed_out" || answer.reason === "other_rig" ||
               answer.reason === "not_accepted" || answer.reason === "no_token") { forget(); }
      return answer;
    }, function () {
      tell(command.kind === "reward" ? REWARD_LOST : "not delivered: this page could not reach wlx serve", "crit");
      return null;
    }).then(function (answer) {
      // The answer's handler outside the catch (the whole-build review's M4): a fault in it is the
      // page's, thrown to the console, never said as a command not delivered. `done` runs either way.
      try {
        if (answer && then) { then(answer); }
      } finally { done(); }
    }, function (fault) { done(); throw fault; });
  }
  function decimals(step) { return (String(step).split(".")[1] || "").length; }
  function stepInput(input, dir) {
    var step = Number(input.getAttribute("data-step")) || 0.01;
    var lo = input.hasAttribute("data-min") ? Number(input.getAttribute("data-min")) : -Infinity;
    var hi = input.hasAttribute("data-max") ? Number(input.getAttribute("data-max")) : Infinity;
    var v = Number(input.value);
    if (input.value.trim() === "" || !isFinite(v)) { v = isFinite(lo) ? lo : 0; }
    // Round to the step first, then clamp -- and on a clamp, write the edge's own
    // attribute string exactly, never `toFixed` it again: `toFixed` rounding a
    // clamped value at the step's decimals could still overshoot a ceiling with
    // more of its own (0.125 mL rounded to "0.13" at a 0.01 step).
    v = Math.round((v + dir * step) / step) * step;
    if (v <= lo) { input.value = input.getAttribute("data-min"); }
    else if (v >= hi) { input.value = input.getAttribute("data-max"); }
    else { input.value = v.toFixed(decimals(step)); }
    // A draft, never a send (the console interface design's call: "−/+ wait for Apply, as typing
    // does"; Shift steps ten times as far, `dir` then ±10).
    var box = input.closest(".box");
    if (box) { refresh(box); showBar(); }
  }
  function closeNote(note) {
    if (markNo === null) { return; }
    var number = markNo;
    markNo = null;
    el("mark-form").hidden = true;
    post({ kind: "note", mark: number, note: note });
  }
  function mark() {
    var button = el("controls").querySelector('[data-cmd="mark"]');
    if (!button || button.disabled) { return; }
    closeNote("");
    post({ kind: "mark", pressed_at: Date.now() / 1000 }, function (answer) {
      if (answer.status !== "signaled") { return; }
      markNo = answer.mark;
      el("mark-note").value = "";
      el("mark-form").hidden = false;
      el("mark-note").focus();
    });
  }
  function toggleAllowed(detail) {
    // The same hold, whichever route a pause or resume comes from (round 2: the
    // click handler alone missed the P key, which calls this before `command` too).
    var now = performance.now();
    if (detail > 1 || now - lastToggleAt < TOGGLE_HOLD_MS) { return false; }
    lastToggleAt = now;
    return true;
  }
  function holdReward() {
    var button = el("controls").querySelector('[data-cmd="reward"]');
    if (rewarding && button && !button.disabled) {
      button.disabled = true;
      button.setAttribute("data-held", "1");
    }
  }
  function reward() {
    var button = el("controls").querySelector('[data-cmd="reward"]');
    if (!button || button.disabled || rewarding) { return; }
    rewarding = true;
    holdReward();
    post({ kind: "reward" }, null, function () {
      rewarding = false;
      var held = el("controls").querySelector('[data-cmd="reward"][data-held]');
      if (held) { held.removeAttribute("data-held"); held.disabled = false; }
      applySignIn();
    });
  }
  // P4d-2b b3a-2 (spec §6.2): a run, a session and the two marks, from the page. Every
  // field is a static element no frame replaces; each form sends one command through
  // `post`, the one `fetch`, which adds who sent it.
  function chosenTask() { return el("task-sel").value; }
  // Engine build C2b (the PI, 2026-10-19, "Preselect first, keep plain"; 2026-10-22, "The plan
  // last run"): the plan a run plays, the empty choice the plain run; a session's first run
  // preselects the task's first plan, its later runs the plan last run (`data-last`, the same
  // task's, still among its plans), else the first, when the plans come back to
  // this page's own plain pre-flight request -- the task chosen, the only one offered (the
  // engineering review, I3), or the next run's -- a choice made since standing; the trials box
  // hidden while a plan is chosen. `awaiting`, the task whose plain pre-flight this page asked
  // for and has not yet had its plans from: a reload, or another member's pre-flight, arms
  // nothing (the task's first review, I1).
  var awaiting = null;
  function chosenPlan() { return el("plan-sel").value || null; }
  function showTrials() { el("run-trials").closest("label").hidden = Boolean(chosenPlan()); }
  function preselect() {
    var select = el("plan-sel");
    var first = select.options[0];
    var task = first ? first.getAttribute("data-for") : null;
    var chosen = select.querySelector("option[data-last]") || first;
    // Nothing here reads the pre-flight pill, which a frame swaps after this select.
    if (task && task === awaiting && task === chosenTask() && !select.value) {
      awaiting = null;
      if (chosen.value) {
        select.value = chosen.value;
        takePreflight(false);
      }
    }
    showTrials();
  }
  function betweenRuns() {
    // The pre-flight pill is a button only between runs (`_pf_pill`).
    return Boolean(el("pf-pill").querySelector('[data-cmd="check"]'));
  }
  // The stage picked in the pre-flight shown, while it is the one for the task and plan chosen: its
  // name, or null for the plan's first; undefined where the pre-flight shown is another's (the
  // pop-out search build's Task 7: the check sends it, as the start does).
  function pickedStage() {
    var button = el("controls").querySelector('[data-cmd="start"]');
    if (!button || button.getAttribute("data-task") !== chosenTask() ||
        (button.getAttribute("data-plan") || null) !== chosenPlan()) { return undefined; }
    var stage = el("start-block");
    return stage && stage.selectedIndex > 0 ? stage.value : null;
  }
  function takePreflight(showPanel) {
    var task = chosenTask();
    // Taken again for the task and plan it shows, the pre-flight keeps the stage and the picks; a
    // task or plan chosen anew forgets them.
    var stage = pickedStage();
    acked = {};
    if (stage === undefined) { picked = {}; }
    if (!task) { tell("not sent: no task is offered to check", "crit"); return; }
    // A plain run's pre-flight is how the page learns the task's plans: arm the preselection.
    // Armed only where this page can send: the sign-in page signed in, the rig PC's own page
    // (no sign-in) able to write.
    awaiting = chosenPlan() === null && (signinPage ? signedIn() : canWrite) ? task : null;
    post({ kind: "check", task: task, values: {}, plan: chosenPlan(), start_block: stage || null });
    if (showPanel) { el("t-setup").checked = true; }
  }
  function startRun() {
    var button = el("controls").querySelector('[data-cmd="start"]');
    var task = button ? button.getAttribute("data-task") : "";
    var plan = button ? (button.getAttribute("data-plan") || null) : null;
    var trials = Number(el("run-trials").value.trim());
    if (!task || task !== chosenTask() || plan !== chosenPlan()) {
      tell("not sent: the pre-flight shown is not for the task and plan chosen; " +
           "take its pre-flight first (the pre-flight pill)", "crit");
      return;
    }
    // The trials box is hidden while a plan is chosen, and a plan's lengths are its own.
    if (plan) { trials = Number.isInteger(trials) && trials >= 1 ? trials : 1; }
    else if (!Number.isInteger(trials) || trials < 1) {
      tell("not sent: a run's trials are a whole number from 1", "crit");
      return;
    }
    var acknowledged = [];
    Array.prototype.forEach.call(document.querySelectorAll("input[data-ack]"), function (box) {
      if (box.checked) { acknowledged.push(box.getAttribute("data-ack")); }
    });
    // Where it starts, as picked (the pop-out search build's Task 6).
    var start = runStart();
    acked = {};
    restoreAcks();
    picked = {};
    post({ kind: "start", task: task, values: start.values, trials: trials,
           acknowledged: acknowledged, plan: plan, start_block: start.block });
  }
  function openNew() {
    el("dn-msg").textContent = "";
    el("dlg-new").hidden = false;
    // A demo's departure and id, the clock's now (demo mode §4.1): every session on a demo
    // service, the demo box's on a rig.
    if (demoService() || demoTicked()) { fillDemo(); }
    el("dn-subject").focus();
  }
  function openSession() {
    var given = el("dn-given").value.trim();
    var today = given === "" ? null : Number(given);
    if (today !== null && !isFinite(today)) {
      el("dn-msg").textContent = "not sent: the fluid given today is mL, or blank when it is not known";
      return;
    }
    var request = {
      kind: "open",
      session_id: el("dn-id").value.trim(),
      animal: el("dn-subject").value,
      deployment: el("dn-deployment").value,
      view: el("dn-view").value,
      session_kind: el("dn-kind").value,
      departure: el("dn-left").value.trim(),
      delivered_today: today,
      answer: null,
      amend_to: null,
      amend_reason: "",
      accepted: acceptedWarnings(),
      // Whether the session is a demo (demo mode §4.1): a demo service's every one, or the box.
      demo: demoService() || demoTicked()
    };
    if (!request.animal) { el("dn-msg").textContent = "not sent: choose the animal"; return; }
    if (!request.deployment) { el("dn-msg").textContent = "not sent: a deployment must be chosen"; return; }
    if (!request.session_kind) { el("dn-msg").textContent = "not sent: choose what this session is for"; return; }
    lastOpen = Object.assign({}, request);
    pendingOpen = request.session_id;
    post(request, function (answer) {
      el("dn-msg").textContent = answer.said;
      if (answer.status === "sent") { el("dlg-new").hidden = true; }
    });
  }
  function acceptedWarnings() {
    // What the person accepted for the session, each warning's code and its sentence as the
    // dialog shows it (the engine B plan, call 25): those the chosen kind accepts. One no kind
    // accepts carries no data-warn, and is never sent.
    var box = el("dn-accept");
    if (!box || !box.checked) { return []; }
    var pairs = [];
    Array.prototype.forEach.call(document.querySelectorAll("#dn-warnings [data-warn]"), function (row) {
      var kinds = row.getAttribute("data-kinds").split(" ");
      if (kinds.indexOf(el("dn-kind").value) >= 0) {
        pairs.push([row.getAttribute("data-warn"), row.getAttribute("data-detail")]);
      }
    });
    return pairs;
  }
  function askEnd() {
    el("end-return").value = "";
    el("end-confirm").hidden = false;
    el("end-return").focus();
  }
  function openReturn(session) {
    returnFor = session;
    el("ret-session").textContent = session;
    el("ret-at").value = "";
    el("return-form").hidden = false;
    el("t-end").checked = true;
    el("ret-at").focus();
  }
  function answerWarning(button) {
    var given = button.getAttribute("data-answer");
    var which = button.getAttribute("data-mark");
    var session = button.getAttribute("data-session");
    if (given === "re-type") { openReturn(session); return; }
    var sent = which === "departure" ? lastOpen : lastEnd;
    if (!sent || sent.session_id !== session) {
      tell("not sent: this page did not send the " + which + " this warning is about, so it cannot answer it; send the time again, then answer the warning it raises", "crit");
      return;
    }
    if (given === "amend") {
      el("amend-to").value = "";
      el("amend-why").value = "";
      el("amend-form").hidden = false;
      el("amend-to").focus();
    } else if (given === "confirm") {
      post(which === "departure" ? Object.assign({}, sent, { answer: "confirm" }) : Object.assign({}, sent, { confirm: true }));
    }
  }
  function command(cmd) {
    if (cmd === "stop") { el("stop-confirm").hidden = false; }
    else if (cmd === "mark") { mark(); }
    else if (cmd === "reward") { reward(); }
    else if (cmd === "new") { openNew(); }
    else if (cmd === "check") { takePreflight(true); }
    else if (cmd === "start") { startRun(); }
    else if (cmd === "end") { askEnd(); }
    else { post({ kind: cmd }); }
  }
  function rewardAllowed(detail) {
    // Same reasoning as `toggleAllowed` (R2, 2026-09-28): loopback's round trip can
    // return well inside a double click's span, so the disabled-until-answered rule
    // in `reward` alone can miss the second click.
    var now = performance.now();
    if (detail > 1 || now - lastRewardAt < REWARD_HOLD_MS) { return false; }
    lastRewardAt = now;
    return true;
  }
  function clearAllowed(detail, key) {
    var now = performance.now();
    if (detail > 1 || now - (lastClearAt[key] || -Infinity) < REWARD_HOLD_MS) { return false; }
    lastClearAt[key] = now;
    return true;
  }
  function pauseOrResume() {
    var button = el("controls").querySelector('[data-cmd="pause"], [data-cmd="resume"]');
    // No click to read a detail from a key press, so 1 -- never a double on its own,
    // still held to the same `TOGGLE_HOLD_MS` as a click.
    if (button && !button.disabled && toggleAllowed(1)) {
      command(button.getAttribute("data-cmd"));
    }
  }
  document.addEventListener("click", function (e) {
    if (!e.target.closest) { return; }
    keepMore(e);
    // A summary line opens its setting in the editor below (`openSetting`).
    var opening = e.target.closest(inCards(".summary .line[data-open]"));
    if (opening) { openSetting(opening.getAttribute("data-open")); return; }
    var pinning = e.target.closest(inCards("[data-pin-toggle]"));
    if (pinning) { togglePin(pinning.getAttribute("data-pin-toggle")); return; }
    var answering = e.target.closest("[data-answer]");
    if (answering && !answering.disabled) { answerWarning(answering); return; }
    var resuming = e.target.closest("[data-resume]");
    if (resuming && !resuming.disabled) { post({ kind: "resume_session", session_id: resuming.getAttribute("data-resume") }); return; }
    var returning = e.target.closest("[data-return]");
    if (returning && !returning.disabled) { openReturn(returning.getAttribute("data-return")); return; }
    // A box's Apply, Discard and *withdraw*, and the drafts bar's (the console interface
    // rework's Task 6).
    var applying = e.target.closest("[data-apply]");
    if (applying && !applying.disabled) { applyBox(applying.getAttribute("data-apply")); return; }
    var discarding = e.target.closest("[data-discard]");
    if (discarding && !discarding.disabled) { discard(discarding.getAttribute("data-discard")); return; }
    var taking = e.target.closest("[data-withdraw]");
    if (taking && !taking.disabled) { withdraw(taking.getAttribute("data-withdraw"), e.detail); return; }
    if (e.target.closest("#drafts-apply")) { if (!el("drafts-apply").disabled) { applyAll(); } return; }
    if (e.target.closest("#drafts-discard")) { if (!el("drafts-discard").disabled) { discardAll(); } return; }
    var switched = e.target.closest("[data-switch]");
    if (switched && !switched.disabled) {
      // A timing card's side: a draft of its box, sent by its Apply.
      var swung = switched.closest(".box");
      showSide(swung, switched.getAttribute("data-switch"));
      refresh(swung);
      showBar();
      return;
    }
    // A color's hue swatch: a draft of its box, the swatch pressed, sent by its Apply (the
    // console interface design's call: "a swatch or a tick is a draft").
    var hue = e.target.closest(inCards(".box .hue[data-color]"));
    if (hue && !hue.disabled) {
      var colored = hue.closest(".box");
      Array.prototype.forEach.call(colored.querySelectorAll(".hue[data-color]"), function (other) {
        var on = other === hue;
        other.classList.toggle("on", on);
        other.setAttribute("aria-pressed", on ? "true" : "false");
      });
      refresh(colored);
      showBar();
      return;
    }
    // A choice among a setting's segments: a draft of its box, as a swatch is, sent by its Apply as
    // a `choice` by its words (the pop-out revision's Task 5b).
    var chosen = e.target.closest(inCards(".box .ch[data-choice]"));
    if (chosen && !chosen.disabled) {
      pressChoice(chosen.closest("[data-choices]"), chosen.getAttribute("data-choice"));
      var picked = chosen.closest(".box");
      refresh(picked);
      showBar();
      return;
    }
    var button = e.target.closest("[data-cmd]");
    if (button && !button.disabled) {
      var cmd = button.getAttribute("data-cmd");
      if ((cmd === "pause" || cmd === "resume") && !toggleAllowed(e.detail)) { return; }
      // The moves between blocks, held as a clear is: a double click is one move.
      if (cmd === "next_block" || cmd === "back_block") {
        if (!clearAllowed(e.detail, cmd)) { return; }
        post({ kind: cmd });
        return;
      }
      if (cmd === "reward" && !rewardAllowed(e.detail)) { return; }
      // A run's count and its drumming (engine build C2a), each naming what it is for.
      if (cmd === "clear") {
        var clearKey = button.getAttribute("data-condition")
          + (button.hasAttribute("data-rest") ? "/rest" : "");
        if (!clearAllowed(e.detail, clearKey)) { return; }
        post({ kind: "clear", condition: button.getAttribute("data-condition"),
               rest: button.hasAttribute("data-rest") });
        return;
      }
      if (cmd === "drum") {
        post({ kind: "drum", scope: button.getAttribute("data-scope") });
        return;
      }
      if (cmd === "training") {
        post({ kind: "training", setting: button.getAttribute("data-setting"),
               on: button.getAttribute("data-on") === "1" });
        return;
      }
      // The console settings build's Task 10 (the design's §8): the training switch's position.
      if (cmd === "shaping") {
        post({ kind: "shaping", position: button.getAttribute("data-position") });
        return;
      }
      // Engine build C3 (the PI, 2026-10-30, Q7a and Q7b; TSK-43): a setting handed back, a drawn
      // range changed live, and the run taken back to a moment, each naming what it is for; a
      // double click is one act, as a clear's is.
      if (cmd === "hand_back") {
        var named = button.getAttribute("data-name");
        if (!clearAllowed(e.detail, "hand_back/" + named)) { return; }
        // At once, a deliberate press (the console interface design's call), under a command id
        // of its own, so its box says the hand-back waiting is this page's and offers *withdraw*.
        post({ kind: "hand_back", name: named, cid: nextCid() });
        return;
      }
      // A new color (the console settings build's Task 8): *preview* asks wlx serve and writes
      // nothing; *save as a proposal* sends it to the rig, which writes the set's proposed file. A
      // double click is one save, as a clear's is.
      if (cmd === "preview_color") { previewColor(button); return; }
      if (cmd === "define_color") {
        var panel = button.closest("[data-newc]");
        var defined = newColorCommand(panel);
        if (!defined || !clearAllowed(e.detail, "define_color/" + panel.getAttribute("data-newc"))) { return; }
        defined.kind = "define_color";
        post(defined);
        return;
      }
      // The trainer's panel (the pop-out search build's Task 7): *Move up* or *Move back* confirms
      // the rig's suggestion, naming it, and *Hold* declines it, the whole prompt; *lock at* holds
      // the staircase's setting at its level, as a person's value does; *add* widens the pool by
      // the pairings ticked. Each held against a double click, as a clear is.
      if (cmd === "confirm" || cmd === "decline") {
        var answered = Number(button.getAttribute("data-suggestion"));
        if (!clearAllowed(e.detail, cmd + "/" + answered)) { return; }
        post(cmd === "decline" ? { kind: "decline", suggestion: answered }
                               : { kind: button.getAttribute("data-move"), suggestion: answered });
        return;
      }
      if (cmd === "lock") {
        var locked = button.getAttribute("data-name");
        if (!clearAllowed(e.detail, "lock/" + locked)) { return; }
        post({ kind: "set", name: locked, value: Number(button.getAttribute("data-value")) });
        return;
      }
      if (cmd === "widen") {
        var adding = 0;
        Array.prototype.forEach.call(el("rt-train").querySelectorAll("input[data-widen]"), function (box) {
          if (box.checked) { adding += Number(box.getAttribute("data-widen")); }
        });
        if (!adding) { tell("not sent: tick a pairing to add first", "crit"); return; }
        if (!clearAllowed(e.detail, "widen/" + button.getAttribute("data-suggestion"))) { return; }
        post({ kind: "set", name: button.getAttribute("data-name"),
               value: Number(button.getAttribute("data-value")) + adding });
        return;
      }
      if (cmd === "revert") {
        var moment = Number(button.getAttribute("data-change"));
        if (!clearAllowed(e.detail, "revert/" + moment)) { return; }
        post({ kind: "revert", change: moment });
        return;
      }
      command(cmd);
      return;
    }
    var arrow = e.target.closest("[data-dir]");
    if (arrow && !arrow.disabled) {
      var input = arrow.closest(".spin").querySelector("input[data-param]");
      if (input && !input.disabled) {
        stepInput(input, Number(arrow.getAttribute("data-dir")) * (e.shiftKey ? 10 : 1));
      }
    }
  });
  document.addEventListener("change", function (e) {
    if (!e.target.matches) { return; }
    if (e.target.matches("select[data-shape]")) {
      var shaped = e.target.closest(".box");
      showShape(shaped, e.target.value);
      refresh(shaped);
      showBar();
    }
    else if (e.target.matches("select[data-colorset]")) {
      colorSets[e.target.getAttribute("data-colorset")] = e.target.value;
      showHues(e.target, e.target.value);
    }
    else if (e.target.closest("[data-newc]")) {
      var changed = e.target.closest("[data-newc]");
      newColorShow(changed);
      newColorRead(changed);
    }
    else if (e.target.matches("input[data-ack]")) { acked[e.target.getAttribute("data-ack")] = e.target.checked; }
    else if (e.target.id === "start-block") {
      picked.block = e.target.value;
      showStage();
      // Taken again at the stage picked, so its task checks judge a start there (Task 7).
      if (betweenRuns()) { takePreflight(false); }
    }
    else if (e.target.matches("select[data-start-setting]")) {
      picked["level:" + e.target.getAttribute("data-start-setting")] = e.target.value;
    }
    else if (e.target.matches("input[data-pairing]")) {
      picked["pairing:" + e.target.getAttribute("data-pairing")] = e.target.checked;
    }
    else if (e.target.matches("input[data-widen]")) {
      widened[e.target.getAttribute("data-suggestion") + ":" + e.target.getAttribute("data-widen")] =
        e.target.checked;
    }
    else if (e.target.id === "dn-demo-box") {
      demoBoxed = e.target.checked;
      if (demoBoxed) { fillDemo(); } else { unfillDemo(); }
      lockSubject(demoBoxed);
    }
    else if (e.target.id === "task-sel") {
      if (betweenRuns()) { el("plan-sel").value = ""; takePreflight(false); }
    }
    else if (e.target.id === "plan-sel") {
      showTrials();
      if (betweenRuns()) { takePreflight(false); }
      // The person chose: the pre-flight this takes arms nothing.
      awaiting = null;
    }
  });
  document.addEventListener("focusout", function () { setTimeout(release, 0); });
  document.addEventListener("input", function (e) {
    // An edit in a box is a draft of it, judged as it is typed (the controls review's §2).
    var edited = e.target && e.target.closest && !e.target.closest("[data-newc]") &&
      e.target.closest(inCards(".box"));
    if (edited) { refresh(edited); showBar(); }
    // What is typed in a New color panel is kept, so a frame replacing the cards keeps it.
    var typing = e.target && e.target.closest && e.target.closest("[data-newc]");
    if (typing) { newColorShow(typing); newColorRead(typing); }
  });
  // A New color panel opened or closed stays so across frames (`toggle` does not bubble).
  document.addEventListener("toggle", function (e) {
    if (e.target && e.target.matches && e.target.matches("[data-newc]")) { newColorRead(e.target); }
  }, true);
  // The primary button only; the hold ends with the press -- its pointer going up, cancelled,
  // a context menu or a drag taking it over, the window losing focus -- or, a release the page
  // never sees, when the ten seconds are up, when the held frame is shown (fix round 3).
  document.addEventListener("pointerdown", function (e) {
    if (e.button === 0 && e.target && e.target.closest &&
        e.target.closest("#params, #training-params, #moments, #pinned-params")) {
      pressedAt = performance.now();
      setTimeout(release, PRESS_MS + 50);
    }
  });
  // After the click that follows the pointer going up has been handled.
  function unpress() { pressedAt = null; setTimeout(release, 0); }
  document.addEventListener("pointerup", function () { setTimeout(unpress, 0); });
  document.addEventListener("pointercancel", unpress);
  document.addEventListener("contextmenu", unpress);
  document.addEventListener("dragstart", unpress);
  window.addEventListener("blur", unpress);
  document.addEventListener("keydown", function (e) {
    if (e.metaKey || e.ctrlKey || e.altKey || e.repeat) { return; }
    var t = e.target;
    if (t && (/^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName) || t.isContentEditable)) { return; }
    var k = e.key.toLowerCase();
    var digit = digitOf(e);
    if (k === "p") { e.preventDefault(); pauseOrResume(); }
    else if (k === "m") { e.preventDefault(); mark(); }
    // A demo's (§4.6): the number keys and B over the drawing or in the full window, F for it.
    else if (digit && keysLive()) {
      e.preventDefault();
      gaze.held |= 1 << (digit - 1);
      gaze.presses[digit - 1] += 1;
      changed();
    }
    else if (k === "b" && keysLive()) { e.preventDefault(); gaze.b = true; placeDot(); changed(); }
    else if (k === "f" && demo.on) { e.preventDefault(); openFull(); }
  });
  // **The keys in a box's field** (the controls review's F7): Enter is Apply; Esc is Discard, and
  // a second Esc, with no draft, leaves the field; ↑ and ↓ step it, Shift ten steps; and a whole
  // setting's field takes no decimal point or comma (the console interface design's goal 6).
  // `field` is the box's own field the keys act on; `typed`, the one typed in -- the same, or its
  // pinned copy's (`pinKeys`), which keeps the focus.
  // **A refused point's fraction** (the whole-build review's I5), by setting: after a `.` or `,`
  // refused in a whole field, each digit after it is refused too -- "12.5" stays "12", never
  // "125" -- and the box's draft cannot be sent while it stands (`draftOf`), saying *whole numbers
  // only*. Any other key in the field, or the field left, ends it.
  var fractions = {};
  function fieldKeys(e, field, typed) {
    var box = field.closest(".box");
    var name = nameOf(box);
    var plain = !e.metaKey && !e.ctrlKey && !e.altKey;
    if (fractions[name]) {
      if (plain && e.key.length === 1 && e.key >= "0" && e.key <= "9") {
        e.preventDefault();
        noted(box, WHOLE);
        refresh(box);
        return;
      }
      if (e.key !== "Enter" && e.key !== "Shift" && e.key !== "." && e.key !== ",") {
        delete fractions[name];
        refresh(box);
      }
    }
    if (e.key === "Enter") { e.preventDefault(); applyBox(name); }
    else if (e.key === "Escape") {
      e.preventDefault();
      var waited = out[name] && out[name].phase === "sending" && answeredLong(out[name]);
      if (drafts[name] || waited) { discard(name, typed === field ? field : null); }
      else {
        typed.blur();
        // A second Esc returns to the setting's summary line, a pinned copy's to its pinned line.
        leftFrom = name;
      }
    }
    else if ((e.key === "ArrowUp" || e.key === "ArrowDown") && field.hasAttribute("data-step")) {
      e.preventDefault();
      stepInput(field, (e.key === "ArrowUp" ? 1 : -1) * (e.shiftKey ? 10 : 1));
    }
    else if (field.hasAttribute("data-whole") && (e.key === "." || e.key === ",") && plain) {
      e.preventDefault();
      fractions[name] = true;
      noted(box, WHOLE);
      refresh(box);
    }
  }
  document.addEventListener("focusout", function (e) {
    var copy = pinOf(e.target);
    // A pinned copy's field ends its box's fraction as the box's own does (the re-review's M-a).
    var box = copy ? cardOf(copy.getAttribute("data-pin"))
      : e.target && e.target.closest ? e.target.closest(".box") : null;
    if (box && fractions[nameOf(box)]) {
      delete fractions[nameOf(box)];
      refresh(box);
    }
  });
  document.addEventListener("keydown", function (e) {
    var field = e.target;
    if (!field || !field.matches || !field.matches(inCards(".box input")) || field.closest("[data-newc]")) {
      return;
    }
    fieldKeys(e, field, field);
  });
  // **The summary at the keyboard** (the summary and editor design's goal 7): on a line, ↑ and ↓
  // move to the line before or after it in the summary's order, past the lines the find box dims;
  // Enter opens its setting and puts the editor's first field in focus (`firstField`). Esc in a
  // field with no draft leaves the field (`fieldKeys`), and a second Esc returns to its line (the
  // design's call), `leftFrom` the setting it left.
  var leftFrom = null;
  // **Esc in a box's `<select>`** (a drawn setting's shape; the pop-out revision's whole-build
  // review, M3): it leaves the select, and a second Esc returns to the setting's line, as from a
  // field (`fieldKeys`).
  document.addEventListener("keydown", function (e) {
    var field = e.target;
    if (e.key !== "Escape" || !field || !field.matches || !field.matches(inCards(".box select"))) {
      return;
    }
    e.preventDefault();
    field.blur();
    leftFrom = nameOf(field.closest(".box"));
  });
  function firstField(root) {
    var editor = root.querySelector(":scope > .editing");
    var shown = editor ? Array.prototype.filter.call(editor.children, function (child) {
      return !child.hidden && !child.classList.contains("placeholder");
    })[0] : null;
    if (!shown) { return null; }
    return Array.prototype.filter.call(shown.querySelectorAll("input, select, textarea"), function (one) {
      return !one.disabled && one.type !== "hidden" && one.getClientRects().length > 0;
    })[0] || null;
  }
  document.addEventListener("keydown", function (e) {
    if (e.metaKey || e.ctrlKey || e.altKey) { return; }
    var line = e.target && e.target.closest ?
      e.target.closest(inCards(".summary .line[data-open]") + ", #pinned > .line[data-open]") : null;
    if (line && (e.key === "ArrowDown" || e.key === "ArrowUp")) {
      e.preventDefault();
      var summary = line.closest(".summary");
      var lines = Array.prototype.filter.call(summary.querySelectorAll(".line[data-open]"), function (one) {
        return one === line || !one.classList.contains("nofind");
      });
      var next = lines[lines.indexOf(line) + (e.key === "ArrowDown" ? 1 : -1)];
      if (next) { next.focus(); }
      return;
    }
    if (line && e.key === "Enter") {
      e.preventDefault();
      var name = line.getAttribute("data-open");
      var pinned = line.parentNode === el("pinned");
      if (pinned) { openPinned(name); } else { openSetting(name); }
      var into = firstField(pinned ? el("pinned-params") : line.closest(CARDS.join(", ")));
      if (into) { into.focus(); }
      return;
    }
    // The second Esc, its target the page itself: the first, whose target was the field, has
    // just left it (`fieldKeys`) and comes here too.
    if (e.key === "Escape" && leftFrom !== null &&
        (e.target === document.body || e.target === document.documentElement)) {
      // Its line on the tab shown: Runtime's pinned line, or its own tab's.
      var back = [pinnedLine(leftFrom)].concat(Array.prototype.slice.call(linesOf(leftFrom))).filter(
        function (one) { return one && one.getClientRects().length; })[0];
      leftFrom = null;
      if (back && back.getClientRects().length) { e.preventDefault(); back.focus(); }
    }
  });
  // **Closing the page with drafts asks once** (the console interface design's call): the
  // browser's own question; nothing else keeps a draft past a reload.
  window.addEventListener("beforeunload", function (e) {
    if (!Object.keys(drafts).length) { return undefined; }
    e.preventDefault();
    e.returnValue = "";
    return "";
  });
  el("mark-note").addEventListener("keydown", function (e) {
    if (e.key === "Enter") { e.preventDefault(); closeNote(el("mark-note").value.trim()); }
    else if (e.key === "Escape") { e.preventDefault(); closeNote(""); }
  });
  el("stop-yes").addEventListener("click", function () {
    el("stop-confirm").hidden = true;
    post({ kind: "stop" });
  });
  el("stop-no").addEventListener("click", function () { el("stop-confirm").hidden = true; });
  if (el("rename")) { el("rename").addEventListener("click", function () { askName(); }); }
  el("sched-set").addEventListener("click", function () {
    var kind = el("sched-kind").value;
    var raw = el("sched-value").value.trim();
    var request = { kind: "schedule" };
    if (kind === "clock") { request.at = raw; }
    else if (kind === "trials") { request.trials = Number(raw); }
    else { request.ml = Number(raw); }
    post(request);
  });
  el("dn-ok").addEventListener("click", openSession);
  el("dn-cancel").addEventListener("click", function () { el("dlg-new").hidden = true; });
  el("dlg-new").addEventListener("keydown", function (e) {
    if (e.key === "Escape") { el("dlg-new").hidden = true; }
  });
  el("end-yes").addEventListener("click", function () {
    var button = el("end-actions").querySelector('[data-cmd="end"]');
    var returned = el("end-return").value.trim();
    el("end-confirm").hidden = true;
    if (!button) { tell("not sent: no session is open to end", "crit"); return; }
    var request = { kind: "end", session_id: button.getAttribute("data-session"), returned: returned === "" ? null : returned, confirm: false };
    if (returned !== "") { lastEnd = Object.assign({}, request); }
    post(request);
  });
  el("end-no").addEventListener("click", function () { el("end-confirm").hidden = true; });
  el("ret-yes").addEventListener("click", function () {
    var returned = el("ret-at").value.trim();
    if (!returned) { tell("not sent: give the time the animal went back into its home cage, or now", "crit"); return; }
    var request = { kind: "end", session_id: returnFor, returned: returned, confirm: false };
    el("return-form").hidden = true;
    lastEnd = Object.assign({}, request);
    post(request);
  });
  el("ret-no").addEventListener("click", function () { el("return-form").hidden = true; });
  el("amend-yes").addEventListener("click", function () {
    el("amend-form").hidden = true;
    if (!lastOpen) { tell("not sent: this page sent no departure to amend", "crit"); return; }
    post(Object.assign({}, lastOpen, { answer: "amend", amend_to: el("amend-to").value.trim(), amend_reason: el("amend-why").value.trim() }));
  });
  el("amend-no").addEventListener("click", function () { el("amend-form").hidden = true; });
  setInterval(check, 1000);
  el("close").addEventListener("click", function () {
    closed = true;
    if (source) { source.close(); }
    say("");
    el("gone").hidden = false;
  });
  el("reconnect").addEventListener("click", function () {
    if (source) { source.close(); }
    open();
  });
  if (signinPage) {
    if (el("signin")) { el("signin").addEventListener("click", startSignIn); }
    if (el("signout")) { el("signout").addEventListener("click", signOut); }
    document.addEventListener("visibilitychange", function () {
      if (!document.hidden && signin && lockHeld && signin.expires - Date.now() < RENEW_BEFORE_MS) { renew(); }
    });
    applySignIn();
    finishSignIn().then(function (exchanged) {
      if (exchanged || !signin) { return; }
      if (!signin.id) { signin.id = random(16); writeStore(SIGNIN_KEY, signin); }
      var id = signin.id;
      return holdLock(id).then(function (mine) {
        if (!signin || signin.id !== id) { return; }  // signed out, or in again, during the wait
        if (!mine) {
          // A copy of another tab's sign-in: forgotten here and never signed out, which
          // would end it in the tab it belongs to (b2b-ready §4.5).
          dropSignIn(DUPLICATE);
          return;
        }
        armLapse();
        // A tab reloaded after its hour renews first; the stored token is not asked about.
        if (signin.expires - Date.now() < FRESH_FOR_MS) { return renew(); }
        return whoami(true);
      });
    }).catch(function () {
      tell("could not reach this rig to confirm the sign-in", "crit");
    }).then(applySignIn);
    if (!body.getAttribute("data-token-endpoint")) {
      // No sign-in could be offered: this rig could not check one when the page was made.
      // Ask it again until it can, then reload into the sign-in (b2b-ready §4.6).
      var recheck = function () {
        fetch("/whoami", {
          method: "POST",
          cache: "no-store",
          headers: { "Content-Type": "application/json" },
          body: "{}"
        }).then(answerOf).then(function (answer) {
          if (answer.reason === "no_token") { window.location.reload(); return; }
          setTimeout(recheck, RECHECK_MS);
        }, function () { setTimeout(recheck, RECHECK_MS); });
      };
      setTimeout(recheck, RECHECK_MS);
    }
  }
  showName();
  demoFrame();
  startBoxes();
  open();
})();
"""


def page(
    parts: dict[str, str],
    *,
    stale_after_s: float,
    nonce: str,
    can_write: bool = False,
    signin: SignIn | None = None,
    https_page: bool = False,
    https_off: str | None = None,
    can_gaze: bool = False,
) -> str:
    """The whole document, every pane already rendered into it, so it reads before
    its stream has opened (spec §4.3).

    `parts` is `fragments(...)`; each fills the element whose id is its key, the id
    the stream's events swap by. A missing key raises `KeyError`: a page with a pane
    left blank is a bug to see, not a page to serve. `nonce` is the one in the
    Content-Security-Policy `wlx serve` sends with this response; the one script
    carries it. `stale_after_s` goes to the script as `data-stale-after`.

    **The controls (P4d-2b b2a, spec §5.2)**: the control bar's buttons are the
    `controls` fragment, and around it are the parts no frame changes -- the name,
    the last command's answer, the stop confirm, the mark's note box and the
    scheduled-stop form -- static, so a frame never replaces what a person is typing.
    `can_write` is `View.can_write` for the browser this page is for: `False`
    disables those static controls here and tells the script (`data-can-write`); the
    fragments grey their own. Close and reconnect, and the tab radios, are b1's.
    **The session forms (P4d-2b b3a-2)**: the *New session* dialog, the end
    confirmation, the return and the amendment are static too, and so is the run's
    trial count; only the task and subject selects' options are fragments (the b3a-2
    plan, decision 11).
    **The https page (b2b spec §4)**: with `signin`, the static controls carry `disabled
    data-signin` for the script to enable, the name is replaced by the sign-in and sign-out
    buttons, and the sign-in's addresses ride on `<body>`. `https_page` is for the plain-http
    page of a rig that has one: a LAN viewer's greyed controls say where else they work.
    `https_off` is why the rig's https page is off (b2b-ready §3.1), shown on the box's own
    page only.
    **A demo (demo mode §4.3; its plan's Task 9)**: the demo screen is static, so no frame
    replaces a drawing or the pointer's dot, and it stands in the right column in place of the
    replica pane, shown while the frame says `demo` (its `demo-tag` fragment says DEMO; the script
    switches the two as frames arrive). `can_gaze` is `View.can_gaze`: whether this console has a
    demo's gaze endpoint, without which no page steers here (`data-can-gaze`); a page that may not
    write steers nothing and draws no dot. `GAZE_EVERY_MS` goes to the script as
    `data-gaze-every-ms`.
    **Drafts (the console interface rework's Task 6)**: the bar the script shows while any box
    holds an edit not sent, "N edits not sent: ... · Discard all · Apply all", is static, fixed at
    the foot of the window so its coming and going moves nothing under the pointer; Apply all
    sends at most `APPLY_ALL_LIMIT` changes as one act (`data-apply-all-limit`).
    """
    p = {key: parts[key] for key in FRAGMENT_IDS}
    demo = bool(p["demo-tag"])
    # **Who the controls act as** (the console interface rework's Task 8): what can be done about
    # it stands in the bar -- read-only, with *sign in* where there is one -- and who is signed in,
    # or the box's name, with the session's details behind *session* (`who_session`).
    who_session = ""
    if can_write:
        off = ""
        attrs = ""
        who = ""
        who_session = (
            '<span class="who">name <b id="who">not given yet</b> <button class="btn small" '
            'id="rename" type="button">change</button></span>'
        )
    elif signin is not None:
        off = f' disabled data-signin title="{_e(SIGN_IN_FIRST)}"'
        attrs = (
            f' data-signin="1" data-authorize="{_e(signin.authorize or "")}"'
            f' data-token-endpoint="{_e(signin.token_endpoint or "")}"'
            f' data-client="{_e(signin.client_id)}" data-page="{_e(signin.page)}"'
            f' data-resource="{_e(signin.resource)}" data-retry-ms="{SIGNIN_RETRY_MS}"'
            f' data-recheck-ms="{KEYS_RECHECK_MS}" data-lock-wait-ms="{SIGNIN_LOCK_WAIT_MS}"'
        )
        if signin.token_endpoint is None:
            who = (
                '<span class="who" id="mode">read-only · <span class="nm">'
                + _e(signin.unavailable or "")
                + "</span></span>"
            )
        else:
            who = (
                '<span class="who" id="mode"><span class="so">read-only · <button class="btn small '
                'primary" id="signin" type="button">sign in with wl.works</button></span></span>'
            )
            who_session = (
                '<span class="who"><span class="si">controls act as <b id="member"></b> · <button '
                'class="btn small" id="signout" type="button">not you? sign out</button></span></span>'
            )
    else:
        why = CONTROLS_ELSEWHERE if https_page else CONTROLS_AT_THE_BOX
        off = f' disabled title="{_e(why)}"'
        attrs = ""
        who = f'<span class="who">read-only · <span class="nm">{_e(why)}</span></span>'
    off_line = (
        f'\n  <div class="banner warn" id="https-off" role="status">{_e(HTTPS_OFF)}: {_e(https_off)}</div>'
        if can_write and https_off is not None
        else ""
    )
    # Who may steer a demo from this page (demo mode §4.5): a page that may write, on a console
    # with the gaze endpoint; any other sees the drawing and no dot, and says why.
    if not can_gaze:
        steers = f'<p class="sub" id="demo-who">{_e(DEMO_NO_GAZE)}</p>'
    elif not can_write and signin is None:
        where = CONTROLS_ELSEWHERE if https_page else CONTROLS_AT_THE_BOX
        steers = f'<p class="sub" id="demo-who">{_e(DEMO_WATCHING)}: {_e(where)}</p>'
    else:
        steers = ""
    replica_hidden, demo_hidden = (" hidden", "") if demo else ("", " hidden")
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>xcon console</title>
<style>{_FONT_FACES}{_CSS}</style>
</head>
<body data-stale-after="{stale_after_s:g}" data-can-write="{int(can_write)}" data-apply-all-limit="{APPLY_ALL_LIMIT}" data-can-gaze="{int(can_gaze)}" data-gaze-every-ms="{GAZE_EVERY_MS}"{attrs}>
<div class="wrap">
  <header class="topbar glass" id="bar" aria-label="the run">
    <div class="barline">
      <span class="logo">{_LOGO}<span class="app">xcon</span></span>
      <span id="demo-tag">{p['demo-tag']}</span>
      <span id="state">{p['state']}</span>
      <span class="nums" id="bar-nums">{p['bar-nums']}</span>
      <div class="ctlrow" id="controls">{p['controls']}</div>
      {who}
      <span class="sent" id="sent" role="status"></span>
      <button class="btn small" id="session-btn" type="button" aria-controls="session" aria-expanded="false" title="{_e(SESSION_SAID)}">session ▾</button>
      <button class="xbtn" id="close" type="button" aria-label="close this page's stream" title="close this page's stream · the session keeps running on the box"><svg viewBox="0 0 12 12" aria-hidden="true"><path d="M2 2l8 8M10 2l-8 8" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg></button>
    </div>
    <div class="banner" id="stream" role="status" hidden></div>
    <div class="inline crit" id="stop-confirm" role="alertdialog" aria-label="confirm stop" hidden><span>stop at a trial boundary, after any commands already sent?</span><button class="btn danger" id="stop-yes" type="button">stop</button><button class="btn" id="stop-no" type="button">cancel</button></div>
    <div class="inline info" id="mark-form" role="dialog" aria-label="mark note" hidden><span>mark sent · note</span><input id="mark-note" maxlength="500" autocomplete="off" placeholder="Enter attaches it · Esc leaves the mark bare" aria-label="mark note"></div>
  </header>
  <section class="session" id="session" aria-label="the session">
    <div class="head glass">
      <div class="id" id="head-id">{p['head-id']}</div>
      <span class="spacer"></span>
      {who_session}
      <span class="presence" id="presence">{p['presence']}</span>
    </div>
    <div class="strip glass" role="region" aria-label="animal" id="strip">{p['strip']}</div>
    <div class="controlbar glass" aria-label="the next run">
      <label class="tsel" for="task-sel"><span class="k">Task</span><select id="task-sel" aria-label="task"{off}>{p['task-sel']}</select></label>
      <label class="tsel" for="plan-sel"><span class="k">Plan</span><select id="plan-sel" aria-label="plan"{off}>{p['plan-sel']}</select></label>
      <label class="tsel" for="run-trials"><span class="k">Trials</span><input class="field mono" id="run-trials" value="{RUN_TRIALS}" inputmode="numeric" autocomplete="off" aria-label="trials"{off}></label>
      <span id="pf-pill">{p['pf-pill']}</span>
      <span class="spacer"></span>
      <div class="inline" id="sched-form"><span>scheduled stop</span><select id="sched-kind" aria-label="stop when"{off}><option value="clock">at HH:MM</option><option value="trials">after N more presentations, drummed tries included</option><option value="fluid">after mL this session</option></select><input id="sched-value" autocomplete="off" aria-label="stop at"{off}><button class="btn small" id="sched-set" type="button"{off}>set</button></div>
    </div>
  </section>{off_line}
  <div class="banners" id="banners">{p['banners']}</div>
  <div class="inline info" id="amend-form" role="dialog" aria-label="amend the departure" hidden><span>amend the departure · the corrected time</span><input id="amend-to" autocomplete="off" placeholder="HH:MM, or 2027-01-13T22:40" aria-label="the corrected departure"{off}><span>why</span><input id="amend-why" maxlength="500" autocomplete="off" aria-label="why it is amended"{off}><span class="nm">your name is recorded with it</span><button class="btn small primary" id="amend-yes" type="button"{off}>send amendment</button><button class="btn small" id="amend-no" type="button">cancel</button></div>
  <div class="shell">
    <div class="main">
      <input type="radio" name="tab" id="t-runtime" checked>
      <input type="radio" name="tab" id="t-task">
      <input type="radio" name="tab" id="t-training">
      <input type="radio" name="tab" id="t-setup">
      <input type="radio" name="tab" id="t-warn">
      <input type="radio" name="tab" id="t-end">
      <div class="tabs" aria-label="console sections">
        <label class="tab" for="t-runtime">Runtime</label>
        <label class="tab" for="t-task">Task parameters</label>
        <label class="tab" for="t-training">Training</label>
        <label class="tab" for="t-setup">Setup</label>
        <label class="tab" for="t-warn">Warnings</label>
        <label class="tab" for="t-end">End of session</label>
      </div>
      <div class="panels">
        <div class="tabpanel" id="tp-runtime">
          <section class="panel glass pins" id="pinned-pane" aria-label="pinned settings" hidden><div class="top"><h2>Pinned</h2><span class="sub">{_e(PINNED_SAID)}</span></div><div class="params" id="pinned-params"><div class="summary" id="pinned"></div><div class="editing" id="pinned-editing"><div class="placeholder">{_e(PINNED_EMPTY)}</div></div></div></section>
          <section class="panel glass"><div class="top"><h2>Trials</h2></div><div id="rt-trials">{p['rt-trials']}</div></section>
          <section class="panel glass"><div class="top"><h2>This run</h2></div><div id="rt-work">{p['rt-work']}</div></section>
          <div class="panel glass" id="rt-shaping">{p['rt-shaping']}</div>
          <div class="cols c3">
            <div class="stack">
              <section class="panel glass"><div class="top"><h2>Still needed</h2></div><div id="rt-need">{p['rt-need']}</div></section>
              <section class="panel glass"><div class="top"><h2>Wrong?</h2></div><div id="rt-wrong">{p['rt-wrong']}</div></section>
            </div>
            <div class="stack"><section class="panel glass health"><div class="top"><h2>wl-works sees</h2></div><div id="rt-health">{p['rt-health']}</div></section></div>
            <div class="stack"><section class="panel glass"><div class="top"><h2>Changes</h2></div><div class="feed" id="rt-changes">{p['rt-changes']}</div></section></div>
          </div>
        </div>
        <div class="tabpanel" id="tp-task"><section class="panel glass"><div class="top tools"><input type="search" class="field find" id="pfind" placeholder="{_e(FIND_SAID)}" aria-label="{_e(FIND_SAID)}"><span class="nomatch" id="pfind-none" role="status" hidden>{_e(NO_MATCH)}</span><span class="sub">each box sends nothing until its Apply · staged until the next trial</span></div><div class="params" id="params">{p['params']}</div></section>
          <section class="panel glass"><div class="top"><h2>Moments of this run</h2>
            <span class="sub">a revert takes the task's settings and drawn ranges back to one</span>
            </div><div id="moments">{p['moments']}</div></section></div>
        <div class="tabpanel" id="tp-training">
          <section class="panel glass"><div class="top"><h2>Training</h2><span class="sub">on, frozen or the full task, staged until the next trial</span></div><div id="shaping">{p['shaping']}</div></section>
          <section class="panel glass train" id="rt-train" aria-label="training">{p['rt-train']}</section>
          <section class="panel glass"><div class="top tools"><h2>Training settings</h2><input type="search" class="field find" id="tfind" placeholder="{_e(FIND_SAID)}" aria-label="{_e(FIND_SAID)}"><span class="nomatch" id="tfind-none" role="status" hidden>{_e(NO_MATCH)}</span><span class="sub">staged until the next trial</span></div><div class="params" id="training-params">{p['training-params']}</div></section>
        </div>
        <div class="tabpanel" id="tp-setup">
          <section class="panel glass" id="pf-panel"><div class="top"><h2>Pre-flight</h2><span id="pf-sum">{p['pf-sum']}</span></div><div id="preflight">{p['preflight']}</div></section>
          <section class="panel glass"><div class="top"><h2>Session</h2></div><div id="setup">{p['setup']}</div></section>
        </div>
        <div class="tabpanel" id="tp-warn"><section class="panel glass"><div class="top"><h2>Warnings</h2></div><div id="warnings">{p['warnings']}</div></section></div>
        <div class="tabpanel" id="tp-end"><section class="panel glass"><div class="top"><h2>Summary</h2><div class="selrow" id="end-actions">{p['end-actions']}</div></div>
          <div class="inline crit" id="end-confirm" role="alertdialog" aria-label="confirm end session" hidden><span>{_e(END_CONFIRM)}</span><span>→cage at</span><input id="end-return" autocomplete="off" placeholder="now, HH:MM, or blank for later" aria-label="the return to the home cage"{off}><button class="btn small danger" id="end-yes" type="button"{off}>end session</button><button class="btn small" id="end-no" type="button">cancel</button></div>
          <div class="inline info" id="return-form" role="dialog" aria-label="the return to the home cage" hidden><span>the return to the home cage · session <b class="mono" id="ret-session"></b> · →cage at</span><input id="ret-at" autocomplete="off" placeholder="now, HH:MM, or 2027-01-13T22:40" aria-label="the return to the home cage"{off}><button class="btn small primary" id="ret-yes" type="button"{off}>record return</button><button class="btn small" id="ret-no" type="button">cancel</button></div>
          <div id="end">{p['end']}</div></section></div>
      </div>
    </div>
    <aside class="aside" aria-label="always shown">
      <section class="panel glass" id="replica-pane"{replica_hidden}><div class="top"><h2>Replica</h2><span class="later">V11</span></div><div class="screen">replica · V11</div></section>
      <section class="panel glass demo-pane" id="demo-pane" aria-label="demo screen" data-steer=""{demo_hidden}>
        <div class="top"><h2>Demo screen</h2><span class="sub">F or a click: full window · Esc closes</span></div>
        <div class="demo-screen" id="demo-screen" role="button" tabindex="0" aria-label="the demo's screen: F or a click opens it full-window, Escape closes it">
          <div class="demo-drawing" id="demo-drawing"></div>
          <div class="demo-none" id="demo-none">{_e(DEMO_NO_SCREEN)}</div>
          <span class="demo-dot" id="demo-dot" hidden></span>
        </div>
        <div class="demo-bar"><span id="demo-under">{p['demo-under']}</span><span class="sent" id="demo-steer" role="status"></span><span class="sub demo-esc">Esc closes the full window</span></div>
        {steers}<details class="demo-fold" id="demo-fold"><summary>{_e(DEMO_FOLD_SAID)}</summary><div class="demo-keys" id="demo-keys">{demo_keys(())}</div></details>
      </section>
      <section class="panel glass"><div class="top"><h2>Subject display</h2></div><div class="screen">subject display · no source yet</div></section>
      <div class="duo">
        <section class="panel glass"><h2>Sound</h2><span class="nm">sound · not measured</span></section>
        <section class="panel glass"><h2>Display</h2><span class="nm">display · not measured</span></section>
      </div>
    </aside>
  </div>
</div>
<div class="scrim" id="dlg-new" hidden>
  <div class="dialog glass" role="dialog" aria-modal="true" aria-labelledby="dn-h">
    <h2 id="dn-h">New session</h2>
    <div id="dn-demo">{p['dn-demo']}</div>
    <div class="grid">
      <label class="sub" for="dn-subject">subject</label><select id="dn-subject"{off}>{p['dn-subject']}</select>
      <label class="sub" for="dn-deployment">deployment</label><select id="dn-deployment" required{off}><option value="">choose the deployment</option><option value="rig_fixed">head-fixed</option><option value="rig_chaired">chaired</option></select>
      <label class="sub" for="dn-view">setup</label><select id="dn-view"{off}><option value="direct">direct view</option><option value="stereoscope">stereoscope</option></select>
      <label class="sub" for="dn-kind">for</label><select id="dn-kind"{off}><option value="">choose what this session is for</option><option value="training">training</option><option value="piloting">piloting</option><option value="recording">recording</option></select>
      <label class="sub" for="dn-left">←cage at</label><input class="field mono" id="dn-left" autocomplete="off" placeholder="HH:MM, or 2027-01-13T22:40"{off}>
      <label class="sub" for="dn-id">id</label><input class="field mono" id="dn-id" autocomplete="off" placeholder="as wlx run --session-id takes it"{off}>
      <label class="sub" for="dn-given">given today, mL</label><input class="field mono" id="dn-given" inputmode="decimal" autocomplete="off" placeholder="blank when not known"{off}>
    </div>
    <div id="dn-warnings">{p['dn-warnings']}</div>
    <div id="dn-msg" class="sub" role="status"></div>
    <div class="end"><button class="btn" id="dn-cancel" type="button">cancel</button><button class="btn primary" id="dn-ok" type="button"{off}>open session</button></div>
  </div>
</div>
<div class="drafts glass" id="drafts" role="status" aria-label="edits not sent" hidden><span class="say" id="drafts-say"></span><button class="btn small" id="drafts-discard" type="button">Discard all</button><button class="btn small primary" id="drafts-apply" type="button">Apply all</button></div>
<div class="scrim" id="gone" role="dialog" aria-modal="true" aria-labelledby="gone-h" hidden>
  <div class="dialog glass">
    <h2 id="gone-h">Disconnected</h2>
    <p>disconnected · the session keeps running on the box</p>
    <div class="actions"><button class="btn primary" id="reconnect" type="button">reconnect</button></div>
  </div>
</div>
<script nonce="{_e(nonce)}">{_SCRIPT}</script>
</body>
</html>
"""
