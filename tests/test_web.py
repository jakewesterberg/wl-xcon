"""The browser console's panes (P4d-2b spec §4.2, §4.4): pure, and tested the way
`cli.render` is.

The assertions that matter most are the ones a simplified pane would break: fluid
session and the supplement never dropped (the zero-reward ruling rests on their being
visible, S9a §9), nothing unmeasured ever shown as 0, and no telemetry string ever
reaching the page as markup.
"""

from __future__ import annotations

import fnmatch
import html
import re
import time
import tomllib
from dataclasses import replace
from importlib import resources
from pathlib import Path

import pytest

from _frames import frame, idle, view
from wl_xcon.actor import Box, Member
from wl_xcon.cli import _clock, _local
from wl_xcon.findings import SESSION_KINDS
from wl_xcon.link import (
    NOTE_LIMIT,
    BackBlock,
    Bars,
    ConditionRow,
    Control,
    Counts,
    Decline,
    MomentRow,
    NextBlock,
    ParamRow,
    Performance,
    Pooled,
    Preflight,
    PreflightItem,
    Question,
    Refused,
    ScheduledStop,
    SetParameter,
    ShortfallRow,
    StaircaseRow,
    Staged,
    Stranded,
    Suggestion,
    WarningRow,
)
from wl_xcon import demoscreen, link, pointer, service, web
from wl_xcon.serve import BadCommand, parse_command
from wl_xcon.task import Polar
from wl_xcon.warnlist import HEAD_FREE, UNLISTED
from wl_xcon.web import (
    _CSS,
    COLOR_APPROXIMATE,
    _SCRIPT,
    _clock_time,
    CONTROLS_AT_THE_BOX,
    CONTROLS_ELSEWHERE,
    APPLY_ALL_LIMIT,
    END_CONFIRM,
    FONTS,
    FRAGMENT_IDS,
    LEGEND,
    NO_MARK_ENDPOINT,
    PLAIN_RUN,
    REWARD_ONLY_PAUSED,
    RUN_TRIALS,
    SIGN_IN_FIRST,
    KEYS_RECHECK_MS,
    SIGNIN_LOCK_WAIT_MS,
    SIGNIN_RETRY_MS,
    SignIn,
    _gate,
    font_bytes,
    fragments,
    page,
    _who,
    DEMO_KEYS_WHERE,
    DEMO_LIMITS,
    DEMO_STRANDED,
    GAZE_EVERY_MS,
    NO_GAZE,
    NO_REFERENCE,
    REFERENCE,
    demo_keys,
)

LIMIT = "out_of_cage: subject 'A' has been out of its cage 28801 s against a ceiling of 28800"

STATES = {
    "running": {},
    "ended by the limit": {"stop_kind": "limit", "stopped_because": LIMIT},
    "awaiting return": {
        "stop_kind": "completed",
        "stopped_because": "every block is finished",
        "phase": "awaiting_return",
    },
    "returned": {
        "stop_kind": "operator",
        "stopped_because": "stopped by jake",
        "phase": "closed",
    },
    "fault": {
        "stop_kind": "fault",
        "stopped_because": "fault, session aborted: RuntimeError: solenoid did not answer",
    },
    "cage-side": {
        "deployment": "cage_side",
        "out_of_cage_seconds": None,
        "out_of_cage_limit_s": None,
        "chair_seconds": None,
    },
}


# --- never dropped -------------------------------------------------------------


@pytest.mark.parametrize("state", sorted(STATES))
def test_fluid_session_and_the_supplement_are_never_dropped(state):
    """The zero-reward ruling (PI, 2026-09-20) rests on both being visible, and the
    strip does not carry fluid session (spec §4.0; the supplement returned to it with
    the session-levels spec §6) -- so Runtime and End of session both must, in every
    state, a zero volume included."""
    parts = fragments(
        frame(fluid_session_ml=0.0, shortfall_ml=3.21, **STATES[state]), view()
    )

    for pane in ("rt-work", "end"):
        assert "0.00 mL" in parts[pane], (state, pane)
        assert "3.21" in parts[pane], (state, pane)


def test_an_unknown_supplement_is_a_sentence_not_a_zero():
    parts = fragments(frame(shortfall_ml=None, fluid_today_ml=None), view())

    for pane in ("rt-work", "end"):
        assert "unknown: the day's prior total was not supplied" in parts[pane]


@pytest.mark.parametrize(
    "state", ["running", "ended by the limit", "awaiting return", "returned", "fault"]
)
def test_the_out_of_cage_time_is_never_dropped(state):
    parts = fragments(frame(**STATES[state]), view())

    assert "1:23:45" in parts["strip"]
    assert "1:23:45" in parts["end"]


def test_a_cage_side_session_says_it_has_no_out_of_cage_clock_rather_than_zero():
    parts = fragments(frame(**STATES["cage-side"]), view())

    assert (
        '<span class="k">back to cage</span><span class="n"><span class="nm">cage-side</span>'
        '</span><span class="n"></span><span class="x">no limit</span>' in parts["strip"]
    )
    assert "cage-side · no out-of-cage interval" in parts["end"]
    assert "0:00" not in parts["strip"] + parts["end"]


def test_the_duration_warning_is_never_dropped():
    warning = "out_of_cage: subject 'A' has 900 s left of its 28800 s out of the cage"

    parts = fragments(frame(duration_warning=warning), view())

    assert html.escape(warning, quote=True) in parts["banners"]


def test_the_refusals_that_fell_off_the_cap_are_counted_before_the_rows():
    parts = fragments(
        frame(refusals=(Refused("fx_hold", Box("sam"), "not declared"),), refusals_dropped=417),
        view(),
    )

    changes = parts["rt-changes"]
    assert "417 earlier refusal(s) not shown" in changes
    assert changes.index("417 earlier") < changes.index("fx_hold")


def test_a_refusal_from_nobody_names_no_one():
    """b2b spec §6: a refusal with no readable sender behind it -- a packet that named
    none, a mark with no session open -- carries `None`, and the feed names no one
    rather than printing it."""
    nobody = (Refused("mark", None, "no session is open, so the mark was not recorded"),)

    for shown in (
        fragments(frame(refusals=nobody), view())["rt-changes"],
        fragments(idle(refusals=nobody), view())["rt-changes"],
    ):
        assert "mark: no session is open" in shown
        assert "None" not in shown


# --- never a zero for what nothing measured -----------------------------------


def test_nothing_unmeasured_is_rendered_as_zero():
    parts = fragments(
        frame(fluid_today_ml=None, last_reward_at=None), view(trials_per_min=None)
    )

    for name in ("dropped frames", "tracker staleness", "RHX margin"):
        assert re.search(
            rf'<span>{name}</span><span class="nm">not measured</span>', parts["rt-wrong"]
        ), name
    strip = parts["strip"]
    assert "unknown" in strip and "none yet" in strip
    # A rate `wlx serve` has not yet derived is left out, as mockup v13 leaves it:
    # never 0.0/min.
    assert "/min" not in strip
    assert "0 s" not in strip


def test_the_time_since_the_last_reward_is_the_frames_instant_aged_by_serve():
    """Ledger Ruling 1 (2026-09-27): the frame's own instant less the reward's, both on
    the session's anchored clock, plus the seconds `wlx serve` has held the frame --
    30 s and 12 s here, so neither alone reads 42."""
    parts = fragments(
        frame(wall_at=1_700_000_030.0, last_reward_at=1_700_000_000.0),
        view(frame_age_s=12.0),
    )

    assert (
        '<span class="k">last reward</span><span class="n">42 s ago</span>' in parts["strip"]
    )


@pytest.mark.parametrize(
    "at", [float("nan"), float("inf"), float("-inf")], ids=["nan", "inf", "-inf"]
)
def test_a_reward_instant_that_is_not_a_number_reads_unknown_not_a_crash(at):
    """m1: `welfare.deliver` stores a non-finite `wall_now` rather than refusing it
    (its docstring: it bounds nothing), so a frame can carry one. `health.ago` raised
    on it, so every stream died and reconnected in a loop and `GET /` failed, while
    `/health` said `ok`. Every other pane still renders."""
    parts = fragments(frame(last_reward_at=at), view())

    assert (
        '<span class="k">last reward</span>'
        '<span class="n"><span class="nm">unknown</span></span>' in parts["strip"]
    )
    assert tuple(parts) == FRAGMENT_IDS


@pytest.mark.parametrize("at", [1e20, 1e18, -1e18], ids=["past-time_t", "1e18", "-1e18"])
def test_a_finite_instant_this_host_cannot_show_is_a_dash_not_a_crash(at):
    """The b2a final review: `_clock_time` refused only NaN and inf, and a finite
    instant `time.localtime` cannot convert raised out of `fragments` -- on this
    macOS host, 2026-09-28, `OverflowError` for 1e20 and `OSError` for +-1e18 --
    which ends every stream and `GET /`, as m1's non-finite reward did. A pause's
    instant and a control's are both on the wire."""
    parts = fragments(
        frame(paused_at=at, controls=(Control("pause", Box("jake"), at, "paused before trial 3"),)),
        view(),
    )

    assert parts["state"] == (
        '<span class="pill warn" data-state="paused">paused · since —</span>'
    )
    assert f"— · paused before trial 3 · {_who(Box('jake'))}" in parts["rt-changes"]
    assert tuple(parts) == FRAGMENT_IDS


def test_out_of_cage_time_with_no_published_limit_shows_the_clock_alone():
    """A rig session whose frame carries its out-of-cage time but no limit shows the
    clock alone, and says no limit was published: no deadline and no time left, since
    neither can be worked out without one."""
    strip = fragments(frame(out_of_cage_limit_s=None), view())["strip"]

    assert (
        '<span class="k">back to cage</span><span class="n">1:23:45</span>'
        '<span class="n"></span><span class="x">out · no limit published</span>' in strip
    )
    assert '<span class="n">by ' not in strip and " left" not in strip


# --- counts, ticks, and the strip's arithmetic ----------------------------------


def test_the_working_pane_keeps_every_count_unrolled():
    """The strip's rollup is the strip's alone: this pane counts each outcome as it
    occurred, as `/health` does."""
    work = fragments(
        frame(
            trial_index=10,
            outcomes={"correct": 3, "correct_reject": 2, "no_fixation": 5},
        ),
        view(),
    )["rt-work"]

    assert '<span>correct</span><span class="num">3</span>' in work
    assert '<span>correct_reject</span><span class="num">2</span>' in work
    assert '<span>correct</span><span class="num">5</span>' not in work


def test_the_fluid_bar_is_today_over_the_floor():
    strip = fragments(frame(fluid_today_ml=61.25, floor_ml=250.0), view())["strip"]

    assert 'style="width:24.5%"' in strip
    assert "61.25" in strip and "/ 250.00 mL" in strip


def test_counts_are_grouped_by_family_with_no_rollup():
    work = fragments(
        frame(outcomes={"correct": 3, "early_response": 1, "no_fixation": 2}), view()
    )["rt-work"]

    assert "<h3>Target</h3>" in work and "<h3>No engagement</h3>" in work
    assert '<span>correct</span><span class="num">3</span>' in work
    assert '<span>early_response</span><span class="num">1</span>' in work
    assert '<span class="num">4</span>' not in work, "a family total is back"


def test_an_outcome_this_build_does_not_know_is_shown_not_dropped():
    """Review Focus 3: a newer `taskd` may send an outcome this `Outcome` lacks."""
    parts = fragments(
        frame(
            outcomes={"from_a_newer_taskd": 5},
            recent_outcomes=("from_a_newer_taskd", "hang"),
        ),
        view(),
    )

    assert "<h3>Other</h3>" in parts["rt-work"]
    assert "from_a_newer_taskd" in parts["rt-work"]
    assert 'class="tk f-other" title="from_a_newer_taskd"' in parts["rt-trials"]
    assert 'class="tk f-hang" title="hang"' in parts["rt-trials"]


def test_the_ticks_are_sixty_oldest_first_colored_by_family_with_a_legend():
    ticks = fragments(
        frame(recent_outcomes=("correct", "fixation_break", "wrong_target")), view()
    )["rt-trials"]

    assert ticks.count('<span class="tk') == 60
    assert 'class="tk f-target" title="correct"' in ticks
    assert 'class="tk f-breaks" title="fixation_break"' in ticks
    assert 'class="tk f-distractor" title="wrong_target"' in ticks
    assert ticks.index('title="correct"') < ticks.index('title="wrong_target"')
    for key, label in LEGEND:
        assert f'<i class="tk f-{key}"></i>{label}' in ticks


# --- the strip's two cells (session-levels spec §6) -----------------------------


def _no_run(phase):
    """A frame while no run goes: the session's counts alone (`taskd.Session.performance`).
    Named apart from b3a-2's `_between` below, which keeps `frame()`'s four levels."""
    return replace(
        frame(),
        phase=phase,
        performance=Performance(
            Counts({"correct": 30, "no_fixation": 10}, 0), None, None, None, None, None, None, None, None
        ),
    )


def test_the_strip_has_two_cells():
    assert fragments(frame(), view())["strip"].count('<div class="row">') == 2


def test_correct_trials_shows_the_session_its_task_this_run_and_this_block():
    strip = fragments(frame(), view(trials_per_min=12.0))["strip"]
    assert '30<span class="u"> / 40</span>' in strip and "75%" in strip
    assert "12.0 presentations/min" in strip
    assert "fixation_detection" in strip and "2 runs" in strip
    assert "this run" in strip and "run 3" in strip
    assert "block 27 · near" in strip


def test_correct_counts_correct_and_correct_reject_at_every_level():
    """The one rollup (PI, 2026-09-26), on each line."""
    perf = Performance(
        session=Counts({"correct": 3, "correct_reject": 2, "no_fixation": 5}, 0),
        task=Counts({"correct": 3, "correct_reject": 2, "no_fixation": 5}, 0),
        run=Counts({"correct": 3, "correct_reject": 2, "no_fixation": 5}, 0),
        block=Counts({"correct": 3, "correct_reject": 2, "no_fixation": 5}, 0),
        task_name="t", runs_of_task=1, run_in_session=1, block_in_session=1, block_type="b",
    )
    strip = fragments(replace(frame(), performance=perf), view())["strip"]
    assert strip.count("50%") == 4


def test_hangs_count_among_the_trials():
    perf = replace(frame().performance, session=Counts({"correct": 1}, 1))
    strip = fragments(replace(frame(), performance=perf), view())["strip"]
    assert '1<span class="u"> / 2</span>' in strip and "50%" in strip


def test_between_runs_one_line_says_so():
    """Review Focus 5 and plan ruling 4."""
    strip = fragments(_no_run("between_runs"), view())["strip"]
    assert '<span class="k">between runs</span>' in strip
    assert "this run" not in strip and "block" not in strip


def test_after_the_runs_one_line_says_no_run_is_going():
    strip = fragments(_no_run("awaiting_return"), view())["strip"]
    # The line's own name span: the fluid cell's reward note also says "no run going".
    assert '<span class="k">no run going</span>' in strip


def test_while_a_run_goes_the_last_reward_line_notes_what_a_correct_trial_pays():
    """Session-levels spec §6 and plan ruling 6: the last-reward line's note is
    `reward_correct`'s value in its row's own unit. The final review found
    `web._per_correct` neutered to `None` with every test passing."""
    running = frame(
        phase="running",
        stop_kind=None,
        params=(ParamRow("reward_correct", "mL", 0.0, 0.4, 0.15, True),),
    )

    strip = fragments(running, view())["strip"]

    assert (
        '<span class="k">last reward</span><span class="n">42 s ago</span>'
        '<span class="n"></span><span class="x">0.15 mL per correct</span>'
    ) in strip


def test_with_no_run_going_the_last_reward_line_says_so_in_its_own_note():
    """The last-reward line's own `x` span, not a bare substring: after the runs the
    performance cell's one line says "no run going" too
    (`test_after_the_runs_one_line_says_no_run_is_going`)."""
    strip = fragments(_no_run("awaiting_return"), view())["strip"]

    assert (
        '<span class="k">last reward</span><span class="n">42 s ago</span>'
        '<span class="n"></span><span class="x">no run going</span>'
    ) in strip


def test_before_the_first_trial_the_session_says_so_not_zero():
    """Its percentage would be 0/0, and neither `0%` nor `NaN` may stand in for a count
    nobody has made (the claim of the four-cell strip's test of this name)."""
    perf = Performance(Counts({}, 0), None, None, None, None, None, None, None, None)
    strip = fragments(replace(frame(), performance=perf, phase="between_runs"), view())["strip"]
    assert "no trials yet" in strip
    assert '<span class="u"> / 0</span>' not in strip
    assert "0%" not in strip and "NaN" not in strip


def test_a_run_before_its_first_trial_keeps_its_notes_and_has_no_block_yet():
    """A block opens with its first trial (plan ruling 1): until then its line is
    *block* and a dash. The run's line and its task's (the task's first run here) show
    a dash, no percentage of nothing, and keep their notes, "run 3" and "1 run" (spec
    §6, mockup v13; the controller's ruling in Task 6's review)."""
    perf = replace(
        frame().performance, task=Counts({}, 0), runs_of_task=1, run=Counts({}, 0),
        block=None, block_in_session=None, block_type=None,
    )
    strip = fragments(replace(frame(), performance=perf), view())["strip"]
    assert (
        '<span class="k">block</span><span class="n"><span class="u">—</span></span>'
        '<span class="n"></span><span class="x"></span>' in strip
    )
    assert (
        '<span class="k">this run</span><span class="n"><span class="u">—</span></span>'
        '<span class="n"></span><span class="x">run 3</span>' in strip
    )
    assert (
        '<span class="k">fixation_detection</span><span class="n"><span class="u">—</span></span>'
        '<span class="n"></span><span class="x">1 run</span>' in strip
    )
    assert "no trials yet" not in strip, "the session has trials; only its line says that"


def test_the_supplement_owed_is_on_the_strip():
    strip = fragments(replace(frame(), shortfall_ml=12.5), view())["strip"]
    assert "supplement" in strip and "12.50" in strip and "to reach the floor" in strip


def test_a_met_floor_says_so():
    strip = fragments(replace(frame(), shortfall_ml=0.0), view())["strip"]
    assert "floor met" in strip


def test_an_unknown_day_says_the_supplement_is_unknown():
    strip = fragments(replace(frame(), shortfall_ml=None, fluid_today_ml=None), view())["strip"]
    assert "unknown" in strip and "the day's prior total was not supplied" in strip


def test_back_to_cage_gives_the_deadline_the_time_out_and_the_time_left():
    """5025 s out of an 8 h limit (ruling 5): the deadline is the frame's wall instant
    less the time out plus the limit, as this host shows it."""
    f = replace(frame(), out_of_cage_seconds=5025.0, out_of_cage_limit_s=28_800.0, duration_warning=None)
    strip = fragments(f, view())["strip"]
    deadline = time.strftime("%H:%M", time.localtime(f.wall_at - 5025.0 + 28_800.0))
    assert f"by {deadline}" in strip
    assert f"{_clock(5025.0)} out · {_clock(28_800.0 - 5025.0)} left" in strip


def test_back_to_cage_warns_with_the_sessions_warning_and_is_critical_at_the_limit():
    warned = fragments(replace(frame(), duration_warning="30 min left"), view())["strip"]
    limited = fragments(replace(frame(), stop_kind="limit"), view())["strip"]
    assert 'class="k warn"' in warned and 'class="k crit"' in limited


def test_back_to_cage_past_the_limit_is_critical_and_says_so():
    """30,000 s out against an 8 h limit, the session ended and the return awaited:
    no time is left, so the line is critical whatever `stop_kind` says, and it says
    *past the limit* rather than a negative time left."""
    f = replace(
        frame(), phase="awaiting_return", stop_kind="completed",
        out_of_cage_seconds=30_000.0, out_of_cage_limit_s=28_800.0,
    )
    strip = fragments(f, view())["strip"]
    assert 'class="k crit"' in strip and "past the limit" in strip


def test_a_recorded_return_says_when():
    f = replace(frame(), returned_at=1_700_000_000.0, phase="closed")
    strip = fragments(f, view())["strip"]
    assert "at " + time.strftime("%H:%M", time.localtime(1_700_000_000.0)) in strip and "recorded" in strip


def test_a_cage_side_session_has_no_back_to_cage_clock():
    strip = fragments(replace(frame(), out_of_cage_seconds=None, out_of_cage_limit_s=None), view())["strip"]
    assert "cage-side" in strip and "no limit" in strip


# --- the header, the banners, and no session ------------------------------------


@pytest.mark.parametrize(
    ("overrides", "label", "state"),
    [
        ({}, "running", "running"),
        ({"stop_kind": "limit", "stopped_because": LIMIT}, "ended · limit", "ended"),
        (STATES["awaiting return"], "ended · completed · awaiting return", "ended"),
        (STATES["returned"], "ended · operator · returned", "ended"),
    ],
)
def test_the_state_pill_reads_phase_and_stop_kind(overrides, label, state):
    pill = fragments(frame(**overrides), view())["state"]

    assert f'data-state="{state}">{label}</span>' in pill


def test_with_no_frame_every_pane_says_so():
    parts = fragments(None, view(frame_age_s=None))

    assert tuple(parts) == FRAGMENT_IDS
    assert 'data-state="none"' in parts["state"]
    assert "no telemetry yet" in parts["banners"]
    for pane in ("head-id", "strip", "rt-trials", "rt-work", "rt-need", "params", "setup", "end"):
        assert "no session" in parts[pane], pane


def test_with_no_frame_and_no_refusal_the_page_names_the_endpoint_it_reads():
    """m4: *Waiting* used to assert that no session was publishing on the link, which
    this console cannot know. What it knows is that nothing has arrived on the PUB
    endpoint it reads, so that is what it says -- and *wl-works sees* says the same."""
    parts = fragments(None, view(frame_age_s=None, endpoint="tcp://10.0.0.7:5571"))

    assert (
        "no telemetry yet: no frame has arrived on tcp://10.0.0.7:5571"
        in parts["banners"]
    )
    assert "no session is publishing" not in parts["banners"]
    assert (
        "none attached · no frame has arrived on tcp://10.0.0.7:5571"
        in parts["rt-health"]
    )


def test_the_endpoint_is_escaped_wherever_the_page_names_it():
    parts = fragments(None, view(frame_age_s=None, endpoint=EVIL))

    text = "".join(parts.values())
    assert "<script" not in text
    assert EVIL not in text
    assert html.escape(EVIL, quote=True) in parts["banners"]


def test_the_header_carries_the_session_and_the_trial():
    head = fragments(frame(trial_index=41), view())["head-id"]

    for text in ("2027-01-14_01", ">A<", "rig_fixed", ">session<", 'data-trial="41">41<', "1:12:01"):
        assert text in head, text


def test_presence_says_this_box_or_lan_viewer_with_the_count():
    assert (
        fragments(frame(), view(on_box=True, lan_viewers=2))["presence"]
        == "<b>this box</b> · 2 LAN viewers"
    )
    assert (
        fragments(frame(), view(on_box=False, lan_viewers=1))["presence"]
        == "<b>LAN viewer</b> · 1 LAN viewer"
    )


def test_a_refused_frame_is_said_above_everything_else():
    """Review Focus 1: a frame this console could not read is said, first."""
    banners = fragments(
        frame(), view(rejected="a telemetry frame carried schema 6")
    )["banners"]

    assert banners.startswith('<div class="banner crit"><span class="tag">Refused</span>')
    assert "schema 6" in banners


def test_a_refusal_with_no_frame_held_says_so_and_nothing_else():
    """Ruling 11 (2026-09-27): with a refusal and no frame, the *Waiting* banner's
    "no session is publishing" is false -- one is, in a schema this console cannot
    read -- so only the refusal is said."""
    banners = fragments(
        None, view(frame_age_s=None, rejected="a telemetry frame carried schema 6")
    )["banners"]

    assert banners.startswith('<div class="banner crit"><span class="tag">Refused</span>')
    assert "Waiting" not in banners
    assert "no telemetry yet" not in banners


@pytest.mark.parametrize("held", [None, *sorted(STATES)])
def test_the_health_pane_features_a_refusal_as_health_does(held):
    """Ruling 11: the pane shows `/health`'s verdict and featured reading, so a
    refusal is on it too -- `degraded`, featured, unless a held frame's warning or
    fault outranks it -- and still with exactly one ◆."""
    found = None if held is None else frame(**STATES[held])
    pane = fragments(
        found, view(frame_age_s=None if found is None else 0.5, rejected="schema 6")
    )["rt-health"]

    assert pane.count("◆") == 1
    assert '<span class="l">Refused</span><span class="v">schema 6</span>' in pane
    if held == "fault":
        assert '<span class="pill crit">down</span>' in pane
    else:
        assert '<span class="pill warn">degraded</span>' in pane
    if held in (None, "running", "awaiting return", "returned", "cage-side"):
        assert '<span class="f">◆</span><span class="l">Refused</span>' in pane


def test_the_stop_reason_is_a_banner_and_ends_the_summary():
    parts = fragments(frame(**STATES["returned"]), view())

    assert "stopped by jake" in parts["banners"]
    assert "stopped by jake" in parts["end"]


# --- the read-only panes ----------------------------------------------------------


def test_parameters_show_value_range_ceiling_and_what_is_staged():
    params = fragments(
        frame(
            params=(
                ParamRow("fix_hold", "s", 0.1, 1.0, 0.3, False),
                ParamRow("reward_correct", "mL", 0.0, 0.4, 0.15, True),
                ParamRow("target_appearance", "", None, None, None, False),
                ParamRow("fix_window", "deg", None, 5.0, 2.0, False),
                ParamRow("shape", "", None, None, "penguin", False),
            ),
            staged=(Staged("fix_hold", 0.3, 0.4, Box("jake"), False),),
        ),
        view(),
    )["params"]

    assert params.count('<div class="box') == 5
    assert '<div class="box staged" data-card="fix_hold" ' in params
    assert f"staged → 0.40 by {_who(Box('jake'))}" in params
    assert '<span class="ceil">ceiling</span>' in params
    # Review fix round 1: the ceiling keeps its own decimals (`_significant`), unlike
    # `_num`'s two-decimal `staged →` figure just above -- 0.4, not 0.40.
    assert "welfare ceiling 0.4 mL" in params
    assert "0.10 to 1.00 s" in params
    assert "open to 5.00 deg" in params
    assert "no limit" in params  # "no declared range" until the console settings plan's Task 4
    assert "unset" in params
    assert "penguin" in params


def test_the_page_shows_the_stereoscopes_half_ipd():
    setup = fragments(frame(view="stereoscope", half_ipd_cm=1.6), view())["setup"]

    assert "the stereoscope, half-IPD 1.60 cm" in setup


def test_setup_names_the_configuration_and_what_has_no_source():
    setup = fragments(frame(allocation="", bounds_config=""), view())["setup"]

    assert "tasks/fixation_detection.py" in setup
    assert "provisional: none given" in setup
    assert '<dt>bounds config</dt><dd><span class="nm">not given</span></dd>' in setup
    assert setup.count("no source yet") == 1
    assert "<dt>display mode</dt><dd>direct view</dd>" in setup
    assert "250.00 mL" in setup and "8:00:00" in setup


def test_still_needed_lists_each_condition_and_its_count():
    need = fragments(frame(owed={"ecc 10": 18, "catch": 2}), view())["rt-need"]

    assert '<span class="mono">ecc 10</span><span class="num">18</span>' in need
    assert '<span class="mono">catch</span><span class="num">2</span>' in need


def test_still_needed_offers_to_clear_a_trial_of_each_condition_owing_one_while_a_run_runs():
    """The PI, 2026-10-11: "some way in the console to manually advance beyond or clear a specific
    trial in the count"; *clear the rest* beside it where a condition owes more than one (the
    science review's D5), while the training aid *clear* is on (the PI, 2026-10-18). A condition
    owing nothing has no button; nothing is offered once the run has ended, and away from where
    controls work each is grayed."""
    need = fragments(frame(owed={"near": 2, "far": 0, "mid": 1}, clearing=True), view())["rt-need"]
    ended = fragments(frame(owed={"near": 2}, stop_kind="completed", clearing=True),
                      view())["rt-need"]
    lan = fragments(frame(owed={"near": 2}, clearing=True), view(can_write=False))["rt-need"]

    one = '<button type="button" class="btn" data-cmd="clear" data-condition="near">clear one'
    assert one in need
    assert 'data-cmd="clear" data-condition="near" data-rest="1">clear the rest' in need
    assert 'data-condition="far"' not in need
    assert 'data-condition="mid">clear one' in need
    assert 'data-condition="mid" data-rest' not in need
    assert 'data-cmd="clear"' not in ended and 'data-cmd="drum"' not in ended
    assert 'data-cmd="training"' not in ended
    assert 'data-cmd="clear" data-condition="near" disabled' in lan


def test_still_needed_offers_no_clear_where_nothing_of_the_block_can_be_owed():
    """The engineering review's Minor 3: a plain "run N trials", whose every trial pays, owes
    nothing to move past, so *clear one* would only shorten it; the counts and the drumming
    switches stay."""
    need = fragments(frame(owed={"session": 30}, clearable=False, clearing=True), view())["rt-need"]

    assert 'data-cmd="clear"' not in need and '<span class="num">30</span>' in need
    assert 'data-cmd="drum"' in need


def test_still_needed_shows_each_shortfall_a_caps_flagged_as_possible_avoidance():
    """Engine spec §16.6: "its shortfall recorded, shown and flagged as possible avoidance"; one
    the rig made is named for the rig and not flagged (the engineering review's M4); a cleared one
    says who cleared it."""
    need = fragments(frame(shortfalls=(
        ShortfallRow("b", "near", 3, "cap", True, None, 12),
        ShortfallRow("b", "mid", 2, "rig", False, None, 15),
        ShortfallRow("b", "far", 1, "cleared", False, Box("jake"), 20),
    )), view())["rt-need"]

    assert ("3 short in b · possible avoidance: its failed repeats in a row reached its "
            "limit") in need
    assert ("2 short in b · its repeat limit was reached with tries the rig lost (a lost tracker "
            "or a fault): not flagged as avoidance") in need
    assert ('1 short in b · cleared by <span class="who-b">jake <span class="nm">(box, unverified)'
            in need)


@pytest.mark.parametrize(
    ("drumming", "said", "offered"),
    [(None, "not drumming", ["block", "run"]), ("block", "drumming this block", ["run", "off"]),
     ("run", "drumming this run", ["block", "off"])],
)
def test_still_needed_says_whether_trials_are_drummed_and_offers_the_other_switches(
        drumming, said, offered):
    """The PI, 2026-10-11: drumming switched on per block or run by the trainer."""
    need = fragments(frame(drumming=drumming), view())["rt-need"]

    assert f'<span class="nm">{said}</span>' in need
    assert re.findall(r'data-cmd="drum" data-scope="(\w+)"', need) == offered


def test_clear_is_offered_only_while_the_training_aid_is_on_beside_the_training_switches():
    """The PI, 2026-10-18: *clear* is a training aid, off by default, and offered only while it is
    on; a switch turns it on or off, and another sets how a percentage counts drummed answers
    (Task 14's `link.Training`)."""
    off = fragments(frame(owed={"near": 2}, rule="percentage"), view())["rt-need"]
    on = fragments(frame(owed={"near": 2}, clearing=True, first_answers=True, rule="percentage"),
                   view())["rt-need"]

    assert 'data-cmd="clear"' not in off
    assert ('<span class="nm">clear is off</span><button type="button" class="btn" '
            'data-cmd="training" data-setting="clear" data-on="1">switch clear on</button>') in off
    assert ('<span class="nm">a percentage counts every answer, drummed too</span>'
            '<button type="button" class="btn" data-cmd="training" data-setting="first_answers" '
            'data-on="1">the block\'s percentage: count first answers only</button>') in off
    assert 'data-cmd="clear" data-condition="near"' in on
    assert 'data-setting="clear" data-on="0">switch clear off' in on
    assert '<span class="nm">a percentage counts first answers only</span>' in on
    assert ('data-setting="first_answers" data-on="0">the block\'s percentage: '
            'count every answer') in on


def test_still_needed_shows_each_conditions_counts():
    """The PI, 2026-10-18: per condition, "trials and presentations; right, wrong, and percent right
    first time; owed, repeats placed, and moved past, with the possible-avoidance flag; drummed
    tries", and the failed run of its trial being drummed now. A condition with no trial yet has no
    percentage."""
    need = fragments(frame(owed={"near": 2, "far": 0}, conditions=(
        ConditionRow("near", 12, 15, 9, 4, 8, 2, 3, 1, True, 3, 2),
        ConditionRow("far", 0, 0, 0, 0, 0, 0, 0, 0, False, 0, 0))), view())["rt-need"]

    assert ('<div class="kv"><span class="nm">12 trials · 15 presentations · 9 right · 4 wrong · '
            '67% right first time · 3 repeats · 1 moved past (possible avoidance) · 3 drummed · '
            'failing 2 in a row</span></div>') in need
    assert ('<span class="nm">0 trials · 0 presentations · 0 right · 0 wrong · — right first time '
            '· 0 repeats · 0 moved past · 0 drummed</span>') in need


@pytest.mark.parametrize(("kind", "tone", "said"), [
    ("training", "info", "drumming and clear on: the record marks every trial"),
    ("recording", "warn", "drumming and clear on in a recording session, though training aids are "
                          "meant for training sessions: the record marks every trial"),
])
def test_a_standing_warning_says_a_training_aid_is_on_in_the_words_for_the_sessions_kind(
        kind, tone, said):
    """The PI, 2026-10-18: "a warning that training aids are on in the console", and in a piloting
    or recording session "a standing warning that a training aid is on in a non-training session".
    None while no aid is on, nor once the run has ended."""
    aids = ("drumming", "clear")
    on = fragments(frame(drumming="run", clearing=True, aids=aids, session_kind=kind),
                   view())["banners"]
    ended = fragments(frame(drumming="run", clearing=True, aids=aids, stop_kind="completed",
                            stopped_because="every block is finished"), view())["banners"]

    assert (f'<div class="banner {tone}"><span class="tag">Training aid</span><span>{said}'
            f'</span></div>') in on
    assert "Training aid" not in fragments(frame(), view())["banners"]
    assert "Training aid" not in ended


def test_the_strip_shows_right_first_time_beside_right_per_presentation_where_trials_were_drummed():
    """The PI, 2026-10-18, "Show both": "right first time (per trial, a trial and its drummed
    repeats one) and right per presentation (every try)". A level with drummed tries leads with
    right first time; one with none shows its one figure, as before."""
    perf = replace(frame().performance, run=Counts({"correct": 12, "wrong_target": 8}, 0,
                                                    drummed=6, right_drummed=4))
    strip = fragments(replace(frame(), performance=perf), view())["strip"]

    assert ('8<span class="u"> / 14</span></span><span class="n">57%</span>'
            '<span class="x">run 3 · right first time; 60% per presentation (12 / 20)</span>'
            ) in strip
    assert '30<span class="u"> / 40</span>' in strip, "the session's line, nothing drummed"


def test_working_counts_trials_with_the_presentations_beside_where_drumming_made_them_differ():
    """The PI, 2026-10-18: "The console would show both: trials (200) and presentations (e.g.
    260)" -- a trial and its drummed repeats are one trial (the controller's ruling I1). What
    counts presentations says so: the ticks, which list lines; the strip's rate; and the
    scheduled stop, which counts presentations, drummed tries included, as the PI kept it."""
    parts = fragments(frame(trials=20, trial_index=25), view(trials_per_min=12.0))
    plain = fragments(frame(), view())
    document = page(plain, stale_after_s=30.0, nonce="n0nce", can_write=True)

    assert ('<span class="big">20</span><span class="unit">trials · 25 presentations</span>'
            in parts["rt-work"])
    assert '<span class="big">40</span><span class="unit">trials</span>' in plain["rt-work"]
    assert "the last 3 of 25 presentations, oldest first" in parts["rt-trials"]
    assert "12.0 presentations/min" in parts["strip"]
    assert ('<option value="trials">after N more presentations, drummed tries included</option>'
            in document)


def test_the_pane_says_where_a_switch_changes_nothing_and_a_block_is_past_its_targets():
    """The controller's ruling M4: with *clear* on where nothing in the run can be cleared, the
    pane says so, and the first-answers switch, in a block whose rule is a streak, says it changes
    nothing there; and past a criterion block's targets it says it draws until the criterion is met
    (the smaller ruling)."""
    flat = fragments(frame(owed={"session": 30}, clearable=False, clearing=True), view())["rt-need"]
    streak = fragments(frame(rule="streak"), view())["rt-need"]
    past = fragments(frame(owed={"near": 0}, past_targets=True, rule="percentage"),
                     view())["rt-need"]

    assert '<span class="nm">clear is on, but nothing in this block can be cleared</span>' in flat
    assert ('<span class="nm">a percentage counts every answer, drummed too -- a streak counts '
            'every try, so this changes nothing in this block</span>') in streak
    assert ('<span class="nm">every target used up: drawing until the criterion is met</span>'
            in past)
    assert "drawing until" not in fragments(frame(), view())["rt-need"]
    # A shortfall row's condition name keeps its words whole in a narrow pane (minor 9).
    short = fragments(frame(shortfalls=(ShortfallRow("b", "ecc 10", 1, "cap", False, None, 2),)),
                      view())["rt-need"]
    assert '<span class="mono keep">ecc 10</span>' in short
    assert (".kv > .keep { overflow-wrap: normal; white-space: nowrap; flex-shrink: 0; }"
            in _document())
    # Only while a run is live: a stopped run draws nothing more.
    stopped = fragments(frame(owed={"near": 0}, past_targets=True, phase="stopped"), view())
    assert "drawing until" not in stopped["rt-need"]


