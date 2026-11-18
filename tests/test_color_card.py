"""A color setting's card: its set, then its hues as named swatches, then two levels (the console
settings design's §6; the PI, 2026-11-16: "you select a set, and then you have hue options from the
set, then you have salience options for each hue", salience "Both, as two choices").

A pick names a set and a hue (`link.SetColor`) and goes through `Session.set`, unchanged, as the
one declared choice it names (`task.color_choices`, `Session._color`), so it is staged until the
next trial and recorded as any value set is. A light's saturation (`photometry.ColorSetLight
.saturation`) scales its CAM16-UCS chroma at its hue toward its set's apex (COL-39), its macaque
luminance held: at 0 every hue is the set's gray, so a target and its distractors both at 0 leave
no odd one (the plan's Review Focus 5). Telemetry carries a look as its words (XC-420), and the
record writes each light's saturation, each realization's macaque row and each look's `light_xy`,
so a reader computes every light from the record alone.

The fixture is `visual_search` drawn in the isohue set: its target's three looks and its
distractors' two, each color-set light reading a saturation setting of its role, the distractors'
a fraction of their luminance. Engine test material, run only in the simulator: no number here is
a timing claim about the rig.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import _sessions
from _rig import DIRECT
from wl_xcon import photometry
from wl_xcon.actor import Box
from wl_xcon.check import IMPOSSIBLE, check_task, impossible
from wl_xcon.cli import _load_task
from wl_xcon.dio import Simulated as Card
from wl_xcon.link import (
    SetColor, SetParameter, Simulated, Staged, Telemetry, decode, encode,
)
from wl_xcon.photometry import SRGB, colorset_xyz
from wl_xcon.run import Scripted
from wl_xcon.task import Block, Condition, color_choices
from wl_xcon.taskd import Session, SessionSpec
from wl_xcon.welfare import Deployment, Simulated as Pump

WALL_NOW = 1_700_000_000.0
JAKE = Box("jake")
FIXTURE = Path(__file__).parent / "fixtures" / "isohue.json"
ISOHUE = photometry.ColorSet.load(FIXTURE)

#: visual_search's colors replaced by the isohue set's: the target's lights read
#: `target_saturation`, the distractors' `distractor_saturation` and `distractor_fraction`, all of
#: them `color_luminance`, as the pop-out search's do.
LIGHTS = f'''
from wl_xcon.photometry import ColorSet, ColorSetLight
_ISOHUE = ColorSet.load({str(FIXTURE)!r})


def _odd(hue):
    return ColorSetLight(_ISOHUE, hue, luminance=P("color_luminance"),
                         saturation=P("target_saturation"))


def _among(hue):
    return ColorSetLight(_ISOHUE, hue, fraction=P("distractor_fraction"),
                         luminance=P("color_luminance"), saturation=P("distractor_saturation"))
'''
#: The settings the fixture adds, each a fraction or the set's luminance, with its meaning.
ADDED = '''[
    Param("target_saturation", unit="fraction", low=0.0, high=1.0, start=1.0),
    Param("distractor_saturation", unit="fraction", low=0.0, high=1.0, start=1.0),
    Param("distractor_fraction", unit="fraction", low=0.0, high=1.0, start=1.0),
    Param("color_luminance", unit="cd/m2", low=1.0, high=30.0, start=15.0,
          why="a stand-in: a color set's luminance is above 0"),
]'''
MEANINGS = '''{
    "target_saturation": Meaning(NOT_DIFFICULTY, STIMULUS, note="the odd one's chroma"),
    "distractor_saturation": Meaning(NOT_DIFFICULTY, STIMULUS, note="the distractors' chroma"),
    "distractor_fraction": Meaning(NOT_DIFFICULTY, STIMULUS, note="the distractors' share"),
    "color_luminance": Meaning(NOT_DIFFICULTY, STIMULUS, note="the set's brightness"),
}'''


def _hue_task(folder: Path, name: str = "hues") -> Path:
    """The fixture, written into `folder` as `NAME.py`."""
    text = Path("tasks/visual_search.py").read_text()
    for old, new in (
        ("GREEN = DKL(lum=0.0, l_m=-0.143, s_lm=-0.87)\n",
         "GREEN = DKL(lum=0.0, l_m=-0.143, s_lm=-0.87)\n" + LIGHTS),
        ("                Disc(size=1.0, color=RED),\n"
         "                Disc(size=1.0, color=GREEN),\n"
         "                Square(size=1.0, color=GREEN),\n",
         '                Disc(size=1.0, color=_odd("red")),\n'
         '                Disc(size=1.0, color=_odd("green")),\n'
         '                Square(size=1.0, color=_odd("green")),\n'),
        ("choices=(Disc(size=1.0, color=GREEN), Disc(size=1.0, color=RED)),",
         'choices=(Disc(size=1.0, color=_among("green")), Disc(size=1.0, color=_among("red"))),'),
    ):
        assert old in text, old
        text = text.replace(old, new, 1)
    text += (
        "\n\nimport dataclasses as _dataclasses\n"
        "from wl_xcon.task import NOT_DIFFICULTY, STIMULUS, Meaning\n"
        f"search = _dataclasses.replace(search, params=[*search.params, *{ADDED}])\n"
        "TASK = _dataclasses.replace(TASK, structures={'search': search},\n"
        f"                            meanings={{**TASK.meanings, **{MEANINGS}}})\n"
    )
    path = Path(folder) / f"{name}.py"
    path.write_text(text)
    return path


@pytest.fixture
def hues(tmp_path):
    return _load_task(_hue_task(tmp_path))


def _param(task, name: str):
    return next(p for p in task.params if p.name == name)


class _Drained(Simulated):
    """A link that queues `script[n]` as the `n`th drain begins (a command drained before trial `n`
    applies from trial `n + 1`). Past `BUDGET` drains the session is one that never ends, and fails
    here by name."""

    BUDGET = 60

    def __init__(self, script):
        super().__init__()
        self.script, self.drains, self.cards = dict(script), 0, {}
        self.session = None

    def drain(self) -> list:
        self.drains += 1
        assert self.drains <= self.BUDGET, (
            f"the session drained {self.drains} times, past the budget of {self.BUDGET}")
        if self.session is not None and self.session.phase == "running":
            self.cards[self.drains] = {row[0]: row for row in self.session.parameters}
        for command in self.script.get(self.drains, ()):
            self.queue(command)
        return super().drain()


def _nobody(trial, values, index) -> Scripted:
    """No gaze: each trial ends as a missed acquisition."""
    return Scripted({})


#: The run's timings and fixation window, which visual_search leaves to the run.
RUN = {"fix_acquisition": 0.5, "fix_hold": 0.3, "response_deadline": 0.6, "target_hold": 0.2,
       "fix_window": 2.0}


def _session(tmp_path, link, *, values=None, trials=6, calibration=SRGB, square=False) -> Session:
    """A run of the fixture, its target the red disc -- or, `square`, the green square, so the
    distractors may be either color -- among green discs."""
    path = _hue_task(tmp_path)
    task = _load_task(path)
    looks = {name: _param(task, name).choices[0]
             for name in ("target_appearance", "distractor_appearance")}
    if square:
        looks["target_appearance"] = _param(task, "target_appearance").choices[2]
    spec = SessionSpec(
        task=str(path), allocation="tasks/allocation.py", root=tmp_path,
        session_id="2027-01-14_01", subject="A", trials=trials, frame_period=1 / 240, seed=3,
        values={**RUN, **looks, **(values or {})}, bounds=_sessions.bounds(),
        already_delivered_today=0.0, deployment=Deployment.RIG_FIXED, geometry=DIRECT,
        session_kind="training", calibration=calibration)
    session = Session(spec, card=Card(), pump=Pump(), link=link)
    session.wall_clock = lambda: WALL_NOW + session.now()
    session.left_cage(at=WALL_NOW)
    session.head_fixed(at=session.wall_now())
    session.world = _nobody
    link.session = session
    return session


def _rows(session, name: str) -> list[dict]:
    path = session.directory / name
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def _hue_of(written: dict) -> str:
    """The hue of a look as a trial line writes it."""
    return written["fields"]["color"]["fields"]["color"]


# --- The pick ---------------------------------------------------------------------------------


def test_a_settings_choices_are_keyed_by_set_and_hue_and_a_shared_key_is_warned(hues):
    """`task.color_choices`: the distractors' two looks by (set, hue); the target's three leave out
    the green its disc and its square share, and the load warns `ambiguous-color-choice`, naming
    it, a warning in every kind. A setting whose choices show no color-set light has none."""
    among = _param(hues, "distractor_appearance")
    assert color_choices(among) == {("isohue", "green"): among.choices[0],
                                    ("isohue", "red"): among.choices[1]}
    target = _param(hues, "target_appearance")
    assert color_choices(target) == {("isohue", "red"): target.choices[0]}
    assert color_choices(_param(hues, "fix_hold")) is None
    (warned,) = [f for f in check_task(hues) if f.code == "ambiguous-color-choice"]
    assert not warned.blocking and "'target_appearance'" in warned.detail
    assert "isohue's green" in warned.detail


def test_a_color_pick_holds_that_sets_hue_through_set(tmp_path, monkeypatch):
    """Among a green square, a pick of the distractors' red goes through `Session.set`, unchanged, as the declared red
    disc: staged until the next trial, then drawn on every trial, its change row a `set` row whose
    `now` is that disc as the record writes a look; the card's source becomes a person's, and its
    color card says the set and hue picked."""
    called = []
    original = Session.set

    def counted(self, name, value, by):
        called.append((name, value))
        return original(self, name, value, by)

    monkeypatch.setattr(Session, "set", counted)
    link = _Drained({2: [SetColor(name="distractor_appearance", colorset="isohue", color="red",
                                  by=JAKE)]})
    session = _session(tmp_path, link, square=True)
    red = _param(_load_task(Path(session.spec.task)), "distractor_appearance").choices[1]

    session.run()

    assert session.refusals == []
    assert called == [("distractor_appearance", red)]
    lines = _rows(session, "trials.jsonl")
    assert [_hue_of(line["params"]["distractor_appearance"]) for line in lines] == (
        ["green"] * 2 + ["red"] * (len(lines) - 2))
    (row,) = _rows(session, "parameter_changes.jsonl")
    assert (row["kind"], row["name"], _hue_of(row["now"]), _hue_of(row["was"])) == (
        "set", "distractor_appearance", "red", "green")
    card = link.cards[4]["distractor_appearance"]
    assert card[7] == "person"
    assert (card[16]["set"], card[16]["hue"]) == ("isohue", "red")


@pytest.mark.parametrize("pick, said", [
    (("distractor_appearance", "isohue", "purple"),
     "'distractor_appearance' offers no choice in isohue's purple"),
    (("target_appearance", "isohue", "green"),
     "'target_appearance' offers no choice in isohue's green"),
    (("distractor_appearance", "other", "red"),
     "'distractor_appearance' offers no choice in other's red"),
    (("fix_hold", "isohue", "red"), "'fix_hold' is no color setting this task declares"),
    (("nothing", "isohue", "red"), "'nothing' is no color setting this task declares"),
])
def test_a_pick_naming_no_choice_is_refused(tmp_path, pick, said):
    """A hue the setting's choices do not offer, one two choices share, a set none shows, a
    setting with no color card, and a name the task does not declare: each refused with its
    sentence, nothing staged, the session running on."""
    name, colorset, color = pick
    link = _Drained({2: [SetColor(name=name, colorset=colorset, color=color, by=JAKE)]})
    session = _session(tmp_path, link, trials=4)

    session.run()

    ((refused, by, why),) = session.refusals
    assert (refused, by) == (name, JAKE) and said in why, why
    assert _rows(session, "parameter_changes.jsonl") == []
    assert len(_rows(session, "trials.jsonl")) == 4


def test_a_pick_that_leaves_no_odd_one_is_refused_as_set_refuses_any_value(tmp_path):
    """A pick is judged as any value set is (`Session._impossible`, then `set`): red distractors
    around the red disc leave no odd one, so the pick is refused with that sentence, the previous
    value standing, nothing staged."""
    link = _Drained({2: [SetColor(name="distractor_appearance", colorset="isohue", color="red",
                                  by=JAKE)]})
    session = _session(tmp_path, link, trials=4)

    session.run()

    ((name, _, why),) = session.refusals
    assert name == "distractor_appearance"
    assert "is refused, and the previous value stands" in why
    assert "no object stands out" in why, why
    assert _rows(session, "parameter_changes.jsonl") == []


# --- Both saturations at 0 (Review Focus 5) ---------------------------------------------------


def test_both_saturations_at_zero_leave_no_odd_one(tmp_path, hues):
    """At saturation 0 a light is its set's apex, whatever its hue: the red target among green
    distractors, both at 0, is a gray disc among gray discs, no odd one. One light at 0 is
    accepted; the second, which leaves none, is refused as `impossible-trial` the moment it is
    set, the previous value standing; the check says so as it reads both."""
    blocks = [Block("session", [Condition("session", {}, target=1)])]
    looks = {name: _param(hues, name).choices[0]
             for name in ("target_appearance", "distractor_appearance")}
    values = {p.name: p.start for p in hues.params if p.start is not None} | RUN | looks
    assert impossible(hues, blocks, {**values, "target_saturation": 0.0}) == []
    (both,) = impossible(hues, blocks, {**values, "target_saturation": 0.0,
                                        "distractor_saturation": 0.0})
    assert both.code == IMPOSSIBLE and both.blocking

    link = _Drained({2: [SetParameter(name="target_saturation", value=0.0, by=JAKE)],
                     3: [SetParameter(name="distractor_saturation", value=0.0, by=JAKE)]})
    session = _session(tmp_path, link)

    session.run()

    ((name, _, why),) = session.refusals
    assert name == "distractor_saturation"
    assert why.startswith("'distractor_saturation' at 0 is refused, and the previous value stands")
    assert IMPOSSIBLE in why or "looks like its distractors" in why, why
    (row,) = _rows(session, "parameter_changes.jsonl")
    assert (row["name"], row["now"]) == ("target_saturation", 0.0)


# --- Telemetry carries a look as its words (XC-420) -------------------------------------------


def test_a_held_look_and_a_staged_one_publish_as_words(tmp_path):
    """XC-420 closed: a run whose values hold looks publishes each card's value `None` with the
    look in the rig's words beside it, and a staged pick its `was` and `now` as words, every frame
    encoding and decoding as it was built."""
    link = _Drained({2: [SetColor(name="distractor_appearance", colorset="isohue", color="red",
                                  by=JAKE)]})
    session = _session(tmp_path, link, trials=4, square=True)

    session.run()

    frames = [frame for frame in link.published if isinstance(frame, Telemetry)]
    assert frames
    for frame in frames:
        assert decode(encode(frame)) == frame
    cards = [row for frame in frames for row in frame.params if row.name == "distractor_appearance"]
    assert cards and all(row.value is None for row in cards)
    green = ("Disc: color isohue green at fraction distractor_fraction, luminance "
             "color_luminance, saturation distractor_saturation")
    assert cards[0].words == green
    assert cards[-1].words == green.replace("green", "red")
    staged = [row for frame in frames for row in frame.staged]
    assert staged and set(staged) == {Staged(
        name="distractor_appearance", was=green, now=green.replace("green", "red"), by=JAKE,
        bounded=False, kind="set")}


# --- The card ---------------------------------------------------------------------------------


def test_a_color_card_names_its_sets_hues_and_two_levels(tmp_path):
    """The card the rig makes (`ParamRow.color`): the set its choices show, with its apex, its
    luminance, its design (none yet) and each hue offered, its chromaticity as written and its
    sRGB swatch, approximate; the set and hue of the run's value; its saturation by its setting,
    and its luminance by the distractors' fraction setting, each with the light's cd/m². The
    target's luminance is its set's setting, which moves every light of the set."""
    link = _Drained({})
    session = _session(tmp_path, link, trials=2, values={"distractor_fraction": 0.5,
                                                         "distractor_saturation": 0.25})

    session.run()

    among = link.cards[2]["distractor_appearance"][16]
    swatch = {hue: photometry.srgb_hex(colorset_xyz(photometry.ColorSetLight(ISOHUE, hue), SRGB))
              for hue in ("green", "red")}
    assert among == {
        "sets": {"isohue": {
            "apex": list(ISOHUE.apex), "luminance_cd_m2": 15.0, "design": None,
            "hues": {hue: {"xy": list(ISOHUE.colors[hue]), "srgb": swatch[hue]}
                     for hue in ("green", "red")}}},
        "set": "isohue", "hue": "green", "approximate": True,
        "saturation": {"setting": "distractor_saturation", "value": 0.25, "cd_m2": 7.5},
        "luminance": {"setting": "distractor_fraction", "value": 0.5, "cd_m2": 7.5,
                      "set_wide": False},
    }
    target = link.cards[2]["target_appearance"][16]
    assert list(target["sets"]["isohue"]["hues"]) == ["red"]
    assert target["luminance"] == {"setting": "color_luminance", "value": 15.0, "cd_m2": 15.0,
                                   "set_wide": True}
    assert all(card[16] is None for name, card in link.cards[2].items()
               if name not in ("target_appearance", "distractor_appearance"))


# --- The record -------------------------------------------------------------------------------


def test_a_light_records_its_saturation_and_each_realization_its_macaque_row(tmp_path):
    """The shapes asked of wl-preproc (2026-11-17, group 3): each light's form writes its
    `saturation` -- a setting by reference here, a number at its default 1.0 elsewhere -- each
    realization its calibration's `macaque_row`, and each set its `design`, null until a set
    declares one."""
    from wl_xcon.record import _written

    link = _Drained({})
    session = _session(tmp_path, link, trials=2)

    session.run()

    (start,) = [row for row in _rows(session, "runs.jsonl") if row["event"] == "start"]
    defined = start["color_sets"]["isohue"]
    assert defined["design"] is None
    assert [each["macaque_row"] for each in defined["realized"]] == [
        list(photometry.macaque_row(SRGB))]
    light = _rows(session, "trials.jsonl")[0]["params"]["target_appearance"]["fields"]["color"]
    assert light["fields"]["saturation"] == {"class": "P", "fields": {"name": "target_saturation"}}
    plain = _written(photometry.ColorSetLight(ISOHUE, "blue"))
    assert plain["fields"]["saturation"] == 1.0


def _bound(form: dict, params: dict) -> object:
    """A field as a line writes it, a setting's reference read from the line's own values."""
    if isinstance(form, dict) and form.get("class") == "P":
        return params[form["fields"]["name"]]
    return form


def _fixating(trial, values, index) -> Scripted:
    """The fixation point held, so the search shows, and no answer: each trial ends unanswered."""
    return Scripted({}, inside={frame: "fix" for frame in range(1, 400)})


@pytest.mark.parametrize("calibration", ["srgb", "narrow"])
def test_a_reader_rebuilds_each_lights_xyz_from_the_record_alone(tmp_path, calibration):
    """wl-preproc's rule (accepted 2026-11-18, the PI's CAM16-UCS answer), from each trial line and
    the start row alone: with `u = (x/y, 1, (1 − x − y)/y)` from the look's `light_xy`, `L =
    fraction × luminance` and the realization's `macaque_row`, `XYZ = u × L / (macaque_row · u)` --
    equal to the rig's own light (`colorset_xyz`) to 1e-9 for each of the search's objects, on the
    standard and on a panel that desaturates the set. The search's own entry and the fixation
    point, drawn in no color set's light, write `light_xy` null."""
    from _calibrations import measured

    panel = SRGB if calibration == "srgb" else measured(green=photometry.xyY(0.30, 0.45, 140.0))
    link = _Drained({})
    values = {"target_saturation": 0.4, "distractor_saturation": 0.7, "distractor_fraction": 0.6,
              "color_luminance": 12.0}
    session = _session(tmp_path, link, trials=2, values=values, calibration=panel)
    session.world = _fixating

    session.run()

    (start,) = [row for row in _rows(session, "runs.jsonl") if row["event"] == "start"]
    defined = start["color_sets"]["isohue"]
    task = session._task
    lines = _rows(session, "trials.jsonl")
    read = 0
    for line in lines:
        params = line["params"]
        stimuli = {entry["name"]: entry for entry in line["stimuli"]}
        assert stimuli["fix"]["light_xy"] is None and stimuli["search"]["light_xy"] is None
        target = stimuli["search"]["target"]
        for index, entry in enumerate(stimuli["search"]["objects"]):
            name = "target_appearance" if index == target else "distractor_appearance"
            fields = params[name]["fields"]["color"]["fields"]
            luminance = _bound(fields["luminance"], params)
            (realization,) = [each for each in defined["realized"]
                              if each["luminance_cd_m2"] == luminance]
            s, f = _bound(fields["saturation"], params), _bound(fields["fraction"], params)
            x, y = entry["light_xy"]
            u = (x / y, 1.0, (1.0 - x - y) / y)
            per = sum(r * v for r, v in zip(realization["macaque_row"], u))
            rebuilt = tuple(v * f * luminance / per for v in u)

            declared = next(choice for choice in _param(task, name).choices
                            if choice.color.color == fields["color"]).color
            rig = colorset_xyz(photometry.ColorSetLight(
                declared.colorset, declared.color, fraction=f, luminance=luminance,
                saturation=s), panel)
            assert rebuilt == pytest.approx(rig, abs=1e-9), (name, fields["color"])
            read += 1
    assert read == 4 * len(lines) and len(lines) == 2
