# Engine A2 (color): research groundwork

> **Corrected 2026-10-08 after an independent check (79 numbered claims, one of them listed twice: 66
> confirmed, 5 wrong, 7 unverified):** sources for the corrections were fetched 2026-10-08 (see Sources).
> - N3 and Q1-D: red-green 0.1 (L +10%, M −22%) is just inside the narrowband display's ceiling, not out of gamut everywhere.
> - N4: now says what 0.1 means under N4 (Δl_MB = 0.1: L ≈ +14.5%, M ≈ −32%); the old cell restated N1's stimulus.
> - Q2: leak figures qualified (+50% S request, two synthetic displays); A's matrix is used outside its CIE definition; B's L/M cost added; recommendation A → toss-up.
> - §2 and Q1: Psychtoolbox `DKLDemo.m`'s per-axis scaling (N5, Q1-E) and plain cone contrast (N6, Q1-F) added; DKLDemo bullet corrected.
> - Q5: per-subject measured isoluminance added as option D; B's "about 2%" is −1.9 to −2.2%, for a +50% S stimulus under CIE 1931 ȳ.
> - §1.2 and Q3-A: the CIE LMS tables are 5 nm only, how 1 nm values would be made; record the metadata sha256 (both LMS pages' MD5s are stale).
> - §1.2: the LMS 2° CSV has at most 7 significant figures, not 10.
> - §2, §3, §4: the synthetic displays are stated (Gaussian, center/FWHM, scaled to D65 in CIE 1931 xy, mid-gray = linear 0.5); the numbers depend on it.
> - §5: Schnapf et al. 1988 does adjust for pre-retinal filtering (to the human cornea); what it lacks is a macaque-vs-human comparison.
> - §2: Brainard's Eq. A.4.2 and √3 are on p. 568, the angular-coordinate warning on p. 574.
> - Sources: Stockman 2019 is Curr Opin Behav Sci 30:87-93 (UNVERIFIED removed).
> - Minor: N2 ratio 1.74; sRGB least-squares M-isolating 0.215; "same on every rig" needs the background in cone coordinates; cvrl HTTPS timed out; He 2021 "consistent with"; unused header references dropped.

Researched 2026-10-07 by an agent for the A2 brainstorm, saved by the controller; sources fetched
2026-10-07. Numbers marked **computed** come from scripts run on the published tables (kept outside the
repository); they are not measurements of the lab's panel. Claims resting only on an abstract say so.
Full texts not opened: Derrington, Krauskopf & Lennie 1984; Lindbloom-Brown 2014; CIE 170-1 and 170-2
themselves (paywalled or blocked).

## 0. Corrections to current repo text

1. **Spec §7.9 and the notes (N§R5) attribute "virtually identical" to Baylor, Nunn & Schnapf.** The
   sentence is from **Schnapf, Kraft, Nunn & Baylor (1988)**, Vis Neurosci 1:255-261,
   https://doi.org/10.1017/S0952523800001917 (the Cambridge URL in the notes points to it). Its
   abstract compares red and green cones from one human retina with macaque cones; it says nothing
   about S cones (the spec's paraphrase, "macaque and human L and M cone spectra", omits that the human
   cones came from one retina). **Baylor, Nunn & Schnapf (1987)** is a different paper: J Physiol
   390:145-160, https://doi.org/10.1113/jphysiol.1987.sp016691 (§5).
2. **PMC10946592 is right for its claim**: Stockman & Rider (2023), Color Res Appl 48:818-840,
   https://doi.org/10.1002/col.22879; its abstract says the CIE sanctioned Stockman & Sharpe.
3. **The science review's §7(b) ceilings hold up (computed, mid-gray, on the display models of §3):**
   isoluminant L-cone contrast 0.06-0.11, pooled cone contrast 0.15-0.26; S-cone contrast 0.86-0.98.
   UNVERIFIED for the lab's panel.
4. **cvrl's pages still call the CIE XYZ_F functions "proposals"**; CIE 170-2:2015 published them (the
   CIE datasets cite its Tables 10.7a and 10.8).

## 1. Cone fundamentals data

### 1.1 cvrl.org

Pages http://www.cvrl.org/cones.htm, /ciepr.htm, /ciepr8dp.htm (plain HTTP; HTTPS timed out); files
returned by form POSTs to `conerequest_ss10.php` and `conerequest_ss2.php` (and `_8dp` variants).

| Set | Linear, energy | Log, energy | Log, quanta | Steps |
|---|---|---|---|---|
| Stockman & Sharpe 10° (= CIE 2006 10°) | `linss10e_{5,1}.csv` | `ss10e_*` | `ss10q_*` | 5, 1, 0.1 nm |
| Stockman & Sharpe 2° (= CIE 2006 2°) | `linss2_10e_*` | `ss2_10e_*` | `ss2_10q_*` | 5, 1, 0.1 nm |
| 9-significant-figure versions | `linss10e_1_8dp.csv` works | — | — | — |

