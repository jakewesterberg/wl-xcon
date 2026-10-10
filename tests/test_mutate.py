"""The mutation harness's own tests -- specifically, that its new escape hatch is narrow.

`tools/mutate.py` is the gate every other gate is checked by, and it has been wrong
four times, always the same way: quietly examining nothing and reporting success
(trap 7). `_already_inert` is a fifth change of exactly the dangerous shape -- a
category of result that does *not* fail the build -- so the point of this file is not
that it works on the case it was written for, but that it **refuses everything else**.

The detector is unit-tested rather than driven end to end because `mutate` runs the
whole pytest suite, and a test that invoked it from inside pytest would be running
this suite inside itself.
"""

from __future__ import annotations

import ast
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "wlx_mutate", Path(__file__).resolve().parents[1] / "tools" / "mutate.py"
)
mutate_tool = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(mutate_tool)
_already_inert = mutate_tool._already_inert


# ---------------------------------------------------------------------------
# What it must accept: bodies no mutation can reach
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "body",
    [
        "        return None",
        '        """A docstring and nothing else."""',
        "        ...",
        "        pass",
        '        """Docstring, then the same return."""\n        return None',
    ],
    ids=["return-none", "docstring-only", "ellipsis", "pass", "docstring-and-return"],
)
def test_a_body_that_already_returns_immediately_is_inert(body):
    source = f"class W:\n    def display(self, visible, frame) -> None:\n{body}\n"
    assert _already_inert(source, "display", "None")


def test_the_returned_value_has_to_match_not_merely_be_a_return():
    """`return []` under `--returns []` is inert; the same body under `--returns None`
    is a real mutation, because the function stops returning a list."""
    source = "def check(trial):\n        return []\n"
    assert _already_inert(source, "check", "[]")
    assert not _already_inert(source, "check", "None")


# ---------------------------------------------------------------------------
# What it must refuse -- the half that keeps the gate a gate
# ---------------------------------------------------------------------------


def test_a_real_body_is_never_inert():
    source = "def signal(self, frame):\n        return self.tracker.state(frame)\n"
    assert not _already_inert(source, "signal", "None")


def test_a_body_that_returns_late_is_not_inert():
    """Only the FIRST statement matters: a function that does work and then returns
    None is fully neutered by an early return, and that is a real mutation."""
    source = (
        "def display(self, visible, frame) -> None:\n"
        "        self.tracker.accept(self.source.poll(frame))\n"
        "        return None\n"
    )
    assert not _already_inert(source, "display", "None")


def test_one_real_definition_among_inert_ones_makes_the_whole_name_mutable():
    """All definitions of a name are neutered together, so the answer has to be about
    all of them. This is the case that would hide a genuine survivor: two worlds with
    no-op displays and a third that actually does something."""
    source = (
        "class Quiet:\n"
        "    def display(self, visible, frame) -> None:\n"
        "        return None\n"
        "class Scripted:\n"
        "    def display(self, visible, frame) -> None:\n"
        "        return None\n"
        "class Tracked:\n"
        "    def display(self, visible, frame) -> None:\n"
        "        self.tracker.accept(self.source.poll(frame))\n"
    )
    assert not _already_inert(source, "display", "None")


def test_a_name_that_is_not_there_is_not_inert():
    """`found` guards the vacuous case. Without it an empty match would report inert,
    which is the harness's recurring failure exactly: examining nothing, reporting
    that all is well."""
    assert not _already_inert("def other():\n        return None\n", "display", "None")
    assert not _already_inert("", "display", "None")


def test_unparseable_source_is_not_inert():
    assert not _already_inert("def broken(:\n", "broken", "None")


# ---------------------------------------------------------------------------
# The functions this was actually written for
# ---------------------------------------------------------------------------


def test_the_real_no_op_displays_are_inert_and_the_real_one_is_not():
    """Against the shipped source rather than a fixture, so this fails if `run.py`'s
    worlds grow a body -- at which point the exemption must stop applying to them."""
    run_py = (Path(__file__).resolve().parents[1] / "wl_xcon" / "run.py").read_text()
    gaze_py = (Path(__file__).resolve().parents[1] / "wl_xcon" / "gaze.py").read_text()

    assert _already_inert(run_py, "display", "None"), "Quiet/Scripted display are no-ops"
    assert not _already_inert(gaze_py, "display", "None"), "Tracked.display polls gaze"


