"""Probe L, rerun (2026-11-06): leaving fixation enters the state that asks for the saccade.

The rig's world, for a replayed saccade to each of the array's four objects, two profiles and two
fixation-window radii, and the simulated animal over 200 trials, as the XC-410 review's probe ran
it. Run as README.md says.
"""
from collections import Counter

from probe_common import *  # noqa
from wl_xcon.task import Exited, Window
from wl_xcon.simulate import Subject
import wl_xcon

print("wl_xcon from", wl_xcon.__file__)


def shaped(fix_radius):
    return Trial(start="fix",
                 windows=[ObjectWindows(of="search", radius=1.5),
                          Window("fix", at=(0.0, 0.0), radius=fix_radius)],
                 states=[State("fix", enter=[Show(ARRAY)],
                               go=[On(Exited("fix"), "flight"), On(After(2.0), Outcome.NO_RESPONSE)]),
                         State("flight", go=[On(SaccadeTo("search.target"), Outcome.CORRECT),
                                             On(SaccadeTo("search.distractor"), Outcome.WRONG_TARGET),
                                             On(After(0.3), Outcome.NO_RESPONSE)])])


objects = drawn()
for radius in (1.5, 4.0, 6.0):
    trial = shaped(radius)
    for profile, make in (("linear 10", linear), ("min-jerk 12", minjerk)):
        row = []
        for name in sorted(objects):
            path, _, _ = make([objects[name]])
            result, world = run(trial, path)
            row.append(f"{name}: {result.outcome.name}@{result.frames}")
        print(f"fix radius {radius}, {profile}: " + ", ".join(row))

trial = shaped(1.5)
c = Counter()
subject = Subject(seed=3, hazards={Exited: 5.0, SaccadeTo: 20.0}, engagement=1.0)
subject._frame_period = FP
for k in range(200):
    subject.new_trial()
    subject._windows.update({"fix"})
    subject._inside = {"fix"}
    r = run_trial(trial, subject, FP, values={}, effects=Recorded())
    c[r.outcome.name] += 1
print("simulated animal, 200 trials:", dict(c))
