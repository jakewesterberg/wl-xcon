"""Several changes applied together, and a waiting change withdrawn (the console interface design's
goals 2 and 3; the PI, 2026-11-19, "Apply per box, plus Apply all" and "Yes, a withdraw button";
its plan's Task 4).

`link.ApplyMany` carries a group box's Apply or an Apply all: one act, judged together and staged
together, or refused whole, nothing staged, each change refused with its own reason or "refused
with" the one that refused it (the plan's Review Focus 2). `link.Withdraw` takes back the whole act
of one command id while it waits for the next trial, written as one `withdrawn` change row for each
setting it covered (XC-529, the shape asked of wl-preproc and built to as drafted), and is refused,
writing no row, once the act is in force ("already in force from trial N"; Review Focus 3). A reward
size is in neither (XC-527). Engine test material, run only in the simulator: no number here is a
timing claim about the rig.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import _sessions
from _rig import DIRECT
from wl_xcon import preflight, variation
from wl_xcon.actor import Box
from wl_xcon.dio import Simulated as Card
from wl_xcon.link import (
    ApplyMany, SetColor, SetForm, SetParameter, SetRange, Simulated, Telemetry, Withdraw, decode,
    encode,
)
from wl_xcon.photometry import SRGB
from wl_xcon.run import Scripted
from wl_xcon.task import FRESH, Uniform
from wl_xcon.taskd import Session, SessionSpec, _load_task
from wl_xcon.welfare import Deployment, Simulated as Pump

WALL_NOW = 1_700_000_000.0
JAKE = Box("jake")
KIM = Box("kim")
BY = {"kind": "box", "name": "jake"}
SEARCH = "tasks/visual_search.py"


class _Drained(Simulated):
    """A link that queues `script[n]` as the `n`th drain begins, so a command drained before trial
    `n - 1` applies from the next. Past `BUDGET` drains the session is one that never ends, and
    fails here by name."""

    BUDGET = 60

    def __init__(self, script):
        super().__init__()
        self.script, self.drains = dict(script), 0

    def drain(self) -> list:
        self.drains += 1
        assert self.drains <= self.BUDGET, (
            f"the session drained {self.drains} times, past the budget of {self.BUDGET}")
        for command in self.script.get(self.drains, ()):
            self.queue(command)
        return super().drain()


def _searched(tmp_path, script: dict, *, task: str = SEARCH, trials: int = 6,
              link_type: type = _Drained, **values) -> tuple[Session, _Drained]:
    """`task` (`visual_search` by default) run on simulators for `trials` trials, nobody looking,
    `script[n]` drained at the `n`th boundary, its values `_sessions.SEARCH_VALUES` under
    `values`, its looks the first of each choice."""
    loaded = _load_task(Path(task))
    looks = {p.name: p.choices[0] for p in loaded.params
             if p.name in ("target_appearance", "distractor_appearance")}
    link = link_type(script)
    spec = SessionSpec(
        task=task, allocation="tasks/allocation.py", root=tmp_path,
        session_id="2027-01-14_01", subject="A", trials=trials, frame_period=1 / 240, seed=1,
        values={**_sessions.SEARCH_VALUES, **looks, **values}, bounds=_sessions.bounds(),
        already_delivered_today=0.0, deployment=Deployment.RIG_FIXED, geometry=DIRECT,
        session_kind="training", calibration=SRGB,
    )
    session = Session(spec, card=Card(), pump=Pump(), link=link)
    session.wall_clock = lambda: WALL_NOW + session.now()
    session.left_cage(at=WALL_NOW)
    session.head_fixed(at=session.wall_now())
    session.world = lambda trial, values, index: Scripted({})
    session.run()
    return session, link


def _rows(session: Session, name: str) -> list[dict]:
    path = session.directory / name
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def _changes(session: Session) -> list[dict]:
    return _rows(session, "parameter_changes.jsonl")


def _lines(session: Session) -> list[dict]:
    return _rows(session, "trials.jsonl")


def _frames(link) -> list:
    return [frame for frame in link.published if isinstance(frame, Telemetry)]


def _staged(link) -> list:
    """Every staged row on the frames `link` was published, each once, in order."""
    found: list = []
    for frame in _frames(link):
        found += [row for row in frame.staged if row not in found]
    return found


def _refused(link, cid: str) -> list:
    """The refusals the last frame carries naming `cid`, in order."""
    return [row for row in _frames(link)[-1].refusals if row.cid == cid]


def _fed(session: Session, kind: str) -> list[str]:
    return [said for fed, _, _, said in session.controls if fed == kind]


def _apply(*changes, cid: str = "all-1", by=JAKE) -> ApplyMany:
    return ApplyMany(changes=tuple(changes), cid=cid, by=by)


def _set(name: str, value, by=JAKE) -> SetParameter:
    return SetParameter(name=name, value=value, by=by)


# --- Apply several together -----------------------------------------------------------------


def test_applied_together_they_take_effect_on_the_same_trial(tmp_path):
    """The design's goal 2 (the PI: Apply all "stages them together, on the same trial"): an apply
    of `fix_hold` and `response_deadline` stages both under its command id, and both take effect at
    one boundary -- each its own act as today (a change id, a strobe and a `sequence` each; XC-529's
    ask: Apply all adds no shape), the same `trial_number` -- the trial before running the old
    values and the trial after the new."""
    session, link = _searched(tmp_path, {
        2: [_apply(_set("fix_hold", 0.35), _set("response_deadline", 0.7), cid="all-1")]})

    assert [(row.name, row.now, row.cid, row.kind) for row in _staged(link)] == [
        ("fix_hold", 0.35, "all-1", "set"), ("response_deadline", 0.7, "all-1", "set")]
    rows = _changes(session)
    assert [(row["kind"], row["name"], row["now"]) for row in rows] == [
        ("set", "fix_hold", 0.35), ("set", "response_deadline", 0.7)]
    assert rows[0]["trial_number"] == rows[1]["trial_number"]
    assert rows[1]["change"] == rows[0]["change"] + 1
    assert rows[1]["sequence"] == rows[0]["sequence"] + 1
    lines = {line["trial_number"]: line["params"] for line in _lines(session)}
    first = rows[0]["trial_number"]
    assert (lines[first - 1]["fix_hold"], lines[first - 1]["response_deadline"]) == (0.3, 0.6)
    assert (lines[first]["fix_hold"], lines[first]["response_deadline"]) == (0.35, 0.7)
    assert not session.refusals
    for frame in _frames(link):
        assert decode(encode(frame)) == frame


def test_changes_that_work_only_together_are_judged_together(tmp_path):
    """Judged as a revert is, all at once: the target given the distractors' look is a search no
    animal can get right, and so is the distractors given the target's, each refused alone; sent
    together, a swap of the two looks, they are staged and apply on one trial."""
    task = _load_task(Path(SEARCH))
    looks = {p.name: p.choices for p in task.params}
    red, green = looks["target_appearance"][0], looks["target_appearance"][1]
    alone, alone_link = _searched(tmp_path / "alone", {
        2: [_apply(_set("target_appearance", green), cid="one-1")]})
    session, link = _searched(tmp_path / "together", {
        2: [_apply(_set("target_appearance", green), _set("distractor_appearance", red),
                   cid="both-1")]})

    (refused,) = _refused(alone_link, "one-1")
    assert "it would leave trials no animal can get right" in refused.why, refused.why
    assert not _changes(alone)
    assert not session.refusals, session.refusals
    rows = _changes(session)
    assert [row["name"] for row in rows] == ["target_appearance", "distractor_appearance"]
    assert rows[0]["trial_number"] == rows[1]["trial_number"]


def test_one_refusal_refuses_the_whole_apply(tmp_path):
    """The plan's Review Focus 2: an apply with one change the rig refuses -- `fix_hold` past its
    declared highest -- stages nothing, and every change in it is refused under its command id,
    `fix_hold` with its own reason, as its box alone would hear it, and the value refused, the
    others "refused with 'fix_hold'". A whole setting's fraction in one is refused the same way."""
    session, link = _searched(tmp_path, {
        2: [_apply(_set("fix_hold", 11.0), _set("response_deadline", 0.7), _set("set_size", 6.0),
                   cid="all-2")],
        3: [_apply(_set("response_deadline", 0.7), _set("set_size", 4.5), cid="all-3")],
        4: [_apply(_set("fix_hold", 0.35), _set("fix_hold", 0.4), cid="all-4")]})

    assert not _staged(link)
    assert not _changes(session)
    hold, deadline, size = _refused(link, "all-2")
    assert [row.name for row in (hold, deadline, size)] == [
        "fix_hold", "response_deadline", "set_size"]
    assert "past-limit" in hold.why and hold.value == 11.0, hold
    assert hold.why.endswith("; so none of the 3 applied together is staged"), hold.why
    assert deadline.why == ("'response_deadline' is refused with 'fix_hold', applied together "
                            "with it, and none of them is staged")
    assert size.why == ("'set_size' is refused with 'fix_hold', applied together with it, and "
                        "none of them is staged")
    assert (deadline.value, deadline.by) == (0.7, JAKE)
    later, fraction = _refused(link, "all-3")
    assert fraction.why.startswith("'set_size' at 4.5 is refused, and the previous value stands: "
                                   "set_size is a whole number of objects"), fraction.why
    assert later.why.startswith("'response_deadline' is refused with 'set_size'")
    first, twice = _refused(link, "all-4")
    assert twice.why.startswith("'fix_hold' is sent twice in one apply"), twice.why
    assert {line["params"]["fix_hold"] for line in _lines(session)} == {0.3}


