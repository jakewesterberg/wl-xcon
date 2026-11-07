"""A staircase on a block's setting, run between trials, that a person's held value stops (the
pop-out search build's Task 3; its design,
`docs/superpowers/specs/2026-11-07-popout-search-design.md` §3.4, approved by the PI on
2026-11-07).

The PI, 2026-11-07, "Automatic within a stage": three correct in a row step harder and one error
steps easier, holding performance near 79% correct [@levitt1971transformed]; errors are TSK-33's,
a wrong item and no response failures, a trial ending before the decision moving nothing; and
"there should also be a way for the experimenter to lock the parameters": a person's live value on
the setting holds it (TSK-32: "a live value on its parameter holds it"; engine build C3's held
setting), and a hand-back resumes it at the level nearest the value held, never where it was before
the lock (the plan's Review Focus 1). The pop-out search's errors after the go -- a wrong item, a
look to empty space, leaving the target before its hold -- are failures (its design, §3.1).

Engine test material, run only in the simulator: the reference search task with a staircase on its
set size, as the pop-out search's Crowd stage has one, and the reference detection task with one on
its fixation hold.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import _sessions
from _frames import view
from _rig import DIRECT
from wl_xcon.actor import Box
from wl_xcon.check import IMPOSSIBLE, check_task
from wl_xcon.cli import _load_task
from wl_xcon.dio import Simulated as Card
from wl_xcon.link import HandBack, SetParameter, Simulated
from wl_xcon.photometry import SRGB
from wl_xcon.review import render_task
from wl_xcon.run import Scripted
from wl_xcon.scheduler import EVERY_TRIAL
from wl_xcon.task import (
    STAIRCASE_FAILURES, Block, ByCriterion, Condition, Outcome, P, SaccadeTo, Staircase, Steps,
    rule_at, staircase_verdict,
)
from wl_xcon.taskd import Session, SessionSpec
from wl_xcon.web import fragments
from wl_xcon.welfare import Deployment, Simulated as Pump

WALL_NOW = 1_700_000_000.0
SEED = 7
JAKE = Box("jake")
#: Jake as a change row writes him.
BY = {"kind": "box", "name": "jake"}
FRAMES = 240
SEARCH = "tasks/visual_search.py"
DETECTION = "tasks/fixation_detection.py"
((RED, GREEN, _),) = [p.choices for p in _load_task(Path(SEARCH)).params
                      if p.name == "target_appearance"]
#: `visual_search`'s starting values, its target red among green, **but its set size**, which its
#: own declaration gives no start (`Param("set_size", low=2, high=12)`): the staircase gives it.
SEARCHED = {**{name: value for name, value in _sessions.SEARCH_VALUES.items()
               if name != "set_size"},
            "target_appearance": RED, "distractor_appearance": GREEN}
#: A ring of 4, 6, 8, 10 and 12 objects, easiest first, as the pop-out search's Crowd stage.
CROWD = (4, 6, 8, 10, 12)


def _search_trial(kind: str, values: dict) -> Scripted:
    """One `visual_search` trial the animal plays as `kind` says: `right`, it holds the fixation
    point past its hold, looks at the target and stays (`CORRECT`); `wrong`, it looks at a
    distractor (`WRONG_TARGET`); `none`, it keeps looking at the center past the deadline
    (`NO_RESPONSE`); `break`, it looks at the target and leaves it before its hold
    (`TARGET_BREAK`); `early`, it leaves the fixation point before the array, the go
    (`FIXATION_BREAK`); `away`, it never looks at the fixation point (`NO_FIXATION`). The target is
    the array's object `target_index` places, whose window the trial loop asks by its own name."""
    held = round(values["fix_hold"] * FRAMES) + 20
    target = f"search.{values['target_index']}"
    looks = {frame: "fix" for frame in range(1, held + 1)}
    if kind == "right":
        return Scripted({SaccadeTo("search.target"): held + 10},
                        inside={**looks, **{f: target for f in range(held + 1, held + 400)}})
    if kind == "break":
        return Scripted({SaccadeTo("search.target"): held + 10},
                        inside={**looks, **{f: target for f in range(held + 1, held + 20)}})
    if kind == "wrong":
        return Scripted({SaccadeTo("search.distractor"): held + 10}, inside=looks)
    if kind == "none":
        return Scripted({}, inside=looks)
    if kind == "early":
        return Scripted({}, inside={frame: "fix" for frame in range(1, 6)})
    assert kind == "away", kind
    return Scripted({}, inside={})


