"""`tools/measure_demo_drawing.py` (demo mode §4.4; its plan's Task 7): the measurement draws what it
says it draws, times what it says it times, chooses the preview's size by its rule, and the size
`demoscreen` draws at is the committed measurement's choice.

The numbers it produces are not tested -- they are what it exists to find out, committed under
`docs/measurements/` with the script and the rig file it ran with. What is tested is that the script
cannot quietly measure something else, and that the preview's size cannot drift from what it found.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path

import pytest

from _rig import DIRECT, RIG
from wl_xcon import demoscreen, look, viewport

ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location(
    "wlx_measure_demo_drawing", ROOT / "tools" / "measure_demo_drawing.py")
tool = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(tool)

#: The committed measurement the preview's size was chosen from.
MEASURED = ROOT / "docs" / "measurements" / "dev-machine" / "2026-11-14-demo-drawing"


def _popout():
    """The pop-out, from the wl-xtasks checkout the script reads."""
    found = tool.xtasks()
    if found is None:
        if os.environ.get("WLX_REQUIRE_XTASKS") == "1":  # pragma: no cover - CI's
            pytest.fail("WLX_REQUIRE_XTASKS=1 but no wl-xtasks checkout holding "
                        "tasks/popout_search.py was found")
        pytest.skip("no wl-xtasks checkout holding tasks/popout_search.py")
    from wl_xcon.cli import _load_task

    return _load_task(found / tool.TASK)


def test_it_draws_the_popouts_ring_at_its_most_discs_and_its_point():
    """The heaviest screen: the ring at `set_size`'s top, twelve, and the fixation point, every one
    a flat disc, resolved through the sRGB standard as a demo's world resolves a frame."""
    task = _popout()
    (set_size,) = [param for param in task.params if param.name == "set_size"]
    assert tool.SET_SIZE == set_size.high == 12

    shown = tool.heaviest(task, DIRECT)

    assert [item.name for item in shown.items] == ["fix", *(f"search.{i}" for i in range(12))]
    assert all(isinstance(item.shape, look.Circle) for item in shown.items)
    assert all(item.fill.xyz is not None for item in shown.items)


def test_its_rig_is_the_rig_files_with_the_stand_ins_a_demo_takes():
    """§3.6: where the rig file's housings are unmeasured, the stand-ins, as a demo takes them, and
    a rig's own where they are measured; its previews are the direct view's viewports at each
    width, their height the panel's to it, rounded."""
    rig, stand_in = tool.demo_rig(tool.RIG_FILE)
    assert stand_in and rig.housings == RIG.housings
    assert tool.demo_rig(ROOT / "tests" / "_rig.py") == (RIG, False)
    for width in tool.WIDTHS:
        height = round(width * RIG.panel_height_cm / RIG.panel_width_cm)
        (wanted,) = viewport.viewports(RIG, DIRECT, pixels=(width, height))
        assert tool.preview_viewport(RIG, DIRECT, width) == wanted


