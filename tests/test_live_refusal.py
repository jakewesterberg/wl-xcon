"""The live refusal of settings no animal can get right (engine build C3's spec §9 and §11; closes
XC-343).

The PI, 2026-10-30, Q10, "Refuse in file and live": "refused in the task file and when set live;
the check judges each concrete combination (per condition, per live change)". The load's half is
`check._impossible_faults`; this is the rest, in `taskd`:
- **live**, one line in the welfare-listed `Session._command`, ahead of `set` (the C3 spec's welfare
  item 2, approved for the design): `Session._impossible` judges the value offered through
  `Session._possible`, against every condition of the run's blocks and the draws in force, and
  raises `Exceeded`, which the listed `except` line turns into a refusal on the feed. A check that
  cannot run refuses the change, never the session. A ceiling's name, a name the task does not
  declare and every value `set` refuses are left to `set`, which says what it always said;
- **at a run's start**, `Session.run`'s backstop beside the record's: a run whose own values leave a
  trial no animal can get right does not start, which covers `wlx run --set` (the outline review's
  I-5);
- and a value outside its declared range is checked again widened with each condition of the run's
  plan and each extreme of a draw in force (`Session._beyond_range`, the C3 spec's §11), once per
  distinct set of values outside their ranges (the outline review's M-11).
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

import _sessions
from _rig import DIRECT, PATH as RIG_FILE
from wl_xcon import stranded, taskd
from wl_xcon.actor import Box
from wl_xcon.bounds import Bounds, Ceiling, Exceeded, Floor
from wl_xcon.cli import _load_task, main
from wl_xcon.dio import Simulated as Card
from wl_xcon.link import SetParameter, Simulated
from wl_xcon.photometry import SRGB, Gray
from wl_xcon.task import FRESH, Block, Condition, Disc, Uniform
from wl_xcon.taskd import Session, SessionSpec
from wl_xcon.welfare import Deployment, Simulated as Pump

#: The wall every session here reads from, plus its frames' seconds (`_session`).
WALL_NOW = 1_700_000_000.0
JAKE = Box("jake")
#: The reference detection task's values, as `tests/test_taskd.py` runs it.
VALUES = {
    "fix_acquisition": 4.0, "fix_hold": 0.3, "response_deadline": 0.6, "target_hold": 0.2,
    "fix_window": 2.0, "target_window": 3.0, "target_x": 10.0, "target_y": 0.0,
    "target_appearance": None, "fix_luminance": 40.0, "target_luminance": 40.0,
}
#: `visual_search`'s looks: a red disc, a green one and a green square for its target; a green
#: disc and a red one for its distractors.
SEARCH = _load_task(Path("tasks/visual_search.py"))
((RED, GREEN, GREEN_SQUARE),) = [p.choices for p in SEARCH.params if p.name == "target_appearance"]
#: `visual_search`'s values, its target red among green, its ring 8° out.
SEARCHED = {"fix_acquisition": 4.0, "fix_hold": 0.3, "response_deadline": 0.6,
            "target_hold": 0.2, "fix_window": 2.0, "object_window": 0.5,
            "array_eccentricity": 8.0, "set_size": 6, "target_index": 0,
            "array_rotation": 0.0, "fix_luminance": 40.0,
            "target_appearance": RED, "distractor_appearance": GREEN}
#: Its blocks: one whose conditions hold the ring at 4°, below its declared 5° ('near' and
#: 'near_again'), at 8° ('far'), or swap the looks ('swapped', a green square among red), and one
#: drawing the ring from 4° to 9°.
RINGS = [Block("set", [Condition("near", {"array_eccentricity": 4.0}, target=2),
                       Condition("near_again", {"array_eccentricity": 4.0,
                                                "array_rotation": 30.0}, target=2),
                       Condition("far", {"array_eccentricity": 8.0}, target=2),
                       Condition("swapped", {"target_appearance": GREEN_SQUARE,
                                             "distractor_appearance": RED}, target=2)]),
         Block("drawn", [Condition("any", {}, target=2)],
               draws={"array_eccentricity": Uniform(4.0, 9.0, repeat=FRESH)})]


def _deadline_task(folder: Path, *, fixed: bool = False, ceiling: bool = False) -> Path:
    """The reference detection task with its target hold bounded by the response deadline, written
    into `folder` as `deadline.py`: the timeout in `verify`, which the reference task writes as 3 s,
    reads `response_deadline`, so a trial whose `target_hold` is longer than its deadline leaves no
    time to answer (XC-343's first combination; the timeout is listed after the hold, so a tie
    leaves time). `fixed` declares `target_hold` not live-editable; `ceiling` declares a setting
    named as the reward ceiling is, `reward_correct`, which nothing reads, with a meaning, as a task
    may. Engine test material, run only in the simulator."""
    text = Path("tasks/fixation_detection.py").read_text()
    edits = [("                On(After(3.0), Outcome.NO_RESPONSE),",
              '                On(After(P("response_deadline")), Outcome.NO_RESPONSE),')]
    if fixed:
        edits.append(('        Param("target_hold", unit="s", low=0.05, high=1.0, start=0.2),',
                      '        Param("target_hold", unit="s", low=0.05, high=1.0, start=0.2,'
                      ' live=False),'))
    if ceiling:
        edits.append(('        Param("target_hold", unit="s", low=0.05, high=1.0, start=0.2',
                      '        Param("reward_correct", unit="mL", low=0.0, high=1.0),\n'
                      '        Param("target_hold", unit="s", low=0.05, high=1.0, start=0.2'))
    for old, new in edits:
        assert text.count(old) == 1, old
        text = text.replace(old, new)
    if ceiling:
        text += (
            "\n\nimport dataclasses as _dataclasses\n"
            "from wl_xcon.task import NEITHER, NOT_DIFFICULTY, Meaning\n"
            "TASK = _dataclasses.replace(TASK, meanings={'reward_correct': Meaning(\n"
            "    NOT_DIFFICULTY, NEITHER, note='named as a ceiling is, read by nothing')})\n"
        )
    path = Path(folder) / "deadline.py"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def _spec(tmp_path, task, **over) -> SessionSpec:
    spec = SessionSpec(
        task=str(task), allocation="tasks/allocation.py", root=tmp_path,
        session_id="2027-01-14_01", subject="A", trials=3, frame_period=1 / 240, seed=1,
        values=dict(VALUES),
        bounds=Bounds(
            subject="A",
            ceilings={"reward_correct": Ceiling(value=0.15, maximum=0.40, unit="mL"),
                      "out_of_cage": Ceiling(value=800.0, maximum=100_000.0, unit="s")},
            minima={"daily_fluid": Floor(value=250.0, unit="mL")},
        ),
        already_delivered_today=0.0, deployment=Deployment.RIG_FIXED, geometry=DIRECT,
        session_kind="training", calibration=SRGB,
    )
    for name, value in over.items():
        setattr(spec, name, value)
    return spec


def _session(spec, link=None) -> Session:
    """On the simulators, its wall following its frames from `WALL_NOW`, the animal out of its
    cage and its head fixed then, as `tests/test_taskd.py`'s sessions are."""
    session = Session(spec, card=Card(), pump=Pump(),
                      link=link if link is not None else Simulated())
    session.wall_clock = lambda: WALL_NOW + session.now()
    session.left_cage(at=WALL_NOW)
    session.head_fixed(at=session.wall_now())
    return session