def test_the_first_answers_switch_names_the_blocks_rule_and_says_where_it_changes_nothing():
    """Important 3 of Task 9's fix round: the switch acts only in a block whose rule is a
    percentage. A flat run has no rule, a streak judges every try; each says so, and a percentage
    block does not. The label names the block's percentage, not the strip's."""
    none = fragments(frame(rule=None), view())["rt-need"]
    streak = fragments(frame(rule="streak"), view())["rt-need"]
    percentage = fragments(frame(rule="percentage"), view())["rt-need"]

    nothing = "this block has no percentage rule, so this changes nothing here"
    assert f'<span class="nm">{nothing}</span>' in none
    assert nothing not in streak and nothing not in percentage
    assert "so this changes nothing in this block" in streak
    assert "changes nothing" not in percentage
    assert 'data-on="1">the block\'s percentage: count first answers only' in percentage
    on = fragments(frame(rule="percentage", first_answers=True), view())["rt-need"]
    assert 'data-on="0">the block\'s percentage: count every answer' in on


def test_the_health_pane_shows_what_wl_works_would_be_sent():
    pane = fragments(frame(duration_warning="warning text"), view())["rt-health"]

    assert '<span class="pill warn">degraded</span>' in pane
    assert pane.count("◆") == 1
    assert "warning text" in pane


# --- escaping ------------------------------------------------------------------

EVIL = "<script>alert(1)</script>\"'&"


def test_every_telemetry_string_is_escaped():
    """Review Focus 2: every string a frame carries -- and the refusal `wlx serve`
    adds -- is text on the page, in an element or an attribute, and never markup."""
    evil = frame(
        session_id=EVIL,
        subject=EVIL,
        block=EVIL,
        deployment=EVIL,
        stop_kind=EVIL,
        phase=EVIL,
        stopped_because=EVIL,
        duration_warning=EVIL,
        task=EVIL,
        allocation=EVIL,
        bounds_config=EVIL,
        outcomes={EVIL: 1, "correct": 2},
        owed={EVIL: 3},
        shortfalls=(ShortfallRow(EVIL, EVIL, 1, "cleared", False, Box(EVIL), 2),),
        clearable=True,
        recent_outcomes=(EVIL, "correct"),
        staged=(Staged(EVIL, 0.1, 0.2, Box(EVIL), False),),
        refusals=(Refused(EVIL, Box(EVIL), EVIL),),
        # A position's words too (schema 18, XC-401; the fix round's M4).
        params=(ParamRow(EVIL, EVIL, None, None, EVIL, False),
                ParamRow("pos", "deg", None, None, None, False, EVIL)),
        performance=replace(frame().performance, task_name=EVIL, block_type=EVIL),
        session_kind=EVIL,
        calibration=EVIL,
        warnings=(WarningRow(EVIL, EVIL, SESSION_KINDS, Box(EVIL), 1_700_000_000.0),),
    )
    # The idle frame's three kinds of row (schema 15): one no kind accepts, the listing
    # fault, and one a kind accepts, each with EVIL for its code and sentence.
    evil_idle = idle(warnings=(
        WarningRow(EVIL, EVIL, (), None, None),
        WarningRow(UNLISTED, EVIL, (), None, None),
        WarningRow(EVIL, EVIL, SESSION_KINDS, None, None),
    ))
    # `phase` is EVIL above, so the reward's unit, which the strip shows only while a
    # run goes (`_per_correct`), needs a running frame of its own.
    # It also draws what a live run with *clear* on draws: the condition's *clear* buttons and a
    # shortfall row whose reason is its own sentence, which are the strings escaped at `_need`.
    paying = frame(params=(ParamRow("reward_correct", EVIL, 0.0, 0.4, 0.15, True),),
                   drumming="run", aids=("drumming",), session_kind=EVIL,
                   owed={EVIL: 3}, clearing=True,
                   shortfalls=(ShortfallRow(EVIL, EVIL, 1, EVIL, False, None, 2),))

    text = "".join(fragments(evil, view(rejected=EVIL)).values()) + "".join(
        fragments(paying, view()).values()
    ) + "".join(fragments(evil_idle, view()).values())
    assert "no session kind accepts this" in text and "could not be listed" in text

    assert "<script" not in text
    assert EVIL not in text
    assert html.escape(EVIL, quote=True) in text


# --- the page (Task 8) --------------------------------------------------------------


def _document(**frame_overrides) -> str:
    return page(
        fragments(frame(**frame_overrides), view()), stale_after_s=30.0, nonce="n0nce"
    )


def test_the_page_holds_every_pane_in_the_element_its_stream_swaps():
    """On connect the page is already rendered (spec §4.3): each fragment sits in the
    element whose id the stream's events name, and each id is on the page once."""
    parts = fragments(frame(), view())
    document = page(parts, stale_after_s=30.0, nonce="n0nce")

    for key in FRAGMENT_IDS:
        assert document.count(f'id="{key}"') == 1, key
        assert re.search(
            rf'id="{re.escape(key)}"[^>]*>{re.escape(parts[key])}<', document
        ), key


def test_a_page_missing_a_pane_is_refused_not_rendered_blank():
    parts = fragments(frame(), view())
    del parts["strip"]

    with pytest.raises(KeyError):
        page(parts, stale_after_s=30.0, nonce="n0nce")


def test_the_one_script_carries_the_nonce_and_nothing_loads_from_elsewhere():
    """A lab host renders with no internet: the fonts are the box's own (PI,
    2026-09-26), and the page names no other host at all."""
    document = _document()

    assert document.count("<script") == 1
    assert '<script nonce="n0nce">' in document
    assert "<link" not in document
    assert "http://" not in document and "https://" not in document
    assert not re.search(r'(?:src|href|url)\s*[=(]\s*"?//', document)


def test_the_page_declares_each_bundled_font_and_no_other():
    document = _document()

    assert document.count("@font-face") == len(FONTS)
    for font in FONTS:
        assert f'url("/fonts/{font.file}") format("woff2")' in document, font.file
    for family in (
        "IBM Plex Sans",
        "IBM Plex Sans Condensed",
        "IBM Plex Mono",
        "Newsreader",
    ):
        assert any(font.family == family for font in FONTS), family


def test_every_font_the_page_uses_is_bundled_with_its_license():
    """OFL-1.1 condition 2: each copy carries the copyright notice and the license --
    here, beside the files, as `OFL.txt`. And each file is the woff2 it claims to be."""
    fonts = resources.files("wl_xcon").joinpath("fonts")

    for font in FONTS:
        assert font_bytes(font)[:4] == b"wOF2", font.file
    for directory in {font.directory for font in FONTS}:
        text = fonts.joinpath(directory).joinpath("OFL.txt").read_text(encoding="utf-8")
        assert "SIL Open Font License, Version 1.1" in text, directory


def test_the_fonts_ship_with_the_package():
    """`pyproject.toml`'s package data carries every font and its license, so an
    installed `wlx serve` serves what a checkout does."""
    pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
    table = tomllib.loads(pyproject.read_text(encoding="utf-8"))["tool"]["setuptools"]
    globs = table["package-data"]["wl_xcon"]

    for font in FONTS:
        for rel in (f"fonts/{font.directory}/{font.file}", f"fonts/{font.directory}/OFL.txt"):
            assert any(fnmatch.fnmatch(rel, pattern) for pattern in globs), rel


def test_the_nonce_is_escaped_into_its_attribute():
    document = page(fragments(frame(), view()), stale_after_s=30.0, nonce='x"><b>')

    assert '<script nonce="x&quot;&gt;&lt;b&gt;">' in document


def test_the_page_tells_its_script_when_a_stream_is_stale():
    document = page(fragments(frame(), view()), stale_after_s=45.0, nonce="n0nce")

    assert ('<body data-stale-after="45" data-can-write="0" data-apply-all-limit="50" '
            'data-can-gaze="0" data-gaze-every-ms="100">') in document


def test_the_right_column_is_honest_placeholders():
    """So the layout never shifts and nothing pretends to be live (PI, 2026-09-26)."""
    document = _document()

    for text in (
        "replica · V11",
        "subject display · no source yet",
        "sound · not measured",
        "display · not measured",
    ):
        assert text in document, text


def test_the_page_writes_only_by_posting_json_to_commands():
    """Spec §4.2, as amended by §5.2: the page's writes are the controls, and every
    one goes through the script's one command `fetch` (`deliver`) -- a JSON `POST` to
    `/commands`; the other four are the sign-in's -- and never a form (the Content-Security-Policy's `form-action 'none'` refuses one
    anyway). Its radio inputs still only choose a tab. **And a demo's pointer** (demo mode §4.5,
    its plan's Task 9): one more `fetch`, a JSON `POST` to `/gaze`, the demo's eye, no command. **And
    a new color's preview** (the console settings build's Task 8): a `GET` of `/color-preview`, which
    writes nothing; its *save* is a command, through `/commands`."""
    document = _document()

    assert "<form" not in document and "<textarea" not in document
    # b2b spec §4: four are the sign-in's (the token endpoint, `/whoami`, `/signout`) and the
    # page's recheck, `POST /whoami` with no token (b2b-ready §4.6); one a demo's pointer
    # reports and its release (`/gaze`); one a new color's preview, a `GET` that writes nothing
    # (`/color-preview`); only `/commands` carries a command.
    assert _SCRIPT.count("fetch(") == 7
    assert _SCRIPT.count('fetch("/color-preview?" + query.toString(), { cache: "no-store" })') == 1
    assert _SCRIPT.count('fetch("/whoami", {') == 2
    assert _SCRIPT.count('fetch("/commands", {') == 1
    assert _SCRIPT.count('fetch("/gaze", {') == 1
    assert 'fetch(body.getAttribute("data-token-endpoint")' in _SCRIPT
    assert 'fetch("/whoami", {' in _SCRIPT and 'fetch("/signout", {' in _SCRIPT
    assert 'method: "POST"' in _SCRIPT
    assert "var headers = { \"Content-Type\": \"application/json\" };" in _SCRIPT
    radios = re.findall(r'<input type="radio"[^>]*>', document)
    # Six tabs since the console settings build's Task 10 added Training (its design's §8).
    assert len(radios) == 6


def test_the_script_does_only_what_spec_4_3_and_5_2_ask():
    """§4.3's stream, and §5.2's growth: it sends commands, debounces the arrows,
    handles P and M, and asks for the name. It still renders nothing itself: every
    `innerHTML` it writes is a fragment `wlx serve` rendered."""
    document = _document()

    for needle in (
        'new EventSource("/events")',
        'addEventListener("frame"',
        "stream stale · last frame ",
        "stream lost",
        'el("close")',
        'el("reconnect")',
        "source.close()",
        'fetch("/commands", {',
        "window.prompt(",
        'k === "p"',
        'k === "m"',
    ):
        assert needle in document, needle
    assert "disconnected · the session keeps running on the box" in document
    # R3 (Task 13 rulings, carried from Task 10's review): capture the whole
    # right-hand side, not just the identifier -- `node.innerHTML = "<b>" + name`
    # would have slipped past a pin that only read the trailing word -- and allow
    # only the fragment renderer's own two forms. No other way to write markup -- but a demo's
    # drawing and its key list (demo mode's Task 9), each rendered by `wlx serve` too
    # (`demoscreen.render`, `web.demo_keys`) and sent as its own event, `drawn`. The boxes' own
    # fragment is parsed into a `<template>` and patched in box by box (the console interface
    # rework's Task 6, `patchCards`): the first `html`.
    assert re.findall(r"\.innerHTML\s*\+?=\s*([^;]+);", _SCRIPT) == [
        "html", "html", "heldMoments", "payload.keys", "payload.svg"]
    patch = _SCRIPT.split("  function patchCards(id, html) {", 1)[1].split("\n  }\n", 1)[0]
    assert 'var made = document.createElement("template");' in patch
    assert "made.innerHTML = html;" in patch
    assert "outerHTML" not in _SCRIPT
    assert "insertAdjacentHTML" not in _SCRIPT
    assert "document.write" not in _SCRIPT


def test_the_stale_timer_runs_from_the_frames_age_not_from_arrival():
    """Ruling 12 (2026-09-27). Python cannot run the script, so its text is pinned
    where it is load-bearing: the baseline is the event's arrival less the `age`
    `wlx serve` sends, stale is `now - baseline` at or beyond `--stale-after` --
    `>=`, so the page agrees with `/health`'s own boundary -- the banner's N is that
    same interval, and a `null` age -- no frame yet -- runs no timer. `now` and the
    baseline are both `performance.now()`, monotonic, so a browser clock step never
    skews the timer. The old `last = Date.now()` reset is what let a reconnect onto
    an old frame, or a refusal's wake-up, restart the clock."""
    assert "last = Date.now()" not in _SCRIPT
    timer = re.search(r"function check\(\) \{(.*?)\n  \}", _SCRIPT, re.S).group(1)
    assert "Date.now()" not in timer
    # The one `Date.now()` is the mark's `pressed_at`, the browser's clock, sent as
    # such (spec §5.1) and never read against the stream.
    # (The sign-in's own `Date.now()`s, its tokens' expiry, are in its block.)
    head, rest = _SCRIPT.split("  var signinPage", 1)
    _, tail = rest.split("  function signOut()", 1)
    tail = tail.split('  if (signinPage) {\n    if (el("signin"))', 1)[0]
    assert (head + tail).count("Date.now()") == 1
    assert "pressed_at: Date.now() / 1000" in _SCRIPT
    assert (
        "baseline = payload.age === null ? null : performance.now() - payload.age * 1000;"
        in _SCRIPT
    )
    assert "var held = performance.now() - baseline;" in _SCRIPT
    assert "if (held >= staleMs) {" in _SCRIPT
    assert '"stream stale · last frame " + Math.floor(held / 1000) + " s ago"' in _SCRIPT
    assert "if (!live || baseline === null) {" in _SCRIPT


def test_a_lost_stream_greys_the_page_as_a_stale_one_does():
    """m3: the stale timer stands down while the stream is lost, so a red *stream
    lost* banner used to sit over full-color numbers nobody was updating. The error
    handler greys the page itself; the next frame's `check()` clears it."""
    handler = re.search(r"source\.onerror = function \(\) \{(.*?)\n    \};", _SCRIPT, re.S)

    assert handler, "the script's error handler moved; re-pin this test on it"
    body = handler.group(1)
    assert 'body.classList.add("stale");' in body
    assert body.index("lost = true;") < body.index('body.classList.add("stale");')
    assert 'say("stream lost", "crit");' in body


def test_the_stream_banner_and_the_disconnect_dialog_start_hidden():
    document = _document()

    assert '<div class="banner" id="stream" role="status" hidden></div>' in document
    assert re.search(r'<div class="scrim" id="gone"[^>]*hidden>', document)


# --- P4d-2b b2a: the controls (spec §5.2) -------------------------------------------


def _controls(**frame_overrides) -> str:
    return fragments(frame(**frame_overrides), view())["controls"]


def test_the_controls_offer_pause_mark_and_stop_while_running():
    controls = _controls()

    assert '<button type="button" class="btn" data-cmd="pause">pause (P)</button>' in controls
    assert '<button type="button" class="btn" data-cmd="mark">mark (M)</button>' in controls
    assert '<button type="button" class="btn danger" data-cmd="stop">stop run</button>' in controls
    # Every control but the manual reward, which waits for a pause (Task 13).
    assert controls.count(" disabled") == 1
    assert 'data-cmd="reward" disabled' in controls


def test_a_paused_session_offers_resume_and_says_since_when_in_its_pill():
    at = 1_700_000_030.0
    since = time.strftime("%H:%M:%S", time.localtime(at))
    parts = fragments(frame(paused_at=at), view())

    assert 'data-cmd="resume">resume (P)</button>' in parts["controls"]
    assert 'data-cmd="pause"' not in parts["controls"]
    assert parts["state"] == (
        f'<span class="pill warn" data-state="paused">paused · since {since}</span>'
    )


def test_an_ended_session_is_not_shown_paused_and_offers_no_controls():
    parts = fragments(frame(**STATES["returned"], paused_at=1_700_000_030.0), view())

    assert 'data-state="ended"' in parts["state"]
    assert "data-cmd" not in parts["controls"]
    assert "the session has ended" in parts["controls"]


def test_everywhere_but_the_box_the_controls_are_greyed_with_the_sentence():
    """Spec §5.2 and §2: every control is disabled and says why, in the §2 sentence,
    on the page a LAN viewer -- or the box's browser under another name -- is
    served. Refused at `POST /commands` too; this is so nobody is offered a button
    that cannot work."""
    parts = fragments(
        frame(scheduled_stop=ScheduledStop("trials", 48.0, Box("jake"), "after trial 48")),
        view(on_box=False, can_write=False),
    )
    written = parts["controls"] + parts["params"] + parts["strip"]

    buttons = re.findall(r"<button[^>]*data-(?:cmd|dir)[^>]*>", written)
    inputs = re.findall(r"<input[^>]*data-param[^>]*>", written)
    assert buttons and inputs
    assert all(" disabled" in tag for tag in buttons + inputs)
    assert CONTROLS_AT_THE_BOX in parts["controls"]
    assert CONTROLS_AT_THE_BOX == "controls work only at the rig PC"


def test_a_console_without_the_mark_endpoint_greys_mark_alone():
    controls = fragments(frame(), view(can_mark=False))["controls"]

    assert re.search(r'data-cmd="mark" disabled title="[^"]+"', controls)
    assert NO_MARK_ENDPOINT in html.unescape(controls)
    assert re.search(r'data-cmd="pause">', controls)


def test_each_parameter_card_has_arrows_and_an_input_with_its_step_and_range():
    """Spec §5.2: − and + and an input on each box (the console interface rework's Task 5: two
    buttons beside the field, where two 8 px arrows were). The step is the rig's
    (`ParamRow.step`, `task.step_of`: by unit, s 0.05, deg 0.1, mL 0.01, else 0.01), and the
    input shows the value at the step's decimals, or more where the value holds more; a
    categorical box takes a word and has neither."""
    params = fragments(
        frame(
            params=(
                ParamRow.of("fix_hold", "s", 0.1, 1.0, 0.3, False, step=0.05),
                ParamRow.of("reward_correct", "mL", 0.0, 0.4, 0.15, True, step=0.01),
                ParamRow.of("fix_window", "deg", None, 5.0, 2.0, False, step=0.1),
                ParamRow("target_appearance", "", None, None, None, False),
                ParamRow("shape", "", None, None, "penguin", False),
            )
        ),
        view(),
    )["params"]

    assert (
        '<button type="button" class="stp" data-dir="-1" tabindex="-1" '
        'aria-label="decrease fix_hold">−</button>'
        '<input class="field mono" data-param="fix_hold" data-step="0.05" '
        'data-min="0.1" data-max="1.0" inputmode="decimal" value="0.30" '
        'aria-label="fix_hold">'
        '<button type="button" class="stp" data-dir="1" tabindex="-1" '
        'aria-label="increase fix_hold">+</button></span><span class="unit">s</span>'
    ) in params
    assert 'data-param="reward_correct" data-step="0.01" data-min="0.0" data-max="0.4"' in params
    assert 'data-param="fix_window" data-step="0.1" data-max="5.0" inputmode="decimal" value="2.0"' in params
    assert 'data-param="target_appearance" data-step="0.01" inputmode="decimal" value=""' in params
    assert (
        '<input class="field mono" data-param="shape" data-kind="word" value="penguin" '
        'aria-label="shape">'
    ) in params
    assert params.count('data-dir="1"') == 4 and params.count('data-dir="-1"') == 4


def test_a_setting_holding_a_position_shows_it_polar_first_and_offers_no_input():
    """XC-401 (the PI, 2026-10-19, "Polar first, x-y allowed"): a setting whose value is a whole
    position shows the rig's words for it, eccentricity and direction first with its (x, y)
    beside them (`ParamRow.position`), escaped, and no input or arrows: nothing a console sends
    sets a position (`link._setting` takes a number or a word). The unit is in the words."""
    params = fragments(
        frame(params=(
            ParamRow("target_pos", "deg", None, None, None, False,
                     "27.236° at 45° · (x, y) (20, 20)"),
            ParamRow("fix_hold", "s", 0.1, 1.0, 0.3, False),
        )),
        view(),
    )["params"]
    target = _cards(params)["target_pos"]

    assert '<span class="pv">27.236° at 45° · (x, y) (20, 20)</span>' in target
    assert "<input" not in target and 'data-dir="1"' not in target and "unset" not in target
    assert 'data-param="fix_hold"' in params


def test_a_value_that_is_no_number_or_word_is_shown_as_written_with_no_input():
    """XC-401's second fix round: a setting holding a value that is neither a number nor a word --
    a pair a setting not declared a position holds, arriving as a list, or a `bool` -- made its
    card raise formatting it as a number, and `serve` builds the page and its event stream from
    the cards unguarded, so the page went blank. It is shown as written, escaped, with no input or
    arrows: nothing a console sends sets it."""
    params = fragments(frame(params=(
        ParamRow("span", "deg", 0.0, 1.0, [0.3, 0.6], False),
        ParamRow("odd", "", None, None, ["<b>", 1], False),
        ParamRow("flag", "", None, None, True, False),
        ParamRow("fix_hold", "s", 0.1, 1.0, 0.3, False),
    )), view())["params"]
    span, odd, flag, hold = (_cards(params)[name] for name in ("span", "odd", "flag", "fix_hold"))

    assert '<span class="pv">[0.3, 0.6] <span class="unit">deg</span></span>' in span
    assert "[&#x27;&lt;b&gt;&#x27;, 1]" in odd and "<b>" not in odd
    assert '<span class="pv">True ' in flag
    assert not any("<input" in card or 'data-dir="1"' in card for card in (span, odd, flag))
    assert 'data-param="fix_hold"' in hold


def test_a_refusal_shows_on_its_parameters_card_with_its_sentence():
    params = fragments(
        frame(
            refusals=(
                Refused("fix_hold", Box("jake"), "first"),
                # A refusal `Session.set` says today; a value outside its range is no longer
                # refused for that alone since XC-352's D2 (Task 11's minor).
                Refused("fix_hold", Box("jake"), "'fix_hold' takes a number (s); 'nine' is not "
                        "one, so it is refused and the previous value stands"),
            )
        ),
        view(),
    )["params"]

    assert (
        '<span class="rfs">last refused: &#x27;fix_hold&#x27; takes a number (s); '
        "&#x27;nine&#x27; is not one, so it is refused and the previous value stands</span>"
    ) in params
    assert "first" not in params


def test_the_strip_shows_a_scheduled_stop_with_who_set_it_and_a_cancel():
    """Spec §5.2: while a schedule is active the strip shows it -- *stop at 14:30 ·
    set by jake* -- with a cancel button."""
    strip = fragments(
        frame(scheduled_stop=ScheduledStop("clock", 1_700_003_600.0, Box("jake"), "at 14:30")),
        view(),
    )["strip"]

    assert '<span class="lab">Scheduled</span><span class="val">stop at 14:30</span>' in strip
    assert f"set by {_who(Box('jake'))}" in strip
    assert '<button type="button" class="btn small" data-cmd="cancel">cancel</button>' in strip


def test_with_nothing_scheduled_the_strip_keeps_its_two_cells():
    strip = fragments(frame(), view())["strip"]

    assert "Scheduled" not in strip
    assert strip.count('<div class="row">') == 2


def test_the_strip_guards_against_an_ended_frame_still_carrying_a_schedule():
    """Review fix round 1: since Task 8's fix, `Telemetry.of` sends
    `scheduled_stop=None` once `stopped_because` is set, so a frame like this should
    never arrive on the wire. This pins the guard's defensive behavior anyway -- a
    frame that combined an ended `stop_kind` with a `scheduled_stop` would still show
    no schedule and no cancel button for it."""
    strip = fragments(
        frame(
            **STATES["returned"],
            scheduled_stop=ScheduledStop("trials", 48.0, Box("jake"), "after trial 48"),
        ),
        view(),
    )["strip"]

    assert "Scheduled" not in strip and "data-cmd" not in strip


def test_the_feed_lists_control_events_newest_first_with_who_and_counts_the_rest():
    """Spec §5.2: the changes feed lists every setting change, refusal, pause, resume,
    mark (with its note) and schedule, with who did it. Newest first, since it is
    read to see what just happened; what fell off the cap is counted below them."""
    at = 1_700_000_001.0
    clock = time.strftime("%H:%M:%S", time.localtime(at))
    changes = fragments(
        frame(
            controls=(
                Control("mark", None, at, "mark 1 stamped in trial 3, frame 10"),
                Control("note", Box("jake"), at, 'mark 1: "bubble"'),
                Control("set", Box("sam"), at, "fix_hold 0.30 → 0.40, from trial 4"),
            ),
            controls_dropped=5,
        ),
        view(),
    )["rt-changes"]

    set_row = changes.index(f"{clock} · fix_hold 0.30 → 0.40, from trial 4 · {_who(Box('sam'))}")
    note_row = changes.index(f"{clock} · mark 1: &quot;bubble&quot; · {_who(Box('jake'))}")
    mark_row = changes.index(f"{clock} · mark 1 stamped in trial 3, frame 10</span>")
    dropped = changes.index("5 earlier control event(s) not shown")
    assert set_row < note_row < mark_row < dropped
    assert '<span class="kind">note</span>' in changes


def test_every_control_string_is_escaped():
    """Review Focus 2 for b2a's strings: an actor's typed name, a note, a schedule's
    words, and a parameter's name in the attributes its input carries."""
    evil = frame(
        controls=(Control(EVIL, Box(EVIL), 1_700_000_001.0, EVIL),),
        scheduled_stop=ScheduledStop(EVIL, 1.0, Box(EVIL), EVIL),
        params=(ParamRow(EVIL, EVIL, 0.0, 1.0, 0.5, False), ParamRow("w", "", None, None, EVIL, False)),
        refusals=(Refused(EVIL, Box(EVIL), EVIL),),
    )

    text = "".join(fragments(evil, view()).values())

    assert "<script" not in text
    assert EVIL not in text


def test_the_page_tells_its_script_whether_it_may_write_and_apply_alls_limit():
    """The page is rendered per request, so the box's own page says it may write and
    a LAN viewer's says it may not; the script reads both from `<body>`. The 600 ms
    debounce that rode there went with the arrows' sends (the console interface rework's Task
    6: nothing is sent until Apply); Apply all's limit rides there now, 50, below the rig's 64
    (`link.APPLY_LIMIT`), so a refused act's every refusal fits in a frame's last 50."""
    box = page(fragments(frame(), view()), stale_after_s=30.0, nonce="n0nce", can_write=True)
    lan = page(
        fragments(frame(), view(can_write=False)), stale_after_s=30.0, nonce="n0nce"
    )

    from wl_xcon.link import APPLY_LIMIT, REFUSAL_HISTORY

    assert APPLY_ALL_LIMIT == 50 == REFUSAL_HISTORY < APPLY_LIMIT
    assert "data-debounce-ms" not in box
    assert ('<body data-stale-after="30" data-can-write="1" data-apply-all-limit="50" '
            'data-can-gaze="0" data-gaze-every-ms="100">') in box
    assert ('<body data-stale-after="30" data-can-write="0" data-apply-all-limit="50" '
            'data-can-gaze="0" data-gaze-every-ms="100">') in lan
    for control in ('id="sched-kind"', 'id="sched-value"', 'id="sched-set"'):
        assert re.search(control + r"[^>]* disabled", lan), control
        assert not re.search(control + r"[^>]* disabled", box), control
    # The name is the box's alone: a LAN viewer reads `read-only`, with no way to rename.
    assert re.search(r'id="rename"[^>]*>change', box) and 'id="rename"' not in lan
    assert "read-only" in lan


def test_the_page_holds_the_stop_confirm_and_the_mark_note_hidden():
    document = page(fragments(frame(), view()), stale_after_s=30.0, nonce="n0nce", can_write=True)

    assert re.search(r'<div class="inline crit" id="stop-confirm"[^>]*hidden>', document)
    assert "stop at a trial boundary, after any commands already sent?" in document
    assert re.search(r'<div class="inline info" id="mark-form"[^>]*hidden>', document)
    assert 'id="mark-note" maxlength="500"' in document


def test_the_script_sends_nothing_from_the_arrows_and_keeps_p_and_m_out_of_text_boxes():
    """Spec §5.2, as the console interface rework's Task 6 left it: the arrows send nothing (they
    make a draft, sent by the box's Apply; the 600 ms debounce and its timers are gone), and the
    keys do nothing while a text box has focus, or when held (a held key does not repeat)."""
    assert "debounce" not in _SCRIPT and "timers[" not in _SCRIPT
    step = _SCRIPT.split("  function stepInput(input, dir) {", 1)[1].split("\n  }\n", 1)[0]
    assert "post(" not in step and "refresh(box);" in step
    assert "if (e.metaKey || e.ctrlKey || e.altKey || e.repeat) { return; }" in _SCRIPT
    assert '/^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName) || t.isContentEditable' in _SCRIPT


def test_the_script_asks_for_the_name_once_and_keeps_it_where_it_may():
    """Spec §5.2: the box's browser asks once and remembers it locally. Storage can
    be refused -- a private window -- so every read and write is in `try`; a prompt
    refused or cleared sends nothing (Review Focus 6)."""
    assert "try { return window.localStorage.getItem(NAME_KEY) || \"\"; } catch (e) { return \"\"; }" in _SCRIPT
    assert "try { window.localStorage.setItem(NAME_KEY, given); } catch (e) { /* kept for this page only */ }" in _SCRIPT
    assert "if (given === null) { return \"\"; }" in _SCRIPT
    assert '"not sent: give your name first -- every command records who sent it"' in _SCRIPT


def test_the_script_keeps_the_editor_of_a_box_it_is_being_typed_into():
    """A frame that re-renders the parameter cards while a person types into one would replace
    the input under them. Since the console interface rework's Task 6 the script patches box by
    box: a box with a draft, its act out or a field focused keeps its editor's nodes
    (`patchDirty`), and only a pointer down holds a tab's frame whole (`heldCards`). The browser
    tests drive it (`test_page_browser.py`'s `test_a_press_during_frames_acts_once`)."""
    swap = _SCRIPT.split("  function swap(id, html) {", 1)[1].split("\n  }\n", 1)[0]
    assert 'if (id === "params" || id === "training-params") {' in swap
    assert "patchCards(id, html);" in swap
    patch = _SCRIPT.split("  function patchCards(id, html) {", 1)[1].split("\n  }\n", 1)[0]
    assert "if (pressing()) { heldCards[id] = html; return; }" in patch
    assert "} else if (dirty(box)) { held[name] = true; }" in patch
    assert "patchDirty(box, given[name], before[name]);" in patch


# --- Task 10 review, fix round 1 ----------------------------------------------------


def test_a_double_click_or_one_within_the_hold_cannot_toggle_pause_or_resume():
    """The review, round 2: the **P** key (`pauseOrResume`, wired from `keydown`)
    called `command` directly and was not covered by round 1's click-only guard -- a
    rapid double **P** is not an `e.repeat` (that only filters OS key-autorepeat, not
    two independent keydowns) and could reproduce the same toggle. One
    `toggleAllowed` helper now guards both routes: it refuses a click's own double
    (`detail > 1`) or anything within `TOGGLE_HOLD_MS` of the last pause/resume this
    page sent, and stamps that instant only on success. `command` itself is called
    only after the helper allows it, from both the click handler and
    `pauseOrResume`."""
    assert "var TOGGLE_HOLD_MS = 1000;" in _SCRIPT
    helper = re.search(
        r"function toggleAllowed\(detail\) \{(.*?)\n  \}", _SCRIPT, re.S
    ).group(1)
    assert "detail > 1" in helper
    assert "now - lastToggleAt < TOGGLE_HOLD_MS" in helper
    assert "return false;" in helper
    assert "lastToggleAt = now;" in helper
    assert "return true;" in helper
    assert helper.index("return false;") < helper.index("lastToggleAt = now;")
    assert helper.index("lastToggleAt = now;") < helper.index("return true;")

    handler = re.search(
        r'document\.addEventListener\("click", function \(e\) \{(.*?)\n  \}\);',
        _SCRIPT,
        re.S,
    ).group(1)
    assert 'cmd === "pause" || cmd === "resume"' in handler
    assert "toggleAllowed(e.detail)" in handler
    # Only pause/resume are guarded -- mark, stop and cancel are unaffected.
    assert handler.index('cmd === "pause"') > handler.index("var cmd =")
    assert handler.index("toggleAllowed(e.detail)") < handler.index("command(cmd);")

    pause_or_resume = re.search(
        r"function pauseOrResume\(\) \{(.*?)\n  \}", _SCRIPT, re.S
    ).group(1)
    assert "toggleAllowed(" in pause_or_resume
    assert pause_or_resume.index("toggleAllowed(") < pause_or_resume.index("command(")


def test_the_arrows_round_before_clamping_and_write_the_edge_exactly():
    """The review: the old order clamped to `[lo, hi]` first and let `toFixed` round
    the display afterwards, so a clamped value could be rounded back out past its own
    ceiling (0.125 mL clamped, then `toFixed(2)` sent "0.13"). Rounding to the step
    now comes first; the clamp that follows writes the edge's own `data-min`/
    `data-max` attribute string exactly, never re-rounding it. Verified against the
    review's own examples in Node (pasted into the fix report): 0.125, 0.337 and 5.25
    ceilings all now stay at their own figure instead of overshooting to "0.13",
    "0.34" and "5.3"."""
    body = re.search(
        r"function stepInput\(input, dir\) \{(.*?)\n  \}", _SCRIPT, re.S
    ).group(1)

    assert body.index("Math.round(") < body.index("if (v <= lo)")
    assert 'input.value = input.getAttribute("data-min");' in body
    assert 'input.value = input.getAttribute("data-max");' in body
    assert body.index("if (v <= lo)") < body.index("else if (v >= hi)")


def test_a_welfare_ceiling_displays_its_own_decimals_not_rounded_to_two():
    """The review: `_num`'s two-decimal display rounded a 0.125 mL ceiling to "0.12"
    -- short of "0.13", which the unfixed arrows could still send. The ceiling now
    keeps its own figure."""
    params = fragments(
        frame(params=(ParamRow("reward_correct", "mL", 0.0, 0.125, 0.1, True),)),
        view(),
    )["params"]

    assert "welfare ceiling 0.125 mL" in params
    assert "welfare ceiling 0.12 mL" not in params


def test_the_script_pins_the_box_only_write_guard():
    """The review found neither half of this pinned: the script reads `can-write`
    from `<body>`, and `post` -- the one function every command goes through --
    refuses to send anything when it says this page may not write, before it does
    anything else. Welfare-critical review round 1 (2026-09-28): a plain `in`
    passed with the guard moved below `tell("sending...")`, so this pins its
    position again. Since b2b the https page's branch comes first and returns on its own;
    the box's guard follows it, still before anything asks a name or sends."""
    assert 'var canWrite = body.getAttribute("data-can-write") === "1";' in _SCRIPT
    post_body = re.search(
        r"function post\(command, then, after\) \{(.*?)\n  \}", _SCRIPT, re.S
    ).group(1)
    # b2b spec §4: the https page's branch comes first and returns on its own; the box's
    # guard follows it and still precedes anything that asks a name or sends.
    assert post_body.strip().startswith(
        "var done = after || function () {};\n    if (signinPage) {"
    )
    after_signin = post_body.split("      return;\n    }\n", 1)[1]
    assert after_signin.startswith("    if (!canWrite) { done(); return; }")
    assert post_body.index("if (!canWrite)") < post_body.index("askName()")
    assert post_body.index("if (!canWrite)") < post_body.rindex("deliver(")


# --- P4d-2b b2a, amended 2026-09-28 (PI): a manual reward during a pause -------------


def test_during_a_run_the_reward_button_is_live_only_while_paused_and_greyed_otherwise():
    """PI, 2026-09-28: a manual reward during a pause. During a run the button works only
    while the session is paused (`paused_at`), and otherwise says why: greyed with its
    reason while trials run, with the §2 sentence away from the box, and gone once a
    `wlx run` session has ended. One button and no key: a click is one command. Outside a
    run, in a `wlx taskd` session, it is live too (PI, 2026-09-29): see
    `test_outside_a_run_the_hand_reward_and_mark_are_live_with_what_the_last_press_did`."""
    at = 1_700_000_030.0
    paused = _controls(paused_at=at)
    running = _controls()
    lan = fragments(frame(paused_at=at), view(on_box=False, can_write=False))["controls"]
    ended = fragments(frame(**STATES["returned"], paused_at=at), view())["controls"]

    assert '<button type="button" class="btn" data-cmd="reward">give reward</button>' in paused
    assert (
        f'<button type="button" class="btn" data-cmd="reward" disabled '
        f'title="{REWARD_ONLY_PAUSED}">give reward</button>'
    ) in running
    assert REWARD_ONLY_PAUSED == (
        "a manual reward is given only while the session is paused: pause first"
    )
    assert re.search(r'data-cmd="reward" disabled title="[^"]+">give reward', lan)
    assert CONTROLS_AT_THE_BOX in lan
    assert "give reward" not in ended
    assert 'k === "r"' not in _SCRIPT, "no key gives a reward"


