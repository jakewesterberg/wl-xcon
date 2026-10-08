> Working file of 2026-10-08, committed as the record of the reference library's backfill and checks (plan: `docs/superpowers/plans/2026-10-08-reference-library.md`). Line numbers, commits and paths are as they were then; citations here are quoted as found, some of them since corrected or removed.

# Independent check: stereo and eye (STE-01..26, EYE-01..28), at 5359fee — the checker's report, saved by the controller

Method: all 47 DOIs fetched from Crossref directly (the checker hit HTTP 429 with others running); full texts from PMC/NCBI, jneurosci.org, archive.org (Julesz 1960, Wheatstone 1838), the Blignaut PDF, SR Research threads 221 and 313, the Edmund page; abstracts from Europe PMC, Optica, Nature, Crossref. All Where links and anchors resolve.

## Wrong
1. **STE-24 and its inline in S4 §10 item 6 (`[@tanabe2004rejection]`)**: Tanabe clamped vergence (±0.5° of the screen plane; disparate centre inside a zero-disparity annulus; "The vergence response of the monkey was unaltered by disparity", Fig. 2C) — a confound check, not a check that a disparity was fused at its depth. Drop Tanabe from STE-24 and the S4 inline; Wirth 2017 and Busettini 1996 carry the claim.
2. **S1a §12 inline (EYE-23)**: "(in a normal macaque it stays nearly as stable as the viewing eye, but not aligned with it [@pirdankar2016influence])" — Pirdankar reports only stability (BCEA; mean difference 0.03 deg², covered eye 0.20 deg²), nothing on alignment; "not aligned" is Gantz and Švede. Move the citation or end the Pirdankar clause at "viewing eye".
3. **STE-07 and STE-10, Tanabe's location**: the sign convention ("negative and positive values refer to crossed and uncrossed disparities, respectively") and the 21-condition list are under the "Electrophysiology." run-in, not "Task and visual stimulation" (only the anticorrelation construction is there); "nine disparities" holds for the first monkey only (later cells 13).
4. **STE-08, Carmel's figure**: the divider is Protocol §2, Fig. 4, not Fig. 1D (Fig. 1D is the nonius lines).

## Overstated
1. **EYE-01, Kimmel** cited for "why a pupil-based tracker alone falls short in macaques": Kimmel concludes optical performance "now rivals that of the search coil, rendering optical systems appropriate for many if not most applications", and the luminance artifact "was generally modest for the luminance range of a typical task". Keep the 0.2–1° and 2° figures (Results, "Experiment 2, analysis 1"); reframe.
2. **EYE-20 and engine spec §5 item 6 inline**: Saunders & Woods for "suppression lessens within 5–25 ms of the saccade's end" — their Discussion attributes it to McConkie & Loschky 2002, Ross et al. 2001, Shioiri 1993, Volkmann…; a claim from a summary (the README forbids). Cite what was opened, or drop.
3. **EYE-20, Cavanaugh**: the displacement-threshold sentence ends "(Bridgeman et al., 1975)" — Cavanaugh restating Bridgeman, which the entry says could not be opened.
4. **EYE-20, Loschky**: "peripheral resolution updates as late as 60 ms … went undetected" is stronger than the abstract ("did not significantly increase the detectability of image blur and/or motion transients").
5. **EYE-10 Basis and Caveat, Švede**: "is absorbed and alters"/"absorbs" vs the abstract's "a vergence error may be present and may affect the subsequent measurement" (abstract only).
6. **STE-11**: "Both argue that the default (identical backgrounds) helps fusion" — Carmel argues identical frames, fixation points and nonius lines, and allows a frame may be undesirable on a uniform background; Cox describes an oval aperture; neither discusses backgrounds.
7. **STE-23**: "is the published macaque procedure" — Cox, Mitchell, Dougherty describe a nine-location mirror-alignment check to 10° with gaze compared across eyes, not each eye's map fitted from its own grid. Say "matches the published alignment procedure".
8. **STE-10**: Julesz Figs. 15–16 called "the first anticorrelated stereogram" — the paper (pp. 1140–1141) makes no priority claim.
9. **EYE-18**: "No tolerance for blinks by default matches macaque practice" — Kimmel's verbatim quote (Methods, "Apparatus") is one monkey's control setup in one study, named as a side benefit.
10. **EYE-15**: "Santini et al. do not address stale samples" — only the abstract was read; an abstract cannot support the negative.
11. **EYE-19 Caveat**: ties Kimmel's sub-saccade merging to ringing; Kimmel attributes the merging to "noise in the position signal" (ringing is a separate Results section).
12. **Engine spec §5 item 6 inline**: "so an isoluminant change is not hidden by landing inside a saccade" from Diamond — Diamond measured contrast thresholds for flashed low-frequency chromatic gratings, not change or displacement detection.
13. **Inlines dropping the paper's hedge**: S5 §4.2 (`"The 2% is OS preemption on a Windows PC … [@ressmeyer]"`), S5 §4 and `openiris-dpi.md` ("from OS preemption") — the paper says "likely due to CPU preemption by background operating system processes" (§3.1) and never names Windows. These sentences are the lab's documents: keep their claim, but the citation must not carry more than the paper says (put "likely" in, or move the citation to a clause that says what the paper says).
14. **Direct-view spec §5 and S0 §7.1 row 5 inlines**: "the paper's rule is that the illuminator sits about 10° shallower" — the rule (§3.1) is only "shallower"; 35° against 25° is its configuration (§2.2). Panel comparison §4.1 correctly marks the 10° ASSUMED.
15. **EYE-21 (minor)**: Saunders says relocating at fixation onset or smoothing "may be desirable"; the entry says "is the practical alternative".