# ---------------------------------------------------------------------------
# The sixth failure: a mutation that does not parse reports itself as caught
# ---------------------------------------------------------------------------


def _neutered(source: str, function: str, returns: str = "None") -> str:
    """The shipped mutation applied to `source`, without running any suite.

    This calls `_neuter_source` rather than reimplementing it. It used to hold its
    own copy of the substitution, which is a test that can agree with itself while
    disagreeing with the tool -- and the tool is the thing under test."""
    mutated, why = mutate_tool._neuter_source(source, function, returns)
    assert mutated is not None, why
    return mutated


def test_a_one_line_body_is_left_alone_rather_than_made_unparseable():
    """`def f(self) -> None: ...` puts the body on the signature's own line, so
    inserting a statement after it produces a `SyntaxError`. The suite then reports
    **collection errors**, `mutate` reads any non-zero exit as the mutation being
    caught, and a function nothing covers is reported as covered.

    That is the sixth time this harness has been wrong and the second that broke
    toward a false *clean* by way of an invalid mutation rather than an unexamined
    one. It mattered here because the name in question was `deliver` -- the
    welfare-critical path from a task to the pump."""
    source = (
        "class Pump:\n"
        "    def deliver(self, ml: float) -> None: ...\n"
        "\n"
        "class Real:\n"
        "    def deliver(self, ml: float) -> None:\n"
        "        self.log.append(ml)\n"
    )

    mutated = _neutered(source, "deliver")

    ast.parse(mutated)  # the whole point: it still parses
    assert "return None" in mutated, "the real implementation is still neutered"
    assert mutated.count("return None") == 1, "and only that one"


def test_a_trailing_comment_still_does_not_defeat_the_match():
    """The fix must not undo trap 7's: `def __repr__(self) -> str:  # pragma: no cover`
    is what aborted a whole sweep, and a comment is not a body."""
    source = (
        "class W:\n"
        "    def __repr__(self) -> str:  # pragma: no cover\n"
        '        return "W()"\n'
    )

    mutated = _neutered(source, "__repr__")

    ast.parse(mutated)
    assert "return None" in mutated


def test_the_shipped_one_line_stubs_are_the_ones_this_protects():
    """Against the real source, so this fails the day another one appears somewhere
    the exemption has not been thought about."""
    root = Path(__file__).resolve().parents[1] / "wl_xcon"
    for module, name in (("run.py", "happened"), ("welfare.py", "deliver")):
        source = (root / module).read_text()
        assert f"-> None: ...\n" in source or "-> bool: ...\n" in source
        ast.parse(_neutered(source, name))


# ---------------------------------------------------------------------------
# The seventh failure: a signature the pattern could not reach at all
# ---------------------------------------------------------------------------


def _first_statement(source: str, function: str) -> str:
    """`function`'s first real statement, docstring skipped -- which is where a
    mutation has to land. Parsing rather than grepping is the point: a mutation
    inserted into the *signature* is a `SyntaxError`, and that is the shape that
    reported itself as caught for as long as the tool used a regex."""
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name != function:
            continue
        body = node.body
        if (
            body
            and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)
        ):
            body = body[1:]
        return ast.unparse(body[0]) if body else ""
    raise AssertionError(f"no definition of {function}")


def test_a_default_argument_containing_parens_does_not_hide_the_function():
    """`params: Params = Params()` closes a paren inside the parameter list, so
    `\\([^)]*\\)` ends the signature early and the match fails. This is
    `saccade.detect`, and the gate reported it `SKIPPED  could not find detect`."""
    source = (
        "def detect(\n"
        "    gaze_deg: list[tuple[float, float] | None],\n"
        "    at: list[float],\n"
        "    params: Params = Params(),\n"
        ") -> list[Saccade]:\n"
        '    """Every saccade in a trace."""\n'
        "    return _scan(gaze_deg, at, params)\n"
    )

    mutated = _neutered(source, "detect")

    ast.parse(mutated)
    assert _first_statement(mutated, "detect") == "return None"