class _Drained(Simulated):
    """A link that queues `script[n]` as the `n`th drain begins: the commands reach the loop at
    the boundary before trial `n`."""

    def __init__(self, script):
        super().__init__()
        self.script, self.drains = dict(script), 0

    def drain(self) -> list:
        self.drains += 1
        for command in self.script.get(self.drains, ()):
            self.queue(command)
        return super().drain()


def _rows_at(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def _rows(session: Session, name: str) -> list[dict]:
    return _rows_at(session.directory / name)


def _broken(monkeypatch) -> None:
    """`check.impossible`, as `taskd` calls it, raising for every live change and judging a run's
    start as it does: a live change always holds a name (`held`), a run's start none."""
    real = taskd.impossible

    def broken(task, blocks, values, *, held=frozenset(), ranges=None):
        if held:
            raise ZeroDivisionError("division by zero")
        return real(task, blocks, values, held=held, ranges=ranges)

    monkeypatch.setattr(taskd, "impossible", broken)


def test_a_live_value_that_makes_some_conditions_trial_impossible_is_refused_naming_them(tmp_path):
    """The spec's §9, live: a response deadline of 0.5 s leaves conditions 'slow' and 'slower',
    whose target holds are 0.8 s and 0.9 s, no time to answer, and 'quick' its 0.2 s: refused at
    once, naming the two, the values and the fix, through `Session._command`'s listed `except` line,
    so the session runs on and the deadline stands. One of 0.05 s, below its declared 0.1 s, leaves
    no condition time: refused by the same check, ahead of `set`, so no warning that it is outside
    its range is written (the outline review's I-1). 1.0 s leaves each its time and is staged and
    applied as before."""
    blocks = [Block("b", [Condition("quick", {"target_hold": 0.2}, target=2),
                          Condition("slow", {"target_hold": 0.8}, target=2),
                          Condition("slower", {"target_hold": 0.9}, target=2)])]
    link = _Drained({2: [SetParameter(name="response_deadline", value=0.5, by=JAKE)],
                     3: [SetParameter(name="response_deadline", value=0.05, by=JAKE)],
                     4: [SetParameter(name="response_deadline", value=1.0, by=JAKE)]})
    session = _session(_spec(tmp_path, _deadline_task(tmp_path), blocks=blocks,
                             values={**VALUES, "response_deadline": 2.0}), link)

    session.run()

    assert session.stop_kind == "completed"
    some, every = session.refusals
    assert some[:2] == every[:2] == ("response_deadline", JAKE)
    assert some[2].startswith(
        "'response_deadline' at 0.5 is refused, and the previous value stands: it would leave "
        "trials no animal can get right, in b: slow, b: slower (impossible-trial): block 'b', "
        "condition 'slow': state 'verify' ends the trial NO_RESPONSE after `response_deadline`, "
        "0.5 s, while its 'target' hold takes `target_hold`, 0.8 s: the hold starts only when the "
        "gaze arrives, so it never finishes and no answer can be paid (XC-343); give the timeout "
        "more than 0.8 s, ")
    assert "; block 'b', condition 'slower': " in some[2] and "quick" not in some[2]
    assert every[2].startswith("'response_deadline' at 0.05 is refused, and the previous value "
                               "stands: it would leave trials no animal can get right, in b: "
                               "quick, b: slow, b: slower (impossible-trial): ")
    assert _rows(session, "warnings.jsonl") == []
    assert session.spec.values["response_deadline"] == 1.0
    (row,) = _rows(session, "parameter_changes.jsonl")
    assert (row["name"], row["was"], row["now"]) == ("response_deadline", 2.0, 1.0)


@pytest.mark.parametrize("check", ["working", "broken"])
def test_the_live_refusal_line_lets_set_refuse_what_it_always_refused_and_never_raises(
    tmp_path, monkeypatch, check
):
    """Review Focus 5 (the outline review's I-1): the line runs ahead of `set` and leaves to it all
    `set` always refused, each refused by `set`'s own sentence, never the live refusal's, whether
    the check works or cannot run: a word for a number, `True`, `nan`, a ceiling past its maximum
    (named as a setting the task declares too, which is never judged: a reward size never passes
    through the check), a name the task does not declare, a setting of another task that no
    structure of this one declares, a choice the setting does not offer, and a setting declared not
    live-editable at a value that would leave no time to answer. A ceiling's value inside its
    maximum is staged and applied as before. Nothing raises past the listed `except` line: the
    session runs to its end."""
    task = _deadline_task(tmp_path, fixed=True, ceiling=True)
    offered = [("fix_hold", "long"), ("fix_hold", True), ("fix_hold", float("nan")),
               ("reward_correct", 0.9), ("fix_holdd", 0.4), ("set_size", 6),
               ("target_appearance", Disc(size=2.0, color=Gray(40.0))), ("target_hold", 0.9)]
    probe = Session(_spec(tmp_path / "probe", task), card=Card(), pump=Pump())
    said = []
    for name, value in offered:
        with pytest.raises(Exceeded) as refused:
            probe.set(name, value, by=JAKE)
        said.append((name, JAKE, str(refused.value)))
    if check == "broken":
        _broken(monkeypatch)
    link = _Drained({2: [SetParameter(name=name, value=value, by=JAKE)
                         for name, value in offered]
                     + [SetParameter(name="reward_correct", value=0.2, by=JAKE)]})
    session = _session(_spec(tmp_path, task), link)

    session.run()

    assert session.stop_kind == "completed"
    assert session.refusals == said
    assert session.spec.bounds.value("reward_correct") == 0.2
    assert session.spec.values["fix_hold"] == 0.3 and session.spec.values["target_hold"] == 0.2


def test_a_check_that_cannot_run_refuses_the_change_and_the_session_runs_on(tmp_path, monkeypatch):
    """The C3 plan's call 26, "The live refusal fails closed": a check that raises refuses the
    change, saying it could not run, never the session, which runs to its end; a ceiling's value,
    never judged, is staged and applied as before, though the task declares a setting of its
    name."""
    _broken(monkeypatch)
    link = _Drained({2: [SetParameter(name="fix_hold", value=0.5, by=JAKE),
                         SetParameter(name="reward_correct", value=0.2, by=JAKE)]})
    session = _session(_spec(tmp_path, _deadline_task(tmp_path, ceiling=True)), link)

    session.run()

    assert session.stop_kind == "completed"
    assert session.refusals == [(
        "fix_hold", JAKE,
        "'fix_hold' at 0.5 is refused, and the previous value stands: the check for trials no "
        "animal can get right could not be run (ZeroDivisionError: division by zero)")]
    assert session.spec.values["fix_hold"] == 0.3
    assert session.spec.bounds.value("reward_correct") == 0.2


def test_a_live_look_that_some_conditions_distractors_have_is_refused_naming_them(tmp_path):
    """The spec's §9, live, XC-343's second combination: a green disc as `visual_search`'s target,
    among the green discs every condition but 'swapped' shows, leaves no object standing out on
    their trials; 'swapped' sets its own target, which the person's value beats, among red. Refused,
    naming the four and saying the look as the console's feed says a choice (`cli._shown`)."""
    link = _Drained({2: [SetParameter(name="target_appearance", value=GREEN, by=JAKE)]})
    session = _session(_spec(tmp_path, "tasks/visual_search.py", values=dict(SEARCHED),
                             blocks=RINGS), link)

    session.run()

    assert session.stop_kind == "completed"
    (refusal,) = session.refusals
    assert refusal[:2] == ("target_appearance", JAKE)
    assert refusal[2].startswith(
        f"'target_appearance' at {GREEN} is refused, and the previous value stands: it would "
        f"leave trials no animal can get right, in set: near, set: near_again, set: far, drawn: "
        f"any (impossible-trial): block 'set', conditions 'near', 'near_again', 'far': array "
        f"'search''s target, `target_appearance`, and its distractors, `distractor_appearance`, "
        f"can look the same (")
    assert "swapped" not in refusal[2] and session.spec.values["target_appearance"] == RED


def test_a_live_look_a_cued_arrays_distractors_have_is_accepted(tmp_path):
    """The PI, 2026-10-31, on the engine C3 plan's Appendix B, item 17, "Refuse only odd-one-out
    tasks (Recommended)": live, a change the look checks would refuse on an array found by its
    look is accepted on one a cue names the target of (`Array.found_by` `"cue"`). The live check
    asks for refusals alone and carries no warning back (the C3 plan's call 45): the load and the
    run's start said it. `visual_search` written with its array cued takes the green target the
    test above refuses, from the next trial."""
    text = Path("tasks/visual_search.py").read_text()
    written = '        phase=P("array_rotation"),\n    ),\n)'
    assert text.count(written) == 1
    cued = tmp_path / "cued_search.py"
    cued.write_text(text.replace(
        written, '        phase=P("array_rotation"),\n        found_by="cue",\n    ),\n)'))
    link = _Drained({2: [SetParameter(name="target_appearance", value=GREEN, by=JAKE)]})
    session = _session(_spec(tmp_path, str(cued), values=dict(SEARCHED), blocks=RINGS), link)

    session.run()

    assert session.stop_kind == "completed"
    assert session.refusals == []
    assert session.spec.values["target_appearance"] == GREEN
    assert [kind for kind, _, _, _ in session.controls if kind == "warning"] == []


def test_a_value_outside_its_range_is_rechecked_with_each_condition_and_draw_once_per_outside_set(
    tmp_path, monkeypatch
):
    """The spec's §11 ("Live, `Session._beyond_range` learns conditions and draws"; call 27):
    `visual_search` at 13 objects, past its 12, is no fault on its 8° ring alone, but conditions
    'near' and 'near_again', holding the ring at 4°, below its 5°, crowd it, and so does block
    'drawn', drawing the ring from 4°. Refused, naming each place, no warning written. A fixation
    hold of 2.5 s, past its 2 s, breaks nothing anywhere: staged, with its warning as the session's
    own values make it and the ring's at 4° naming where it is met. Each is checked once for the
    session's own values and once for the set of values outside their ranges the three places
    share (the outline review's M-11), never once per condition or extreme."""
    checked = []
    real = taskd.beyond_range

    def counted(task, these, *args, **kwargs):
        checked.append((these["set_size"], these["fix_hold"], these["array_eccentricity"]))
        return real(task, these, *args, **kwargs)

    monkeypatch.setattr(taskd, "beyond_range", counted)
    link = _Drained({2: [SetParameter(name="set_size", value=13, by=JAKE)],
                     3: [SetParameter(name="fix_hold", value=2.5, by=JAKE)]})
    session = _session(_spec(tmp_path, "tasks/visual_search.py", values=dict(SEARCHED),
                             blocks=RINGS), link)

    session.run()

    assert session.stop_kind == "completed"
    places = ("(on the trials of block 'set', condition 'near'; block 'set', condition "
              "'near_again'; block 'drawn', condition 'any', block 'drawn''s draw of "
              "'array_eccentricity' at 4)")
    (refusal,) = session.refusals
    assert refusal[:2] == ("set_size", JAKE)
    assert refusal[2] == (
        "'set_size' at 13 is outside its declared range, and with the range widened to it the "
        "load-time checks refuse it: crowded-array: with 'array_eccentricity' at 4, 'set_size' at "
        "13, outside its declared range: array 'search' can put 13 objects on a 4° ring, 1.91° "
        "apart, with windows of 1° radius; adjacent objects would overlap and a saccade to one "
        f"would be scored against another {places}; the previous value stands")
    assert checked == [(13, 0.3, 8.0), (13, 0.3, 4.0), (6, 2.5, 8.0), (6, 2.5, 4.0)]
    assert [(row["code"], row["by"]["name"], row["detail"]) for row in
            _rows(session, "warnings.jsonl")] == [
        ("outside-range", "jake",
         "'fix_hold' is 2.5 s, outside the [0.05, 2.0] the task declares, so the task was not "
         "designed for it: its load-time checks were proved only over its declared range, and "
         "were run again with the range widened to 2.5"),
        ("outside-range", "jake",
         "'array_eccentricity' is 4 deg, outside the [5.0, 14.0] the task declares, so the task "
         "was not designed for it: its load-time checks were proved only over its declared range, "
         f"and were run again with the range widened to 4 {places}"),
    ]
    assert session.spec.values["set_size"] == 6 and session.spec.values["fix_hold"] == 2.5

    # Where a person holds the ring, no condition or draw moves it; and a live range's extreme is
    # its own.
    values = {**session.spec.values, "set_size": 13}
    session._edited = frozenset({"array_eccentricity"})
    assert session._outside_sets("set_size", values) == [(values, [])]
    session._edited = frozenset()
    session._ranges = {("block", "drawn", "array_eccentricity"): (Uniform(3.0, 9.0), 5)}
    assert [places for _, places in session._outside_sets("set_size", values)][-1] == [
        "block 'drawn', condition 'any', block 'drawn''s draw of 'array_eccentricity' at 3"]


def test_wlx_run_given_values_that_make_an_impossible_trial_does_not_start(tmp_path, capsys):
    """The outline review's I-5: `wlx run` takes no pre-flight (XC-159), so its `--set` values were
    judged by nothing, and a target hold of 3.5 s against the 3 s the reference task's `verify`
    state waits ran trials no animal could get right. `Session.run`'s backstop, beside the
    record's, refuses the run before its first trial, naming the condition, the values and the fix;
    no trial and no run row is written. **And it is refused before the session opens** (the C3
    plan's Task 19 review, Important 2): no "out of cage" is said, no departure is marked and
    nothing is left under the root, so `stranded.find` lists no session. Refused by the backstop
    alone, after the departure, it left one stranded, as XC-415's unplaced value did."""
    argv = [
        "run", "tasks/fixation_detection.py",
        "--rig", RIG_FILE, "--view", "direct", "--kind", "training", "--accept-warnings",
        "--allocation", "tasks/allocation.py", "--bounds", "tasks/reference_bounds.py",
        "--root", str(tmp_path), "--session-id", "2027-01-14_01", "--subject", "REFERENCE",
        "--out-of-cage-at", time.strftime("%H:%M"), "--delivered-today", "0", "--trials", "2",
        "--set", "fix_acquisition=4.0", "--set", "fix_hold=0.3", "--set", "response_deadline=0.6",
        "--set", "target_hold=3.5", "--set", "fix_window=2.0", "--set", "target_window=3.0",
        "--set", "target_x=10.0",
    ]

    with pytest.raises(SystemExit) as refused:
        main(argv)

    assert str(refused.value) == (
        "task refused, session not started: its starting values leave trials no animal can get "
        "right:\n"
        "  impossible-trial: block 'session', condition 'session': state 'verify' ends the trial "
        "NO_RESPONSE after 3 s, while its 'target' hold takes `target_hold`, 3.5 s: the hold "
        "starts only when the gaze arrives, so it never finishes and no answer can be paid "
        "(XC-343); give the timeout more than 3.5 s, or hold in a state of its own bounded longer, "
        "as the reference tasks hold their target")
    folder = tmp_path / "2027-01-14_01" / "xcon"
    assert _rows_at(folder / "trials.jsonl") == [] and _rows_at(folder / "runs.jsonl") == []
    assert "out of cage" not in capsys.readouterr().out
    assert list(tmp_path.iterdir()) == []
    assert stranded.find(tmp_path) == []


def _wlx_run(tmp_path: Path, task: str, *sets: str, plan: str | None = None) -> list[str]:
    """`wlx run`'s argv for `task` with the reference detection task's values, `sets` over them."""
    values = {"fix_acquisition": "4.0", "fix_hold": "0.3", "response_deadline": "0.6",
              "target_hold": "0.2", "fix_window": "2.0", "target_window": "3.0",
              "target_x": "10.0"}
    values |= dict(item.split("=") for item in sets)
    return [
        "run", task, *(["--plan", plan] if plan else []),
        "--rig", RIG_FILE, "--view", "direct", "--kind", "training", "--accept-warnings",
        "--allocation", "tasks/allocation.py", "--bounds", "tasks/reference_bounds.py",
        "--root", str(tmp_path / "root"), "--session-id", "2027-01-14_01",
        "--subject", "REFERENCE", "--out-of-cage-at", time.strftime("%H:%M"),
        "--delivered-today", "0", "--trials", "2",
        *[arg for name, value in values.items() for arg in ("--set", f"{name}={value}")],
    ]


def test_wlx_run_of_a_plan_judges_the_conditions_its_factors_make_before_it_starts(
        tmp_path, capsys):
    """The re-review of Task 19: the check beside `unplaced` in `wlx run` reads the blocks of the
    plan named (`check.impossible` expands each factorial itself). A response deadline of 0.15 s
    against a 0.2 s target hold is refused naming the conditions the factors make, before any
    departure, with no "out of cage", nothing under the root and no stranded session. The plan
    branch is pinned: judged as the plain run, the refusal would name block 'session' instead."""
    task = _sessions.varied_task(tmp_path / "tasks", name="planned", plans=(
        '{"p": Plan([Block("grid", [], factorial=Factorial({"target_x": (-10.0, 10.0)}, '
        'target=1))])}'))
    text = task.read_text()
    old = "                On(After(3.0), Outcome.NO_RESPONSE),"
    assert text.count(old) == 1
    task.write_text(text.replace(
        old, '                On(After(P("response_deadline")), Outcome.NO_RESPONSE),'))

    with pytest.raises(SystemExit) as refused:
        main(_wlx_run(tmp_path, str(task), "response_deadline=0.15", plan="p"))

    assert str(refused.value).startswith(
        "task refused, session not started: its starting values leave trials no animal can get "
        "right:\n  impossible-trial: block 'grid', conditions 'target_x=-10.0', "
        "'target_x=10.0': state 'verify' ends the trial NO_RESPONSE after `response_deadline`, "
        "0.15 s, while its 'target' hold takes `target_hold`, 0.2 s")
    assert "out of cage" not in capsys.readouterr().out
    assert not (tmp_path / "root").exists() or list((tmp_path / "root").iterdir()) == []
    assert stranded.find(tmp_path / "root") == []


@pytest.mark.parametrize("value", ("abc", "nan", "inf", "-inf"))
def test_wlx_run_refuses_a_value_its_setting_cannot_hold_before_the_departure(
        tmp_path, capsys, value):
    """The re-review of Task 19, out-of-scope 2: `--set target_hold=abc` passed every refusal, marked
    the departure and died with a `TypeError` in the first trial; `nan` and `inf` ran. A numeric
    setting takes a number that is real, as `Session.set` and `bounds._finite` hold a live value
    to: refused before the session opens, so no "out of cage", nothing under the root, no stranded
    session."""
    with pytest.raises(SystemExit) as refused:
        main(_wlx_run(tmp_path, "tasks/fixation_detection.py", f"target_hold={value}"))

    said = str(refused.value)
    assert said.startswith("task refused, session not started, nothing recorded: --set "
                           "'target_hold' ")
    assert ("takes a number (s)" in said) if value == "abc" else ("not a real number" in said)
    assert "out of cage" not in capsys.readouterr().out
    assert not (tmp_path / "root").exists()
    assert stranded.find(tmp_path / "root") == []


def test_possible_judges_a_hand_back_a_range_and_a_whole_revert(tmp_path):
    """`Session._possible`, as the C3 plan's Tasks 13 and 14 call it for a hand-back, a live range
    and a revert, after a run of the deadline task: the run's values with the values staged ahead
    over them (a ceiling's left out), the names a person holds beating conditions and draws, and the
    ranges changed live with their change ids left out; then the change offered. A hand-back puts
    the run's own value back and ends the hold; a range of `None` restores the declared draw."""
    drawn = ("block", "drawn", "target_hold")
    wide = Uniform(0.1, 0.9, repeat=FRESH)
    blocks = [Block("set", [Condition("quick", {"target_hold": 0.2}, target=2),
                            Condition("slow", {"target_hold": 0.8}, target=2)]),
              Block("drawn", [Condition("any", {}, target=2)],
                    draws={"target_hold": Uniform(0.1, 0.3, repeat=FRESH)})]
    session = _session(_spec(tmp_path, _deadline_task(tmp_path), blocks=blocks,
                             values={**VALUES, "response_deadline": 2.0}))
    session.run()
    assert session._possible() is None

    value = session._possible({"response_deadline": 0.5})
    assert value.startswith("it would leave trials no animal can get right, in set: slow "
                            "(impossible-trial): block 'set', condition 'slow': ")

    session._staged = [("reward_correct", 0.15, 0.2, JAKE, True),
                       ("response_deadline", 2.0, 0.5, JAKE, False)]
    assert session._possible() == value
    session._staged = []

    session.spec.values["response_deadline"] = 0.85
    session._edited = frozenset({"response_deadline"})
    assert session._possible() is None
    assert session._possible({"target_hold": 0.9}).startswith(
        "it would leave trials no animal can get right, in set: quick, set: slow, drawn: any "
        "(impossible-trial): ")
    ranged = session._possible(ranges={drawn: wide})
    assert ranged.startswith("it would leave trials no animal can get right, in drawn: any "
                             "(impossible-trial): block 'drawn', condition 'any': ")
    session._ranges = {drawn: (wide, 7)}
    assert session._possible() == ranged
    assert session._possible(ranges={drawn: None}) is None

    session.spec.values.update(response_deadline=0.5, target_hold=0.2)
    session._ranges = {}
    session._edited = frozenset({"response_deadline", "target_hold"})
    assert session._possible() is None
    assert session._possible(handed=frozenset({"target_hold"})) == value
    assert session._possible(handed=frozenset({"response_deadline"})) is None
    session.spec.values["response_deadline"] = 2.0
    session._edited = frozenset({"response_deadline"})
    session._run_values["response_deadline"] = 0.5
    assert session._possible() is None
    assert session._possible(handed=frozenset({"response_deadline"})) == value

    assert session._possible({"response_deadline": 0.85}, handed=frozenset({"target_hold"}),
                             ranges={drawn: wide}) == ranged
    assert session._possible({"response_deadline": 0.85},
                             handed=frozenset({"target_hold"})) is None


@pytest.mark.parametrize("low, high, draw, shown", [
    (0.0, 360.0, "Uniform(-45.0, 45.0, repeat=FRESH)", ()),
    (-180.0, 180.0, "Uniform(-45.0, 45.0, repeat=FRESH)", ()),
    (0.0, 180.0, "Uniform(-45.0, 45.0, repeat=FRESH)", ("-45",)),
    (0.0, 90.0, "Uniform(100.0, 120.0, repeat=FRESH)", ("100", "120")),
    (-30.0, 30.0, "Uniform(-45.0, 45.0, repeat=FRESH)", ("-45", "45")),
])
def test_a_live_value_outside_its_range_widens_a_direction_draw_as_the_runs_start_does(
    tmp_path, low, high, draw, shown
):
    """The review of Task 12 (Important 1; the controller's ruling that the live check widens a
    draw by the one rule a run's start does), with the final whole-branch review's Minor 1 (the
    controller's revised ruling): a direction draw is judged against its declared range on the
    circle by arc containment. `Uniform(-45, 45)`, declared [0, 360] or in signed terms [-180,
    180], is inside the whole turn, so a person's `fix_hold` of 2.5, outside its own, writes that
    setting's warning alone and no `target_dir` row. Declared [0, 180] it reaches past at -45, as
    drawn; declared [-30, 30], at -45 and 45; and `Uniform(100, 120)`, declared [0, 90], is wholly
    past it, at 100 and 120. Each the start warns and the live check says too, once, and no
    `direction-outside-0-360` row (the load suppresses that warning for a drawn direction). A
    setting that is no direction keeps its live warning."""
    from test_draws_in_runs import _directed, _right, _rows as _run_rows
    from test_draws_in_runs import _session as _run_session, _spec as _run_spec
    from wl_xcon import preflight
    from wl_xcon.cli import _load_allocation
    from wl_xcon.photometry import SRGB as _SRGB

    path = _directed(tmp_path, f'{{"target_dir": {draw}}}',
                     plans='{"p": Plan([Block("drawn", [Condition("c", {}, target=6)])])}')
    text = path.read_text()
    old = 'Param("target_dir", unit="deg", low=-180.0, high=180.0, start=0.0)'
    assert text.count(old) == 1
    path.write_text(text.replace(old, f'Param("target_dir", unit="deg", low={low}, high={high},'
                                      f' start=0.0)'))
    task = _load_task(path)
    start = [f for f in preflight.beyond(task, {}, _load_allocation(Path("tasks/allocation.py")),
                                         DIRECT, _SRGB, None, plan="p")
             if "target_dir" in f.detail]
    link = _Drained({2: [SetParameter(name="fix_hold", value=2.5, by=JAKE)]})
    session = _run_session(_run_spec(tmp_path, path, plan="p", trials=3), link,
                           world=lambda trial, values, index: _right(values))

    session.run()

    rows = _run_rows(session, "warnings.jsonl")
    live = [row for row in rows if "target_dir" in row["detail"]]
    assert [row["code"] for row in live] == [f.code for f in start]
    assert [row["code"] for row in rows if "fix_hold" in row["detail"]] == ["outside-range"]
    assert [row["code"] for row in live] == ["outside-range"] * len(shown)
    for details in ([f.detail for f in start], [row["detail"] for row in live]):
        assert [f"target_dir' is {end} deg" in detail
                for detail, end in zip(details, shown)] == [True] * len(shown)


def _choosing_task(folder: Path) -> Path:
    """The reference detection task with one more setting of number choices, `mode`, which nothing
    reads, written into `folder` as `choosing.py`. Engine test material, run only in the
    simulator."""
    text = Path("tasks/fixation_detection.py").read_text()
    old = '        Param("target_hold", unit="s", low=0.05, high=1.0, start=0.2'
    assert text.count(old) == 1
    path = Path(folder) / "choosing.py"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.replace(
        old, '        Param("mode", unit="mode", choices=(1.0, 2.0), start=1.0),\n' + old) + (
        "\n\nimport dataclasses as _dataclasses\n"
        "from wl_xcon.task import NEITHER, NOT_DIFFICULTY, Meaning\n"
        "TASK = _dataclasses.replace(TASK, meanings={**TASK.meanings, 'mode': Meaning(\n"
        "    NOT_DIFFICULTY, NEITHER, note='read by nothing')})\n"))
    return path


