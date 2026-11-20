"""**The pop-out search, revised after the PI's try-out** (the pop-out revision's plan, Task 7; its
design, `docs/superpowers/specs/2026-11-16-popout-revision-design.md`, §2 to §6, approved by the PI
on 2026-11-16, "Approve both"), as wl-xtasks holds it, run through this engine: the fixation point
stays on and hollows out at the go; the go may follow the discs after `go_delay`, and the reaction
time runs from it; four kinds of special trial, three catches held for the task's own reward and a
probe scored as a search, each recording and strobing its kind and none stepping a staircase; every
bound the task file fixed a setting at its old number, outcomes unmoved; the fixation hold drawn
non-aging; and its full task.

Read by path from the wl-xtasks checkout, as `tests/test_popout_search.py` reads it (its module's
helpers are used here: its scripted eye, `_Eye`, and the rig's gaze world under it, `_Seen`). Engine
test material: no timing claim rests on the frames counted here, which are the simulated frame
clock's.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
from collections import Counter
from dataclasses import replace
from pathlib import Path

import pytest

import test_popout_search as popout
from wl_xcon import photometry, simeye
from wl_xcon.link import SetForm, Shaping, Simulated, Stop
from wl_xcon.photometry import D65, SRGB, ColorSetLight, colorset_xyz
from wl_xcon.run import Recorded, Scripted, run_trial
from wl_xcon.simulate import Subject, simulate
from wl_xcon.task import (
    FRESH, NOT_DIFFICULTY, Annulus, Array, Blank, Disc, Entered, Exited, FullTask, NonAging,
    Outcome, P, SaccadeTo, Square, Update, actions_of, section_of,
)

pytestmark = pytest.mark.skipif(
    popout.XTASKS is None,
    reason="no wl-xtasks checkout holding tasks/popout_search.py; the pop-out is read from there",
)

FRAME, HZ, JAKE = popout.FRAME, popout.HZ, popout.JAKE
#: The codes this module reads, `tasks/allocation.py`'s as the pop-out strobes them.
FIX_ON, ARRAY_ON, SACCADE_ONSET, GO_CUE = 4096, 4103, 4098, 4139
REWARD_COMMANDED, TIMEOUT_ON = 4102, 4138
CATCH_FIXATION_HELD, CATCH_FIXATION_BREAK = 4140, 4141
OUTCOME_CORRECT_REJECT, OUTCOME_FALSE_ALARM, OUTCOME_NO_RESPONSE = 4123, 4124, 4117
#: Each special kind's structure, its share's setting and its code, as the task declares them.
KINDS = {
    "target_absent": ("target_absent_percent", 4142),
    "odd_place_empty": ("odd_place_empty_percent", 4143),
    "distractor_alone": ("distractor_alone_percent", 4144),
    "odd_one_alone": ("odd_one_alone_percent", 4145),
}
CATCHES = ("target_absent", "odd_place_empty", "distractor_alone")
SHARES = tuple(share for share, _ in KINDS.values())
#: The bounds the task file fixed until the revision, each now a setting at its number.
BOUNDS = {"fix_hold_limit": 10.0, "landing_limit": 0.3, "target_hold_limit": 3.0,
          "catch_hold_limit": 3.0}
FIXATION, ODD_ONE, EMPTY, LOOK = popout.FIXATION, popout.ODD_ONE, popout.EMPTY, popout.LOOK


@pytest.fixture(scope="module")
def task():
    return popout._load_task(popout.TASK_FILE)


def _play_in(task, structure: str, moves, *, eye_at=(6.0, 6.0), **values):
    """One trial of `structure`, its scripted eye making `moves` (`test_popout_search._play`'s)."""
    trial = task.structures[structure]
    bound = {**popout._values(task), **values}
    eye = popout._Eye(moves, start=eye_at)
    effects = Recorded()
    result = run_trial(trial, popout._Seen(eye, trial, bound), FRAME, values=dict(bound),
                       effects=effects)
    return result, eye, effects.log


def _marks(log) -> list[int]:
    return [entry[1] for entry in log if entry[0] == "mark"]


def _rewards(log) -> list:
    return [entry for entry in log if entry[0] == "reward"]


def _param(task, name: str):
    (param,) = [param for param in task.params if param.name == name]
    return param


class _Script(Simulated):
    """A person's commands, each queued as its drain begins, and a stop at drain `stop`."""

    def __init__(self, stop: int, commands: dict | None = None) -> None:
        super().__init__()
        self.stop, self.commands, self.drains = stop, dict(commands or {}), 0

    def drain(self) -> list:
        self.drains += 1
        for command in self.commands.get(self.drains, ()):
            self.queue(command)
        if self.drains == self.stop:
            self.queue(Stop(by=JAKE))
        return super().drain()


def _session(tmp_path: Path, *, stop: int, start_block: str = "Crowd", values=None,
             commands=None, **spec):
    """A simulated session of the training plan from `start_block`, its animal the simulated eye,
    its values over the task's, stopped by a person at drain `stop`: the session and its lines."""
    made = replace(popout._spec(tmp_path, seed=spec.pop("seed", 5), start_block=start_block),
                   values=dict(values or {}), **spec)
    session = popout._opened(made, _Script(stop, commands))
    session.run()
    return session, popout._rows(session, "trials.jsonl")


# --- The fixation point stays on, and hollows out at the go (§2) ---------------------------------


def test_the_fixation_point_stays_on_and_hollows_out_at_the_go(task, tmp_path):
    """§2, the PI's rule: "a gray fix dot. then when the monkey should "act" ..., the fix dot
    changes in some way". **The point is never hidden as the go**: its hold look is a disc and its
    act look a ring of the same size, its hole half its width, each lit by the set's gray at its
    own brightness; the discs come on with the point staying, and at the go it takes its act look
    by an `Update`, never a `Hide`. On a trial line's `stimuli`: the point shown once and never off
    while the trial is answered, the array shown, and the point's `update` on the go's frame,
    changing its looks; the window `fix` scores it throughout, no remembered `center` left."""
    hold, act = _param(task, "fix_look"), _param(task, "fix_act_look")
    assert [type(look) for look in hold.choices] == [Disc, Annulus, Square]
    assert [type(look) for look in act.choices] == [Disc, Annulus, Square]
    assert hold.start == Disc(size=P("fix_size"), color=P("fix_color"))
    assert act.start == Annulus(inner=P("fix_act_hole"), outer=P("fix_act_size"),
                                color=P("fix_act_color"))
    assert {name: _param(task, name).start for name in (
        "fix_size", "fix_act_size", "fix_hole", "fix_act_hole", "fix_luminance",
        "fix_act_luminance", "fix_saturation", "fix_act_saturation")} == {
        "fix_size": 0.3, "fix_act_size": 0.3, "fix_hole": 0.15, "fix_act_hole": 0.15,
        "fix_luminance": 40.0, "fix_act_luminance": 40.0, "fix_saturation": 0.0,
        "fix_act_saturation": 0.0}
    for structure in task.structures.values():
        assert [w.name for w in structure.windows if hasattr(w, "name")] == ["fix"]
        hides = [(state, action.stimulus) for state, action in actions_of(structure)
                 if type(action).__name__ == "Hide"]
        updates = [action for _, action in actions_of(structure) if isinstance(action, Update)]
        assert updates == [Update("fix", looks=P("fix_act_look"))]
        # The point goes off only on an error's blank, never at the go.
        on_the_go = [edge for state in structure.states if state.name == "delay"
                     for edge in state.go if edge.to == "go"]
        assert [type(action).__name__ for edge in on_the_go for action in edge.do] == [
            "Update", "Mark"], hides

    session, lines = _session(tmp_path, stop=12, start_block="Fade-in")
    answered = [line for line in lines if line["outcome"] in ("correct", "wrong_target")]
    assert answered, Counter(line["outcome"] for line in lines)
    for line in answered:
        entries = line["stimuli"]
        (fix,) = [e for e in entries if e["name"] == "fix" and e["kind"] == "show"]
        (array,) = [e for e in entries if e["name"] == "search" and e["kind"] == "show"]
        (go,) = [e for e in entries if e["name"] == "fix" and e["kind"] == "update"]
        assert go["changed"] == ["looks"] and go["frame"] == array["frame"]
        assert fix["frame"] < array["frame"]
        assert fix["light_xy"] == pytest.approx(D65, abs=1e-4), "the set's gray, as before"
        if line["outcome"] == "correct":
            assert fix["off"] is None, "the point stays on to the trial's end"
        else:
            assert fix["off"] == array["off"], "an error's blank takes both off on one frame"


# --- The go and its delay (§3) -----------------------------------------------------------------


def test_at_go_delay_0_the_array_and_the_go_are_one_frame_and_rt_runs_from_it(task):
    """§3 item 5, the reaction-time version: at `go_delay` 0 **the discs and the point's change are
    drawn on one frame** -- the frame the trial enters `go` -- the array's mark then the go's
    strobed together; the reaction time (`ReactionTime`, from `go` to `flight`) runs from the go,
    the frame the point takes its act look, to the eye leaving the fixation window; an eye leaving
    on the frame after is the answer (Review Focus 3)."""
    result, eye, log = _play_in(task, "search", [LOOK, ("go", 48, ODD_ONE)], go_delay=0.0)

    assert result.outcome is Outcome.CORRECT, result.visited
    go = eye.begun["go"]
    shown = popout._shown(result)
    (changed,) = result.changed
    assert shown["search"][0] == changed.frame == go == eye.begun["delay"], (shown, changed)
    assert changed.name == "fix" and shown["fix"][1] is None
    marks = _marks(log)
    assert marks[marks.index(ARRAY_ON) + 1] == GO_CUE
    timed = task.reaction_time
    assert (timed.state, timed.to) == ("go", ("flight",))
    assert "the frame the fixation point takes its act look" in timed.note
    assert eye.begun["flight"] > go, "the reaction time is the frames from the go to the flight"

    # The eye leaving on the frame after the go is the answer, never early.
    world = Scripted(at_frame={SaccadeTo("search.target"): go + 4},
                     inside={**dict.fromkeys(range(eye.begun["await_fix"] + 5, go + 1), "fix")})
    scripted = run_trial(task.trial, world, FRAME, values=popout._values(task),
                         effects=Recorded())
    assert scripted.visited[:6] == ("between", "await_fix", "hold_fix", "delay", "go", "flight")


def test_at_go_delay_half_a_second_leaving_in_the_delay_is_early_with_the_timeout(task):
    """§3 item 5, the delayed-saccade version: at `go_delay` 0.5 the discs come on and the point
    keeps its hold look for half a second; **leaving the fixation window then is an early
    saccade**, the point and the discs off on one frame, the timeout, no go strobed and no reward.
    Held through, the go comes 0.5 s after the discs."""
    early, eye, log = _play_in(task, "search", [LOOK, ("delay", 60, ODD_ONE)], go_delay=0.5)

    assert early.outcome is Outcome.FIXATION_BREAK and early.visited[-1] == "early"
    shown = popout._shown(early)
    assert shown["search"][1] == shown["fix"][1] == eye.begun["early"]
    assert GO_CUE not in _marks(log) and not _rewards(log) and not early.changed
    assert _marks(log)[-2:] == [TIMEOUT_ON, popout.REASON[Outcome.FIXATION_BREAK]]
    assert early.frames == eye.begun["early"] + round(2.0 * HZ) - 1

    held, eye, log = _play_in(task, "search", [LOOK, ("go", 48, ODD_ONE)], go_delay=0.5)
    assert held.outcome is Outcome.CORRECT
    (changed,) = held.changed
    assert changed.frame - popout._shown(held)["search"][0] == round(0.5 * HZ)


def test_leaving_on_the_frame_the_delay_ends_is_early(task):
    """**Review Focus 3**: an `Exited` is an edge (EYE-30), so an eye that leaves the fixation
    window on the very frame the delay's wait ends must be taken by the delay's own `Exited`,
    listed first: an early saccade with the timeout -- never a go state that never sees it leave
    and waits out its deadline as no response."""
    values = {**popout._values(task), "go_delay": 0.5}

    def played(leaves: int | None):
        frames = range(250, leaves if leaves is not None else 10_000)
        world = _Began(at_frame={}, inside=dict.fromkeys(frames, "fix"))
        return run_trial(task.trial, world, FRAME, values=values, effects=Recorded()), world

    stayed, world = played(None)
    assert stayed.outcome is Outcome.NO_RESPONSE and stayed.visited[-1] == "go"
    ends = world.begun["go"] - 1  # the frame the delay's wait is taken
    left, _ = played(ends)

    assert left.outcome is Outcome.FIXATION_BREAK, left.visited
    assert left.visited[-2:] == ("delay", "early")
    after, _ = played(ends + 1)
    assert after.outcome is not Outcome.FIXATION_BREAK and "go" in after.visited


class _Began:
    """A `run.Scripted` world, keeping the first frame of each state it is told began."""

    def __init__(self, at_frame, inside) -> None:
        self.script = Scripted(at_frame=at_frame, inside=inside)
        self.begun: dict[str, int] = {}

    def __getattr__(self, name: str):
        return getattr(self.script, name)

    def began(self, state: str, frame: int) -> None:
        self.begun.setdefault(state, frame)


def test_go_delay_drawn_is_drawn_each_trial(task, tmp_path):
    """§3 item 5: "`go_delay` is a timing setting like any other, so it can be drawn". A person
    draws it uniform from 0.1 to 0.4 s; from the next trial each trial's line gives its own, in
    that range, and **on each trial the go comes that long after the discs**, on its line's
    `stimuli`."""
    drawn = SetForm(name="go_delay", shape="uniform", numbers={"low": 0.1, "high": 0.4}, by=JAKE)
    session, lines = _session(tmp_path, stop=14, start_block="Fade-in", commands={1: [drawn]})

    later = lines[1:]
    delays = [line["params"]["go_delay"] for line in later]
    assert lines[0]["params"]["go_delay"] == 0.0
    assert all(0.1 <= delay <= 0.4 for delay in delays) and len(set(delays)) == len(delays)
    (form,) = [row for row in popout._rows(session, "parameter_changes.jsonl")
               if row["kind"] == "form"]
    assert {line["drawn"]["go_delay"] for line in later} == {form["change"]}
    for line in later:
        entries = line["stimuli"]
        arrays = [e for e in entries if e["name"] == "search" and e["kind"] == "show"]
        gone = [e for e in entries if e["name"] == "fix" and e["kind"] == "update"]
        if arrays and gone:
            # The first frame its wait has run out on, counted from the frame after the discs'.
            assert gone[0]["frame"] - arrays[0]["frame"] == math.ceil(
                line["params"]["go_delay"] * HZ - 1e-9), line["params"]["go_delay"]


# --- The special trials (§4) -------------------------------------------------------------------


@pytest.mark.parametrize("kind", CATCHES)
def test_each_catch_held_pays_one_reward_and_broken_is_a_false_alarm_with_the_timeout(task, kind):
    """§4: on a catch the dot hollows out exactly as at a normal go, and **holding the fixation
    window for `catch_hold` after it is correct** -- `CORRECT_REJECT`, paid one reward, the task's
    own (`reward_correct`, bounded as every reward is), its hold, its reason and the reward's
    command strobed first; **looking away first is a false alarm**, "an error, counted": the point
    and the array off on one frame, the timeout, no reward, `FALSE_ALARM`. Each of the three."""
    held, eye, log = _play_in(task, kind, [LOOK])

    assert held.outcome is Outcome.CORRECT_REJECT, held.visited
    assert held.frames == eye.begun["go"] + round(0.5 * HZ) - 1
    assert _rewards(log) == [("reward", "reward_correct")]
    assert log[-4:] == [("mark", CATCH_FIXATION_HELD), ("mark", OUTCOME_CORRECT_REJECT),
                        ("mark", REWARD_COMMANDED), ("reward", "reward_correct")]
    (changed,) = held.changed
    assert changed.frame == eye.begun["go"], "the same change as a normal go"

    broken, eye, log = _play_in(task, kind, [LOOK, ("go", 24, EMPTY)])
    assert broken.outcome is Outcome.FALSE_ALARM, broken.visited
    assert broken.visited[-1] == "false_alarm" and not _rewards(log)
    shown = popout._shown(broken)
    assert shown["fix"][1] == shown["search"][1] == eye.begun["false_alarm"]
    assert _marks(log)[-3:] == [CATCH_FIXATION_BREAK, TIMEOUT_ON, OUTCOME_FALSE_ALARM]
    assert broken.frames == eye.begun["false_alarm"] + round(2.0 * HZ) - 1


def test_the_probe_is_scored_as_a_search_and_steps_nothing(task, tmp_path):
    """§4's fourth kind, *odd one alone*: only the odd one shows, **scored as a normal trial** --
    landing on it and holding it is correct and paid, a look to empty space an abort with the
    timeout -- and, a special trial, **it steps no staircase** ("Only normal trials move it"): a run
    of probes alone in Crowd leaves its set size where it started, each line saying it did not
    step."""
    right, _, log = _play_in(task, "odd_one_alone", [LOOK, ("go", 48, ODD_ONE)], set_size=9)
    assert right.outcome is Outcome.CORRECT and _rewards(log) == [("reward", "reward_correct")]
    astray, eye, log = _play_in(task, "odd_one_alone", [LOOK, ("go", 48, EMPTY)], set_size=9)
    assert astray.outcome is Outcome.ABORT and _marks(log)[-2:] == [TIMEOUT_ON, 4118]
    (array,) = [action.stimulus.looks for _, action in actions_of(task.structures["odd_one_alone"])
                if type(action).__name__ == "Show" and action.stimulus.name == "search"]
    assert (array.n, array.looks, array.found_by) == (1, P("odd_color"), "look")

    session, lines = _session(tmp_path, stop=25, values={"odd_one_alone_percent": 100})
    assert {line["trial_kind"] for line in lines} == {"odd_one_alone"}
    assert {line["stepped"] for line in lines} == {False}
    assert {line["params"]["set_size"] for line in lines} == {4}, "Crowd stays at its first level"
    assert Counter(line["outcome"] for line in lines)["correct"] >= 10


@pytest.mark.parametrize("kind", list(KINDS))
def test_each_special_in_alone_runs_and_records_its_kind(task, tmp_path, kind):
    """**Review Focus 4, a special kind where it degenerates**: in Alone (one disc), *odd one's
    place empty* shows the fixation point alone, *target absent* and *a distractor alone* one disc
    in the distractor color, *odd one alone* the odd one. Each runs, is held or answered for its
    reward, and each line names its kind, the stage's own `set_size` of 1 among its values."""
    share, _ = KINDS[kind]
    session, lines = _session(tmp_path, stop=10, start_block="Alone", values={share: 100})

    assert len(lines) >= 8 and {line["trial_kind"] for line in lines} == {kind}
    assert {line["params"]["set_size"] for line in lines} == {1}
    right = "correct" if kind == "odd_one_alone" else "correct_reject"
    paid = [line for line in lines if line["outcome"] == right]
    assert len(paid) >= 4, Counter(line["outcome"] for line in lines)
    assert all(line["fluid_ml"] > 0 for line in paid)
    assert session.pump.delivered and len(session.pump.delivered) == len(paid)
    for line in lines:
        arrays = [e for e in line["stimuli"] if e["name"] == "search" and e["kind"] == "show"]
        for array in arrays:
            (one,) = array["objects"]
            assert one["drawn"] is (kind != "odd_place_empty"), kind
            assert array["found_by"] == ("look" if kind == "odd_one_alone" else "none")
            assert array["target"] == (0 if kind == "odd_one_alone" else None)


@pytest.mark.parametrize("kind", ["search", *KINDS])
def test_each_special_strobes_array_on_then_its_kind_and_the_go(task, kind):
    """§4: "the marks carry it". On each special kind's array frame the array's mark is strobed,
    then its kind's code, then the go's (at `go_delay` 0, one frame); a normal search strobes the
    array's and the go's alone, after the fixation point's."""
    result, _, log = _play_in(task, kind, [LOOK])
    marks = _marks(log)

    assert marks[0] == FIX_ON
    at = marks.index(ARRAY_ON)
    expected = [ARRAY_ON, GO_CUE] if kind == "search" else [ARRAY_ON, KINDS[kind][1], GO_CUE]
    assert marks[at:at + len(expected)] == expected, marks
    assert [code for code in marks if 4142 <= code <= 4145] == expected[1:-1]


# --- Every bound a setting, nothing else moved (§3) ----------------------------------------------

#: **The old file's outcomes, through the simulated eye** (`simeye.Eye`, 85% right, 0.2 s median,
#: 5% early, engaged 85% of trials), each seed's 300 trials of the plain search at varied set
#: sizes and directions: their counts, and a digest of each trial's `(outcome, frames)` in order,
#: recorded on wl-xtasks `c30ca28`, the task before the revision, 2026-11-19.
AT_C30CA28 = {
    3: ({"correct": 209, "no_fixation": 53, "wrong_target": 29, "fixation_break": 9},
        "c5b2556b3db129f1"),
    11: ({"correct": 215, "wrong_target": 40, "no_fixation": 39, "fixation_break": 6},
         "c04f8ec51afb5866"),
    29: ({"wrong_target": 41, "correct": 208, "no_fixation": 39, "fixation_break": 12},
         "12cef5ce01fd813e"),
}


def _through_the_eye(task, seed: int, trials: int = 300) -> list:
    eye = simeye.Eye(accuracy=0.85, rt_median_s=0.2, early_rate=0.05, seed=seed, engagement=0.85)
    played = []
    for index in range(trials):
        values = popout._values(task, rotation=(37.0 * index) % 360.0, set_size=4 + index % 9)
        world = eye.world(task.trial, values, FRAME)
        result = run_trial(task.trial, world, FRAME, values=values, effects=Recorded())
        played.append((result.outcome.value, result.frames))
    return played


@pytest.mark.parametrize("seed", list(AT_C30CA28))
def test_every_bound_is_a_setting_at_its_old_value_and_nothing_else_moved(task, seed):
    """§3: "The fixed 0.3 s landing bound ... and the other fixed bounds in the task file become
    settings". **Each bound is a setting at the number the file fixed**, in `Timing/bounds`, its
    reason beside it, and no edge of any structure waits a literal number; the graces are settings
    at the engine's own, in Timing. **And nothing else moved**: the revised trial at the old starts
    (the go at once, the fixation hold fixed at its 0.5 s) gives, through the simulated eye at
    three seeds, the old file's outcomes, trial by trial and frame by frame."""
    for name, number in BOUNDS.items():
        param = _param(task, name)
        assert (param.start, param.unit, param.section) == (number, "s", "Timing/bounds"), name
    for structure in task.structures.values():
        for state in structure.states:
            for edge in state.go:
                seconds = getattr(edge.guard, "seconds", None)
                assert seconds is None or isinstance(seconds, P), (state.name, seconds)
        tolerances = structure.tolerances
        assert (tolerances.blink, tolerances.tracker_lost) == (P("blink_grace"),
                                                               P("tracker_lost_grace"))
    assert {name: (_param(task, name).start, section_of(_param(task, name))) for name in (
        "blink_grace", "tracker_lost_grace")} == {"blink_grace": (0.0, "Timing"),
                                                   "tracker_lost_grace": (0.05, "Timing")}

    played = _through_the_eye(task, seed)
    counts, digest = AT_C30CA28[seed]
    assert dict(Counter(outcome for outcome, _ in played)) == counts
    assert hashlib.sha256(json.dumps(played).encode()).hexdigest()[:16] == digest


# --- Its colors, its sections, its draws and its full task (§2, §5, §6) -------------------------


def test_the_fixation_point_at_saturation_0_is_todays_gray(task):
    """§2 and §6, and the plan's seam note (its Amendments, item 7): each fixation look's color is
    one of the four colors at its own saturation, which starts at 0, **the set's apex at the
    point's brightness: today's D65 gray**, on the default calibration -- its chromaticity D65's
    within 1e-4 and its luminance 40 cd/m² within 1e-9, whichever hue. **The luminance held is the
    set's, macaque** (`photometry.macaque_row`, COL-37), exact; its CIE Y is 40.0002, within 1e-3,
    since the set's apex is written (0.31272, 0.329), D65 to five places, not D65's (0.3127,
    0.3290), which the gray the point was is."""
    for name, (saturation, luminance) in (("fix_color", ("fix_saturation", "fix_luminance")),
                                           ("fix_act_color", ("fix_act_saturation",
                                                              "fix_act_luminance"))):
        param = _param(task, name)
        assert [light.color for light in param.choices] == list(popout.COLORS)
        assert param.start == param.choices[0]
        for light in param.choices:
            assert (light.saturation, light.luminance) == (P(saturation), P(luminance))
            bound = ColorSetLight(light.colorset, light.color, saturation=0.0, luminance=40.0)
            X, Y, Z = colorset_xyz(bound, SRGB)
            assert (X / (X + Y + Z), Y / (X + Y + Z)) == pytest.approx(D65, abs=1e-4), light
            held = sum(r * v for r, v in zip(photometry.macaque_row(SRGB), (X, Y, Z)))
            assert held == pytest.approx(40.0, abs=1e-9), light
            assert Y == pytest.approx(40.0, abs=1e-3), light


#: **The warnings the pop-out loads with since the console build** (`test_popout_search`'s
#: `test_popout_loads_clean_but_the_expected_warnings`): the default calibration's two, the plan's
#: two, and the set size read at its top.
BEFORE = {"color-on-default", "contrast-on-default", "margin-reaches-bar", "endless-plan",
          "crowded-array"}


def test_the_popout_loads_with_no_warning_it_did_not_have(task):
    """The plan's seam note: **the revision brings no new warning** (`fixation-hidden-at-go` is
    gone: the point changes its look at the go). **A saturation setting is judged at its start at
    load** (the whole-build review, the controller's ruling): the fixation point's, 0, is the set's
    gray, which every panel shows, so no `color-set-desaturated` on either calibration; and each
    warning is said once, naming the structures it is in (XC-545)."""
    from wl_xcon.check import check_task, laid_out

    allocation = popout._load_allocation(Path(popout.ALLOCATION))
    found = {}
    for name, calibration in (("default", SRGB), ("measured", popout.measured())):
        found[name] = check_task(task, allocation, geometry=popout.DIRECT, calibration=calibration,
                                 deployment=popout.Deployment.RIG_FIXED, source=popout.TASK_FILE)
        assert all(f.is_warning for f in found[name]), found[name]
    assert {f.code for f in found["measured"]} == BEFORE - {"color-on-default",
                                                            "contrast-on-default"}
    assert {f.code for f in found["default"]} == BEFORE
    # Once each, but the plan's two margins, which say two things (XC-545).
    assert Counter(f.code for f in found["default"]) == {
        **dict.fromkeys(BEFORE, 1), "margin-reaches-bar": 2}
    starts = {param.name: param.start for param in task.params if param.start is not None}
    at_starts = laid_out(task, {**starts, "set_size": 12}, allocation=allocation,
                         geometry=popout.DIRECT, calibration=SRGB,
                         deployment=popout.Deployment.RIG_FIXED)
    assert "color-set-desaturated" not in {f.code for f in at_starts}


def test_the_special_trials_section_holds_the_four_shares_and_catch_hold(task):
    """§4 and §5, and the plan's Amendments, item 4 (the PI, 2026-11-19, "One box after Timing"):
    **the section *Special trials*, right after Timing**, holds each kind's percentage -- whole,
    in percent, 0 to 100 with its reason, 0 to start -- and `catch_hold`, 0.5 s, a time a person may
    draw; **one group, one box**, read as one sentence; and the task declares the four kinds in
    that order, each playing its own structure."""
    from wl_xcon.task import SPECIAL_UNIT

    sections = list(dict.fromkeys(section_of(param).split("/")[0] for param in task.params))
    assert sections[:3] == ["Timing", "Special trials", "Gaze windows"], sections
    for share in SHARES:
        param = _param(task, share)
        assert (param.unit, param.low, param.high, param.start, param.whole, param.why,
                param.section) == (SPECIAL_UNIT, 0, 100, 0, True,
                                   "a share of trials is at most 100", "Special trials"), share
        assert task.meanings[share].kind == NOT_DIFFICULTY
    catch = _param(task, "catch_hold")
    assert (catch.unit, catch.start, catch.section) == ("s", 0.5, "Special trials")
    assert [name for name in (param.name for param in task.params)
            if section_of(_param(task, name)) == "Special trials"] == [*SHARES, "catch_hold"]
    (group,) = [group for group in task.groups if group.name == "Special trials"]
    assert group.settings == (*SHARES, "catch_hold")
    assert group.sentence == (
        "Of every 100 trials: {target_absent_percent} target absent, {odd_place_empty_percent} "
        "odd place empty, {distractor_alone_percent} a distractor alone, {odd_one_alone_percent} "
        "the odd one alone; a catch is held {catch_hold}")
    assert task.groups[0] is group, "its box first, as its section is right after Timing"
    assert [(s.kind, s.share, s.structure) for s in task.specials] == [
        (kind, P(share), kind) for kind, (share, _) in KINDS.items()]


def test_the_full_task_is_crowd_at_12_every_pairing_distractors_at_full(task, tmp_path):
    """§5: "Full task": **the Crowd stage at its hardest, with all 12 discs, distractors at full and
    every pairing**. The training switch's *full task* plays it from the next trial: Crowd, its
    staircase held at 12, its condition's distractors at full, the pool holding all twelve."""
    (plan,) = task.plans.values()
    assert plan.full == FullTask("Crowd", {"pairings": 4095})
    assert task.pool.unpooled(4095) is None and len(task.pool.choices) == 12

    session, lines = _session(tmp_path, stop=6, start_block="Fade-in",
                              commands={1: [Shaping("full", JAKE)]})
    full = lines[1:]
    assert full and {line["block"] for line in full} == {"Crowd"}
    assert {line["params"]["set_size"] for line in full} == {12}
    assert {line["params"]["distractor_fraction"] for line in full} == {1.0}
    assert {line["params"]["pairings"] for line in full} == {4095}
    assert {line["drawn"]["pairings"] for line in full} == {"full"}


def test_fix_hold_is_drawn_non_aging_from_0_75_to_1_25(task, tmp_path):
    """§6: "`fix_hold`: drawn non-aging, 0.75–1.25 s, the PI's published foreperiod"
    [@westerberg2020priming], drawn afresh on a trial brought back; its start, 0.5 s, the timing
    switch's fixed side. Every trial of a session holds it its own wait in that range."""
    assert task.draws["fix_hold"] == NonAging.between(0.75, 1.25, repeat=FRESH)
    assert _param(task, "fix_hold").start == 0.5

    session, lines = _session(tmp_path, stop=30, start_block="Fade-in")
    holds = [line["params"]["fix_hold"] for line in lines]
    assert all(0.75 <= hold <= 1.25 for hold in holds) and len(set(holds)) == len(holds)
    assert {line["drawn"]["fix_hold"] for line in lines} == {"task"}


def test_every_outcome_of_every_structure_is_reached_by_the_hazard_subject(task):
    """Sim first: **each of the five structures, played by the hazard subject**, reaches every
    outcome it declares (`Census.uncovered` empty) and never hangs: the search's and the probe's
    answers and errors, each catch's correct reject, false alarm and no response. **A catch's no
    response is its bound's** (`catch_hold_limit`), which an eye held on the point never meets, so
    a catch is also played with the hold at 2.9 s -- warned, not refused (`little-time-to-answer`)
    -- by an animal whose tracker stalls often, each stall within its grace, holding the hold up
    (the graces freeze gaze, `run`), until the bound ends some trials first."""
    values = {**popout._values(task), "set_size": 6}
    for name, structure in task.structures.items():
        census = simulate(
            structure,
            Subject(seed=5, engagement=0.85, lapse=0.15,
                    hazards={Entered: 4.0, Exited: 0.5, SaccadeTo: 5.0}),
            trials=1500, frame_period=FRAME, values=values, effects=Recorded())
        assert census.hangs == 0, name
        reached = Counter(census.outcomes)
        if name in CATCHES:
            assert census.uncovered(structure) == {Outcome.NO_RESPONSE}, name
            stalled = simulate(
                structure,
                Subject(seed=5, engagement=1.0, hazards={Entered: 4.0}, stalls=30.0,
                        stall_seconds=0.008),
                trials=300, frame_period=FRAME, values={**values, "catch_hold": 2.9},
                effects=Recorded())
            assert stalled.hangs == 0, name
            reached += stalled.outcomes
        declared = {edge.to for state in structure.states for edge in state.go
                    if isinstance(edge.to, Outcome)}
        assert declared - set(reached) == set(), (name, reached)


def test_a_simulated_session_with_specials_runs_end_to_end_through_the_simulated_eye(task,
                                                                                    tmp_path):
    """§4, the path, not the piece: **a session of Crowd with each kind at 10%**, its animal the
    simulated eye with a false-alarm rate of 0.1 (`SessionSpec.false_alarm_rate`): every kind
    appears, with its outcomes -- catches held and broken, probes answered -- the staircase steps on
    normal trials alone, every line's `trial_kind` and `stepped` say so, and **wl-preproc reads the
    record back whole**, its strobed stream assembled into one trial per line, each ending on its
    outcome's marker."""
    try:
        from wl_preproc.contracts import events as their_events
        from wl_preproc.events.assemble import assemble
        from wl_preproc.events.rigruns import read_rig_runs
        from wl_preproc.events.rigtrials import read_rig_trials
    except ImportError as exc:  # pragma: no cover - exercised by the CI job
        if os.environ.get("WLX_REQUIRE_PREPROC") == "1":
            raise AssertionError(
                f"WLX_REQUIRE_PREPROC=1 but wl-preproc is not importable ({exc})") from exc
        pytest.skip("wl-preproc checkout not beside this repo")
    session, lines = _session(tmp_path, stop=220, values=dict.fromkeys(SHARES, 10),
                              false_alarm_rate=0.1)

    kinds = Counter(line["trial_kind"] for line in lines)
    assert set(kinds) == {"normal", *KINDS} and all(kinds[kind] >= 8 for kind in KINDS), kinds
    outcomes = Counter((line["trial_kind"], line["outcome"]) for line in lines)
    assert sum(outcomes[(kind, "correct_reject")] for kind in CATCHES) >= 20, outcomes
    assert sum(outcomes[(kind, "false_alarm")] for kind in CATCHES) >= 2, outcomes
    assert outcomes[("odd_one_alone", "correct")] >= 5, outcomes
    assert all(line["stepped"] is False for line in lines if line["trial_kind"] != "normal")
    assert any(line["stepped"] for line in lines if line["trial_kind"] == "normal")
    levels = [line["params"]["set_size"] for line in lines]
    for before, after, line in zip(levels, levels[1:], lines):
        if line["trial_kind"] != "normal":
            assert before == after, "a special trial moved the staircase"
    assert len(set(levels)) >= 3

    folder = session.directory.parent
    trials, runs = read_rig_trials(folder, "A"), read_rig_runs(folder, "A")
    assert (trials.problems, runs.problems) == ((), ())
    assert [(t.number, t.outcome) for t in trials.trials] == [
        (line["trial_number"], line["outcome"]) for line in lines]
    events = their_events.decode_stream([(i * 0.001, w) for i, w in enumerate(session.card.codes)])
    assembly = assemble(events)
    assert assembly.errors == []
    assert [t.trial_id for t in assembly.trials] == [line["trial_number"] for line in lines]
    for trial, line in zip(assembly.trials, lines):
        marker = their_events.Marker(session.allocation.outcomes[Outcome(line["outcome"])])
        assert trial.outcome == marker.name.removeprefix("TRIAL_").lower(), line


@pytest.mark.parametrize("go_delay", [0.0, 0.3])
def test_a_simulated_session_plays_the_delayed_version_through_the_simulated_eye(task, tmp_path,
                                                                                 go_delay):
    """The delayed version the PI asked for, the path, not the piece (the whole-build review's I2):
    **a session of Crowd at `go_delay` 0.3 plays as one at 0** -- the simulated eye holds the point
    through the delay, since leaving it there enters `early`, from which no right outcome can be
    reached (`simeye._lost`), and answers after the go -- so most trials are answered right, a
    catch is mostly held, and fixation breaks stay few. Until 2026-11-19 the eye read the delay as
    a relay it should answer, and 243 of 299 such trials were breaks."""
    _, lines = _session(tmp_path, stop=220,
                        values={**dict.fromkeys(SHARES, 10), "go_delay": go_delay},
                        false_alarm_rate=0.1)
    assert {line["params"]["go_delay"] for line in lines} == {go_delay}
    outcomes = Counter(line["outcome"] for line in lines)
    assert len(lines) >= 150, outcomes
    assert outcomes["correct"] >= 0.35 * len(lines), outcomes
    assert outcomes["correct_reject"] >= 0.12 * len(lines), outcomes
    assert outcomes["fixation_break"] <= 0.12 * len(lines), outcomes
    assert outcomes["false_alarm"] >= 1, outcomes


def test_a_session_spec_carries_the_false_alarm_rate_to_the_eye(tmp_path, monkeypatch):
    """The plan's Task 6, carried to Task 7: **a session's simulated eye takes its false-alarm rate
    from its spec** (`SessionSpec.false_alarm_rate`), 0 by default, so a simulated session can
    exercise its catches; and at 0 a session plays exactly as one that names none: a session of
    catches at 0 holds every one it plays, and the same at 0.5 breaks some."""
    from wl_xcon import taskd

    built = []
    real = taskd.Eye

    def eye(*args, **kwargs):
        made = real(*args, **kwargs)
        built.append(made.false_alarm_rate)
        return made

    monkeypatch.setattr(taskd, "Eye", eye)
    assert popout._spec(tmp_path / "spec", seed=5).false_alarm_rate == 0.0
    shares = dict.fromkeys(SHARES[:3], 100 / 3)
    _, unnamed = _session(tmp_path / "unnamed", stop=30, values=shares)
    _, zero = _session(tmp_path / "zero", stop=30, values=shares, false_alarm_rate=0.0)
    _, half = _session(tmp_path / "half", stop=30, values=shares, false_alarm_rate=0.5)

    assert built == [0.0, 0.0, 0.5]
    said = [(line["trial_kind"], line["outcome"], line["params"]["fix_hold"]) for line in unnamed]
    assert said == [(line["trial_kind"], line["outcome"], line["params"]["fix_hold"])
                    for line in zero]
    assert not [line for line in zero if line["outcome"] == "false_alarm"]
    broken = Counter(line["outcome"] for line in half)
    assert broken["false_alarm"] >= 5, broken


# --- The whole-build review's fix wave (2026-11-19) -----------------------------------------------


def test_a_share_and_a_shape_set_from_the_console_are_said_and_recorded_as_they_are(tmp_path):
    """The whole-build review's M1 and M4: **a whole setting set from the console is recorded
    whole** -- the wire carries 100 as 100.0 (`link._setting`), and the lines and the change row
    hold the integer 100, as they held 0 before it (`Session._whole`) -- and **the changes feed and
    the moments of the run say a value as the box does**: a share "0 → 100", never "0.00 →
    100.00", and a look's shape by its segment's words, "Ring → Square", never a Python repr
    (`Session._said`, `link.choice_label`)."""
    from wl_xcon.link import SetChoice, SetParameter, choice_label, choice_words

    act = _param(popout._load_task(popout.TASK_FILE), "fix_act_look")
    words = choice_words(act.choices)
    square = next(said for said, choice in words.items() if isinstance(choice, Square))
    session, lines = _session(tmp_path, stop=8, commands={2: [
        SetParameter("target_absent_percent", 100.0, JAKE),
        SetChoice(name="fix_act_look", choice=square, by=JAKE)]})

    assert session.refusals == []
    shares = [line["params"]["target_absent_percent"] for line in lines]
    assert shares[0] == 0 and shares[-1] == 100 and all(type(one) is int for one in shares), shares
    rows = {row["name"]: row for row in popout._rows(session, "parameter_changes.jsonl")}
    assert type(rows["target_absent_percent"]["now"]) is int
    said = [text for kind, _, _, text in session.controls if kind == "set"]
    assert "target_absent_percent 0 → 100, from trial 2" in said, said
    assert choice_label(square, tuple(words)) == "Square"
    assert "fix_act_look Ring → Square, from trial 2" in said, said
    assert not [text for text in said if "(" in text.partition(",")[0]], said


def test_the_fixation_points_ring_is_said_ring_and_picking_it_still_applies(tmp_path):
    """The PI, 2026-11-20, from his try-out: **"ring" everywhere, not "Annulus"**. The fixation
    point's shape segments, its summary line, the changes feed and the moments of the run say the
    hollow look "Ring" (`task.kind_words`, through `review.appearance_words`); its words, which a
    `choice` names it by, begin "Ring: "; and picking the ring for the hold look on the box still
    sends, applies and draws it -- **the record writes the look as it always has**, its class
    `Annulus`, so what wl-preproc reads is unchanged."""
    import dataclasses

    from _frames import view
    from wl_xcon import web
    from wl_xcon.link import ParamRow, SetChoice, choice_words

    hold = _param(popout._load_task(popout.TASK_FILE), "fix_look")
    words = choice_words(hold.choices)
    (ring,) = [said for said, choice in words.items() if isinstance(choice, Annulus)]
    assert ring.startswith("Ring: ") and "Annulus" not in "".join(words), list(words)
    row = ParamRow.of("fix_look", "appearance", None, None, hold.start, False,
                      choices=hold.choices, source="task", section="Stimuli/fixation point")
    segments = web._choice_segments(row, view(can_write=True))
    assert ">Ring</button>" in segments and "Annulus" not in segments, segments
    assert web._summary_value(dataclasses.replace(row, words=ring)) == "Ring"

    session, lines = _session(tmp_path, stop=8, commands={2: [
        SetChoice(name="fix_look", choice=ring, by=JAKE)]})
    assert session.refusals == []
    said = [text for kind, _, _, text in session.controls if kind == "set"]
    assert "fix_look Disc → Ring, from trial 2" in said, said
    assert [moment for _, _, moment, _ in session.moments if "Ring" in moment], session.moments
    assert not [text for text in said if "Annulus" in text], said
    (change,) = [row for row in popout._rows(session, "parameter_changes.jsonl")
                 if row["name"] == "fix_look"]
    assert change["now"]["class"] == "Annulus", change["now"]
    assert lines[-1]["params"]["fix_look"]["class"] == "Annulus", lines[-1]["params"]["fix_look"]


def test_a_starting_value_given_for_a_drawn_setting_is_said_to_do_nothing(task):
    """The whole-build review's M5 (Task 7's concern 6): a run's `--set fix_hold=...` was silently
    beaten by the task's draw. **The pre-flight's starting values item says so**, naming the
    setting and why, and passes ("warnings over refusals"); a value given for a setting nothing
    draws says nothing of it. `wlx demo` prints the item (`tests/test_demo_command.py`)."""
    from wl_xcon.preflight import DRAWN_GIVEN, PASS, values

    drawn = values(task, {"fix_hold": 0.7}, (), "training", calibration=SRGB)
    assert drawn.result == PASS
    assert f"{DRAWN_GIVEN} ('fix_hold'): the run draws it every trial" in drawn.said, drawn.said
    plain = values(task, {"fix_hold": 0.7}, (), None, calibration=SRGB)
    assert DRAWN_GIVEN in plain.said
    fixed = values(task, {"timeout": 2.5}, (), "training", calibration=SRGB)
    assert fixed.result == PASS and DRAWN_GIVEN not in fixed.said


@pytest.mark.parametrize("go_delay", [0.0, 0.25])
@pytest.mark.parametrize("structure", ["search", "target_absent"])
def test_an_eye_leaving_on_any_frame_about_the_holds_end_is_scored_by_an_edge(task, structure,
                                                                              go_delay):
    """XC-547, probed with the tracked world (the whole-build review's M6): the rig's own gaze
    world (`gaze.Tracked`), its tracker a scripted eye whose saccades its detector finds, the eye
    leaving the fixation point on each frame from 14 before the hold's end to 6 after the go, at
    `go_delay` 0 and 0.25, on the search and on a catch. **Every trial is scored by an edge**: a
    fixation break while the hold or the delay lasts, then from one frame on, the answer (the
    search's `flight`, a catch's false alarm) -- no frame between them where a departure is seen by
    neither and the trial waits out its deadline. The one-frame gap P28 described was read from
    the code; measured, there is none, and XC-547 and P28 are withdrawn."""
    trial = task.structures[structure]
    bound = {**popout._values(task), "go_delay": go_delay, "fix_hold": 0.5}
    hold, delay = round(0.5 * HZ), round(go_delay * HZ)
    answered = Outcome.CORRECT if structure == "search" else Outcome.FALSE_ALARM
    seen = []
    for frames in range(hold - 14, hold + delay + 6):
        eye = popout._Eye([popout.LOOK, ("hold_fix", frames, popout.ODD_ONE)])
        result = run_trial(trial, popout._Seen(eye, trial, bound), FRAME, values=dict(bound),
                           effects=Recorded())
        seen.append(result.outcome)
    assert set(seen) == {Outcome.FIXATION_BREAK, answered}, seen
    switched = seen.index(answered)
    assert seen[:switched] == [Outcome.FIXATION_BREAK] * switched
    assert seen[switched:] == [answered] * (len(seen) - switched)


def test_the_summary_says_shares_in_percent_a_staircase_its_level_and_the_catch_hold_its_unit(
        tmp_path):
    """The whole-build review's M8 and M9, and the catch hold's unit (the controller's ruling on
    Task 7's concern 8), on the pop-out's own rows: **the Special trials line says its shares
    with %** (since the PI's "Shorter line, no cut" of 2026-11-20, only those on, "none" at rest,
    "absent 10%" with one on; `test_the_special_trials_line_says_only_the_shares_that_are_on`), a
    share's widest "100%"; a line its staircase gives says its words, the level
    after them where the frame's staircase gives one
    (`test_a_staircases_line_follows_its_level_as_it_steps`), and its widest, the staircase's
    highest, sizes the columns (`web._widest`, I1); **and the special
    trials' sentence shows the catch hold's unit**, "a catch is held [0.50] s", where the shares
    show their own `%`."""
    import dataclasses

    from _frames import view
    from test_page_browser import _popout_own
    from wl_xcon import web

    made = _popout_own(tmp_path)
    summary = web._summary(made, view(can_write=True), False)
    assert '<span class="lv" data-now="none">none</span>' in summary, summary[:200]
    one = dataclasses.replace(made, params=tuple(
        dataclasses.replace(row, value=10) if row.name == "target_absent_percent" else row
        for row in made.params))
    assert '<span class="lv" data-now="absent 10%">absent 10%</span>' in web._summary(
        one, view(can_write=True), False)
    rows = {row.name: row for row in made.params}
    stepped = dataclasses.replace(rows["set_size"], source="staircase")
    # With no level from the frame's staircase, its words alone (the re-review's N1).
    assert web._summary_value(stepped) == "by its staircase"
    assert web._summary_value(stepped, 9) == "by its staircase · 9"
    assert web._widest(stepped) == "by its staircase · 36"
    assert web._widest(rows["target_absent_percent"]) == "100%"

    editor = web.fragments(made, view(can_write=True))["params"]
    box = editor[editor.index('data-card="Special trials"'):]
    after = box[box.index('data-param="catch_hold"'):].split("</button></span>", 1)[1]
    assert after.startswith('<span class="unit">s</span>'), after[:120]
    share = box[box.index('data-param="target_absent_percent"'):].split("</button></span>", 1)[1]
    assert not share.startswith('<span class="unit">'), share[:120]


def test_the_special_trials_line_says_only_the_shares_that_are_on(tmp_path):
    """The PI, 2026-11-20, from his try-out: **"Shorter line, no cut"**. The Special trials line
    says only the shares that are on, each in short words from its plain name -- "absent",
    "empty", "distractor alone", "disc alone", each telling it from the others -- or "none" with
    every share at 0, the catch hold left off it; a share waiting to come on says its arrow; and
    where the shares on would not fit the summary's column (the controller's ruling), how many
    kinds and their sum, "4 kinds · 400% of trials". Its title says every setting whole, the
    catch hold among them, and the columns are sized as they were (`web._line_width` of the
    group's name alone)."""
    import dataclasses
    import html

    from _frames import view
    from test_page_browser import _popout_own
    from wl_xcon import web
    from wl_xcon.actor import Box
    from wl_xcon.link import Staged

    made = _popout_own(tmp_path)

    def line(shares: dict, staged=()) -> tuple[str, str]:
        frame = dataclasses.replace(made, staged=tuple(staged), params=tuple(
            dataclasses.replace(row, value=shares[row.name]) if row.name in shares else row
            for row in made.params))
        summary = web._summary(frame, view(can_write=True), False)
        found = summary[summary.index('data-open="Special trials"'):]
        title = html.unescape(found.split('title="', 1)[1].split('"', 1)[0])
        value = html.unescape(found.split('<span class="lv"', 1)[1].split(">", 1)[1]
                              .split("</span>", 1)[0])
        return value, title

    rows = [row for row in made.params if row.unit == "percent"]
    assert web._share_words(rows) == {
        "target_absent_percent": "absent", "odd_place_empty_percent": "empty",
        "distractor_alone_percent": "distractor alone", "odd_one_alone_percent": "disc alone"}
    assert line({})[0] == "none"
    assert line({"distractor_alone_percent": 5})[0] == "distractor alone 5%"
    assert line({"target_absent_percent": 10, "odd_place_empty_percent": 5})[0] == (
        "absent 10% · empty 5%")
    value, title = line(dict.fromkeys(web._share_words(rows), 100))
    assert value == "4 kinds · 400% of trials"
    assert ("Target absent trials 100% · Odd place empty trials 100% · Distractor alone trials "
            "100% · Odd disc alone trials 100% · Catch hold 0.50 s") in title, title
    waiting = Staged("target_absent_percent", 0, 10, Box("jake"), False, cid="c-1")
    assert line({}, [waiting])[0] == "absent 0 → 10%"
    assert "0.50 s" not in line({"target_absent_percent": 10})[0]


def test_a_staircases_line_follows_its_level_as_it_steps(tmp_path):
    """The re-review's N1: a staircase's summary line said the run's start as its level ("by its
    staircase · 4") while the staircase stood at 9, its row's value never stepped. **The line takes
    the level from the frame's own staircase row** (`Telemetry.staircase`), so on a session of
    Crowd whose staircase steps, each frame's line for `set_size` says the value at the level that
    frame's staircase is at, and over the session it says more than one."""
    from _frames import view
    from wl_xcon import web
    from wl_xcon.link import Telemetry

    session, lines = _session(tmp_path, stop=60)
    frames = [frame for frame in session.link.published
              if isinstance(frame, Telemetry) and frame.staircase is not None and frame.params]
    assert frames, "no frame of the run carried its staircase"
    said = []
    for frame in frames:
        assert frame.staircase.setting == "set_size"
        (row,) = [row for row in frame.params if row.name == "set_size"]
        if row.source != "staircase":
            continue
        level = frame.staircase.levels[frame.staircase.level]
        summary = web._summary(frame, view(can_write=True), False)
        line = summary[summary.index('data-open="set_size"'):]
        line = line[:line.index("</button>")]
        assert f">by its staircase · {web._number_said(row, level)}<" in line, (level, line)
        said.append(level)
    assert len(set(said)) >= 2, said
    assert len({line["params"]["set_size"] for line in lines}) >= 2
