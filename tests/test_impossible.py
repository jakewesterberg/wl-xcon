"""Settings no animal can get right, refused at load (engine build C3's spec §9; XC-343).

The PI, 2026-10-30, Q10, "Refuse in file and live": "refused in the task file and when set live;
the check judges each concrete combination (per condition, per live change)". One function,
`check.impossible`, judges what each condition's trials can hold -- the run's values, a
condition's value or its own range, a block's or the task's draw, a person's held value over them
-- for the three combinations XC-343 names: a hold its state's timeout always beats, a target that
looks like its distractors, and two objects whose looks swap within a block. At load it runs at
the task's starting values (`check_task`'s `_impossible_faults`); a run's start and a live change
call it with their own values (the C3 plan's Tasks 11 and 12).
"""

from __future__ import annotations

import dataclasses
import math
from pathlib import Path

import pytest

from wl_xcon.check import CUED, impossible, IMPOSSIBLE, check_task
from wl_xcon import check
from wl_xcon.cli import _load_task
from wl_xcon.findings import SESSION_KINDS
from wl_xcon.photometry import Gray
from wl_xcon.task import (
    FRESH,
    OWED,
    SAME,
    After,
    Array,
    Block,
    Condition,
    Counting,
    Disc,
    Entered,
    Factorial,
    Hold,
    Listed,
    ObjectWindows,
    On,
    Outcome,
    P,
    Param,
    Plan,
    Polar,
    SaccadeTo,
    Show,
    Square,
    State,
    Stimulus,
    Task,
    Trial,
    TruncatedNormal,
    Uniform,
    Weighted,
    Window,
)

BASE = _load_task(Path("tasks/fixation_detection.py"))
SEARCH = _load_task(Path("tasks/visual_search.py"))
((RED, GREEN, GREEN_SQUARE),) = [p.choices for p in SEARCH.params
                                 if p.name == "target_appearance"]
PLAIN = Block("session", [Condition("session", {}, target=1)])
REFERENCE = ["fixation_detection", "adaptive_detection", "visual_search",
             "visual_search_training", "calibration"]


def _refused(task: Task) -> list:
    """The task's `impossible-trial` findings at load."""
    return [f for f in check_task(task) if f.code == IMPOSSIBLE]


def _respond(*, first: bool = False, hold: object = P("target_hold"),
             wait: object = P("response_deadline"), to: object = Outcome.NO_RESPONSE,
             since: object = None, starts: tuple = (0.2, 0.6), plans: dict | None = None,
             draws: dict | None = None) -> Task:
    """A task whose one state shows a disc 8° out and asks for a hold on it, `hold` seconds, bounded
    by a timeout on the same state, `wait` seconds to `to`, listed before the hold (`first`) or
    after it; `target_hold` and `response_deadline` start at `starts`."""
    shown = Stimulus("s", at=Polar(8.0, 0.0), looks=Disc(size=0.5, color=Gray(40.0)))
    held = On(Hold("w", hold), Outcome.CORRECT)
    timeout = On(After(wait, since=since), to)
    later = [State("late", go=[On(After(1.0), Outcome.NO_RESPONSE)])] if isinstance(to, str) else []
    trial = Trial(
        start="respond",
        params=[Param("target_hold", unit="s", low=0.05, high=1.0, start=starts[0]),
                Param("response_deadline", unit="s", low=0.1, high=3.0, start=starts[1])],
        windows=[Window("w", at=Polar(8.0, 0.0), radius=1.0, on="s")],
        states=[State("respond", enter=[Show(shown)],
                      go=[timeout, held] if first else [held, timeout]), *later],
        counting=Counting(after_stimulus=OWED, appears="respond"),
    )
    return Task({"t": trial}, default="t", plans=plans or {}, draws=draws or {})


