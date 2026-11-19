"""What a task file declares for the console's boxes (the console interface design's goals 5, 6 and
8, and its calls on steps and percents; the PI, 2026-11-19: "Plain name, code name small", whole
numbers with "no decimal option", "One box after Timing"): a plain name (`Param.label`) and one
sentence (`Param.help`), whole numbers (`Param.whole`), a step (`Param.step`, else the unit's,
`task.step_of`), a fraction shown as a percent (`Param.percent`), and groups of settings that
share one box and one Apply, read as a sentence where one is given (`task.Group`,
`Task.groups`). A value malformed on its own is refused as the setting or group is built; what
needs the task is judged at load (`bad-whole`, `bad-group`). Engine test material, run only in
the simulator: no number here is a timing claim about the rig.
"""

from __future__ import annotations

import ast
import dataclasses
import math
from pathlib import Path

import pytest

from wl_xcon.check import beyond_range, check_task
from wl_xcon.declarations import content_hash
from wl_xcon.task import (
    LABEL_LIMIT, REASON_LIMIT, UNIT_STEPS, After, Group, On, Outcome, Param, Reward, State,
    Task, Trial, step_of,
)

ROOT = Path(__file__).resolve().parents[1]

#: The sentence the pop-out's training rules read as (the design's goal 8), its two places
#: `move_up_bar` and `move_up_window`.
MOVE_UP = "Move up when at least {move_up_bar} of the last {move_up_window} answers are right"


def _task(*params: Param, groups: tuple = (), reward: str | None = None) -> Task:
    """A one-state task declaring `params` and `groups`; `reward` names a bounded-config entry
    its one state rewards through."""
    enter = [Reward(reward)] if reward else []
    return Task({"s": Trial(start="s", params=list(params), states=[
        State("s", enter=enter, go=[On(After(1.0), Outcome.NO_RESPONSE)])])},
        default="s", groups=groups)


def _found(task: Task, code: str) -> list[str]:
    return [finding.detail for finding in check_task(task) if finding.code == code]


# --- A plain name and one sentence -------------------------------------------------------------


@pytest.mark.parametrize("label", ["", "Hold on the fixation point", "é° cd/m²", "w" * 40])
def test_a_label_is_one_printable_line_of_40_at_most(label):
    """The box's plain name: printable text of `LABEL_LIMIT` (40) characters at most, refused
    otherwise as the setting is built, saying what is allowed and what was given."""
    assert LABEL_LIMIT == 40
    assert Param("fix_hold", unit="s", label=label).label == label
    for wrong in ("w" * 41, "two\nlines", "a\ttab", 3, None):
        with pytest.raises(ValueError, match=(
                r"parameter 'fix_hold': its plain name \(label\) is one printable line of 40 "
                r"characters at most, not ")):
            Param("fix_hold", unit="s", label=wrong)


@pytest.mark.parametrize("help_", ["", "How long the gaze stays on the point.", "h" * 120])
def test_help_is_one_printable_line_of_120_at_most(help_):
    """The box's one sentence, what the setting is: printable text of `REASON_LIMIT` (120)
    characters at most, as a limit's reason is, refused otherwise as the setting is built."""
    assert REASON_LIMIT == 120
    assert Param("fix_hold", unit="s", help=help_).help == help_
    for wrong in ("h" * 121, "two\nlines", "a\ttab", 3, None):
        with pytest.raises(ValueError, match=(
                r"parameter 'fix_hold': what it is \(help\) is one printable line of 120 "
                r"characters at most, not ")):
            Param("fix_hold", unit="s", help=wrong)


def test_labels_help_and_groups_are_part_of_what_the_task_declares():
    """Hashed as before (the design's "The record"): each moves the task's content hash, and a
    task declaring none of them hashes as it did."""
    plain = _task(Param("a", unit="s"), Param("b", unit="s"))
    assert content_hash(_task(Param("a", unit="s"), Param("b", unit="s"))) == content_hash(plain)
    for other in (
        _task(Param("a", unit="s", label="A"), Param("b", unit="s")),
        _task(Param("a", unit="s", help="An a."), Param("b", unit="s")),
        _task(Param("a", unit="s", whole=True), Param("b", unit="s")),
        _task(Param("a", unit="s", step=0.5), Param("b", unit="s")),
        _task(Param("a", unit="fraction", percent=True), Param("b", unit="s")),
        _task(Param("a", unit="s"), Param("b", unit="s"), groups=(Group("Both", ("a", "b")),)),
    ):
        assert content_hash(other) != content_hash(plain)