def test_while_paused_the_controls_show_the_fluid_total_and_what_the_last_press_did():
    """The answer to a press, from the frames the rig publishes while paused: the
    session's fluid total, the newest reward given with its size, and the newest
    refused with the rig's sentence -- *last*, since a refusal carries no time, as on
    a parameter card. Escaped like every string from telemetry."""
    at = 1_700_000_035.0
    controls = _controls(
        paused_at=1_700_000_030.0,
        fluid_session_ml=1.4,
        controls=(
            Control(
                "reward",
                Box("jake"),
                at,
                "0.15 mL of reward_correct, given while paused before trial 40",
            ),
        ),
        refusals=(Refused(name="reward", by=Box("sam"), why="the session is <not> paused"),),
    )
    clock = time.strftime("%H:%M:%S", time.localtime(at))

    assert "fluid session 1.40 mL" in controls
    assert (
        f"last given {clock}: 0.15 mL of reward_correct, given while paused before trial 40"
        in controls
    )
    assert "last refused: the session is &lt;not&gt; paused" in controls
    assert "fluid session" not in _controls(), "said beside the live button alone"


def test_the_scripts_top_level_names_are_each_declared_once():
    """The page's script is one closure, so a second `function NAME` or `var NAME` at its top level
    silently replaces the first wherever either is called -- the fix wave's round 2 found two
    (`UNCONFIRMED`, the sign-in's word taken by a box's; `letGo`, the demo's taking a box's gate),
    each passing every test of its own part. Each top-level name is declared once."""
    import collections

    declared = [function or variable for function, variable in re.findall(
        r"^  (?:function (\w+)\(|var (\w+)\b)", _SCRIPT, re.M)]
    assert len(declared) > 200, "the script's top level is read"
    twice = sorted(name for name, count in collections.Counter(declared).items() if count > 1)
    assert twice == [], twice


def test_the_script_sends_one_reward_per_click_and_holds_the_button_until_its_answer():
    """No accidental doubles (PI, 2026-09-28). Python cannot run the script, so its text
    is pinned where it is load-bearing: a click while a reward is on its way does
    nothing; the button is held from the click until the answer or the failure -- and
    held again whenever a frame re-renders the controls meanwhile -- and only a button
    the script held is released; the one `fetch` is never retried; and an answer the
    page lost is *unknown*, never *not delivered*, with the fluid total to check first."""
    assert "if (!button || button.disabled || rewarding) { return; }" in _SCRIPT
    assert "rewarding = true;" in _SCRIPT
    assert 'post({ kind: "reward" }, null, function () {' in _SCRIPT
    assert 'if (id === "controls") { holdReward(); }' in _SCRIPT
    assert "if (rewarding && button && !button.disabled) {" in _SCRIPT
    assert """el("controls").querySelector('[data-cmd="reward"][data-held]')""" in _SCRIPT
    # `done` runs on the answer and on the failure alike, outside the answer's handler (the
    # console interface rework's whole-build review, M4).
    assert "} finally { done(); }" in _SCRIPT
    assert "}, function (fault) { done(); throw fault; });" in _SCRIPT
    assert _SCRIPT.count('fetch("/commands"') == 1
    assert (
        "unknown: this page lost wlx serve's answer, so whether the reward was given is "
        "not known, and it was not sent again; check the session's fluid total before "
        "pressing again"
    ) in _SCRIPT


def test_a_double_click_on_give_reward_gives_only_one_reward():
    """R2 (Task 13 rulings, an animal-facing defect in the plan): the disabled-until-
    answered rule alone can miss a double click on loopback, where the answer can
    return well inside a double click's span, leaving the button live again before
    the second click lands. `rewardAllowed` gives *give reward* the same debounce
    Task 10 gave pause and resume -- refused on a native double click (`detail > 1`)
    or within `REWARD_HOLD_MS` of the last reward this page sent -- in the click
    handler's own branch, never inside `command` or `post`, so a deliberate second
    press a second later still gives another reward."""
    assert "var REWARD_HOLD_MS = 1000;" in _SCRIPT
    assert (
        "// Housekeeping, not a measurement (R2, 2026-09-28): the same double click's span as\n"
        "  // TOGGLE_HOLD_MS, since a reward's answer can return well inside it on loopback,\n"
        "  // leaving the button live again before a double click's second click lands.\n"
        "  var REWARD_HOLD_MS = 1000;"
    ) in _SCRIPT
    assert "var lastRewardAt = -Infinity;" in _SCRIPT
    assert "function rewardAllowed(detail) {" in _SCRIPT
    assert (
        "if (detail > 1 || now - lastRewardAt < REWARD_HOLD_MS) { return false; }"
        in _SCRIPT
    )
    assert "lastRewardAt = now;" in _SCRIPT
    assert 'if (cmd === "reward" && !rewardAllowed(e.detail)) { return; }' in _SCRIPT
    command_body = re.search(
        r"function command\(cmd\) \{(.*?)\n  \}", _SCRIPT, re.S
    ).group(1)
    post_body = re.search(
        r"function post\(command, then, after\) \{(.*?)\n  \}", _SCRIPT, re.S
    ).group(1)
    assert "rewardAllowed" not in command_body
    assert "rewardAllowed" not in post_body


def test_the_page_with_no_session_open_says_so_and_puts_a_stranded_animal_first():
    panes = fragments(
        idle(
            stranded=(Stranded("2027-01-13_01", "<b>B</b>", 1_700_000_000.0),),
            question=Question("departure", "2027-01-14_01", 1.0, "far <i>", ("confirm", "amend")),
            refusals=(Refused("open", Box("jake"), "refused <script>"),),
        ),
        view(),
    )

    assert set(panes) == set(FRAGMENT_IDS)
    assert 'data-state="idle"' in panes["state"]
    assert panes["banners"].index("Stranded") < panes["banners"].index("Confirm")
    assert "&lt;b&gt;B&lt;/b&gt;" in panes["banners"] and "<b>B" not in panes["banners"]
    assert "far &lt;i&gt; · answer confirm or amend" in panes["banners"]
    assert "Waiting" not in panes["banners"]
    assert "refused &lt;script&gt;" in panes["rt-changes"]
    assert "controls · no session open" in panes["controls"]
    assert "none open · wlx taskd is idle" in panes["rt-health"]
    assert '<span class="pill warn">degraded</span>' in panes["rt-health"], "an animal is stranded"


@pytest.mark.parametrize("unshowable", [1e20, float("nan")])
def test_the_pages_stranded_banner_shows_the_departures_date_or_says_it_is_unknown(unshowable):
    """The b3a-1 final review, Minor 1: the banner gave the departure as a clock time
    alone, so an animal stranded three days ago read "left its cage at 22:55:14". It is
    this host's local date, minute and zone, as the terminal gives it (`cli._moment`),
    or "an unknown time" for an instant this host cannot show."""
    left_at = 1_700_000_000.0
    banners = fragments(
        idle(stranded=(Stranded("2027-01-13_01", "B", left_at), Stranded("2027-01-13_02", "C", unshowable))),
        view(),
    )["banners"]

    assert f"B left its cage at {html.escape(_local(left_at))} in session 2027-01-13_01" in banners
    assert "C left its cage at an unknown time in session 2027-01-13_02" in banners


def test_the_page_escapes_control_characters_and_markup_in_an_idle_frames_text():
    panes = fragments(
        idle(
            stranded=(Stranded("<s>", "B\x1b[2J<", None),),
            question=Question("return", "<q>", 1.0, "far\x1b", ("<a>",)),
            refusals=(Refused("<n>", Box("<by>"), "<why>\x1b"),),
        ),
        view(),
    )

    joined = "".join(panes.values())
    for raw in ("<s>", "<q>", "<a>", "<n>", "<by>", "<why>"):
        assert raw not in joined


def test_the_page_between_runs_says_which_run_ended_and_offers_start_run_not_pause_or_stop():
    """`run_index` 1 is the session's second run: a person reads runs from 1
    (session-levels spec §3)."""
    panes = fragments(
        frame(phase="between_runs", service=True, run_index=1, stop_kind="operator", stopped_because="stopped by jake"),
        view(),
    )

    assert 'data-state="between-runs"' in panes["state"] and "run 2 ended" in panes["state"]
    assert "Run 2 ended" in panes["banners"]
    assert 'data-cmd="start"' in panes["controls"]
    assert 'data-cmd="pause"' not in panes["controls"] and 'data-cmd="stop"' not in panes["controls"]
    assert '<span class="k">Run</span><span class="v">2</span>' in panes["head-id"]


def test_the_header_pill_banner_and_strip_name_one_run():
    """The review of session levels' Task 6: the header, pill and banner printed the
    wire's 0-based `run_index` while the strip printed `run_in_session`, so one page
    named a session's third run as both 2 and 3."""
    perf = frame().performance
    assert perf.run_in_session == 3
    running = fragments(frame(run_index=2), view())
    ended = fragments(
        frame(
            phase="between_runs", service=True, run_index=2, stop_kind="operator",
            stopped_because="stopped by jake",
            performance=replace(perf, task=None, run=None, block=None, task_name=None,
                                runs_of_task=None, run_in_session=None,
                                block_in_session=None, block_type=None),
        ),
        view(),
    )

    assert '<span class="k">Run</span><span class="v">3</span>' in running["head-id"]
    assert "run 3" in running["strip"]
    assert '<span class="k">Run</span><span class="v">3</span>' in ended["head-id"]
    assert "run 3 ended" in ended["state"] and "Run 3 ended" in ended["banners"]


def test_the_page_before_a_sessions_first_run_shows_no_block_and_no_task():
    panes = fragments(
        frame(phase="between_runs", service=True, run_index=None, block=None, task=None, trial_index=0, outcomes={}),
        view(),
    )

    assert "between runs" in panes["state"] and "None" not in panes["head-id"]
    assert "no run yet" in panes["setup"] and "no run yet" in panes["end"]


def test_the_page_shows_the_question_a_return_owes():
    panes = fragments(
        frame(phase="awaiting_return", service=True, stop_kind="operator", stopped_because="session ended by jake",
              question=Question("return", "2027-01-14_01", 1.0, "the return is far", ("confirm", "re-type"))),
        view(),
    )

    assert "the return is far · answer confirm or re-type" in panes["banners"]


# --- P4d-2b b3a-2: sessions from the page ---------------------------------------------


def _between(**over):
    """A `wlx taskd` session between runs, its first run ended, one task offered."""
    fields = dict(
        phase="between_runs", service=True, run_index=0, stop_kind="completed",
        stopped_because="every block is finished", offered_tasks=("fixation_detection.py",),
    )
    fields.update(over)
    return frame(**fields)


#: A pre-flight as `wlx taskd` takes one (`preflight.py`'s item names), two items passing
#: and the two nothing measures yet unknown.
PREFLIGHT = Preflight(
    "fixation_detection.py",
    (
        PreflightItem("task checks", "pass", "fixation_detection.py passes its load-time checks"),
        PreflightItem("out of cage", "pass", "the departure is marked and the limit is not reached"),
        PreflightItem("pump calibration", "unknown", "no pump calibration has been measured (V10)"),
        PreflightItem("eye tracker", "unknown", "nothing reports the eye tracker's health yet"),
    ),
)
FAILING = replace(
    PREFLIGHT,
    items=(PREFLIGHT.items[0], PreflightItem("out of cage", "fail", "past <the> limit"))
    + PREFLIGHT.items[2:],
)


def test_the_task_chooser_offers_what_wlx_taskd_offers_and_says_when_there_is_nothing():
    only = '<option value="fixation_detection.py">fixation_detection.py</option>'

    assert fragments(_between(), view())["task-sel"] == only
    assert fragments(idle(), view())["task-sel"] == only
    assert fragments(frame(), view())["task-sel"] == '<option value="">no task offered</option>'
    assert fragments(None, view())["task-sel"] == '<option value="">no task offered</option>'


@pytest.mark.parametrize(
    ("preflight", "tone", "said"),
    [
        (None, "neutral", "pre-flight · not taken"),
        (PREFLIGHT, "warn", "pre-flight · 2 to acknowledge"),
        (FAILING, "crit", "pre-flight · 1 fail"),
        (replace(PREFLIGHT, items=PREFLIGHT.items[:2]), "ok", "pre-flight ✓"),
    ],
    ids=["not-taken", "unknowns", "a-fail", "all-pass"],
)
def test_between_runs_the_preflight_pill_is_a_button_that_says_what_the_rig_found(
    preflight, tone, said
):
    """The mockup's `pf-pill` and `pf-sum` (the b3a-2 plan, decisions 6 and 7): its words
    from the frame's pre-flight, and, between runs, a button that takes the pre-flight."""
    parts = fragments(_between(preflight=preflight), view())

    assert parts["pf-pill"] == (
        f'<button type="button" class="pill {tone}" data-cmd="check" '
        f'title="take the pre-flight for the task chosen">{said}</button>'
    )
    assert parts["pf-sum"] == f'<span class="pill {tone}">{said}</span>'


@pytest.mark.parametrize(
    ("shown", "said"),
    [
        (None, "no session"),
        (idle(), "no session"),
        (frame(), "pre-flight · wlx run takes none"),
        (frame(service=True), "pre-flight · taken as the run started"),
        (_between(phase="awaiting_return"), "pre-flight · the session has ended"),
    ],
    ids=["no-frame", "idle", "wlx-run", "a-run-going", "ended"],
)
def test_outside_between_runs_the_preflight_pill_only_says_why_there_is_none(shown, said):
    assert fragments(shown, view())["pf-pill"] == f'<span class="pill neutral">{said}</span>'


def test_the_preflight_panel_shows_each_item_its_result_and_no_unplanned_warning():
    """Under a line naming the task and S9a §10's rule, and nothing after it: the PI
    retired the unplanned-run warning on 2026-10-01, through wl-works (P4d-2b spec
    §4.0)."""
    shown = fragments(_between(preflight=FAILING), view())["preflight"]

    assert '<span class="st fail" title="fail"></span><span>out of cage</span>' in shown
    assert '<span class="st pass" title="pass"></span><span>task checks</span>' in shown
    assert '<span class="st untested" title="unknown"></span><span>eye tracker</span>' in shown
    assert "past &lt;the&gt; limit" in shown
    assert (
        '<div class="sub">for fixation_detection.py · the plain run · a fail blocks the run; each '
        "unknown starts it only on your acknowledgement, by name, written into runs.jsonl</div>"
    ) in shown
    assert "unplanned" not in shown and "timing tier" not in shown
    assert 'data-task="fixation_detection.py"' in shown
    assert "not taken" in fragments(_between(), view())["preflight"]


def test_each_unknown_item_has_an_unticked_acknowledgement_carrying_its_exact_name():
    """Review Focus 4 (the b3a-2 plan, decision 9): one box per unknown item, its exact
    name on it for the start to send, never rendered ticked -- a tick is the person's,
    for the run about to start -- and greyed away from the box."""
    shown = fragments(_between(preflight=PREFLIGHT), view())["preflight"]
    lan = fragments(_between(preflight=PREFLIGHT), view(can_write=False))["preflight"]

    for name in ("pump calibration", "eye tracker"):
        assert (
            f'<label class="chk"><input type="checkbox" data-ack="{name}" '
            f'aria-label="acknowledge {name}"> acknowledge</label>'
        ) in shown
    assert shown.count("data-ack=") == 2, "only an unknown is acknowledged"
    assert "checked" not in shown
    boxes = re.findall(r"<input[^>]*data-ack[^>]*>", lan)
    assert boxes and all(" disabled" in box for box in boxes)


def test_between_runs_start_run_carries_the_shown_preflights_task_and_waits_for_one_with_no_fail():
    """The b3a-2 plan, decision 8, and spec §6.2: "the start refused while any item
    fails" -- greyed with its reason in the page, and refused by the rig anyway."""
    none = fragments(_between(), view())["controls"]
    ready = fragments(_between(preflight=PREFLIGHT), view())["controls"]
    failing = fragments(_between(preflight=FAILING), view())["controls"]

    assert (
        '<button type="button" class="btn go" data-cmd="start" data-task="" data-plan="" disabled '
        'title="take the pre-flight first: choose a task, or press the pre-flight pill">'
        "start run</button>"
    ) in none
    assert (
        '<button type="button" class="btn go" data-cmd="start" '
        'data-task="fixation_detection.py" data-plan="">start run</button>'
    ) in ready
    assert 'disabled title="pre-flight: out of cage failing">start run</button>' in failing
    # No unplanned-run warning beside it (the PI, 2026-10-01, through wl-works).
    assert "unplanned" not in ready and "timing tier" not in ready
    assert 'data-cmd="pause"' not in ready and 'data-cmd="stop"' not in ready


@pytest.mark.parametrize("phase", ["between_runs", "awaiting_return"])
def test_outside_a_run_the_hand_reward_and_mark_are_live_with_what_the_last_press_did(phase):
    """PI, 2026-09-29 (spec §6.0): *give reward* works between runs and while the return
    is awaited in a `wlx taskd` session, and says beside itself what the rig did."""
    controls = fragments(
        _between(
            phase=phase,
            fluid_session_ml=0.4,
            controls=(
                Control("reward", Box("jake"), 1_700_000_035.0,
                        "0.15 mL of reward_correct, given between runs"),
            ),
        ),
        view(),
    )["controls"]

    assert '<button type="button" class="btn" data-cmd="reward">give reward</button>' in controls
    assert '<button type="button" class="btn" data-cmd="mark">mark (M)</button>' in controls
    assert "fluid session 0.40 mL" in controls
    assert "0.15 mL of reward_correct, given between runs" in controls


@pytest.mark.parametrize(
    "name, phase",
    [("start", "between_runs"), ("check", "between_runs"), ("end", "awaiting_return"), ("end", "between_runs")],
)
def test_a_refused_session_command_shows_in_the_control_bar_escaped(name, phase):
    """The b3a-2 final review, I3: a start refused on the Setup tab, or a return refused
    on the End tab, showed only in the Runtime tab's feed. `serve.SERVICE_SENT` promises
    the page shows a refusal with its reason; the newest of the session's own commands'
    refusals shows in the always-visible control bar, as a reward's does."""
    refusals = (
        Refused("start", Box("jake"), "older"),
        Refused("reward", Box("jake"), "a reward's own"),
        Refused(name, Box("jake"), "why <b>&"),
        Refused("set", Box("jake"), "not a session command"),
    )

    controls = fragments(_between(phase=phase, refusals=refusals), view())["controls"]

    assert f'<span class="nm">last refused · {name}: why &lt;b&gt;&amp;</span>' in controls
    assert "older" not in controls and "not a session command" not in controls


def test_the_idle_control_bar_shows_a_refused_open_or_stranded_return():
    refusals = (Refused("open", Box("jake"), "no session opens while <b>"),)

    controls = fragments(idle(refusals=refusals), view())["controls"]

    assert '<span class="nm">last refused · open: no session opens while &lt;b&gt;</span>' in controls
    assert "last refused" not in fragments(idle(), view())["controls"]
    assert "last refused ·" not in fragments(_between(), view())["controls"]


def test_the_phases_the_page_lights_the_reward_in_are_the_ones_the_rig_gives_it_in():
    """The b3a-2 final review, m3: `taskd.OUTSIDE_A_RUN` decides in which phases outside a
    run the rig gives a hand reward, and `web._hand_reward_now` repeats it. The page must
    light the button in exactly those phases -- and during a run only while paused."""
    from wl_xcon.taskd import OUTSIDE_A_RUN
    from wl_xcon.web import _hand_reward_now

    phases = ("", "running", "between_runs", "awaiting_return", "closed")
    lit = {phase for phase in phases if _hand_reward_now(frame(service=True, phase=phase))}

    assert lit == set(OUTSIDE_A_RUN)
    assert not any(_hand_reward_now(frame(service=False, phase=phase)) for phase in phases)
    assert _hand_reward_now(frame(service=True, phase="running", paused_at=1_700_000_030.0))


def test_while_the_return_is_awaited_there_is_no_run_to_start():
    controls = fragments(_between(phase="awaiting_return"), view())["controls"]

    assert "session ended · waiting for the animal&#x27;s return" in controls
    assert 'data-cmd="start"' not in controls


def test_a_wlx_run_session_after_its_run_offers_no_hand_reward():
    """XC-184: its return is taken at its terminal, and the rig refuses a press then."""
    assert "give reward" not in fragments(frame(**STATES["awaiting return"]), view())["controls"]


def test_away_from_the_box_the_run_controls_are_greyed_with_the_sentence():
    parts = fragments(_between(preflight=PREFLIGHT), view(on_box=False, can_write=False))
    written = parts["controls"] + parts["pf-pill"] + parts["preflight"]

    buttons = re.findall(r"<button[^>]*data-cmd[^>]*>", written)
    assert buttons and all(" disabled" in tag for tag in buttons)
    assert CONTROLS_AT_THE_BOX in parts["controls"]


def test_the_control_bar_offers_the_task_the_trials_and_the_preflight_as_the_mockup_draws_them():
    """The mockup's toolbar (`task-sel`, `pf-pill`), with the run's trial count beside the
    task (the b3a-2 plan, decision 6): the select's options are a fragment, the count is
    static, and it starts at `wlx run --trials`'s default. Since the console interface rework's
    Task 8 the run's buttons (`controls`) stand in the one bar that stays in view, before the
    session's details behind *session*, where the next run's task, plan and pre-flight are."""
    document = page(fragments(_between(), view()), stale_after_s=30.0, nonce="n0nce", can_write=True)

    assert '<label class="tsel" for="task-sel"><span class="k">Task</span><select id="task-sel" aria-label="task">' in document
    assert (
        f'<input class="field mono" id="run-trials" value="{RUN_TRIALS}" inputmode="numeric" '
        f'autocomplete="off" aria-label="trials">'
    ) in document
    assert RUN_TRIALS == 1000
    assert document.index('id="controls"') < document.index('id="session"') < document.index(
        'id="task-sel"') < document.index('id="pf-pill"')
    assert "<h2>Pre-flight</h2>" in document and "<h2>Session</h2>" in document
    assert document.index('id="pf-panel"') < document.index('id="setup"')


def test_a_run_going_in_a_wlx_taskd_session_gives_no_hand_reward_until_xc_157():
    """XC-157: during a trial the rig refuses a manual reward, so the page greys the
    button with the reason -- a `wlx taskd` session's being a service is not enough."""
    controls = fragments(frame(service=True, phase="running", paused_at=None), view())["controls"]

    assert re.search(r'data-cmd="reward" disabled title="[^"]+"', controls)
    assert html.escape(REWARD_ONLY_PAUSED) in controls


HOSTILE = 'x"><b>'


def test_a_hostile_name_reaches_no_attribute_unescaped():
    """Every place a rig-supplied name becomes an attribute value or a label: the
    acknowledgement's `data-ack`, `data-task` on the panel and on *start run*, the
    option's value and label, and *start run*'s `title`."""
    preflight = Preflight(
        HOSTILE,
        (
            PreflightItem(HOSTILE, "unknown", "s"),
            PreflightItem(HOSTILE + "2", "fail", "s"),
        ),
    )
    shown = fragments(_between(preflight=preflight, offered_tasks=(HOSTILE,)), view())
    escaped = html.escape(HOSTILE)
    for name in ("preflight", "controls", "task-sel"):
        assert '"><b>' not in shown[name], name
    assert f'data-ack="{escaped}"' in shown["preflight"]
    assert f'<div class="pf" data-task="{escaped}">' in shown["preflight"]
    assert f'data-task="{escaped}"' in shown["controls"]
    assert f'title="pre-flight: {html.escape(HOSTILE + "2")} failing"' in shown["controls"]
    assert f'<option value="{escaped}">{escaped}</option>' == shown["task-sel"]
    assert fragments(idle(offered_tasks=(HOSTILE,)), view())["task-sel"] == shown["task-sel"]


def test_the_summary_ends_a_wlx_taskd_session_in_two_steps():
    """The b3a-2 plan, decision 12 (b3a-1 decision 6): *end session* while the session is
    open -- during a run too, which it stops first -- then *record return…*, the second
    step, while the return is awaited. A `wlx run` session's return is its terminal's."""
    open_ = (
        '<span class="pill neutral">open</span><button type="button" class="btn small '
        'danger" data-cmd="end" data-session="2027-01-14_01">end session</button>'
    )
    for phase in ("between_runs", "running"):
        assert fragments(_between(phase=phase), view())["end-actions"] == open_
    assert fragments(_between(phase="awaiting_return"), view())["end-actions"] == (
        '<span class="pill warn">ended · awaiting the return</span><button type="button" '
        'class="btn small danger" data-return="2027-01-14_01">record return…</button>'
    )
    assert fragments(_between(phase="closed"), view())["end-actions"] == (
        '<span class="pill ok">ended</span>'
    )
    assert "<button" not in fragments(frame(**STATES["awaiting return"]), view())["end-actions"]
    assert fragments(idle(), view())["end-actions"] == '<span class="pill neutral">none</span>'


def test_the_warning_is_answered_with_its_own_answers_naming_its_mark_and_session():
    """Spec §6.2: a far departure is confirmed or amended, a far return confirmed or
    typed again -- buttons for the frame's own answers, which the page's script sends
    only as the answer to this question (the b3a-2 plan, decision 10)."""
    departure = fragments(
        idle(question=Question("departure", "2027-01-14_01", 1.0, "far", ("confirm", "amend"))),
        view(),
    )["banners"]
    returning = fragments(
        _between(
            phase="awaiting_return",
            question=Question("return", "2027-01-14_01", 1.0, "far", ("confirm", "re-type")),
        ),
        view(),
    )["banners"]
    lan = fragments(
        idle(question=Question("departure", "2027-01-14_01", 1.0, "far", ("confirm", "amend"))),
        view(can_write=False),
    )["banners"]

    assert (
        '<button type="button" class="btn small" data-answer="confirm" data-mark="departure" '
        'data-session="2027-01-14_01">confirm</button>'
    ) in departure
    assert (
        '<button type="button" class="btn small" data-answer="amend" data-mark="departure" '
        'data-session="2027-01-14_01">amend…</button>'
    ) in departure
    assert (
        'data-answer="re-type" data-mark="return" data-session="2027-01-14_01">re-type</button>'
    ) in returning
    answers = re.findall(r"<button[^>]*data-answer[^>]*>", lan)
    assert answers and all(" disabled" in tag for tag in answers)


def test_the_end_tab_shows_the_closed_sessions_summary_from_an_idle_frame():
    """The b3a-2 final review, I2 (spec §6.2; the v12 mockup's `closed` state; §4.0 puts
    the supplement owed there): once the return is recorded the page is idle, and the End
    tab shows the closed session's summary, rendered as any closed frame's is, naming its
    session, until the next opens -- then *no session* again."""
    closed = frame(
        phase="closed", stop_kind="operator", stopped_because="stopped by jake",
        service=True, shortfall_ml=112.5, fluid_session_ml=0.3,
    )

    panes = fragments(idle(closed=closed), view())

    assert panes["end"] == fragments(closed, view())["end"], "one renderer for a closed frame"
    assert "Supplement owed" in panes["end"] and "112.50" in panes["end"]
    assert "2027-01-14_01" in panes["end-actions"] and "closed" in panes["end-actions"]
    assert "<script" not in fragments(
        idle(closed=replace(closed, session_id="<script>x", subject="<b>")), view()
    )["end-actions"]
    assert fragments(idle(), view())["end"] == fragments(None, view())["end"]
    assert fragments(idle(), view())["end-actions"] == '<span class="pill neutral">none</span>'


def test_the_closed_summary_keeps_an_unknown_day_unknown():
    closed = frame(phase="closed", stop_kind="operator", service=True, shortfall_ml=None, fluid_today_ml=None)

    end = fragments(idle(closed=closed), view())["end"]

    assert "0.00</span><span class=\"unit\">mL" not in end
    assert end == fragments(closed, view())["end"]


def test_a_stranded_animals_return_is_recorded_from_its_banner_naming_its_session():
    """XC-176: `Service._open`'s refusal says "Resume it, or record its return with End
    session, naming its session", and this is where its return is recorded. A record
    that cannot be read is repaired by hand first, so it has no button."""
    banners = fragments(
        idle(stranded=(Stranded("2027-01-13_01", "B", 1_700_000_000.0), Stranded("2027-01-13_02", "", None))),
        view(),
    )["banners"]

    assert (
        '<button type="button" class="btn small danger" data-return="2027-01-13_01">'
        "end session…</button>"
    ) in banners
    assert 'data-return="2027-01-13_02"' not in banners
    assert "Idle" not in banners, "nothing opens while an animal is stranded"


def test_the_idle_page_offers_a_new_session_and_says_which_animals_and_tasks_there_are():
    """Spec §6.1: "the page shows *no session open* beside the form that opens one"; the
    mockup's Session panel has *new session* too. Greyed while an animal is stranded."""
    parts = fragments(idle(), view())
    stranded = fragments(idle(stranded=(Stranded("2027-01-13_01", "B", 1_700_000_000.0),)), view())
    button = '<button type="button" class="btn small primary" data-cmd="new">new session</button>'

    assert button in parts["banners"] and "no session open" in parts["banners"]
    assert button in parts["setup"]
    assert "<dt>animals</dt><dd>A, B</dd>" in parts["setup"]
    assert "<dt>tasks offered</dt><dd>fixation_detection.py</dd>" in parts["setup"]
    assert parts["dn-subject"] == (
        '<option value="">choose the animal</option>'
        '<option value="A">A</option><option value="B">B</option>'
    ), "the b3a-2 final review, I1: no animal is chosen until a person chooses one"
    assert re.search(r'data-cmd="new" disabled title="[^"]+">new session</button>', stranded["setup"])
    assert fragments(frame(), view())["dn-subject"] == '<option value="">no animal offered</option>'


def test_every_string_the_session_panes_show_is_escaped():
    parts = fragments(
        _between(
            session_id=EVIL,
            offered_tasks=(EVIL,),
            preflight=Preflight(EVIL, (PreflightItem(EVIL, "unknown", EVIL),)),
            question=Question(EVIL, EVIL, 1.0, EVIL, (EVIL,)),
        ),
        view(),
    )
    idle_parts = fragments(
        idle(animals=(EVIL,), offered_tasks=(EVIL,), stranded=(Stranded(EVIL, EVIL, 1.0),)),
        view(),
    )

    text = "".join(parts.values()) + "".join(idle_parts.values())
    assert "<script" not in text
    assert EVIL not in text


#: What a person types or chooses on the page's forms. Each is static, outside every
#: fragment, so no frame -- one a second while idle and between runs -- replaces it.
_TYPED = (
    "run-trials", "amend-to", "amend-why", "end-return", "ret-at",
    "dn-deployment", "dn-view", "dn-left", "dn-id", "dn-given",
)


def test_nothing_a_person_types_into_is_inside_a_fragment():
    """Review Focus 1 (the b3a-2 plan, decision 11)."""
    for parts in (fragments(_between(preflight=PREFLIGHT), view()), fragments(idle(), view())):
        document = page(parts, stale_after_s=30.0, nonce="n0nce", can_write=True)
        for name in _TYPED:
            assert document.count(f'id="{name}"') == 1, name
            assert not any(f'id="{name}"' in pane for pane in parts.values()), name


def test_the_new_session_dialog_asks_what_an_open_needs_and_offers_no_now_for_the_departure():
    """Spec §6.2's fields, in the mockup's `dlg-new` (the b3a-2 plan, decision 6): no rig
    and no "saved to" (`wlx taskd`'s are fixed), the id typed, and the departure empty --
    the terminal's parser has no `now` for it."""
    document = page(fragments(idle(), view()), stale_after_s=30.0, nonce="n0nce", can_write=True)

    assert re.search(r'<div class="scrim" id="dlg-new"[^>]*hidden>', document)
    for field, label in (
        ("dn-subject", "subject"), ("dn-deployment", "deployment"), ("dn-view", "setup"),
        ("dn-left", "←cage at"), ("dn-id", "id"), ("dn-given", "given today, mL"),
    ):
        assert f'<label class="sub" for="{field}">{label}</label>' in document, field
    assert (
        '<select id="dn-deployment" required><option value="">choose the deployment</option>'
        '<option value="rig_fixed">head-fixed</option><option value="rig_chaired">chaired</option></select>'
    ) in document, "WEL-06: each session declares its deployment, with no default (XC-355)"
    assert '<option value="direct">direct view</option><option value="stereoscope">stereoscope</option>' in document
    left = re.search(r'<input[^>]*id="dn-left"[^>]*>', document).group(0)
    assert " value=" not in left and "now" not in left
    assert '<button class="btn primary" id="dn-ok" type="button">open session</button>' in document
    assert "<title>xcon console</title>" in document and "expcontroller" not in document


def test_end_session_asks_first_and_takes_the_return_now_or_later():
    document = page(fragments(_between(), view()), stale_after_s=30.0, nonce="n0nce", can_write=True)

    assert "<h2>Summary</h2>" in document
    assert re.search(r'<div class="inline crit" id="end-confirm"[^>]*hidden>', document)
    assert html.escape(END_CONFIRM) in document
    assert END_CONFIRM.startswith("end the session?")
    assert "the head's release is recorded then" in END_CONFIRM
    assert "leave it blank" in END_CONFIRM
    assert re.search(r'<div class="inline info" id="return-form"[^>]*hidden>', document)
    assert re.search(r'<div class="inline info" id="amend-form"[^>]*hidden>', document)


def test_away_from_the_box_every_session_form_is_greyed():
    lan = page(fragments(_between(preflight=PREFLIGHT), view(can_write=False)), stale_after_s=30.0, nonce="n0nce")

    for control in (
        "task-sel", "plan-sel", "run-trials", "dn-subject", "dn-deployment", "dn-view", "dn-left",
        "dn-id", "dn-given", "dn-ok", "end-return", "end-yes", "ret-at", "ret-yes",
        "amend-to", "amend-why", "amend-yes",
    ):
        assert re.search(r'id="' + control + r'"[^>]* disabled', lan), control


def test_away_from_the_box_every_session_button_in_a_fragment_is_greyed():
    """The fragments' own write buttons, as the static forms' are above: *end session*
    and *record return…* in the Summary, a stranded animal's *end session…*, *new
    session* in the banner and the Session panel, and the warning's answers -- each
    disabled on a page that may not write (fix round 1 of Task 5's review)."""
    lan = view(on_box=False, can_write=False)
    frames = (
        _between(),
        _between(
            phase="awaiting_return",
            question=Question("return", "2027-01-14_01", 1.0, "far", ("confirm", "re-type")),
        ),
        idle(),
        idle(stranded=(Stranded("2027-01-13_01", "B", 1_700_000_000.0),)),
    )
    written = "".join(
        parts["end-actions"] + parts["banners"] + parts["setup"]
        for parts in (fragments(shown, lan) for shown in frames)
    )

    buttons = re.findall(r"<button[^>]*data-(?:cmd|return|answer)[^>]*>", written)
    for needle in (
        'data-cmd="end"', 'data-return="2027-01-14_01"', 'data-return="2027-01-13_01"',
        'data-cmd="new"', 'data-answer="re-type"',
    ):
        assert any(needle in tag for tag in buttons), needle
    assert all(" disabled" in tag for tag in buttons)


def _function(name: str) -> str:
    """The body of the page script's function `name`, from its opening line to its own
    closing brace at two spaces' indent."""
    return re.search(rf"function {name}\((.*?)\) \{{(.*?)\n  \}}", _SCRIPT, re.S).group(2)


def _listener(element: str) -> str:
    """The body of the page script's click listener on `element`."""
    return re.search(
        rf'el\("{element}"\)\.addEventListener\("click", function \(\) \{{(.*?)\n  \}}\);',
        _SCRIPT,
        re.S,
    ).group(1)


def test_a_frame_keeps_the_option_chosen_in_a_select():
    """Review Focus 1: a frame re-renders the task and subject selects' options; the
    option a person chose stays chosen while it is still offered."""
    swap = _function("swap")

    assert ('var chosen = node && node.tagName === "SELECT" && id !== "plan-sel" ? node.value : '
            "null;") in swap
    assert swap.index("var chosen") < swap.index("node.innerHTML = html;") < swap.index(
        "choose(node, chosen);"
    )
    assert 'if (id === "preflight") { restoreAcks(); restoreStarts(); }' in swap
    assert "if (option.value === value) { select.value = value; }" in _function("choose")


def test_no_acknowledgement_outlives_the_run_or_the_task_it_was_ticked_for():
    """Review Focus 4 (the b3a-2 plan, decision 9): the ticks are the person's, kept
    across a re-render, sent with the start, and cleared by a start or a new pre-flight."""
    take, start = _function("takePreflight"), _function("startRun")

    assert "acked = {};" in take and "acked = {};" in start
    assert start.index("acked = {};") < start.index("post(")
    assert 'if (box.checked) { acknowledged.push(box.getAttribute("data-ack")); }' in start
    assert (
        'else if (e.target.matches("input[data-ack]")) '
        '{ acked[e.target.getAttribute("data-ack")] = e.target.checked; }'
    ) in _SCRIPT
    assert "box.checked = acked[box.getAttribute(\"data-ack\")] === true;" in _function("restoreAcks")


def test_start_sends_the_task_whose_preflight_is_shown_and_only_while_it_is_chosen():
    """The b3a-2 plan, decision 8; the page's values are none, the task's own (decision 1), but
    what a person picked in the run's start, with the stage it starts at (the pop-out search
    build's Task 6: `runStart`)."""
    start = _function("startRun")

    assert "var button = el(\"controls\").querySelector('[data-cmd=\"start\"]');" in start
    assert 'var task = button ? button.getAttribute("data-task") : "";' in start
    assert 'var plan = button ? (button.getAttribute("data-plan") || null) : null;' in start
    assert "if (!task || task !== chosenTask() || plan !== chosenPlan()) {" in start
    assert "if (!Number.isInteger(trials) || trials < 1) {" in start
    assert (
        'post({ kind: "start", task: task, values: start.values, trials: trials,\n'
        '           acknowledged: acknowledged, plan: plan, start_block: start.block });'
    ) in start
    assert start.index("var start = runStart();") < start.index("post(")
    # The check sends the stage picked too (the pop-out search build's Task 7), its task checks
    # judging a start there; a pre-flight for another task or plan forgets it.
    take = _function("takePreflight")
    assert ('post({ kind: "check", task: task, values: {}, plan: chosenPlan(), '
            "start_block: stage || null });") in take
    assert "var stage = pickedStage();" in take and "if (stage === undefined) { picked = {}; }" in take
    picked = _function("pickedStage")
    assert ("if (!button || button.getAttribute(\"data-task\") !== chosenTask() ||\n"
            "        (button.getAttribute(\"data-plan\") || null) !== chosenPlan()) "
            "{ return undefined; }") in picked
    assert "return stage && stage.selectedIndex > 0 ? stage.value : null;" in picked


