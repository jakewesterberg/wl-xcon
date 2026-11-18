"""Sizes scaled by eccentricity, and object windows as a ratio of their objects (the console settings
design's §5; the PI, 2026-11-16: "Size = factor x eccentricity", 0.3° per degree as in his 2020
arrays [@westerberg2020priming], and the window "Grows in proportion"; STE-31).

A size setting's card is *fixed* or *scaled*: scaled, each look whose `size` is the setting is drawn
at `factor` times its own eccentricity, its true angle from straight ahead (`task.size_at`,
`geometry.polar_of_deg`), never at an average (the PI, 2026-10-19). An object window may be declared
as a multiple of its object's radius (`ObjectWindows.scale`), so a disc twice as big gets a window
twice as big, whether its size is fixed or scaled. The layout is judged at each object's own size,
a stimulus at the center warned as not drawn and one drawn smaller than its fixed size warned with
both (`scaled-small`, the plan's Review Focus 4).

The fixture is `visual_search` with its discs `disc_size` across, its fixation point `fix_size`, and
its object windows a ratio (`object_window`, 3.0: today's 1.5° about a 1° disc). Engine test
material, run only in the simulator: no number here is a timing claim about the rig.
"""

from __future__ import annotations

import dataclasses
import json
import math
from pathlib import Path

import pytest

import _sessions
from _rig import DIRECT
from wl_xcon import link
from wl_xcon.actor import Box
from wl_xcon.check import LAYOUT, check_task, laid_out
from wl_xcon.cli import _load_task
from wl_xcon.dio import Simulated as Card
from wl_xcon.geometry import polar_of_deg
from wl_xcon.link import SetForm, SetParameter, Simulated, Telemetry
from wl_xcon.photometry import SRGB
from wl_xcon.run import Scripted
from wl_xcon.task import (
    Array, Disc, ObjectWindows, P, Scaled, placements, size_at, size_settings,
)
from wl_xcon.taskd import Session, SessionSpec
from wl_xcon.welfare import Deployment, Simulated as Pump

WALL_NOW = 1_700_000_000.0
JAKE = Box("jake")
#: The PI's factor, as in his 2020 arrays [@westerberg2020priming].
PI = 0.3

#: The fixture's settings beside visual_search's: its discs' and fixation point's sizes, open
#: above (a size's lowest is 0, the controller's ruling for Tasks 5 and 11), and the windows as a
#: ratio of each object's radius, 3.0 to start.
ADDED = '''[
    Param("disc_size", unit="deg", low=0.0, start=1.0),
    Param("fix_size", unit="deg", low=0.0, start=0.3),
]'''
MEANINGS = '''{
    "disc_size": Meaning(NOT_DIFFICULTY, STIMULUS, note="the ring's discs, across"),
    "fix_size": Meaning(NOT_DIFFICULTY, STIMULUS, note="the fixation point, across"),
}'''


