"""This rig with **stand-in** light-sensor housings, for the tests (backlog XC-056).

The real housings are unmeasured (direct-view spec §9 item 1), so `tasks/rig.py`'s
direct view refuses to exist, deliberately. The tests need one that does: these are
one per bottom corner, 4 × 3 cm with a 0.5 cm margin, and **nobody measured them**.
They are `geometry.stand_in_housings`'s, the ones a demo takes on an unmeasured rig (demo
mode §3.6), so the tests and a demo stand in with the same two; `tests/test_geometry.py`
holds them to the numbers written here before demo mode. Everything else is
`tasks/rig.py`'s own.

Also a rig settings file: it defines `RIG`, so `wlx run --rig` and `wlx check --rig`
can load it by `PATH`. Never collected, since its name does not start with `test_`. It loads `tasks/rig.py`
by path because `tasks/` is not part of the installed package, so `import tasks` works
under pytest's `pythonpath` and fails under the real `wlx`.
"""

import importlib.util
from dataclasses import replace
from pathlib import Path

from wl_xcon.geometry import stand_in_housings


def _load_this_rig():
    path = Path(__file__).resolve().parents[1] / "tasks" / "rig.py"
    spec = importlib.util.spec_from_file_location("_tasks_rig_by_path", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.RIG


_THIS_RIG = _load_this_rig()

RIG = replace(_THIS_RIG, housings=stand_in_housings(_THIS_RIG.panel_width_cm))
DIRECT = RIG.direct()
STEREOSCOPE = RIG.stereoscope(half_ipd_cm=1.6)
#: What `--rig` is given in the tests that run `wlx`.
PATH = "tests/_rig.py"


def naming(folder: Path, calibration: object) -> Path:
    """A rig settings file in `folder`: this stand-in rig, housings and all, naming
    `calibration` as its color calibration record (engine build B), for the tests of a
    rig that names one. It imports `_rig`, which the suite's own path provides, so it is
    loaded in-process only (`wlx check --rig`, `wlx run --rig`, `Service`)."""
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "rig.py"
    path.write_text(
        "from dataclasses import replace\n"
        "from _rig import RIG as _STAND_IN\n"
        f"RIG = replace(_STAND_IN, calibration={calibration!r})\n",
        encoding="utf-8",
    )
    return path
