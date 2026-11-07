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
- A later build that bundles another CIE table (the CIE 1931 color-matching functions, XC-308)
  amends ADR-0004 again for its files, with their own rows; the 2° cone fundamentals came with
  the amendment below (2026-11-07).
- Every session that converts a cone color records the observer and the table's DOI
  (`config.json`'s `calibration.cones`, engine build A2).

## Amended 2026-11-07: the CIE's 2° table, which macaque luminance is computed on

The pop-out search (its spec §3.2 and §5 item 4; its plan's Task 2) holds a color set's lights
equal in **macaque luminance**, L + M at L:M 1 on the 2° cone fundamentals, as wl-style computes it
(the PI, 2026-11-07, asked in the UI: "wl-style's 2-degree set"; COL-37), so the package needs a 2°
table beside the CIE's 10° one.

- **What is bundled**: the CIE's own data set, **unmodified**, under the rule above for its files:
  `wl_xcon/cie/CIE_lms_cf_2deg.csv` and its metadata `CIE_lms_cf_2deg.csv_metadata.json`, "CIE 2006
  LMS cone fundamentals for 2° field size in terms of energy", DOI 10.25039/CIE.DS.tijidesg, from
  CIE 170-1:2006, Table 6.7, downloaded 2026-11-07 from
  https://files.cie.co.at/Publications-datasets/. 390 to 830 nm by 5 nm, the S cone NaN beyond
  615 nm. **Its license is verified**: CC BY-SA 4.0, its metadata's `rightsList` (read
  2026-11-07), as the 10° files' are. Its sha256,
  `f48160edf11c1a121aaaf41d4c3b7513385bfc9c60d726b88e735519f6d37b1f`, is its metadata's: pinned in
  `cones.CIE_FILES`, held by `tests/test_color_set.py`, and `cones.cie_file` refuses a changed
  file. Read as the 10° table is: NaN as zero, and between its 5 nm rows by straight lines, zero
  outside 390-830 nm, the `interpolationMethod: linear` and `extrapolationMethod: zero` its
  metadata declares. Nothing derived from it is written.
- **Why the CIE's and not the export it replaced the same day** (the PI, 2026-11-07, asked in the
  UI after the build's review, I7: "Swap before merge"): the build first bundled colour-science
  0.4.7's 1 nm Stockman-Sharpe 2° table, exported from the installed package, the table wl-style's
  isohue set was computed with; its own license, from CVRL, could not be verified (CVRL states no
  grant, Q3-B above), which this ADR's own reasoning rejected bundling for. The two are the same
  fundamentals [@stockman2000spectral], **computed 2026-11-07**: at the CIE table's 89 rows they
  agree within 1.4e-5 relative in L, M and S; on the tests' 5 nm panel spectra macaque luminance
  moves by under 1e-6 relative, and the isohue set's realized drive values are unchanged to 5
  decimals; on spectra resampled to 1 nm, narrow bands move by up to 0.31% (red +0.16%, green
  -0.12%, blue +0.31%), which is what the test against wl-style's own 1 nm numbers allows for.
- **What reads it**: `cones.macaque_luminance` alone, for color sets (`photometry.ColorSet`). No
  cone color converts through it; the lab observer stays the CIE's 10° set, and a task naming the
  2° fundamentals for its cone colors (XC-302) is still not built.
