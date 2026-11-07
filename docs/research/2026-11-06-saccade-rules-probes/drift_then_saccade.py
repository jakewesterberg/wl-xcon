"""Gaze drifts out of a window with no saccade; a saccade to the target begins k samples after the exit frame."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "tests"))
import test_gaze as tg  # noqa: E402
from wl_xcon.eye import Tracker
from wl_xcon.gaze import Tracked
from wl_xcon.task import *
from wl_xcon.run import Recorded, run_trial

trial = Trial(start="fix", windows=[ObjectWindows(of="search", radius=1.5), Window("fix", at=(0.45, 0.0), radius=0.5)],
              states=[State("fix", enter=[Show(tg._PROBED)], go=[On(Exited("fix"), "left"), On(After(1.0), Outcome.NO_FIXATION)]),
                      State("left", go=tg._asks())])
to = tg._drawn(tg._PROBED, {}, trial)["search.1"]
for k in range(-3, 6):
    path = [(0.0, 0.0)] * 200 + [(-0.01 * j, 0.0) for j in range(1, 8)]
    here = path[-1]
    # exit frame computed below; saccade starts at index 207 + k - ... we place saccade start by index
    start = 200 + 6 + k  # sample index the saccade's first moving sample is at
    path = path[:start] if start <= len(path) else path + [here] * (start - len(path))
    base = path[-1]
    path += [(base[0] + (to[0] - base[0]) * j / 10, base[1] + (to[1] - base[1]) * j / 10) for j in range(1, 11)]
    path += [to] * 600
    src = lambda: tg._replay_path(path)
    exit_ = tg._exit_frame(trial, src())
    (onset, confirmed, landed), = tg._timelines(trial, src())
    r = tg._replayed(trial, src())
    print(f"k={k:+d} first moving frame={start + 1} exit frame={exit_} (left begins {exit_ + 1}) detector onset frame={onset} confirmed={confirmed} landed={landed} -> {r.visited} {r.outcome.name}")