def test_a_new_session_is_sent_with_every_field_the_dialog_asks_as_typed():
    body = _function("openSession")

    for field in (
        'session_id: el("dn-id").value.trim(),',
        'animal: el("dn-subject").value,',
        'deployment: el("dn-deployment").value,',
        'view: el("dn-view").value,',
        'departure: el("dn-left").value.trim(),',
        "delivered_today: today,",
        "answer: null,",
        "amend_to: null,",
        'amend_reason: ""',
    ):
        assert field in body, field
    assert 'var today = given === "" ? null : Number(given);' in body
    assert "lastOpen = Object.assign({}, request);" in body
    assert body.index("lastOpen = Object.assign({}, request);") < body.index("post(")


def test_the_new_session_dialog_forgets_what_was_typed_once_the_session_it_sent_opens():
    """The b3a-2 final review, I1: the dialog reopened with the last session's departure,
    id and fluid given today -- a departure within thirty minutes of now is taken on trust,
    and the fluid figure feeds the day's floor. They are cleared, and the subject set back
    to its placeholder, **only once the page shows the session it sent open** (the
    Summary's *end session* names it), so a refused or unanswered open keeps what was
    typed for a retry, and no other frame clears it."""
    settle, swap, send = _function("settleOpen"), _function("swap"), _function("openSession")

    assert 'if (id === "end-actions") { settleOpen(); }' in swap
    assert "pendingOpen = request.session_id;" in send
    assert 'if (!request.animal) { el("dn-msg").textContent = "not sent: choose the animal"; return; }' in send
    assert (
        'if (!request.deployment) { el("dn-msg").textContent = '
        '"not sent: a deployment must be chosen"; return; }'
    ) in send, "WEL-06: no open goes out without a deployment (XC-355)"
    assert send.index("must be chosen") < send.index("post(")
    assert 'el("dn-deployment").value = "";' in settle, "the next session's starts with none chosen"
    assert "if (pendingOpen === null) { return; }" in settle
    assert (
        "var shown = el(\"end-actions\").querySelector('[data-cmd=\"end\"][data-session]');"
    ) in settle
    assert 'if (!shown || shown.getAttribute("data-session") !== pendingOpen) { return; }' in settle
    guard = settle.index('!== pendingOpen) { return; }')
    for cleared in ('el("dn-left").value = "";', 'el("dn-id").value = "";', 'el("dn-given").value = "";',
                    'el("dn-subject").value = "";', "pendingOpen = null;"):
        assert cleared in settle and settle.index(cleared) > guard, cleared
    assert "pendingOpen" not in _function("onFrame"), "not on every frame"


def test_a_preflight_items_sentence_takes_the_rows_width():
    """The b3a-2 final review, m4: the pre-flight's items were laid out in columns of at
    least 320 px, which left each sentence a sliver -- the pump calibration's wrapped
    about twenty lines. One item per row, across the panel; and the end confirmation's
    return field is wide enough for its placeholder."""
    from wl_xcon.web import _CSS

    pf = re.search(r"\n\.pf \{([^}]*)\}", _CSS).group(1)
    assert "auto-fill" not in pf and "grid-template-columns: minmax(0, 1fr);" in pf
    width = re.search(r"#end-return \{ width: (\d+)ch; \}", _CSS)
    assert width and int(width.group(1)) >= len("now, HH:MM, or blank for later")


def test_a_message_for_the_dialog_is_shown_in_it_not_behind_its_scrim():
    """Task 6's deferred point, with I3: while *New session* is open, `post`'s own "not
    sent: give your name" went to the control bar's line behind the dialog's scrim."""
    tell = _function("tell")

    assert 'if (!el("dlg-new").hidden) { el("dn-msg").textContent = text; }' in tell


def test_choosing_a_task_takes_the_preflight_only_between_runs():
    """The b3a-2 final review, m1: choosing a task sent a check in every phase, and each
    put a refusal on the feed while idle, running or awaiting the return. The pre-flight
    pill is a button only between runs (`_pf_pill`), and the script reads that."""
    assert "return Boolean(el(\"pf-pill\").querySelector('[data-cmd=\"check\"]'));" in _function("betweenRuns")
    assert 'data-cmd="check"' in fragments(_between(), view())["pf-pill"]
    for outside in (frame(service=True), _between(phase="awaiting_return"), idle(), None):
        assert 'data-cmd="check"' not in fragments(outside, view())["pf-pill"]


def test_an_answer_re_sends_the_time_as_typed_and_only_for_a_warning_this_page_raised():
    """The b3a-2 plan, decision 10: *confirm* re-sends the open or the return this page
    sent, with its answer; *amend…* the open with the corrected time and the reason; a
    warning whose session this page did not send is not answered."""
    body = _function("answerWarning")

    assert 'if (given === "re-type") { openReturn(session); return; }' in body
    assert 'var sent = which === "departure" ? lastOpen : lastEnd;' in body
    assert "if (!sent || sent.session_id !== session) {" in body
    assert body.index("if (!sent || sent.session_id !== session) {") < body.index("post(")
    assert 'Object.assign({}, sent, { answer: "confirm" })' in body
    assert "Object.assign({}, sent, { confirm: true })" in body
    assert (
        'post(Object.assign({}, lastOpen, { answer: "amend", amend_to: '
        'el("amend-to").value.trim(), amend_reason: el("amend-why").value.trim() }));'
    ) in _listener("amend-yes")


def test_end_session_sends_the_return_as_typed_or_later_and_a_return_needs_a_time():
    """The b3a-2 plan, decision 12: step one's return may be left blank for later; the
    return form's may not."""
    end, ret = _listener("end-yes"), _listener("ret-yes")

    assert 'returned: returned === "" ? null : returned, confirm: false' in end
    assert 'if (returned !== "") { lastEnd = Object.assign({}, request); }' in end
    assert (
        'if (!returned) { tell("not sent: give the time the animal went back into its home '
        'cage, or now", "crit"); return; }'
    ) in ret
    assert "lastEnd = Object.assign({}, request);" in ret


def test_the_session_forms_are_opened_from_the_buttons_the_panes_render():
    command = re.search(r"function command\(cmd\) \{(.*?)\n  \}", _SCRIPT, re.S).group(1)

    for line in (
        'else if (cmd === "new") { openNew(); }',
        'else if (cmd === "check") { takePreflight(true); }',
        'else if (cmd === "start") { startRun(); }',
        'else if (cmd === "end") { askEnd(); }',
    ):
        assert line in command, line
    handler = re.search(
        r'document\.addEventListener\("click", function \(e\) \{(.*?)\n  \}\);', _SCRIPT, re.S
    ).group(1)
    assert 'var answering = e.target.closest("[data-answer]");' in handler
    assert 'openReturn(returning.getAttribute("data-return"))' in handler
    assert handler.index("[data-answer]") < handler.index("[data-cmd]")


def test_end_session_opens_its_confirmation_and_posts_nothing_until_end_yes():
    """One click on *end session* once posted `{kind: "end"}` and ended the session with
    no confirmation. Now only the confirmation's *end-yes* (or the return form's *ret-yes*)
    posts an end; every function a button opens a form with posts nothing."""
    command = re.search(r"function command\(cmd\) \{(.*?)\n  \}", _SCRIPT, re.S).group(1)

    assert 'else if (cmd === "end") { askEnd(); }' in command
    assert 'else { post({ kind: cmd }); }' in command
    assert command.index('cmd === "end"') < command.index("post({ kind: cmd })")
    for opener in ("askEnd", "openNew", "openReturn"):
        assert "post(" not in _function(opener), opener
    assert 'el("end-confirm").hidden = false;' in _function("askEnd")
    assert 'el("dlg-new").hidden = false;' in _function("openNew")
    assert 'el("return-form").hidden = false;' in _function("openReturn")
    assert "returnFor = session;" in _function("openReturn")
    assert 'kind: "end"' not in re.sub(
        r'el\("(end-yes|ret-yes)"\)\.addEventListener\("click".*?\n  \}\);', "", _SCRIPT, flags=re.S
    )



def test_a_resumable_stranded_session_offers_resume_beside_end_and_a_refused_one_says_why():
    """XC-026 Task 5: *resume session* is offered only when the record can carry one; a
    session that cannot be resumed says why, escaped, and keeps *end session...*."""
    can = fragments(
        idle(stranded=(Stranded("2027-01-13_01", "B", 1_700_000_000.0, resumable=True),)), view()
    )["banners"]
    cannot = fragments(
        idle(stranded=(Stranded("2027-01-13_01", "B", 1_700_000_000.0, False, "no <i>fluid</i> record"),)),
        view(),
    )["banners"]

    assert 'data-resume="2027-01-13_01"' in can and 'data-return="2027-01-13_01"' in can
    assert "It cannot be resumed" not in can
    assert 'data-resume=' not in cannot and 'data-return="2027-01-13_01"' in cannot
    assert "It cannot be resumed: no &lt;i&gt;fluid&lt;/i&gt; record." in cannot
    assert "<i>fluid" not in cannot
    assert "no session opens until it is resumed or its return recorded" in can
    assert "no session opens until it is resumed or its return recorded" in cannot


def test_a_resumed_session_says_so_in_its_banner_and_its_closed_summary():
    resumed = frame(resumed_at=1_700_000_000.0)
    clock = _clock_time(1_700_000_000.0)[:5]
    sentence = f"this session was resumed after its process stopped, at {clock}"

    banners = fragments(resumed, view())["banners"]
    closed = replace(resumed, phase="closed", stop_kind="operator", service=True)

    assert "Resumed" in banners and sentence in banners
    assert "Resumed" not in fragments(frame(), view())["banners"]
    assert sentence in fragments(closed, view())["end"]
    assert sentence in fragments(idle(closed=closed), view())["end"]
    assert "resumed" not in fragments(replace(closed, resumed_at=None), view())["end"]


def test_the_pages_script_posts_resume_session_for_a_click_on_resume():
    handler = re.search(
        r'document\.addEventListener\("click", function \(e\) \{(.*?)\n  \}\);', _SCRIPT, re.S
    ).group(1)

    assert 'var resuming = e.target.closest("[data-resume]");' in handler
    assert (
        'post({ kind: "resume_session", session_id: resuming.getAttribute("data-resume") })'
    ) in handler
    assert handler.index("[data-resume]") < handler.index("[data-return]")


_MEMBER = Member(name="Jake Westerberg", account="u", issuer="https://wl.works/api/auth", token_id="j")


def test_a_member_and_a_box_name_render_apart():
    assert 'class="who-m"' in _who(_MEMBER) and "(wl.works)" in _who(_MEMBER)
    assert 'class="who-b"' in _who(Box("jake")) and "(box, unverified)" in _who(Box("jake"))
    assert _who(None) == ""


def test_a_box_name_typed_to_look_like_a_member_still_renders_as_a_box():
    """b2b Review Focus 2: a typed name dressed as a member's still reads as typed."""
    shown = _who(Box("Jake Westerberg (wl.works)"))

    assert 'class="who-b"' in shown and 'class="who-m"' not in shown
    assert shown.endswith('<span class="nm">(box, unverified)</span></span>')


def test_a_box_name_is_escaped_where_a_who_is_built():
    assert "<b>" not in _who(Box("<b>x</b>")) and "&lt;b&gt;" in _who(Box("<b>x</b>"))


def _apart(html_: str) -> None:
    assert 'class="who-m"' in html_ and 'class="who-b"' in html_, html_


def test_every_pane_that_names_who_shows_a_member_and_a_box_apart():
    """One frame per site, so a site left printing a bare name fails alone."""
    at = 1_700_000_000.0
    other = Member(name="Sam", account="v", issuer="https://wl.works/api/auth", token_id="k")
    # The feed's control lines.
    _apart(fragments(frame(controls=(
        Control("pause", _MEMBER, at, "paused"), Control("resume", Box("sam"), at, "resumed"),
    )), view())["rt-changes"])
    # The feed's staged lines.
    _apart(fragments(frame(staged=(
        Staged("fix_hold", 0.3, 0.4, _MEMBER, False), Staged("reward_correct", 0.1, 0.2, Box("sam"), True),
    )), view())["rt-changes"])
    # The feed's refusal lines.
    _apart(fragments(frame(refusals=(
        Refused("reward", _MEMBER, "no"), Refused("pause", Box("sam"), "no"),
    )), view())["rt-changes"])
    # The idle page's refusals.
    _apart(fragments(idle(refusals=(Refused("start", _MEMBER, "no"), Refused("end", Box("sam"), "no"))), view())["rt-changes"])
    # The parameter card's staged line.
    for who in (_MEMBER, Box("sam")):
        card = fragments(frame(staged=(Staged("fix_hold", 0.3, 0.4, who, False),)), view())["params"]
        assert f"by {_who(who)}" in card
    # The scheduled-stop cell.
    for who in (other, Box("sam")):
        strip = fragments(frame(scheduled_stop=ScheduledStop("clock", at + 3600, who, "at 14:30")), view())["strip"]
        assert f"set by {_who(who)}" in strip


# --- P4d-2b b2b slice 2, Task 10: the https page's modes, gating and script ----------

_SIGNIN = SignIn(
    authorize="https://wl.works/oauth/authorize?x=1&y=2",
    token_endpoint="https://wl.works/oauth/token",
    client_id="rig<1>",
    page="https://rig.lab:8443/",
    resource="https://rig.lab:8443",
)
_NO_KEYS = SignIn(
    authorize=None,
    token_endpoint=None,
    client_id="rig1",
    page="https://rig.lab:8443/",
    resource="https://rig.lab:8443",
    unavailable="the rig has not reached wl.works to check sign-ins; use the rig PC",
)


def _markup(document: str) -> str:
    """The page without its script, which names `data-signin` to find those controls."""
    return re.sub(r"<script.*?</script>", "", document, flags=re.S)


def _https_view(**overrides):
    return view(can_write=False, on_box=False, signin=True, **overrides)


def test_gate_leaves_the_boxs_own_reason_alone_and_greys_the_rest_by_mode():
    own = ' disabled title="its own reason"'
    assert _gate(view(), own) == own and _gate(view()) == ""
    assert _gate(_https_view(), own) == own
    assert _gate(_https_view()) == (
        f' disabled data-signin title="{SIGN_IN_FIRST}"'
    )
    assert SIGN_IN_FIRST == "sign in with wl.works to use the controls"
    lan = view(can_write=False, on_box=False)
    assert _gate(lan) == f' disabled title="{CONTROLS_AT_THE_BOX}"'
    assert _gate(replace(lan, https_page=True)) == (
        f' disabled title="{html.escape(CONTROLS_ELSEWHERE)}"'
    )
    assert "data-signin" not in _gate(lan)
    assert CONTROLS_ELSEWHERE == (
        "controls work at the rig PC, or signed in on this rig's https page"
    )


def test_on_the_https_page_a_control_greyed_for_its_own_reason_never_carries_data_signin():
    controls = fragments(frame(), _https_view())["controls"]
    reward = re.search(r"<button[^>]*data-cmd=\"reward\"[^>]*>", controls).group(0)
    pause = re.search(r"<button[^>]*data-cmd=\"pause\"[^>]*>", controls).group(0)

    assert REWARD_ONLY_PAUSED in reward and "data-signin" not in reward
    assert "data-signin" in pause and " disabled" in pause
    # Nothing on the https page says controls work only at the rig PC.
    assert CONTROLS_AT_THE_BOX not in controls


def test_the_https_page_carries_its_sign_in_on_body_and_renders_sign_in_and_out():
    document = page(
        fragments(frame(), _https_view()),
        stale_after_s=30.0,
        nonce="n0nce",
        signin=_SIGNIN,
    )

    assert 'data-signin="1"' in document
    assert 'data-authorize="https://wl.works/oauth/authorize?x=1&amp;y=2"' in document
    assert 'data-token-endpoint="https://wl.works/oauth/token"' in document
    assert 'data-client="rig&lt;1&gt;"' in document
    assert 'data-page="https://rig.lab:8443/"' in document
    assert 'data-resource="https://rig.lab:8443"' in document
    assert 'id="signin"' in document and 'id="signout"' in document
    assert 'id="rename"' not in document and 'id="who"' not in document
    for control in ('id="sched-kind"', 'id="task-sel"', 'id="amend-yes"', 'id="dn-ok"'):
        assert re.search(control + r"[^>]* disabled data-signin", document), control


def test_a_rig_without_keys_says_so_and_offers_no_sign_in():
    document = page(
        fragments(frame(), _https_view()),
        stale_after_s=30.0,
        nonce="n0nce",
        signin=_NO_KEYS,
    )

    assert "the rig has not reached wl.works to check sign-ins; use the rig PC" in document
    assert 'id="signin"' not in document and 'id="signout"' not in document


def test_the_box_page_is_unchanged_by_the_https_page_existing():
    document = page(
        fragments(frame(), view()), stale_after_s=30.0, nonce="n0nce", can_write=True
    )

    assert 'id="who"' in document and 'id="rename"' in document
    assert "data-signin" not in _markup(document)


def test_the_rig_pc_page_says_why_the_https_page_is_off_and_no_other_page_does():
    """b2b-ready §3.1: the box's own page says why; a lab-network viewer is told only where
    controls work (`CONTROLS_AT_THE_BOX`), and nothing is said while the https page serves."""
    why = "cannot serve https on 0.0.0.0:8443: [Errno 48] Address already in use"
    box = page(fragments(frame(), view()), stale_after_s=30.0, nonce="n0nce", can_write=True, https_off=why)
    lan = page(
        fragments(frame(), view(can_write=False, on_box=False)),
        stale_after_s=30.0, nonce="n0nce", https_off=why,
    )
    serving = page(fragments(frame(), view()), stale_after_s=30.0, nonce="n0nce", can_write=True)

    assert 'id="https-off"' in box
    assert html.unescape(box).count(f"the rig's https page is off: {why}") == 1
    assert 'id="https-off"' not in lan and 'id="https-off"' not in serving


def test_a_lan_page_says_where_else_controls_work_only_when_an_https_page_exists():
    lan = view(can_write=False, on_box=False)
    without = page(fragments(frame(), lan), stale_after_s=30.0, nonce="n0nce")
    with_https = page(
        fragments(frame(), replace(lan, https_page=True)),
        stale_after_s=30.0,
        nonce="n0nce",
        https_page=True,
    )

    assert CONTROLS_AT_THE_BOX in without and CONTROLS_ELSEWHERE not in without
    assert CONTROLS_ELSEWHERE in with_https
    assert "data-signin" not in _markup(without) + _markup(with_https)


def test_the_sign_in_script_uses_pkce_and_keeps_its_tokens_in_session_storage_only():
    assert '"offline_access"' in _SCRIPT and '"S256"' in _SCRIPT
    assert 'credentials: "omit"' in _SCRIPT
    assert "sessionStorage" in _SCRIPT and "Authorization" in _SCRIPT
    # The box's name keeps its `localStorage` (two uses), and so do the setting opened in each
    # settings tab's editor (three: read, kept, dropped; the summary and editor design's goal 5,
    # which retired the sections' last-left state), the pins and the demo keys' first visit (two
    # each, the console interface rework's Task 8); the sign-in never touches it.
    assert _SCRIPT.count("localStorage") == 9
    assert "console.log" not in _SCRIPT
    # The authorization code leaves the address bar before anything else is done with it.
    assert _SCRIPT.index("history.replaceState") < _SCRIPT.index("tokenRequest({")
    assert "document.cookie" not in _SCRIPT


# --- Task 10 fix round 1: the script's structure, pinned as the file's other script tests do


def _script_between(start: str, end: str) -> str:
    return _SCRIPT.split(start, 1)[1].split(end, 1)[0]


def test_every_renewal_is_the_one_in_flight_so_a_token_is_never_presented_twice():
    renew = _script_between("  function renew() {", "  function renewNow() {")
    assert "var renewing = null;" in _SCRIPT
    assert "if (renewing) { return renewing; }" in renew
    assert "renewNow().then(resolve, function () { resolve(false); });" in renew
    assert "renewing = null;" in renew
    # Only `renew` starts a renewal; every caller goes through it.
    assert _SCRIPT.count("renewNow()") == 2  # its call and its definition
    assert _SCRIPT.count('grant_type: "refresh_token"') == 1


def test_a_held_reward_stays_held_through_a_sign_in_state_change():
    applied = _script_between("  function applySignIn() {", "  function startSignIn() {")
    assert ('if (node.hasAttribute("data-held") || node.hasAttribute("data-demo-locked")) '
            '{ return; }') in applied
    assert applied.index("data-held") < applied.index("node.disabled")
    swap = _script_between("  function swap(id, html) {", "  function release() {")
    assert swap.index("applySignIn();") < swap.index("holdReward();")
    # The held button is released through `applySignIn`, which disables it if signed out.
    released = _script_between("  function reward() {", "  // P4d-2b b3a-2 (spec §6.2): a run")
    assert released.index("held.disabled = false;") < released.index("applySignIn();")
    # A press's end makes every box current through `settle`, which ends with the sign-in's gray.
    assert "settle();" in _script_between("  function release() {", "  // The boxes as the page")
    assert "applySignIn();" in _script_between("  function settle() {", "  // **The drafts bar**")


def test_a_lapsed_tab_renews_on_load_and_whoami_reads_the_reason_word():
    init = _SCRIPT.split('if (el("signin")) {', 1)[1]
    assert "signin.expires - Date.now() < FRESH_FOR_MS) { return renew(); }" in init
    assert init.index("return renew();") < init.index("return whoami(true);")
    who = _script_between("  function whoami(mayRenew) {", "  // Resolves true when it exchanged")
    assert 'answer.reason === "expired" && mayRenew' in who
    assert 'answer.reason === "clock" || answer.reason === "no_keys"' in who
    assert who.index('"clock"') < who.index("forget(answer.said);")
    # After a renewal the new token is not asked to renew again, nor by either retry (the rig
    # out of reach, and since the final review's M2 `clock` or `no_keys`).
    assert _SCRIPT.count("whoami(false)") == 4 and _SCRIPT.count("whoami(true)") == 1


def test_the_script_says_what_failed_and_does_not_fetch_a_missing_endpoint():
    post = _script_between("  function post(command, then, after) {", "  function deliver(")
    assert "this sign-in could not be renewed" in post and "done();" in post
    finish = _script_between("  function finishSignIn() {", "  // Every caller shares")
    assert finish.index('data-token-endpoint")) {') < finish.index("tokenRequest({")
    assert "could not reach wl.works to finish signing in" in finish
    assert "new URL(body.getAttribute(\"data-authorize\"))" in _SCRIPT
    assert "searchParams.set" in _SCRIPT
    assert "this sign-in was renewed; the command was not sent" in _SCRIPT
    applied = _script_between("  function applySignIn() {", "  function startSignIn() {")
    assert 'removeAttribute("title")' in applied and 'setAttribute("title"' in applied
    assert "var usable = signedIn() && confirmed;" in applied


def test_a_command_is_delivered_only_where_it_is_today():
    # `deliver` is its definition and two call sites (the https page's, the box's); a
    # renew-then-resend would add a third, and has to be argued for.
    assert _SCRIPT.count("deliver(") == 3


def test_a_control_with_its_own_reason_must_be_a_greying_one():
    with pytest.raises(ValueError):
        _gate(_https_view(), ' title="only a title"')
    with pytest.raises(ValueError):
        _gate(view(), "x")


def test_a_sign_out_stands_against_a_renewal_or_a_sign_in_still_in_flight():
    assert "var generation = 0;" in _SCRIPT
    forget = _script_between("  function forget(why) {", "  // The page signs itself out")
    assert "generation += 1;" in forget
    assert "generation += 1;" in _script_between("  function keep(answer, prior) {", "  function forget(why) {")
    # Each answer is dropped, before anything is kept, stored or shown, if the sign-in it
    # began from is gone.
    who = _script_between("  function whoami(mayRenew) {", "  // Resolves true when")
    assert who.index("var mine = generation;") < who.index("if (mine !== generation) { return false; }")
    assert who.index("if (mine !== generation)") < who.index("signin.name = answer.name;")
    finish = _script_between("  function finishSignIn() {", "  // Every caller shares")
    assert finish.index("if (mine !== generation)") < finish.index("keep(result.answer, null);")
    renew = _script_between("  function renewNow() {", "  function scheduleRenew() {")
    assert renew.index("if (mine !== generation)") < renew.index("keep(result.answer, prior);")
    # wl.works out of reach (the final review, I1): a sign-out during that renewal stands too.
    unreached = renew.split("    }, function () {\n", 1)[1]
    assert unreached.index("if (mine !== generation)") < unreached.index("return notRenewed(UNREACHED, RETRYING);")


def test_a_renewed_pair_is_stored_before_the_rig_confirms_it():
    renew = _script_between("  function renewNow() {", "  function scheduleRenew() {")
    assert renew.index("keep(result.answer, prior);") < renew.index("writeStore(SIGNIN_KEY, signin);")
    assert renew.index("writeStore(SIGNIN_KEY, signin);") < renew.index("whoami(false)")
    assert "nothing answered" not in _SCRIPT
    assert 'var UNCONFIRMED = "this rig has not confirmed the sign-in; trying again";' in _SCRIPT


def test_the_https_page_tells_its_script_how_often_to_try_again():
    document = page(fragments(frame(), _https_view()), stale_after_s=30.0, nonce="n0nce", signin=_SIGNIN)
    assert f'data-retry-ms="{SIGNIN_RETRY_MS}"' in document and SIGNIN_RETRY_MS == 30_000


def test_the_https_page_tells_its_script_how_often_to_ask_for_keys_again():
    document = page(fragments(frame(), _https_view()), stale_after_s=30.0, nonce="n0nce", signin=_NO_KEYS)
    assert f'data-recheck-ms="{KEYS_RECHECK_MS}"' in document and KEYS_RECHECK_MS == 60_000
    recheck = _SCRIPT.split("var recheck = function () {", 1)[1].split("setTimeout(recheck, RECHECK_MS);\n    }", 1)[0]
    assert 'if (answer.reason === "no_token") { window.location.reload(); return; }' in recheck
    assert recheck.count("window.location.reload()") == 1
    assert f'data-lock-wait-ms="{SIGNIN_LOCK_WAIT_MS}"' in document and SIGNIN_LOCK_WAIT_MS == 1000


def test_the_warnings_tab_shows_each_accepted_warning_with_its_kinds_and_who_accepted_it():
    pane = fragments(frame(), view())["warnings"]

    assert "a training session" in pane
    assert 'data-warn="default calibration"' in pane
    assert "accepted in training, piloting, recording" in pane and "jake" in pane


def test_with_no_session_open_the_tab_and_the_dialog_list_what_an_open_asks_to_accept():
    panes = fragments(idle(), view())

    assert "an open asks to accept" in panes["warnings"]
    assert 'data-warn="default calibration"' in panes["dn-warnings"]
    assert 'data-detail="the sRGB standard&#x27;s"' in panes["dn-warnings"]
    assert 'data-kinds="training piloting recording"' in panes["dn-warnings"]
    assert 'id="dn-accept"' in panes["dn-warnings"]


def test_a_warning_no_kind_accepts_is_shown_in_the_dialog_and_can_never_be_sent():
    """The engine B plan, call 21: listed, marked, and carrying no `data-warn`. The rig lists
    none since XC-352's E1 and E2 (the PI, 2026-10-11), which made a record that will not load,
    call 21's case, a warning every kind accepts: the row is a stand-in."""
    refused = WarningRow("calibration record", "it is not JSON", (), None, None)

    panes = fragments(idle(warnings=(refused,)), view())

    assert "data-warn" not in panes["dn-warnings"]
    assert "no session kind accepts this: every run's pre-flight fails on it" in panes["dn-warnings"]


def test_a_listing_fault_is_shown_as_one_and_not_as_a_warning():
    """The second review's Minor 2: the idle frame's fault row has no kinds, and is not a
    warning every run refuses."""
    fault = WarningRow("warnings", "the warnings an open asks to accept could not be listed: x",
                       (), None, None)

    pane = fragments(idle(warnings=(fault,)), view())["dn-warnings"]

    assert "could not be listed" in pane and "data-warn" not in pane
    assert "no session kind accepts this" not in pane


def test_the_accept_box_is_drawn_only_when_a_row_can_be_accepted():
    """D7: a box that accepts nothing would read as accepting something."""
    refused = WarningRow("calibration record", "it is not JSON", (), None, None)
    fault = WarningRow("warnings", "could not be listed: x", (), None, None)
    good = WarningRow("default calibration", "the sRGB standard's", SESSION_KINDS, None, None)

    assert "dn-accept" not in fragments(idle(warnings=(refused,)), view())["dn-warnings"]
    assert "dn-accept" not in fragments(idle(warnings=(fault,)), view())["dn-warnings"]
    assert "dn-accept" not in fragments(idle(warnings=(refused, fault)), view())["dn-warnings"]
    assert 'id="dn-accept"' in fragments(idle(warnings=(refused, fault, good)), view())["dn-warnings"]


def test_a_runs_owed_warnings_are_shown_whole_in_the_pre_flight():
    """Task 12's welfare review, I1: the page does not shorten what the source already cut."""
    said = "luminance-step x30, other: " + "q" * (NOTE_LIMIT - 27) + "…"
    assert len(said) == NOTE_LIMIT + 1
    shown = frame(
        service=True, phase="between_runs",
        preflight=Preflight("fixation_detection.py", (PreflightItem("warnings", "unknown", said),)),
    )

    assert f'<span class="val">{said}</span>' in fragments(shown, view())["preflight"]
    assert "overflow-wrap: anywhere" in _CSS.split("#warnings .val")[1].split("}")[0]


def test_the_head_and_the_session_panel_say_what_it_is_for_and_its_calibration():
    panes = fragments(frame(), view())

    assert '<span class="k">For</span><span class="v">training</span>' in panes["head-id"]
    assert "<dt>color calibration</dt><dd>srgb-standard</dd>" in panes["setup"]
    assert "<dt>for</dt><dd>training</dd>" in panes["setup"], "shown, never changed: fixed for the session"
    # A session given none, which since XC-352's E1 neither `wlx taskd` nor `wlx run` is (the
    # final review, row 17).
    assert "none loaded: no run starts without one" in fragments(
        frame(calibration=None), view())["setup"]


def test_an_unknown_accepted_earlier_this_session_shows_who_accepted_it_and_no_box():
    """The review's minor ruling (Call 30): a carried item needs no new acknowledgement."""
    pump = PreflightItem("pump calibration", "unknown", "no pump calibration")
    shown = frame(
        service=True, phase="between_runs",
        preflight=Preflight("fixation_detection.py", (pump, PreflightItem("out of cage", "pass", "marked"))),
        warnings=(WarningRow("pump calibration", "no pump calibration", SESSION_KINDS, Box("ann"), 1_700_000_000.0),),
    )

    panes = fragments(shown, view())

    assert 'data-ack="pump calibration"' not in panes["preflight"]
    assert "accepted earlier this session by" in panes["preflight"] and "ann" in panes["preflight"]
    assert "pre-flight ✓" in panes["pf-sum"]


def test_a_new_session_is_sent_with_what_it_is_for_and_the_warnings_accepted():
    body = _function("openSession")

    assert 'session_kind: el("dn-kind").value,' in body
    assert "accepted: acceptedWarnings()" in body
    assert ('if (!request.session_kind) { el("dn-msg").textContent = '
            '"not sent: choose what this session is for"; return; }') in body
    accepted = _function("acceptedWarnings")
    assert "if (!box || !box.checked) { return []; }" in accepted
    assert 'document.querySelectorAll("#dn-warnings [data-warn]")' in accepted
    assert 'if (kinds.indexOf(el("dn-kind").value) >= 0) {' in accepted
    assert 'pairs.push([row.getAttribute("data-warn"), row.getAttribute("data-detail")]);' in accepted
    settle = _function("settleOpen")
    assert 'el("dn-kind").value = "";' in settle
    assert 'if (el("dn-accept")) { el("dn-accept").checked = false; }' in settle


def test_the_page_has_a_warnings_tab_and_its_panel_shows_when_chosen():
    html = page(fragments(frame(), view()), stale_after_s=30.0, nonce="n0nce")

    assert '<label class="tab" for="t-warn">Warnings</label>' in html
    assert '<div class="tabpanel" id="tp-warn">' in html
    assert '<div id="warnings">' in html and '<div id="dn-warnings">' in html
    assert "#t-warn:checked ~ .panels #tp-warn" in _CSS


def _pf_frame(name_said, accepted_said):
    pump = PreflightItem("pump calibration", "unknown", name_said)
    return frame(
        service=True, phase="between_runs",
        preflight=Preflight("fixation_detection.py", (pump,)),
        warnings=(WarningRow("pump calibration", accepted_said, SESSION_KINDS, Box("ann"), 1_700_000_000.0),),
    )


def test_an_unknown_whose_sentence_changed_is_not_carried_and_keeps_its_box():
    """`taskd.Session.carried` matches name and sentence; a page that matched the name alone
    would offer no box for an item the gate refuses, and no run could start."""
    panes = fragments(_pf_frame("a new sentence", "the sentence accepted"), view())

    assert 'data-ack="pump calibration"' in panes["preflight"]
    assert "accepted earlier this session" not in panes["preflight"]
    assert "pre-flight · 1 to acknowledge" in panes["pf-sum"]


def test_a_head_free_row_no_one_accepted_yet_says_it_is_a_chaired_sessions():
    row = WarningRow(HEAD_FREE, "the head is free", SESSION_KINDS, None, None)

    assert " · a chaired session's" in fragments(idle(warnings=(row,)), view())["dn-warnings"]
    accepted = WarningRow(HEAD_FREE, "the head is free", SESSION_KINDS, Box("ann"), 1_700_000_000.0)
    assert "a chaired session" not in fragments(frame(warnings=(accepted,)), view())["warnings"]


def test_a_carried_row_with_no_actor_does_not_say_by_nobody():
    pump = PreflightItem("pump calibration", "unknown", "s")
    shown = frame(
        service=True, phase="between_runs", preflight=Preflight("t.py", (pump,)),
        warnings=(WarningRow("pump calibration", "s", SESSION_KINDS, None, 1_700_000_000.0),),
    )

    pane = fragments(shown, view())["preflight"]

    assert "accepted earlier this session at " in pane and "by  at" not in pane


# --- Plans (engine build C2b) ----------------------------------------------------------------

PLANNED = Preflight(
    "planned.py",
    (PreflightItem("task checks", "pass", "planned.py passes its load-time checks"),),
    plan="train",
    plans=("train", "test"),
)


def test_the_plan_picker_offers_the_tasks_plans_then_the_plain_run_the_shown_preflights_chosen():
    """The PI, 2026-10-19, "Preselect first, keep plain": the task's plans in order, then the plain
    run as one more labeled choice; the plan the shown pre-flight was taken for selected, so a wrong
    plan shows; no pre-flight, the plain run alone."""
    planned = fragments(_between(preflight=PLANNED), view())["plan-sel"]
    plain = fragments(_between(preflight=PREFLIGHT), view())["plan-sel"]

    assert planned == (
        '<option value="train" data-for="planned.py" selected>plan train</option>'
        '<option value="test" data-for="planned.py">plan test</option>'
        f'<option value="" data-for="planned.py">{PLAIN_RUN}</option>'
    )
    assert plain == (
        # The frame's run (run_index 0, plain) was of this task: repeated, so marked `data-last`.
        f'<option value="" data-for="fixation_detection.py" data-last selected>'
        f"{PLAIN_RUN}</option>")
    assert fragments(_between(), view())["plan-sel"] == f'<option value="">{PLAIN_RUN}</option>'
    # The science review, I8: "every trial paying" read as "every trial rewarded".
    assert PLAIN_RUN == "plain run: the trials below, each counted once, none shown again"
    assert fragments(idle(), view())["plan-sel"] == f'<option value="">{PLAIN_RUN}</option>'
    assert 'data-plan="train"' in fragments(_between(preflight=PLANNED), view())["controls"]
    assert "for planned.py · plan train · a fail blocks" in fragments(
        _between(preflight=PLANNED), view())["preflight"]


def test_a_tasks_first_plan_is_preselected_once_its_plans_arrive_and_a_plan_hides_the_trials():
    """The page learns a task's plans from its pre-flight, so choosing a task takes the plain run's
    first, then -- that task's plans arrived -- preselects its first plan and takes its pre-flight;
    a person's own choice of plan, the plain run included, stands."""
    preselect = _function("preselect")

    assert "if (task && task === awaiting && task === chosenTask() && !select.value) {" in preselect
    assert "awaiting = null;" in preselect and "if (chosen.value) {" in preselect
    assert 'var chosen = select.querySelector("option[data-last]") || first;' in preselect
    assert "select.value = chosen.value;" in preselect and "takePreflight(false);" in preselect
    # The pre-flight pill is swapped after this select in the same frame: nothing here reads it.
    assert "betweenRuns" not in preselect
    assert ("awaiting = chosenPlan() === null && (signinPage ? signedIn() : canWrite) ? task : "
            "null;") in _function("takePreflight")
    assert 'if (id === "plan-sel") { preselect(); }' in _function("swap")
    assert 'if (betweenRuns()) { el("plan-sel").value = ""; takePreflight(false); }' in _SCRIPT
    assert ("      if (betweenRuns()) { takePreflight(false); }\n"
            "      // The person chose: the pre-flight this takes arms nothing.\n"
            "      awaiting = null;") in _SCRIPT
    assert "plansOf" not in _SCRIPT
    assert ('el("run-trials").closest("label").hidden = Boolean(chosenPlan());'
            in _function("showTrials"))


