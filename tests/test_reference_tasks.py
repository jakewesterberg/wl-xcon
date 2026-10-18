"""The reference tasks, held to the standard ADR-0006 rests on.

A task is approved from its checks and its simulation report, not by reading its
source. These assert both for the tasks that demonstrate it.
"""

from __future__ import annotations

import importlib.util
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from _calibrations import LINEAR, SPECTRA
from _rig import DIRECT, RIG
from wl_xcon import screen
from wl_xcon.calibration import constellation
from wl_xcon.cli import _load_task
from wl_xcon.check import check, check_task
from wl_xcon.cones import V_F10
from wl_xcon.declarations import COMMON, OVERRIDE, OWN, SHARED, resolved
from wl_xcon.findings import SESSION_KINDS
from wl_xcon.photometry import SRGB, SRGB_WHITE_CD_M2, DKL, Calibration, Gray, _apply3, xyY
from wl_xcon.run import Recorded
from wl_xcon.simulate import Subject, simulate
from wl_xcon.task import (
    BACKGROUND,
    CLEAR_CUT,
    CRITERION,
    EASIER,
    EXPECTED,
    HARDER,
    NOT_DIFFICULTY,
    NO_CHOICE,
    OWED,
    SPENT,
    STIMULUS,
    Counting,
    Entered,
    Hold,
    Exited,
    Outcome,
    P,
    SaccadeTo,
    Show,
    Trial,
    actions_of,
)
from wl_xcon.welfare import Deployment

TASKS = Path(__file__).resolve().parents[1] / "tasks"

#: The rig in direct view (`tasks/rig.py`), where every reference task runs, with
#: stand-in housings (`tests/_rig.py`).
GEOMETRY = DIRECT
VALUES = {
    "fix_acquisition": 4.0,
    "fix_hold": 0.3,
    "response_deadline": 0.6,
    "target_hold": 0.2,
}


