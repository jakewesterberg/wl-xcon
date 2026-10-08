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
import http.client
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
        ("@article{a2000b,\n  year = 2000,\n}\n", 2),  # a bare value outside `month`
        ("@article{a2000b,\n  month = march,\n}\n", 2),  # not one of the twelve macros
        ("@article{a2000b,\n  month = foo,\n}\n", 2),  # nor this
        ("@article{a2000b,\n  note = mar,\n}\n", 2),  # a month macro, but not in `month`
    ],
)
def test_a_malformed_library_is_refused_at_its_line(text, line):
    with pytest.raises(refs.Malformed, match=rf"^line {line}:"):
        refs.parse(text)


def test_the_subset_reads_both_this_repositorys_layout_and_zoteros():
    """Ours indents with two spaces. Zotero's stock exporter indents with a tab and
    writes `month` as a bare macro, `month = mar` (`BibTeX.js` at zotero/translators
    6d4490d), the one unbraced value the subset allows. Nested braces stay part of the
    value."""
    ours = "@article{a2000b,\n  title = {On {Macaca} cones},\n  year = {2000},\n}\n"
    zotero = (
        "@article{a2000b,\n\ttitle = {On {Macaca} cones},\n\tmonth = mar,\n"
        "\tyear = {2000},\n}\n"
    )
    for text, extra in ((ours, {}), (zotero, {"month": "mar"})):
        (entry,) = refs.parse(text)
        assert (entry.type, entry.key, entry.line) == ("article", "a2000b", 1)
        assert entry.fields == {"title": "On {Macaca} cones", "year": "2000", **extra}


#: The words a key skips when it takes the title's first word: articles and
#: prepositions (the key rule in docs/references/README.md).
SKIPPED = frozenset(
    "a an the about above across after against along among around as at before behind "
    "below beneath beside between beyond by despite down during except for from in inside "
    "into like near of off on onto out outside over past per since through throughout to "
    "toward towards under underneath until up upon via with within without".split()
)
#: Author part, year, title word. The year is the four digits just before the closing
#: letters, so a short name with a digit in it parses: `nc3rs2012refining` is `nc3rs`,
#: 2012, `refining`.
KEY = re.compile(r"^(?P<author>[a-z0-9]+)(?P<year>[0-9]{4})(?P<word>[a-z]+)$")


def _expected_key(entry) -> str:
    """`<firstauthor><year><firstword>`: the first author's family name without
    particles, the year, and the title's first word that is not an article or a
    preposition, all lowercase ASCII letters. An organization that is the author
    (`{Video Electronics Standards Association}`) is cited by its usual short name,
    BibLaTeX's `shortauthor` (`{VESA}`), and that name, digits kept, is the author part
    (docs/references/README.md, "Keys")."""
    short = entry.fields.get("shortauthor", "")
    if short:
        author = re.sub(r"[^a-z0-9]", "", refs.fold(short))
    else:
        words = refs.first_author(entry.fields.get("author", "")).split()
        while len(words) > 1 and words[0][:1].islower():  # "van Norren" -> "Norren"
            words.pop(0)
        author = refs.letters(" ".join(words))
    title = (refs.letters(w) for w in entry.fields.get("title", "").split())
    first_word = next((w for w in title if w and w not in SKIPPED), "")
    return f"{author}{entry.fields.get('year', '')}{first_word}"


def _key_problems(entries) -> list[tuple[int, str, str]]:
    """`(line, key, what is wrong)` for every key off the rule. A digit in the author
    part comes only from a `shortauthor`. A suffix letter is a collision's, so it stands
    only beside the unsuffixed key it collided with."""
    keys = {entry.key for entry in entries}
    bad = []
    for entry in entries:
        expected = _expected_key(entry)
        parts = KEY.match(entry.key)
        if not parts:
            bad.append((entry.line, entry.key, "not a lowercase author, a year, letters"))
        elif not entry.fields.get("shortauthor") and not parts["author"].isalpha():
            bad.append((entry.line, entry.key, "a digit in the author part, but no shortauthor"))
        elif entry.key == expected:
            continue
        elif entry.key[:-1] != expected or entry.key[-1] not in "bcdefghijklmnopqrstuvwxyz":
            bad.append((entry.line, entry.key, f"the rule gives {expected!r}"))
        elif expected not in keys:
            bad.append((entry.line, entry.key, f"a collision suffix, but no {expected!r}"))
    return bad