# --- Whole numbers -----------------------------------------------------------------------------


def test_a_whole_setting_declares_whole_start_low_and_high():
    """`whole=True` is judged at load (`bad-whole`): its start, lowest, highest and step are whole
    where given, `4.0` among them; each one that is not named. A setting not declared whole is
    not judged, and `whole` is True or False, refused otherwise as the setting is built."""
    def whole(**given) -> Param:
        return Param("set_size", unit="objects", whole=True, **{"low": 1, "high": 36, **given})

    assert _found(_task(whole(start=4)), "bad-whole") == []
    assert _found(_task(whole(start=4.0, low=1.0, high=36.0, step=2)), "bad-whole") == []
    assert _found(_task(whole(low=None, high=None)), "bad-whole") == []
    assert _found(_task(whole(start=4.5)), "bad-whole") == [
        "'set_size' is declared whole, and its start, 4.5, is not a whole number"]
    assert _found(_task(whole(low=1.5, high=36.5, step=0.5)), "bad-whole") == [
        "'set_size' is declared whole, and its lowest, 1.5, its highest, 36.5 and its step, 0.5, "
        "are not whole numbers"]
    assert all(finding.blocking for finding in check_task(_task(whole(start=4.5)))
               if finding.code == "bad-whole")
    assert _found(_task(Param("set_size", unit="objects", low=1, high=36, start=4.5)),
                  "bad-whole") == []
    for wrong in (1, "yes", None):
        with pytest.raises(ValueError, match=r"parameter 'set_size': whole is True or False"):
            Param("set_size", unit="objects", whole=wrong)


def test_the_load_check_of_whole_numbers_is_said_of_the_declaration_never_of_a_value():
    """A value past a whole setting's highest is refused for the limit (`past-limit`), and the
    widened re-check does not add a `bad-whole` naming a bound the task never declared: whether a
    value is whole is the live path's to judge (the plan's Task 3), never `Session.set`'s."""
    task = _task(Param("set_size", unit="objects", low=1, high=36, start=4, whole=True))
    codes = [finding.code for finding in beyond_range(task, {"set_size": 36.5})]

    assert "past-limit" in codes and "bad-whole" not in codes


# --- Steps -------------------------------------------------------------------------------------


def test_the_step_comes_from_the_unit_unless_declared():
    """The design's call (the plan's Global Constraints): each unit's step; a whole setting steps
    by 1; any other unit by 0.01; a step the setting declares wins over both."""
    assert UNIT_STEPS == {"s": 0.05, "deg": 0.1, "mL": 0.01, "cd/m2": 1.0, "fraction": 0.05,
                          "× disc radius": 0.1, "%": 1.0}
    for unit, step in UNIT_STEPS.items():
        assert step_of(Param("x", unit=unit)) == step
    assert step_of(Param("x", unit="objects", whole=True)) == 1
    assert step_of(Param("x", unit="s", whole=True)) == 1
    assert step_of(Param("x", unit="objects")) == 0.01
    assert step_of(Param("x", unit="index")) == 0.01
    assert step_of(Param("x", unit="s", step=0.01)) == 0.01
    assert step_of(Param("x", unit="objects", whole=True, step=2)) == 2


@pytest.mark.parametrize("step", [0, -0.1, math.nan, math.inf, True, "0.1", 10 ** 400])
def test_a_declared_step_is_a_positive_finite_number(step):
    with pytest.raises(ValueError, match=(
            r"parameter 'x': its step is a number above 0 that a float holds, or None for "
            r"its unit's, not ")):
        Param("x", unit="s", step=step)


# --- A fraction shown as a percent -------------------------------------------------------------


def test_percent_is_for_a_fraction_only():
    """The design's call: a fraction may be shown ×100 with `%`; the setting keeps the fraction.
    On any other unit it is refused as the setting is built, and it is True or False."""
    assert Param("move_up_bar", unit="fraction", low=0.0, high=1.0, percent=True).percent
    with pytest.raises(ValueError, match=(
            r"parameter 'fix_hold': percent shows a fraction as a percent, and its unit is 's', "
            r"not 'fraction'")):
        Param("fix_hold", unit="s", percent=True)
    with pytest.raises(ValueError, match=r"parameter 'move_up_bar': percent is True or False"):
        Param("move_up_bar", unit="fraction", percent=1)


# --- Groups ------------------------------------------------------------------------------------