def _detection_trial(kind: str, values: dict) -> Scripted:
    """One `fixation_detection` trial: `right`, it holds the fixation point past its hold, looks at
    the target and stays (`CORRECT`); `none`, it keeps looking at the center (`NO_RESPONSE`)."""
    held = round(values["fix_hold"] * FRAMES) + 20
    looks = {frame: "fix" for frame in range(1, held + 1)}
    if kind == "right":
        return Scripted({SaccadeTo("target"): held + 10},
                        inside={**looks, **{f: "target" for f in range(held + 1, held + 400)}})
    assert kind == "none", kind
    return Scripted({}, inside=looks)


def _played(script: list[str], play=_search_trial):
    """A world playing trial `n` as `script[n]` says."""
    return lambda trial, values, index: play(script[index], values)


class _Drained(Simulated):
    """A link that queues `script[n]` as the `n`th drain begins: the loop drains once before each
    trial, so a command drained before trial `n` applies from trial `n + 1`, counted from 0."""

    def __init__(self, script):
        super().__init__()
        self.script, self.drains = dict(script), 0

    def drain(self) -> list:
        self.drains += 1
        assert self.drains <= 100, "the session is not ending"
        for command in self.script.get(self.drains, ()):
            self.queue(command)
        return super().drain()


def _session(tmp_path, blocks, script, *, task=SEARCH, values=None, link=None,
             play=_search_trial) -> Session:
    """A session of `task` playing `blocks` on the simulators, its animal playing `script`, its
    wall following its frames from `WALL_NOW`, the animal out of its cage and its head fixed."""
    spec = SessionSpec(
        task=str(task), allocation="tasks/allocation.py", root=tmp_path,
        session_id="2027-01-14_01", subject="A", trials=len(script), frame_period=1 / FRAMES,
        seed=SEED, values=dict(SEARCHED if values is None else values),
        bounds=_sessions.bounds(), already_delivered_today=0.0,
        deployment=Deployment.RIG_FIXED, geometry=DIRECT, session_kind="training",
        calibration=SRGB, blocks=blocks,
    )
    session = Session(spec, card=Card(), pump=Pump(),
                      link=link if link is not None else Simulated())
    session.wall_clock = lambda: WALL_NOW + session.now()
    session.left_cage(at=WALL_NOW)
    session.head_fixed(at=session.wall_now())
    session.world = _played(script, play)
    return session


def _block(staircase: Staircase, script: list[str], name: str = "crowd") -> Block:
    """A block of `len(script)` trials, every one paying its condition (`EVERY_TRIAL`), so the run
    is as long as the script, with `staircase`."""
    return Block(name, [Condition("c", {}, target=len(script))], counting=EVERY_TRIAL,
                 staircase=staircase)


def _rows(session: Session, name: str) -> list[dict]:
    path = session.directory / name
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def _lines(session: Session) -> list[dict]:
    return _rows(session, "trials.jsonl")


def _sizes(session: Session) -> list:
    return [line["params"].get("set_size") for line in _lines(session)]


def test_three_correct_step_harder_one_error_easier(tmp_path):
    """The PI's rule (2026-11-07): three right in a row step one level harder, one failure one level
    easier, each trial's level given between trials. A failure is a wrong item, no response, or
    leaving the target before its hold (the pop-out search's errors after the go, its design §3.1);
    a step harder needs three right since the last step, so two right and a failure step easier.
    With no start given and none in the run's values, it starts at the easiest."""
    script = (["right"] * 6 + ["wrong"] + ["right", "right", "none"] + ["right"] * 3 + ["break"]
              + ["right"])
    session = _session(tmp_path, [_block(Staircase("set_size", CROWD), script)], script)

    session.run()

    assert [line["outcome"] for line in _lines(session)] == (
        ["correct"] * 6 + ["wrong_target", "correct", "correct", "no_response"] + ["correct"] * 3
        + ["target_break", "correct"])
    assert _sizes(session) == [4, 4, 4, 6, 6, 6, 8, 6, 6, 6, 4, 4, 4, 6, 4]


