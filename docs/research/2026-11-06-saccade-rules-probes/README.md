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
With `cur` at version 8 (the same day: the end after a short loss, a withheld loss flagging nothing, the scale over
complete windows of known velocities) they give version 7's numbers but two, in `p3_fixation.py`'s heavy-tailed noise,
where the scale leaves out the measured velocities beside each lost sample: one lost a trial, online, 34 trials of
2000 with a saccade against 35; three lost a trial, batch, 35 against 36.

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

**One more reads wl-preproc's proof code:** `versus_preproc_68b76b6.py` reads it at `68b76b6` (branch
`proof/eye-lost`, unapproved) from the directory `WLPP_EYE_LOST_SOURCE` names:
`git -C <wl-preproc> archive 68b76b6 wl_preproc | tar -x -C <dir>`.

**Three read wl-preproc's code on its branch `replay2/eye-lost` at `bb6180e`** (not yet merged there):
`whole_stretch_oracle.py`, optionally, `edge_versus_preproc.py` and `versus_preproc_edge_rule.py`, from
the directory `WLPP_BB6180E_SOURCE` names: `git -C <wl-preproc> archive bb6180e wl_preproc | tar -x -C
<dir>`. Since saccade version 10 each also puts into it, in memory only, the edge rule wl-preproc's
session sent on 2026-11-06, not yet in its code (`preproc_edge_rule.py`: a stretch is withheld when
the sample beside it on either side is one of the two at an end of the trace); nothing in wl-preproc
is edited.

**One is run under two trees and compared:** `carry_short_loss.py` drives the whole gaze world, so it
is run with each version's tree on `PYTHONPATH` (a `git archive` of the commit, extracted) and the rows
compared, columns 1 to 7 for outcomes and frames. `edge_versus_preproc.py` and `rest_after_loss.py` are
run so too; `whole_stretch_oracle.py`, `clean_traces.py` and `blink_flank.py` take another version's
`wl_xcon/saccade.py` as an argument (`git show <commit>:wl_xcon/saccade.py`).

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
| `trailing_loss.py` | The review of version 7, its check 3: minimum-jerk saccades of 8 to 40 samples and 2° to 15°, each losing 1 to 24 samples from three into it to two past its end, versions 6 and 7 against the working tree's, batch. | 2026-11-06 (version 8, I2): version 7 cut 1316 of 2970 back to before the loss, unflagged, as little as 0.45° of an 8° saccade; version 8 none, 1287 of them version 6's run with its landing sample added. |
| `carry_short_loss.py` | The review of version 7, its checks 3 and 5: the onset and exit carries of saccades whose last datagrams are lost, at half a frame's staleness and the rig's 50 ms, under two trees. | 2026-11-06 (version 8, I1): version 7 refused 122 of 1820 trials versions 6 and 8 score `CORRECT`, and put the eye at rest while it was still moving in 704 of 1660 landings; versions 6 and 8 never do. 2026-11-06 (versions 9 and 10): all 3640 rows as version 8's, half a frame's 1820 trials 1637 `CORRECT`, no eye put at rest while moving. |
| `whole_stretch_oracle.py` | Version 9 (each stretch of unknown velocities judged whole): the review of version 8's oracle (its `q1_rule.py`), its loss rule and run rule now wl-preproc's code at `bb6180e`, on the review's 5093 cases, its 1500 with breaks in time and jittered clocks, 5040 pairs of losses 0 to 6 measured samples apart around a saccade, and 156 losses at a trace's first or last seven samples; batch, online with its thresholds held at the batch form's, and wl-preproc's own code. Since version 10 its stretch rule is the edge rule (both neighbours with known velocities), their code is given it in memory, and the edges add 52 breaks in time of 60 ms after each of a trace's first seven samples or between any two of its last seven. | 2026-11-06 (version 9): version 9 equals the oracle in every case, batch and held online past its warmup; version 8 in all 5093 of the review's, but flagged 193 runs the rule does not (8 with breaks in time, 173 pairs of losses, 12 at a trace's start), its runs otherwise the same; wl-preproc's code equals the oracle in 10,272 of the 10,283 cases with an `i / fs` clock and every value a number, the other 11 at a trace's end (its filled-in zero velocity there). 2026-11-06 (version 10): version 10 equals the oracle in all 5093, 1500, 5040 and 208 cases, batch and held online past its warmup; version 9 in all but 12, each a flag at a trace's start (a loss from its fourth or fifth sample) that the rule does not set; wl-preproc's code with the edge rule equals the oracle in all 10,283, none apart at the end. |
| `clean_traces.py` | The review of version 8's check 2: 3000 clean traces, another version's detector against the working tree's, batch and online, every sample. | 2026-11-06 (version 9): version 8 and 9 the same on every trace and sample. 2026-11-06 (version 10): versions 9 and 10 the same on every trace and sample. |
| `edge_versus_preproc.py` | The review of version 8's N3: a saccade from a trace's start or to its end with one of its first six or last six samples lost (first four and last five until version 10), ours against wl-preproc's code at `bb6180e`, as it is and (since version 10) with its edge rule in memory. | 2026-11-06 (version 9): sample 1 or 2 lost now unflagged, as theirs; a sample lost fourth- or fifth-last, theirs ends the run on its filled-in zero velocity at the trace's end, flagged, ours at its last measured velocity, unflagged. 2026-11-06 (version 10): equal to theirs with the edge rule at all twelve; sample 3 or 4 lost now unflagged, as theirs with it, flagged by theirs without it and by version 9; fourth- or fifth-last, theirs with it ends the run as ours does. |
| `rest_after_loss.py` | The review of version 8's N4(a): how far after the eye's first sample at rest a run carried through a short loss stops, abrupt saccades. | 2026-10-30's sentence as corrected on 2026-11-06 (version 9): up to the loss's length and six samples, the same in versions 8 and 9. |
| `blink_flank.py` | The review of version 8's N2: a transient just after a blink delivered as a withheld loss, versions 7, 8 and 9, batch and online. | 2026-11-06 (version 9): starting 0 to 3 samples after the return, flagged in version 7, unflagged in 8 and 9. |
| `versus_preproc_edge_rule.py` (with `preproc_edge_rule.py`) | Version 10 (a stretch carried only between known velocities): the review of version 9's check 1 (its `r2_versus.py`) re-run, 3000 random traces with one or two saccades and one to four losses near a saccade, an edge or another loss, ours against wl-preproc's code at `bb6180e`, as it is and with its edge rule in memory; and online, thresholds held, against the batch form. | 2026-11-06 (version 10): thresholds and runs equal to theirs with the edge rule in all 3000; to theirs as it is in 2994, the other six three losses at a trace's fourth or fifth sample, which theirs flags, and three at its end, where its zero velocity ends a carried run; version 9 against theirs as it is, 2997 and those three at the end. Online, held, 2659 equal, 341 starting inside the warmup, none apart, as with version 9. |
| `versus_preproc_68b76b6.py` | The review of version 7, its check 1's sweep: 1500 saccades with one or two losses against wl-preproc's proof code at `68b76b6`, thresholds and runs. | 2026-11-06 (version 8, M1 and M2): thresholds equal in all 1500, runs in 1253, the other 247 only by the agreed end after a short loss, which `68b76b6` predates. |

`versions.py`, `probe_common.py` and `preproc_edge_rule.py` are shared helpers, not probes.