def _ring(looks: object, among: object, *, n: object = 4, plans: dict | None = None,
          draws: dict | None = None, found_by: str = "look") -> Task:
    """A task showing an array of `n` objects, its target `looks` among `among`, found by its look
    or a cue (`found_by`), with the luminances `lum` and `target_lum` starting at 40 cd/m² and
    `distractor_lum` at 30."""
    ring = Stimulus("ring", at=(0.0, 0.0), looks=Array(n=n, radius=8.0, looks=looks, among=among,
                                                       found_by=found_by))
    trial = Trial(
        start="search",
        params=[Param("lum", unit="cd/m2", low=0.0, high=80.0, start=40.0),
                Param("target_lum", unit="cd/m2", low=0.0, high=80.0, start=40.0),
                Param("distractor_lum", unit="cd/m2", low=0.0, high=80.0, start=30.0)],
        windows=[ObjectWindows(of="ring", radius=1.0)],
        states=[State("search", enter=[Show(ring)],
                      go=[On(SaccadeTo("ring.target"), Outcome.CORRECT),
                          On(After(1.0), Outcome.NO_RESPONSE)])],
        counting=Counting(after_stimulus=OWED, appears="search"),
    )
    return Task({"t": trial}, default="t", plans=plans or {}, draws=draws or {})


def _lit(name: str) -> Disc:
    """A disc lit by the luminance setting `name`."""
    return Disc(size=1.0, color=Gray(P(name)))


def _searched(**plans: Plan) -> Task:
    return dataclasses.replace(SEARCH, plans=plans)


def _subjects(found: list) -> list[tuple]:
    return [f.subjects for f in found]


def test_a_hold_its_states_timeout_always_beats_is_refused_ties_by_exit_order():
    """The spec's §9 item 1: a hold its state's timeout always beats, ending the trial in an outcome
    no right answer is, never finishes, since it starts only when the gaze arrives. Judged at the
    values each trial has, and a tie goes by the order the state lists its exits, as
    `hold-cut-short` reads them: a timeout listed first wins the frame both end on."""
    assert _refused(_respond()) == []  # a 0.2 s hold, a 0.6 s deadline

    (plain,) = _refused(_respond(starts=(0.7, 0.6)))
    assert plain.blocking
    assert plain.subjects == ("session: session",)
    assert plain.detail == (
        "the plain run: block 'session', condition 'session': state 'respond' ends the trial "
        "NO_RESPONSE after `response_deadline`, 0.6 s, while its 'w' hold takes `target_hold`, "
        "0.7 s: the hold starts only when the gaze arrives, so it never finishes and no answer "
        "can be paid (XC-343); give the timeout more than 0.7 s, or hold in a state of its own "
        "bounded longer, as the reference tasks hold their target")

    plan = Plan([Block("b", [Condition("short", {"target_hold": 0.3}, target=1),
                             Condition("tie", {"target_hold": 0.6}, target=1),
                             Condition("long", {"target_hold": 0.9}, target=1)])])
    assert _subjects(_refused(_respond(plans={"p": plan}))) == [("b: long",)]
    first = _refused(_respond(first=True, plans={"p": plan}))
    assert _subjects(first) == [("b: tie",), ("b: long",)]
    assert first[0].detail.startswith("plan 'p': block 'b', condition 'tie': ")
    assert "0.6 s, and the timeout, listed first, wins the frame both end on" in first[0].detail

    # One setting both wait on is one number on every trial: only its order decides.
    assert _refused(_respond(wait=P("target_hold"))) == []
    (same,) = _refused(_respond(first=True, wait=P("target_hold")))
    assert "after `target_hold`, which its 'w' hold takes too" in same.detail
    assert "list the hold first" in same.detail

    # Written as numbers, it is refused as written.
    (written,) = _refused(_respond(hold=0.5, wait=0.4))
    assert "after 0.4 s, while its 'w' hold takes 0.5 s" in written.detail


def test_a_timeout_that_is_the_right_answer_is_not_refused():
    """The outline review's M-10: only a timeout ending the trial in an outcome no right answer is
    (`task.RIGHT`) makes the hold's trial impossible. In a no-go design the timeout is the right
    answer, so a hold it always beats is not refused; nor a timeout that moves on to another
    state, nor one timed from something later than the state's start (`since`)."""
    assert _refused(_respond(starts=(0.7, 0.6), to=Outcome.CORRECT_REJECT)) == []
    assert _refused(_respond(starts=(0.7, 0.6), to="late")) == []
    assert _refused(_respond(starts=(0.7, 0.6), since=Entered("w"))) == []
    assert len(_refused(_respond(starts=(0.7, 0.6), to=Outcome.NO_FIXATION))) == 1