def test_an_early_saccade_moves_nothing(tmp_path):
    """TSK-33: "trials ending before the decision are ignored" -- an early saccade, leaving the
    fixation point before the go (`FIXATION_BREAK`), and no fixation (`NO_FIXATION`) move nothing:
    they neither count toward a step harder nor break the run of right answers toward one, and
    they step nothing easier."""
    script = ["right", "right", "early", "right", "right", "away", "right", "right", "early",
              "wrong", "right"]
    session = _session(tmp_path, [_block(Staircase("set_size", CROWD), script)], script)

    session.run()

    assert [line["outcome"] for line in _lines(session)] == [
        "correct", "correct", "fixation_break", "correct", "correct", "no_fixation", "correct",
        "correct", "fixation_break", "wrong_target", "correct"]
    assert _sizes(session) == [4, 4, 4, 4, 6, 6, 6, 6, 8, 8, 6]


def test_a_held_value_stops_the_staircase_and_a_hand_back_resumes_from_it(tmp_path):
    """The plan's Review Focus 1: a person's value on the staircase's setting holds it (TSK-32;
    engine build C3's held setting), its trials taking that value, marked `live` and not drawn by
    the staircase, which does not move however they end; a hand-back mid-stage resumes it at the
    level nearest the value held, its run of right answers started again -- never where it was
    before the lock. The value's row writes no `was` (no single value was held before it: the
    staircase gave each trial its own), and the hand-back's goes to the draw, `now` null, as a
    draw's does (`to` is one of the words told to wl-preproc; each trial's line names the
    staircase)."""
    levels = (4, 5, 8, 10, 12)
    script = ["right"] * 14
    link = _Drained({7: [SetParameter(name="set_size", value=6, by=JAKE)],
                     10: [HandBack(name="set_size", by=JAKE)]})
    session = _session(tmp_path, [_block(Staircase("set_size", levels), script)], script,
                       values={**SEARCHED, "set_size": 4}, link=link)

    session.run()

    assert session.refusals == []
    lines = _lines(session)
    assert _sizes(session) == [4, 4, 4, 5, 5, 5, 8, 6, 6, 6, 5, 5, 5, 8]
    assert [line["drawn"] for line in lines] == (
        [{"set_size": "staircase"}] * 7 + [{}] * 3 + [{"set_size": "staircase"}] * 4)
    assert [line["live"] for line in lines] == [[]] * 7 + [["set_size"]] * 3 + [[]] * 4
    held, handed = _rows(session, "parameter_changes.jsonl")
    assert (held["kind"], held["name"], held["was"], held["now"], held["trial_number"]) == (
        "set", "set_size", None, 6, 8)
    assert (handed["kind"], handed["name"], handed["was"], handed["now"], handed["to"],
            handed["trial_number"]) == ("hand_back", "set_size", 6, None, "draw", 11)


def test_the_trial_line_marks_the_setting_drawn_by_the_staircase(tmp_path):
    """wl-preproc's answer of 2026-11-07 (`docs/pending-wl-preproc-amendments.md`): no new key on
    a trial line; the staircase's value travels in `params` as every value does, its setting
    marked `drawn` `"staircase"`. While a run goes, the console's card of the setting says where
    its value comes from, the staircase, in the value's place, with a field to set one value over
    it: the lock (telemetry schema 19's `source`)."""
    script = ["right"] * 4
    session = _session(tmp_path, [_block(Staircase("set_size", CROWD), script)], script)

    session.run()

    lines = _lines(session)
    assert [(line["params"]["set_size"], line["drawn"], line["live"]) for line in lines] == (
        [(4, {"set_size": "staircase"}, [])] * 3 + [(6, {"set_size": "staircase"}, [])])
    running = [frame for frame in session.link.published if frame.phase == "running"]
    assert running and all(row.source == "staircase" for frame in running
                           for row in frame.params if row.name == "set_size")
    card = fragments(running[-1], view())["params"].split('<div class="param')
    (size,) = [part for part in card if "<span>set_size</span>" in part]
    assert '<span class="pv">set each trial by its staircase</span>' in size
    assert 'placeholder="a value over its staircase"' in size


def test_it_stops_at_its_ends(tmp_path):
    """It never steps past either end (the PI's rule, 2026-11-07): three more right at its hardest
    level leave it there, and a failure at its easiest leaves it there. It starts at `start`, an
    index into its levels, where one is given."""
    script = ["right"] * 3 + ["wrong"] * 3 + ["right"]
    session = _session(tmp_path, [_block(Staircase("set_size", (4, 6, 8), start=2), script)],
                       script)

    session.run()

    assert _sizes(session) == [8, 8, 8, 8, 6, 4, 4]


