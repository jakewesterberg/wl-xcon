#!/usr/bin/env python3
"""The welfare-listed code between two revisions, by the manifest's own measure, and whether each
change to the manifest names the PI's approval.

    python3 tools/welfare_diff.py BASE HEAD

Run from the repository's root at every merge (`docs/design/architecture.md`, "Welfare-critical
modules"). `tests/test_welfare_manifest.py` holds every commit to `tests/welfare_manifest.json`,
but the manifest lives in the branch it judges: a branch that changes a listed function and its
hash in one commit is green. What the suite cannot see is whether that change was approved, so the
merge reads the manifest's own diff, and this prints it item by item.

For each item of HEAD's manifest it prints, measured with HEAD's definition of the item at both
revisions:
- `SAME` or `DIFFERS` (or `NEW`, an item whose code is not at BASE);
- `manifest changed`, with its `approved`, when the item's entry differs from BASE's (or BASE has
  none);
and for an item only BASE's manifest has, `REMOVED`; and `CHECK CHANGED` for each file of the check
itself (the manifest's test and this file) that differs.

It exits 1, saying why on each line, when:
- an item DIFFERS while its manifest entry is unchanged, or HEAD's code does not match HEAD's
  manifest, or an item cannot be found at HEAD;
- an item's entry changed and its `approved` is BASE's word for word, or does not name the PI and a
  date (`YYYY-MM-DD`): a form, not a proof, since only a person can check an approval against the
  PI's words;
- an item was removed (the list is the PI's; the controller reads his approval of it);
- the check itself changed (its diff is read before the merge).
It exits 0 otherwise, and 2 when a revision or a manifest cannot be read.

**This file also holds the measure** the suite uses: `tests/test_welfare_manifest.py` loads
`measure` and `as_reviewed` from here (as `tests/test_references.py` loads its checker's parser),
so the suite and the merge cut every item one way. Each kind of item:
- `module`: the whole file, byte for byte.
- `function`: its lines from its first decorator (or its `def`) to its last; a method is named
  `Class.name`.
- `constant`: the module-level assignment's lines.
- `first_statement`: the first statement of a function's body after its docstring, so both the
  statement and its place first are held.
- `line`: how many of a function's lines are exactly that text, stripped (a count, not a hash).
**A listed name must be bound exactly once in its module**: a `def` or `class`, an import (its
alias), an assignment, augmented assignment or `del` of it, a loop's or `with`'s or `except`'s
target, and an attribute target such as `Session._ends = ...` keyed `Session._ends`, in the module's
body or a class body and inside any `if`, `try`, `with`, `for`, `while` or `match` there; a
`from ... import *` counts as binding every module-level name. So a second binding that replaces a
listed function without touching its text fails. What the parser cannot see is not counted: a
binding made by `setattr`, `globals()`, `exec` or `:=`, or inside a function.
"""

from __future__ import annotations

import ast
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

MANIFEST = "tests/welfare_manifest.json"
#: The check itself: a change to either is read before a merge.
CHECK = ("tests/test_welfare_manifest.py", "tools/welfare_diff.py")
#: An `approved` names the PI and a date.
_PI = re.compile(r"\bthe PI\b")
_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
#: Statements whose bodies bind in the scope that holds them.
_BLOCKS = tuple(
    getattr(ast, name)
    for name in ("If", "While", "For", "AsyncFor", "With", "AsyncWith", "Try", "TryStar", "Match")
    if hasattr(ast, name)
)


class StaleMutation(Exception):
    """A file still holds the mutation an interrupted `tools/mutate.py` run left in it."""


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def names_approval(approved: object) -> bool:
    """Whether an `approved` names the PI and a date: its form, which is all a program can check."""
    return isinstance(approved, str) and bool(_PI.search(approved)) and bool(_DATE.search(approved))


def _dotted(node: ast.expr) -> str | None:
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        return ".".join([node.id, *reversed(parts)])
    return None


def _targets(node: ast.expr | None, prefix: str) -> list[str]:
    """The names an assignment target binds: a name in this scope, or an attribute by its dotted
    name (`Session._ends`)."""
    if isinstance(node, ast.Name):
        return [prefix + node.id]
    if isinstance(node, (ast.Tuple, ast.List)):
        return [name for element in node.elts for name in _targets(element, prefix)]
    if isinstance(node, ast.Starred):
        return _targets(node.value, prefix)
    if isinstance(node, ast.Attribute):
        dotted = _dotted(node)
        return [dotted] if dotted else []
    return []