def test_a_hold_in_its_own_state_as_the_reference_tasks_write_it_is_not_refused():
    """The C3 plan's call 25: the reference tasks hold their target in its own `verify` state,
    bounded by `After(3.0)`, so no hold and deadline their ranges allow is refused, the longest
    hold against the shortest deadline included."""
    extremes = {"target_hold": 1.0, "fix_hold": 2.0, "response_deadline": 0.1,
                "fix_acquisition": 0.5}
    for task in (BASE, SEARCH):
        plan = Plan([Block("b", [Condition("extreme", extremes, target=1)])])
        assert _refused(dataclasses.replace(task, plans={"p": plan})) == []
        assert impossible(task, [PLAIN], extremes) == []


def test_a_target_that_resolves_to_its_distractors_look_is_refused():
    """The spec's §9 item 2: an array whose target and distractor appearances resolve to the same
    value, equality only, through every setting they read: a whole look, or a look's color."""
    plan = Plan([Block("b", [
        Condition("alike", {"target_appearance": GREEN, "distractor_appearance": GREEN,
                            "set_size": 4}, target=1),
        Condition("apart", {"target_appearance": RED, "distractor_appearance": GREEN,
                            "set_size": 4}, target=1),
        Condition("shape", {"target_appearance": GREEN_SQUARE, "distractor_appearance": GREEN,
                            "set_size": 4}, target=1),
        Condition("alone", {"target_appearance": GREEN, "distractor_appearance": GREEN,
                            "set_size": 1}, target=1),
    ])])
    (alike,) = _refused(_searched(p=plan))
    assert alike.subjects == ("b: alike",)
    assert alike.detail.startswith(
        "plan 'p': block 'b', condition 'alike': array 'search''s target, `target_appearance`, "
        "and its distractors, `distractor_appearance`, can look the same (`target_appearance` ")
    assert alike.detail.endswith(
        "no object stands out, so no answer can be chosen (XC-343); give the target a look its "
        "distractors never have")

    # A look's own setting: two luminances, equal or not, and one luminance both read.
    lums = Plan([Block("b", [
        Condition("equal", {"target_lum": 20.0, "distractor_lum": 20.0}, target=1),
        Condition("unequal", {"target_lum": 20.0, "distractor_lum": 30.0}, target=1)])])
    assert _subjects(_refused(_ring(_lit("target_lum"), _lit("distractor_lum"),
                                    plans={"p": lums}))) == [("b: equal",)]
    (one,) = _refused(_ring(_lit("lum"), _lit("lum")))
    assert one.subjects == ("session: session",)
    assert "can look the same (`lum` 40.0)" in one.detail
    assert _refused(_ring(Square(size=1.0, color=Gray(P("lum"))), _lit("lum"))) == []


def test_two_objects_whose_looks_swap_within_a_block_are_refused_and_across_blocks_not():
    """The spec's §9 item 3: at set size 2, in a block where one trial's target and distractor
    appearances are another trial's distractor and target. Two objects have no odd one out, so one
    display can call for either answer. Two blocks, one look each way, are not refused, nor four
    objects, nor a chain whose displays differ."""
    def shown(name: str, target, distractor, size: int = 2) -> Condition:
        return Condition(name, {"target_appearance": target, "distractor_appearance": distractor,
                                "set_size": size}, target=1)

    red, green = shown("red", RED, GREEN), shown("green", GREEN, RED)
    again = shown("again", RED, GREEN)
    (swap,) = _refused(_searched(p=Plan([Block("swap", [red, again, green])])))
    assert swap.subjects == ("swap: red", "swap: again", "swap: green")
    assert swap.detail.startswith(
        "plan 'p': block 'swap': an array can show two objects, and two looks are the target and "
        "the distractors on one trial and the other way round on another (conditions 'red', "
        "'again' (`target_appearance` ")
    assert swap.detail.endswith(
        "two objects have no odd one out, so one display can call for either answer (XC-343); "
        "show three objects or more, or give each look one role in the block")

    assert _refused(_searched(p=Plan([Block("one", [red]), Block("other", [green])]))) == []
    assert _refused(_searched(p=Plan([Block("four", [shown("red", RED, GREEN, 4),
                                                       shown("green", GREEN, RED, 4)])]))) == []
    assert _refused(_searched(p=Plan([Block("mixed", [red, shown("green", GREEN, RED, 4)])]))) == []
    # A chain whose displays differ, red among green beside a green square among red, has its
    # answer on each display, so it loads, in either order (the controller's ruling, 2026-10-30:
    # a full swap only, the spec's own reason; TSK-51, refuse only what breaks a run).
    square = shown("square", GREEN_SQUARE, RED)
    assert _refused(_searched(p=Plan([Block("chain", [red, square])]))) == []
    assert _refused(_searched(p=Plan([Block("chain", [square, red])]))) == []
    # One trial's own look, the same as its distractors', is the second combination alone.
    (alone,) = _refused(_searched(p=Plan([Block("b", [shown("same", GREEN, GREEN)])])))
    assert "can look the same" in alone.detail


