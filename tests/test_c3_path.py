"""The path, end to end (engine build C3's spec §12, "The path, not the piece"; pitfall P21).

Each piece of engine build C3 is tested alone in its own file. This walks the chain between them,
as a person drives it: a `wlx taskd` service (`service.Service`) on the simulators, its link the
page's, every command a `POST /commands` body built as `wlx serve` builds it
(`serve.parse_command`). It opens a session and starts a run of a plan whose task draws two
settings, whose first block makes its conditions from factors and whose second plays a
sequence-balanced order. Between trials it sends a drum switch and two values (one over a draw,
one over the conditions), a hand-back, a value no animal could answer with, which is refused, a
range changed live, and a revert of three rows.

Its record is read back by `resume.read`, as a resume reads it, and by wl-preproc's own code
(`read_rig_records`, `decode_stream`, `assemble` and `time_records`) through the worktree's
`wl-preproc` link. A missing checkout skips those tests locally and fails this module under
`WLX_REQUIRE_PREPROC=1`, which CI sets. The shapes read are the ones the C3 ask fixes
(`docs/pending-wl-preproc-amendments.md`, "OPEN — engine build C3"). A start no animal can
answer is refused by its pre-flight, and a session that died after its acts is found resumable by
`stranded.find` and goes on numbering.

One finding of this path is fixed with it (the controller's rulings of 2026-10-30): a value a person
or a revert gives a setting the open block draws, or its conditions give, was written with `was` the
run's own value, which no trial so given held. Such a row now writes `was`, and its meaning's `went`
and `step`, null.

No timing claim: a change row's `at` is the rig's bookkeeping, and the times in the streams here
are word counts. The animal is scripted, right on every trial, so each act lands on the trial
named whatever the simulated animal's model does (the C3 plan's call 40).
"""

from __future__ import annotations

import json
import os
import random
import shutil
from collections import Counter
from pathlib import Path

import pytest

import _sessions
from _rig import DIRECT, RIG
from _rig import PATH as RIG_FILE
from _sessions import OPEN_ACCEPTED, WALL, typed
from wl_xcon import link as _link
from wl_xcon import resume, stranded, taskd, variation
from wl_xcon.actor import Box
from wl_xcon.check import IMPOSSIBLE
from wl_xcon.cli import _load_allocation
from wl_xcon.dio import Simulated as Card
from wl_xcon.link import Simulated
from wl_xcon.photometry import SRGB
from wl_xcon.run import Scripted
from wl_xcon.serve import parse_command
from wl_xcon.service import Service
from wl_xcon.task import SaccadeTo, Uniform
from wl_xcon.taskd import Session, SessionSpec
from wl_xcon.welfare import Deployment
from wl_xcon.welfare import Simulated as Pump

#: wl-preproc's decoder, trial assembler, record reader and timing join, as `tests/test_service.py`
#: guards its assembler: a missing checkout skips the tests that read through them locally, and
#: fails this module under `WLX_REQUIRE_PREPROC=1`, which CI sets.
_REQUIRED = os.environ.get("WLX_REQUIRE_PREPROC") == "1"
try:
    from wl_preproc.contracts import events as their_events
    from wl_preproc.events.assemble import assemble as their_assemble
    from wl_preproc.events.rigrecords import CHANGES_NAME, read_rig_records
    from wl_preproc.events.rigtiming import code_times, time_records
except ImportError as exc:  # pragma: no cover - exercised by the CI job
    if _REQUIRED:
        raise AssertionError(
            f"WLX_REQUIRE_PREPROC=1 but wl-preproc is not importable ({exc}). The C3 record read "
            f"by wl-preproc's own code is the only check that it reads back whole; skipping it "
            f"would report a record nobody read"
        ) from exc
    their_events = their_assemble = read_rig_records = None

_contract = pytest.mark.skipif(
    their_assemble is None,
    reason="wl-preproc checkout not beside this repo; the record cannot be read by its code",
)

ALLOCATION = "tasks/allocation.py"
SESSION = "2027-01-14_01"
#: The seed the service draws for every run here.
SEED = 7
JAKE = Box("jake")
#: `PARAM_CHANGED`'s code in the reference allocation: what each act here but the switch strobes.
PARAM_CHANGED = 4130
#: `RUN_START`'s, strobed as a run starts.
RUN_START = 4135
#: The task's two draws: the fixation hold drawn afresh each trial, the target's height kept on a
#: repeat.
DRAWS = ('{"fix_hold": Uniform(0.25, 0.45, repeat=FRESH), '
         '"target_y": Uniform(-2.0, 2.0, repeat=SAME)}')
#: Its plan: the four conditions two factors make, each twice, then a sequence-balanced block of
#: two conditions over two cycles, each the linear sequence of five, ten trials. Engine test
#: material, run only in the simulator.
PLANS = ('{"p": Plan([Block("grid", [], factorial=Factorial({"target_x": (-10.0, 10.0), '
         '"target_luminance": (30.0, 60.0)}, target=2)), '
         'Block("seq", [Condition("left", {"target_x": -10.0}, target=4), '
         'Condition("right", {"target_x": 10.0}, target=4)], '
         'order=SequenceBalanced(cycles=2))])}')
#: A plan of one block whose one condition draws the target's height from a range of its own in
#: place of the task's draw, ten trials, for the test of a value set over a draw. Engine test
#: material.
OWN = ('{"own": Plan([Block("b", [Condition("c", {"target_y": Uniform(-2.0, 2.0, '
       'repeat=FRESH)}, target=10)], draws={"target_y": BY_CONDITIONS})])}')
