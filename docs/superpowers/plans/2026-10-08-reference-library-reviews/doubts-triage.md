> Working file of 2026-10-08, committed as the record of the reference library's backfill and checks (plan: `docs/superpowers/plans/2026-10-08-reference-library.md`). Line numbers, commits and paths are as they were then; citations here are quoted as found, some of them since corrected or removed.

# Triage of the backfill's doubts, and of the 13 documents left behind

Read 2026-10-08 against `origin/main` (backlog next free ID XC-276 there; `origin/engine-b` has used XC-276 to
XC-278, so the next free ID is XC-279 once it merges, and every line below is written `XC-???`), the PI's
answers at the end of `docs/superpowers/specs/2026-10-07-engine-brainstorm-notes.md` on `origin/engine-b`
("The morning after"), and the seven backfill write-ups in `backfill/`. Passages quoted as "wrong text" were
read at `origin/main`, not taken from the write-ups' paraphrase. "Triage N" is item N of
`disagreements-triage.md`. Citations in note and fix texts use the library's `[@key]` form (every key is in
one of the seven `.bib` files); backlog lines use author and year, as the backlog's other lines do.

**Tally: class 1, 19; class 2, 15; class 3, 10 (9 new lines, 1 already scheduled); class 4, 0; class 5, 5.**

Coverage: color doubts 1-5, display 1-6, stereo 1-4 (and STE-18's note), eye 7 (EYE-03, -07/08, -10, -11, -19,
-20, -23), welfare 1-5, task 8 (TSK-34 three, TSK-39 three, TSK-35, TSK-48), recording 4; triage items 1, 2, 5,
6, 7, 8, 9, 13, 14, 15, 16, 17, 19.

---

## Class 1: library note only

Each is a caveat on a settled, informed decision or a nuance. It goes into that decision's entry in
`docs/references/decisions.md` as a dated line, after **Basis**: `- **Caveat (2026-10-08):** <text>`.
No other action.

**N1. COL-03, COL-05, COL-17 (color doubt 1).** Isoluminance against the human standard observer is not the
macaque's; the PI declined the per-animal null on 2026-10-07 knowing it was recommended, and named V_F,10 on
2026-10-08 (A2 Q5).
> Isoluminance here is the CIE 10° standard observer's (V_F,10), not the animal's. Macaque red-green
> equiluminance points differ from humans' and between animals, consistent with L:M ratios near 1:1 against
> 2:1 [@dobkins2000comparison]; monkeys are more sensitive than humans to 15 Hz red-green isoluminant
> modulation in a way optics do not explain [@lindbloombrown2014spectral]; the macaque luminance plane differs
> from the human definition [@horwitz2015what]; "a stimulus that is equiluminant for a human may possess
> luminance contrast for a monkey" [@conway2014color]; even among 22 young humans, settings against this
> observer spanned M:L cone-contrast ratios of −6.1 to −0.7 [@he2021modeling]; per-observer flicker
> photometry is the published remedy where silencing luminance matters [@brainard2002display, p. 183].
> Against them, MT null planes lay close to photometric isoluminance [@gegenfurtner1994chromatic]. A methods
> section states that the isoluminance is the standard observer's; a result that rests on it (laminar M/P/K
> mapping, chromatic motion) says so.

**N2. COL-15, COL-16 (color doubt 2).** Human fundamentals for a macaque observer; decided 2026-10-08 (A2 Q4)
after a deeper search.
> For nonhuman observers "it is crucial to customize the rendering calculations for the spectral
> sensitivities appropriate for the species" [@brainard2002display, p. 183], and the macaque lens is about 60%
> of the human density [@horwitz2015what]. The unadjusted human observer is nonetheless the field's routine
> practice [@conway2014color; @li2022cone], and the 2026-10-08 computation put the effect near the CIE's own
> 2° against 10° difference and below the spread between animals. The observer's parameters are recorded and
> the macaque lens or macular setting can be switched on later.

**N3. COL-11 (color doubt 3).** The stereoscope's halves assumed equal (PI, 2026-10-07, offered against
measuring each eye's path); the doubt adds a second effect.
> Published consumer-OLED uniformity is 4-7% worst case, the left half worse on every consumer display tested
> [@abuhaila2025recent, Results "Luminance uniformity", Fig. 8], so "equal halves" is an assumption V9's
> per-half photometry checks. The stated eye-dominance effect is supported and small at a few percent (a 1
> log-unit attenuation moved the balance point from 1.03 to 0.91 [@zhou2013effect]). Not stated in the spec: a
> dimmer eye's signal is also delayed (about 38 ms in V1 for a 1.5 log-unit filter
> [@chadnova2018interocular]), the Pulfrich effect, which counterbalancing the masked eye does not remove
> from a motion-in-depth task. At a few percent the delay should be far smaller; no measurement at that size
> was found. A motion-in-depth task checks V9's measured difference first.

**N4. DISP-17 (display doubt 5).** The pixel limit is below macaque foveal acuity; the PI chose a warning.
> Macaque foveal grating acuity is about 38 c/deg [@merigan1990spatial]; direct view resolves about 28 c/deg at
> the center (about 36 through the stereoscope, by the sampling theorem [@shannon1949communication]). The rig
> cannot present gratings at the animal's foveal acuity limit in direct view, and artifacts near the pixel
> limit are within what the animal resolves; hence the warning rather than silence.