def test_a_cued_array_is_warned_where_an_odd_one_out_is_refused():
    """The PI, 2026-10-31, on the engine C3 plan's Appendix B, item 17, "Refuse only odd-one-out
    tasks (Recommended)": the two look checks refuse only an array its task says is found by its
    look (`Array.found_by`, the default), the odd one out, as a pop-out search's target is. Where
    the task says a cue names the target -- a cue, a remembered sample, a place, as in a cued
    two-choice task whose two pictures are target and nontarget by turns [@chelazzi1993neural] --
    each is a warning, `cued-target`, accepted in every kind: the target must be named by a cue. A
    swap is refused where any array in it is found by its look. `impossible` says the warning only
    when asked (`cued`), as the load and a run's start ask, so a live change, judged for refusals
    alone, is accepted on a cued array; no time to answer is refused whatever names the target."""
    def judged(task: Task) -> list:
        return [f for f in check_task(task) if f.code in (IMPOSSIBLE, CUED)]

    alike = _ring(_lit("lum"), _lit("lum"), found_by="cue")
    (warned,) = judged(alike)
    assert (warned.code, warned.blocking, warned.accepted_in, warned.subjects) == (
        CUED, False, SESSION_KINDS, ("session: session",))
    assert warned.detail.startswith(
        "the plain run: block 'session', condition 'session': array 'ring''s target, ")
    assert "can look the same (`lum` 40.0)" in warned.detail
    assert warned.detail.endswith(
        ", and a cue names the target (found_by 'cue'): the target must be named by a cue; "
        "check that one is shown")
    assert impossible(alike, [PLAIN], {"lum": 40.0}) == []
    assert [f.code for f in impossible(alike, [PLAIN], {"lum": 40.0}, cued=True)] == [CUED]
    assert [f.code for f in judged(_ring(_lit("lum"), _lit("lum")))] == [IMPOSSIBLE]

    swapping = {"p": Plan([Block("swap", [
        Condition("a", {"target_lum": 20.0, "distractor_lum": 30.0}, target=1),
        Condition("b", {"target_lum": 30.0, "distractor_lum": 20.0}, target=1)])])}
    looked = _ring(_lit("target_lum"), _lit("distractor_lum"), n=2, plans=swapping)
    named = _ring(_lit("target_lum"), _lit("distractor_lum"), n=2, plans=swapping,
                  found_by="cue")
    assert [f.code for f in judged(looked)] == [IMPOSSIBLE]
    (swap,) = judged(named)
    assert (swap.code, swap.blocking, swap.subjects) == (CUED, False, ("swap: a", "swap: b"))
    assert swap.detail.startswith(
        "plan 'p': block 'swap': an array can show two objects, and two looks are the target and "
        "the distractors on one trial and the other way round on another (")
    assert swap.detail.endswith(
        "and a cue names the target (found_by 'cue'): the target must be named by a cue; check "
        "that one is shown")
    # One condition's array found by its look, the other's by a cue: the swap is refused.
    mixed = Task({"t": looked.structures["t"], "c": named.structures["t"]}, default="t",
                 plans={"p": Plan([Block("swap", [
                     Condition("a", {"target_lum": 20.0, "distractor_lum": 30.0}, target=1),
                     Condition("b", {"target_lum": 30.0, "distractor_lum": 20.0}, target=1,
                               structure="c")])])})
    assert [f.code for f in judged(mixed)] == [IMPOSSIBLE]
    # Each array judged by what names its target, however alike its looks are to another's: one
    # look in two structures, and a swap between them, refused for the one found by its look and
    # warned for the cued one alone.
    lit = _ring(_lit("lum"), _lit("lum"))
    shared = Task({"t": lit.structures["t"], "c": alike.structures["t"]}, default="t",
                  plans={"p": Plan([Block("b", [Condition("odd", {}, target=1),
                                                Condition("cued", {}, target=1, structure="c")])])})
    assert sorted((f.code, f.subjects) for f in judged(shared) if f.detail.startswith("plan")) == [
        (CUED, ("b: cued",)), (IMPOSSIBLE, ("b: odd",))]
    three = Task({"t": looked.structures["t"], "c": named.structures["t"]}, default="t",
                 plans={"p": Plan([Block("swap", [
                     Condition("a", {"target_lum": 20.0, "distractor_lum": 30.0}, target=1),
                     Condition("b", {"target_lum": 20.0, "distractor_lum": 30.0}, target=1,
                               structure="c"),
                     Condition("c", {"target_lum": 30.0, "distractor_lum": 20.0}, target=1,
                               structure="c")])])})
    assert sorted((f.code, f.subjects) for f in judged(three)) == [
        (CUED, ("swap: b", "swap: c")), (IMPOSSIBLE, ("swap: a", "swap: c"))]


