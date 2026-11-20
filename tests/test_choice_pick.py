"""One of a setting's declared choices picked on its box by its words (the pop-out revision's design
§2: each of the fixation point's looks has a shape that is "a setting on the console"; its plan's
Task 5b).

A live pick of a choice went only through `link.SetColor`, which names a color-set light by its set
and its hue; a look's shape -- a disc, a ring, a square -- is no color-set light, and
`link._setting` (welfare-listed) takes numbers and words, never a look. So `link.SetChoice` names
the choice by the words its box shows it by (`link.choice_words`, a row's `ParamRow.choices`),
decoded as `SetColor`'s words are, and the session sets the one declared choice of those words
through `Session.set` unchanged, recorded as any value set is. Engine test material, run only in the
simulator: no number here is a timing claim about the rig.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import _sessions
from _rig import DIRECT
from wl_xcon.actor import Box
from wl_xcon.cli import _load_task
from wl_xcon.dio import Simulated as Card
from wl_xcon.link import (
    APPLY_KINDS, ApplyMany, CommandRefused, ParamRow, SetChoice, SetParameter, Simulated,
    Telemetry, TEXT_LIMIT, Withdraw, _command_from, _decode_command, _encode_command,
    choice_words,
)
from wl_xcon.photometry import SRGB, ColorSet, ColorSetLight
from wl_xcon.record import _written
from wl_xcon.run import Scripted
from wl_xcon.serve import parse_command
from wl_xcon.task import Disc
from wl_xcon.taskd import Session, SessionSpec
from wl_xcon.welfare import Deployment, Simulated as Pump

WALL_NOW = 1_700_000_000.0
JAKE = Box("jake")
BY = {"kind": "box", "name": "jake"}
#: The reference task whose target appearance is a disc or a square, each a gray of the target's
#: luminance: two looks, neither a color-set light, so neither is picked on a color card.
TASK = "tasks/fixation_detection.py"
NAME = "target_appearance"


def _looks() -> tuple:
    (declared,) = [p for p in _load_task(Path(TASK)).params if p.name == NAME]
    return declared.choices


def _words(choice) -> str:
    """The words a choice's segment shows and a pick names (`choice_words`)."""
    (words,) = [said for said, one in choice_words(_looks()).items() if one == choice]
    return words


class _Drained(Simulated):
    """A link that queues `script[n]` as the `n`th drain begins, so a command queued there is
    staged at the boundary before trial `n` and applies from trial `n + 1`. Past `BUDGET` drains
    the session is one that never ends, and fails here by name."""

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


def _run(tmp_path, script: dict, trials: int = 5) -> tuple[Session, _Drained]:
    """`fixation_detection` for `trials` trials on simulators, nobody looking, its target
    appearance the disc, `script[n]` drained at the `n`th boundary."""
    disc, _ = _looks()
    link = _Drained(script)
    spec = SessionSpec(
        task=TASK, allocation="tasks/allocation.py", root=tmp_path, session_id="2027-01-14_01",
        subject="A", trials=trials, frame_period=1 / 240, seed=3, values={NAME: disc},
        bounds=_sessions.bounds(), already_delivered_today=0.0,
        deployment=Deployment.RIG_FIXED, geometry=DIRECT, session_kind="training",
        calibration=SRGB)
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


def _looked(session: Session) -> list:
    """Each trial line's target appearance, in REC-27's form, in order."""
    return [line["params"][NAME] for line in _rows(session, "trials.jsonl")]


def _frames(link) -> list:
    return [frame for frame in link.published if isinstance(frame, Telemetry)]


def _staged(link) -> list:
    found: list = []
    for frame in _frames(link):
        found += [row for row in frame.staged if row not in found]
    return found


def _row(link, name: str = NAME) -> ParamRow:
    """`name`'s row on the last frame published while the run went."""
    running = [frame for frame in _frames(link) if frame.params and frame.trial_index > 0]
    (row,) = [row for row in running[-1].params if row.name == name]
    return row