def test_keys_are_unique_and_follow_the_rule():
    """A key is what a document cites, so two entries with one key make every citation
    of it ambiguous, and a key that says 1987 for a 1988 paper is a citation that
    reads right and points wrong. A collision appends `b`, `c`, ..."""
    entries = _entries()
    keys = [e.key for e in entries]
    assert sorted({k for k in keys if keys.count(k) > 1}) == [], "keys used twice"
    assert _key_problems(entries) == []


def test_a_collision_suffix_needs_the_key_it_collided_with():
    """`baylor1987spectrall` alone is a typo that the suffix rule would otherwise wave
    through; beside `baylor1987spectral` a `b` is the rule working."""
    entry = (
        "@article{{{key},\n  author = {{Baylor, D. A.}},\n"
        "  title = {{Spectral cones}},\n  year = {{1987}},\n}}\n"
    )
    alone = refs.parse(entry.format(key="baylor1987spectrall"))
    assert _key_problems(alone) == [
        (1, "baylor1987spectrall", "a collision suffix, but no 'baylor1987spectral'")
    ]
    pair = refs.parse(
        entry.format(key="baylor1987spectral") + "\n" + entry.format(key="baylor1987spectralb")
    )
    assert _key_problems(pair) == []


def test_an_organization_is_keyed_by_its_short_name():
    """`{Video Electronics Standards Association}` with `shortauthor = {VESA}` is
    `vesa2026dsc`: a thirty-six-letter author part is no use in a sentence or a methods
    section. The short name keeps its digits (`nc3rs2012refining`: NC3Rs, 2012,
    "Refining"), and a digit in an author part has no other source. Without a
    `shortauthor` the rule is unchanged."""
    for key, split in (
        ("nc3rs2012refining", ("nc3rs", "2012", "refining")),
        ("ab12020word", ("ab1", "2020", "word")),  # a short name ending in a digit
    ):
        parts = KEY.match(key)
        assert parts and parts.group("author", "year", "word") == split, key

    entry = (
        "@misc{{{key},\n  author = {{{{{author}}}}},\n{short}"
        "  title = {{{title}}},\n  year = {{{year}}},\n}}\n"
    )

    def problems(key, author, short, title, year):
        line = f"  shortauthor = {{{short}}},\n" if short else ""
        text = entry.format(key=key, author=author, short=line, title=title, year=year)
        return [problem for _, _, problem in _key_problems(refs.parse(text))]

    vesa = ("Video Electronics Standards Association", "VESA", "DSC: Display Stream", "2026")
    assert problems("vesa2026dsc", *vesa) == []
    assert problems("videoelectronicsstandardsassociation2026dsc", *vesa) == [
        "the rule gives 'vesa2026dsc'"
    ]
    nc3rs = ("NC3Rs", "NC3Rs", "Refining a procedure", "2012")
    assert problems("nc3rs2012refining", *nc3rs) == []
    assert problems("ncrs2012refining", *nc3rs) == ["the rule gives 'nc3rs2012refining'"]
    unnamed = (nc3rs[0], "", *nc3rs[2:])
    assert problems("ncrs2012refining", *unnamed) == []
    assert problems("nc3rs2012refining", *unnamed) == [
        "a digit in the author part, but no shortauthor"
    ]


#: What each entry type needs beyond `COMMON`; `a/b` is met by either field. A type not
#: listed here is refused; add it, with what it needs, when the library first holds one.
REQUIRED = {
    # A volume, or the issue's `number` for a journal that numbers only its issues (JoVE,
    # `carmel2010how`).
    "article": ("journal", "volume/number", "pages"),
    "incollection": ("booktitle", "publisher", "pages"),
    "inproceedings": ("booktitle", "pages"),
    "book": ("publisher",),
    "techreport": ("institution",),
    # A standard, a data set, a preprint or a maker's web page: who issued it, in place of
    # a journal, and like every entry a `doi` or `url`. Its author is often that body,
    # written whole in braces (`{CIE}`), and its key is made from its `shortauthor`.
    "misc": ("publisher/organization",),
}
COMMON = ("author", "title", "year", "note")
DOI = re.compile(r"^10\.\d{4,9}/\S+$")