def _sized_task(folder: Path, *, ring: float = 8.0, ratio: float = 3.0, extra: str = "",
                name: str = "sized") -> Path:
    """The fixture, written into `folder`: `visual_search`'s discs `disc_size` across, its
    fixation point `fix_size`, its object windows `object_window` times each object's radius, its
    ring `ring` degrees out; `extra` is Python run after the task's own source, before it is
    made."""
    text = Path("tasks/visual_search.py").read_text()
    for old, new in (
        ("size=1.0,", 'size=P("disc_size"),'),
        ("looks=Disc(size=0.3, color=", 'looks=Disc(size=P("fix_size"), color='),
        ('ObjectWindows(of="search", radius=P("object_window"))',
         'ObjectWindows(of="search", scale=P("object_window"))'),
        ('Param("object_window", unit="deg", start=1.0)',
         f'Param("object_window", unit="ratio", low=0.0, start={ratio!r})'),
        ('Param("array_eccentricity", unit="deg", low=0.0, start=8.0)',
         f'Param("array_eccentricity", unit="deg", low=0.0, start={ring!r})'),
        ('Param("fix_window", unit="deg")', 'Param("fix_window", unit="deg", start=2.0)'),
        ('Param("fix_acquisition", unit="s", low=0.0)',
         'Param("fix_acquisition", unit="s", low=0.0, start=0.5)'),
        ('Param("fix_hold", unit="s", low=0.0, high=10.0,',
         'Param("fix_hold", unit="s", low=0.0, high=10.0, start=0.3,'),
        ('Param("response_deadline", unit="s", low=0.0)',
         'Param("response_deadline", unit="s", low=0.0, start=0.6)'),
        ('Param("target_hold", unit="s", low=0.0, high=3.0,',
         'Param("target_hold", unit="s", low=0.0, high=3.0, start=0.2,'),
    ):
        assert text.count(old) >= 1, old
        text = text.replace(old, new)
    text += (
        "\n\nimport dataclasses as _dataclasses\n"
        "from wl_xcon.task import NEITHER, NOT_DIFFICULTY, STIMULUS, Meaning\n"
        f"{extra}\n"
        "search = _dataclasses.replace(search, params=[*search.params, *" + ADDED + "])\n"
        "TASK = _dataclasses.replace(TASK, structures={'search': search},\n"
        f"                            meanings={{**TASK.meanings, **{MEANINGS}}})\n"
    )
    path = Path(folder) / f"{name}.py"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


class _Drained(Simulated):
    """A link that queues `script[n]` as the `n`th drain begins (a command drained before trial `n`
    applies from trial `n + 1`). Past `BUDGET` drains the session is one that never ends, and fails
    here by name."""

    BUDGET = 60

    def __init__(self, script):
        super().__init__()
        self.script, self.drains, self.seen, self.session = dict(script), 0, {}, None

    def drain(self) -> list:
        self.drains += 1
        assert self.drains <= self.BUDGET, (
            f"the session drained {self.drains} times, past the budget of {self.BUDGET}")
        if self.session is not None and self.session.phase == "running":
            self.seen[self.drains] = {row[0]: row for row in self.session.parameters}
        for command in self.script.get(self.drains, ()):
            self.queue(command)
        return super().drain()


def _nobody(trial, values, index) -> Scripted:
    """No gaze: each trial ends as a missed acquisition, at the fixture's 0.5 s."""
    return Scripted({})


def _holding(trial, values, index) -> Scripted:
    """A gaze held on the fixation point throughout: the array shows, and each trial ends as no
    response, at the fixture's 0.6 s deadline."""
    return Scripted({}, inside={frame: "fix" for frame in range(1, 400)})


def _session(tmp_path, link_, *, ring: float = 8.0, trials: int = 6) -> Session:
    path = _sized_task(tmp_path / "task", ring=ring)
    task = _load_task(path)
    looks = {p.name: p.choices[0] for p in task.params
             if p.name in ("target_appearance", "distractor_appearance")}
    spec = SessionSpec(
        task=str(path), allocation="tasks/allocation.py", root=tmp_path,
        session_id="2027-01-14_01", subject="A", trials=trials, frame_period=1 / 240, seed=3,
        values=looks, bounds=_sessions.bounds(), already_delivered_today=0.0,
        deployment=Deployment.RIG_FIXED, geometry=DIRECT, session_kind="training",
        calibration=SRGB)
    session = Session(spec, card=Card(), pump=Pump(), link=link_)
    session.wall_clock = lambda: WALL_NOW + session.now()
    session.left_cage(at=WALL_NOW)
    session.head_fixed(at=session.wall_now())
    session.world = _nobody
    link_.session = session
    return session


def _scale(name: str = "disc_size", factor: float = PI, **numbers) -> SetForm:
    return SetForm(name=name, shape="scaled", numbers={"factor": factor, **numbers}, by=JAKE)


