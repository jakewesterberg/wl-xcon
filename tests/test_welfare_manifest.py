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

**How each kind of item is measured is `tools/welfare_diff.py`'s** (its docstring says each),
loaded here so the suite and the merge-time comparison cut every item one way: by the parser,
never by a pattern; a function from its first decorator; and a listed name bound exactly once in
its module, so a second `def`, a class-body or attribute rebinding, or an import that shadows it
fails as surely as an edit to its text.

**A listed item that cannot be found fails**: a renamed, moved or deleted function, a file that
is gone, or a name bound twice. Nothing here is ever skipped.

**The manifest and architecture.md cannot drift apart.** Each item's `doc` phrase must be in the
section and must name what the item measures; the section's own summary, its bold "In code, that
is ..." sentence (the whole modules, then for each other file its count of functions, the
functions it names, and its count of lines or parts), must agree with the manifest's items file
by file; and every constant the section names (`` `module.UPPER_CASE` ``) must be a manifest
constant. Prose elsewhere in the section that names something the summary does not is not read.

**This suite cannot see an approval**, only that a hash was updated; and the manifest lives in
the branch it judges. So at a merge its own diff is read (`tools/welfare_diff.py BASE HEAD`,
tested last below): architecture.md's welfare section gives the rule.

**During a mutation sweep** `tools/mutate.py` neuters one function on disk and writes the file's
original beside it (its `SENTINEL`). Inside a suite mutate.py launched (it sets its `PROGRESS_ENV`
for the suites it runs, and nothing else does), that one file is judged as its original, so a
neutered welfare function is caught by the tests of what it does, or survives, rather than caught
by its hash. **Outside one, a file still holding the mutation a sentinel names fails**, naming the
stale sentinel: an interrupted run must not pass for the approved code. `tests/test_mutate.py`
drives `mutate` with this reading, so the sentinel's format cannot change unseen.

