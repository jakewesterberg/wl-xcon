#!/usr/bin/env python3
"""How long the exact drawer takes to draw a demo's heaviest screen at a preview's size (demo
mode §4.4; its plan's Task 7).

CLAUDE.md: no timing claim without a measurement. `wlx serve` draws each screen a demo publishes
with the exact drawer (`exact.draw`, engine spec §4.9), on a thread of its own, at a preview of the
rig's panel: the same centimeters and degrees at fewer pixels. The design leaves the preview's size
to this measurement (§4.4: "How long a drawing takes is unmeasured: the builder measures it ...
and chooses the preview's size from it"). Its numbers are the only ones anyone may quote for it.

**What it draws.** The pop-out search's heaviest screen, from the wl-xtasks checkout: its ring at
its most discs (`set_size` 12, the setting's top) and its fixation point, thirteen flat discs. The
pop-out never shows the point with the ring (they swap on the go's frame), so this is more than any
frame it shows, and its time bounds theirs. The screen is resolved as a demo's world resolves it
(`screen.resolve`, through the default calibration, the sRGB standard, the one a rig file naming
none runs on), against the rig file's direct view, with the stand-in housings where its own are
unmeasured, as a demo takes them (§3.6).

**How.** For each preview width (480, 640 and 960 px) and supersample (2 and 4), the preview's
viewport is `viewport.viewports(rig, geometry, pixels=(width, height))`, its height the width
times the panel's height over its width, rounded. Each pair is drawn once untimed, then
`--repeats` times, the pairs taken in turn within each round so that a change in the host's load
falls on all of them alike. Each drawing is `exact.draw` alone, timed by `time.perf_counter`, and
then `exact.output_levels` through the sRGB standard and `demoscreen.png`, each timed apart. The
collector is left as `wlx serve`'s thread has it, on. The host's one-minute load average is read before and after, and
at the start of each round.

**What it chooses.** `demoscreen.PREVIEW_WIDTH_PX` and `demoscreen.SUPERSAMPLE` are the largest pair
(the widest, then the finer supersample) whose median `exact.draw` time is at most
`demoscreen.GAZE_EVERY_MS`, the page's report interval: a change drawn within one report (the plan's
call). **Where no pair is, the fastest pair** (the builder's call, demo mode's Task 7 report), and
`within_bound` says so.

**`--drawer preview` times the preview's own drawing**, `demoscreen.draw`: the exact drawer's image
bit for bit, the background drawn once and each stimulus over its own box (the follow-up, XC-507).
Its kept background is dropped before each drawing, so every time includes drawing it, as on a
screen whose background is new. Each pair's drawing is held to `exact.draw`'s, bit for bit, before
any is timed (`identical_to_exact`). With the drawing no longer most of the time, the pair is chosen
by the whole image, the drawing, `exact.output_levels` and `demoscreen.png` together (`chosen_by`).

**What this is not.** A development machine's drawing time with whatever else ran on it, for one
screen. It is a display choice for a demo's preview on this machine, never a claim about a rig, a
frame time or the display process (engine build E), and it says nothing about a machine or a
screen it was not run on.

    python tools/measure_demo_drawing.py --out docs/measurements/dev-machine/2026-11-14-demo-drawing
    python tools/measure_demo_drawing.py --drawer preview \\
        --out docs/measurements/dev-machine/2026-11-14-demo-drawing-preview
"""

from __future__ import annotations

import argparse
import gc
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import time
from dataclasses import replace
from datetime import datetime
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
# This checkout's package, never an installed copy.
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from wl_xcon import demoscreen, exact, screen, service, viewport  # noqa: E402
from wl_xcon.cli import _load_rig, _load_task  # noqa: E402
from wl_xcon.geometry import stand_in_housings  # noqa: E402
from wl_xcon.photometry import SRGB  # noqa: E402
from wl_xcon.task import Show, actions_of  # noqa: E402

