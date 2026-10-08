#!/usr/bin/env python3
"""Check each entry of the reference library against Crossref's record of its DOI.

`docs/references/library.bib` is the lab's list of papers that justify its choices
(ADR-0010). An entry whose DOI names a different paper is the error a reader cannot
see: the citation renders, the key resolves, `tests/test_references.py` passes, and the
claim points at the wrong source. This fetches `https://api.crossref.org/works/<doi>`
for every entry that has a DOI and compares three things:

- **the year**, against Crossref's `issued` year or its `published-print` year (a
  paper online in one year and in a volume the next is cited by the volume's year;
  a 1988 paper digitized online in 2009 still has `issued` 1988);
- **the first author's family name**, exactly, after folding case and accents to
  lowercase ASCII letters (so "Smith" does not pass for "Goldsmith");
- **the title**, after folding case, accents, punctuation, LaTeX braces and
  Crossref's HTML tags, against Crossref's title (with its subtitle, when it has one).

It prints one line per entry -- `ok`, `MISMATCH` with what disagreed, `unreachable`
with why, or `no DOI` for an entry cited by URL -- and a count. **Exit 1 if any entry
mismatched; 2 if none did but some could not be checked; 0 only when every DOI was
fetched and agreed.** A run that reached nothing must not read as a run that found
nothing wrong.

**Never in CI.** It needs the network, and a test suite that fails when Crossref is
slow reports on Crossref. `tests/test_references.py` tests it against a canned
response instead. Run it after adding papers (docs/references/README.md):

    python3 tools/check_references.py
    python3 tools/check_references.py --library some/other.bib

The parser here is the one the test uses on the library, so the file the checker
reads and the file the test passes are read by one definition of the format.
"""

from __future__ import annotations

import argparse
import http.client
import json
import re
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parents[1]
LIBRARY = ROOT / "docs" / "references" / "library.bib"
CROSSREF = "https://api.crossref.org/works/"
#: A neutral tool identifier and nothing else: no person's name, address, account or
#: user name goes into a network request (the lab's rule from 2026-10-08).
USER_AGENT = "wl-xcon-check-references/1.0"
TIMEOUT_SECONDS = 30

# ---------------------------------------------------------------------------
# The library's format: the subset of BibTeX this repository writes
# ---------------------------------------------------------------------------

#: `@type{key,` alone on its line.
ENTRY_START = re.compile(r"^@(?P<type>[A-Za-z]+)\{(?P<key>[^,\s{}]+),[ \t]*$")
#: `<indent>field = {value},` on one line; the trailing comma is optional, as BibTeX's is.
FIELD = re.compile(r"^[ \t]+(?P<name>[a-z][a-z0-9_-]*)[ \t]*=[ \t]*\{(?P<value>.*)\},?[ \t]*$")
#: The one unbraced value allowed: `month` as one of BibTeX's twelve month macros, which
#: is how Zotero's stock BibTeX exporter writes it (`month = mar`; `BibTeX.js` at
#: zotero/translators 6d4490d, `writeField("month", months[date.month], true)`).
MONTH = re.compile(
    r"^[ \t]+(?P<name>month)[ \t]*=[ \t]*"
    r"(?P<value>jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec),?[ \t]*$"
)


@dataclass(frozen=True)
class Entry:
    type: str
    key: str
    fields: dict[str, str]
    line: int


class Malformed(ValueError):
    """A line the subset does not allow. The message starts with its line number."""


def _balanced(value: str) -> bool:
    depth = 0
    for char in value:
        depth += {"{": 1, "}": -1}.get(char, 0)
        if depth < 0:
            return False
    return depth == 0


def parse(text: str) -> list[Entry]:
    """Every entry in `text`, or `Malformed` naming the first line that is not the subset.

    The subset: blank lines between entries; an entry opens with `@type{key,` alone on
    its line, has one `field = {value},` per line (indented, braces balanced, each
    field once) and closes with `}` alone on its line. The one unbraced value is
    `month` as a month macro (`month = mar`), which Zotero's stock exporter writes
    (`MONTH`). Anything else -- a value quoted with `"`, any other bare value, a field
    running onto a second line, `@string`, `@comment` -- is refused rather than
    half-read, because a parser that skips what it does not understand passes an
    entry it never looked at.
    """
    entries: list[Entry] = []
    current: tuple[str, str, dict[str, str], int] | None = None
    for number, line in enumerate(text.splitlines(), start=1):
        if current is None:
            if not line.strip():
                continue
            start = ENTRY_START.match(line)
            if not start:
                raise Malformed(
                    f"line {number}: expected `@type{{key,` or a blank line, got {line!r}"
                )
            current = (start["type"].lower(), start["key"], {}, number)
            continue
        if line.strip() == "}":
            entries.append(Entry(*current))
            current = None
            continue
        field = FIELD.match(line) or MONTH.match(line)
        if not field:
            raise Malformed(f"line {number}: expected `field = {{value}},` or `}}`, got {line!r}")
        if not _balanced(field["value"]):
            raise Malformed(f"line {number}: unbalanced braces in {field['name']!r}")
        if field["name"] in current[2]:
            raise Malformed(f"line {number}: {field['name']!r} given twice in {current[1]!r}")
        current[2][field["name"]] = field["value"]
    if current is not None:
        raise Malformed(f"line {current[3]}: entry {current[1]!r} is never closed with `}}`")
    return entries


# ---------------------------------------------------------------------------
# Folding, so that agreement is not defeated by typography
# ---------------------------------------------------------------------------