def test_a_reward_size_is_never_applied_with_others(tmp_path):
    """XC-527 (the design: a reward size "keeps its own Apply only"): `reward_correct` in an apply
    refuses the whole, with a sentence, written to the session record as a ceiling's refusal always
    is; nothing is staged, and the reward stays at its value."""
    session, link = _searched(tmp_path, {
        2: [_apply(_set("fix_hold", 0.35), _set("reward_correct", 0.2), cid="all-4")]})

    hold, reward = _refused(link, "all-4")
    assert reward.why == ("'reward_correct' is a reward size, a welfare ceiling, which is sent "
                          "alone with its own Apply and never applied with other settings "
                          "(XC-527); so none of the 2 applied together is staged")
    assert hold.why.startswith("'fix_hold' is refused with 'reward_correct'")
    assert not _staged(link) and not _changes(session)
    assert session.spec.bounds.value("reward_correct") == 0.15
    (recorded,) = _rows(session, "refusals.jsonl")
    assert (recorded["name"], recorded["asked"]) == ("reward_correct", 0.2)


def test_a_reward_size_refused_behind_another_change_is_still_recorded(tmp_path):
    """The whole-build review's M2: a reward size in a refused apply is written to the session
    record as a ceiling's refusal whatever its place in the act -- here behind a whole count sent a
    fraction, which refuses the apply first -- and its value stays as it was."""
    session, link = _searched(tmp_path, {
        2: [_apply(_set("set_size", 2.5), _set("reward_correct", 0.2), cid="all-9")]})

    size, reward = _refused(link, "all-9")
    assert reward.why.startswith("'reward_correct' is refused with 'set_size'"), reward.why
    assert not _staged(link) and session.spec.bounds.value("reward_correct") == 0.15
    (recorded,) = _rows(session, "refusals.jsonl")
    assert (recorded["name"], recorded["asked"], recorded["why"]) == (
        "reward_correct", 0.2, reward.why)