#: A plan of two blocks for the test of a value set over conditions: in `given` one condition gives
#: the fixation window and the other leaves it to the run, three trials each; in `bare` none gives
#: it, four trials. Engine test material.
GIVEN = ('{"given": Plan([Block("given", [Condition("wide", {"fix_window": 3.0}, target=3), '
         'Condition("plain", {}, target=3)]), Block("bare", [Condition("any", {}, target=4)])])}')
#: The acts, each a body the page sends, by the drain that hands it over. The run's drains are 3
#: (before trial 1) to 11 (before trial 9) in `grid`, 12 as the plan moves to `seq`, then 13
#: (before trial 10) on. A switch applies at once; a value, a hand-back, a range or a revert
#: applies from the trial after the one it was drained before.
ACTS = {
    5: [{"kind": "drum", "by": "jake", "scope": "run"},
        {"kind": "set", "by": "jake", "name": "fix_hold", "value": 0.25},
        {"kind": "set", "by": "jake", "name": "target_luminance", "value": 45.0}],
    8: [{"kind": "hand_back", "by": "jake", "name": "fix_hold"},
        {"kind": "set", "by": "jake", "name": "target_hold", "value": 0.8}],
    13: [{"kind": "range", "by": "jake", "name": "fix_hold",
          "numbers": {"low": 0.25, "high": 0.3}}],
    16: [{"kind": "revert", "by": "jake", "change": 2}],
}


def _task(folder: Path, plans: str = PLANS) -> Path:
    """`varied_task` drawing `DRAWS` with `plans`, written into `folder` as `path.py`, its target
    hold bounded by the response deadline: the timeout in `verify`, which the reference task writes
    as 3 s, reads `response_deadline`, so a target hold longer than the deadline leaves no time to
    answer (XC-343's first combination), as `tests/test_live_refusal.py`'s `_deadline_task` has
    it. It loads, warned `hold-cut-short` over the declared ranges."""
    path = _sessions.varied_task(folder, draws=DRAWS, plans=plans, name="path")
    text = path.read_text()
    old = "                On(After(3.0), Outcome.NO_RESPONSE),"
    assert text.count(old) == 1, old
    path.write_text(text.replace(
        old, '                On(After(P("response_deadline")), Outcome.NO_RESPONSE),'))
    return path


def _folders(tmp_path) -> tuple[Path, Path, Path]:
    """`--subjects`, `--tasks` and `--root` for a service, as `tests/test_service.py`'s: the animal
    `REFERENCE`, its eight-hour bounds and its settings, and the task above. Copies, never
    imports."""
    subjects, tasks, root = tmp_path / "subjects", tmp_path / "tasks", tmp_path / "sessions"
    (subjects / "REFERENCE").mkdir(parents=True)
    shutil.copy("tasks/eight_hour_bounds.py", subjects / "REFERENCE" / "bounds.py")
    shutil.copy("tasks/reference_subject.py", subjects / "REFERENCE" / "settings.py")
    root.mkdir()
    _task(tasks)
    return subjects, tasks, root


class _Page(Simulated):
    """The page, as the service's link: its `n`th drain hands over `script[n]`, each body built
    into a command as `wlx serve` builds it (`serve.parse_command`), so a body the page could not
    send fails here. The service's own drains and a run's are counted alike, as
    `tests/test_service.py`'s `_Script` counts them.

    It also bounds the session: the longest passing test here drains 23 times, so one past
    `BUDGET` is a plan that never completes (a mutant of `scheduler.advance` or `task.of` runs it
    toward the eight-hour limit), and fails here by name at once rather than hanging."""

    BUDGET = 120

    def __init__(self, script: dict) -> None:
        super().__init__()
        self.script, self.drains, self.exceeded = script, 0, None

    def drain(self) -> list:
        self.drains += 1
        if self.drains > self.BUDGET:
            # The session turns an exception in its loop into a fault stop, so the message is kept
            # for the test's assertion on the stop to name (`exceeded`) as well as raised.
            self.exceeded = (f"the session drained {self.drains} times, past the budget of "
                             f"{self.BUDGET} (the longest passing test here counts 23): the "
                             "plan is not completing")
            raise AssertionError(self.exceeded)
        for body in self.script.get(self.drains, ()):
            # Through the command codec as well, as `Server.dispatch` and `ZmqLink` carry it.
            self.queue(_link._decode_command(_link._encode_command(parse_command(body))))
        return super().drain()


class _Recording:
    """The simulated rig's wall, advancing with the recording `_timed` reads: `start`,
    and a millisecond for each word the cards it makes have sent."""

    def __init__(self, start: float) -> None:
        self.start, self.cards = start, []

    def card(self) -> Card:
        card = Card()
        self.cards.append(card)
        return card

    def __call__(self) -> float:
        return self.start + 0.001 * sum(len(card.codes) for card in self.cards)


def _service(folders, script: dict, wall: float = WALL) -> Service:
    """A `wlx taskd` service on the simulators, its link the page's, its wall `wall` advancing a
    millisecond a word (`_Recording`), and every run's seed `SEED`."""
    subjects, tasks, root = folders
    recording = _Recording(wall)
    return Service(
        rig=RIG, rig_path=RIG_FILE, subjects=subjects, tasks=tasks,
        allocation=_load_allocation(Path(ALLOCATION)), allocation_path=ALLOCATION,
        root=root, link=_Page(script), seed=lambda: SEED, wall_clock=recording,
        card=recording.card,
    )


def _open() -> dict:
    """The page's open: the animal head-fixed, its departure a minute before the wall, every
    warning an open lists accepted."""
    return {"kind": "open", "by": "jake", "session_id": SESSION, "animal": "REFERENCE",
            "deployment": "rig_fixed", "view": "direct", "session_kind": "training",
            "departure": typed(60), "delivered_today": 0.0, "answer": None, "amend_to": None,
            "amend_reason": "", "accepted": [list(key) for key in OPEN_ACCEPTED]}


