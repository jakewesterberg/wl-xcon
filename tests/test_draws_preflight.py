"""A run's pre-flight knows what its task draws and refuses a start no animal can get right;
`wlx run` draws a fresh seed when given none (engine build C3's spec §2, §9 and §11).

A run's pre-flight holds its starting values to the task's declarations (`preflight.values`):
a number the task uses that nothing gives fails the run. A value outside its declared range is
checked again with the range widened to it (`preflight.beyond`; the PI, 2026-10-11, XC-352's
D2): a warning, refused only where it breaks the run. Engine build C3 lets a task draw a value
each trial, and the pre-flight learns it. **A number a draw gives is given** (the spec's call
24), so no run is refused for a number "nothing gives". **A draw that can reach past its
setting's declared range is checked widened to each end it reaches** (its §11): warned, and
refused where it breaks the run, each finding naming where and which draw. **§9's three
combinations no animal can answer are judged at the run's own starting values** (the PI,
2026-10-30, Q10, "Refuse in file and live"; the C3 plan's review, I-5), so a start that makes
one fails the starting values item. And `wlx run`, which gave every run seed 1 unless told
otherwise, draws a fresh seed as `wlx taskd`'s service does (TSK-06: "a fresh seed per run,
recorded").
"""

from __future__ import annotations

import dataclasses
import json
import time
from pathlib import Path

import pytest

import _sessions
from _rig import DIRECT, PATH as RIG_FILE
from wl_xcon import check, preflight, service, variation
from wl_xcon.check import CUED, IMPOSSIBLE, check_task
from wl_xcon.cli import _load_allocation, _load_task, main
from wl_xcon.photometry import SRGB, Gray
from wl_xcon.task import (
    BY_CONDITIONS, FRESH, OWED, SAME, After, Array, Block, Condition, Counting, Disc, Factorial,
    Listed, NonAging, ObjectWindows, On, Outcome, P, Param, Plan, Polar, SaccadeTo, Show, State,
    Stimulus, Task, Trial, TruncatedNormal, Uniform, Weighted,
)

ALLOCATION = _load_allocation(Path("tasks/allocation.py"))
TASK = Path("tasks/fixation_detection.py")


def _task(**changes) -> Task:
    """The reference detection task, its task object given `changes`."""
    return dataclasses.replace(_load_task(TASK), **changes)


def _unstarted(task: Task, name: str) -> Task:
    """`task` with no starting value for `name`, in every structure."""
    def bare(param: Param) -> Param:
        return dataclasses.replace(param, start=None) if param.name == name else param

    return dataclasses.replace(task, structures={
        key: dataclasses.replace(structure, params=[bare(p) for p in structure.params])
        for key, structure in task.structures.items()})


def _deadline_bound(task: Task) -> Task:
    """`task` with its target hold's state bounded by the response deadline, where the reference
    task bounds it by 3 s, longer than any target hold it allows. It loads, warned `hold-cut-short`
    over the declared ranges, and makes a trial no animal can get right only at values where the
    deadline always beats the hold."""
    trial = task.structures["detection"]
    states = [
        dataclasses.replace(state, go=[
            dataclasses.replace(edge, guard=After(P("response_deadline")))
            if isinstance(edge.guard, After) and edge.guard.seconds == 3.0 else edge
            for edge in state.go])
        if state.name == "verify" else state
        for state in trial.states
    ]
    return dataclasses.replace(
        task, structures={"detection": dataclasses.replace(trial, states=states)})


def _blocking(task: Task) -> list:
    """What refuses `task` at load."""
    return [f for f in check_task(task, ALLOCATION, geometry=DIRECT, calibration=SRGB)
            if f.blocking]


