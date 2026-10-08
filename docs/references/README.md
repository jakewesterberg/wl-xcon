# The reference library

Every science-facing choice in wl-xcon names the papers it rests on, and the tasks in wl-xtasks cite
the same library (the PI, 2026-10-08; [ADR-0010](../design/decisions/ADR-0010-reference-library.md)).
It serves two uses: a reader can check a claim against its source where the choice is made, and a
methods section can be written from the same entries.

- [`library.bib`](library.bib) — one BibTeX entry per paper.
- [`decisions.md`](decisions.md) — one entry per decision: when and by whom, where it is recorded,
  and its basis, published or not.
- `tests/test_references.py` keeps the three consistent; `tools/check_references.py` checks each DOI
  against Crossref on demand.

**The rule** (CLAUDE.md): a choice that rests on the literature names its papers by key from
`library.bib` and has an entry in `decisions.md`; one that rests on an institutional rule, a PI's
decision or an engineering default says so there instead. A paper is never cited for a decision it
does not support, and a decision without a published basis is not given one.

**No PDFs here.** The repository is public under Apache-2.0: citations, DOIs and the lab's notes only.

## Citing

In a document's prose, Pandoc's bracketed forms: `[@schnapf1988spectral]`, with a locator
`[@brainard1996cone, p. 571]`, several at once `[@baylor1987spectral; @schnapf1988spectral]`, without
the author's name `[-@horwitz2015what]`. The test reads these at any depth of brackets
(`[@key, p. 3 [sic]]` included), and outside brackets anything shaped like a library key after an `@`
that does not sit inside a word — Pandoc's author-in-text form, `@schnapf1988spectral says` — so a bare
citation of a key the library lacks fails too. Other bare `@` words (`@dataclass`, a handle) are not
read, and nothing in a code span or a fenced block is, which is where examples of citing belong.

To render a document with its references:

```
pandoc --citeproc --bibliography docs/references/library.bib in.md -o out.docx
```

What Pandoc does with that (its manual, pandoc.org/MANUAL.html, read 2026-10-08): `--citeproc` replaces
the citations and adds a bibliography; without `--csl` the style is `chicago-author-date`; a `.bib`
file is read as BibLaTeX, and the extension `.bibtex` forces BibTeX. The command above was run on
`decisions.md` with pandoc 3.8 on 2026-10-08 and rendered every citation in it.

## Keys

`<firstauthor><year><firstword>`, lowercase ASCII letters and the year: the first author's family
name without particles or accents, and the title's first word that is not an article or a
preposition. Schnapf, Kraft, Nunn & Baylor 1988, "Spectral sensitivity of primate photoreceptors", is
`schnapf1988spectral`; Stockman & Sharpe 2000, "The spectral sensitivities of ...", is
`stockman2000spectral`. A second paper that would take the same key appends `b`, then `c`, and a
suffixed key stands only beside the key it collided with. The test derives each key from its entry and
fails one that disagrees, so a key never says 1987 for a 1988 paper.

## Adding a paper

1. **Open it.** The full text if you can reach it, otherwise the publisher's abstract page or PubMed.
   Never enter a paper from another paper's reference list, and never a claim from a summary of it.
   If no source can be reached, do not enter it: list the claim for the PI as unsourced.
