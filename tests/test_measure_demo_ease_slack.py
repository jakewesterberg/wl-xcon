"""`tools/measure_demo_ease_slack.py` (the demo build's re-review, N4): the measurement plays the
glide the glide test plays, scores it as the test scores it, and the slack `pointer` eases with is
the one the committed record measured.

Its numbers are not tested -- they are what it exists to find out, committed under
`docs/measurements/` with the script -- but that it measures what it says it measures is.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path

import pytest

import test_pointer
from wl_xcon import pointer

ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location(
    "wlx_measure_demo_ease_slack", ROOT / "tools" / "measure_demo_ease_slack.py")
tool = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(tool)

#: The committed record the slack's costs are said from.
MEASURED = ROOT / "docs" / "measurements" / "dev-machine" / "2026-11-16-demo-ease-slack"


def _popout():
    found = tool.xtasks()
    if found is None:
        if os.environ.get("WLX_REQUIRE_XTASKS") == "1":  # pragma: no cover - CI's
            pytest.fail("WLX_REQUIRE_XTASKS=1 but no wl-xtasks checkout holding "
                        "tasks/popout_search.py was found")
        pytest.skip("no wl-xtasks checkout holding tasks/popout_search.py")
    from wl_xcon.cli import _load_task

    return _load_task(found / tool.TASK)


def test_it_plays_and_scores_the_glide_as_the_glide_test_does():
    """A jittered glide, by the tool and by `tests/test_pointer.py`'s glide test, ends the same way
    for the same seed, the old ease's second looks among them; and with regular reports the tool's
    eye leaves the fixation window later with the slack than without."""
    task = _popout()
    for glide_s in (0.4, 0.6):
        for seed in range(4):
            by_tool = tool.glide_trial(task, glide_s, seed, True)["ended"]
            assert by_tool == test_pointer._glided(task, glide_s, seed), (glide_s, seed)
    old = tool._with_slack(0.0, lambda: [tool.glide_trial(task, 0.4, seed, True)["ended"]
                                         for seed in range(4)])
    assert "second look" in old
    without = tool._with_slack(0.0, lambda: tool.glide_trial(task, 0.4, 0, False)["exit_ms"])
    assert tool.glide_trial(task, 0.4, 0, False)["exit_ms"] > without
    assert pointer.EASE_SLACK_S == tool.SLACKS[1]


def test_its_merges_count_two_moves_apart_as_two_saccades():
    """Two moves 200 ms apart in the page's reports are two saccades the detector confirms, with the
    slack or without: the probe counts what it says it counts."""
    rows = tool.merges(2, stops_ms=(200,))
    assert [(row["slack_ms"], row["two"]) for row in rows] == [(0, 2), (25, 2)]


def test_the_slack_pointer_eases_with_is_the_one_measured():
    """The committed record was made with the slack `pointer` holds, by the script beside it."""
    results = json.loads((MEASURED / "results.json").read_text())
    assert results["ease_slack_s"] == pointer.EASE_SLACK_S
    copy = MEASURED / "measure_demo_ease_slack.py"
    assert hashlib.sha256(copy.read_bytes()).hexdigest() == results["script_sha256"]
    rows = {(row["glide_ms"], row["timing"], row["slack_ms"]): row["ended"]
            for row in results["glides"]}
    assert rows[(400, "jittered", 25)] == {"correct": results["seeds"]}