def test_a_running_plan_shows_its_block_what_comes_next_its_time_left_and_the_moves():
    """Engine build C2b: the plan, the open block, the next, the time left before the block's and
    the run's limits, and *next block* and *back one* (the PI, 2026-10-19), *next block* greyed at
    the plan's last block; a plain run shows none of it."""
    running = fragments(frame(plan="train", block="easy", next_block="hard", block_left_s=125.0,
                              run_left_s=1800.0), view())["rt-need"]
    last = fragments(frame(plan="train", block="hard", next_block=None), view())["rt-need"]

    assert ("plan train · block easy · 2:05 of the block&#x27;s time left · 30:00 of the "
            "run&#x27;s time left · next: hard") in running
    assert '<button type="button" class="btn" data-cmd="next_block">next block</button>' in running
    assert '<button type="button" class="btn" data-cmd="back_block">back one</button>' in running
    assert ('data-cmd="next_block" disabled title="this block is the last its plan gives"'
            in last and "the plan&#x27;s last block" in last)
    assert 'data-cmd="next_block"' not in fragments(frame(), view())["rt-need"]


def test_what_a_blocks_time_left_owed_is_said_as_not_run():
    """The PI, 2026-10-19: trials a block still owed when its time ran out are "recorded as not
    run, 'time ran out'"."""
    shown = fragments(frame(shortfalls=(ShortfallRow("easy", "near", 3, "time", False, None, 40),)),
                      view())["rt-need"]

    assert "3 short in easy · not run: its block's time ran out" in shown


def test_what_the_runs_time_left_owed_is_said_as_the_runs():
    """The plan's science review, I3: the console's label says whose time ran out."""
    shown = fragments(frame(shortfalls=(
        ShortfallRow("easy", "near", 3, "run_time", False, None, 40),)), view())["rt-need"]

    assert "3 short in easy · not run: the run's time ran out" in shown


def test_a_block_past_its_targets_says_what_it_draws_until_and_a_passed_top_stage_says_so():
    """The plan's science review, I1: "drawing until the criterion is met" was said of a block of
    a number of trials too, and a top stage passed said nothing; each now says what is true -- its
    criterion, its number of trials, or both -- and a training progression's passed top stage
    says when it passed and that the animal keeps working."""
    def need(**over) -> str:
        return fragments(frame(past_targets=True, **over), view())["rt-need"]

    assert "every target used up: drawing until the criterion is met<" in need(rule="percentage")
    assert "every target used up: drawing until 200 trials are run<" in need(trials_to_run=200)
    assert ("drawing until the criterion is met and 200 trials are run" in
            need(rule="streak", trials_to_run=200))
    # Past its targets too, so "drawing until" is absent because the passed line replaced it.
    passed = fragments(frame(plan="train", block="hard", passed_at=41, past_targets=True,
                             rule="percentage"), view())["rt-need"]
    assert "top stage passed at trial 41; keeps working" in passed
    assert "drawing until" not in passed


def test_the_plan_row_counts_how_often_the_plan_fell_back():
    """The plan's science review, I2: a move-back count in the plan row."""
    def row(fell_back) -> str:
        return fragments(frame(plan="train", block="easy", fell_back=fell_back), view())["rt-need"]

    assert "fell back" not in row(0)
    assert "the plan&#x27;s last block · fell back once" in row(1)
    assert " · fell back 3 times" in row(3)


def test_a_run_that_is_not_running_shows_neither_the_plan_row_nor_a_passed_top_stage():
    """The row and the passed-stage line are for a live run: a run that is stopping, or a session
    between runs, carries its last plan and passed trial on a frame and shows neither."""
    for over in (dict(stop_kind="completed", stopped_because="every block is finished"),
                 dict(phase="between_runs", service=True, stop_kind="completed",
                      stopped_because="every block is finished")):
        shown = fragments(frame(plan="train", block="hard", next_block=None, passed_at=41,
                                **over), view())["rt-need"]
        assert "plan train" not in shown and 'data-cmd="next_block"' not in shown
        assert "top stage passed" not in shown


def test_a_plans_and_a_blocks_names_are_escaped_where_the_page_shows_them():
    """A plan's name reaches the picker and the plan row, a block's the row; each is escaped."""
    name = "a<b>&c"
    picker = fragments(_between(preflight=Preflight(
        "planned.py", PLANNED.items, plan=name, plans=(name,))), view())["plan-sel"]
    row = fragments(frame(plan=name, block="x<y&z", next_block="n<m"), view())["rt-need"]
    running = fragments(frame(plan=name, block="b"), view())["plan-sel"]

    assert "a&lt;b&gt;&amp;c" in picker and "a<b>" not in picker
    assert "a&lt;b&gt;&amp;c" in row and "x&lt;y&amp;z" in row and "n&lt;m" in row
    assert "<b>" not in row and "x<y" not in row
    assert running == '<option value="a&lt;b&gt;&amp;c" selected>plan a&lt;b&gt;&amp;c</option>'


def test_the_picker_shows_the_plan_that_runs_not_the_plain_runs_label():
    """The task's first review, I1a: while a plan runs, the bar must not read the plain run's label
    over it; a plain run, and the time between runs, still read the plain run."""
    running = fragments(frame(plan="train", block="easy"), view())["plan-sel"]

    assert running == '<option value="train" selected>plan train</option>'
    assert fragments(frame(), view())["plan-sel"] == f'<option value="">{PLAIN_RUN}</option>'
    assert fragments(_between(), view())["plan-sel"] == f'<option value="">{PLAIN_RUN}</option>'
    # Between runs, and while a run stops, the frame still carries the last run's plan (taskd's
    # `Session.plan`), which is not the next run's: the plain run is shown.
    for over in (dict(phase="between_runs", service=True, stop_kind="completed"),
                 dict(stop_kind="completed")):
        assert fragments(frame(plan="train", block="easy", **over), view())["plan-sel"] == (
            f'<option value="">{PLAIN_RUN}</option>')


def test_the_option_for_the_plan_last_run_is_marked_when_it_is_the_same_tasks_and_still_offered():
    """The PI, 2026-10-22, "The plan last run": the page preselects the plan the frame's last run
    played, when that run was of the pre-flight's task and the plan is still among its plans; the
    frame's task is the run's file path, the pre-flight's the name it is offered by."""
    def picker(**over) -> str:
        return fragments(_between(preflight=Preflight(
            "planned.py", PLANNED.items, plan=None, plans=("train", "test")), **over),
            view())["plan-sel"]

    last = picker(plan="test", task="tasks/planned.py")
    assert '<option value="test" data-for="planned.py" data-last>plan test</option>' in last
    assert last.count("data-last") == 1
    assert "data-last" not in picker(plan="gone", task="tasks/planned.py")
    assert "data-last" not in picker(plan="test", task="tasks/other.py")
    assert "data-last" not in picker(plan="test", task=None)
    # A plain last run is repeated: the plain run's option is the marked one. No run yet -- the
    # session's first -- marks none.
    plain = picker(plan=None, task="tasks/planned.py", run_index=1)
    assert (f'<option value="" data-for="planned.py" data-last selected>{PLAIN_RUN}</option>'
            in plain)
    assert plain.count("data-last") == 1
    assert "data-last" not in picker(plan=None, task="tasks/planned.py", run_index=None)
    assert "data-last" not in picker(plan="test", task="tasks/planned.py", run_index=None)


def test_the_moves_between_blocks_are_held_against_a_double_click_and_a_plan_start_skips_trials():
    """The task's first review, I2 and M4, in the script's own text; the browser tests drive it."""
    click = _SCRIPT
    start = _function("startRun")

    assert 'if (cmd === "next_block" || cmd === "back_block") {' in click
    assert "if (!clearAllowed(e.detail, cmd)) { return; }" in click
    assert "if (plan) { trials = Number.isInteger(trials) && trials >= 1 ? trials : 1; }" in start
    assert "else if (!Number.isInteger(trials) || trials < 1) {" in start


# --- engine build C3: where each value comes from, hand back, a range, revert (XC-418) ----------
#
# Telemetry schema 19 carries each card's source, conditions, draw and live numbers, each staged
# change's kind and what it will override, and the moments a revert can go back to; the page shows
# them (the C3 spec §6 and §8; the PI, 2026-10-30, Q7a and Q7b; TSK-19, TSK-43).

_SINCE = 1_700_000_000.0


def _cards(params: str) -> dict[str, str]:
    """Each box of the parameters pane, by its setting's name (`data-card`; the console interface
    rework's Task 5)."""
    cards = {}
    for card in params.split('<div class="box')[1:]:
        cards[html.unescape(re.search(r'data-card="(.*?)"', card).group(1))] = card
    return cards


def test_a_card_shows_where_its_value_comes_from_and_its_conditions():
    """The C3 spec §6: "each setting's card says where its value comes from (task, run,
    conditions, a draw and its range, or a person) and which conditions set or draw it" (engine
    spec §14.7; telemetry schema 19). The task's start, the run and a person beneath the value
    they give; conditions and a draw in the value's place, since each trial takes its own; the
    run's plan's conditions, one or several; the open block's draw in the rig's words, on a card a
    person holds too, since a hand-back gives it back to it. Nothing where the rig sends none."""
    params = fragments(frame(params=(
        ParamRow("fix_hold", "s", 0.1, 1.0, 0.3, False, None, "task"),
        ParamRow("fix_window", "deg", None, 5.0, 2.0, False, None, "run", ("wide",)),
        ParamRow("target_x", "deg", None, None, 4.0, False, None, "conditions", ("near", "far")),
        ParamRow("wait", "s", 0.5, 2.0, None, False, None, "draw", (),
                 "uniform from 0.75 s to 1.25 s", {"low": 0.75, "high": 1.25}),
        ParamRow("gain", "", None, None, 2.0, False, None, "person", ("near",),
                 "uniform from 1.0 to 3.0", None),
        ParamRow("reward_correct", "mL", 0.0, 0.4, 0.15, True),
    )), view())["params"]
    cards = _cards(params)

    assert '<span class="src">from the task\'s start</span>' in cards["fix_hold"]
    assert '<span class="src">given by this run</span>' in cards["fix_window"]
    assert '<span class="src">set or drawn by condition wide</span>' in cards["fix_window"]
    assert '<span class="pv">set or drawn by its conditions</span>' in cards["target_x"]
    assert '<span class="src">set or drawn by conditions near, far</span>' in cards["target_x"]
    assert "4.00" not in cards["target_x"]
    assert '<span class="pv">drawn each trial</span>' in cards["wait"]
    assert '<span class="src">its draw: uniform from 0.75 s to 1.25 s</span>' in cards["wait"]
    assert "set or drawn by" not in cards["wait"]
    assert '<span class="src">held by a person</span>' in cards["gain"]
    assert '<span class="pv">2.00 ' in cards["gain"]
    assert '<span class="src">set or drawn by condition near</span>' in cards["gain"]
    assert '<span class="src">its draw: uniform from 1.0 to 3.0</span>' in cards["gain"]
    assert 'class="src"' not in cards["reward_correct"]


def test_a_setting_its_conditions_set_shows_no_spinner():
    """XC-418: an unset setting whose choices are `Polar`s, a position a plan's conditions set,
    showed a number spinner on its card, the run's values holding nothing for it. A card whose
    conditions, or whose draw, give each trial a value of its own says so in the value's place,
    never a spinner: no arrows stepping from a number no trial uses, and no value of the run's
    shown as though trials took it. A person may still set one value over them (TSK-19, the PI,
    2026-10-07: it wins and the trial counts; the C3 spec §6: it replaces a draw), in an empty
    field, a word where the run's value is one; a card holding a whole position offers none, as
    a position's card never does (STE-30)."""
    choices = (Polar(8.0, 0.0), Polar(8.0, 45.0))
    rows = (
        ParamRow.of("target_pos", "deg", None, None, None, False, choices, "conditions",
                    ("near", "far")),
        ParamRow("target_x", "deg", -16.0, 16.0, 10.0, False, None, "conditions", ("near",)),
        ParamRow("shape", "", None, None, "penguin", False, None, "conditions", ("near",)),
        ParamRow("wait", "s", 0.5, 2.0, 1.0, False, None, "draw", (),
                 "uniform from 0.75 s to 1.25 s", None),
        ParamRow.of("start_pos", "deg", None, None, Polar(8.0, 0.0), False, choices,
                    "conditions", ("near",)),
    )
    params = fragments(frame(params=rows), view())["params"]
    lan = fragments(frame(params=rows), view(can_write=False))["params"]
    cards = _cards(params)

    for name in ("target_pos", "target_x", "shape", "wait", "start_pos"):
        assert 'class="spin"' not in cards[name] and "data-dir" not in cards[name], name
    assert "unset" not in cards["target_pos"] and "10.00" not in cards["target_x"]
    assert "penguin" not in cards["shape"] and "1.00" not in cards["wait"]
    assert ('<input class="field mono over" data-param="target_x" inputmode="decimal" value="" '
            'placeholder="a value over its conditions" aria-label="target_x: a value over its '
            'conditions">') in cards["target_x"]
    assert 'data-param="shape" data-kind="word" value=""' in cards["shape"]
    assert 'data-param="wait" inputmode="decimal" value="" placeholder="a value over its draw"' in (
        cards["wait"])
    assert "<input" not in cards["start_pos"] and "8° at 0°" not in cards["start_pos"]
    assert lan.count(f'its conditions" disabled title="{CONTROLS_AT_THE_BOX}">') == 3


def test_a_setting_without_live_numbers_shows_no_range_editor():
    """Review M-4 and Call 22: a card whose draw has numbers a person may change live
    (`ParamRow.numbers`: a uniform's ends, a normal's mean, spread and cut, a wait's three) has a
    field for each, holding it as the wire carried it, sent by its box's Apply (the console
    interface rework's Task 6: *change the range* is gone); no other card has
    any -- not one declared not live, a direction (XC-445), a weighted set or a list (XC-443),
    each sent with `numbers` `None`, nor one with no draw. Greyed away from the box."""
    rows = (
        ParamRow("wait", "s", 0.5, 2.0, None, False, None, "draw", (),
                 "uniform from 0.75 s to 1.25 s", {"low": 0.75, "high": 1.25}),
        ParamRow("gap", "s", None, None, None, False, None, "draw", (),
                 "normal of mean 1 s and sd 0.1 s, cut to the setting's range",
                 {"mean": 1, "sd": 0.1}),
        ParamRow("angle", "deg", None, None, None, False, None, "draw", (),
                 "uniform from 315 deg to 45 deg", None),
        ParamRow("fix_hold", "s", 0.1, 1.0, 0.3, False, None, "task"),
    )
    params = fragments(frame(params=rows), view())["params"]
    lan = fragments(frame(params=rows), view(can_write=False))["params"]
    cards = _cards(params)

    assert 'data-cmd="range"' not in params and "change the range" not in params
    assert ('<div class="rng"><label class="rn">low<input class="field mono" data-number="low" '
            'inputmode="decimal" value="0.75" aria-label="wait: low"><span class="unit">s</span>'
            '</label>') in cards["wait"]
    assert 'data-number="high" inputmode="decimal" value="1.25"' in cards["wait"]
    assert ('<label class="rn">high<input class="field mono" data-number="high" inputmode="decimal" '
            'value="1.25" aria-label="wait: high"><span class="unit">s</span></label></div>'
            ) in cards["wait"]
    assert 'data-number="mean" inputmode="decimal" value="1"' in cards["gap"]
    assert 'data-number="sd" inputmode="decimal" value="0.1"' in cards["gap"]
    for name in ("angle", "fix_hold"):
        assert "data-number" not in cards[name], name
    assert lan.count(f'aria-label="wait: low" disabled title="{CONTROLS_AT_THE_BOX}">') == 1


def test_a_card_a_person_holds_has_hand_back_and_no_other_does():
    """The PI, 2026-10-30, Q7a: "Yes, a 'hand back' button" on each setting a person holds: from
    the next trial its conditions' values, or its draw, apply again, trials no longer marked,
    recorded as a change. Only a card a person holds has it; greyed away from the box."""
    rows = (
        ParamRow("fix_hold", "s", 0.1, 1.0, 0.4, False, None, "person", ("near",)),
        ParamRow("fix_window", "deg", None, 5.0, 2.0, False, None, "run"),
        ParamRow("target_x", "deg", None, None, None, False, None, "conditions", ("near",)),
        ParamRow("reward_correct", "mL", 0.0, 0.4, 0.15, True),
    )
    params = fragments(frame(params=rows), view())["params"]
    lan = fragments(frame(params=rows), view(can_write=False))["params"]

    assert params.count('data-cmd="hand_back"') == 1
    assert ('<button type="button" class="btn small" data-cmd="hand_back" data-name="fix_hold">'
            "hand back</button>") in _cards(params)["fix_hold"]
    assert (f'data-cmd="hand_back" data-name="fix_hold" disabled title="{CONTROLS_AT_THE_BOX}">'
            in lan)


def test_a_staged_row_names_what_it_will_override():
    """The C3 spec §6: "A staged change names the conditions it will override **before** it
    applies; today only the applied line on the feed does" (TSK-19; `Staged.overrides`). One
    condition and several, each worded as the applied line words them; a ceiling's change names
    none. The card says it is staged, as before."""
    jake = Box("jake")
    who = _who(jake)
    parts = fragments(frame(
        params=(ParamRow("target_x", "deg", None, None, None, False, None, "conditions",
                         ("near", "far")),
                ParamRow("fix_hold", "s", 0.1, 1.0, 0.3, False, None, "task", ("slow",)),
                ParamRow("reward_correct", "mL", 0.0, 0.4, 0.15, True)),
        staged=(Staged("target_x", 4.0, 5.0, jake, False, "set", ("near", "far")),
                Staged("fix_hold", 0.3, 0.4, jake, False, "set", ("slow",)),
                Staged("reward_correct", 0.15, 0.2, jake, True)),
    ), view())
    feed = parts["rt-changes"]

    assert (f"target_x 4.00 → 5.00 by {who} (task parameter, applies at the next trial); it will "
            "override what conditions near, far set or draw</span>") in feed
    assert (f"fix_hold 0.30 → 0.40 by {who} (task parameter, applies at the next trial); it will "
            "override what condition slow sets or draws</span>") in feed
    assert (f"reward_correct 0.15 → 0.20 by {who} (welfare-bounded ceiling, applies at the next "
            "trial)</span>") in feed
    assert f'<span class="stg">staged → 5.00 by {who}</span>' in _cards(parts["params"])["target_x"]


def test_a_staged_hand_back_a_range_and_a_revert_are_said_in_words():
    """Review M-15, Call 30 and the controller's ruling for Task 18: a staged hand-back says what
    takes the setting back in the open block -- the run's own value (its `now`), else its draw,
    else its conditions -- never "unset", which it is not; a staged range says the draw before
    and after in the rig's words; a revert's changes say they are a revert, one handing a setting
    back saying so. Each led by its kind, in the feed and on the card."""
    jake = Box("jake")
    who = _who(jake)
    params = (
        ParamRow("fix_hold", "s", 0.1, 1.0, 0.4, False, None, "person"),
        ParamRow("wait", "s", 0.5, 2.0, 1.0, False, None, "person", (),
                 "uniform from 0.75 s to 1.25 s", {"low": 0.75, "high": 1.25}),
        ParamRow("target_x", "deg", None, None, 6.0, False, None, "person", ("near",)),
        ParamRow("gap", "s", None, None, None, False, None, "draw", (),
                 "uniform from 0.2 s to 0.4 s", {"low": 0.2, "high": 0.4}),
    )
    parts = fragments(frame(params=params, staged=(
        Staged("fix_hold", 0.4, 0.3, jake, False, "hand_back", (), True, "run"),
        Staged("wait", 1.0, None, jake, False, "hand_back", (), True, "draw"),
        Staged("target_x", 6.0, None, jake, False, "hand_back", (), True, "conditions"),
        Staged("gap", "uniform from 0.2 s to 0.4 s", "uniform from 0.2 s to 0.5 s", jake, False,
               "range"),
    )), view())
    feed, cards = parts["rt-changes"], _cards(parts["params"])

    assert f"hand back: fix_hold 0.40 → the run's 0.30 by {who} (task parameter, " in feed
    assert f"hand back: wait 1.00 → its draw by {who}" in feed
    assert f"hand back: target_x 6.00 → its conditions by {who}" in feed
    assert (f"range: gap uniform from 0.2 s to 0.4 s → uniform from 0.2 s to 0.5 s by {who} "
            "(task parameter, applies at the next trial)</span>") in feed
    assert "unset" not in feed
    assert f"staged hand back → the run's 0.30 by {who}" in cards["fix_hold"]
    assert f"staged hand back → its draw by {who}" in cards["wait"]
    assert f"staged hand back → its conditions by {who}" in cards["target_x"]
    assert f"staged range → uniform from 0.2 s to 0.5 s by {who}" in cards["gap"]


def test_a_staged_revert_is_said_in_words_and_a_hand_back_is_said_where_it_goes():
    """The revert case of the words test above, a test of its own (fix round 1 of the C3 plan's
    Task 18): a revert's changes say they are a revert, one handing a setting back saying so and
    where it goes; and a hand-back to a run that gives the setting no value says that, as the
    rig's applied line does (`Staged.to`, review minor 1), not "its conditions"."""
    jake = Box("jake")
    who = _who(jake)
    params = (
        ParamRow("fix_hold", "s", 0.1, 1.0, 0.4, False, None, "person"),
        ParamRow("target_x", "deg", None, None, 6.0, False, None, "person", ("near",)),
        ParamRow("gap", "s", None, None, None, False, None, "draw", (),
                 "uniform from 0.2 s to 0.4 s", {"low": 0.2, "high": 0.4}),
    )
    reverted = fragments(frame(params=params, staged=(
        Staged("target_x", 6.0, 5.0, jake, False, "revert", ("near",)),
        Staged("fix_hold", 0.4, None, jake, False, "revert", (), True, "conditions"),
        Staged("gap", "uniform from 0.2 s to 0.4 s", "uniform from 0.2 s to 0.3 s", jake, False,
               "revert"),
    )), view())
    feed, cards = reverted["rt-changes"], _cards(reverted["params"])

    assert (f"revert: target_x 6.00 → 5.00 by {who} (task parameter, applies at the next trial); "
            "it will override what condition near sets or draws</span>") in feed
    assert f"revert: fix_hold 0.40 → handed back to its conditions by {who}" in feed
    assert (f"revert: gap uniform from 0.2 s to 0.4 s → uniform from 0.2 s to 0.3 s by {who}"
            in feed)
    assert "unset" not in feed
    assert f"staged revert → handed back to its conditions by {who}" in cards["fix_hold"]
    assert f"staged revert → 5.00 by {who}" in cards["target_x"]

    nothing = fragments(frame(params=params, staged=(
        Staged("fix_hold", 0.4, None, jake, False, "hand_back", (), True, "run"),
        Staged("target_x", 6.0, None, jake, False, "revert", (), True, "run"),
    )), view())
    feed, cards = nothing["rt-changes"], _cards(nothing["params"])

    assert f"hand back: fix_hold 0.40 → the run, which gives it no value by {who}" in feed
    assert (f"revert: target_x 6.00 → handed back to the run, which gives it no value by {who}"
            in feed)
    assert "its conditions" not in feed
    assert f"staged hand back → the run, which gives it no value by {who}" in cards["fix_hold"]

    held = (ParamRow("target_y", "deg", None, None, 2.0, False, None, "person"),
            ParamRow("target_z", "deg", None, None, 2.0, False, None, "person"))
    same = fragments(frame(params=held, staged=(
        Staged("target_y", 2.0, 0.0, jake, False, "revert", (), True, "run"),
        Staged("target_z", 2.0, 0.0, jake, False, "revert", ()),
    )), view())
    feed, cards = same["rt-changes"], _cards(same["params"])

    assert f"revert: target_y 2.00 → handed back to the run's 0.00 by {who}" in feed
    assert f"revert: target_z 2.00 → 0.00 by {who}" in feed
    assert f"staged revert → handed back to the run's 0.00 by {who}" in cards["target_y"]
    assert f"staged revert → 0.00 by {who}" in cards["target_z"]


def test_the_moments_pane_offers_a_revert_to_each_newest_first_and_the_runs_start_last():
    """TSK-43 (the PI, 2026-10-07, "Yes, with revert": "any earlier state restored in one action,
    itself recorded"); the C3 spec §8; review M-15: each moment the rig sends, newest first and
    the run's start last, with when it was kept, what was done then, and *revert to this*,
    sending its change id. Between runs nothing is offered, and before any frame the pane says
    so; greyed away from the box."""
    moments = (MomentRow(7, _SINCE + 90, "target_x 4.00 → 5.00", ("target_x → 5.00",)),
               MomentRow(3, _SINCE + 30, "fix_hold handed back to its conditions",
                         ("fix_hold handed back",)),
               MomentRow(0, _SINCE, "the run's start", ("target_x → 4.00",)))
    pane = fragments(frame(moments=moments), view())["moments"]
    lan = fragments(frame(moments=moments), view(can_write=False))["moments"]
    between = fragments(frame(moments=()), view())["moments"]

    assert re.findall(r'data-change="(\d+)"', pane) == ["7", "3", "0"]
    assert (f'<div class="kv"><span>{_clock_time(_SINCE + 90)} · target_x 4.00 → 5.00</span>'
            '<button type="button" class="btn small" data-cmd="revert" data-change="7">'
            "revert to this</button></div>") in pane
    assert pane.index("the run&#x27;s start") > pane.index("fix_hold handed back")
    assert lan.count(f'data-change="0" disabled title="{CONTROLS_AT_THE_BOX}">') == 1
    assert between == '<span class="nm">no run in progress: no moment to go back to</span>'
    assert fragments(None, view())["moments"] == '<span class="nm">no session</span>'


def test_where_a_value_comes_from_its_draw_its_numbers_and_the_moments_are_escaped():
    """Every telemetry string reaches the page through `_e` (the module's rule), schema 19's too:
    a condition's name, a draw's words, a live number's name, a staged change's overrides and a
    range's words, and a moment's words."""
    jake = Box("jake")
    parts = fragments(frame(
        params=(ParamRow("fix_hold", "s", None, None, 0.4, False, None, "person", (EVIL,), EVIL,
                         {EVIL: 1.0}),
                ParamRow("gap", "s", None, None, None, False, None, "conditions", (EVIL, "near"))),
        staged=(Staged("fix_hold", 0.3, 0.4, jake, False, "set", (EVIL,)),
                Staged("fix_hold", 0.4, 0.5, jake, False, "set", (EVIL, "near")),
                Staged("gap", EVIL, EVIL, jake, False, "range", (EVIL,)),
                Staged("gap", 0.2, EVIL, jake, False, "hand_back", (), True, "run")),
        moments=(MomentRow(1, _SINCE, EVIL, (EVIL,)),),
        eased=(EVIL,),
    ), view())
    text = parts["params"] + parts["rt-changes"] + parts["moments"] + parts["banners"]

    assert "<script" not in text
    assert EVIL not in text
    # Five on the held card (its condition, its draw, a number's name thrice), the other card's
    # conditions and its staged hand-back -- in its *more*, and in its head after the arrow and
    # that head's `title` (the console interface rework's Task 5), and in who is changing it under
    # a draft, `data-under` (its Task 6), and on its summary line after the arrow and in the
    # line's `title` (the summary and editor design's goal 3) -- seven in the feed (a range's
    # block among them), the moment's words and what a revert to it changes, and the setting the
    # eased line names.
    assert text.count(html.escape(EVIL, quote=True)) == 21


def test_the_page_says_while_a_persons_change_keeps_trials_out_of_moving_up():
    """The C3 plan's engineering review, I-2, and its science review, I-4: a trainer who widened a
    window sees a perfect streak and a block that will not end. While the rig says a person's
    change keeps trials out of moving up (`Telemetry.eased`), a standing line says which settings
    do and how to count trials again, beside the changes feed's warning said once a block; none
    otherwise."""
    banners = fragments(frame(eased=("fix_window", "target_luminance")), view())["banners"]

    assert ('<span class="tag">Not counting</span><span>trials are not counting toward moving up: '
            'a person changed fix_window, target_luminance; hand each back, or send its range as '
            'the task writes it, or revert, to count them again</span>') in banners
    assert "Not counting" not in fragments(frame(), view())["banners"]


def test_a_card_whose_range_was_changed_live_says_so_and_a_staged_range_names_its_blocks():
    """The C3 plan's science review, I-4 and M-2: a card whose draw's range a person changed live
    says so in the value's place (`source` `range`), with the field over its draw a drawn card
    has; a staged range names the blocks of the run's plan it reaches for the rest of the run, one
    or several (`Staged.overrides`), never as conditions it overrides."""
    jake = Box("jake")
    parts = fragments(frame(
        params=(ParamRow("gap", "s", 0.1, 1.0, 0.3, False, None, "range", (),
                         "uniform from 0.2 s to 0.5 s", {"low": 0.2, "high": 0.5}),
                ParamRow("wait", "s", 0.5, 2.0, 1.0, False, None, "draw", (),
                         "uniform from 0.75 s to 1.25 s", {"low": 0.75, "high": 1.25})),
        staged=(Staged("gap", "uniform from 0.2 s to 0.5 s", "uniform from 0.2 s to 0.6 s", jake,
                       False, "range", ("train", "test")),
                Staged("wait", "uniform from 0.75 s to 1.25 s", "uniform from 0.75 s to 1.5 s",
                       jake, False, "range", ("own",))),
    ), view())
    feed, cards = parts["rt-changes"], _cards(parts["params"])

    assert ('<span class="pv">drawn each trial, from a range a person changed live</span>'
            in cards["gap"])
    assert 'placeholder="a value over its draw"' in cards["gap"]
    assert '<span class="pv">drawn each trial</span>' in cards["wait"]
    assert ("uniform from 0.2 s to 0.6 s by " + _who(jake) + " (task parameter, applies at the "
            "next trial); it reaches blocks train, test for the rest of the run</span>") in feed
    assert ("uniform from 0.75 s to 1.5 s by " + _who(jake) + " (task parameter, applies at the "
            "next trial); it reaches block own for the rest of the run</span>") in feed
    assert "override" not in feed


def test_a_card_names_the_conditions_the_rig_sends_and_counts_the_rest():
    """The C3 plan's engineering review, M-5: the rig names at most twenty conditions on a card
    and counts the rest (`ParamRow.more`), so a factorial of thousands cannot grow every frame;
    the card says how many more."""
    cards = _cards(fragments(frame(params=(
        ParamRow("target_x", "deg", None, None, 4.0, False, None, "conditions", ("c0", "c1"),
                 None, None, 23),
        ParamRow("fix_hold", "s", 0.1, 1.0, 0.3, False, None, "task", ("slow",), None, None, 1),
    )), view())["params"])

    assert ('<span class="src">set or drawn by conditions c0, c1 and 23 more</span>'
            in cards["target_x"])
    assert ('<span class="src">set or drawn by conditions slow and 1 more</span>'
            in cards["fix_hold"])


def test_each_moment_says_what_a_revert_to_it_would_change():
    """The C3 plan's science review, M-1: one tap on *revert to this* restores many settings, so
    each moment says beneath it what a revert to it would change, in the changes feed's words, as
    the rig sends them (`MomentRow.changes`), or that it would change nothing now, which the rig
    would refuse, so its *revert to this* is greyed (fix round 1 of the C3 plan's Task 18, review
    minor 7)."""
    pane = fragments(frame(moments=(
        MomentRow(4, _SINCE + 60, "target_y 0.00 → 2.00"),
        MomentRow(1, _SINCE + 10, "target_x 10.00 → 12.00",
                  ("target_y handed back", "the task's draw of 'fix_hold' → as declared",
                   "target_x → 12.00")),
    )), view())["moments"]

    assert ('data-change="4" disabled title="a revert to this would change nothing now">'
            'revert to this</button></div><div class="rv">would change nothing now</div>'
            '<div class="kv">') in pane
    assert 'data-change="1">revert to this</button>' in pane
    assert pane.endswith(
        '<div class="rv">would change: target_y handed back; the task&#x27;s draw of '
        '&#x27;fix_hold&#x27; → as declared; target_x → 12.00</div>')


# --- the trainer's panel (the pop-out search build's Task 7) ------------------------------------
#
# The design's §3.5 (approved by the PI on 2026-11-07, who accepted the sketch of the trainer's
# screen with short stage names): during the session, "the stage by name, the staircase's level
# and its lock, the last 50 trials' percent correct and errors by kind, the pairings on, and, when
# the bar is met, a prompt naming why ... with Move up and Hold"; back down the same way, Move back
# and Hold; and at a widening, "Trainer picks at the prompt". Each from the frame, never computed
# here but the percentages (plan ruling 5's display arithmetic).

_LADDER = StaircaseRow("distractor_luminance", (0.25, 0.5, 0.75, 1.0), 2, False, 3, 1)
_BARS = Bars(39, 50, 50, {"no_response": 4, "wrong_target": 7},
             {"no_fixation": 2, "fixation_break": 4}, 30, 34, 50, 0.8, 0.5)
#: Pairings 1 and 3 on, of four.
_POOLED = Pooled("pairings", ("blue>red", "red>blue", "purple>red", "red>purple"), 5)


def _training(**over) -> object:
    """A confirmed progression's run in Fade-in, its staircase on the distractors' luminance."""
    fields = dict(plan="train", block="Fade-in", next_block="Crowd", staircase=_LADDER,
                  bars=_BARS, pool=_POOLED, params=(
                      ParamRow("distractor_luminance", "of full", 0.0, 1.0, 0.5, False,
                               source="staircase"),
                      ParamRow("pairings", "pairings", 1, 15, 5, False, source="run")))
    fields.update(over)
    return frame(**fields)


def _up(change: int = 7) -> Suggestion:
    return Suggestion(change, "up", "Fade-in", "Crowd", 41, 50, True)


def _widening(change: int = 8) -> Suggestion:
    return Suggestion(change, "widen", "Fade-in", None, 41, 50, True)


def _back(change: int = 9) -> Suggestion:
    return Suggestion(change, "back", "Fade-in", "Alone", 22, 50, False)


def _train(frame_, can_write: bool = True) -> str:
    return fragments(frame_, view(can_write=can_write))["rt-train"]


def test_the_pane_names_the_stage_and_its_level():
    """The stage by name, with its plan and the stage it goes on to; the staircase's setting at the
    level the next trial takes, which level of how many, its rule, and its lock: *lock at* holds the
    setting where it is, as a person's value does (TSK-32). Held, the person's value, where the
    staircase waits, and *hand back* (engine build C3's), which resumes it nearest the value
    held."""
    pane = _train(_training())
    held = _train(_training(staircase=replace(_LADDER, held=True), params=(
        ParamRow("distractor_luminance", "of full", 0.0, 1.0, 0.5, False, source="person"),)))

    assert pane.startswith('<div class="top"><h2>Training</h2></div>')
    assert ('<div class="kv"><span>stage <b>Fade-in</b></span>'
            '<span class="nm">plan train · next: Crowd</span></div>') in pane
    assert ('<div class="kv"><span>distractor_luminance <b>0.75</b> of full</span>'
            '<span class="nm">level 3 of 4, set by its staircase (3 right harder, 1 wrong easier)'
            '</span><button type="button" class="btn small" data-cmd="lock" '
            'data-name="distractor_luminance" data-value="0.75">lock at 0.75</button></div>'
            ) in pane
    assert 'data-cmd="hand_back"' not in pane
    assert ('<div class="kv"><span>distractor_luminance <b>0.5</b> of full, held by a person'
            '</span><span class="nm">its staircase waits at 0.75, level 3 of 4; a hand-back '
            'resumes it at the level nearest the value held</span><button type="button" '
            'class="btn small" data-cmd="hand_back" data-name="distractor_luminance">hand back'
            '</button></div>') in held
    assert 'data-cmd="lock"' not in held
    # The last stage says so; a plain run names no plan.
    assert ('<span class="nm">plan train · the plan&#x27;s last stage</span>'
            in _train(_training(next_block=None)))
    assert "<span>stage <b>Fade-in</b></span></div>" in _train(_training(plan=None))


def test_the_pane_shows_the_last_answers_their_errors_by_kind_and_those_left_out():
    """"The last 50 trials' percent correct and errors by kind", the trials left out of them
    "shown beside it" (§3.4), each by its outcome in `Outcome`'s order; and the bar to move up as it
    reads, at the stage's hardest step, with its proportion. **The last answers are the stage's**
    (the build's final fixes, 3: no hold or change of the pool clears them): a stage that has given
    fewer than the window shows them all, saying they are the stage's; an empty one says so, never
    0%."""
    pane = _train(_training())
    filling = _train(_training(bars=replace(_BARS, correct=9, of=12, wrong={}, left_out={})))
    empty = _train(_training(bars=replace(_BARS, correct=0, of=0, wrong={}, left_out={},
                                          up_correct=0, up_of=0, up_at=None)))

    assert ('<div class="kv"><span>last 50 answers <b>39 right (78%)</b></span>'
            '<span class="nm">wrong: wrong_target 7 · no_response 4</span></div>'
            '<div class="kv"><span class="nm">left out of them: no_fixation 2 · fixation_break 4'
            '</span></div>'
            '<div class="kv"><span class="nm">toward moving up: 30 of the last 34 answers at its '
            'hardest step right; the rig suggests it at 80% of 50</span></div>') in pane
    assert ('<span>this stage&#x27;s 12 answers <b>9 right (75%)</b></span>'
            '<span class="nm">wrong: none</span></div><div class="kv"><span class="nm">left out '
            'of them: none</span></div>') in filling
    assert ('<div class="kv"><span>no answers yet in this stage</span><span class="nm">it shows '
            'its last 50</span></div>') in empty
    assert "this stage has no bar to move up" in empty and "0%" not in empty