WIDTHS = (480, 640, 960)
SUPERSAMPLES = (2, 4)
REPEATS = 50
#: The pop-out's most discs a run's staircase draws: Crowd's hardest, 12. The `set_size` setting
#: goes to 36 by hand since the PI, 2026-11-19; that screen is not yet measured (XC-526).
SET_SIZE = 12
#: The pop-out's two stimuli: the fixation point and the ring.
SHOWN = ("fix", "search")
RIG_FILE = ROOT / "tasks" / "rig.py"
TASK = Path("tasks") / "popout_search.py"


def xtasks() -> Path | None:
    """The wl-xtasks checkout holding the pop-out, looked for as the tests look: the link at this
    repository's root, then beside it."""
    for candidate in (ROOT / "wl-xtasks", ROOT.parent / "wl-xtasks"):
        if (candidate / TASK).is_file():
            return candidate
    return None


def demo_rig(path: Path):
    """The rig file's settings as a demo takes them (§3.6): its own housings where measured, the
    stand-ins where not. Returns the rig and whether it stands in."""
    rig = _load_rig(path)
    if rig.housings:
        return rig, False
    return replace(rig, housings=stand_in_housings(rig.panel_width_cm)), True


def heaviest(task, geometry):
    """The pop-out's ring at `SET_SIZE` and its fixation point, resolved as a demo's world resolves
    a frame: every setting at its start, the pool's first pairing, through the sRGB standard."""
    values = {param.name: param.start for param in task.params if param.start is not None}
    odd, among = task.pool.choices[0]
    values.update(odd_color=odd, distractor_color=among, set_size=SET_SIZE)
    shown = {action.stimulus.name: action.stimulus for _, action in actions_of(task.trial)
             if isinstance(action, Show)}
    visible = {name: shown[name] for name in SHOWN}
    return screen.resolve(visible, values, task.trial, geometry, frame_period=service.FRAME_PERIOD,
                          frame=1, calibration=SRGB)


def preview_height(rig, width_px: int) -> int:
    """The preview's height in pixels: its width times the panel's height over its width,
    rounded, so its pixels are as square as whole pixels allow."""
    return max(1, round(width_px * rig.panel_height_cm / rig.panel_width_cm))


def preview_viewport(rig, geometry, width_px: int):
    """The direct view's viewport at a preview `width_px` wide (`viewport.viewports(...,
    pixels=...)`): the same centimeters and degrees at fewer pixels."""
    (vp,) = viewport.viewports(rig, geometry, pixels=(width_px, preview_height(rig, width_px)))
    return vp


def _spread(times_ms: list[float]) -> dict:
    values = np.asarray(times_ms, dtype=float)
    return {"median": float(np.median(values)), "p95": float(np.percentile(values, 95)),
            "min": float(values.min()), "max": float(values.max())}


def _preview_cold(drawn_screen, vp, *, supersample):
    """`demoscreen.draw` with nothing kept from a drawing before: its background drawn too, as on
    the first screen of a background."""
    demoscreen._background.cache_clear()
    return demoscreen.draw(drawn_screen, vp, supersample=supersample)


#: **What `--drawer` times**: the exact drawer itself, or the preview's own drawing,
#: `demoscreen.draw`, its kept background dropped before each drawing (`_preview_cold`).
DRAWERS = {"exact": exact.draw, "preview": _preview_cold}