def test_a_small_measurement_times_each_pair_by_its_clock_in_turn(monkeypatch):
    """Each pair drawn once untimed, then each round every pair in turn, `exact.draw` at the pair's
    preview and supersample and `exact.output_levels` timed apart, in milliseconds, by the clock
    given."""
    drawn_at: list = []
    draw = tool.exact.draw

    def watched(screen, vp, *, supersample):
        drawn_at.append((vp.width_px, supersample))
        return draw(screen, vp, supersample=supersample)

    monkeypatch.setattr(tool.exact, "draw", watched)
    task = _popout()
    shown = tool.heaviest(task, DIRECT)
    # The clock as each round's drawings would read it: in round r, each pair's drawing takes
    # r × 10 ms of the pair's own number, and its levels 0.5 ms.
    moments, now = [], 0.0
    for r in (1, 2, 3, 4, 5):
        for k in (1, 2, 3, 4):
            moments += [now, now + r * 10 * k / 1000.0, now + (r * 10 * k + 0.5) / 1000.0]
            now = moments[-1] + 1.0
    ticks = iter(moments)

    found = tool.measure(shown, RIG, DIRECT, widths=(8, 12), supersamples=(1, 2), repeats=5,
                         clock=lambda: next(ticks))

    assert next(ticks, None) is None, "three readings a drawing, none untimed"
    assert drawn_at == [(8, 1), (8, 2), (12, 1), (12, 2)] * 6
    assert found["repeats"] == 5 and len(found["loads_each_round"]) == 5
    assert [(run["width_px"], run["supersample"]) for run in found["runs"]] == [
        (8, 1), (8, 2), (12, 1), (12, 2)]
    for k, run in enumerate(found["runs"], start=1):
        assert run["draw_ms"] == pytest.approx([10.0 * k * r for r in (1, 2, 3, 4, 5)])
        assert run["levels_ms"] == pytest.approx([0.5] * 5)
        assert run["draw"] == pytest.approx({"median": 30.0 * k, "p95": 48.0 * k,
                                             "min": 10.0 * k, "max": 50.0 * k})
        assert run["samples"] == run["width_px"] * run["height_px"] * run["supersample"] ** 2
        assert run["height_px"] == tool.preview_height(RIG, run["width_px"])


def test_it_chooses_the_largest_pair_within_the_bound_and_else_the_fastest():
    """The plan's rule: the widest, then the finer supersample, whose median is at most the bound;
    and the builder's where none is: the fastest by its median, saying it is not within it."""
    def run(width, n, median):
        return {"width_px": width, "supersample": n, "draw": {"median": median}}

    runs = [run(480, 2, 40.0), run(480, 4, 90.0), run(640, 2, 80.0), run(640, 4, 150.0),
            run(960, 2, 120.0), run(960, 4, 400.0)]

    def pair(bound):
        chosen = tool.choose(runs, bound)
        return chosen["width_px"], chosen["supersample"], chosen["within_bound"]

    assert tool.choose(runs, 100.0) == {"width_px": 640, "supersample": 2, "median_ms": 80.0,
                                        "within_bound": True}
    assert pair(80.0) == (640, 2, True)
    assert pair(79.9) == (480, 2, True)
    assert pair(150.0) == (960, 2, True)
    assert pair(400.0) == (960, 4, True)
    assert pair(95.0) == (640, 2, True)
    assert tool.choose(runs, 39.9) == {"width_px": 480, "supersample": 2, "median_ms": 40.0,
                                       "within_bound": False}
    slower_coarse = [run(480, 2, 70.0), run(480, 4, 60.0)]
    assert tool.choose(slower_coarse, 10.0)["supersample"] == 4


def test_the_previews_size_is_the_committed_measurements_choice():
    """`demoscreen.PREVIEW_WIDTH_PX` and `SUPERSAMPLE` are what the committed measurement chose by
    the rule above, against the bound `demoscreen.GAZE_EVERY_MS` gives, from fifty drawings of each
    pair; the record holds the script and the rig file it ran with, each as its hash says."""
    results = json.loads((MEASURED / "results.json").read_text(encoding="utf-8"))

    assert results["bound_ms"] == demoscreen.GAZE_EVERY_MS
    assert results["repeats"] == tool.REPEATS == 50
    assert [(run["width_px"], run["supersample"]) for run in results["runs"]] == [
        (w, n) for w in tool.WIDTHS for n in tool.SUPERSAMPLES]
    for run in results["runs"]:
        assert len(run["draw_ms"]) == 50
    chosen = tool.choose(results["runs"], demoscreen.GAZE_EVERY_MS)
    assert chosen == results["chosen"]
    assert (chosen["width_px"], chosen["supersample"]) == (demoscreen.PREVIEW_WIDTH_PX,
                                                           demoscreen.SUPERSAMPLE)
    for name, key in (("measure_demo_drawing.py", "script_sha256"), ("rig.py", "rig_sha256")):
        assert hashlib.sha256((MEASURED / name).read_bytes()).hexdigest() == results[key]
    assert (MEASURED.parent / f"{MEASURED.name}.md").is_file()