def test_a_suggestion_shows_why_and_its_two_buttons():
    """When the bar is met, a prompt naming why -- the setting at its hardest step and the answers
    right there -- with *Move up* and *Hold* (the PI's sketch); back down the same way, *Move back*
    and *Hold*, naming the bar it fell under. Each button names the suggestion it answers."""
    up = _train(_training(suggestion=_up(), staircase=replace(_LADDER, level=3)))
    back = _train(_training(suggestion=_back(), staircase=None))

    assert ('<div class="prompt" data-prompt="7"><div><b>Ready for Crowd.</b> '
            'distractor_luminance is at its hardest step, 1, and 41 of the last 50 answers there '
            'were right (82%).</div><div class="acts"><button type="button" class="btn primary" '
            'data-cmd="confirm" data-move="next_block" data-suggestion="7">Move up to Crowd'
            '</button><button type="button" class="btn" data-cmd="decline" data-suggestion="7">'
            'Hold at Fade-in</button></div></div>') in up
    assert ('<div class="prompt back" data-prompt="9"><div><b>Back to Alone?</b> 22 of the last '
            '50 answers were right (44%), under 50%.</div><div class="acts"><button '
            'type="button" class="btn primary" data-cmd="confirm" data-move="back_block" '
            'data-suggestion="9">Move back to Alone</button><button type="button" class="btn" '
            'data-cmd="decline" data-suggestion="9">Hold at Fade-in</button></div></div>') in back
    # A stage with no staircase is always at its hardest: the answers alone.
    assert ("<b>Ready for Crowd.</b> 41 of the last 50 answers were right (82%).</div>"
            in _train(_training(suggestion=_up(), staircase=None)))
    # **The task's own words for its hardest step** (the build's review, M7; the PI's sketch: "the
    # distractors are at full brightness and 41 of the last 50 were correct").
    worded = replace(_LADDER, hardest="the distractors are at full brightness", level=3)
    # The words ride the frame's staircase (ADR-0003's round trip).
    from wl_xcon.link import decode, encode
    assert decode(encode(_training(staircase=worded))).staircase == worded
    full = ("<b>Ready for Crowd.</b> The distractors are at full brightness and 41 of the last "
            "50 were correct (82%).</div>")
    assert full in _train(_training(suggestion=_up(), staircase=worded))
    # **Said only while the trial's value is at the hardest step** (the re-review, I-1): the
    # staircase a level below it, or a person's value held merely near it, gets the plain bar; a
    # person's value held at it gets the words.
    def held(value: float) -> object:
        return _training(suggestion=_up(), staircase=replace(worded, held=True), params=(
            ParamRow("distractor_luminance", "of full", 0.0, 1.0, value, False, source="person"),))
    for below in (_training(suggestion=_up(), staircase=replace(worded, level=2)), held(0.951)):
        pane = _train(below)
        assert "full brightness" not in pane and "is at its hardest step" not in pane
        assert ("<b>Ready for Crowd.</b> 41 of the last 50 answers at its hardest step, 1, were "
                "right (82%).</div>") in pane
    assert full in _train(held(1.0))
    # Nothing suggested, no prompt.
    assert "prompt" not in _train(_training())


def test_move_up_sends_next_block_and_hold_sends_decline():
    """*Move up* (*Move back*) sends `next_block` (`back_block`) naming the suggestion it confirms,
    and *Hold* sends `decline` naming it (Task 4's wire): the buttons carry the move and the id, the
    script builds the body from them, held against a double click as a clear is, and `wlx serve`
    reads those bodies as the commands that answer it. The existing *next block* and *back one*
    send none, moves by hand."""
    handler = re.search(
        r'document\.addEventListener\("click", function \(e\) \{(.*?)\n  \}\);', _SCRIPT, re.S
    ).group(1)
    pane = _train(_training(suggestion=_up(12)))

    assert ('data-cmd="confirm" data-move="next_block" data-suggestion="12">Move up to Crowd'
            in pane)
    assert 'data-cmd="decline" data-suggestion="12">Hold at Fade-in' in pane
    for line in (
        'if (cmd === "confirm" || cmd === "decline") {',
        'var answered = Number(button.getAttribute("data-suggestion"));',
        'if (!clearAllowed(e.detail, cmd + "/" + answered)) { return; }',
        'post(cmd === "decline" ? { kind: "decline", suggestion: answered }',
        ': { kind: button.getAttribute("data-move"), suggestion: answered });',
    ):
        assert line in handler, line
    assert handler.index('cmd === "confirm"') < handler.index("command(cmd);")
    assert parse_command({"kind": "next_block", "suggestion": 12, "by": "jake"}) == NextBlock(
        by=Box("jake"), suggestion=12)
    assert parse_command({"kind": "back_block", "suggestion": 12, "by": "jake"}) == BackBlock(
        by=Box("jake"), suggestion=12)
    assert parse_command({"kind": "decline", "suggestion": 12, "by": "jake"}) == Decline(
        suggestion=12, by=Box("jake"))
    # The plan row's moves by hand name no suggestion.
    assert "post({ kind: cmd });" in handler


def test_widen_shows_a_picker_of_unused_pairings():
    """"Trainer picks at the prompt": a widening offers the pairings the pool does not hold yet, in
    its declared order, each with its number; *add* sends the pool's value now with them (Task 5's
    whole number, the `set` that answers it), and *Hold* declines it. Met on the window that moves
    the stage up, it shares that prompt, the stage's first, whose one *Hold* holds both (Task 5); at
    the top stage a widening stands beside a move back as a prompt of its own."""
    alone = _train(_training(widen=_widening()))
    both = _train(_training(suggestion=_up(), widen=_widening()))
    top = _train(_training(suggestion=_back(), widen=_widening(), next_block=None))
    handler = re.search(
        r'document\.addEventListener\("click", function \(e\) \{(.*?)\n  \}\);', _SCRIPT, re.S
    ).group(1)

    picker = ('<label class="chk"><input type="checkbox" data-widen="2" data-suggestion="8" '
              'aria-label="add pairing red&gt;blue"> red&gt;blue</label><label class="chk"><input '
              'type="checkbox" data-widen="8" data-suggestion="8" aria-label="add pairing '
              'red&gt;purple"> red&gt;purple</label><button type="button" class="btn" '
              'data-cmd="widen" data-suggestion="8" data-name="pairings" data-value="5">add the '
              'pairings ticked</button>')
    assert ('<div class="prompt" data-prompt="8"><div><b>Ready for more pairings.</b> 41 of the '
            'last 50 answers at its hardest step were right (82%), over the 2 pairings on. Tick '
            'those to add; adding any starts both bars afresh.</div><div class="acts">' + picker
            + '<button type="button" class="btn" data-cmd="decline" data-suggestion="8">Hold'
            '</button></div></div>') in alone
    assert "blue&gt;red</label>" not in alone and "purple&gt;red</label>" not in alone
    assert both.count('class="prompt') == 1 and both.count('data-cmd="decline"') == 1
    assert ('Hold at Fade-in</button></div><div><b>And ready for more pairings.</b> Tick those to '
            'add; adding any starts both bars afresh.</div><div class="acts">' + picker
            + "</div></div>") in both
    assert top.count('class="prompt') == 2 and top.count('data-cmd="decline"') == 2
    assert top.index('data-prompt="9"') < top.index('data-prompt="8"')
    # *add* sends the value now plus each pairing ticked, refusing none ticked; the ticks a frame
    # would redraw are kept, by the suggestion they were ticked for.
    for line in (
        'if (cmd === "widen") {',
        "var adding = 0;",
        "if (box.checked) { adding += Number(box.getAttribute(\"data-widen\")); }",
        'if (!adding) { tell("not sent: tick a pairing to add first", "crit"); return; }',
        'post({ kind: "set", name: button.getAttribute("data-name"),',
        'value: Number(button.getAttribute("data-value")) + adding });',
    ):
        assert line in handler, line
    assert 'if (id === "rt-train") { restoreWidening(); }' in _function("swap")
    assert parse_command({"kind": "set", "name": "pairings", "value": 15, "by": "jake"}) == (
        SetParameter("pairings", 15, Box("jake")))


def _isohue_pool(*pairings, square: str | None = None):
    """A pool of the pop-out's kind (Task 9's report): each pairing two 1° discs whose colors are
    color-set lights of the isohue set (the tests' fixture), the odd one's at full and the
    distractors' at a setting's fraction; with `square`, that color's odd one is also offered as a
    square among the same distractors' color, its first pairing again in another shape."""
    from wl_xcon.photometry import ColorSet, ColorSetLight
    from wl_xcon.task import Disc, P, Pool, Square

    isohue = ColorSet.load(Path(__file__).parent / "fixtures" / "isohue.json")

    def light(color: str, fraction=1.0):
        return ColorSetLight(isohue, color, fraction)

    choices = [(Disc(size=1.0, color=light(odd)),
                Disc(size=1.0, color=light(among, P("distractor_fraction"))))
               for odd, among in pairings]
    if square is not None:
        among = next(among for odd, among in pairings if odd == square)
        choices.append((Square(size=1.0, color=light(square)),
                        Disc(size=1.0, color=light(among, P("distractor_fraction")))))
    return Pool("pairings", tuple(choices), odd="target_appearance",
                distractor="distractor_appearance")


def test_a_color_set_pool_names_each_pairing_by_its_colors():
    """Task 9's report: the pop-out's looks are discs whose colors are color-set lights, so the
    panel, the widening's picker and the start form named its pairings "pairing 1" to "pairing
    12". **Each is named by its colors' names, the odd one's first** -- "blue among red" -- where
    both looks' colors are color-set lights, by the rig's own words (`task.Pool.named`, which the
    start form's row takes through `taskd.start_rows` and the panel's through `Session.pooled`);
    a pairing whose colors another pairing shares, in another shape, keeps its place's name, so no
    two read alike."""
    from wl_xcon.cli import _load_task
    from wl_xcon.taskd import start_rows

    pool = _isohue_pool(("blue", "red"), ("red", "blue"), ("purple", "red"))
    task = replace(_load_task(Path("tasks/visual_search.py")), pool=pool)
    _, row = start_rows(task, None, {"pairings": 5})
    names = ("blue among red", "red among blue", "purple among red")
    assert row.pairings == names and row.start == 5
    shapes = _isohue_pool(("blue", "red"), ("red", "blue"), square="blue")
    assert tuple(shapes.named(at) for at in range(3)) == ("pairing 1", "red among blue", "pairing 3")

    form = fragments(_between(preflight=replace(PREFLIGHT, pool=row)), view())["preflight"]
    pane = _train(_training(pool=Pooled("pairings", row.pairings, 5), widen=_widening()))

    assert ('<input type="checkbox" data-pairing="1" checked aria-label="pairing blue among red">'
            ' blue among red</label>') in form
    assert ('<input type="checkbox" data-pairing="2" aria-label="pairing red among blue"> red '
            'among blue</label>') in form
    assert ('<span>pairings on <b>blue among red, purple among red</b></span>'
            '<span class="nm">2 of 3; the rig suggests adding more at 80% of 50</span>') in pane
    assert ('<input type="checkbox" data-widen="2" data-suggestion="8" aria-label="add pairing '
            'red among blue"> red among blue</label>') in pane
    assert "pairing 1" not in form + pane and "Disc(" not in form + pane


def test_the_lock_sends_the_staircases_value_as_a_persons():
    """*lock at* is the existing hold (TSK-32: "a live value on its parameter holds it"): a `set`
    of the staircase's setting at the level it is at, which a person's *hand back* undoes."""
    handler = re.search(
        r'document\.addEventListener\("click", function \(e\) \{(.*?)\n  \}\);', _SCRIPT, re.S
    ).group(1)

    for line in (
        'if (cmd === "lock") {',
        'var locked = button.getAttribute("data-name");',
        'if (!clearAllowed(e.detail, "lock/" + locked)) { return; }',
        'post({ kind: "set", name: locked, value: Number(button.getAttribute("data-value")) });',
    ):
        assert line in handler, line


def test_the_pane_is_empty_with_nothing_to_train_and_between_runs():
    """A run with no staircase, no confirmed progression and no pool has no panel, nor a run being
    stopped, nor anything between runs: the section is empty and the page hides it (`:empty`).
    The controls grey away from where they work, as every control does."""
    assert _train(frame()) == ""
    assert _train(_training(phase="between_runs", suggestion=_up())) == ""
    assert _train(_training(stop_kind="operator", suggestion=_up())) == ""
    assert _train(None) == ""
    assert "#rt-train:empty { display: none; }" in _CSS
    lan = _train(_training(suggestion=_up(), widen=_widening()), can_write=False)
    assert lan.count(" disabled ") == lan.count("<button") + lan.count("<input")
    assert lan.count("<button") == 4 and lan.count("<input") == 2


def test_every_string_the_panel_draws_is_escaped():
    """The stage, the setting, the unit, the outcomes and the pairings are telemetry strings: text,
    in an element or an attribute, never markup."""
    pane = _train(_training(
        block=EVIL, next_block=EVIL, plan=EVIL,
        staircase=replace(_LADDER, setting=EVIL),
        params=(ParamRow(EVIL, EVIL, 0.0, 1.0, 0.5, False, source="staircase"),),
        bars=replace(_BARS, wrong={EVIL: 1}, left_out={EVIL: 2}),
        pool=Pooled(EVIL, (EVIL, EVIL + "2", "a", "b"), 5),
        suggestion=Suggestion(7, "up", EVIL, EVIL, 41, 50, True), widen=_widening()))

    assert "<script" not in pane and EVIL not in pane
    assert html.escape(EVIL, quote=True) in pane


def test_the_lock_holds_the_level_exactly_not_as_shown():
    """*lock at* sends the level the staircase is at, exactly as the rig sent it -- a held value is
    judged against the level it stopped at (`taskd.Session._eased`), so one a hair fainter than a
    computed level of 1/3 would keep the held trials out of moving up as eased -- while the panel
    shows it to six figures."""
    third = (1 / 3, 2 / 3, 1.0)
    pane = _train(_training(staircase=replace(_LADDER, levels=third, level=0)))

    assert ('data-cmd="lock" data-name="distractor_luminance" data-value="0.3333333333333333">'
            "lock at 0.333333</button>") in pane
    assert "<b>0.333333</b>" in pane
    assert parse_command({"kind": "set", "name": "distractor_luminance",
                          "value": float("0.3333333333333333"), "by": "jake"}).value == 1 / 3


# --- A demo (demo mode §4.1-§4.3, §4.6; its plan's Task 9) ------------------------------------

#: The demo service's `REFERENCE` alone, and a rig offering it beside a real animal.
_REF_ONLY = ("REFERENCE",)
_RIG_ANIMALS = ("A", "REFERENCE")


def _tag(frame_) -> str:
    return fragments(frame_, view())["demo-tag"]


def test_the_demo_tag_shows_on_every_demo_frame_and_never_else():
    """§4.2: DEMO in the header on every frame of a demo, from the frame's own `demo`: a demo
    session's, in every phase, and a demo service's idle frame; never on a live session's, a live
    rig's idle frame -- one that offers a demo (`gaze`) included -- or before any frame. The tag
    names the session, whose drawing alone the page shows, and says whether a page may steer:
    between runs and in one, never once the session has ended."""
    phases = {"running": {}, "between_runs": {"phase": "between_runs"},
              "awaiting_return": {"phase": "awaiting_return", "stop_kind": "operator"},
              "closed": {"phase": "closed", "stop_kind": "operator"}}
    for phase, overrides in phases.items():
        tag = _tag(frame(demo=True, **overrides))
        assert ">DEMO</span>" in tag and 'data-demo="session"' in tag, phase
        assert 'data-session="2027-01-14_01"' in tag, phase
        assert ("data-steerable" in tag) == (phase in ("running", "between_runs")), phase
        assert _tag(frame(demo=False, **overrides)) == "", phase
    service = _tag(idle(demo=True, gaze=True, animals=_REF_ONLY))
    assert ">DEMO</span>" in service and 'data-demo="service"' in service
    assert 'data-session=""' in service and "data-steerable" not in service
    for live in (idle(), idle(gaze=True, animals=_RIG_ANIMALS), None):
        assert _tag(live) == ""
    document = page(fragments(frame(demo=True), view()), stale_after_s=30.0, nonce="n")
    assert re.search(r'<span id="demo-tag"><span class="pill demo"[^>]*>DEMO</span></span>',
                     document)
    assert '<span id="demo-tag"></span>' in _document()


def test_the_demo_screen_replaces_the_replica_only_while_demo():
    """§4.3: the demo screen stands where *replica · V11* is, only on a demo's page; the replica
    pane, which a live animal's screen will fill (V11), is hidden then, and shown otherwise. Both
    are static, so a frame never replaces a drawing; the script switches them as the tag comes and
    goes, and fills the screen from the stream's `drawn` events, the session's own alone (Task 8's
    carried (c))."""
    demo = page(fragments(frame(demo=True), view()), stale_after_s=30.0, nonce="n",
                can_write=True, can_gaze=True)
    live = page(fragments(frame(), view()), stale_after_s=30.0, nonce="n", can_write=True,
                can_gaze=True)
    service = page(fragments(idle(demo=True, gaze=True, animals=_REF_ONLY), view()),
                   stale_after_s=30.0, nonce="n", can_write=True, can_gaze=True)

    for document in (demo, service):
        assert re.search(r'<section class="panel glass" id="replica-pane" hidden>', document)
        assert re.search(r'<section class="panel glass demo-pane" id="demo-pane"[^>]*'
                         r'data-steer="">', document)
    assert re.search(r'<section class="panel glass" id="replica-pane">', live)
    assert re.search(r'<section class="panel glass demo-pane" id="demo-pane"[^>]*hidden>', live)
    for document in (demo, live, service):
        assert "replica · V11" in document
        assert document.count('id="demo-drawing"') == 1 and 'id="demo-dot" hidden' in document
        assert f'data-gaze-every-ms="{GAZE_EVERY_MS}"' in document
    assert '<div class="demo-none" id="demo-none">no screen yet' in demo
    # The script: the switch on the tag, the drawing on its own event, the session's alone, the
    # full window by F, a click or `#demo`, and Escape.
    assert 'source.addEventListener("drawn", onDrawn);' in _SCRIPT
    frame_switch = _script_between("  function demoFrame() {", "  function onDrawn(event) {")
    assert 'el("replica-pane").hidden = demo.on;' in frame_switch
    assert 'el("demo-pane").hidden = !demo.on;' in frame_switch
    assert 'if (!demo.on) { closeFull(); }' in frame_switch
    shown = _script_between("  function showDrawing() {", "  function openFull() {")
    assert 'svg.getAttribute("data-session") === demo.session' in shown
    assert 'wantFull: window.location.hash === "#demo"' in _SCRIPT
    assert 'if (id === "demo-tag") { demoFrame(); }' in _SCRIPT
    # One definition of the report interval (Task 7's carried item): `demoscreen`'s, imported.
    source = Path(web.__file__).read_text()
    assert "from wl_xcon.demoscreen import GAZE_EVERY_MS" in source
    assert not re.search(r"^GAZE_EVERY_MS\s*=", source, re.M)
    assert GAZE_EVERY_MS == demoscreen.GAZE_EVERY_MS == 100
    # Under the screen, the last trial's outcome, from the frame.
    under = fragments(frame(demo=True, recent_outcomes=("no_fixation", "fixation_break")),
                      view())["demo-under"]
    assert '<b class="mono" data-outcome="fixation_break">fixation break</b>' in under
    assert "none yet" in fragments(frame(demo=True, recent_outcomes=()), view())["demo-under"]
    assert "no session open" in fragments(idle(demo=True), view())["demo-under"]
    assert fragments(frame(), view())["demo-under"] == ""


def test_the_key_list_names_each_input_b_and_the_limits():
    """§3.3, §3.4, §4.6: each number key and the input it stands for (`Drawn.keys`, key k at
    k - 1), or that the task waits on none; B, which is tracker loss and hides a key pressed while
    it is held (Task 2); Escape beside it, which with nobody steering is tracker loss mid-trial
    (Task 8's carried (b)); where the keys act; and what a mouse is not, word for word, its
    sources cited by key."""
    keys = demo_keys(("lever", "feature theta", "the chair"))
    none = demo_keys(())

    assert "<dt><kbd>1</kbd></dt><dd>lever · down: lever pressed or answered; up: lever " \
           "released</dd>" in keys
    assert "<dt><kbd>2</kbd></dt><dd>feature theta · held: feature theta is above its " \
           "threshold</dd>" in keys
    assert "<dt><kbd>3</kbd></dt><dd>the chair · held: the chair moves" in keys
    assert "<kbd>4</kbd>" not in keys
    assert "<dt><kbd>1-9</kbd></dt><dd>this task waits on no other input</dd>" in none
    for document in (keys, none):
        b = document.index("<kbd>B</kbd>")
        escape = document.index("<kbd>Esc</kbd>")
        assert b < escape, "Escape's tracker loss sits beside B"
        assert "A number key pressed while B is held is not seen" in document
        assert "lets go of the eye, as hiding the tab does" in document
        assert (f"With no page steering, the eye reads as tracker loss after {pointer.LIVE_S:g} "
                f"s, so an Escape mid-trial ends that trial as tracker lost, and the run waits "
                f"before the next until a page points again") in document
        assert html.escape(DEMO_KEYS_WHERE) in document
        for limit in DEMO_LIMITS:
            assert f"<li>{html.escape(limit)}</li>" in document
    assert len(DEMO_LIMITS) == 6
    assert "[@card1977evaluation, Table 2, p. 10]" in DEMO_LIMITS[0]
    assert "[@fischer1983saccadic]" in DEMO_LIMITS[0]
    assert "1.29 s (SD 0.42)" in DEMO_LIMITS[0] and "0.36 s of homing" in DEMO_LIMITS[0]
    assert "15 cd/m²" in DEMO_LIMITS[-1]
    evil = demo_keys((EVIL,))
    assert EVIL not in evil and html.escape(EVIL, quote=True) in evil
    with pytest.raises(ValueError):
        demo_keys(tuple(str(n) for n in range(pointer.KEYS + 1)))
    # The page holds the list with no keys until a drawing brings the task's.
    assert none in page(fragments(frame(demo=True), view()), stale_after_s=30.0, nonce="n")


def test_the_dialog_on_a_demo_service_offers_reference_alone_with_now_filled():
    """§4.1: a demo service's New session dialog offers `REFERENCE` alone, chosen -- whatever else
    its frame lists -- says every session there is a demo, and its script fills *←cage at* with
    the clock's time and the id with `demo-YYYYMMDD-HHMMSS`, both editable, and sends `demo`
    (the browser's own test plays it)."""
    parts = fragments(idle(demo=True, gaze=True, animals=("A", "REFERENCE")), view())

    assert parts["dn-subject"] == '<option value="REFERENCE">REFERENCE</option>'
    assert 'data-demo-service="1"' in parts["dn-demo"]
    assert "every session here is a demo, for REFERENCE alone" in parts["dn-demo"]
    assert 'id="dn-demo-box"' not in parts["dn-demo"]
    empty = fragments(idle(demo=True, animals=()), view())["dn-subject"]
    assert empty == f'<option value="">{NO_REFERENCE}</option>'
    assert REFERENCE == service.REFERENCE
    fill = _script_between("  function fillDemo() {", "  function unfillDemo() {")
    assert 'var left = two(now.getHours()) + ":" + two(now.getMinutes());' in fill
    assert ('var id = "demo-" + now.getFullYear() + two(now.getMonth() + 1) + two(now.getDate()) '
            '+ "-" +') in fill
    assert "two(now.getHours()) + two(now.getMinutes()) + two(now.getSeconds());" in fill
    opened = _script_between("  function openNew() {", "  function openSession() {")
    assert "if (demoService() || demoTicked()) { fillDemo(); }" in opened
    assert "demo: demoService() || demoTicked()" in _script_between(
        "  function openSession() {", "  function acceptedWarnings() {")
    # The dialog holds the choice above its fields; a session's frame shows none.
    document = page(parts, stale_after_s=30.0, nonce="n", can_write=True)
    assert document.index('<div id="dn-demo">') < document.index('id="dn-subject"')
    assert fragments(frame(), view())["dn-demo"] == ""


def test_the_rig_pages_demo_box_is_grayed_without_reference_or_gaze_saying_why():
    """§4.1 and the PI's folder answer (2026-11-14): a rig service's dialog has a **demo** box,
    offered only where its idle frame says `gaze` (a gaze endpoint and a `--demo-root`) and offers
    `REFERENCE`; grayed otherwise, saying why where it is grayed and in its title: no REFERENCE,
    no gaze, or both. Ticked, the script locks the subject to `REFERENCE` (read from the box) and
    fills the departure and id as a demo service does. A viewer who cannot write sees it grayed as
    every control, and the https page's waits for the sign-in."""
    def box(frame_, view_=None):
        return fragments(frame_, view_ or view())["dn-demo"]

    offered = box(idle(gaze=True, animals=_RIG_ANIMALS))
    assert re.search(r'<input type="checkbox" id="dn-demo-box" data-reference="REFERENCE">',
                     offered)
    assert "demo-why" not in offered
    cases = {
        (False, _RIG_ANIMALS): NO_GAZE,
        (True, ("A",)): NO_REFERENCE,
        (False, ("A",)): f"{NO_GAZE}; {NO_REFERENCE}",
    }
    for (gaze, animals), why in cases.items():
        grayed = box(idle(gaze=gaze, animals=animals))
        assert re.search(r'id="dn-demo-box" data-reference="REFERENCE" disabled title="'
                         + re.escape(html.escape(why, quote=True)) + '">', grayed), why
        assert f'<span class="sub" id="dn-demo-why">{html.escape(why)}</span>' in grayed, why
    assert NO_REFERENCE == "no REFERENCE folder under --subjects"
    assert NO_GAZE == "this rig names no gaze endpoint or no --demo-root"
    lan = box(idle(gaze=True, animals=_RIG_ANIMALS), view(can_write=False))
    assert re.search(r'id="dn-demo-box"[^>]* disabled title="[^"]+">', lan)
    https = box(idle(gaze=True, animals=_RIG_ANIMALS), view(can_write=False, signin=True))
    assert re.search(r'id="dn-demo-box"[^>]* disabled data-signin title=', https)
    # The rig's dialog keeps its animals, none chosen, the demo box beside them.
    assert fragments(idle(gaze=True, animals=_RIG_ANIMALS), view())["dn-subject"].startswith(
        '<option value="">choose the animal</option>')
    changed = _script_between('    else if (e.target.id === "dn-demo-box") {',
                              '    else if (e.target.id === "task-sel") {')
    assert "if (demoBoxed) { fillDemo(); } else { unfillDemo(); }" in changed
    assert "lockSubject(demoBoxed);" in changed
    lock = _script_between("  function lockSubject(locked) {", "  function restoreDemoBox() {")
    assert 'choose(subject, box.getAttribute("data-reference"));' in lock
    assert "subject.disabled = true;" in lock


def test_a_stranded_demo_in_the_demo_folder_holds_up_only_demos_and_new_session_stays():
    """XC-504: a rig's stranded demo (`Stranded.demo_folder`) holds up only another demo, so the
    page says so in a banner of its own, offers *end session…* and no resume, keeps *new session*
    live beside it, and grays the demo box saying why. A stranded session under `--root`, a demo
    service's own demo among them, still holds up every open, as before."""
    demo = Stranded("demo-20261114-101200", "REFERENCE", 1_700_000_000.0, False,
                    "a demo is never resumed, only ended: record its return with End session",
                    demo_folder=True)
    parts = fragments(idle(gaze=True, animals=_RIG_ANIMALS, stranded=(demo,)), view())
    button = '<button type="button" class="btn small primary" data-cmd="new">new session</button>'

    assert '<span class="tag">Stranded demo</span>' in parts["banners"]
    assert "a real animal's session opens beside it" in parts["banners"]
    assert "no demo opens until it is" in parts["banners"]
    assert "no session opens" not in parts["banners"]
    assert 'data-return="demo-20261114-101200"' in parts["banners"]
    assert "data-resume" not in parts["banners"]
    assert button in parts["banners"] and button in parts["setup"]
    assert html.escape(DEMO_STRANDED) in parts["dn-demo"] and "disabled" in parts["dn-demo"]
    unreadable = fragments(idle(stranded=(Stranded("demo-1", "", None, demo_folder=True),)),
                           view())
    assert "cannot be read, so no demo opens" in unreadable["banners"]
    assert button in unreadable["banners"]
    real = replace(demo, demo_folder=False)
    for stranded in ((real,), (real, demo)):
        blocked = fragments(idle(stranded=stranded), view())
        assert "no session opens until it is resumed or its return recorded" in blocked["banners"]
        assert button not in blocked["banners"]
        assert re.search(r'data-cmd="new" disabled title="[^"]+">new session</button>',
                         blocked["setup"])
    service_demo = fragments(idle(demo=True, animals=_REF_ONLY, stranded=(real,)), view())
    assert button not in service_demo["banners"], "a demo service's own holds up every open"


#: An open as the New session dialog sends it, from the box's page.
_OPEN = {
    "kind": "open", "by": "jake", "session_id": "demo-20261114-120000", "animal": "REFERENCE",
    "deployment": "rig_fixed", "view": "direct", "session_kind": "training",
    "departure": "12:00", "delivered_today": None, "answer": None, "amend_to": None,
    "amend_reason": "", "accepted": [],
}


def test_an_open_carries_demo_and_a_non_boolean_is_refused():
    """§4.1: the dialog's open sends `demo`, a boolean; `wlx serve` builds it by the wire's own
    rules (`link._command_from`), and it crosses to the rig as sent (`_encode_command`,
    `_decode_command`), where `Service._open`'s demo path reads it. Absent, it is false, an open
    as every one before demo mode was; anything but a boolean is refused before anything is sent,
    from the box's page and the signed-in page alike, and on the rig's own decode too."""
    for demo in (True, False):
        command = parse_command({**_OPEN, "demo": demo})
        assert command.demo is demo
        assert link._decode_command(link._encode_command(command)) == command
        signed = parse_command({**{k: v for k, v in _OPEN.items() if k != "by"}, "demo": demo},
                               actor=Member("Jake Westerberg", "acct-1", "https://wl.works", "t-1"))
        assert signed.demo is demo
    assert parse_command(_OPEN).demo is False
    for bad in (1, 0, "true", None, [], {}):
        with pytest.raises(BadCommand, match="an open's demo is true or false"):
            parse_command({**_OPEN, "demo": bad})
        with pytest.raises(link.CommandRefused, match="an open's demo is true or false"):
            link._command_from({**_OPEN, "by": {"kind": "box", "name": "jake"}, "demo": bad})


def test_a_timing_card_offers_fixed_and_drawn_with_each_shapes_fields():
    """The timing switch (the console settings design's §3; the PI, 2026-11-16): a card whose
    `switch` is `drawn` -- a live setting in seconds -- offers *fixed* and *drawn*. Fixed is today's
    number field, `set`; drawn is a shape select of the five shapes (no scaling: a size's) and each
    shape's fields, with *apply*, which sends `form`. The side open is drawn where a draw is in
    force (`shape`), its shape selected and its numbers filled; fixed otherwise. A card the
    person's draw gives says so, names what it overrides -- its draw, its conditions or its
    staircase -- and offers *hand back*. A card with no switch shows neither. Greyed away from the
    box."""
    person = {"shape": "non_aging", "numbers": {"shortest": 0.75, "longest": 1.25},
              "values": [], "weights": [], "by": "person"}
    block = {"shape": "uniform", "numbers": {"low": 0.2, "high": 0.4}, "values": [],
             "weights": [], "by": "block"}
    listed = {"shape": "weights", "numbers": {}, "values": [0.3, 0.5], "weights": [3.0, 1.0],
              "by": "task"}
    rows = (
        ParamRow.of("fix_hold", "s", 0.05, 2.0, 0.3, False, (), "task", (), None, None, "drawn"),
        ParamRow.of("wait", "s", 0.05, 2.0, 0.3, False, (), "form", (),
                    "uniform from 0.2 s to 0.4 s", None, "drawn", person),
        ParamRow.of("gap", "s", 0.05, 2.0, 0.3, False, (), "draw", (),
                    "uniform from 0.2 s to 0.4 s", {"low": 0.2, "high": 0.4}, "drawn", block),
        ParamRow.of("hold", "s", 0.05, 2.0, 0.3, False, (), "draw", (),
                    "one of 0.3 s, 0.5 s, weighted 3.0:1.0", None, "drawn", listed),
        ParamRow.of("fix_window", "deg", 0.5, 5.0, 2.0, False),
    )
    params = fragments(frame(params=rows), view())["params"]
    lan = fragments(frame(params=rows), view(can_write=False))["params"]
    cards = _cards(params)

    fixed = cards["fix_hold"]
    assert ('<div class="sw" role="group" aria-label="fix_hold: fixed or drawn">'
            '<button type="button" class="btn small seg on" data-switch="fixed" '
            'data-name="fix_hold" aria-pressed="true">fixed</button>'
            '<button type="button" class="btn small seg" data-switch="drawn" data-name="fix_hold" '
            'aria-pressed="false">drawn</button></div>') in fixed
    assert '<div class="side fixed" data-side="fixed">' in fixed
    assert '<div class="side drawn" data-side="drawn" hidden>' in fixed
    assert 'data-param="fix_hold"' in fixed.split('data-side="fixed"')[1].split("data-side")[0]
    assert ('<select class="field" data-shape="fix_hold" aria-label="fix_hold: shape">'
            '<option value="non_aging" selected>non-aging</option>'
            '<option value="uniform">uniform</option>'
            '<option value="normal">normal, cut</option>'
            '<option value="list">a list, in shuffled passes</option>'
            '<option value="weights">a list, weighted</option></select>') in fixed
    assert "scaled" not in fixed
    for shape, numbers in (("non_aging", ("shortest", "longest")), ("uniform", ("low", "high")),
                           ("normal", ("mean", "sd", "low", "high")), ("list", ("values",)),
                           ("weights", ("values", "weights"))):
        fields = fixed.split(f'data-fields="{shape}"')[1].split("</div>")[0]
        for number in numbers:
            assert (f'<label class="rn">{number}<input class="field mono" data-form="{number}" '
                    f'inputmode="decimal" value=""') in fields, (shape, number)
    assert fixed.count('data-fields="non_aging">') == 1
    assert 'data-fields="uniform" hidden>' in fixed
    # The box's Apply sends the drawn side (the console interface rework's Task 6): no *apply* of
    # its own.
    assert 'data-cmd="form"' not in fixed and 'data-apply="fix_hold"' in fixed

    drawn = cards["wait"]
    assert '<div class="side drawn" data-side="drawn">' in drawn
    assert '<div class="side fixed" data-side="fixed" hidden>' in drawn
    assert 'data-switch="drawn" data-name="wait" aria-pressed="true"' in drawn
    assert 'data-form="shortest" inputmode="decimal" value="0.75"' in drawn
    assert 'data-form="longest" inputmode="decimal" value="1.25"' in drawn
    assert "drawn each trial, from a person&#x27;s draw" in drawn
    assert "a person&#x27;s draw, over its draw" in drawn
    assert 'data-cmd="hand_back" data-name="wait"' in drawn
    assert '<option value="uniform" selected>uniform</option>' in cards["gap"]
    assert 'data-form="low" inputmode="decimal" value="0.2"' in cards["gap"]
    assert 'data-number="low"' in cards["gap"], "the block's range still changes"
    assert 'data-form="values" inputmode="decimal" value="0.3, 0.5"' in cards["hold"]
    assert 'data-form="weights" inputmode="decimal" value="3.0, 1.0"' in cards["hold"]
    assert "data-switch" not in cards["fix_window"] and 'data-form' not in cards["fix_window"]
    assert lan.count(f'data-apply="fix_hold" tabindex="0" disabled title="{CONTROLS_AT_THE_BOX}"'
                     ) == 1


def test_a_form_card_names_the_staircase_it_holds_and_a_staged_form_says_drawn():
    """A person's draw over the open block's staircase says so on its card (`Telemetry.staircase`
    names the setting), and a staged form is led *drawn* with its draw in the rig's words."""
    person = {"shape": "uniform", "numbers": {"low": 0.2, "high": 0.4}, "values": [],
              "weights": [], "by": "person"}
    rows = (ParamRow.of("fix_hold", "s", 0.05, 2.0, 0.3, False, (), "form", (), None, None,
                        "drawn", person),)
    stair = link.StaircaseRow("fix_hold", (0.2, 0.3, 0.4), 0, True, 3, 1)
    staged = (Staged("fix_hold", None, "uniform from 0.2 s to 0.4 s", Box("jake"), False,
                     kind="form", overrides=("c",)),)
    shown = fragments(frame(params=rows, staircase=stair, staged=staged), view())

    card = _cards(shown["params"])["fix_hold"]
    assert "a person&#x27;s draw, over its staircase" in card
    assert "staged drawn → uniform from 0.2 s to 0.4 s" in card
    assert "drawn: fix_hold unset → uniform from 0.2 s to 0.4 s" in shown["rt-changes"]