def fold(text: str) -> str:
    """Lowercase ASCII words separated by single spaces: no accents, punctuation,
    LaTeX braces or commands, or HTML tags (Crossref titles carry `<i>`)."""
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\\[A-Za-z]+", " ", text)
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def letters(text: str) -> str:
    """`fold`, then letters only: how two spellings of one name are compared."""
    return re.sub(r"[^a-z]", "", fold(text))


def first_author(authors: str) -> str:
    """The first author's family name as written, particles included ("van Norren").

    BibTeX names are joined by ` and `; a family name is what precedes the first comma
    (`Schnapf, J. L.`) or, without one, the last word (`J. L. Schnapf`). A name wholly
    in braces is a corporate author (`{CIE}`) and is taken whole, `and` and all.
    """
    authors = authors.strip()
    if authors.startswith("{"):
        depth = 0
        for index, char in enumerate(authors):
            depth += {"{": 1, "}": -1}.get(char, 0)
            if depth == 0:
                return authors[1:index]
    first = re.split(r"\s+and\s+", authors, maxsplit=1)[0].strip()
    if "," in first:
        return first.split(",", 1)[0].strip()
    return first.split()[-1] if first.split() else ""


# ---------------------------------------------------------------------------
# Comparing an entry with Crossref's record
# ---------------------------------------------------------------------------


def _year(message: dict, field: str) -> int | None:
    try:
        return int(message[field]["date-parts"][0][0])
    except (KeyError, IndexError, TypeError, ValueError):
        return None


def compare(entry: Entry, message: dict) -> list[str]:
    """What disagrees between `entry` and Crossref's `message` for its DOI; empty if nothing."""
    problems: list[str] = []

    years = {y for y in (_year(message, "issued"), _year(message, "published-print")) if y}
    if not entry.fields.get("year", "").isdigit() or int(entry.fields["year"]) not in years:
        problems.append(
            f"year {entry.fields.get('year')!r}, Crossref "
            f"issued {_year(message, 'issued')} / print {_year(message, 'published-print')}"
        )

    authors = message.get("author") or []
    lead = next(
        (a for a in authors if a.get("sequence") == "first"), authors[0] if authors else None
    )
    ours = letters(first_author(entry.fields.get("author", "")))
    if lead is None:
        problems.append("Crossref lists no author")
    else:
        theirs = letters(lead.get("family") or lead.get("name") or "")
        if not ours or ours != theirs:
            problems.append(f"first author {ours!r}, Crossref {theirs!r}")

    titles = message.get("title") or [""]
    subtitles = message.get("subtitle") or []
    candidates = {fold(titles[0])} | {fold(f"{titles[0]} {s}") for s in subtitles}
    title = fold(entry.fields.get("title", ""))
    if title not in candidates:
        problems.append(f"title {title!r}, Crossref {fold(titles[0])!r}")
    return problems


def fetch(doi: str, timeout: float = TIMEOUT_SECONDS) -> dict:
    """Crossref's `message` for `doi`. Raises `OSError` (`URLError`, `HTTPError`,
    timeouts), `http.client.HTTPException` (a response cut short: `IncompleteRead`) or
    `ValueError` (a body that is not Crossref's JSON)."""
    url = CROSSREF + urllib.parse.quote(doi, safe="/")
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = json.load(response)
    if not isinstance(body, dict) or not isinstance(body.get("message"), dict):
        raise ValueError("the response is not a Crossref work record")
    return body["message"]


OK, MISMATCH, UNREACHABLE, NO_DOI = "ok", "MISMATCH", "unreachable", "no DOI"


def check(entry: Entry, fetcher: Callable[[str], dict] = fetch) -> tuple[str, str]:
    """`(verdict, line)` for one entry: one of `OK`, `MISMATCH`, `UNREACHABLE`, `NO_DOI`."""
    doi = entry.fields.get("doi")
    if not doi:
        return NO_DOI, f"{NO_DOI:<11} {entry.key} (cited by URL; not checked)"
    try:
        message = fetcher(doi)
    except urllib.error.HTTPError as error:
        why = f"HTTP {error.code}"
        if error.code == 404:
            why += " -- Crossref has no record of this DOI (registered elsewhere, or wrong)"
        return UNREACHABLE, f"{UNREACHABLE:<11} {entry.key} {doi}: {why}"
    except (OSError, http.client.HTTPException, ValueError) as error:
        return UNREACHABLE, f"{UNREACHABLE:<11} {entry.key} {doi}: {error}"
    problems = compare(entry, message)
    if problems:
        return MISMATCH, f"{MISMATCH:<11} {entry.key} {doi}: " + "; ".join(problems)
    return OK, f"{OK:<11} {entry.key}"


def main(argv: list[str] | None = None, fetcher: Callable[[str], dict] = fetch) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--library", type=Path, default=LIBRARY)
    args = parser.parse_args(argv)

    try:
        entries = parse(args.library.read_text(encoding="utf-8"))
    except Malformed as error:
        print(f"{args.library}: {error}")
        return 1
    counts = {OK: 0, MISMATCH: 0, UNREACHABLE: 0, NO_DOI: 0}
    for entry in entries:
        verdict, line = check(entry, fetcher)
        counts[verdict] += 1
        print(line, flush=True)
    print(
        f"\nof {len(entries)}: {counts[OK]} ok, {counts[MISMATCH]} mismatched, "
        f"{counts[UNREACHABLE]} unreachable, {counts[NO_DOI]} without a DOI"
    )
    if counts[MISMATCH]:
        return 1
    return 2 if counts[UNREACHABLE] else 0


if __name__ == "__main__":
    raise SystemExit(main())