def _rows(session: Session, name: str) -> list[dict]:
    path = session.directory / name
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def _refused(session: Session) -> list[str]:
    return [why for _, _, why in session.refusals]


def _ring(about=(0.0, 0.0), radius: float = 8.0, n: int = 4):
    looks = Disc(size=P("disc_size"))
    return Array(n=n, radius=radius, looks=looks, among=looks)


# --- The size, at each object's own place -----------------------------------------------------


def test_size_at_is_the_factor_times_true_eccentricity():
    """§5's rule, at the true angle from straight ahead (the PI, 2026-10-19, no average ppd): 0.3
    at (8°, 0°) is 2.4°; at (6°, 6°) it is 0.3 times `polar_of_deg(6, 6)`'s eccentricity, 8.4545°,
    never √72 = 8.4853°, the per-axis hypotenuse; at the center 0; a fixed size is itself."""
    assert size_at(Scaled(PI), (8.0, 0.0)) == pytest.approx(2.4, abs=1e-12)
    true = polar_of_deg(6.0, 6.0)[0]
    assert size_at(Scaled(PI), (6.0, 6.0)) == pytest.approx(PI * true, abs=1e-12)
    assert abs(size_at(Scaled(PI), (6.0, 6.0)) - PI * math.sqrt(72.0)) > 5e-3
    assert size_at(Scaled(PI), (0.0, 0.0)) == 0.0
    assert size_at(1.5, (6.0, 6.0)) == 1.5


def test_object_windows_by_scale_are_that_multiple_of_each_objects_radius():
    """`ObjectWindows.scale`: each window's radius is the ratio times half its own object's size at
    its own place (STE-05). 3 × 0.5 = 1.5° about a fixed 1° disc; scaled by 0.3 on an 8° ring,
    each disc is 2.4° and each window 3.6°; on a ring about (4°, 0°), each object's own,
    the windows the loop scores (`placements`) the same."""
    windows = ObjectWindows(of="search", scale=3.0)
    fixed = windows.expand(_ring(), {"disc_size": 1.0})
    assert {window.radius for window in fixed} == {1.5}
    scaled = windows.expand(_ring(), {"disc_size": Scaled(PI)})
    assert [window.radius for window in scaled[:4]] == pytest.approx([3.6] * 4, abs=1e-12)
    off = windows.expand(_ring(radius=4.0), {"disc_size": Scaled(PI)}, at=(4.0, 0.0))
    for window in off[:4]:
        assert window.radius == pytest.approx(3.0 * PI * polar_of_deg(*window.at)[0] / 2.0,
                                              abs=1e-12)
    assert len({round(window.radius, 9) for window in off[:4]}) == 3  # 8°, 5.65° twice, 0°
    target, distractor = off[4], off[5]
    assert target.radius == off[0].radius == distractor.radius


def test_a_ratio_means_the_same_fixed_or_scaled():
    """"It means the same whether the size is fixed or scaled": a fixed 2.4° disc and one scaled by
    0.3 on an 8° ring are the same disc, so a ratio of 3 gives both a 3.6° window; and wherever an
    object is, its window is the ratio times its own radius."""
    windows = ObjectWindows(of="search", scale=3.0)
    fixed = [w.radius for w in windows.expand(_ring(), {"disc_size": 2.4})]
    scaled = [w.radius for w in windows.expand(_ring(), {"disc_size": Scaled(PI)})]
    assert scaled == pytest.approx(fixed, abs=1e-12)
    array = _ring(radius=4.0)
    for values in ({"disc_size": 1.7}, {"disc_size": Scaled(PI)}):
        for index, window in enumerate(windows.expand(array, values, at=(4.0, 0.0))[:4]):
            own = size_at(values["disc_size"], window.at)
            assert window.radius == pytest.approx(3.0 * own / 2.0, abs=1e-12), (values, index)