def _foreperiod_row(name: str = "wait", **over) -> ParamRow:
    """A card drawn from the PI's foreperiod, its profile as the rig sends it."""
    from wl_xcon import variation
    from wl_xcon.task import NonAging

    wait = NonAging.between(0.75, 1.25)
    shape = {**variation.shaped(wait), "by": "person"}
    return ParamRow.of(name, "s", 0.05, 2.0, 0.3, False, (), "form", (), None, None, "drawn",
                       shape, variation.profile(wait).as_dict(), **over)


def _svg(card: str) -> str:
    return card[card.index("<svg"):card.index("</svg>") + len("</svg>")]


def test_a_drawn_card_draws_its_histogram_and_hazard_against_flat():
    """§3: a drawn card carries an inline SVG, a bar for each bin of the density and a line for the
    hazard against a dashed line at 1, *flat*. The hazard's first point is 1 by construction, so
    its line starts on the flat one; the bars follow the density (the first tallest, the last
    shortest, for a wait that ends at a constant rate), and a fixed card draws none."""
    rows = (_foreperiod_row(),
            ParamRow.of("fix_hold", "s", 0.05, 2.0, 0.3, False, (), "task", (), None, None,
                        "drawn"),
            ParamRow.of("fix_window", "deg", 0.5, 5.0, 2.0, False))
    cards = _cards(fragments(frame(params=rows), view())["params"])

    assert "<svg" not in cards["fix_hold"] and "<svg" not in cards["fix_window"]
    drawn = cards["wait"]
    assert drawn.count("<svg") == 1
    assert drawn.index('data-form="shortest"') < drawn.index("<svg"), "the drawn side first"
    svg = _svg(drawn)
    bars = re.findall(r'<rect class="bar" x="[\d.]+" y="[\d.]+" width="[\d.]+" height="([\d.]+)"',
                      svg)
    assert len(bars) == 20
    heights = [float(height) for height in bars]
    assert heights[0] == max(heights) and heights[-1] == min(heights) > 0
    flat = re.search(r'<line class="flat" x1="[\d.]+" y1="([\d.]+)" x2="[\d.]+" y2="([\d.]+)"'
                     r'[^>]*stroke-dasharray', svg)
    assert flat and flat.group(1) == flat.group(2)
    line = re.search(r'<polyline class="haz" points="([^"]+)"', svg)
    points = [tuple(map(float, point.split(","))) for point in line.group(1).split()]
    assert len(points) == 20
    assert points[0][1] == float(flat.group(1)), "the hazard starts on the flat line"
    assert all(later[1] < earlier[1] for earlier, later in zip(points, points[1:])), (
        "a rising hazard climbs the page (a smaller y)")
    assert ">flat</text>" in svg
    assert "0.75 s" in svg and "1.25 s" in svg


def test_the_profile_says_it_is_the_declared_distribution():
    """§3: the figure is arithmetic of what was declared, and says so in words on the card -- never
    a measurement of the rig -- and it is plain inline SVG: no external reference, no font file."""
    card = _cards(fragments(frame(params=(_foreperiod_row(),)), view())["params"])["wait"]
    svg = _svg(card)

    assert "the declared distribution, not a measurement" in svg
    assert 'role="img"' in svg and "aria-label=" in svg
    for forbidden in ("http", "url(", "@import", "@font-face", "<image", "<foreignObject",
                      "xlink:href", "<style"):
        assert forbidden not in svg, forbidden


def test_a_lists_profile_is_drawn_one_bar_a_value():
    """A list's card draws a bar for each value, the hazard a mark on each."""
    from wl_xcon import variation
    from wl_xcon.task import Listed

    listed = Listed((0.3, 0.5, 0.9))
    row = ParamRow.of("hold", "s", 0.05, 2.0, 0.3, False, (), "form", (), None, None, "drawn",
                      {**variation.shaped(listed), "by": "person"},
                      variation.profile(listed).as_dict())
    svg = _svg(_cards(fragments(frame(params=(row,)), view())["params"])["hold"])

    assert svg.count('<rect class="bar"') == 3
    assert len(re.search(r'<polyline class="haz" points="([^"]+)"', svg).group(1).split()) == 3
    assert "0.3 s" in svg and "0.9 s" in svg


def test_a_size_card_offers_fixed_and_scaled_and_says_what_each_object_gets():
    """The console settings design's §5: a size card (`switch` `scaled`) offers *fixed* and
    *scaled*: fixed is today's number field, `set`; scaled is a factor field with *apply*, which
    sends `form`, the side open scaled where a person's scaling is in force, its factor filled. The
    card says what it gives each object in degrees, as the rig wrote it (`ParamRow.gives`), and a
    window ratio's card says the radius each object gets. A staged scaling is led "scaled". Greyed
    away from the box."""
    scaled = {"shape": "scaled", "numbers": {"factor": 0.3}, "values": [], "weights": [],
              "by": "person"}
    rows = (
        ParamRow.of("disc_size", "deg", 0.0, None, 1.0, False, (), "task", (), None, None,
                    "scaled"),
        ParamRow.of("fix_size", "deg", 0.0, None, 0.3, False, (), "form", (), None, None,
                    "scaled", scaled, gives="0° at 0° out"),
        ParamRow.of("object_window", "ratio", 0.0, None, 3.0, False, (), "task",
                    gives="radius 1.5° at 8° out, every object"),
    )
    staged = (Staged("disc_size", 1.0, "scaled, 0.3 times its eccentricity", Box("jake"), False,
                     kind="form"),)
    params = fragments(frame(params=rows, staged=staged), view())["params"]
    lan = fragments(frame(params=rows), view(can_write=False))["params"]
    cards = _cards(params)

    fixed = cards["disc_size"]
    assert ('<div class="sw" role="group" aria-label="disc_size: fixed or scaled">'
            '<button type="button" class="btn small seg on" data-switch="fixed" '
            'data-name="disc_size" aria-pressed="true">fixed</button>'
            '<button type="button" class="btn small seg" data-switch="scaled" '
            'data-name="disc_size" aria-pressed="false">scaled</button></div>') in fixed
    assert '<div class="side fixed" data-side="fixed">' in fixed
    assert '<div class="side scaled" data-side="scaled" hidden>' in fixed
    assert ('<label class="rn">factor<input class="field mono" data-form="factor" '
            'inputmode="decimal" value="" aria-label="disc_size: factor">'
            '<span class="unit">× each object&#x27;s eccentricity</span></label>') in fixed
    assert 'data-cmd="form"' not in fixed and 'data-apply="disc_size"' in fixed
    assert "select" not in fixed.split('data-side="scaled"')[1]
    assert "staged scaled → scaled, 0.3 times its eccentricity by" in fixed
    assert "gives" not in fixed

    on = cards["fix_size"]
    assert '<div class="side fixed" data-side="fixed" hidden>' in on
    assert '<div class="side scaled" data-side="scaled">' in on
    assert 'data-form="factor" inputmode="decimal" value="0.3"' in on
    assert "scaled by eccentricity, by a person" in on
    assert "a person&#x27;s scaling, over the run&#x27;s value" in on
    assert '<span class="src gives">gives 0° at 0° out</span>' in on

    window = cards["object_window"]
    assert '<span class="src gives">gives radius 1.5° at 8° out, every object</span>' in window
    assert "data-switch" not in window
    assert 'data-switch="scaled" data-name="disc_size" aria-pressed="false" disabled' in lan


#: A color card as the rig makes it (`ParamRow.color`; the console settings design's §6), its
#: distractors' card: a saturation setting and the distractors' fraction, each with its cd/m².
_COLOR = {
    "sets": {"isohue": {"apex": [0.31272, 0.329], "luminance_cd_m2": 15.0, "design": None,
                        "hues": {"green": {"xy": [0.31324, 0.50711], "srgb": "#4A9A3E"},
                                 "red": {"xy": [0.45955, 0.32918],
                                         "srgb": "red;background:url(x)"}}}},
    "set": "isohue", "hue": "green", "approximate": True,
    "saturation": {"setting": "distractor_saturation", "value": 0.25, "cd_m2": 7.5},
    "luminance": {"setting": "distractor_fraction", "value": 0.5, "cd_m2": 7.5,
                  "set_wide": False},
}


def test_the_color_card_offers_set_hue_and_two_levels_and_says_approximate():
    """The design's §6 (the PI, 2026-11-16: "you select a set, and then you have hue options from
    the set, then you have salience options for each hue"): the set, a select; its hues, a swatch
    with its name each, the run's pressed, each sending `color` with its set and hue; then the
    saturation and the luminance, each typed in its own setting's unit with the light's cd/m²
    beside it -- the set's luminance setting saying it moves every light of the set, a level the
    task file writes as a number shown fixed there -- and the caption. A swatch's color is written
    only where the rig sent a `#rrggbb`. The look is shown in the rig's words, with no field.
    Greyed away from the box."""
    target = {**_COLOR, "hue": None, "set": None,
              "saturation": {"setting": None, "value": 1.0, "cd_m2": 15.0},
              "luminance": {"setting": "color_luminance", "value": 15.0, "cd_m2": 15.0,
                            "set_wide": True}}
    rows = (
        replace(ParamRow.of("distractor_appearance", "appearance", None, None, None, False,
                            source="run", color=_COLOR),
                words="Disc: color isohue green at saturation distractor_saturation"),
        ParamRow.of("target_appearance", "appearance", None, None, None, False, source="pool",
                    color=target),
        ParamRow.of("distractor_saturation", "fraction", 0.0, 1.0, 0.25, False),
        ParamRow.of("distractor_fraction", "fraction", 0.0, 1.0, 0.5, False),
        ParamRow.of("color_luminance", "cd/m2", 1.0, 30.0, 15.0, False),
    )
    cards = _cards(fragments(frame(params=rows), view())["params"])
    lan = _cards(fragments(frame(params=rows), view(can_write=False))["params"])

    among = cards["distractor_appearance"]
    assert '<span class="pv">Disc: color isohue green at saturation distractor_saturation</span>' in among
    assert 'data-param="distractor_appearance"' not in among
    assert ('<select class="field" data-colorset="distractor_appearance" '
            'aria-label="distractor_appearance: color set"><option value="isohue" selected>'
            'isohue</option></select>') in among
    assert ('<button type="button" class="btn small hue on" '
            'data-name="distractor_appearance" data-colorset="isohue" data-color="green" '
            'aria-pressed="true"><span class="chip" style="background:#4a9a3e"></span>green'
            '</button>') in among
    assert ('data-color="red" aria-pressed="false"><span class="chip none"></span>red</button>'
            in among)
    assert "url(x)" not in among
    assert ('saturation <span class="mono">distractor_saturation</span><input class="field mono" '
            'data-param="distractor_saturation" inputmode="decimal" value="0.25" '
            'aria-label="distractor_saturation: saturation"><span class="unit">fraction</span>'
            ' <span class="unit">· 7.50 cd/m²</span>') in among
    assert ('luminance <span class="mono">distractor_fraction</span><input class="field mono" '
            'data-param="distractor_fraction" inputmode="decimal" value="0.5"') in among
    assert "moves every light of the set" not in among
    assert COLOR_APPROXIMATE in html.unescape(among)
    assert COLOR_APPROXIMATE == ("approximate: this screen is not measured; the rig's measured "
                                 "panel decides what is drawn")

    odd = cards["target_appearance"]
    assert 'aria-pressed="true"' not in odd
    assert ('saturation <span class="mono">1.00</span>, fixed in the task file'
            ' <span class="unit">· 15.00 cd/m²</span>') in odd
    assert 'data-param="color_luminance"' in odd and "moves every light of the set" in odd
    assert all(card.count(" disabled") >= 4 for name, card in lan.items()
               if name in ("distractor_appearance", "target_appearance"))
    assert "data-colorset" not in cards["distractor_saturation"]


# --- the Training tab (the console settings design's §8; the build's Task 10) -----------------


def _tab(document: str, tab: str) -> str:
    """The inner HTML of tab panel `tab`, up to the next tab panel or the end of the panels."""
    start = document.index(f'<div class="tabpanel" id="{tab}">')
    end = document.find('<div class="tabpanel"', start + 1)
    return document[start:end if end != -1 else len(document)]


def test_the_training_tab_holds_the_switch_the_panel_and_the_training_sections():
    """**A Training tab of its own** (§8; the PI, 2026-11-16: "the training parameters should be in
    a whole different tab ... and easily toggleable"): its label beside the others, its panel
    holding the switch -- *on · frozen · full task*, the position in force pressed, each sending
    `shaping` with its position, *full task* grayed with why where the plan declares none -- the
    trainer's panel (`rt-train`), moved from the Runtime tab, and the cards of every section under
    `Training`, which the Task parameters tab no longer holds."""
    rows = (ParamRow.of("fix_hold", "s", 0.0, 10.0, 0.3, False, section="Timing"),
            ParamRow.of("fade_step", "cd/m2", 0.0, 10.0, 2.0, False, section="Training/stages"),
            ParamRow.of("bar", "answers", 1.0, 50.0, 40.0, False, section="Training"))
    shown = frame(params=rows, phase="running", shaping="frozen", full_task=False,
                  plan="train", block="Crowd", next_block=None,
                  staircase=StaircaseRow("set_size", (4, 6, 8), 1, False, 3, 1))
    parts = fragments(shown, view(can_write=True))
    document = page(parts, stale_after_s=30.0, nonce="n0nce", can_write=True)

    assert '<label class="tab" for="t-training">Training</label>' in document
    assert '<input type="radio" name="tab" id="t-training">' in document
    training = _tab(document, "tp-training")
    assert 'id="rt-train"' in training and 'id="rt-train"' not in _tab(document, "tp-runtime")
    assert 'id="shaping"' in training and 'id="training-params"' in training
    switch = parts["shaping"]
    assert re.findall(r'data-cmd="shaping" data-position="(\w+)" aria-pressed="(\w+)"', switch) == [
        ("on", "false"), ("frozen", "true"), ("full", "false")]
    full = re.search(r'<button[^>]*data-position="full"[^>]*>', switch).group(0)
    assert " disabled" in full and html.escape(web.NO_FULL_TASK, quote=True) in full
    assert f"full task: {html.escape(web.NO_FULL_TASK, quote=True)}" in switch
    assert ">on</button>" in switch and ">full task</button>" in switch
    assert "fade_step" in parts["training-params"] and "bar" in parts["training-params"]
    assert "fade_step" not in parts["params"] and "fix_hold" in parts["params"]
    assert "Training" not in re.findall(r'data-sec="([^"]+)"', parts["params"])
    assert "fix_hold" not in parts["training-params"]
    declared = fragments(replace(shown, full_task=True), view(can_write=True))["shaping"]
    assert " disabled" not in re.search(r'<button[^>]*data-position="full"[^>]*>',
                                        declared).group(0)
    assert "full task:" not in declared
    # A run with no switch, and between runs, each says why there is none.
    assert "no training to switch" in fragments(replace(shown, shaping=""), view())["shaping"]
    assert "no run in progress" in fragments(replace(shown, phase="between_runs"), view())["shaping"]
    # And the page's script sends the switch's position.
    assert 'kind: "shaping", position: button.getAttribute("data-position")' in _SCRIPT


def test_runtime_says_the_switch_in_one_line():
    """**The Runtime tab keeps one line** (`rt-shaping`; §8), so nothing the Training tab holds is
    hidden: `training frozen · stage Crowd · Training tab`, the last a link to the tab; `full
    task` while it plays; none for a run with no switch, nor between runs. A card the switch holds
    says what it holds it at."""
    shown = frame(phase="running", shaping="frozen", block="Crowd")
    line = fragments(shown, view())["rt-shaping"]
    text = re.sub(r"<[^>]+>", "", line)

    assert text == "training frozen · stage Crowd · Training tab"
    assert '<label for="t-training"' in line
    assert re.sub(r"<[^>]+>", "", fragments(replace(shown, shaping="full"), view())[
        "rt-shaping"]) == "full task · stage Crowd · Training tab"
    assert fragments(replace(shown, shaping=""), view())["rt-shaping"] == ""
    assert fragments(replace(shown, phase="between_runs"), view())["rt-shaping"] == ""
    document = page(fragments(shown, view()), stale_after_s=30.0, nonce="n0nce")
    assert 'id="rt-shaping"' in _tab(document, "tp-runtime")
    cards = fragments(replace(shown, params=(
        ParamRow.of("set_size", "objects", 1.0, 12.0, 6, False, source="frozen"),
        ParamRow.of("fix_luminance", "cd/m2", 0.0, 80.0, 40.0, False, source="full"))),
        view())["params"]
    assert "frozen at 6.00 " in cards and "training frozen" in cards
    assert "full task at 40.00 " in cards and "given by the full task" in cards


# --- the console interface rework's Task 5: the box, drawn (the design of 2026-11-19) ----------
#
# A setting is a small box of three zones -- head, editor, status -- and a *more* that opens in
# place (the PI, 2026-11-19: "Small boxes"; the controls review's §2). The markup Tasks 6 to 8
# script against: `<div class="box" data-card="<name>">` holding `.head`, `.editor`, `.status`
# and `<details class="more">`.

from html.parser import HTMLParser  # noqa: E402

_VOID = frozenset({"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta",
                   "param", "source", "track", "wbr"})


class _Node:
    def __init__(self, tag: str, attrs: dict, parent: "_Node | None") -> None:
        self.tag, self.attrs, self.parent, self.children = tag, attrs, parent, []

    def classes(self) -> set:
        return set((self.attrs.get("class") or "").split())

    def text(self) -> str:
        return "".join(child if isinstance(child, str) else child.text()
                       for child in self.children)

    def walk(self):
        for child in self.children:
            if isinstance(child, _Node):
                yield child
                yield from child.walk()

    def find(self, cls: str) -> "list[_Node]":
        return [node for node in self.walk() if cls in node.classes()]

    def zone(self, cls: str) -> "_Node":
        (found,) = [child for child in self.children
                    if isinstance(child, _Node) and cls in child.classes()]
        return found


class _Tree(HTMLParser):
    """The fragment as a tree of elements: enough to say which zone of a box a text is in."""

    def __init__(self, markup: str) -> None:
        super().__init__(convert_charrefs=True)
        self.root = self.at = _Node("root", {}, None)
        self.feed(markup)

    def handle_starttag(self, tag, attrs):
        node = _Node(tag, dict(attrs), self.at)
        self.at.children.append(node)
        if tag not in _VOID:
            self.at = node

    def handle_startendtag(self, tag, attrs):
        self.at.children.append(_Node(tag, dict(attrs), self.at))

    def handle_endtag(self, tag):
        node = self.at
        while node is not None and node.tag != tag:
            node = node.parent
        if node is not None and node.parent is not None:
            self.at = node.parent

    def handle_data(self, data):
        self.at.children.append(data)


def _box(params: str, name: str) -> _Node:
    """The box of the setting `name` in a parameters pane, as a tree."""
    (box,) = [node for node in _Tree(params).root.walk()
              if node.attrs.get("data-card") == name]
    assert "box" in box.classes() and box.tag == "div", box.attrs
    return box


def _said(node: _Node) -> str:
    return " ".join(node.text().split())


def test_a_box_shows_its_plain_name_and_code_name():
    """The design's goal 5 (the PI, 2026-11-19: "Plain name, code name small"): a box's head leads
    with the plain name its task declares (`ParamRow.label`) and the code name small beneath it;
    a setting with no plain name shows its code name alone, as the name. Each is whole in its
    `title`, so a name cut short at a narrow box is still read; the head ends with the value in
    force. The box is the markup Tasks 6 to 8 script: `div.box[data-card]` with `.head`,
    `.editor`, `.status` and `details.more`, in that order."""
    rows = (ParamRow.of("fix_hold", "s", 0.0, None, 0.5, False, label="Fixation hold",
                        help="How long gaze must stay on the fixation point."),
            ParamRow.of("timeout", "s", 0.0, None, 2.0, False))
    params = fragments(frame(params=rows), view())["params"]

    named = _box(params, "fix_hold")
    zones = [child for child in named.children if isinstance(child, _Node)]
    assert [(z.tag, sorted(z.classes())) for z in zones] == [
        ("div", ["head"]), ("div", ["editor"]), ("div", ["status"]), ("details", ["more"])]
    head = named.zone("head")
    (label,) = head.find("lbl")
    (code,) = head.find("code")
    assert (_said(label), label.attrs["title"]) == ("Fixation hold", "Fixation hold")
    assert (_said(code), code.attrs["title"]) == ("fix_hold", "fix_hold")
    assert "only" not in code.classes()
    assert _said(head.find("now")[0]) == "0.50 s"
    assert "How long gaze must stay" in _said(named.zone("more"))

    # At rest the status line says the limits in short (the layout review's finding 2).
    assert _said(_box(params, "timeout").zone("status").find("say")[0]) == "0.00 or more"
    bare = _box(params, "timeout").zone("head")
    assert bare.find("lbl") == []
    (alone,) = bare.find("code")
    assert _said(alone) == "timeout" and "only" in alone.classes()
    # The small code name and the plain name are styled apart.
    assert ".box .code {" in _CSS and ".box .lbl {" in _CSS and ".box .code.only {" in _CSS


def test_a_whole_box_shows_no_decimals_and_steps_by_one():
    """The design's goal 6 (the PI: "for necessary whole numbers (set size), there should not be a
    decimal option for entry"): a setting its task declares whole (`ParamRow.whole`) shows `4`,
    never `4.00` -- in its head, its field, its limits and what is staged for it -- and its field
    steps by 1 with a numeric keyboard. A setting that is not whole keeps its step's decimals and
    never loses a digit its value holds."""
    # Whole whatever step a row says (a hand-made row's 0.01 here): the page steps it by 1.
    rows = (ParamRow.of("set_size", "objects", 1.0, 36.0, 4.0, False, whole=True),
            ParamRow.of("fix_window", "deg", 0.0, 9.0, 2.35, False, step=0.1))
    params = fragments(frame(params=rows, staged=(
        Staged("set_size", 4.0, 6.0, Box("jake"), False),)), view())["params"]

    box = _box(params, "set_size")
    whole = _said(box)
    assert not re.search(r"\d\.\d", whole), whole
    # The head: the value in force, then what waits for the next trial.
    assert _said(box.zone("head").find("now")[0]) == "4 → 6 objects"
    # The unit is said once, after what waits (the whole-build review's I4).
    assert _said(box.zone("head").find("pv")[0]) == "4"
    (field,) = [n for n in box.zone("editor").walk() if n.tag == "input"]
    assert (field.attrs["value"], field.attrs["data-step"], field.attrs["inputmode"]) == (
        "4", "1", "numeric")
    assert "1 to 36 objects" in _said(box.zone("more"))
    assert "staged → 6 by" in _said(box.zone("more"))

    other = _box(params, "fix_window")
    (field,) = [n for n in other.zone("editor").walk() if n.tag == "input"]
    assert (field.attrs["value"], field.attrs["data-step"], field.attrs["inputmode"]) == (
        "2.35", "0.1", "decimal")


def test_a_box_keeps_its_reasons_behind_more():
    """The design's goal 1 and the layout review's finding 2 (the PI: "descriptions are too
    long"): the limits with their reasons, where the value comes from, the conditions and the
    draw, *hand back*, the whole of what is staged and the whole refusal sit inside the box's
    *more*, a `<details>` that opens in place, and nowhere else on the box. The status line is one
    line: one span, never wrapped (cut short with its whole text in its `title`), the refusal's
    gist in it, its whole sentence in *more*."""
    why = ("'fix_hold' at 30 is refused, and the previous value stands: the trial ends "
           "NO_FIXATION after 10 s, while the hold can take up to 30 s, so some trials could "
           "never be answered; shorten the hold or lengthen the timeout (XC-343)")
    row = ParamRow.of("fix_hold", "s", 0.0, None, 0.5, False, source="person",
                      conditions=("near", "far"), draw="uniform from 0.4 to 0.6 s",
                      why={"low": "below 0 cannot be"})
    params = fragments(frame(params=(row,), refusals=(
        Refused("fix_hold", Box("jake"), why, cid="box-1", value=30.0),)), view())["params"]

    box = _box(params, "fix_hold")
    more = box.zone("more")
    assert more.tag == "details" and "open" not in more.attrs
    # A ⋯ in the box's head since the console interface rework's Task 8, its word its label.
    summary = more.children[0]
    assert (summary.tag, _said(summary), summary.attrs["aria-label"]) == (
        "summary", "⋯", web.MORE_SAID)
    inside = _said(more)
    outside = " ".join(_said(box.zone(z)) for z in ("head", "editor", "status"))
    for said in (_said(_Tree(web._range(row)).root), "held by a person",
                 "set or drawn by conditions near, far", "its draw: uniform from 0.4 to 0.6 s",
                 " ".join(html.unescape(why).split()), "hand back"):
        assert said in inside, said
        assert said not in outside, said
    assert [n for n in more.walk() if n.attrs.get("data-cmd") == "hand_back"]

    status = box.zone("status")
    (say,) = status.find("say")
    assert "\n" not in say.text() and not [n for n in say.walk() if n.tag in ("br", "div", "p")]
    assert _said(say).startswith("refused 30.00 · the trial ends NO_FIXATION")
    assert len(_said(say)) < len(why) and say.attrs["title"] == _said(say)
    assert "refused" in box.classes()
    rule = re.search(r"\.box \.status \.say \{([^}]*)\}", _CSS).group(1)
    assert "white-space: nowrap" in rule and "text-overflow: ellipsis" in rule
    # Apply and Discard sit at the status line's right, hidden by `visibility` until a draft, so
    # the box's height never jumps (the design's anti-goals).
    acts = status.find("acts")[0]
    assert [(n.attrs.get("data-discard"), n.attrs.get("data-apply")) for n in acts.walk()
            if n.tag == "button"] == [("fix_hold", None), (None, "fix_hold")]
    assert re.search(r"\.box \.status \.acts \{[^}]*visibility: hidden", _CSS)
    assert re.search(r"\.box\.draft \.status \.acts[^{]*\{[^}]*visibility: visible", _CSS)


def test_every_field_says_its_unit_the_drawn_side_too():
    """The design's call (the PI's units, "Seconds stay seconds, the unit beside every field, the
    drawn side's fields included"; the controls review's F9: "no unit on any of them"): every
    field a box types a number in -- its value, a value over its draw, the drawn side's shapes,
    a size's factor, its draw's live numbers -- has its unit beside it; a list's weights are
    relative, and say so."""
    shape = {"shape": "non_aging", "numbers": {"shortest": 0.5, "longest": 1.25},
             "values": [], "weights": [], "by": "person"}
    rows = (
        ParamRow.of("fix_hold", "s", 0.0, None, 0.5, False, source="form", switch="drawn",
                    shape=shape),
        ParamRow.of("fix_acquisition", "s", 0.0, None, 2.0, False, source="draw",
                    draw="uniform from 1 to 3 s", numbers={"low": 1.0, "high": 3.0}),
        ParamRow.of("disc_size", "deg", 0.0, None, 1.0, False, source="task", switch="scaled"),
        ParamRow.of("set_size", "objects", 1.0, 36.0, 4.0, False, whole=True, step=1.0),
    )
    params = fragments(frame(params=rows), view())["params"]

    fields = 0
    for name, unit in (("fix_hold", "s"), ("fix_acquisition", "s"), ("disc_size", "deg"),
                       ("set_size", "objects")):
        box = _box(params, name)
        for node in box.walk():
            if node.tag != "input" or not ({"data-param", "data-form", "data-number"}
                                           & set(node.attrs)):
                continue
            fields += 1
            said, at = None, node.parent
            while said is None and at is not box:
                units = [c for c in at.children if isinstance(c, _Node)
                         and "unit" in c.classes() and c.tag == "span"]
                said = _said(units[0]) if units else None
                at = at.parent
            assert said, (name, node.attrs)
            form = node.attrs.get("data-form")
            expected = ("relative" if form == "weights" else "× each object's eccentricity"
                        if form == "factor" else unit)
            assert said == expected, (name, node.attrs, said)
    # fix_hold: each shape's fields on its drawn side (11, a list's values and a weighted list's
    # values and weights among them) and the value over its draw; fix_acquisition: the value over
    # its draw and its two live numbers; disc_size: its field and its factor; set_size: its field.
    assert fields == 11 + 1 + 3 + 2 + 1, fields


def test_runtime_still_needed_reads_as_words():
    """The workflow review's F12 (Runtime, "Still needed": `this block has no percentage rule, so
    this changes nothing here` drawn one letter per line down 950 px): a row of the pane that holds
    a sentence and a button wraps, the button going under the sentence where both do not fit,
    never squeezing the sentence to a letter's width (`.kv.wrap`; a browser test measures it)."""
    need = fragments(frame(rule=None, owed={"ecc 10": 18}), view())["rt-need"]
    tree = _Tree(need).root
    rows = [node for node in tree.walk() if "kv" in node.classes()
            and [c for c in node.children if isinstance(c, _Node) and c.tag == "button"]
            and [c for c in node.children if isinstance(c, _Node) and "nm" in c.classes()]]
    assert len(rows) >= 3, need  # drumming, clear, and the percentage's
    assert all("wrap" in row.classes() for row in rows), [row.attrs for row in rows]
    assert any("this block has no percentage rule" in _said(row) for row in rows)
    rule = re.search(r"\.kv\.wrap \{([^}]*)\}", _CSS).group(1)
    assert "flex-wrap: wrap" in rule
    assert re.search(r"\.kv\.wrap > span \{[^}]*flex: 1 1 \d+em", _CSS)


# --- the console interface rework's Task 6: what the script reads off a box ---------------------


def test_a_box_carries_what_the_script_reads_of_its_verdicts():
    """The page's script ties each verdict to the press it answers and says who changed a box
    under a draft (the console interface rework's Task 6), from marks the box carries: the staged
    change's command id, the refusal's key and id, the trial the change in force took effect at,
    who changed it (`data-under`), and on a refusal's line what it says once a later change is
    accepted. A change waiting under an id offers *withdraw*, saying first how many it takes back;
    a reward size never does. A refused withdrawal rides in `.wdrs`, by the act's id; the run
    in progress on the sections (`data-run`, "" between runs); a whole field says so
    (`data-whole`); Apply and Discard are in the Tab order."""
    from wl_xcon.link import Applied, Refused, Staged

    jake, ana = Box("jake"), Box("Ana")
    rows = (ParamRow.of("fix_hold", "s", 0.1, 1.0, 0.3, False, step=0.05),
            ParamRow.of("response_deadline", "s", 0.2, 2.0, 0.6, False, step=0.05),
            ParamRow.of("set_size", "objects", 1.0, 36.0, 4, False, whole=True, step=1.0,
                        applied=Applied(39, "Ana (box, unverified)")),
            ParamRow.of("reward_correct", "mL", 0.0, 0.4, 0.15, True))
    staged = (Staged("fix_hold", 0.3, 0.5, jake, False, cid="p-1"),
              Staged("response_deadline", 0.6, 0.8, jake, False, cid="p-1"),
              Staged("reward_correct", 0.15, 0.2, jake, True, cid="p-2"))
    refusals = (Refused("set_size", ana, "'set_size' at 40 is refused, and the previous value "
                        "stands: it is past 36", cid="p-0", value=40),
                Refused("withdraw", jake, "the change sent as 'p-9' is not withdrawn: it is "
                        "already in force from trial 41, so nothing of it waits", cid="p-9"))
    params = fragments(frame(params=rows, staged=staged, refusals=refusals), view())["params"]
    cards = _cards(params)

    hold, size, reward = cards["fix_hold"], cards["set_size"], cards["reward_correct"]
    assert 'data-staged-cid="p-1"' in hold and 'data-under="jake (box, unverified) is changing this to 0.50"' in hold
    assert ('<span class="wd" title="withdraws the 2 applied together: fix_hold, '
            'response_deadline"><button type="button" class="btn small" data-withdraw="p-1" '
            'tabindex="0">withdraw all 2</button></span>') in hold
    assert 'data-staged-cid="p-2"' in reward and "data-withdraw" not in reward
    assert ('data-refusal="p-0" data-refusal-cid="p-0" data-applied="39" '
            'data-under="Ana (box, unverified) changed this from trial 39"') in size
    assert ('data-rest="in force from trial 39" data-rest-state="applied">refused 40 · it is past 36'
            ) in size
    assert 'data-param="set_size" data-step="1" data-min="1.0" data-max="36.0" data-whole="1"' in size
    assert 'data-whole' not in hold
    for card in cards.values():
        assert ' data-discard="' in card and 'tabindex="0">Discard' in card
        assert 'tabindex="0">Apply</button>' in card
    assert params.endswith('<div class="wdrs" hidden><span class="wdr" data-cid="p-9">it is '
                           'already in force from trial 41, so nothing of it waits</span></div>')
    assert 'data-run="2027-01-14_01/0"' in params
    between = fragments(frame(params=rows, phase="between_runs"), view())["params"]
    assert 'data-run=""' in between
    lone = fragments(frame(params=rows, staged=staged[:1]), view())["params"]
    assert 'title="takes this change back before the next trial"' in lone
    assert 'tabindex="0">withdraw</button>' in lone


# --- the console interface rework's Task 7: the pairings grid, group boxes, percents, New color -

#: The pop-out's four colors in its pool's order, each with a swatch as the rig sends one.
_POOL_COLORS = {"blue": "#2476c8", "purple": "#8a5cc2", "red": "#bf5c5c", "green": "#3f9a4a"}


def _pool_row(value=66, **fields):
    """A pool's setting's row as the rig makes it (`taskd.pool_members`): its twelve pairs in the
    pool's order, each odd color among each other, bits 1 to 2048, `on` as `value` holds them."""
    from wl_xcon.link import PoolMember

    members = tuple(
        PoolMember(bit=1 << at, odd=odd, among=among, odd_hex=_POOL_COLORS[odd],
                   among_hex=_POOL_COLORS[among], on=bool(value >> at & 1))
        for at, (odd, among) in enumerate(
            (odd, among) for odd in _POOL_COLORS for among in _POOL_COLORS if among != odd))
    return ParamRow.of("pairings", "pairings", 1.0, 4095.0, value, False, source="run",
                       whole=True, step=1.0, section="Colors", members=members, **fields)


def test_a_pool_box_draws_its_pairs_as_a_grid():
    """The design's goal 7 (the PI, 2026-11-19: "4 × 4 grid, add or remove"): the pool's box draws
    its pairs as a grid -- the odd one's color down, the distractors' across, each with the rig's
    swatch, the diagonal empty -- a tick for each pair the row lists, ticked as its `on` says,
    named for a screen reader and carrying its bit, never worked out on the page; two columns wide,
    its head saying how many pairs the pool holds, and no number field. A staged change says what
    it leaves the pool with in pairs."""
    from wl_xcon.link import Staged

    jake = Box("jake")
    params = fragments(frame(params=(_pool_row(),), staged=(
        Staged("pairings", 66.0, 2114.0, jake, False, cid="p-1"),)), view())["params"]
    box = _cards(params)["pairings"]

    assert box.startswith(' staged wide" data-card="pairings"')
    grid = re.search(r'<table class="pairs" data-pool="pairings".*?</table>', box).group(0)
    heads = re.findall(r'<th scope="(col|row)"[^>]*>(.*?)</th>', grid)
    assert [re.sub(r"<[^>]+>", "", said) for scope, said in heads if scope == "col"] == [
        "odd ↓among →", "blue", "purple", "red", "green"]
    assert [re.sub(r"<[^>]+>", "", said) for scope, said in heads if scope == "row"] == [
        "blue", "purple", "red", "green"]
    for color, hex_ in _POOL_COLORS.items():
        assert grid.count(f'<span class="chip" style="background:{hex_}"></span>{color}') == 2
    rows = re.findall(r"<tr><th scope=\"row\">.*?</tr>", grid)
    assert len(rows) == 4
    for at, line in enumerate(rows):
        cells = re.findall(r"<td[^>]*>.*?</td>", line)
        assert len(cells) == 4 and cells[at] == '<td class="diag"></td>', line
    ticks = re.findall(r'<input type="checkbox" class="tick" data-bit="(\d+)"( checked)? '
                       r'aria-label="(\w+ among \w+)"', grid)
    assert [int(bit) for bit, _, _ in ticks] == [1 << n for n in range(12)]
    assert [said for _, on, said in ticks if on] == ["blue among red", "red among blue"]
    assert 'data-param="pairings"' not in box
    assert '<span class="pv">2 of 12 pairs</span> <span class="to">→ 3 of 12 pairs</span>' in box
    assert 'data-under="jake (box, unverified) is changing this to 3 of 12 pairs"' in box
    rest = fragments(frame(params=(_pool_row(),)), view())["params"]
    assert web.POOL_REST in rest


def _group_rows(bar=0.8, window=50):
    return (
        ParamRow.of("move_up_bar", "fraction", 0.0, 1.0, bar, False, source="task", step=0.05,
                    percent=True, label="Bar to move up", group="Move up", section="Rules",
                    why={"low": "below 0 cannot be", "high": "a fraction is at most 1"}),
        ParamRow.of("fix_hold", "s", 0.1, 1.0, 0.3, False, source="task", step=0.05,
                    section="Rules"),
        ParamRow.of("move_up_window", "answers", 1.0, 200.0, window, False, source="task",
                    whole=True, step=1.0, label="Answers judged", group="Move up",
                    section="Rules"),
    )


_MOVE_UP = "Move up when at least {move_up_bar} of the last {move_up_window} answers are right"