def measure(drawn_screen, rig, geometry, *, widths=WIDTHS, supersamples=SUPERSAMPLES,
            repeats=REPEATS, clock=time.perf_counter, draw=None) -> dict:
    """Each pair drawn once untimed, then `repeats` rounds of every pair in turn: `draw`'s time,
    `exact.output_levels`' and `demoscreen.png`'s apart, and the three together (the image),
    in milliseconds, and the load at each round's start. `draw` is `exact.draw` unless another is
    given, whose untimed drawing of each pair is then held to `exact.draw`'s, bit for bit
    (`identical_to_exact`)."""
    reference = exact.draw
    checking = draw is not None and draw is not reference
    draw = draw or reference
    pairs = [(width, n) for width in widths for n in supersamples]
    vps = {width: preview_viewport(rig, geometry, width) for width in widths}
    draws = {pair: [] for pair in pairs}
    levels = {pair: [] for pair in pairs}
    pngs = {pair: [] for pair in pairs}
    identical = {}
    for width, n in pairs:
        image = draw(drawn_screen, vps[width], supersample=n)
        demoscreen.png(exact.output_levels(image, SRGB))
        if checking:
            identical[(width, n)] = bool(np.array_equal(
                image, reference(drawn_screen, vps[width], supersample=n)))
    loads = []
    for _ in range(repeats):
        loads.append(os.getloadavg()[0])
        for width, n in pairs:
            start = clock()
            image = draw(drawn_screen, vps[width], supersample=n)
            drawn_at = clock()
            out = exact.output_levels(image, SRGB)
            levelled = clock()
            demoscreen.png(out)
            done = clock()
            draws[(width, n)].append((drawn_at - start) * 1000.0)
            levels[(width, n)].append((levelled - drawn_at) * 1000.0)
            pngs[(width, n)].append((done - levelled) * 1000.0)
    runs = []
    for width, n in pairs:
        vp = vps[width]
        pair = (width, n)
        images = [a + b + c for a, b, c in zip(draws[pair], levels[pair], pngs[pair])]
        run = {
            "width_px": vp.width_px, "height_px": vp.height_px, "supersample": n,
            "samples": vp.width_px * vp.height_px * n * n,
            "draw_ms": draws[pair], "levels_ms": levels[pair], "png_ms": pngs[pair],
            "draw": _spread(draws[pair]), "levels": _spread(levels[pair]),
            "png": _spread(pngs[pair]), "image": _spread(images),
        }
        if pair in identical:
            run["identical_to_exact"] = identical[pair]
        runs.append(run)
    return {"repeats": repeats, "loads_each_round": loads, "runs": runs}


def choose(runs: list[dict], bound_ms: float, by: str = "draw") -> dict:
    """**The preview's pair**: the largest -- the widest, then the finer supersample -- whose
    median time `by` (the drawing, `"draw"`, or the whole image, drawing, levels and PNG,
    `"image"`) is at most `bound_ms`; where none is, the fastest, by its median. `within_bound`
    says which."""
    passing = [run for run in runs if run[by]["median"] <= bound_ms]
    if passing:
        best = max(passing, key=lambda run: (run["width_px"], run["supersample"]))
    else:
        best = min(runs, key=lambda run: (run[by]["median"], run["width_px"],
                                          run["supersample"]))
    return {"width_px": best["width_px"], "supersample": best["supersample"],
            "median_ms": best[by]["median"], "within_bound": bool(passing)}


def _named(path: Path) -> str:
    """A path as the record names it: from this checkout's root where it is under it."""
    try:
        return str(Path(path).absolute().relative_to(ROOT))
    except ValueError:
        return str(path)


def _sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _git(*args: str, where: Path = ROOT) -> str:
    try:
        done = subprocess.run(["git", *args], cwd=where, capture_output=True, text=True, check=True)
    except (OSError, subprocess.CalledProcessError) as failed:
        return f"unavailable: {failed}"
    return done.stdout.strip()