def test_a_number_a_draw_gives_counts_as_given():
    """The spec's call 24: a number a draw gives is given -- in the plain run, the task's draw;
    in a plan's, its block's own draw or the task's, a condition's own range, a factor's levels --
    and a block where nothing gives it still fails, naming it, as before engine build C3. A
    block that sets the task's draw aside for its conditions (`BY_CONDITIONS`) gives it only
    where they do. A factorial is expanded, so the structure its conditions play needs its
    numbers too."""
    bare = _unstarted(_task(), "fix_hold")
    drawn = Uniform(0.2, 0.4, repeat=FRESH)
    plain = dataclasses.replace(bare, draws={"fix_hold": drawn})
    trial = bare.structures["detection"]
    cued = dataclasses.replace(
        trial,
        params=[*trial.params, Param("cue_delay", unit="s", low=0.0, high=1.0)],
        windows=[dataclasses.replace(trial.windows[0], radius=P("cue_delay")),
                 *trial.windows[1:]],
    )
    factors = Factorial({"fix_hold": (0.2, 0.4)}, structure="cued")
    plans = {
        "block": Plan([Block("b", [Condition("c", {}, target=1)], draws={"fix_hold": drawn})]),
        "own": Plan([Block("b", [Condition("c", {"fix_hold": drawn}, target=1)])]),
        "factor": Plan([Block("b", [], factorial=Factorial({"fix_hold": (0.2, 0.4)}))]),
        "cued": Plan([Block("b", [], factorial=factors)]),
        "cued and drawn": Plan([Block("b", [], factorial=factors,
                                      draws={"cue_delay": Uniform(0.1, 0.3, repeat=SAME)})]),
        "half": Plan([Block("b", [Condition("c", {}, target=1)], draws={"fix_hold": drawn}),
                      Block("bare", [Condition("d", {}, target=1)])]),
        "aside": Plan([Block("b", [Condition("c", {"fix_hold": 0.3}, target=1),
                                   Condition("d", {}, target=1)],
                             draws={"fix_hold": BY_CONDITIONS})]),
    }
    task = dataclasses.replace(bare, structures={"detection": trial, "cued": cued}, plans=plans)
    drawing = dataclasses.replace(task, draws={"fix_hold": drawn})

    assert preflight.values(plain, {}).result == "pass", preflight.values(plain, {}).said
    unset = preflight.values(bare, {})
    assert unset.result == "fail"
    assert "'fix_hold' is used by the task and has no starting value" in unset.said
    assert {name: preflight.values(task, {}, plan=name).result for name in plans} == {
        "block": "pass", "own": "pass", "factor": "pass", "cued": "fail",
        "cued and drawn": "pass", "half": "fail", "aside": "fail"}
    assert "'cue_delay' is used by the task and has no starting value" in preflight.values(
        task, {}, plan="cued").said
    assert "'fix_hold' is used by the task and has no starting value" in preflight.values(
        task, {}, plan="half").said
    assert preflight.values(drawing, {}, plan="half").result == "pass", "the task's draw"
    aside = preflight.values(drawing, {}, plan="aside")
    assert aside.result == "fail", "set aside for conditions that do not all give it"
    assert "'fix_hold' is used by the task and has no starting value" in aside.said


def test_a_place_a_draw_gives_is_given_and_a_block_nothing_places_is_still_refused(tmp_path):
    """The ruling on the C3 plan's prospect run (Call 24 carried to places, beside the PI's "Refuse
    to start", XC-415): a setting that places the target and has no start is given where a draw
    gives it each trial -- the task's draw in the plain run, the block's own or the task's in a
    plan's block (`variation.in_force`) -- so the run is not refused at its start; a block whose
    conditions and draws give it no place still is, naming where."""
    polar = _load_task(_sessions.polar_task(tmp_path))
    places = Weighted((Polar(8.0, 0.0), Polar(8.0, 45.0)), (1, 1), repeat=FRESH)
    drawn = dataclasses.replace(polar, draws={"target_pos": places})
    plans = {
        "drawn": Plan([Block("b", [Condition("c", {}, target=1)],
                             draws={"target_pos": places})]),
        "given": Plan([Block("b", [Condition("c", {"target_pos": Polar(8.0, 0.0)}, target=1)])]),
        "bare": Plan([Block("b", [Condition("c", {"target_pos": Polar(8.0, 0.0)}, target=1)]),
                      Block("none", [Condition("d", {}, target=1)])]),
    }
    planned = dataclasses.replace(polar, plans=plans)
    starts = {param.name: param.start for param in polar.params if param.start is not None}

    assert [name for name, _ in check.unplaced(polar, starts)] == ["target_pos"]
    assert check.unplaced(drawn, starts) == []
    assert preflight.values(drawn, {}).result == "pass", preflight.values(drawn, {}).said
    assert {name: [n for n, _ in check.unplaced(planned, starts, plan.blocks)]
            for name, plan in plans.items()} == {"drawn": [], "given": [], "bare": ["target_pos"]}
    assert preflight.values(planned, {}, plan="drawn").result == "pass"
    refused = preflight.values(planned, {}, plan="bare")
    assert refused.result == "fail"
    assert "has no value in condition 'd' of block 'none'" in refused.said