def test_an_applys_warnings_are_carried_by_the_settings_they_name(tmp_path):
    """The controller's ruling on Task 3's concern: a raised set size that crowds the ring's
    windows warns of `set_size`, so its row carries the warning and `fix_hold`'s, applied with
    it, does not."""
    _, link = _searched(tmp_path, {
        2: [_apply(_set("set_size", 12.0), _set("fix_hold", 0.35), cid="all-5")]},
        object_window=1.6, array_eccentricity=6.0, set_size=4)

    size, hold = _staged(link)
    (warning,) = size.warnings
    assert warning.startswith("crowded-array:"), warning
    assert (hold.name, hold.cid, hold.warnings) == ("fix_hold", "all-5", ())


# --- Withdraw ----------------------------------------------------------------------------------


def test_a_waiting_change_withdrawn_never_takes_effect_and_is_recorded(tmp_path):
    """The design's goal 3: a change applied and withdrawn before the next trial never applies --
    no `set` row, no strobe, every trial at the old value -- and the withdrawal is its own act, a
    `withdrawn` row of a fresh change id in the shape asked of wl-preproc (XC-529): `was` and `now`
    what the setting holds, its `cid`, the row it would have been, who sent it, no `sequence`, and
    its line on the changes feed."""
    session, link = _searched(tmp_path, {
        2: [SetParameter(name="fix_hold", value=0.35, by=KIM, cid="box-1"),
            Withdraw(cid="box-1", by=JAKE)]})

    (row,) = _changes(session)
    del row["at"], row["at_local"]
    assert row == {
        "change": 1, "kind": "withdrawn", "name": "fix_hold", "was": 0.3, "now": 0.3, "by": BY,
        "trial_number": row["trial_number"], "run": 0, "meaning": None, "offered": [],
        "odds": None, "event_code": None, "cid": "box-1",
        "withdrawn": {"kind": "set", "now": 0.35}, "staged_by": {"kind": "box", "name": "kim"}}
    assert row["trial_number"] == 2
    assert {line["params"]["fix_hold"] for line in _lines(session)} == {0.3}
    assert not _staged(link) and not session.refusals
    (said,) = _fed(session, "withdrawn")
    assert said == "fix_hold 0.30 → 0.35 withdrawn before trial 1: it never applied"