def test_with_no_start_it_starts_at_the_level_nearest_the_runs_value(tmp_path):
    """With no `start`, a block's staircase starts at the level nearest the run's own value of its
    setting (the task's start under the run's), the easier of two as near: a run given 7 objects
    on a staircase of 4, 6, 8 and 10 starts at 6, and three right step it to 8."""
    script = ["right"] * 4
    session = _session(tmp_path, [_block(Staircase("set_size", (4, 6, 8, 10)), script)], script,
                       values={**SEARCHED, "set_size": 7})

    session.run()

    assert _sizes(session) == [6, 6, 6, 8]


def test_each_block_starts_its_own_staircase_afresh(tmp_path):
    """A block's staircase starts afresh as the block opens, where its `start` says, as a stage a
    plan moves on to or back to is started fresh (TSK-57): a later block with the same staircase
    does not take up the level an earlier one reached, and a block with none between them gives
    the setting as its conditions do, the staircase's not marked."""
    staircase = Staircase("set_size", (4, 6, 8))
    script = ["right"] * 7
    blocks = [_block(staircase, script[:4], "a"),
              Block("b", [Condition("c", {"set_size": 5}, target=1)], counting=EVERY_TRIAL),
              _block(staircase, script[5:], "c")]
    session = _session(tmp_path, blocks, script)

    session.run()

    lines = _lines(session)
    assert [(line["block"], line["params"]["set_size"], line["drawn"]) for line in lines] == (
        [("a", size, {"set_size": "staircase"}) for size in (4, 4, 4, 6)] + [("b", 5, {})]
        + [("c", 4, {"set_size": "staircase"})] * 2)


def test_a_value_held_over_the_staircase_is_judged_eased_against_its_level(tmp_path):
    """Engine build C3's eased trials (the PI, Q8: a trial a person's change made easier does not
    count toward moving up): a value held over the staircase is judged against the level the
    staircase stopped at, not the run's own value, and trials played at a held value leave it
    there. Here the fixation hold steps up from the run's 0.1 s to 0.3 s; a person holds 0.2 s,
    easier than the staircase's 0.3 s though harder than the run's 0.1 s, so those trials are
    eased; then 0.35 s, harder, which is not, however many are right: right trials played at a held
    value do not step the staircase on to 0.4 s, against which 0.35 s would be easier."""
    script = ["right"] * 12
    link = _Drained({7: [SetParameter(name="fix_hold", value=0.2, by=JAKE)],
                     9: [SetParameter(name="fix_hold", value=0.35, by=JAKE)]})
    session = _session(tmp_path, [_block(Staircase("fix_hold", (0.1, 0.2, 0.3, 0.4)), script)],
                       script, task=DETECTION, values={"target_appearance": None, "fix_hold": 0.1},
                       link=link, play=_detection_trial)

    session.run()

    assert session.refusals == []
    lines = _lines(session)
    assert [line["params"]["fix_hold"] for line in lines] == (
        [0.1] * 3 + [0.2] * 3 + [0.3, 0.2, 0.2, 0.35, 0.35, 0.35])
    assert [line["eased"] for line in lines] == [[]] * 7 + [["fix_hold"]] * 2 + [[]] * 3


def test_each_outcome_is_a_success_a_failure_or_nothing():
    """TSK-33's classes, outcome by outcome (`task.staircase_verdict`): a right answer
    (`task.RIGHT`) is a success; every other answer, no response, and the pop-out search's two
    errors after the go that are no answer to the engine -- a look to empty space (`ABORT`) and
    leaving the target before its hold (`TARGET_BREAK`) -- are failures; everything else moves
    nothing -- a fixation break (an early saccade), no fixation, the other breaks, the rig's two
    and a hang -- and so does any trial whose stimulus never appeared."""
    failures = {Outcome.WRONG_TARGET, Outcome.EARLY_RESPONSE, Outcome.LATE_RESPONSE,
                Outcome.EARLY_ERROR, Outcome.LATE_ERROR, Outcome.FALSE_ALARM,
                Outcome.NO_RESPONSE, Outcome.TARGET_BREAK, Outcome.ABORT}

    assert STAIRCASE_FAILURES == failures
    assert {outcome: staircase_verdict(outcome, True) for outcome in Outcome} == {
        **{outcome: None for outcome in Outcome}, Outcome.CORRECT: True,
        Outcome.CORRECT_REJECT: True, **{outcome: False for outcome in failures}}
    assert {staircase_verdict(outcome, False) for outcome in Outcome} == {None}
    assert staircase_verdict(None, True) is None