def _load(name: str, attribute: str):
    sys.path.insert(0, str(TASKS))
    spec = importlib.util.spec_from_file_location(name, TASKS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return getattr(module, attribute)


@pytest.fixture(scope="module")
def detection() -> Trial:
    return _load("fixation_detection", "detection")


def test_the_reference_task_passes_every_load_time_check(detection):
    allocation = _load("allocation", "ALLOCATION")

    assert check(detection, allocation, geometry=GEOMETRY) == []


def test_simulation_reaches_every_outcome_the_reference_task_declares(detection):
    """The acceptance test, and the one that is hard to satisfy honestly.

    `NO_RESPONSE` needs an animal that acquires fixation, holds it, and then does
    not respond -- a mid-trial lapse. A subject whose engagement is decided once per
    trial cannot produce one, so every task's no-response path would go untested by
    simulation while the report claimed a clean run.
    """
    census = simulate(
        detection,
        Subject(
            seed=11,
            engagement=0.85,
            # Rates per second, not per frame.
            lapse=0.15,
            hazards={Entered: 6.0, SaccadeTo: 5.0, Exited: 0.05},
        ),
        trials=5_000,
        frame_period=1 / 240,
        values=VALUES,
        effects=Recorded(),
    )

    assert census.hangs == 0
    assert census.uncovered(detection) == set()
    assert census.states_visited == {"await_fix", "hold_fix", "stim_on", "verify"}


@pytest.fixture(scope="module")
def adaptive() -> Trial:
    return _load("adaptive_detection", "adaptive_detection")


def test_the_adaptive_task_passes_every_load_time_check(adaptive):
    allocation = _load("allocation", "ALLOCATION")

    assert check(adaptive, allocation, geometry=GEOMETRY) == []


def test_the_adaptive_trial_is_the_detection_trial_with_more_parameters(adaptive, detection):
    """S1's bake-off finding, asserted rather than claimed: the adaptive task's
    *trial* is structurally the same. Everything adaptive lives between trials."""
    assert [s.name for s in adaptive.states] == [s.name for s in detection.states]
    assert {p.name for p in detection.params} < {p.name for p in adaptive.params}


def test_each_detection_task_places_its_target_at_its_x_and_y(adaptive, detection):
    """The PI, 2026-10-11: "shouldnt there also be a target_y?". The target and its window sit at
    (`target_x`, `target_y`), each declared over ±16° and `target_y` starting on the horizontal
    meridian; the target's computed position is the trial's to record (XC-348), not a setting."""
    where = (P("target_x"), P("target_y"))
    for trial in (detection, adaptive):
        shown = {action.stimulus.name: action.stimulus.at
                 for _, action in actions_of(trial) if isinstance(action, Show)}
        windows = {window.name: window.at for window in trial.windows}
        assert shown["target"] == windows["target"] == where
        (y,) = [param for param in trial.params if param.name == "target_y"]
        assert (y.low, y.high, y.start) == (-16.0, 16.0, 0.0) == (*_range(trial, "target_x"), 0.0)


def test_the_staircase_converges_downward_on_success_and_backs_off_on_error():
    staircase = _load("adaptive_detection", "Staircase")(value=0.5)

    staircase.update(True)
    assert staircase.value == 0.5, "one correct is not enough; it is two-down"
    staircase.update(True)
    assert staircase.value < 0.5

    harder = staircase.value
    staircase.update(False)
    assert staircase.value > harder, "one error backs off immediately"


def test_an_aborted_trial_does_not_move_the_staircase():
    """An abort says nothing about difficulty. Letting one move the estimate makes
    the target's contrast track engagement rather than perception -- so a disengaged animal
    would be handed easier stimuli for a reason unrelated to what it can see."""
    module_staircase = _load("adaptive_detection", "Staircase")
    next_params = _load("adaptive_detection", "next_params")
    staircase = module_staircase(value=0.5)

    for outcome in (Outcome.NO_FIXATION, Outcome.FIXATION_BREAK, Outcome.NO_RESPONSE):
        next_params(staircase, target_eccentricity=10.0, last=outcome)

    assert staircase.value == 0.5


# --- Colour pop-out search -------------------------------------------------
#
# The paradigm the vocabulary could not express before 2026-08-31: no colour, so a
# red target among green distractors could not be stated; and an array was N `Show`
# actions, so set size was a change to the shape of the task rather than a value.

SEARCH_VALUES = {
    "fix_acquisition": 4.0,
    "fix_hold": 0.3,
    "response_deadline": 0.6,
    "target_hold": 0.2,
    "fix_window": 2.0,
    "object_window": 2.0,
    "array_eccentricity": 8.0,
    "set_size": 6,
    "target_index": 1,
    "array_rotation": 0.0,
}

#: Illustrative, not measured. A real calibration comes from a photometer on the
#: actual panel and is committed under `docs/measurements/`; none exists yet.
PANEL = Calibration(
    red=xyY(0.640, 0.330, 45.0),
    green=xyY(0.300, 0.600, 145.0),
    blue=xyY(0.150, 0.060, 15.0),
    background=xyY(0.3127, 0.3290, 50.0),
    transfer=(LINEAR,) * 3,
    observer="macaque V(lambda) -- placeholder, unmeasured",
    measured_on="2026-08-31",
    spectra=SPECTRA,
)


@pytest.fixture(scope="module")
def search() -> Trial:
    return _load("visual_search", "search")


def test_the_search_task_passes_every_load_time_check(search):
    allocation = _load("allocation", "ALLOCATION")

    assert check(search, allocation, geometry=GEOMETRY, calibration=PANEL) == []


def test_the_search_task_runs_on_a_measured_display_without_spectra_with_a_warning(search):
    """XC-352's E3 (the PI, 2026-10-11): its cone colors convert as the default's do, with a
    warning in every kind; until then it was refused (call 8)."""
    allocation = _load("allocation", "ALLOCATION")

    found = check(search, allocation, geometry=GEOMETRY, calibration=replace(PANEL, spectra=None))

    assert [f for f in found if f.blocking] == []
    assert "cone-colors-without-spectra" in {f.code for f in found if f.is_warning}


def test_the_search_task_will_not_load_without_a_measured_display(search):
    """Isoluminance is a claim about photometry, so it needs a photometer.

    The failure mode this prevents is not a crash: it is a task that runs, looks
    convincing, and reports a colour nobody measured -- which reaches a methods
    section.
    """
    allocation = _load("allocation", "ALLOCATION")
    codes = {f.code for f in check(search, allocation, geometry=GEOMETRY)}

    assert "uncalibrated-color" in codes


def test_the_search_task_s_red_and_green_are_drawn_isoluminant_with_its_gray(search):
    """The path end to end on a measured panel (engine build A2): checked, resolved through the
    calibration, and each object's V_F,10 luminance is the gray's (A2's Q5), red and green
    differing only in color."""
    choices = {p.name: p.choices for p in search.params}
    values = {**SEARCH_VALUES, "fix_luminance": 40.0, "target_appearance": choices["target_appearance"][0],
              "distractor_appearance": choices["distractor_appearance"][0]}
    array = _load("visual_search", "ARRAY")

    s = screen.resolve({"search": array}, values, search, GEOMETRY, frame_period=1 / 240,
                       calibration=PANEL)

    def luminance(xyz):
        L, M, _ = _apply3(PANEL.cones, xyz)
        return V_F10[0] * L + V_F10[1] * M

    gray = luminance(s.background_left)
    target = next(i for i in s.items if i.order[1] == SEARCH_VALUES["target_index"])
    distractor = next(i for i in s.items if i.order[1] != SEARCH_VALUES["target_index"])
    assert [luminance(i.fill.xyz) for i in s.items] == pytest.approx([gray] * len(s.items), rel=1e-9)
    assert target.fill.xyz != pytest.approx(distractor.fill.xyz, rel=1e-3)


def test_set_size_is_a_value_this_task_can_be_run_at_several_of(search):
    """The gap, closed: one task file, many set sizes, no structural change."""
    for n in (2, 4, 8, 12):
        census = simulate(
            search,
            Subject(seed=7, engagement=0.9, lapse=0.1, hazards={Entered: 4.0, Exited: 0.3, SaccadeTo: 5.0}),
            trials=120,
            frame_period=1 / 240,
            values={**SEARCH_VALUES, "set_size": n, "target_index": 0},
            effects=Recorded(),
        )
        assert census.hangs == 0
        assert census.outcomes.total() == 120


def test_simulation_reaches_every_outcome_the_search_task_declares(search):
    census = simulate(
        search,
        Subject(
            seed=5,
            engagement=0.85,
            lapse=0.15,
            hazards={Entered: 4.0, Exited: 0.5, SaccadeTo: 5.0},
        ),
        trials=1500,
        frame_period=1 / 240,
        values=SEARCH_VALUES,
        effects=Recorded(),
    )

    assert census.hangs == 0
    assert census.uncovered(search) == set()


# --- In direct view (direct-view spec §8) -----------------------------------------

REFERENCE = {
    "fixation_detection": "detection",
    "adaptive_detection": "adaptive_detection",
    "visual_search": "search",
    "calibration": "calibration",
}


def _range(trial: Trial, name: str) -> tuple[float, float]:
    (param,) = [p for p in trial.params if p.name == name]
    return (param.low, param.high)


@pytest.mark.parametrize("name", sorted(REFERENCE))
def test_every_reference_task_is_written_for_direct_view(name):
    """The first animal task runs in direct view (PI, 2026-09-28), and these are the
    tasks that stand for it."""
    assert _load(name, REFERENCE[name]).view == "direct"


def test_the_interim_narrowing_is_undone(detection, adaptive, search):
    """The ranges the stereoscope's ±12° mask forced on 2026-09-28, back to what they
    were, now that direct view's field is what they are checked against."""
    assert _range(detection, "target_x") == (-16.0, 16.0)
    assert _range(adaptive, "target_x") == (-16.0, 16.0)
    assert _range(adaptive, "target_eccentricity") == (2.0, 16.0)
    assert _range(search, "array_eccentricity") == (5.0, 14.0)


def test_the_calibration_task_passes_every_load_time_check_in_direct_view():
    allocation = _load("allocation", "ALLOCATION")

    assert check(_load("calibration", "calibration"), allocation, geometry=GEOMETRY) == []


def test_the_calibration_task_can_present_direct_views_whole_constellation():
    """Its ranges are the ±15° region the constellation is placed over, so every
    target the block schedules is one the task declares."""
    task = _load("calibration", "calibration")
    (x_low, x_high), (y_low, y_high) = _range(task, "target_x"), _range(task, "target_y")

    assert (x_low, x_high, y_low, y_high) == (-15.0, 15.0, -15.0, 15.0)
    for x, y in constellation(GEOMETRY):
        assert x_low <= x <= x_high and y_low <= y <= y_high


def test_a_direct_view_task_is_refused_in_the_stereoscope_for_its_field_and_warned_for_its_setup(
    detection,
):
    """What a session start says if the operator picks the stereoscope for this task: the ±16°
    its mask cannot show refuses (A15, kept), and the mismatch of setups is a warning (XC-352's
    A12; the PI, 2026-10-11)."""
    allocation = _load("allocation", "ALLOCATION")
    found = {f.code: f for f in check(detection, allocation, geometry=RIG.stereoscope(1.6))}

    assert set(found) == {"wrong-setup", "stimulus-off-screen"}
    assert found["stimulus-off-screen"].blocking and found["wrong-setup"].is_warning


def test_the_fixation_task_starts_from_the_values_the_console_mockup_shows():
    """P4d-2b spec §6.2 ("Starting values are the task's own"), with the values the
    mockup the PI reviewed shows for it (`TASKS.fixation_detection`) -- the ones every
    end-to-end test has run it at (`tests/test_cli.py`'s `_TASK_SETS`) -- each inside its
    own range. Its appearance is left unset, as every test has left it; its `target_y`, added by
    the PI on 2026-10-11 ("shouldnt there also be a target_y?"), starts on the horizontal
    meridian."""
    params = _load_task(TASKS / "fixation_detection.py").params

    assert {param.name: param.start for param in params} == {
        "fix_acquisition": 4.0, "fix_hold": 0.3, "response_deadline": 0.6, "target_hold": 0.2,
        "fix_window": 2.0, "target_window": 3.0, "target_x": 10.0, "target_y": 0.0,
        "target_appearance": None, "fix_luminance": 40.0, "target_luminance": 40.0,
    }
    for param in params:
        if param.start is not None:
            assert param.low <= param.start <= param.high, param.name


@pytest.mark.parametrize("module, attribute", [
    ("fixation_detection", "detection"),
    ("adaptive_detection", "adaptive_detection"),
    ("visual_search", "search"),
    ("calibration", "calibration"),
])
def test_each_reference_task_lights_its_achromatic_stimuli_at_40_cd_m2(module, attribute):
    trial = _load(module, attribute)
    luminances = [p for p in trial.params if p.unit == "cd/m2"]
    assert luminances
    assert all((p.low, p.high, p.start) == (0.0, SRGB_WHITE_CD_M2, 40.0) for p in luminances)


@pytest.mark.parametrize("name", sorted(REFERENCE))
def test_on_the_default_every_reference_task_runs_in_every_kind_with_its_warnings(name):
    """Spec §7.2-7.3 on the four tasks, as the PI revised COL-02 and COL-03 (2026-10-11, XC-352's
    A19 and A21): each runs on the default calibration in every session kind, recording included,
    with its warnings -- the search task's isoluminant colors among them. **The search task's
    isoluminant red and green are just outside the sRGB standard's gamut** (a primary weight of
    -0.003 to -0.006), which its isoluminance refusal hid until then: `unrealizable-color` warns of
    them, naming the light the panel shows (XC-352's A20)."""
    found = check(_load(name, REFERENCE[name]), _load("allocation", "ALLOCATION"),
                  geometry=GEOMETRY, calibration=SRGB)

    refusing = {f.code for f in found if any(f.refuses(kind) for kind in SESSION_KINDS)}
    warned = {f.code for f in found if f.is_warning}
    assert refusing == set()
    if name == "visual_search":
        assert warned == {"isoluminance-on-default", "unrealizable-color", "color-on-default",
                          "contrast-on-default"}
    else:
        assert warned == {"contrast-on-default"}


@pytest.fixture(scope="module")
def training() -> Trial:
    return _load("visual_search_training", "search")


def test_the_training_variant_is_the_search_task_with_ordinary_colors(search, training):
    """N§4 batch 2: "a training variant uses ordinary red and green (no isoluminance claim)".
    Everything but the colors and their two luminances is the search task's own."""
    assert (training.states, training.windows, training.view, training.start) == (
        search.states, search.windows, search.view, search.start)
    theirs = {p.name: p for p in search.params}
    ours = {p.name: p for p in training.params}
    assert set(ours) - set(theirs) == {"red_luminance", "green_luminance"}
    for name in set(theirs) - {"target_appearance", "distractor_appearance"}:
        assert ours[name] == theirs[name], name
    assert [(p.low, p.high, p.start) for p in (ours["red_luminance"], ours["green_luminance"])] == [
        (0.0, 17.0, 15.0), (0.0, 57.0, 15.0)]
    theirs_task = _load_task(TASKS / "visual_search.py")
    ours_task = _load_task(TASKS / "visual_search_training.py")
    assert (ours_task.reaction_time, ours_task.choice) == (
        theirs_task.reaction_time, theirs_task.choice)
    assert {name: meaning for name, meaning in ours_task.meanings.items()
            if name not in ("red_luminance", "green_luminance")} == theirs_task.meanings


def test_the_training_variant_runs_on_the_default_in_every_kind_with_its_warnings(training):
    """COL-02, revised (the PI, 2026-10-11): a warning in recording too."""
    found = check(training, _load("allocation", "ALLOCATION"), geometry=GEOMETRY, calibration=SRGB)

    assert [f for f in found if any(f.refuses(kind) for kind in SESSION_KINDS)] == []
    assert {f.code for f in found if f.is_warning} == {"color-on-default", "contrast-on-default"}


def test_simulation_reaches_every_outcome_the_training_variant_declares(training):
    census = simulate(
        training,
        Subject(seed=5, engagement=0.85, lapse=0.15,
                hazards={Entered: 4.0, Exited: 0.5, SaccadeTo: 5.0}),
        trials=1500, frame_period=1 / 240, values=SEARCH_VALUES, effects=Recorded(),
    )

    assert census.hangs == 0
    assert census.uncovered(training) == set()


def test_each_color_reads_its_own_luminance_setting_and_nothing_else(training):
    """Q3: a person removes a brightness cue live, one color at a time. Red target among green
    distractors, then the reverse; moving one setting moves only that color's light."""
    choices = {p.name: p.choices for p in training.params}
    array = _load("visual_search_training", "ARRAY")

    def lights(target, among, red, green):
        values = {**SEARCH_VALUES, "target_appearance": choices["target_appearance"][target],
                  "distractor_appearance": choices["distractor_appearance"][among],
                  "red_luminance": red, "green_luminance": green}
        s = screen.resolve({"search": array}, values, training, GEOMETRY, frame_period=1 / 240)
        by_index = {i.order[1]: i.fill.xyz[1] for i in s.items}
        return by_index[SEARCH_VALUES["target_index"]], by_index[0]

    # target_appearance[0] is the red disc and distractor_appearance[0] the green one.
    assert lights(0, 0, red=5.0, green=9.0) == pytest.approx((5.0, 9.0))
    assert lights(0, 0, red=7.0, green=9.0) == pytest.approx((7.0, 9.0))
    assert lights(0, 0, red=5.0, green=11.0) == pytest.approx((5.0, 11.0))
    # And the other way about: green target, red distractors.
    assert lights(1, 1, red=5.0, green=9.0) == pytest.approx((9.0, 5.0))


def test_the_search_task_shows_its_colors_on_a_gray_and_so_does_its_training(search, training):
    """Its red and green are contrasts about the background, so they need a lit one (engine spec
    §7.5): D65 at 16 cd/m², the training variant's too, and the red and green are the PI's 2023
    objects made isoluminant in the lab's observer (the PI's answer to the engine A2 plan's Q1)."""
    assert search.background == Gray(16.0)
    assert training.background == search.background
    assert (_load("visual_search", "RED"), _load("visual_search", "GREEN")) == (
        DKL(lum=0.0, l_m=0.603, s_lm=-0.94), DKL(lum=0.0, l_m=-0.143, s_lm=-0.87))


# --- The task object (engine build C1) ------------------------------------------------------

#: Each reference task file: its trial's attribute and the name its task object gives it.
TASK_FILES = {
    "fixation_detection": ("detection", "detection"),
    "adaptive_detection": ("adaptive_detection", "detection"),
    "visual_search": ("search", "search"),
    "visual_search_training": ("search", "search"),
    "calibration": ("calibration", "calibration"),
}

#: **Appendix B of the engine C1 plan, as the PI confirmed it** on 2026-10-11, item by item and with
#: changes, and as he revised it on reviewing the build that day (decisions.md TRN-10): the shared
#: list's kind, role, direction, what the direction reads relative to, note and why it overrides,
#: for each setting (`_said`). A list of appearances is no difficulty setting unless a task says
#: otherwise (his rule for item 1).
CONFIRMED_SHARED = {
    "fix_acquisition": (CLEAR_CUT, CRITERION, EASIER, None, "", ""),
    "fix_hold": (CLEAR_CUT, CRITERION, HARDER, None, "", ""),
    "fix_window": (CLEAR_CUT, CRITERION, EASIER, None, "", ""),
    "fix_luminance": (EXPECTED, STIMULUS, EASIER, BACKGROUND, (
        "a point farther in luminance from the background is easier to find: on black a brighter "
        "one; on a gray one farther above or below it, so a point near the gray's luminance can "
        "vanish"), ""),
    "response_deadline": (CLEAR_CUT, CRITERION, EASIER, None, "", ""),
    "target_hold": (CLEAR_CUT, CRITERION, HARDER, None, "", ""),
    "target_window": (CLEAR_CUT, CRITERION, EASIER, None, "", ""),
    "object_window": (EXPECTED, CRITERION, EASIER, None, (
        "a wider window accepts a less accurate landing on the target, and can also turn a "
        "near-miss beside a distractor into a wrong target"), ""),
    "target_appearance": (NOT_DIFFICULTY, STIMULUS, None, None, (
        "an appearance is not easier or harder in general; a task where it is what the animal "
        "judges may declare its own meaning"), ""),
    "target_luminance": (EXPECTED, STIMULUS, EASIER, BACKGROUND, (
        "a target farther in luminance from the background is easier to see: on black a brighter "
        "one, on a gray one farther above or below it; saccade latency falls as intensity rises "
        "and then levels off, so far above threshold more light changes little"), ""),
    "target_x": (NOT_DIFFICULTY, STIMULUS, None, None, (
        "the target's horizontal position; a task may declare how moving it changes the task"), ""),
    "target_y": (NOT_DIFFICULTY, STIMULUS, None, None, (
        "the target's vertical position; a task may declare how moving it changes the task"), ""),
    "set_size": (NOT_DIFFICULTY, STIMULUS, None, None, (
        "the direction depends on the search: in a pop-out search more objects make it easier, "
        "in a search without pop-out harder"), ""),
    "distractor_appearance": (NOT_DIFFICULTY, STIMULUS, None, None, (
        "what a change does depends on the search, a broad category of tasks where one "
        "definition does not serve: a task declares its own as it is created"), ""),
    "target_index": (NOT_DIFFICULTY, STIMULUS, None, None,
                     "which object of the array is the target", ""),
    "array_rotation": (NOT_DIFFICULTY, STIMULUS, None, None, (
        "turns the whole array; held fixed with target_index, it lets an animal answer by "
        "position rather than by the target's appearance"), ""),
    "array_eccentricity": (NOT_DIFFICULTY, STIMULUS, None, None, (
        "how far the array sits from fixation; what moving it does depends on the search task, "
        "and an array need not be a ring"), ""),
}
#: The pop-out search tasks' override of `set_size`, the PI's words (2026-10-11).
POP_OUT = (EXPECTED, STIMULUS, EASIER, None,
           "in a pop-out search a denser array makes the odd object stand out more",
           "a pop-out search: a denser array makes the odd object stand out more", OVERRIDE)
#: The training variant's two luminances, each read from the other.
GAP = (
    "the cue it adds is the brightness gap between the red and the green, redundant with their "
    "color, so a larger gap is easier; near equal brightness, whose point for this animal is "
    "unknown, the direction is uncertain; narrowing the gap is the fading path toward "
    "isoluminance"
)
#: And each task's own: its settings no other task declares alike, and its overrides.
CONFIRMED_OWN = {
    "fixation_detection": {},
    "adaptive_detection": {
        "target_contrast": (CLEAR_CUT, STIMULUS, EASIER, None, (
            "nothing reads it yet: no stimulus draws with it, and nothing moves it until a "
            "between-trial procedure is called (XC-242)"), "", OWN),
        "target_eccentricity": (NOT_DIFFICULTY, STIMULUS, None, None, (
            "nothing reads it yet: the target's place is target_x's and target_y's, and this "
            "setting moves nothing on screen until a between-trial procedure is called "
            "(XC-242)"), "", OWN),
    },
    "visual_search": {"set_size": POP_OUT},
    "visual_search_training": {
        "set_size": POP_OUT,
        "red_luminance": (EXPECTED, STIMULUS, EASIER, "green_luminance", GAP, "", OWN),
        "green_luminance": (EXPECTED, STIMULUS, EASIER, "red_luminance", GAP, "", OWN),
    },
    "calibration": {
        "cal_window": (CLEAR_CUT, CRITERION, EASIER, None, "", "", OWN),
        "cal_hold": (CLEAR_CUT, CRITERION, HARDER, None, "", "", OWN),
    },
}


def _said(meaning) -> tuple:
    """A meaning as the tables above write it: every field of it."""
    return (meaning.kind, meaning.role, meaning.raising, meaning.relative_to, meaning.note,
            meaning.overrides)


@pytest.mark.parametrize("name", sorted(TASK_FILES))
def test_each_reference_task_file_defines_one_task_object_over_its_trial(name):
    attribute, structure = TASK_FILES[name]
    task = _load_task(TASKS / f"{name}.py")

    assert (list(task.structures), task.default) == ([structure], structure)
    assert task.trial == _load(name, attribute)


@pytest.mark.parametrize("name", sorted(TASK_FILES))
@pytest.mark.parametrize("calibration", [None, SRGB, PANEL], ids=["none", "default", "measured"])
def test_each_reference_task_object_adds_no_finding_to_its_trials(name, calibration):
    """Its settings' meanings, its reaction time and its choice are declared and well formed: the
    task object's checks find nothing its one structure's did not."""
    task = _load_task(TASKS / f"{name}.py")
    allocation = _load("allocation", "ALLOCATION")

    assert check_task(task, allocation, geometry=GEOMETRY, calibration=calibration) == check(
        task.trial, allocation, geometry=GEOMETRY, calibration=calibration)


def test_the_shared_list_says_what_the_pi_confirmed():
    assert {name: _said(m) for name, m in COMMON.items()} == CONFIRMED_SHARED
    assert len(COMMON) == 17


@pytest.mark.parametrize("name", sorted(TASK_FILES))
def test_every_setting_of_each_reference_task_has_the_meaning_the_pi_confirmed(name):
    task = _load_task(TASKS / f"{name}.py")
    settings = [param.name for param in task.params]
    expected = {setting: (*CONFIRMED_SHARED[setting], SHARED)
                for setting in settings if setting in CONFIRMED_SHARED}
    expected.update(CONFIRMED_OWN[name])

    assert {setting: (*_said(meaning), origin)
            for setting, (meaning, origin) in resolved(task).items()} == expected
    assert set(expected) == set(settings), "every setting has a meaning"


@pytest.mark.parametrize("name", sorted(TASK_FILES))
def test_each_reference_task_needs_a_fixed_head_and_warns_without_one(name):
    """The PI, 2026-10-11 (the engine C1 plan's Appendix B, item 31): "kiosk will be head free, in
    the rig will be head fixed. we do not have head tracking in the rig". Every reference task warns
    in a chaired or cage-side session, and only there, and is refused in none (the PI, 2026-10-11:
    "warnings are more appropriate most of the time")."""
    task = _load_task(TASKS / f"{name}.py")

    def head(deployment: Deployment) -> list:
        return [f for f in check_task(task, deployment=deployment) if f.code == "head-not-fixed"]

    assert task.needs_fixed_head is True
    assert [bool(head(d)) for d in Deployment] == [
        d is not Deployment.RIG_FIXED for d in Deployment]
    assert all(f.is_warning and not f.refuses(kind)
               for d in Deployment for f in head(d) for kind in SESSION_KINDS)


def test_the_reference_tasks_declare_twenty_three_settings_between_them():
    assert len({param.name for name in TASK_FILES
                for param in _load_task(TASKS / f"{name}.py").params}) == 23


def test_each_reference_task_says_how_its_reaction_time_is_defined_and_what_it_offers():
    """XC-288 §4.3, Appendix B: the detection tasks time a saccade to their one target and offer no
    choice; the search tasks time a saccade to any object and offer the target and the distractors;
    the calibration task times its target's acquisition and offers no choice."""
    def declared(name):
        task = _load_task(TASKS / f"{name}.py")
        offered = task.choice if task.choice is NO_CHOICE else (task.choice.objects, task.choice.by)
        return task.reaction_time.state, task.reaction_time.to, offered

    assert declared("fixation_detection") == declared("adaptive_detection") == (
        "stim_on", ("verify",), NO_CHOICE)
    assert declared("visual_search") == declared("visual_search_training") == (
        "array_on", ("verify", Outcome.WRONG_TARGET),
        (("search.target", "search.distractor"), "saccade"))
    assert declared("calibration") == ("await_fix", ("hold",), NO_CHOICE)


#: **Appendix B of the engine C2a plan, as the PI confirmed it** on 2026-10-13 ("Accept, target
#: break"), items 5 to 12: each reference task's counting table, each naming the state its
#: stimulus appears in, none with a repeat limit (items 11 and 12).
CONFIRMED_COUNTING = {
    "fixation_detection": Counting(after_stimulus=OWED, appears="stim_on", withholding=True),
    "adaptive_detection": Counting(after_stimulus=OWED, appears="stim_on", withholding=True),
    "visual_search": Counting(after_stimulus=SPENT, appears="array_on"),
    "visual_search_training": Counting(after_stimulus=OWED, appears="array_on"),
    "calibration": Counting(after_stimulus=OWED, appears="await_fix"),
}


@pytest.mark.parametrize("name", sorted(TASK_FILES))
def test_each_reference_task_counts_as_the_pi_confirmed(name):
    """Engine spec §16.1-16.2; the PI, 2026-10-11: both detection tasks count no response as a
    miss, and each task says what a break after its stimulus does. No reference task sets a repeat
    limit (the PI: "no limit")."""
    task = _load_task(TASKS / f"{name}.py")

    assert task.trial.counting == CONFIRMED_COUNTING[name]
    assert task.trial.counting.cap is None
    assert "undeclared-counting" in {
        f.code for f in check_task(replace(task, structures={
            task.default: replace(task.trial, counting=None)}))}


def test_a_search_task_that_says_nothing_of_its_choice_is_refused():
    """The plan's engineering review, I2: with its choice unset, `visual_search` would load and its
    trials would record no object chosen (build C7); it is refused at load instead."""
    task = _load_task(TASKS / "visual_search.py")

    assert "undeclared-choice" not in {f.code for f in check_task(task)}
    assert "undeclared-choice" in {f.code for f in check_task(replace(task, choice=None))}
