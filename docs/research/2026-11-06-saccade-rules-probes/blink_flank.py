"""The review of version 8, its N2: a blink delivered as lost samples (75 or 150 of them, longer than
`max_gap_s`, so withheld), then a transient where the eye returns, modelled as a 2° excursion over 10
samples decaying over 30, starting 0 to 5 samples after the return. wl-preproc pads a blink's flanks as
invalid for 80 ms after the pupil returns (XC-358); our rig pads nothing yet, so a run on that transient
just after a withheld loss is unflagged since version 8 (a withheld loss flags no run). Not a
measurement of any tracker: a synthetic shape, to show which runs the flag reaches (`q10_blink.py`,
kept here as it ran, run against more versions). Usage: blink_flank.py SACCADE_PY [SACCADE_PY ...],
each another version's `wl_xcon/saccade.py`, compared with the working tree's, batch and online."""
import importlib.util
import random
import sys

import wl_xcon
import wl_xcon.saccade as current

versions = []
for k, path in enumerate(sys.argv[1:]):
    spec = importlib.util.spec_from_file_location(f"saccade_{k}", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[f"saccade_{k}"] = module
    spec.loader.exec_module(module)
    versions.append(module)
versions.append(current)
print("wl_xcon:", wl_xcon.__file__, "| versions", [m.VERSION for m in versions])
FS = 500.0


def trial(blink_from, blink_len, onset_after, seed):
    rng = random.Random(seed)
    g = []
    back = blink_from + blink_len
    for i in range(700):
        x = y = 0.0
        j = i - back - onset_after
        if 0 <= j < 10:
            y = 2.0 * j / 10
        elif 10 <= j < 40:
            y = 2.0 * (1 - (j - 10) / 30)
        g.append((x + rng.gauss(0, 0.01), y + rng.gauss(0, 0.01)))
    for i in range(blink_from, back):
        g[i] = None
    return g, [i / FS for i in range(700)]


def online(module, g, at):
    detector = module.Detector()
    out = []
    for t, p in zip(at, g):
        s = detector.accept(t, p)
        if s is not None:
            out.append((s.start, s.flagged))
    return out


for blink_len in (75, 150):
    for after in (0, 1, 2, 3, 5):
        g, at = trial(300, blink_len, after, 7)
        cells = []
        for module in versions:
            batch = [(s.start, s.stop, s.flagged, round(s.amplitude_deg, 2)) for s in module.detect(g, at)]
            cells.append(f"v{module.VERSION} batch {batch} online {online(module, g, at)}")
        print(f"blink {blink_len} samples from 300, transient {after} after the return: " + " | ".join(cells))