def test_a_draw_that_can_produce_an_impossible_trial_is_refused():
    """The spec's §9: "a draw that can produce an impossible trial is refused, since some trials
    would take that value", judged over every draw's full range: the task's, a block's own and a
    condition's own range. A weight of 0 is never drawn, and a continuous draw gives any one number
    with no chance, so it is never judged equal to another value; its one number, where its lowest
    is its highest, is."""
    def drawn(low: float, high: float) -> Uniform:
        return Uniform(low, high, repeat=FRESH)

    (task,) = _refused(_respond(starts=(None, 0.6), draws={"target_hold": drawn(0.1, 0.8)}))
    assert "hold takes `target_hold`, up to 0.8 s" in task.detail
    assert _refused(_respond(starts=(None, 0.6), draws={"target_hold": drawn(0.1, 0.5)})) == []
    (soon,) = _refused(_respond(starts=(0.5, None), draws={"response_deadline": drawn(0.3, 2.0)}))
    assert "after `response_deadline`, as soon as 0.3 s" in soon.detail

    blocks = Plan([Block("narrow", [Condition("c", {}, target=1)]),
                   Block("wide", [Condition("c", {}, target=1)],
                         draws={"target_hold": drawn(0.1, 0.9)})])
    assert _subjects(_refused(_respond(starts=(None, 0.6), draws={"target_hold": drawn(0.1, 0.5)},
                                       plans={"p": blocks}))) == [("wide: c",)]

    own = Plan([Block("b", [
        Condition("reaching", {"target_hold": TruncatedNormal(0.4, 0.1, low=0.2, high=0.7,
                                                              repeat=SAME)}, target=1),
        Condition("short", {"target_hold": TruncatedNormal(0.4, 0.1, low=0.2, high=0.55,
                                                           repeat=SAME)}, target=1)])])
    assert _subjects(_refused(_respond(plans={"p": own}))) == [("b: reaching",)]

    def sized(weights: tuple) -> Plan:
        return Plan([Block("swap", [
            Condition("red", {"target_appearance": RED, "distractor_appearance": GREEN}, 1),
            Condition("green", {"target_appearance": GREEN, "distractor_appearance": RED}, 1)],
            draws={"set_size": Weighted((2, 4), weights, repeat=FRESH)})])

    assert _subjects(_refused(_searched(p=sized((1, 1))))) == [("swap: red", "swap: green")]
    assert _refused(_searched(p=sized((0, 1)))) == []

    def among(values: tuple) -> Plan:
        return Plan([Block("b", [Condition("red", {"target_appearance": RED, "set_size": 4}, 1)],
                           draws={"distractor_appearance": Listed(values, repeat=FRESH)})])

    (listed,) = _refused(_searched(p=among((GREEN, RED))))
    assert "`distractor_appearance` one of " in listed.detail
    assert _refused(_searched(p=among((GREEN,)))) == []

    # Two draws of the looks, each trial its own: one trial can show red among red, and two can
    # swap them.
    both = Plan([Block("b", [Condition("both", {"set_size": 2}, target=1)], draws={
        "target_appearance": Listed((RED, GREEN), repeat=FRESH),
        "distractor_appearance": Listed((GREEN, RED), repeat=FRESH)})])
    alike, swapped = _refused(_searched(p=both))
    assert alike.subjects == swapped.subjects == ("b: both",)
    assert "can look the same" in alike.detail
    assert "(condition 'both' (`target_appearance` one of " in swapped.detail
    assert "whose trials can swap them" in swapped.detail

    assert _refused(_ring(_lit("target_lum"), _lit("distractor_lum"),
                          draws={"target_lum": Uniform(20.0, 60.0, repeat=SAME)})) == []
    assert _refused(_ring(_lit("target_lum"), _lit("distractor_lum"), draws={
        "target_lum": Uniform(20.0, 60.0, repeat=SAME),
        "distractor_lum": Uniform(20.0, 60.0, repeat=SAME)})) == []
    # One drawn setting both looks read is one number on a trial, whatever it is.
    (shared,) = _refused(_ring(_lit("lum"), _lit("lum"),
                               draws={"lum": Uniform(20.0, 60.0, repeat=SAME)}))
    assert "(`lum` 20 to 60)" in shared.detail
    (pinned,) = _refused(_ring(_lit("target_lum"), _lit("distractor_lum"),
                               draws={"target_lum": Uniform(30.0, 30.0, repeat=SAME)}))
    assert "`target_lum` 30.0; `distractor_lum` 30.0" in pinned.detail