def test_the_preflight_judges_places_over_a_factorials_generated_conditions(tmp_path):
    """The ruling on the C3 plan's prospect run: `preflight.values` hands `check.unplaced` the plan
    as the run plays it, each factorial expanded (`_played`), as `Session.run`'s backstop does. A
    factorial whose levels place the target starts; one whose generated conditions place nothing,
    its target given no value, is refused, naming a generated condition."""
    polar = _load_task(_sessions.polar_task(tmp_path))
    plans = {
        "placed": Plan([Block("b", [], factorial=Factorial(
            {"target_pos": (Polar(8.0, 0.0), Polar(8.0, 45.0))}))]),
        "unplaced": Plan([Block("b", [], factorial=Factorial(
            {"target_luminance": (30.0, 60.0)}))]),
    }
    task = dataclasses.replace(polar, plans=plans)

    assert preflight.values(task, {}, plan="placed").result == "pass"
    refused = preflight.values(task, {}, plan="unplaced")
    assert refused.result == "fail"
    assert "setting 'target_pos' places" in refused.said
    assert "in condition 'target_luminance=30.0' of block 'b'" in refused.said


def test_a_draw_past_its_declared_range_is_warned_and_one_that_breaks_the_run_refused():
    """The spec's §11: a draw that can reach past its setting's declared range is checked widened
    to each extreme past it, alone, as a starting value is (XC-352's D2): a warning,
    `outside-range`, and for a wait longer than any the task declares `longer-than-declared`;
    refused where that breaks the run (here a target drawn off the screen). Each finding names
    where and which draw, and is said once, never again for a condition whose own value gave it.
    Not checked: a draw inside its range, a value a weighted set gives at weight 0, a set of
    appearances, a block type's draw in a plain run, and a draw the load refuses."""
    appearances = next(p for p in _task().params if p.name == "target_appearance").choices
    task = _task(draws={
        "fix_hold": Uniform(0.2, 2.5, repeat=FRESH),
        "fix_acquisition": NonAging(1.0, 2.0, 12.0, repeat=FRESH),
        "target_window": Uniform(1.0, 4.0, repeat=FRESH),
        "target_x": Weighted((10.0, 40.0, -40.0), (1, 1, 0), repeat=SAME),
        "target_appearance": Weighted(appearances, (1, 1), repeat=FRESH),
    })
    assert not _blocking(task)

    found = preflight.beyond(task, {}, ALLOCATION, DIRECT, SRGB, None)

    warned = [(f.code, f.detail.split(": ")[0]) for f in found if not f.blocking]
    assert warned == [
        ("outside-range", "in the plain run, the task's draw of 'fix_hold' at 2.5"),
        ("outside-range", "in the plain run, the task's draw of 'fix_acquisition' at 12"),
        ("longer-than-declared", "in the plain run, the task's draw of 'fix_acquisition' at 12"),
        ("outside-range", "in the plain run, the task's draw of 'target_x' at 40"),
    ]
    assert found[0].detail == (
        "in the plain run, the task's draw of 'fix_hold' at 2.5: 'fix_hold' is 2.5 s, outside "
        "the [0.05, 2.0] the task declares, so the task was not designed for it: its load-time "
        "checks were proved only over its declared range, and were run again with the range "
        "widened to 2.5")
    refused = [f for f in found if f.blocking]
    assert refused and {f.code for f in refused} == {"stimulus-off-screen"}
    assert all(f.detail.startswith(
        "in the plain run, the task's draw of 'target_x' at 40: with 'target_x' at 40, outside "
        "its declared range: ") for f in refused)
    item = preflight.values(task, {}, refused)
    assert item.result == "fail" and "stimulus-off-screen: in the plain run, the task's draw" in (
        item.said)

    planned = _task(plans={"p": Plan([
        Block("b", [Condition("c", {}, target=1), Condition("d", {"fix_window": 5.5}, target=1)],
              draws={"fix_hold": Uniform(0.01, 0.3, repeat=FRESH)}),
        Block("own", [Condition("far", {"target_x": Uniform(-40.0, 0.0, repeat=SAME)},
                                target=1)]),
    ])})
    assert not _blocking(planned)

    found = preflight.beyond(planned, {}, ALLOCATION, DIRECT, SRGB, None, plan="p")

    assert [(f.code, f.detail.split(": ")[0]) for f in found if not f.blocking] == [
        ("outside-range", "in plan 'p', block 'b', condition 'd'"),
        ("outside-range",
         "in plan 'p', block 'b', condition 'c', the block's draw of 'fix_hold' at 0.01"),
        ("outside-range",
         "in plan 'p', block 'own', condition 'far', its own range of 'target_x' at -40"),
    ], "each said once, where the run first reaches it"
    refused = [f for f in found if f.blocking]
    assert refused and {f.code for f in refused} == {"stimulus-off-screen"}
    assert all(f.detail.startswith(
        "in plan 'p', block 'own', condition 'far', its own range of 'target_x' at -40: ")
        for f in refused)
    assert preflight.beyond(planned, {}, ALLOCATION, DIRECT, SRGB, None) == [], (
        "a block type's draws are not the plain run's")

    refused_at_load = _task(draws={"cue_delay": Uniform(0.1, 9.0, repeat=FRESH),
                                   "fix_hold": Weighted((1.0, 3.0), ("a", 1), repeat=FRESH)})
    assert {f.code for f in _blocking(refused_at_load)} == {"bad-draw"}
    assert preflight.beyond(refused_at_load, {}, ALLOCATION, DIRECT, SRGB, None) == []