def _planned(folder: Path, base: str, plans: str, name: str, *edits: tuple[str, str]) -> Path:
    """The reference task at `base` with `plans`, Python source for its plans dict, free to name
    the plan vocabulary, `Staircase`, `Uniform` and `FRESH`, and each `(old, new)` of `edits` made,
    each `old` found once; written into `folder` as `NAME.py`. Engine test material."""
    text = Path(base).read_text()
    for old, new in edits:
        assert text.count(old) == 1, old
        text = text.replace(old, new)
    path = folder / f"{name}.py"
    path.write_text(text + (
        "\n\nimport dataclasses as _dataclasses\n"
        "from wl_xcon.task import (FRESH, Block, ByCriterion, Condition, P, Plan, Staircase, "
        "Steps, Uniform)\n"
        f"TASK = _dataclasses.replace(TASK, plans={plans})\n"))
    return path


def _refused(path: Path) -> dict[str, str]:
    """Each `bad-staircase` finding of the task at `path`, by the plan its sentence names."""
    found = [f for f in check_task(_load_task(path)) if f.code == "bad-staircase"]
    assert all(f.blocking for f in found), found
    return {f.detail.split("'")[1]: f.detail for f in found}


def test_a_staircase_on_an_undeclared_setting_is_refused_at_load(tmp_path):
    """Refused at load, `bad-staircase`, each sentence saying which plan, block and setting and
    what to write, only what a staircase cannot run or the record could not be read for: a setting
    the task does not declare; a bounded setting, a reward size, by name (welfare: the task names
    how reward is configured, never how much); a setting of choices, since a staircase steps among
    numbers; a level outside the setting's declared range; a level that is no whole number where an
    array reads the setting as one; a setting its block draws, or its conditions give ("never
    both", as for draws); and a block's staircase that is no `Staircase`. One the task can run is
    not refused."""
    block = 'Block("b", [Condition("c", {}, target=5)], staircase=Staircase('
    plans = "{" + ", ".join([
        f'"fine": Plan([{block}"fix_hold", (0.1, 0.2, 0.3)))])',
        f'"undeclared": Plan([{block}"fix_holdd", (0.1, 0.2)))])',
        f'"bounded": Plan([{block}"reward_correct", (0.1, 0.2)))])',
        f'"choices": Plan([{block}"target_appearance", (1.0, 2.0)))])',
        f'"outside": Plan([{block}"fix_hold", (0.01, 0.2, 2.5)))])',
        '"drawn": Plan([Block("b", [Condition("c", {}, target=5)], '
        'draws={"fix_hold": Uniform(0.2, 0.4, repeat=FRESH)}, '
        'staircase=Staircase("fix_hold", (0.1, 0.2)))])',
        '"given": Plan([Block("b", [Condition("c", {"fix_hold": 0.3}, target=5), '
        'Condition("d", {}, target=5)], staircase=Staircase("fix_hold", (0.1, 0.2)))])',
        '"other": Plan([Block("b", [Condition("c", {}, target=5)], staircase="fix_hold")])',
    ]) + "}"
    whole = ('{"halves": Plan([Block("b", [Condition("c", {}, target=5)], '
             'staircase=Staircase("set_size", (4, 4.5, 6)))])}')

    found = {**_refused(_planned(tmp_path, DETECTION, plans, "detection")),
             **_refused(_planned(tmp_path, SEARCH, whole, "search"))}

    assert found == {
        "undeclared": "plan 'undeclared': block 'b' has a staircase on 'fix_holdd', which is no "
                      "setting the task declares; a staircase steps one of the task's own settings",
        "bounded": "plan 'bounded': block 'b' has a staircase on 'reward_correct', a bounded "
                   "setting, which the subject's bounded config sets and no staircase steps "
                   "(welfare); take it out",
        "choices": "plan 'choices': block 'b' has a staircase on 'target_appearance', a setting "
                   "of choices, and a staircase steps among numbers; declare it with a range, or "
                   "vary it by conditions",
        "outside": "plan 'outside': block 'b''s staircase on 'fix_hold' has the levels 0.01, 2.5 "
                   "outside the range the setting declares, 0.05 to 2.0 s; give it levels inside "
                   "it",
        "drawn": "plan 'drawn': block 'b' draws 'fix_hold' and its staircase steps it: a setting "
                 "is drawn or stepped by a staircase, never both; take it out of the block's "
                 "draws, or the staircase off it",
        "given": "plan 'given': block 'b''s condition(s) 'c' give 'fix_hold' and its staircase "
                 "steps it: a setting is given by conditions or stepped by a staircase, never "
                 "both; take it out of those conditions, or the staircase off it",
        "other": "plan 'other': block 'b''s staircase is 'fix_hold', and a block's staircase is "
                 "a Staircase, or None",
        "halves": "plan 'halves': block 'b''s staircase on 'set_size' has the level 4.5, and an "
                  "array reads 'set_size' as a whole number, its set size or its target's place, "
                  "so the record would write 4.5 while 4 objects show; give it whole numbers",
    }


