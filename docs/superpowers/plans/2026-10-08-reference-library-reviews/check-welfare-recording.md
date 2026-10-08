> Working file of 2026-10-08, committed as the record of the reference library's backfill and checks (plan: `docs/superpowers/plans/2026-10-08-reference-library.md`). Line numbers, commits and paths are as they were then; citations here are quoted as found, some of them since corrected or removed.

# Independent check: welfare and recording (REW-01..16, WEL-01..25, REC-01..23, OTH-01..04), at 5359fee — the checker's report, saved by the controller

No fabricated citation; no forced citation. Both welfare rules recorded as decided (WEL-01: one limit, cage to cage, eight hours, the institution's, corrected from twelve 2026-10-01, per excursion 2026-09-20, chair time recorded and bounding nothing, no session-length or trial maximum; REW-01: fluid a floor, not a ceiling).

## Welfare residues
- **Stale sentence in S8's head paragraph** (REW-01's first Where link): it still ends "Chair time and trial count are genuine ceilings and are unaffected." — contradicting WEL-01, S8 §4 and S8 §8 item 7 (`max_trials` removed 2026-09-19); the only remaining instance in docs/. Give it a dated correction like the twelve-hour mentions.
- **WEL-01's provenance**: Basis says "(the project authorization, not public…)"; Caveat says the hour figure is one "which the ethics committee sets per project (decree Art. 23 §1)". Art. 23 §1 only says the Ethics Committee decides whether to authorize a project within forty working days; no document names the project authorization as the source. Correct: "institutional rule; the documents name no source document; that it is set in the project authorization is our reading of the decree."

## Wrong
1. **OTH-04**: "OpenIrisDPI's own license was not stated in the paper text read" — Ressmeyer et al. 2026 (PMC12900282), last paragraph of the Introduction: "The source code for the plugin is free and openly available under the GPLv3 license (https://github.com/ryan-ressmeyer/OpenIrisDPI)." Only the AGPL part (OpenIris itself) rests on the spike.
2. **REW-07**: NRC 2003 p. 59 — equipment malfunctions and programming errors are variables "that might hinder training or disrupt performance", to be ruled out before tightening restriction, not "named among the causes" of unplanned restriction ("nonprogrammed water restriction" is a separate item). The daily-monitoring claim is right ("careful monitoring of animals under food or fluid control is necessary every day to avoid additional nonprogrammed restriction").
3. **REW-09**: Seo & Lee 2009 — "most trials paid only a token" is wrong: gain 50.8%, neutral 31.1%, loss 18.2%, juice on average every 9.5 trials (Results, "Effects of tokens on choices"; Fig. 1b). Correct: about half the trials gained a token, the rest nothing or a loss; juice only at the sixth token.
4. **WEL-20**: ICNIRP p. 81 — pain "usually induce[s] an avoidance response … that prevent[s] a burn, with the exception of very high irradiances that rapidly heat the skin": very high irradiance is the exception. Correct: ICNIRP relies on avoidance at painfully warm levels (p. 81; p. 88 for skin past 10 s) and says it fails at very high irradiance. S0's conclusion unaffected. (Lead: ICNIRP p. 81 cites Randolph & Stuck 1976 on the rhesus cornea — not entered.)
5. **REC-05**: Karsh's sync page says an event is "no more than one period away from a nearest … sync wave edge" and the mapped-time error is bounded by "sync_period * rate_error/rate" (0.1 ms in its example) — not "bounds any alignment error to one period".
6. **REW-08 caveat**: NC3Rs says "Supplements should be the maximum amount consistent with reliable performance and should be regularly reviewed." Quote it correctly (it strengthens the caveat).
7. **Locations (minor)**: Hwang 2019 (PMC6743332, §3.4, 7 paragraphs) — loopback/event-marker ¶3 not ¶1 (REC-01); −0.05 ms, 39.92 ms, 40.98 ms ¶4–5 not ¶2–3 (REC-13); 24.78 ms LCD lag ¶6–7 not ¶4–5 (REC-03). Bridges 2020 "Lab-based package results": ~4 ms lag and <1 ms audio in ¶2, not ¶1 (REC-03, REC-13). WEL-14 Chang 2016 "in macaques … (abstract)" — the species is from PubMed's MeSH (Macaca), say so (as REC-18 does for Legatt). REW-05: NRC p. 56 asks daily records only at a new protocol's start; ongoing daily records p. 60.