def test_a_draw_over_many_conditions_is_checked_once_and_said_once(monkeypatch):
    """The widened checks depend only on the values outside their ranges (the C3 plan's call 27),
    so a draw past its range over a twelve-cell factorial is checked once, not once a cell, and
    its finding said once: the starting values' check, and the draw's."""
    asked = []
    real = preflight.beyond_range

    def counted(task, values, *args, **kwargs):
        asked.append(dict(values))
        return real(task, values, *args, **kwargs)

    monkeypatch.setattr(preflight, "beyond_range", counted)
    task = _task(draws={"fix_hold": Uniform(0.2, 2.5, repeat=FRESH)}, plans={"p": Plan([
        Block("b", [], factorial=Factorial({
            "target_x": (-6.0, -4.0, -2.0, 2.0, 4.0, 6.0), "target_y": (-1.0, 1.0)}))])})
    assert not _blocking(task)

    found = preflight.beyond(task, {}, ALLOCATION, DIRECT, SRGB, None, plan="p")

    assert len(asked) == 2 and asked[1]["fix_hold"] == 2.5
    assert [f.detail.split(": ")[0] for f in found] == [
        "in plan 'p', block 'b', condition 'target_x=-6.0, target_y=-1.0', the task's draw of "
        "'fix_hold' at 2.5"]


def test_a_draws_extremes_are_its_least_and_greatest_finite_numbers():
    """`variation.extremes`, the rule a draw is widened by: a uniform's, a normal's or a wait's
    ends, a normal cut to its setting's declared range where it gives no end of its own; a finite
    set's least and greatest number, a value of weight 0 left out, since it is never drawn (the
    controller's ruling, as `check._drawable` leaves it out), a word or a `True` no number; each
    finite one, once."""
    hold = Param("fix_hold", unit="s", low=0.05, high=2.0)
    assert variation.extremes(Uniform(0.2, 2.5)) == (0.2, 2.5)
    assert variation.extremes(Uniform(4.0, 4.0)) == (4.0,)
    assert variation.extremes(TruncatedNormal(5.0, 1.0, high=6.0)) == (6.0,)
    assert variation.extremes(TruncatedNormal(1.0, 0.5, high=6.0), hold) == (0.05, 6.0)
    assert variation.extremes(NonAging(1.0, 2.0, 12.0)) == (1.0, 12.0)
    assert variation.extremes(Weighted((9.0, "x", 3.0, 6.0, True), (1, 1, 0, 1, 1))) == (6.0, 9.0)
    assert variation.extremes(Listed((2, 8, 4))) == (2, 8)
    assert variation.extremes(Weighted(("a", "b"), (1, 1))) == ()


