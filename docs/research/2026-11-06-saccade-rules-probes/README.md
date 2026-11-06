# Saccade-rule probes, 2026-11-04 to 2026-11-06

The scripts behind the numbers in EYE-19's revisions of 2026-11-04 and 2026-11-06
(`docs/references/decisions.md`): the exit carry, the measured-samples rule (`saccade.VERSION` 3),
true visual angle (version 4) and the controller's rulings on their reviews. Kept so the lab record
can be reproduced from the repository.

**These are simulations, not the rig.** Every trace is synthetic (linear, raised-cosine or
minimum-jerk saccades, Gaussian or heavy-tailed noise, lost samples placed by hand) or one of
wl-preproc's contract fixtures, replayed through the detector and the trial loop. No number here is
a measurement of the rig, its tracker or its timing, and none is a timing claim.

With `cur` at versions 5 to 7 (2026-11-06: the lost-stretch bound; a gaze sample that is no number; five of
wl-preproc's lost-data rules) `p10_trial_false.py` and `p3_fixation.py` give the same numbers as with version 4: none
of their losses is longer than one sample, none of their samples is no number, and none of their runs ends in a loss.

## Running them

From the repository's root, with the project's interpreter (the virtual environment the suite runs
in), the root on `PYTHONPATH`, and **never `-I`**, which would drop the path and import another
checkout's `wl_xcon`:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=$PWD python docs/research/2026-11-06-saccade-rules-probes/<probe>.py
```

`versions.py` loads the detector's earlier versions from this repository's history with `git show`
(version 1 at `d3a1070`, 2 at `3c9c0dd`, 3 at `acb57a2`) and the working tree's as `cur`, and refuses
to run if `wl_xcon` is not this repository's. The scripts put the repository's `tests/` on the path
themselves where they use its helpers.

**Two read wl-preproc, which is outside the repository:**
- `p2_offline.py` (and `p3_fixation.py` through it) reads wl-preproc's per-axis detector (its v1)
  through the repository's git-ignored `wl-preproc` link, as the suite does under
  `WLX_REQUIRE_PREPROC=1`, or from the directory `WLPP_PER_AXIS` names.
- `p2ta.py` (and `p3_fixation_v4.py`, `p13_v2_and_e.py` through it) reads wl-preproc's true-angle
  detector at its `82380d2` (its v2) from the directory `WLPP_V2_SOURCE` names, and refuses to run
  without it. Make one from a wl-preproc checkout:
  `git -C <wl-preproc> archive 82380d2 wl_preproc | tar -x -C <dir>`, then `WLPP_V2_SOURCE=<dir>`.

The long ones (`p1_clean`, `p3_fixation`, `p3_fixation_v4`, `p12b_missed_by_run`, `pinned_sweep`)
take minutes each.

## What each measures

| Script | Measures | EYE-19's numbers it gives |
|---|---|---|
| `pL_exited_then_saccade.py` (with `probe_common.py`) | The XC-410 review's probe L: a state entered as gaze leaves the fixation window, asking for a saccade to the target; the rig's world for a replayed saccade to each of four objects (two profiles, three window sizes), and `simulate.Subject` over 200 trials. | 2026-11-04 (exit carry): every replayed saccade scored where it lands, where all were "no response"; the simulated animal 115 CORRECT, 85 WRONG_TARGET. |
| `drift_then_saccade.py` | Gaze drifts out of a window with no saccade; a saccade begins k samples after the exit. | 2026-11-04 (exit carry): a saccade beginning a sample or two after the exit is carried, its onset put up to two samples early. |
| `r1_relay.py` | The exit-carry review's I1: a `hold` → `go` → `Exited` relay against `go` asking itself, for saccades whose detected onset is on every frame around the cue, 1.5° and 4° windows. | 2026-11-06 (rulings, I1): an onset up to six frames before the cue was scored on the relay; now the relay agrees with the direct form on every row. |
| `p10_trial_false.py` | A catch trial (any saccade an early response), fixation with a 0.12° step at sample 300 and datagram 302 lost, through the loop, versions 1 to 3 and the working tree's. | 2026-11-04 (measured samples): version 2 ended it early at frame 308; versions 3 to 7 a correct reject. Version 2's detector is now refused by the gaze world (it confirms on a closed run). |
| `p3_fixation.py` (with `p2_offline.py`, `p1_clean.py`) | The saccade-gap-onset review's probe 3: (a) the 0.12° step with each of samples 298 to 305 lost; (b) fixation only, Gaussian or heavy-tailed noise, one or three lost samples per 2 s trial, 2000 trials: trials with a "saccade", versions 1, 2 and the working tree's, online and batch, and wl-preproc per axis, whole and masked. | 2026-11-04 (measured samples): heavy-tailed, three lost, 166 under version 2 against 44 under version 1; with version 3, 44 online and 36 batch; wl-preproc 37 whole, 34 masked. Version 4 as `cur` (2026-11-06) gives the same. |
| `p3_fixation_v4.py` (with `p2ta.py`) | The same table in true angle, versions 1 to 3, the working tree's (labelled v4) and wl-preproc's true-angle detector, at (0°, 0°) and (20°, 0°). | 2026-11-06 (true angle), as commit 3's report gives it: unchanged in true angle. wl-preproc's default validity mask masks gaze at (20°, 0°) entirely (its screen region), so its columns read 0 there for that reason. |
| `p1_clean.py` | Version 1 against 2, 2 against the working tree's, and 1 against it, online, sample for sample, on 3000 random traces with nothing missing. | 2026-11-04 (measured samples): clean traces unchanged online, sample for sample, between versions 1, 2 and 3. Against version 4 they differ (8308 samples on 2026-11-06), its sizes being true angle. |
| `p12b_missed_by_run.py` | Real saccades (2 to 30 samples, 0.5° to 15°, linear and raised-cosine) with one to three consecutive samples lost at every offset: what version 2 reported and the working tree's misses, by the run's length on the whole trace and by amplitude, and whether version 1 missed it too. | 2026-11-04 (measured samples): 403 of 8277 with one lost; runs of 10 velocities or fewer (11, 12 with two, three lost), and 10 whose whole trace the batch form gave other than one run; version 1 missed every one. Measured with version 3 as `cur`; with version 4 (2026-11-06) every count is the same. |
| `p13_v2_and_e.py` (with `p2ta.py`) | (a) wl-preproc's true-angle detector and ours reproduce v2's runs on all 11 traces; (b) where they part: a run meeting a lost or unavailable sample, ours against theirs whole, with the sample alone unavailable, and with their validity mask. | 2026-11-06 (true angle): a 12-sample saccade with one interior sample unavailable is two runs in wl-preproc, one flagged run in ours; at (20°, 0°) up 2°, their two are microsaccades. |
| `pinned_sweep.py` | The sweep test's online/batch comparison over 61 seeds, the online threshold free and held at the batch form's. | The sweep test's docstring: 53 of 12,200 traces disagree free, none held. |

`versions.py` and `probe_common.py` are shared helpers, not probes.