def bindings(tree: ast.Module) -> dict[str, list[ast.AST]]:
    """Every binding the module and its class bodies make, by the name it binds (a method as
    `Class.name`), each with the statement that makes it."""
    found: dict[str, list[ast.AST]] = {}

    def add(names: list[str], node: ast.AST) -> None:
        for name in names:
            found.setdefault(name, []).append(node)

    def scope(body: list[ast.stmt], prefix: str) -> None:
        for node in body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                add([prefix + node.name], node)
            elif isinstance(node, ast.ClassDef):
                add([prefix + node.name], node)
                scope(node.body, f"{prefix}{node.name}.")
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                for alias in node.names:
                    bound = alias.asname or alias.name.split(".")[0]
                    add([prefix + bound], node)
            elif isinstance(node, ast.Assign):
                add([name for target in node.targets for name in _targets(target, prefix)], node)
            elif isinstance(node, (ast.AnnAssign, ast.AugAssign)):
                add(_targets(node.target, prefix), node)
            elif isinstance(node, ast.Delete):
                add([name for target in node.targets for name in _targets(target, prefix)], node)
            elif isinstance(node, _BLOCKS):
                if isinstance(node, (ast.For, ast.AsyncFor)):
                    add(_targets(node.target, prefix), node)
                if isinstance(node, (ast.With, ast.AsyncWith)):
                    for item in node.items:
                        add(_targets(item.optional_vars, prefix), node)
                if hasattr(ast, "Match") and isinstance(node, ast.Match):
                    for case in node.cases:
                        scope(case.body, prefix)
                    continue
                for handler in getattr(node, "handlers", ()):
                    if handler.name:
                        add([prefix + handler.name], handler)
                    scope(handler.body, prefix)
                for field in ("body", "orelse", "finalbody"):
                    scope(getattr(node, field, []), prefix)

    scope(tree.body, "")
    return found


def _bound_once(name: str, found: dict[str, list[ast.AST]], path: str) -> ast.AST:
    nodes = list(found.get(name, []))
    if "." not in name:
        # A star import may rebind any module-level name.
        nodes += found.get("*", [])
    if len(nodes) != 1:
        lines = sorted(getattr(node, "lineno", 0) for node in nodes)
        raise LookupError(f"{path} binds {name} {len(nodes)} times, not once (lines {lines})")
    return nodes[0]


def measure(item: dict, text: str) -> str | int:
    """What the manifest holds for `item`, measured in a file whose text is `text`: a SHA-256, or
    for a `line` its count. Raises `LookupError`, saying what is missing, when the item cannot be
    found or its name is bound more than once."""
    if item["kind"] == "module":
        return sha(text)
    lines = text.split("\n")
    name = item["qualname"] if item["kind"] in ("function", "constant") else item["within"]
    node = _bound_once(name, bindings(ast.parse(text)), item["path"])
    wanted = (ast.Assign, ast.AnnAssign) if item["kind"] == "constant" else (
        ast.FunctionDef, ast.AsyncFunctionDef)
    if not isinstance(node, wanted):
        raise LookupError(f"{item['path']}'s {name} is bound by a {type(node).__name__}, not what is "
                          f"listed")
    if item["kind"] == "constant":
        return sha("\n".join(lines[node.lineno - 1 : node.end_lineno]))
    if item["kind"] == "function":
        first = min([node.lineno, *(decorator.lineno for decorator in node.decorator_list)])
        return sha("\n".join(lines[first - 1 : node.end_lineno]))
    if item["kind"] == "first_statement":
        body = node.body
        if (
            body
            and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)
        ):
            body = body[1:]
        if not body:
            raise LookupError(f"{item['path']}'s {name} has no statement after its docstring")
        statement = body[0]
        return sha("\n".join(lines[statement.lineno - 1 : statement.end_lineno]))
    own = lines[node.lineno - 1 : node.end_lineno]
    return sum(line.strip() == item["line"] for line in own)