def test_a_held_value_and_a_live_range_are_judged_over_conditions_and_draws():
    """`impossible` called as a run's start and a live change call it (the C3 plan's Tasks 11 and
    12): `values` are the run's, under each condition's value and each draw; a setting a person
    holds (`held`) beats both; `ranges`, keyed as the C3 plan's call 7 keys a draw, replaces the
    draw in force, and `None` there restores the declared one."""
    task = _respond()
    conditions = Block("b", [Condition("short", {"target_hold": 0.2}, target=1),
                             Condition("shorter", {"target_hold": 0.1}, target=1)])
    values = {"target_hold": 0.9, "response_deadline": 0.6}
    assert impossible(task, [conditions], values) == []
    (held,) = impossible(task, [conditions], values, held=frozenset({"target_hold"}))
    assert held.subjects == ("b: short", "b: shorter")
    assert held.detail.startswith("block 'b', conditions 'short', 'shorter': state 'respond'")

    drawing = _respond(draws={"target_hold": Uniform(0.1, 0.5, repeat=FRESH)})
    values = {"target_hold": 0.2, "response_deadline": 0.6}
    assert impossible(drawing, [PLAIN], values) == []
    wide = {("task", "target_hold"): Uniform(0.1, 0.9, repeat=FRESH)}
    (ranged,) = impossible(drawing, [PLAIN], values, ranges=wide)
    assert "`target_hold`, up to 0.9 s" in ranged.detail
    assert impossible(drawing, [PLAIN], values, ranges={("task", "target_hold"): None}) == []
    assert len(impossible(drawing, [PLAIN], {**values, "target_hold": 0.9},
                          held=frozenset({"target_hold"}))) == 1
    assert len(impossible(drawing, [PLAIN], {**values, "response_deadline": 0.15},
                          held=frozenset({"response_deadline"}))) == 1

    own = Block("b", [Condition("c", {}, target=1)],
                draws={"target_hold": Uniform(0.1, 0.4, repeat=FRESH)})
    assert impossible(drawing, [own], values, ranges=wide) == []  # the block's own draw is in force
    assert len(impossible(drawing, [own], values, ranges={
        ("block", "b", "target_hold"): Uniform(0.1, 0.9, repeat=FRESH)})) == 1
    ranged = Block("b", [Condition("c", {"target_hold": Uniform(0.1, 0.4, repeat=SAME)}, 1)])
    assert impossible(task, [ranged], values) == []
    assert len(impossible(task, [ranged], values, ranges={
        ("condition", "c", "target_hold"): Uniform(0.1, 0.9, repeat=SAME)})) == 1