def _field_problems(entries) -> list[tuple[str, str]]:
    """`(key, what is wrong)` for every entry missing what its type needs."""
    bad = []
    for entry in entries:
        if entry.type not in REQUIRED:
            bad.append((entry.key, f"type {entry.type!r} is not one of {sorted(REQUIRED)}"))
            continue
        needed = COMMON + REQUIRED[entry.type]
        missing = [
            need
            for need in needed
            if not any(entry.fields.get(name, "").strip() for name in need.split("/"))
        ]
        if missing:
            bad.append((entry.key, f"missing {missing}"))
        if not re.fullmatch(r"\d{4}", entry.fields.get("year", "")):
            bad.append((entry.key, "year is not four digits"))
        doi, url = entry.fields.get("doi", ""), entry.fields.get("url", "")
        if not doi and not url:
            bad.append((entry.key, "neither doi nor url"))
        if doi and not DOI.match(doi):
            bad.append((entry.key, f"doi {doi!r} is not a bare 10.xxxx/... DOI"))
    return bad


def test_every_entry_has_the_fields_its_type_needs():
    """Enough to find the paper again and to cite it in a methods section: author,
    title, year, where it appeared, and a DOI (bare, `10.xxxx/...`, so the checker can
    look it up) or a URL."""
    assert _field_problems(_entries()) == []