@pytest.mark.parametrize("assignment", ("target_appearance=square", "target_appearance=1.0",
                                        "mode=fast", "mode=3.0"))
def test_wlx_run_refuses_a_value_outside_a_settings_choices_before_the_departure(
        tmp_path, capsys, assignment):
    """The re-review of Task 19, out-of-scope 3: a `--set` word or number for a setting of choices
    passed every refusal in `wlx run`, was recorded though it is none of its choices, and on a
    renderer path faulted after the departure (`NotYetDrawable`), stranding the session. It is
    refused as `Session.set` refuses a live value (it may only be one of its choices), before the
    session opens: no "out of cage", nothing under the root, no stranded session. A choice of the
    setting still runs (the next test)."""
    task = _choosing_task(tmp_path / "tasks")

    with pytest.raises(SystemExit) as refused:
        main(_wlx_run(tmp_path, str(task), assignment))

    name, _, value = assignment.partition("=")
    said = str(refused.value)
    assert said.startswith(f"task refused, session not started, nothing recorded: --set "
                           f"{name!r} may only be one of (")
    assert said.endswith(f"; {(float(value) if value[0].isdigit() else value)!r} is not")
    assert "out of cage" not in capsys.readouterr().out
    assert not (tmp_path / "root").exists()
    assert stranded.find(tmp_path / "root") == []


def test_wlx_run_runs_with_a_value_that_is_one_of_a_settings_choices(tmp_path, capsys):
    """A choice of the setting (`mode=2.0`) is not refused: the run starts and the departure is
    marked, as for any run."""
    task = _choosing_task(tmp_path / "tasks")

    main(_wlx_run(tmp_path, str(task), "mode=2.0"))

    assert "out of cage" in capsys.readouterr().out