2. **Enter it** in `library.bib`, in key order, in the format below: `author`, `title`, `year`, what
   the type needs (`journal`, `volume`, `pages` for an article; `booktitle`, `publisher`, `pages` for a
   chapter), a bare `doi` (`10.xxxx/...`) or else a `url`, and `note = {checked YYYY-MM-DD: full text
   ...}` or `{checked YYYY-MM-DD: abstract ...}` followed by what you opened (PubMed ID, PMC ID, the
   publisher's page, which table or page you read).
3. **Add or extend the decision** in `decisions.md`: each key with the claim it supports and where in
   the paper (page, table, figure, or "abstract").
4. **Run the test:** `python -m pytest -q tests/test_references.py`.
5. **Run the checker** (it needs the network, so it is not part of the suite):
   `python3 tools/check_references.py`. One line per entry — `ok`, `MISMATCH` with what disagreed
   (year, first author or title against Crossref's record of the DOI), `unreachable` with why, or
   `no DOI` — and a count. It exits 1 on any mismatch, 2 if nothing mismatched but something could not
   be checked, and 0 only when every DOI was fetched and agreed. A DOI Crossref does not know (HTTP 404)
   may be registered elsewhere, such as DataCite, or may be wrong: open it at `https://doi.org/` to see.

## The format the test reads

A subset of BibTeX, chosen so the test needs nothing beyond Python's standard library: blank lines
between entries; `@type{key,` alone on its line; one `field = {value},` per line, indented, braces
balanced, each field once; `}` alone on the line that closes the entry. The one unbraced value allowed
is `month` as one of BibTeX's twelve month macros (`month = mar`), which is how Zotero's stock exporter
writes it. A value in quotes, any other bare value (`month = march`, `year = 1988`), a field running
onto a second line, `@string` and `@comment` are refused with their line number. The entry types the
test knows are `article`, `incollection`, `inproceedings`, `book` and `techreport`; another is added to
the test with the fields it needs when the library first holds one.

## Zotero (optional)

The lab uses Zotero, so the library can live in a Zotero group as well as here (the PI's "1 and, as an
option, 3", ADR-0010), and **the lab's Zotero runs Better BibTeX** (the PI, 2026-10-08). The route is
therefore Better BibTeX's: import `library.bib` into the lab's group with the keys pinned, and export
back with the keys kept. **The file in this repository is the record**; a Zotero copy is a convenience,
and anything it changes comes back only through a commit that passes the test.

1. **The group.** File → New Library → "New Group…" in Zotero, or "Create a New Group" on zotero.org; a
   private group's page is seen only by its members and those invited (zotero.org/support/groups, read
   2026-10-08).
2. **Import, keys pinned.** File → "Import…" → "A file", choosing `library.bib`; Zotero imports BibTeX
   and BibLaTeX (zotero.org/support/kb/importing_standardized_formats, last updated 2018-11-04, read
   2026-10-08). That the items land in the library selected at the time, such as the group: UNVERIFIED.
   That Better BibTeX pins each entry's own key on import: UNVERIFIED — its documentation does not say;
   a Zotero forum thread does (forums.zotero.org/discussion/comment/363614, 2020-09-04, read
   2026-10-08: a participant writes that with Better BibTeX installed "it will pin the citation keys on
   import", and that a key shown as "Citation Key" in Extra is pinned and preserved). Check after
   importing that each item shows its key.
3. **Export, keys kept.** File → "Export Library…", or right-click a collection → "Export Collection…"
   (zotero.org/support/kb/exporting, last updated 2025-11-24, read 2026-10-08), choosing the format
   "Better BibTeX" (retorque.re/zotero-better-bibtex/installation/bundled-translators/, read
   2026-10-08). Better BibTeX's documentation says the standard exporters generate keys "at time of
   export" and that it "allows you to fix keys to any value of your choosing"
   (retorque.re/zotero-better-bibtex/citing/, read 2026-10-08; latest release v9.0.71, 2026-10-07).
   Zotero's exporting page warns that reimported items may have minor changes in a few fields, or with
   some formats lose fields. Export over `library.bib`, read the diff, and run the test before
   committing: a changed key fails it (the key rule, and every citation of the old key in
   `decisions.md`), and so does a `note` that lost its `checked` line.
4. **What Better BibTeX writes, unverified.** Its documentation, read 2026-10-08, does not say how it
   writes `month`, how it lays out fields, or what it does with a BibTeX `note` on import and export;
   its export preferences give `note` as an example of a field a user may choose to omit
   (retorque.re/zotero-better-bibtex/preferences/export/, read 2026-10-08). The test is the check:
   whatever the export changes shows in the diff, and whatever it writes outside the subset fails with
   its line.

**Without Better BibTeX** (Zotero's own BibTeX translator, `BibTeX.js` in github.com/zotero/translators
at commit 6d4490d, read 2026-10-08; not tried in a running Zotero): on import it reads an entry's key
but keeps it only as an internal identifier, and it turns a BibTeX `note` into a child note; on export
it takes the key from a `Citation Key: <key>` line in the item's Extra field, else from the item's
`citationKey` property (`BibTeX.js` line 1281, `if (item.citationKey) return item.citationKey`; whether
Zotero ever sets it: UNVERIFIED), else makes a new one of the form `author_title_year`, and it writes
child notes as `annote` when notes are exported (the default). Its layout is one field per line,
tab-indented, with a trailing comma, every value braced except `month`, which it writes as a bare month
macro (`month = mar`); the test reads that. A value with a line break in it, such as an abstract, is
refused, so delete `abstract` fields before committing. So without the plugin every key is typed into
Extra by hand, and every `note` restored after an export.