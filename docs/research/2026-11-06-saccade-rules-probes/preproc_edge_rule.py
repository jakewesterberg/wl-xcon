"""wl-preproc's edge rule of 2026-11-06, put into its code at `bb6180e` in memory only (saccade
version 10). Its session's message of that day, agreed with the controller: its `local_velocity`
fills a trace's first and last two velocities with zeros, which are not measurements, so **a stretch
of unknown velocities is withheld when the sample beside it on either side is one of the two at an
end of the trace**, as well as when it is withheld or beyond the trace. It lands in its
`validity._uncarried` (with v3's `about` and a test) when it merges; until then this is that change
as the message describes it, and nothing in wl-preproc is edited: `patch` replaces the function in
the modules already imported from the directory `WLPP_BB6180E_SOURCE` names.

A shared helper, not a probe: `whole_stretch_oracle.py`, `edge_versus_preproc.py` and
`versus_preproc_edge_rule.py` use it."""
from __future__ import annotations

import numpy as np


def uncarried_with_edge_rule(lost, withheld, untrusted, frames, max_frames):
    """`validity._uncarried` at `bb6180e`, its first condition widened from "beyond the trace"
    (`before < 0 or after >= lost.size`) to "one of the two at an end of the trace or beyond it";
    the rest as it is there."""
    from wl_preproc.eye.detect.labels import true_runs
    from wl_preproc.eye.detect.velocity import _HALF_WINDOW

    out = np.zeros_like(lost)
    for start, stop in true_runs(lost):
        before, after = start - 1, stop
        if (before < _HALF_WINDOW or after >= lost.size - _HALF_WINDOW
                or withheld[before] or withheld[after]):
            out[start:stop] = True
            continue
        measured = before + np.flatnonzero(~untrusted[before:after + 1])
        if np.diff(frames[measured]).max() > max_frames:
            out[start:stop] = True
    return out


def patch():
    """Put the edge rule into wl-preproc's modules, as imported, in memory; returns `unpatch`.
    `contract_fixtures` imported the name from `validity`, so both are replaced."""
    from wl_preproc.eye.detect import contract_fixtures, validity

    original = validity._uncarried
    validity._uncarried = contract_fixtures._uncarried = uncarried_with_edge_rule

    def unpatch():
        validity._uncarried = contract_fixtures._uncarried = original

    return unpatch
