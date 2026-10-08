"""The reference library stays consistent: every paper entered as the lab enters papers,
every citation in the docs resolving to one, every decision saying what it rests on.

`docs/references/library.bib` holds the papers, `docs/references/decisions.md` the
decisions they justify, and documents cite with Pandoc's `[@key]` (ADR-0010). What can
go wrong without anyone seeing it is a key cited in a document that is not in the
library, an entry no one can say they opened, and a decision with no stated basis --
each renders, or reads, as fine. Stdlib only: the library adds no dependency.

`tools/check_references.py` is the other half: it compares each DOI with Crossref's
record, which needs the network, so it never runs here; its own tests below use a canned
response. Its parser is the one these tests read the library with, so the file the
checker reads and the file these tests pass are read by one definition of the format.

The files map to no module, so the mutation gate selects nothing for them; each check
below was shown to fail with the library, a document or the checker deliberately broken
and then restored (2026-10-08).
"""

from __future__ import annotations

import datetime
import importlib.util
import io
import json
import re
import sys
import urllib.error
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
LIBRARY = DOCS / "references" / "library.bib"
DECISIONS = DOCS / "references" / "decisions.md"

_SPEC = importlib.util.spec_from_file_location(
    "wlx_check_references", ROOT / "tools" / "check_references.py"
)
refs = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = refs  # `dataclass` looks its module up while building `Entry`
_SPEC.loader.exec_module(refs)


