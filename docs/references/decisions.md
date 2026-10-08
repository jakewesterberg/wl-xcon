# Decisions and the papers they rest on

One entry per science-facing decision: what was decided, by whom and when (**Decided**), where it is
recorded (**Where**), and what it rests on (**Basis**). A published basis names its papers by key from
[library.bib](library.bib), each with the claim it supports and where in the paper that claim is. A
decision that rests on something else — an institutional rule, the PI's decision, an engineering
default — says so in **Basis** instead, and is never given a paper it does not rest on. Where a
decision combines the two, the entry says which part is whose. How to add a paper or an entry:
[README.md](README.md). `tests/test_references.py` checks that every entry has its three lines, that
every link names a file that exists, and that every key resolves.

## Color and luminance

### Cone fundamentals: the CIE 10° observer, unadjusted for macaques
- **Decided:** 2026-10-08, the PI (A2 Q4: "Human 10°, switchable later"), after a literature search; the 10° default itself on 2026-10-07 (the brainstorm notes' N§R5).
- **Where:** [engine spec §7.9](../superpowers/specs/2026-10-07-engine-design.md#7-color-and-luminance-n4-nr4-nr5), [A2 research note §5](../research/2026-10-08-engine-a2-color-research.md#5-macaque-vs-human); the brainstorm notes, "The morning after (asked 2026-10-08)", on engine-b.
- **Basis:** [@stockman2000spectral] — the 10° cone fundamentals themselves (Table 2, pp. 1732-1734); that the CIE 2006 10° observer is this set is CIE 170-1:2006's statement, not yet in the library. [@schnapf1988spectral] — the red and green cones of one human retina were "virtually identical" to macaque cones (abstract). [@baylor1987spectral] — macaque cone peaks near 430, 531 and 561 nm, and human color matching well predicted from the monkey cones (abstract). [@horwitz2015what] — fitting rhesus detection data needs a macaque lens about 60% of the average human lens density, put down to the monkeys being younger and smaller (the text on Fig. 3). Not adjusting for it is the PI's decision. It rests on the search's own computation that a macaque lens or macular setting changes stimuli by about the CIE's own 2° vs 10° difference (summarized in the brainstorm notes; not a published result), and on that being smaller than the spread between animals. The spread is published — macular pigment's central peak 0.42-1.0 across monkey retinas (Snodderly, Auran & Delori 1984) and zeaxanthin differing up to fourfold between individual monkeys (Handelman et al. 1991), abstracts read 2026-10-08, not yet in the library; the color backfill, this plan's Task 3, enters them — but comparing it with the computed effect is the search's own. The observer's parameters are recorded so the setting can be switched on later.

### DKL: the luminance axis in luminance contrast, the color axes in pooled cone contrast
- **Decided:** 2026-10-08, the PI (A2 Q1: "Hybrid").
- **Where:** [A2 research note §2](../research/2026-10-08-engine-a2-color-research.md#2-dkl-normalizations-in-use) and its [Q1](../research/2026-10-08-engine-a2-color-research.md#questions-for-the-pi-the-agents-framing-to-be-asked-in-plain-terms); [engine spec §7.4](../superpowers/specs/2026-10-07-engine-design.md#7-color-and-luminance-n4-nr4-nr5), which requires one stated normalization; the brainstorm notes, "The morning after (asked 2026-10-08)", on engine-b.
- **Basis:** [@derrington1984chromatic] — the space: a luminance axis and two isoluminant axes, "constant B" and "constant R & G", through a white point (abstract). [@brainard1996cone] — luminance contrast is the natural scaling for the luminance axis, and there is none for the two color axes (p. 571); scaling each axis to unit response for its isolating stimulus of unit pooled cone contrast does not depend on apparatus or observer (p. 572; pooled cone contrast is Eq. A.4.2, p. 568); the constants and the background must be stated whenever the space is used (p. 575). Taking Brainard's natural choice for one axis and his adopted one for the other two is the PI's decision among the options offered; its consequence, that the axes then carry different units and the gamut check needs a limit per axis, is the research note's (§2).

### The cone citation: "virtually identical" is Schnapf et al. 1988; the macaque peaks are Baylor et al. 1987
- **Decided:** 2026-10-08, the PI ("Yes, keep it"), confirming the research note's correction of the spec.
- **Where:** [engine spec §7.9](../superpowers/specs/2026-10-07-engine-design.md#7-color-and-luminance-n4-nr4-nr5), [A2 research note §0](../research/2026-10-08-engine-a2-color-research.md#0-corrections-to-current-repo-text) and [§5](../research/2026-10-08-engine-a2-color-research.md#5-macaque-vs-human); the brainstorm notes, "The morning after (asked 2026-10-08)", on engine-b.
- **Basis:** [@schnapf1988spectral] — "Spectral sensitivities of the red and green cones from a human retina were virtually identical to those of macaque cones" (abstract; L and M cones only, from one human retina). [@baylor1987spectral] — suction-electrode spectra of five blue, twenty green and sixteen red cones of *Macaca fascicularis*, peaking near 430, 531 and 561 nm (abstract).