def _start(plan: str | None = "p", trials: int = 40, **values) -> dict:
    """The page's start of `plan` (the plain run of `trials` where `None`): the response deadline
    and the target hold as the run's values, each of `values` over them, every unknown item
    acknowledged."""
    return {"kind": "start", "by": "jake", "task": "path.py", "plan": plan, "trials": trials,
            "values": {"response_deadline": 0.6, "target_hold": 0.2, **values},
            "acknowledged": ["warnings", "pump calibration", "eye tracker"]}


def _right(trial, values: dict, index: int) -> Scripted:
    """An animal right on every trial, whatever its holds: it holds the fixation point 20 frames
    past its hold, then looks at the target and stays on it 400 frames, past any target hold here
    (as `tests/test_hand_back_and_ranges.py`'s)."""
    held = round(values["fix_hold"] * 240) + 20
    return Scripted({SaccadeTo("target"): held + 10},
                    inside={frame: "fix" if frame <= held else "target"
                            for frame in range(1, held + 400)})


def _opened(folders, script: dict) -> Service:
    """A service whose first pass took the page's open, its session's animal `_right`."""
    service = _service(folders, script)
    service.step()
    assert service.session is not None, service.refusals
    service.session.world = _right
    return service


def _rows(xcon: Path, name: str) -> list[dict]:
    """The rows of one of a session's files, none where it was never written."""
    path = xcon / name
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def _timed(records, codes: list[int], resumed: tuple = ()) -> tuple:
    """wl-preproc's reading of `codes` as one recording, a word a millisecond: its assembly, and
    each change row's time by its code (`time_records`'s rule: the n-th row carrying
    `PARAM_CHANGED` takes the n-th such code's time)."""
    stream = [(i * 0.001, word) for i, word in enumerate(codes)]
    for start, more in resumed:
        stream += [(start + i * 0.001, word) for i, word in enumerate(more)]
    events = their_events.decode_stream(stream)
    return their_assemble(events), time_records(records, code_times(events), ())