def test_a_choice_is_picked_by_its_words_and_recorded_as_a_value_set(tmp_path):
    """The box's row gives a look setting's choices as their words (`ParamRow.choices`), in the
    order declared; a `choice` naming the square's words crosses the wire and a page's body as
    made, and is set through `Session.set` from the next trial: every line from trial 3 holds the
    square in REC-27's form, the change row is a `set` row as any value's -- `was` the disc, `now`
    the square, by who sent it -- the staged row names its command id, and the row says the
    square in the rig's words, from a person. A word setting's choices are its words as before,
    and a setting of numbers, or of color-set lights, gives none."""
    disc, square = _looks()
    words = (_words(disc), _words(square))
    assert words[0].startswith("Disc") and words[1].startswith("Square"), words

    pick = SetChoice(name=NAME, choice=words[1], by=JAKE, cid="box-1")
    assert SetChoice.KIND == "choice" and "choice" in APPLY_KINDS
    assert _decode_command(_encode_command(pick)) == pick
    assert parse_command({"kind": "choice", "name": NAME, "choice": words[1], "by": "jake",
                          "cid": "box-1"}) == SetChoice(name=NAME, choice=words[1],
                                                        by=Box("jake"), cid="box-1")

    session, link = _run(tmp_path, {2: [pick]})

    assert session.refusals == []
    lines = _rows(session, "trials.jsonl")
    assert [line["params"][NAME] for line in lines] == (
        [_written(disc)] * 2 + [_written(square)] * (len(lines) - 2))
    (change,) = _rows(session, "parameter_changes.jsonl")
    assert (change["kind"], change["name"], change["trial_number"]) == ("set", NAME, 3)
    assert (change["was"], change["now"], change["by"]) == (_written(disc), _written(square), BY)
    assert [row.cid for row in _staged(link)] == ["box-1"]
    row = _row(link)
    assert row.choices == words
    assert (row.source, row.changed, row.value, row.words) == ("person", True, None, words[1])

    assert ParamRow.of("side", "side", None, None, "left", False,
                       choices=("left", "right")).choices == ("left", "right")
    assert ParamRow.of("gap", "s", None, None, 0.5, False, choices=(0.5, 1.0)).choices == ()
    isohue = ColorSet.load("tests/fixtures/isohue.json")
    lights = tuple(Disc(size=1.0, color=ColorSetLight(isohue, hue)) for hue in ("green", "red"))
    assert choice_words(lights) is None
    assert ParamRow.of("odd", "appearance", None, None, lights[0], False,
                       choices=lights).choices == ()


def test_a_word_naming_no_choice_is_refused_with_the_choices_named(tmp_path):
    """Words naming none of the setting's choices are refused with a sentence naming each it
    offers, nothing staged, no change row, the disc on every line; so are a pick on a setting of
    numbers, on one the task does not declare, and on a reward size -- a welfare ceiling, which has
    no choices -- whose refusal is written to the session record too, its value as it was. And on
    the wire a choice or a name that is no text of 1 to `TEXT_LIMIT` characters is refused where it
    is decoded, naming the field, before any session sees it."""
    disc, square = _looks()
    session, link = _run(tmp_path, {2: [
        SetChoice(name=NAME, choice="Triangle", by=JAKE, cid="box-2"),
        SetChoice(name="fix_hold", choice="0.5", by=JAKE),
        SetChoice(name="no_such_setting", choice="Disc", by=JAKE),
        SetChoice(name="reward_correct", choice="0.2", by=JAKE)]})

    said = {name: why for name, _, why in session.refusals}
    assert said[NAME] == (
        f"'target_appearance' offers no choice 'Triangle', so the pick is refused and the previous "
        f"value stands; it offers {_words(disc)!r}; {_words(square)!r}")
    for name in ("fix_hold", "no_such_setting"):
        assert said[name] == (f"{name!r} is no setting this task declares whose box picks among "
                              f"its choices by their words, so no choice is picked for it")
    assert said["reward_correct"] == (
        "'reward_correct' is a reward size, a welfare ceiling, which has no choices, so no choice "
        "is picked for it; it is set alone, by its own box")
    (refused,) = [row for row in _frames(link)[-1].refusals if row.cid == "box-2"]
    assert refused.name == NAME
    assert not _staged(link) and not _rows(session, "parameter_changes.jsonl")
    assert _looked(session) == [_written(disc)] * len(_looked(session))
    (recorded,) = _rows(session, "refusals.jsonl")
    assert (recorded["name"], recorded["asked"], recorded["why"]) == (
        "reward_correct", "0.2", said["reward_correct"])
    assert session.spec.bounds.value("reward_correct") == 0.15

    body = {"kind": "choice", "name": NAME, "choice": "Disc", "by": BY}
    for field, bad in (("choice", ""), ("choice", 3), ("choice", "x" * (TEXT_LIMIT + 1)),
                       ("name", None)):
        with pytest.raises(CommandRefused, match=f"a 'choice' command's {field} is text"):
            _command_from({**body, field: bad})


