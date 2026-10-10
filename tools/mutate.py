#!/usr/bin/env python3
"""Prove a test can fail, by breaking the code it claims to cover.

A test that passes whether or not the behaviour exists is worse than no test: it
reports safety it cannot provide. This script neuters one function -- replacing its
body with `return []` -- runs the suite, and restores.

**It clears `__pycache__` around every step, and that is the whole reason it is a
script rather than three shell lines.** Doing this by hand left stale bytecode from
a previous mutation in place: the source was restored, the interpreter kept running
the broken version, and the suite reported failures against code that was already
correct. A false failure is merely alarming. The same staleness in the other
direction reports a **false pass** -- the mutation never actually ran, and a vacuous
test is pronounced sound. That is the failure this exists to prevent, so it cannot
depend on anyone remembering to clear a cache.

    python3 tools/mutate.py wl_xcon/check.py _unbounded_waits
    python3 tools/mutate.py --all wl_xcon/check.py
    python3 tools/mutate.py --all --only detect,_saccade wl_xcon/saccade.py

`--only` narrows `--all` to the names given, in `--all`'s own order, with the same
baseline before and restored suite after. It exists so `tools/mutation_gate.py
--shard` can cut one module's functions across CI machines (PI, 2026-09-30), and
it refuses a name `--all` would not list rather than skipping it: a target that was
never run must not read as one that was.
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import NamedTuple

ROOT = Path(__file__).resolve().parent.parent

#: Written before a file is mutated and removed after it is restored. A `finally`
#: cannot survive SIGKILL, and a timeout kills -- which once left a neutered
#: `__exit__` on disk that was then committed and pushed, because the commit did not
#: re-run the suite. The sentinel makes the damage self-healing rather than silent:
#: the next run restores from it before doing anything else.
SENTINEL = ROOT / ".mutate-in-progress.json"


def _restore_any_interrupted_run() -> None:
    """Undo a mutation left behind by a killed process -- **only if it is still there**.

    Called before anything else, including the baseline, so a suite that looks red
    because of a stale mutation is repaired rather than reported.

    **It restores only when the file still matches the text this tool wrote.** A
    blind restore is worse than the problem it solves: run this in the background,
    edit the source while it holds a mutation, and healing would revert that work
    silently. Never edit source while this is running; this check is the backstop,
    not permission.
    """
    if not SENTINEL.exists():
        return
    saved = json.loads(SENTINEL.read_text())
    path = Path(saved["path"])
    current = path.read_text()
    if current == saved["mutated"]:
        path.write_text(saved["original"])
        print(f"restored {path} from an interrupted run\n")
    elif current == saved["original"]:
        pass  # someone already put it back
    else:
        # **Do not restore.** The file has changed since the mutation, so the
        # sentinel's copy is stale and writing it back would silently revert
        # whatever was done in between. This nearly happened: a harness run was
        # backgrounded, source was edited while it held a mutation, and a
        # self-healing restore would have thrown that work away without a word.
        print(
            f"WARNING: {path} changed since an interrupted mutation run.\n"
            f"  Not restoring -- the sentinel's copy is stale and would revert "
            f"live edits.\n"
            f"  Check for a stray `return` at the top of a function, then delete "
            f"{SENTINEL.name}.\n"
        )
        return
    SENTINEL.unlink()


def _clear_pycache() -> None:
    for cache in ROOT.rglob("__pycache__"):
        shutil.rmtree(cache, ignore_errors=True)


#: A mutated suite may not terminate. Neutering `Scheduler.record` stops the counts
#: advancing, so a test running a block to completion never sees it finish -- and the
#: suite hung until an outer timeout killed the whole harness, past its `finally`,
#: stranding a neutered module on disk (2026-09-01). The sentinel healed that; a time
#: limit on every suite run is the fix.
#:
#: **What a timeout means changed as the suite grew, and the verdict did not.** Set
#: when the suite ran in seconds (674 tests in 16 s on 2026-09-25, about eighteen times
#: under the limit), 300 s then held only hangs, and a hang was counted *caught*. By
#: 2026-10-09 CI's baselines ran 146-207 s, the limit only 1.45-2.05 times them, and a
#: caught mutant runs the baseline plus a few seconds per failing test while those
#: tests wait out their own bounded waits -- so the limit mostly caught slow suites:
#: 82 functions on `main` read caught with no test named, and 45 more finished within
#: 30 s of it (XC-275; CI runs `37919247229` and `37991004478`). Two changes answer that:
#:
#: - the limit is relative to the measured baseline, `LIMIT_FACTOR` times it and never
#:   under this floor (`_mutant_limit`), so a slower machine is not 10 s from a false
#:   catch;
#: - a killed suite is judged by what it had done, read from the progress file
#:   `tools/suite_progress/` writes as it runs: a test that failed before the kill is
#:   a catch, named; a kill before any test failed is `TIMED OUT`, which is not.
SUITE_TIMEOUT_SECONDS = 300

#: A mutant's suite is stopped after this many times the baseline's wall time.
LIMIT_FACTOR = 2

#: The unmutated runs -- the baseline and the restored suite -- cannot be caught, so a
#: limit on them only bounds a harness that would otherwise wait forever. Generous
#: because the mutants' limit is computed from the baseline: a baseline cut short
#: would leave nothing to compute it from.
BASELINE_TIMEOUT_SECONDS = 3600

#: The pytest plugin that records each test as it runs, in a directory of its own so
#: that putting it on the child's `PYTHONPATH` exposes nothing else in `tools/`.
PROGRESS_PLUGIN_DIR = Path(__file__).resolve().parent / "suite_progress"
PROGRESS_PLUGIN = "wlx_suite_progress"
#: The variable naming the plugin's file. Without it the plugin writes nothing.
PROGRESS_ENV = "WLX_SUITE_PROGRESS"

#: `-rfE` makes pytest end with one line per failed or errored test. **Keeping only
#: the last line is how the 2026-09-25 nightly went red on a flaky test without once
#: naming it** (run 36115579357: `1 failed, 673 passed` on 7 of 41 unmutated runs).
#: The message on each line is trimmed to the terminal width *unless* `CI` or
#: `BUILD_NUMBER` is set, which GitHub Actions does -- pytest 9.1.1,
#: `_pytest/terminal.py:_get_line_with_reprcrash_message` and
#: `_pytest/compat.py:running_on_ci`, read 2026-09-26 -- so CI gets it whole.
SUITE_ARGV = ["-m", "pytest", "-q", "-p", "no:cacheprovider", "-rfE"]

#: How many failing tests a mutant's line names before it only counts the rest.
NAMED = 3


class SuiteRun(NamedTuple):
    """One run of the suite: whether it passed, pytest's final line, one line per
    failure, and -- from the progress file -- how far it got.

    For a run that finished, `failures` are the short summary's lines (`_failures`).
    For one that was killed (`timed_out`), pytest never printed a summary, so they
    are built from the progress file instead, in the same `FAILED <nodeid>` /
    `ERROR <nodeid>` form, and `running` is the test that had started and not
    finished (`None` when the kill fell between tests), `running_for` how long it
    had been running.

    A `NamedTuple` rather than a dataclass: this file is loaded by path, outside
    `sys.modules` (`tests/test_mutate.py`, `mutation_gate._load_mutate`), and a
    dataclass with postponed annotations looks its module up there and fails.
    """

    passed: bool
    summary: str
    failures: list[str]
    timed_out: bool = False
    seconds: float = 0.0
    started: int = 0
    finished: int = 0
    running: str | None = None
    running_for: float = 0.0


def _run_suite(cwd: Path = ROOT, *, timeout: float = SUITE_TIMEOUT_SECONDS) -> SuiteRun:
    """Run the suite once, with the progress plugin loaded, and stop it at `timeout`.

    `cwd` is only ever the repository in use; it is a parameter so a test can run
    this, end to end, against a three-test suite rather than this one.
    """
    _clear_pycache()
    handle, name = tempfile.mkstemp(prefix="wlx-suite-progress-", suffix=".jsonl")
    os.close(handle)
    progress = Path(name)
    env = dict(os.environ)
    env[PROGRESS_ENV] = str(progress)
    env["PYTHONPATH"] = os.pathsep.join(
        [str(PROGRESS_PLUGIN_DIR), *filter(None, [os.environ.get("PYTHONPATH")])]
    )
    start = time.monotonic()
    try:
        try:
            result = subprocess.run(
                [sys.executable, *SUITE_ARGV, "-p", PROGRESS_PLUGIN],
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=env,
            )
        except subprocess.TimeoutExpired:
            killed_at = time.time()
            seen = _read_progress(progress.read_text(encoding="utf-8"), killed_at)
            return SuiteRun(
                False,
                f"timed out after {timeout:.0f}s",
                seen.failures,
                timed_out=True,
                seconds=time.monotonic() - start,
                started=seen.started,
                finished=seen.finished,
                running=seen.running,
                running_for=seen.running_for,
            )
        seconds = time.monotonic() - start
        seen = _read_progress(progress.read_text(encoding="utf-8"), time.time())
    finally:
        progress.unlink(missing_ok=True)
    output = result.stdout.strip().splitlines()
    return SuiteRun(
        result.returncode == 0,
        output[-1] if output else "no output",
        _failures(result.stdout),
        seconds=seconds,
        started=seen.started,
        finished=seen.finished,
    )


class Progress(NamedTuple):
    """What the progress file says a suite had done."""

    failures: list[str]
    started: int
    finished: int
    running: str | None
    running_for: float


def _read_progress(text: str, now: float) -> Progress:
    """Read the plugin's JSON lines (`tools/suite_progress/wlx_suite_progress.py`).

    **The file, never pytest's terminal output.** A killed suite's output stops
    mid-line and carries no summary; the file holds one record per event, written
    as each test starts, fails and finishes. A test that fails in more than one
    phase is one failure, named once, as pytest's summary names it: `FAILED` for
    its call, `ERROR` for its setup or teardown.

    A kill can land while the plugin is writing, so **the last line alone** may be
    cut short and is dropped if it does not parse. Anywhere else a line that does
    not parse is a broken plugin, and raises.
    """
    started: dict[str, float] = {}
    finished: set[str] = set()
    failed: dict[str, str] = {}
    lines = [line for line in text.splitlines() if line.strip()]
    for n, line in enumerate(lines):
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            if n == len(lines) - 1:
                break
            raise
        nodeid = record["nodeid"]
        if record["event"] == "start":
            started.setdefault(nodeid, record["at"])
        elif record["event"] == "finished":
            finished.add(nodeid)
        elif record["event"] == "failed":
            failed.setdefault(nodeid, "FAILED" if record["when"] == "call" else "ERROR")
    unfinished = [nodeid for nodeid in started if nodeid not in finished]
    running = unfinished[-1] if unfinished else None
    return Progress(
        failures=[f"{kind} {nodeid}" for nodeid, kind in failed.items()],
        started=len(started),
        finished=len(finished),
        running=running,
        running_for=now - started[running] if running else 0.0,
    )


def _failures(stdout: str) -> list[str]:
    """The `FAILED ...`/`ERROR ...` lines of pytest's short test summary.

    **Only the summary is read.** A failing test's captured output is echoed above
    it, verbatim, so a line there that happens to start `FAILED ` is not a failure.
    """
    lines = stdout.splitlines()
    start = next(
        (n for n, line in enumerate(lines) if "short test summary info" in line), None
    )
    if start is None:
        return []
    return [line for line in lines[start + 1 :] if line.startswith(("FAILED ", "ERROR "))]


def _caught_by(failures: list[str]) -> str:
    """What to append to a mutant's line: the tests that failed, by node id.

    On 2026-09-25 a flaky test added exactly one failure to 24 mutant runs. A mutant
    nothing really covers reads `1 failed` in that run and is reported `caught`; the
    name of the test that did the catching is the only thing that shows it.
    """
    if not failures:
        return ""
    names = [line.split(" ", 1)[1].split(" - ", 1)[0] for line in failures]
    shown = ", ".join(names[:NAMED])
    rest = len(names) - NAMED
    return f"  <- {shown}" + (f", +{rest} more" if rest > 0 else "")


def _function_names(source: str) -> list[str]:
    """Every function, module-level and method alike, and each name once.

    Four blind spots found by using it, all the same shape -- the tool quietly
    examining nothing and reporting success. First it matched only `_`-prefixed
    names, so a run over `simulate.py` covered none of it. Then it matched only
    module-level `def`, so `record.py` -- which is entirely methods -- reported
    nothing to mutate, which reads like nothing to check. Then, found by replacing
    the pattern with the parser: `^ *def ([a-z_][a-z0-9_]*)\\(` cannot spell a
    capital, so **`photometry._XYZ` and `task.FixPoint` had never been mutated
    once** and no output said so -- they were simply not on the list.

    A coverage tool that can silently cover nothing has the exact failure mode it
    exists to catch, so `--all` refuses an empty target list and this asks the
    parser rather than a pattern.

    **And each name once.** Every definition of a name is neutered together, so a
    name six worlds implement ran six identical sweeps against identical inputs for
    identical results -- and a sweep is a full run of the suite. `run.py` was
    twenty-four targets and is twelve; `dio.py` was fourteen and is six.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    found = sorted(
        (node.lineno, node.name)
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    )
    return list(dict.fromkeys(name for _, name in found))


