> Working file of 2026-10-08, committed as the record of the reference library's backfill and checks (plan: `docs/superpowers/plans/2026-10-08-reference-library.md`). Line numbers, commits and paths are as they were then; citations here are quoted as found, some of them since corrected or removed.

# Independent check: task design (TSK-01..49), at 5359fee — the checker's report, saved by the controller

Read-only; all 69 DOIs fetched from Crossref directly (the repo checker hit HTTP 429 on 15); full texts for Westerberg 2020 and 2023, Luo, Asaad, Han, Pilly, Pronk, Hafed, Wolfe (PMC) and Levitt, Rensink, Peli, Field, Treisman, Card, Salmon, Portilla (PDFs), both MonkeyLogic pages. Westerberg 2020/2023 methods are quoted accurately throughout.

## Wrong
1. **TSK-05, pilly2009what**: "the four common algorithms differ in what the noise dots do (§1, A-D)" is false. §1 (PMC2789308): WN noise dots "randomly relocated"; MN "similar to WN, but three uncorrelated random dot sequences… interleaved"; LL "similar to MN" with a hard limit on signal lifetime; BM the only one changing noise dots ("noise dots are only given random directions"). Correct: they differ mostly in how signal dots are chosen and displaced; only BM changes the noise rule. The three noise rules the decision names (replotted, random direction, random walk) are Scase et al.'s.
2. **TSK-10, rensink1997see**: p. 370 — 17.1 alternations (10.9 s) is for marginal-interest changes only; central-interest took 7.3 (4.7 s); without blanks 1.4 (0.9 s). "Would swamp the local motion signals" is the hypothesis in the introduction (p. 369, above GENERAL METHOD), stated conditionally.
3. **TSK-34 Basis and Caveat, levitt1971transformed**: the curvature sentence (top of p. 471) qualifies Wetherill's Robbins–Monro result (c = 0.5/b minimizing variance about X50: "This result, however, is based on the assumption that the response curve is approximately linear…"). Levitt derives 70.7% on p. 472 (Sec. II.B, [P(X)]² = 0.5) with no step-size condition. Correct: convergence's dependence on step size is García-Pérez 1998's (already in the caveat).
4. **Levitt page locations (TSK-32, -33, -34)**: step-halving rule ("first, third, seventh, fifteenth… runs") p. 471 not 470; Sec. II.B, the derivation and Fig. 5 p. 472 not 471 (Table I entry 2, P(X) = 0.707, p. 471 — correct); interleaving sentence pp. 471–472 not 470–471, and it reads "two or more strategies" (the quote drops "or more").
5. **TSK-48, card1977evaluation**: Table 2 is report p. 10 (PDF p. 12), not p. 11 — in decisions.md, the bib note, and the inline `[@card1977evaluation, Table 2, p. 11]` in demo-mode §14 item 17. Figures correct (homing 0.36 s, positioning 1.29 s, SD 0.42).