- The 2° 9-sf endpoint returned a PHP parse error on 2026-10-07 (still on 2026-10-08).
- Range 390-830 nm; S blank above 615 nm (unmeasured; cvrl says it can be set to zero).
- Linear tables 6 significant figures; log tables 5 decimal places; 0.1 and 1 nm tables are cubic-spline
  interpolations of the 5 nm data.
- Each function peaks at 1. One-nm peaks: 10° L 569, M 541, S 448 nm; 2° L 570, M 543, S 442 nm.
- Both sets come from the Stiles & Burch 10° color-matching data (cvrl `ss2_10.htm`); the 2° set raises
  macular pigment peak from 0.095 to 0.35 and photopigment optical density from 0.38 to 0.50 (L, M) and
  0.30 to 0.40 (S).
- Use the energy tables for spectroradiometer power spectra; cvrl's MacLeod-Boynton page notes the
  coordinates come out identical from either.
- SHA-256 of the downloads: `linss10e_1` 36ab758d…, `linss2_10e_1` 98459f0a…, `linss10e_1_8dp` 59148195….

### 1.2 Official CIE datasets (cie.co.at/data-tables)

| Dataset | DOI | File | Range, step | Source table |
|---|---|---|---|---|
| LMS 10° | 10.25039/CIE.DS.nxsqeri8 | `CIE_lms_cf_10deg.csv` | 390-830 nm, 5 nm only; 6 significant figures | CIE 170-1:2006 Table 6.2 |
| LMS 2° | 10.25039/CIE.DS.tijidesg | `CIE_lms_cf_2deg.csv` | 390-830 nm, 5 nm only; at most 7 significant figures (up to 10 decimal places) | CIE 170-1 Table 6.7 |
| XYZ_F 2° | 10.25039/CIE.DS.548rw69q | — | 1 nm | CIE 170-2:2015 Table 10.7a |
| XYZ_F 10° | 10.25039/CIE.DS.dm6qiig7 | — | 1 nm | CIE 170-2 Table 10.8 |

The site also lists cone-based V(λ) (2°, 10°) and MacLeod-Boynton 2°; blank cells are NaN. Quirks: the
CIE 10° L value at 390 nm is 0.000407615 where cvrl has 0.000407619 (9-sf 4.07619067E-04), every other
5 nm entry agreeing to 6 significant figures. Both LMS datatable pages show stale MD5s (2° checked
2026-10-08): 10° page c92c94a7…, file served c2e606fd…, matching metadata v2 (sha256 bd64f1f6…); 2° page
27c74cc0…, file served dba2e9d1…, metadata sha256 f48160ed…. Whatever is bundled should record its
source and the metadata JSON's sha256, not the page's MD5.

**The LMS CSVs are 5 nm only** (checked 2026-10-08). One-nm values would be a derived table, made one of
two ways (computed 2026-10-08): linear interpolation, the method the CIE metadata declares, which differs
from cvrl's 1 nm spline tables by up to 0.31% (L), 0.38% (M) and 0.78% (S) of peak; or exact 1 nm LMS
recovered from the CIE's 1 nm XYZ_F datasets by inverting the published LMS-to-XYZ_F matrix (§1.4; max
error 2.4e-7).

### 1.3 Terms of use and license (not legal advice)

- **cvrl.org: no license grant found.** The main page footer says the data are "provided free of charge
  as a service to the vision science community", believed correct when posted, use at the user's
  responsibility, with a copyright notice 1995-2026 (Color and Vision Research Labs). Nothing addresses
  redistribution: bundling cvrl tables is UNVERIFIED as permitted (contact a.stockman@ucl.ac.uk).
- **CIE datasets: CC BY-SA 4.0**, per each dataset's metadata rights field (the HTML page shows a
  recommended citation and "Copyright 2026 CIE").
- **Creative Commons FAQ** (creativecommons.org/faq, paraphrased): CC material may sit in a collection
  whose license does not change it; CC 4.0 covers databases, including the EU database right (relevant at
  KU Leuven); attribution and share-alike bind only where copyright or database right restricts the use
  and the material is shared; whether data values are protected depends on jurisdiction; CC advises
  against CC licenses for software (BY-SA 4.0 can flow one way into GPLv3).
- **Reading for an Apache-2.0 repository (UNVERIFIED):** an unmodified CSV kept as its own file, labeled
  CC BY-SA 4.0 with attribution, can sit in the repository as separately licensed material; a changed
  table (resampled, renormalized, S zero-filled above 615 nm, converted to log) is an adaptation and
  carries BY-SA when shared.
- **Precedent, not permission:** colour-science (BSD-3-Clause, develop 248121e3) bundles the Stockman &
  Sharpe 2° and 10° sets citing cvrl; Psychtoolbox bundles `T_cones_ss2.mat`, `T_cones_ss10.mat`,
  `T_xyzCIEPhys2.mat`, `T_xyzCIEPhys10.mat`; PsychoPy bundles Smith-Pokorny in `calibData.py`.
