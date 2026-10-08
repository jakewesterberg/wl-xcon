# ADR-0010: The reference library is BibTeX in wl-xcon; a Zotero group is optional

- Status: Accepted 2026-10-08
- Date: 2026-10-08
- Deciders: PI

## Context

On 2026-10-08, answering build A2's question on the macaque observer, the PI asked: "record
references that justify choices. This should be done throughout this repo and for desigining
experiments. The wl-xcon and xtasks set should have a library of papers that justify choices and can
be used for writing up reports" (the engine brainstorm notes, "The morning after (asked 2026-10-08)",
on branch `engine-b`).

No file held papers before this. Citations sat inline in specs and research notes, each written
where it was needed, and nothing in the suite checked one. The cost showed the same week: engine spec
§7.9 attributed "virtually identical" to Baylor, Nunn & Schnapf (1987) when the sentence is Schnapf,
Kraft, Nunn & Baylor's (1988). The A2 research note found and corrected it
(`docs/research/2026-10-08-engine-a2-color-research.md` §0), and the independent check of that note
confirmed the correction.

The library has two uses, and they pull in one direction: a reader checking a choice needs the claim
next to the paper and where in the paper it is; someone writing a methods section needs the same
papers in a form a citation processor reads.

**The three questions put to the PI, and his answers** (the same notes):

1. **Where it lives** — offered: in wl-xcon, wl-xtasks citing it (recommended); in wl-xtasks; its own
   repository; in wl-works. Answer: "In wl-xcon, xtasks cites it".
2. **Its form** — offered: BibTeX and short notes (recommended); CSL-JSON; a Zotero group as the
   source. Answer: "can we manage 1 and, as an option, 3? We use Zotero now so it would be convenient,
   but bibtex as a fallback is nice to have".
3. **How far back** — offered: the engine first, then the rest as it is touched (recommended); a full
   backfill now. Answer: "Full backfill now".

To the design then put to him in chat (the files and checks below), "Yes, and run build B alongside".

**What was verified about the tools, 2026-10-08** (sources in `docs/references/README.md`): Pandoc
reads a `.bib` bibliography as BibLaTeX and renders `[@key]` citations with `--citeproc` (its manual;
and pandoc 3.8, run on `docs/references/decisions.md`, rendered every citation); Zotero imports BibTeX
and BibLaTeX (its documentation); Zotero's own BibTeX translator does not store an imported entry's
key, exports the key from a `Citation Key: <key>` line in the item's Extra field, else from the item's
`citationKey` property, else makes a new one, writes `month` as a bare macro, and turns a BibTeX `note`
into a child note that it exports as `annote` (its source, not tried in a running Zotero); Better
BibTeX lets keys be fixed per item (its documentation), and that it pins a file's keys on import is
said in a Zotero forum thread, not its documentation, so UNVERIFIED. After these answers the PI added
that **the lab's Zotero runs Better BibTeX** (2026-10-08).

## Decision

**The library is `docs/references/` in wl-xcon, in BibTeX, and wl-xtasks cites it by key.**

- `library.bib` holds one entry per paper, in a subset of BibTeX that a standard-library parser reads
  (`tools/check_references.py`'s `parse`). Each entry carries a DOI (or a URL when there is none) and a
  `note` saying when it was checked and whether against the full text or the abstract.
- `decisions.md` holds one entry per science-facing decision: **Decided**, **Where**, **Basis**. A
  basis that is not published — an institutional rule, the PI's decision, an engineering default — is
  written as such, never given a paper.
- Documents cite with Pandoc's `[@key]`.
- `tests/test_references.py` checks that the library parses, keys follow the key rule and are unique,
  entries have their fields and a dated `note`, every `[@key]` in `docs/**/*.md` prose resolves, every
  link in `decisions.md` names a file that exists, and every decision has its three lines.
- `tools/check_references.py` compares each DOI with Crossref's record (year, first author, title),
  run by hand when papers are added; never in CI, since it needs the network.
- **A Zotero group is optional**: the lab may import `library.bib` into one and export back to it
  through Better BibTeX, which its Zotero runs, keys kept on the way out (pinned on the way in:
  UNVERIFIED, see the README); the
  file in this repository stays the record. An export comes back only through a commit that passes the
  test.
- No PDFs in the repository, which is public under Apache-2.0.
- **No new dependency.** The test and the checker use Python's standard library; Pandoc and Zotero are
  programs a person runs, not imports of this package, so ADR-0004's inventory does not change.

## Alternatives considered

The PI's answers record his choices; where a reason below is not his quoted words, it is this record's.

- **The library in wl-xtasks.** Most of the science-facing choices so far are wl-xcon's own — the
  engine's color model and observer, the display's calibration — and this repository's tests could
  not check citations against a file in another repository.
- **Its own repository.** A third repository to keep in step, and the same problem: no test here could
  resolve a key there.
- **In wl-works.** The lab's ELN; this repository's tests cannot read it, and a methods section written
  from a repository's documents would have its sources somewhere else.
- **CSL-JSON.** Pandoc reads it equally well, but people rarely write it by hand.
- **A Zotero group as the source.** Offered as the third form; the PI took it as an option beside
  BibTeX rather than instead of it ("1 and, as an option, 3"). As the source it would put the record
  where this repository's tests cannot see it, and a stock Zotero round trip changes keys and moves
  notes (the context above).
- **The engine first, then the rest as touched.** Recommended, and declined: the PI chose a full
  backfill now.

## Consequences

- CLAUDE.md gains the rule: a choice resting on the literature names its papers from `library.bib` and
  has an entry in `decisions.md`; one resting on a rule, a PI's decision or a default says so there.
- The backfill of every science-facing decision already in the specs and docs runs as the rest of
  `docs/superpowers/plans/2026-10-08-reference-library.md`, with an independent check of every claim
  against its source.
- A key cited in `docs/` and missing from the library, an entry without a dated note, or a decision
  without its basis fails the suite. A DOI that names a different paper does not fail the suite; it
  fails `tools/check_references.py`, which someone has to run.
- **Not settled here:** how wl-xtasks' own documents resolve a key against this file — a path to a
  wl-xcon checkout, a copy, or a check in wl-xtasks — is for wl-xtasks to decide when it first cites
  one.