## Overstated
- TSK-38 nystrom2013influence (also inline in S5 §2): the abstract lists gaze direction as studied but reports results only for calibration method and eye physiology; nothing on gaze outside the calibrated region.
- TSK-45 hafed2009neural: "triggered when that activity's center of mass deviates" is the computational model ("provides a plausible mechanism"); the inactivation experiments show the SC's causal role. Say so.
- TSK-39 treisman1980featureintegration p. 107: the quote drops "apparently" ("the display was apparently searched spatially in parallel…").
- TSK-39 thompson1996perceptual: "color pop-out" — the abstract never names the feature.
- TSK-39 bravo1992role: omits the abstract's exception — when the target's shape was judged and the colors reversed unpredictably, RT fell with set size (relevant: the task's feature can change any trial).
- TSK-29 asaad2008flexible: Asaad names only immediate repetition ("immediately repeat incorrect trials"; "repeat errors immediately"); ignore and delayed repeat come from the NIMH documentation only.
- TSK-23 nimhmonkeylogic2026task: "the standard choice" not on the page (it lists random with/without replacement alongside increasing, decreasing, user-defined).
- TSK-08 daugman1985uncertainty: "their bandwidths follow from the envelope" not in the abstract.
- TSK-46 pronk2020mental: per-device means in Table 4 run 57.6–132.9 ms but single trials as low as 44.9 ms — "57 ms or more" overstates.
- TSK-34 Caveat garciaperez1998forcedchoice: "in log units" not in the abstract; its condition is Δ−/Δ+ = 1.
- TSK-40 carpenter1995neural: the abstract says "In one such model…", which the experiments "confirm" — not that distributions "come from" a linear rise.
- TSK-06 salmon2011parallel: "All our PRNGs pass… BigCrush" — the paper's generators, not counter-based generators as a class.
- TSK-05 scase1996what: "both support declaring it" is generous — Scase's practical message: thresholds "are not much affected by the choice of noise".
- TSK-04 field1987relations: Field never says "pink"; he shows equal energy per octave (p. 2385, Eqs. 7–9).
- TSK-36 westerberg2020/2023: "…smaller than the receptive field, about 3° at 10°" reads as if 3° were the RF size; items are ~3° at 10°, V4 RFs 0.84 dva per dva (~8.4° at 10°) per 2023.
- Location only: Luo "(Results)" in TSK-12 and the TSK-34 caveat — the hit-rate ambiguity is stated in the Introduction ("any improvements in hit rate could depend on a change in only criterion, only sensitivity, or both"); Han "(Introduction)" in TSK-15 and TSK-24 — the non-aging definition is under "Prior studies → Repetition priming account".

## Forced
1. **TSK-39, bichot2002priming supporting randomized `array_phase`**: Bichot's inhibition of return is about repeating the target's position (which `target_index` already varies), not about rotating the array or animals learning positions. The PI's own design did not rotate the array between trials — 2020: "The array was then oriented so that its eccentricity coincided with the location of the receptive field… a single array item was placed at the center of the receptive field"; 2023: "The polar angle positioning of the items… varied from session to session so that one item… at the center of the population receptive field". Record as a caveat (rotating every trial removes the item centered on the RF that a recording needs); drop Bichot as support for rotation. (The controller adds this to the PI's step-3 questions.)
2. **TSK-29 and TSK-31 (and engine spec §16.6 inline), kiani2009representation**: Kiani's monkeys chose an offered, rewarded sure option; it does not show animals erring or breaking fixation to avoid a condition. Label as an analogy or drop (remove the inline if it presents it as evidence).
3. **TSK-38 nystrom2013influence** (see Overstated): not about extrapolation.
4. **S1a §9 inline `[@daugman1985uncertainty]`** on "hard aperture — and that changes edge artifacts and spatial-frequency bandwidth": TSK-08 says the hard-edge effect has no paper behind it. Move the citation to the Gaussian-envelope clause.
5. **TSK-26 attribution**: `scheduler.py` attributes only `Counting` "Declared per block" to the PI; `criterion_over`'s comment carries none — that part is an engineering choice.

## Bibliographic
69 DOIs agree on all fields. Confirmed: garciaperez (dotless ı + combining acute), nystrom (online 2012-09-07, print 2013-03, vol. 45), pronk (online 2019-12-10, print 2020-06). End pages confirmed: daugman 1160–1169, field 2379–2394 (PubMed), peli 2032–2040 (PDF). Crossref lists gur1997visual's second author as "NODDERLY" — the bib's "Snodderly" is right (OpenAlex agrees). Unresolved: portilla2000parametric — Crossref/OpenAlex 49–70; the authors' reprint header says 49–71 and its last page is 71 (note it). Card report cover (SSL-77-1, April 1977) and Ergonomics 21(8):601–613 cross-reference correct; both MonkeyLogic pages contain the quoted text.

## Link/inline
- Every Where link resolves; code facts in TSK-11, -34, -35, -36, -37, -39 match the code.
- The 9 spec files other than demo mode are identical once citations are removed; demo-mode §14 item 17 reworded as a recorded correction.
- TSK-48 heading still states the superseded "roughly 0.6-1 s"; TSK-15 heading "a truncated exponential's rises" is missing "hazard".
- `[@asaad2008flexible]` in S8 §1 and controller architecture §5.5 sits right after the "80% correct over the last 20 completed trials" example (TSK-25: no source) — move it to "criterion-based".

## The PI's papers
Accurate: 750–1250 ms non-aging foreperiod and both reasons; fixation within 1° (2020) and 0.5 dva (2023); saccade within 1000 ms then 500 ms ("at least" 500 ms, 2020) held within 2–5 dva of the target; 0.3 dva fixation dot and 0.3 dva-per-dva item scaling; six items, each position equally likely; no reward and 1–5 s time-out after a distractor saccade; blocks of 5–50 trials, median 12 (2020). Also: 2023's blocks were 5–15 trials; 2023 calls the colors isoluminant only "to a human observer" and treats them as features "at the intersection of color and luminance" — bears on TSK-39's "isoluminant red and green". Optional caveat for TSK-15/24: Han & Proctor found sequential foreperiod effects persist under non-aging distributions.

## Counts
49 entries; 72 library entries (69 DOI, 3 URL); 149 citation claims + ~25 code/document claims; Wrong 5, Overstated 14 (+1 ambiguous, 2 location-only), Forced 5, Bibliographic 0 (1 Crossref error noted, 1 unresolved), Link/inline 3 (+ Card's page inline). 90 of 149 claims checkable only against an abstract.