- **Alternative to bundling:** Stockman & Rider (2023) give closed-form formulae (360-850 nm) that per
  their abstract reproduce the CIE 2° and 10° tables with little error, with a Python program whose
  license is UNVERIFIED (link stripped in the PMC text).

### 1.4 CIE 170-1:2006 and 170-2:2015

- **CIE 170-1:2006** (DOI 10.25039/TR.170-1.2006; ISBN 978 3 901906 46 6), per its abstract: cone
  fundamentals for 1°-10° fields from the Stiles & Burch 10° data, adjusted for lens, macular pigment and
  photopigment density; 2° and 10° tabulated at 5 nm, with age- and field-size-dependent densities.
- **CIE 170-2:2015** (DOI 10.25039/TR.170-2.2015) adds a cone-based V(λ) from L and M only,
  MacLeod-Boynton coordinates, and XYZ_F.
- **Stiles & Burch 10° RGB to LMS10, up to scale** (Stockman 2019, Eq. 3), applied to (r̄10, ḡ10, b̄10):
  l (2.846201, 11.092490, 1); m (0.168926, 8.265895, 1); s (0, 0.010600, 1).
- **LMS to XYZ_F** (energy, peak-normalized; cvrl equation images and Stockman 2019 Eqs. 4-5):
  - 2°: x̄F = 1.94735469 l̄ − 1.41445123 m̄ + 0.36476327 s̄; ȳF = 0.68990272 l̄ + 0.34832189 m̄;
    z̄F = 1.93485343 s̄.
  - 10°: x̄F,10 = 1.93986443 l̄10 − 1.34664359 m̄10 + 0.43044935 s̄10; ȳF,10 = 0.69283932 l̄10 +
    0.34967567 m̄10; z̄F,10 = 2.14687945 s̄10.
  - **Checked (computed):** on cvrl's 1 nm tables they reproduce `lin2012xyz10e_1_7sf.csv` within a
    relative 4.7e-7 (10°; 2° 3.3e-4, limited by the 6-sf input) and the CIE datasets within 3.1e-5
    absolute; the three functions integrate equally for an equal-energy white (118.5181 at 10°,
    113.0423 at 2°).
- **Cone-based luminosity and MacLeod-Boynton** (cvrl `mb2`, `mb10`): V_F = 0.689903 l̄ + 0.348322 m̄
  (2°); V_F,10 = 0.692839 l̄10 + 0.349676 m̄10 (10°); l_MB = 0.689903 l̄ / V_F, m_MB = 0.348322 m̄ / V_F;
  s_MB = 0.0371597 s̄ / V_F (2°), s_MB,10 = 0.0554786 s̄10 / V_F,10 (10°).
- **XYZ_F is not CIE 1931 XYZ**: x̄F was only optimized so that xF, yF chromaticities resemble the 1931
  (2°) and 1964 (10°) ones.

## 2. DKL normalizations in use

- **Derrington, Krauskopf & Lennie (1984)**, J Physiol 357:241-265,
  https://doi.org/10.1113/jphysiol.1984.sp015499 (abstract only): three axes through a white point —
  luminance at fixed chromaticity; "constant B" (S fixed, L and M vary); "constant R&G" (L and M fixed, S
  varies). Polar form: azimuth 0-180° on the constant-B axis, 90-270° on the constant-R&G axis;
  elevation −90° to +90° from the isoluminant plane.
- **MacLeod & Boynton (1979)**, JOSA 69:1183-1186, https://doi.org/10.1364/JOSA.69.001183 (abstract): a
  constant-luminance plane of cone-excitation space as a chromaticity diagram, each cone's excitation at
  fixed luminance on a linear scale.
- **Brainard (1996)**, "Cone contrast and opponent modulation color spaces", in Kaiser & Boynton, *Human
  Color Vision* 2nd ed., OSA, pp. 563-579 (color2.psych.upenn.edu/brainard/papers/Brainard32.pdf):
  - p. 564, Eq. A.4.1: cone contrast is each cone's change in excitation over its background excitation.
  - p. 568, Eq. A.4.2: pooled cone contrast √(CL² + CM² + CS²), independent of apparatus, observer and
    configuration; an achromatic modulation can reach √3.
  - p. 571: the DKL scaling constants are free; luminance contrast is the natural choice for the
    luminance axis, with none for the two color axes; DKL 1984 set each color axis to 1.0 at the
    largest in-gamut modulation on their monitor, tying the space to the apparatus; other options are
    detection thresholds (real or ideal-observer) or unit response to the mechanism-isolating stimulus
    of unit pooled cone contrast, which Brainard adopts (p. 572).
  - p. 574: angular coordinates depend on the normalization.
  - p. 575: no agreed standard — the constants and the background must be stated whenever DKL is used;
    the space assumes S cones do not contribute to luminance; results depend on how cone sensitivities
    are scaled.
  - pp. 563-568 present cone contrast itself (ΔL/L, ΔM/M, ΔS/S, no DKL scaling) as the primary
    alternative (per the 2026-10-08 check of the same PDF).