## Overstated
1. **REW-01 and REW-04 caveats**: "daily body weight [… @nrc2003guidelines, pp. 56, 60]" — NRC p. 60: animals "should be weighed several times a week, ideally before experimental sessions"; daily only at a new protocol's start (p. 56); NC3Rs recommendation 6 does say daily. "Guidance establishes each monkey's minimum from its own baseline intake" goes past both (NC3Rs asks that baseline intake be established; NRC p. 56 warns voluntary intake "might not be equivalent to the animal's minimal fluid-requirement levels").
2. **Womelsdorf 2021 called a "published minimum"** (REW-01 caveat, REW-04): the paper (Testing Procedure) adjusted volume so completion gave "~150–350 ml" and "all monkeys would work for more fluid reward on some days" — neither a minimum nor a daily total. REW-08's "supplied the daily water amount" also goes past the text; REW-03's wording is right.
3. **REW-01**: Gray 2016 "blood and urine measures showed no dehydration" — blood did not differ; urine osmolality, creatinine and specific gravity were significantly higher under both fluid-control protocols (Results, "Physiological measures"; Table 4), read by the authors as healthy kidneys retaining fluid.
4. **WEL-01 Basis and Caveat** — see Welfare residues.
5. **WEL-01 and WEL-25 state AWR 3.81(d) as absolute** ("must include") — NRC p. 49 quotes it with "unless continuous restraint is justified for scientific reasons and approved by the IACUC".
6. **REC-07**: NWB §2.6.2.46 defines `invalid_times` as "Time intervals that should be removed from analysis" — no position on discarding a session.
7. **REW-04**: NRC p. 55 says "It is difficult to specify…", not "cannot be specified in general".
8. **REC-15**: a 40 kHz scan keeps only harmonics below 20 kHz, and wl-sync's anti-alias filter (~12 kHz, §6.4) limits the band anyway.

## Bibliographic
1. `nc3rs2012refining`: the note says "its recommendations are numbered" — on the page they are an unnumbered bulleted list; the numbers 2, 3, 5, 6 match bullet order — say they are the library's numbering by bullet order.
2. Unlisted checker flags, entries correct: christie2015comparison, fraser2009control (en dash dropped by `fold()`); icnirp2013icnirp, nrc2003guidelines (corporate authors, no Crossref author); ieee2020ieee (no year, no author; title appends "(IEEE Std 1588-2019)"; approved 2019-11-07, published 2020-06-16); cie2006fundamental (no issued year; author "CIE TC 1-36"; title prefixed "CIE 170-1:2006").
3. cie2006cie/cieb explanations true (DataCite: publicationYear 2006, tables 6.2, 6.7, CC BY-SA 4.0; CSV md5/sha256 match; pages show stale MD5s).
4. Minor: mills2010network (Crossref omits Martin; RFC header lists "J. Martin, Ed." — four authors right); cogan2008neural missing its issue number; halir1998numerically confirmed via the handle record (WSCG '98, Plzeň, pp. 125–132) — PostScript not openable (TLS), claim checked against title only (say so in the note).
5. All other DOIs match. Calapai and Christie use print years (online 2016 and 2014).

## Link/inline
1. S8 head — the stale sentence above.
2. Engine spec §8 item 4: `[@siegle2021survey]` on "counting flip-patch edges from each trial's start code" — REC-05 calls that this design's own; Siegle interpolates between photodiode events every 60 frames. Move or drop.
3. P9 §2: `[@siegle2021survey]` on "the primary samples the sync box's barcode … every frame" — in Siegle the master computer recorded per-frame sync and the barcode went to the probes; cameras did not sample it. Weak — move or drop.
4. Engine spec §8 item 7: `[@nwb2026nwb]` on "(acceptable in every session kind)" — belongs on "affected trials marked".
5. All 215 anchored Where links resolve.
6. Reworded sentences disclosed (S0 §7.1, §7.7, S9 §3, pitfalls P5, SpikeGLX and landscape notes).

## Counts
68 entries; 65 library entries; 120 cited claims; ~25 inline placements. Wrong 6 (+4 location groups), Overstated 8, Forced 0, Bibliographic 1 actionable + flags, Link/inline 4. 26 claims checked against abstracts only.