@pytest.mark.parametrize("levels, more, said", [
    ((), {}, "a staircase has at least one level, and this one has none"),
    ([0.1, 0.2], {}, "a staircase's levels are a tuple, easiest first, not a list"),
    ((0.1, float("nan")), {}, "a staircase's levels are finite numbers, and nan is not one"),
    ((0.1, True), {}, "a staircase's levels are finite numbers, and True is not one"),
    ((0.1, "0.2"), {}, "a staircase's levels are finite numbers, and '0.2' is not one"),
    ((0.1, 0.2), {"down": 0}, "a staircase's down is a whole number from 1, not 0"),
    ((0.1, 0.2), {"up": 1.5}, "a staircase's up is a whole number from 1, not 1.5"),
    ((0.1, 0.2), {"down": True}, "a staircase's down is a whole number from 1, not True"),
    ((0.1, 0.2), {"start": 2}, "a staircase's start is the index of one of its 2 levels, from 0, "
                               "or None, not 2"),
    ((0.1, 0.2), {"start": -1}, "a staircase's start is the index of one of its 2 levels, from 0, "
                                "or None, not -1"),
])
def test_a_staircase_that_cannot_step_is_refused_as_it_is_built(levels, more, said):
    """A staircase whose shape cannot step is refused as it is built, as a setting's declaration
    is (`task.Param`), with the sentence: no levels, levels that are not a tuple of finite numbers,
    a `down` or an `up` that is no whole number from 1, and a `start` that is no index of its
    levels."""
    with pytest.raises(ValueError) as refused:
        Staircase("fix_hold", levels, **more)

    assert str(refused.value) == f"setting 'fix_hold': {said}"


def test_a_staircase_level_no_animal_can_get_right_is_refused_at_load(tmp_path):
    """Engine build C3's spec §9 (the PI, 2026-10-30, Q10): the trials no animal can get right are
    refused at load, judged on every value a setting can hold in each block, so on each of a
    staircase's levels, which the staircase gives its setting instead of the task's start. Here
    the target hold steps up to 0.8 s past the 0.6 s the response deadline leaves to answer in
    (the reference detection task's timeout in `verify` made to read the deadline, XC-343's first
    combination); stopping at 0.4 s is not refused."""
    block = 'Block("b", [Condition("c", {}, target=5)], staircase=Staircase('
    path = _planned(
        tmp_path, DETECTION,
        f'{{"long": Plan([{block}"target_hold", (0.2, 0.4, 0.8)))]), '
        f'"short": Plan([{block}"target_hold", (0.2, 0.4)))])}}',
        "deadline",
        ("                On(After(3.0), Outcome.NO_RESPONSE),",
         '                On(After(P("response_deadline")), Outcome.NO_RESPONSE),'))

    impossible = [f for f in check_task(_load_task(path)) if f.code == IMPOSSIBLE]

    assert len(impossible) == 1, impossible
    assert impossible[0].detail.startswith("plan 'long': block 'b', condition 'c': ")
    assert "target_hold" in impossible[0].detail


def test_the_review_report_shows_each_blocks_staircase(tmp_path):
    """The review report (`wlx review`; engine spec §18.1) shows each block's staircase beside its
    draws: the setting it steps, its levels easiest first in the setting's unit, the runs of right
    answers and of failures that step it, and where it starts -- so a reviewer reads the staircase
    a task declares, since tasks are written by a model and read by people."""
    plans = ('{"train": Plan([Block("crowd", [Condition("c", {}, target=5)], '
             'staircase=Staircase("set_size", (4, 6, 8))), '
             'Block("held", [Condition("c", {}, target=5)], '
             'staircase=Staircase("set_size", (4, 8, 12), down=2, start=1)), '
             'Block("plain", [Condition("c", {}, target=5)])])}')

    report = render_task(_load_task(_planned(tmp_path, SEARCH, plans, "search")))

    assert ("| Block | Steps | Levels, easiest first | A level harder after | A level easier after "
            "| Starts at |") in report
    assert ("| crowd | set_size | 4, 6, 8 objects | 3 right in a row | 1 failed in a row | the "
            "level nearest the run's value, else the easiest |") in report
    assert ("| held | set_size | 4, 8, 12 objects | 2 right in a row | 1 failed in a row | 8 |"
            in report)
    assert "| plain | set_size" not in report


