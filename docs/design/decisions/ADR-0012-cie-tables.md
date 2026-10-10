# ADR-0012: The CIE's cone fundamental tables ship with the package, unmodified, under CC BY-SA 4.0

- Status: Accepted 2026-10-08, by the PI in his answer to engine A2's Q3 ("Bundle the CIE's files (Recommended)")
- Date: 2026-10-10
- Deciders: PI

## Context

Engine build A2 converts every cone color (a `DKL` color, a `ConeContrast`) through one lab-wide
observer, the CIE 2006 10° cone fundamentals (engine spec §7.9; the PI, 2026-10-07 and 2026-10-08;
`docs/references/decisions.md` COL-15, COL-16), so the package needs their table. A2's research
(`docs/research/2026-10-08-engine-a2-color-research.md` §1) found four sources, and the question
was put to the PI as its Q3 (2026-10-08, through the question box):

- **A (recommended): bundle the CIE's own CSVs** as separate files, licensed CC BY-SA 4.0 with
  attribution, recording the sha256 the CIE's metadata gives (the data set pages' MD5 is stale for
  the 10° table).
- B: bundle cvrl.org's tables after asking their author: cvrl.org states no license grant.
- C: generate them from Stockman and Rider's (2023) formulae: they reproduce the CIE's tables
  "with little error", not exactly, and their program's license was not found.
- D: download them on first use, with a checksum: an offline rig needs a cache anyway.

**Verified 2026-10-09**: each data set's metadata JSON (files.cie.co.at) gives
`"rightsIdentifier": "CC BY-SA 4.0"` and the file's sha256; the data set pages show the CIE's
recommended citation and the footer "Copyright © 2026 CIE". CC BY-SA 4.0's Section 3(a)(1)
(creativecommons.org/licenses/by-sa/4.0/legalcode.en, read 2026-10-09) asks a sharer to keep the
creator's identification and notices, link the material and the license, and say whether it was
modified; Section 3(b) puts adapted material under the same license. **ADR-0004's amendment of
2026-09-26 says any copyleft asset other than an unmodified OFL font reopens it**, and CC BY-SA is
share-alike: this ADR is that reopening.

**His answer:** "Bundle the CIE's files (Recommended)": A. In answering he accepted the choice, so
this ADR is written as Accepted.

## Decision

**The CIE's files ship unmodified in `wl_xcon/cie/`**, each beside its own metadata JSON, with a
`NOTICE.md` giving the attribution Section 3(a)(1) asks for, as package data
(`pyproject.toml`): `CIE_lms_cf_10deg.csv` (DOI 10.25039/CIE.DS.nxsqeri8), the observer every cone
color converts through, and `CIE_cfb_stv_10deg.csv` (DOI 10.25039/CIE.DS.dm6qiig7), the XYZ_F,10
functions a test holds the CIE's LMS-to-XYZ_F,10 matrix to and nothing reads at runtime.
`wl_xcon/cones.py` **reads a file only when its sha256 is the CIE's**, pinned in `CIE_FILES` and held
to the metadata by a test. **Nothing derived from them is written**: values between the CIE's
5 nm points are interpolated in memory, as its metadata declares. The code stays Apache-2.0; the
files keep CC BY-SA 4.0.

## Alternatives considered

- **cvrl.org's tables** (Q3-B): no license grant is stated (research note §1.3), and asking was not
  needed with the CIE's own files available under a stated one.
- **Stockman and Rider's formulae** (Q3-C): not the CIE's numbers, and their program's license was
  not found; they remain the way to build a non-standard observer (XC-301).
- **Download on first use** (Q3-D): an offline rig needs the files on disk regardless, and a
  download adds a network path to a session's start.

## Consequences

- ADR-0004 is amended for these two files only: each ships unmodified as package data, with its
  metadata, the `NOTICE.md` and an inventory row; any other CC BY-SA table, a modified one, or any
  other copyleft asset, still reopens it.
- **A changed table is adapted material** under Section 3(b) and would carry the license if shared,
  so the build never resamples, renormalizes or zero-fills a file on disk. Whether an unmodified
  CSV beside Apache-2.0 code is "separately licensed material" is the research note's reading
  (§1.3), not legal advice: UNVERIFIED, and the PI's to settle if it ever matters.
- A later build that bundles another CIE table (the 2° set, XC-302; the CIE
  1931 color-matching functions, XC-308) amends ADR-0004 again for
  its files, with their own rows.
- Every session that converts a cone color records the observer and the table's DOI
  (`config.json`'s `calibration.cones`, engine build A2).