def test_a_groups_sentence_reads_with_its_fields_in_place():
    """The design's goal 8 (the PI, 2026-11-19: "One box after Timing"; "Move up when at least
    [80]% of the last [50] answers are right"): a group's settings share one box, titled by the
    group, standing where its first setting would, its settings drawing no box of their own; its
    editor is its sentence with each setting's field in its place -- the percent's with its `%`,
    the count's with no unit, the sentence naming what it counts -- and one Apply; its head shows
    each value in force; its *more* each setting's plain name, limits and reasons; the section
    counts the group's settings. A group with no sentence lists each field under its plain name;
    one naming a ceiling never takes it in (a reward size is sent alone)."""
    from wl_xcon.link import GroupRow

    group = GroupRow("Move up", ("move_up_bar", "move_up_window"), _MOVE_UP, "Rules")
    params = fragments(frame(params=_group_rows(), groups=(group,)), view())["params"]
    cards = _cards(params)

    assert list(cards) == ["Move up", "fix_hold"]
    box = cards["Move up"]
    # `data-echo`: its fields show what its head would, so its head says it only while it differs
    # (the console interface rework's Task 8); `hidden` until it is opened in the editor (the
    # summary and editor design's goal 2).
    assert box.startswith(' group wide" data-card="Move up" data-echo hidden>')
    assert ('<span class="lbl" title="Move up">Move up</span><span class="code" '
            'title="move_up_bar, move_up_window">move_up_bar, move_up_window</span>') in box
    sentence = re.search(r'<div class="sentence">(.*?)</div><div class="status">', box).group(1)
    pieces = re.findall(r'<span class="gs">(.*?)</span>|data-param="(\w+)"[^>]*value="([^"]*)"'
                        r'|<span class="unit">(.*?)</span>', sentence)
    assert [part for piece in pieces for part in piece if part] == [
        "Move up when at least ", "move_up_bar", "80", "%", " of the last ", "move_up_window",
        "50", " answers are right"]
    assert 'data-step="5" data-min="0" data-max="100" data-percent="1"' in sentence
    assert 'data-step="1" data-min="1.0" data-max="200.0" data-whole="1"' in sentence
    assert ('<span class="now" title="80 % · 50 answers"><span class="pv">80 <span class="unit">%'
            '</span></span> · <span class="pv">50 <span class="unit">answers</span></span></span>'
            ) in box
    assert box.count('data-apply="Move up"') == 1 and "data-apply=\"move_up" not in params
    assert web.GROUP_REST in box
    assert '<span class="gn">Bar to move up</span>' in box and '0 to 100 % · a fraction is at most 100%' in box
    # The summary's header (the summary and editor design of 2026-11-19), the whole in its title.
    assert '<h4 title="Rules · 3 settings · 0 changed">Rules · 3 settings</h4>' in params

    listed = fragments(frame(params=_group_rows(), groups=(replace(group, sentence=None),)),
                       view())["params"]
    plain = _cards(listed)["Move up"]
    assert re.findall(r'<div class="gm"><span class="gl">(.*?)</span>.*?data-param="(\w+)"', plain) == [
        ("Bar to move up", "move_up_bar"), ("Answers judged", "move_up_window")]
    assert '<span class="unit">answers</span></span></div>' in plain

    reward = ParamRow.of("reward_correct", "mL", 0.0, 0.4, 0.15, True)
    paid = fragments(frame(params=_group_rows() + (reward,), groups=(
        GroupRow("Pay", ("fix_hold", "reward_correct"), None, "Rules"),)), view())["params"]
    assert list(_cards(paid))[-1] == "reward_correct" and "Pay" in _cards(paid)
    assert "reward_correct" not in _cards(paid)["Pay"]


def test_a_percent_box_says_the_rigs_numbers_in_percent():
    """The design's call: "a fraction may be shown as a percent ... its steps, limits and the rig's
    sentences are converted on the page, and the setting, the command and the record keep the
    fraction": a percent's field, head and limits ×100 with `%`, a float's noise never shown (0.07
    reads 7, 0.575 reads 57.5, a step of 0.07 steps by 7); a refusal's value and the rig's sentence about it in percent, the
    fraction's own numbers only; a setting that is no percent left as the rig wrote it."""
    from wl_xcon.link import Refused

    bar = ParamRow.of("move_up_bar", "fraction", 0.0, 1.0, 0.07, False, step=0.05, percent=True,
                      why={"low": "below 0 cannot be", "high": "a fraction is at most 1"})
    why = ("'move_up_bar' at 1.2 is refused, and the previous value stands: past-limit: "
           "'move_up_bar' at 1.2 fraction is above its 1: a fraction is at most 1 (block 2)")
    refused = (Refused("move_up_bar", Box("jake"), why, cid="p-3", value=1.2),)
    box = _cards(fragments(frame(params=(bar,), refusals=refused), view())["params"])["move_up_bar"]

    assert 'data-step="5" data-min="0" data-max="100" data-percent="1" inputmode="decimal" value="7"' in box
    assert '<span class="pv">7 <span class="unit">%</span></span>' in box
    assert "refused 120% · past-limit: &#x27;move_up_bar&#x27; at 120% is above its 100%: a fraction is at most 100%" in box
    assert "(block 2)" in box and "7.000000000000001" not in box
    assert "last refused: &#x27;move_up_bar&#x27; at 120% is refused" in box
    noisy = _cards(fragments(frame(params=(replace(bar, value=0.575),)), view())["params"])
    assert 'value="57.5"' in noisy["move_up_bar"] and "57.49" not in noisy["move_up_bar"]
    # A step of 0.07 is 7.000000000000001 × 100: its decimals would be fifteen.
    sevens = _cards(fragments(frame(params=(replace(bar, value=0.14, step=0.07),)),
                              view())["params"])["move_up_bar"]
    assert 'data-step="7" ' in sevens and 'value="14"' in sevens and "14.0" not in sevens
    plain = replace(bar, percent=False, name="hit")
    said = _cards(fragments(frame(params=(plain,), refusals=(replace(refused[0], name="hit"),)),
                            view())["params"])["hit"]
    assert "refused 1.20 · past-limit: &#x27;move_up_bar&#x27; at 1.2 fraction is above its 1" in said


def test_a_percent_is_said_in_percent_only_where_the_sentence_ties_the_number_to_it():
    """The whole-build review's I7: a number in the rig's sentence is converted only where the
    sentence ties it to a percent setting -- after its quoted name ("'move_up_bar' at 1.2"), after
    "its", given in its unit ("1.2 fraction"), or the standard limit's "a fraction is at most 1" --
    so "block 1" and "the last 1 answers" stay as written, whatever the setting's limits; and a
    peer bar's number is converted where the sentence gives it as that bar's, in either bar's box."""
    from wl_xcon.link import Refused

    up = ParamRow.of("move_up_bar", "fraction", 0.0, 1.0, 0.8, False, step=0.05, percent=True,
                     why={"low": "below 0 cannot be", "high": "a fraction is at most 1"})
    back = ParamRow.of("move_back_bar", "fraction", 0.0, 1.0, 0.5, False, step=0.05, percent=True)
    late = ("'move_up_bar' at 1.2 is refused: past-limit: 'move_up_bar' at 1.2 fraction is above "
            "its 1: a fraction is at most 1 (block 1), judged over the last 1 answers")
    order = "'move_back_bar' at 0.9 must be below 'move_up_bar' at 0.8, so it is refused"
    refused = (Refused("move_up_bar", Box("jake"), late, cid="p-1", value=1.2),
               Refused("move_back_bar", Box("jake"), order, cid="p-2", value=0.9))
    cards = _cards(fragments(frame(params=(up, back), refusals=refused), view())["params"])

    assert ("last refused: &#x27;move_up_bar&#x27; at 120% is refused: past-limit: "
            "&#x27;move_up_bar&#x27; at 120% is above its 100%: a fraction is at most 100% "
            "(block 1), judged over the last 1 answers") in cards["move_up_bar"]
    assert ("last refused: &#x27;move_back_bar&#x27; at 90% must be below &#x27;move_up_bar&#x27; "
            "at 80%, so it is refused") in cards["move_back_bar"]
    assert "100% answers" not in cards["move_up_bar"] and "block 100%" not in cards["move_up_bar"]


def test_one_new_color_panel_per_colors_section():
    """The design's call: "the new-color panel moves out of each color's box into one *New
    color…* panel for the Colors section": no color box holds one; each section holding a color
    box has one, after its boxes, keyed by the section, offering every set its boxes show, the
    first box's set chosen; a section with none has none. Rewritten for the summary and editor
    design (2026-11-19): the panel stands in the editor after its section's boxes, `hidden` until
    the *New color…* line its section's summary ends with opens it (`new-color:SECTION`; the
    design's "Colors" call)."""
    def color(sets, chosen):
        return {"sets": {named: {"apex": [0.31, 0.33], "luminance_cd_m2": 15.0, "design": None,
                                 "hues": {"red": {"xy": [0.46, 0.33], "srgb": "#c76f6a"}}}
                         for named in sets},
                "set": chosen, "hue": "red", "approximate": True,
                "saturation": {"setting": None, "value": 1.0, "cd_m2": 15.0},
                "luminance": {"setting": None, "value": 15.0, "cd_m2": 15.0, "set_wide": False}}

    rows = (
        ParamRow.of("odd_color", "appearance", None, None, None, False, source="run",
                    color=color(("isohue",), "isohue"), section="Colors"),
        ParamRow.of("distractor_color", "appearance", None, None, None, False, source="run",
                    color=color(("isohue", "bright"), "bright"), section="Colors"),
        _pool_row(),
        ParamRow.of("fix_hold", "s", 0.1, 1.0, 0.3, False, section="Timing"),
        ParamRow.of("cue_color", "appearance", None, None, None, False, source="run",
                    color=color(("dim",), "dim"), section="Cues"),
    )
    params = fragments(frame(params=rows), view())["params"]

    assert params.count("<details class=\"newc\"") == 2
    assert re.findall(r'data-newc="([^"]+)"', params) == ["Colors", "Cues"]
    for card in _cards(params).values():
        card = card.partition('<details class="newc"')[0]
        assert "data-newc" not in card and "New color" not in card
    editor = params.partition('<div class="editing">')[2]
    colors = editor.partition('data-card="pairings"')[2].partition('data-card="fix_hold"')[0]
    # After the section's last box, in the editor, hidden until it is opened.
    assert ('</details></div><details class="newc" data-newc="Colors" hidden><summary>New color…'
            '</summary>') in colors
    into = re.search(r'data-newc-into[^>]*>(.*?)</select>', colors).group(1)
    assert re.findall(r'<option value="([^"]*)"( selected)?', into) == [
        ("isohue", " selected"), ("bright", ""), ("", "")]
    summary = params.partition('<div class="legend">')[0]
    opens = re.findall(r'<div class="ssec" data-section="([^"]+)">|data-open="([^"]+)"', summary)
    assert [one for pair in opens for one in pair if one] == [
        "Colors", "odd_color", "distractor_color", "pairings", "new-color:Colors",
        "Timing", "fix_hold", "Cues", "cue_color", "new-color:Cues"]
    assert ('<button type="button" class="line newcolor" data-open="new-color:Colors" '
            'title="New color… Colors: define a color and save it as a proposal">') in summary



# --- the console interface rework's Task 8: the page around the boxes ---------------------------


def test_the_bar_holds_the_runs_numbers_and_buttons_and_the_session_is_behind_a_button():
    """The design's call: "the top of the page becomes one bar that stays in view: state, trial,
    correct, fluid, cage time and the run's buttons; the session's details behind a *session*
    button". The bar's numbers are the strip's own (`_level`, `_back_to_cage`), its title the cage
    time's note; before any frame it holds none; the session's details -- who, the strip, the next
    run's task, plan and pre-flight, a scheduled stop -- stand behind *session*; the stop's confirm
    and the mark's note open in the bar; the Training tab has a find box of its own; the demo's
    keys fold to one line."""
    parts = fragments(frame(), view())
    nums = parts["bar-nums"]
    words = _said(_Tree(nums).root)
    assert words == "trial 40 correct 30 / 40 75% fluid today 61.25 mL cage by " + words.split(
        "cage by ")[1]
    cage = re.search(r'<span class="bn"( title="[^"]*")?><span class="k">cage</span>', nums)
    assert cage and "out ·" in cage.group(1)
    assert fragments(None, view())["bar-nums"] == ""
    assert "unknown" in fragments(frame(fluid_today_ml=None), view())["bar-nums"]

    document = page(parts, stale_after_s=30.0, nonce="n0nce", can_write=True)
    bar = document[document.index('<header class="topbar glass" id="bar"'):document.index("</header>")]
    for inside in ('id="state"', 'id="bar-nums"', 'id="controls"', 'id="sent"', 'id="session-btn"',
                   'id="stop-confirm"', 'id="mark-form"', 'id="stream"'):
        assert inside in bar, inside
    session = document[document.index('<section class="session" id="session"'):]
    session = session[:session.index("</section>")]
    for inside in ('id="head-id"', 'id="presence"', 'id="strip"', 'id="task-sel"', 'id="plan-sel"',
                   'id="run-trials"', 'id="pf-pill"', 'id="sched-form"'):
        assert inside in session, inside
    assert ".topbar { position: sticky; top: 0;" in _CSS
    assert ("body:has(#t-task:checked) .session, body:has(#t-training:checked) .session "
            "{ display: none; }") in _CSS
    training = _tab(document, "tp-training")
    assert 'id="tfind"' in training and 'id="pfind"' in _tab(document, "tp-task")
    assert ('<details class="demo-fold" id="demo-fold"><summary>keys and demo limits</summary>'
            '<div class="demo-keys" id="demo-keys">') in document
    assert ('<section class="panel glass pins" id="pinned-pane" aria-label="pinned settings" hidden>'
            in _tab(document, "tp-runtime"))


def test_a_section_counts_its_unsent_drafts():
    """The console interface rework's Task 8: a section's header counts what in it is not sent,
    after the rig's counts. What the rig counts is the header's one text -- `N settings`, the
    whole `N settings · M changed` in its title, a group's settings each once, a parent's taking
    in its subsections' -- so the page's
    script puts "· K not sent" after it in a slot of its own (`countDrafts`, from `showBar`, the
    one place drafts are summed), counting a group's draft by the settings it changes (`unsent`),
    and after a frame's new counts `settle` says it again. The browser test
    `test_a_section_and_its_tab_count_the_edits_not_sent` drives it."""
    from wl_xcon.link import GroupRow

    rows = (ParamRow.of("fix_hold", "s", 0.0, 1.0, 0.3, False, section="Timing", changed=True),
            ParamRow.of("move_up_bar", "fraction", 0.0, 1.0, 0.8, False, section="Rules",
                        changed=True),
            ParamRow.of("move_up_window", "answers", 1.0, 200.0, 50.0, False, section="Rules",
                        whole=True),
            ParamRow.of("fix_size", "deg", 0.0, 9.0, 0.5, False, section="Timing/points"))
    group = GroupRow("Move up", ("move_up_bar", "move_up_window"), None, "Rules")
    params = fragments(frame(params=rows, groups=(group,)), view())["params"]

    summaries = re.findall(r'<div class="ssec" data-section="([^"]+)"><h4 title="([^"]*)">([^<]*)</h4>',
                           params)
    # Rewritten for the summary and editor design (2026-11-19): the summary's section headers
    # (`.ssec > h4`) say the settings on one line, the whole with what changed in their title.
    assert summaries == [("Timing", "Timing · 2 settings · 1 changed", "Timing · 2 settings"),
                         ("Timing/points", "points · 1 setting · 0 changed", "points · 1 setting"),
                         ("Rules", "Rules · 2 settings · 1 changed", "Rules · 2 settings")]
    counting = _script_between("function unsent(box)", "  // **Pins**")
    assert 'box.classList.contains("group") ? Math.max(1, draft.changes.length) : 1' in counting
    assert 'sayIn(slotIn(header, "ns"), count)' in counting
    assert 'sayIn(slotIn(tab, "tns"), total)' in counting
    assert '" · " + count + " not sent"' in counting
    assert _script_between("function showBar() {", "var bar = ").strip() == "countDrafts();"


def test_a_box_says_its_value_in_its_head_only_where_its_field_does_not():
    """The ledger's density ruling for the console interface rework's Task 8: "the head shows the
    value in force only when it differs from the field (a draft or a waiting change), not twice".
    A box whose field shows its value in force carries `data-echo`, and the page's CSS hides its
    head's value while it has no draft, no act out and nothing waiting; a box whose head is the
    only place its value is said -- drawn each trial, held by the training switch, a position, an
    appearance, a color, a pool, a scaling -- carries none, and its head always says it."""
    rows = (
        ParamRow.of("fix_hold", "s", 0.0, 1.0, 0.3, False, source="task"),
        ParamRow.of("rule", "word", None, None, "hollow", False, source="task"),
        ParamRow.of("wait", "s", 0.0, 1.0, 0.3, False, source="draw", draw="uniform 0.2 to 0.4"),
        ParamRow.of("bar", "fraction", 0.0, 1.0, 0.8, False, source="frozen"),
        replace(ParamRow.of("place", "deg", None, None, None, False), position="10° at 45°"),
        replace(ParamRow.of("look", "appearance", None, None, None, False), words="hollow ring"),
        _pool_row(),
        ParamRow.of("disc_size", "deg", 0.0, 5.0, 1.0, False, source="form", switch="scaled",
                    shape={"shape": "scaled", "numbers": {"factor": 0.1}, "values": [],
                           "weights": [], "by": "person"}),
    )
    params = fragments(frame(params=rows), view())["params"]
    cards = _cards(params)
    echoed = {name for name, card in cards.items()
              if re.match(r'[^>]*data-card="[^"]*"[^>]*\bdata-echo\b[^>]*>', card)}
    assert echoed == {"fix_hold", "rule"}
    assert ('.box[data-echo]:not(.draft):not(.staged):not(.sending) > .head > .now '
            '{ display: none; }') in _CSS
    # The head's value is still made for every box: the script and a draft read it.
    assert all('<span class="now"' in card for card in cards.values())


def test_every_box_has_a_pin_and_a_mark_for_more_in_its_head():
    """The design's goal 9 and the ledger's density ruling for Task 8: every box, a group's too,
    holds *pin to Runtime* first in its *more* (nothing pinned as served: the page's script keeps
    the pins), and its *more* opens from a ⋯ in its head's corner, not a line of its own; the pin
    sends nothing, so no gate grays it."""
    from wl_xcon.link import GroupRow

    rows = (ParamRow.of("fix_hold", "s", 0.0, 1.0, 0.3, False, section="Rules"),
            ParamRow.of("move_up_bar", "fraction", 0.0, 1.0, 0.8, False, section="Rules"),
            ParamRow.of("move_up_window", "answers", 1.0, 200.0, 50.0, False, section="Rules"))
    group = GroupRow("Move up", ("move_up_bar", "move_up_window"), None, "Rules")
    params = fragments(frame(params=rows, groups=(group,)), view(can_write=False))["params"]

    for name in ("fix_hold", "Move up"):
        more = _box(params, name).zone("more")
        detail = more.children[1]
        first = detail.children[0]
        assert (first.tag, first.attrs["data-pin-toggle"], first.attrs["aria-pressed"],
                _said(first)) == ("button", name, "false", "pin to Runtime"), name
        assert "disabled" not in first.attrs, name
    assert ".box > .more > summary { position: absolute; top: 1px; right: 2px;" in _CSS


# --- the settings tabs as a summary and one editor (the design of 2026-11-19, Task 1) -----------


def _summary_rows():
    """A task's settings of every kind a summary line says (the plan's Task 1): a plain number, a
    whole number, a percent and a person's draw in Timing and Stimuli, a group of two in Rules, a
    color and a pool in Colors, and the reward size, a ceiling, declared first but shown last."""
    from wl_xcon.link import GroupRow

    color = {"sets": {"isohue": {"apex": [0.31, 0.33], "luminance_cd_m2": 15.0, "design": None,
                                 "hues": {"red": {"xy": [0.46, 0.33], "srgb": "#c76f6a"}}}},
             "set": "isohue", "hue": "red", "approximate": True,
             "saturation": {"setting": None, "value": 1.0, "cd_m2": 15.0},
             "luminance": {"setting": None, "value": 15.0, "cd_m2": 15.0, "set_wide": False}}
    shape = {"shape": "non_aging", "numbers": {"shortest": 0.5, "longest": 1.25},
             "values": [], "weights": [], "by": "person"}
    rows = (
        ParamRow.of("reward_correct", "mL", 0.0, 0.4, 0.15, True, step=0.01, section="Ceilings"),
        ParamRow.of("iti", "s", 0.2, 5.0, 1.0, False, source="task", step=0.05, section="Timing",
                    label="Time between trials"),
        ParamRow.of("fix_hold", "s", 0.1, 2.0, 0.5, False, source="form", step=0.05,
                    section="Timing", label="Fixation hold", switch="drawn", shape=shape),
        ParamRow.of("set_size", "objects", 1.0, 36.0, 4, False, source="task", whole=True,
                    step=1.0, section="Stimuli", label="Number of discs"),
        ParamRow.of("distractor_fraction", "fraction", 0.0, 1.0, 0.8, False, source="task",
                    step=0.05, percent=True, section="Stimuli", label="Distractor brightness"),
        ParamRow.of("odd_color", "appearance", None, None, None, False, source="run",
                    color=color, section="Colors", label="Odd disc color"),
        _pool_row(),
    ) + tuple(replace(row, section="Rules") for row in _group_rows() if row.name != "fix_hold")
    group = GroupRow("Move up", ("move_up_bar", "move_up_window"), _MOVE_UP, "Rules")
    return rows, (group,)


def _lines(params: str) -> list:
    """Each summary line, in page order: `(section, data-open, classes, mk, ln, lv)`."""
    summary = params.partition('<div class="legend">')[0]
    found = []
    for piece in re.split(r'(?=<div class="ssec")', summary)[1:]:
        section = html.unescape(re.search(r'data-section="([^"]*)"', piece).group(1))
        for classes, name, mark, label, value in re.findall(
                r'<button type="button" class="([^"]*)" data-open="([^"]*)"[^>]* title="[^"]*">'
                r'<span class="mk">([^<]*)</span><span class="ln">([^<]*)</span>'
                r'<span class="lv"[^>]*>([^<]*)</span></button>', piece):
            found.append((section, html.unescape(name), classes, mark, html.unescape(label),
                          html.unescape(value)))
    return found


def test_the_summary_has_a_line_for_every_box_in_section_order():
    """The summary and editor design's goal 1 (the PI, 2026-11-19: "perhaps some way to visualize
    all params at top and clicking opens the ability to change it below"; mock-up A): above the
    editor, one line per box, by section in the task's order with Ceilings last, each opening its
    box (`data-open` is its `data-card`), its value the rig's as the box shows it -- "1.00 s", a
    whole number's "4", a percent's "80%", a person's draw "0.5–1.25 s", a pool's "2 of 12", a
    color's hue, a group's settings' values joined -- and a Colors section ending in its New
    color… line; then the legend, then the editor holding every box hidden and its placeholder."""
    rows, groups = _summary_rows()
    params = fragments(frame(params=rows, groups=groups), view())["params"]
    lines = _lines(params)

    assert [(section, name, label, value) for section, name, _, _, label, value in lines] == [
        ("Timing", "iti", "Time between trials", "1.00 s"),
        ("Timing", "fix_hold", "Fixation hold", "0.5–1.25 s"),
        ("Stimuli", "set_size", "Number of discs", "4"),
        ("Stimuli", "distractor_fraction", "Distractor brightness", "80%"),
        ("Colors", "odd_color", "Odd disc color", "red"),
        ("Colors", "pairings", "pairings", "2 of 12"),
        ("Colors", "new-color:Colors", "New color…", ""),
        ("Rules", "Move up", "Move up", "80% · 50"),
        ("Ceilings", "reward_correct", "reward_correct", "0.15 mL"),
    ]
    boxes = list(_cards(params))
    assert [name for _, name, *_ in lines if not name.startswith("new-color:")] == boxes
    summary, _, rest = params.partition('<div class="legend">')
    assert "<details" not in summary and summary.count('<div class="ssec"') == 5
    assert rest.startswith(html.escape(web.SUMMARY_LEGEND, quote=True) + "</div>"
                           '<div class="editing"><div class="placeholder">'
                           "click a setting above to change it</div>")
    editor = rest.partition('<div class="editing">')[2]
    assert len(re.findall(r'<div class="box[^"]*" data-card="[^"]*"[^>]* hidden>', editor)) == len(boxes)
    assert '<details class="newc" data-newc="Colors" hidden>' in editor
    assert ('<h4 title="Timing · 2 settings · 0 changed">Timing · 2 settings</h4>' in summary
            and '<h4 title="Rules · 2 settings · 0 changed">Rules · 2 settings</h4>' in summary)
    assert 'data-task="tasks/fixation_detection.py" data-run="2027-01-14_01/0"' in summary
    assert web._summary_value(rows[0]) == "0.15 mL"
    # A value each trial gives its own, in short; a position and an appearance in the rig's words.
    for fields, said in (({"source": "conditions"}, "from conditions"),
                         ({"source": "pool"}, "from pairings"),
                         ({"source": "draw"}, "drawn each trial"),
                         ({"source": "range", "numbers": {"low": 1.0, "high": 3.5}}, "1–3.5 s"),
                         ({"source": "frozen"}, "frozen at 1.00 s"),
                         ({"position": "10° at 45°"}, "10° at 45°"),
                         ({"words": "hollow ring"}, "hollow ring")):
        assert web._summary_value(replace(rows[1], **fields)) == said, fields


def test_a_line_marks_what_the_rig_knows():
    """The summary and editor design's goal 3 and its call on combined states: a line marks what
    the rig's frame says, never color alone -- ◆ a value drawn each trial (`drawn`), ◷ a change
    waiting for the next trial with the value in force first and what waits after an arrow
    (`waiting`), ! the box's refusal as its status line ranks it (`refused`), ⚠ a warning
    (`warned`) -- and its classes say a value changed from the task's start (`changed`) and a
    reward size (`ceiling`); its `title` says each state in words."""
    from wl_xcon.link import Applied

    rows, groups = _summary_rows()
    rows = tuple(replace(row, changed=True) if row.name == "set_size" else
                 replace(row, applied=Applied(39, "jake"), warned=("crowded",))
                 if row.name == "distractor_fraction" else row for row in rows)
    jake = Box("jake")
    params = fragments(frame(
        params=rows, groups=groups,
        staged=(Staged("iti", 1.0, 1.5, jake, False, cid="p-1"),
                Staged("move_up_window", 50.0, 60.0, jake, False, cid="p-2")),
        refusals=(Refused("set_size", jake, "set-size: 40 objects do not fit", cid="p-3",
                          value=40.0),)), view())["params"]
    marked = {name: (classes.split(), mark, value) for _, name, classes, mark, _, value in _lines(params)}
    assert set(marked) >= {"iti", "fix_hold", "set_size", "Move up", "reward_correct"}, marked

    assert marked["iti"] == (["line", "waiting"], "◷", "1.00 → 1.50 s")
    assert marked["fix_hold"] == (["line", "drawn"], "◆", "0.5–1.25 s")
    assert marked["set_size"] == (["line", "refused", "changed"], "!", "4")
    assert marked["distractor_fraction"] == (["line", "warned"], "⚠", "80%")
    assert marked["Move up"] == (["line", "waiting"], "◷", "80% · 50 → 60")
    assert marked["reward_correct"] == (["line", "ceiling"], "", "0.15 mL")
    assert marked["odd_color"][:2] == (["line"], "")
    titles = dict((html.unescape(name), html.unescape(title)) for name, title in re.findall(
        r'class="line[^"]*" data-open="([^"]*)"[^>]* title="([^"]*)"', params))
    assert titles["iti"] == ("Time between trials (iti) · 1.00 → 1.50 s · waiting for the next "
                             "trial · jake (box, unverified)")
    assert titles["fix_hold"] == ("Fixation hold (fix_hold) · 0.5–1.25 s · drawn each trial, from a "
                                  "person's draw")
    assert titles["set_size"].startswith("Number of discs (set_size) · 4 · refused 40 · ")
    assert titles["set_size"].endswith(" · changed from the task's start")
    assert "in force, with a warning · from trial 39" in titles["distractor_fraction"]
    assert titles["reward_correct"].endswith("a welfare ceiling: sent alone, by its own Apply")
    assert 'data-open="iti" data-said="waiting for the next trial · jake (box, unverified)" ' \
        'data-unit=" s" title="' in params and '<span class="lv" data-now="1.00 s">' in params


def test_a_line_says_short_units_and_carries_what_the_page_reads():
    """The ledger's ruling for the summary and editor build's Task 2 ("the summary's short units
    ('°', 'cd/m²')"): a line says degrees as the sign against the number and cd/m² with its
    square, in force, waiting and drawn alike, while the box keeps the setting's own unit; and it
    carries what the page reads to say a draft as the rig's value is said (`markLine`):
    `data-unit`, what the line writes after a number ("°", " cd/m²", " s", "%", nothing for a whole
    number; none on a line whose value is no number), and `data-said`, the status its title says,
    where there is one."""
    from wl_xcon.link import Applied

    rows, groups = _summary_rows()
    shape = {"shape": "uniform", "numbers": {"low": 1.0, "high": 2.5},
             "values": [], "weights": [], "by": "person"}
    rows = rows + (
        ParamRow.of("fix_window", "deg", 0.0, 9.0, 2.0, False, source="task", step=0.1,
                    section="Gaze windows", label="Fixation window"),
        ParamRow.of("fix_luminance", "cd/m2", 0.0, 80.0, 40.0, False, source="task", step=1.0,
                    section="Stimuli", label="Fixation point brightness",
                    applied=Applied(12, "jake")),
        ParamRow.of("ring_radius", "deg", 0.0, 20.0, 8.0, False, source="form", step=0.1,
                    section="Stimuli", switch="drawn", shape=shape),
    )
    params = fragments(frame(params=rows, groups=groups, staged=(
        Staged("fix_window", 2.0, 1.5, Box("jake"), False, cid="p-1"),)), view())["params"]
    said = {name: value for _, name, _, _, _, value in _lines(params)}
    assert (said["fix_window"], said["fix_luminance"], said["ring_radius"]) == (
        "2.0 → 1.5°", "40 cd/m²", "1–2.5°")
    assert web._number_said(rows[-3], 2.0) == "2.0°"
    assert '<span class="unit">deg</span>' in _cards(params)["fix_window"]
    assert '<span class="unit">cd/m2</span>' in _cards(params)["fix_luminance"]
    units = {html.unescape(name): html.unescape(unit) for name, unit in re.findall(
        r'class="line[^"]*" data-open="([^"]*)"[^>]* data-unit="([^"]*)"', params)}
    assert units == {"iti": " s", "fix_hold": " s", "set_size": "", "distractor_fraction": "%",
                     "reward_correct": " mL", "fix_window": "°", "fix_luminance": " cd/m²",
                     "ring_radius": "°"}, units
    told = {html.unescape(name): html.unescape(status) for name, status in re.findall(
        r'class="line[^"]*" data-open="([^"]*)" data-said="([^"]*)"', params)}
    assert told == {"fix_window": "waiting for the next trial · jake (box, unverified)",
                    "fix_luminance": "in force from trial 12"}, told


def test_a_summary_is_as_wide_as_its_own_longest_line():
    """The ledger's ruling for the summary and editor build's Task 3: "size the summary's columns
    from the tab's own longest line (Python sets a width in `ch` from the longest label and value
    it renders, with a floor)". A tab of short names takes the floor (`SUMMARY_FLOOR_CH`); a long
    plain name widens its own tab's columns, not the other tab's; the longest plain name a task may
    declare, with its draw, is given at least the 332 px (39.5 ch of 8.4 px) Task 2 measured it
    needs (layout, not timing); a capital or a wide letter is taken as wider than a narrow one; and
    a change waiting, which the line says after an arrow, moves no column (the design's anti-goal:
    "the page jumping under the pointer")."""
    from wl_xcon.task import LABEL_LIMIT

    import math

    def width(html_text: str) -> float:
        found = re.search(r'<div class="summary" [^>]*style="column-width: ([0-9.]+)ch"', html_text)
        assert found, html_text[:200]
        return float(found.group(1))

    short = (ParamRow.of("hold", "s", 0.0, 2.0, 0.3, False, source="task", section="Timing"),
             ParamRow.of("step", "", 0.0, 1.0, 0.1, False, source="task", section="Training"))
    parts = fragments(frame(params=short), view())
    assert width(parts["params"]) == web.SUMMARY_FLOOR_CH
    assert width(parts["training-params"]) == web.SUMMARY_FLOOR_CH
    long_name = "Fixation hold, before the array is shown"[:LABEL_LIMIT]
    long = (replace(short[0], label=long_name),) + short[1:]
    parts = fragments(frame(params=long), view())
    assert width(parts["params"]) == math.ceil(web._line_width(long_name, "0.30 s") * 10) / 10
    assert width(parts["training-params"]) == web.SUMMARY_FLOOR_CH, "each tab its own"
    assert web._line_width(long_name, "0.5–1.25 s") >= 332 / 8.4
    assert (web._line_width("mmmm", "") > web._line_width("AAAA", "") > web._line_width("aaaa", "")
            > web._line_width("iiii", "")), "wide, a capital, any other, narrow"
    waiting = fragments(frame(params=long, staged=(
        Staged("hold", 0.3, 0.45, Box("jake"), False, cid="w-1"),)), view())["params"]
    assert "0.30 → 0.45 s" in waiting
    assert width(waiting) == width(parts["params"]), "a change waiting moves no column"


def test_the_editor_has_words_for_a_setting_find_hides_and_runtime_has_its_own_editor():
    """The ledger's rulings for the summary and editor build's Task 3: each settings tab's editor
    holds, hidden, the words it says where the find box hides the setting opened
    (`FIND_HIDES_OPENED`), after its placeholder; and Runtime's Pinned strip is a summary of lines
    (`#pinned`, empty until a person pins one; the page's script fills it) above an editor of its
    own (`#pinned-editing`), which says `PINNED_EMPTY` while no pinned setting is opened (the
    design's goal 9)."""
    parts = fragments(frame(), view())
    for key in ("params", "training-params"):
        if 'class="editing"' not in parts[key]:
            continue
        editor = parts[key].partition('<div class="editing">')[2]
        assert editor.startswith(f'<div class="placeholder">{web.EDITOR_EMPTY}</div>'
                                 f'<div class="findhid" hidden>{html.escape(web.FIND_HIDES_OPENED)}</div>'), key
    assert web.FIND_HIDES_OPENED == "the opened setting is hidden by find · clear find to see it"
    document = page(parts, stale_after_s=30.0, nonce="n0nce", can_write=True)
    pane = document[document.index('<section class="panel glass pins" id="pinned-pane"'):]
    pane = pane[:pane.index("</section>")]
    assert ('<div class="params" id="pinned-params"><div class="summary" id="pinned"></div>'
            f'<div class="editing" id="pinned-editing"><div class="placeholder">{web.PINNED_EMPTY}'
            '</div></div></div>') in pane
    assert '<div class="cards" id="pinned">' not in document, "the strip holds lines, not boxes"


def test_a_looks_line_says_its_segment_and_its_words_in_its_title():
    """The pop-out revision's plan, Amendments, item 6 ("check the real looks' line widths too: a
    look's words can be long"): a setting whose choices are looks, picked among segments (Task 5b),
    says on its summary line what its segment says -- "Ring" for "Ring: inner fix_act_hole,
    outer fix_act_size, color ..." -- its words whole in the line's title, and the line's width is
    taken from the short label, so the pop-out's two looks leave its summary's columns as they
    were; a change waiting says the segment it goes to, "Ring → Square" (the PI, 2026-11-20: "ring"
    everywhere, not "Annulus"). A choice short enough
    to stand whole says it whole."""
    from wl_xcon.link import ParamRow, Staged
    from wl_xcon.photometry import Gray
    from wl_xcon.task import Annulus, Disc, P, Square

    gray = Gray(P("fix_act_luminance"))
    looks = (Disc(size=P("fix_act_size"), color=gray),
             Annulus(inner=P("fix_act_hole"), outer=P("fix_act_size"), color=gray),
             Square(size=P("fix_act_size"), color=gray))
    row = ParamRow.of("fix_act_look", "appearance", None, None, looks[1], False, choices=looks,
                      source="task", section="Stimuli/fixation point",
                      label="Fixation shape at go")
    disc, ring, square = row.choices
    assert len(ring) > web.CHOICE_LABEL_LIMIT and row.words == ring
    assert web._summary_value(row) == "Ring" and ring.startswith("Ring: ")
    summary = web._summary(frame(params=(row,)), view(), False)
    (line,) = re.findall(r'<button type="button" class="line[^"]*" data-open="fix_act_look".*?'
                         r"</button>", summary)
    assert '<span class="lv" data-now="Ring">Ring</span>' in line and "Annulus" not in line
    assert html.escape(ring, quote=True) in line, "the words whole in its title"
    assert web._line_width(row.label, "Ring") < web._line_width(row.label, ring)

    # A pick is staged by its words, as the rig sends a look's change (Task 5b).
    staged = Staged("fix_act_look", ring, square, Box("jake"), False, cid="c-1")
    waiting = web._summary(frame(params=(row,), staged=(staged,)), view(), False)
    assert ">Ring → Square</span>" in waiting, waiting

    short = ParamRow.of("side", "word", None, None, "left", False, choices=("left", "right"),
                        source="task")
    assert web._summary_value(short) == "left"