def _entries() -> list:
    return refs.parse(LIBRARY.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# The library
# ---------------------------------------------------------------------------


def test_the_library_parses_and_is_not_empty():
    """Every line is the subset `parse` reads; a malformed one fails here with its
    line number (the next test proves the parser refuses rather than skips)."""
    assert _entries(), "docs/references/library.bib holds no entries"


@pytest.mark.parametrize(
    "text, line",
    [
        ("@article{a2000b,\n  title = {T},\n", 1),  # never closed
        ("@article{a2000b,\n  title = {T}\n  year 2000,\n}\n", 3),  # not a field
        ("@article{a2000b,\n  title = {T} x},\n}\n", 2),  # unbalanced braces
        ('@article{a2000b,\n  title = "T",\n}\n', 2),  # quoted, not braced
        ("@article{a2000b,\n  title = {T},\n  title = {U},\n}\n", 3),  # a field twice
        ("% a comment\n@article{a2000b,\n}\n", 1),  # text outside an entry
        ("@article{a2000b,\n  abstract = {one\n  two},\n}\n", 2),  # a field on two lines
    ],
)
def test_a_malformed_library_is_refused_at_its_line(text, line):
    with pytest.raises(refs.Malformed, match=rf"^line {line}:"):
        refs.parse(text)


def test_the_subset_reads_both_this_repositorys_layout_and_zoteros():
    """Zotero's stock exporter indents with a tab; ours with two spaces. Both are the
    subset, and nested braces stay part of the value."""
    ours = "@article{a2000b,\n  title = {On {Macaca} cones},\n  year = {2000},\n}\n"
    zotero = "@article{a2000b,\n\ttitle = {On {Macaca} cones},\n\tyear = {2000},\n}\n"
    for text in (ours, zotero):
        (entry,) = refs.parse(text)
        assert (entry.type, entry.key, entry.line) == ("article", "a2000b", 1)
        assert entry.fields == {"title": "On {Macaca} cones", "year": "2000"}


#: The words a key skips when it takes the title's first word: articles and
#: prepositions (the key rule in docs/references/README.md).
SKIPPED = frozenset(
    "a an the about above across after against along among around as at before behind "
    "below beneath beside between beyond by despite down during except for from in inside "
    "into like near of off on onto out outside over past per since through throughout to "
    "toward towards under underneath until up upon via with within without".split()
)
KEY = re.compile(r"^[a-z]+[0-9]{4}[a-z]+$")


def _expected_key(entry) -> str:
    """`<firstauthor><year><firstword>`: the first author's family name without
    particles, the year, and the title's first word that is not an article or a
    preposition, all lowercase ASCII letters."""
    words = refs.first_author(entry.fields.get("author", "")).split()
    while len(words) > 1 and words[0][:1].islower():  # "van Norren" -> "Norren"
        words.pop(0)
    title = (refs.letters(w) for w in entry.fields.get("title", "").split())
    first_word = next((w for w in title if w and w not in SKIPPED), "")
    return f"{refs.letters(' '.join(words))}{entry.fields.get('year', '')}{first_word}"


def test_keys_are_unique_and_follow_the_rule():
    """A key is what a document cites, so two entries with one key make every citation
    of it ambiguous, and a key that says 1987 for a 1988 paper is a citation that
    reads right and points wrong. A collision appends `b`, `c`, ..."""
    entries = _entries()
    keys = [e.key for e in entries]
    assert sorted({k for k in keys if keys.count(k) > 1}) == [], "keys used twice"
    bad = []
    for entry in entries:
        expected = _expected_key(entry)
        if not KEY.match(entry.key):
            bad.append((entry.line, entry.key, "not lowercase letters, a year, letters"))
        elif entry.key != expected and not (
            entry.key[:-1] == expected and entry.key[-1] in "bcdefghijklmnopqrstuvwxyz"
        ):
            bad.append((entry.line, entry.key, f"the rule gives {expected!r}"))
    assert bad == [], bad


#: What each entry type needs beyond `COMMON`. A type not listed here is refused; add
#: it, with what it needs, when the library first holds one.
REQUIRED = {
    "article": ("journal", "volume", "pages"),
    "incollection": ("booktitle", "publisher", "pages"),
    "inproceedings": ("booktitle", "pages"),
    "book": ("publisher",),
    "techreport": ("institution",),
}
COMMON = ("author", "title", "year", "note")
DOI = re.compile(r"^10\.\d{4,9}/\S+$")


def test_every_entry_has_the_fields_its_type_needs():
    """Enough to find the paper again and to cite it in a methods section: author,
    title, year, where it appeared, and a DOI (bare, `10.xxxx/...`, so the checker can
    look it up) or a URL."""
    bad = []
    for entry in _entries():
        if entry.type not in REQUIRED:
            bad.append((entry.key, f"type {entry.type!r} is not one of {sorted(REQUIRED)}"))
            continue
        needed = COMMON + REQUIRED[entry.type]
        missing = [f for f in needed if not entry.fields.get(f, "").strip()]
        if missing:
            bad.append((entry.key, f"missing {missing}"))
        if not re.fullmatch(r"\d{4}", entry.fields.get("year", "")):
            bad.append((entry.key, "year is not four digits"))
        doi, url = entry.fields.get("doi", ""), entry.fields.get("url", "")
        if not doi and not url:
            bad.append((entry.key, "neither doi nor url"))
        if doi and not DOI.match(doi):
            bad.append((entry.key, f"doi {doi!r} is not a bare 10.xxxx/... DOI"))
    assert bad == [], bad


NOTE = re.compile(r"^checked (?P<date>\d{4}-\d{2}-\d{2}): (?:full text|abstract)\b")


def test_every_note_says_when_the_paper_was_opened_and_how_much_of_it():
    """`note = {checked YYYY-MM-DD: full text | abstract ...}`: an entry is a paper
    someone opened (CLAUDE.md, "No fabrication"), and a claim resting on an abstract
    is weaker than one resting on the text, so the reader is told which."""
    bad = []
    for entry in _entries():
        match = NOTE.match(entry.fields.get("note", ""))
        if not match:
            bad.append((entry.key, "note is not `checked YYYY-MM-DD: full text|abstract ...`"))
            continue
        try:
            date = datetime.date.fromisoformat(match["date"])
        except ValueError:
            bad.append((entry.key, f"{match['date']} is not a date"))
            continue
        if date > datetime.date.today():
            bad.append((entry.key, f"checked on {date}, which has not happened yet"))
    assert bad == [], bad


# ---------------------------------------------------------------------------
# Citations in the documents
# ---------------------------------------------------------------------------

FENCE = re.compile(r"^[ \t]*(`{3,}|~{3,})")
#: A code span may wrap a line but, as in CommonMark, never crosses a blank one: a stray
#: backtick must not blank the rest of a file, and every citation in it, from the check.
CODE_SPAN = re.compile(r"(?<!`)(`+)(?!`)(?:(?!\n[ \t]*\n).)+?(?<!`)\1(?!`)", re.DOTALL)
BRACKETS = re.compile(r"\[([^\[\]]*)\]")
#: Pandoc's key: a letter, digit or `_`, then those and single internal punctuation
#: (pandoc.org/MANUAL.html, "Citation syntax", read 2026-10-08). The `@` must start a
#: word in the bracket, so `[mail a@b.org]` is not a citation.
CITATION = re.compile(
    r"(?<![^\s;])-?@([A-Za-z0-9_](?:[A-Za-z0-9_]|[:.#$%&+?<>~/-](?=[A-Za-z0-9_]))*)"
)


def prose(text: str) -> str:
    """`text` with fenced code blocks and inline code spans blanked, newlines kept, so
    an example of citing is never read as a citation and line numbers still hold."""
    lines, fence = [], None
    for line in text.split("\n"):
        opening = FENCE.match(line)
        if fence is None and opening:
            fence = opening[1]
            lines.append("")
        elif fence is not None:
            closing = line.strip()
            if closing and set(closing) == {fence[0]} and len(closing) >= len(fence):
                fence = None
            lines.append("")
        else:
            lines.append(line)
    return CODE_SPAN.sub(lambda m: re.sub(r"[^\n]", " ", m[0]), "\n".join(lines))


def citations(text: str) -> list[tuple[int, str]]:
    """`(line, key)` for every key cited in brackets in `text`'s prose: `[@key]`,
    `[@key, p. 3]`, `[see @a; @b]`, `[-@key]`. Pandoc's author-in-text form, a bare
    `@key`, is not read; docs/references/README.md says to use the bracketed forms."""
    text = prose(text)
    found = []
    for group in BRACKETS.finditer(text):
        for key in CITATION.finditer(group[1]):
            found.append((text.count("\n", 0, group.start(1) + key.start()) + 1, key[1]))
    return found


def test_citations_are_read_from_prose_only():
    text = "\n".join(
        [
            "Prose cites [@alpha1990one] and [see @beta1991two, p. 3; -@gamma1992three].",
            "A code span `[@delta1993four]` is not a citation, nor is ``[@eps1994five]``.",
            "```markdown",
            "- **Basis:** [@zeta1995six] in an example",
            "```",
            "   ~~~",
            "   [@eta1996seven]",
            "   ~~~",
            "An address [mail a@b.org] is not one; a split one [see",
            "@theta1997eight] is.",
            "A stray ` backtick ends with its paragraph,",
            "",
            "so [@iota1998nine] after a blank line is read, before a later `code span`.",
        ]
    )
    assert citations(text) == [
        (1, "alpha1990one"),
        (1, "beta1991two"),
        (1, "gamma1992three"),
        (10, "theta1997eight"),
        (13, "iota1998nine"),
    ]


def test_every_citation_in_the_docs_resolves_to_the_library():
    """Review focus 1 of the plan: a key cited in a document and absent from the
    library renders as a bare key, or a warning nobody reads, and the claim beside it
    has no source."""
    keys = {entry.key for entry in _entries()}
    unresolved = []
    for path in sorted(DOCS.rglob("*.md")):
        for line, key in citations(path.read_text(encoding="utf-8")):
            if key not in keys:
                unresolved.append(f"{path.relative_to(ROOT)}:{line}: {key}")
    assert unresolved == [], unresolved


# ---------------------------------------------------------------------------
# The decisions
# ---------------------------------------------------------------------------

LINK = re.compile(r"\[[^\]]+\]\(([^)\s]+)\)")
DECISION_FIELD = re.compile(r"^- \*\*(?P<name>Decided|Where|Basis):\*\*(?P<value>.*)$")


def _decisions() -> list[tuple[int, str, dict[str, str]]]:
    """`(line, heading, {field: value})` for every `### ` entry under a `## ` area."""
    found: list[tuple[int, str, dict[str, str]]] = []
    for number, line in enumerate(DECISIONS.read_text(encoding="utf-8").splitlines(), 1):
        if line.startswith("## "):
            found.append((number, "", {}))  # an area: closes the entry before it
        elif line.startswith("### "):
            found.append((number, line[4:].strip(), {}))
        elif found and found[-1][1] and (field := DECISION_FIELD.match(line)):
            found[-1][2][field["name"]] = field["value"].strip()
    return [decision for decision in found if decision[1]]


def test_decisions_holds_entries():
    assert _decisions(), "docs/references/decisions.md holds no entries"


def test_every_decision_says_when_where_and_on_what_basis():
    """**Decided** (starting with its date), **Where** and **Basis**, each saying
    something. A decision without its basis is the thing this file exists to end; one
    that rests on the PI's word or a rule says so in **Basis** rather than leaving it
    blank."""
    bad = []
    for line, heading, fields in _decisions():
        for name in ("Decided", "Where", "Basis"):
            if not fields.get(name):
                bad.append((line, heading, f"no **{name}:**"))
        if fields.get("Decided") and not re.match(r"\d{4}-\d{2}-\d{2}\b", fields["Decided"]):
            bad.append((line, heading, "**Decided:** does not start with its date"))
    assert bad == [], bad


def test_every_link_in_decisions_names_a_file_that_exists():
    """A **Where** is the decision's address. When a document is renamed the link
    points at nothing, and nothing else would notice. Anchors are not checked, as in
    `test_backlog.py`: a heading can change wording without the file moving."""
    missing = []
    for number, line in enumerate(DECISIONS.read_text(encoding="utf-8").splitlines(), 1):
        for target in LINK.findall(line):
            if "://" in target or target.startswith("#"):
                continue
            if not (DECISIONS.parent / target.partition("#")[0]).resolve().exists():
                missing.append((number, target))
    assert missing == [], missing


# ---------------------------------------------------------------------------
# tools/check_references.py, against a canned Crossref record
# ---------------------------------------------------------------------------

#: Crossref's record for 10.1017/S0952523800001917, fetched 2026-10-08 and trimmed to
#: the fields the checker reads. Its last author has given and family swapped, as
#: Crossref really has it; only the first author is compared.
SCHNAPF = {
    "title": ["Spectral sensitivity of primate photoreceptors"],
    "author": [
        {"given": "J.L.", "family": "Schnapf", "sequence": "first"},
        {"given": "T.W.", "family": "Kraft", "sequence": "additional"},
        {"given": "B.J.", "family": "Nunn", "sequence": "additional"},
        {"given": "Baylor", "family": "D.A.", "sequence": "additional"},
    ],
    "issued": {"date-parts": [[1988, 5]]},
    "published-print": {"date-parts": [[1988, 5]]},
    "published-online": {"date-parts": [[2009, 6, 2]]},
    "container-title": ["Visual Neuroscience"],
    "volume": "1",
    "page": "255-261",
}


def _schnapf(**changes) -> object:
    fields = {
        "author": "Schnapf, J. L. and Kraft, T. W. and Nunn, B. J. and Baylor, D. A.",
        "title": "Spectral sensitivity of primate photoreceptors",
        "year": "1988",
        "doi": "10.1017/S0952523800001917",
    }
    fields.update(changes)
    return refs.Entry("article", "schnapf1988spectral", fields, 1)


def test_the_checker_passes_an_entry_that_agrees_with_crossref():
    verdict, line = refs.check(_schnapf(), lambda doi: SCHNAPF)
    assert (verdict, line.split()) == (refs.OK, ["ok", "schnapf1988spectral"])


def test_the_checker_ignores_typography_but_not_words():
    """Case, punctuation, braces, accents and HTML tags are folded away; a different
    word is not."""
    styled = {**SCHNAPF, "title": ["Spectral Sensitivity of <i>Primate</i> Photoreceptors."]}
    assert refs.check(_schnapf(title="Spectral sensitivity of {primate} photoreceptors"),
                      lambda doi: styled)[0] == refs.OK
    assert refs.check(_schnapf(title="Spectral sensitivity of primate rods"),
                      lambda doi: styled)[0] == refs.MISMATCH


@pytest.mark.parametrize(
    "changes, said",
    [
        ({"year": "1987"}, "year '1987'"),
        ({"year": "2009"}, "year '2009'"),  # the online date of a 1988 paper is not its year
        ({"author": "Baylor, D. A. and Nunn, B. J."}, "first author 'baylor'"),
        (
            {"title": "Spectral sensitivity of cones of the monkey"},
            "title 'spectral sensitivity of cones",
        ),
    ],
)
def test_the_checker_names_what_disagrees(changes, said):
    verdict, line = refs.check(_schnapf(**changes), lambda doi: SCHNAPF)
    assert verdict == refs.MISMATCH
    assert line.startswith("MISMATCH") and said in line


def test_the_checker_takes_the_print_year_when_online_came_first():
    """A paper online in December and in the next year's volume is cited by the
    volume's year; Crossref's `issued` is then the earlier one."""
    online_first = {**SCHNAPF, "issued": {"date-parts": [[1987, 12]]}}
    assert refs.check(_schnapf(), lambda doi: online_first)[0] == refs.OK


def test_the_checker_reports_what_it_could_not_reach():
    def offline(doi):
        raise urllib.error.URLError("no route to host")

    def unknown(doi):
        raise urllib.error.HTTPError(doi, 404, "Not Found", None, None)

    assert refs.check(_schnapf(), offline)[0] == refs.UNREACHABLE
    verdict, line = refs.check(_schnapf(), unknown)
    assert verdict == refs.UNREACHABLE and "HTTP 404" in line
    no_doi = _schnapf()
    del no_doi.fields["doi"]
    assert refs.check(no_doi, offline)[0] == refs.NO_DOI


def test_the_checker_exits_by_its_worst_line(tmp_path, capsys):
    """1 on any mismatch, 2 when nothing mismatched but something went unchecked, 0
    only when every DOI was fetched and agreed."""
    library = tmp_path / "library.bib"
    library.write_text(
        "@article{schnapf1988spectral,\n"
        "  author = {Schnapf, J. L. and Kraft, T. W.},\n"
        "  title = {Spectral sensitivity of primate photoreceptors},\n"
        "  year = {1988},\n"
        "  doi = {10.1017/S0952523800001917},\n"
        "}\n"
    )
    argv = ["--library", str(library)]
    assert refs.main(argv, fetcher=lambda doi: SCHNAPF) == 0
    assert refs.main(argv, fetcher=lambda doi: {**SCHNAPF, "title": ["Other"]}) == 1

    def offline(doi):
        raise urllib.error.URLError("no route to host")

    assert refs.main(argv, fetcher=offline) == 2
    assert "of 1: 0 ok, 0 mismatched, 1 unreachable" in capsys.readouterr().out


def test_the_fetch_asks_crossref_for_the_quoted_doi_and_refuses_a_non_record(monkeypatch):
    """No network: `urlopen` is replaced. A DOI's parentheses are quoted, the request
    names this tool, and a body that is not a Crossref work record is an error rather
    than an empty record that would then mismatch on everything."""
    asked = []

    def answer(body):
        def urlopen(request, timeout):
            asked.append((request.full_url, request.get_header("User-agent"), timeout))
            return io.BytesIO(json.dumps(body).encode())

        return urlopen

    monkeypatch.setattr(refs.urllib.request, "urlopen", answer({"message": SCHNAPF}))
    assert refs.fetch("10.1016/S0042-6989(00)00021-3") == SCHNAPF
    url, agent, timeout = asked[-1]
    assert url == "https://api.crossref.org/works/10.1016/S0042-6989%2800%2900021-3"
    assert agent == refs.USER_AGENT and timeout == refs.TIMEOUT_SECONDS

    monkeypatch.setattr(refs.urllib.request, "urlopen", answer({"status": "failed"}))
    with pytest.raises(ValueError):
        refs.fetch("10.1017/S0952523800001917")