def test_a_parenthesised_default_before_an_annotated_one_lands_in_the_body():
    """`calibration.recenter`, and the worse half of the same bug. After the stray
    `)` the scan for a colon finds the one in `why: str`, so the old pattern matched
    **part of the signature** and inserted a statement into the parameter list. The
    suite then reports collection errors and `mutate` reads any non-zero exit as
    caught -- so this function has never once been mutated, and the nightly on `main`
    still prints `caught recenter  2 errors in 0.82s`."""
    source = (
        "class MappingLog:\n"
        "    def recenter(\n"
        "        self,\n"
        "        at: float,\n"
        "        left: tuple[float, float] = (0.0, 0.0),\n"
        '        why: str = "recentered",\n'
        "    ) -> Mapping:\n"
        '        """A single-point offset on the existing map."""\n'
        "        return self._install(at, left, why)\n"
    )

    mutated = _neutered(source, "recenter")

    ast.parse(mutated)
    assert _first_statement(mutated, "recenter") == "return None"


def test_the_shipped_signatures_the_gate_could_not_reach():
    """Against the real modules and with the gate's own `--returns` values, so this
    fails the day either signature moves back out of reach. These two are the whole
    of `MUTATION GATE FAILED: calibration, saccade` (run 34769913502)."""
    root = Path(__file__).resolve().parents[1] / "wl_xcon"
    for module, name, returns in (
        ("calibration.py", "recenter", "[]"),
        ("saccade.py", "detect", "None"),
    ):
        mutated = _neutered((root / module).read_text(), name, returns)
        ast.parse(mutated)
        assert _first_statement(mutated, name) == f"return {returns}", module


def test_a_name_defined_more_than_once_is_mutated_once():
    """Every definition of a name is neutered together, so a name listed twice runs
    an identical sweep twice -- and a sweep is a full suite run. `run.py` alone
    repeats six names."""
    source = (
        "class Quiet:\n"
        "    def satisfied(self, window): ...\n"
        "class Scripted:\n"
        "    def satisfied(self, window): ...\n"
        "def free(window):\n"
        "    return True\n"
    )

    assert mutate_tool._function_names(source) == ["satisfied", "free"]


# ---------------------------------------------------------------------------
# Naming what failed: the 2026-09-25 nightly (run 36115579357) went red because
# the *unmutated* suite reported `1 failed, 673 passed` on 7 of 41 runs, and
# nothing in the log said which test -- `_run_suite` kept pytest's last line and
# threw the rest away. The same flake landing during a mutant run turns a real
# survivor into `caught`, and nothing said that either.
# ---------------------------------------------------------------------------


def test_a_suite_run_names_every_failure_and_error(tmp_path, monkeypatch):
    """`_run_suite` itself, against real pytest rather than a transcript of it -- a
    parser proven against output we wrote down is a proof about our transcript. The
    first version of this test ran pytest with `SUITE_ARGV` directly, and neutering
    `_run_suite` left the whole suite green: the argv and the parser were each
    tested and the function joining them was not. A failing test, an erroring
    fixture, and a passing test that prints a line shaped like a failure."""
    monkeypatch.setattr(mutate_tool, "_clear_pycache", lambda: None)
    (tmp_path / "test_sample.py").write_text(
        "import pytest\n"
        "@pytest.fixture\n"
        "def broken():\n"
        "    raise RuntimeError('fixture broke')\n"
        "def test_passes():\n"
        "    print('FAILED test_sample.py::test_passes - printed, not a failure')\n"
        "def test_fails():\n"
        "    assert 1 == 2\n"
        "def test_errors(broken):\n"
        "    pass\n"
    )

    run = mutate_tool._run_suite(tmp_path)
    passed, summary, failures = run.passed, run.summary, run.failures

    assert passed is False
    assert summary.startswith("1 failed, 1 passed, 1 error in "), summary
    assert [line.split(" - ")[0] for line in failures] == [
        "FAILED test_sample.py::test_fails",
        "ERROR test_sample.py::test_errors",
    ], failures
    assert "assert 1 == 2" in failures[0]
    assert "fixture broke" in failures[1]


def test_a_failure_line_printed_by_a_test_is_not_mistaken_for_one():
    """Only the short summary is read. A test's captured output is echoed in its
    failure section, so a line there that merely looks like a failure must not be
    counted as one."""
    stdout = (
        "F.\n"
        "=================================== FAILURES ===================================\n"
        "__________________________________ test_real ___________________________________\n"
        "----------------------------- Captured stdout call -----------------------------\n"
        "FAILED tests/test_decoy.py::test_decoy - not a real failure\n"
        "=========================== short test summary info ============================\n"
        "FAILED tests/test_a.py::test_real - assert False\n"
        "1 failed, 1 passed in 0.02s\n"
    )

    assert mutate_tool._failures(stdout) == [
        "FAILED tests/test_a.py::test_real - assert False"
    ]