- **Psychtoolbox `ComputeDKL_M.m`** (master, 3b64237, 2021-08-21): Brainard's appendix, generalized to
  any cone fundamentals and luminosity function (L and M luminance weights from a least-squares fit of
  V(λ)); fixes two typos in the chapter (Eq. A.4.8, p. 571); scales each axis's isolating direction to
  unit pooled cone contrast. `DKLDemo.m` (master, last commit aa91f54, 2022-04-12; reread 2026-10-08)
  defaults to Stockman-Sharpe 2° with `T_ss2000_Y2` and builds two further scalings: one just inside
  the monitor gamut (`MaximizeGamutContrast`, ×0.95), and a per-axis one — luminance axis as
  isochromatic (luminance) contrast, red-green axis as the mean of |ΔL/L| and |ΔM/M|, S axis as ΔS/S —
  noting that "there are lots of ways to choose the scaling" (N5 below).
- **PsychoPy** (`colorspacetools.py` acba102, 2025-08-20; `calibTools.py` 713a139, 2026-01-29): DKL as
  (elevation°, azimuth°, radius); the docs (psychopy.org/general/colours.html) define the radius as a
  fraction of the maximal modulation along the cardinal axes (−1 to 1); `makeDKL2RGB` builds the matrix
  from Smith-Pokorny cones and Judd-Vos ȳ on the measured gun spectra and divides each column by its
  largest absolute gun value — unit radius is the largest in-range step from mid-gray, monitor-dependent.
  Without a calibration `dkl2rgb` falls back to a generic Sony Trinitron matrix with a warning. Its LMS
  space (`makeLMS2RGB`) does not divide by the background: increments, not contrasts (reading of the
  code).