def test_a_start_whose_values_make_an_impossible_trial_fails_the_starting_values_item():
    """The spec's §9 at a run's start (the C3 plan's review, I-5): `check.impossible` judges the
    run's own starting values -- here a response deadline sent at 0.15 s, inside its range,
    against a 0.2 s target hold the deadline bounds -- over the blocks the run plays, each
    refused, so the starting values item fails; a condition's own deadline is judged over the
    run's. One the task's own starts give fails its task checks at load and is not said again."""
    task = _deadline_bound(_task())
    assert not _blocking(task)

    found = preflight.beyond(task, {"response_deadline": 0.15}, ALLOCATION, DIRECT, SRGB, None)

    refused = [f for f in found if f.blocking]
    assert [f.code for f in refused] == [IMPOSSIBLE]
    assert refused[0].detail.startswith(
        "the plain run: block 'session', condition 'session': state 'verify' ends the trial "
        "NO_RESPONSE after `response_deadline`, 0.15 s, while its 'target' hold takes "
        "`target_hold`, 0.2 s: the hold starts only when the gaze arrives")
    item = preflight.values(task, {"response_deadline": 0.15}, refused)
    assert item.result == "fail"
    assert "impossible-trial: the plain run: block 'session', condition 'session': " in item.said

    planned = dataclasses.replace(task, plans={"p": Plan([Block("b", [
        Condition("slow", {"response_deadline": 0.6}, target=1),
        Condition("fast", {}, target=1)])])})
    (one,) = preflight.beyond(planned, {"response_deadline": 0.15}, ALLOCATION, DIRECT, SRGB,
                              None, plan="p")
    assert one.code == IMPOSSIBLE
    assert one.detail.startswith("plan 'p': block 'b', condition 'fast': state 'verify' ")

    started = _unstarted(task, "response_deadline")
    impossible_at_load = dataclasses.replace(started, structures={
        "detection": dataclasses.replace(started.structures["detection"], params=[
            dataclasses.replace(p, start=0.15) if p.name == "response_deadline" else p
            for p in started.structures["detection"].params])})
    assert [f.code for f in _blocking(impossible_at_load)] == [IMPOSSIBLE]
    assert preflight.beyond(impossible_at_load, {}, ALLOCATION, DIRECT, SRGB, None) == []
    (again,) = preflight.beyond(impossible_at_load, {"response_deadline": 0.1}, ALLOCATION,
                                DIRECT, SRGB, None)
    assert "`response_deadline`, 0.1 s" in again.detail, "the run's own value says what it adds"