def test_radius_and_scale_both_or_neither_are_refused():
    """Exactly one of `radius` and `scale` is declared, refused as built with a sentence."""
    with pytest.raises(ValueError, match="exactly one of radius, in degrees, and scale"):
        ObjectWindows(of="search")
    with pytest.raises(ValueError, match="these declare both"):
        ObjectWindows(of="search", radius=1.5, scale=3.0)
    assert ObjectWindows("search", 1.5).radius == 1.5  # a radius in degrees, as before


def test_a_scale_window_on_an_unsized_look_is_refused_at_load(tmp_path):
    """A window that is a multiple of its object's radius needs the object's radius: a look with no
    single `size` among the array's -- a `Gabor` a look setting offers -- is refused at load,
    `unsized-window`; the same array with windows in degrees loads."""
    extra = ("from wl_xcon.task import Gabor as _Gabor\n"
             "search = _dataclasses.replace(search, params=[_dataclasses.replace(p, choices=("
             "*p.choices, _Gabor())) if p.name == 'target_appearance' else p "
             "for p in search.params])\n")
    task = _load_task(_sized_task(tmp_path, extra=extra))
    (finding,) = [f for f in check_task(task) if f.code == "unsized-window"]
    assert finding.blocking
    assert ("the object windows of 'search' are a multiple of each object's radius (scale), and "
            "array 'search' can draw an object as Gabor, which has no single size") in finding.detail
    assert not [f for f in check_task(_load_task(_sized_task(tmp_path, name="plain")))
                if f.code == "unsized-window"]


# --- The warnings -------------------------------------------------------------------------------


def test_scaled_at_the_center_and_below_its_fixed_size_are_warned(tmp_path):
    """Review Focus 4. `fix_size` scaled at eccentricity 0 is warned as not drawn; a ring close in,
    at the PI's 0.3, is warned smaller than its fixed size, saying both; neither refused. Live, each
    is accepted by who sent it and said on the feed, and the scaling applies."""
    task = _load_task(_sized_task(tmp_path / "t", ring=3.0))
    assert "scaled-small" in LAYOUT
    (center,) = [f for f in laid_out(task, {"fix_size": Scaled(PI)}, fixed={"fix_size": 0.3})
                 if f.code == "scaled-small"]
    assert not center.blocking
    assert ("'fix_size' scaled by 0.3 gives stimulus 'fix' no size straight ahead, at 0° out, so it "
            "is not drawn") in center.detail
    (near,) = [f for f in laid_out(task, {"disc_size": Scaled(PI)}, fixed={"disc_size": 1.0})
               if f.code == "scaled-small"]
    assert "'disc_size' scaled by 0.3 gives array 'search' 0.9° at 3° out, below its fixed 1°" in (
        near.detail)
    # Far enough out, the same factor draws it larger: nothing said.
    far = _load_task(_sized_task(tmp_path / "far", ring=8.0))
    assert not [f for f in laid_out(far, {"disc_size": Scaled(PI)}, fixed={"disc_size": 1.0})
                if f.code == "scaled-small"]

    link_ = _Drained({2: [_scale("fix_size")], 3: [_scale("disc_size")]})
    session = _session(tmp_path / "s", link_, ring=3.0)
    session.run()
    warned = [row for row in _rows(session, "warnings.jsonl") if row["code"] == "scaled-small"]
    assert len(warned) == 2
    assert {row["by"]["name"] for row in warned} == {"jake"}
    fed = [said for kind, _, _, said in session.controls if kind == "warning"]
    assert any("is not drawn" in said for said in fed)
    assert any("below its fixed 1°" in said for said in fed)
    assert [row["name"] for row in _rows(session, "parameter_changes.jsonl")
            if row["kind"] == "form"] == ["fix_size", "disc_size"]