def test_withdraw_takes_back_the_whole_act(tmp_path):
    """The design: "a group box's Apply or an Apply all is one act ... so withdrawing from any of its
    boxes withdraws all of it". One command id, three settings -- a person's draw of `fix_hold`
    among them -- all withdrawn, three rows of one change id; a change sent beside it with another
    id still applies, after it, its own act."""
    session, link = _searched(tmp_path, {
        2: [_apply(SetForm(name="fix_hold", shape="uniform", numbers={"low": 0.2, "high": 0.4},
                           by=JAKE),
                   _set("response_deadline", 0.7), _set("set_size", 6.0), cid="all-6"),
            SetParameter(name="target_hold", value=0.25, by=JAKE, cid="box-7"),
            Withdraw(cid="all-6", by=JAKE)]})

    rows = _changes(session)
    withdrawn = [row for row in rows if row["kind"] == "withdrawn"]
    assert [(row["name"], row["withdrawn"]["kind"]) for row in withdrawn] == [
        ("response_deadline", "set"), ("set_size", "set"), ("fix_hold", "form")]
    assert {row["change"] for row in withdrawn} == {1} and {row["cid"] for row in withdrawn} == {
        "all-6"}
    form = withdrawn[2]["withdrawn"]["now"]
    assert form == variation.recorded(Uniform(0.2, 0.4, repeat=FRESH)), form
    assert [(row["was"], row["now"]) for row in withdrawn] == [(0.6, 0.6), (6, 6), (0.3, 0.3)]
    (applied,) = [row for row in rows if row["kind"] == "set"]
    assert (applied["name"], applied["now"], applied["change"]) == ("target_hold", 0.25, 2)
    assert {line["params"]["response_deadline"] for line in _lines(session)} == {0.6}
    assert {line["params"]["fix_hold"] for line in _lines(session)} == {0.3}


def test_a_withdraw_pressed_while_its_change_waits_takes_it_back_in_a_running_session(tmp_path):
    """The whole-build review's C1, the path a page takes: the change drained at one boundary is on
    that boundary's frame, waiting, with its *withdraw*; the press reaches the rig in the next
    drain, before that boundary applies what waits (`Session.run`: a drain's withdrawals are read
    ahead of `_apply_staged`), so it is taken back -- the `withdrawn` row, no `set` row, every trial
    at the old value -- and the frame says the act was withdrawn (`Telemetry.withdrawals`)."""
    session, link = _searched(tmp_path, {
        2: [SetParameter(name="fix_hold", value=0.35, by=KIM, cid="box-1")],
        3: [Withdraw(cid="box-1", by=JAKE)]})

    assert [row.cid for row in _staged(link)] == ["box-1"], "the frame showed it waiting first"
    (row,) = _changes(session)
    assert row["kind"] == "withdrawn", f"the change applied before its withdrawal was read: {row}"
    assert (row["name"], row["cid"], row["withdrawn"]) == (
        "fix_hold", "box-1", {"kind": "set", "now": 0.35})
    assert {line["params"]["fix_hold"] for line in _lines(session)} == {0.3}
    assert not session.refusals and not _fed(session, "set")
    assert _frames(link)[-1].withdrawals == ("box-1",)
    # The re-review's M-c: a `wlx taskd` session back between runs lists none (`Session
    # .withdrawals`: empty between runs).
    session._after_service_run()
    assert session.withdrawals == ()