def test_a_start_that_makes_a_cued_arrays_looks_alike_is_warned_and_fails_no_item():
    """The PI, 2026-10-31, on the engine C3 plan's Appendix B, item 17, "Refuse only odd-one-out
    tasks (Recommended)": at a run's start, a cued array (`Array.found_by` `"cue"`) whose run
    values make its target look like its distractors gets the same warning as at load,
    `cued-target`, never a refusal, so the starting values item passes and the warning joins the
    run's; found by its look, the same start is refused, failing the item. A ring of four discs,
    its target lit by `target_lum` among `distractor_lum`, starting at 40 and 30 cd/m²; the start
    sends the distractors 40. One the task's own starts give, the load warned, and the start does
    not say it again."""
    def ring(found_by: str, distractor: float = 30.0) -> Task:
        def lit(name: str) -> Disc:
            return Disc(size=1.0, color=Gray(P(name)))

        shown = Stimulus("ring", at=(0.0, 0.0), looks=Array(
            n=4, radius=8.0, looks=lit("target_lum"), among=lit("distractor_lum"),
            found_by=found_by))
        trial = Trial(
            start="search",
            params=[Param("target_lum", unit="cd/m2", low=0.0, high=80.0, start=40.0),
                    Param("distractor_lum", unit="cd/m2", low=0.0, high=80.0, start=distractor)],
            windows=[ObjectWindows(of="ring", radius=1.0)],
            states=[State("search", enter=[Show(shown)],
                          go=[On(SaccadeTo("ring.target"), Outcome.CORRECT),
                              On(After(1.0), Outcome.NO_RESPONSE)])],
            counting=Counting(after_stimulus=OWED, appears="search"),
        )
        return Task({"t": trial}, default="t")

    given = {"distractor_lum": 40.0}
    refused = preflight.beyond(ring("look"), given, ALLOCATION, DIRECT, SRGB, None)
    assert [f.code for f in refused if f.blocking] == [IMPOSSIBLE]
    assert preflight.values(ring("look"), given, [f for f in refused if f.blocking]).result == (
        "fail")
    warned = preflight.beyond(ring("cue"), given, ALLOCATION, DIRECT, SRGB, None)
    assert [(f.code, f.blocking) for f in warned] == [(CUED, False)]
    assert warned[0].detail.startswith("the plain run: block 'session', condition 'session': ")
    assert warned[0].detail.endswith("the target must be named by a cue; check that one is shown")
    assert preflight.values(ring("cue"), given, [f for f in warned if f.blocking]).result == (
        "pass")
    assert preflight.beyond(ring("cue"), {}, ALLOCATION, DIRECT, SRGB, None) == []
    alike = ring("cue", distractor=40.0)
    assert CUED in [f.code for f in check_task(alike, ALLOCATION, geometry=DIRECT,
                                                calibration=SRGB)]
    assert preflight.beyond(alike, {}, ALLOCATION, DIRECT, SRGB, None) == []


def test_an_impossible_trial_check_that_cannot_run_at_the_start_refuses_it(monkeypatch):
    """Nothing raises out of the pre-flight (`preflight.beyond`'s rule): a check that raises
    refuses the start, saying it could not run and why, never that the values make a trial no
    animal can get right, which they may not."""
    monkeypatch.setattr(preflight, "impossible", lambda *a, **k: 1 / 0)

    (refusal,) = preflight.beyond(_task(), {}, ALLOCATION, DIRECT, SRGB, None)

    assert refusal.blocking and refusal.code == IMPOSSIBLE
    assert refusal.detail == (
        "the check for a trial no animal can get right could not be run at the starting values "
        "(ZeroDivisionError: division by zero), so whether they make one is unknown")


def _start_row(root: Path, session: str) -> dict:
    """The start row of `wlx run`'s one run."""
    rows = [json.loads(line) for line in
            (root / session / "xcon" / "runs.jsonl").read_text().splitlines()]
    (start,) = [row for row in rows if row["event"] == "start"]
    return start


def _wlx_run(root: Path, session: str, *extra: str) -> int:
    """`wlx run` of the reference task: two trials, the departure now, its warnings accepted."""
    return main([
        "run", str(TASK), "--rig", RIG_FILE, "--view", "direct", "--kind", "training",
        "--accept-warnings", "--allocation", "tasks/allocation.py",
        "--bounds", "tasks/reference_bounds.py", "--root", str(root), "--session-id", session,
        "--subject", "REFERENCE", "--out-of-cage-at", time.strftime("%H:%M"),
        "--delivered-today", "0", "--trials", "2", *extra])


def test_wlx_run_without_a_seed_records_a_fresh_one_and_with_one_records_it(
        tmp_path, monkeypatch, capsys):
    """TSK-06 (the PI, 2026-10-07: "a fresh seed per run, recorded"; engine build C3's call 23):
    `wlx run` given no `--seed` draws one as `wlx taskd`'s service does (`service._fresh_seed`),
    records it on the run's start row and says it once; given one, it records that. Every run
    given none was seed 1."""
    monkeypatch.setattr(service, "_fresh_seed", lambda: 424242)

    assert _wlx_run(tmp_path, "2027-01-14_01") == 0
    assert _wlx_run(tmp_path, "2027-01-14_02", "--seed", "9") == 0

    assert _start_row(tmp_path, "2027-01-14_01")["seed"] == 424242
    assert _start_row(tmp_path, "2027-01-14_02")["seed"] == 9
    out = capsys.readouterr().out.splitlines()
    assert [line for line in out if line.startswith("  seed: ")] == [
        "  seed: 424242 (drawn fresh)", "  seed: 9 (given)"]