# --- Every number a setting (the pop-out search build's fix round; the PI, 2026-11-07) ----------


def test_steps_make_a_staircases_levels_by_a_step_a_setting_gives():
    """"i mean, everything should be adjustable in the console, no?" (the PI, 2026-11-07): a
    staircase's levels by a step (`Steps`), from its start, the easiest, toward its end, the
    hardest, which is always the last level whether or not a step lands on it; rising or falling;
    tenths as written; whole numbers from a whole start, end and step, and on a setting an array
    reads as one (`whole`) each the nearest, repeats dropped. Its counts may be settings too, each
    read as the nearest whole number from 1 (`Staircase.at`)."""
    tenths = Steps(0.1, 1.0, P("step"))
    assert tenths.levels(0.1) == (0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0)
    assert tenths.levels(0.3) == (0.1, 0.4, 0.7, 1.0)
    assert tenths.levels(0.25) == (0.1, 0.35, 0.6, 0.85, 1.0)
    assert Steps(1.0, 0.2, 0.4).levels(0.4) == (1.0, 0.6, 0.2)
    crowd = Steps(4, 12, P("step"))
    assert crowd.levels(1.0) == (4, 5, 6, 7, 8, 9, 10, 11, 12)
    assert all(isinstance(level, int) for level in crowd.levels(1.0))
    assert crowd.levels(1.5, whole=True) == (4, 6, 7, 9, 10, 12)
    for bad in (0, -1.0, float("nan"), "1"):
        with pytest.raises(ValueError, match="positive number"):
            crowd.levels(bad)
    with pytest.raises(ValueError, match="more than the 1000"):
        tenths.levels(1e-6)
    with pytest.raises(ValueError, match="positive number or a setting"):
        Steps(0.1, 1.0, 0)

    declared = Staircase("fix_hold", tenths, down=P("down"), up=P("up"))
    assert declared.settings == ("down", "up", "step")
    now = declared.at({"step": 0.3, "down": 2.4, "up": 0.0})
    assert (now.levels, now.down, now.up) == ((0.1, 0.4, 0.7, 1.0), 2, 1)
    assert Staircase("fix_hold", (0.1, 0.2)).at({}) == Staircase("fix_hold", (0.1, 0.2))
    with pytest.raises(ValueError, match="setting 'step', which has no number here"):
        declared.at({"down": 3, "up": 1})


def test_a_step_changed_live_puts_the_staircase_at_the_level_nearest_its_value():
    """`taskd._Climb.restep`, between trials: a count changed takes effect at the next step, the
    count so far kept; a step changed re-derives the levels and puts the staircase at the level
    nearest the value it was at, its count kept; a value that makes no staircase leaves it as it
    was."""
    from wl_xcon.taskd import _Climb

    climb = _Climb.started(Staircase("fix_hold", Steps(0.1, 1.0, P("step")), down=P("down")),
                           {"step": 0.1, "down": 3}, lambda staircase: staircase.nearest(0.5))
    assert (climb.value, climb.level) == (0.5, 4)
    climb.right = 2
    climb.restep({"step": 0.3, "down": 3})
    assert (climb.staircase.levels, climb.value, climb.right) == ((0.1, 0.4, 0.7, 1.0), 0.4, 2)
    climb.restep({"step": 0.3, "down": 2})
    assert (climb.staircase.down, climb.value, climb.right) == (2, 0.4, 2)
    climb.restep({"step": 0.0, "down": 2})
    assert climb.staircase.levels == (0.1, 0.4, 0.7, 1.0)
    fixed = _Climb.started(Staircase("fix_hold", (0.1, 0.2)), {}, lambda staircase: 0)
    assert fixed.declared is None


#: Two settings a staircase's counts and steps and a rule's numbers can come from, for the load
#: checks below: a count from 1 to 5, a step from 0.05 to 0.5, a share and a window of answers.
_NAMED = (('        Param("fix_hold", unit="s", low=0.05, high=2.0, start=0.3),',
           '        Param("fix_hold", unit="s", low=0.05, high=2.0, start=0.3),\n'
           '        Param("count", unit="answers", low=1, high=5, start=3),\n'
           '        Param("step", unit="s", low=0.05, high=0.5, start=0.1),\n'
           '        Param("share", unit="fraction", low=0.5, high=1.0, start=0.8),\n'
           '        Param("window", unit="answers", low=5, high=50, start=10),'),)