def test_a_window_ratio_below_one_is_warned(tmp_path):
    """A window smaller than its disc is `window-inside-object`, the one warning code, for a ratio
    below 1 whatever the object's size; at 1 nothing is said."""
    task = _load_task(_sized_task(tmp_path))
    (inside,) = [f for f in laid_out(task, {"object_window": 0.8})
                 if f.code == "window-inside-object"]
    assert not inside.blocking
    assert ("array 'search''s object windows can be 0.8 times its objects' radius "
            "('object_window'), a ratio below 1, smaller than its objects") in inside.detail
    for values in ({"object_window": 1.0}, {"object_window": 1.0, "disc_size": Scaled(PI)}):
        assert not [f for f in laid_out(task, values, fixed={"disc_size": 1.0})
                    if f.code == "window-inside-object"]
    low = _load_task(_sized_task(tmp_path, ratio=0.5, name="low"))
    assert [f.code for f in check_task(low) if f.code == "window-inside-object"] == [
        "window-inside-object"]


# --- The switch -----------------------------------------------------------------------------


def test_scaling_is_a_size_settings_alone(tmp_path):
    """Only a setting a look draws its `size` by is scaled (`size_settings`), and only a timing
    setting drawn: a scaling of `fix_hold`, a draw of `disc_size`, a factor of 0 or below and other
    numbers are each refused with a sentence, nothing staged; a scaling of `disc_size` is staged.
    The cards say which switch each offers."""
    task = _load_task(_sized_task(tmp_path / "t"))
    assert size_settings(task) == frozenset({"disc_size", "fix_size"})
    link_ = _Drained({2: [
        _scale("fix_hold"),
        SetForm(name="disc_size", shape="non_aging", numbers={"shortest": 0.75, "longest": 1.25},
                by=JAKE),
        _scale(factor=0.0), _scale(factor=-0.3),
        _scale(factor=PI, low=0.2),
        _scale("array_eccentricity"),
    ], 3: [_scale()]})
    session = _session(tmp_path / "s", link_)
    session.run()
    refused = _refused(session)
    assert len(refused) == 6, refused
    assert "'fix_hold' is not scaled as asked: a scaling by eccentricity is a size's" in refused[0]
    assert "'disc_size' is not drawn as asked: it is in deg" in refused[1]
    assert "its factor, 0.0, is no number above 0: a size is a positive width" in refused[2]
    assert "its factor, -0.3, is no number above 0" in refused[3]
    assert "a scaling takes one number, its factor, and was sent factor, low" in refused[4]
    assert "'array_eccentricity' is not scaled as asked: a scaling by eccentricity is a size's" in (
        refused[5])
    forms = [row for row in _rows(session, "parameter_changes.jsonl") if row["kind"] == "form"]
    assert [(row["name"], row["now"], row["shape"]) for row in forms] == [
        ("disc_size", {"class": "Scaled", "fields": {"factor": PI}}, "scaled")]
    cards = link_.seen[2]
    switch = {name: cards[name][11] for name in ("disc_size", "fix_size", "fix_hold",
                                                 "object_window", "array_eccentricity")}
    assert switch == {"disc_size": "scaled", "fix_size": "scaled", "fix_hold": "drawn",
                      "object_window": None, "array_eccentricity": None}


