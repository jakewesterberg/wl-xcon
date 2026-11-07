"""The welfare-listed code is the code the PI approved, and the list is architecture.md's.

`docs/design/architecture.md`'s "Welfare-critical modules" section is the list: four whole
modules, named functions in five more files, a constant one of them reads, and three parts of
functions that are otherwise not listed (`cli.main`'s one line, and `taskd.Session._command`'s
reward pass-through and its `except` line). A change to any of it needs the PI's welfare review
before merge (CLAUDE.md). `tests/welfare_manifest.json` holds that list as data, each item with
the SHA-256 of its exact source as last approved (a line: its count), and this file holds the
tree to it. The PI, 2026-11-07, on an audit's finding that the proof that welfare code did not
change depended on a script only the controller had, which silently skipped any name it could
not find: "turn the welfare check and the fuzzer into tests in the repository".

**What each kind of item holds**, cut by the parser (`ast`), never by a pattern:
- `module`: the whole file, byte for byte.
- `function`: its lines from `def` to its last, as the controller's comparison cut them (the
  decorators and the comments above it excluded); a method is named `Class.name`.
- `constant`: the module-level assignment's lines.
- `first_statement`: the first statement of a function's body after its docstring, so both the
  statement and its place first are held (`Session._command` hands a manual reward to
  `_manual_reward` before anything else, in every phase).
- `line`: how many of a function's lines are exactly that text, stripped, which must be its
  `count` (a line commented out is not that line).

**A listed item that cannot be found fails**: a renamed, moved or deleted function, a file that
is gone, or a name defined twice. Nothing here is ever skipped.

**The manifest and architecture.md cannot drift apart.** Each item's `doc` phrase must be in the
section; and the section's own summary, its bold "In code, that is ..." sentence (the whole
modules, then for each other file its count of functions, the functions it names, and its count
of lines or parts), must agree with the manifest's items file by file. The constant is held by
the first direction only: the summary counts functions and parts, and the section names
`taskd.OUTSIDE_A_RUN` as part of `_manual_reward`'s rule.

**During a mutation sweep** `tools/mutate.py` neuters one function on disk and writes the file's
original beside it (its `SENTINEL`). That one file is judged here as its original, so a neutered
welfare function is caught by the tests of what it does, or survives, and is never caught by
its hash alone, which would report every welfare mutant caught; every other file is judged as
it stands.

The files map to no module, so the mutation gate selects nothing for them; each check was shown
to fail with a listed function, a name and architecture.md deliberately broken and then
restored (2026-11-07).
"""

from __future__ import annotations

import ast
import functools
import hashlib
import importlib.util
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = Path(__file__).resolve().parent / "welfare_manifest.json"
ARCHITECTURE = ROOT / "docs" / "design" / "architecture.md"
#: The sentence that opens architecture.md's welfare section; the next `## ` heading ends it.
SECTION = "Welfare-critical modules requiring human review"
#: The section's bold sentence that gives the list in code.
SUMMARY = "**In code, that is "
#: What an item of each kind must carry beside `name`, `kind`, `path`, `doc` and `approved`.
FIELDS = {
    "module": {"sha256"},
    "function": {"qualname", "sha256"},
    "constant": {"qualname", "sha256"},
    "first_statement": {"within", "sha256"},
    "line": {"within", "line", "count"},
}
#: The kinds the summary counts as parts of a function.
PARTS = ("first_statement", "line")
#: What a change needs (CLAUDE.md, "Welfare-critical code requires human review").
REVIEW = (
    "a change to welfare-listed code needs the PI's welfare review before merge, and "
    "tests/welfare_manifest.json updated in the same commit, the item's `sha256` (or `count`) "
    "and its `approved` naming his approval (CLAUDE.md; docs/design/architecture.md, "
    "'Welfare-critical modules')"
)
NUMBERS = {
    word: n
    for n, word in enumerate(
        "one two three four five six seven eight nine ten eleven twelve".split(), start=1
    )
}

ITEMS: list[dict] = json.loads(MANIFEST.read_text(encoding="utf-8"))["items"]