def test_a_document_that_is_not_a_paper_names_who_issued_it():
    """A standard or a web page (`@misc`) has no journal, so who issued it stands in its
    place, `publisher` or `organization`; with neither, or with no DOI or URL, it could
    not be found again. A type the table does not know is still refused."""
    entry = (
        "@{type}{{cie2006fundamental,\n  author = {{{{CIE}}}},\n"
        "  title = {{Fundamental chromaticity diagram}},\n  year = {{2006}},\n{extra}"
        "  note = {{checked 2026-10-08: abstract}},\n}}\n"
    )
    url = "  url = {https://cie.co.at/publications},\n"
    for extra in (
        "  publisher = {CIE},\n" + url,
        "  organization = {CIE},\n" + url,
    ):
        assert _field_problems(refs.parse(entry.format(type="misc", extra=extra))) == []
    nobody = refs.parse(entry.format(type="misc", extra=url))
    assert _field_problems(nobody) == [
        ("cie2006fundamental", "missing ['publisher/organization']")
    ]
    nowhere = refs.parse(entry.format(type="misc", extra="  publisher = {CIE},\n"))
    assert _field_problems(nowhere) == [("cie2006fundamental", "neither doi nor url")]
    (manual,) = _field_problems(
        refs.parse(entry.format(type="manual", extra="  publisher = {CIE},\n" + url))
    )
    assert manual[1].startswith("type 'manual' is not one of")


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
#: What the scan stops at: a bracket, a blank line (brackets, like code spans, do not
#: cross a paragraph), and an `@`.
TOKENS = re.compile(r"\[|\]|\n[ \t]*\n|@")
#: Pandoc's key: a letter, digit or `_`, then those and single internal punctuation
#: (pandoc.org/MANUAL.html, "Citation syntax", read 2026-10-08).
PANDOC_KEY = re.compile(r"[A-Za-z0-9_](?:[A-Za-z0-9_]|[:.#$%&+?<>~/-](?=[A-Za-z0-9_]))*")
#: Outside brackets only what looks like one of this library's keys (`KEY`, digits in a
#: short name included) is read, so a decorator (`@dataclass`) or a handle is not taken
#: for a citation.
LIBRARY_SHAPED = re.compile(r"[a-z0-9]+[0-9]{4}[a-z]+(?![A-Za-z0-9_])")


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
    """`(line, key)` for every key cited in `text`'s prose.

    Inside brackets, at any depth (`[@key]`, `[@key, p. 3]`, `[see @a; @b]`, `[-@key]`,
    `[@a, p. 3 [sic]]`), every Pandoc key whose `@` starts a word, so `[mail a@b.org]`
    is not one. Outside brackets, Pandoc's author-in-text form (`@key says`) and
    anything else shaped like this library's keys, `@` not inside a word: failing
    closed on a form the bracket scan would otherwise skip."""
    text = prose(text)
    found, depth = [], 0
    for token in TOKENS.finditer(text):
        if token[0] == "[":
            depth += 1
        elif token[0] == "]":
            depth = max(0, depth - 1)
        elif token[0] != "@":
            depth = 0
        else:
            at = token.start()
            start = at - 1 if depth and at and text[at - 1] == "-" else at
            before = text[start - 1] if start else " "
            if depth:
                starts_word = before.isspace() or before in "[;"
                key = PANDOC_KEY.match(text, at + 1) if starts_word else None
            else:
                inside_word = before.isalnum() or before in "_.@"
                key = None if inside_word else LIBRARY_SHAPED.match(text, at + 1)
            if key:
                found.append((text.count("\n", 0, at) + 1, key[0]))
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
            "A bracket in a bracket [@kappa1999ten, p. 3 [sic]] is read, and so is",
            "@lambda2000eleven says, in Pandoc's author-in-text form; not x@mu2001twelve.org,",
            "nor @dataclass; [@nu2002thirteen] is, and `[@xi2003fourteen]` in code is not.",
            "Any Pandoc key is read in brackets, after an inner one too: [see [sic] @Doe99].",
            "A short name's digit does not hide a bare key: @nc3rs2012refining says so.",
        ]
    )
    assert citations(text) == [
        (1, "alpha1990one"),
        (1, "beta1991two"),
        (1, "gamma1992three"),
        (10, "theta1997eight"),
        (13, "iota1998nine"),
        (14, "kappa1999ten"),
        (15, "lambda2000eleven"),
        (16, "nu2002thirteen"),
        (17, "Doe99"),
        (18, "nc3rs2012refining"),
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


def test_the_checker_compares_the_first_author_exactly():
    """A suffix match would let "Smith" pass for "Goldsmith", or the reverse; case and
    accents still fold, so "H{\\'a}rosi" is "Hárosi"."""
    for ours, theirs in (("Smith, A.", "Goldsmith"), ("Goldsmith, A.", "Smith")):
        record = {**SCHNAPF, "author": [{"family": theirs, "sequence": "first"}]}
        verdict, line = refs.check(_schnapf(author=ours), lambda doi: record)
        assert verdict == refs.MISMATCH and "first author" in line, (ours, theirs)
    accented = {**SCHNAPF, "author": [{"family": "Hárosi", "sequence": "first"}]}
    assert refs.check(_schnapf(author="H{\\'a}rosi, F. I."), lambda doi: accented)[0] == refs.OK


def test_the_checker_reports_what_it_could_not_reach():
    def offline(doi):
        raise urllib.error.URLError("no route to host")

    def unknown(doi):
        raise urllib.error.HTTPError(doi, 404, "Not Found", None, None)

    def cut_short(doi):
        raise http.client.IncompleteRead(b'{"message": {"tit')

    assert refs.check(_schnapf(), offline)[0] == refs.UNREACHABLE
    assert refs.check(_schnapf(), cut_short)[0] == refs.UNREACHABLE
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
    carries one header, a neutral tool identifier with no personal detail in it (the
    lab's rule from 2026-10-08), and a body that is not a Crossref work record is an
    error rather than an empty record that would then mismatch on everything."""
    asked = []

    def answer(body):
        def urlopen(request, timeout):
            asked.append((request.full_url, request.header_items(), timeout))
            return io.BytesIO(json.dumps(body).encode())

        return urlopen

    monkeypatch.setattr(refs.urllib.request, "urlopen", answer({"message": SCHNAPF}))
    assert refs.fetch("10.1016/S0042-6989(00)00021-3") == SCHNAPF
    url, headers, timeout = asked[-1]
    assert url == "https://api.crossref.org/works/10.1016/S0042-6989%2800%2900021-3"
    assert headers == [("User-agent", "wl-xcon-check-references/1.0")]
    assert timeout == refs.TIMEOUT_SECONDS

    monkeypatch.setattr(refs.urllib.request, "urlopen", answer({"status": "failed"}))
    with pytest.raises(ValueError):
        refs.fetch("10.1017/S0952523800001917")