**Normalizations a lab could state** (computed: Stockman-Sharpe 10°, V_F,10, mid-gray D65 background,
the display models of §3; the isoluminant M:L ratio is the narrowband synthetic display's, −2.21, against
−2.26 on the broadband one; gamut ceilings are the "Max L-M isoluminant ΔL/L" column of §3's table):

| | Normalization | DKL(l_m = 0.1) means | Same on every rig? |
|---|---|---|---|
| N1 | Pooled cone contrast (Brainard; Psychtoolbox `ComputeDKL_M.m`) | L +4.1%, M −9.1% (pooled 0.1); lum 0.1 = each cone +5.8%; s 0.1 = S +10% | Yes, with the background fixed in cone coordinates (and fundamentals, V) |
| N2 | Fraction of the screen's maximum (DKL 1984; PsychoPy) | narrowband display L +1.1%, M −2.4%; broadband L +0.6%, M −1.4% (1.74× apart) | No |
| N3 | Each axis in its own cone's contrast (lum = luminance contrast; l_m = ΔL/L with M by isoluminance; s = ΔS/S); no published implementation cited | L +10%, M −22%: beyond the ceiling of sRGB (0.063-0.067), the broadband display (0.061) and the QD-OLED TV by least squares (0.095); just inside on the narrowband display (ceiling 0.107) and on the QD-OLED TV by inverse XYZ_F,10 (0.102) | Yes, with the background fixed in cone coordinates |
| N4 | MacLeod-Boynton changes at constant luminance | Not defined well enough to evaluate. If 0.1 means Δl_MB = +0.1 (from l_MB ≈ 0.689): L ≈ +14.5%, M ≈ −32%, out of gamut on every display modeled; if it means a relative change Δl_MB/l_MB = 0.1, it is N3. (N1's 0.1 is Δl_MB +0.028.) | Yes, with the background fixed in cone coordinates |
| N5 | Per-axis contrast (Psychtoolbox `DKLDemo.m`'s third scaling: lum = luminance contrast; l_m = mean of \|ΔL/L\| and \|ΔM/M\| at isoluminance; s = ΔS/S) | L +6.2%, M −13.8% (pooled 0.151): inside the ceiling on every display modeled except the broadband one, where it sits at the ceiling (0.061) | Yes, with the background fixed in cone coordinates |
| N6 | No DKL scaling: stimuli stated directly as cone contrasts (ΔL/L, ΔM/M, ΔS/S) (Brainard pp. 563-568; He et al. 2021) | No DKL number; N1's red-green 0.1 is written (0.041, −0.091, 0) | Yes, with the background fixed in cone coordinates |

N4's earlier cell (Δl_MB +0.028) restated N1's stimulus; N5's gamut position was computed 2026-10-08 with
the check's scripts, each display at its own isoluminant ratio (0.58-0.65 of the ceiling on the
narrowband and QD-OLED models, 0.92-0.97 on sRGB, 1.00 on the broadband model). **"Same on every rig"
needs the background fixed in cone coordinates:** a background specified as D65 in CIE 1931 xy (as
`wl_xcon.photometry.D65` is) is not the same cone excitation on different panels — l_MB 0.6888 vs
0.6933 and M:L at isoluminance −2.21 vs −2.26 on the two synthetic displays (computed). Not tabulated:
threshold units (real or ideal observer; Brainard pp. 567-568, 572), which are per observer and so not
the same across rigs or subjects.

A hybrid: the luminance axis as luminance contrast (Brainard's natural choice), color axes as N1. Its
axes then carry different units (luminance contrast against pooled cone contrast), so a single gate on
the largest component — `DKL.magnitude()` against one `max_cone_contrast`, as on a2-prep — compares
unlike quantities. Along the isoluminant axis M:L cone contrast is about −2.2 (computed), consistent
with He, Taveras-Cruz & Eskew (2021), J Vis 21(7):15, https://doi.org/10.1167/jov.21.7.15 (mean human
flicker-photometry M:L about −2, individuals −6.1 to −0.7, n = 22; they used Stockman-Sharpe 2°
fundamentals, a 2° field and a (0.289, 0.315) background, so the agreement is approximate).

## 3. Cone contrast to primary weights

**The computation** (Brainard 1996 Part IV; Psychtoolbox `SensorToPrimary`, `MaximizeGamutContrast`)
[@brainard1996cone; @brainard2002display]:

1. M (3×3): column j is the cone excitation of primary j at full drive — with spectra
   M_ij = Σ_λ c̄_i(λ) P_j(λ) Δλ; without, M = T · [XYZ_R XYZ_G XYZ_B] for some XYZ-to-cone T.
2. Background excitation e_bg = M · w_bg.
3. Target e = e_bg ∘ (1 + c), c = (ΔL/L, ΔM/M, ΔS/S); a DKL color first converts to c through the stated
   normalization.
4. w = M⁻¹ · e; realizable iff every weight is in [0, 1]; each weight then goes through the channel's
   measured transfer table.
5. For a modulation ±a·d the largest a is the minimum over primaries k of (1 − w_bg,k)/|Δw_k| where
   Δw_k > 0 and w_bg,k/|Δw_k| where Δw_k < 0; check both extremes of a grating and a noise distribution's
   full range.

Assumptions to state: channels add and are independent (Abu Haila et al. 2025 measure this for consumer
OLEDs); ABL never engages; the screen is uniform; 10-bit quantization; three primaries cannot also
silence rods or ipRGCs [@brainard2002display; @abuhaila2025recent; @dimigen2026advantages;
@spitschan2018method; @estevez1982silent].

**Achievable contrasts** (computed, not measured; mid-gray, D65 white). What the numbers were computed
on (stated 2026-10-08; the original computation did not record the spectral shape, and these are the
assumptions under which the independent check reproduced every entry):

- sRGB and QD-OLED: each primary's CIE 1931 xy, scaled so R+G+B = D65 (0.3127, 0.3290) in CIE 1931 xy,
  then converted to cones by the transform named in the row (§4).
- Synthetic displays: Gaussian spectra, "630/25" read as center/FWHM in nm, scaled the same way to D65;
  cones computed from the spectra with SS10. Reading the widths as Gaussian sigma instead moves the
  broadband L-M ceiling from 0.061 to 0.020 and its S ceiling from 0.94 to 0.53 — these are properties
  of assumed spectra, not of any panel.
- Background: linear primary weights (0.5, 0.5, 0.5). Isoluminant direction (1, r, 0) in cone contrast
  with r = −w_L·L0/(w_M·M0) under V_F,10. Limits are symmetric (±a).

| Display | Max L-M isoluminant ΔL/L (ΔM/M) | Max S ΔS/S | Max L-isolating | Max M-isolating | Achromatic |
|---|---|---|---|---|---|
| sRGB primaries, least-squares transform to SS10 | 0.063 (−0.142) | 0.88 | 0.19 | 0.215 | 1.0 |
| sRGB primaries, inverse XYZ_F,10 | 0.067 (−0.149) | 0.86 | 0.19 | 0.23 | 1.0 |
| QD-OLED TV primaries, least-squares | 0.095 (−0.214) | 0.98 | 0.26 | 0.34 | 1.0 |
| Synthetic narrowband (630/25, 530/25, 455/20 nm), true SS10 | 0.107 (−0.236) | 0.98 | 0.28 | 0.38 | 1.0 |
| Synthetic broadband (615/60, 540/70, 450/25 nm), true SS10 | 0.061 (−0.139) | 0.94 | 0.18 | 0.21 | 1.0 |

QD-OLED primaries from Abu Haila, Kunst, Khanh & Wallis (2025), J Vis 25(2):11,
https://doi.org/10.1167/jov.25.2.11 (table in the published version, PMC11875038, checked 2026-10-08;
also arXiv v1): R (0.700, 0.297), G (0.232, 0.727), B (0.143, 0.045); their white (0.319, 0.323), D65
assumed here. Literature values for these limits were
not retrieved from primary sources (UNVERIFIED). **Consequence:** `photometry.unrealizable` accepts any
DKL color of magnitude ≤ 0.85, while under N1 the real L-M ceiling on these displays is about 0.15-0.26
pooled — `l_m = 0.5` passes today's gate and cannot be shown (science review §7(b) confirmed).

## 4. Converting the default calibration without spectra

**sRGB** (W3C sRGB v1.10, Stokes et al. 1996, https://www.w3.org/Graphics/Color/sRGB.html): primaries
R (0.64, 0.33), G (0.30, 0.60), B (0.15, 0.06); white D65 (0.3127, 0.3290); reference white 80 cd/m²;
conversions to CIE 1931 2° XYZ. IEC 61966-2-1 itself not opened.

| Transform | Matrix | Source | What it is |
|---|---|---|---|
| Hunt-Pointer-Estévez | [[0.38971, 0.68898, −0.07868], [−0.22981, 1.18340, 0.04641], [0, 0, 1]] | colour-science `hunt.py`, citing Fairchild 2013 | Cone-like space for appearance models; S row is Z |
| Smith-Pokorny | L = 0.15514X′ + 0.54312Y′ − 0.03286Z′; M = −0.15514X′ + 0.45684Y′ + 0.03286Z′; S = 0.00801Z′ | cvrl `sp.htm`; Smith & Pokorny 1975 | On Judd-Vos XYZ (X′Y′Z′), not 1931; L + M = Judd-Vos V(λ) |
| Inverse XYZ_F (2° or 10°) | inverse of §1.4 | CIE 170-2 / cvrl | Exact only for XYZ_F |
| Least-squares 1931 to SS10 (computed) | [[0.188944, 0.911934, 0.003163], [−0.474399, 1.233874, 0.162137], [0.031032, −0.036533, 0.522345]] | fit over 390-780 nm, 1 nm, peak-normalized SS10 energy | Best linear approximation; not a standard |
| CAT02 | [[0.7328, 0.4296, −0.1624], [−0.7036, 1.6975, 0.0061], [0.0030, 0.0136, 0.9834]] | colour-science `cat.py` | Adaptation space, not cone fundamentals (CIE 159:2004 not opened) |

RMS residual against the 10° curves, fraction of peak after best scaling (computed): HPE 0.075 / 0.099 /
0.034 (L/M/S); Smith-Pokorny on 1931 XYZ 0.044 / 0.065 / 0.034; inverse XYZ_F,2 0.039 / 0.066 / 0.034;
inverse XYZ_F,10 0.041 / 0.064 / 0.034; least-squares 0.030 / 0.048 / 0.032. No linear transform of
1931 XYZ reproduces SS10; even the best leaves 3-5% of peak, and the real error depends on the panel's
spectra.

Errors in stimuli (computed on the two synthetic displays of §3 — Gaussian center/FWHM spectra scaled to
D65, mid-gray = linear 0.5; truth is SS10 from the spectra, the engine seeing only each primary's CIE 1931
XYZ; luminance under V_F,10; ranges over the two displays):

| Transform | Ask S-isolating +50%: L, M leak and luminance (V_F,10) | Ask L-isolating +10%: L, M delivered |
|---|---|---|
| HPE | L +1.5 to +1.7%, M +2.9 to +3.2%, lum +1.9 to +2.2% | L 6.5%, M −3.5 to −3.9% |
| Smith-Pokorny on 1931 XYZ | L ≈ +1.6 to +1.8%, M ≈ +2.6 to +2.9%, lum ≈ +2% | L 9.1%, M −0.1 to −0.5% |
| Inverse XYZ_F,10 | L +1.5 to +1.7%, M +2.9 to +3.2%, lum +1.9 to +2.2% | L 9.4%, M −0.1 to +0.4% |
| Least-squares fit | L and M −0.3 to −0.8%, lum −0.3 to −0.6% | L 10.3%, M +0.7 to +1.1% |

The luminosity function matters too (computed): a truly S-isolating +50% stimulus shows −1.9 to −2.2%
luminance contrast under CIE 1931 ȳ and −0.9 to −1.1% under V_F,2; an L-M stimulus isoluminant under
V_F,10 (ΔL/L 0.05) shows +1.4 to +1.6% under V_F,2 and +0.07 to +0.3% under 1931 ȳ.

Options for a training-only default: (a) one published fixed transform (inverse XYZ_F,10), labeled —
the CIE publishes the matrix for LMS to XYZ_F, so applying its inverse to 1931 XYZ is not a CIE-defined
use; (b) one fitted transform, computed once from the bundled tables and recorded; (c) assumed spectra for
the sRGB primaries (arbitrary: many spectra share an XYZ); (d) refuse cone-based and DKL colors on the
default (stricter than the PI's rule). With a spectroradiometer calibration none applies.

## 5. Macaque vs human

- **Baylor, Nunn & Schnapf (1987)**, *Macaca fascicularis*: suction-electrode recordings from 5 blue,
  20 green, 16 red cones; peaks about 430, 531, 561 nm, within-class spread under 1.5 nm; human color
  matching well predicted from the monkey cones after correcting for absorption in front of the retina.
- **Schnapf et al. (1988)**: macaque peaks about 430, 530, 561 nm; red and green cones from one human
  retina matched macaque — L/M equivalence only; nothing on S cones, and no macaque-vs-human comparison
  of pre-retinal filters (the spectra "were adjusted to give the sensitivities expected for light
  incident on the cornea of the human eye"; PubMed 3154798 abstract, checked 2026-10-08).
- **Lindbloom-Brown, Tait & Horwitz (2014)**, J Neurophysiol 112:3164-3172,
  https://doi.org/10.1152/jn.00356.2014 (abstract): on identical displays, monkeys had lower
  blue-to-green threshold ratios at 0.5-7° (consistent with lower lens density) and were more sensitive
  to 15 Hz red-green isoluminant flicker (not explained by optics); the size of the lens difference is
  UNVERIFIED.
- **Conway (2014)**, Vis Neurosci 31:197-209, https://doi.org/10.1017/S0952523813000382 (PMC full text):
  different pre-retinal filters, so a human-isoluminant stimulus may carry luminance for a monkey; human
  fundamentals are nonetheless routinely used in monkey work.
- **Macular pigment:** Snodderly, Auran & Delori (1984), IOVS 25:674-685 (abstract), macaque and Cebus:
  central peak density 0.42-1.0, falling to low, fairly constant levels within 1 mm of the fovea (1 mm in
  macaque degrees UNVERIFIED; about 4-5° if about 0.2 mm/deg). In humans macular pigment is largely
  absent by about 10° (Stockman & Rider 2023). The CIE standard macular density at 460 nm is 0.350 (2°)
  and 0.095 (10°) — the 10° set still includes some.
- **Adjustable observers:** CIE 170-1 field-size (1-10°) and age adjustments; Stockman & Rider (2023)
  vary lens, macular and photopigment densities and L/M peaks.
- **No standard macaque fundamentals found** (PubMed and web searched) — "not found", not "does not
  exist".

## Questions for the PI (the agent's framing; to be asked in plain terms)

1. **What a DKL number means** ("red-green 0.1"; figures from §2's table, computed on the display models
   of §3; every option but C is the same on every rig once the background is fixed in cone coordinates):
   A pooled cone contrast (N1; red-green 0.1 = L +4.1%, M −9.1%; lum 0.1 = 5.8% per cone); B hybrid —
   luminance axis as ordinary contrast, color axes as N1 (the axes then carry different units, which
   today's single gate — the largest component against one `max_cone_contrast` — mixes); C fraction of
   what the screen can show (N2; differs per rig and background); D each axis in its own cone's contrast
   (N3; red-green 0.1 = L +10%, M −22%: beyond the ceiling of sRGB, the broadband display and the QD-OLED
   TV by least squares, just inside on the narrowband display, ceiling 0.107; no published
   implementation cited); E Psychtoolbox `DKLDemo.m`'s per-axis scaling (N5; red-green 0.1 = mean L and
   M contrast 0.1, i.e. L +6.2%, M −13.8%, inside every modeled ceiling but at the broadband display's;
   from a demo that says "there are lots of ways to choose the scaling", not the convention
   `ComputeDKL_M.m` implements); F no DKL numbers — tasks state cone contrasts directly (N6; Brainard's
   primary alternative, used by He et al. 2021; nothing to normalize, but no azimuth or elevation, and
   isoluminance is not built in: an isoluminant red-green needs its M:L ratio, about −2.2 here and
   dependent on background and V, computed for the task).
2. **Cone-based colors on the sRGB default** (training and piloting). The default has no spectra, so its
   real errors are unknown; the figures are §4's, computed on the two synthetic displays of §3 (luminance
   under V_F,10): A the inverse of the CIE's published LMS-to-XYZ_F,10 matrix, applied to the default's
   CIE 1931 XYZ — the matrix is citable, but the CIE defines it for XYZ_F, not 1931 XYZ; asked for a +50%
   S-cone-isolating stimulus it leaks luminance +1.9 to +2.2% (about 4% of the S contrast), the same as
   the non-standard HPE and Smith-Pokorny transforms; asked for L +10% it delivers L 9.4%, M −0.1 to
   +0.4%. B a best-fit matrix computed once from the bundled tables (lab-made, documented, not a
   standard): the same S request leaks luminance −0.3 to −0.6%; L +10% delivers L 10.3%, M +0.7 to
   +1.1% — better for S and luminance, worse in M on L-isolating stimuli. C no cone-based colors on the
   default (stricter than the 2026-10-07 rule; affects color-noise and Mondrian training variants).
3. **Where the cone tables come from** (an ADR, being a license decision): A bundle the CIE's CSVs as
   separate CC BY-SA 4.0 files with attribution (5 nm only: 1 nm values are derived as in §1.2, and a
   derived table is an adaptation when shared under the UNVERIFIED §1.3 reading; record the metadata
   JSON's sha256, the pages' MD5s being stale); B bundle cvrl's tables after asking Stockman; C generate
   them from Stockman & Rider's formulae (code license to check; small residual error); D download on
   first use with a checksum (offline rigs need a cache).
4. **Adjusting the human 10° standard for monkeys:** A as is, recorded (common practice); B macular
   pigment set to zero for stimuli well outside the center; C also lower the lens density (needs a
   published macaque value, none found).
5. **Which luminosity defines isoluminance and the DKL luminance axis:** A V_F,10 (consistent with the
   cone default; cd/m² stays on CIE V(λ), so two luminances in the record); B CIE V(λ) throughout (a
   truly S-isolating +50% stimulus then reads −1.9 to −2.2% luminance contrast under CIE 1931 ȳ, where
   V_F,10 reads zero; computed on the two synthetic displays of §3); C follow the task's fundamentals
   (2° foveal, 10° otherwise); D isoluminance measured per subject (He et al. 2021: individual human
   settings span M:L −6.1 to −0.7 around a mean of about −2, n = 22; §5: monkeys differ from humans —
   Lindbloom-Brown et al. 2014, Conway 2014), at the cost of a measurement task each animal must do (a
   procedure for macaques was not researched here: UNVERIFIED), a per-subject value carried in every
   record, and one of A-C still needed until an animal is measured.

And separately: confirm the citation fix (Schnapf et al. 1988 for the quote; Baylor et al. 1987 for the
macaque peaks).

The agent's recommendations, labeled as its own (re-read 2026-10-08 against the corrections): Q1 B (or
A), unchanged — luminance contrast is Brainard's natural choice for the luminance axis and N1 is the
convention `ComputeDKL_M.m` implements for the color axes; under B the realizability gate needs a limit
per axis rather than one limit across mixed units. Q2 **changed from A to a toss-up**: A's case was
citability, but its use on 1931 XYZ is not CIE-defined and its S leak equals the non-standard HPE's; on
synthetic spectra B errs less for S and luminance and more in M on L-isolating stimuli, and the
default's real error is unknown either way — the tie-breaker is which error the color-noise and Mondrian
training variants tolerate better, a luminance cue on S-cone stimuli (A's) or M intrusion on L-cone
stimuli (B's). Q3 A, with the metadata JSON's sha256 (not the page MD5) in the record. Q4 A, with B as a
named option. Q5 A, unchanged; D is an addition for tasks whose result rests on isoluminance, not a
replacement, since a standard function is needed until an animal is measured.

## Sources (fetched 2026-10-07 unless marked)

cvrl.org (`cones.htm`, `ciepr.htm`, `ciepr8dp.htm`, `cmfs.htm`, `ss10.htm`, `ss2_10.htm`,
`cie2012xyz2.htm`, `cie2012xyz10.htm`, `mb2.htm`, `mb10.htm`, `sp.htm`, `main.php`); cie.co.at
(`/data-tables`, `/datatable/*`, `files.cie.co.at` metadata, the CIE 170-1 publication page);
creativecommons.org/faq; W3C sRGB v1.10; Brainard 1996 (Brainard32.pdf); Psychtoolbox-3
`ComputeDKL_M.m`, `DKLDemo.m` (master); PsychoPy `colorspacetools.py`, `calibTools.py` (release
7d5c61b) and its colour-spaces docs; colour-science `cat.py`, `hunt.py`, `cmfs.py` (develop 248121e);
Stockman 2019, "Cone fundamentals and CIE standards", Curr Opin Behav Sci 30:87-93,
https://doi.org/10.1016/j.cobeha.2019.06.005 (venue confirmed via Crossref 2026-10-08; read as UCL eprint
10079410); via PubMed: DKL 1984, Baylor 1987, Schnapf 1988, MacLeod & Boynton 1979,
Stockman & Sharpe 2000, Snodderly 1984, Lindbloom-Brown 2014, Conway 2014, He 2021, Stockman & Rider
2023, Abu Haila 2025 (arXiv 2410.17019v1), Hansen & Gegenfurtner 2013 (abstract only).

Fetched 2026-10-08 by the independent check, for the corrections: PubMed 3154798 (Schnapf 1988
abstract); https://color2.psych.upenn.edu/brainard/papers/Brainard32.pdf (page numbers); Psychtoolbox-3
`DKLDemo.m` (master, last commit aa91f54, 2022-04-12); PMC8322724 (He et al. 2021, full text);
PMC11875038 (Abu Haila et al. 2025, published version); the CIE LMS 2° and 10° datatable pages and
metadata JSON (cie.co.at, files.cie.co.at); cvrl `conerequest_ss2_8dp.php`; Crossref for
doi 10.1016/j.cobeha.2019.06.005. Numbers it recomputed came from the same published tables.