def test_a_choice_pick_rides_apply_all_and_withdraws(tmp_path):
    """The console interface design's goals 2 and 3, a choice's pick among them: an Apply all of
    the square and `fix_hold` stages both under one command id and both take effect on one trial;
    one whose words name no choice refuses the whole, `fix_hold` "refused with" it; and an apply
    holding a pick, withdrawn while it waits, never applies and is written as `withdrawn` rows of
    the setting's kind `set`, the square what it would have been. A page's body carries the pick
    as a change by its own fields."""
    disc, square = _looks()
    together = ApplyMany(changes=(SetChoice(name=NAME, choice=_words(square), by=JAKE),
                                  SetParameter(name="fix_hold", value=0.35, by=JAKE)),
                         cid="all-1", by=JAKE)
    assert _decode_command(_encode_command(together)) == together
    assert parse_command({"kind": "apply_many", "by": "jake", "cid": "all-1", "changes": [
        {"kind": "choice", "name": NAME, "choice": _words(square)},
        {"kind": "set", "name": "fix_hold", "value": 0.35}]}) == ApplyMany(
            changes=(SetChoice(name=NAME, choice=_words(square), by=Box("jake")),
                     SetParameter(name="fix_hold", value=0.35, by=Box("jake"))),
            cid="all-1", by=Box("jake"))

    session, link = _run(tmp_path, {2: [together]})
    assert session.refusals == []
    rows = _rows(session, "parameter_changes.jsonl")
    assert sorted((row["kind"], row["name"], row["trial_number"]) for row in rows) == [
        ("set", "fix_hold", 3), ("set", NAME, 3)]
    assert [row.cid for row in _staged(link)] == ["all-1", "all-1"]
    lines = _rows(session, "trials.jsonl")
    assert [(line["params"][NAME], line["params"]["fix_hold"]) for line in lines] == (
        [(_written(disc), 0.3)] * 2 + [(_written(square), 0.35)] * (len(lines) - 2))

    refused, _ = _run(tmp_path / "refused", {2: [ApplyMany(changes=(
        SetParameter(name="fix_hold", value=0.35, by=JAKE),
        SetChoice(name=NAME, choice="Triangle", by=JAKE)), cid="all-2", by=JAKE)]})
    said = {name: why for name, _, why in refused.refusals}
    assert said["fix_hold"] == ("'fix_hold' is refused with 'target_appearance', applied together "
                                "with it, and none of them is staged")
    assert said[NAME].startswith("'target_appearance' offers no choice 'Triangle'"), said[NAME]
    assert not _rows(refused, "parameter_changes.jsonl")

    taken, link = _run(tmp_path / "withdrawn", {2: [
        ApplyMany(changes=(SetChoice(name=NAME, choice=_words(square), by=JAKE),
                           SetParameter(name="fix_hold", value=0.35, by=JAKE)),
                  cid="all-3", by=JAKE),
        Withdraw(cid="all-3", by=JAKE)]})
    assert taken.refusals == []
    withdrawn = _rows(taken, "parameter_changes.jsonl")
    assert sorted((row["kind"], row["name"], row["cid"]) for row in withdrawn) == [
        ("withdrawn", "fix_hold", "all-3"), ("withdrawn", NAME, "all-3")]
    (look,) = [row for row in withdrawn if row["name"] == NAME]
    assert look["withdrawn"] == {"kind": "set", "now": _written(square)}
    assert (look["was"], look["now"]) == (_written(disc), _written(disc))
    assert _looked(taken) == [_written(disc)] * len(_looked(taken))