def test_a_scaled_size_is_drawn_and_recorded_from_the_next_trial(tmp_path):
    """From the trial after it applies, each trial's values carry the scaling and its line names
    the form row (`drawn[name]`), writes the scaling as its `params` value, and gives each object's
    own size and window in degrees; the block's end says it varied by the scaling. A typed value
    then ends it, the next lines fixed again."""
    link_ = _Drained({2: [_scale()], 4: [SetParameter(name="disc_size", value=1.2, by=JAKE)]})
    session = _session(tmp_path, link_)
    session.world = _holding
    session.run()
    lines = _rows(session, "trials.jsonl")
    (form,) = [row for row in _rows(session, "parameter_changes.jsonl") if row["kind"] == "form"]
    assert [line["params"]["disc_size"] for line in lines] == [
        1.0, 1.0, {"class": "Scaled", "fields": {"factor": PI}},
        {"class": "Scaled", "fields": {"factor": PI}}, 1.2, 1.2]
    assert [line["drawn"].get("disc_size") for line in lines] == [
        None, None, form["change"], form["change"], None, None]
    assert session.spec.values["disc_size"] == 1.2
    # Each object of the 8° ring as drawn: 1° and a 1.5° window, 2.4° and 3.6° scaled, 1.2° and
    # 1.8° typed; the fixation point's size stands fixed.
    for line, (size, window) in zip(lines, [(1.0, 1.5)] * 2 + [(2.4, 3.6)] * 2 + [(1.2, 1.8)] * 2,
                                    strict=True):
        fix, search = line["stimuli"]
        assert (fix["name"], fix["size_deg"], search["name"], search["size_deg"]) == (
            "fix", 0.3, "search", None)
        assert [(o["eccentricity"], o["size_deg"], o["window_deg"]) for o in search["objects"]] == (
            [(pytest.approx(8.0), pytest.approx(size), pytest.approx(window))] * 4)
    (end,) = next(row for row in _rows(session, "runs.jsonl")
                  if row["event"] == "end")["block_ends"]
    assert {"by": "scaled", "from": form["change"], "factor": PI} in end["varied"]["disc_size"]
    assert form["shape"] == "scaled"


def test_the_card_says_the_radius_each_object_gets(tmp_path):
    """"The card shows the radius in degrees it gives at each object's eccentricity": the window's
    ratio gives `radius 1.5° at 8° out, every object` about the fixed 1° discs on the 8° ring; scaled
    by 0.3, each disc gives `2.4° at 8° out, every object` and the windows `radius 3.6°`; a fixed
    size and a timing setting give none."""
    link_ = _Drained({2: [_scale()]})
    session = _session(tmp_path, link_, trials=4)
    session.run()
    before, after = link_.seen[2], link_.seen[4]
    assert before["object_window"][15] == "radius 1.5° at 8° out, every object"
    assert (before["disc_size"][15], before["fix_hold"][15]) == (None, None)
    assert after["disc_size"][15] == "2.4° at 8° out, every object"
    assert after["object_window"][15] == "radius 3.6° at 8° out, every object"
    assert after["disc_size"][12]["shape"] == "scaled"
    assert after["disc_size"][12]["numbers"] == {"factor": PI}
    assert after["disc_size"][13] is None  # no histogram: a scaling is no draw
    row = link.ParamRow.of(*after["disc_size"])
    assert (row.switch, row.gives, row.source) == ("scaled", "2.4° at 8° out, every object", "form")


def test_a_scaled_size_never_reaches_telemetry_as_an_object(tmp_path):
    """`spec.values` keeps the fixed number, so what a console is sent holds no `Scaled`: no frame
    published while a size is scaled holds one, as built or as its wire map (`link`'s
    `_telemetry_out`), and the scaled card's value is the fixed number beneath it."""
    link_ = _Drained({2: [_scale()]})
    session = _session(tmp_path, link_)
    session.run()
    frames = [frame for frame in link_.published if isinstance(frame, Telemetry)]
    assert frames

    def walk(value, path="frame"):
        assert not isinstance(value, Scaled), path
        if dataclasses.is_dataclass(value) and not isinstance(value, type):
            for f in dataclasses.fields(value):
                walk(getattr(value, f.name), f"{path}.{f.name}")
        elif isinstance(value, dict):
            for key, item in value.items():
                walk(item, f"{path}[{key!r}]")
        elif isinstance(value, (list, tuple)):
            for at, item in enumerate(value):
                walk(item, f"{path}[{at}]")

    scaled = 0
    for frame in frames:
        walk(frame)
        cards = {row.name: row for row in frame.params}
        if cards["disc_size"].source == "form":
            scaled += 1
            assert cards["disc_size"].value == 1.0
        walk(link._telemetry_out(frame), "wire")
    assert scaled >= 2
