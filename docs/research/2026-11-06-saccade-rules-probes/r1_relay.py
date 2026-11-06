"""The review's r1: hold -> go -> Exited relay; onset in hold scored? Also go asking directly."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "tests"))
import test_gaze as tg  # noqa: E402
from wl_xcon.task import *

def relay(radius=4.0):
    return Trial(start="hold", windows=[ObjectWindows(of="search", radius=1.5), Window("fix", at=(0.0, 0.0), radius=radius)],
                 states=[State("hold", enter=[Show(tg._PROBED)], go=[On(Exited("fix"), Outcome.ABORT), On(After(0.4), "go")]),
                         State("go", go=[On(Exited("fix"), "respond"), On(After(1.0), Outcome.NO_FIXATION)]),
                         State("respond", go=tg._asks())])
def direct(radius=4.0):
    return Trial(start="hold", windows=[ObjectWindows(of="search", radius=1.5), Window("fix", at=(0.0, 0.0), radius=radius)],
                 states=[State("hold", enter=[Show(tg._PROBED)], go=[On(Exited("fix"), Outcome.ABORT), On(After(0.4), "go")]),
                         State("go", go=tg._asks())])
for radius in (1.5, 4.0):
    t = relay(radius)
    to = tg._drawn(tg._PROBED, {}, t)["search.1"]
    for dwell in range(193, 206):
        src = lambda: tg._saccades(to, dwell=dwell)
        (onset, conf, landed), = tg._timelines(t, src())
        ex = tg._exit_frame(t, src())
        r = tg._replayed(t, src()); d = tg._replayed(direct(radius), src())
        print(f"r={radius} dwell={dwell} first moving frame={dwell+1} onset={onset} exit={ex} conf={conf} landed={landed}: relay {r.visited} {r.outcome.name}  direct {d.outcome.name}")