def test_a_staircases_settings_are_checked_at_load(tmp_path):
    """A staircase whose counts or step a setting gives (the fix round) is refused at load,
    `bad-staircase`, where that setting is none of the task's own with a range of numbers, a
    bounded one, or the setting it steps; where a count's range reaches below 1 or a step's to 0;
    and where any level its steps can make falls outside its setting's range. One the task can run
    is not refused."""
    block = 'Block("b", [Condition("c", {}, target=5)], staircase=Staircase('
    plans = "{" + ", ".join([
        f'"fine": Plan([{block}"fix_hold", Steps(0.1, 1.0, P("step")), down=P("count"), '
        f'up=P("count")))])',
        f'"undeclared": Plan([{block}"fix_hold", (0.1, 0.2), down=P("nope")))])',
        f'"own": Plan([{block}"fix_hold", Steps(0.1, 1.0, P("fix_hold"))))])',
        f'"bounded": Plan([{block}"fix_hold", (0.1, 0.2), up=P("reward_correct")))])',
        f'"zero": Plan([{block}"fix_hold", Steps(0.1, 1.0, P("target_luminance"))))])',
        f'"below": Plan([{block}"fix_hold", (0.1, 0.2), down=P("fix_window")))])',
        f'"outside": Plan([{block}"fix_hold", Steps(0.1, 2.5, P("step"))))])',
    ]) + "}"

    found = _refused(_planned(tmp_path, DETECTION, plans, "detection", *_NAMED))

    assert set(found) == {"undeclared", "own", "bounded", "zero", "below", "outside"}
    assert "takes its down from 'nope', which is no setting of numbers with a range" in (
        found["undeclared"])
    assert "takes its step from 'fix_hold', which is the setting it steps" in found["own"]
    assert "takes its up from 'reward_correct', which is a bounded setting" in found["bounded"]
    assert "takes its step from 'target_luminance', whose range reaches 0" in found["zero"]
    assert "takes its down from 'fix_window', whose range reaches 0.5" in found["below"]
    assert "outside the range the setting declares, 0.05 to 2.0 s" in found["outside"]


def test_a_rules_numbers_may_be_settings_checked_at_load_and_read_live(tmp_path):
    """A stage's criterion and a plan's fall-back may each name settings (the fix round: "Let
    `Block(criterion=...)` and `ByCriterion(fall_back=...)` take `P(...)` references, read at each
    judgment from the run's live values"): refused at load, `bad-plan`, where a setting named is
    none of the task's own with a range of numbers, a proportion's range leaves (0, 1] or a
    window's reaches below 1. `task.rule_at` reads one at the run's values, a window the nearest
    whole number from 1."""
    rule = lambda criterion: ('Plan([Block("b", [Condition("c", {}, target=5)], '
                              f'criterion={criterion})])')
    plans = "{" + ", ".join([
        f'"fine": {rule("(P(\'share\'), P(\'window\'))")}',
        f'"undeclared": {rule("(P(\'nope\'), 10)")}',
        f'"brighter": {rule("(P(\'target_luminance\'), 10)")}',
        f'"narrow": {rule("(0.8, P(\'fix_window\'))")}',
        '"back": Plan([Block("b", [Condition("c", {}, target=5)]), '
        'Block("d", [Condition("c", {}, target=5)])], '
        'order=ByCriterion(fall_back=(P("share"), P("nope"))))',
    ]) + "}"
    path = _planned(tmp_path, DETECTION, plans, "detection", *_NAMED)

    refused = {f.detail.split("'")[1]: f.detail for f in check_task(_load_task(path))
               if f.code == "bad-plan"}

    assert set(refused) == {"undeclared", "brighter", "narrow", "back"}
    assert all("each a number or a setting the task declares whose range holds only such "
               "values" in detail for detail in refused.values())
    assert rule_at((P("share"), P("window")), {"share": 0.7, "window": 19.6}) == (0.7, 20)
    assert rule_at((0.8, P("window")), {"window": 0.2}) == (0.8, 1)
    assert rule_at((0.8, 50), {}) == (0.8, 50) and rule_at(None, {}) is None
    with pytest.raises(ValueError, match="setting 'share', which has no number here"):
        rule_at((P("share"), 50), {})