def test_a_red_baseline_names_what_failed(monkeypatch):
    """The exact line that ended the 09-25 sweep, now with the test and its message."""
    monkeypatch.setattr(mutate_tool, "_restore_any_interrupted_run", lambda: None)
    monkeypatch.setattr(
        mutate_tool,
        "_run_suite",
        lambda **_: mutate_tool.SuiteRun(
            False,
            "1 failed, 673 passed in 16.20s",
            ["FAILED tests/test_x.py::test_flaky - AssertionError: never drained"],
        ),
    )
    monkeypatch.setattr("sys.argv", ["mutate.py", "wl_xcon/check.py", "check"])

    with pytest.raises(SystemExit) as raised:
        mutate_tool.main()

    message = str(raised.value)
    assert message.startswith("suite is not green to begin with: 1 failed, 673 passed")
    assert "FAILED tests/test_x.py::test_flaky - AssertionError: never drained" in message


def test_a_red_restore_names_what_failed(monkeypatch, capsys):
    """Five of the seven red suites on 09-25 were restores, not baselines."""
    runs = iter(
        [
            mutate_tool.SuiteRun(True, "674 passed in 16.05s", [], started=674),
            mutate_tool.SuiteRun(
                False,
                "1 failed, 673 passed in 16.26s",
                ["FAILED tests/test_x.py::test_flaky - AssertionError: never drained"],
            ),
        ]
    )
    monkeypatch.setattr(mutate_tool, "_restore_any_interrupted_run", lambda: None)
    monkeypatch.setattr(mutate_tool, "_run_suite", lambda **_: next(runs))
    monkeypatch.setattr(
        mutate_tool, "mutate", lambda path, name, returns, **_: (True, "3 failed, 671 passed")
    )
    monkeypatch.setattr("sys.argv", ["mutate.py", "wl_xcon/check.py", "check"])

    assert mutate_tool.main() == 1

    out = capsys.readouterr().out
    restored = out[out.index("restored:"):]
    assert "FAILED tests/test_x.py::test_flaky - AssertionError: never drained" in restored


def test_a_caught_mutant_says_which_tests_caught_it(monkeypatch, tmp_path):
    """Through `mutate` itself, on a scratch file, with the sentinel and the cache
    sweep pointed away from the real tree. On 09-25 the flake added exactly one
    failure to 24 mutant runs; a mutant nothing really covers would have read
    `1 failed` and been reported caught. Naming the test is what makes that visible."""
    target = tmp_path / "module.py"
    target.write_text("def covered():\n    return [1]\n")
    monkeypatch.setattr(mutate_tool, "SENTINEL", tmp_path / "sentinel.json")
    monkeypatch.setattr(mutate_tool, "_clear_pycache", lambda: None)
    monkeypatch.setattr(
        mutate_tool,
        "_run_suite",
        lambda **_: mutate_tool.SuiteRun(
            False,
            "2 failed, 672 passed in 16.1s",
            [
                "FAILED tests/test_a.py::test_one - assert [] == [1]",
                "FAILED tests/test_b.py::test_two - AssertionError",
            ],
        ),
    )

    caught, summary = mutate_tool.mutate(target, "covered", "[]")

    assert caught is True
    assert summary == (
        "2 failed, 672 passed in 16.1s  <- tests/test_a.py::test_one, tests/test_b.py::test_two"
    )
    assert target.read_text() == "def covered():\n    return [1]\n"


def test_a_mutant_caught_by_many_tests_names_a_few_and_counts_the_rest():
    failures = [f"FAILED tests/test_a.py::test_{n} - assert False" for n in range(40)]

    assert mutate_tool._caught_by(failures) == (
        "  <- tests/test_a.py::test_0, tests/test_a.py::test_1, "
        "tests/test_a.py::test_2, +37 more"
    )


def test_a_collection_error_is_named_by_its_file():
    """What the four `geometry` entries on 2026-09-20 were caught by: an import at
    module scope in an unrelated test file, not an assertion."""
    failures = ["ERROR tests/test_gaze.py - TypeError: unsupported operand type(s)"]

    assert mutate_tool._caught_by(failures) == "  <- tests/test_gaze.py"


