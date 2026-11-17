"""**What an `Entered` on a state's first judged frame moves** (decisions.md EYE-30; the PI's
try-out of demo mode, 2026-11-16): every reference task in `tasks/` and the pop-out search from a
wl-xtasks checkout at the repository's root, by the hazard `simulate.Subject` (1,500 trials at each
of two seeds) and by the simulated eye (`simeye.Eye`, 600 trials at each of three), their exact
outcome counts, as JSON on stdout.

Run from the repository's root, `PYTHONPATH=. python
docs/research/2026-11-16-entered-at-a-states-start/census_probe.py`, once on `wl_xcon/run.py` as it
was at `04797cb` (`census-at-04797cb.json`) and once with the change (`census-with-the-fix.json`),
and diff the two. Settings without a start take the reference tests' values
(`tests/test_reference_tasks.py`) or their range's middle. Engine test material: the frames are the
simulated frame clock's, and no timing claim rests on them.
"""

import json
import sys
from collections import Counter
from pathlib import Path

from wl_xcon.cli import _load_task
from wl_xcon.run import Recorded, run_trial
from wl_xcon.simeye import Eye
from wl_xcon.simulate import Subject, simulate
from wl_xcon.task import Entered, Exited, SaccadeTo

FRAME = 1 / 240
ROOT = Path(__file__).resolve().parents[3]
TASKS = {
    "fixation_detection": ROOT / "tasks" / "fixation_detection.py",
    "adaptive_detection": ROOT / "tasks" / "adaptive_detection.py",
    "visual_search": ROOT / "tasks" / "visual_search.py",
    "visual_search_training": ROOT / "tasks" / "visual_search_training.py",
    "calibration": ROOT / "tasks" / "calibration.py",
    "popout_search": ROOT / "wl-xtasks" / "tasks" / "popout_search.py",
}


#: The reference tests' values (`tests/test_reference_tasks.py`, VALUES and SEARCH_VALUES), and a
#: few more for the settings no start fills; any other setting without one at its range's middle.
OVERRIDES = {"fix_acquisition": 4.0, "fix_hold": 0.3, "response_deadline": 0.6,
             "target_hold": 0.2, "fix_window": 2.0, "object_window": 1.0,
             "array_eccentricity": 8.0, "set_size": 6, "target_index": 1, "array_rotation": 0.0,
             "target_x": 8.0, "target_y": 0.0, "cal_window": 4.0, "cal_hold": 0.3,
             "target_window": 3.0, "target_contrast": 0.5, "target_eccentricity": 8.0}


def values_of(task):
    values = {p.name: p.start for p in task.params if p.start is not None}
    for p in task.params:
        if p.start is None and p.choices:
            values[p.name] = p.choices[0]
        elif p.start is None:
            middle = OVERRIDES.get(p.name, (p.low + p.high) / 2)
            values[p.name] = round(middle) if p.unit in ("objects", "index") else middle
    if task.pool is not None:
        odd, among = task.pool.choices[1]
        values[task.pool.odd] = odd
        values[task.pool.distractor] = among
    return values


def keyed(counter):
    return {str(k): v for k, v in sorted(counter.items(), key=lambda kv: str(kv[0]))}


out = {}
for name, path in TASKS.items():
    task = _load_task(path)
    trial = task.trial
    values = values_of(task)
    for seed in (5, 11):
        census = simulate(trial, Subject(seed=seed, engagement=0.85, lapse=0.15,
                                         hazards={Entered: 4.0, Exited: 0.5, SaccadeTo: 5.0}),
                          trials=1500, frame_period=FRAME, values=dict(values),
                          effects=Recorded())
        out[f"{name} subject seed {seed}"] = {"outcomes": keyed(census.outcomes),
                                              "responses": keyed(census.responses),
                                              "hangs": census.hangs}
    for seed, early, engagement, rt in ((3, 0.1, 0.9, 0.2), (7, 0.2, 0.8, 0.35), (9, 0.0, 1.0, 0.6)):
        eye = Eye(accuracy=0.8, rt_median_s=rt, early_rate=early, seed=seed, engagement=engagement)
        outcomes, visited, frames = Counter(), Counter(), 0
        for _ in range(600):
            world = eye.world(trial, dict(values), FRAME)
            result = run_trial(trial, world, FRAME, values=dict(values), effects=Recorded())
            outcomes[result.outcome] += 1
            visited[result.visited] += 1
            frames += result.frames
        out[f"{name} eye seed {seed}"] = {"outcomes": keyed(outcomes), "frames": frames,
                                          "paths": len(visited)}

json.dump(out, sys.stdout, indent=1, sort_keys=True)
print()