@_contract
def test_a_session_driven_through_the_consoles_commands_reads_back_whole(tmp_path):
    """The C3 spec §12's path (pitfall P21). Through the page's bodies, a `wlx taskd` session plays
    a plan with task draws, a factorial block and a sequence-balanced block, while a person
    switches drumming on, holds the fixation hold over its draw and the target's luminance over
    the conditions, hands the hold back, sends a value no animal could answer with, which is
    refused, narrows the hold's draw, and reverts to the moment after the hold was set. Then:
    - the change log holds one row per setting an act moved, a change id per act, a revert's three
      rows sharing one, `sequence` on each that strobed, every row named;
    - each trial line's `drawn`, `live`, `overridden`, `eased` and `planned` agree with the acts,
      and each value it drew is the one its seed, its start row's draws and the change log give;
    - each block end's `counts` agree with its lines (the plan's science review, M-4);
    - wl-preproc's reader reports no problem, and its timing join puts the n-th row carrying
      `PARAM_CHANGED` at the n-th such code, in the gap before the first trial the row names;
    - `resume.read` finds it resumable, numbering on from the log."""
    service = _opened(_folders(tmp_path), {1: [_open()], 2: [_start()], **ACTS})

    service.step()

    session = service.session
    xcon = session.directory
    frame = service.link.published[-1]
    assert (frame.phase, frame.stop_kind) == ("between_runs", "completed"), service.link.exceeded
    # The value no animal could answer with: refused on the feed, never staged or applied.
    ((name, by, why),) = session.refusals
    assert (name, by) == ("target_hold", JAKE)
    assert why.startswith("'target_hold' at 0.8 is refused, and the previous value stands: it "
                          "would leave trials no animal can get right, in grid: ")
    assert f"({IMPOSSIBLE})" in why
    start, end = _rows(xcon, "runs.jsonl")
    lines = _rows(xcon, "trials.jsonl")
    changes = _rows(xcon, "parameter_changes.jsonl")

    # The change log (the ask's table): the switch at once, strobing nothing; each value, the
    # hand-back and the range its own act; the revert one act of three rows -- the luminance
    # handed back, the draw put back to the declared one, the hold set again -- each strobed.
    declared = start["draws"]["fix_hold"]
    narrowed = {"class": "Uniform", "fields": {"high": 0.3, "low": 0.25, "repeat": "fresh"}}
    assert declared == {"class": "Uniform", "fields": {"high": 0.45, "low": 0.25,
                                                       "repeat": "fresh"}}
    assert [(row["change"], row["kind"], row["name"], row.get("sequence"), row["trial_number"])
            for row in changes] == [
        (1, "drum", "drumming", None, 3),
        (2, "set", "fix_hold", 1, 4),
        (3, "set", "target_luminance", 2, 4),
        (4, "hand_back", "fix_hold", 3, 7),
        (5, "range", "fix_hold", 4, 11),
        (6, "revert", "target_luminance", 5, 14),
        (6, "revert", "fix_hold", 6, 14),
        (6, "revert", "fix_hold", 7, 14),
    ]
    # A value landing on a setting the open block draws or its conditions give writes no `was`,
    # and no way it went: no trial held one value before it (the controller's rulings; the unit
    # tests below).
    assert [(row["was"], row["now"]) for row in changes] == [
        (None, "run"), (None, 0.25), (None, 45.0), (0.25, None), (declared, narrowed),
        (45.0, None), (narrowed, declared), (None, 0.25)]
    assert [(changes[n]["meaning"]["went"], changes[n]["meaning"]["step"])
            for n in (1, 2, 7)] == [(None, None)] * 3
    assert (changes[3]["to"], changes[4]["from"], changes[4]["block"]) == ("draw", "task", None)
    assert [row["moment"] for row in changes[5:]] == [2, 2, 2]
    assert "to" not in changes[5] and (changes[6]["from"], changes[6]["block"]) == ("task", None)
    assert [row["event_code"] for row in changes] == [None] + [PARAM_CHANGED] * 7
    assert all(row["by"] == {"kind": "box", "name": "jake"} for row in changes)
    # Each kind's whole row, as the ask's table fixes it (the instants aside: `at` is the rig's
    # bookkeeping, XC-383, and `at_local` its local reading).
    assert all(isinstance(row["at_local"], str) for row in changes)
    bare = [{key: value for key, value in row.items() if key not in ("at", "at_local")}
            for row in changes]
    jake = {"kind": "box", "name": "jake"}
    common = {"by": jake, "offered": [], "odds": None, "run": 0, "event_code": PARAM_CHANGED}
    hold = {"kind": "clear-cut", "raising": "harder", "relative_to": None, "role": "criterion"}
    shine = {"kind": "expected", "raising": "easier", "relative_to": "background",
             "role": "stimulus"}
    assert bare[0] == {
        "by": jake, "offered": [], "odds": None, "run": 0, "event_code": None, "change": 1,
        "kind": "drum", "name": "drumming", "was": None, "now": "run", "scope": "run",
        "block": "grid", "meaning": None, "trial_number": 3}
    assert bare[1] == {**common, "change": 2, "kind": "set", "name": "fix_hold", "was": None,
                       "now": 0.25, "sequence": 1, "trial_number": 4,
                       "meaning": {**hold, "step": None, "went": None}}
    assert bare[3] == {**common, "change": 4, "kind": "hand_back", "name": "fix_hold",
                       "was": 0.25, "now": None, "to": "draw", "sequence": 3, "trial_number": 7,
                       "meaning": {**hold, "step": None, "went": None}}
    assert bare[4] == {**common, "change": 5, "kind": "range", "name": "fix_hold",
                       "was": declared, "now": narrowed, "from": "task", "block": None,
                       "sequence": 4, "trial_number": 11,
                       "meaning": {**hold, "step": None, "went": "easier"}}
    assert bare[5:] == [
        {**common, "change": 6, "kind": "revert", "name": "target_luminance", "was": 45.0,
         "now": None, "moment": 2, "sequence": 5, "trial_number": 14,
         "meaning": {**shine, "step": None, "went": None}},
        {**common, "change": 6, "kind": "revert", "name": "fix_hold", "was": narrowed,
         "now": declared, "from": "task", "block": None, "moment": 2, "sequence": 6,
         "trial_number": 14, "meaning": {**hold, "step": None, "went": None}},
        {**common, "change": 6, "kind": "revert", "name": "fix_hold", "was": None, "now": 0.25,
         "moment": 2, "sequence": 7, "trial_number": 14,
         "meaning": {**hold, "step": None, "went": None}}]
    # The drum switch is a control too, in `controls.jsonl`, with the trial it was drained before.
    (control,) = _rows(xcon, "controls.jsonl")
    assert {key: value for key, value in control.items() if key not in ("at", "at_local")} == {
        "kind": "drum", "scope": "run", "block": "grid", "was": None, "now": "run", "by": jake,
        "event_code": None, "run": 0, "trial_index": 2}

    # Each trial line, as the acts leave things from the trial each row names: trials 1-3 drawn
    # as declared; 4-6 the two values held, the luminance over the conditions that give it (so
    # overridden), each eased (a hold at the declared lowest, an expected setting moved); 7-8 the
    # hold handed back to its draw; 9-10 the sequence-balanced block, whose conditions give no
    # luminance; 11-13 the hold drawn from the range change 5 put in force, eased by it, its
    # longest lowered, the easier way, so the range counts as easier as a whole (the PI,
    # 2026-10-31, "Judge the range as a whole"); 14-18 the revert to change 2: the hold held
    # again, the luminance back to the run's own.
    declared_draws = {"fix_hold": "task", "target_y": "task"}
    narrowed_draws = {"fix_hold": 5, "target_y": "task"}
    held_draws = {"target_y": "task"}
    both, luminance, hold = ["fix_hold", "target_luminance"], ["target_luminance"], ["fix_hold"]
    assert [(line["trial_number"], line["block"], line["drawn"], line["live"],
             line["overridden"], line["eased"]) for line in lines] == [
        *[(n, "grid", declared_draws, [], [], []) for n in (1, 2, 3)],
        *[(n, "grid", held_draws, both, luminance, both) for n in (4, 5, 6)],
        *[(n, "grid", declared_draws, luminance, luminance, luminance) for n in (7, 8)],
        *[(n, "seq", declared_draws, luminance, [], luminance) for n in (9, 10)],
        *[(n, "seq", narrowed_draws, luminance, [], both) for n in (11, 12, 13)],
        *[(n, "seq", held_draws, hold, [], hold) for n in (14, 15, 16, 17, 18)],
    ]
    # Each drawn value is the one the seed gives it from the range its line names, read from the
    # record alone (TSK-06: "any run replayed exactly from its seed"); each held one the person's.
    ranges = {row["change"]: row["now"] for row in changes if row["kind"] == "range"}
    held = {"fix_hold": 0.25, "target_luminance": 45.0}
    for line in lines:
        for setting, source in line["drawn"].items():
            written = start["draws"][setting] if source == "task" else ranges[source]
            assert written["class"] == "Uniform"
            assert line["params"][setting] == variation.draw(
                Uniform(**written["fields"]), start["seed"], line["index"], ("task", setting))
        assert {setting: line["params"][setting] for setting in line["live"]} == {
            setting: held[setting] for setting in line["live"]}
        assert line["params"]["target_hold"] == 0.2, "the refused value never applied"
    assert [line["params"]["target_luminance"] for line in lines[13:]] == [40.0] * 5, (
        "handed back by the revert, to the run's own")

    # The designed order and the factorial, as the start and end rows record them.
    made = [condition["name"] for condition in start["generated"][0]["conditions"]]
    assert made == [f"target_x={x}, target_luminance={luminance}"
                    for x in (-10.0, 10.0) for luminance in (30.0, 60.0)]
    played = Counter(line["condition"] for line in lines if line["block"] == "grid")
    assert played == dict.fromkeys(made, 2)
    assert start["generated"] == [{"block": "grid", "excluded": [], "conditions": [
        {"name": name, "target": 2, "values": {"target_x": x, "target_luminance": lum}}
        for name, (x, lum) in zip(made, [(-10.0, 30.0), (-10.0, 60.0), (10.0, 30.0),
                                         (10.0, 60.0)], strict=True)]}]
    grid, seq = end["block_ends"]
    sequence = [line for line in lines if line["block"] == "seq"]
    assert seq["planned"] == list(variation.balanced_sequence(
        ["left", "right"], 2, 2, random.Random(f"design:{start['seed']}:1")))
    assert [line["condition"] for line in sequence] == seq["planned"]
    assert [line["planned"] for line in sequence] == [
        {"cycle": place // 5, "position": place % 5, "lead_in": place % 5 == 0}
        for place in range(10)]
    assert grid["planned"] is None and all(line["planned"] is None for line in lines[:8])
    assert grid["varied"]["target_luminance"] == [{"by": "condition"}, {"by": "person"}]
    assert seq["varied"]["fix_hold"] == [
        {"by": "draw", "from": "task", "distribution": declared},
        {"by": "draw", "from": 5, "distribution": narrowed}, {"by": "person"}]
    # Each block's counts, as its lines say (the ask's `counts`; the plan's science review, M-4):
    # each condition's lines, those a person's value overrode, and those kept out of moving up --
    # in the factorial block five of its eight overridden and eased, the luminance held over its
    # conditions; in the sequence-balanced block none overridden, every one eased. No setting
    # here places a direction.
    for block, entry in (("grid", grid), ("seq", seq)):
        mine = [line for line in lines if line["block"] == block]
        assert entry["counts"] == {
            name: {"trials": sum(1 for line in mine if line["condition"] == name),
                   "overridden": sum(1 for line in mine
                                     if line["condition"] == name and line["overridden"]),
                   "eased": sum(1 for line in mine if line["condition"] == name and line["eased"])}
            for name in dict.fromkeys(line["condition"] for line in mine)}
    assert [[sum(counted[kind] for counted in entry["counts"].values())
             for kind in ("trials", "overridden", "eased")] for entry in (grid, seq)] == [
        [8, 5, 5], [10, 0, 10]]
    assert start["directions"] == []

    # wl-preproc's reader and timing join: every row named, `sequence` on the strobed ones alone,
    # the n-th carrying `PARAM_CHANGED` at the n-th such code, in the gap before its first trial.
    records = read_rig_records(xcon.parent)
    assert records.problems == ()
    assert [(change.name, change.sequence) for change in records.changes] == [
        (row["name"], row.get("sequence")) for row in changes]
    codes = session.card.codes
    assert codes.count(PARAM_CHANGED) == 7
    assembly, timing = _timed(records, codes)
    assert assembly.errors == []
    assert [trial.trial_id for trial in assembly.trials] == list(range(1, 19))
    assert [problem for problem in timing.problems if problem.startswith(CHANGES_NAME)] == []
    trials = {trial.trial_id: trial for trial in assembly.trials}
    assert timing.clock is not None and timing.problems == (), timing.problems
    for row, at in zip(changes, timing.changes, strict=True):
        # To the word: a switch, which sends none, is timed at the last word before it.
        at = round(at, 6)
        before, after = trials[row["trial_number"] - 1].end_s, trials[row["trial_number"]].start_s
        assert (before < at if "sequence" in row else before == at) and at < after, (row, at)

    # Resumable, as `stranded.find` reads it, numbering on from the log.
    restoration = resume.read(xcon, session.welfare.left_cage_wall_at)
    assert (restoration.sequence, restoration.change, restoration.levels.trials) == (7, 6, 18)


def test_a_start_with_an_impossible_value_is_refused_by_its_preflight(tmp_path):
    """The C3 spec §9 at a run's start, on the path through `wlx taskd` (the C3 plan's review,
    I-5): a start whose response deadline, 0.15 s and inside its declared range, cannot outlast
    the 0.2 s target hold it bounds fails its pre-flight's starting values item, judged over every
    condition the plan's factors make, and does not start: no run row, nothing strobed for a run.
    The session waits between runs, and the same start at a 0.6 s deadline runs."""
    service = _opened(_folders(tmp_path), {1: [_open()], 2: [_start(response_deadline=0.15)],
                                           3: [_start()]})

    service.step()

    session = service.session
    frame = service.link.published[-1]
    assert (frame.phase, frame.run_index) == ("between_runs", None)
    (values,) = [item for item in frame.preflight.items if item.name == "starting values"]
    assert values.result == "fail"
    assert values.said.startswith(
        f"{IMPOSSIBLE}: plan 'p': block 'grid', conditions 'target_x=-10.0, "
        "target_luminance=30.0', 'target_x=-10.0, target_luminance=60.0', 'target_x=10.0, "
        "target_luminance=30.0', 'target_x=10.0, target_luminance=60.0': state 'verify' ends the "
        "trial NO_RESPONSE after `response_deadline`, 0.15 s, while its 'target' hold takes "
        "`target_hold`, 0.2 s")
    assert f"; {IMPOSSIBLE}: plan 'p': block 'seq', conditions 'left', 'right': " in values.said
    ((name, by, why),) = session.refusals
    assert (name, by) == ("start", JAKE)
    assert why == f"pre-flight failed, so the run does not start: starting values: {values.said}"
    assert _rows(session.directory, "runs.jsonl") == []
    assert RUN_START not in session.card.codes

    service.step()

    assert service.link.published[-1].stop_kind == "completed"
    assert [row["event"] for row in _rows(session.directory, "runs.jsonl")] == ["start", "end"]


@_contract
def test_a_crashed_c3_session_is_listed_resumable_by_stranded_find(tmp_path, monkeypatch):
    """The C3 spec §12 ("every session resumable, none refused by `stranded.find` over a change
    row"), on the path. A session driven by the acts above dies as trial 15 begins (a
    `KeyboardInterrupt`, which `Service._run` does not contain, so the service is dropped with no
    end and no return), its change log holding a switch, values, a hand-back, a range and a
    three-row revert. A restarted service finds it stranded and resumable through the
    welfare-listed `stranded.find`, resumes it from the page, and runs a run in which a person's
    value takes the next change id and `sequence`. wl-preproc reads the whole log with no problem,
    and both processes' codes as one recording time every strobed row."""
    folders = _folders(tmp_path)
    real, calls = taskd.run_trial, [0]

    def dies_as_trial_15_begins(*args, **kwargs):
        calls[0] += 1
        if calls[0] == 15:
            raise KeyboardInterrupt
        return real(*args, **kwargs)

    monkeypatch.setattr(taskd, "run_trial", dies_as_trial_15_begins)
    first = _opened(folders, {1: [_open()], 2: [_start()], **ACTS})
    with pytest.raises(KeyboardInterrupt):
        first.step()
    xcon = first.session.directory
    assert [row["kind"] for row in _rows(xcon, "parameter_changes.jsonl")] == [
        "drum", "set", "set", "hand_back", "range", "revert", "revert", "revert"]

    (found,) = stranded.find(folders[2])
    assert (found.session_id, found.subject, found.resumable, found.why) == (
        SESSION, "REFERENCE", True, "")
    assert found.left_at == first.session.welfare.left_cage_wall_at

    second = _service(folders, {
        1: [{"kind": "resume_session", "by": "jake", "session_id": SESSION}],
        2: [_start(plan=None, trials=3)],
        4: [{"kind": "set", "by": "jake", "name": "fix_hold", "value": 0.3}],
    }, wall=WALL + 600)
    assert second.stranded == [found]
    second.step()
    assert second.session is not None and second.stranded == [], second.refusals
    second.session.world = _right
    second.step()

    assert second.link.published[-1].stop_kind == "completed"
    changes = _rows(xcon, "parameter_changes.jsonl")
    assert [(row["kind"], row["change"], row.get("sequence"), row["run"])
            for row in changes[-2:]] == [("revert", 6, 7, 0), ("set", 7, 8, 1)]
    records = read_rig_records(xcon.parent)
    assert records.problems == ()
    assert [change.sequence for change in records.changes] == [None, *range(1, 9)]
    codes = first.session.card.codes + second.session.card.codes
    assert codes.count(PARAM_CHANGED) == 8
    assembly, timing = _timed(records, first.session.card.codes,
                              resumed=((600.0, second.session.card.codes),))
    assert assembly.errors == []
    assert timing.clock is not None and timing.problems == (), timing.problems
    assert [at is None for at in timing.changes] == [False] * 9


def _session(tmp_path, script: dict, plans: str = OWN, plan: str = "own") -> Session:
    """A session on the simulators running `plan` of the task above with `plans`, its link the
    page's with `script`, its wall following its frames, the animal out of its cage, its head fixed
    and `_right`. Its run drains once before each trial and once as the plan moves to its next
    block: a value drained before trial `n` applies from trial `n + 1`."""
    spec = SessionSpec(
        task=str(_task(tmp_path / "tasks", plans)), allocation=ALLOCATION, root=tmp_path,
        session_id=SESSION, subject="A", trials=40, frame_period=1 / 240, seed=SEED,
        values={"response_deadline": 0.6, "target_hold": 0.2}, bounds=_sessions.bounds(),
        already_delivered_today=0.0, deployment=Deployment.RIG_FIXED, geometry=DIRECT,
        session_kind="training", calibration=SRGB, plan=plan,
    )
    session = Session(spec, card=Card(), pump=Pump(), link=_Page(script))
    session.wall_clock = lambda: WALL + session.now()
    session.left_cage(at=WALL)
    session.head_fixed(at=session.wall_now())
    session.world = _right
    return session


def test_a_value_set_over_a_draw_writes_no_was_and_no_way_it_went(tmp_path):
    """The path test's finding, and the controller's ruling of 2026-10-30: a record must not claim a
    value no trial held. A value a person or a revert gives a setting drawn at that moment -- by
    the task's draw, a block's or a condition's own range, no person holding it -- writes `was`
    null in its change row, and its meaning's `went` and `step` null. `Session.set` reads the run's
    own value under the draw, which no trial held; what the animal saw is each trial line's
    `drawn` and `params`. A value over a setting a person already holds, or one neither a draw nor
    a condition gives, keeps its `was`, `went` and `step`, and so does a reward size. Here a person
    sets the hold over the task's draw, the target's height over its condition's own range, the
    fixation window (given by nothing) and the reward size; then the hold again, now held; hands
    the hold back; and reverts to the first change, which sets the hold again over its draw."""
    set_ = {"kind": "set", "by": "jake"}
    session = _session(tmp_path, {
        2: [{**set_, "name": "fix_hold", "value": 0.4}, {**set_, "name": "target_y", "value": 1.0},
            {**set_, "name": "fix_window", "value": 2.5},
            {**set_, "name": "reward_correct", "value": 0.2}],
        4: [{**set_, "name": "fix_hold", "value": 0.35}],
        6: [{"kind": "hand_back", "by": "jake", "name": "fix_hold"}],
        8: [{"kind": "revert", "by": "jake", "change": 1}],
    })

    session.run()

    assert session.refusals == [] and session.stop_kind == "completed"
    rows = _rows(session.directory, "parameter_changes.jsonl")
    assert [(row["change"], row["kind"], row["name"], row["was"], row["now"], row["trial_number"])
            for row in rows] == [
        (1, "set", "fix_hold", None, 0.4, 3),
        (2, "set", "target_y", None, 1.0, 3),
        (3, "set", "fix_window", 2.0, 2.5, 3),
        (4, "set", "reward_correct", 0.15, 0.2, 3),
        (5, "set", "fix_hold", 0.4, 0.35, 5),
        (6, "hand_back", "fix_hold", 0.35, None, 7),
        (7, "revert", "fix_window", 2.5, None, 9),
        (7, "revert", "target_y", 1.0, None, 9),
        (7, "revert", "fix_hold", None, 0.4, 9),
    ]
    assert [None if row["meaning"] is None else (row["meaning"]["went"], row["meaning"]["step"])
            for row in rows] == [
        (None, None), (None, None), ("easier", 2.5 - 2.0), None, ("easier", 0.35 - 0.4),
        (None, None), (None, None), (None, None), (None, None)]
    lines = _rows(session.directory, "trials.jsonl")
    assert [line["drawn"] for line in lines[:2]] == [
        {"fix_hold": "task", "target_y": "condition"}] * 2
    assert [line["params"]["fix_hold"] for line in lines[2:4]] == [0.4, 0.4]


def test_a_value_set_over_its_conditions_writes_no_was_and_no_way_it_went(tmp_path):
    """The controller's second ruling of 2026-10-30, for the same reason: where no person holds a
    setting and the open block's conditions give it -- one condition is enough, the others leaving
    it to the run -- a value a person or a revert gives it writes `was` null, and its meaning's
    `went` and `step` null. No single value was held before it: engine build C2b wrote the run's
    own value there, which no trial its conditions gave held; each trial line's `params` shows what
    the animal saw. In a block whose conditions do not give it, nor a draw, the run's own value
    was held, and the row keeps it, with the way it went. Here a person sets the fixation window
    over block `given`'s conditions, hands it back, reverts to that first change (setting it again
    over them), hands it back again, and sets it in block `bare`, whose conditions give nothing."""
    window = {"kind": "set", "by": "jake", "name": "fix_window", "value": 2.5}
    hand_back = {"kind": "hand_back", "by": "jake", "name": "fix_window"}
    session = _session(tmp_path, {
        2: [window], 3: [hand_back], 4: [{"kind": "revert", "by": "jake", "change": 1}],
        5: [hand_back], 9: [window],
    }, plans=GIVEN, plan="given")

    session.run()

    assert session.refusals == [] and session.stop_kind == "completed"
    rows = _rows(session.directory, "parameter_changes.jsonl")
    assert [(row["change"], row["kind"], row["was"], row["now"], row["trial_number"])
            for row in rows] == [
        (1, "set", None, 2.5, 3),
        (2, "hand_back", 2.5, None, 4),
        (3, "revert", None, 2.5, 5),
        (4, "hand_back", 2.5, None, 6),
        (5, "set", 2.0, 2.5, 9),
    ]
    assert [(row["meaning"]["went"], row["meaning"]["step"]) for row in rows] == [
        (None, None), (None, None), (None, None), (None, None), ("easier", 2.5 - 2.0)]
    lines = _rows(session.directory, "trials.jsonl")
    assert [line["block"] for line in lines] == ["given"] * 6 + ["bare"] * 4
    assert [line["params"]["fix_window"] for line in lines[8:]] == [2.5, 2.5]


def test_two_values_of_one_setting_in_one_drain_both_write_no_was(tmp_path):
    """The path test's finding, held for a second value in one inter-trial interval (the review of
    Task 19, Important 1): `set` reads `was` before the interval, so both rows are judged by what
    gave the setting then, not by the first row's hold. Over the task's draw, 0.4 then 0.35 of the
    fixation hold; over block `given`'s conditions, 2.5 then 2.6 of the fixation window. Each row
    writes `was` null and no way it went; it was the run's own value, which no trial held."""
    hold = [{"kind": "set", "by": "jake", "name": "fix_hold", "value": 0.4},
            {"kind": "set", "by": "jake", "name": "fix_hold", "value": 0.35}]
    window = [{"kind": "set", "by": "jake", "name": "fix_window", "value": 2.5},
              {"kind": "set", "by": "jake", "name": "fix_window", "value": 2.6}]
    drawn = _session(tmp_path / "a", {2: hold})
    drawn.run()
    given = _session(tmp_path / "b", {2: window}, plans=GIVEN, plan="given")
    given.run()

    for session, name in ((drawn, "fix_hold"), (given, "fix_window")):
        rows = _rows(session.directory, "parameter_changes.jsonl")
        assert [(row["name"], row["was"], row["trial_number"]) for row in rows] == [
            (name, None, 3)] * 2
        assert [(row["meaning"]["went"], row["meaning"]["step"]) for row in rows] == [
            (None, None)] * 2


@pytest.mark.parametrize("drain", (6, 7))
def test_a_value_applied_as_a_block_ends_is_judged_by_the_block_its_trial_plays(tmp_path, drain):
    """The review of Task 19, Minor 1: the fixation window set as block `given`'s sixth trial ends
    -- drained before it (6), or one drain later, as the plan moves on (7) -- applies from trial 7,
    in block `bare`, whose conditions give nothing. Both rows are judged by `bare`, as the
    row's `trial_number` says: the run's own window was held, so each keeps its `was` and the way
    it went."""
    session = _session(tmp_path, {drain: [
        {"kind": "set", "by": "jake", "name": "fix_window", "value": 2.5}]},
        plans=GIVEN, plan="given")

    session.run()

    (row,) = _rows(session.directory, "parameter_changes.jsonl")
    assert (row["trial_number"], row["was"], row["now"]) == (7, 2.0, 2.5)
    assert (row["meaning"]["went"], row["meaning"]["step"]) == ("easier", 2.5 - 2.0)
    lines = _rows(session.directory, "trials.jsonl")
    assert [line["block"] for line in lines[6:]] == ["bare"] * 4
    assert [line["params"]["fix_window"] for line in lines[6:]] == [2.5] * 4


def test_the_feed_and_the_moments_word_a_value_over_a_draw_or_conditions_as_such(tmp_path):
    """The review of Task 19, Minor 4 (settling Task 18's Minor 2): where the record writes `was`
    null, the changes feed's line and the revert list's moment say what gave the setting, not a
    value no trial held: "fix_hold its draw → 0.4", "fix_window its conditions → 2.5"."""
    drawn = _session(tmp_path / "a", {2: [
        {"kind": "set", "by": "jake", "name": "fix_hold", "value": 0.4}]})
    drawn.run()
    given = _session(tmp_path / "b", {2: [
        {"kind": "set", "by": "jake", "name": "fix_window", "value": 2.5}]},
        plans=GIVEN, plan="given")
    given.run()

    for session, said in ((drawn, "fix_hold its draw → 0.40"),
                          (given, "fix_window its conditions → 2.50")):
        sets = [line for kind, _, _, line in session._controls if kind == "set"]
        assert [line.startswith(said) for line in sets] == [True], (said, sets)
        assert [moment.said for moment in session._moments] == ["the run's start", said]


#: `GIVEN` with block `given` ended by a time limit of four seconds of trials instead of its counts.
TIMED = GIVEN.replace('Condition("plain", {}, target=3)])', 'Condition("plain", {}, target=3)], '
                      'time_limit_s=4.0)')


@pytest.mark.parametrize("drain", (4, 5))
def test_a_value_applied_as_a_block_ends_by_its_time_limit_is_judged_by_the_next_block(
        tmp_path, drain):
    """The re-review of Task 19, Minor 1: a block ended by its time limit is decided at the
    boundary where the value applies (`Session._playing`), not a few lines after it, so the fixation
    window set as `given` ends -- drained before the trial that ends it, or one drain later -- is
    judged by block `bare`, whose conditions give nothing: the same row both times, `was` the
    run's own 2.0 and the way it went."""
    assert TIMED != GIVEN
    session = _session(tmp_path, {drain: [
        {"kind": "set", "by": "jake", "name": "fix_window", "value": 2.5}]},
        plans=TIMED, plan="given")

    session.run()

    (row,) = _rows(session.directory, "parameter_changes.jsonl")
    lines = _rows(session.directory, "trials.jsonl")
    first = next(line["trial_number"] for line in lines if line["block"] == "bare")
    assert row["trial_number"] == first
    assert (row["was"], row["now"]) == (2.0, 2.5)
    assert (row["meaning"]["went"], row["meaning"]["step"]) == ("easier", 2.5 - 2.0)


#: `TIMED` with `given` sequence-balanced (four trials a condition, two cycles), whose end row's
#: `owed` reads whether the block's time has run out.
TIMED_SB = TIMED.replace('Condition("wide", {"fix_window": 3.0}, target=3), ',
                         'Condition("wide", {"fix_window": 3.0}, target=4), ').replace(
    'Condition("plain", {}, target=3)], time_limit_s=4.0)',
    'Condition("plain", {}, target=4)], order=SequenceBalanced(cycles=2), time_limit_s=4.0)')
SET_WINDOW = {"kind": "set", "by": "jake", "name": "fix_window", "value": 2.5}


def _boundary(tmp_path, script: dict, plans: str) -> dict:
    """What a time-limited block's end leaves that a value applied there must not move: each trial
    line's drumming and aids, the drum switches' blocks in controls.jsonl, and the run end row's
    per-condition counts (`owed` among them)."""
    session = _session(tmp_path, script, plans=plans, plan="given")
    session.run()
    return {
        "lines": [(line["trial_number"], line["block"], line.get("drumming"), line.get("aids"))
                  for line in _rows(session.directory, "trials.jsonl")],
        "controls": [(row["kind"], row.get("block"))
                     for row in _rows(session.directory, "controls.jsonl")],
        "owed": [(row["block"], row["condition"], row["owed"])
                 for row in _rows(session.directory, "runs.jsonl")[-1]["conditions"]],
    }


@pytest.mark.parametrize("act", ({"kind": "drum", "by": "jake", "scope": "block"},
                                 {"kind": "next_block", "by": "jake"}), ids=("drum", "next_block"))
@pytest.mark.parametrize("plans", (TIMED, TIMED_SB), ids=("counted", "sequence_balanced"))
def test_a_value_applied_at_a_time_limit_boundary_moves_nothing_but_its_own_record(
        tmp_path, plans, act):
    """The re-review of Task 19: deciding a block's time-limit end where a value applies must have
    no side effect on the boundary. A value drained before the trial that ends `given`, and a drum
    switch or a move to the next block at the boundary after it, leave the trial lines' drumming,
    the switch's block and the run end row's `owed` as they are without the value (only the change
    row, the feed line and the moment differ). Setting the scheduler's expiry early put the switch
    in block `bare` and read a sequence-balanced block's `owed` as 0."""
    assert plans != GIVEN
    with_value = _boundary(tmp_path / "a", {4: [SET_WINDOW], 5: [act]}, plans)
    without = _boundary(tmp_path / "b", {5: [act]}, plans)

    assert with_value == without