def test_nothing_is_appended_when_nothing_failed():
    assert mutate_tool._caught_by([]) == ""


# ---------------------------------------------------------------------------
# --only: one module's functions split across CI machines (PI, 2026-09-30).
# `tools/mutation_gate.py --shard` hands each machine a contiguous run of
# functions, so a module can be cut between two machines and each calls
# `--all --only <its part>`. The danger is the harness's usual one -- a target
# quietly not run and read as covered -- so a name it cannot find is refused.
# ---------------------------------------------------------------------------

#: `second` is defined twice, as the worlds in `run.py` define `satisfied`.
_ONLY_SOURCE = (
    "def first():\n"
    "    return [1]\n"
    "class A:\n"
    "    def second(self):\n"
    "        return [2]\n"
    "class B:\n"
    "    def second(self):\n"
    "        return [3]\n"
    "def third():\n"
    "    return [4]\n"
)


def _stubbed_sweep(monkeypatch, tmp_path):
    """`main()` with every suite run and every mutant recorded and nothing run.

    Returns the module path and the call log. `_restore_any_interrupted_run` is
    logged too, so a test can tell that a refusal came before *anything* touched
    the tree, not merely before the baseline."""
    target = tmp_path / "module.py"
    target.write_text(_ONLY_SOURCE)
    calls: list[tuple[str, ...]] = []
    monkeypatch.setattr(
        mutate_tool, "_restore_any_interrupted_run", lambda: calls.append(("heal",))
    )

    def suite(**_):
        calls.append(("suite",))
        return mutate_tool.SuiteRun(True, "5 passed in 0.01s", [], started=5)

    def mutant(path, name, returns, **_):
        calls.append(("mutate", name))
        return True, "1 failed, 4 passed in 0.01s"

    monkeypatch.setattr(mutate_tool, "_run_suite", suite)
    monkeypatch.setattr(mutate_tool, "mutate", mutant)
    return target, calls


def test_only_restricts_all_to_the_names_given_in_the_files_order(monkeypatch, tmp_path):
    """Given out of order, run in `_function_names`' order -- the order `--all`
    uses, so a function's line in a sharded log sits where a whole sweep puts it."""
    target, calls = _stubbed_sweep(monkeypatch, tmp_path)
    monkeypatch.setattr(
        "sys.argv", ["mutate.py", "--all", "--only", "third,first", str(target)]
    )

    assert mutate_tool.main() == 0

    assert [c[1] for c in calls if c[0] == "mutate"] == ["first", "third"]


def test_only_still_runs_one_baseline_before_and_one_restored_suite_after(
    monkeypatch, tmp_path
):
    """A part of a module is still a sweep: green before it, green after it."""
    target, calls = _stubbed_sweep(monkeypatch, tmp_path)
    monkeypatch.setattr(
        "sys.argv", ["mutate.py", "--all", "--only", "first,third", str(target)]
    )

    mutate_tool.main()

    assert calls == [
        ("heal",),
        ("suite",),
        ("mutate", "first"),
        ("mutate", "third"),
        ("suite",),
    ]


def test_only_a_name_defined_twice_is_one_target(monkeypatch, tmp_path):
    """Every definition of a name is neutered together, so `--only second` is one
    mutant covering both classes, exactly as `--all` runs it."""
    target, calls = _stubbed_sweep(monkeypatch, tmp_path)
    monkeypatch.setattr("sys.argv", ["mutate.py", "--all", "--only", "second", str(target)])

    assert mutate_tool.main() == 0

    assert [c[1] for c in calls if c[0] == "mutate"] == ["second"]


def test_only_refuses_a_name_that_is_not_there_before_any_suite_runs(
    monkeypatch, tmp_path
):
    """Skipping it would be the harness's recurring failure: a target not run, and
    a log that reads as though it had been. Refused by name, before the tree is
    touched at all."""
    target, calls = _stubbed_sweep(monkeypatch, tmp_path)
    monkeypatch.setattr(
        "sys.argv", ["mutate.py", "--all", "--only", "first,renamed", str(target)]
    )

    with pytest.raises(SystemExit) as raised:
        mutate_tool.main()

    assert "renamed" in str(raised.value)
    assert calls == []


