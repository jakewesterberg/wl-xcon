"""The saccade detector's versions side by side, each read from this repository's own history with
`git show`, so none is a copy: version 1 at `d3a1070` (before saccade-gap-onset), version 2 at
`3c9c0dd`, version 3 at `acb57a2`, and `cur`, the working tree's `wl_xcon.saccade`, whatever its
version (4 when the probes were written, 5 since the same day's lost-stretch bound). Run from the repository's root with it on `PYTHONPATH` (see README.md)."""
from __future__ import annotations

import subprocess
import sys
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def _load(name: str, commit: str) -> types.ModuleType:
    source = subprocess.run(["git", "-C", str(ROOT), "show", f"{commit}:wl_xcon/saccade.py"],
                            check=True, capture_output=True, text=True).stdout
    module = types.ModuleType(name)
    module.__file__ = f"{commit}:wl_xcon/saccade.py"
    sys.modules[name] = module
    exec(compile(source, module.__file__, "exec"), module.__dict__)
    return module


v1 = _load("saccade_v1", "d3a1070")
v2 = _load("saccade_v2", "3c9c0dd")
v3 = _load("saccade_v3", "acb57a2")
import wl_xcon.saccade as cur  # noqa: E402

assert (v1.VERSION, v2.VERSION, v3.VERSION) == (1, 2, 3)
assert Path(cur.__file__).resolve().parents[1] == ROOT, \
    f"{cur.__file__} is not this repository's wl_xcon: run with PYTHONPATH at the repository's root"