def table(found: dict) -> str:
    """The runs as a Markdown table, for the measurement's document."""
    rows = [
        "| width × height (px) | supersample | samples | draw median (ms) | draw p95 (ms) "
        "| draw min / max (ms) | levels median (ms) | PNG median (ms) | image median (ms) "
        "| image p95 (ms) |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for run in found["runs"]:
        draw, lv, pn, im = run["draw"], run["levels"], run["png"], run["image"]
        rows.append(
            f"| {run['width_px']} × {run['height_px']} | {run['supersample']} | "
            f"{run['samples']:,} | {draw['median']:.1f} | {draw['p95']:.1f} | "
            f"{draw['min']:.1f} / {draw['max']:.1f} | {lv['median']:.1f} | {pn['median']:.1f} | "
            f"{im['median']:.1f} | {im['p95']:.1f} |")
    return "\n".join(rows) + "\n"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--out", type=Path, required=True,
                        help="the folder the raw output, the script and the rig file go in")
    parser.add_argument("--rig", type=Path, default=RIG_FILE)
    parser.add_argument("--tasks", type=Path, default=None,
                        help="a wl-xtasks checkout (default: the link here, then beside it)")
    parser.add_argument("--repeats", type=int, default=REPEATS)
    parser.add_argument("--drawer", choices=sorted(DRAWERS), default="exact",
                        help="exact: exact.draw; preview: demoscreen.draw, its background drawn "
                             "each time, held to exact.draw bit for bit (default: exact)")
    args = parser.parse_args(argv)
    if args.repeats < 1:
        parser.error("--repeats must be at least 1")
    checkout = args.tasks or xtasks()
    if checkout is None or not (checkout / TASK).is_file():
        parser.error(f"no wl-xtasks checkout holding {TASK} was found; name one with --tasks")
    task_file = checkout / TASK

    rig, stand_in = demo_rig(args.rig)
    geometry = rig.direct()
    task = _load_task(task_file)
    if task.trial.view != "direct":
        parser.error(f"{task_file} is no longer a direct-view task; this measures direct view")
    drawn_screen = heaviest(task, geometry)

    started = datetime.now().astimezone()
    load_before = os.getloadavg()
    found = measure(drawn_screen, rig, geometry, repeats=args.repeats,
                    draw=DRAWERS[args.drawer])
    load_after = os.getloadavg()
    finished = datetime.now().astimezone()

    results = {
        "script": "tools/measure_demo_drawing.py",
        "script_sha256": _sha256(Path(__file__)),
        "git_head": _git("rev-parse", "HEAD"),
        "git_status": _git("status", "--porcelain"),
        "command": ["python", _named(Path(sys.argv[0])), *sys.argv[1:]],
        "started": started.isoformat(timespec="seconds"),
        "finished": finished.isoformat(timespec="seconds"),
        "host": {
            "platform": platform.platform(), "machine": platform.machine(),
            "processor": platform.processor() or "not reported", "cpus": os.cpu_count(),
            "load_before": list(load_before), "load_after": list(load_after),
        },
        "python": platform.python_version(),
        "numpy": np.__version__,
        "wl_xcon": _named(Path(exact.__file__).parent),
        "collector_enabled": gc.isenabled(),
        "clock": "time.perf_counter",
        "percentile": "numpy.percentile, linear interpolation",
        "rig_file": _named(args.rig),
        "rig_sha256": _sha256(args.rig),
        "stand_in_housings": stand_in,
        "view": geometry.view,
        "viewing_distance_cm": geometry.viewing_distance_cm,
        "task_file": _named(task_file),
        "task_sha256": _sha256(task_file),
        "xtasks_head": _git("rev-parse", "HEAD", where=checkout),
        "screen": {"items": [item.name for item in drawn_screen.items], "set_size": SET_SIZE,
                   "frame": drawn_screen.frame, "frame_period": drawn_screen.frame_period},
        "calibration": "photometry.SRGB",
        "bound_ms": demoscreen.GAZE_EVERY_MS,
        "bound_from": "wl_xcon.demoscreen.GAZE_EVERY_MS",
        "drawer": args.drawer,
        **found,
    }
    # The exact drawer's own time chose the first preview; the preview's drawing is now a small part
    # of its image, so the whole image -- drawing, levels and PNG -- is what must fit.
    results["chosen_by"] = "draw" if args.drawer == "exact" else "image"
    results["chosen"] = choose(found["runs"], demoscreen.GAZE_EVERY_MS, results["chosen_by"])

    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "results.json").write_text(json.dumps(results, indent=1) + "\n", encoding="utf-8")
    (args.out / "table.md").write_text(table(results), encoding="utf-8")
    shutil.copyfile(Path(__file__), args.out / "measure_demo_drawing.py")
    shutil.copyfile(args.rig, args.out / "rig.py")
    print(table(results))
    print(json.dumps({"chosen": results["chosen"], "host": results["host"],
                      "python": results["python"], "numpy": results["numpy"]}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