def test_a_setting_nothing_gives_is_not_judged_and_nothing_raises():
    """The C3 plan's call 25: a setting nothing gives is not judged (a run's pre-flight refuses
    it), nor a draw that cannot be drawn (refused `bad-draw`), nor a block or a condition that is
    not the shape its class declares (refused by the plans' checks); none of them raises."""
    assert impossible(_respond(starts=(None, None)), [PLAIN], {}) == []
    assert impossible(_respond(starts=(None, 0.6)), [PLAIN], {"response_deadline": 0.6}) == []
    assert impossible(_respond(first=True, wait=P("target_hold"), starts=(None, 0.6)), [PLAIN],
                      {"response_deadline": 0.6}) == []
    assert impossible(SEARCH, [PLAIN], {"set_size": 2}) == []
    assert impossible(_ring(_lit("target_lum"), _lit("distractor_lum"), n=P("lum")), [PLAIN],
                      {"target_lum": 30.0, "distractor_lum": 30.0}) == []

    unread = _respond(starts=(None, 0.6),
                      draws={"target_hold": Uniform(0.1, math.inf, repeat=FRESH)})
    codes = {f.code for f in check_task(unread)}
    assert "bad-draw" in codes and IMPOSSIBLE not in codes

    junk = Block("junk", ["no condition",
                          Condition("text", "no values", target=1),
                          Condition("elsewhere", {}, target=1, structure="nowhere"),
                          Condition("listed", {}, target=1, structure=["t"]),
                          Condition("words", {"target_hold": "slow"}, target=1)],
                 draws=["no draws"])
    assert impossible(_respond(), [junk, "no block"], {"response_deadline": 0.6}) == []
    assert _refused(_respond(plans={"p": Plan([junk])})) == []


def test_a_hold_its_timeout_leaves_less_than_a_saccades_latency_after_is_warned():
    """The C3 plan's science review, I-6: the hold starts only when the gaze arrives, and with no
    gap a macaque's saccade comes about 200 ms after its target ([@fischer1983saccadic], as the
    decisions read it; `check.SACCADE_LATENCY_S`), so a timeout ending the state less than that
    after the hold's longest is won only by an anticipation. Warned, `little-time-to-answer`,
    with the margin, accepted in every kind; 0.2 s or more is not; a hold refused as impossible is
    not warned again; one setting bounding both, the hold listed first, is warned; a timeout to a
    right answer is not."""
    def warned(task: Task) -> list:
        return [f for f in check_task(task) if f.code == "little-time-to-answer"]

    assert check.SACCADE_LATENCY_S == 0.2
    assert warned(_respond()) == []  # a 0.2 s hold, a 0.6 s deadline: 0.4 s to spare
    assert warned(_respond(starts=(0.4, 0.6))) == []  # 0.2 s to spare, a latency exactly
    (near,) = warned(_respond(starts=(0.5, 0.6)))
    assert (near.blocking, near.accepted_in, near.subjects) == (
        False, SESSION_KINDS, ("session: session",))
    assert near.detail.startswith("the plain run: state 'respond' ends the trial NO_RESPONSE")
    assert "0.1 s past the most its 'w' hold takes" in near.detail
    assert near.detail.endswith("give the timeout at least 0.7 s")
    assert warned(_respond(starts=(0.7, 0.6))) == []  # refused as impossible
    assert _refused(_respond(starts=(0.7, 0.6))) != []
    (same,) = warned(_respond(hold=P("target_hold"), wait=P("target_hold")))
    assert "`target_hold`, which its 'w' hold takes too" in same.detail
    assert warned(_respond(hold=P("target_hold"), wait=P("target_hold"), first=True)) == []
    assert warned(_respond(starts=(0.5, 0.6), to=Outcome.CORRECT)) == []
    # A drawn hold is judged at its longest, a drawn timeout at its soonest (fix round 1: the
    # warning's own bounds, once unpinned, now read the one generator `_cut_off` reads).
    (long_draw,) = warned(_respond(starts=(None, 0.6),
                                   draws={"target_hold": Uniform(0.1, 0.5, repeat=FRESH)}))
    assert "up to 0.5 s" in long_draw.detail
    (soon_draw,) = warned(_respond(starts=(0.5, None),
                                   draws={"response_deadline": Uniform(0.55, 2.0, repeat=FRESH)}))
    assert "as soon as 0.55 s" in soon_draw.detail
    near_plan = _respond(plans={"p": Plan([Block("b", [Condition("tight", {
        "target_hold": 0.55}, target=1), Condition("loose", {}, target=1)])])})
    found = [f for f in warned(near_plan) if f.detail.startswith("plan 'p'")]
    assert [f.subjects for f in found] == [("b: tight",)]


@pytest.mark.parametrize("name", REFERENCE)
def test_no_reference_task_is_refused(name):
    """The C3 plan's call 34: no reference task draws or has plans, and none is refused at load, nor
    at any hold and bound their ranges allow: every hold at its longest, every other number at its
    least."""
    task = _load_task(Path(f"tasks/{name}.py"))
    assert IMPOSSIBLE not in {f.code for f in check_task(task)}
    assert "little-time-to-answer" not in {f.code for f in check_task(task)}
    extremes = {param.name: param.high if param.name.endswith("hold") else param.low
                for param in task.params if not param.choices and param.low is not None}
    assert impossible(task, [PLAIN], extremes) == []


