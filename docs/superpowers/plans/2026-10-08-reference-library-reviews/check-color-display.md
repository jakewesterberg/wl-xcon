> Working file of 2026-10-08, committed as the record of the reference library's backfill and checks (plan: `docs/superpowers/plans/2026-10-08-reference-library.md`). Line numbers, commits and paths are as they were then; citations here are quoted as found, some of them since corrected or removed.

# Independent check: color and display (COL-01..31, "COL-15, its citation", DISP-01..31), at 5359fee — the checker's report, saved by the controller

Full texts: Abu Haila 2025, Bridges 2020, Dimigen 2026, Elze 2010, Saunders 2014, Wang 2011, Conway 2014, He 2021, Horwitz 2015, Li 2022, Pelli & Bex 2013, Spitschan 2018, Stockman & Rider 2023, Zhou 2013, Ressmeyer 2026 (PMC); Brainard, Pelli & Robson 2002 (chapter PDF pp. 172–188); Brainard 1996 (author's PDF); Stockman & Sharpe 2000; the W3C sRGB page incl. equation images; T.81 (w3.org copy); both ASUS pages; VESA DSC; IEC description page. The rest abstract only.

## Wrong
1. **COL-01, sRGB breakpoint**: the W3C page's Eq. 1.2a condition image (`srgb10`) reads R,G,B_sRGB ≤ 0.00304, not 0.0031308; the page notes "During standardization, a small numerical error caused by rounding error was corrected." 0.0031308 is IEC 61966-2-1's corrected value (not opened). Correct: "≤ 0.00304 in the 1996 draft; 0.0031308 in IEC 61966-2-1 (not opened: UNVERIFIED)".
2. **COL-01, gamma range**: "fitted γ 2.04-2.30" (Abu Haila 2025, Table 3) — Table 3: LG R 2.04, G 2.07, B 1.98, grayscale 2.01. Correct: "γ 1.98–2.30 across channels (grayscale 2.01–2.29)".
3. **COL-03 caveat (He et al. 2021)**: "against this observer" (CIE 10° V_F,10) — He et al. used the Stockman–Sharpe 2° observer ("for their mean 2° observer"; macular density "0.35 at 460 nm for a 2° observer"; "we emphasized results based upon the central 2°"). Numbers correct (Introduction: 99.3°–146.2°, "−6.1 and −0.7"). Say "against the Stockman–Sharpe 2° observer".
4. **COL-09 and COL-24, equation locators**: Pelli & Bex 2013 "Introduction, Eqs. 1-2"/"Eqs. 1-3" — in PMC3744596 the Weber, Michelson, RMS definitions are inline, unnumbered, in the unheaded opening paragraph; the only numbered Eq. 1 is contrast energy (E = c²rms·A·T = k). Locator: "opening paragraph".
5. **COL-20**: "engineering choice with no paper behind" measuring at the eye point — Brainard et al. 2002, p. 173: "the light sensor should generally be in approximately the same position as the observer's eye." Automation was the PI's ruling ("Automated, from the console", notes §9 Batch 1), not engineering.

## Overstated
1. **COL-31**: "contradicts" — Abu Haila fitted the output after DisplayCAL calibration (γ 2.2) and say "the encoded gamma behavior … is determined by the ICC calibration profile, besides the behavior of the display hardware" — nothing about the native transfer. Say "does not support it".
2. **COL-04 and COL-08 (Brainard 1996, p. 572)**: "There is no guarantee … within the gamut" is a parenthetical about a worked example's numbers — supports "may be out of gamut", not clipping or isoluminance; COL-04's "Clipping:" label and pitfalls P19's inline [@brainard1996cone] on "a clipped colour has neither the requested chromaticity nor … luminance — so an isoluminant pair stops being isoluminant" attribute arithmetic to Brainard. Re-label; move or drop the P19 inline.
3. **COL-15 and COL-16 caveats**: "The macaque lens is about 60% of the human density [@horwitz2015what]" — Horwitz: "the optical density of the macaque lens would have to be ~60%" to account for one macaque's data under the lens interpretation. COL-16's Basis words it right; align COL-15's.
4. **COL-03 caveat (Conway 2014)**: the quote drops its condition: "If human and monkey cone fundamentals are indeed substantially different, …" (section "MT").
5. **COL-22 (Stokes 1996, Part 3)**: "the standard's default" — the source is a proposal ("We propose that all page elements defined in the style sheets be assumed to be in the sRGB color space unless embedded ICC profiles indicate otherwise") about CSS page elements; the IEC text not opened.
6. **DISP-02 (Cooper 2013)**: "only after" — the abstract has no "only".
7. **COL-11 caveat (Zhou 2013)**: "small at a few percent" extrapolates (Zhou tested 10×–1000× attenuations, 3 observers).
8. **Beyond an abstract-only source**: DISP-09 Reid 1997 "one element per displayed frame" (not in the abstract; cat); DISP-17 Merigan & Katz "two M. nemestrina" (abstract: "two macaques"); COL-16 Snodderly 1984 "across monkey retinas" (abstract: "primate retinas").
9. **COL-14 (Tyler 1997)**: "below 0.2%" — the PubMed abstract reads "from 1.5% to > 0.2%" (probably a typo; Brill refused the fetch). Quote as the abstract reads, flagged.
10. Minor: COL-15 (Baylor 1987) "after correcting for pre-retinal absorption" belongs to the π-mechanism sentence; DISP-01 (Fung 2016) "has N times" → "should be N times"; DISP-28 (Dimigen) "human observers" was one observer, an author; COL-26 and COL-28 carry unsourced generalizations ("The convention is common in methods sections"; "values vary over orders of magnitude") — mark them as the lab's.

## Forced
- **DISP-10**: Bridges et al. say software can detect dropped frames ("some timing errors (such as a dropped frame) can be detected by the software packages themselves"); their call for hardware tests concerns monitor-side delays. Bridges does not support "dropped frames are detected in hardware"; only Plant 2004's general case for validation does. Make that explicit.

## Bibliographic
No metadata errors (52 DOIs fetched directly; HTTP 429 on 11 via the checker). Benign: sharpe2005luminous (Crossref page "3"; PubMed 948–968 as the bib); allison2018perspectives (Crossref "1-23"; 053035 is the article number); wang2011lcd (Crossref lists only Wang; PMC confirms Wang & Nikolić). Unexplained checker flags, all false positives: cie2006fundamental, cie2015fundamental, cie2018colorimetry (Crossref: no issued date, author "CIE TC 1-36/1-35/1-85", title prefixed with the standard number) — note them; dobkins2000comparison, fung2016tandem — **`fold()` in tools/check_references.py ASCII-folds Unicode dashes away** ("red–green" → "redgreen"; "Light‐Emitting" → "lightemitting") — a checker bug (also explains hoffman2008, fraser2009, christie2015, ferrea2025, walton2019). conway2014color is online 2013-10-08, print 2014-03 — its note should say so.

## Link/inline
- All 196 Where links resolve; PI quotes match the notes; no sentence reworded.
- COL-11: "left half worse on every consumer display" is in Abu Haila's Discussion, not "Results … Fig. 8".
- COL-28: visual_search.py has only `fix_luminance` (its targets are DKL colors) and calibration.py only `target_luminance` — correct the entry.
- Stray citations after the full stop in engine spec §4.3 and §10 item 2.
- S0 §5.1: [@abuhaila2025recent; @dimigen2026advantages; @ito2013evaluation; @cooper2013assessment] sit on "tandem QD-OLED at 4K/240" — none tested a tandem QD-OLED monitor (DISP-01 says none was found); [@fung2016tandem] there sits on S0's ABL-headroom inference — move each to the clause it supports.

## Counts
63 entries; 60 library entries; ~215 claims. Wrong 5, Overstated 10 items (~17 instances), Forced 1, Bibliographic 0 (5 checker false positives), Link/inline 4. 64 cited instances (36 keys) checked against abstracts only.