def test_a_change_drained_beside_a_withdraw_still_waits_a_boundary(tmp_path):
    """S9a §8's one-boundary window, kept by C1's fix: a change drained in the pass that reads a
    withdrawal ahead of the boundary is staged after it applies, so it waits a whole trial on the
    frame (`Telemetry.staged`) and takes effect only at the next; and a mark arriving between the
    trials with its note in that drain is stamped first, the note joined to it."""
    from wl_xcon.link import Mark

    class _Marked(_Drained):
        def drain(self) -> list:
            if self.drains + 1 == 3:
                self.marks.append(5)
            return super().drain()

    session, link = _searched(tmp_path, {
        2: [SetParameter(name="fix_hold", value=0.35, by=JAKE, cid="box-1")],
        3: [Mark(mark=5, note="restless", by=JAKE, pressed_at=None, received_at=None),
            Withdraw(cid="box-1", by=JAKE),
            SetParameter(name="target_hold", value=0.25, by=JAKE, cid="box-2")]},
        link_type=_Marked)

    waited = [frame for frame in _frames(link) if any(r.cid == "box-2" for r in frame.staged)]
    assert waited, "the change drained beside the withdrawal was on a frame, waiting"
    (applied,) = [row for row in _changes(session) if row["kind"] == "set"]
    assert (applied["name"], applied["now"]) == ("target_hold", 0.25)
    assert [row["kind"] for row in _changes(session)] == ["withdrawn", "set"]
    trials = [line["params"]["target_hold"] for line in _lines(session)]
    assert trials[:2] == [trials[0]] * 2 and 0.25 in trials and trials[0] != 0.25, trials
    stamp, note = [row for row in _rows(session, "controls.jsonl")
                   if row["kind"] in ("mark", "note")]
    assert (stamp["kind"], note["kind"], note["number"]) == ("mark", "note", stamp["number"])


def test_withdraw_after_the_boundary_is_refused_as_in_force(tmp_path):
    """The plan's Review Focus 3: a withdraw that arrives once its change has applied finds it in
    force and is refused, saying "already in force from trial N" -- the trial the feed says the
    change is from -- and writes no row; one naming an id nothing carries is refused too. The
    change drained at boundary 2 waits through trial 2's frame and applies at boundary 3, so a
    withdrawal read at boundary 4 is late."""
    session, link = _searched(tmp_path, {
        2: [SetParameter(name="fix_hold", value=0.35, by=JAKE, cid="box-1")],
        4: [Withdraw(cid="box-1", by=JAKE), Withdraw(cid="box-404", by=JAKE)]})

    (fed,) = _fed(session, "set")
    trial = int(re.search(r"from trial (\d+)", fed).group(1))
    late, unknown = (row for row in _frames(link)[-1].refusals if row.name == "withdraw")
    assert late.why == (f"the change sent as 'box-1' is not withdrawn: it is already in force from "
                        f"trial {trial}, so nothing of it waits to be taken back; change the "
                        f"setting again to move it")
    assert late.cid == "box-1"
    assert unknown.why.endswith("nothing sent with it waits for the next trial, so there is "
                                "nothing to take back")
    assert [row["kind"] for row in _changes(session)] == ["set"]
    assert not _fed(session, "withdrawn")


def test_a_withdrawal_that_would_leave_what_waits_impossible_is_refused(tmp_path):
    """What was offered after a change was judged with it: the target made a green square, then the
    distractors made red, is a search an animal can do; withdrawing the square would leave red
    among red waiting, a search no animal can get right, so the withdrawal is refused, writing no
    row, and both apply."""
    task = _load_task(Path(SEARCH))
    looks = {p.name: p.choices for p in task.params}
    red, square = looks["target_appearance"][0], looks["target_appearance"][2]
    session, link = _searched(tmp_path, {
        2: [SetParameter(name="target_appearance", value=square, by=JAKE, cid="box-1"),
            SetParameter(name="distractor_appearance", value=red, by=JAKE, cid="box-2"),
            Withdraw(cid="box-1", by=JAKE)]})

    (refused,) = _refused(link, "box-1")
    assert refused.why.startswith("the change sent as 'box-1' is not withdrawn: what still waits "
                                  "was judged with it, and without it it would leave trials no "
                                  "animal can get right"), refused.why
    assert [row["kind"] for row in _changes(session)] == ["set", "set"]
    assert [row.cid for row in _staged(link)] == ["box-1", "box-2"]