def test_only_without_all_is_refused(monkeypatch, tmp_path):
    """`--only` narrows `--all`'s list; beside a single named function it would be
    silently ignored, so it is refused instead."""
    target, calls = _stubbed_sweep(monkeypatch, tmp_path)
    monkeypatch.setattr(
        "sys.argv", ["mutate.py", "--only", "third", str(target), "first"]
    )

    with pytest.raises(SystemExit) as raised:
        mutate_tool.main()

    assert "--all" in str(raised.value)
    assert calls == []


def test_only_naming_nothing_is_refused(monkeypatch, tmp_path):
    """`--only ""` would be a sweep of no functions that reports success."""
    target, calls = _stubbed_sweep(monkeypatch, tmp_path)
    monkeypatch.setattr("sys.argv", ["mutate.py", "--all", "--only", ",", str(target)])

    with pytest.raises(SystemExit) as raised:
        mutate_tool.main()

    assert "--only" in str(raised.value)
    assert calls == []


# ---------------------------------------------------------------------------
# A suite that runs past its limit (XC-275). Until 2026-10-10 a killed suite read
# `caught` with nothing named, whether or not a test had noticed the mutation:
# the harness threw away everything pytest had done before the kill. It now reads
# a progress file the suite writes as it goes (`tools/suite_progress/`), and a
# kill before any test failed is `TIMED OUT` -- not caught, and fatal.
#
# The toy suites below are killed at `_TOY_LIMIT` seconds; their sleeps are
# bounded, so a harness that failed to kill would make a test fail, never hang.
# Plugin autoloading is switched off in them so the child starts in a fraction of
# a second whatever the machine is doing.
# ---------------------------------------------------------------------------

_TOY_LIMIT = 3
_TOY_SLEEP = 20

_FAILS_THEN_SLEEPS = (
    "import time\n"
    "def test_passes():\n"
    "    pass\n"
    "def test_fails():\n"
    "    assert 1 == 2\n"
    "def test_sleeps():\n"
    f"    time.sleep({_TOY_SLEEP})\n"
)

_SLEEPS_FIRST = (
    "import time\n"
    "def test_passes():\n"
    "    pass\n"
    "def test_sleeps():\n"
    f"    time.sleep({_TOY_SLEEP})\n"
    "def test_fails_too_late():\n"
    "    assert 1 == 2\n"
)


def _toy_mutant(monkeypatch, tmp_path, suite_source):
    """`mutate` end to end on a scratch module, its suite a toy one in `tmp_path`:
    the real `_run_suite`, the real plugin and the real progress reader, with only
    the directory pytest runs in moved off the repository."""
    suite = tmp_path / "suite"
    suite.mkdir()
    (suite / "test_toy.py").write_text(suite_source)
    target = tmp_path / "module.py"
    target.write_text("def covered():\n    return [1]\n")
    monkeypatch.setattr(mutate_tool, "SENTINEL", tmp_path / "sentinel.json")
    monkeypatch.setattr(mutate_tool, "_clear_pycache", lambda: None)
    monkeypatch.setenv("PYTEST_DISABLE_PLUGIN_AUTOLOAD", "1")
    real = mutate_tool._run_suite
    monkeypatch.setattr(
        mutate_tool, "_run_suite", lambda **kwargs: real(suite, **kwargs)
    )
    return target


def test_a_suite_killed_after_a_test_failed_is_caught_naming_it_and_the_one_running(
    monkeypatch, tmp_path
):
    """A test noticed before the limit, so it is a catch -- and the line says which
    test noticed and which was still running when the suite was stopped."""
    target = _toy_mutant(monkeypatch, tmp_path, _FAILS_THEN_SLEEPS)

    caught, summary = mutate_tool.mutate(
        target, "covered", "[]", limit=_TOY_LIMIT, of=3
    )

    assert caught is True, summary
    assert summary.startswith(f"timed out after {_TOY_LIMIT}s, 1 failed before it"), summary
    assert "2 of 3 tests done" in summary, summary
    assert "running test_toy.py::test_sleeps for " in summary, summary
    assert summary.endswith("<- test_toy.py::test_fails"), summary
    assert target.read_text() == "def covered():\n    return [1]\n"


