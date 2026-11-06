"""The load-time checks of draws, factorials and designed orders (engine build C3; its spec §2,
§4, §5 and §11).

Under the PI's rule of 2026-10-11, warnings over refusals (TSK-51): a draw, a factorial or a
designed order is refused only for welfare, an authoring rule, an unreadable record or what breaks
a run, each sentence saying which and what to write (`bad-draw`, `bad-plan`), and warned, saying
why, where it runs but may not do what was meant (`cut-sequence`, `long-condition-name`). Every
caller that holds a task to its checks sees these through `check.check_task`.
"""

from __future__ import annotations

import dataclasses
import math
from pathlib import Path

import pytest

from wl_xcon import check, link
from wl_xcon.check import check_task
from wl_xcon.cli import _load_task
from wl_xcon.findings import SESSION_KINDS
from wl_xcon.photometry import Gray
from wl_xcon.task import (
    BY_CONDITIONS,
    FRESH,
    OWED,
    SAME,
    After,
    Array,
    Block,
    ByCriterion,
    Condition,
    Counting,
    Disc,
    Distribution,
    Factorial,
    Hold,
    Listed,
    NonAging,
    On,
    Outcome,
    P,
    Param,
    Plan,
    Polar,
    Priming,
    SequenceBalanced,
    Show,
    Shuffled,
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
((DISC, SQUARE),) = [p.choices for p in BASE.params if p.name == "target_appearance"]
#: The refusals these checks give; the reference tasks give none of them.
CODES = ("bad-draw", "bad-plan")
DIRECTION = "direction-outside-0-360"

#: `fix_hold` as the reference task declares it, and with no highest.
HOLD = Param("fix_hold", unit="s", low=0.05, high=2.0, start=0.3)
OPEN_HOLD = Param("fix_hold", unit="s", low=0.05, start=0.3)

NEAR = Condition("near", {"target_x": 5.0}, target=2)
FAR = Condition("far", {"target_x": 12.0}, target=2)


def _found(task: Task, codes: tuple = CODES) -> list:
    return [f for f in check_task(task) if f.code in codes]


def _codes(task: Task, codes: tuple = CODES) -> list[str]:
    return [f.code for f in _found(task, codes)]


def _with(task: Task = BASE, *, draws: dict | None = None, **plans) -> Task:
    """`task` drawing `draws`, with `plans` as its plans."""
    return dataclasses.replace(task, draws=draws or {}, plans=plans)


def _redeclared(task: Task, *params: Param) -> Task:
    """`task` with each of `params` in place of its setting of that name, or beside them."""
    def swapped(declared: list) -> list:
        named = {param.name: param for param in params}
        return [named.pop(param.name, param) for param in declared] + list(named.values())

    return dataclasses.replace(task, structures={
        name: dataclasses.replace(structure, params=swapped(structure.params))
        for name, structure in task.structures.items()})


def _owing(condition: Condition, target: int) -> Condition:
    return dataclasses.replace(condition, target=target)


def _aimed(direction: Param, *, extra: tuple = (), looks=None, draws: dict | None = None,
           plans: dict | None = None) -> Task:
    """A task showing a disc, or `looks`, 8° out at the direction `dir` (`direction`), its window
    there, with `ecc`, a setting no direction, and `extra` declared beside it."""
    at = Polar(8.0, P("dir"))
    shown = Stimulus("s", at=at, looks=looks or Disc(size=0.5, color=Gray(40.0)))
    trial = Trial(
        start="on",
        params=[direction, Param("ecc", unit="deg", low=0.0, high=400.0, start=8.0), *extra],
        windows=[Window("w", at=at, radius=1.0, on="s")],
        states=[State("on", enter=[Show(shown)], go=[On(Hold("w", 0.1), Outcome.CORRECT),
                                                     On(After(1.0), Outcome.NO_RESPONSE)])],
        counting=Counting(after_stimulus=OWED, appears="on"),
    )
    return Task({"t": trial}, default="t", draws=draws or {}, plans=plans or {})


@dataclasses.dataclass(frozen=True, slots=True)
class _Mine(Uniform):
    """An author's own kind of draw, which `variation.draw` cannot draw."""


@pytest.mark.parametrize(("drawn", "declared", "said"), [
    (Uniform(0.5, 0.2, repeat=FRESH), HOLD,
     "its lowest, 0.5, is above its highest, 0.2; write the lowest first"),
    (Uniform(0.2, math.inf, repeat=FRESH), HOLD,
     "its high is inf, and each of a Uniform's numbers is a finite one"),
    (Uniform(0.2, math.nan, repeat=FRESH), HOLD, "its high is nan"),
    (Uniform("short", 0.4, repeat=FRESH), HOLD, "its low is 'short'"),
    (Uniform(-1e308, 1e308, repeat=FRESH), HOLD,
     "it spans from -1e+308 to 1e+308, past what a float holds"),
    (Weighted((), (), repeat=FRESH), HOLD, "it has no values, so nothing can be drawn"),
    (Weighted((0.2, 0.4), (0, 0), repeat=FRESH), HOLD,
     "its weights are all 0, so nothing can be drawn"),
    (Weighted((0.2, 0.4), (1, -1), repeat=FRESH), HOLD,
     "its weights are (1, -1), and each is a finite number of 0 or more"),
    (Weighted((0.2, 0.4), (1, math.inf), repeat=FRESH), HOLD,
     "its weights are (1, inf), and each is a finite number of 0 or more"),
    (Weighted((0.2, 0.4), (1,), repeat=FRESH), HOLD,
     "it has 2 value(s) and 1 weight(s); give each value one weight"),
    (Weighted([0.2, 0.4], (1, 1), repeat=FRESH), HOLD,
     "its values are [0.2, 0.4], and a Weighted's values are a tuple"),
    (Weighted((0.2, 0.4), [1, 1], repeat=FRESH), HOLD,
     "its weights are [1, 1], and a Weighted's weights are a tuple"),
    (Listed((), repeat=FRESH), HOLD, "it has no values, so nothing can be drawn"),
    (Listed([0.2, 0.4], repeat=FRESH), HOLD,
     "its values are [0.2, 0.4], and a Listed's values are a tuple"),
    (TruncatedNormal(0.3, 0.0, repeat=FRESH), HOLD, "its spread, sd 0.0, is not above 0"),
    (TruncatedNormal(0.3, -0.1, repeat=FRESH), HOLD, "its spread, sd -0.1, is not above 0"),
    (TruncatedNormal(0.3, math.nan, repeat=FRESH), HOLD, "its sd is nan"),
    (TruncatedNormal(0.3, 0.1, low=0.5, high=0.4, repeat=FRESH), HOLD,
     "its lowest, 0.5, is above its highest, 0.4"),
    (TruncatedNormal(0.3, 0.1, repeat=FRESH), OPEN_HOLD,
     "it has no highest to be cut to: neither it nor its setting declares one"),
    # Review I-2: a cut, its own or its setting's range, where floating point holds none of it.
    (TruncatedNormal(0.3, 0.01, low=1.5, high=1.9, repeat=FRESH), HOLD,
     "its cut, from 1.5 to 1.9, holds almost none of a normal of mean 0.3 and sd 0.01"),
    (TruncatedNormal(-40.0, 1.0, repeat=FRESH), HOLD,
     "its cut, from 0.05 to 2.0, holds almost none of a normal of mean -40.0 and sd 1.0"),
    (NonAging(0.75, 0.75, 1.25, repeat=FRESH), HOLD,
     "its mean, 0.75, is not above its shortest, 0.75: a wait of no spread"),
    (NonAging(0.75, 0.5, 1.25, repeat=FRESH), HOLD, "its mean, 0.5, is not above its shortest"),
    (NonAging(0.75, 1.5, 1.25, repeat=FRESH), HOLD, "its mean, 1.5, is above its longest, 1.25"),
    (NonAging(1.25, 1.0, 0.75, repeat=FRESH), HOLD,
     "its shortest, 1.25, is above its longest, 0.75; write the shortest first"),
    (Distribution(), HOLD, "it is a Distribution, and a setting is drawn from one of five"),
    (_Mine(0.2, 0.4, repeat=FRESH), HOLD, "it is a _Mine, and a setting is drawn from one of five"),
    # The C3 plan's engineering review, M-2 and M-4.
    (Weighted((0.2, 0.4), (1e308, 1e308), repeat=FRESH), HOLD,
     "its weights, (1e+308, 1e+308), add up past what a float holds"),
    (Weighted((0.2, 0.4), (1, 5e-324), repeat=FRESH), HOLD,
     "one of them above 0 and too small to add to the rest in floating point"),
    (Listed((0.2, 0.4), in_order="yes", repeat=FRESH), HOLD,
     "its in_order is 'yes', and a Listed's in_order is True"),
])
def test_a_draw_that_cannot_be_drawn_is_refused_saying_what_to_write(drawn, declared, said):
    """The spec's §11 ("a distribution that cannot be drawn: lowest above highest, a non-finite
    number, an empty list, all-zero weights, a spread of zero or less, a non-aging average outside
    its shortest and longest"; breaks a run), the outline review's I-2 (a normal whose cut holds
    no probability in floating point), and the controller's rulings of 2026-10-30 (none of the five;
    a list where a tuple belongs): refused at load, `bad-draw`, with `check.undrawable`'s sentence,
    which a live range reuses."""
    found = _found(_with(_redeclared(BASE, declared), draws={"fix_hold": drawn}))

    assert [f.code for f in found] == ["bad-draw"], found
    assert found[0].detail == (
        f"the task's draw of 'fix_hold' cannot be drawn: {check.undrawable(drawn, declared)}")
    assert said in found[0].detail


def test_a_draw_on_a_reward_size_or_an_undeclared_setting_is_refused():
    """The spec's §11, row 1 (welfare): a draw, a block's or a condition's own range naming a
    bounded setting is refused by name, whether or not the task declares a setting of that name
    (the outline review's M-24); and one naming a setting the task does not declare."""
    reward = Uniform(0.1, 0.2, repeat=FRESH)
    declaring = _redeclared(BASE, Param("reward_correct", unit="mL", low=0.0, high=1.0))
    for task in (BASE, declaring):
        for drawing, where in (
            (_with(task, draws={"reward_correct": reward}), "the task's draw of 'reward_correct'"),
            (_with(task, p=Plan([Block("b", [NEAR], draws={"reward_correct": reward})])),
             "plan 'p': block 'b''s draw of 'reward_correct'"),
            (_with(task, p=Plan([Block("b", [Condition("c", {"reward_correct": reward},
                                                       target=1)])])),
             "plan 'p': block 'b''s condition 'c''s own range for 'reward_correct'"),
        ):
            found = _found(drawing)
            assert [f.code for f in found] == ["bad-draw"], found
            assert found[0].detail == (
                f"{where} draws 'reward_correct', a bounded setting, which the subject's bounded "
                f"config sets and nothing draws (welfare); take it out")
    found = _found(_with(draws={"nothing": Uniform(0.2, 0.4, repeat=FRESH)}))
    assert [f.code for f in found] == ["bad-draw"]
    assert found[0].detail == (
        "the task's draw of 'nothing' draws 'nothing', which is no setting the task declares; a "
        "draw names one of the task's own settings")


@pytest.mark.parametrize("drawn", [
    Uniform(0.2, 0.4), Weighted((0.2, 0.4), (3, 1)), TruncatedNormal(0.3, 0.1),
    Listed((0.2, 0.4)), NonAging(0.75, 1.0, 1.25)])
def test_a_draw_that_says_neither_same_nor_fresh_is_refused(drawn):
    """The PI, 2026-10-30, Q3, "Per drawn setting, required": "each drawn setting declares same or
    fresh on a repeat; a task that draws and does not say is refused at load". Each of the five
    saying either is accepted; saying nothing, or anything else, is refused, as the task's draw, a
    block's or a condition's own range."""
    for repeat in (SAME, FRESH):
        said = dataclasses.replace(drawn, repeat=repeat)
        assert _codes(_with(draws={"fix_hold": said})) == []
        assert _codes(_with(p=Plan([Block("b", [Condition("c", {"fix_hold": said}, target=1)])]))
                      ) == []
    for repeat in (None, "again"):
        unsaid = dataclasses.replace(drawn, repeat=repeat)
        for task in (_with(draws={"fix_hold": unsaid}),
                     _with(p=Plan([Block("b", [NEAR], draws={"fix_hold": unsaid})]))):
            found = _found(task)
            assert [f.code for f in found] == ["bad-draw"], found
            assert (f"says neither same nor fresh (its repeat is {repeat!r}), and each drawn "
                    f"setting says what a repeat of its trial takes (the PI, 2026-10-30, Q3); "
                    f"give it repeat=SAME") in found[0].detail


def test_never_both_is_judged_block_by_block_and_a_block_says_by_conditions():
    """The PI, 2026-10-30, Q1b: "never both" reads block by block -- a setting is drawn by the
    block, its own draw or the task's it does not replace, or given by its conditions, each a value
    or its own range, not both -- and (the C3 plan's call 3) a block whose conditions give a
    setting the task draws says so, `BY_CONDITIONS`, or is refused; `BY_CONDITIONS` for a setting
    the task does not draw is refused too, as is a block's draw that is neither."""
    hold = Uniform(0.2, 0.6, repeat=FRESH)
    giving = Condition("short", {"fix_hold": 0.2}, target=1)
    ranged = Condition("ranged", {"fix_hold": Uniform(0.3, 0.5, repeat=SAME)}, target=1)
    assert _codes(_with(draws={"fix_hold": hold}, p=Plan([
        Block("given", [giving, ranged], draws={"fix_hold": BY_CONDITIONS}),
        Block("narrow", [NEAR], draws={"fix_hold": Uniform(0.3, 0.4, repeat=FRESH)}),
        Block("drawn", [FAR]),
    ]))) == []
    for task, said in (
        (_with(draws={"fix_hold": hold}, p=Plan([Block("given", [giving, NEAR])])),
         "plan 'p': block 'given''s condition(s) 'short' give 'fix_hold', which the task draws, "
         "and the block does not say so; a block whose conditions give a setting the task draws "
         "says draws={'fix_hold': BY_CONDITIONS} (the PI, 2026-10-30, Q1b)"),
        (_with(draws={"fix_hold": hold}, p=Plan([Block("given", [ranged])])),
         "plan 'p': block 'given''s condition(s) 'ranged' give 'fix_hold', which the task draws"),
        (_with(draws={"fix_hold": hold}, p=Plan([Block(
            "made", [], factorial=Factorial({"fix_hold": (0.2, 0.4)}))])),
         "plan 'p': block 'made''s condition(s) 'fix_hold=0.2', 'fix_hold=0.4' give 'fix_hold', "
         "which the task draws"),
        (_with(p=Plan([Block("b", [giving, ranged], draws={"fix_hold": hold})])),
         "plan 'p': block 'b' draws 'fix_hold', and its condition(s) 'short', 'ranged' give it "
         "too: a setting is drawn by its block or given by its conditions, never both (the PI, "
         "2026-10-30, Q1b); take 'fix_hold' out of the block's draws or out of those conditions"),
        (_with(p=Plan([Block("b", [NEAR], draws={"fix_hold": BY_CONDITIONS})])),
         "plan 'p': block 'b' says its conditions give 'fix_hold' (BY_CONDITIONS), and the task "
         "draws no 'fix_hold', so no draw is set aside; take it out of the block's draws"),
        (_with(draws={"fix_hold": hold},
               p=Plan([Block("b", [NEAR], draws={"fix_hold": "sometimes"})])),
         "plan 'p': block 'b''s draw of 'fix_hold' is 'sometimes', and a block's draw is a "
         "Distribution, or BY_CONDITIONS for a setting the task draws and its conditions give"),
        (_with(p=Plan([Block("b", [NEAR], draws=[("fix_hold", hold)])])),
         "plan 'p': block 'b''s draws are [('fix_hold', Uniform(low=0.2, high=0.6, "
         "repeat='fresh'))], and a block's draws are a dict"),
    ):
        found = _found(task)
        assert [f.code for f in found] == ["bad-draw"], found
        assert said in found[0].detail


def test_a_conditions_own_range_is_accepted_and_held_to_the_draw_rules():
    """The PI, 2026-10-30, Q1b, "Yes": "a condition may draw its own setting from its own range";
    held at load to the rules a task's draw is (the spec's §11), each refusal naming the
    condition. A setting of choices draws among them."""
    own = Condition("near", {"target_x": Uniform(2.0, 8.0, repeat=SAME)}, target=2)
    assert _codes(_with(p=Plan([Block("b", [own, FAR])]))) == []
    seen = Condition("seen", {"target_appearance": Weighted((DISC, SQUARE), (1, 1),
                                                            repeat=FRESH)}, target=1)
    assert _codes(_with(p=Plan([Block("b", [seen])]))) == []
    for value, said in (
        (Uniform(2.0, 8.0), "says neither same nor fresh"),
        (Uniform(8.0, 2.0, repeat=SAME),
         "cannot be drawn: its lowest, 8.0, is above its highest, 2.0"),
        (Weighted((2.0, "far"), (1, 1), repeat=SAME),
         "can draw 'far', and 'target_x' takes a finite number (deg)"),
    ):
        ranged = dataclasses.replace(own, values={"target_x": value})
        found = _found(_with(p=Plan([Block("b", [ranged, FAR])])))
        assert [f.code for f in found] == ["bad-draw"], found
        assert found[0].detail.startswith(
            "plan 'p': block 'b''s condition 'near''s own range for 'target_x' ")
        assert said in found[0].detail
    # A factorial's level may be its own range (the C3 plan's call 14), held to the same rules.
    levels = Factorial({"target_x": (Uniform(2.0, 8.0, repeat=SAME), 12.0)})
    assert _codes(_with(p=Plan([Block("b", [], factorial=levels)]))) == []
    levels = Factorial({"target_x": (Uniform(8.0, 2.0, repeat=SAME), 12.0)})
    found = _found(_with(p=Plan([Block("b", [], factorial=levels)])))
    assert [f.code for f in found] == ["bad-draw"], found
    assert found[0].detail.startswith(
        "plan 'p': block 'b''s condition 'target_x=uniform from 8.0 to 2.0''s own range for "
        "'target_x' cannot be drawn: its lowest, 8.0, is above its highest, 2.0")


def test_a_draw_its_setting_cannot_hold_is_refused():
    """The spec's §11 ("a draw its setting cannot hold: numbers for a setting of choices; a list
    item the record cannot write"; an unreadable record), and the C3 plan's call 8 (the outline
    review's M-12): an array reads its set size and its target's place through `int()`, so a
    uniform there would record 4.7 while 4 objects show; such a setting is drawn from a set of
    whole numbers."""
    found = _found(_with(draws={"target_appearance": Uniform(0.0, 1.0, repeat=FRESH)}))
    assert [f.code for f in found] == ["bad-draw"], found
    assert found[0].detail == (
        "the task's draw of 'target_appearance' draws numbers, a Uniform, and "
        "'target_appearance' is a setting of choices; draw among its choices with a Weighted or a "
        "Listed")
    assert _codes(_with(draws={"target_appearance": Listed((SQUARE, DISC), repeat=SAME)})) == []
    found = _found(_with(draws={"target_appearance": Weighted((DISC, "disc"), (1, 1),
                                                              repeat=SAME)}))
    assert [f.code for f in found] == ["bad-draw"], found
    assert found[0].detail.startswith(
        "the task's draw of 'target_appearance' can draw 'disc', and 'target_appearance' is one "
        "of (Disc(")
    found = _found(_with(draws={"fix_hold": Listed((0.2, math.nan), repeat=FRESH)}))
    assert [f.code for f in found] == ["bad-draw"], found
    assert found[0].detail == (
        "the task's draw of 'fix_hold' can draw nan, and 'fix_hold' takes a finite number (s)")
    for setting, drawn in (("set_size", Uniform(2, 8, repeat=FRESH)),
                           ("target_index", TruncatedNormal(0.5, 0.2, repeat=FRESH)),
                           ("set_size", NonAging(2, 4, 8, repeat=FRESH))):
        found = _found(_with(SEARCH, draws={setting: drawn}))
        assert [f.code for f in found] == ["bad-draw"], found
        assert (f"draws real numbers, a {type(drawn).__name__}, and an array reads {setting!r} "
                f"as a whole number, its set size or its target's place, so the record would "
                f"write 4.7 while 4 objects show") in found[0].detail
    assert _codes(_with(SEARCH, draws={"set_size": Listed((2, 4, 6), repeat=FRESH),
                                       "target_index": Weighted((0, 1), (1, 1), repeat=SAME)})
                  ) == []
    found = _found(_with(SEARCH, draws={"set_size": Weighted((4, 4.5), (1, 1), repeat=FRESH)}))
    assert [f.code for f in found] == ["bad-draw"], found
    assert found[0].detail == (
        "the task's draw of 'set_size' can draw 4.5, and an array reads 'set_size' as a whole "
        "number, its set size or its target's place; give it whole numbers")


def test_a_direction_drawn_from_one_value_is_refused_and_a_plain_setting_may_be():
    """The controller's ruling on the review of Task 4, I-2: in a direction draw equal ends mean the
    whole turn (the record writes both ends from 0 to 360), so a draw whose ends are one value in
    the task's terms -- a uniform's, a cut normal's -- is no draw: write the value instead. A
    setting that is no direction may draw from one value."""
    wide = Param("dir", unit="deg", low=-180.0, high=180.0)
    for drawn in (Uniform(45.0, 45.0, repeat=FRESH),
                  TruncatedNormal(45.0, 10.0, low=45.0, high=45.0, repeat=FRESH)):
        found = _found(_aimed(wide, draws={"dir": drawn}))
        assert [f.code for f in found] == ["bad-draw"], found
        assert found[0].detail == (
            "the task's draw of 'dir' cannot be drawn: it draws a direction from one value, "
            "45.0, which is not a draw (in a direction draw, equal ends mean the whole turn); "
            "write the value instead")
    assert _codes(_aimed(wide, draws={"dir": Uniform(-180.0, 180.0, repeat=FRESH)})) == []
    assert _codes(_aimed(wide, draws={"ecc": Uniform(8.0, 8.0, repeat=FRESH)})) == []


def test_a_direction_drawn_in_its_own_terms_is_accepted_and_one_over_360_refused():
    """The controller's ruling 1 (2026-10-30, the PI's "0 to 360 in both repos"): a drawn
    direction is declared in the task's own terms, lowest at most highest -- Uniform(-45, 45) --
    and spans at most a whole turn; each value drawn is written from 0 to 360. A setting that is
    no direction may span more."""
    wide = Param("dir", unit="deg", low=-45.0, high=45.0)
    assert _codes(_aimed(wide, draws={"dir": Uniform(-45.0, 45.0, repeat=FRESH)})) == []
    assert _codes(_aimed(Param("dir", unit="deg", low=-180.0, high=180.0),
                         draws={"dir": Uniform(-180.0, 180.0, repeat=FRESH)})) == []
    for drawn, said in (
        (Uniform(0.0, 400.0, repeat=FRESH), "it spans 400.0°, from 0.0 to 400.0"),
        (TruncatedNormal(0.0, 90.0, low=-200.0, high=200.0, repeat=FRESH),
         "it spans 400.0°, from -200.0 to 200.0"),
    ):
        found = _found(_aimed(wide, draws={"dir": drawn}))
        assert [f.code for f in found] == ["bad-draw"], found
        assert found[0].detail == (
            f"the task's draw of 'dir' cannot be drawn: {said}, and a direction is drawn over at "
            f"most a whole turn, in the task's own terms -- Uniform(-45, 45), say -- and written "
            f"from 0 to 360; give it a span of 360 or less")
    assert _codes(_aimed(wide, draws={"ecc": Uniform(0.0, 400.0, repeat=FRESH)})) == []


def test_a_direction_drawn_everywhere_is_not_warned_two_spellings_and_one_given_somewhere_is():
    """The C3 plan's call 39, on the PI's "Warn at load" (2026-10-30): a direction setting placing a
    `Polar` is warned `direction-outside-0-360` for a range reaching outside 0 to 360, which its
    declaration alone shows. A task drawing it in every block every run can play -- the plain
    run's, and each plan's, by the task's draw, a block's or each condition's own range -- writes
    every number of it drawn, from 0 to 360, so nothing writes it two ways and the warning goes.
    It stands where the task's own number can reach the record: a start or a choice outside 0 to
    360, a condition giving it a value (a factorial's level included), a condition leaving it to
    its start, a run that does not draw it; and for a grating's drift direction, which the rig
    writes as drawn."""
    from wl_xcon import look
    from wl_xcon.photometry import Michelson

    def warned(task: Task) -> list:
        return [f.subjects for f in check_task(task) if f.code == DIRECTION]

    wide = Param("dir", unit="deg", low=-45.0, high=45.0)
    draw = {"dir": Uniform(-45.0, 45.0, repeat=FRESH)}
    ranged = Condition("ranged", {"dir": Uniform(-30.0, 30.0, repeat=SAME)}, target=1)
    everywhere = {"p": Plan([
        Block("task's", [Condition("a", {}, target=1)]),
        Block("own", [ranged], draws={"dir": BY_CONDITIONS}),
        Block("block's", [Condition("b", {}, target=1)],
              draws={"dir": Uniform(-10.0, 10.0, repeat=FRESH)}),
    ])}
    assert warned(_aimed(wide)) == [("setting 'dir'",)]
    assert warned(_aimed(wide, draws=draw)) == []
    assert warned(_aimed(wide, draws=draw, plans=everywhere)) == []
    for task in (
        _aimed(dataclasses.replace(wide, start=-30.0), draws=draw),
        _aimed(Param("dir", unit="deg", choices=(-30.0, 30.0)),
               draws={"dir": Weighted((-30.0, 30.0), (1, 1), repeat=FRESH)}),
        _aimed(wide, draws=draw, plans={"p": Plan([Block(
            "b", [Condition("given", {"dir": 10.0}, target=1)], draws={"dir": BY_CONDITIONS})])}),
        _aimed(wide, draws=draw, plans={"p": Plan([Block(
            "b", [ranged, Condition("unset", {}, target=1)], draws={"dir": BY_CONDITIONS})])}),
        _aimed(wide, draws=draw, plans={"p": Plan([Block(
            "b", [Condition("given", {"dir": 10.0}, target=1)])])}),
        _aimed(wide, plans=everywhere),
    ):
        assert warned(task) == [("setting 'dir'",)]
    levels = _aimed(wide, draws=draw, plans={"p": Plan([Block(
        "b", [], factorial=Factorial({"dir": (-90.0, 90.0)}, target=1),
        draws={"dir": BY_CONDITIONS})])})
    assert warned(levels) == [("setting 'dir'",),
                              ("plan 'p': block 'b': condition 'dir=-90.0': setting 'dir'",)]
    grating = look.Look(shape=look.Circle(size=4.0), orientation=0.0, fill=look.SineGrating(
        tf=2.0, direction=P("drift"), contrast=Michelson(0.5)))
    drifting = _aimed(Param("dir", unit="deg", low=0.0, high=360.0), looks=grating,
                      extra=(Param("drift", unit="deg", low=-45.0, high=45.0),),
                      draws={"drift": Uniform(-45.0, 45.0, repeat=FRESH)})
    assert warned(drifting) == [("setting 'drift'",)]


def test_a_factorials_faults_are_refused_and_its_names_must_be_unique():
    """TSK-22 and the spec's §4 ("an exclusion naming a factor or level that does not exist; two
    conditions in one block with one name; exclusions that leave nothing"), the C3 plan's call 14
    (each factor a setting the task declares, never a bounded one; each level a value it can hold,
    or its own range; a name `level_name` can write), and the controller's rulings on Task 4's
    draft (no factors; an exclusion empty or no dict; levels or targets of the wrong type): each
    refused, `bad-plan`, saying what to write. A refused factorial makes no conditions, so its
    fault is said once; the conditions an accepted one makes are its block's, a training
    progression's middle stage judged on them."""
    made = Factorial({"target_x": (-8.0, 8.0), "target_appearance": (DISC, SQUARE)}, target=2,
                     targets={"target_x=8.0, target_appearance=" + repr(DISC): 3})
    assert _codes(_with(p=Plan([Block("b", [NEAR], factorial=made)]))) == []
    two = {"target_x": (8.0, -8.0)}
    for factorial, said in (
        ({"target_x": (8.0,)},
         "block 'b''s factorial is {'target_x': (8.0,)}, and a block's factorial is a "
         "Factorial(factors={setting: (level, ...)}), or None"),
        (Factorial({}), "block 'b''s factorial's factors are {}, and they are a dict of one or "
                        "more of the task's settings to their levels"),
        (Factorial([("target_x", (8.0,))]), "factorial's factors are [('target_x', (8.0,))]"),
        (Factorial({"nothing": (1.0,)}),
         "block 'b''s factorial varies 'nothing', which is no setting the task declares"),
        (Factorial({"reward_correct": (0.1, 0.2)}),
         "block 'b''s factorial varies 'reward_correct', a bounded setting, which the subject's "
         "bounded config sets and no condition varies (welfare)"),
        (Factorial({"target_x": [-8.0, 8.0]}),
         "levels of 'target_x' are [-8.0, 8.0], and a factor's levels are a tuple of one or more"),
        (Factorial({"target_x": ()}), "levels of 'target_x' are (), and a factor's levels"),
        (Factorial({"target_x": ("far",)}),
         "factorial gives 'target_x' the level 'far', and it takes a finite number (deg)"),
        (Factorial({"target_x": (True,)}), "factorial gives 'target_x' the level True"),
        (Factorial({"target_appearance": ("disc",)}),
         "factorial gives 'target_appearance' the level 'disc', and it is one of (Disc("),
        (Factorial(two, exclude=[{"target_x": 8.0}]),
         "factorial's exclusions are [{'target_x': 8.0}], and they are a tuple of dicts"),
        (Factorial(two, exclude=("target_x",)),
         "factorial excludes 'target_x', and an exclusion is a dict of one or more factors"),
        (Factorial(two, exclude=({},)), "factorial excludes {}, and an exclusion is a dict"),
        (Factorial(two, exclude=({"target_y": 0.0},)),
         "factorial excludes {'target_y': 0.0}, and 'target_y' is not one of its factors "
         "('target_x')"),
        (Factorial(two, exclude=({"target_x": 3.0},)),
         "factorial excludes {'target_x': 3.0}, and 3.0 is not one of 'target_x''s levels "
         "(8.0, -8.0)"),
        (Factorial(two, exclude=({"target_x": 8.0}, {"target_x": -8.0})),
         "factorial's exclusions leave no condition: they exclude every combination of its "
         "levels; exclude fewer"),
        (Factorial(two, targets=[("target_x=8.0", 2)]),
         "factorial's targets are [('target_x=8.0', 2)], and they are a dict"),
        (Factorial(two, targets={"target_x=3.0": 2}),
         "factorial's targets name 'target_x=3.0', and it makes no condition of that name; its "
         "conditions are named from their levels, such as 'target_x=8.0'"),
        (Factorial(two, exclude=({"target_x": 8.0},), targets={"target_x=8.0": 2}),
         "factorial's targets name 'target_x=8.0', and it makes no condition of that name"),
        (Factorial({"target_x": (8.0,)}, target=-1),
         "block 'b''s condition 'target_x=8.0' has target -1"),
    ):
        found = _found(_with(p=Plan([Block("b", [NEAR], factorial=factorial)])))
        assert [f.code for f in found] == ["bad-plan"], (factorial, found)
        assert said in found[0].detail
    hand = Condition("target_x=8.0", {"target_x": 8.0}, target=1)
    found = _found(_with(p=Plan([Block("b", [hand], factorial=Factorial(two))])))
    assert [f.code for f in found] == ["bad-plan"], found
    assert "block 'b' has two conditions named 'target_x=8.0'" in found[0].detail

    class Thing:
        """A choice Python writes by its place in memory."""

    stages = Plan([Block("easy", [NEAR], criterion=(0.8, 10)),
                   Block("mid", [], factorial=Factorial({"target_x": (5.0, 12.0)}, target=10)),
                   Block("hard", [FAR], criterion=(0.8, 10))],
                  order=ByCriterion(fall_back=(0.5, 10)), time_limit_s=600.0)
    assert _codes(_with(p=stages), ("bad-plan", "fall-back-unjudged", "empty-block")) == []
    odd = Thing()
    task = _redeclared(BASE, Param("thing", unit="thing", choices=(odd,)))
    found = _found(_with(task, p=Plan([Block("b", [NEAR],
                                             factorial=Factorial({"thing": (odd,)}))])))
    assert [f.code for f in found] == ["bad-plan"], found
    assert ("by its place in memory, which names its conditions differently in every process"
            in found[0].detail)


def test_a_designed_blocks_faults_are_refused():
    """The C3 plan's calls 15 and 16 (the spec's §5, §11: "a designed block's written target
    contradicting its sequence; a priming feature with fewer than two values"): a sequence of depth
    under 2 or cycles under 1, over fewer than 2 conditions, owing other than `cycles *
    n**(depth - 1)` each, running more trials than it plans (the outline review's I-3), ending on
    a criterion, or at a training progression's top stage (review M-8); a priming block on no
    setting, one a condition does not set to a value or sets to fewer than two, with not exactly
    one of a chance from 0 to 1 and runs of whole lengths, with no number of trials or time limit,
    owing trials, or ending on a criterion. A priming block may be a top stage."""
    sequence = Block("seq", [NEAR, FAR], order=SequenceBalanced())
    primed = Block("prime", [_owing(NEAR, 0), _owing(FAR, 0)],
                   order=Priming("target_x", chance=0.8), trials=100)
    assert _codes(_with(p=Plan([sequence, primed]))) == []
    for block, said in (
        (dataclasses.replace(sequence, order=SequenceBalanced(depth=1)),
         "block 'seq''s sequence has depth 1, and a depth is a whole number from 2"),
        (dataclasses.replace(sequence, order=SequenceBalanced(depth=2.5)),
         "block 'seq''s sequence has depth 2.5"),
        (dataclasses.replace(sequence, order=SequenceBalanced(cycles=0)),
         "block 'seq''s sequence has 0 cycles, and its cycles are a whole number from 1"),
        (dataclasses.replace(sequence, conditions=[_owing(NEAR, 1)]),
         "block 'seq' is sequence-balanced over 1 condition(s), and a sequence balances how 2 or "
         "more follow one another"),
        (dataclasses.replace(sequence, conditions=[NEAR, _owing(FAR, 4)]),
         "block 'seq''s sequence plays each condition 2 times past its lead-ins (5 trials, 1 "
         "cycle(s) of 5, each opening on a lead-in of 1), and 'far' is owed otherwise; write "
         "target=2 for each"),
        (dataclasses.replace(sequence, order=SequenceBalanced(cycles=2)),
         "block 'seq''s sequence plays each condition 4 times past its lead-ins (10 trials, 2 "
         "cycle(s) of 5, each opening on a lead-in of 1), and 'near', 'far' are owed otherwise; "
         "write target=4 for each"),
        (dataclasses.replace(sequence, order=SequenceBalanced(depth=3)),
         "plays each condition 4 times past its lead-ins (10 trials, 1 cycle(s) of 10, each "
         "opening on a lead-in of 2)"),
        (dataclasses.replace(sequence, trials=6),
         "block 'seq' runs 6 trials, past its sequence (5 trials, 1 cycle(s) of 5, each opening "
         "on a lead-in of 1), which ends it first; write trials=5 or fewer, or none"),
        (dataclasses.replace(sequence, criterion=(0.8, 10)),
         "block 'seq' plays a designed order, SequenceBalanced, and ends on a criterion"),
        (dataclasses.replace(primed, criterion=(0.8, 10)),
         "block 'prime' plays a designed order, Priming, and ends on a criterion"),
        (dataclasses.replace(primed, order=Priming("target_x")),
         "block 'prime''s priming gives neither a chance nor runs; give exactly one"),
        (dataclasses.replace(primed, order=Priming("target_x", chance=0.5, runs=(3, 7))),
         "block 'prime''s priming gives both a chance and runs"),
        (dataclasses.replace(primed, order=Priming("target_x", chance=1.5)),
         "block 'prime''s chance of a repeat is 1.5, and a chance is a number from 0 to 1"),
        (dataclasses.replace(primed, order=Priming("target_x", chance=True)),
         "chance of a repeat is True"),
        (dataclasses.replace(primed, order=Priming("target_x", runs=(0, 3))),
         "block 'prime''s runs are (0, 3), and runs are (low, high), whole numbers with 1 <= low "
         "<= high"),
        (dataclasses.replace(primed, order=Priming("target_x", runs=(7, 3))), "runs are (7, 3)"),
        (dataclasses.replace(primed, order=Priming("target_x", runs=(3.0, 7))),
         "runs are (3.0, 7)"),
        (dataclasses.replace(primed, order=Priming("target_x", runs=[3, 7])), "runs are [3, 7]"),
        (dataclasses.replace(primed, trials=None),
         "block 'prime' primes with no number of trials and no time limit"),
        (dataclasses.replace(primed, conditions=[_owing(NEAR, 0), _owing(FAR, 1)]),
         "block 'prime' primes, and 'far' is owed trials; a priming block owes none"),
        (dataclasses.replace(primed, order=Priming("nothing", chance=0.5)),
         "block 'prime' primes 'nothing', which is no setting the task declares"),
        (dataclasses.replace(primed, conditions=[_owing(NEAR, 0), Condition("blank", {}, 0)]),
         "block 'prime' primes 'target_x', and its condition(s) 'blank' set it to no value"),
        (dataclasses.replace(primed, conditions=[
            _owing(NEAR, 0), Condition("ranged", {"target_x": Uniform(2.0, 8.0, repeat=FRESH)},
                                       0)]),
         "its condition(s) 'ranged' set it to no value"),
        (dataclasses.replace(primed, conditions=[
            _owing(NEAR, 0), Condition("also", {"target_x": 5.0}, 0)]),
         "block 'prime' primes 'target_x', which its conditions set to 1 value(s), and priming "
         "repeats or switches between 2 or more"),
    ):
        found = _found(_with(p=Plan([block])))
        assert [f.code for f in found] == ["bad-plan"], (block, found)
        assert said in found[0].detail
    easy = Block("easy", [NEAR], criterion=(0.8, 10))
    found = _found(_with(p=Plan([easy, sequence], order=ByCriterion(), time_limit_s=600.0)))
    assert [f.code for f in found] == ["bad-plan"], found
    assert "block 'seq' is the top stage of a training progression" in found[0].detail
    assert _codes(_with(p=Plan([easy, primed], order=ByCriterion(), time_limit_s=600.0))) == []


def test_a_sequence_balanced_stage_below_a_progressions_top_is_warned_it_moves_up_when_played_out():
    """The PI, 2026-10-31, on the engine C3 plan's Appendix B, item 10, "Only warn at load": a
    training progression's stage below its top that plays a sequence-balanced order ends when its
    sequence is played out, eased trials or not, since a sequence is not extended, so the
    animal moves up then however many of its trials a live change eased (the C3 plan's calls 15
    and 18, built as they stand). The load says so, `sequence-stage-moves-up`, accepted in every
    kind; a sequence in a plan of another order, and a priming stage, are not warned. At the top a
    sequence is refused (review M-8)."""
    sequence = Block("seq", [NEAR, FAR], order=SequenceBalanced())
    easy = Block("easy", [NEAR], criterion=(0.8, 10))
    primed = Block("prime", [_owing(NEAR, 0), _owing(FAR, 0)],
                   order=Priming("target_x", chance=0.8), trials=100)
    codes = ("sequence-stage-moves-up", "bad-plan")

    found = _found(_with(p=Plan([sequence, easy], order=ByCriterion(), time_limit_s=600.0)),
                   codes)
    assert [(f.code, f.is_warning, f.accepted_in) for f in found] == [
        ("sequence-stage-moves-up", True, SESSION_KINDS)]
    assert found[0].detail == (
        "plan 'p': block 'seq' is a training progression's stage below its top, and it is "
        "sequence-balanced: it moves up when its sequence is played out, eased trials or not, "
        "since a sequence plays each of its places once and is not extended, so trials a live "
        "change made easier can move the animal up; each such trial's line names what eased it "
        "(eased); a stage the animal must pass on its own is better with an ordinary order and a "
        "criterion")
    assert _found(_with(p=Plan([sequence, easy])), codes) == []
    assert _found(_with(p=Plan([primed, easy], order=ByCriterion(), time_limit_s=600.0)),
                  codes) == []


def test_an_arrays_found_by_is_its_look_or_a_cue():
    """The PI, 2026-10-31, on the engine C3 plan's Appendix B, item 17: an array says what names
    its target (`found_by`), its look or a cue, which decides whether the load's two look checks
    refuse it or only warn (`check.impossible`); a word that is neither is refused, `bad-array`,
    saying both, since a misspelling would otherwise soften a pop-out search's refusal."""
    direction = Param("dir", unit="deg", low=0.0, high=360.0, start=90.0)

    def refused(found_by) -> list[str]:
        task = _aimed(direction, looks=Array(n=4, radius=2.0, found_by=found_by))
        return [f.detail for f in check_task(task) if f.code == "bad-array"]

    assert refused("look") == refused("cue") == []
    assert refused("cued") == [
        "array 's' is found by 'cued', and an array's found_by is one of 'look', 'cue': 'look', "
        "its target the odd one out by its look, or 'cue', something else the trial shows naming "
        "it"]


def test_a_designed_orders_again_at_once_is_true_or_false():
    """The C3 plan's engineering review, M-4: `again_at_once='yes'` loaded, and the scheduler read
    any value as true or false. Either designed order refuses one that is neither."""
    sequence = Block("seq", [NEAR, FAR], order=SequenceBalanced(again_at_once="yes"))
    primed = Block("prime", [_owing(NEAR, 0), _owing(FAR, 0)],
                   order=Priming("target_x", chance=0.8, again_at_once=1), trials=100)
    for block, said in ((sequence, "block 'seq''s again_at_once is 'yes', and it is True"),
                        (primed, "block 'prime''s again_at_once is 1, and it is True")):
        found = _found(_with(p=Plan([block])))
        assert [f.code for f in found] == ["bad-plan"], found
        assert said in found[0].detail
    assert _codes(_with(p=Plan([dataclasses.replace(
        sequence, order=SequenceBalanced(again_at_once=True))]))) == []


def test_priming_runs_may_be_drawn_from_any_distribution_of_lengths_from_1():
    """The C3 plan's science review, I-8: a priming block's run lengths may be drawn by any of the
    five distributions, each length its draw rounded down -- a non-aging one keeps a switch as
    likely after every trial of a run -- and one that cannot be drawn, or can give a length under
    1, or anything but numbers, is refused."""
    def primed(runs) -> Block:
        return Block("prime", [_owing(NEAR, 0), _owing(FAR, 0)],
                     order=Priming("target_x", runs=runs), trials=100)

    for runs in (NonAging(3.0, 5.0, 12.0), Weighted((2, 4), (1, 1)), Uniform(2.0, 6.0),
                 Listed((3, 5, 7)), TruncatedNormal(5.0, 1.0, low=2.0, high=8.0)):
        assert _codes(_with(p=Plan([primed(runs)]))) == [], runs
    for runs, said in (
        (Uniform(0.5, 4.0), "block 'prime''s runs cannot be drawn: it can give 0.5, and a run is "
                            "at least 1 trial long"),
        (TruncatedNormal(4.0, 1.0),
         "runs cannot be drawn: it has no lowest or highest to be cut to; give it low= and high="),
        (Weighted(("short", "long"), (1, 1)), "its lengths are ('short', 'long'), and a run's "
                                              "length is a number of trials"),
        (Uniform(4.0, 2.0), "its lowest, 4.0, is above its highest, 2.0"),
    ):
        found = _found(_with(p=Plan([primed(runs)])))
        assert [f.code for f in found] == ["bad-plan"], (runs, found)
        assert said in found[0].detail


def test_a_same_draw_a_drum_can_hold_and_a_same_wait_brought_back_at_once_are_warned():
    """The C3 plan's science review, I-5: a block that drums, drawing a clear-cut setting `same`
    (a drum can hold its hardest value try after try), and a designed block that brings a broken
    trial back at once, drawing a non-aging wait `same` (the repeat's wait is known to outlast the
    moment it broke), are each warned, accepted in every kind; `fresh`, a block that does not
    drum or bring a trial back, and a setting that is no difficulty one are not."""
    codes = ("same-in-drum", "same-wait-at-once")

    def warned(task: Task) -> list:
        return [(f.code, f.blocking, f.accepted_in) for f in _found(task, codes)]

    drummed = Block("drum", [NEAR, FAR], drum=True)
    hard = {"fix_window": Uniform(1.0, 2.0, repeat=SAME)}
    assert warned(_with(draws=hard, p=Plan([drummed]))) == [
        ("same-in-drum", False, SESSION_KINDS)]
    found = _found(_with(draws=hard, p=Plan([drummed])), codes)
    assert "block 'drum' drums and draws 'fix_window' same, a clear-cut setting" in found[0].detail
    assert warned(_with(draws={"fix_window": Uniform(1.0, 2.0, repeat=FRESH)},
                        p=Plan([drummed]))) == []
    assert warned(_with(draws=hard, p=Plan([dataclasses.replace(drummed, drum=False)]))) == []
    assert warned(_with(draws={"target_y": Uniform(-1.0, 1.0, repeat=SAME)},
                        p=Plan([drummed]))) == []
    again = Block("seq", [NEAR, FAR], order=SequenceBalanced(again_at_once=True))
    wait = {"fix_hold": NonAging(0.2, 0.3, 0.6, repeat=SAME)}
    assert warned(_with(draws=wait, p=Plan([again]))) == [
        ("same-wait-at-once", False, SESSION_KINDS)]
    assert warned(_with(draws=wait, p=Plan([dataclasses.replace(
        again, order=SequenceBalanced())]))) == []
    assert warned(_with(draws={"fix_hold": NonAging(0.2, 0.3, 0.6, repeat=FRESH)},
                        p=Plan([again]))) == []
    assert warned(_with(draws={"fix_window": Uniform(1.0, 2.0, repeat=SAME)},
                        p=Plan([again]))) == []


def test_a_drum_block_with_a_setting_keyed_by_no_text_is_refused_not_a_traceback():
    """The review of Task 5, Important 1 (Call 2: a finding at load with a sentence, never a task
    file that will not import): a drumming block whose condition draws `same` under a key that is
    no text and under a setting's name once made `check_task` sort the two together and raise.
    The key is refused as no setting, and the setting is still warned."""
    ranged = Condition("c", {5: Uniform(1.0, 2.0, repeat=SAME),
                             "fix_window": Uniform(1.0, 2.0, repeat=SAME)}, target=1)
    found = _found(_with(p=Plan([Block("drum", [ranged], drum=True)])),
                   ("bad-draw", "same-in-drum"))
    assert [f.code for f in found] == ["bad-draw", "same-in-drum"], found
    assert "draws 5, which is no setting the task declares" in found[0].detail
    assert "draws 'fix_window' same" in found[1].detail


def test_a_drum_warns_a_setting_once_a_block_and_reads_a_factorials_conditions():
    """The review of Task 5, Minor 1 and Minor 8: two conditions drawing one setting `same` from
    ranges of different kinds are one warning, not two, and a factorial's level that is its own
    `same` range is read like a hand-listed condition's."""
    drum = Block("drum", [Condition("a", {"fix_window": Uniform(1.0, 2.0, repeat=SAME)}, 1),
                          Condition("b", {"fix_window": NonAging(0.2, 0.3, 0.6, repeat=SAME)}, 1)],
                 drum=True)
    assert [f.code for f in _found(_with(p=Plan([drum])), ("same-in-drum",))] == ["same-in-drum"]
    made = Block("drum", [], factorial=Factorial(
        {"fix_window": (Uniform(1.0, 2.0, repeat=SAME), 1.5)}), drum=True)
    found = _found(_with(p=Plan([made])), ("bad-draw", "bad-plan", "same-in-drum"))
    assert [f.code for f in found] == ["same-in-drum"], found


def test_a_same_wait_brought_back_at_once_is_warned_in_these_words():
    """The review of Task 5, Minor 8: `same-wait-at-once`'s sentence."""
    again = Block("seq", [NEAR, FAR], order=SequenceBalanced(again_at_once=True))
    found = _found(_with(draws={"fix_hold": NonAging(0.2, 0.3, 0.6, repeat=SAME)},
                         p=Plan([again])), ("same-wait-at-once",))
    assert [f.detail for f in found] == [
        "plan 'p': block 'seq' brings a broken trial straight back and draws the wait "
        "'fix_hold' same, so the repeat's wait is known to last past the moment its trial "
        "broke, a cue in the very time the wait keeps unforeseeable; draw it fresh (the C3 "
        "plan's science review, I-5)"]


def test_an_array_found_by_a_misspelt_word_is_said_once_for_a_stimulus_shown_twice():
    """The review of Task 5, Minor 8: each stimulus and word is said once, however many states
    `Show` the array."""
    task = _aimed(Param("dir", unit="deg", low=0.0, high=360.0, start=90.0),
                  looks=Array(n=4, radius=2.0, found_by="cued"))
    trial = task.structures["t"]
    state = trial.states[0]
    again = dataclasses.replace(state, name="again")
    task = dataclasses.replace(task, structures={"t": dataclasses.replace(
        trial, states=[*trial.states, again])})
    assert len([f for f in check_task(task) if f.code == "bad-array"]) == 1


def test_a_block_of_a_refused_factorial_alone_gets_the_factorials_refusal_only():
    """The review of Task 5, Minor 10: a block with no hand-listed conditions whose factorial is
    refused makes none, and was also told it "has no conditions" (XC-381), sending the author the
    wrong way; the factorial's own refusal is the one sentence."""
    found = _found(_with(p=Plan([Block("b", [], factorial=Factorial({"nothing": (1.0,)}),
                                       trials=5)])))
    assert [f.code for f in found] == ["bad-plan"], found
    assert "varies 'nothing'" in found[0].detail


def test_a_designed_block_meets_no_empty_block_or_late_condition_warning():
    """The outline review's M-8: a designed block owes what its order says -- a priming block
    none, a sequence each condition alike -- so a priming block ending on its time alone is not
    "a block over before it starts" (`empty-block`), nor are its targets of 0 "late" ones
    (`late-condition`); the same blocks shuffled are."""
    warned = ("empty-block", "late-condition", "bad-plan")
    timed = Block("prime", [_owing(NEAR, 0), _owing(FAR, 0)], order=Priming("target_x",
                                                                            runs=(3, 7)),
                  time_limit_s=300.0)
    assert _codes(_with(p=Plan([timed])), warned) == []
    assert _codes(_with(p=Plan([dataclasses.replace(timed, order=Shuffled())])), warned) == [
        "empty-block"]
    late = Block("prime", [_owing(NEAR, 0), FAR], order=Priming("target_x", chance=0.5),
                 trials=50)
    assert _codes(_with(p=Plan([late])), warned) == ["bad-plan"]
    assert _codes(_with(p=Plan([dataclasses.replace(late, order=Shuffled())])), warned) == [
        "late-condition"]


def test_a_sequence_a_count_or_time_can_cut_is_warned():
    """The spec's §5 ("a trial count or time limit can cut a cycle short; the record says so") and
    §11 ("a designed block whose trial count or time limit can end it mid-cycle, unbalanced"),
    with the outline review's I-3: a sequence-balanced block ends on its plan played out or its
    trials run, whichever comes first, owing nothing then, so a number of trials under its plan,
    or a time limit, its own or its plan's, is warned, `cut-sequence`, in every kind."""
    sequence = Block("seq", [NEAR, FAR], order=SequenceBalanced())

    def cut(plan: Plan) -> list:
        return _found(_with(p=plan), ("cut-sequence", "bad-plan"))

    assert cut(Plan([sequence])) == []
    assert cut(Plan([dataclasses.replace(sequence, trials=5)])) == []
    for plan, said in (
        (Plan([dataclasses.replace(sequence, trials=3)]), "its 3 trials end it before its 5"),
        (Plan([dataclasses.replace(sequence, time_limit_s=60.0)]),
         "its time limit can end it first"),
        (Plan([sequence], time_limit_s=600.0), "the plan's time limit can end it first"),
    ):
        found = cut(plan)
        assert [f.code for f in found] == ["cut-sequence"], found
        assert found[0].is_warning and found[0].accepted_in == SESSION_KINDS
        assert found[0].detail == (
            f"plan 'p': block 'seq''s sequence (5 trials, 1 cycle(s) of 5, each opening on a "
            f"lead-in of 1) can be cut short -- {said} -- and a sequence cut short is not "
            f"balanced: the transitions it did not play are missing, recorded on its block's "
            f"planned sequence, and nothing makes up the trials it did not play; to play it "
            f"whole, write trials=5 or none, and no time limit")


def test_a_condition_name_over_200_characters_is_warned_naming_both_limits():
    """The controller's ruling 5 and the outline review's M-14 (the C3 plan's call 36): a
    condition's name over 200 characters cannot be cleared from the console (a clear names its
    condition in at most `link.TEXT_LIMIT`), and over 255 wl-preproc's main-sequence table drops
    its group; warned in every kind, naming both, a generated name most likely."""
    def warned(task: Task) -> list:
        return _found(task, ("long-condition-name",))

    def named(name: str) -> Task:
        return _with(p=Plan([Block("b", [Condition(name, {"target_x": 5.0}, target=1)])]))

    assert warned(named("n" * 200)) == []
    found = warned(named("n" * 201))
    assert [f.code for f in found] == ["long-condition-name"], found
    assert found[0].is_warning and found[0].accepted_in == SESSION_KINDS
    assert found[0].detail == (
        f"plan 'p': block 'b''s condition {'n' * 40 + '…'!r} is named in 201 characters, over "
        f"200: a person clears what a condition owes by naming it in at most 200, so cannot clear "
        f"this one from the console, and wl-preproc's main-sequence table groups trials by "
        f"condition names of up to 255 characters, so this one's trials still group, though a "
        f"name past 255 would not; give it, or its factors and levels, shorter names")
    found = warned(named("n" * 256))
    assert [f.code for f in found] == ["long-condition-name"], found
    assert ("groups trials by condition names of up to 255 characters, so this one's trials are "
            "left out of their condition's group; give it") in found[0].detail
    long = "x" * 195
    task = _redeclared(BASE, Param(long, unit="deg", low=0.0, high=1000.0))
    found = warned(_with(task, p=Plan([Block(
        "b", [], factorial=Factorial({long: (10.0, 100.0)}))])))
    assert [f.detail.split(" is named in ")[1][:3] for f in found] == ["201"]
    assert check.CONDITION_NAME_LIMIT == link.TEXT_LIMIT == 200


@pytest.mark.parametrize("name", ["fixation_detection", "adaptive_detection", "visual_search",
                                  "visual_search_training", "calibration"])
def test_no_reference_task_gives_any_new_code(name):
    """The C3 plan's call 34: no reference task draws, makes conditions from factors or plays a
    designed order, so none gives a code these checks add."""
    task = _load_task(Path(f"tasks/{name}.py"))

    assert not task.draws and not task.plans
    assert {f.code for f in check_task(task)} & {
        "bad-draw", "bad-array", "cut-sequence", "sequence-stage-moves-up",
        "long-condition-name"} == set()