def test_a_group_names_settings_the_task_has_each_once():
    """Judged at load (`bad-group`, blocking): each name a setting the task declares, each
    setting in one group, no two groups of one name, and never a ceiling -- a welfare-bounded
    setting, `reward_correct` the one today, or any entry the task rewards through -- since a
    reward size is never applied with others (the design's call; XC-527)."""
    a, b, c = (Param(name, unit="s") for name in ("a", "b", "c"))
    assert _found(_task(a, b, c, groups=(Group("First", ("a", "b")), Group("Second", ("c",)))),
                  "bad-group") == []
    assert _found(_task(a, b, groups=(Group("First", ("a", "ghost")),)), "bad-group") == [
        "group 'First' names 'ghost', which the task does not declare"]
    assert _found(_task(a, b, groups=(Group("First", ("a", "b")), Group("Second", ("b",)))),
                  "bad-group") == [
        "setting 'b' is in group 'First' and in group 'Second'; a setting sits in one box"]
    assert _found(_task(a, b, groups=(Group("Both", ("a",)), Group("Both", ("b",)))),
                  "bad-group") == ["two groups are named 'Both'; a box's title names one"]
    ceiling = ("group 'Pay' holds 'reward_correct', a welfare-bounded setting: a reward size is "
               "sent alone, by its own Apply")
    assert _found(_task(a, groups=(Group("Pay", ("a", "reward_correct")),)), "bad-group") == [
        ceiling]
    assert _found(_task(a, Param("reward_correct", unit="mL"),
                        groups=(Group("Pay", ("a", "reward_correct")),)), "bad-group") == [ceiling]
    assert _found(_task(a, Param("juice", unit="mL"), reward="juice",
                        groups=(Group("Pay", ("a", "juice")),)), "bad-group") == [
        ceiling.replace("'reward_correct'", "'juice'")]
    assert all(finding.blocking for finding in check_task(
        _task(a, groups=(Group("First", ("ghost",)),))) if finding.code == "bad-group")


def test_a_groups_settings_share_one_section():
    """The controller's ruling on the plan's Task 3: a group's box sits in the section its settings
    share (`task.section_of`), so a group across two is refused at load (`bad-group`, blocking),
    naming the sections in its settings' order; a setting named into the section of the others is
    accepted."""
    timing, other = Param("hold", unit="s"), Param("ring", unit="deg")
    moved = Param("ring", unit="deg", section="Timing")
    assert _found(_task(timing, moved, groups=(Group("G", ("hold", "ring")),)), "bad-group") == []
    split = _task(timing, other, groups=(Group("G", ("hold", "ring")),))
    assert _found(split, "bad-group") == [
        "group 'G' holds settings of the sections 'Timing', 'Other'; its box sits in one "
        "section, so its settings share one"]
    assert all(f.blocking for f in check_task(split) if f.code == "bad-group")


def test_two_settings_with_one_plain_name_are_refused():
    """The controller's ruling on the plan's Task 3: two settings declaring one plain name, as a
    person reads it -- case and runs of spaces aside -- are refused at load (`bad-label`,
    blocking), naming both, since their boxes would read alike. Different names, and settings with
    none, pass."""
    hold = Param("fix_hold", unit="s", label="Fixation hold")
    assert _found(_task(hold, Param("target_hold", unit="s", label="Target hold"),
                        Param("a", unit="s"), Param("b", unit="s")), "bad-label") == []
    twice = _task(hold, Param("target_hold", unit="s", label="fixation  HOLD"))
    assert _found(twice, "bad-label") == [
        "settings 'fix_hold', 'target_hold' share the plain name 'Fixation hold'; their boxes "
        "would read alike, so each takes a name of its own"]
    assert all(f.blocking for f in check_task(twice) if f.code == "bad-label")


def test_a_groups_shape_is_refused_as_it_is_built():
    """A group's title is one printable line of `LABEL_LIMIT` at most and not empty; it names its
    settings as a tuple of names, one at least, each once; a task's groups are a tuple of
    `Group`s."""
    assert Group("Move up", ("move_up_bar", "move_up_window")).sentence == ""
    for name in ("", "t" * 41, "two\nlines", 3):
        with pytest.raises(ValueError, match=r"a group's title is one printable line of 40"):
            Group(name, ("a",))
    for settings in ((), "ab", ["a", "b"], ("a", ""), ("a", 3)):
        with pytest.raises(ValueError, match=r"group 'G' names its settings as a tuple of"):
            Group("G", settings)
    with pytest.raises(ValueError, match=r"group 'G' names 'a' twice"):
        Group("G", ("a", "b", "a"))
    for groups in ([Group("G", ("a",))], (("a",),), Group("G", ("a",))):
        with pytest.raises(ValueError, match=r"a task's groups are a tuple of Groups"):
            _task(Param("a", unit="s"), groups=groups)