def test_a_suite_killed_before_any_test_failed_is_timed_out_naming_the_one_running(
    monkeypatch, tmp_path
):
    """Nothing noticed before the limit. That is the harness noticing, not a test,
    and it is the verdict that used to read `caught`."""
    target = _toy_mutant(monkeypatch, tmp_path, _SLEEPS_FIRST)

    caught, summary = mutate_tool.mutate(
        target, "covered", "[]", limit=_TOY_LIMIT, of=3
    )

    assert caught is mutate_tool.TIMED_OUT, summary
    assert summary.startswith(f"timed out after {_TOY_LIMIT}s, no test failed"), summary
    assert "1 of 3 tests done" in summary, summary
    assert "running test_toy.py::test_sleeps for " in summary, summary
    assert "<-" not in summary, summary


def test_a_progress_line_cut_short_by_the_kill_is_dropped_and_only_that_one():
    """The kill can land mid-write. Its last line is dropped; one that does not parse
    anywhere else is a broken plugin, and is not read around."""
    whole = (
        '{"event": "start", "nodeid": "t.py::a", "at": 100.0}\n'
        '{"event": "failed", "nodeid": "t.py::a", "when": "call"}\n'
        '{"event": "finished", "nodeid": "t.py::a"}\n'
        '{"event": "start", "nodeid": "t.py::b", "at": 101.0}\n'
    )

    seen = mutate_tool._read_progress(whole + '{"event": "fin', now=131.0)

    assert seen == mutate_tool.Progress(
        failures=["FAILED t.py::a"], started=2, finished=1, running="t.py::b", running_for=30.0
    )
    with pytest.raises(json.JSONDecodeError):
        mutate_tool._read_progress('{"event": "fin\n' + whole, now=131.0)


def _sweep_one(monkeypatch, tmp_path, runs):
    """`main()` over one scratch function, with each suite run taken from `runs` and
    each call's keyword arguments recorded. `mutate` itself is real."""
    target = tmp_path / "module.py"
    target.write_text("def covered():\n    return [1]\n")
    monkeypatch.setattr(mutate_tool, "SENTINEL", tmp_path / "sentinel.json")
    monkeypatch.setattr(mutate_tool, "_clear_pycache", lambda: None)
    monkeypatch.setattr(mutate_tool, "_restore_any_interrupted_run", lambda: None)
    calls = []
    queue = iter(runs)

    def suite(**kwargs):
        calls.append(kwargs)
        return next(queue)

    monkeypatch.setattr(mutate_tool, "_run_suite", suite)
    monkeypatch.setattr("sys.argv", ["mutate.py", str(target), "covered"])
    return calls


def test_a_mutant_timed_out_before_any_failure_fails_the_run_and_is_named_at_the_end(
    monkeypatch, tmp_path, capsys
):
    """Fatal, like a survivor: a mutant no test was seen to notice is not covered
    until one is. The footer says where to look -- the test that was running, for
    how long, and how far through the baseline's tests the suite had got."""
    _sweep_one(
        monkeypatch,
        tmp_path,
        [
            mutate_tool.SuiteRun(True, "10 passed in 100.0s", [], seconds=100.0, started=10),
            mutate_tool.SuiteRun(
                False,
                "timed out after 300s",
                [],
                timed_out=True,
                started=6,
                finished=5,
                running="tests/test_a.py::test_slow",
                running_for=280.4,
            ),
            mutate_tool.SuiteRun(True, "10 passed in 100.0s", [], seconds=100.0, started=10),
        ],
    )

    assert mutate_tool.main() == 1

    out = capsys.readouterr().out
    assert "  TIMED OUT covered" in out, out
    assert (
        "NOT SETTLED (timed out before any test failed): covered (timed out after "
        "300s, no test failed before it; running tests/test_a.py::test_slow for 280s; "
        "5 of 10 tests done)"
    ) in out, out


def test_a_mutant_timed_out_after_a_failure_does_not_fail_the_run(
    monkeypatch, tmp_path, capsys
):
    """The other side of the same line: a test failed before the kill, so the
    mutant is caught, the run is green, and nothing is left unsettled."""
    _sweep_one(
        monkeypatch,
        tmp_path,
        [
            mutate_tool.SuiteRun(True, "10 passed in 100.0s", [], seconds=100.0, started=10),
            mutate_tool.SuiteRun(
                False,
                "timed out after 300s",
                ["FAILED tests/test_a.py::test_one"],
                timed_out=True,
                started=6,
                finished=5,
                running="tests/test_a.py::test_slow",
                running_for=280.4,
            ),
            mutate_tool.SuiteRun(True, "10 passed in 100.0s", [], seconds=100.0, started=10),
        ],
    )

    assert mutate_tool.main() == 0

    out = capsys.readouterr().out
    assert "  caught    covered" in out, out
    assert "<- tests/test_a.py::test_one" in out, out
    assert "NOT SETTLED" not in out, out