def as_reviewed(path: Path, text: str, sentinel: Path, in_sweep: bool) -> str:
    """`path`'s text as the manifest judges it. **Inside a suite `tools/mutate.py` launched**
    (`in_sweep`), a file the sentinel names that is still exactly its mutation is judged as the
    original the sentinel saved, so a neutered welfare function is judged by the tests of what it
    does rather than caught by its hash. **Anywhere else** that file is a mutation an interrupted
    run left behind, and `StaleMutation` says so. Any other file is judged as it stands."""
    try:
        saved = json.loads(sentinel.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return text
    if not (
        isinstance(saved, dict)
        and isinstance(saved.get("path"), str)
        and Path(saved["path"]).resolve() == path.resolve()
        and saved.get("mutated") == text
        and isinstance(saved.get("original"), str)
    ):
        return text
    if in_sweep:
        return saved["original"]
    raise StaleMutation(
        f"{sentinel} is a stale mutation sentinel: a tools/mutate.py run stopped while it held a "
        f"mutation of {path}, and the file is still that mutation. This suite is not one mutate.py "
        f"launched, so the file is judged as it stands, and fails. The next tools/mutate.py run "
        f"restores it from the sentinel; or put back the sentinel's `original` by hand and delete "
        f"the sentinel"
    )


def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], capture_output=True)


def _show(revision: str, path: str) -> str | None:
    done = _git("show", f"{revision}:{path}")
    return done.stdout.decode("utf-8") if done.returncode == 0 else None


def _manifest(revision: str) -> dict[str, dict]:
    text = _show(revision, MANIFEST)
    if text is None:
        return {}
    return {item["name"]: item for item in json.loads(text)["items"]}


def _at(item: dict, revision: str) -> str | int | None:
    text = _show(revision, item["path"])
    if text is None:
        return None
    try:
        return measure(item, text)
    except (LookupError, SyntaxError):
        return None


def compare(base: str, head: str) -> tuple[list[str], bool]:
    """The report's lines, and whether anything in it needs a person before the merge."""
    before, after = _manifest(base), _manifest(head)
    lines: list[str] = []
    bad = False
    for name, item in after.items():
        was, now = _at(item, base), _at(item, head)
        held = item.get("count") if item["kind"] == "line" else item.get("sha256")
        state = "NEW" if was is None else "SAME" if was == now else "DIFFERS"
        notes: list[str] = []
        problems: list[str] = []
        if now is None:
            problems.append(f"cannot be found at {head}")
        elif now != held:
            problems.append(f"{head}'s code does not match {head}'s manifest")
        if before.get(name) != item:
            approved = item.get("approved")
            notes.append(f"manifest changed, approved: {approved!r}")
            if name in before and before[name].get("approved") == approved:
                problems.append("its `approved` is unchanged from the base")
            elif not names_approval(approved):
                problems.append("its `approved` does not name the PI and a date")
        elif state == "DIFFERS":
            problems.append("its manifest entry is unchanged")
        bad = bad or bool(problems)
        said = "; ".join(notes + problems)
        lines.append(f"{'!' if problems else ' '} {state:8} {name}" + (f"  ({said})" if said else ""))
    for name in before:
        if name not in after:
            bad = True
            lines.append(f"! REMOVED  {name}  (the list is the PI's: read his approval of its removal)")
    for path in CHECK:
        if _show(base, path) != _show(head, path):
            bad = True
            lines.append(f"! CHECK CHANGED  {path}  (read its diff before the merge)")
    return lines, bad


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(__doc__.split("\n\n")[1], file=sys.stderr)
        return 2
    base, head = argv[1], argv[2]
    for revision in (base, head):
        if _git("rev-parse", "--verify", "--quiet", f"{revision}^{{commit}}").returncode != 0:
            print(f"welfare_diff: {revision!r} is not a commit here", file=sys.stderr)
            return 2
    try:
        lines, bad = compare(base, head)
    except (ValueError, KeyError) as unreadable:
        print(f"welfare_diff: a manifest cannot be read ({unreadable!r})", file=sys.stderr)
        return 2
    print("\n".join(lines))
    print(f"welfare_diff {base}..{head}: "
          + ("something above needs reading before the merge (lines marked !)" if bad
             else "nothing to read"))
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