def test_a_48_cell_factorial_judges_its_looks_once_and_says_one_finding(monkeypatch):
    """The outline review's M-11: a check run live between trials judges once per distinct
    combination, never once per condition. 48 cells that give no setting the three combinations
    read share one judgement of their arrays and one pair of looks, and a sentence true of all 48
    is one finding naming each."""
    looked, paired = [], []
    same_looks, swapped = check._same_looks, check._swapped
    monkeypatch.setattr(check, "_same_looks",
                        lambda *args: looked.append(1) or same_looks(*args))
    monkeypatch.setattr(check, "_swapped",
                        lambda pairs: paired.append(len(pairs)) or swapped(pairs))
    grid = Block("grid", [], factorial=Factorial({
        "array_eccentricity": (5.0, 6.0, 7.0, 8.0, 9.0, 10.0, 11.0, 12.0),
        "array_rotation": (0.0, 60.0, 120.0, 180.0, 240.0, 300.0)}))
    values = {"set_size": 2, "target_appearance": RED, "distractor_appearance": RED,
              "target_hold": 0.2, "response_deadline": 0.6}

    (found,) = impossible(SEARCH, [grid], values)
    assert len(found.subjects) == 48
    assert found.subjects[0] == "grid: array_eccentricity=5.0, array_rotation=0.0"
    assert looked == [1] and paired == [1]


def test_a_hold_leading_to_a_wrong_answer_that_the_timeout_cuts_off_is_not_refused():
    """Fix round 1, the review's Important 1: the right answer's hold is payable, so a second hold
    whose own exit is a wrong answer (an outcome no right answer is) and that the state's timeout
    always beats refuses nothing and warns nothing; a hold leading to a right answer is judged."""
    def two(wrong: object) -> Task:
        shown = Stimulus("s", at=Polar(8.0, 0.0), looks=Disc(size=0.5, color=Gray(40.0)))
        trial = Trial(
            start="respond",
            params=[Param("response_deadline", unit="s", low=0.1, high=3.0, start=0.6)],
            windows=[Window("w", at=Polar(8.0, 0.0), radius=1.0, on="s"),
                     Window("x", at=Polar(-8.0, 0.0), radius=1.0, on="s")],
            states=[State("respond", enter=[Show(shown)], go=[
                On(Hold("w", 0.2), Outcome.CORRECT), On(Hold("x", 0.8), wrong),
                On(After(P("response_deadline")), Outcome.NO_RESPONSE)])],
            counting=Counting(after_stimulus=OWED, appears="respond"),
        )
        return Task({"t": trial}, default="t")

    task = two(Outcome.WRONG_TARGET)
    assert _refused(task) == []
    assert "little-time-to-answer" not in {f.code for f in check_task(task)}
    assert len(_refused(two(Outcome.CORRECT))) == 1


def test_a_self_pair_already_judged_alike_says_no_swap_and_a_cut_off_hold_is_refused_when_cued():
    """Fix round 1, the review's Minor 1 and 2: one condition drawing its target from red or green
    among green at two objects has green among green (item 2) but no trial of green among red, so
    it gets the item-2 sentence alone; and no time to answer is refused whatever names the target."""
    drawn = Plan([Block("b", [Condition("both", {"set_size": 2, "distractor_appearance": GREEN},
                                        target=1)],
                        draws={"target_appearance": Listed((RED, GREEN), repeat=FRESH)})])
    (alone,) = _refused(_searched(p=drawn))
    assert "can look the same" in alone.detail and "swap" not in alone.detail

    cued = _ring(_lit("lum"), _lit("lum"), found_by="cue")
    state = cued.structures["t"].states[0]
    held = dataclasses.replace(state, go=[
        On(Hold("w", 0.7), Outcome.CORRECT), On(After(0.6), Outcome.NO_RESPONSE),
        *state.go[:1]])
    trial = dataclasses.replace(cued.structures["t"], states=[held], windows=[
        *cued.structures["t"].windows, Window("w", at=Polar(8.0, 0.0), radius=1.0, on="ring")])
    refused = _refused(dataclasses.replace(cued, structures={"t": trial}))
    assert len(refused) == 1 and "'w' hold" in refused[0].detail