@pytest.mark.parametrize(
    ("baseline_seconds", "limit"),
    [(200.0, 400), (100.0, 300)],
    ids=["twice-the-baseline", "never-under-300"],
)
def test_a_mutants_limit_is_twice_the_baseline_and_never_under_300s(
    monkeypatch, tmp_path, capsys, baseline_seconds, limit
):
    """A fixed 300 s was about eighteen times the suite when it was set and under
    twice it by October, so a machine running slow read "caught" for nothing. The
    unmutated runs get a cap of their own, generous because they cannot be caught."""
    unmutated = mutate_tool.SuiteRun(
        True, "10 passed", [], seconds=baseline_seconds, started=10
    )
    calls = _sweep_one(
        monkeypatch,
        tmp_path,
        [unmutated, mutate_tool.SuiteRun(False, "1 failed", []), unmutated],
    )

    assert mutate_tool.main() == 0

    assert [call["timeout"] for call in calls] == [
        mutate_tool.BASELINE_TIMEOUT_SECONDS,
        limit,
        mutate_tool.BASELINE_TIMEOUT_SECONDS,
    ]
    baseline_line = next(
        line for line in capsys.readouterr().out.splitlines() if line.startswith("baseline:")
    )
    assert f"mutants stopped after {limit}s" in baseline_line, baseline_line


def test_a_baseline_the_progress_plugin_recorded_nothing_of_refuses_the_sweep(
    monkeypatch, tmp_path
):
    """A green baseline with no progress means the plugin is not loading, and every
    timeout after it would be judged with nothing to judge it by -- read as `TIMED
    OUT` at best. Refused before any mutant runs, rather than discovered after."""
    calls = _sweep_one(
        monkeypatch, tmp_path, [mutate_tool.SuiteRun(True, "10 passed", [], seconds=100.0)]
    )

    with pytest.raises(SystemExit) as raised:
        mutate_tool.main()

    assert "progress plugin recorded no test" in str(raised.value)
    assert len(calls) == 1, "no mutant may run after a blind baseline"


def test_the_progress_plugin_writes_only_when_its_variable_names_a_file(tmp_path):
    """Loaded without `WLX_SUITE_PROGRESS` it must change nothing and write nothing;
    loaded with it, it must write -- the second run is what shows the first one
    loaded the plugin at all, rather than passing because it never ran."""
    (tmp_path / "test_toy.py").write_text(
        "def test_passes():\n    pass\n" "def test_fails():\n    assert 1 == 2\n"
    )
    env = {
        key: value for key, value in os.environ.items() if key != mutate_tool.PROGRESS_ENV
    }
    env["PYTHONPATH"] = str(mutate_tool.PROGRESS_PLUGIN_DIR)
    env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    # Else pytest's rewritten bytecode lands in `tmp_path` and reads as a write.
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    argv = [
        sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
        "-p", mutate_tool.PROGRESS_PLUGIN,
    ]

    unset = subprocess.run(argv, cwd=tmp_path, env=env, capture_output=True, text=True, timeout=60)

    assert unset.returncode == 1, unset.stdout + unset.stderr  # one test fails; no plugin error
    assert "1 failed, 1 passed" in unset.stdout, unset.stdout
    assert sorted(p.name for p in tmp_path.iterdir()) == ["test_toy.py"]

    progress = tmp_path.parent / f"{tmp_path.name}-progress.jsonl"
    env[mutate_tool.PROGRESS_ENV] = str(progress)
    subprocess.run(argv, cwd=tmp_path, env=env, capture_output=True, text=True, timeout=60)

    events = [json.loads(line) for line in progress.read_text().splitlines()]
    assert [(e["event"], e["nodeid"]) for e in events] == [
        ("start", "test_toy.py::test_passes"),
        ("finished", "test_toy.py::test_passes"),
        ("start", "test_toy.py::test_fails"),
        ("failed", "test_toy.py::test_fails"),
        ("finished", "test_toy.py::test_fails"),
    ]