#: Returned by `mutate` when the neutered body is the body it already had.
INERT = "inert"

#: Returned by `mutate` when the suite was stopped at its limit before any test had
#: failed: nothing was seen to notice the mutation, so it is not a catch. Fatal, like
#: a survivor, and listed at the end with the test that was running (XC-275).
TIMED_OUT = "timed out"


def _is_docstring(node: ast.stmt) -> bool:
    return (
        isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
    )


def _neuter_source(source: str, function: str, returns: str) -> tuple[str | None, str]:
    r"""`source` with every definition of `function` returning `returns` first, or
    `(None, why)` when there is nothing this can safely do.

    **This asks the parser where a body starts.** It used to ask a regex, and that
    regex was wrong three times in three different ways. A trailing comment defeated
    the match, so `def __repr__(self) -> str:  # pragma: no cover` aborted a whole
    sweep. A body on the signature's own line matched, and the line inserted after it
    made a `SyntaxError`. And a default argument containing a `)` ended the signature
    early: `\([^)]*\)` stops inside `Params()`, so `saccade.detect` could not be
    found at all, and in `calibration.recenter` the scan for the colon ran on into
    `why: str` and inserted a statement **into the parameter list**.

    That last one is the seventh time this harness has been wrong and the third that
    broke toward a false *clean*: the suite reported collection errors, `mutate` read
    the non-zero exit as the mutation being caught, and a function that had never in
    its life been mutated was reported covered. The nightly on `main` still prints
    `caught recenter  2 errors in 0.82s`, which is what that looks like from outside.

    A parser cannot make any of those three mistakes, because `body[0]` **is** the
    body. Two decisions are left, and both are about where the line goes rather than
    about where the body is:

    - a docstring is stepped over rather than displaced, so the mutation lands below
      it and the function keeps its documentation;
    - a body written on the signature's own line is refused *for that definition*,
      because no line can follow `def deliver(self, ml: float) -> None: ...` and still
      parse. Its siblings are still neutered -- a Protocol stub beside a real
      implementation must not exempt the implementation.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return None, f"{function}: source does not parse ({exc})"

    lines = source.splitlines(keepends=True)
    insertions: list[tuple[int, str]] = []
    on_signature_line = 0
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name != function:
            continue
        anchor = node.body[0]
        if lines[anchor.lineno - 1][: anchor.col_offset].strip():
            on_signature_line += 1
            continue
        at = anchor.end_lineno if _is_docstring(anchor) else anchor.lineno - 1
        insertions.append((at, " " * anchor.col_offset + f"return {returns}\n"))

    if not insertions:
        if on_signature_line:
            return None, f"{function} is written on its signature's own line"
        return None, f"could not find {function}"

    # Descending, so an earlier insertion cannot move a later one's line number.
    for at, text in sorted(insertions, reverse=True):
        if at and not lines[at - 1].endswith("\n"):
            lines[at - 1] += "\n"
        lines.insert(at, text)
    return "".join(lines), ""


def _already_inert(source: str, function: str, returns: str) -> bool:
    """True when inserting `return {returns}` at the top of `function` changes nothing.

    **A function that already returns immediately cannot be neutered, because it is
    already neutral.** `Quiet.display` and `Scripted.display` are `return None`;
    `World.display` is a docstring. Neutering inserts `return None` above a body that
    was `return None`, the suite passes because nothing changed, and the harness
    called that a SURVIVOR -- so the mutation gate could never go green, and the
    build failed on three functions that are not defects. `docs/CHECKPOINT.md` had
    been carrying the discrepancy as a footnote ("the only non-caught entries are
    no-op display bodies") rather than as the tool bug it is.

    **This must stay narrow.** It is the fifth time this harness has been changed,
    and the previous four were all it quietly examining nothing and reporting
    success -- so a category that does not fail the build is exactly the shape of the
    recurring bug. The condition is therefore proved from the AST, not guessed: every
    definition of the name must already begin (after any docstring) with the very
    statement the mutation would insert, or be empty where the insertion is
    `return None`. If any one definition would really be changed, this is False and a
    survivor is a real survivor.
    """
    try:
        tree = ast.parse(source)
        wanted = ast.dump(ast.parse(f"return {returns}").body[0])
    except SyntaxError:
        return False

    found = False
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name != function:
            continue
        found = True
        body = list(node.body)
        if (
            body
            and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)
        ):
            body = body[1:]  # the docstring is not a statement the mutation displaces
        neutral_already = returns.strip() == "None" and (
            not body
            or isinstance(body[0], ast.Pass)
            or (
                isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and body[0].value.value is Ellipsis
            )
        )
        if neutral_already:
            continue
        if body and ast.dump(body[0]) == wanted:
            continue
        return False
    return found


def mutate(
    path: Path,
    function: str,
    args_returns: str,
    *,
    limit: float = SUITE_TIMEOUT_SECONDS,
    of: int | None = None,
) -> tuple[bool | str | None, str]:
    """`(verdict, the line's text)` for neutering `function`.

    The verdict is True if the suite failed, i.e. the function is covered; False if
    it passed (a survivor); `INERT` or `None` if nothing could be neutered; and
    `TIMED_OUT` if the suite ran past `limit` before any test failed. A suite that
    ran past `limit` *after* a test failed is a catch, and the line names the tests
    that failed and the one still running (`_how_far`, where `of` is the baseline's
    test count).

    A name defined more than once -- `satisfied`, implemented by every `World` --
    has **all** its definitions neutered together. Bailing on the ambiguity was the
    earlier behaviour and it was worse than useless: it stopped the whole run, so
    `run.py` reported nothing at all rather than reporting what it could.

    **What the neutered body returns changes how sharp the answer is.** For the
    checkers, whose results are concatenated, `return []` fails exactly the tests
    that cover that check -- so "1 failed" localises the coverage. `return None`
    breaks the concatenation instead, failing every check test at once: still proof
    the function is load-bearing, but no longer proof that any single test isolates
    it. Prefer the value the caller actually composes; the default suits list
    returns because that is what this codebase's checkers do.
    """
    original = path.read_text()
    if _already_inert(original, function, args_returns):
        return INERT, f"body is already `return {args_returns}`; nothing to neuter"
    mutated, why = _neuter_source(original, function, args_returns)
    if mutated is None:
        # A miss is reported, never fatal. Under `--all` an abort here stopped the
        # sweep at the first unmatchable signature, and every function *after* it
        # went silently unmutated -- which reads as a completed run. That is the
        # same false-clean failure this whole script exists to prevent, and it is
        # the fourth blind spot of exactly that shape.
        return None, why

    try:
        path.write_text(mutated)
        # Written *after* the mutation, holding both texts: the restore checks the
        # file still looks like what it wrote before putting the original back.
        SENTINEL.write_text(
            json.dumps({"path": str(path), "original": original, "mutated": mutated})
        )
        run = _run_suite(timeout=limit)
        if run.timed_out:
            if not run.failures:
                return TIMED_OUT, f"{run.summary}, no test failed before it; {_how_far(run, of)}"
            return True, (
                f"{run.summary}, {len(run.failures)} failed before it; {_how_far(run, of)}"
                + _caught_by(run.failures)
            )
        return not run.passed, run.summary + _caught_by(run.failures)
    finally:
        path.write_text(original)
        SENTINEL.unlink(missing_ok=True)
        _clear_pycache()


def _how_far(run: SuiteRun, of: int | None) -> str:
    """Where a stopped suite was: the test still running and for how long, and how
    many of the baseline's `of` tests had finished. One test running for most of the
    limit is a hang there; most tests done is a suite near its own time."""
    done = f"{run.finished} of {of} tests done" if of else f"{run.finished} tests done"
    if run.running is None:
        return f"no test running; {done}"
    return f"running {run.running} for {run.running_for:.0f}s; {done}"


def _mutant_limit(baseline_seconds: float) -> float:
    """How long a mutant's suite may run: `LIMIT_FACTOR` times the baseline's wall
    time, and never under `SUITE_TIMEOUT_SECONDS` (see there for why)."""
    return max(SUITE_TIMEOUT_SECONDS, LIMIT_FACTOR * baseline_seconds)


def _only(targets: list[str], only: str, path: Path) -> list[str]:
    """`targets` cut down to the names in `only` (comma-separated), in `targets`' order.

    **A name `targets` does not hold is refused, never skipped.** This is how
    `tools/mutation_gate.py --shard` splits one module across machines, and a name
    it passes that is not there -- renamed since, or a typo -- would otherwise be a
    target nobody ran in a log that reads as a finished sweep: the harness's
    recurring failure. A list naming nothing is refused for the same reason.
    """
    wanted = [name.strip() for name in only.split(",") if name.strip()]
    if not wanted:
        raise SystemExit(f"--only named no functions (got {only!r})")
    missing = [name for name in dict.fromkeys(wanted) if name not in targets]
    if missing:
        raise SystemExit(
            f"--only names what --all does not list in {path}: {', '.join(missing)}"
        )
    return [name for name in targets if name in wanted]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    parser.add_argument("function", nargs="?")
    parser.add_argument("--all", action="store_true")
    parser.add_argument(
        "--returns",
        default="[]",
        help="what the neutered body returns; see mutate() on why it matters",
    )
    parser.add_argument(
        "--only",
        metavar="NAME[,NAME...]",
        help=(
            "with --all: mutate only these of its targets, in its order; a name "
            "--all would not list is refused, never skipped"
        ),
    )
    args = parser.parse_args()

    if args.only is not None and not args.all:
        raise SystemExit("--only narrows --all's target list; give --all as well")

    path = ROOT / args.path
    if args.all:
        targets = _function_names(path.read_text())
        if not targets:
            raise SystemExit(f"--all found no module-level functions in {path}")
        if args.only is not None:
            targets = _only(targets, args.only, path)
    else:
        if not args.function:
            raise SystemExit("give a function name or --all")
        targets = [args.function]

    _restore_any_interrupted_run()
    baseline = _run_suite(timeout=BASELINE_TIMEOUT_SECONDS)
    if not baseline.passed:
        raise SystemExit(
            "\n".join(
                [f"suite is not green to begin with: {baseline.summary}", *baseline.failures]
            )
        )
    if not baseline.started:
        # The progress file is how a stopped suite is judged. A baseline that ran and
        # recorded nothing means the plugin is not loading, and every timeout after it
        # would be judged blind -- so the sweep refuses rather than starting.
        raise SystemExit(
            f"the progress plugin recorded no test during the baseline "
            f"({baseline.summary}); a suite stopped at its limit could not be judged. "
            f"Check {PROGRESS_PLUGIN_DIR / (PROGRESS_PLUGIN + '.py')} loads."
        )
    limit = _mutant_limit(baseline.seconds)
    print(
        f"baseline: {baseline.summary}; mutants stopped after {limit:.0f}s "
        f"({LIMIT_FACTOR} x this run's {baseline.seconds:.0f}s, never under "
        f"{SUITE_TIMEOUT_SECONDS}s)\n"
    )

    survivors = []
    skipped = []
    inert = []
    unsettled = []
    for name in targets:
        caught, summary = mutate(path, name, args.returns, limit=limit, of=baseline.started)
        if caught is None:
            skipped.append(name)
            print(f"  SKIPPED   {name:32} {summary}")
            continue
        if caught is INERT:
            inert.append(name)
            print(f"  inert     {name:32} {summary}")
            continue
        if caught is TIMED_OUT:
            unsettled.append(f"{name} ({summary})")
            print(f"  TIMED OUT {name:32} {summary}")
            continue
        # **Caught only when `mutate` said exactly True.** The other verdicts are
        # strings, and a string is truthy: a fall-through `if caught` would read any
        # verdict this loop does not know -- a new sentinel, a misspelt one -- as a
        # catch, which is this harness's recurring failure in a new place.
        if caught is True:
            print(f"  caught    {name:32} {summary}")
        elif caught is False:
            print(f"  SURVIVED  {name:32} {summary}")
            survivors.append(name)
        else:
            raise ValueError(
                f"mutate() gave {name} the verdict {caught!r}, which is none of True, "
                f"False, None, INERT or TIMED_OUT; refusing to read it as anything"
            )

    restored = _run_suite(timeout=BASELINE_TIMEOUT_SECONDS)
    ok = restored.passed
    print("\n".join([f"\nrestored: {restored.summary}", *restored.failures]))
    if inert:
        # Printed, never fatal, and never silent: these are functions no mutation
        # can reach, and a reader has to be able to tell that from coverage.
        print(f"\nNOT MUTABLE (already returns immediately): {', '.join(inert)}")
    if skipped:
        print(f"\nNOT MUTATED (signature not matched): {', '.join(skipped)}")
    if survivors:
        print(f"\nNOT COVERED: {', '.join(survivors)}")
    if unsettled:
        print(f"\nNOT SETTLED (timed out before any test failed): {', '.join(unsettled)}")
    if survivors or skipped or unsettled:
        return 1
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