@functools.cache
def _sentinel() -> Path:
    """`tools/mutate.py`'s own `SENTINEL`, read from the tool so the two cannot disagree."""
    spec = importlib.util.spec_from_file_location(
        "wlx_mutate_for_welfare_manifest", ROOT / "tools" / "mutate.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.SENTINEL


def as_reviewed(path: Path, text: str, sentinel: Path) -> str:
    """`path`'s text as this file judges it: the original `tools/mutate.py` saved while it holds
    a mutation of that file (the sentinel names it, and the file is still exactly the mutation),
    and otherwise `text`, as it stands."""
    try:
        saved = json.loads(sentinel.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return text
    if (
        isinstance(saved, dict)
        and isinstance(saved.get("path"), str)
        and Path(saved["path"]).resolve() == path.resolve()
        and saved.get("mutated") == text
        and isinstance(saved.get("original"), str)
    ):
        return saved["original"]
    return text


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _definitions(tree: ast.Module) -> dict[str, list[ast.stmt]]:
    """Each module-level function, method (`Class.name`) and assigned name, with every
    definition of it, so a name defined twice is seen as twice."""
    found: dict[str, list[ast.stmt]] = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            found.setdefault(node.name, []).append(node)
        elif isinstance(node, ast.ClassDef):
            for sub in node.body:
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    found.setdefault(f"{node.name}.{sub.name}", []).append(sub)
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if isinstance(target, ast.Name):
                    found.setdefault(target.id, []).append(node)
    return found


def measure(item: dict, text: str) -> str | int:
    """What the manifest holds for `item`, measured in a file whose text is `text`: a SHA-256,
    or for a `line` its count. Raises `LookupError`, saying what is missing, when the item
    cannot be found."""
    if item["kind"] == "module":
        return _sha(text)
    lines = text.split("\n")
    name = item["qualname"] if item["kind"] in ("function", "constant") else item["within"]
    nodes = _definitions(ast.parse(text)).get(name, [])
    if len(nodes) != 1:
        raise LookupError(f"{item['path']} defines {name} {len(nodes)} times, not once")
    (node,) = nodes
    wanted = (ast.Assign, ast.AnnAssign) if item["kind"] == "constant" else (
        ast.FunctionDef, ast.AsyncFunctionDef)
    if not isinstance(node, wanted):
        raise LookupError(f"{item['path']}'s {name} is a {type(node).__name__}, not what is listed")
    if item["kind"] in ("function", "constant"):
        return _sha("\n".join(lines[node.lineno - 1 : node.end_lineno]))
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
        first = body[0]
        return _sha("\n".join(lines[first.lineno - 1 : first.end_lineno]))
    own = lines[node.lineno - 1 : node.end_lineno]
    return sum(line.strip() == item["line"] for line in own)


def test_the_manifest_is_well_formed():
    names = [item.get("name") for item in ITEMS]
    assert len(set(names)) == len(names), f"an item's name is used twice: {names}"
    for item in ITEMS:
        kind = item.get("kind")
        assert kind in FIELDS, f"{item.get('name')}: kind {kind!r} is none of {sorted(FIELDS)}"
        missing = ({"name", "kind", "path", "doc", "approved"} | FIELDS[kind]) - set(item)
        assert not missing, f"{item['name']} lacks {sorted(missing)}"
        assert str(item["approved"]).strip(), f"{item['name']}'s `approved` names no approval"
        if "sha256" in item:
            assert re.fullmatch(r"[0-9a-f]{64}", item["sha256"]), (
                f"{item['name']}'s sha256 {item['sha256']!r} is not a SHA-256 in hex")
        if kind == "line":
            assert type(item["count"]) is int, f"{item['name']}'s count is not a whole number"


@pytest.mark.parametrize("item", ITEMS, ids=[item["name"] for item in ITEMS])
def test_welfare_listed_code_is_as_approved(item):
    path = ROOT / item["path"]
    if not path.is_file():
        pytest.fail(
            f"{item['name']}: {item['path']} is not a file. A welfare-listed item that moved or "
            f"was removed fails, and is never skipped; {REVIEW}"
        )
    text = as_reviewed(path, path.read_bytes().decode("utf-8"), _sentinel())
    try:
        now = measure(item, text)
    except LookupError as missing:
        pytest.fail(
            f"{item['name']} cannot be found: {missing}. A renamed, moved or removed "
            f"welfare-listed item fails, and is never skipped; {REVIEW}"
        )
    if item["kind"] == "line":
        assert now == item["count"], (
            f"{item['name']}: {item['path']}'s {item['within']} has {now} lines that are exactly "
            f"{item['line']!r}, where the manifest says {item['count']} ({item['approved']}); "
            f"{REVIEW}"
        )
    else:
        assert now == item["sha256"], (
            f"{item['name']} has changed: its source's SHA-256 is {now}, the manifest's "
            f"{item['sha256']} ({item['approved']}); {REVIEW}"
        )


def _section() -> str:
    """architecture.md's welfare section, its whitespace runs made single spaces."""
    text = ARCHITECTURE.read_text(encoding="utf-8")
    start = text.find(SECTION)
    assert start >= 0, (
        f"docs/design/architecture.md has no {SECTION!r}: the welfare list's section moved or was "
        f"reworded, and tests/welfare_manifest.json is held to it"
    )
    end = text.find("\n## ", start)
    return " ".join(text[start : end if end >= 0 else len(text)].split())


def _number(word: str, where: str) -> int:
    assert word in NUMBERS, (
        f"architecture.md's welfare summary says {word!r} {where}, which this test cannot read as "
        f"a number; say it as one of {sorted(NUMBERS, key=NUMBERS.get)}"
    )
    return NUMBERS[word]


def _summary(section: str) -> tuple[set[str], dict[str, dict]]:
    """The section's summary of the list in code: the modules it lists whole, and for each other
    file its count of functions, the functions it names, its count of parts (lines inside a
    function, or parts of one) and the function holding them where it names it."""
    start = section.find(SUMMARY)
    assert start >= 0, (
        f"architecture.md's welfare section has no {SUMMARY!r} sentence: the summary the manifest "
        f"is held to moved or was reworded"
    )
    summary = section[start + 2 : section.find("**", start + 2)]
    whole: set[str] = set()
    files: dict[str, dict] = {}
    for found in re.finditer(r"(?:\b([a-z]+) (?:functions? )?in )?`wl_xcon/(\w+)\.py`", summary):
        count, module = found.group(1), found.group(2)
        if count is None:
            whole.add(module)
            continue
        rest = summary[found.end() :]
        names: list[str] = []
        listed = re.match(r"\s*\(([^)]*)\)", rest)
        if listed:
            names = re.findall(r"`([^`]+)`", listed.group(1))
            rest = rest[listed.end() :]
        parts = re.match(
            r",?\s*plus ([a-z]+) (?:lines?|parts?) (?:inside|of) a [a-z]+(?:\s*\(`([^`]+)`)?", rest
        )
        files[module] = {
            "functions": _number(count, f"of wl_xcon/{module}.py"),
            "names": names,
            "parts": _number(parts.group(1), f"of wl_xcon/{module}.py's parts") if parts else 0,
            "holder": parts.group(2) if parts else None,
        }
    return whole, files


def test_every_manifest_item_is_named_in_architecture():
    section = _section()
    unnamed = [
        f"{item['name']} ({item['doc']})"
        for item in ITEMS
        if " ".join(item["doc"].split()) not in section
    ]
    assert not unnamed, (
        f"tests/welfare_manifest.json lists what docs/design/architecture.md's welfare section "
        f"does not name: {unnamed}. The PI keeps the list: an item joins or leaves it in both, in "
        f"one commit naming his approval"
    )


def test_architecture_lists_nothing_the_manifest_lacks():
    whole, files = _summary(_section())
    problems = []
    listed_whole = {Path(item["path"]).stem for item in ITEMS if item["kind"] == "module"}
    if whole != listed_whole:
        problems.append(
            f"architecture.md lists {sorted(whole)} whole, the manifest {sorted(listed_whole)}")
    by_file: dict[str, list[dict]] = {}
    for item in ITEMS:
        if item["kind"] == "function" or item["kind"] in PARTS:
            by_file.setdefault(Path(item["path"]).stem, []).append(item)
    if set(files) != set(by_file):
        problems.append(
            f"architecture.md lists functions or parts in {sorted(files)}, the manifest in "
            f"{sorted(by_file)}")
    for module, said in files.items():
        items = by_file.get(module, [])
        functions = [item["qualname"] for item in items if item["kind"] == "function"]
        parts = [item for item in items if item["kind"] in PARTS]
        if said["functions"] != len(functions):
            problems.append(
                f"architecture.md counts {said['functions']} functions in wl_xcon/{module}.py, the "
                f"manifest {len(functions)}: {functions}")
        if said["names"] and len(said["names"]) != said["functions"]:
            problems.append(
                f"architecture.md counts {said['functions']} functions in wl_xcon/{module}.py and "
                f"names {len(said['names'])}: {said['names']}")
        problems += [
            f"architecture.md lists {name} in wl_xcon/{module}.py, which the manifest lacks"
            for name in said["names"]
            if name not in functions
        ]
        if said["parts"] != len(parts):
            problems.append(
                f"architecture.md counts {said['parts']} parts in wl_xcon/{module}.py, the "
                f"manifest {len(parts)}: {[item['name'] for item in parts]}")
        if said["holder"] is not None:
            problems += [
                f"architecture.md puts wl_xcon/{module}.py's parts in {said['holder']}, the "
                f"manifest {item['name']} in {item['within']}"
                for item in parts
                if item["within"] != said["holder"]
            ]
    assert not problems, (
        "docs/design/architecture.md's welfare summary and tests/welfare_manifest.json disagree:\n"
        + "\n".join(problems)
        + "\nThe PI keeps the list: an item joins or leaves it in both, in one commit naming his "
        "approval"
    )


def test_a_file_mutate_py_holds_is_judged_as_its_original(tmp_path):
    """While `tools/mutate.py` holds a mutation, the file it mutated is judged as the original it
    saved; any other file, or that file once it is no longer exactly the mutation, as it stands."""
    path, other, sentinel = tmp_path / "listed.py", tmp_path / "other.py", tmp_path / "s.json"
    original, mutated = "def f():\n    return 1\n", "def f():\n    return []\n"
    assert as_reviewed(path, mutated, sentinel) == mutated
    sentinel.write_text(json.dumps({"path": str(path), "original": original, "mutated": mutated}))
    assert as_reviewed(path, mutated, sentinel) == original
    assert as_reviewed(path, mutated + "# edited\n", sentinel) == mutated + "# edited\n"
    assert as_reviewed(other, mutated, sentinel) == mutated
    sentinel.write_text("{half a sentinel")
    assert as_reviewed(path, mutated, sentinel) == mutated