def test_wlx_run_of_a_plan_whose_factorial_places_nothing_is_refused_before_any_departure(
        tmp_path, capsys):
    """The review of Task 11 (fix round 1): `wlx run --plan` reads its place check over the blocks
    the plan plays, each factorial expanded (`Session.run`'s backstop reads them so), so a
    factorial whose generated conditions place nothing is refused before the departure is marked.
    Read over the declared blocks it passed, the animal was marked out of its cage, and
    the backstop then refused, leaving the session stranded (XC-415's failure)."""
    from wl_xcon import stranded
    text = _sessions.polar_task(tmp_path, name="u").read_text()
    text += (
        "\nfrom wl_xcon.task import Block as _B, Factorial as _F, Plan as _P\n"
        "TASK = _polar_dataclasses.replace(TASK, plans={'u': _P([_B('b', [], factorial=_F(\n"
        "    {'target_luminance': (30.0, 60.0)}))])})\n")
    path = tmp_path / "u.py"
    path.write_text(text)
    root = tmp_path / "root"

    refused = None
    try:
        main([
            "run", str(path), "--rig", RIG_FILE, "--view", "direct", "--kind", "training",
            "--accept-warnings", "--allocation", "tasks/allocation.py",
            "--bounds", "tasks/reference_bounds.py", "--root", str(root),
            "--session-id", "2027-01-14_01", "--subject", "REFERENCE",
            "--out-of-cage-at", time.strftime("%H:%M"), "--delivered-today", "0",
            "--trials", "2", "--plan", "u", "--seed", "3"])
    except SystemExit as stop:
        refused = str(stop)

    assert refused is not None and refused.startswith("task refused, session not started, nothing")
    assert "has no value in condition 'target_luminance=30.0' of block 'b'" in refused
    assert "out of cage" not in capsys.readouterr().out
    assert stranded.find(root) == []


def test_a_direction_drawn_across_zero_is_judged_on_the_circle_it_is_shown_on():
    """The review of Task 11 (fix round 1, minor 1; the controller's ruling): a direction setting
    declared [0, 360] and drawn `Uniform(-45, 45)` -- the form `check.undrawable` recommends -- is
    the angles 315 to 45, all inside it, so a run's start warns nothing, as for the same angles
    written `Weighted((350, 10))`; `variation.extremes(direction=True)` gives the ends in the
    declared range's numbers (the final review's M1 ruling): as shown for [0, 360], or with no
    range declared, and as drawn for [-180, 180]. A setting that is no direction keeps its
    warning, and a direction really outside its range is still warned."""
    spun = Param("target_dir", unit="deg", low=0.0, high=360.0)
    signed = Param("target_dir", unit="deg", low=-180.0, high=180.0)
    assert variation.extremes(Uniform(-45.0, 45.0), spun, direction=True) == (315.0, 45.0)
    assert variation.extremes(Uniform(-45.0, 45.0), direction=True) == (315.0, 45.0)
    assert variation.extremes(Uniform(-45.0, 45.0), signed, direction=True) == (-45.0, 45.0)
    assert variation.extremes(Weighted((350.0, 10.0), (1, 1)), spun, direction=True) == (
        10.0, 350.0)
    assert variation.extremes(Weighted((350.0, 10.0), (1, 1)), signed, direction=True) == (
        -10.0, 10.0)
    assert variation.extremes(Uniform(-45.0, 45.0), spun) == (-45.0, 45.0)
    assert preflight._ends(Uniform(-45.0, 45.0), spun, direction=True) == []
    assert preflight._ends(Uniform(-45.0, 45.0), spun) == [-45.0]
    half = Param("target_dir", unit="deg", low=0.0, high=180.0)
    # Past [0, 180] at -45 as drawn (the final review's M1 ruling): widened to -45 the range
    # reads -45 to 180, which holds the draw; widened to 315 it would read 0 to 315, which
    # leaves out the 315 to 360 drawn and takes in the 180 to 315 never drawn.
    assert preflight._ends(Uniform(-45.0, 45.0), half, direction=True) == [-45.0]