**N5. DISP-13 (display doubt 6, the decision's part).** Five-minute trials and the continuous mode meet OLED
thermal after-images. (The measurement is class 3's L2.)
> On an OLED, a high-contrast stimulus held for tens of seconds to a minute leaves a local luminance
> difference of about 0.7-1.5% of peak that takes up to minutes to fade [@dimigen2026advantages, Results
> "Slow temperature-luminance interactions"; a WOLED, not our panel]. After a long adapter the luminance is
> not the calibrated one; an adaptation design states it until V9 measures it on the PG27UCDM.

**N6. STE-07 (stereo doubt 2b).** The disparity sign convention differs between macaque labs; the choice is
the PI's (2026-10-07, "Near is negative").
> Crossed-negative, as here, follows [@tanabe2004rejection]; Cumming and Parker use crossed-positive
> [@cumming1999binocular]. A methods section states the sign, and a comparison with the Cumming-Parker papers
> flips it.

**N7. STE-18, STE-19 (stereo doubt 4).** Accommodation-vergence coupling at large disparities.
> Accommodative amplitude is not the limit (young rhesus have at least 17-18 D voluntary
> [@smith1984behavioral]), but monkeys separate accommodation from vergence only modestly under conflicting
> cues [@cumming1986disparityinduced]. At about 0.55 D of vergence demand per degree of disparity, a large
> disparity in the stereoscope may pull accommodation off the screen and blur the stimulus; the software
> vergence offset removes the conflict at zero disparity only. No macaque measurement of the blur cost was
> found.

**N8. EYE-03 (eye doubt, the fallback).** The pupil-CR fallback moves with luminance.
> Pupil-CR positions in macaques move 0.2-1° and more with luminance-driven pupil changes
> [@kimmel2012tracking], and drift with pupil dynamics even at constant luminance
> [@ressmeyer2026openirisdpi, §3.3.2, §4.1]. The fallback map holds at the luminance it was fitted at; the
> per-sample method flag (XC-006) keeps that visible.

**N9. EYE-10 (eye doubt, direct view's part).** Direct view calibrates binocularly.
> A binocular calibration absorbs the fixation disparity the animal holds while calibrating, so later vergence
> or fixation-disparity measures are relative to it; a monocular calibration avoids this
> [@svede2015monocular] (human, video tracker), as the stereoscope's monocular grids do. A direct-view task
> that measures vergence or fixation disparity says so. (S4 §3's stale stereoscope rule is in class 3's L4.)

**N10. EYE-19 (eye doubt).** Saccade detection on a DPI signal.
> DPI "is ill-suited for measuring saccade kinematics": the lens oscillates at saccade onset and end, so the
> trace rings and briefly decouples from the eye's rotation [@ressmeyer2026openirisdpi, §4.1, Introduction],
> with deviations from the search coil during and just after saccades [@deubel1995fourth]; pupil-based
> tracking rings after saccades too, where sub-saccades within 30 ms were merged [@kimmel2012tracking].
> Engbert-Kliegl stands, but saccade offsets ("update on landing", EYE-21) and amplitudes detected on the DPI
> signal are distorted; V3(c) sets the detector's parameters with that in view (XC-072).

**N11. EYE-07 (eye doubt, the edge-target part).** Targets at the edges of the measured area.
> Targets on the edges of the area measured limit polynomial end effects [@blignaut2014mapping, p. 3]. Along
> the axes, direct view's stimuli from 10.8° to 15° lie beyond the constellation's edge targets, which S5 §2
> reports as extrapolation rather than refusing, by design.

**N12. REW-08 (welfare doubt 1).** What "the supplement" is.
> NC3Rs: a monkey that misses its daily requirement in the session gets a supplement afterwards, and
> supplements should be the most consistent with reliable performance, reviewed regularly
> [@nc3rs2012refining, recommendation 5]. The figure reported here, "mL to reach the day's floor" (floor −
> already delivered − earned), is the least that may be given, not a recommended amount; the floor-not-ceiling
> rule (PI, 2026-09-06) is not in question.

**N13. REW-01, REW-04 (welfare doubt 2).** The floor is a fixed mL figure; guidance sets it per animal and per
body weight.
> Guidance establishes each monkey's minimum from its own baseline intake, re-established periodically, with
> daily body weight `[@nc3rs2012refining, recommendations 2 and 6; @national2003guidelines, pp. 56, 60]`;
> published minima are 14-26 mL/kg/day [@gray2016physiological] and about 20-25 mL/kg
> [@womelsdorf2021kiosk]. A subject's bounded config holds a fixed mL floor (XC-067), which does not follow
> weight on its own; the reference configs' 20 mL is a deliberately implausible placeholder, not 20 mL/kg.

**N14. WEL-01, WEL-07 (welfare doubt 3).** Per excursion or per day.
> The eight hours are the institution's (the project authorisation, not public and not named in the
> documents); neither the EU Directive `[@european2010directive]` nor the Belgian Royal Decree
> [@belgium2013koninklijk] sets an hour figure, which the ethics committee sets per project (decree Art. 23
> §1). The limit is cage to cage, per excursion, and a second excursion the same day starts a new interval and
> a new session (PI, 2026-09-20, weighing the two-record consequence). The one numeric restraint rule found is
> per day (US AWR 3.81(d), restraint past 12 h, via `[@national2003guidelines, p. 49]`) and is not this
> institution's.

**N15. TSK-34 (task doubt 2).** "Converging near 71%" is approximate.
> One-up two-down converges on 70.7% for steps small against the response curve [@levitt1971transformed,
> pp. 470-471]. With equal up and down steps in log units (×0.8, ÷0.8), forced-choice transformed staircases
> "fail to reach their presumed targets", and a two-down one-up rule with Δ−/Δ+ = 0.5488 converges on 80.35%
> [@garciaperez1998forcedchoice]. The task is not forced choice, so the size of the error here is unknown.
> (Context for class 5's Q1.)

**N16. TSK-39 (task doubt 4).** Shape pop-out is weaker than color pop-out.
> Color is an "undoubted" guiding attribute and shape only "probable" [@wolfe2017five]; color targets were
> detected fast regardless of local feature contrast, orientation targets not [@nothdurft1993role]; Treisman
> and Gelade's parallel shape search used letters [@treisman1980featureintegration, p. 107]. A square among
> discs is piloted before it is called pop-out.

**N17. TSK-35 (task doubt 7).** The fixation window starts at a training value.
> `fix_window` starts at 2.0°; published recording windows are 0.5-1.5° [@westerberg2020priming;
> @westerberg2023feedforward; @luo2015neuronal], inside the range (0.5-5°). A recording session sets it lower.

**N18. REC-16 (recording doubt 3).** Two cameras is below the 3D-pose recommendation.
> For several limbs Anipose recommends at least three cameras, with "a dramatic reduction in error from 2 to
> 3 cameras" [@karashchuk2021anipose]; two, the low end of "2 to 4 in practice", is below that for 3D pose of
> the hands and body. (The count is the PI's procurement.)

**N19. REC-07 (recording doubt 4).** No session-level threshold for frame-clock faults.
> The Allen survey failed a whole session past 60 delayed frames [@siegle2021survey]; this design marks
> affected trials and never fails a session (PI, 2026-10-07), consistent with NWB's invalid intervals
> [@nwb2026nwb]. No session-level threshold exists.

---

## Class 2: document fix (in the library's integration commit)

Each fix is a dated correction. Documents the PI ruled keep their wording as records (the brainstorm notes,
dated research notes, M0-REVIEW) get a dated note beside the wrong text instead of a rewrite.

**D1. COL-13, DISP-02, DISP-03 (color doubt 4, display doubt 1, and the color write-up's header).** S0 cites
"the JOV paper" without naming it and misattributes the fill-factor finding to it.
- File: `docs/superpowers/specs/2026-08-31-S0-hosts-and-hardware-design.md`.
- §5.1, "Schedule mitigation". Wrong: `the JOV authors state that performance "cannot be assumed or
  guaranteed" even across units of one model.` Correct: `Abu Haila, Kunst, Khanh and Wallis (2025) state that
  similar performance across identical models "cannot be assumed or guaranteed" [@abuhaila2025recent]
  ("Caveats and limitations"), and three units of one OLED model bought together each showed their own
  pattern of nonuniformity [@dimigen2026advantages] ("Spatial uniformity").`
- §5.4 item 2. Wrong: `The JOV paper found luminance "drops drastically" above ~40% fill factor on the panel
  it tested.` Correct: `An earlier study of a Sony PVM-2541 OLED, quoted in [@abuhaila2025recent]
  (Introduction), found luminance "drops drastically" above ~40% fill factor; Abu Haila et al.'s own panels
  held luminance across fill factor except the ASUS WOLED's green channel above 60% fill at values over 900 of
  1023 (Results, "Filling factor", Fig. 9), and an ASUS PG27AQDM showed ABL above its 40% brightness setting
  (about 140 cd/m²) [@dimigen2026advantages] ("Auto-brightness limiting behavior").` (The display backfill
  names the earlier study as [@ito2013evaluation], entered from its abstract, which does not mention fill
  factor; cite it for the 40% only once its full text is read.)
- §5.4 item 3. Wrong: `The IPS LCD in the JOV study showed 10.7% with the left side underperforming; the 27"
  OLED showed ~4%.` Correct: `In [@abuhaila2025recent] (Results, "Luminance uniformity", Fig. 8) the IPS LCD
  differed from center by up to 10.7%, the 27-inch ASUS OLED (a WOLED) by about 4% and the Samsung QD-OLED TV
  by about 7%, all three consumer displays worse on their left half.`

**D2. COL-31 (color doubt 5).** "A QD-OLED's transfer is not a power law" is stated as known, unmeasured,
against the one QD-OLED measurement found.
- `docs/superpowers/specs/2026-10-07-engine-brainstorm-notes.md` §4, "Settled before the element". Wrong (as
  fact): `Known hazards: a QD-OLED's transfer is not a power law;`. Add after the sentence: `(Note
  2026-10-08: that a QD-OLED's transfer is not a power law is UNVERIFIED. The one QD-OLED measured, a Samsung
  TV in a chosen picture mode, fitted power functions with γ 2.29-2.30 after calibration
  [@abuhaila2025recent] (Results "Linearity and gamma function", Table 3). The measured per-channel table,
  engine spec §7 item 6, is right either way.)`
- `docs/research/2026-10-07-engine-display-state.md` §7 ("Inference: what a design can settle now"), the item
  "The panel's real transfer function (QD-OLED not a power law; ABL depends on fill factor)". Correct:
  `(whether this QD-OLED follows a power law is UNVERIFIED; one QD-OLED TV did after calibration
  [@abuhaila2025recent]; ABL depends on fill factor)`. Beside §1.6's quotation of CHECKPOINT at `42e4a9f` ("a
  QD-OLED is not a power law"), add `(UNVERIFIED; see §7's note)`.

**D3. STE-18's note.** Two specs say mirror angles set vergence; the optics drawing §6 makes vergence a
software constant ("Angling the mirrors to converge is the mistake to avoid").
- `docs/superpowers/specs/2026-08-31-controller-architecture-design.md` §8.2. Wrong: `**Mirror angles set
  vergence**, so alignment is a calibrated rig parameter`. Correct: `**Vergence is a constant software
  offset, not a mirror angle** (optics drawing §6), and mirror alignment is a calibrated rig parameter`
  (the rest of the bullet, its "(Nonius/vernier)", is class 3's L4).
- `docs/superpowers/specs/2026-08-31-S0-hosts-and-hardware-design.md` §5.2, last paragraph. Wrong: `the two
  folded paths are equal only if the mirrors are, and mirror angles set vergence, so alignment is a calibrated
  parameter`. Correct: `the two folded paths are equal only if the mirrors are, so alignment is a calibrated
  parameter` and, after the sentence, `Vergence itself is a constant software offset, not a mirror angle
  (optics drawing §6).`

**D4. EYE-20 (eye doubt).** The engine spec says a change landing after a saccade is readily seen; the
literature says only that one landing during it is safely unseen.
- `docs/superpowers/specs/2026-10-07-engine-design.md` §5 item 6. Wrong: `one that lands after it is readily
  seen (corrected from the notes' gloss; the science review's finding 12).` Correct: `one that lands after it
  may be seen (corrected from the notes' gloss, the science review's finding 12; and on 2026-10-08 from the
  reference library: suppression of luminance contrast outlasts the saccade by about 50 ms
  [@diamond2000extraretinal] and lessens within 5-25 ms of its end [@saunders2014direct], so a change landing
  just after is neither safely hidden nor reliably seen; chromatic gratings show no saccadic suppression
  [@diamond2000extraretinal], so an isoluminant change is not hidden by landing inside a saccade; and trained
  monkeys did not show humans' benefit from a post-saccadic blank [@joiner2013corollary], so human results on
  post-saccadic visibility do not transfer directly).`

**D5. EYE-23 (eye doubt).** "The non-viewing eye drifts": the literature shows it deviates to its phoria; in a
normal macaque the covered eye is nearly as stable as the viewing eye. The rule stands.
- `docs/superpowers/specs/2026-08-31-S1a-vocabulary-design.md` §12, "Per-eye criteria". Wrong: `under
  dichoptic presentation the non-viewing eye drifts, so a conjugate estimate averages one eye doing the task
  with one eye doing nothing.` Correct: `under dichoptic presentation the non-viewing eye deviates to its
  phoria [@gantz2020synchronization; @svede2015monocular] rather than following the stimulus (in a normal
  macaque it stays nearly as stable as the viewing eye, but not aligned with it [@pirdankar2016influence]), so
  a conjugate estimate averages one eye doing the task with one eye not looking at the stimulus.`
- The same claim in comments, comment-only, neither module welfare-critical: `wl_xcon/run.py` (the docstring
  near line 62, "the non-viewing eye drifts") and `wl_xcon/task.py` (the `#:` comment near line 238): "drifts"
  → "deviates to its phoria".

**D6. WEL-22 (welfare doubt 4).** S0's inference about the behavior lamps' glow omits that 850 nm itself is
visible at sufficient power and that the LP830 passes it.
- `docs/superpowers/specs/2026-08-31-S0-hosts-and-hardware-design.md` §7.7, "A visible-cut filter on each
  emitter". Wrong: `It cuts the LED's shorter wavelengths, which is where a faint red glow comes from
  (INFERENCE).` Correct: `It cuts the LED's shorter wavelengths, where part of a faint red glow comes from
  (INFERENCE). It passes 850 nm itself, which the human fovea detects at sufficient power
  [@sliney1976visual], so the filter only trims the tail; the darkness check at the eye position (below) is
  the safeguard.`

**D7. TSK-48 (task doubt 8).** The demo spec's uncited hand latency is likely low.
- `docs/superpowers/specs/2026-10-06-demo-mode-design.md` §14 item 17. Wrong: `a hand takes roughly 0.6-1 s
  from onset to a landing where a monkey's eye takes about 0.25 s`. Correct: `a hand takes a second or more
  from onset to a landing (a mouse positioned on text in a mean 1.29 s, SD 0.42, after 0.36 s of homing
  [@card1977evaluation, Table 2, p. 11]) where a monkey's eye takes about 0.25 s (saccadic reaction times
  about 200 ms with no gap [@fischer1983saccadic])`. The conclusion it supports is unchanged.

**D8. REC-20 (recording doubt 2).** Three citation errors in what the documents carry about closed-loop
latency.
- `docs/research/spikeglx-realtime.md`, "Latency". Wrong: `**Independent measurement**: OP-GLX ([bioRxiv
  2026.03.04.709636](https://www.biorxiv.org/content/10.1101/2026.03.04.709636)), a MATLAB client on simulated
  recordings: minimum ~6.5 ms end-to-end round trip.` Correct: `**OP-GLX** (preprint, doi
  10.64898/2026.03.04.709636 [@slack2026opglx]; the 10.1101 form does not resolve, 2026-10-08) gives a minimum
  of ~6.5 ms end to end, which it attributes to the SpikeGLX API's round trip, citing the SpikeGLX MATLAB SDK,
  not to a measurement of its own (Discussion); that SDK's README shows only the C++ histogram near 2 ms
  [@karsh2026spikeglxcppsdk], so the 6.5 ms's origin is untraced and it is not quoted as measured.` The next
  line, "Treat this as the realistic bound for non-C++ clients", is struck.
- Same file, the fallback item. Wrong: `9.241 ms median / 13 ms max, end-to-end, 384 channels`. Correct:
  `median 9.2 ms, SD 1.3 ms, maximum 13 ms round trip for one Neuropixels probe, as the Falcon Output page reads
  on 2026-10-08 [@openephys2026falcon]; the "9.241 ms ... 384 channels" read on 2026-08-30 is no longer there`.
- `docs/research/landscape.md`, the SpikeGLX and Open Ephys rows: the same two corrections (the OP-GLX link
  and "independent MATLAB measurement ~6.5 ms min"; "9.241 ms median, SD 1.302 ... all 384 ch").
- `docs/pitfalls.md` P5. Wrong: `(published 9.241 ms median, 384 ch)`. Correct: `(published median 9.2 ms,
  maximum 13 ms, one probe, as read 2026-10-08 [@openephys2026falcon])`.

**D9. Triage 1.** The 32-inch panel at 57 cm, replaced by the PG27UCDM at 50 cm (PI, 2026-09-27 and
2026-09-28; S0 §5.1-§5.2).
- `docs/superpowers/specs/2026-08-31-spec-map.md`, S0's "Decided". Wrong: `a 32-inch-class 16:9 flat OLED with
  the specific model deferred to a tandem panel expected late 2026, plus a bench panel bought now so M1/M2 are
  not blocked on a launch; the display geometry as a formula with 57 cm as the build target`. Correct: `the
  ASUS PG27UCDM, a 26.5-inch tandem QD-OLED at 4K/240 (PI, 2026-09-27), plus a bench panel so M1/M2 are not
  blocked; the display geometry as a formula, the screen fixed 50 cm from the eyes in both setups (PI,
  2026-09-28)`.
- `docs/superpowers/specs/2026-08-31-controller-architecture-design.md` §16 item 3 (a struck-through record):
  append `(Superseded: the 26.5-inch PG27UCDM, PI 2026-09-27, at 50 cm in both setups, PI 2026-09-28; S0
  §5.1-§5.2.)`

**D10. Triage 2.** Twelve hours where the out-of-cage limit is meant; eight since the PI's correction of
2026-10-01 (S8 §5.2 item 4). Engineering call: storage and soak keep twelve as a stated margin, as P9 §5 already
reads ("longer than any session can now be").
- `docs/M0-REVIEW.md` §3.1 item 4: after "out of cage to back in cage, twelve hours", add `(corrected to
  eight by the PI on 2026-10-01, the institution's limit; S8 §5.2 item 4)`.
- `docs/superpowers/specs/2026-08-31-S0-hosts-and-hardware-design.md`: in §7.6's "Storage: the arithmetic",
  add once `Twelve hours is a sizing margin over the eight-hour out-of-cage limit (PI correction, 2026-10-01),
  as is bring-up check 2's twelve-hour run.`; §5.1's Dell note, wrong `a 12-hour session would meet it`,
  correct `any session past four hours would meet it`; §7.2's C16 row, §7.5 ("for 12 hours (bring-up check
  2)"), §7.8 and §7.9's twelve-hour runs: append `(a margin over the eight-hour limit)`.
- `docs/superpowers/specs/2026-09-27-P9-camera-system-design.md` §6 check 2: `8 cameras at 200 fps for 12
  hours` → append `(a margin over the eight-hour limit, §5)`; P9 §5's sentence "still use twelve" then reads as
  settled.
- `docs/backlog.md` XC-085: "8 cameras for 12 hours" → "8 cameras for 12 hours, a margin over the eight-hour
  limit".

**D11. Triage 9.** The 0.05 s tracker-loss grace and staleness ceiling are the OpenIris paper's stall maximum
on its authors' PC, not a figure measured on our rig (S5 §4, §10 item 2: frozen only after V3(a)).
- `docs/superpowers/specs/2026-08-31-S1a-vocabulary-design.md` §13. Wrong: `defaulting to P6's **measured**
  stall maximum for OpenIrisDPI (~2% of frames >= 10 ms, max ~50 ms)`. Correct: `defaulting, as a placeholder
  until V3(a) measures ours (S5 §4), to the OpenIrisDPI paper's reported stall maximum on its authors' PC (~2%
  of frames >= 10 ms, max ~50 ms [@ressmeyer2026openirisdpi], §3.1)`.
- `docs/superpowers/specs/2026-10-06-demo-mode-design.md` §3.3. Wrong: ``the 50 ms staleness rule
  (`eye.Tracker.staleness`)``. Correct: ``the 50 ms staleness placeholder (`eye.Tracker.staleness`, the
  OpenIrisDPI paper's stall maximum until V3(a) sets ours)``.
- Comment-only, neither module welfare-critical: `wl_xcon/eye.py` (`Tracker.staleness`'s `#:` comment, "P6's
  **measured** worst OpenIrisDPI frame time") and `wl_xcon/task.py` (the `Tolerances` docstring, "P6's
  **measured** stall maximum"): "measured" → "the OpenIrisDPI paper's reported", plus "a placeholder until
  V3(a)".

**D12. Triage 14, and S4 §3 found with EYE-10.** The calibration grid is thirteen targets (S5 §2 amended
2026-09-05; engine spec §12 item 2), not a 3×3.
- `docs/superpowers/specs/2026-08-31-S9a-console-design.md` §2.2. Wrong: `The calibration grid (S5 §7, a 3×3 —
  never a ring)`. Correct: `The calibration constellation (S5 §2: thirteen targets, a 3×3 plus four
  intermediates, never a ring)`.
- `docs/superpowers/specs/2026-08-31-S4-stimulus-presentation-design.md` §3, "Consequence for the calibration
  block". Wrong: `its 3×3 grid (S5 §2)`. Correct: `its thirteen-target constellation (S5 §2)`. (§3's
  zero-disparity rule for the stereoscope is class 3's L4.)

**D13. Triage 15.** The photodiode patch candidate.
- `docs/superpowers/specs/2026-08-31-S3-sync-integration-design.md` §10 item 3. Wrong: `**candidate found**
  (central strip from the nasal clip)`. Correct: `**decided**: the bottom strip the stereoscope's mask makes
  (3.22 cm at the ±12° mask), and in direct view under each sensor's housing (S3 §8, S4 §7, optics drawing §5,
  direct-view spec §4); the central strip is the fallback (optics drawing §8 items 3-4)`; the rest of the row
  (confirm with wl-sync, XC-090; verify dark at bring-up) stays.

**D14. Triage 16.** The protocol that photometers the panel halves.
- `docs/design/architecture.md`, "The display: direct view, and stereo as viewports". Wrong: `is photometered
  in V1.` Correct: `is photometered in V9 (validation.md; V1 is display timing).`

**D15. Triage 19.** The approaching-limit warning's default.
- `docs/superpowers/specs/2026-08-31-S9-operations-console-design.md` §3. Wrong: `The threshold is
  configurable and its default is a proposal, not a settled figure.` Correct: ``The threshold is
  configurable; its default, 30 minutes (`welfare.WARN_WITHIN_DEFAULT`, 1,800 s), was accepted by the PI on
  2026-09-20 as a starting value (S8 §5.2 item 4) and is derived from no measurement.``

---

## Class 3: defect or gap, backlog line

Lines in `docs/backlog.md`'s format, for the section named. L4, L7, L8 and L9 are the earlier triage's proposed
lines, merged with the literature where it bears on them and corrected where the passages were re-read.

**L1. DISP-11 (display doubt 4).** Section: Deferred defects. Nothing checks a temporal sine against the
sampling limit; it is the example the brief names.
```text
- **XC-???** A temporal sine (a drifting or counterphase grating's `tf`, or any per-frame-sampled modulation) is not checked against half the session's refresh rate, so one at or above 60 Hz in the 120 Hz mode (120 Hz at 240) reaches the animal as a lower, aliased frequency, a drift possibly reversed, and is recorded at its nominal value (Shannon 1949, Theorem 1; Dimigen & Stein 2026); refuse it at load at each rate the task may run at, as square-wave flicker without whole frames is refused, amend engine spec §6 item 4's "any frequency", and say in the review report that a sample-and-hold display attenuates a sampled sine's fundamental by about sinc(f/f_refresh) (0.90 at 60 Hz on 240 Hz, arithmetic). — 2026-10-08, [engine spec §6](superpowers/specs/2026-10-07-engine-design.md#6-when-n3-nr3), the reference library's display backfill (DISP-11) — waits on: nothing
```

**L2. DISP-01, DISP-02, DISP-13 (display doubts 2, 3 and 6, the measurement).** Section: Needs the rig. Three
OLED effects the acceptance test's sweeps would miss.
```text
- **XC-???** Add to the panel acceptance test (S0 §5.4, validation V9) three OLED effects its sweeps would miss, each measured on the PG27UCDM before its numbers are trusted: gray-to-gray transitions near peak in every mode, not only black and white (a QD-OLED TV's 204 to 255 took up to 21 ms against a 1.96 ms average, Abu Haila et al. 2025); a small bright patch's luminance over its first 500 ms (dynamic dimming of up to 5% whatever the uniform-brightness setting) and whether that setting works under Linux (Dimigen & Stein 2026); and the local after-image a high-contrast stimulus held for a minute leaves (0.7 to 1.5% of peak, fading over minutes, Dimigen & Stein 2026), which five-minute trials and the continuous mode's adapters meet. — 2026-10-08, [S0 §5.4](superpowers/specs/2026-08-31-S0-hosts-and-hardware-design.md#54-panel-acceptance-test--written-now-before-the-panel-exists), the reference library's display backfill (DISP-01, DISP-02, DISP-13) — waits on: nothing to amend the test; the panel to run it (XC-070)
```

**L3. STE-07 (stereo doubt 2a).** Section: Features not yet planned. The disparity sign check as specified
can confirm the wrong sign.
```text
- **XC-???** Specify the disparity sign check (engine spec §5 item 4, S4 §10 item 6) as crossed disparity steps, or uncrossed steps under about 1.5° applied just after a saccade: in rhesus, crossed steps always drive convergence, but larger or later uncrossed steps drive convergence too rather than divergence, so a check with a large uncrossed step can "confirm" the wrong sign (Busettini, Miles & Krauzlis 1996). — 2026-10-08, [engine spec §5](superpowers/specs/2026-10-07-engine-design.md#5-where-n2-nr5), the reference library's stereo backfill (STE-07) — waits on: engine build T
```

**L4. Triage 5, STE-22 (stereo doubt 3), EYE-10 (S4 §3).** Section: Debt. The triage's line named "controller
architecture §11.3", which is the console; the passage is §8.2, and S0 §5.2 and S4 §3 were missing.
```text
- **XC-???** Passages beyond S4 §10 (which engine spec §22 lists) still hold the stereoscope to a Nonius or vernier alignment residual against a tolerance, or calibrate it at zero disparity against one cyclopean target set: S0 §5.2, controller architecture §8.2, S4 §3, S9 §2 and §6, optics drawing §4.5 and §7, roadmap M5 and validation V9; the PI replaced them with two monocular grids, each point's offset between the eyes reported and the experimenter's acceptance recorded (2026-10-07, engine spec §12 item 3), which is the published macaque procedure (Cox et al. 2019; Dougherty et al. 2021), whereas a nonius is a perceptual report an animal cannot give (Larson 1982). — 2026-10-08, [engine spec §12](superpowers/specs/2026-10-07-engine-design.md#12-calibration-procedures-and-test-screens-n9-nr5), the stereo and eye backfills (STE-22, EYE-10) — waits on: engine build T
```

**L5. EYE-07, EYE-08 (eye doubt, the reach part).** Section: Features not yet planned. The DPI map's
second-order rung rests on targets the published tracker cannot see; the fit cannot tell.
```text
- **XC-???** With P4 visible to about 10° of gaze at the paper's pupils (Ressmeyer et al. 2026, §2.2), direct view's constellation leaves five targets inside the DPI's reach (the center and the four intermediates at about 7 to 8°), one fewer than the second-order map's six coefficients, and conditioning, being scale-invariant, cannot see on which targets P4 was lost; the DPI fit takes only targets where P4 was tracked and records the rung that leaves, as part of the fallback's design. — 2026-10-08, [S5 §2](superpowers/specs/2026-08-31-S5-eye-tracking-design.md#2-a-ring-of-calibration-targets-cannot-fit-a-second-order-map), the reference library's eye backfill (EYE-07, EYE-08) — waits on: XC-006; P4's reach on our animals (XC-081)
```

**L6. WEL-17 (welfare doubt 5).** Section: Features not yet planned. A real gap in the stimulation bounds,
recorded for the stimulation design rather than asked.
```text
- **XC-???** The stimulation bounds (S8 §4; controller architecture §10.4) are per delivery and per channel, with no bound on charge delivered on several channels at once, though in chronic macaque microstimulation high synchronous current through many electrodes caused rhythmic muscle contractions and the authors limited how many fired together (Rajan et al. 2015); bound simultaneous multi-channel delivery in XC-010's design (welfare-critical). — 2026-10-08, [S8 §4](superpowers/specs/2026-08-31-S8-session-management-design.md#4-the-bounded-config), the reference library's welfare backfill (WEL-17) — waits on: XC-010
```

**L7. Triage 6 and 7, with color doubt 1 (COL-03, COL-04).** Section: Debt. The passages describe today's code
(refusal without a calibration) until build B lands, so they change with it; engine B's plan (Task 15) names
neither, and the cheapest route is to add them to its Step 1.
```text
- **XC-???** S1a §12, pitfall P19 and XC-071 still say color without a measured calibration is refused, that chromatic tasks wait on a photometer, and that the luminosity function must be a macaque's; since engine build B the default sRGB calibration loads such tasks in training and piloting with a warning and refuses them in recording (PI, 2026-10-07 and 2026-10-08), the instrument is a spectroradiometer (engine spec §12 item 1), and isoluminance is the named CIE 10° observer's V_F,10 (PI, 2026-10-08, A2 Q5) with a per-animal null declined (2026-10-07); reword all three, keeping P19's risk with its sources (Dobkins et al. 2000; Conway 2014) and saying a methods section states the observer. — 2026-10-08, [S1a §12](superpowers/specs/2026-08-31-S1a-vocabulary-design.md#12-added-2026-08-31-after-review--what-the-graph-could-not-see), disagreements triage items 6 and 7 — waits on: engine build B
```

**L8. Triage 13.** Section: Debt. As the triage proposed.
```text
- **XC-???** architecture.md's interface section and controller architecture §3.2, §8.5 and §9.4 still say audio output is host-side and not in copper; the engine plays sound from two analog outputs of the task PC's PCIe-6343 started by the task-patch edge (engine spec §9.1, PI 2026-10-07), pending a line-out from wl-sync; S4 and S6 are already in the engine spec §22. — 2026-10-08, [engine spec §9](superpowers/specs/2026-10-07-engine-design.md#9-media-and-sound-n6-nr5-nr6) — waits on: engine build G
```

**L9. Triage 17.** Section: Deferred defects. A gap in the engine spec, an engineering call (a stuck task's
trial run again would hang again), not animal-facing.
```text
- **XC-???** State in the engine spec §16.2 whether a trial that reaches the 5-minute cap (recorded as hang, outcome none) is repeated; the notes' §3 Batch 4 says it ends as a fault, §6 item 8 says hang, and a fault repeats by default; the proposed call is not repeated, recorded and flagged. — 2026-10-08, [engine spec §6](superpowers/specs/2026-10-07-engine-design.md#6-when-n3-nr3) — waits on: engine build C
```

**L0. Triage 8.** No line: the four reference tasks' luminance bounds (100 → 80 cd/m², PI 2026-10-08, build B
Q1) are edited by engine B's plan, Task 4 (its file table: "luminance bounds 0-80 (Q1-A)"). Add the
triage's fallback line only if build B is deferred.

---

## Class 4: PI decision, ask now

**None.** No doubt is at once science- or animal-facing, unsettled by a dated decision, and decisive for builds
B, C or E or the rig work in hand. The candidates fell out as follows: the color doubts (COL-03, -11, -15/16,
-31) disagree with decisions the PI made on 2026-10-07 and 2026-10-08 knowing the literature (class 1); the
welfare doubts are a label, a reading of a rule he set, a document's inference and a future stimulation bound
(classes 1 to 3); the display doubts change V9's content, which is engineering (class 3); the timing of the five
genuine questions is a named later step (class 5).

---

## Class 5: PI decision, ask later

Asked in the UI, in plain terms, at the named moment. Two questions already drafted in `disagreements-triage.md`
are asked at the same moment as Q1 and Q2: **item 10** (a look away from the target before its hold ends:
wrong answer or broken hold) and **item 12** (which contrast convention the staircase's contrast uses).

**Q1. TSK-34 (task doubts 1 and 3; triage 11): `adaptive_detection`'s staircase and catch trials.**
Moment: the reference tasks made right (engine spec §25; CHECKPOINT's order, step 3).
- **(a)** "In the contrast staircase, when the monkey doesn't respond to the target at all, should the next
  trial get easier (as after a wrong answer), or should that trial be ignored, as the task does now?"
  - **A. A miss makes it easier (recommended).** The engine's default rule (engine spec §15 item 3, PI
    2026-10-07) and the staircase's own theory, which classifies every answered trial as a success or a
    failure [@levitt1971transformed, p. 471]; in detection a miss is the negative answer
    [@stanislaw1999calculation; @luo2015neuronal]. Cost: one line in `next_params`. A disengaged animal then
    pushes contrast up; build C's disengagement alert covers long runs of misses.
  - **B. Ignore misses (today).** Cost: none now. The track descends only on trials the animal chose to
    answer, so the threshold is biased low and mixes contrast with engagement.
- **(b)** "Should the detection task include trials with no target (catch trials), so the record can tell 'did
  not see it' from 'did not want to answer'?"
  - **A. Yes, a declared share (e.g. 20%) with an explicit blank (recommended for recording).** Gives a
    false-alarm rate, so sensitivity and criterion separate (d′) [@stanislaw1999calculation;
    @luo2015neuronal]. Cost: about a fifth fewer target trials, and a reward rule for correctly holding
    fixation on a blank.
  - **B. No (today).** Cost: none. The threshold is a hit-rate threshold, moving with willingness to respond as
    well as with sensitivity [@luo2015neuronal; @pelli2013measuring]; the methods say so. Adequate for
    training.
  - Context: with equal up and down steps, "near 71%" is approximate [@garciaperez1998forcedchoice] (N15).

**Q2. TSK-39 (task doubts 5 and 6; engine spec §25's `item_window`): `visual_search`'s choice windows and the
color sequence.** Moment: the reference tasks made right.
- **(a)** "In visual search, how big should the zone around each item be where a landing gaze counts as
  choosing it? Today it is 0.5-1° in radius for items 5-14° out; your own pop-out papers accepted 2-5° around
  the target."
  - **A. Grow with eccentricity, capped so neighbors never overlap (recommended).** Accurate but scattered
    landings stop being scored as misses, since saccade scatter grows with eccentricity
    [@opstal1989scatter]; matches [@westerberg2020priming; @westerberg2023feedforward]. Cost: a rule in the
    task and in the overlap check, and fewer items allowed on small rings (twelve on a 5° ring sit 2.59°
    apart).
  - **B. Keep 0.5-1° fixed.** Cost: none; far items' scattered landings score as no response or wrong.
  - **C. One larger fixed window (e.g. 2°), fewer items on small rings.** Cost: limits set size near the
    fovea.
- **(b)** "Should the target and distractor colors swap at random trial to trial, or stay the same for runs of
  trials, as in your priming work?"
  - **A. Held for runs (e.g. 5-50 trials) [@westerberg2020priming].** Priming of pop-out becomes a controlled
    factor [@bichot2002priming]. Cost: a block structure in the task.
  - **B. Random per trial, sequence balanced.** Cost: none beyond build C's orders; priming varies trial to
    trial and must be analyzed out.
  - **C. Declared per block, both available.** Cost: both A's and B's.
  - No option is clearly better; it depends on the experiment. The realized sequence is recorded either way
    (engine spec §16 item 4). Context: shape pop-out is weaker than color (N16).

**Q3. EYE-11 (eye doubt): `calibration`'s `cal_hold`.** Moment: engine build T's plan (the session-start
calibration), or the reference tasks made right if that comes first (engine spec §25 names it there).
- "How long must the monkey hold its gaze on each calibration target before the fixation counts toward the eye
  map? It starts at 0.3 s today (adjustable live, 0.1-2 s); S9 suggested 0.5 s; the two published macaque
  procedures held 0.6 s and 0.75 s."
  - **A. Start at 0.6 s and fit from the hold's last 0.3 s (recommended).** Published practice: 600 ms within
    a 1.4° box [@ressmeyer2026openirisdpi, §2.4]; 750 ms with the last 300 ms averaged [@kimmel2012tracking].
    Fitting the late part also skips the DPI's ringing just after the landing saccade
    [@ressmeyer2026openirisdpi, §4.1]. Cost: a longer calibration and a harder start for a naive animal; the
    operator can lower it live.
  - **B. Start at 0.5 s (S9).** Cost: a middle value with less settling time.
  - **C. Keep 0.3 s.** Fastest; the fit then averages over a period that can include post-saccadic ringing.

**Q4. REC-15 (recording doubt 1): the microphone's bandwidth.** Moment: when the ask to wl-sync for the audio
line-out (engine spec §21) is written, beside the lever-line question (both are at the wl-sync board; CHECKPOINT
lists the cross-repo asks as next, so this may be this week).
- "Will the lab analyze the sound of the monkeys' calls (their pitch and spectrum), or only detect and time
  them? The sync box filters the microphone at about 12 kHz on the premise that calls sit below 10 kHz, but
  rhesus screams have fundamentals of 3-10 kHz, so their harmonics are cut."
  - **A. Detect and time only (recommended unless vocal analysis is planned).** Keep wl-sync's 40 kHz scan and
    12 kHz filter, and ask wl-sync to correct its premise. Cost: none.
  - **B. Analyze spectra on the recording card.** Raise the filter to about 20 kHz and the microphone's scan to
    at least 44.1 kHz, the rate the cited acoustic study used [@schwartz2022vocal]. Cost: a board change, and
    the card's whole scan rate rises with it (S6: the scan rate is set by the microphone).
  - **C. A separate audio recorder (96 kHz or more) synchronized through a sync-box line.** Cost: a device and
    an input line.
  - Sources: screams' F0 3-10 kHz, coos analyzed at 44.1 kHz [@schwartz2022vocal]; noisy screams broadband
    with a high-frequency component [@rendall1998role].

**Q5. STE-20 (stereo doubt 1): the stereoscope's smallest eye separation.** Moment: before the stereoscope's
carriage is bought or machined (optics drawing §7; XC-083).
- "The stereoscope adjusts for eye separations of 30-38 mm, and the rig refuses an animal outside that.
  Measured adult rhesus in the literature are 30-36 mm, but one paper says 'typically 25-35 mm'. Will any
  animal on the stereoscope be small: a juvenile, a small female, or another species such as a cynomolgus?"
  - **A. Adults only: keep 30-38 mm.** Cost: none.
  - **B. Extend down to 25 mm (recommended if unsure).** The mirrors are sized for the largest separation, so
    smaller ones use less of them (optics drawing §4.3); the near mirror needs about 13 mm more travel (it
    sits at E(1 + 1/tan θ), a coefficient of about 5.3, arithmetic), and `tasks/rig.py`'s
    `half_ipd_range_cm` follows. Cost: small if designed in; a re-machined carriage if not.
  - **C. Measure the lab's animals first (XC-082) and set the range from them.** Cost: waits on the animals.
  - Sources: "typically 25-35 mm", unsourced there, and 34 mm measured [@walton2019rhesus]; 35 and 32 mm
    [@hadjidimitrakis2011fix]; 33.2 and 33.1 mm [@ferrea2025frontal]; 31 and 30 mm [@wirth2017gazeinformed];
    about 35 and 36 mm implied [@cumming1999binocular].
