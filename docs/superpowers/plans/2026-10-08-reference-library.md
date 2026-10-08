# The reference library — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

> **Asked for by the PI on 2026-10-08:** "record references that justify choices. This should be done
> throughout this repo and for designing experiments. The wl-xcon and xtasks set should have a library
> of papers that justify choices and can be used for writing up reports." His answers, through the
> question box the same morning: the library lives **in wl-xcon, and wl-xtasks cites it**; **BibTeX in
> the repository, with a Zotero group as an option** ("We use Zotero now so it would be convenient, but
> bibtex as a fallback is nice to have"); a **full backfill now** of every science-facing decision
> already in the specs and docs; and **engine build B is built alongside** on its own branch. The design
> below was put to him in chat and approved.

**Goal:** Every science-facing choice in wl-xcon names the papers that justify it, from one library a
methods section can be written from.

**Architecture:** `docs/references/library.bib` holds one BibTeX entry per paper; `docs/references/decisions.md`
holds one entry per decision (what, where, which keys, the claim each supports and where in the paper);
documents cite with Pandoc's `[@key]`; `tests/test_references.py` keeps all three consistent with no new
dependency; `tools/check_references.py` checks each DOI against Crossref on demand (never in CI). ADR-0010
records the format; CLAUDE.md gains the rule.

**Tech stack:** Python 3.11-3.13 standard library (`re`, `urllib`, `json`); pytest. **No new dependency.**

**Branch:** `references`, from `main` once `main` carries the overnight merge (`d697f34`), in its own
worktree (`.claude/worktrees/references`), so build B's implementers in the other worktree never share a
tree with this plan's.

## Global constraints

- **No fabrication** (CLAUDE.md): every entry is a paper someone on this plan opened — full text, or the
  publisher's abstract page, said which — with its DOI (or a stable URL when none exists) and an as-of
  date. A claim a source could not be reached for is not entered; it is listed for the PI as unsourced.
- **No PDFs** in the repository (it is public, Apache-2.0); citations, DOIs and the lab's notes only.
- Keys: `<firstauthor><year><firstword>`, lowercase ASCII, the first author's family name without
  particles or accents, the title's first word that is not an article or preposition; a collision adds
  `b`, `c`. Example: Schnapf, Kraft, Nunn & Baylor 1988, "Spectral sensitivity of primate photoreceptors"
  → `schnapf1988spectral`.
- Entry fields: `author`, `title`, `year`, `journal`/`booktitle`/`publisher` as the type needs, `volume`,
  `pages`, `doi` or `url`, and `note = {checked YYYY-MM-DD: full text | abstract}`.
- Backlog IDs are assigned by the controller (build B runs alongside): an implementer does not add a
  backlog line; it reports what it defers.
- US English; docs stay in sync (architecture.md's document list names the library).

## Review focus

1. A key cited in a document that is not in the library (the test must catch it).
2. An entry whose DOI resolves to a different paper (the Crossref check must catch it; the backfill's
   independent check runs it on every entry).
3. A decision attributed to a paper that does not support it (the independent check reads the claim
   against the source for every decision, not a sample).
4. A decision with no published basis (an institutional rule, a PI's preference, an engineering default)
   forced into a citation: these are recorded as such — "basis: PI, 2026-10-07" or "basis: institutional
   rule" — never given a paper they do not rest on.
5. `[@key]` inside code spans or example text being read as a citation (the test reads only prose).

---

### Task 1: The library's skeleton, its test, its checker, ADR-0010 and the rule

**Files:** create `docs/references/README.md`, `docs/references/library.bib`, `docs/references/decisions.md`,
`tests/test_references.py`, `tools/check_references.py`, `docs/design/decisions/ADR-0010-reference-library.md`;
modify `CLAUDE.md` (one rule), `docs/design/architecture.md` (the document list), `tools/mutation_gate.py`
only if the gate requires every `tools/` module or test to be listed (read it first).

**Behavior:**
1. `library.bib` starts with the entries already checked on 2026-10-08 for the engine's color work, each
   re-opened and checked by the implementer before entry: Schnapf, Kraft, Nunn & Baylor 1988; Baylor,
   Nunn & Schnapf 1987; Brainard 1996 (Cone contrast and opponent modulation color spaces); Stockman &
   Sharpe 2000; Derrington, Krauskopf & Lennie 1984; Horwitz 2015 (Neuroscience 296:110). Sources: the
   research note `docs/research/2026-10-08-engine-a2-color-research.md` and its fact-check.
2. `decisions.md`: a short header (what an entry is; that a decision without a published basis says what
   it rests on instead), then sections by area with one entry each in this form:

   ```markdown
   ### Cone fundamentals: the CIE 10° observer, unadjusted for macaques
   - **Decided:** 2026-10-08, the PI (A2 Q4), after a literature search.
   - **Where:** [engine spec §7.9](../superpowers/specs/2026-10-07-engine-design.md#79-...), [A2 research note §5](../research/2026-10-08-engine-a2-color-research.md#5-...)
   - **Basis:** [@stockman2000spectral] — the 10° fundamentals (Table 2); [@horwitz2015...] — macaque lens about 60% of human (p. …), the adjustment declined as smaller than between-animal spread.
   ```
   Task 1 writes the color entries the six seed papers support; the backfill writes the rest.
3. `README.md`: what the library is for (justifying choices; writing methods sections), the key rule, how
   to cite (`[@key]` in prose; Pandoc `--citeproc --bibliography docs/references/library.bib`), how to
   add a paper (open it, enter it, run the test and `tools/check_references.py`), and the Zotero route:
   import `library.bib` into the lab's Zotero group, and export from Zotero back to `library.bib` keeping
   the keys. Each statement about Zotero or Pandoc behavior is verified against their documentation (cite
   the page and as-of date in the README) or marked UNVERIFIED; in particular whether stable keys need
   the Better BibTeX plugin.
4. `tests/test_references.py` (stdlib only): parses `library.bib` (the subset this plan writes: `@type{key,`
   then `field = {value},` lines; a malformed entry fails the test with its line); keys unique and
   well-formed; required fields present; `note` carries a `checked YYYY-MM-DD` date; every `[@key]` in
   `docs/**/*.md` prose (outside code fences and inline code) resolves; every `decisions.md` link's file
   exists (anchors as `test_backlog` treats them); every `decisions.md` entry has **Decided**, **Where**
   and **Basis**. Prove each check can fail.
5. `tools/check_references.py`: for each entry with a DOI, fetch `https://api.crossref.org/works/<doi>`
   and compare the year and the first author's family name, and the title after case and punctuation
   folding; print one line per entry (`ok` / `MISMATCH …` / `unreachable`); exit 1 on any mismatch. Never
   run in CI (it needs the network); its own tests use a canned Crossref response.
6. ADR-0010 "The reference library is BibTeX in wl-xcon; a Zotero group is optional", Accepted, by the
   PI on 2026-10-08 (his three answers), with the options he was offered.
7. CLAUDE.md, under Rules, after "No fabrication": **"Cite the library for science-facing choices.** A
   choice that rests on the literature names its papers by key from `docs/references/library.bib` and has
   an entry in `docs/references/decisions.md`; one that rests on an institutional rule, a PI's decision
   or an engineering default says so there instead. wl-xtasks cites the same library."

### Task 2: The inventory of science-facing decisions

Read-only research, no repository change. Produce `.superpowers/references/inventory.md`: every
science-facing decision stated in `docs/` (specs S0-S13 and their amendments, the engine spec and its
brainstorm notes, the research notes, `pitfalls.md`, the ADRs, `architecture.md`, the roadmap, the reference
tasks under `tasks/`) — one row each: the decision in a line, where it is stated (file and section), the
area (color and photometry; display and timing; stereo geometry and vergence; eye tracking and
calibration; reward and fluid; welfare limits; task design and psychophysics; recording and events;
other), any citation it already carries, and whether its basis looks published, institutional, a PI's
decision or an engineering default. Engineering choices with no scientific content (a port number, a
file layout) are out of scope; when in doubt, include the row and say why.

### Task 3: The backfill, by area

One research agent per area of the inventory (the controller dispatches them in parallel; none edits
the repository). Each returns, for its rows: BibTeX entries in the plan's form (each paper opened, its
DOI checked, its note dated), `decisions.md` entries in the Task 1 form, and a list of rows it could not
source, with what it searched. Then one implementer integrates them into the repository: dedupes keys,
adds the entries, adds `[@key]` at each decision's statement in its document (a citation appended to the
sentence that states the decision; no rewording), runs the test, and commits per area.

### Task 4: The independent check

A fresh agent that did not write any entry runs `tools/check_references.py` on every entry and reads,
for every `decisions.md` entry, the claim against the cited source (full text or abstract, said which).
It reports mismatches, unsupported claims and forced citations (Review focus 4). One fix pass follows.
The list of decisions left unsourced goes to the PI, in plain terms, as the closing summary — with which
of them want a citation and which rest on something else.

### Task 5: Record it

CHECKPOINT entry; `architecture.md`'s document list; the backlog lines the controller assigns for anything
deferred; the wl-xtasks convention line proposed to the PI (a change in another repository: asked, not
pushed).