The files map to no module, so the mutation gate selects nothing for them; each check was shown
to fail with a listed function, a name, a binding, a sentinel, the manifest and architecture.md
deliberately broken and then restored (2026-11-07).
"""

from __future__ import annotations

import functools
import importlib.util
import json
import os
import re
import subprocess
import sys
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
    "and its `approved` naming his approval and its date (CLAUDE.md; docs/design/architecture.md, "
    "'Welfare-critical modules')"
)
NUMBERS = {
    word: n
    for n, word in enumerate(
        "one two three four five six seven eight nine ten eleven twelve".split(), start=1
    )
}


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


#: The measure and the sweep's reading, one definition with the merge-time comparison.
welfare_diff = _load("wlx_welfare_diff", ROOT / "tools" / "welfare_diff.py")
ITEMS: list[dict] = json.loads(MANIFEST.read_text(encoding="utf-8"))["items"]


@functools.cache
def _mutate():
    """`tools/mutate.py`, for its own `SENTINEL` and `PROGRESS_ENV`, so the two cannot disagree."""
    return _load("wlx_mutate_for_welfare_manifest", ROOT / "tools" / "mutate.py")


def test_the_manifest_is_well_formed():
    names = [item.get("name") for item in ITEMS]
    assert len(set(names)) == len(names), f"an item's name is used twice: {names}"
    for item in ITEMS:
        kind = item.get("kind")
        assert kind in FIELDS, f"{item.get('name')}: kind {kind!r} is none of {sorted(FIELDS)}"
        missing = ({"name", "kind", "path", "doc", "approved"} | FIELDS[kind]) - set(item)
        assert not missing, f"{item['name']} lacks {sorted(missing)}"
        assert welfare_diff.names_approval(item["approved"]), (
            f"{item['name']}'s `approved` ({item['approved']!r}) does not name the PI and a date")
        if "sha256" in item:
            assert re.fullmatch(r"[0-9a-f]{64}", item["sha256"]), (
                f"{item['name']}'s sha256 {item['sha256']!r} is not a SHA-256 in hex")
        if kind == "line":
            assert type(item["count"]) is int, f"{item['name']}'s count is not a whole number"
        # The phrase that ties an item to architecture.md names what it measures.
        measured = item["path"] if kind == "module" else item.get("qualname") or item["within"]
        assert (measured if kind == "module" else measured.split(".")[-1]) in item["doc"], (
            f"{item['name']}'s doc {item['doc']!r} does not name {measured}, which it measures")


@pytest.mark.parametrize("item", ITEMS, ids=[item["name"] for item in ITEMS])
def test_welfare_listed_code_is_as_approved(item):
    path = ROOT / item["path"]
    if not path.is_file():
        pytest.fail(
            f"{item['name']}: {item['path']} is not a file. A welfare-listed item that moved or "
            f"was removed fails, and is never skipped; {REVIEW}"
        )
    mutate = _mutate()
    try:
        text = welfare_diff.as_reviewed(
            path,
            path.read_bytes().decode("utf-8"),
            mutate.SENTINEL,
            in_sweep=bool(os.environ.get(mutate.PROGRESS_ENV)),
        )
    except welfare_diff.StaleMutation as stale:
        pytest.fail(f"{item['name']}: {stale}")
    try:
        now = welfare_diff.measure(item, text)
    except LookupError as missing:
        pytest.fail(
            f"{item['name']} cannot be found: {missing}. A renamed, moved, removed or rebound "
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
    section = _section()
    whole, files = _summary(section)
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
    # Constants: the summary counts none, so each the section names must be a manifest constant.
    constants = {(Path(item["path"]).stem, item["qualname"]) for item in ITEMS
                 if item["kind"] == "constant"}
    problems += [
        f"architecture.md names the constant {module}.{name}, which the manifest lacks"
        for module, name in sorted(set(re.findall(r"`([a-z_][a-z0-9_]*)\.([A-Z][A-Z0-9_]*)`",
                                                  section)))
        if (module, name) not in constants
    ]
    assert not problems, (
        "docs/design/architecture.md's welfare section and tests/welfare_manifest.json disagree:\n"
        + "\n".join(problems)
        + "\nThe PI keeps the list: an item joins or leaves it in both, in one commit naming his "
        "approval"
    )


# --- The measure ---------------------------------------------------------------------------------

#: A listed method, bound once.
_ONCE = "class Session:\n    def _ends(self, index):\n        return index > 3\n"
_ENDS = {"kind": "function", "path": "x.py", "qualname": "Session._ends"}


def test_a_function_is_held_from_its_first_decorator():
    decorated = _ONCE.replace("    def _ends", "    @staticmethod\n    def _ends")
    assert welfare_diff.measure(_ENDS, decorated) == welfare_diff.sha(
        "    @staticmethod\n    def _ends(self, index):\n        return index > 3")
    assert welfare_diff.measure(_ENDS, decorated) != welfare_diff.measure(_ENDS, _ONCE)


@pytest.mark.parametrize(
    ("item", "text"),
    [
        (_ENDS, _ONCE + "    _ends = print\n"),
        (_ENDS, _ONCE + "Session._ends = lambda self, index: False\n"),
        (_ENDS, _ONCE + "if True:\n    Session._ends = print\n"),
        (_ENDS, _ONCE + "    if True:\n        def _ends(self):\n            pass\n"),
        ({**_ENDS, "qualname": "gate"}, "def gate():\n    pass\nfrom os import sep as gate\n"),
        ({**_ENDS, "qualname": "gate"}, "def gate():\n    pass\ntry:\n    pass\nexcept OSError as gate:\n"
                                        "    pass\n"),
        ({**_ENDS, "qualname": "gate"}, "def gate():\n    pass\nfor gate in ():\n    pass\n"),
        ({**_ENDS, "qualname": "gate"}, "def gate():\n    pass\nwith open('x') as gate:\n    pass\n"),
        ({**_ENDS, "qualname": "gate"}, "def gate():\n    pass\ndel gate\n"),
        ({**_ENDS, "qualname": "gate"}, "def gate():\n    pass\nfrom os import *\n"),
        ({"kind": "constant", "path": "x.py", "qualname": "PHASES"},
         "PHASES = ('a',)\nPHASES += ('b',)\n"),
        ({**_ENDS, "qualname": "gate"}, "x = 1\n"),
    ],
    ids=["class-body", "attribute", "attribute-in-if", "def-in-class-if", "import", "except-as",
         "for-target", "with-target", "del", "star-import", "augmented", "absent"],
)
def test_a_listed_name_not_bound_exactly_once_cannot_be_found(item, text):
    with pytest.raises(LookupError, match="times, not once"):
        welfare_diff.measure(item, text)


def test_a_name_bound_once_is_found_whatever_else_the_module_binds():
    text = _ONCE + "import os\nfrom os import sep\nOther = Session\nfor index in ():\n    pass\n"
    assert welfare_diff.measure(_ENDS, text) == welfare_diff.measure(_ENDS, _ONCE)


# --- The sweep's reading of mutate.py's sentinel ------------------------------------------------

def test_a_file_mutate_py_holds_is_its_original_in_a_sweep_and_a_failure_outside_one(tmp_path):
    """Inside a suite `tools/mutate.py` launched, the file it mutated is judged as the original it
    saved; outside one, that file still holding the mutation is a stale sentinel, and fails; any
    other file, or that file once it is no longer exactly the mutation, is judged as it stands."""
    path, other, sentinel = tmp_path / "listed.py", tmp_path / "other.py", tmp_path / "s.json"
    original, mutated = "def f():\n    return 1\n", "def f():\n    return []\n"
    for in_sweep in (True, False):
        assert welfare_diff.as_reviewed(path, mutated, sentinel, in_sweep) == mutated
    sentinel.write_text(json.dumps({"path": str(path), "original": original, "mutated": mutated}))
    assert welfare_diff.as_reviewed(path, mutated, sentinel, in_sweep=True) == original
    with pytest.raises(welfare_diff.StaleMutation, match="stale mutation sentinel"):
        welfare_diff.as_reviewed(path, mutated, sentinel, in_sweep=False)
    for in_sweep in (True, False):
        edited = mutated + "# edited\n"
        assert welfare_diff.as_reviewed(path, edited, sentinel, in_sweep) == edited
        assert welfare_diff.as_reviewed(other, mutated, sentinel, in_sweep) == mutated
    sentinel.write_text("{half a sentinel")
    assert welfare_diff.as_reviewed(path, mutated, sentinel, in_sweep=False) == mutated


# --- The merge-time comparison -------------------------------------------------------------------

def test_welfare_diff_reads_each_item_and_refuses_a_change_without_the_pis_approval(tmp_path):
    """`tools/welfare_diff.py BASE HEAD` in a scratch repository: a listed function changed with its
    hash but its `approved` left as it was is refused, and so is one whose `approved` names no one;
    the same with an `approved` naming the PI and a date passes, the item read `DIFFERS`; a
    revision against itself reads `SAME`."""
    def git(*args):
        subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid",
                        "-c", "commit.gpgsign=false", "-c", "core.hooksPath=/dev/null", *args],
                       cwd=tmp_path, check=True, capture_output=True)

    def commit(body, approved):
        source = f"def gate(item):\n    return {body}\n"
        item = {"name": "listed.gate", "kind": "function", "path": "wl_xcon/listed.py",
                "qualname": "gate", "doc": "`listed.gate`", "approved": approved}
        item["sha256"] = welfare_diff.measure(item, source)
        (tmp_path / "wl_xcon").mkdir(exist_ok=True)
        (tmp_path / "tests").mkdir(exist_ok=True)
        (tmp_path / "wl_xcon" / "listed.py").write_text(source)
        (tmp_path / "tests" / "welfare_manifest.json").write_text(json.dumps({"items": [item]}))
        git("add", "-A")
        git("commit", "-q", "-m", body)
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=tmp_path, check=True,
                              capture_output=True, text=True).stdout.strip()

    def diff(base, head):
        return subprocess.run([sys.executable, str(ROOT / "tools" / "welfare_diff.py"), base, head],
                              cwd=tmp_path, capture_output=True, text=True)

    git("init", "-q")
    base = commit("item is None", "the PI, 2026-01-02")
    unapproved = commit("item is not None", "the PI, 2026-01-02")
    unnamed = commit("item is not None", "approved")
    approved = commit("item is not None", "the PI, 2026-11-07, asked in the UI: 'Approve'")

    same = diff(base, base)
    assert same.returncode == 0 and "  SAME     listed.gate" in same.stdout, same.stdout + same.stderr
    refused = diff(base, unapproved)
    assert refused.returncode == 1, refused.stdout + refused.stderr
    assert "! DIFFERS  listed.gate" in refused.stdout, refused.stdout
    assert "its `approved` is unchanged from the base" in refused.stdout, refused.stdout
    refused = diff(unapproved, unnamed)
    assert refused.returncode == 1, refused.stdout + refused.stderr
    assert "its `approved` does not name the PI and a date" in refused.stdout, refused.stdout
    passed = diff(unapproved, approved)
    assert passed.returncode == 0, passed.stdout + passed.stderr
    assert "  SAME     listed.gate  (manifest changed" in passed.stdout, passed.stdout
    passed = diff(base, approved)
    assert passed.returncode == 0 and "  DIFFERS  listed.gate  (manifest changed" in passed.stdout, (
        passed.stdout + passed.stderr)