def test_a_reward_size_cannot_be_withdrawn(tmp_path):
    """XC-527 (the design: a reward size's box says "sent alone · cannot be withdrawn"): a withdraw
    naming a reward size's change is refused with a sentence, takes nothing back and writes no row;
    the reward applies at the next trial as sent."""
    session, link = _searched(tmp_path, {
        2: [SetParameter(name="reward_correct", value=0.2, by=JAKE, cid="box-r"),
            Withdraw(cid="box-r", by=JAKE)]})

    (refused,) = _refused(link, "box-r")
    assert refused.why == ("the change sent as 'box-r' is not withdrawn: 'reward_correct' is a "
                           "reward size, a welfare ceiling, which is never withdrawn (XC-527): it "
                           "applies at the next trial, and a value sent after it takes its place")
    (row,) = _changes(session)
    assert (row["kind"], row["name"], row["now"]) == ("set", "reward_correct", 0.2)
    assert session.spec.bounds.value("reward_correct") == 0.2


# --- A whole setting, judged whole wherever it is given (the controller's ruling 2) --------------


def _whole_drawn(folder: Path) -> Path:
    """`visual_search` with `fix_acquisition` declared whole and drawn uniformly from 3 to 5 s, the
    same on a repeat: engine test material, written into `folder`."""
    text = Path(SEARCH).read_text() + (
        "\n\nimport dataclasses as _dataclasses\n"
        "from wl_xcon.task import SAME as _SAME, Uniform as _Uniform\n"
        "_search = TASK.structures['search']\n"
        "_search = _dataclasses.replace(_search, params=[\n"
        "    _dataclasses.replace(p, whole=True) if p.name == 'fix_acquisition' else p\n"
        "    for p in _search.params])\n"
        "TASK = _dataclasses.replace(\n"
        "    TASK, structures={'search': _search},\n"
        "    draws={'fix_acquisition': _Uniform(3.0, 5.0, repeat=_SAME)})\n"
    )
    path = folder / "whole_drawn.py"
    folder.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def test_a_whole_settings_range_draw_and_starting_value_refuse_a_fraction(tmp_path):
    """The controller's ruling on Task 3's concern 4: a whole setting's range and a person's draw
    of one are refused where an end is a fraction, alone and in an apply of several; whole ends
    are staged. A run's starting value that is a fraction fails the pre-flight's starting values
    item, never `preflight.gate`."""
    path = _whole_drawn(tmp_path / "tasks")
    session, link = _searched(tmp_path / "run", {
        2: [SetRange(name="fix_acquisition", numbers={"low": 2.5}, by=JAKE, cid="box-1"),
            SetForm(name="fix_acquisition", shape="uniform", numbers={"low": 3.0, "high": 4.5},
                    by=JAKE, cid="box-2"),
            _apply(SetRange(name="fix_acquisition", numbers={"high": 5.5}, by=JAKE),
                   _set("fix_hold", 0.35), cid="all-3")],
        3: [SetRange(name="fix_acquisition", numbers={"low": 2.0}, by=JAKE, cid="box-4")]},
        task=str(path))

    (ranged,) = _refused(link, "box-1")
    assert ranged.why.startswith("the range of 'fix_acquisition' is not changed: "
                                 "fix_acquisition is a whole number of s, and "), ranged.why
    assert ranged.why.endswith("reaches 2.5, which is not one"), ranged.why
    (formed,) = _refused(link, "box-2")
    assert formed.why.startswith("'fix_acquisition' is not drawn as asked: fix_acquisition is a "
                                 "whole number of s"), formed.why
    assert formed.why.endswith("reaches 4.5, which is not one")
    together, hold = _refused(link, "all-3")
    assert together.why.endswith("reaches 5.5, which is not one; so none of the 2 applied "
                                 "together is staged"), together.why
    assert hold.why.startswith("'fix_hold' is refused with 'fix_acquisition'")
    assert [row.cid for row in _staged(link)] == ["box-4"]
    assert [row["kind"] for row in _changes(session)] == ["range"]

    task = _load_task(Path(SEARCH))
    item = preflight.values(task, {**_sessions.SEARCH_VALUES, "set_size": 4.5})
    assert item.result == preflight.FAIL
    assert "'set_size' is a whole number of objects, and 4.5 is not one" in item.said
    assert preflight.values(task, dict(_sessions.SEARCH_VALUES)).result == preflight.PASS