## Forced
1. **EYE-17, and the inlines in roadmap M3 and S5 §10 item 2 (`[@saunders2014direct]`)**: grace and staleness from our own data rest on CLAUDE.md's measurement rule and S5 §4; Saunders is about end-to-end display latency. Remove the inlines; EYE-17's Basis says what it rests on.
2. **S1a §13 inline `[@kimmel2012tracking]`** on "blinks are not tolerated unless a task says so, because …": the reason is the lab's. Remove the inline.
3. **STE-10 "Basis: Published."**: the RDS-appearance/Form-disparity split and the `correlation` field are engineering (its Decided says so). Say which part is whose.
4. **STE-06 (minor)**: the engine spec §5 item 3 inline puts Marshel (mouse) on "true visual angle (default)" — the entry says it is a PI decision with only mouse precedent; the inline does not. Remove the inline or qualify.

## Bibliographic
No metadata errors in 51 entries (47 DOIs and 4 URLs). Blignaut's and Saunders's year explanations are true. Three MISMATCH lines are checker artefacts: ferrea2025frontal ("brain-computer") and hoffman2008vergenceaccommodation ("Vergence-accommodation") — the checker deletes Crossref's en dash; walton2019rhesus — `{B}ehavioral` folds to "b ehavioral". Fix the checker's folding (en/em dash → hyphen or space consistently; strip braces without inserting spaces), with tests.

## Link/inline
1. Headings still state superseded claims: EYE-20 "(after it, it is readily seen)", EYE-23 "the non-viewing eye drifts" — the bodies say they were corrected; update the headings.
2. Code comments `wl_xcon/run.py` and `wl_xcon/task.py` still say "one eye doing nothing" (S1a §12 corrected it) — align (comments only).
3. For awareness: reworded decision sentences each marked "(Corrected 2026-10-08…)" in S0 §5.2, controller architecture §8.2, S1a §12 and §13, S4 §3, S9a §2.2, demo-mode §3.3, engine spec §5 item 6 — supported by the sources except as above (Wrong 2; Overstated 2, 12, 13).
4. STE-12's heading "73 px/deg" is the field mean (1920/(2×13.15°)); the centre is 71.7 px/deg; the heading pairs 73 with the centre's 0.84 arcmin. Say which.

## Counts
54 decision entries, 51 library entries; 151 cited claims, 6 arithmetic re-derivations (all hold), ~50 inline citations in 17 documents. Wrong 4, Overstated 15, Forced 4, Bibliographic 0 (+3 checker artefacts), Link/inline 4. About 45 claims checked against abstracts only.