@pytest.mark.parametrize("low, high, draw, past", [
    # The four the final review's M1 ruling names: a range declared in signed terms or from 0 to
    # 360 is the whole turn, so a draw across 0 is inside either; a draw wholly past its range
    # (Task 11's deferred test) and one past a signed range on both sides are warned.
    (-180.0, 180.0, Uniform(-45.0, 45.0), []),
    (0.0, 360.0, Uniform(-45.0, 45.0), []),
    (0.0, 90.0, Uniform(100.0, 120.0), [100.0, 120.0]),
    (-30.0, 30.0, Uniform(-45.0, 45.0), [-45.0, 45.0]),
    # Inside, or past, only a whole turn on: the end past is given where the draw really reaches.
    (-180.0, -90.0, Uniform(190.0, 260.0), []),
    (-180.0, -90.0, Uniform(170.0, 200.0), [-190.0]),
    (0.0, 90.0, Uniform(0.0, 360.0), [360.0]),
    # A range open on a side is the whole turn.
    (0.0, None, Uniform(-45.0, 45.0), []),
    (None, 0.0, Uniform(-45.0, 45.0), []),
    # Each value of a set is its own point on the circle: 350 is -10.
    (-30.0, 30.0, Weighted((350.0, 10.0), (1, 1)), []),
    (-30.0, 30.0, Weighted((350.0, 100.0), (1, 1)), [100.0]),
])
def test_a_direction_draw_is_judged_against_its_declared_range_by_arc_containment(
        low, high, draw, past):
    """The final whole-branch review of engine build C3, Minor 1 (the controller's revised ruling):
    a direction's draw is judged against its declared range on the circle by arc containment --
    the declared arc, the whole turn where its span is 360 or more, holding the draw's arc, from
    its ends as drawn -- so a range declared in signed terms, [-180, 180], no longer warns its own
    `Uniform(-45, 45)` "outside" at 315, at a run's start or live, and one declared [0, 360] still
    does not. A setting that is no direction is judged as before, on the numbers."""
    declared = Param("target_dir", unit="deg", low=low, high=high)

    assert preflight._ends(draw, declared, direction=True) == past


def test_a_draw_the_load_refuses_as_a_direction_is_not_also_widened():
    """The review of Task 11 (minor 2): `_ends` asks `check.undrawable` as the load does, with
    `direction=` for a setting the task places a direction by, so a direction drawn over more than
    a whole turn, which the load refuses, is not also warned at a run's start."""
    spun = Param("target_dir", unit="deg", low=0.0, high=360.0)
    half = Param("target_dir", unit="deg", low=0.0, high=180.0)
    assert preflight._ends(Uniform(100.0, 600.0), half, direction=True) == []
    assert preflight._ends(Uniform(100.0, 600.0), half) == [600.0]


def test_a_run_s_start_asks_for_a_direction_settings_draw_as_a_direction(monkeypatch):
    """The review of Task 11 (minors 1 and 2) at a run's start: `beyond` hands `_ends` the flag
    for each setting `variation.directions` names, and only those."""
    asked = []
    real = preflight._ends

    def seen(draw, declared, direction=False):
        asked.append((declared.name, direction))
        return real(draw, declared, direction)

    monkeypatch.setattr(preflight, "_ends", seen)
    monkeypatch.setattr(preflight, "directions", lambda task: frozenset({"fix_hold"}))
    task = _task(draws={"fix_hold": Uniform(0.2, 1.0, repeat=FRESH),
                        "fix_window": Uniform(1.0, 2.0, repeat=FRESH)})

    preflight.beyond(task, {}, ALLOCATION, DIRECT, SRGB, None)

    assert sorted(asked) == [("fix_hold", True), ("fix_window", False)]