def test_a_groups_sentence_places_each_of_its_settings_once():
    """Its sentence names its settings as `{setting}` places, each exactly once, read by the
    format parser (`{{` a brace); a missing place, an unknown one, one twice, one with a format
    or a conversion, an empty `{}` and an unmatched brace are refused as the group is built. Its
    words, the places left out, are one printable line of `REASON_LIMIT` at most."""
    settings = ("move_up_bar", "move_up_window")
    assert Group("Move up", settings, sentence=MOVE_UP).sentence == MOVE_UP
    assert Group("G", ("a",), sentence="{{at least}} {a}").sentence == "{{at least}} {a}"
    assert Group("G", ("a",), sentence="{a}" + "w" * 120).sentence.endswith("w")
    wrong = {
        "Move up when at least {move_up_bar} answers are right":
            r"its sentence has no place for 'move_up_window'",
        MOVE_UP + " {move_up_rate}": r"its sentence has a place for 'move_up_rate', which is not "
                                     r"one of its settings",
        MOVE_UP + " {move_up_bar}": r"its sentence has a place for 'move_up_bar' twice",
        MOVE_UP.replace("{move_up_bar}", "{move_up_bar:.0%}"):
            r"its sentence's place for 'move_up_bar' carries a format or a conversion",
        MOVE_UP.replace("{move_up_bar}", "{move_up_bar!r}"):
            r"its sentence's place for 'move_up_bar' carries a format or a conversion",
        MOVE_UP + " {}": r"its sentence has a place for '', which is not one of its settings",
        MOVE_UP + " }": r"its sentence is not read as words and places",
        MOVE_UP + " {": r"its sentence is not read as words and places",
        MOVE_UP + "\n": r"its sentence's words are one printable line of 120 characters",
        MOVE_UP + " " + "w" * 120: r"its sentence's words are one printable line of 120",
        3: r"its sentence's words are one printable line of 120",
    }
    for sentence, said in wrong.items():
        with pytest.raises(ValueError, match=r"group 'Move up': " + said):
            Group("Move up", settings, sentence=sentence)


# --- The reference tasks -----------------------------------------------------------------------


def test_the_reference_tasks_declare_whole_on_their_counts_and_nothing_else():
    """The controller's ruling 4: the engine's fixtures declare `whole=True` on their counts, the
    set sizes, and no plain name, sentence, step, percent or group (wl-xtasks' tasks, curated
    with the PI, carry those). **And on an index** (the controller's ruling on the plan's Task 3:
    "an index is whole"), the search tasks' `target_index`."""
    import importlib.util

    found: dict[str, set[str]] = {}
    for name in ("fixation_detection", "adaptive_detection", "visual_search",
                 "visual_search_training", "calibration"):
        spec = importlib.util.spec_from_file_location(f"ref_{name}", ROOT / "tasks" / f"{name}.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        task = module.TASK
        found[name] = {param.name for param in task.params if param.whole}
        assert task.groups == ()
        for param in task.params:
            assert (param.label, param.help, param.step, param.percent) == ("", "", None, False)
    assert found == {"fixation_detection": set(), "adaptive_detection": set(),
                     "visual_search": {"set_size", "target_index"},
                     "visual_search_training": {"set_size", "target_index"},
                     "calibration": set()}
    # The counts by unit, so a count added later without `whole` fails here.
    for name in found:
        tree = ast.parse((ROOT / "tasks" / f"{name}.py").read_text())
        counted = {
            node.args[0].value for node in ast.walk(tree)
            if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "Param"
            and any(k.arg == "unit" and getattr(k.value, "value", None) in (
                        "objects", "answers", "pairings", "trials", "index")
                    for k in node.keywords)
        }
        assert counted <= found[name], (name, counted)


def test_the_new_fields_leave_a_param_and_a_task_as_they_were():
    """Each field is added at a default that changes nothing a task does (`declarations.FORMAT`
    is not raised): no plain name, no sentence, not whole, the unit's step, no percent, no
    groups."""
    param = Param("x", unit="s")
    assert (param.label, param.help, param.whole, param.step, param.percent) == (
        "", "", False, None, False)
    assert _task(param).groups == ()
    assert {spec.name for spec in dataclasses.fields(Group)} == {"name", "settings", "sentence"}
