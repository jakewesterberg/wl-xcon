"""Arrays with no target, places left empty, and the checks that read them (the pop-out revision's
Task 4; its design, `docs/superpowers/specs/2026-11-16-popout-revision-design.md` §8 and §3,
approved by the PI on 2026-11-16, "Approve both").

The design's §8: the engine refuses at load an array whose target looks like its distractors
(`Array.found_by` `"look"`, the PI's rule of 2026-10-31), and the target-absent catch is exactly
such an array, so the check must become catch-aware: it still refuses a normal trial whose target
cannot be told apart, and accepts a declared catch. An array declares it has no target with
`found_by="none"`; the odd one's place is left empty by a `Blank` among its looks, drawn as no
object and recorded `drawn: false`.

Each special kind's structure is judged for what no animal can get right (TSK-69, revised): at load
each kind, whatever its percentage (`specials="every"`); at a run's start and live, each kind whose
percentage is above 0 (`"set"`), so raising one is judged when it is set. Percentages set past 100
live are a warning on the feed (`specials-over-100`, one of `check.LAYOUT`). A bound that is a
setting is judged against a hold drawn up to it (the plan's Review Focus 5).

Engine test material, run only in the simulator: no number here is a timing claim about the rig.
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import _sessions
from _rig import DIRECT
from wl_xcon import check, screen, variation
from wl_xcon.actor import Box
from wl_xcon.check import IMPOSSIBLE, check_task, impossible, laid_out
from wl_xcon.cli import _load_task
from wl_xcon.dio import Simulated as Card
from wl_xcon.link import SetForm, SetParameter, Simulated, Stop
from wl_xcon.photometry import SRGB, Gray
from wl_xcon.record import _stimuli
from wl_xcon.run import Placed, Scripted
from wl_xcon.task import (
    FOUND_BY, FRESH, OWED, After, Array, Blank, Block, Condition, Counting, Disc, Exited, Hold,
    NonAging, ObjectWindows, On, Outcome, P, Param, Plan, SaccadeTo, Show, Special, State,
    Stimulus, Task, Trial, Window,
)
from wl_xcon.taskd import Session, SessionSpec
from wl_xcon.welfare import Deployment, Simulated as Pump

WALL_NOW = 1_700_000_000.0
SEED = 7
JAKE = Box("jake")
FRAMES = 240
SEARCH = "tasks/visual_search.py"
PLAIN = Block("session", [Condition("session", {}, target=1)])
WHY = "a percentage of trials is at most 100"

# --- A task built here, judged by the checks ------------------------------------------------------

FIX = Stimulus("fix", at=(0.0, 0.0), looks=Disc(size=0.3, color=Gray(40.0)))
GREEN = Disc(size=1.0, color=Gray(30.0))
RED = Disc(size=1.0, color=Gray(50.0))


def _ring(looks: object, among: object, *, n: object = 4, found_by: str = "look",
          radius: object = 8.0) -> Stimulus:
    return Stimulus("ring", at=(0.0, 0.0), looks=Array(n=n, radius=radius, looks=looks,
                                                       among=among, found_by=found_by))


def _search(ring: Stimulus, *, params: tuple = ()) -> Trial:
    """A search: the fixation point and the array at once, a saccade to the target right, to a
    distractor wrong."""
    return Trial(
        start="search",
        params=[Param("absent_percent", unit="percent", low=0, high=100, start=0, whole=True,
                      why=WHY), *params],
        windows=[Window("fix", at=(0.0, 0.0), radius=2.0, on="fix"),
                 ObjectWindows(of="ring", radius=1.0)],
        states=[State("search", enter=[Show(FIX), Show(ring)],
                      go=[On(SaccadeTo("ring.target"), Outcome.CORRECT),
                          On(SaccadeTo("ring.distractor"), Outcome.WRONG_TARGET),
                          On(After(1.0), Outcome.NO_RESPONSE)])],
        counting=Counting(after_stimulus=OWED, appears="search"),
    )


def _catch(ring: Stimulus, *, scored: object = None, hold: object = P("catch_hold")) -> Trial:
    """A catch: the fixation point and the array at once, the fixation held for `catch_hold` right
    (`CORRECT_REJECT`), leaving it a false alarm, bounded by `catch_hold_limit`; `scored`, an exit
    more, first."""
    go = [On(Hold("fix", hold), Outcome.CORRECT_REJECT),
          On(Exited("fix"), Outcome.FALSE_ALARM),
          On(After(P("catch_hold_limit")), Outcome.NO_RESPONSE)]
    return Trial(
        start="catch",
        params=[Param("catch_hold", unit="s", low=0.0, high=10.0, start=0.5,
                      why="a catch is held at most 10 s"),
                Param("catch_hold_limit", unit="s", low=0.0, start=3.0)],
        windows=[Window("fix", at=(0.0, 0.0), radius=2.0, on="fix"),
                 ObjectWindows(of="ring", radius=1.0)],
        states=[State("catch", enter=[Show(FIX), Show(ring)],
                      go=([scored] if scored is not None else []) + go)],
        counting=Counting(after_stimulus=OWED, appears="catch"),
    )


def _task(search: Trial, catch: Trial, *, plans: dict | None = None) -> Task:
    return Task({"search": search, "absent": catch}, default="search", plans=plans or {},
                specials=(Special("target_absent", P("absent_percent"), "absent"),))


def _codes(task: Task, code: str) -> list[str]:
    return [finding.detail for finding in check_task(task) if finding.code == code]


# --- A run on the simulators: the reference search with two catches -----------------------------


def _source(*, catch_hold: str = "0.5", extra: str = "") -> str:
    """`visual_search`'s source with a pool of two pairings and two catches, `target_absent`
    (`absent`, every object in the distractor's look) and `odd_place_empty` (`empty`, the odd one's
    place a `Blank`), each found by `"none"`, holding the fixation point `catch_hold` for a correct
    rejection, bounded by `catch_hold_limit` (3 s), their percentages `absent_percent` and
    `empty_percent` starting at 0; one plan, `train`, of one stage. Engine test material."""
    return Path(SEARCH).read_text() + (
        "\n\nimport dataclasses as _dataclasses\n"
        "from wl_xcon.scheduler import EVERY_TRIAL\n"
        "from wl_xcon.task import (Blank, Block, Condition, Plan, Pool, Special, NEITHER, "
        "NOT_DIFFICULTY)\n"
        "RED_DISC, GREEN_DISC = Disc(size=1.0, color=RED), Disc(size=1.0, color=GREEN)\n"
        f"WHY = {WHY!r}\n"
        "MORE = [Param('pairings', unit='pairings', low=1, high=7, start=1), "
        "Param('absent_percent', unit='percent', low=0, high=100, start=0, whole=True, why=WHY), "
        "Param('empty_percent', unit='percent', low=0, high=100, start=0, whole=True, why=WHY), "
        f"Param('catch_hold', unit='s', low=0.0, high=10.0, start={catch_hold}, "
        "why='a catch is held at most 10 s'), "
        "Param('catch_hold_limit', unit='s', low=0.0, start=3.0)]\n"
        "search = _dataclasses.replace(search, params=[*search.params, *MORE])\n"
        "def _catch(looks):\n"
        "    shown = _dataclasses.replace(ARRAY, looks=_dataclasses.replace(\n"
        "        ARRAY.looks, looks=looks, found_by='none'))\n"
        "    return _dataclasses.replace(search, states=[*search.states[:2], State(\n"
        "        'array_on', enter=[Show(shown), Mark(4103)], go=[\n"
        "            On(Hold('fix', P('catch_hold')), Outcome.CORRECT_REJECT,\n"
        "               do=[Reward('reward_correct')]),\n"
        "            On(Exited('fix'), Outcome.FALSE_ALARM),\n"
        "            On(After(P('catch_hold_limit')), Outcome.NO_RESPONSE)])])\n"
        "SHARE = Meaning(NOT_DIFFICULTY, NEITHER, note='how many trials are special')\n"
        "HELD = Meaning(NOT_DIFFICULTY, NEITHER, note='how long a catch is held')\n"
        "TASK = _dataclasses.replace(\n"
        "    TASK, structures={'search': search, 'absent': _catch(P('distractor_appearance')),\n"
        "                      'empty': _catch(Blank())},\n"
        "    meanings={**TASK.meanings, 'pairings': Meaning(NOT_DIFFICULTY, NEITHER, "
        "note='which pairings are drawn'), 'absent_percent': SHARE, 'empty_percent': SHARE, "
        "'catch_hold': HELD, 'catch_hold_limit': HELD},\n"
        "    pool=Pool('pairings', ((RED_DISC, GREEN_DISC), (GREEN_DISC, RED_DISC)), "
        "odd='target_appearance', distractor='distractor_appearance'),\n"
        "    specials=(Special('target_absent', P('absent_percent'), 'absent'), "
        "Special('odd_place_empty', P('empty_percent'), 'empty')),\n"
        "    plans={'train': Plan([Block('Crowd', [Condition('c', {}, target=100)], "
        "counting=EVERY_TRIAL)])})\n"
        + extra)


def _trial(values: dict) -> Scripted:
    """One trial the animal gets right on a search: it holds the fixation point, then looks at
    the target and stays."""
    held = round(values["fix_hold"] * FRAMES) + 20
    target = f"search.{values['target_index']}"
    return Scripted({SaccadeTo("search.target"): held + 10},
                    inside={**{frame: "fix" for frame in range(1, held + 1)},
                            **{frame: target for frame in range(held + 1, held + 400)}})


class _Drained(Simulated):
    """A link that queues `script[n]` as the `n`th drain begins."""

    def __init__(self, script):
        super().__init__()
        self.script, self.drains = dict(script), 0

    def drain(self) -> list:
        self.drains += 1
        assert self.drains <= 200, "the session is not ending"
        for command in self.script.get(self.drains, ()):
            self.queue(command)
        return super().drain()


def _session(folder: Path, trials: int, commands: dict, *, source: str | None = None,
             task: str = "search.py", values: dict | None = None, plan: str | None = "train"
             ) -> Session:
    """A run of `trials` on the simulators, the animal right on each, `commands` queued by drain,
    the run stopped by a person once `trials` are played."""
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / task
    if source is not None:
        path.write_text(source)
    spec = SessionSpec(
        task=str(path), allocation="tasks/allocation.py", root=folder,
        session_id="2027-01-14_01", subject="A", trials=trials, frame_period=1 / FRAMES,
        seed=SEED, values=values if values is not None else {
            **_sessions.SEARCH_VALUES, "pairings": 1, "absent_percent": 0, "empty_percent": 0},
        bounds=_sessions.bounds(), already_delivered_today=0.0,
        deployment=Deployment.RIG_FIXED, geometry=DIRECT, session_kind="training",
        calibration=SRGB, plan=plan,
    )
    session = Session(spec, card=Card(), pump=Pump(), link=_Drained(commands))
    session.wall_clock = lambda: WALL_NOW + session.now()
    session.left_cage(at=WALL_NOW)
    session.head_fixed(at=session.wall_now())

    def built(trial, values, index):
        if index == trials - 1:
            session.link.queue(Stop(by=JAKE))
        return _trial(values)

    session.world = built
    return session


def _rows(session: Session, name: str) -> list[dict]:
    path = session.directory / name
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def _fed(session: Session, kind: str) -> list[str]:
    return [said for fed, _, _, said in session.controls if fed == kind]


# --- An array with no target ----------------------------------------------------------------------


def test_a_catch_whose_distractors_all_look_alike_is_accepted_and_a_search_is_still_refused():
    """The design's §8: an array found by `"none"` has no target, so its objects may all look
    alike -- that is the catch -- and neither look check judges it, at load, at a run's start or
    live; a normal array keeps `"look"`, so a normal trial whose target looks like its distractors
    is still refused. A two-object catch whose looks are the other way round on a search of its
    block is no swap: the catch has no target to swap."""
    assert FOUND_BY == ("look", "cue", "none")
    catch = _catch(_ring(GREEN, GREEN, found_by="none"))
    task = _task(_search(_ring(RED, GREEN)), catch)
    assert _codes(task, IMPOSSIBLE) == []
    assert _codes(task, "bad-array") == []
    # Played by a condition that names it, as at a run's start and live.
    named = Block("b", [Condition("catch", {}, target=1, structure="absent")])
    assert impossible(task, [named], {"catch_hold": 0.5, "catch_hold_limit": 3.0}) == []
    assert impossible(task, [PLAIN], {"absent_percent": 10, "catch_hold": 0.5,
                                      "catch_hold_limit": 3.0}, specials="set") == []

    # A search whose target looks like its distractors is still refused, and a cued one warned.
    alike = _task(_search(_ring(GREEN, GREEN)), catch)
    (refused,) = _codes(alike, IMPOSSIBLE)
    assert "array 'ring''s target" in refused and "no object stands out" in refused
    cued = _task(_search(_ring(GREEN, GREEN, found_by="cue")), catch)
    assert _codes(cued, IMPOSSIBLE) == [] and len(_codes(cued, check.CUED)) == 1

    # Two objects, the catch's two greens beside a search's red among green: no swap.
    pair = _task(_search(_ring(RED, GREEN, n=2)),
                 _catch(_ring(GREEN, RED, n=2, found_by="none")))
    block = Block("b", [Condition("search", {}, target=1),
                        Condition("catch", {}, target=1, structure="absent")])
    assert impossible(pair, [block], {"catch_hold": 0.5, "catch_hold_limit": 3.0}) == []
    swapped = _task(_search(_ring(RED, GREEN, n=2)), _catch(_ring(GREEN, RED, n=2)))
    assert len(impossible(swapped, [block], {"catch_hold": 0.5, "catch_hold_limit": 3.0})) == 1


def test_a_catch_array_scored_by_a_saccade_to_its_target_is_refused():
    """`bad-array`, refused at load: an array with no target whose structure scores a `SaccadeTo`
    or a `Hold` on its family's target. A catch's right answer is no look at an object; one scored
    by its target's place is a search in a catch's name."""
    ring = _ring(GREEN, GREEN, found_by="none")
    assert _codes(_task(_search(_ring(RED, GREEN)), _catch(ring)), "bad-array") == []
    for guard, said in ((SaccadeTo("ring.target"), "SaccadeTo"),
                        (Hold("ring.target", 0.2), "Hold")):
        task = _task(_search(_ring(RED, GREEN)),
                     _catch(ring, scored=On(guard, Outcome.CORRECT)))
        (found,) = _codes(task, "bad-array")
        assert found.startswith(
            f"array 'ring' has no target (found_by 'none'), and state 'catch' of structure "
            f"'absent' scores {said}('ring.target')")
        assert next(f for f in check_task(task) if f.code == "bad-array").blocking
    # A distractor scored on a catch is a look at an object, which is the catch's error to say,
    # not its target's.
    task = _task(_search(_ring(RED, GREEN)),
                 _catch(ring, scored=On(SaccadeTo("ring.distractor"), Outcome.FALSE_ALARM)))
    assert _codes(task, "bad-array") == []


# --- A place left empty ---------------------------------------------------------------------------


def test_an_empty_place_draws_nothing_and_records_its_object_undrawn(tmp_path):
    """A `Blank` among an array's looks: the screen draws no item for it, its neighbors where they
    are; the record writes every object, the empty one `drawn: false`, and the array's entry its
    `found_by`. An array with no target writes `target: null` and the place an odd one would hold
    as `odd_place` (wl-preproc's answer to XC-543, 2026-11-19)."""
    empty = Array(n=4, radius=8.0, target=P("target_index"), looks=Blank(),
                  among=P("distractor_appearance"), found_by="none")
    stimulus = Stimulus("search", at=(0.0, 0.0), looks=empty)
    values = {"target_index": 2, "distractor_appearance": GREEN}
    drawn = screen.resolve({"search": stimulus}, values, Trial(start="s", states=[]), DIRECT,
                           frame_period=1 / FRAMES)
    assert [item.name for item in drawn.items] == ["search.0", "search.1", "search.3"]
    full = screen.resolve({"search": dataclasses.replace(stimulus, looks=dataclasses.replace(
        empty, looks=RED))}, values, Trial(start="s", states=[]), DIRECT, frame_period=1 / FRAMES)
    assert [item.at_left for item in drawn.items] == [
        item.at_left for item in full.items if item.name != "search.2"]

    (entry,) = _stimuli((Placed(stimulus, 3, "show", (), 0, None),), values)
    assert [each["drawn"] for each in entry["objects"]] == [True, True, False, True]
    assert (entry["drawn"], entry["found_by"], entry["target"], entry["odd_place"]) == (
        True, "none", None, 2)
    # An object whose look is a setting with no value: whether it was drawn is unknown.
    (unknown,) = _stimuli((Placed(stimulus, 3, "show", (), 0, None),), {"target_index": 2})
    assert [each["drawn"] for each in unknown["objects"]] == [None, None, False, None]


def test_an_empty_place_is_no_object_the_layout_checks_read():
    """The layout checks read no object at an empty place, as they read no `Blank` stimulus: the
    distractors of an array whose odd place is empty still touch and crowd one another, judged by
    their own size; two places, one empty, put one object on the screen, which touches nothing
    and crowds nothing; a set size sent past its highest is judged by the objects drawn."""
    def trial(n: int, radius: float, looks, among) -> Trial:
        ring = _ring(looks, among, n=n, radius=radius, found_by="none")
        return _catch(ring)

    def codes(trial: Trial) -> list[str]:
        return sorted(f.code for f in check.check(trial)
                      if f.code in ("objects-touch", "crowded-array"))

    # Twelve 1° discs on a 1.5° ring, 0.78° apart, the odd one's place empty: they touch, and
    # their 1° windows crowd, as with the odd one drawn.
    assert codes(trial(12, 1.5, Blank(), GREEN)) == ["crowded-array", "objects-touch"]
    assert codes(trial(12, 1.5, RED, GREEN)) == ["crowded-array", "objects-touch"]
    (touch,) = [f for f in check.check(trial(12, 1.5, Blank(), GREEN))
                if f.code == "objects-touch"]
    assert "closer than their sizes' mean (1°)" in touch.detail
    # Two places on a 0.3° ring, one empty: one disc drawn.
    assert codes(trial(2, 0.3, Blank(), GREEN)) == []
    assert codes(trial(2, 0.3, RED, Blank())) == []
    assert codes(trial(2, 0.3, RED, GREEN)) == ["crowded-array", "objects-touch"]
    # A set size sent past its highest: refused where the drawn objects overlap, not for one.
    assert check._overlapping_objects(_catch(_ring(Blank(), GREEN, n=P("n"), radius=0.3,
                                                   found_by="none")), {"n": 2}) == []
    assert len(check._overlapping_objects(_catch(_ring(RED, GREEN, n=P("n"), radius=0.3)),
                                          {"n": 2})) == 1
    assert len(check._overlapping_objects(_catch(_ring(Blank(), GREEN, n=P("n"), radius=0.3,
                                                       found_by="none")), {"n": 40})) == 1


# --- Each special judged --------------------------------------------------------------------------


def test_a_special_no_animal_can_answer_is_refused_at_load_whatever_its_share(tmp_path):
    """TSK-69, revised: at load each special kind's structure is judged on every condition playing
    the default structure, at the task's starts, whatever its percentage (`specials="every"`): a
    `catch_hold` past `catch_hold_limit` leaves its catches no time to answer, refused though the
    kind starts at 0, each kind named; the same catches in a plan's stage too. A hold the limit
    leaves less than a saccade's latency after is warned, likewise."""
    path = tmp_path / "search.py"
    path.write_text(_source(catch_hold="4.0"))
    task = _load_task(path)
    found = [f for f in check_task(task) if f.code == IMPOSSIBLE]
    said = [f.detail for f in found]
    assert all(f.blocking for f in found)
    for kind, structure in (("target_absent", "absent"), ("odd_place_empty", "empty")):
        for where in ("the plain run: block 'session', condition 'session'",
                      "plan 'train': block 'Crowd', condition 'c'"):
            assert (
                f"{where}: special kind {kind!r} (structure {structure!r}): state 'array_on' "
                f"ends the trial NO_RESPONSE after `catch_hold_limit`, 3 s, while its 'fix' hold "
                f"takes `catch_hold`, 4 s: the hold starts only when the gaze arrives"
            ) in "\n".join(said), (kind, where)
    assert len(found) == 4
    # Called on its own, a special's structure is judged only where asked.
    starts = {param.name: param.start for param in task.params if param.start is not None}
    assert impossible(task, [PLAIN], starts) == []
    assert len(impossible(task, [PLAIN], starts, specials="every")) == 2

    folder = tmp_path / "little"
    folder.mkdir()
    (folder / "search.py").write_text(_source(catch_hold="2.9"))
    little = [f.detail for f in check_task(_load_task(folder / "search.py"))
              if f.code == "little-time-to-answer"]
    assert any("special kind 'target_absent' (structure 'absent'): state 'array_on'" in said
               for said in little), little
    assert [f for f in check_task(_load_task(folder / "search.py")) if f.code == IMPOSSIBLE] == []


def test_raising_a_share_live_is_judged_then_and_a_special_at_0_blocks_nothing(tmp_path):
    """`Session._possible` judges with `specials="set"`: a kind at 0 is drawn on no trial, so a
    `catch_hold` past its limit is accepted while its kind is at 0; raising the kind's percentage
    then is refused, naming the kind and both settings, nothing staged, the session running on.
    The other kind, still at 0, refuses nothing; with the hold set back inside its limit, the same
    percentage is accepted."""
    session = _session(tmp_path, 5, {
        2: [SetParameter("catch_hold", 4.0, JAKE)],
        3: [SetParameter("absent_percent", 10, JAKE)],
        4: [SetParameter("catch_hold", 0.5, JAKE), SetParameter("absent_percent", 10, JAKE)],
    }, source=_source())

    session.run()

    ((name, _, why),) = session.refusals
    assert name == "absent_percent"
    assert IMPOSSIBLE in why and "'absent_percent' at 10 is refused" in why
    assert ("special kind 'target_absent' (structure 'absent'): state 'array_on' ends the trial "
            "NO_RESPONSE after `catch_hold_limit`, 3 s, while its 'fix' hold takes `catch_hold`, "
            "4 s") in why
    assert "odd_place_empty" not in why
    changes = [(row["name"], row["now"]) for row in _rows(session, "parameter_changes.jsonl")]
    assert changes == [("catch_hold", 4.0), ("catch_hold", 0.5), ("absent_percent", 10)]
    assert len(_rows(session, "trials.jsonl")) == 5


def test_a_hold_drawn_past_its_bound_is_refused_and_one_inside_it_accepted(tmp_path):
    """The plan's Review Focus 5: `fix_hold` drawn non-aging up to 12 s against a
    `fix_hold_limit` of 10 s gives some trials no time to answer: refused with a sentence naming
    both, nothing staged, the session running on. Up to 9.9 s it is accepted, and so is the 12 s
    draw once `fix_hold_limit` is raised to 13 s first. TSK-69's no-time-to-answer refusal judges a
    draw by its extremes, once the bound is a setting: nothing new is needed for it."""
    text = Path("tasks/fixation_detection.py").read_text()
    for old, new in (
        ('Param("fix_hold", unit="s", low=0.0, high=10.0, start=0.3, why=HOLD_WHY_10),',
         'Param("fix_hold", unit="s", low=0.0, high=20.0, start=0.3, why="held at most 20 s"),\n'
         '        Param("fix_hold_limit", unit="s", low=0.0, start=10.0),'),
        ("                On(After(10.0), Outcome.NO_FIXATION),",
         '                On(After(P("fix_hold_limit")), Outcome.NO_FIXATION),'),
    ):
        assert text.count(old) == 1, old
        text = text.replace(old, new)
    text += ("\n\nimport dataclasses as _dataclasses\n"
             "from wl_xcon.task import Meaning, NEITHER, NOT_DIFFICULTY\n"
             "TASK = _dataclasses.replace(TASK, meanings={**TASK.meanings, 'fix_hold_limit': "
             "Meaning(NOT_DIFFICULTY, NEITHER, note='a bound on the fixation hold')})\n")
    values = {"target_appearance": None}

    def form(longest: float) -> SetForm:
        return SetForm(name="fix_hold", shape="non_aging",
                       numbers={"shortest": 0.75, "longest": longest}, by=JAKE)

    session = _session(tmp_path / "bound", 3, {2: [form(12.0), form(9.9)]}, source=text,
                       task="detection.py", values=values, plan=None)
    session.world = lambda trial, values, index: _right(values, session, index, 3)
    session.run()
    ((name, _, why),) = session.refusals
    assert name == "fix_hold" and IMPOSSIBLE in why
    assert ("state 'hold_fix' ends the trial NO_FIXATION after `fix_hold_limit`, 10 s, while its "
            "'fix' hold takes `fix_hold`, up to 12 s") in why
    (row,) = _rows(session, "parameter_changes.jsonl")
    assert row["now"] == variation.recorded(NonAging.between(0.75, 9.9, repeat=FRESH))
    assert len(_rows(session, "trials.jsonl")) == 3

    raised = _session(tmp_path / "raised", 3, {
        2: [SetParameter("fix_hold_limit", 13.0, JAKE), form(12.0)]}, source=text,
        task="detection.py", values=values, plan=None)
    raised.world = lambda trial, values, index: _right(values, raised, index, 3)
    raised.run()
    assert raised.refusals == []
    assert [row["name"] for row in _rows(raised, "parameter_changes.jsonl")] == [
        "fix_hold_limit", "fix_hold"]


def _right(values: dict, session: Session, index: int, trials: int) -> Scripted:
    """The detection task's trial the animal gets right, the run stopped after `trials`."""
    if index == trials - 1:
        session.link.queue(Stop(by=JAKE))
    held = round(values["fix_hold"] * FRAMES) + 20
    return Scripted({SaccadeTo("target"): held + 10},
                    inside={frame: "fix" if frame <= held else "target"
                            for frame in range(1, held + 400)})


def test_shares_set_past_100_live_are_warned_on_the_feed(tmp_path):
    """The console plan's mechanism (`check.LAYOUT`, `Session._laid_out`): percentages set live
    that add past 100 are a warning when the change makes them so, accepted by who set it and said
    on the changes feed, naming the sum and each share; one that keeps them at 100 or below says
    nothing, and the load's sentence is the run's start's at the task's own starts, so it is said
    once."""
    assert "specials-over-100" in check.LAYOUT
    session = _session(tmp_path, 3, {2: [SetParameter("absent_percent", 60, JAKE),
                                         SetParameter("empty_percent", 40, JAKE)],
                                     3: [SetParameter("empty_percent", 50, JAKE)]},
                       source=_source())

    session.run()

    assert session.refusals == []
    (warned,) = [said for said in _fed(session, "warning") if "specials-over-100" in said]
    assert warned.startswith(
        "specials-over-100: the special trials' percentages add to 110 at the values set "
        "(target_absent 60 from 'absent_percent', odd_place_empty 50 from 'empty_percent'), past "
        "100: each kind is then drawn in proportion to its percentage, and no trial is normal")
    accepted = [row for row in _rows(session, "warnings.jsonl")
                if row.get("code") == "specials-over-100"]
    assert len(accepted) == 1

    task = _load_task(tmp_path / "search.py")
    at_starts = [f for f in laid_out(task, {"absent_percent": 0, "empty_percent": 0})
                 if f.code == "specials-over-100"]
    assert at_starts == []
    over = dataclasses.replace(task, structures={
        name: dataclasses.replace(trial, params=[
            dataclasses.replace(param, start=60) if param.name in ("absent_percent",
                                                                   "empty_percent") else param
            for param in trial.params]) for name, trial in task.structures.items()})
    (loaded,) = [f for f in check_task(over) if f.code == "specials-over-100"]
    (laid,) = [f for f in laid_out(over, {}) if f.code == "specials-over-100"]
    assert laid == loaded and laid.subjects == loaded.subjects
    assert "add to 120 at the task's starts (" in laid.detail
